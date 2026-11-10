"""Amadeus Self-Service API 数据源（免费测试环境，真实价格）。

免费注册密钥:
  1. https://developers.amadeus.com 注册并登录
  2. My Self-Service Workspace -> My Apps -> Create new app
  3. 环境选 Test，把 API Key / API Secret 填入 backend/.env 并重启后端
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

import httpx

from cache import TTLCache
from .base import Airport, DayPrice, FlightOffer, Provider, ProviderError, Segment

_TOKEN_TTL = 1500  # 官方 1800 秒，留余量提前刷新


def _parse_duration(iso: str) -> int:
    """ISO 8601 时长 (PT10H30M / P1DT2H) -> 分钟。"""
    if not iso:
        return 0
    m = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$", iso)
    if not m:
        return 0
    d, h, mi = (int(g or 0) for g in m.groups())
    return d * 1440 + h * 60 + mi


class AmadeusProvider(Provider):
    name = "amadeus"

    def __init__(self, client_id: str, client_secret: str, env: str = "test", cache: Optional[TTLCache] = None):
        self._base = "https://test.api.amadeus.com" if env != "production" else "https://api.amadeus.com"
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache = cache or TTLCache()
        self._token: Optional[str] = None
        self._token_exp = 0.0
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    # ---------- 认证 ----------

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp:
            return self._token
        resp = await self._client.post(
            f"{self._base}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise ProviderError(f"Amadeus 认证失败 (HTTP {resp.status_code})：{resp.text[:300]}")
        body = resp.json()
        self._token = body.get("access_token")
        expires = int(body.get("expires_in") or 1800)
        self._token_exp = time.time() + max(expires - 60, 60)
        return self._token

    async def _get(self, path: str, params: dict, ttl: int) -> Any:
        key = f"amadeus|{path}|{json.dumps(params, sort_keys=True, default=str)}"
        hit = self._cache.get(key)
        if hit is not None:
            return hit

        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.get(f"{self._base}{path}", params=params, headers=headers)
        if resp.status_code == 401:  # token 过期，刷新后重试一次
            self._token = None
            token = await self._get_token()
            resp = await self._client.get(
                f"{self._base}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
        if resp.status_code >= 400:
            raise ProviderError(self._error_text(resp))

        data = resp.json()
        self._cache.set(key, data, ttl)
        return data

    @staticmethod
    def _error_text(resp) -> str:
        detail = ""
        try:
            body = resp.json()
            errors = body.get("errors") or []
            detail = "；".join(
                f"{e.get('title', '')}: {e.get('detail', '')}" for e in errors if isinstance(e, dict)
            )
        except Exception:
            pass
        return f"Amadeus API 错误 (HTTP {resp.status_code})：{detail or resp.text[:300]}"

    # ---------- Provider 接口 ----------

    async def search_dates(self, origin, destination, date_from, date_to, adults=1, currency="CNY", non_stop=False):
        # 低价日历接口不支持 adults/currencyCode 参数；返回的是航线本地币种，
        # 由 main.py 统一换算为展示货币。
        params = {
            "origin": origin,
            "destination": destination,
            "departureDate": f"{date_from},{date_to}",
            "oneWay": "true",
            "viewBy": "DATE",
        }
        if non_stop:
            params["nonStop"] = "true"
        data = await self._get("/v1/shopping/flight-dates", params, ttl=900)

        meta_currency = ((data.get("meta") or {}).get("currency") or "EUR").upper()
        result: list[DayPrice] = []
        for item in data.get("data") or []:
            if item.get("type") != "flight-date":
                continue
            day = item.get("departureDate")
            price_obj = item.get("price") or {}
            total = price_obj.get("total")
            if not day or total is None:
                continue
            result.append(DayPrice(
                date=day,
                price=float(total),
                currency=(price_obj.get("currency") or meta_currency).upper(),
            ))
        return result

    async def search_round_trip(self, origin, destination, departure_date, return_date=None, adults=1, currency="CNY", max_results=10):
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": adults,
            "currencyCode": currency,
            "max": min(max_results, 50),
        }
        if return_date:
            params["returnDate"] = return_date
        data = await self._get("/v2/shopping/flight-offers", params, ttl=600)

        dictionaries = data.get("dictionaries") or {}
        carriers = dictionaries.get("carriers") or {}

        offers: list[FlightOffer] = []
        for item in data.get("data") or []:
            if item.get("type") != "flight-offer":
                continue
            price = item.get("price") or {}
            total = price.get("grandTotal") or price.get("total")
            if total is None:
                continue
            itineraries = item.get("itineraries") or []
            out_segs: list[Segment] = []
            in_segs: list[Segment] = []
            for i, itin in enumerate(itineraries[:2]):
                segs = [self._parse_segment(s, carriers) for s in (itin.get("segments") or [])]
                if i == 0:
                    out_segs = segs
                else:
                    in_segs = segs
            offers.append(FlightOffer(
                price_total=float(total),
                currency=(price.get("currency") or currency).upper(),
                outbound=out_segs,
                inbound=in_segs,
            ))
        return offers

    @staticmethod
    def _parse_segment(s: dict, carriers: dict) -> Segment:
        dep = s.get("departure") or {}
        arr = s.get("arrival") or {}
        code = s.get("carrierCode") or "?"
        return Segment(
            carrier_code=code,
            carrier_name=carriers.get(code, code),
            flight_number=f"{code}{s.get('number', '')}",
            departure_iata=dep.get("iataCode", ""),
            departure_at=dep.get("at", ""),
            arrival_iata=arr.get("iataCode", ""),
            arrival_at=arr.get("at", ""),
            duration_minutes=_parse_duration(s.get("duration", "")),
        )

    async def search_airports(self, query, limit=10):
        params = {
            "subType": "CITY,AIRPORT",
            "keyword": query,
            "page[limit]": limit,
        }
        data = await self._get("/v1/reference-data/locations", params, ttl=86400)
        result: list[Airport] = []
        for item in data.get("data") or []:
            code = item.get("iataCode")
            if not code:
                continue
            address = item.get("address") or {}
            result.append(Airport(
                iata=code,
                name=item.get("name", ""),
                city=address.get("cityName") or item.get("name", ""),
                country=address.get("countryCode", ""),
            ))
        return result
