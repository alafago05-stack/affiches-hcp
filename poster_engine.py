#!/usr/bin/env python3
"""poster_engine.py — Briques visuelles communes aux 4 générateurs d'affiches HCP.

Port fidèle de `generate_affiche.py` (v4, référence faisant foi pour la
palette, la structure des sections et le schéma de `spec`) dans
l'architecture modulaire de l'application Streamlit. Rien n'est réinterprété
ici : la palette, les fonctions de dessin et les "builders" de spec sont
repris tels quels ; seul le découpage en fichiers change.

Depuis la maquette HTML de juillet 2026 (« Souss-Massa standalone »), l'ordre
et le style des sections suivent le nouveau design : police IBM Plex Sans
Arabic, introduction + lexique d'abord, répartition en ARBRE (carte totale
avec anneau → boîtes marine force/hors force → cartes feuilles), puis les
3 taux essentiels dans une carte titrée. L'arbre est volontairement
simplifié par rapport à la maquette : les nœuds « main-d'œuvre potentielle »,
« chômeurs au sens étroit » et « sous-emploi horaire » n'existent pas dans
l'export Excel ENE actuel (choix validé — ne pas inventer de données).

Le rendu d'une affiche se fait toujours en 3 étapes, dans cet ordre :

  1. `render_fixed_header_zone(spec, lang)` — en-tête (pastille + titre +
     logo), introduction + lexique côte à côte, répartition de la population
     (arbre), les 3 taux essentiels en anneaux (carte titrée). Structure
     identique quel que soit le type d'affiche ; SEULE fonction qui dessine
     ces 4 blocs, les 4 types d'affiche (posters/*.py) l'appellent sans la
     dupliquer.
  2. Une zone flexible propre à chaque type :
       - `render_flexible_standard(...)` (Type 1) — indicateurs complémentaires.
       - `render_flexible_trend(...)` (Type 2, comparatif années) — courbes.
       - `render_flexible_compare(...)` (Types 3 et 4, comparatif jihat /
         trimestres) — barres comparatives entre 2 à 4 entités.
     Les 3 terminent par les "points saillants" (fonction partagée
     `_render_key_points`).
  3. `finalize(...)` — ligne de source + recadrage + sauvegarde du PNG.

Les modules `posters/*.py` construisent un `spec` (dict Python) à partir de
données déjà parsées (voir `parsers/annual.py`), puis enchaînent ces 3
appels dans leur propre fonction `render(spec, lang, output_path)`.
"""

from pathlib import Path

from openpyxl import load_workbook  # noqa: F401  (ré-exporté pour compat des parsers)
from PIL import Image, ImageDraw, ImageFont

import matplotlib

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_ARABIC_FALLBACK_LIBS = True
except ImportError:
    HAS_ARABIC_FALLBACK_LIBS = False

try:
    from fontTools.ttLib import TTFont
    _HAS_FONTTOOLS = True
except ImportError:
    _HAS_FONTTOOLS = False

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from parsers.annual import (
    format_number,
    get_rate,
    get_value,
    resolve_salariat_title,
    resolve_working_age_title,
)

HERE = Path(__file__).parent

# ==========================================================================
# 1. PALETTE / POLICES — thème clair crème / marine / vert olive
# ==========================================================================

BG = (233, 230, 218)            # fond extérieur (#E9E6DA)
PAGE = (247, 245, 236)          # fond de la fiche (#F7F5EC)
INK = (22, 50, 63)              # marine foncé — en-têtes, boîtes pleines (#16323F)
CARD = (255, 255, 255)          # cartes blanches (#FFFFFF)
CARD_ALT = (247, 245, 236)      # variante claire (#F7F5EC, glossaire/indicateurs)
CARD_BORDER = (228, 224, 210)   # bordure fine des cartes (#E4E0D2)
TRACK = (228, 224, 210)

TEXT = (34, 48, 56)             # texte principal (#223038)
TEXT_BODY = (68, 82, 90)        # texte de paragraphe (#44525A)
MUTED = (90, 104, 112)          # texte secondaire (#5A6870)
MUTED_ON_DARK = (157, 179, 188) # texte secondaire sur fond marine (#9DB3BC)
LIGHT_ON_DARK = (199, 210, 216) # texte clair sur fond marine (#C7D2D8)
KEYPOINTS_TEXT = (213, 222, 226)  # texte des points saillants (#D5DEE2)
WHITE = (255, 255, 255)

GREEN = (163, 181, 32)          # accent principal — olive (#A3B520)
GREEN_DARK = (126, 143, 20)     # accent au survol / plus profond (#7E8F14)
GOLD = (232, 161, 60)           # or/ambre — anneau chômage (#E8A13C)
CORAL = (196, 74, 62)           # rouge — baisse (delta négatif)

NAVY_DARK = INK  # alias conservé pour compatibilité interne
GREY = MUTED     # alias conservé pour compatibilité interne
CREAM = PAGE     # alias conservé pour compatibilité interne

def _font_path(preferred: str, fallback: str) -> str:
    """Chemin d'une police avec repli : IBM Plex Sans Arabic (la police du
    nouveau design HTML, qui couvre aussi le latin) si présente dans fonts/,
    sinon l'ancienne police (DejaVu / Noto) pour ne jamais planter."""
    p = HERE / "fonts" / preferred
    return str(p) if p.exists() else str(HERE / "fonts" / fallback)


F_LATIN_REG = _font_path("IBMPlexSansArabic-Regular.ttf", "DejaVuSans.ttf")
F_LATIN_BOLD = _font_path("IBMPlexSansArabic-Bold.ttf", "DejaVuSans-Bold.ttf")
F_AR_REG = _font_path("IBMPlexSansArabic-Regular.ttf", "NotoSansArabic-Regular.ttf")
F_AR_BOLD = _font_path("IBMPlexSansArabic-Bold.ttf", "NotoSansArabic-Bold.ttf")


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _detect_raqm():
    """Teste si Pillow dispose du moteur Raqm (nécessaire pour lier les
    lettres arabes nativement). Sur certains PC Windows, Pillow est installé
    sans cette option : on doit alors utiliser une solution de repli."""
    try:
        img = Image.new("RGB", (10, 10))
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(F_LATIN_REG, 10, layout_engine=ImageFont.Layout.RAQM)
        d.textbbox((0, 0), "test", font=f, direction="ltr")
        return True
    except Exception:
        return False


HAS_RAQM = _detect_raqm()


def font(lang, size, bold=False):
    """Charge la police. Utilise le moteur Raqm (HarfBuzz) s'il est
    disponible, pour lier correctement les lettres arabes ; sinon, se rabat
    sur le moteur de base (le texte arabe est alors pré-formé manuellement,
    voir shape())."""
    if lang == "ar":
        path = F_AR_BOLD if bold else F_AR_REG
    else:
        path = F_LATIN_BOLD if bold else F_LATIN_REG
    if HAS_RAQM:
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.truetype(path, size)


def _direction(lang):
    return "rtl" if lang == "ar" else "ltr"


def shape(text, lang):
    """Avec Raqm : ne fait rien (Raqm gère la liaison des lettres et le sens
    de lecture au moment du dessin). Sans Raqm : reshape + bidi manuels,
    indispensables pour un rendu arabe correct."""
    text = str(text) if text is not None else ""
    if lang == "ar" and not HAS_RAQM and HAS_ARABIC_FALLBACK_LIBS and text:
        return get_display(arabic_reshaper.reshape(text))
    return text


# ---- repli par police mixte (Latin) pour le texte arabe sans Raqm ----
# Sans Raqm, Pillow ne fait pas de repli de police automatique : un caractère
# absent de NotoSansArabic (ex. '%', '/', un tiret cadratin, une lettre
# latine) s'affiche en carré vide au lieu d'utiliser la police latine. On
# reproduit manuellement ce que Raqm ferait, uniquement pour le texte arabe
# rendu sans Raqm.

_CMAP_CACHE = {}


def _font_cmap(path):
    if not _HAS_FONTTOOLS:
        return None
    if path not in _CMAP_CACHE:
        try:
            _CMAP_CACHE[path] = TTFont(path, lazy=True).getBestCmap() or {}
        except Exception:
            _CMAP_CACHE[path] = {}
    return _CMAP_CACHE[path]


_FALLBACK_FONT_CACHE = {}


def _latin_fallback_for(fnt):
    bold = getattr(fnt, "path", None) == F_AR_BOLD
    key = (bold, fnt.size)
    if key not in _FALLBACK_FONT_CACHE:
        path = F_LATIN_BOLD if bold else F_LATIN_REG
        _FALLBACK_FONT_CACHE[key] = ImageFont.truetype(path, fnt.size)
    return _FALLBACK_FONT_CACHE[key]


def _needs_mixed_fallback(lang, fnt):
    return lang == "ar" and not HAS_RAQM and getattr(fnt, "path", None) in (F_AR_REG, F_AR_BOLD)


def _split_runs(text, fnt):
    cmap = _font_cmap(fnt.path)
    if not cmap:
        return [(text, fnt)]
    fallback = _latin_fallback_for(fnt)
    runs, cur_font, cur_text = [], fnt, ""
    for ch in text:
        use_fallback = ch != " " and ord(ch) not in cmap
        chosen = fallback if use_fallback else fnt
        if chosen is cur_font:
            cur_text += ch
        else:
            if cur_text:
                runs.append((cur_text, cur_font))
            cur_font, cur_text = chosen, ch
    if cur_text:
        runs.append((cur_text, cur_font))
    return runs


def text_w(draw, text, fnt, lang="fr"):
    if HAS_RAQM:
        b = draw.textbbox((0, 0), text, font=fnt, direction=_direction(lang))
        return b[2] - b[0]
    if _needs_mixed_fallback(lang, fnt):
        total = 0
        for seg, f in _split_runs(text, fnt):
            b = draw.textbbox((0, 0), seg, font=f)
            total += b[2] - b[0]
        return total
    b = draw.textbbox((0, 0), text, font=fnt)
    return b[2] - b[0]


def wrap(draw, text, fnt, max_width, lang="fr"):
    """Découpe `text` (texte brut, non transformé) en lignes qui tiennent dans
    max_width. Les lignes retournées restent en texte brut : c'est draw_line()
    qui applique le reshape/bidi juste avant le dessin, une seule fois."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if text_w(draw, shape(test, lang), fnt, lang) <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_line(draw, x, y, text, fnt, fill, lang, align="left"):
    """Dessine une ligne de texte à la position x selon align."""
    text = shape(text, lang)
    w = text_w(draw, text, fnt, lang)
    if align == "right":
        x0 = x - w
    elif align == "center":
        x0 = x - w / 2
    else:
        x0 = x
    if HAS_RAQM:
        draw.text((x0, y), text, font=fnt, fill=fill, direction=_direction(lang))
        return
    if _needs_mixed_fallback(lang, fnt):
        cx = x0
        base_ascent, _ = fnt.getmetrics()
        for seg, f in _split_runs(text, fnt):
            seg_ascent, _ = f.getmetrics()
            seg_y = y + (base_ascent - seg_ascent) if f is not fnt else y
            draw.text((cx, seg_y), seg, font=f, fill=fill)
            b = draw.textbbox((0, 0), seg, font=f)
            cx += b[2] - b[0]
        return
    draw.text((x0, y), text, font=fnt, fill=fill)


# ==========================================================================
# 2. ICÔNES
# ==========================================================================

def icon_briefcase(draw, cx, cy, s, color):
    w, h = s, s * 0.7
    draw.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=s * 0.08, outline=color, width=3)
    draw.rounded_rectangle([cx - w * 0.22, cy - h / 2 - s * 0.18, cx + w * 0.22, cy - h / 2], radius=s * 0.05, outline=color, width=3)
    draw.line([cx - w / 2, cy, cx + w / 2, cy], fill=color, width=3)


def icon_person(draw, cx, cy, s, color):
    r = s * 0.22
    draw.ellipse([cx - r, cy - s * 0.45, cx + r, cy - s * 0.45 + 2 * r], outline=color, width=3)
    draw.arc([cx - s * 0.32, cy - s * 0.05, cx + s * 0.32, cy + s * 0.6], 200, 340, fill=color, width=3)


def icon_group(draw, cx, cy, s, color):
    icon_person(draw, cx - s * 0.22, cy, s * 0.75, color)
    icon_person(draw, cx + s * 0.22, cy, s * 0.75, color)


def icon_clock(draw, cx, cy, s, color):
    r = s * 0.4
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
    draw.line([cx, cy, cx, cy - r * 0.6], fill=color, width=3)
    draw.line([cx, cy, cx + r * 0.4, cy], fill=color, width=3)


def icon_badge(draw, cx, cy, s, color):
    r = s * 0.32
    draw.ellipse([cx - r, cy - r * 1.3, cx + r, cy + r * 0.7], outline=color, width=3)
    draw.polygon([(cx - r * 0.5, cy + r * 0.3), (cx - r * 0.15, cy + r * 1.1), (cx, cy + r * 0.6),
                  (cx + r * 0.15, cy + r * 1.1), (cx + r * 0.5, cy + r * 0.3)], outline=color, width=2)


def icon_heart(draw, cx, cy, s, color):
    r = s * 0.22
    draw.ellipse([cx - 2 * r, cy - r * 0.7, cx, cy + r * 0.9], outline=color, width=3)
    draw.ellipse([cx, cy - r * 0.7, cx + 2 * r, cy + r * 0.9], outline=color, width=3)
    draw.polygon([(cx - 2 * r * 0.9, cy + r * 0.4), (cx, cy + r * 1.7), (cx + 2 * r * 0.9, cy + r * 0.4)], outline=color, width=3)


def icon_shield(draw, cx, cy, s, color):
    w, h = s * 0.5, s * 0.62
    draw.polygon([
        (cx - w, cy - h * 0.7), (cx, cy - h), (cx + w, cy - h * 0.7),
        (cx + w, cy + h * 0.2), (cx, cy + h), (cx - w, cy + h * 0.2),
    ], outline=color, width=3)
    draw.line([cx - w * 0.4, cy, cx - w * 0.1, cy + h * 0.3], fill=color, width=3)
    draw.line([cx - w * 0.1, cy + h * 0.3, cx + w * 0.4, cy - h * 0.3], fill=color, width=3)


def icon_document(draw, cx, cy, s, color):
    w, h = s * 0.42, s * 0.58
    draw.rounded_rectangle([cx - w, cy - h, cx + w, cy + h], radius=4, outline=color, width=3)
    for i in range(3):
        ly = cy - h * 0.35 + i * h * 0.4
        draw.line([cx - w * 0.55, ly, cx + w * 0.55, ly], fill=color, width=2)


ICONS = {"briefcase": icon_briefcase, "person": icon_person, "group": icon_group,
         "clock": icon_clock, "badge": icon_badge, "heart": icon_heart,
         "shield": icon_shield, "document": icon_document}


def _new_figure(width_in, height_in, dpi=100):
    """Crée une Figure via l'API objet directe (Figure + FigureCanvasAgg),
    sans passer par l'état global de `matplotlib.pyplot`. `pyplot` (plt.subplots
    / plt.close) n'est pas thread-safe : sous Streamlit, qui exécute le script
    dans son propre thread à chaque interaction, enchaîner plusieurs figures
    (donuts + courbes) dans un même rendu pouvait faire planter le canvas
    ('FigureCanvasBase' object has no attribute 'buffer_rgba'). L'API objet
    est le pattern recommandé par matplotlib pour un usage serveur/threadé."""
    fig = Figure(figsize=(width_in, height_in), dpi=dpi)
    FigureCanvasAgg(fig)
    return fig


def _figure_to_image(fig):
    canvas = fig.canvas
    canvas.draw()
    buf = canvas.buffer_rgba()
    return Image.frombuffer("RGBA", canvas.get_width_height(), buf, "raw", "RGBA", 0, 1).copy()


def make_donut(value_pct, color, size_px=260):
    # Garde-fou : matplotlib refuse les tailles de secteur négatives ("Wedge
    # sizes 'x' must be non negative") et un taux > 100 % déborderait
    # l'anneau — on borne à [0, 100]. La validation en amont
    # (validate_blocks) signale de toute façon ces valeurs suspectes.
    value_pct = min(100.0, max(0.0, value_pct if value_pct is not None else 0.0))
    fig = _new_figure(size_px / 100, size_px / 100)
    ax = fig.add_subplot(111)
    remainder = max(0, 100 - value_pct)
    ax.pie([value_pct, remainder], colors=[color, "#E7EAD8"], startangle=90,
           counterclock=False, wedgeprops=dict(width=0.28, edgecolor="#FFFFFF", linewidth=1))
    ax.set_aspect("equal")
    fig.patch.set_alpha(0)
    fig.subplots_adjust(0, 0, 1, 1)
    return _figure_to_image(fig)


def make_multi_donut(values, colors, size_px=300):
    # Même garde-fou que make_donut : pas de secteur négatif.
    values = [max(0.0, v if v is not None else 0.0) for v in values]
    fig = _new_figure(size_px / 100, size_px / 100)
    ax = fig.add_subplot(111)
    ax.pie(values, colors=colors, startangle=90, counterclock=False,
           wedgeprops=dict(width=0.35, edgecolor="#FFFFFF", linewidth=2))
    ax.set_aspect("equal")
    fig.patch.set_alpha(0)
    fig.subplots_adjust(0, 0, 1, 1)
    return _figure_to_image(fig)


def make_line_chart(years, values, color, width_px=1000, height_px=280, lang="fr"):
    """Courbe d'évolution annuelle (ligne + marqueurs + étiquettes de valeur
    à chaque point), utilisée par la zone flexible du Type 2 (comparatif
    années)."""
    fig = _new_figure(width_px / 100, height_px / 100)
    ax = fig.add_subplot(111)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    xs = list(range(len(years)))
    ax.plot(xs, values, color=color, linewidth=2.5, marker="o",
             markersize=7, markerfacecolor=color, markeredgecolor="#FFFFFF", markeredgewidth=1.5, zorder=3)

    vmin, vmax = min(values), max(values)
    span = max(vmax - vmin, 1)
    for x, v in zip(xs, values):
        offset = span * 0.10
        label = f"{v:.1f}".replace(".", "," if lang != "en" else ".")
        ax.annotate(label, (x, v), textcoords="offset points", xytext=(0, 12 if v >= (vmin + vmax) / 2 else -18),
                    ha="center", fontsize=11, color="#0D3047", fontweight="bold")

    ax.set_xticks(xs)
    ax.set_xticklabels([str(y) for y in years], color="#6E767E", fontsize=10)
    ax.tick_params(axis="x", length=0)
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#C7CEB8")
    ax.margins(x=0.06, y=0.35)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.88, bottom=0.18)

    return _figure_to_image(fig)


def make_multi_line_chart(series, years, width_px=1120, height_px=320, lang="fr"):
    """Superpose plusieurs courbes (TA/TE/TC) dans un SEUL graphe, sur un axe
    des années commun. `series` : liste de {color, values} où `values` est
    aligné sur `years` (None = point manquant, la ligne se coupe). Chaque
    courbe est étiquetée seulement à ses extrémités (valeur de départ et
    d'arrivée, dans la couleur de la série) pour rester lisible malgré la
    superposition — la légende (dessinée dans l'affiche) rappelle les libellés."""
    fig = _new_figure(width_px / 100, height_px / 100)
    ax = fig.add_subplot(111)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    dec = "," if lang != "en" else "."
    xs = list(range(len(years)))

    if not any(v is not None for s in series for v in s["values"]):
        return _figure_to_image(fig)

    for s in series:
        color = s["color"]
        ys = [v if v is not None else float("nan") for v in s["values"]]
        ax.plot(xs, ys, color=color, linewidth=2.6, marker="o", markersize=6,
                markerfacecolor=color, markeredgecolor="#FFFFFF", markeredgewidth=1.4, zorder=3)
        pts = [(x, v) for x, v in zip(xs, s["values"]) if v is not None]
        if not pts:
            continue
        ends = (pts[0], pts[-1]) if len(pts) > 1 else (pts[0],)
        for j, (x, v) in enumerate(ends):
            is_first = j == 0 and len(pts) > 1
            ax.annotate(f"{v:.1f}".replace(".", dec), (x, v), textcoords="offset points",
                        xytext=(-8 if is_first else 8, 9), ha="right" if is_first else "left",
                        fontsize=10.5, color=color, fontweight="bold", zorder=4)

    ax.set_xticks(xs)
    ax.set_xticklabels([str(y) for y in years], color="#6E767E", fontsize=10)
    ax.tick_params(axis="x", length=0)
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#C7CEB8")
    ax.margins(x=0.07, y=0.26)
    fig.subplots_adjust(left=0.05, right=0.95, top=0.93, bottom=0.15)

    return _figure_to_image(fig)


# ==========================================================================
# 3. TRADUCTIONS
# ==========================================================================

STRINGS = {
    "fr": {
        "intro_title": "Introduction",
        "lexique_title": "Lexique",
        "breakdown_title": "Répartition de la population en âge de travailler",
        "notes_title": "Points clés",
    },
    "en": {
        "intro_title": "Introduction",
        "lexique_title": "Glossary",
        "breakdown_title": "Breakdown of the working-age population",
        "notes_title": "Key takeaways",
    },
    "ar": {
        "intro_title": "مقدمة",
        "lexique_title": "المعجم",
        "breakdown_title": "توزيع الساكنة في سن النشاط",
        "notes_title": "أهم النقاط",
    },
}

# Contenu générique partagé par les 4 types d'affiche (pastille, 3 taux
# essentiels, lexique, répartition, indicateurs complémentaires, points
# saillants). Seuls title/subtitle/intro varient réellement par type — voir
# COMPARE_I18N pour les variantes des types 2/3/4.
DEMO_I18N = {
    "fr": {
        "kicker": "Enquête Nationale sur l'Emploi (ENE 2025)",
        "title": "Marché du travail dans la région Souss-Massa — année 2025",
        "subtitle": "Haut-Commissariat au Plan — Direction régionale de Souss-Massa",
        "rate_activity": "Taux d'activité",
        "rate_activity_sub": "Force de travail parmi la population en âge d'activité",
        "rate_employment": "Taux d'emploi",
        "rate_employment_sub": "Personnes en emploi parmi la population en âge d'activité",
        "rate_unemployment": "Taux de chômage",
        "rate_unemployment_sub": "Chômeurs parmi la force de travail",
        "intro_title": "Introduction",
        "intro": "Cette note présente les principaux résultats de l'Enquête Nationale sur l'Emploi pour la région Souss-Massa au titre de l'année 2025 : activité, emploi et chômage. Toutes les données portent sur l'ensemble de la population (milieux urbain et rural confondus).",
        "glossary_title": "Lexique",
        "glossary": [
            ("Emploi contre revenu", "Travail effectué contre un salaire ou un profit."),
            ("Taux d'activité", "Part de la force de travail dans la population en âge d'activité."),
            ("Taux d'emploi", "Part des personnes en emploi dans la population en âge d'activité."),
            ("Taux de chômage", "Part des chômeurs dans la force de travail."),
            ("Sous-emploi", "Actifs occupés souhaitant et disponibles à travailler davantage."),
        ],
        "dist_title": "Comment se répartit la population en âge d'activité ?",
        "hero_title": "Les trois indicateurs essentiels",
        "total_pop_label": "Personnes en âge d'activité",
        "lf_label": "Force de travail",
        "out_label": "Hors force de travail",
        "lf_cards": ["Actifs occupés", "Chômeurs"],
        "out_cards": ["Inactifs"],
        "indic_title": "Indicateurs complémentaires (ensemble)",
        "indicators": ["Taux d'activité des femmes", "Taux de sous-emploi", "Taux de salariat", "Taux d'emploi des femmes"],
        "key_title": "Points saillants",
        "key_points": [
            "Une participation limitée au marché du travail, en particulier chez les femmes.",
            "Un taux de chômage qui reste élevé à l'échelle régionale.",
            "Un sous-emploi qui demeure présent parmi les actifs occupés.",
            "Des résultats qui orientent les politiques publiques régionales.",
        ],
        "source": "Source : Haut-Commissariat au Plan — Enquête Nationale sur l'Emploi (ENE), région Souss-Massa, 2025.",
    },
    "en": {
        "kicker": "National Employment Survey (ENE 2025)",
        "title": "Labour market in the Souss-Massa region — year 2025",
        "subtitle": "High Commission for Planning — Souss-Massa Regional Directorate",
        "rate_activity": "Activity rate",
        "rate_activity_sub": "Labour force out of the working-age population",
        "rate_employment": "Employment rate",
        "rate_employment_sub": "Employed persons out of the working-age population",
        "rate_unemployment": "Unemployment rate",
        "rate_unemployment_sub": "Unemployed out of the labour force",
        "intro_title": "Introduction",
        "intro": "This brief presents the key results of the National Employment Survey for the Souss-Massa region for the year 2025: activity, employment and unemployment. All figures refer to the total population (urban and rural combined).",
        "glossary_title": "Glossary",
        "glossary": [
            ("Employment for pay", "Work performed in exchange for pay or profit."),
            ("Activity rate", "Share of the labour force in the working-age population."),
            ("Employment rate", "Share of employed persons in the working-age population."),
            ("Unemployment rate", "Share of the unemployed in the labour force."),
            ("Underemployment", "Employed persons willing and available to work more."),
        ],
        "dist_title": "How is the working-age population distributed?",
        "hero_title": "The three key indicators",
        "total_pop_label": "Persons of working age",
        "lf_label": "Labour force",
        "out_label": "Outside the labour force",
        "lf_cards": ["Employed", "Unemployed"],
        "out_cards": ["Inactive"],
        "indic_title": "Additional indicators (total)",
        "indicators": ["Female activity rate", "Underemployment rate", "Wage employment rate", "Female employment rate"],
        "key_title": "Highlights",
        "key_points": [
            "Limited labour market participation, especially among women.",
            "An unemployment rate that remains high at the regional level.",
            "Underemployment that remains present among the employed.",
            "Results that guide regional public policies.",
        ],
        "source": "Source: High Commission for Planning — National Employment Survey (ENE), Souss-Massa region, 2025.",
    },
    "ar": {
        "kicker": "البحث الوطني حول التشغيل (ENE 2025)",
        "title": "وضعية سوق الشغل بجهة سوس ماسة — سنة 2025",
        "subtitle": "المندوبية السامية للتخطيط — المديرية الجهوية لسوس ماسة",
        "rate_activity": "معدل النشاط",
        "rate_activity_sub": "القوى العاملة من الساكنة في سن النشاط",
        "rate_employment": "معدل الشغل",
        "rate_employment_sub": "المشتغلون من الساكنة في سن النشاط",
        "rate_unemployment": "معدل البطالة",
        "rate_unemployment_sub": "العاطلون من القوى العاملة",
        "intro_title": "المقدمة",
        "intro": "تقدم هذه المذكرة أبرز نتائج البحث الوطني حول التشغيل بجهة سوس ماسة برسم سنة 2025: النشاط، التشغيل والبطالة. جميع المعطيات تخص مجموع الساكنة (الوسطين الحضري والقروي معا).",
        "glossary_title": "المعجم",
        "glossary": [
            ("الشغل مقابل دخل", "العمل المنجز مقابل أجر أو ربح."),
            ("معدل النشاط", "نسبة القوى العاملة من الساكنة في سن النشاط."),
            ("معدل الشغل", "نسبة المشتغلين من الساكنة في سن النشاط."),
            ("معدل البطالة", "نسبة العاطلين من القوى العاملة."),
            ("الشغل الناقص", "المشتغلون الراغبون في العمل أكثر والمتوفرون لذلك."),
        ],
        "dist_title": "كيف تتوزع الساكنة في سن النشاط؟",
        "hero_title": "المؤشرات الثلاثة الأساسية",
        "total_pop_label": "الأشخاص في سن النشاط",
        "lf_label": "القوة العاملة",
        "out_label": "خارج القوة العاملة",
        "lf_cards": ["المشتغلون", "العاطلون"],
        "out_cards": ["غير النشيطين"],
        "indic_title": "مؤشرات إضافية (المجموع)",
        "indicators": ["معدل النشاط لدى النساء", "معدل الشغل الناقص", "معدل الأجراء", "معدل الشغل لدى النساء"],
        "key_title": "نقاط بارزة",
        "key_points": [
            "مشاركة محدودة في سوق الشغل، خاصة بين النساء.",
            "معدل بطالة لا يزال مرتفعا على مستوى الجهة.",
            "الشغل الناقص لا يزال حاضرا في صفوف المشتغلين.",
            "نتائج تساهم في توجيه السياسات العمومية الجهوية.",
        ],
        "source": "المصدر: المندوبية السامية للتخطيط — البحث الوطني حول التشغيل (ENE)، جهة سوس ماسة، 2025.",
    },
}

COMPARE_I18N = {
    "fr": {
        "intro_year": "Cette fiche compare l'évolution du marché du travail régional entre {a} et {b}, à partir des résultats de l'Enquête Nationale sur l'Emploi.",
        "intro_region": "Cette fiche compare le marché du travail entre {a} et {b} pour l'année {year}, à partir des résultats de l'Enquête Nationale sur l'Emploi.",
        "intro_quarter": "Cette fiche compare l'évolution trimestrielle du marché du travail en {year}, à partir des résultats de l'Enquête Nationale sur l'Emploi.",
        "title_year": "Comparatif {a} — {b}",
        "title_region": "{a} — {b}",
        "title_quarter": "Évolution trimestrielle {year}",
        "kicker_year": "Enquête Nationale sur l'Emploi (ENE {a}–{b})",
        "subtitle_year": "Marché du travail — évolution {a} → {b}",
        "subtitle_region": "Marché du travail — comparaison régionale ({year})",
        "subtitle_quarter": "Marché du travail par trimestre",
        "compare_section_title": "Indicateurs comparés",
        "indicators": ["Taux d'activité", "Taux d'emploi", "Taux de chômage"],
        "source": "Source : Haut-Commissariat au Plan — Enquête Nationale sur l'Emploi",
    },
    "en": {
        "intro_year": "This factsheet compares the regional labour market between {a} and {b}, based on the National Labour Force Survey.",
        "intro_region": "This factsheet compares the labour market between {a} and {b} for {year}, based on the National Labour Force Survey.",
        "intro_quarter": "This factsheet compares the quarterly evolution of the labour market in {year}, based on the National Labour Force Survey.",
        "title_year": "Comparison {a} — {b}",
        "title_region": "{a} — {b}",
        "title_quarter": "Quarterly evolution {year}",
        "kicker_year": "National Employment Survey (ENE {a}–{b})",
        "subtitle_year": "Labour market — {a} to {b} trend",
        "subtitle_region": "Labour market — regional comparison ({year})",
        "subtitle_quarter": "Labour market by quarter",
        "compare_section_title": "Compared indicators",
        "indicators": ["Activity rate", "Employment rate", "Unemployment rate"],
        "source": "Source: Haut-Commissariat au Plan — National Labour Force Survey",
    },
    "ar": {
        "intro_year": "تقارن هذه المذكرة تطور سوق الشغل الجهوي بين {a} و {b}، اعتمادا على نتائج البحث الوطني حول التشغيل.",
        "intro_region": "تقارن هذه المذكرة سوق الشغل بين {a} و {b} برسم سنة {year}، اعتمادا على نتائج البحث الوطني حول التشغيل.",
        "intro_quarter": "تقارن هذه المذكرة التطور الفصلي لسوق الشغل خلال سنة {year}، اعتمادا على نتائج البحث الوطني حول التشغيل.",
        "title_year": "مقارنة {a} — {b}",
        "title_region": "{a} — {b}",
        "title_quarter": "التطور الفصلي {year}",
        "kicker_year": "البحث الوطني حول التشغيل (ENE {a}–{b})",
        "subtitle_year": "سوق الشغل — تطور من {a} إلى {b}",
        "subtitle_region": "سوق الشغل — مقارنة جهوية ({year})",
        "subtitle_quarter": "سوق الشغل حسب الفصل",
        "compare_section_title": "المؤشرات المقارنة",
        "indicators": ["معدل النشاط", "معدل الشغل", "معدل البطالة"],
        "source": "المصدر: المندوبية السامية للتخطيط — البحث الوطني حول التشغيل",
    },
}


# ==========================================================================
# 4. HELPERS DE DESSIN (cartes, badges numérotés)
# ==========================================================================

def _card(draw, x0, y0, x1, y1, fill=None, outline=None, radius=14):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                            fill=CARD if fill is None else fill,
                            outline=CARD_BORDER if outline is None else outline, width=1)


def _badge(draw, lang, x, y0, num, on_accent=False, align="left"):
    """Petit badge carré numéroté. Retourne le x à partir duquel dessiner le
    titre de section qui suit (avance de 10px, ou recule si align='right')."""
    size = 26
    x0 = x if align == "left" else x - size
    bg = GREEN if on_accent else INK
    fg = INK if on_accent else WHITE
    draw.rounded_rectangle([x0, y0, x0 + size, y0 + size], radius=8, fill=bg)
    f = font(lang, 13, bold=True)
    txt = shape(str(num), lang)
    w = text_w(draw, txt, f, lang)
    draw.text((x0 + size / 2 - w / 2, y0 + size / 2 - 8), txt, font=f, fill=fg)
    return x0 + size + 10 if align == "left" else x0 - 10


# ==========================================================================
# 5. BUILDERS DE SPEC PARTAGÉS (utilisés par les 4 types d'affiche)
# ==========================================================================

def build_hero_rates(blocks, lang):
    """Les 3 taux essentiels (activité / emploi / chômage) — cartes en
    anneau (1 carte foncée + 2 cartes claires). Toujours présents, quel que
    soit le type d'affiche : c'est la zone fixe qui les porte."""
    C = DEMO_I18N[lang]
    v_ta, p_ta = get_rate(blocks, "TA", lang=lang)
    v_te, p_te = get_rate(blocks, "TE", lang=lang)
    v_tc, p_tc = get_rate(blocks, "TC", lang=lang)
    return [
        {"value": v_ta, "pct": p_ta or 0, "label": C["rate_activity"], "sub": C["rate_activity_sub"],
         "style": "dark", "ring": "accent"},
        {"value": v_te, "pct": p_te or 0, "label": C["rate_employment"], "sub": C["rate_employment_sub"],
         "style": "light", "ring": "ink"},
        {"value": v_tc, "pct": p_tc or 0, "label": C["rate_unemployment"], "sub": C["rate_unemployment_sub"],
         "style": "light", "ring": "gold"},
    ]


def build_glossary(lang, number=2):
    C = DEMO_I18N[lang]
    return {"number": number, "title": C["glossary_title"],
            "items": [{"term": term, "def": d} for term, d in C["glossary"]]}


def build_distribution(blocks, lang, number=3):
    """Diagramme de répartition de la population en âge d'activité — construit
    à partir de vraies données Excel (table population en âge de travailler)."""
    C = DEMO_I18N[lang]
    titre_pop = resolve_working_age_title(blocks)
    total_v, unite = get_value(blocks, titre_pop, "Ensemble", "Ensemble")
    actif_v, _ = get_value(blocks, titre_pop, "Actif occupé", "Ensemble")
    chomeur_v, _ = get_value(blocks, titre_pop, "Chômeur", "Ensemble")
    inactif_v, _ = get_value(blocks, titre_pop, "Inactif", "Ensemble")
    lf_v = actif_v + chomeur_v

    v_ta, p_ta = get_rate(blocks, "TA", lang=lang)
    p_out = 100 - (p_ta or 0)

    def fmt(x):
        return format_number(x, unite, lang)

    pct_actif = (actif_v / lf_v * 100) if lf_v else 0
    pct_chomeur = (chomeur_v / lf_v * 100) if lf_v else 0

    return {
        "number": number,
        "title": C["dist_title"],
        "total_label": C["total_pop_label"],
        "total_value": fmt(total_v),
        # part de la force de travail — alimente l'anneau de la carte "total"
        # de l'arbre de répartition (nouveau design HTML).
        "total_pct": p_ta or 0,
        "groups": [
            {
                "label": C["lf_label"], "rate": v_ta, "count": fmt(lf_v),
                "cards": [
                    {"pct": format_number(pct_actif, "%", lang), "count": fmt(actif_v), "label": C["lf_cards"][0]},
                    {"pct": format_number(pct_chomeur, "%", lang), "count": fmt(chomeur_v), "label": C["lf_cards"][1]},
                ],
            },
            {
                # Hors force de travail = inactifs : dans l'arbre simplifié
                # (données Excel disponibles uniquement), cette branche n'a
                # pas de cartes feuilles — la maquette HTML en avait deux
                # ("main-d'œuvre potentielle" / "autres") mais ces concepts
                # sont absents de l'export ENE actuel, choix validé.
                "label": C["out_label"], "rate": format_number(p_out, "%", lang), "count": fmt(inactif_v),
                "cards": [],
            },
        ],
    }


def build_indicators(blocks, lang, number=4):
    """Les 4 puces d'indicateurs complémentaires du nouveau design : activité
    des femmes, sous-emploi, taux de salariat (nouveau), emploi des femmes."""
    C = DEMO_I18N[lang]
    v_ta_f, _ = get_rate(blocks, "TA", "Ensemble", "Féminin", lang=lang)
    v_ts, _ = get_rate(blocks, "TS", lang=lang)
    try:
        titre_sal = resolve_salariat_title(blocks)
        sal_v, sal_u = get_value(blocks, titre_sal, "Salarié")
        v_sal = format_number(sal_v, sal_u, lang)
    except KeyError:
        v_sal = format_number(None, "%", lang)  # n.d. — validate_blocks l'aura signalé
    v_te_f, _ = get_rate(blocks, "TE", "Ensemble", "Féminin", lang=lang)
    values = [v_ta_f, v_ts, v_sal, v_te_f]
    return {"number": number, "title": C["indic_title"],
            "items": [{"value": v, "label": lbl} for v, lbl in zip(values, C["indicators"])]}


def build_key_points(lang, number=5):
    C = DEMO_I18N[lang]
    return {"number": number, "title": C["key_title"],
            "items": [{"num": f"0{i+1}", "text": txt} for i, txt in enumerate(C["key_points"])]}


# ==========================================================================
# 6. ZONE FIXE (en-tête + 3 taux + intro/lexique + répartition) — PARTAGÉE
# ==========================================================================

def render_fixed_header_zone(spec: dict, lang: str):
    """Dessine l'en-tête, introduction + lexique (côte à côte), la
    répartition de la population (arbre du nouveau design) puis les 3 taux
    essentiels (carte titrée, sous l'arbre — ordre de la maquette HTML).
    Retourne (img, draw, y, ctx) pour que l'appelant poursuive avec sa zone
    flexible : `ctx` transporte {W, margin, rtl, align, S, content_w}.

    Spec attendu : kicker, title, subtitle, logo (optionnel),
    hero_rates (3 items), intro (number+title+text), glossary (build_glossary),
    distribution (build_distribution).
    """
    S = STRINGS[lang]
    rtl = lang == "ar"
    align = "right" if rtl else "left"
    W = 1240
    margin = 40
    content_w = W - 2 * margin
    img = Image.new("RGB", (W, 3200), PAGE)
    draw = ImageDraw.Draw(img)
    y = margin

    # ================= 1. EN-TÊTE =================
    header_h = 108
    _card(draw, margin, y, W - margin, y + header_h, fill=INK, outline=INK, radius=16)
    logo_path = spec.get("logo", str(HERE / "hcp_logo.png"))
    logo_box_w = 0
    if Path(logo_path).exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((110, 76))
        pad = 12
        plate_w, plate_h = logo.width + pad * 2, logo.height + pad * 2
        plate_img = Image.new("RGBA", (plate_w, plate_h), (255, 255, 255, 255))
        plate_img.paste(logo, (pad, pad), logo)
        logo_x = margin + 20 if rtl else W - margin - 20 - plate_w
        logo_y = y + (header_h - plate_h) / 2
        draw.rounded_rectangle([logo_x, logo_y, logo_x + plate_w, logo_y + plate_h], radius=10, fill=WHITE)
        img.paste(plate_img, (int(logo_x), int(logo_y)), plate_img)
        logo_box_w = plate_w + 20

    text_x0 = margin + 24 if not rtl else margin + 24 + logo_box_w
    text_x1 = W - margin - 24 - logo_box_w if not rtl else W - margin - 24
    text_area_w = text_x1 - text_x0
    tx = text_x0 if not rtl else text_x1
    ty = y + 18

    kicker = spec.get("kicker", "")
    if kicker:
        f_kicker = font(lang, 12, bold=True)
        kt = shape(kicker, lang)
        kw = text_w(draw, kt, f_kicker, lang)
        pill_pad = 12
        px0 = tx if not rtl else tx - kw - 2 * pill_pad
        draw.rounded_rectangle([px0, ty, px0 + kw + 2 * pill_pad, ty + 24], radius=12, fill=GREEN)
        draw.text((px0 + pill_pad, ty + 4), kt, font=f_kicker, fill=INK)
        ty += 34

    f_title = font(lang, 22, bold=True)
    title_lines = wrap(draw, spec["title"], f_title, text_area_w, lang)
    for line in title_lines[:2]:
        draw_line(draw, tx, ty, line, f_title, WHITE, lang, align=align)
        ty += 28
    f_sub = font(lang, 13)
    for line in wrap(draw, spec.get("subtitle", ""), f_sub, text_area_w, lang)[:1]:
        draw_line(draw, tx, ty + 4, line, f_sub, MUTED_ON_DARK, lang, align=align)

    y += header_h + 18

    # ================= 2. INTRODUCTION + LEXIQUE (côte à côte) =================
    intro = spec.get("intro")
    glossary = spec.get("glossary")
    if intro or glossary:
        gap = 16
        intro_w = content_w * (1 / 2.9)
        gloss_w = content_w - intro_w - gap
        if rtl:
            intro_x0, intro_x1 = W - margin - intro_w, W - margin
            gloss_x0, gloss_x1 = margin, margin + gloss_w
        else:
            intro_x0, intro_x1 = margin, margin + intro_w
            gloss_x0, gloss_x1 = W - margin - gloss_w, W - margin

        row_h = 190
        if intro:
            _card(draw, intro_x0, y, intro_x1, y + row_h)
            bx = _badge(draw, lang, intro_x0 + 14 if not rtl else intro_x1 - 14, y + 14, intro.get("number", 1), align=align)
            f_h = font(lang, 15, bold=True)
            draw_line(draw, bx, y + 17, intro.get("title", S["intro_title"]), f_h, TEXT, lang, align=align)
            f_body = font(lang, 12)
            ix = intro_x0 + 16 if not rtl else intro_x1 - 16
            iy = y + 52
            for line in wrap(draw, intro["text"], f_body, intro_w - 32, lang):
                draw_line(draw, ix, iy, line, f_body, TEXT_BODY, lang, align=align)
                iy += 18.5
                if iy > y + row_h - 16:
                    break

        if glossary:
            _card(draw, gloss_x0, y, gloss_x1, y + row_h)
            bx = _badge(draw, lang, gloss_x0 + 14 if not rtl else gloss_x1 - 14, y + 14, glossary.get("number", 2), align=align)
            f_h = font(lang, 15, bold=True)
            draw_line(draw, bx, y + 17, glossary.get("title", S["lexique_title"]), f_h, TEXT, lang, align=align)
            items = glossary["items"]
            n = len(items)
            gcell_gap = 8
            gcell_w = (gloss_w - 32 - gcell_gap * (n - 1)) / n
            gy0 = y + 52
            gcell_h = row_h - 52 - 14
            for idx, it in enumerate(items):
                order = idx if not rtl else (n - 1 - idx)
                gx0 = gloss_x0 + 16 + order * (gcell_w + gcell_gap)
                _card(draw, gx0, gy0, gx0 + gcell_w, gy0 + gcell_h, fill=CARD_ALT, outline=CARD_ALT, radius=10)
                draw.rounded_rectangle([gx0 + 10, gy0 + 10, gx0 + 32, gy0 + 13], radius=2, fill=GREEN)
                f_term = font(lang, 11, bold=True)
                ty2 = gy0 + 20
                for line in wrap(draw, it["term"], f_term, gcell_w - 20, lang)[:2]:
                    draw_line(draw, gx0 + 10, ty2, line, f_term, TEXT, lang, align="left")
                    ty2 += 14
                f_def = font(lang, 9)
                for line in wrap(draw, it["def"], f_def, gcell_w - 20, lang)[:5]:
                    draw_line(draw, gx0 + 10, ty2, line, f_def, MUTED, lang, align="left")
                    ty2 += 12.5
        y += row_h + 18

    # ================= 3. RÉPARTITION (arbre, nouveau design) =================
    # Reproduit l'arbre de la maquette HTML : carte "total" (crème, avec
    # anneau) reliée par des connecteurs aux deux boîtes marine (force de
    # travail / hors force), la première alimentant des cartes feuilles
    # (actifs occupés / chômeurs). En RTL le total est à gauche et les
    # feuilles à droite (comme la maquette arabe) ; en LTR, miroir exact.
    dist = spec.get("distribution")
    if dist:
        groups = dist["groups"]
        leaf_h, leaf_gap, group_gap = 84, 10, 18
        zone_hs = [max(len(g["cards"]), 1) * leaf_h + (max(len(g["cards"]), 1) - 1) * leaf_gap + (10 if len(g["cards"]) > 1 else 8) for g in groups]
        body_h = sum(zone_hs) + group_gap * (len(groups) - 1)
        box_h = 60 + body_h + 20
        _card(draw, margin, y, W - margin, y + box_h)
        bx = _badge(draw, lang, margin + 16 if not rtl else W - margin - 16, y + 16, dist.get("number", 3), align=align)
        f_h = font(lang, 15, bold=True)
        draw_line(draw, bx, y + 19, dist.get("title", S["breakdown_title"]), f_h, TEXT, lang, align=align)

        in_x0, in_x1 = margin + 16, W - margin - 16
        total_w, conn_w, branch_w, leaf_gap_x = 240, 48, 280, 16
        leaves_w = (in_x1 - in_x0) - total_w - conn_w - branch_w - leaf_gap_x
        if rtl:  # comme la maquette AR : total à gauche, feuilles à droite
            total_x0 = in_x0
            conn_x0 = total_x0 + total_w
            branch_x0 = conn_x0 + conn_w
            leaves_x0 = branch_x0 + branch_w + leaf_gap_x
        else:    # miroir LTR : feuilles à gauche, total à droite
            leaves_x0 = in_x0
            branch_x0 = leaves_x0 + leaves_w + leaf_gap_x
            conn_x0 = branch_x0 + branch_w
            total_x0 = conn_x0 + conn_w
        conn_mid = conn_x0 + conn_w / 2

        body_y0 = y + 60
        branch_centers = []
        gy = body_y0
        for gi, grp in enumerate(groups):
            zone_h = zone_hs[gi]
            cards_ = grp["cards"]
            # boîte marine de la branche, centrée dans sa zone
            bh = min(120, zone_h) if cards_ else zone_h
            by0 = gy + (zone_h - bh) / 2
            _card(draw, branch_x0, by0, branch_x0 + branch_w, by0 + bh, fill=INK, outline=INK, radius=10)
            bxm = branch_x0 + branch_w / 2
            f_bv = font(lang, 20, bold=True)
            draw_line(draw, bxm, by0 + 12, grp["rate"], f_bv, WHITE, lang, align="center")
            f_bl = font(lang, 11, bold=True)
            draw_line(draw, bxm, by0 + 40, grp["label"], f_bl, WHITE, lang, align="center")
            draw.line([(branch_x0 + 18, by0 + bh - 24), (branch_x0 + branch_w - 18, by0 + bh - 24)], fill=(70, 94, 106))
            f_bc = font(lang, 11)
            draw_line(draw, bxm, by0 + bh - 20, grp["count"], f_bc, MUTED_ON_DARK, lang, align="center")
            branch_centers.append(by0 + bh / 2)

            # cartes feuilles (à gauche en LTR, à droite en RTL)
            ly = gy
            for c in cards_:
                _card(draw, leaves_x0, ly, leaves_x0 + leaves_w, ly + leaf_h, fill=INK, outline=INK, radius=8)
                pad = 16
                lx = leaves_x0 + pad if not rtl else leaves_x0 + leaves_w - pad
                f_cv = font(lang, 15, bold=True)
                draw_line(draw, lx, ly + 10, c["pct"], f_cv, WHITE, lang, align=align)
                f_cl = font(lang, 10)
                lines = wrap(draw, c["label"], f_cl, leaves_w - 2 * pad - 90, lang)
                ly2 = ly + 34
                for line in lines[:2]:
                    draw_line(draw, lx, ly2, line, f_cl, LIGHT_ON_DARK, lang, align=align)
                    ly2 += 13
                f_cc = font(lang, 12, bold=True)
                ox = leaves_x0 + leaves_w - pad if not rtl else leaves_x0 + pad
                draw_line(draw, ox, ly + leaf_h / 2 - 8, c["count"], f_cc, GREEN, lang,
                          align=("right" if not rtl else "left"))
                # connecteur feuille -> branche
                cy_mid = ly + leaf_h / 2
                if rtl:
                    draw.line([branch_x0 + branch_w, cy_mid, leaves_x0, cy_mid], fill=CARD_BORDER, width=2)
                else:
                    draw.line([leaves_x0 + leaves_w, cy_mid, branch_x0, cy_mid], fill=CARD_BORDER, width=2)
                ly += leaf_h + leaf_gap
            gy += zone_h + group_gap

        # connecteurs total -> branches (colonne épine)
        total_cy = body_y0 + body_h / 2
        draw.line([conn_mid, branch_centers[0], conn_mid, branch_centers[-1]], fill=CARD_BORDER, width=2)
        for bcy in branch_centers:
            if rtl:
                draw.line([conn_mid, bcy, branch_x0, bcy], fill=CARD_BORDER, width=2)
            else:
                draw.line([branch_x0 + branch_w, bcy, conn_mid, bcy], fill=CARD_BORDER, width=2)
        if rtl:
            draw.line([total_x0 + total_w, total_cy, conn_mid, total_cy], fill=CARD_BORDER, width=2)
        else:
            draw.line([conn_mid, total_cy, total_x0 + total_w, total_cy], fill=CARD_BORDER, width=2)

        # carte "total" (crème) avec anneau de la part de la force de travail
        tc_h = min(body_h, 264)
        tc_y0 = body_y0 + (body_h - tc_h) / 2
        _card(draw, total_x0, tc_y0, total_x0 + total_w, tc_y0 + tc_h, fill=CARD_ALT, outline=CARD_BORDER, radius=14)
        ax = total_x0 + 14 if not rtl else total_x0 + total_w - 26
        draw.rectangle([ax, tc_y0 + 14, ax + 12, tc_y0 + 26], fill=GREEN)
        dsize = 104
        dx = total_x0 + (total_w - dsize) / 2
        dy = tc_y0 + 34
        donut_img = make_donut(dist.get("total_pct", 0), "#%02X%02X%02X" % GREEN, size_px=dsize)
        img.paste(donut_img, (int(dx), int(dy)), donut_img)
        f_dv = font(lang, 16, bold=True)
        pct_txt = format_number(dist.get("total_pct", 0), "%", lang)
        draw_line(draw, dx + dsize / 2, dy + dsize / 2 - 11, pct_txt, f_dv, TEXT, lang, align="center")
        tcx = total_x0 + total_w / 2
        f_tl = font(lang, 12, bold=True)
        ty2 = dy + dsize + 14
        for line in wrap(draw, dist["total_label"], f_tl, total_w - 24, lang)[:2]:
            draw_line(draw, tcx, ty2, line, f_tl, TEXT, lang, align="center")
            ty2 += 19
        draw.line([tcx - 22, ty2 + 3, tcx + 22, ty2 + 3], fill=GREEN, width=3)
        f_tv = font(lang, 17, bold=True)
        draw_line(draw, tcx, ty2 + 12, dist["total_value"], f_tv, TEXT, lang, align="center")

        y += box_h + 18

    # ================= 4. TROIS TAUX ESSENTIELS (carte titrée, sous l'arbre) =================
    hero = spec.get("hero_rates")
    if hero:
        card_h = 128
        box_h = 48 + card_h + 16
        _card(draw, margin, y, W - margin, y + box_h, radius=16)
        f_h = font(lang, 15, bold=True)
        hx = margin + 16 if not rtl else W - margin - 16
        draw_line(draw, hx, y + 16, spec.get("hero_title", DEMO_I18N[lang]["hero_title"]), f_h, TEXT, lang, align=align)

        n = len(hero)
        gap = 14
        cw = (content_w - 32 - gap * (n - 1)) / n
        cy0 = y + 48
        colors_ring = {"accent": GREEN, "ink": INK, "gold": GOLD}
        for idx, r in enumerate(hero):
            order = idx if not rtl else (n - 1 - idx)
            cx0 = margin + 16 + order * (cw + gap)
            dark = r.get("style") == "dark"
            fillc = INK if dark else CARD_ALT
            _card(draw, cx0, cy0, cx0 + cw, cy0 + card_h, fill=fillc,
                  outline=(INK if dark else CARD_BORDER), radius=14)
            ring_color = colors_ring.get(r.get("ring", "ink"), INK)
            dsize = 92
            donut_img = make_donut(r["pct"], "#%02X%02X%02X" % ring_color, size_px=dsize)
            dx = cx0 + 18 if not rtl else cx0 + cw - 18 - dsize
            dy = cy0 + (card_h - dsize) / 2
            img.paste(donut_img, (int(dx), int(dy)), donut_img)
            f_val = font(lang, 20, bold=True)
            valcol = WHITE if dark else TEXT
            draw_line(draw, dx + dsize / 2, dy + dsize / 2 - 13, r["value"], f_val, valcol, lang, align="center")
            tx2 = dx + dsize + 14 if not rtl else dx - 14
            f_lbl = font(lang, 14, bold=True)
            draw_line(draw, tx2, cy0 + 28, r["label"], f_lbl, valcol, lang, align=align)
            f_subl = font(lang, 11)
            subcol = MUTED_ON_DARK if dark else MUTED
            sub_w = cw - dsize - 18 - 14 - 14
            sy = cy0 + 50
            for line in wrap(draw, r["sub"], f_subl, sub_w, lang)[:3]:
                draw_line(draw, tx2, sy, line, f_subl, subcol, lang, align=align)
                sy += 15
        y += box_h + 18

    ctx = {"W": W, "margin": margin, "rtl": rtl, "align": align, "S": S, "content_w": content_w}
    return img, draw, y, ctx


# ==========================================================================
# 7. POINTS SAILLANTS — PARTAGÉE (fin de chaque zone flexible)
# ==========================================================================

def _render_key_points(draw, y, spec: dict, lang: str, ctx: dict) -> float:
    rtl, margin, W, content_w = ctx["rtl"], ctx["margin"], ctx["W"], ctx["content_w"]
    align, S = ctx["align"], ctx["S"]
    key_points = spec.get("key_points")
    if not key_points:
        return y
    items = key_points["items"]
    n = len(items)
    box_h = 108
    _card(draw, margin, y, W - margin, y + box_h, fill=INK, outline=INK, radius=14)
    bx = _badge(draw, lang, margin + 16 if not rtl else W - margin - 16, y + 16, key_points.get("number", 5),
                on_accent=True, align=align)
    f_h = font(lang, 15, bold=True)
    draw_line(draw, bx, y + 19, key_points.get("title", S["notes_title"]), f_h, WHITE, lang, align=align)

    gap = 14
    cell_w = (content_w - 32 - gap * (n - 1)) / n
    cy0 = y + 52
    for idx, kp in enumerate(items):
        order = idx if not rtl else (n - 1 - idx)
        cx0 = margin + 16 + order * (cell_w + gap)
        draw.rectangle([cx0, cy0, cx0 + cell_w, cy0 + 2], fill=GREEN)
        f_num = font(lang, 16, bold=True)
        draw_line(draw, cx0, cy0 + 8, kp["num"], f_num, GREEN, lang, align="left")
        f_txt = font(lang, 10)
        ty2 = cy0 + 28
        for line in wrap(draw, kp["text"], f_txt, cell_w - 6, lang)[:5]:
            draw_line(draw, cx0, ty2, line, f_txt, KEYPOINTS_TEXT, lang, align="left")
            ty2 += 13.5
    return y + box_h + 14


# ==========================================================================
# 8. ZONE FLEXIBLE — Type 1 (indicateurs complémentaires)
# ==========================================================================

def render_flexible_standard(img, draw, y, spec: dict, lang: str, ctx: dict) -> float:
    rtl, margin, W, content_w = ctx["rtl"], ctx["margin"], ctx["W"], ctx["content_w"]
    align = ctx["align"]

    indicators = spec.get("indicators")
    if indicators:
        items = indicators["items"]
        n = len(items)
        box_h = 118
        _card(draw, margin, y, W - margin, y + box_h)
        bar_x = margin + 16 if not rtl else W - margin - 16
        draw.rounded_rectangle([bar_x - (0 if not rtl else 4), y + 14, bar_x + (4 if not rtl else 0), y + 34],
                                 radius=2, fill=GREEN)
        f_h = font(lang, 15, bold=True)
        tx3 = bar_x + 12 if not rtl else bar_x - 12
        draw_line(draw, tx3, y + 16, indicators.get("title", ""), f_h, TEXT, lang, align=align)

        gap = 12
        cell_w = (content_w - 32 - gap * (n - 1)) / n
        cy0 = y + 46
        cell_h = box_h - 46 - 14
        for idx, it in enumerate(items):
            order = idx if not rtl else (n - 1 - idx)
            cx0 = margin + 16 + order * (cell_w + gap)
            _card(draw, cx0, cy0, cx0 + cell_w, cy0 + cell_h, fill=CARD_ALT, outline=CARD_ALT, radius=8)
            draw.rectangle([cx0, cy0, cx0 + cell_w, cy0 + 3], fill=GREEN)
            vx = cx0 + 12 if not rtl else cx0 + cell_w - 12
            f_v = font(lang, 19, bold=True)
            draw_line(draw, vx, cy0 + 10, it["value"], f_v, TEXT, lang, align=align)
            f_l = font(lang, 9, bold=True)
            ly = cy0 + 37
            for line in wrap(draw, it["label"], f_l, cell_w - 24, lang)[:2]:
                draw_line(draw, vx, ly, line, f_l, MUTED, lang, align=align)
                ly += 12
        y += box_h + 18

    return _render_key_points(draw, y, spec, lang, ctx)


# ==========================================================================
# 9. ZONE FLEXIBLE — Type 2 (comparatif années, courbes de tendance)
# ==========================================================================

def _draw_trend_legend(draw, y, series, lang, ctx) -> None:
    """Légende du graphe combiné : une puce colorée + libellé + dernière
    valeur par série, répartis en colonnes égales, RTL-aware."""
    rtl, margin, W, content_w = ctx["rtl"], ctx["margin"], ctx["W"], ctx["content_w"]
    n = len(series)
    col_w = (content_w - 36) / n
    f_lbl = font(lang, 13, bold=True)
    dec = "," if lang != "en" else "."
    dot_r = 6
    cy = y + 8
    for i, s in enumerate(series):
        color = s["color_rgb"]
        last = s.get("last")
        val_txt = (f"{last:.1f}".replace(".", dec) + "%") if last is not None else ""
        text = f"{s['label']} · {val_txt}" if val_txt else s["label"]
        if rtl:
            x_right = W - margin - 18 - i * col_w
            draw.ellipse([x_right - 2 * dot_r, cy - dot_r, x_right, cy + dot_r], fill=color)
            draw_line(draw, x_right - 2 * dot_r - 8, y, text, f_lbl, TEXT, lang, align="right")
        else:
            x_left = margin + 18 + i * col_w
            draw.ellipse([x_left, cy - dot_r, x_left + 2 * dot_r, cy + dot_r], fill=color)
            draw_line(draw, x_left + 2 * dot_r + 8, y, text, f_lbl, TEXT, lang, align="left")


def render_flexible_trend(img, draw, y, spec: dict, lang: str, ctx: dict) -> float:
    rtl, margin, W, content_w = ctx["rtl"], ctx["margin"], ctx["W"], ctx["content_w"]
    align = ctx["align"]

    trends = spec.get("trend_charts")
    if trends and trends.get("charts"):
        # _badge gère lui-même le décalage en RTL (align="right") : on lui
        # passe le bord du contenu et on dessine le titre au x qu'il retourne
        # — pré-compenser le x ici ferait chevaucher badge et titre en arabe.
        tx4 = _badge(draw, lang, margin if not rtl else W - margin, y, trends.get("number", 6), align=align)
        f_h = font(lang, 16, bold=True)
        draw_line(draw, tx4, y + 4, trends["title"], f_h, TEXT, lang, align=align)
        y += 40

        charts = trends["charts"]
        # Axe des années commun = union triée de toutes les séries (en pratique
        # TA/TE/TC partagent les mêmes années ; l'alignement gère le cas rare
        # où un indicateur manque sur une année — point coupé sur cette série).
        master_years = sorted({yr for c in charts for yr in c["years"]}, key=lambda v: int(v))
        series = []
        for c in charts:
            by_year = dict(zip(c["years"], c["values"]))
            series.append({
                "label": c["label"],
                "color": c.get("color", "#A3B520"),
                "color_rgb": c.get("color_rgb", GREEN),
                "values": [by_year.get(yr) for yr in master_years],
                "last": c["values"][-1] if c["values"] else None,
            })

        legend_h, chart_h = 46, 320
        ch = legend_h + chart_h + 18
        _card(draw, margin, y, W - margin, y + ch, radius=14)
        _draw_trend_legend(draw, y + 16, series, lang, ctx)
        chart_img = make_multi_line_chart(series, master_years, width_px=content_w - 40,
                                          height_px=chart_h, lang=lang)
        img.paste(chart_img, (margin + 20, y + legend_h + 4), chart_img)
        y += ch + 18

    return _render_key_points(draw, y, spec, lang, ctx)


# ==========================================================================
# 10. ZONE FLEXIBLE — Types 3 & 4 (comparatif jihat / trimestres, barres)
# ==========================================================================

def render_flexible_compare(img, draw, y, spec: dict, lang: str, ctx: dict) -> float:
    rtl, margin, W = ctx["rtl"], ctx["margin"], ctx["W"]
    align = ctx["align"]

    compare = spec.get("compare_bars")
    if compare:
        # même logique que render_flexible_trend : laisser _badge placer le
        # badge et le titre (sinon chevauchement badge/titre en RTL).
        tx4 = _badge(draw, lang, margin if not rtl else W - margin, y, compare.get("number", 6), align=align)
        f_h = font(lang, 16, bold=True)
        draw_line(draw, tx4, y + 4, compare["title"], f_h, TEXT, lang, align=align)
        y += 40
        entities = compare["entities"]
        items = compare["items"]
        n_entities = len(entities)
        colors = [GREEN, GOLD, (59, 111, 160), CORAL][:n_entities]
        # 28px par entité : libellé (16px) PUIS barre en dessous (à +20),
        # sinon la piste raye le texte de l'entité.
        row_h = 34 + 28 * n_entities
        box_h = row_h * len(items) + 16
        _card(draw, margin, y, W - margin, y + box_h, radius=14)
        by = y + 14
        f_ind = font(lang, 14, bold=True)
        f_ent = font(lang, 12)
        f_delta = font(lang, 12, bold=True)
        row_x0, row_x1 = margin + 20, W - margin - 20
        bar_area_w = (row_x1 - row_x0) - 110
        for it in items:
            draw_line(draw, row_x1 if rtl else row_x0, by, it["label"], f_ind, TEXT, lang, align=align)
            if n_entities == 2 and it["pcts"][0] is not None and it["pcts"][1] is not None:
                delta = it["pcts"][1] - it["pcts"][0]
                sign = "+" if delta >= 0 else ""
                dtxt = f"{sign}{delta:.1f} pt".replace(".", "," if lang != "en" else ".")
                dcolor = GREEN if delta >= 0 else CORAL
                draw_line(draw, row_x0 if rtl else row_x1, by, dtxt, f_delta, dcolor, lang,
                          align=("left" if rtl else "right"))
            ey = by + 24
            for idx, (ent_label, val_str, pct) in enumerate(zip(entities, it["values"], it["pcts"])):
                pct = pct or 0
                bar_full = int(bar_area_w * min(pct, 100) / 100)
                bar_y = ey + 20
                ecol = colors[idx % len(colors)]
                if rtl:
                    draw_line(draw, row_x1, ey, f"{ent_label} — {val_str}", f_ent, MUTED, lang, align="right")
                    draw.line([row_x1 - bar_area_w, bar_y, row_x1, bar_y], fill=TRACK, width=4)
                    draw.line([row_x1 - bar_full, bar_y, row_x1, bar_y], fill=ecol, width=4)
                else:
                    draw_line(draw, row_x0, ey, f"{ent_label} — {val_str}", f_ent, MUTED, lang, align="left")
                    draw.line([row_x0, bar_y, row_x0 + bar_area_w, bar_y], fill=TRACK, width=4)
                    draw.line([row_x0, bar_y, row_x0 + bar_full, bar_y], fill=ecol, width=4)
                ey += 28
            by += row_h
        y += box_h + 18

    return _render_key_points(draw, y, spec, lang, ctx)


# ==========================================================================
# 11. FINALISATION (source + recadrage + sauvegarde) — PARTAGÉE
# ==========================================================================

def finalize(img, draw, y, spec: dict, lang: str, output_path: str) -> str:
    W = img.width
    margin = 40
    src = spec.get("source", "")
    if src:
        f_src = font(lang, 11)
        draw_line(draw, W / 2, y, src, f_src, (122, 133, 127), lang, align="center")
        y += 20
    img = img.crop((0, 0, W, int(y + margin)))
    img.save(output_path)
    return output_path
