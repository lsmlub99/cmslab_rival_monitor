"""
PRTIMES Japan 수집기
- 일본 최대 PR 보도자료 플랫폼 (https://prtimes.jp)
- 브랜드명으로 검색 → 일본 진출 PR 보도자료 수집
- 국가 JP 전용 (PR 보도자료 특성상 JP 관련 내용)
"""

import logging
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector, RawArticle
from config.settings import RSS_REQUEST_DELAY

logger = logging.getLogger(__name__)

PRTIMES_SEARCH_URL = "https://prtimes.jp/main/html/searchrlp/key/{query}"
PRTIMES_RSS_URL = "https://prtimes.jp/rss20.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}


def _safe_text(tag) -> str:
    return tag.get_text(strip=True) if tag else ""


class PRTimesCollector(BaseCollector):
    """PRTIMES Japan 검색 기반 수집기."""

    collector_type = "prtimes"

    def collect(self, brand: str, country: str) -> list[RawArticle]:
        """PRTIMES에서 브랜드 관련 일본어 PR 보도자료 수집."""
        if country.upper() != "JP":
            return []

        from urllib.parse import quote
        url = PRTIMES_SEARCH_URL.format(query=quote(brand))

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 404:
                logger.debug("PRTIMES 검색 미지원 — 건너뜀 (%s)", brand)
                return []
            resp.raise_for_status()
        except Exception as e:
            logger.warning("PRTIMES 요청 오류 (%s): %s", brand, e)
            return []

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = []

            # PRTIMES 검색 결과 파싱 (각 기사 카드)
            for item in soup.select("article.list-article, div.release-list-item, li.release"):
                title_tag = item.select_one("h2, h3, .title, a.corp-title")
                link_tag = item.select_one("a[href]")
                summary_tag = item.select_one("p, .summary, .description")
                date_tag = item.select_one("time, .date")

                title = _safe_text(title_tag)
                link = link_tag["href"] if link_tag and link_tag.get("href") else ""
                summary = _safe_text(summary_tag)

                if not title or not link:
                    continue

                # 상대경로 → 절대 URL
                if link.startswith("/"):
                    link = f"https://prtimes.jp{link}"

                # 날짜 파싱
                pub_date = datetime.utcnow()
                if date_tag:
                    dt_str = date_tag.get("datetime") or _safe_text(date_tag)
                    try:
                        pub_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                articles.append(RawArticle(
                    title=title,
                    url=link,
                    published=pub_date,
                    summary=summary,
                    source_name="PRTIMES",
                    language="ja",
                    brand_hint=brand,
                    country_hint="JP",
                ))

        except Exception as e:
            logger.warning("PRTIMES 파싱 오류 (%s): %s", brand, e)
            articles = []

        time.sleep(RSS_REQUEST_DELAY)
        logger.info("PRTIMES 수집: %s/JP → %d건", brand, len(articles))
        return articles
