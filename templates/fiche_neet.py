#!/usr/bin/env python3
"""templates/fiche_neet.py — Fiche 2 : « Les jeunes NEET »
(reproduction fidèle de Affiche NEET Souss-Massa 2024.pdf).

A4 portrait. Bandeau haut + en-tête (titre « Les jeunes NEET »), intro, 3 gros
chiffres clés, puis 7 sections numérotées : phénomène féminin, ancrage rural,
baisse depuis 2017 (courbe 3 séries), repères nationaux, chômage par province,
4 profils, enjeux (bande sombre). Contenu piloté par le `spec` ; design figé.
"""

import pandas as pd
from PIL import Image, ImageDraw

from poster_engine import draw_line, font, make_donut, shape, text_w, wrap
from templates import theme as T

# Palette propre à la maquette NEET (bordeaux un peu plus chaud que la fiche 1)
BURG = (122, 28, 43)       # #7A1C2B
BURG_DARK = (46, 12, 22)   # bande « enjeux » très sombre
GOLD = (198, 148, 74)      # or de la maquette
INK = (43, 33, 33)
BODY = (74, 66, 64)
MUTED = (138, 128, 124)
PAGE = (246, 239, 231)     # crème légèrement plus chaud
WHITE = (255, 255, 255)
RULE = (214, 200, 188)

W = 1191
MARGIN = 48

DEFAULT_SPEC = {
    "top_left": "HAUT-COMMISSARIAT AU PLAN · DIRECTION RÉGIONALE SOUSS-MASSA",
    "top_right": "NOTE STATISTIQUE · ÉDITION 2024",
    "kicker": "MARCHÉ DU TRAVAIL · JEUNESSE",
    "title_main": "Les jeunes ",
    "title_accent": "NEET",
    "subtitle": "Région Souss-Massa — 2024",
    "intro": ("Les NEET désignent les jeunes de 15 à 24 ans qui ne sont ni en emploi, ni en études, "
              "ni en formation. En 2024, ils représentent près d'un quart de cette classe d'âge dans "
              "la région — un phénomène concentré sur les jeunes femmes et le milieu rural, malgré "
              "un recul continu depuis 2017."),
    "stats": [
        ("EFFECTIF RÉGIONAL", "112 000", "jeunes NEET en 2024"),
        ("TAUX RÉGIONAL", "23,9 %", "des 15-24 ans sont NEET"),
        ("POPULATION DE RÉFÉRENCE", "466 866", "jeunes de 15-24 ans"),
    ],
    "s1_title": "Un phénomène d'abord féminin",
    "s1_donut": 74.0,
    "s1_donut_label": "de femmes",
    "s1_note": "Près de 3 NEET sur 4 sont des jeunes femmes.",
    "s1_bars": [("Féminin", 35.3), ("Masculin", 12.0)],
    "s2_title": "Un ancrage rural marqué",
    "s2_bars": [("Rural · ≈ 56 000 jeunes", 32.1), ("Urbain · ≈ 55 000 jeunes", 19.1)],
    "s2_note": "Le poids des NEET est 1,7 fois plus élevé en milieu rural qu'en milieu urbain.",
    "s3_title": "Une baisse continue depuis 2017",
    "s3_sub": "effectifs, en milliers",
    "s3_years": ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024"],
    "s3_series": [
        {"label": "Ensemble", "color": "#2B2121", "values": [145, 138, 130, 113, 101, 99, 95, 112]},
        {"label": "Féminin", "color": "#7A1C2B", "values": [85, 82, 77, 68, 64, 66, 62, 83]},
        {"label": "Masculin", "color": "#C6944A", "values": [15, 16, 16, 14, 13, 14, 13, 28]},
    ],
    "s3_note": "De 145 000 en 2017 à 112 000 en 2024 — un recul de près de 23 % en sept ans.",
    "s4_title": "Repères nationaux",
    "s4_big": "24,4 %",
    "s4_big_label": "taux national",
    "s4_sub": "1 444 000 jeunes NEET au Maroc",
    "s4_bars": [("Femmes", 35.1), ("Hommes", 14.2)],
    "s4_note": "Souss-Massa (23,9 %) se situe légèrement en deçà de la moyenne nationale.",
    "s5_title": "Chômage par province",
    "s5_sub": "15 ans + · %",
    "s5_bars": [
        ("Agadir-Ida-Ou-Tanane", 16.4), ("Inezgane-Aït Melloul", 15.6), ("Tata", 11.7),
        ("Tiznit", 8.9), ("Taroudannt", 8.3), ("Chtouka-Aït Baha", 7.4),
    ],
    "s6_title": "Quatre profils de jeunes NEET",
    "s6_sub": "typologie HCP-OIT · 15-29 ans",
    "s6_profiles": [
        ("Femmes au foyer inactives", "Souvent mariées, confrontées à des contraintes familiales et sociales."),
        ("Chômeurs de longue durée", "Sans emploi depuis plus d'un an, exposés à l'exclusion durable."),
        ("Inactifs pour raisons de santé", "Éloignés du marché du travail pour raisons de santé ou de handicap."),
        ("Découragés ou « invisibles »", "Sans recherche active, rendus plus visibles durant la période Covid-19."),
    ],
    "s7_title": "Enjeux & leviers d'action",
    "s7_note": "en cohérence avec l'ODD 8.6",
    "s7_items": [
        ("Prévenir en amont", "Capital humain et lutte contre le décrochage scolaire."),
        ("Insérer autrement", "Des dispositifs adaptés à la diversité des profils."),
        ("Autonomiser les femmes", "L'inactivité féminine comme enjeu économique central."),
        ("Territorialiser l'action", "Coordonner les politiques, surtout en milieu rural."),
    ],
    "source": ("Source : HCP — Enquête Nationale sur l'Emploi (ENE), 2024 · Champ : 15-24 ans · "
               "Profils : rapport HCP-OIT, 2025"),
}

LANG = "fr"
LABEL = "Les jeunes NEET"
PDF_REF = "Affiche NEET Souss-Massa 2024.pdf"


def _shead(draw, x, y, num, title, rule_to):
    """En-tête de section NEET : numéro or + titre bordeaux + trait fin dessous."""
    f_n = font("fr", 15, bold=True)
    draw_line(draw, x, y, num, f_n, GOLD, "fr", align="left")
    nw = text_w(draw, num, f_n, "fr")
    f_t = font("fr", 17, bold=True)
    draw_line(draw, x + nw + 12, y, title, f_t, BURG, "fr", align="left")
    draw.line([x, y + 28, rule_to, y + 28], fill=RULE, width=1)
    return y + 40


def _bar_row(draw, x, y, w, label, pct, color, lang):
    """Ligne : libellé (gauche) + valeur % (droite, gras) + barre dessous."""
    f_l = font(lang, 11, bold=True)
    draw_line(draw, x, y, label, f_l, INK, lang, align="left")
    f_v = font(lang, 13, bold=True)
    draw_line(draw, x + w, y - 1, f"{pct:.1f}".replace(".", ",") + " %", f_v, BURG, lang, align="right")
    T.hbar(draw, x, y + 20, w, pct, color, track=(233, 224, 213), h=11)


def _neet_linechart(series, years, width_px, height_px, lang):
    fig = T._new_figure(width_px / 100, height_px / 100)
    ax = fig.add_subplot(111)
    fig.patch.set_alpha(0)
    ax.set_facecolor("#EFE7DE")
    xs = list(range(len(years)))
    for s in series:
        ax.plot(xs, s["values"], color=s["color"], linewidth=3, solid_capstyle="round", zorder=3)
        ax.scatter([xs[-1]], [s["values"][-1]], color=s["color"], s=45, zorder=4)
        ax.annotate(str(int(round(s["values"][-1]))), (xs[-1], s["values"][-1]), xytext=(10, 0),
                    textcoords="offset points", va="center", fontsize=14, fontweight="bold", color=s["color"])
    # étiquette de départ pour la première série (Ensemble : 145)
    s0 = series[0]
    ax.annotate(str(int(round(s0["values"][0]))), (xs[0], s0["values"][0]), xytext=(-6, 8),
                textcoords="offset points", ha="center", fontsize=14, fontweight="bold", color=s0["color"])
    ax.set_ylim(0, 165)
    ax.set_yticks([0, 50, 100, 150])
    ax.set_yticklabels(["0", "50", "100", "150"], color="#9A8F86", fontsize=10)
    ax.set_xticks(xs)
    ax.set_xticklabels(years, color="#5A504C", fontsize=11)
    ax.tick_params(length=0)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#D8CFC0")
    ax.margins(x=0.05)
    fig.subplots_adjust(left=0.05, right=0.92, top=0.96, bottom=0.10)
    return T._figure_to_image(fig)


def render(spec: dict, lang: str = "fr", output_path: str = "fiche_neet.png") -> str:
    s = {**DEFAULT_SPEC, **(spec or {})}
    img = Image.new("RGB", (W, 1980), PAGE)
    draw = ImageDraw.Draw(img)
    cw = W - 2 * MARGIN

    # ===== bandeau haut =====
    band_h = 34
    draw.rectangle([0, 0, W, band_h], fill=BURG)
    f_tb = font(lang, 10, bold=True)
    draw_line(draw, MARGIN, 10, s["top_left"], f_tb, (232, 210, 214), lang, align="left")
    draw_line(draw, W - MARGIN, 10, s["top_right"], f_tb, (232, 210, 214), lang, align="right")

    y = band_h + 26
    logo_w = T.paste_logo(img, W - MARGIN, y, max_h=62)
    f_k = font(lang, 12, bold=True)
    draw_line(draw, MARGIN, y, s["kicker"], f_k, GOLD, lang, align="left")
    # titre : « Les jeunes » bordeaux + « NEET » or
    ty = y + 22
    f_ti = font(lang, 44, bold=True)
    draw_line(draw, MARGIN, ty, s["title_main"], f_ti, BURG, lang, align="left")
    mw = text_w(draw, shape(s["title_main"], lang), f_ti, lang)
    draw_line(draw, MARGIN + mw, ty, s["title_accent"], f_ti, GOLD, lang, align="left")
    f_st = font(lang, 20, bold=True)
    draw_line(draw, MARGIN, ty + 58, s["subtitle"], f_st, INK, lang, align="left")
    y = ty + 92
    draw.line([MARGIN, y, W - MARGIN, y], fill=RULE, width=1)
    y += 16

    # ===== intro =====
    f_body = font(lang, 12)
    for line in wrap(draw, s["intro"], f_body, cw, lang):
        draw_line(draw, MARGIN, y, line, f_body, BODY, lang, align="left")
        y += 20
    y += 14

    # ===== 3 chiffres clés =====
    n = len(s["stats"])
    tile_w = cw / n
    for i, (cap, val, sub) in enumerate(s["stats"]):
        tx = MARGIN + i * tile_w
        if i > 0:
            draw.line([tx - 1, y + 4, tx - 1, y + 92], fill=RULE, width=1)
        px = tx + (18 if i > 0 else 0)
        f_cap = font(lang, 11, bold=True)
        draw_line(draw, px, y, cap, f_cap, MUTED, lang, align="left")
        f_val = font(lang, 40, bold=True)
        draw_line(draw, px, y + 20, val, f_val, BURG, lang, align="left")
        f_sub = font(lang, 11)
        draw_line(draw, px, y + 74, sub, f_sub, BODY, lang, align="left")
    y += 116

    # ===== 01 + 02 =====
    gap = 40
    colw = (cw - gap) / 2
    lx, rx = MARGIN, MARGIN + colw + gap
    top = y
    _shead(draw, lx, y, "01", s["s1_title"], lx + colw)
    dy = y + 52
    dsize = 92
    donut = make_donut(s["s1_donut"], "#%02X%02X%02X" % BURG, size_px=dsize)
    img.paste(donut, (int(lx), int(dy)), donut)
    f_dv = font(lang, 16, bold=True)
    draw_line(draw, lx + dsize / 2, dy + dsize / 2 - 12, f"{s['s1_donut']:.0f}%", f_dv, BURG, lang, align="center")
    f_dl = font(lang, 9)
    draw_line(draw, lx + dsize / 2, dy + dsize / 2 + 6, s["s1_donut_label"], f_dl, MUTED, lang, align="center")
    bx = lx + dsize + 20
    bw = colw - dsize - 20
    f_note = font(lang, 10)
    for line in wrap(draw, s["s1_note"], f_note, bw, lang)[:2]:
        draw_line(draw, bx, dy, line, f_note, BODY, lang, align="left")
        dy_note = dy
        dy += 15
    by = dy + 8
    for lbl, pct in s["s1_bars"]:
        col = BURG if "min" in lbl.lower() or "fémin" in lbl.lower() else GOLD
        _bar_row(draw, bx, by, bw, lbl, pct, col, lang)
        by += 42
    left_bottom = by

    _shead(draw, rx, top, "02", s["s2_title"], rx + colw)
    ry = top + 56
    for lbl, pct in s["s2_bars"]:
        col = BURG if "rural" in lbl.lower() else GOLD
        _bar_row(draw, rx, ry, colw, lbl, pct, col, lang)
        ry += 46
    draw.rectangle([rx, ry + 2, rx + 4, ry + 34], fill=GOLD)
    f_n2 = font(lang, 10)
    ny = ry
    for line in wrap(draw, s["s2_note"], f_n2, colw - 16, lang)[:2]:
        draw_line(draw, rx + 14, ny, line, f_n2, BODY, lang, align="left")
        ny += 15
    y = max(left_bottom, ny) + 24

    # ===== 03 courbe pleine largeur =====
    yh = _shead(draw, MARGIN, y, "03", s["s3_title"], W - MARGIN)
    f_sub = font(lang, 11)
    thw = text_w(draw, shape(s["s3_title"], lang), font(lang, 17, bold=True), lang)
    draw_line(draw, MARGIN + 32 + thw + 16, y + 2, s["s3_sub"], f_sub, MUTED, lang, align="left")
    # légende (droite)
    lx2 = W - MARGIN
    f_leg = font(lang, 10, bold=True)
    for ser in reversed(s["s3_series"]):
        lw = text_w(draw, shape(ser["label"], lang), f_leg, lang)
        draw_line(draw, lx2, y + 2, ser["label"], f_leg, INK, lang, align="right")
        draw.line([lx2 - lw - 24, y + 8, lx2 - lw - 8, y + 8], fill=T.hex_to_rgb(ser["color"]), width=3)
        lx2 -= lw + 40
    chart = _neet_linechart(s["s3_series"], s["s3_years"], cw, 300, lang)
    img.paste(chart, (int(MARGIN), int(yh + 6)), chart)
    y = yh + 6 + 300 + 6
    f_n3 = font(lang, 11)
    draw_line(draw, MARGIN, y, s["s3_note"], f_n3, BODY, lang, align="left")
    y += 34

    # ===== 04 + 05 =====
    top = y
    _shead(draw, lx, y, "04", s["s4_title"], lx + colw)
    ay = y + 52
    f_big = font(lang, 40, bold=True)
    draw_line(draw, lx, ay, s["s4_big"], f_big, BURG, lang, align="left")
    bigw = text_w(draw, shape(s["s4_big"], lang), f_big, lang)
    f_bl = font(lang, 11, bold=True)
    draw_line(draw, lx + bigw + 12, ay + 8, s["s4_big_label"], f_bl, MUTED, lang, align="left")
    f_bs = font(lang, 10)
    draw_line(draw, lx + bigw + 12, ay + 26, s["s4_sub"], f_bs, BODY, lang, align="left")
    ay += 62
    for lbl, pct in s["s4_bars"]:
        col = BURG if "femme" in lbl.lower() else GOLD
        _bar_row(draw, lx, ay, colw, lbl, pct, col, lang)
        ay += 44
    draw.rectangle([lx, ay + 2, lx + 4, ay + 30], fill=GOLD)
    ny = ay
    for line in wrap(draw, s["s4_note"], font(lang, 10), colw - 16, lang)[:2]:
        draw_line(draw, lx + 14, ny, line, font(lang, 10), BODY, lang, align="left")
        ny += 15
    left_bottom = ny

    _shead(draw, rx, top, "05", s["s5_title"], rx + colw)
    draw_line(draw, rx + colw, top, s["s5_sub"], font(lang, 10), MUTED, lang, align="right")
    ry = top + 52
    vmax = max(p for _, p in s["s5_bars"]) or 1
    barw = colw - 210
    for i, (name, pct) in enumerate(s["s5_bars"]):
        col = BURG if i < 2 else GOLD
        draw_line(draw, rx, ry, name, font(lang, 10, bold=True), INK, lang, align="left")
        T.hbar(draw, rx + 150, ry + 1, barw, pct / vmax * 100, col, track=(233, 224, 213), h=12)
        draw_line(draw, rx + colw, ry, f"{pct:.1f}".replace(".", ","), font(lang, 11, bold=True), BURG, lang, align="right")
        ry += 30
    y = max(left_bottom, ry) + 22

    # ===== 06 quatre profils =====
    yh = _shead(draw, MARGIN, y, "06", s["s6_title"], W - MARGIN)
    thw = text_w(draw, shape(s["s6_title"], lang), font(lang, 17, bold=True), lang)
    draw_line(draw, MARGIN + 32 + thw + 16, y + 2, s["s6_sub"], font(lang, 11), MUTED, lang, align="left")
    pcols = len(s["s6_profiles"])
    pgap = 22
    pcw = (cw - pgap * (pcols - 1)) / pcols
    py = yh + 6
    for i, (t, d) in enumerate(s["s6_profiles"]):
        px = MARGIN + i * (pcw + pgap)
        draw.rectangle([px, py, px + pcw, py + 3], fill=BURG if i % 2 == 0 else GOLD)
        draw_line(draw, px, py + 12, t, font(lang, 12, bold=True), BURG, lang, align="left")
        dyy = py + 34
        for line in wrap(draw, d, font(lang, 10), pcw, lang)[:3]:
            draw_line(draw, px, dyy, line, font(lang, 10), BODY, lang, align="left")
            dyy += 15
    y = py + 92

    # ===== 07 enjeux (bande sombre) =====
    band_h = 130
    draw.rounded_rectangle([MARGIN, y, W - MARGIN, y + band_h], radius=14, fill=BURG_DARK)
    draw_line(draw, MARGIN + 24, y + 18, "07", font(lang, 16, bold=True), GOLD, lang, align="left")
    draw_line(draw, MARGIN + 24 + 34, y + 18, s["s7_title"], font(lang, 16, bold=True), WHITE, lang, align="left")
    draw_line(draw, W - MARGIN - 24, y + 20, s["s7_note"], font(lang, 10), (200, 170, 150), lang, align="right")
    icols = len(s["s7_items"])
    igap = 22
    icw = (cw - 48 - igap * (icols - 1)) / icols
    iy = y + 54
    for i, (t, d) in enumerate(s["s7_items"]):
        ix = MARGIN + 24 + i * (icw + igap)
        draw_line(draw, ix, iy, str(i + 1), font(lang, 18, bold=True), GOLD, lang, align="left")
        draw_line(draw, ix + 22, iy + 2, t, font(lang, 12, bold=True), WHITE, lang, align="left")
        dyy = iy + 26
        for line in wrap(draw, d, font(lang, 9), icw, lang)[:3]:
            draw_line(draw, ix, dyy, line, font(lang, 9), (214, 198, 190), lang, align="left")
            dyy += 12
    y += band_h + 16

    # ===== source =====
    draw.line([MARGIN, y, W - MARGIN, y], fill=RULE, width=1)
    y += 10
    draw_line(draw, MARGIN, y, s["source"], font(lang, 9), MUTED, lang, align="left")
    draw_line(draw, W - MARGIN, y, "Haut-Commissariat au Plan", font(lang, 9, bold=True), BURG, lang, align="right")
    y += 22

    img = img.crop((0, 0, W, int(y + MARGIN / 2)))
    img.save(output_path)
    return output_path


# ==========================================================================
# Schéma d'édition
# ==========================================================================
def _stats_to_df(spec):
    return pd.DataFrame([list(x) for x in spec["stats"]], columns=["Intitulé", "Valeur", "Sous-texte"])


def _stats_from_df(df, spec):
    return [(str(r["Intitulé"]), str(r["Valeur"]), str(r["Sous-texte"])) for _, r in df.iterrows()]


def _num(v, d=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return d


def _bars_to_df(key):
    def to_df(spec):
        return pd.DataFrame([list(x) for x in spec[key]], columns=["Libellé", "Valeur %"])
    return to_df


def _bars_from_df(key):
    def from_df(df, spec):
        return [(str(r["Libellé"]), _num(r["Valeur %"])) for _, r in df.iterrows() if str(r["Libellé"]).strip()]
    return from_df


def _pairs_to_df(key, cols):
    def to_df(spec):
        return pd.DataFrame([list(x) for x in spec[key]], columns=cols)
    return to_df


def _pairs_from_df(key):
    def from_df(df, spec):
        return [tuple(str(c) for c in r) for r in df.itertuples(index=False)]
    return from_df


def _trend_to_df(spec):
    years = spec["s3_years"]
    data = {"Série": [x["label"] for x in spec["s3_series"]]}
    for i, y in enumerate(years):
        data[y] = [x["values"][i] if i < len(x["values"]) else None for x in spec["s3_series"]]
    return pd.DataFrame(data)


def _trend_from_df(df, spec):
    years = spec["s3_years"]
    out = []
    for i, (_, r) in enumerate(df.iterrows()):
        base = spec["s3_series"][i] if i < len(spec["s3_series"]) else {"color": "#2B2121"}
        out.append({"label": str(r["Série"]), "color": base.get("color", "#2B2121"),
                    "values": [_num(r[y]) for y in years]})
    return out


EDIT_SCHEMA = [
    {"group": "En-tête", "fields": [
        {"kind": "text", "key": "kicker", "label": "Kicker"},
        {"kind": "text", "key": "title_main", "label": "Titre (partie bordeaux)"},
        {"kind": "text", "key": "title_accent", "label": "Titre (partie or)"},
        {"kind": "text", "key": "subtitle", "label": "Sous-titre"},
        {"kind": "text", "key": "top_left", "label": "Bandeau haut — gauche"},
        {"kind": "text", "key": "top_right", "label": "Bandeau haut — droite"},
    ]},
    {"group": "Introduction", "fields": [
        {"kind": "textarea", "key": "intro", "label": "Texte d'introduction"},
    ]},
    {"group": "Chiffres clés", "fields": [
        {"kind": "table", "key": "stats", "to_df": _stats_to_df, "from_df": _stats_from_df, "dynamic": True},
    ]},
    {"group": "01 · Phénomène féminin", "fields": [
        {"kind": "text", "key": "s1_title", "label": "Titre"},
        {"kind": "text", "key": "s1_note", "label": "Note"},
        {"kind": "table", "key": "s1_bars", "to_df": _bars_to_df("s1_bars"), "from_df": _bars_from_df("s1_bars"), "dynamic": True},
    ]},
    {"group": "02 · Ancrage rural", "fields": [
        {"kind": "text", "key": "s2_title", "label": "Titre"},
        {"kind": "text", "key": "s2_note", "label": "Note"},
        {"kind": "table", "key": "s2_bars", "to_df": _bars_to_df("s2_bars"), "from_df": _bars_from_df("s2_bars"), "dynamic": True},
    ]},
    {"group": "03 · Baisse depuis 2017 (courbe)", "fields": [
        {"kind": "text", "key": "s3_title", "label": "Titre"},
        {"kind": "text", "key": "s3_note", "label": "Note"},
        {"kind": "table", "key": "s3_series", "to_df": _trend_to_df, "from_df": _trend_from_df, "dynamic": False},
    ]},
    {"group": "04 · Repères nationaux", "fields": [
        {"kind": "text", "key": "s4_big", "label": "Grand chiffre"},
        {"kind": "text", "key": "s4_sub", "label": "Sous-texte"},
        {"kind": "text", "key": "s4_note", "label": "Note"},
        {"kind": "table", "key": "s4_bars", "to_df": _bars_to_df("s4_bars"), "from_df": _bars_from_df("s4_bars"), "dynamic": True},
    ]},
    {"group": "05 · Chômage par province", "fields": [
        {"kind": "text", "key": "s5_title", "label": "Titre"},
        {"kind": "table", "key": "s5_bars", "to_df": _bars_to_df("s5_bars"), "from_df": _bars_from_df("s5_bars"), "dynamic": True},
    ]},
    {"group": "06 · Quatre profils", "fields": [
        {"kind": "table", "key": "s6_profiles", "to_df": _pairs_to_df("s6_profiles", ["Profil", "Description"]),
         "from_df": _pairs_from_df("s6_profiles"), "dynamic": True},
    ]},
    {"group": "07 · Enjeux & leviers", "fields": [
        {"kind": "table", "key": "s7_items", "to_df": _pairs_to_df("s7_items", ["Levier", "Description"]),
         "from_df": _pairs_from_df("s7_items"), "dynamic": True},
    ]},
    {"group": "Bas de page", "fields": [
        {"kind": "text", "key": "source", "label": "Source"},
    ]},
]
