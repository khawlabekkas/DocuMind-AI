"""Tests de rag_agent.py (faux LLM, fausse recherche)."""

from conftest import FauxLLM
from rag_agent import agent_rag, generer_citations, numeros_cites

PASSAGES = [
    {"chunk_id": "d_p2_c0", "document_id": "d", "page": 2,
     "texte": "Conclusion : le budget est de 5000 euros.", "debut": 0, "fin": 41},
    {"chunk_id": "d_p1_c0", "document_id": "d", "page": 1,
     "texte": "Introduction du rapport.", "debut": 0, "fin": 24},
]
LIGNES = {("d", 2): [{"texte": "Conclusion : le budget est de 5000 euros.",
                      "bbox": [72, 60, 300, 75], "debut": 0, "fin": 41}],
          ("d", 1): [{"texte": "Introduction du rapport.",
                      "bbox": [72, 60, 200, 75], "debut": 0, "fin": 24}]}


def fausse_recherche(question, k=5, document_ids=None):
    return [p for p in PASSAGES if document_ids is None or p["document_id"] in document_ids]


def positions(doc_id, page):
    return LIGNES.get((doc_id, page), [])


def test_numeros_cites():
    assert numeros_cites("A [1]. B [2][3]. C [1, 4]. Rien [x].") == [1, 2, 3, 4]


def test_reponse_avec_citation_et_rectangles():
    res = agent_rag("Quel budget ?", fausse_recherche, FauxLLM(), positions)
    assert res["status"] == "answered"
    c = res["citations"][0]
    assert c["page"] == 2 and c["rects"] == [[72, 60, 300, 75]]


def test_citation_inexistante_ignoree():
    assert generer_citations("Faux [9].", PASSAGES, positions) == []


def test_refus_si_llm_dit_insuffisant():
    res = agent_rag("Capitale du Japon ?", fausse_recherche, FauxLLM("INSUFFISANT"), positions)
    assert res["status"] == "refused" and res["answer"] is None


def test_refus_si_aucun_document():
    res = agent_rag("Quel budget ?", fausse_recherche, FauxLLM(), positions,
                    document_ids=["autre"])
    assert res["status"] == "refused"


def test_branchement_guard_et_fact_check():
    llm = FauxLLM()
    guard_non = lambda q, p: {"status": "insufficient", "reason": "Score trop bas"}
    res = agent_rag("Quel budget ?", fausse_recherche, llm, positions, guard=guard_non)
    assert res["refusal_reason"] == "Score trop bas" and llm.prompts == []  # Gemini pas appelé

    corrige = lambda q, r, p: {"verdict": "corrected", "corrected_answer": "Budget : 5000 € [1]."}
    res = agent_rag("Quel budget ?", fausse_recherche, FauxLLM(), positions, fact_check=corrige)
    assert res["answer"] == "Budget : 5000 € [1]." and res["verdict"] == "corrected"

    rejete = lambda q, r, p: {"verdict": "rejected"}
    res = agent_rag("Quel budget ?", fausse_recherche, FauxLLM(), positions, fact_check=rejete)
    assert res["status"] == "refused"


def test_surlignage_precis():
    lignes = [{"texte": "Règles de fonctionnement", "bbox": [0, 0, 1, 1], "debut": 0, "fin": 24},
              {"texte": "Le Guard intervient après la récupération des passages", "bbox": [0, 2, 1, 3], "debut": 25, "fin": 80},
              {"texte": "Technologies React Vite", "bbox": [0, 4, 1, 5], "debut": 81, "fin": 104}]
    passage = [{"chunk_id": "c", "document_id": "x", "page": 1, "texte": "...", "debut": 0, "fin": 104}]
    cit = generer_citations("Le Guard intervient après la récupération [1].", passage,
                            lambda d, p: lignes)
    assert cit[0]["rects"] == [[0, 2, 1, 3]]          # seulement la bonne ligne
