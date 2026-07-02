"""
APScheduler 스케줄

- Tier1 브랜드 × Tier1 국가: 매일 06:00 KST
- 전체 브랜드 × 전체 국가: 매주 월요일 03:00 KST (주간 풀스캔)
- 주간 중복 정리: 매주 일요일 02:00 KST
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config.brands import TIER1_BRANDS, ALL_BRANDS, TIER1_COUNTRIES, COUNTRIES
from config.settings import TITLE_SIMILARITY_THRESHOLD
from scheduler.pipeline import run_pipeline, reset_jangup_cache
from scheduler.briefing import generate_weekly_briefing
from storage.models import get_session
from storage.repository import save_dedup_candidate, get_recent_titles
from deduplication.url_hasher import title_similarity

logger = logging.getLogger(__name__)


def job_daily_tier1() -> None:
    """Tier1 브랜드 × Tier1 국가 — 매일 수집 (구글RSS + 전문미디어 + 장업신문 + PRTIMES)."""
    reset_jangup_cache()  # 장업신문 피드 캐시 초기화 (하루 1회 새로 fetch)
    logger.info("=== [일별] Tier1 수집 시작 (브랜드 %d개 x 국가 %d개) ===",
                len(TIER1_BRANDS), len(TIER1_COUNTRIES))
    for brand in TIER1_BRANDS:
        for country in TIER1_COUNTRIES:
            try:
                run_pipeline(brand, country)
            except Exception as e:
                logger.error("오류 [%s/%s]: %s", brand, country, e)
    logger.info("=== [일별] Tier1 수집 완료 ===")


def job_weekly_full() -> None:
    """전체 브랜드 × 전체 국가 — 주간 풀스캔."""
    all_countries = list(COUNTRIES.keys())
    logger.info("=== [주간] 전체 수집 시작 (브랜드 %d개 x 국가 %d개) ===",
                len(ALL_BRANDS), len(all_countries))
    for brand in ALL_BRANDS:
        for country in all_countries:
            try:
                run_pipeline(brand, country)
            except Exception as e:
                logger.error("오류 [%s/%s]: %s", brand, country, e)
    logger.info("=== [주간] 전체 수집 완료 ===")


def job_weekly_dedup() -> None:
    """제목 유사도 기반 중복 쌍 기록."""
    logger.info("=== 주간 중복 정리 시작 ===")
    session = get_session()
    try:
        recent = get_recent_titles(session, days=7)
        count = 0
        for i in range(len(recent)):
            for j in range(i + 1, len(recent)):
                id1, title1 = recent[i]
                id2, title2 = recent[j]
                score = title_similarity(title1, title2)
                if score >= TITLE_SIMILARITY_THRESHOLD:
                    save_dedup_candidate(session, id1, id2, score)
                    count += 1
        logger.info("중복 후보 %d쌍 기록 완료", count)
    except Exception as e:
        logger.error("주간 중복 정리 오류: %s", e)
    finally:
        session.close()
    logger.info("=== 주간 중복 정리 완료 ===")


def create_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 매일 06:00 KST
    scheduler.add_job(
        job_daily_tier1,
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_tier1",
        name="[일별] Tier1 브랜드x국가 수집",
        max_instances=1,
        coalesce=True,
    )

    # 매주 월요일 03:00 KST
    scheduler.add_job(
        job_weekly_full,
        trigger=CronTrigger(day_of_week="mon", hour=3, minute=0),
        id="weekly_full",
        name="[주간] 전체 브랜드x국가 풀스캔",
        max_instances=1,
        coalesce=True,
    )

    # 매주 일요일 02:00 KST
    scheduler.add_job(
        job_weekly_dedup,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_dedup",
        name="[주간] 중복 정리",
        max_instances=1,
    )

    # 매주 월요일 09:00 KST — 주간 브리핑 Slack 전송
    scheduler.add_job(
        generate_weekly_briefing,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_briefing",
        name="[주간] 브리핑 생성 및 Slack 전송",
        max_instances=1,
    )

    return scheduler


def start() -> None:
    """스케줄러 시작 (블로킹 — Ctrl+C 로 종료)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    scheduler = create_scheduler()

    logger.info("스케줄러 시작")
    for job in scheduler.get_jobs():
        logger.info("  %-14s %s", job.id, job.name)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("스케줄러 종료")
