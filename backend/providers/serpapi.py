"""SerpApi 数据源 —— Google Flights 引擎（真实价格）。

免费套餐：100 次搜索/月（相同参数的重复请求走 SerpApi 缓存，不计费）。
注册最简单：serpapi.com 用 Google/GitHub 账号登录即可拿 API Key，无需邮箱验证。

本 provider 使用两个引擎：
- google_flights_calendar：一次调用返回日期区间内每天的最低票价（search_dates，
  去程+返程共 2 次调用完成一次组合搜索）
- google_flights：返回指定日期组合的具体航班报价（search_round_trip）

注意：日历引擎不支持"仅直飞"过滤（接口无此参数），non_stop 在日期粒度上会被忽略。
机场联想使用内置机场列表（main.py 转发给 mock），不消耗额度。
"""
from __future__ import annotations

from typing import Optional

import httpx

from cache import TTLCache
from .base import DayPrice, FlightOffer, Provider, ProviderError, Segment


class SerpApiProvider(Provider):
    name = "serpapi"

    def __init__(self, api_key: str, cache: Optional[TTLCache] = None):
        self._api_key = api_key
        self._cache = cache or TTLCache()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    async def _search(self, params: dict, ttl: int) -> dict:
        params = {**params, "api_key": self._api_key, "output": "json"}
        cache_key = "serpapi|" + "|".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key")
        hit = self._cache.get(cache_key)
        if hit is not None:
            return hit

        resp = await self._client.get("https://serpapi.com/search", params=params)
        if resp.status_code >= 400:
            raise ProviderError(f"SerpApi 请求失败 (HTTP {resp.status_code})：{resp.text[:300]}")
        try:
            data = resp.json()
        except Exception:
            raise ProviderError(f"SerpApi 返回了无法解析的响应：{resp.text[:300]}")
        if isinstance(data, dict) and data.get("error"):
            raise ProviderError(f"SerpApi 错误：{data['error']}")
        self._cache.set(cache_key, data, ttl)
        return data

    async def search_dates(self, origin, destination, date_from, date_to, adults=1, currency="CNY", non_stop=False):
        # google_flights_calendar 的 type=2 为单程：一次调用返回区间内每天最低价
        data = await self._search({
            "engine": "google_flights_calendar",
            "departure_id": origin,
            "arrival_id": destination,
            "date_range_start": date_from,
            "date_range_end": date_to,
            "type": "2",
            "currency": currency,
            "adults": adults,
            "hl": "zh-cn",
        }, ttl=1800)

        result: list[DayPrice] = []
        for item in data.get("prices") or []:
            d = item.get("outbound_date")
            price = item.get("price")
            if not d or price is None:
                continue
            result.append(DayPrice(date=d, price=float(price), currency=currency))
        return result

    async def search_round_trip(self, origin, destination, departure_date, return_date=None, adults=1, currency="CNY", max_results=10):
        # SerpApi 往返搜索的 flights[] 只返回去程航段（价格是往返总价），
        # 因此这里按两个单程搜索分别取航段与分段价，再组合报价，总价 = 去程 + 返程。
        outbound = await self._oneway_offers(origin, destination, departure_date, adults, currency, max_results)
        if not return_date:
            return [FlightOffer(price_total=p, currency=currency, outbound=segs) for p, segs in outbound]

        inbound = await self._oneway_offers(destination, origin, return_date, adults, currency, 3)
        if not inbound:
            return [FlightOffer(price_total=p, currency=currency, outbound=segs) for p, segs in outbound]

        out_top = outbound[: min(4, len(outbound))]
        in_top = inbound[: min(2, len(inbound))]
        pairs: list[FlightOffer] = []
        for op, osegs in out_top:
            for ip, isegs in in_top:
                pairs.append(FlightOffer(
                    price_total=round(op + ip, 2),
                    currency=currency,
                    outbound=osegs,
                    inbound=isegs,
                    outbound_price=op,
                    inbound_price=ip,
                ))
        pairs.sort(key=lambda o: o.price_total)
        return pairs[:max_results]

    async def _oneway_offers(self, origin, destination, d, adults, currency, limit):
        """单程搜索：返回 [(价格, 航段列表)]，按价格升序。"""
        data = await self._search({
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": d,
            "type": "2",
            "currency": currency,
            "adults": adults,
            "hl": "zh-cn",
            "sort_by": "2",  # 按价格排序
        }, ttl=600)

        result: list[tuple[float, list[Segment]]] = []
        raw = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        for item in raw:
            price = item.get("price")
            legs = item.get("flights") or []
            if price is None or not legs:
                continue
            result.append((float(price), [self._parse_leg(l) for l in legs]))
        result.sort(key=lambda x: x[0])
        return result[:limit]

    @staticmethod
    def _parse_leg(leg: dict) -> Segment:
        dep = leg.get("departure_airport") or {}
        arr = leg.get("arrival_airport") or {}
        fn = (leg.get("flight_number") or "").strip()
        code = fn.split(" ")[0] if fn else ""
        return Segment(
            carrier_code=code or "?",
            carrier_name=leg.get("airline") or code or "?",
            flight_number=fn,
            departure_iata=dep.get("id", ""),
            departure_at=dep.get("time", ""),
            arrival_iata=arr.get("id", ""),
            arrival_at=arr.get("time", ""),
            duration_minutes=int(leg.get("duration") or 0),
        )

    async def search_airports(self, query, limit=10):
        raise ProviderError("SerpApi 数据源的机场联想由内置机场列表提供（不消耗额度），不应调用本方法。")
