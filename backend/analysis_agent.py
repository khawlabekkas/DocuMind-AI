"""
analysis_agent.py — Agent Analyse (Binôme 1, étape 5)

Trois fonctions, toutes avec un résultat SOURCÉ (citations [n] -> pages) :
  resumer_document          : résumé d'une page, d'un intervalle de pages ou du PDF
  expliquer_section         : explication simple d'une section / d'un concept
  analyser_document_complet : analyse structurée de tout le PDF (map-reduce)

Format de sortie (POST /analysis/run) :
  {"type": "summarize" | "explain" | "full", "scope": {...},
   "sections": [{"titre", "pages"}], "result": "texte", "citations": [...]}
"""

import time

from rag_agent import generer_citations

 
MAX_CARACTERES = 8_000
  # au-delà, on découpe (map-reduce)

SYSTEME = """Tu es DocuMind. Tu travailles UNIQUEMENT à partir des extraits fournis.
Cite tes sources avec le numéro de l'extrait entre crochets, ex. [1] ou [2][3].
Réponds en français sauf si on te demande une autre langue."""


def _pages_comme_passages(pages: list[dict], document_id: str) -> list[dict]:
    """Une page entière = un 'passage' citable (debut=0, fin=longueur)."""
    return [{"chunk_id": f"{document_id}_p{p['page']}", "document_id": document_id,
             "page": p["page"], "texte": p["texte"], "debut": 0, "fin": len(p["texte"])}
            for p in pages if p["texte"].strip()]


def _numeroter(passages: list[dict]) -> str:
    return "\n\n".join(f"[{i}] (page {p['page']})\n{p['texte']}"
                       for i, p in enumerate(passages, start=1))


def _lots(passages: list[dict], limite: int | None = None) -> list[list[dict]]:
    """Regroupe les passages en lots, sans dépasser la limite de caractères."""
    limite = limite or MAX_CARACTERES

    if limite <= 0:
        raise ValueError("La limite doit être positive.")

    lots = []
    courant = []
    taille = 0

    for passage in passages:
        texte = passage["texte"]

        # Découper les pages trop longues.
        morceaux = [
            texte[i:i + limite]
            for i in range(0, len(texte), limite)
        ]

        for morceau in morceaux:
            nouveau = {**passage, "texte": morceau}

            if courant and taille + len(morceau) > limite:
                lots.append(courant)
                courant = []
                taille = 0

            courant.append(nouveau)
            taille += len(morceau)

    if courant:
        lots.append(courant)

    return lots



def _resultat(type_, scope, passages, texte, obtenir_positions):
    return {
        "type": type_,
        "scope": scope,
        "sections": [{"titre": f"Page {p['page']}", "pages": [p["page"]]} for p in passages],
        "result": texte,
        "citations": generer_citations(texte, passages, obtenir_positions),
    }


# --------------------------------------------------------------- Résumé
def resumer_document(document_id: str, pages: list[dict], llm, obtenir_positions,
                     page_debut: int | None = None, page_fin: int | None = None) -> dict:
    page_debut = page_debut or 1
    page_fin = page_fin or len(pages)
    choisies = [p for p in pages if page_debut <= p["page"] <= page_fin]
    passages = _pages_comme_passages(choisies, document_id)
    scope = {"document_id": document_id, "page_debut": page_debut, "page_fin": page_fin}
    if not passages:
        return {"type": "summarize", "scope": scope, "sections": [], "citations": [],
                "result": "Aucun texte exploitable sur ces pages."}

    if sum(len(p["texte"]) for p in passages) <= MAX_CARACTERES:
        texte = llm("Résume ces extraits en 5 à 10 points clés, avec citations.\n\n"
                    + _numeroter(passages), SYSTEME)
    else:
        texte = _map_reduce(passages, llm, "Résume en points clés")
    return _resultat("summarize", scope, passages, texte, obtenir_positions)



def _map_reduce(passages, llm, consigne, systeme=SYSTEME):
    """
    Résumé hiérarchique :
    MAP : résumer les lots de passages.
    REDUCE : fusionner progressivement les résumés.
    """
    LIMITE_FUSION = 6_000

    # MAP : résumé de chaque lot
    partiels = []
    decalage = 0

    for lot in _lots(passages):
        bloc = "\n\n".join(
            f"[{decalage + i}] (page {p['page']})\n{p['texte']}"
            for i, p in enumerate(lot, start=1)
        )

        resume = llm(
            f"{consigne}. Cite tes sources avec les numéros [n]. "
            "Produis un résumé très concis de 150 à 200 mots maximum. "
            "Conserve uniquement les idées essentielles et les citations. "
            "N'ajoute aucune introduction inutile.\n\n"
            f"EXTRAITS :\n{bloc}",
            systeme
        )

        partiels.append(resume)
        decalage += len(lot)

        # Espacer les appels Groq pour réduire les pics de consommation.
        if decalage < len(passages):
            time.sleep(15)

    # REDUCE : fusion progressive
    while len(partiels) > 1:
        nouveaux = []
        groupe = []
        taille = 0

        for resume in partiels:
            if groupe and taille + len(resume) > LIMITE_FUSION:
                nouveaux.append(groupe)
                groupe = []
                taille = 0

            groupe.append(resume)
            taille += len(resume)

        if groupe:
            nouveaux.append(groupe)

        # Si les résumés sont déjà assez courts,
        # les fusionner directement.
        if len(nouveaux) == 1:
            return llm(
                "Fusionne ces résumés en un résumé final cohérent. "
                "Conserve les citations [n].\n\n"
                + "\n\n---\n\n".join(partiels),
                systeme
            )

        partiels_suivants = []

        for groupe in nouveaux:
            if len(groupe) == 1:
                partiels_suivants.append(groupe[0])
            else:
                fusion = llm(
                    "Fusionne ces résumés partiels. "
                    "Conserve les informations importantes "
                    "et les citations [n].\n\n"
                    + "\n\n---\n\n".join(groupe),
                    systeme
                )
                partiels_suivants.append(fusion)

        print(
            "DEBUG MAPREDUCE :",
            "avant =", len(partiels),
            "apres =", len(partiels_suivants),
            "tailles =", [len(r) for r in partiels],
            flush=True
        )

        if len(partiels_suivants) >= len(partiels):
            raise RuntimeError(
                "Impossible de réduire les résumés : "
                "un résumé individuel dépasse la limite."
            )

        partiels = partiels_suivants

    return partiels[0] if partiels else ""



# ----------------------------------------------------------- Explication
def expliquer_section(document_id: str, section: str, rechercher, llm,
                      obtenir_positions, k: int = 6) -> dict:
    """
    `section` : un titre ("section 3", "Méthodologie") ou un concept.
    On retrouve les passages concernés avec la recherche hybride,
    puis Gemini explique simplement.
    """
    passages = rechercher(section, k=k, document_ids=[document_id])
    scope = {"document_id": document_id, "section": section}
    if not passages:
        return {"type": "explain", "scope": scope, "sections": [], "citations": [],
                "result": "Section introuvable dans ce document."}
    passages = sorted(passages, key=lambda p: (p["page"], p["debut"]))  # ordre de lecture
    texte = llm(
        f"Explique de façon simple et pédagogique : « {section} ».\n"
        "Structure : 1) idée principale 2) explication pas à pas 3) exemple si possible.\n"
        "Si les extraits ne parlent pas de ce sujet, dis-le.\n\n" + _numeroter(passages),
        SYSTEME)
    return _resultat("explain", scope, passages, texte, obtenir_positions)


# ------------------------------------------------------- Analyse complète
def analyser_document_complet(
    document_id: str,
    pages: list[dict],
    llm,
    obtenir_positions,
    langue: str = "fr"
) -> dict:
    langues = {
        "fr": "français",
        "en": "anglais",
        "es": "espagnol",
        "ar": "arabe",
    }

    langue = langue if langue in langues else "fr"

    systeme_analyse = (
        "Tu es DocuMind. Travaille uniquement à partir des extraits fournis. "
        "Conserve les citations [n] et n'invente aucune information. "
        f"Rédige toute l'analyse en {langues[langue]}."
    )
    passages = _pages_comme_passages(pages, document_id)
    scope = {"document_id": document_id, "page_debut": 1, "page_fin": len(pages)}
    if not passages:
        return {"type": "full", "scope": scope, "sections": [], "citations": [],
                "result": "Aucun texte exploitable dans ce PDF."}
    consigne = ("Analyse ce document : 1) sujet et objectif 2) structure (parties et pages) "
                "3) idées clés 4) conclusion")
    if sum(len(p["texte"]) for p in passages) <= MAX_CARACTERES:
        texte = llm(
            f"{consigne}. Cite tes sources.\n\nEXTRAITS :\n"
            + _numeroter(passages),
            systeme_analyse
        )
    else:
        texte = _map_reduce(
            passages,
            llm,
            consigne,
            systeme=systeme_analyse
        )
    return _resultat("full", scope, passages, texte, obtenir_positions)
