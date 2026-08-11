"""Base class for keyword volume clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class KeywordVolumeResult:
    keyword: str
    search_volume: Optional[int] = None
    cpc: Optional[float] = None
    competition: Optional[float] = None
    error: Optional[str] = None
    monthly_searches: Optional[list] = None  # [{year, month, search_volume}, ...]


class KeywordVolumeClient(ABC):
    @abstractmethod
    async def get_volume(
        self,
        keywords: List[str],
        location_code: Optional[int] = None,
        language_code: Optional[str] = None,
    ) -> List[KeywordVolumeResult]:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass
