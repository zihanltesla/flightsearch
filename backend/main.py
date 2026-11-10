"""FlightSearch 后端 —— 运行在你电脑上的机票比价服务。

用法:
    cd backend && ./start.sh            # 首次先 ./setup.sh
    然后访问 http://localhost:8000（自带前端），或使用 GitHub Pages 前端。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from cache import TTLCache
from currency import SUPPORTED_CURRENCIES, convert_price
from providers.amadeus import AmadeusProvider
from providers.base import DayPrice, Provider, ProviderError
from providers.mock import MockProvider
from providers.serpapi import SerpApiProvider

MAX_WINDOW_DAYS = 60   # 单个日期区间最大跨度
CHUNK_DAYS = 30        # 低价日历接口每次最多查询的天数

app = FastAPI(title="FlightSearch API", version=config.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 本地个人工具，宽松处理；如需收紧改成具体前端域名
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_private_network(request, call_next):
    """GitHub Pages(HTTPS) -> 本机(HTTP) 属于 Chrome 的 Private Network Access，
    响应需携带该头才能通过浏览器预检。"""
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


_cache = TTLCache()
mock = MockProvider()
amadeus = (
    AmadeusProvider(
        config.AMADEUS_CLIENT_ID,
        config.AMADEUS_CLIENT_SECRET,
        env=config.AMADEUS_ENV,
        cache=_cache,
    )
    if config.amadeus_configured()
    else None
)
serpapi = (
    SerpApiProvider(config.SERPAPI_API_KEY, cache=_cache)
    if config.serpapi_configured()
    else None
)


def resolve_provider(requested: str) -> tuple[Provider, Optional[str]]:
    """返回 (provider, 降级说明)。降级说明非 None 表示自动降级到了演示数据。"""
    requested = (requested or "auto").strip().lower()
    if requested == "mock":
        return mock, None
    if requested == "amadeus":
        if amadeus is None:
            raise HTTPException(
                status_code=400,
                detail="尚未配置 Amadeus API 密钥（backend/.env），请先在「设置」中切换为演示数据，或按 README 完成配置。",
            )
        return amadeus, None
    if requested == "serpapi":
        if serpapi is None:
            raise HTTPException(
                status_code=400,
                detail="尚未配置 SerpApi API Key（backend/.env），请先在「设置」中切换为演示数据，或按 README 完成配置。",
            )
        return serpapi, None
    # auto
    if amadeus is not None:
        return amadeus, None
    if serpapi is not None:
        return serpapi, None
    return mock, "未配置任何真实数据源（Amadeus / SerpApi），当前为演示数据（模拟价格），配置方法见 README。"


def parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{label}日期格式应为 YYYY-MM-DD。")


def normalize_iata(value: str, label: str) -> str:
    code = (value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise HTTPException(status_code=422, detail=f"{label}请填写 3 位 IATA 机场代码（如 SFO），可从输入框建议中选择。")
    return code


def validate_currency(currency: str) -> str:
    currency = (currency or "CNY").strip().upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=422, detail=f"不支持的货币代码：{currency}")
    return currency


# ---------- 请求模型 ----------

class DateWindow(BaseModel):
    frm: str
    to: str


class SearchRequest(BaseModel):
    origin: str
    destination: str
    departure_window: DateWindow
    return_window: Optional[DateWindow] = None  # 为空 = 单程
    adults: int = Field(1, ge=1, le=9)
    currency: str = "CNY"
    non_stop: bool = False
    provider: str = "auto"      # auto | amadeus | mock
    max_combos: int = Field(50, ge=1, le=200)


def validate_window(win: DateWindow, label: str) -> tuple[date, date]:
    d1 = parse_date(win.frm, label)
    d2 = parse_date(win.to, label)
    if d1 > d2:
        raise HTTPException(status_code=422, detail=f"{label}：开始日期不能晚于结束日期。")
    if (d2 - d1).days > MAX_WINDOW_DAYS:
        raise HTTPException(status_code=422, detail=f"{label}区间不能超过 {MAX_WINDOW_DAYS} 天。")
    return d1, d2


async def fetch_date_prices(
    provider: Provider, origin: str, destination: str,
    d1: date, d2: date, currency: str, non_stop: bool,
) -> list[DayPrice]:
    """按 30 天切片请求低价日历，合并结果。"""
    result: list[DayPrice] = []
    cursor = d1
    while cursor <= d2:
        end = min(cursor + timedelta(days=CHUNK_DAYS - 1), d2)
        chunk = await provider.search_dates(
            origin, destination, cursor.isoformat(), end.isoformat(),
            currency=currency, non_stop=non_stop,
        )
        result.extend(chunk)
        cursor = end + timedelta(days=1)
    return result


# ---------- 接口 ----------

@app.post("/api/search")
async def search(req: SearchRequest):
    origin = normalize_iata(req.origin, "出发地")
    destination = normalize_iata(req.destination, "目的地")
    if origin == destination:
        raise HTTPException(status_code=422, detail="出发地与目的地不能相同。")
    currency = validate_currency(req.currency)

    provider, fallback_reason = resolve_provider(req.provider)

    d1, d2 = validate_window(req.departure_window, "出发日期")
    today = date.today()
    if d1 < today:
        raise HTTPException(status_code=422, detail="出发日期不能早于今天。")
    if d2 > today + timedelta(days=365):
        raise HTTPException(status_code=422, detail="出发日期不能晚于一年后。")

    r1 = r2 = None
    if req.return_window is not None:
        r1, r2 = validate_window(req.return_window, "返程日期")
        if r2 <= d1:
            raise HTTPException(status_code=422, detail="返程日期必须晚于出发日期。")

    try:
        out = await fetch_date_prices(provider, origin, destination, d1, d2, currency, req.non_stop)
        ret: list[DayPrice] = []
        if r1 is not None:
            ret = await fetch_date_prices(provider, destination, origin, r1, r2, currency, req.non_stop)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not out:
        raise HTTPException(status_code=404, detail="所选日期范围内没有找到航班价格，请调整日期或机场。")

    def norm(dp: DayPrice) -> dict:
        price, approx = convert_price(dp.price, dp.currency, currency)
        return {
            "date": dp.date,
            "price": round(price, 2),
            "currency": currency,
            "approx": approx,
            "stops": dp.stops,
            "native_price": round(dp.price, 2),
            "native_currency": dp.currency,
        }

    out_n = [norm(x) for x in out]
    ret_n = [norm(x) for x in ret]

    combos: list[dict] = []
    if ret_n:
        for o in out_n:
            for r in ret_n:
                if r["date"] > o["date"]:
                    combos.append({
                        "outbound_date": o["date"],
                        "return_date": r["date"],
                        "outbound_price": o["price"],
                        "return_price": r["price"],
                        "total_price": round(o["price"] + r["price"], 2),
                        "outbound_stops": o["stops"],
                        "return_stops": r["stops"],
                        "approx": o["approx"] or r["approx"],
                    })
    else:
        # 单程：每天的价格即是一个"组合"
        for o in out_n:
            combos.append({
                "outbound_date": o["date"],
                "return_date": None,
                "outbound_price": o["price"],
                "return_price": None,
                "total_price": o["price"],
                "outbound_stops": o["stops"],
                "return_stops": None,
                "approx": o["approx"],
            })
    combos.sort(key=lambda c: c["total_price"])
    checked = len(combos)
    combos = combos[: req.max_combos]

    return {
        "provider": provider.name,
        "fallback_reason": fallback_reason,
        "currency": currency,
        "outbound_dates": out_n,
        "return_dates": ret_n,
        "combos": combos,
        "combos_checked": checked,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _offer_to_dict(o) -> dict:
    def segs_to_dict(segs) -> list[dict]:
        return [
            {
                "carrier_code": s.carrier_code,
                "carrier_name": s.carrier_name,
                "flight_number": s.flight_number,
                "departure_iata": s.departure_iata,
                "departure_at": s.departure_at,
                "arrival_iata": s.arrival_iata,
                "arrival_at": s.arrival_at,
                "duration_minutes": s.duration_minutes,
            }
            for s in segs
        ]

    out_segs = segs_to_dict(o.outbound)
    in_segs = segs_to_dict(o.inbound)
    return {
        "price_total": o.price_total,
        "currency": o.currency,
        "outbound": out_segs,
        "inbound": in_segs,
        "outbound_price": o.outbound_price,
        "inbound_price": o.inbound_price,
        "outbound_stops": max(0, len(out_segs) - 1),
        "inbound_stops": max(0, len(in_segs) - 1),
        "outbound_duration_minutes": sum(s["duration_minutes"] for s in out_segs),
        "inbound_duration_minutes": sum(s["duration_minutes"] for s in in_segs),
    }


@app.get("/api/offers")
async def offers(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    adults: int = Query(1, ge=1, le=9),
    currency: str = "CNY",
    provider: str = "auto",
    limit: int = Query(10, ge=1, le=50, alias="max"),
):
    origin = normalize_iata(origin, "出发地")
    destination = normalize_iata(destination, "目的地")
    currency = validate_currency(currency)
    dep = parse_date(departure_date, "出发")
    ret = parse_date(return_date, "返程") if return_date else None
    if ret is not None and ret <= dep:
        raise HTTPException(status_code=422, detail="返程日期必须晚于出发日期。")

    p, _ = resolve_provider(provider)
    try:
        items = await p.search_round_trip(
            origin, destination, dep.isoformat(), ret.isoformat() if ret else None,
            adults=adults, currency=currency, max_results=limit,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "provider": p.name,
        "currency": currency,
        "offers": [_offer_to_dict(o) for o in items],
    }


@app.get("/api/airports")
async def airports(
    q: str,
    provider: str = "auto",
    limit: int = Query(10, ge=1, le=20),
):
    if not q.strip():
        return []
    try:
        p, _ = resolve_provider(provider)
    except HTTPException:
        p = mock  # 所选数据源未配置时，机场联想仍使用内置列表
    if p.name == "serpapi":
        p = mock  # SerpApi 无机场联想接口，使用内置机场列表（不消耗额度）
    try:
        items = await p.search_airports(q.strip(), limit)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [{"iata": a.iata, "name": a.name, "city": a.city, "country": a.country} for a in items]


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "amadeus_configured": amadeus is not None,
        "serpapi_configured": serpapi is not None,
        "providers": ["mock"]
        + (["amadeus"] if amadeus is not None else [])
        + (["serpapi"] if serpapi is not None else []),
    }


# 若前端目录存在，后端也直接托管前端（http://localhost:8000 即可使用）
if config.FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")


def main() -> None:
    if amadeus:
        mode = "Amadeus（真实价格）"
    elif serpapi:
        mode = "SerpApi / Google Flights（真实价格）"
    else:
        mode = "演示数据（模拟价格，未配置真实数据源）"
    print("=" * 52)
    print("  FlightSearch 后端已启动")
    print(f"  访问地址 : http://localhost:{config.PORT}")
    print(f"  数据源   : {mode}")
    print(f"  健康检查 : http://localhost:{config.PORT}/api/health")
    print("=" * 52)
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
