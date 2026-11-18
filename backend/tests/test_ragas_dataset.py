
import json
import sys
from pathlib import Path
import asyncio
import re
from openai import RateLimitError

import csv
from datetime import datetime




# Allow imports from backend/
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# Import project modules AFTER configuring the path
from graph import executer_workflow
from ragas_evaluation import ragas_llm, BGEEmbeddings
from ragas.metrics.collections import Faithfulness, AnswerRelevancy

from ragas.metrics.collections.answer_relevancy.util import (
    AnswerRelevanceInput,
    AnswerRelevanceOutput
)




# Load the evaluation dataset
chemin = BACKEND / "data" / "dataset_ragas.json"

with open(chemin, encoding="utf-8") as f:
    dataset = json.load(f)

async def evaluer_dataset():
    faithfulness = Faithfulness(llm=ragas_llm)

    relevancy = AnswerRelevancy(
        llm=ragas_llm,
        embeddings=BGEEmbeddings(),
        strictness=1
    )

    # Store evaluation results
    resultats = []

    chemin_csv = BACKEND / "data" / "ragas_results.csv"


    for test in dataset[:3]:
        print("\nEvaluating:", test["question"])

        resultat = executer_workflow({
            "requete": test["question"],
            "document_id": test["document_id"],
            "langue_cible": None
        })

        reponse = resultat["resultat"]["reponse"]

        if reponse["status"] != "answered":
            print("Skipped: RAG did not produce an answer")
            continue

        answer_original = reponse["answer"]

        # Remove PDF citation markers and Markdown formatting
        answer = re.sub(r"\[\d+\]", "", answer_original)
        answer = answer.replace("**", "").strip()

        contexts = [
            p["texte"]
            for p in reponse["passages"]
        ]

        print("Original answer:", answer_original)
        print("Cleaned answer:", answer)

        print("Generated answer:", answer)
        print("Retrieved contexts:", contexts)
        print("Verification verdict:", reponse["verdict"])


        try:
            score_f = await faithfulness.ascore(
                user_input=test["question"],
                response=answer,
                retrieved_contexts=contexts
            )

            score_r = await relevancy.ascore(
                user_input=test["question"],
                response=answer
            )

            print("Faithfulness:", round(score_f.value, 4))
            print("Answer Relevancy:", round(score_r.value, 4))

            resultats.append({
                "date": datetime.now().isoformat(timespec="seconds"),
                "question": test["question"],
                "expected_answer": test["expected_answer"],
                "generated_answer": answer,
                "faithfulness": round(score_f.value, 4),
                "answer_relevancy": round(score_r.value, 4),
                "verification_verdict": reponse["verdict"]
            })

            # Save immediately so successful results aren't lost
            with open(chemin_csv, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=resultats[0].keys())
                writer.writeheader()
                writer.writerows(resultats)

            print("Results saved to:", chemin_csv)

        except Exception as e:
            print("Evaluation failed:", str(e)[:300])
            print("Skipping this question and continuing.")
            continue

        if test["question"] == "What technology is transforming healthcare?":
            print("\n--- RAGAS DEBUG ---")
            print("Faithfulness raw:", score_f)
            print("Relevancy raw:", score_r)
            print("Faithfulness details:", vars(score_f))
            print("Relevancy details:", vars(score_r))

        await asyncio.sleep(15)

def tester_refus():
    test = dataset[3]

    print("\n--- HALLUCINATION GUARD TEST ---")
    print("Question:", test["question"])

    resultat = executer_workflow({
        "requete": test["question"],
        "document_id": test["document_id"],
        "langue_cible": None
    })

    reponse = resultat["resultat"]["reponse"]

    print("Generated answer:", reponse.get("answer"))
    print("Status:", reponse.get("status"))
    print("Verification verdict:", reponse.get("verdict"))
    print("Refusal reason:", reponse.get("refusal_reason"))

    chemin_refus = BACKEND / "data" / "guard_results.csv"

    with open(chemin_refus, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "question",
                "expected_behavior",
                "actual_status",
                "refusal_reason",
                "test_passed"
            ]
        )

        writer.writeheader()
        writer.writerow({
            "question": test["question"],
            "expected_behavior": "refused",
            "actual_status": reponse.get("status"),
            "refusal_reason": reponse.get("refusal_reason"),
            "test_passed": reponse.get("status") == "refused"
        })

    print("Guard results saved to:", chemin_refus)



if __name__ == "__main__":
    asyncio.run(evaluer_dataset())


