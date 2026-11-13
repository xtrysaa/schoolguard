"use strict";
const $ = (s, r = document) => r.querySelector(s);
const main = $("#main");
let uiVersion = "";
let S = null, page = "live", events = [], evFilter = "all", bindInfo = null, bindTimer = null, camDraft = null, lastKey = "", audit = [];

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (url, body) => {
  const r = await fetch(url, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
};
const toast = (m) => { const el = $("#toast"); el.textContent = m; el.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => el.hidden = true, 3500); };
const fmtDate = ts => new Date(ts * 1000).toLocaleDateString(LOCALES[LANG]);
const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString(LOCALES[LANG]);
const SENS = ["sensitive", "balanced", "strict"];
const sigName = k => t("sig_" + k);
// демо-камера называется по-разному в зависимости от языка, на котором её добавили: показываем на текущем
const DEMO_NAMES = Object.values(I18N).map(d => d.demo_name);
const camName = name => DEMO_NAMES.includes(name) ? t("demo_name") : name;
const camLabel = (no, name) => `${t("cam_no", { n: no })} — ${esc(camName(name))}`;

// ------------------------------------------------------------------ навигация и язык
$("#nav").addEventListener("click", e => { const b = e.target.closest("button"); if (b) go(b.dataset.page); });
function go(p) { page = p; lastKey = ""; if (p === "events") loadEvents(true); if (p === "settings") loadAudit(); render(); }
function applyLang() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
}
async function setLang(l) { LANG = l; await api("/api/settings", { lang: l }); applyLang(); lastKey = ""; await poll(); }
function renderWelcome() {
  $(".shell").classList.add("welcome");
  main.innerHTML = `<div class="hello"><img src="/ui/icon.svg" width="56" height="56" alt="">
    <h1>SchoolGuard</h1><p>Тілді таңдаңыз · Выберите язык · Choose a language</p>
    <div class="langs">${Object.entries(LANG_NAMES).map(([k, v]) => `<button class="btn" onclick="setLang('${k}')">${v}</button>`).join("")}</div></div>`;
}

async function poll() {
  try { S = await api("/api/state"); } catch { return; }
  if (uiVersion && S.version !== uiVersion) { location.reload(); return; }
  uiVersion = S.version;
  if (!S.settings.lang) { renderWelcome(); return; }
  if ($(".shell").classList.contains("welcome")) { $(".shell").classList.remove("welcome"); lastKey = ""; }
  if (LANG !== S.settings.lang) { LANG = S.settings.lang; lastKey = ""; }
  applyLang();
  const badge = $("#badge");
  badge.hidden = !S.stats.unreviewed; badge.textContent = S.stats.unreviewed;
  const on = S.cameras.filter(c => c.state === "online").length;
  $("#ver").textContent = "v" + S.version;
  $("#sysline").innerHTML = `<div>${t("sys_cams")} <b>${on} / ${S.cameras.length}</b></div><div>${t("sys_compute")} <b>${S.device === "GPU" ? t("gpu") : t("cpu")}</b></div>`
    + `<div>Telegram <b class="${S.telegram.recipients.length ? "ok" : "off"}">${S.telegram.recipients.length ? t("sys_tg_on") : t("sys_tg_off")}</b></div><div>${t("sys_time")} <b>${new Date().toLocaleTimeString(LOCALES[LANG])}</b></div>`;
  const key = LANG + page + "|" + S.cameras.map(c => c.id + c.name + c.enabled + c.source + !!c.demo).join(",") + "|" + S.telegram.connected + S.telegram.recipients.length
    + "|" + S.settings.sensitivity + S.settings.privacy_blur + S.settings.share_feedback + S.pin_set;
  if (key !== lastKey && !document.activeElement.matches("input, select")) { lastKey = key; render(); }
  else tick();
  if (bindInfo && S.telegram.last_bind) { toast(t("tg_bound", { n: S.telegram.last_bind.name })); bindInfo = null; lastKey = ""; }
  if (!S.settings.share_asked && $("#modal").hidden) askShare();
}

// Один раз после выбора языка: спросить школу, отправлять ли отметки разработчику (без видео).
function askShare() {
  const m = $("#modal");
  m.innerHTML = `<div class="sheet consent"><h2>${t("consent_h")}</h2><p>${t("consent_p")}</p><p class="note">${t("consent_note")}</p>
    <div class="row" style="margin-top:16px"><button class="btn primary" id="share_yes">${t("btn_enable")}</button><button class="btn" id="share_no">${t("btn_not_now")}</button></div></div>`;
  m.hidden = false;
  const answer = async enable => { m.hidden = true; m.innerHTML = ""; await api("/api/share_consent", { enable }); if (enable) toast(t("consent_thanks")); lastKey = ""; await poll(); };
  $("#share_yes").onclick = () => answer(true);
  $("#share_no").onclick = () => answer(false);
}

function render() {
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.page === page));
  if (!S) { main.innerHTML = `<p class="muted">${t("starting")}</p>`; return; }
  if (!S.settings.lang) return renderWelcome();
  ({ live: renderLive, events: renderEvents, cameras: renderCameras, telegram: renderTelegram, settings: renderSettings })[page]();
  tick();
}

// ------------------------------------------------------------------ наблюдение
function renderLive() {
  const cams = S.cameras.filter(c => c.enabled);
  const warn = S.settings.privacy_blur ? "" : `<p class="banner">${t("blur_off_banner")}</p>`;
  if (!cams.length) {
    main.innerHTML = `<div class="head"><div><h1>${t("nav_live")}</h1></div></div>${warn}
    <div class="empty"><h2>${t("live_empty_h")}</h2>
    <p>${t("live_empty_p")}</p>
    <div class="row"><button class="btn primary" onclick="go('cameras')">${t("btn_connect_cam")}</button>
    ${S.demo_available ? `<button class="btn" onclick="addDemo()">${t("btn_demo")}</button>` : ""}</div></div>`;
    return;
  }
  main.innerHTML = `<div class="head"><div><h1>${t("nav_live")}</h1><p>${t("live_sub")}</p></div>
    <button class="btn" onclick="go('cameras')">${t("btn_add_cam")}</button></div>${warn}
  <div class="kpis"><div><span class="lbl">${t("kpi_cams")}</span><b data-k="cams"></b></div><div><span class="lbl">${t("kpi_day")}</span><b data-k="day"></b></div>
    <div><span class="lbl">${t("kpi_new")}</span><b data-k="new"></b></div><div><span class="lbl">${t("kpi_tg")}</span><b data-k="tg"></b></div></div>
  <div class="livewrap"><div class="grid ${cams.length === 1 ? "one" : ""}">${cams.map(c => `
    <div class="tile" data-cam="${c.id}">
      <div class="thead"><span class="no">№ ${c.no}</span><b>${esc(camName(c.name))}</b><span class="st"><i class="dot" data-f="dot"></i><span data-f="st"></span></span></div>
      ${c.demo ? `<div class="demobar"><span class="lbl">${t("demo_lbl")}</span><span class="ttl" data-f="dttl"></span><span class="truth" data-f="dtruth"></span>
        <span class="pos" data-f="dpos"></span><button class="btn sm" onclick="demoStep('${c.id}',-1)">${t("btn_prev")}</button><button class="btn sm primary" onclick="demoStep('${c.id}',1)">${t("btn_next")}</button></div>` : ""}
      <div class="view"><span data-f="msg"></span><img alt="" data-f="img"><span class="flag" data-f="flag" hidden>${t("alarm")}</span></div>
      <div class="readout">
        <div class="num"><b data-f="val">0.00</b><span data-f="lvl">${t("lvl_calm")}</span></div>
        <div class="scale"><span class="lbl" data-f="thrv"></span>
          <div class="track"><u data-f="bar"></u><s data-f="thr"></s></div>
          <div class="ticks"><span>0.0</span><span>0.25</span><span>0.5</span><span>0.75</span><span>1.0</span></div></div>
      </div>
      <div class="sigs">${Object.keys(S.signals).map(k => `<div class="sig" data-sig="${k}"><span>${esc(sigName(k))}</span><em>0.00</em><div class="track"><u></u></div></div>`).join("")}</div>
    </div>`).join("")}</div>
    <aside class="rail"><h2><span>${t("queue")}</span><span data-k="qn"></span></h2><div id="queue"></div><button class="btn sm" onclick="go('events')">${t("all_events")}</button></aside></div>`;
  queueKey = "";
}

let queueKey = "";
function tick() {
  if (!S || page !== "live") return;
  const k = n => main.querySelector(`[data-k="${n}"]`);
  if (k("cams")) {
    const on = S.cameras.filter(c => c.state === "online").length;
    k("cams").textContent = `${on} / ${S.cameras.length}`; k("day").textContent = S.stats.day;
    k("new").textContent = S.stats.unreviewed; k("new").className = S.stats.unreviewed ? "warn" : "";
    k("tg").textContent = S.telegram.recipients.length; k("tg").className = S.telegram.recipients.length ? "ok" : "warn";
    const top = events.slice(0, 5), key = LANG + top.map(e => e.id + (e.verdict || "")).join(",") + "|" + events.length;
    if (key !== queueKey && $("#queue")) {
      queueKey = key; k("qn").textContent = events.length ? t("q_of", { a: top.length, b: events.length }) : "";
      $("#queue").innerHTML = top.length ? top.map(e => `<button class="q" onclick="openEvent('${e.id}')"><span class="qn">${camLabel(e.camera_no, e.camera_name)}</span>
        <span class="qs">${e.peak.toFixed(2)}<small class="${e.verdict === "confirmed" ? "ok" : e.verdict === "false_alarm" ? "fp" : ""}">${e.verdict === "confirmed" ? t("v_ok") : e.verdict === "false_alarm" ? t("v_fp") : t("v_new")}</small></span>
        <span class="qt">${fmtDate(e.ts)} · ${fmtTime(e.ts)}</span></button>`).join("") : `<div class="none">${t("q_none")}</div>`;
    }
  }
  for (const c of S.cameras) {
    const tile = main.querySelector(`[data-cam="${c.id}"]`);
    if (!tile) continue;
    const f = n => tile.querySelector(`[data-f="${n}"]`);
    const img = f("img");
    if (c.state === "online") { if (!img.src) img.src = `/stream/${c.id}.mjpg?${Date.now()}`; img.hidden = false; f("msg").textContent = ""; }
    else { img.hidden = true; img.removeAttribute("src"); f("msg").textContent = terr(c.error) || t("st_" + c.state); }
    f("dot").className = "dot " + c.state;
    f("st").textContent = c.state === "online" ? t("people_fps", { n: c.people, f: c.fps.toFixed(0) }) : t("st_" + c.state);
    if (c.demo && f("dttl")) {
      f("dttl").textContent = I18N.ru["demo_t" + c.demo.idx] ? t("demo_t" + c.demo.idx) : c.demo.title; f("dpos").textContent = `${c.demo.idx + 1} / ${c.demo.n}`;
      f("dtruth").textContent = c.demo.fight ? t("truth_fight") : t("truth_calm"); f("dtruth").className = "truth" + (c.demo.fight ? " fight" : "");
    }
    const lvl = c.alert ? "alert" : c.score >= 0.6 * c.threshold ? "warn" : "";
    f("bar").style.width = Math.min(c.score, 1) * 100 + "%"; f("bar").className = lvl;
    f("thr").style.left = c.threshold * 100 + "%";
    f("val").textContent = c.score.toFixed(2); f("val").className = lvl;
    f("lvl").textContent = c.alert ? t("lvl_alert") : lvl === "warn" ? t("lvl_warn") : t("lvl_calm"); f("thrv").textContent = t("risk_thr", { v: c.threshold.toFixed(2) });
    f("flag").hidden = !c.alert; tile.classList.toggle("alert", c.alert);
    tile.querySelectorAll("[data-sig]").forEach(el => {
      const v = c.signals[el.dataset.sig] || 0;
      el.querySelector("u").style.width = Math.min(v, 1) * 100 + "%"; el.classList.toggle("hot", v >= 0.4); el.querySelector("em").textContent = v.toFixed(2);
    });
  }
}
async function demoStep(id, step) { await api(`/api/cameras/${id}/demo`, { step }); poll(); }
async function addDemo() { await api("/api/cameras", { demo: true, demo_name: t("demo_name") }); page = "live"; lastKey = ""; poll(); }

// ------------------------------------------------------------------ события
let eventsKey = "";
async function loadEvents(force) {
  let list; try { list = await api("/api/events?limit=300"); } catch { return; }
  const key = JSON.stringify(list.map(e => [e.id, e.verdict, e.sent, e.clip]));
  if (key === eventsKey && !force) return;
  events = list; eventsKey = key;
  if (page === "events") renderEvents(); else tick();
}
function renderEvents() {
  const list = events.filter(e => evFilter === "all" || (evFilter === "new" ? !e.verdict : e.verdict === evFilter));
  const st = S.stats;
  main.innerHTML = `<div class="head"><div><h1>${t("nav_events")}</h1><p>${t("ev_sub")}</p></div></div>
  <div class="filters">${[["all", t("f_all", { n: st.total })], ["new", t("f_new", { n: st.unreviewed })], ["confirmed", t("f_conf", { n: st.confirmed })], ["false_alarm", t("f_false", { n: st.false_alarm })]]
    .map(([k, label]) => `<button class="btn sm ${evFilter === k ? "primary" : ""}" onclick="evFilter='${k}';renderEvents()">${label}</button>`).join("")}</div>
  ${list.length ? list.map(evRow).join("") : `<div class="empty"><p>${events.length ? t("ev_empty_sec") : t("ev_empty")}</p></div>`}`;
}
function evRow(e) {
  const sig = Object.entries(e.signals).filter(([, v]) => v >= 0.15).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k]) => `<span class="chip">${esc(sigName(k))}</span>`).join("");
  const v = e.verdict === "confirmed" ? `<span class="chip ok">${t("chip_ok")}</span>` : e.verdict === "false_alarm" ? `<span class="chip fp">${t("chip_fp")}</span>` : `<span class="chip new">${t("chip_new")}</span>`;
  return `<div class="ev">
    ${e.thumb ? `<img src="/clips/${esc(e.thumb)}" alt="${t("frame_alt")}" onclick="openEvent('${e.id}')">` : `<div class="noimg"></div>`}
    <div><div class="when">${fmtDate(e.ts)} · ${fmtTime(e.ts)}</div><div class="cam">${camLabel(e.camera_no, e.camera_name)}</div>
      <div>${v}<span class="chip">${t("chip_risk", { v: e.peak.toFixed(2) })}</span>${e.sent ? `<span class="chip tg">${t("chip_sent")}</span>` : ""}${sig}</div></div>
    <div class="acts"><button class="btn sm primary" onclick="openEvent('${e.id}')">${t("btn_watch")}</button>
      <div class="row"><button class="btn sm" onclick="verdict('${e.id}','confirmed')">${t("btn_confirm")}</button><button class="btn sm" onclick="verdict('${e.id}','false_alarm')">${t("btn_false")}</button></div></div></div>`;
}
async function verdict(id, v) { await api(`/api/events/${id}/verdict`, { verdict: v }); closeModal(); await loadEvents(true); poll(); }
async function delEvent(id) { if (!confirm(t("confirm_del"))) return; await api(`/api/events/${id}/delete`, {}); closeModal(); await loadEvents(true); poll(); }
function openEvent(id) {
  const e = events.find(x => x.id === id); if (!e) return;
  const m = $("#modal");
  m.innerHTML = `<div class="sheet"><div class="row" style="margin-bottom:12px"><div class="grow"><h2 style="margin:0">${camLabel(e.camera_no, e.camera_name)}</h2>
    <span class="when mono muted">${fmtDate(e.ts)} · ${fmtTime(e.ts)} · ${t("ev_meta", { p: e.peak.toFixed(2), t: e.threshold.toFixed(2) })}</span></div><button class="btn sm" onclick="closeModal()">${t("btn_close")}</button></div>
    ${e.clip ? `<video src="/clips/${esc(e.clip)}" controls autoplay loop muted></video>` : `<img src="/clips/${esc(e.thumb)}" style="width:100%" alt="">`}
    <div class="row" style="margin-top:12px"><button class="btn primary" onclick="verdict('${e.id}','confirmed')">${t("btn_confirm_long")}</button>
    <button class="btn" onclick="verdict('${e.id}','false_alarm')">${t("btn_false_long")}</button><span class="grow"></span>
    <button class="btn danger" onclick="delEvent('${e.id}')">${t("btn_del_rec")}</button></div></div>`;
  m.hidden = false;
}
function closeModal() { const m = $("#modal"); m.hidden = true; m.innerHTML = ""; if (closeModal.done) { const d = closeModal.done; closeModal.done = null; d(null); } }
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

// ------------------------------------------------------------------ камеры
const BRANDS = {
  hik: ["Hikvision / HiWatch", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/Streaming/Channels/${o.ch}0${o.sub ? 2 : 1}`],
  dahua: ["Dahua / Imou", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/cam/realmonitor?channel=${o.ch}&subtype=${o.sub ? 1 : 0}`],
  tapo: ["TP-Link Tapo / VIGI", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/stream${o.sub ? 2 : 1}`],
  uniview: ["Uniview", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/media/video${o.sub ? 2 : 1}`],
  other: [null, null],
};
const srcLabel = c => c.source_kind === "demo" ? t("src_demo") : c.source_kind === "webcam" ? t("src_webcam", { n: c.source_masked }) : c.source_masked;
function draft() { return camDraft ??= { kind: "ip", brand: "hik", ip: "", port: "554", user: "admin", pass: "", ch: "1", sub: true, url: "", name: "", webcam: "", file: "", test: null, webcams: null }; }
function draftSource() {
  const d = draft();
  if (d.kind === "webcam") return d.webcam;
  if (d.kind === "file") return d.file.trim().replace(/^"|"$/g, "");
  if (d.brand === "other") return d.url.trim();
  if (!d.ip.trim()) return "";
  const auth = d.user ? `${encodeURIComponent(d.user)}${d.pass ? ":" + encodeURIComponent(d.pass) : ""}@` : "";
  return BRANDS[d.brand][1]({ auth, ip: d.ip.trim(), port: d.port || "554", ch: d.ch || "1", sub: d.sub });
}
function renderCameras() {
  const d = draft();
  const inp = (k, label, type = "text", ph = "") => `<label>${label}<input type="${type}" value="${esc(d[k])}" placeholder="${esc(ph)}" oninput="camDraft.${k}=this.value;camDraft.test=null"></label>`;
  let form = "";
  if (d.kind === "ip") {
    form = `<div class="form"><label>${t("f_brand")}<select onchange="camDraft.brand=this.value;camDraft.test=null;renderCameras()">${Object.entries(BRANDS).map(([k, v]) => `<option value="${k}" ${d.brand === k ? "selected" : ""}>${v[0] || t("brand_other")}</option>`).join("")}</select></label>
      ${d.brand === "other" ? `<label style="grid-column:span 2">${t("f_url")}<input type="text" value="${esc(d.url)}" placeholder="${esc(t("f_url_ph"))}" oninput="camDraft.url=this.value;camDraft.test=null"></label>` :
        inp("ip", t("f_ip"), "text", "192.168.1.64") + inp("user", t("f_login")) + inp("pass", t("f_pass"), "password") + inp("ch", t("f_channel"), "number")
        + `<label>${t("f_quality")}<select onchange="camDraft.sub=this.value==='1';camDraft.test=null"><option value="1" ${d.sub ? "selected" : ""}>${t("q_eco")}</option><option value="0" ${d.sub ? "" : "selected"}>${t("q_full")}</option></select></label>`}
      </div><p class="note" style="margin-top:10px">${t("ip_note")}</p>`;
  } else if (d.kind === "webcam") {
    form = d.webcams === null ? `<p class="note">${t("webcam_search")}</p>` : d.webcams.length
      ? `<div class="form"><label>${t("tab_webcam")}<select onchange="camDraft.webcam=this.value;camDraft.test=null">${d.webcams.map(i => `<option value="${i}" ${d.webcam == i ? "selected" : ""}>${t("webcam_n", { n: i + 1 })}</option>`).join("")}</select></label></div>`
      : `<p class="note">${t("webcam_none")}</p>`;
  } else {
    form = `<div class="form"><label style="grid-column:1/-1">${t("f_file")}<input type="text" value="${esc(d.file)}" placeholder="${esc(t("file_ph"))}" oninput="camDraft.file=this.value;camDraft.test=null"></label></div>
      <p class="note" style="margin-top:10px">${t("file_note")}</p>`;
  }
  const res = d.test;
  main.innerHTML = `<div class="head"><div><h1>${t("nav_cameras")}</h1><p>${t("cam_sub")}</p></div></div>
  <div class="card"><h2>${t("cam_connected")}</h2>${S.cameras.length ? `<table><tr><th>№</th><th>${t("th_name")}</th><th>${t("th_source")}</th><th>${t("th_state")}</th><th>${t("th_sens")}</th><th></th></tr>
    ${S.cameras.map(c => `<tr><td class="mono">${c.no}</td><td><input type="text" value="${esc(c.name)}" style="min-width:160px" onchange="camUpdate('${c.id}',{name:this.value})"></td>
      <td class="mono">${esc(srcLabel(c))}</td><td><i class="dot ${c.state}"></i> ${t("st_" + c.state)}</td>
      <td><select onchange="camUpdate('${c.id}',{sensitivity:this.value||null})"><option value="">${t("as_settings")}</option>${SENS.map(k => `<option value="${k}" ${c.sensitivity === k ? "selected" : ""}>${t("sens_" + k)}</option>`).join("")}</select></td>
      <td><div class="row" style="justify-content:flex-end;flex-wrap:nowrap"><button class="btn sm" onclick="camUpdate('${c.id}',{enabled:${!c.enabled}})">${c.enabled ? t("btn_off") : t("btn_on")}</button>
      <button class="btn sm danger" data-name="${esc(c.name)}" onclick="camDelete('${c.id}',this.dataset.name)">${t("btn_delete")}</button></div></td></tr>`).join("")}</table>` : `<p class="note">${t("no_cams")}</p>`}</div>
  <div class="card"><h2>${t("btn_add_cam")}</h2>
    <div class="tabs">${[["ip", t("tab_ip")], ["webcam", t("tab_webcam")], ["file", t("tab_file")]].map(([k, v]) => `<button class="${d.kind === k ? "on" : ""}" onclick="camKind('${k}')">${v}</button>`).join("")}</div>
    ${form}
    <div class="form" style="margin-top:12px">${inp("name", t("f_name"), "text", t("name_ph"))}</div>
    <div class="row" style="margin-top:14px"><button class="btn" onclick="camTest()" ${res === "wait" ? "disabled" : ""}>${res === "wait" ? t("testing") : t("btn_test")}</button>
      <button class="btn primary" onclick="camAdd()">${t("btn_add_cam")}</button>
      ${res && res !== "wait" ? (res.ok ? `<span class="okmsg">${t("test_ok", { w: res.width, h: res.height })}</span>` : `<span class="err">${esc(terr(res.error))}</span>`) : ""}</div>
    ${res && res.ok ? `<img class="preview" src="${res.jpeg}" alt="${t("cam_frame_alt")}">` : ""}</div>`;
}
async function camKind(k) { draft().kind = k; camDraft.test = null; renderCameras(); if (k === "webcam" && camDraft.webcams === null) { camDraft.webcams = await api("/api/webcams"); if (camDraft.webcams.length && camDraft.webcam === "") camDraft.webcam = String(camDraft.webcams[0]); if (page === "cameras") renderCameras(); } }
async function camTest() { const src = draftSource(); if (src === "") return toast(t("need_addr")); camDraft.test = "wait"; renderCameras(); camDraft.test = await api("/api/cameras/test", { source: String(src) }); if (page === "cameras") renderCameras(); }
async function camAdd() {
  const src = draftSource(); if (src === "") return toast(t("need_addr"));
  const r = await api("/api/cameras", { source: String(src), name: camDraft.name });
  if (r.error) return toast(terr(r.error));
  camDraft = null; toast(t("cam_added", { n: r.no })); page = "live"; lastKey = ""; poll();
}
async function camUpdate(id, patch) { await api(`/api/cameras/${id}`, patch); lastKey = ""; poll(); }
async function camDelete(id, name) { if (!confirm(t("confirm_cam_del", { name }))) return; await api(`/api/cameras/${id}/delete`, {}); lastKey = ""; poll(); }

// ------------------------------------------------------------------ telegram
function renderTelegram() {
  const tg = S.telegram;
  const step1 = tg.connected
    ? `<div class="step done"><div><b>${t("tg_bot_ok", { u: esc(tg.bot_username) })}</b><div class="note">${t("tg_bot_note")} <a href="#" onclick="tgDisconnect();return false">${t("tg_change")}</a></div></div></div>`
    : `<div class="step"><div><b>${t("tg_create_h")}</b>
        <p class="note">${t("tg_create_p", { link: `<a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a>` })}</p>
        <div class="row" style="margin-top:8px"><input id="tok" type="text" class="grow" placeholder="1234567890:AA…" style="max-width:420px"><button class="btn primary" onclick="tgToken()">${t("btn_connect_bot")}</button></div>
        <div id="tokerr" class="err"></div></div></div>`;
  let step2 = "";
  if (tg.connected) {
    step2 = `<div class="step ${tg.recipients.length ? "done" : ""}"><div><b>${t("tg_who")}</b>
      ${tg.recipients.length ? `<table style="margin-top:6px">${tg.recipients.map(r => `<tr><td>${esc(r.name)}</td><td class="mono">${t("tg_connected_on", { d: fmtDate(r.added) })}</td><td style="text-align:right"><button class="btn sm danger" onclick="tgRemove(${r.chat_id})">${t("btn_disconnect")}</button></td></tr>`).join("")}</table>` : `<p class="note">${t("tg_nobody")}</p>`}
      ${bindInfo ? `<div class="bind"><div class="qr" id="qr"></div><div>
          <p>${t("tg_qr_p")}</p>
          <p class="note" style="margin:8px 0 4px">${t("tg_code_p", { link: `<a href="${esc(bindInfo.link)}" target="_blank" rel="noopener">@${esc(tg.bot_username)}</a>` })}</p>
          <div class="code">${bindInfo.code.slice(0, 3)} ${bindInfo.code.slice(3)}</div>
          <p class="note" id="bindleft"></p></div></div>`
        : `<div class="row" style="margin-top:10px"><button class="btn primary" onclick="tgBind()">${t("btn_bind")}</button>
           ${tg.recipients.length ? `<button class="btn" onclick="tgTest()">${t("btn_tg_test")}</button>` : ""}</div>`}
      </div></div>`;
  }
  const now = new Date();
  main.innerHTML = `<div class="head"><div><h1>Telegram</h1><p>${t("tg_sub")}</p></div></div>
  <div class="card"><div class="steps">${step1}${step2}</div>${tg.error ? `<p class="err" style="margin-top:12px">${esc(terr(tg.error))}</p>` : ""}</div>
  <div class="card"><h2>${t("tg_preview_h")}</h2><pre class="msg">⚠️ ${t("msg_title")}

📷 ${t("msg_cam")}
📅 ${t("msg_date")}: ${now.toLocaleDateString(LOCALES[LANG])}
🕒 ${t("msg_time")}: ${now.toLocaleTimeString(LOCALES[LANG])}
📈 ${t("msg_risk")}: 0.81 (${t("msg_thr")} ${(+(S.thresholds.balanced ?? 0.65)).toFixed(2)})
${t("msg_signs")}: ${sigName("strikes").toLowerCase()}, ${sigName("contact").toLowerCase()}

${t("msg_video", { a: S.settings.clip_pre_s, b: S.settings.clip_post_s })}
[✅ ${t("btn_confirm")}]  [❌ ${t("btn_false_long")}]</pre></div>`;
  if (bindInfo) {
    const q = qrcode(0, "M"); q.addData(bindInfo.link); q.make();
    $("#qr").innerHTML = q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
    clearInterval(bindTimer);
    const upd = () => { const left = Math.max(0, Math.round(bindInfo ? bindInfo.until - Date.now() / 1000 : 0)); const el = $("#bindleft"); if (!bindInfo || !left) { clearInterval(bindTimer); if (bindInfo) { bindInfo = null; if (page === "telegram") renderTelegram(); } return; } if (el) el.textContent = t("tg_left", { m: Math.floor(left / 60), s: String(left % 60).padStart(2, "0") }); };
    upd(); bindTimer = setInterval(upd, 1000);
  }
}
async function tgToken() { const r = await api("/api/telegram/token", { token: $("#tok").value }); if (!r.ok) { $("#tokerr").textContent = terr(r.error); return; } lastKey = ""; await poll(); }
async function tgDisconnect() { if (!confirm(t("confirm_tg_off"))) return; await api("/api/telegram/disconnect", {}); bindInfo = null; lastKey = ""; poll(); }
async function tgBind() { const r = await api("/api/telegram/bind", {}); bindInfo = { ...r, until: Date.now() / 1000 + r.ttl }; renderTelegram(); }
async function tgRemove(id) { await api("/api/telegram/remove", { chat_id: id }); lastKey = ""; poll(); }
async function tgTest() { const r = await api("/api/telegram/test", {}); toast(r.ok ? t("tg_test_ok") : t("tg_test_fail", { e: terr(r.error) })); }

// ------------------------------------------------------------------ настройки
async function loadAudit() { try { audit = await api("/api/audit"); } catch { audit = []; } if (page === "settings") renderSettings(); }
const auditVal = v => I18N.ru["val_" + v] ? t("val_" + v) : esc(v);
function renderSettings() {
  const s = S.settings, th = S.thresholds || {};
  const num = (k, label, min, max, unit) => `<label>${label}<div class="row" style="flex-wrap:nowrap"><input type="number" min="${min}" max="${max}" value="${s[k]}" onchange="setS({${k}:+this.value})" style="width:90px"><span class="note">${unit}</span></div></label>`;
  main.innerHTML = `<div class="head"><div><h1>${t("nav_settings")}</h1></div></div>
  <div class="card"><h2>${t("set_lang")}</h2><div class="tabs" style="margin:0">${Object.entries(LANG_NAMES).map(([k, v]) => `<button class="${LANG === k ? "on" : ""}" onclick="setLang('${k}')">${v}</button>`).join("")}</div></div>
  <div class="card"><h2>${t("set_sens")}</h2><div class="opts">${SENS.map(k => `<button class="opt ${s.sensitivity === k ? "on" : ""}" onclick="setS({sensitivity:'${k}'})"><b>${t("sens_" + k)}</b><span>${t("desc_" + k)}</span>${th[k] != null ? `<span class="mono">${t("thr", { v: (+th[k]).toFixed(2) })}</span>` : ""}</button>`).join("")}</div>
    <p class="note" style="margin-top:10px">${t("thr_note")}</p></div>
  <div class="card"><h2>${t("set_privacy")}</h2>
    <label class="switch"><input type="checkbox" ${s.privacy_blur ? "checked" : ""} onchange="setS({privacy_blur:this.checked})"><span>${t("blur_h")}<small>${t("blur_p")}</small></span></label>
    <div class="form" style="margin-top:14px">${num("clip_pre_s", t("clip_pre"), 2, 15, t("unit_s"))}${num("clip_post_s", t("clip_post"), 2, 15, t("unit_s"))}${num("cooldown_s", t("cooldown"), 10, 600, t("unit_s"))}${num("retention_days", t("retention"), 1, 365, t("unit_days"))}</div></div>
  <div class="card"><h2>${t("set_share")}</h2>
    <label class="switch"><input type="checkbox" ${s.share_feedback ? "checked" : ""} onchange="setS({share_feedback:this.checked})"><span>${t("share_h")}<small>${t("share_p")}</small></span></label></div>
  <div class="card"><h2>${t("set_admin")}</h2>
    <p><b>${t("pin_h")}.</b> ${S.pin_set ? t("pin_is_set") : t("pin_not_set")}</p><p class="note" style="margin-top:4px">${t("pin_p")}</p>
    <div class="row" style="margin-top:10px">${S.pin_set ? `<button class="btn" onclick="pinChange()">${t("btn_pin_change")}</button><button class="btn danger" onclick="pinRemove()">${t("btn_pin_remove")}</button>` : `<button class="btn primary" onclick="pinChange()">${t("btn_pin_set")}</button>`}</div>
    <h2 style="margin-top:20px">${t("audit_h")}</h2><p class="note">${t("audit_p")}</p>
    ${audit.length ? `<table style="margin-top:8px">${audit.slice(0, 12).map(a => `<tr><td class="mono">${fmtDate(a.ts)} ${fmtTime(a.ts)}</td><td>${t("a_" + a.key)}</td><td>${auditVal(a.old)} → <b>${auditVal(a.new)}</b></td></tr>`).join("")}</table>` : `<p class="note" style="margin-top:8px">${t("audit_empty")}</p>`}</div>
  <div class="card"><h2>${t("set_app")}</h2>
    <label class="switch"><input type="checkbox" ${s.autostart ? "checked" : ""} onchange="setS({autostart:this.checked})"><span>${t("autostart_h")}<small>${t("autostart_p")}</small></span></label>
    <p class="note" style="margin-top:12px">${t("compute_line", { c: S.device === "GPU" ? t("gpu_fast") : t("cpu"), v: esc(S.version) })}<br>${t("home_line")} <span class="mono">${esc(S.home)}</span></p>
    <div class="row" style="margin-top:12px"><button class="btn danger" onclick="quitApp()">${t("btn_quit")}</button></div></div>`;
}
// Окно ввода пароля: возвращает строку или null, если закрыли.
function askPin(title) {
  return new Promise(done => {
    const m = $("#modal");
    m.innerHTML = `<form class="sheet pin"><h2>${title}</h2><input type="password" id="pinin" autocomplete="off">
      <div class="row" style="margin-top:14px"><button class="btn primary" type="submit">${t("btn_ok")}</button><button class="btn" type="button" id="pincancel">${t("btn_cancel")}</button></div></form>`;
    m.hidden = false; closeModal.done = done;
    $("#pinin").focus();
    m.querySelector("form").onsubmit = e => { e.preventDefault(); const v = $("#pinin").value; closeModal.done = null; closeModal(); done(v); };
    $("#pincancel").onclick = () => closeModal();
  });
}
async function setS(patch) {
  let r = await api("/api/settings", patch);
  if (r.error === "pin_required") {
    const pin = await askPin(t("pin_prompt"));
    if (pin !== null) { r = await api("/api/settings", { ...patch, pin }); if (r.error === "pin_required") toast(t("pin_wrong")); }
  }
  lastKey = ""; await poll(); if (page === "settings") loadAudit();
}
async function pinChange() {
  const pin = S.pin_set ? await askPin(t("pin_prompt")) : "";
  if (pin === null) return;
  const nw = await askPin(t("pin_new_prompt"));
  if (!nw) return;
  const r = await api("/api/pin", { pin, new: nw });
  toast(r.ok ? t("pin_saved") : r.error === "pin_short" ? t("pin_short") : t("pin_wrong"));
  lastKey = ""; await poll(); loadAudit();
}
async function pinRemove() {
  const pin = await askPin(t("pin_prompt"));
  if (pin === null) return;
  const r = await api("/api/pin", { pin, new: "" });
  toast(r.ok ? t("pin_removed") : t("pin_wrong"));
  lastKey = ""; await poll(); loadAudit();
}
async function quitApp() { if (!confirm(t("confirm_quit"))) return; await api("/api/quit", {}); main.innerHTML = `<div class="empty"><h2>${t("stopped_h")}</h2><p>${t("stopped_p")}</p></div>`; clearInterval(pollTimer); }

render();
poll();
const pollTimer = setInterval(poll, 1000);
loadEvents();
setInterval(() => { if (page === "events" || page === "live") loadEvents(); }, 4000);
