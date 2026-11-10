"""货币与静态参考汇率。

Amadeus 的低价日历接口不接受 currencyCode，返回的是航线本地币种；
本表只用于把结果换算成用户选择的展示货币，仅为参考估算（前端会标注 ≈）。
"""
SUPPORTED_CURRENCIES = {
    "CNY", "USD", "EUR", "GBP", "JPY", "HKD", "SGD", "AUD", "CAD",
    "KRW", "TWD", "THB", "MYR", "IDR", "INR", "AED", "CHF", "NZD",
}

# 1 USD 兑换多少该货币（静态参考汇率，2026 年初）
RATES_TO_USD = {
    "USD": 1.0, "CNY": 7.25, "EUR": 0.92, "GBP": 0.79, "JPY": 150.0,
    "HKD": 7.82, "SGD": 1.34, "AUD": 1.52, "CAD": 1.37, "KRW": 1345.0,
    "TWD": 31.8, "THB": 34.5, "MYR": 4.45, "IDR": 15800.0, "INR": 84.0,
    "AED": 3.67, "CHF": 0.88, "NZD": 1.67,
    # 以下仅作为航线本地币种的换算输入
    "BRL": 5.6, "MXN": 19.9, "CLP": 940.0, "ZAR": 18.0, "TRY": 34.2,
    "PLN": 4.0, "CZK": 23.3, "HUF": 370.0, "SEK": 10.7, "NOK": 10.9,
    "DKK": 6.9, "PHP": 58.0, "VND": 25300.0, "RUB": 97.0, "ILS": 3.7,
    "QAR": 3.64, "SAR": 3.75, "EGP": 48.5, "KES": 129.0, "ETB": 130.0,
    "KZT": 490.0, "NGN": 1650.0, "BDT": 119.0, "PKR": 278.0, "LKR": 300.0,
    "NPR": 134.0, "MAD": 9.9, "TND": 3.12, "JOD": 0.709, "KWD": 0.307,
    "BHD": 0.376, "OMR": 0.385, "COP": 4400.0, "PEN": 3.72, "UYU": 41.5,
    "BOB": 6.91, "PYG": 7800.0, "ARS": 1000.0, "UAH": 41.2, "RON": 4.58,
    "BGN": 1.8, "RSD": 108.0, "HRK": 6.93, "ISK": 138.0, "TZS": 2700.0,
    "UGX": 3700.0, "GHS": 15.6, "XOF": 603.0, "XAF": 603.0, "DZD": 134.0,
    "AOA": 912.0, "MZN": 63.9, "NAD": 18.0, "BWP": 13.6, "MUR": 46.5,
    "AMD": 388.0, "GEL": 2.71, "AZN": 1.7, "MDL": 17.8, "BYN": 3.26,
}


def convert_price(amount: float, from_currency: str, to_currency: str) -> tuple[float, bool]:
    """把金额换算为 to_currency。

    返回 (金额, 是否参考汇率估算)。原币种与目标币种相同时不做换算。
    """
    f = (from_currency or "USD").strip().upper()
    if f == to_currency:
        return amount, False
    if f not in RATES_TO_USD:
        return amount, True  # 未知币种：按 1:1 估算，前端会标注 ≈
    usd = amount / RATES_TO_USD[f]
    return usd * RATES_TO_USD[to_currency], True
