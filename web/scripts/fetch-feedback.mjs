// Скачивает отметки школ из хранилища Vercel Blob в data/feedback/*.json (их читает tools/train.py).
//   cd web && node scripts/fetch-feedback.mjs            скачать всё
//   cd web && node scripts/fetch-feedback.mjs --delete aaaaaaaaaaa1 ...   удалить записи по id (например, проверочные)
// Ключ доступа берётся из web/.env.local (BLOB_READ_WRITE_TOKEN); в репозиторий этот файл не попадает.
import { del, get, list } from "@vercel/blob";
import fs from "node:fs";
import path from "node:path";

const env = fs.readFileSync(new URL("../.env.local", import.meta.url), "utf8");
const token = (env.match(/^BLOB_READ_WRITE_TOKEN="?([^"\r\n]+)"?/m) || [])[1];
if (!token) throw new Error("В web/.env.local нет BLOB_READ_WRITE_TOKEN (выполните: npx vercel env pull .env.local)");
const out = path.resolve(new URL("../../data/feedback", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
fs.mkdirSync(out, { recursive: true });

const blobs = [];
let cursor;
do {
  const r = await list({ prefix: "feedback/", token, cursor, limit: 1000 });
  blobs.push(...r.blobs);
  cursor = r.hasMore ? r.cursor : undefined;
} while (cursor);

const drop = process.argv.includes("--delete") ? new Set(process.argv.slice(process.argv.indexOf("--delete") + 1)) : null;
if (drop) {
  const urls = blobs.filter((b) => drop.has(path.basename(b.pathname, ".json"))).map((b) => b.url);
  if (urls.length) await del(urls, { token });
  for (const id of drop) fs.rmSync(path.join(out, id + ".json"), { force: true });
  console.log(`удалено записей: ${urls.length}`);
} else {
  let n = 0, yes = 0;
  for (const b of blobs) {
    const r = await get(b.pathname, { access: "private", token });
    const text = await new Response(r.stream).text();
    const rec = JSON.parse(text);
    fs.writeFileSync(path.join(out, rec.id + ".json"), text);
    n += 1; yes += rec.verdict === "confirmed" ? 1 : 0;
  }
  console.log(`скачано отметок: ${n} (подтверждено ${yes}, ложных ${n - yes}) -> ${out}`);
}
