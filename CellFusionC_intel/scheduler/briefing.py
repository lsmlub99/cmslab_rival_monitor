"""
주간 브리핑 자동 생성 (GPT + Supabase DB)

- 최근 7일 수집 데이터를 GPT-4o로 요약
- 브랜드별 주요 활동 + 시장 패턴 인사이트 생성
- Slack으로 전송
"""

import logging
from datetime import datetime, timedelta

from openai import OpenAI

from config.settings import OPENAI_API_KEY, DB_SCHEMA
from storage.models import get_session
from notifications.slack import send_weekly_briefing
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _fetch_week_data(session) -> dict:
    """최근 7일 데이터 집계."""
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()

    rows = session.execute(text(f"""
        SELECT brand, country, activity_type, importance,
               details, product_name, source_url, collected_at
        FROM {DB_SCHEMA}.news_articles
        WHERE collected_at >= :since
        ORDER BY importance DESC, collected_at DESC
    """), {"since": since}).fetchall()

    stats = session.execute(text(f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE importance='high') as high,
            COUNT(DISTINCT brand) as brands,
            COUNT(DISTINCT country) as countries
        FROM {DB_SCHEMA}.news_articles
        WHERE collected_at >= :since
    """), {"since": since}).fetchone()

    return {
        "rows": rows,
        "stats": {
            "total":     stats[0],
            "high":      stats[1],
            "brands":    stats[2],
            "countries": stats[3],
        },
    }


def _build_gpt_prompt(rows) -> str:
    if not rows:
        return "이번 주 수집된 기사가 없습니다."

    lines = ["=== 최근 7일 수집 데이터 ===\n"]
    for r in rows[:60]:  # 최대 60건 (토큰 절약)
        product = f" [{r[4]}]" if r[4] else ""
        lines.append(
            f"[{r[3].upper()}] {r[0]}/{r[1]} - {r[2]}{product}: {r[4][:150] if r[4] else ''}"
        )

    return "\n".join(lines)


def generate_weekly_briefing() -> str:
    """GPT-4o로 주간 브리핑 생성 후 Slack 전송."""
    session = get_session()
    try:
        data = _fetch_week_data(session)
    finally:
        session.close()

    if not data["rows"]:
        logger.info("주간 브리핑: 수집 데이터 없음")
        return ""

    data_prompt = _build_gpt_prompt(data["rows"])

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 K-뷰티 시장 인텔리전스 분석가입니다. "
                        "수집된 경쟁사 활동 데이터를 바탕으로 간결하고 통찰력 있는 주간 브리핑을 작성하세요.\n\n"
                        "형식:\n"
                        "1. 이번 주 핵심 시그널 (2-3가지)\n"
                        "2. 브랜드별 주요 활동 (high importance 위주)\n"
                        "3. 시장 패턴 및 인사이트 (여러 브랜드에서 보이는 공통 트렌드)\n\n"
                        "한국어로 작성, 총 400자 이내로 간결하게."
                    ),
                },
                {"role": "user", "content": data_prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        briefing_text = response.choices[0].message.content
    except Exception as e:
        logger.error("브리핑 GPT 생성 오류: %s", e)
        briefing_text = f"브리핑 생성 오류: {e}"

    logger.info("주간 브리핑 생성 완료 (%d자)", len(briefing_text))
    send_weekly_briefing(briefing_text, data["stats"])
    return briefing_text
