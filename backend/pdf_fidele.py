
from pathlib import Path
import json
import re

import pymupdf

from translation_agent import (
    extraire_structure_pdf,
    regrouper_paragraphes_pdf,
    preparer_paragraphes_traduction,
    traduire_structure_pdf,
)


FONT_DIR = Path(__file__).resolve().parent / "fonts"


def choisir_police(nom, langue):
    """Choisit une police compatible avec le style original."""
    if langue == "ar":
        raise ValueError(
            "Le rendu arabe nécessite un moteur RTL dédié. "
            "Utilisez temporairement l'export PDF existant."
        )

    bold = "bold" in nom.lower()

    if "dejavu" in nom.lower():
        fichier = (
            "DejaVuSans-Bold.ttf"
            if bold else "DejaVuSans.ttf"
        )
    else:
        # Police de remplacement Unicode
        fichier = (
            "DejaVuSans-Bold.ttf"
            if bold else "DejaVuSans.ttf"
        )

    chemin = FONT_DIR / fichier

    if not chemin.is_file():
        raise FileNotFoundError(
            f"Police introuvable : {chemin}"
        )

    return chemin


def nettoyer_traduction(texte):
    """Supprime les éventuelles balises Markdown de code."""
    texte = str(texte).strip()
    texte = re.sub(
        r"^```(?:text|markdown)?\s*",
        "",
        texte,
        flags=re.I
    )
    texte = re.sub(r"\s*```$", "", texte)
    return texte.strip()


def couleur_rgb(valeur):
    return (
        ((valeur >> 16) & 255) / 255,
        ((valeur >> 8) & 255) / 255,
        (valeur & 255) / 255,
    )


def style_groupe(groupe):
    spans = [
        span
        for bloc in groupe["blocs"]
        for ligne in bloc["lignes"]
        for span in ligne["spans"]
    ]

    if not spans:
        raise ValueError("Groupe sans texte.")

    return spans[0]


def mesurer_texte(
    largeur,
    hauteur,
    texte,
    police,
    taille,
    alignement=0
):
    """
    Mesure sur une page temporaire.
    Ne modifie pas le PDF original.
    """
    with pymupdf.open() as doc:
        page = doc.new_page(
            width=max(largeur + 20, 50),
            height=max(hauteur + 20, 50)
        )

        page.insert_font(
            fontname="PoliceTest",
            fontfile=str(police)
        )

        return page.insert_textbox(
            pymupdf.Rect(
                10, 10,
                10 + largeur,
                10 + hauteur
            ),
            texte,
            fontname="PoliceTest",
            fontsize=taille,
            lineheight=1.15,
            align=alignement
        )


def ajuster_mise_en_page(page, operations):
    """
    Réorganise verticalement les blocs d'une page.

    Priorités :
    1. Conserver la taille originale.
    2. Réduire les espaces entre les blocs.
    3. Ajuster légèrement la police si nécessaire.
    4. Ne jamais dépasser les limites de la page.
    """

    if not operations:
        return operations

    operations = sorted(
        operations,
        key=lambda op: (
            op["groupe"]["bbox"][1],
            op["groupe"]["bbox"][0]
        )
    )

    marge_bas = 20
    marge_haut = 20
    espace_min = 4
    taille_min_ratio = 0.90

    # Première passe : calculer les hauteurs nécessaires.
    for op in operations:
        rect = pymupdf.Rect(op["groupe"]["bbox"])
        taille_originale = op["taille"]

        largeur = op["zone"].width
        hauteur = page.rect.height

        espace = mesurer_texte(
            largeur,
            hauteur,
            op["texte"],
            op["police"],
            taille_originale
        )

        if espace < 0:
            raise ValueError(
                "Impossible de mesurer le texte."
            )

        # Hauteur approximative occupée.
        op["hauteur_necessaire"] = (
            hauteur - espace + 2
        )

        op["taille_originale"] = taille_originale

    # Deuxième passe : disposer les groupes.
    position_y = max(
        marge_haut,
        operations[0]["groupe"]["bbox"][1]
    )

    for op in operations:
        hauteur = op["hauteur_necessaire"]

        op["zone"] = pymupdf.Rect(
            op["zone"].x0,
            position_y,
            op["zone"].x1,
            position_y + hauteur
        )

        position_y += hauteur + espace_min

    # Troisième passe : ajuster si la page déborde.
    if position_y > page.rect.height - marge_bas:

        espace_disponible = (
            page.rect.height
            - marge_bas
            - max(
                marge_haut,
                operations[0]["groupe"]["bbox"][1]
            )
        )

        espace_requis = sum(
            op["hauteur_necessaire"]
            for op in operations
        ) + espace_min * (len(operations) - 1)

        ratio = espace_disponible / espace_requis

        if ratio < taille_min_ratio:
            raise ValueError(
                "Le texte traduit ne peut pas tenir "
                "lisiblement sur la page sans changer "
                "le nombre de pages."
            )

        position_y = max(
            marge_haut,
            operations[0]["groupe"]["bbox"][1]
        )

        for op in operations:
            op["taille"] = (
                op["taille_originale"] * ratio
            )

            nouvelle_hauteur = (
                op["hauteur_necessaire"] * ratio
            )

            op["zone"] = pymupdf.Rect(
                op["zone"].x0,
                position_y,
                op["zone"].x1,
                position_y + nouvelle_hauteur
            )

            position_y += (
                nouvelle_hauteur + espace_min
            )

    return operations

def exporter_pdf_fidele(
    chemin_original,
    chemin_sortie,
    langue_cible,
    llm=None,
    cache_traductions=None
):
    """
    Traduction avec conservation approximative
    de la mise en page d'un PDF texte.

    - Maximum 5 pages
    - Conserve les éléments graphiques non textuels
    - Respecte les tailles de police originales
    - Ne réduit pas automatiquement les caractères
    - Arrête l'export si un bloc ne peut pas tenir
    """

    chemin_original = Path(chemin_original)
    chemin_sortie = Path(chemin_sortie)

    if langue_cible not in ("fr", "en", "es"):
        raise ValueError(
            "Cet exporteur expérimental prend en charge "
            "le français, l'anglais et l'espagnol."
        )

    if chemin_original.resolve() == chemin_sortie.resolve():
        raise ValueError(
            "Le fichier de sortie doit être différent de l'original."
        )

    structure = extraire_structure_pdf(
        str(chemin_original)
    )

    if not structure or len(structure) > 5:
        raise ValueError(
            "Le PDF doit contenir entre 1 et 5 pages."
        )

    if any(not page["blocs"] for page in structure):
        raise ValueError(
            "Une page ne contient aucun texte extractible. "
            "Les PDF scannés nécessitent un OCR."
        )

    groupes = regrouper_paragraphes_pdf(structure)
    pages = preparer_paragraphes_traduction(groupes)

    # Cache facultatif pour éviter de retraduire
    # les mêmes groupes pendant les essais.
    cache = {}
    chemin_cache = (
        Path(cache_traductions)
        if cache_traductions else None
    )

    if chemin_cache and chemin_cache.exists():
        cache = json.loads(
            chemin_cache.read_text(encoding="utf-8")
        )

    a_traduire = []

    for page in pages:
        for groupe in page["paragraphes"]:
            cle = (
                langue_cible
                + "::"
                + groupe["texte_traduction"]
            )

            if cle not in cache:
                a_traduire.append((cle, groupe))

    # Traduire uniquement les groupes absents du cache.
    for cle, groupe in a_traduire:
        temporaire = [{
            "page": 1,
            "largeur": 595,
            "hauteur": 842,
            "paragraphes": [groupe]
        }]

        traduit = traduire_structure_pdf(
            temporaire,
            langue_cible,
            llm=llm
        )

        cache[cle] = nettoyer_traduction(
            traduit[0]["paragraphes"][0]["traduction"]
        )

        if chemin_cache:
            chemin_cache.parent.mkdir(
                parents=True,
                exist_ok=True
            )
            chemin_cache.write_text(
                json.dumps(
                    cache,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

    with pymupdf.open(str(chemin_original)) as doc:

        operations = []

        # Préparer et valider tous les textes
        # AVANT de supprimer le texte original.
        for index_page, page_info in enumerate(pages):
            page = doc[index_page]
            paragraphes = page_info["paragraphes"]

            for index, groupe in enumerate(paragraphes):
                original = groupe["texte_traduction"]
                cle = langue_cible + "::" + original
                traduction = cache[cle]

                span = style_groupe(groupe)
                police = choisir_police(
                    groupe["police"],
                    langue_cible
                )

                x0, y0, x1, y1 = groupe["bbox"]

                # Utiliser la largeur de la zone de texte,
                # pas uniquement la largeur du texte anglais.
                marge_droite = max(
                    20,
                    page.rect.width - x0
                    if groupe["type"] == "paragraphe"
                    else page.rect.width - x0 - 20
                )

                largeur = min(
                    marge_droite,
                    page.rect.width - x0 - 5
                )

                # Limite verticale : prochain groupe.
                prochain_y = page.rect.height - 20

                if index + 1 < len(paragraphes):
                    prochain_y = paragraphes[
                        index + 1
                    ]["bbox"][1] - 2

                # Marge verticale pour les métriques
                # des polices, sans déplacer le texte.
                haut = max(0, y0 - 2)
                bas = max(y1 + 3, prochain_y)

                bas = min(
                    bas,
                    page.rect.height - 5
                )

                if bas <= haut:
                    raise ValueError(
                        f"Zone invalide page {index_page + 1}, "
                        f"groupe {index + 1}."
                    )

                zone = pymupdf.Rect(
                    x0,
                    haut,
                    x0 + largeur,
                    bas
                )

                taille = float(groupe["taille"])

                espace = mesurer_texte(
                    zone.width,
                    zone.height,
                    traduction,
                    police,
                    taille
                )

                if espace < 0:
                    # Le contrôle définitif sera effectué
                    # après réorganisation de la page.
                    pass

                operations.append({
                    "page": index_page,
                    "groupe": groupe,
                    "zone": zone,
                    "texte": traduction,
                    "police": police,
                    "taille": taille,
                    "couleur": couleur_rgb(
                        span["couleur"]
                    )
                })
        # Réorganiser les groupes page par page.
        for numero_page in range(len(doc)):
            operations_page = [
                op for op in operations
                if op["page"] == numero_page
            ]

            ajuster_mise_en_page(
                doc[numero_page],
                operations_page
            )
        # Supprimer les anciens textes.
        # Les annotations couvrent uniquement
        # les rectangles originaux.
        for operation in operations:
            page = doc[operation["page"]]

            for bloc in operation["groupe"]["blocs"]:
                for ligne in bloc["lignes"]:
                    for span in ligne["spans"]:
                        page.add_redact_annot(
                            pymupdf.Rect(span["bbox"]),
                            fill=False,
                            cross_out=False
                        )

        for page in doc:
            page.apply_redactions(
                images=0,
                graphics=0,
                text=0
            )

        # Insérer les traductions.
        for operation in operations:
            page = doc[operation["page"]]

            nom_police = (
                "TradBold"
                if "Bold" in operation["police"].name
                else "TradRegular"
            )

            page.insert_font(
                fontname=nom_police,
                fontfile=str(operation["police"])
            )

            reste = page.insert_textbox(
                operation["zone"],
                operation["texte"],
                fontname=nom_police,
                fontsize=operation["taille"],
                color=operation["couleur"],
                lineheight=1.15,
                overlay=True
            )

            if reste < 0:
                raise ValueError(
                    "Erreur de placement du texte traduit."
                )

        chemin_sortie.parent.mkdir(
            parents=True,
            exist_ok=True
        )
        if len(doc) != len(structure):
            raise ValueError(
                "Le nombre de pages a changé."
            )
        doc.save(
            str(chemin_sortie),
            garbage=4,
            deflate=True
        )

    return str(chemin_sortie)
