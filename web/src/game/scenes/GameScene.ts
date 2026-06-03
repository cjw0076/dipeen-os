import * as Phaser from "phaser";
import { EventBus } from "../EventBus";
import { AgentCharacter, ROLE_HOME, DIR_DOWN } from "../AgentCharacter";
import type { DipeenAgent } from "@/components/office/useOfficeEngine";
import type { Point } from "../AgentCharacter";
import { findPath } from "../pathfinding";
import { SpeechBubble } from "../SpeechBubble";
import { PathRenderer } from "../PathRenderer";
import { UserCharacter } from "../UserCharacter";

// ── Map constants ────────────────────────────────────────────────
const MAP_COLS = 40;
const MAP_ROWS = 30;
const TILE_SIZE = 32;
const MAIN_CAMERA_ZOOM = 2;

// Tile indices
const T = {
  EMPTY: 0, FLOOR: 1, WALL: 2, DESK: 3, CHAIR: 4, COMPUTER: 5,
  PLANT: 6, DOOR: 7, MEETING_TABLE: 8, COFFEE: 9, WATER_COOLER: 10,
  BOOKSHELF: 11, CARPET: 12, WHITEBOARD: 13, RECEPTION_DESK: 14, CUBICLE_WALL: 15,
};

// Tiles that block movement
const BLOCKED_TILES = new Set([
  T.WALL, T.DESK, T.MEETING_TABLE, T.BOOKSHELF, T.RECEPTION_DESK,
  T.COMPUTER, T.CUBICLE_WALL, T.WHITEBOARD,
]);

// Meeting room zone bounds (tile coords)
const MEETING_ZONE = { x1: 17, y1: 6, x2: 22, y2: 11 };

// Proximity bubble constants
const PROXIMITY_RADIUS = 48;
const BUBBLE_COLOR     = 0x6366f1;
const BUBBLE_ALPHA     = 0.06;

// ── GameScene ────────────────────────────────────────────────────

export class GameScene extends Phaser.Scene {
  private characters = new Map<string, AgentCharacter>();
  private roleMap = new Map<string, AgentCharacter>(); // role → char (FE, BE, PM, QA)
  private selectedId: string | null = null;
  private onAgentUpdate!: (agents: DipeenAgent[]) => void;
  private onAgentSpeech!: (data: { agentId: string; text: string }) => void;
  private collisionGrid: boolean[][] = [];
  private mapData: number[][] = [];
  private activeBubbles = new Map<string, SpeechBubble>();
  private previousStatuses = new Map<string, string>();
  private lastAgents: DipeenAgent[] = [];
  private pathRenderer!: PathRenderer;
  private userChar!: UserCharacter;
  private proximityBubbles = new Map<string, Phaser.GameObjects.Arc>();
  private _fadingBubbles = new Set<Phaser.GameObjects.Arc>();
  private onUserMoveTo!: (data: { worldX: number; worldY: number }) => void;

  constructor() {
    super({ key: "GameScene" });
  }

  create(): void {
    this._buildMap();
    this._buildCollisionGrid();
    this._setupCamera();
    this._setupInput();
    this.pathRenderer = new PathRenderer(this);
    this.userChar = new UserCharacter(this, 20, 20);
    this._subscribeEvents();
    EventBus.emit("scene-ready");
  }

  // ── Map ───────────────────────────────────────────────────────

  private _buildMap(): void {
    const map: number[][] = Array.from({ length: MAP_ROWS }, () =>
      Array(MAP_COLS).fill(T.FLOOR)
    );

    // Border walls
    for (let c = 0; c < MAP_COLS; c++) {
      map[0][c] = T.WALL; map[MAP_ROWS - 1][c] = T.WALL;
    }
    for (let r = 0; r < MAP_ROWS; r++) {
      map[r][0] = T.WALL; map[r][MAP_COLS - 1] = T.WALL;
    }

    // ── Meeting room (center-top) ──────────────────────────────
    // Walls around meeting room
    for (let c = 16; c <= 23; c++) { map[5][c] = T.WALL; map[12][c] = T.WALL; }
    for (let r = 5; r <= 12; r++) { map[r][16] = T.WALL; map[r][23] = T.WALL; }
    map[12][19] = T.DOOR; map[12][20] = T.DOOR; // entrance
    // Carpet floor
    for (let r = 6; r <= 11; r++) {
      for (let c = 17; c <= 22; c++) map[r][c] = T.CARPET;
    }
    // Meeting table
    for (let r = 7; r <= 10; r++) {
      for (let c = 18; c <= 21; c++) map[r][c] = T.MEETING_TABLE;
    }
    map[5][19] = T.WHITEBOARD; map[5][20] = T.WHITEBOARD;

    // ── Coffee / break area (top-left) ─────────────────────────
    for (let r = 2; r <= 6; r++) { map[r][6] = T.CUBICLE_WALL; }
    map[2][2] = T.COFFEE; map[2][3] = T.WATER_COOLER;
    map[3][2] = T.PLANT; map[4][2] = T.PLANT;
    map[3][4] = T.CHAIR; map[4][4] = T.CHAIR;
    map[5][3] = T.BOOKSHELF;

    // ── Server room (top-right) ────────────────────────────────
    for (let r = 2; r <= 6; r++) { map[r][32] = T.CUBICLE_WALL; }
    map[2][33] = T.COMPUTER; map[2][34] = T.COMPUTER; map[2][35] = T.COMPUTER;
    map[3][33] = T.COMPUTER; map[3][34] = T.COMPUTER; map[3][35] = T.COMPUTER;
    map[4][33] = T.CUBICLE_WALL; map[4][35] = T.CUBICLE_WALL;
    map[5][34] = T.BOOKSHELF;

    // ── FE Desk area (left wing) ───────────────────────────────
    // Cubicle walls
    map[13][8] = T.CUBICLE_WALL; map[13][12] = T.CUBICLE_WALL;
    map[17][8] = T.CUBICLE_WALL; map[17][12] = T.CUBICLE_WALL;
    // Desk cluster
    map[14][9] = T.DESK; map[14][10] = T.COMPUTER;
    map[15][9] = T.CHAIR;
    map[16][10] = T.PLANT;
    // Extra desks for team feel
    map[14][11] = T.DESK; map[15][11] = T.CHAIR;

    // ── PM Desk area (center) ──────────────────────────────────
    map[13][19] = T.DESK; map[13][20] = T.COMPUTER; map[13][21] = T.DESK;
    map[14][20] = T.CHAIR;
    map[14][18] = T.PLANT; map[14][22] = T.PLANT;
    map[13][18] = T.BOOKSHELF;

    // ── BE Desk area (right wing) ──────────────────────────────
    map[13][27] = T.CUBICLE_WALL; map[13][31] = T.CUBICLE_WALL;
    map[17][27] = T.CUBICLE_WALL; map[17][31] = T.CUBICLE_WALL;
    map[14][28] = T.DESK; map[14][29] = T.COMPUTER;
    map[15][28] = T.CHAIR;
    map[16][29] = T.PLANT;
    map[14][30] = T.DESK; map[15][30] = T.CHAIR;

    // ── QA Desk area (bottom-center) ───────────────────────────
    map[20][18] = T.CUBICLE_WALL; map[20][22] = T.CUBICLE_WALL;
    map[24][18] = T.CUBICLE_WALL; map[24][22] = T.CUBICLE_WALL;
    map[21][19] = T.DESK; map[21][20] = T.COMPUTER; map[21][21] = T.DESK;
    map[22][19] = T.CHAIR; map[22][21] = T.CHAIR;
    map[23][20] = T.PLANT;

    // ── Reception (bottom) ─────────────────────────────────────
    for (let c = 15; c <= 24; c++) map[26][c] = T.WALL;
    map[26][19] = T.DOOR; map[26][20] = T.DOOR;
    map[27][17] = T.RECEPTION_DESK; map[27][18] = T.RECEPTION_DESK;
    map[27][21] = T.RECEPTION_DESK; map[27][22] = T.RECEPTION_DESK;
    map[28][17] = T.CHAIR; map[28][22] = T.CHAIR;
    map[27][15] = T.PLANT; map[27][24] = T.PLANT;

    // ── Hallway decorations ────────────────────────────────────
    // Left hallway
    map[10][2] = T.BOOKSHELF; map[11][2] = T.BOOKSHELF;
    map[20][2] = T.PLANT; map[25][2] = T.PLANT;
    // Right hallway
    map[10][37] = T.BOOKSHELF; map[11][37] = T.BOOKSHELF;
    map[20][37] = T.PLANT; map[25][37] = T.PLANT;
    // Center corridor plants
    map[18][15] = T.PLANT; map[18][24] = T.PLANT;

    this.mapData = map;
    this._drawTileMap(map);
  }

  private _drawTileMap(map: number[][]): void {
    // Use individual tile textures generated by BootScene for detailed rendering
    map.forEach((row, r) => {
      row.forEach((tileIdx, c) => {
        if (tileIdx === T.EMPTY) return;
        const texKey = `tile-${tileIdx}`;
        if (this.textures.exists(texKey)) {
          this.add.image(
            c * TILE_SIZE + TILE_SIZE / 2,
            r * TILE_SIZE + TILE_SIZE / 2,
            texKey,
          ).setDepth(0);
        }
      });
    });

    // Zone labels with background for readability
    const labelStyle: Phaser.Types.GameObjects.Text.TextStyle = {
      fontSize: "8px",
      color: "#e0e0e0",
      stroke: "#1a1a2e",
      strokeThickness: 3,
      fontStyle: "bold",
    };
    const zones: [string, number, number][] = [
      ["Meeting Room", 17, 4],
      ["Break Room", 2, 1],
      ["Server Room", 33, 1],
      ["Reception", 17, 25],
    ];
    zones.forEach(([label, col, row]) => {
      this.add.text(col * TILE_SIZE, row * TILE_SIZE + 8, label, labelStyle)
        .setDepth(2).setAlpha(0.7);
    });

    // Role desk labels
    const deskStyle: Phaser.Types.GameObjects.Text.TextStyle = {
      fontSize: "7px",
      color: "#fbbf24",
      stroke: "#000000",
      strokeThickness: 2,
    };
    Object.entries(ROLE_HOME).forEach(([role, { col, row }]) => {
      this.add.text(col * TILE_SIZE, (row - 2) * TILE_SIZE + 16, role, deskStyle)
        .setDepth(2).setAlpha(0.6);
    });
  }

  private _buildCollisionGrid(): void {
    this.collisionGrid = this.mapData.map(row =>
      row.map(t => !BLOCKED_TILES.has(t))
    );
  }

  private _isWalkable = (tx: number, ty: number): boolean => {
    if (tx < 0 || ty < 0 || tx >= MAP_COLS || ty >= MAP_ROWS) return false;
    return this.collisionGrid[ty][tx];
  };

  // ── Camera ────────────────────────────────────────────────────

  private _setupCamera(): void {
    const worldW = MAP_COLS * TILE_SIZE;
    const worldH = MAP_ROWS * TILE_SIZE;
    this.cameras.main
      .setBounds(0, 0, worldW, worldH)
      .setZoom(MAIN_CAMERA_ZOOM)
      .centerOn(worldW / 2, worldH / 2);
  }

  // ── Input ─────────────────────────────────────────────────────

  private _setupInput(): void {
    this.input.on("pointerdown", (ptr: Phaser.Input.Pointer) => {
      const worldPoint = this.cameras.main.getWorldPoint(ptr.x, ptr.y);
      const worldX = worldPoint.x;
      const worldY = worldPoint.y;

      // right-click → move user character
      if (ptr.rightButtonDown()) {
        this._moveUserTo(worldX, worldY);
        return;
      }

      // left-click → agent selection (existing logic preserved)
      let hit: string | null = null;
      let minDist = 24;
      this.characters.forEach((char, id) => {
        const dist = Phaser.Math.Distance.Between(worldX, worldY, char.x, char.y);
        if (dist < minDist) { minDist = dist; hit = id; }
      });

      if (hit === this.selectedId) {
        this._setSelected(null);
      } else {
        this._setSelected(hit);
        if (hit) {
          const agent = this.lastAgents.find(a => a.id === hit);
          if (agent?.task) this._showSpeechBubble(hit, agent.task);
        }
      }
    });

    this.input.mouse?.disableContextMenu();
  }

  private _moveUserTo(worldX: number, worldY: number): void {
    let targetCol = Math.floor(worldX / TILE_SIZE);
    let targetRow = Math.floor(worldY / TILE_SIZE);

    if (!this._isWalkable(targetCol, targetRow)) {
      outer: for (let r = 1; r <= 3; r++) {
        for (const [dc, dr] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,1],[1,-1],[-1,-1]]) {
          const nc = targetCol + (dc as number) * r;
          const nr = targetRow + (dr as number) * r;
          if (this._isWalkable(nc, nr)) { targetCol = nc; targetRow = nr; break outer; }
        }
      }
    }
    if (!this._isWalkable(targetCol, targetRow)) return;

    const startCol = Math.floor(this.userChar.x / TILE_SIZE);
    const startRow = Math.floor(this.userChar.y / TILE_SIZE);
    if (startCol === targetCol && startRow === targetRow) return;

    const path = findPath(startCol, startRow, targetCol, targetRow, this._isWalkable);
    if (!path || path.length === 0) return;

    this.userChar.setPath(path);
    const worldPoints = path.map(p => ({ x: (p.x + 0.5) * TILE_SIZE, y: (p.y + 0.5) * TILE_SIZE }));
    this.pathRenderer.showPath(worldPoints);
  }

  private _setSelected(id: string | null): void {
    if (this.selectedId) {
      this.characters.get(this.selectedId)?.setHighlight(false);
    }
    this.selectedId = id;
    if (id) {
      this.characters.get(id)?.setHighlight(true);
    }
    EventBus.emit("agent-selected", id);
  }

  // ── Speech Bubbles ────────────────────────────────────────────

  private _showSpeechBubble(agentId: string, text: string): void {
    // Remove existing bubble for this agent
    this.activeBubbles.get(agentId)?.destroy();

    const char = this.characters.get(agentId) ?? this.roleMap.get(agentId.toUpperCase());
    if (!char) return;

    const bubble = new SpeechBubble(this, char.x, char.y - 60, text);
    this.activeBubbles.set(agentId, bubble);

    this.time.delayedCall(4000, () => {
      if (this.activeBubbles.get(agentId) === bubble) {
        bubble.destroy();
        this.activeBubbles.delete(agentId);
      }
    });
  }

  // ── Meeting Zone Detection ────────────────────────────────────

  private _checkMeetingZone(): void {
    const inZone: string[] = [];
    this.characters.forEach((char, id) => {
      const col = Math.floor(char.x / TILE_SIZE);
      const row = Math.floor(char.y / TILE_SIZE);
      if (col >= MEETING_ZONE.x1 && col <= MEETING_ZONE.x2 &&
          row >= MEETING_ZONE.y1 && row <= MEETING_ZONE.y2) {
        inZone.push(id);
      }
    });
    EventBus.emit("meeting-zone-agents", inZone);
  }

  // ── Proximity Bubbles ─────────────────────────────────────────

  private _updateProximityBubbles(): void {
    const ids = [...this.characters.keys()];
    const activePairs = new Set<string>();

    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = this.characters.get(ids[i])!;
        const b = this.characters.get(ids[j])!;
        const dist = Phaser.Math.Distance.Between(a.x, a.y, b.x, b.y);
        const pairKey = ids[i] < ids[j] ? `${ids[i]}:${ids[j]}` : `${ids[j]}:${ids[i]}`;

        if (dist < PROXIMITY_RADIUS) {
          activePairs.add(pairKey);
          if (!this.proximityBubbles.has(pairKey)) {
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            const radius = dist / 2 + 28;
            const bubble = this.add.arc(mx, my, radius, 0, 360, false, BUBBLE_COLOR, BUBBLE_ALPHA)
              .setDepth(4)
              .setScale(0.1);
            this.proximityBubbles.set(pairKey, bubble);
            this.tweens.add({ targets: bubble, scaleX: 1, scaleY: 1, duration: 300, ease: "Back.Out" });
          } else {
            const bubble = this.proximityBubbles.get(pairKey)!;
            bubble.setPosition((a.x + b.x) / 2, (a.y + b.y) / 2);
            bubble.setRadius(dist / 2 + 28);
          }
        }
      }
    }

    this.proximityBubbles.forEach((bubble, key) => {
      if (!activePairs.has(key)) {
        this.proximityBubbles.delete(key);
        this._fadingBubbles.add(bubble);
        this.tweens.add({
          targets: bubble,
          scaleX: 0, scaleY: 0, alpha: 0,
          duration: 250,
          onComplete: () => {
            bubble.destroy();
            this._fadingBubbles.delete(bubble);
          },
        });
      }
    });
  }

  // ── Status-Based Movement ─────────────────────────────────────

  private _handleStatusChange(agent: DipeenAgent, char: AgentCharacter): void {
    const prevStatus = this.previousStatuses.get(agent.id);
    if (prevStatus === agent.status) return;
    this.previousStatuses.set(agent.id, agent.status);

    const role = (agent.role ?? "FE").toUpperCase();
    let targetCol: number;
    let targetRow: number;

    switch (agent.status) {
      case "working":
      case "done": {
        const home = ROLE_HOME[role] ?? ROLE_HOME.FE;
        targetCol = home.col;
        targetRow = home.row;
        break;
      }
      case "reviewing": {
        // Go to meeting room
        targetCol = 19 + Math.floor(Math.random() * 2);
        targetRow = 8 + Math.floor(Math.random() * 2);
        break;
      }
      case "idle": {
        // Random wander near home
        const home = ROLE_HOME[role] ?? ROLE_HOME.FE;
        const offset = () => Math.floor(Math.random() * 7) - 3;
        targetCol = Math.max(1, Math.min(MAP_COLS - 2, home.col + offset()));
        targetRow = Math.max(1, Math.min(MAP_ROWS - 2, home.row + offset()));
        break;
      }
      default:
        return; // offline, error — stay put
    }

    const startCol = Math.floor(char.x / TILE_SIZE);
    const startRow = Math.floor(char.y / TILE_SIZE);

    if (startCol === targetCol && startRow === targetRow) return;

    const path = findPath(startCol, startRow, targetCol, targetRow, this._isWalkable);
    if (path) {
      char.setPath(path);
    }
  }

  // ── Events ────────────────────────────────────────────────────

  private _subscribeEvents(): void {
    this.onAgentUpdate = (agents: DipeenAgent[]) => {
      this.lastAgents = agents;
      const seen = new Set<string>();

      agents.forEach((agent) => {
        seen.add(agent.id);
        const existing = this.characters.get(agent.id);
        if (existing) {
          existing.update(agent);
          this._handleStatusChange(agent, existing);
        } else {
          const char = new AgentCharacter(this, agent);
          this.characters.set(agent.id, char);
          this.roleMap.set((agent.role ?? "").toUpperCase(), char);
          this.previousStatuses.set(agent.id, agent.status);
        }
      });

      // Remove characters for agents no longer in list
      this.characters.forEach((char, id) => {
        if (!seen.has(id)) {
          char.destroy();
          this.characters.delete(id);
          this.previousStatuses.delete(id);
          if (this.selectedId === id) this._setSelected(null);
        }
      });
    };

    this.onAgentSpeech = (data: { agentId: string; text: string }) => {
      this._showSpeechBubble(data.agentId, data.text);
    };

    this.onUserMoveTo = (data: { worldX: number; worldY: number }) => {
      this._moveUserTo(data.worldX, data.worldY);
    };

    EventBus.on("agent-state-update", this.onAgentUpdate);
    EventBus.on("agent-speech", this.onAgentSpeech);
    EventBus.on("user-move-to", this.onUserMoveTo);
  }

  // ── Update Loop ───────────────────────────────────────────────

  update(_time: number, delta: number): void {
    this.characters.forEach((char) => char.lerpUpdate(delta));

    this.userChar.lerpUpdate(delta);

    if (this.userChar.isMoving()) {
      this.pathRenderer.update(delta);
    } else {
      if ((this.pathRenderer as unknown as { pathPoints: { x: number; y: number }[] }).pathPoints?.length > 0) {
        this.pathRenderer.clearPath();
      }
    }

    this.activeBubbles.forEach((bubble, id) => {
      const char = this.characters.get(id);
      if (char) bubble.updatePosition(char.x, char.y - 60);
    });

    this._updateProximityBubbles();

    if (Math.random() < 0.03) this._checkMeetingZone();
  }

  shutdown(): void {
    EventBus.off("agent-state-update", this.onAgentUpdate);
    EventBus.off("agent-speech", this.onAgentSpeech);
    EventBus.off("user-move-to", this.onUserMoveTo);
    this.pathRenderer.destroy();
    this.userChar.destroy();
    this.proximityBubbles.forEach(b => b.destroy());
    this.proximityBubbles.clear();
    this._fadingBubbles.forEach(b => b.destroy());
    this._fadingBubbles.clear();
    this.roleMap.clear();
  }
}
