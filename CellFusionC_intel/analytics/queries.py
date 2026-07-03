"""
분석 쿼리 함수 모음 — 대시보드 / CLI 드릴다운용

모든 함수는 SQLAlchemy Session을 받아 순수 Python dict/list를 반환.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import DB_SCHEMA


def _cutoff_iso(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).isoformat()


def get_collection_stats(session: Session, days: int = 30) -> dict:
    """KPI 요약 통계 반환."""
    cutoff = _cutoff_iso(days)
    row = session.execute(
        text(f"""
            SELECT
                COUNT(*)                                              AS total,
                COUNT(*) FILTER (WHERE importance = 'high')          AS high,
                COUNT(*) FILTER (WHERE importance = 'medium')        AS medium,
                COUNT(*) FILTER (WHERE importance = 'low')           AS low,
                COUNT(DISTINCT brand)                                AS brands_active,
                COUNT(DISTINCT country)                              AS countries_active
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
        """),
        {"cutoff": cutoff},
    ).fetchone()

    return {
        "total":            row[0] or 0,
        "high":             row[1] or 0,
        "medium":           row[2] or 0,
        "low":              row[3] or 0,
        "brands_active":    row[4] or 0,
        "countries_active": row[5] or 0,
        "days":             days,
        "generated_at":     datetime.utcnow().isoformat(),
    }


def get_high_articles(
    session: Session,
    days: int = 30,
    brand: "str | None" = None,
    country: "str | None" = None,
) -> list:
    """HIGH importance 기사 전체 목록 반환 (드릴다운용)."""
    cutoff = _cutoff_iso(days)

    where_extras = ""
    params: dict = {"cutoff": cutoff}
    if brand:
        where_extras += " AND LOWER(brand) = :brand"
        params["brand"] = brand.lower()
    if country:
        where_extras += " AND country = :country"
        params["country"] = country.upper()

    rows = session.execute(
        text(f"""
            SELECT id, title, brand, country, activity_type,
                   details, product_name, source_url, source_name,
                   published_date, note, classification_confidence,
                   title_ko, article_body, article_body_ko, importance
            FROM {DB_SCHEMA}.news_articles
            WHERE importance IN ('high', 'medium')
              AND published_date >= :cutoff
              {where_extras}
            ORDER BY
                CASE importance WHEN 'high' THEN 0 ELSE 1 END,
                published_date DESC
        """),
        params,
    ).fetchall()

    return [
        {
            "id":               r[0],
            "title":            r[1] or "",
            "brand":            r[2] or "",
            "country":          r[3] or "",
            "activity_type":    r[4] or "",
            "details":          r[5] or "",
            "product_name":     r[6],
            "source_url":       r[7] or "",
            "source_name":      r[8] or "",
            "published_date":   r[9].isoformat() if r[9] else "",
            "note":             r[10],
            "confidence":       float(r[11]) if r[11] is not None else None,
            "title_ko":         r[12],
            "article_body":     r[13],
            "article_body_ko":  r[14],
            "importance":       r[15] or "high",
        }
        for r in rows
    ]


def get_brand_country_matrix(
    session: Session, days: int = 30, top_n: int = 12
) -> dict:
    """brand × country 크로스탭 카운트 매트릭스 반환."""
    cutoff = _cutoff_iso(days)

    rows = session.execute(
        text(f"""
            SELECT brand, country, COUNT(*) AS cnt
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY brand, country
            ORDER BY brand, country
        """),
        {"cutoff": cutoff},
    ).fetchall()

    brand_totals: dict = defaultdict(int)
    country_totals: dict = defaultdict(int)
    raw_matrix: dict = defaultdict(lambda: defaultdict(int))

    for brand_val, country_val, cnt in rows:
        raw_matrix[brand_val][country_val] += cnt
        brand_totals[brand_val] += cnt
        country_totals[country_val] += cnt

    top_brands = sorted(brand_totals, key=lambda b: brand_totals[b], reverse=True)[:top_n]
    top_countries = sorted(country_totals, key=lambda c: country_totals[c], reverse=True)

    return {
        "brands":         top_brands,
        "countries":      top_countries,
        "matrix":         {b: dict(raw_matrix[b]) for b in top_brands},
        "brand_totals":   dict(brand_totals),
        "country_totals": dict(country_totals),
        "grand_total":    sum(brand_totals.values()),
    }


def get_weekly_trend(session: Session, weeks: int = 12) -> dict:
    """주별 importance 카운트 반환 (시계열 트렌드)."""
    cutoff = (datetime.utcnow() - timedelta(weeks=weeks)).isoformat()

    rows = session.execute(
        text(f"""
            SELECT
                TO_CHAR(DATE_TRUNC('week', published_date AT TIME ZONE 'UTC'), 'IYYY"-W"IW') AS week_label,
                importance,
                COUNT(*) AS cnt
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY week_label, importance
            ORDER BY week_label
        """),
        {"cutoff": cutoff},
    ).fetchall()

    week_set: set = set()
    raw: dict = defaultdict(lambda: defaultdict(int))
    for week_label, importance_val, cnt in rows:
        week_set.add(week_label)
        raw[week_label][importance_val] = cnt

    all_weeks = sorted(week_set)
    return {
        "weeks":  all_weeks,
        "high":   [raw[w].get("high", 0)   for w in all_weeks],
        "medium": [raw[w].get("medium", 0) for w in all_weeks],
        "low":    [raw[w].get("low", 0)    for w in all_weeks],
    }


def get_activity_distribution(session: Session, days: int = 30) -> list:
    """activity_type별 카운트 반환 (중요도 breakdown 포함)."""
    cutoff = _cutoff_iso(days)

    rows = session.execute(
        text(f"""
            SELECT
                activity_type,
                COUNT(*)                                             AS total,
                COUNT(*) FILTER (WHERE importance = 'high')         AS high,
                COUNT(*) FILTER (WHERE importance = 'medium')       AS medium,
                COUNT(*) FILTER (WHERE importance = 'low')          AS low
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY activity_type
            ORDER BY total DESC
        """),
        {"cutoff": cutoff},
    ).fetchall()

    grand_total = sum(r[1] for r in rows) or 1
    return [
        {
            "activity_type": r[0] or "기타",
            "total":         r[1] or 0,
            "high":          r[2] or 0,
            "medium":        r[3] or 0,
            "low":           r[4] or 0,
            "pct":           round((r[1] or 0) / grand_total * 100, 1),
        }
        for r in rows
    ]


def get_brand_activity_matrix(session: Session, days: int = 30) -> list:
    """brand × activity_type 크로스탭 (브랜드별 전략 포지셔닝 차트용)."""
    cutoff = _cutoff_iso(days)

    rows = session.execute(
        text(f"""
            SELECT
                brand,
                activity_type,
                COUNT(*)                                             AS total,
                COUNT(*) FILTER (WHERE importance = 'high')         AS high,
                COUNT(*) FILTER (WHERE importance = 'medium')       AS medium,
                COUNT(*) FILTER (WHERE importance = 'low')          AS low
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY brand, activity_type
            ORDER BY brand, total DESC
        """),
        {"cutoff": cutoff},
    ).fetchall()

    # brand → {act_type: {total, high, medium, low}}
    brand_map: dict = defaultdict(lambda: defaultdict(lambda: {"total": 0, "high": 0, "medium": 0, "low": 0}))
    for brand_val, act, total, high, med, low in rows:
        brand_map[brand_val][act or "기타"] = {
            "total":  total or 0,
            "high":   high  or 0,
            "medium": med   or 0,
            "low":    low   or 0,
        }

    return [
        {"brand": b, "activities": dict(acts)}
        for b, acts in brand_map.items()
    ]


def get_brand_high_ratio(session: Session, days: int = 30) -> list:
    """브랜드별 HIGH 비중 비교 (시그널 강도 차트용)."""
    cutoff = _cutoff_iso(days)

    rows = session.execute(
        text(f"""
            SELECT
                brand,
                COUNT(*)                                         AS total,
                COUNT(*) FILTER (WHERE importance = 'high')     AS high
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY brand
            ORDER BY high DESC, total DESC
        """),
        {"cutoff": cutoff},
    ).fetchall()

    return [
        {
            "brand": r[0] or "",
            "total": r[1] or 0,
            "high":  r[2] or 0,
            "pct":   round((r[2] or 0) / (r[1] or 1) * 100, 1),
        }
        for r in rows
    ]


def get_brand_insights_raw(session: Session, days: int = 30) -> dict:
    """브랜드별 전략 인사이트 카드용 원자료 수집.

    반환 형식:
    {
      brand: {
        top_act: str, top_pct: float, high_pct: float,
        top_countries: [[country, count], ...],  # top-3
        articles: [{imp, date, act, title_ko, url}, ...]  # HIGH+MEDIUM top-5
      }
    }
    """
    cutoff = _cutoff_iso(days)

    # 1) brand × activity_type 카운트
    act_rows = session.execute(
        text(f"""
            SELECT brand, activity_type, COUNT(*) AS cnt
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY brand, activity_type
            ORDER BY brand, cnt DESC
        """),
        {"cutoff": cutoff},
    ).fetchall()

    # 2) 브랜드별 총계 + HIGH 카운트
    high_rows = session.execute(
        text(f"""
            SELECT brand,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE importance = 'high') AS high
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY brand
        """),
        {"cutoff": cutoff},
    ).fetchall()

    # 3) 브랜드별 주력 시장 top-3
    country_rows = session.execute(
        text(f"""
            SELECT brand, country, COUNT(*) AS cnt
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY brand, country
            ORDER BY brand, cnt DESC
        """),
        {"cutoff": cutoff},
    ).fetchall()

    # 4) HIGH+MEDIUM 기사 상위 5건 per brand (Claude 요약용)
    art_rows = session.execute(
        text(f"""
            SELECT brand, importance, activity_type,
                   COALESCE(NULLIF(title_ko,''), LEFT(NULLIF(details,''),70), title) AS title_ko,
                   source_url, published_date::date::text AS pub_date,
                   details
            FROM {DB_SCHEMA}.news_articles
            WHERE importance IN ('high', 'medium')
              AND published_date >= :cutoff
            ORDER BY brand,
                     CASE importance WHEN 'high' THEN 0 ELSE 1 END,
                     published_date DESC
        """),
        {"cutoff": cutoff},
    ).fetchall()

    # ── 조합 ──────────────────────────────────────────────
    brand_totals: dict = {}
    for r in high_rows:
        brand_totals[r[0]] = {"total": r[1] or 0, "high": r[2] or 0}

    # top activity per brand
    brand_acts: dict = defaultdict(list)
    for r in act_rows:
        brand_acts[r[0]].append((r[1] or "기타", r[2] or 0))

    # top countries per brand
    brand_countries: dict = defaultdict(list)
    for r in country_rows:
        brand_countries[r[0]].append([r[1], r[2] or 0])

    # articles per brand (max 5)
    brand_arts: dict = defaultdict(list)
    for r in art_rows:
        b = r[0]
        if len(brand_arts[b]) < 5:
            brand_arts[b].append({
                "imp":      r[1] or "",
                "act":      r[2] or "기타",
                "title_ko": r[3] or "",
                "url":      r[4] or "",
                "details":  r[6] or "",
                "date":     r[5] or "",
            })

    result: dict = {}
    for brand in brand_totals:
        acts = brand_acts.get(brand, [])
        top_act, top_cnt = acts[0] if acts else ("기타", 0)
        total = brand_totals[brand]["total"] or 1
        high  = brand_totals[brand]["high"]
        result[brand] = {
            "top_act":       top_act,
            "top_pct":       round(top_cnt / total * 100),
            "high_pct":      round(high / total * 100, 1),
            "top_countries": brand_countries.get(brand, [])[:3],
            "articles":      brand_arts.get(brand, []),
        }
    return result


def get_insights_cache(session: Session, from_date: str, to_date: str) -> dict:
    """날짜 범위 기준 캐시 조회. {brand: {summary, top_act, top_pct, high_pct}}"""
    rows = session.execute(
        text(f"""
            SELECT brand, summary, top_act, top_pct, high_pct
            FROM {DB_SCHEMA}.brand_insights
            WHERE from_date::date = :from_date
              AND to_date::date = :to_date
        """),
        {"from_date": from_date, "to_date": to_date},
    ).fetchall()
    return {
        r[0]: {
            "summary":  r[1] or "",
            "top_act":  r[2] or "기타",
            "top_pct":  r[3] or 0,
            "high_pct": float(r[4]) if r[4] is not None else 0.0,
        }
        for r in rows
    }


def upsert_insight_cache(
    session: Session, brand: str, from_date: str, to_date: str, data: dict
) -> None:
    """브랜드 인사이트 DB에 UPSERT (brand, from_date, to_date 기준)."""
    session.execute(
        text(f"""
            INSERT INTO {DB_SCHEMA}.brand_insights
                (brand, from_date, to_date, summary, top_act, top_pct, high_pct, generated_at)
            VALUES (:brand, :from_date, :to_date, :summary, :top_act, :top_pct, :high_pct, NOW())
            ON CONFLICT (brand, from_date, to_date)
            DO UPDATE SET
                summary      = EXCLUDED.summary,
                top_act      = EXCLUDED.top_act,
                top_pct      = EXCLUDED.top_pct,
                high_pct     = EXCLUDED.high_pct,
                generated_at = EXCLUDED.generated_at
        """),
        {
            "brand":     brand,
            "from_date": from_date,
            "to_date":   to_date,
            "summary":   data.get("summary", ""),
            "top_act":   data.get("top_act", "기타"),
            "top_pct":   int(data.get("top_pct", 0)),
            "high_pct":  float(data.get("high_pct", 0.0)),
        },
    )
    session.commit()


def get_brand_insights_raw_by_range(session: Session, from_date: str, to_date: str) -> dict:
    """명시적 날짜 범위 기반 브랜드 인사이트 원자료 (API 엔드포인트용)."""
    params = {"from_date": from_date, "to_date": to_date}
    date_filter = "published_date::date >= :from_date AND published_date::date <= :to_date"

    act_rows = session.execute(
        text(f"""
            SELECT brand, activity_type, COUNT(*) AS cnt
            FROM {DB_SCHEMA}.news_articles
            WHERE {date_filter}
            GROUP BY brand, activity_type
            ORDER BY brand, cnt DESC
        """), params,
    ).fetchall()

    high_rows = session.execute(
        text(f"""
            SELECT brand,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE importance = 'high') AS high
            FROM {DB_SCHEMA}.news_articles
            WHERE {date_filter}
            GROUP BY brand
        """), params,
    ).fetchall()

    country_rows = session.execute(
        text(f"""
            SELECT brand, country, COUNT(*) AS cnt
            FROM {DB_SCHEMA}.news_articles
            WHERE {date_filter}
            GROUP BY brand, country
            ORDER BY brand, cnt DESC
        """), params,
    ).fetchall()

    art_rows = session.execute(
        text(f"""
            SELECT brand, importance, activity_type,
                   COALESCE(NULLIF(title_ko,''), LEFT(NULLIF(details,''),70), title) AS title_ko,
                   source_url, published_date::date::text AS pub_date, details
            FROM {DB_SCHEMA}.news_articles
            WHERE importance IN ('high', 'medium')
              AND {date_filter}
            ORDER BY brand,
                     CASE importance WHEN 'high' THEN 0 ELSE 1 END,
                     published_date DESC
        """), params,
    ).fetchall()

    brand_totals: dict = {r[0]: {"total": r[1] or 0, "high": r[2] or 0} for r in high_rows}
    brand_acts: dict = defaultdict(list)
    for r in act_rows:
        brand_acts[r[0]].append((r[1] or "기타", r[2] or 0))
    brand_countries: dict = defaultdict(list)
    for r in country_rows:
        brand_countries[r[0]].append([r[1], r[2] or 0])
    brand_arts: dict = defaultdict(list)
    for r in art_rows:
        b = r[0]
        if len(brand_arts[b]) < 5:
            brand_arts[b].append({
                "imp": r[1] or "", "act": r[2] or "기타",
                "title_ko": r[3] or "", "url": r[4] or "",
                "details": r[6] or "", "date": r[5] or "",
            })

    result: dict = {}
    for brand in brand_totals:
        acts = brand_acts.get(brand, [])
        top_act, top_cnt = acts[0] if acts else ("기타", 0)
        total = brand_totals[brand]["total"] or 1
        result[brand] = {
            "top_act":       top_act,
            "top_pct":       round(top_cnt / total * 100),
            "high_pct":      round(brand_totals[brand]["high"] / total * 100, 1),
            "top_countries": brand_countries.get(brand, [])[:3],
            "articles":      brand_arts.get(brand, []),
        }
    return result


def get_country_signal_stats(session: Session, days: int = 30) -> dict:
    """국가별 신호 통계 반환 (세계지도용). {CC: {total, high, medium}}"""
    cutoff = _cutoff_iso(days)
    rows = session.execute(
        text(f"""
            SELECT country,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE importance = 'high') AS high,
                   COUNT(*) FILTER (WHERE importance = 'medium') AS medium
            FROM {DB_SCHEMA}.news_articles
            WHERE published_date >= :cutoff
            GROUP BY country
        """),
        {"cutoff": cutoff},
    ).fetchall()
    return {r[0]: {"total": r[1] or 0, "high": r[2] or 0, "medium": r[3] or 0} for r in rows}
