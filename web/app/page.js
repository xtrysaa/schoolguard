import Home from "../components/Home";
import m from "../public/replay/metrics.json";

// Страница одна; тексты на трёх языках лежат в lib/i18n.js, язык выбирается переключателем в шапке.
export default function Page() {
  // в браузер передаём только те поля метрик, которые показываются на странице
  const { trees, thresholds, clip_test, clip_test_auc } = m;
  return <Home m={{ trees, thresholds, clip_test, clip_test_auc }} />;
}
