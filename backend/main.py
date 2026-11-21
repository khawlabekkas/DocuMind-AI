"""
main.py — API FastAPI (routes du Binôme 1)

Lancer :  uvicorn main:app --reload
Doc interactive : http://localhost:8000/docs
"""

import os
import uuid
from contextlib import asynccontextmanager
import database as db

from dotenv import load_dotenv

load_dotenv()  # avant d'importer database (DB_PATH)

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database as db
from analysis_agent import analyser_document_complet, expliquer_section, resumer_document
from llm import appeler_gemini
from pdf_extract import charger_document, extraire_pages, extraire_positions
from rag_agent import agent_rag
from rag_pipeline import MoteurRecherche, decouper_chunks
from verification_agent import guard_rag, fact_check_rag
from translation_agent import (
    traduire_document,
    exporter_traduction_txt,
    exporter_traduction_pdf,
    exporter_pdf_mise_en_page,
    LANGUES
)
from graph import executer_workflow
from translation_agent import traduire_texte
from database import statistiques_dashboard
from pdf_fidele import exporter_pdf_fidele
from translation_agent import exporter_pdf_arabe_fidele
from pdf_arabe_layout import exporter_pdf_arabe_layout
DOSSIER_UPLOADS = os.getenv("UPLOAD_DIR", "data/uploads")



class Etat:
    """Objets partagés. Les tests remplacent moteur et llm par des faux."""

    moteur = MoteurRecherche()
    llm = staticmethod(appeler_gemini)

    # Binôme 2 — Verification Agent
    guard = staticmethod(guard_rag)
    fact_check = staticmethod(fact_check_rag)


etat = Etat()



@asynccontextmanager
async def lifespan(app):
    db.initialiser()
    os.makedirs(DOSSIER_UPLOADS, exist_ok=True)
    etat.moteur.recharger(db.tous_les_chunks())   # index reconstruit au démarrage
    yield


app = FastAPI(title="DocuMind AI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# ================================================================ Documents
def _indexer(doc_id: str, chunks: list[dict]):
    """Tâche de fond : embeddings BGE-M3 (lent) puis statut 'ready'."""
    try:
        etat.moteur.ajouter_document(chunks)
        db.changer_statut(doc_id, "ready")
    except Exception as e:
        print("Erreur d'indexation :", e)
        db.changer_statut(doc_id, "error")


@app.post("/documents/upload")
async def upload(taches: BackgroundTasks, fichier: UploadFile = File(...)):
    if not fichier.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptés.")

    doc_id = uuid.uuid4().hex[:12]
    chemin = os.path.join(DOSSIER_UPLOADS, f"{doc_id}.pdf")
    with open(chemin, "wb") as f:
        f.write(await fichier.read())

    try:
        doc = charger_document(chemin)
        pages = extraire_pages(doc)
        positions = extraire_positions(doc)
        doc.close()
    except ValueError as e:
        os.remove(chemin)
        raise HTTPException(400, str(e))

    chunks = decouper_chunks(pages, doc_id)
    if not chunks:
        os.remove(chemin)
        raise HTTPException(400, "Aucun texte trouvé (PDF scanné ? l'OCR est hors périmètre).")

    db.ajouter_document(doc_id, fichier.filename, chemin, pages, positions, chunks)
    taches.add_task(_indexer, doc_id, chunks)   # la réponse part tout de suite
    return {"document_id": doc_id, "nom": fichier.filename,
            "pages": len(pages), "index_status": "indexing"}


@app.get("/documents")
def lister():
    return db.lister_documents()


@app.get("/documents/recent")
def recents():
    return db.documents_recents()


@app.get("/documents/{doc_id}/file")
def fichier_pdf(doc_id: str):
    d = db.obtenir_document(doc_id)
    if not d:
        raise HTTPException(404, "Document introuvable.")
    return FileResponse(d["chemin"], media_type="application/pdf")


@app.delete("/documents/{doc_id}")
def supprimer(doc_id: str):
    d = db.obtenir_document(doc_id)
    if not d:
        raise HTTPException(404, "Document introuvable.")
    etat.moteur.supprimer_document(doc_id)
    db.supprimer_document(doc_id)
    if os.path.exists(d["chemin"]):
        os.remove(d["chemin"])
    return {"deleted": doc_id}


# ===================================================================== Chat
class Question(BaseModel):
    question: str
    document_ids: list[str] | None = None
    conversation_id: str | None = None



@app.post("/chat/ask")
def ask(q: Question):
    if q.document_ids is not None and len(q.document_ids) == 0:
        raise HTTPException(400, "Sélectionnez au moins un document.")

    # 1. Create a conversation or reuse an existing one
    if q.conversation_id:
        conversation_id = q.conversation_id

        with db.connexion() as con:
            existe = con.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,)
            ).fetchone()

        if existe is None:
            raise HTTPException(404, "Conversation introuvable")
    else:
        conversation = db.creer_conversation(
            titre=q.question[:60]
        )
        conversation_id = conversation["id"]

    # 2. Execute the existing RAG pipeline
    # Load previous messages from SQLite
    historique = db.obtenir_messages(conversation_id)

    # Keep the last 6 messages for contextual memory
    historique = historique[-6:]

    try:
        res = agent_rag(
            q.question,
            etat.moteur.rechercher,
            etat.llm,
            db.obtenir_positions,
            document_ids=q.document_ids,
            guard=etat.guard,
            fact_check=etat.fact_check,
            historique=historique
        )
    except Exception as e:
        raise HTTPException(502, f"Erreur du modèle : {e}")

    # 3. Save the user question and assistant response
    try:
        db.ajouter_message(
            conversation_id,
            "user",
            q.question
        )

        db.ajouter_message(
            conversation_id,
            "assistant",
            res.get("answer") or res.get("refusal_reason") or "",
            metadata={
                "status": res.get("status"),
                "citations": res.get("citations", []),
                "verdict": res.get("verdict"),
                "refusal_reason": res.get("refusal_reason")
            }
        )

    except Exception as e:
        raise HTTPException(
            500,
            f"Erreur lors de la sauvegarde des messages : {e}"
        )

    # 4. Keep the existing interaction tracking
    db.enregistrer_interaction(
        "ask",
        q.question,
        "insufficient" if res["status"] == "refused" else "answered"
    )

    # 5. Return the conversation ID to React
    return {
        **res,
        "conversation_id": conversation_id
    }


# ================================================================= Analyse
class DemandeAnalyse(BaseModel):
    document_id: str
    type: str                      # "summarize" | "explain" | "full"
    page_debut: int | None = None
    page_fin: int | None = None
    section: str | None = None  
    langue: str = "fr"   # pour "explain"


@app.post("/analysis/run")
def analyse(d: DemandeAnalyse):
    if not db.obtenir_document(d.document_id):
        raise HTTPException(404, "Document introuvable.")
    pages = db.obtenir_pages(d.document_id)
    try:
        if d.type == "summarize":
            res = resumer_document(d.document_id, pages, etat.llm, db.obtenir_positions,
                                   d.page_debut, d.page_fin)
        elif d.type == "explain":
            if not d.section:
                raise HTTPException(400, "Précisez la section ou le concept à expliquer.")
            res = expliquer_section(d.document_id, d.section, etat.moteur.rechercher,
                                    etat.llm, db.obtenir_positions)
        elif d.type == "full":
           res = analyser_document_complet(
        d.document_id,
        pages,
        etat.llm,
        db.obtenir_positions,
        langue=d.langue
    )
        else:
            raise HTTPException(400, "type doit être summarize, explain ou full.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Erreur du modèle : {e}")
    db.enregistrer_interaction(d.type, d.section or "", "answered")
    return res

# ============================================================= Translation

class DemandeTraduction(BaseModel):
    document_id: str
    langue_cible: str  # "fr" | "en" | "ar" | "es"


@app.post("/translation/run")
def traduction(d: DemandeTraduction):

    # Vérifier la langue
    if d.langue_cible not in LANGUES:
        raise HTTPException(
            400,
            "Langue non supportée. Utilisez fr, en, ar ou es."
        )

    # Récupérer le document enregistré
    document = db.obtenir_document(d.document_id)

    if not document:
        raise HTTPException(404, "Document introuvable.")

    # Vérifier que le fichier existe encore
    chemin = document["chemin"]

    if not os.path.isfile(chemin):
        raise HTTPException(404, "Fichier PDF introuvable.")

    # Traduire le PDF
    try:
        pages_traduites = traduire_document(
            chemin_pdf=chemin,
            langue_cible=d.langue_cible,
            llm=etat.llm
        )
    except Exception as e:
        raise HTTPException(
            502,
            f"Erreur de traduction : {e}"
        )

    # Retourner les résultats au frontend
    return {
        "document_id": d.document_id,
        "nom": document["nom"],
        "langue_cible": d.langue_cible,
        "nombre_pages": len(pages_traduites),
        "pages": pages_traduites
    }

class DemandeTraductionTexte(BaseModel):
    texte: str
    langue_cible: str


@app.post("/translation/text")
def traduction_texte(d: DemandeTraductionTexte):

    if d.langue_cible not in LANGUES:
        raise HTTPException(
            status_code=400,
            detail="Langue non supportée. Utilisez fr, en, ar ou es."
        )

    if not d.texte.strip():
        raise HTTPException(
            status_code=400,
            detail="Le texte à traduire est vide."
        )

    try:
        resultat = traduire_texte(
            texte=d.texte,
            langue_cible=d.langue_cible,
            llm=etat.llm
        )

        return {
            "traduction": resultat,
            "langue_cible": d.langue_cible
        }

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur de traduction : {e}"
        )


from fastapi.responses import Response


@app.post("/translation/export/txt")
def exporter_txt(d: DemandeTraduction):

    if d.langue_cible not in LANGUES:
        raise HTTPException(
            400,
            "Langue non supportée. Utilisez fr, en, ar ou es."
        )

    document = db.obtenir_document(d.document_id)

    if not document:
        raise HTTPException(404, "Document introuvable.")

    chemin = document["chemin"]

    if not os.path.isfile(chemin):
        raise HTTPException(404, "Fichier PDF introuvable.")

    try:
        pages_traduites = traduire_document(
            chemin_pdf=chemin,
            langue_cible=d.langue_cible,
            llm=etat.llm
        )

        import tempfile

        with tempfile.TemporaryDirectory() as dossier:
            chemin_txt = os.path.join(dossier, "traduction.txt")
            exporter_traduction_txt(pages_traduites, chemin_txt)

            with open(chemin_txt, "rb") as fichier:
                contenu = fichier.read()

    except Exception as e:
        raise HTTPException(502, f"Erreur d'export : {e}")

    return Response(
        content=contenu,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="traduction.txt"'
        }
    )

@app.post("/translation/export/pdf")
def exporter_pdf(d: DemandeTraduction):

    if d.langue_cible not in LANGUES:
        raise HTTPException(
            400,
            "Langue non supportée. Utilisez fr, en, ar ou es."
        )

    document = db.obtenir_document(d.document_id)

    if not document:
        raise HTTPException(404, "Document introuvable.")

    chemin = document["chemin"]

    if not os.path.isfile(chemin):
        raise HTTPException(404, "Fichier PDF introuvable.")

    try:
        import tempfile

        with tempfile.TemporaryDirectory() as dossier:
            chemin_pdf = os.path.join(dossier, "traduction.pdf")

            if d.langue_cible == "ar":
                exporter_pdf_arabe_layout(
                    chemin_original=chemin,
                    chemin_sortie=chemin_pdf,
                    llm=etat.llm
                )
            else:
                exporter_pdf_fidele(
                    chemin_original=chemin,
                    chemin_sortie=chemin_pdf,
                    langue_cible=d.langue_cible,
                    llm=etat.llm
                )

            with open(chemin_pdf, "rb") as fichier:
                contenu = fichier.read()

    except Exception as e:
        raise HTTPException(
            502,
            f"Erreur d'export PDF : {e}"
        )

    return Response(
        content=contenu,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                'attachment; filename="traduction.pdf"'
        }
    )

# ==========================================
# LANGGRAPH — MULTI-AGENT WORKFLOW
# ==========================================

class DemandeWorkflow(BaseModel):
    requete: str
    document_id: str
    langue_cible: str | None = None
    conversation_id: str | None = None


@app.post("/workflow/run")
def lancer_workflow(d: DemandeWorkflow):
    if not db.obtenir_document(d.document_id):
        raise HTTPException(
            status_code=404,
            detail="Document introuvable."
        )

    try:
        # Create or reuse a conversation
        if d.conversation_id:
            conversation_id = d.conversation_id

            with db.connexion() as con:
                existe = con.execute(
                    "SELECT id FROM conversations WHERE id = ?",
                    (conversation_id,)
                ).fetchone()

            if existe is None:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation introuvable."
                )
        else:
            conversation = db.creer_conversation(
                titre=d.requete[:60]
            )
            conversation_id = conversation["id"]

        # Execute LangGraph
        resultat = executer_workflow({
            "requete": d.requete,
            "document_id": d.document_id,
            "langue_cible": d.langue_cible,
            "conversation_id": conversation_id
        })

        # Save the interaction
        reponse_workflow = resultat.get("resultat", {})
        agent = reponse_workflow.get("agent")

        if agent == "RAG":
            details = reponse_workflow.get("reponse", {})
            contenu = (
                details.get("answer")
                or details.get("refusal_reason")
                or ""
            )
            metadata = {
                "agent": agent,
                "status": details.get("status"),
                "citations": details.get("citations", []),
                "verdict": details.get("verdict"),
                "refusal_reason": details.get("refusal_reason")
            }
        else:
            # Store a readable summary of analysis/translation results
            contenu = f"Workflow {agent} terminé."
            metadata = {
                "agent": agent,
                "resultat": reponse_workflow
            }

        db.ajouter_message(conversation_id, "user", d.requete)
        db.ajouter_message(
            conversation_id,
            "assistant",
            contenu,
            metadata=metadata
        )

        return {
            **resultat,
            "conversation_id": conversation_id
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur du workflow : {e}"
        )
    
import csv
from pathlib import Path


@app.get("/analytics/results")
def obtenir_resultats_analytics():
    dossier = Path(__file__).resolve().parent / "data"

    def lire_csv(nom):
        chemin = dossier / nom

        if not chemin.exists():
            return []

        with open(chemin, encoding="utf-8-sig", newline="") as f:
            lignes = (ligne for ligne in f if ligne.strip())
            return list(csv.DictReader(lignes))

    return {
        "ragas": lire_csv("ragas_results.csv"),
        "guard": lire_csv("guard_results.csv"),
        "comparison": lire_csv("ragas_comparison.csv")
    }

@app.get("/conversations")
def api_lister_conversations():
    return db.lister_conversations()

@app.post("/conversations")
def api_creer_conversation():
    return db.creer_conversation()

from fastapi import HTTPException

@app.get("/conversations/{conversation_id}/messages")
def api_obtenir_messages(conversation_id: str):

    with db.connexion() as con:
        conversation = con.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,)
        ).fetchone()

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation introuvable"
        )

    return db.obtenir_messages(conversation_id)

@app.post("/conversations/{conversation_id}/messages")
def api_ajouter_message(conversation_id: str, role: str, contenu: str, metadata: dict | None = None):
    with db.connexion() as con:
        conversation = con.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,)
        ).fetchone()

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation introuvable"
        )

    try:
        message_id = db.ajouter_message(conversation_id, role, contenu, metadata)
        return {"id": message_id}
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
class SauvegardeEchange(BaseModel):
    conversation_id: str | None = None
    question: str
    reponse: str
    citations: list[dict] = []
    verdict: str | None = None
    type_interaction: str = "analysis"


@app.post("/conversations/save-exchange")
def sauvegarder_echange(d: SauvegardeEchange):
    if not d.question.strip() or not d.reponse.strip():
        raise HTTPException(400, "Question et réponse obligatoires.")

    conversation_id = d.conversation_id

    if conversation_id:
        with db.connexion() as con:
            existe = con.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,)
            ).fetchone()

        if existe is None:
            raise HTTPException(404, "Conversation introuvable.")
    else:
        conversation = db.creer_conversation(
            titre=d.question[:60]
        )
        conversation_id = conversation["id"]

    db.ajouter_message(conversation_id, "user", d.question)
    db.ajouter_message(
        conversation_id,
        "assistant",
        d.reponse,
        metadata={
            "citations": d.citations,
            "verdict": d.verdict,
            "type_interaction": d.type_interaction
        }
    )

    return {"conversation_id": conversation_id, "saved": True}

    
# ------------------------------------------------- Dashboard API



@app.get("/dashboard/stats")
def obtenir_statistiques_dashboard():
    stats = db.statistiques_dashboard()

    stats["verification"] = db.statistiques_verification()

    stats["documents_recents"] = db.documents_recents(5)

    return stats












