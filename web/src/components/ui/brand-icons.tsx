import type { ReactNode, SVGProps } from "react";

export type BrandIconName =
  | "agent"
  | "board"
  | "branch"
  | "chat"
  | "check"
  | "code"
  | "command"
  | "database"
  | "graph"
  | "inspect"
  | "key"
  | "layers"
  | "meeting"
  | "play"
  | "review"
  | "settings"
  | "shield"
  | "spark"
  | "token"
  | "workflow";

type BrandIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: BrandIconName;
  size?: number;
  title?: string;
};

const paths: Record<BrandIconName, ReactNode> = {
  agent: (
    <>
      <rect x="6" y="9" width="12" height="8" rx="4" />
      <path d="M9.5 13h.01M14.5 13h.01M12 9V6" />
      <path d="M8 17.5v1M16 17.5v1" />
      <circle cx="12" cy="5" r="1.2" />
    </>
  ),
  board: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="3" />
      <path d="M8 9h3M8 13h8M8 16h5" />
      <path d="M15.5 9h.01" />
    </>
  ),
  branch: (
    <>
      <circle cx="7" cy="6" r="2" />
      <circle cx="17" cy="6" r="2" />
      <circle cx="12" cy="18" r="2" />
      <path d="M7 8v2.5A3.5 3.5 0 0010.5 14H12v2" />
      <path d="M17 8v2.5A3.5 3.5 0 0113.5 14H12" />
    </>
  ),
  chat: (
    <>
      <path d="M6.5 16.5 4 20v-5.2A7.2 7.2 0 013 11.2C3 7.2 7 4 12 4s9 3.2 9 7.2-4 7.2-9 7.2a10.5 10.5 0 01-5.5-1.9Z" />
      <path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="m8.5 12.2 2.2 2.2 4.9-5" />
    </>
  ),
  code: <path d="m9 8-4 4 4 4M15 8l4 4-4 4M13 6l-2 12" />,
  command: (
    <>
      <circle cx="12" cy="12" r="2.2" />
      <circle cx="6" cy="7" r="1.8" />
      <circle cx="18" cy="7" r="1.8" />
      <circle cx="6" cy="17" r="1.8" />
      <circle cx="18" cy="17" r="1.8" />
      <path d="M7.5 8.1 10.2 11M16.5 8.1 13.8 11M7.5 15.9l2.7-2.9M16.5 15.9 13.8 13" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="6.5" rx="6" ry="3" />
      <path d="M6 6.5v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5" />
      <path d="M6 11.5v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5" />
    </>
  ),
  graph: (
    <>
      <path d="M4 17.5h16" />
      <path d="m5.5 15 3.2-3.2 3 2.2 5-6.5 1.8 2.2" />
      <circle cx="8.7" cy="11.8" r="1" />
      <circle cx="11.7" cy="14" r="1" />
      <circle cx="16.7" cy="7.5" r="1" />
    </>
  ),
  inspect: (
    <>
      <path d="M3.8 12s3-5.5 8.2-5.5S20.2 12 20.2 12s-3 5.5-8.2 5.5S3.8 12 3.8 12Z" />
      <circle cx="12" cy="12" r="2.6" />
    </>
  ),
  key: (
    <>
      <circle cx="8.5" cy="13" r="3.5" />
      <path d="M11.5 11 20 2.5M15.5 6H19v3.5" />
      <path d="M7.5 13h.01" />
    </>
  ),
  layers: (
    <>
      <path d="m12 4 8 4-8 4-8-4 8-4Z" />
      <path d="m4 12 8 4 8-4" />
      <path d="m4 16 8 4 8-4" />
    </>
  ),
  meeting: (
    <>
      <circle cx="8" cy="8" r="2.5" />
      <circle cx="16" cy="8" r="2.5" />
      <path d="M4.5 18c.5-2.7 1.8-4 3.5-4s3 1.3 3.5 4" />
      <path d="M12.5 18c.5-2.7 1.8-4 3.5-4s3 1.3 3.5 4" />
    </>
  ),
  play: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="m10.5 8.8 5 3.2-5 3.2V8.8Z" />
    </>
  ),
  review: (
    <>
      <path d="M5 5h14v10H9l-4 4V5Z" />
      <path d="M8 9h8M8 12h5" />
      <path d="m15.5 16.5 1.3 1.3 2.7-3" />
    </>
  ),
  settings: (
    <>
      <path d="M5 7h14M5 12h14M5 17h14" />
      <circle cx="9" cy="7" r="1.7" />
      <circle cx="15" cy="12" r="1.7" />
      <circle cx="11" cy="17" r="1.7" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.8 18.5 6v5.6c0 4.2-2.6 7.1-6.5 8.6-3.9-1.5-6.5-4.4-6.5-8.6V6L12 3.8Z" />
      <path d="m8.8 12 2.2 2.2 4.2-4.6" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3.5 13.8 9l5.7 3-5.7 3L12 20.5 10.2 15l-5.7-3 5.7-3L12 3.5Z" />
      <path d="M19 4.5v3M20.5 6h-3" />
    </>
  ),
  token: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7v10M8.5 9.5h5.2a2.1 2.1 0 010 4.2H10" />
    </>
  ),
  workflow: (
    <>
      <rect x="4" y="5" width="5" height="5" rx="1.5" />
      <rect x="15" y="5" width="5" height="5" rx="1.5" />
      <rect x="9.5" y="15" width="5" height="5" rx="1.5" />
      <path d="M9 7.5h6M12 10v5" />
    </>
  ),
};

export function BrandIcon({
  name,
  size = 20,
  title,
  className,
  strokeWidth = 1.8,
  ...props
}: BrandIconProps) {
  return (
    <svg
      aria-hidden={title ? undefined : true}
      aria-label={title}
      className={className}
      fill="none"
      height={size}
      role={title ? "img" : undefined}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      {title && <title>{title}</title>}
      {paths[name]}
    </svg>
  );
}
