/* FlightSearch 前端逻辑（无构建依赖，可直接部署到 GitHub Pages） */
"use strict";

/* ---------- 常量与状态 ---------- */
const LS_KEY = "flightsearch.settings.v1";
const DEFAULT_SETTINGS = { backend: "http://localhost:8000", provider: "auto" };
const ZERO_DECIMAL = new Set(["JPY", "KRW", "IDR", "INR", "TWD", "THB", "MYR", "CLP", "VND", "ISK", "HUF"]);
const HM_BUCKETS = 6;

let settings = loadSettings();
let lastResult = null;
let lastPayload = null;

function loadSettings() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch { /* 隐私模式等场景下忽略 */ }
  return { ...DEFAULT_SETTINGS };
}
function saveSettings() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(settings)); } catch { /* 忽略 */ }
}

const $ = (sel, root = document) => root.querySelector(sel);
const el = (id) => document.getElementById(id);
const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

/* ---------- 格式化工具 ---------- */
function fmtPrice(v, cur, approx = false) {
  if (v == null || isNaN(v)) return "—";
  const dec = ZERO_DECIMAL.has(cur) ? 0 : 2;
  let s;
  try {
    s = new Intl.NumberFormat("zh-CN", { style: "currency", currency: cur, minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v);
  } catch {
    s = `${cur} ${v.toFixed(dec)}`;
  }
  return (approx ? "≈ " : "") + s;
}
function fmtDateShort(iso) { return (iso || "").slice(5); }
function fmtDateCN(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${y}年${+m}月${+d}日`;
}
function fmtDuration(min) {
  if (min == null || isNaN(min)) return "—";
  const h = Math.floor(min / 60), m = min % 60;
  return h ? `${h}小时${m ? m + "分" : ""}` : `${m}分钟`;
}
function fmtTime(at) { return (at || "").replace("T", " ").slice(5, 16); }
function fmtStops(s) {
  if (s == null) return "—";
  if (s === 0) return "直飞";
  return `${s} 停`;
}

/* ---------- API 调用 ---------- */
class ApiError extends Error {
  constructor(message, status = null) { super(message); this.status = status; }
}

async function api(method, path, body, baseOverride) {
  const base = (baseOverride != null ? baseOverride : (settings.backend || "")).trim().replace(/\/+$/, "");
  let resp;
  try {
    resp = await fetch(base + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(`无法连接后端服务（${base || "未设置地址"}）。请确认后端已在电脑上运行：cd backend && ./start.sh，或到「设置」修改后端地址。`);
  }
  let data = null;
  try { data = await resp.json(); } catch { /* 非 JSON 响应 */ }
  if (!resp.ok) {
    const detail = data && data.detail;
    throw new ApiError(typeof detail === "string" ? detail : `后端返回错误（HTTP ${resp.status}）`, resp.status);
  }
  return data;
}

/* ---------- 健康检查 ---------- */
async function refreshHealth() {
  const pill = el("health-pill");
  try {
    const h = await api("GET", "/api/health");
    const src = h.amadeus_configured ? "Amadeus" : (h.serpapi_configured ? "SerpAPI" : "演示模式");
    pill.className = "pill pill-good";
    pill.textContent = "后端已连接 · " + src;
    pill.title = "后端运行正常，点击打开设置";
  } catch {
    pill.className = "pill pill-critical";
    pill.textContent = "后端未连接";
    pill.title = "无法连接后端，点击打开设置查看地址与启动说明";
  }
}

/* ---------- 机场联想 ---------- */
function setupAirportInput(inputId) {
  const input = el(inputId);
  const list = input.closest(".airport-box").querySelector(".suggest");
  let timer = null;

  const hide = () => { list.hidden = true; list.innerHTML = ""; };

  function pick(a) {
    input.value = a.iata;
    input.dataset.label = `${a.city} · ${a.name}`;
    input.title = input.dataset.label;
    hide();
  }

  function renderList(items) {
    if (!items.length) { hide(); return; }
    list.innerHTML = "";
    for (const a of items) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "suggest-item";
      row.innerHTML = `<span class="si-code">${escapeHtml(a.iata)}</span>` +
        `<span class="si-name">${escapeHtml(a.city)} · ${escapeHtml(a.name)}</span>` +
        `<span class="si-country">${escapeHtml(a.country)}</span>`;
      row.addEventListener("mousedown", (e) => { e.preventDefault(); pick(a); });
      list.appendChild(row);
    }
    list.hidden = false;
  }

  function refresh() {
    const q = input.value.trim();
    if (!q) { hide(); return; }
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const items = await api("GET", `/api/airports?q=${encodeURIComponent(q)}&provider=${encodeURIComponent(settings.provider)}&limit=8`);
        if (document.activeElement === input) renderList(items);
        else hide();
      } catch { hide(); }
    }, 250);
  }

  input.addEventListener("input", refresh);
  input.addEventListener("focus", refresh);
  input.addEventListener("blur", () => setTimeout(hide, 150));
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
}

/* ---------- 表单默认值 ---------- */
function setupDefaults() {
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const add = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };
  el("dep-from").value = add(14);
  el("dep-to").value = add(24);
  el("ret-from").value = add(30);
  el("ret-to").value = add(40);
}

/* ---------- 表单校验与搜索 ---------- */
function showFormError(msg) { const box = el("form-error"); box.textContent = msg; box.hidden = false; }
function hideFormError() { el("form-error").hidden = true; }

function validateForm() {
  const code = (v) => /^[A-Za-z]{3}$/.test(v.trim());
  if (!code(el("origin").value)) return "出发地请填写 3 位机场代码（IATA），可从输入框的联想列表中选择。";
  if (!code(el("dest").value)) return "目的地请填写 3 位机场代码（IATA），可从输入框的联想列表中选择。";
  if (el("origin").value.trim().toUpperCase() === el("dest").value.trim().toUpperCase()) return "出发地与目的地不能相同。";
  const df = el("dep-from").value, dt = el("dep-to").value;
  if (!df || !dt) return "请选择出发日期区间。";
  if (df > dt) return "出发开始日期不能晚于结束日期。";
  if (!el("oneway").checked) {
    const rf = el("ret-from").value, rt = el("ret-to").value;
    if (!rf || !rt) return "请选择返程日期区间，或勾选「单程」。";
    if (rf > rt) return "返程开始日期不能晚于结束日期。";
    if (rt <= df) return "返程日期必须晚于出发日期。";
  }
  return null;
}

function buildPayload() {
  const p = {
    origin: el("origin").value.trim().toUpperCase(),
    destination: el("dest").value.trim().toUpperCase(),
    departure_window: { frm: el("dep-from").value, to: el("dep-to").value },
    adults: +el("adults").value,
    currency: el("currency").value,
    non_stop: el("nonstop").checked,
    provider: settings.provider,
    max_combos: 60,
  };
  if (!el("oneway").checked) p.return_window = { frm: el("ret-from").value, to: el("ret-to").value };
  return p;
}

function setLoading(on) {
  const btn = el("search-btn");
  btn.disabled = on;
  btn.textContent = on ? "搜索中…" : "搜索最低价";
}

async function onSearch(e) {
  e.preventDefault();
  const err = validateForm();
  if (err) { showFormError(err); return; }
  hideFormError();
  setLoading(true);
  try {
    lastPayload = buildPayload();
    const data = await api("POST", "/api/search", lastPayload);
    lastResult = data;
    renderResults(data);
    el("results").scrollIntoView({ behavior: "smooth", block: "start" });
    refreshHealth();
  } catch (err2) {
    showFormError(err2.message + (err2.status === 502 ? "（也可以在「设置」中切换为演示数据后重试）" : ""));
    el("results").hidden = true;
  } finally {
    setLoading(false);
  }
}

/* ---------- 结果渲染 ---------- */
function renderResults(d) {
  el("results").hidden = false;
  el("empty-state").hidden = true;

  const notice = el("notice");
  if (d.fallback_reason) { notice.hidden = false; notice.innerHTML = `⚠️ ${escapeHtml(d.fallback_reason)}`; }
  else notice.hidden = true;

  const best = d.combos[0];
  el("stat-best").textContent = best ? fmtPrice(best.total_price, d.currency, best.approx) : "—";
  el("stat-best-note").textContent = best
    ? (best.return_date ? `去 ${fmtDateShort(best.outbound_date)} · 返 ${fmtDateShort(best.return_date)}` : `出发 ${fmtDateShort(best.outbound_date)}（单程）`)
    : "";
  el("stat-count").textContent = (d.combos_checked || 0).toLocaleString("zh-CN") + " 种";
  el("stat-provider").textContent = d.provider === "mock" ? "演示数据" : "Amadeus";
  el("stat-provider-note").textContent = d.provider === "mock" ? "模拟价格" : "真实价格";

  renderHeatmap(d);
  renderCombos(d);
}

/* ---------- 热力图 ---------- */
function renderHeatmap(d) {
  const wrap = el("heatmap");
  wrap.innerHTML = "";
  const out = d.outbound_dates, ret = d.return_dates;
  const oneWay = !ret || ret.length === 0;

  const values = [];
  if (oneWay) {
    for (const o of out) values.push(o.price);
  } else {
    for (const o of out) for (const r of ret) if (r.date > o.date) values.push(o.price + r.price);
  }
  if (!values.length) { wrap.innerHTML = `<p class="hint">没有可用的日期组合。</p>`; return; }
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const bucket = (v) => Math.min(HM_BUCKETS - 1, Math.floor(((v - min) / range) * HM_BUCKETS));

  const grid = document.createElement("div");
  grid.className = "hm-grid";

  if (oneWay) {
    grid.style.gridTemplateColumns = `92px repeat(${out.length}, var(--hm-cell))`;
    const corner = document.createElement("div");
    corner.className = "hm-corner"; corner.textContent = "出发日期";
    grid.appendChild(corner);
    for (const o of out) {
      const cell = mkCell(o.date, null, o.price, o.approx, bucket(o.price), d, o, null);
      grid.appendChild(cell);
    }
  } else {
    grid.style.gridTemplateColumns = `92px repeat(${ret.length}, var(--hm-cell))`;
    const corner = document.createElement("div");
    corner.className = "hm-corner hm-top hm-left";
    corner.textContent = "去程 ↓ 返程 →";
    grid.appendChild(corner);
    for (const r of ret) {
      const h = document.createElement("div");
      h.className = "hm-axis hm-top";
      h.textContent = fmtDateShort(r.date);
      grid.appendChild(h);
    }
    for (const o of out) {
      const axis = document.createElement("div");
      axis.className = "hm-axis hm-left";
      axis.textContent = fmtDateShort(o.date);
      grid.appendChild(axis);
      for (const r of ret) {
        const valid = r.date > o.date;
        const total = o.price + r.price;
        grid.appendChild(valid
          ? mkCell(o.date, r.date, total, o.approx || r.approx, bucket(total), d, o, r)
          : emptyCell());
      }
    }
  }
  wrap.appendChild(grid);
  renderLegend(d, min, max);
}

function emptyCell() {
  const cell = document.createElement("div");
  cell.className = "hm-cell hm-none";
  cell.setAttribute("aria-hidden", "true");
  return cell;
}

function mkCell(depDate, retDate, total, approx, bucketIndex, d, o, r) {
  const cell = document.createElement("div");
  cell.className = `hm-cell hm-b${bucketIndex}`;
  cell.setAttribute("role", "button");
  cell.setAttribute("tabindex", "0");
  cell.setAttribute("aria-label", retDate
    ? `去程 ${depDate}，返程 ${retDate}，合计 ${fmtPrice(total, d.currency, approx)}`
    : `出发 ${depDate}，价格 ${fmtPrice(total, d.currency, approx)}`);

  cell.addEventListener("mousemove", (e) => {
    const t = el("tooltip");
    t.hidden = false;
    if (retDate) {
      t.innerHTML =
        `<div class="tt-title">${fmtDateCN(depDate)} → ${fmtDateCN(retDate)}</div>` +
        `<div class="tt-row"><span>去程</span><span>${fmtPrice(o.price, d.currency, o.approx)}</span></div>` +
        `<div class="tt-row"><span>返程</span><span>${fmtPrice(r.price, d.currency, r.approx)}</span></div>` +
        `<div class="tt-total">合计 ${fmtPrice(total, d.currency, approx)}</div>`;
    } else {
      t.innerHTML =
        `<div class="tt-title">${fmtDateCN(depDate)} 出发</div>` +
        `<div class="tt-total">${fmtPrice(total, d.currency, approx)}</div>`;
    }
    positionTooltip(e.clientX, e.clientY);
  });
  cell.addEventListener("mouseleave", () => { el("tooltip").hidden = true; });
  cell.addEventListener("click", () => {
    el("tooltip").hidden = true;
    openDetail({
      outbound_date: depDate,
      return_date: retDate,
      outbound_price: retDate ? o.price : total,
      return_price: retDate ? r.price : null,
      total_price: total,
      approx,
    });
  });
  cell.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); cell.click(); } });
  return cell;
}

function positionTooltip(x, y) {
  const t = el("tooltip");
  const pad = 14;
  const w = t.offsetWidth || 200, h = t.offsetHeight || 90;
  let left = x + pad, top = y + pad;
  if (left + w > window.innerWidth - 8) left = x - w - pad;
  if (top + h > window.innerHeight - 8) top = y - h - pad;
  t.style.left = `${Math.max(4, left)}px`;
  t.style.top = `${Math.max(4, top)}px`;
}

function renderLegend(d, min, max) {
  el("legend").innerHTML =
    `<span class="leg-min">${fmtPrice(min, d.currency)}</span>` +
    `<span class="leg-bar"></span>` +
    `<span class="leg-max">${fmtPrice(max, d.currency)}</span>` +
    `<span class="leg-cap">低 → 高</span>`;
}

/* ---------- 组合列表 ---------- */
function renderCombos(d) {
  const box = el("combos");
  box.innerHTML = "";
  el("combos-hint").textContent = d.combos.some((c) => c.approx) ? "≈ 为参考汇率换算" : "";
  if (!d.combos.length) {
    box.innerHTML = `<p class="hint">没有符合条件的组合，请调整日期区间。</p>`;
    return;
  }
  const oneWay = !d.combos[0].return_date;

  d.combos.forEach((c, i) => {
    const row = document.createElement("div");
    row.className = "combo";
    row.innerHTML =
      `<span class="rank">${i + 1}</span>` +
      `<div class="c-dates">` +
        `<div class="c-seg">✈ 去 <b>${fmtDateShort(c.outbound_date)}</b></div>` +
        (c.return_date ? `<div class="c-seg">✈ 返 <b>${fmtDateShort(c.return_date)}</b></div>` : "") +
      `</div>` +
      `<div class="c-prices">` +
        `<span>去程 ${fmtPrice(c.outbound_price, d.currency, c.approx)}</span>` +
        (c.return_date ? `<span>返程 ${fmtPrice(c.return_price, d.currency, c.approx)}</span>` : "") +
      `</div>` +
      `<div class="c-total">${fmtPrice(c.total_price, d.currency, c.approx)}` +
        (i === 0 ? `<span class="best-tag">最低</span>` : "") +
      `</div>` +
      `<div class="c-stops">去 ${fmtStops(c.outbound_stops)}` +
        (c.return_date ? ` · 返 ${fmtStops(c.return_stops)}` : "") +
      `</div>` +
      `<button type="button" class="btn-ghost c-detail">航班详情</button>`;
    row.querySelector(".c-detail").addEventListener("click", () => openDetail(c));
    box.appendChild(row);
  });
  if (!oneWay) {
    box.insertAdjacentHTML("beforeend",
      `<p class="hint" style="margin-top:10px">价格日历与组合基于每天最低单程票价计算，点「航班详情」可查看该日期组合的具体航班报价。</p>`);
  }
}

/* ---------- 航班详情弹窗 ---------- */
async function openDetail(c) {
  const modal = el("detail-modal");
  const body = el("detail-body");
  const title = el("detail-title");
  modal.hidden = false;
  const p = lastPayload;
  title.textContent = p
    ? `${p.origin} → ${p.destination} · ${c.return_date ? `去 ${fmtDateCN(c.outbound_date)} / 返 ${fmtDateCN(c.return_date)}` : `单程 ${fmtDateCN(c.outbound_date)}`}`
    : "航班详情";
  updateGfLink(c);
  body.innerHTML = `<p class="loading">正在获取航班详情…</p>`;
  try {
    const qs = new URLSearchParams({
      origin: p.origin, destination: p.destination,
      departure_date: c.outbound_date,
      adults: p.adults, currency: p.currency,
      provider: settings.provider, max: 8,
    });
    if (c.return_date) qs.set("return_date", c.return_date);
    const data = await api("GET", `/api/offers?${qs.toString()}`);
    renderOffers(data.offers, body);
  } catch (err) {
    body.innerHTML = `<p class="form-error">${escapeHtml(err.message)}</p>` +
      `<p class="hint">你也可以直接点击下方按钮，在 Google Flights 查看该组合。</p>`;
  }
}

function updateGfLink(c) {
  const p = lastPayload;
  const link = el("detail-gf");
  if (!p) { link.hidden = true; return; }
  link.hidden = false;
  const q = c.return_date
    ? `Flights from ${p.origin} to ${p.destination} on ${c.outbound_date} returning ${c.return_date}`
    : `Flights from ${p.origin} to ${p.destination} on ${c.outbound_date}`;
  link.href = `https://www.google.com/travel/flights?q=${encodeURIComponent(q)}`;
}

function renderOffers(offers, body) {
  if (!offers || !offers.length) {
    body.innerHTML = `<p class="hint">该日期组合暂时没有可展示的航班报价。</p>`;
    return;
  }
  body.innerHTML = offers.map((o, i) => {
    const breakdown = (o.outbound_price != null && o.inbound_price != null)
      ? `<span class="hint">去程 ${fmtPrice(o.outbound_price, o.currency)} + 返程 ${fmtPrice(o.inbound_price, o.currency)}</span>`
      : "";
    return `
    <div class="offer">
      <div class="offer-head">
        <span class="offer-price">${fmtPrice(o.price_total, o.currency)}${i === 0 ? '<span class="best-tag">最低</span>' : ""}</span>
        <span class="hint">${breakdown}${breakdown ? " · " : ""}总时长 ${fmtDuration((o.outbound_duration_minutes || 0) + (o.inbound_duration_minutes || 0))}</span>
      </div>
      ${journeyHtml("去程", o.outbound)}
      ${o.inbound && o.inbound.length ? journeyHtml("返程", o.inbound) : ""}
    </div>`;
  }).join("");
  if (offers.some((o) => o.inbound && o.inbound.length)) {
    body.insertAdjacentHTML("beforeend", `<p class="hint">价格为两段单程票价之和，往返同订可能有更优票价，可在 Google Flights 中确认。</p>`);
  }
}

function journeyHtml(title, segs) {
  const parts = segs.map((s, i) => {
    let layover = "";
    if (i < segs.length - 1) {
      const lay = layoverMinutes(segs[i].arrival_at, segs[i + 1].departure_at);
      layover = `<div class="j-layover">↳ 中转 ${escapeHtml(s.arrival_iata)} · 约 ${fmtDuration(lay)}</div>`;
    }
    return `<div class="j-seg">
      <div class="j-times"><b>${fmtTime(s.departure_at)}</b> → <b>${fmtTime(s.arrival_at)}</b><span class="j-dur">${fmtDuration(s.duration_minutes)}</span></div>
      <div class="j-airports">${escapeHtml(s.departure_iata)} → ${escapeHtml(s.arrival_iata)}</div>
      <div class="j-flight">${escapeHtml(s.carrier_name || s.carrier_code || "")} ${escapeHtml(s.flight_number || "")}</div>
    </div>${layover}`;
  }).join("");
  return `<div class="journey"><div class="j-title">${title}</div>${parts}</div>`;
}

function layoverMinutes(arrIso, depIso) {
  if (!arrIso || !depIso) return 0;
  const a = new Date(arrIso), b = new Date(depIso);
  if (isNaN(a) || isNaN(b)) return 0;
  return Math.max(0, Math.round((b - a) / 60000));
}

/* ---------- 弹窗与设置 ---------- */
function bindModals() {
  el("detail-close").addEventListener("click", () => { el("detail-modal").hidden = true; });
  for (const id of ["settings-modal", "detail-modal"]) {
    el(id).addEventListener("click", (e) => { if (e.target === el(id)) el(id).hidden = true; });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      el("settings-modal").hidden = true;
      el("detail-modal").hidden = true;
      el("tooltip").hidden = true;
    }
  });
}

function bindSettings() {
  el("settings-btn").addEventListener("click", openSettings);
  el("health-pill").addEventListener("click", openSettings);

  function openSettings() {
    el("set-backend").value = settings.backend;
    el("set-provider").value = settings.provider;
    el("conn-result").textContent = "";
    el("settings-modal").hidden = false;
  }

  el("save-settings").addEventListener("click", () => {
    settings.backend = el("set-backend").value.trim().replace(/\/+$/, "");
    settings.provider = el("set-provider").value;
    saveSettings();
    el("settings-modal").hidden = true;
    refreshHealth();
  });

  el("test-conn").addEventListener("click", async () => {
    const base = el("set-backend").value.trim().replace(/\/+$/, "");
    const res = el("conn-result");
    res.textContent = "测试中…";
    try {
      const h = await api("GET", "/api/health", null, base);
      const src = h.amadeus_configured ? "Amadeus" : (h.serpapi_configured ? "SerpAPI" : "演示模式");
      res.textContent = `✅ 连接成功 · 数据源 ${src}（后端 v${h.version}）`;
    } catch (err) {
      res.textContent = `❌ ${err.message}`;
    }
  });
}

/* ---------- 其它交互 ---------- */
function bindMisc() {
  el("swap").addEventListener("click", () => {
    const a = el("origin"), b = el("dest");
    [a.value, b.value] = [b.value, a.value];
    [a.dataset.label, b.dataset.label] = [b.dataset.label || "", a.dataset.label || ""];
    a.title = a.dataset.label || ""; b.title = b.dataset.label || "";
  });
  el("oneway").addEventListener("change", () => {
    const on = el("oneway").checked;
    el("ret-from").disabled = on;
    el("ret-to").disabled = on;
    el("return-field").style.opacity = on ? ".45" : "1";
  });
  el("search-form").addEventListener("submit", onSearch);
}

/* ---------- 初始化 ---------- */
function init() {
  setupAirportInput("origin");
  setupAirportInput("dest");
  setupDefaults();
  bindMisc();
  bindSettings();
  bindModals();
  refreshHealth();
}
document.addEventListener("DOMContentLoaded", init);
