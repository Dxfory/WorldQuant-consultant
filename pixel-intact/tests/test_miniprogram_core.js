const assert = require("node:assert/strict");
const {
  planSlice,
  spanSizes,
  parseTileName,
  describePlan,
  formatPixels,
  overlayLines,
  sizeAfterScaleExceeds,
  tilesAfterScaleExceed,
  suggestSafeGrid,
  planWithScaledTiles,
} = require("../miniprogram/utils/core");

const widths = spanSizes(101, 3);
assert.deepEqual(widths, [34, 34, 33]);

const plan = planSlice(101, 77, { cols: 3, rows: 2 });
assert.equal(plan.complete, true);
assert.equal(plan.discardedPixels, 0);
assert.equal(plan.remainderDistributed, true);
assert.match(describePlan(plan), /丢弃 0/);

assert.deepEqual(parseTileName("r00_c01.png"), { row: 0, col: 1 });
assert.equal(parseTileName("photo.png"), null);

assert.equal(formatPixels(7777), "7777");
assert.match(formatPixels(130142460), /亿/);

const lines = overlayLines(plan);
assert.equal(lines.vLines.length, 2);
assert.equal(lines.hLines.length, 1);

assert.equal(sizeAfterScaleExceeds(9505, 13692, 2), true);
assert.equal(sizeAfterScaleExceeds(9505, 13692, 1), true);

const poster = planSlice(9505, 13692, { cols: 3, rows: 2 });
assert.equal(poster.complete, true);
assert.equal(tilesAfterScaleExceed(poster, 1), true);

const safe = suggestSafeGrid(9505, 13692, 1);
assert.equal(tilesAfterScaleExceed(safe.plan, 1), false);
assert.ok(safe.cols * safe.rows >= 12);

const scaledSafe = suggestSafeGrid(9505, 13692, 2);
assert.equal(tilesAfterScaleExceed(scaledSafe.plan, 2), false);
assert.ok(scaledSafe.cols * scaledSafe.rows >= 12);

const estimated = planWithScaledTiles(safe.plan, 2);
assert.equal(estimated.complete, true);
assert.equal(estimated.discardedPixels, 0);

console.log("miniprogram core tests passed");
