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

# Alias vers le modèle « flash » courant : immunise contre le retrait des
# versions anciennes (les comptes récents n'ont plus accès à 2.0/2.5-flash).
# Surchargeable via le secret [gemini] model.
DEFAULT_MODEL = "gemini-flash-latest"

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


# --------------------------------------------------------------------------- #
#  Application des opérations de l'IA (remplacer / supprimer / ajouter)        #
# --------------------------------------------------------------------------- #
import html as _html  # échappement pour les fragments construits

# html.parser met en minuscule les attributs SVG en camelCase (viewBox ->
# viewbox), ce qui CASSE le rendu SVG. On restaure la casse après sérialisation.
_SVG_CAMEL = ["viewBox", "preserveAspectRatio", "gradientUnits", "gradientTransform",
              "patternUnits", "patternContentUnits", "clipPath", "clipPathUnits",
              "spreadMethod", "markerWidth", "markerHeight", "refX", "refY",
              "textLength", "lengthAdjust", "baseProfile"]

_PALETTE = ["#4a9d3f", "#2f6fb0", "#cf3b2c", "#c8992e", "#7a1c3f", "#3f7a6a"]
_HEXRE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_NAMEDCOLORS = {"red", "green", "blue", "orange", "purple", "teal", "gray", "grey",
                "black", "gold", "maroon", "navy", "olive", "brown", "crimson", "white"}


def _restore_svg_case(html_out: str) -> str:
    for name in _SVG_CAMEL:
        html_out = re.sub(r"\b" + name.lower() + r"=", name + "=", html_out)
    return html_out


def _esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace(" ", "").replace(",", ".").strip())
    except Exception:
        return default


def _safe_color(c, default: str) -> str:
    c = str(c or "").strip()
    return c if (_HEXRE.match(c) or c.lower() in _NAMEDCOLORS) else default


def _fmt(v: float) -> str:            # 43.0 -> "43,0" (décimal => éditable par le panneau)
    return f"{round(v, 1):.1f}".replace(".", ",")


def _frag_style(n: int, extra: str = "") -> str:
    # placement par défaut en cascade ; l'utilisateur déplace ensuite (glisser).
    return f"position:absolute; left:44px; top:{150 + (n % 12) * 30}px; z-index:60; {extra}"


def _build_text(op: dict, n: int) -> str:
    tag = str(op.get("tag", "p"))
    big = tag in ("h1", "h2", "h3", "title")
    style = _frag_style(n,
        "max-width:70%; padding:6px 10px; background:rgba(255,255,255,.92); "
        "border:1px dashed #c8992e; border-radius:6px; font-family:'Manrope',sans-serif; "
        f"color:#5a1330; font-size:{17 if big else 12}px; font-weight:{700 if big else 400}; line-height:1.35;")
    return f'<div style="{style}">{_esc(op.get("text", ""))}</div>'


def _build_table(op: dict, n: int) -> str:
    headers = op.get("headers") or []
    rows = op.get("rows") or []
    th = "".join(
        f'<th style="background:#7a1c3f;color:#fff;padding:4px 9px;text-align:left;'
        f'border:1px solid #e0d5cc;font-weight:700;">{_esc(h)}</th>' for h in headers)
    body = ""
    for r in rows:
        cells = r if isinstance(r, list) else [r]
        body += "<tr>" + "".join(
            f'<td style="padding:4px 9px;border:1px solid #e0d5cc;">{_esc(c)}</td>'
            for c in cells) + "</tr>"
    title = op.get("title", "")
    title_html = (f'<div style="font-size:12px;font-weight:700;color:#5a1330;'
                  f'margin-bottom:6px;">{_esc(title)}</div>') if title else ""
    style = _frag_style(n,
        "background:#fff;border:1px solid #e0d5cc;border-radius:8px;padding:8px 10px;"
        "box-shadow:0 4px 14px rgba(90,19,48,.14);font-family:'Manrope',sans-serif;")
    return (f'<div style="{style}">{title_html}'
            f'<table style="border-collapse:collapse;font-size:11px;color:#3a2a30;">'
            f'{("<thead><tr>" + th + "</tr></thead>") if th else ""}'
            f'<tbody>{body}</tbody></table></div>')


def _build_chart(op: dict, n: int) -> str | None:
    ctype = str(op.get("chart", "bar")).lower()
    labels = [str(x) for x in (op.get("labels") or [])]
    series = []
    for si, s in enumerate(op.get("series") or []):
        if not isinstance(s, dict):
            continue
        vals = [_num(v) for v in (s.get("values") or [])]
        if vals:
            series.append({"name": s.get("name", ""),
                           "color": _safe_color(s.get("color"), _PALETTE[si % len(_PALETTE)]),
                           "values": vals})
    if not series:
        return None
    N = max(len(labels), max(len(s["values"]) for s in series))
    if N == 0:
        return None
    maxv = max((v for s in series for v in s["values"]), default=1.0) or 1.0
    W = max(240, 46 * N + 30)
    H = 190
    padL, padR, top, bottom = 12, 12, 16, 22
    plotW = W - padL - padR
    plotH = H - top - bottom
    baseY = H - bottom

    def X(i):  # centre de la i-ème colonne
        return round(padL + (i + 0.5) * plotW / N, 1)

    def Y(v):
        return round(baseY - plotH * (v / maxv), 1)

    parts = [f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
             f'xmlns="http://www.w3.org/2000/svg" style="overflow:visible;font-family:\'Manrope\',sans-serif;">']
    # ligne de base
    parts.append(f'<line x1="{padL}" y1="{baseY}" x2="{W-padR}" y2="{baseY}" stroke="#d9cfc6" stroke-width="1"/>')

    if ctype == "line":
        for s in series:
            pts = " ".join(f"{X(i)},{Y(v)}" for i, v in enumerate(s["values"]))
            parts.append(f'<polyline points="{pts}" fill="none" stroke="{s["color"]}" stroke-width="2"/>')
            for i, v in enumerate(s["values"]):
                cx, cy = X(i), Y(v)
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="{s["color"]}"/>')
                parts.append(f'<text x="{cx}" y="{cy-6}" text-anchor="middle" font-size="9" fill="#3a2a30">{_fmt(v)}</text>')
    else:  # barres (première série)
        vals = series[0]["values"]
        color = series[0]["color"]
        bw = max(6, plotW / max(1, len(vals)) * 0.55)
        for i, v in enumerate(vals):
            cx = X(i)
            h = round(plotH * (v / maxv), 1)
            y = round(baseY - h, 1)
            parts.append(f'<rect x="{round(cx-bw/2,1)}" y="{y}" width="{round(bw,1)}" height="{h}" rx="2" fill="{color}"/>')
            parts.append(f'<text x="{cx}" y="{y-3}" text-anchor="middle" font-size="9" fill="#3a2a30">{_fmt(v)}</text>')

    for i, lb in enumerate(labels[:N]):
        parts.append(f'<text x="{X(i)}" y="{H-6}" text-anchor="middle" font-size="9" fill="#5a1330">{_esc(lb)}</text>')
    parts.append("</svg>")

    title = op.get("title", "")
    title_html = (f'<div style="font-size:12px;font-weight:700;color:#5a1330;'
                  f'margin-bottom:4px;">{_esc(title)}</div>') if title else ""
    legend = ""
    if ctype == "line" and len(series) > 1:
        legend = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;font-size:9px;color:#3a2a30;">' + "".join(
            f'<span><span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background:{s["color"]};margin-right:3px;"></span>{_esc(s["name"])}</span>' for s in series) + "</div>"
    style = _frag_style(n,
        "background:#fff;border:1px solid #e0d5cc;border-radius:8px;padding:8px 10px;"
        "box-shadow:0 4px 14px rgba(90,19,48,.14);")
    return f'<div style="{style}">{title_html}{"".join(parts)}{legend}</div>'


def _build_list(op: dict, n: int) -> str:
    items = op.get("items") or []
    lis = "".join(f'<li style="margin:2px 0;">{_esc(it)}</li>' for it in items)
    title = op.get("title", "")
    title_html = (f'<div style="font-size:12px;font-weight:700;color:#5a1330;'
                  f'margin-bottom:4px;">{_esc(title)}</div>') if title else ""
    style = _frag_style(n,
        "max-width:70%;background:rgba(255,255,255,.92);border:1px dashed #c8992e;"
        "border-radius:6px;padding:6px 10px;font-family:'Manrope',sans-serif;")
    return (f'<div style="{style}">{title_html}<ul style="margin:0;padding-left:20px;'
            f'font-size:11px;color:#3a2a30;line-height:1.45;">{lis}</ul></div>')


def _build_kpi(op: dict, n: int) -> str:
    color = _safe_color(op.get("color"), "#7a1c3f")
    style = _frag_style(n,
        "text-align:center;padding:8px 14px;background:#fff;border-radius:10px;"
        "box-shadow:0 4px 14px rgba(90,19,48,.14);font-family:'Manrope',sans-serif;")
    return (f'<div style="{style}"><div style="font-size:26px;font-weight:800;'
            f'color:{color};line-height:1;">{_esc(op.get("value", ""))}</div>'
            f'<div style="font-size:10px;color:#5a1330;margin-top:3px;">'
            f'{_esc(op.get("label", ""))}</div></div>')


def _build_donut(op: dict, n: int) -> str:
    p = int(round(max(0.0, min(100.0, _num(op.get("percent"), 0)))))
    color = _safe_color(op.get("color"), "#7a1c3f")
    style = _frag_style(n, "font-family:'Manrope',sans-serif;")
    return (f'<div style="{style}width:98px;height:98px;border-radius:50%;'
            f'background:conic-gradient({color} 0% {p}%,#e9e3e6 {p}% 100%);'
            f'display:flex;align-items:center;justify-content:center;">'
            f'<div style="width:68px;height:68px;border-radius:50%;background:#fff;'
            f'display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;">'
            f'<span style="font-size:17px;font-weight:800;color:{color};">{p}%</span>'
            f'<span style="font-size:8px;color:#5a1330;max-width:60px;line-height:1.1;">'
            f'{_esc(op.get("label", ""))}</span></div></div>')


_BUILDERS = {"add_text": _build_text, "add_table": _build_table, "add_chart": _build_chart,
             "add_list": _build_list, "add_kpi": _build_kpi, "add_donut": _build_donut}


def _deletable_ancestor(node, root):
    """Élément à retirer pour 'supprimer' le segment : le parent direct porteur
    du texte, sans jamais remonter jusqu'à la racine."""
    el = node.parent
    return el if (el is not None and el is not root) else None


def apply_ops(html_in: str, ops: list[dict]) -> tuple[str, int]:
    """Applique les opérations de l'IA : replace / delete / add_text / add_table
    / add_chart. Renvoie (html_modifié, nb_appliquées).

    Sûreté : tout texte est ÉCHAPPÉ (html.escape ou nœud BeautifulSoup) ; les
    ajouts sont des fragments construits par NOUS (l'IA ne fournit que des
    données), insérés via marqueurs pour éviter que la re-sérialisation ne
    déforme leur SVG. La casse des attributs SVG existants est restaurée."""
    from bs4 import BeautifulSoup, NavigableString
    soup = BeautifulSoup(html_in, "html.parser")
    root = soup.select_one(".dc-fiche") or soup
    nodes = [t for t in root.find_all(string=True)
             if not any(getattr(p, "name", None) in _SKIP_ANCESTORS for p in t.parents)
             and _meaningful(str(t))]
    if getattr(root, "name", None) and "position" not in (root.get("style", "") or ""):
        root["style"] = (root.get("style", "") or "") + ";position:relative"

    pending, n, ins = {}, 0, 0
    for op in ops or []:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "replace":
            i, txt = op.get("i"), op.get("text")
            if isinstance(i, int) and txt is not None and 0 <= i < len(nodes):
                orig = str(nodes[i])
                lead = orig[: len(orig) - len(orig.lstrip())]
                trail = orig[len(orig.rstrip()):]
                nodes[i].replace_with(NavigableString(lead + str(txt) + trail))
                n += 1
        elif kind == "delete":
            i = op.get("i")
            if isinstance(i, int) and 0 <= i < len(nodes):
                tgt = _deletable_ancestor(nodes[i], root)
                if tgt is not None:
                    tgt.extract()
                    n += 1
        elif kind == "style":
            i = op.get("i")
            if isinstance(i, int) and 0 <= i < len(nodes):
                el = nodes[i].parent
                if el is not None and el is not root and getattr(el, "name", None):
                    add = []
                    if op.get("color"):
                        add.append(f"color:{_safe_color(op['color'], '#5a1330')}")
                    if op.get("background"):
                        add.append(f"background:{_safe_color(op['background'], 'transparent')}")
                    if op.get("bold") is True:
                        add.append("font-weight:700")
                    if op.get("align") in ("left", "center", "right"):
                        add.append(f"text-align:{op['align']}")
                    sz = op.get("size")
                    if isinstance(sz, (int, float)):
                        add.append(f"font-size:{max(6, min(80, int(sz)))}px")
                    elif sz in ("larger", "plus", "+", "bigger"):
                        add.append("font-size:larger")
                    elif sz in ("smaller", "moins", "-"):
                        add.append("font-size:smaller")
                    if add:
                        el["style"] = (el.get("style", "") or "").rstrip(";") + ";" + ";".join(add)
                        n += 1
        elif kind in _BUILDERS:
            frag = _BUILDERS[kind](op, ins)
            if frag:
                token = f"__AIINS_{ins}__"
                marker = soup.new_tag("div")
                marker["data-ai-ins"] = "1"
                marker.string = token
                root.append(marker)
                pending[token] = frag
                ins += 1
                n += 1

    if not n:
        return html_in, 0
    out = _restore_svg_case(str(soup))
    for token, frag in pending.items():
        out = out.replace(token, frag, 1)
    return out, n


def apply_edits(html: str, edits: list[dict]) -> tuple[str, int]:
    """Compat : ancien format {i, replace} -> opérations replace."""
    return apply_ops(html, [{"op": "replace", "i": e.get("i"), "text": e.get("replace")}
                            for e in (edits or []) if isinstance(e, dict)])


# --------------------------------------------------------------------------- #
#  Thèmes de couleurs (changer le design sans toucher aux données)            #
# --------------------------------------------------------------------------- #
import colorsys

# clé -> (libellé, teinte primaire, teinte accent). None = design d'origine.
THEMES = {
    "bordeaux": ("🍷 Bordeaux (défaut)", None, None),
    "bleu":     ("🌊 Bleu marine", 212, 34),
    "vert":     ("🌿 Vert", 150, 44),
    "violet":   ("🔮 Violet", 278, 40),
    "sarcelle": ("💠 Sarcelle", 186, 40),
    "rouille":  ("🔥 Rouille", 14, 40),
    "prune":    ("🍇 Prune", 320, 30),
}


def theme_labels() -> dict:
    return {k: v[0] for k, v in THEMES.items()}


def _recolor_component(r: int, g: int, b: int, ph: float, ah: float):
    """Décale la teinte d'une couleur de la charte (bordeaux -> primaire, or ->
    accent) en gardant clarté/saturation. Renvoie None (inchangé) pour les
    couleurs de données (vert/bleu/rouge), les gris et les crèmes/blancs."""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if l > 0.80:                                 # crème / blanc : garder le fond clair
        return None
    hue = h * 360
    if s > 0.15 and 300 <= hue <= 360:           # bordeaux / magenta -> primaire
        nh = ph
    elif s > 0.22 and 18 <= hue <= 55:           # or / orange -> accent
        nh = ah
    else:
        return None                              # vert/bleu/rouge (données), gris… inchangés
    r2, g2, b2 = colorsys.hls_to_rgb((nh % 360) / 360, l, s)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})(?![0-9a-fA-F])")
_RGB_RE = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)")


def recolor(html: str, theme: str) -> str:
    """Applique un thème de couleurs à toute la fiche (hex ET rgb()), sans
    toucher aux couleurs de données ni aux crèmes. À appliquer sur le HTML aux
    couleurs d'origine (le thème est recalculé, jamais empilé)."""
    conf = THEMES.get(theme)
    if not conf or conf[1] is None:
        return html
    _, ph, ah = conf

    def hx(m):
        r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        nc = _recolor_component(r, g, b, ph, ah)
        return ("#%02x%02x%02x" % nc) if nc else m.group(0)

    def rg(m):
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        nc = _recolor_component(r, g, b, ph, ah)
        return ("rgb(%d, %d, %d)" % nc) if nc else m.group(0)

    return _RGB_RE.sub(rg, _HEX_RE.sub(hx, html))


# --------------------------------------------------------------------------- #
#  Conversation avec Gemini                                                    #
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "Tu es l'assistant d'édition d'une fiche infographique du HCP "
    "(Haut-Commissariat au Plan, Maroc) sur le marché du travail. Tu peux "
    "améliorer le texte (reformuler, raccourcir, corriger, traduire FR↔AR, ton "
    "institutionnel), MAIS AUSSI modifier la STRUCTURE : ajouter du texte, des "
    "tableaux, des graphiques, ou supprimer un élément. Tu NE changes jamais les "
    "chiffres existants sauf demande explicite. Écris dans la langue demandée. "
    "Concis et factuel.\n\n"
    "On te fournit les SEGMENTS de texte de la fiche, numérotés [i]. Réfère un "
    "segment existant par son indice i (n'invente pas d'indice).\n\n"
    "L'utilisateur peut JOINDRE des fichiers : une image ou un PDF (que tu vois "
    "directement) ou des données Excel/CSV (fournies en texte). Lis-les et "
    "utilise leur contenu pour proposer des ajouts pertinents — par ex. "
    "transformer un tableau d'image/Excel en op add_table, ou ses chiffres en "
    "op add_chart.\n\n"
    "Réponds STRICTEMENT en JSON, sans texte autour :\n"
    '{ "reply": "<réponse en clair à l\'utilisateur>", "ops": [ ... ] }\n'
    "Chaque opération de \"ops\" est l'un de :\n"
    '• {"op":"replace","i":<indice>,"text":"<nouveau texte>"}  (remplace un segment)\n'
    '• {"op":"delete","i":<indice>}  (supprime l\'élément du segment)\n'
    '• {"op":"add_text","tag":"h3"|"p","text":"...","after":<indice|null>}\n'
    '• {"op":"add_table","title":"...","headers":["A","B"],"rows":[["1","2"],["3","4"]],"after":<indice|null>}\n'
    '• {"op":"add_chart","chart":"bar"|"line","title":"...","labels":["2019","2020"],'
    '"series":[{"name":"Taux","color":"#4a9d3f","values":[43.0,41.5]}],"after":<indice|null>}\n'
    '• {"op":"style","i":<indice>,"color":"#c0392b","background":"#fff","bold":true,'
    '"align":"center","size":18}  (mise en forme d\'un texte ; toutes les clés sont facultatives)\n'
    '• {"op":"add_list","title":"...","items":["point 1","point 2","point 3"]}  (liste à puces)\n'
    '• {"op":"add_kpi","value":"24 %","label":"Jeunes NEET","color":"#7a1c3f"}  (grand chiffre-clé)\n'
    '• {"op":"add_donut","percent":61,"label":"Services","color":"#4a9d3f"}  (anneau de pourcentage)\n'
    "Règles : les valeurs de graphiques sont numériques ; les couleurs en hex "
    "(#rrggbb). Ne mets JAMAIS de balises HTML dans les textes — juste du texte "
    "brut. Les éléments ajoutés apparaissent dans la fiche et l'utilisateur peut "
    "les déplacer. Si tu ne fais que discuter, renvoie \"ops\": []."
)


# ---- fichiers joints au chat -------------------------------------------- #
_IMG_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "webp": "image/webp", "gif": "image/gif"}
UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "pdf", "xlsx", "xls", "csv"]
_MAX_MEDIA_BYTES = 12 * 1024 * 1024   # ~12 Mo par image/PDF (limite inline)
_MAX_DOC_CHARS = 4000                 # par fichier tableur


def _spreadsheet_to_text(name: str, data: bytes, ext: str) -> str:
    import io
    import pandas as pd
    if ext == "csv":
        df = pd.read_csv(io.BytesIO(data))
        return f"Fichier {name} :\n" + df.head(60).to_csv(index=False)[:_MAX_DOC_CHARS]
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)  # toutes les feuilles
    parts = []
    for sh, df in sheets.items():
        parts.append(f"Feuille « {sh} » ({name}) :\n"
                     + df.head(60).to_csv(index=False)[:_MAX_DOC_CHARS])
    return "\n\n".join(parts)


def process_uploads(files: list[tuple]) -> tuple[list[dict], str, list[str], list[str]]:
    """files : liste de (name, mime, data:bytes).
    Renvoie (media, doc_text, labels, warnings) :
      media  = [{mime, data}] pour images/PDF (envoyés tels quels à Gemini) ;
      doc_text = données Excel/CSV converties en texte ;
      labels = étiquettes pour l'affichage ; warnings = fichiers écartés."""
    media, docs, labels, warns = [], [], [], []
    for name, mime, data in files or []:
        mime = mime or ""
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext in _IMG_MIME or mime.startswith("image/"):
            if len(data) > _MAX_MEDIA_BYTES:
                warns.append(f"{name} : image trop lourde (> 12 Mo), ignorée.")
                continue
            media.append({"mime": _IMG_MIME.get(ext, mime or "image/png"), "data": data})
            labels.append(f"🖼️ {name}")
        elif ext == "pdf" or mime == "application/pdf":
            if len(data) > _MAX_MEDIA_BYTES:
                warns.append(f"{name} : PDF trop lourd (> 12 Mo), ignoré.")
                continue
            media.append({"mime": "application/pdf", "data": data})
            labels.append(f"📄 {name}")
        elif ext in ("xlsx", "xls", "csv"):
            try:
                docs.append(_spreadsheet_to_text(name, data, ext))
                labels.append(f"📊 {name}")
            except Exception as exc:
                warns.append(f"{name} : illisible ({exc}).")
        else:
            warns.append(f"{name} : type non pris en charge, ignoré.")
    return media, "\n\n".join(docs), labels, warns


def converse(history: list[dict], user_msg: str, segments: list[str],
             model: str | None = None, media: list[dict] | None = None,
             doc_text: str = "") -> tuple[str, list[dict]]:
    """Envoie l'historique + le message + les segments (+ éventuellement des
    fichiers joints) à Gemini. `media` = liste de {mime, data(bytes)} (images,
    PDF — Gemini les lit nativement) ; `doc_text` = données extraites d'un
    Excel/CSV. Renvoie (réponse_texte, ops). Lève RuntimeError si souci."""
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
    if doc_text:
        prompt += ("\n\nDONNÉES DES FICHIERS JOINTS (Excel/CSV) — utilise-les "
                   "pour construire tableaux/graphiques si demandé :\n" + doc_text)
    # Multimodal : texte d'abord, puis les images/PDF joints.
    contents: list = [prompt]
    for m in media or []:
        try:
            contents.append(types.Part.from_bytes(data=m["data"], mime_type=m["mime"]))
        except Exception:
            pass
    used_model = model or _model_name()
    try:
        resp = client.models.generate_content(
            model=used_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                response_mime_type="application/json",
                temperature=0.4,
            ),
        )
        raw = (resp.text or "").strip()
    except Exception as exc:
        raise RuntimeError(_friendly_api_error(exc, used_model)) from exc

    # Parse JSON tolérant (au cas où le modèle enrobe le JSON).
    reply, ops = _parse_json_reply(raw)
    return reply, ops


def _friendly_api_error(exc: Exception, model: str | None = None) -> str:
    """Transforme une erreur d'API brute en message actionnable pour l'utilisateur."""
    code = getattr(exc, "code", None)
    s = str(exc)
    low = s.lower()
    mdl = f" (modèle demandé : `{model}`)" if model else ""
    if code == 429 or "RESOURCE_EXHAUSTED" in s or "quota" in low:
        return (
            f"🚦 Quota Gemini épuisé{mdl}. Souvent, le projet Google n'a **aucun "
            "palier gratuit** pour ce modèle/région. Deux options :\n\n"
            "• Essayez un modèle actuel (`gemini-2.5-flash`, `gemini-2.5-flash-lite`) "
            "via `model` dans les secrets — voir « 🔧 Modèles disponibles » ci-dessous.\n"
            "• Ou activez la **facturation** sur votre projet Google (Gemini Flash "
            "coûte quelques centimes par million de tokens)."
        )
    if "API_KEY_INVALID" in s or ("api key" in low and "not valid" in low) or code == 401:
        return "🔑 Clé API invalide — vérifiez `api_key` sous `[gemini]` dans les secrets."
    if code == 404 or "NOT_FOUND" in s:
        return (
            f"🔎 Modèle introuvable{mdl}. Mettez `model` sous `[gemini]` dans les "
            "secrets sur un modèle **actuel** — ex. `gemini-2.5-flash`, "
            "`gemini-2.5-flash-lite` ou l'alias `gemini-flash-latest`. Cliquez "
            "« 🔧 Modèles disponibles » ci-dessous pour voir la liste exacte de votre clé."
        )
    return f"⚠️ Erreur de l'API Gemini : {exc}"


def probe_model(model: str) -> str:
    """Mini-appel generateContent réel : renvoie le message BRUT (OK ou erreur
    complète de Google), pour diagnostiquer un 404/quota précis. Ne lève pas."""
    key = _key()
    if not key:
        return "(pas de clé configurée)"
    try:
        from google.genai import types
        client = _client(key)
        r = client.models.generate_content(
            model=model, contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        return f"✅ OK — « {model} » répond : {(r.text or '').strip()[:60] or '(vide)'}"
    except Exception as exc:
        return f"❌ {type(exc).__name__} sur « {model} » :\n{exc}"


def list_models() -> list[str]:
    """Noms des modèles accessibles avec la clé configurée (diagnostic).
    Ne garde que ceux qui supportent generateContent. Ne lève jamais."""
    key = _key()
    if not key:
        return []
    try:
        client = _client(key)
        out = []
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            if not name:
                continue
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            out.append(name)
        return sorted(set(out))
    except Exception as exc:
        return [f"⚠️ erreur en listant les modèles : {exc}"]


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
    return reply, _clean_ops(data)


def _clean_ops(data: dict) -> list[dict]:
    """Valide/normalise les opérations. Accepte le nouveau format `ops` et
    l'ancien `edits` ({i, replace} -> op replace)."""
    ops = []
    for e in data.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("i"), int):
            ops.append({"op": "replace", "i": e["i"], "text": str(e.get("replace", ""))})
    for o in data.get("ops") or []:
        if not isinstance(o, dict):
            continue
        kind = o.get("op")
        if kind == "replace" and isinstance(o.get("i"), int):
            ops.append({"op": "replace", "i": o["i"], "text": str(o.get("text", ""))})
        elif kind == "delete" and isinstance(o.get("i"), int):
            ops.append({"op": "delete", "i": o["i"]})
        elif kind == "add_text" and o.get("text"):
            ops.append({"op": "add_text", "tag": str(o.get("tag", "p")),
                        "text": str(o["text"])})
        elif kind == "add_table" and (o.get("headers") or o.get("rows")):
            ops.append({"op": "add_table", "title": str(o.get("title", "")),
                        "headers": [str(h) for h in (o.get("headers") or [])],
                        "rows": [[str(c) for c in (r if isinstance(r, list) else [r])]
                                 for r in (o.get("rows") or [])]})
        elif kind == "add_chart" and o.get("series"):
            ops.append({"op": "add_chart", "chart": str(o.get("chart", "bar")),
                        "title": str(o.get("title", "")),
                        "labels": [str(x) for x in (o.get("labels") or [])],
                        "series": o.get("series") or []})
        elif kind == "style" and isinstance(o.get("i"), int):
            st = {"op": "style", "i": o["i"]}
            for k in ("color", "background", "align", "size"):
                if o.get(k) is not None:
                    st[k] = o[k]
            if o.get("bold") is not None:
                st["bold"] = bool(o["bold"])
            if len(st) > 2:  # au moins une propriété à changer
                ops.append(st)
        elif kind == "add_list" and o.get("items"):
            ops.append({"op": "add_list", "title": str(o.get("title", "")),
                        "items": [str(x) for x in o["items"]]})
        elif kind == "add_kpi" and o.get("value") is not None:
            ops.append({"op": "add_kpi", "value": str(o.get("value", "")),
                        "label": str(o.get("label", "")), "color": o.get("color")})
        elif kind == "add_donut" and o.get("percent") is not None:
            ops.append({"op": "add_donut", "percent": o.get("percent"),
                        "label": str(o.get("label", "")), "color": o.get("color")})
    return ops


def op_summary(op: dict) -> str:
    """Libellé lisible d'une opération (pour l'aperçu avant application)."""
    k = op.get("op")
    if k == "replace":
        return f"✏️ Modifier le texte #{op.get('i')}"
    if k == "delete":
        return f"🗑️ Supprimer l'élément #{op.get('i')}"
    if k == "add_text":
        return f"➕ Ajouter un texte : « {op.get('text', '')[:40]} »"
    if k == "add_table":
        return f"➕ Ajouter un tableau ({len(op.get('rows') or [])} lignes)"
    if k == "add_chart":
        return f"➕ Ajouter un graphique {op.get('chart', '')} ({len(op.get('series') or [])} série(s))"
    if k == "style":
        return f"🎨 Mettre en forme le texte #{op.get('i')}"
    if k == "add_list":
        return f"➕ Ajouter une liste ({len(op.get('items') or [])} points)"
    if k == "add_kpi":
        return f"➕ Ajouter un chiffre-clé : {op.get('value', '')}"
    if k == "add_donut":
        return f"➕ Ajouter un anneau {op.get('percent', '')} %"
    return str(k)
