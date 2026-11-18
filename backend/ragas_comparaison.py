
from dotenv import load_dotenv

from database import tous_les_chunks
from rag_pipeline import MoteurRecherche, rechercher_baseline
from llm import appeler_groq

import asyncio

from ragas.metrics.collections import Faithfulness, AnswerRelevancy
from ragas_evaluation import ragas_llm, BGEEmbeddings


load_dotenv()

DOCUMENT_ID = "01741fc49d23"

QUESTIONS = [
    "What is artificial intelligence transforming?",
    "What technology is transforming healthcare?",
    "Does the document mention artificial intelligence?"
]


def generer_reponse(question, passages):
    contexte = "\n\n".join(
        passage["texte"] for passage in passages
    )

    prompt = f"""
Answer the question using only the provided context.
If the answer is not present, say INSUFFICIENT.
Answer in English.

Context:
{contexte}

Question:
{question}
"""

    return appeler_groq(
        prompt=prompt,
        temperature=0
    )

async def evaluer_reponse(question, reponse, passages):
    contextes = [p["texte"] for p in passages]

    faithfulness = Faithfulness(llm=ragas_llm)

    relevancy = AnswerRelevancy(
        llm=ragas_llm,
        embeddings=BGEEmbeddings(),
        strictness=1
    )

    resultat_f = await faithfulness.ascore(
        user_input=question,
        response=reponse,
        retrieved_contexts=contextes
    )

    resultat_r = await relevancy.ascore(
        user_input=question,
        response=reponse
    )

    return {
        "faithfulness": round(float(resultat_f.value), 4),
        "answer_relevancy": round(float(resultat_r.value), 4)
    }



def main():
    moteur = MoteurRecherche()
    moteur.recharger(tous_les_chunks())

    for question in QUESTIONS:
        baseline = rechercher_baseline(
            moteur,
            question,
            k=3,
            document_ids=[DOCUMENT_ID]
        )

        advanced = moteur.rechercher(
            question,
            k=3,
            document_ids=[DOCUMENT_ID]
        )

        reponse_baseline = generer_reponse(
            question,
            baseline
        )

        reponse_advanced = generer_reponse(
            question,
            advanced
        )

        scores_baseline = asyncio.run(
            evaluer_reponse(question, reponse_baseline, baseline)
        )

        scores_advanced = asyncio.run(
            evaluer_reponse(question, reponse_advanced, advanced)
        )

        print("RAGAS BASELINE:", scores_baseline)
        print("RAGAS ADVANCED:", scores_advanced)


        print("\nQUESTION:", question)
        print("BASELINE:", reponse_baseline)
        print("ADVANCED:", reponse_advanced)
    




if __name__ == "__main__":
    main()
