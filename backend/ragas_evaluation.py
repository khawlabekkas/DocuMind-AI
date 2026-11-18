
import os
import instructor

from dotenv import load_dotenv
from openai import OpenAI
from ragas.llms import llm_factory

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY introuvable dans .env")



import instructor
from openai import OpenAI
from ragas.llms import llm_factory

# OpenAI-compatible Groq client
client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1"
)

# RAGAS with Instructor tool-calling mode
ragas_llm = llm_factory(
    model="openai/gpt-oss-20b",
    provider="openai",
    client=client,
    mode=instructor.Mode.JSON,
    temperature=0,
    max_completion_tokens=4096
)


print("RAGAS + Groq configured successfully!")

import asyncio
from ragas.metrics.collections import Faithfulness

async def tester_faithfulness():
    metric = Faithfulness(llm=ragas_llm)

    resultat = await metric.ascore(
        user_input="What is artificial intelligence transforming?",
        response="Artificial intelligence is transforming healthcare.",
        retrieved_contexts=[
            "Artificial intelligence is transforming healthcare."
        ]
    )

    print("Faithfulness score:", resultat.value)

import asyncio
from ragas.embeddings import BaseRagasEmbedding
from rag_pipeline import charger_modele


class BGEEmbeddings(BaseRagasEmbedding):
    """Adaptateur BGE-M3 pour RAGAS 0.4.4."""

    def __init__(self):
        self.modele = None

    def embed_text(self, text: str, **kwargs) -> list[float]:
        if self.modele is None:
            self.modele = charger_modele()

        vecteur = self.modele.encode(
            text,
            normalize_embeddings=True
        )

        return vecteur.tolist()

    async def aembed_text(self, text: str, **kwargs) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text, **kwargs)
    
from ragas.metrics.collections import AnswerRelevancy


async def tester_answer_relevancy():
    metric = AnswerRelevancy(
        llm=ragas_llm,
        embeddings=BGEEmbeddings(),
        strictness=1
    )

    resultat = await metric.ascore(
        user_input="What is artificial intelligence transforming?",
        response="Artificial intelligence is transforming healthcare."
    )

    print("Answer Relevancy score:", resultat.value)

# Questions communes aux deux configurations
# Les réponses de référence seront utilisées
# pour vérifier la cohérence des résultats.

JEU_EVALUATION = [
    {
        "question": "What is artificial intelligence transforming?",
        "reference": "Healthcare."
    },
    {
        "question": "What technology is transforming healthcare?",
        "reference": "Artificial intelligence."
    },
    {
        "question": "Does the document mention artificial intelligence?",
        "reference": "Yes."
    }
]





if __name__ == "__main__":
    asyncio.run(tester_faithfulness())
    asyncio.run(tester_answer_relevancy())

