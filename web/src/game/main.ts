import * as Phaser from "phaser";
import { BootScene } from "./scenes/BootScene";
import { GameScene } from "./scenes/GameScene";

export function createGame(containerId: string): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    parent: containerId,
    width: "100%",
    height: "100%",
    backgroundColor: "#1E1E2E",
    scene: [BootScene, GameScene],
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
    render: {
      antialias: false,
      pixelArt: true,
    },
  });
}
