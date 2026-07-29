#!/usr/bin/env python3
"""editable_fiches.py — Section « Fiches éditables » de l'app.

Donne accès aux 3 fiches HTML autonomes (générées par html_fiches/build_editable.py) :
téléchargement du fichier (où l'édition en place + export PDF fonctionnent
pleinement), aperçu interactif intégré, et un assistant IA (Gemini) qui aide à
améliorer le contenu et peut appliquer ses propositions directement à la fiche.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import ai_assistant

HTML_DIR = Path(__file__).parent / "html_fiches"

# Hauteurs d'aperçu embarqué — approximatives : la fiche se met à l'échelle
# de la largeur de l'iframe (~970px dans l'app), donc sa hauteur visible varie
# un peu selon l'écran ; scrolling=True absorbe l'écart. NEET (1488px de large)
# est fortement réduite, d'où une hauteur plus basse.
FICHES = {
    "situation": {"label": "📊 Situation du marché du travail (2025)", "file": "situation_editable.html", "height": 1270},
    "emo": {"label": "📈 EMO 2026 — nouvelle enquête (arabe)", "file": "emo_editable.html", "height": 1690},
    "neet": {"label": "🎓 Les jeunes NEET (2024)", "file": "neet_editable.html", "height": 1500},
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
    base_html = path.read_text(encoding="utf-8")

    # HTML courant = version modifiée par l'IA si elle existe, sinon l'original.
    html_key = f"ai_html_{key}"
    cur_html = st.session_state.get(html_key, base_html)
    modified = html_key in st.session_state

    col1, col2 = st.columns([1, 2])
    with col1:
        st.download_button(
            "⬇️ Télécharger le modèle" + (" (modifié)" if modified else " (vierge)"),
            data=cur_html,
            file_name=f["file"],
            mime="text/html",
            help="Ouvrez-le dans votre navigateur pour éditer en place et exporter le PDF.",
        )
    with col2:
        st.info(
            "💡 Modifiez la fiche ci-dessous, puis cliquez sur **💾 Enregistrer** dans sa barre "
            "d'outils : cela télécharge un HTML **avec vos changements**, réouvrable et à nouveau "
            "éditable. **⬇️ Exporter en PDF** télécharge directement le PDF final (A4)."
        )

    _render_ai(key, cur_html, modified)

    st.divider()
    st.markdown("**Aperçu interactif** — essayez de cliquer sur un texte, un chiffre, un anneau :")
    if modified:
        st.caption("✏️ Cet aperçu reflète les modifications appliquées par l'assistant IA.")
    components.html(cur_html, height=f["height"], scrolling=True)


def _render_ai(key: str, cur_html: str, modified: bool) -> None:
    """Assistant IA : chat contextuel + bouton « Appliquer » sur la fiche.

    Sécurité : la clé n'est lue que côté serveur (st.secrets) ; l'IA ne renvoie
    jamais de HTML — seulement des textes appliqués de façon échappée. Voir
    ai_assistant.py."""
    with st.container(border=True):
        st.markdown("#### 🤖 Assistant IA — améliorer le contenu de la fiche")

        if not ai_assistant.is_configured():
            with st.expander("🔒 Assistant IA désactivé — comment l'activer ?"):
                st.markdown(
                    "Aucune clé Gemini n'est configurée (le reste de l'app fonctionne normalement).\n\n"
                    "1. Récupérez une clé gratuite sur "
                    "[Google AI Studio](https://aistudio.google.com/apikey) (elle commence par `AIza…`).\n"
                    "2. **En local** : copiez `.streamlit/secrets.toml.example` en "
                    "`.streamlit/secrets.toml` et collez la clé sous `[gemini]`.\n"
                    "3. **En ligne** (Streamlit Cloud) : votre app > **Settings > Secrets**, "
                    "collez-y le bloc `[gemini]`.\n\n"
                    "✅ **Une seule fois** : après ça, le chat fonctionne **pour tous les "
                    "visiteurs** — personne d'autre n'a de clé à saisir.\n\n"
                    "🔐 La clé reste **côté serveur** : elle n'est jamais envoyée au navigateur "
                    "ni écrite dans la fiche (indispensable ici, le dépôt étant public)."
                )
            return

        msgs_key = f"ai_msgs_{key}"
        msgs = st.session_state.setdefault(msgs_key, [])

        if not msgs:
            st.caption(
                "Demandez une amélioration du texte : reformuler, raccourcir, corriger les "
                "fautes, traduire en arabe, proposer des points saillants… "
                "L'assistant ne change pas les chiffres sauf si vous le demandez."
            )

        for m in msgs:
            with st.chat_message("user" if m["role"] == "user" else "assistant"):
                st.markdown(m["content"])

        # Bouton « Appliquer » sur la DERNIÈRE proposition non appliquée
        # (indices de segments frais → application fiable).
        last = msgs[-1] if msgs and msgs[-1]["role"] == "assistant" else None
        if last and last.get("edits") and not last.get("applied"):
            st.caption(f"💡 {len(last['edits'])} modification(s) proposée(s) pour la fiche.")
            c1, c2 = st.columns([1, 1])
            if c1.button("✅ Appliquer à la fiche", key=f"apply_{key}", type="primary"):
                new_html, n = ai_assistant.apply_edits(cur_html, last["edits"])
                last["applied"] = True
                st.session_state[f"ai_html_{key}"] = new_html
                st.session_state[msgs_key] = msgs
                st.toast(f"✅ {n} modification(s) appliquée(s).")
                st.rerun()
            if c2.button("Ignorer", key=f"ignore_{key}"):
                last["applied"] = True
                st.session_state[msgs_key] = msgs
                st.rerun()

        # Zone de saisie
        with st.form(f"ai_form_{key}", clear_on_submit=True):
            q = st.text_area(
                "Votre demande",
                placeholder="ex : raccourcis l'introduction et corrige les fautes ; "
                "traduis le titre en arabe ; propose 3 points saillants…",
                label_visibility="collapsed",
                height=70,
            )
            sent = st.form_submit_button("Envoyer", type="primary")

        cols = st.columns([1, 1, 2])
        if msgs and cols[0].button("🗑️ Effacer le chat", key=f"clear_{key}"):
            st.session_state.pop(msgs_key, None)
            st.rerun()
        if modified and cols[1].button("↩️ Revenir au texte original", key=f"reset_{key}"):
            st.session_state.pop(f"ai_html_{key}", None)
            st.rerun()

        if sent and q.strip():
            msgs.append({"role": "user", "content": q.strip()})
            with st.spinner("L'assistant réfléchit…"):
                try:
                    segs = ai_assistant.extract_segments(cur_html)
                    reply, edits = ai_assistant.converse(msgs, q.strip(), segs)
                except Exception as exc:  # clé invalide, paquet manquant, erreur API…
                    reply, edits = f"⚠️ {exc}", []
            msgs.append({"role": "assistant", "content": reply, "edits": edits, "applied": False})
            st.session_state[msgs_key] = msgs
            st.rerun()
