#!/usr/bin/env python3
"""build_editable.py — Transforme une fiche HTML (design figé du HCP) en une
page autonome ÉDITABLE : chaque texte/chiffre se modifie sur place, et l'on
peut sélectionner, déplacer (glisser), supprimer, annuler, puis exporter en
PDF (impression navigateur).

Deux entrées possibles :
  - un export « .dc.html » propre (EMO, NEET) → mode `build()` : on extrait le
    <div> racine, on aplatit les gabarits (sc-for/sc-if), on intègre le logo,
    et on emballe dans une page autonome.
  - un fichier « compressé » (bundler auto-décompressé, ex. la fiche
    « Situation ») → mode `augment_bundled()` : on injecte l'éditeur qui
    s'active APRÈS le rendu du bundler (il construit lui-même sa barre
    d'outils), sans toucher au contenu généré.

L'éditeur (CSS + JS ci-dessous) est partagé par les deux modes.
"""

import base64
import json
import re
from pathlib import Path

HERE = Path(__file__).parent

FONTS = ("https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900"
         "&family=Tajawal:wght@400;500;700;800&family=Spectral:wght@500;600;700;800"
         "&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500"
         "&family=Manrope:wght@400;600;700;800&display=swap")

# ==========================================================================
# Éditeur partagé (CSS + JS). Le JS construit lui-même sa barre d'outils et
# attend que la fiche soit rendue (utile en mode « compressé » asynchrone).
# ==========================================================================
EDITOR_CSS = """
  .dc-has-editor { padding-top: 62px !important; }
  .dc-toolbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100000;
    background: linear-gradient(105deg,#5a1330,#7a1c3f 70%,#8f2549);
    color: #fff; display: flex; align-items: center; gap: 12px;
    padding: 9px 16px; box-shadow: 0 2px 10px rgba(0,0,0,.25);
    font-family: 'Manrope','Cairo',sans-serif;
  }
  .dc-toolbar .ttl { font-weight: 800; font-size: 14px; white-space: nowrap; }
  .dc-toolbar .hint { font-size: 12px; color: #e7cdd6; flex: 1; line-height: 1.3; }
  .dc-toolbar .hint b { color: #f3d99b; }
  .dc-btn { border: none; border-radius: 9px; font-weight: 800; font-size: 13px;
            padding: 9px 15px; cursor: pointer; font-family: inherit; white-space: nowrap; }
  .dc-btn.pdf { background: #c19a4b; color: #3d1122; }
  .dc-btn.pdf:hover { background: #d3ad5c; }
  .dc-btn.ghost { background: rgba(255,255,255,.14); color: #fff; }
  .dc-btn.ghost:hover { background: rgba(255,255,255,.26); }
  .dc-btn:disabled { opacity: .4; cursor: default; }

  .dc-hover { outline: 1.5px dashed rgba(193,154,75,.9) !important; outline-offset: 1px; }
  .dc-selected { outline: 2px solid #7a1c3f !important; outline-offset: 1px; }
  [contenteditable="true"] { cursor: text; }
  [contenteditable="true"]:focus { outline: 2px solid #7a1c3f !important; background: rgba(255,249,224,.65); }

  .dc-mini { position: absolute; z-index: 100001; display: none; gap: 3px;
             background: #3d1122; border-radius: 9px; padding: 4px;
             box-shadow: 0 4px 14px rgba(0,0,0,.35); font-family: 'Manrope',sans-serif; }
  .dc-mini.on { display: flex; }
  .dc-mini button { border: none; background: #7a1c3f; color: #fff; border-radius: 6px;
                    padding: 5px 9px; cursor: pointer; font-size: 13px; font-weight: 700; }
  .dc-mini button:hover { background: #9a2848; }
  .dc-mini button.mv { background: #c19a4b; color: #3d1122; cursor: move; }
  .dc-mini button.del:hover { background: #b3271f; }

  @media print {
    .dc-toolbar, .dc-mini { display: none !important; }
    .dc-has-editor { padding-top: 0 !important; }
    body { background: #fff !important; }
    .dc-stage { padding: 0 !important; display: block !important; }
    .dc-fiche, doc-page > div { box-shadow: none !important; }
    .dc-hover, .dc-selected { outline: none !important; }
    [contenteditable="true"]:focus { outline: none !important; background: none !important; }
    @page { size: A4 portrait; margin: 0; }
  }
"""

EDITOR_JS = r"""
(function () {
  function boot() {
    var root = document.querySelector('.dc-fiche') || document.querySelector('doc-page > div');
    if (!root) { return setTimeout(boot, 150); }
    if (root.__dcInit) return; root.__dcInit = true;
    init(root);
  }
  function init(root) {
    document.body.classList.add('dc-has-editor');

    var tb = document.createElement('div');
    tb.className = 'dc-toolbar';
    tb.innerHTML = '<span class="ttl">Fiche éditable</span>'
      + '<span class="hint">Clique un élément : <b>✎ modifier</b> · <b>✥ déplacer</b> (glisser) · '
      + '<b>⬆ parent</b> · <b>🗑 supprimer</b>. Double-clic = éditer le texte.</span>'
      + '<button class="dc-btn ghost" id="dc-undo" title="Annuler (Ctrl+Z)">↶ Annuler</button>'
      + '<button class="dc-btn pdf" id="dc-pdf">🖨️ Exporter en PDF</button>'
      + '<button class="dc-btn ghost" id="dc-reset">↩️ Réinitialiser</button>';
    document.body.appendChild(tb);

    var mini = document.createElement('div');
    mini.className = 'dc-mini';
    mini.innerHTML = '<button data-act="edit" title="Modifier le texte">✎</button>'
      + '<button data-act="move" class="mv" title="Déplacer">✥</button>'
      + '<button data-act="parent" title="Sélectionner le parent">⬆</button>'
      + '<button data-act="del" class="del" title="Supprimer">🗑</button>';
    document.body.appendChild(mini);

    var selected = null, hovered = null, editing = null, undo = [];
    var undoBtn = document.getElementById('dc-undo');
    document.getElementById('dc-pdf').onclick = function () { window.print(); };
    document.getElementById('dc-reset').onclick = function () { location.reload(); };
    undoBtn.disabled = true;
    undoBtn.onclick = doUndo;

    function snapshot() { undo.push(root.innerHTML); if (undo.length > 40) undo.shift(); undoBtn.disabled = false; }
    function doUndo() { if (!undo.length) return; root.innerHTML = undo.pop(); undoBtn.disabled = undo.length === 0; deselect(); }
    function placeMini() {
      if (!selected) return;
      var r = selected.getBoundingClientRect();
      mini.style.top = (window.scrollY + r.top - 40) + 'px';
      mini.style.left = (window.scrollX + r.left) + 'px';
    }
    function select(el) {
      if (!el || el === root || !root.contains(el)) return;
      deselect(true); selected = el; el.classList.add('dc-selected');
      mini.classList.add('on'); placeMini();
    }
    function deselect(keepMini) {
      if (selected) selected.classList.remove('dc-selected');
      selected = null; if (!keepMini) mini.classList.remove('on');
    }
    function stopEdit() { if (editing) { editing.removeAttribute('contenteditable'); editing = null; } }
    function edit(el) { stopEdit(); snapshot(); el.setAttribute('contenteditable', 'true'); el.spellcheck = false; editing = el; el.focus(); }
    function removeSel() { if (!selected) return; snapshot(); var el = selected; deselect(); el.remove(); }

    // --- liaison chiffre -> graphique (anneaux conic-gradient + barres CSS %) ---
    function num(s) { var v = parseFloat((s || '').replace(/[^0-9,.\-]/g, '').replace(',', '.')); return isFinite(v) ? v : 0; }
    function styleOf(el) { return el.getAttribute('style') || ''; }
    function ancestorConic(el) {
      var a = el.parentElement;
      while (a && a !== root) { if (styleOf(a).indexOf('conic-gradient') >= 0) return a; a = a.parentElement; }
      return null;
    }
    function updateDonut(donut, v) {
      v = Math.max(0, Math.min(100, v));
      donut.setAttribute('style', styleOf(donut).replace(/conic-gradient\(([^)]*)\)/, function (m, inner) {
        var seg = inner.split(',');
        var c0 = seg[0].trim().split(/\s+/)[0];
        var c1 = (seg[1] || '#eeeeee 0% 100%').trim().split(/\s+/)[0];
        return 'conic-gradient(' + c0 + ' 0% ' + v + '%,' + c1 + ' ' + v + '% 100%)';
      }));
    }
    // dimension VARIABLE d'une barre (< 100 %) — une barre a souvent aussi
    // width:100% (pleine largeur) qu'il ne faut pas confondre avec la hauteur.
    function barDim(el) {
      var s = styleOf(el), re = /(height|width):\s*([0-9.]+)%/g, m, best = null;
      while ((m = re.exec(s))) { var v = parseFloat(m[2]); if (v < 100) best = { axis: m[1], val: v }; }
      return best;
    }
    function updateBarGroup(col) {
      var row = col.parentElement; if (!row) return;
      var items = [];
      [].forEach.call(row.children, function (cc) {
        var lbl = null, bar = null, bd = null;
        [].forEach.call(cc.querySelectorAll('*'), function (c) {
          if (!bar) { var d = barDim(c); if (d) { bar = c; bd = d; } }
          if (!lbl && c.children.length === 0 && /[0-9]/.test(c.textContent || '')) lbl = c;
        });
        if (lbl && bar) items.push({ bar: bar, axis: bd.axis, val: num(lbl.textContent) });
      });
      if (!items.length) return;
      var maxV = Math.max.apply(null, items.map(function (i) { return i.val; })) || 1;
      var full = Math.max.apply(null, items.map(function (i) { return barDim(i.bar).val; })) || 100;
      items.forEach(function (it) {
        var dim = (it.val / maxV * full).toFixed(1);
        it.bar.setAttribute('style', styleOf(it.bar).replace(
          new RegExp('(' + it.axis + ':\\s*)[0-9.]+%'), '$1' + dim + '%'));
      });
    }
    function applyBinding(el) {
      if (!el || el === root || el.children.length) return;
      var txt = (el.textContent || '').trim();
      if (!/[0-9]/.test(txt)) return;
      var donut = ancestorConic(el);
      if (donut) { updateDonut(donut, num(txt)); return; }
      var col = el.parentElement;
      if (col && [].some.call(col.querySelectorAll('*'), barDim)) updateBarGroup(col);
    }

    root.addEventListener('mouseover', function (e) {
      if (editing || dragging) return;
      if (hovered) hovered.classList.remove('dc-hover');
      hovered = e.target === root ? null : e.target;
      if (hovered) hovered.classList.add('dc-hover');
    });
    root.addEventListener('mouseout', function () { if (hovered) { hovered.classList.remove('dc-hover'); hovered = null; } });
    root.addEventListener('click', function (e) { if (editing) return; e.preventDefault(); e.stopPropagation(); select(e.target); });
    root.addEventListener('dblclick', function (e) { e.preventDefault(); e.stopPropagation(); select(e.target); edit(e.target); });
    document.addEventListener('click', function (e) { if (root.contains(e.target) || mini.contains(e.target)) return; stopEdit(); deselect(); });
    root.addEventListener('keydown', function (e) { if (e.key === 'Enter' && editing) { e.preventDefault(); document.execCommand('insertLineBreak'); } });
    root.addEventListener('input', function (e) { applyBinding(e.target); });
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); doUndo(); }
      if (e.key === 'Delete' && selected && !editing) { e.preventDefault(); removeSel(); }
    });
    mini.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b || !selected) return;
      var act = b.dataset.act;
      if (act === 'edit') edit(selected);
      else if (act === 'parent') { var p = selected.parentElement; if (p && p !== root && root.contains(p)) select(p); }
      else if (act === 'del') removeSel();
    });

    var dragging = false, sx = 0, sy = 0, bx = 0, by = 0, target = null;
    mini.querySelector('[data-act="move"]').addEventListener('mousedown', function (e) {
      if (!selected) return;
      e.preventDefault(); dragging = true; target = selected; snapshot();
      sx = e.clientX; sy = e.clientY;
      var m = /translate\((-?[0-9.]+)px,\s*(-?[0-9.]+)px\)/.exec(target.style.transform || '');
      bx = m ? parseFloat(m[1]) : 0; by = m ? parseFloat(m[2]) : 0;
      document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      target.style.transform = 'translate(' + (bx + e.clientX - sx) + 'px,' + (by + e.clientY - sy) + 'px)';
      placeMini();
    });
    document.addEventListener('mouseup', function () { if (dragging) { dragging = false; document.body.style.userSelect = ''; placeMini(); } });
    window.addEventListener('scroll', placeMini, true);
  }
  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot);
})();
"""


# ==========================================================================
# Helpers d'extraction (mode .dc.html)
# ==========================================================================
def _logo_data_uri(logo_path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(logo_path).read_bytes()).decode()


def _expand_su_bars(content: str) -> str:
    """Aplatit les blocs `sc-for` (barres SU d'EMO) en 4 barres statiques."""
    su = [("SU1", 8.2, "معدل البطالة بالمفهوم الضيق"),
          ("SU2", 11.3, "المعدل المركب للبطالة بالمفهوم الضيق والشغل الناقص المرتبط بساعات العمل"),
          ("SU3", 13.2, "المعدل المركب للبطالة بالمفهوم الضيق والقوى العاملة المحتملة"),
          ("SU4", 16.1, "المعدل المركب للاستخدام غير الكامل للقوى العاملة")]
    vmax = max(v for _, v, _ in su) * 1.15 or 1
    bars = [{"key": k, "valueLabel": f"{v:.1f}".replace(".", ",") + "%",
             "heightPct": f"{v / vmax * 100:.1f}%", "desc": d} for k, v, d in su]

    def expand(m):
        tpl, out = m.group(1), []
        for b in bars:
            s = tpl
            for key, val in b.items():
                s = s.replace("{{ b." + key + " }}", val)
            out.append(s)
        return "".join(out)

    return re.sub(r"<sc-for[^>]*>(.*?)</sc-for>", expand, content, flags=re.S)


def _extract_fiche(dc_html: str, logo_uri: str) -> str:
    if "<doc-page" in dc_html:
        i = dc_html.index(">", dc_html.index("<doc-page")) + 1
        j = dc_html.index("</doc-page>")
    else:
        i = dc_html.index("</helmet>") + len("</helmet>")
        j = dc_html.index("</x-dc>")
    content = dc_html[i:j].strip()
    content = re.sub(r"<sc-if[^>]*>", "", content).replace("</sc-if>", "")
    content = _expand_su_bars(content)
    content = content.replace("assets/hcp-logo.png", logo_uri)
    logo_img = (f'<img src="{logo_uri}" alt="HCP" style="max-width:100%;max-height:100%;'
                'width:auto;height:auto;object-fit:contain;display:block;margin:auto;">')
    content = re.sub(r'<image-slot[^>]*id="hcp-logo"[^>]*>\s*</image-slot>', lambda m: logo_img, content)
    content = content.replace("<div", '<div class="dc-fiche"', 1)
    return content


_PAGE = """<!DOCTYPE html>
<html lang="__LANG__" dir="__DIR__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="__FONTS__" rel="stylesheet">
<style>
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body { margin: 0; background: #e9e3e6; font-family: 'Manrope','Cairo',sans-serif; }
  .dc-stage { display: flex; justify-content: center; padding: 22px 20px 40px; overflow-x: auto; }
  .dc-fiche { box-shadow: 0 12px 40px rgba(90,19,48,.22); flex: 0 0 auto; }
  /* impression : mise à l'échelle pour tenir sur une page A4 (par fiche) */
  @media print { .dc-fiche { zoom: __PRINTZOOM__; } }
__EDITOR_CSS__
</style>
</head>
<body>
  <div class="dc-stage">
    __FICHE__
  </div>
  <script>__EDITOR_JS__</script>
</body>
</html>
"""


def _print_zoom(fiche_html: str) -> str:
    """Zoom d'impression = hauteur A4 (1123px à 96 dpi) / hauteur de la fiche,
    pour que l'affiche tienne sur une seule page A4."""
    m = re.search(r"height:\s*(\d+)px", fiche_html)
    h = int(m.group(1)) if m else 1123
    return f"{min(1.0, 1123.0 / h):.3f}"


def _wrap(fiche: str, out_path, title, lang):
    page = (_PAGE.replace("__LANG__", lang).replace("__DIR__", "rtl" if lang == "ar" else "ltr")
            .replace("__TITLE__", title).replace("__FONTS__", FONTS)
            .replace("__PRINTZOOM__", _print_zoom(fiche))
            .replace("__EDITOR_CSS__", EDITOR_CSS).replace("__EDITOR_JS__", EDITOR_JS)
            .replace("__FICHE__", fiche))
    Path(out_path).write_text(page, encoding="utf-8")
    return out_path


def build(dc_html_path, logo_path, out_path, title, lang="ar"):
    dc = Path(dc_html_path).read_text(encoding="utf-8")
    fiche = _extract_fiche(dc, _logo_data_uri(logo_path))
    return _wrap(fiche, out_path, title, lang)


def build_from_rendered(rendered_html: str, logo_path, out_path, title, lang="fr"):
    """Construit la page éditable à partir du HTML DÉJÀ RENDU (capturé dans le
    navigateur) — pour les fiches dont les gabarits ne s'aplatissent pas
    proprement en Python (ex. « Situation »). Le logo doit y figurer sous la
    forme du marqueur `LOGO_PLACEHOLDER`."""
    fiche = rendered_html.replace("LOGO_PLACEHOLDER", _logo_data_uri(logo_path))
    fiche = fiche.replace("<div", '<div class="dc-fiche"', 1)
    return _wrap(fiche, out_path, title, lang)


def augment_bundled(bundled_path, out_path, title):
    """Injecte l'éditeur dans une page « compressée » (auto-décompressée par
    son propre JS, qui RECONSTRUIT tout le DOM au chargement).

    Piège : ce bundler efface tout ce qu'on met dans <body> et les balises
    statiques du <head>. Seul un <script> du <head>, exécuté au parsing,
    survit — car il enregistre un écouteur `load` qui se déclenche APRÈS la
    reconstruction. On y injecte donc, à ce moment-là, la CSS de l'éditeur
    (créée par JS) puis on lance l'éditeur (lui aussi démarre sur `load`)."""
    html = Path(bundled_path).read_text(encoding="utf-8")
    css_loader = (
        "<script>window.addEventListener('load',function(){"
        "var s=document.createElement('style');s.textContent=" + json.dumps(EDITOR_CSS) + ";"
        "document.head.appendChild(s);document.title=" + json.dumps(title) + ";"
        "});</script>"
    )
    inject = css_loader + "<script>" + EDITOR_JS + "</script>"
    html = html.replace("</head>", inject + "</head>", 1)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    proj = HERE.parent.parent.parent
    src = proj / "_html_src"
    logo = src / "emo" / "assets" / "hcp-logo.png"
    if src.exists():
        for dc, out, title, lang in [
            (src / "emo" / "Affiche EMO2026 Souss-Massa.dc.html", HERE / "emo_editable.html", "Fiche EMO 2026 — Souss-Massa", "ar"),
            (src / "neet" / "Affiche NEET Souss-Massa 2024.dc.html", HERE / "neet_editable.html", "Fiche NEET — Souss-Massa 2024", "fr"),
        ]:
            if dc.exists():
                print("écrit :", build(dc, logo, out, title, lang=lang))
    # NB : la fiche « Situation » n'existe qu'au format compressé (bundler),
    # dont le rendu dépend de l'emplacement des assets → `augment_bundled` y
    # est peu fiable. On la traitera dès qu'on aura son export « .dc.html »
    # (comme EMO et NEET), pour un résultat propre et identique.
