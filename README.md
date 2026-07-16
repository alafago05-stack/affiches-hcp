# Générateur d'affiches HCP — Guide d'installation

Ce dossier contient une application web (Streamlit) qui génère des affiches
infographiques HCP multilingues (FR / AR / EN) à partir de fichiers Excel
d'indicateurs du marché du travail, sans avoir besoin de toucher au code.

Palette et structure suivent la maquette HTML de référence (« Souss-Massa
standalone », juillet 2026) : thème clair crème / marine / vert olive,
police **IBM Plex Sans Arabic** (latin + arabe), en-tête avec pastille,
introduction + lexique côte à côte, **répartition de la population en arbre**
(carte totale avec anneau → force de travail / hors force → actifs occupés /
chômeurs), **3 taux essentiels en anneaux dans une carte titrée** (sous
l'arbre), puis une zone propre à chaque type d'affiche (indicateurs — dont le
taux de salariat —, courbes ou barres comparatives) et les points saillants.

⚠️ L'arbre est volontairement simplifié par rapport à la maquette HTML : les
nœuds « main-d'œuvre potentielle », « chômeurs au sens étroit » et
« sous-emploi lié aux heures » utilisent des concepts absents de l'export
Excel « ENE-Indicateurs désagrégés » actuel — on ne les affiche pas plutôt
que d'inventer des chiffres (choix validé). Si un export plus complet devient
disponible, ces nœuds pourront être ajoutés dans `build_distribution` /
`render_fixed_header_zone` (poster_engine.py).

## Structure du projet

```
affiches_package/
├── app.py                 # Interface Streamlit (point d'entrée : streamlit run app.py)
├── poster_engine.py        # Briques visuelles + builders de spec partagés (palette, cartes,
│                            # donuts, courbes, texte FR/AR/EN, zone fixe, points saillants)
├── support.py              # Espace support : chatbot de signalement + stockage SQLite + suivi
├── support/tickets.db      # Base des signalements (créée automatiquement, non versionnée)
├── parsers/
│   └── annual.py            # Parseur Excel (ENE annuel ET trimestriel — même format)
├── posters/
│   ├── standard.py          # Type 1 : affiche standard (1 année, 1 région)
│   ├── year_compare.py      # Type 2 : comparatif entre années (courbes de tendance)
│   ├── region_compare.py    # Type 3 : comparatif entre 2 régions (barres)
│   └── quarter_compare.py   # Type 4 : comparatif entre trimestres (barres, 2 à 4 fichiers)
├── generate_affiche.py      # Script CLI historique (ANCIEN design — l'app web fait foi)
├── fonts/
│   ├── IBMPlexSansArabic-Regular.ttf   # police du nouveau design (latin + arabe)
│   ├── IBMPlexSansArabic-Bold.ttf
│   ├── DejaVuSans.ttf                  # replis si les IBM Plex manquent
│   ├── DejaVuSans-Bold.ttf
│   ├── NotoSansArabic-Regular.ttf
│   └── NotoSansArabic-Bold.ttf
├── hcp_logo.png
└── requirements.txt
```

⚠️ Important : ne déplace pas ces fichiers individuellement — le dossier
`fonts/` et `hcp_logo.png` doivent toujours rester à côté de `poster_engine.py`
et `app.py`, quel que soit l'endroit d'où tu lances l'application.

## 1. Installer Python

- **Windows** : télécharge Python sur https://python.org/downloads (coche
  "Add Python to PATH" pendant l'installation), puis vérifie dans une invite
  de commande (`cmd`) :
  ```
  python --version
  ```
- **Mac** : Python est souvent déjà présent. Vérifie dans le Terminal :
  ```
  python3 --version
  ```
  Sinon installe-le via https://python.org/downloads ou `brew install python`.
- **Linux** : `sudo apt install python3 python3-pip` (Debian/Ubuntu).

## 2. Installer les librairies nécessaires

Ouvre un terminal (ou l'invite de commande Windows) dans ce dossier
(`affiches_package`), puis :

```bash
pip install -r requirements.txt
```

(sur Mac/Linux, utilise `pip3` si `pip` n'est pas reconnu)

## 3. Lancer l'application web

Toujours dans ce dossier, depuis le terminal :

```bash
streamlit run app.py
```

Une page s'ouvre automatiquement dans le navigateur (sinon, l'URL affichée
dans le terminal, en général `http://localhost:8501`). Depuis cette page :

1. Choisis le type d'affiche (1 à 4).
2. Choisis la langue (français / arabe / anglais) — ou active le bouton
   **🌍 Générer les 3 langues d'un coup** pour obtenir directement un ZIP
   contenant les trois versions (FR + AR + EN).
3. Importe le ou les fichiers Excel demandés et renseigne les paramètres
   (année, région, etc.).
4. Vérifie les chiffres dans l'**📊 Aperçu des données** :
   - cartes chiffrées des trois taux clés (TA / TE / TC) de l'année choisie,
     avec l'écart en points depuis l'année comparée (Type 2) ;
   - une **courbe d'évolution interactive** (survol des points pour lire les
     valeurs) pour les Types 1 et 2, ou un **graphique à barres comparatif**
     pour le Type 3 ;
   - une **📝 lecture automatique** des données : deux à quatre phrases
     factuelles (niveaux, évolution, années extrêmes) prêtes à recopier dans
     les points saillants de l'affiche ;
   - un bouton **⬇️ Exporter les indicateurs (CSV)** pour récupérer les
     chiffres propres (ouvrable directement dans Excel).
5. Clique sur **Générer l'affiche**.
6. L'affiche s'affiche à l'écran — en **onglets FR / AR / EN** si tu as
   généré les trois langues. Boutons de téléchargement :
   - **⬇️ PNG** : l'affiche dans la langue choisie ;
   - **🖨️ PDF** : la même affiche prête à imprimer (aucune dépendance
     supplémentaire, conversion Pillow) ;
   - **📦 ZIP (3 langues)** et **🖨️ PDF (3 pages)** : quand la génération
     multilingue est activée — le PDF contient une page par langue.

Les **8 dernières affiches générées** restent disponibles en bas de page
(🕘 historique de session, avec re-téléchargement) tant que l'onglet du
navigateur est ouvert — pratique pour comparer plusieurs années ou régions.
Le Type 4 dispose aussi d'un **aperçu comparatif des trimestres** (barres
groupées par indicateur) dès que deux fichiers sont déposés.

Un mode d'emploi résumé est toujours visible dans la barre latérale gauche
de l'application.

### Espace support (chatbot de signalement)

Un menu **Navigation** en haut de la barre latérale permet de passer du
**🎨 Générateur** au **💬 Support**. La page Support contient :

- un **assistant (chatbot)** qui guide l'utilisateur en 6 questions courtes
  — type de sujet (bug / données / affichage / suggestion / autre), titre,
  description, emplacement dans l'app, gravité, contact facultatif — puis
  affiche un récapitulatif et enregistre le signalement sous une référence
  (`SUP-0001`, `SUP-0002`…). C'est un chatbot « à base de règles » : aucune
  clé d'API, il fonctionne hors ligne et produit des signalements structurés.
- un **espace de suivi (administration)**, dépliable en bas de page :
  statistiques (nouveaux / en cours / résolus), tableau de tous les
  signalements, changement de statut, et **export CSV / JSON** pour préparer
  les prochaines mises à jour.

Le stockage se fait dans une base **SQLite** (`support/tickets.db`, créée
automatiquement) : un seul fichier requêtable, indexé sur le statut et la
date — efficace même après des centaines de signalements. La logique vit dans
`support.py` ; `app.py` ne fait que l'appeler. Pour restreindre l'accès de
l'espace admin, on pourra plus tard ajouter une authentification devant
`support._render_admin`.

### Identité visuelle

L'interface reprend la palette et les codes des affiches (crème #F7F5EC,
marine #16323F, vert olive #A3B520, or #E8A13C) : bannière héro avec pastille
et logo, étapes numérotées comme les sections des affiches, cartes chiffrées
et barre latérale marine. Les graphiques d'aperçu (Altair) utilisent les
mêmes couleurs d'indicateurs que les courbes des affiches — l'aperçu et
l'affiche racontent visuellement la même histoire. Le thème est appliqué à la
fois par `.streamlit/config.toml` et par du CSS dans `app.py`.

### Les 4 types d'affiche

| Type | Description | Entrées |
|---|---|---|
| 1 — Standard | Une année, une région | 1 fichier Excel + 1 année |
| 2 — Comparatif années | Les trois taux TA/TE/TC **superposés dans un seul graphe** (une courbe par indicateur, avec légende) sur toute la plage entre 2 années | 1 fichier Excel + 2 années |
| 3 — Comparatif régions | Compare 2 régions (2 fichiers) pour une même année | 2 fichiers Excel + 1 année commune |
| 4 — Comparatif trimestres | Compare 2 à 4 trimestres (1 fichier Excel par trimestre) | 1 à 4 fichiers Excel + 1 feuille/année commune |

⚠️ Le Type 4 suppose que chaque fichier Excel trimestriel suit le même
format de bloc que les classeurs annuels "ENE-Indicateurs désagrégés"
(même parseur, `parsers/annual.py`). Cette hypothèse vient du script de
référence et n'a pas encore été vérifiée contre un vrai export trimestriel
du HCP — à confirmer avec un fichier réel dès que possible.

## 4. Vérifier le rendu de l'arabe (RTL)

Le script utilise le moteur de rendu **Raqm** de Pillow pour lier
correctement les lettres arabes. Les versions récentes de Pillow (>= 9.2)
l'incluent nativement sur Windows, Mac et Linux — l'installation à l'étape 2
suffit normalement. Si le texte arabe s'affiche mal (lettres non liées),
mets Pillow à jour :

```bash
pip install --upgrade pillow
```

Si Raqm n'est vraiment pas disponible, l'application bascule automatiquement
sur `arabic-reshaper` + `python-bidi` (déjà dans `requirements.txt`), avec un
repli par police mixte pour les caractères absents de la police arabe
(`%`, `/`, tiret cadratin, lettres latines) — géré automatiquement dans
`poster_engine.py`, rien à faire de ton côté.

## 5. Utiliser encore le script en ligne de commande (optionnel)

`generate_affiche.py` reste utilisable tel quel, indépendamment de
l'application web, avec les 4 modes :

```bash
# Standard
python generate_affiche.py "ENE-Indicateurs.xlsx" --sheet 2025 --demo --lang fr --output affiche_fr.png

# Comparatif années
python generate_affiche.py "ENE-Indicateurs.xlsx" --mode year_compare --sheet 2022 --sheet-b 2025 --lang fr --output out.png

# Comparatif régions
python generate_affiche.py regionA.xlsx --mode region_compare --excel-b regionB.xlsx --region-a "Souss-Massa" --region-b "Casablanca-Settat" --year 2025 --lang fr --output out.png

# Comparatif trimestres
python generate_affiche.py t1.xlsx --mode quarter_compare --sheet 2025 --q2 t2.xlsx --q3 t3.xlsx --year 2025 --lang fr --output out.png
```

## 6. Mettre l'application en ligne (Streamlit Community Cloud)

⚠️ **Vercel ne peut pas héberger cette application.** Vercel exécute des
fonctions *serverless* (courtes, sans état), alors que Streamlit est un
*serveur permanent* qui garde une connexion WebSocket par utilisateur (c'est
ce qui fait vivre `session_state`, les uploads et le ré-affichage à chaque
clic). Les deux modèles sont incompatibles. On utilise donc **Streamlit
Community Cloud**, gratuit et conçu pour ça.

Ce dossier est déjà un dépôt git prêt à être publié (`main`), avec les
secrets, la base locale et les fichiers Excel exclus via `.gitignore`.

### Étape A — créer la base des signalements (Postgres)

Le disque de Streamlit Cloud est **éphémère** : sans base externe, les
signalements du support disparaîtraient à chaque redémarrage. Crée une base
Postgres gratuite chez **[Supabase](https://supabase.com)** ou
**[Neon](https://neon.tech)**, puis récupère l'URL de connexion :

- Supabase : *Project Settings > Database > Connection string > URI*
- Neon : *Dashboard > Connection Details > Connection string*

Elle ressemble à `postgresql://user:motdepasse@hote:5432/base?sslmode=require`.
La table est créée automatiquement au premier signalement — rien à faire de
plus. Sans cette étape l'app fonctionne quand même, mais en mode SQLite
éphémère (un avertissement s'affiche dans l'espace de suivi).

### Étape B — publier le code sur GitHub

Crée un dépôt vide sur GitHub (sans README ni .gitignore), puis :

```bash
cd affiches_generator/affiches_package
git remote add origin https://github.com/TON_COMPTE/TON_DEPOT.git
git push -u origin main
```

Le dépôt peut être **privé** : Streamlit Cloud sait déployer depuis un dépôt
privé après autorisation GitHub. Aucun secret ni donnée HCP n'est versionné.

### Étape C — déployer

1. Va sur **[share.streamlit.io](https://share.streamlit.io)** et connecte-toi
   avec ton compte GitHub.
2. **Create app** → choisis ton dépôt, branche `main`, fichier principal
   **`app.py`**.
3. Dans **Advanced settings** → **Python version**, choisis **3.12** ou
   **3.13** (le code utilise une syntaxe qui demande au minimum Python 3.10).
4. Toujours dans **Advanced settings** → **Secrets**, colle :

   ```toml
   [postgres]
   url = "postgresql://user:motdepasse@hote:5432/base?sslmode=require"
   ```

5. **Deploy**. Le premier build prend quelques minutes (installation des
   dépendances). Ensuite, chaque `git push` sur `main` redéploie tout seul.

### Après le déploiement

- L'app est accessible à tous ceux qui ont le lien. Si elle doit rester
  interne au HCP, regarde dans **Settings > Sharing** pour restreindre
  l'accès à une liste d'adresses e-mail.
- Vérifie dans **💬 Support > Espace de suivi** que le stockage affiche bien
  « **Postgres (persistant)** » — si tu vois « SQLite local », le secret n'a
  pas été pris en compte.
- Les signalements se consultent depuis l'espace de suivi (statuts, export
  CSV/JSON), et survivent désormais aux redéploiements.

## En cas d'erreur

- `ModuleNotFoundError` → refais `pip install -r requirements.txt`
- `FileNotFoundError` sur une police → vérifie que le dossier `fonts/` est
  bien à côté de `app.py` / `poster_engine.py`
- Le texte arabe ne s'affiche pas correctement → mets Pillow à jour
  (`pip install --upgrade pillow`)
- Un message d'erreur explicite apparaît dans l'application (au lieu d'un
  plantage) si le fichier Excel importé n'a pas le format attendu, ou si une
  feuille/tableau/indicateur est introuvable.

### Tolérance aux fichiers Excel « désordonnés »

Le parseur (`parsers/annual.py`) accepte les variantes courantes des exports
ENE sans intervention :

- lignes ou colonnes vides insérées en haut / à gauche de la feuille ;
- espaces parasites (y compris insécables) dans les titres et libellés ;
- apostrophes typographiques (`'`) à la place des apostrophes droites ;
- nombres enregistrés comme texte (`"41,3"` ou `"41.3"`) ;
- casse différente dans les libellés (`ensemble` / `Ensemble`).

Dès qu'un fichier est importé et qu'une année est choisie, l'application
**valide les données avant génération** (`validate_blocks`) : si un tableau,
une ligne ou une valeur nécessaire à l'affiche manque (taux d'activité /
d'emploi / de chômage, sous-emploi, lignes « Féminin », population en âge de
travailler), la liste exacte de ce qui manque s'affiche et le bouton
**Générer** est désactivé. Un fichier sans aucune structure ENE reconnaissable
est signalé comme tel, et un fichier corrompu ou illisible produit un message
clair plutôt qu'un traceback.

## Étendre l'application

- **Nouvelles sections visuelles** : ajoute-les dans `poster_engine.py`, soit
  dans `render_fixed_header_zone` (si la section doit être identique pour
  les 4 types), soit dans l'une des zones flexibles
  (`render_flexible_standard` / `render_flexible_trend` /
  `render_flexible_compare`) selon le(s) type(s) concerné(s).
- **Contenu démo/traductions** : `DEMO_I18N` et `COMPARE_I18N` dans
  `poster_engine.py` centralisent tout le texte partagé (pastille, lexique,
  répartition, points saillants) ; les textes propres à chaque type
  (titre/sous-titre/intro) vivent dans `posters/*.py`.
