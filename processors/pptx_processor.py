"""
Slide extraction from PPTX files.

Strategy:
  1. Try LibreOffice (soffice) → PDF → pdftoppm (best fidelity).
  2. If that fails, fall back to the built-in Pillow renderer which faithfully
     reproduces the slide layout using python-pptx geometry data.
"""

import subprocess
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Output resolution for the Pillow renderer
RENDER_WIDTH = 1920
RENDER_HEIGHT = 1080

# EMU → pixel scale factor (filled in per-presentation)
_EMU_PX = None


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def convert_pptx_to_images(pptx_path: str, output_dir: str) -> list[str]:
    """Return a sorted list of PNG paths, one per slide."""
    pptx_path = Path(pptx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        images = _libreoffice_convert(pptx_path, output_dir)
        if images:
            return images
    except Exception:
        pass

    return _pillow_render(pptx_path, output_dir)


def extract_slide_texts(pptx_path: str) -> list[dict]:
    """Return [{slide_number, title, content}, …] for every slide."""
    from pptx import Presentation

    prs = Presentation(pptx_path)
    slides = []
    for idx, slide in enumerate(prs.slides, start=1):
        title = ""
        body_parts: list[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            if shape == slide.shapes.title or "title" in shape.name.lower():
                title = text
            else:
                body_parts.append(text)
        slides.append(
            {
                "slide_number": idx,
                "title": title,
                "content": " ".join(body_parts),
            }
        )
    return slides


# ─────────────────────────────────────────────
# LibreOffice path (best quality)
# ─────────────────────────────────────────────

def _libreoffice_convert(pptx_path: Path, output_dir: Path) -> list[str]:
    tmp_dir = output_dir / "_lo_tmp"
    tmp_dir.mkdir(exist_ok=True)

    result = subprocess.run(
        ["soffice", "--headless", "--norestore",
         "--convert-to", "pdf", "--outdir", str(tmp_dir), str(pptx_path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice error: {result.stderr}")

    pdfs = list(tmp_dir.glob("*.pdf"))
    if not pdfs:
        raise RuntimeError("LibreOffice produced no PDF.")
    pdf = pdfs[0]

    slides_dir = output_dir / "slides"
    slides_dir.mkdir(exist_ok=True)

    result = subprocess.run(
        ["pdftoppm", "-r", "150", "-png", str(pdf), str(slides_dir / "slide")],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm error: {result.stderr}")

    images = sorted(slides_dir.glob("slide*.png"), key=lambda p: p.name)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return [str(p) for p in images]


# ─────────────────────────────────────────────
# Pillow renderer (fallback)
# ─────────────────────────────────────────────

# Colour palette
_PALETTE = [
    ("#1e1e2e", "#7c3aed"),  # dark bg / purple accent
    ("#0f172a", "#4f46e5"),  # dark blue / indigo
    ("#1a1a2e", "#0891b2"),  # dark navy / cyan
    ("#16213e", "#059669"),  # deep blue / green
    ("#1e1b4b", "#d97706"),  # indigo bg / amber
]


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf".format("-Bold" if bold else ""),
        "/usr/share/fonts/truetype/liberation/LiberationSans{}-Regular.ttf".format(
            "-Bold" if bold else ""
        ),
        "/usr/share/fonts/truetype/freefont/FreeSans{}.ttf".format("Bold" if bold else ""),
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _pillow_render(pptx_path: Path, output_dir: Path) -> list[str]:
    from pptx import Presentation
    from pptx.util import Emu

    prs = Presentation(pptx_path)
    slide_w_emu = prs.slide_width
    slide_h_emu = prs.slide_height

    scale_x = RENDER_WIDTH / slide_w_emu
    scale_y = RENDER_HEIGHT / slide_h_emu

    slides_dir = output_dir / "slides"
    slides_dir.mkdir(exist_ok=True)

    images: list[str] = []
    n = len(prs.slides)

    for idx, slide in enumerate(prs.slides):
        bg_color, accent = _PALETTE[idx % len(_PALETTE)]
        img = Image.new("RGB", (RENDER_WIDTH, RENDER_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        # Header bar
        draw.rectangle([0, 0, RENDER_WIDTH, 10], fill=accent)

        # Slide number badge
        badge_font = _get_font(28)
        badge_text = f"{idx + 1}/{n}"
        draw.text((RENDER_WIDTH - 20, 30), badge_text, fill="#666688", font=badge_font, anchor="rm")

        # Render shapes in Z-order
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            # Shape bounding box in pixels
            left = int(shape.left * scale_x)
            top = int(shape.top * scale_y)
            width = int(shape.width * scale_x)
            height = int(shape.height * scale_y)

            is_title = shape == slide.shapes.title or "title" in shape.name.lower()
            full_text = shape.text_frame.text.strip()
            if not full_text:
                continue

            if is_title:
                font = _get_font(72, bold=True)
                draw.rectangle([left, top - 8, left + width, top + height + 8], fill="#00000040")
                lines = _wrap_text(full_text, font, width - 40, draw)
                y = top + 10
                for line in lines:
                    draw.text((left + 20, y), line, fill="#ffffff", font=font)
                    bbox = draw.textbbox((0, 0), line, font=font)
                    y += (bbox[3] - bbox[1]) + 12
                # Accent underline
                draw.rectangle([left, y + 4, left + min(width, 600), y + 10], fill=accent)
            else:
                font = _get_font(40)
                padding = 24
                lines = _wrap_text(full_text, font, width - 2 * padding, draw)
                y = top + padding
                for line in lines:
                    draw.rectangle([left + padding - 8, y - 4, left + width - padding, y + 44], fill="#00000020")
                    draw.text((left + padding, y), line, fill="#cbd5e1", font=font)
                    y += 52

        # Bottom accent bar
        draw.rectangle([0, RENDER_HEIGHT - 6, RENDER_WIDTH, RENDER_HEIGHT], fill=accent)

        out_file = slides_dir / f"slide-{idx + 1:03d}.png"
        img.save(str(out_file), "PNG")
        images.append(str(out_file))

    return images
