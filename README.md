# FlightSearch · 机票低价日历

在**指定的时间段内**查找两个目的地之间**最便宜的往返组合**：输入出发地、目的地和日期区间，得到区间内每一天的价格热力图 + 最便宜的「去程 × 返程」组合列表，点击组合可查看具体航班（航司、时刻、中转）。

## 架构

```
┌──────────────────────────┐          HTTPS          ┌────────────────────────────┐
│  GitHub Pages 前端        │ ──────────────────────► │  你的电脑（localhost）       │
│  frontend/ 纯静态页面      │  fetch → localhost:8000 │  FastAPI 后端（backend/）    │
│                          │                         │  ├ Amadeus 免费API（真实价格）│
│  也可直接访问             │                         │  └ 演示数据（模拟价格，无需密钥）│
│  http://localhost:8000    │                         │                            │
└──────────────────────────┘                         └────────────────────────────┘
```

- **后端**：FastAPI + [Amadeus Self-Service API](https://developers.amadeus.com/)（免费测试环境），低价日历接口 `flight-dates` 一次查询返回区间内每天的最低票价，后端把去程 × 返程组合出所有日期组合并按总价排序。内置缓存减少 API 配额消耗。
- **前端**：纯 HTML/CSS/JS（无构建），部署在 GitHub Pages；通过 `fetch` 访问本机后端（已处理 CORS 与 Chrome Private Network Access 预检）。
- **数据源可扩展**：`backend/providers/base.py` 定义了 Provider 接口，新增平台只需实现 3 个方法并在 `main.py` 注册。

> 为什么用 Amadeus 而不是 Skyscanner：Skyscanner 没有公开免费 API（仅面向企业合作伙伴）。Amadeus 为开发者提供免费自助测试环境，包含低价日历与航班报价接口。

## 快速开始

### 1. 启动后端（在你的电脑上）

```bash
cd backend
./setup.sh     # 首次：创建虚拟环境并安装依赖
./start.sh     # 启动，监听 http://localhost:8000
```

启动后直接访问 **http://localhost:8000** 即可使用完整应用（后端同时托管前端页面）。未配置密钥时使用**演示数据**（模拟价格），开箱即用。

### 2. （可选）接入 Amadeus 真实价格

1. 注册 https://developers.amadeus.com → **My Self-Service Workspace → My Apps → Create new app**，环境选 **Test**；
2. 把 API Key / API Secret 填入 `backend/.env`（复制自 `.env.example`）；
3. 重启后端，页面数据源即自动切换为 Amadeus。

> 免费测试环境有调用配额（低价日历约 2000 次/月），后端已内置结果缓存。测试环境的数据与价格仅用于开发验证。

### 3. 部署前端到 GitHub Pages

1. 把仓库 push 到 GitHub（当前已是 git 仓库）；
2. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**；
3. 之后每次推送 `frontend/` 的改动，workflow 会自动发布到 `https://<用户名>.github.io/flightsearch/`。

打开 GitHub Pages 页面后，它会连接你电脑上的 `http://localhost:8000` 后端（页面右上角「设置」可修改后端地址）。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（数据源状态） |
| GET | `/api/airports?q=…` | 机场/城市联想搜索 |
| POST | `/api/search` | 区间低价搜索：去程×返程组合 + 每天最低价 |
| GET | `/api/offers?origin=…&departure_date=…` | 指定日期组合的具体航班报价 |

`POST /api/search` 请求示例：

```json
{
  "origin": "SFO",
  "destination": "NRT",
  "departure_window": { "frm": "2026-12-01", "to": "2026-12-10" },
  "return_window":    { "frm": "2026-12-15", "to": "2026-12-20" },
  "adults": 1,
  "currency": "CNY",
  "non_stop": false,
  "provider": "auto"
}
```

## 常见问题

- **页面提示「后端未连接」**：确认后端已在本机启动（`cd backend && ./start.sh`）；若前端部署在 GitHub Pages，请确认浏览器允许页面访问 localhost（Chrome/Safari/Firefox 均支持，后端已返回 PNA 预检头）。最简单的验证方式：直接打开 `http://localhost:8000`。
- **价格为什么带 ≈**：Amadeus 低价日历接口返回航线本地币种，后端按静态参考汇率换算成所选货币，仅供参考。
- **想从手机访问**：把 `backend/.env` 中 `HOST` 改为 `0.0.0.0` 并重启，手机浏览器直接访问 `http://<电脑局域网IP>:8000`（HTTP 页面访问 HTTP 后端，无跨域限制）。
- **切换生产环境**：`AMADEUS_ENV=production`（需在 Amadeus 申请生产环境，通过审核后可用真实价格数据）。

## 目录结构

```
backend/
  main.py            # FastAPI 应用：/api/search 等接口 + 托管前端
  config.py          # .env 配置加载
  currency.py        # 静态参考汇率换算
  cache.py           # TTL 内存缓存
  providers/
    base.py          # Provider 抽象接口（扩展新平台在此实现）
    mock.py          # 演示数据源（130+ 机场，模拟价格）
    amadeus.py       # Amadeus Self-Service API（真实价格）
frontend/            # 前端（部署到 GitHub Pages）
  index.html  css/style.css  js/app.js
```

## 免责声明

价格信息来自第三方数据源，仅供参考，实际价格以航司或 OTA 为准；演示数据为模拟生成，不构成任何出行建议。
