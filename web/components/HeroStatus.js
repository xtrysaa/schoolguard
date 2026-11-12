"use client";
import { useEffect, useState } from "react";

// Столбик состояний на первом экране: подсвечивается та строка, которая соответствует моменту ролика.
// Границы в секундах: до 4,5 с идёт коридор и сканер, до 7 с — толчок и красная рамка, дальше — пульт и тревога.
const TIMES = [0, 4.5, 7];

export default function HeroStatus({ steps }) {
  const [on, setOn] = useState(0);
  useEffect(() => {
    const v = document.querySelector(".herovid video");
    if (!v) return;
    const upd = () => {
      let i = 0;
      TIMES.forEach((t, k) => { if (v.currentTime >= t) i = k; });
      setOn(i);
    };
    v.addEventListener("timeupdate", upd);
    upd();
    return () => v.removeEventListener("timeupdate", upd);
  }, []);
  return (
    <ul className="status">
      {steps.map((text, i) => <li key={i} className={i === on ? "on" : ""}>{text}</li>)}
    </ul>
  );
}
