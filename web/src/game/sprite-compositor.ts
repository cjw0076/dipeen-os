// ---------------------------------------------------------------------------
// Sprite Compositor — composites LPC layers for role-based character presets
// Reference: deskrpg-master/src/lib/sprite-compositor.ts
// ---------------------------------------------------------------------------

export const FRAME_W = 64;
export const FRAME_H = 64;
export const COLS = 9;
export const ROWS = 4;
export const SHEET_W = 576; // 9 * 64
export const SHEET_H = 256; // 4 * 64

// Direction row indices (walk-only sheets)
// Row 0 = up, Row 1 = left, Row 2 = down, Row 3 = right

/**
 * Role-based character presets.
 * Each array is ordered by zPos (bottom layer first).
 * Paths are relative to /assets/spritesheets/.
 */
export const ROLE_PRESETS: Record<string, string[]> = {
  PM: [
    "/assets/spritesheets/body/bodies/female/walk/light.png",
    "/assets/spritesheets/head/human/female/walk/light.png",
    "/assets/spritesheets/eyes/default/walk/brown.png",
    "/assets/spritesheets/legs/cuffed/male/walk/charcoal.png",
    "/assets/spritesheets/torso/clothes/blouse_longsleeve/female/walk/navy.png",
    "/assets/spritesheets/hair/bob/adult/walk/gold.png",
  ],
  FE: [
    "/assets/spritesheets/body/bodies/male/walk/light.png",
    "/assets/spritesheets/head/human/male/walk/light.png",
    "/assets/spritesheets/eyes/default/walk/brown.png",
    "/assets/spritesheets/legs/cuffed/male/walk/blue.png",
    "/assets/spritesheets/torso/clothes/longsleeve/laced/male/walk/blue.png",
    "/assets/spritesheets/hair/bangsshort/adult/walk/black.png",
  ],
  BE: [
    "/assets/spritesheets/body/bodies/male/walk/light.png",
    "/assets/spritesheets/head/human/male/walk/light.png",
    "/assets/spritesheets/eyes/default/walk/brown.png",
    "/assets/spritesheets/legs/cuffed/male/walk/charcoal.png",
    "/assets/spritesheets/torso/clothes/longsleeve/laced/male/walk/forest.png",
    "/assets/spritesheets/hair/buzzcut/adult/walk/black.png",
  ],
  QA: [
    "/assets/spritesheets/body/bodies/female/walk/light.png",
    "/assets/spritesheets/head/human/female/walk/light.png",
    "/assets/spritesheets/eyes/default/walk/brown.png",
    "/assets/spritesheets/legs/cuffed/male/walk/charcoal.png",
    "/assets/spritesheets/torso/clothes/blouse_longsleeve/female/walk/purple.png",
    "/assets/spritesheets/hair/ponytail/adult/bg/walk/black.png",
  ],
};

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load: ${src}`));
    img.src = src;
  });
}

/**
 * Composites all layers for a role preset onto a canvas and returns a dataURL.
 * Uses Promise.allSettled so missing layers degrade gracefully.
 */
export async function compositePreset(role: string): Promise<string> {
  const canvas = document.createElement("canvas");
  canvas.width = SHEET_W;
  canvas.height = SHEET_H;

  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Cannot get 2d context");

  ctx.clearRect(0, 0, SHEET_W, SHEET_H);
  ctx.imageSmoothingEnabled = false;

  const paths = ROLE_PRESETS[role.toUpperCase()] ?? ROLE_PRESETS.FE;
  const results = await Promise.allSettled(paths.map(loadImage));

  for (const r of results) {
    if (r.status === "fulfilled") {
      ctx.drawImage(r.value, 0, 0, SHEET_W, SHEET_H);
    }
  }

  return canvas.toDataURL();
}
