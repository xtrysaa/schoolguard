"use client";
import { useEffect, useMemo, useRef, useState } from "react";

const EDGES = [[5,7],[7,9],[6,8],[8,10],[5,6],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16],[0,5],[0,6]];
const KP = 0.3;
const COMP = [
  { key: "physical", label: "Удары / резкое сближение", w: 0.35, color: "#ff6b3d" },
  { key: "encirclement", label: "Окружение / зажатие", w: 0.25, color: "#c264ff" },
  { key: "pursuit", label: "Преследование", w: 0.15, color: "#ffb020" },
  { key: "distress", label: "Поза дистресса", w: 0.17, color: "#ff3b5c" },
  { key: "face", label: "Мимика (вес 8%)", w: 0.08, color: "#22e6ff" },
];
const WHY = {
  physical: "резкое сближение и быстрые движения рук в сторону другого человека",
  encirclement: "один человек окружён группой и не может отойти",
  pursuit: "один быстро уходит, остальные движутся по его траектории",
  distress: "поза падения или защиты руками рядом с другим человеком",
  face: "негативная мимика",
};

const pt = (k, i) => (k[i][2] >= KP ? [k[i][0], k[i][1]] : null);
const mid = (a, b) => (a && b ? [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] : a || b);
function centroid(p) {
  const k = p.k;
  const m = mid(mid(pt(k, 11), pt(k, 12)), mid(pt(k, 5), pt(k, 6)));
  return m || [(p.b[0] + p.b[2]) / 2, (p.b[1] + p.b[3]) / 2];
}

function draw(ctx, W, H, data, idx, t, layers) {
  ctx.clearRect(0, 0, W, H);
  const fr = data.frames[idx];
  if (!fr) return;
  const alert = !!fr.a;
  const main = alert ? "#ff3b5c" : "#22e6ff";
  const pulse = 0.5 + 0.5 * Math.sin(t * 8);

  // сканлайны и виньетка
  if (layers.hud) {
    ctx.fillStyle = "rgba(0,0,0,.10)";
    for (let y = 0; y < H; y += 3) ctx.fillRect(0, y, W, 1);
    const g = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.85);
    g.addColorStop(0, "rgba(0,0,0,0)");
    g.addColorStop(1, alert ? `rgba(255,30,70,${0.25 + 0.25 * pulse})` : "rgba(0,10,20,.55)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }

  const byId = {};
  fr.p.forEach((p) => (byId[p.id] = p));

  // траектории
  if (layers.trails) {
    const from = Math.max(0, idx - 24);
    const tr = {};
    for (let i = from; i <= idx; i++) for (const p of data.frames[i].p) (tr[p.id] ||= []).push(centroid(p));
    for (const id in tr) {
      const pts = tr[id];
      for (let i = 1; i < pts.length; i++) {
        ctx.strokeStyle = `rgba(${alert ? "255,90,120" : "34,230,255"},${(i / pts.length) * 0.7})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(pts[i - 1][0] * W, pts[i - 1][1] * H);
        ctx.lineTo(pts[i][0] * W, pts[i][1] * H);
        ctx.stroke();
      }
    }
  }

  // окружение: кольцо и линии к соседям
  const victim = byId[fr.v];
  if (layers.rings && victim && fr.f.encirclement > 0.3) {
    const c = centroid(victim);
    const bh = (victim.b[3] - victim.b[1]) * H;
    const r = 1.8 * bh;
    ctx.save();
    ctx.strokeStyle = `rgba(194,100,255,${0.5 + 0.4 * pulse})`;
    ctx.lineWidth = 2; ctx.setLineDash([8, 6]); ctx.lineDashOffset = -t * 40;
    ctx.beginPath(); ctx.arc(c[0] * W, c[1] * H, r, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([3, 5]);
    for (const p of fr.p) {
      if (p.id === victim.id) continue;
      const o = centroid(p);
      const d = Math.hypot((o[0] - c[0]) * W, (o[1] - c[1]) * H);
      if (d < r) {
        ctx.strokeStyle = "rgba(194,100,255,.85)";
        ctx.beginPath(); ctx.moveTo(c[0] * W, c[1] * H); ctx.lineTo(o[0] * W, o[1] * H); ctx.stroke();
      }
    }
    ctx.restore();
  }

  for (const p of fr.p) {
    const isV = alert && p.id === fr.v;
    const col = isV ? "#ff3b5c" : main;
    const [x1, y1, x2, y2] = [p.b[0] * W, p.b[1] * H, p.b[2] * W, p.b[3] * H];

    if (layers.boxes) {
      const L = Math.min(18, (x2 - x1) / 3, (y2 - y1) / 3);
      ctx.strokeStyle = col; ctx.lineWidth = isV ? 3 : 2;
      ctx.shadowColor = col; ctx.shadowBlur = 10;
      ctx.beginPath();
      [[x1, y1, 1, 1], [x2, y1, -1, 1], [x1, y2, 1, -1], [x2, y2, -1, -1]].forEach(([x, y, dx, dy]) => {
        ctx.moveTo(x + dx * L, y); ctx.lineTo(x, y); ctx.lineTo(x, y + dy * L);
      });
      ctx.stroke(); ctx.shadowBlur = 0;
      ctx.font = "bold 11px ui-monospace, Consolas, monospace";
      const tag = `ID ${p.id}${isV ? " · ЦЕЛЬ" : ""}`;
      const tw = ctx.measureText(tag).width + 10;
      ctx.fillStyle = col; ctx.fillRect(x1, Math.max(y1 - 16, 0), tw, 15);
      ctx.fillStyle = "#001018"; ctx.fillText(tag, x1 + 5, Math.max(y1 - 5, 11));
    }

    if (layers.skeleton) {
      ctx.lineCap = "round";
      for (const pass of [0, 1]) {
        ctx.strokeStyle = pass ? "#ffffff" : col;
        ctx.lineWidth = pass ? 1.2 : 4;
        ctx.globalAlpha = pass ? 0.9 : 0.35;
        ctx.shadowColor = col; ctx.shadowBlur = pass ? 0 : 12;
        ctx.beginPath();
        for (const [a, b] of EDGES) {
          const A = pt(p.k, a), B = pt(p.k, b);
          if (A && B) { ctx.moveTo(A[0] * W, A[1] * H); ctx.lineTo(B[0] * W, B[1] * H); }
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1; ctx.shadowBlur = 0;
      p.k.forEach((k, i) => {
        if (k[2] < KP || i < 5 && i > 0) return;
        const wrist = i === 9 || i === 10;
        ctx.fillStyle = wrist && fr.f.strike > 1.2 ? "#ffb020" : "#fff";
        ctx.beginPath(); ctx.arc(k[0] * W, k[1] * H, wrist ? 4 : 2.5, 0, Math.PI * 2); ctx.fill();
      });
    }
  }

  if (layers.hud) {
    ctx.font = "bold 12px ui-monospace, Consolas, monospace";
    ctx.fillStyle = "#ff3b5c"; ctx.globalAlpha = 0.6 + 0.4 * pulse;
    ctx.beginPath(); ctx.arc(16, 18, 5, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
    ctx.fillStyle = "#cfefff";
    ctx.fillText(`REC  ${t.toFixed(2)}s  ·  ${fr.p.length} чел.`, 28, 22);
    ctx.fillStyle = "rgba(207,239,255,.7)";
    ctx.fillText("SCHOOLGUARD // POSE-TRACK", 12, H - 12);

    // шкала риска
    const bw = Math.min(220, W * 0.4), bx = W - bw - 14, by = H - 26;
    ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.fillRect(bx - 4, by - 18, bw + 8, 36);
    ctx.fillStyle = "#12202f"; ctx.fillRect(bx, by, bw, 8);
    ctx.fillStyle = alert ? "#ff3b5c" : fr.s >= data.t_high * 0.7 ? "#ffb020" : "#2bff88";
    ctx.fillRect(bx, by, bw * Math.min(fr.s, 1), 8);
    ctx.fillStyle = "#fff"; ctx.fillRect(bx + bw * data.t_high - 1, by - 4, 2, 16);
    ctx.fillStyle = "#cfefff"; ctx.fillText(`RISK ${fr.s.toFixed(2)}`, bx, by - 5);

    // флаги сигналов
    const flags = COMP.filter((c) => c.key !== "face" && fr.c[c.key] >= 0.4);
    flags.forEach((c, i) => {
      const label = c.label.split(" / ")[0].toUpperCase();
      const w = ctx.measureText(label).width + 16, x = W - w - 12, y = 12 + i * 24;
      ctx.fillStyle = "rgba(0,0,0,.6)"; ctx.fillRect(x, y, w, 19);
      ctx.fillStyle = c.color; ctx.fillRect(x, y, 3, 19);
      ctx.fillStyle = "#fff"; ctx.fillText(label, x + 9, y + 14);
    });

    if (alert) {
      const txt = "ТРЕБУЕТСЯ ПРОВЕРКА ПЕДАГОГОМ";
      ctx.font = "bold 14px ui-monospace, Consolas, monospace";
      const w = ctx.measureText(txt).width + 24;
      ctx.fillStyle = `rgba(255,59,92,${0.75 + 0.2 * pulse})`;
      ctx.fillRect((W - w) / 2, 34, w, 26);
      ctx.fillStyle = "#fff"; ctx.fillText(txt, (W - w) / 2 + 12, 52);
    }
  }
}

function Radar({ c }) {
  const n = COMP.length, R = 62, cx = 90, cy = 80;
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const P = (i, v) => [cx + Math.cos(ang(i)) * R * v, cy + Math.sin(ang(i)) * R * v];
  const poly = COMP.map((k, i) => P(i, Math.min(c[k.key] || 0, 1)).join(",")).join(" ");
  return (
    <svg viewBox="0 0 180 160" width="100%" style={{ maxHeight: 190 }}>
      {[0.25, 0.5, 0.75, 1].map((r) => (
        <polygon key={r} points={COMP.map((_, i) => P(i, r).join(",")).join(" ")} fill="none" stroke="#1b2a3f" />
      ))}
      {COMP.map((k, i) => {
        const [x, y] = P(i, 1.22);
        return <text key={k.key} x={x} y={y} textAnchor="middle" fontSize="8">{k.label.split(" ")[0]}</text>;
      })}
      <polygon points={poly} fill="#22e6ff33" stroke="#22e6ff" strokeWidth="1.5" />
    </svg>
  );
}

function Timeline({ data, idx, onSeek }) {
  const W = 600, H = 130, fr = data.frames, N = fr.length;
  const x = (i) => (i / Math.max(N - 1, 1)) * W;
  const y = (v) => H - 14 - Math.min(v, 1) * (H - 28);
  const line = fr.map((f, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(f.s).toFixed(1)}`).join(" ");
  const zones = [];
  let s = null;
  fr.forEach((f, i) => {
    if (f.a && s === null) s = i;
    if ((!f.a || i === N - 1) && s !== null) { zones.push([s, f.a ? i : i - 1]); s = null; }
  });
  const click = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * data.duration);
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" onClick={click} style={{ cursor: "pointer" }}>
      {[0, 0.5, 1].map((v) => (<g key={v}><line x1="0" x2={W} y1={y(v)} y2={y(v)} stroke="#1b2a3f" /><text x="2" y={y(v) - 2}>{v}</text></g>))}
      {zones.map(([a, b], i) => <rect key={i} x={x(a)} y="0" width={Math.max(x(b) - x(a), 2)} height={H} fill="#ff3b5c22" />)}
      <line x1="0" x2={W} y1={y(data.t_high)} y2={y(data.t_high)} stroke="#ffb020" strokeDasharray="5 4" />
      <text x={W - 70} y={y(data.t_high) - 3}>порог {data.t_high}</text>
      <path d={line} fill="none" stroke="#22e6ff" strokeWidth="2" />
      <line x1={x(idx)} x2={x(idx)} y1="0" y2={H} stroke="#fff" strokeWidth="1.2" />
    </svg>
  );
}

function Stack({ data, idx, onSeek }) {
  const W = 600, H = 130, fr = data.frames, N = fr.length;
  const x = (i) => (i / Math.max(N - 1, 1)) * W;
  const y = (v) => H - 14 - Math.min(v, 1) * (H - 28);
  const acc = fr.map(() => 0);
  const areas = COMP.map((k) => {
    const lo = [...acc];
    fr.forEach((f, i) => (acc[i] += k.w * (f.c[k.key] || 0)));
    const up = [...acc];
    const top = up.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const bot = lo.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse();
    return { k, d: `M${top.join(" L")} L${bot.join(" L")}Z` };
  });
  const click = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * data.duration);
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" onClick={click} style={{ cursor: "pointer" }}>
      {[0, 0.5, 1].map((v) => (<g key={v}><line x1="0" x2={W} y1={y(v)} y2={y(v)} stroke="#1b2a3f" /><text x="2" y={y(v) - 2}>{v}</text></g>))}
      {areas.map((a) => <path key={a.k.key} d={a.d} fill={a.k.color} fillOpacity=".75" />)}
      <line x1={x(idx)} x2={x(idx)} y1="0" y2={H} stroke="#fff" strokeWidth="1.2" />
    </svg>
  );
}

export default function Player() {
  const [index, setIndex] = useState([]);
  const [sel, setSel] = useState(null);
  const [data, setData] = useState(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [rate, setRate] = useState(0.5);
  const [layers, setLayers] = useState({ skeleton: true, boxes: true, trails: true, rings: true, hud: true });
  const vref = useRef(null), cref = useRef(null), dref = useRef(null), lref = useRef(layers), iref = useRef(0);
  lref.current = layers; dref.current = data;

  useEffect(() => {
    fetch("/replay/index.json").then((r) => r.json()).then((j) => { setIndex(j); if (j[0]) setSel(j[0].id); }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!sel) return;
    setData(null);
    fetch(`/replay/${sel}.json`).then((r) => r.json()).then(setData).catch(() => {});
  }, [sel]);
  useEffect(() => { if (vref.current) vref.current.playbackRate = rate; }, [rate, data]);

  useEffect(() => {
    let raf;
    const loop = () => {
      const v = vref.current, c = cref.current, d = dref.current;
      if (v && c && d) {
        const r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
        const W = Math.round(r.width * dpr), H = Math.round(r.height * dpr);
        if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
        const i = Math.min(d.frames.length - 1, Math.max(0, Math.round(v.currentTime * d.fps)));
        const ctx = c.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        draw(ctx, r.width, r.height, d, i, v.currentTime, lref.current);
        if (i !== iref.current) { iref.current = i; setIdx(i); }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = () => {
    const v = vref.current; if (!v) return;
    if (v.paused) { v.play(); setPlaying(true); } else { v.pause(); setPlaying(false); }
  };
  const seek = (t) => { const v = vref.current; if (v) { v.currentTime = Math.max(0, Math.min(t, data.duration - 0.01)); } };
  const fr = data?.frames[Math.min(idx, (data?.frames.length || 1) - 1)];
  const alert = !!fr?.a;
  const active = useMemo(() => (fr ? COMP.filter((c) => c.key !== "face" && fr.c[c.key] >= 0.4) : []), [fr]);
  const peak = data ? Math.max(...data.frames.map((f) => f.s)) : 0;

  const L = (k, label) => (
    <button key={k} className={"btn" + (layers[k] ? " on" : "")} onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>{label}</button>
  );

  return (
    <div>
      <div className="grid">
        <div className="card">
          <h3>Видео · аналитика поверх кадра</h3>
          <div className="stage" style={{ aspectRatio: data ? `${data.width}/${data.height}` : "4/3" }}>
            {sel && <video ref={vref} key={sel} src={`/replay/${sel}.mp4`} autoPlay muted loop playsInline />}
            <canvas ref={cref} />
          </div>
          <div className="toolbar">
            <button className="btn" onClick={toggle}>{playing ? "⏸ Пауза" : "▶ Играть"}</button>
            {[0.25, 0.5, 1].map((r) => <button key={r} className={"btn" + (rate === r ? " on" : "")} onClick={() => setRate(r)}>{r}×</button>)}
            <span style={{ width: 8 }} />
            {L("skeleton", "Скелеты")}{L("boxes", "Рамки")}{L("trails", "Траектории")}{L("rings", "Окружение")}{L("hud", "HUD")}
          </div>
          <div className="clips">
            {index.map((c) => (
              <button key={c.id} className={"clip " + (c.label ? "fight " : "") + (sel === c.id ? "sel" : "")} onClick={() => { setSel(c.id); setPlaying(true); }}>
                <b>{c.title.replace(" · ", " ")}</b> · пик {c.peak.toFixed(2)}{c.alerts ? " ⚠" : ""}
              </button>
            ))}
          </div>
          <p className="note">Видео из открытого датасета Fight Detection Surv (MIT). Ролики выбраны по качеству видео и могли входить в обучающую выборку, поэтому честную точность смотрите в таблице метрик на тестовых данных. Головы пикселизованы до анализа — лица и личности не обрабатываются. Мимика в публичной демо отключена. Для наглядности скелеты нарисованы крупной моделью позы (YOLO11x), а риск считает рабочая лёгкая модель (YOLO11n), как при обучении.</p>
        </div>

        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          <div className="card">
            <h3>Решение системы (по кадру)</h3>
            <div className="verdict">
              <div className="score" style={{ color: alert ? "var(--red)" : fr && fr.s >= (data?.t_high || 0.4) * 0.7 ? "var(--amber)" : "var(--green)" }}>{fr ? fr.s.toFixed(2) : "—"}</div>
              <div>
                <span className={"pill " + (alert ? "alert" : fr && fr.s >= (data?.t_high || 0.4) * 0.7 ? "warn" : "ok")}>
                  {alert ? "ТРЕВОГА → педагогу" : fr && fr.s >= (data?.t_high || 0.4) * 0.7 ? "ПОВЫШЕННОЕ ВНИМАНИЕ" : "НОРМА"}
                </span>
                <div className="note">пик по ролику: {peak.toFixed(2)} · порог {data?.t_high ?? "—"}</div>
              </div>
            </div>
            <p className="why">
              {!fr ? "Загрузка…" : active.length
                ? "Почему: " + active.map((c) => WHY[c.key]).join("; ") + (fr.m != null && fr.m >= 0.5 ? "; классификатор подтверждает паттерн (P=" + fr.m.toFixed(2) + ")." : ".")
                : fr.m != null && fr.m >= 0.5
                  ? `Явных отдельных сигналов нет, но классификатор по динамике всего окна оценивает вероятность конфликта в ${fr.m.toFixed(2)}.`
                  : "Паттернов, характерных для насилия, нет: движения и дистанции в пределах нормы."}
            </p>
            <p className="note">Система ничего не решает сама: человек подтверждает или отклоняет тревогу.</p>
          </div>

          <div className="card">
            <h3>Сигналы тела и пространства</h3>
            {fr && <Radar c={fr.c} />}
            {COMP.map((c) => {
              const v = fr?.c[c.key] || 0;
              return (
                <div className="sig" key={c.key}>
                  <span>{c.label}</span><span>{v.toFixed(2)}</span>
                  <div className="bar"><i style={{ width: `${Math.min(v, 1) * 100}%`, background: c.color }} /></div>
                </div>
              );
            })}
            <div className="sig">
              <span>ML-классификатор P(конфликт), вес 70%</span><span>{fr?.m != null ? fr.m.toFixed(2) : "—"}</span>
              <div className="bar"><i style={{ width: `${Math.min(fr?.m || 0, 1) * 100}%`, background: "#2bff88" }} /></div>
            </div>
          </div>
        </div>
      </div>

      {data && (
        <div className="charts">
          <div className="card">
            <h3>Risk Score во времени</h3>
            <Timeline data={data} idx={idx} onSeek={seek} />
            <p className="note">Красная зона — период тревоги. Клик по графику перематывает видео.</p>
          </div>
          <div className="card">
            <h3>Из чего складывается риск</h3>
            <Stack data={data} idx={idx} onSeek={seek} />
            <div className="legend">{COMP.map((c) => <span key={c.key}><i style={{ background: c.color }} />{c.label.split(" / ")[0]}</span>)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
