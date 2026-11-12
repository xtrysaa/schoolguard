// Приём отметок «подтверждено / ложная тревога» от программ SchoolGuard, где школа включила обмен.
// Принимаются только числа: 125 признаков движения за окно 2 с и ответ человека. Видео, кадры, названия камер,
// адреса и время события сюда не попадают; IP-адрес отправителя не сохраняется.
import { put } from "@vercel/blob";

export const runtime = "nodejs";
const N = 125;
const num = (v, lo, hi) => typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;

export async function POST(req) {
  let b;
  try {
    const text = await req.text();
    if (text.length > 12000) return Response.json({ ok: false, error: "too large" }, { status: 413 });
    b = JSON.parse(text);
  } catch {
    return Response.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const ok = b && b.v === 1 && /^[a-f0-9]{12}$/.test(b.id || "") && ["confirmed", "false_alarm"].includes(b.verdict)
    && Array.isArray(b.features) && b.features.length === N && b.features.every((x) => num(x, -1e6, 1e6))
    && num(b.peak, 0, 1) && num(b.threshold, 0, 1) && /^[\w.\-]{1,20}$/.test(b.app || "");
  if (!ok) return Response.json({ ok: false, error: "bad payload" }, { status: 400 });
  const rec = { v: 1, id: b.id, verdict: b.verdict, features: b.features, peak: b.peak, threshold: b.threshold, app: b.app };
  const day = new Date().toISOString().slice(0, 10);
  await put(`feedback/${day}/${b.id}.json`, JSON.stringify(rec), { access: "private", contentType: "application/json", addRandomSuffix: false, allowOverwrite: true });
  return Response.json({ ok: true });
}

export function GET() {
  return Response.json({ ok: true, accepts: "POST: 125 признаков окна и ответ человека, без видео" });
}
