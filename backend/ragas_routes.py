
"""
DocuMind AI — API d'évaluation des interactions réelles.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException

import database as db

router = APIRouter(
    prefix="/ragas",
    tags=["RAGAS Live"]
)

evaluation_lock = asyncio.Lock()


# =========================================================
# 1. Récupérer les interactions enregistrées
# =========================================================

def obtenir_interactions(message_id=None):

    requete = """
        SELECT
            a.id AS message_id,
            a.conversation_id,
            a.contenu AS answer,
            a.metadata,
            a.created_at,
            q.contenu AS question,
            e.faithfulness,
            e.answer_relevancy,
            e.status AS evaluation_status,
            e.erreur,
            e.created_at AS evaluated_at

        FROM messages a

        JOIN messages q ON q.id = (
            SELECT p.id
            FROM messages p
            WHERE p.conversation_id = a.conversation_id
              AND p.id < a.id
            ORDER BY p.id DESC
            LIMIT 1
        ) AND q.role = 'user'

        LEFT JOIN ragas_evaluations e
            ON e.message_id = a.id

        WHERE a.role = 'assistant'
    """

    parametres = []

    if message_id is not None:
        requete += " AND a.id = ?"
        parametres.append(message_id)

    requete += " ORDER BY a.id DESC"

    with db.connexion() as con:
        lignes = con.execute(
            requete,
            parametres
        ).fetchall()

    interactions = []

    for ligne in lignes:

        item = dict(ligne)

        metadata = json.loads(
            item.pop("metadata") or "{}"
        )

        contextes = [
            c for c in (
                metadata.get("retrieved_contexts") or []
            )
            if isinstance(c, str) and c.strip()
        ]

        # Uniquement les réponses RAG évaluables
        if metadata.get("status") != "answered":
            continue

        if not contextes:
            continue

        if not item["question"].strip():
            continue

        if not item["answer"].strip():
            continue

        item["retrieved_contexts"] = contextes
        item["nb_contextes"] = len(contextes)

        item["evaluation_status"] = (
            item["evaluation_status"] or "pending"
        )

        interactions.append(item)

    return interactions


# =========================================================
# 2. GET — Liste des interactions évaluables
# =========================================================

@router.get("/interactions")
def lister_interactions():

    interactions = obtenir_interactions()

    # Ne pas envoyer les contextes complets au dashboard
    for item in interactions:
        item.pop("retrieved_contexts", None)

    return interactions


# =========================================================
# 3. Sauvegarder les scores dans SQLite
# =========================================================

def sauvegarder_evaluation(message_id, resultat):

    with db.connexion() as con:

        con.execute("""
            INSERT INTO ragas_evaluations (
                message_id,
                faithfulness,
                answer_relevancy,
                status,
                erreur,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(message_id) DO UPDATE SET
                faithfulness = excluded.faithfulness,
                answer_relevancy = excluded.answer_relevancy,
                status = excluded.status,
                erreur = excluded.erreur,
                created_at = excluded.created_at
        """, (
            message_id,
            resultat.get("faithfulness"),
            resultat.get("answer_relevancy"),
            resultat["status"],
            resultat.get("erreur"),
            db.maintenant()
        ))


# =========================================================
# 4. POST — Évaluer une interaction sélectionnée
# =========================================================

@router.post("/evaluate/{message_id}")
async def evaluer_message(message_id: int):

    if evaluation_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Une évaluation est déjà en cours."
        )

    async with evaluation_lock:

        interactions = obtenir_interactions(message_id)

        if not interactions:
            raise HTTPException(
                status_code=404,
                detail="Interaction non évaluable."
            )

        item = interactions[0]

        # Éviter une nouvelle consommation de tokens
        # si l'évaluation est déjà complète.
        if item["evaluation_status"] == "completed":
            return {
                "message_id": message_id,
                "faithfulness": item["faithfulness"],
                "answer_relevancy": item["answer_relevancy"],
                "status": "completed",
                "cached": True
            }

        try:
            # Import uniquement lors d'une évaluation
            from ragas_live import evaluer_interaction

            resultat = await evaluer_interaction(
                question=item["question"],
                reponse=item["answer"],
                contextes=item["retrieved_contexts"]
            )

        except Exception as exc:

            print(
                f"[RAGAS LIVE ERROR] {type(exc).__name__}",
                flush=True
            )

            resultat = {
                "faithfulness": None,
                "answer_relevancy": None,
                "status": "error",
                "erreur": "Échec de l'évaluation RAGAS."
            }

        sauvegarder_evaluation(
            message_id,
            resultat
        )

        return {
            "message_id": message_id,
            **resultat,
            "cached": False
        }
