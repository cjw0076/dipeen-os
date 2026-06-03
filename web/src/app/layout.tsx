import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "dipeen — AI Agent Workspace",
  description: "Multi-PM agent collaboration platform",
};

// React/LoginGate/api.ts보다 먼저 실행 — ?api= 쿼리를 검증해 localStorage에 origin만 저장하고 쿼리 제거.
// allowlist 규칙은 web/src/lib/api-url-bootstrap.ts 와 동일(SSOT). dev/api-url preview가 정합 확인.
const BOOTSTRAP = `(function(){try{
var p=new URLSearchParams(location.search);var raw=p.get("api")||p.get("api_url");if(!raw)return;
var u;try{u=new URL(raw)}catch(e){return}
if(u.username||u.password)return;
var ok=false,h=u.hostname;
if(u.protocol==="https:"&&/^[a-z0-9-]+\\.trycloudflare\\.com$/.test(h))ok=true;
else if(u.protocol==="http:"&&(h==="localhost"||h==="127.0.0.1"))ok=true;
else if(u.protocol==="http:"&&(/^10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$/.test(h)||/^172\\.(1[6-9]|2\\d|3[01])\\.\\d{1,3}\\.\\d{1,3}$/.test(h)||/^192\\.168\\.\\d{1,3}\\.\\d{1,3}$/.test(h)))ok=true;
if(!ok)return;
localStorage.setItem("dipeen_api_url",u.origin);
p.delete("api");p.delete("api_url");
var q=p.toString();history.replaceState(null,"",location.pathname+(q?"?"+q:"")+location.hash);
}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" data-dipeen-locale="ko" data-dipeen-theme="light">
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOTSTRAP }} />
      </head>
      <body className="ds-page h-screen overflow-hidden">{children}</body>
    </html>
  );
}
