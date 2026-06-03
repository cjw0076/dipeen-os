import { buildBarSeries, buildDonutSegments, buildSparklinePath } from "./dataVizModel";

type Tone = "blue" | "emerald" | "violet" | "amber" | "danger" | "neutral";

const toneColor: Record<Tone, string> = {
  blue: "#60A5FA",
  emerald: "#34D399",
  violet: "#A78BFA",
  amber: "#FBBF24",
  danger: "#EF4444",
  neutral: "#A1A1AA",
};

export function Sparkline({
  values,
  tone = "blue",
  width = 160,
  height = 56,
  className,
}: {
  values: number[];
  tone?: Tone;
  width?: number;
  height?: number;
  className?: string;
}) {
  const { path, points } = buildSparklinePath(values, { width, height, padding: 8 });
  const color = toneColor[tone];

  return (
    <svg className={className} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Trend">
      <path d={`M8 ${height - 8} H${width - 8}`} stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
      <path d={path} fill="none" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.4" />
      {points.map((point) => (
        <circle key={`${point.x}-${point.y}`} cx={point.x} cy={point.y} r="2.4" fill="#09090B" stroke={color} strokeWidth="1.6" />
      ))}
    </svg>
  );
}

export function UsageBars({
  items,
  tone = "blue",
}: {
  items: Array<{ label: string; value: number; color?: string; meta?: string }>;
  tone?: Tone;
}) {
  const bars = buildBarSeries(items);
  const fallback = toneColor[tone];

  return (
    <div className="space-y-2">
      {bars.map((bar, index) => {
        const source = items[index];
        return (
          <div key={`${bar.label}-${index}`} className="space-y-1">
            <div className="flex items-center justify-between gap-3 text-[10px]">
              <span className="truncate font-medium text-text-secondary">{bar.label}</span>
              <span className="shrink-0 font-mono text-text-muted">{bar.value.toLocaleString()}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{
                  width: `${bar.percent}%`,
                  backgroundColor: source?.color ?? fallback,
                }}
              />
            </div>
            {source?.meta && <p className="truncate text-[9px] text-text-muted">{source.meta}</p>}
          </div>
        );
      })}
    </div>
  );
}

export function TokenDonut({
  items,
  size = 82,
  strokeWidth = 9,
}: {
  items: Array<{ label: string; value: number; color: string }>;
  size?: number;
  strokeWidth?: number;
}) {
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  const segments = buildDonutSegments(items, { radius, gap: 3 });
  const total = items.reduce((sum, item) => sum + Math.max(0, item.value), 0);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Token distribution">
      <circle cx={center} cy={center} r={radius} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={strokeWidth} />
      {segments.map((segment, index) => (
        <circle
          key={`${segment.label}-${index}`}
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={segment.color}
          strokeDasharray={segment.dashArray}
          strokeDashoffset={segment.dashOffset}
          strokeLinecap="round"
          strokeWidth={strokeWidth}
          transform={`rotate(-90 ${center} ${center})`}
        />
      ))}
      <text x="50%" y="49%" dominantBaseline="middle" textAnchor="middle" className="fill-text-primary font-mono text-[12px] font-semibold">
        {total}
      </text>
      <text x="50%" y="64%" dominantBaseline="middle" textAnchor="middle" className="fill-text-muted text-[8px]">
        total
      </text>
    </svg>
  );
}

export function WorkflowGraph({
  counts,
}: {
  counts: Array<{ label: string; value: number; color: string }>;
}) {
  const max = Math.max(1, ...counts.map((item) => item.value));

  return (
    <div className="grid grid-cols-4 gap-2">
      {counts.map((item, index) => {
        const height = 22 + Math.round((item.value / max) * 34);
        return (
          <div key={`${item.label}-${index}`} className="flex min-w-0 flex-col items-center gap-1">
            <div className="flex h-16 items-end">
              <span
                className="w-8 rounded-t-md border border-white/10"
                style={{
                  height,
                  background: `linear-gradient(180deg, ${item.color}, rgba(255,255,255,0.04))`,
                }}
              />
            </div>
            <span className="font-mono text-[10px] text-text-secondary">{item.value}</span>
            <span className="max-w-full truncate text-[9px] text-text-muted">{item.label}</span>
            {index < counts.length - 1 && <span className="sr-only">then</span>}
          </div>
        );
      })}
    </div>
  );
}
