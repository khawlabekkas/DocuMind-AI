import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Line, Bar, Doughnut } from "react-chartjs-2";
import "./Dashboard.css";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler
);

const COULEUR_MUTED = "#a39db0";
const COULEUR_GRID = "rgba(255, 255, 255, 0.06)";
const COULEUR_PINK = "#ec4899";
const COULEUR_PURPLE = "#8b5cf6";

const TOOLTIP_SOMBRE = {
  backgroundColor: "#1c1922",
  titleColor: "#ffffff",
  bodyColor: "#d8d3e0",
  borderColor: "rgba(255, 255, 255, 0.1)",
  borderWidth: 1,
  padding: 10,
  cornerRadius: 8,
  displayColors: true,
};

const LABELS_TYPE_INTERACTION = {
  ask: "Questions",
  summarize: "Résumés",
  explain: "Explications",
  full: "Analyse complète",
};

const INTERVALLE_RAFRAICHISSEMENT_MS = 5000;

export default function Dashboard({ onRetour }) {
  const [stats, setStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState(null);
  const [actualisation, setActualisation] = useState(false);
  const [sectionActive, setSectionActive] = useState("apercu");

  const refApercu = useRef(null);
  const refRagas = useRef(null);
  const refGuard = useRef(null);
  const refDocuments = useRef(null);

  // Empêche les requêtes de polling de se chevaucher si une précédente
  // n'est pas encore terminée (ex. latence réseau supérieure à 5s).
  const requeteEnCoursRef = useRef(false);
  // Retient si un premier chargement a déjà réussi, pour distinguer un
  // échec initial d'un échec de rafraîchissement (on garde alors les
  // dernières données valides affichées).
  const dejaChargeRef = useRef(false);

  const chargerDashboard = useCallback(async () => {
    if (requeteEnCoursRef.current) return;
    requeteEnCoursRef.current = true;
    setActualisation(true);

    try {
      const [statsResponse, analyticsResponse] =
        await Promise.all([
          fetch("http://127.0.0.1:8000/dashboard/stats"),
          fetch("http://127.0.0.1:8000/analytics/results"),
        ]);

      if (!statsResponse.ok || !analyticsResponse.ok) {
        throw new Error("Erreur lors du chargement");
      }

      const statsData = await statsResponse.json();
      const analyticsData = await analyticsResponse.json();

      setStats(statsData);
      setAnalytics(analyticsData);
      setErreur(null);
      dejaChargeRef.current = true;
    } catch (error) {
      console.error("Dashboard error:", error);
      // Les dernières données affichées (stats/analytics) ne sont pas
      // effacées : on les conserve et on signale juste l'échec.
      setErreur(
        dejaChargeRef.current
          ? "Échec de la dernière actualisation — affichage des dernières données connues."
          : "Impossible de charger les statistiques. Vérifiez que l'API est démarrée."
      );
    } finally {
      setLoading(false);
      setActualisation(false);
      requeteEnCoursRef.current = false;
    }
  }, []);

  useEffect(() => {
    chargerDashboard();

    const intervalId = setInterval(() => {
      // Met en pause le polling pendant que l'onglet est en arrière-plan.
      if (document.hidden) return;
      chargerDashboard();
    }, INTERVALLE_RAFRAICHISSEMENT_MS);

    const gererChangementVisibilite = () => {
      if (!document.hidden) {
        chargerDashboard();
      }
    };

    document.addEventListener("visibilitychange", gererChangementVisibilite);

    return () => {
      clearInterval(intervalId);
      document.removeEventListener(
        "visibilitychange",
        gererChangementVisibilite
      );
    };
  }, [chargerDashboard]);

  const allerALaSection = (nom, ref) => {
    setSectionActive(nom);
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // ------------------------------------------------------- Activité (line)
  const activite = stats?.activite || [];

  const activiteChartData = useMemo(
    () => ({
      labels: activite.map((j) =>
        new Date(`${j.jour}T12:00:00`).toLocaleDateString("fr-FR", {
          day: "2-digit",
          month: "short",
        })
      ),
      datasets: [
        {
          label: "Interactions",
          data: activite.map((j) => j.total),
          borderColor: COULEUR_PINK,
          borderWidth: 2.5,
          pointBackgroundColor: COULEUR_PURPLE,
          pointBorderColor: "#ffffff",
          pointRadius: 4,
          tension: 0.4,
          fill: true,
          backgroundColor: (context) => {
            const { ctx, chartArea } = context.chart;
            if (!chartArea) return "rgba(236, 72, 153, 0.15)";
            const gradient = ctx.createLinearGradient(
              0,
              chartArea.top,
              0,
              chartArea.bottom
            );
            gradient.addColorStop(0, "rgba(236, 72, 153, 0.45)");
            gradient.addColorStop(1, "rgba(139, 92, 246, 0)");
            return gradient;
          },
        },
      ],
    }),
    [activite]
  );

  const optionsLigne = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: TOOLTIP_SOMBRE,
    },
    scales: {
      x: {
        ticks: { color: COULEUR_MUTED },
        grid: { display: false },
      },
      y: {
        beginAtZero: true,
        ticks: { color: COULEUR_MUTED, precision: 0 },
        grid: { color: COULEUR_GRID },
      },
    },
  };

  // -------------------------------------------------- RAGAS (grouped bar)
  const comparaison = analytics?.comparison || [];

  const moyenneRagas = (method, metric) => {
    const valeurs = comparaison
      .filter((r) => r.method === method)
      .map((r) => Number(r[metric]))
      .filter(Number.isFinite);

    return valeurs.length
      ? valeurs.reduce((a, b) => a + b, 0) / valeurs.length
      : 0;
  };

  const ragasChartData = useMemo(
    () => ({
      labels: ["Faithfulness", "Answer Relevancy"],
      datasets: [
        {
          label: "Baseline (FAISS)",
          data: [
            moyenneRagas("baseline", "faithfulness"),
            moyenneRagas("baseline", "answer_relevancy"),
          ],
          backgroundColor: COULEUR_PINK,
          borderRadius: 8,
          maxBarThickness: 48,
        },
        {
          label: "Advanced (Hybrid)",
          data: [
            moyenneRagas("advanced", "faithfulness"),
            moyenneRagas("advanced", "answer_relevancy"),
          ],
          backgroundColor: COULEUR_PURPLE,
          borderRadius: 8,
          maxBarThickness: 48,
        },
      ],
    }),
    [comparaison]
  );

  const optionsBarres = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: COULEUR_MUTED, boxWidth: 10, padding: 16 },
      },
      tooltip: TOOLTIP_SOMBRE,
    },
    scales: {
      x: {
        ticks: { color: COULEUR_MUTED },
        grid: { display: false },
      },
      y: {
        beginAtZero: true,
        max: 1,
        ticks: { color: COULEUR_MUTED },
        grid: { color: COULEUR_GRID },
      },
    },
  };

  // --------------------------------------------------- Vérification (doughnut)
  const verification = stats?.verification || {};
  const totalVerifie = verification.total_verifie ?? 0;

  const verificationChartData = useMemo(
    () => ({
      labels: ["Supported", "Corrected", "Rejected"],
      datasets: [
        {
          data: [
            verification.supported ?? 0,
            verification.corrected ?? 0,
            verification.rejected ?? 0,
          ],
          backgroundColor: ["#34d399", "#fbbf24", "#f87171"],
          borderWidth: 0,
          hoverOffset: 6,
        },
      ],
    }),
    [verification.supported, verification.corrected, verification.rejected]
  );

  // ------------------------------------------------ Types d'interaction
  const interactionsParType = stats?.interactions_par_type || [];

  const interactionsChartData = useMemo(
    () => ({
      labels: interactionsParType.map(
        (ligne) =>
          LABELS_TYPE_INTERACTION[ligne.type] ||
          (ligne.type
            ? ligne.type.charAt(0).toUpperCase() + ligne.type.slice(1)
            : "Autre")
      ),
      datasets: [
        {
          data: interactionsParType.map((ligne) => ligne.total),
          backgroundColor: [
            COULEUR_PINK,
            COULEUR_PURPLE,
            "#f472b6",
            "#a78bfa",
            "#c084fc",
          ],
          borderWidth: 0,
          hoverOffset: 6,
        },
      ],
    }),
    [interactionsParType]
  );

  const optionsDoughnut = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: COULEUR_MUTED, boxWidth: 10, padding: 14 },
      },
      tooltip: TOOLTIP_SOMBRE,
    },
    cutout: "68%",
  };

  if (loading) {
    return (
      <div className="documind-dashboard-root documind-dashboard-loading">
        Chargement du dashboard...
      </div>
    );
  }

  const tests = analytics?.guard || [];
  const reussis = tests.filter(
    (test) => String(test.test_passed).toLowerCase() === "true"
  ).length;
  const tauxReussite = tests.length
    ? ((reussis / tests.length) * 100).toFixed(1)
    : null;

  const documentsRecents = stats?.documents_recents || [];

  return (
    <div className="documind-dashboard-root">
      <aside className="documind-dashboard-sidebar">
        <div className="documind-dashboard-brand">
          <span className="documind-dashboard-brand-mark">📊</span>
          DocuMind AI
        </div>

        <nav className="documind-dashboard-nav">
          <button
            type="button"
            className={
              "documind-dashboard-nav-item" +
              (sectionActive === "apercu" ? " is-active" : "")
            }
            onClick={() => allerALaSection("apercu", refApercu)}
          >
            <span className="documind-dashboard-nav-icon">🏠</span>
            Overview
          </button>

          <button
            type="button"
            className={
              "documind-dashboard-nav-item" +
              (sectionActive === "ragas" ? " is-active" : "")
            }
            onClick={() => allerALaSection("ragas", refRagas)}
          >
            <span className="documind-dashboard-nav-icon">🧠</span>
            RAGAS Evaluation
          </button>

          <button
            type="button"
            className={
              "documind-dashboard-nav-item" +
              (sectionActive === "guard" ? " is-active" : "")
            }
            onClick={() => allerALaSection("guard", refGuard)}
          >
            <span className="documind-dashboard-nav-icon">🛡️</span>
            Hallucination Guard
          </button>

          <button
            type="button"
            className={
              "documind-dashboard-nav-item" +
              (sectionActive === "documents" ? " is-active" : "")
            }
            onClick={() => allerALaSection("documents", refDocuments)}
          >
            <span className="documind-dashboard-nav-icon">📚</span>
            Documents
          </button>
        </nav>

        <button
          type="button"
          className="documind-dashboard-retour"
          onClick={onRetour}
        >
          ← Return to Chatbot
        </button>
      </aside>

      <main className="documind-dashboard-main">
        <div className="documind-dashboard-header">
          <div>
            <h1 className="documind-dashboard-title">DocuMind AI</h1>
            <p className="documind-dashboard-subtitle">
              Intelligent Document Analytics
            </p>
          </div>

          <span className="documind-dashboard-status">
            <span
              className={
                "documind-dashboard-status-dot" +
                (actualisation ? " is-loading" : "")
              }
            />
            {actualisation
              ? "Actualisation…"
              : "Données analytiques chargées · auto-actualisation 5s"}
          </span>
        </div>

        {erreur && <div className="documind-dashboard-error">{erreur}</div>}

        <section ref={refApercu} className="documind-dashboard-section">
          <div className="documind-dashboard-kpi-grid">
            {[
              ["📄", "Documents PDF", stats?.kpi?.documents],
              ["📑", "Pages analysées", stats?.kpi?.pages],
              ["💬", "Conversations", stats?.kpi?.conversations],
              ["❓", "Questions posées", stats?.kpi?.questions],
              ["🧩", "Chunks indexés", stats?.kpi?.chunks],
              ["⚡", "Interactions", stats?.kpi?.interactions],
            ].map(([icon, label, value]) => (
              <div className="documind-dashboard-kpi-card" key={label}>
                <div className="documind-dashboard-kpi-icon">{icon}</div>
                <div className="documind-dashboard-kpi-value">{value ?? 0}</div>
                <div className="documind-dashboard-kpi-label">{label}</div>
              </div>
            ))}
          </div>

          <div className="documind-dashboard-charts-grid">
            <div className="documind-dashboard-card">
              <h2 className="documind-dashboard-section-title">
                📈 Activité des 7 derniers jours
              </h2>
              <div className="documind-dashboard-chart-box">
                {activite.length ? (
                  <Line data={activiteChartData} options={optionsLigne} />
                ) : (
                  <p className="documind-dashboard-empty">
                    Aucune activité enregistrée pour le moment.
                  </p>
                )}
              </div>
            </div>

            <div className="documind-dashboard-card">
              <h2 className="documind-dashboard-section-title">
                ⚡ Types d'interactions
              </h2>
              <div className="documind-dashboard-chart-box">
                {interactionsParType.length ? (
                  <Doughnut
                    data={interactionsChartData}
                    options={optionsDoughnut}
                  />
                ) : (
                  <p className="documind-dashboard-empty">
                    Aucune interaction enregistrée pour le moment.
                  </p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section ref={refRagas} className="documind-dashboard-section">
          <div className="documind-dashboard-charts-grid">
            <div className="documind-dashboard-card">
              <h2 className="documind-dashboard-section-title">
                🧠 Évaluation RAGAS — Baseline vs Advanced
              </h2>
              <p className="documind-dashboard-section-hint">
                Moyennes calculées sur {new Set(comparaison.map((r) => r.question)).size || 0} question(s). Scores compris entre 0 et 1.
              </p>
              <div className="documind-dashboard-chart-box">
                {comparaison.length ? (
                  <Bar data={ragasChartData} options={optionsBarres} />
                ) : (
                  <p className="documind-dashboard-empty">
                    Aucune donnée de comparaison RAGAS disponible.
                  </p>
                )}
              </div>
            </div>

            <div className="documind-dashboard-card">
              <h2 className="documind-dashboard-section-title">
                ✅ Vérification des réponses IA
              </h2>
              <p className="documind-dashboard-verif-total">
                {totalVerifie} réponse(s) vérifiée(s) — verdicts enregistrés,
                ceci ne représente pas la précision globale du chatbot.
              </p>
              <div className="documind-dashboard-chart-box">
                {totalVerifie ? (
                  <Doughnut
                    data={verificationChartData}
                    options={optionsDoughnut}
                  />
                ) : (
                  <p className="documind-dashboard-empty">
                    Aucune réponse vérifiée pour le moment.
                  </p>
                )}
              </div>
              <div className="documind-dashboard-verif-legend">
                <span className="documind-dashboard-legend-item">
                  <span
                    className="documind-dashboard-legend-dot"
                    style={{ background: "#34d399" }}
                  />
                  Supported ({verification.supported ?? 0})
                </span>
                <span className="documind-dashboard-legend-item">
                  <span
                    className="documind-dashboard-legend-dot"
                    style={{ background: "#fbbf24" }}
                  />
                  Corrected ({verification.corrected ?? 0})
                </span>
                <span className="documind-dashboard-legend-item">
                  <span
                    className="documind-dashboard-legend-dot"
                    style={{ background: "#f87171" }}
                  />
                  Rejected ({verification.rejected ?? 0})
                </span>
              </div>
            </div>
          </div>
        </section>

        <section ref={refGuard} className="documind-dashboard-section">
          <div className="documind-dashboard-card">
            <h2 className="documind-dashboard-section-title">
              🛡️ Hallucination Guard
            </h2>

            <div className="documind-dashboard-guard-summary">
              <div className="documind-dashboard-guard-metric">
                <strong>{tests.length}</strong>
                <span>Tests exécutés</span>
              </div>
              <div className="documind-dashboard-guard-metric">
                <strong>{reussis}</strong>
                <span>Tests réussis</span>
              </div>
              <div className="documind-dashboard-guard-metric">
                <strong>{tauxReussite === null ? "N/A" : `${tauxReussite}%`}</strong>
                <span>Taux de réussite</span>
              </div>
            </div>

            {tests.length > 0 && tests.length < 5 && (
              <p className="documind-dashboard-guard-caveat">
                ⚠️ Taux calculé sur seulement {tests.length} test(s) enregistré(s) —
                ce n'est pas une garantie que le système ne génère jamais
                d'hallucinations.
              </p>
            )}

            {tests.length === 0 ? (
              <p className="documind-dashboard-empty">
                Aucun test du Hallucination Guard enregistré.
              </p>
            ) : (
              tests.map((test, index) => (
                <div className="documind-dashboard-guard-test" key={index}>
                  <p>
                    <strong>Question :</strong> {test.question}
                  </p>
                  <p>
                    <strong>Comportement attendu :</strong>{" "}
                    {test.expected_behavior}
                  </p>
                  <p>
                    <strong>Résultat :</strong> {test.actual_status}
                  </p>
                  <p>
                    <strong>Raison du refus :</strong>{" "}
                    {test.refusal_reason || "Non renseignée"}
                  </p>
                  <span
                    className={
                      "documind-dashboard-guard-badge " +
                      (String(test.test_passed).toLowerCase() === "true"
                        ? "is-pass"
                        : "is-fail")
                    }
                  >
                    {String(test.test_passed).toLowerCase() === "true"
                      ? "✓ Test réussi"
                      : "✗ Test échoué"}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>

        <section ref={refDocuments} className="documind-dashboard-section">
          <div className="documind-dashboard-card">
            <h2 className="documind-dashboard-section-title">
              📚 Documents PDF récents
            </h2>

            <div className="documind-dashboard-table-wrap">
              <table className="documind-dashboard-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Pages</th>
                    <th>Statut</th>
                    <th>Date d'import</th>
                  </tr>
                </thead>
                <tbody>
                  {documentsRecents.map((doc) => (
                    <tr key={doc.id}>
                      <td>📄 {doc.nom}</td>
                      <td>{doc.pages}</td>
                      <td>
                        <span
                          className={
                            "documind-dashboard-status-pill " +
                            (doc.index_status === "ready"
                              ? "is-ready"
                              : "is-pending")
                          }
                        >
                          {doc.index_status === "ready"
                            ? "✓ Prêt"
                            : doc.index_status}
                        </span>
                      </td>
                      <td>
                        {doc.created_at
                          ? new Date(doc.created_at).toLocaleString("fr-FR")
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {documentsRecents.length === 0 && (
                <p className="documind-dashboard-empty">
                  Aucun document récent.
                </p>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
