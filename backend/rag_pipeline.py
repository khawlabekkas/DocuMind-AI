"""
rag_pipeline.py — Chunks, index et recherche (Binôme 1, étape 2)

Chaîne complète :
  pages (pdf_extract) -> decouper_chunks -> creer_embeddings -> creer_index_faiss
                                         -> creer_index_bm25
  question -> rechercher (FAISS + BM25 fusionnés) -> meilleurs passages

FORMAT D'UN PASSAGE (à communiquer au Binôme 2) :
  {
    "chunk_id": "doc1_p3_c2",   # identifiant unique
    "document_id": "doc1",
    "page": 3,                  # commence à 1
    "texte": "...",
    "debut": 120, "fin": 900,   # offsets dans le texte de la page (surlignage)
    # ajoutés par rechercher() :
    "score_dense": 0.71,        # similarité cosinus (0 à 1) -> utile au Guard
    "score_bm25": 8.3,
    "score": 0.032              # score final de la fusion (RRF)
  }
"""

import re

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

NOM_MODELE = "BAAI/bge-m3"
_modele_cache = None  # le modèle est lourd : on le charge une seule fois


# ---------------------------------------------------------------- 1. Chunks
def decouper_chunks(pages: list[dict], document_id: str,
                    taille: int = 800, chevauchement: int = 150) -> list[dict]:
    """
    Découpe le texte de chaque page en morceaux d'environ `taille` caractères.
    - Un chunk ne traverse jamais deux pages -> chaque citation a UNE page.
    - Les chunks se chevauchent de `chevauchement` caractères, pour qu'une
      phrase coupée en fin de chunk existe en entier dans le suivant.
    - On coupe de préférence en fin de phrase, sinon sur un espace.
    """
    chunks = []
    for page in pages:
        texte = page["texte"]
        n = len(texte)
        debut, numero = 0, 0
        while debut < n:
            fin = min(debut + taille, n)
            if fin < n:
                fin = _meilleure_coupure(texte, debut, fin)

            # on retire les espaces aux bords SANS fausser les offsets
            morceau = texte[debut:fin]
            gauche = len(morceau) - len(morceau.lstrip())
            droite = len(morceau.rstrip())
            if morceau.strip():
                chunks.append({
                    "chunk_id": f"{document_id}_p{page['page']}_c{numero}",
                    "document_id": document_id,
                    "page": page["page"],
                    "texte": morceau.strip(),
                    "debut": debut + gauche,
                    "fin": debut + droite,
                })
                numero += 1

            if fin >= n:
                break
            # chunk suivant : on recule de `chevauchement`, au début d'un mot
            suivant = max(fin - chevauchement, debut + 1)
            while 0 < suivant < fin and not texte[suivant - 1].isspace():
                suivant += 1
            debut = suivant
    return chunks


def _meilleure_coupure(texte: str, debut: int, fin: int) -> int:
    """Cherche, dans la 2e moitié de la fenêtre, une fin de phrase puis un espace."""
    mini = debut + (fin - debut) // 2
    for separateurs in ([". ", ".\n", "? ", "! ", "\n"], [" "]):
        pos = max(texte.rfind(s, mini, fin) for s in separateurs)
        if pos != -1:
            return pos + 1
    return fin  # aucun séparateur : on coupe net


# ------------------------------------------------------------ 2. Embeddings
def charger_modele():
    """Charge BGE-M3 (≈2 Go, téléchargé au premier lancement)."""
    global _modele_cache
    if _modele_cache is None:
        from sentence_transformers import SentenceTransformer
        _modele_cache = SentenceTransformer(NOM_MODELE)
    return _modele_cache


def creer_embeddings(textes: list[str], modele=None,
                     taille_lot: int = 16) -> np.ndarray:
    """
    Transforme chaque texte en vecteur (1024 dimensions pour BGE-M3).
    - normalize_embeddings=True : vecteurs de longueur 1, donc
      produit scalaire = similarité cosinus.
    - taille_lot : on encode par lots (BGE-M3 est lent sur CPU).
    `modele` est injectable : en test on passe un faux modèle rapide.
    """
    modele = modele or charger_modele()
    vecteurs = modele.encode(textes, batch_size=taille_lot,
                             normalize_embeddings=True,
                             show_progress_bar=len(textes) > 50)
    return np.asarray(vecteurs, dtype="float32")  # FAISS exige du float32


# ---------------------------------------------------------- 3. Index FAISS
def creer_index_faiss(embeddings: np.ndarray) -> faiss.Index:
    """
    IndexFlatIP = recherche exacte par produit scalaire (Inner Product).
    Vecteurs normalisés -> c'est une recherche par similarité cosinus.
    La position i dans l'index correspond à chunks[i].
    """
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index


# ----------------------------------------------------------- 4. Index BM25
def tokeniser(texte: str) -> list[str]:
    """Minuscules + mots (\\w gère aussi les accents et l'arabe)."""
    return re.findall(r"\w+", texte.lower())


def creer_index_bm25(chunks: list[dict]) -> BM25Okapi:
    """BM25 = recherche par mots-clés, pondérée par la rareté des mots."""
    return BM25Okapi([tokeniser(c["texte"]) for c in chunks])


# --------------------------------------------------- 5. Recherche hybride
def rechercher(question: str, chunks: list[dict], index_faiss: faiss.Index,
               index_bm25: BM25Okapi, k: int = 5, modele=None,
               document_ids: list[str] | None = None, k_rrf: int = 60) -> list[dict]:
    """
    Recherche hybride :
      1. FAISS classe les chunks par SENS (embeddings)
      2. BM25 classe les chunks par MOTS-CLÉS
      3. On fusionne les deux classements avec la Reciprocal Rank Fusion :
            score(chunk) = 1/(k_rrf + rang_faiss) + 1/(k_rrf + rang_bm25)
    `document_ids` : on ne garde que les PDF sélectionnés par l'utilisateur.
    """
    if not chunks:
        return []
    autorises = [i for i, c in enumerate(chunks)
                 if document_ids is None or c["document_id"] in document_ids]
    if not autorises:
        return []

    # 1. Dense (FAISS) : on classe tout l'index puis on filtre.
    #    Suffisant pour quelques milliers de chunks (projet MVP).
    q = creer_embeddings([question], modele=modele)
    scores_faiss, indices = index_faiss.search(q, index_faiss.ntotal)
    dense = {int(i): float(s) for i, s in zip(indices[0], scores_faiss[0]) if i != -1}

    # 2. Mots-clés (BM25)
    scores_bm25 = index_bm25.get_scores(tokeniser(question))

    # 3. Classements limités aux documents autorisés
    rang_dense = sorted(autorises, key=lambda i: dense.get(i, -1), reverse=True)
    rang_bm25 = sorted(autorises, key=lambda i: scores_bm25[i], reverse=True)

    fusion = {i: 0.0 for i in autorises}
    for rang, i in enumerate(rang_dense, start=1):
        fusion[i] += 1 / (k_rrf + rang)
    for rang, i in enumerate(rang_bm25, start=1):
        if scores_bm25[i] > 0:  # un chunk sans aucun mot commun ne gagne rien
            fusion[i] += 1 / (k_rrf + rang)

    meilleurs = sorted(fusion, key=fusion.get, reverse=True)[:k]
    return [{**chunks[i],
             "score_dense": round(dense.get(i, 0.0), 4),
             "score_bm25": round(float(scores_bm25[i]), 4),
             "score": round(fusion[i], 6)}
            for i in meilleurs]


# ------------------------------------------- 6. Moteur (état de l'application)
class MoteurRecherche:
    """
    Garde en mémoire TOUS les chunks des PDF importés + leurs index.
    - Les embeddings de chaque PDF sont sauvegardés sur disque (.npy) :
      au redémarrage du serveur, on ne recalcule pas BGE-M3 (lent).
    - BM25 et FAISS sont reconstruits à chaque ajout/suppression
      (rapide : quelques millisecondes pour un projet de cette taille).
    """

    def __init__(self, dossier_embeddings="data/embeddings", modele=None):
        self.dossier = dossier_embeddings
        self.modele = modele
        self.chunks: list[dict] = []
        self.embeddings: dict[str, np.ndarray] = {}   # document_id -> vecteurs
        self.index_faiss = None
        self.index_bm25 = None

    def _chemin(self, document_id):
        import os
        os.makedirs(self.dossier, exist_ok=True)
        return f"{self.dossier}/{document_id}.npy"

    def _reconstruire(self):
        if not self.chunks:
            self.index_faiss = self.index_bm25 = None
            return
        # on remet les vecteurs dans le MÊME ordre que self.chunks
        vecteurs, vus = [], set()
        for c in self.chunks:
            if c["document_id"] not in vus:
                vus.add(c["document_id"])
                vecteurs.append(self.embeddings[c["document_id"]])
        self.index_faiss = creer_index_faiss(np.vstack(vecteurs))
        self.index_bm25 = creer_index_bm25(self.chunks)

    def ajouter_document(self, chunks_doc: list[dict]):
        if not chunks_doc:
            return
        doc_id = chunks_doc[0]["document_id"]
        emb = creer_embeddings([c["texte"] for c in chunks_doc], modele=self.modele)
        np.save(self._chemin(doc_id), emb)
        self.embeddings[doc_id] = emb
        self.chunks.extend(chunks_doc)
        self._reconstruire()

    def supprimer_document(self, document_id: str):
        import os
        self.chunks = [c for c in self.chunks if c["document_id"] != document_id]
        self.embeddings.pop(document_id, None)
        if os.path.exists(self._chemin(document_id)):
            os.remove(self._chemin(document_id))
        self._reconstruire()

    def recharger(self, tous_chunks: list[dict]):
        """Au démarrage : recharge les chunks (SQLite) + embeddings (.npy)."""
        import os
        self.chunks, self.embeddings = [], {}
        par_doc: dict[str, list] = {}
        for c in tous_chunks:
            par_doc.setdefault(c["document_id"], []).append(c)
        for doc_id, liste in par_doc.items():
            chemin = self._chemin(doc_id)
            if os.path.exists(chemin):
                self.embeddings[doc_id] = np.load(chemin)
            else:  # embeddings perdus : on les recalcule
                self.embeddings[doc_id] = creer_embeddings(
                    [c["texte"] for c in liste], modele=self.modele)
                np.save(chemin, self.embeddings[doc_id])
            self.chunks.extend(liste)
        self._reconstruire()

    def rechercher(self, question, k=5, document_ids=None):
        if self.index_faiss is None:
            return []
        return rechercher(question, self.chunks, self.index_faiss, self.index_bm25,
                          k=k, modele=self.modele, document_ids=document_ids)
    
# ------------------------------------------------- Baseline RAGAS
# Recherche sémantique FAISS uniquement

def rechercher_baseline(
    moteur: MoteurRecherche,
    question: str,
    k: int = 5,
    document_ids: list[str] | None = None
) -> list[dict]:

    if moteur.index_faiss is None:
        return []

    autorises = [
        i for i, chunk in enumerate(moteur.chunks)
        if document_ids is None
        or chunk["document_id"] in document_ids
    ]

    if not autorises:
        return []

    vecteur = creer_embeddings(
        [question],
        modele=moteur.modele
    )

    scores, indices = moteur.index_faiss.search(
        vecteur,
        moteur.index_faiss.ntotal
    )

    resultats = []

    for indice, score in zip(indices[0], scores[0]):
        if int(indice) not in autorises:
            continue

        resultats.append({
            **moteur.chunks[int(indice)],
            "score_dense": float(score)
        })

        if len(resultats) >= k:
            break

    return resultats

