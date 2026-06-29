import { useEffect, useRef, useState } from "react";
import type { Scenario } from "../types/config";
import type { Frame, RunTrace, ThreatFrame } from "../types/result";

// The engine models position as a scalar distance-to-asset (the sim is 1D; see ARCHITECTURE_AND_PLAN
// §11 "2D plane" is a presentation choice). For replay we give each threat a stable bearing derived
// from its uid and render a radar scope: asset at center, threats closing inward. This is a dumb
// renderer of the recorded trace - it contains no simulation logic.

const CATEGORY_COLORS: Record<string, string> = {
  cheap_mass: "#5b9cff",
  decoy: "#8a93a6",
  autonomous: "#ff7b72",
  terrain_hugger: "#b48cff",
};

const SPEEDS = [3, 6, 12];

function bearing(uid: number): number {
  // Deterministic pseudo-random angle so archetypes interleave around the scope.
  const h = ((uid * 9301 + 49297) % 233280) / 233280;
  return h * Math.PI * 2;
}

function indexByUid(frame: Frame): Map<number, ThreatFrame> {
  const m = new Map<number, ThreatFrame>();
  for (const t of frame.threats) m.set(t.uid, t);
  return m;
}

export function EngagementCanvas({
  trace,
  scenario,
  color,
}: {
  trace: RunTrace;
  scenario: Scenario;
  color: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(6);
  const [frameIdx, setFrameIdx] = useState(0);

  const playingRef = useRef(playing);
  const speedRef = useRef(speed);
  const timeRef = useRef(0);
  playingRef.current = playing;
  speedRef.current = speed;

  const frames = trace.frames;
  const lastTick = Math.max(0, frames.length - 1);
  const maxPos = scenario.approach_distance;

  // Reset playback when a new trace arrives.
  useEffect(() => {
    timeRef.current = 0;
    setFrameIdx(0);
    setPlaying(true);
  }, [trace]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let last = performance.now();

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = (time: number) => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const cx = w / 2;
      const cy = h / 2;
      const maxR = Math.min(w, h) * 0.46;
      const rOf = (pos: number) => (Math.max(0, Math.min(maxPos, pos)) / maxPos) * maxR;

      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#070b13";
      ctx.fillRect(0, 0, w, h);

      // Range rings for each effector (faint), plus the spawn ring.
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(91,156,255,0.10)";
      ctx.beginPath();
      ctx.arc(cx, cy, maxR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.font = "10px system-ui, sans-serif";
      for (const eff of scenario.defense.effectors) {
        const r = rOf(eff.range);
        ctx.strokeStyle = "rgba(124,138,165,0.18)";
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "rgba(124,138,165,0.55)";
        ctx.fillText(eff.id, cx + 4, cy - r - 3);
      }

      const i0 = Math.floor(time);
      const i1 = Math.min(i0 + 1, lastTick);
      const a = time - i0;
      const f0 = frames[i0];
      const f1 = frames[i1];
      if (!f1) return;
      const m0 = indexByUid(f0);

      // Shots fired during this tick (fade across the tick).
      const shotAlpha = 1 - a;
      for (const shot of f1.shots) {
        const tgt = (indexByUid(f1).get(shot.target_uid) ?? m0.get(shot.target_uid));
        if (!tgt) continue;
        const ang = bearing(shot.target_uid);
        const r = rOf(tgt.position);
        const tx = cx + Math.cos(ang) * r;
        const ty = cy + Math.sin(ang) * r;
        ctx.strokeStyle = shot.hit
          ? `rgba(63,185,80,${0.55 * shotAlpha})`
          : `rgba(232,184,75,${0.30 * shotAlpha})`;
        ctx.lineWidth = shot.hit ? 1.6 : 1;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(tx, ty);
        ctx.stroke();
      }

      // Kills this tick: expanding flash at the threat's location.
      for (const uid of f1.kills) {
        const t = m0.get(uid) ?? indexByUid(f1).get(uid);
        if (!t) continue;
        const ang = bearing(uid);
        const r = rOf(t.position);
        const px = cx + Math.cos(ang) * r;
        const py = cy + Math.sin(ang) * r;
        ctx.strokeStyle = `rgba(63,185,80,${0.9 * (1 - a)})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(px, py, 4 + a * 14, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Live threats: interpolate position between frames.
      for (const t of f1.threats) {
        if (!t.alive) continue;
        const prev = m0.get(t.uid);
        const pos = prev ? prev.position + (t.position - prev.position) * a : t.position;
        const ang = bearing(t.uid);
        const r = rOf(pos);
        const px = cx + Math.cos(ang) * r;
        const py = cy + Math.sin(ang) * r;
        const col = CATEGORY_COLORS[t.category] ?? "#cccccc";
        if (t.tracked) {
          ctx.strokeStyle = col;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(px, py, 6, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.fillStyle = col;
        ctx.beginPath();
        ctx.arc(px, py, 3.2, 0, Math.PI * 2);
        ctx.fill();
      }

      // Asset at center.
      ctx.fillStyle = "#3fb950";
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(Math.PI / 4);
      ctx.fillRect(-5, -5, 10, 10);
      ctx.restore();
      if (f1.leaks.length > 0) {
        ctx.strokeStyle = `rgba(255,123,114,${0.8 * (1 - a)})`;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(cx, cy, 10 + (1 - (1 - a)) * 6, 0, Math.PI * 2);
        ctx.stroke();
      }
    };

    const loop = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      if (playingRef.current) {
        timeRef.current += dt * speedRef.current;
        if (timeRef.current >= lastTick) {
          timeRef.current = lastTick;
          setPlaying(false);
        }
      }
      draw(timeRef.current);
      const idx = Math.round(timeRef.current);
      setFrameIdx((cur) => (cur !== idx ? idx : cur));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trace, scenario]);

  const atEnd = frameIdx >= lastTick;
  const cur = frames[Math.min(frameIdx, lastTick)];
  const aliveNow = cur ? cur.threats.filter((t) => t.alive).length : 0;

  return (
    <div className="replay">
      <canvas ref={canvasRef} className="replay-canvas" />
      <div className="replay-controls">
        <button
          className="replay-btn"
          style={{ background: color }}
          onClick={() => {
            if (atEnd) {
              timeRef.current = 0;
              setFrameIdx(0);
            }
            setPlaying((p) => !p);
          }}
        >
          {playing ? "Pause" : atEnd ? "Replay" : "Play"}
        </button>
        <input
          className="replay-scrub"
          type="range"
          min={0}
          max={lastTick}
          value={Math.min(frameIdx, lastTick)}
          onChange={(e) => {
            const v = Number(e.target.value);
            timeRef.current = v;
            setFrameIdx(v);
            setPlaying(false);
          }}
        />
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="replay-speed">
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
      </div>
      <div className="replay-hud">
        <span>
          tick <strong>{Math.min(frameIdx, lastTick)}</strong>/{lastTick}
        </span>
        <span>
          alive <strong>{aliveNow}</strong>
        </span>
        <span className="legend">
          {Object.entries(CATEGORY_COLORS)
            .filter(([cat]) => scenario.swarm.some((s) => s.spec.category === cat))
            .map(([cat, col]) => (
              <span key={cat} className="legend-item">
                <span className="legend-dot" style={{ background: col }} />
                {cat}
              </span>
            ))}
        </span>
      </div>
    </div>
  );
}
