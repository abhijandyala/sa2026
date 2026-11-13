// Small inline icon set so nothing loads from a CDN (playbook p.30). Decorative by default.
import type { ReactNode } from "react";

type P = { size?: number; title?: string };

function Svg({ size = 16, title, children }: P & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export const IconCheck = (p: P) => (
  <Svg {...p}>
    <path d="M3 8.5l3.2 3L13 4.5" />
  </Svg>
);
export const IconAlert = (p: P) => (
  <Svg {...p}>
    <path d="M8 2.2l6.2 11H1.8z" />
    <path d="M8 6.5v3.2M8 11.6v.1" />
  </Svg>
);
export const IconDash = (p: P) => (
  <Svg {...p}>
    <path d="M4 8h8" />
  </Svg>
);
export const IconInfo = (p: P) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="6.2" />
    <path d="M8 7.2v4M8 4.9v.1" />
  </Svg>
);
export const IconRain = (p: P) => (
  <Svg {...p}>
    <path d="M4.5 9.5a3 3 0 0 1 .3-6 4 4 0 0 1 7.4 1.4A2.4 2.4 0 0 1 12 9.5z" />
    <path d="M5.5 11.5l-.8 2M8.5 11.5l-.8 2M11.5 11.5l-.8 2" />
  </Svg>
);
export const IconClose = (p: P) => (
  <Svg {...p}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Svg>
);
export const IconFlask = (p: P) => (
  <Svg {...p}>
    <path d="M6 2h4M6.8 2v4.2L3 13a1 1 0 0 0 .9 1.4h8.2A1 1 0 0 0 13 13L9.2 6.2V2" />
  </Svg>
);
