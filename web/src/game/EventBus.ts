import mitt from "mitt";
import type { DipeenAgent } from "@/components/office/useOfficeEngine";

type Events = {
  /** GameScene이 준비됐을 때 emit */
  "scene-ready": void;
  /** React→Phaser: 에이전트 상태 배열 전달 */
  "agent-state-update": DipeenAgent[];
  /** Phaser→React: 에이전트 클릭 시 agent.id (또는 null = 선택 해제) */
  "agent-selected": string | null;
  /** React→Phaser: 에이전트 위에 말풍선 표시 */
  "agent-speech": { agentId: string; text: string };
  /** Phaser→React: 회의실 zone 내 에이전트 목록 */
  "meeting-zone-agents": string[];
  /** React→Phaser: 사용자 캐릭터를 해당 월드 좌표로 이동 */
  "user-move-to": { worldX: number; worldY: number };
  /** Phaser→React: 에이전트 마지막 메시지 */
  "agent-last-message": { agentId: string; message: string };
  /** React→React: 채팅 패널에 포커스 요청 */
  "focus-chat-room": Record<string, never>;
};

export const EventBus = mitt<Events>();
