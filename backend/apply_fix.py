from pathlib import Path
import re, shutil, sys

root = Path(__file__).resolve().parent
# Run from project root: python path/to/apply_fix.py [project_root]
project = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
front = project/'frontend/src/components/Chatbot.jsx'
main = project/'backend/main.py'
agent = project/'backend/analysis_agent.py'
for p in (front,main,agent):
    if not p.exists(): raise SystemExit(f'Missing file: {p}')
files = {p:p.read_text(encoding='utf-8') for p in (front,main,agent)}

def replace_once(src, old, new, name):
    if src.count(old)!=1: raise ValueError(f'{name}: expected one match, found {src.count(old)}')
    return src.replace(old,new,1)

try:
    s=files[front]
    # Keep existing detectors and routes unchanged; add a dedicated full-analysis intent.
    marker='const envoyer = async (e) => {'
    helper='''// Dedicated full-document analysis intent; does not intercept ordinary questions.
const detecterAnalyseComplete = (texte) => {
  const q = texte.trim();
  const commande = /^(?:(?:please|can you|could you|s'il te plaît|svp)\\s+)?(?:analy[sz]e|analyse[rz]?|análisis|analiza|analizar|حلل|تحليل)\\b?/iu;
  // Arabic word boundaries are not reliable in JS; check Arabic separately.
  const demande = /^(?:analy[sz]e|analyse[rz]?|analiza|analizar)\\b/i.test(q)
    || /^(?:حلل|تحليل)(?:\\s|$)/u.test(q)
    || /^(?:please\\s+|can you\\s+|could you\\s+)(?:analy[sz]e|analyse[rz]?)\\b/i.test(q);
  if (!demande) return false;
  return /\\b(document|pdf|file|fichier|texte|text|documento|archivo)\\b/i.test(q)
    || /(?:المستند|الوثيقة|الملف)/u.test(q)
    || /^(?:analy[sz]e|analyse[rz]?|analiza|analizar|حلل|تحليل)[.!?\\s]*$/iu.test(q);
};

const langueAnalyseComplete = (texte) => {
  const q = texte.toLowerCase();
  if (/(?:in|en)\\s+(?:spanish|espagnol)\\b|(?:بالإسبانية)/iu.test(q)) return "es";
  if (/(?:in|en)\\s+(?:arabic|arabe)\\b|(?:بالعربية)/iu.test(q)) return "ar";
  if (/(?:in|en)\\s+(?:english|anglais)\\b|(?:بالإنجليزية)/iu.test(q)) return "en";
  if (/(?:in|en)\\s+(?:french|français|francais)\\b|(?:بالفرنسية)/iu.test(q)) return "fr";
  if (/[\\u0600-\\u06ff]/u.test(q)) return "ar";
  if (/\\b(?:analiza|analizar|análisis|documento|archivo|este|esta|por favor)\\b/i.test(q)) return "es";
  return detecterLangueDemande(texte);
};

'''
    s=replace_once(s,marker,helper+marker,'frontend helper')
    marker='if (intention?.type === "resume") {'
    # Only full analysis requests; existing intent branches still take precedence for other commands.
    route='''if (detecterAnalyseComplete(q)) {
  const document_id = documentOuvert || (selection.length === 1 ? selection[0] : null);
  ajouter({ role: "user", texte: q });
  if (!document_id) {
    ajouter({ role: "erreur", texte: "Ouvrez un PDF ou sélectionnez un seul document à analyser." });
    return;
  }
  setAttente(true);
  try {
    const resultat = await lancerAnalyse({
      document_id,
      type: "full",
      langue: langueAnalyseComplete(q)
    });
    ajouter({
      role: "assistant",
      texte: resultat.result,
      citations: resultat.citations || [],
      verdict: null,
      refus: null
    });
    await enregistrerAnalyse(q, resultat.result, resultat.citations || [], "full");
  } catch (erreur) {
    ajouter({ role: "erreur", texte: `Erreur d'analyse : ${erreur.message}` });
  } finally {
    setAttente(false);
  }
  return;
}

'''
    s=replace_once(s,marker,route+marker,'frontend route')
    # Explicit button full analysis remains in French (existing button label is French).
    files[front]=s

    s=files[main]
    s=replace_once(s,'    section: str | None = None     # pour "explain"','    section: str | None = None     # pour "explain"\n    langue: str = "fr"              # uniquement pour "full"','main model')
    s=replace_once(s,'res = analyser_document_complet(d.document_id, pages, etat.llm, db.obtenir_positions)','res = analyser_document_complet(d.document_id, pages, etat.llm, db.obtenir_positions, langue=d.langue)','main call')
    files[main]=s

    s=files[agent]
    s=replace_once(s,'def _map_reduce(passages, llm, consigne):','def _map_reduce(passages, llm, consigne, systeme=SYSTEME):','map reduce signature')
    # All 3 SYSTEME uses inside _map_reduce only.
    a=s.index('def _map_reduce('); b=s.index('# ----------------------------------------------------------- Explication',a)
    part=s[a:b]
    if part.count('SYSTEME')!=4: raise ValueError(f'map-reduce SYSTEME references unexpected: {part.count("SYSTEME")}')
    part=part.replace('            SYSTEME\n','            systeme\n').replace('                SYSTEME\n','                systeme\n')
    # replace remaining SYSTEME arguments (different indent)
    part=re.sub(r'(?m)^(\s*)SYSTEME(\s*)$',r'\1systeme\2',part)
    s=s[:a]+part+s[b:]
    old='''def analyser_document_complet(document_id: str, pages: list[dict], llm,
                              obtenir_positions) -> dict:'''
    new='''def analyser_document_complet(document_id: str, pages: list[dict], llm,
                              obtenir_positions, langue: str = "fr") -> dict:'''
    s, count = re.subn(r'def analyser_document_complet\(document_id:\s*str,\s*pages:\s*list\[dict\],\s*llm,\s*obtenir_positions\s*\)\s*->\s*dict:', new, s, count=1)
    if count != 1: raise ValueError(f'agent signature: expected one match, found {count}')
    a=s.index('def analyser_document_complet(')
    section=s[a:]
    old='''    consigne = ("Analyse ce document : 1) sujet et objectif 2) structure (parties et pages) "
                "3) idées clés 4) conclusion")'''
    new='''    langues = {"fr": "français", "en": "anglais", "es": "espagnol", "ar": "arabe"}
    if langue not in langues:
        raise ValueError("Langue non supportée pour l'analyse complète.")
    systeme_analyse = (
        "Tu es DocuMind. Tu travailles UNIQUEMENT à partir des extraits fournis. "
        "Cite tes sources avec le numéro de l'extrait entre crochets, ex. [1] ou [2][3]. "
        f"Réponds intégralement en {langues[langue]}. "
        "Conserve les citations et n'invente aucune information."
    )
    consigne = ("Analyse ce document : 1) sujet et objectif 2) structure (parties et pages) "
                "3) idées clés 4) conclusion")'''
    section=replace_once(section,old,new,'agent instruction')
    section=replace_once(section,'+ _numeroter(passages), SYSTEME)','+ _numeroter(passages), systeme_analyse)','agent short analysis')
    section=replace_once(section,'_map_reduce(passages, llm, consigne)','_map_reduce(passages, llm, consigne, systeme=systeme_analyse)','agent long analysis')
    s=s[:a]+section
    files[agent]=s
    for p,s in files.items():
        if p.suffix=='.py': compile(s,str(p),'exec')
    for p,s in files.items():
        backup=p.with_suffix(p.suffix+'.before_language_fix.bak')
        if backup.exists(): raise ValueError(f'Backup already exists: {backup}')
    for p,s in files.items():
        shutil.copy2(p,p.with_suffix(p.suffix+'.before_language_fix.bak'))
        p.write_text(s,encoding='utf-8')
    print('SUCCESS: updated only Chatbot.jsx, main.py, analysis_agent.py. Backups created.')
except Exception as exc:
    raise SystemExit(f'No changes applied: {exc}')
