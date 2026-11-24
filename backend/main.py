"""
main.py â€” API FastAPI (routes du BinÃ´me 1)

Lancer :  uvicorn main:app --reload
Doc interactive : http://localhost:8000/docs
"""

import os
import uuid
from contextlib import asynccontextmanager
import database as db
from time import perf_counter
from rag_pipeline import charger_modele
import re

from dotenv import load_dotenv
from functools import partial

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
    """Objets partagÃ©s. Les tests remplacent moteur et llm par des faux."""

    moteur = MoteurRecherche()
    llm = staticmethod(appeler_gemini)

    # BinÃ´me 2 â€” Verification Agent
    guard = staticmethod(guard_rag)
    fact_check = staticmethod(fact_check_rag)


etat = Etat()



@asynccontextmanager
async def lifespan(app):
    db.initialiser()
    os.makedirs(DOSSIER_UPLOADS, exist_ok=True)

    # Rebuild the existing document index
    etat.moteur.recharger(db.tous_les_chunks())

    # Preload BGE-M3 once before accepting requests
    print("[STARTUP] Loading BGE-M3...", flush=True)
    debut = perf_counter()

    charger_modele()

    print(
        f"[STARTUP] BGE-M3 ready in {perf_counter() - debut:.2f}s",
        flush=True
    )

    yield


app = FastAPI(title="DocuMind AI", lifespan=lifespan)
@app.middleware("http")
async def mesurer_temps_reponse(request, call_next):
    debut = perf_counter()

    try:
        response = await call_next(request)
        return response
    finally:
        duree = perf_counter() - debut

        if request.url.path in {
            "/chat/ask",
            "/analysis/run",
            "/translation/text",
            "/translation/run",
            "/translation/export/pdf",
        }:
            print(
                f"[PERFORMANCE] {request.url.path} : {duree:.2f}s",
                flush=True
            )
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# ================================================================ Documents
def _indexer(doc_id: str, chunks: list[dict]):
    """TÃ¢che de fond : embeddings BGE-M3 (lent) puis statut 'ready'."""
    try:
        etat.moteur.ajouter_document(chunks)
        db.changer_statut(doc_id, "ready")
    except Exception as e:
        print("Erreur d'indexation :", e)
        db.changer_statut(doc_id, "error")


@app.post("/documents/upload")
async def upload(taches: BackgroundTasks, fichier: UploadFile = File(...)):
    if not fichier.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Seuls les fichiers PDF sont acceptÃ©s.")

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
        raise HTTPException(400, "Aucun texte trouvÃ© (PDF scannÃ© ? l'OCR est hors pÃ©rimÃ¨tre).")

    db.ajouter_document(doc_id, fichier.filename, chemin, pages, positions, chunks)
    taches.add_task(_indexer, doc_id, chunks)   # la rÃ©ponse part tout de suite
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




def detecter_page_analyse(question: str) -> int | None:
    import re
    import unicodedata

    texte = unicodedata.normalize("NFKC", question.strip().lower())

    # Remove Arabic diacritics: حلّل -> حلل
    texte = re.sub(r"[\u064B-\u065F\u0670]", "", texte)

    nombres_arabes = {
        "الاولى": 1, "الاول": 1,
        "الثانية": 2, "الثاني": 2,
        "الثالثة": 3, "الثالث": 3,
        "الرابعة": 4, "الرابع": 4,
        "الخامسة": 5, "الخامس": 5,
        "السادسة": 6, "السادس": 6,
        "السابعة": 7, "السابع": 7,
        "الثامنة": 8, "الثامن": 8,
        "التاسعة": 9, "التاسع": 9,
        "العاشرة": 10, "العاشر": 10,
    }

    # French, English and Spanish
    motif_latin = (
        r"\b(?:analyse|analyser|analyze|analiza|analizar)\s+"
        r"(?:(?:uniquement|only|solo)\s+)?"
        r"(?:(?:la|the)\s+)?"
        r"(?:page|página|pagina)\s+(\d+)\b"
    )

    match = re.search(motif_latin, texte)
    if match:
        return int(match.group(1))

    # Arabic: حلل الصفحة 2 / حلل الصفحة الثانية
    motif_arabe = (
        r"(?:حلل|تحليل|اشرح|فسر)\s+"
        r"(?:الصفحة|صفحة)\s+"
        r"([0-9\u0660-\u0669\u06F0-\u06F9]+|[\u0621-\u064A]+)"
    )

    match = re.search(motif_arabe, texte)
    if match:
        valeur = match.group(1)

        if valeur.isdigit():
            return int(valeur)

        return nombres_arabes.get(valeur)

    return None



def detecter_resume_complet(question: str) -> bool:
    import re
    import unicodedata

    texte = unicodedata.normalize("NFKC", question.strip().lower())

    # Supprimer les voyelles/diacritiques arabes
    texte = re.sub(r"[\u064B-\u065F\u0670]", "", texte)

    # Intentions de résumé dans les quatre langues
    motifs_resume = [
        r"\b(?:résume|résumer|resume|summarize|summarise)\b",
        r"\b(?:resumen|resumir)\b",
        r"(?:لخص|تلخيص|ملخص)"
    ]

    # Expressions indiquant le document entier
    motifs_document = [
        r"\b(?:document|documento|pdf)\b",
        r"\b(?:entier|entière|complet|complète|tout|entire|whole|todo|completo)\b",
        r"(?:المستند|الوثيقة|الملف|بالكامل|كامل)"
    ]

    resume = any(re.search(m, texte) for m in motifs_resume)
    document = any(re.search(m, texte) for m in motifs_document)

    return resume and document
for question in [
    "Résume tout le document",
    "Summarize the entire document",
    "Resume todo el documento",
    "لخص المستند بالكامل",
    "لخّص المستند بالكامل"
]:
    print(
        repr(question),
        "->",
        detecter_resume_complet(question),
        flush=True
    )



def detecter_langue_question(question: str) -> str:
    texte = question.strip().lower()

    # PrioritÃ© 1 : langue explicitement demandÃ©e
    langues_explicites = [
        (
            "ar",
            r"\b(?:arabic|arabe|Ã¡rabe|Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©|Ø¹Ø±Ø¨ÙŠ|Ø¨Ø§Ù„Ø¹Ø±Ø¨ÙŠØ©)\b"
        ),
        (
            "es",
            r"\b(?:spanish|espagnol|espaÃ±ol|espagnole)\b"
        ),
        (
            "en",
            r"\b(?:english|anglais|inglÃ©s|anglaise)\b"
        ),
        (
            "fr",
            r"\b(?:french|franÃ§ais|francais|francÃ©s|franÃ§aise)\b"
        ),
    ]

    for langue, motif in langues_explicites:
        if re.search(motif, texte):
            return langue

    # PrioritÃ© 2 : langue utilisÃ©e dans la question
    if re.search(r"[\u0600-\u06FF]", texte):
        return "ar"

    if re.search(
        r"\b(?:analyze|analyse the|explain|summarize)\b",
        texte
    ):
        return "en"

    if re.search(
        r"\b(?:analiza|analizar|pÃ¡gina|pagina|explica|resume)\b",
        texte
    ):
        return "es"

    return "fr"
print(
    "TEST ESPAGNOL:",
    "page =", detecter_page_analyse("Analiza la pÃ¡gina 2"),
    "langue =", detecter_langue_question("Analiza la pÃ¡gina 2"),
    flush=True
)

def detecter_traduction_reponse(question: str) -> str | None:
    import unicodedata

    texte = unicodedata.normalize("NFKC", question.lower())
    texte = re.sub(r"[\u064B-\u065F\u0670]", "", texte)

    intentions = [
        r"\btranslat(?:e|ion)\b",
        r"\btradui(?:s|re|t)\b",
        r"\btradu(?:ce|cir|zca)\b",
        r"ترجم",
    ]

    references = [
        r"\b(?:previous|last|earlier)\s+(?:answer|response)\b",
        r"\b(?:réponse|reponse)\s+précédente\b",
        r"\b(?:respuesta)\s+anterior\b",
        r"(?:اجابتك|الاجابة|ردك)\s+(?:السابقة|السابق)",
    ]

    if not (
        any(re.search(p, texte) for p in intentions)
        and any(re.search(p, texte) for p in references)
    ):
        return None

    return detecter_langue_question(question)






@app.post("/chat/ask")
def ask(q: Question):
    if q.document_ids is not None and len(q.document_ids) == 0:
        raise HTTPException(400, "SÃ©lectionnez au moins un document.")

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
        numero_page = detecter_page_analyse(q.question)
        resume_complet = detecter_resume_complet(q.question)
        langue = detecter_langue_question(q.question)
        print(
    "DEBUG SUMMARY:",
    "resume_complet =", resume_complet,
    "langue =", langue,
    "document_ids =", q.document_ids,
    "nombre_documents =", len(q.document_ids) if q.document_ids else 0,
    flush=True
)
    
        langue_traduction = detecter_traduction_reponse(q.question)

        if langue_traduction is not None:
            dernier = next(
                (
                    m for m in reversed(historique)
                    if m.get("role") == "assistant"
                    and m.get("contenu", "").strip()
                ),
                None
            )

            if dernier is None:
                res = {
                    "answer": None,
                    "status": "refused",
                    "citations": [],
                    "verdict": None,
                    "refusal_reason": (
                        "Aucune réponse précédente à traduire."
                    )
                }
            else:
                traduction = traduire_texte(
                    texte=dernier["contenu"],
                    langue_cible=langue_traduction,
                    llm=partial(
                        etat.llm,
                        max_completion_tokens=3000
                    )
                )

                res = {
                    "answer": traduction,
                    "status": "answered",
                    "citations": [],
                    "verdict": None,
                    "refusal_reason": None
                }

        # Analyse d'une page précise
        elif (
            numero_page is not None
            and q.document_ids
            and len(q.document_ids) == 1
        ):

    
        # Analyse d'une page prÃ©cise
          if (
            numero_page is not None
            and q.document_ids
            and len(q.document_ids) == 1
        ):
            document_id = q.document_ids[0]
    
            if not db.obtenir_document(document_id):
                raise HTTPException(404, "Document introuvable.")
    
            pages = db.obtenir_pages(document_id)
    
            if numero_page < 1 or numero_page > len(pages):
                raise HTTPException(
                    400,
                    f"La page {numero_page} n'existe pas dans ce document."
                )
    
            analyse_page = analyser_document_complet(
                document_id,
                pages,
                partial(etat.llm, max_completion_tokens=3000),
                db.obtenir_positions,
                langue=langue,
                page_debut=numero_page,
                page_fin=numero_page
            )
    
            res = {
                "answer": analyse_page["result"],
                "status": "answered",
                "citations": analyse_page.get("citations", []),
                "verdict": None,
                "refusal_reason": None
            }
    
        # RÃ©sumÃ© de l'ensemble du document
        elif (
            resume_complet
            and q.document_ids
            and len(q.document_ids) == 1
        ):
            document_id = q.document_ids[0]
    
            if not db.obtenir_document(document_id):
                raise HTTPException(404, "Document introuvable.")
    
            pages = db.obtenir_pages(document_id)
    
            resume = resumer_document(
                document_id,
                pages,
                etat.llm,
                db.obtenir_positions,
                langue=langue
            )
    
            res = {
                "answer": resume["result"],
                "status": "answered",
                "citations": resume.get("citations", []),
                "verdict": None,
                "refusal_reason": None
            }
    
        # Toutes les autres questions : RAG existant
        else:
            print("DEBUG ROUTE: AGENT_RAG", flush=True)

            res = agent_rag(
                q.question,
                etat.moteur.rechercher,
                partial(etat.llm, max_completion_tokens=1800),
                db.obtenir_positions,
                document_ids=q.document_ids,
                guard=etat.guard,
                fact_check=etat.fact_check,
                historique=historique
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Erreur du modÃ¨le : {e}")

    # 3. Save the user question and assistant response
    try:
        verification_origin = res.pop("_verification_origin", None)
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
                "refusal_reason": res.get("refusal_reason"),
                **({"verification_origin": verification_origin}
                   if verification_origin == "hallucination_guard" else {})
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
            print("DEBUG ROUTE: RESUMER_DOCUMENT", flush=True)
            res = resumer_document(d.document_id, pages, etat.llm, db.obtenir_positions,
                                   d.page_debut, d.page_fin,langue=d.langue)
        
        elif d.type == "explain":
            if not d.section:
                raise HTTPException(
                    400,
                    "Précisez la section ou le concept à expliquer."
                )

            res = expliquer_section(
                d.document_id,
                d.section,
                etat.moteur.rechercher,
                partial(etat.llm, max_completion_tokens=1800),
                db.obtenir_positions
            )

        elif d.type == "full":
            res = analyser_document_complet(
                d.document_id,
                pages,
                    partial(etat.llm, max_completion_tokens=3500),
                db.obtenir_positions,
                langue=d.langue,
                page_debut=d.page_debut,
                page_fin=d.page_fin
            )
        else:
            raise HTTPException(400, "type doit Ãªtre summarize, explain ou full.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Erreur du modÃ¨le : {e}")
    db.enregistrer_interaction(d.type, d.section or "", "answered")
    return res

# ============================================================= Translation

class DemandeTraduction(BaseModel):
    document_id: str
    langue_cible: str  # "fr" | "en" | "ar" | "es"


@app.post("/translation/run")
def traduction(d: DemandeTraduction):

    # VÃ©rifier la langue
    if d.langue_cible not in LANGUES:
        raise HTTPException(
            400,
            "Langue non supportÃ©e. Utilisez fr, en, ar ou es."
        )

    # RÃ©cupÃ©rer le document enregistrÃ©
    document = db.obtenir_document(d.document_id)

    if not document:
        raise HTTPException(404, "Document introuvable.")

    # VÃ©rifier que le fichier existe encore
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

    # Retourner les rÃ©sultats au frontend
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
            detail="Langue non supportÃ©e. Utilisez fr, en, ar ou es."
        )

    if not d.texte.strip():
        raise HTTPException(
            status_code=400,
            detail="Le texte Ã  traduire est vide."
        )

    try:
        resultat = traduire_texte(
            texte=d.texte,
            langue_cible=d.langue_cible,
            llm=partial(etat.llm, max_completion_tokens=1800)
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
            "Langue non supportÃ©e. Utilisez fr, en, ar ou es."
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
            llm=partial(etat.llm, max_completion_tokens=1800)
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
            "Langue non supportÃ©e. Utilisez fr, en, ar ou es."
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
                    llm=partial(etat.llm, max_completion_tokens=1800)
                )
            else:
                exporter_pdf_fidele(
                    chemin_original=chemin,
                    chemin_sortie=chemin_pdf,
                    langue_cible=d.langue_cible,
                    llm=partial(etat.llm, max_completion_tokens=1800)
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
# LANGGRAPH â€” MULTI-AGENT WORKFLOW
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
            verification_origin = details.pop("_verification_origin", None)
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
                "refusal_reason": details.get("refusal_reason"),
                **({"verification_origin": verification_origin}
                   if verification_origin == "hallucination_guard" else {})
            }
        else:
            # Store a readable summary of analysis/translation results
            contenu = f"Workflow {agent} terminÃ©."
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

    except HTTPException:
        raise

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
        metadata = dict(metadata or {})
        metadata.pop("verification_origin", None)
        metadata.pop("_verification_origin", None)
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
        raise HTTPException(400, "Question et rÃ©ponse obligatoires.")

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
tests = [
    "Analyse la page 2",
    "Analyze page 3",
    "Ø­Ù„Ù„ Ø§Ù„ØµÙØ­Ø© 2",
    "Ø­Ù„Ù‘Ù„ Ø§Ù„ØµÙØ­Ø© Ù¢",
    "Analyze page 3 en arabic",
   "Analiza la página 4",
    "Analyse la page 2 en anglais",
]

for question in tests:
    print(
        question,
        "-> page:",
        detecter_page_analyse(question),
        "| langue:",
        detecter_langue_question(question)
    )
    print(
        "DEBUG LANGUE:",
        repr(question),
        "->",
        detecter_langue_question(question),
        flush=True
    )












