#!/usr/bin/env python3
"""fiche_editor.py — Générateur « v2 » : les 4 nouvelles fiches éditables.

L'utilisateur choisit une fiche, modifie son contenu (édition directe pilotée
par le `EDIT_SCHEMA` de la fiche — l'import Excel et le chat IA viendront se
brancher sur le même `spec`), et voit l'aperçu se mettre à jour en direct.
Le design de chaque fiche est figé (voir templates/) ; seul le contenu change.

Ce module est autonome : app.py n'a qu'à appeler `render_generator()`.
"""

import io
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

from templates import fiche_situation

# Registre des fiches. `module` doit exposer DEFAULT_SPEC, EDIT_SCHEMA,
# render(spec, lang, path), LANG. Les fiches non encore construites sont
# marquées "soon" (affichées comme « en préparation »).
REGISTRY = {
    "situation": {"label": "📊 Fiche 1 — Situation du marché du travail", "module": fiche_situation, "status": "ready"},
    "neet": {"label": "🎓 Fiche 2 — Les jeunes NEET", "module": None, "status": "soon"},
    "emo": {"label": "📈 Fiche 3 — EMO 2026 (nouvelle enquête, arabe)", "module": None, "status": "soon"},
    "autre": {"label": "📝 Fiche 4 — Autre (modèle générique)", "module": None, "status": "soon"},
}


def _png_to_pdf(png_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def _render_png(fiche_key: str, spec_json: str) -> bytes:
    """Rend la fiche en PNG. Mis en cache par le contenu (spec_json) : l'aperçu
    n'est recalculé que si le contenu change réellement, malgré les nombreux
    reruns de Streamlit pendant l'édition."""
    spec = json.loads(spec_json)
    mod = REGISTRY[fiche_key]["module"]
    lang = getattr(mod, "LANG", "fr")
    out = str(Path(tempfile.gettempdir()) / f"fiche_{fiche_key}.png")
    mod.render(spec, lang, out)
    return Path(out).read_bytes()


def _default_spec(mod) -> dict:
    """Copie profonde et JSON-able du contenu par défaut (les tuples y
    deviennent des listes, ce qui convient au rendu et à l'édition)."""
    return json.loads(json.dumps(mod.DEFAULT_SPEC, ensure_ascii=False, default=list))


def _render_editor(spec: dict, schema: list, fiche_key: str) -> None:
    """Construit les widgets d'édition d'après le schéma et réécrit le `spec`
    (mutation en place → persiste dans st.session_state)."""
    for grp in schema:
        with st.expander(grp["group"], expanded=(grp is schema[0])):
            for fld in grp["fields"]:
                k = fld["key"]
                wkey = f"ed_{fiche_key}_{k}"
                if fld["kind"] == "text":
                    spec[k] = st.text_input(fld["label"], value=str(spec.get(k, "")), key=wkey)
                elif fld["kind"] == "textarea":
                    spec[k] = st.text_area(fld["label"], value=str(spec.get(k, "")), key=wkey, height=110)
                elif fld["kind"] == "table":
                    df = fld["to_df"](spec)
                    edited = st.data_editor(
                        df,
                        key=wkey,
                        use_container_width=True,
                        hide_index=True,
                        num_rows="dynamic" if fld.get("dynamic") else "fixed",
                    )
                    spec[k] = fld["from_df"](edited, spec)


def render_generator(app_version: str = "—") -> None:
    # ---- choix de la fiche ----
    st.markdown(
        '<div class="hcp-step"><span class="hcp-step-num">1</span>'
        "<h3>Choisissez un type de fiche</h3></div>",
        unsafe_allow_html=True,
    )
    key = st.radio(
        "Type de fiche",
        options=list(REGISTRY),
        format_func=lambda k: REGISTRY[k]["label"],
        label_visibility="collapsed",
    )
    entry = REGISTRY[key]
    if entry["status"] != "ready" or entry["module"] is None:
        st.info(
            "🚧 Cette fiche est **en préparation** — elle arrivera dans une prochaine étape. "
            "La fiche 1 « Situation du marché du travail » est déjà disponible et pleinement éditable."
        )
        return

    mod = entry["module"]
    sk = f"spec_{key}"
    if sk not in st.session_state:
        st.session_state[sk] = _default_spec(mod)
    spec = st.session_state[sk]

    st.markdown(
        '<div class="hcp-step"><span class="hcp-step-num">2</span>'
        "<h3>Modifiez le contenu, l'aperçu se met à jour</h3></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Changez les textes et les chiffres à gauche : le design reste figé, seul le contenu change. "
        "(L'import Excel et le chat IA se brancheront ici prochainement.)"
    )

    col_edit, col_prev = st.columns([1, 1], gap="large")
    with col_edit:
        _render_editor(spec, mod.EDIT_SCHEMA, key)
        if st.button("↩️ Réinitialiser au modèle par défaut", key=f"reset_{key}"):
            st.session_state[sk] = _default_spec(mod)
            # purge les valeurs des widgets d'édition pour qu'ils reprennent les défauts
            for wk in [w for w in st.session_state if w.startswith(f"ed_{key}_")]:
                del st.session_state[wk]
            st.rerun()

    with col_prev:
        spec_json = json.dumps(st.session_state[sk], ensure_ascii=False, sort_keys=True, default=list)
        try:
            png = _render_png(key, spec_json)
            st.image(png)
            dl = st.columns(2)
            with dl[0]:
                st.download_button("⬇️ PNG", data=png, file_name=f"fiche_{key}.png",
                                   mime="image/png", key=f"dl_png_{key}")
            with dl[1]:
                st.download_button("🖨️ PDF", data=_png_to_pdf(png), file_name=f"fiche_{key}.pdf",
                                   mime="application/pdf", key=f"dl_pdf_{key}")
        except Exception as exc:  # garde-fou : jamais de traceback brut à l'écran
            st.error(f"Impossible de générer l'aperçu : {exc}")
