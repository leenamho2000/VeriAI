# VeriAI 🧠🌿  
문서 신뢰도 & ESG·그린워싱 위험도 분석 도구

> 환경 광고/ESG 문서/일반 보고서를 문장 단위로 분석해 **근거 부족·모호한 표현·범위 과장** 등을 점수화하고, 상위 위험 문장만 LLM으로 심층 분석해 리포트까지 만들어 주는 도구입니다.

---

## 🔎 프로젝트 개요

**VeriAI**는 다음과 같은 워크플로우로 동작합니다.

1. 사용자가 텍스트를 붙여넣거나, URL을 입력하면 본문을 추출합니다.
2. 미리 정의된 규칙(`config/ad_rules.json`, `config/report_rules.json`)에 따라  
   각 문장의 **증거성, 모호성, 범위, 시점, 언어적 위험, 오프셋 의존도** 등을 정량화합니다.
3. 문장별로 0–100 사이의 **위험도 점수 risk**와 **등급 High/Medium/Low**를 부여합니다.
4. 위험도가 높은 상위 K개 문장을 골라 OpenAI LLM에 보내,  
   - 환경 광고 모드: 왜 그린워싱 위험이 있는지, 어떤 근거가 추가되어야 하는지  
   - 일반 보고서 모드: 어떤 수치/방법/표/인용이 부족한지  
   를 JSON 형태로 받아옵니다.
5. 전체 결과를 **대시보드 Streamlit**로 탐색하고,  
   **CSV / PDF 리포트**로 내보낼 수 있습니다.

---

## 🌍 Project Overview (EN)

**VeriAI** is an AI-assisted document checker for:

- ESG / environmental advertisements (greenwashing risk)
- General business / technical reports (evidence & clarity)

It:

- Splits documents into sentences
- Scores each sentence with rule-based features
- Sends only the riskiest ones to an LLM for deeper review
- Provides interactive visualizations and exports (CSV, PDF)

---

## ✨ 주요 기능

- **📥 입력**
  - 텍스트 직접 입력
  - URL 입력 → `trafilatura`로 본문 자동 추출
- **⚖️ 규칙 기반 정량 분석**
  - 수치·연도·표준·제3자 검증 등 **근거 점수(evidence_score)**
  - 모호어/과장/미래시제 등 **모호성 점수(vagueness_score)**
  - 적용 범위/시점/오프셋 사용에 따른 위험도
  - 0–100 위험도(risk) + High/Medium/Low 라벨 부여
- **🧾 두 가지 분석 모드**
  - `환경 광고 (Ad)` : ESG·그린워싱 중심 규칙
  - `일반 보고서 (Report)` : 연구/기술/비즈니스 보고서용 증거성 규칙
- **🧠 LLM 심층 분석**
  - 상위 위험 문장 K개만 LLM에 전달
  - 광고 모드: `risk_reasons`, `explanation`, `evidence_needed`, `suggested_queries` 등
  - 보고서 모드: `issues`, `what_to_add(metrics/method/tables_figures/citations)` 등
- **📊 시각화 & XAI**
  - 문장별 위험도 스캐터 플롯
  - 위험 요인 Stacked Bar 차트
  - SHAP Waterfall Plot으로 **점수가 어떻게 만들어졌는지** 설명
- **📤 내보내기**
  - 전체 결과 CSV 다운로드
  - 요약 + LLM 결과를 포함한 PDF 리포트 생성

---

## 📂 프로젝트 구조

```text
VeriAI/
├─ app.py           # Streamlit 메인 앱 (UI + 전체 워크플로우)
├─ rules.py         # 문장 분할, 피처 추출, 위험도 계산 로직
├─ llm.py           # OpenAI LLM 호출 및 JSON 응답 파싱
├─ parsers.py       # URL에서 본문 텍스트 추출
├─ ranker.py        # (선택) Top-K 위험 문장 선별 유틸
├─ report.py        # PDF 리포트 생성 (FPDF 기반)
├─ config/
│  ├─ ad_rules.json       # 환경 광고/그린워싱용 규칙 설정
│  └─ report_rules.json   # 일반 보고서용 규칙 설정
├─ data/            # 샘플 데이터, 테스트용 문서 등 (필요 시)
├─ fonts/           # 한글 폰트 파일 (PDF/그래프용)
├─ requirements.txt
├─ .env             # 환경 변수(로컬용, Git에는 올리지 말 것)
└─ README.md
```

## ⚙️ 설치 (Installation)
### 1️⃣ 저장소 클론

```bash
git clone https://github.com/USERNAME/VeriAI.git
cd VerAI
```

> `USERNME`은 실제 깃허브 계정으로 변경하세요.

### 2️⃣ 가상환경 생성 및 활성화 (권장)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3️⃣ 패키지 설치

```bash
pip install -r requiremnets.txt
```

`requirements.txt`에는 대략 다음과 같은 패키지들이 포함됩니다:
- streamlit, openai, python-dotenv
- pandas, numpy, plotly, matplotlib, shap
- rapidfuzz, trafilatura, fpdf, pillow 등