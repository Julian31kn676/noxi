"""Собирает картинки для оформления репозитория: баннер, превью для ссылок и гифки.

    python tools/make_media.py [видео_прогулки.mp4] [видео_взмаха.mov]

Результат — в папке media/."""
import os
import random
import subprocess
import sys

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "media")
POSES = os.path.join(BASE, "assets", "poses")
PINK, CYAN, GREEN, BG1, BG2 = (255, 34, 96), (0, 240, 255), (40, 255, 150), (10, 6, 18), (34, 8, 26)
FONTS = r"C:\Windows\Fonts"


def font(names, size):
    for n in names:
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def background(w, h):
    img = Image.new("RGB", (w, h), BG1)
    d = ImageDraw.Draw(img)
    for y in range(h):  # вертикальный градиент
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(BG1[i] + (BG2[i] - BG1[i]) * t) for i in range(3)))
    rnd = random.Random(7)
    for _ in range(60):  # осколки-«глитчи» на фоне
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        d.rectangle([x, y, x + rnd.randint(20, 160), y + rnd.randint(1, 4)],
                    fill=rnd.choice([(60, 10, 40), (20, 40, 60), (20, 60, 40)]))
    return img


def scanlines(img, alpha=40):
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for y in range(0, img.size[1], 3):
        d.line([(0, y), (img.size[0], y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), over)


def glitch_text(canvas, xy, text, fnt, color=PINK, split=6, slices=3, seed=3):
    """Текст с RGB-сдвигом и горизонтальными «разрывами», как у самой Капри."""
    rnd = random.Random(seed)
    w = int(canvas.size[0])
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for dx, col in ((-split, (255, 0, 70, 170)), (split, CYAN + (170,)), (0, color + (255,))):
        d.text((xy[0] + dx, xy[1]), text, font=fnt, fill=col)
    box = layer.getbbox()
    if box:
        for _ in range(slices):  # сдвинутые полосы
            y = rnd.randint(box[1], box[3] - 6)
            hgt = rnd.randint(3, 7)
            band = layer.crop((0, y, w, y + hgt))
            layer.paste((0, 0, 0, 0), (0, y, w, y + hgt))
            layer.paste(band, (rnd.choice((-1, 1)) * rnd.randint(6, 14), y), band)
    canvas.alpha_composite(layer)


def pose(name, height):
    img = Image.open(os.path.join(POSES, name)).convert("RGBA")
    img = img.crop(img.getbbox())
    img.thumbnail((height * 2, height), Image.LANCZOS)
    return img


def with_split(img, shift=8):
    """Поза с розово-голубой тенью по бокам (как в глитч-эффекте окна)."""
    w, h = img.size
    out = Image.new("RGBA", (w + shift * 2, h), (0, 0, 0, 0))
    alpha = img.split()[3]
    for dx, col in ((0, (255, 0, 70, 150)), (shift * 2, CYAN + (150,))):
        tint = Image.new("RGBA", img.size, col)
        tint.putalpha(ImageChops.multiply(alpha, Image.new("L", img.size, col[3])))
        out.alpha_composite(tint, (dx, 0))
    out.alpha_composite(img, (shift, 0))
    return out


def card(w, h, title_size, path):
    img = background(w, h).convert("RGBA")
    big = font(["impact.ttf", "arialbd.ttf"], title_size)
    mono = font(["consolab.ttf", "consola.ttf", "courbd.ttf"], max(18, title_size // 6))
    mono_s = font(["consola.ttf", "cour.ttf"], max(16, title_size // 8))
    # позы справа
    p1 = with_split(pose("capri_roam.png", int(h * 0.92)))
    img.alpha_composite(p1, (w - p1.size[0] - int(w * 0.02), int(h * 0.04)))
    left = int(w * 0.06)
    top = int(h * 0.18)
    glitch_text(img, (left, top), "CAPRI", big, split=max(3, title_size // 40))
    d = ImageDraw.Draw(img)
    y = top + int(title_size * 1.15)
    d.text((left, y), "голосовой ассистент для Windows", font=mono, fill=(255, 210, 225))
    y += int(title_size * 0.30)
    d.text((left, y), "// офлайн · бесплатно · по-русски", font=mono_s, fill=GREEN)
    # «окно» HUD как у Капри
    hy = y + int(title_size * 0.32)
    hw, hh = int(w * 0.38), int(title_size * 0.42)
    d.polygon([(left, hy), (left + hw - 16, hy), (left + hw, hy + 16), (left + hw, hy + hh),
               (left + 16, hy + hh), (left, hy + hh - 16)], fill=(10, 4, 16, 230), outline=PINK)
    d.text((left + 14, hy + 10), "// CAPRI :: ОНЛАЙН", font=mono_s, fill=GREEN)
    d.text((left + 14, hy + 10 + int(title_size * 0.14)), "Слушаю…", font=mono_s, fill=(255, 200, 220))
    img = scanlines(img)
    img.convert("RGB").save(path, optimize=True)
    print("сохранено:", path, img.size)


def ffmpeg(*args):
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", *args], check=True)


def walk_gif(src, dst):
    """Прогулка: вырезаем правую нижнюю часть экрана, где идёт Капри, 12 кадров/с, палитра для качества."""
    # трава на фоне всё время шевелится и плохо сжимается: меньше кадров, цветов и без дизеринга
    vf = ("trim=start=1:end=14,crop=iw*0.47:ih*0.47:iw*0.53:ih*0.49,fps=10,scale=440:-1:flags=lanczos,"
          "split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle")
    ffmpeg("-i", src, "-vf", vf, "-loop", "0", dst)
    print("сохранено:", dst, f"{os.path.getsize(dst) / 2**20:.1f} МБ")


def wave_gif(dst):
    """Взмах рукой — из уже вырезанных кадров анимации (с прозрачным фоном), на тёмной подложке."""
    folder = os.path.join(BASE, "assets", "anim", "capri")
    frames = []
    for f in sorted(os.listdir(folder)):
        fr = Image.open(os.path.join(folder, f)).convert("RGBA")
        bg = Image.new("RGBA", (fr.size[0] + 40, fr.size[1] + 20), BG1 + (255,))
        bg.alpha_composite(fr, (20, 10))
        frames.append(bg.convert("P", palette=Image.ADAPTIVE, colors=64))
    frames[0].save(dst, save_all=True, append_images=frames[1:], duration=42, loop=0, optimize=True)
    print("сохранено:", dst, f"{os.path.getsize(dst) / 2**20:.1f} МБ")


def main():
    os.makedirs(OUT, exist_ok=True)
    card(1280, 420, 150, os.path.join(OUT, "banner.png"))
    card(1280, 640, 190, os.path.join(OUT, "social_preview.png"))
    if len(sys.argv) > 1:
        walk_gif(sys.argv[1], os.path.join(OUT, "walk.gif"))
    wave_gif(os.path.join(OUT, "wave.gif"))


if __name__ == "__main__":
    main()
