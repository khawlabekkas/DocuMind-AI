"""Tests de pdf_extract.py — lancer avec : pytest -v (depuis backend/)"""

import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pdf_extract import (charger_document, extraire_pages,
                         extraire_positions, lignes_pour_intervalle)


@pytest.fixture
def pdf_test(tmp_path):
    """Crée un petit PDF de 2 pages dont on connaît le contenu exact."""
    chemin = tmp_path / "test.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Introduction a DocuMind")
    p1.insert_text((72, 100), "Le RAG cite ses sources.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Conclusion : le projet fonctionne.")
    doc.save(chemin)
    return str(chemin)


def test_extraire_pages(pdf_test):
    pages = extraire_pages(charger_document(pdf_test))
    assert len(pages) == 2
    assert pages[0]["page"] == 1
    assert "Le RAG cite ses sources." in pages[0]["texte"]
    assert "Conclusion" in pages[1]["texte"]


def test_positions_coherentes_avec_texte(pdf_test):
    doc = charger_document(pdf_test)
    pages = extraire_pages(doc)
    for pos in extraire_positions(doc):
        texte_page = pages[pos["page"] - 1]["texte"]
        # les offsets debut/fin doivent pointer exactement sur la ligne
        assert texte_page[pos["debut"]:pos["fin"]] == pos["texte"]
        x0, y0, x1, y1 = pos["bbox"]
        assert x1 > x0 and y1 > y0


def test_lignes_pour_intervalle(pdf_test):
    doc = charger_document(pdf_test)
    positions = extraire_positions(doc)
    texte = extraire_pages(doc)[0]["texte"]
    debut = texte.index("RAG")
    lignes = lignes_pour_intervalle(positions, 1, debut, debut + 3)
    assert len(lignes) == 1
    assert lignes[0]["texte"] == "Le RAG cite ses sources."


def test_fichier_invalide(tmp_path):
    faux = tmp_path / "faux.pdf"
    faux.write_text("ceci n'est pas un pdf")
    with pytest.raises(ValueError):
        charger_document(str(faux))
