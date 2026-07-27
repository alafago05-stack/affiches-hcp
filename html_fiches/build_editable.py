#!/usr/bin/env python3
"""build_editable.py — Transforme une fiche HTML (export « .dc.html ») en une
page autonome ÉDITABLE.

À partir du HTML source du HCP (design figé), on produit un fichier HTML
unique et hors-ligne où :
  - chaque texte/chiffre de la fiche devient modifiable **sur place** (clic +
    saisie), avec un aperçu du changement en direct ;
  - une barre d'outils permet d'exporter en PDF (impression navigateur) et de
    réinitialiser ;
  - le logo est intégré en data-URI (aucun fichier externe requis).

Le petit moteur de gabarit du source (`sc-for` pour les barres SU, `sc-if`
pour le glossaire) est « aplati » ici en HTML statique, pour ne pas dépendre
du framework d'origine.
"""

import base64
import re
from pathlib import Path

HERE = Path(__file__).parent


def _logo_data_uri(logo_path: Path) -> str:
    b = logo_path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


def _expand_su_bars(content: str) -> str:
    """Remplace les blocs `sc-for` (barres SU) par 4 barres concrètes.
    Valeurs et logique reprises du script `x-dc` du fichier source."""
    su = [("SU1", 8.2, "معدل البطالة بالمفهوم الضيق"),
          ("SU2", 11.3, "المعدل المركب للبطالة بالمفهوم الضيق والشغل الناقص المرتبط بساعات العمل"),
          ("SU3", 13.2, "المعدل المركب للبطالة بالمفهوم الضيق والقوى العاملة المحتملة"),
          ("SU4", 16.1, "المعدل المركب للاستخدام غير الكامل للقوى العاملة")]
    vmax = max(v for _, v, _ in su) * 1.15 or 1
    bars = [{"key": k, "valueLabel": f"{v:.1f}".replace(".", ",") + "%",
             "heightPct": f"{v / vmax * 100:.1f}%", "desc": d} for k, v, d in su]

    def expand(m):
        tpl = m.group(1)
        out = []
        for b in bars:
            s = tpl
            for key, val in b.items():
                s = s.replace("{{ b." + key + " }}", val)
            out.append(s)
        return "".join(out)

    return re.sub(r"<sc-for[^>]*>(.*?)</sc-for>", expand, content, flags=re.S)


def _extract_fiche(dc_html: str, logo_uri: str) -> str:
    """Extrait le <div> racine de la fiche du fichier .dc.html, aplatit les
    éventuels sc-if/sc-for, intègre le logo, et marque le div racine.

    Gère les deux formats d'export rencontrés :
      - avec <doc-page> (EMO) : contenu entre la balise et </doc-page> ;
      - sans doc-page (NEET) : contenu entre </helmet> et </x-dc>.
    """
    if "<doc-page" in dc_html:
        i = dc_html.index(">", dc_html.index("<doc-page")) + 1
        j = dc_html.index("</doc-page>")
    else:
        i = dc_html.index("</helmet>") + len("</helmet>")
        j = dc_html.index("</x-dc>")
    content = dc_html[i:j].strip()

    # glossaire/sections optionnels toujours affichés : on retire sc-if
    content = re.sub(r"<sc-if[^>]*>", "", content)
    content = content.replace("</sc-if>", "")
    # barres répétées (EMO) : on aplatit en HTML statique (no-op ailleurs)
    content = _expand_su_bars(content)

    # logo : soit <img src="assets/hcp-logo.png">, soit un <image-slot> vide
    content = content.replace("assets/hcp-logo.png", logo_uri)
    logo_img = (f'<img src="{logo_uri}" alt="HCP" style="max-width:100%;max-height:100%;'
                'width:auto;height:auto;object-fit:contain;display:block;margin:auto;">')
    content = re.sub(r'<image-slot[^>]*id="hcp-logo"[^>]*>\s*</image-slot>',
                     lambda m: logo_img, content)

    # marque le div racine (premier <div) pour le ciblage de l'éditeur
    content = content.replace("<div", '<div class="dc-fiche"', 1)
    return content


_PAGE = """<!DOCTYPE html>
<html lang="{lang}" dir="{dir}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Tajawal:wght@400;500;700;800&family=Spectral:wght@500;600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  body {{ margin: 0; background: #e9e3e6; font-family: 'Manrope','Cairo',sans-serif; }}

  .dc-toolbar {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    background: linear-gradient(105deg,#5a1330,#7a1c3f 70%,#8f2549);
    color: #fff; display: flex; align-items: center; gap: 12px;
    padding: 9px 16px; box-shadow: 0 2px 10px rgba(0,0,0,.25);
  }}
  .dc-toolbar .ttl {{ font-weight: 800; font-size: 14px; white-space: nowrap; }}
  .dc-toolbar .hint {{ font-size: 12px; color: #e7cdd6; flex: 1; line-height: 1.3; }}
  .dc-toolbar .hint b {{ color: #f3d99b; }}
  .dc-btn {{
    border: none; border-radius: 9px; font-weight: 800; font-size: 13px;
    padding: 9px 15px; cursor: pointer; font-family: inherit; white-space: nowrap;
  }}
  .dc-btn.pdf {{ background: #c19a4b; color: #3d1122; }}
  .dc-btn.pdf:hover {{ background: #d3ad5c; }}
  .dc-btn.ghost {{ background: rgba(255,255,255,.14); color: #fff; }}
  .dc-btn.ghost:hover {{ background: rgba(255,255,255,.26); }}
  .dc-btn:disabled {{ opacity: .4; cursor: default; }}

  .dc-stage {{ display: flex; justify-content: center; padding: 84px 20px 40px; overflow-x: auto; }}
  .dc-fiche {{ box-shadow: 0 12px 40px rgba(90,19,48,.22); flex: 0 0 auto; }}  /* jamais compressée */

  /* survol : signale l'élément visé ; sélection : contour net */
  .dc-hover {{ outline: 1.5px dashed rgba(193,154,75,.9) !important; outline-offset: 1px; }}
  .dc-selected {{ outline: 2px solid #7a1c3f !important; outline-offset: 1px; }}
  [contenteditable="true"] {{ cursor: text; }}
  [contenteditable="true"]:focus {{ outline: 2px solid #7a1c3f !important; background: rgba(255,249,224,.65); }}

  /* mini-barre d'actions flottante attachée à l'élément sélectionné */
  .dc-mini {{
    position: absolute; z-index: 2000; display: none; gap: 3px;
    background: #3d1122; border-radius: 9px; padding: 4px;
    box-shadow: 0 4px 14px rgba(0,0,0,.35);
  }}
  .dc-mini.on {{ display: flex; }}
  .dc-mini button {{
    border: none; background: #7a1c3f; color: #fff; border-radius: 6px;
    padding: 5px 9px; cursor: pointer; font-size: 13px; font-family: inherit; font-weight: 700;
  }}
  .dc-mini button:hover {{ background: #9a2848; }}
  .dc-mini button.mv {{ background: #c19a4b; color: #3d1122; cursor: move; }}
  .dc-mini button.del:hover {{ background: #b3271f; }}

  @media print {{
    .dc-toolbar, .dc-mini {{ display: none !important; }}
    body {{ background: #fff; }}
    .dc-stage {{ padding: 0; display: block; }}
    .dc-fiche {{ box-shadow: none; zoom: 0.685; }}  /* tient sur une page A4 */
    .dc-hover, .dc-selected {{ outline: none !important; }}
    [contenteditable="true"]:focus {{ outline: none !important; background: none !important; }}
    @page {{ size: A4 portrait; margin: 0; }}
  }}
</style>
</head>
<body>
  <div class="dc-toolbar">
    <span class="ttl">{title}</span>
    <span class="hint">Clique un élément : <b>✎ modifier</b> le texte · <b>✥ déplacer</b> (glisser) · <b>⬆ parent</b> · <b>🗑 supprimer</b>. Double-clic = éditer le texte.</span>
    <button class="dc-btn ghost" id="dc-undo" title="Annuler (Ctrl+Z)">↶ Annuler</button>
    <button class="dc-btn pdf" onclick="window.print()">🖨️ Exporter en PDF</button>
    <button class="dc-btn ghost" onclick="location.reload()">↩️ Tout réinitialiser</button>
  </div>
  <div class="dc-stage">
    {fiche}
  </div>

  <div class="dc-mini" id="dc-mini">
    <button data-act="edit" title="Modifier le texte">✎</button>
    <button data-act="move" class="mv" title="Déplacer (glisser)">✥</button>
    <button data-act="parent" title="Sélectionner l'élément parent">⬆</button>
    <button data-act="del" class="del" title="Supprimer">🗑</button>
  </div>

  <script>
  (function () {{
    const root = document.querySelector('.dc-fiche');
    const mini = document.getElementById('dc-mini');
    const undoBtn = document.getElementById('dc-undo');
    if (!root) return;

    let selected = null, hovered = null, editing = null;
    const undo = [];

    function snapshot() {{
      undo.push(root.innerHTML);
      if (undo.length > 40) undo.shift();
      undoBtn.disabled = undo.length === 0;
    }}
    function doUndo() {{
      if (!undo.length) return;
      root.innerHTML = undo.pop();
      undoBtn.disabled = undo.length === 0;
      deselect();
    }}
    undoBtn.disabled = true;
    undoBtn.onclick = doUndo;

    function placeMini() {{
      if (!selected) return;
      const r = selected.getBoundingClientRect();
      mini.style.top = (window.scrollY + r.top - 40) + 'px';
      mini.style.left = (window.scrollX + r.left) + 'px';
    }}
    function select(el) {{
      if (!el || el === root || !root.contains(el)) return;
      deselect(true);
      selected = el;
      el.classList.add('dc-selected');
      mini.classList.add('on');
      placeMini();
    }}
    function deselect(keepMini) {{
      if (selected) selected.classList.remove('dc-selected');
      selected = null;
      if (!keepMini) mini.classList.remove('on');
    }}
    function stopEdit() {{
      if (editing) {{ editing.removeAttribute('contenteditable'); editing = null; }}
    }}
    function edit(el) {{
      stopEdit(); snapshot();
      el.setAttribute('contenteditable', 'true'); el.spellcheck = false;
      editing = el; el.focus();
    }}

    // --- survol ---
    root.addEventListener('mouseover', function (e) {{
      if (editing || dragging) return;
      if (hovered) hovered.classList.remove('dc-hover');
      hovered = e.target === root ? null : e.target;
      if (hovered) hovered.classList.add('dc-hover');
    }});
    root.addEventListener('mouseout', function () {{
      if (hovered) {{ hovered.classList.remove('dc-hover'); hovered = null; }}
    }});

    // --- sélection / édition ---
    root.addEventListener('click', function (e) {{
      if (editing) return;
      e.preventDefault(); e.stopPropagation();
      select(e.target);
    }});
    root.addEventListener('dblclick', function (e) {{
      e.preventDefault(); e.stopPropagation();
      select(e.target); edit(e.target);
    }});
    // clic ailleurs = déselection ; Entrée = saut de ligne simple
    document.addEventListener('click', function (e) {{
      if (root.contains(e.target) || mini.contains(e.target)) return;
      stopEdit(); deselect();
    }});
    root.addEventListener('keydown', function (e) {{
      if (e.key === 'Enter' && editing) {{ e.preventDefault(); document.execCommand('insertLineBreak'); }}
    }});
    document.addEventListener('keydown', function (e) {{
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {{ e.preventDefault(); doUndo(); }}
      if ((e.key === 'Delete') && selected && !editing) {{ e.preventDefault(); removeSel(); }}
    }});

    function removeSel() {{
      if (!selected) return;
      snapshot(); const el = selected; deselect(); el.remove();
    }}

    // --- actions de la mini-barre ---
    mini.addEventListener('click', function (e) {{
      const b = e.target.closest('button'); if (!b || !selected) return;
      const act = b.dataset.act;
      if (act === 'edit') edit(selected);
      else if (act === 'parent') {{ const p = selected.parentElement; if (p && p !== root && root.contains(p)) select(p); }}
      else if (act === 'del') removeSel();
    }});

    // --- déplacement par glisser (bouton ✥) ---
    let dragging = false, sx = 0, sy = 0, bx = 0, by = 0, target = null;
    mini.querySelector('[data-act="move"]').addEventListener('mousedown', function (e) {{
      if (!selected) return;
      e.preventDefault();
      dragging = true; target = selected; snapshot();
      sx = e.clientX; sy = e.clientY;
      const m = /translate\\((-?[0-9.]+)px,\\s*(-?[0-9.]+)px\\)/.exec(target.style.transform || '');
      bx = m ? parseFloat(m[1]) : 0; by = m ? parseFloat(m[2]) : 0;
      document.body.style.userSelect = 'none';
    }});
    document.addEventListener('mousemove', function (e) {{
      if (!dragging) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      target.style.transform = 'translate(' + (bx + dx) + 'px,' + (by + dy) + 'px)';
      placeMini();
    }});
    document.addEventListener('mouseup', function () {{
      if (dragging) {{ dragging = false; document.body.style.userSelect = ''; placeMini(); }}
    }});
    window.addEventListener('scroll', placeMini, true);
  }})();
  </script>
</body>
</html>
"""


def build(dc_html_path, logo_path, out_path, title, lang="ar"):
    dc = Path(dc_html_path).read_text(encoding="utf-8")
    logo_uri = _logo_data_uri(Path(logo_path))
    fiche = _extract_fiche(dc, logo_uri)
    page = _PAGE.format(
        lang=lang, dir="rtl" if lang == "ar" else "ltr",
        title=title, fiche=fiche,
    )
    Path(out_path).write_text(page, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    src = HERE.parent.parent.parent / "_html_src"
    logo = src / "emo" / "assets" / "hcp-logo.png"  # même logo HCP pour toutes
    jobs = [
        (src / "emo" / "Affiche EMO2026 Souss-Massa.dc.html",
         HERE / "emo_editable.html", "Fiche EMO 2026 — Souss-Massa", "ar"),
        (src / "neet" / "Affiche NEET Souss-Massa 2024.dc.html",
         HERE / "neet_editable.html", "Fiche NEET — Souss-Massa 2024", "fr"),
    ]
    for dc, out_path, title, lang in jobs:
        if dc.exists():
            print("écrit :", build(dc, logo, out_path, title, lang=lang))
