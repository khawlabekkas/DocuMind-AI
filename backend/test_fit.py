
import pymupdf

from translation_agent import (
    extraire_structure_pdf,
    regrouper_paragraphes_pdf,
    preparer_paragraphes_traduction,
    traduire_structure_pdf
)

structure = extraire_structure_pdf("test_layout.pdf")
groupes = regrouper_paragraphes_pdf(structure)
pages = preparer_paragraphes_traduction(groupes)

# Traduire tous les groupes
resultat = traduire_structure_pdf(pages, "fr")

doc = pymupdf.open("test_layout.pdf")
page = doc[0]

page.insert_font(
    fontname="DVRegularTest",
    fontfile="fonts/DejaVuSans.ttf"
)

page.insert_font(
    fontname="DVBoldTest",
    fontfile="fonts/DejaVuSans-Bold.ttf"
)

for i, g in enumerate(resultat[0]["paragraphes"], 1):
    x0, y0, x1, y1 = g["bbox"]

    police = (
        "DVBoldTest"
        if "Bold" in g["police"]
        else "DVRegularTest"
    )

    marge_verticale = g["taille"] * 0.5

    zone = pymupdf.Rect(
        x0,
        y0 - marge_verticale,
        page.rect.width - x0,
        y1 + marge_verticale
    )

    espace = page.insert_textbox(
        zone,
        g["traduction"],
        fontname=police,
        fontsize=g["taille"],
        lineheight=1.15
    )

    statut = "OK" if espace >= 0 else "DEPASSEMENT"

    print(
        f"Groupe {i:02d} | "
        f"{statut} | "
        f"espace={espace:.2f} | "
        f"taille={g['taille']:.1f}"
    )

doc.close()
