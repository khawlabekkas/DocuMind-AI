
from llm import appeler_groq

LANGUES = {
    "fr": "français",
    "en": "anglais",
    "ar": "arabe",
    "es": "espagnol"
}


def traduire_texte(
    texte: str,
    langue_cible: str,
    llm=None
) -> str:
    """Traduit un texte avec Groq sans modifier son sens."""

    if langue_cible not in LANGUES:
        raise ValueError("Langue non supportée.")

    if not texte or not texte.strip():
        raise ValueError("Le texte à traduire est vide.")

    if llm is None:
        llm = appeler_groq

    systeme = (
        "Tu es un agent de traduction professionnel. "
        "Traduis fidèlement le texte fourni. "
        "Conserve le sens, les termes techniques, les chiffres "
        "et la structure du texte. "
        "Ne résume pas et n'ajoute aucune information. "
        "Retourne uniquement la traduction."
    )

    prompt = (
        f"Traduis le texte suivant en {LANGUES[langue_cible]} :\n\n"
        f"<texte>\n{texte}\n</texte>"
    )

    return llm(prompt, systeme)

from pdf_extract import charger_document, extraire_pages



def traduire_document(
    chemin_pdf: str,
    langue_cible: str,
    llm=None
) -> list[dict]:
    """
    Traduit un PDF page par page et morceau par morceau.
    Conserve le numéro de page et le texte original.
    """

    if langue_cible not in LANGUES:
        raise ValueError("Langue non supportée.")

    doc = charger_document(chemin_pdf)

    try:
        pages = extraire_pages(doc)
    finally:
        doc.close()

    resultats = []

    for page in pages:
        texte = page["texte"]

        if not texte.strip():
            traduction = ""
        else:
            morceaux = decouper_texte(texte, taille_max=3000)

            traductions = []

            for morceau in morceaux:
                traduction_morceau = traduire_texte(
                    morceau,
                    langue_cible,
                    llm=llm
                )
                traductions.append(traduction_morceau)

            traduction = "\n".join(traductions)

        resultats.append({
            "page": page["page"],
            "texte_original": texte,
            "traduction": traduction
        })

    return resultats


def decouper_texte(texte: str, taille_max: int = 3000) -> list[str]:
    """
    Découpe un texte long en morceaux sans perdre de contenu.
    Privilégie les retours à la ligne.
    """

    if taille_max <= 0:
        raise ValueError("taille_max doit être positive.")

    morceaux = []
    restant = texte

    while restant:
        if len(restant) <= taille_max:
            morceaux.append(restant)
            break

        coupure = restant.rfind("\n", 0, taille_max + 1)

        if coupure <= 0:
            coupure = taille_max
        else:
            coupure += 1

        morceaux.append(restant[:coupure])
        restant = restant[coupure:]

    return morceaux

def exporter_traduction_txt(
    pages_traduites: list[dict],
    chemin_sortie: str
) -> str:
    """
    Exporte les pages traduites dans un fichier TXT.
    """

    with open(chemin_sortie, "w", encoding="utf-8") as fichier:
        for page in pages_traduites:
            fichier.write(
                f"===== PAGE {page['page']} =====\n\n"
            )
            fichier.write(page["traduction"])
            fichier.write("\n\n")

    return chemin_sortie

import pymupdf



def exporter_traduction_pdf(
    pages_traduites: list[dict],
    chemin_sortie: str,
    langue_cible: str = "fr"
) -> str:
    from pathlib import Path
    from xml.sax.saxutils import escape

    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph,
        Spacer, PageBreak
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if langue_cible not in LANGUES:
        raise ValueError("Langue non supportée.")

    if langue_cible == "ar":
        import arabic_reshaper
        from bidi.algorithm import get_display

        police = Path("fonts/NotoNaskhArabic-Regular.ttf")
        if not police.is_file():
            raise FileNotFoundError(
                f"Police arabe introuvable : {police}"
            )

        nom_police = "DocuMindArabic"
        if nom_police not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont(nom_police, str(police))
            )
    else:
        nom_police = "Helvetica"

    style = ParagraphStyle(
        name="TraductionDocuMind",
        fontName=nom_police,
        fontSize=11,
        leading=19,
        alignment=TA_RIGHT if langue_cible == "ar" else TA_LEFT,
        spaceAfter=9,
        splitLongWords=True
    )

    document = SimpleDocTemplate(
        chemin_sortie,
        pagesize=(595.28, 841.89),
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    contenu = []

    for index, page in enumerate(pages_traduites):
        if index > 0:
            contenu.append(PageBreak())

        texte = page.get("traduction", "")

        for paragraphe in texte.split("\n"):
            paragraphe = paragraphe.strip()

            if not paragraphe:
                contenu.append(Spacer(1, 9))
                continue

            if langue_cible == "ar":
                paragraphe = get_display(
                    arabic_reshaper.reshape(paragraphe)
                )

            contenu.append(
                Paragraph(escape(paragraphe), style)
            )

    if not contenu:
        contenu.append(Spacer(1, 1))

    document.build(contenu)
    return chemin_sortie


    document = pymupdf.open()

    try:
        for page_traduite in pages_traduites:
            page = document.new_page()
            texte = page_traduite["traduction"]

            # Ajouter le texte traduit dans la page
            page.insert_textbox(
                pymupdf.Rect(50, 50, 545, 790),
                texte,
                fontsize=10,
                fontname="helv"
            )

        document.save(chemin_sortie)

    finally:
        document.close()

    return chemin_sortie




