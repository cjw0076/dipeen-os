"use client";

import { useState, useCallback } from "react";

const KEY_NAME = "dipeen_user_name";
const KEY_EMOJI = "dipeen_user_emoji";

function getStored(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return localStorage.getItem(key) || fallback;
}

export function useUserProfile() {
  const [name, setName] = useState(() => getStored(KEY_NAME, "You"));
  const [emoji, setEmoji] = useState(() => getStored(KEY_EMOJI, "\u{1F464}")); // 👤

  const save = useCallback((newName: string, newEmoji: string) => {
    const n = newName.trim() || "You";
    localStorage.setItem(KEY_NAME, n);
    localStorage.setItem(KEY_EMOJI, newEmoji);
    setName(n);
    setEmoji(newEmoji);
  }, []);

  return { name, emoji, save };
}

/** Get user display name without hook (for API calls) */
export function getUserName(): string {
  if (typeof window === "undefined") return "You";
  return localStorage.getItem(KEY_NAME) || "You";
}
