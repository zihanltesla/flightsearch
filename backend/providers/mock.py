"""演示数据源：无需任何 API 密钥，开箱即用。

价格基于机场坐标距离 + 季节/星期因子 + 确定性噪声生成，
同一查询结果稳定可复现，仅用于开发与演示。

内置机场列表同时供机场联想使用（英文名；中文拼音之外也支持
中文城市/机场名搜索，见 CN_CITY / CN_NAME）。
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from currency import RATES_TO_USD
from .base import Airport, DayPrice, FlightOffer, Provider, ProviderError, Segment

# (IATA, 英文机场名, 英文城市, 国家代码, 纬度, 经度)
AIRPORT_DATA: list[tuple[str, str, str, str, float, float]] = [
    # China 中国大陆
    ("PEK", "Beijing Capital International Airport", "Beijing", "CN", 40.0799, 116.6031),
    ("PKX", "Beijing Daxing International Airport", "Beijing", "CN", 39.5098, 116.4105),
    ("PVG", "Shanghai Pudong International Airport", "Shanghai", "CN", 31.1443, 121.8083),
    ("SHA", "Shanghai Hongqiao International Airport", "Shanghai", "CN", 31.1979, 121.3363),
    ("CAN", "Guangzhou Baiyun International Airport", "Guangzhou", "CN", 23.3924, 113.2988),
    ("SZX", "Shenzhen Bao'an International Airport", "Shenzhen", "CN", 22.6393, 113.8107),
    ("CTU", "Chengdu Shuangliu International Airport", "Chengdu", "CN", 30.5785, 103.9471),
    ("CKG", "Chongqing Jiangbei International Airport", "Chongqing", "CN", 29.7192, 106.6417),
    ("XIY", "Xi'an Xianyang International Airport", "Xi'an", "CN", 34.4471, 108.7516),
    ("HGH", "Hangzhou Xiaoshan International Airport", "Hangzhou", "CN", 30.2295, 120.4345),
    ("KMG", "Kunming Changshui International Airport", "Kunming", "CN", 25.1019, 102.9292),
    ("WUH", "Wuhan Tianhe International Airport", "Wuhan", "CN", 30.7838, 114.2081),
    ("XMN", "Xiamen Gaoqi International Airport", "Xiamen", "CN", 24.544, 118.1277),
    ("TSN", "Tianjin Binhai International Airport", "Tianjin", "CN", 39.1244, 117.3462),
    ("TAO", "Qingdao Jiaodong International Airport", "Qingdao", "CN", 36.3619, 120.0889),
    ("CSX", "Changsha Huanghua International Airport", "Changsha", "CN", 28.1892, 113.2196),
    ("NKG", "Nanjing Lukou International Airport", "Nanjing", "CN", 31.742, 118.862),
    ("SHE", "Shenyang Taoxian International Airport", "Shenyang", "CN", 41.6398, 123.4834),
    ("HRB", "Harbin Taiping International Airport", "Harbin", "CN", 45.6234, 126.2503),
    ("DLC", "Dalian Zhoushuizi International Airport", "Dalian", "CN", 38.9657, 121.5386),
    ("HAK", "Haikou Meilan International Airport", "Haikou", "CN", 19.9349, 110.459),
    ("SYX", "Sanya Phoenix International Airport", "Sanya", "CN", 18.3029, 109.4123),
    ("URC", "Ürümqi Diwopu International Airport", "Urumqi", "CN", 43.9071, 87.4742),
    ("KWE", "Guiyang Longdongbao International Airport", "Guiyang", "CN", 26.5385, 106.8007),
    ("FOC", "Fuzhou Changle International Airport", "Fuzhou", "CN", 25.9351, 119.6633),
    ("CGO", "Zhengzhou Xinzheng International Airport", "Zhengzhou", "CN", 34.5197, 113.8409),
    ("TNA", "Jinan Yaoqiang International Airport", "Jinan", "CN", 36.8572, 117.216),
    # Hong Kong / Macau / Taiwan 港澳台
    ("HKG", "Hong Kong International Airport", "Hong Kong", "HK", 22.308, 113.9185),
    ("MFM", "Macau International Airport", "Macau", "MO", 22.1496, 113.5916),
    ("TPE", "Taiwan Taoyuan International Airport", "Taipei", "TW", 25.0777, 121.2328),
    ("KHH", "Kaohsiung International Airport", "Kaohsiung", "TW", 22.5771, 120.35),
    # Japan / Korea 日韩
    ("NRT", "Tokyo Narita International Airport", "Tokyo", "JP", 35.772, 140.3929),
    ("HND", "Tokyo Haneda Airport", "Tokyo", "JP", 35.5494, 139.7798),
    ("KIX", "Osaka Kansai International Airport", "Osaka", "JP", 34.4347, 135.2441),
    ("CTS", "New Chitose Airport", "Sapporo", "JP", 42.7752, 141.6923),
    ("FUK", "Fukuoka Airport", "Fukuoka", "JP", 33.5859, 130.4507),
    ("NGO", "Chubu Centrair International Airport", "Nagoya", "JP", 34.8584, 136.8054),
    ("OKA", "Naha Airport", "Okinawa", "JP", 26.1958, 127.6459),
    ("ICN", "Seoul Incheon International Airport", "Seoul", "KR", 37.4602, 126.4407),
    ("GMP", "Seoul Gimpo International Airport", "Seoul", "KR", 37.5583, 126.7906),
    ("PUS", "Gimhae International Airport", "Busan", "KR", 35.1796, 128.9382),
    # Southeast / South Asia 东南亚 / 南亚
    ("SIN", "Singapore Changi Airport", "Singapore", "SG", 1.3644, 103.9915),
    ("BKK", "Bangkok Suvarnabhumi International Airport", "Bangkok", "TH", 13.69, 100.7501),
    ("DMK", "Bangkok Don Mueang International Airport", "Bangkok", "TH", 13.9126, 100.6068),
    ("HKT", "Phuket International Airport", "Phuket", "TH", 8.1132, 98.3169),
    ("CNX", "Chiang Mai International Airport", "Chiang Mai", "TH", 18.7668, 98.9626),
    ("KUL", "Kuala Lumpur International Airport", "Kuala Lumpur", "MY", 2.7456, 101.7099),
    ("CGK", "Jakarta Soekarno-Hatta International Airport", "Jakarta", "ID", -6.1256, 106.6559),
    ("DPS", "Ngurah Rai International Airport", "Denpasar (Bali)", "ID", -8.7482, 115.1672),
    ("SGN", "Tan Son Nhat International Airport", "Ho Chi Minh City", "VN", 10.8188, 106.652),
    ("HAN", "Noi Bai International Airport", "Hanoi", "VN", 21.2212, 105.8072),
    ("MNL", "Ninoy Aquino International Airport", "Manila", "PH", 14.5086, 121.0198),
    ("PNH", "Phnom Penh International Airport", "Phnom Penh", "KH", 11.5466, 104.8441),
    ("DEL", "Indira Gandhi International Airport", "Delhi", "IN", 28.5562, 77.1),
    ("BOM", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "IN", 19.0896, 72.8656),
    # Middle East 中东
    ("DXB", "Dubai International Airport", "Dubai", "AE", 25.2532, 55.3657),
    ("AUH", "Abu Dhabi International Airport", "Abu Dhabi", "AE", 24.433, 54.6511),
    ("DOH", "Hamad International Airport", "Doha", "QA", 25.2731, 51.6081),
    ("RUH", "King Khalid International Airport", "Riyadh", "SA", 24.9576, 46.6988),
    ("TLV", "Ben Gurion Airport", "Tel Aviv", "IL", 32.0114, 34.8867),
    # Europe 欧洲
    ("IST", "Istanbul Airport", "Istanbul", "TR", 41.2753, 28.7519),
    ("LHR", "London Heathrow Airport", "London", "GB", 51.47, -0.4543),
    ("LGW", "London Gatwick Airport", "London", "GB", 51.1537, -0.1821),
    ("MAN", "Manchester Airport", "Manchester", "GB", 53.3537, -2.275),
    ("CDG", "Paris Charles de Gaulle Airport", "Paris", "FR", 49.0097, 2.5479),
    ("ORY", "Paris Orly Airport", "Paris", "FR", 48.7262, 2.3652),
    ("AMS", "Amsterdam Airport Schiphol", "Amsterdam", "NL", 52.3105, 4.7683),
    # Germany 德国
    ("FRA", "Frankfurt Airport", "Frankfurt", "DE", 50.0379, 8.5622),
    ("MUC", "Munich Airport", "Munich", "DE", 48.3538, 11.7861),
    ("BER", "Berlin Brandenburg Airport", "Berlin", "DE", 52.3667, 13.5033),
    ("DUS", "Düsseldorf Airport", "Düsseldorf", "DE", 51.2895, 6.7668),
    ("HAM", "Hamburg Airport", "Hamburg", "DE", 53.6304, 9.9882),
    ("STR", "Stuttgart Airport", "Stuttgart", "DE", 48.6899, 9.2219),
    ("CGN", "Cologne Bonn Airport", "Cologne", "DE", 50.8659, 7.1427),
    ("HAJ", "Hanover Airport", "Hanover", "DE", 52.4611, 9.6851),
    ("NUE", "Nuremberg Airport", "Nuremberg", "DE", 49.4987, 11.0781),
    ("DRS", "Dresden Airport", "Dresden", "DE", 51.1343, 13.7681),
    ("LEJ", "Leipzig/Halle Airport", "Leipzig", "DE", 51.4239, 12.2364),
    ("BRE", "Bremen Airport", "Bremen", "DE", 53.0475, 8.7867),
    ("FMO", "Münster Osnabrück International Airport", "Münster", "DE", 52.1346, 7.6848),
    # Switzerland 瑞士
    ("ZRH", "Zurich Airport", "Zurich", "CH", 47.4647, 8.5492),
    ("GVA", "Geneva Airport", "Geneva", "CH", 46.2381, 6.1089),
    # Iberia / Italy 伊比利亚 / 意大利
    ("MAD", "Adolfo Suárez Madrid–Barajas Airport", "Madrid", "ES", 40.4983, -3.5676),
    ("BCN", "Josep Tarradellas Barcelona-El Prat Airport", "Barcelona", "ES", 41.2974, 2.0833),
    ("LIS", "Humberto Delgado Airport", "Lisbon", "PT", 38.7742, -9.1342),
    ("FCO", "Rome Fiumicino Leonardo da Vinci Airport", "Rome", "IT", 41.8003, 12.2389),
    ("MXP", "Milan Malpensa Airport", "Milan", "IT", 45.6306, 8.7281),
    ("VIE", "Vienna International Airport", "Vienna", "AT", 48.1103, 16.5697),
    # Nordic: Denmark 丹麦
    ("CPH", "Copenhagen Airport", "Copenhagen", "DK", 55.618, 12.6508),
    ("BLL", "Billund Airport", "Billund", "DK", 55.7403, 9.1518),
    ("AAL", "Aalborg Airport", "Aalborg", "DK", 57.0928, 9.8492),
    ("AAR", "Aarhus Airport", "Aarhus", "DK", 56.3, 10.619),
    # Nordic: Norway 挪威
    ("OSL", "Oslo Airport Gardermoen", "Oslo", "NO", 60.1939, 11.1004),
    ("BGO", "Bergen Airport Flesland", "Bergen", "NO", 60.2934, 5.2181),
    ("SVG", "Stavanger Airport Sola", "Stavanger", "NO", 58.8767, 5.6378),
    ("TRD", "Trondheim Airport Værnes", "Trondheim", "NO", 63.4576, 10.9243),
    ("TOS", "Tromsø Airport Langnes", "Tromsø", "NO", 69.6833, 18.9189),
    # Nordic: Sweden 瑞典
    ("ARN", "Stockholm Arlanda Airport", "Stockholm", "SE", 59.6519, 17.9186),
    ("GOT", "Gothenburg Landvetter Airport", "Gothenburg", "SE", 57.6628, 12.2798),
    ("MMX", "Malmö Airport", "Malmö", "SE", 55.5363, 13.3762),
    # Nordic: Finland 芬兰
    ("HEL", "Helsinki-Vantaa Airport", "Helsinki", "FI", 60.3172, 24.9633),
    ("ROV", "Rovaniemi Airport", "Rovaniemi", "FI", 66.5648, 25.8304),
    # Nordic: Iceland 冰岛
    ("KEF", "Keflavík International Airport", "Reykjavik", "IS", 63.985, -22.6056),
    # Rest of Europe 欧洲其他
    ("DUB", "Dublin Airport", "Dublin", "IE", 53.4213, -6.2701),
    ("BRU", "Brussels Airport", "Brussels", "BE", 50.9014, 4.4844),
    ("WAW", "Warsaw Chopin Airport", "Warsaw", "PL", 52.1657, 20.9671),
    ("PRG", "Václav Havel Airport Prague", "Prague", "CZ", 50.1008, 14.26),
    ("BUD", "Budapest Ferenc Liszt International Airport", "Budapest", "HU", 47.4369, 19.2556),
    ("ATH", "Athens International Airport", "Athens", "GR", 37.9364, 23.9445),
    ("SVO", "Sheremetyevo International Airport", "Moscow", "RU", 55.9726, 37.4146),
    # North America 北美
    ("JFK", "John F. Kennedy International Airport", "New York", "US", 40.6413, -73.7781),
    ("EWR", "Newark Liberty International Airport", "New York", "US", 40.6895, -74.1745),
    ("BOS", "Boston Logan International Airport", "Boston", "US", 42.3656, -71.0096),
    ("IAD", "Washington Dulles International Airport", "Washington", "US", 38.9531, -77.4565),
    ("ATL", "Hartsfield–Jackson Atlanta International Airport", "Atlanta", "US", 33.6407, -84.4277),
    ("ORD", "Chicago O'Hare International Airport", "Chicago", "US", 41.9742, -87.9073),
    ("DFW", "Dallas/Fort Worth International Airport", "Dallas", "US", 32.8998, -97.0403),
    ("DEN", "Denver International Airport", "Denver", "US", 39.8561, -104.6737),
    ("MIA", "Miami International Airport", "Miami", "US", 25.7959, -80.287),
    ("LAX", "Los Angeles International Airport", "Los Angeles", "US", 33.9416, -118.4085),
    ("SFO", "San Francisco International Airport", "San Francisco", "US", 37.6213, -122.379),
    ("SEA", "Seattle-Tacoma International Airport", "Seattle", "US", 47.4502, -122.3088),
    ("LAS", "Harry Reid International Airport", "Las Vegas", "US", 36.084, -115.1537),
    ("HNL", "Daniel K. Inouye International Airport", "Honolulu", "US", 21.3187, -157.9225),
    ("YVR", "Vancouver International Airport", "Vancouver", "CA", 49.1967, -123.1815),
    ("YYZ", "Toronto Pearson International Airport", "Toronto", "CA", 43.6777, -79.6248),
    ("YUL", "Montréal-Trudeau International Airport", "Montreal", "CA", 45.4706, -73.7408),
    # Latin America 拉美
    ("MEX", "Mexico City International Airport", "Mexico City", "MX", 19.4363, -99.0721),
    ("CUN", "Cancún International Airport", "Cancún", "MX", 21.0365, -86.8771),
    ("GRU", "São Paulo/Guarulhos International Airport", "São Paulo", "BR", -23.4356, -46.4731),
    ("EZE", "Ministro Pistarini International Airport", "Buenos Aires", "AR", -34.8222, -58.5358),
    ("LIM", "Jorge Chávez International Airport", "Lima", "PE", -12.0219, -77.1143),
    ("BOG", "El Dorado International Airport", "Bogotá", "CO", 4.7016, -74.1469),
    ("SCL", "Arturo Merino Benítez International Airport", "Santiago", "CL", -33.393, -70.7858),
    # Oceania 大洋洲
    ("SYD", "Sydney Kingsford Smith Airport", "Sydney", "AU", -33.9461, 151.1772),
    ("MEL", "Melbourne Airport", "Melbourne", "AU", -37.669, 144.841),
    ("BNE", "Brisbane Airport", "Brisbane", "AU", -27.3842, 153.1175),
    ("PER", "Perth Airport", "Perth", "AU", -31.9403, 115.9672),
    ("AKL", "Auckland Airport", "Auckland", "NZ", -37.0082, 174.785),
    # Africa 非洲
    ("JNB", "O. R. Tambo International Airport", "Johannesburg", "ZA", -26.1392, 28.246),
    ("CAI", "Cairo International Airport", "Cairo", "EG", 30.1219, 31.4056),
    ("NBO", "Jomo Kenyatta International Airport", "Nairobi", "KE", -1.3192, 36.9278),
    ("ADD", "Addis Ababa Bole International Airport", "Addis Ababa", "ET", 8.9779, 38.7993),
]

AIRPORTS: dict[str, Airport] = {
    iata: Airport(iata=iata, name=name, city=city, country=cc)
    for iata, name, city, cc, _lat, _lon in AIRPORT_DATA
}
COORDS: dict[str, tuple[float, float]] = {
    iata: (lat, lon) for iata, _n, _c, _cc, lat, lon in AIRPORT_DATA
}

# 中文城市 / 机场名（仅用于中文输入联想，展示仍为英文）
CN_CITY: dict[str, str] = {
    "PEK": "北京", "PKX": "北京", "PVG": "上海", "SHA": "上海", "CAN": "广州",
    "SZX": "深圳", "CTU": "成都", "CKG": "重庆", "XIY": "西安", "HGH": "杭州",
    "KMG": "昆明", "WUH": "武汉", "XMN": "厦门", "TSN": "天津", "TAO": "青岛",
    "CSX": "长沙", "NKG": "南京", "SHE": "沈阳", "HRB": "哈尔滨", "DLC": "大连",
    "HAK": "海口", "SYX": "三亚", "URC": "乌鲁木齐", "KWE": "贵阳", "FOC": "福州",
    "CGO": "郑州", "TNA": "济南", "HKG": "香港", "MFM": "澳门", "TPE": "台北",
    "KHH": "高雄", "NRT": "东京", "HND": "东京", "KIX": "大阪", "CTS": "札幌",
    "FUK": "福冈", "NGO": "名古屋", "OKA": "那霸", "ICN": "首尔", "GMP": "首尔",
    "PUS": "釜山", "SIN": "新加坡", "BKK": "曼谷", "DMK": "曼谷", "HKT": "普吉",
    "CNX": "清迈", "KUL": "吉隆坡", "CGK": "雅加达", "DPS": "登巴萨", "SGN": "胡志明市",
    "HAN": "河内", "MNL": "马尼拉", "PNH": "金边", "DEL": "新德里", "BOM": "孟买",
    "DXB": "迪拜", "AUH": "阿布扎比", "DOH": "多哈", "RUH": "利雅得", "TLV": "特拉维夫",
    "IST": "伊斯坦布尔", "LHR": "伦敦", "LGW": "伦敦", "MAN": "曼彻斯特",
    "CDG": "巴黎", "ORY": "巴黎", "AMS": "阿姆斯特丹",
    "FRA": "法兰克福", "MUC": "慕尼黑", "BER": "柏林", "DUS": "杜塞尔多夫",
    "HAM": "汉堡", "STR": "斯图加特", "CGN": "科隆", "HAJ": "汉诺威",
    "NUE": "纽伦堡", "DRS": "德累斯顿", "LEJ": "莱比锡", "BRE": "不来梅",
    "FMO": "明斯特", "ZRH": "苏黎世", "GVA": "日内瓦", "MAD": "马德里",
    "BCN": "巴塞罗那", "LIS": "里斯本", "FCO": "罗马", "MXP": "米兰",
    "VIE": "维也纳", "CPH": "哥本哈根", "BLL": "比隆", "AAL": "奥尔堡",
    "AAR": "奥胡斯", "OSL": "奥斯陆", "BGO": "卑尔根", "SVG": "斯塔万格",
    "TRD": "特隆赫姆", "TOS": "特罗姆瑟", "ARN": "斯德哥尔摩", "GOT": "哥德堡",
    "MMX": "马尔默", "HEL": "赫尔辛基", "ROV": "罗瓦涅米", "KEF": "雷克雅未克",
    "DUB": "都柏林", "BRU": "布鲁塞尔", "WAW": "华沙", "PRG": "布拉格",
    "BUD": "布达佩斯", "ATH": "雅典", "SVO": "莫斯科",
    "JFK": "纽约", "EWR": "纽约", "BOS": "波士顿", "IAD": "华盛顿",
    "ATL": "亚特兰大", "ORD": "芝加哥", "DFW": "达拉斯", "DEN": "丹佛",
    "MIA": "迈阿密", "LAX": "洛杉矶", "SFO": "旧金山", "SEA": "西雅图",
    "LAS": "拉斯维加斯", "HNL": "檀香山", "YVR": "温哥华", "YYZ": "多伦多",
    "YUL": "蒙特利尔", "MEX": "墨西哥城", "CUN": "坎昆", "GRU": "圣保罗",
    "EZE": "布宜诺斯艾利斯", "LIM": "利马", "BOG": "波哥大", "SCL": "圣地亚哥",
    "SYD": "悉尼", "MEL": "墨尔本", "BNE": "布里斯班", "PER": "珀斯",
    "AKL": "奥克兰", "JNB": "约翰内斯堡", "CAI": "开罗", "NBO": "内罗毕",
    "ADD": "亚的斯亚贝巴",
}
CN_NAME: dict[str, str] = {
    "PEK": "北京首都国际机场", "PKX": "北京大兴国际机场", "PVG": "上海浦东国际机场",
    "SHA": "上海虹桥国际机场", "CAN": "广州白云国际机场", "SZX": "深圳宝安国际机场",
    "CTU": "成都双流国际机场", "CKG": "重庆江北国际机场", "XIY": "西安咸阳国际机场",
    "HGH": "杭州萧山国际机场", "KMG": "昆明长水国际机场", "WUH": "武汉天河国际机场",
    "XMN": "厦门高崎国际机场", "TSN": "天津滨海国际机场", "TAO": "青岛胶东国际机场",
    "CSX": "长沙黄花国际机场", "NKG": "南京禄口国际机场", "SHE": "沈阳桃仙国际机场",
    "HRB": "哈尔滨太平国际机场", "DLC": "大连周水子国际机场", "HAK": "海口美兰国际机场",
    "SYX": "三亚凤凰国际机场", "URC": "乌鲁木齐地窝堡国际机场", "KWE": "贵阳龙洞堡国际机场",
    "FOC": "福州长乐国际机场", "CGO": "郑州新郑国际机场", "TNA": "济南遥墙国际机场",
    "HKG": "香港国际机场", "MFM": "澳门国际机场", "TPE": "台北桃园国际机场",
    "KHH": "高雄国际机场", "NRT": "东京成田国际机场", "HND": "东京羽田国际机场",
    "KIX": "大阪关西国际机场", "CTS": "札幌新千岁机场", "FUK": "福冈机场",
    "NGO": "名古屋中部国际机场", "OKA": "冲绳那霸机场", "ICN": "首尔仁川国际机场",
    "GMP": "首尔金浦国际机场", "PUS": "釜山金海国际机场", "SIN": "新加坡樟宜机场",
    "BKK": "曼谷素万那普国际机场", "DMK": "曼谷廊曼国际机场", "HKT": "普吉国际机场",
    "CNX": "清迈国际机场", "KUL": "吉隆坡国际机场", "CGK": "雅加达苏加诺-哈达国际机场",
    "DPS": "巴厘岛伍拉·赖国际机场", "SGN": "胡志明市新山一国际机场", "HAN": "河内内排国际机场",
    "MNL": "马尼拉尼诺·阿基诺国际机场", "PNH": "金边国际机场",
    "DEL": "德里英迪拉·甘地国际机场", "BOM": "孟买贾特拉帕蒂·希瓦吉国际机场",
    "DXB": "迪拜国际机场", "AUH": "阿布扎比国际机场", "DOH": "多哈哈马德国际机场",
    "RUH": "利雅得哈立德国王国际机场", "TLV": "特拉维夫本·古里安机场",
    "IST": "伊斯坦布尔机场", "LHR": "伦敦希思罗机场", "LGW": "伦敦盖特威克机场",
    "MAN": "曼彻斯特机场", "CDG": "巴黎戴高乐机场", "ORY": "巴黎奥利机场",
    "AMS": "阿姆斯特丹史基浦机场", "FRA": "法兰克福机场", "MUC": "慕尼黑机场",
    "BER": "柏林勃兰登堡机场", "DUS": "杜塞尔多夫机场", "HAM": "汉堡机场",
    "STR": "斯图加特机场", "CGN": "科隆波恩机场", "HAJ": "汉诺威机场",
    "NUE": "纽伦堡机场", "DRS": "德累斯顿机场", "LEJ": "莱比锡哈雷机场",
    "BRE": "不来梅机场", "FMO": "明斯特奥斯纳布吕克国际机场", "ZRH": "苏黎世机场",
    "GVA": "日内瓦机场", "MAD": "马德里巴拉哈斯机场", "BCN": "巴塞罗那埃尔普拉特机场",
    "LIS": "里斯本机场", "FCO": "罗马菲乌米奇诺机场", "MXP": "米兰马尔彭萨机场",
    "VIE": "维也纳国际机场", "CPH": "哥本哈根凯斯楚普机场", "BLL": "比隆机场",
    "AAL": "奥尔堡机场", "AAR": "奥胡斯机场", "OSL": "奥斯陆加勒穆恩机场",
    "BGO": "卑尔根弗莱斯兰机场", "SVG": "斯塔万格索拉机场", "TRD": "特隆赫姆韦尔内斯机场",
    "TOS": "特罗姆瑟朗内斯机场", "ARN": "斯德哥尔摩阿兰达机场", "GOT": "哥德堡兰德维特机场",
    "MMX": "马尔默机场", "HEL": "赫尔辛基万塔机场", "ROV": "罗瓦涅米机场",
    "KEF": "凯夫拉维克国际机场", "DUB": "都柏林机场", "BRU": "布鲁塞尔机场",
    "WAW": "华沙肖邦机场", "PRG": "布拉格瓦茨拉夫·哈维尔机场",
    "BUD": "布达佩斯李斯特·费伦茨机场", "ATH": "雅典埃莱夫塞里奥斯·韦尼泽洛斯机场",
    "SVO": "莫斯科谢列梅捷沃机场", "JFK": "纽约肯尼迪机场", "EWR": "纽约纽瓦克机场",
    "BOS": "波士顿洛根机场", "IAD": "华盛顿杜勒斯机场",
    "ATL": "亚特兰大哈茨菲尔德-杰克逊机场", "ORD": "芝加哥奥黑尔机场",
    "DFW": "达拉斯/沃思堡机场", "DEN": "丹佛国际机场", "MIA": "迈阿密国际机场",
    "LAX": "洛杉矶国际机场", "SFO": "旧金山国际机场", "SEA": "西雅图-塔科马机场",
    "LAS": "拉斯维加斯哈里·里德机场", "HNL": "檀香山丹尼尔·井上机场",
    "YVR": "温哥华国际机场", "YYZ": "多伦多皮尔逊机场", "YUL": "蒙特利尔特鲁多机场",
    "MEX": "墨西哥城国际机场", "CUN": "坎昆国际机场", "GRU": "圣保罗瓜鲁柳斯机场",
    "EZE": "布宜诺斯艾利斯埃塞萨机场", "LIM": "利马豪尔赫·查韦斯机场",
    "BOG": "波哥大埃尔多拉多机场", "SCL": "圣地亚哥阿图罗·梅里诺·贝尼特斯机场",
    "SYD": "悉尼金斯福德·史密斯机场", "MEL": "墨尔本图拉马林机场",
    "BNE": "布里斯班机场", "PER": "珀斯机场", "AKL": "奥克兰机场",
    "JNB": "约翰内斯堡奥利弗·坦博机场", "CAI": "开罗国际机场",
    "NBO": "内罗毕乔莫·肯雅塔机场", "ADD": "亚的斯亚贝巴博莱机场",
}

# 常用城市英文别名（简写/昵称）
CITY_ALIASES = {
    "nyc": "New York", "sf": "San Francisco", "la": "Los Angeles", "dc": "Washington",
}

COUNTRY_NAMES = {
    "CN": "China", "HK": "Hong Kong", "MO": "Macau", "TW": "Taiwan",
    "JP": "Japan", "KR": "South Korea", "SG": "Singapore", "TH": "Thailand",
    "MY": "Malaysia", "ID": "Indonesia", "VN": "Vietnam", "PH": "Philippines",
    "KH": "Cambodia", "IN": "India", "AE": "United Arab Emirates", "QA": "Qatar",
    "SA": "Saudi Arabia", "IL": "Israel", "TR": "Turkey", "GB": "United Kingdom",
    "FR": "France", "NL": "Netherlands", "DE": "Germany", "CH": "Switzerland",
    "ES": "Spain", "PT": "Portugal", "IT": "Italy", "AT": "Austria",
    "DK": "Denmark", "NO": "Norway", "SE": "Sweden", "FI": "Finland",
    "IS": "Iceland", "IE": "Ireland", "BE": "Belgium", "PL": "Poland",
    "CZ": "Czech Republic", "HU": "Hungary", "GR": "Greece", "RU": "Russia",
    "US": "United States", "CA": "Canada", "MX": "Mexico", "BR": "Brazil",
    "AR": "Argentina", "PE": "Peru", "CO": "Colombia", "CL": "Chile",
    "AU": "Australia", "NZ": "New Zealand", "ZA": "South Africa", "EG": "Egypt",
    "KE": "Kenya", "ET": "Ethiopia",
}

SEASONAL = [1.18, 1.08, 0.95, 0.90, 0.95, 1.15, 1.25, 1.30, 1.05, 0.95, 0.90, 1.15]
WEEKDAY = [0.88, 0.82, 0.85, 0.90, 1.10, 1.06, 1.12]

CARRIER_CODES = ["CA", "MU", "CZ", "HU", "CX", "NH", "JL", "KE", "SQ", "EK", "QR", "TK",
                 "LH", "AF", "BA", "KL", "UA", "DL", "AA", "AC", "QF", "NZ", "LX", "AY"]
CARRIER_NAMES = ["Air China", "China Eastern", "China Southern", "Hainan Airlines", "Cathay Pacific",
                 "ANA", "Japan Airlines", "Korean Air", "Singapore Airlines", "Emirates",
                 "Qatar Airways", "Turkish Airlines", "Lufthansa", "Air France", "British Airways",
                 "KLM", "United Airlines", "Delta Air Lines", "American Airlines", "Air Canada",
                 "Qantas", "Air New Zealand", "SWISS", "Finnair"]


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
            raise ProviderError(f"机场代码 {bad} 不在内置列表中，请从输入框的联想列表中选择。")

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
            out_price = _price_usd(origin, destination, dep) * (0.95 + 0.02 * k)
            out_segs = _build_segments(origin, destination, dep, h, k)
            in_segs: list[Segment] = []
            in_price = None
            if ret is not None:
                h2 = _fnv(seed + "|ret")
                in_price = _price_usd(destination, origin, ret) * (0.95 + 0.02 * k)
                in_segs = _build_segments(destination, origin, ret, h2, k)
            offers.append(FlightOffer(
                price_total=round((out_price + (in_price or 0)) * rate, 2),
                currency=currency,
                outbound=out_segs,
                inbound=in_segs,
                outbound_price=round(out_price * rate, 2),
                inbound_price=round(in_price * rate, 2) if in_price is not None else None,
            ))
        offers.sort(key=lambda o: o.price_total)
        return offers

    async def search_airports(self, query, limit=10):
        q = query.strip().lower()
        if not q:
            return []

        def score(a: Airport) -> Optional[int]:
            cn_city = CN_CITY.get(a.iata, "")
            cn_name = CN_NAME.get(a.iata, "")
            country = COUNTRY_NAMES.get(a.country, "").lower()
            if a.iata.lower() == q:
                return 0
            if a.iata.lower().startswith(q):
                return 1
            if (a.city.lower().startswith(q) or a.name.lower().startswith(q)
                    or cn_city.startswith(q) or cn_name.startswith(q)
                    or CITY_ALIASES.get(q) == a.city.lower()):
                return 2
            if q in a.city.lower() or q in a.name.lower() or q in cn_city or q in cn_name:
                return 3
            if country and (country == q or country.startswith(q) or q in country):
                return 4
            return None

        scored = [(s, a) for a in AIRPORTS.values() if (s := score(a)) is not None]
        scored.sort(key=lambda t: (t[0], t[1].iata))
        return [a for _, a in scored[:limit]]
