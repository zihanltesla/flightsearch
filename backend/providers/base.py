"""Provider 抽象接口：新增数据源只需实现本接口并在 main.py 中注册。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Airport:
    iata: str
    name: str
    city: str
    country: str


@dataclass
class DayPrice:
    """某一天的最低票价（低价日历粒度）。"""
    date: str
    price: float
    currency: str
    stops: Optional[int] = None  # 未知时为 None（如 Amadeus 低价日历接口）


@dataclass
class Segment:
    carrier_code: str
    carrier_name: str
    flight_number: str
    departure_iata: str
    departure_at: str
    arrival_iata: str
    arrival_at: str
    duration_minutes: int


@dataclass
class FlightOffer:
    price_total: float
    currency: str
    outbound: list[Segment] = field(default_factory=list)
    inbound: list[Segment] = field(default_factory=list)
    outbound_price: Optional[float] = None  # 单程分段价（SerpApi 等按两段单程组合的报价）
    inbound_price: Optional[float] = None


class ProviderError(Exception):
    """数据源错误，message 会直接展示给前端用户。"""


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    async def search_dates(
        self,
        origin: str,
        destination: str,
        date_from: str,
        date_to: str,
        adults: int = 1,
        currency: str = "CNY",
        non_stop: bool = False,
    ) -> list[DayPrice]:
        """查询 [date_from, date_to] 区间内每天的最低单程票价。"""

    @abstractmethod
    async def search_round_trip(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        currency: str = "CNY",
        max_results: int = 10,
    ) -> list[FlightOffer]:
        """查询指定日期的具体航班报价（return_date 为空即单程）。"""

    @abstractmethod
    async def search_airports(self, query: str, limit: int = 10) -> list[Airport]:
        """机场/城市联想搜索。"""
