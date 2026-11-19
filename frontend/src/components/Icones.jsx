// Icônes SVG en ligne (aucune dépendance). Elles héritent de
// `currentColor`, la couleur est donc pilotée par le CSS.

function Svg({ children, taille = 20, className = "", epaisseur = 1.7 }) {
  return (
    <svg
      className={className}
      width={taille}
      height={taille}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={epaisseur}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const IconeCerveau = (p) => (
  <Svg {...p}>
    <path d="M12 5.2a3 3 0 0 0-5.4-1.6A3 3 0 0 0 4 7.6a3 3 0 0 0-.6 5A3.4 3.4 0 0 0 7 18.3a3 3 0 0 0 5 1.5z" />
    <path d="M12 5.2a3 3 0 0 1 5.4-1.6A3 3 0 0 1 20 7.6a3 3 0 0 1 .6 5 3.4 3.4 0 0 1-3.6 5.7 3 3 0 0 1-5 1.5z" />
    <path d="M12 5.2v14.6" />
    <path d="M7.6 9.2c1.1.2 1.9.9 2.3 2" />
    <path d="M16.4 9.2c-1.1.2-1.9.9-2.3 2" />
    <path d="M7.2 14.1c1-.2 2 .1 2.8.9" />
    <path d="M16.8 14.1c-1-.2-2 .1-2.8.9" />
  </Svg>
);

export const IconePlus = (p) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const IconeBulle = (p) => (
  <Svg {...p}>
    <path d="M20 11.5a7.5 7.5 0 0 1-11 6.6L4 19.5l1.4-4.6A7.5 7.5 0 1 1 20 11.5z" />
  </Svg>
);

export const IconeGraphique = (p) => (
  <Svg {...p}>
    <path d="M5 20v-6M10 20V9M15 20v-8M20 20V5" />
  </Svg>
);

export const IconeAnalyser = (p) => (
  <Svg {...p}>
    <path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4" />
    <path d="M13.5 3 19 8.5V11" />
    <path d="M13.5 3v5.5H19" />
    <path d="M8.5 11h4M8.5 14.5h2.5" />
    <circle cx="16.2" cy="16.2" r="3.2" />
    <path d="m18.6 18.6 2.4 2.4" />
  </Svg>
);

export const IconeTraduire = (p) => (
  <Svg {...p}>
    <path d="M3 6h10M8 3.5V6" />
    <path d="M5 6c.9 3.2 3.2 5.7 6.3 7" />
    <path d="M11 6c-.9 3.2-3.2 5.7-6.6 7.2" />
    <path d="m12.5 21 4.2-10 4.3 10" />
    <path d="M14 17.6h5.4" />
  </Svg>
);

export const IconeBouclier = (p) => (
  <Svg {...p}>
    <path d="M12 3 4.5 6v5.6c0 4.6 3.1 8 7.5 9.4 4.4-1.4 7.5-4.8 7.5-9.4V6z" />
    <path d="m8.8 12 2.3 2.3 4.2-4.4" />
  </Svg>
);

export const IconeChevron = (p) => (
  <Svg {...p}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);

export const IconeEtincelle = (p) => (
  <Svg {...p}>
    <path d="M12 3c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7z" />
    <path d="M19 15.5c.2 1.4.8 2 2.2 2.2-1.4.2-2 .8-2.2 2.2-.2-1.4-.8-2-2.2-2.2 1.4-.2 2-.8 2.2-2.2z" />
  </Svg>
);

export const IconeTrombone = (p) => (
  <Svg {...p}>
    <path d="m20 11.4-8 8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.4 3.4 0 0 1 4.8 4.8l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.4l7.7-7.7" />
  </Svg>
);

export const IconeEnvoyer = (p) => (
  <Svg {...p}>
    <path d="M21 3 10.5 13.5" />
    <path d="M21 3 14.5 21l-4-7.5L3 9.5z" />
  </Svg>
);

export const IconeDocument = (p) => (
  <Svg {...p}>
    <path d="M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8z" />
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M8.5 12.5h7M8.5 16h5" />
  </Svg>
);
