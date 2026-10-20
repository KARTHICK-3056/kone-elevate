import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js';

/**
 * 3D traction lift for the simulation page - visual only.
 *
 * Everything shown is driven by the simulation results passed in `visual`:
 *  - car load       -> passengers in the car
 *  - life band      -> colour of motor, sheave, governor, ropes (green / amber / red)
 *  - motor heat     -> red glow on the motor
 *  - vibration      -> shake of the machine and car
 * The car's up/down travel is animated in real time and is not simulation time.
 */

export const BAND_HEX = { green: 0x0f9d58, amber: 0xf4a300, red: 0xd93025 };
const NEUTRAL = 0x8593aa;
const RATED_SPEED = 1.6; // m/s, matches the simulation reference
const ACCELERATION = 0.8; // m/s^2
const DWELL_SECONDS = 1.6;

function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(window.WebGLRenderingContext && (canvas.getContext('webgl2') || canvas.getContext('webgl')));
  } catch {
    return false;
  }
}

function label(text) {
  const div = document.createElement('div');
  div.className =
    'pointer-events-none rounded bg-navy-900/80 px-1.5 py-0.5 text-[10px] font-semibold text-white shadow';
  div.textContent = text;
  return new CSS2DObject(div);
}

export default function ElevatorScene({ visual, height = 520 }) {
  const mountRef = useRef(null);
  const visualRef = useRef(visual);
  const sceneRef = useRef(null);
  const [unsupported, setUnsupported] = useState(false);

  visualRef.current = visual;

  // ----------------------------------------------------------- build once
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;
    if (!supportsWebGL()) {
      setUnsupported(true);
      return undefined;
    }

    const floors = visual?.floors || 8;
    const floorHeight = visual?.floorHeight || 3.5;
    const travel = (floors - 1) * floorHeight;
    const shaftHeight = travel + 3.2;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf6f7f9);

    // Frame the whole lift, machine room included: distance from the vertical
    // field of view, viewed from the front-right and slightly above.
    const fov = 38;
    const camera = new THREE.PerspectiveCamera(fov, mount.clientWidth / height, 0.1, 400);
    const frameHeight = shaftHeight + 4;
    const distance = (frameHeight / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2))) * 1.1;
    const lookY = frameHeight * 0.48;
    const view = new THREE.Vector3(0.55, 0.18, 0.82).normalize().multiplyScalar(distance);
    camera.position.set(view.x, lookY + view.y, view.z);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, height);
    mount.appendChild(renderer.domElement);

    const labels = new CSS2DRenderer();
    labels.setSize(mount.clientWidth, height);
    labels.domElement.style.position = 'absolute';
    labels.domElement.style.top = '0';
    labels.domElement.style.pointerEvents = 'none';
    mount.appendChild(labels.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, lookY, 0);
    controls.enableDamping = true;
    controls.maxDistance = 90;
    controls.minDistance = 8;

    scene.add(new THREE.HemisphereLight(0xffffff, 0xb0bac9, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(10, 40, 20);
    scene.add(sun);

    // -- shaft ---------------------------------------------------------------
    const shaft = new THREE.Mesh(
      new THREE.BoxGeometry(4.4, shaftHeight, 2.6),
      new THREE.MeshStandardMaterial({ color: 0xd5dae3, transparent: true, opacity: 0.08, depthWrite: false }),
    );
    shaft.position.y = shaftHeight / 2;
    scene.add(shaft);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(shaft.geometry),
      new THREE.LineBasicMaterial({ color: 0x8593aa }),
    );
    edges.position.copy(shaft.position);
    scene.add(edges);

    const slabMaterial = new THREE.MeshStandardMaterial({ color: 0xb0bac9, transparent: true, opacity: 0.35 });
    for (let i = 0; i < floors; i += 1) {
      const slab = new THREE.Mesh(new THREE.BoxGeometry(5.6, 0.06, 3.4), slabMaterial);
      slab.position.set(-0.6, i * floorHeight, 0);
      scene.add(slab);
      const tag = label(i === 0 ? 'G' : String(i));
      tag.position.set(-3.6, i * floorHeight + 0.4, 0);
      scene.add(tag);
    }

    const railMaterial = new THREE.MeshStandardMaterial({ color: 0x66758f, metalness: 0.6, roughness: 0.4 });
    [-1.9, 0.7].forEach((x) => {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(0.08, shaftHeight, 0.12), railMaterial);
      rail.position.set(x, shaftHeight / 2, 0);
      scene.add(rail);
    });

    // -- car and passengers --------------------------------------------------
    const carGroup = new THREE.Group();
    const car = new THREE.Mesh(
      new THREE.BoxGeometry(2.2, 2.4, 1.8),
      new THREE.MeshStandardMaterial({ color: 0x4869a3, transparent: true, opacity: 0.35, metalness: 0.3 }),
    );
    car.position.y = 1.2;
    carGroup.add(car);
    const carOutline = new THREE.LineSegments(
      new THREE.EdgesGeometry(car.geometry),
      new THREE.LineBasicMaterial({ color: 0x1d2d4e }),
    );
    carOutline.position.copy(car.position);
    carGroup.add(carOutline);
    const carTag = label('Car');
    carTag.position.set(0, 2.9, 0);
    carGroup.add(carTag);

    const personMaterial = new THREE.MeshStandardMaterial({ color: 0x0f1c33 });
    const people = [];
    for (let i = 0; i < 15; i += 1) {
      const person = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.16, 1.1, 10), personMaterial);
      body.position.y = 0.55;
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.13, 12, 10), personMaterial);
      head.position.y = 1.25;
      person.add(body, head);
      person.position.set(-0.8 + (i % 5) * 0.4, 0.03, -0.55 + Math.floor(i / 5) * 0.55);
      person.visible = false;
      carGroup.add(person);
      people.push(person);
    }
    carGroup.position.set(-0.6, 0, 0);
    scene.add(carGroup);

    // -- counterweight -------------------------------------------------------
    const counterweight = new THREE.Mesh(
      new THREE.BoxGeometry(0.9, 2.0, 0.5),
      new THREE.MeshStandardMaterial({ color: 0x434d60, metalness: 0.5 }),
    );
    counterweight.position.set(1.4, travel + 1, 0);
    scene.add(counterweight);
    const cwTag = label('Counterweight');
    cwTag.position.set(0, 1.3, 0);
    counterweight.add(cwTag);

    // -- machine: sheave, motor ----------------------------------------------
    const machine = new THREE.Group();
    const machineY = shaftHeight + 0.6;
    machine.position.set(0, machineY, 0);
    scene.add(machine);

    const bed = new THREE.Mesh(
      new THREE.BoxGeometry(5, 0.2, 3),
      new THREE.MeshStandardMaterial({ color: 0x9bb2d5 }),
    );
    bed.position.y = -0.7;
    machine.add(bed);

    const sheaveMaterial = new THREE.MeshStandardMaterial({ color: NEUTRAL, metalness: 0.7, roughness: 0.35 });
    const sheave = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.0, 0.45, 40), sheaveMaterial);
    sheave.rotation.x = Math.PI / 2;
    sheave.position.set(0.4, 0.4, 0);
    machine.add(sheave);
    const spokes = new THREE.Mesh(
      new THREE.BoxGeometry(1.9, 0.12, 0.5),
      new THREE.MeshStandardMaterial({ color: 0x333a46 }),
    );
    sheave.add(spokes);
    const sheaveTag = label('Sheave');
    sheaveTag.position.set(1.3, 1.5, 0.5);
    machine.add(sheaveTag);

    const motorMaterial = new THREE.MeshStandardMaterial({ color: NEUTRAL, metalness: 0.4, emissive: 0x000000 });
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.75, 1.3, 32), motorMaterial);
    motor.rotation.x = Math.PI / 2;
    motor.position.set(0.4, 0.4, -1.0);
    machine.add(motor);
    const motorTag = label('Motor');
    motorTag.position.set(-0.6, 1.3, -1.7);
    machine.add(motorTag);

    // -- overspeed governor: machine-room sheave, rope loop to a pit tension
    // pulley, clamped to the car's safety-gear linkage ---------------------
    const GOVERNOR_X = -2.0;
    const GOVERNOR_Z = 0.8;
    const GOVERNOR_R = 0.32;
    const governorMaterial = new THREE.MeshStandardMaterial({ color: NEUTRAL, metalness: 0.6, roughness: 0.4 });
    const governor = new THREE.Group(); // spins about x
    const governorSheave = new THREE.Mesh(
      new THREE.CylinderGeometry(GOVERNOR_R, GOVERNOR_R, 0.14, 28),
      governorMaterial,
    );
    governorSheave.rotation.z = Math.PI / 2;
    governor.add(governorSheave);
    const flyweightMaterial = new THREE.MeshStandardMaterial({ color: 0x333a46 });
    [-1, 1].forEach((side) => {
      const flyweight = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.12, 0.2), flyweightMaterial);
      flyweight.position.set(0.1, side * 0.14, 0);
      governor.add(flyweight);
    });
    governor.position.set(GOVERNOR_X, -0.25, GOVERNOR_Z);
    machine.add(governor);
    const governorTag = label('Governor');
    governorTag.position.set(GOVERNOR_X, 0.45, GOVERNOR_Z + 0.3);
    machine.add(governorTag);

    const tensionPulley = new THREE.Mesh(
      new THREE.CylinderGeometry(0.22, 0.22, 0.1, 20),
      new THREE.MeshStandardMaterial({ color: 0x66758f, metalness: 0.5 }),
    );
    tensionPulley.rotation.z = Math.PI / 2;
    tensionPulley.position.set(GOVERNOR_X, 0.35, GOVERNOR_Z);
    scene.add(tensionPulley);
    const governorRopeMaterial = new THREE.MeshStandardMaterial({ color: 0x5b6577, metalness: 0.7 });
    const governorRopeTop = machineY - 0.25;
    [-GOVERNOR_R, GOVERNOR_R].forEach((dz) => {
      const length = governorRopeTop - 0.35;
      const rope = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, length, 5), governorRopeMaterial);
      rope.position.set(GOVERNOR_X, 0.35 + length / 2, GOVERNOR_Z + dz);
      scene.add(rope);
    });
    // Safety-gear linkage from the car to the governor rope.
    // Car-local x: the car wall is at -1.1, the rope at GOVERNOR_X - carGroup.x.
    const ropeLocalX = GOVERNOR_X + 0.6;
    const linkage = new THREE.Mesh(
      new THREE.BoxGeometry(Math.abs(ropeLocalX + 1.1), 0.08, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x333a46 }),
    );
    linkage.position.set((ropeLocalX - 1.1) / 2, 2.2, GOVERNOR_Z - GOVERNOR_R);
    carGroup.add(linkage);

    // -- ropes -----------------------------------------------------------------
    const ropeMaterial = new THREE.MeshStandardMaterial({ color: NEUTRAL, metalness: 0.8, roughness: 0.3 });
    const makeRopes = (x) =>
      [-0.12, 0, 0.12].map((z) => {
        const rope = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1, 6), ropeMaterial);
        rope.position.set(x, 0, z);
        scene.add(rope);
        return rope;
      });
    const carRopes = makeRopes(-0.6);
    const cwRopes = makeRopes(1.4);
    const ropeTag = label('Steel ropes');
    scene.add(ropeTag);

    const fitRope = (rope, fromY, toY) => {
      const length = Math.max(0.01, toY - fromY);
      rope.scale.y = length;
      rope.position.y = fromY + length / 2;
    };

    // -- motion ------------------------------------------------------------------
    const motion = { y: 0, target: 0, velocity: 0, dwell: 1 };
    const pickTarget = () => {
      let floor = Math.floor(Math.random() * floors);
      if (floor * floorHeight === motion.target) floor = (floor + 1) % floors;
      motion.target = floor * floorHeight;
    };

    // Camera presets, eased towards each frame.
    const views = {
      lift: { position: camera.position.clone(), target: new THREE.Vector3(0, lookY, 0) },
      machine: {
        position: new THREE.Vector3(6.5, machineY + 3.2, 7.5),
        target: new THREE.Vector3(0.4, machineY + 0.2, -0.6),
      },
    };
    let goal = null;
    sceneRef.current = {
      setView: (name) => {
        goal = views[name] || null;
      },
    };

    const clock = new THREE.Clock();
    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      const v = visualRef.current || {};

      // Travel with a trapezoidal speed profile, dwell at each floor.
      if (motion.dwell > 0) {
        motion.dwell -= dt;
        if (motion.dwell <= 0) pickTarget();
      } else {
        const distance = motion.target - motion.y;
        const direction = Math.sign(distance);
        const stopping = (motion.velocity * motion.velocity) / (2 * ACCELERATION);
        if (Math.abs(distance) <= stopping + 0.02) {
          motion.velocity = Math.max(0, motion.velocity - ACCELERATION * dt);
        } else {
          motion.velocity = Math.min(RATED_SPEED, motion.velocity + ACCELERATION * dt);
        }
        motion.y += direction * motion.velocity * dt * 2.2; // x2.2: visual time-lapse
        if (Math.abs(motion.target - motion.y) < 0.03 || Math.sign(motion.target - motion.y) !== direction) {
          motion.y = motion.target;
          motion.velocity = 0;
          motion.dwell = DWELL_SECONDS;
        }
      }

      // Vibration shake grows once readings pass 60% of the limit.
      const shake = Math.max(0, (v.vibrationRatio || 0) - 0.6) * 0.12;
      const jitter = () => (Math.random() - 0.5) * shake;

      carGroup.position.y = motion.y + (motion.velocity > 0 ? jitter() : 0);
      carGroup.position.x = -0.6 + (motion.velocity > 0 ? jitter() : 0);
      counterweight.position.y = travel - motion.y + 1;
      machine.position.x = jitter();
      sheave.rotation.y += (motion.velocity * dt * 2.2) * (motion.target > motion.y ? -1 : 1);
      // The governor rope runs with the car, so its sheave turns with travel.
      governor.rotation.x += ((motion.velocity * dt * 2.2) / GOVERNOR_R) * (motion.target > motion.y ? 1 : -1);

      const sheaveBottom = machineY + 0.4;
      carRopes.forEach((rope) => fitRope(rope, carGroup.position.y + 2.4, sheaveBottom));
      cwRopes.forEach((rope) => fitRope(rope, counterweight.position.y + 1.0, sheaveBottom));
      ropeTag.position.set(-0.6, (carGroup.position.y + 2.4 + sheaveBottom) / 2, 0.4);

      // Colours from the simulation results.
      const bands = v.bands || {};
      motorMaterial.color.setHex(BAND_HEX[bands.Motor] ?? NEUTRAL);
      sheaveMaterial.color.setHex(BAND_HEX[bands.Sheave] ?? NEUTRAL);
      governorMaterial.color.setHex(BAND_HEX[bands.Governor] ?? NEUTRAL);
      ropeMaterial.color.setHex(BAND_HEX[bands['Steel Rope']] ?? NEUTRAL);
      const heat = Math.min(1, Math.max(0, v.motorHeat || 0));
      motorMaterial.emissive.setRGB(heat * 0.7, heat * 0.08, 0);

      const passengers = Math.round((v.loadKg || 0) / 75);
      people.forEach((person, index) => {
        person.visible = index < passengers;
      });

      if (goal) {
        camera.position.lerp(goal.position, 0.08);
        controls.target.lerp(goal.target, 0.08);
        if (camera.position.distanceTo(goal.position) < 0.05) goal = null;
      }
      controls.update();
      renderer.render(scene, camera);
      labels.render(scene, camera);
    };
    animate();

    const resize = () => {
      const width = mount.clientWidth;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      labels.setSize(width, height);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((object) => {
        object.geometry?.dispose?.();
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((material) => material?.dispose?.());
      });
      renderer.dispose();
      mount.innerHTML = '';
    };
    // Geometry depends only on the lift layout; live values flow through visualRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visual?.floors, visual?.floorHeight, height]);

  if (unsupported) {
    return (
      <div
        className="flex items-center justify-center rounded-lg bg-steel-100 text-sm text-steel-500"
        style={{ height }}
      >
        3D view needs WebGL, which this browser does not provide. The simulation still runs.
      </div>
    );
  }

  return (
    <div className="relative">
      <div ref={mountRef} className="relative w-full overflow-hidden rounded-lg" style={{ height }} />
      <div className="absolute right-2 top-2 flex gap-1">
        {[
          ['lift', 'Whole lift'],
          ['machine', 'Machine room'],
        ].map(([name, text]) => (
          <button
            key={name}
            type="button"
            className="rounded-md bg-white/90 px-2 py-1 text-xs font-semibold text-navy-800 shadow hover:bg-white"
            onClick={() => sceneRef.current?.setView(name)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
