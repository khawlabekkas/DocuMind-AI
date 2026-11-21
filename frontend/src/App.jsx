import { useEffect, useMemo, useState } from "react";
import Documents from "./components/Documents.jsx";
import Chatbot from "./components/Chatbot.jsx";
import PdfViewer from "./components/PdfViewer.jsx";
import { listerConversations, obtenirMessages } from "./api.js";
import Dashboard from "./components/Dashboard.jsx";
import { IconeBulle, IconeCerveau, IconeGraphique, IconePlus } from "./components/Icones.jsx";

// Ordre d'affichage des groupes (du plus récent au plus ancien).
const ORDRE_GROUPES_DATE = [
  "Today",
  "Yesterday",
  "Previous 7 Days",
  "Previous 30 Days",
  "Older"
];

// Détermine le libellé de groupe (ChatGPT-like) à partir d'une date réelle.
const libelleGroupeDate = (date, maintenant) => {
  const debutJour = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const jours = Math.round(
    (debutJour(maintenant) - debutJour(date)) / 86_400_000
  );

  if (jours <= 0) return "Today";
  if (jours === 1) return "Yesterday";
  if (jours <= 7) return "Previous 7 Days";
  if (jours <= 30) return "Previous 30 Days";
  return "Older";
};

// Regroupe les conversations par date réelle (updated_at/created_at).
// Si une date est manquante ou invalide, on renonce au regroupement
// plutôt que d'inventer une date, et on conserve l'ordre existant.
const grouperConversationsParDate = (conversations) => {
  const horodatageValide = (c) => {
    const valeur = c.updated_at || c.created_at;
    return valeur && !Number.isNaN(new Date(valeur).getTime());
  };

  if (!conversations.every(horodatageValide)) {
    return [{ libelle: null, conversations }];
  }

  const maintenant = new Date();
  const groupes = new Map();

  for (const conversation of conversations) {
    const date = new Date(conversation.updated_at || conversation.created_at);
    const libelle = libelleGroupeDate(date, maintenant);

    if (!groupes.has(libelle)) {
      groupes.set(libelle, []);
    }

    groupes.get(libelle).push(conversation);
  }

  return ORDRE_GROUPES_DATE.filter((libelle) => groupes.has(libelle)).map(
    (libelle) => ({ libelle, conversations: groupes.get(libelle) })
  );
};


export default function App() {

const [messagesSauvegardes, setMessagesSauvegardes] = useState([]);
const [pageActive, setPageActive] = useState("chat");
const ouvrirConversation = async (id) => {
  try {
    const historique = await obtenirMessages(id);

const documentsAssocies = [
  ...new Set(
    historique.flatMap((m) =>
      (m.metadata?.citations || [])
        .map((c) => c.document_id)
        .filter(Boolean)
    )
  )
];

console.log("PDFs retrouvés :", documentsAssocies);

setSelection(documentsAssocies);

if (documentsAssocies.length > 0) {
  setVue({
    documentId: documentsAssocies[0],
    page: 1,
    rects: []
  });
} else {
  setVue({
    documentId: null,
    page: 1,
    rects: []
  });
}


console.log(
  "DOCUMENTS ASSOCIÉS :",
  [...new Set(
    historique.flatMap((m) =>
      (m.metadata?.citations || [])
        .map((c) => c.document_id)
        .filter(Boolean)
    )
  )]
);

    console.log("HISTORIQUE COMPLET :", historique);

console.log(
  "DOCUMENTS DANS LES MESSAGES :",
  historique.map((m) => ({
    role: m.role,
    metadata: m.metadata
  }))
);

    const messages = historique.map((m) => ({
      role: m.role,
      texte: m.contenu,
      citations: m.metadata?.citations || [],
      verdict: m.metadata?.verdict || null,
      refus: m.metadata?.refusal_reason || null,
    }));

    setConversationId(id);
    setMessagesSauvegardes(messages);
    setNouveauChat((n) => n + 1);
  } catch (erreur) {
    console.error("Erreur chargement conversation :", erreur);
  }
};

  const [documents, setDocuments] = useState([]);
 
  const [conversationId, setConversationId] = useState(null);

const [nouveauChat, setNouveauChat] = useState(0);

const demarrerNouveauChat = () => {
  setConversationId(null);
  setMessagesSauvegardes([]);
  setNouveauChat((n) => n + 1);
  setVue({ documentId: null, page: 1, rects: [] });
  setViewerOuvert(false);
};


  const [conversations, setConversations] = useState([]);


useEffect(() => {
  let actif = true;

  const chargerConversations = async () => {
    try {
      const liste = await listerConversations();

      if (actif) {
        setConversations(liste);
      }
    } catch (erreur) {
      console.error(
        "Erreur chargement conversations :",
        erreur
      );
    }
  };

  chargerConversations();

  // Réessaie automatiquement toutes les 5 secondes.
  const intervalle = setInterval(
    chargerConversations,
    5000
  );

  return () => {
    actif = false;
    clearInterval(intervalle);
  };
}, []);


const handleConversationCreated = async (id) => {
  setConversationId(id);

  try {
    const liste = await listerConversations();
    setConversations(liste);
  } catch (erreur) {
    console.error("Erreur actualisation conversations :", erreur);
  }
};


  const [selection, setSelection] = useState([]); // ids des PDF cochés
  // ce que la visionneuse affiche : quel PDF, quelle page, quoi surligner
  const [vue, setVue] = useState({ documentId: null, page: 1, rects: [] });
  // visibilité de la visionneuse, indépendante du document actif
  const [viewerOuvert, setViewerOuvert] = useState(false);

  const ouvrirCitation = (c) => {
    setVue({ documentId: c.document_id, page: c.page, rects: c.rects });
    setViewerOuvert(true);
  };

  // Ouvre la visionneuse sur un document (carte pièce jointe, liste de documents).
  const ouvrirVisionneuse = (id) => {
    setVue({ documentId: id, page: 1, rects: [] });
    setViewerOuvert(true);
  };

  // Définit le document actif (pour résumé/traduction/etc.) sans ouvrir la visionneuse.
  const definirDocumentActif = (id) =>
    setVue((v) => ({ ...v, documentId: id }));

  return (
    <div
      className={
        pageActive === "dashboard"
          ? "app-dashboard"
          : `app${viewerOuvert ? "" : " viewer-ferme"}`
      }
    >

      {pageActive === "dashboard" ?( <Dashboard onRetour={() => setPageActive("chat")} />
) : (
      <>
      <aside className="colonne gauche">
        <h1 className="marque">
          <IconeCerveau className="marque-icone" taille={30} epaisseur={1.5} />
          <span>DocuMind <em>AI</em></span>
        </h1>

<button
  type="button"
  className="nouveau-chat"
  onClick={demarrerNouveauChat}
>
  <IconePlus taille={18} />
  New Chat
</button>

<div className="navigation-app">
  <button
    type="button"
    className="actif"
    onClick={() => setPageActive("chat")}
  >
    <IconeBulle taille={19} />
    Chat
  </button>

  <button
    type="button"
    onClick={() => setPageActive("dashboard")}
  >
    <IconeGraphique taille={19} />
    Dashboard
  </button>
</div>


<div className="historique-conversations">
  <h3>Recent Conversations</h3>

  {conversations.length === 0 ? (
    <p>Aucune conversation enregistrée.</p>
  ) : (
    <div className="liste-conversations">
      {conversations.map((conversation) => (
        <button
          key={conversation.id}
          type="button"
          className={
            conversationId === conversation.id
              ? "conversation-item active"
              : "conversation-item"
          }
          onClick={() => ouvrirConversation(conversation.id)}
          title={conversation.titre}
        >
          <IconeBulle taille={17} />
          <span>{conversation.titre}</span>
        </button>
      ))}
    </div>
  )}
</div>

        
      </aside>
      <main className="colonne centre">
        <Chatbot
      messagesSauvegardes={messagesSauvegardes}
  key={nouveauChat}
  selection={selection}
  documents={documents}
  setDocuments={setDocuments}
  setSelection={setSelection}
  onCitation={ouvrirCitation}
  onOuvrir={ouvrirVisionneuse}
  onImporterPDF={definirDocumentActif}
  documentOuvert={vue.documentId}
  conversationId={conversationId}
  onConversationCreated={handleConversationCreated}
/>
      </main>
      {viewerOuvert && (
      <section className="colonne droite">
        <div className="visionneuse-entete">
          <button
            type="button"
            className="fermer-visionneuse"
            onClick={() => setViewerOuvert(false)}
            title="Fermer la visionneuse"
            aria-label="Fermer la visionneuse"
          >
            ✕
          </button>
        </div>
        <PdfViewer
          documentId={vue.documentId}
          page={vue.page}
          rects={vue.rects}
          onPage={(p) => setVue({ ...vue, page: p, rects: [] })}
        />
      </section>
      )}
        </> )}
    </div>
  );
}
