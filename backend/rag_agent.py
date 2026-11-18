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

PROMPT_SYSTEME = """Tu es DocuMind, un assistant qui répond UNIQUEMENT à partir des passages fournis.
Règles :
1. N'utilise aucune connaissance extérieure aux passages.
2. Après chaque information, cite le passage source avec son numéro entre crochets, ex. [1] ou [2][3].
3. Si les passages ne permettent pas de répondre, réponds exactement : INSUFFISANT
4. Réponds dans la langue de la question, de façon claire et concise."""

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
    """Les phrases de la réponse qui contiennent la citation [n]."""
    phrases = re.split(r"(?<=[.!?])\s+|\n+", reponse)
    return " ".join(ph for ph in phrases if n in numeros_cites(ph))


def lignes_les_plus_proches(lignes: list[dict], phrase: str) -> list[dict]:
    """
    Surlignage précis : parmi les lignes du chunk, on garde celles qui
    partagent le plus de mots avec la phrase de la réponse.
    Si aucun mot commun (ex. réponse dans une autre langue), on garde tout le chunk.
    """
    cible = _mots(phrase)
    scores = [len(_mots(l["texte"]) & cible) for l in lignes]
    if not scores or max(scores) == 0:
        return lignes
    seuil = max(scores) * 0.5
    return [l for l, s in zip(lignes, scores) if s >= seuil]


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


def preparer_reponse(answer: str | None, citations=None, verdict=None,
                     refusal_reason=None, passages=None) -> dict:
    """Format renvoyé par POST /chat/ask (identique pour le frontend)."""
    return {
        "answer": answer,
        "citations": citations or [],
        "verdict": verdict,
        "refusal_reason": refusal_reason,
        "status": "refused" if refusal_reason else "answered",
        "passages": passages or [],
    }



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
                                    passages=passages)

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

    # 5. Citations cliquables
    citations = generer_citations(reponse, passages, obtenir_positions)
    return preparer_reponse(reponse, citations, verdict=verdict, passages=passages)
