const assert = require("node:assert/strict");
const { planSlice, spanSizes, parseTileName, describePlan } = require("../miniprogram/utils/core");

const widths = spanSizes(101, 3);
assert.deepEqual(widths, [34, 34, 33]);

const plan = planSlice(101, 77, { cols: 3, rows: 2 });
assert.equal(plan.complete, true);
assert.equal(plan.discardedPixels, 0);
assert.equal(plan.remainderDistributed, true);
assert.match(describePlan(plan), /丢弃 0/);

assert.deepEqual(parseTileName("r00_c01.png"), { row: 0, col: 1 });
assert.equal(parseTileName("photo.png"), null);

console.log("miniprogram core tests passed");
