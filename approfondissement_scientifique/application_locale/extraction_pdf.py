#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extraction heuristique des valeurs d'un contrat depuis des PDF.

Ce module ne remplace pas le validateur : il alimente un formulaire qui
reste corrigeable par l'utilisateur avant validation. Les PDF reels (PV
feu, scenario d'essai, document commercial) n'ont pas de format fixe, donc
l'extraction par motifs textuels reste "best effort".
"""

import re

import pdfplumber

MOTS_OUI = {"oui", "vrai", "true", "avec", "yes"}
MOTS_NON = {"non", "faux", "false", "sans", "no"}


def extraire_texte(fichier) -> str:
    """Concatene le texte de toutes les pages d'un PDF (chemin ou flux)."""
    pages = []
    with pdfplumber.open(fichier) as pdf:
        for page in pdf.pages:
            texte = page.extract_text() or ""
            pages.append(texte)
    return "\n".join(pages)


def _mots_cles(parametre: dict) -> list[str]:
    cles = [parametre["label"], parametre["id"].replace("_", " ")]
    return sorted(set(cles), key=len, reverse=True)


def _fragment_apres_motif(texte: str, mot_cle: str) -> str | None:
    motif = re.compile(re.escape(mot_cle) + r"\s*[:\-=]?\s*([^\n]{1,60})", re.IGNORECASE)
    trouve = motif.search(texte)
    return trouve.group(1).strip() if trouve else None


def _extraire_nombre(fragment: str):
    trouve = re.search(r"-?\d+(?:[.,]\d+)?", fragment)
    if not trouve:
        return None
    return trouve.group(0).replace(",", ".")


def _extraire_valeur_enum(fragment: str, valeurs_autorisees: list) -> str:
    for valeur in valeurs_autorisees:
        if re.search(re.escape(str(valeur)), fragment, re.IGNORECASE):
            return str(valeur)
    trouve = re.search(r"[A-Za-z0-9_]+", fragment)
    return trouve.group(0) if trouve else fragment.strip()


def _extraire_booleen(fragment: str):
    fragment_normalise = fragment.strip().lower()
    premier_mot = re.split(r"[\s,;.]", fragment_normalise)[0] if fragment_normalise else ""
    if premier_mot in MOTS_OUI:
        return True
    if premier_mot in MOTS_NON:
        return False
    return fragment.strip()


def _interpreter_fragment(parametre: dict, fragment: str):
    """Tente de convertir le fragment de texte au type attendu.

    Retourne None si le fragment ne peut pas etre interprete de facon
    fiable (le fragment brut reste alors affiche a l'utilisateur tel quel).
    """
    type_parametre = parametre["type"]
    if type_parametre in ("integer", "number"):
        nombre = _extraire_nombre(fragment)
        if nombre is None:
            return None
        return int(float(nombre)) if type_parametre == "integer" else float(nombre)
    if type_parametre == "boolean":
        valeur = _extraire_booleen(fragment)
        return valeur if isinstance(valeur, bool) else None
    domaine = parametre.get("domaine", {})
    if "valeurs" in domaine:
        return _extraire_valeur_enum(fragment, domaine["valeurs"])
    return fragment.strip() or None


def extraire_valeurs(contrat: dict, textes: dict[str, str]) -> dict[str, dict | None]:
    """Pour chaque parametre du contrat, cherche un fragment dans les textes fournis.

    `textes` associe un nom de fichier a son contenu textuel. Retourne un
    dict {parametre_id: {"valeur": ... | None, "brut": str, "fichier": ...} | None}.
    `valeur` est None quand un fragment a ete trouve mais n'a pas pu etre
    interprete de facon fiable dans le type attendu (l'utilisateur corrige
    alors a partir du fragment brut affiche dans l'interface).
    """
    resultats = {}
    for parametre in contrat["parametres"]:
        resultats[parametre["id"]] = None
        trouve = False
        for nom_fichier, texte in textes.items():
            for mot_cle in _mots_cles(parametre):
                fragment = _fragment_apres_motif(texte, mot_cle)
                if not fragment:
                    continue
                valeur = _interpreter_fragment(parametre, fragment)
                resultats[parametre["id"]] = {
                    "valeur": valeur,
                    "brut": fragment,
                    "fichier": nom_fichier,
                }
                trouve = True
                break
            if trouve:
                break
    return resultats
