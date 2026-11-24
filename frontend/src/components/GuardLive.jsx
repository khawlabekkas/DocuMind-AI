import { useEffect, useState } from "react";
import { Doughnut } from "react-chartjs-2";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";

import { IconeBouclier } from "./Icones.jsx";
import "./GuardLive.css";

ChartJS.register(ArcElement, Tooltip, Legend);

const API = "http://127.0.0.1:8000/guard/interactions";

export default function GuardLive() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState(null);
  const [filtre, setFiltre] = useState("all");
  const [actualisation, setActualisation] = useState(0);

  useEffect(() => {
    let actif = true;
    let enCours = false;
    const controller = new AbortController();

    const charger = async () => {
      if (enCours || document.hidden) return;

      enCours = true;

      try {
        const response = await fetch(API, {
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error("Chargement impossible.");
        }

        const resultat = await response.json();

        if (actif) {
          setData(resultat);
          setErreur(null);
        }
      } catch (error) {
        if (actif && error.name !== "AbortError") {
          setErreur(error.message);
        }
      } finally {
        enCours = false;
        if (actif) setLoading(false);
      }
    };

    charger();

    const interval = setInterval(charger, 5000);

    return () => {
      actif = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [actualisation]);

  const interactions = data?.interactions || [];

  const interactionsFiltrees = interactions.filter(
    (item) => filtre === "all" || item.decision === filtre
  );

  const chartData = {
    labels: ["Réponses générées", "Questions bloquées"],
    datasets: [
      {
        data: [data?.answered || 0, data?.blocked || 0],
        backgroundColor: ["#a855f7", "#f472b6"],
        borderWidth: 0,
        hoverOffset: 5,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "72%",
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          color: "#e9d5ff",
          usePointStyle: true,
          padding: 20,
        },
      },
    },
  };

  const indicateurs = [
    ["Interactions suivies", data?.total ?? "—"],
    ["Réponses générées", data?.answered ?? "—"],
    ["Questions bloquées", data?.blocked ?? "—"],
    [
      "Taux de refus",
      data?.total > 0
        ? `${data.refusal_rate.toFixed(2)}%`
        : "—",
    ],
  ];

  return (
    <div className="documind-dashboard-card guard-live">

      <div className="guard-live-header">
        <div>
          <h2 className="documind-dashboard-section-title">
            <span className="documind-dashboard-title-glyph">
              <IconeBouclier taille={18} />
            </span>
            Hallucination Guard — Live Monitoring
          </h2>

          <p className="documind-dashboard-section-hint">
            Surveillance dynamique des réponses RAG
            et des refus du Hallucination Guard.
          </p>
        </div>

        <div className="guard-live-actions">
          <span className="guard-live-indicator">
            <span />
            Live Monitoring
          </span>

          <button
            type="button"
            className="guard-live-refresh"
            onClick={() => setActualisation((n) => n + 1)}
          >
            ↻ Actualiser
          </button>
        </div>
      </div>

      <div className="guard-live-kpis">
        {indicateurs.map(([label, valeur]) => (
          <div className="guard-live-kpi" key={label}>
            <strong>{valeur}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>

      {erreur && (
        <p className="guard-live-error" role="alert">
          {erreur}
        </p>
      )}

      {loading && <p>Chargement des interactions...</p>}

      <div className="guard-live-chart-section">
        <h3 className="documind-dashboard-section-title">
          Distribution des interactions
        </h3>

        {data?.total > 0 ? (
          <div className="guard-live-chart">
            <Doughnut
              data={chartData}
              options={chartOptions}
            />
          </div>
        ) : (
          <p className="documind-dashboard-empty">
            Aucune interaction disponible.
          </p>
        )}

        <p className="guard-live-note">
          Le taux de refus est calculé sur les interactions
          suivies. Il ne représente pas un taux de réussite
          ni une mesure de précision du Guard.
        </p>
      </div>

      <div className="guard-live-toolbar">
        <h3>Historique des interactions</h3>

        <div className="guard-live-filters">
          {[
            ["all", "Toutes"],
            ["answered", "Répondues"],
            ["blocked", "Bloquées"],
          ].map(([value, label]) => (
            <button
              type="button"
              key={value}
              className={filtre === value ? "active" : ""}
              onClick={() => setFiltre(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="guard-live-list">
        {interactionsFiltrees.map((item) => (
          <article
            className={`guard-live-item ${item.decision}`}
            key={item.message_id}
          >
            <div className="guard-live-item-header">
              <span
                className={`guard-live-status ${item.decision}`}
              >
                {item.decision === "blocked"
                  ? "Bloquée par le Guard"
                  : "Réponse générée"}
              </span>

              <small>#{item.message_id}</small>
            </div>

            <h4>{item.question}</h4>

            <small className="guard-live-date">
              {new Date(item.created_at).toLocaleString("fr-FR")}
            </small>

            {item.decision === "blocked" ? (
              <div className="guard-live-reason">
                <strong>Raison du refus</strong>
                <p>
                  {item.refusal_reason ||
                    "Raison non enregistrée."}
                </p>
              </div>
            ) : (
              <details className="guard-live-answer">
                <summary>Voir la réponse originale</summary>
                <p>{item.answer}</p>
              </details>
            )}
          </article>
        ))}

        {!loading && interactionsFiltrees.length === 0 && (
          <p className="documind-dashboard-empty">
            Aucune interaction pour ce filtre.
          </p>
        )}
      </div>

      <p className="guard-live-note">
        Actualisation automatique toutes les 5 secondes.
        Aucun appel supplémentaire au LLM.
      </p>
    </div>
  );
}