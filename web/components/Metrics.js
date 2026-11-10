"use client";
import { useEffect, useState } from "react";

const fmt = (v) => (typeof v === "number" ? v.toFixed(3) : v);

export default function Metrics() {
  const [m, setM] = useState(null);
  useEffect(() => {
    fetch("/replay/metrics.json").then((r) => r.json()).then(setM).catch(() => setM({}));
  }, []);
  if (!m) return <p className="note">Загрузка…</p>;
  const rows = m.metrics || [];
  if (!rows.length) return <p className="note">Метрики появятся после обучения модели.</p>;
  const cols = ["accuracy", "precision", "recall", "f1", "roc_auc", "FPR"];
  return (
    <>
      <table>
        <thead><tr><th>Модель</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r) => <tr key={r.model}><td>{r.model}</td>{cols.map((c) => <td key={c}>{fmt(r[c])}</td>)}</tr>)}</tbody>
      </table>
      {(m.metrics_by_source || []).length > 0 && (
        <>
          <p className="note" style={{ marginTop: 14 }}>По источникам данных (лучшая модель):</p>
          <table>
            <thead><tr><th>Источник</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{m.metrics_by_source.map((r) => <tr key={r.model}><td>{r.model}</td>{cols.map((c) => <td key={c}>{fmt(r[c])}</td>)}</tr>)}</tbody>
          </table>
        </>
      )}
    </>
  );
}
