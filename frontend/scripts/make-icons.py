"""Erzeugt die PWA-Icons fuer die Karaoke-App (schlichtes Mikrofon-Symbol,
rein geometrisch gezeichnet - kein Font/Emoji noetig, damit deterministisch).

Selten noetig (nur wenn sich Farbe/Form aendern soll). Ausfuehren mit einem
Python, das Pillow hat, z.B. das konverter-venv:

    ..\..\konverter\venv\Scripts\python.exe scripts\make-icons.py

Schreibt direkt nach frontend/public/. Die erzeugten PNGs sind eingecheckt,
das Skript muss also nicht Teil des Builds sein."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(r"C:\ki\karaoke-app\frontend\public")
BG = (5, 150, 105)        # emerald-600, passt zur Nuxt-UI-Primary
FG = (255, 255, 255)


def rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def draw_mic(size: int, pad_frac: float) -> Image.Image:
    """pad_frac: Anteil Rand, den das Symbol freilaesst (fuer maskable groesser)."""
    S = size * 4  # supersampling
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Hintergrund (voll, Icon-Radius uebernimmt der Browser/das Manifest-Purpose)
    rounded(d, (0, 0, S, S), int(S * 0.22), BG)

    # sanftes Top-Highlight
    hi = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    rounded(hd, (0, 0, S, int(S * 0.5)), int(S * 0.22), (255, 255, 255, 28))
    img.alpha_composite(hi)
    d = ImageDraw.Draw(img)

    # Zeichenflaeche fuers Mikrofon
    inset = S * pad_frac
    cx = S / 2
    # Kapsel (Mikrofonkopf)
    cap_w = (S - 2 * inset) * 0.42
    cap_top = inset + (S - 2 * inset) * 0.06
    cap_h = (S - 2 * inset) * 0.52
    d.rounded_rectangle(
        (cx - cap_w / 2, cap_top, cx + cx - (cx - cap_w / 2), cap_top + cap_h),
        radius=cap_w / 2, fill=FG,
    )
    # Buegel (U-Form) um die Kapsel
    arc_r = cap_w * 0.95
    arc_box = (cx - arc_r, cap_top + cap_h * 0.32, cx + arc_r, cap_top + cap_h * 0.32 + 2 * arc_r)
    lw = max(2, int(S * 0.028))
    d.arc(arc_box, start=20, end=160, fill=FG, width=lw)
    # Staender
    stem_top = arc_box[3] - arc_r * 0.15
    stem_bot = stem_top + (S - 2 * inset) * 0.16
    d.line((cx, stem_top, cx, stem_bot), fill=FG, width=lw)
    # Fuss
    foot_w = cap_w * 0.9
    d.line((cx - foot_w / 2, stem_bot, cx + foot_w / 2, stem_bot), fill=FG, width=lw)

    return img.resize((size, size), Image.LANCZOS)


def save(name: str, img: Image.Image):
    (OUT / name).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(OUT / name)
    print(f"  {name:<28} {(OUT / name).stat().st_size:>6} B")


def main():
    save("pwa-192x192.png", draw_mic(192, 0.16))
    save("pwa-512x512.png", draw_mic(512, 0.16))
    save("maskable-512x512.png", draw_mic(512, 0.26))  # Symbol in der Safe-Zone
    save("apple-touch-icon-180x180.png", draw_mic(180, 0.14))
    save("favicon-64x64.png", draw_mic(64, 0.14))
    print("fertig ->", OUT)


if __name__ == "__main__":
    main()
