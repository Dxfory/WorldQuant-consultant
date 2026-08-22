import assert from "node:assert/strict";
import { assertSafeSize, describePlan, planSlice, spanSizes } from "../web/processor.js";

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

console.log("processor plan tests passed");
