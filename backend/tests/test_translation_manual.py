
from pdf_extract import charger_document, extraire_pages
from translation_agent import traduire_texte

chemin = "data/uploads/c784d73bd43f.pdf"

doc = charger_document(chemin)

try:
    pages = extraire_pages(doc)
finally:
    doc.close()

page = next(
    (p for p in pages if p["texte"].strip()),
    None
)

if page is None:
    print("Aucun texte trouvé dans le PDF.")
else:
    texte = page["texte"][:500]

    print("PAGE :", page["page"])
    print("\nTEXTE ORIGINAL :\n", texte)

    traduction = traduire_texte(texte, "en")

    print("\nTRADUCTION :\n", traduction)
