#!/usr/bin/env python3
"""posters/region_compare.py — Type 3 : comparatif entre deux jihat (régions)
pour une même année. Reprend `build_region_compare_spec` de
`generate_affiche.py` à l'identique : zone fixe basée sur la région B (le
2e fichier), zone flexible en barres comparatives (2 entités) pour
TA/TE/TC.
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
    render_fixed_header_zone,
    render_flexible_compare,
)


def build_spec(blocks_a: dict, blocks_b: dict, region_a: str, region_b: str, year_label: str, lang: str) -> dict:
    """Construit le spec du comparatif Type 3 à partir des blocs déjà parsés
    pour deux fichiers Excel régionaux, sur la même année."""
    T = COMPARE_I18N[lang]
    C = DEMO_I18N[lang]
    items = []
    for code, label in zip(["TA", "TE", "TC"], T["indicators"]):
        va, pa = get_rate(blocks_a, code, lang=lang)
        vb, pb = get_rate(blocks_b, code, lang=lang)
        items.append({"label": label, "values": [va, vb], "pcts": [pa, pb]})

    return {
        "kicker": C["kicker"],
        "title": T["title_region"].format(a=region_a, b=region_b),
        "subtitle": T["subtitle_region"].format(year=year_label),
        "hero_rates": build_hero_rates(blocks_b, lang),
        "intro": {"number": 1, "title": C["intro_title"],
                  "text": T["intro_region"].format(a=region_a, b=region_b, year=year_label)},
        "glossary": build_glossary(lang, number=2),
        "distribution": build_distribution(blocks_b, lang, number=3),
        "compare_bars": {"number": 4, "title": T["compare_section_title"],
                          "entities": [region_a, region_b], "items": items},
        "key_points": build_key_points(lang, number=5),
        "source": T["source"],
    }


def render(spec: dict, lang: str, output_path: str) -> str:
    """Rendu du Type 3 : zone fixe suivie de la zone flexible comparative
    (barres), puis finalisation."""
    img, draw, y, ctx = render_fixed_header_zone(spec, lang)
    y = render_flexible_compare(img, draw, y, spec, lang, ctx)
    return finalize(img, draw, y, spec, lang, output_path)
