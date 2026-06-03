// ---------------------------------------------------------------------------
// A* Pathfinding — ported from deskrpg GameScene.ts lines 88-154
// ---------------------------------------------------------------------------

interface PathNode {
  x: number;
  y: number;
  g: number;
  h: number;
  f: number;
  parent: PathNode | null;
}

/**
 * A* pathfinding on a tile grid.
 * Returns an array of tile coordinates from start to end, or null if no path.
 */
export function findPath(
  startTileX: number,
  startTileY: number,
  endTileX: number,
  endTileY: number,
  isWalkable: (tx: number, ty: number) => boolean,
): { x: number; y: number }[] | null {
  // Allow destination itself even if marked unwalkable (agent may be
  // pathfinding to their own desk tile which is blocked)
  if (!isWalkable(startTileX, startTileY)) return null;

  const open: PathNode[] = [];
  const closed = new Set<string>();

  const start: PathNode = {
    x: startTileX, y: startTileY,
    g: 0, h: 0, f: 0, parent: null,
  };
  start.h = Math.abs(endTileX - startTileX) + Math.abs(endTileY - startTileY);
  start.f = start.h;
  open.push(start);

  while (open.length > 0) {
    open.sort((a, b) => a.f - b.f);
    const current = open.shift()!;
    const key = `${current.x},${current.y}`;

    if (current.x === endTileX && current.y === endTileY) {
      // Reconstruct path
      const path: { x: number; y: number }[] = [];
      let node: PathNode | null = current;
      while (node) {
        path.unshift({ x: node.x, y: node.y });
        node = node.parent;
      }
      return path;
    }

    closed.add(key);

    // 4-directional neighbors
    for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
      const nx = current.x + dx;
      const ny = current.y + dy;
      const nkey = `${nx},${ny}`;

      if (closed.has(nkey)) continue;

      // Allow walking to the exact destination even if it's blocked
      const isEnd = (nx === endTileX && ny === endTileY);
      if (!isEnd && !isWalkable(nx, ny)) continue;

      const g = current.g + 1;
      const h = Math.abs(endTileX - nx) + Math.abs(endTileY - ny);
      const f = g + h;

      const existing = open.find(n => n.x === nx && n.y === ny);
      if (existing) {
        if (g < existing.g) {
          existing.g = g;
          existing.f = f;
          existing.parent = current;
        }
      } else {
        open.push({ x: nx, y: ny, g, h, f, parent: current });
      }
    }
  }

  return null; // No path found
}
