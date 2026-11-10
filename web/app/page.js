import Player from "../components/Player";
import Metrics from "../components/Metrics";

export default function Home() {
  return (
    <>
      <div className="wrap">
        <div className="topbar">
          <div className="logo">SCHOOL<span>GUARD</span></div>
          <nav className="nav">
            <a href="#demo">Демо</a><a href="#how">Как работает</a><a href="#metrics">Метрики</a>
            <a href="#live">Живой режим</a><a href="#ethics">Этика</a>
          </nav>
        </div>
        <div className="hero">
          <h1>ИИ, который <em>замечает буллинг</em> раньше, чем его заметят взрослые</h1>
          <p>Система анализирует видео из коридоров и рекреаций: скелеты, дистанции, траектории. Когда риск растёт,
            она отправляет короткий клип педагогу или психологу. Решение всегда принимает человек.</p>
          <div className="badges">
            <span className="badge">YOLO11-Pose</span><span className="badge">ByteTrack</span>
            <span className="badge">Random Forest / XGBoost</span><span className="badge">Human-in-the-Loop</span>
            <span className="badge">без распознавания лиц</span>
          </div>
        </div>
      </div>

      <div className="wrap" id="demo"><Player /></div>

      <section id="how"><div className="wrap">
        <h2>Как система «понимает» насилие</h2>
        <p className="lead">Нейросеть не смотрит на картинку целиком. Она превращает людей в скелеты и считает геометрию движения, а потом оценивает 30-кадровое окно (около секунды).</p>
        <div className="steps">
          <div className="card step"><b>01 · ДЕТЕКЦИЯ</b><p>YOLO11-Pose находит людей и 17 точек тела. ByteTrack сохраняет ID человека от кадра к кадру.</p></div>
          <div className="card step"><b>02 · ПРИЗНАКИ</b><p>Дистанции между людьми, скорость сближения, скорость руки к цели, угол окружения, векторы преследования, поза падения.</p></div>
          <div className="card step"><b>03 · РЕШЕНИЕ</b><p>Взвешенный Risk Score плюс обученный классификатор. Сглаживание и требование нескольких независимых сигналов снижают ложные тревоги.</p></div>
          <div className="card step"><b>04 · ЧЕЛОВЕК</b><p>Клип и таймкод уходят психологу. Кнопки «Подтвердить» или «Ложная тревога» пополняют датасет для дообучения.</p></div>
        </div>
        <div style={{ height: 16 }} />
        <pre className="code">{`Risk = (0.35·Удары + 0.25·Окружение + 0.15·Преследование + 0.17·Поза + 0.08·Мимика) · A
A    = 0.65 + 0.35·min(k, 2)/2      k — число активных телесных сигналов (≥ 0.4)
Score = 0.7·P(классификатор) + 0.3·Risk   → сглаживание по окну 30 кадров → порог + гистерезис`}</pre>
        <p className="note">Вес мимики минимальный: выражение лица не равно внутреннему состоянию (L. F. Barrett и др., 2019).</p>
      </div></section>

      <section id="metrics"><div className="wrap">
        <h2>Насколько система точна</h2>
        <p className="lead">Метрики считаются на тестовых роликах, которые модель не видела при обучении (разбиение по видео).</p>
        <div className="card"><Metrics /></div>
      </div></section>

      <section id="live"><div className="wrap">
        <h2>Живой режим на школьных камерах</h2>
        <div className="two">
          <div className="card">
            <h3>Схема</h3>
            <pre className="code">{`IP-камеры (RTSP) → школьный сервер (GPU)
  YOLO-Pose + ByteTrack → Risk Score
     ├─ клип 3 с до + 3 с после → Telegram психологу
     └─ события → этот сайт`}</pre>
          </div>
          <div className="card">
            <h3>Условия</h3>
            <ul className="list">
              <li>Сервер работает круглосуточно в локальной сети школы.</li>
              <li>Видеопоток не покидает школу, наружу уходят только клипы с замазанными головами.</li>
              <li>Для публичной демо на Vercel используется запись разбора, а не нейросеть в облаке.</li>
            </ul>
          </div>
        </div>
      </div></section>

      <section id="ethics"><div className="wrap">
        <h2>Этика и закон</h2>
        <div className="two">
          <div className="card"><ul className="list">
            <li>Нет распознавания личности: только ID треков и скелеты.</li>
            <li>Головы пикселизуются до анализа и в клипах.</li>
            <li>Система только предупреждает, наказаний и вердиктов нет.</li>
            <li>Обучение: открытые датасеты и постановочные сцены с письменного согласия.</li>
          </ul></div>
          <div className="card"><ul className="list">
            <li>Опора: Закон РК «О персональных данных и их защите» и защита прав ребёнка.</li>
            <li>Ограничение: игра и спорт могут давать ложные тревоги, поэтому нужен человек.</li>
            <li>Ограничение: мимика ненадёжна, её вес в формуле минимален.</li>
          </ul></div>
        </div>
      </div></section>

      <div className="wrap"><footer>SchoolGuard · научный проект · демо-ролики: Fight Detection Surv (MIT, Aktı et al., 2019)</footer></div>
    </>
  );
}
