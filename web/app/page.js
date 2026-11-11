import Player from "../components/Player";
import m from "../public/replay/metrics.json";

const DOWNLOAD = "https://github.com/xtrysaa/schoolguard/releases/latest/download/SchoolGuard.exe";
const REPO = "https://github.com/xtrysaa/schoolguard";
const pct = (v) => Math.round(v * 100);
const SOURCES = { rlvs: "RLVS — съёмка с телефонов и из интернета", cctv: "CCTV-Fights — камеры наблюдения", cctvmob: "CCTV-Fights — телефоны, видеорегистраторы", surv: "Surv — уличные и офисные камеры" };
const MODES = [["sensitive", "Высокая"], ["balanced", "Средняя (по умолчанию)"], ["strict", "Низкая"]];

function Logo() {
  return (
    <a className="logo" href="#top" aria-label="SchoolGuard">
      <img src="/icon.svg" width="28" height="28" alt="" />SchoolGuard
    </a>
  );
}

export default function Home() {
  const bal = m.clip_test.balanced.all;
  return (
    <>
      <div className="wrap" id="top">
        <header className="top">
          <Logo />
          <nav>
            <a href="#demo">Демо</a><a href="#how">Как работает</a><a href="#app">Приложение</a><a href="#accuracy">Точность</a><a href="#privacy">Приватность</a>
          </nav>
          <a className="btn sm" href={DOWNLOAD}>Скачать</a>
        </header>

        <div className="hero">
          <div>
            <div className="eyebrow">Раннее предупреждение для школ</div>
            <h1>Камера замечает драку. Психолог узнаёт через десять секунд.</h1>
            <p className="lead">SchoolGuard подключается к школьным камерам, следит за движениями людей и присылает видеозапись
              момента в Telegram: номер камеры, дата, время. Лица закрыты. Что делать дальше, решает человек.</p>
            <div className="cta">
              <a className="btn" href={DOWNLOAD}>Скачать для Windows</a>
              <a className="btn ghost" href="#demo">Посмотреть, как видит система</a>
            </div>
          </div>
          <div className="facts" aria-label="Коротко о системе">
            <div><span>Замечает драк на проверочных видео</span><span>{pct(bal.recall)} из 100</span></div>
            <div><span>Ложных тревог на спокойных сценах</span><span>{pct(bal.fpr)} из 100</span></div>
            <div><span>Проверено на видео, не участвовавших в обучении</span><span>{bal.n} записей</span></div>
            <div><span>Где работает</span><span>компьютер школы, без облака</span></div>
            <div><span>Исходный код</span><span><a href={REPO}>открыт на GitHub</a></span></div>
          </div>
        </div>
      </div>

      <div className="stageband" id="demo">
        <div className="wrap">
          <div className="stagehead">
            <h2>Вот что видит система</h2>
            <p>Она не узнаёт людей и не смотрит на лица. Каждый человек для неё — семнадцать точек тела, а конфликт — то, как эти точки движутся рядом друг с другом.</p>
          </div>
          <Player />
          <p className="fine">Записи из открытого набора Fight Detection Surv (лицензия MIT). Все они из проверочной части: при обучении система их не видела.
            Ролики отбирались по качеству изображения, а не по ответу системы, поэтому её ошибки здесь тоже видны и подписаны.</p>
        </div>
      </div>

      <div className="wrap">
        <section className="sec" id="how">
          <div className="sechead">
            <div className="num">01 — Как работает</div>
            <div><h2>От кадра до сообщения в Telegram — пять шагов</h2>
              <p>Картинка целиком в решении не участвует. Система переводит людей в скелеты, считает геометрию их движения и оценивает последние две секунды.</p></div>
          </div>
          <div className="chain">
            <div><b>01</b><h3>Камера</h3><p>IP-камера, видеорегистратор или веб-камера. Поток остаётся внутри школы.</p></div>
            <div><b>02</b><h3>Скелеты</h3><p>Нейросеть YOLO11-Pose находит людей и 17 точек тела. Трекер ByteTrack ведёт каждого от кадра к кадру.</p></div>
            <div><b>03</b><h3>31 признак</h3><p>Скорость рук и ног в сторону другого, захват, падение, окружение, преследование, всплеск движения.</p></div>
            <div><b>04</b><h3>Оценка риска</h3><p>Градиентный бустинг ({m.trees} деревьев) оценивает окно в две секунды. Тревога, если риск держится выше порога.</p></div>
            <div><b>05</b><h3>Человек</h3><p>Запись момента уходит в Telegram. Психолог смотрит и отмечает: подтверждено или ложная тревога.</p></div>
          </div>
          <div className="indent">
            <div className="formula">{`признаки кадра  →  окно 2 с: среднее, максимум, разброс, минимум  →  P(конфликт)
тревога, если  P ≥ порог  не меньше 0,8 с подряд;   снимается, когда  P < 0,6 · порог  в течение 2 с
все расстояния — в «ростах человека», скорости — в «ростах в секунду»: не важно, далеко ли камера`}</div>
            <p className="small">Шесть сигналов на панели справа от видео — объяснение для человека: по ним видно, что именно насторожило систему. Само решение принимает модель, обученная на {m.clips} размеченных записях.</p>
          </div>
        </section>

        <section className="sec" id="app">
          <div className="sechead">
            <div className="num">02 — Приложение</div>
            <div><h2>Одна программа для Windows. Настройка занимает несколько минут</h2>
              <p>Никаких серверов и командной строки. Скачали файл, запустили, подключили камеру и Telegram.</p></div>
          </div>
          <div className="appgrid">
            <figure className="shot">
              <img src="/app-live.jpg" alt="Окно программы SchoolGuard: трансляция камеры со скелетами людей, шкала риска и сигналы" width="800" height="500" />
              <figcaption>Экран «Наблюдение»: скелеты поверх видео, шкала риска и порог тревоги для каждой камеры.</figcaption>
            </figure>
            <div>
              <ol className="setup">
                <li><div><h3>Скачайте и запустите</h3><p>Один файл SchoolGuard.exe. Установка не нужна, нейросеть уже внутри. Работает на процессоре, с видеокартой — быстрее.</p></div></li>
                <li><div><h3>Подключите камеры</h3><p>Выберите производителя, введите IP-адрес, логин и пароль — ссылку на поток программа составит сама. Каждая камера получает номер.</p></div></li>
                <li><div><h3>Привяжите Telegram</h3><p>Наведите телефон на QR-код и нажмите «Старт» в боте. Или отправьте боту шесть цифр. Вводить идентификаторы чата не нужно.</p></div></li>
                <li><div><h3>Получайте записи</h3><p>При тревоге приходит видео: пять секунд до события и пять после. В подписи — номер камеры, дата и время.</p></div></li>
              </ol>
              <div className="tg" aria-label="Пример сообщения в Telegram">
                <div className="msg">
                  <div className="vid" style={{ backgroundImage: "url(/app-alert.jpg)" }} />
                  <div className="txt">{`⚠️ Возможный конфликт

📷 Камера № 2 — Коридор, 2 этаж
📅 Дата: 11.11.2026
🕒 Время: 13:45:07
📈 Риск: 0.81 (порог ${m.thresholds.balanced.toFixed(2)})
Признаки: удары и резкие движения, плотный контакт`}</div>
                </div>
                <div className="kb"><span>✅ Подтвердить</span><span>❌ Ложная тревога</span></div>
              </div>
            </div>
          </div>
        </section>

        <section className="sec" id="accuracy">
          <div className="sechead">
            <div className="num">03 — Точность</div>
            <div><h2>Что система умеет, а что нет — в цифрах</h2>
              <p>Проверка на {bal.n} записях, которые не участвовали в обучении. Записи одного исходного видео никогда не попадают одновременно в обучение и проверку.</p></div>
          </div>
          <div className="cols2">
            <div className="tablewrap">
              <table className="data">
                <caption>Три режима чувствительности</caption>
                <thead><tr><th>Чувствительность</th><th>Порог</th><th>Замечено драк</th><th>Ложных тревог</th></tr></thead>
                <tbody>
                  {MODES.map(([k, name]) => (
                    <tr key={k} className={k === "balanced" ? "main" : ""}>
                      <td>{name}</td><td className="n">{m.thresholds[k].toFixed(2)}</td>
                      <td className="n">{pct(m.clip_test[k].all.recall)} из 100</td><td className="n">{pct(m.clip_test[k].all.fpr)} из 100</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small">«Ложных тревог» — доля спокойных записей, на которых система всё же подняла тревогу. Пороги подбирались на отдельной части данных, не на проверочной.</p>
            </div>
            <div className="tablewrap">
              <table className="data">
                <caption>По типам видео, средняя чувствительность</caption>
                <thead><tr><th>Источник</th><th>Записей</th><th>Замечено</th><th>Ложных</th><th>AUC</th></tr></thead>
                <tbody>
                  {Object.keys(SOURCES).filter((s) => m.clip_test.balanced[s]).map((s) => {
                    const r = m.clip_test.balanced[s];
                    return <tr key={s}><td>{SOURCES[s]}</td><td className="n">{r.n}</td><td className="n">{pct(r.recall)}%</td><td className="n">{pct(r.fpr)}%</td><td className="n">{r.roc_auc.toFixed(2)}</td></tr>;
                  })}
                  <tr className="main"><td>Все вместе</td><td className="n">{bal.n}</td><td className="n">{pct(bal.recall)}%</td><td className="n">{pct(bal.fpr)}%</td><td className="n">{m.clip_test_auc.toFixed(2)}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="indent" style={{ marginTop: 28 }}>
            <ul className="plain">
              <li>Система видит физический конфликт: удары, захваты, падения, окружение. Словесную травлю и бойкот по видео не распознать.</li>
              <li>Спорт, шумные игры и объятия иногда похожи на драку. Поэтому тревога — это просьба посмотреть запись, а не вывод.</li>
              <li>Чем дальше и хуже камера, тем больше ошибок. Порог стоит подбирать под каждую камеру: это одна настройка в программе.</li>
              <li>Данные для обучения — открытые наборы видео драк, не съёмка в школах. До проверки в реальной школе цифры выше — оценка, а не гарантия.</li>
            </ul>
          </div>
        </section>

        <section className="sec" id="privacy">
          <div className="sechead">
            <div className="num">04 — Приватность</div>
            <div><h2>Система следит за движениями, а не за людьми</h2></div>
          </div>
          <div className="cols2 indent">
            <ul className="plain">
              <li>Нет распознавания лиц и личностей: у людей в кадре только временные номера.</li>
              <li>Головы закрываются пикселями в трансляции, в записях и в Telegram.</li>
              <li>Видео обрабатывается на компьютере школы и никуда не отправляется, кроме коротких записей тревог.</li>
            </ul>
            <ul className="plain">
              <li>Записи хранятся ограниченный срок (по умолчанию 30 дней) и удаляются сами.</li>
              <li>Система никого не наказывает и не выносит решений: она предупреждает взрослого.</li>
              <li>Внедрение в школе требует информирования родителей и соблюдения Закона РК «О персональных данных и их защите».</li>
            </ul>
          </div>
        </section>

        <div className="dl">
          <div><h2>Попробуйте на своём компьютере</h2>
            <p>В программе есть демонстрационная запись: работу можно увидеть за минуту, без камер. Windows 10 или 11, 64 бита.</p></div>
          <a className="btn" href={DOWNLOAD}>Скачать SchoolGuard.exe</a>
        </div>

        <footer>
          <span>SchoolGuard · научный проект школьника, конкурс «Дарын»</span>
          <span>Данные: Fight Detection Surv (MIT), RLVS, NTU CCTV-Fights — только для исследований</span>
          <span><a href={REPO}>GitHub</a></span>
        </footer>
      </div>
    </>
  );
}
