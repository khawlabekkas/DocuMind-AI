import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { urlFichier } from "../api.js";

// PDF.js lit le PDF dans un "worker" (thread séparé) pour ne pas bloquer la page
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfViewer({ documentId, page, rects, onPage }) {
  const [pdf, setPdf] = useState(null);
  const [echelle, setEchelle] = useState(1);
  const [erreur, setErreur] = useState("");
  const conteneur = useRef(null);
  const canvas = useRef(null);
  const premierSurlignage = useRef(null);

  // 1. Charger le PDF quand le document change
  useEffect(() => {
    if (!documentId) return;
    let annule = false;
    setPdf(null); setErreur("");
    const tache = pdfjsLib.getDocument(urlFichier(documentId));
    tache.promise
      .then((p) => !annule && setPdf(p))
      .catch((e) => !annule && setErreur("Impossible d'afficher le PDF : " + e.message));
    return () => { annule = true; tache.destroy(); };
  }, [documentId]);

  // 2. Dessiner la page dans le <canvas>
  useEffect(() => {
    if (!pdf) return;
    let rendu;
    pdf.getPage(page).then((p) => {
      const largeurDispo = conteneur.current.clientWidth - 24;
      const base = p.getViewport({ scale: 1 });           // taille en points PDF
      const s = largeurDispo / base.width;                // échelle "ajuster à la largeur"
      const viewport = p.getViewport({ scale: s });
      const ratio = window.devicePixelRatio || 1;         // écrans haute densité
      const c = canvas.current;
      c.width = viewport.width * ratio;
      c.height = viewport.height * ratio;
      c.style.width = `${viewport.width}px`;
      c.style.height = `${viewport.height}px`;
      const ctx = c.getContext("2d");
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      rendu = p.render({ canvasContext: ctx, viewport });
      rendu.promise.then(() => {
        setEchelle(s);
        premierSurlignage.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      }).catch(() => {});
    });
    return () => rendu?.cancel();
  }, [pdf, page, rects]);

  if (!documentId) return <div className="vide">Aucun document ouvert.</div>;

  return (
    <div className="viewer" ref={conteneur}>
      <div className="navigation">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}>◀</button>
        <span>Page {page} / {pdf?.numPages ?? "…"}</span>
        <button disabled={!pdf || page >= pdf.numPages} onClick={() => onPage(page + 1)}>▶</button>
      </div>
      {erreur && <p className="erreur">{erreur}</p>}
      <div className="page">
        <canvas ref={canvas} />
        {/* bbox PyMuPDF [x0,y0,x1,y1] en points, origine en haut à gauche -> pixels = points × échelle */}
        {rects.map(([x0, y0, x1, y1], i) => (
          <div
            key={i}
            ref={i === 0 ? premierSurlignage : null}
            className="surlignage"
            style={{
              left: x0 * echelle,
              top: y0 * echelle,
              width: (x1 - x0) * echelle,
              height: (y1 - y0) * echelle,
            }}
          />
        ))}
      </div>
    </div>
  );
}
