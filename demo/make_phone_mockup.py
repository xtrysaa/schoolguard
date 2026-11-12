"""Рисует мокап экрана iPhone с пуш-уведомлением Telegram. Картинки собраны кодом, не нейросетью.

    python demo/make_phone_mockup.py
Результат:
    demo/phone_mockup.png       — текст из рекламного сценария (постановка, 96 %)
    web/public/phone-ru.png, phone-kk.png, phone-en.png — то, что на самом деле присылает программа, на трёх языках;
                                  эти картинки стоят на сайте
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
F = "C:/Windows/Fonts/"
W, H = 900, 1760
PROMO = "Внимание! Зафиксировано проявление агрессии/буллинга. Локация: Коридор Б, 2 этаж. Вероятность: 96%. Требуется немедленное вмешательство."
# текст уведомления повторяет подпись, которую программа отправляет на выбранном языке (schoolguard/i18n.py)
REAL = {
    "ru": ("Возможный конфликт. Камера № 2 — Коридор, 2 этаж. 12.11.2026, 13:45:07. Риск 0.81 (порог 0.65). Видео · 0:10", "четверг, 12 ноября", "сейчас"),
    "kk": ("Ықтимал жанжал. № 2 камера — Дәліз, 2-қабат. 12.11.2026, 13:45:07. Тәуекел 0.81 (шек 0.65). Бейне · 0:10", "бейсенбі, 12 қараша", "қазір"),
    "en": ("Possible conflict. Camera 2 — Corridor, 2nd floor. 12.11.2026, 13:45:07. Risk 0.81 (threshold 0.65). Video · 0:10", "Thursday, 12 November", "now"),
}


def font(size, bold=False):
    return ImageFont.truetype(F + ("seguisb.ttf" if bold else "segoeui.ttf"), size)


def wrap(d, text, f, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur); cur = word
    return lines + [cur]


def render(text: str, out: Path, transparent: bool, date: str = "четверг, 12 ноября", now: str = "сейчас"):
    S = 2                                                              # рисуем крупнее и уменьшаем: гладкие края
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0) if transparent else (7, 9, 12, 255))
    d = ImageDraw.Draw(img)
    R = lambda *v: [x * S for x in v]
    # корпус: тёмная рамка, чуть светлее кант
    d.rounded_rectangle(R(40, 30, W - 40, H - 30), 150 * S, fill=(52, 56, 62, 255))
    d.rounded_rectangle(R(48, 38, W - 48, H - 38), 143 * S, fill=(10, 11, 13, 255))
    sx0, sy0, sx1, sy1 = 70, 60, W - 70, H - 60
    screen = Image.new("RGBA", ((sx1 - sx0) * S, (sy1 - sy0) * S))
    sd = ImageDraw.Draw(screen)
    for i in range(screen.height):                                      # фон экрана блокировки: глубокий сине-зелёный
        k = i / screen.height
        sd.line([(0, i), (screen.width, i)], fill=(int(6 + 12 * k), int(34 - 14 * k), int(44 - 12 * k), 255))
    glow = Image.new("RGBA", screen.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-200 * S, 900 * S, 700 * S, 1700 * S], fill=(53, 214, 232, 70))
    screen = Image.alpha_composite(screen, glow.filter(ImageFilter.GaussianBlur(160 * S)))
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, screen.width, screen.height], 122 * S, fill=255)
    img.paste(screen, (sx0 * S, sy0 * S), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(R(W // 2 - 125, 92, W // 2 + 125, 162), 35 * S, fill=(0, 0, 0, 255))        # Dynamic Island
    d.text((W // 2 * S, 250 * S), date, font=font(40 * S), fill=(230, 238, 240, 255), anchor="mm")
    d.text((W // 2 * S, 390 * S), "13:45", font=font(190 * S, True), fill=(255, 255, 255, 255), anchor="mm")

    # уведомление
    nx0, nx1, ny0 = sx0 + 26, sx1 - 26, 590
    body_f, title_f, small_f = font(33 * S), font(34 * S, True), font(27 * S)
    lines = wrap(d, text, body_f, (nx1 - nx0 - 150) * S)
    ny1 = ny0 + 84 + len(lines) * 44 + 30
    card = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(R(nx0, ny0, nx1, ny1), 46 * S, fill=(236, 240, 242, 232))
    img = Image.alpha_composite(img, card)
    d = ImageDraw.Draw(img)
    ix, iy = nx0 + 26, ny0 + (ny1 - ny0) // 2 - 42
    d.rounded_rectangle(R(ix, iy, ix + 84, iy + 84), 20 * S, fill=(42, 171, 238, 255))                # значок Telegram
    d.polygon([((ix + 18) * S, (iy + 42) * S), ((ix + 66) * S, (iy + 22) * S), ((ix + 54) * S, (iy + 66) * S), ((ix + 40) * S, (iy + 52) * S)],
              fill=(255, 255, 255, 255))
    tx = nx0 + 132
    d.text((tx * S, (ny0 + 22) * S), "SchoolGuard", font=title_f, fill=(17, 20, 24, 255))
    d.text(((nx1 - 28) * S, (ny0 + 28) * S), now, font=small_f, fill=(107, 116, 128, 255), anchor="ra")
    y = ny0 + 70
    for ln in lines:
        d.text((tx * S, y * S), ln, font=body_f, fill=(30, 36, 43, 255))
        y += 44
    d.rounded_rectangle(R(W // 2 - 150, sy1 - 40, W // 2 + 150, sy1 - 28), 6 * S, fill=(255, 255, 255, 255))   # полоска «домой»
    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((W, H), Image.LANCZOS).save(out)
    print(out)


if __name__ == "__main__":
    render(PROMO, HERE / "phone_mockup.png", transparent=False)
    for lang, (text, date, now) in REAL.items():
        render(text, HERE.parent / "web" / "public" / f"phone-{lang}.png", True, date, now)
