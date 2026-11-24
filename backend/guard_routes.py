import json

from fastapi import APIRouter
import database as db

router = APIRouter(
    prefix="/guard",
    tags=["Hallucination Guard Live"]
)


@router.get("/interactions")
def obtenir_interactions_guard():

    conn = db.connexion()

    try:
        rows = conn.execute("""
            SELECT
                a.id AS message_id,
                a.contenu AS answer,
                a.metadata,
                a.created_at,
                q.contenu AS question

            FROM messages a

            JOIN messages q ON q.id = (
                SELECT p.id
                FROM messages p
                WHERE p.conversation_id = a.conversation_id
                  AND p.id < a.id
                ORDER BY p.id DESC
                LIMIT 1
            )

            WHERE a.role = 'assistant'
              AND q.role = 'user'

            ORDER BY a.id DESC
        """).fetchall()

    finally:
        conn.close()

    interactions = []

    for row in rows:

        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (ValueError, TypeError):
            continue

        if not isinstance(metadata, dict):
            continue

        status = metadata.get("status")
        origin = metadata.get("verification_origin")
        verdict = metadata.get("verdict")

        # Genuine Hallucination Guard refusal
        if (
            status == "refused"
            and origin == "hallucination_guard"
            and not verdict
        ):
            decision = "blocked"

        # Recorded RAG answer with source contexts
        elif (
            status == "answered"
            and metadata.get("retrieved_contexts")
            and verdict in ("supported", "corrected")
        ):
            decision = "answered"

        # Exclude unrelated operations and legacy refusals
        else:
            continue

        interactions.append({
            "message_id": row["message_id"],
            "question": row["question"],
            "answer": row["answer"],
            "decision": decision,
            "verdict": verdict,
            "refusal_reason": (
                metadata.get("refusal_reason")
                if decision == "blocked"
                else None
            ),
            "created_at": row["created_at"]
        })

    bloquees = sum(
        item["decision"] == "blocked"
        for item in interactions
    )

    repondues = sum(
        item["decision"] == "answered"
        for item in interactions
    )

    total = len(interactions)

    return {
        "total": total,
        "answered": repondues,
        "blocked": bloquees,
        "refusal_rate": (
            round(bloquees / total * 100, 2)
            if total > 0
            else 0
        ),
        "interactions": interactions
    }