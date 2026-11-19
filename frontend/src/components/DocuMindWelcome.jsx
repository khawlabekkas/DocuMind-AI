import { Suspense, lazy } from "react";
import { IconeAnalyser, IconeBouclier, IconeChevron, IconeTraduire } from "./Icones.jsx";
import "./DocuMindWelcome.css";

// Chargé paresseusement : le code three.js/R3F et le modèle .glb ne
// sont récupérés que lorsque l'écran d'accueil est réellement affiché.
const BrainScene = lazy(() => import("./BrainScene.jsx"));

const SUGGESTIONS = [
  {
    Icone: IconeAnalyser,
    titre: "Analyze documents",
    question: "Résume ce document"
  },
  {
    Icone: IconeTraduire,
    titre: "Translate PDFs",
    question: "Traduis ce document en anglais et télécharge le PDF"
  },
  {
    Icone: IconeBouclier,
    titre: "Verify answers",
    question: "Pose une question sur ce document et vérifie la fiabilité de la réponse."
  }
];

// Écran d'accueil affiché uniquement quand la conversation est vide.
// Purement présentationnel : `onQuickAction` ne fait que pré-remplir
// le champ de saisie existant, le reste du pipeline (envoyer,
// detecterTraduction, RAG...) n'est jamais contourné.
export default function DocuMindWelcome({ onQuickAction }) {
  return (
    <div className="documind-welcome-root">
      <div className="documind-welcome-brain">
        <div className="documind-welcome-aura" />
        <div className="documind-welcome-socle" />
        <Suspense fallback={null}>
          <BrainScene />
        </Suspense>
      </div>

      <div className="documind-welcome-texte">
        <h2 className="documind-welcome-titre">
          Welcome to <span>DocuMind AI</span>
        </h2>
        <p className="documind-welcome-sous-titre">
          Analyze, understand, translate and explore your documents with AI.
        </p>
      </div>

      <div className="documind-welcome-cartes">
        {SUGGESTIONS.map(({ Icone, titre, question }) => (
          <button
            key={titre}
            type="button"
            className="documind-welcome-carte"
            onClick={() => onQuickAction?.(question)}
          >
            <Icone className="documind-welcome-carte-icone" taille={34} epaisseur={1.5} />
            <span className="documind-welcome-carte-titre">{titre}</span>
            <IconeChevron className="documind-welcome-carte-fleche" taille={18} />
          </button>
        ))}
      </div>
    </div>
  );
}
