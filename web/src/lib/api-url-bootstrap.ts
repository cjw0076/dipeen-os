// SSOT: docs/superpowers/specs/2026-06-03-public-tunnel-dual-web-api-design.md §6
// 동일 규칙이 layout.tsx inline script에도 복제됨(번들 import 불가). dev/api-url preview가 정합 검증.

const TRYCLOUDFLARE = /^[a-z0-9-]+\.trycloudflare\.com$/;
const LAN_10 = /^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;
const LAN_172 = /^172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}$/;
const LAN_192 = /^192\.168\.\d{1,3}\.\d{1,3}$/;

export function isAllowedApiUrl(raw: string): boolean {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return false;
  }
  if (url.username || url.password) return false;
  if (url.protocol === "https:" && TRYCLOUDFLARE.test(url.hostname)) return true;
  if (url.protocol === "http:") {
    if (url.hostname === "localhost" || url.hostname === "127.0.0.1") return true;
    if (LAN_10.test(url.hostname) || LAN_172.test(url.hostname) || LAN_192.test(url.hostname)) return true;
  }
  return false;
}

/** ?api / ?api_url 쿼리 → 검증된 origin (없거나 거부면 null). */
export function resolveApiOverride(search: string): string | null {
  const params = new URLSearchParams(search);
  const raw = params.get("api") ?? params.get("api_url");
  if (!raw) return null;
  if (!isAllowedApiUrl(raw)) return null;
  return new URL(raw).origin; // path/query/hash 폐기
}
