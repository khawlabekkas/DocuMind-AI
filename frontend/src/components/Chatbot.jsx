import { useEffect, useRef, useState } from "react";
import Documents from "./Documents.jsx";




import {
  traduireTexte,
  lancerAnalyse,
  poserQuestion,
  obtenirMessages,
  importerDocument,
  listerDocuments,
  telechargerTraductionPDF
} from "../api.js";



// Transforme "texte [1] suite [2]" en texte + boutons cliquables
function TexteCite({ texte, citations, onCitation }) {
  const morceaux = texte.split(/(\[\d+(?:\s*,\s*\d+)*\])/g);
  return (
    <p className="texte">
      {morceaux.map((m, i) => {
        const nums = m.match(/^\[([\d,\s]+)\]$/);
        if (!nums) return <span key={i}>{m}</span>;
        return nums[1].split(",").map((n) => {
          const c = citations.find((x) => x.numero === Number(n.trim()));
          return c ? (
            <button key={i + n} className="pastille" onClick={() => onCitation(c)}
                    title={`Page ${c.page}`}>{n.trim()}</button>
          ) : null;
        });
      })}
    </p>
  );
}

function Message({ m, onCitation, nomDocument }) {
  if (m.role === "user") return <div className="message user">{m.texte}</div>;
  if (m.role === "erreur") return <div className="message erreur">{m.texte}</div>;
  if (m.refus)
    return <div className="message refus">🛡️ Je ne peux pas répondre : {m.refus}</div>;
  return (
    <div className="message assistant">
      <TexteCite texte={m.texte} citations={m.citations} onCitation={onCitation} />
      {m.verdict && <span className={`verdict ${m.verdict}`}>Vérification : {m.verdict}</span>}
      {m.citations.length > 0 && (
        <div className="sources">
          <strong>Sources</strong>
          {m.citations.map((c) => (
            <button key={c.numero} className="source" onClick={() => onCitation(c)}>
              <b>[{c.numero}]</b> {nomDocument(c.document_id)} — page {c.page}
              <small>« {c.extrait.slice(0, 140)}… »</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}



export default function Chatbot({
  messagesSauvegardes,
  selection,
  documents,
  setDocuments,
  setSelection,
  onCitation,
  onOuvrir,
  documentOuvert,
  conversationId,
  onConversationCreated
}) {


  const [messages, setMessages] = useState(messagesSauvegardes);
  const [question, setQuestion] = useState("");
  const [menuDocuments, setMenuDocuments] = useState(false);
  const [afficherDocuments, setAfficherDocuments] = useState(false);
  const [attente, setAttente] = useState(false);
  const bas = useRef(null);

const inputPDF = useRef(null);

const importerPDF = async (e) => {
  const fichier = e.target.files?.[0];
  if (!fichier) return;

  try {
    const resultat = await importerDocument(fichier);

    setSelection((precedent) => [
      ...new Set([...precedent, resultat.document_id])
    ]);

    onOuvrir(resultat.document_id);

    const liste = await listerDocuments();
    setDocuments(liste);

    setMenuDocuments(false);
    setAfficherDocuments(false);
  } catch (erreur) {
    alert("Erreur import PDF : " + erreur.message);
  } finally {
    e.target.value = "";
  }
};


useEffect(() => {
  if (!conversationId) {
    setMessages([]);
    return;
  }

  let actif = true;

  obtenirMessages(conversationId)
    .then((historique) => {
      if (!actif) return;

      const messagesFormates = historique.map((m) => ({
        role: m.role,
        texte: m.contenu,
        citations: m.metadata?.citations || [],
        verdict: m.metadata?.verdict || null,
        refus: m.metadata?.refusal_reason || null
      }));

      setMessages(messagesFormates);
    })
    .catch((error) => {
      if (actif) {
        console.error("Erreur chargement historique :", error);
      }
    });

  return () => {
    actif = false;
  };
}, [conversationId]);


  useEffect(() => {
    bas.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, attente]);

  const nomDocument = (id) => documents.find((d) => d.id === id)?.nom || id;
  const ajouter = (m) => setMessages((ms) => [...ms, m]);

  const executer = async (texteUtilisateur, appel) => {
    ajouter({ role: "user", texte: texteUtilisateur });
    setAttente(true);
    try {
      const r = await appel();

console.log("DOCUMIND API RESPONSE:", r);


if (r.conversation_id && onConversationCreated) {
  onConversationCreated(r.conversation_id);
}

      // /chat/ask renvoie "answer", /analysis/run renvoie "result"
      ajouter({
        role: "assistant",
        texte: r.answer ?? r.result ?? "",
        citations: r.citations || [],
        verdict: r.verdict,
        refus: r.refusal_reason,
      });
    } catch (e) {
      ajouter({ role: "erreur", texte: e.message });
    } finally {
      setAttente(false);
    }
  };


const detecterTraduction = (texte) => {
  const q = texte.toLowerCase().trim();

  // 1. Détecter la langue demandée (optionnelle pour le résumé)
  let langue = null;

  if (/\b(français|francais|french)\b/i.test(q)) langue = "fr";
  else if (/\b(anglais|english)\b/i.test(q)) langue = "en";
  else if (/\b(arabe|arabic)\b/i.test(q)) langue = "ar";
  else if (/\b(espagnol|spanish)\b/i.test(q)) langue = "es";

  // 2. Détecter les intentions
  const traduction =
    /\b(tradui\w*|traduction|translate|translation)\b/i.test(q);

  const explication =
    /\b(expliqu\w*|explication|explain\w*)\b/i.test(q);

  const resume =
    /\b(résum\w*|resum\w*|summari\w*|summariz\w*|summary)\b/i.test(q);

  // 3. Détecter une référence à une réponse précédente
  const precedent =
    /\b(ta|ton|your|previous|last|dernière|dernier)\b/i.test(q) &&
    /\b(réponse|reponse|explication|answer|response|message|summary|résumé)\b/i.test(q);

  // 4. Traduction du PDF complet
  const documentComplet =
    traduction &&
    !precedent &&
    /\b(document|pdf|fichier|file)\b/i.test(q) &&
    /\b(tout|entier|entire|whole|complet|complete|full)\b/i.test(q);

  if (documentComplet && langue) {
    return { type: "pdf", langue };
  }

  // 5. Traduction de la réponse précédente
  if (precedent && traduction && langue) {
    return { type: "message", langue };
  }

  // 6. Résumé du document (langue facultative)
  if (resume) {
    return { type: "resume", langue };
  }

  // 7. Explication
  if (explication) {
    return { type: "explication", langue };
  }

  // 8. Autres traductions
  if (traduction && langue) {
    return { type: "texte", langue };
  }

  return null;
};

  
const envoyer = async (e) => {
  e.preventDefault();

  const q = question.trim();
  if (!q || attente) return;

  
const intention = detecterTraduction(q);
setQuestion("");


console.log("DOCUMENTS SÉLECTIONNÉS :", selection);
console.log("NOMBRE DE DOCUMENTS :", selection.length);


  

if (intention?.type === "pdf") {
  const langue = intention.langue;

  const document_id =
    selection.length === 1
      ? selection[0]
      : selection.length === 0
        ? documentOuvert
        : null;

  if (!document_id) {
    ajouter({
      role: "erreur",
      texte: "Ouvrez un PDF ou sélectionnez un seul document à traduire."
    });
    return;
  }


    ajouter({ role: "user", texte: q });
    setAttente(true);

    try {
      const blob = await telechargerTraductionPDF(
  document_id,
  langue
);

      const url = URL.createObjectURL(blob);
      const lien = document.createElement("a");

      lien.href = url;
      lien.download = `document_traduit_${langue}.pdf`;
      document.body.appendChild(lien);
      lien.click();
      lien.remove();

      setTimeout(() => URL.revokeObjectURL(url), 60000);

      ajouter({
        role: "assistant",
        texte: "Traduction terminée ! Le PDF traduit a été téléchargé.",
        citations: [],
        verdict: null,
        refus: null
      });
    } catch (erreur) {
      ajouter({
        role: "erreur",
        texte: `Erreur de traduction : ${erreur.message}`
      });
    } finally {
      setAttente(false);
    }

    return;
  }


if (intention?.type === "resume") {

console.log("DEBUG RÉSUMÉ :", {
  selection,
  documentOuvert,
  nombreDocumentsSelectionnes: selection.length
});

  
const document_id =
  documentOuvert ||
  (selection.length === 1 ? selection[0] : null);


  ajouter({ role: "user", texte: q });

  if (!document_id) {
    ajouter({
      role: "erreur",
      texte: "Ouvrez un PDF ou sélectionnez un seul document à résumer."
    });
    return;
  }

  setAttente(true);

  try {
    const resultat = await lancerAnalyse({
      document_id,
      type: "summarize",
      section: null,
      page_debut: null,
      page_fin: null
    });

    let resume = resultat.result;

    // Translate the summary if a target language was requested.
    if (intention.langue) {
      resume = await traduireTexte(
        resume,
        intention.langue
      );
    }

    ajouter({
      role: "assistant",
      texte: resume,
      citations: resultat.citations || [],
      verdict: null,
      refus: null
    });

  } catch (erreur) {
    ajouter({
      role: "erreur",
      texte: `Erreur de résumé : ${erreur.message}`
    });
  } finally {
    setAttente(false);
  }

  return;
}

if (intention?.type === "message") {
  const dernierMessage = [...messages]
    .reverse()
    .find(
      (message) =>
        message.role === "assistant" &&
        typeof message.texte === "string" &&
        message.texte.trim()
    );

  ajouter({ role: "user", texte: q });

  if (!dernierMessage) {
    ajouter({
      role: "erreur",
      texte: "Aucune réponse précédente à traduire."
    });
    return;
  }

  setAttente(true);

  try {
    const traduction = await traduireTexte(
      dernierMessage.texte,
      intention.langue
    );

    ajouter({
      role: "assistant",
      texte: traduction,
      citations: [],
      verdict: null,
      refus: null
    });
  } catch (erreur) {
    ajouter({
      role: "erreur",
      texte: `Erreur de traduction : ${erreur.message}`
    });
  } finally {
    setAttente(false);
  }

  return;
}


if (intention?.type === "explication") {
  const document_id =
    documentOuvert ||
    (selection.length === 1 ? selection[0] : null);

  ajouter({
    role: "user",
    texte: q
  });

  if (!document_id) {
    ajouter({
      role: "erreur",
      texte: "Ouvrez ou sélectionnez un PDF à expliquer."
    });
    return;
  }

  setAttente(true);

  try {
    const resultat = await lancerAnalyse({
      document_id,
      type: "explain",
      section: q
    });

    ajouter({
      role: "assistant",
      texte: resultat.result,
      citations: resultat.citations || [],
      verdict: null,
      refus: null
    });
  } catch (erreur) {
    console.error("Erreur explication :", erreur);

    ajouter({
      role: "erreur",
      texte: `Erreur d'explication : ${erreur.message}`
    });
  } finally {
    setAttente(false);
  }

  return;
}



// Les autres demandes en langue spécifique
// seront connectées à l'agent d'analyse ensuite.
if (intention && intention.type !== "pdf") {
  ajouter({ role: "user", texte: q });

  ajouter({
    role: "assistant",
    texte: "Demande détectée. Le traitement de cette demande sera connecté à l'agent d'analyse.",
    citations: [],
    verdict: null,
    refus: null
  });

  return;
}



  // Les questions normales continuent vers RAG.
  executer(q, () => poserQuestion(q, selection, conversationId));
};


  const analyser = (type) => {
    const document_id = selection[0];
    let section = null;
    if (type === "explain") {
      section = window.prompt("Quelle section ou quel concept expliquer ?");
      if (!section) return;
    }
    const libelles = { summarize: "Résume ce document", full: "Analyse complète", explain: `Explique : ${section}` };
    executer(libelles[type], () => lancerAnalyse({ document_id, type, section }));
  };

  const unSeul = selection.length === 1;

  return (
    <div className="chatbot">

<input
  ref={inputPDF}
  type="file"
  accept="application/pdf"
  hidden
  onChange={importerPDF}
/>

      <div className="messages">
        {messages.length === 0 && (
          <div className="vide">
            Importez un PDF, cochez-le, puis posez votre question.<br />
            Chaque réponse cite ses sources : cliquez sur un numéro pour voir le passage surligné.
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} m={m} onCitation={onCitation} nomDocument={nomDocument} />
        ))}
        {attente && <div className="message assistant">⏳ Recherche dans les documents…</div>}
        <div ref={bas} />
      </div>

     

      
<div className="zone-composition">
  
{menuDocuments && (
  <div className="menu-documents">

    {!afficherDocuments ? (
      <div className="menu-options">
        <button
          type="button"
          className="option-document"
          onClick={() => inputPDF.current?.click()}
        >
          <span>📎</span>
          <span>Ajouter des fichiers</span>
        </button>

        <button
          type="button"
          className="option-document"
          onClick={() => setAfficherDocuments(true)}
        >
          <span>📁</span>
          <span>Mes documents</span>
        </button>
      </div>
    ) : (
      <>
        <button
          type="button"
          className="retour-documents"
          onClick={() => setAfficherDocuments(false)}
        >
          ← Retour
        </button>

        <Documents
          documents={documents}
          setDocuments={setDocuments}
          selection={selection}
          setSelection={setSelection}
          onOuvrir={onOuvrir}
          documentOuvert={documentOuvert}
          afficherImport={false}
        />
      </>
    )}

  </div>
)}


  <form onSubmit={envoyer} className="saisie">
    <button
      type="button"
      className="bouton-ajouter"
      onClick={() => setMenuDocuments((ouvert) => !ouvert)}
      title="Ajouter ou sélectionner un PDF"
      aria-label="Ajouter ou sélectionner un PDF"
      aria-expanded={menuDocuments}
    >
      +
    </button>

    
<input
  value={question}
  onChange={(e) => setQuestion(e.target.value)}
  placeholder="Posez une question sur vos documents..."
  disabled={attente}
/>


    <button
      type="submit"
      className="principal"
      disabled={attente || !question.trim()}
    >
      ↑
    </button>
  </form>
</div>

    </div>
  );
}
