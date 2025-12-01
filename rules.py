# rules.py — VeriAI (enhanced hits + flexible config)
# -----------------------------------------------------------------------------
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# ====== Config loader (ad/report) =================================================
ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"
RULE_FILES = {
    "ad": CONFIG_DIR / "ad_rules.json",
    "report": CONFIG_DIR / "report_rules.json",
}

# fallback: 루트 경로에도 파일이 있으면 사용
def _resolve_rule_file(name: str) -> Path:
    primary = RULE_FILES.get(name)
    if primary and primary.exists():
        return primary
    alt = ROOT / f"{name}_rules.json"
    if alt.exists():
        return alt
    raise FileNotFoundError(f"Ruleset file not found (tried): {primary} / {alt}")

CFG: Optional[dict] = None
W: Dict[str, float] = {}
TH: Dict[str, float] = {}
RX: Dict[str, re.Pattern] = {}
LEX: Dict[str, List[str]] = {}
CURRENT_RULESET: Optional[str] = None

def load_rules(ruleset: str = "ad") -> None:
    """Load selected ruleset (ad/report) and compile globals."""
    global CFG, W, TH, RX, LEX, CURRENT_RULESET
    ruleset = ruleset if ruleset in ("ad","report") else "ad"
    path = _resolve_rule_file(ruleset)
    CFG = json.loads(path.read_text(encoding="utf-8"))
    W = CFG.get("weights", {})
    TH = CFG.get("thresholds", {"high": 70, "medium": 40})
    RX = {k: re.compile(v) for k, v in CFG.get("regex", {}).items()}
    LEX = CFG.get("lexicons", {})
    CURRENT_RULESET = ruleset

# initial load
load_rules("ad")

# ====== Safe getters ==============================================================
def L(name: str) -> List[str]:
    return LEX.get(name, [])

def RXget(name: str, default: str = r"$") -> re.Pattern:
    return RX.get(name, re.compile(default))

def _count_contains(s: str, words: List[str]) -> int:
    """Counts whole-word occurrences of words from a list in a string."""
    if not words:
        return 0
    # 단어 경계(\b)를 사용하여 단어 단위로만 매칭되도록 수정
    return sum(1 for w in words if w and re.search(r'\b' + re.escape(w) + r'\b', s))

def _find_hits(s: str, words: List[str], *, limit: int = 50) -> List[str]:
    """Finds whole-word hits from a list in a string."""
    # 단어 경계(\b)를 사용하여 단어 단위로만 매칭되도록 수정
    hits = [w for w in words if w and re.search(r'\b' + re.escape(w) + r'\b', s)]
    # 길이 긴 단어 우선(겹침 방지)
    hits = sorted(set(hits), key=lambda x: (-len(x), x))
    return hits[:limit]

# ====== Robust sentence splitting ================================================
def _normalize_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\u00A0", " ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"(,{2,}|<+|>+|;{2,}|·{2,})", ", ", t)
    t = re.sub(
        r"^\s*(?:[-–—∙·•◦►▫▪➤*]|[0-9]+\.|[0-9]+\)|\([0-9]+\)|[A-Za-z]\)|[①-⑳])\s+",
        "• ",
        t,
        flags=re.M,
    )
    return t

def _merge_hard_wraps(text: str) -> str:
    pat1 = re.compile(
        r"([^\.\!\?;:\"”'’\)\]\}，。！？…])\s*\n(?!\s*(?:•|#|\d+[\.\)]|[①-⑳]))\s*", re.M
    )
    text = pat1.sub(lambda m: (m.group(1) or "") + " ", text)
    pat2 = re.compile(r",(?:\s*\n)+\s*(?!\s*(?:•|#|\d+[\.\)]|[①-⑳]))", re.M)
    text = pat2.sub(", ", text)
    return text

def _final_split(text: str) -> List[str]:
    splitter = re.compile(r"(?:(?<=[\.!?…。？！])\s+|(?=^\s*•\s+))", re.M)
    parts = splitter.split(text)
    out: List[str] = []
    for p in parts:
        s = (p or "").strip()
        if not s:
            continue
        if s.startswith("• ") and not re.search(r"[\.!?…。？！]$", s):
            s += "."
        if len(re.sub(r"[^\w가-힣]", "", s)) < 3:
            continue
        out.append(s)
    dedup, seen = [], set()
    for s in out:
        key = re.sub(r"\s+", " ", s)
        if key not in seen:
            seen.add(key)
            dedup.append(s)
    return dedup

def split_sentences(text: str) -> List[str]:
    t = _normalize_text(text or "")
    t = _merge_hard_wraps(t)
    return _final_split(t)

# ====== Feature extraction & scoring =============================================
def extract_features(sentence: str) -> Dict[str, Any]:
    s = sentence.strip()

    # regex-based indicators
    has_number_unit = bool(RXget("number_unit").search(s))
    has_year = bool(RXget("year").search(s))
    has_scope = bool(RXget("scope").search(s))
    has_url = bool(RXget("url").search(s))
    has_award_rating = bool(RXget("award_or_rating").search(s))
    has_money = bool(RXget("money").search(s))
    has_time_phrase = bool(RXget("time_phrase").search(s))
    has_percent_change = bool(RXget("percent_change").search(s))

    # report-specific
    has_citation_sq = bool(RXget("citation_square").search(s))
    has_citation_yr = bool(RXget("citation_year").search(s))
    has_doi = bool(RXget("doi").search(s))
    has_fig_table = bool(RXget("fig_table").search(s))
    has_stats = bool(RXget("stats").search(s))

    # lexicon counts
    c_vague = _count_contains(s, L("vague"))
    c_overclaim = _count_contains(s, L("overclaim"))
    c_future = _count_contains(s, L("future"))
    c_cov_risky = _count_contains(s, L("coverage_risky"))
    c_cov_clarify = _count_contains(s, L("coverage_clarifier"))
    c_standards = _count_contains(s, L("standards")) + _count_contains(s, L("methodology"))
    c_thirdparty = _count_contains(s, L("third_party"))
    c_offset_terms = _count_contains(s, L("offset_terms"))
    c_greenhot = _count_contains(s, L("labels_greenwashing_hot"))

    in_category = any(
        _count_contains(s, L(name)) > 0
        for name in ["emissions", "energy", "packaging", "waste", "water", "biodiversity", "chemicals", "transport"]
    )

    # Evidence score
    evidence = 0
    evidence += 3 if has_number_unit else 0
    evidence += 3 if has_year else 0
    evidence += 3 if c_standards > 0 else 0
    evidence += 4 if c_thirdparty > 0 else 0
    evidence += 2 if has_url else 0
    evidence += 1 if has_award_rating else 0
    evidence += 1 if has_money else 0
    evidence += 1 if in_category else 0
    if CURRENT_RULESET == "report":
        evidence += 2 if (has_citation_sq or has_citation_yr) else 0
        evidence += 2 if has_doi else 0
        evidence += 1 if has_fig_table else 0
        evidence += 2 if has_stats else 0
    evidence = min(16, evidence)

    # Vagueness
    vagueness = 0
    vagueness += min(8, c_vague)
    vagueness += 2 if c_overclaim > 0 else 0
    vagueness += 2 if c_future > 0 else 0
    vagueness += 1 if c_greenhot > 0 else 0
    if CURRENT_RULESET == "report" and LEX.get("weasel"):
        if any(w in s for w in L("weasel")):
            vagueness = min(16, vagueness + 1)

    # Coverage
    coverage_penalty = 2 if c_cov_risky > 0 else 0
    if coverage_penalty and c_cov_clarify > 0:
        coverage_penalty = max(0, coverage_penalty - 1)

    # Temporal
    temporal_penalty = 0
    if c_future > 0 and not has_year:
        temporal_penalty += 2
    if c_future > 0 and not (has_time_phrase or has_percent_change):
        temporal_penalty += 1
    if has_time_phrase or has_percent_change:
        temporal_penalty = max(0, temporal_penalty - 1)
    temporal_penalty = min(4, temporal_penalty)

    # Language
    language_risk = min(8, (4 if c_overclaim > 0 else 0) + min(4, c_vague))

    # Offset
    offset_flag = 1 if (c_offset_terms > 0 and not (has_year or has_number_unit or has_scope)) else 0

    hits = {
        "vague": _find_hits(s, L("vague")),
        "overclaim": _find_hits(s, L("overclaim")),
        "future": _find_hits(s, L("future")),
        "coverage_risky": _find_hits(s, L("coverage_risky")),
        "coverage_clarifier": _find_hits(s, L("coverage_clarifier")),
        "standards_method": _find_hits(s, L("standards")) + _find_hits(s, L("methodology")),
        "third_party": _find_hits(s, L("third_party")),
        "offset_terms": _find_hits(s, L("offset_terms")),
    }

    return {
        "has_number_unit": has_number_unit,
        "has_year": has_year,
        "has_scope": has_scope,
        "has_url": has_url,
        "has_award_or_rating": has_award_rating,
        "has_money": has_money,
        "has_time_phrase": has_time_phrase,
        "has_percent_change": has_percent_change,
        "has_citation_square": has_citation_sq,
        "has_citation_year": has_citation_yr,
        "has_doi": has_doi,
        "has_fig_table": has_fig_table,
        "has_stats": has_stats,
        "count_vague": c_vague,
        "count_overclaim": c_overclaim,
        "count_future": c_future,
        "count_coverage_risky": c_cov_risky,
        "count_coverage_clarifier": c_cov_clarify,
        "count_standards_method": c_standards,
        "count_third_party": c_thirdparty,
        "count_greenhot": c_greenhot,
        "offset_flag": offset_flag,
        "evidence_score": evidence,
        "vagueness_score": vagueness,
        "coverage_penalty": coverage_penalty,
        "temporal_penalty": temporal_penalty,
        "language_risk": language_risk,
        "hits": hits,
    }

def score_sentence(sentence: str) -> Dict[str, Any]:
    f = extract_features(sentence)
    risk = 100 * (
        W.get("evidence_inverse", 0.30) * (1 - f.get("evidence_score", 0) / 16)
        + W.get("vagueness", 0.22) * (f.get("vagueness_score", 0) / 16)
        + W.get("language", 0.12) * (f.get("language_risk", 0) / 8)
        + W.get("coverage", 0.10) * (f.get("coverage_penalty", 0) / 6)
        + W.get("temporal", 0.16) * (f.get("temporal_penalty", 0) / 4)
        + W.get("offset_risk", 0.10) * f.get("offset_flag", 0)
    )
    risk = max(0, min(100, round(risk, 1)))
    label = "High" if risk >= TH.get("high", 70) else ("Medium" if risk >= TH.get("medium", 40) else "Low")
    f["risk"] = risk
    f["label"] = label
    return f

def analyze_text(text: str, ruleset: str = None) -> List[Dict[str, Any]]:
    if ruleset and ruleset != CURRENT_RULESET:
        load_rules(ruleset)
    sents = split_sentences(text)
    rows: List[Dict[str, Any]] = []
    for s in sents:
        sc = score_sentence(s)
        rows.append({"sentence": s, **sc})
    return rows
# -----------------------------------------------------------------------------
