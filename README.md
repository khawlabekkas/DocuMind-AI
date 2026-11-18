# DocuMind AI — partie Binôme 1 (RAG, Analyse, Chatbot)

## Installation (Windows / PowerShell)

### Backend
```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # puis mettre votre clé dans .env
uvicorn main:app --reload
```
- Clé Gemini : https://aistudio.google.com/apikey → `GEMINI_API_KEY=...` dans `backend/.env`
- Au premier import de PDF, BGE-M3 (~2 Go) est téléchargé : c'est normal que ce soit long.
- Documentation interactive de l'API : http://localhost:8000/docs

### Frontend (Node.js 18+)
```powershell
cd frontend
npm install
npm run dev
```
Ouvrir http://localhost:5173

### Tests
```powershell
cd backend
pytest -v
```
(les tests utilisent un faux modèle et un faux Gemini : ni réseau ni clé nécessaires)

## Scénario de démonstration
1. Importer un PDF → statut « Indexation… » puis « Prêt ».
2. Le cocher, poser une question → réponse avec numéros de citation.
3. Cliquer sur un numéro → la page s'ouvre, le passage est surligné en jaune.
4. Question hors document (« Quelle est la capitale du Japon ? ») → refus.
5. Boutons Résumer / Expliquer / Analyse complète.

## Fichiers du Binôme 1
| Fichier | Rôle |
|---|---|
| `backend/pdf_extract.py` | Lecture PDF : texte par page + position (bbox) de chaque ligne |
| `backend/rag_pipeline.py` | Chunks, embeddings BGE-M3, FAISS, BM25, recherche hybride (RRF) |
| `backend/rag_agent.py` | Agent RAG : prompt, Gemini, citations, surlignage, branchements Binôme 2 |
| `backend/analysis_agent.py` | Résumé, explication, analyse complète (map-reduce) |
| `backend/llm.py` | Appel unique à Gemini |
| `backend/database.py` | SQLite (documents, pages, chunks, positions, interactions) |
| `backend/main.py` | Routes FastAPI |
| `frontend/src/components/Documents.jsx` | Importer, lister, sélectionner, supprimer |
| `frontend/src/components/Chatbot.jsx` | Chatbot unique, citations cliquables |
| `frontend/src/components/PdfViewer.jsx` | Affichage PDF.js + surlignage |

## Pour le Binôme 2
Brancher les agents de vérification dans `main.py` :
```python
from verification_agent import hallucination_guard, fact_checking
etat.guard = hallucination_guard        # (question, passages) -> {"status", "reason"}
etat.fact_check = fact_checking         # (question, reponse, passages) -> {"verdict", "corrected_answer"}
```
Format d'un passage : voir l'en-tête de `rag_pipeline.py`.
