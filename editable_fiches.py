#!/usr/bin/env python3
"""editable_fiches.py — Section « Fiches éditables » de l'app.

Donne accès aux 3 fiches HTML autonomes (générées par html_fiches/build_editable.py) :
téléchargement du fichier (où l'édition en place + export PDF fonctionnent
pleinement) et aperçu interactif intégré dans l'app pour essayer tout de suite.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HTML_DIR = Path(__file__).parent / "html_fiches"

FICHES = {
    "situation": {"label": "📊 Situation du marché du travail (2025)", "file": "situation_editable.html", "height": 1220},
    "emo": {"label": "📈 EMO 2026 — nouvelle enquête (arabe)", "file": "emo_editable.html", "height": 1760},
    "neet": {"label": "🎓 Les jeunes NEET (2024)", "file": "neet_editable.html", "height": 2240},
}


def render() -> None:
    st.markdown(
        '<div class="hcp-step"><span class="hcp-step-num">✏️</span>'
        "<h3>Fiches éditables — modifiez directement sur la fiche</h3></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Chaque fiche s'édite en place : cliquez sur un texte ou un chiffre pour le modifier, "
        "glissez pour déplacer, supprimez, annulez, puis exportez en PDF. Les anneaux et barres "
        "en couleur se recalculent quand vous changez leur pourcentage."
    )

    key = st.radio(
        "Fiche",
        options=list(FICHES),
        format_func=lambda k: FICHES[k]["label"],
        label_visibility="collapsed",
        horizontal=True,
    )
    f = FICHES[key]
    path = HTML_DIR / f["file"]
    if not path.exists():
        st.error(f"Fiche introuvable : {path.name}. Régénérez-la avec html_fiches/build_editable.py.")
        return
    html = path.read_text(encoding="utf-8")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.download_button(
            "⬇️ Télécharger la fiche éditable",
            data=html,
            file_name=f["file"],
            mime="text/html",
            help="Ouvrez le fichier téléchargé dans votre navigateur : c'est là que "
            "l'édition et l'export PDF sont les plus fiables (vos modifications sont conservées).",
        )
    with col2:
        st.info(
            "💡 Pour **conserver** vos modifications et obtenir un **PDF fidèle**, téléchargez le "
            "fichier et ouvrez-le dans votre navigateur (double-clic). L'aperçu ci-dessous sert "
            "à essayer l'édition ; il repart du modèle à chaque rechargement de la page."
        )

    st.divider()
    st.markdown("**Aperçu interactif** — essayez de cliquer sur un texte, un chiffre, un anneau :")
    components.html(html, height=f["height"], scrolling=True)
