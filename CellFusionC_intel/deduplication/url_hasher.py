"""
2단계 중복 제거

1단계 (DB INSERT 전): URL SHA-256 해시 → article_exists() 로 즉시 차단
2단계 (주기적 정리): 제목 유사도 SequenceMatcher ≥ 0.85 → 오래된 기사 soft-delete
"""

import hashlib
import logging
from difflib import SequenceMatcher

from config.settings import TITLE_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def url_hash(url: str) -> str:
    """URL을 SHA-256 해시(hex 64자)로 변환. DB UNIQUE 키로 사용."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def title_similarity(a: str, b: str) -> float:
    """두 제목 간 SequenceMatcher 유사도 0.0~1.0."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_near_duplicates(
    new_title: str,
    existing: list[tuple[int, str]],
    threshold: float = TITLE_SIMILARITY_THRESHOLD,
) -> list[tuple[int, float]]:
    """
    새 기사 제목과 기존 제목 목록을 비교하여 유사 기사 목록 반환.

    Args:
        new_title: 새로 수집된 기사 제목
        existing: [(article_id, title), ...] — get_recent_titles() 결과
        threshold: 유사도 임계값 (기본 0.85)

    Returns:
        [(article_id, similarity), ...] — 임계값 이상인 기존 기사 목록
    """
    matches: list[tuple[int, float]] = []
    for article_id, existing_title in existing:
        score = title_similarity(new_title, existing_title)
        if score >= threshold:
            matches.append((article_id, score))
    return matches


def is_near_duplicate(
    new_title: str,
    existing: list[tuple[int, str]],
    threshold: float = TITLE_SIMILARITY_THRESHOLD,
) -> bool:
    """유사 기사가 하나라도 있으면 True."""
    return bool(find_near_duplicates(new_title, existing, threshold))


def deduplicate_batch(
    articles: list,
    existing: list[tuple[int, str]],
    threshold: float = TITLE_SIMILARITY_THRESHOLD,
) -> list:
    """
    수집된 기사 배치에서 기존 기사와 유사한 것을 제거.

    Args:
        articles: RawArticle 목록
        existing: DB에서 가져온 최근 기사 (id, title) 목록
        threshold: 유사도 임계값

    Returns:
        중복이 제거된 RawArticle 목록
    """
    # 배치 내 자체 중복도 제거 (URL 기준 먼저, 제목 유사도 순)
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    result = []

    for article in articles:
        normalized_url = article.url.split("?")[0].rstrip("/")

        if normalized_url in seen_urls:
            logger.debug("배치 내 URL 중복 제거: %s", article.title[:60])
            continue

        # 배치 내 제목 유사도 체크
        batch_duplicate = False
        for prev_title in seen_titles:
            if title_similarity(article.title, prev_title) >= threshold:
                logger.debug("배치 내 제목 유사 제거: %s", article.title[:60])
                batch_duplicate = True
                break

        if batch_duplicate:
            continue

        # DB 기존 기사 대비 유사도 체크
        if is_near_duplicate(article.title, existing, threshold):
            logger.debug("DB 유사 기사 존재, 건너뜀: %s", article.title[:60])
            continue

        seen_urls.add(normalized_url)
        seen_titles.append(article.title)
        result.append(article)

    return result
