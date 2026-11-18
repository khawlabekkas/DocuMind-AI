"""Outils partagés par tous les tests : faux modèle d'embeddings et faux LLM."""

import sys
from pathlib import Path

import numpy as np
import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag_pipeline import tokeniser  # noqa: E402


class FauxModele:
    """Remplace BGE-M3 : vecteur = sac de mots haché (rapide, sans réseau)."""
    def encode(self, textes, batch_size=16, normalize_embeddings=True, **kw):
        vecs = np.zeros((len(textes), 64), dtype="float32")
        for i, t in enumerate(textes):
            for mot in tokeniser(t):
                vecs[i, sum(map(ord, mot)) % 64] += 1   # hash stable
        return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)


class FauxLLM:
    """Remplace Gemini : renvoie une réponse programmée et garde les prompts."""
    def __init__(self, reponse="Le budget est de 5000 euros [1]."):
        self.reponse = reponse
        self.prompts = []

    def __call__(self, prompt, systeme=None):
        self.prompts.append(prompt)
        return self.reponse(prompt) if callable(self.reponse) else self.reponse


@pytest.fixture
def faux_modele():
    return FauxModele()


@pytest.fixture
def pdf_rapport(tmp_path):
    """PDF de 2 pages au contenu connu."""
    chemin = tmp_path / "rapport.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Introduction : ce rapport presente le projet DocuMind.")
    p1.insert_text((72, 100), "Le chat dort sur le canape.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Conclusion : le budget recommande est de 5000 euros.")
    doc.save(chemin)
    return str(chemin)
