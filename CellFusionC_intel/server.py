"""
K-뷰티 경쟁사 인텔리전스 — FastAPI 서버

실행:
    uvicorn server:app --reload          # 개발
    uvicorn server:app --host 0.0.0.0 --port 8000  # 배포
"""

import html as html_lib
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# .env를 명시적 경로로 로드 (CWD 무관)
from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))

from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="K-뷰티 경쟁사 인텔리전스", docs_url="/docs")

# 생성된 HTML 캐시 (메모리)
_dashboard_html: str = ""


def _build_dashboard() -> str:
    from dashboard.generate import generate_report
    path = generate_report("_server_cache.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── 대시보드 ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """메인 대시보드."""
    global _dashboard_html
    if not _dashboard_html:
        _dashboard_html = _build_dashboard()
    return _dashboard_html


@app.post("/api/refresh")
async def refresh(background_tasks: BackgroundTasks):
    """대시보드 재생성 (백그라운드). 기사 수집 후 호출."""
    def _regen():
        global _dashboard_html
        _dashboard_html = _build_dashboard()
        logger.info("대시보드 재생성 완료")

    background_tasks.add_task(_regen)
    return {"status": "ok", "message": "재생성 중 — 잠시 후 새로고침하세요"}


# ── 인사이트 API ─────────────────────────────────────────────────────────────

@app.get("/api/insights")
async def api_insights(
    from_date: str = Query(..., description="시작일 YYYY-MM-DD"),
    to_date: str   = Query(..., description="종료일 YYYY-MM-DD"),
):
    """날짜 범위 기반 브랜드 전략 인사이트.

    DB 캐시 히트 → 즉시 반환.
    캐시 미스 → OpenAI 생성 → DB 저장 → 반환.
    동일 날짜 범위는 영구 캐시 (기사가 변하지 않으므로 결과도 동일).
    """
    from analytics.queries import (
        get_insights_cache,
        upsert_insight_cache,
        get_brand_insights_raw_by_range,
    )
    from analytics.summarizer import generate_brand_strategy_summary
    from storage.models import get_session

    session = get_session()
    try:
        cached = get_insights_cache(session, from_date, to_date)
        raw    = get_brand_insights_raw_by_range(session, from_date, to_date)
    finally:
        session.close()

    if not raw:
        return JSONResponse({})

    result: dict = {}
    save_session = get_session()
    try:
        for brand, data in raw.items():
            if brand in cached and cached[brand].get("summary"):
                ins = cached[brand]
            else:
                summary = generate_brand_strategy_summary(brand, data.get("articles", []))
                ins = {
                    "summary":  summary,
                    "top_act":  data["top_act"],
                    "top_pct":  data["top_pct"],
                    "high_pct": data["high_pct"],
                }
                if summary:  # 빈 문자열은 캐시 저장 안 함
                    upsert_insight_cache(save_session, brand, from_date, to_date, ins)

            result[brand] = {
                "top_act":       html_lib.escape(ins.get("top_act", "기타")),
                "top_pct":       ins.get("top_pct", 0),
                "high_pct":      ins.get("high_pct", 0.0),
                "strategy":      html_lib.escape(ins.get("summary", "")),
                "top_countries": data["top_countries"],
                "key_articles": [
                    {
                        "imp":      a.get("imp", "low"),
                        "date":     a.get("date", ""),
                        "act":      html_lib.escape(a.get("act", "")),
                        "title_ko": html_lib.escape(a.get("title_ko", "")),
                        "url":      a.get("url", ""),
                    }
                    for a in data.get("articles", [])[:3]
                ],
            }
    finally:
        save_session.close()

    return JSONResponse(result)


# ── 로컬 실행 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
