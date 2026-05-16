"""
armada_custom_app/pdf_engine/pl_pdf.py
P&L PDF generator — dynamic header + data rows
"""
import os
import pdfplumber
from collections import defaultdict
from reportlab.lib.colors import Color

from armada.armada_custom_app.pdf_engine.base_generator import (
    register_fonts, get_template, get_output_path,
    new_canvas, resolve_font, to_color, rl_y,
    C_BLACK, C_WHITE, C_RED,
)

TEMPLATE_COL_X = [290.0, 364.6, 439.2, 513.7, 588.3, 662.9, 737.5, 812.0]
LABEL_CUTOFF   = 217.0

HEADER_TOPS = {36, 37, 47, 59}

MONTH_RU = {
    "jan":"Январь",  "feb":"Февраль", "mar":"Март",
    "apr":"Апрель",  "may":"Май",     "jun":"Июнь",
    "jul":"Июль",    "aug":"Август",  "sep":"Сентябрь",
    "oct":"Октябрь", "nov":"Ноябрь",  "dec":"Декабрь",
}

# Bu row larda manfiy qiymat qizil fonda ko'rinmaydi —
# shuning uchun qora rangda chizamiz
RED_BG_ROWS = {"marginal", "gross_profit", "op_profit", "net_profit"}


def _parse_col(ck):
    """'oct_2025' -> ('Октябрь', '2025')"""
    parts = ck.split("_")
    mon   = MONTH_RU.get(parts[0].lower(), parts[0].capitalize())
    year  = parts[1] if len(parts) > 1 else ""
    return mon, year

ROW_MAP = {
    70:  ("revenue_mult",  "plain"),
    82:  ("revenue",       "num"),
    109: ("cogs",          "num"),
    120: ("loss_adj",      "num"),
    136: ("marginal",      "dollar"),
    148: ("margin_pct",    "pct"),
    164: ("other_income",  "num"),
    192: ("komunal",       "num"),
    203: ("produkt",       "num"),
    214: ("arenda_cex",    "num"),
    225: ("proizvodstvo",  "num"),
    236: ("nalog_imush",   "num"),
    247: ("zarplata_pr",   "num"),
    281: ("total_manuf",   "num"),
    307: ("gross_profit",  "dollar"),
    319: ("gross_pct",     "pct_dec"),
    358: ("uslugi",        "num"),
    369: ("prochie",       "num"),
    380: ("komis_bank",    "num"),
    391: ("podoh_nalog",   "num"),
    402: ("inps",          "num"),
    413: ("sp",            "num"),
    425: ("kredit",        "num"),
    436: ("alimenty",      "num"),
    447: ("mobil_bank",    "num"),
    458: ("nds",           "num"),
    469: ("utilizaciya",   "num"),
    480: ("kantc",         "num"),
    491: ("komis_klik",    "num"),
    502: ("transport",     "num"),
    513: ("obed",          "num"),
    524: ("ofis",          "num"),
    536: ("arenda_dukon",  "num"),
    547: ("prazdnik",      "num"),
    558: ("obuchenie",     "num"),
    569: ("skidka",        "num"),
    580: ("bonus",         "num"),
    591: ("remont",        "num"),
    602: ("fin_uslugi",    "num"),
    613: ("kurs_razn",     "num"),
    624: ("svyaz",         "num"),
    636: ("zarplata_adm",  "num"),
    647: ("yandex",        "num"),
    658: ("stoyanka",      "num"),
    691: ("total_admin",   "num"),
    719: ("arenda_reklam", "num"),
    730: ("khairiya",      "num"),
    741: ("reklama",       "num"),
    774: ("total_commer",  "num"),
    811: ("op_profit",     "dollar"),
    823: ("op_pct",        "pct"),
    839: ("nalog_prib",    "num"),
    855: ("net_profit",    "dollar"),
    867: ("net_pct",       "pct"),
    901: ("s_balansa",     "num"),
    912: ("raznitsa",      "dollar"),
    934: ("zapas",         "num"),
    945: ("kassa",         "num"),
    956: ("kassa_pct",     "pct"),
}


# ─────────────────────────────────────────────────────────────────────────────
# CHANGED: _fmt() — all numeric styles now output whole numbers (no decimals)
# Logic (_derive, generate, ROW_MAP) is untouched.
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(v, style):
    """Format a value for display — whole numbers only."""
    rv = int(round(v)) if isinstance(v, (int, float)) else 0

    if style == "dollar":
        # Negative → ($123,456)  |  Positive → $123,456
        return f"${rv:,}"

    if style == "pct":
        return f"{rv}%"

    if style == "pct_dec":
        # Was: f"{v:.2f}%"  →  Now: whole percent
        return f"{rv}%"

    if style == "plain":
        # Was: f"{v:.2f}"  →  Now: comma-separated integer
        return f"{rv:,}"

    # "num" — pl_pdf uses color (red) for negatives, not parentheses
    # Was: f"{v:,.2f}"
    return f"{rv:,}"


def _derive(data, n):
    def g(k): return (data.get(k, []) + [0.0]*n)[:n]

    rev   = g("revenue")
    cogs  = g("cogs")
    ladj  = g("loss_adj")
    other = g("other_income")

    mfg = ["komunal","produkt","arenda_cex","proizvodstvo","nalog_imush","zarplata_pr"]
    adm = ["uslugi","prochie","komis_bank","podoh_nalog","inps","sp",
           "kredit","alimenty","mobil_bank","nds","utilizaciya","kantc",
           "komis_klik","transport","obed","ofis","arenda_dukon",
           "prazdnik","obuchenie","skidka","bonus","remont","fin_uslugi",
           "kurs_razn","svyaz","zarplata_adm","yandex","stoyanka"]
    com = ["arenda_reklam","khairiya","reklama"]

    def vsum(*keys):
        r = [0.0]*n
        for k in keys:
            for i, v in enumerate(g(k)):
                r[i] += v
        return r

    marginal    = [rev[i] - cogs[i] - ladj[i] for i in range(n)]
    total_manuf = vsum(*mfg)
    gross       = [marginal[i] + other[i] - total_manuf[i] for i in range(n)]
    total_admin = vsum(*adm)
    total_comm  = vsum(*com)
    op_profit   = [gross[i] - total_admin[i] - total_comm[i] for i in range(n)]
    nalog       = g("nalog_prib")
    net_profit  = [op_profit[i] - nalog[i] for i in range(n)]

    def pct(num, den):
        return [round(num[i]/den[i]*100, 2) if den[i] else 0.0 for i in range(n)]

    return {
        "marginal":     marginal,
        "margin_pct":   pct(marginal, rev),
        "total_manuf":  total_manuf,
        "gross_profit": gross,
        "gross_pct":    pct(gross, rev),
        "total_admin":  total_admin,
        "total_commer": total_comm,
        "op_profit":    op_profit,
        "op_pct":       pct(op_profit, rev),
        "net_profit":   net_profit,
        "net_pct":      pct(net_profit, rev),
        "s_balansa":    net_profit,
        "raznitsa":     [0.0]*n,
        "revenue_mult": [0.0]*n,
    }


def _is_red_rect(clr):
    """pdfplumber rect non_stroking_color qizilmi tekshiradi."""
    if isinstance(clr, (int, float)):
        return False
    if isinstance(clr, (list, tuple)) and len(clr) >= 3:
        return clr[0] > 0.5 and clr[1] < 0.35 and clr[2] < 0.35
    return False


def _value_color(v, data_key, base_clr):
    """
    Qiymat rangi:
    - RED_BG_ROWS da manfiy → C_BLACK (qizil fonda ko'rinadi)
    - Boshqa row larda manfiy → C_RED
    - Musbat → base_clr
    """
    if not isinstance(v, (int, float)):
        return base_clr
    if v < 0:
        if data_key in RED_BG_ROWS:
            return C_BLACK
        return C_RED
    return base_clr


def _draw_dynamic_header(cv, col_keys, col_x, page):
    chars_by_top = defaultdict(list)
    for ch in page.chars:
        chars_by_top[round(ch["top"])].append(ch)

    year_row_chars = chars_by_top.get(47, [])
    if year_row_chars:
        ref = [c for c in year_row_chars if c.get("text", "").strip() and c["x0"] < LABEL_CUTOFF]
        if ref:
            size = ref[0].get("size", 6.88)
            font = resolve_font(ref[0].get("fontname", ""))
            clr  = to_color(ref[0].get("non_stroking_color", (1, 1, 1)))
            by   = rl_y(ref[0]["bottom"])
            for i, cx in enumerate(col_x):
                if i < len(col_keys):
                    _, year = _parse_col(col_keys[i])
                    cv.setFont(font, size)
                    cv.setFillColor(clr)
                    cv.drawRightString(cx, by, year)

    month_row_chars = chars_by_top.get(59, [])
    if month_row_chars:
        ref = [c for c in month_row_chars if c.get("text", "").strip() and c["x0"] < LABEL_CUTOFF]
        if ref:
            size = ref[0].get("size", 6.88)
            font = resolve_font(ref[0].get("fontname", ""))
            clr  = to_color(ref[0].get("non_stroking_color", (1, 1, 1)))
            by   = rl_y(ref[0]["bottom"])
            for i, cx in enumerate(col_x):
                if i < len(col_keys):
                    mon, _ = _parse_col(col_keys[i])
                    cv.setFont(font, size)
                    cv.setFillColor(clr)
                    cv.drawRightString(cx, by, mon)


def generate(data: dict,
             output_filename: str = "pl_report.pdf",
             col_keys: list = None) -> str:

    register_fonts()
    template = get_template("pl_statement.pdf")
    output   = get_output_path(output_filename)
    n_cols   = min(len(col_keys), 8) if col_keys else 8
    col_x    = TEMPLATE_COL_X[:n_cols]
    col_keys = (col_keys or [])[:n_cols]

    full = {**data, **_derive(data, n_cols)}

    cv = new_canvas(output)

    with pdfplumber.open(template) as pdf:
        page = pdf.pages[0]

        cv.setFillColor(C_WHITE)
        cv.rect(0, 0, 842, 1191, stroke=0, fill=1)

        for r in page.rects:
            if not r.get("fill"):
                continue
            clr = r.get("non_stroking_color")
            if clr is None:
                continue
            if _is_red_rect(clr):
                cv.setFillColor(Color(0.85, 0.11, 0.11))
            else:
                cv.setFillColor(to_color(clr))
            cv.rect(r["x0"], rl_y(r["bottom"]), r["width"], r["height"], stroke=0, fill=1)

        rows = defaultdict(list)
        for ch in page.chars:
            rows[round(ch["top"])].append(ch)

        for top_key in sorted(rows.keys()):
            chars = rows[top_key]
            row_text = "".join(ch.get("text", "") for ch in chars)
            if "#REF" in row_text:
                continue

            if top_key in HEADER_TOPS:
                for ch in chars:
                    txt = ch.get("text", "")
                    if not txt.strip() or ch["x0"] >= LABEL_CUTOFF:
                        continue
                    cv.setFont(resolve_font(ch.get("fontname", "")), ch.get("size", 6.88))
                    cv.setFillColor(to_color(ch.get("non_stroking_color", (0, 0, 0))))
                    cv.drawString(ch["x0"], rl_y(ch["bottom"]), txt)
                continue

            for ch in chars:
                txt = ch.get("text", "")
                if not txt.strip() or ch["x0"] >= LABEL_CUTOFF:
                    continue
                cv.setFont(resolve_font(ch.get("fontname", "")), ch.get("size", 6.88))
                cv.setFillColor(to_color(ch.get("non_stroking_color", (0, 0, 0))))
                cv.drawString(ch["x0"], rl_y(ch["bottom"]), txt)

            best_key, best_dist = None, 9999
            for rk in ROW_MAP:
                d = abs(top_key - rk)
                if d < best_dist:
                    best_dist, best_key = d, rk

            if best_dist <= 6 and best_key is not None:
                data_key, fmt_style = ROW_MAP[best_key]
                values = full.get(data_key)
                if not values:
                    continue

                ref = [ch for ch in chars if ch["x0"] < LABEL_CUTOFF and ch.get("text", "").strip()]
                if not ref:
                    ref = chars
                font     = resolve_font(ref[0].get("fontname", "")) if ref else "Rubik"
                size     = ref[0].get("size", 6.88) if ref else 6.88
                base_clr = to_color(ref[0].get("non_stroking_color", (0, 0, 0))) if ref else C_BLACK

                if data_key == "raznitsa":
                    base_clr, font = C_RED, "Rubik-Bold"

                dchs = [ch for ch in chars if ch["x0"] >= LABEL_CUTOFF and ch.get("text", "").strip()]
                by   = rl_y(dchs[0]["bottom"]) if dchs else (rl_y(ref[0]["bottom"]) if ref else 0)

                for i, cx in enumerate(col_x):
                    v   = values[i] if i < len(values) else 0.0
                    txt = _fmt(v, fmt_style)
                    clr = _value_color(v, data_key, base_clr)
                    cv.setFont(font, size)
                    cv.setFillColor(clr)
                    cv.drawRightString(cx, by, txt)
            else:
                for ch in chars:
                    txt = ch.get("text", "")
                    if not txt.strip() or ch["x0"] < LABEL_CUTOFF:
                        continue
                    cv.setFont(resolve_font(ch.get("fontname", "")), ch.get("size", 6.88))
                    cv.setFillColor(to_color(ch.get("non_stroking_color", (0, 0, 0))))
                    cv.drawString(ch["x0"], rl_y(ch["bottom"]), txt)

        _draw_dynamic_header(cv, col_keys, col_x, page)

    cv.save()
    return output
