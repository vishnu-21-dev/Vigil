// Run with: node tests/js/failsafe_state.test.js
// Loads the real frontend/js/api.js in a vm with stubbed browser globals,
// then exercises the global failsafeState() function.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "..", "frontend", "js", "api.js"), "utf8");
const context = vm.createContext({ window: { location: { port: "8000" } }, fetch: () => {} });
vm.runInContext(source, context);
const failsafeState = context.failsafeState;
assert.equal(typeof failsafeState, "function", "api.js must define failsafeState");

const alert = (extra = {}) => ({ id: "a1", device_id: "d1", acknowledged: true, ...extra });
const req = (status, flagged_at, extra = {}) => ({ id: `r-${status}-${flagged_at}`, device_id: "d1", status, flagged_at, ...extra });

const cases = [
  ["unacknowledged alert -> countdown",
    alert({ acknowledged: false }), [req("ai_contained", "2026-10-05T10:00:00Z")], "countdown"],
  ["acknowledged, newest request ai_contained -> ai_contained",
    alert(), [req("ai_contained", "2026-10-05T10:00:00Z")], "ai_contained"],
  ["acknowledged, newest request approved -> handled",
    alert(), [req("approved", "2026-10-05T10:00:00Z")], "handled"],
  ["acknowledged, newest request dismissed -> handled",
    alert(), [req("dismissed", "2026-10-05T10:00:00Z")], "handled"],
  ["older ai_contained + newer pending -> handled",
    alert(), [req("ai_contained", "2026-10-05T09:00:00Z"), req("pending", "2026-10-05T10:00:00Z")], "handled"],
  ["acknowledged, no requests -> handled",
    alert(), [], "handled"],
  ["requests for other devices are ignored",
    alert(), [req("ai_contained", "2026-10-05T10:00:00Z", { device_id: "other" })], "handled"],
  // 11:30+02:00 is 09:30Z, i.e. OLDER than 10:00Z even though it sorts later as a string.
  ["mixed formats: offset time is older than Z time -> ai_contained",
    alert(), [req("ai_contained", "2026-10-05T10:00:00.123456Z"), req("approved", "2026-10-05T11:30:00+02:00")], "ai_contained"],
  ["mixed formats: +00:00 microseconds newer than Z seconds -> handled",
    alert(), [req("ai_contained", "2026-10-05T10:00:00Z"), req("approved", "2026-10-05T10:00:00.500000+00:00")], "handled"],
  ["input order does not matter",
    alert(), [req("pending", "2026-10-05T10:00:00Z"), req("ai_contained", "2026-10-05T11:00:00Z")], "ai_contained"],
];

let failed = 0;
for (const [name, a, requests, expected] of cases) {
  try {
    assert.equal(failsafeState(a, requests), expected);
    console.log(`ok   - ${name}`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL - ${name}\n       expected ${expected}, got ${failsafeState(a, requests)}`);
  }
}
console.log(`\n${cases.length - failed}/${cases.length} passed`);
process.exit(failed ? 1 : 0);
