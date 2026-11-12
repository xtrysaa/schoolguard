"use client";
import { useEffect, useState } from "react";
import { LANGS, T, fill } from "../lib/i18n";
import HeroStatus from "./HeroStatus";
import Player from "./Player";
import { Accuracy, Rows } from "./Sections";

const DOWNLOAD = "https://github.com/xtrysaa/schoolguard/releases/latest/download/SchoolGuard.exe";
const REPO = "https://github.com/xtrysaa/schoolguard";
const pct = (v) => Math.round(v * 100);

export default function Home({ m }) {
  const [lang, setLang] = useState("ru");
  // язык: сохранённый выбор, иначе язык браузера (казахский и английский распознаются, остальным — русский)
  useEffect(() => {
    let l = null;
    try { l = localStorage.getItem("sg_lang"); } catch {}
    if (!T[l]) { const n = (navigator.language || "").toLowerCase(); l = n.startsWith("kk") ? "kk" : n.startsWith("en") ? "en" : "ru"; }
    setLang(l);
  }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const choose = (l) => { setLang(l); try { localStorage.setItem("sg_lang", l); } catch {} };

  const t = T[lang], bal = m.clip_test.balanced.all, size = t.size;
  return (
    <>
      <header className="nav" id="top">
        <a className="logo" href="#top" aria-label="SchoolGuard"><img src="/icon.svg" width="28" height="28" alt="" />SchoolGuard</a>
        <nav>
          <a href="#demo">{t.nav.demo}</a><a href="#how">{t.nav.how}</a><a href="#numbers">{t.nav.numbers}</a><a href="#app">{t.nav.app}</a><a href="#faq">{t.nav.faq}</a>
        </nav>
        <div className="langsw" role="group" aria-label={t.nav.lang}>
          {LANGS.map(([k, label]) => <button key={k} className={lang === k ? "on" : ""} aria-pressed={lang === k} onClick={() => choose(k)}>{label}</button>)}
        </div>
        <a className="btn" href={DOWNLOAD}>{t.nav.download}</a>
      </header>

      <section className="herovid">
        <video src="/promo.mp4" poster="/promo-poster.jpg" autoPlay muted loop playsInline aria-hidden="true" />
        <div className="wrap herovid-in">
          <div>
            <a className="badge" href={REPO}>{t.hero.badge} <span aria-hidden="true">↗</span></a>
            <h1>{t.hero.h1}</h1>
            <p className="lead">{t.hero.lead}</p>
            <div className="cta">
              <a className="btn big" href={DOWNLOAD}>{t.hero.cta1}</a>
              <a className="btn ghost big" href="#demo">{t.hero.cta2}</a>
            </div>
          </div>
          <HeroStatus steps={t.hero.status} />
        </div>
        <p className="herovid-note">{t.hero.note}</p>
      </section>

      <div className="wrap">
        <section className="panel" id="demo">
          <div className="chead"><h2>{t.demo.h2}</h2><p>{t.demo.p}</p></div>
          <Player t={t.P} />
          <p className="fine">{t.demo.fine}</p>
        </section>

        <section className="sec2" id="how">
          <div className="chead"><h2>{t.how.h2}</h2></div>
          <Rows m={m} t={t.how} phone={<img className="phone" src={`/phone-${lang}.png`} width="900" height="1760" alt={t.how.phoneAlt} />} />
        </section>

        <section className="sec2" id="numbers">
          <div className="chead"><h2>{t.numbers.h2}</h2><p>{fill(t.numbers.p, { n: bal.n })}</p></div>
          <div className="nums">
            <div><b>{pct(bal.recall)} {t.numbers.of} 100</b><span>{t.numbers.cards[0]}</span></div>
            <div><b>{pct(bal.fpr)} {t.numbers.of} 100</b><span>{t.numbers.cards[1]}</span></div>
            <div><b>{bal.n}</b><span>{t.numbers.cards[2]}</span></div>
            <div><b>0 ₸</b><span>{t.numbers.cards[3]}</span></div>
          </div>
          <Accuracy m={m} t={t.numbers} />
          <ul className="plain limits">{t.numbers.limits.map((x) => <li key={x}>{x}</li>)}</ul>
        </section>

        <section className="panel alt" id="app">
          <div className="chead"><h2>{t.app.h2}</h2><p>{t.app.p}</p></div>
          <div className="appgrid">
            <figure className="shot">
              <img src={`/app-live-${lang}.jpg`} alt={t.app.shotAlt} width="800" height="518" />
              <figcaption>{t.app.shotCap}</figcaption>
            </figure>
            <ol className="setup">
              {t.app.steps.map(([h, p]) => <li key={h}><div><h3>{h}</h3><p>{fill(p, { size })}</p></div></li>)}
            </ol>
          </div>
        </section>

        <section className="sec2" id="privacy">
          <div className="chead"><h2>{t.priv.h2}</h2></div>
          <div className="priv">{t.priv.cards.map(([h, p]) => <div key={h}><h3>{h}</h3><p>{p}</p></div>)}</div>
          <p className="fine center">{t.priv.law}</p>
        </section>

        <section className="sec2 faqsec" id="faq">
          <h2>{t.faq.h2}</h2>
          <div className="faq">{t.faq.items.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div>
        </section>

        <section className="panel final">
          <h2>{t.final.h2}</h2>
          <p>{fill(t.final.p, { size })}</p>
          <a className="btn big" href={DOWNLOAD}>{t.final.cta}</a>
        </section>

        <footer>
          <span>{t.foot[0]}</span><span>{t.foot[1]}</span><span><a href={REPO}>GitHub</a></span>
        </footer>
      </div>
    </>
  );
}
