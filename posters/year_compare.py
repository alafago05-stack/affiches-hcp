#!/usr/bin/env python3
"""posters/year_compare.py — Type 2 : comparatif entre deux années.

Reprend `build_year_compare_spec` de `generate_affiche.py` à l'identique :
zone fixe basée sur l'année la plus récente (année B), zone flexible en
courbes de tendance (une par indicateur TA/TE/TC) sur toute la plage
d'années entre A et B — pas seulement les deux bornes, ce qui suppose que
l'app fournit un `blocks_by_year` couvrant toute la plage (voir app.py).
"""

from parsers.annual import get_rate
from poster_engine import (
    COMPARE_I18N,
    DEMO_I18N,
    build_distribution,
    build_glossary,
    build_hero_rates,
    build_key_points,
    finalize,
    hex_to_rgb,
    render_fixed_header_zone,
    render_flexible_trend,
)


def build_spec(blocks_by_year: dict, year_a: str, year_b: str, lang: str) -> dict:
    """Construit le spec du comparatif Type 2. `blocks_by_year` doit couvrir
    toutes les années entre min(year_a, year_b) et max(year_a, year_b) déjà
    parsées (les années au format incompatible peuvent être omises : elles
    seront simplement absentes de la courbe pour cet indicateur)."""
    T = COMPARE_I18N[lang]
    C = DEMO_I18N[lang]
    years_sorted = sorted(blocks_by_year.keys(), key=lambda y: int(y))
    chart_colors = {"TA": "#4E9A50", "TE": "#3B6FA0", "TC": "#C44A3E"}

    charts = []
    for code, label in zip(["TA", "TE", "TC"], T["indicators"]):
        vals, valid_years = [], []
        for yr in years_sorted:
            try:
                _, p = get_rate(blocks_by_year[yr], code, lang=lang)
            except KeyError:
                continue
            if p is not None:
                vals.append(p)
                valid_years.append(yr)
        if vals:
            charts.append({"label": label, "years": valid_years, "values": vals,
                            "color": chart_colors[code], "color_rgb": hex_to_rgb(chart_colors[code])})

    blocks_b = blocks_by_year[str(year_b)]

    return {
        "kicker": T["kicker_year"].format(a=year_a, b=year_b),
        "title": T["title_year"].format(a=year_a, b=year_b),
        "subtitle": T["subtitle_year"].format(a=year_a, b=year_b),
        "hero_rates": build_hero_rates(blocks_b, lang),
        "intro": {"number": 1, "title": C["intro_title"], "text": T["intro_year"].format(a=year_a, b=year_b)},
        "glossary": build_glossary(lang, number=2),
        "distribution": build_distribution(blocks_b, lang, number=3),
        "trend_charts": {"number": 4, "title": T["compare_section_title"], "charts": charts},
        "key_points": build_key_points(lang, number=5),
        "source": T["source"],
    }


def render(spec: dict, lang: str, output_path: str) -> str:
    """Rendu du Type 2 : zone fixe suivie de la zone flexible en courbes de
    tendance, puis finalisation."""
    img, draw, y, ctx = render_fixed_header_zone(spec, lang)
    y = render_flexible_trend(img, draw, y, spec, lang, ctx)
    return finalize(img, draw, y, spec, lang, output_path)
