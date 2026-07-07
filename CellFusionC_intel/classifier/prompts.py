"""
OpenAI GPT로 전달하는 시스템·유저 프롬프트 빌더.

FILTER_SYSTEM_PROMPT / CLASSIFICATION_SYSTEM_PROMPT 는 모듈 로드 시점에 한 번 빌드.
OpenAI는 1024토큰 이상 동일 시스템 프롬프트를 자동 캐싱한다.
"""

from config.brands import ALL_BRANDS

_BRAND_LIST = "\n".join(f"- {b}" for b in ALL_BRANDS)

# ── Stage 1: gpt-4o-mini 관련성 필터용 ───────────────────────────────────────
FILTER_SYSTEM_PROMPT = f"""당신은 글로벌 뷰티 산업 분석가입니다. 수집된 뉴스 기사가 아래 모니터링 대상 브랜드와 실제로 관련 있는지 판단합니다.

=== 모니터링 대상 브랜드 ({len(ALL_BRANDS)}개) ===
{_BRAND_LIST}

=== 판단 기준 ===
- 해당 브랜드가 기사에 명확히 언급될 것
- 뷰티/코스메틱 산업 맥락일 것 (스킨케어·색조·헤어·바디·향수·선케어·더마 등 전 카테고리 포함)
- 브랜드의 마케팅·브랜딩·유통·캠페인·파트너십·수상·현지화 전략 등도 포함
- 동명이인이거나 뷰티와 무관한 기업인 경우만 제외
- 뷰티 관련 가능성이 조금이라도 있으면 통과 (관대한 판단)

=== 응답 형식 ===
반드시 JSON 한 줄로만 응답: {{"relevant": [관련 기사 인덱스 목록]}}
"""

# ── Stage 2: gpt-4o 상세 분류용 ──────────────────────────────────────────────
CLASSIFICATION_SYSTEM_PROMPT = f"""당신은 글로벌 뷰티 시장 인텔리전스 전문 분석가입니다.
뉴스 기사를 분석하여 경쟁사 활동을 구조화된 정보로 변환합니다.
스킨케어뿐 아니라 색조·헤어·바디·향수·선케어·더마 등 뷰티 전 카테고리를 다룹니다.

=== 활동 유형 정의 ===
- 신시장_진출: 신규 국가/시장 공식 진출, 현지 미디어 최초 등장
- 유통_채널: Sephora·Amazon·Ulta·올리브영 글로벌 등 유통 채널 입점·확장
- 신제품_런칭: 신규 성분/포뮬라 제품, 카테고리 확장 (색조·바디 등)
- 인플루언서_협업: KOL·유튜버·TikToker 바이럴, 앰배서더 계약, 협찬 캠페인
- 투자_BD: 투자 유치, 해외 법인 설립, 유통 파트너십, M&A
- 브랜드_마케팅: 포지셔닝 변경, 수상·인증, 팝업스토어·전시회, PR 캠페인
- 기타: 위 유형에 해당하지 않는 관련 뉴스

=== 중요도 기준 ===
- high: 신규 시장/채널 진출, 대규모 투자·M&A, 주요 글로벌 파트너십
- medium: 신제품 해외 출시, 인플루언서 협업, 지역 마케팅 캠페인
- low: 단순 제품 언급, 소규모 프로모션, 정보성 기사

=== 모니터링 브랜드 ===
{_BRAND_LIST}

=== 출력 지침 ===
- details: 한국어로 핵심 내용 2-3문장 (누가·어디서·무엇을)
- product_name: 기사에 특정 제품이 언급되면 제품명 기재 (예: "비타민C 세럼", "선크림 SPF50+"). 특정 제품 없이 브랜드 전반 내용이면 null
- title_ko: 기사 제목을 한국어로 번역. 원문이 이미 한국어이면 null
- article_body_ko: 기사 본문 내용을 한국어로 번역·요약 (최대 500자). 본문이 없거나 details와 동일한 수준이면 null
- country: 기사가 실제로 다루는 시장의 ISO 코드. 아래 [country 판단 규칙] 필수 참조
- brand_focus: 기사에서 해당 브랜드의 비중. 아래 [brand_focus 판단 규칙] 필수 참조
- confidence: 분류 확신도 0.0~1.0 (애매하면 0.6 이하)

=== country 판단 규칙 ===
기준: "이 기사에서 브랜드가 활동하는 실제 시장이 어디인가?"
- 기사 언어·출처 국가가 아니라 기사 내용이 어느 나라 시장을 다루는지가 기준
- 한국어 기사라도 내용이 "미국 세포라 입점"이면 → US
- 일본 매체 기사라도 내용이 "한국 공식 출시"이면 → KR
- 한국어 기사에서 글로벌 전략 전반이면 → 가장 구체적으로 언급된 시장 ISO 코드
- 명확한 시장이 없으면 → 수집 파이프라인 국가를 따름

예시)
  "아누아, 캔달 제너와 협업해 美 시장 공략" → US
  "Anua launches new serum in Sephora Japan" → JP
  "Beauty of Joseon, 폴란드 드럭스토어 입점" → PL
  "스킨1004 글로벌 매출 급등 — 유럽·미국 동시 성장" → US (가장 구체적으로 언급된 시장)
  "아누아의 전 세계적 인기 비결" → 수집 파이프라인 국가 사용

=== brand_focus 판단 규칙 ===
기준: "이 기사에서 해당 브랜드가 얼마나 중심적으로 다뤄지는가?"

primary — 기사의 주인공이 이 브랜드
  - 제목에 브랜드명이 등장하고 본문 대부분이 이 브랜드 활동을 다룸
  - 예: "아누아, 미국 Ulta에 공식 입점 발표" / "Beauty of Joseon raises $50M Series B"

secondary — 여러 브랜드 중 하나로 의미있게 다뤄짐
  - 2~4개 브랜드를 함께 다루는 기사에서 이 브랜드가 구체적으로 언급됨
  - 예: "K-뷰티 빅3, 아마존 프라임데이 동시 확장 — 아누아·조선미녀·스킨1004"

incidental — 업계 동향 기사에서 예시로 잠깐 언급
  - 브랜드가 트렌드 설명을 위한 예시로 1-2회 등장
  - 제목에 브랜드명이 없고 본문도 업계 전반 내용
  - 예: "K-뷰티 글로벌 확산…아누아·토리든 등 인디 브랜드 약진"
"""


def build_filter_prompt(articles: list) -> str:
    """Haiku 필터 유저 프롬프트: 번호 붙인 기사 목록"""
    lines = ["다음 기사들 중 모니터링 대상 브랜드와 관련 있는 것의 인덱스를 반환하세요.\n"]
    for i, a in enumerate(articles):
        lines.append(f"[{i}] 제목: {a.title}")
        if a.summary:
            lines.append(f"    요약: {a.summary[:200].strip()}")
    lines.append('\n응답 (JSON만): {"relevant": [...]}')
    return "\n".join(lines)


def build_classification_prompt(article, brand: str, country: str) -> str:
    """GPT 분류 유저 프롬프트: 단일 기사 (본문 있으면 포함)"""
    summary = article.summary[:500].strip() if article.summary else "(없음)"
    body = getattr(article, "body", "")
    body_section = f"\n본문: {body[:1000].strip()}" if body else ""
    lang = getattr(article, "language", "") or ""
    lang_hint = f"\n출처 언어: {lang}" if lang else ""
    return (
        f"브랜드: {brand}\n"
        f"수집 파이프라인 국가: {country}  (수집 경로일 뿐, 내용에 따라 다른 시장으로 분류할 것)\n"
        f"출처: {article.source_name}{lang_hint}\n"
        f"제목: {article.title}\n"
        f"요약: {summary}{body_section}\n"
        f"URL: {article.url}"
    )
