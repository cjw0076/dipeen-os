// API base URL의 단일 소스. localStorage override > NEXT_PUBLIC_API_URL > localhost.
const DEFAULT_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const override = localStorage.getItem("dipeen_api_url");
    if (override?.trim()) return override.trim();
  }
  return DEFAULT_BASE;
}

/** localhost / 127.0.0.1 / 사설 LAN 이면 true → local/dev UX 허용 대상. */
export function isLocalApiBase(base: string = getApiBaseUrl()): boolean {
  try {
    const h = new URL(base).hostname;
    return (
      h === "localhost" ||
      h === "127.0.0.1" ||
      /^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(h) ||
      /^172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}$/.test(h) ||
      /^192\.168\.\d{1,3}\.\d{1,3}$/.test(h)
    );
  } catch {
    return true; // 파싱 불가 시 보수적으로 local 취급(외부 노출로 오판 방지)
  }
}

/** http(s) base → ws(s) URL + path. (Providers의 인라인 derive를 대체) */
export function deriveWsUrl(base: string = getApiBaseUrl(), path: string = "/ws/events"): string {
  return base.replace(/^http/, "ws").replace(/\/$/, "") + path;
}
