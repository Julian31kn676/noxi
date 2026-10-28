"""Превращает видео в набор PNG-кадров с прозрачным фоном для анимаций Капри.

    python tools/convert_anim.py <видео> <имя> <фон: black|green> [ширина] [высота]

Кадры сохраняются в assets/anim/<имя>/. Фон вырезается только там, где он соединён с краем кадра,
поэтому тёмные и зелёные детали внутри фигуры остаются на месте."""
import os
import shutil
import sys

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bg_candidates(rgb, kind):
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    if kind == "black":
        return np.maximum(np.maximum(r, g), b) <= 10
    if kind == "white":
        return np.minimum(np.minimum(r, g), b) >= 225
    # зелёный хромакей
    return (g > 140) & (g > r + 80) & (g > b + 60)


def key_frame(rgb, kind):
    h, w, _ = rgb.shape
    cand = Image.fromarray(np.where(bg_candidates(rgb, kind), 255, 0).astype(np.uint8))
    draw = ImageDraw.Draw(cand)
    step = 8
    border = ([(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)] +
              [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)])
    for xy in border:
        if cand.getpixel(xy) == 255:
            ImageDraw.floodfill(cand, xy, 128, thresh=0)
    bg = np.array(cand) == 128
    if kind == "white":
        # белый фон бывает и в замкнутых просветах (между рукой и телом, у шеи), а в самой
        # фигуре белого нет — поэтому убираем весь белый, а не только соединённый с краем
        bg |= np.array(cand) > 0
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.6))  # убрать кайму
    img = Image.fromarray(rgb).convert("RGBA")
    img.putalpha(alpha)
    return img


def main():
    src, name, kind = sys.argv[1], sys.argv[2], sys.argv[3]
    box_w = int(sys.argv[4]) if len(sys.argv) > 4 else 340
    box_h = int(sys.argv[5]) if len(sys.argv) > 5 else 380

    reader = imageio_ffmpeg.read_frames(src)
    meta = next(reader)
    w, h = meta["size"]
    scale = 700 / max(w, h)  # кеим на промежуточном размере — быстро и достаточно точно
    frames = []
    for raw in reader:
        im = Image.frombytes("RGB", (w, h), raw).resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        frames.append(key_frame(np.array(im), kind))

    # общая рамка по всем кадрам, чтобы фигура не прыгала
    box = None
    for f in frames:
        bb = f.getbbox()
        if bb:
            box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]),
                                          max(box[2], bb[2]), max(box[3], bb[3]))
    out = os.path.join(BASE, "assets", "anim", name)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for i, f in enumerate(frames):
        f = f.crop(box)
        f.thumbnail((box_w, box_h), Image.LANCZOS)
        f.save(os.path.join(out, f"{i:04d}.png"), optimize=True)
    print(f"{name}: {len(frames)} кадров, {meta.get('fps')} fps, размер {frames and f.size} -> {out}")


if __name__ == "__main__":
    main()
