import { useEffect, useRef } from "react";
import * as THREE from "three";

export type GlobeState = "idle" | "thinking" | "tool_call" | "answer";

type NeuralGlobeProps = {
  state: GlobeState;
};

const PARTICLE_COUNT = 800;
const RADIUS = 2.2;
const NEIGHBORS = 3;

export function NeuralGlobe({ state }: NeuralGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.z = 7;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    const positions: THREE.Vector3[] = [];
    const golden = Math.PI * (3 - Math.sqrt(5));

    for (let index = 0; index < PARTICLE_COUNT; index += 1) {
      const y = 1 - (index / (PARTICLE_COUNT - 1)) * 2;
      const radiusAtY = Math.sqrt(1 - y * y);
      const theta = golden * index;
      positions.push(
        new THREE.Vector3(
          Math.cos(theta) * radiusAtY * RADIUS,
          y * RADIUS,
          Math.sin(theta) * radiusAtY * RADIUS,
        ),
      );
    }

    const pointGeometry = new THREE.BufferGeometry().setFromPoints(positions);
    const pointMaterial = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.035,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const points = new THREE.Points(pointGeometry, pointMaterial);
    scene.add(points);

    const linePositions: number[] = [];
    for (let index = 0; index < PARTICLE_COUNT; index += 1) {
      for (let step = 1; step <= NEIGHBORS; step += 1) {
        const target = (index + step * 17) % PARTICLE_COUNT;
        linePositions.push(
          positions[index].x,
          positions[index].y,
          positions[index].z,
          positions[target].x,
          positions[target].y,
          positions[target].z,
        );
      }
    }

    const lineGeometry = new THREE.BufferGeometry();
    lineGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(linePositions, 3),
    );
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.12,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
    scene.add(lines);

    const glow = new THREE.PointLight(0xffffff, 0.35, 20);
    glow.position.set(0, 0, 4);
    scene.add(glow);

    let frameId = 0;
    const start = performance.now();

    const resize = () => {
      const { clientWidth, clientHeight } = container;
      renderer.setSize(clientWidth, clientHeight);
      camera.aspect = clientWidth / Math.max(clientHeight, 1);
      camera.updateProjectionMatrix();
    };

    resize();
    window.addEventListener("resize", resize);

    const animate = (time: number) => {
      const elapsed = (time - start) * 0.001;
      const pulseSpeed =
        state === "thinking" ? 4.5 : state === "answer" ? 3.2 : state === "tool_call" ? 2.8 : 1.2;
      const pulse = (Math.sin(elapsed * pulseSpeed) + 1) * 0.5;
      const rotationSpeed =
        state === "thinking" ? 0.0035 : state === "tool_call" ? 0.005 : 0.0018;

      points.rotation.y += rotationSpeed;
      lines.rotation.y += rotationSpeed;

      const baseSize =
        state === "thinking" ? 0.04 : state === "tool_call" ? 0.045 : state === "answer" ? 0.042 : 0.035;
      pointMaterial.size = baseSize + pulse * 0.02;
      pointMaterial.opacity = 0.55 + pulse * (state === "thinking" ? 0.45 : 0.25);

      const lineOpacity =
        state === "thinking"
          ? 0.18 + pulse * 0.22
          : state === "tool_call"
            ? 0.14 + Math.abs(Math.sin(elapsed * 6)) * 0.2
            : state === "answer"
              ? 0.16 + pulse * 0.18
              : 0.1 + pulse * 0.08;
      lineMaterial.opacity = lineOpacity;

      glow.intensity = 0.25 + pulse * (state === "idle" ? 0.15 : 0.45);
      renderer.render(scene, camera);
      frameId = requestAnimationFrame(animate);
    };

    frameId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", resize);
      container.removeChild(renderer.domElement);
      pointGeometry.dispose();
      pointMaterial.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
      renderer.dispose();
    };
  }, [state]);

  return (
    <div
      ref={containerRef}
      className="h-full w-full min-h-[320px] shadow-[0_0_60px_rgba(255,255,255,0.05)]"
    />
  );
}