import assert from "node:assert/strict";
import {
  assertSafeSize,
  describePlan,
  exceedsLimit,
  planFromEnhancedTiles,
  planSlice,
  planWithScaledTiles,
  sizeAfterScaleExceeds,
  spanSizes,
  suggestSafeGrid,
  targetSize,
  tilesAfterScaleExceed,
} from "../web/processor.js";

const widths = spanSizes(101, 3);
assert.deepEqual(widths, [34, 34, 33]);
assert.equal(widths.reduce((sum, value) => sum + value, 0), 101);

const plan = planSlice(101, 77, { cols: 3, rows: 2 });
assert.equal(plan.complete, true);
assert.equal(plan.discardedPixels, 0);
assert.equal(plan.exportedPixels, 101 * 77);
assert.equal(plan.remainderDistributed, true);
assert.deepEqual(
  plan.tiles.filter((tile) => tile.row === 0).map((tile) => tile.width),
  [34, 34, 33],
);

const sized = planSlice(50, 41, { tileWidth: 20, tileHeight: 20 });
assert.equal(sized.cols, 3);
assert.equal(sized.rows, 3);
assert.equal(sized.tiles.at(-1).width, 10);
assert.equal(sized.tiles.at(-1).height, 1);
assert.equal(sized.complete, true);
assert.match(describePlan(plan), /丢弃 0/);

assert.throws(() => assertSafeSize(20000, 20000), /太大/);

assert.deepEqual(targetSize(9505, 13692, 2), { width: 19010, height: 27384 });
assert.equal(exceedsLimit(19010, 27384), true);
assert.equal(exceedsLimit(6336, 13692), false);
assert.equal(sizeAfterScaleExceeds(9505, 13692, 2), true);

const poster = planSlice(9505, 13692, { cols: 3, rows: 2 });
assert.equal(poster.complete, true);
assert.equal(poster.discardedPixels, 0);
assert.equal(tilesAfterScaleExceed(poster, 2), false);
assert.equal(tilesAfterScaleExceed(planSlice(9505, 13692, { cols: 2, rows: 2 }), 2), true);

const estimated = planWithScaledTiles(poster, 2);
assert.equal(estimated.complete, true);
assert.equal(estimated.discardedPixels, 0);
assert.equal(estimated.tiles.length, 6);

const suggested = suggestSafeGrid(9505, 13692, 2);
assert.ok(suggested.cols * suggested.rows >= 6);
assert.equal(tilesAfterScaleExceed(suggested.plan, 2), false);

const rebuilt = planFromEnhancedTiles(
  poster,
  poster.tiles.map((tile) => ({
    width: Math.round(tile.width * 2),
    height: Math.round(tile.height * 2),
  })),
);
assert.equal(rebuilt.complete, true);
assert.equal(rebuilt.tiles.length, 6);
assert.equal(rebuilt.tiles[0].left, 0);
assert.equal(rebuilt.tiles[1].left, rebuilt.tiles[0].width);

console.log("processor plan tests passed");
