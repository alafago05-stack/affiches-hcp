#!/usr/bin/env python3
"""templates/fiche_situation.py — Fiche 1 : « Situation du marché du travail »
(reproduction fidèle de er_A4.pdf).

Mise en page A4 portrait, deux colonnes :
  en-tête (kicker + logo + titre + année)
  1. Introduction        2. Le glossaire (6 cartes à icônes)
  3. Évolution TA/TE/TC   4. Tableau par sexe et milieu
  5. Chômage par catégorie (2024 vs 2025)   6. Emploi par secteur (3 donuts)
  Indicateurs complémentaires (4 cartes)
  Points saillants (bande bordeaux, 4 colonnes)

Tout le contenu vient du `spec` ; le design est figé. `DEFAULT_SPEC` contient
les valeurs de la maquette (Souss-Massa 2025) et sert de contenu par défaut
pour l'édition (manuelle, Excel ou IA).
"""

import pandas as pd
from PIL import Image, ImageDraw

from poster_engine import draw_line, font, make_multi_line_chart, shape, text_w, wrap
from templates import theme as T

# ==========================================================================
# Contenu par défaut = valeurs de la maquette er_A4.pdf
# ==========================================================================
DEFAULT_SPEC = {
    "kicker": "ENQUÊTE NATIONALE SUR L'EMPLOI",
    "kicker_sub": "( ENE 2025 )",
    "region_dir": "DIRECTION RÉGIONALE DU SOUSS MASSA",
    "title": "SITUATION DU MARCHÉ DU TRAVAIL DANS LA RÉGION SOUSS-MASSA",
    "year_label": "Année",
    "year": "2025",
    "intro": (
        "Le marché du travail dans la région Souss-Massa affiche une amélioration entre 2024 "
        "et 2025, portée par la création d'emplois urbains et la reprise dans les secteurs des "
        "services et de l'agriculture. La baisse du chômage, notamment chez les jeunes et en "
        "milieu rural, reflète une dynamique positive."
    ),
    "glossary": [
        ("group", "Population active", "Ensemble des personnes constituant la main-d'œuvre disponible pour la production de biens et services : les personnes pourvues d'un emploi (actifs occupés) et celles à la recherche d'un emploi (actifs en chômage)."),
        ("briefcase", "Actifs occupés", "Personnes âgées de 7 ans et plus participant à la production de biens et services pendant une brève période de référence, y compris celles temporairement absentes de leur travail."),
        ("person", "Chômeurs", "Personnes âgées de 15 ans et plus déclarant n'avoir pas d'activité professionnelle et qui sont à la recherche d'un emploi."),
        ("clock", "Taux d'activité", "Rapport de la population active (actifs occupés et chômeurs) âgée de 15 ans et plus à la population totale du même groupe d'âge."),
        ("badge", "Taux d'emploi", "Part des actifs occupés (15 ans et plus) dans la population totale du même groupe d'âge."),
        ("document", "Taux de chômage", "Rapport de la population en chômage âgée de 15 ans et plus à la population active du même groupe d'âge."),
    ],
    "trend_title": "ÉVOLUTION DU TAUX D'ACTIVITÉ, DU TAUX D'EMPLOI ET DU TAUX DE CHÔMAGE (2019-2025)",
    "trend_years": ["2019", "2020", "2021", "2022", "2023", "2024", "2025"],
    "trend_series": [
        {"label": "Taux d'activité", "color": T.SERIES_GREEN, "values": [42.9, 41.5, 41.3, 38.3, 39.0, 40.3, 40.4]},
        {"label": "Taux d'emploi", "color": T.SERIES_BLUE, "values": [38.5, 36.6, 36.6, 34.0, 33.7, 35.4, 36.0]},
        {"label": "Taux de chômage", "color": T.SERIES_RED, "values": [10.3, 11.8, 11.3, 11.4, 13.5, 12.3, 11.1]},
    ],
    "table_title": "TAUX D'ACTIVITÉ, D'EMPLOI ET DE CHÔMAGE PAR SEXE ET MILIEU (%)",
    "table_groups": ["Taux d'activité", "Taux d'emploi", "Taux de chômage"],
    "table_subcols": ["Urbain", "Rural", "Ens."],
    "table_rows": [
        ("Masculin", [68.0, 67.0, 67.6, 61.2, 63.1, 61.8, 10.0, 5.7, 8.6]),
        ("Féminin", [17.2, 10.0, 14.7, 12.9, 8.9, 11.5, 25.1, 11.5, 21.8]),
        ("Ensemble", [42.3, 36.8, 40.4, 36.8, 34.4, 36.0, 13.1, 6.6, 11.1]),
    ],
    "cat_title": "CHÔMAGE POUR CERTAINES CATÉGORIES DE LA POPULATION (%)",
    "cat_years": ["2024", "2025"],
    "cat_bars": [
        ("Femmes", 23.0, 21.8), ("15-24 ans", 39.3, 35.0), ("Sans dipl.", 4.5, 3.2),
        ("Diplômés", 18.3, 16.8), ("Urbain", 14.6, 13.1), ("Rural", 7.3, 6.6),
        ("Régional", 12.3, 11.1), ("Maroc", 13.3, 13.0),
    ],
    "sector_title": "EMPLOI PAR SECTEUR D'ACTIVITÉ",
    "sector_legend": ["Agriculture", "Industrie", "BTP", "Services", "Non dét."],
    "sectors": [
        {"milieu": "URBAIN", "dominant": "61,6%", "dominant_label": "Services",
         "values": [5.0, 18.0, 12.0, 61.6, 3.4]},
        {"milieu": "RURAL", "dominant": "47,3%", "dominant_label": "Agri.",
         "values": [47.3, 12.0, 8.0, 30.0, 2.7]},
        {"milieu": "ENSEMBLE", "dominant": "50,5%", "dominant_label": "Services",
         "values": [25.0, 14.0, 8.0, 50.5, 2.5]},
    ],
    "indic_title": "INDICATEURS COMPLÉMENTAIRES (ENSEMBLE)",
    "indicators": [
        ("14,7%", "Taux d'activité des femmes"),
        ("17,7%", "Taux d'activité des jeunes (15-24 ans)"),
        ("9,3%", "Taux de sous-emploi"),
        ("68,3%", "Taux de salariat"),
    ],
    "key_title": "POINTS SAILLANTS",
    "key_points": [
        "Une participation limitée au marché du travail des femmes et des jeunes adultes.",
        "Un taux de chômage qui reste élevé à l'échelle régionale.",
        "Un sous-emploi qui demeure présent parmi les actifs occupés.",
        "Des résultats qui orientent les politiques publiques régionales.",
    ],
    "source": "Source : Haut-Commissariat au Plan — Enquête Nationale sur l'Emploi (ENE), région Souss-Massa, 2025.",
}

W = 1191
MARGIN = 40


def _fmt(v, lang):
    return f"{v:.1f}".replace(".", "," if lang != "en" else ".")


def render(spec: dict, lang: str = "fr", output_path: str = "fiche_situation.png") -> str:
    s = {**DEFAULT_SPEC, **(spec or {})}
    rtl = lang == "ar"
    img = Image.new("RGB", (W, 1780), T.PAGE)
    draw = ImageDraw.Draw(img)
    cw = W - 2 * MARGIN
    y = MARGIN

    # ================= EN-TÊTE =================
    logo_w = T.paste_logo(img, W - MARGIN, y + 2, max_h=58)
    f_kick = font(lang, 15, bold=True)
    draw_line(draw, MARGIN, y, s["kicker"], f_kick, T.BURGUNDY, lang, align="left")
    f_kick2 = font(lang, 13, bold=True)
    draw_line(draw, MARGIN, y + 22, s["kicker_sub"], f_kick2, T.GOLD, lang, align="left")
    f_dir = font(lang, 11, bold=True)
    draw_line(draw, W - MARGIN - logo_w - 14, y + 20, s["region_dir"], f_dir, T.BURGUNDY, lang, align="right")

    ty = y + 66
    f_title = font(lang, 27, bold=True)
    for line in wrap(draw, s["title"], f_title, cw, lang)[:2]:
        draw_line(draw, MARGIN, ty, line, f_title, T.BURGUNDY, lang, align="left")
        ty += 34
    f_yl = font(lang, 20)
    f_yv = font(lang, 22, bold=True)
    draw_line(draw, MARGIN, ty + 2, s["year_label"], f_yl, T.INK, lang, align="left")
    ylw = text_w(draw, shape(s["year_label"], lang), f_yl, lang)
    draw_line(draw, MARGIN + ylw + 12, ty, s["year"], f_yv, T.GOLD, lang, align="left")
    ty += 34
    draw.line([MARGIN, ty, MARGIN + 320, ty], fill=T.GOLD, width=3)
    y = ty + 22

    # ================= 1. INTRODUCTION | 2. GLOSSAIRE =================
    gap = 24
    intro_w = int(cw * 0.30)
    gloss_w = cw - intro_w - gap
    intro_x = MARGIN
    gloss_x = MARGIN + intro_w + gap
    row_top = y

    T.section_title(draw, lang, intro_x, y, 1, "INTRODUCTION", rule_to=intro_x + intro_w)
    iy = y + 42
    f_body = font(lang, 11)
    for line in wrap(draw, s["intro"], f_body, intro_w, lang):
        draw_line(draw, intro_x, iy, line, f_body, T.BODY, lang, align="left")
        iy += 18

    T.section_title(draw, lang, gloss_x, y, 2, "LE GLOSSAIRE", rule_to=gloss_x + gloss_w)
    gy = y + 42
    gcols, grows = 3, 2
    gcgap, grgap = 12, 12
    gcw = (gloss_w - gcgap * (gcols - 1)) / gcols
    gch = 118
    for idx, (icon, term, definition) in enumerate(s["glossary"][:6]):
        r, c = divmod(idx, gcols)
        gx = gloss_x + c * (gcw + gcgap)
        gyy = gy + r * (gch + grgap)
        T.card(draw, gx, gyy, gx + gcw, gyy + gch, radius=10)
        ico = T.ICONS.get(icon)
        if ico:
            ico(draw, gx + 22, gyy + 22, 22, T.GOLD)
        f_term = font(lang, 12, bold=True)
        draw_line(draw, gx + 40, gyy + 12, term, f_term, T.BURGUNDY, lang, align="left")
        f_def = font(lang, 8)
        dyy = gyy + 40
        for line in wrap(draw, definition, f_def, gcw - 24, lang)[:6]:
            draw_line(draw, gx + 12, dyy, line, f_def, T.MUTED, lang, align="left")
            dyy += 11
    y = max(iy, gy + grows * (gch + grgap)) + 20

    # ================= 3. ÉVOLUTION | 4. TABLEAU =================
    left_w = int(cw * 0.44)
    right_w = cw - left_w - gap
    left_x = MARGIN
    right_x = MARGIN + left_w + gap
    sec_top = y

    T.section_title(draw, lang, left_x, y, 3, "ÉVOLUTION DES TROIS TAUX (2019-2025)", size=28)
    ly = y + 40
    # légende
    f_leg = font(lang, 10, bold=True)
    lx = left_x
    for ser in s["trend_series"]:
        col = T.hex_to_rgb(ser["color"])
        draw.ellipse([lx, ly + 2, lx + 11, ly + 13], fill=col)
        draw_line(draw, lx + 16, ly, ser["label"], f_leg, T.INK, lang, align="left")
        lx += 16 + text_w(draw, shape(ser["label"], lang), f_leg, lang) + 20
    chart = make_multi_line_chart(s["trend_series"], s["trend_years"],
                                  width_px=left_w, height_px=210, lang=lang)
    img.paste(chart, (int(left_x), int(ly + 22)), chart)
    left_bottom = ly + 22 + 210

    T.section_title(draw, lang, right_x, y, 4, "TAUX PAR SEXE ET MILIEU (%)", size=28)
    _draw_table(draw, right_x, y + 40, right_w, s, lang)
    y = max(left_bottom, y + 40 + 24 + 4 * 34) + 20

    # ================= 5. CHÔMAGE PAR CATÉGORIE | 6. EMPLOI PAR SECTEUR =================
    T.section_title(draw, lang, left_x, y, 5, "CHÔMAGE PAR CATÉGORIE (%)", size=28)
    f_yr = font(lang, 10, bold=True)
    lx = left_x
    for yr, col in zip(s["cat_years"], (T.GOLD, T.BURGUNDY)):
        draw.rectangle([lx, y + 42, lx + 12, y + 54], fill=col)
        draw_line(draw, lx + 16, y + 42, yr, f_yr, T.INK, lang, align="left")
        lx += 60
    cats = [c[0] for c in s["cat_bars"]]
    v2024 = [c[1] for c in s["cat_bars"]]
    v2025 = [c[2] for c in s["cat_bars"]]
    bars = T.make_grouped_bars(cats, v2024, v2025, "#E09040", "#700030",
                               width_px=left_w, height_px=250, lang=lang)
    img.paste(bars, (int(left_x), int(y + 62)), bars)

    T.section_title(draw, lang, right_x, y, 6, "EMPLOI PAR SECTEUR D'ACTIVITÉ", size=28)
    _draw_sectors(img, draw, right_x, y + 46, right_w, s, lang)
    y = max(y + 62 + 250, y + 46 + 240) + 18

    # ================= INDICATEURS COMPLÉMENTAIRES =================
    draw.rectangle([MARGIN, y + 2, MARGIN + 6, y + 26], fill=T.GOLD)
    f_ind = font(lang, 15, bold=True)
    draw_line(draw, MARGIN + 16, y + 3, s["indic_title"], f_ind, T.BURGUNDY, lang, align="left")
    y += 40
    n = len(s["indicators"])
    icw = (cw - 14 * (n - 1)) / n
    for i, (val, lbl) in enumerate(s["indicators"]):
        ix = MARGIN + i * (icw + 14)
        T.card(draw, ix, y, ix + icw, y + 76, radius=10)
        draw.rectangle([ix, y, ix + icw, y + 4], fill=T.GOLD)
        f_v = font(lang, 24, bold=True)
        draw_line(draw, ix + 14, y + 14, val, f_v, T.BURGUNDY, lang, align="left")
        f_l = font(lang, 9, bold=True)
        lyy = y + 48
        for line in wrap(draw, lbl, f_l, icw - 24, lang)[:2]:
            draw_line(draw, ix + 14, lyy, line, f_l, T.MUTED, lang, align="left")
            lyy += 11
    y += 76 + 20

    # ================= POINTS SAILLANTS =================
    kp = s["key_points"]
    band_h = 118
    T.card(draw, MARGIN, y, W - MARGIN, y + band_h, fill=T.BURGUNDY, outline=T.BURGUNDY, radius=14)
    T.num_badge(draw, lang, MARGIN + 18, y + 16, "", size=28, bg=T.GOLD)  # petit carré or décoratif
    f_kt = font(lang, 15, bold=True)
    draw_line(draw, MARGIN + 56, y + 20, s["key_title"], f_kt, T.WHITE, lang, align="left")
    kn = len(kp)
    kcw = (cw - 32 - 16 * (kn - 1)) / kn
    ky = y + 56
    for i, txt in enumerate(kp):
        kx = MARGIN + 16 + i * (kcw + 16)
        draw.rectangle([kx, ky, kx + kcw, ky + 2], fill=T.GOLD)
        f_num = font(lang, 20, bold=True)
        draw_line(draw, kx, ky + 8, f"0{i + 1}", f_num, T.GOLD, lang, align="left")
        f_txt = font(lang, 9)
        tyy = ky + 34
        for line in wrap(draw, txt, f_txt, kcw - 4, lang)[:5]:
            draw_line(draw, kx, tyy, line, f_txt, (233, 222, 214), lang, align="left")
            tyy += 12
    y += band_h + 16

    # ================= SOURCE =================
    f_src = font(lang, 9)
    draw_line(draw, W / 2, y, s["source"], f_src, T.MUTED, lang, align="center")
    y += 18

    img = img.crop((0, 0, W, int(y + MARGIN / 2)))
    img.save(output_path)
    return output_path


def _draw_table(draw, x, y, w, s, lang):
    """Tableau par sexe × milieu : 1 col libellé + 3 groupes × 3 sous-cols."""
    rows = s["table_rows"]
    groups = s["table_groups"]
    subcols = s["table_subcols"]
    label_w = w * 0.16
    grp_w = (w - label_w) / len(groups)
    sub_w = grp_w / len(subcols)
    h1, h2, rh = 24, 22, 34
    # entête groupe
    draw.rectangle([x, y, x + w, y + h1], fill=T.BURGUNDY)
    f_h = font(lang, 9, bold=True)
    draw_line(draw, x + label_w / 2, y + 5, "Sexe", f_h, T.WHITE, lang, align="center")
    for gi, g in enumerate(groups):
        gx = x + label_w + gi * grp_w
        draw_line(draw, gx + grp_w / 2, y + 5, g, f_h, T.WHITE, lang, align="center")
    # entête sous-colonnes
    y2 = y + h1
    draw.rectangle([x, y2, x + w, y2 + h2], fill=T.BURGUNDY_ALT)
    f_s = font(lang, 8, bold=True)
    for gi in range(len(groups)):
        for si, sc in enumerate(subcols):
            sx = x + label_w + gi * grp_w + si * sub_w
            draw_line(draw, sx + sub_w / 2, y2 + 5, sc, f_s, T.WHITE, lang, align="center")
    # lignes
    ry = y2 + h2
    f_c = font(lang, 10)
    for ri, (name, vals) in enumerate(rows):
        bg = (247, 242, 234) if ri % 2 == 0 else T.CARD
        bold = name.lower().startswith("ensemble")
        draw.rectangle([x, ry, x + w, ry + rh], fill=(244, 236, 224) if bold else bg)
        f_name = font(lang, 10, bold=True)
        draw_line(draw, x + 10, ry + rh / 2 - 7, name, f_name, T.BURGUNDY if bold else T.INK, lang, align="left")
        f_val = font(lang, 10, bold=bold)
        for ci, v in enumerate(vals):
            cx = x + label_w + ci * sub_w
            draw_line(draw, cx + sub_w / 2, ry + rh / 2 - 7, _fmt(v, lang), f_val, T.INK, lang, align="center")
        ry += rh
    draw.rounded_rectangle([x, y, x + w, ry], radius=8, outline=T.CARD_BORDER, width=1)


def _draw_sectors(img, draw, x, y, w, s, lang):
    """3 donuts (Urbain / Rural / Ensemble) + légende commune."""
    sectors = s["sectors"]
    n = len(sectors)
    dsize = 120
    slot = w / n
    colors = [T.SECTOR_COLORS.get(k, (160, 160, 160)) for k in s["sector_legend"]]
    hexcols = ["#%02X%02X%02X" % c for c in colors]
    for i, sec in enumerate(sectors):
        cx = x + i * slot + slot / 2
        donut = T.sector_donut(sec["values"], hexcols, size_px=dsize)
        img.paste(donut, (int(cx - dsize / 2), int(y)), donut)
        f_c = font(lang, 12, bold=True)
        draw_line(draw, cx, y + dsize / 2 - 16, sec["dominant"], f_c, T.BURGUNDY, lang, align="center")
        f_cl = font(lang, 8)
        draw_line(draw, cx, y + dsize / 2 + 2, sec["dominant_label"], f_cl, T.MUTED, lang, align="center")
        f_m = font(lang, 10, bold=True)
        draw_line(draw, cx, y + dsize + 4, sec["milieu"], f_m, T.INK, lang, align="center")
    # légende
    ly = y + dsize + 26
    f_l = font(lang, 9)
    total_txt = sum(text_w(draw, shape(k, lang), f_l, lang) + 26 for k in s["sector_legend"])
    lx = x + (w - total_txt) / 2
    for k, col in zip(s["sector_legend"], colors):
        draw.ellipse([lx, ly, lx + 11, ly + 11], fill=col)
        draw_line(draw, lx + 16, ly - 2, k, f_l, T.BODY, lang, align="left")
        lx += 26 + text_w(draw, shape(k, lang), f_l, lang)


# ==========================================================================
# Schéma d'édition — décrit les champs modifiables et comment les convertir
# en/depuis un DataFrame (pour st.data_editor). Consommé par fiche_editor.py.
# Convertisseurs : to_df(spec) -> DataFrame ; from_df(df, spec) -> valeur.
# ==========================================================================
def _gloss_to_df(spec):
    return pd.DataFrame([list(x) for x in spec["glossary"]], columns=["Icône", "Terme", "Définition"])


def _gloss_from_df(df, spec):
    return [(str(r["Icône"]).strip() or "document", str(r["Terme"]), str(r["Définition"]))
            for _, r in df.iterrows() if str(r["Terme"]).strip()]


def _indic_to_df(spec):
    return pd.DataFrame([list(x) for x in spec["indicators"]], columns=["Valeur", "Libellé"])


def _indic_from_df(df, spec):
    return [(str(r["Valeur"]), str(r["Libellé"])) for _, r in df.iterrows() if str(r["Valeur"]).strip()]


def _kp_to_df(spec):
    return pd.DataFrame({"Point saillant": list(spec["key_points"])})


def _kp_from_df(df, spec):
    return [str(x) for x in df["Point saillant"].tolist() if str(x).strip() and str(x) != "nan"]


def _num(v, default=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _trend_to_df(spec):
    years = spec["trend_years"]
    data = {"Indicateur": [s["label"] for s in spec["trend_series"]]}
    for i, y in enumerate(years):
        data[y] = [s["values"][i] if i < len(s["values"]) else None for s in spec["trend_series"]]
    return pd.DataFrame(data)


def _trend_from_df(df, spec):
    years = spec["trend_years"]
    series = []
    for i, (_, r) in enumerate(df.iterrows()):
        base = spec["trend_series"][i] if i < len(spec["trend_series"]) else {"color": T.SERIES_GREEN}
        series.append({"label": str(r["Indicateur"]), "color": base.get("color", T.SERIES_GREEN),
                       "values": [_num(r[y]) for y in years]})
    return series


_TBL_COLS = ["TA·Urb", "TA·Rur", "TA·Ens", "TE·Urb", "TE·Rur", "TE·Ens", "TC·Urb", "TC·Rur", "TC·Ens"]


def _tbl_to_df(spec):
    return pd.DataFrame([[name] + list(vals) for name, vals in spec["table_rows"]],
                        columns=["Sexe"] + _TBL_COLS)


def _tbl_from_df(df, spec):
    return [(str(r["Sexe"]), [_num(r[c]) for c in _TBL_COLS]) for _, r in df.iterrows()]


def _cat_to_df(spec):
    y0, y1 = spec["cat_years"]
    return pd.DataFrame([[c[0], c[1], c[2]] for c in spec["cat_bars"]], columns=["Catégorie", y0, y1])


def _cat_from_df(df, spec):
    y0, y1 = spec["cat_years"]
    return [(str(r["Catégorie"]), _num(r[y0]), _num(r[y1])) for _, r in df.iterrows() if str(r["Catégorie"]).strip()]


_SEC_SEG = ["Agriculture", "Industrie", "BTP", "Services", "Non dét."]


def _sec_to_df(spec):
    return pd.DataFrame([[s["milieu"], s["dominant"], s["dominant_label"]] + list(s["values"])
                         for s in spec["sectors"]],
                        columns=["Milieu", "% dominant", "Libellé dom."] + _SEC_SEG)


def _sec_from_df(df, spec):
    return [{"milieu": str(r["Milieu"]), "dominant": str(r["% dominant"]),
             "dominant_label": str(r["Libellé dom."]), "values": [_num(r[c]) for c in _SEC_SEG]}
            for _, r in df.iterrows()]


EDIT_SCHEMA = [
    {"group": "En-tête", "fields": [
        {"kind": "text", "key": "kicker", "label": "Kicker (nom de l'enquête)"},
        {"kind": "text", "key": "kicker_sub", "label": "Sous-kicker"},
        {"kind": "text", "key": "region_dir", "label": "Direction régionale"},
        {"kind": "textarea", "key": "title", "label": "Titre principal"},
        {"kind": "text", "key": "year", "label": "Année"},
    ]},
    {"group": "1 · Introduction", "fields": [
        {"kind": "textarea", "key": "intro", "label": "Texte d'introduction"},
    ]},
    {"group": "2 · Glossaire", "fields": [
        {"kind": "table", "key": "glossary", "to_df": _gloss_to_df, "from_df": _gloss_from_df, "dynamic": True},
    ]},
    {"group": "3 · Évolution (valeurs de la courbe)", "fields": [
        {"kind": "table", "key": "trend_series", "to_df": _trend_to_df, "from_df": _trend_from_df, "dynamic": False},
    ]},
    {"group": "4 · Tableau par sexe et milieu", "fields": [
        {"kind": "table", "key": "table_rows", "to_df": _tbl_to_df, "from_df": _tbl_from_df, "dynamic": False},
    ]},
    {"group": "5 · Chômage par catégorie", "fields": [
        {"kind": "table", "key": "cat_bars", "to_df": _cat_to_df, "from_df": _cat_from_df, "dynamic": True},
    ]},
    {"group": "6 · Emploi par secteur", "fields": [
        {"kind": "table", "key": "sectors", "to_df": _sec_to_df, "from_df": _sec_from_df, "dynamic": False},
    ]},
    {"group": "Indicateurs complémentaires", "fields": [
        {"kind": "table", "key": "indicators", "to_df": _indic_to_df, "from_df": _indic_from_df, "dynamic": True},
    ]},
    {"group": "Points saillants", "fields": [
        {"kind": "table", "key": "key_points", "to_df": _kp_to_df, "from_df": _kp_from_df, "dynamic": True},
    ]},
    {"group": "Bas de page", "fields": [
        {"kind": "text", "key": "source", "label": "Source"},
    ]},
]

LANG = "fr"  # cette fiche est en français
PDF_REF = "er_A4.pdf"
LABEL = "Situation du marché du travail"
