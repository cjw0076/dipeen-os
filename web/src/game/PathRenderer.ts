// web/src/game/PathRenderer.ts
import * as Phaser from "phaser";

const DOT_INTERVAL = 10;   // 점 간격 (px)
const DOT_RADIUS   = 1.8;  // 점 크기
const DOT_COLOR    = 0x6366f1;
const DOT_ALPHA    = 0.75;

export class PathRenderer {
  private gfx: Phaser.GameObjects.Graphics;
  private destInner: Phaser.GameObjects.Arc;
  private destOuter: Phaser.GameObjects.Arc;
  private pathPoints: { x: number; y: number }[] = [];
  private dashOffset = 0;
  private totalLength = 0;
  private outerTween: Phaser.Tweens.Tween | null = null;

  constructor(private scene: Phaser.Scene) {
    this.gfx = scene.add.graphics().setDepth(5);
    this.destInner = scene.add.arc(0, 0, 5, 0, 360, false, 0x6366f1, 1)
      .setDepth(6).setVisible(false);
    this.destOuter = scene.add.arc(0, 0, 5, 0, 360, false, 0x6366f1, 0.4)
      .setDepth(6).setVisible(false);
  }

  showPath(worldPoints: { x: number; y: number }[]): void {
    this.clearPath();
    if (worldPoints.length < 2) return;

    this.pathPoints = worldPoints;
    this.totalLength = this._computeTotalLength(worldPoints);
    this.dashOffset = 0;

    const dest = worldPoints[worldPoints.length - 1];
    this.destInner.setPosition(dest.x, dest.y).setVisible(true);
    this.destOuter.setPosition(dest.x, dest.y).setVisible(true);
    this.outerTween = this.scene.tweens.add({
      targets: this.destOuter,
      scaleX: 3.5, scaleY: 3.5, alpha: 0,
      duration: 900, repeat: -1,
      onRepeat: () => { this.destOuter.setScale(1).setAlpha(0.4); },
    });
  }

  clearPath(): void {
    this.pathPoints = [];
    this.totalLength = 0;
    this.gfx.clear();
    this.destInner.setVisible(false);
    this.destOuter.setVisible(false).setScale(1).setAlpha(0.4);
    if (this.outerTween) {
      this.scene.tweens.remove(this.outerTween);
      this.outerTween = null;
    }
  }

  update(delta: number): void {
    if (this.pathPoints.length < 2) return;
    this.dashOffset = (this.dashOffset + delta * 0.05) % DOT_INTERVAL;
    this.gfx.clear();
    this.gfx.fillStyle(DOT_COLOR, DOT_ALPHA);

    let distAccum = 0;
    let nextDot = DOT_INTERVAL - this.dashOffset;

    for (let i = 1; i < this.pathPoints.length; i++) {
      const p0 = this.pathPoints[i - 1];
      const p1 = this.pathPoints[i];
      const segLen = Math.hypot(p1.x - p0.x, p1.y - p0.y);
      if (segLen === 0) continue;

      while (nextDot <= distAccum + segLen) {
        const t = (nextDot - distAccum) / segLen;
        const px = p0.x + (p1.x - p0.x) * t;
        const py = p0.y + (p1.y - p0.y) * t;
        this.gfx.fillCircle(px, py, DOT_RADIUS);
        nextDot += DOT_INTERVAL;
      }
      distAccum += segLen;
    }
  }

  private _computeTotalLength(pts: { x: number; y: number }[]): number {
    let len = 0;
    for (let i = 1; i < pts.length; i++) {
      len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    }
    return len;
  }

  destroy(): void {
    if (this.outerTween) {
      this.scene.tweens.remove(this.outerTween);
      this.outerTween = null;
    }
    this.gfx.destroy();
    this.destInner.destroy();
    this.destOuter.destroy();
  }
}
