import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  explainFacility,
  getFacilities,
  getFacility,
  getTrophy,
  postSchedule,
} from "../lib/api.ts";
import {
  isScored,
  LABEL_COLOR,
  NEUTRAL_COLOR,
  RATING_COLOR,
  ratingColor,
  UNRATED_COLOR,
  scoreHeadline,
  scoreSummary,
  UNSCORED_COPY,
} from "../lib/format.ts";
import { clampCapacity, overdueCount, visibleProbabilities } from "../lib/regulator.ts";
import { citationSignal, riskScore, timeSignal } from "../lib/risk.ts";
import { bucketOf, nextMonthOverdue, summarizeBacklog, WEEKS_PER_MONTH } from "../lib/backlog.ts";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function walk(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) files.push(...walk(full));
    else if (/\.(tsx|ts|css)$/.test(entry)) files.push(full);
  }
  return files;
}

describe("package scripts", () => {
  test("dev listens on port 3000 and npm test exists", () => {
    const pkg = JSON.parse(readFileSync(path.join(webRoot, "package.json"), "utf8")) as {
      scripts: { dev: string; test: string };
    };
    assert.match(pkg.scripts.dev, /next dev/);
    assert.match(pkg.scripts.dev, /--port 3000/);
    assert.ok(pkg.scripts.test.length > 0);
  });
});

describe("fixture fallback", () => {
  const previousBase = process.env.NEXT_PUBLIC_API_BASE;
  const previousTimeout = process.env.API_TIMEOUT_MS;

  before(() => {
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:9/api";
    process.env.API_TIMEOUT_MS = "400";
  });

  after(() => {
    if (previousBase === undefined) delete process.env.NEXT_PUBLIC_API_BASE;
    else process.env.NEXT_PUBLIC_API_BASE = previousBase;
    if (previousTimeout === undefined) delete process.env.API_TIMEOUT_MS;
    else process.env.API_TIMEOUT_MS = previousTimeout;
  });

  test("search and facility detail match the contract fixtures", async () => {
    const savannah = await getFacilities("Savannah");
    assert.equal(savannah.length, 2);
    assert.ok(savannah.every((row) => row.city === "Savannah"));
    for (const row of savannah) {
      assert.equal(typeof row.ccn, "string");
      assert.equal(row.ccn.length, 6);
      assert.equal(typeof row.ci_low, "number");
      assert.equal(typeof row.ci_high, "number");
      assert.ok(row.ci_low !== null && row.ci_high !== null && row.ci_low <= row.ci_high);
      assert.ok(row.label !== null && ["High", "Watch", "Low"].includes(row.label));
    }

    const facility = await getFacility("115999");
    assert.equal(facility.name, "Sample Harbor Health & Rehab");
    assert.equal(typeof facility.n_surveys, "number");
    assert.ok(facility.curve.some((point) => point.d === 0));
    assert.ok(facility.state_curve.length > 0);
    assert.equal(facility.explanation, null);

    const explained = await explainFacility("115999");
    assert.match(explained.text, /survey-responsive staffing/);
    assert.doesNotMatch(explained.text, /gaming/i);

    const trophy = await getTrophy();
    assert.ok(trophy.length >= 1);
    assert.equal(typeof trophy[0].ci_low, "number");
    assert.equal(typeof trophy[0].score_pct, "number");

    const schedule = await postSchedule({ month: "2026-10", capacity: 3 });
    assert.equal(schedule.capacity, 3);
    assert.equal(schedule.selected.length, 3);
    assert.ok(schedule.probs.length >= schedule.selected.length);
    const probSum = schedule.probs.reduce((sum, row) => sum + row.prob, 0);
    assert.ok(Math.abs(probSum - schedule.capacity) < 0.01);
  });
});

describe("regulator header", () => {
  let server: Server;
  let base = "";
  const seen: { method: string; url: string; role: string | undefined; body: string }[] = [];
  const previousBase = process.env.NEXT_PUBLIC_API_BASE;

  before(async () => {
    server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on("data", (chunk) => chunks.push(chunk as Buffer));
      req.on("end", () => {
        const url = req.url ?? "";
        seen.push({
          method: req.method ?? "",
          url,
          role: req.headers["x-demo-role"] as string | undefined,
          body: Buffer.concat(chunks).toString("utf8"),
        });
        res.setHeader("Content-Type", "application/json");
        if (url.startsWith("/api/facilities")) {
          res.end("[]");
          return;
        }
        if (url.startsWith("/api/facility/")) {
          res.end(JSON.stringify({ ccn: "115999", explanation: null, curve: [], state_curve: [] }));
          return;
        }
        if (url === "/api/explain") {
          res.end(JSON.stringify({ text: "ok" }));
          return;
        }
        if (url === "/api/schedule") {
          res.end(
            JSON.stringify({
              month: "2026-10",
              capacity: 3,
              selected: [],
              probs: [],
            }),
          );
          return;
        }
        if (url === "/api/trophy") {
          res.end("[]");
          return;
        }
        res.statusCode = 404;
        res.end("{}");
      });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (address === null || typeof address === "string") throw new Error("no port");
    base = `http://127.0.0.1:${address.port}/api`;
    process.env.NEXT_PUBLIC_API_BASE = base;
  });

  after(async () => {
    if (previousBase === undefined) delete process.env.NEXT_PUBLIC_API_BASE;
    else process.env.NEXT_PUBLIC_API_BASE = previousBase;
    await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  });

  test("public routes omit the demo header and regulator routes send it", async () => {
    await getFacilities("Savannah");
    await getFacility("115999");
    await explainFacility("115999");
    await postSchedule({ month: "2026-10", capacity: 3, seed: 1 });
    await getTrophy();

    const byPath = (prefix: string) => seen.find((call) => call.url.startsWith(prefix));
    assert.equal(byPath("/api/facilities")?.role, undefined);
    assert.equal(byPath("/api/facility/")?.role, undefined);
    assert.equal(byPath("/api/explain")?.role, undefined);
    assert.equal(byPath("/api/schedule")?.role, "regulator");
    assert.equal(byPath("/api/trophy")?.role, "regulator");

    const schedule = byPath("/api/schedule");
    assert.equal(schedule?.method, "POST");
    assert.deepEqual(JSON.parse(schedule?.body ?? "{}"), {
      month: "2026-10",
      capacity: 3,
      seed: 1,
    });
  });
});

describe("regulator capacity", () => {
  test("the minimum is the number of legally overdue homes", () => {
    const schedule = { probs: [{ forced: true }, { forced: true }, { forced: false }] };
    assert.equal(overdueCount(schedule), 2);
    assert.equal(overdueCount(null), 0);
    assert.equal(clampCapacity(1, 14), 14);
    assert.equal(clampCapacity(22, 14, 40), 22);
    assert.equal(clampCapacity(99, 14, 40), 40);
    assert.equal(clampCapacity(Number.NaN, 14), 14);
  });
});

describe("regulator lists", () => {
  test("hides zero probabilities", () => {
    const probs = [
      { ccn: "000001", prob: 0, forced: false },
      { ccn: "000002", prob: 0.2, forced: false },
      { ccn: "000003", prob: 0.9, forced: true },
    ];
    assert.deepEqual(
      visibleProbabilities(probs, false).map((row) => row.ccn),
      ["000003", "000002"],
    );
    assert.equal(visibleProbabilities(probs, true).at(-1)?.prob, 0);
  });
});
describe("scores copy", () => {
  test("null scores and labels are not filled in", () => {
    assert.equal(isScored(null, null, null), false);
    assert.equal(scoreHeadline(null, 0, 0, null), null);
    assert.equal(scoreSummary(null, null, null), UNSCORED_COPY);
    assert.equal(ratingColor(1), "#d03b3b");
    assert.equal(ratingColor(4), "#56b870");
    assert.equal(ratingColor(5), "#17693a");
    assert.equal(ratingColor(null), UNRATED_COLOR);
    assert.equal(ratingColor(0), UNRATED_COLOR);
    // A consistency chip color is never a rating color.
    for (const chip of Object.values(LABEL_COLOR)) assert.ok(!Object.values(RATING_COLOR).includes(chip));
  });

  test("the headline names the window through the day before the inspection ended", () => {
    const headline = scoreHeadline(11, 6, 16, 7);
    assert.ok(headline);
    assert.match(headline, /14 days through the day before past inspections ended/);
    assert.match(headline, /11%/);
    assert.match(headline, /range 6–16%/);
    assert.match(headline, /7 inspections/);
    assert.doesNotMatch(headline, /before past inspections,/);
    assert.doesNotMatch(headline, /2 weeks before/);
  });

});

describe("family copy", () => {
  test("user-facing files follow the language rules", () => {
    const files = [...walk(path.join(webRoot, "app")), ...walk(path.join(webRoot, "components"))];
    const text = files.map((file) => readFileSync(file, "utf8")).join("\n");
    assert.doesNotMatch(text, /gaming/i);
    assert.match(text, /survey-responsive staffing/);
    assert.match(text, /PBJ staffing data is self-reported/);
    assert.match(text, /Chen & Dillender \(NBER w34037\)/);
    assert.match(text, /Gandhi, Olenski & Shi \(NBER w34491\)/);

    const family = ["page.tsx", path.join("facility", "[ccn]", "page.tsx")]
      .map((name) => readFileSync(path.join(webRoot, "app", name), "utf8"))
      .join("\n");
    assert.doesNotMatch(family, /p_next_60d|predictability|X-Demo-Role|getPredictability|getBacklog|weeks_since_last/);

    const familySurfaces = [
      path.join(webRoot, "app", "page.tsx"),
      path.join(webRoot, "app", "facility", "[ccn]", "page.tsx"),
      path.join(webRoot, "components", "FacilityMap.tsx"),
      path.join(webRoot, "components", "MapView.tsx"),
      path.join(webRoot, "components", "StaffingChart.tsx"),
    ];
    const surfaceText = familySurfaces.map((file) => readFileSync(file, "utf8")).join("\n");
    assert.doesNotMatch(surfaceText, /p_next_60d|getPredictability|PredictabilityPanel|getBacklog|weeks_since_last|BacklogPanel/);
    assert.match(text, /not enough inspections/);
  });
});

describe("risk score", () => {
  test("matches risk_weights() in models/scheduler.py", () => {
    // 100 × (0.25 + 1 + min(1, 0.1 + 0.4) + 0.25 × 0.5) = 187.5, as in models/test_smoke.py
    assert.ok(Math.abs(riskScore({ residents: 100, scorePercentile: 1, weekendPercentile: 0.5, harm: 1, ij: 2 }) - 187.5) < 1e-9);
    // Missing residents default to 80, missing ranks to 0.5, citations cap at 1.
    assert.ok(Math.abs(riskScore({ ij: 20 }) - 80 * (0.25 + 0.5 + 1 + 0.125)) < 1e-9);
    assert.equal(citationSignal(0, 20), 1);
    // Time: nothing before 12 months, halfway at 13.95, full at the 15.9-month limit.
    assert.equal(timeSignal(11), 0);
    assert.ok(Math.abs(timeSignal(13.95) - 0.5) < 1e-9);
    assert.equal(timeSignal(20), 1);
    assert.ok(Math.abs(riskScore({ residents: 100, scorePercentile: 1, weekendPercentile: 0.5, harm: 1, ij: 2, monthsSinceLast: 15.9 }) - 287.5) < 1e-9);
  });
});

describe("inspection backlog", () => {
  const homes = [
    { ccn: "000001", weeks_since_last: 10, forced: false }, // ~2.3 months
    { ccn: "000002", weeks_since_last: 40, forced: false }, // ~9.2 months
    { ccn: "000003", weeks_since_last: 66, forced: false }, // ~15.2 months, crosses within a month
    { ccn: "000004", weeks_since_last: 75, forced: true },
  ];
  const probs = [
    { ccn: "000001", prob: 0.1, forced: false },
    { ccn: "000002", prob: 0.3, forced: false },
    { ccn: "000003", prob: 0.6, forced: false },
    { ccn: "000004", prob: 1, forced: true },
  ];

  test("buckets by months since the last inspection, overdue from the scheduler's flag", () => {
    assert.deepEqual(homes.map(bucketOf), ["recent", "mid", "due", "overdue"]);
    assert.equal(bucketOf({ ccn: "x", weeks_since_last: Math.ceil(6 * WEEKS_PER_MONTH), forced: false }), "mid");
  });

  test("expected inspections add up the chances", () => {
    const rows = summarizeBacklog(homes, probs);
    assert.deepEqual(rows.map((row) => row.homes), [1, 1, 1, 1]);
    const total = rows.reduce((sum, row) => sum + row.expectedPicks, 0);
    assert.ok(Math.abs(total - 2) < 1e-9);
    assert.equal(rows[3].avgChance, 1);
  });

  test("next month's overdue count is the crossing homes not picked this month", () => {
    const next = nextMonthOverdue(homes, probs, 69.1);
    assert.equal(next.crossing, 1);
    assert.ok(Math.abs(next.expectedOverdue - 0.4) < 1e-9);
  });
});
