// Toutes les requêtes vers FastAPI passent par ici.
export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function requete(chemin, options = {}) {
  const r = await fetch(API + chemin, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Erreur ${r.status}`);
  return data;
}

const json = (corps) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(corps),
});

export const listerDocuments = () => requete("/documents");

export const importerDocument = (fichier) => {
  const form = new FormData();
  form.append("fichier", fichier); // même nom que le paramètre FastAPI
  return requete("/documents/upload", { method: "POST", body: form });
};

export const supprimerDocument = (id) =>
  requete(`/documents/${id}`, { method: "DELETE" });

export const urlFichier = (id) => `${API}/documents/${id}/file`;



export const poserQuestion = (question, document_ids, conversation_id = null) =>
  requete("/chat/ask", json({
    question,
    document_ids,
    conversation_id
  }));



export const lancerAnalyse = (corps) => requete("/analysis/run", json(corps));

export const obtenirAnalytics = () =>
  requete("/analytics/results");

export const listerConversations = () =>
  requete("/conversations");

export const creerConversation = () =>
  requete("/conversations", {
    method: "POST"
  });

export const obtenirMessages = (conversationId) =>
  requete(
    `/conversations/${encodeURIComponent(conversationId)}/messages`
  );

export const telechargerTraductionPDF = async (
  document_id,
  langue_cible
) => {
  const response = await fetch(
    `${API}/translation/export/pdf`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id,
        langue_cible
      })
    }
  );

  if (!response.ok) {
    const erreur = await response.json().catch(() => ({}));
    throw new Error(
      typeof erreur.detail === "string"
        ? erreur.detail
        : `Erreur de traduction (${response.status})`
    );
  }

  return response.blob();
};

export async function traduireTexte(texte, langue_cible) {
  const response = await fetch(
    "http://localhost:8000/translation/text",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        texte,
        langue_cible
      })
    }
  );

  if (!response.ok) {
    const erreur = await response.json().catch(() => ({}));

    throw new Error(
      erreur.detail || "Erreur pendant la traduction du texte."
    );
  }

  const data = await response.json();

  return data.traduction;
}

export const sauvegarderEchange = ({
  conversation_id = null,
  question,
  reponse,
  citations = [],
  verdict = null,
  type_interaction = "analysis",
}) =>
  requete(
    "/conversations/save-exchange",
    json({
      conversation_id,
      question,
      reponse,
      citations,
      verdict,
      type_interaction,
    })
  );




