#!/usr/bin/env python3
"""fiche_store.py — Persistance des fiches modifiées (survit au rafraîchissement).

Les modifications appliquées à une fiche (assistant IA) sont enregistrées côté
serveur pour rester en place quand on recharge la page — `st.session_state`,
lui, est remis à zéro à chaque rafraîchissement.

Stockage : fichiers `html_fiches/_saved/<clé>.html`. Ce dossier survit aux
rafraîchissements de page ; sur Streamlit Community Cloud il est réinitialisé
lors d'un redéploiement (nouveau conteneur). Pour une durabilité totale
(redéploiements), on pourra basculer ce module sur la base Postgres existante.
"""

from pathlib import Path

_DIR = Path(__file__).parent / "html_fiches" / "_saved"


def _path(key: str) -> Path:
    safe = "".join(c for c in str(key) if c.isalnum() or c in "-_") or "fiche"
    return _DIR / f"{safe}.html"


def load(key: str) -> str | None:
    """HTML enregistré pour cette fiche, ou None. Ne lève jamais."""
    try:
        p = _path(key)
        return p.read_text(encoding="utf-8") if p.exists() else None
    except Exception:
        return None


def save(key: str, html: str) -> None:
    """Enregistre l'état courant de la fiche. Ne lève jamais."""
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        _path(key).write_text(html, encoding="utf-8")
    except Exception:
        pass


def clear(key: str) -> None:
    """Supprime l'état enregistré (retour à la fiche d'origine). Ne lève jamais."""
    try:
        p = _path(key)
        if p.exists():
            p.unlink()
    except Exception:
        pass
