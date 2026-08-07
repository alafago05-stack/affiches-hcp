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
import fiche_store

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

    # HTML courant = modifs de la session en cours ; sinon la version PERSISTÉE
    # (survit au rafraîchissement de la page) ; sinon la fiche d'origine.
    html_key = f"ai_html_{key}"
    persisted = fiche_store.load(key)
    cur_html = st.session_state.get(html_key, persisted or base_html)
    modified = (html_key in st.session_state) or (persisted is not None)

    # Thème de couleurs (design) — persisté, orthogonal au contenu.
    themes = ai_assistant.theme_labels()
    theme_key = f"theme_{key}"
    if theme_key not in st.session_state:
        st.session_state[theme_key] = fiche_store.load_theme(key) or "bordeaux"
    theme = st.session_state[theme_key]
    display_html = ai_assistant.recolor(cur_html, theme)  # ce qu'on montre/télécharge
    changed = modified or theme != "bordeaux"

    top1, top2, top3 = st.columns([1.3, 1, 2])
    with top1:
        st.download_button(
            "⬇️ Télécharger" + (" (modifié)" if changed else " (vierge)"),
            data=display_html,
            file_name=f["file"],
            mime="text/html",
            help="Ouvrez-le dans votre navigateur pour éditer en place et exporter le PDF.",
        )
    with top2:
        st.selectbox("🎨 Design (couleurs)", options=list(themes),
                     format_func=lambda k: themes[k], key=theme_key)
        if st.session_state[theme_key] != (fiche_store.load_theme(key) or "bordeaux"):
            fiche_store.save_theme(key, st.session_state[theme_key])
    with top3:
        st.info(
            "💡 L'assistant est à **gauche**, l'aperçu à **droite** : vos modifications "
            "s'affichent **en direct**. **⬇️ Exporter en PDF** se trouve dans la barre d'outils de la fiche."
        )

    st.divider()
    # Côte à côte : assistant IA à gauche, aperçu de la fiche à droite (live).
    col_chat, col_fiche = st.columns([5, 7], gap="large")
    with col_chat:
        _render_ai(key, cur_html, modified)
    with col_fiche:
        st.markdown("**🔎 Aperçu en direct**")
        if changed:
            st.caption("💾 Enregistré — persiste au rafraîchissement (design inclus).")
        components.html(display_html, height=850, scrolling=True)


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
                    "[Google AI Studio](https://aistudio.google.com/apikey) "
                    "(format `AIza…` ou `AQ.…`, les deux marchent).\n"
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

        def send(ask, media=None, doc_text="", labels=None):
            """Envoie une demande à l'assistant (utilisé par le formulaire ET
            les actions rapides)."""
            shown = (ask or "").strip() + (("\n\n📎 " + ", ".join(labels)) if labels else "")
            msgs.append({"role": "user", "content": shown or "📎 (fichiers joints)"})
            real = (ask or "").strip() or "Utilise le(s) fichier(s) joint(s) pour proposer des ajouts à la fiche."
            with st.spinner("L'assistant réfléchit…"):
                try:
                    segs = ai_assistant.extract_segments(cur_html)
                    reply, ops = ai_assistant.converse(
                        msgs, real, segs, media=media or [], doc_text=doc_text)
                except Exception as exc:  # clé invalide, paquet manquant, erreur API…
                    reply, ops = str(exc), []
            msgs.append({"role": "assistant", "content": reply, "ops": ops, "applied": False})
            st.session_state[msgs_key] = msgs
            st.rerun()

        if not msgs:
            st.caption(
                "Demandez tout : **corriger / reformuler / traduire** un texte, le **mettre "
                "en forme** (couleur, gras, taille), **ajouter** un tableau, un graphique "
                "(barres/courbe), une **liste** de points, un **chiffre-clé** ou un **anneau %**, "
                "ou **supprimer** un élément. Joignez une image / un PDF / un Excel pour en "
                "extraire les données. Les éléments ajoutés se déplacent à la souris ; les "
                "chiffres existants ne changent que si vous le demandez."
            )

        for m in msgs:
            with st.chat_message("user" if m["role"] == "user" else "assistant"):
                st.markdown(m["content"])

        # Bouton « Appliquer » sur la DERNIÈRE proposition non appliquée
        # (indices de segments frais → application fiable).
        last = msgs[-1] if msgs and msgs[-1]["role"] == "assistant" else None
        if last and last.get("ops") and not last.get("applied"):
            ops = last["ops"]
            st.caption(f"💡 {len(ops)} opération(s) proposée(s) :")
            for o in ops[:8]:
                st.caption("• " + ai_assistant.op_summary(o))
            c1, c2 = st.columns([1, 1])
            if c1.button("✅ Appliquer à la fiche", key=f"apply_{key}", type="primary"):
                undo = st.session_state.setdefault(f"ai_undo_{key}", [])
                undo.append(cur_html)   # état AVANT application (pour « Annuler »)
                del undo[:-10]          # on garde les 10 derniers
                new_html, n = ai_assistant.apply_ops(cur_html, ops)
                last["applied"] = True
                st.session_state[f"ai_html_{key}"] = new_html
                fiche_store.save(key, new_html)  # persiste (survit au rafraîchissement)
                st.session_state[msgs_key] = msgs
                st.toast(f"✅ {n} opération(s) appliquée(s) — enregistrée(s).")
                st.rerun()
            if c2.button("Ignorer", key=f"ignore_{key}"):
                last["applied"] = True
                st.session_state[msgs_key] = msgs
                st.rerun()

        # Actions rapides (un clic = une demande prête à l'emploi)
        QUICK = [
            ("🔤 Corriger", "Corrige toutes les fautes d'orthographe et de grammaire des textes de la fiche (op replace)."),
            ("🇲🇦 En arabe", "Traduis en arabe les principaux titres et l'introduction de la fiche (op replace)."),
            ("✨ Points clés", "Ajoute une liste (op add_list) de 3 à 4 points saillants qui synthétisent la fiche."),
            ("📊 Tableau", "Ajoute un tableau (op add_table) pertinent qui résume des données présentes dans la fiche."),
            ("📈 Graphique", "Ajoute un graphique (op add_chart) illustrant une évolution ou une comparaison de la fiche."),
            ("🎨 Mise en forme", "Améliore la mise en forme : mets en valeur le titre et les chiffres clés (op style, couleurs bordeaux #7a1c3f / or #c8992e)."),
        ]
        st.caption("Actions rapides :")
        for start in range(0, len(QUICK), 3):          # 3 par ligne (colonne étroite)
            chunk = QUICK[start:start + 3]
            cols = st.columns(len(chunk))
            for j, (label, prompt) in enumerate(chunk):
                if cols[j].button(label, key=f"q_{key}_{start + j}", use_container_width=True):
                    send(prompt)

        # Zone de saisie
        with st.form(f"ai_form_{key}", clear_on_submit=True):
            q = st.text_area(
                "Votre demande",
                placeholder="ex : ajoute un tableau du chômage par région ; ajoute un "
                "graphique en barres 2024 vs 2025 ; raccourcis l'intro ; traduis en arabe…",
                label_visibility="collapsed",
                height=70,
            )
            up = st.file_uploader(
                "📎 Joindre une image, un PDF ou un Excel/CSV (facultatif) — "
                "l'IA lit son contenu pour créer un tableau/graphique",
                type=ai_assistant.UPLOAD_TYPES,
                accept_multiple_files=True,
                key=f"upl_{key}",
            )
            sent = st.form_submit_button("Envoyer", type="primary")

        undo_stack = st.session_state.get(f"ai_undo_{key}", [])
        bcols = st.columns(3)
        if msgs and bcols[0].button("🗑️ Effacer le chat", key=f"clear_{key}", use_container_width=True):
            st.session_state.pop(msgs_key, None)
            st.rerun()
        if undo_stack and bcols[1].button("↶ Annuler la dernière modif", key=f"undo_{key}", use_container_width=True):
            prev = undo_stack.pop()
            st.session_state[f"ai_html_{key}"] = prev
            fiche_store.save(key, prev)
            st.session_state[f"ai_undo_{key}"] = undo_stack
            st.rerun()
        if modified and bcols[2].button("↩️ Revenir à l'original", key=f"reset_{key}", use_container_width=True):
            st.session_state.pop(f"ai_html_{key}", None)
            st.session_state.pop(f"ai_undo_{key}", None)
            fiche_store.clear(key)  # efface aussi la version persistée
            st.rerun()

        with st.expander("🔧 Modèles disponibles pour ma clé (diagnostic)"):
            st.caption(
                "En cas d'erreur « modèle introuvable » ou « quota », listez ici les "
                "modèles que votre clé accepte, puis copiez-en un dans `model` sous "
                "`[gemini]` dans les secrets."
            )
            if st.button("Lister les modèles Gemini", key=f"lm_{key}"):
                with st.spinner("Interrogation de l'API…"):
                    st.session_state[f"ai_models_{key}"] = ai_assistant.list_models()
            models = st.session_state.get(f"ai_models_{key}")
            if models:
                flash = [m for m in models if "flash" in m]
                st.markdown("**Modèles « flash » (rapides, recommandés) :**")
                st.code("\n".join(flash) or "(aucun modèle « flash »)", language="text")
                st.caption(f"{len(models)} modèle(s) au total pour votre clé.")
            elif models == []:
                st.warning("Aucun modèle listé (clé absente ou erreur d'accès).")

            st.divider()
            probe_m = st.text_input("Tester un modèle précis (appel réel)",
                                    value="gemini-2.5-flash", key=f"pm_{key}")
            if st.button("Tester ce modèle", key=f"pb_{key}"):
                with st.spinner("Appel test…"):
                    st.session_state[f"ai_probe_{key}"] = ai_assistant.probe_model(probe_m.strip())
            res = st.session_state.get(f"ai_probe_{key}")
            if res:
                st.code(res, language="text")

        if sent and (q.strip() or up):
            media, doc_text, labels, warns = [], "", [], []
            if up:
                media, doc_text, labels, warns = ai_assistant.process_uploads(
                    [(f.name, f.type, f.getvalue()) for f in up])
            for w in warns:
                st.warning(w)
            send(q, media=media, doc_text=doc_text, labels=labels)
