# Prototype : contrat d'interface SQL -- CAO

Ce dossier contient le prototype présenté dans le chapitre d'approfondissement
scientifique du mémoire. Il matérialise la démarche de sécurisation de la
liaison entre le configurateur SQL et Autodesk Inventor par un contrat
d'interface formel, versionné et validable automatiquement.

## Contenu

```
approfondissement_scientifique/
├── application_locale/
│   ├── app.py                       Interface web locale (Streamlit) : 2 onglets
│   ├── extraction_pdf.py            Extraction heuristique des valeurs depuis les PDF
│   ├── gamme_excel.py               Import des tables de gamme (feuilles vertes) depuis Excel
│   ├── generer_excel.py             Genere un classeur (structure de reference) depuis des PDF
│   ├── requirements.txt
│   └── exemples_pdf/                3 PDF d'exemple (PV feu, scénario, doc commercial)
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

## Application locale (PDF -> validation)

Le dossier `application_locale/` fournit une interface web locale (Streamlit)
pour utiliser le validateur sans écrire de JSON à la main : on y dépose des
PV feu, scénarios d'essai et documents commerciaux au format PDF, l'appli en
extrait par reconnaissance de motifs les valeurs des paramètres du contrat,
pré-remplit un formulaire corrigeable, puis exécute `valider()` dessus. Tout
le traitement (lecture des PDF, extraction, validation) reste local : aucun
document n'est transmis à un service externe.

```bash
cd approfondissement_scientifique/application_locale
python3 -m venv .venv
source .venv/bin/activate          # .venv\Scripts\activate sous Windows
pip install -r requirements.txt
streamlit run app.py
```

L'appli s'ouvre dans le navigateur à l'adresse `http://localhost:8501`. Trois
PDF d'exemple sont fournis dans `exemples_pdf/` pour tester le parcours
complet sans documents confidentiels réels (régénérables avec
`python3 exemples_pdf/generer_exemples.py`).

L'extraction par motifs textuels reste volontairement « best effort » : les
PDF réels n'ont pas de format fixe, donc chaque valeur détectée est affichée
avec sa source (fichier et fragment brut) et reste éditable avant validation.
Une section « Avancé » dans la barre latérale permet, en complément, de
fournir un export schéma SQL et/ou paramètres CAO (JSON) pour activer les
passes SQL et CAO du validateur en plus de la passe configuration.

### Second onglet : configurateur par tables de gamme

En testant l'extraction avec de vrais documents (plaquette commerciale,
PV de résistance au feu), il s'est avéré que les dimensions précises, les
compatibilités matière/finition/fixation et les formules de calcul du
vantail ne s'y trouvent pas sous une forme exploitable automatiquement —
cette donnée d'ingénierie n'existe que dans les classeurs Excel de
configurateur (ex. `TPS.xlsx`) construits à partir de la documentation
technique.

L'onglet « Configurateur (tables de gamme) » importe directement ce type de
classeur via `application_locale/gamme_excel.py` : seules les feuilles à
onglet **vert** sont prises en compte (les feuilles rouges/oranges sont des
brouillons), selon la convention de nommage `Ls_` (listes de valeurs),
`Tc_` (tables de correspondance/compatibilité) et `Tb_` (tables de base :
modèles, constantes). Le module est générique — il ne connaît aucun champ
propre à une gamme précise — et fonctionne donc pour tout classeur suivant
la même convention de couleur/préfixes, gamme Coveraccess ou une autre.

Le module peut aussi s'utiliser en ligne de commande pour produire un export
JSON réutilisable :

```bash
python3 gamme_excel.py --xlsx chemin/vers/le/classeur.xlsx --sortie data/gammes/nom.json
```

Dans l'appli, un modèle et des options sont choisis à partir des tables
importées, puis le bouton « Vérifier la configuration » contrôle la
combinaison choisie contre toutes les tables de correspondance applicables
ainsi que les bornes dimensionnelles du modèle. Un expander optionnel permet
une vérification croisée *indicative* (recherche de mots-clés normalisés,
sans extraction de valeurs) du modèle et du classement feu choisis dans des
PDF déposés — le moteur de calcul des formules (`Tb_Formule`, masse du
vantail, position des paumelles, etc.) n'est volontairement pas implémenté
dans cette itération.

### Troisième onglet : générer un classeur depuis des PDF

Ce troisième onglet inverse le flux du précédent : au lieu d'importer un
classeur existant, on dépose les PDF d'un **nouvel** appareil (PV d'essai,
document commercial) et l'appli produit directement un résumé des
configurations possibles, plus un classeur Excel structuré comme une
référence fournie (ex. `TPS.xlsx`, qui ne sert qu'à connaître les noms de
feuilles/colonnes à utiliser — aucune valeur n'en est recopiée).

Concrètement (`application_locale/generer_excel.py`) : les plages
dimensionnelles (modèle, nombre de vantaux, classement feu, largeur/hauteur
mini-maxi) sont extraites via `pdfplumber.extract_tables()` — l'extraction
tenant compte des bordures/positions du tableau, contrairement au texte
brut qui mélange les tableaux avec le reste de la mise en page. Les codes
de classement feu (EI60, EI120...) sont recherchés par motif générique dans
tout le texte. Les listes de valeurs (`Ls_*` de la référence — matière,
finition, options...) sont recherchées par mention littérale dans le texte
des PDF.

Le résumé (modèles/plages, classements feu, options détectées) s'affiche
directement à l'écran — pas de formulaire de saisie ni de vérification
manuelle. Le classeur Excel téléchargeable reprend ces mêmes données. Les
tables `Tc_*` (compatibilités) et `Tb_Formule` (calculs) restent avec leurs
en-têtes seuls dans le classeur généré : cette logique d'ingénierie interne
ne se trouve dans aucun PDF, quel que soit l'appareil, et doit être
complétée manuellement. De même, une ligne de variante détectée sans code
de modèle explicite dans le PDF (ex. une option ajoutant une plage
dimensionnelle sans nom propre) est signalée « à compléter » plutôt que
devinée.

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
