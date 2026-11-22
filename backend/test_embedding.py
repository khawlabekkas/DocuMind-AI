
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import torch
torch.set_num_threads(1)

from rag_pipeline import charger_modele

print("Loading BGE-M3...", flush=True)

modele = charger_modele()

print("MODEL OK", flush=True)

vecteur = modele.encode(
    "Bonjour",
    normalize_embeddings=True
)

print("EMBEDDING OK", len(vecteur), flush=True)

print("TEST RETRIEVAL...", flush=True)

import database as db
from rag_pipeline import MoteurRecherche

db.initialiser()

moteur = MoteurRecherche()
moteur.recharger(db.tous_les_chunks())

resultats = moteur.rechercher(
    "Quel est le sujet principal du cours ?",
    k=5,
    document_ids=["c784d73bd43f"]
)

print("RETRIEVAL OK", len(resultats), flush=True)

for passage in resultats:
    print(
        "Page:",
        passage.get("page"),
        "| Score:",
        passage.get("score")
    )
