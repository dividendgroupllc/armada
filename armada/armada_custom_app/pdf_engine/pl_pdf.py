"""
armada_custom_app/pdf_engine/pl_pdf.py  —  v7 FINAL

v6 dan farq: 4 yangi metrik qator PASTDAN → TEPAGA ko'chirildi.
  - Месяц (oy nomlari, top=59) qatoridan KEYIN, Выручка'dan OLDIN joylashadi
  - Buning uchun Выручка (top=67.5) va undan pastdagi BARCHA narsa
    4 qator (46.4pt) PASTGA suriladi
  - 4 yangi qator tepada chiziladi (fon + label + har oy raqamlari)

Boshqa o'zgarishlar saqlanadi:
  1. total_manuf → Bold
  2. Кредит/Алименты o'chirilgan + gap yopilgan
  3. Яндекс инстаграм (659) + Стоянка (670)
"""
import os
import pdfplumber
from collections import defaultdict
from reportlab.lib.colors import Color

from armada.armada_custom_app.pdf_engine.base_generator import (
    register_fonts, get_template, get_output_path,
    new_canvas, resolve_font, to_color, rl_y,
    C_BLACK, C_WHITE, C_RED, bg_fill_objects,
)

TEMPLATE_COL_X = [290.0, 364.6, 439.2, 513.7, 588.3, 662.9, 737.5, 812.0]
LABEL_CUTOFF   = 217.0
HEADER_TOPS    = {36, 37, 47, 59}

SKIP_TOPS = {282}   # DejaVu Bold overlay label (template) — overlap

# ── Выручка/Себестоимость bo'lim sarlavhalari OLIB TASHLANGAN ──
# Ularning o'rniga ostidagi data qatorlar (revenue, cogs) qizil
# kategoriya qatoriga aylanadi (oq bold matn, band fon).
HDR_REMOVE_RECT_TOPS = [67.5, 95.0]   # sarlavha band rectlari (x0>30)
HDR_SKIP_CHAR_TOPS   = {70, 97}       # "Выручка"(+revenue_mult), "Себестоимость"
REVHDR_REMOVE_AFTER  = 78.0           # revenue va pastdagilar -11.6
COGSHDR_REMOVE_AFTER = 106.0          # cogs va pastdagilar -11.6
HDR_ROW_PT           = 11.6

# ── TEPADA yangi metrik qatorlar uchun joy ochish ──
# Bu top dan PASTdagi hamma narsa pastga suriladi:
TOP_INSERT_AFTER_TOP = 67.0
# Surilish (7 qator × 11.6pt):
TOP_INSERT_PT        = 81.2
# 7 yangi qator tops (Месяц=59 dan keyin):
NEW_ROW_TOPS         = [70.0, 81.6, 93.2, 104.8, 116.4, 128.0, 139.6]
NEW_ROW_H            = 11.6

# ── Выручка (82) ostiga 2 yangi qator (Инстаграм/B2B выручка) ──
# Bu top dan boshlab hamma narsa qo'shimcha pastga suriladi
# (revenue qatori 82 da, spacer 89.7 da, Себестоимость band 95 da):
REV_INSERT_AFTER_TOP = 89.0
REV_INSERT_PT        = 23.2      # 2 qator × 11.6
REV_BAND_TOP         = 79.2      # revenue qatorining template'dagi fon top'i
REV_SPLIT_ROWS = [
    ("instagram_revenue", "Инстаграм выручка", "num"),
    ("b2b_revenue",       "B2B выручка",       "num"),
]

# ── Сырьевая себестоимость (109) ostiga 2 qator (Инстаграм/B2B) ──
COGS_INSERT_AFTER_TOP = 115.0    # cogs (109) dan keyin, Убыток (120) dan oldin
COGS_INSERT_PT        = 23.2     # 2 qator × 11.6
COGS_BAND_TOP         = 106.7    # cogs qatorining template'dagi fon top'i
COGS_SPLIT_ROWS = [
    ("instagram_cogs", "Инстаграм себестоимость", "num"),
    ("b2b_cogs",       "B2B себестоимость",       "num"),
]

# ── Программа (5237) — admin oxirida, Стоянка (670) dan keyin ──
PROG_INSERT_AFTER_TOP = 675.0
PROG_INSERT_PT        = 11.6

# ── Скидка/Бонус: Admin → Kommerciya (root account o'zgargan) ──
# Template'da admin bo'limida turgan Скидка/Бонус endi Kommerciya bo'limida,
# Реклама и маркетинг (741) dan keyin chiziladi.
# Яндекс инстаграм (yandex_inst, 5236) ham template joyidan (659) OLINADI, lekin
# endi Kommerciya'da alohida emas — 5238 Инстаграм group ichida leaf sifatida
# chiziladi (NEW_COMMER_ROWS, reparent bilan mos).
MOVED_TO_COMMER   = {"skidka", "bonus", "yandex_inst"}
MOVED_COMMER_ROWS = [("skidka",      "Скидка"),
                     ("bonus",       "Бонус сотрудникам")]
# Olib tashlanadigan zebra fonlar: Скидка(565.7), Бонус(576.9),
# Яндекс инст(654.6) + almashinish buzilmasligi uchun Стоянка(665.7) va
# blank(676.8) ham olib tashlanadi (Стоянка gray qilib qayta chiziladi).
MOVE_REMOVE_RECT_TOPS = [565.7, 576.9, 654.6, 665.7, 676.8]
STOYANKA_BAND_TOP = 665.7   # gray qilib qayta chiziladigan band
MOVE_UP_AFTER_1   = 585.0   # Скидка+Бонус o'rni: pastdagilar -23.2
MOVE_UP_AFTER_2   = 663.0   # Яндекс инстаграм o'rni: yana -11.6
MOVE_DOWN_AFTER   = 748.0   # Реклама dan keyin qatorlar (2 ko'chirilgan Скидка/Бонус
                            # + Инстаграм group + 4 leaf = 7 qator): +81.2
MOVE_ROW_PT       = 11.6
MOVE_DOWN_ROWS    = 7       # Реклама dan keyingi yangi qatorlar soni

# ── Инстаграм(5238 group) va uning leaf'lari — Kommerciya, ko'chirilgan
#    Скидка/Бонус dan keyin chiziladi ──
#    Инстаграм = qizil group sarlavha; ostida 4 leaf:
#      Таргет(5239), Яндекс инстаграм(5236, reparent), Таргетолог, Маркетолог.
#    instagram_group qiymati = shu 4 leaf yig'indisi (_derive'da hisoblanadi).
NEW_COMMER_ROWS = [("instagram_group", "Инстаграм",          0),   # group sarlavha
                   ("target",          "Таргет",             1),   # 5239 leaf
                   ("yandex_inst",     "Яндекс инстаграм",   1),   # 5236 leaf
                   ("target_salary",   "Таргетолог",         1),   # oylik leaf
                   ("market_salary",   "Маркетолог",         1)]   # oylik leaf
NEW_COMMER_INDENT_X = 40.0  # leaf uchun chekinish (group 33.5 da)

# ── Кредит/Алименты GAP yopish (v6 dan) ──
GAP_REMOVE_RECT_TOPS = [421.4, 432.5]
GAP_RECT_TOL         = 1.0
GAP_SHIFT_AFTER_TOP  = 440.0
GAP_SHIFT_PT         = 23.2

MONTH_RU = {
    "jan":"Январь",  "feb":"Февраль", "mar":"Март",
    "apr":"Апрель",  "may":"Май",     "jun":"Июнь",
    "jul":"Июль",    "aug":"Август",  "sep":"Сентябрь",
    "oct":"Октябрь", "nov":"Ноябрь",  "dec":"Декабрь",
}

RED_BG_ROWS = {"marginal", "gross_profit", "op_profit", "net_profit",
               "revenue", "cogs"}
BOLD_ROWS   = {"total_manuf"}
# Qizil kategoriya qatoriga aylangan data qatorlar (oq bold matn)
CATEGORY_ROWS = {"revenue", "cogs"}

# 7 yangi metrik qator (tepada)
# 4-element: qator uslubi — "red" (total ko'rinishi) yoki "zebra" (oddiy)
# prod_volume — "Объём производства" kategoriya qatori: ostidagi 3 qator yig'indisi
EXTRA_ROWS = [
    ("units_sold",         "Количество продаж",                   "plain", "red"),
    ("instagram_sold",     "Инстаграм продаж",                    "plain", "zebra"),
    ("b2b_sold",           "B2B продаж",                          "plain", "zebra"),
    ("prod_volume",        "Объём производства",                  "num",   "red"),
    ("units_produced",     "Количество произведённых изделий",    "plain", "zebra"),
    ("production_cost",    "Сумма производства",                  "num",   "zebra"),
    ("production_workers", "Количество производственных рабочих", "plain", "zebra"),
]


def _parse_col(ck):
    parts = ck.split("_")
    mon   = MONTH_RU.get(parts[0].lower(), parts[0].capitalize())
    year  = parts[1] if len(parts) > 1 else ""
    return mon, year


ROW_MAP = {
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
    659: ("yandex_inst",   "num"),
    670: ("stoyanka",      "num"),
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


def _fmt(v, style):
    rv = int(round(v)) if isinstance(v, (int, float)) else 0
    if style == "dollar":  return f"${rv:,}"
    if style == "pct":     return f"{rv}%"
    if style == "pct_dec": return f"{rv}%"
    if style == "plain":   return f"{rv:,}"
    return f"{rv:,}"


def _derive(data, n):
    def g(k): return (data.get(k, []) + [0.0]*n)[:n]

    rev   = g("revenue")
    cogs  = g("cogs")
    ladj  = g("loss_adj")
    other = g("other_income")

    mfg = ["komunal","produkt","arenda_cex","proizvodstvo","nalog_imush","zarplata_pr"]
    # skidka/bonus/yandex_inst — root account o'zgargan: endi Kommerciyada
    adm = ["uslugi","prochie","komis_bank","podoh_nalog","inps","sp",
           "mobil_bank","nds","utilizaciya","kantc",
           "komis_klik","transport","obed","ofis","arenda_dukon",
           "prazdnik","obuchenie","remont","fin_uslugi",
           "kurs_razn","svyaz","zarplata_adm","yandex","stoyanka",
           "programma"]
    # Инстаграм group (5238) — ko'rinadigan 4 leaf yig'indisi:
    #   target(5239) + yandex_inst(5236, reparent) + target_salary + market_salary.
    # yandex_inst endi com da ALOHIDA emas — instagram_group ichida.
    # reklama (5218) allaqachon target/market oyliklaridan tozalangan (API da),
    # shuning uchun bu yerda double-count bo'lmaydi.
    com = ["arenda_reklam","khairiya","reklama","skidka","bonus"]

    def vsum(*keys):
        r = [0.0]*n
        for k in keys:
            for i, v in enumerate(g(k)): r[i] += v
        return r

    ig_group    = vsum("target", "yandex_inst", "target_salary", "market_salary")
    marginal    = [rev[i]-cogs[i]-ladj[i] for i in range(n)]
    total_manuf = vsum(*mfg)
    gross       = [marginal[i]+other[i]-total_manuf[i] for i in range(n)]
    total_admin = vsum(*adm)
    total_comm  = [vsum(*com)[i] + ig_group[i] for i in range(n)]
    op_profit   = [gross[i]-total_admin[i]-total_comm[i] for i in range(n)]
    nalog       = g("nalog_prib")
    net_profit  = [op_profit[i]-nalog[i] for i in range(n)]

    def pct(num, den):
        return [round(num[i]/den[i]*100,2) if den[i] else 0.0 for i in range(n)]

    return {
        "marginal":     marginal,
        "margin_pct":   pct(marginal, rev),
        "total_manuf":  total_manuf,
        "gross_profit": gross,
        "gross_pct":    pct(gross, rev),
        "total_admin":  total_admin,
        "total_commer": total_comm,
        "instagram_group": ig_group,
        "op_profit":    op_profit,
        "op_pct":       pct(op_profit, rev),
        "net_profit":   net_profit,
        "net_pct":      pct(net_profit, rev),
        "s_balansa":    net_profit,
        "raznitsa":     [0.0]*n,
    }


def _is_red_rect(clr):
    if isinstance(clr, (int, float)): return False
    if isinstance(clr, (list, tuple)) and len(clr) >= 3:
        return clr[0] > 0.5 and clr[1] < 0.35 and clr[2] < 0.35
    return False


def _value_color(v, data_key, base_clr):
    if not isinstance(v, (int, float)): return base_clr
    if v < 0:
        return C_BLACK if data_key in RED_BG_ROWS else C_RED
    return base_clr


def _bold_font(font_name):
    if "Bold" in font_name: return font_name
    if "Rubik" in font_name: return "Rubik-Bold"
    return font_name + "-Bold"


# ── Koordinata tuzatish: TOP insert (pastga) + GAP close (yuqoriga) ──
def _adj_bottom(top_key, bottom):
    b = bottom
    if top_key >= TOP_INSERT_AFTER_TOP:
        b += TOP_INSERT_PT          # tepaga joy → pastga sur
    if top_key >= REVHDR_REMOVE_AFTER:
        b -= HDR_ROW_PT             # Выручка sarlavhasi o'chirildi → yuqoriga
    if top_key >= COGSHDR_REMOVE_AFTER:
        b -= HDR_ROW_PT             # Себестоимость sarlavhasi o'chirildi → yuqoriga
    if top_key >= REV_INSERT_AFTER_TOP:
        b += REV_INSERT_PT          # Выручка sub-qatorlari uchun joy
    if top_key >= COGS_INSERT_AFTER_TOP:
        b += COGS_INSERT_PT         # Себестоимость sub-qatorlari uchun joy
    if top_key > PROG_INSERT_AFTER_TOP:
        b += PROG_INSERT_PT         # Программа qatori uchun joy
    if top_key > GAP_SHIFT_AFTER_TOP:
        b -= GAP_SHIFT_PT           # Кредит/Алименты gap → yuqoriga sur
    if top_key > MOVE_UP_AFTER_1:
        b -= 2 * MOVE_ROW_PT        # Скидка+Бонус ko'chirildi → yuqoriga
    if top_key > MOVE_UP_AFTER_2:
        b -= MOVE_ROW_PT            # Яндекс инстаграм ko'chirildi → yuqoriga
    if top_key >= MOVE_DOWN_AFTER:
        b += MOVE_DOWN_ROWS * MOVE_ROW_PT   # Kommerciyada 5 yangi qator → pastga
    return b


def _draw_dynamic_header(cv, col_keys, col_x, page):
    chars_by_top = defaultdict(list)
    for ch in page.chars:
        chars_by_top[round(ch["top"])].append(ch)

    # Год(47), Месяц(59) — TOP_INSERT dan yuqorida, surilmaydi
    for pdf_top, use_year in [(47, True), (59, False)]:
        chars = chars_by_top.get(pdf_top, [])
        ref   = [c for c in chars if c.get("text","").strip() and c["x0"] < LABEL_CUTOFF]
        if not ref: continue
        size = ref[0].get("size", 6.88)
        font = resolve_font(ref[0].get("fontname",""))
        clr  = to_color(ref[0].get("non_stroking_color",(1,1,1)))
        by   = rl_y(ref[0]["bottom"])
        for i, cx in enumerate(col_x):
            if i >= len(col_keys): break
            mon, year = _parse_col(col_keys[i])
            cv.setFont(font, size); cv.setFillColor(clr)
            cv.drawRightString(cx, by, year if use_year else mon)


def _draw_extra_rows_top(cv, full, col_x, n_cols, std_font, std_size, std_color):
    """6 yangi metrik qator — Месяц dan keyin, tepada."""
    C_GRAY   = Color(0.9529412, 0.9529412, 0.9529412)
    C_RED_BG = Color(0.85, 0.11, 0.11)   # template'dagi total qatorlar bilan bir xil

    zebra = 0
    for idx, (dkey, label, fstyle, rstyle) in enumerate(EXTRA_ROWS):
        top    = NEW_ROW_TOPS[idx]
        bottom = top + 7.0
        by     = rl_y(bottom)
        values = full.get(dkey, [0] * n_cols)

        # Fon — jadval kengligida
        if rstyle == "red":
            bg, row_font, row_clr = C_RED_BG, "Rubik-Bold", C_WHITE
        else:
            bg = C_GRAY if zebra % 2 == 0 else C_WHITE
            zebra += 1
            row_font, row_clr = std_font, std_color
        cv.setFillColor(bg)
        cv.rect(31.4, rl_y(top + NEW_ROW_H), 814.2 - 31.4, NEW_ROW_H, stroke=0, fill=1)

        # Label
        cv.setFont(row_font, std_size); cv.setFillColor(row_clr)
        cv.drawString(33.5, by, label)

        # Har oy raqamlari
        for i, cx in enumerate(col_x):
            v   = values[i] if i < len(values) else 0
            txt = _fmt(v, fstyle)
            cv.setFont(row_font, std_size); cv.setFillColor(row_clr)
            cv.drawRightString(cx, by, txt)


def _draw_split_rows(cv, full, col_x, n_cols, std_font, std_size, std_color,
                     page, anchor_top, band_top, split_rows):
    """Anchor qatoridan keyin Инстаграм/B2B sub-qatorlarini chizadi
    (gray/white zebra). Выручка va Себестоимость uchun ishlatiladi."""
    C_GRAY = Color(0.9529412, 0.9529412, 0.9529412)

    chars      = [ch for ch in page.chars
                  if round(ch["top"]) == anchor_top and ch.get("text","").strip()]
    raw_bottom = chars[0]["bottom"] if chars else anchor_top + 7.0
    base_by    = _adj_bottom(anchor_top, raw_bottom)
    fin_band   = band_top + _adj_bottom(anchor_top, 0.0)   # anchor surilishi bilan

    for idx, (dkey, label, fstyle) in enumerate(split_rows):
        off    = NEW_ROW_H * (idx + 1)
        values = full.get(dkey) or [0.0] * n_cols

        # Fon — anchor oq, keyin gray/white almashinadi
        bg = C_GRAY if idx % 2 == 0 else C_WHITE
        cv.setFillColor(bg)
        cv.rect(31.4, rl_y(fin_band + off + NEW_ROW_H), 782.8, NEW_ROW_H,
                stroke=0, fill=1)

        by = rl_y(base_by + off)
        cv.setFont(std_font, std_size); cv.setFillColor(std_color)
        cv.drawString(33.5, by, label)
        for i, cx in enumerate(col_x):
            v = values[i] if i < len(values) else 0
            cv.setFont(std_font, std_size); cv.setFillColor(std_color)
            cv.drawRightString(cx, by, _fmt(v, fstyle))


def _draw_programma_row(cv, full, col_x, n_cols, std_font, std_size, std_color, page):
    """Программа (5237) — admin oxirida, Стоянка dan keyin (oq fon)."""
    chars_670  = [ch for ch in page.chars
                  if round(ch["top"]) == 670 and ch.get("text","").strip()]
    raw_bottom = chars_670[0]["bottom"] if chars_670 else 677.0
    by         = rl_y(_adj_bottom(670, raw_bottom) + PROG_INSERT_PT)
    values     = full.get("programma") or [0.0] * n_cols

    cv.setFont(std_font, std_size); cv.setFillColor(std_color)
    cv.drawString(33.5, by, "Программа")
    for i, cx in enumerate(col_x):
        v   = values[i] if i < len(values) else 0.0
        clr = C_RED if (isinstance(v, (int, float)) and v < 0) else std_color
        cv.setFont(std_font, std_size); cv.setFillColor(clr)
        cv.drawRightString(cx, by, _fmt(v, "num"))


def _draw_moved_commer_rows(cv, full, col_x, n_cols, std_font, std_size, std_color, page):
    """Скидка/Бонус/Яндекс инстаграм — Kommerciya bo'limida, Реклама dan keyin.
    Bu zonada zebra yo'q (oq fon), faqat matn chiziladi."""
    chars_741  = [ch for ch in page.chars
                  if round(ch["top"]) == 741 and ch.get("text","").strip()]
    raw_bottom = chars_741[0]["bottom"] if chars_741 else 748.0
    base_by    = _adj_bottom(741, raw_bottom)      # Реклама qatorining final bottom'i

    for idx, (dkey, label) in enumerate(MOVED_COMMER_ROWS):
        by     = rl_y(base_by + MOVE_ROW_PT * (idx + 1))
        values = full.get(dkey) or [0.0] * n_cols

        cv.setFont(std_font, std_size); cv.setFillColor(std_color)
        cv.drawString(33.5, by, label)
        for i, cx in enumerate(col_x):
            v   = values[i] if i < len(values) else 0.0
            clr = C_RED if (isinstance(v, (int, float)) and v < 0) else std_color
            cv.setFont(std_font, std_size); cv.setFillColor(clr)
            cv.drawRightString(cx, by, _fmt(v, "num"))


def _draw_new_commer_rows(cv, full, col_x, n_cols, std_font, std_size, std_color, page):
    """Инстаграм(5238 group) + uning leaf'lari — Kommerciya bo'limida,
    ko'chirilgan Скидка/Бонус dan keyin.
    Инстаграм (5238 group) — qizil kategoriya qatori (oq qalin matn, qizil fon).
    Leaf'lar (Таргет, Яндекс инстаграм, Таргетолог, Маркетолог) — oq fon,
    NEW_COMMER_INDENT_X indent."""
    C_RED_BG   = Color(0.85, 0.11, 0.11)   # template kategoriya qatorlari bilan bir xil
    chars_741  = [ch for ch in page.chars
                  if round(ch["top"]) == 741 and ch.get("text","").strip()]
    raw_bottom = chars_741[0]["bottom"] if chars_741 else 748.0
    base_by    = _adj_bottom(741, raw_bottom)      # Реклама qatorining final bottom'i
    n_moved    = len(MOVED_COMMER_ROWS)            # ko'chirilgan qatorlar (Скидка/Бонус = 2)

    for idx, (dkey, label, indent) in enumerate(NEW_COMMER_ROWS):
        # 2 ko'chirilgan qatordan keyin: +3, +4, +5 ...
        text_bottom = base_by + MOVE_ROW_PT * (n_moved + idx + 1)
        by          = rl_y(text_bottom)
        values      = full.get(dkey) or [0.0] * n_cols
        label_x     = NEW_COMMER_INDENT_X if indent else 33.5

        is_red = (dkey == "instagram_group")   # 5238 group — qizil kategoriya qatori

        if is_red:
            # Qizil fon band (jadval kengligida) — _draw_extra_rows_top geometriyasi:
            # matn tayanchi band tepasidan 7.0, band tubidan 4.6pt
            cv.setFillColor(C_RED_BG)
            cv.rect(31.4, rl_y(text_bottom + 4.6), 782.8, MOVE_ROW_PT, stroke=0, fill=1)
            row_font, row_clr = _bold_font(std_font), C_WHITE
        else:
            row_font, row_clr = std_font, std_color

        cv.setFont(row_font, std_size); cv.setFillColor(row_clr)
        cv.drawString(label_x, by, label)
        for i, cx in enumerate(col_x):
            v = values[i] if i < len(values) else 0.0
            if is_red:
                # qizil fonda: manfiy → qora (o'qilishi uchun), musbat → oq
                clr = C_BLACK if (isinstance(v, (int, float)) and v < 0) else C_WHITE
            else:
                clr = C_RED if (isinstance(v, (int, float)) and v < 0) else std_color
            cv.setFont(row_font, std_size); cv.setFillColor(clr)
            cv.drawRightString(cx, by, _fmt(v, "num"))


def generate(data: dict,
             output_filename: str = "pl_report.pdf",
             col_keys: list = None) -> str:

    register_fonts()
    template = get_template("pl_statement_final.pdf")
    output   = get_output_path(output_filename)
    n_cols   = min(len(col_keys), 8) if col_keys else 8
    col_x    = TEMPLATE_COL_X[:n_cols]
    col_keys = (col_keys or [])[:n_cols]

    full = {**data, **_derive(data, n_cols)}
    for dkey in ["units_sold","instagram_sold","b2b_sold",
                 "instagram_revenue","b2b_revenue",
                 "instagram_cogs","b2b_cogs","programma",
                 "instagram_exp","target","yandex_inst",
                 "target_salary","market_salary",
                 "units_produced","production_cost","production_workers"]:
        if dkey not in full:
            full[dkey] = [0] * n_cols

    # "Объём производства" — ostidagi 3 qator yig'indisi (oyma-oy)
    def _v(key, i):
        vals = full.get(key) or []
        return float(vals[i] or 0) if i < len(vals) else 0.0

    full["prod_volume"] = [
        _v("units_produced", i) + _v("production_cost", i) + _v("production_workers", i)
        for i in range(n_cols)
    ]

    cv = new_canvas(output)

    with pdfplumber.open(template) as pdf:
        page = pdf.pages[0]

        cv.setFillColor(C_WHITE)
        cv.rect(0, 0, 842, 1191, stroke=0, fill=1)

        # ── RECTS ──
        for r in bg_fill_objects(page):
            clr = r.get("non_stroking_color")
            if clr is None: continue

            r_top = r.get("top", 0)

            # Кредит/Алименты bo'sh rect — skip
            if any(abs(r_top - gt) <= GAP_RECT_TOL for gt in GAP_REMOVE_RECT_TOPS):
                continue

            # Kommerciyaga ko'chirilgan qatorlar zonasi — skip
            if any(abs(r_top - mt) <= GAP_RECT_TOL for mt in MOVE_REMOVE_RECT_TOPS):
                continue

            # Выручка/Себестоимость sarlavha bandlari — skip
            # (x0>30: chap chetdagi oq sidebar rectlariga tegmaymiz)
            if r.get("x0", 0) > 30 and any(
                    abs(r_top - ht) <= GAP_RECT_TOL for ht in HDR_REMOVE_RECT_TOPS):
                continue

            r_bottom = _adj_bottom(r_top, r["bottom"])

            if _is_red_rect(clr):
                cv.setFillColor(Color(0.85, 0.11, 0.11))
            else:
                cv.setFillColor(to_color(clr))
            cv.rect(r["x0"], rl_y(r_bottom), r["width"], r["height"], stroke=0, fill=1)

        # Стоянка zebra fonini gray qilib qayta chizamiz (ko'chirishdan keyin
        # gray/white almashinishi buzilmasligi uchun; blank qator oq qoladi)
        cv.setFillColor(Color(0.9529412, 0.9529412, 0.9529412))
        cv.rect(31.4, rl_y(_adj_bottom(STOYANKA_BAND_TOP, STOYANKA_BAND_TOP + 11.6)),
                782.8, 11.6, stroke=0, fill=1)

        # Выручка/Себестоимость data qatorlari — endi qizil kategoriya bandlari
        cv.setFillColor(Color(0.85, 0.11, 0.11))
        cv.rect(31.4, rl_y(_adj_bottom(REV_BAND_TOP, REV_BAND_TOP + NEW_ROW_H)),
                782.8, NEW_ROW_H, stroke=0, fill=1)
        cv.rect(31.4, rl_y(_adj_bottom(COGS_BAND_TOP, COGS_BAND_TOP + NEW_ROW_H)),
                782.8, NEW_ROW_H, stroke=0, fill=1)

        rows = defaultdict(list)
        for ch in page.chars:
            rows[round(ch["top"])].append(ch)

        ref_82    = rows.get(82, [])
        label_82  = [ch for ch in ref_82 if ch["x0"] < LABEL_CUTOFF and ch.get("text","").strip()]
        std_font  = resolve_font(label_82[0].get("fontname","")) if label_82 else "Rubik"
        std_size  = label_82[0].get("size", 6.88) if label_82 else 6.88
        std_color = to_color(label_82[0].get("non_stroking_color",(0,0,0))) if label_82 else C_BLACK

        for top_key in sorted(rows.keys()):

            if top_key in SKIP_TOPS or top_key in HDR_SKIP_CHAR_TOPS:
                continue

            chars    = rows[top_key]
            row_text = "".join(ch.get("text","") for ch in chars)
            if "#REF" in row_text:
                continue

            if top_key in HEADER_TOPS:
                for ch in chars:
                    txt = ch.get("text","")
                    if not txt.strip() or ch["x0"] >= LABEL_CUTOFF: continue
                    cv.setFont(resolve_font(ch.get("fontname","")), ch.get("size",6.88))
                    cv.setFillColor(to_color(ch.get("non_stroking_color",(0,0,0))))
                    cv.drawString(ch["x0"], rl_y(_adj_bottom(top_key, ch["bottom"])), txt)
                continue

            best_key, best_dist = None, 9999
            for rk in ROW_MAP:
                d = abs(top_key - rk)
                if d < best_dist:
                    best_dist, best_key = d, rk

            is_bold_row = (best_dist <= 6 and best_key is not None and
                           ROW_MAP.get(best_key, ("",))[0] in BOLD_ROWS)

            is_cat_row  = (best_dist <= 6 and best_key is not None and
                           ROW_MAP.get(best_key, ("",))[0] in CATEGORY_ROWS)

            # Kommerciyaga ko'chirilgan qatorlar — template joyidan chizilmaydi
            if (best_dist <= 6 and best_key is not None and
                    ROW_MAP.get(best_key, ("",))[0] in MOVED_TO_COMMER):
                continue

            # Label chars
            for ch in chars:
                txt = ch.get("text","")
                if not txt.strip() or ch["x0"] >= LABEL_CUTOFF: continue
                raw_font = resolve_font(ch.get("fontname",""))
                font = _bold_font(raw_font) if (is_bold_row or is_cat_row) else raw_font
                cv.setFont(font, ch.get("size",6.88))
                if is_cat_row:
                    cv.setFillColor(C_WHITE)
                else:
                    cv.setFillColor(to_color(ch.get("non_stroking_color",(0,0,0))))
                cv.drawString(ch["x0"], rl_y(_adj_bottom(top_key, ch["bottom"])), txt)

            if best_dist <= 6 and best_key is not None:
                data_key, fmt_style = ROW_MAP[best_key]
                values = full.get(data_key)
                if not values:
                    continue

                ref      = [ch for ch in chars if ch["x0"] < LABEL_CUTOFF and ch.get("text","").strip()]
                if not ref: ref = chars
                font     = resolve_font(ref[0].get("fontname","")) if ref else std_font
                size     = ref[0].get("size", std_size) if ref else std_size
                base_clr = to_color(ref[0].get("non_stroking_color",(0,0,0))) if ref else std_color

                if data_key in BOLD_ROWS:
                    font = _bold_font(font)
                if data_key in CATEGORY_ROWS:
                    font, base_clr = _bold_font(font), C_WHITE
                if data_key == "raznitsa":
                    base_clr, font = C_RED, "Rubik-Bold"

                dchs = [ch for ch in chars if ch["x0"] >= LABEL_CUTOFF and ch.get("text","").strip()]
                if dchs:
                    raw_bottom = dchs[0]["bottom"]
                elif ref:
                    raw_bottom = ref[0]["bottom"]
                else:
                    raw_bottom = top_key + 7
                by = rl_y(_adj_bottom(top_key, raw_bottom))

                for i, cx in enumerate(col_x):
                    v = values[i] if i < len(values) else 0.0

                    txt = _fmt(v, fmt_style)
                    clr = _value_color(v, data_key, base_clr)

                    cv.setFont(font, size); cv.setFillColor(clr)
                    cv.drawRightString(cx, by, txt)

            else:
                for ch in chars:
                    txt = ch.get("text","")
                    if not txt.strip() or ch["x0"] < LABEL_CUTOFF: continue
                    cv.setFont(resolve_font(ch.get("fontname","")), ch.get("size",6.88))
                    cv.setFillColor(to_color(ch.get("non_stroking_color",(0,0,0))))
                    cv.drawString(ch["x0"], rl_y(_adj_bottom(top_key, ch["bottom"])), txt)

        _draw_dynamic_header(cv, col_keys, col_x, page)

        # ── 6 yangi metrik qator — TEPADA (Месяц dan keyin) ──
        _draw_extra_rows_top(cv, full, col_x, n_cols, std_font, std_size, std_color)

        # ── Инстаграм/B2B выручка — Выручка qatoridan keyin ──
        _draw_split_rows(cv, full, col_x, n_cols, std_font, std_size, std_color,
                         page, anchor_top=82, band_top=REV_BAND_TOP,
                         split_rows=REV_SPLIT_ROWS)

        # ── Инстаграм/B2B себестоимость — Сырьевая себестоимость dan keyin ──
        _draw_split_rows(cv, full, col_x, n_cols, std_font, std_size, std_color,
                         page, anchor_top=109, band_top=COGS_BAND_TOP,
                         split_rows=COGS_SPLIT_ROWS)

        # ── Программа — admin bo'limi oxirida ──
        _draw_programma_row(cv, full, col_x, n_cols,
                            std_font, std_size, std_color, page)

        # ── Скидка/Бонус/Яндекс инстаграм — Kommerciya bo'limida ──
        _draw_moved_commer_rows(cv, full, col_x, n_cols,
                                std_font, std_size, std_color, page)

        # ── Инстаграм/Таргет — ko'chirilgan qatorlardan keyin ──
        _draw_new_commer_rows(cv, full, col_x, n_cols,
                              std_font, std_size, std_color, page)

    cv.save()
    return output
