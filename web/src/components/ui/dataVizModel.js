function round(value) {
  return Math.round(value * 100) / 100;
}

function format(value) {
  const rounded = round(value);
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
}

function formatFixed(value) {
  return round(value).toFixed(2);
}

export function buildSparklinePath(values, options = {}) {
  const width = options.width ?? 160;
  const height = options.height ?? 56;
  const padding = options.padding ?? 6;
  const normalized = Array.isArray(values) ? values.filter(Number.isFinite) : [];

  if (normalized.length === 0) {
    return { path: "", points: [] };
  }

  const min = Math.min(...normalized);
  const max = Math.max(...normalized);
  const range = max - min;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const step = normalized.length === 1 ? 0 : innerWidth / (normalized.length - 1);

  const points = normalized.map((value, index) => {
    const x = round(padding + step * index);
    const y = range === 0
      ? round(height / 2)
      : round(padding + ((max - value) / range) * innerHeight);
    return { value, x, y };
  });

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${format(point.x)} ${format(point.y)}`)
    .join(" ");

  return { path, points };
}

export function buildBarSeries(items) {
  const normalized = Array.isArray(items) ? items : [];
  const max = Math.max(0, ...normalized.map((item) => Number(item.value) || 0));

  return normalized.map((item) => {
    const value = Number(item.value) || 0;
    return {
      label: String(item.label ?? ""),
      value,
      percent: max === 0 ? 0 : Math.round((value / max) * 100),
    };
  });
}

export function buildDonutSegments(items, options = {}) {
  const radius = options.radius ?? 22;
  const gap = options.gap ?? 2;
  const normalized = (Array.isArray(items) ? items : []).map((item) => ({
    label: String(item.label ?? ""),
    value: Math.max(0, Number(item.value) || 0),
    color: item.color,
  }));
  const total = normalized.reduce((sum, item) => sum + item.value, 0);
  const circumference = 2 * Math.PI * radius;

  if (total === 0) {
    return [];
  }

  let offset = 0;
  return normalized.map((item) => {
    const rawLength = (item.value / total) * circumference;
    const visibleLength = Math.max(0, rawLength - gap);
    const segment = {
      label: item.label,
      value: item.value,
      color: item.color,
      dashArray: `${formatFixed(visibleLength)} ${formatFixed(circumference)}`,
      dashOffset: formatFixed(-offset),
    };
    offset += rawLength;
    return segment;
  });
}
