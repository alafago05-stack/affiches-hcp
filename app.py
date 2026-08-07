#!/usr/bin/env python3
"""app.py — Interface Streamlit du générateur d'affiches HCP.

Point d'entrée unique : choix du type d'affiche, upload des fichiers Excel,
saisie des paramètres (année / jihat / trimestre / langue), génération et
téléchargement du PNG. Toute la logique de dessin vit dans `poster_engine.py`
(via `posters/*.py`) ; ce fichier ne fait qu'orchestrer les entrées/sorties et
afficher des messages d'erreur clairs (jamais de traceback brut).

L'identité visuelle de l'interface reprend la palette des affiches
(poster_engine.py) : fond crème #F7F5EC, marine #16323F, vert olive #A3B520,
or #E8A13C — bannière héro, badges numérotés et cartes chiffrées calqués sur
les sections des affiches. Les graphiques d'aperçu utilisent Altair (fourni
avec Streamlit) avec les mêmes couleurs d'indicateurs que les courbes des
affiches Type 2.

Lancer avec :
    streamlit run app.py
"""

import base64
import io
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

from parsers.annual import (
    AnnualExcelFormatError,
    get_rate,
    guess_region_from_filename,
    list_years,
    parse_ene_excel,
    validate_blocks,
)
from posters import quarter_compare, region_compare, standard, year_compare
import editable_fiches
import fiche_editor
import support

# Version affichée dans le pied de page et enregistrée avec chaque signalement
# de support (utile pour savoir sur quelle version un problème a été remonté).
APP_VERSION = "2026.07"

RENDERERS = {
    "type1_standard": standard.render,
    "type2_annees": year_compare.render,
    "type3_regions": region_compare.render,
    "type4_trimestres": quarter_compare.render,
}

# Exceptions natives levées par parse_ene_excel/get_value/get_rate (repris
# tels quels de generate_affiche.py) — voir parsers/annual.py pour pourquoi
# on ne les remplace pas par une exception "maison".
DATA_ERRORS = (AnnualExcelFormatError, KeyError, ValueError)

st.set_page_config(
    page_title="Générateur d'affiches HCP",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

LANG_LABELS = {"fr": "Français", "ar": "العربية", "en": "English"}
LANG_CODES = list(LANG_LABELS.keys())

POSTER_TYPES = {
    "standard": "📄  Type 1 — Affiche standard (une année, une région)",
    "year": "📈  Type 2 — Comparatif entre deux années",
    "region": "🗺️  Type 3 — Comparatif entre deux jihat (régions)",
    "quarter": "🗓️  Type 4 — Comparatif entre trimestres",
}

RATE_LABELS = {"TA": "Taux d'activité", "TE": "Taux d'emploi", "TC": "Taux de chômage"}
# Mêmes couleurs que les courbes de tendance des affiches Type 2
# (posters/year_compare.py) — l'aperçu et l'affiche racontent la même histoire.
RATE_COLORS = {"TA": "#4E9A50", "TE": "#3B6FA0", "TC": "#C44A3E"}

NAVY, OLIVE, GOLD, CREAM = "#16323F", "#A3B520", "#E8A13C", "#F7F5EC"
# Couleurs des séries des graphiques comparatifs (2 régions, jusqu'à 4 trimestres).
SERIES_PALETTE = [NAVY, GOLD, OLIVE, "#C44A3E"]

POSTER_SHORT = {
    "type1_standard": "Type 1",
    "type2_annees": "Type 2",
    "type3_regions": "Type 3",
    "type4_trimestres": "Type 4",
}


# ==========================================================================
# Identité visuelle (CSS + composants HTML maison)
# ==========================================================================
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --bg: #FAF9F5;            /* crème chaud (esprit Claude) */
    --surface: #FFFFFF;
    --surface-2: #F2F0E9;     /* panneaux / barre latérale */
    --ink: #20201D;           /* presque-noir chaud */
    --ink-soft: #6E6B63;
    --ink-faint: #9A968C;
    --border: #E7E3D8;
    --coral: #D97757;         /* accent signature */
    --coral-dark: #BE5D3C;
    --coral-soft: #F6E6DE;
    --shadow: 0 1px 2px rgba(20,20,19,.04), 0 8px 24px rgba(20,20,19,.06);
}

html, body, .stApp, .stApp * { font-family: 'Inter', 'Segoe UI', sans-serif; }
/* ne pas écraser la police d'icônes Material de Streamlit */
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
.stApp {
    background:
        radial-gradient(1100px 420px at 90% -10%, rgba(217,119,87,.06), transparent 60%),
        var(--bg);
    color: var(--ink);
}
.block-container { padding-top: 1.4rem; padding-left: 2.2rem; padding-right: 2.2rem; max-width: 1680px; }
h1, h2 { font-family: 'Fraunces', Georgia, serif; color: var(--ink); letter-spacing: -0.01em; font-weight: 600; }
h3, h4, h5 { font-family: 'Inter', sans-serif; color: var(--ink); font-weight: 600; }
#MainMenu, footer { visibility: hidden; }

/* ---- bannière héro : carte claire chaleureuse ---- */
.hcp-hero {
    background: linear-gradient(180deg, #FFFFFF 0%, #FBFAF6 100%);
    border: 1px solid var(--border);
    border-radius: 22px; padding: 30px 34px; margin-bottom: 18px;
    display: flex; align-items: center; justify-content: space-between; gap: 22px;
    box-shadow: var(--shadow); position: relative; overflow: hidden;
}
.hcp-hero::after {
    content: ""; position: absolute; right: -70px; bottom: -120px;
    width: 320px; height: 320px; border-radius: 50%;
    background: radial-gradient(circle, rgba(217,119,87,.12), transparent 70%);
}
.hcp-pill {
    display: inline-block; background: var(--coral-soft); color: var(--coral-dark);
    font-weight: 600; font-size: .72rem; letter-spacing: .06em;
    text-transform: uppercase; padding: 5px 13px; border-radius: 999px;
    border: 1px solid rgba(217,119,87,.25);
}
.hcp-hero h1 { font-family: 'Fraunces', Georgia, serif; color: var(--ink); font-size: 2.15rem; font-weight: 600; margin: .6rem 0 .3rem; line-height: 1.12; }
.hcp-hero p  { color: var(--ink-soft); margin: 0; font-size: 1rem; }
.hcp-logo-box {
    background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 10px 14px; flex: 0 0 auto;
    box-shadow: 0 4px 14px rgba(20,20,19,.06); z-index: 1;
}
.hcp-logo-box img { height: 62px; display: block; }

/* ---- badges d'étape numérotés ---- */
.hcp-step { display: flex; align-items: center; gap: .7rem; margin: 1.8rem 0 .8rem; }
.hcp-step-num {
    background: var(--coral); color: #fff; font-weight: 700; font-size: .95rem;
    width: 34px; height: 34px; border-radius: 50%; flex: 0 0 34px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 12px rgba(217,119,87,.32);
}
.hcp-step h3 { font-family: 'Fraunces', Georgia, serif; margin: 0; font-size: 1.3rem; font-weight: 600; }

/* ---- cartes chiffrées de l'aperçu ---- */
.hcp-metrics { display: flex; gap: 14px; flex-wrap: wrap; margin: .3rem 0 .9rem; }
.hcp-card {
    flex: 1 1 180px; background: var(--surface); border: 1px solid var(--border);
    border-top: 3px solid var(--c, var(--coral)); border-radius: 14px;
    padding: 15px 18px 16px; box-shadow: var(--shadow);
}
.hcp-card .lbl { font-size: .76rem; font-weight: 600; color: var(--ink-soft); text-transform: uppercase; letter-spacing: .05em; }
.hcp-card .val { font-family: 'Fraunces', Georgia, serif; font-size: 2.05rem; font-weight: 600; color: var(--ink); line-height: 1.15; }
.hcp-card .sub { font-size: .78rem; color: var(--ink-faint); margin-top: 2px; }
.hcp-delta {
    display: inline-block; font-size: .78rem; font-weight: 600;
    padding: 2px 10px; border-radius: 999px; margin-top: 6px;
}
.hcp-delta.good { background: #E8F0E6; color: #3B7A3F; }
.hcp-delta.bad  { background: var(--coral-soft); color: var(--coral-dark); }
.hcp-delta.flat { background: #EEEDE6; color: var(--ink-soft); }

/* ---- choix du type d'affiche : cartes cliquables ---- */
label[data-testid="stRadioOption"] {
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
    padding: 12px 16px; margin: 0 0 9px 0; width: 100%;
    transition: all .15s ease;
}
label[data-testid="stRadioOption"]:hover { border-color: var(--coral); background: #FFFDFB; }
label[data-testid="stRadioOption"][data-selected="true"] {
    border-color: var(--coral); background: var(--coral-soft);
    box-shadow: 0 3px 12px rgba(217,119,87,.18);
}

/* ---- boutons ---- */
.stButton button, .stDownloadButton button {
    border-radius: 12px; font-weight: 600; padding: .55rem 1.4rem;
    border: 1px solid var(--border); color: var(--ink); background: var(--surface);
    transition: all .15s ease;
}
.stButton button:hover { border-color: var(--coral); color: var(--coral-dark); }
.stButton button[kind="primary"], .stButton button[data-testid="stBaseButton-primary"] {
    background: var(--coral); border-color: var(--coral); color: #fff;
    box-shadow: 0 4px 14px rgba(217,119,87,.32);
}
.stButton button[kind="primary"]:hover { background: var(--coral-dark); border-color: var(--coral-dark); color: #fff; }
.stButton button:disabled { opacity: .45; box-shadow: none; }
.stDownloadButton button { background: var(--ink); color: #fff; border-color: var(--ink); }
.stDownloadButton button:hover { background: #000; color: #fff; border-color: #000; }

/* ---- zones de dépôt, expanders, images, chat ---- */
[data-testid="stFileUploaderDropzone"] {
    border: 1.5px dashed rgba(217,119,87,.55); background: #FBF6F3; border-radius: 14px;
}
[data-testid="stExpander"] {
    background: var(--surface); border: 1px solid var(--border) !important; border-radius: 14px !important;
    box-shadow: var(--shadow);
}
[data-testid="stImage"] img { border-radius: 16px; box-shadow: var(--shadow); }
[data-testid="stChatMessage"] { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; }
[data-testid="stNotification"], .stAlert { border-radius: 14px; }

/* ---- onglets FR/AR/EN ---- */
button[data-baseweb="tab"] { font-weight: 600; color: var(--ink-soft); }
button[data-baseweb="tab"][aria-selected="true"] { color: var(--ink); }
[data-baseweb="tab-highlight"] { background-color: var(--coral); height: 3px; border-radius: 3px; }

/* ---- pied de page ---- */
.hcp-footer {
    text-align: center; color: var(--ink-faint); font-size: .8rem;
    margin-top: 3rem; padding: 1.1rem 0 .4rem; border-top: 1px solid var(--border);
}

/* ---- barre latérale : panneau clair chaleureux (esprit Claude) ---- */
[data-testid="stSidebar"] { background: var(--surface-2); border-right: 1px solid var(--border); }
[data-testid="stSidebar"] * { color: var(--ink); }
[data-testid="stSidebar"] h2 { font-family: 'Fraunces', Georgia, serif; color: var(--ink); font-size: 1.05rem; font-weight: 600; }
[data-testid="stSidebar"] h2::before { content: "— "; color: var(--coral); }
[data-testid="stSidebar"] hr { border-color: var(--border); }
[data-testid="stSidebar"] [data-testid="stImage"] img {
    background: #fff; border: 1px solid var(--border); border-radius: 12px; padding: 8px; box-shadow: none;
}
[data-testid="stSidebar"] strong { color: var(--coral-dark); }
</style>
"""


@st.cache_data(show_spinner=False)
def _logo_b64() -> str:
    logo = Path(__file__).parent / "hcp_logo.png"
    return base64.b64encode(logo.read_bytes()).decode() if logo.exists() else ""


def _hero() -> None:
    logo_html = (
        f'<div class="hcp-logo-box"><img src="data:image/png;base64,{_logo_b64()}" alt="HCP"/></div>'
        if _logo_b64()
        else ""
    )
    st.markdown(
        f"""
        <div class="hcp-hero">
          <div>
            <span class="hcp-pill">Haut-Commissariat au Plan</span>
            <h1>Générateur d'affiches — Enquête Nationale sur l'Emploi</h1>
            <p>Affiches infographiques multilingues FR / AR / EN, fidèles à la maquette de référence.</p>
          </div>
          {logo_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _step(num: int, title: str) -> None:
    st.markdown(
        f'<div class="hcp-step"><span class="hcp-step-num">{num}</span><h3>{title}</h3></div>',
        unsafe_allow_html=True,
    )


def _fmt_pct(v: float) -> str:
    return f"{v:.1f}".replace(".", ",") + " %"


def _metric_cards(cards: list[dict]) -> None:
    """Rangée de cartes chiffrées maison. Chaque carte : {label, value, color,
    sub (optionnel), delta (optionnel, en points), delta_inverse (True si une
    hausse est une mauvaise nouvelle, ex. chômage)}."""
    html = ['<div class="hcp-metrics">']
    for c in cards:
        delta_html = ""
        if c.get("delta") is not None:
            d = c["delta"]
            if abs(d) < 0.05:
                cls, arrow = "flat", "→"
            else:
                good = (d < 0) if c.get("delta_inverse") else (d > 0)
                cls = "good" if good else "bad"
                arrow = "▲" if d > 0 else "▼"
            delta_html = (
                f'<span class="hcp-delta {cls}">{arrow} {f"{d:+.1f}".replace(".", ",")} pt</span>'
            )
        sub_html = f'<div class="sub">{c["sub"]}</div>' if c.get("sub") else ""
        html.append(
            f'<div class="hcp-card" style="--c:{c.get("color", OLIVE)}">'
            f'<div class="lbl">{c["label"]}</div>'
            f'<div class="val">{c["value"]}</div>'
            f"{delta_html}{sub_html}</div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _chart_theme(chart: alt.Chart) -> alt.Chart:
    """Habillage commun des graphiques Altair : fond transparent, axes marine,
    grille discrète, police Manrope."""
    return (
        chart.configure(background="transparent", font="Manrope, Segoe UI, sans-serif")
        .configure_axis(
            labelColor=NAVY, titleColor=NAVY, gridColor="#E4E1D2",
            domainColor="#CBC8B8", tickColor="#CBC8B8", labelFontSize=12, labelFontWeight=600,
        )
        .configure_legend(labelColor=NAVY, labelFontSize=12, labelFontWeight=700, orient="top", title=None)
        .configure_view(strokeWidth=0)
    )


def _trend_chart(df: pd.DataFrame, highlight_years: list[str] | None = None) -> None:
    """Courbe d'évolution interactive TA/TE/TC (mêmes couleurs que les
    affiches Type 2), avec survol : point le plus proche mis en avant et
    valeurs des trois taux affichées."""
    long = (
        df.rename(columns=RATE_LABELS)
        .reset_index(names="Année")
        .melt("Année", var_name="Indicateur", value_name="Taux")
        .dropna(subset=["Taux"])
    )
    color = alt.Color(
        "Indicateur:N",
        scale=alt.Scale(
            domain=[RATE_LABELS[c] for c in ("TA", "TE", "TC")],
            range=[RATE_COLORS[c] for c in ("TA", "TE", "TC")],
        ),
    )
    hover = alt.selection_point(fields=["Année"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(long).encode(
        x=alt.X("Année:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Taux:Q", title="%", scale=alt.Scale(zero=False, padding=12)),
        color=color,
    )
    lines = base.mark_line(strokeWidth=3, interpolate="monotone")
    points = base.mark_circle(size=70).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0.55)),
        size=alt.condition(hover, alt.value(160), alt.value(70)),
        tooltip=[
            alt.Tooltip("Année:O"),
            alt.Tooltip("Indicateur:N"),
            alt.Tooltip("Taux:Q", format=".1f", title="Taux (%)"),
        ],
    ).add_params(hover)
    layers = [lines, points]
    if highlight_years:
        # Règles verticales sur les années comparées (Type 2).
        rules = (
            alt.Chart(pd.DataFrame({"Année": [str(y) for y in highlight_years]}))
            .mark_rule(strokeDash=[5, 4], stroke=GOLD, strokeWidth=2)
            .encode(x="Année:O")
        )
        layers.insert(0, rules)
    chart = _chart_theme(alt.layer(*layers).properties(height=290))
    st.altair_chart(chart, width="stretch", theme=None)
    st.caption(
        "Évolution des trois taux (Ensemble) sur toutes les années exploitables du fichier — "
        "survolez les points pour lire les valeurs exactes."
    )


def _compare_bar_chart(rows: list[dict], series_name: str = "Région") -> None:
    """Barres groupées horizontales (2 régions ou 2 à 4 trimestres), valeurs
    affichées au bout des barres — même logique visuelle que les barres
    comparatives des affiches Type 3/4. `rows` : [{Indicateur, <series_name>,
    Taux}]."""
    df = pd.DataFrame(rows).dropna(subset=["Taux"])
    if df.empty:
        return
    series = list(dict.fromkeys(df[series_name]))
    color = alt.Color(
        f"{series_name}:N",
        scale=alt.Scale(domain=series, range=SERIES_PALETTE[: len(series)]),
    )
    base = alt.Chart(df).encode(
        y=alt.Y("Indicateur:N", title=None, sort=list(RATE_LABELS.values())),
        yOffset=f"{series_name}:N",
        x=alt.X("Taux:Q", title="%", scale=alt.Scale(padding=14)),
        color=color,
        tooltip=[
            alt.Tooltip(f"{series_name}:N"),
            alt.Tooltip("Indicateur:N"),
            alt.Tooltip("Taux:Q", format=".1f", title="Taux (%)"),
        ],
    )
    bars = base.mark_bar(cornerRadiusEnd=5, height=15)
    labels = base.mark_text(align="left", dx=5, fontWeight=700, fontSize=11.5, color=NAVY).encode(
        text=alt.Text("Taux:Q", format=".1f")
    )
    # Hauteur adaptée au nombre de séries (3 indicateurs × N barres).
    chart = _chart_theme((bars + labels).properties(height=100 + 55 * len(series)))
    st.altair_chart(chart, width="stretch", theme=None)


# ==========================================================================
# Helpers (parsing avec cache, aperçu des données, génération mono/multilingue)
# ==========================================================================
@st.cache_data(show_spinner=False)
def _cached_parse(file_bytes: bytes, year: str) -> dict:
    """Parse une feuille-année depuis les octets du fichier uploadé. Le cache
    évite de relire le classeur à chaque interaction Streamlit."""
    return parse_ene_excel(io.BytesIO(file_bytes), year)


@st.cache_data(show_spinner=False)
def _rates_over_years(file_bytes: bytes) -> pd.DataFrame:
    """TA/TE/TC (Ensemble) pour chaque feuille-année exploitable du fichier —
    alimente l'aperçu chiffré et la courbe d'évolution. Les feuilles au format
    incompatible sont simplement omises."""
    try:
        years = list_years(io.BytesIO(file_bytes))
    except AnnualExcelFormatError:
        return pd.DataFrame()
    data = {}
    for yr in sorted(years, key=int):
        try:
            blocks = _cached_parse(file_bytes, yr)
            row = {}
            for code in RATE_LABELS:
                _, pct = get_rate(blocks, code)
                row[code] = pct
            data[yr] = row
        except Exception:
            continue
    return pd.DataFrame.from_dict(data, orient="index")


def _evolution_phrase(code: str, delta: float) -> str:
    """Décrit en français l'évolution d'un taux (hausse/baisse/stabilité) sur
    l'écart en points fourni — formulation neutre, réutilisable telle quelle
    dans les points saillants de l'affiche."""
    label = RATE_LABELS[code].lower()
    pts = f"{abs(delta):.1f}".replace(".", ",")
    if abs(delta) < 0.05:
        return f"le {label} est resté stable"
    sens = "progressé" if delta > 0 else "reculé"
    return f"le {label} a {sens} de {pts} point{'s' if abs(delta) >= 2 else ''}"


def _auto_reading(df: pd.DataFrame, ref_year: str, prev_year: str = None) -> list[str]:
    """Lecture automatique des données : 2 à 4 phrases factuelles décrivant les
    niveaux de l'année de référence, leur évolution depuis l'année comparée, et
    les extrêmes de la série. Pensée comme aide à la rédaction des points
    saillants — l'utilisateur peut les copier telles quelles."""
    bullets = []
    if ref_year not in df.index:
        return bullets
    ta, te, tc = (df.loc[ref_year, c] for c in ("TA", "TE", "TC"))
    if pd.notna(ta) and pd.notna(tc):
        bullets.append(
            f"En **{ref_year}**, le taux d'activité s'établit à **{_fmt_pct(ta)}** et le taux de "
            f"chômage à **{_fmt_pct(tc)}** (ensemble, urbain et rural confondus)."
        )
    if prev_year and prev_year in df.index and prev_year != ref_year:
        parts = []
        for code in ("TA", "TE", "TC"):
            cur, prev = df.loc[ref_year, code], df.loc[prev_year, code]
            if pd.notna(cur) and pd.notna(prev):
                parts.append(_evolution_phrase(code, float(cur - prev)))
        if parts:
            bullets.append(
                f"Entre **{prev_year}** et **{ref_year}**, " + ", ".join(parts) + "."
            )
    # Extrêmes de la série sur le chômage (indicateur le plus suivi).
    tc_series = df["TC"].dropna()
    if len(tc_series) >= 3:
        hi, lo = tc_series.idxmax(), tc_series.idxmin()
        if hi != lo:
            bullets.append(
                f"Sur l'ensemble des années disponibles, le chômage a culminé en **{hi}** "
                f"({_fmt_pct(tc_series[hi])}) et atteint son plus bas en **{lo}** "
                f"({_fmt_pct(tc_series[lo])})."
            )
    return bullets


def _indicators_csv(df: pd.DataFrame) -> bytes:
    """Exporte les indicateurs extraits (une ligne par année) en CSV UTF-8-BOM
    — le BOM permet à Excel d'ouvrir directement le fichier avec les accents
    corrects et les séparateurs français."""
    out = df.rename(columns={c: f"{RATE_LABELS[c]} (%)" for c in RATE_LABELS}).copy()
    out.index.name = "Année"
    return out.round(1).to_csv(sep=";", decimal=",").encode("utf-8-sig")


def _data_preview(file_bytes: bytes, year: str = None, year_a: str = None, year_b: str = None) -> None:
    """Expander « Aperçu des données » : cartes chiffrées des 3 taux clés
    (avec écart si l'on compare deux années), courbe d'évolution interactive,
    lecture automatique des données et export CSV. Purement informatif :
    permet de vérifier les chiffres AVANT de générer l'affiche."""
    df = _rates_over_years(file_bytes)
    with st.expander("📊 Aperçu des données du fichier", expanded=True):
        if df.empty:
            st.info("Aucune feuille exploitable trouvée pour l'aperçu.")
            return
        compare = year_a is not None and year_b is not None and year_a != year_b
        ref_year = str(year_b) if compare else (str(year) if year is not None else None)
        prev_year = str(year_a) if compare else None
        if ref_year in df.index:
            cards = []
            for code in RATE_LABELS:
                val = df.loc[ref_year, code]
                if val is None or pd.isna(val):
                    continue
                delta = None
                if compare and str(year_a) in df.index:
                    prev = df.loc[str(year_a), code]
                    if prev is not None and not pd.isna(prev):
                        delta = float(val - prev)
                cards.append(
                    {
                        "label": f"{RATE_LABELS[code]} · {ref_year}",
                        "value": _fmt_pct(val),
                        "color": RATE_COLORS[code],
                        "delta": delta,
                        "delta_inverse": code == "TC",
                        "sub": f"depuis {year_a}" if delta is not None else "Ensemble (urbain + rural)",
                    }
                )
            _metric_cards(cards)
        if len(df) >= 2:
            _trend_chart(df, highlight_years=[year_a, year_b] if compare else None)
        reading = _auto_reading(df, ref_year, prev_year) if ref_year else []
        if reading:
            st.markdown("**📝 Lecture automatique** — à réutiliser dans les points saillants :")
            for b in reading:
                st.markdown(f"- {b}")
        st.download_button(
            "⬇️ Exporter les indicateurs (CSV)",
            data=_indicators_csv(df),
            file_name="indicateurs_ene.csv",
            mime="text/csv",
            help="Les trois taux (Ensemble) pour toutes les années exploitables, ouvrable dans Excel.",
        )


def _png_to_pdf(pngs: list[bytes]) -> bytes:
    """Convertit une ou plusieurs affiches PNG en un PDF (une page par
    affiche) — pratique pour l'impression et l'envoi officiel. Aucune
    dépendance supplémentaire : Pillow écrit le PDF directement."""
    imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in pngs]
    buf = io.BytesIO()
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:], resolution=150.0)
    return buf.getvalue()


def _push_history(entry: dict) -> None:
    """Ajoute une affiche à l'historique de session (les 8 dernières)."""
    hist = st.session_state.setdefault("history", [])
    hist.insert(0, entry)
    del hist[8:]


def _generate(poster_key: str, lang: str, build_spec, all_langs: bool = False, context: str = "") -> None:
    """Rend l'affiche (dans la langue choisie, ou les 3 langues si demandé) et
    stocke le résultat dans la session pour affichage + téléchargement, en
    capturant toute erreur dans un message lisible. `context` décrit les
    paramètres (année, régions…) pour l'historique de session.

    `build_spec` est un callable lang -> spec : la spec dépend de la langue
    (titres, libellés traduits), il faut donc la reconstruire par langue."""
    try:
        langs = LANG_CODES if all_langs else [lang]
        results = {}
        with st.spinner("Génération de l'affiche…" if not all_langs else "Génération des 3 langues…"):
            for lg in langs:
                spec = build_spec(lg)
                out_path = str(Path(tempfile.gettempdir()) / f"affiche_{poster_key}_{lg}.png")
                RENDERERS[poster_key](spec, lg, out_path)
                with open(out_path, "rb") as f:
                    results[lg] = f.read()
        if all_langs:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for lg, png in results.items():
                    zf.writestr(f"affiche_{poster_key}_{lg}.png", png)
            st.session_state["generated_zip"] = buf.getvalue()
            st.session_state["generated_zip_name"] = f"affiches_{poster_key}_fr_ar_en.zip"
            st.session_state["generated_all"] = results
        else:
            st.session_state.pop("generated_zip", None)
            st.session_state.pop("generated_all", None)
        st.session_state["generated_png"] = results[lang]
        st.session_state["generated_name"] = f"affiche_{poster_key}_{lang}.png"
        st.session_state["generated_key"] = poster_key
        st.session_state["generated_lang"] = lang
        st.session_state.pop("generation_error", None)
        lang_label = "FR + AR + EN" if all_langs else LANG_LABELS[lang]
        _push_history(
            {
                "label": " · ".join(x for x in (POSTER_SHORT[poster_key], context, lang_label) if x),
                "time": datetime.now().strftime("%H:%M"),
                "png": results[lang],
                "name": f"affiche_{poster_key}_{lang}.png",
            }
        )
    except DATA_ERRORS as exc:
        st.session_state["generation_error"] = str(exc)
        st.session_state.pop("generated_png", None)
        st.session_state.pop("generated_zip", None)
        st.session_state.pop("generated_all", None)
    except Exception as exc:  # garde-fou : jamais de traceback brut à l'écran
        st.session_state["generation_error"] = f"Erreur inattendue lors de la génération : {exc}"
        st.session_state.pop("generated_png", None)
        st.session_state.pop("generated_zip", None)
        st.session_state.pop("generated_all", None)


def _check_file_data(file_bytes: bytes, year: str, label: str = "") -> bool:
    """Valide AVANT génération que la feuille `year` contient toutes les
    données requises par les affiches (TA/TE/TC, sous-emploi, population en
    âge de travailler…). Affiche la liste exacte de ce qui manque et retourne
    False sinon — le bouton « Générer » est alors désactivé."""
    try:
        blocks = _cached_parse(file_bytes, year)
    except DATA_ERRORS as exc:
        st.error(f"{label}Feuille {year} illisible : {exc}")
        return False
    missing = validate_blocks(blocks)
    if missing:
        st.error(
            f"{label}Ce fichier ne contient pas toutes les données requises "
            f"pour la feuille **{year}** :\n\n- " + "\n- ".join(missing)
        )
        return False
    return True


def _read_years(uploaded_file):
    """Liste les années disponibles dans un fichier uploadé, en gérant
    proprement les erreurs de format."""
    try:
        uploaded_file.seek(0)
        return list_years(uploaded_file), None
    except AnnualExcelFormatError as exc:
        return [], str(exc)


def _parse_years_in_range(file_bytes: bytes, year_a: str, year_b: str) -> dict:
    """Parse toutes les feuilles-années entre year_a et year_b (bornes
    incluses), en ignorant silencieusement celles dont le format de feuille
    est incompatible (comme le fait la CLI de référence) — utilisé pour les
    courbes de tendance du Type 2."""
    y0, y1 = sorted([int(year_a), int(year_b)])
    try:
        all_years = list_years(io.BytesIO(file_bytes))
    except AnnualExcelFormatError:
        return {}
    blocks_by_year = {}
    for yr in all_years:
        if y0 <= int(yr) <= y1:
            try:
                blocks_by_year[yr] = _cached_parse(file_bytes, yr)
            except Exception:
                continue  # feuille présente mais format incompatible : on l'ignore
    return blocks_by_year


# ==========================================================================
# Mise en page
# ==========================================================================
st.markdown(_CSS, unsafe_allow_html=True)

with st.sidebar:
    _logo = Path(__file__).parent / "hcp_logo.png"
    if _logo.exists():
        st.image(str(_logo), width=96)
    nav_page = st.radio(
        "Navigation",
        options=["editable", "generator", "support"],  # « Fiches éditables » = page d'accueil
        format_func=lambda k: {
            "editable": "✏️ Fiches éditables",
            "generator": "🎨 Générateur d'affiches",
            "support": "💬 Support",
        }[k],
        key="nav_page",
    )
    st.divider()
    st.markdown("## Mode d'emploi")
    st.markdown(
        "1. Choisissez le **type d'affiche**\n"
        "2. Choisissez la **langue** (ou activez « 3 langues » pour tout générer d'un coup)\n"
        "3. Déposez le(s) **fichier(s) Excel** ENE\n"
        "4. Vérifiez les chiffres dans l'**aperçu des données**\n"
        "5. Cliquez sur **Générer l'affiche** puis téléchargez le PNG"
    )
    st.divider()
    st.markdown("## Fichiers acceptés")
    st.markdown(
        "Exports Excel **« ENE — Indicateurs désagrégés »** (une feuille par année). "
        "Les trois variantes de mise en page des feuilles (2019-2020, 2021, 2022-2025) "
        "sont prises en charge, ainsi que les fichiers légèrement désordonnés "
        "(colonnes décalées, titres mal formatés, nombres en texte)."
    )
    st.divider()
    st.caption(
        "Haut-Commissariat au Plan — Enquête Nationale sur l'Emploi. "
        "Affiches générées en FR / AR / EN, fidèles à la maquette de référence."
    )

_hero()

# La page « Support » (chatbot + suivi des signalements) remplace le
# générateur : on l'affiche puis on arrête le script pour ne pas dérouler
# toute l'interface de génération en dessous.
if nav_page in ("support", "editable"):
    if nav_page == "support":
        support.render(APP_VERSION)
    else:
        editable_fiches.render()
    st.markdown(
        f'<div class="hcp-footer">Haut-Commissariat au Plan — Enquête Nationale sur l\'Emploi · '
        f"Générateur d'affiches multilingues · v{APP_VERSION}</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# ======================================================================
# GÉNÉRATEUR v2 — les 4 nouvelles fiches éditables (voir fiche_editor.py).
# L'ancien générateur (comparaison années/régions/trimestres) reste dans
# git et dans posters/ ; il est simplement retiré du menu.
# ======================================================================
fiche_editor.render_generator(APP_VERSION)

st.markdown(
    f'<div class="hcp-footer">Haut-Commissariat au Plan — Enquête Nationale sur l\'Emploi · '
    f"Générateur d'affiches multilingues · v{APP_VERSION}</div>",
    unsafe_allow_html=True,
)
