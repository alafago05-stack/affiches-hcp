#!/usr/bin/env python3
"""templates/fiche_emo.py — Fiche 3 : « EMO 2026 » (arabe / RTL)
(reproduction fidèle de ex_1page_A4.pdf).

A4 portrait, sens de lecture droite→gauche. En-tête (logo + bande titre),
1 المقدمة, 2 المعجم (5 cartes), 3 arbre de répartition de la population en
sn du activité, 4 barres SU1-SU4 + 5 donuts de participation, 6 grand tableau
par milieu × région. Contenu piloté par le `spec` ; design figé.
"""

import pandas as pd
from PIL import Image, ImageDraw

from poster_engine import draw_line, font, make_donut, shape, text_w, wrap
from templates import theme as T

BURG = (112, 25, 58)       # #70193A — boîtes / bandes
BURG2 = (132, 32, 68)      # #842044
GOLD = (193, 154, 75)      # #C19A4B
INK = (43, 33, 33)
BODY = (74, 66, 64)
MUTED = (138, 128, 124)
PAGE = (250, 248, 245)
CARD = (255, 255, 255)
BORDER = (232, 224, 210)
CREAM_HI = (247, 240, 226)
WHITE = (255, 255, 255)
LINE = (198, 176, 168)

W = 1191
MARGIN = 40
LANG = "ar"
LABEL = "EMO 2026 (arabe)"
PDF_REF = "ex_1page_A4.pdf"

DEFAULT_SPEC = {
    "dir": "المديرية الجهوية لسوس ماسة",
    "kicker": "EMO 2026 — البحث الجديد حول القوى العاملة",
    "title": "وضعية سوق الشغل بجهة سوس ماسة خلال الفصل الأول لسنة 2026",
    "intro": ("تقدم هذه المذكرة أبرز نتائج بحث القوى العاملة، جيل جديد للبحوث حول سوق الشغل بالمغرب. "
              "تسلط هذه النتائج الضوء على وضعية سوق الشغل من خلال مؤشرات حول المشاركة في سوق الشغل، "
              "والشغل مقابل دخل، والاستخدام غير الكامل للقوى العاملة، مما يتيح قراءة متجددة ويساهم في "
              "تحسين دعم اتخاذ القرار العمومي."),
    "glossary": [
        ("القوى العاملة", "مجموع الأشخاص المشتغلين مقابل دخل والعاطلين بالمفهوم الضيق."),
        ("الشغل مقابل دخل", "العمل المنجز مقابل أجر أو ربح."),
        ("البطالة بالمفهوم الضيق", "الأشخاص الذين لا يتوفرون على شغل ومستعدون للعمل، والذين قاموا بالبحث الفعلي عن شغل."),
        ("القوة العاملة المحتملة", "الأشخاص الذين لا يتوفرون على شغل فعلي ولا يبحثون عنه بشكل فعلي، ولكنهم مستعدون حاليا للعمل."),
        ("خارج القوى العاملة", "الأشخاص الذين لا يشتغلون مقابل دخل وليسوا بعاطلين بالمفهوم الضيق."),
    ],
    "tree_title": "كيف تتوزع الساكنة في سن النشاط؟",
    "tree": {
        "root": ("الأشخاص في سن النشاط", "2 278 229"),
        "lf": ("القوى العاملة", "883 953", "معدل المشاركة في القوى العاملة", "38,8%"),
        "out": ("خارج القوى العاملة", "1 394 276", "نسبة الأشخاص خارج القوى العاملة", "61,2%"),
        "emp": ("المشتغلون مقابل دخل", "811 469", "معدل الشغل مقابل دخل", "35,6%"),
        "unemp": ("العاطلون بالمفهوم الضيق", "72 484", "معدل البطالة بالمفهوم الضيق", "8,2%"),
        "under": ("الشغل الناقص المرتبط بساعات العمل", "27 400", "نسبة الشغل الناقص المرتبط بالساعات", "3,37%"),
        "pot": ("قوة العمل المحتملة", "50 920", "نسبة قوة العمل المحتملة", "3,6%"),
    },
    "s4_title": "الاستخدام غير الكامل للقوى العاملة: مقاربة موسعة",
    "s4_bars": [("SU4", 16.1), ("SU3", 13.2), ("SU2", 11.3), ("SU1", 8.2)],
    "s4_legend": [
        ("SU1", "معدل البطالة بالمفهوم الضيق"),
        ("SU2", "المعدل المركب للبطالة بالمفهوم الضيق والشغل الناقص المرتبط بساعات العمل"),
        ("SU3", "المعدل المركب للبطالة بالمفهوم الضيق والقوى العاملة المحتملة"),
        ("SU4", "المعدل المركب للاستخدام غير الكامل للقوى العاملة"),
    ],
    "s5_title": "المشاركة في سوق الشغل",
    "s5_donuts": [
        ("معدل المشاركة في القوى العاملة", 38.8, "burg"),
        ("معدل الشغل مقابل دخل", 35.6, "gold"),
        ("نسبة الساكنة خارج القوى العاملة", 61.2, "burg"),
    ],
    "s6_title": "مؤشرات سوق الشغل حسب وسط الإقامة (بـ %)",
    "s6_headers": ["معدل المشاركة", "الشغل مقابل دخل", "SU1", "SU2", "SU3", "SU4"],
    "s6_groups": [
        {"name": "جهة سوس ماسة", "rows": [
            ("حضري", [41.7, 38.0, 9.0, 11.7, 14.3, 16.8]),
            ("قروي", [34.3, 32.0, 6.8, 10.5, 11.2, 14.6]),
            ("المجموع", [38.8, 35.6, 8.2, 11.3, 13.2, 16.1]),
        ]},
        {"name": "المغرب", "rows": [
            ("حضري", [41.0, 35.5, 13.5, 18.3, 20.4, 24.0]),
            ("قروي", [43.3, 40.7, 6.1, 13.6, 11.2, 18.3]),
            ("المجموع", [41.8, 37.3, 10.8, 16.6, 17.1, 22.5]),
        ]},
    ],
    "source": "المصدر: المندوبية السامية للتخطيط – بحث القوى العاملة (EMO)",
}


def _shead(draw, x_right, y, num, title):
    """En-tête de section RTL : pastille or (numéro) à droite + titre à gauche."""
    r = 15
    draw.ellipse([x_right - 2 * r, y, x_right, y + 2 * r], fill=GOLD)
    f_n = font("ar", 13, bold=True)
    nt = str(num)
    nw = text_w(draw, nt, f_n, "ar")
    draw.text((x_right - r - nw / 2, y + r - 9), nt, font=f_n, fill=WHITE)
    f_t = font("ar", 16, bold=True)
    draw_line(draw, x_right - 2 * r - 12, y + 3, title, f_t, BURG, "ar", align="right")
    return y + 2 * r + 10


def _tbox(draw, cx, y, w, h, title, value, fill, fg, tsize=11, vsize=17):
    draw.rounded_rectangle([cx - w / 2, y, cx + w / 2, y + h], radius=10, fill=fill)
    f_t = font("ar", tsize, bold=True)
    lines = wrap(draw, title, f_t, w - 20, "ar")[:2]
    ty = y + 8
    for ln in lines:
        draw_line(draw, cx, ty, ln, f_t, fg, "ar", align="center")
        ty += tsize + 4
    f_v = font("ar", vsize, bold=True)
    draw_line(draw, cx, y + h - vsize - 8, value, f_v, WHITE if fill != CREAM_HI else BURG, "ar", align="center")


def _pctblock(draw, cx, y, caption, pct):
    f_c = font("ar", 8)
    draw_line(draw, cx, y, caption, f_c, MUTED, "ar", align="center")
    pw = text_w(draw, shape(pct, "ar"), font("ar", 11, bold=True), "ar") + 22
    draw.rounded_rectangle([cx - pw / 2, y + 14, cx + pw / 2, y + 36], radius=11, fill=BURG)
    draw_line(draw, cx, y + 18, pct, font("ar", 11, bold=True), WHITE, "ar", align="center")


def _connect(draw, parent_cx, parent_bottom, children_cx, child_top):
    """Connecteur parent → enfants : descente, barre horizontale, descentes."""
    midy = (parent_bottom + child_top) / 2
    draw.line([parent_cx, parent_bottom, parent_cx, midy], fill=LINE, width=2)
    xs = [c for c in children_cx]
    draw.line([min(xs), midy, max(xs), midy], fill=LINE, width=2)
    for c in children_cx:
        draw.line([c, midy, c, child_top], fill=LINE, width=2)


def render(spec: dict, lang: str = "ar", output_path: str = "fiche_emo.png") -> str:
    s = {**DEFAULT_SPEC, **(spec or {})}
    lang = "ar"
    img = Image.new("RGB", (W, 1820), PAGE)
    draw = ImageDraw.Draw(img)
    cw = W - 2 * MARGIN
    rr = W - MARGIN  # bord droit du contenu

    # ===== en-tête =====
    y = 28
    logo_w = T.paste_logo(img, W - MARGIN, y, max_h=58)
    draw_line(draw, W - MARGIN - logo_w - 14, y + 16, s["dir"], font(lang, 17, bold=True), BURG, lang, align="right")
    y += 74
    # kicker (pastille or)
    kt = s["kicker"]
    kw = text_w(draw, shape(kt, lang), font(lang, 12, bold=True), lang) + 28
    draw.rounded_rectangle([rr - kw, y, rr, y + 30], radius=8, fill=GOLD)
    draw_line(draw, rr - 14, y + 6, kt, font(lang, 12, bold=True), WHITE, lang, align="right")
    y += 40
    # bande titre
    band_h = 56
    draw.rounded_rectangle([MARGIN, y, W - MARGIN, y + band_h], radius=10, fill=BURG)
    draw_line(draw, rr - 20, y + 15, s["title"], font(lang, 22, bold=True), WHITE, lang, align="right")
    y += band_h + 20

    # ===== 1 المقدمة =====
    yh = _shead(draw, rr, y, 1, "المقدمة")
    f_b = font(lang, 11)
    iy = yh + 4
    for ln in wrap(draw, s["intro"], f_b, cw, lang):
        draw_line(draw, rr, iy, ln, f_b, BODY, lang, align="right")
        iy += 18
    y = iy + 12

    # ===== 2 المعجم (5 cartes) =====
    yh = _shead(draw, rr, y, 2, "المعجم")
    items = s["glossary"]
    n = len(items)
    gap = 12
    gcw = (cw - gap * (n - 1)) / n
    gch = 122
    gy = yh + 6
    for i, (term, definition) in enumerate(items):
        gx1 = rr - i * (gcw + gap)   # RTL : première carte à droite
        gx0 = gx1 - gcw
        hi = "محتمل" in term
        T.card(draw, gx0, gy, gx1, gy + gch, fill=CREAM_HI if hi else CARD, radius=9)
        draw.rounded_rectangle([gx1 - 4, gy, gx1, gy + gch], radius=2, fill=GOLD if hi else BURG)
        draw_line(draw, gx1 - 12, gy + 10, term, font(lang, 11, bold=True), BURG, lang, align="right")
        dyy = gy + 34
        for ln in wrap(draw, definition, font(lang, 8), gcw - 22, lang)[:7]:
            draw_line(draw, gx1 - 12, dyy, ln, font(lang, 8), MUTED, lang, align="right")
            dyy += 11
    y = gy + gch + 18

    # ===== 3 arbre =====
    yh = _shead(draw, rr, y, 3, s["tree_title"])
    t = s["tree"]
    ty0 = yh + 8
    cx_mid = W / 2
    # racine
    _tbox(draw, cx_mid, ty0, 250, 58, t["root"][0], t["root"][1], CREAM_HI, BURG, tsize=11, vsize=18)
    # niveau 1
    lf_cx, out_cx = 360, 830
    y1 = ty0 + 100
    _connect(draw, cx_mid, ty0 + 58, [lf_cx, out_cx], y1)
    _tbox(draw, lf_cx, y1, 250, 56, t["lf"][0], t["lf"][1], GOLD, WHITE, tsize=12, vsize=18)
    _tbox(draw, out_cx, y1, 250, 56, t["out"][0], t["out"][1], GOLD, WHITE, tsize=12, vsize=18)
    _pctblock(draw, lf_cx, y1 + 62, t["lf"][2], t["lf"][3])
    _pctblock(draw, out_cx, y1 + 62, t["out"][2], t["out"][3])
    # niveau 2
    emp_cx, unemp_cx, pot_cx = 250, 480, 830
    y2 = y1 + 148
    _connect(draw, lf_cx, y1 + 56 + 44, [emp_cx, unemp_cx], y2)
    _connect(draw, out_cx, y1 + 56 + 44, [pot_cx], y2)
    _tbox(draw, emp_cx, y2, 220, 54, t["emp"][0], t["emp"][1], BURG, WHITE, tsize=11, vsize=16)
    _tbox(draw, unemp_cx, y2, 210, 54, t["unemp"][0], t["unemp"][1], BURG, WHITE, tsize=11, vsize=16)
    _tbox(draw, pot_cx, y2, 250, 54, t["pot"][0], t["pot"][1], BURG, WHITE, tsize=11, vsize=16)
    _pctblock(draw, emp_cx, y2 + 60, t["emp"][2], t["emp"][3])
    _pctblock(draw, unemp_cx, y2 + 60, t["unemp"][2], t["unemp"][3])
    _pctblock(draw, pot_cx, y2 + 60, t["pot"][2], t["pot"][3])
    # niveau 3
    y3 = y2 + 150
    _connect(draw, emp_cx, y2 + 54 + 46, [emp_cx], y3)
    _tbox(draw, emp_cx, y3, 250, 66, t["under"][0], t["under"][1], BURG, WHITE, tsize=10, vsize=16)
    _pctblock(draw, emp_cx, y3 + 72, t["under"][2], t["under"][3])
    y = max(y3 + 108, y2 + 60 + 60) + 16

    # ===== 4 (droite) + 5 (gauche) =====
    gap = 30
    colw = (cw - gap) / 2
    r_x1 = rr                      # section 4 : moitié droite
    r_x0 = rr - colw
    l_x1 = MARGIN + colw           # section 5 : moitié gauche
    l_x0 = MARGIN
    top = y

    yh4 = _shead(draw, r_x1, y, 4, s["s4_title"])
    T.card(draw, r_x0, yh4 + 4, r_x1, yh4 + 250, radius=12)
    bars = s["s4_bars"]
    nb = len(bars)
    plot_x0, plot_x1 = r_x0 + 20, r_x1 - 20
    baseline = yh4 + 4 + 150
    bw = (plot_x1 - plot_x0) / nb
    vmax = max(v for _, v in bars) or 1
    for i, (name, v) in enumerate(bars):
        bxc = plot_x0 + i * bw + bw / 2
        bh = v / vmax * 110
        draw.rounded_rectangle([bxc - 34, baseline - bh, bxc + 34, baseline], radius=6, fill=BURG)
        draw_line(draw, bxc, baseline - bh - 22, f"{v:.1f}".replace(".", ",") + "%", font(lang, 13, bold=True), BURG, lang, align="center")
        draw_line(draw, bxc, baseline + 8, name, font(lang, 11, bold=True), INK, lang, align="center")
    ly = yh4 + 4 + 168
    for code, desc in s["s4_legend"]:
        draw.rounded_rectangle([r_x1 - 20 - 34, ly, r_x1 - 20, ly + 18], radius=5, fill=BURG)
        draw_line(draw, r_x1 - 20 - 17, ly + 2, code, font(lang, 9, bold=True), WHITE, lang, align="center")
        draw_line(draw, r_x1 - 20 - 44, ly + 1, desc, font(lang, 9), BODY, lang, align="right")
        ly += 22
    r_bottom = ly

    yh5 = _shead(draw, l_x1, top, 5, s["s5_title"])
    dy = yh5 + 8
    color_map = {"burg": BURG, "gold": GOLD}
    for label, pct, col in s["s5_donuts"]:
        T.card(draw, l_x0, dy, l_x1, dy + 74, radius=12)
        dsize = 58
        donut = make_donut(pct, "#%02X%02X%02X" % color_map.get(col, BURG), size_px=dsize)
        img.paste(donut, (int(l_x0 + 14), int(dy + 8)), donut)
        draw_line(draw, l_x0 + 14 + dsize / 2, dy + 8 + dsize / 2 - 9, f"{pct:.1f}".replace(".", ",") + "%",
                  font(lang, 11, bold=True), BURG, lang, align="center")
        draw_line(draw, l_x1 - 16, dy + 26, label, font(lang, 12, bold=True), INK, lang, align="right")
        dy += 84
    y = max(r_bottom, dy) + 18

    # ===== 6 tableau =====
    yh = _shead(draw, rr, y, 6, s["s6_title"])
    _draw_table(draw, MARGIN, yh + 8, cw, s, lang)
    y = yh + 8 + _table_height(s)

    # ===== source =====
    band_y = y + 8
    draw.rounded_rectangle([MARGIN, band_y, W - MARGIN, band_y + 34], radius=8, fill=BURG)
    draw_line(draw, rr - 16, band_y + 9, s["source"], font(lang, 10, bold=True), WHITE, lang, align="right")
    draw_line(draw, MARGIN + 16, band_y + 9, "HAUT-COMMISSARIAT AU PLAN", font(lang, 10, bold=True), GOLD, "fr", align="left")
    y = band_y + 34 + 16

    img = img.crop((0, 0, W, int(y)))
    img.save(output_path)
    return output_path


_COL_FRAC = {"group": 0.16, "milieu": 0.10, "v0": 0.155, "v1": 0.165}
_RH = 30
_HH = 34


def _table_height(s):
    nrows = sum(len(g["rows"]) for g in s["s6_groups"])
    return _HH + nrows * _RH + 2


def _draw_table(draw, x, y, w, s, lang):
    rr = x + w
    headers = s["s6_headers"]  # 6 : مشاركة, شغل, SU1..SU4
    group_w = w * 0.16
    milieu_w = w * 0.10
    v_total = w - group_w - milieu_w
    vw = v_total / len(headers)
    # entête (droite -> gauche)
    draw.rectangle([x, y, rr, y + _HH], fill=BURG)
    f_h = font(lang, 10, bold=True)
    cx = rr
    draw_line(draw, cx - group_w / 2, y + 9, "المجال", f_h, WHITE, lang, align="center")
    cx -= group_w
    draw_line(draw, cx - milieu_w / 2, y + 9, "الوسط", f_h, WHITE, lang, align="center")
    cx -= milieu_w
    for h in headers:
        draw_line(draw, cx - vw / 2, y + 9, h, f_h, WHITE, lang, align="center")
        cx -= vw
    # lignes
    ry = y + _HH
    for gi, g in enumerate(s["s6_groups"]):
        rows = g["rows"]
        gh = len(rows) * _RH
        # cellule groupe (fusionnée) à droite
        gbg = CREAM_HI if gi % 2 == 0 else (243, 236, 226)
        draw.rectangle([rr - group_w, ry, rr, ry + gh], fill=gbg)
        draw_line(draw, rr - group_w / 2, ry + gh / 2 - 8, g["name"], font(lang, 11, bold=True), BURG, lang, align="center")
        draw.line([rr - group_w, ry, rr - group_w, ry + gh], fill=GOLD, width=2)
        for ri, (milieu, vals) in enumerate(rows):
            yy = ry + ri * _RH
            total = "مجموع" in milieu
            bg = (244, 237, 227) if total else (CARD if ri % 2 == 0 else (250, 246, 240))
            draw.rectangle([x, yy, rr - group_w, yy + _RH], fill=bg)
            f_m = font(lang, 10, bold=total)
            draw_line(draw, rr - group_w - milieu_w / 2, yy + _RH / 2 - 7, milieu, f_m, BURG if total else INK, lang, align="center")
            cx = rr - group_w - milieu_w
            f_v = font(lang, 10, bold=total)
            for v in vals:
                draw_line(draw, cx - vw / 2, yy + _RH / 2 - 7, f"{v:.1f}".replace(".", ","), f_v, INK, lang, align="center")
                cx -= vw
        ry += gh
    draw.rounded_rectangle([x, y, rr, ry], radius=8, outline=BORDER, width=1)


# ==========================================================================
# Schéma d'édition
# ==========================================================================
def _num(v, d=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return d


def _gloss_to_df(spec):
    return pd.DataFrame([list(x) for x in spec["glossary"]], columns=["Terme (ar)", "Définition (ar)"])


def _gloss_from_df(df, spec):
    return [(str(r["Terme (ar)"]), str(r["Définition (ar)"])) for _, r in df.iterrows() if str(r["Terme (ar)"]).strip()]


def _s4bars_to_df(spec):
    return pd.DataFrame([list(x) for x in spec["s4_bars"]], columns=["Indicateur", "Valeur %"])


def _s4bars_from_df(df, spec):
    return [(str(r["Indicateur"]), _num(r["Valeur %"])) for _, r in df.iterrows() if str(r["Indicateur"]).strip()]


def _s4leg_to_df(spec):
    return pd.DataFrame([list(x) for x in spec["s4_legend"]], columns=["Code", "Définition (ar)"])


def _s4leg_from_df(df, spec):
    return [(str(r["Code"]), str(r["Définition (ar)"])) for _, r in df.iterrows() if str(r["Code"]).strip()]


def _s5_to_df(spec):
    return pd.DataFrame([[lbl, pct, col] for lbl, pct, col in spec["s5_donuts"]],
                        columns=["Libellé (ar)", "Valeur %", "Couleur (burg/gold)"])


def _s5_from_df(df, spec):
    out = []
    for _, r in df.iterrows():
        col = str(r["Couleur (burg/gold)"]).strip().lower()
        out.append((str(r["Libellé (ar)"]), _num(r["Valeur %"]), col if col in ("burg", "gold") else "burg"))
    return out


def _tree_to_df(spec):
    t = spec["tree"]
    order = [("root", "Racine"), ("lf", "Force de travail"), ("out", "Hors force"),
             ("emp", "Occupés"), ("unemp", "Chômeurs"), ("under", "Sous-emploi"), ("pot", "Potentielle")]
    rows = []
    for k, fr in order:
        node = t[k]
        title, value = node[0], node[1]
        cap = node[2] if len(node) > 2 else ""
        pct = node[3] if len(node) > 3 else ""
        rows.append([fr, title, value, cap, pct])
    return pd.DataFrame(rows, columns=["Nœud", "Titre (ar)", "Effectif", "Légende % (ar)", "%"])


def _tree_from_df(df, spec):
    keys = ["root", "lf", "out", "emp", "unemp", "under", "pot"]
    t = {}
    for k, (_, r) in zip(keys, df.iterrows()):
        base = spec["tree"][k]
        if len(base) > 2:
            t[k] = (str(r["Titre (ar)"]), str(r["Effectif"]), str(r["Légende % (ar)"]), str(r["%"]))
        else:
            t[k] = (str(r["Titre (ar)"]), str(r["Effectif"]))
    return t


def _tbl_to_df(spec):
    rows = []
    for g in spec["s6_groups"]:
        for milieu, vals in g["rows"]:
            rows.append([g["name"], milieu] + list(vals))
    return pd.DataFrame(rows, columns=["Région", "Milieu"] + spec["s6_headers"])


def _tbl_from_df(df, spec):
    headers = spec["s6_headers"]
    groups = {}
    order = []
    for _, r in df.iterrows():
        name = str(r["Région"])
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append((str(r["Milieu"]), [_num(r[h]) for h in headers]))
    return [{"name": name, "rows": groups[name]} for name in order]


EDIT_SCHEMA = [
    {"group": "En-tête", "fields": [
        {"kind": "text", "key": "dir", "label": "Direction régionale (ar)"},
        {"kind": "text", "key": "kicker", "label": "Kicker (ar)"},
        {"kind": "textarea", "key": "title", "label": "Titre (ar)"},
    ]},
    {"group": "1 · المقدمة", "fields": [
        {"kind": "textarea", "key": "intro", "label": "Introduction (ar)"},
    ]},
    {"group": "2 · المعجم", "fields": [
        {"kind": "table", "key": "glossary", "to_df": _gloss_to_df, "from_df": _gloss_from_df, "dynamic": True},
    ]},
    {"group": "3 · Arbre de répartition", "fields": [
        {"kind": "table", "key": "tree", "to_df": _tree_to_df, "from_df": _tree_from_df, "dynamic": False},
    ]},
    {"group": "4 · Sous-emploi (SU1-SU4)", "fields": [
        {"kind": "text", "key": "s4_title", "label": "Titre (ar)"},
        {"kind": "table", "key": "s4_bars", "to_df": _s4bars_to_df, "from_df": _s4bars_from_df, "dynamic": True},
        {"kind": "table", "key": "s4_legend", "to_df": _s4leg_to_df, "from_df": _s4leg_from_df, "dynamic": True},
    ]},
    {"group": "5 · Participation (donuts)", "fields": [
        {"kind": "text", "key": "s5_title", "label": "Titre (ar)"},
        {"kind": "table", "key": "s5_donuts", "to_df": _s5_to_df, "from_df": _s5_from_df, "dynamic": True},
    ]},
    {"group": "6 · Tableau par milieu", "fields": [
        {"kind": "text", "key": "s6_title", "label": "Titre (ar)"},
        {"kind": "table", "key": "s6_groups", "to_df": _tbl_to_df, "from_df": _tbl_from_df, "dynamic": True},
    ]},
    {"group": "Bas de page", "fields": [
        {"kind": "text", "key": "source", "label": "Source (ar)"},
    ]},
]
