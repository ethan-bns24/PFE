#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import generique des tables d'une gamme depuis un classeur Excel.

Convention observee sur TPS.xlsx (gamme Coveraccess) et reprise pour
toute autre gamme suivant le meme principe :
  - seules les feuilles a onglet vert (couleur de validation/figee) sont
    considerees comme faisant foi ;
  - le prefixe du nom de feuille indique son role :
      Ls_ : liste de valeurs (code -> libelle)
      Tc_ : table de correspondance / compatibilite entre codes
      Tb_ : table de base (modeles, constantes, formules, dimensions)
  - la premiere ligne de chaque feuille est un titre, la deuxieme les
    en-tetes de colonnes, les suivantes les donnees.

Ce module ne sait rien des champs precis d'une gamme donnee : il lit la
structure telle qu'elle est presente dans le classeur.

Usage :
    python3 gamme_excel.py --xlsx chemin.xlsx --sortie data/gammes/nom.json
"""

import argparse
import json
import re
from pathlib import Path

import openpyxl

THEME_VERT = 9


def est_feuille_verte(ws) -> bool:
    """Feuille a onglet vert : couleur de theme 'Accent 6' (verte dans le
    theme Office par defaut), ou repli heuristique sur une couleur RGB
    explicitement verte pour un classeur utilisant un autre theme."""
    couleur = ws.sheet_properties.tabColor
    if couleur is None:
        return False
    if getattr(couleur, "type", None) == "theme":
        return couleur.theme == THEME_VERT
    if getattr(couleur, "type", None) == "rgb" and isinstance(couleur.rgb, str) and len(couleur.rgb) == 8:
        r, g, b = (int(couleur.rgb[i:i + 2], 16) for i in (2, 4, 6))
        return g > r + 20 and g > b + 20
    return False


def _normaliser_nom_feuille(nom: str) -> str:
    return re.sub(r"_+", "_", nom.strip().replace(" ", "_"))


def lire_feuille(ws) -> dict:
    """Certaines feuilles ont une ligne de titre (une seule cellule remplie)
    avant les en-tetes, d'autres demarrent directement sur la ligne
    d'en-tetes (plusieurs cellules remplies) : on detecte le cas plutot que
    de supposer une position fixe."""
    lignes_brutes = [list(row) for row in ws.iter_rows(values_only=True) if any(c is not None for c in row)]
    if not lignes_brutes:
        return {"feuille": ws.title, "titre": ws.title, "colonnes": [], "lignes": [], "notes": []}

    premiere = [c for c in lignes_brutes[0] if c is not None]
    if len(premiere) == 1:
        titre = premiere[0]
        reste = lignes_brutes[1:]
    else:
        titre = ws.title
        reste = lignes_brutes

    entetes = reste[0] if reste else []
    colonnes = [c for c in entetes if c is not None]

    lignes, notes = [], []
    for row in reste[1:]:
        cellules_remplies = [c for c in row if c is not None]
        if len(cellules_remplies) <= 1 and len(colonnes) > 1:
            if cellules_remplies:
                notes.append(str(cellules_remplies[0]))
            continue
        lignes.append({entetes[i]: row[i] for i in range(len(entetes)) if entetes[i] is not None and i < len(row)})

    return {
        "feuille": ws.title,
        "titre": titre,
        "colonnes": colonnes,
        "lignes": lignes,
        "notes": notes,
    }


def charger_gamme_excel(chemin_ou_fichier) -> dict:
    classeur = openpyxl.load_workbook(chemin_ou_fichier, data_only=True)
    feuilles = {}
    for ws in classeur.worksheets:
        if est_feuille_verte(ws):
            feuilles[_normaliser_nom_feuille(ws.title)] = lire_feuille(ws)
    nom_source = getattr(chemin_ou_fichier, "name", None) or str(chemin_ou_fichier)
    return {"source": Path(nom_source).name, "feuilles": feuilles}


def lister_par_prefixe(gamme: dict, prefixe: str) -> dict:
    return {nom: f for nom, f in gamme["feuilles"].items() if nom.startswith(prefixe)}


def feuilles_listes_simples(gamme: dict) -> list:
    """Feuilles Ls_* exploitables comme listes code -> libelle (exactement
    2 colonnes Ce_X / Li_X). Les autres feuilles Ls_ presentes dans le
    classeur (ex. tables de correspondance mal prefixees) sont ignorees
    par cette fonction generique."""
    resultat = []
    for nom, feuille in lister_par_prefixe(gamme, "Ls_").items():
        cols = feuille["colonnes"]
        if len(cols) == 2 and cols[0].startswith("Ce_") and cols[1].startswith("Li_"):
            resultat.append((nom, feuille))
    return resultat


def _trouver_feuille(gamme: dict, nom_normalise: str):
    return gamme["feuilles"].get(nom_normalise)


def verifier_compatibilite(gamme: dict, choix: dict) -> list[dict]:
    """Verifie un jeu de codes choisis (ex. {"Ce_Matiere": "INOX304", ...})
    contre toutes les tables de correspondance Tc_* applicables, plus les
    bornes dimensionnelles du modele si Tb_TPS_Modele est presente."""
    erreurs = []

    for nom, feuille in lister_par_prefixe(gamme, "Tc_").items():
        colonnes = feuille["colonnes"]
        if not colonnes or not all(c in choix for c in colonnes):
            continue
        cle_attendue = tuple(choix[c] for c in colonnes)
        existe = any(tuple(ligne.get(c) for c in colonnes) == cle_attendue for ligne in feuille["lignes"])
        if not existe:
            erreurs.append({
                "table": nom,
                "message": (
                    f"La combinaison {dict(zip(colonnes, cle_attendue))} n'est pas "
                    f"autorisee par la table de correspondance '{nom}'."
                ),
            })

    feuille_modeles = _trouver_feuille(gamme, "Tb_TPS_Modele")
    if feuille_modeles and {"Ce_Modele", "La_PassageLibre", "Ht_PassageLibre"} <= choix.keys():
        ligne_modele = next(
            (l for l in feuille_modeles["lignes"] if l.get("Ce_Modele") == choix["Ce_Modele"]), None
        )
        if ligne_modele is None:
            erreurs.append({
                "table": "Tb_TPS_Modele",
                "message": f"Le modele '{choix['Ce_Modele']}' n'existe pas dans la table des modeles.",
            })
        else:
            largeur, hauteur = choix["La_PassageLibre"], choix["Ht_PassageLibre"]
            la_min, la_max = ligne_modele.get("Co_LPL_Min"), ligne_modele.get("Co_LPL_Max")
            ht_min, ht_max = ligne_modele.get("Co_HPL_Min"), ligne_modele.get("Co_HPL_Max")
            if la_min is not None and la_max is not None and not (la_min <= largeur <= la_max):
                erreurs.append({
                    "table": "Tb_TPS_Modele",
                    "message": (
                        f"Largeur passage libre {largeur} hors bornes du modele "
                        f"'{choix['Ce_Modele']}' [{la_min}, {la_max}]."
                    ),
                })
            if ht_min is not None and ht_max is not None and not (ht_min <= hauteur <= ht_max):
                erreurs.append({
                    "table": "Tb_TPS_Modele",
                    "message": (
                        f"Hauteur passage libre {hauteur} hors bornes du modele "
                        f"'{choix['Ce_Modele']}' [{ht_min}, {ht_max}]."
                    ),
                })

    return erreurs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import des tables de gamme (feuilles vertes) depuis un classeur Excel")
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--sortie", help="Chemin du JSON a generer")
    args = parser.parse_args(argv)

    gamme = charger_gamme_excel(args.xlsx)
    par_prefixe = {p: len(lister_par_prefixe(gamme, p)) for p in ("Ls_", "Tc_", "Tb_")}
    nb_notes = sum(len(f["notes"]) for f in gamme["feuilles"].values())

    print(f"{len(gamme['feuilles'])} feuille(s) verte(s) importee(s) depuis {gamme['source']}")
    print(f"  Ls_ (listes) : {par_prefixe['Ls_']}  Tc_ (correspondances) : {par_prefixe['Tc_']}  "
          f"Tb_ (tables de base) : {par_prefixe['Tb_']}")
    if nb_notes:
        print(f"  {nb_notes} ligne(s) de texte libre ignoree(s) comme notes")

    if args.sortie:
        Path(args.sortie).parent.mkdir(parents=True, exist_ok=True)
        with open(args.sortie, "w", encoding="utf-8") as f:
            json.dump(gamme, f, ensure_ascii=False, indent=2)
        print(f"Ecrit dans {args.sortie}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
