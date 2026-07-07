"""
title_ko 누락 기사 일괄 한국어 번역

대상: language != 'ko' AND title_ko IS NULL
방법: gpt-4o-mini (제목만, 1건당 ~50토큰 → 매우 저렴)

사용:
    python tools/fill_title_ko.py --dry-run    # 대상 목록만 출력
    python tools/fill_title_ko.py              # 실제 번역 + DB 업데이트
    python tools/fill_title_ko.py --limit 50   # 50건씩 나눠서 실행
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import text
from openai import OpenAI, RateLimitError

from storage.models import get_session, DB_SCHEMA
from config.settings import OPENAI_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH = 20   # 한 번에 번역할 기사 수 (gpt-4o-mini 1콜)

_client = None
def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _translate_batch(items: list[dict]) -> dict[int, str]:
    """items: [{id, title, language}] → {id: title_ko}"""
    lines = ["다음 기사 제목들을 한국어로 번역하세요. 각 항목을 [번호] 형식으로 구분해 반환하세요.\n"]
    for i, it in enumerate(items):
        lines.append(f"[{i}] ({it['language']}) {it['title']}")
    lines.append("\n출력 형식 (JSON): {\"0\": \"번역된 제목\", \"1\": \"번역된 제목\", ...}")

    delay = 10
    for attempt in range(4):
        try:
            resp = _get_client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 전문 번역가입니다. 뷰티/화장품 산업 기사 제목을 자연스러운 한국어로 번역합니다. 브랜드명·고유명사는 원문 유지."},
                    {"role": "user",   "content": "\n".join(lines)},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=len(items) * 80,
            )
            import json
            raw = json.loads(resp.choices[0].message.content or "{}")
            return {items[int(k)]["id"]: v for k, v in raw.items() if k.isdigit() and int(k) < len(items)}
        except RateLimitError:
            if attempt == 3:
                raise
            time.sleep(delay); delay *= 2
        except Exception as e:
            logger.error("번역 오류: %s", e)
            return {}
    return {}


def run(dry_run: bool = False, limit: int = 500):
    session = get_session()
    try:
        rows = session.execute(text(f"""
            SELECT id, title, language
            FROM {DB_SCHEMA}.news_articles
            WHERE title_ko IS NULL
              AND language IS NOT NULL
              AND language != 'ko'
            ORDER BY published_date DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        logger.info("번역 대상: %d건", len(rows))
        if dry_run:
            for r in rows[:20]:
                print(f"  [{r[0]}] ({r[2]}) {r[1][:80]}")
            if len(rows) > 20:
                print(f"  ... 외 {len(rows)-20}건")
            return

        items = [{"id": r[0], "title": r[1], "language": r[2]} for r in rows]
        total_updated = 0

        for i in range(0, len(items), BATCH):
            batch = items[i:i+BATCH]
            translations = _translate_batch(batch)
            for art_id, title_ko in translations.items():
                if title_ko:
                    session.execute(text(f"""
                        UPDATE {DB_SCHEMA}.news_articles
                        SET title_ko = :title_ko
                        WHERE id = :id AND title_ko IS NULL
                    """), {"title_ko": title_ko[:400], "id": art_id})
            session.commit()
            total_updated += len(translations)
            logger.info("진행: %d/%d건 완료", min(i+BATCH, len(items)), len(items))
            time.sleep(0.5)

        logger.info("완료: %d건 번역됨", total_updated)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit",   type=int, default=500)
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
