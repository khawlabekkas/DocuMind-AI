"""
database.py — Stockage SQLite (partagé avec le Binôme 2)

Tables :
  documents     : un PDF importé
  chunks        : les passages découpés (format commun avec le Binôme 2)
  positions     : la bbox de chaque ligne (pour le surlignage)
  interactions  : chaque question / analyse (pour le dashboard)
"""

import json
import os
import sqlite3
from datetime import datetime

CHEMIN_DB = os.getenv("DB_PATH", "data/documind.db")


def connexion():
    os.makedirs(os.path.dirname(CHEMIN_DB) or ".", exist_ok=True)
    con = sqlite3.connect(CHEMIN_DB)
    con.row_factory = sqlite3.Row          # lignes accessibles comme des dict
    con.execute("PRAGMA foreign_keys = ON")
    return con


def initialiser():
    with connexion() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            nom TEXT NOT NULL,
            chemin TEXT NOT NULL,
            pages INTEGER,
            index_status TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            page INTEGER, texte TEXT, debut INTEGER, fin INTEGER
        );
        CREATE TABLE IF NOT EXISTS positions (
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            page INTEGER, texte TEXT, bbox TEXT, debut INTEGER, fin INTEGER
        );
        CREATE TABLE IF NOT EXISTS pages (
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            page INTEGER, texte TEXT, largeur REAL, hauteur REAL
        );
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT, question TEXT, status TEXT, created_at TEXT
        );

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    titre TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    contenu TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id)
        REFERENCES conversations(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
ON messages(conversation_id, id);

        """)



def maintenant():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------- documents
def ajouter_document(doc_id, nom, chemin, pages, positions, chunks):
    with connexion() as con:
        con.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)",
                    (doc_id, nom, chemin, len(pages), "indexing", maintenant()))
        con.executemany("INSERT INTO pages VALUES (?,?,?,?,?)",
                        [(doc_id, p["page"], p["texte"], p["largeur"], p["hauteur"])
                         for p in pages])
        con.executemany("INSERT INTO positions VALUES (?,?,?,?,?,?)",
                        [(doc_id, p["page"], p["texte"], json.dumps(p["bbox"]),
                          p["debut"], p["fin"]) for p in positions])
        con.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?)",
                        [(c["chunk_id"], doc_id, c["page"], c["texte"],
                          c["debut"], c["fin"]) for c in chunks])


def changer_statut(doc_id, statut):
    with connexion() as con:
        con.execute("UPDATE documents SET index_status=? WHERE id=?", (statut, doc_id))


def lister_documents():
    with connexion() as con:
        lignes = con.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [dict(l) for l in lignes]


def obtenir_document(doc_id):
    with connexion() as con:
        l = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    return dict(l) if l else None


def supprimer_document(doc_id):
    with connexion() as con:
        con.execute("DELETE FROM documents WHERE id=?", (doc_id,))


# ------------------------------------------------- pages, chunks, positions
def obtenir_pages(doc_id):
    with connexion() as con:
        lignes = con.execute("SELECT * FROM pages WHERE document_id=? ORDER BY page",
                             (doc_id,)).fetchall()
    return [dict(l) for l in lignes]


def tous_les_chunks():
    with connexion() as con:
        lignes = con.execute("SELECT * FROM chunks ORDER BY rowid").fetchall()
    return [dict(l) for l in lignes]


def obtenir_positions(doc_id, page):
    with connexion() as con:
        lignes = con.execute(
            "SELECT * FROM positions WHERE document_id=? AND page=? ORDER BY debut",
            (doc_id, page)).fetchall()
    return [{**dict(l), "bbox": json.loads(l["bbox"])} for l in lignes]


# ------------------------------------------------------------ interactions
def enregistrer_interaction(type_, question, status):
    with connexion() as con:
        con.execute("INSERT INTO interactions (type, question, status, created_at) "
                    "VALUES (?,?,?,?)", (type_, question, status, maintenant()))


def documents_recents(n=5):
    """Pour le dashboard : les n derniers documents indexés."""
    with connexion() as con:
        lignes = con.execute("SELECT * FROM documents WHERE index_status='ready' "
                             "ORDER BY created_at DESC LIMIT ?", (n,)).fetchall()
    return [dict(l) for l in lignes]

# ------------------------------------------------- Conversation memory

import uuid

def creer_conversation(titre="Nouvelle conversation"):
    conversation_id = str(uuid.uuid4())
    date = maintenant()

    with connexion() as con:
        con.execute(
            """
            INSERT INTO conversations
            (id, titre, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, titre, date, date)
        )

    return {
        "id": conversation_id,
        "titre": titre,
        "created_at": date,
        "updated_at": date
    }

def ajouter_message(conversation_id, role, contenu, metadata=None):
    if role not in ("user", "assistant"):
        raise ValueError("Role must be 'user' or 'assistant'")

    with connexion() as con:
        curseur = con.execute(
            """
            INSERT INTO messages
            (conversation_id, role, contenu, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                contenu,
                json.dumps(metadata or {}, ensure_ascii=False),
                maintenant()
            )
        )

        con.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (maintenant(), conversation_id)
        )

        return curseur.lastrowid


def obtenir_messages(conversation_id):
    with connexion() as con:
        lignes = con.execute(
            """
            SELECT id, conversation_id, role, contenu,
                   metadata, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,)
        ).fetchall()

    messages = []

    for ligne in lignes:
        message = dict(ligne)
        message["metadata"] = json.loads(message["metadata"] or "{}")
        messages.append(message)

    return messages

def lister_conversations():
    with connexion() as con:
        lignes = con.execute(
            """
            SELECT id, titre, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """
        ).fetchall()

    return [dict(ligne) for ligne in lignes]

# ------------------------------------------------- Dashboard analytics

def statistiques_dashboard():
    """Retourne les KPI réels enregistrés dans SQLite."""

    with connexion() as con:

        documents = con.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]

        documents_prets = con.execute(
            "SELECT COUNT(*) FROM documents WHERE index_status = 'ready'"
        ).fetchone()[0]

        pages = con.execute(
            "SELECT COALESCE(SUM(pages), 0) FROM documents"
        ).fetchone()[0]

        conversations = con.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0]

        questions = con.execute(
            "SELECT COUNT(*) FROM messages WHERE role = 'user'"
        ).fetchone()[0]

        reponses = con.execute(
            "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
        ).fetchone()[0]

        chunks = con.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]

        interactions = con.execute(
            "SELECT COUNT(*) FROM interactions"
        ).fetchone()[0]

        interactions_par_type = con.execute("""
            SELECT type, COUNT(*) AS total
            FROM interactions
            GROUP BY type
            ORDER BY total DESC
        """).fetchall()

        interactions_par_statut = con.execute("""
            SELECT status, COUNT(*) AS total
            FROM interactions
            GROUP BY status
            ORDER BY total DESC
        """).fetchall()

        # Activité sur les 7 derniers jours (interactions)
        activite = con.execute("""
            WITH RECURSIVE jours(jour) AS (
                SELECT DATE('now', 'localtime', '-6 days')
                UNION ALL
                SELECT DATE(jour, '+1 day')
                FROM jours
                WHERE jour < DATE('now', 'localtime')
            )
            SELECT
                jours.jour,
                COUNT(i.id) AS total
            FROM jours
            LEFT JOIN interactions i
                ON DATE(i.created_at) = jours.jour
            GROUP BY jours.jour
            ORDER BY jours.jour ASC
        """).fetchall()

    return {
        "kpi": {
            "documents": documents,
            "documents_prets": documents_prets,
            "pages": pages,
            "conversations": conversations,
            "questions": questions,
            "reponses": reponses,
            "chunks": chunks,
            "interactions": interactions
        },
        "interactions_par_type": [
            dict(ligne) for ligne in interactions_par_type
        ],
        "interactions_par_statut": [
            dict(ligne) for ligne in interactions_par_statut
        ],
        "activite": [
            dict(ligne) for ligne in activite
        ]
    }

# ------------------------------------------------- Verification analytics

def statistiques_verification():
    """Statistiques des verdicts enregistrés dans les messages."""

    with connexion() as con:
        lignes = con.execute("""
            SELECT
                json_extract(metadata, '$.verdict') AS verdict,
                COUNT(*) AS total
            FROM messages
            WHERE role = 'assistant'
              AND json_valid(COALESCE(metadata, '{}'))
              AND json_extract(metadata, '$.verdict')
                  IN ('supported', 'corrected', 'rejected')
            GROUP BY json_extract(metadata, '$.verdict')
        """).fetchall()
        guard_refusals = con.execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE role = 'assistant'
              AND json_valid(COALESCE(metadata, '{}'))
              AND json_extract(metadata, '$.verification_origin')
                  = 'hallucination_guard'
              AND json_extract(metadata, '$.status') = 'refused'
              AND json_extract(metadata, '$.verdict') IS NULL
        """).fetchone()[0]

    comptes = {
        "supported": 0,
        "corrected": 0,
        "rejected": 0
    }

    for ligne in lignes:
        comptes[ligne["verdict"]] = ligne["total"]

    total = sum(comptes.values())

    pourcentage = (
        round(comptes["supported"] / total * 100, 2)
        if total > 0
        else None
    )

    return {
        "total_verifie": total,
        "supported": comptes["supported"],
        "corrected": comptes["corrected"],
        "rejected": comptes["rejected"],
        "guard_refusals": guard_refusals,
        "pourcentage_supported": pourcentage
    }





