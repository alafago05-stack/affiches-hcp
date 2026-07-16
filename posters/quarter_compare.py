#!/usr/bin/env python3
"""posters/quarter_compare.py — Type 4 : comparatif entre trimestres d'une
même année. Reprend `build_quarter_compare_spec` de `generate_affiche.py` à
l'identique : zone fixe basée sur le dernier trimestre fourni, zone
flexible en barres comparatives (2 à 4 entités) pour TA/TE/TC.

STATUT : chaque fichier Excel trimestriel est parsé avec le même
`parse_ene_excel` que les fichiers annuels (même feuille/année pour tous les
trimestres) — c'est l'hypothèse posée par `generate_affiche.py`. Elle n'a
pas encore été vérifiée contre un vrai export trimestriel du HCP (le seul
exemple fourni jusqu'ici était une affiche déjà mise en forme, pas un
tableur). Si un fichier trimestriel réel s'avère structuré différemment,
il faudra l'adapter ici.
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


def build_spec(blocks_list: list, quarter_labels: list, year_label: str, lang: str) -> dict:
    """Construit le spec du comparatif Type 4 à partir de 2 à 4 jeux de
    blocs déjà parsés (un par trimestre), tous sur la même feuille/année."""
    T = COMPARE_I18N[lang]
    C = DEMO_I18N[lang]
    items = []
    for code, label in zip(["TA", "TE", "TC"], T["indicators"]):
        values, pcts = [], []
        for blocks_q in blocks_list:
            v, p = get_rate(blocks_q, code, lang=lang)
            values.append(v)
            pcts.append(p)
        items.append({"label": label, "values": values, "pcts": pcts})

    return {
        "kicker": C["kicker"],
        "title": T["title_quarter"].format(year=year_label),
        "subtitle": T["subtitle_quarter"],
        "hero_rates": build_hero_rates(blocks_list[-1], lang),
        "intro": {"number": 1, "title": C["intro_title"], "text": T["intro_quarter"].format(year=year_label)},
        "glossary": build_glossary(lang, number=2),
        "distribution": build_distribution(blocks_list[-1], lang, number=3),
        "compare_bars": {"number": 4, "title": T["compare_section_title"],
                          "entities": quarter_labels, "items": items},
        "key_points": build_key_points(lang, number=5),
        "source": T["source"],
    }


def render(spec: dict, lang: str, output_path: str) -> str:
    """Rendu du Type 4 : zone fixe suivie de la zone flexible comparative
    (barres), puis finalisation."""
    img, draw, y, ctx = render_fixed_header_zone(spec, lang)
    y = render_flexible_compare(img, draw, y, spec, lang, ctx)
    return finalize(img, draw, y, spec, lang, output_path)
