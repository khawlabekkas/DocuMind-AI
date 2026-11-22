
"""
llm.py — Appel à Groq pour DocuMind AI.

Toutes les fonctions utilisent llm(prompt, systeme) -> str.
Les tests peuvent injecter une fausse fonction LLM.
"""

import os
from dotenv import load_dotenv
from groq import Groq
import time
import re
from groq import Groq, RateLimitError, APIStatusError
load_dotenv()

_client = None



def appeler_groq(
    prompt: str,
    systeme: str | None = None,
    temperature: float = 0.1
) -> str:
    global _client

    if _client is None:
        cle = os.getenv("GROQ_API_KEY")

        if not cle:
            raise RuntimeError(
                "GROQ_API_KEY manquante : configurez backend/.env"
            )

        _client = Groq(api_key=cle)

    messages = []

    if systeme:
        messages.append({
            "role": "system",
            "content": systeme
        })

    messages.append({
        "role": "user",
        "content": prompt
    })

    for tentative in range(4):
        try:
            reponse = _client.chat.completions.create(
                model=os.getenv(
                    "GROQ_MODEL",
                    "openai/gpt-oss-20b"
                ),
                messages=messages,
                temperature=temperature,
                 max_completion_tokens=700,
            )

            return (
                reponse.choices[0].message.content or ""
            ).strip()

        
        except RateLimitError as e:
            message = str(e)

            match = re.search(
                r"try again in (\d+(?:\.\d+)?)s",
                message,
                re.IGNORECASE
            )

            attente = (
                float(match.group(1)) + 1
                if match
                else 20 * (tentative + 1)
            )

            print(f"Groq 429 : {message}")

            if tentative == 3:
                raise RuntimeError(
                    "Limite Groq atteinte. "
                    "Réessayez après la réinitialisation du quota."
                ) from e

            print(
                f"Nouvelle tentative dans {attente:.1f}s..."
            )
            time.sleep(attente)

        except APIStatusError as e:
            print(f"Erreur API Groq {e.status_code}: {e}")
            raise

    raise RuntimeError("Impossible de contacter Groq.")




# Compatibilité avec les imports existants du Binôme 1
appeler_gemini = appeler_groq
