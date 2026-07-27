"""templates/ — Nouveaux gabarits de fiches (refonte juillet 2026).

Chaque fiche reproduit fidèlement une maquette PDF fournie par le HCP, dans la
charte bordeaux/or (voir theme.py). Le contenu vit dans un `spec` (dict) qui
peut être pré-rempli depuis l'Excel, édité à la main, ou modifié par l'IA ;
le design, lui, reste figé. On réutilise les primitives bas niveau de
`poster_engine` (police, texte RTL, graphes) — seule la palette et la mise en
page changent ici, ce qui laisse l'ancien générateur intact.
"""
