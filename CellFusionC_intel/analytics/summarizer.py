"""
브랜드 전략 인사이트 요약 — Claude API (Haiku 사용, 리포트당 ~$0.02)
"""

import anthropic


def generate_brand_strategy_summary(brand: str, articles: list) -> str:
    """HIGH+MEDIUM 기사 목록 → 1-2줄 전략 요약 (한국어).

    Args:
        brand: 브랜드명
        articles: [{imp, act, title_ko, date}, ...] 최대 5건

    Returns:
        1-2줄 전략 요약 문자열
    """
    if not articles:
        return f"{brand}의 최근 주목할 만한 활동이 없습니다."

    article_lines = "\n".join(
        f"- [{a['imp'].upper()}] {a['title_ko']} ({a['act']}, {a['date']})"
        for a in articles
        if a.get("title_ko")
    )
    if not article_lines:
        return f"{brand}의 기사 요약 정보가 없습니다."

    prompt = f"""다음은 K-뷰티 브랜드 {brand}의 최근 주요 경쟁 인텔리전스 기사입니다:

{article_lines}

이 데이터를 바탕으로 {brand}의 현재 전략 방향을 2문장 이내로 한국어로 요약해 주세요.
- 첫 문장: 주요 전략 접근법 (어떤 채널/방식으로 무엇을 하고 있는지)
- 두 번째 문장: 주요 타겟 시장·고객층
반드시 기사에 나온 구체적 사실(브랜드명·캠페인·채널·수치)을 기반으로 작성하세요. 추측하지 마세요."""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
