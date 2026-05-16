"""
armada_custom_app/pdf_engine/balance_pdf.py
Balance Sheet PDF generator — dynamic header + data rows + ratios

CHANGES vs original:
  1. _fmt()         — whole numbers (no decimals)
  2. ROW_MAP        — 8 new section-subtotal entries added
  3. _derive()      — 8 subtotals calculated + returned
  4. generate()     — BOLD_SECTION_KEYS: section totals rendered bold
"""
import os
from collections import defaultdict

import pdfplumber

from armada.armada_custom_app.pdf_engine.base_generator import (
    register_fonts, get_template, get_output_path,
    new_canvas, resolve_font, to_color, rl_y,
    C_BLACK, C_WHITE, C_RED, C_DARK_GRAY, PAGE_W, PAGE_H,
)

# ─── LAYOUT CONSTANTS ────────────────────────────────────────────────────────
TEMPLATE_COL_X = [296.1, 371.0, 445.9, 520.8, 595.6, 670.5, 745.4, 820.3]
LABEL_CUTOFF   = 250.0

HEADER_TOPS = {46, 59, 70, 81}
SKIP_TOPS   = {46}

# Section-subtotal rows → rendered bold (label font stays as-is, only value font)
BOLD_SECTION_KEYS = {
    "zapasy", "dengi", "debit_zadolzh", "prochie_akt",
    "kapital", "dolgosrochnye", "kratkosrochnye", "kred_zadolzh",
}

# ─── MONTH NAMES ─────────────────────────────────────────────────────────────
MONTH_RU = {
    "jan": "Январь",  "feb": "Февраль", "mar": "Март",
    "apr": "Апрель",  "may": "Май",     "jun": "Июнь",
    "jul": "Июль",    "aug": "Август",  "sep": "Сентябрь",
    "oct": "Октябрь", "nov": "Ноябрь",  "dec": "Декабрь",
}

def _parse_col(ck):
    parts = ck.split("_")
    mon  = MONTH_RU.get(parts[0].lower(), parts[0].capitalize())
    year = parts[1] if len(parts) > 1 else ""
    return mon, year


# ─── ROW MAP ─────────────────────────────────────────────────────────────────
ROW_MAP = {
    # ── Активы ──────────────────────────────────────────────────────────────
    127: ("oborudovanie",           "num"),

    # [NEW] Запасы subtotal (top=149, data_chars=0 in template)
    149: ("zapasy",                 "num"),
    160: ("syryo",                  "num"),
    171: ("polufabrikat",           "num"),
    182: ("gotoviy_produkt",        "num"),

    # [NEW] Денежные средства subtotal (top=205, second "Денежные средства" at 216 is sub-label)
    205: ("dengi",                  "num"),
    227: ("nalichnye",              "num"),
    238: ("klik",                   "num"),
    249: ("perechislenie",          "num"),
    260: ("empty_cash_row",         "num"),
    272: ("raznitsa_peremesh",      "num"),

    # [NEW] Дебиторская задолж-ть subtotal (top=294)
    294: ("debit_zadolzh",          "num"),
    305: ("zadolzh_klientov",       "num"),
    316: ("avansy_postavshikam",    "num"),
    327: ("zadolzh_sotrudnikov",    "num"),
    339: ("dolg_debitorov",         "num"),

    # [NEW] Прочие активы subtotal (top=361)
    361: ("prochie_akt",            "num"),
    372: ("rashody_budushih",       "num"),
    383: ("prochee_aktiv",          "num"),

    # Итого Активы
    394: ("itogo_aktiv",            "num"),

    # ── Пассивы ─────────────────────────────────────────────────────────────
    # [NEW] Капитал subtotal (top=428)
    428: ("kapital",                "num"),
    439: ("ustavniy_kapital",       "num"),
    462: ("pribyl_proshlyh",        "num"),
    473: ("pribyl_tekushih",        "num"),
    484: ("dividendy",              "num"),
    495: ("investiciya",            "num"),

    # [NEW] Долгосрочные subtotal (top=540)
    540: ("dolgosrochnye",          "num"),
    551: ("kredit_bank_dolg",       "num"),
    562: ("zaymy_dolg",             "num"),
    573: ("lizing",                 "num"),

    # [NEW] Краткосрочные subtotal (top=596)
    596: ("kratkosrochnye",         "num"),
    607: ("kredit_bank_kratk",      "num"),
    618: ("zaymy_kratk",            "num"),

    # [NEW] Кредиторская задолженность subtotal (top=640)
    640: ("kred_zadolzh",           "num"),
    651: ("zadolzh_postavshik",     "num"),
    663: ("zadolzh_sotrudnikam",    "num"),
    674: ("zadolzh_nalog",          "num"),
    685: ("avansy_klientov",        "num"),
    696: ("zarplata_sobstvennika",  "num"),
    707: ("prochie_obyaz",          "num"),

    # Итого Пассивы
    718: ("itogo_passiv",           "num"),
    # Разница
    741: ("raznitsa",               "num"),
}

CUTOFF_TOP = 755


# ─── FORMATTER ───────────────────────────────────────────────────────────────
def _fmt(v, style):
    """Whole numbers only — no decimals."""
    rv = int(round(v)) if isinstance(v, (int, float)) else 0
    if style == "dollar":
        return f"(${abs(rv):,})" if rv < 0 else f"${rv:,}"
    if style in ("pct", "pct_dec"):
        return f"{rv}%"
    if style == "plain":
        return f"{rv:,}"
    # "num" — accounting parentheses for negatives
    return f"({abs(rv):,})" if rv < 0 else f"{rv:,}"


# ─── DERIVED CALCULATIONS ────────────────────────────────────────────────────
def _derive(data, n):
    def g(k):
        return (data.get(k, []) + [0.0] * n)[:n]

    # Raw account balances
    oborudovanie      = g("oborudovanie")
    syryo             = g("syryo")
    polufabrikat      = g("polufabrikat")
    gotoviy_produkt   = g("gotoviy_produkt")
    nalichnye         = g("nalichnye")
    klik              = g("klik")
    perechislenie     = g("perechislenie")
    raznitsa_peremesh = g("raznitsa_peremesh")
    zadolzh_klientov  = g("zadolzh_klientov")
    avansy_postav     = g("avansy_postavshikam")
    zadolzh_sotr      = g("zadolzh_sotrudnikov")
    dolg_debit        = g("dolg_debitorov")
    rashody_bud       = g("rashody_budushih")
    prochee_aktiv     = g("prochee_aktiv")

    ustavniy          = g("ustavniy_kapital")
    pribyl_pr         = g("pribyl_proshlyh")
    pribyl_tek        = g("pribyl_tekushih")
    dividendy         = g("dividendy")
    investiciya       = g("investiciya")
    kredit_dolg       = g("kredit_bank_dolg")
    zaymy_dolg        = g("zaymy_dolg")
    lizing            = g("lizing")
    kredit_kratk      = g("kredit_bank_kratk")
    zaymy_kratk       = g("zaymy_kratk")
    zadolzh_postav    = g("zadolzh_postavshik")
    zadolzh_sotr_p    = g("zadolzh_sotrudnikam")
    zadolzh_nalog     = g("zadolzh_nalog")
    avansy_kl         = g("avansy_klientov")
    zarplata_sobst    = g("zarplata_sobstvennika")
    prochie_obyaz     = g("prochie_obyaz")

    # Retained Earnings roll-forward
    opening_re = pribyl_pr[0] if pribyl_pr else 0.0
    pribyl_pr_rolled = [opening_re]
    for i in range(1, n):
        pribyl_pr_rolled.append(
            pribyl_pr_rolled[-1] + pribyl_tek[i - 1] + dividendy[i - 1]
        )

    # ── Section subtotals (8 new) ────────────────────────────────────────────
    zapasy = [
        syryo[i] + polufabrikat[i] + gotoviy_produkt[i]
        for i in range(n)
    ]
    dengi = [
        nalichnye[i] + klik[i] + perechislenie[i] + raznitsa_peremesh[i]
        for i in range(n)
    ]
    debit_zadolzh = [
        zadolzh_klientov[i] + avansy_postav[i] + zadolzh_sotr[i] + dolg_debit[i]
        for i in range(n)
    ]
    prochie_akt = [
        rashody_bud[i] + prochee_aktiv[i]
        for i in range(n)
    ]
    kapital = [
        ustavniy[i] + pribyl_pr_rolled[i] + pribyl_tek[i] + dividendy[i] + investiciya[i]
        for i in range(n)
    ]
    dolgosrochnye = [
        kredit_dolg[i] + zaymy_dolg[i] + lizing[i]
        for i in range(n)
    ]
    kratkosrochnye = [
        kredit_kratk[i] + zaymy_kratk[i]
        for i in range(n)
    ]
    kred_zadolzh = [
        zadolzh_postav[i] + zadolzh_sotr_p[i] + zadolzh_nalog[i]
        + avansy_kl[i] + zarplata_sobst[i] + prochie_obyaz[i]
        for i in range(n)
    ]

    # ── Grand totals ─────────────────────────────────────────────────────────
    erp_total_asset  = g("_erp_total_asset")
    erp_total_credit = g("_erp_total_credit")
    has_erp_totals   = any(v != 0 for v in erp_total_asset)

    if has_erp_totals:
        itogo_aktiv  = erp_total_asset
        itogo_passiv = erp_total_credit
    else:
        itogo_aktiv = [
            oborudovanie[i] + zapasy[i] + dengi[i] + debit_zadolzh[i] + prochie_akt[i]
            for i in range(n)
        ]
        itogo_passiv = [
            kapital[i] + dolgosrochnye[i] + kratkosrochnye[i] + kred_zadolzh[i]
            for i in range(n)
        ]

    raznitsa = [itogo_passiv[i] - itogo_aktiv[i] for i in range(n)]

    return {
        # Section subtotals — NEW
        "zapasy":          zapasy,
        "dengi":           dengi,
        "debit_zadolzh":   debit_zadolzh,
        "prochie_akt":     prochie_akt,
        "kapital":         kapital,
        "dolgosrochnye":   dolgosrochnye,
        "kratkosrochnye":  kratkosrochnye,
        "kred_zadolzh":    kred_zadolzh,
        # Existing
        "empty_cash_row":  [0.0] * n,
        "pribyl_proshlyh": pribyl_pr_rolled,
        "itogo_aktiv":     itogo_aktiv,
        "itogo_passiv":    itogo_passiv,
        "raznitsa":        raznitsa,
    }


# ─── DYNAMIC HEADER ──────────────────────────────────────────────────────────
def _draw_dynamic_header(cv, col_keys, col_x, page):
    chars_by_top = defaultdict(list)
    for ch in page.chars:
        chars_by_top[round(ch["top"])].append(ch)

    year_chars = chars_by_top.get(70, [])
    if year_chars:
        ref = [c for c in year_chars if c.get("text", "").strip() and c["x0"] < LABEL_CUTOFF]
        if ref:
            size = ref[0].get("size", 6.90)
            font = resolve_font(ref[0].get("fontname", ""))
            clr  = to_color(ref[0].get("non_stroking_color", (1, 1, 1)))
            by   = rl_y(ref[0]["bottom"])
            for i, cx in enumerate(col_x):
                if i < len(col_keys):
                    _, year = _parse_col(col_keys[i])
                    cv.setFont(font, size)
                    cv.setFillColor(clr)
                    cv.drawRightString(cx, by, year)

    month_chars = chars_by_top.get(81, [])
    if month_chars:
        ref = [c for c in month_chars if c.get("text", "").strip() and c["x0"] < LABEL_CUTOFF]
        if ref:
            size = ref[0].get("size", 6.90)
            font = resolve_font(ref[0].get("fontname", ""))
            clr  = to_color(ref[0].get("non_stroking_color", (1, 1, 1)))
            by   = rl_y(ref[0]["bottom"])
            for i, cx in enumerate(col_x):
                if i < len(col_keys):
                    mon, _ = _parse_col(col_keys[i])
                    cv.setFont(font, size)
                    cv.setFillColor(clr)
                    cv.drawRightString(cx, by, mon)

    num_chars = chars_by_top.get(59, [])
    if num_chars:
        ref = [c for c in num_chars if c.get("text", "").strip()]
        if ref:
            size = ref[0].get("size", 6.90)
            font = resolve_font(ref[0].get("fontname", ""))
            clr  = to_color(ref[0].get("non_stroking_color", (0.26, 0.26, 0.26)))
            by   = rl_y(ref[0]["bottom"])
            for i, cx in enumerate(col_x):
                cv.setFont(font, size)
                cv.setFillColor(clr)
                cv.drawRightString(cx, by, str(i + 1))


# ─── MAIN GENERATOR ──────────────────────────────────────────────────────────
def generate(data: dict,
             output_filename: str = "balance_report.pdf",
             col_keys: list = None) -> str:

    register_fonts()
    template = get_template("balance_sheet_template.pdf")
    output   = get_output_path(output_filename)
    n_cols   = min(len(col_keys), 8) if col_keys else 8
    col_x    = TEMPLATE_COL_X[:n_cols]
    col_keys = (col_keys or [])[:n_cols]

    full = {**data, **_derive(data, n_cols)}

    cv = new_canvas(output)

    with pdfplumber.open(template) as pdf:
        page = pdf.pages[0]

        # 1. Backgrounds
        cv.setFillColor(C_WHITE)
        cv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        for r in page.rects:
            if not r.get("fill"):
                continue
            if r["top"] >= CUTOFF_TOP:
                continue
            clr = r.get("non_stroking_color")
            if clr is None:
                continue
            cv.setFillColor(to_color(clr))
            cv.rect(r["x0"], rl_y(r["bottom"]), r["width"], r["height"],
                    stroke=0, fill=1)

        # 2. Group chars by row
        rows = defaultdict(list)
        for ch in page.chars:
            rows[round(ch["top"])].append(ch)

        # 3. Draw rows
        for top_key in sorted(rows.keys()):
            if top_key >= CUTOFF_TOP:
                continue
            chars = rows[top_key]

            if top_key in SKIP_TOPS:
                continue

            if top_key in HEADER_TOPS:
                for ch in chars:
                    txt = ch.get("text", "")
                    if not txt.strip() or ch["x0"] >= LABEL_CUTOFF:
                        continue
                    cv.setFont(resolve_font(ch.get("fontname", "")),
                               ch.get("size", 6.90))
                    cv.setFillColor(to_color(ch.get("non_stroking_color", (0, 0, 0))))
                    cv.drawString(ch["x0"], rl_y(ch["bottom"]), txt)
                continue

            # Labels (always draw)
            for ch in chars:
                txt = ch.get("text", "")
                if not txt.strip() or ch["x0"] >= LABEL_CUTOFF:
                    continue
                cv.setFont(resolve_font(ch.get("fontname", "")),
                           ch.get("size", 6.90))
                cv.setFillColor(to_color(ch.get("non_stroking_color", (0, 0, 0))))
                cv.drawString(ch["x0"], rl_y(ch["bottom"]), txt)

            # ROW_MAP match
            best_key, best_dist = None, 9999
            for rk in ROW_MAP:
                d = abs(top_key - rk)
                if d < best_dist:
                    best_dist, best_key = d, rk

            if best_dist <= 6 and best_key is not None:
                data_key, fmt_style = ROW_MAP[best_key]
                values = full.get(data_key)
                if not values:
                    values = [0.0] * n_cols

                ref = [ch for ch in chars
                       if ch["x0"] < LABEL_CUTOFF and ch.get("text", "").strip()]
                if not ref:
                    ref = chars

                font     = resolve_font(ref[0].get("fontname", "")) if ref else "Rubik"
                size     = ref[0].get("size", 6.90) if ref else 6.90
                base_clr = to_color(
                    ref[0].get("non_stroking_color", (0, 0, 0))
                ) if ref else C_BLACK

                # Styling overrides
                if data_key == "raznitsa":
                    base_clr = C_RED
                    font     = "Rubik-Bold"
                elif data_key in ("itogo_aktiv", "itogo_passiv"):
                    font = "Rubik-Bold"
                elif data_key in BOLD_SECTION_KEYS:
                    font = "Rubik-Bold"

                # Baseline: prefer data-zone chars, fall back to label chars
                dchs = [ch for ch in chars
                        if ch["x0"] >= LABEL_CUTOFF and ch.get("text", "").strip()]
                by = (rl_y(dchs[0]["bottom"]) if dchs
                      else (rl_y(ref[0]["bottom"]) if ref else 0))

                for i, cx in enumerate(col_x):
                    v   = values[i] if i < len(values) else 0.0
                    txt = _fmt(v, fmt_style)
                    clr = (C_RED if (isinstance(v, (int, float)) and v < 0)
                           else base_clr)
                    cv.setFont(font, size)
                    cv.setFillColor(clr)
                    cv.drawRightString(cx, by, txt)
            else:
                # No ROW_MAP match — clone original data-zone text
                for ch in chars:
                    txt = ch.get("text", "")
                    if not txt.strip() or ch["x0"] < LABEL_CUTOFF:
                        continue
                    cv.setFont(resolve_font(ch.get("fontname", "")),
                               ch.get("size", 6.90))
                    cv.setFillColor(to_color(ch.get("non_stroking_color", (0, 0, 0))))
                    cv.drawString(ch["x0"], rl_y(ch["bottom"]), txt)

        # 4. Dynamic header
        _draw_dynamic_header(cv, col_keys, col_x, page)

    cv.save()
    return output
