# Prototype : contrat d'interface SQL -- CAO

Ce dossier contient le prototype présenté dans le chapitre d'approfondissement
scientifique du mémoire. Il matérialise la démarche de sécurisation de la
liaison entre le configurateur SQL et Autodesk Inventor par un contrat
d'interface formel, versionné et validable automatiquement.

## Contenu

```
approfondissement_scientifique/
├── contrat/
│   └── contrat_coveraccess.json     Contrat d'interface (v1.0.0, 5 paramètres)
├── data/
│   ├── export_schema_sql.json           Export simulé du schéma SQL (nominal)
│   ├── export_schema_sql_invalide.json  Schéma dégradé (ruptures R1, R2)
│   ├── export_parametres_cao.json       Export simulé des paramètres Inventor (nominal)
│   ├── export_parametres_cao_invalide.json  Modèle dégradé (ruptures R1, R2, R3)
│   ├── sample_configuration.json        Configuration utilisateur valide
│   └── sample_configuration_broken.json Configuration dégradée (ruptures R2, R3, R4)
├── liaison_inventor/
│   └── ouvrir_modele.py             Version « branchée » : introspection COM réelle
├── rapports/                        Rapports JSON générés par la suite de tests
├── validateur.py                    Validateur autonome (Python standard, sans dépendance)
└── run_test_suite.py                Suite de tests reproductible (4 scénarios)
```

## Classes de rupture détectées

| Classe | Signification |
|--------|---------------|
| R1 | Source SQL ou cible CAO absente (rupture nominale) |
| R2 | Type incompatible (rupture de type) |
| R3 | Domaine de valeur incohérent (rupture de domaine) |
| R4 | Paramètre obligatoire absent (rupture de complétude) |

## Exécution de la suite de tests

```bash
cd approfondissement_scientifique
python3 run_test_suite.py
```

Résultat attendu : le cas nominal est validé sans erreur, et les 9 anomalies
injectées dans les trois scénarios dégradés sont toutes détectées et
rattachées à leur classe (R1 : 2, R2 : 3, R3 : 3, R4 : 1). Les rapports
détaillés sont écrits dans `rapports/`.

## Validation d'un cas isolé

```bash
python3 validateur.py \
  --contrat contrat/contrat_coveraccess.json \
  --schema-sql data/export_schema_sql.json \
  --parametres-cao data/export_parametres_cao.json \
  --configuration data/sample_configuration_broken.json \
  --sortie rapports/rapport_manuel.json
```

## Version branchée sur Inventor (poste Windows)

Le script `liaison_inventor/ouvrir_modele.py` remplace l'export simulé des
paramètres CAO par une introspection réelle du modèle via l'API COM
d'Inventor. Il enchaîne validation de la configuration, contrôle du modèle
ouvert, application des paramètres puis contrôle post-exécution (valeur
demandée vs valeur réellement appliquée, pour détecter le clampage
silencieux).

```bash
pip install pywin32
python ouvrir_modele.py --contrat ..\contrat\contrat_coveraccess.json ^
    --configuration configuration.json ^
    --modele "C:\Vault\COVERACCESS\COVERACCESS_V3.iam"
```
