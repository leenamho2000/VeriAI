# llm.py — updated with caching and few-shot prompts
import os, json, re
from typing import List, Dict, Any
from openai import OpenAI
import streamlit as st

def _u(s):
    if s is None: return ""
    if not isinstance(s, str): s = str(s)
    return s.encode("utf-8", "ignore").decode("utf-8")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_OUT_TOKENS = int(os.getenv("OPENAI_MAX_OUT_TOKENS", "1200"))

def _get_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다. 환경변수를 설정하고 다시 시도하세요.")
    return OpenAI(api_key=key)

def _call_openai(system: str, user: str) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        max_tokens=MAX_OUT_TOKENS,
        messages=[
            {"role": "system", "content": _u(system)},
            {"role": "user", "content": _u(user)},
        ],
    )
    return resp.choices[0].message.content

def _extract_json_array(text: str):
    text = _u(text)
    m = re.search(r"```json\s*(\[.*?\])\s*```", text, re.S)
    if m: return json.loads(m.group(1))
    m2 = re.search(r"(\[.*\])", text, re.S)
    if m2:
        try: return json.loads(m2.group(1))
        except: pass
    try:
        obj = json.loads(text)
        if isinstance(obj, list): return obj
        for k in ("results","data","items"):
            if isinstance(obj, dict) and isinstance(obj.get(k), list):
                return obj[k]
    except: pass
    raise ValueError("모델 응답에서 JSON 배열을 추출하지 못했습니다.")

# ---- Prompts ----
_AD_SYSTEM = _u("""당신은 환경광고/표시의 사실성·그린워싱 위험을 점검하는 분석가다.
1) 왜 위험한지 분류/설명하고, 2) 입력 텍스트에 실제 존재하는 URL만 existing_citations에 넣고,
3) 부족한 근거를 채우기 위한 evidence_needed와 검색 쿼리를 제안하라.
분류 태그: ["모호어","과장표현","미래시제·계획부재","범위과대","근거부족","오프셋의존","기한·지표부재"].
링크 지어내지 말 것. 한국어로 답하고, 출력은 JSON 배열 하나만.""")

_AD_USER_TMPL = """다음 위험 문장 리스트를 분석해줘.
[메타]
- 문서종류: 환경 광고/표시
- 문장_리스트: {sentences_json}
- 문장별 사전점수(참고): {scores_json}

[예시]
- 입력: {{"id": 1, "text": "우리의 혁신적인 기술로 지구를 위한 지속가능한 미래를 만듭니다."}}
- 출력:
{{
  "id": 1,
  "risk_reasons": ["모호어", "근거부족", "기한·지표부재"],
  "explanation": "'혁신적인 기술', '지속가능한 미래' 등은 의미가 불분명한 마케팅 용어입니다. 어떤 기술인지, '지속가능성'을 어떤 기준으로 측정하는지 명시해야 합니다.",
  "existing_citations": [],
  "evidence_needed": ["기술의 구체적인 원리/명칭", "지속가능성 기여도 정량지표(예: tCO2e 감축량)", "기준연도/목표연도", "외부 기술 검증 보고서"],
  "suggested_queries": ["(회사명) 지속가능성 보고서", "(기술명) 환경 영향 평가 결과"],
  "reference_standards": ["ISO 14021", "FTC Green Guides"],
  "confidence": 0.9
}}

[요구]
각 문장마다 위 예시와 같은 JSON 항목으로만 출력:
{{
  "id": <원문 id>,
  "risk_reasons": ["모호어","범위과대",...],
  "explanation": "<누락된 지표/기간/적용범위/단위 등>",
  "existing_citations": [],
  "evidence_needed": ["정량지표(tCO2e, kWh)","기준연도/목표연도","적용범위(조직/제품/공급망)","외부검증/인증"],
  "suggested_queries": ["<검증용 검색쿼리 #1>","<검증용 검색쿼리 #2>"],
  "reference_standards": ["GHG Protocol","SBTi","ISO 14064"],
  "confidence": 0.0
}}
출력은 JSON 배열 하나만."""

_REPORT_SYSTEM = _u("""당신은 일반 보고서의 근거성·명확성·재현가능성을 점검하는 에디터다.
문장의 애매/허세/근거부족 요소를 지적하고, 무엇을(데이터·방법·지표·표/그림·인용) 추가할지 제안하라.
입력에 존재하는 URL만 existing_citations에 넣고, 없으면 빈 배열. 한국어로, JSON 배열 하나만.""")

_REPORT_USER_TMPL = """다음 위험 문장 리스트를 분석해줘.
[메타]
- 문서종류: 일반 보고서
- 문장_리스트: {sentences_json}
- 문장별 사전점수(참고): {scores_json}

[예시]
- 입력: {{"id": 1, "text": "이 시스템은 전반적으로 상당한 성능 개선을 보였습니다."}}
- 출력:
{{
  "id": 1,
  "issues": ["weasel word", "근거/출처 부재", "통계/표본 정보 부족"],
  "what_to_add": {{
    "metrics": ["'성능 개선'의 구체적 지표(예: 응답시간, 처리량)", "개선율(%) 또는 절대수치 변화량", "측정 기간"],
    "method": ["성능 측정 방법론", "테스트 환경(HW/SW 스펙)", "비교 대상(Baseline) 시스템 정보"],
    "tables_figures": ["Table: 전후 성능 지표 비교표", "Fig: 시간에 따른 성능 변화 그래프"],
    "citations": ["내부 성능 테스트 결과 보고서 링크"]
  }},
  "existing_citations": [],
  "suggested_queries": ["시스템 성능 벤치마크 방법론", "(시스템명) 성능 측정 논문"],
  "confidence": 0.9
}}

[요구]
각 문장마다 위 예시와 같은 JSON 항목으로만 출력:
{{
  "id": <원문 id>,
  "issues": ["weasel word","근거/출처 부재","범위/대상 불명확","기간/마일스톤 없음","통계/표본 정보 부족"],
  "what_to_add": {{
    "metrics": ["정확한 수치+단위","기준연도/기간","성공기준(KPI)"],
    "method": ["표본(n)/수집방법","통계검정(p, CI)","재현 가능한 절차(SOP)"],
    "tables_figures": ["Fig: 프로세스/아키텍처","Table: 지표 정의/결과 요약"],
    "citations": ["핵심 선행연구/표준","내부 로그/스크린샷","감사/검증보고서"]
  }},
  "existing_citations": [],
  "suggested_queries": ["<근거 보강용 검색쿼리>"],
  "confidence": 0.0
}}
출력은 JSON 배열 하나만."""

@st.cache_data(show_spinner="LLM이 광고 문장을 분석 중입니다...")
def analyze_ad(hashable_items: tuple) -> List[Dict[str, Any]]:
    # --- 추가된 부분 시작 ---
    # 캐시를 위해 변환된 tuple을 다시 list of dicts로 복원
    items_list = [dict(item) for item in hashable_items]
    # --- 추가된 부분 끝 ---
    
    sentences = [{"id": int(it["id"]), "text": _u(it["text"])} for it in items_list]
    scores = {int(it["id"]): {"risk": it.get("risk"), "label": it.get("label")} for it in items_list}
    user = _AD_USER_TMPL.format(
        sentences_json=json.dumps(sentences, ensure_ascii=False),
        scores_json=json.dumps(scores, ensure_ascii=False),
    )
    raw = _call_openai(_AD_SYSTEM, user)
    return _extract_json_array(raw)

@st.cache_data(show_spinner="LLM이 보고서 문장을 분석 중입니다...")
def analyze_report(hashable_items: tuple) -> List[Dict[str, Any]]:
    # --- 추가된 부분 시작 ---
    # 캐시를 위해 변환된 tuple을 다시 list of dicts로 복원
    items_list = [dict(item) for item in hashable_items]
    # --- 추가된 부분 끝 ---

    sentences = [{"id": int(it["id"]), "text": _u(it["text"])} for it in items_list]
    scores = {int(it["id"]): {"risk": it.get("risk"), "label": it.get("label")} for it in items_list}
    user = _REPORT_USER_TMPL.format(
        sentences_json=json.dumps(sentences, ensure_ascii=False),
        scores_json=json.dumps(scores, ensure_ascii=False),
    )
    raw = _call_openai(_REPORT_SYSTEM, user)
    return _extract_json_array(raw)