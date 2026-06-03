/**
 * Browser-native asset loader for pixel-agents engine.
 * Replaces Node.js fs + pngjs with fetch() + Image + offscreen canvas.
 */

import {
  CHAR_FRAME_W,
  CHAR_FRAME_H,
  CHAR_FRAMES_PER_ROW,
  CHARACTER_DIRECTIONS,
  CHAR_COUNT,
  FLOOR_TILE_SIZE,
  WALL_PIECE_WIDTH,
  WALL_PIECE_HEIGHT,
  WALL_GRID_COLS,
  WALL_BITMASK_COUNT,
  PNG_ALPHA_THRESHOLD,
} from './shared-constants';
import type { CharacterDirectionSprites } from './shared-types';
import type { SpriteData, OfficeLayout } from './types';
import { flattenManifest, type FurnitureManifest, type FurnitureAsset, type InheritedProps } from './manifestUtils';
import { buildDynamicCatalog, type LoadedAssetData } from './layout/furnitureCatalog';
import { setFloorSprites } from './floorTiles';
import { setWallSprites } from './wallTiles';
import { setCharacterTemplates } from './sprites/spriteData';

// ── PNG → SpriteData conversion ───────────────────────────────

function rgbaToHex(r: number, g: number, b: number, a: number): string {
  if (a < PNG_ALPHA_THRESHOLD) return '';
  const hex = (n: number) => n.toString(16).padStart(2, '0');
  if (a >= 255) return `#${hex(r)}${hex(g)}${hex(b)}`;
  return `#${hex(r)}${hex(g)}${hex(b)}${hex(a)}`;
}

/** Load an image and return its RGBA pixel data */
async function loadImageData(src: string): Promise<{ data: Uint8ClampedArray; width: number; height: number }> {
  const img = new Image();
  img.crossOrigin = 'anonymous';
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error(`Failed to load: ${src}`));
    img.src = src;
  });
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(img, 0, 0);
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return { data: imageData.data, width: canvas.width, height: canvas.height };
}

/** Extract a rectangular region from RGBA data as SpriteData */
function extractSprite(
  data: Uint8ClampedArray,
  imgWidth: number,
  x: number, y: number,
  w: number, h: number,
): SpriteData {
  const sprite: SpriteData = [];
  for (let row = 0; row < h; row++) {
    const line: string[] = [];
    for (let col = 0; col < w; col++) {
      const px = ((y + row) * imgWidth + (x + col)) * 4;
      line.push(rgbaToHex(data[px], data[px + 1], data[px + 2], data[px + 3]));
    }
    sprite.push(line);
  }
  return sprite;
}

// ── Character loading ─────────────────────────────────────────

function decodeCharacterPng(
  data: Uint8ClampedArray,
  width: number,
): CharacterDirectionSprites {
  const result: CharacterDirectionSprites = { down: [], up: [], right: [] };
  const dirs = CHARACTER_DIRECTIONS; // ['down', 'up', 'right']

  for (let d = 0; d < dirs.length; d++) {
    const frames: SpriteData[] = [];
    for (let f = 0; f < CHAR_FRAMES_PER_ROW; f++) {
      frames.push(extractSprite(
        data, width,
        f * CHAR_FRAME_W, d * CHAR_FRAME_H,
        CHAR_FRAME_W, CHAR_FRAME_H,
      ));
    }
    result[dirs[d]] = frames;
  }
  return result;
}

async function loadCharacters(basePath: string): Promise<CharacterDirectionSprites[]> {
  const chars: CharacterDirectionSprites[] = [];
  for (let i = 0; i < CHAR_COUNT; i++) {
    try {
      const { data, width } = await loadImageData(`${basePath}/characters/char_${i}.png`);
      chars.push(decodeCharacterPng(data, width));
    } catch {
      // Skip missing characters
    }
  }
  return chars;
}

// ── Floor loading ─────────────────────────────────────────────

async function loadFloors(basePath: string): Promise<SpriteData[]> {
  const floors: SpriteData[] = [];
  for (let i = 0; i <= 8; i++) {
    try {
      const { data, width } = await loadImageData(`${basePath}/floors/floor_${i}.png`);
      floors.push(extractSprite(data, width, 0, 0, FLOOR_TILE_SIZE, FLOOR_TILE_SIZE));
    } catch {
      // Skip missing floor
    }
  }
  return floors;
}

// ── Wall loading ──────────────────────────────────────────────

function parseWallPng(data: Uint8ClampedArray, width: number): SpriteData[] {
  const sprites: SpriteData[] = [];
  for (let mask = 0; mask < WALL_BITMASK_COUNT; mask++) {
    const col = mask % WALL_GRID_COLS;
    const row = Math.floor(mask / WALL_GRID_COLS);
    sprites.push(extractSprite(
      data, width,
      col * WALL_PIECE_WIDTH, row * WALL_PIECE_HEIGHT,
      WALL_PIECE_WIDTH, WALL_PIECE_HEIGHT,
    ));
  }
  return sprites;
}

async function loadWalls(basePath: string): Promise<SpriteData[][]> {
  const wallSets: SpriteData[][] = [];
  // Currently only 1 wall set (wall_0.png)
  try {
    const { data, width } = await loadImageData(`${basePath}/walls/wall_0.png`);
    wallSets.push(parseWallPng(data, width));
  } catch {
    // No wall set
  }
  return wallSets;
}

// ── Furniture loading ─────────────────────────────────────────

// Known furniture folder names (no directory listing in static hosting)
const FURNITURE_FOLDERS = [
  'BIN', 'BOOKSHELF', 'CACTUS', 'CLOCK', 'COFFEE', 'COFFEE_TABLE',
  'CUSHIONED_BENCH', 'CUSHIONED_CHAIR', 'DESK', 'DOUBLE_BOOKSHELF',
  'HANGING_PLANT', 'LARGE_PAINTING', 'LARGE_PLANT', 'PC', 'PLANT',
  'PLANT_2', 'POT', 'SMALL_PAINTING', 'SMALL_PAINTING_2', 'SMALL_TABLE',
  'SOFA', 'TABLE_FRONT', 'WHITEBOARD', 'WOODEN_BENCH', 'WOODEN_CHAIR',
];

async function loadFurniture(basePath: string): Promise<{
  assets: FurnitureAsset[];
  sprites: Map<string, SpriteData>;
}> {
  const allAssets: FurnitureAsset[] = [];
  const sprites = new Map<string, SpriteData>();

  for (const folder of FURNITURE_FOLDERS) {
    try {
      const manifestUrl = `${basePath}/furniture/${folder}/manifest.json`;
      const res = await fetch(manifestUrl);
      if (!res.ok) continue;
      const manifest: FurnitureManifest = await res.json();

      // Flatten manifest into individual assets
      const inherited: InheritedProps = {
        groupId: manifest.id,
        name: manifest.name,
        category: manifest.category,
        canPlaceOnWalls: manifest.canPlaceOnWalls,
        canPlaceOnSurfaces: manifest.canPlaceOnSurfaces ?? false,
        backgroundTiles: manifest.backgroundTiles ?? 0,
      };

      let assets: FurnitureAsset[];
      if (manifest.type === 'asset') {
        // Single asset manifest
        assets = [{
          id: manifest.id,
          name: manifest.name,
          label: manifest.name,
          category: manifest.category,
          file: manifest.file ?? `${manifest.id}.png`,
          width: manifest.width ?? 16,
          height: manifest.height ?? 16,
          footprintW: manifest.footprintW ?? 1,
          footprintH: manifest.footprintH ?? 1,
          isDesk: manifest.category === 'desks',
          canPlaceOnWalls: manifest.canPlaceOnWalls,
          canPlaceOnSurfaces: manifest.canPlaceOnSurfaces ?? false,
          backgroundTiles: manifest.backgroundTiles ?? 0,
        }];
      } else {
        // Group manifest — flatten recursively
        assets = flattenManifest(manifest as any, inherited);
      }

      allAssets.push(...assets);

      // Load PNG sprites for each asset
      for (const asset of assets) {
        const pngUrl = `${basePath}/furniture/${folder}/${asset.file ?? asset.id + '.png'}`;
        try {
          const { data, width } = await loadImageData(pngUrl);
          sprites.set(asset.id, extractSprite(data, width, 0, 0, asset.width, asset.height));
        } catch {
          // Skip missing sprite
        }
      }
    } catch {
      // Skip broken manifests
    }
  }

  return { assets: allAssets, sprites };
}

// ── Default layout ────────────────────────────────────────────

async function loadDefaultLayout(basePath: string): Promise<OfficeLayout | null> {
  try {
    const res = await fetch(`${basePath}/default-layout-1.json`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ── Main loader ───────────────────────────────────────────────

export interface LoadedAssets {
  characters: CharacterDirectionSprites[];
  floors: SpriteData[];
  wallSets: SpriteData[][];
  furnitureAssets: FurnitureAsset[];
  furnitureSprites: Map<string, SpriteData>;
  defaultLayout: OfficeLayout | null;
}

/**
 * Load all pixel-agents assets from the given base path.
 * Registers sprites globally in the engine subsystems.
 */
export async function loadAllAssets(basePath: string): Promise<LoadedAssets> {
  // Load all asset types in parallel
  const [characters, floors, wallSets, furniture, defaultLayout] = await Promise.all([
    loadCharacters(basePath),
    loadFloors(basePath),
    loadWalls(basePath),
    loadFurniture(basePath),
    loadDefaultLayout(basePath),
  ]);

  // Register in engine subsystems
  setCharacterTemplates(characters);
  setFloorSprites(floors);
  setWallSprites(wallSets);

  // Build furniture catalog — convert to LoadedAssetData format
  const catalogData: LoadedAssetData = {
    catalog: furniture.assets.map(a => ({
      id: a.id,
      label: a.label,
      category: a.category,
      width: a.width,
      height: a.height,
      footprintW: a.footprintW,
      footprintH: a.footprintH,
      isDesk: a.isDesk,
      groupId: a.groupId,
      orientation: a.orientation,
      state: a.state,
      canPlaceOnSurfaces: a.canPlaceOnSurfaces,
      backgroundTiles: a.backgroundTiles,
      canPlaceOnWalls: a.canPlaceOnWalls,
      mirrorSide: a.mirrorSide,
      rotationScheme: a.rotationScheme,
      animationGroup: a.animationGroup,
      frame: a.frame,
    })),
    sprites: Object.fromEntries(furniture.sprites),
  };
  buildDynamicCatalog(catalogData);

  return {
    characters,
    floors,
    wallSets,
    furnitureAssets: furniture.assets,
    furnitureSprites: furniture.sprites,
    defaultLayout,
  };
}
