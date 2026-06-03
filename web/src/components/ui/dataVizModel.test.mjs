import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBarSeries,
  buildDonutSegments,
  buildSparklinePath,
} from "./dataVizModel.js";

test("buildSparklinePath maps token values into an SVG path", () => {
  const result = buildSparklinePath([10, 20, 15], {
    width: 120,
    height: 60,
    padding: 10,
  });

  assert.equal(result.path, "M10 50 L60 10 L110 30");
  assert.deepEqual(result.points, [
    { value: 10, x: 10, y: 50 },
    { value: 20, x: 60, y: 10 },
    { value: 15, x: 110, y: 30 },
  ]);
});

test("buildSparklinePath keeps a flat series centered", () => {
  const result = buildSparklinePath([7, 7, 7], {
    width: 100,
    height: 40,
    padding: 8,
  });

  assert.equal(result.path, "M8 20 L50 20 L92 20");
});

test("buildBarSeries returns proportional bar widths with stable labels", () => {
  const bars = buildBarSeries([
    { label: "FE", value: 1200 },
    { label: "BE", value: 600 },
    { label: "QA", value: 0 },
  ]);

  assert.deepEqual(bars, [
    { label: "FE", value: 1200, percent: 100 },
    { label: "BE", value: 600, percent: 50 },
    { label: "QA", value: 0, percent: 0 },
  ]);
});

test("buildDonutSegments converts values into stroke dash segments", () => {
  const segments = buildDonutSegments([
    { label: "FE", value: 30, color: "#60A5FA" },
    { label: "BE", value: 10, color: "#34D399" },
  ], {
    radius: 20,
    gap: 2,
  });

  assert.equal(segments.length, 2);
  assert.deepEqual(segments[0], {
    label: "FE",
    value: 30,
    color: "#60A5FA",
    dashArray: "92.25 125.66",
    dashOffset: "0.00",
  });
  assert.deepEqual(segments[1], {
    label: "BE",
    value: 10,
    color: "#34D399",
    dashArray: "29.42 125.66",
    dashOffset: "-94.25",
  });
});
