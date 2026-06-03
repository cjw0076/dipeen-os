// ---------------------------------------------------------------------------
// AgentCharacter — LPC sprite-based agent representation
// Reference: deskrpg RemotePlayer (lines 170-295) + NpcSprite.applyTexture (382-457)
// ---------------------------------------------------------------------------

import * as Phaser from "phaser";
import type { DipeenAgent } from "@/components/office/useOfficeEngine";
import { COLS } from "./sprite-compositor";

const TILE_SIZE = 32;
const LERP_FACTOR = 0.18;
const MOVE_SPEED = 120; // px/s

export const DIR_UP = 0;
export const DIR_LEFT = 1;
export const DIR_DOWN = 2;
export const DIR_RIGHT = 3;

const DIR_NAMES = ["up", "left", "down", "right"];

const STATUS_COLORS: Record<string, number> = {
  working:   0x60a5fa,
  reviewing: 0xa78bfa,
  idle:      0x52525b,
  error:     0xf87171,
  done:      0x34d399,
  offline:   0x27272a,
};

const STATUS_EMOTES: Record<string, string> = {
  working: "\u{1F4BB}", // 💻
  reviewing: "\u{1F4CB}", // 📋
  idle: "\u{1F4A4}", // 💤
  error: "\u26A0\uFE0F", // ⚠️
  done: "\u2705", // ✅
  offline: "",
};

export interface Point { x: number; y: number; }

// Fixed tile positions for each role's desk area (chair positions)
const ROLE_HOME: Record<string, { col: number; row: number }> = {
  PM:  { col: 20, row: 15 },
  FE:  { col: 9,  row: 16 },
  BE:  { col: 28, row: 16 },
  QA:  { col: 20, row: 23 },
};

export { ROLE_HOME };

function tileToWorld(col: number, row: number): { x: number; y: number } {
  return { x: (col + 0.5) * TILE_SIZE, y: (row + 0.5) * TILE_SIZE };
}

export class AgentCharacter {
  sprite: Phaser.GameObjects.Sprite;
  nameLabel: Phaser.GameObjects.Text;
  statusDot: Phaser.GameObjects.Arc;
  statusEmote: Phaser.GameObjects.Text;

  agentId: string;
  direction: number = DIR_DOWN;
  targetX: number;
  targetY: number;
  private scene: Phaser.Scene;
  private textureKey: string;
  private animKeyBase: string;

  // Path following (R-2)
  currentPath: Point[] | null = null;
  pathIndex: number = 0;
  private previousStatus: string = "";

  // Highlight glow
  private highlightGlow: Phaser.GameObjects.Graphics | null = null;
  private isHighlighted = false;

  constructor(scene: Phaser.Scene, agent: DipeenAgent) {
    this.scene = scene;
    this.agentId = agent.id;

    const role = (agent.role ?? "FE").toUpperCase();
    const home = ROLE_HOME[role] ?? ROLE_HOME.FE;
    const pos = tileToWorld(home.col, home.row);
    this.targetX = pos.x;
    this.targetY = pos.y;

    // Use preset texture if available, else fallback
    const presetKey = `preset-${role}`;
    this.textureKey = scene.textures.exists(presetKey) ? presetKey : "fallback-char";
    this.animKeyBase = this.textureKey;

    this.sprite = scene.add.sprite(pos.x, pos.y, this.textureKey);
    this.sprite.setOrigin(0.5, 0.85);
    this.sprite.setDisplaySize(48, 48);
    this.sprite.setDepth(10);

    // Set initial idle frame (facing down)
    const idleFrame = DIR_DOWN * COLS;
    if (idleFrame < (this.sprite.texture.frameTotal - 1)) {
      this.sprite.setFrame(idleFrame);
    }

    // Create walk animations for this texture
    this._createAnimations();

    // Name label
    this.nameLabel = scene.add.text(pos.x, pos.y - 44, agent.label, {
      fontSize: "10px",
      color: "#ffffff",
      stroke: "#000000",
      strokeThickness: 2,
      align: "center",
    }).setOrigin(0.5, 1).setDepth(20001);

    // Status indicator dot
    this.statusDot = scene.add.circle(
      pos.x + 14, pos.y - 38, 4,
      STATUS_COLORS[agent.status] ?? 0x52525b
    ).setDepth(20002);

    // Status emote
    this.statusEmote = scene.add.text(pos.x, pos.y - 56, "", {
      fontSize: "14px",
    }).setOrigin(0.5, 1).setDepth(20003);
    this._updateEmote(agent.status);
  }

  private _createAnimations(): void {
    const totalFrames = this.sprite.texture.frameTotal - 1;
    for (let dir = 0; dir < 4; dir++) {
      const key = `${this.animKeyBase}-walk-${DIR_NAMES[dir]}`;
      const startFrame = dir * COLS + 1;
      const endFrame = dir * COLS + COLS - 1;
      if (!this.scene.anims.exists(key) && endFrame < totalFrames) {
        this.scene.anims.create({
          key,
          frames: this.scene.anims.generateFrameNumbers(this.textureKey, {
            start: startFrame,
            end: endFrame,
          }),
          frameRate: 10,
          repeat: -1,
        });
      }
    }
  }

  update(agent: DipeenAgent): void {
    this.statusDot.setFillStyle(STATUS_COLORS[agent.status] ?? 0x52525b);
    this.nameLabel.setText(agent.label);
    this._updateEmote(agent.status);
    this.previousStatus = agent.status;
  }

  private _updateEmote(status: string): void {
    this.statusEmote.setText(STATUS_EMOTES[status] ?? "");
  }

  /** Assign a path for the character to follow */
  setPath(path: Point[]): void {
    if (path.length === 0) return;
    this.currentPath = path;
    this.pathIndex = 0;
  }

  /** Main update: follow path if set, otherwise lerp to target */
  lerpUpdate(delta: number): void {
    const moved = this._followPath(delta);
    if (!moved) {
      this._lerpToTarget();
    }
    this._syncPositions();
  }

  private _followPath(delta: number): boolean {
    if (!this.currentPath || this.pathIndex >= this.currentPath.length) {
      return false;
    }

    const target = this.currentPath[this.pathIndex];
    const tx = (target.x + 0.5) * TILE_SIZE;
    const ty = (target.y + 0.5) * TILE_SIZE;

    const dx = tx - this.sprite.x;
    const dy = ty - this.sprite.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist < 2) {
      this.sprite.setPosition(tx, ty);
      this.pathIndex++;
      if (this.pathIndex >= this.currentPath.length) {
        this.currentPath = null;
        this.stopWalk();
        return false;
      }
      return true;
    }

    // Determine direction
    const dir = Math.abs(dx) > Math.abs(dy)
      ? (dx > 0 ? DIR_RIGHT : DIR_LEFT)
      : (dy > 0 ? DIR_DOWN : DIR_UP);
    this.playWalk(dir);

    const speed = MOVE_SPEED * (delta / 1000);
    this.sprite.x += (dx / dist) * speed;
    this.sprite.y += (dy / dist) * speed;
    return true;
  }

  private _lerpToTarget(): void {
    const dx = this.targetX - this.sprite.x;
    const dy = this.targetY - this.sprite.y;

    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) {
      this.sprite.setPosition(this.targetX, this.targetY);
      this.stopWalk();
      return;
    }

    if (Math.abs(dx) > 200 || Math.abs(dy) > 200) {
      this.sprite.setPosition(this.targetX, this.targetY);
      return;
    }

    this.sprite.x += dx * LERP_FACTOR;
    this.sprite.y += dy * LERP_FACTOR;
  }

  private _syncPositions(): void {
    this.nameLabel.setPosition(this.sprite.x, this.sprite.y - 44);
    this.statusDot.setPosition(this.sprite.x + 14, this.sprite.y - 38);
    this.statusEmote.setPosition(this.sprite.x, this.sprite.y - 56);
    if (this.isHighlighted) this._drawHighlight();
  }

  playWalk(dir: number): void {
    if (dir !== this.direction || !this.sprite.anims.isPlaying) {
      this.direction = dir;
      const key = `${this.animKeyBase}-walk-${DIR_NAMES[dir]}`;
      if (this.scene.anims.exists(key)) {
        this.sprite.anims.play(key, true);
      }
    }
  }

  stopWalk(): void {
    this.sprite.anims.stop();
    const idleFrame = this.direction * COLS;
    if (idleFrame < (this.sprite.texture.frameTotal - 1)) {
      this.sprite.setFrame(idleFrame);
    }
  }

  setHighlight(on: boolean): void {
    if (on === this.isHighlighted) return;
    this.isHighlighted = on;
    if (on) {
      if (!this.highlightGlow) {
        this.highlightGlow = this.scene.add.graphics();
        this.highlightGlow.setDepth(20000);
      }
      this._drawHighlight();
    } else {
      this.highlightGlow?.clear();
    }
  }

  private _drawHighlight(): void {
    if (!this.highlightGlow) return;
    this.highlightGlow.clear();
    this.highlightGlow.lineStyle(3, 0x60a5fa, 0.8);
    this.highlightGlow.strokeRoundedRect(
      this.sprite.x - 15, this.sprite.y - 39, 30, 48, 6
    );
    this.highlightGlow.lineStyle(5, 0x60a5fa, 0.3);
    this.highlightGlow.strokeRoundedRect(
      this.sprite.x - 17, this.sprite.y - 41, 34, 52, 8
    );
  }

  get x(): number { return this.sprite.x; }
  get y(): number { return this.sprite.y; }

  destroy(): void {
    this.sprite.destroy();
    this.nameLabel.destroy();
    this.statusDot.destroy();
    this.statusEmote.destroy();
    this.highlightGlow?.destroy();
  }
}
