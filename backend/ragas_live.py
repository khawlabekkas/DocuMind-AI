
"""
DocuMind AI — Évaluation RAGAS des interactions réelles.
Évalue les réponses enregistrées sans relancer le pipeline RAG.
"""

import os
import math
import asyncio

import instructor
from openai import OpenAI
from dotenv import load_dotenv
from ragas.embeddings import BaseRagasEmbedding
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy
)

load_dotenv()


# =========================================================
# 1. Adaptateur BGE-M3
# =========================================================

class BGEEmbeddings(BaseRagasEmbedding):

    def __init__(self):
        self.modele = None

    def embed_text(self, text: str, **kwargs) -> list[float]:
        from rag_pipeline import charger_modele

        if self.modele is None:
            self.modele = charger_modele()

        return self.modele.encode(
            text,
            normalize_embeddings=True
        ).tolist()

    async def aembed_text(
        self, text: str, **kwargs
    ) -> list[float]:
        return await asyncio.to_thread(
            self.embed_text,
            text,
            **kwargs
        )


# =========================================================
# 2. Calcul sécurisé des métriques
# =========================================================

async def noter(metric, nom: str, **kwargs):

    for tentative in range(2):
        try:
            resultat = await metric.ascore(**kwargs)

            valeur = float(resultat.value)

            if not math.isfinite(valeur):
                raise ValueError("Score invalide")

            return valeur, ""

        except Exception as exc:

            if tentative == 0:
                print(
                    f"[RAGAS LIVE] {nom}: nouvelle tentative",
                    flush=True
                )
                await asyncio.sleep(3)

            else:
                return None, f"{nom}: {exc}; "


# =========================================================
# 3. Évaluation d'une interaction réelle
# =========================================================

async def evaluer_interaction(
    question: str,
    reponse: str,
    contextes: list[str]
) -> dict:

    if not question.strip() or not reponse.strip():
        raise ValueError("Question ou réponse manquante.")

    if not contextes:
        raise ValueError("Contextes sources manquants.")

    fournisseur = os.getenv(
        "LLM_PROVIDER",
        "groq"
    ).strip().lower()

    if fournisseur == "openrouter":

        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = "https://openrouter.ai/api/v1"

        modele = os.getenv(
            "OPENROUTER_MODEL",
            "openai/gpt-oss-20b"
        )

    elif fournisseur == "groq":

        api_key = os.getenv("GROQ_API_KEY")
        base_url = "https://api.groq.com/openai/v1"
        modele = "openai/gpt-oss-20b"

    else:
        raise ValueError(
            f"Fournisseur LLM inconnu : {fournisseur}"
        )

    if not api_key:
        raise ValueError(
            f"Cle API manquante pour {fournisseur}"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    print(
        f"[RAGAS LIVE] Provider : {fournisseur} "
        f"| Modele : {modele}",
        flush=True
    )

    ragas_llm = llm_factory(
        model=modele,
        provider="openai",
        client=client,
        mode=instructor.Mode.JSON,
        temperature=0,
        max_completion_tokens=4096
    )

    faithfulness = Faithfulness(
        llm=ragas_llm
    )

    relevancy = AnswerRelevancy(
        llm=ragas_llm,
        embeddings=BGEEmbeddings(),
        strictness=1
    )

    print(
        f"[RAGAS LIVE] Evaluation : {question[:80]}",
        flush=True
    )

    score_fidelite, erreur_fidelite = await noter(
        faithfulness,
        "Faithfulness",
        user_input=question,
        response=reponse,
        retrieved_contexts=contextes
    )

    score_pertinence, erreur_pertinence = await noter(
        relevancy,
        "AnswerRelevancy",
        user_input=question,
        response=reponse
    )

    if (
        score_fidelite is not None
        and score_pertinence is not None
    ):
        status = "completed"

    elif (
        score_fidelite is not None
        or score_pertinence is not None
    ):
        status = "partial"

    else:
        status = "error"

    resultat = {
        "faithfulness": score_fidelite,
        "answer_relevancy": score_pertinence,
        "status": status,
        "erreur": erreur_fidelite + erreur_pertinence
    }

    print("[RAGAS LIVE]", resultat, flush=True)

    return resultat
