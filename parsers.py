# parsers.py

import trafilatura

def extract_text_from_url(url: str, max_paragraphs: int = 24) -> str:
    # 1. URL에서 HTML 다운로드
    downloaded = trafilatura.fetch_url(url)

    if downloaded is None:
        return "오류: URL에서 콘텐츠를 다운로드할 수 없습니다."

    # 2. HTML에서 메인 텍스트만 추출 (광고, 메뉴 등 자동 제거)
    # include_comments=False -> 댓글 제외
    # output_format='txt' -> 일반 텍스트로
    main_text = trafilatura.extract(
        downloaded,
        output_format='txt',
        include_comments=False,
        include_tables=False # 테이블 제외 원하시면 추가
    )

    if not main_text:
        return "오류: 해당 URL에서 본문을 추출하지 못했습니다."

    # 3. 분량 조절 (기존 로직과 유사하게)
    lines = main_text.splitlines()
    # 비어있지 않은 라인만 필터링하여 max_paragraphs 만큼만 사용
    meaningful_lines = [line for line in lines if line.strip()]
    return "\n".join(meaningful_lines[:max_paragraphs])