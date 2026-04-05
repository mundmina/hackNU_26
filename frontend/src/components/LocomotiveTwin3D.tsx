import { Canvas } from "@react-three/fiber";
import { Float, OrbitControls } from "@react-three/drei";

import type { HealthSnapshot } from "../types";

interface LocomotiveTwin3DProps {
  health: HealthSnapshot | null;
}

function subsystemColor(health: HealthSnapshot | null, key: string, fallback: string) {
  const factor = health?.factors.find((item) => item.key === key);
  if (!factor) return fallback;
  if (factor.penalty > 10) return "#d7263d";
  if (factor.penalty > 6) return "#ff8a4c";
  return "#f2b94b";
}

export function LocomotiveTwin3D({ health }: LocomotiveTwin3DProps) {
  return (
    <section className="panel twin-panel">
      <div className="panel-header">
        <p>3D-модель локомотива</p>
        <span className="muted">Наложение по подсистемам</span>
      </div>
      <div className="twin-shell">
        <Canvas camera={{ position: [4, 2.5, 6], fov: 42 }}>
          <ambientLight intensity={1.2} />
          <directionalLight position={[6, 8, 5]} intensity={2.2} />
          <Float speed={1.4} rotationIntensity={0.2} floatIntensity={0.18}>
            <group rotation={[0.12, -0.7, 0]}>
              <mesh position={[0, 0.25, 0]}>
                <boxGeometry args={[3.6, 0.7, 1.2]} />
                <meshStandardMaterial color="#2f3441" metalness={0.3} roughness={0.5} />
              </mesh>
              <mesh position={[0.4, 0.9, 0]}>
                <boxGeometry args={[1.6, 0.6, 1]} />
                <meshStandardMaterial color={subsystemColor(health, "oil_temp", "#58c5ff")} />
              </mesh>
              <mesh position={[-1.2, 0.78, 0]}>
                <boxGeometry args={[1.1, 0.4, 0.9]} />
                <meshStandardMaterial color={subsystemColor(health, "motor_temp", "#3ccf91")} />
              </mesh>
              <mesh position={[1.7, 0.45, 0]}>
                <boxGeometry args={[0.45, 0.45, 0.85]} />
                <meshStandardMaterial color={subsystemColor(health, "reservoir_pressure", "#f2b94b")} />
              </mesh>
              {[-1.2, -0.2, 0.8, 1.8].map((x) => (
                <mesh key={x} position={[x, -0.3, 0.55]} rotation={[Math.PI / 2, 0, 0]}>
                  <cylinderGeometry args={[0.32, 0.32, 0.28, 24]} />
                  <meshStandardMaterial color={subsystemColor(health, "wheel_slip", "#d8dee9")} />
                </mesh>
              ))}
              {[-1.2, -0.2, 0.8, 1.8].map((x) => (
                <mesh key={`${x}-right`} position={[x, -0.3, -0.55]} rotation={[Math.PI / 2, 0, 0]}>
                  <cylinderGeometry args={[0.32, 0.32, 0.28, 24]} />
                  <meshStandardMaterial color={subsystemColor(health, "wheel_slip", "#d8dee9")} />
                </mesh>
              ))}
            </group>
          </Float>
          <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 1.9} minDistance={4} maxDistance={8} />
        </Canvas>
      </div>
    </section>
  );
}
