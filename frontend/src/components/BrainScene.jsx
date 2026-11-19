import { Component, Suspense, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, Sparkles, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { MeshSurfaceSampler } from "three/examples/jsm/math/MeshSurfaceSampler.js";

// Chemin servi depuis frontend/public/models/brain.glb (voir le README
// dans ce dossier). Modèle Grab3D, licence CC0.
const CHEMIN_MODELE = "/models/brain.glb";

// Le modèle Grab3D a son axe avant/arrière sur Z : une rotation d'un
// quart de tour présente la vue latérale de la maquette de référence.
const ROTATION_BASE = -Math.PI / 2;
const AMPLITUDE_BALANCEMENT = 0.42;
const NB_NEURONES = 460;
const LIAISONS_PAR_NEURONE = 3;

// Matériau lavande physiquement éclairé + liseré de Fresnel injecté dans
// le shader standard : les flancs des circonvolutions s'illuminent sans
// noyer le relief sous une émissivité uniforme.
function creerMateriauCerveau(original) {
  const materiau = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#8462ee"),
    roughness: 0.45,
    metalness: 0,
    roughnessMap: original?.roughnessMap ?? null,
    emissive: new THREE.Color("#33106a"),
    emissiveIntensity: 0.6,
  });

  materiau.onBeforeCompile = (shader) => {
    shader.uniforms.uRim = { value: new THREE.Color("#ff9cf2") };
    shader.uniforms.uRimForce = { value: 1.45 };
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        "#include <common>\nuniform vec3 uRim;\nuniform float uRimForce;"
      )
      .replace(
        "#include <emissivemap_fragment>",
        `#include <emissivemap_fragment>
        float dmFresnel = pow(1.0 - clamp(dot(normalize(normal), normalize(vViewPosition)), 0.0, 1.0), 2.4);
        totalEmissiveRadiance += uRim * dmFresnel * uRimForce;`
      );
  };

  return materiau;
}

// Prépare une seule fois (puis met en cache sur la scène glTF, réutilisée
// par useGLTF entre deux montages) : matériau, centre, taille et réseau
// de neurones échantillonné sur la vraie surface du modèle.
function preparerCerveau(scene) {
  if (scene.userData.documind) return scene.userData.documind;

  let maillage = null;
  scene.traverse((enfant) => {
    if (enfant.isMesh && !maillage) maillage = enfant;
  });

  scene.updateMatrixWorld(true);
  const relatif = new THREE.Matrix4()
    .copy(scene.matrixWorld)
    .invert()
    .multiply(maillage.matrixWorld);

  const original = Array.isArray(maillage.material)
    ? maillage.material[0]
    : maillage.material;
  maillage.material = creerMateriauCerveau(original);

  maillage.geometry.computeBoundingBox();
  const boite = maillage.geometry.boundingBox.clone().applyMatrix4(relatif);
  const centre = boite.getCenter(new THREE.Vector3());
  const taille = boite.getSize(new THREE.Vector3());

  // Neurones : points tirés sur la surface, légèrement décollés selon
  // la normale pour ne pas être masqués par le maillage lui-même.
  const echantillonneur = new MeshSurfaceSampler(maillage).build();
  const p = new THREE.Vector3();
  const n = new THREE.Vector3();
  const decalage = Math.max(taille.x, taille.y, taille.z) * 0.004;
  const points = [];
  for (let i = 0; i < NB_NEURONES; i++) {
    echantillonneur.sample(p, n);
    p.addScaledVector(n, decalage).applyMatrix4(relatif);
    points.push(p.clone());
  }

  const positions = new Float32Array(points.length * 3);
  const tailles = new Float32Array(points.length);
  const phases = new Float32Array(points.length);
  points.forEach((pt, i) => {
    pt.toArray(positions, i * 3);
    tailles[i] = Math.random() < 0.12 ? 15 + Math.random() * 9 : 5 + Math.random() * 6;
    phases[i] = Math.random() * Math.PI * 2;
  });

  // Voies neuronales : chaque neurone est relié à ses plus proches voisins
  // dans un rayon limité, ce qui dessine des filaments le long du cortex.
  const rayon = Math.max(taille.x, taille.y, taille.z) * 0.13;
  const segments = [];
  const dejaRelies = new Set();
  points.forEach((a, i) => {
    const voisins = points
      .map((b, j) => ({ j, d: a.distanceTo(b) }))
      .filter(({ j, d }) => j !== i && d < rayon)
      .sort((x, y) => x.d - y.d)
      .slice(0, LIAISONS_PAR_NEURONE);
    voisins.forEach(({ j }) => {
      const cle = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (dejaRelies.has(cle)) return;
      dejaRelies.add(cle);
      segments.push(a.x, a.y, a.z, points[j].x, points[j].y, points[j].z);
    });
  });

  scene.userData.documind = {
    centre,
    taille,
    positions,
    tailles,
    phases,
    segments: new Float32Array(segments),
  };
  return scene.userData.documind;
}

const NEURONES_VERTEX = `
  attribute float aTaille;
  attribute float aPhase;
  uniform float uTemps;
  uniform float uEchelle;
  varying float vEclat;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vEclat = 0.45 + 0.55 * (0.5 + 0.5 * sin(uTemps * 1.7 + aPhase));
    gl_PointSize = aTaille * uEchelle / -mv.z;
    gl_Position = projectionMatrix * mv;
  }
`;

const NEURONES_FRAGMENT = `
  uniform vec3 uCouleur;
  varying float vEclat;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float halo = pow(smoothstep(0.5, 0.0, d), 2.2);
    float coeur = smoothstep(0.12, 0.0, d);
    vec3 c = mix(uCouleur, vec3(1.0), coeur * 0.8);
    gl_FragColor = vec4(c, (halo + coeur) * vEclat);
  }
`;

const ANNEAU_VERTEX = `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const ANNEAU_FRAGMENT = `
  uniform float uTemps;
  uniform vec3 uCouleur;
  varying vec2 vUv;
  void main() {
    float angle = vUv.x * 6.2831853;
    float eclat = pow(0.5 + 0.5 * cos(angle - uTemps * 0.35), 4.0);
    gl_FragColor = vec4(uCouleur * (0.7 + eclat), 0.1 + 0.9 * eclat);
  }
`;

function CerveauModele() {
  const { scene } = useGLTF(CHEMIN_MODELE);
  const donnees = useMemo(() => preparerCerveau(scene), [scene]);
  const { viewport, gl } = useThree();
  const pivot = useRef(null);

  // Échelle calculée depuis la bounding box mesurée et la taille réelle
  // du canvas : le cerveau (balancement + flottement compris) et son
  // anneau restent toujours entièrement dans le cadre.
  const { echelle, largeurVue, hauteurVue } = useMemo(() => {
    const { x, y, z } = donnees.taille;
    const largeurMax =
      z * Math.cos(AMPLITUDE_BALANCEMENT) + x * Math.sin(AMPLITUDE_BALANCEMENT);
    const e = Math.min(
      (viewport.height * 0.8) / y,
      (viewport.width * 0.52) / largeurMax
    );
    return { echelle: e, largeurVue: z * e, hauteurVue: y * e };
  }, [donnees, viewport.width, viewport.height]);

  const geometrieNeurones = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(donnees.positions, 3));
    g.setAttribute("aTaille", new THREE.BufferAttribute(donnees.tailles, 1));
    g.setAttribute("aPhase", new THREE.BufferAttribute(donnees.phases, 1));
    return g;
  }, [donnees]);

  const geometrieVoies = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(donnees.segments, 3));
    return g;
  }, [donnees]);

  const uniformsNeurones = useMemo(
    () => ({
      uTemps: { value: 0 },
      uEchelle: { value: 1 },
      uCouleur: { value: new THREE.Color("#ff6ad5") },
    }),
    []
  );

  const uniformsAnneau = useMemo(
    () => ({ uTemps: { value: 0 }, uCouleur: { value: new THREE.Color("#ff79d9") } }),
    []
  );

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (pivot.current) {
      pivot.current.rotation.y =
        ROTATION_BASE + Math.sin(t * 0.22) * AMPLITUDE_BALANCEMENT;
    }
    uniformsNeurones.uTemps.value = t;
    uniformsNeurones.uEchelle.value = 7 * gl.getPixelRatio();
    uniformsAnneau.uTemps.value = t;
  });

  const { centre } = donnees;
  const rayonAnneau = largeurVue * 0.68;

  return (
    <>
      <group ref={pivot} rotation={[0.1, ROTATION_BASE, 0]} scale={echelle}>
        <group position={[-centre.x, -centre.y, -centre.z]}>
          <primitive object={scene} />

          <lineSegments geometry={geometrieVoies}>
            <lineBasicMaterial
              color="#ff4fd0"
              transparent
              opacity={0.7}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </lineSegments>

          <points geometry={geometrieNeurones}>
            <shaderMaterial
              uniforms={uniformsNeurones}
              vertexShader={NEURONES_VERTEX}
              fragmentShader={NEURONES_FRAGMENT}
              transparent
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </points>
        </group>
      </group>

      {/* Anneau orbital incliné : sa partie arrière est masquée par le
          cerveau grâce au test de profondeur, comme sur la maquette. */}
      <mesh
        position={[0, -hauteurVue * 0.12, 0]}
        rotation={[Math.PI / 2 - 0.3, 0.08, -0.12]}
      >
        <torusGeometry args={[rayonAnneau, rayonAnneau * 0.0045, 8, 200]} />
        <shaderMaterial
          uniforms={uniformsAnneau}
          vertexShader={ANNEAU_VERTEX}
          fragmentShader={ANNEAU_FRAGMENT}
          transparent
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </>
  );
}

// Forme de secours affichée si brain.glb est introuvable (404) ou
// si le chargement échoue, pour que l'écran d'accueil ne casse jamais.
function CerveauSecours() {
  const groupe = useRef(null);

  useFrame((_, delta) => {
    if (groupe.current) {
      groupe.current.rotation.y += delta * 0.1;
    }
  });

  return (
    <group ref={groupe}>
      <mesh>
        <icosahedronGeometry args={[2.4, 2]} />
        <meshStandardMaterial
          color="#140a1f"
          emissive="#c026d3"
          emissiveIntensity={0.6}
          wireframe
        />
      </mesh>
    </group>
  );
}

// Limite les erreurs de chargement du modèle (ex. fichier absent) à ce
// composant : le reste de l'application continue de fonctionner.
class LimiteErreurModele extends Component {
  constructor(props) {
    super(props);
    this.state = { enErreur: false };
  }

  static getDerivedStateFromError() {
    return { enErreur: true };
  }

  componentDidCatch(erreur) {
    console.warn("Brain model indisponible, affichage du modèle de secours :", erreur);
  }

  render() {
    if (this.state.enErreur) return this.props.secours;
    return this.props.children;
  }
}

// Limite les erreurs d'initialisation du Canvas/WebGL lui-même
// (ex. navigateur sans support WebGL). Repli 100% CSS, sans three.js.
class LimiteErreurCanvas extends Component {
  constructor(props) {
    super(props);
    this.state = { enErreur: false };
  }

  static getDerivedStateFromError() {
    return { enErreur: true };
  }

  componentDidCatch(erreur) {
    console.warn("WebGL indisponible, repli CSS statique :", erreur);
  }

  render() {
    if (this.state.enErreur) return this.props.secours;
    return this.props.children;
  }
}

function SceneCanvas() {
  return (
    <Canvas
      className="documind-brain-canvas"
      camera={{ position: [0, 0, 8], fov: 34 }}
      dpr={[1, 1.75]}
      gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
    >
      {/* Ambiance violette douce : les sillons restent lisibles. */}
      <ambientLight intensity={0.34} color="#a98fff" />

      {/* Lumière clé en hauteur, à gauche, comme sur la maquette : elle
          sculpte les circonvolutions (ombres + reflets). */}
      <directionalLight position={[-3, 5, 4]} intensity={2.6} color="#f1e9ff" />

      {/* Contre-jours magenta/violet pour le liseré lumineux des bords. */}
      <pointLight position={[3.5, -1.5, -2.5]} intensity={22} color="#ec4899" />
      <pointLight position={[-3.5, 1.5, -2.5]} intensity={16} color="#8b5cf6" />
      <pointLight position={[0, -2.2, 2.5]} intensity={6} color="#f472b6" />

      <Float speed={1.1} rotationIntensity={0.08} floatIntensity={0.8}>
        <LimiteErreurModele secours={<CerveauSecours />}>
          <Suspense fallback={null}>
            <CerveauModele />
          </Suspense>
        </LimiteErreurModele>
      </Float>

      <Sparkles
        count={55}
        scale={[11, 5, 3]}
        size={2.4}
        speed={0.25}
        opacity={0.7}
        noise={0.6}
        color="#f9a8d4"
      />
    </Canvas>
  );
}

// Repli entièrement CSS (aucun WebGL requis) si le Canvas ne peut
// pas s'initialiser du tout dans le navigateur de l'utilisateur.
function RepliStatique() {
  return <div className="documind-brain-fallback" />;
}

export default function BrainScene() {
  return (
    <LimiteErreurCanvas secours={<RepliStatique />}>
      <SceneCanvas />
    </LimiteErreurCanvas>
  );
}
