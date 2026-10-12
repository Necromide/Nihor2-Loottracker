"use strict";
/* Nihor2 - Loottracker dashboard. Plain JS, no build step, no external libraries. */

// ---------------------------------------------------------------- utilities
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("lt_" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("lt_" + k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
};

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch("/api/" + path, opt);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

const S = {
  lang: "de",
  status: null,
  route: "overview",
  sub: "elite",
  portals: ["elite", "mystic", "greater"],
  categories: [],
  filter: null,
  report: null,
  reportKey: null,
  lastLines: null,
  sort: store.get("sort", {}),
  runsOffset: 0,
  filterOpen: store.get("filterOpen", false),
};

function t(key, vars) {
  const d = (window.I18N[S.lang] || window.I18N.de);
  let s = d[key] ?? window.I18N.de[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split("{" + k + "}").join(v);
  return s;
}
const locale = () => (S.lang === "de" ? "de-DE" : "en-GB");
const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString(locale()));
const fmtNum = (n, d = 2) => (n == null ? "–" : n.toLocaleString(locale(), { maximumFractionDigits: d, minimumFractionDigits: 0 }));
function fmtPct(p, d) {
  if (p == null) return "–";
  const v = p * 100;
  if (d == null) d = v >= 10 ? 1 : v >= 1 ? 2 : 3;
  return v.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d }) + " %";
}
function fmtCompact(n) {
  if (n == null) return "–";
  const a = Math.abs(n);
  if (a >= 1e9) return fmtNum(n / 1e9, 2) + (S.lang === "de" ? " Mrd." : "B");
  if (a >= 1e6) return fmtNum(n / 1e6, 2) + (S.lang === "de" ? " Mio." : "M");
  if (a >= 1e4) return fmtNum(n / 1e3, 1) + "k";
  return fmtInt(n);
}
const pad = (n) => String(n).padStart(2, "0");
function fmtDate(ts, withTime = true) {
  if (ts == null) return "–";
  const d = new Date(ts * 1000);
  const date = S.lang === "de"
    ? `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`
    : `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  return withTime ? `${date} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}` : date;
}
function fmtDur(sec) {
  if (sec == null) return "–";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h} ${t("h")} ${pad(m)} ${t("min")}`;
  if (m) return `${m}:${pad(s)} ${t("min")}`;
  return `${s} ${t("s")}`;
}
function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec));
  return `${pad(Math.floor(sec / 3600))}:${pad(Math.floor((sec % 3600) / 60))}:${pad(sec % 60)}`;
}
// "now" in the same naive-local seconds the log uses
const nowNaive = () => Math.floor((Date.now() - new Date().getTimezoneOffset() * 60000) / 1000);
const toInput = (ts) => (ts == null ? "" : new Date(ts * 1000).toISOString().slice(0, 16));
const fromInput = (v) => (v ? Math.floor(Date.parse(v + ":00Z") / 1000) : null);
const portalColor = (k) => `var(--s-${k}, var(--accent))`;
const portalName = (k) => t("portal_" + k);

// ---------------------------------------------------------------- filters
function defaultFilter() {
  return { preset: "all", from: null, to: null, portals: S.portals.slice(), se: "all", se_conf: "all",
    chest: "exclude", outside: "exclude", sessions: [], category: "", search: "",
    weekdays: [0, 1, 2, 3, 4, 5, 6], hour_from: 0, hour_to: 23, min_runs: 30 };
}
function presetRange(p) {
  const now = nowNaive();
  const day = Math.floor(now / 86400) * 86400;
  const d = new Date(now * 1000);
  const monthStart = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000;
  const lastMonthStart = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 1, 1) / 1000;
  switch (p) {
    case "today": return [day, null];
    case "yesterday": return [day - 86400, day - 1];
    case "7d": return [day - 6 * 86400, null];
    case "30d": return [day - 29 * 86400, null];
    case "month": return [monthStart, null];
    case "lastmonth": return [lastMonthStart, monthStart - 1];
    case "custom": return [S.filter.from, S.filter.to];
    default: return [null, null];
  }
}
function apiFilter(extra) {
  const f = S.filter;
  const [from, to] = presetRange(f.preset);
  const o = { from, to, portals: f.portals, se: f.se, se_conf: f.se_conf, chest: f.chest, outside: f.outside,
    sessions: f.sessions, category: f.category || null, search: f.search || null, weekdays: f.weekdays,
    hour_from: f.hour_from, hour_to: f.hour_to };
  return Object.assign(o, extra || {});
}
function saveFilter() { store.set("filter", S.filter); }

function renderFilterbar() {
  const bar = $("#filterbar");
  const show = ["overview", "portals", "se", "runs", "drops"].includes(S.route) && S.status && S.status.client_check.ok;
  bar.classList.toggle("hidden", !show);
  if (!show) return;
  const f = S.filter;
  const sel = (name, opts, val) => `<select data-f="${name}">${opts.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(val) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  const tri = (name) => sel(name, [["exclude", t("f_exclude")], ["include", t("f_include")], ["only", t("f_only")]], f[name]);
  const presets = ["all", "today", "yesterday", "7d", "30d", "month", "lastmonth", "custom"];
  const sessOpts = [["", t("f_sessions_none")]].concat((S.sessionsCache || []).map((s) => [String(s.id), s.name]));
  const hours = Array.from({ length: 24 }, (_, i) => [i, pad(i) + ":00"]);
  bar.innerHTML = `
    <div class="fgroup"><span>${t("f_period")}</span><div class="row">
      ${sel("preset", presets.map((p) => [p, t("p_" + p)]), f.preset)}
      ${f.preset === "custom" ? `<input type="datetime-local" data-f="from" value="${toInput(f.from)}" aria-label="${t("f_from")}">–<input type="datetime-local" data-f="to" value="${toInput(f.to)}" aria-label="${t("f_to")}">` : ""}
    </div></div>
    <div class="fgroup"><span>${t("f_portals")}</span><div class="chips">
      ${S.portals.map((p) => `<span class="chip ${f.portals.includes(p) ? "on" : ""}" data-portal="${p}"><i class="dot" style="background:${portalColor(p)}"></i>${esc(portalName(p))}</span>`).join("")}
    </div></div>
    <div class="fgroup"><span>${t("f_chest")}</span>${tri("chest")}</div>
    <div class="fgroup"><span>${t("f_outside")}</span>${tri("outside")}</div>
    <div class="fgroup"><span>${t("f_search")}</span><input type="search" data-f="search" value="${esc(f.search)}" placeholder="…" style="width:150px"></div>
    <div class="filter-extra ${S.filterOpen ? "" : "collapsed"}">
      <div class="fgroup"><span>${t("f_se")}</span>${sel("se", [["all", t("f_se_all")], ["with", t("f_se_with")], ["without", t("f_se_without")]], f.se)}</div>
      <div class="fgroup"><span>${t("f_conf")}</span>${sel("se_conf", [["all", t("f_conf_all")], ["confirmed", t("f_conf_confirmed")]], f.se_conf)}</div>
      <div class="fgroup"><span>${t("f_sessions")}</span>${sel("session", sessOpts, f.sessions[0] ?? "")}</div>
      <div class="fgroup"><span>${t("f_category")}</span>${sel("category", [["", t("f_all")]].concat(S.categories.map((c) => [c.key, c[S.lang] || c.key])), f.category)}</div>
      <div class="fgroup"><span>${t("f_weekdays")}</span><div class="chips">${t("wd").map((w, i) => `<span class="chip ${f.weekdays.includes(i) ? "on" : ""}" data-wd="${i}">${w}</span>`).join("")}</div></div>
      <div class="fgroup"><span>${t("f_hours")}</span><div class="row">${sel("hour_from", hours, f.hour_from)}–${sel("hour_to", hours.map(([i]) => [i, pad(i) + ":59"]), f.hour_to)}</div></div>
      <div class="fgroup"><span>${t("f_minruns")}</span><input type="number" min="0" data-f="min_runs" value="${f.min_runs}"></div>
    </div>
    <div class="fgroup more"><span>&nbsp;</span><div class="row">
      <button class="ghost small" id="f-more">${S.filterOpen ? t("f_less") : t("f_more")}</button>
      <button class="ghost small" id="f-reset">${t("f_reset")}</button></div></div>`;

  bar.querySelectorAll("[data-f]").forEach((el) => {
    const ev = el.type === "search" ? "input" : "change";
    el.addEventListener(ev, () => {
      const k = el.dataset.f;
      let v = el.value;
      if (k === "from" || k === "to") v = fromInput(v);
      if (["hour_from", "hour_to", "min_runs"].includes(k)) v = Number(v);
      if (k === "session") { f.sessions = v ? [Number(v)] : []; }
      else if (k === "preset" && v === "custom") {
        const [a, b] = presetRange(f.preset); f.from = a; f.to = b; f.preset = v;
      } else f[k] = v;
      saveFilter();
      if (k === "preset") renderFilterbar();
      if (k === "min_runs") return renderView();
      clearTimeout(S.fTimer);
      S.fTimer = setTimeout(refresh, k === "search" ? 350 : 0);
    });
  });
  bar.querySelectorAll("[data-portal]").forEach((el) => el.addEventListener("click", () => {
    const p = el.dataset.portal;
    f.portals = f.portals.includes(p) ? f.portals.filter((x) => x !== p) : f.portals.concat(p);
    if (!f.portals.length) f.portals = [p];
    saveFilter(); renderFilterbar(); refresh();
  }));
  bar.querySelectorAll("[data-wd]").forEach((el) => el.addEventListener("click", () => {
    const i = Number(el.dataset.wd);
    f.weekdays = f.weekdays.includes(i) ? f.weekdays.filter((x) => x !== i) : f.weekdays.concat(i).sort();
    if (!f.weekdays.length) f.weekdays = [i];
    saveFilter(); renderFilterbar(); refresh();
  }));
  $("#f-more").onclick = () => { S.filterOpen = !S.filterOpen; store.set("filterOpen", S.filterOpen); renderFilterbar(); };
  $("#f-reset").onclick = () => { S.filter = defaultFilter(); saveFilter(); renderFilterbar(); refresh(); };
}

// ---------------------------------------------------------------- tooltip & modal
const tip = $("#tooltip");
function showTip(html, ev) {
  tip.innerHTML = html; tip.classList.remove("hidden");
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
  if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
const hideTip = () => tip.classList.add("hidden");
function openModal(html) { $("#modal-body").innerHTML = html; $("#modal").classList.remove("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal" || e.target.dataset.close !== undefined) $("#modal").classList.add("hidden"); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#modal").classList.add("hidden"); });

// ---------------------------------------------------------------- tables
function table(el, id, cols, rows, opts = {}) {
  const st = S.sort[id] || opts.defaultSort || { key: cols[0].key, asc: false };
  const col = cols.find((c) => c.key === st.key) || cols[0];
  const sv = col.sort || ((r) => r[col.key]);
  const sorted = rows.slice().sort((a, b) => {
    const x = sv(a), y = sv(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    const c = typeof x === "string" ? x.localeCompare(y) : x - y;
    return st.asc ? c : -c;
  });
  const limit = opts.limit || 500;
  const shown = sorted.slice(0, limit);
  el.innerHTML = `<div class="tablewrap"><table><thead><tr>${cols.map((c) =>
    `<th data-k="${c.key}" class="${c.num ? "num" : ""} ${c.key === col.key ? "sorted" + (st.asc ? " asc" : "") : ""}">${esc(c.label)}</th>`).join("")}</tr></thead>
    <tbody>${shown.map((r, i) => `<tr data-i="${i}" class="${opts.rowClass ? opts.rowClass(r) : ""} ${opts.onRow ? "click" : ""}">${cols.map((c) =>
      `<td class="${c.num ? "num" : ""} ${c.cls || ""}">${c.html ? c.html(r) : esc(c.fmt ? c.fmt(r[c.key], r) : r[c.key])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    ${sorted.length > limit ? `<p class="muted">${shown.length} / ${sorted.length}</p>` : ""}
    ${rows.length ? "" : `<div class="empty">${t("no_data")}</div>`}`;
  el.querySelectorAll("th").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.k;
    S.sort[id] = { key: k, asc: st.key === k ? !st.asc : false };
    store.set("sort", S.sort);
    table(el, id, cols, rows, opts);
  }));
  if (opts.onRow) el.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", (e) => {
    if (e.target.closest("button, input")) return;
    opts.onRow(shown[Number(tr.dataset.i)]);
  }));
  if (opts.after) opts.after(el, shown);
}

// ---------------------------------------------------------------- charts
function niceMax(v) {
  if (v <= 0) return 1;
  const e = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * e >= v) return m * e;
  return 10 * e;
}
/** Stacked daily bars. series: [{key,label,color}], data: [{day, [key]: number}] */
function barChart(el, series, data, opts = {}) {
  const W = Math.max(320, el.clientWidth || 800), H = opts.height || 220;
  const m = { l: 56, r: 10, t: 8, b: 26 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  if (!data.length) { el.innerHTML = `<div class="empty">${t("no_data")}</div>`; return; }
  const totals = data.map((d) => series.reduce((s, x) => s + (d[x.key] || 0), 0));
  const max = 4 * niceMax(Math.max(...totals) / 4);
  const step = iw / data.length;
  const bw = Math.max(1, Math.min(28, step - (step > 4 ? 2 : 0.5)));
  const fy = opts.fmt || fmtInt;
  let g = `<g class="grid">`;
  for (let i = 0; i <= 4; i++) {
    const y = m.t + ih - (ih * i) / 4;
    g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}"/>`;
  }
  g += `</g><g class="axis">`;
  for (let i = 0; i <= 4; i++) g += `<text x="${m.l - 8}" y="${m.t + ih - (ih * i) / 4 + 4}" text-anchor="end">${esc(fy((max * i) / 4))}</text>`;
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.floor(iw / 80)));
  data.forEach((d, i) => {
    if (i % labelEvery === 0) g += `<text x="${m.l + step * i + step / 2}" y="${H - 6}" text-anchor="middle">${esc(fmtDate(d.day, false).slice(0, S.lang === "de" ? 6 : 10).replace(/^(\d{4})-/, ""))}</text>`;
  });
  g += `</g>`;
  let bars = "";
  data.forEach((d, i) => {
    let y = m.t + ih;
    const x = m.l + step * i + (step - bw) / 2;
    const segs = series.filter((s) => d[s.key] > 0);
    segs.forEach((s, j) => {
      const h = (ih * d[s.key]) / max;
      const top = j === segs.length - 1;
      const gap = !top && h > 3 ? 1 : 0;
      const r = top && bw >= 6 ? Math.min(3, h, bw / 2) : 0;
      y -= h;
      bars += r
        ? `<path d="M${x},${y + h - gap}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${y + h - gap}Z" fill="${s.color}"/>`
        : `<rect x="${x}" y="${y}" width="${bw}" height="${Math.max(0, h - gap)}" fill="${s.color}"/>`;
    });
    bars += `<rect class="hit" data-i="${i}" x="${m.l + step * i}" y="${m.t}" width="${step}" height="${ih}" fill="transparent"/>`;
  });
  const legend = series.length > 1 ? `<div class="legend">${series.map((s) => `<span><i class="dot" style="background:${s.color}"></i>${esc(s.label)}</span>`).join("")}</div>` : "";
  el.innerHTML = `${legend}<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.title || "")}">${g}${bars}</svg></div>`;
  el.querySelectorAll(".hit").forEach((r) => {
    r.addEventListener("mousemove", (ev) => {
      const d = data[Number(r.dataset.i)];
      showTip(`<div class="tt-h">${fmtDate(d.day, false)}</div>` + series.map((s) =>
        `<div class="tt-r"><span><i class="dot" style="background:${s.color}"></i> ${esc(s.label)}</span><b>${esc(fy(d[s.key] || 0))}</b></div>`).join("") +
        (opts.extra ? opts.extra(d) : ""), ev);
      r.setAttribute("fill", "rgba(127,127,127,.08)");
    });
    r.addEventListener("mouseleave", () => { hideTip(); r.setAttribute("fill", "transparent"); });
  });
}

// ---------------------------------------------------------------- data loading
async function loadReport(force) {
  const f = apiFilter();
  const key = JSON.stringify(f);
  if (!force && S.report && S.reportKey === key) return S.report;
  const r = await api("report", f);
  S.report = r; S.reportKey = key;
  return r;
}
async function refresh(force) {
  try {
    if (["overview", "portals", "se", "drops"].includes(S.route)) await loadReport(force);
    renderView();
  } catch (e) {
    $("#view").innerHTML = `<div class="notice">${esc(e.message)}</div>`;
  }
}

function tile(label, value, hint, cls = "", dot) {
  return `<div class="card tile ${cls}"><div class="label">${dot ? `<i class="dot" style="background:${dot}"></i>` : ""}${esc(label)}</div><div class="value">${value}</div>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
}
function qualityNotice(r) {
  const f = apiFilter();
  return (r.quality.yang_gaps || []).filter((g) => (f.from == null || g.to >= f.from) && (f.to == null || g.from <= f.to))
    .map((g) => `<div class="notice">${esc(t("yang_gap_notice", { a: fmtDate(g.from, false), b: fmtDate(g.to, false) }))}</div>`).join("");
}
function importingNotice() {
  const st = S.status && S.status.importer;
  if (st && (st.state === "importing" || st.state === "analysing"))
    return `<div class="notice info"><span class="spin"></span> ${esc(t("importing_text"))} (${st.files_done}/${st.files_total}, ${fmtInt(st.lines)})</div>`;
  return "";
}

// ---------------------------------------------------------------- views
function seTiles(se, minRuns) {
  const dim = se.runs < minRuns;
  return tile(t("se_rate"), se.rate == null ? "–" : fmtPct(se.rate),
    se.rate ? `${t("one_in", { n: fmtInt(1 / se.rate) })} · ${t("ci95")} ${fmtPct(se.ci_lo)} – ${fmtPct(se.ci_hi)}` + (dim ? ` · <span class="bad-text">${t("min_runs_hint", { n: minRuns })}</span>` : "") : "", "hero") +
    tile(t("se_count"), fmtInt(se.count), `${fmtInt(se.runs)} ${t("se_runs")}`);
}

function viewOverview(r) {
  const minRuns = S.filter.min_runs;
  const P = S.portals.filter((k) => S.filter.portals.includes(k));
  let h = `<h1>${t("nav_overview")}</h1>${importingNotice()}${qualityNotice(r)}`;
  h += `<div class="grid">`;
  h += tile(t("runs_total"), fmtInt(r.runs_total), r.span ? `${fmtDate(r.span.first, false)} – ${fmtDate(r.span.last, false)}` : "");
  P.forEach((k) => {
    const p = r.portals[k];
    h += tile(portalName(k), fmtInt(p.runs), `${t("median_dur")}: ${fmtDur(p.median_duration)}`, "", portalColor(k));
  });
  if (P.includes(r.super_elite.portal)) h += seTiles(r.super_elite, minRuns);
  h += tile(t("yang_total"), fmtCompact(r.yang_total), r.runs_total ? `${t("yang_per_run")}: ${fmtCompact(r.yang_total / r.runs_total)}` : "");
  if (r.value_total) h += tile(t("value_total"), fmtCompact(r.value_total), r.runs_total ? `/ ${t("runs")}: ${fmtCompact(r.value_total / r.runs_total)}` : "");
  h += `</div>`;
  h += `<h2>${t("runs_per_day")}</h2><div class="card"><div id="c-runs"></div></div>`;
  h += `<h2>${t("yang_per_day")}</h2><div class="card"><div id="c-yang"></div></div>`;
  $("#view").innerHTML = h;
  const series = P.map((k) => ({ key: k, label: portalName(k), color: getCss(`--s-${k}`) }));
  barChart($("#c-runs"), series, r.series, { title: t("runs_per_day"),
    extra: (d) => d.se ? `<div class="tt-r"><span>${t("se_count")}</span><b>${d.se}</b></div>` : "" });
  barChart($("#c-yang"), [{ key: "yang", label: "Yang", color: getCss("--s-yang") }], r.series, { title: t("yang_per_day"), fmt: fmtCompact, height: 180 });
}
const getCss = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function itemCols(minRuns, totalRuns) {
  return [
    { key: "item", label: t("col_item"), cls: "item", html: (x) => esc(x.item) + (x.chest ? `<span class="tag chest">${t("tag_chest")}</span>` : "") },
    { key: "runs", label: t("col_runs_with"), num: true, fmt: fmtInt },
    { key: "rate", label: t("col_rate"), num: true, html: (x) => `<div style="display:flex;gap:8px;align-items:center;justify-content:flex-end"><span>${fmtPct(x.rate)}</span><div class="bar" style="width:70px"><i style="width:${(x.rate || 0) * 100}%"></i></div></div>` },
    { key: "ci_lo", label: t("col_ci"), num: true, html: (x) => `<span class="ci">${fmtPct(x.ci_lo)} – ${fmtPct(x.ci_hi)}</span>` },
    { key: "avg_qty", label: t("col_avg"), num: true, fmt: (v) => fmtNum(v, v < 10 ? 2 : 0) },
    { key: "qty", label: t("col_total"), num: true, fmt: fmtInt },
    { key: "value", label: t("col_value"), num: true, fmt: fmtCompact },
    { key: "since", label: t("col_since"), num: true, fmt: fmtInt },
    { key: "last", label: t("col_last"), num: true, fmt: (v) => fmtDate(v) },
  ];
}

function portalTable(el, id, p, minRuns) {
  table(el, id, itemCols(minRuns, p.runs), p.items, {
    defaultSort: { key: "runs", asc: false },
    rowClass: () => (p.runs < minRuns ? "dim" : ""),
  });
}

function viewPortals(r) {
  const minRuns = S.filter.min_runs;
  if (!S.portals.includes(S.sub)) S.sub = S.portals[0];
  const p = r.portals[S.sub];
  let h = `<h1>${t("nav_portals")}</h1>${importingNotice()}<div class="tabs">${S.portals.map((k) =>
    `<button class="${k === S.sub ? "primary" : ""}" data-sub="${k}">${esc(portalName(k))} · ${fmtInt(r.portals[k].runs)}</button>`).join("")}</div>`;
  h += `<div class="grid">${tile(t("runs"), fmtInt(p.runs), "", "", portalColor(S.sub))}${tile(t("median_dur"), fmtDur(p.median_duration))}`;
  if (S.sub === r.super_elite.portal) h += seTiles(r.super_elite, minRuns);
  h += `</div><p class="muted">${t("min_runs_hint", { n: minRuns })}</p><div id="t-items"></div>`;
  $("#view").innerHTML = h;
  $("#view").querySelectorAll("[data-sub]").forEach((b) => (b.onclick = () => { S.sub = b.dataset.sub; location.hash = "#portals/" + S.sub; }));
  portalTable($("#t-items"), "portal", p, minRuns);
}

function viewSE(r) {
  const se = r.super_elite, minRuns = S.filter.min_runs;
  let h = `<h1>${t("nav_se")}</h1><p class="sub">${esc(t("se_explain"))}</p>${importingNotice()}${qualityNotice(r)}<div class="grid">`;
  h += seTiles(se, minRuns);
  h += tile(t("se_current"), fmtInt(se.current_streak), t("runs"));
  h += tile(t("se_longest"), fmtInt(se.longest_streak), se.p_longest != null ? t("se_longest_hint", { n: fmtInt(se.longest_streak), p: fmtPct(se.p_longest) }) : "");
  h += tile(t("se_avg_gap"), se.avg_gap ? fmtNum(se.avg_gap, 1) : "–", "");
  h += `</div><p class="muted">${esc(t("se_breakdown", { c: se.by_conf.confirmed, s: se.by_conf.signature, n: se.by_conf.no_yang_data }))}</p>`;
  h += `<h2>${t("se_list")}</h2><div id="t-se"></div>`;
  $("#view").innerHTML = h;
  table($("#t-se"), "se", [
    { key: "ts", label: t("col_time"), fmt: (v) => fmtDate(v) },
    { key: "yang", label: t("col_yang"), num: true, fmt: (v) => (v ? fmtInt(v) : "–") },
    { key: "conf", label: t("col_conf"), html: (x) => `<span class="tag ${x.conf === "confirmed" ? "se" : ""}">${t("conf_" + x.conf)}</span>` },
    { key: "run_end", label: t("col_end"), fmt: (v) => fmtDate(v) },
  ], se.list, { defaultSort: { key: "ts", asc: false }, onRow: (x) => showRun(x.run_id) });
}

async function showRun(id) {
  const d = await api("run/" + id);
  const r = d.run;
  openModal(`<h2 style="margin-top:0">${t("run_detail")} · <span style="color:${portalColor(r.type)}">${esc(portalName(r.type))}</span>
    ${r.se ? `<span class="tag se">${t("tag_se")}</span>` : ""}</h2>
    <p class="muted">${fmtDate(r.start)} – ${fmtDate(r.end)} · ${t("duration")} ${fmtDur(r.end - r.start)}
    ${r.se ? ` · ${t("tag_se")}: ${fmtDate(r.se_ts)}, ${r.se_yang ? fmtInt(r.se_yang) + " Yang" : ""} (${t("conf_" + r.se_conf)})` : ""}</p>
    <div class="tablewrap" style="max-height:60vh;overflow:auto"><table><thead><tr><th>${t("col_time")}</th><th class="num">#</th><th>${t("col_item")}</th></tr></thead><tbody>
    ${d.drops.map((x) => `<tr><td class="muted">${fmtDate(x.ts).slice(-8)}</td><td class="num">${fmtInt(x.qty)}</td><td>${esc(x.item)}${x.chest ? `<span class="tag chest">${t("tag_chest")}</span>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`);
}

async function viewRuns() {
  const limit = 100;
  const d = await api("runs", { filter: apiFilter(), offset: S.runsOffset, limit });
  let h = `<h1>${t("nav_runs")}</h1><p class="sub">${t("runs_click")}</p>${importingNotice()}<div id="t-runs"></div>
    <div class="pager"><span class="muted">${t("page", { a: d.total ? S.runsOffset + 1 : 0, b: Math.min(S.runsOffset + limit, d.total), n: fmtInt(d.total) })}</span>
    <button id="pg-prev" ${S.runsOffset ? "" : "disabled"}>${t("prev")}</button><button id="pg-next" ${S.runsOffset + limit < d.total ? "" : "disabled"}>${t("next")}</button></div>`;
  $("#view").innerHTML = h;
  table($("#t-runs"), "runs", [
    { key: "end", label: t("col_end"), fmt: (v) => fmtDate(v) },
    { key: "type", label: t("col_type"), html: (x) => `<i class="dot" style="background:${portalColor(x.type)}"></i> ${esc(portalName(x.type))}${x.se ? `<span class="tag se">${t("tag_se")}</span>` : ""}` },
    { key: "duration", label: t("col_dur"), num: true, fmt: fmtDur },
    { key: "drops", label: t("col_drops"), num: true, fmt: fmtInt },
    { key: "yang", label: t("col_yang"), num: true, fmt: fmtInt },
  ], d.runs, { defaultSort: { key: "end", asc: false }, onRow: (x) => showRun(x.id) });
  $("#pg-prev").onclick = () => { S.runsOffset = Math.max(0, S.runsOffset - limit); renderView(); };
  $("#pg-next").onclick = () => { S.runsOffset += limit; renderView(); };
}

function viewDrops(r) {
  let h = `<h1>${t("nav_drops")}</h1>${importingNotice()}${qualityNotice(r)}<div id="t-drops"></div>`;
  if (S.filter.outside !== "exclude") h += `<h2>${t("outside_title")}</h2><p class="sub">${esc(t("outside_hint"))}</p><div id="t-out"></div>`;
  $("#view").innerHTML = h;
  const catName = (k) => { const c = S.categories.find((x) => x.key === k); return c ? c[S.lang] || k : ""; };
  table($("#t-drops"), "drops", [
    { key: "item", label: t("col_item"), cls: "item", html: (x) => esc(x.item) + (x.chest ? `<span class="tag chest">${t("tag_chest")}</span>` : "") },
    { key: "category", label: t("col_category"), fmt: (v) => catName(v) },
    { key: "qty", label: t("col_total"), num: true, fmt: fmtInt },
    { key: "portal_qty", label: t("col_portal_qty"), num: true, fmt: fmtInt },
    { key: "outside_qty", label: t("col_outside_qty"), num: true, fmt: fmtInt },
    { key: "value", label: t("col_value"), num: true, fmt: fmtCompact },
    { key: "last", label: t("col_last"), num: true, fmt: (v) => fmtDate(v) },
  ], r.items, { defaultSort: { key: "qty", asc: false } });
  if ($("#t-out")) table($("#t-out"), "outside", [
    { key: "item", label: t("col_item"), cls: "item", html: (x) => esc(x.item) + (x.chest ? `<span class="tag chest">${t("tag_chest")}</span>` : "") },
    { key: "count", label: t("col_count"), num: true, fmt: fmtInt },
    { key: "qty", label: t("col_total"), num: true, fmt: fmtInt },
    { key: "value", label: t("col_value"), num: true, fmt: fmtCompact },
    { key: "last", label: t("col_last"), num: true, fmt: (v) => fmtDate(v) },
  ], r.outside, { defaultSort: { key: "count", asc: false } });
}

// ---------------------------------------------------------------- live
const liveOpts = () => store.get("liveOpts", { chest: "exclude", outside: "exclude", portal: "elite" });
async function viewLive() {
  const live = S.status.live;
  if (!live) {
    $("#view").innerHTML = `<h1>${t("live_title")}</h1><div class="card setup" style="margin:0;max-width:560px">
      <p>${t("live_none")}</p><p class="muted">${esc(t("live_explain"))}</p>
      <div class="row" style="display:flex;gap:8px"><input id="live-name" placeholder="${esc(t("live_name"))}" style="flex:1">
      <button class="primary" id="live-start">▶ ${t("live_start")}</button></div></div>`;
    $("#live-start").onclick = async () => { await api("session/start", { name: $("#live-name").value.trim() || null }); await pollStatus(); renderView(); };
    return;
  }
  const o = liveOpts();
  const r = await api("report", { sessions: [live.id], chest: o.chest, outside: o.outside });
  const recentRaw = await api(`recent?limit=300&since=${live.first}`);
  const inLive = (ts) => live.segments.some((s) => ts >= s.start && ts <= (s.end ?? 1e12));
  const recent = recentRaw.filter((x) => inLive(x.ts) && (o.chest === "include" || (o.chest === "only") === x.chest)).slice(0, 60);
  const hours = Math.max(live.active_seconds, 1) / 3600;
  const se = r.super_elite;
  const tri = (name) => `<select data-lo="${name}">${[["exclude", t("f_exclude")], ["include", t("f_include")], ["only", t("f_only")]].map(([v, l]) => `<option value="${v}" ${o[name] === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  let h = `<h1>${t("live_title")} · ${esc(live.name)}</h1>
    <div class="card live-head">
      <div><div class="${live.running ? "bad-text" : "muted"}">${live.running ? "● " + t("live_running") : "❚❚ " + t("live_paused")}</div><div class="timer ${live.running ? "" : "paused"}" id="timer">${fmtClock(live.active_seconds)}</div></div>
      <div class="live-controls">
        ${live.running ? `<button id="l-pause">❚❚ ${t("live_pause")}</button>` : `<button class="primary" id="l-resume">▶ ${t("live_resume")}</button>`}
        <button class="danger" id="l-stop">■ ${t("live_stop")}</button>
      </div>
      <div class="fgroup" style="margin-left:auto"><span>${t("f_chest")}</span>${tri("chest")}</div>
      <div class="fgroup"><span>${t("f_outside")}</span>${tri("outside")}</div>
    </div>
    <p class="muted">${esc(t("live_explain"))}</p>
    <div class="grid">`;
  S.portals.forEach((k) => { h += tile(portalName(k), fmtInt(r.portals[k].runs), `${fmtNum(r.portals[k].runs / hours, 1)} / ${t("h")}`, "", portalColor(k)); });
  h += tile(t("live_runs_h"), fmtNum(r.runs_total / hours, 1), `${fmtInt(r.runs_total)} ${t("runs")}`);
  h += tile(t("se_rate"), se.runs ? fmtPct(se.rate) : "–", `${fmtInt(se.count)} / ${fmtInt(se.runs)} ${t("se_runs")}`, "hero");
  h += tile(t("live_yang_h"), fmtCompact(r.yang_total / hours), `${t("yang_total")}: ${fmtCompact(r.yang_total)}`);
  if (r.value_total) h += tile(t("live_value_h"), fmtCompact(r.value_total / hours), `${t("value_total")}: ${fmtCompact(r.value_total)}`);
  h += `</div><div class="live-grid"><div style="min-width:0"><div class="tabs">${S.portals.map((k) =>
    `<button class="small ${k === o.portal ? "primary" : ""}" data-lp="${k}">${esc(portalName(k))}</button>`).join("")}</div><div id="t-live"></div></div>
    <div><h2 style="margin-top:4px">${t("live_recent")}</h2><div class="card ticker" id="ticker">${recent.map((x) =>
      `<div class="${S.seenTs && x.ts > S.seenTs ? "new" : ""}"><span class="t">${fmtDate(x.ts).slice(-8)}</span><span style="flex:1">${fmtInt(x.qty)}× ${esc(x.item)}${x.chest ? `<span class="tag chest">${t("tag_chest")}</span>` : ""}</span>${x.portal ? `<i class="dot" title="${esc(portalName(x.portal))}" style="background:${portalColor(x.portal)};margin-top:6px"></i>` : ""}</div>`).join("") || `<div class="muted">–</div>`}</div></div></div>`;
  $("#view").innerHTML = h;
  S.seenTs = recent.length ? recent[0].ts : S.seenTs;
  portalTable($("#t-live"), "live", r.portals[o.portal], 0);
  $("#view").querySelectorAll("[data-lp]").forEach((b) => (b.onclick = () => { store.set("liveOpts", { ...liveOpts(), portal: b.dataset.lp }); renderView(); }));
  $("#view").querySelectorAll("[data-lo]").forEach((s) => (s.onchange = () => { store.set("liveOpts", { ...liveOpts(), [s.dataset.lo]: s.value }); renderView(); }));
  const act = async (a) => { await api("session/" + a, {}); await pollStatus(); renderView(); };
  if ($("#l-pause")) $("#l-pause").onclick = () => act("pause");
  if ($("#l-resume")) $("#l-resume").onclick = () => act("resume");
  $("#l-stop").onclick = () => { if (confirm(t("live_stop_confirm"))) act("stop"); };
  S.liveBase = { secs: live.active_seconds, at: Date.now(), running: live.running };
}
setInterval(() => {
  const el = $("#timer");
  if (el && S.liveBase && S.liveBase.running) el.textContent = fmtClock(S.liveBase.secs + (Date.now() - S.liveBase.at) / 1000);
}, 500);

// ---------------------------------------------------------------- sessions
async function viewSessions() {
  const list = await api("sessions");
  S.sessionsCache = list;
  S.compare = S.compare || new Set();
  let h = `<h1>${t("sessions_title")}</h1>`;
  if (!list.length) { $("#view").innerHTML = h + `<div class="empty">${t("sessions_none")}</div>`; return; }
  h += `<p class="sub">${t("s_compare_hint")}</p><div id="t-sess"></div><div class="pager"><button class="primary" id="s-cmp">${t("s_compare")}</button></div><div id="cmp"></div>`;
  $("#view").innerHTML = h;
  table($("#t-sess"), "sessions", [
    { key: "sel", label: "", html: (x) => `<input type="checkbox" data-cmp="${x.id}" ${S.compare.has(x.id) ? "checked" : ""}>` },
    { key: "name", label: t("col_name"), cls: "item", html: (x) => esc(x.name) + (x.ended == null ? ` <span class="tag se">${t("s_running")}</span>` : "") },
    { key: "first", label: t("col_start"), fmt: (v) => fmtDate(v) },
    { key: "last", label: t("col_end"), fmt: (v, x) => (x.ended == null ? "–" : fmtDate(v)) },
    { key: "active_seconds", label: t("col_active"), num: true, fmt: fmtDur },
    { key: "act", label: "", html: (x) => `<button class="small" data-an="${x.id}">${t("s_analyse")}</button> <button class="small ghost" data-rn="${x.id}">${t("s_rename")}</button> <button class="small ghost danger" data-del="${x.id}">${t("s_delete")}</button>` },
  ], list, { defaultSort: { key: "first", asc: false } });
  const v = $("#view");
  v.querySelectorAll("[data-cmp]").forEach((c) => (c.onchange = () => { const id = Number(c.dataset.cmp); c.checked ? S.compare.add(id) : S.compare.delete(id); }));
  v.querySelectorAll("[data-an]").forEach((b) => (b.onclick = () => {
    S.filter = Object.assign(defaultFilter(), { sessions: [Number(b.dataset.an)] }); saveFilter(); location.hash = "#overview";
  }));
  v.querySelectorAll("[data-rn]").forEach((b) => (b.onclick = async () => {
    const s = list.find((x) => x.id === Number(b.dataset.rn));
    const n = prompt(t("s_rename"), s.name);
    if (n) { await api("session/rename", { id: s.id, name: n }); renderView(); }
  }));
  v.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
    if (confirm(t("s_delete_confirm"))) { await api("session/delete", { id: Number(b.dataset.del) }); await pollStatus(); renderView(); }
  }));
  $("#s-cmp").onclick = async () => {
    const ids = [...S.compare].filter((id) => list.some((s) => s.id === id));
    if (!ids.length) return;
    const reps = await Promise.all(ids.map((id) => api("report", { sessions: [id] })));
    const ss = ids.map((id) => list.find((s) => s.id === id));
    const rows = [
      [t("col_active"), (r, s) => fmtDur(s.active_seconds)],
      [t("runs_total"), (r) => fmtInt(r.runs_total)],
      ...S.portals.map((k) => [portalName(k), (r) => fmtInt(r.portals[k].runs)]),
      [t("live_runs_h"), (r, s) => fmtNum(r.runs_total / Math.max(s.active_seconds / 3600, 1 / 3600), 1)],
      [t("se_count"), (r) => `${fmtInt(r.super_elite.count)} / ${fmtInt(r.super_elite.runs)}`],
      [t("se_rate"), (r) => fmtPct(r.super_elite.rate)],
      [t("yang_total"), (r) => fmtCompact(r.yang_total)],
      [t("live_yang_h"), (r, s) => fmtCompact(r.yang_total / Math.max(s.active_seconds / 3600, 1 / 3600))],
      [t("value_total"), (r) => fmtCompact(r.value_total || null)],
      [t("live_value_h"), (r, s) => fmtCompact(r.value_total ? r.value_total / Math.max(s.active_seconds / 3600, 1 / 3600) : null)],
    ];
    $("#cmp").innerHTML = `<h2>${t("s_compare")}</h2><div class="tablewrap"><table><thead><tr><th>${t("s_metric")}</th>${ss.map((s) => `<th class="num">${esc(s.name)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(([l, f]) => `<tr><td>${esc(l)}</td>${reps.map((r, i) => `<td class="num">${f(r, ss[i])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  };
}

// ---------------------------------------------------------------- settings
async function viewSettings() {
  const [settings, items] = await Promise.all([api("settings"), api("items")]);
  const q = S.status.importer;
  const qual = S.report ? S.report.quality : null;
  let h = `<h1>${t("set_title")}</h1>
  <div class="two">
    <div class="card"><h2 style="margin-top:0">${t("set_lang")}</h2>
      <select id="s-lang"><option value="de" ${S.lang === "de" ? "selected" : ""}>Deutsch</option><option value="en" ${S.lang === "en" ? "selected" : ""}>English</option></select>
      <h2>${t("set_client")}</h2><p class="muted">${esc(t("set_client_hint"))}</p>
      <div style="display:flex;gap:8px"><input id="s-path" style="flex:1" value="${esc(settings.client_path)}"><button id="s-browse">${t("set_browse")}</button></div>
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center"><button class="primary" id="s-savepath">${t("set_save")}</button><span id="s-pathres" class="${S.status.client_check.ok ? "ok-text" : "bad-text"}">${S.status.client_check.ok ? "✓ " + t("set_ok") : t("set_bad")}</span></div>
    </div>
    <div class="card"><h2 style="margin-top:0">${t("set_import")}</h2><p class="muted">${esc(t("set_import_hint"))}</p>
      <input type="file" id="s-file" accept=".log,.txt" multiple><p id="s-impres" class="muted"></p>
      <h2>${t("set_quality")}</h2><p class="muted">${qual ? esc(t("set_drops_total", { n: fmtInt(qual.drops), a: fmtDate(qual.first_ts, false), b: fmtDate(qual.last_ts, false) })) : ""}</p>
      ${qual ? `<details><summary>${t("set_files")} (${qual.files.length})</summary><div class="tablewrap" style="margin-top:8px"><table><tbody>${qual.files.map((f) => `<tr><td>${esc(f.name)}</td><td class="num">${fmtInt(f.lines)}</td><td class="muted">${fmtDate(f.first_ts, false)} – ${fmtDate(f.last_ts, false)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      <p><button id="s-rebuild">${t("set_rebuild")}</button> <span class="muted">${esc(t("st_" + q.state))}</span></p>
    </div>
  </div>
  <h2>${t("set_items")}</h2><p class="sub">${esc(t("set_items_hint"))}</p>
  <input type="search" id="s-isearch" placeholder="${esc(t("set_search"))}" style="width:260px;margin-bottom:8px" value="${esc(S.itemSearch || "")}">
  <datalist id="dl-items">${items.map((x) => `<option value="${esc(x.item)}">`).join("")}</datalist>
  <div id="t-catalog"></div>
  <div class="two" style="margin-top:16px">
    <div class="card"><h2 style="margin-top:0">${t("set_chest")}</h2><p class="muted">${esc(t("set_chest_hint"))}</p>
      <textarea id="s-chest" rows="7">${esc(settings.chest_patterns.join("\n"))}</textarea>
      <p><button class="primary" id="s-chest-save">${t("set_save")}</button> <button class="ghost" data-reset="chest_patterns">${t("set_reset")}</button></p></div>
    <div class="card"><h2 style="margin-top:0">${t("set_categories")}</h2>
      <textarea id="s-cats" rows="7">${esc(JSON.stringify(settings.categories, null, 1))}</textarea>
      <p><button class="primary" id="s-cats-save">${t("set_save")}</button> <button class="ghost" data-reset="categories">${t("set_reset")}</button></p></div>
  </div>
  <div class="card" style="margin-top:16px"><h2 style="margin-top:0">${t("set_rules")}</h2><p class="muted">${esc(t("set_rules_hint"))}</p>
    <textarea id="s-rules" rows="14">${esc(JSON.stringify(settings.rules, null, 2))}</textarea>
    <p><button class="primary" id="s-rules-save">${t("set_save")}</button> <button class="ghost" data-reset="rules">${t("set_reset")}</button> <span id="s-rules-res" class="muted"></span></p></div>`;
  $("#view").innerHTML = h;

  const catName = (k) => { const c = settings.categories.find((x) => x.key === k); return c ? c[S.lang] || k : ""; };
  const renderCatalog = () => {
    const s = (S.itemSearch || "").toLowerCase();
    const rows = items.filter((x) => !s || x.names.some((n) => n.toLowerCase().includes(s)));
    table($("#t-catalog"), "catalog", [
      { key: "item", label: t("col_item"), cls: "item", html: (x) => esc(x.item) },
      { key: "names", label: t("col_names"), cls: "item", sort: (x) => x.names.length, html: (x) => x.names.filter((n) => n !== x.item).map((n) =>
        `<span class="tag">${esc(n)} <button class="ghost small" style="padding:0 4px" data-unalias="${esc(n)}" title="${t("set_unmerge")}">×</button></span>`).join(" ") },
      { key: "drops", label: t("col_count"), num: true, fmt: fmtInt },
      { key: "category", label: t("col_category"), fmt: (v) => catName(v) },
      { key: "chest", label: t("col_chest"), fmt: (v) => (v ? t("yes") : "") },
      { key: "last", label: t("col_last"), num: true, fmt: (v) => fmtDate(v, false) },
      { key: "price", label: t("col_price"), num: true, html: (x) => `<input class="price-in" type="number" min="0" data-price="${esc(x.item)}" value="${x.price ?? ""}">` },
      { key: "act", label: "", html: (x) => `<button class="small ghost" data-merge="${esc(x.item)}">${t("set_merge")}</button>` },
    ], rows, { defaultSort: { key: "drops", asc: false }, limit: 150, after: (el) => {
      el.querySelectorAll("[data-price]").forEach((i) => (i.onchange = async () => { await api("price", { item: i.dataset.price, price: i.value === "" ? null : Number(i.value) }); S.report = null; }));
      el.querySelectorAll("[data-merge]").forEach((b) => (b.onclick = () => mergeDialog(b.dataset.merge)));
      el.querySelectorAll("[data-unalias]").forEach((b) => (b.onclick = async () => { await api("alias", { name: b.dataset.unalias, canon: null }); S.report = null; renderView(); }));
    } });
  };
  renderCatalog();
  $("#s-isearch").oninput = (e) => { S.itemSearch = e.target.value; renderCatalog(); };
  $("#s-lang").onchange = async (e) => { await api("settings", { language: e.target.value }); S.lang = e.target.value; renderAll(); };
  $("#s-browse").onclick = async () => { const r = await api("pick_folder", {}); if (r.path) { $("#s-path").value = r.path; $("#s-savepath").click(); } };
  $("#s-savepath").onclick = async () => {
    const p = $("#s-path").value.trim();
    const c = await api("check_path", { path: p });
    const res = $("#s-pathres");
    res.className = c.ok ? "ok-text" : "bad-text"; res.textContent = pathMsg(c);
    if (c.ok) { $("#s-path").value = c.path; await api("settings", { client_path: c.path }); await pollStatus(); }
  };
  $("#s-file").onchange = async (e) => {
    let total = 0;
    for (const f of e.target.files) {
      $("#s-impres").innerHTML = `<span class="spin"></span> ${esc(f.name)}`;
      const r = await fetch("/api/import", { method: "POST", headers: { "X-Filename": encodeURIComponent(f.name) }, body: f });
      total += (await r.json()).new_drops || 0;
    }
    $("#s-impres").textContent = t("set_import_done", { n: fmtInt(total) });
    S.report = null;
  };
  $("#s-rebuild").onclick = async () => { await api("rebuild", {}); S.report = null; pollStatus(); };
  const saved = (el) => { el.textContent = t("set_saved"); setTimeout(() => (el.textContent = ""), 2500); };
  $("#s-chest-save").onclick = async () => {
    await api("settings", { chest_patterns: $("#s-chest").value.split("\n").map((s) => s.trim()).filter(Boolean) }); S.report = null; renderView();
  };
  $("#s-cats-save").onclick = async () => {
    try { const c = JSON.parse($("#s-cats").value); await api("settings", { categories: c }); S.categories = c; S.report = null; renderView(); }
    catch (err) { alert(err.message); }
  };
  $("#s-rules-save").onclick = async () => {
    try { await api("settings", { rules: JSON.parse($("#s-rules").value) }); S.report = null; saved($("#s-rules-res")); pollStatus(); }
    catch (err) { $("#s-rules-res").textContent = err.message; }
  };
  $("#view").querySelectorAll("[data-reset]").forEach((b) => (b.onclick = async () => {
    await api("reset_setting", { key: b.dataset.reset }); S.report = null; await init(true); renderView();
  }));
}

function mergeDialog(name) {
  openModal(`<h2 style="margin-top:0">${t("set_merge")}</h2><p><b>${esc(name)}</b></p><p class="muted">${t("set_merge_prompt")}</p>
    <div style="display:flex;gap:8px"><input id="m-target" list="dl-items" style="flex:1"><button class="primary" id="m-ok">${t("set_merge")}</button></div>`);
  $("#m-target").focus();
  $("#m-ok").onclick = async () => {
    const target = $("#m-target").value.trim();
    if (!target || target === name) return;
    await api("alias", { name, canon: target });
    $("#modal").classList.add("hidden"); S.report = null; renderView();
  };
}

// ---------------------------------------------------------------- setup screen
function pathMsg(c) {
  if (c.ok) return "✓ " + t("set_ok") + (c.path ? ": " + c.path : "");
  return t("set_reason_" + (c.reason || "not_found"), { p: c.path || "" });
}
function viewSetup() {
  $("#view").innerHTML = `<div class="card setup"><h1>${t("setup_title")}</h1><p>${esc(t("setup_text"))}</p>
    <div id="su-found" class="muted"><span class="spin"></span> ${t("setup_detecting")}</div>
    <div class="row"><input id="su-path" placeholder="C:\\…\\Nihor2 - Chronicles of Jinteia" value="${esc(S.status.client_path || "")}"><button id="su-browse">${t("set_browse")}</button></div>
    <p id="su-res"></p>
    <button class="primary" id="su-go">${t("setup_go")}</button>
    <p style="margin-top:20px"><select id="su-lang"><option value="de" ${S.lang === "de" ? "selected" : ""}>Deutsch</option><option value="en" ${S.lang === "en" ? "selected" : ""}>English</option></select></p></div>`;
  const check = async () => {
    const c = await api("check_path", { path: $("#su-path").value });
    const res = $("#su-res");
    res.className = c.ok ? "ok-text" : "bad-text";
    res.textContent = pathMsg(c);
    return c;
  };
  const go = async () => {
    const c = await check();
    if (!c.ok) return;
    await api("settings", { client_path: c.path });
    await pollStatus(); location.hash = "#overview"; renderAll();
  };
  $("#su-browse").onclick = async () => { const r = await api("pick_folder", {}); if (r.path) { $("#su-path").value = r.path; check(); } };
  $("#su-path").onchange = check;
  $("#su-lang").onchange = async (e) => { await api("settings", { language: e.target.value }); S.lang = e.target.value; renderAll(); };
  $("#su-go").onclick = go;
  api("detect_paths", {}).then((r) => {
    const el = $("#su-found");
    if (!el) return;
    if (!r.paths.length) { el.textContent = t("setup_none_found"); return; }
    el.innerHTML = `${t("setup_found")}<br>` + r.paths.map((p, i) => `<button class="small ghost" data-p="${i}" style="margin:4px 0">📁 ${esc(p)}</button>`).join("<br>");
    el.querySelectorAll("[data-p]").forEach((b) => (b.onclick = () => { $("#su-path").value = r.paths[Number(b.dataset.p)]; check(); }));
    if (!$("#su-path").value) { $("#su-path").value = r.paths[0]; check(); }
  }).catch(() => { const el = $("#su-found"); if (el) el.textContent = ""; });
}

// ---------------------------------------------------------------- shell
const ROUTES = ["overview", "portals", "se", "runs", "drops", "live", "sessions", "settings"];
function renderNav() {
  $("#nav").innerHTML = ROUTES.map((r) => `<a href="#${r}" class="${S.route === r ? "active" : ""}">${t("nav_" + r)}</a>`).join("");
  $("#lang").textContent = S.lang === "de" ? "EN" : "DE";
  document.documentElement.lang = S.lang;
}
function renderStatus() {
  const st = S.status;
  if (!st) return;
  const el = $("#status");
  const s = st.importer.state;
  el.className = "status " + (st.importer.error ? "err" : s === "watching" ? "ok" : s === "no_client_path" ? "err" : "busy");
  el.textContent = t("st_" + s) || s;
  el.title = st.importer.error || st.client_path || "";
  const lb = $("#livebadge");
  if (st.live) {
    lb.classList.remove("hidden"); lb.classList.toggle("paused", !st.live.running);
    lb.textContent = (st.live.running ? "● LIVE " : "❚❚ ") + fmtClock(st.live.active_seconds);
    lb.onclick = () => (location.hash = "#live");
  } else lb.classList.add("hidden");
}
async function renderView() {
  hideTip();
  renderNav();
  renderFilterbar();
  if (!S.status) return;
  if (!S.status.client_check.ok && S.route !== "settings") return viewSetup();
  try {
    switch (S.route) {
      case "overview": return viewOverview(await loadReport());
      case "portals": return viewPortals(await loadReport());
      case "se": return viewSE(await loadReport());
      case "drops": return viewDrops(await loadReport());
      case "runs": return await viewRuns();
      case "live": return await viewLive();
      case "sessions": return await viewSessions();
      case "settings": return await viewSettings();
    }
  } catch (e) {
    $("#view").innerHTML = `<div class="notice">${esc(e.message)}</div>`;
  }
}
function renderAll() { renderNav(); renderStatus(); renderView(); }

function readRoute() {
  const [r, sub] = location.hash.replace(/^#/, "").split("/");
  S.route = ROUTES.includes(r) ? r : "overview";
  if (sub) S.sub = sub;
  if (S.route !== "runs") S.runsOffset = 0;
}
window.addEventListener("hashchange", () => { readRoute(); renderView(); window.scrollTo(0, 0); });
window.addEventListener("resize", () => { clearTimeout(S.rz); S.rz = setTimeout(() => { if (["overview"].includes(S.route)) renderView(); }, 200); });
$("#lang").onclick = async () => { S.lang = S.lang === "de" ? "en" : "de"; await api("settings", { language: S.lang }); renderAll(); };

async function pollStatus() {
  try {
    S.status = await api("status");
    renderStatus();
  } catch (e) {
    $("#status").className = "status err"; $("#status").textContent = t("st_error");
  }
  return S.status;
}

async function init(force) {
  await pollStatus();
  S.lang = S.status.language || "de";
  S.portals = S.status.portals;
  S.categories = S.status.categories;
  const saved = store.get("filter", null);
  S.filter = Object.assign(defaultFilter(), saved || {});
  S.filter.portals = S.filter.portals.filter((p) => S.portals.includes(p));
  if (!S.filter.portals.length) S.filter.portals = S.portals.slice();
  try { S.sessionsCache = await api("sessions"); } catch (e) { S.sessionsCache = []; }
  if (!force) { readRoute(); renderAll(); }
}

// Poll: status every 2 s; live view every 3 s; other data views when new drops arrived (max every 15 s).
let tick = 0;
setInterval(async () => {
  tick++;
  const prevLive = S.status && S.status.live && S.status.live.id;
  const prevOk = S.status && S.status.client_check.ok;
  const prevState = S.status && S.status.importer.state;
  await pollStatus();
  if (!S.status) return;
  const st = S.status.importer;
  if (prevOk !== S.status.client_check.ok) return renderView();
  if (S.route === "live" && (tick % 2 === 0 || prevLive !== (S.status.live && S.status.live.id))) return renderView();
  const busy = st.state === "importing" || st.state === "analysing";
  if (["overview", "portals", "se", "drops", "runs"].includes(S.route)) {
    const finished = (prevState === "importing" || prevState === "analysing") && !busy;
    const noticeMissing = busy && !document.querySelector("#view .notice.info");
    if (finished || noticeMissing || (S.lastLines !== st.lines && tick % 8 === 0) || (busy && tick % 5 === 0)) {
      S.lastLines = st.lines;
      if (!document.querySelector(".modal:not(.hidden)")) refresh(true);
    }
  }
}, 2000);

init();
