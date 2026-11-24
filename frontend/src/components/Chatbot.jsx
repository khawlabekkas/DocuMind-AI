import { useEffect, useRef, useState } from "react";
import Documents from "./Documents.jsx";
import DocuMindWelcome from "./DocuMindWelcome.jsx";
import { IconeDocument, IconeEnvoyer, IconeEtincelle, IconeTrombone } from "./Icones.jsx";




import {
  traduireTexte,
  lancerAnalyse,
  poserQuestion,
  obtenirMessages,
  importerDocument,
  listerDocuments,
  telechargerTraductionPDF,
  sauvegarderEchange
} from "../api.js";



// Transforme "texte [1] suite [2]" en texte + boutons cliquables

function TexteCite({ texte, citations = [], onCitation }) {
  const contenu = String(texte || "")
    .replace(/【(\d+)】/g, "[$1]")
    .replace(/［(\d+)］/g, "[$1]");

  // Detect Arabic while keeping citations clickable.
  const estArabe = /[\u0600-\u06FF]/.test(contenu);
  const direction = estArabe ? "rtl" : "ltr";
  const rendreMarkdown = (texte) => {
  return texte.split(/(\*\*.*?\*\*|\*[^*\n]+\*)/g).map((partie, i) => {
    if (partie.startsWith("**") && partie.endsWith("**")) {
      return <strong key={i}>{partie.slice(2, -2)}</strong>;
    }

    if (partie.startsWith("*") && partie.endsWith("*")) {
      return <em key={i}>{partie.slice(1, -1)}</em>;
    }

    return partie;
  });
};

  const rendreAvecCitations = (ligne) => {
    const morceaux = ligne.split(/(\[\d+(?:\s*,\s*\d+)*\])/g);

    return morceaux.flatMap((m, i) => {
      const nums = m.match(/^\[([\d,\s]+)\]$/);

      if (!nums) {
  return [
    <span key={`t-${i}`}>
      {rendreMarkdown(m)}
    </span>
  ];
}

      return nums[1].split(",").map((n, j) => {
        const numero = Number(n.trim());
        const citation = citations.find(
          (c) => Number(c.numero) === numero
        );

        if (!citation) {
          return <span key={`missing-${i}-${j}`}>[{numero}]</span>;
        }

        return (
          <button
            key={`citation-${i}-${j}`}
            type="button"
            className="pastille"
            onClick={() => onCitation(citation)}
            title={`Page ${citation.page}`}
          >
            {numero}
          </button>
        );
      });
    });
  };

  const lignes = contenu.split(/\r?\n/);
  const blocs = [];
  let paragraphe = [];
  let liste = [];
  let typeListe = null;

  const viderParagraphe = () => {
    if (!paragraphe.length) return;

    blocs.push({
      type: "paragraphe",
      texte: paragraphe.join(" ")
    });
    paragraphe = [];
  };

  const viderListe = () => {
    if (!liste.length) return;

    blocs.push({
      type: typeListe,
      elements: liste
    });

    liste = [];
    typeListe = null;
  };

  for (const ligne of lignes) {
    const propre = ligne.trim();

    if (!propre) {
      viderParagraphe();
      viderListe();
      continue;
    }

    const titre = propre.match(/^(#{1,3})\s+(.+)$/);
    const puce = propre.match(/^[-*•]\s+(.+)$/);
    const numero = propre.match(/^\d+[.)]\s+(.+)$/);

    if (titre) {
      viderParagraphe();
      viderListe();
      blocs.push({
        type: "titre",
        niveau: titre[1].length,
        texte: titre[2]
      });
    } else if (puce || numero) {
      viderParagraphe();

      const nouveauType = puce ? "ul" : "ol";

      if (typeListe && typeListe !== nouveauType) {
        viderListe();
      }

      typeListe = nouveauType;
      liste.push((puce || numero)[1]);
    } else {
      viderListe();
      paragraphe.push(propre);
    }
  }

  viderParagraphe();
  viderListe();

  return (
    <div className="texte texte-structure" dir={direction}>
      {blocs.map((bloc, i) => {
        if (bloc.type === "titre") {
          const Tag = `h${Math.min(bloc.niveau + 2, 5)}`;

          return (
            <Tag key={i} className="texte-titre">
              {rendreAvecCitations(bloc.texte)}
            </Tag>
          );
        }

        if (bloc.type === "ul" || bloc.type === "ol") {
          const Tag = bloc.type;

          return (
            <Tag key={i} className="texte-liste">
              {bloc.elements.map((element, j) => (
                <li key={j}>
                  {rendreAvecCitations(element)}
                </li>
              ))}
            </Tag>
          );
        }

        return (
          <p key={i} className="texte-paragraphe">
            {rendreAvecCitations(bloc.texte)}
          </p>
        );
      })}
    </div>
  );
}


function Message({ m, onCitation, nomDocument, onOuvrirDocument }) {
  if (m.role === "user") return <div className="message user">{m.texte}</div>;
  if (m.role === "erreur") return <div className="message erreur">{m.texte}</div>;
  if (m.role === "piece-jointe")
    return (
      <button
        type="button"
        className="piece-jointe"
        onClick={() => onOuvrirDocument(m.documentId)}
        title={m.nom}
      >
        <span className="piece-jointe-icone">
          <IconeDocument taille={22} epaisseur={1.6} />
        </span>
        <span className="piece-jointe-infos">
          <span className="piece-jointe-nom">{m.nom}</span>
          <span className="piece-jointe-pages">
            {m.pages ? `${m.pages} page${m.pages > 1 ? "s" : ""}` : "PDF"}
          </span>
        </span>
      </button>
    );
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
              <small>« {(c.extrait ?? "").slice(0, 140)}… »</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Langue de la demande quand aucune langue cible explicite n'est fournie.
const detecterLangueDemande = (texte) => {
  const q = texte.toLowerCase().normalize("NFKC");
  const cible = q.match(/\b(?:in|en)\s+(french|français|francais|francés|frances|english|anglais|inglés|ingles|spanish|español|espanol|espagnol|arabic|arabe|árabe)\b/i);
  if (cible) {
    const cibleNormalisee = cible[1].normalize("NFD").replace(/\p{Diacritic}/gu, "");
    if (["french", "francais", "frances"].includes(cibleNormalisee)) return "fr";
    if (["english", "anglais", "ingles"].includes(cibleNormalisee)) return "en";
    if (["spanish", "espanol", "espagnol"].includes(cibleNormalisee)) return "es";
    if (["arabic", "arabe"].includes(cibleNormalisee)) return "ar";
  }

  const cibleArabe = q.match(/(?:باللغة\s*|بال)(العربية|الإنجليزية|الانجليزية|الإسبانية|الاسبانية|الفرنسية|فرنسية)/);
  if (cibleArabe) {
    if (cibleArabe[1] === "العربية") return "ar";
    if (["الإنجليزية", "الانجليزية"].includes(cibleArabe[1])) return "en";
    if (["الإسبانية", "الاسبانية"].includes(cibleArabe[1])) return "es";
    return "fr";
  }

  if (/[\u0600-\u06FF]/.test(q)) return "ar";

  const qNormalisee = q.normalize("NFD").replace(/\p{Diacritic}/gu, "");
  const motsAnglais = new Set([
    "make", "summary", "summery", "summarize", "summarise", "explain", "analyze",
    "give", "show", "tell", "please", "the", "this", "that", "these", "entire",
    "those", "of", "into", "what", "how", "can", "could", "you", "about"
  ]);
  const motsFrancais = new Set([
    "resume", "resumer", "analyse", "fais", "fait", "donne", "explique",
    "expliquer", "traduis", "ce", "cet", "cette", "ces", "le", "la", "les",
    "des", "du", "de", "un", "une", "moi", "sur", "pour", "avec", "et", "tout",
    "document", "mon", "ma", "mes", "peux", "pouvez", "je", "veux"
  ]);
  const motsEspagnols = new Set([
    "resume", "resumen", "resumir", "todo", "toda", "el", "documento", "completo",
    "analiza", "analizar", "explica", "pagina", "las", "los", "sus", "esto", "eso",
    "que", "como", "y", "del", "para"
  ]);
  let anglais = 0;
  let francais = /[éèêëàâùûçôîï]/.test(q) ? 2 : 0;
  let espagnol = 0;

  for (const mot of qNormalisee.match(/[\p{L}']+/gu) || []) {
    if (motsAnglais.has(mot)) anglais++;
    if (motsFrancais.has(mot)) francais++;
    if (motsEspagnols.has(mot)) espagnol++;
  }

  if (espagnol > anglais && espagnol > francais) return "es";
  if (anglais > francais) return "en";
  return "fr";
};

// Traduit un texte en conservant les marqueurs de citation [1], [2][3]...
// 1) un seul appel, marqueurs remplacés par des jetons puis restitués ;
// 2) si un jeton est altéré, repli : seuls les morceaux entre les
//    marqueurs sont traduits, les marqueurs ne sont jamais envoyés.
const MARQUEUR_CITATION = /\[\d+(?:\s*,\s*\d+)*\]/g;

const traduireEnGardantCitations = async (texte, langue) => {
  const marqueurs = texte.match(MARQUEUR_CITATION) || [];
  if (marqueurs.length === 0) return traduireTexte(texte, langue);

  let n = 0;
  const protege = texte.replace(MARQUEUR_CITATION, () => `⟦${n++}⟧`);
  const traduit = await traduireTexte(protege, langue);

  const intacts = marqueurs.every(
    (_, k) => (traduit.match(new RegExp(`⟦${k}⟧`, "g")) || []).length === 1
  );
  if (intacts) {
    return traduit.replace(/⟦(\d+)⟧/g, (_, k) => marqueurs[Number(k)] ?? "");
  }
  console.warn(
  "[TRANSLATION] Citation markers not preserved; using fallback.",
  {
    expected: marqueurs.length,
    originalMarkers: protege.match(/⟦\d+⟧/g),
    translatedMarkers: traduit.match(/⟦\d+⟧/g)
  }
);

  const morceaux = texte.split(/(\[\d+(?:\s*,\s*\d+)*\])/g);
  const resultats = await Promise.all(
    morceaux.map(async (m, k) => {
      if (k % 2 === 1 || !/\p{L}/u.test(m)) return m;
      const [, avant, coeur, apres] = m.match(/^(\s*)([\s\S]*?)(\s*)$/);
      return avant + (await traduireTexte(coeur, langue)) + apres;
    })
  );
  return resultats.join("");
};

export default function Chatbot({
  messagesSauvegardes,
  selection,
  documents,
  setDocuments,
  setSelection,
  onCitation,
  onOuvrir,
  onImporterPDF,
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

    // Sélectionne le document comme actif, sans ouvrir la visionneuse.
    onImporterPDF(resultat.document_id);

    // Affiche une carte pièce jointe cliquable dans le fil de discussion.
    setMessages((ms) => [
      ...ms,
      {
        role: "piece-jointe",
        documentId: resultat.document_id,
        nom: resultat.nom,
        pages: resultat.pages
      }
    ]);

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

const enregistrerAnalyse = async (
  question,
  reponse,
  citations = [],
  type = "analysis"
) => {
  const resultat = await sauvegarderEchange({
    conversation_id: conversationId || null,
    question,
    reponse,
    citations,
    type_interaction: type
  });

  if (!conversationId && resultat.conversation_id) {
    onConversationCreated?.(resultat.conversation_id);
  }

  return resultat;
};


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

  // 1. Langue cible
  let langue = null;

  if (/\b(français|francais|french)\b/i.test(q)) langue = "fr";
  else if (/\b(anglais|english)\b/i.test(q)) langue = "en";
  else if (/\b(arabe|arabic)\b/i.test(q)) langue = "ar";
  else if (/\b(espagnol|spanish)\b/i.test(q)) langue = "es";

  // 2. Intentions
  
const traduction =
  /tradui\w*|traduction|translat\w*/i.test(q);

const demandeTelechargement =
  /t[ée]l[ée]charg\w*|download\w*/i.test(q);


  const explication =
    /expliqu\w*|explication|explain\w*/i.test(q);

  const resume =
    /r[ée]sum\w*|r[ée]sm\w*|summ[ae]ri[sz]\w*|summ[ae]ry/i.test(q);

  // 3. Réponse précédente
  const precedent =
    /\b(ta|ton|your|previous|last|dernière|dernier)\b/i.test(q) &&
    /\b(réponse|reponse|explication|answer|response|message|summary|résumé)\b/i.test(q);

  // 4. Document PDF
  const documentPDF =
    /\b(document|pdf|fichier|file)\b/i.test(q);

  // 5. Traduction d'un PDF
  // Le mot "entier" n'est plus obligatoire.
  // Un verbe de traduction OU une demande explicite de téléchargement
  // suffit, tant que le contexte PDF et la langue cible sont présents.
  if (
    (traduction || demandeTelechargement) &&
    documentPDF &&
    !precedent &&
    langue
  ) {
    return { type: "pdf", langue };
  }

  // 6. Traduction d'une réponse précédente
  if (precedent && traduction && langue) {
    return { type: "message", langue };
  }

  // 6b. "translate this summary / traduis l'explication en anglais" :
  // c'est une traduction de réponse, pas un nouveau résumé ni une
  // nouvelle explication.
  if (traduction && langue && (resume || explication) && !documentPDF) {
    return { type: "message", langue };
  }

  // 7. Résumé
  if (resume) {
    return { type: "resume", langue };
  }

  // 8. Explication
  if (explication) {
    return { type: "explication", langue };
  }

  // 9. Traduction d'un autre texte
  if (traduction && langue) {
    return { type: "texte", langue };
  }

  return null;
};
const detecterAnalyseComplete = (texte) => {
  const q = texte.toLowerCase().trim();

  const analyse = /\b(analy[sz]e|analysis|analyse[rz]?|analiza[r]?|análisis)\b|حلل|تحليل/u.test(q);

  const document = /\b(document|pdf|file|fichier|documento)\b|المستند|الوثيقة|الملف/u.test(q);

  return analyse && document;
};
  
const envoyer = async (e) => {
  e.preventDefault();

  const q = question.trim();
  if (!q || attente) return;

  
const intention = detecterTraduction(q);
setQuestion("");
if (!intention && detecterAnalyseComplete(q)) {
  const document_id =
    documentOuvert ||
    (selection.length === 1 ? selection[0] : null);

  if (!document_id) {
    ajouter({
      role: "erreur",
      texte: "Ouvrez ou sélectionnez un PDF à analyser."
    });
    return;
  }

  const langue = detecterLangueDemande(q);

  await executer(q, () =>
    lancerAnalyse({
      document_id,
      type: "full",
      langue
    })
  );

  return;
}


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
    // Langue explicite d'abord ; sinon langue de la demande (fr/en).
    const langueReponse = intention.langue || detecterLangueDemande(q);

    const resultat = await lancerAnalyse({
      document_id,
      type: "summarize",
      section: null,
      page_debut: null,
      page_fin: null,
      langue: langueReponse
    });

    const texteResume = resultat.result;

    ajouter({
      role: "assistant",
      texte: texteResume,
      citations: resultat.citations || [],
      verdict: null,
      refus: null
    });

    await enregistrerAnalyse(
      q,
      texteResume,
      resultat.citations || [],
      "summarize"
    );

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

  // Sépare le sujet à expliquer de la langue demandée
  // ("Explique le RAG en anglais" -> sujet "le RAG", langue "en").
  const nettoyerSujet = (texte) =>
    texte
      .replace(/\b(?:expliqu|explication|explain)[\p{L}]*/giu, " ")
      .replace(/\b(?:en|in|dans|to)\s+(?:le\s+|la\s+)?(?:fran[cç]ais|french|anglais|english|arabe|arabic|espagnol|spanish)\b/giu, " ")
      .replace(/\b(?:fran[cç]ais|french|anglais|english|arabe|arabic|espagnol|spanish)\b/giu, " ")
      .replace(/\b(?:moi|me|s'il\s+(?:te|vous)\s+pla[iî]t|stp|svp|please|peux-tu|pouvez-vous|pourrais-tu|pourriez-vous|can you|could you|je veux|je voudrais|i want|i'd like|i would like)\b/giu, " ")
      .replace(/(^|\s)-+(?=\s|$)/g, " ")
      .replace(/[?!.,;:]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();

  let sujet = nettoyerSujet(q);

  // Aucun sujet dans la phrase ("Explique en anglais") : on reprend le
  // sujet de la demande précédente seulement si elle était une question
  // ordinaire ou une explication ; sinon on demande une précision.
  if (!sujet) {
    const precedentUtilisateur = [...messages]
      .reverse()
      .find(
        (message) =>
          message.role === "user" &&
          typeof message.texte === "string" &&
          message.texte.trim()
      );

    const intentionPrecedente = precedentUtilisateur
      ? detecterTraduction(precedentUtilisateur.texte)
      : null;

    if (
      precedentUtilisateur &&
      (!intentionPrecedente || intentionPrecedente.type === "explication")
    ) {
      sujet = nettoyerSujet(precedentUtilisateur.texte);
    }
  }

  if (!sujet) {
    ajouter({
      role: "assistant",
      texte:
        "Que dois-je expliquer ? Précisez un sujet, par exemple « Explique le RAG en anglais », ou « Explique ce document en anglais ».",
      citations: [],
      verdict: null,
      refus: null
    });
    return;
  }

  // "ce document", "le pdf"... : explication du document entier.
  const expliquerDocument =
    /^(?:tout\s+)?(?:(?:ce|cet|cette|le|la|this|the|mon|my)\s+)?(?:document|pdf|fichier|file|texte|text)(?:\s+(?:ci|entier|complet|en entier|entirely|whole))?$/i.test(sujet);

  setAttente(true);

  try {
    const langueReponse = intention.langue || detecterLangueDemande(q);
    const resultat = await lancerAnalyse(
      expliquerDocument
        ? { document_id, type: "full", langue: langueReponse }
        : { document_id, type: "explain", section: sujet }
    );

    let texteExplication = resultat.result;

    // L'explication du backend est en français : on ne traduit que si besoin.
    if (!expliquerDocument && (intention.langue || langueReponse !== "fr")) {
      texteExplication = await traduireEnGardantCitations(
        texteExplication,
        langueReponse
      );
    }

    ajouter({
      role: "assistant",
      texte: texteExplication,
      citations: resultat.citations || [],
      verdict: null,
      refus: null
    });

await enregistrerAnalyse(
  q,
  texteExplication,
  resultat.citations || [],
  "explain"
);

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
    executer(libelles[type], () => lancerAnalyse({
      document_id,
      type,
      section,
      ...(type === "full" && { langue: detecterLangueDemande(libelles[type]) })
    }));
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
          <DocuMindWelcome onQuickAction={(texte) => setQuestion(texte)} />
        )}
        {messages.map((m, i) => (
          <Message
            key={i}
            m={m}
            onCitation={onCitation}
            nomDocument={nomDocument}
            onOuvrirDocument={onOuvrir}
          />
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
    <IconeEtincelle className="saisie-etincelle" taille={22} />

<input
  value={question}
  onChange={(e) => setQuestion(e.target.value)}
  placeholder="Ask anything about your documents..."
  disabled={attente}
/>

    <button
      type="button"
      className="bouton-ajouter"
      onClick={() => setMenuDocuments((ouvert) => !ouvert)}
      title="Ajouter ou sélectionner un PDF"
      aria-label="Ajouter ou sélectionner un PDF"
      aria-expanded={menuDocuments}
    >
      <IconeTrombone taille={21} />
    </button>

    <button
      type="submit"
      className="principal"
      disabled={attente || !question.trim()}
      aria-label="Envoyer"
    >
      <IconeEnvoyer taille={20} epaisseur={1.9} />
    </button>
  </form>
</div>

    </div>
  );
}
