
import html
import io
import re
from pathlib import Path

import pymupdf

from translation_agent import (
    extraire_structure_pdf,
    regrouper_paragraphes_pdf,
    preparer_paragraphes_traduction,
    traduire_texte,
)


DOSSIER_FONTS = Path(__file__).resolve().parent / "fonts"


def nettoyer_texte(texte):
    return re.sub(
        r"\s+",
        " ",
        str(texte)
    ).strip()


def est_texte_a_conserver(texte):
    """Conserve les URL, emails et numéros sans traduction."""
    texte = texte.strip()

    return bool(
        re.fullmatch(r"https?://\S+", texte)
        or re.fullmatch(r"\S+@\S+\.\S+", texte)
        or re.fullmatch(r"\+?[\d\s().-]{7,}", texte)
    )


def style_principal(groupe):
    spans = [
        span
        for bloc in groupe["blocs"]
        for ligne in bloc["lignes"]
        for span in ligne["spans"]
    ]

    if not spans:
        raise ValueError("Groupe de texte vide.")

    return max(
        spans,
        key=lambda s: len(s["texte"])
    )


def convertir_couleur(valeur):
    return "#{:06x}".format(int(valeur) & 0xFFFFFF)


def construire_html(texte, taille, gras, couleur):
    texte = html.escape(texte)

    # Conserver les retours intentionnels
    texte = texte.replace("\n", "<br/>")

    classe = "bold" if gras else "regular"

    return f"""
    <div class="{classe}"
         dir="rtl"
         lang="ar"
         style="
            font-size:{taille:.2f}pt;
            color:{couleur};
         ">
        {texte}
    </div>
    """


def creer_story(contenu, archive):
    css = """
    @font-face {
        font-family: Naskh;
        src: url('NotoNaskhArabic-Regular.ttf');
    }

    @font-face {
        font-family: DejaVu;
        src: url('DejaVuSans.ttf');
    }

    @font-face {
        font-family: DejaVuBold;
        src: url('DejaVuSans-Bold.ttf');
    }

    body {
        margin: 0;
        padding: 0;
    }

    div {
        font-family: Naskh, DejaVu;
        direction: rtl;
        text-align: right;
        line-height: 1.20;
        margin: 0;
        padding: 0;
    }

    .bold {
        font-family: DejaVuBold, Naskh;
        font-weight: bold;
    }

    .regular {
        font-weight: normal;
    }
    """

    return pymupdf.Story(
        html=contenu,
        user_css=css,
        archive=archive
    )


def calculer_zone(page, groupe, suivant, tous):
    """
    Calcule une zone de placement sans utiliser
    automatiquement toute la page.
    """
    x0, y0, x1, y1 = groupe["bbox"]

    marge = 35
    largeur_page = page.rect.width
    hauteur_page = page.rect.height

    est_paragraphe = groupe["type"] == "paragraphe"

    # Pour les paragraphes, autoriser une zone large.
    # Pour les éléments courts, garder leur région.
    if est_paragraphe:
        gauche = max(marge, x0 - 4)
        droite = largeur_page - marge
    else:
        gauche = max(5, x0 - 3)
        droite = min(
            largeur_page - 5,
            max(x1 + 45, x0 + 120)
        )

    # Éviter d'empiéter sur un élément
    # placé à côté sur la même ligne.
    for autre in tous:
        if autre is groupe:
            continue

        ax0, ay0, ax1, ay1 = autre["bbox"]

        meme_ligne = (
            ay0 < y1 and ay1 > y0
        )

        if meme_ligne and ax0 >= x1:
            droite = min(droite, ax0 - 5)

    if droite <= gauche + 15:
        raise ValueError(
            "Région horizontale trop étroite."
        )

    haut = max(2, y0 - 3)

    # Le groupe suivant limite la hauteur uniquement
    # s'il se trouve réellement en dessous.
    bas = hauteur_page - 20

    if suivant is not None:
        prochain_y = suivant["bbox"][1]

        if prochain_y > y1:
            bas = min(bas, prochain_y - 2)

    # Un peu de marge pour les métriques de police.
    bas = max(bas, y1 + 3)
    bas = min(bas, hauteur_page - 2)

    return pymupdf.Rect(
        gauche,
        haut,
        droite,
        bas
    )


def exporter_pdf_arabe_layout(
    chemin_original,
    chemin_sortie,
    llm=None
):
    """
    Export arabe RTL pour PDF textuels de 1 à 5 pages.

    Vérifie les débordements avant modification.
    Préserve les graphiques autant que possible.
    """

    chemin_original = Path(chemin_original)
    chemin_sortie = Path(chemin_sortie)

    if chemin_original.resolve() == chemin_sortie.resolve():
        raise ValueError(
            "Le fichier de sortie doit être différent."
        )

    police_arabe = (
        DOSSIER_FONTS
        / "NotoNaskhArabic-Regular.ttf"
    )

    if not police_arabe.exists():
        raise FileNotFoundError(
            f"Police arabe absente : {police_arabe}"
        )

    structure = extraire_structure_pdf(
        str(chemin_original)
    )

    if not 1 <= len(structure) <= 5:
        raise ValueError(
            "Le PDF doit contenir entre 1 et 5 pages."
        )

    if any(not p["blocs"] for p in structure):
        raise ValueError(
            "PDF sans texte extractible : OCR nécessaire."
        )

    groupes = regrouper_paragraphes_pdf(structure)
    pages = preparer_paragraphes_traduction(groupes)

    archive = pymupdf.Archive(
        str(DOSSIER_FONTS)
    )

    with pymupdf.open(str(chemin_original)) as source:
        operations = []

        # 1. Traduction et mesure
        for numero_page, info in enumerate(pages):
            page = source[numero_page]
            elements = info["paragraphes"]

            # Trier par position verticale
            elements = sorted(
                elements,
                key=lambda g: (
                    g["bbox"][1],
                    g["bbox"][0]
                )
            )

            for index, groupe in enumerate(elements):
                texte_original = groupe["texte_traduction"]

                if est_texte_a_conserver(texte_original):
                    traduction = texte_original
                else:
                    traduction = traduire_texte(
                        texte_original,
                        "ar",
                        llm=llm
                    )

                traduction = str(traduction).strip()

                if not traduction:
                    raise ValueError(
                        f"Traduction vide page {numero_page + 1}, "
                        f"groupe {index + 1}."
                    )

                span = style_principal(groupe)

                taille = float(groupe["taille"])
                gras = "bold" in groupe["police"].lower()
                couleur = convertir_couleur(
                    span["couleur"]
                )

                suivant = (
                    elements[index + 1]
                    if index + 1 < len(elements)
                    else None
                )

                zone = calculer_zone(
                    page,
                    groupe,
                    suivant,
                    elements
                )

                contenu = construire_html(
                    traduction,
                    taille,
                    gras,
                    couleur
                )

                story = creer_story(
                    contenu,
                    archive
                )

                reste, _ = story.place(zone)

                if reste != 0:
                    raise ValueError(
                        f"Débordement arabe page "
                        f"{numero_page + 1}, "
                        f"groupe {index + 1}. "
                        "La traduction nécessite une "
                        "réorganisation de la mise en page."
                    )

                operations.append({
                    "page": numero_page,
                    "groupe": groupe,
                    "zone": zone,
                    "html": contenu
                })

        # 2. Vérifier les collisions des zones réellement utilisées.
        # Les rectangles disponibles peuvent se chevaucher
        # sans que les textes dessinés se chevauchent.

        for i, op1 in enumerate(operations):
            for op2 in operations[i + 1:]:
                if op1["page"] != op2["page"]:
                    continue

                # Vérifier uniquement les régions d'origine
                # pour éviter les faux positifs causés
                # par l'agrandissement des zones.
                rect1 = pymupdf.Rect(op1["groupe"]["bbox"])
                rect2 = pymupdf.Rect(op2["groupe"]["bbox"])

                intersection = rect1 & rect2

                if (
                    not intersection.is_empty
                    and intersection.width > 2
                    and intersection.height > 2
                ):
                    raise ValueError(
                        "Deux groupes originaux se chevauchent "
                        f"sur la page {op1['page'] + 1}."
                    )

        # 3. Générer les calques arabes dans des
        # PDF temporaires avant toute suppression.
        calques = []

        for numero_page, page in enumerate(source):
            tampon = io.BytesIO()

            writer = pymupdf.DocumentWriter(
                tampon
            )

            device = writer.begin_page(
                pymupdf.Rect(
                    0,
                    0,
                    page.rect.width,
                    page.rect.height
                )
            )

            for operation in operations:
                if operation["page"] != numero_page:
                    continue

                story = creer_story(
                    operation["html"],
                    archive
                )

                reste, _ = story.place(
                    operation["zone"]
                )

                if reste != 0:
                    raise ValueError(
                        "Erreur de placement arabe."
                    )

                story.draw(
                    device,
                    pymupdf.Identity
                )

            writer.end_page()
            writer.close()

            calques.append(
                tampon.getvalue()
            )

        # 4. Retirer les anciens textes.
        for operation in operations:
            page = source[operation["page"]]

            for bloc in operation["groupe"]["blocs"]:
                for ligne in bloc["lignes"]:
                    for span in ligne["spans"]:
                        page.add_redact_annot(
                            pymupdf.Rect(span["bbox"]),
                            fill=False,
                            cross_out=False
                        )

        for page in source:
            page.apply_redactions(
                images=0,
                graphics=0,
                text=0
            )

        # 5. Superposer les calques arabes.
        for numero_page, contenu_pdf in enumerate(calques):
            with pymupdf.open(
                stream=contenu_pdf,
                filetype="pdf"
            ) as calque:
                page = source[numero_page]

                page.show_pdf_page(
                    page.rect,
                    calque,
                    0,
                    overlay=True
                )

        chemin_sortie.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        source.save(
            str(chemin_sortie),
            garbage=4,
            deflate=True
        )

    return str(chemin_sortie)
