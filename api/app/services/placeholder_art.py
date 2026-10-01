"""Generated stand-in artwork for samples: real photos always replace these."""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .media import _font, _hex_rgb


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def scene(w: int, h: int, accent: str, variant: int = 0, label: str = "", kind: str = "car") -> Image.Image:
    if kind == "beauty":
        return _beauty_scene(w, h, accent, variant)
    rnd = random.Random(variant * 7919 + w)
    acc = _hex_rgb(accent)
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    top, bottom = _mix((6, 6, 8), acc, 0.10 + 0.04 * (variant % 3)), (0, 0, 0)
    for y in range(h):
        px.line([(0, y), (w, y)], fill=_mix(top, bottom, y / h))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = int(w * (0.35 + 0.3 * rnd.random())), int(h * 0.62)
    gd.ellipse([cx - w * 0.45, cy - h * 0.28, cx + w * 0.45, cy + h * 0.28], fill=_mix((0, 0, 0), acc, 0.55))
    img = Image.blend(img, Image.composite(glow.filter(ImageFilter.GaussianBlur(w // 7)), img, Image.new("L", (w, h), 255)), 0.55)
    d = ImageDraw.Draw(img)
    # floor line and a low car silhouette
    floor = int(h * 0.74)
    d.rectangle([0, floor, w, h], fill=(4, 4, 6))
    u = w / 100
    x0 = w * (0.16 + 0.05 * (variant % 2))
    body = [(x0, floor - 6 * u), (x0 + 4 * u, floor - 13 * u), (x0 + 22 * u, floor - 16 * u), (x0 + 34 * u, floor - 26 * u),
            (x0 + 52 * u, floor - 27 * u), (x0 + 64 * u, floor - 17 * u), (x0 + 72 * u, floor - 14 * u), (x0 + 74 * u, floor - 6 * u)]
    d.polygon(body, fill=(14, 14, 18), outline=_mix((30, 30, 36), acc, 0.5))
    d.line([(x0 + 22 * u, floor - 16 * u), (x0 + 72 * u, floor - 14 * u)], fill=_mix((60, 60, 70), acc, 0.7), width=max(2, int(u * 0.5)))
    for wx in (x0 + 16 * u, x0 + 58 * u):
        r = 7 * u
        d.ellipse([wx - r, floor - 6 * u - r, wx + r, floor - 6 * u + r], fill=(2, 2, 3), outline=(50, 50, 58), width=max(2, int(u * 0.5)))
        d.ellipse([wx - r * 0.45, floor - 6 * u - r * 0.45, wx + r * 0.45, floor - 6 * u + r * 0.45], fill=(24, 24, 28))
    for i in range(12):  # light streaks
        y = floor - int(h * 0.05) + i * 3
        a = int(60 * math.exp(-i / 4))
        d.line([(0, y), (w, y)], fill=(a, a, a + 6))
    if label:
        d.text((w * 0.05, h * 0.06), label, font=_font(int(w * 0.03)), fill=(255, 255, 255))
    return img


def _beauty_scene(w: int, h: int, accent: str, variant: int) -> Image.Image:
    """Soft abstract stand-in (no car): blurred colour blobs on a dark ground."""
    rnd = random.Random(variant * 104729 + w)
    acc = _hex_rgb(accent)
    img = Image.new("RGB", (w, h), (10, 8, 12))
    d = ImageDraw.Draw(img)
    for i in range(5):
        r = int(min(w, h) * (0.22 + 0.2 * rnd.random()))
        cx, cy = int(w * rnd.random()), int(h * rnd.random())
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_mix((18, 14, 22), acc, 0.25 + 0.45 * rnd.random()))
    return img.filter(ImageFilter.GaussianBlur(min(w, h) // 6))


def portrait(accent: str, letter: str, size: int = 720, variant: int = 0) -> Image.Image:
    img = _beauty_scene(size, size, accent, variant + 50)
    d = ImageDraw.Draw(img)
    font = _font(int(size * 0.42))
    box = d.textbbox((0, 0), letter, font=font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), letter, font=font, fill=(255, 255, 255))
    return img


def logo(accent: str, letter: str, size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 4, fill=(8, 8, 10, 255), outline=_hex_rgb(accent) + (255,), width=size // 32)
    font = _font(int(size * 0.55))
    box = d.textbbox((0, 0), letter, font=font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), letter, font=font, fill=_hex_rgb(accent) + (255,))
    return img


def write_set(root: Path, accent: str, letter: str, works: int = 4, kind: str = "car", people: list[str] | None = None) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    scene(1600, 1100, accent, 0, kind=kind).save(root / "hero.jpg", quality=86)
    for i, key in enumerate(people or []):
        portrait(accent, key[:1].upper(), variant=i).save(root / f"{key}.jpg", quality=86)
    logo(accent, letter).save(root / "logo.png")
    names = ["hero.jpg", "logo.png"]
    for i in range(1, works + 1):
        scene(1200, 900, accent, i, kind=kind).save(root / f"work-{i}.jpg", quality=84)
        names.append(f"work-{i}.jpg")
    return names
