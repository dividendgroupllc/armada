"""
pdf_engine/base_generator.py
============================
Markaziy PDF generator engine.
Barcha report PDF lar shu modulni ishlatadi.

Qo'shilishi mumkin bo'lgan reportlar:
  - P&L Statement        → pdf_engine/pl_pdf.py
  - Balance Sheet        → report/balance_sheet/balance_sheet_pdf.py
  - Kontragent Hisobot   → report/kontragent_hisobot/kontragent_pdf.py
  - Cash Flow            → ...
"""

import os
from collections import defaultdict

import pdfplumber
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import Color

# ── Try Frappe import (graceful fallback for standalone testing) ──────────────
try:
    import frappe
    _FRAPPE = True
except ImportError:
    _FRAPPE = False

# ─── PATHS ───────────────────────────────────────────────────────────────────
_ENGINE_DIR  = os.path.dirname(os.path.abspath(__file__))
FONT_DIR     = os.path.join(_ENGINE_DIR, "fonts")
TEMPLATE_DIR = os.path.join(_ENGINE_DIR, "templates")

# ─── PAGE DEFAULTS ───────────────────────────────────────────────────────────
PAGE_W  = 842.0    # A3 landscape / A3 portrait width  (pt)
PAGE_H  = 1191.0   # A3 portrait height (pt)

# ─── FONT REGISTRATION (singleton) ───────────────────────────────────────────
_fonts_registered = False

def register_fonts():
    """Register Rubik font family + system Arial. Call once before any canvas operation."""
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont("Rubik",
        os.path.join(FONT_DIR, "RubikFull-regular.ttf")))
    pdfmetrics.registerFont(TTFont("Rubik-Bold",
        os.path.join(FONT_DIR, "RubikFull-bold.ttf")))
    pdfmetrics.registerFont(TTFont("Rubik-Italic",
        os.path.join(FONT_DIR, "RubikFull-italic.ttf")))
    # Arial — strelka (↓↑) va boshqa maxsus belgilar uchun
    _arial = "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"
    _arial_bold = "/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf"
    if os.path.exists(_arial):
        pdfmetrics.registerFont(TTFont("Arial", _arial))
    if os.path.exists(_arial_bold):
        pdfmetrics.registerFont(TTFont("Arial-Bold", _arial_bold))
    _fonts_registered = True

# Maps embedded subset name → registered ReportLab font name
FONT_MAP = {
    "MUFUZY+Rubik-Regular": "Rubik",
    "MUFUZY+Rubik-Bold":    "Rubik-Bold",
    "MUFUZY+Rubik-Italic":  "Rubik-Italic",
    "MUFUZY+ArialMT":       "Arial",
    "ArialMT":              "Arial",
    "Arial-BoldMT":         "Arial-Bold",
}

def resolve_font(fontname: str) -> str:
    """Return registered RL font name for an embedded PDF font name."""
    return FONT_MAP.get(fontname, "Rubik")

# ─── COLOR HELPERS ───────────────────────────────────────────────────────────
def to_color(c):
    """Convert pdfplumber color tuple/scalar to ReportLab Color."""
    if c is None:
        return Color(0, 0, 0)
    if isinstance(c, (int, float)):
        return Color(c, c, c)
    return Color(*c[:3])

# Common colors (reuse across reports)
C_WHITE      = Color(1.0,    1.0,    1.0   )
C_BLACK      = Color(0.0,    0.0,    0.0   )
C_RED        = Color(1.0,    0.0,    0.0   )
C_DARK_GRAY  = Color(0.2627, 0.2627, 0.2627)
C_MED_GRAY   = Color(0.6,    0.6,    0.6   )
C_ORANGE_RED = Color(0.8,    0.2549, 0.1451)   # section headers
C_YELLOW     = Color(1.0,    0.8510, 0.4   )   # Операционные расходы
C_PEACH      = Color(1.0,    0.9490, 0.8   )   # gross/net subtotals
C_LIGHT_GRAY = Color(0.9529, 0.9529, 0.9529)   # regular data rows

# ─── COORDINATE CONVERSION ───────────────────────────────────────────────────
def rl_y(pdf_bottom: float, page_h: float = PAGE_H) -> float:
    """
    Convert pdfplumber coordinate (top-of-page = 0, y increases down)
    to ReportLab coordinate (bottom-of-page = 0, y increases up).

    Pass char['bottom'] for text baseline positioning.
    Pass rect['bottom'] + rect['height'] for rect y.
    """
    return page_h - pdf_bottom

# ─── TEMPLATE CLONER ─────────────────────────────────────────────────────────
def clone_backgrounds(cv, template_pdf_path: str, page_h: float = PAGE_H):
    """
    Draw only the filled rectangles (background colors) from a template PDF.
    Text is intentionally skipped — each report module draws its own data.

    Returns pdfplumber page object so caller can inspect original layout.
    """
    with pdfplumber.open(template_pdf_path) as pdf:
        page = pdf.pages[0]

        # White base
        cv.setFillColor(C_WHITE)
        cv.rect(0, 0, PAGE_W, page_h, stroke=0, fill=1)

        # All filled rects in source order (preserves z-layering)
        for r in page.rects:
            if not r.get("fill"):
                continue
            clr = r.get("non_stroking_color")
            if clr is None:
                continue
            cv.setFillColor(to_color(clr))
            y = rl_y(r["bottom"], page_h)
            cv.rect(r["x0"], y, r["width"], r["height"], stroke=0, fill=1)

        return page

def clone_full(cv, template_pdf_path: str, page_h: float = PAGE_H):
    """
    Full pixel clone: backgrounds + all original text.
    Use when you want an exact static copy with no data injection.
    """
    page = clone_backgrounds(cv, template_pdf_path, page_h)

    for ch in page.chars:
        txt = ch.get("text", "")
        if not txt.strip():
            continue
        font_rl  = resolve_font(ch.get("fontname", ""))
        size     = ch.get("size", 6.88)
        clr      = to_color(ch.get("non_stroking_color", (0, 0, 0)))
        baseline = rl_y(ch["bottom"], page_h)
        cv.setFont(font_rl, size)
        cv.setFillColor(clr)
        cv.drawString(ch["x0"], baseline, txt)

# ─── TEXT DRAWING HELPERS ────────────────────────────────────────────────────
def draw_text(cv, x: float, baseline_y: float, text: str,
              font: str = "Rubik", size: float = 6.88,
              color: Color = None, align: str = "left"):
    """Draw text at (x, baseline_y) in ReportLab coordinates."""
    cv.setFont(font, size)
    cv.setFillColor(color or C_BLACK)
    if align == "right":
        cv.drawRightString(x, baseline_y, text)
    elif align == "center":
        cv.drawCentredString(x, baseline_y, text)
    else:
        cv.drawString(x, baseline_y, text)

def draw_value(cv, x: float, pdf_bottom: float, value,
               fmt: str = "num", font: str = "Rubik",
               size: float = 6.88, base_color: Color = None,
               page_h: float = PAGE_H):
    """
    Format and right-align a single numeric value.

    fmt options:
      "num"      → 1,234.56   (negative → red)
      "dollar"   → $1,234.56
      "pct"      → 36%
      "pct_dec"  → 26.95%
      "plain"    → 3.00
    """
    baseline = rl_y(pdf_bottom, page_h)

    if fmt == "dollar":
        text = f"${value:,.2f}"
    elif fmt == "pct":
        text = f"{int(value)}%"
    elif fmt == "pct_dec":
        text = f"{value:.2f}%"
    elif fmt == "plain":
        text = f"{value:.2f}"
    else:
        text = f"{value:,.2f}"

    clr = C_RED if (isinstance(value, (int, float)) and value < 0) else (base_color or C_BLACK)
    cv.setFont(font, size)
    cv.setFillColor(clr)
    cv.drawRightString(x, baseline, text)

# ─── ROW HELPERS ─────────────────────────────────────────────────────────────
def get_row_style(page, pdf_top: float, tolerance: float = 4.0) -> dict:
    """
    From pdfplumber page, find font + color of first char near pdf_top.
    Returns dict: {font, size, color, baseline_y}
    """
    chars = page.chars
    matches = [ch for ch in chars if abs(ch["top"] - pdf_top) <= tolerance
               and ch.get("text","").strip()]
    if not matches:
        return {"font": "Rubik", "size": 6.88,
                "color": C_BLACK, "baseline_y": rl_y(pdf_top + 8)}
    ch = matches[0]
    return {
        "font":       resolve_font(ch.get("fontname","")),
        "size":       ch.get("size", 6.88),
        "color":      to_color(ch.get("non_stroking_color", (0,0,0))),
        "baseline_y": rl_y(ch["bottom"]),
    }

def draw_data_row(cv, page, pdf_top: float, col_x: list, values: list,
                  fmt: str = "num", color_override: Color = None,
                  font_override: str = None):
    """
    Draw 8 (or N) right-aligned values for a data row.

    col_x   : list of right-edge x coordinates, one per column
    values  : list of numeric values matching col_x
    fmt     : format string (see draw_value)
    """
    style = get_row_style(page, pdf_top)
    font  = font_override or style["font"]
    size  = style["size"]
    clr   = color_override or style["color"]
    by    = style["baseline_y"]

    for v, cx in zip(values, col_x):
        draw_value(cv, cx, 0, v, fmt=fmt, font=font, size=size,
                   base_color=clr, page_h=PAGE_H)
        # Override baseline with extracted value (draw_value uses pdf_bottom=0 trick)
        # Re-draw correctly:
        if fmt == "dollar":
            text = f"${v:,.2f}"
        elif fmt == "pct":
            text = f"{int(v)}%"
        elif fmt == "pct_dec":
            text = f"{v:.2f}%"
        elif fmt == "plain":
            text = f"{v:.2f}"
        else:
            text = f"{v:,.2f}"
        actual_clr = C_RED if (isinstance(v,(int,float)) and v < 0) else clr
        cv.setFont(font, size)
        cv.setFillColor(actual_clr)
        cv.drawRightString(cx, by, text)

# ─── PATH HELPERS ─────────────────────────────────────────────────────────────
def get_template(name: str) -> str:
    """Return absolute path to a template PDF."""
    return os.path.join(TEMPLATE_DIR, name)

def get_output_path(filename: str) -> str:
    """Return site-level private/files path (Frappe) or cwd fallback."""
    if _FRAPPE:
        return frappe.get_site_path("private", "files", filename)
    return os.path.join(os.getcwd(), filename)

def new_canvas(output_path: str,
               page_w: float = PAGE_W,
               page_h: float = PAGE_H):
    """Create and return a ReportLab canvas."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    return rl_canvas.Canvas(output_path, pagesize=(page_w, page_h))
