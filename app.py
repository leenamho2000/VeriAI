# app.py — Final version with all features including SHAP
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re as _re
from rapidfuzz import fuzz
from PIL import Image
from pathlib import Path
import platform
import matplotlib.patches

# --- SHAP/XAI 기능을 위한 라이브러리 ---
import shap
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from rules import analyze_text, W
from llm import analyze_ad, analyze_report
from parsers import extract_text_from_url
from report import export_pdf

st.set_page_config(page_title="VeriAI — 문서 신뢰도/근거 분석 AI", layout="wide")

# ====================== 한글 폰트 설정 (최종 수정 버전) ======================
def _setup_korean_font():
    """시스템에 맞는 한글 폰트를 찾아 matplotlib에 설정합니다. 앱이 중단되지 않도록 예외 처리를 포함합니다."""
    try:
        font_path_to_use = None
        
        # 1. 프로젝트 내 fonts 폴더를 우선적으로 확인합니다.
        local_font_candidates = [
            Path("./fonts/NotoSansKR-Regular.otf"),
            Path("./fonts/NanumGothic.ttf")
        ]
        for font_path in local_font_candidates:
            if font_path.exists():
                font_path_to_use = str(font_path)
                break

        # 2. 로컬 폰트가 없으면 시스템 폰트를 확인합니다.
        if not font_path_to_use:
            system_name = platform.system()
            if system_name == "Windows":
                system_font_path = Path("c:/Windows/Fonts/malgun.ttf")
            elif system_name == "Darwin":  # macOS
                system_font_path = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
            elif system_name == "Linux":
                system_font_path = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
            else:
                system_font_path = None
            
            if system_font_path and system_font_path.exists():
                font_path_to_use = str(system_font_path)

        # 3. 찾은 폰트를 Matplotlib에 설정합니다. (가장 안정적인 방식으로 수정)
        if font_path_to_use:
            fm.fontManager.addfont(font_path_to_use)
            font_name = fm.FontProperties(fname=font_path_to_use).get_name()
            
            # rcParams를 한 번에 업데이트하여 설정 충돌 가능성을 최소화합니다.
            plt.rcParams.update({
                "font.family": font_name,
                "axes.unicode_minus": False,
            })
        else:
            print("Warning: Korean font not found. SHAP plot may display Korean characters as squares.")

    except Exception as e:
        # 폰트 설정 중 어떤 에러가 발생하더라도 앱이 죽지 않도록 방지합니다.
        print(f"Error setting up Korean font: {e}")
        print("Warning: Proceeding without custom font settings due to an error.")
        
_setup_korean_font()

# ====================== STYLE ======================
CUSTOM_CSS = """
<style>
.badge{display:inline-block;padding:4px 8px;border-radius:999px;margin:2px 6px 2px 0;font-size:12px;background:#eef1f5;}
.badge.red{background:#ffe4e4;} .badge.orange{background:#fff0e0;} .badge.green{background:#eaf7ea;}
mark{background:#fff3a6;padding:0 2px;} .small-muted{color:#6b7280;font-size:12px;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ====================== STATE ======================
def _init_state():
    defaults = { "ruleset": "ad", "text_input": "", "url_input": "", "url_error": "", "df": None, "k": 5, "min_risk": 40, "allowed_labels": ("High", "Medium"), "similarity_threshold": 85, "llm_results": None, }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v
_init_state(); st.session_state._re_sub = _re.sub

# ====================== HELPERS ======================
AXES = ["evidence_inverse", "vagueness", "language", "coverage", "temporal", "offset_risk"]
AXES_KO = ["근거성(역)", "모호성", "언어적 위험", "적용범위 위험", "시점/기간 위험", "오프셋 의존도"]
def _as_dict(x): return x if isinstance(x, dict) else {}
def _highlight_sentence(text: str, hits_like) -> str:
    hits = _as_dict(hits_like)
    all_hits = []
    for vals in hits.values():
        if isinstance(vals, list):
            all_hits.extend([v for v in vals if v])

    if not all_hits:
        return str(text)

    uniq = sorted(set(all_hits), key=lambda x: (-len(x), x))
    pat = "|".join(map(_re.escape, uniq))

    if not pat:
        return str(text)
        
    return st.session_state._re_sub(pat, lambda m: f"<mark>{m.group(0)}</mark>", str(text))
def _component_values(row):
    ev_inv=1-(row.get("evidence_score",0)/16);vag=(row.get("vagueness_score",0)/16);lang=(row.get("language_risk",0)/8);cov=(row.get("coverage_penalty",0)/6);tmp=(row.get("temporal_penalty",0)/4);off=float(row.get("offset_flag",0))
    return np.clip(np.array([ev_inv, vag, lang, cov, tmp, off]), 0, 1)
def _weighted_contrib(row):
    base=_component_values(row);weights=np.array([W.get(k,0) for k in AXES]);parts=100*base*weights;total=parts.sum();risk=float(row.get("risk") or 0)
    if total > 0 and risk > 0: parts=parts*(risk/total)
    return parts

# SHAP을 위한 Helper 함수: 이미 추출된 특징(dict)으로 점수를 계산
def score_sentence_from_features(features: dict) -> float:
    f = features
    risk = 100 * (
        W.get("evidence_inverse", 0.30) * (1 - f.get("evidence_score", 0) / 16)
        + W.get("vagueness", 0.22) * (f.get("vagueness_score", 0) / 16)
        + W.get("language", 0.12) * (f.get("language_risk", 0) / 8)
        + W.get("coverage", 0.10) * (f.get("coverage_penalty", 0) / 6)
        + W.get("temporal", 0.16) * (f.get("temporal_penalty", 0) / 4)
        + W.get("offset_risk", 0.10) * f.get("offset_flag", 0)
    )
    return max(0, min(100, risk))

# ====================== UI LAYOUT ======================
def on_click_fetch_url():
    url = (st.session_state.get("url_input") or "").strip()
    if not url: st.session_state["url_error"] = "URL을 입력하세요."; return
    try:
        with st.spinner("URL에서 본문을 불러오는 중…"): fetched = extract_text_from_url(url, max_paragraphs=16)
        fetched = fetched.replace("\uFFFD", " "); st.session_state["text_input"] = fetched; st.session_state["url_error"] = ""
    except Exception as e: st.session_state["url_error"] = f"URL 읽기 실패: {e}"

st.title("🧠 VeriAI — 문서 신뢰·근거 자동 분석"); st.caption("문장 단위 규칙 점수화 → 상위 위험문장만 LLM으로 근거/보완 제안 (ESG/광고/일반 보고서 전부 지원)")

with st.sidebar:
    st.header("설정")
    mode = st.radio(
        "분석 모드",
        ["환경 광고 (Ad)", "일반 보고서 (Report)"],
        index=0 if st.session_state.ruleset == "ad" else 1,
        help="분석할 문서의 종류를 선택합니다. '환경 광고'는 그린워싱 탐지에, '일반 보고서'는 비즈니스/기술 보고서의 근거성 점검에 최적화된 규칙을 적용합니다."
    )
    st.session_state.ruleset = "ad" if mode.startswith("환경") else "report"
    st.session_state.k = st.slider(
        "Top-K (LLM 대상)", 1, 10, st.session_state.k,
        help="규칙 기반으로 분석된 문장 중, 위험도가 가장 높은 K개의 문장을 선정하여 LLM(AI)에게 심층 분석을 요청합니다. LLM은 왜 위험한지, 어떤 근거가 보강되어야 하는지 등을 제안합니다."
    )
    st.session_state.min_risk = st.slider(
        "최소 위험도", 0, 100, st.session_state.min_risk, step=5,
        help="LLM 심층 분석 대상으로 고려할 문장의 최소 위험도 점수(0-100)를 설정합니다. 이 점수 미만인 문장은 LLM 분석에서 제외됩니다."
    )
    st.session_state.allowed_labels = tuple(st.multiselect(
        "포함 라벨", ["High", "Medium", "Low"],
        default=list(st.session_state.allowed_labels),
        help="LLM 심층 분석 대상으로 고려할 위험도 라벨(High, Medium, Low)을 선택합니다. 선택된 라벨에 해당하는 문장만 분석 대상이 됩니다."
    ))
    st.session_state.similarity_threshold = st.slider(
        "유사문장 제거 민감도", 70, 100, st.session_state.similarity_threshold, step=1,
        help="LLM 분석 대상 선정 시, 내용이 유사한 문장들이 중복으로 뽑히지 않도록 제거합니다. 민감도가 높을수록 약간의 차이만 있어도 다른 문장으로 간주합니다."
    )
    st.markdown("---"); st.markdown("**LLM 사용 안내**\n- `OPENAI_API_KEY` 필요\n- 광고: ‘왜 위험인지 + 검증 쿼리’\n- 보고서: ‘무엇을 추가할지(지표/방법/인용)’")

st.subheader("1) 텍스트/URL 입력"); col1, col2 = st.columns([2,1])
with col1: st.text_area("문장 단위로 자동 분할/정규화합니다.", key="text_input", height=220, placeholder="분석할 텍스트를 붙여넣으세요.")
with col2:
    st.text_input("또는 URL 입력", key="url_input", placeholder="https://example.com/article")
    st.button("🌐 URL 본문 불러오기", use_container_width=True, on_click=on_click_fetch_url)
    if st.session_state.get("url_error"): st.error(st.session_state["url_error"])
run = st.button("🔎 분석하기", type="primary")

@st.cache_data(show_spinner=False)
def _analyze(text: str, ruleset: str): return pd.DataFrame(analyze_text(text, ruleset=ruleset))

if run:
    txt = (st.session_state.text_input or "").strip()
    if not txt: st.warning("텍스트를 입력하거나 URL을 불러오세요.")
    else:
        df_raw = _analyze(txt, st.session_state.ruleset); df_raw.insert(0, '번호', range(1, len(df_raw) + 1))
        st.session_state.df = df_raw; st.session_state.llm_results = None

df = st.session_state.df
# ====================== OUTPUT ======================
if isinstance(df, pd.DataFrame) and not df.empty:
    avg_risk = round(float(df["risk"].mean()), 1); high_cnt = int((df.get("label") == "High").sum())
    c1,c2,c3,c4 = st.columns(4); c1.metric("평균 위험도",f"{avg_risk}"); c2.metric("High 문장 수",f"{high_cnt}"); c3.metric("총 문장 수",f"{len(df)}"); c4.metric("분석 모드", "환경 광고" if st.session_state.ruleset == "ad" else "일반 보고서")
    st.subheader("2) 결과 탐색"); tab1, tab2, tab3, tab4 = st.tabs(["개요(표)", "문장별 탐색", "시각화", "내보내기"])

    with tab1:
        show = df.copy().sort_values("risk", ascending=False); q = st.text_input("문장 검색(키워드)", "")
        if q: show = show[show["sentence"].astype(str).str.contains(q, case=False, na=False)]
        
        rename_map = {
            "sentence": "문장", "risk": "위험도", "label": "등급",
            "evidence_score": "근거 점수", "vagueness_score": "모호성 점수"
        }
        show.rename(columns=rename_map, inplace=True)
        
        cols = ["번호", "문장", "위험도", "등급", "근거 점수", "모호성 점수"]
        cols = [c for c in cols if c in show.columns]
        
        cfg = {"위험도": st.column_config.ProgressColumn("위험도", min_value=0, max_value=100, format="%.1f")}
        
        st.dataframe(show[cols], use_container_width=True, column_config=cfg)
        st.caption("※ 근거 점수: 문장에 수치, 연도, 출처, 외부 검증 등 구체적인 근거가 많을수록 높은 점수를 받습니다.")

    with tab2:
        options_map = {row['번호']: f"{row['번호']}. {str(row['sentence'])[:70]}..." for _, row in df.iterrows()}
        selected_num = st.selectbox("문장 선택", options=df['번호'].tolist(), format_func=lambda num: options_map[num])
        row = df[df['번호'] == selected_num].iloc[0].to_dict()

        st.markdown("**원문**"); st.markdown(_highlight_sentence(row.get("sentence",""), row.get("hits")), unsafe_allow_html=True)
        a, b, c = st.columns(3); a.metric("위험도", f"{row.get('risk',0):.1f}"); b.metric("등급", str(row.get('label',''))); c.metric("근거 점수", f"{int(row.get('evidence_score',0))}/16")
        with st.expander("🔎 규칙 매칭 상세 (히트 단어 보기)"):
            hits = _as_dict(row.get("hits"))
            def chips(items, tone=""):
                if not items: return
                tone_cls = {"red":"red", "orange":"orange", "green":"green"}.get(tone, "")
                st.markdown(" ".join([f"<span class='badge {tone_cls}'>{st.session_state._re_sub(r'\\s+', '&nbsp;', str(it))}</span>" for it in items]), unsafe_allow_html=True)
            st.write("**모호어**"); chips(hits.get("vague", []), "orange"); st.write("**과장표현**"); chips(hits.get("overclaim", []), "red"); st.write("**미래시제/계획**"); chips(hits.get("future", [])); st.write("**범위-위험**"); chips(hits.get("coverage_risky", []), "red"); st.write("**범위-완화(명확화)**"); chips(hits.get("coverage_clarifier", []), "green"); st.write("**표준/방법**"); chips(hits.get("standards_method", []), "green"); st.write("**제3자/검증**"); chips(hits.get("third_party", []), "green"); st.write("**오프셋/크레딧**"); chips(hits.get("offset_terms", []), "orange")

        st.markdown("#### AI 판단 근거 분석 (SHAP Waterfall Plot)")
        with st.spinner("SHAP 분석을 실행 중입니다..."):
            shap_features = [
                'evidence_score', 'vagueness_score', 'coverage_penalty', 
                'temporal_penalty', 'language_risk', 'offset_flag'
            ]
            feature_name_map_ko = {
                'evidence_score': '근거 점수', 'vagueness_score': '모호성 점수',
                'coverage_penalty': '적용범위 위험', 'temporal_penalty': '시점/기간 위험',
                'language_risk': '언어적 위험', 'offset_flag': '오프셋 의존'
            }
            shap_features_ko = [feature_name_map_ko[f] for f in shap_features]

            instance_values = pd.Series(row)[shap_features].values.astype(float)
            background_data = df[shap_features].sample(min(50, len(df)))

            explainer = shap.KernelExplainer(
                lambda x: pd.DataFrame(x, columns=shap_features).apply(
                    lambda s: score_sentence_from_features(dict(s)), axis=1
                ).values, 
                background_data
            )
            shap_values = explainer.shap_values(instance_values)
            
            fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
            
            shap_exp = shap.Explanation(
                values=shap_values, base_values=explainer.expected_value,
                data=instance_values, feature_names=shap_features_ko
            )
            
            shap.plots.waterfall(shap_exp, max_display=10, show=False)

            # --- 그래프 색상 및 부호 Failsafe 로직 ---
            # SHAP 값에 따라 막대 색상을 강제로 재설정
            shap_values_in_plot_order = shap_exp.values[np.argsort(np.abs(shap_exp.values))][-10:]
            bar_artists = [p for p in ax.patches if isinstance(p, matplotlib.patches.Rectangle) and p.get_height() < 1.0]
            bar_artists.sort(key=lambda p: p.get_y())
            
            if len(bar_artists) == len(shap_values_in_plot_order):
                for artist, value in zip(bar_artists, shap_values_in_plot_order):
                    artist.set_facecolor(shap.plots.colors.red_rgb if value > 0 else shap.plots.colors.blue_rgb)

            # 막대 위의 숫자 레이블에서 부호(+/-)를 모두 제거
            for text_obj in ax.texts:
                label = text_obj.get_text()
                cleaned_label = label.lstrip('+−-')
                if label != cleaned_label:
                    try:
                        float(cleaned_label)
                        text_obj.set_text(cleaned_label)
                    except ValueError:
                        pass

            xmin, xmax = ax.get_xlim()
            padding = (xmax - xmin) * 0.1
            ax.set_xlim(xmin - padding, xmax + padding)
            plt.tight_layout(pad=1.5)
            st.pyplot(fig, clear_figure=True)

        with st.expander("💡 차트 해석 방법 (고정 안내문)"):
            st.markdown("""
            이 차트는 **AI가 계산한 위험도 점수가 어떻게 만들어졌는지** 각 요인별로 상세히 보여줍니다.

            - **`E[f(X)]` (회색 기준선)**: 이 문서에 있는 문장들의 평균적인 위험도 점수입니다. 모든 분석은 이 평균 점수에서 시작합니다.
            - **`f(x)` (최종 예측 점수)**: 현재 선택된 문장의 최종 위험도 점수입니다.
            - <span style='color:red;'>**빨간색 막대 (점수 상승 요인) ↑**</span>: 위험도 점수를 **높이는** 요인들입니다.
            - <span style='color:blue;'>**파란색 막대 (점수 하락 요인) ↓**</span>: 위험도 점수를 **낮추는** 요인들입니다.
            - **막대의 길이**: 각 요인이 점수에 미친 영향력의 크기를 나타냅니다.
            """, unsafe_allow_html=True)
            
    with tab3:
        parts_avg=np.mean([_weighted_contrib(r) for _,r in df.iterrows()],axis=0); contrib_sorted=sorted(zip(AXES_KO,parts_avg),key=lambda x:-x[1]); top_two_risks=[item[0] for item in contrib_sorted[:2]]; st.info(f"**문서 전체의 주요 위험 요인:** {top_two_risks[0]}, {top_two_risks[1]}")
        st.markdown("#### 문장별 위험도 분포 (Scatter Plot)"); scatter_df=df.copy(); scatter_df['요약']=scatter_df['sentence'].str.slice(0,80)+'...'; color_map={'High':'red','Medium':'orange','Low':'skyblue'}; fig_scatter=px.scatter(scatter_df,x='번호',y='risk',color='label',color_discrete_map=color_map,hover_data=['요약'],title='문장 위치별 위험도 점수',labels={'번호':'문장 번호','risk':'위험도 점수'}); st.plotly_chart(fig_scatter,use_container_width=True)
        st.markdown("#### 문장별 위험 요소 기여도 (Stacked Bar Chart)"); contrib_data=pd.DataFrame([_weighted_contrib(row) for _,row in df.iterrows()],columns=AXES_KO); contrib_data['번호']=contrib_data.index+1; contrib_df_melted=contrib_data.melt(id_vars='번호',var_name='위험 요소',value_name='기여도'); fig_stacked_bar=px.bar(contrib_df_melted,x='번호',y='기여도',color='위험 요소',title='각 문장의 위험도 점수 구성 요소',labels={'번호':'문장 번호','기여도':'위험도 기여도'}); st.plotly_chart(fig_stacked_bar,use_container_width=True)

    with tab4:
        work = df.copy()
        if "label" in work.columns:
            work = work[work["label"].isin(st.session_state.allowed_labels)]
        work = work[work["risk"] >= st.session_state.min_risk].sort_values("risk", ascending=False).reset_index(drop=True)

        if work.empty:
            st.warning("설정 기준에 해당하는 문장이 없습니다.")
        else:
            selected = []
            for _, r in work.iterrows():
                s = r["sentence"]
                if all(fuzz.ratio(s, prev) < st.session_state.similarity_threshold for prev in selected):
                    selected.append(s)
                    if len(selected) >= st.session_state.k:
                        break
            
            topk = work[work["sentence"].isin(selected)].copy().sort_values("risk", ascending=False)
            
            view_cols = ["번호", "sentence", "risk", "label"]
            view = df[df['sentence'].isin(topk['sentence'].tolist())][view_cols].sort_values('risk', ascending=False)

            view_display = view.copy()
            view_display.rename(columns={"sentence": "문장", "risk": "위험도", "label": "등급"}, inplace=True)
            st.dataframe(view_display, use_container_width=True)
            st.info("위 목록만 LLM 후처리 대상으로 사용합니다.")

            colx, coly = st.columns(2)
            items_list = [{"id": int(r.번호), "text": r.sentence, "risk": float(r.risk), "label": r.label} for r in view.itertuples(index=False)]
            hashable_items = tuple(tuple(sorted(d.items())) for d in items_list)

            if st.session_state.ruleset == "ad":
                if colx.button("🔎 LLM 근거·위험 분석 실행 (광고)", use_container_width=True):
                    try:
                        st.session_state.llm_results = analyze_ad(hashable_items)
                        st.success("LLM 분석 완료")
                    except Exception as e:
                        st.error(f"LLM 분석 실패: {e}")
            else:
                if colx.button("🧩 LLM 증빙 보완 제안 실행 (보고서)", use_container_width=True):
                    try:
                        st.session_state.llm_results = analyze_report(hashable_items)
                        st.success("LLM 분석 완료")
                    except Exception as e:
                        st.error(f"LLM 분석 실패: {e}")

            if isinstance(st.session_state.llm_results, list) and st.session_state.llm_results:
                st.markdown("#### LLM 결과 미리보기")
                id2sent = {int(r["id"]): r["text"] for r in items_list}
                disp_data = []
                for res in st.session_state.llm_results:
                    res_id = res.get("id")
                    disp_item = {"번호": res_id, "문장": id2sent.get(res_id, "")}
                    if st.session_state.ruleset == "ad":
                        disp_item["위험 사유"] = ", ".join(res.get("risk_reasons", []))
                        disp_item["상세 설명"] = res.get("explanation", "")
                    else:
                        disp_item["주요 이슈"] = ", ".join(res.get("issues", []))
                    disp_data.append(disp_item)
                st.dataframe(pd.DataFrame(disp_data), use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 전체 결과 CSV", csv, "veriai_results.csv", "text/csv", use_container_width=True)

            if coly.button("🖨️ PDF 리포트 생성", use_container_width=True):
                with st.spinner("PDF 리포트를 생성 중입니다..."):
                    try:
                        summary = {
                            "분석 모드": "환경 광고" if st.session_state.ruleset=="ad" else "일반 보고서",
                            "평균 위험도": avg_risk,
                            "'High' 등급 문장 수": high_cnt,
                            "총 문장 수": len(df)
                        }
                        outputs = []
                        if isinstance(st.session_state.llm_results, list):
                            id2sent = {int(r.번호): r.sentence for r in view.itertuples(index=False)}
                            for obj in st.session_state.llm_results:
                                outputs.append({ "sentence": id2sent.get(int(obj.get("id")), ""), "result": obj })
                        
                        path = export_pdf(summary, df.to_dict("records"), outputs, path="veriai_report.pdf", visuals=None)
                        
                        st.success("PDF 생성 완료!")
                        with open(path, "rb") as f:
                            st.download_button("⬇️ PDF 다운로드", f, file_name="veriai_report.pdf", mime="application/pdf")
                    except Exception as e:
                        st.error(f"PDF 생성 실패: {e}", icon="🚨")

