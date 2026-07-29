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


# Librairies d'export PDF chargées depuis un CDN (et NON intégrées) : un gros
# JS minifié intégré dans le HTML déclenche des faux positifs antivirus qui
# suppriment le fichier. html-to-image donne un rendu fidèle (arabe/RTL +
# dégradés coniques + polices), jsPDF assemble le PDF. L'édition fonctionne
# hors-ligne ; seul l'export PDF a besoin d'internet — sinon l'éditeur bascule
# automatiquement sur l'impression du navigateur (repli dans downloadPdf).
VENDOR = ('<script src="https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.js"></script>'
          '<script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"></script>')

# ==========================================================================
# Éditeur partagé (CSS + JS). Le JS construit lui-même sa barre d'outils et
# attend que la fiche soit rendue (utile en mode « compressé » asynchrone).
# ==========================================================================
EDITOR_CSS = """
  .dc-has-editor { padding-top: 60px; }  /* remplacé dynamiquement par la hauteur réelle de la barre */
  .dc-toolbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100000;
    background: linear-gradient(105deg,#5a1330,#7a1c3f 70%,#8f2549);
    color: #fff; display: flex; align-items: center; gap: 8px 12px; flex-wrap: wrap;
    padding: 8px 16px; box-shadow: 0 2px 10px rgba(0,0,0,.25);
    font-family: 'Manrope','Cairo',sans-serif;
  }
  .dc-toolbar .ttl { font-weight: 800; font-size: 14px; white-space: nowrap; flex: none; }
  .dc-toolbar .hint { font-size: 12px; color: #e7cdd6; flex: 1 1 120px; min-width: 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dc-toolbar .hint b { color: #f3d99b; }
  .dc-btn { border: none; border-radius: 9px; font-weight: 800; font-size: 13px;
            padding: 9px 15px; cursor: pointer; font-family: inherit; white-space: nowrap; }
  .dc-btn.pdf { background: #c19a4b; color: #3d1122; }
  .dc-btn.pdf:hover { background: #d3ad5c; }
  .dc-btn.save { background: #4e9a50; color: #fff; }
  .dc-btn.save:hover { background: #5aab5c; }
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

  /* panneau de style (couleurs / gras / taille / alignement) */
  .dc-style { position: absolute; z-index: 100002; display: none; flex-direction: column; gap: 4px;
              background: #fff; border: 1px solid #e0d5cc; border-radius: 10px; padding: 6px;
              box-shadow: 0 6px 18px rgba(0,0,0,.28); font-family: 'Manrope',sans-serif; }
  .dc-style.on { display: flex; }
  .dc-style .pr { display: flex; align-items: center; gap: 4px; }
  .dc-style .pr > span { font-size: 11px; color: #6a4152; width: 42px; flex: none; }
  .dc-style button { border: 1px solid #e0d5cc; background: #f7eff2; color: #3d1122; border-radius: 5px;
                     min-width: 26px; height: 24px; cursor: pointer; font-size: 12px; font-weight: 700; padding: 0 6px; }
  .dc-style button:hover { background: #efdfe6; }
  .dc-style button.sw { width: 20px; min-width: 20px; height: 20px; padding: 0; border-radius: 50%; }
  .dc-style input[type=color] { width: 28px; height: 24px; padding: 0; border: 1px solid #e0d5cc; border-radius: 5px; background: #fff; cursor: pointer; }

  .dc-chartdata { position: absolute; z-index: 100002; display: none; background: #fff; border: 1px solid #e0d5cc;
                  border-radius: 10px; padding: 8px 10px; box-shadow: 0 6px 18px rgba(0,0,0,.28);
                  font-family: 'Manrope',sans-serif; max-width: 520px; }
  .dc-chartdata.on { display: block; }
  .dc-chartdata .ch-hd { font-size: 12px; font-weight: 700; color: #5a1330; margin-bottom: 6px; }
  .dc-chartdata .ch-body { display: flex; flex-wrap: wrap; gap: 6px; }
  .dc-chartdata .ch-it { display: flex; align-items: center; gap: 4px; }
  .dc-chartdata .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }
  .dc-chartdata input { width: 58px; padding: 3px 6px; border: 1px solid #e0d5cc; border-radius: 5px; font-size: 12px; }

  .dc-btn.add { background: #c19a4b; color: #3d1122; }
  .dc-btn.add:hover { background: #d3ad5c; }
  .dc-insmenu { position: absolute; z-index: 100003; display: none; flex-direction: column; gap: 2px;
                background: #fff; border: 1px solid #e0d5cc; border-radius: 10px; padding: 5px;
                box-shadow: 0 6px 18px rgba(0,0,0,.28); font-family: 'Manrope',sans-serif; }
  .dc-insmenu.on { display: flex; }
  .dc-insmenu button { border: none; background: transparent; color: #3d1122; text-align: left;
                       padding: 7px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap; }
  .dc-insmenu button:hover { background: #f7eff2; }

  @media print {
    .dc-toolbar, .dc-mini, .dc-style, .dc-insmenu, .dc-chartdata { display: none !important; }
    .dc-has-editor { padding-top: 0 !important; }
    body { background: #fff !important; }
    .dc-stage { padding: 0 !important; display: block !important; }
    .dc-fiche, doc-page > div { box-shadow: none !important; margin: 0 auto !important; }
    .dc-hover, .dc-selected { outline: none !important; }
    [contenteditable="true"]:focus { outline: none !important; background: none !important; }
    @page { size: A4 portrait; margin: 8mm; }
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
      + '<span class="hint" title="Clique un élément : ✎ éditer le texte (double-clic) · ⧉ dupliquer · '
      + '✥ déplacer (glisser ou flèches) · 🎨 style · 🗑 supprimer · ➕ insérer">'
      + 'Clique un élément : ✎ texte · ⧉ dupliquer · ✥ déplacer · 🎨 style · 🗑 supprimer</span>'
      + '<button class="dc-btn add" id="dc-insert" title="Ajouter texte, tableau, graphe…">➕ Insérer ▾</button>'
      + '<button class="dc-btn ghost" id="dc-undo" title="Annuler (Ctrl+Z)">↶ Annuler</button>'
      + '<button class="dc-btn ghost" id="dc-redo" title="Rétablir (Ctrl+Y)">↷ Rétablir</button>'
      + '<button class="dc-btn save" id="dc-save" title="Enregistrer votre version (télécharge le HTML modifié, réouvrable et éditable)">💾 Enregistrer</button>'
      + '<button class="dc-btn pdf" id="dc-pdf" title="Télécharge directement le PDF (A4)">⬇️ Exporter en PDF</button>'
      + '<button class="dc-btn ghost" id="dc-reset">↩️ Réinitialiser</button>';
    document.body.appendChild(tb);

    var mini = document.createElement('div');
    mini.className = 'dc-mini';
    mini.innerHTML = '<button data-act="edit" title="Modifier le texte">✎</button>'
      + '<button data-act="dup" title="Dupliquer">⧉</button>'
      + '<button data-act="move" class="mv" title="Déplacer (glisser)">✥</button>'
      + '<button data-act="parent" title="Sélectionner le bloc parent">⬆</button>'
      + '<button data-act="style" title="Style : couleur, gras, taille, alignement">🎨</button>'
      + '<button data-act="del" class="del" title="Supprimer">🗑</button>';
    document.body.appendChild(mini);

    // panneau de style (couleurs / gras / taille / alignement)
    var SW = ['#7a1c3f', '#5a1330', '#c19a4b', '#e09040', '#3d1122', '#6a4152', '#4e9a50', '#3b6fa0', '#ffffff', '#f6efe7'];
    function swHtml(kind) {
      return SW.map(function (c) { return '<button class="sw" data-k="' + kind + '" data-c="' + c + '" style="background:' + c + '"></button>'; }).join('');
    }
    var panel = document.createElement('div');
    panel.className = 'dc-style';
    panel.innerHTML =
        '<div class="pr"><button data-s="bold" title="Gras"><b>G</b></button>'
      + '<button data-s="bigger" title="Agrandir le texte">A+</button>'
      + '<button data-s="smaller" title="Réduire le texte">A−</button>'
      + '<button data-s="left" title="Aligner à gauche">⯇</button>'
      + '<button data-s="center" title="Centrer">≡</button>'
      + '<button data-s="right" title="Aligner à droite">⯈</button></div>'
      + '<div class="pr"><span>Texte</span>' + swHtml('color') + '<input type="color" data-k="color" title="Couleur personnalisée"></div>'
      + '<div class="pr"><span>Fond</span>' + swHtml('background') + '<input type="color" data-k="background" title="Fond personnalisé"><button data-s="nobg" title="Sans fond">∅</button></div>';
    document.body.appendChild(panel);

    // menu « Insérer » (nouveaux éléments)
    var insMenu = document.createElement('div');
    insMenu.className = 'dc-insmenu';
    insMenu.innerHTML = '<button data-ins="text">📝 Bloc de texte</button>'
      + '<button data-ins="title">🔠 Titre</button>'
      + '<button data-ins="table">▦ Tableau</button>'
      + '<button data-ins="bars">📊 Graphe (barres)</button>'
      + '<button data-ins="donut">◔ Anneau (%)</button>';
    document.body.appendChild(insMenu);

    // panneau « Données du graphe » (pour les graphes SVG dont le texte n'est
    // pas éditable au clavier : on modifie les valeurs ici, ça redessine)
    var chartPanel = document.createElement('div');
    chartPanel.className = 'dc-chartdata';
    document.body.appendChild(chartPanel);

    var selected = null, hovered = null, editing = null, nudged = false, undo = [], redo = [];
    var chartModel = null, chartEditing = false, chartSvg = null;
    var undoBtn = document.getElementById('dc-undo'), redoBtn = document.getElementById('dc-redo');
    document.getElementById('dc-pdf').onclick = downloadPdf;
    document.getElementById('dc-reset').onclick = function () { location.reload(); };

    // Exporte la fiche en PDF A4 et le TÉLÉCHARGE directement (sans boîte
    // d'impression). On capture la fiche en image via html-to-image (rendu
    // fidèle : arabe/RTL, dégradés coniques, polices intégrées), puis on la
    // place dans un PDF A4 (une page, 8 mm de marge) via jsPDF. Repli sur
    // l'impression navigateur si les librairies ne sont pas chargées.
    function downloadPdf() {
      if (!window.htmlToImage || !window.jspdf) { window.print(); return; }
      stopEdit(); deselect();
      var btn = document.getElementById('dc-pdf'), lbl = btn.innerHTML;
      btn.disabled = true; btn.innerHTML = '⏳ PDF…';
      var prev = root.style.zoom; root.style.zoom = '';
      function done() { root.style.zoom = prev; btn.disabled = false; btn.innerHTML = lbl; fitAll(); }
      window.htmlToImage.toJpeg(root, { pixelRatio: 2, quality: 0.95, backgroundColor: '#ffffff' }).then(function (dataUrl) {
        var img = new Image();
        img.onload = function () {
          var pdf = new window.jspdf.jsPDF({ orientation: 'p', unit: 'mm', format: 'a4', compress: true });
          var pw = 210, ph = 297, m = 8, aw = pw - 2 * m, ah = ph - 2 * m;
          var s = Math.min(aw / img.width, ah / img.height);
          var w = img.width * s, h = img.height * s;
          pdf.addImage(dataUrl, 'JPEG', (pw - w) / 2, (ph - h) / 2, w, h);
          pdf.save((document.title || 'fiche').replace(/[^\w\-]+/g, '_') + '.pdf');
          done();
        };
        img.src = dataUrl;
      }).catch(function (e) { done(); alert('Impossible de générer le PDF : ' + e); });
    }
    document.getElementById('dc-save').onclick = save;
    undoBtn.onclick = doUndo; redoBtn.onclick = doRedo;

    // Télécharge la fiche AVEC les modifications : on clone le document, on
    // retire les éléments d'interface de l'éditeur (recréés au chargement) et
    // les états transitoires (sélection, contenteditable). Le fichier obtenu
    // est un HTML autonome identique aux fiches d'origine — donc réouvrable et
    // à nouveau éditable, avec le contenu modifié conservé.
    function save() {
      stopEdit(); deselect(); insMenu.classList.remove('on');
      var docEl = document.documentElement.cloneNode(true);
      ['.dc-toolbar', '.dc-mini', '.dc-style', '.dc-insmenu'].forEach(function (s) {
        var e = docEl.querySelector(s); if (e) e.remove();
      });
      var b = docEl.querySelector('body'); if (b) b.classList.remove('dc-has-editor');
      var f = docEl.querySelector('.dc-fiche');
      if (f) {
        f.style.zoom = '';
        [].forEach.call(f.querySelectorAll('.dc-selected, .dc-hover, [contenteditable]'), function (e) {
          e.classList.remove('dc-selected'); e.classList.remove('dc-hover'); e.removeAttribute('contenteditable');
        });
      }
      var html = '<!DOCTYPE html>\n' + docEl.outerHTML;
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
      a.download = (document.title || 'fiche').replace(/[^\w\-]+/g, '_') + '.html';
      document.body.appendChild(a); a.click(); a.remove();
    }
    function updateBtns() { undoBtn.disabled = !undo.length; redoBtn.disabled = !redo.length; }
    updateBtns();

    function snapshot() { undo.push(root.innerHTML); if (undo.length > 60) undo.shift(); redo = []; updateBtns(); }
    function doUndo() { if (!undo.length) return; redo.push(root.innerHTML); root.innerHTML = undo.pop(); deselect(); updateBtns(); }
    function doRedo() { if (!redo.length) return; undo.push(root.innerHTML); root.innerHTML = redo.pop(); deselect(); updateBtns(); }
    function placeMini() {
      if (!selected) return;
      var r = selected.getBoundingClientRect();
      mini.style.top = (window.scrollY + r.top - 40) + 'px';
      mini.style.left = (window.scrollX + r.left) + 'px';
      placePanel();
    }
    function placePanel() {
      if (!panel.classList.contains('on') || !selected) return;
      var r = selected.getBoundingClientRect();
      panel.style.top = (window.scrollY + r.bottom + 6) + 'px';
      panel.style.left = (window.scrollX + r.left) + 'px';
    }
    function select(el) {
      if (!el || el === root || !root.contains(el)) return;
      deselect(true); selected = el; nudged = false; el.classList.add('dc-selected');
      mini.classList.add('on'); placeMini();
      var ch = chartOf(el);
      if (ch) { showChartPanel(ch); } else { chartPanel.classList.remove('on'); chartSvg = null; }
    }
    function deselect(keepMini) {
      if (selected) selected.classList.remove('dc-selected');
      selected = null; panel.classList.remove('on'); chartPanel.classList.remove('on'); chartSvg = null;
      if (!keepMini) mini.classList.remove('on');
    }
    function stopEdit() { if (editing) { editing.removeAttribute('contenteditable'); editing = null; } }
    function edit(el) { stopEdit(); snapshot(); el.setAttribute('contenteditable', 'true'); el.spellcheck = false; editing = el; el.focus(); }
    function removeSel() { if (!selected) return; snapshot(); var el = selected; deselect(); el.remove(); }

    // --- actions « style utilisateur » ---
    function duplicate() { if (!selected) return; snapshot(); var c = selected.cloneNode(true); if (selected.parentNode) selected.parentNode.insertBefore(c, selected.nextSibling); select(c); }
    function fontStep(d) { if (!selected) return; snapshot(); var cur = parseFloat(getComputedStyle(selected).fontSize) || 14; selected.style.fontSize = Math.max(6, cur + d) + 'px'; }
    function toggleBold() { if (!selected) return; snapshot(); var w = getComputedStyle(selected).fontWeight; selected.style.fontWeight = (w === 'bold' || parseInt(w, 10) >= 600) ? '400' : '700'; }
    function setAlign(a) { if (!selected) return; snapshot(); selected.style.textAlign = a; }
    function setStyleProp(prop, val) {
      if (!selected) return; snapshot();
      if (prop === 'background') { selected.style.background = val; selected.style.backgroundImage = (val === 'transparent' ? 'none' : ''); }
      else { selected.style.color = val; }
    }
    function nudge(dx, dy) {
      if (!selected) return;
      if (!nudged) { snapshot(); nudged = true; }
      var m = /translate\((-?[0-9.]+)px,\s*(-?[0-9.]+)px\)/.exec(selected.style.transform || '');
      selected.style.transform = 'translate(' + ((m ? parseFloat(m[1]) : 0) + dx) + 'px,' + ((m ? parseFloat(m[2]) : 0) + dy) + 'px)';
      placeMini();
    }

    // --- insertion de nouveaux éléments (texte, titre, tableau, graphes) ---
    var TD = 'style="padding:6px 14px;border:1px solid #e0d5cc;"';
    function barsHtml() {
      var cols = [['A', 60], ['B', 80], ['C', 45], ['D', 30]];
      return '<div style="display:flex;align-items:flex-end;gap:16px;height:130px;padding:12px;margin:8px;border:1px solid #e0d5cc;border-radius:10px;background:#fff;">'
        + cols.map(function (c) {
          return '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:6px;">'
            + '<div style="font-weight:800;font-size:15px;color:#7a1c3f;">' + c[1] + '%</div>'
            + '<div style="width:100%;max-width:52px;height:' + c[1] + '%;background:linear-gradient(180deg,#a63b5c,#7a1c3f);border-radius:6px 6px 0 0;"></div>'
            + '<div style="font-size:12px;font-weight:700;color:#5a1330;">' + c[0] + '</div></div>';
        }).join('') + '</div>';
    }
    var SNIPPETS = {
      text: '<div style="padding:8px 10px;font-size:14px;line-height:1.45;color:#3d1122;">Nouveau texte — cliquez pour le modifier.</div>',
      title: '<div style="padding:6px 10px;font-weight:800;font-size:20px;color:#7a1c3f;">Nouveau titre</div>',
      table: '<table style="border-collapse:collapse;font-size:13px;margin:8px;background:#fff;text-align:center;">'
        + '<tr style="background:#5a1330;color:#fff;font-weight:700;"><td ' + TD + '>Colonne 1</td><td ' + TD + '>Colonne 2</td><td ' + TD + '>Colonne 3</td></tr>'
        + '<tr><td ' + TD + '>—</td><td ' + TD + '>—</td><td ' + TD + '>—</td></tr>'
        + '<tr><td ' + TD + '>—</td><td ' + TD + '>—</td><td ' + TD + '>—</td></tr></table>',
      bars: barsHtml(),
      donut: '<div style="display:inline-flex;align-items:center;gap:12px;padding:10px;margin:8px;">'
        + '<div style="width:74px;height:74px;border-radius:50%;background:conic-gradient(#7a1c3f 0% 60%,#f0dde4 60% 100%);display:flex;align-items:center;justify-content:center;">'
        + '<div style="width:52px;height:52px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;color:#7a1c3f;">60%</div></div>'
        + '<div style="font-weight:700;font-size:14px;color:#3d1122;">Libellé — modifier</div></div>'
    };
    function insertEl(kind) {
      var tpl = SNIPPETS[kind]; if (!tpl) return;
      snapshot();
      var w = document.createElement('div'); w.innerHTML = tpl.trim();
      var el = w.firstChild;
      var ref = (selected && root.contains(selected)) ? selected : null;
      if (ref && ref.parentNode && root.contains(ref.parentNode)) ref.parentNode.insertBefore(el, ref.nextSibling);
      else root.appendChild(el);
      insMenu.classList.remove('on');
      fitAll(); select(el);
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }

    // --- graphes SVG (courbe / barres) : panneau de données -> redessin ---
    function isValTxt(t) { return /^-?\d+[.,]\d+$/.test((t.textContent || '').trim()); }
    function svgNum(t) { return parseFloat((t.textContent || '').replace(',', '.')); }
    function fmtNum(v) { return (Math.round(v * 10) / 10).toFixed(1).replace('.', ','); }
    function attr(e, n) { return parseFloat(e.getAttribute(n)); }
    function colorOf(e) {
      // Une polyligne a fill="none" + stroke="couleur" ; un cercle a fill="couleur".
      // On saute "none" pour apparier un point (fill) à sa courbe (stroke).
      var cand = [e.getAttribute('fill'), e.getAttribute('stroke'), e.style.fill, e.style.stroke];
      for (var i = 0; i < cand.length; i++) { var c = cand[i]; if (c && c !== 'none') return c.toLowerCase(); }
      return '';
    }
    function fitLin(pts) {
      var n = pts.length, sx = 0, sy = 0, sxx = 0, sxy = 0;
      pts.forEach(function (p) { sx += p[0]; sy += p[1]; sxx += p[0] * p[0]; sxy += p[0] * p[1]; });
      var den = n * sxx - sx * sx || 1;
      var b = (n * sxy - sx * sy) / den;
      return { a: (sy - b * sx) / n, b: b };
    }
    function chartOf(el) {
      var a = el;
      while (a && a !== root) { if (a.tagName && a.tagName.toLowerCase() === 'svg') break; a = a.parentNode; }
      if (a && a.tagName && a.tagName.toLowerCase() === 'svg'
          && (a.querySelectorAll('polyline').length || a.querySelectorAll('rect').length >= 3)
          && [].some.call(a.querySelectorAll('text'), isValTxt)) return a;
      return null;
    }
    function parseChart(svg) {
      var labels = [].filter.call(svg.querySelectorAll('text'), isValTxt);
      var items = [];
      if (svg.querySelectorAll('polyline').length) {           // ----- COURBE -----
        var circles = [].slice.call(svg.querySelectorAll('circle'));
        var polys = [].slice.call(svg.querySelectorAll('polyline'));
        var matched = labels.map(function (lb) {
          var lx = attr(lb, 'x'), ly = attr(lb, 'y');
          var cand = circles.filter(function (c) { return Math.abs(attr(c, 'cx') - lx) < 5; });
          if (!cand.length) return null;
          cand.sort(function (a, b) { return Math.abs(attr(a, 'cy') - ly) - Math.abs(attr(b, 'cy') - ly); });
          return { lb: lb, circle: cand[0] };
        }).filter(Boolean);
        var sc = fitLin(matched.map(function (m) { return [svgNum(m.lb), attr(m.circle, 'cy')]; }));
        matched.forEach(function (m) {
          var color = colorOf(m.circle);
          var poly = polys.filter(function (p) { return colorOf(p) === color; })[0];
          var group = circles.filter(function (c) { return colorOf(c) === color; }).sort(function (a, b) { return attr(a, 'cx') - attr(b, 'cx'); });
          var idx = group.indexOf(m.circle), cx = attr(m.circle, 'cx');
          items.push({
            label: m.lb, value: svgNum(m.lb), color: color, apply: function (v) {
              var cy = sc.a + sc.b * v, oldY = attr(m.circle, 'cy');
              m.circle.setAttribute('cy', cy.toFixed(2));
              if (poly && idx >= 0) { var pts = poly.getAttribute('points').trim().split(/\s+/); if (idx < pts.length) { pts[idx] = cx.toFixed(1) + ',' + cy.toFixed(1); poly.setAttribute('points', pts.join(' ')); } }
              m.lb.setAttribute('y', (attr(m.lb, 'y') + (cy - oldY)).toFixed(1));
              m.lb.textContent = fmtNum(v);
            }
          });
        });
      } else {                                                 // ----- BARRES -----
        var rects = [].slice.call(svg.querySelectorAll('rect'));
        var baseline = Math.max.apply(null, rects.map(function (r) { return attr(r, 'y') + attr(r, 'height'); }));
        labels.forEach(function (lb) {
          var lx = attr(lb, 'x');
          var rect = rects.slice().sort(function (a, b) {
            return Math.abs(attr(a, 'x') + attr(a, 'width') / 2 - lx) - Math.abs(attr(b, 'x') + attr(b, 'width') / 2 - lx);
          })[0];
          if (!rect) return;
          var v0 = svgNum(lb), k = v0 > 0 ? attr(rect, 'height') / v0 : 2.8;
          items.push({
            label: lb, value: v0, color: colorOf(rect), apply: function (v) {
              var h = Math.max(0, v * k);
              rect.setAttribute('height', h.toFixed(2)); rect.setAttribute('y', (baseline - h).toFixed(2));
              lb.setAttribute('y', (baseline - h - 2).toFixed(1)); lb.textContent = fmtNum(v);
            }
          });
        });
      }
      return { items: items };
    }
    function placeChartPanel() {
      if (!chartPanel.classList.contains('on') || !chartSvg) return;
      var r = chartSvg.getBoundingClientRect();
      chartPanel.style.top = (window.scrollY + r.bottom + 6) + 'px';
      chartPanel.style.left = (window.scrollX + Math.max(6, Math.min(r.left, window.innerWidth - 540))) + 'px';
    }
    function showChartPanel(svg) {
      chartSvg = svg; chartEditing = false;
      chartModel = parseChart(svg);
      if (!chartModel.items.length) { chartPanel.classList.remove('on'); return; }
      var h = '<div class="ch-hd">📊 Données du graphe — modifiez les valeurs</div><div class="ch-body">';
      chartModel.items.forEach(function (it, i) {
        h += '<label class="ch-it"><span class="dot" style="background:' + (it.color || '#7a1c3f') + '"></span>'
          + '<input type="number" step="0.1" data-i="' + i + '" value="' + (Math.round(it.value * 10) / 10) + '"></label>';
      });
      chartPanel.innerHTML = h + '</div>';
      chartPanel.classList.add('on'); placeChartPanel();
    }

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
    document.addEventListener('click', function (e) {
      if (!insMenu.contains(e.target) && e.target.id !== 'dc-insert') insMenu.classList.remove('on');
      if (root.contains(e.target) || mini.contains(e.target) || panel.contains(e.target)
          || insMenu.contains(e.target) || chartPanel.contains(e.target)) return;
      stopEdit(); deselect();
    });
    root.addEventListener('keydown', function (e) { if (e.key === 'Enter' && editing) { e.preventDefault(); document.execCommand('insertLineBreak'); } });
    root.addEventListener('input', function (e) { applyBinding(e.target); });
    document.addEventListener('keydown', function (e) {
      var k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === 'z' && !e.shiftKey) { e.preventDefault(); doUndo(); return; }
      if ((e.ctrlKey || e.metaKey) && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); doRedo(); return; }
      if (!selected || editing) return;
      if (e.key === 'Delete') { e.preventDefault(); removeSel(); }
      else if (e.key.indexOf('Arrow') === 0) {
        e.preventDefault(); var s = e.shiftKey ? 10 : 1;
        if (e.key === 'ArrowUp') nudge(0, -s); else if (e.key === 'ArrowDown') nudge(0, s);
        else if (e.key === 'ArrowLeft') nudge(-s, 0); else if (e.key === 'ArrowRight') nudge(s, 0);
      }
    });
    mini.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b || !selected) return;
      var act = b.dataset.act;
      if (act === 'edit') edit(selected);
      else if (act === 'dup') duplicate();
      else if (act === 'parent') { var p = selected.parentElement; if (p && p !== root && root.contains(p)) select(p); }
      else if (act === 'style') { if (panel.classList.contains('on')) panel.classList.remove('on'); else { panel.classList.add('on'); placePanel(); } }
      else if (act === 'del') removeSel();
    });
    panel.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.classList.contains('sw')) { setStyleProp(b.dataset.k, b.dataset.c); return; }
      var s = b.dataset.s;
      if (s === 'bold') toggleBold();
      else if (s === 'bigger') fontStep(1);
      else if (s === 'smaller') fontStep(-1);
      else if (s === 'left' || s === 'center' || s === 'right') setAlign(s);
      else if (s === 'nobg') setStyleProp('background', 'transparent');
    });
    panel.addEventListener('input', function (e) { if (e.target.type === 'color') setStyleProp(e.target.dataset.k, e.target.value); });
    chartPanel.addEventListener('input', function (e) {
      var inp = e.target; if (inp.tagName !== 'INPUT' || !chartModel) return;
      if (!chartEditing) { snapshot(); chartEditing = true; }
      var v = parseFloat(String(inp.value).replace(',', '.'));
      if (isFinite(v)) chartModel.items[+inp.dataset.i].apply(v);
    });
    document.getElementById('dc-insert').onclick = function (e) {
      e.stopPropagation();
      if (insMenu.classList.contains('on')) { insMenu.classList.remove('on'); return; }
      var r = this.getBoundingClientRect();
      insMenu.style.top = (window.scrollY + r.bottom + 4) + 'px';
      insMenu.style.left = (window.scrollX + Math.max(6, Math.min(r.left, window.innerWidth - 190))) + 'px';
      insMenu.classList.add('on');
    };
    insMenu.addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) insertEl(b.dataset.ins); });

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
    window.addEventListener('scroll', function () { placeMini(); placeChartPanel(); }, true);

    // --- impression : ajuster à une A4 (8 mm de marge) d'après la taille RÉELLE ---
    // A4 à 96 dpi = 794×1123 px ; zone utile après 8 mm de marge ≈ 734×1063 px.
    // Ajuste la fiche à l'affichage :
    //  1) hauteur — si le VRAI contenu dépasse le bas (cas « Situation »), on
    //     agrandit le cadre pour ne rien couper (overflow:hidden garde les
    //     décorations volontairement hors-cadre découpées, ex. filigrane 24%) ;
    //  2) largeur — on réduit la fiche pour qu'elle tienne dans la zone
    //     visible (les fiches larges comme NEET, 1488px, ne sont plus coupées
    //     ni ne demandent de défilement horizontal).
    function fitAll() {
      // la fiche commence toujours SOUS la barre d'outils (dont la hauteur
      // varie selon la largeur — le texte peut passer sur plusieurs lignes).
      document.body.style.paddingTop = tb.offsetHeight + 'px';
      root.style.zoom = '';  // mesurer en taille naturelle
      if (root.scrollHeight > root.clientHeight + 1) root.style.height = root.scrollHeight + 'px';
      var natW = root.offsetWidth;
      var avail = (root.parentElement ? root.parentElement.clientWidth : window.innerWidth) - 8;
      if (avail > 60 && natW > 0) root.style.zoom = Math.min(1, avail / natW);
    }
    fitAll();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitAll);
    setTimeout(fitAll, 400);
    window.addEventListener('resize', fitAll);

    // À l'impression : échelle A4 (8 mm de marge) d'après la taille réelle.
    window.addEventListener('beforeprint', function () {
      root.style.zoom = '';
      var w = Math.max(root.scrollWidth, root.offsetWidth);
      var h = Math.max(root.scrollHeight, root.offsetHeight);
      root.style.zoom = Math.min(734 / w, 1063 / h, 1);
    });
    window.addEventListener('afterprint', fitAll);
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
__EDITOR_CSS__
</style>
</head>
<body>
  <div class="dc-stage">
    __FICHE__
  </div>
  __VENDOR__
  <script>__EDITOR_JS__</script>
</body>
</html>
"""


def _wrap(fiche: str, out_path, title, lang):
    # Le cadre garde son overflow:hidden d'origine (découpe les décorations
    # débordantes) ; l'éditeur agrandit le cadre côté navigateur seulement si
    # le vrai contenu dépasse (voir fitHeight dans EDITOR_JS).
    page = (_PAGE.replace("__LANG__", lang).replace("__DIR__", "rtl" if lang == "ar" else "ltr")
            .replace("__TITLE__", title).replace("__FONTS__", FONTS)
            .replace("__EDITOR_CSS__", EDITOR_CSS).replace("__VENDOR__", VENDOR).replace("__EDITOR_JS__", EDITOR_JS)
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
