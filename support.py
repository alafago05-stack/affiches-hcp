#!/usr/bin/env python3
"""support.py — Espace support de l'application HCP.

Deux volets, réunis dans `render()` :

  1. Un **chatbot guidé** (assistant de signalement) qui pose une série de
     questions courtes à l'utilisateur (collègue du HCP) — catégorie du
     problème, titre, description, où il est survenu, gravité, contact
     facultatif — puis enregistre le tout.
  2. Un **espace de suivi** (administration) qui liste les signalements
     collectés, permet de changer leur statut (nouveau / en cours / résolu)
     et de les exporter (CSV, JSON) — pour préparer les prochaines mises à
     jour de l'application.

Le stockage bascule automatiquement selon l'environnement :
  - **en local** : une base **SQLite** (`support/tickets.db`) — un seul
    fichier, aucune installation ;
  - **en ligne** (Streamlit Community Cloud) : une base **Postgres** externe
    (Supabase / Neon) dès qu'une URL est fournie dans les secrets, car le
    disque des hébergeurs est éphémère et perdrait les signalements.
Dans les deux cas, la table est indexée sur le statut et la date pour rester
efficace même après des centaines de signalements.

Le chatbot est volontairement « à base de règles » (une machine à états),
pas un modèle de langage : il n'a besoin d'aucune clé d'API, fonctionne hors
ligne, et garantit des signalements structurés et exploitables.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "support" / "tickets.db"

# --------------------------------------------------------------------------
# Référentiels (clés stockées en base, libellés affichés dans l'interface)
# --------------------------------------------------------------------------
CATEGORIES = {
    "bug": ("🐞 Un bug / une erreur", "L'application affiche une erreur ou se bloque."),
    "donnees": ("📊 Un problème de données Excel", "Chiffres faux, tableau non reconnu, fichier refusé…"),
    "affichage": ("🎨 Un problème d'affichage", "Texte coupé, chevauchement, couleur, mise en page…"),
    "suggestion": ("💡 Une suggestion / une demande", "Une fonctionnalité que vous aimeriez avoir."),
    "autre": ("💬 Autre", "Toute autre remarque."),
}
CATEGORY_LABEL = {k: v[0] for k, v in CATEGORIES.items()}

WHERE_CHOICES = {
    "type1": "Type 1 — Affiche standard",
    "type2": "Type 2 — Comparatif années",
    "type3": "Type 3 — Comparatif régions",
    "type4": "Type 4 — Comparatif trimestres",
    "apercu": "L'aperçu des données",
    "app": "L'application en général",
}

SEVERITIES = {
    "bloquant": "🔴 Bloquant — je ne peux pas générer d'affiche",
    "genant": "🟠 Gênant — je peux continuer, mais c'est pénible",
    "mineur": "🟢 Mineur — détail ou cosmétique",
}
SEVERITY_LABEL = {"bloquant": "🔴 Bloquant", "genant": "🟠 Gênant", "mineur": "🟢 Mineur"}

STATUSES = ["nouveau", "en cours", "résolu"]

QUESTIONS = {
    "welcome": (
        "Bonjour 👋 Je suis l'assistant de support du générateur d'affiches HCP. "
        "Je vais recueillir votre problème ou votre suggestion en quelques questions, "
        "puis l'enregistrer pour qu'il soit traité dans une prochaine mise à jour.\n\n"
        "**De quel type de sujet s'agit-il ?**"
    ),
    "title": "D'accord. Donnez-moi un **titre court** (une ligne) qui résume le sujet.",
    "description": (
        "Merci. **Décrivez-le maintenant le plus précisément possible** : ce que vous "
        "faisiez, ce qui s'est passé, et ce que vous attendiez à la place."
    ),
    "where": "**Où** avez-vous rencontré ce sujet dans l'application ?",
    "severity": "**À quel point** cela vous gêne-t-il ?",
    "contact": (
        "Souhaitez-vous laisser un **contact** (e-mail ou nom) pour être recontacté si "
        "besoin ? C'est facultatif — vous pouvez passer cette étape."
    ),
}

REFERENCE_FMT = "SUP-{:04d}"


# ==========================================================================
# Couche de stockage — Postgres en ligne, SQLite en local
# ==========================================================================
# En LOCAL (aucune configuration) : les signalements vont dans un fichier
# SQLite. Zéro installation, pratique pour développer et tester.
#
# EN LIGNE (Streamlit Community Cloud) : le disque est ÉPHÉMÈRE — il est remis
# à zéro à chaque redémarrage ou redéploiement, ce qui ferait perdre tous les
# signalements. On bascule donc automatiquement sur une base Postgres externe
# (Supabase / Neon) dès qu'une URL de connexion est fournie, via les secrets
# Streamlit (`.streamlit/secrets.toml` en local, « Settings > Secrets » en
# ligne) ou la variable d'environnement DATABASE_URL.
#
# Le reste du module (chatbot, espace de suivi) ne connaît que les 4 fonctions
# publiques ci-dessous : il fonctionne à l'identique sur les deux backends.
def _pg_url():
    """URL Postgres si configurée, sinon None (⇒ repli SQLite local)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        return st.secrets["postgres"]["url"]
    except Exception:
        # Pas de fichier secrets, ou pas de section [postgres] : mode local.
        return None


def storage_backend() -> str:
    """Nom du backend actif — affiché dans l'espace de suivi."""
    return "Postgres (persistant)" if _pg_url() else "SQLite local (éphémère en ligne)"


def _connect():
    """Retourne (connexion, is_postgres). L'import de psycopg est fait ici, et
    seulement si une URL est configurée, pour que l'app tourne en local sans
    que psycopg soit installé."""
    url = _pg_url()
    if url:
        import psycopg

        return psycopg.connect(url, autocommit=True), True
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn, False


# Le schéma ne diffère que par la clé auto-incrémentée ; `created_at` est un
# texte ISO sur les deux backends (tri lexicographique = tri chronologique),
# ce qui garde un comportement identique en local et en ligne.
_SCHEMA_SQLITE = """
    CREATE TABLE IF NOT EXISTS tickets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at  TEXT    NOT NULL,
        category    TEXT    NOT NULL,
        poster      TEXT,
        severity    TEXT,
        title       TEXT    NOT NULL,
        description TEXT    NOT NULL,
        contact     TEXT,
        status      TEXT    NOT NULL DEFAULT 'nouveau',
        app_version TEXT
    )
"""
_SCHEMA_PG = _SCHEMA_SQLITE.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL  PRIMARY KEY")

_COLS = ["id", "created_at", "category", "poster", "severity", "title",
         "description", "contact", "status", "app_version"]


def init_db() -> None:
    """Crée la table et ses index si besoin (idempotent, sur les 2 backends)."""
    conn, pg = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_SCHEMA_PG if pg else _SCHEMA_SQLITE)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at)")
        if not pg:
            conn.commit()
    finally:
        conn.close()


def save_ticket(ticket: dict, app_version: str = "—") -> str:
    """Enregistre un signalement et retourne sa référence (ex. 'SUP-0007')."""
    init_db()
    conn, pg = _connect()
    try:
        ph = "%s" if pg else "?"  # psycopg et sqlite3 n'ont pas le même marqueur
        cols = ("created_at, category, poster, severity, title, "
                "description, contact, status, app_version")
        sql = f"INSERT INTO tickets ({cols}) VALUES ({', '.join([ph] * 9)})"
        values = (
            datetime.now().isoformat(timespec="seconds"),
            ticket.get("category", "autre"),
            ticket.get("poster"),
            ticket.get("severity"),
            ticket.get("title", "").strip(),
            ticket.get("description", "").strip(),
            (ticket.get("contact") or "").strip() or None,
            "nouveau",
            app_version,
        )
        cur = conn.cursor()
        if pg:
            cur.execute(sql + " RETURNING id", values)
            new_id = cur.fetchone()[0]
        else:
            cur.execute(sql, values)
            new_id = cur.lastrowid
            conn.commit()
        return REFERENCE_FMT.format(new_id)
    finally:
        conn.close()


def list_tickets() -> pd.DataFrame:
    """Retourne tous les signalements (plus récents d'abord) en DataFrame,
    avec une colonne 'reference' lisible. DataFrame vide si aucun."""
    init_db()
    conn, _pg = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(_COLS)} FROM tickets ORDER BY id DESC")
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    # tuple(r) : sqlite3.Row et les tuples psycopg sont tous deux itérables
    df = pd.DataFrame([dict(zip(_COLS, tuple(r))) for r in rows])
    df.insert(0, "reference", df["id"].map(REFERENCE_FMT.format))
    return df


def update_status(ticket_id: int, status: str) -> None:
    conn, pg = _connect()
    try:
        ph = "%s" if pg else "?"
        cur = conn.cursor()
        cur.execute(f"UPDATE tickets SET status = {ph} WHERE id = {ph}", (status, int(ticket_id)))
        if not pg:
            conn.commit()
    finally:
        conn.close()


# ==========================================================================
# Chatbot (machine à états dans st.session_state)
# ==========================================================================
def _reset_chat() -> None:
    st.session_state.sup_stage = "category"
    st.session_state.sup_ticket = {}
    st.session_state.sup_msgs = [("assistant", QUESTIONS["welcome"])]


def _say_user(text: str) -> None:
    st.session_state.sup_msgs.append(("user", text))


def _ask(stage: str) -> None:
    """Passe à l'étape suivante et pousse la question correspondante dans le
    fil de discussion."""
    st.session_state.sup_stage = stage
    q = QUESTIONS.get(stage)
    if q:
        st.session_state.sup_msgs.append(("assistant", q))


def _ask_confirm() -> None:
    t = st.session_state.sup_ticket
    lines = [
        "Parfait, voici le **récapitulatif** de votre signalement :",
        "",
        f"- **Sujet** : {CATEGORY_LABEL.get(t.get('category'), '—')}",
        f"- **Titre** : {t.get('title', '—')}",
        f"- **Description** : {t.get('description', '—')}",
        f"- **Emplacement** : {WHERE_CHOICES.get(t.get('poster'), '—')}",
        f"- **Gravité** : {SEVERITIES.get(t.get('severity'), '—')}",
        f"- **Contact** : {t.get('contact') or '— (non renseigné)'}",
        "",
        "Envoyez-le pour l'enregistrer, ou recommencez si besoin.",
    ]
    st.session_state.sup_stage = "confirm"
    st.session_state.sup_msgs.append(("assistant", "\n".join(lines)))


def _text_step(stage: str, next_stage: str, placeholder: str, optional: bool = False) -> None:
    """Étape à saisie libre : un formulaire (texte + bouton) évite un rerun à
    chaque frappe. Pour une étape facultative, un bouton « Passer » est ajouté."""
    with st.form(f"sup_form_{stage}", clear_on_submit=True):
        value = st.text_area(placeholder, key=f"sup_input_{stage}", height=90,
                             label_visibility="collapsed", placeholder=placeholder)
        cols = st.columns([1, 1, 4])
        sent = cols[0].form_submit_button("Envoyer", type="primary")
        skipped = cols[1].form_submit_button("Passer") if optional else False
    if sent and value.strip():
        _say_user(value.strip())
        st.session_state.sup_ticket[_FIELD_OF[stage]] = value.strip()
        _advance_after(stage, next_stage)
        st.rerun()
    elif sent and not value.strip() and not optional:
        st.warning("Merci de saisir un texte avant d'envoyer.")
    elif skipped:
        _say_user("_(passé)_")
        st.session_state.sup_ticket[_FIELD_OF[stage]] = None
        _advance_after(stage, next_stage)
        st.rerun()


# champ du ticket alimenté par chaque étape à saisie libre
_FIELD_OF = {"title": "title", "description": "description", "contact": "contact"}


def _advance_after(stage: str, next_stage: str) -> None:
    """Va à l'étape suivante, sauf la transition vers 'confirm' qui construit
    d'abord le récapitulatif."""
    if next_stage == "confirm":
        _ask_confirm()
    else:
        _ask(next_stage)


def _choice_step(options: dict, field: str, next_stage: str, prefix: str) -> None:
    """Étape à choix : un bouton pleine largeur par option."""
    for key, label in options.items():
        display = label[0] if isinstance(label, tuple) else label
        if st.button(display, key=f"{prefix}_{key}", width="stretch"):
            _say_user(display)
            st.session_state.sup_ticket[field] = key
            _advance_after(next_stage[0], next_stage[1])
            st.rerun()


def _render_chatbot(app_version: str) -> None:
    if "sup_stage" not in st.session_state:
        _reset_chat()

    # fil de discussion
    for role, msg in st.session_state.sup_msgs:
        with st.chat_message(role, avatar="🛟" if role == "assistant" else "🙋"):
            st.markdown(msg)

    stage = st.session_state.sup_stage

    if stage == "category":
        _choice_step(CATEGORIES, "category", ("category", "title"), "sup_cat")
    elif stage == "title":
        _text_step("title", "description", "Titre court du problème…")
    elif stage == "description":
        _text_step("description", "where", "Décrivez le problème en détail…")
    elif stage == "where":
        _choice_step(WHERE_CHOICES, "poster", ("where", "severity"), "sup_where")
    elif stage == "severity":
        _choice_step(SEVERITIES, "severity", ("severity", "contact"), "sup_sev")
    elif stage == "contact":
        _text_step("contact", "confirm", "E-mail ou nom (facultatif)…", optional=True)
    elif stage == "confirm":
        cols = st.columns([1, 1, 3])
        if cols[0].button("✅ Envoyer le signalement", type="primary"):
            ref = save_ticket(st.session_state.sup_ticket, app_version)
            st.session_state.sup_msgs.append((
                "assistant",
                f"✅ Merci ! Votre signalement est enregistré sous la référence **{ref}**. "
                "L'équipe le traitera lors d'une prochaine mise à jour. "
                "Vous pouvez en envoyer un autre si besoin.",
            ))
            st.session_state.sup_stage = "done"
            st.rerun()
        if cols[1].button("↩️ Recommencer"):
            _reset_chat()
            st.rerun()
    elif stage == "done":
        if st.button("➕ Nouveau signalement", type="primary"):
            _reset_chat()
            st.rerun()


# ==========================================================================
# Espace de suivi (administration)
# ==========================================================================
def _render_admin(app_version: str) -> None:
    with st.expander("🔧 Espace de suivi des signalements (administration)"):
        st.caption(f"Stockage : **{storage_backend()}** · version de l'app : {app_version}")
        if not _pg_url():
            st.warning(
                "Base locale : en ligne (Streamlit Cloud), ce mode est remis à zéro à chaque "
                "redémarrage. Configurez une base Postgres dans les secrets pour conserver "
                "durablement les signalements — voir le README."
            )
        df = list_tickets()
        if df.empty:
            st.info("Aucun signalement pour le moment.")
            return

        # statistiques rapides
        c = st.columns(4)
        c[0].metric("Total", len(df))
        c[1].metric("🔵 Nouveaux", int((df["status"] == "nouveau").sum()))
        c[2].metric("🟠 En cours", int((df["status"] == "en cours").sum()))
        c[3].metric("🟢 Résolus", int((df["status"] == "résolu").sum()))

        # tableau lisible
        show = df.copy()
        show["catégorie"] = show["category"].map(CATEGORY_LABEL).fillna(show["category"])
        show["gravité"] = show["severity"].map(SEVERITY_LABEL).fillna("—")
        show["emplacement"] = show["poster"].map(WHERE_CHOICES).fillna("—")
        show = show.rename(columns={"created_at": "date", "title": "titre", "status": "statut"})
        st.dataframe(
            show[["reference", "date", "statut", "catégorie", "gravité", "emplacement", "titre"]],
            width="stretch",
            hide_index=True,
        )

        # détail + changement de statut
        st.markdown("**Traiter un signalement**")
        refs = df["reference"].tolist()
        sel = st.selectbox("Signalement", refs, key="sup_admin_sel")
        row = df[df["reference"] == sel].iloc[0]
        st.markdown(
            f"**{sel}** — {CATEGORY_LABEL.get(row['category'], row['category'])} · "
            f"{SEVERITY_LABEL.get(row['severity'], '—')} · {WHERE_CHOICES.get(row['poster'], '—')}\n\n"
            f"**{row['title']}**\n\n{row['description']}"
            # pd.notna : un contact absent (NULL en base) devient NaN dans le
            # DataFrame, et bool(NaN) vaut True — un simple `if row['contact']`
            # afficherait « Contact : nan ».
            + (f"\n\n📇 Contact : {row['contact']}" if pd.notna(row["contact"]) else "")
        )
        cols = st.columns([2, 1])
        new_status = cols[0].radio(
            "Statut", STATUSES, index=STATUSES.index(row["status"]) if row["status"] in STATUSES else 0,
            horizontal=True, key="sup_admin_status",
        )
        if cols[1].button("💾 Mettre à jour", key="sup_admin_update"):
            update_status(int(row["id"]), new_status)
            st.success(f"{sel} → {new_status}")
            st.rerun()

        # exports pour traitement hors ligne / prochaines mises à jour
        st.divider()
        exp = st.columns(2)
        exp[0].download_button(
            "⬇️ Exporter en CSV",
            data=df.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name="signalements_hcp.csv",
            mime="text/csv",
        )
        exp[1].download_button(
            "⬇️ Exporter en JSON",
            data=json.dumps(df.to_dict(orient="records"), ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="signalements_hcp.json",
            mime="application/json",
        )


# ==========================================================================
# Point d'entrée appelé par app.py
# ==========================================================================
def render(app_version: str = "—") -> None:
    """Affiche l'espace support complet (chatbot + suivi)."""
    init_db()
    st.markdown(
        '<div class="hcp-step"><span class="hcp-step-num">💬</span>'
        "<h3>Support — signaler un problème ou une suggestion</h3></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Discutez avec l'assistant : votre signalement est enregistré de façon structurée "
        "pour être traité dans une prochaine mise à jour de l'application."
    )
    _render_chatbot(app_version)
    st.divider()
    _render_admin(app_version)
