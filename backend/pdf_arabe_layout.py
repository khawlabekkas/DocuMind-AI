
import html
import io
import re
from pathlib import Path
import hashlib
import sqlite3
import os

import pymupdf
import json

from translation_agent import (
    extraire_structure_pdf,
    regrouper_paragraphes_pdf,
    preparer_paragraphes_traduction,
    traduire_texte,
)


DOSSIER_FONTS = Path(__file__).resolve().parent / "fonts"
# ==========================================
# CACHE PERSISTANT — TRADUCTION ARABE
# ==========================================

CACHE_ARABE = (
    Path(__file__).resolve().parent
    / "cache"
    / "traductions_arabes.sqlite3"
)

VERSION_CACHE_ARABE = "ar-v1"


def initialiser_cache_arabe():
    CACHE_ARABE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with sqlite3.connect(CACHE_ARABE, timeout=10) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS traductions (
                cle TEXT PRIMARY KEY,
                traduction TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def cle_cache_arabe(texte):
    fournisseur = os.getenv(
        "LLM_PROVIDER",
        "groq"
    ).strip().lower()

    if fournisseur == "openrouter":
        modele = os.getenv(
            "OPENROUTER_MODEL",
            "openai/gpt-oss-20b"
        )
    else:
        modele = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-20b"
        )

    contenu = (
        f"{VERSION_CACHE_ARABE}|"
        f"{fournisseur}|{modele}|ar|{texte}"
    )

    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


def lire_cache_arabe(texte):
    cle = cle_cache_arabe(texte)

    with sqlite3.connect(CACHE_ARABE, timeout=10) as con:
        resultat = con.execute(
            """
            SELECT traduction
            FROM traductions
            WHERE cle = ?
            """,
            (cle,)
        ).fetchone()

    return resultat[0] if resultat else None


def sauvegarder_cache_arabe(texte, traduction):
    traduction = str(traduction or "").strip()

    if not traduction:
        return

    cle = cle_cache_arabe(texte)

    with sqlite3.connect(CACHE_ARABE, timeout=10) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO traductions
            (cle, traduction)
            VALUES (?, ?)
            """,
            (cle, traduction)
        )


def traduire_arabe_cache(texte, llm=None):
    if est_texte_a_conserver(texte):
        return texte

    traduction = lire_cache_arabe(texte)

    if traduction:
        print(
            "[ARABIC CACHE] HIT — traduction reutilisee",
            flush=True
        )
        return traduction

    print(
        "[ARABIC CACHE] MISS — appel Groq",
        flush=True
    )

    for tentative in range(2):
        resultat = traduire_texte(
            texte,
            "ar",
            llm=llm
        )

        traduction = str(resultat or "").strip()

        if traduction:
            sauvegarder_cache_arabe(
                texte,
                traduction
            )

            return traduction

        print(
            f"[ARABIC CACHE] Reponse vide "
            f"{tentative + 1}/2",
            flush=True
        )

    raise ValueError(
        "Le modele a retourne une traduction arabe vide."
    )
def traduire_arabe_batch(textes, llm=None):
    """
    Traduit plusieurs blocs arabes en un seul appel.
    Réutilise le cache et vérifie les identifiants.
    """

    if llm is None:
        from llm import appeler_groq
        llm = appeler_groq

    resultats = {}
    manquants = {}

    for texte in dict.fromkeys(textes):

        if est_texte_a_conserver(texte):
            resultats[texte] = texte
            continue

        cache = lire_cache_arabe(texte)

        if cache:
            resultats[texte] = cache
        else:
            identifiant = str(len(manquants))
            manquants[identifiant] = texte

    if not manquants:
        return resultats

    systeme = (
        "Tu es un traducteur professionnel. "
        "Traduis chaque bloc intégralement en arabe. "
        "Conserve les termes techniques, les chiffres "
        "et les retours à la ligne nécessaires. "
        "Ne résume pas et ne fusionne pas les blocs. "
        "Retourne uniquement un objet JSON valide "
        "avec les mêmes identifiants et les textes "
        "traduits comme valeurs."
    )

    prompt = (
        "Traduis les valeurs de cet objet JSON "
        "en arabe sans modifier ses clés :\n\n"
        + json.dumps(
            manquants,
            ensure_ascii=False
        )
    )

    print(
        f"[ARABIC BATCH] {len(manquants)} blocs",
        flush=True
    )

    reponse = str(
        llm(prompt, systeme) or ""
    ).strip()

    reponse = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        reponse
    ).strip()

    try:
        donnees = json.loads(reponse)

        if not isinstance(donnees, dict):
            donnees = {}

    except json.JSONDecodeError:
        donnees = {}

    for identifiant, texte in manquants.items():

        traduction = donnees.get(identifiant)

        if (
            isinstance(traduction, str)
            and traduction.strip()
        ):
            traduction = traduction.strip()

            sauvegarder_cache_arabe(
                texte,
                traduction
            )

            resultats[texte] = traduction

    # Retraduire uniquement les blocs manquants.
    for texte in manquants.values():
        if texte not in resultats:
            resultats[texte] = traduire_arabe_cache(
                texte,
                llm=llm
            )

    return resultats
def preparer_lots_arabes(textes, taille_max=500):
    lots = []
    courant = []
    longueur = 0

    for texte in textes:

        if courant and (
            longueur + len(texte) > taille_max
            or len(courant) >= 4
        ):
            lots.append(courant)
            courant = []
            longueur = 0

        courant.append(texte)
        longueur += len(texte)

    if courant:
        lots.append(courant)

    return lots


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
    Adapte les zones de texte à la lecture RTL
    en respectant les éléments voisins.
    """

    rect = pymupdf.Rect(groupe["bbox"])
    limites = page.rect

    marge = 35

    # Utiliser la largeur disponible pour le texte arabe.
    gauche = max(
        limites.x0 + 5,
        min(rect.x0, limites.x0 + marge)
    )

    droite = min(
        limites.x1 - 5,
        max(rect.x1, limites.x1 - marge)
    )

    haut = max(limites.y0 + 2, rect.y0)
    bas = min(limites.y1 - 2, rect.y1 + 20)

    # Protéger les éléments voisins sur la même ligne.
    for autre in tous:
        if autre is groupe:
            continue

        voisin = pymupdf.Rect(autre["bbox"])

        meme_ligne = (
            voisin.y0 < rect.y1
            and voisin.y1 > rect.y0
        )

        if meme_ligne:
            if voisin.x0 >= rect.x1:
                droite = min(droite, voisin.x0 - 2)

            if voisin.x1 <= rect.x0:
                gauche = max(gauche, voisin.x1 + 2)

    # Protéger les blocs situés en dessous.
    for autre in tous:
        if autre is groupe:
            continue

        voisin = pymupdf.Rect(autre["bbox"])

        meme_colonne = (
            voisin.x0 < droite
            and voisin.x1 > gauche
        )

        if meme_colonne and voisin.y0 >= rect.y1:
            bas = min(bas, voisin.y0 - 1)

    zone = pymupdf.Rect(gauche, haut, droite, bas)

    if zone.is_empty:
        raise ValueError(
            "Zone de placement arabe invalide."
        )

    return zone
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
    initialiser_cache_arabe()

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
    textes = [
        groupe["texte_traduction"]
        for info in pages
        for groupe in info["paragraphes"]
    ]

    traductions_arabes = {}

    for lot in preparer_lots_arabes(
        list(dict.fromkeys(textes))
    ):
        traductions_arabes.update(
            traduire_arabe_batch(
                lot,
                llm=llm
            )
        )

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

                traduction = traductions_arabes[texte_original]

                traduction = str(traduction or "").strip()

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

                # Ajustement progressif de la taille du texte arabe.
                taille_initiale = taille
                taille_minimale = min(
                    taille_initiale,
                    max(8.0, taille_initiale * 0.75)
                )

                taille_actuelle = taille_initiale
                contenu = None

                while True:
                    candidat = construire_html(
                        traduction,
                        taille_actuelle,
                        gras,
                        couleur
                    )

                    story = creer_story(
                        candidat,
                        archive
                    )

                    reste, zone_utilisee = story.place(zone)

                    if reste == 0:
                        contenu = candidat
                        break

                    if taille_actuelle <= taille_minimale:
                        break

                    taille_actuelle = max(
                        taille_minimale,
                        taille_actuelle - 0.5
                    )

                if contenu is None:
                    raise ValueError(
                        f"Débordement arabe page {numero_page + 1}, "
                        f"groupe {index + 1}. "
                        "Une mise en page adaptative est nécessaire."
                    )

                print(
                    f"[ARABIC PDF] Page {numero_page + 1} | "
                    f"Bloc {index + 1} | "
                    f"Police : {taille_initiale:.1f} -> "
                    f"{taille_actuelle:.1f} pt",
                    flush=True
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
