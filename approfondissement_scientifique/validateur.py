#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validateur de contrat d'interface SQL -- CAO.

Ce script compare un contrat d'interface (JSON) avec :
  - un export du schema SQL (passe SQL) ;
  - un export des parametres du modele Inventor (passe CAO) ;
  - une configuration utilisateur (passe configuration).

Chaque anomalie detectee est rattachee a une classe de rupture :
  R1 : source SQL ou cible CAO absente (rupture nominale)
  R2 : type incompatible (rupture de type)
  R3 : domaine de valeur incoherent (rupture de domaine)
  R4 : parametre obligatoire absent (rupture de completude)

Le validateur ne se contente pas de bloquer : il produit un rapport JSON
lisible indiquant, pour chaque erreur, le parametre concerne, la classe
de rupture et un message de diagnostic.

Usage :
    python validateur.py --contrat contrat/contrat_coveraccess.json \
        --schema-sql data/export_schema_sql.json \
        --parametres-cao data/export_parametres_cao.json \
        --configuration data/sample_configuration.json \
        --sortie rapports/rapport.json
"""

import argparse
import json
import sys
from pathlib import Path

# Correspondance entre les types declares cote SQL Server et les types
# canoniques du contrat. Le bit SQL Server est le booleen usuel.
TYPES_SQL = {
    "int": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "bit": "boolean",
    "decimal": "number",
    "float": "number",
    "nvarchar": "string",
    "varchar": "string",
    "char": "string",
}

# Correspondance entre les types exposes par l'export Inventor et les
# types canoniques du contrat.
TYPES_CAO = {
    "integer": "integer",
    "numeric": "number",
    "text": "string",
    "boolean": "boolean",
}

TYPES_PYTHON = {
    "integer": int,
    "number": (int, float),
    "string": str,
    "boolean": bool,
}


def charger_json(chemin):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def erreur(parametre, classe, passe, message):
    return {
        "parametre": parametre,
        "classe": classe,
        "passe": passe,
        "message": message,
    }


def valider_coherence_contrat(contrat):
    """Verifications internes du contrat (dependances declarees, version)."""
    erreurs = []
    ids = {p["id"] for p in contrat["parametres"]}
    for p in contrat["parametres"]:
        for dep in p.get("dependances", []):
            if dep not in ids:
                erreurs.append(erreur(
                    p["id"], "R1", "contrat",
                    f"La dependance declaree '{dep}' ne correspond a aucun parametre du contrat."))
    version = contrat.get("version_contrat", "")
    if len(version.split(".")) != 3:
        erreurs.append(erreur(
            "(contrat)", "R2", "contrat",
            f"Le champ version_contrat '{version}' ne respecte pas le format majeur.mineur.patch."))
    return erreurs


def passe_sql(contrat, schema_sql):
    """Verifie que chaque source SQL declaree existe et porte le bon type."""
    erreurs = []
    tables = schema_sql.get("tables", {})
    for p in contrat["parametres"]:
        table, _, champ = p["source_sql"].partition(".")
        colonnes = tables.get(table, {})
        if champ not in colonnes:
            erreurs.append(erreur(
                p["id"], "R1", "sql",
                f"Le champ source '{p['source_sql']}' est introuvable dans le schema SQL exporte."))
            continue
        type_sql = colonnes[champ].get("type", "")
        type_canonique = TYPES_SQL.get(type_sql)
        if type_canonique != p["type"]:
            erreurs.append(erreur(
                p["id"], "R2", "sql",
                f"Le champ '{p['source_sql']}' est de type SQL '{type_sql}' "
                f"alors que le contrat attend '{p['type']}'."))
    return erreurs


def passe_cao(contrat, parametres_cao):
    """Verifie l'existence des cibles Inventor, leur type et leur domaine."""
    erreurs = []
    params = parametres_cao.get("parametres", {})
    for p in contrat["parametres"]:
        cible = p["cible_cao"]
        if cible not in params:
            erreurs.append(erreur(
                p["id"], "R1", "cao",
                f"Le parametre cible '{cible}' est absent du modele Inventor exporte."))
            continue
        decl = params[cible]
        type_cao = TYPES_CAO.get(decl.get("type", ""))
        if type_cao != p["type"]:
            erreurs.append(erreur(
                p["id"], "R2", "cao",
                f"Le parametre Inventor '{cible}' est de type '{decl.get('type')}' "
                f"alors que le contrat attend '{p['type']}'."))
        domaine = p.get("domaine", {})
        if "min" in domaine and "max" in domaine and "min" in decl and "max" in decl:
            if decl["min"] > domaine["min"] or decl["max"] < domaine["max"]:
                erreurs.append(erreur(
                    p["id"], "R3", "cao",
                    f"Le domaine du contrat [{domaine['min']}, {domaine['max']}] n'est pas "
                    f"entierement couvert par le modele Inventor "
                    f"[{decl['min']}, {decl['max']}] : risque de clampage silencieux."))
    return erreurs


def passe_configuration(contrat, configuration):
    """Verifie la configuration utilisateur : presence, types et domaines."""
    erreurs = []
    valeurs = configuration.get("valeurs", {})
    for p in contrat["parametres"]:
        pid = p["id"]
        if pid not in valeurs:
            if p.get("obligatoire", False):
                erreurs.append(erreur(
                    pid, "R4", "configuration",
                    f"Le parametre obligatoire '{pid}' est absent de la configuration transmise."))
            continue
        valeur = valeurs[pid]
        attendu = TYPES_PYTHON[p["type"]]
        # En Python, bool est un sous-type de int : il faut le traiter a part
        # pour ne pas accepter true/false comme valeur entiere (et inversement).
        if p["type"] == "boolean":
            type_ok = isinstance(valeur, bool)
        else:
            type_ok = isinstance(valeur, attendu) and not isinstance(valeur, bool)
        if not type_ok:
            erreurs.append(erreur(
                pid, "R2", "configuration",
                f"La valeur '{valeur}' ({type(valeur).__name__}) ne correspond pas "
                f"au type attendu '{p['type']}'."))
            continue
        domaine = p.get("domaine", {})
        if "min" in domaine and valeur < domaine["min"] or \
           "max" in domaine and valeur > domaine["max"]:
            erreurs.append(erreur(
                pid, "R3", "configuration",
                f"La valeur {valeur} sort du domaine admis "
                f"[{domaine.get('min')}, {domaine.get('max')}]."))
        elif "valeurs" in domaine and valeur not in domaine["valeurs"]:
            erreurs.append(erreur(
                pid, "R3", "configuration",
                f"La valeur '{valeur}' ne fait pas partie des valeurs autorisees : "
                f"{domaine['valeurs']}."))
    return erreurs


def valider(contrat, schema_sql=None, parametres_cao=None, configuration=None):
    """Execute les passes disponibles et construit le rapport complet."""
    erreurs = valider_coherence_contrat(contrat)
    if schema_sql is not None:
        erreurs += passe_sql(contrat, schema_sql)
    if parametres_cao is not None:
        erreurs += passe_cao(contrat, parametres_cao)
    if configuration is not None:
        erreurs += passe_configuration(contrat, configuration)

    classes = {}
    for e in erreurs:
        classes[e["classe"]] = classes.get(e["classe"], 0) + 1

    return {
        "ok": not erreurs,
        "contrat": {
            "gamme": contrat.get("gamme"),
            "version_contrat": contrat.get("version_contrat"),
        },
        "resume": {
            "nb_parametres": len(contrat["parametres"]),
            "nb_erreurs": len(erreurs),
            "classes_detectees": classes,
        },
        "erreurs": erreurs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validateur de contrat d'interface SQL -- CAO")
    parser.add_argument("--contrat", required=True)
    parser.add_argument("--schema-sql")
    parser.add_argument("--parametres-cao")
    parser.add_argument("--configuration")
    parser.add_argument("--sortie", help="Chemin du rapport JSON a generer")
    args = parser.parse_args(argv)

    contrat = charger_json(args.contrat)
    schema_sql = charger_json(args.schema_sql) if args.schema_sql else None
    parametres_cao = charger_json(args.parametres_cao) if args.parametres_cao else None
    configuration = charger_json(args.configuration) if args.configuration else None

    rapport = valider(contrat, schema_sql, parametres_cao, configuration)

    if args.sortie:
        Path(args.sortie).parent.mkdir(parents=True, exist_ok=True)
        with open(args.sortie, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)

    statut = "VALIDE" if rapport["ok"] else "INVALIDE"
    print(f"[{statut}] {rapport['resume']['nb_erreurs']} erreur(s) detectee(s) "
          f"sur {rapport['resume']['nb_parametres']} parametres.")
    for e in rapport["erreurs"]:
        print(f"  - [{e['classe']}] ({e['passe']}) {e['parametre']} : {e['message']}")

    return 0 if rapport["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
