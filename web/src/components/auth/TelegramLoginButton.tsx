"use client";

import { useEffect, useRef } from "react";
import { auth } from "@/lib/auth";

interface TelegramUser {
  id: number;
  first_name: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

interface Props {
  botName?: string;
  onSuccess?: (user: TelegramUser) => void;
  onError?: (msg: string) => void;
  buttonSize?: "large" | "medium" | "small";
  className?: string;
}

declare global {
  interface Window {
    TelegramLoginWidget?: { dataOnauth: (user: TelegramUser) => void };
    onTelegramAuth?: (user: TelegramUser) => void;
  }
}

const API_URL =
  typeof window !== "undefined"
    ? (localStorage.getItem("dipeen_api_url") ?? "http://localhost:8000")
    : "http://localhost:8000";

export function TelegramLoginButton({
  botName = process.env.NEXT_PUBLIC_TELEGRAM_BOT_NAME ?? "",
  onSuccess,
  onError,
  buttonSize = "medium",
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!botName || !containerRef.current) return;

    // Telegram Widget callback
    window.onTelegramAuth = async (user: TelegramUser) => {
      try {
        const res = await fetch(`${API_URL}/api/auth/telegram`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(user),
        });
        if (!res.ok) {
          const err = await res.json();
          onError?.(err.detail ?? "Auth failed");
          return;
        }
        const data = await res.json();
        auth.setToken(data.access_token);
        onSuccess?.(user);
      } catch (e) {
        onError?.(String(e));
      }
    };

    // Inject Telegram widget script
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", botName);
    script.setAttribute("data-size", buttonSize);
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    script.async = true;

    containerRef.current.innerHTML = "";
    containerRef.current.appendChild(script);

    return () => {
      delete window.onTelegramAuth;
    };
  }, [botName, buttonSize, onSuccess, onError]);

  if (!botName) {
    return (
      <div className={`text-[11px] text-text-muted ${className ?? ""}`}>
        NEXT_PUBLIC_TELEGRAM_BOT_NAME 미설정
      </div>
    );
  }

  return <div ref={containerRef} className={className} />;
}
