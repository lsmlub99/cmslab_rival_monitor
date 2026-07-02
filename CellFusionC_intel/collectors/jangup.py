"""
장업신문 수집기 (한국 뷰티 전문지)
- RSS 피드로 최신 기사 수집 후 브랜드명(영문+한국어) 필터링
- 한국 시각에서의 글로벌 K-뷰티 동향 파악에 유용
"""

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

from collectors.base_collector import BaseCollector, RawArticle
from config.brands import BRAND_KO_NAMES
from config.settings import RSS_REQUEST_DELAY

logger = logging.getLogger(__name__)

JANGUP_RSS_URLS = [
    "http://www.jangup.com/rss/allArticle.xml",
    "https://www.jangup.com/rss/allArticle.xml",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _parse_date(entry) -> datetime:
    for field in ("published", "updated", "pubDate"):
        val = getattr(entry, field, None)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass
    return datetime.utcnow()


def _brand_terms(brand: str) -> list[str]:
    """영문명 + 한국어명 모두 반환."""
    terms = [brand.lower()]
    for ko in BRAND_KO_NAMES.get(brand, []):
        terms.append(ko)
    return terms


class JangupCollector(BaseCollector):
    """장업신문 RSS 수집기."""

    collector_type = "jangup"

    def __init__(self):
        self._feed_cache: list | None = None

    def _fetch_feed(self) -> list:
        """RSS 피드 파싱 (requests로 fetch 후 feedparser에 전달, 한 번만 실행)."""
        if self._feed_cache is not None:
            return self._feed_cache

        for url in JANGUP_RSS_URLS:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    logger.debug("장업신문 RSS 로드 완료: %d건", len(feed.entries))
                    self._feed_cache = feed.entries
                    return self._feed_cache
            except Exception as e:
                logger.warning("장업신문 RSS 오류 (%s): %s", url, e)

        logger.warning("장업신문 RSS 수집 실패 — 빈 결과 반환")
        self._feed_cache = []
        return self._feed_cache

    def collect(self, brand: str, country: str) -> list[RawArticle]:
        """브랜드 영문/한국어명이 언급된 장업신문 기사 반환."""
        entries = self._fetch_feed()
        search_terms = _brand_terms(brand)
        articles = []

        for entry in entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            summary = getattr(entry, "summary", "").strip()

            if not title or not link:
                continue

            combined = f"{title} {summary}"
            if not any(term in combined for term in search_terms):
                continue

            articles.append(RawArticle(
                title=title,
                url=link,
                published=_parse_date(entry),
                summary=summary,
                source_name="장업신문",
                language="ko",
                brand_hint=brand,
                country_hint=country,
            ))

        time.sleep(RSS_REQUEST_DELAY)
        logger.info("장업신문 수집: %s → %d건", brand, len(articles))
        return articles

    def reset_cache(self):
        """다음 collect() 호출 시 피드 재fetch (스케줄 실행 간 캐시 초기화용)."""
        self._feed_cache = None
