
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
from openai import OpenAI
load_dotenv()

_client = None
_client_openrouter = None



def appeler_groq(
    prompt: str,
    systeme: str | None = None,
    temperature: float = 0.1,
    max_completion_tokens: int = 700
) -> str:
    global _client

    fournisseur = os.getenv(
        "LLM_PROVIDER",
        "groq"
    ).strip().lower()

    if fournisseur == "openrouter":
        return appeler_openrouter(
            prompt=prompt,
            systeme=systeme,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens
        )

    if fournisseur != "groq":
        raise ValueError(
            f"Fournisseur LLM inconnu : {fournisseur}"
        )

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
                max_completion_tokens=max_completion_tokens,
            )
            print(
                f"[GROQ] finish_reason={reponse.choices[0].finish_reason} "
                f"tokens={reponse.usage.total_tokens if reponse.usage else 'unknown'}",
                flush=True
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
def appeler_openrouter(
    prompt: str,
    systeme: str | None = None,
    temperature: float = 0.1,
    max_completion_tokens: int = 700
) -> str:

    global _client_openrouter

    if _client_openrouter is None:
        cle = os.getenv("OPENROUTER_API_KEY")

        if not cle:
            raise RuntimeError(
                "OPENROUTER_API_KEY manquante dans .env"
            )

        _client_openrouter = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=cle,
            timeout=90.0,
            max_retries=2
        )

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

    reponse = _client_openrouter.chat.completions.create(
        model=os.getenv(
            "OPENROUTER_MODEL",
            "openai/gpt-oss-20b"
        ),
        messages=messages,
        temperature=temperature,
        max_tokens=max_completion_tokens
    )

    usage = reponse.usage

    print(
        f"[OPENROUTER] "
        f"finish_reason={reponse.choices[0].finish_reason} "
        f"tokens={usage.total_tokens if usage else 'unknown'} "
        f"cost=${getattr(usage, 'cost', 'unknown')}",
        flush=True
    )

    return (
        reponse.choices[0].message.content or ""
    ).strip()




# Compatibilité avec les imports existants du Binôme 1
appeler_gemini = appeler_groq
