#!/usr/bin/env python3
"""templates/theme.py — Charte visuelle v2 (bordeaux / or / crème) et briques
de dessin communes aux nouveaux gabarits.

Les couleurs sont relevées directement sur les maquettes PDF fournies
(er_A4.pdf : bordeaux #700030, or #E09040, crème #FBF8F1). Les primitives bas
niveau (police, mise en forme du texte arabe/latin, graphes matplotlib) sont
importées telles quelles de `poster_engine` : elles prennent la couleur en
paramètre, donc rien n'y est spécifique à l'ancienne palette.
"""

from PIL import Image, ImageDraw

from poster_engine import (  # primitives indépendantes de la palette
    HERE,
    ICONS,
    _figure_to_image,
    _new_figure,
    draw_line,
    font,
    hex_to_rgb,
    make_multi_donut,
    make_multi_line_chart,
    shape,
    text_w,
    wrap,
)

# ==========================================================================
# Palette v2 — relevée sur er_A4.pdf
# ==========================================================================
BURGUNDY = (112, 0, 48)        # #700030 — bordeaux principal (titres, badges, bandes)
BURGUNDY_ALT = (130, 19, 56)   # #821338 — variante (rayures de tableau)
GOLD = (224, 144, 64)          # #E09040 — or/ambre (accents, année, numéros)
GOLD_DEEP = (193, 154, 75)     # #C19A4B — or plus sombre
PAGE = (251, 248, 241)         # #FBF8F1 — fond crème de la page
CARD = (255, 255, 255)         # cartes blanches
CARD_BORDER = (232, 224, 208)  # bordure beige des cartes
INK = (43, 33, 33)             # texte principal (presque noir chaud)
BODY = (74, 66, 64)            # texte de paragraphe
MUTED = (138, 128, 124)        # texte secondaire
WHITE = (255, 255, 255)
TRACK = (233, 226, 212)        # piste claire des barres de progression

# Couleurs des séries (courbes / secteurs) — reprises des maquettes
SERIES_GREEN = "#4E9A50"
SERIES_BLUE = "#3B6FA0"
SERIES_RED = "#C4442E"
SECTOR_COLORS = {
    "Agriculture": (78, 154, 80),
    "Industrie": (224, 144, 64),
    "BTP": (59, 111, 160),
    "Services": (112, 0, 48),
    "Non dét.": (176, 168, 156),
}

F_LOGO = HERE / "hcp_logo.png"


# ==========================================================================
# Briques de dessin
# ==========================================================================
def card(draw, x0, y0, x1, y1, fill=CARD, outline=CARD_BORDER, radius=14, width=1):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


def num_badge(draw, lang, x, y, num, size=30, bg=BURGUNDY, fg=WHITE):
    """Carré arrondi bordeaux avec un numéro blanc (comme les sections des
    maquettes). Retourne x1 = bord droit du badge (pour placer le titre)."""
    draw.rounded_rectangle([x, y, x + size, y + size], radius=7, fill=bg)
    f = font(lang, int(size * 0.52), bold=True)
    t = shape(str(num), lang)
    w = text_w(draw, t, f, lang)
    draw.text((x + size / 2 - w / 2, y + size / 2 - size * 0.32), t, font=f, fill=fg)
    return x + size


def section_title(draw, lang, x, y, num, title, rtl=False, rule_to=None, size=30):
    """En-tête de section : badge numéroté + titre bordeaux majuscule, avec un
    trait fin optionnel qui prolonge jusqu'à `rule_to`. Retourne y du bas."""
    f = font(lang, 17, bold=True)
    if rtl:
        num_badge(draw, lang, x - size, y, num, size=size)
        tx = x - size - 12
        draw_line(draw, tx, y + size / 2 - 11, title, f, BURGUNDY, lang, align="right")
        if rule_to is not None:
            tw = text_w(draw, shape(title, lang), f, lang)
            draw.line([rule_to, y + size / 2, tx - tw - 12, y + size / 2], fill=GOLD, width=2)
    else:
        num_badge(draw, lang, x, y, num, size=size)
        tx = x + size + 12
        draw_line(draw, tx, y + size / 2 - 11, title, f, BURGUNDY, lang, align="left")
        if rule_to is not None:
            tw = text_w(draw, shape(title, lang), f, lang)
            draw.line([tx + tw + 12, y + size / 2, rule_to, y + size / 2], fill=GOLD, width=2)
    return y + size


def paste_logo(img, x_right, y, max_h=64):
    """Colle le logo HCP sur une plaque blanche, bord droit à x_right."""
    if not F_LOGO.exists():
        return 0
    logo = Image.open(F_LOGO).convert("RGBA")
    logo.thumbnail((150, max_h))
    pad = 8
    pw, ph = logo.width + 2 * pad, logo.height + 2 * pad
    plate = Image.new("RGBA", (pw, ph), (255, 255, 255, 255))
    plate.paste(logo, (pad, pad), logo)
    img.paste(plate, (int(x_right - pw), int(y)), plate)
    return pw


# ==========================================================================
# Graphes propres aux nouveaux gabarits
# ==========================================================================
def make_grouped_bars(cats, series_a, series_b, color_a, color_b, width_px=560, height_px=300, lang="fr"):
    """Barres groupées à 2 séries (ex. 2024 vs 2025) avec valeur au-dessus de
    chaque barre. `cats` : libellés d'axe ; series_a/b : listes de valeurs."""
    fig = _new_figure(width_px / 100, height_px / 100)
    ax = fig.add_subplot(111)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    dec = "," if lang != "en" else "."
    n = len(cats)
    xs = list(range(n))
    bw = 0.38
    for i, (vals, col) in enumerate([(series_a, color_a), (series_b, color_b)]):
        offs = [x + (i - 0.5) * bw for x in xs]
        ax.bar(offs, vals, width=bw, color=col, zorder=3)
        for x, v in zip(offs, vals):
            if v is None:
                continue
            ax.annotate(f"{v:.1f}".replace(".", dec), (x, v), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=8.5, color="#2B2121", fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels(cats, color="#5A504C", fontsize=8.5, rotation=25, ha="right")
    ax.tick_params(axis="x", length=0)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#D8CFC0")
    ax.margins(y=0.18)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.28)
    return _figure_to_image(fig)


def sector_donut(values, colors, size_px=150):
    """Donut multi-secteurs (emploi par secteur) — sans texte, le centre est
    rempli par l'appelant."""
    return make_multi_donut(values, colors, size_px=size_px)
