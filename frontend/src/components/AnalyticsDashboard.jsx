import { useEffect, useState } from "react";
import { obtenirAnalytics } from "../api.js";

export default function AnalyticsDashboard() {
  const [donnees, setDonnees] = useState({ ragas: [], guard: [] });
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [detailsOuverts, setDetailsOuverts] = useState(false);

  useEffect(() => {
    obtenirAnalytics()
      .then((resultat) => {
        setDonnees({
          ragas: Array.isArray(resultat?.ragas) ? resultat.ragas : [],
          guard: Array.isArray(resultat?.guard) ? resultat.guard : [],
        });
      })
      .catch((err) => setErreur(err.message))
      .finally(() => setChargement(false));
  }, []);

  if (chargement) return <p>Chargement des statistiques...</p>;
  if (erreur) return <p>Erreur : {erreur}</p>;

  const { ragas, guard } = donnees;
  const scoresValides = (champ) =>
    ragas
      .map((ligne) => ligne[champ])
      .filter(
        (valeur) =>
          valeur !== null &&
          valeur !== undefined &&
          String(valeur).trim() !== "" &&
          Number.isFinite(Number(valeur))
      )
      .map(Number);

  const moyenne = (champ) => {
    const scores = scoresValides(champ);
    if (scores.length === 0) return "N/A";
    const total = scores.reduce((somme, score) => somme + score, 0);
    return `${((total / scores.length) * 100).toFixed(2)}%`;
  };

  const refusReussis = guard.filter(
    (test) => String(test.test_passed).toLowerCase() === "true"
  ).length;

  return (
    <div className="analytics-dashboard">
      <h2>DocuMind AI — Analytics Dashboard</h2>
      <p>Évaluation de la qualité du système RAG</p>

      <div className="analytics-cards">
        <div className="analytics-card">
          <h3>Faithfulness</h3>
          <strong>{moyenne("faithfulness")}</strong>
          <small>{scoresValides("faithfulness").length} évaluations valides</small>
        </div>
        <div className="analytics-card">
          <h3>Answer Relevancy</h3>
          <strong>{moyenne("answer_relevancy")}</strong>
          <small>{scoresValides("answer_relevancy").length} évaluations valides</small>
        </div>
        <div className="analytics-card">
          <h3>Hallucination Guard</h3>
          <strong>{refusReussis}/{guard.length}</strong>
        </div>
        <div className="analytics-card">
          <h3>Questions évaluées</h3>
          <strong>{ragas.length}</strong>
        </div>
      </div>

      <section className="analytics-section">
        <button
          type="button"
          className="analytics-details-toggle"
          onClick={() => setDetailsOuverts(!detailsOuverts)}
          aria-expanded={detailsOuverts}
        >
          <span>Résultats RAGAS par question</span>
          <span>{detailsOuverts ? "−" : "+"}</span>
        </button>

        {detailsOuverts && (
          <div className="analytics-table-wrapper">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Faithfulness</th>
                  <th>Answer Relevancy</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {ragas.map((ligne, index) => (
                  <tr key={index}>
                    <td>
                      <strong>Q{index + 1}</strong>
                      <div>{ligne.question}</div>
                      {ligne.refusal_reason && (
                        <small>Motif : {ligne.refusal_reason}</small>
                      )}
                      {ligne.erreur && (
                        <small>Erreur technique d'évaluation</small>
                      )}
                    </td>
                    <td>
                      {ligne.faithfulness !== "" && ligne.faithfulness != null
                        ? `${(Number(ligne.faithfulness) * 100).toFixed(2)}%`
                        : "N/A"}
                    </td>
                    <td>
                      {ligne.answer_relevancy !== "" && ligne.answer_relevancy != null
                        ? `${(Number(ligne.answer_relevancy) * 100).toFixed(2)}%`
                        : "N/A"}
                    </td>
                    <td>
                      {ligne.status === "refused"
                        ? "Refusé"
                        : ligne.erreur
                          ? "Partiellement évalué"
                          : ligne.verdict || "Évalué"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <h3>Résultats Hallucination Guard</h3>
      <table className="analytics-table">
        <thead>
          <tr>
            <th>Question</th>
            <th>Statut obtenu</th>
            <th>Résultat</th>
          </tr>
        </thead>
        <tbody>
          {guard.map((test, index) => (
            <tr key={index}>
              <td>{test.question}</td>
              <td>{test.actual_status}</td>
              <td>
                {String(test.test_passed).toLowerCase() === "true"
                  ? "Réussi"
                  : "Échoué"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
