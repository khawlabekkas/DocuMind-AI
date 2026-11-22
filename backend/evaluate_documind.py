"""Évaluation RAGAS de DocuMind AI, sans modifier l'application.

Depuis backend/ : python -X faulthandler -u evaluate_documind.py
Les résultats sont sauvegardés après chaque question dans data/ragas_results.csv.
"""

import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import torch

torch.set_num_threads(1)

import asyncio
import csv
import shutil
from datetime import datetime
from pathlib import Path
import instructor
from dotenv import load_dotenv
from openai import OpenAI
from ragas.embeddings import BaseRagasEmbedding
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, Faithfulness

load_dotenv()

DOCUMENT_ID = "c784d73bd43f"
QUESTIONS = [
    "Quel est le sujet principal du cours ?",
    "Quelles sont les quatre étapes du cycle d'un modèle génératif ?",
    "Quel est le rôle du maximum de vraisemblance dans l'apprentissage d'un modèle génératif ?",
    "Comment fonctionne la descente de gradient lors de l'optimisation d'un modèle génératif ?",
    "Quel est le rôle de l'Analyse en Composantes Principales (ACP) ?",
    "Quelle est la différence entre un modèle gaussien et un mélange de gaussiennes ?",
    "Comment les modèles génératifs apprennent-ils une distribution de probabilité ?",
    "Quels types de modèles génératifs sont présentés dans le cours ?",
    "Quel est le rôle du jeu de données dans le cycle d'un modèle génératif ?",
    "Comment un modèle génératif produit-il de nouveaux exemples après l'apprentissage ?",
]

CHAMPS = ["question", "document_id", "status", "verdict", "refusal_reason",
          "answer", "nb_contextes", "faithfulness", "answer_relevancy", "erreur"]
DESTINATION = Path(__file__).resolve().parent / "data" / "ragas_results.csv"


class BGEEmbeddings(BaseRagasEmbedding):
    """Adaptateur BGE-M3 pour la version RAGAS utilisée dans ce projet."""
    def __init__(self):
        self.modele = None

    def embed_text(self, text: str, **kwargs) -> list[float]:
        from rag_pipeline import charger_modele
        if self.modele is None:
            self.modele = charger_modele()
        return self.modele.encode(text, normalize_embeddings=True).tolist()

    async def aembed_text(self, text: str, **kwargs) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text, **kwargs)


def extraire_donnees_ragas(resultat: dict, question: str) -> dict:
    passages = resultat.get("passages") or []
    return {
        "user_input": question,
        "response": resultat.get("answer") or "",
        "retrieved_contexts": [
            p["texte"] for p in passages
            if isinstance(p, dict) and isinstance(p.get("texte"), str) and p["texte"].strip()
        ],
        "status": resultat.get("status"),
        "verdict": resultat.get("verdict"),
        "refusal_reason": resultat.get("refusal_reason"),
    }


def sauvegarder(lignes: list[dict]):
    """Écriture atomique : un arrêt pendant l'écriture ne corrompt pas le CSV existant."""
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporaire = DESTINATION.with_suffix(".tmp")
    with temporaire.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CHAMPS)
        writer.writeheader()
        writer.writerows(lignes)
    temporaire.replace(DESTINATION)


async def noter(metric, nom: str, **kwargs):
    """Un seul retry pour les erreurs RAGAS/Groq; ne relance pas le chatbot."""
    for tentative in range(2):
        try:
            resultat = await metric.ascore(**kwargs)
            valeur = resultat.value
            if valeur is None:
                raise ValueError("Score absent")
            return valeur, ""
        except Exception as exc:
            if tentative == 0:
                print(f"  {nom}: échec, nouvelle tentative dans 3 s... ({type(exc).__name__})", flush=True)
                await asyncio.sleep(3)
            else:
                return "", f"{nom}: {exc}; "


async def main():
    if not QUESTIONS or DOCUMENT_ID.startswith("REMPLACER_") or any(q.startswith("REMPLACER_") for q in QUESTIONS):
        raise ValueError("Renseigner DOCUMENT_ID et QUESTIONS dans le script.")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY introuvable dans .env")

    import database as db
    from main import etat
    from rag_agent import agent_rag
    from rag_pipeline import charger_modele

    db.initialiser()
    if not db.obtenir_document(DOCUMENT_ID):
        raise ValueError(f"Document inconnu : {DOCUMENT_ID}")
    etat.moteur.recharger(db.tous_les_chunks())
    charger_modele()

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    ragas_llm = llm_factory(
        model="openai/gpt-oss-20b", provider="openai", client=client,
        mode=instructor.Mode.JSON, temperature=0, max_completion_tokens=4096,
    )
    faithfulness = Faithfulness(llm=ragas_llm)
    relevancy = AnswerRelevancy(llm=ragas_llm, embeddings=BGEEmbeddings(), strictness=1)

    if DESTINATION.exists():
        backup = DESTINATION.with_name(
            f"ragas_results_backup_{datetime.now():%Y%m%d_%H%M%S}.csv"
        )
        shutil.copy2(DESTINATION, backup)
        print(f"Ancien CSV sauvegardé : {backup}", flush=True)

    lignes = []
    for i, question in enumerate(QUESTIONS, 1):
        print(f"\n[{i}/{len(QUESTIONS)}] {question}", flush=True)
        ligne = {
            "question": question, "document_id": DOCUMENT_ID,
            "status": "error", "verdict": "", "refusal_reason": "", "answer": "",
            "nb_contextes": 0, "faithfulness": "", "answer_relevancy": "", "erreur": "",
        }
        try:
            # Exécuter le RAG directement dans le thread principal.
            # Évite le passage de BGE-M3/PyTorch dans un worker thread.
            resultat = agent_rag(
                question,
                etat.moteur.rechercher,
                etat.llm,
                db.obtenir_positions,
                document_ids=[DOCUMENT_ID],
                guard=etat.guard,
                fact_check=etat.fact_check,
                historique=[],
            )

            donnees = extraire_donnees_ragas(resultat, question)
            ligne.update({
                "status": donnees["status"],
                "verdict": donnees["verdict"] or "",
                "refusal_reason": donnees["refusal_reason"] or "",
                "answer": donnees["response"],
                "nb_contextes": len(donnees["retrieved_contexts"]),
            })
            if donnees["status"] == "answered" and donnees["response"] and donnees["retrieved_contexts"]:
                ligne["faithfulness"], erreur = await noter(
                    faithfulness, "Faithfulness", user_input=question,
                    response=donnees["response"],
                    retrieved_contexts=donnees["retrieved_contexts"],
                )
                ligne["erreur"] += erreur
                ligne["answer_relevancy"], erreur = await noter(
                    relevancy, "AnswerRelevancy", user_input=question,
                    response=donnees["response"],
                )
                ligne["erreur"] += erreur
            elif donnees["status"] == "answered":
                ligne["erreur"] = "Réponse ou contextes manquants; "
        except Exception as exc:
            ligne["erreur"] += f"Pipeline: {exc}; "
            print(f"  Erreur pipeline : {exc}", flush=True)
        finally:
            lignes.append(ligne)
            sauvegarder(lignes)
            print(
                f"  status={ligne['status']} | faithfulness={ligne['faithfulness']} "
                f"| relevancy={ligne['answer_relevancy']} | sauvegardé",
                flush=True,
            )

    print(f"\nRésultats enregistrés : {DESTINATION}")
    for metrique in ("faithfulness", "answer_relevancy"):
        valeurs = [float(l[metrique]) for l in lignes if l[metrique] != ""]
        print(f"{metrique} : {sum(valeurs)/len(valeurs):.4f} ({len(valeurs)} évaluations)"
              if valeurs else f"{metrique} : aucun score")
    print(f"Refus : {sum(l['status'] == 'refused' for l in lignes)} / {len(lignes)}")
    print(f"Erreurs d'évaluation : {sum(bool(l['erreur']) for l in lignes)} / {len(lignes)}")


if __name__ == "__main__":
    asyncio.run(main())
