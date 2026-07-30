#!/usr/bin/env python3
"""ai_assistant.py — Assistant IA (Google Gemini) pour aider à modifier les fiches.

Sécurité (le point clé) :
  * La clé API vit UNIQUEMENT dans les secrets Streamlit — jamais dans le code,
    jamais dans le HTML des fiches, jamais dans git (`.streamlit/secrets.toml`
    est ignoré). En ligne : app > Settings > Secrets.
  * Tous les appels à Gemini se font CÔTÉ SERVEUR (ici, en Python). La clé ne
    transite jamais par le navigateur ni par la fiche téléchargée.
  * L'IA ne renvoie PAS de HTML : elle renvoie des modifications repérées par
    l'INDICE d'un segment de texte. On les applique comme du TEXTE (échappé par
    BeautifulSoup), donc un `<script>` renvoyé par l'IA devient inerte
    (`&lt;script&gt;`) — pas d'injection possible dans la fiche.
  * Sans clé configurée, `is_configured()` renvoie False et l'app masque tout
    simplement le chat.

Le module n'importe `google.genai` et `bs4` que lorsqu'on s'en sert, pour que
l'app démarre même si ces paquets ne sont pas encore installés.
"""

from __future__ import annotations

import json
import re

import streamlit as st

DEFAULT_MODEL = "gemini-2.0-flash"

# Bornes de sûreté pour ne pas envoyer un prompt démesuré à l'API.
_MAX_SEGMENTS = 500
_MAX_SEG_LEN = 600
_MAX_HISTORY = 8

# Un segment « utile » : au moins une lettre (latine ou arabe), pas juste des
# chiffres/ponctuation (on ne veut pas que l'IA renumérote les années par ex.).
_HAS_LETTER = re.compile(r"[A-Za-zÀ-ÿ؀-ۿ]")
_SKIP_ANCESTORS = {"script", "style", "svg"}


# --------------------------------------------------------------------------- #
#  Clé / configuration                                                         #
# --------------------------------------------------------------------------- #
def _key() -> str | None:
    """Clé API — depuis les secrets Streamlit (recommandé) ou, à défaut, la
    variable d'environnement GEMINI_API_KEY / GOOGLE_API_KEY. Toujours lue
    côté serveur, jamais exposée au navigateur. Ne lève jamais."""
    try:
        g = st.secrets.get("gemini")
        if g:
            k = str(g.get("api_key") or "").strip()
            # Accepte tout format de clé (AIza…, AQ.…) ; rejette seulement le
            # placeholder non modifié (les vrais clés ne contiennent pas "...").
            if k and "..." not in k:
                return k
    except Exception:
        pass
    import os
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        k = (os.environ.get(var) or "").strip()
        if k:
            return k
    return None


def is_configured() -> bool:
    return _key() is not None


def _model_name() -> str:
    try:
        g = st.secrets.get("gemini") or {}
        return (g.get("model") or DEFAULT_MODEL).strip()
    except Exception:
        return DEFAULT_MODEL


@st.cache_resource(show_spinner=False)
def _client(key: str):
    """Client Gemini (mis en cache pour ne pas le recréer à chaque rerun)."""
    from google import genai  # import tardif : l'app démarre sans le paquet
    return genai.Client(api_key=key)


# --------------------------------------------------------------------------- #
#  Extraction / application des textes de la fiche                             #
# --------------------------------------------------------------------------- #
def _meaningful(s: str) -> bool:
    s = s.strip()
    return len(s) >= 2 and bool(_HAS_LETTER.search(s))


def _text_nodes(html: str):
    """(soup, [NavigableString]) : les nœuds de texte éditables de la fiche,
    dans l'ordre du document, hors script/style/svg. Ordre DÉTERMINISTE : les
    indices sont donc stables entre l'extraction (pour l'IA) et l'application."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".dc-fiche") or soup
    nodes = []
    for t in root.find_all(string=True):
        if any(getattr(p, "name", None) in _SKIP_ANCESTORS for p in t.parents):
            continue
        if _meaningful(str(t)):
            nodes.append(t)
    return soup, nodes


def extract_segments(html: str) -> list[str]:
    """Liste ordonnée des textes de la fiche (pour donner le contexte à l'IA)."""
    _soup, nodes = _text_nodes(html)
    segs = [re.sub(r"\s+", " ", str(t)).strip() for t in nodes]
    return [s[:_MAX_SEG_LEN] for s in segs[:_MAX_SEGMENTS]]


def apply_edits(html: str, edits: list[dict]) -> tuple[str, int]:
    """Applique des modifs {i:<indice>, replace:<texte>} au HTML.
    Renvoie (html_modifié, nombre_de_modifs_appliquées). Le remplacement se
    fait sur le TEXTE (BeautifulSoup échappe automatiquement < > & en sortie)."""
    from bs4 import NavigableString
    soup, nodes = _text_nodes(html)
    n = 0
    for e in edits or []:
        i, rep = e.get("i"), e.get("replace")
        if not isinstance(i, int) or rep is None or not (0 <= i < len(nodes)):
            continue
        orig = str(nodes[i])
        lead = orig[: len(orig) - len(orig.lstrip())]
        trail = orig[len(orig.rstrip()):]
        nodes[i].replace_with(NavigableString(lead + str(rep) + trail))
        n += 1
    return (str(soup), n) if n else (html, 0)


# --------------------------------------------------------------------------- #
#  Conversation avec Gemini                                                    #
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "Tu es l'assistant de rédaction d'une fiche infographique du HCP "
    "(Haut-Commissariat au Plan, Maroc) sur le marché du travail. Tu aides à "
    "améliorer le CONTENU TEXTUEL : reformuler, raccourcir, corriger "
    "l'orthographe/grammaire, traduire (français ↔ arabe), harmoniser le ton "
    "institutionnel, proposer des points saillants. Tu NE changes JAMAIS les "
    "chiffres/pourcentages sauf demande explicite. Tu écris dans la langue de "
    "la fiche (ou celle demandée). Reste factuel et concis.\n\n"
    "On te fournit les SEGMENTS de texte de la fiche, numérotés [i]. Pour "
    "proposer une modification concrète d'un segment existant, référence-le "
    "par son indice i (n'invente pas d'indice). Ne touche qu'aux segments à "
    "modifier.\n\n"
    "Réponds STRICTEMENT en JSON, sans texte autour, avec ce schéma :\n"
    '{ "reply": "<ta réponse à l\'utilisateur, en clair>", '
    '"edits": [ { "i": <indice du segment>, "replace": "<nouveau texte>" } ] }\n'
    'Si tu ne fais que discuter/expliquer sans modifier la fiche, renvoie '
    '"edits": []. Ne mets jamais de balises HTML dans "replace".'
)


def converse(history: list[dict], user_msg: str, segments: list[str],
             model: str | None = None) -> tuple[str, list[dict]]:
    """Envoie l'historique + le message + les segments à Gemini.
    Renvoie (réponse_texte, edits). Lève RuntimeError avec un message clair
    en cas de souci (clé absente, paquet manquant, erreur API)."""
    key = _key()
    if not key:
        raise RuntimeError("Aucune clé Gemini configurée.")
    try:
        from google.genai import types
    except Exception as exc:  # paquet non installé
        raise RuntimeError(
            "Le paquet « google-genai » n'est pas installé. Lance : "
            "pip install -r requirements.txt"
        ) from exc

    client = _client(key)
    seg_txt = "\n".join(f"[{i}] {s}" for i, s in enumerate(segments)) or "(fiche vide)"
    convo = ""
    for h in history[-_MAX_HISTORY:]:
        who = "Utilisateur" if h.get("role") == "user" else "Assistant"
        convo += f"{who}: {h.get('content', '')}\n"
    prompt = (
        f"SEGMENTS DE LA FICHE (numérotés) :\n{seg_txt}\n\n"
        f"CONVERSATION JUSQU'ICI :\n{convo}"
        f"NOUVEAU MESSAGE DE L'UTILISATEUR :\n{user_msg}"
    )
    try:
        resp = client.models.generate_content(
            model=model or _model_name(),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                response_mime_type="application/json",
                temperature=0.4,
            ),
        )
        raw = (resp.text or "").strip()
    except Exception as exc:
        raise RuntimeError(_friendly_api_error(exc)) from exc

    # Parse JSON tolérant (au cas où le modèle enrobe le JSON).
    reply, edits = _parse_json_reply(raw)
    return reply, edits


def _friendly_api_error(exc: Exception) -> str:
    """Transforme une erreur d'API brute en message actionnable pour l'utilisateur."""
    code = getattr(exc, "code", None)
    s = str(exc)
    low = s.lower()
    if code == 429 or "RESOURCE_EXHAUSTED" in s or "quota" in low:
        return (
            "🚦 Quota Gemini épuisé pour ce modèle. Souvent, le projet Google n'a "
            "**aucun palier gratuit** pour ce modèle/région. Deux options :\n\n"
            "• Essayez un autre modèle : ajoutez `model = \"gemini-1.5-flash\"` sous "
            "`[gemini]` dans les secrets.\n"
            "• Ou activez la **facturation** sur votre projet Google (Gemini Flash "
            "coûte quelques centimes par million de tokens)."
        )
    if "API_KEY_INVALID" in s or ("api key" in low and "not valid" in low) or code == 401:
        return "🔑 Clé API invalide — vérifiez `api_key` sous `[gemini]` dans les secrets."
    if code == 404 or "NOT_FOUND" in s:
        return (
            "🔎 Modèle introuvable — changez `model` sous `[gemini]` dans les secrets "
            "(ex. `gemini-1.5-flash` ou `gemini-flash-latest`)."
        )
    return f"⚠️ Erreur de l'API Gemini : {exc}"


def _parse_json_reply(raw: str) -> tuple[str, list[dict]]:
    if not raw:
        return "(réponse vide)", []
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return raw, []  # pas du JSON : on affiche tel quel, aucune modif
        try:
            data = json.loads(m.group(0))
        except Exception:
            return raw, []
    reply = str(data.get("reply", "")).strip() or "(aucune réponse)"
    edits = data.get("edits") or []
    clean = [
        {"i": e["i"], "replace": str(e.get("replace", ""))}
        for e in edits
        if isinstance(e, dict) and isinstance(e.get("i"), int)
    ]
    return reply, clean
