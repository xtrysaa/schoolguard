"use client";
import { useEffect, useRef, useState } from "react";
import { draw } from "./Player";

// Запись первого экрана: настоящий ролик из проверочной части и то, что система посчитала на нём.
export default function HeroLive({ clip = "clip02" }) {
  const [data, setData] = useState(null);
  const [now, setNow] = useState({ i: 0, level: "calm" });
  const vref = useRef(null), cref = useRef(null), dref = useRef(null);
  dref.current = data;

  useEffect(() => { fetch(`/replay/${clip}.json`).then((r) => r.json()).then(setData).catch(() => {}); }, [clip]);
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
        const [i, level] = draw(ctx, r.width, r.height, d, v.currentTime, { skeleton: true, boxes: true, trails: false });
        if (i !== last || level !== lastLevel) { last = i; lastLevel = level; setNow({ i, level }); }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const fr = data?.frames[Math.min(now.i, (data?.frames.length || 1) - 1)];
  const level = fr ? now.level : "calm";
  const status = { calm: "спокойно", warn: "риск растёт", alert: "тревога" }[level];
  return (
    <figure className="live">
      <div className="live-frame" style={{ aspectRatio: data ? `${data.width}/${data.height}` : "16/9" }}>
        <video ref={vref} src={`/replay/${clip}.mp4`} autoPlay muted loop playsInline />
        <canvas ref={cref} />
      </div>
      <figcaption>
        <span>Риск <b className={level}>{fr ? fr.s.toFixed(2) : "0.00"}</b></span>
        <span>порог <b>{data ? data.t_high.toFixed(2) : "0.65"}</b></span>
        <span>людей в кадре <b>{fr ? fr.p.length : 0}</b></span>
        <span className={"st " + level}>{status}</span>
      </figcaption>
    </figure>
  );
}
