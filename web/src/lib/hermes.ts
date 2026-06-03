"use client";
import { WSManager } from './ws';

export const hermesManager = new WSManager();

export function getHermesUrl(teamId: string = 'default-team') {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // apiFetch(getBase)와 같은 소스를 따른다: localStorage override → NEXT_PUBLIC_API_URL → localhost:8000.
  // (.env.local이 stale 포트를 가리켜도 런타임 override를 우선해 UI 로그가 올바른 HQ에 붙는다.)
  const override = typeof window !== 'undefined' ? localStorage.getItem('dipeen_api_url') : null;
  const base = (override?.trim() || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');
  const host = base.replace(/^https?:\/\//, '');
  return `${protocol}//${host}/ws/hermes/ui?team_id=${teamId}`;
}
