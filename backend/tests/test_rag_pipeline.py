"""Tests de rag_pipeline.py — un faux modèle remplace BGE-M3 (rapide, sans réseau)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import FauxModele
from rag_pipeline import (creer_embeddings, creer_index_bm25, creer_index_faiss,
                          decouper_chunks, rechercher, tokeniser)




PAGES_A = [
    {"page": 1, "texte": "Le chat dort sur le canapé. Il aime la chaleur."},
    {"page": 2, "texte": "La conclusion du rapport recommande un budget de 5000 euros."},
]
PAGES_B = [{"page": 1, "texte": "Le chat du voisin chasse les souris la nuit."}]


@pytest.fixture
def base():
    chunks = decouper_chunks(PAGES_A, "docA") + decouper_chunks(PAGES_B, "docB")
    modele = FauxModele()
    emb = creer_embeddings([c["texte"] for c in chunks], modele=modele)
    return chunks, creer_index_faiss(emb), creer_index_bm25(chunks), modele


def test_chunks_offsets_et_taille():
    texte = " ".join(f"Phrase numero {i} du document." for i in range(200))
    pages = [{"page": 1, "texte": texte}]
    chunks = decouper_chunks(pages, "d", taille=300, chevauchement=50)
    assert len(chunks) > 1
    for c in chunks:
        assert texte[c["debut"]:c["fin"]] == c["texte"]   # offsets exacts
        assert len(c["texte"]) <= 300
    # chevauchement : chaque chunk commence avant la fin du précédent
    for a, b in zip(chunks, chunks[1:]):
        assert b["debut"] < a["fin"]
    # tout le texte est couvert
    assert chunks[0]["debut"] == 0 and chunks[-1]["fin"] == len(texte)


def test_chunk_ne_traverse_pas_les_pages():
    chunks = decouper_chunks(PAGES_A, "docA")
    assert {c["page"] for c in chunks} == {1, 2}
    assert all("conclusion" not in c["texte"] for c in chunks if c["page"] == 1)


def test_embeddings_normalises(base):
    chunks, index, _, modele = base
    emb = creer_embeddings(["bonjour le monde"], modele=modele)
    assert emb.dtype == np.float32
    assert np.isclose(np.linalg.norm(emb[0]), 1.0)
    assert index.ntotal == len(chunks)


def test_recherche_trouve_le_bon_passage(base):
    chunks, index, bm25, modele = base
    res = rechercher("Quel budget recommande la conclusion ?", chunks, index, bm25,
                     k=2, modele=modele)
    assert res[0]["page"] == 2 and res[0]["document_id"] == "docA"
    assert {"score", "score_dense", "score_bm25"} <= res[0].keys()


def test_filtre_documents_selectionnes(base):
    chunks, index, bm25, modele = base
    res = rechercher("chat", chunks, index, bm25, k=5, modele=modele,
                     document_ids=["docB"])
    assert res and all(r["document_id"] == "docB" for r in res)
    assert rechercher("chat", chunks, index, bm25, modele=modele,
                      document_ids=["inconnu"]) == []
