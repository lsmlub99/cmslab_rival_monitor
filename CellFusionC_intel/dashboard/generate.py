"""
HTML 대시보드 보고서 생성기

generate_report(output_path, days) → self-contained HTML 파일 절대경로 반환.
외부 CDN 없이 브라우저에서 바로 열 수 있는 단일 파일을 생성한다.
"""

import html as html_lib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests as req

from analytics.queries import (
    get_activity_distribution,
    get_brand_activity_matrix,
    get_brand_country_matrix,
    get_brand_high_ratio,
    get_brand_insights_raw,
    get_collection_stats,
    get_high_articles,
    get_weekly_trend,
)
from analytics.summarizer import generate_brand_strategy_summary
from storage.models import get_session

logger = logging.getLogger(__name__)

CHARTJS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"
_CACHE_PATH = Path(__file__).parent / "chartjs_cache.min.js"

COUNTRY_FLAGS = {
    "US": "🇺🇸", "JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳",
    "PL": "🇵🇱", "SG": "🇸🇬", "TH": "🇹🇭", "GB": "🇬🇧",
    "CA": "🇨🇦", "AU": "🇦🇺", "DE": "🇩🇪", "FR": "🇫🇷",
    "ID": "🇮🇩", "MY": "🇲🇾", "VN": "🇻🇳", "PH": "🇵🇭",
    "IT": "🇮🇹",
}

ACTIVITY_LABELS = {
    "신시장_진출":    "신시장 진출",
    "유통_채널":      "유통 채널",
    "신제품_런칭":    "신제품 런칭",
    "인플루언서_협업": "인플루언서 협업",
    "투자_BD":        "투자·BD",
    "브랜드_마케팅":  "브랜드 마케팅",
    "기타":           "기타",
}

# 활동 유형별 차트 색상
ACTIVITY_COLORS = [
    "#2b6cb0", "#e53e3e", "#2f855a", "#744210",
    "#553c9a", "#c05621", "#4a5568",
]


# ---------------------------------------------------------------------------
# Chart.js 로컬 캐시
# ---------------------------------------------------------------------------

def _get_chartjs() -> str:
    """Chart.js minified 소스 반환. 캐시 파일 우선, 없으면 다운로드."""
    if _CACHE_PATH.exists():
        try:
            return _CACHE_PATH.read_text(encoding="utf-8")
        except Exception:
            pass
    try:
        resp = req.get(CHARTJS_URL, timeout=15)
        if resp.status_code == 200:
            _CACHE_PATH.write_text(resp.text, encoding="utf-8")
            logger.info("Chart.js 캐시 완료: %s", _CACHE_PATH)
            return resp.text
    except Exception as e:
        logger.warning("Chart.js 다운로드 실패 (CSS 폴백 사용): %s", e)
    return ""


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _esc(s) -> str:
    return html_lib.escape(str(s)) if s else ""


def _fmt_date(iso_str: str) -> str:
    """ISO 날짜 문자열 → KST YYYY-MM-DD."""
    if not iso_str:
        return "?"
    try:
        dt = datetime.fromisoformat(iso_str[:19]) + timedelta(hours=9)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10]


def _cell_color(value: int, max_value: int) -> str:
    """히트맵 셀 배경색. 0=흰색, max=남색(#1a3a5c), 텍스트 색도 반환."""
    if max_value == 0 or value == 0:
        return "background:#f8fafc;color:#cbd5e0;"
    norm = value / max_value
    r = int(255 - norm * (255 - 26))
    g = int(255 - norm * (255 - 58))
    b = int(255 - norm * (255 - 92))
    text = "#ffffff" if norm > 0.55 else "#1a3a5c"
    return f"background:rgb({r},{g},{b});color:{text};"


# ---------------------------------------------------------------------------
# 섹션별 HTML 렌더러
# ---------------------------------------------------------------------------

def _render_kpi_cards(stats: dict) -> str:
    items = [
        ("총 수집", stats["total"],            "건", "#2b6cb0"),
        ("HIGH",    stats["high"],             "건", "#c53030"),
        ("활성 브랜드", stats["brands_active"],  "개", "#276749"),
        ("커버 국가",  stats["countries_active"], "개", "#744210"),
    ]
    cards = "".join(
        f'<div class="kpi-card">'
        f'<div class="kpi-value" style="color:{color}">{val}<span class="kpi-unit">{unit}</span></div>'
        f'<div class="kpi-label">{_esc(label)}</div>'
        f'</div>'
        for label, val, unit, color in items
    )
    return f'<div class="kpi-grid">{cards}</div>'


def _render_high_table(articles: list) -> str:
    if not articles:
        return '<p class="no-data">HIGH 기사 없음</p>'

    rows = []
    for i, art in enumerate(articles):
        flag = COUNTRY_FLAGS.get(art["country"], "🌐")
        act_label = ACTIVITY_LABELS.get(art["activity_type"], art["activity_type"])
        date_str = _fmt_date(art["published_date"])
        conf_str = f"{art['confidence']:.0%}" if art["confidence"] is not None else "?"
        title_disp = art["title"][:85] + ("…" if len(art["title"]) > 85 else "")

        product_line = (
            f'<p><strong>제품:</strong> {_esc(art["product_name"])}</p>'
            if art.get("product_name") else ""
        )
        note_line = (
            f'<p class="note-line"><strong>메모:</strong> {_esc(art["note"])}</p>'
            if art.get("note") else ""
        )
        # 제목: 한국어 번역이 있으면 원문 + 번역 모두 표시
        title_ko_line = (
            f'<p class="title-ko-line"><strong>제목(한):</strong> {_esc(art["title_ko"])}</p>'
            if art.get("title_ko") else ""
        )
        # 본문: 한국어 번역이 있으면 표시, 없으면 details로 대체
        body_ko = art.get("article_body_ko") or ""
        body_ko_line = (
            f'<p><strong>본문(한):</strong> {_esc(body_ko)}</p>'
            if body_ko else ""
        )
        # 원문 본문이 있으면 아코디언으로 표시
        orig_body = art.get("article_body") or ""
        orig_body_line = (
            f'<details class="body-orig"><summary>원문 본문 보기</summary>'
            f'<pre class="body-text">{_esc(orig_body[:1500])}'
            f'{"…" if len(orig_body) > 1500 else ""}</pre></details>'
            if orig_body else ""
        )
        # 제목 표시: title_ko 있으면 그걸 먼저, 없으면 원문
        title_display = art.get("title_ko") or art["title"]
        title_disp2 = title_display[:85] + ("…" if len(title_display) > 85 else "")

        rows.append(
            f'<tr class="main-row" onclick="toggleRow({i})">'
            f'<td class="date-cell">{_esc(date_str)}</td>'
            f'<td><span class="brand-tag">{_esc(art["brand"])}</span></td>'
            f'<td class="flag-cell">{flag} {_esc(art["country"])}</td>'
            f'<td><span class="act-tag">{_esc(act_label)}</span></td>'
            f'<td class="title-cell">{_esc(title_disp2)}</td>'
            f'<td class="conf-cell">{_esc(conf_str)}</td>'
            f'<td><a href="{_esc(art["source_url"])}" target="_blank" '
            f'onclick="event.stopPropagation()">원문↗</a></td>'
            f'</tr>'
            f'<tr id="dr-{i}" class="detail-row hidden">'
            f'<td colspan="7">'
            f'<div class="detail-box">'
            f'{title_ko_line}'
            f'<p><strong>요약(한):</strong> {_esc(art["details"])}</p>'
            f'{body_ko_line}'
            f'{product_line}{note_line}'
            f'{orig_body_line}'
            f'<p class="src-info">출처: {_esc(art.get("source_name","?"))}</p>'
            f'</div></td></tr>'
        )

    return (
        '<div class="table-wrap">'
        '<table class="data-table">'
        '<thead><tr>'
        '<th>날짜</th><th>브랜드</th><th>국가</th>'
        '<th>활동 유형</th><th>제목</th><th>신뢰도</th><th>링크</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></div>'
    )


def _render_heatmap(matrix_data: dict) -> str:
    brands = matrix_data["brands"]
    countries = matrix_data["countries"]
    if not brands:
        return '<p class="no-data">데이터 없음</p>'

    matrix = matrix_data["matrix"]
    brand_totals = matrix_data["brand_totals"]
    country_totals = matrix_data["country_totals"]
    max_val = max(
        (matrix.get(b, {}).get(c, 0) for b in brands for c in countries),
        default=1,
    ) or 1

    header = "".join(
        f'<th title="{_esc(c)}">{COUNTRY_FLAGS.get(c,"")} {_esc(c)}</th>'
        for c in countries
    )
    thead = f'<thead><tr><th class="sticky-col">브랜드</th>{header}<th>합계</th></tr></thead>'

    body_rows = []
    for brand in brands:
        cells = []
        for c in countries:
            v = matrix.get(brand, {}).get(c, 0)
            style = _cell_color(v, max_val)
            if v:
                b_esc = _esc(brand).replace("'", "\\'")
                click = f' onclick="openHeatmapDrilldown(\'{b_esc}\',\'{c}\')"'
                extra = f' title="{_esc(brand)} × {c} ({v}건)" style="{style}cursor:pointer;"'
            else:
                click = ""
                extra = f' style="{style}"'
            cells.append(f'<td{extra}{click}>{v or ""}</td>')
        total = brand_totals.get(brand, 0)
        body_rows.append(
            f'<tr><td class="sticky-col brand-name">{_esc(brand)}</td>'
            f'{"".join(cells)}<td class="total-cell">{total}</td></tr>'
        )

    # 합계 행
    foot_cells = "".join(
        f'<td class="total-cell">{country_totals.get(c,0)}</td>'
        for c in countries
    )
    grand = matrix_data["grand_total"]
    foot = (
        f'<tr class="total-row"><td class="sticky-col">합계</td>'
        f'{foot_cells}<td class="total-cell">{grand}</td></tr>'
    )

    return (
        '<div class="table-wrap heatmap-wrap">'
        f'<table class="data-table heatmap-table">{thead}'
        f'<tbody>{"".join(body_rows)}{foot}</tbody></table>'
        '</div>'
    )


def _canvas_or_table_trend(trend: dict, has_chartjs: bool) -> str:
    """트렌드 섹션 HTML (Chart.js 없으면 테이블 폴백)."""
    if not trend["weeks"]:
        return '<p class="no-data">주별 트렌드 데이터 없음</p>'
    if has_chartjs:
        return '<div class="chart-container"><canvas id="trendChart"></canvas></div>'
    # 폴백: 테이블
    rows = "".join(
        f'<tr><td>{_esc(w)}</td>'
        f'<td style="color:#c53030;font-weight:700">{h}</td>'
        f'<td style="color:#dd6b20">{m}</td>'
        f'<td style="color:#a0aec0">{lo}</td></tr>'
        for w, h, m, lo in zip(trend["weeks"], trend["high"], trend["medium"], trend["low"])
    )
    return (
        '<div class="table-wrap"><table class="data-table">'
        '<thead><tr><th>주차</th><th>HIGH</th><th>MEDIUM</th><th>LOW</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )


def _canvas_or_table_activity(distribution: list, has_chartjs: bool) -> str:
    """활동 분포 섹션 HTML (Chart.js 없으면 테이블 폴백)."""
    if not distribution:
        return '<p class="no-data">데이터 없음</p>'
    if has_chartjs:
        return '<div class="chart-container chart-sm"><canvas id="actChart"></canvas></div>'
    rows = "".join(
        f'<tr><td>{_esc(ACTIVITY_LABELS.get(d["activity_type"],d["activity_type"]))}</td>'
        f'<td>{d["total"]}</td><td>{d["pct"]}%</td>'
        f'<td style="color:#c53030">{d["high"]}</td></tr>'
        for d in distribution
    )
    return (
        '<div class="table-wrap"><table class="data-table">'
        '<thead><tr><th>활동 유형</th><th>건수</th><th>비율</th><th>HIGH</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )


def _render_filter_bar(brands: list, activity_types: list) -> str:
    """브랜드 + 활동유형 필터 pill 바."""
    brand_pills = '<button class="filter-pill active" data-brand="all">전체</button>'
    for b in brands:
        brand_pills += f'<button class="filter-pill" data-brand="{_esc(b)}">{_esc(b)}</button>'

    act_pills = '<button class="filter-pill active" data-act="all">전체</button>'
    for a in activity_types:
        label = ACTIVITY_LABELS.get(a, a)
        act_pills += f'<button class="filter-pill" data-act="{_esc(a)}">{_esc(label)}</button>'

    return (
        '<div class="filter-bar" id="filter-bar">'
        f'<span class="filter-label">브랜드</span>'
        f'<div class="filter-group" id="brand-filters">{brand_pills}</div>'
        '<div class="filter-sep"></div>'
        f'<span class="filter-label">활동</span>'
        f'<div class="filter-group" id="act-filters">{act_pills}</div>'
        '<span class="filter-count" id="filter-count"></span>'
        '</div>'
    )


def _render_brand_high_ratio(brand_high: list) -> str:
    """브랜드별 HIGH 비중 CSS 바 차트."""
    if not brand_high:
        return '<p class="no-data">데이터 없음</p>'
    rows = []
    for d in brand_high:
        pct = d["pct"]
        rows.append(
            f'<div class="hr-row">'
            f'<div class="hr-brand">{_esc(d["brand"])}</div>'
            f'<div class="hr-bar-bg"><div class="hr-bar-fill" style="width:{pct}%"></div></div>'
            f'<div class="hr-badge">{pct:.1f}%</div>'
            f'<div class="hr-meta">{d["high"]}/{d["total"]}건</div>'
            f'</div>'
        )
    return f'<div class="high-ratio-wrap">{"".join(rows)}</div>'


def _render_brand_activity_bar(brand_act: list) -> str:
    """브랜드별 활동 유형 수평 스택바 (Canvas)."""
    if not brand_act:
        return '<p class="no-data">데이터 없음</p>'
    return '<div class="stacked-wrap"><canvas id="stackedBar"></canvas></div>'


def _build_stacked_bar_script(brand_act: list) -> str:
    """브랜드별 활동유형 스택바 Canvas 스크립트."""
    if not brand_act:
        return ""
    act_keys = ["유통_채널", "인플루언서_협업", "신시장_진출", "신제품_런칭", "투자_BD", "기타"]
    act_labels_list = [ACTIVITY_LABELS.get(k, k) for k in act_keys]
    act_colors = ["#1e40af", "#0d9488", "#7c3aed", "#d97706", "#dc2626", "#9ca3af"]

    # [{brand, acts: [count...]}]
    rows_data = []
    for d in brand_act:
        acts = [d["activities"].get(k, {}).get("total", 0) for k in act_keys]
        rows_data.append({"brand": d["brand"], "acts": acts})

    data_json = json.dumps({
        "brands": [r["brand"] for r in rows_data],
        "act_labels": act_labels_list,
        "act_colors": act_colors,
        "rows": [r["acts"] for r in rows_data],
    })
    return f"""
(function() {{
  var d = {data_json};
  var canvas = document.getElementById('stackedBar');
  if (!canvas) return;
  var dpr = window.devicePixelRatio || 1;
  var BAR_H = 34, GAP = 14, LABEL_W = 110, PAD_R = 16, PAD_T = 8, PAD_B = 28;
  var n = d.brands.length;
  var totalH = PAD_T + n * BAR_H + (n - 1) * GAP + PAD_B;
  var W = canvas.parentElement.getBoundingClientRect().width;
  canvas.width = W * dpr; canvas.height = totalH * dpr;
  canvas.style.width = W + 'px'; canvas.style.height = totalH + 'px';
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  var chartW = W - LABEL_W - PAD_R;
  d.brands.forEach(function(brand, ri) {{
    var acts = d.rows[ri];
    var total = acts.reduce(function(s, v) {{ return s + v; }}, 0);
    var y = PAD_T + ri * (BAR_H + GAP);
    ctx.fillStyle = '#1a202c';
    ctx.font = '600 11px system-ui,-apple-system,sans-serif';
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText(brand, LABEL_W - 8, y + BAR_H / 2);
    var x = LABEL_W;
    acts.forEach(function(v, ki) {{
      if (!v || !total) return;
      var segW = (v / total) * chartW;
      ctx.fillStyle = d.act_colors[ki];
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {{
        ctx.roundRect(x, y, segW, BAR_H, 3);
      }} else {{ ctx.rect(x, y, segW, BAR_H); }}
      ctx.fill();
      if (v / total > 0.1) {{
        ctx.fillStyle = '#fff';
        ctx.font = '500 10px system-ui';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(d.act_labels[ki], x + segW / 2, y + BAR_H / 2);
      }}
      x += segW;
    }});
    ctx.fillStyle = '#718096';
    ctx.font = '11px system-ui';
    ctx.textAlign = 'left';
    ctx.fillText(total + '건', x + 5, y + BAR_H / 2);
  }});
  // Legend
  var leg = document.getElementById('stacked-legend');
  if (leg) {{
    d.act_labels.forEach(function(lb, i) {{
      var el = document.createElement('div');
      el.className = 'legend-item';
      el.innerHTML = '<span class="legend-dot" style="background:' + d.act_colors[i] + '"></span>' + lb;
      leg.appendChild(el);
    }});
  }}
}})();"""


def _build_insights_script(brand_insights: dict) -> str:
    """BRAND_INSIGHTS JS 상수 + buildInsightCards() 호출 스크립트."""
    if not brand_insights:
        return ""

    flag_map = {"US":"🇺🇸","JP":"🇯🇵","KR":"🇰🇷","SG":"🇸🇬","PL":"🇵🇱","TH":"🇹🇭","CA":"🇨🇦","GB":"🇬🇧"}
    imp_colors = {"high": "#dc2626", "medium": "#d97706", "low": "#9ca3af"}
    act_colors_map = {
        "유통_채널": "#1e40af", "인플루언서_협업": "#0d9488",
        "신시장_진출": "#7c3aed", "신제품_런칭": "#d97706",
        "투자_BD": "#dc2626", "기타": "#9ca3af",
    }

    # Sanitize for JSON embed
    def esc(s: str) -> str:
        return html_lib.escape(str(s or ""), quote=True)

    insights_json = json.dumps({
        brand: {
            "top_act":       esc(data["top_act"]),
            "top_pct":       data["top_pct"],
            "high_pct":      data["high_pct"],
            "strategy":      esc(data["strategy"]),
            "top_countries": data["top_countries"],
            "key_articles":  [
                {
                    "imp":      a.get("imp", "low"),
                    "date":     a.get("date", ""),
                    "act":      esc(a.get("act", "")),
                    "title_ko": esc(a.get("title_ko", "")),
                    "url":      a.get("url", ""),
                }
                for a in data.get("key_articles", [])
            ],
        }
        for brand, data in brand_insights.items()
    }, ensure_ascii=False)

    flag_json = json.dumps(flag_map)
    imp_json  = json.dumps(imp_colors)

    return f"""
// ── Brand Insight Cards (auto-generated by Claude API) ──
(function() {{
  var INSIGHTS = {insights_json};
  var FLAGS = {flag_json};
  var IMP_C = {imp_json};
  var ACT_ORDER = ["유통_채널","인플루언서_협업","신시장_진출","신제품_런칭","투자_BD","기타"];
  var ACT_COLORS_MAP = {{"유통_채널":"#1e40af","인플루언서_협업":"#0d9488","신시장_진출":"#7c3aed","신제품_런칭":"#d97706","투자_BD":"#dc2626","기타":"#9ca3af"}};

  var grid = document.getElementById('insight-grid');
  if (!grid) return;

  var html = '';
  Object.keys(INSIGHTS).forEach(function(brand) {{
    var ins = INSIGHTS[brand];
    var highCls = ins.high_pct >= 15 ? 'insight-badge-high-hot'
                : ins.high_pct >= 8  ? 'insight-badge-high-warm'
                :                      'insight-badge-high-low';
    var actColor = ACT_COLORS_MAP[ins.top_act] || '#9ca3af';
    var mkts = (ins.top_countries || []).map(function(cc_cnt) {{
      return '<span class="insight-market-item">' + (FLAGS[cc_cnt[0]] || cc_cnt[0]) +
             ' <span class="insight-market-cnt">' + cc_cnt[1] + '건</span></span>';
    }}).join('');
    var arts = (ins.key_articles || []).map(function(a) {{
      var dot = IMP_C[a.imp] || '#9ca3af';
      var lnk = (a.url && a.url.indexOf('http') === 0)
        ? '<a class="insight-art-link" href="' + a.url + '" target="_blank" rel="noopener">↗</a>'
        : '';
      return '<div class="insight-art-row">' +
        '<span class="insight-art-imp" style="background:' + dot + '"></span>' +
        '<span class="insight-art-title">' + a.title_ko + '</span>' +
        '<span class="insight-art-meta">' + (a.date || '').slice(5) + '</span>' +
        lnk + '</div>';
    }}).join('');
    var safeId = 'insight-' + brand.replace(/\\s/g, '_');
    html += '<div class="insight-card" id="' + safeId + '">' +
      '<div class="insight-hdr">' +
        '<span class="insight-brand">' + brand + '</span>' +
        '<span class="insight-badge insight-badge-act" style="background:' + actColor + '">' + ins.top_act + ' ' + ins.top_pct + '%</span>' +
        '<span class="insight-badge ' + highCls + '">HIGH ' + ins.high_pct + '%</span>' +
      '</div>' +
      '<div class="insight-strategy">' + ins.strategy + '</div>' +
      '<div class="insight-markets">' + mkts + '</div>' +
      '<div class="insight-articles-hdr">핵심 근거 기사</div>' +
      arts +
    '</div>';
  }});
  grid.innerHTML = html;
}})();"""


def _build_chart_scripts(trend: dict, distribution: list) -> str:
    """Chart.js 초기화 스크립트 (Chart.js 로드 후 실행될 코드)."""
    scripts = []

    if trend["weeks"]:
        data_json = json.dumps({
            "labels": trend["weeks"],
            "high":   trend["high"],
            "medium": trend["medium"],
            "low":    trend["low"],
        })
        scripts.append(f"""
(function() {{
  var d = {data_json};
  var ctx = document.getElementById('trendChart');
  if (!ctx || typeof Chart === 'undefined') return;
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: d.labels,
      datasets: [
        {{ label: 'HIGH',   data: d.high,   borderColor:'#c53030', backgroundColor:'rgba(197,48,48,0.1)',  tension:0.3, fill:true,  pointRadius:4 }},
        {{ label: 'MEDIUM', data: d.medium, borderColor:'#dd6b20', backgroundColor:'rgba(221,107,32,0.06)',tension:0.3, fill:false, pointRadius:3 }},
        {{ label: 'LOW',    data: d.low,    borderColor:'#a0aec0', backgroundColor:'transparent',           tension:0.3, fill:false, pointRadius:2 }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'top', labels: {{ font: {{ size: 12 }} }} }} }},
      scales: {{ y: {{ beginAtZero: true, ticks: {{ precision: 0, font: {{ size: 11 }} }} }}, x: {{ ticks: {{ font: {{ size: 10 }}, maxRotation: 45 }} }} }}
    }}
  }});
}})();""")

    if distribution:
        labels = [ACTIVITY_LABELS.get(d["activity_type"], d["activity_type"]) for d in distribution]
        totals = [d["total"] for d in distribution]
        colors = ACTIVITY_COLORS[:len(distribution)]
        data_json = json.dumps({"labels": labels, "data": totals, "colors": colors})
        scripts.append(f"""
(function() {{
  var d = {data_json};
  var ctx = document.getElementById('actChart');
  if (!ctx || typeof Chart === 'undefined') return;
  new Chart(ctx, {{
    type: 'doughnut',
    data: {{
      labels: d.labels,
      datasets: [{{ data: d.data, backgroundColor: d.colors, borderWidth: 2, borderColor: '#fff' }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ position: 'right', labels: {{ font: {{ size: 11 }}, boxWidth: 14 }} }},
        tooltip: {{ callbacks: {{ label: function(c) {{ return c.label + ': ' + c.parsed + '건'; }} }} }}
      }}
    }}
  }});
}})();""")

    return "\n".join(scripts)


# ---------------------------------------------------------------------------
# HTML 조립
# ---------------------------------------------------------------------------

def _build_full_html(
    stats: dict,
    high_articles: list,
    matrix: dict,
    trend: dict,
    distribution: list,
    brand_act: list,
    brand_high: list,
    brand_insights: dict,
    chartjs_src: str,
    days: int,
) -> str:
    has_chartjs = bool(chartjs_src)
    generated = datetime.utcnow() + timedelta(hours=9)
    generated_str = generated.strftime("%Y-%m-%d %H:%M KST")

    kpi_html          = _render_kpi_cards(stats)
    brands_list       = matrix.get("brands", [])
    act_types_list    = sorted({d["activity_type"] for d in distribution})
    filter_bar_html   = _render_filter_bar(brands_list, act_types_list)
    high_html         = _render_high_table(high_articles)
    heatmap_html      = _render_heatmap(matrix)
    brand_high_html   = _render_brand_high_ratio(brand_high)
    brand_act_html    = _render_brand_activity_bar(brand_act)
    insights_script   = _build_insights_script(brand_insights)
    trend_html        = _canvas_or_table_trend(trend, has_chartjs)
    activity_html     = _canvas_or_table_activity(distribution, has_chartjs)
    chart_scripts     = _build_chart_scripts(trend, distribution) if has_chartjs else ""
    stacked_script    = _build_stacked_bar_script(brand_act)

    chartjs_tag = f"<script>{chartjs_src}</script>" if has_chartjs else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K-뷰티 경쟁사 인텔리전스 — 최근 {days}일</title>
{chartjs_tag}
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", "Noto Sans KR", sans-serif;
  background: #eef2f7;
  color: #1a202c;
  font-size: 14px;
  line-height: 1.55;
}}
a {{ color: #2b6cb0; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* ── Header ── */
.page-header {{
  background: linear-gradient(135deg, #1a3a5c 0%, #2563a8 100%);
  color: #fff;
  padding: 20px 32px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}}
.page-header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }}
.page-header .meta {{ font-size: 12px; opacity: 0.75; }}

/* ── Layout ── */
.page-body {{ max-width: 1440px; margin: 0 auto; padding: 24px 24px 60px; }}
.section {{
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04);
  padding: 20px 24px;
  margin-bottom: 20px;
}}
.section-title {{
  font-size: 14px; font-weight: 700; color: #2d3748;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
  display: flex; align-items: baseline; gap: 8px;
}}
.section-sub {{ font-size: 12px; color: #718096; font-weight: 400; }}

/* ── KPI ── */
.kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }}
@media (max-width: 680px) {{ .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
.kpi-card {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px 18px;
  text-align: center;
}}
.kpi-value {{ font-size: 30px; font-weight: 800; line-height: 1.1; }}
.kpi-unit {{ font-size: 13px; font-weight: 400; margin-left: 2px; }}
.kpi-label {{
  font-size: 11px; color: #718096; margin-top: 5px;
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px;
}}

/* ── Tables ── */
.table-wrap {{ overflow-x: auto; }}
.data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.data-table th {{
  background: #edf2f7; color: #4a5568; font-weight: 600;
  padding: 8px 12px; text-align: left; white-space: nowrap;
  position: sticky; top: 0; z-index: 2;
}}
.data-table td {{ padding: 7px 12px; border-bottom: 1px solid #f0f4f8; vertical-align: top; }}
.data-table tbody .main-row:hover td {{ background: #f7fafc; }}
.main-row {{ cursor: pointer; }}
.main-row td {{ transition: background 0.12s; }}

/* ── Drilldown ── */
.detail-row.hidden {{ display: none; }}
.detail-box {{
  background: #f0f7ff;
  border-left: 3px solid #2b6cb0;
  padding: 10px 16px;
  border-radius: 0 6px 6px 0;
  margin: 2px 0;
}}
.detail-box p {{ margin-bottom: 5px; color: #2d3748; font-size: 13px; }}
.detail-box .note-line {{ color: #744210; }}
.detail-box .src-info {{ color: #718096; font-size: 11px; margin-top: 6px; }}
.detail-box .title-ko-line {{ color: #2b6cb0; font-size: 12px; margin-bottom: 4px; }}
.detail-box .note-line {{ color: #744210; }}
.body-orig {{ margin-top: 8px; }}
.body-orig summary {{ font-size: 11px; color: #718096; cursor: pointer; }}
.body-text {{ font-size: 11px; line-height: 1.5; color: #4a5568; background: #f7fafc;
  padding: 8px 10px; border-radius: 4px; margin-top: 6px;
  white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; }}

/* ── Tags ── */
.brand-tag {{
  background: #ebf4ff; color: #2b6cb0;
  padding: 2px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 700; white-space: nowrap;
}}
.act-tag {{
  background: #f0fff4; color: #276749;
  padding: 2px 8px; border-radius: 10px;
  font-size: 11px; white-space: nowrap;
}}
.date-cell {{ color: #718096; font-size: 12px; white-space: nowrap; }}
.flag-cell {{ white-space: nowrap; }}
.conf-cell {{ color: #718096; font-size: 12px; text-align: right; white-space: nowrap; }}
.title-cell {{ max-width: 320px; }}

/* ── Heatmap ── */
.heatmap-wrap {{ max-height: 420px; overflow: auto; }}
.heatmap-table th {{ position: sticky; top: 0; z-index: 2; }}
.heatmap-table .sticky-col {{
  position: sticky; left: 0;
  background: #edf2f7 !important; color: #4a5568 !important;
  z-index: 3; min-width: 110px;
}}
.heatmap-table thead .sticky-col {{ z-index: 4; }}
.heatmap-table td {{
  text-align: center; min-width: 44px; max-width: 60px;
  font-size: 12px; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.3);
}}
.brand-name {{ font-weight: 600; font-size: 12px; }}
.total-cell {{
  background: #edf2f7 !important; color: #2d3748 !important;
  font-weight: 700; border-left: 2px solid #e2e8f0;
  position: sticky; right: 0; z-index: 1;
}}
.total-row td {{
  background: #e2e8f0 !important; color: #2d3748 !important;
  font-weight: 700;
}}

/* ── Charts layout ── */
.charts-row {{ display: grid; grid-template-columns: 3fr 2fr; gap: 20px; }}
@media (max-width: 900px) {{ .charts-row {{ grid-template-columns: 1fr; }} }}
.chart-section {{
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
  padding: 20px 24px;
}}
.chart-container {{ position: relative; height: 270px; }}
.chart-sm {{ height: 250px; }}

.no-data {{ color: #a0aec0; font-style: italic; padding: 12px 0; }}

/* ── Filter bar ── */
.filter-bar {{
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
  padding: 12px 16px; background: #fff;
  border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 16px;
}}
.filter-group {{ display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }}
.filter-sep {{ width: 1px; height: 20px; background: #e2e8f0; margin: 0 4px; }}
.filter-label {{
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.6px; color: #a0aec0; margin-right: 2px; white-space: nowrap;
}}
.filter-pill {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 20px;
  padding: 3px 12px; font-size: 11px; font-weight: 500; color: #718096;
  cursor: pointer; transition: all 0.15s; white-space: nowrap; font-family: inherit;
}}
.filter-pill:hover {{ border-color: #2b6cb0; color: #2b6cb0; }}
.filter-pill.active {{ background: #1a3a5c; color: #fff; border-color: #1a3a5c; }}
.filter-pill.act-active {{ background: #2f855a; color: #fff; border-color: #2f855a; }}
.filter-count {{ font-size: 11px; color: #a0aec0; margin-left: 6px; white-space: nowrap; }}

/* ── Lower 2-col (heatmap + high ratio) ── */
.lower-row {{ display: grid; grid-template-columns: 1fr 320px; gap: 20px; margin-bottom: 20px; }}
@media (max-width: 900px) {{ .lower-row {{ grid-template-columns: 1fr; }} }}

/* ── Brand HIGH ratio ── */
.high-ratio-wrap {{ display: flex; flex-direction: column; gap: 12px; }}
.hr-row {{ display: flex; align-items: center; gap: 10px; }}
.hr-brand {{ font-size: 12px; font-weight: 600; color: #2d3748; min-width: 90px; white-space: nowrap; }}
.hr-bar-bg {{ flex: 1; height: 18px; background: #edf2f7; border-radius: 9px; overflow: hidden; }}
.hr-bar-fill {{ height: 100%; background: #c53030; border-radius: 9px; transition: width 0.6s ease; }}
.hr-badge {{ font-size: 11px; font-weight: 700; color: #c53030; min-width: 38px; text-align: right; }}
.hr-meta {{ font-size: 11px; color: #718096; white-space: nowrap; min-width: 60px; }}

/* ── Stacked bar ── */
.stacked-wrap {{ position: relative; }}
.legend-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin-top: 12px; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 11px; color: #718096; }}
.legend-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}

/* ── Drilldown panel ── */
.dd-overlay {{
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 200;
  display: none; backdrop-filter: blur(1px);
}}
.dd-panel {{
  position: fixed; top: 0; right: 0; width: 420px; max-width: 92vw;
  height: 100%; background: #fff; overflow-y: auto; z-index: 201;
  transform: translateX(100%); transition: transform 0.25s ease;
  box-shadow: -4px 0 24px rgba(0,0,0,0.12);
}}
.dd-panel.open {{ transform: translateX(0); }}
.dd-header {{
  position: sticky; top: 0; background: #1a3a5c; color: #fff;
  padding: 16px 18px; display: flex; justify-content: space-between;
  align-items: flex-start; gap: 12px;
}}
.dd-header h3 {{ font-size: 14px; font-weight: 700; margin: 0; }}
.dd-header p  {{ font-size: 11px; opacity: 0.6; margin: 3px 0 0; }}
.dd-close {{
  background: rgba(255,255,255,0.15); border: none; color: #fff;
  width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
  font-size: 16px; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}}
.dd-body {{ padding: 14px 18px; }}
.dd-empty {{ text-align: center; padding: 40px 20px; color: #718096; font-size: 13px; }}
.dd-item {{
  border: 1px solid #e2e8f0; border-radius: 5px; padding: 10px 12px;
  margin-bottom: 10px;
}}
.dd-item-top {{ display: flex; gap: 8px; align-items: center; margin-bottom: 5px; }}
.dd-date {{ font-size: 11px; color: #718096; white-space: nowrap; }}
.dd-act-chip {{
  font-size: 10px; font-weight: 700; padding: 2px 8px;
  border-radius: 10px; white-space: nowrap;
  background: #ebf4ff; color: #2b6cb0;
}}
.dd-title {{ font-size: 13px; color: #2d3748; line-height: 1.45; }}
.dd-link {{ display: inline-block; margin-top: 5px; font-size: 11px; color: #2b6cb0; }}
/* ── INSIGHT CARDS ── */
.insight-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.insight-card {{
  border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px;
  background: #fff; transition: border-color 0.15s, box-shadow 0.15s;
}}
.insight-card:hover {{ border-color: #0d9488; box-shadow: 0 2px 8px rgba(13,148,136,0.08); }}
.insight-card.pulse {{ border-color: #0d9488; box-shadow: 0 0 0 3px rgba(13,148,136,0.18); }}
.insight-hdr {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
.insight-brand {{ font-size: 14px; font-weight: 700; color: #1a202c; }}
.insight-badge {{
  font-size: 10px; font-weight: 700; padding: 2px 8px;
  border-radius: 10px; white-space: nowrap;
}}
.insight-badge-act  {{ color: #fff; }}
.insight-badge-high-hot  {{ background: #fee2e2; color: #dc2626; }}
.insight-badge-high-warm {{ background: #fef3c7; color: #d97706; }}
.insight-badge-high-low  {{ background: #f3f4f6; color: #6b7280; }}
.insight-strategy {{
  font-size: 12px; color: #2d3748; line-height: 1.55; margin-bottom: 10px;
  padding: 8px 10px; background: #f8fafc; border-radius: 5px;
  border-left: 3px solid #0d9488;
}}
.insight-markets {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }}
.insight-market-item {{ font-size: 11px; color: #718096; display: flex; align-items: center; gap: 3px; }}
.insight-market-cnt {{ font-weight: 700; color: #2d3748; }}
.insight-articles-hdr {{
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; color: #a0aec0; margin-bottom: 6px;
}}
.insight-art-row {{
  display: flex; align-items: flex-start; gap: 6px;
  padding: 5px 0; border-top: 1px solid #f0f0f0; font-size: 11px;
}}
.insight-art-imp {{
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 4px;
}}
.insight-art-title {{ flex: 1; color: #2d3748; line-height: 1.4; }}
.insight-art-meta  {{ color: #a0aec0; white-space: nowrap; font-size: 10px; }}
.insight-art-link  {{ color: #0d9488; font-size: 10px; white-space: nowrap; }}
</style>
</head>
<body>
<header class="page-header">
  <h1>📊 K-뷰티 경쟁사 인텔리전스</h1>
  <div class="meta">최근 {days}일 집계 &nbsp;|&nbsp; 생성: {_esc(generated_str)}</div>
</header>

<div class="page-body">

  <div class="section">
    <div class="section-title">요약 통계</div>
    {kpi_html}
  </div>

  {filter_bar_html}

  <div class="section">
    <div class="section-title">
      🚨 HIGH Importance 기사
      <span class="section-sub" id="high-count-label">{len(high_articles)}건 &mdash; 행 클릭 시 상세 펼침</span>
    </div>
    {high_html}
  </div>

  <div class="lower-row">
    <div class="section">
      <div class="section-title">
        브랜드 &times; 국가 분포 히트맵
        <span class="section-sub">셀 클릭 시 HIGH 기사 목록</span>
      </div>
      {heatmap_html}
    </div>
    <div class="section">
      <div class="section-title">브랜드별 HIGH 비중</div>
      {brand_high_html}
    </div>
  </div>

  <div class="section">
    <div class="section-title">
      브랜드별 활동 유형 구성
      <span class="section-sub">전략 포지셔닝 비교</span>
    </div>
    {brand_act_html}
    <div class="legend-row" id="stacked-legend"></div>
  </div>

  <!-- Brand Insight Cards (Claude API 자동생성) -->
  <div class="dashboard-card" id="insight-section">
    <div class="section-title">
      브랜드별 전략 인사이트
      <span class="section-sub">스택바 클릭 시 해당 브랜드로 이동</span>
    </div>
    <div class="insight-grid" id="insight-grid"></div>
  </div>

  <div class="charts-row">
    <div class="chart-section">
      <div class="section-title">주별 수집 트렌드</div>
      {trend_html}
    </div>
    <div class="chart-section">
      <div class="section-title">활동 유형 분포</div>
      {activity_html}
    </div>
  </div>

</div>

<!-- Drilldown panel -->
<div class="dd-overlay" id="dd-overlay" onclick="closeDrilldown()"></div>
<div class="dd-panel" id="dd-panel">
  <div class="dd-header">
    <div><h3 id="dd-title">—</h3><p id="dd-subtitle">HIGH importance 기사</p></div>
    <button class="dd-close" onclick="closeDrilldown()">✕</button>
  </div>
  <div class="dd-body" id="dd-body"></div>
</div>

<script>
// HIGH articles data for drilldown
var HIGH_DATA = {json.dumps([{{
  "brand": a["brand"], "country": a["country"],
  "date": _fmt_date(a["published_date"]),
  "act": ACTIVITY_LABELS.get(a["activity_type"], a["activity_type"]),
  "title": a.get("title_ko") or a["title"],
  "details": a["details"],
  "url": a["source_url"] or "",
}} for a in high_articles], ensure_ascii=False)};

function toggleRow(i) {{
  var row = document.getElementById('dr-' + i);
  if (row) row.classList.toggle('hidden');
}}

// ── Heatmap drilldown ──
function openHeatmapDrilldown(brand, country) {{
  var arts = HIGH_DATA.filter(function(a) {{ return a.brand === brand && a.country === country; }});
  document.getElementById('dd-title').textContent = brand + ' · ' + country;
  document.getElementById('dd-subtitle').textContent = 'HIGH importance 기사 ' + arts.length + '건';
  var body = document.getElementById('dd-body');
  if (!arts.length) {{
    body.innerHTML = '<div class="dd-empty">이 셀에 HIGH 기사 없음</div>';
  }} else {{
    body.innerHTML = arts.map(function(a) {{
      var link = a.url ? '<a class="dd-link" href="' + a.url + '" target="_blank" rel="noopener">원문 보기 ↗</a>' : '';
      return '<div class="dd-item">'
        + '<div class="dd-item-top"><span class="dd-date">' + a.date + '</span>'
        + '<span class="dd-act-chip">' + a.act + '</span></div>'
        + '<div class="dd-title">' + a.title + '</div>'
        + (a.details ? '<div style="font-size:12px;color:#718096;margin-top:4px;">' + a.details + '</div>' : '')
        + link + '</div>';
    }}).join('');
  }}
  document.getElementById('dd-panel').classList.add('open');
  document.getElementById('dd-overlay').style.display = 'block';
}}

function closeDrilldown() {{
  document.getElementById('dd-panel').classList.remove('open');
  document.getElementById('dd-overlay').style.display = 'none';
}}

// ── Filter ──
var _fBrand = 'all', _fAct = 'all';
function applyFilter() {{
  var visible = 0;
  document.querySelectorAll('#high-tbody tr').forEach(function(tr) {{
    var i = tr.dataset.i;
    if (i === undefined) return;
    var idx = parseInt(i);
    var rows_data = {json.dumps([{{"brand": a["brand"], "act": ACTIVITY_LABELS.get(a["activity_type"], a["activity_type"])}} for a in high_articles], ensure_ascii=False)};
    var a = rows_data[idx];
    if (!a) return;
    var show = (_fBrand === 'all' || a.brand === _fBrand) && (_fAct === 'all' || a.act === _fAct);
    if (tr.classList.contains('main-row')) {{
      tr.style.display = show ? '' : 'none';
      if (show) visible++;
    }} else {{
      tr.style.display = (show && !tr.classList.contains('hidden')) ? '' : 'none';
    }}
  }});
  var lbl = document.getElementById('high-count-label');
  if (lbl) lbl.textContent = visible + '건' + (_fBrand !== 'all' || _fAct !== 'all' ? ' (필터됨)' : '') + ' — 행 클릭 시 상세 펼침';
  document.querySelectorAll('.heatmap-table tbody tr').forEach(function(tr) {{
    var bc = tr.querySelector('.brand-name');
    if (!bc) return;
    tr.style.opacity = (_fBrand === 'all' || bc.textContent.trim() === _fBrand || bc.textContent === '합계') ? '1' : '0.35';
  }});
}}
document.addEventListener('DOMContentLoaded', function() {{
  var bf = document.getElementById('brand-filters');
  if (bf) bf.addEventListener('click', function(e) {{
    var pill = e.target.closest('.filter-pill');
    if (!pill) return;
    bf.querySelectorAll('.filter-pill').forEach(function(p) {{ p.classList.remove('active'); }});
    pill.classList.add('active');
    _fBrand = pill.dataset.brand;
    applyFilter();
  }});
  var af = document.getElementById('act-filters');
  if (af) af.addEventListener('click', function(e) {{
    var pill = e.target.closest('.filter-pill');
    if (!pill) return;
    af.querySelectorAll('.filter-pill').forEach(function(p) {{ p.classList.remove('active', 'act-active'); }});
    pill.classList.add(pill.dataset.act === 'all' ? 'active' : 'act-active');
    _fAct = pill.dataset.act;
    applyFilter();
  }});
}});

{chart_scripts}
{stacked_script}
{insights_script}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def generate_report(output_path: str = "rival_report.html", days: int = 30) -> str:
    """
    DB 조회 → self-contained HTML 대시보드 생성.

    Returns:
        생성된 파일의 절대 경로
    """
    session = get_session()
    try:
        stats         = get_collection_stats(session, days=days)
        high_articles = get_high_articles(session, days=days)
        matrix        = get_brand_country_matrix(session, days=days)
        trend         = get_weekly_trend(session, weeks=12)
        distribution  = get_activity_distribution(session, days=days)
        brand_act     = get_brand_activity_matrix(session, days=days)
        brand_high    = get_brand_high_ratio(session, days=days)
        insights_raw  = get_brand_insights_raw(session, days=days)
    finally:
        session.close()

    # Claude API로 브랜드별 전략 요약 생성
    brand_insights: dict = {}
    for brand, data in insights_raw.items():
        summary = generate_brand_strategy_summary(brand, data.get("articles", []))
        brand_insights[brand] = {
            "top_act":       data["top_act"],
            "top_pct":       data["top_pct"],
            "high_pct":      data["high_pct"],
            "strategy":      summary,
            "top_countries": data["top_countries"],
            "key_articles":  data.get("articles", [])[:3],
        }

    chartjs_src  = _get_chartjs()
    html_content = _build_full_html(
        stats, high_articles, matrix, trend, distribution,
        brand_act, brand_high, brand_insights, chartjs_src, days
    )

    abs_path = os.path.abspath(output_path)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info("보고서 생성 완료: %s (%.1f KB)", abs_path, len(html_content) / 1024)
    return abs_path
