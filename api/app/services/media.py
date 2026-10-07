"""Images on disk. Uploads are decoded and re-encoded (drops EXIF/GPS and any
payload hidden in the file); PWA icons and splash screens are generated per tenant."""
import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from ..config import get_settings

Image.MAX_IMAGE_PIXELS = 40_000_000

# (width, height, device-width, device-height, pixel-ratio) of common iPhone screens
SPLASH_SIZES = [
    (750, 1334, 375, 667, 2),
    (1125, 2436, 375, 812, 3),
    (828, 1792, 414, 896, 2),
    (1242, 2688, 414, 896, 3),
    (1170, 2532, 390, 844, 3),
    (1284, 2778, 428, 926, 3),
    (1179, 2556, 393, 852, 3),
    (1290, 2796, 430, 932, 3),
    (1206, 2622, 402, 874, 3),
    (1320, 2868, 440, 956, 3),
]


class ImageError(ValueError):
    pass


def media_root() -> Path:
    root = get_settings().media_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_path(rel: str) -> Path:
    root = media_root().resolve()
    full = (root / rel).resolve()
    if root not in full.parents:
        raise ImageError("bad path")
    return full


def process_image(data: bytes, *, max_side: int, keep_alpha: bool = False) -> tuple[bytes, str]:
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise ImageError("file_too_large")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img = ImageOps.exif_transpose(img)
    except Exception as exc:
        raise ImageError("not_an_image") from exc
    if fmt not in {"JPEG", "PNG", "WEBP"}:
        raise ImageError("unsupported_format")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    if keep_alpha and ("A" in img.getbands() or img.mode == "P"):
        img.convert("RGBA").save(out, "PNG", optimize=True)
        return out.getvalue(), "png"
    img.convert("RGB").save(out, "JPEG", quality=84, optimize=True, progressive=True)
    return out.getvalue(), "jpg"


def store(slug: str, folder: str, data: bytes, ext: str) -> str:
    name = f"{hashlib.sha256(data).hexdigest()[:12] if folder == 'config' else uuid.uuid4().hex[:12]}.{ext}"
    rel = f"{slug}/{folder}/{name}"
    full = safe_path(rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    return rel


def store_upload(slug: str, data: bytes, *, kind: str) -> str:
    """kind: logo | hero | photo"""
    side = {"logo": 512, "hero": 1800, "photo": 1600}[kind]
    processed, ext = process_image(data, max_side=side, keep_alpha=(kind == "logo"))
    return store(slug, "uploads", processed, ext)


def _hex_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _mark(size: int, name: str, accent: str, logo: Image.Image | None, padding: float) -> Image.Image:
    """Square icon: the logo (or the first letter) centred on a tile. A logo with transparency (often light,
    white or gold lettering) sits on a dark tile, since the brand colour may hide it."""
    see_through = logo is not None and logo.mode == "RGBA" and logo.getchannel("A").getextrema()[0] < 250
    tile = Image.new("RGB", (size, size), (17, 17, 17) if see_through else _hex_rgb(accent))
    inner = int(size * (1 - padding * 2))
    if logo is not None:
        mark = logo.copy()
        mark.thumbnail((inner, inner))
        tile.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2), mark if mark.mode == "RGBA" else None)
        return tile
    draw = ImageDraw.Draw(tile)
    letter = (name.strip()[:1] or "S").upper()
    font = _font(int(inner * 0.8))
    box = draw.textbbox((0, 0), letter, font=font)
    draw.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), letter, font=font, fill="white")
    return tile


def _badge(size: int, name: str, logo: Image.Image | None) -> Image.Image:
    """Android status-bar icon: only the alpha channel is shown, so a white silhouette on transparency."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = int(size * 0.84)
    mask = None
    if logo is not None:
        alpha = logo.getchannel("A")
        see_through = sum(alpha.histogram()[:128]) / (alpha.width * alpha.height)
        if see_through < 0.05:  # opaque logo: the emblem is whatever differs from the corner (background) colour
            rgb = logo.convert("RGB")
            diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))).convert("L")
            alpha = diff.point(lambda v: 255 if v > 48 else 0)
        box = alpha.getbbox()
        if box and (box[2] - box[0]) * (box[3] - box[1]) < alpha.width * alpha.height * 0.98:
            mask = alpha.crop(box)
    if mask is None:  # no usable logo: the first letter of the name
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        letter = (name.strip()[:1] or "S").upper()
        font = _font(int(inner * 0.9))
        box = draw.textbbox((0, 0), letter, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), letter, font=font, fill=255)
        mask = mask.crop(mask.getbbox() or (0, 0, size, size))
    scale = inner / max(mask.size)
    mask = mask.resize((max(1, round(mask.width * scale)), max(1, round(mask.height * scale))), Image.LANCZOS)
    white = Image.new("RGBA", mask.size, (255, 255, 255, 255))
    white.putalpha(mask)
    img.paste(white, ((size - mask.width) // 2, (size - mask.height) // 2), white)
    return img


def build_badge(slug: str, name: str, logo_rel: str | None) -> str:
    logo = None
    if logo_rel:
        try:
            logo = Image.open(safe_path(logo_rel)).convert("RGBA")
        except Exception:
            logo = None
    rel = f"{slug}/pwa/badge-96.png"
    full = safe_path(rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    _badge(96, name, logo).save(full, "PNG", optimize=True)
    return rel


def build_pwa_assets(slug: str, name: str, accent: str, logo_rel: str | None) -> dict:
    """Icons, apple-touch-icon and iOS splash screens. Returns their media paths."""
    logo = None
    if logo_rel:
        try:
            logo = Image.open(safe_path(logo_rel)).convert("RGBA")
        except Exception:
            logo = None
    base = f"{slug}/pwa"
    out: dict = {"startup": []}

    def save(rel: str, img: Image.Image) -> str:
        full = safe_path(rel)
        full.parent.mkdir(parents=True, exist_ok=True)
        img.save(full, "PNG", optimize=True)
        return rel

    out["icon192"] = save(f"{base}/icon-192.png", _mark(192, name, accent, logo, 0.16))
    out["icon512"] = save(f"{base}/icon-512.png", _mark(512, name, accent, logo, 0.16))
    out["maskable512"] = save(f"{base}/maskable-512.png", _mark(512, name, accent, logo, 0.28))
    out["appleTouch"] = save(f"{base}/apple-touch-icon.png", _mark(180, name, accent, logo, 0.16))
    out["badge"] = build_badge(slug, name, logo_rel)
    for w, h, dw, dh, ratio in SPLASH_SIZES:
        img = Image.new("RGB", (w, h), (0, 0, 0))
        icon = _mark(int(min(w, h) * 0.28), name, accent, logo, 0.16)
        img.paste(icon, ((w - icon.width) // 2, (h - icon.height) // 2 - int(h * 0.04)))
        d = ImageDraw.Draw(img)
        font = _font(int(w * 0.055))
        box = d.textbbox((0, 0), name, font=font)
        d.text(((w - (box[2] - box[0])) / 2, h // 2 + icon.height // 2 + int(h * 0.02)), name, font=font, fill="white")
        rel = save(f"{base}/splash-{w}x{h}.png", img)
        out["startup"].append({"url": rel, "dw": dw, "dh": dh, "ratio": ratio})
    return out
