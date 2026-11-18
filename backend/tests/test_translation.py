
from pdf_extract import charger_document, extraire_pages
from translation_agent import traduire_texte

chemin = "data/uploads/c784d73bd43f.pdf"

# 1. Ouvrir le PDF
doc = charger_document(chemin)

try:
    # 2. Extraire les pages
    pages = extraire_pages(doc)
finally:
    doc.close()

# 3. Prendre uniquement la première page contenant du texte
page = next(
    (p for p in pages if p["texte"].strip()),
    None
)

if page is None:
    print("Aucun texte trouvé dans le PDF.")
else:
    # Limiter le test à un court extrait
    texte = page["texte"][:500]

    print("PAGE :", page["page"])
    print("\nTEXTE ORIGINAL :\n", texte)

    # 4. Traduire en anglais
    traduction = traduire_texte(texte, "en")

    print("\nTRADUCTION :\n", traduction)
