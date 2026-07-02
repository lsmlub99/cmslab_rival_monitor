"""
기사 본문 수집기 — URL에서 실제 기사 본문 텍스트 추출

- Google News redirect URL은 원문 접근 불가 → 스킵
- 타임아웃 8초, 최대 2000자 저장
- 실패 시 빈 문자열 반환 (파이프라인 중단 없음)
"""

import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
}

MAX_BODY_CHARS = 2000
FETCH_TIMEOUT = 8

# 기사 본문 영역 CSS 셀렉터 (우선순위 순)
ARTICLE_SELECTORS = [
    "article",
    '[role="main"]',
    "main",
    ".article-body",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".story-body",
    ".content-body",
    "#article-body",
    "#content",
]

# 제거 대상 태그
NOISE_TAGS = ["script", "style", "nav", "header", "footer",
              "aside", "iframe", "noscript", "figure", "figcaption"]


def fetch_body(url: str) -> str:
    """
    URL에서 기사 본문 텍스트 추출.
    실패하거나 Google News URL이면 빈 문자열 반환.
    """
    if not url or "news.google.com" in url:
        return ""

    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT,
                            allow_redirects=True)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(NOISE_TAGS):
            tag.decompose()

        # 기사 영역 우선 추출
        for selector in ARTICLE_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 150:
                    return text[:MAX_BODY_CHARS]

        # fallback: body 전체
        body = soup.find("body")
        if body:
            return body.get_text(separator=" ", strip=True)[:MAX_BODY_CHARS]

        return ""

    except Exception as e:
        logger.debug("본문 수집 실패 (%s): %s", url[:70], e)
        return ""
