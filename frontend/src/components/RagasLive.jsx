
import { useEffect, useState, useRef } from "react";
import { IconeCerveau } from "./Icones.jsx";
import "./RagasLive.css";

const API = "http://127.0.0.1:8000/ragas";

const LABELS = {
  pending: "En attente d'évaluation",
  completed: "Évaluation terminée",
  partial: "Évaluation partielle",
  error: "Échec de l'évaluation",
};

const scoreValide = (v) =>
  typeof v === "number" && Number.isFinite(v);

const pourcentage = (v) =>
  scoreValide(v) ? `${(v * 100).toFixed(2)}%` : "—";

export default function RagasLive() {
  const [interactions, setInteractions] = useState([]);
  const [selection, setSelection] = useState([]);
  const [loading, setLoading] = useState(true);
  const [evaluation, setEvaluation] = useState(false);
  const [messageActif, setMessageActif] = useState(null);
  const [progression, setProgression] = useState(null);
  const [erreur, setErreur] = useState(null);

  const operationRef = useRef(false);

  // Chargement des interactions sans appel LLM
  const chargerInteractions = async () => {
    if (operationRef.current) return;

    operationRef.current = true;
    setLoading(true);
    setErreur(null);

    try {
      const response = await fetch(`${API}/interactions`);

      if (!response.ok) {
        throw new Error("Chargement impossible.");
      }

      const data = await response.json();

      setInteractions(data);

      setSelection((ancienne) =>
        ancienne.filter((id) =>
          data.some(
            (item) =>
              item.message_id === id &&
              item.evaluation_status !== "completed"
          )
        )
      );
    } catch (error) {
      setErreur(error.message);
    } finally {
      setLoading(false);
      operationRef.current = false;
    }
  };

  useEffect(() => {
    chargerInteractions();
  }, []);

  // Statistiques des évaluations réelles
  const moyenne = (champ) => {
    const scores = interactions
      .map((item) => item[champ])
      .filter(scoreValide);

    return scores.length
      ? scores.reduce((a, b) => a + b, 0) / scores.length
      : null;
  };

  const terminees = interactions.filter(
    (item) => item.evaluation_status === "completed"
  ).length;

  const evaluables = interactions.filter(
    (item) => item.evaluation_status !== "completed"
  );

  const toutSelectionne =
    evaluables.length > 0 &&
    evaluables.every((item) =>
      selection.includes(item.message_id)
    );

  const modifierSelection = (id) => {
    setSelection((ancienne) =>
      ancienne.includes(id)
        ? ancienne.filter((value) => value !== id)
        : [...ancienne, id]
    );
  };

  const selectionnerTout = () => {
    setSelection(
      toutSelectionne
        ? []
        : evaluables.map((item) => item.message_id)
    );
  };

  // Évaluation séquentielle pour limiter les appels API
  const lancerEvaluation = async () => {
    if (operationRef.current || !selection.length) return;

    operationRef.current = true;
    setEvaluation(true);
    setErreur(null);

    const ids = [...selection];

    setProgression({
      actuel: 0,
      total: ids.length,
    });

    try {
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];

        setMessageActif(id);

        const response = await fetch(
          `${API}/evaluate/${id}`,
          { method: "POST" }
        );

        const resultat = await response.json();

        if (!response.ok) {
          throw new Error(
            typeof resultat.detail === "string"
              ? resultat.detail
              : "Erreur pendant l'évaluation."
          );
        }

        setInteractions((anciennes) =>
          anciennes.map((item) =>
            item.message_id === id
              ? {
                  ...item,
                  faithfulness: resultat.faithfulness,
                  answer_relevancy: resultat.answer_relevancy,
                  evaluation_status: resultat.status,
                  erreur: resultat.erreur || null,
                }
              : item
          )
        );

        setProgression({
          actuel: i + 1,
          total: ids.length,
        });

        if (resultat.status === "completed") {
          setSelection((ancienne) =>
            ancienne.filter((value) => value !== id)
          );
        }

        // Arrêter le lot en cas d'échec ou de résultat
        // partiel pour éviter des appels API inutiles.
        if (resultat.status !== "completed") {
          throw new Error(
            "Évaluation interrompue. Vérifiez le quota API " +
            "et les résultats avant de réessayer."
          );
        }
      }
    } catch (error) {
      setErreur(error.message);
    } finally {
      setEvaluation(false);
      setMessageActif(null);
      operationRef.current = false;
    }
  };

  return (
    <div className="documind-dashboard-card ragas-live">
      <div className="ragas-live-header">
        <div>
          <h2 className="documind-dashboard-section-title">
            <span className="documind-dashboard-title-glyph">
              <IconeCerveau taille={18} />
            </span>
            Évaluation des interactions réelles
          </h2>

          <p className="documind-dashboard-section-hint">
            Évaluez les réponses enregistrées avec leurs
            contextes sources, sans relancer le chatbot.
          </p>
        </div>

        <button
          type="button"
          className="ragas-live-refresh"
          onClick={chargerInteractions}
          disabled={loading || evaluation}
        >
          ↻ Actualiser
        </button>
      </div>

      <div className="ragas-live-kpis">
        {[
          ["Interactions évaluables", interactions.length],
          ["Évaluations terminées", terminees],
          ["Faithfulness moyenne", pourcentage(moyenne("faithfulness"))],
          ["Answer Relevancy moyenne", pourcentage(moyenne("answer_relevancy"))],
        ].map(([label, valeur]) => (
          <div className="ragas-live-kpi" key={label}>
            <strong>{valeur}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>

      {erreur && (
        <div className="ragas-live-error" role="alert">
          {erreur}
        </div>
      )}

      <div className="ragas-live-toolbar">
        <strong>Interactions enregistrées</strong>

        <label>
          <input
            type="checkbox"
            checked={toutSelectionne}
            onChange={selectionnerTout}
            disabled={evaluation || loading || !evaluables.length}
          />
          Tout sélectionner
        </label>
      </div>

      {loading && <p>Chargement des interactions...</p>}

      {!loading && !interactions.length && (
        <p className="documind-dashboard-empty">
          Aucune interaction RAG évaluable disponible.
        </p>
      )}

      <div className="ragas-live-list">
        {interactions.map((item) => {
          const actif = messageActif === item.message_id;
          const termine = item.evaluation_status === "completed";

          return (
            <article
              key={item.message_id}
              className={
                "ragas-live-item" +
                (selection.includes(item.message_id)
                  ? " is-selected"
                  : "")
              }
            >
              <div className="ragas-live-question">
                <input
                  type="checkbox"
                  aria-label={`Sélectionner ${item.question}`}
                  checked={selection.includes(item.message_id)}
                  disabled={evaluation || loading || termine}
                  onChange={() =>
                    modifierSelection(item.message_id)
                  }
                />

                <div>
                  <strong>{item.question}</strong>
                  <small>
                    #{item.message_id} · {item.nb_contextes} contextes
                    sources
                  </small>
                </div>
              </div>

              <div className="ragas-live-scores">
                {[
                  ["Faithfulness", item.faithfulness],
                  ["Answer Relevancy", item.answer_relevancy],
                ].map(([label, score]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{pourcentage(score)}</strong>

                    <div className="ragas-live-track">
                      <div
                        className="ragas-live-fill"
                        style={{
                          width: scoreValide(score)
                            ? `${Math.max(0, Math.min(100, score * 100))}%`
                            : "0%",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <span
                className={
                  "ragas-live-status " +
                  (actif ? "running" : item.evaluation_status)
                }
              >
                {actif
                  ? "Évaluation en cours..."
                  : LABELS[item.evaluation_status] || LABELS.pending}
              </span>

              <details className="ragas-live-answer">
                <summary>Voir la réponse originale</summary>
                <p>{item.answer}</p>
              </details>

              {item.erreur && (
                <small className="ragas-live-error">
                  Évaluation incomplète ou échouée.
                </small>
              )}
            </article>
          );
        })}
      </div>

      {progression && (
        <div className="ragas-live-progress">
          <span>
            {progression.actuel} / {progression.total} interaction(s)
            traitée(s)
          </span>

          <div className="ragas-live-track">
            <div
              className="ragas-live-fill"
              style={{
                width: `${
                  (progression.actuel / progression.total) * 100
                }%`,
              }}
            />
          </div>
        </div>
      )}

      <button
        type="button"
        className="ragas-live-launch"
        disabled={evaluation || loading || !selection.length}
        onClick={lancerEvaluation}
      >
        {evaluation
          ? "Évaluation en cours..."
          : `Évaluer ${selection.length} interaction(s)`}
      </button>

      <p className="ragas-live-note">
        Les appels LLM sont déclenchés uniquement lors d'une
        évaluation manuelle. Les évaluations terminées sont
        conservées dans SQLite.
      </p>
    </div>
  );
}
