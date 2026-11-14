import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/*
  A screen recording that is not a video: the real app screen, drawn small, with a
  scripted pointer that moves, hovers and clicks on it (Loom-style: a window frame, a
  pointer, a caption, a progress bar and a pause button). Because the screen is the app's
  own components with the app's own data, the recording can never drift from the product.

  A script is a list of steps on one timeline. The player runs it in a loop while the
  demo is on screen, pauses when it scrolls away or the tab is hidden, and holds still
  for people who ask for reduced motion (they get a play button instead).
*/

export interface DemoStep {
  /** Milliseconds from the start of the loop. */
  at: number;
  /** Where the pointer goes: a CSS selector inside the screen, optionally a spot within that element. */
  to?: string | { sel: string; fx?: number; fy?: number };
  /** After arriving: press, or send a hover so the screen's own hover labels appear. */
  act?: "click" | "hover";
  /** Keep the pointer glued to this element until the next step that moves it (for drags). */
  follow?: string;
  /** Change the scene's own state. */
  run?: () => void;
  /** One line shown under the recording. */
  say?: string;
}

const MOVE_MS = 650;

export function DemoPlayer({
  steps,
  duration,
  onLoop,
  width,
  height,
  title,
  chrome = true,
  play = "visible",
  children,
}: {
  steps: DemoStep[];
  /** Length of one loop in milliseconds. */
  duration: number;
  /** Put the scene back to its first frame. */
  onLoop: () => void;
  /** The size the screen is drawn at before it is scaled to fit. */
  width: number;
  height: number;
  /** Shown in the window bar, like a browser tab. */
  title: string;
  /** The window bar and the control bar. Small inline demos turn them off. */
  chrome?: boolean;
  /** Run while on screen, or only while pointed at. */
  play?: "visible" | "hover";
  children: ReactNode;
}) {
  const shell = useRef<HTMLDivElement>(null);
  const screen = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);
  const [pos, setPos] = useState<{ x: number; y: number; glide: boolean }>({ x: 0.72, y: 0.78, glide: false });
  const [pressed, setPressed] = useState(0);
  const [say, setSay] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [inView, setInView] = useState(false);
  const [hovered, setHovered] = useState(false);
  const still = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [paused, setPaused] = useState(still);
  const stepsRef = useRef(steps);
  stepsRef.current = steps;
  const loopRef = useRef(onLoop);
  loopRef.current = onLoop;

  // Fit the fixed-size screen to the space it is given.
  useEffect(() => {
    const el = screen.current;
    if (!el) return;
    const fit = () => setScale(el.clientWidth / width);
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [width]);

  useEffect(() => {
    const el = shell.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setInView(Boolean(e?.isIntersecting)), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // The scene is decoration with a text caption: keep it out of the tab order and the reading order.
  useEffect(() => {
    stage.current?.setAttribute("inert", "");
  }, []);

  const running = !paused && (play === "hover" ? hovered : inView);

  useEffect(() => {
    if (!running) return;
    let t = 0;
    let next = 0;
    let follow: string | null = null;
    let last = performance.now();
    let raf = 0;
    const timers: number[] = [];

    const point = (target: DemoStep["to"]) => {
      const box = screen.current?.getBoundingClientRect();
      if (!box || !target || !stage.current) return null;
      const sel = typeof target === "string" ? target : target.sel;
      const el = stage.current.querySelector<HTMLElement>(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const fx = typeof target === "string" ? 0.5 : (target.fx ?? 0.5);
      const fy = typeof target === "string" ? 0.5 : (target.fy ?? 0.5);
      const cx = r.left + r.width * fx;
      const cy = r.top + r.height * fy;
      return { el, cx, cy, x: (cx - box.left) / box.width, y: (cy - box.top) / box.height };
    };

    const act = (step: DemoStep) => {
      const p = point(step.to);
      if (!p) return;
      if (step.act === "hover") {
        p.el.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: p.cx, clientY: p.cy }));
      } else if (step.act === "click") {
        setPressed((n) => n + 1);
        p.el.click();
      }
    };

    const restart = () => {
      t = 0;
      next = 0;
      follow = null;
      loopRef.current();
      setSay(null);
      setPos({ x: 0.72, y: 0.78, glide: false });
    };

    const tick = (now: number) => {
      t += Math.min(80, now - last);
      last = now;
      const list = stepsRef.current;
      while (next < list.length && list[next]!.at <= t) {
        const step = list[next++]!;
        if (step.say !== undefined) setSay(step.say);
        step.run?.();
        if (step.to) {
          // Glide there first; start following (for a drag) once the pointer has arrived.
          follow = null;
          const p = point(step.to);
          if (p) setPos({ x: p.x, y: p.y, glide: true });
          if (step.act) timers.push(window.setTimeout(() => act(step), MOVE_MS));
          if (step.follow) {
            const sel = step.follow;
            timers.push(window.setTimeout(() => (follow = sel), MOVE_MS));
          }
        } else if (step.follow !== undefined) {
          follow = step.follow || null;
        }
      }
      if (follow) {
        const p = point(follow);
        if (p) setPos({ x: p.x, y: p.y, glide: false });
      }
      setProgress(Math.min(1, t / duration));
      if (t >= duration) restart();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      timers.forEach((id) => window.clearTimeout(id));
    };
  }, [running, duration]);

  const seconds = (ms: number) => `0:${String(Math.floor(ms / 1000)).padStart(2, "0")}`;

  return (
    <div
      className={`demo${chrome ? " has-chrome" : ""}${running ? " is-running" : ""}`}
      ref={shell}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      {chrome ? (
        <div className="demo-bar" aria-hidden="true">
          <span className="demo-dots">
            <i />
            <i />
            <i />
          </span>
          <span className="demo-url">{title}</span>
          <span className="demo-rec">
            <i /> Recording of the real app
          </span>
        </div>
      ) : null}
      <div className="demo-screen" ref={screen} style={{ aspectRatio: `${width} / ${height}` }}>
        <div className="demo-stage" ref={stage} aria-hidden="true" style={{ width, height, transform: `scale(${scale})` } as CSSProperties}>
          {children}
        </div>
        <span
          className={`demo-cursor${pos.glide ? " is-gliding" : ""}`}
          style={{ left: `${pos.x * 100}%`, top: `${pos.y * 100}%`, "--move": `${MOVE_MS}ms` } as CSSProperties}
          aria-hidden="true"
        >
          <svg width="22" height="22" viewBox="0 0 22 22">
            <path d="M4 2.5l13 7.4-6 1.5-2.6 5.8z" fill="#15191C" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
          </svg>
          <span className="demo-press" key={pressed} data-on={pressed > 0 ? "" : undefined} />
        </span>
        {say ? (
          <p className="demo-say" key={say}>
            {say}
          </p>
        ) : null}
      </div>
      {chrome ? (
        <div className="demo-controls">
          <button type="button" className="demo-toggle" onClick={() => setPaused((p) => !p)} aria-label={paused ? "Play the recording" : "Pause the recording"}>
            {paused ? (
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                <path d="M3 1.5v9l7.5-4.500z" fill="currentColor" />
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                <path d="M2.500 1.500h2.500v9H2.500zM7 1.500h2.500v9H7z" fill="currentColor" />
              </svg>
            )}
          </button>
          <span className="demo-track" aria-hidden="true">
            <span style={{ transform: `scaleX(${progress})` }} />
          </span>
          <span className="demo-time tabular" aria-hidden="true">
            {seconds(progress * duration)} / {seconds(duration)}
          </span>
        </div>
      ) : null}
    </div>
  );
}
