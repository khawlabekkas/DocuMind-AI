
import { useEffect, useState } from "react";
import { obtenirAnalytics } from "../api.js";

export default function AnalyticsDashboard() {
  const [donnees, setDonnees] = useState({
    ragas: [],
    guard: [],
  });

  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    obtenirAnalytics()
      .then(setDonnees)
      .catch((err) => setErreur(err.message))
      .finally(() => setChargement(false));
  }, []);

  if (chargement) {
    return <p>Chargement des statistiques...</p>;
  }

  if (erreur) {
    return <p>Erreur : {erreur}</p>;
  }

  const ragas = donnees.ragas;
  const guard = donnees.guard;

  const moyenne = (champ) => {
    if (ragas.length === 0) return 0;

    const total = ragas.reduce(
      (somme, ligne) => somme + Number(ligne[champ]),
      0
    );

    return (total / ragas.length * 100).toFixed(2);
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
          <strong>{moyenne("faithfulness")}%</strong>
        </div>

        <div className="analytics-card">
          <h3>Answer Relevancy</h3>
          <strong>{moyenne("answer_relevancy")}%</strong>
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

      <h3>Résultats RAGAS par question</h3>

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
              <td>{ligne.question}</td>
              <td>{ligne.faithfulness}</td>
              <td>{ligne.answer_relevancy}</td>
              <td>{ligne.verification_verdict}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Tests du Hallucination Guard</h3>

      <table className="analytics-table">
        <thead>
          <tr>
            <th>Question</th>
            <th>Statut</th>
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
