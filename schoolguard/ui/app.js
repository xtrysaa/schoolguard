"use strict";
const $ = (s, r = document) => r.querySelector(s);
const main = $("#main");
let S = null, page = "live", events = [], evFilter = "all", bindInfo = null, bindTimer = null, camDraft = null, lastKey = "";

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (url, body) => {
  const r = await fetch(url, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
};
const toast = (t) => { const el = $("#toast"); el.textContent = t; el.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => el.hidden = true, 3500); };
const fmtDate = ts => new Date(ts * 1000).toLocaleDateString("ru-RU");
const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString("ru-RU");
const STATE = { online: "В сети", offline: "Нет сигнала", connecting: "Подключение…", disabled: "Выключена" };
const SENS = { sensitive: "Высокая", balanced: "Средняя", strict: "Низкая" };

// ------------------------------------------------------------------ навигация
$("#nav").addEventListener("click", e => { const b = e.target.closest("button"); if (b) go(b.dataset.page); });
function go(p) { page = p; lastKey = ""; if (p === "events") loadEvents(); render(); }

async function poll() {
  try { S = await api("/api/state"); } catch { return; }
  const badge = $("#badge");
  badge.hidden = !S.stats.unreviewed; badge.textContent = S.stats.unreviewed;
  const on = S.cameras.filter(c => c.state === "online").length;
  $("#ver").textContent = "v" + S.version;
  $("#sysline").innerHTML = `<div>КАМЕРЫ <b>${on} / ${S.cameras.length}</b></div><div>ВЫЧИСЛЕНИЯ <b>${S.device === "GPU" ? "видеокарта" : "процессор"}</b></div>`
    + `<div>TELEGRAM <b class="${S.telegram.recipients.length ? "ok" : "off"}">${S.telegram.recipients.length ? "подключён" : "нет получателей"}</b></div><div>ВРЕМЯ <b>${new Date().toLocaleTimeString("ru-RU")}</b></div>`;
  const key = page + "|" + S.cameras.map(c => c.id + c.name + c.enabled + c.source + !!c.demo).join(",") + "|" + S.telegram.connected + S.telegram.recipients.length + "|" + S.settings.sensitivity;
  if (key !== lastKey && !document.activeElement.matches("input, select")) { lastKey = key; render(); }
  else tick();
  if (bindInfo && S.telegram.last_bind) { toast(`Подключён получатель: ${S.telegram.last_bind.name}`); bindInfo = null; lastKey = ""; }
}

function render() {
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.page === page));
  if (!S) { main.innerHTML = `<p class="muted">Запуск…</p>`; return; }
  ({ live: renderLive, events: renderEvents, cameras: renderCameras, telegram: renderTelegram, settings: renderSettings })[page]();
  tick();
}

// ------------------------------------------------------------------ наблюдение
function renderLive() {
  const cams = S.cameras.filter(c => c.enabled);
  if (!cams.length) {
    main.innerHTML = `<div class="head"><div><h1>Наблюдение</h1></div></div>
    <div class="empty"><h2>Камер пока нет</h2>
    <p>Подключите камеру школы по сети или веб-камеру этого компьютера. Чтобы сначала посмотреть, как всё работает, включите демонстрационную запись.</p>
    <div class="row"><button class="btn primary" onclick="go('cameras')">Подключить камеру</button>
    ${S.demo_available ? `<button class="btn" onclick="addDemo()">Показать на демо-записи</button>` : ""}</div></div>`;
    return;
  }
  main.innerHTML = `<div class="head"><div><h1>Наблюдение</h1><p>Скелеты рисуются поверх видео. Число — риск конфликта от 0 до 1, белая отметка на шкале — порог тревоги.</p></div>
    <button class="btn" onclick="go('cameras')">Добавить камеру</button></div>
  <div class="grid ${cams.length === 1 ? "one" : ""}">${cams.map(c => `
    <div class="tile" data-cam="${c.id}">
      <div class="thead"><span class="no">CAM ${String(c.no).padStart(2, "0")}</span><b>${esc(c.name)}</b><span class="st"><i class="dot" data-f="dot"></i><span data-f="st"></span></span></div>
      ${c.demo ? `<div class="demobar"><span class="lbl">Демо-запись</span><span class="ttl" data-f="dttl"></span><span class="truth" data-f="dtruth"></span>
        <span class="pos" data-f="dpos"></span><button class="btn sm" onclick="demoStep('${c.id}',-1)">‹ Предыдущая</button><button class="btn sm primary" onclick="demoStep('${c.id}',1)">Следующая ›</button></div>` : ""}
      <div class="view"><span data-f="msg"></span><img alt="" data-f="img"><span class="flag" data-f="flag" hidden>ТРЕВОГА · ПРОВЕРЬТЕ</span></div>
      <div class="readout">
        <div class="num"><b data-f="val">0.00</b><span data-f="lvl">СПОКОЙНО</span></div>
        <div class="scale"><span class="lbl">Риск конфликта · порог <span data-f="thrv"></span></span>
          <div class="track"><u data-f="bar"></u><s data-f="thr"></s></div>
          <div class="ticks"><span>0.0</span><span>0.25</span><span>0.5</span><span>0.75</span><span>1.0</span></div></div>
      </div>
      <div class="sigs">${Object.entries(S.signals).map(([k, v]) => `<div class="sig" data-sig="${k}"><span>${esc(v)}</span><em>0.00</em><div class="track"><u></u></div></div>`).join("")}</div>
    </div>`).join("")}</div>`;
}

function tick() {
  if (!S || page !== "live") return;
  for (const c of S.cameras) {
    const t = main.querySelector(`[data-cam="${c.id}"]`);
    if (!t) continue;
    const f = n => t.querySelector(`[data-f="${n}"]`);
    const img = f("img");
    if (c.state === "online") { if (!img.src) img.src = `/stream/${c.id}.mjpg?${Date.now()}`; img.hidden = false; f("msg").textContent = ""; }
    else { img.hidden = true; img.removeAttribute("src"); f("msg").textContent = c.error || STATE[c.state]; }
    f("dot").className = "dot " + c.state;
    f("st").textContent = c.state === "online" ? `людей ${c.people} · ${c.fps.toFixed(0)} к/с` : STATE[c.state];
    if (c.demo && f("dttl")) {
      f("dttl").textContent = c.demo.title; f("dpos").textContent = `${c.demo.idx + 1} / ${c.demo.n}`;
      f("dtruth").textContent = c.demo.fight ? "в кадре драка" : "обычная сцена"; f("dtruth").className = "truth" + (c.demo.fight ? " fight" : "");
    }
    const lvl = c.alert ? "alert" : c.score >= 0.6 * c.threshold ? "warn" : "";
    f("bar").style.width = Math.min(c.score, 1) * 100 + "%"; f("bar").className = lvl;
    f("thr").style.left = c.threshold * 100 + "%";
    f("val").textContent = c.score.toFixed(2); f("val").className = lvl;
    f("lvl").textContent = c.alert ? "ТРЕВОГА" : lvl === "warn" ? "РИСК РАСТЁТ" : "СПОКОЙНО"; f("thrv").textContent = c.threshold.toFixed(2);
    f("flag").hidden = !c.alert; t.classList.toggle("alert", c.alert);
    t.querySelectorAll("[data-sig]").forEach(el => {
      const v = c.signals[el.dataset.sig] || 0;
      el.querySelector("u").style.width = Math.min(v, 1) * 100 + "%"; el.classList.toggle("hot", v >= 0.4); el.querySelector("em").textContent = v.toFixed(2);
    });
  }
}
async function demoStep(id, step) { await api(`/api/cameras/${id}/demo`, { step }); poll(); }
async function addDemo() { await api("/api/cameras", { demo: true }); page = "live"; lastKey = ""; poll(); }

// ------------------------------------------------------------------ события
async function loadEvents() { events = await api("/api/events?limit=300"); if (page === "events") renderEvents(); }
function renderEvents() {
  const list = events.filter(e => evFilter === "all" || (evFilter === "new" ? !e.verdict : e.verdict === evFilter));
  const st = S.stats;
  main.innerHTML = `<div class="head"><div><h1>События</h1><p>Каждая тревога — это запись: несколько секунд до и после момента срабатывания. Посмотрите её и отметьте результат: ваши отметки показывают, насколько системе можно доверять.</p></div></div>
  <div class="filters">${[["all", `Все · ${st.total}`], ["new", `Не проверены · ${st.unreviewed}`], ["confirmed", `Подтверждены · ${st.confirmed}`], ["false_alarm", `Ложные · ${st.false_alarm}`]]
    .map(([k, t]) => `<button class="btn sm ${evFilter === k ? "primary" : ""}" onclick="evFilter='${k}';renderEvents()">${t}</button>`).join("")}</div>
  ${list.length ? list.map(evRow).join("") : `<div class="empty"><p>${events.length ? "В этом разделе пусто." : "Тревог пока не было. Когда система заметит возможный конфликт, запись появится здесь и придёт в Telegram."}</p></div>`}`;
}
function evRow(e) {
  const sig = Object.entries(e.signals).filter(([, v]) => v >= 0.15).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k]) => `<span class="chip">${esc(S.signals[k] || k)}</span>`).join("");
  const v = e.verdict === "confirmed" ? `<span class="chip ok">Подтверждено</span>` : e.verdict === "false_alarm" ? `<span class="chip fp">Ложная тревога</span>` : `<span class="chip new">Не проверено</span>`;
  return `<div class="ev">
    ${e.thumb ? `<img src="/clips/${esc(e.thumb)}" alt="Кадр события" onclick="openEvent('${e.id}')">` : `<div class="noimg"></div>`}
    <div><div class="when">${fmtDate(e.ts)} · ${fmtTime(e.ts)}</div><div class="cam">Камера № ${e.camera_no} — ${esc(e.camera_name)}</div>
      <div>${v}<span class="chip">риск ${e.peak.toFixed(2)}</span>${e.sent ? `<span class="chip tg">отправлено в Telegram</span>` : ""}${sig}</div></div>
    <div class="acts"><button class="btn sm primary" onclick="openEvent('${e.id}')">Смотреть запись</button>
      <div class="row"><button class="btn sm" onclick="verdict('${e.id}','confirmed')">Подтвердить</button><button class="btn sm" onclick="verdict('${e.id}','false_alarm')">Ложная</button></div></div></div>`;
}
async function verdict(id, v) { await api(`/api/events/${id}/verdict`, { verdict: v }); closeModal(); await loadEvents(); poll(); }
async function delEvent(id) { if (!confirm("Удалить запись и видео без возможности восстановления?")) return; await api(`/api/events/${id}/delete`, {}); closeModal(); await loadEvents(); poll(); }
function openEvent(id) {
  const e = events.find(x => x.id === id); if (!e) return;
  const m = $("#modal");
  m.innerHTML = `<div class="sheet"><div class="row" style="margin-bottom:12px"><div class="grow"><h2 style="margin:0">Камера № ${e.camera_no} — ${esc(e.camera_name)}</h2>
    <span class="when mono muted">${fmtDate(e.ts)} · ${fmtTime(e.ts)} · риск ${e.peak.toFixed(2)} при пороге ${e.threshold.toFixed(2)}</span></div><button class="btn sm" onclick="closeModal()">Закрыть</button></div>
    ${e.clip ? `<video src="/clips/${esc(e.clip)}" controls autoplay loop muted></video>` : `<img src="/clips/${esc(e.thumb)}" style="width:100%" alt="">`}
    <div class="row" style="margin-top:12px"><button class="btn primary" onclick="verdict('${e.id}','confirmed')">Подтвердить конфликт</button>
    <button class="btn" onclick="verdict('${e.id}','false_alarm')">Ложная тревога</button><span class="grow"></span>
    <button class="btn danger" onclick="delEvent('${e.id}')">Удалить запись</button></div></div>`;
  m.hidden = false;
}
function closeModal() { const m = $("#modal"); m.hidden = true; m.innerHTML = ""; }
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

// ------------------------------------------------------------------ камеры
const BRANDS = {
  hik: ["Hikvision / HiWatch", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/Streaming/Channels/${o.ch}0${o.sub ? 2 : 1}`],
  dahua: ["Dahua / Imou", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/cam/realmonitor?channel=${o.ch}&subtype=${o.sub ? 1 : 0}`],
  tapo: ["TP-Link Tapo / VIGI", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/stream${o.sub ? 2 : 1}`],
  uniview: ["Uniview", (o) => `rtsp://${o.auth}${o.ip}:${o.port}/media/video${o.sub ? 2 : 1}`],
  other: ["Другая (вставить ссылку RTSP)", null],
};
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
  const inp = (k, label, type = "text", ph = "") => `<label>${label}<input type="${type}" value="${esc(d[k])}" placeholder="${ph}" oninput="camDraft.${k}=this.value;camDraft.test=null"></label>`;
  let form = "";
  if (d.kind === "ip") {
    form = `<div class="form"><label>Производитель<select onchange="camDraft.brand=this.value;camDraft.test=null;renderCameras()">${Object.entries(BRANDS).map(([k, v]) => `<option value="${k}" ${d.brand === k ? "selected" : ""}>${v[0]}</option>`).join("")}</select></label>
      ${d.brand === "other" ? `<label style="grid-column:span 2">Ссылка на поток${`<input type="text" value="${esc(d.url)}" placeholder="rtsp://логин:пароль@192.168.1.64:554/..." oninput="camDraft.url=this.value;camDraft.test=null">`}</label>` :
        inp("ip", "IP-адрес камеры", "text", "192.168.1.64") + inp("user", "Логин") + inp("pass", "Пароль", "password") + inp("ch", "Канал (для регистратора)", "number")
        + `<label>Качество<select onchange="camDraft.sub=this.value==='1';camDraft.test=null"><option value="1" ${d.sub ? "selected" : ""}>Экономное (рекомендуется)</option><option value="0" ${d.sub ? "" : "selected"}>Полное</option></select></label>`}
      </div><p class="note" style="margin-top:10px">IP-адрес, логин и пароль есть в настройках камеры или видеорегистратора. Компьютер и камера должны быть в одной сети.</p>`;
  } else if (d.kind === "webcam") {
    form = d.webcams === null ? `<p class="note">Поиск веб-камер…</p>` : d.webcams.length
      ? `<div class="form"><label>Веб-камера<select onchange="camDraft.webcam=this.value;camDraft.test=null">${d.webcams.map(i => `<option value="${i}" ${d.webcam == i ? "selected" : ""}>Камера ${i + 1}</option>`).join("")}</select></label></div>`
      : `<p class="note">Свободных веб-камер не найдено.</p>`;
  } else {
    form = `<div class="form"><label style="grid-column:1/-1">Путь к видеофайлу<input type="text" value="${esc(d.file)}" placeholder="C:\\Видео\\запись.mp4" oninput="camDraft.file=this.value;camDraft.test=null"></label></div>
      <p class="note" style="margin-top:10px">Файл проигрывается по кругу, как будто это камера. Удобно для проверки и показа.</p>`;
  }
  const t = d.test;
  main.innerHTML = `<div class="head"><div><h1>Камеры</h1><p>У каждой камеры есть номер: он указывается в уведомлениях Telegram и в журнале событий.</p></div></div>
  <div class="card"><h2>Подключённые камеры</h2>${S.cameras.length ? `<table><tr><th>№</th><th>Название</th><th>Источник</th><th>Состояние</th><th>Чувствительность</th><th></th></tr>
    ${S.cameras.map(c => `<tr><td class="mono">${c.no}</td><td><input type="text" value="${esc(c.name)}" style="min-width:160px" onchange="camUpdate('${c.id}',{name:this.value})"></td>
      <td class="mono">${esc(c.source_masked)}</td><td><i class="dot ${c.state}"></i> ${STATE[c.state]}</td>
      <td><select onchange="camUpdate('${c.id}',{sensitivity:this.value||null})"><option value="">Как в настройках</option>${Object.entries(SENS).map(([k, v]) => `<option value="${k}" ${c.sensitivity === k ? "selected" : ""}>${v}</option>`).join("")}</select></td>
      <td><div class="row" style="justify-content:flex-end;flex-wrap:nowrap"><button class="btn sm" onclick="camUpdate('${c.id}',{enabled:${!c.enabled}})">${c.enabled ? "Выключить" : "Включить"}</button>
      <button class="btn sm danger" onclick="camDelete('${c.id}','${esc(c.name)}')">Удалить</button></div></td></tr>`).join("")}</table>` : `<p class="note">Пока нет ни одной камеры.</p>`}</div>
  <div class="card"><h2>Добавить камеру</h2>
    <div class="tabs">${[["ip", "IP-камера или регистратор"], ["webcam", "Веб-камера"], ["file", "Видеофайл"]].map(([k, v]) => `<button class="${d.kind === k ? "on" : ""}" onclick="camKind('${k}')">${v}</button>`).join("")}</div>
    ${form}
    <div class="form" style="margin-top:12px">${inp("name", "Название (где висит камера)", "text", "Коридор, 2 этаж")}</div>
    <div class="row" style="margin-top:14px"><button class="btn" onclick="camTest()" ${t === "wait" ? "disabled" : ""}>${t === "wait" ? "Проверка…" : "Проверить подключение"}</button>
      <button class="btn primary" onclick="camAdd()">Добавить камеру</button>
      ${t && t !== "wait" ? (t.ok ? `<span class="okmsg">Камера отвечает: ${t.width}×${t.height}</span>` : `<span class="err">${esc(t.error)}</span>`) : ""}</div>
    ${t && t.ok ? `<img class="preview" src="${t.jpeg}" alt="Кадр с камеры">` : ""}</div>`;
}
async function camKind(k) { draft().kind = k; camDraft.test = null; renderCameras(); if (k === "webcam" && camDraft.webcams === null) { camDraft.webcams = await api("/api/webcams"); if (camDraft.webcams.length && camDraft.webcam === "") camDraft.webcam = String(camDraft.webcams[0]); if (page === "cameras") renderCameras(); } }
async function camTest() { const src = draftSource(); if (src === "") return toast("Сначала укажите адрес камеры"); camDraft.test = "wait"; renderCameras(); camDraft.test = await api("/api/cameras/test", { source: String(src) }); if (page === "cameras") renderCameras(); }
async function camAdd() {
  const src = draftSource(); if (src === "") return toast("Сначала укажите адрес камеры");
  const r = await api("/api/cameras", { source: String(src), name: camDraft.name });
  if (r.error) return toast(r.error);
  camDraft = null; toast(`Камера № ${r.no} добавлена`); page = "live"; lastKey = ""; poll();
}
async function camUpdate(id, patch) { await api(`/api/cameras/${id}`, patch); lastKey = ""; poll(); }
async function camDelete(id, name) { if (!confirm(`Удалить камеру «${name}»? Записи событий сохранятся.`)) return; await api(`/api/cameras/${id}/delete`, {}); lastKey = ""; poll(); }

// ------------------------------------------------------------------ telegram
function renderTelegram() {
  const t = S.telegram;
  const step1 = t.connected
    ? `<div class="step done"><div><b>Бот подключён: @${esc(t.bot_username)}</b><div class="note">От его имени приходят уведомления. <a href="#" onclick="tgDisconnect();return false">Сменить бота</a></div></div></div>`
    : `<div class="step"><div><b>Создайте бота для школы</b>
        <p class="note">Откройте в Telegram <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a>, отправьте ему команду <span class="mono">/newbot</span>, придумайте имя. В ответ придёт длинная строка — токен. Вставьте её сюда.</p>
        <div class="row" style="margin-top:8px"><input id="tok" type="text" class="grow" placeholder="1234567890:AA…" style="max-width:420px"><button class="btn primary" onclick="tgToken()">Подключить бота</button></div>
        <div id="tokerr" class="err"></div></div></div>`;
  let step2 = "";
  if (t.connected) {
    step2 = `<div class="step ${t.recipients.length ? "done" : ""}"><div><b>Кто получает тревоги</b>
      ${t.recipients.length ? `<table style="margin-top:6px">${t.recipients.map(r => `<tr><td>${esc(r.name)}</td><td class="mono">подключён ${fmtDate(r.added)}</td><td style="text-align:right"><button class="btn sm danger" onclick="tgRemove(${r.chat_id})">Отключить</button></td></tr>`).join("")}</table>` : `<p class="note">Пока никто не подключён.</p>`}
      ${bindInfo ? `<div class="bind"><div class="qr" id="qr"></div><div>
          <p>Наведите камеру телефона на QR-код и нажмите в Telegram кнопку <b>«Старт»</b>.</p>
          <p class="note" style="margin:8px 0 4px">Или откройте бота <a href="${esc(bindInfo.link)}" target="_blank" rel="noopener">@${esc(t.bot_username)}</a> и отправьте ему код:</p>
          <div class="code">${bindInfo.code.slice(0, 3)} ${bindInfo.code.slice(3)}</div>
          <p class="note" id="bindleft"></p></div></div>`
        : `<div class="row" style="margin-top:10px"><button class="btn primary" onclick="tgBind()">Подключить получателя</button>
           ${t.recipients.length ? `<button class="btn" onclick="tgTest()">Отправить проверочное сообщение</button>` : ""}</div>`}
      </div></div>`;
  }
  main.innerHTML = `<div class="head"><div><h1>Telegram</h1><p>При тревоге психолог или дежурный педагог получает видеозапись момента, номер камеры, дату и время. Подключение занимает минуту.</p></div></div>
  <div class="card"><div class="steps">${step1}${step2}</div>${t.error ? `<p class="err" style="margin-top:12px">${esc(t.error)}</p>` : ""}</div>
  <div class="card"><h2>Как выглядит уведомление</h2><pre class="msg">⚠️ Возможный конфликт

📷 Камера № 2 — Коридор, 2 этаж
📅 Дата: ${new Date().toLocaleDateString("ru-RU")}
🕒 Время: ${new Date().toLocaleTimeString("ru-RU")}
📈 Риск: 0.81 (порог ${(+(S.thresholds.balanced ?? 0.65)).toFixed(2)})
Признаки: удары и резкие движения рук/ног, захват, плотный контакт

[видео: ${S.settings.clip_pre_s} с до события и ${S.settings.clip_post_s} с после]
[✅ Подтвердить]  [❌ Ложная тревога]</pre></div>`;
  if (bindInfo) {
    const q = qrcode(0, "M"); q.addData(bindInfo.link); q.make();
    $("#qr").innerHTML = q.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
    clearInterval(bindTimer);
    const upd = () => { const left = Math.max(0, Math.round(bindInfo ? bindInfo.until - Date.now() / 1000 : 0)); const el = $("#bindleft"); if (!bindInfo || !left) { clearInterval(bindTimer); if (bindInfo) { bindInfo = null; if (page === "telegram") renderTelegram(); } return; } if (el) el.textContent = `Код действует ещё ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}. Страница обновится сама, когда человек подключится.`; };
    upd(); bindTimer = setInterval(upd, 1000);
  }
}
async function tgToken() { const r = await api("/api/telegram/token", { token: $("#tok").value }); if (!r.ok) { $("#tokerr").textContent = r.error; return; } lastKey = ""; await poll(); }
async function tgDisconnect() { if (!confirm("Отключить бота? Список получателей будет очищен.")) return; await api("/api/telegram/disconnect", {}); bindInfo = null; lastKey = ""; poll(); }
async function tgBind() { const r = await api("/api/telegram/bind", {}); bindInfo = { ...r, until: Date.now() / 1000 + r.ttl }; renderTelegram(); }
async function tgRemove(id) { await api("/api/telegram/remove", { chat_id: id }); lastKey = ""; poll(); }
async function tgTest() { const r = await api("/api/telegram/test", {}); toast(r.ok ? "Сообщение отправлено — проверьте Telegram" : "Не получилось: " + r.error); }

// ------------------------------------------------------------------ настройки
function renderSettings() {
  const s = S.settings, th = S.thresholds || {};
  const desc = { sensitive: "Ловит больше конфликтов, но чаще ошибается. Для мест, где важно не пропустить.", balanced: "Лучший баланс пропусков и ложных тревог. Подходит большинству камер.", strict: "Тревога только при явных признаках. Для шумных мест: спортзал, столовая." };
  const num = (k, label, min, max, unit) => `<label>${label}<div class="row" style="flex-wrap:nowrap"><input type="number" min="${min}" max="${max}" value="${s[k]}" onchange="setS({${k}:+this.value})" style="width:90px"><span class="note">${unit}</span></div></label>`;
  main.innerHTML = `<div class="head"><div><h1>Настройки</h1></div></div>
  <div class="card"><h2>Чувствительность</h2><div class="opts">${Object.entries(SENS).map(([k, v]) => `<button class="opt ${s.sensitivity === k ? "on" : ""}" onclick="setS({sensitivity:'${k}'})"><b>${v}</b><span>${desc[k]}</span>${th[k] != null ? `<span class="mono">порог ${(+th[k]).toFixed(2)}</span>` : ""}</button>`).join("")}</div>
    <p class="note" style="margin-top:10px">Пороги подобраны на проверочных видео, которых система не видела при обучении. Для отдельной камеры чувствительность можно задать в разделе «Камеры».</p></div>
  <div class="card"><h2>Запись и приватность</h2>
    <label class="switch"><input type="checkbox" ${s.privacy_blur ? "checked" : ""} onchange="setS({privacy_blur:this.checked})"><span>Закрывать лица на записи<small>Головы людей заменяются крупными пикселями в трансляции, в сохранённых клипах и в Telegram. Система не распознаёт личности.</small></span></label>
    <div class="form" style="margin-top:14px">${num("clip_pre_s", "В клипе до события", 2, 15, "секунд")}${num("clip_post_s", "После события", 2, 15, "секунд")}${num("cooldown_s", "Пауза между тревогами с одной камеры", 10, 600, "секунд")}${num("retention_days", "Хранить записи", 1, 365, "дней, затем удалять")}</div></div>
  <div class="card"><h2>Программа</h2>
    <label class="switch"><input type="checkbox" ${s.autostart ? "checked" : ""} onchange="setS({autostart:this.checked})"><span>Запускать вместе с Windows<small>Наблюдение начнётся само после включения компьютера.</small></span></label>
    <p class="note" style="margin-top:12px">Вычисления: ${S.device === "GPU" ? "видеокарта (быстро)" : "процессор"} · версия ${esc(S.version)}<br>Записи и настройки хранятся на этом компьютере: <span class="mono">${esc(S.home)}</span></p>
    <div class="row" style="margin-top:12px"><button class="btn danger" onclick="quitApp()">Остановить наблюдение и выйти</button></div></div>`;
}
async function setS(patch) { await api("/api/settings", patch); lastKey = ""; poll(); }
async function quitApp() { if (!confirm("Остановить наблюдение? Тревоги перестанут приходить, пока программа не будет запущена снова.")) return; await api("/api/quit", {}); main.innerHTML = `<div class="empty"><h2>Наблюдение остановлено</h2><p>Окно можно закрыть.</p></div>`; clearInterval(pollTimer); }

render();
poll();
const pollTimer = setInterval(poll, 1000);
setInterval(() => { if (page === "events") loadEvents(); }, 5000);
