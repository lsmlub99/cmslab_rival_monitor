"""
CelFusion 경쟁사 모니터링 CLI

사용법:
    python cli.py init-db                              # DB 테이블 생성
    python cli.py collect --brand Anua --country PL   # 단일 수집 테스트
    python cli.py query --brand Anua --days 7         # 최근 기사 조회
    python cli.py drill --days 30                     # HIGH 기사 드릴다운 (터미널)
    python cli.py report --days 30                    # HTML 대시보드 생성 후 브라우저 오픈
    python cli.py run                                  # 스케줄러 시작
"""

import logging
import sys

import click

from config.brands import ALL_BRANDS, COUNTRIES, ACTIVITY_TYPES


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="DEBUG 로그 출력")
def cli(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


@cli.command()
def init_db() -> None:
    """PostgreSQL 테이블 생성."""
    from storage.models import create_tables
    create_tables()
    click.echo("DB 초기화 완료")


@cli.command()
@click.option("--brand", "-b", required=True, help=f"브랜드명 (예: Anua)")
@click.option("--country", "-c", required=True,
              help=f"국가 코드 [{', '.join(COUNTRIES.keys())}]")
def collect(brand: str, country: str) -> None:
    """단일 브랜드+국가 수집 파이프라인 실행 (테스트용)."""
    if brand not in ALL_BRANDS:
        click.echo(f"[오류] 미지원 브랜드: {brand}", err=True)
        click.echo(f"지원 브랜드: {', '.join(ALL_BRANDS)}", err=True)
        sys.exit(1)
    if country.upper() not in COUNTRIES:
        click.echo(f"[오류] 미지원 국가 코드: {country}", err=True)
        sys.exit(1)

    from scheduler.pipeline import run_pipeline
    stats = run_pipeline(brand, country.upper())

    click.echo(
        f"\n결과: 수집 {stats.found}건 / URL중복 {stats.url_duped} / "
        f"제목중복 {stats.title_duped} / 분류 {stats.classified} / "
        f"저장 {stats.saved} / 오류 {stats.errors} ({stats.duration}s)"
    )


@cli.command()
@click.option("--brand", "-b", default=None, help="브랜드 필터")
@click.option("--country", "-c", default=None, help="국가 코드 필터")
@click.option("--activity", "-a", default=None,
              type=click.Choice(ACTIVITY_TYPES), help="활동 유형 필터")
@click.option("--importance", "-i", default=None,
              type=click.Choice(["high", "medium", "low"]), help="중요도 필터")
@click.option("--days", "-d", default=7, show_default=True, help="최근 N일")
@click.option("--limit", "-l", default=20, show_default=True, help="최대 결과 수")
def query(
    brand: str,
    country: str,
    activity: str,
    importance: str,
    days: int,
    limit: int,
) -> None:
    """수집된 기사 조회."""
    from storage.models import get_session
    from storage.repository import query_articles

    session = get_session()
    try:
        articles = query_articles(
            session,
            brand=brand,
            country=country.upper() if country else None,
            activity_type=activity,
            importance=importance,
            days=days,
            limit=limit,
        )
    finally:
        session.close()

    if not articles:
        click.echo("조회 결과 없음")
        return

    click.echo(f"\n{'='*70}")
    click.echo(f"조회 결과: {len(articles)}건")
    click.echo(f"{'='*70}")

    for art in articles:
        importance_label = {"high": "★★★", "medium": "★★☆", "low": "★☆☆"}.get(
            art.importance, art.importance
        )
        click.echo(
            f"\n[{art.brand}] {art.country} | {art.activity_type} | {importance_label}"
        )
        date_str = art.published_date.strftime("%Y-%m-%d") if art.published_date else "?"
        click.echo(f"  날짜: {date_str}  |  출처: {art.source_name or '?'}")
        click.echo(f"  제목: {art.title}")
        click.echo(f"  내용: {art.details}")
        if art.note:
            click.echo(f"  메모: {art.note}")
        click.echo(f"  URL: {art.source_url}")

    click.echo(f"\n{'='*70}\n")


@cli.command()
@click.option("--days", "-d", default=30, show_default=True, help="집계 기간 (일)")
@click.option("--brand", "-b", default=None, help="브랜드 필터")
@click.option("--country", "-c", default=None, help="국가 코드 필터")
def drill(days: int, brand: str, country: str) -> None:
    """HIGH importance 기사 상세 드릴다운 (터미널 출력)."""
    from storage.models import get_session
    from analytics.queries import get_high_articles

    session = get_session()
    try:
        articles = get_high_articles(
            session, days=days,
            brand=brand,
            country=country.upper() if country else None,
        )
    finally:
        session.close()

    if not articles:
        click.echo("HIGH 기사 없음")
        return

    click.echo(f"\n{'='*72}")
    click.echo(f"  HIGH IMPORTANCE 드릴다운 — 최근 {days}일  ({len(articles)}건)")
    if brand:
        click.echo(f"  브랜드 필터: {brand}")
    if country:
        click.echo(f"  국가 필터: {country.upper()}")
    click.echo(f"{'='*72}")

    act_short = {
        "신시장_진출": "신시장진출", "유통_채널": "유통채널",
        "신제품_런칭": "신제품런칭", "인플루언서_협업": "인플루언서",
        "투자_BD": "투자BD", "브랜드_마케팅": "마케팅", "기타": "기타",
    }

    for i, art in enumerate(articles, 1):
        date_str = art["published_date"][:10] if art["published_date"] else "?"
        conf_str = f"{art['confidence']:.0%}" if art["confidence"] is not None else "?"
        act_label = act_short.get(art["activity_type"], art["activity_type"])
        click.echo(
            f"\n[{i:02d}] {art['brand']} | {art['country']} | "
            f"{act_label} | {date_str} | 신뢰도 {conf_str}"
        )
        click.echo(f"  제목: {art['title']}")
        if art.get("product_name"):
            click.echo(f"  제품: {art['product_name']}")
        click.echo(f"  내용: {art['details']}")
        if art.get("note"):
            click.echo(f"  메모: {art['note']}")
        click.echo(f"  URL : {art['source_url']}")
        if art.get("source_name"):
            click.echo(f"  출처: {art['source_name']}")

    click.echo(f"\n{'='*72}\n")


@cli.command()
@click.option("--days", "-d", default=30, show_default=True, help="집계 기간 (일)")
@click.option("--output", "-o", default="rival_report.html", show_default=True,
              help="출력 HTML 파일 경로")
@click.option("--no-open", is_flag=True, default=False, help="브라우저 자동 오픈 생략")
def report(days: int, output: str, no_open: bool) -> None:
    """HTML 대시보드 보고서 생성 후 기본 브라우저로 오픈."""
    import webbrowser
    from pathlib import Path
    from dashboard.generate import generate_report as gen_report

    click.echo(f"보고서 생성 중... (최근 {days}일, 출력: {output})")
    abs_path = gen_report(output_path=output, days=days)
    click.echo(f"생성 완료: {abs_path}")

    if not no_open:
        url = Path(abs_path).as_uri()
        webbrowser.open(url)
        click.echo(f"브라우저 오픈: {url}")


@cli.command("collect-all")
@click.option("--tier", "-t", default=1, type=click.Choice(["1", "2"]),
              show_default=True, help="수집 Tier (1=핵심, 2=전체)")
def collect_all(tier: str) -> None:
    """전체 브랜드 × 국가 일괄 수집."""
    from config.brands import TIER1_BRANDS, ALL_BRANDS, TIER1_COUNTRIES, COUNTRIES
    from scheduler.pipeline import run_pipeline

    brands = TIER1_BRANDS if tier == "1" else ALL_BRANDS
    countries = TIER1_COUNTRIES if tier == "1" else list(COUNTRIES.keys())

    total_saved = 0
    click.echo(f"수집 시작: {len(brands)}개 브랜드 × {len(countries)}개 국가")

    for brand in brands:
        for country in countries:
            try:
                stats = run_pipeline(brand, country)
                total_saved += stats.saved
                click.echo(
                    f"  [{brand}/{country}] 저장 {stats.saved}건 "
                    f"(수집 {stats.found} / 분류 {stats.classified})"
                )
            except Exception as e:
                click.echo(f"  [{brand}/{country}] 오류: {e}", err=True)

    click.echo(f"\n완료: 총 {total_saved}건 저장")


@cli.command()
def run() -> None:
    """스케줄러 시작 (백그라운드 운영용, Ctrl+C 로 종료)."""
    from scheduler.runner import start
    start()


if __name__ == "__main__":
    cli()
