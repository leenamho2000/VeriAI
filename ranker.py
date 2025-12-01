from rapidfuzz import fuzz
import pandas as pd
from typing import Iterable, Tuple

def select_top_k(
    df: pd.DataFrame,
    k: int = 5,
    *,
    min_risk: float = 40.0,                         # ← 최소 위험도(기본: Medium 기준)
    allowed_labels: Tuple[str, ...] = ("High","Medium"),  # ← 포함할 라벨
    similarity_threshold: int = 85
) -> pd.DataFrame:
    # 1) 필터
    work = df.copy()
    if "label" in work.columns:
        work = work[work["label"].isin(allowed_labels)]
    work = work[work["risk"] >= min_risk]

    if work.empty:
        return work  # 비어있으면 그대로 반환(앱에서 안내)

    # 2) 위험도 내림차순 + 유사문장 제거
    work = work.sort_values("risk", ascending=False).reset_index(drop=True)
    selected = []
    for _, row in work.iterrows():
        s = row["sentence"]
        if all(fuzz.ratio(s, prev) < similarity_threshold for prev in selected):
            selected.append(s)
            if len(selected) >= k:
                break

    return work[work["sentence"].isin(selected)].sort_values("risk", ascending=False)
