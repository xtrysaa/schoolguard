// Секции «Как работает» и «Точность»: схемы и диаграммы вместо карточек и таблиц.
const pct = (v) => Math.round(v * 100);

// два условных скелета: 17 точек тела, как их видит система
const A = { head: [112, 52], sh: [[92, 84], [132, 84]], el: [[80, 120], [156, 100]], wr: [[86, 152], [190, 92]], hip: [[98, 162], [126, 162]], kn: [[92, 212], [134, 208]], an: [[86, 260], [142, 258]] };
const B = { head: [282, 58], sh: [[262, 90], [304, 92]], el: [[246, 122], [318, 126]], wr: [[234, 104], [324, 160]], hip: [[268, 168], [298, 170]], kn: [[262, 216], [306, 216]], an: [[256, 262], [312, 264]] };

function Figure({ p, color }) {
  const bones = [[p.sh[0], p.sh[1]], [p.sh[0], p.el[0]], [p.el[0], p.wr[0]], [p.sh[1], p.el[1]], [p.el[1], p.wr[1]], [p.sh[0], p.hip[0]], [p.sh[1], p.hip[1]],
    [p.hip[0], p.hip[1]], [p.hip[0], p.kn[0]], [p.kn[0], p.an[0]], [p.hip[1], p.kn[1]], [p.kn[1], p.an[1]]];
  const pts = [...p.sh, ...p.el, ...p.wr, ...p.hip, ...p.kn, ...p.an];
  return (
    <g>
      {bones.map(([a, b], i) => <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={color} strokeWidth="3" strokeLinecap="round" />)}
      <circle cx={p.head[0]} cy={p.head[1]} r="13" fill="none" stroke={color} strokeWidth="3" />
      {pts.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r="3.4" fill="#fff" />)}
    </g>
  );
}

export function HowItWorks({ m }) {
  const steps = [
    ["Камера", "IP-камера, видеорегистратор или веб-камера. Поток остаётся внутри школы.", "12 кадров в секунду"],
    ["Скелеты", "Нейросеть YOLO11-Pose находит людей и 17 точек тела. Трекер ведёт каждого человека от кадра к кадру.", "каждый кадр"],
    ["Признаки движения", "31 число на кадр: скорость руки или ноги в сторону другого, захват, падение, окружение, преследование. Расстояния считаются в «ростах человека», поэтому не важно, далеко ли камера.", "каждый кадр"],
    ["Оценка риска", `Градиентный бустинг из ${m.trees} деревьев смотрит на последние две секунды и выдаёт риск от 0 до 1.`, "окно 2 секунды"],
    ["Тревога и человек", "Если риск держится выше порога 0,8 секунды, запись момента уходит психологу в Telegram. Он смотрит и отмечает: подтверждено или ложная тревога.", "около 10 секунд"],
  ];
  return (
    <div className="how">
      <div className="how-figs">
        <figure>
          <svg viewBox="0 0 440 310" role="img" aria-label="Два условных скелета: система измеряет скорость руки в сторону другого человека и дистанцию между людьми">
            <Figure p={A} color="var(--alert)" />
            <Figure p={B} color="var(--accent)" />
            <line x1="196" y1="91" x2="232" y2="88" stroke="var(--alert)" strokeWidth="2" markerEnd="url(#arr)" />
            <defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--alert)" /></marker></defs>
            <text x="118" y="24" className="svg-t">скорость руки в сторону другого</text>
            <line x1="212" y1="30" x2="212" y2="80" stroke="var(--ink3)" strokeWidth="1" />
            <line x1="112" y1="288" x2="283" y2="288" stroke="var(--ink3)" strokeWidth="1.5" strokeDasharray="5 5" />
            <line x1="112" y1="282" x2="112" y2="294" stroke="var(--ink3)" strokeWidth="1.5" /><line x1="283" y1="282" x2="283" y2="294" stroke="var(--ink3)" strokeWidth="1.5" />
            <text x="197" y="306" textAnchor="middle" className="svg-t">дистанция: 0,8 роста</text>
            <text x="344" y="118" className="svg-t">17 точек тела</text>
            <line x1="340" y1="116" x2="322" y2="124" stroke="var(--ink3)" strokeWidth="1" />
          </svg>
          <figcaption>Лиц и одежды система не видит. Для неё человек — это 17 точек и то, как они движутся.</figcaption>
        </figure>
        <figure>
          <svg viewBox="0 0 400 150" role="img" aria-label="График риска: тревога включается, когда риск держится выше порога 0,8 секунды">
            <line x1="20" y1="58" x2="380" y2="58" stroke="var(--ink3)" strokeWidth="1.5" strokeDasharray="6 6" />
            <text x="24" y="50" className="svg-t">порог {m.thresholds.balanced.toFixed(2)}</text>
            <rect x="188" y="14" width="62" height="112" fill="var(--alert)" opacity=".14" />
            <path d="M20 118 C70 116 110 112 140 104 C165 96 172 70 188 52 C205 34 230 30 250 28 C300 24 340 30 380 26" fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
            <path d="M250 28 C300 24 340 30 380 26" fill="none" stroke="var(--alert)" strokeWidth="3" strokeLinecap="round" />
            <line x1="250" y1="14" x2="250" y2="126" stroke="var(--alert)" strokeWidth="1.5" />
            <text x="219" y="142" textAnchor="middle" className="svg-t">0,8 с</text>
            <text x="258" y="142" className="svg-t svg-alert">тревога</text>
          </svg>
          <figcaption>Одного резкого кадра мало: риск должен продержаться выше порога. Так отсекаются случайные взмахи.</figcaption>
        </figure>
      </div>
      <ol className="steps">
        {steps.map(([title, text, when]) => (
          <li key={title}><div><h3>{title}</h3><p>{text}</p></div><span>{when}</span></li>
        ))}
      </ol>
    </div>
  );
}

function Bars({ recall, fpr }) {
  return (
    <div className="bars">
      <div className="bar"><i style={{ width: `${pct(recall)}%` }} className="good" /><span><b>{pct(recall)}</b> из 100 драк замечено</span></div>
      <div className="bar"><i style={{ width: `${pct(fpr)}%` }} className="bad" /><span><b>{pct(fpr)}</b> из 100 спокойных сцен с ложной тревогой</span></div>
    </div>
  );
}

export function Accuracy({ m, modes, sources }) {
  const bal = m.clip_test.balanced;
  return (
    <div className="acc">
      <div>
        <h3 className="acc-h">Три режима чувствительности</h3>
        <div className="modes">
          {modes.map(([k, name]) => (
            <div key={k} className={"mode" + (k === "balanced" ? " main" : "")}>
              <div className="mode-h"><b>{name.replace(" (по умолчанию)", "")}</b>{k === "balanced" && <em>по умолчанию</em>}<span>порог {m.thresholds[k].toFixed(2)}</span></div>
              <Bars recall={m.clip_test[k].all.recall} fpr={m.clip_test[k].all.fpr} />
            </div>
          ))}
        </div>
        <p className="small">Чем выше чувствительность, тем меньше пропусков и больше ложных тревог. Пороги подбирались на отдельной части данных, не на проверочной.</p>
      </div>
      <div>
        <h3 className="acc-h">На каких видео система сильнее и слабее</h3>
        <div className="srcs">
          {Object.keys(sources).filter((s) => bal[s]).map((s) => {
            const r = bal[s], [nm, sub] = sources[s].split(" — ");
            return (
              <div className="src" key={s}>
                <div className="src-h"><b>{nm}</b><span>{sub} · {r.n} записей</span><em>AUC {r.roc_auc.toFixed(2)}</em></div>
                <div className="duo">
                  <div><i className="good" style={{ width: `${pct(r.recall)}%` }} /><span>{pct(r.recall)}%</span></div>
                  <div><i className="bad" style={{ width: `${pct(r.fpr)}%` }} /><span>{pct(r.fpr)}%</span></div>
                </div>
              </div>
            );
          })}
        </div>
        <p className="legend"><span className="good" />замечено драк<span className="bad" />ложных тревог</p>
        <p className="small">Средняя чувствительность. Все вместе: {bal.all.n} записей, замечено {pct(bal.all.recall)}%, ложных {pct(bal.all.fpr)}%, AUC {m.clip_test_auc.toFixed(2)}.</p>
      </div>
    </div>
  );
}
