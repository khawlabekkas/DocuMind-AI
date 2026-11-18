"""Test de bout en bout de l'API : upload -> question -> citation -> suppression."""

import importlib

import pytest
from fastapi.testclient import TestClient

from conftest import FauxLLM, FauxModele


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    import database, main
    importlib.reload(database)
    importlib.reload(main)
    from rag_pipeline import MoteurRecherche
    main.etat.moteur = MoteurRecherche(str(tmp_path / "emb"), modele=FauxModele())
    main.etat.llm = FauxLLM("Le budget recommandé est de 5000 euros [1].")
    with TestClient(main.app) as c:
        yield c


def test_parcours_complet(client, pdf_rapport):
    with open(pdf_rapport, "rb") as f:
        r = client.post("/documents/upload", files={"fichier": ("rapport.pdf", f, "application/pdf")})
    assert r.status_code == 200
    doc_id = r.json()["document_id"]
    assert r.json()["pages"] == 2

    docs = client.get("/documents").json()
    assert docs[0]["index_status"] == "ready"         # tâche de fond terminée

    r = client.post("/chat/ask", json={"question": "Quel budget est recommandé ?",
                                       "document_ids": [doc_id]})
    rep = r.json()
    assert rep["status"] == "answered"
    cit = rep["citations"][0]
    assert cit["page"] == 2 and cit["rects"]           # page + rectangle à surligner

    assert client.get(f"/documents/{doc_id}/file").status_code == 200
    r = client.post("/analysis/run", json={"document_id": doc_id, "type": "summarize"})
    assert r.status_code == 200 and r.json()["type"] == "summarize"

    assert client.delete(f"/documents/{doc_id}").status_code == 200
    assert client.get("/documents").json() == []


def test_upload_refuse_non_pdf(client):
    r = client.post("/documents/upload", files={"fichier": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_upload_refuse_pdf_corrompu(client):
    r = client.post("/documents/upload", files={"fichier": ("a.pdf", b"pas un pdf", "application/pdf")})
    assert r.status_code == 400


def test_aucun_document_selectionne(client):
    r = client.post("/chat/ask", json={"question": "test", "document_ids": []})
    assert r.status_code == 400
