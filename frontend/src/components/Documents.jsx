import { useEffect, useRef, useState } from "react";
import { importerDocument, listerDocuments, supprimerDocument } from "../api.js";

const STATUTS = { indexing: "Indexation…", ready: "Prêt", error: "Erreur" };
export default function Documents({
  documents,
  setDocuments,
  selection,
  setSelection,
  onOuvrir,
  documentOuvert,
  afficherImport = true
}) {
 
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const input = useRef(null);

  const rafraichir = () => listerDocuments().then(setDocuments).catch((e) => setErreur(e.message));

  useEffect(() => { rafraichir(); }, []);

  // Tant qu'un PDF est en cours d'indexation, on redemande la liste toutes les 2 s
  useEffect(() => {
    if (!documents.some((d) => d.index_status === "indexing")) return;
    const t = setInterval(rafraichir, 2000);
    return () => clearInterval(t);
  }, [documents]);

  const importer = async (e) => {
    const fichier = e.target.files[0];
    if (!fichier) return;
    setErreur(""); setEnvoi(true);
    try {
      const res = await importerDocument(fichier);
      setSelection((s) => [...s, res.document_id]); // sélectionné d'office
      onOuvrir(res.document_id);
      await rafraichir();
    } catch (err) {
      setErreur(err.message);
    } finally {
      setEnvoi(false);
      input.current.value = "";
    }
  };

  const supprimer = async (id) => {
    if (!window.confirm("Supprimer ce document ?")) return;
    await supprimerDocument(id).catch((e) => setErreur(e.message));
    setSelection((s) => s.filter((x) => x !== id));
    rafraichir();
  };

  const basculer = (id) =>
    setSelection((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="documents">
     
{afficherImport && (
  <label className="bouton principal">
    {envoi ? "Import en cours…" : "+ Importer un PDF"}
    <input
      ref={input}
      type="file"
      accept="application/pdf"
      hidden
      onChange={importer}
      disabled={envoi}
    />
  </label>
)}

      {erreur && <p className="erreur">{erreur}</p>}
      <p className="aide">Cochez les documents à interroger.</p>
      <ul>
        {documents.map((d) => (
          <li key={d.id} className={d.id === documentOuvert ? "ouvert" : ""}>
            <input
              type="checkbox"
              checked={selection.includes(d.id)}
              disabled={d.index_status !== "ready"}
              onChange={() => basculer(d.id)}
            />
            <button className="nom" onClick={() => onOuvrir(d.id)} title={d.nom}>
              {d.nom}
            </button>
            <span className={`statut ${d.index_status}`}>
              {STATUTS[d.index_status]} · {d.pages} p.
            </span>
            <button className="supprimer" onClick={() => supprimer(d.id)} title="Supprimer">✕</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
