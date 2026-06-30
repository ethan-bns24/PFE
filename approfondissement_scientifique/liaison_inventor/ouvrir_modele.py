#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liaison configurateur SQL -- Autodesk Inventor avec validation prealable.

Ce script est la version "branchee" du prototype : au lieu de comparer le
contrat a un export simule des parametres CAO, il interroge directement le
modele Inventor via l'API COM, puis applique la configuration validee.

Deroulement :
  1. chargement du contrat d'interface et de la configuration utilisateur ;
  2. validation de la configuration contre le contrat (R2, R3, R4) ;
  3. ouverture du document Inventor et introspection de ses parametres ;
  4. validation des cibles CAO reelles contre le contrat (R1, R2) ;
  5. application des valeurs, mise a jour du document et controle
     post-execution (valeur demandee vs valeur reellement appliquee).

Prerequis (poste Windows avec Inventor installe) :
    pip install pywin32

Usage :
    python ouvrir_modele.py --contrat ..\\contrat\\contrat_coveraccess.json ^
        --configuration configuration.json ^
        --modele "C:\\Vault\\COVERACCESS\\COVERACCESS_V3.iam"
"""

import argparse
import json
import sys
from pathlib import Path

# Le validateur du prototype est reutilise tel quel : seules les donnees
# d'entree changent (introspection reelle au lieu d'un export simule).
sys.path.insert(0, str(Path(__file__).parent.parent))
from validateur import charger_json, passe_configuration, passe_cao  # noqa: E402

try:
    import win32com.client
except ImportError:
    win32com = None

# Unites internes d'Inventor : les longueurs sont stockees en cm dans le
# modele, alors que le contrat et la base SQL travaillent en mm.
MM_VERS_CM = 0.1


def connecter_inventor():
    if win32com is None:
        raise RuntimeError(
            "pywin32 n'est pas installe ou ce poste n'est pas sous Windows. "
            "Ce script doit etre execute sur un poste disposant d'Autodesk Inventor.")
    try:
        app = win32com.client.GetActiveObject("Inventor.Application")
    except Exception:
        app = win32com.client.Dispatch("Inventor.Application")
        app.Visible = True
    return app


def introspection_parametres(document):
    """Construit, depuis le document ouvert, la meme structure que les
    exports simules du prototype (data/export_parametres_cao.json)."""
    parametres = {}
    try:
        user_params = document.ComponentDefinition.Parameters.UserParameters
    except Exception:
        # Les assemblages exposent les parametres au meme endroit, mais on
        # reste defensif : un document sans parametres utilisateur est un
        # cas de rupture R1 generalise qu'il faut remonter clairement.
        return parametres
    for param in user_params:
        unite = str(param.Units).lower()
        if unite in ("mm", "cm", "m"):
            type_canonique = "integer"
        elif unite in ("ul",):  # "unitless" : booleen ou nombre pur
            type_canonique = "boolean" if isinstance(param.Value, bool) else "numeric"
        else:
            type_canonique = "text"
        parametres[param.Name] = {"type": type_canonique, "unite": unite}
    return parametres


def appliquer_configuration(document, contrat, configuration):
    """Applique les valeurs validees et verifie la valeur reellement prise
    en compte par le modele (controle post-execution)."""
    ecarts = []
    user_params = document.ComponentDefinition.Parameters.UserParameters
    valeurs = configuration["valeurs"]
    for p in contrat["parametres"]:
        if p["id"] not in valeurs:
            continue
        valeur = valeurs[p["id"]]
        param = user_params.Item(p["cible_cao"])
        if p.get("unite") == "mm":
            param.Value = valeur * MM_VERS_CM
            attendu = valeur * MM_VERS_CM
        else:
            param.Value = valeur
            attendu = valeur
        if param.Value != attendu:
            ecarts.append({
                "parametre": p["id"],
                "cible_cao": p["cible_cao"],
                "valeur_demandee": attendu,
                "valeur_appliquee": param.Value,
            })
    document.Update()
    return ecarts


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ouverture parametree d'un modele Inventor avec validation de contrat")
    parser.add_argument("--contrat", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--modele", required=True, help="Chemin du fichier .ipt ou .iam")
    args = parser.parse_args(argv)

    contrat = charger_json(args.contrat)
    configuration = charger_json(args.configuration)

    # Passe configuration : inutile d'ouvrir Inventor si la configuration
    # transmise est deja incoherente avec le contrat.
    erreurs = passe_configuration(contrat, configuration)
    if erreurs:
        print("Configuration rejetee avant ouverture du modele :")
        for e in erreurs:
            print(f"  - [{e['classe']}] {e['parametre']} : {e['message']}")
        return 1

    app = connecter_inventor()
    document = app.Documents.Open(args.modele)

    # Passe CAO sur le modele reel : memes controles que le prototype,
    # mais alimentes par introspection COM au lieu d'un export simule.
    parametres_reels = {"parametres": introspection_parametres(document)}
    erreurs = passe_cao(contrat, parametres_reels)
    if erreurs:
        print("Le modele ouvert n'est pas conforme au contrat d'interface :")
        for e in erreurs:
            print(f"  - [{e['classe']}] {e['parametre']} : {e['message']}")
        print("Aucun parametre n'a ete modifie.")
        return 1

    ecarts = appliquer_configuration(document, contrat, configuration)
    if ecarts:
        print("Attention : ecarts detectes entre valeurs demandees et appliquees")
        for ecart in ecarts:
            print(f"  - {ecart['parametre']} : demande {ecart['valeur_demandee']}, "
                  f"applique {ecart['valeur_appliquee']}")
        return 1

    print(f"Modele '{Path(args.modele).name}' ouvert et parametre avec succes "
          f"(contrat {contrat['gamme']} v{contrat['version_contrat']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
