#!/usr/bin/env python3
"""posters/standard.py — Type 1 : affiche standard (une année, une région).

Reprend `build_demo_spec` de `generate_affiche.py` à l'identique. Les
briques partagées (3 taux essentiels, lexique, répartition population,
indicateurs complémentaires, points saillants) vivent dans
`poster_engine.py` ; ce module ne fait qu'assembler le `spec` pour ce type
et enchaîner zone fixe → zone flexible → finalisation.
"""

from poster_engine import (
    DEMO_I18N,
    build_distribution,
    build_hero_rates,
    build_indicators,
    build_key_points,
    build_glossary,
    finalize,
    render_fixed_header_zone,
    render_flexible_standard,
)


def build_spec(blocks: dict, lang: str) -> dict:
    """Construit le spec de l'affiche standard (Type 1) à partir des blocs
    déjà parsés pour UNE année. Fidèle à `build_demo_spec` : le titre, le
    sous-titre et le texte d'intro restent le contenu démo fixe (année 2025,
    Souss-Massa) — seules les valeurs des indicateurs proviennent réellement
    de `blocks` (donc de l'année/du fichier choisis dans l'app)."""
    C = DEMO_I18N[lang]
    return {
        "kicker": C["kicker"],
        "title": C["title"],
        "subtitle": C["subtitle"],
        "hero_rates": build_hero_rates(blocks, lang),
        "intro": {"number": 1, "title": C["intro_title"], "text": C["intro"]},
        "glossary": build_glossary(lang, number=2),
        "distribution": build_distribution(blocks, lang, number=3),
        "indicators": build_indicators(blocks, lang, number=4),
        "key_points": build_key_points(lang, number=5),
        "source": C["source"],
    }


def render(spec: dict, lang: str, output_path: str) -> str:
    """Rendu du Type 1 : zone fixe (en-tête + 3 taux + intro/lexique +
    répartition) suivie de la zone flexible standard (indicateurs), puis
    finalisation."""
    img, draw, y, ctx = render_fixed_header_zone(spec, lang)
    y = render_flexible_standard(img, draw, y, spec, lang, ctx)
    return finalize(img, draw, y, spec, lang, output_path)
