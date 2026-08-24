import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";

const STATUS_COLORS = { open: 0x16835f, closed: 0x707b77, maintenance: 0xc08319, secured: 0x315f8c };
const CAMERA_PRESETS = {
  overview: [[18, 17, 22], [0, 0, 0]], top: [[0, 30, 0.01], [0, 0, 0]],
  "facade-1": [[0, 7, 29], [0, 1, 0]], "facade-2": [[29, 7, 0], [0, 1, 0]],
};

function readDoorCards() {
  return new Map([...document.querySelectorAll(".engineering-card")].map((card) => [card.dataset.number, {
    number: card.dataset.number, status: card.dataset.status, employees: Number(card.dataset.employees),
    incidents: Number(card.dataset.incidents), maintenance: Number(card.dataset.maintenance), card,
  }]));
}

export async function mountEngineering3D(panel) {
  if (panel.dataset.mounted) return;
  panel.dataset.mounted = "true";
  const viewport = panel.querySelector("[data-3d-viewport]");
  const loading = panel.querySelector("[data-3d-loading]");
  const progress = panel.querySelector("[data-3d-progress]");
  const progressLabel = panel.querySelector("[data-3d-progress-label]");
  const setProgress = (value) => { progress.value = value; progressLabel.textContent = `${value}%`; };
  setProgress(10);

  const [anchorResponse] = await Promise.all([fetch(panel.dataset.anchorsUrl, { credentials: "same-origin" })]);
  if (!anchorResponse.ok) throw new Error("anchors-unavailable");
  const anchorConfig = await anchorResponse.json();
  setProgress(30);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x10251f);
  scene.fog = new THREE.Fog(0x10251f, 34, 70);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 120);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  viewport.append(renderer.domElement);
  const labelRenderer = new CSS2DRenderer();
  labelRenderer.domElement.className = "engineering-3d__labels";
  viewport.append(labelRenderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.minDistance = 8; controls.maxDistance = 52; controls.maxPolarAngle = Math.PI * 0.49;
  controls.enablePan = true;

  scene.add(new THREE.HemisphereLight(0xf4fff9, 0x3d382b, 2.4));
  const sun = new THREE.DirectionalLight(0xfff1cf, 3.2);
  sun.position.set(12, 22, 10); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = -25; sun.shadow.camera.right = 25; sun.shadow.camera.top = 25; sun.shadow.camera.bottom = -25;
  scene.add(sun);

  const modelRoot = new THREE.Group();
  scene.add(modelRoot);
  const placeholder = buildVisualPlaceholder();
  modelRoot.add(placeholder);
  // GLTFLoader is kept in the local runtime so a reviewed, licensed GLB can replace the visual placeholder without changing telemetry.
  const gltfLoader = new GLTFLoader();
  if (panel.dataset.modelUrl) {
    await new Promise((resolve, reject) => gltfLoader.load(panel.dataset.modelUrl, (gltf) => {
      modelRoot.clear(); modelRoot.add(gltf.scene); resolve();
    }, (event) => setProgress(event.total ? Math.round((event.loaded / event.total) * 60) + 30 : 60), reject));
  }
  setProgress(65);

  let doorData = readDoorCards();
  let selectedDoor = null;
  const markers = new Map();
  const pickables = [];
  const markerRoot = new THREE.Group();
  scene.add(markerRoot);
  anchorConfig.doors.forEach((anchor) => {
    const group = new THREE.Group(); group.position.fromArray(anchor.position);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.38, 24), new THREE.MeshBasicMaterial({ color: STATUS_COLORS.open, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2; ring.userData.door = anchor.door; group.add(ring); pickables.push(ring);
    const element = document.createElement("button"); element.type = "button"; element.className = "engineering-3d-door";
    element.innerHTML = `<span>${anchor.door}</span><small><span class="engineering-3d-door__employees"></span> <span class="engineering-3d-door__incidents"></span> <span class="engineering-3d-door__maintenance"></span></small>`;
    element.setAttribute("aria-label", `فتح تفاصيل الباب ${anchor.door}`);
    element.addEventListener("click", () => selectDoor(anchor.door, true));
    const label = new CSS2DObject(element); label.position.set(0, 1, 0); group.add(label);
    markerRoot.add(group); markers.set(anchor.door, { group, ring, label, element, anchor });
  });
  setProgress(85);

  function render() { renderer.render(scene, camera); labelRenderer.render(scene, camera); }
  function resize() {
    const width = Math.max(viewport.clientWidth, 1), height = Math.max(viewport.clientHeight, 1);
    camera.aspect = width / height; camera.updateProjectionMatrix(); renderer.setSize(width, height, false); labelRenderer.setSize(width, height); render();
  }
  const observer = new ResizeObserver(resize); observer.observe(viewport);
  controls.addEventListener("change", render);

  function applyDoorData() {
    markers.forEach((marker, number) => {
      const item = doorData.get(number); if (!item) { marker.group.visible = false; return; }
      marker.group.visible = true;
      marker.ring.material.color.setHex(STATUS_COLORS[item.status] || STATUS_COLORS.closed);
      marker.element.className = `engineering-3d-door is-${item.status}${item.incidents || item.maintenance ? " has-alert" : ""}`;
      marker.element.querySelector(".engineering-3d-door__employees").textContent = `👥 ${item.employees}`;
      marker.element.querySelector(".engineering-3d-door__incidents").textContent = `⚠ ${item.incidents}`;
      marker.element.querySelector(".engineering-3d-door__maintenance").textContent = `◆ ${item.maintenance}`;
      marker.element.title = `الباب ${number} · موظفون ${item.employees} · بلاغات ${item.incidents} · صيانة ${item.maintenance}`;
    });
    const missing = [...doorData.keys()].filter((number) => !markers.has(number));
    panel.querySelector("[data-3d-unplaced]").hidden = !missing.length;
    panel.querySelector("[data-3d-unplaced-list]").textContent = missing.join("، ");
    if (selectedDoor) renderDrawer(selectedDoor);
    render();
  }

  function renderDrawer(number) {
    const item = doorData.get(number); if (!item) return;
    const statusText = item.card.querySelector("[data-metric='status']")?.textContent.trim() || item.status;
    const links = [...item.card.querySelectorAll(".engineering-card__drawer nav a")].map((link) => link.outerHTML).join("");
    panel.querySelector("[data-3d-drawer-content]").innerHTML = `<small>بيانات منصة أبواب التشغيلية</small><h3>الباب ${number}</h3><dl><div><dt>الحالة</dt><dd>${statusText}</dd></div><div><dt>الموظفون</dt><dd>${item.employees}</dd></div><div><dt>البلاغات المفتوحة</dt><dd>${item.incidents}</dd></div><div><dt>طلبات الصيانة</dt><dd>${item.maintenance}</dd></div></dl><nav>${links}</nav>`;
    panel.querySelector("[data-3d-drawer]").hidden = false;
  }

  function moveCamera(position, target, animate = true) {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startPosition = camera.position.clone(), startTarget = controls.target.clone();
    if (!animate || reduced) { camera.position.fromArray(position); controls.target.fromArray(target); controls.update(); render(); return; }
    const started = performance.now(), duration = 450;
    const frame = (now) => { const t = Math.min((now - started) / duration, 1), eased = 1 - ((1 - t) ** 3); camera.position.lerpVectors(startPosition, new THREE.Vector3(...position), eased); controls.target.lerpVectors(startTarget, new THREE.Vector3(...target), eased); controls.update(); render(); if (t < 1) requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
  }

  function selectDoor(number, focus = false) {
    const marker = markers.get(number); if (!marker || !doorData.has(number)) return false;
    selectedDoor = number; renderDrawer(number);
    if (focus) moveCamera([marker.anchor.position[0] * 1.2, 6, marker.anchor.position[2] * 1.2 + 5], marker.anchor.position, true);
    return true;
  }

  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  renderer.domElement.addEventListener("pointerup", (event) => {
    const rect = renderer.domElement.getBoundingClientRect(); pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera); const hit = raycaster.intersectObjects(pickables, false)[0]; if (hit) selectDoor(hit.object.userData.door, false);
  });
  panel.querySelector("[data-3d-search]").addEventListener("change", (event) => { const exact = event.target.value.trim().toUpperCase(); if (exact) selectDoor(exact, true); });
  panel.querySelectorAll("[data-3d-camera]").forEach((button) => button.addEventListener("click", () => moveCamera(...CAMERA_PRESETS[button.getAttribute("data-3d-camera")])));
  panel.querySelector("[data-3d-reset]").addEventListener("click", () => moveCamera(...CAMERA_PRESETS.overview));
  panel.querySelector("[data-3d-drawer-close]").addEventListener("click", () => { selectedDoor = null; panel.querySelector("[data-3d-drawer]").hidden = true; });
  panel.querySelector("[data-3d-fullscreen]").addEventListener("click", () => panel.requestFullscreen?.());

  function setQuality(value) {
    const automatic = (navigator.hardwareConcurrency || 4) >= 8 ? "high" : "medium";
    const quality = value === "auto" ? automatic : value;
    const ratio = quality === "high" ? Math.min(devicePixelRatio, 2) : quality === "medium" ? Math.min(devicePixelRatio, 1.35) : 1;
    renderer.setPixelRatio(ratio); renderer.shadowMap.enabled = quality !== "economy"; labelRenderer.domElement.hidden = quality === "economy"; resize();
  }
  panel.querySelector("[data-3d-quality]").addEventListener("change", (event) => setQuality(event.target.value));
  panel.querySelectorAll("[data-3d-layer]").forEach((input) => input.addEventListener("change", () => {
    const layer = input.getAttribute("data-3d-layer");
    if (layer === "labels") labelRenderer.domElement.hidden = !input.checked;
    else if (layer === "status") markers.forEach((marker) => { marker.ring.visible = input.checked; });
    else panel.classList.toggle(`engineering-3d--hide-${layer}`, !input.checked);
    render();
  }));
  panel.closest(".engineering-center").addEventListener("engineering:center-refreshed", () => { doorData = readDoorCards(); applyDoorData(); });

  moveCamera(...CAMERA_PRESETS.overview, false); setQuality("auto"); applyDoorData(); setProgress(100); loading.hidden = true; resize();
}

function buildVisualPlaceholder() {
  const root = new THREE.Group(); root.name = "VISUAL_PLACEHOLDER";
  const stone = new THREE.MeshStandardMaterial({ color: 0xe9dfc5, roughness: 0.72, metalness: 0.02 });
  const side = new THREE.MeshStandardMaterial({ color: 0xcab98f, roughness: 0.82 });
  const green = new THREE.MeshStandardMaterial({ color: 0x126448, roughness: 0.55, metalness: 0.05 });
  const plaza = new THREE.Mesh(new THREE.BoxGeometry(25, 0.3, 19), new THREE.MeshStandardMaterial({ color: 0xbcb79f, roughness: 0.95 }));
  plaza.position.y = -0.2; plaza.receiveShadow = true; root.add(plaza);
  const lod = new THREE.LOD();
  const high = new THREE.Group();
  [[0,1.2,0,14,2.4,9],[-6,1,-1.5,3.5,2,6],[6,1,-1.5,3.5,2,6]].forEach(([x,y,z,w,h,d]) => { const mesh = new THREE.Mesh(new THREE.BoxGeometry(w,h,d,4,2,3), stone); mesh.position.set(x,y,z); mesh.castShadow = true; mesh.receiveShadow = true; high.add(mesh); });
  const courtyard = new THREE.Mesh(new THREE.BoxGeometry(4.2,.12,3.2), side); courtyard.position.set(0,2.45,0); high.add(courtyard);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(1,32,18,0,Math.PI*2,0,Math.PI/2), green); dome.position.set(3.2,3.25,-1.4); dome.castShadow = true; high.add(dome);
  [[-7,-4.6],[7,-4.6],[-7,4.6],[7,4.6]].forEach(([x,z]) => { const tower = new THREE.Mesh(new THREE.CylinderGeometry(.18,.35,6,16), stone); tower.position.set(x,3,z); tower.castShadow = true; high.add(tower); });
  const low = new THREE.Mesh(new THREE.BoxGeometry(14,2.4,9), stone); low.position.y = 1.2;
  lod.addLevel(high, 0); lod.addLevel(low, 38); root.add(lod);
  return root;
}
