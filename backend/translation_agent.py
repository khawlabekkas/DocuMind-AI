
from llm import appeler_groq
from time import perf_counter

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
        "Tu es DocuMind, un traducteur professionnel. "
        "Traduis intégralement le texte fourni dans la langue demandée. "
        "Ne résume pas, ne supprime aucune information et n'ajoute rien. "
        "Conserve fidèlement les termes techniques, les nombres "
        "et les références de citation comme [1], [2] et [3]. "
        "Conserve les titres Markdown et les listes à puces. "
        "Si le texte contient un tableau Markdown, transforme-le "
        "en sections avec des sous-titres et des listes à puces "
        "pour garantir une présentation lisible. "
        "N'utilise aucune balise HTML ou XML. "
        "Ne reproduis jamais les délimiteurs du texte source. "
        "Termine toutes les phrases et toutes les sections. "
        "Retourne uniquement le texte traduit."
    )

    prompt = (
        f"Langue cible : {LANGUES[langue_cible]}\n\n"
        "Traduis intégralement le contenu ci-dessous. "
        "Ne reproduis pas les délimiteurs.\n\n"
        "=== DÉBUT DU CONTENU ===\n"
        f"{texte}\n"
        "=== FIN DU CONTENU ==="
    )

    debut = perf_counter()

    print(
        f"[TRANSLATION] Input: {len(texte)} characters",
        flush=True
    )

    resultat = llm(prompt, systeme)

    print(
        f"[TRANSLATION] Groq call: {perf_counter() - debut:.2f}s",
        flush=True
    )

    return resultat

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

def exporter_pdf_mise_en_page(
    chemin_original: str,
    chemin_sortie: str,
    langue_cible: str,
    llm=None
) -> str:
    """
    Traduit les blocs de texte d'un PDF en conservant
    les pages et les éléments graphiques originaux.
    """
    import pymupdf
    from pathlib import Path

    if langue_cible not in LANGUES:
        raise ValueError("Langue non supportée.")

    source = pymupdf.open(chemin_original)

    try:
        # Traduire d'abord, sans modifier le PDF source.
        traductions_pages = []

        for page in source:
            blocs = page.get_text("dict")["blocks"]
            traductions = []

            for bloc in blocs:
                if bloc.get("type") != 0:
                    continue

                lignes = bloc.get("lines", [])
                texte = "\n".join(
                    "".join(
                        span["text"]
                        for span in ligne.get("spans", [])
                    )
                    for ligne in lignes
                ).strip()

                if not texte:
                    continue

                traduction = traduire_texte(
                    texte,
                    langue_cible,
                    llm=llm
                )

                tailles = [
                    span["size"]
                    for ligne in lignes
                    for span in ligne.get("spans", [])
                ]

                traductions.append({
                    "rect": pymupdf.Rect(bloc["bbox"]),
                    "texte": traduction,
                    "taille": max(tailles) if tailles else 10
                })

            traductions_pages.append(traductions)

        # Police Unicode pour le texte traduit.
        if langue_cible == "ar":
            police = (
                Path(__file__).resolve().parent
                / "fonts"
                / "NotoNaskhArabic-Regular.ttf"
            )
        else:
            police = Path("C:/Windows/Fonts/arial.ttf")

        if not police.exists():
            raise FileNotFoundError(
                f"Police nécessaire introuvable : {police}"
            )

        # Retirer les anciens textes, en préservant
        # autant que possible les images et graphiques.
        for page, traductions in zip(
            source, traductions_pages
        ):
            for element in traductions:
                page.add_redact_annot(
                    element["rect"],
                    fill=False,
                    cross_out=False
                )

            page.apply_redactions(
                images=0,
                graphics=0,
                text=0
            )

            page.insert_font(
                fontname="traduction",
                fontfile=str(police)
            )

            for element in traductions:
                rect = element["rect"]
                texte = element["texte"]

                # Ajuster légèrement la zone disponible.
                zone = pymupdf.Rect(
                    rect.x0,
                    rect.y0,
                    min(page.rect.x1 - 5, rect.x1 + 12),
                    min(page.rect.y1 - 5, rect.y1 + 8)
                )

                taille = min(element["taille"], 14)

                if langue_cible == "ar":
                    import arabic_reshaper
                    from bidi.algorithm import get_display

                    texte = get_display(
                        arabic_reshaper.reshape(texte)
                    )
                    alignement = pymupdf.TEXT_ALIGN_RIGHT
                else:
                    alignement = pymupdf.TEXT_ALIGN_LEFT

                insere = False

                while taille >= 5:
                    restant = page.insert_textbox(
                        zone,
                        texte,
                        fontname="traduction",
                        fontsize=taille,
                        lineheight=1.15,
                        align=alignement,
                        overlay=True
                    )

                    if restant >= 0:
                        insere = True
                        break

                    taille -= 0.5

                if not insere:
                    raise ValueError(
                        "Texte traduit trop long pour la "
                        f"zone de la page {page.number + 1}."
                    )

        source.save(
            chemin_sortie,
            garbage=4,
            deflate=True
        )

    finally:
        source.close()

    return chemin_sortie

def extraire_structure_pdf(chemin_pdf: str) -> list[dict]:
    """
    Extrait la structure visuelle d'un PDF :
    pages, blocs, lignes, texte et styles.
    Ne modifie pas le document original.
    """
    import pymupdf

    structure = []

    with pymupdf.open(chemin_pdf) as document:
        if len(document) > 5:
            raise ValueError(
                "Le PDF ne doit pas dépasser 5 pages."
            )

        for numero_page, page in enumerate(document, start=1):
            informations = page.get_text("dict")
            blocs = []

            for bloc in informations["blocks"]:
                if bloc.get("type") != 0:
                    continue

                lignes = []

                for ligne in bloc.get("lines", []):
                    spans = []

                    for span in ligne.get("spans", []):
                        texte = span.get("text", "")

                        if not texte.strip():
                            continue

                        spans.append({
                            "texte": texte,
                            "bbox": list(span["bbox"]),
                            "police": span.get("font", ""),
                            "taille": span.get("size", 10),
                            "couleur": span.get("color", 0),
                            "flags": span.get("flags", 0)
                        })

                    if spans:
                        lignes.append({
                            "bbox": list(ligne["bbox"]),
                            "spans": spans
                        })

                if lignes:
                    blocs.append({
                        "bbox": list(bloc["bbox"]),
                        "lignes": lignes
                    })

            structure.append({
                "page": numero_page,
                "largeur": page.rect.width,
                "hauteur": page.rect.height,
                "blocs": blocs
            })

    return structure

def regrouper_paragraphes_pdf(structure: list[dict]) -> list[dict]:
    """
    Regroupe les blocs de texte consécutifs en paragraphes,
    tout en conservant leurs positions et styles.
    """
    resultat = []

    for page in structure:
        groupes = []
        courant = None

        for bloc in page["blocs"]:
            spans = [
                span
                for ligne in bloc["lignes"]
                for span in ligne["spans"]
            ]

            if not spans:
                continue

            texte = " ".join(
                span["texte"].strip()
                for span in spans
            ).strip()

            if not texte:
                continue

            taille = spans[0]["taille"]
            police = spans[0]["police"]
            bbox = bloc["bbox"]

            if courant is not None:
                precedent = courant["bbox"]

                ecart = bbox[1] - precedent[3]

                meme_style = (
                    police == courant["police"]
                    and abs(taille - courant["taille"]) < 0.5
                )

                meme_alignement = (
                    abs(bbox[0] - precedent[0]) < 8
                )

                proche = 0 <= ecart <= taille * 1.2

                if meme_style and meme_alignement and proche:
                    courant["texte"] += "\n" + texte
                    courant["bbox"][2] = max(
                        courant["bbox"][2], bbox[2]
                    )
                    courant["bbox"][3] = bbox[3]
                    courant["blocs"].append(bloc)
                    continue

            courant = {
                "texte": texte,
                "police": police,
                "taille": taille,
                "bbox": bbox.copy(),
                "blocs": [bloc]
            }

            groupes.append(courant)

        resultat.append({
            "page": page["page"],
            "largeur": page["largeur"],
            "hauteur": page["hauteur"],
            "paragraphes": groupes
        })

    return resultat

def preparer_paragraphes_traduction(pages: list[dict]) -> list[dict]:
    """
    Prépare les groupes pour la traduction.

    - Les paragraphes longs peuvent être reformatés.
    - Les groupes courts conservent leurs retours à la ligne.
    - Les informations de style et de position sont conservées.
    """
    resultat = []

    for page in pages:
        paragraphes = []

        for groupe in page["paragraphes"]:
            lignes = groupe["texte"].splitlines()
            texte_complet = " ".join(
                ligne.strip() for ligne in lignes if ligne.strip()
            )

            # Heuristique provisoire : distinguer les groupes
            # courts des paragraphes de texte.
            est_paragraphe = (
                len(texte_complet) > 180
                and len(lignes) >= 2
            )

            paragraphes.append({
                **groupe,
                "texte_traduction": (
                    texte_complet
                    if est_paragraphe
                    else groupe["texte"]
                ),
                "type": (
                    "paragraphe"
                    if est_paragraphe
                    else "bloc_structure"
                )
            })

        resultat.append({
            **page,
            "paragraphes": paragraphes
        })

    return resultat

def traduire_structure_pdf(
    pages: list[dict],
    langue_cible: str,
    llm=None
) -> list[dict]:
    """
    Traduit les groupes de texte préparés sans perdre
    leurs informations de mise en page.
    """
    if langue_cible not in LANGUES:
        raise ValueError(
            f"Langue non supportée : {langue_cible}"
        )

    resultat = []

    for page in pages:
        groupes_traduits = []

        for groupe in page["paragraphes"]:
            texte = groupe["texte_traduction"]

            if not texte.strip():
                continue

            traduction = traduire_texte(
                texte=texte,
                langue_cible=langue_cible,
                llm=llm
            )

            groupes_traduits.append({
                **groupe,
                "traduction": traduction
            })

        resultat.append({
            **page,
            "paragraphes": groupes_traduits
        })

    return resultat

def tester_reconstruction_pdf(
    chemin_original: str,
    chemin_sortie: str
) -> None:
    """
    Test de reconstruction visuelle sans traduction.
    Conserve une copie de la page originale et remplace
    les blocs de texte par leur texte initial.
    """
    import pymupdf
    from pathlib import Path

    structure = extraire_structure_pdf(chemin_original)
    dossier_fonts = Path(__file__).resolve().parent / "fonts"

    with pymupdf.open(chemin_original) as document:
        for numero_page, page_info in enumerate(structure):
            page = document[numero_page]

            blocs = page_info["blocs"]

            # Supprimer uniquement les zones textuelles.
            for bloc in blocs:
                zone = pymupdf.Rect(bloc["bbox"])
                page.add_redact_annot(
                    zone,
                    fill=False,
                    cross_out=False
                )

            page.apply_redactions(
                images=0,
                graphics=0,
                text=0
            )

            page.insert_font(
                fontname="DVRegular",
                fontfile=str(dossier_fonts / "DejaVuSans.ttf")
            )

            page.insert_font(
                fontname="DVBold",
                fontfile=str(dossier_fonts / "DejaVuSans-Bold.ttf")
            )

            for bloc in blocs:
                for ligne in bloc["lignes"]:
                    for span in ligne["spans"]:
                        texte = span["texte"]
                        x0, y0, x1, y1 = span["bbox"]

                        police = (
                            "DVBold"
                            if "Bold" in span["police"]
                            else "DVRegular"
                        )

                        couleur_int = span["couleur"]

                        couleur = (
                            (couleur_int >> 16 & 255) / 255,
                            (couleur_int >> 8 & 255) / 255,
                            (couleur_int & 255) / 255
                        )

                        # Insertion à la position originale
                        page.insert_text(
                            (x0, y1 - 2),
                            texte,
                            fontname=police,
                            fontsize=span["taille"],
                            color=couleur,
                            overlay=True
                        )

        document.save(
            chemin_sortie,
            garbage=4,
            deflate=True
        )
    
def exporter_pdf_arabe_fidele(
    chemin_original: str,
    chemin_sortie: str,
    llm=None
) -> str:
    """
    Traduit un PDF en arabe avec rendu RTL via
    PyMuPDF Story.

    Conserve les pages et les éléments graphiques
    dans la mesure du possible.
    """
    import html
    import pymupdf
    from pathlib import Path

    police = (
        Path(__file__).resolve().parent
        / "fonts"
        / "NotoNaskhArabic-Regular.ttf"
    )

    if not police.is_file():
        raise FileNotFoundError(
            f"Police arabe introuvable : {police}"
        )

    source = pymupdf.open(chemin_original)

    try:
        if not 1 <= len(source) <= 5:
            raise ValueError(
                "Le PDF doit contenir entre 1 et 5 pages."
            )

        donnees_pages = []

        # 1. Traduire sans modifier le PDF.
        for page in source:
            elements = []

            for bloc in page.get_text("dict")["blocks"]:
                if bloc.get("type") != 0:
                    continue

                lignes = bloc.get("lines", [])
                texte = " ".join(
                    "".join(
                        span.get("text", "")
                        for span in ligne.get("spans", [])
                    ).strip()
                    for ligne in lignes
                ).strip()

                if not texte:
                    continue

                tailles = [
                    span.get("size", 10)
                    for ligne in lignes
                    for span in ligne.get("spans", [])
                ]

                traduction = traduire_texte(
                    texte,
                    "ar",
                    llm=llm
                )

                elements.append({
                    "rect": pymupdf.Rect(bloc["bbox"]),
                    "traduction": traduction,
                    "taille": max(tailles) if tailles else 10
                })

            donnees_pages.append(elements)

        # 2. Charger la police dans l'archive HTML.
        archive = pymupdf.Archive(
            str(police.parent)
        )

        css = """
        @font-face {
            font-family: ArabicPDF;
            src: url('NotoNaskhArabic-Regular.ttf');
        }

        body {
            margin: 0;
            padding: 0;
        }

        .texte {
            font-family: ArabicPDF;
            direction: rtl;
            text-align: right;
            line-height: 1.25;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        """

        # 3. Mesurer les textes avant de modifier
        #    le PDF.
        operations = []

        for numero, elements in enumerate(donnees_pages):
            page = source[numero]

            for index, element in enumerate(elements):
                rect = element["rect"]
                taille = min(
                    float(element["taille"]),
                    14.0
                )

                # Zone élargie horizontalement.
                zone = pymupdf.Rect(
                    max(5, rect.x0 - 10),
                    max(5, rect.y0 - 3),
                    min(page.rect.x1 - 5, rect.x1 + 30),
                    min(page.rect.y1 - 5, rect.y1 + 12)
                )

                contenu = html.escape(
                    element["traduction"]
                )

                contenu_html = f"""
                <div class="texte"
                     dir="rtl"
                     style="font-size:{taille}pt">
                    {contenu}
                </div>
                """

                story = pymupdf.Story(
                    html=contenu_html,
                    user_css=css,
                    archive=archive
                )

                reste, _ = story.place(zone)

                if reste != 0:
                    raise ValueError(
                        f"Texte arabe trop long : "
                        f"page {numero + 1}, "
                        f"bloc {index + 1}. "
                        "La mise en page doit être adaptée."
                    )

                operations.append({
                    "page": numero,
                    "rect": rect,
                    "zone": zone,
                    "html": contenu_html
                })

        # 4. Supprimer les textes originaux.
        for operation in operations:
            page = source[operation["page"]]
            page.add_redact_annot(
                operation["rect"],
                fill=False,
                cross_out=False
            )

        for page in source:
            page.apply_redactions(
                images=0,
                graphics=0,
                text=0
            )

        # 5. Insérer les textes arabes avec Story.
        import io

        for operation in operations:
            page = source[operation["page"]]

            story = pymupdf.Story(
                html=operation["html"],
                user_css=css,
                archive=archive
            )

            zone = operation["zone"]

            # Générer un PDF temporaire avec le texte arabe.
            tampon = io.BytesIO()

            writer = pymupdf.DocumentWriter(tampon)

            device = writer.begin_page(
                pymupdf.Rect(
                    0, 0,
                    page.rect.width,
                    page.rect.height
                )
            )

            reste, _ = story.place(zone)

            if reste != 0:
                raise ValueError(
                    "Le texte arabe ne tient pas "
                    "dans sa zone."
                )

            story.draw(device, pymupdf.Identity)

            writer.end_page()
            writer.close()

            # Superposer le rendu arabe sur la page originale.
            tampon.seek(0)

            with pymupdf.open(
                stream=tampon.getvalue(),
                filetype="pdf"
            ) as rendu:
                page.show_pdf_page(
                    page.rect,
                    rendu,
                    0,
                    overlay=True
                )

        source.save(
            chemin_sortie,
            garbage=4,
            deflate=True
        )

    finally:
        source.close()

    return chemin_sortie








