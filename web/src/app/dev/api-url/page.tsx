"use client";

import { useEffect, useState } from "react";
import { resolveApiOverride, isAllowedApiUrl } from "@/lib/api-url-bootstrap";
import { getApiBaseUrl, isLocalApiBase, deriveWsUrl } from "@/lib/api-base";

const CASES = [
  "https://abc.trycloudflare.com",
  "https://abc.trycloudflare.com/path?token=x",
  "http://localhost:8000",
  "http://192.168.0.10:8000",
  "https://attacker.com",
  "http://abc.trycloudflare.com",
  "https://abc.trycloudflare.com.evil.com",
  "https://user:pass@abc.trycloudflare.com",
];

export default function ApiUrlPreview() {
  const [stored, setStored] = useState("");
  useEffect(() => {
    setStored(localStorage.getItem("dipeen_api_url") ?? "(none)");
  }, []);
  const base = typeof window !== "undefined" ? getApiBaseUrl() : "";
  return (
    <div style={{ padding: 24, fontFamily: "monospace", fontSize: 13 }}>
      <h2>api-url bootstrap preview</h2>
      <p>localStorage[dipeen_api_url] = <b>{stored}</b></p>
      <p>getApiBaseUrl() = <b>{base}</b></p>
      <p>isLocalApiBase() = <b>{String(isLocalApiBase(base))}</b> → mode = <b>{isLocalApiBase(base) ? "local" : "external"}</b></p>
      <p>deriveWsUrl() = <b>{deriveWsUrl(base, "/ws/events")}</b></p>
      <hr />
      <h3>allowlist cases (resolveApiOverride)</h3>
      <table cellPadding={4}>
        <tbody>
          {CASES.map((c) => (
            <tr key={c}>
              <td>{isAllowedApiUrl(c) ? "✅" : "⛔"}</td>
              <td>{c}</td>
              <td>→ {resolveApiOverride("api=" + encodeURIComponent(c)) ?? "(rejected)"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
