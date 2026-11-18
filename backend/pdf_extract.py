"""
pdf_extract.py — Lecture des PDF (Binôme 1, étape 1)

Rôle : transformer un fichier PDF en données structurées que le reste
du projet peut utiliser :
  - le TEXTE de chaque page (pour le découpage en chunks et la recherche)
  - la POSITION de chaque ligne (pour le surlignage dans PdfViewer.jsx)

Bibliothèque utilisée : PyMuPDF (import pymupdf, ancien nom "fitz").
"""

import pymupdf


def charger_document(chemin_pdf: str) -> pymupdf.Document:
    """Ouvre un PDF et vérifie qu'il est exploitable."""
    try:
        doc = pymupdf.open(chemin_pdf)
    except Exception as e:
        raise ValueError(f"Impossible d'ouvrir le PDF : {e}")

    if doc.page_count == 0:
        raise ValueError("Le PDF ne contient aucune page.")
    if doc.is_encrypted:
        raise ValueError("Le PDF est protégé par un mot de passe.")
    return doc


def _lignes_de_page(page: pymupdf.Page) -> list[dict]:
    """
    Fonction interne : renvoie les lignes de texte d'une page avec leur
    rectangle (bbox). Utilisée par extraire_pages ET extraire_positions,
    pour que le texte et les positions soient toujours cohérents.
    """
    lignes = []
    # get_text("dict") renvoie la structure : blocs -> lignes -> spans
    structure = page.get_text("dict", sort=True)  # sort=True : ordre de lecture
    for bloc in structure["blocks"]:
        if bloc["type"] != 0:  # type 0 = texte, type 1 = image
            continue
        for ligne in bloc["lines"]:
            texte = "".join(span["text"] for span in ligne["spans"]).strip()
            if texte:
                lignes.append({"texte": texte, "bbox": list(ligne["bbox"])})
    return lignes


def extraire_pages(doc: pymupdf.Document) -> list[dict]:
    """
    Renvoie une liste avec une entrée par page :
      {"page": 1, "texte": "...", "largeur": 595.0, "hauteur": 842.0}
    Les numéros de page commencent à 1 (comme dans un lecteur PDF).
    """
    pages = []
    for index, page in enumerate(doc):
        lignes = _lignes_de_page(page)
        pages.append({
            "page": index + 1,
            "texte": "\n".join(l["texte"] for l in lignes),
            "largeur": page.rect.width,
            "hauteur": page.rect.height,
        })
    return pages


def extraire_positions(doc: pymupdf.Document) -> list[dict]:
    """
    Renvoie la position de chaque ligne :
      {"page": 1, "texte": "...", "bbox": [x0, y0, x1, y1],
       "debut": 0, "fin": 42}

    - bbox  : rectangle de la ligne en points PDF (origine en haut à gauche)
    - debut / fin : position (en caractères) de la ligne dans le texte de
      la page renvoyé par extraire_pages. Grâce à ça, quand un chunk cite
      les caractères 120 à 300 de la page 4, on retrouve les lignes à
      surligner.
    """
    positions = []
    for index, page in enumerate(doc):
        curseur = 0
        for ligne in _lignes_de_page(page):
            debut = curseur
            fin = debut + len(ligne["texte"])
            positions.append({
                "page": index + 1,
                "texte": ligne["texte"],
                "bbox": [round(v, 2) for v in ligne["bbox"]],
                "debut": debut,
                "fin": fin,
            })
            curseur = fin + 1  # +1 pour le "\n" ajouté entre les lignes
    return positions


def lignes_pour_intervalle(positions: list[dict], page: int,
                           debut: int, fin: int) -> list[dict]:
    """
    Outil pour le surlignage : renvoie les lignes d'une page qui
    chevauchent l'intervalle de caractères [debut, fin).
    """
    return [
        p for p in positions
        if p["page"] == page and p["debut"] < fin and p["fin"] > debut
    ]


if __name__ == "__main__":
    # Test rapide en ligne de commande : python pdf_extract.py fichier.pdf
    import sys, json
    doc = charger_document(sys.argv[1])
    pages = extraire_pages(doc)
    print(f"{len(pages)} pages")
    print(json.dumps(pages[0], ensure_ascii=False, indent=2)[:800])
    print(json.dumps(extraire_positions(doc)[:3], ensure_ascii=False, indent=2))
