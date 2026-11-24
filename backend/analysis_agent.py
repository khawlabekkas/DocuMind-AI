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

from functools import partial
from rag_agent import (
    generer_citations,
    generer_citations_precises
)


MAX_CARACTERES = 8_000
# Au-delà, on découpe (map-reduce)

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

    # Nouveau surlignage précis uniquement pour les explications
    if type_ in ("explain", "summarize","full"):
        try:
            texte, citations = generer_citations_precises(
                texte,
                passages,
                obtenir_positions
            )

        except Exception as e:
            print(
                f"[HIGHLIGHT] Fallback : {e}",
                flush=True
            )

            citations = generer_citations(
                texte,
                passages,
                obtenir_positions
            )

    else:
        # Conserver le fonctionnement existant
        citations = generer_citations(
            texte,
            passages,
            obtenir_positions
        )

    return {
        "type": type_,
        "scope": scope,
        "sections": [
            {
                "titre": f"Page {p['page']}",
                "pages": [p["page"]]
            }
            for p in passages
        ],
        "result": texte,
        "citations": citations,
    }



# --------------------------------------------------------------- Résumé

def resumer_document(
    document_id: str,
    pages: list[dict],
    llm,
    obtenir_positions,
    page_debut: int | None = None,
    page_fin: int | None = None,
    langue: str = "fr"
) -> dict:
    langues = {
        "fr": "français",
        "en": "anglais",
        "es": "espagnol",
        "ar": "arabe"
    }

    langue = langue if langue in langues else "fr"
    langues_llm = {"fr": "French", "en": "English", "es": "Spanish", "ar": "Arabic"}

    systeme_resume = (
         "Tu es DocuMind, un expert en analyse documentaire et en pédagogie. "
    "Travaille uniquement à partir des extraits fournis. "
    "N'invente aucune information. "
    "Conserve les citations [n] après les informations correspondantes. "

    f"Réponds exclusivement en {langues[langue]} du début à la fin. "
    f"Rédige intégralement le résumé en {langues[langue]}, "
    "y compris les titres et sous-titres. "

    "Présente le résumé comme un document professionnel, "
    "clair, pédagogique et facile à lire. "

    "Utilise une structure Markdown avec : "
    "- Un titre principal commençant par ## ; "
    "- Des sous-titres pertinents commençant par ### ; "
    "- Des listes à puces pour les idées essentielles ; "
    "- Des paragraphes courts pour les explications ; "
    "- Une conclusion synthétique. "

    "Adapte les titres au sujet exact du document. "
    "Évite les longs blocs de texte. "
    "N'ajoute pas de sections inutiles. "
    "N'affiche pas de balises HTML. "
    "Retourne uniquement le résumé structuré."
    )

    page_debut = page_debut or 1
    page_fin = page_fin or len(pages)

    choisies = [
        p for p in pages
        if page_debut <= p["page"] <= page_fin
    ]

    passages = _pages_comme_passages(choisies, document_id)

    scope = {
        "document_id": document_id,
        "page_debut": page_debut,
        "page_fin": page_fin
    }

    if not passages:
        return {
            "type": "summarize",
            "scope": scope,
            "sections": [],
            "citations": [],
            "result": "Aucun texte exploitable sur ces pages."
        }
    nombre_caracteres = sum(len(p["texte"]) for p in passages)

    # Larger completion budget for document summaries only
    llm_resume = partial(llm, max_completion_tokens=3000)


    print(
        f"[SUMMARY DEBUG] Pages: {len(choisies)} | "
        f"Characters: {nombre_caracteres} | "
        f"Limit: {MAX_CARACTERES} | "
        f"Mode: {'DIRECT' if nombre_caracteres <= MAX_CARACTERES else 'MAP_REDUCE'}",
        flush=True
    )

    if sum(len(p["texte"]) for p in passages) <= MAX_CARACTERES:
        texte = llm_resume(
            f"Respond exclusively in {langues_llm[langue]}. " +
            "Résume ces extraits en 5 à 10 points clés, "
            "avec citations.\n\n" + _numeroter(passages),
            systeme_resume
        )
    else:
        texte = _map_reduce(
            passages,
            llm_resume,
            "Résume en points clés",
            systeme=systeme_resume,
            langue=langues_llm[langue]
        )
    print(
        "[SUMMARY RAW RESPONSE]",
        repr(texte),
        flush=True
    )

    return _resultat(
        "summarize",
        scope,
        passages,
        texte,
        obtenir_positions
    )

def _map_reduce(passages, llm, consigne, systeme=SYSTEME, mode="resume", langue=None):
    """
    MAP-REDUCE avec deux modes :
    - resume : résumé hiérarchique classique.
    - analyse : sections pédagogiques assemblées sans appel LLM final.
    """
    LIMITE_FUSION = 6_000

    if mode not in ("resume", "analyse"):
        raise ValueError("Mode MAP-REDUCE invalide.")

    instruction_langue = f"Respond exclusively in {langue}. " if langue else ""
    partiels = []
    decalage = 0

    # --------------------------------------------------
    # ETAPE 1 : MAP
    # --------------------------------------------------

    for lot in _lots(passages):
        bloc = "\n\n".join(
            f"[{decalage + i}] (page {p['page']})\n{p['texte']}"
            for i, p in enumerate(lot, start=1)
        )

        if mode == "analyse":
            instruction_map = (
                "Rédige une section complète d'analyse experte et pédagogique "
                "à partir des extraits fournis. "
                "Commence par un sous-titre Markdown ### décrivant le sujet traité. "
                "Explique les concepts importants, leur fonctionnement, "
                "leur utilité et leurs relations. "
                "Développe les exemples présents dans les extraits. "
                "Mentionne les limites et implications justifiées par les sources. "
                "Ne fais pas une simple liste de définitions. "
                "Rédige environ 150 à 220 mots, avec des phrases complètes. "
                "Termine proprement sans laisser de phrase incomplète. "
                "Conserve les citations exactement au format [n]. "
                "N'invente aucune information. "
            )
            # Eviter de demander une longue analyse globale
            # dans chaque lot.
            instruction = instruction_map

        else:
            instruction_map = (
                "Produis un résumé très concis de 150 à 200 mots maximum. "
                "Conserve uniquement les idées essentielles et les citations. "
                "N'ajoute aucune introduction inutile. "
            )
            instruction = f"{consigne}. " + instruction_map

        resultat = llm(
            instruction
            + instruction_langue
            + " Cite tes sources avec les numéros [n].\n\n"
            + f"EXTRAITS :\n{bloc}",
            systeme,
        )

        partiels.append(resultat)
        decalage += len(lot)

    if not partiels:
        return ""

    # --------------------------------------------------
    # ETAPE 2 : ANALYSE
    # Assemblage direct des sections en Python
    # --------------------------------------------------

    if mode == "analyse":
        return (
            "## Analyse experte du document\n\n"
            + "\n\n".join(partiels)
        )

    # --------------------------------------------------
    # ETAPE 3 : REDUCE
    # Conserver le fonctionnement des résumés
    # --------------------------------------------------

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

        # Fusion finale des résumés
        if len(nouveaux) == 1:
            consigne_finale = (
                "Fusionne ces résumés en une synthèse finale cohérente. "
                "Conserve les citations [n] après les informations correspondantes. "
                "N'invente aucune information. "
                "Présente le résultat en Markdown avec : "
                "un titre principal commençant par ##, "
                "des sous-titres pertinents commençant par ###, "
                "des paragraphes courts et quelques listes à puces. "
                "Adapte les titres au sujet du document. "
                "Evite les répétitions et les longs blocs de texte. "
                "Respecte la langue demandée dans les instructions système. "
                "Retourne uniquement la synthèse structurée.\n\n"
            )

            return llm(
                instruction_langue + consigne_finale + "\n\n---\n\n".join(partiels),
                systeme,
            )

        partiels_suivants = []

        for groupe in nouveaux:
            if len(groupe) == 1:
                partiels_suivants.append(groupe[0])
            else:
                fusion = llm(
                    instruction_langue +
                    "Fusionne ces résumés partiels. "
                    "Conserve les informations importantes "
                    "et les citations [n].\n\n"
                    + "\n\n---\n\n".join(groupe),
                    systeme,
                )
                partiels_suivants.append(fusion)

        print(
            "DEBUG MAPREDUCE :",
            "avant =", len(partiels),
            "apres =", len(partiels_suivants),
            "tailles =", [len(r) for r in partiels],
            flush=True,
        )

        if len(partiels_suivants) >= len(partiels):
            raise RuntimeError(
                "Impossible de réduire les résumés : "
                "un résumé individuel dépasse la limite."
            )

        partiels = partiels_suivants

    return partiels[0]






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
        f"Explique clairement et de manière pédagogique le sujet suivant : "
        f"« {section} ».\n\n"
        "Consignes :\n"
        "- Réponds uniquement à partir des extraits fournis.\n"
        "- Identifie les concepts réellement pertinents pour la question.\n"
        "- Explique chaque concept simplement, avec un exemple si utile.\n"
        "- Respecte le niveau de détail demandé par l'utilisateur.\n"
        "- Si un nombre précis de points est demandé, respecte ce nombre.\n"
        "- Utilise des titres Markdown sur des lignes séparées et des listes lisibles.\n"
        "- Évite les tableaux Markdown et les développements inutiles.\n"
        "- Ajoute les citations exactement au format [n].\n"
        "- Ne crée aucune citation inexistante.\n"
        "- Termine toutes les phrases et sections.\n"
        "- Si les extraits sont insuffisants, indique-le clairement.\n\n"
        "EXTRAITS :\n"
        + _numeroter(passages),
        SYSTEME
    )

    return _resultat("explain", scope, passages, texte, obtenir_positions)


# ------------------------------------------------------- Analyse complète

def analyser_document_complet(
    document_id: str,
    pages: list[dict],
    llm,
    obtenir_positions,
    langue: str = "fr",
    page_debut: int | None = None,
    page_fin: int | None = None
) -> dict:
    langues = {
        "fr": "français",
        "en": "anglais",
        "es": "espagnol",
        "ar": "arabe",
    }

    langue = langue if langue in langues else "fr"
    systeme_analyse = (
         "Tu es DocuMind, un expert en analyse documentaire. "
    "Travaille uniquement à partir des extraits fournis. "
    "Conserve les citations exactement au format [n]. "
    "N'invente aucune information. "
    f"Rédige toute l'analyse exclusivement en {langues[langue]}, "
    "y compris les titres, sous-titres et explications. "
    "Ne change jamais de langue pendant la réponse. ")
    if langue == "ar":
        systeme_analyse = (
            systeme_analyse +
            "\nاكتب التحليل كاملاً باللغة العربية الفصحى. "
            "يجب أن تكون جميع العناوين والشروحات باللغة العربية. "
            "لا تستخدم اللغة الفرنسية في الإجابة."
        )
    
    elif langue == "es":
        systeme_analyse += (
            "\nResponde exclusivamente en español. "
            "Escribe todos los títulos, subtítulos, explicaciones "
            "y conclusiones en español. "
            "No respondas en francés."
        )

    print(
    "DEBUG SYSTEME ANALYSE:",
    repr(systeme_analyse),
    flush=True
)

    # Filtrer uniquement les pages demandées
    debut = 1 if page_debut is None else page_debut
    fin = len(pages) if page_fin is None else page_fin

    if debut < 1 or fin < debut or fin > len(pages):
        raise ValueError("Plage de pages invalide.")

    choisies = [
        p for p in pages
        if debut <= p["page"] <= fin
    ]

    passages = _pages_comme_passages(choisies, document_id)

    scope = {
        "document_id": document_id,
        "page_debut": debut,
        "page_fin": fin
    }

    if not passages:
        return {
            "type": "full",
            "scope": scope,
            "sections": [],
            "citations": [],
            "result": "Aucun texte exploitable sur ces pages."
        }

    if debut == fin:
        consigne = (
            f"Analyse exclusivement le contenu de la page {debut}. "
        "Agis comme un professeur expert qui explique le document "
        "à un étudiant souhaitant comprendre le sujet en profondeur. "

        "Commence par identifier le sujet exact et son objectif. "
        "Pour chaque concept essentiel, explique : "
        "ce qu'il signifie, comment il fonctionne et pourquoi "
        "il est important dans le contexte du document. "

        "Explique les relations entre les concepts. "
        "Développe les exemples présents dans les extraits. "
        "Présente les implications et les limites uniquement "
        "lorsqu'elles sont justifiées par le contenu fourni. "

        "Ne te contente pas de résumer ou de lister les idées. "
        "Privilégie les explications pédagogiques et le raisonnement. "

        "Structure la réponse avec des titres Markdown, "
        "des paragraphes explicatifs courts et des listes "
        "uniquement lorsqu'elles facilitent la compréhension. "

        "Conserve les citations [n] et n'invente aucune information. "
        "Respecte la langue demandée dans les instructions système."
        "Commence directement par un titre décrivant le sujet, "
"sans salutation ni présentation de ton rôle. "

"Écris toujours les citations exactement au format [n], "
"jamais sous forme de nombres isolés. "

"Si tu ajoutes une analogie pédagogique, présente-la "
"explicitement comme une illustration et non comme "
"une information provenant du document. "
        )
    else:
        consigne = (
             "Réalise une analyse approfondie de l'ensemble du document fourni. "
        "Agis comme un expert du domaine qui explique les informations "
        "avec rigueur et pédagogie. "

        "Commence par identifier le sujet exact, l'objectif principal "
        "et le contexte du document. "

        "Analyse les différentes sections dans un ordre logique. "
        "Pour chaque concept important, explique sa signification, "
        "son fonctionnement et son importance dans le document. "

        "Identifie les relations entre les concepts présentés "
        "dans différentes sections ou pages. "
        "Explique comment les idées se complètent, se renforcent "
        "ou se distinguent. "

        "Développe les exemples et applications présents dans le document. "
        "Présente les implications, les limites ou les points de vigilance "
        "uniquement lorsqu'ils sont justifiés par les sources. "

        "Ne produis pas un simple résumé des sections. "
        "Privilégie les explications, les liens logiques "
        "et l'interprétation des informations. "

        "Organise la réponse avec des titres Markdown clairs, "
        "des sous-sections et des paragraphes explicatifs. "
        "Utilise les listes uniquement lorsqu'elles améliorent la lisibilité. "

        "Commence directement par un titre pertinent, sans salutation. "
        "Conserve les citations exactement au format [n]. "
        "Distingue les analogies pédagogiques des faits du document. "
        "N'invente aucune information et respecte la langue demandée."
        )

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
            systeme=systeme_analyse,
            mode="analyse"
        )

    return _resultat(
        "full",
        scope,
        passages,
        texte,
        obtenir_positions
    )
