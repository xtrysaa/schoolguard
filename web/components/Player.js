"use client";
import { useEffect, useRef, useState } from "react";
import { T } from "../lib/i18n";

const BONES = [[5,7],[7,9],[6,8],[8,10],[5,6],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
const KP = 0.3;
const SIGNAL_KEYS = ["strikes", "contact", "fall", "encirclement", "pursuit", "motion"];
const COLORS = { calm: "#35D6E8", warn: "#E8A21C", alert: "#FF4D4D" };

// кадр анализа для момента времени t + доля до следующего (для плавной интерполяции скелетов)
function locate(frames, t) {
  let lo = 0, hi = frames.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (frames[m].t <= t) lo = m; else hi = m - 1; }
  const a = frames[lo], b = frames[Math.min(lo + 1, frames.length - 1)];
  const span = b.t - a.t;
  return [lo, span > 0 ? Math.min(Math.max((t - a.t) / span, 0), 1) : 0];
}

export function draw(ctx, W, H, data, t, layers) {
  ctx.clearRect(0, 0, W, H);
  const [i, f] = locate(data.frames, t);
  const A = data.frames[i], B = data.frames[Math.min(i + 1, data.frames.length - 1)];
  const next = {};
  for (const p of B.p) next[p.id] = p;
  const level = A.a ? "alert" : A.s >= 0.6 * data.t_high ? "warn" : "calm";
  const lw = Math.max(2, W / 320);
  ctx.lineCap = "round"; ctx.lineJoin = "round";

  if (layers.trails) {
    const from = Math.max(0, i - 14), tr = {};
    for (let j = from; j <= i; j++) for (const p of data.frames[j].p) (tr[p.id] ||= []).push([(p.b[0] + p.b[2]) / 2, p.b[3]]);
    ctx.lineWidth = 1.5;
    for (const id in tr) {
      const pts = tr[id];
      for (let j = 1; j < pts.length; j++) {
        ctx.strokeStyle = `rgba(255,255,255,${(j / pts.length) * 0.55})`;
        ctx.beginPath(); ctx.moveTo(pts[j - 1][0] * W, pts[j - 1][1] * H); ctx.lineTo(pts[j][0] * W, pts[j][1] * H); ctx.stroke();
      }
    }
  }

  for (const p of A.p) {
    const q = next[p.id];
    const k = p.k.map((a, j) => {
      const b = q && q.k[j];
      return b && a[2] >= KP && b[2] >= KP ? [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2]] : a;
    });
    const hot = level !== "calm" && A.pr && A.pr.includes(p.id);
    const col = hot ? COLORS[level] : COLORS.calm;
    if (layers.skeleton) {
      for (const [w, c] of [[lw + 2.5, "rgba(8,10,14,.55)"], [lw, col]]) {       // тёмная подложка: линии читаются на любом фоне
        ctx.strokeStyle = c; ctx.lineWidth = w;
        ctx.beginPath();
        for (const [a, b] of BONES) if (k[a][2] >= KP && k[b][2] >= KP) { ctx.moveTo(k[a][0] * W, k[a][1] * H); ctx.lineTo(k[b][0] * W, k[b][1] * H); }
        ctx.stroke();
      }
      ctx.fillStyle = "#fff";
      for (let j = 5; j < 17; j++) if (k[j][2] >= KP) { ctx.beginPath(); ctx.arc(k[j][0] * W, k[j][1] * H, lw * 0.8, 0, 6.3); ctx.fill(); }
    }
    if (layers.boxes && hot) {
      const b = q ? p.b.map((v, j) => v + (q.b[j] - v) * f) : p.b;
      ctx.strokeStyle = col; ctx.lineWidth = 1.5;
      ctx.strokeRect(b[0] * W, b[1] * H, (b[2] - b[0]) * W, (b[3] - b[1]) * H);
    }
  }
  return [i, level];
}

function Timeline({ data, t, onSeek, tr }) {
  const W = 800, H = 110, fr = data.frames, D = data.duration;
  const x = (s) => (s / D) * W, y = (v) => H - 16 - Math.min(v, 1) * (H - 28);
  const line = fr.map((f, i) => `${i ? "L" : "M"}${x(f.t).toFixed(1)},${y(f.s).toFixed(1)}`).join(" ");
  const zones = [];
  let s = null;
  fr.forEach((f, i) => {
    if (f.a && s === null) s = f.t;
    if (s !== null && (!f.a || i === fr.length - 1)) { zones.push([s, f.t]); s = null; }
  });
  const click = (e) => { const r = e.currentTarget.getBoundingClientRect(); onSeek(((e.clientX - r.left) / r.width) * D); };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} onClick={click} role="img" aria-label={tr.chartAria}>
      {[0, 0.5, 1].map((v) => <g key={v}><line x1="0" x2={W} y1={y(v)} y2={y(v)} stroke="#2B313A" /><text x="2" y={y(v) - 3}>{v.toFixed(1)}</text></g>)}
      {zones.map(([a, b], i) => <rect key={i} x={x(a)} y="0" width={Math.max(x(b) - x(a), 3)} height={H - 16} fill="#C1341C" fillOpacity=".28" />)}
      <line x1="0" x2={W} y1={y(data.t_high)} y2={y(data.t_high)} stroke="#E8A21C" strokeDasharray="5 4" />
      <text x={W - 4} y={y(data.t_high) - 4} textAnchor="end" style={{ fill: "#E8A21C" }}>{tr.thrLine} {data.t_high.toFixed(2)}</text>
      <path d={line} fill="none" stroke="#E9EBE6" strokeWidth="2" />
      <line x1={x(t)} x2={x(t)} y1="0" y2={H - 16} stroke="#fff" strokeWidth="1" />
      {[0, 1, 2, 3, 4, 5, 6, 7, 8].filter((s) => s <= D).map((s) => <text key={s} x={Math.min(x(s) + 2, W - 14)} y={H - 3}>{s} {tr.sec}</text>)}
    </svg>
  );
}

export default function Player({ base = "/replay", cam = "CAM 01", t = T.ru.P }) {
  const SIGNALS = SIGNAL_KEYS.map((k) => [k, t.sig[k][0], t.sig[k][1]]);
  const [index, setIndex] = useState([]);
  const [sel, setSel] = useState(null);
  const [data, setData] = useState(null);
  const [now, setNow] = useState({ i: 0, t: 0, level: "calm" });
  const [playing, setPlaying] = useState(true);
  const [rate, setRate] = useState(1);
  const [layers, setLayers] = useState({ skeleton: true, boxes: true, trails: false });
  const vref = useRef(null), cref = useRef(null), dref = useRef(null), lref = useRef(layers);
  lref.current = layers; dref.current = data;

  useEffect(() => {
    fetch(`${base}/index.json`).then((r) => r.json()).then((j) => { setIndex(j); const first = j.find((c) => c.label && c.alerts) || j[0]; if (first) setSel(first.id); }).catch(() => {});
  }, [base]);
  useEffect(() => {
    if (!sel) return;
    setData(null);
    fetch(`${base}/${sel}.json`).then((r) => r.json()).then(setData).catch(() => {});
  }, [sel, base]);
  useEffect(() => { if (vref.current) vref.current.playbackRate = rate; }, [rate, data]);

  useEffect(() => {
    let raf, last = -1, lastLevel = "";
    const loop = () => {
      const v = vref.current, c = cref.current, d = dref.current;
      if (v && c && d && d.frames.length) {
        const r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
        const W = Math.round(r.width * dpr), H = Math.round(r.height * dpr);
        if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
        const ctx = c.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const [i, level] = draw(ctx, r.width, r.height, d, v.currentTime, lref.current);
        if (i !== last || level !== lastLevel) { last = i; lastLevel = level; setNow({ i, t: v.currentTime, level }); }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = () => { const v = vref.current; if (!v) return; if (v.paused) { v.play(); setPlaying(true); } else { v.pause(); setPlaying(false); } };
  const seek = (t) => { const v = vref.current; if (v && data) v.currentTime = Math.max(0, Math.min(t, data.duration - 0.05)); };
  const fr = data?.frames[Math.min(now.i, (data?.frames.length || 1) - 1)];
  const level = fr ? now.level : "calm";
  // в тексте называем не больше двух самых сильных сигналов: блок имеет постоянную высоту и не двигает страницу
  const hot = fr ? SIGNALS.filter(([k]) => (fr.c[k] || 0) >= 0.4).sort((a, b) => fr.c[b[0]] - fr.c[a[0]]).slice(0, 2) : [];
  const status = t.st[level];
  const meta = index.find((c) => c.id === sel);
  const hotText = hot.map((h) => h[2]).join("; ");
  const why = !fr ? t.loading
    : level === "alert" ? `${t.sent} ${hot.length ? t.cause.replace("{v}", hotText) : t.causeDefault}`
    : hot.length ? t.noticed.replace("{v}", hotText)
    : t.normal;
  const clipTitle = (c) => `${c.label ? t.fight : t.calm} · ${c.title.split(" · ").slice(1).join(" · ")}`;
  const L = (k, label) => <button key={k} className={"ctl" + (layers[k] ? " on" : "")} aria-pressed={layers[k]} onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>{label}</button>;

  return (
    <div className="player">
      <div>
        <div className="screen" style={{ aspectRatio: data ? `${data.width}/${data.height}` : "4/3" }}>
          {sel && <video ref={vref} key={sel} src={`${base}/${sel}.mp4`} autoPlay muted loop playsInline />}
          <canvas ref={cref} />
          <div className="osd">{cam} · {fr ? fr.t.toFixed(1).padStart(4, "0") : "00.0"} {t.sec} · {t.people}: {fr ? fr.p.length : 0}</div>
          <div className={"osd right " + level}>{status}</div>
        </div>
        <div className="controls">
          <button className="ctl" onClick={toggle}>{playing ? t.pause : t.play}</button>
          {[0.25, 0.5, 1].map((r) => <button key={r} className={"ctl" + (rate === r ? " on" : "")} onClick={() => setRate(r)}>{r}×</button>)}
          <span className="ctl-sep" />
          {L("skeleton", t.skeleton)}{L("boxes", t.boxes)}{L("trails", t.trails)}
        </div>
        {data && (
          <div className="timeline">
            <div className="cap"><span>{t.riskTime}</span><span>{t.seek}</span></div>
            <Timeline data={data} t={fr ? fr.t : 0} onSeek={seek} tr={t} />
          </div>
        )}
      </div>

      <div className="panel">
        <div className="box">
          <h3>{t.nowH}</h3>
          <div className="risk"><b className={level}>{fr ? fr.s.toFixed(2) : "—"}</b><span>{t.risk01}<br />{t.thr} {data ? data.t_high.toFixed(2) : "—"}</span></div>
          <p className="why">{why}</p>
        </div>
        <div className="box">
          <h3>{t.seesH}</h3>
          {SIGNALS.map(([k, label]) => {
            const v = fr?.c[k] || 0;
            return <div className={"sigrow" + (v >= 0.4 ? " hot" : "")} key={k}><span>{label}</span><em>{v.toFixed(2)}</em><i><u style={{ width: `${Math.min(v, 1) * 100}%` }} /></i></div>;
          })}
        </div>
        <div className="box">
          <h3>{t.clipsH}</h3>
          <div className="cliplist">
            {index.map((c) => {
              const right = !!c.alerts === !!c.label;
              return (
                <button key={c.id} className={"clipbtn" + (sel === c.id ? " sel" : "")} onClick={() => { setSel(c.id); setPlaying(true); }}>
                  <span>{clipTitle(c)}</span>
                  <em className={right ? "hit" : "miss"}>{c.alerts ? t.alert : t.noAlert}{right ? "" : " · " + t.err}</em>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
