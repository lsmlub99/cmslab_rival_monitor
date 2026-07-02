from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, Float, Index, String, Text, TIMESTAMP, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Session

from config.settings import DATABASE_URL, DB_SCHEMA


class Base(DeclarativeBase):
    pass


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url_hash = Column(String(64), unique=True, nullable=False)

    # PRD 8개 핵심 필드
    published_date = Column(TIMESTAMP(timezone=True), nullable=False)
    brand = Column(String(100), nullable=False)
    country = Column(String(10), nullable=False)
    activity_type = Column(String(50), nullable=False)
    details = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    importance = Column(String(10), nullable=False)
    note = Column(Text)

    # 보조 필드
    title = Column(Text, nullable=False)
    source_name = Column(String(200))
    language = Column(String(10))

    # 제품 정보
    product_name = Column(String(200))   # GPT가 추출한 언급 제품명

    # 기사 본문 (원문 + 한국어 번역)
    article_body = Column(Text)          # URL fetch로 가져온 원문 본문 (최대 2000자)
    title_ko = Column(String(400))       # GPT가 번역한 제목 한국어
    article_body_ko = Column(Text)       # GPT가 번역·요약한 본문 한국어 (최대 500자)

    # 분류 메타데이터
    classification_confidence = Column(Float)
    classifier_model = Column(String(50))

    # 시스템 필드
    collected_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    collector_type = Column(String(50))

    __table_args__ = (
        Index("idx_news_brand", "brand"),
        Index("idx_news_country", "country"),
        Index("idx_news_activity", "activity_type"),
        Index("idx_news_date", "published_date"),
        Index("idx_news_brand_country", "brand", "country"),
        {"schema": DB_SCHEMA},
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    collector_type = Column(String(50))
    brand = Column(String(100))
    country = Column(String(10))
    articles_found = Column(BigInteger, default=0)
    articles_new = Column(BigInteger, default=0)
    articles_duped = Column(BigInteger, default=0)
    error_message = Column(Text)
    duration_secs = Column(Float)


class DedupCandidate(Base):
    __tablename__ = "dedup_candidates"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    article_id_1 = Column(BigInteger, nullable=False)
    article_id_2 = Column(BigInteger, nullable=False)
    similarity = Column(Float)
    reviewed = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)


def get_engine():
    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"},
    )


def create_tables():
    from sqlalchemy import text
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
        conn.commit()
    Base.metadata.create_all(engine)
    print(f"DB 테이블 생성 완료 (schema: {DB_SCHEMA})")
    return engine


def migrate_tables():
    """기존 테이블에 신규 컬럼 추가 (idempotent — 이미 있으면 무시)."""
    from sqlalchemy import text
    engine = get_engine()
    migrations = [
        f"ALTER TABLE {DB_SCHEMA}.news_articles ADD COLUMN IF NOT EXISTS product_name VARCHAR(200)",
        f"ALTER TABLE {DB_SCHEMA}.news_articles ADD COLUMN IF NOT EXISTS article_body TEXT",
        f"ALTER TABLE {DB_SCHEMA}.news_articles ADD COLUMN IF NOT EXISTS title_ko VARCHAR(400)",
        f"ALTER TABLE {DB_SCHEMA}.news_articles ADD COLUMN IF NOT EXISTS article_body_ko TEXT",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"마이그레이션 완료: {sql.split('ADD')[1].strip()}")
            except Exception as e:
                print(f"마이그레이션 스킵 ({e})")
    return engine


def get_session(engine=None) -> Session:
    from sqlalchemy.orm import sessionmaker
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
