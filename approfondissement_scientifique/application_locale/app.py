#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application locale : valider un contrat d'interface SQL <-> CAO a partir
de documents PDF reels (PV feu, scenario d'essai, document commercial).

Lancement :
    streamlit run app.py

Tout le traitement (lecture des PDF, extraction, validation) s'execute en
local : aucun document n'est envoye a un service externe.
"""

import io
import json
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
RACINE = APP_DIR.parent
sys.path.insert(0, str(RACINE))

import re  # noqa: E402

from validateur import charger_json, valider  # noqa: E402
from extraction_pdf import extraire_texte, extraire_valeurs  # noqa: E402
from gamme_excel import (  # noqa: E402
    charger_gamme_excel,
    feuilles_listes_simples,
    lister_par_prefixe,
    verifier_compatibilite,
)
from generer_excel import (  # noqa: E402
    detecter_mentions_listes,
    detecter_tables_dimensions,
    extraire_classements_feu,
    generer_classeur,
    interpreter_table_dimensions,
)

CONTRAT_DIR = RACINE / "contrat"
DATA_DIR = RACINE / "data"

CLASSES_RUPTURE = {
    "R1": "Source SQL ou cible CAO absente",
    "R2": "Type incompatible",
    "R3": "Domaine de valeur incoherent",
    "R4": "Parametre obligatoire absent",
}

OPTIONS_BOOLEEN = ["Oui", "Non", '"true" (texte, type incorrect)', '"false" (texte, type incorrect)']
MAPPING_BOOLEEN = {
    "Oui": True,
    "Non": False,
    '"true" (texte, type incorrect)': "true",
    '"false" (texte, type incorrect)': "false",
}


def seeder_valeurs_par_defaut(contrat, valeurs_extraites):
    for parametre in contrat["parametres"]:
        pid = parametre["id"]
        type_p = parametre["type"]
        domaine = parametre.get("domaine", {})
        detect = valeurs_extraites.get(pid)
        key_valeur, key_absent = f"valeur_{pid}", f"absent_{pid}"

        if type_p in ("integer", "number"):
            valeur_brute = detect["valeur"] if detect else None
            defaut = valeur_brute if isinstance(valeur_brute, (int, float)) else domaine.get("min", 0)
            st.session_state[key_valeur] = defaut
        elif type_p == "boolean":
            valeur_brute = detect["valeur"] if detect else None
            if valeur_brute is True:
                st.session_state[key_valeur] = "Oui"
            elif valeur_brute is False:
                st.session_state[key_valeur] = "Non"
            else:
                st.session_state[key_valeur] = "Oui"
        elif "valeurs" in domaine:
            valeur_brute = detect["valeur"] if detect else None
            st.session_state[key_valeur] = str(valeur_brute) if valeur_brute is not None else str(domaine["valeurs"][0])
        else:
            valeur_brute = detect["valeur"] if detect else None
            st.session_state[key_valeur] = str(valeur_brute) if valeur_brute is not None else ""

        st.session_state[key_absent] = detect is None


def rendre_formulaire(contrat, valeurs_extraites):
    for parametre in contrat["parametres"]:
        pid = parametre["id"]
        type_p = parametre["type"]
        domaine = parametre.get("domaine", {})
        detect = valeurs_extraites.get(pid)
        key_valeur, key_absent = f"valeur_{pid}", f"absent_{pid}"

        col_label, col_widget, col_absent = st.columns([2.3, 3, 1.2])
        with col_label:
            tag = " · obligatoire" if parametre.get("obligatoire") else ""
            st.markdown(f"**{parametre['label']}**{tag}")
            if detect:
                statut = "valeur detectee" if detect["valeur"] is not None else "fragment trouve, a verifier"
                st.caption(f"{statut} dans *{detect['fichier']}* : « {detect['brut']} »")
            else:
                st.caption("non detecte dans les documents fournis")

        with col_widget:
            if type_p in ("integer", "number"):
                pas = 1 if type_p == "integer" else 0.1
                st.number_input(" ", key=key_valeur, step=pas, label_visibility="collapsed")
            elif type_p == "boolean":
                st.selectbox(" ", OPTIONS_BOOLEEN, key=key_valeur, label_visibility="collapsed")
            elif "valeurs" in domaine:
                options = [str(v) for v in domaine["valeurs"]]
                if detect and detect["valeur"] is not None and str(detect["valeur"]) not in options:
                    options.append(str(detect["valeur"]))
                options.append("Autre (saisie libre)")
                if st.session_state.get(key_valeur) not in options:
                    st.session_state[key_valeur] = options[0]
                choix = st.selectbox(" ", options, key=key_valeur, label_visibility="collapsed")
                if choix == "Autre (saisie libre)":
                    st.text_input("Valeur personnalisee", key=f"{key_valeur}_libre")
            else:
                st.text_input(" ", key=key_valeur, label_visibility="collapsed")

        with col_absent:
            st.checkbox("absent", key=key_absent)


def construire_configuration(contrat):
    valeurs = {}
    for parametre in contrat["parametres"]:
        pid = parametre["id"]
        if st.session_state.get(f"absent_{pid}"):
            continue
        type_p = parametre["type"]
        domaine = parametre.get("domaine", {})
        brut = st.session_state.get(f"valeur_{pid}")

        if type_p in ("integer", "number"):
            valeurs[pid] = int(brut) if type_p == "integer" else float(brut)
        elif type_p == "boolean":
            valeurs[pid] = MAPPING_BOOLEEN.get(brut, brut)
        elif "valeurs" in domaine:
            if brut == "Autre (saisie libre)":
                valeurs[pid] = st.session_state.get(f"valeur_{pid}_libre", "")
            else:
                valeurs[pid] = brut
        else:
            valeurs[pid] = brut
    return {"gamme": contrat.get("gamme"), "valeurs": valeurs}


def afficher_rapport(rapport):
    st.header("3. Resultat de la validation")
    resume = rapport["resume"]
    if rapport["ok"]:
        st.success(f"VALIDE — {resume['nb_parametres']} parametre(s), 0 erreur.")
    else:
        st.error(f"INVALIDE — {resume['nb_erreurs']} erreur(s) sur {resume['nb_parametres']} parametre(s).")

    if resume["classes_detectees"]:
        cols = st.columns(len(resume["classes_detectees"]))
        for col, (classe, nb) in zip(cols, resume["classes_detectees"].items()):
            col.metric(classe, nb, help=CLASSES_RUPTURE.get(classe, classe))

    if rapport["erreurs"]:
        st.table([
            {"Parametre": e["parametre"], "Classe": e["classe"], "Passe": e["passe"], "Message": e["message"]}
            for e in rapport["erreurs"]
        ])

    st.download_button(
        "Telecharger le rapport JSON",
        data=json.dumps(rapport, ensure_ascii=False, indent=2),
        file_name="rapport_validation.json",
        mime="application/json",
    )
    with st.expander("Rapport JSON complet"):
        st.json(rapport)


def onglet_contrat_json():
    st.caption(
        "Prototype du chapitre d'approfondissement scientifique — depose des PV feu, "
        "scenarios d'essai et documents commerciaux en PDF, et fais executer le validateur "
        "dessus. Tout s'execute en local, aucun document n'est transmis a un service externe."
    )

    fichiers_contrats = sorted(CONTRAT_DIR.glob("*.json"))
    noms_contrats = [f.name for f in fichiers_contrats]
    index_defaut = noms_contrats.index("contrat_coveraccess.json") if "contrat_coveraccess.json" in noms_contrats else 0
    nom_contrat = st.sidebar.selectbox("Contrat d'interface", noms_contrats, index=index_defaut)
    contrat = charger_json(CONTRAT_DIR / nom_contrat)
    st.sidebar.caption(f"Gamme : {contrat.get('gamme')} · version {contrat.get('version_contrat')}")

    schema_sql, parametres_cao = None, None
    with st.sidebar.expander("Avance : passes SQL et CAO (optionnel)"):
        utiliser_exemples = st.checkbox("Utiliser les exports d'exemple fournis (data/)")
        fichier_schema_sql = st.file_uploader("Export schema SQL (JSON)", type="json", key="upload_schema_sql")
        fichier_parametres_cao = st.file_uploader("Export parametres CAO (JSON)", type="json", key="upload_parametres_cao")
        if utiliser_exemples:
            schema_sql = charger_json(DATA_DIR / "export_schema_sql.json")
            parametres_cao = charger_json(DATA_DIR / "export_parametres_cao.json")
        if fichier_schema_sql is not None:
            schema_sql = json.load(fichier_schema_sql)
        if fichier_parametres_cao is not None:
            parametres_cao = json.load(fichier_parametres_cao)

    st.header("1. Documents sources")
    col_pv, col_scenario, col_commercial = st.columns(3)
    with col_pv:
        fichiers_pv_feu = st.file_uploader("PV feu", type="pdf", accept_multiple_files=True, key="pv_feu")
    with col_scenario:
        fichiers_scenario = st.file_uploader("Scenario d'essai", type="pdf", accept_multiple_files=True, key="scenario")
    with col_commercial:
        fichiers_commercial = st.file_uploader("Document commercial", type="pdf", accept_multiple_files=True, key="commercial")

    textes = {}
    for f in fichiers_pv_feu or []:
        textes[f"PV feu — {f.name}"] = extraire_texte(f)
    for f in fichiers_scenario or []:
        textes[f"Scenario — {f.name}"] = extraire_texte(f)
    for f in fichiers_commercial or []:
        textes[f"Doc. commercial — {f.name}"] = extraire_texte(f)

    with st.expander("Texte extrait des documents (verification)"):
        if textes:
            for nom, texte in textes.items():
                st.markdown(f"**{nom}**")
                st.text(texte or "(aucun texte detecte — PDF scanne en image ?)")
        else:
            st.caption("Aucun document charge pour le moment.")

    signature = (nom_contrat,) + tuple(
        sorted((f.name, f.size) for f in list(fichiers_pv_feu or []) + list(fichiers_scenario or []) + list(fichiers_commercial or []))
    )
    reinitialiser = st.button("Reinitialiser les valeurs depuis les documents")
    if reinitialiser or st.session_state.get("signature_fichiers") != signature:
        st.session_state["signature_fichiers"] = signature
        valeurs_extraites = extraire_valeurs(contrat, textes) if textes else {p["id"]: None for p in contrat["parametres"]}
        st.session_state["valeurs_extraites"] = valeurs_extraites
        seeder_valeurs_par_defaut(contrat, valeurs_extraites)
    else:
        valeurs_extraites = st.session_state.get("valeurs_extraites", {p["id"]: None for p in contrat["parametres"]})

    st.header("2. Parametres a valider")
    rendre_formulaire(contrat, valeurs_extraites)

    if st.button("Lancer la validation", type="primary"):
        configuration = construire_configuration(contrat)
        st.session_state["derniere_configuration"] = configuration
        st.session_state["dernier_rapport"] = valider(
            contrat, schema_sql=schema_sql, parametres_cao=parametres_cao, configuration=configuration
        )

    if "dernier_rapport" in st.session_state:
        with st.expander("Configuration soumise a la validation"):
            st.json(st.session_state.get("derniere_configuration", {}))
        afficher_rapport(st.session_state["dernier_rapport"])


def normaliser_pour_recherche(texte) -> str:
    return re.sub(r"[\s()]+", "", str(texte)).upper()


def chercher_mention(textes: dict, candidats: list) -> str | None:
    texte_complet = normaliser_pour_recherche(" ".join(t for t in textes.values() if t))
    for candidat in candidats:
        if candidat and normaliser_pour_recherche(candidat) in texte_complet:
            return candidat
    return None


def afficher_apercu_gamme(gamme: dict):
    for prefixe, titre in (("Ls_", "Listes de valeurs"), ("Tc_", "Tables de correspondance"), ("Tb_", "Tables de base")):
        feuilles = lister_par_prefixe(gamme, prefixe)
        with st.expander(f"{titre} ({len(feuilles)})"):
            for nom, feuille in feuilles.items():
                st.markdown(f"**{nom}**")
                if feuille["lignes"]:
                    st.dataframe(feuille["lignes"], hide_index=True, use_container_width=True)
                if feuille["notes"]:
                    st.caption("Notes : " + " · ".join(feuille["notes"]))


def onglet_configurateur_gamme():
    st.caption(
        "Importe un classeur Excel structure comme TPS.xlsx (feuilles a onglet vert : "
        "listes de valeurs, tables de correspondance, modeles) et configure/verifie une "
        "trappe a partir de ces tables, sans extraction depuis les PDF."
    )

    st.header("1. Classeur de gamme")
    fichier_xlsx = st.file_uploader("Classeur Excel (.xlsx)", type="xlsx", key="gamme_xlsx")
    if fichier_xlsx is None:
        st.info("Depose un classeur Excel pour commencer (ex. TPS.xlsx).")
        return

    signature_gamme = (fichier_xlsx.name, fichier_xlsx.size)
    if st.session_state.get("signature_gamme") != signature_gamme:
        st.session_state["signature_gamme"] = signature_gamme
        st.session_state["gamme"] = charger_gamme_excel(fichier_xlsx)
    gamme = st.session_state["gamme"]

    par_prefixe = {p: len(lister_par_prefixe(gamme, p)) for p in ("Ls_", "Tc_", "Tb_")}
    st.success(
        f"{len(gamme['feuilles'])} feuille(s) importee(s) — "
        f"{par_prefixe['Ls_']} liste(s), {par_prefixe['Tc_']} correspondance(s), "
        f"{par_prefixe['Tb_']} table(s) de base."
    )
    afficher_apercu_gamme(gamme)

    st.header("2. Modele et parametres")
    choix = {}
    feuille_modeles = gamme["feuilles"].get("Tb_TPS_Modele")
    ligne_modele = None
    if feuille_modeles and feuille_modeles["lignes"]:
        options_modele = feuille_modeles["lignes"]
        libelle = st.selectbox(
            "Modele",
            options_modele,
            format_func=lambda l: f"{l.get('Ce_Modele')} — {l.get('Li_Modele', '')}",
            key="gamme_modele",
        )
        ligne_modele = libelle
        choix["Ce_Modele"] = libelle.get("Ce_Modele")
        col_l, col_h = st.columns(2)
        with col_l:
            choix["La_PassageLibre"] = st.number_input(
                "Largeur passage libre (mm)", min_value=0, step=1, key="gamme_largeur"
            )
        with col_h:
            choix["Ht_PassageLibre"] = st.number_input(
                "Hauteur passage libre (mm)", min_value=0, step=1, key="gamme_hauteur"
            )
    else:
        st.caption("Pas de feuille 'Tb_TPS_Modele' dans ce classeur : pas de selection de modele.")

    for nom, feuille in feuilles_listes_simples(gamme):
        code_col, label_col = feuille["colonnes"]
        if not feuille["lignes"]:
            continue
        choisi = st.selectbox(
            feuille["titre"] or nom,
            feuille["lignes"],
            format_func=lambda l: f"{l.get(code_col)} — {l.get(label_col, '')}",
            key=f"gamme_liste_{nom}",
        )
        choix[code_col] = choisi.get(code_col)

    st.header("3. Verification de compatibilite")
    if st.button("Verifier la configuration", type="primary", key="gamme_verifier"):
        st.session_state["gamme_choix"] = choix
        st.session_state["gamme_erreurs"] = verifier_compatibilite(gamme, choix)

    if "gamme_erreurs" in st.session_state:
        with st.expander("Configuration soumise"):
            st.json(st.session_state.get("gamme_choix", {}))
        erreurs = st.session_state["gamme_erreurs"]
        if erreurs:
            st.error(f"INCOMPATIBLE — {len(erreurs)} probleme(s) detecte(s).")
            st.table([{"Table": e["table"], "Message": e["message"]} for e in erreurs])
        else:
            st.success("Configuration compatible avec les tables de la gamme.")

    with st.expander("Verification croisee avec des documents (optionnel)"):
        st.caption(
            "Recherche indicative du modele et du classement feu choisis dans le texte des "
            "documents fournis — n'extrait aucune dimension, ne bloque pas la validation."
        )
        codes_resistance_feu = sorted({
            ligne.get("Ce_ResistanceFeu")
            for feuille in gamme["feuilles"].values()
            if "Ce_ResistanceFeu" in feuille["colonnes"]
            for ligne in feuille["lignes"]
            if ligne.get("Ce_ResistanceFeu")
        })
        classement_choisi = st.selectbox(
            "Classement feu a verifier", ["(aucun)"] + codes_resistance_feu, key="gamme_classement_feu"
        )

        col_pv, col_commercial = st.columns(2)
        with col_pv:
            fichiers_pv = st.file_uploader("PV feu", type="pdf", accept_multiple_files=True, key="gamme_pv_feu")
        with col_commercial:
            fichiers_commercial = st.file_uploader(
                "Document commercial", type="pdf", accept_multiple_files=True, key="gamme_commercial"
            )

        textes_gamme = {}
        for f in fichiers_pv or []:
            textes_gamme[f"PV feu — {f.name}"] = extraire_texte(f)
        for f in fichiers_commercial or []:
            textes_gamme[f"Doc. commercial — {f.name}"] = extraire_texte(f)

        if textes_gamme:
            candidats_modele = [choix.get("Ce_Modele"), ligne_modele.get("Li_Modele") if ligne_modele else None]
            trouve_modele = chercher_mention(textes_gamme, candidats_modele)
            st.write("✅ Modele mentionne dans les documents" if trouve_modele else "⚠️ Modele non trouve dans les documents fournis")

            if classement_choisi != "(aucun)":
                trouve_classement = chercher_mention(textes_gamme, [classement_choisi])
                st.write(
                    "✅ Classement feu mentionne dans les documents"
                    if trouve_classement
                    else "⚠️ Classement feu non trouve dans les documents fournis"
                )
        else:
            st.caption("Aucun document charge pour le moment.")


def onglet_generer_depuis_pdf():
    st.caption(
        "Depose les PDF d'un appareil (PV d'essai, document commercial) et obtiens un resume "
        "des plages de configuration possibles, plus un classeur Excel structure comme une "
        "reference existante (ex. TPS.xlsx) — sans etape de saisie manuelle."
    )

    st.header("1. Classeur de reference (structure/nommage)")
    fichier_reference = st.file_uploader(
        "Classeur Excel de reference (ex. TPS.xlsx)", type="xlsx", key="genere_reference_xlsx"
    )
    if fichier_reference is None:
        st.info("Depose un classeur de reference pour connaitre les noms de tables/colonnes a produire.")
        return
    reference_gamme = charger_gamme_excel(fichier_reference)
    st.caption(f"Reference : {len(reference_gamme['feuilles'])} feuille(s) importee(s) depuis {reference_gamme['source']}.")

    st.header("2. Documents de l'appareil")
    fichiers_pdf = st.file_uploader(
        "PV d'essai / documents commerciaux (PDF, plusieurs fichiers possibles)",
        type="pdf",
        accept_multiple_files=True,
        key="genere_pdfs",
    )
    if not fichiers_pdf:
        st.info("Depose au moins un PDF pour lancer l'analyse.")
        return

    if st.button("Analyser les documents", type="primary", key="genere_analyser"):
        fichiers = {f.name: f for f in fichiers_pdf}
        textes = {nom: extraire_texte(f) for nom, f in fichiers.items()}

        tables_brutes = detecter_tables_dimensions(fichiers)
        lignes_modele = []
        for t in tables_brutes:
            lignes_modele.extend(interpreter_table_dimensions(t["table"]))

        st.session_state["genere_lignes_modele"] = lignes_modele
        st.session_state["genere_classements"] = extraire_classements_feu(textes)
        st.session_state["genere_mentions"] = detecter_mentions_listes(reference_gamme, textes)

    if "genere_lignes_modele" not in st.session_state:
        return

    st.header("3. Resume des configurations possibles")

    lignes_modele = st.session_state["genere_lignes_modele"]
    if lignes_modele:
        st.subheader("Modeles et plages dimensionnelles")
        st.table([
            {
                "Modele": ("⚠️ " if l["a_completer"] else "") + str(l["Ce_Modele"]),
                "Vantaux": l["Qt_Vantaux"],
                "Classement feu": l["Ce_ResistanceFeu_detectee"],
                "Largeur mini (mm)": l["Co_LPL_Min"],
                "Largeur maxi (mm)": l["Co_LPL_Max"],
                "Hauteur mini (mm)": l["Co_HPL_Min"],
                "Hauteur maxi (mm)": l["Co_HPL_Max"],
            }
            for l in lignes_modele
        ])
        if any(l["a_completer"] for l in lignes_modele):
            st.caption("⚠️ = ligne de variante detectee sans code de modele explicite dans le PDF, a completer a la main.")
    else:
        st.warning("Aucun tableau de plages dimensionnelles detecte dans les documents fournis.")

    st.subheader("Classements feu detectes")
    classements = st.session_state["genere_classements"]
    st.write(", ".join(classements) if classements else "Aucun classement feu detecte.")

    mentions = st.session_state["genere_mentions"]
    if mentions:
        st.subheader("Options / listes detectees dans les documents")
        for nom, lignes in mentions.items():
            feuille_ref = reference_gamme["feuilles"][nom]
            st.markdown(f"**{feuille_ref['titre'] or nom}**")
            st.table(lignes)

    st.header("4. Export")
    classeur = generer_classeur(reference_gamme, lignes_modele, mentions)
    buffer = io.BytesIO()
    classeur.save(buffer)
    st.download_button(
        "Telecharger le classeur Excel genere",
        data=buffer.getvalue(),
        file_name="gamme_generee.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(
        "Les feuilles Tc_* (compatibilites) et Tb_Formule (calculs) restent avec leurs en-tetes "
        "seuls : cette logique d'ingenierie ne se trouve dans aucun PDF, a completer manuellement."
    )


def main():
    st.set_page_config(page_title="Validateur contrat SQL <-> CAO", layout="wide")
    st.title("Validateur de contrat d'interface SQL ↔ CAO")

    onglet_contrat, onglet_gamme, onglet_generer = st.tabs([
        "Validation par contrat JSON",
        "Configurateur (tables de gamme)",
        "Generer un classeur depuis des PDF",
    ])
    with onglet_contrat:
        onglet_contrat_json()
    with onglet_gamme:
        onglet_configurateur_gamme()
    with onglet_generer:
        onglet_generer_depuis_pdf()


if __name__ == "__main__":
    main()
