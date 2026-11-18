"""Tests de analysis_agent.py."""

import analysis_agent
from analysis_agent import analyser_document_complet, expliquer_section, resumer_document
from conftest import FauxLLM

PAGES = [{"page": 1, "texte": "Introduction du projet."},
         {"page": 2, "texte": "Methode : recherche hybride."},
         {"page": 3, "texte": "Conclusion : ca marche."}]


def positions(doc_id, page):
    return []


def test_resume_intervalle_de_pages():
    llm = FauxLLM("Point clé [1]. Autre [2].")
    res = resumer_document("d", PAGES, llm, positions, page_debut=2, page_fin=3)
    assert res["type"] == "summarize"
    assert [s["pages"] for s in res["sections"]] == [[2], [3]]
    assert [c["page"] for c in res["citations"]] == [2, 3]
    assert "Introduction" not in llm.prompts[0]          # page 1 exclue


def test_explication_section():
    recherche = lambda q, k=6, document_ids=None: [
        {"chunk_id": "x", "document_id": "d", "page": 2,
         "texte": "Methode : recherche hybride.", "debut": 0, "fin": 28}]
    res = expliquer_section("d", "méthode", recherche, FauxLLM("Simple [1]."), positions)
    assert res["type"] == "explain" and res["citations"][0]["page"] == 2


def test_analyse_complete_map_reduce(monkeypatch):
    monkeypatch.setattr(analysis_agent, "MAX_CARACTERES", 30)   # force le découpage
    llm = FauxLLM("Synthèse [1].")
    res = analyser_document_complet("d", PAGES, llm, positions)
    assert res["type"] == "full"
    assert len(llm.prompts) > 2                    # plusieurs MAP + 1 REDUCE
    assert "Fusionne" in llm.prompts[-1]


def test_pdf_sans_texte():
    res = resumer_document("d", [{"page": 1, "texte": "  "}], FauxLLM(), positions)
    assert res["citations"] == [] and "Aucun texte" in res["result"]
