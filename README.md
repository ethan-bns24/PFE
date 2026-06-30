# Mémoire de PFE — Ethan Binisti

Mémoire de projet de fin d'études (ESILV, majeure Modélisation & Numérique),
alternance R&D chez Souchier-Boullet.

## Structure

- `memoire.tex` : fichier principal (préambule, styles, ordre des chapitres)
- `sections/` : page de garde, remerciements, glossaire, résumé, abstract, bibliographie, annexes
- `chapters/` : chapitres principaux du mémoire
- `approfondissement_scientifique/` : prototype exécutable du chapitre scientifique
  (contrat d'interface JSON, validateur Python, suite de tests, script de liaison Inventor)

## Compilation

```bash
pdflatex memoire.tex
pdflatex memoire.tex   # seconde passe pour les références croisées et le sommaire
```

Packages requis (au-delà d'une installation TeX Live basique) : `titlesec`,
`fancyhdr`, `listings`, `caption`, `float`, `helvetic`, `pgf` (TikZ).
Ils s'installent avec `tlmgr install <package>`.

## Prototype du chapitre scientifique

```bash
cd approfondissement_scientifique
python3 run_test_suite.py
```

Voir `approfondissement_scientifique/README.md` pour le détail.
