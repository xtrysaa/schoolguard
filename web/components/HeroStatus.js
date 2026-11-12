"use client";
import { useEffect, useState } from "react";

// Столбик состояний на первом экране: подсвечивается та строка, которая соответствует моменту ролика.
// Границы в секундах: до 4,5 с идёт коридор и сканер, до 7 с — толчок и красная рамка, дальше — пульт и тревога.
const STEPS = [[0, "Оценивает движение людей"], [4.5, "Замечает признаки конфликта"], [7, "Отправляет запись психологу"]];

export default function HeroStatus() {
  const [on, setOn] = useState(0);
  useEffect(() => {
    const v = document.querySelector(".herovid video");
    if (!v) return;
    const upd = () => {
      let i = 0;
      STEPS.forEach(([t], k) => { if (v.currentTime >= t) i = k; });
      setOn(i);
    };
    v.addEventListener("timeupdate", upd);
    upd();
    return () => v.removeEventListener("timeupdate", upd);
  }, []);
  return (
    <ul className="status" aria-label="Что делает система">
      {STEPS.map(([, text], i) => <li key={text} className={i === on ? "on" : ""}>{text}</li>)}
    </ul>
  );
}
