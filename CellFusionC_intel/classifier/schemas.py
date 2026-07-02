from typing import Literal, Optional

from pydantic import BaseModel, Field


class NewsClassification(BaseModel):
    brand: str = Field(description="브랜드명 (원본 영문)")
    country: str = Field(description="기사 관련 ISO 국가 코드 (예: US, PL, TH)")
    activity_type: Literal[
        "신시장_진출",
        "유통_채널",
        "신제품_런칭",
        "인플루언서_협업",
        "투자_BD",
        "브랜드_마케팅",
        "기타",
    ] = Field(description="활동 유형")
    importance: Literal["high", "medium", "low"] = Field(description="중요도")
    details: str = Field(description="핵심 내용 2-3문장 (한국어)")
    product_name: Optional[str] = Field(default=None, description="기사에서 언급된 특정 제품명 (없으면 null)")
    title_ko: Optional[str] = Field(default=None, description="기사 제목의 한국어 번역 (원문이 이미 한국어면 null)")
    article_body_ko: Optional[str] = Field(default=None, description="기사 본문의 한국어 번역 요약 (최대 500자, 본문 없으면 null)")
    confidence: float = Field(ge=0.0, le=1.0, description="분류 신뢰도 0.0~1.0")
    note: Optional[str] = Field(default=None, description="추가 메모 또는 불확실 사항")
