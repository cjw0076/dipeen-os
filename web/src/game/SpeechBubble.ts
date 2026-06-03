// ---------------------------------------------------------------------------
// SpeechBubble — floating text bubble above agent sprites
// ---------------------------------------------------------------------------

import * as Phaser from "phaser";

const MAX_WIDTH = 120;
const PADDING = 6;
const BORDER_RADIUS = 8;

export class SpeechBubble {
  private bg: Phaser.GameObjects.Graphics;
  private text: Phaser.GameObjects.Text;

  constructor(scene: Phaser.Scene, x: number, y: number, message: string) {
    // Truncate long messages
    const display = message.length > 50 ? message.slice(0, 47) + "..." : message;

    this.text = scene.add.text(x, y, display, {
      fontSize: "8px",
      color: "#1a1a2e",
      wordWrap: { width: MAX_WIDTH - PADDING * 2 },
      align: "center",
    }).setOrigin(0.5, 1).setDepth(30001);

    const bounds = this.text.getBounds();
    const w = Math.max(bounds.width + PADDING * 2, 30);
    const h = bounds.height + PADDING * 2;

    this.bg = scene.add.graphics().setDepth(30000);
    this._drawBubble(x, y, w, h);
  }

  private _drawBubble(x: number, y: number, w: number, h: number): void {
    this.bg.clear();
    // Background
    this.bg.fillStyle(0xffffff, 0.9);
    this.bg.fillRoundedRect(x - w / 2, y - h, w, h, BORDER_RADIUS);
    // Border
    this.bg.lineStyle(1, 0x374151, 0.6);
    this.bg.strokeRoundedRect(x - w / 2, y - h, w, h, BORDER_RADIUS);
    // Tail triangle
    this.bg.fillStyle(0xffffff, 0.9);
    this.bg.fillTriangle(x - 4, y, x + 4, y, x, y + 6);
  }

  updatePosition(x: number, y: number): void {
    this.text.setPosition(x, y);
    const bounds = this.text.getBounds();
    const w = Math.max(bounds.width + PADDING * 2, 30);
    const h = bounds.height + PADDING * 2;
    this._drawBubble(x, y, w, h);
  }

  destroy(): void {
    this.bg.destroy();
    this.text.destroy();
  }
}
