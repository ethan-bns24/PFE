#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Suite de tests du validateur de contrat d'interface.

Quatre scenarios sont executes :
  1. cas nominal : configuration, schema SQL et parametres CAO coherents ;
  2. configuration invalide : 4 anomalies injectees (R2, R3, R4) ;
  3. schema SQL invalide : 2 anomalies injectees (R1, R2) ;
  4. parametres CAO invalides : 3 anomalies injectees (R1, R2, R3).

Chaque scenario produit un rapport JSON dans le dossier rapports/, plus un
rapport de synthese global. Le script renvoie un code de sortie non nul si
les resultats obtenus ne correspondent pas aux resultats attendus.
"""

import json
import sys
from pathlib import Path

from validateur import charger_json, valider

RACINE = Path(__file__).parent
DATA = RACINE / "data"
RAPPORTS = RACINE / "rapports"

SCENARIOS = [
    {
        "nom": "cas_nominal",
        "description": "Configuration, schema SQL et parametres CAO coherents avec le contrat.",
        "schema_sql": "export_schema_sql.json",
        "parametres_cao": "export_parametres_cao.json",
        "configuration": "sample_configuration.json",
        "attendu": {"ok": True, "nb_erreurs": 0, "classes": {}},
    },
    {
        "nom": "configuration_invalide",
        "description": "Largeur hors domaine, hauteur absente, classement feu inconnu, booleen en chaine.",
        "schema_sql": "export_schema_sql.json",
        "parametres_cao": "export_parametres_cao.json",
        "configuration": "sample_configuration_broken.json",
        "attendu": {"ok": False, "nb_erreurs": 4, "classes": {"R2": 1, "R3": 2, "R4": 1}},
    },
    {
        "nom": "schema_sql_invalide",
        "description": "Champ source renomme et changement de type non synchronise cote SQL.",
        "schema_sql": "export_schema_sql_invalide.json",
        "parametres_cao": "export_parametres_cao.json",
        "configuration": "sample_configuration.json",
        "attendu": {"ok": False, "nb_erreurs": 2, "classes": {"R1": 1, "R2": 1}},
    },
    {
        "nom": "parametres_cao_invalides",
        "description": "Cible renommee, type modifie et domaine retreci cote modele Inventor.",
        "schema_sql": "export_schema_sql.json",
        "parametres_cao": "export_parametres_cao_invalide.json",
        "configuration": "sample_configuration.json",
        "attendu": {"ok": False, "nb_erreurs": 3, "classes": {"R1": 1, "R2": 1, "R3": 1}},
    },
]


def executer_scenario(contrat, scenario):
    rapport = valider(
        contrat,
        schema_sql=charger_json(DATA / scenario["schema_sql"]),
        parametres_cao=charger_json(DATA / scenario["parametres_cao"]),
        configuration=charger_json(DATA / scenario["configuration"]),
    )
    chemin = RAPPORTS / f"rapport_{scenario['nom']}.json"
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    attendu = scenario["attendu"]
    conforme = (
        rapport["ok"] == attendu["ok"]
        and rapport["resume"]["nb_erreurs"] == attendu["nb_erreurs"]
        and rapport["resume"]["classes_detectees"] == attendu["classes"]
    )
    return rapport, conforme


def main():
    RAPPORTS.mkdir(exist_ok=True)
    contrat = charger_json(RACINE / "contrat" / "contrat_coveraccess.json")

    synthese = {
        "contrat": {
            "gamme": contrat["gamme"],
            "version_contrat": contrat["version_contrat"],
        },
        "scenarios": [],
        "total_erreurs_detectees": 0,
        "total_par_classe": {},
        "suite_conforme": True,
    }

    print(f"Suite de tests -- contrat {contrat['gamme']} v{contrat['version_contrat']}")
    print("-" * 72)

    for scenario in SCENARIOS:
        rapport, conforme = executer_scenario(contrat, scenario)
        resume = rapport["resume"]
        synthese["scenarios"].append({
            "nom": scenario["nom"],
            "description": scenario["description"],
            "ok": rapport["ok"],
            "nb_erreurs": resume["nb_erreurs"],
            "classes_detectees": resume["classes_detectees"],
            "conforme_a_l_attendu": conforme,
        })
        synthese["total_erreurs_detectees"] += resume["nb_erreurs"]
        for classe, n in resume["classes_detectees"].items():
            synthese["total_par_classe"][classe] = synthese["total_par_classe"].get(classe, 0) + n
        if not conforme:
            synthese["suite_conforme"] = False

        statut = "VALIDE" if rapport["ok"] else "INVALIDE"
        verdict = "OK" if conforme else "ECHEC (resultat inattendu)"
        print(f"{scenario['nom']:<28} {statut:<9} {resume['nb_erreurs']} erreur(s)  "
              f"{resume['classes_detectees'] or ''}  -> {verdict}")

    print("-" * 72)
    print(f"Total : {synthese['total_erreurs_detectees']} erreurs detectees, "
          f"reparties par classe : {synthese['total_par_classe']}")
    print(f"Suite conforme aux resultats attendus : {synthese['suite_conforme']}")

    with open(RAPPORTS / "synthese_tests.json", "w", encoding="utf-8") as f:
        json.dump(synthese, f, ensure_ascii=False, indent=2)

    return 0 if synthese["suite_conforme"] else 1


if __name__ == "__main__":
    sys.exit(main())
