from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from storage.models import NewsArticle, CollectionRun, DedupCandidate


def article_exists(session: Session, url_hash: str) -> bool:
    return session.query(NewsArticle).filter_by(url_hash=url_hash).first() is not None


def save_article(session: Session, article: NewsArticle) -> NewsArticle:
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


def get_recent_titles(session: Session, days: int = 3) -> list[tuple[int, str]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(NewsArticle.id, NewsArticle.title)
        .filter(NewsArticle.published_date >= cutoff)
        .all()
    )
    return [(r.id, r.title) for r in rows]


def save_dedup_candidate(session: Session, id1: int, id2: int, similarity: float):
    cand = DedupCandidate(article_id_1=id1, article_id_2=id2, similarity=similarity)
    session.add(cand)
    session.commit()


def save_collection_run(session: Session, run: CollectionRun) -> CollectionRun:
    session.add(run)
    session.commit()
    return run


def query_articles(
    session: Session,
    brand: Optional[str] = None,
    country: Optional[str] = None,
    activity_type: Optional[str] = None,
    importance: Optional[str] = None,
    days: Optional[int] = None,
    limit: int = 20,
) -> list[NewsArticle]:
    q = session.query(NewsArticle)
    if brand:
        q = q.filter(NewsArticle.brand.ilike(f"%{brand}%"))
    if country:
        q = q.filter(NewsArticle.country == country.upper())
    if activity_type:
        q = q.filter(NewsArticle.activity_type == activity_type)
    if importance:
        q = q.filter(NewsArticle.importance == importance)
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = q.filter(NewsArticle.published_date >= cutoff)
    return q.order_by(NewsArticle.published_date.desc()).limit(limit).all()
