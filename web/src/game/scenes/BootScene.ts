import * as Phaser from "phaser";
import { compositePreset, FRAME_W, FRAME_H } from "../sprite-compositor";

// 16 office tiles, each 32×32, laid out in a single row (512×32)
const TILE = 32;

/**
 * Draw a single 32×32 tile at the given pixel offset.
 * Exported so GameScene can render detailed tiles directly on the map.
 */
export function drawTile(g: Phaser.GameObjects.Graphics, index: number, x: number = index * TILE, y: number = 0): void {

  switch (index) {
    case 0: // empty — transparent
      break;

    case 1: // floor — dark charcoal
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.lineStyle(1, 0x333130, 0.4);
      g.strokeRect(x, 0, TILE, TILE);
      g.fillStyle(0x302e2c, 0.5);
      g.fillRect(x + 6, 6, 2, 2);
      g.fillRect(x + 18, 14, 2, 2);
      g.fillRect(x + 10, 24, 2, 2);
      g.fillRect(x + 26, 8, 2, 2);
      break;

    case 2: // wall
      g.fillStyle(0x4a4a5e);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x6a6a7e);
      g.fillRect(x, 0, TILE, 4);
      g.lineStyle(1, 0x3a3a4e, 0.4);
      g.lineBetween(x, 16, x + TILE, 16);
      g.lineBetween(x + 16, 4, x + 16, 16);
      g.lineBetween(x + 8, 16, x + 8, TILE);
      g.lineBetween(x + 24, 16, x + 24, TILE);
      g.lineStyle(1, 0x5a5a6e, 0.5);
      g.strokeRect(x, 0, TILE, TILE);
      break;

    case 3: // desk
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x6b4226);
      g.fillRect(x + 2, 4, 28, 20);
      g.fillStyle(0x523218);
      g.fillRect(x + 2, 22, 28, 4);
      g.lineStyle(1, 0x7a5236, 0.4);
      g.lineBetween(x + 4, 8, x + 28, 8);
      g.lineBetween(x + 6, 14, x + 26, 14);
      break;

    case 4: // chair
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x4060b0);
      g.fillRect(x + 8, 10, 16, 14);
      g.fillStyle(0x3050a0);
      g.fillRect(x + 8, 6, 16, 6);
      g.fillStyle(0x333333);
      g.fillRect(x + 10, 24, 3, 4);
      g.fillRect(x + 19, 24, 3, 4);
      break;

    case 5: // computer
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x222233);
      g.fillRect(x + 6, 4, 20, 16);
      g.fillStyle(0x1a3a2a);
      g.fillRect(x + 8, 6, 16, 12);
      g.fillStyle(0x44ff44);
      g.fillCircle(x + 16, 12, 2);
      g.fillStyle(0x444444);
      g.fillRect(x + 13, 20, 6, 4);
      g.fillRect(x + 10, 24, 12, 2);
      break;

    case 6: // plant
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x8b4513);
      g.fillRect(x + 10, 20, 12, 10);
      g.fillStyle(0x6b3210);
      g.fillRect(x + 8, 18, 16, 4);
      g.fillStyle(0x2d8b2d);
      g.fillCircle(x + 16, 12, 8);
      g.fillStyle(0x3aa53a);
      g.fillCircle(x + 13, 10, 5);
      g.fillCircle(x + 19, 10, 5);
      g.fillCircle(x + 16, 7, 4);
      break;

    case 7: // door
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x6b5a3a);
      g.fillRect(x + 2, 0, 28, TILE);
      g.fillStyle(0x8b7a5a);
      g.fillRect(x + 4, 2, 24, 28);
      g.fillStyle(0xd4af37);
      g.fillCircle(x + 23, 18, 2);
      g.lineStyle(1, 0x7a6a4a, 0.5);
      g.strokeRect(x + 6, 4, 9, 12);
      g.strokeRect(x + 17, 4, 9, 12);
      break;

    case 8: // meeting table
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x4a3020);
      g.fillRect(x + 2, 2, 28, 28);
      g.fillStyle(0x5a4030);
      g.fillRect(x + 4, 4, 24, 24);
      g.fillStyle(0x6a5040);
      g.fillRect(x + 6, 6, 10, 6);
      break;

    case 9: // coffee area
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x5a4a3a);
      g.fillRect(x + 2, 4, 28, 24);
      g.fillStyle(0x333333);
      g.fillRect(x + 6, 6, 12, 16);
      g.fillStyle(0xff3333);
      g.fillCircle(x + 12, 10, 2);
      g.fillStyle(0xffffff);
      g.fillRect(x + 20, 14, 6, 8);
      g.fillStyle(0x8b6914);
      g.fillRect(x + 21, 15, 4, 6);
      break;

    case 10: // water cooler
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0xcccccc);
      g.fillRect(x + 8, 16, 16, 14);
      g.fillStyle(0x88bbff);
      g.fillRect(x + 10, 2, 12, 16);
      g.fillStyle(0x6699dd);
      g.fillRect(x + 10, 6, 12, 12);
      g.fillStyle(0x4477bb);
      g.fillRect(x + 12, 0, 8, 4);
      g.fillStyle(0x888888);
      g.fillRect(x + 22, 18, 4, 3);
      break;

    case 11: // bookshelf
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x5a3a1a);
      g.fillRect(x + 2, 2, 28, 28);
      g.fillStyle(0x6b4a2a);
      g.fillRect(x + 2, 10, 28, 2);
      g.fillRect(x + 2, 20, 28, 2);
      {
        const bookColors = [0xcc3333, 0x3366cc, 0x33aa33, 0xccaa33, 0x9933cc, 0xcc6633];
        for (let i = 0; i < 6; i++) {
          g.fillStyle(bookColors[i]);
          g.fillRect(x + 4 + i * 4, 3, 3, 7);
          g.fillRect(x + 4 + i * 4, 13, 3, 7);
          g.fillRect(x + 4 + i * 4, 23, 3, 5);
        }
      }
      break;

    case 12: // meeting room carpet
      g.fillStyle(0x252340);
      g.fillRect(x, 0, TILE, TILE);
      g.lineStyle(1, 0x302e50, 0.4);
      g.strokeRect(x, 0, TILE, TILE);
      g.fillStyle(0x3a3860, 0.4);
      g.fillRect(x + 4, 4, 3, 3);
      g.fillRect(x + 20, 12, 3, 3);
      g.fillRect(x + 12, 22, 3, 3);
      break;

    case 13: // whiteboard
      g.fillStyle(0x4a4a5e);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0xcccccc);
      g.fillRect(x + 3, 4, 26, 20);
      g.fillStyle(0xf0f0f0);
      g.fillRect(x + 5, 6, 22, 16);
      g.lineStyle(1, 0x3366cc, 0.5);
      g.lineBetween(x + 8, 10, x + 22, 10);
      g.lineBetween(x + 8, 14, x + 20, 14);
      g.lineBetween(x + 8, 18, x + 18, 18);
      g.fillStyle(0xaaaaaa);
      g.fillRect(x + 6, 24, 20, 3);
      break;

    case 14: // reception desk
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x8b6b3a);
      g.fillRect(x + 2, 6, 28, 20);
      g.fillStyle(0x9b7b4a);
      g.fillRect(x + 2, 4, 28, 6);
      g.fillStyle(0x7b5b2a);
      g.fillRect(x + 4, 14, 24, 10);
      g.fillStyle(0xd4af37);
      g.fillRect(x + 12, 16, 8, 4);
      break;

    case 15: // cubicle wall
      g.fillStyle(0x2a2826);
      g.fillRect(x, 0, TILE, TILE);
      g.fillStyle(0x888899);
      g.fillRect(x + 12, 0, 8, TILE);
      g.fillStyle(0x777788);
      g.fillRect(x + 12, 0, 2, TILE);
      g.fillRect(x + 18, 0, 2, TILE);
      g.fillStyle(0x9999aa, 0.3);
      g.fillRect(x + 14, 4, 4, 4);
      g.fillRect(x + 14, 12, 4, 4);
      g.fillRect(x + 14, 20, 4, 4);
      break;
  }
}

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: "BootScene" });
  }

  create(): void {
    // Generate 16 office tile textures — both as strip and as individual textures
    const g = this.add.graphics();
    for (let i = 0; i < 16; i++) {
      drawTile(g, i);
    }
    g.generateTexture("office-tiles", 16 * TILE, TILE);
    g.destroy();

    // Generate individual tile textures for map rendering
    for (let i = 1; i < 16; i++) {
      const tg = this.add.graphics();
      drawTile(tg, i, 0, 0);
      tg.generateTexture(`tile-${i}`, TILE, TILE);
      tg.destroy();
    }

    // Generate fallback character texture (colored square)
    this._generateFallbackChar();

    // Composite role preset spritesheets, then start GameScene
    this._compositeRolePresets().then(() => {
      this.scene.start("GameScene");
    });
  }

  private _generateFallbackChar(): void {
    const g = this.add.graphics();
    g.fillStyle(0x6366f1);
    g.fillRect(0, 0, 64, 64);
    // Simple body shape
    g.fillStyle(0xfbbf24);
    g.fillCircle(32, 18, 10); // head
    g.fillStyle(0x6366f1);
    g.fillRect(22, 28, 20, 24); // body
    g.fillStyle(0x374151);
    g.fillRect(24, 52, 7, 10); // left leg
    g.fillRect(33, 52, 7, 10); // right leg
    g.generateTexture("fallback-char", 64, 64);
    g.destroy();
  }

  private async _compositeRolePresets(): Promise<void> {
    const roles = ["PM", "FE", "BE", "QA"];
    for (const role of roles) {
      try {
        const dataUrl = await compositePreset(role);
        const img = new Image();
        await new Promise<void>((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error(`Failed to load preset: ${role}`));
          img.src = dataUrl;
        });
        this.textures.addSpriteSheet(`preset-${role}`, img, {
          frameWidth: FRAME_W,
          frameHeight: FRAME_H,
        });
      } catch (err) {
        console.warn(`[BootScene] Failed to composite preset for ${role}:`, err);
      }
    }
  }
}
