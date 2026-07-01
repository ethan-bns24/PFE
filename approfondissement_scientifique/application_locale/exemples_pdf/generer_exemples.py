#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genere 3 PDF d'exemple (PV feu, scenario d'essai, document commercial)
pour pouvoir tester l'application locale sans documents confidentiels reels.

Usage :
    python3 generer_exemples.py
"""

from pathlib import Path

from fpdf import FPDF

RACINE = Path(__file__).parent


def creer_pdf(nom_fichier: str, titre: str, lignes: list[str]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, titre, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.ln(4)
    for ligne in lignes:
        pdf.multi_cell(0, 8, ligne, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.output(str(RACINE / nom_fichier))


def main():
    creer_pdf(
        "pv_feu_exemple.pdf",
        "Proces-verbal d'essai de resistance au feu",
        [
            "Reference du dossier : PV-2026-0412",
            "Gamme testee : Coveraccess",
            "Classement de resistance au feu : EI60",
            "Largeur utile testee : 1200 mm",
            "Conclusion : conforme aux exigences de la classe EI60.",
        ],
    )
    creer_pdf(
        "scenario_exemple.pdf",
        "Scenario d'essai",
        [
            "Reference de configuration : CFG-2026-0412",
            "Hauteur utile : 800 mm",
            "Type de support de pose : beton",
            "Description : porte d'acces installee en facade beton, "
            "scenario d'essai standard.",
        ],
    )
    creer_pdf(
        "doc_commercial_exemple.pdf",
        "Document commercial",
        [
            "Produit : Coveraccess EI60",
            "Option joint intumescent renforce : oui",
            "Delai de livraison standard : 4 semaines.",
        ],
    )
    print("PDF d'exemple generes dans", RACINE)


if __name__ == "__main__":
    main()
