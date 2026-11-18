
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
import os
import database as db
from translation_agent import traduire_document, LANGUES
from llm import appeler_groq
from analysis_agent import resumer_document
from pdf_extract import charger_document, extraire_pages, extraire_positions
from rag_agent import agent_rag
from verification_agent import guard_rag, fact_check_rag
from rag_pipeline import MoteurRecherche


moteur_recherche = MoteurRecherche()

Intent = Literal["question", "analyse", "traduction"]


class EtatWorkflow(TypedDict, total=False):
    requete: str
    document_id: str
    langue_cible: str
    intention: Intent
    resultat: dict
    conversation_id: str


def classifier_intention(etat: EtatWorkflow) -> dict:
    """
    Identifie l'intention de l'utilisateur.
    """

    requete = etat.get("requete", "").lower().strip()

    mots_traduction = (
        "traduis", "traduire", "traduction",
        "translate", "translation"
    )

    mots_analyse = (
        "résume", "résumer", "resume",
        "summary", "summarize",
        "analyse", "analyser", "analyze"
    )

    if any(mot in requete for mot in mots_traduction):
        intention = "traduction"

    elif any(mot in requete for mot in mots_analyse):
        intention = "analyse"

    else:
        intention = "question"

    return {"intention": intention}

def router_requete(etat: EtatWorkflow) -> str:
    """
    Sélectionne l'agent selon l'intention détectée.
    Fonction utilisée pour le routage conditionnel LangGraph.
    """

    intention = etat.get("intention")

    routes = {
        "question": "agent_rag",
        "analyse": "agent_analyse",
        "traduction": "agent_traduction"
    }

    if intention not in routes:
        raise ValueError(
            f"Intention non reconnue : {intention}"
        )

    return routes[intention]

def executer_workflow(etat_initial: EtatWorkflow) -> dict:
    """
    Construit et exécute le workflow LangGraph.
    Version initiale : agents simulés.
    """

    def agent_rag_node(etat: EtatWorkflow) -> dict:
        """
        Exécute le RAG Agent avec Hallucination Guard,
        Fact-Checking et citations PDF.
        """

        question = etat.get("requete", "").strip()
        document_id = etat.get("document_id")

        # Retrieve contextual memory from SQLite
        conversation_id = etat.get("conversation_id")

        historique = []

        if conversation_id:
            with db.connexion() as con:
                existe = con.execute(
                    "SELECT id FROM conversations WHERE id = ?",
                    (conversation_id,)
                ).fetchone()

            if existe is None:
                raise ValueError("Conversation introuvable.")

            historique = db.obtenir_messages(conversation_id)[-6:]


        if not question:
            raise ValueError("Question manquante.")

        if not document_id:
            raise ValueError("document_id manquant.")

        if not db.obtenir_document(document_id):
            raise ValueError("Document introuvable.")

        # Index chargé à la demande depuis SQLite + embeddings .npy
        if not moteur_recherche.chunks:
            moteur_recherche.recharger(db.tous_les_chunks())

        resultat_rag = agent_rag(
            question=question,
            rechercher=moteur_recherche.rechercher,
            llm=appeler_groq,
            obtenir_positions=db.obtenir_positions,
            document_ids=[document_id],
            guard=guard_rag,
            fact_check=fact_check_rag,
            historique=historique
        )


        return {
            "resultat": {
                "agent": "RAG",
                "document_id": document_id,
                "reponse": resultat_rag
            }
        }

   
    def agent_analyse(etat: EtatWorkflow) -> dict:
        """
        Exécute le véritable Analysis Agent.
        """

        document_id = etat.get("document_id")

        if not document_id:
            raise ValueError("document_id manquant.")

        document = db.obtenir_document(document_id)

        if not document:
            raise ValueError("Document introuvable.")

        chemin = document["chemin"]

        if not os.path.isfile(chemin):
            raise FileNotFoundError("Fichier PDF introuvable.")

        pdf = charger_document(chemin)

        try:
            pages = extraire_pages(pdf)
            positions = extraire_positions(pdf)
        finally:
            pdf.close()

        
        def obtenir_positions(doc_id, numero_page):
            if doc_id != document_id:
                return []

            return [
                ligne for ligne in positions
                if ligne["page"] == numero_page
            ]


        analyse = resumer_document(
            document_id=document_id,
            pages=pages,
            llm=appeler_groq,
            obtenir_positions=obtenir_positions
        )

        return {
            "resultat": {
                "agent": "Analyse",
                "document_id": document_id,
                "analyse": analyse
            }
        }


    
    def agent_traduction(etat: EtatWorkflow) -> dict:
        """
        Exécute le véritable Translation Agent.
        """

        document_id = etat.get("document_id")
        langue_cible = etat.get("langue_cible")

        if not document_id:
            raise ValueError("document_id manquant.")

        if langue_cible not in LANGUES:
            raise ValueError(
                "Langue cible invalide. Utilisez fr, en, ar ou es."
            )

        document = db.obtenir_document(document_id)

        if not document:
            raise ValueError("Document introuvable.")

        chemin = document["chemin"]

        if not os.path.isfile(chemin):
            raise FileNotFoundError(
                "Fichier PDF introuvable."
            )

        pages_traduites = traduire_document(
            chemin_pdf=chemin,
            langue_cible=langue_cible,
            llm=appeler_groq
        )

        return {
            "resultat": {
                "agent": "Traduction",
                "document_id": document_id,
                "langue_cible": langue_cible,
                "nombre_pages": len(pages_traduites),
                "pages": pages_traduites
            }
        }


    workflow = StateGraph(EtatWorkflow)

    workflow.add_node(
        "classifier_intention",
        classifier_intention
    )

    workflow.add_node("agent_rag", agent_rag_node)
    workflow.add_node("agent_analyse", agent_analyse)
    workflow.add_node("agent_traduction", agent_traduction)

    workflow.add_edge(START, "classifier_intention")

    workflow.add_conditional_edges(
        "classifier_intention",
        router_requete,
        {
            "agent_rag": "agent_rag",
            "agent_analyse": "agent_analyse",
            "agent_traduction": "agent_traduction"
        }
    )

    
    workflow.add_node("retourner_resultat", retourner_resultat)

    workflow.add_edge("agent_rag", "retourner_resultat")
    workflow.add_edge("agent_analyse", "retourner_resultat")
    workflow.add_edge("agent_traduction", "retourner_resultat")

    workflow.add_edge("retourner_resultat", END)


    graphe = workflow.compile()

    return graphe.invoke(etat_initial)

def retourner_resultat(etat: EtatWorkflow) -> dict:
    """
    Prépare la réponse finale du workflow.
    """

    resultat = etat.get("resultat")

    if resultat is None:
        raise ValueError(
            "Aucun résultat généré par le workflow."
        )

    return {
        "intention": etat.get("intention"),
        "document_id": etat.get("document_id"),
        "resultat": resultat
    }



