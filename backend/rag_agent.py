"""
rag_agent.py — Agent RAG (Binôme 1, étape 3)

Parcours d'une question (cahier des charges, section 5) :
  RAG (recherche) -> Guard (Binôme 2) -> Gemini -> Fact-Checking (Binôme 2) -> citations

CONTRAT AVEC LE BINÔME 2 (fonctions optionnelles passées à agent_rag) :
  guard(question, passages) -> {"status": "sufficient" | "insufficient",
                                "reason": str}
  fact_check(question, reponse, passages) -> {"verdict": "supported" | "corrected" | "rejected",
                                              "corrected_answer": str | None,
                                              "details": ...}
"""

import re
from rag_pipeline import charger_modele
from time import perf_counter
from functools import lru_cache

PROMPT_SYSTEME = """Tu es DocuMind, un assistant qui répond UNIQUEMENT à partir des passages fournis.
Règles :
1. N'utilise aucune connaissance extérieure aux passages.
2. Après chaque information, cite le passage source avec son numéro entre crochets, ex. [1] ou [2][3].
3. Si les passages ne permettent pas de répondre, réponds exactement : INSUFFISANT.
4. Réponds intégralement dans la langue demandée par l'utilisateur,
y compris les titres, sous-titres, tableaux et conclusions.
Ne mélange jamais les langues, sauf pour les termes techniques
et les citations originales.
5. Utilise un Markdown valide :
   - Chaque titre commence sur une nouvelle ligne.
   - Ajoute une ligne vide avant et après chaque titre.
   - Utilise des listes à puces pour les étapes.
   - Évite les tableaux Markdown pour les explications longues.
   - Ne produis jamais de balises HTML.
6. Termine chaque section et chaque phrase.
   Ne commence pas une section si tu ne peux pas la développer.
7. Si l'utilisateur demande un nombre précis de points,
   respecte exactement ce nombre.
   Si l'utilisateur demande une réponse concise,
   évite les développements détaillés, les exemples
   et les sous-sections non demandés.
   Ajoute une citation [n] à chaque point.
8. Granularité des citations :
   - Chaque affirmation distincte doit avoir sa propre citation.
   - Place la citation immédiatement après l'information
     qu'elle justifie.
   - Ne regroupe pas plusieurs concepts différents sous
     une seule citation placée en fin de paragraphe.
   - Si plusieurs concepts proviennent du même passage,
     répète le numéro de citation après chaque concept.
   - Cite séparément chaque définition, exemple et explication.
   - Utilise exclusivement les numéros des passages fournis.
   - N'invente jamais de numéro de citation.
"""

MOT_REFUS = "INSUFFISANT"

def reformuler_question(question: str, historique: list[dict], llm) -> str:
    """
    Reformule une question de suivi en utilisant l'historique.
    Ne génère pas de réponse : uniquement une question autonome.
    """
    if not historique:
        return question

    derniers_messages = historique[-6:]

    contexte = "\n".join(
        f"{m['role']}: {m['contenu']}"
        for m in derniers_messages
        if m.get("contenu")
    )

    prompt = f"""
HISTORIQUE DE CONVERSATION :
{contexte}

NOUVELLE QUESTION :
{question}

Reformule la nouvelle question pour qu'elle soit compréhensible
sans l'historique.

Règles :
- Utilise l'historique uniquement pour résoudre les références.
- N'ajoute aucun fait ou détail non présent dans la question
  ou l'historique.
- Ne réponds pas à la question.
- Si la question est déjà autonome, conserve-la.
- Retourne uniquement la question reformulée.
"""

    systeme = (
        "Tu es un assistant de reformulation de questions "
        "pour un système RAG. Tu ne réponds jamais aux questions."
    )

    resultat = llm(prompt, systeme).strip()

    return resultat if resultat else question



def construire_prompt(question: str, passages: list[dict]) -> str:
    blocs = [f"[{i}] (document {p['document_id']}, page {p['page']})\n{p['texte']}"
             for i, p in enumerate(passages, start=1)]
    return "PASSAGES :\n\n" + "\n\n".join(blocs) + f"\n\nQUESTION : {question}"


def numeros_cites(reponse: str) -> list[int]:
    """Trouve [1], [2][3], [1, 4] dans la réponse -> [1, 2, 3, 4]."""
    numeros = set()
    for groupe in re.findall(r"\[([\d,\s]+)\]", reponse):
        numeros.update(int(n) for n in re.findall(r"\d+", groupe))
    return sorted(numeros)


def _mots(texte: str) -> set[str]:
    return {m for m in re.findall(r"\w+", texte.lower()) if len(m) > 3}



def phrases_citant(reponse: str, n: int) -> str:
    """Associe les citations aux phrases correspondantes."""

    # Rattacher les citations placées après la ponctuation
    texte = re.sub(
        r"([.!?])\s*(\[\d+\](?:\s*\[\d+\])*)",
        r" \2\1",
        reponse
    )

    phrases = re.split(r"(?<=[.!?])\s+|\n+", texte)

    return " ".join(
        ph for ph in phrases
        if n in numeros_cites(ph)
    )



@lru_cache(maxsize=128)
def encoder_candidats_cache(candidats: tuple[str, ...]):
    modele = charger_modele()

    return modele.encode(
        list(candidats),
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False
    )


def lignes_les_plus_proches(
    lignes: list[dict],
    phrase: str
) -> list[dict]:
    """
    Surlignage sémantique multilingue avec BGE-M3.
    Compare la réponse avec des groupes de lignes du PDF.
    """

    if not lignes or not phrase.strip():
        return lignes

    try:
        modele = charger_modele()

        # Supprimer les marqueurs de citation
        phrase = re.sub(r"\[\d+\]", "", phrase).strip()

        if not phrase:
            return lignes

        # Construire des groupes de lignes adjacentes
        candidats = []
        indices = []

        for i in range(len(lignes)):
            for taille in (1, 2, 3):
                fin = i + taille

                if fin <= len(lignes):
                    texte = " ".join(
                        l["texte"] for l in lignes[i:fin]
                    )

                    candidats.append(texte)
                    indices.append((i, fin))
        
        # Embeddings des passages avec cache
        debut_embedding = perf_counter()

        embeddings_candidats = encoder_candidats_cache(
            tuple(candidats)
        )

        # Encoder uniquement la nouvelle affirmation
        embedding_phrase = modele.encode(
            [phrase],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )[0]

        print(
            f"[PERF EMBEDDINGS] "
            f"{perf_counter() - debut_embedding:.2f}s | "
            f"Cache : {encoder_candidats_cache.cache_info()}",
            flush=True
        )

        # Même calcul de similarité cosinus
        scores = embeddings_candidats @ embedding_phrase


        meilleur = int(scores.argmax())
        score = float(scores[meilleur])

        print(
            f"[HIGHLIGHT] Similarité : {score:.3f}",
            flush=True
        )

        # Fallback si la correspondance est trop faible
        if score < 0.40:
            return lignes

        debut, fin = indices[meilleur]

        return lignes[debut:fin]

    except Exception as e:
        print(f"[HIGHLIGHT] Erreur : {e}", flush=True)

        # Préserver le surlignage existant en cas d'erreur
        return lignes



def generer_citations(reponse: str, passages: list[dict], obtenir_positions) -> list[dict]:
    """
    Transforme chaque [n] de la réponse en citation cliquable :
    page + extrait + rectangles à surligner.
    `obtenir_positions(document_id, page)` renvoie les lignes de la page
    (format de pdf_extract.extraire_positions).
    """
    citations = []
    for n in numeros_cites(reponse):
        if not 1 <= n <= len(passages):
            continue  # Gemini a cité un numéro qui n'existe pas : on ignore
        p = passages[n - 1]
        lignes = [l for l in obtenir_positions(p["document_id"], p["page"])
                  if l["debut"] < p["fin"] and l["fin"] > p["debut"]]
        print(f"\n[CITATION {n}]", flush=True)

        print(
            "PHRASES CITEES :",
            phrases_citant(reponse, n),
            flush=True
        )

        print(
            "CHUNK SOURCE :",
            p["texte"],
            flush=True
        )
        lignes = lignes_les_plus_proches(lignes, phrases_citant(reponse, n))
        rects = [l["bbox"] for l in lignes]
        citations.append({
            "numero": n,
            "chunk_id": p.get("chunk_id"),
            "document_id": p["document_id"],
            "page": p["page"],
            "extrait": (" ".join(l["texte"] for l in lignes) or p["texte"])[:300],
            "debut": p["debut"],
            "fin": p["fin"],
            "rects": rects,
        })
    return citations

def generer_citations_precises(
    reponse: str,
    passages: list[dict],
    obtenir_positions
) -> tuple[str, list[dict]]:
    """
    Génère une citation distincte pour chaque occurrence.
    Sélection sémantique multilingue avec BGE-M3.
    Calcul des embeddings en un seul lot.
    """

    # Normaliser les formats de citations
    reponse = reponse.replace("【", "[").replace("】", "]")
    reponse = reponse.replace("［", "[").replace("］", "]")

    pattern = r"\[(\d+(?:\s*,\s*\d+)*)\]"
    occurrences = list(re.finditer(pattern, reponse))

    print(
        "[HIGHLIGHT] Citations détectées :",
        len(occurrences),
        flush=True
    )

    if not occurrences:
        return reponse, []

    modele = charger_modele()

    textes = []
    taches = []
    cache = {}
    precedent = 0

    # 1. Préparer les affirmations et les passages sources
    for occurrence in occurrences:
        contexte = reponse[precedent:occurrence.start()]
        precedent = occurrence.end()

        paragraphes = [
            p.strip()
            for p in re.split(r"\n\s*\n", contexte)
            if p.strip()
        ]

        affirmation = paragraphes[-1] if paragraphes else ""

        if not affirmation:
            affirmation = reponse[
                max(0, occurrence.start() - 500):
                occurrence.start()
            ]

        affirmation = re.sub(pattern, "", affirmation).strip()

        numeros = [
            int(n.strip())
            for n in occurrence.group(1).split(",")
        ]

        references = []

        for n in numeros:
            if not 1 <= n <= len(passages):
                continue

            p = passages[n - 1]

            if n not in cache:
                lignes = [
                    l for l in obtenir_positions(
                        p["document_id"], p["page"]
                    )
                    if l["debut"] < p["fin"]
                    and l["fin"] > p["debut"]
                ]

                candidats = []

                for i in range(len(lignes)):
                    for taille in (1, 2, 3):
                        fin = i + taille

                        if fin <= len(lignes):
                            groupe = lignes[i:fin]

                            index = len(textes)

                            textes.append(
                                " ".join(
                                    l["texte"] for l in groupe
                                )
                            )

                            candidats.append((index, groupe))

                cache[n] = (lignes, candidats)

            references.append((n, p))

        index_affirmation = len(textes)
        textes.append(affirmation)

        taches.append({
            "occurrence": occurrence,
            "index": index_affirmation,
            "references": references
        })

    # 2. Calcul groupé des embeddings
    embeddings = modele.encode(
        textes,
        batch_size=16,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False
    )

    # 3. Sélection des preuves et renumérotation
    citations = []
    morceaux = []
    position = 0

    for tache in taches:
        occurrence = tache["occurrence"]

        morceaux.append(
            reponse[position:occurrence.start()]
        )

        nouveaux_numeros = []

        for n, p in tache["references"]:
            lignes, candidats = cache[n]
            selection = lignes

            if candidats:
                indices = [c[0] for c in candidats]

                scores = (
                    embeddings[indices]
                    @ embeddings[tache["index"]]
                )

                meilleur = int(scores.argmax())
                score = float(scores[meilleur])

                if score >= 0.40:
                    selection = candidats[meilleur][1]

                print(
                    f"[HIGHLIGHT] Source {n}: {score:.3f}",
                    flush=True
                )

            numero = len(citations) + 1

            citations.append({
                "numero": numero,
                "chunk_id": p.get("chunk_id"),
                "document_id": p["document_id"],
                "page": p["page"],
                "extrait": (
                    " ".join(l["texte"] for l in selection)
                    or p["texte"]
                )[:300],
                "debut": min(
                    (l["debut"] for l in selection),
                    default=p["debut"]
                ),
                "fin": max(
                    (l["fin"] for l in selection),
                    default=p["fin"]
                ),
                "rects": [
                    l["bbox"] for l in selection
                ]
            })

            nouveaux_numeros.append(f"[{numero}]")

        morceaux.append(
            "".join(nouveaux_numeros)
            if nouveaux_numeros
            else occurrence.group(0)
        )

        position = occurrence.end()

    morceaux.append(reponse[position:])

    print(
        "[HIGHLIGHT] Citations générées :",
        len(citations),
        flush=True
    )

    return "".join(morceaux), citations



def preparer_reponse(answer: str | None, citations=None, verdict=None,
                     refusal_reason=None, passages=None,
                     verification_origin=None) -> dict:
    """Format renvoyé par POST /chat/ask (identique pour le frontend)."""
    reponse = {
        "answer": answer,
        "citations": citations or [],
        "verdict": verdict,
        "refusal_reason": refusal_reason,
        "status": "refused" if refusal_reason else "answered",
        "passages": passages or [],
    }
    if verification_origin:
        reponse["_verification_origin"] = verification_origin
    return reponse



def agent_rag(question: str, rechercher, llm, obtenir_positions,
              document_ids=None, k: int = 5, guard=None,
              fact_check=None, historique=None) -> dict:
    question = question.strip()

    if not question:
        return preparer_reponse(None, refusal_reason="Question vide.")

    # Contextual memory: rewrite follow-up questions
    question_contextuelle = reformuler_question(
        question,
        historique or [],
        llm
    )

    # 1. Hybrid retrieval using the contextualized question
    passages = rechercher(
        question_contextuelle,
        k=k,
        document_ids=document_ids
    )

    if not passages:
        return preparer_reponse(None, refusal_reason="Aucun passage trouvé dans les documents sélectionnés.")

    # 2. Hallucination Guard (Binôme 2) : AVANT la génération
    if guard:
        g = guard(question, passages)
        if g.get("status") == "insufficient":
            return preparer_reponse(None, refusal_reason=g.get("reason", "Preuves insuffisantes."),
                                    passages=passages,
                                    verification_origin="hallucination_guard")

    # 3. Génération avec Gemini
    reponse = llm(construire_prompt(question, passages), PROMPT_SYSTEME)
    if reponse.strip().upper().startswith(MOT_REFUS):
        return preparer_reponse(None, refusal_reason="Les documents ne contiennent pas cette information.",
                                passages=passages)

    # 4. Fact-Checking (Binôme 2) : APRÈS la génération, AVANT l'affichage
    verdict = None
    if fact_check:
        fc = fact_check(question, reponse, passages)
        verdict = fc.get("verdict")
        if verdict == "rejected":
            return preparer_reponse(None, verdict=verdict, passages=passages,
                                    refusal_reason="La réponse n'a pas pu être vérifiée dans les documents.")
        if verdict == "corrected" and fc.get("corrected_answer"):
            reponse = fc["corrected_answer"]

    
    # 5. Citations sémantiques par occurrence
    try:
        reponse, citations = generer_citations_precises(
            reponse,
            passages,
            obtenir_positions
        )

    except Exception as e:
        print(f"[HIGHLIGHT] Fallback : {e}", flush=True)

        citations = generer_citations(
            reponse,
            passages,
            obtenir_positions
        )

    return preparer_reponse(
        reponse,
        citations,
        verdict=verdict,
        passages=passages
    )
