"""演示数据源：无需任何 API 密钥，开箱即用。

价格基于机场坐标距离 + 季节/星期因子 + 确定性噪声生成，
同一查询结果稳定可复现，仅用于开发与演示。
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from currency import RATES_TO_USD
from .base import Airport, DayPrice, FlightOffer, Provider, ProviderError, Segment

# (IATA, 机场名, 城市, 国家代码, 纬度, 经度)
AIRPORT_DATA: list[tuple[str, str, str, str, float, float]] = [
    # 中国大陆
    ("PEK", "北京首都国际机场", "北京", "CN", 40.0799, 116.6031),
    ("PKX", "北京大兴国际机场", "北京", "CN", 39.5098, 116.4105),
    ("PVG", "上海浦东国际机场", "上海", "CN", 31.1443, 121.8083),
    ("SHA", "上海虹桥国际机场", "上海", "CN", 31.1979, 121.3363),
    ("CAN", "广州白云国际机场", "广州", "CN", 23.3924, 113.2988),
    ("SZX", "深圳宝安国际机场", "深圳", "CN", 22.6393, 113.8107),
    ("CTU", "成都双流国际机场", "成都", "CN", 30.5785, 103.9471),
    ("CKG", "重庆江北国际机场", "重庆", "CN", 29.7192, 106.6417),
    ("XIY", "西安咸阳国际机场", "西安", "CN", 34.4471, 108.7516),
    ("HGH", "杭州萧山国际机场", "杭州", "CN", 30.2295, 120.4345),
    ("KMG", "昆明长水国际机场", "昆明", "CN", 25.1019, 102.9292),
    ("WUH", "武汉天河国际机场", "武汉", "CN", 30.7838, 114.2081),
    ("XMN", "厦门高崎国际机场", "厦门", "CN", 24.544, 118.1277),
    ("TSN", "天津滨海国际机场", "天津", "CN", 39.1244, 117.3462),
    ("TAO", "青岛胶东国际机场", "青岛", "CN", 36.3619, 120.0889),
    ("CSX", "长沙黄花国际机场", "长沙", "CN", 28.1892, 113.2196),
    ("NKG", "南京禄口国际机场", "南京", "CN", 31.742, 118.862),
    ("SHE", "沈阳桃仙国际机场", "沈阳", "CN", 41.6398, 123.4834),
    ("HRB", "哈尔滨太平国际机场", "哈尔滨", "CN", 45.6234, 126.2503),
    ("DLC", "大连周水子国际机场", "大连", "CN", 38.9657, 121.5386),
    ("HAK", "海口美兰国际机场", "海口", "CN", 19.9349, 110.459),
    ("SYX", "三亚凤凰国际机场", "三亚", "CN", 18.3029, 109.4123),
    ("URC", "乌鲁木齐地窝堡国际机场", "乌鲁木齐", "CN", 43.9071, 87.4742),
    ("KWE", "贵阳龙洞堡国际机场", "贵阳", "CN", 26.5385, 106.8007),
    ("FOC", "福州长乐国际机场", "福州", "CN", 25.9351, 119.6633),
    ("CGO", "郑州新郑国际机场", "郑州", "CN", 34.5197, 113.8409),
    ("TNA", "济南遥墙国际机场", "济南", "CN", 36.8572, 117.216),
    # 港澳台
    ("HKG", "香港国际机场", "香港", "HK", 22.308, 113.9185),
    ("MFM", "澳门国际机场", "澳门", "MO", 22.1496, 113.5916),
    ("TPE", "台北桃园国际机场", "台北", "TW", 25.0777, 121.2328),
    ("KHH", "高雄国际机场", "高雄", "TW", 22.5771, 120.35),
    # 日韩
    ("NRT", "东京成田国际机场", "东京", "JP", 35.772, 140.3929),
    ("HND", "东京羽田国际机场", "东京", "JP", 35.5494, 139.7798),
    ("KIX", "大阪关西国际机场", "大阪", "JP", 34.4347, 135.2441),
    ("CTS", "札幌新千岁机场", "札幌", "JP", 42.7752, 141.6923),
    ("FUK", "福冈机场", "福冈", "JP", 33.5859, 130.4507),
    ("NGO", "名古屋中部国际机场", "名古屋", "JP", 34.8584, 136.8054),
    ("OKA", "冲绳那霸机场", "那霸", "JP", 26.1958, 127.6459),
    ("ICN", "首尔仁川国际机场", "首尔", "KR", 37.4602, 126.4407),
    ("GMP", "首尔金浦国际机场", "首尔", "KR", 37.5583, 126.7906),
    ("PUS", "釜山金海国际机场", "釜山", "KR", 35.1796, 128.9382),
    # 东南亚 / 南亚
    ("SIN", "新加坡樟宜机场", "新加坡", "SG", 1.3644, 103.9915),
    ("BKK", "曼谷素万那普国际机场", "曼谷", "TH", 13.69, 100.7501),
    ("DMK", "曼谷廊曼国际机场", "曼谷", "TH", 13.9126, 100.6068),
    ("HKT", "普吉国际机场", "普吉", "TH", 8.1132, 98.3169),
    ("CNX", "清迈国际机场", "清迈", "TH", 18.7668, 98.9626),
    ("KUL", "吉隆坡国际机场", "吉隆坡", "MY", 2.7456, 101.7099),
    ("CGK", "雅加达苏加诺-哈达国际机场", "雅加达", "ID", -6.1256, 106.6559),
    ("DPS", "巴厘岛伍拉·赖国际机场", "登巴萨", "ID", -8.7482, 115.1672),
    ("SGN", "胡志明市新山一国际机场", "胡志明市", "VN", 10.8188, 106.652),
    ("HAN", "河内内排国际机场", "河内", "VN", 21.2212, 105.8072),
    ("MNL", "马尼拉尼诺·阿基诺国际机场", "马尼拉", "PH", 14.5086, 121.0198),
    ("PNH", "金边国际机场", "金边", "KH", 11.5466, 104.8441),
    ("DEL", "德里英迪拉·甘地国际机场", "新德里", "IN", 28.5562, 77.1),
    ("BOM", "孟买贾特拉帕蒂·希瓦吉国际机场", "孟买", "IN", 19.0896, 72.8656),
    # 中东
    ("DXB", "迪拜国际机场", "迪拜", "AE", 25.2532, 55.3657),
    ("AUH", "阿布扎比国际机场", "阿布扎比", "AE", 24.433, 54.6511),
    ("DOH", "多哈哈马德国际机场", "多哈", "QA", 25.2731, 51.6081),
    ("RUH", "利雅得哈立德国王国际机场", "利雅得", "SA", 24.9576, 46.6988),
    ("TLV", "特拉维夫本·古里安机场", "特拉维夫", "IL", 32.0114, 34.8867),
    # 欧洲
    ("IST", "伊斯坦布尔机场", "伊斯坦布尔", "TR", 41.2753, 28.7519),
    ("LHR", "伦敦希思罗机场", "伦敦", "GB", 51.47, -0.4543),
    ("LGW", "伦敦盖特威克机场", "伦敦", "GB", 51.1537, -0.1821),
    ("MAN", "曼彻斯特机场", "曼彻斯特", "GB", 53.3537, -2.275),
    ("CDG", "巴黎戴高乐机场", "巴黎", "FR", 49.0097, 2.5479),
    ("ORY", "巴黎奥利机场", "巴黎", "FR", 48.7262, 2.3652),
    ("AMS", "阿姆斯特丹史基浦机场", "阿姆斯特丹", "NL", 52.3105, 4.7683),
    ("FRA", "法兰克福机场", "法兰克福", "DE", 50.0379, 8.5622),
    ("MUC", "慕尼黑机场", "慕尼黑", "DE", 48.3538, 11.7861),
    ("BER", "柏林勃兰登堡机场", "柏林", "DE", 52.3667, 13.5033),
    ("ZRH", "苏黎世机场", "苏黎世", "CH", 47.4647, 8.5492),
    ("GVA", "日内瓦机场", "日内瓦", "CH", 46.2381, 6.1089),
    ("MAD", "马德里巴拉哈斯机场", "马德里", "ES", 40.4983, -3.5676),
    ("BCN", "巴塞罗那埃尔普拉特机场", "巴塞罗那", "ES", 41.2974, 2.0833),
    ("LIS", "里斯本机场", "里斯本", "PT", 38.7742, -9.1342),
    ("FCO", "罗马菲乌米奇诺机场", "罗马", "IT", 41.8003, 12.2389),
    ("MXP", "米兰马尔彭萨机场", "米兰", "IT", 45.6306, 8.7281),
    ("VIE", "维也纳国际机场", "维也纳", "AT", 48.1103, 16.5697),
    ("CPH", "哥本哈根凯斯楚普机场", "哥本哈根", "DK", 55.618, 12.6508),
    ("ARN", "斯德哥尔摩阿兰达机场", "斯德哥尔摩", "SE", 59.6519, 17.9186),
    ("OSL", "奥斯陆加勒穆恩机场", "奥斯陆", "NO", 60.1939, 11.1004),
    ("HEL", "赫尔辛基万塔机场", "赫尔辛基", "FI", 60.3172, 24.9633),
    ("DUB", "都柏林机场", "都柏林", "IE", 53.4213, -6.2701),
    ("BRU", "布鲁塞尔机场", "布鲁塞尔", "BE", 50.9014, 4.4844),
    ("WAW", "华沙肖邦机场", "华沙", "PL", 52.1657, 20.9671),
    ("PRG", "布拉格瓦茨拉夫·哈维尔机场", "布拉格", "CZ", 50.1008, 14.26),
    ("BUD", "布达佩斯李斯特·费伦茨机场", "布达佩斯", "HU", 47.4369, 19.2556),
    ("ATH", "雅典埃莱夫塞里奥斯·韦尼泽洛斯机场", "雅典", "GR", 37.9364, 23.9445),
    ("SVO", "莫斯科谢列梅捷沃机场", "莫斯科", "RU", 55.9726, 37.4146),
    # 北美
    ("JFK", "纽约肯尼迪机场", "纽约", "US", 40.6413, -73.7781),
    ("EWR", "纽约纽瓦克机场", "纽约", "US", 40.6895, -74.1745),
    ("BOS", "波士顿洛根机场", "波士顿", "US", 42.3656, -71.0096),
    ("IAD", "华盛顿杜勒斯机场", "华盛顿", "US", 38.9531, -77.4565),
    ("ATL", "亚特兰大哈茨菲尔德-杰克逊机场", "亚特兰大", "US", 33.6407, -84.4277),
    ("ORD", "芝加哥奥黑尔机场", "芝加哥", "US", 41.9742, -87.9073),
    ("DFW", "达拉斯/沃思堡机场", "达拉斯", "US", 32.8998, -97.0403),
    ("DEN", "丹佛国际机场", "丹佛", "US", 39.8561, -104.6737),
    ("MIA", "迈阿密国际机场", "迈阿密", "US", 25.7959, -80.287),
    ("LAX", "洛杉矶国际机场", "洛杉矶", "US", 33.9416, -118.4085),
    ("SFO", "旧金山国际机场", "旧金山", "US", 37.6213, -122.379),
    ("SEA", "西雅图-塔科马机场", "西雅图", "US", 47.4502, -122.3088),
    ("LAS", "拉斯维加斯麦卡伦机场", "拉斯维加斯", "US", 36.084, -115.1537),
    ("HNL", "檀香山国际机场", "檀香山", "US", 21.3187, -157.9225),
    ("YVR", "温哥华国际机场", "温哥华", "CA", 49.1967, -123.1815),
    ("YYZ", "多伦多皮尔逊机场", "多伦多", "CA", 43.6777, -79.6248),
    ("YUL", "蒙特利尔特鲁多机场", "蒙特利尔", "CA", 45.4706, -73.7408),
    # 拉美
    ("MEX", "墨西哥城国际机场", "墨西哥城", "MX", 19.4363, -99.0721),
    ("CUN", "坎昆国际机场", "坎昆", "MX", 21.0365, -86.8771),
    ("GRU", "圣保罗瓜鲁柳斯机场", "圣保罗", "BR", -23.4356, -46.4731),
    ("EZE", "布宜诺斯艾利斯埃塞萨机场", "布宜诺斯艾利斯", "AR", -34.8222, -58.5358),
    ("LIM", "利马豪尔赫·查韦斯机场", "利马", "PE", -12.0219, -77.1143),
    ("BOG", "波哥大埃尔多拉多机场", "波哥大", "CO", 4.7016, -74.1469),
    ("SCL", "圣地亚哥阿图罗·梅里诺·贝尼特斯机场", "圣地亚哥", "CL", -33.393, -70.7858),
    # 大洋洲
    ("SYD", "悉尼金斯福德·史密斯机场", "悉尼", "AU", -33.9461, 151.1772),
    ("MEL", "墨尔本图拉马林机场", "墨尔本", "AU", -37.669, 144.841),
    ("BNE", "布里斯班机场", "布里斯班", "AU", -27.3842, 153.1175),
    ("PER", "珀斯机场", "珀斯", "AU", -31.9403, 115.9672),
    ("AKL", "奥克兰机场", "奥克兰", "NZ", -37.0082, 174.785),
    # 非洲
    ("JNB", "约翰内斯堡奥利弗·坦博机场", "约翰内斯堡", "ZA", -26.1392, 28.246),
    ("CAI", "开罗国际机场", "开罗", "EG", 30.1219, 31.4056),
    ("NBO", "内罗毕乔莫·肯雅塔机场", "内罗毕", "KE", -1.3192, 36.9278),
    ("ADD", "亚的斯亚贝巴博莱机场", "亚的斯亚贝巴", "ET", 8.9779, 38.7993),
]

AIRPORTS: dict[str, Airport] = {
    iata: Airport(iata=iata, name=name, city=city, country=cc)
    for iata, name, city, cc, _lat, _lon in AIRPORT_DATA
}
COORDS: dict[str, tuple[float, float]] = {
    iata: (lat, lon) for iata, _n, _c, _cc, lat, lon in AIRPORT_DATA
}

# 主要城市英文别名，方便英文输入联想
CITY_ALIASES = {
    "beijing": "北京", "shanghai": "上海", "guangzhou": "广州", "shenzhen": "深圳",
    "chengdu": "成都", "chongqing": "重庆", "xian": "西安", "hangzhou": "杭州",
    "kunming": "昆明", "wuhan": "武汉", "xiamen": "厦门", "tianjin": "天津",
    "qingdao": "青岛", "changsha": "长沙", "nanjing": "南京", "shenyang": "沈阳",
    "harbin": "哈尔滨", "dalian": "大连", "haikou": "海口", "sanya": "三亚",
    "urumqi": "乌鲁木齐", "guiyang": "贵阳", "fuzhou": "福州", "zhengzhou": "郑州",
    "jinan": "济南", "hong kong": "香港", "macau": "澳门", "taipei": "台北",
    "taibei": "台北", "kaohsiung": "高雄", "tokyo": "东京", "osaka": "大阪",
    "sapporo": "札幌", "fukuoka": "福冈", "nagoya": "名古屋", "okinawa": "那霸",
    "seoul": "首尔", "busan": "釜山", "singapore": "新加坡", "bangkok": "曼谷",
    "phuket": "普吉", "chiang mai": "清迈", "kuala lumpur": "吉隆坡",
    "jakarta": "雅加达", "bali": "登巴萨", "denpasar": "登巴萨",
    "ho chi minh": "胡志明市", "hanoi": "河内", "manila": "马尼拉",
    "phnom penh": "金边", "new delhi": "新德里", "delhi": "新德里",
    "mumbai": "孟买", "bombay": "孟买", "dubai": "迪拜", "abu dhabi": "阿布扎比",
    "doha": "多哈", "riyadh": "利雅得", "tel aviv": "特拉维夫",
    "istanbul": "伊斯坦布尔", "london": "伦敦", "manchester": "曼彻斯特",
    "paris": "巴黎", "amsterdam": "阿姆斯特丹", "frankfurt": "法兰克福",
    "munich": "慕尼黑", "berlin": "柏林", "zurich": "苏黎世", "geneva": "日内瓦",
    "madrid": "马德里", "barcelona": "巴塞罗那", "lisbon": "里斯本",
    "rome": "罗马", "milan": "米兰", "vienna": "维也纳", "copenhagen": "哥本哈根",
    "stockholm": "斯德哥尔摩", "oslo": "奥斯陆", "helsinki": "赫尔辛基",
    "dublin": "都柏林", "brussels": "布鲁塞尔", "warsaw": "华沙",
    "prague": "布拉格", "budapest": "布达佩斯", "athens": "雅典",
    "moscow": "莫斯科", "new york": "纽约", "boston": "波士顿",
    "washington": "华盛顿", "atlanta": "亚特兰大", "chicago": "芝加哥",
    "dallas": "达拉斯", "denver": "丹佛", "miami": "迈阿密",
    "los angeles": "洛杉矶", "san francisco": "旧金山", "seattle": "西雅图",
    "las vegas": "拉斯维加斯", "honolulu": "檀香山", "vancouver": "温哥华",
    "toronto": "多伦多", "montreal": "蒙特利尔", "mexico city": "墨西哥城",
    "cancun": "坎昆", "sao paulo": "圣保罗", "buenos aires": "布宜诺斯艾利斯",
    "lima": "利马", "bogota": "波哥大", "santiago": "圣地亚哥",
    "sydney": "悉尼", "melbourne": "墨尔本", "brisbane": "布里斯班",
    "perth": "珀斯", "auckland": "奥克兰", "johannesburg": "约翰内斯堡",
    "cairo": "开罗", "nairobi": "内罗毕", "addis ababa": "亚的斯亚贝巴",
}

SEASONAL = [1.18, 1.08, 0.95, 0.90, 0.95, 1.15, 1.25, 1.30, 1.05, 0.95, 0.90, 1.15]
WEEKDAY = [0.88, 0.82, 0.85, 0.90, 1.10, 1.06, 1.12]

CARRIER_CODES = ["CA", "MU", "CZ", "HU", "CX", "NH", "JL", "KE", "SQ", "EK", "QR", "TK",
                 "LH", "AF", "BA", "KL", "UA", "DL", "AA", "AC", "QF", "NZ", "LX", "AY"]
CARRIER_NAMES = ["中国国航", "东方航空", "南方航空", "海南航空", "国泰航空", "全日空", "日本航空",
                 "大韩航空", "新加坡航空", "阿联酋航空", "卡塔尔航空", "土耳其航空", "汉莎航空",
                 "法国航空", "英国航空", "荷兰皇家航空", "美联航", "达美航空", "美国航空",
                 "加拿大航空", "澳洲航空", "新西兰航空", "瑞士国际航空", "芬兰航空"]


def _fnv(text: str) -> int:
    """FNV-1a 哈希，用于生成确定性伪随机数。"""
    h = 2166136261
    for ch in text:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _distance(a: str, b: str) -> float:
    la1, lo1 = COORDS[a]
    la2, lo2 = COORDS[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    tmp = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(tmp))


def _price_usd(origin: str, destination: str, d: date) -> float:
    dist = _distance(origin, destination) or 2500.0
    base = 25 + dist * 0.055
    h = _fnv(f"{origin}|{destination}|{d.isoformat()}")
    noise = 0.82 + (h % 1000) / 1000 * 0.35
    return round(base * SEASONAL[d.month - 1] * WEEKDAY[d.weekday()] * noise, 2)


def _stops(origin: str, destination: str, d: date, h: int) -> int:
    dist = _distance(origin, destination)
    p = h % 100
    if dist < 1200:
        return 0 if p < 85 else 1
    if dist < 6000:
        return 0 if p < 55 else (1 if p < 85 else 2)
    return 0 if p < 40 else (1 if p < 75 else 2)


def _has_flight(origin: str, destination: str, d: date) -> bool:
    return _fnv(f"avail|{origin}|{destination}|{d.isoformat()}") % 100 >= 5


def _iso_minutes(d: date, minutes: int) -> str:
    """把「当日分钟数」格式化为 ISO 时间（允许超过 24h，自动进位到次日）。"""
    day = d + timedelta(days=minutes // 1440)
    minutes %= 1440
    hh, mm = divmod(minutes, 60)
    return f"{day.isoformat()}T{hh:02d}:{mm:02d}:00"


def _build_segments(origin: str, destination: str, d: date, h: int, k: int) -> list[Segment]:
    stops = _stops(origin, destination, d, _fnv(f"{origin}|{destination}|{d.isoformat()}|{k}"))
    legs = stops + 1
    codes = list(COORDS.keys())
    route = [origin]
    for i in range(stops):
        mid = codes[_fnv(f"{origin}|{destination}|{d.isoformat()}|{k}|mid{i}") % len(codes)]
        while mid in route:
            mid = codes[(codes.index(mid) + 1) % len(codes)]
        route.append(mid)
    route.append(destination)

    dep_min = 360 + h % (13 * 60)  # 06:00–19:00 起飞
    segs: list[Segment] = []
    for i in range(legs):
        a, b = route[i], route[i + 1]
        seg_dist = _distance(a, b) or 500.0
        dur = max(45, int(seg_dist / 820 * 60))
        arr_min = dep_min + dur
        idx = (h + i * 7 + k) % len(CARRIER_CODES)
        segs.append(Segment(
            carrier_code=CARRIER_CODES[idx],
            carrier_name=CARRIER_NAMES[idx],
            flight_number=f"{CARRIER_CODES[idx]}{100 + (h + i * 13) % 900}",
            departure_iata=a,
            departure_at=_iso_minutes(d, dep_min),
            arrival_iata=b,
            arrival_at=_iso_minutes(d, arr_min),
            duration_minutes=dur,
        ))
        dep_min = arr_min + 70 + (h + i) % 110  # 中转停留 1h10m–3h
    return segs


class MockProvider(Provider):
    name = "mock"

    def _check(self, origin: str, destination: str) -> None:
        if origin not in AIRPORTS or destination not in AIRPORTS:
            bad = origin if origin not in AIRPORTS else destination
            raise ProviderError(f"演示数据中没有机场代码 {bad}，请从输入框的联想列表中选择。")

    async def search_dates(self, origin, destination, date_from, date_to, adults=1, currency="CNY", non_stop=False):
        origin, destination = origin.upper(), destination.upper()
        self._check(origin, destination)
        rate = RATES_TO_USD.get(currency)
        if rate is None:
            raise ProviderError(f"不支持的货币：{currency}")

        result: list[DayPrice] = []
        d = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        while d <= end:
            if _has_flight(origin, destination, d):
                h = _fnv(f"{origin}|{destination}|{d.isoformat()}")
                stops = _stops(origin, destination, d, h)
                if not (non_stop and stops > 0):
                    result.append(DayPrice(
                        date=d.isoformat(),
                        price=round(_price_usd(origin, destination, d) * rate, 2),
                        currency=currency,
                        stops=stops,
                    ))
            d += timedelta(days=1)
        return result

    async def search_round_trip(self, origin, destination, departure_date, return_date=None, adults=1, currency="CNY", max_results=10):
        origin, destination = origin.upper(), destination.upper()
        self._check(origin, destination)
        rate = RATES_TO_USD.get(currency)
        if rate is None:
            raise ProviderError(f"不支持的货币：{currency}")

        dep = date.fromisoformat(departure_date)
        ret = date.fromisoformat(return_date) if return_date else None
        if ret is not None and ret <= dep:
            raise ProviderError("返程日期必须晚于出发日期")

        offers: list[FlightOffer] = []
        for k in range(max_results):
            seed = f"offers|{origin}|{destination}|{dep}|{ret}|{k}"
            h = _fnv(seed)
            total = _price_usd(origin, destination, dep) * (0.95 + 0.02 * k)
            out_segs = _build_segments(origin, destination, dep, h, k)
            in_segs: list[Segment] = []
            if ret is not None:
                h2 = _fnv(seed + "|ret")
                total += _price_usd(destination, origin, ret) * (0.95 + 0.02 * k)
                in_segs = _build_segments(destination, origin, ret, h2, k)
            offers.append(FlightOffer(
                price_total=round(total * rate, 2),
                currency=currency,
                outbound=out_segs,
                inbound=in_segs,
            ))
        offers.sort(key=lambda o: o.price_total)
        return offers

    async def search_airports(self, query, limit=10):
        q = query.strip().lower()
        if not q:
            return []

        def score(a: Airport) -> Optional[int]:
            if a.iata.lower() == q:
                return 0
            if a.iata.lower().startswith(q):
                return 1
            if a.city.lower().startswith(q) or a.name.lower().startswith(q):
                return 2
            if CITY_ALIASES.get(q) == a.city:
                return 2
            if q in a.city.lower() or q in a.name.lower():
                return 3
            return None

        scored = [(s, a) for a in AIRPORTS.values() if (s := score(a)) is not None]
        scored.sort(key=lambda t: (t[0], t[1].iata))
        return [a for _, a in scored[:limit]]
