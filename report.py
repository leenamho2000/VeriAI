# report.py — final corrected version with proper syntax and formatting
from fpdf import FPDF
from datetime import datetime
from pathlib import Path
import platform
import re

# ---------- 텍스트 유틸 ----------
_ZWS = "\u200b"  # zero-width space

def _soft_wrap_token(tok: str, chunk: int = 30) -> str:
    """공백이 전혀 없는 긴 토큰(URL 등)을 ZWS로 잘라서 줄바꿈 가능하게 만든다."""
    t = tok or ""
    if len(t) <= chunk:
        return t
    return _ZWS.join(t[i:i + chunk] for i in range(0, len(t), chunk))

def _soft_wrap_line(text: str, token_chunk: int = 30) -> str:
    """한 줄 전체를 토큰 단위로 소프트랩 적용."""
    parts = []
    for tok in re.split(r"(\s+)", str(text or "")):
        if tok.strip() and len(tok) > token_chunk and not re.search(r"\s", tok):
            parts.append(_soft_wrap_token(tok, token_chunk))
        else:
            parts.append(tok)
    s = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    return s

# ---------- 폰트 탐색 ----------
def _find_font_path() -> str | None:
    here = Path(__file__).parent
    candidates = [
        here / "fonts" / "NotoSansKR-Regular.otf",
        here / "fonts" / "NotoSansKR-Regular.ttf",
        here / "fonts" / "NanumGothic.ttf",
        here / "fonts" / "NanumGothic-Regular.ttf",
        here / "fonts" / "malgun.ttf",
    ]
    sysname = platform.system().lower()
    if "windows" in sysname:
        candidates += [Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/NanumGothic.ttf")]
    elif "linux" in sysname:
        candidates += [Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansKR-Regular.otf")]
    elif "darwin" in sysname:
        candidates += [Path("/Library/Fonts/NanumGothic.ttf"), Path("/Library/Fonts/NotoSansKR-Regular.otf"), Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")]
    
    for p in candidates:
        if p and Path(p).exists():
            return str(p)
    return None

class Report(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        self.set_left_margin(12)
        self.set_right_margin(12)
        font_path = _find_font_path()
        if not font_path:
            raise RuntimeError("유니코드 폰트를 찾지 못했습니다. 프로젝트 루트에 fonts 폴더를 만들고 NotoSansKR-Regular.otf 또는 NanumGothic.ttf 를 넣어주세요.")
        self.add_font('KR', '', font_path, uni=True)
        try:
            self.add_font('KR', 'B', font_path, uni=True)
        except Exception:
            pass

    def header(self):
        self.set_font('KR', 'B', 14)
        self.cell(0, 10, 'VeriAI 분석 리포트', ln=1, align='L')
        self.set_font('KR', '', 10)
        self.cell(0, 6, datetime.now().strftime('%Y-%m-%d %H:%M'), ln=1, align='L')
        self.ln(2)

    def para(self, text: str, h: float = 5):
        self.set_x(self.l_margin)
        self.set_font('KR', '', 10)
        safe = _soft_wrap_line(text, token_chunk=34)
        self.multi_cell(self.epw, h, safe)

    def para_bold(self, text: str, h: float = 5):
        self.set_x(self.l_margin)
        self.set_font('KR', 'B', 10)
        safe = _soft_wrap_line(text, token_chunk=34)
        self.multi_cell(self.epw, h, safe)

def export_pdf(summary: dict, rows: list, outputs: list, path: str, visuals: list = None):
    pdf = Report()
    pdf.add_page()
    # ... (summary, LLM results 출력 부분은 기존과 동일) ...
    pdf.set_font('KR','B',12); pdf.cell(0, 8, '요약', ln=1); pdf.set_font('KR','',11)
    for k, v in summary.items(): pdf.para(f"  - {k}: {v}", h=5)
    pdf.ln(4)
    if outputs:
        pdf.set_font('KR','B',12); pdf.cell(0, 8, 'LLM 상세 분석 결과 (Top-K)', ln=1)
        for i, item in enumerate(outputs):
            sent = item.get("sentence", ""); res = item.get("result", {}) or {}
            pdf.para_bold(f"{i+1}. 원문: {sent}", h=5)
            if "risk_reasons" in res:
                if rr := ", ".join(res.get("risk_reasons") or []): pdf.para(f"  - 위험 사유: {rr}")
                if ex := res.get("explanation", ""): pdf.para(f"  - 상세 설명: {ex}")
            elif "issues" in res:
                if issues := ", ".join(res.get("issues") or []): pdf.para(f"  - 주요 이슈: {issues}")
            pdf.ln(3)

    # --- PDF 차트 삽입 최종 수정 ---
    if visuals:
        if pdf.get_y() > 180 or not outputs:
            pdf.add_page()
            
        pdf.set_font('KR', 'B', 12)
        pdf.cell(0, 8, '주요 시각화 분석', ln=1)
        
        for vis in visuals:
            img_path, title = vis["path"], vis["title"]
            if Path(img_path).exists():
                pdf.para_bold(f"차트: {title}", h=6)
                # 가장 단순한 형태로 페이지 폭에 맞춰 이미지 삽입
                pdf.image(img_path, w=pdf.epw - 2)
                pdf.ln(2)

    pdf.output(path)
    return path