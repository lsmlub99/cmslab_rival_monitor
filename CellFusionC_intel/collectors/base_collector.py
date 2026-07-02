from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RawArticle:
    title: str
    url: str
    published: datetime
    summary: str
    source_name: str
    language: str
    brand_hint: Optional[str] = None
    country_hint: Optional[str] = None
    body: str = ""  # 기사 본문 (URL fetch 후 채워짐, 없으면 빈 문자열)


class BaseCollector(ABC):
    collector_type: str = "base"

    @abstractmethod
    def collect(self, brand: str, country: str) -> list[RawArticle]:
        """브랜드 + 국가 조합으로 기사 수집"""
        ...
