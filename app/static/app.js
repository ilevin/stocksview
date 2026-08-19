/* 原生 JS：自选管理页（watchlist）+ 行情首页（index）。
 * 页面通过 body[data-page] 区分，行情首页逻辑见 pollQuotes 部分（Phase 6）。 */

"use strict";

// ---------- 通用 ----------

async function api(path, options) {
  const resp = await fetch(path, options);
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = data && data.detail ? data.detail : `HTTP ${resp.status}`;
    throw new Error(detail);
  }
  return data;
}

function showMsg(el, text, kind) {
  el.textContent = text;
  el.className = `message ${kind}`;
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

const MARKET_LABEL = { CN: "A股", HK: "港股" };
const TYPE_LABEL = { STOCK: "股票", ETF: "ETF", INDEX: "指数" };

// ---------- 自选管理页 ----------

function initWatchlistPage() {
  const wlForm = document.getElementById("add-watchlist-form");
  const wlMsg = document.getElementById("wl-message");
  const idxForm = document.getElementById("add-index-form");
  const idxMsg = document.getElementById("idx-message");
  if (!wlForm) return;

  async function loadList(kind) {
    // kind: "wl" | "idx"
    const data = await api(kind === "wl" ? "/api/watchlist" : "/api/index-watchlist");
    const tbody = document.querySelector(`#${kind}-table tbody`);
    const empty = document.getElementById(`${kind}-empty`);
    tbody.innerHTML = "";
    empty.classList.toggle("hidden", data.items.length > 0);
    document.getElementById(`${kind}-table`).classList.toggle("hidden", data.items.length === 0);

    data.items.forEach((item, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${esc(item.name)}</td>
        <td>${esc(item.symbol)}</td>
        <td>${MARKET_LABEL[item.market] || item.market}${kind === "wl" && item.market === "HK" && item.delayed ? " · 延时" : ""}</td>
        ${kind === "wl" ? `<td>${TYPE_LABEL[item.asset_type] || item.asset_type}</td>` : ""}
        <td class="right">${item.sort_order}</td>
        <td>
          <button class="link" data-act="up" data-iid="${esc(item.instrument_id)}" ${i === 0 ? "disabled" : ""}>↑</button>
          <button class="link" data-act="down" data-iid="${esc(item.instrument_id)}" ${i === data.items.length - 1 ? "disabled" : ""}>↓</button>
          <button class="link danger" data-act="del" data-iid="${esc(item.instrument_id)}">删除</button>
        </td>`;
      tbody.appendChild(tr);
    });
  }

  async function refreshBoth() {
    await Promise.all([loadList("wl"), loadList("idx")]);
  }

  async function reorderFromCurrent(kind) {
    // 用当前渲染顺序重算 sort_order（步长 10）
    const rows = Array.from(document.querySelectorAll(`#${kind}-table tbody tr`));
    const ids = rows.map((r) => r.querySelector("button[data-act=del]").dataset.iid);
    const items = ids.map((iid, i) => ({ instrument_id: iid, sort_order: (i + 1) * 10 }));
    await api(kind === "wl" ? "/api/watchlist/order" : "/api/index-watchlist/order", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
  }

  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-act]");
    if (!btn) return;
    const iid = btn.dataset.iid;
    const kind = iid.includes(":INDEX:") ? "idx" : "wl";
    const act = btn.dataset.act;
    try {
      if (act === "del") {
        await api(`/${kind === "wl" ? "api/watchlist" : "api/index-watchlist"}/${encodeURIComponent(iid)}`, { method: "DELETE" });
      } else if (act === "up" || act === "down") {
        const table = document.getElementById(`${kind}-table`);
        const row = btn.closest("tr");
        if (act === "up") table.tBodies[0].insertBefore(row, row.previousSibling);
        else row.nextSibling.insertAdjacentElement("afterend", row);
        await reorderFromCurrent(kind);
      }
      await refreshBoth();
    } catch (err) {
      showMsg(kind === "wl" ? wlMsg : idxMsg, err.message, "error");
    }
  });

  wlForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: document.getElementById("wl-symbol").value.trim(),
          market: document.getElementById("wl-market").value,
          asset_type: document.getElementById("wl-type").value,
        }),
      });
      showMsg(wlMsg, "添加成功", "success");
      document.getElementById("wl-symbol").value = "";
      await refreshBoth();
    } catch (err) {
      showMsg(wlMsg, `添加失败：${err.message}`, "error");
    }
  });

  idxForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("/api/index-watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: document.getElementById("idx-symbol").value.trim(),
          market: document.getElementById("idx-market").value,
          asset_type: "INDEX",
        }),
      });
      showMsg(idxMsg, "添加成功", "success");
      document.getElementById("idx-symbol").value = "";
      await refreshBoth();
    } catch (err) {
      showMsg(idxMsg, `添加失败：${err.message}`, "error");
    }
  });

  refreshBoth().catch((err) => showMsg(wlMsg, err.message, "error"));
}

// ---------- 行情首页 ----------

const STATUS_LABEL = {
  OPEN: "交易中",
  LUNCH_BREAK: "午间休市",
  CLOSED: "已收盘",
  HOLIDAY: "休市",
};
const REFRESH_MS = 60 * 1000;
let pollTimer = null;

function chgClass(value) {
  if (value == null) return "flat";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

function fmtNum(value, digits = 2) {
  return value == null ? "-" : Number(value).toFixed(digits);
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return "-";
  // 统一显示北京时间
  return d.toLocaleTimeString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderMarketStatus(status) {
  for (const market of ["CN", "HK"]) {
    const el = document.getElementById(`status-${market}`);
    const st = status[market];
    el.textContent = `${MARKET_LABEL[market]} · ${STATUS_LABEL[st] || st || "--"}`;
    el.className = `market-badge ${st === "OPEN" ? "open" : "closed"}`;
  }
}

function renderIndices(data) {
  const box = document.getElementById("indices");
  const empty = document.getElementById("indices-empty");
  box.innerHTML = "";
  empty.classList.toggle("hidden", data.items.length > 0);
  data.items.forEach((idx) => {
    const card = document.createElement("div");
    card.className = "index-card";
    card.innerHTML = `
      <div class="name">${esc(idx.name)}</div>
      <div class="points">${fmtNum(idx.price, 2)}</div>
      <div class="chg ${chgClass(idx.change_percent)}">${fmtNum(idx.change_percent)}%${idx.is_stale ? '<span class="stale-mark">&#9888;</span>' : ""}</div>`;
    box.appendChild(card);
  });
}

function renderQuotes(data) {
  const tbody = document.querySelector("#quotes-table tbody");
  const empty = document.getElementById("quotes-empty");
  tbody.innerHTML = "";
  empty.classList.toggle("hidden", data.items.length > 0);
  document.getElementById("quotes-table").classList.toggle("hidden", data.items.length === 0);

  data.items.forEach((q) => {
    const marketText =
      MARKET_LABEL[q.market] || q.market;
    const marketCell =
      q.market === "HK" && q.delayed ? `${marketText} · 延时` : marketText;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${esc(q.name)}</td>
      <td class="muted">${esc(q.symbol)}</td>
      <td>${marketCell}</td>
      <td class="right num">${fmtNum(q.price)}</td>
      <td class="right num ${chgClass(q.change_percent)}">${fmtNum(q.change_percent)}%</td>
      <td class="right num">${fmtNum(q.volume_ratio)}</td>
      <td class="right num">${fmtNum(q.pe_ttm)}</td>
      <td class="right num">${fmtNum(q.pb)}</td>
      <td class="right num">${fmtNum(q.dividend_yield_ttm)}</td>
      <td class="right num muted">${fmtTime(q.source_timestamp)}${q.is_stale ? '<span class="stale-mark">&#9888;</span>' : ""}</td>`;
    tbody.appendChild(tr);
  });
}

function showError(text) {
  const el = document.getElementById("error-message");
  el.textContent = text;
  el.classList.remove("hidden");
}

async function fetchAndRender() {
  let quotesData = null;
  let indicesData = null;
  try {
    [quotesData, indicesData] = await Promise.all([
      api("/api/quotes"),
      api("/api/indices"),
    ]);
  } catch (err) {
    showError(`获取行情失败：${err.message}`);
    return null;
  }
  document.getElementById("error-message").classList.add("hidden");
  renderMarketStatus(quotesData.market_status);
  renderIndices(indicesData);
  renderQuotes(quotesData);
  return quotesData.market_status;
}

function schedulePolling(marketStatus) {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  // 任一市场 OPEN 时每 60 秒读取一次缓存；全部非 OPEN 停止轮询（保留已显示数据）
  const anyOpen = Object.values(marketStatus || {}).some((s) => s === "OPEN");
  if (anyOpen) {
    pollTimer = setTimeout(async () => {
      const status = await fetchAndRender();
      schedulePolling(status);
    }, REFRESH_MS);
  }
}

function initIndexPage() {
  // 首次打开：无论是否交易，立即读取一次后端缓存
  fetchAndRender()
    .then((status) => schedulePolling(status))
    .catch(() => {});
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "watchlist") initWatchlistPage();
  else if (page === "index") initIndexPage();
});
