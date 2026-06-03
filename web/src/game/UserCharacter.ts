// ---------------------------------------------------------------------------
// UserCharacter — Player avatar representation in virtual office
// Reference: AgentCharacter.ts path-following + arc rendering pattern
// ---------------------------------------------------------------------------

import * as Phaser from "phaser";
import type { Point } from "./AgentCharacter";

const TILE_SIZE = 32;
const MOVE_SPEED = 120; // px/s
const USER_COLOR = 0x818cf8;
const USER_RADIUS = 10;

export class UserCharacter {
  private circle: Phaser.GameObjects.Arc;
  private label: Phaser.GameObjects.Text;
  private currentPath: Point[] | null = null;
  private pathIndex = 0;

  constructor(private scene: Phaser.Scene, startCol: number, startRow: number) {
    const sx = (startCol + 0.5) * TILE_SIZE;
    const sy = (startRow + 0.5) * TILE_SIZE;

    this.circle = scene.add.arc(sx, sy, USER_RADIUS, 0, 360, false, USER_COLOR, 1)
      .setDepth(11)
      .setStrokeStyle(2, 0xa5b4fc, 1);

    this.label = scene.add.text(sx, sy - 18, "You", {
      fontSize: "9px",
      color: "#c7d2fe",
      stroke: "#1e1b4b",
      strokeThickness: 2,
      align: "center",
    }).setOrigin(0.5, 1).setDepth(20004);
  }

  setPath(path: Point[]): void {
    if (path.length === 0) return;
    this.currentPath = path;
    this.pathIndex = 0;
  }

  isMoving(): boolean {
    return this.currentPath !== null && this.pathIndex < this.currentPath.length;
  }

  lerpUpdate(delta: number): void {
    if (!this.currentPath || this.pathIndex >= this.currentPath.length) {
      this._syncLabel();
      return;
    }

    const target = this.currentPath[this.pathIndex];
    const tx = (target.x + 0.5) * TILE_SIZE;
    const ty = (target.y + 0.5) * TILE_SIZE;
    const dx = tx - this.circle.x;
    const dy = ty - this.circle.y;
    const dist = Math.hypot(dx, dy);

    if (dist < 2) {
      this.circle.setPosition(tx, ty);
      this.pathIndex++;
      if (this.pathIndex >= this.currentPath.length) {
        this.currentPath = null;
      }
    } else {
      const speed = MOVE_SPEED * (delta / 1000);
      this.circle.x += (dx / dist) * speed;
      this.circle.y += (dy / dist) * speed;
    }

    this._syncLabel();
  }

  private _syncLabel(): void {
    this.label.setPosition(this.circle.x, this.circle.y - 14);
  }

  get x(): number { return this.circle.x; }
  get y(): number { return this.circle.y; }

  destroy(): void {
    this.circle.destroy();
    this.label.destroy();
  }
}
