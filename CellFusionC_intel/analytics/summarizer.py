"""
브랜드 전략 인사이트 요약 — OpenAI API (gpt-4o-mini)
"""

import logging
import os

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# 자사 프로필 — 인사이트를 우리(씨엠에스랩) 관점으로 튜닝하기 위한 컨텍스트
CMS_PROFILE = """[우리 회사]
- 씨엠에스랩(CMS Lab): 병의원 기반 20년 노하우의 글로벌 메디컬 코스메틱 기업.
- 대표 브랜드: 셀퓨전씨(CellFusionC) — 클리니컬 더마 브랜드, 핵심은 '선케어(썬-에이징/햇빛케어)' 전문.
  데일리 선크림부터 건강기능식품까지 전방위 선케어.
- 강점·현황: 올리브영 인기 선크림, 베트남 자외선차단 1위·중국 선케어 1위, 일본 버라이어티샵 입점.
- 포지셔닝: 더마/메디컬 '선케어 스페셜리스트' (매스 K-뷰티가 아닌 전문성·임상 기반)."""

_ACT_LABEL = {
    "신시장_진출": "신시장 진출", "유통_채널": "유통 채널", "신제품_런칭": "신제품 런칭",
    "인플루언서_협업": "인플루언서 협업", "투자_BD": "투자·BD", "브랜드_마케팅": "브랜드 마케팅",
    "실적_공시": "실적·공시", "기타": "기타",
}


def generate_brand_strategy_summary(brand: str, articles: list) -> str:
    """HIGH+MEDIUM 기사 → 분석적 전략 인사이트 (2섹션, 한국어).

    ### 전략 요약 / ### 관전 포인트 형식. 프론트가 '### 라벨'로 분할 렌더.
    articles: [{imp, act, title_ko, details, date}, ...]
    """
    if not articles:
        return f"### 전략 요약\n{brand}의 최근 주목할 만한 활동이 없습니다."

    article_lines = "\n".join(
        f"- [{a['imp'].upper()}] {a.get('title_ko','')} / {a.get('details','')[:140]} ({a.get('act','')}, {a.get('date','')})"
        for a in articles
        if a.get("title_ko") or a.get("details")
    )
    if not article_lines:
        return _fallback_from_data(brand, articles)

    prompt = f"""당신은 씨엠에스랩(더마 선케어 브랜드 '셀퓨전씨' 운영)의 경쟁사 인텔리전스 분석가입니다.
아래는 경쟁 브랜드 **{brand}**의 최근 기사(여러 시장 종합)입니다:

{article_lines}

{CMS_PROFILE}

이 브랜드의 움직임을 **날카롭게** 분석하세요. 뭉툭한 서술("~하고 있다", "경쟁력을 강화 중") 절대 금지.
반드시 아래 2개 섹션 형식으로 (머리말은 `### `로 시작):

### 전략 요약
{brand}의 핵심 전략을 관통하는 **한 문장 결론 + 근거 1문장**. 구체 사실(채널명·국가·파트너·수치)로 못박을 것. 여러 활동이면 그 밑에 깔린 하나의 의도로 꿰어라.

### 관전 포인트
셀퓨전씨 입장에서의 **날 선 시사점** 1~2문장. 다음 중 최소 하나를 명시:
(a) 우리와 겹치는 지점(선케어·더마·해외시장 특히 베트남/중국/일본)이 있으면 위협 강도,
(b) 우리가 취할 구체적 대응/선점 포인트,
(c) 다음에 반드시 주시할 시그널.
일반론 말고 이 브랜드·이 상황에 특정된 조언만."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=450,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("empty response from gpt-4o-mini")
        return content
    except Exception as e:
        logger.warning("브랜드 요약 생성 실패 [%s]: %s", brand, e)
        return _fallback_from_data(brand, articles)


_COUNTRY_KO = {
    "US": "미국", "JP": "일본", "KR": "한국", "CN": "중국", "GB": "영국",
    "PL": "폴란드", "SG": "싱가포르", "TH": "태국", "CA": "캐나다", "AU": "호주",
    "DE": "독일", "FR": "프랑스", "ID": "인도네시아", "MY": "말레이시아",
    "VN": "베트남", "PH": "필리핀", "IT": "이탈리아",
}


def generate_brand_country_summary(brand: str, country: str, articles: list) -> str:
    """특정 브랜드가 특정 국가에서 벌이는 활동 → 구조화된 전략 리딩.

    3개 섹션(### 핵심 행보 / ### 근거 / ### 전략적 의도)으로 반환.
    프론트가 '### 라벨' 기준으로 분할해 소제목 블록으로 렌더링.

    articles: [{imp, act, title_ko, details, date}, ...] (해당 브랜드×국가만)
    """
    country_ko = _COUNTRY_KO.get(country, country)
    if not articles:
        return f"### 핵심 행보\n{brand}의 {country_ko} 관련 주목할 만한 활동이 아직 없습니다."

    article_lines = "\n".join(
        f"- [{a['imp'].upper()}] {a.get('title_ko','')} / {a.get('details','')[:160]} ({a.get('act','')}, {a.get('date','')})"
        for a in articles
        if a.get("title_ko") or a.get("details")
    )
    if not article_lines:
        return _fallback_from_data(brand, articles)

    prompt = f"""당신은 K-뷰티 경쟁사 인텔리전스 분석가입니다.
다음은 브랜드 **{brand}**의 **{country_ko}** 시장 관련 최근 기사입니다:

{article_lines}

위 기사들을 종합해 {brand}가 **{country_ko}에서** 무엇을 어떻게 하고 있으며 그 속셈(전략적 의도)이 무엇인지 분석하세요.
아래 3개 섹션 형식을 **정확히** 지켜서 작성하세요 (각 섹션 머리말은 반드시 `### `로 시작):

### 핵심 행보
{country_ko} 시장에서의 구체적 움직임을 2~3문장으로. 반드시 기사의 **구체적 사실**(유통 채널명, 파트너·인플루언서 이름, 진출 방식, 제품, 수치·시점)을 명시. 여러 건이면 흐름/순서로 엮을 것.

### 근거
위 판단의 핵심 근거가 된 기사 1~3건을 "- 제목 요지 (날짜)" 형식으로 나열. 각 줄에 왜 중요한지 한 구절 덧붙일 것.

### 전략적 의도
{brand}가 {country_ko}에서 노리는 것 — 사업 확장 방식(유통 확대? 브랜드 인지도? 특정 세그먼트 공략?)과 다음 수순 예측을 2~3문장으로. "글로벌 공략 중" 같은 뻔한 말 금지, 이 브랜드·이 시장에 특정된 해석만."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=600,
            temperature=0.35,
            messages=[{"role": "user", "content": prompt}],
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("empty response from gpt-4o-mini")
        return content
    except Exception as e:
        logger.warning("브랜드×국가 요약 생성 실패 [%s/%s]: %s", brand, country, e)
        return _fallback_from_data(brand, articles)


def generate_market_overview(brand_insights_raw: dict) -> str:
    """전 브랜드 데이터 종합 → 시장 인사이트 + 셀퓨전씨 맞춤 조언 (구조화).

    brand_insights_raw: {brand: {top_act, high_pct, articles:[{imp,act,title_ko,details,date}], ...}}
    반환: ### 시장 흐름 / ### 핵심 위협·기회 / ### 셀퓨전씨 액션
    """
    if not brand_insights_raw:
        return "### 시장 흐름\n최근 종합할 만한 경쟁사 활동이 없습니다."

    # 활동유형 집계
    act_tally: dict = {}
    # 브랜드별 HIGH 기사 digest (HIGH 우선, 브랜드당 최대 2건, 전체 최대 22건)
    lines: list = []
    for brand, d in brand_insights_raw.items():
        for a in (d.get("articles") or []):
            act = a.get("act", "")
            if act:
                act_tally[act] = act_tally.get(act, 0) + 1
        highs = [a for a in (d.get("articles") or []) if a.get("imp") == "high"][:2]
        for a in highs:
            t = a.get("title_ko") or (a.get("details") or "")[:70]
            if t:
                lines.append(f"- [{brand}] {t} ({_ACT_LABEL.get(a.get('act',''), a.get('act',''))}, {a.get('date','')})")
    lines = lines[:22]
    if not lines:
        return "### 시장 흐름\n최근 종합할 만한 HIGH 경쟁 활동이 없습니다."

    act_rank = sorted(act_tally.items(), key=lambda x: -x[1])
    act_str = ", ".join(f"{_ACT_LABEL.get(k,k)} {v}건" for k, v in act_rank[:5])

    prompt = f"""당신은 씨엠에스랩의 수석 경쟁 전략 애널리스트입니다.
아래는 최근 모니터링된 K-뷰티 경쟁 브랜드들의 주요 활동(HIGH)입니다:

{chr(10).join(lines)}

[활동유형 분포] {act_str}

{CMS_PROFILE}

위 경쟁 동향 **전체를 종합**해 시장을 읽고, 우리(셀퓨전씨)에게 맞는 실행 조언을 주세요.
아래 3개 섹션 형식을 **정확히** 지키세요 (머리말은 `### `로 시작):

### 시장 흐름
지금 K-뷰티 경쟁 시장을 관통하는 **핵심 흐름 2~3가지**를 구체적 근거(브랜드·채널·시장)와 함께. 어떤 유형의 움직임이 몰리는지, 어디로 확장하는지.

### 핵심 위협·기회
셀퓨전씨(더마 선케어, 베트남·중국·일본 강세)에 **특히 중요한** 경쟁 움직임을 위협/기회로 구분해 짚기. 선케어·더마 인접 영역, 우리 주력 시장과 겹치는 경쟁사 행보를 우선.

### 셀퓨전씨 액션
우리가 당장 검토·실행할 만한 **구체적 액션 2~3개**를 불릿(-)으로. 각 액션은 위 흐름/위협에 직접 연결되고 실행 가능해야 함(예: 특정 채널 선점, 특정 시장 선케어 라인 강화, 특정 경쟁사 대응). 일반론 금지."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=800,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("empty market overview")
        return content
    except Exception as e:
        logger.warning("시장 종합 인사이트 생성 실패: %s", e)
        return ""


def _fallback_from_data(brand: str, articles: list) -> str:
    """AI 실패 시 실제 기사 내용 기반 fallback."""
    # HIGH 우선, 없으면 MEDIUM
    key = next((a for a in articles if a.get("imp") == "high" and (a.get("details") or a.get("title_ko"))), None)
    if not key:
        key = next((a for a in articles if a.get("details") or a.get("title_ko")), None)
    if not key:
        return f"{brand}의 최근 주목할 만한 활동이 없습니다."

    first = (key.get("details") or key.get("title_ko") or "").strip()
    # 두 번째 다른 기사
    second = next(
        (a for a in articles if a is not key and (a.get("details") or a.get("title_ko"))),
        None,
    )
    second_text = ""
    if second:
        s = (second.get("details") or second.get("title_ko") or "").strip()
        if s:
            second_text = f" 아울러 {s}"

    return f"{first}{second_text}"
