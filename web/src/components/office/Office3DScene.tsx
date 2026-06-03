"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

type OfficeRole = "PM" | "FE" | "BE" | "QA";

type OfficeAgent = {
  id: string;
  name: string;
  role: OfficeRole;
  status: string;
  tokens?: string;
};

type Office3DSceneProps = {
  agents: OfficeAgent[];
  selected: string;
  setSelected: (agentId: string) => void;
};

type MarkerHandle = {
  role: OfficeRole;
  group: THREE.Group;
  bodyMaterial: THREE.MeshStandardMaterial;
  ringMaterial: THREE.MeshBasicMaterial;
  label?: THREE.Sprite;
  hitTarget: THREE.Object3D;
  light: THREE.PointLight;
};

type DisposableMaterial = {
  dispose: () => void;
};

const ROLE_CONFIG: Record<OfficeRole, { color: string; position: [number, number, number] }> = {
  PM: { color: "#f6c945", position: [-2.55, 0.42, -1.08] },
  FE: { color: "#3b82f6", position: [-0.85, 0.42, -0.9] },
  BE: { color: "#8b5cf6", position: [0.9, 0.42, -0.9] },
  QA: { color: "#ec4899", position: [-0.78, 0.42, 0.78] },
};

const ROLE_ORDER: OfficeRole[] = ["PM", "FE", "BE", "QA"];

function isRole(value: string): value is OfficeRole {
  return ROLE_ORDER.includes(value as OfficeRole);
}

function statusTone(status?: string) {
  const raw = (status ?? "").toLowerCase();
  if (raw.includes("run") || raw.includes("work") || raw.includes("online")) return "#34d399";
  if (raw.includes("idle")) return "#94a3b8";
  if (raw.includes("away") || raw.includes("offline") || raw.includes("error")) return "#f59e0b";
  return "#60a5fa";
}

function selectedRoleFor(agents: OfficeAgent[], selected: string): OfficeRole | null {
  const agent = agents.find((item) => item.id === selected);
  if (agent) return agent.role;
  return isRole(selected) ? selected : null;
}

function selectedAgentForRole(agents: OfficeAgent[], role: OfficeRole) {
  return agents.find((agent) => agent.role === role);
}

function makeLabelTexture(role: OfficeRole, title: string, status: string, color: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 192;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "rgba(255, 253, 248, 0.92)";
  roundRect(ctx, 14, 18, 484, 132, 26);
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 4;
  ctx.stroke();

  ctx.fillStyle = color;
  ctx.font = "700 44px Arial, sans-serif";
  ctx.fillText(role, 38, 76);

  ctx.fillStyle = "rgba(31, 42, 55, 0.95)";
  ctx.font = "600 28px Arial, sans-serif";
  ctx.fillText(title.slice(0, 22), 132, 66);

  ctx.fillStyle = "rgba(99, 112, 131, 0.95)";
  ctx.font = "500 24px Arial, sans-serif";
  ctx.fillText(status, 132, 108);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function disposeLabel(label?: THREE.Sprite) {
  if (!label) return;
  const material = label.material as THREE.SpriteMaterial;
  material.map?.dispose();
  material.dispose();
}

function createMarker(role: OfficeRole) {
  const config = ROLE_CONFIG[role];
  const color = new THREE.Color(config.color);
  const group = new THREE.Group();
  group.name = `dipeen_agent_marker_${role.toLowerCase()}`;
  group.position.set(...config.position);

  const ringMaterial = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
  });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.018, 10, 64), ringMaterial);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = -0.3;
  group.add(ring);

  const bodyMaterial = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.42,
    metalness: 0.05,
    transparent: true,
    opacity: 0.96,
  });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.13, 0.34, 5, 14), bodyMaterial);
  body.position.y = 0.05;
  body.castShadow = true;
  group.add(body);

  const head = new THREE.Mesh(
    new THREE.SphereGeometry(0.15, 20, 12),
    new THREE.MeshStandardMaterial({ color: "#e6edf7", roughness: 0.35, metalness: 0.0 })
  );
  head.position.y = 0.38;
  head.castShadow = true;
  group.add(head);

  const visor = new THREE.Mesh(
    new THREE.BoxGeometry(0.22, 0.055, 0.03),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9 })
  );
  visor.position.set(0, 0.39, -0.13);
  group.add(visor);

  const hitMaterial = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.001, depthWrite: false });
  const hitTarget = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 1.2, 18), hitMaterial);
  hitTarget.position.y = 0.16;
  hitTarget.userData.role = role;
  group.add(hitTarget);

  const light = new THREE.PointLight(color, 0.8, 1.8);
  light.position.set(0, 0.45, 0);
  group.add(light);

  return { role, group, bodyMaterial, ringMaterial, hitTarget, light } satisfies MarkerHandle;
}

export function Office3DScene({ agents, selected, setSelected }: Office3DSceneProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const markersRef = useRef<Map<OfficeRole, MarkerHandle>>(new Map());
  const agentsRef = useRef(agents);
  const selectedRef = useRef(selected);
  const hoverRef = useRef<OfficeRole | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hoverRole, setHoverRole] = useState<OfficeRole | null>(null);

  useEffect(() => {
    agentsRef.current = agents;
    updateMarkers(markersRef.current, agentsRef.current, selectedRef.current, hoverRef.current);
  }, [agents]);

  useEffect(() => {
    selectedRef.current = selected;
    updateMarkers(markersRef.current, agentsRef.current, selectedRef.current, hoverRef.current);
  }, [selected]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let animationFrame = 0;
    let disposed = false;
    const markerHitTargets: THREE.Object3D[] = [];

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#fbf4e8");
    scene.fog = new THREE.Fog("#fbf4e8", 9, 18);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.domElement.className = "h-full w-full";
    renderer.domElement.setAttribute("aria-label", "Interactive 3D Dipeen virtual office");
    mount.appendChild(renderer.domElement);

    const camera = new THREE.PerspectiveCamera(42, mount.clientWidth / Math.max(1, mount.clientHeight), 0.1, 80);
    camera.position.set(5.6, 4.25, 5.4);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0.55, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = true;
    controls.minDistance = 4.8;
    controls.maxDistance = 9.5;
    controls.minPolarAngle = 0.62;
    controls.maxPolarAngle = 1.25;
    controls.update();

    scene.add(new THREE.HemisphereLight("#fff7ed", "#d7e4f5", 1.35));

    const keyLight = new THREE.DirectionalLight("#ffffff", 1.4);
    keyLight.position.set(3.5, 6, 4.5);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(1024, 1024);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight("#7aa7ff", 0.72);
    fillLight.position.set(-4, 3.5, -3);
    scene.add(fillLight);

    const loader = new GLTFLoader();
    loader.load(
      "/assets/dipeen-spatial/3d/dipeen-office-scene.glb",
      (gltf: GLTF) => {
        if (disposed) return;
        const office = gltf.scene;
        office.name = "dipeen_office_asset_pack";
        office.traverse((object: THREE.Object3D) => {
          if (object instanceof THREE.Mesh) {
            object.castShadow = true;
            object.receiveShadow = true;
            if (object.material instanceof THREE.MeshStandardMaterial) {
              object.material.envMapIntensity = 0.35;
              object.material.needsUpdate = true;
            }
          }
        });
        scene.add(office);
        setIsReady(true);
      },
      undefined,
      (error: unknown) => {
        if (!disposed) setLoadError(error instanceof Error ? error.message : "Failed to load office GLB");
      }
    );

    for (const role of ROLE_ORDER) {
      const marker = createMarker(role);
      markersRef.current.set(role, marker);
      markerHitTargets.push(marker.hitTarget);
      scene.add(marker.group);
    }
    updateMarkers(markersRef.current, agentsRef.current, selectedRef.current, hoverRef.current);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    function pickRole(event: PointerEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(markerHitTargets, false)[0];
      return isRole(String(hit?.object.userData.role ?? "")) ? hit.object.userData.role as OfficeRole : null;
    }

    function onPointerMove(event: PointerEvent) {
      const role = pickRole(event);
      hoverRef.current = role;
      setHoverRole(role);
      renderer.domElement.style.cursor = role ? "pointer" : "grab";
      updateMarkers(markersRef.current, agentsRef.current, selectedRef.current, role);
    }

    function onPointerLeave() {
      hoverRef.current = null;
      setHoverRole(null);
      renderer.domElement.style.cursor = "grab";
      updateMarkers(markersRef.current, agentsRef.current, selectedRef.current, null);
    }

    function onClick(event: PointerEvent) {
    const role = pickRole(event);
      if (role) setSelected(selectedAgentForRole(agentsRef.current, role)?.id ?? role);
    }

    function onContextLost(event: Event) {
      event.preventDefault();
      setLoadError("WebGL context lost. Reload the page to recover the 3D office.");
    }

    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerleave", onPointerLeave);
    renderer.domElement.addEventListener("click", onClick);
    renderer.domElement.addEventListener("webglcontextlost", onContextLost, false);

    const resizeObserver = new ResizeObserver(([entry]) => {
      const width = Math.max(1, Math.floor(entry.contentRect.width));
      const height = Math.max(1, Math.floor(entry.contentRect.height));
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    });
    resizeObserver.observe(mount);

    const startedAt = performance.now();
    function animate() {
      const elapsed = (performance.now() - startedAt) / 1000;
      markersRef.current.forEach((marker) => {
        const isSelected = selectedRoleFor(agentsRef.current, selectedRef.current) === marker.role;
        const bob = Math.sin(elapsed * 2.4 + marker.role.charCodeAt(0)) * 0.025;
        marker.group.position.y = ROLE_CONFIG[marker.role].position[1] + (isSelected ? 0.08 : 0) + bob;
        marker.group.rotation.y = Math.sin(elapsed * 0.65 + marker.role.charCodeAt(1)) * 0.08;
        marker.ringMaterial.opacity = isSelected ? 0.85 : hoverRef.current === marker.role ? 0.55 : 0.22;
        marker.light.intensity = isSelected ? 1.6 : 0.72;
      });
      controls.update();
      renderer.render(scene, camera);
      animationFrame = window.requestAnimationFrame(animate);
    }
    animate();

    return () => {
      disposed = true;
      window.cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("click", onClick);
      renderer.domElement.removeEventListener("webglcontextlost", onContextLost);
      controls.dispose();
      markersRef.current.forEach((marker) => disposeLabel(marker.label));
      markersRef.current.clear();
      scene.traverse((object: THREE.Object3D) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material: DisposableMaterial) => material.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [setSelected]);

  const activeAgent = agents.find((agent) => agent.id === selected);
  const selectedRole = selectedRoleFor(agents, selected) ?? "FE";

  return (
    <div className="relative h-full min-h-[520px] overflow-hidden bg-[#fbf4e8]">
      <div ref={mountRef} className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-4">
        <div className="rounded-lg border border-[#e4d7c2] bg-white/85 px-3 py-2 shadow-[0_10px_24px_rgba(68,56,38,0.10)] backdrop-blur-md">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-blue-700">3D Office</p>
          <p className="mt-1 text-sm text-slate-600">{agents.length} live agents · GLB environment</p>
        </div>
        <div className="rounded-lg border border-[#e4d7c2] bg-white/85 px-3 py-2 text-right shadow-[0_10px_24px_rgba(68,56,38,0.10)] backdrop-blur-md">
          <p className="text-xs text-slate-500">Selected</p>
          <p className="text-sm font-semibold text-slate-950">{activeAgent?.name ?? `${selectedRole} station`}</p>
        </div>
      </div>
      <div className="pointer-events-none absolute bottom-4 left-4 z-10 rounded-lg border border-[#e4d7c2] bg-white/85 px-3 py-2 text-xs text-slate-500 shadow-[0_10px_24px_rgba(68,56,38,0.10)] backdrop-blur-md">
        Drag to rotate · Scroll to zoom · Click a role marker
        {hoverRole && <span className="ml-2 text-blue-700">Hovering {hoverRole}</span>}
      </div>
      {!isReady && !loadError && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[#fbf4e8]">
          <div className="rounded-lg border border-[#e4d7c2] bg-white/90 px-4 py-3 text-sm text-slate-600 shadow-[0_10px_24px_rgba(68,56,38,0.10)]">Loading 3D office...</div>
        </div>
      )}
      {loadError && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[#fbf4e8]">
          <div className="max-w-md rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{loadError}</div>
        </div>
      )}
    </div>
  );
}

function updateMarkers(markers: Map<OfficeRole, MarkerHandle>, agents: OfficeAgent[], selected: string, hover: OfficeRole | null) {
  const agentByRole = new Map<OfficeRole, OfficeAgent>();
  for (const agent of agents) {
    if (!agentByRole.has(agent.role)) agentByRole.set(agent.role, agent);
  }

  markers.forEach((marker, role) => {
    const agent = agentByRole.get(role);
    const isSelected = selectedRoleFor(agents, selected) === role;
    const isHover = hover === role;
    marker.bodyMaterial.opacity = agent ? 0.96 : 0.38;
    marker.bodyMaterial.color.set(agent ? ROLE_CONFIG[role].color : "#64748b");
    marker.ringMaterial.color.set(isSelected || isHover ? ROLE_CONFIG[role].color : "#64748b");
    marker.group.scale.setScalar(isSelected ? 1.14 : isHover ? 1.06 : 1);
    marker.light.color.set(statusTone(agent?.status));

    if (marker.label) {
      marker.group.remove(marker.label);
      disposeLabel(marker.label);
      marker.label = undefined;
    }
    const labelTexture = makeLabelTexture(role, agent?.name ?? "Unassigned", agent?.status ?? "No live agent", ROLE_CONFIG[role].color);
    if (labelTexture) {
      const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: labelTexture, transparent: true, depthWrite: false }));
      label.position.set(0, 0.98, 0);
      label.scale.set(1.26, 0.46, 1);
      marker.label = label;
      marker.group.add(label);
    }
  });
}
