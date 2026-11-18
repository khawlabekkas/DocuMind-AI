
from translation_agent import traduire_document

# Faux LLM : aucun appel à Groq
nombre_appels = 0

def faux_llm(prompt, systeme):
    global nombre_appels
    nombre_appels += 1
    return "TRADUCTION_TEST"


chemin = "data/uploads/c784d73bd43f.pdf"

resultats = traduire_document(
    chemin_pdf=chemin,
    langue_cible="en",
    llm=faux_llm
)

print("Pages traitées :", len(resultats))
print("Appels LLM simulés :", nombre_appels)

print("\nPremière page :")
print("Numéro :", resultats[0]["page"])
print("Texte original présent :", bool(resultats[0]["texte_original"]))
print("Traduction :", resultats[0]["traduction"][:100])

print("\nDernière page :")
print("Numéro :", resultats[-1]["page"])
print("Traduction présente :", bool(resultats[-1]["traduction"]))
