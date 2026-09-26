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
  getPredictability,
  getSimulate,
  getTrophy,
  postSchedule,
} from "../lib/api.ts";
import {
  isScored,
  pinColor,
  reductionCaption,
  scoreHeadline,
  scoreSummary,
  UNSCORED_COPY,
} from "../lib/format.ts";
import { topPredictability, visibleProbabilities } from "../lib/regulator.ts";

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

    const sim = await getSimulate(3);
    assert.equal(sim.months, 36);
    assert.equal(typeof sim.status_quo.undetected_shirk_resident_months, "number");
    assert.equal(typeof sim.popquiz.undetected_shirk_resident_months, "number");
    assert.equal(typeof sim.reduction_pct, "number");

    const hazard = await getPredictability();
    assert.ok(hazard.every((row) => typeof row.p_next_60d === "number"));
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
        if (url.startsWith("/api/simulate")) {
          res.end(
            JSON.stringify({
              months: 36,
              status_quo: { undetected_shirk_resident_months: 1 },
              popquiz: { undetected_shirk_resident_months: 1 },
              reduction_pct: 0,
            }),
          );
          return;
        }
        if (url === "/api/predictability") {
          res.end("[]");
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
    await getSimulate(3);
    await getPredictability();
    await getTrophy();

    const byPath = (prefix: string) => seen.find((call) => call.url.startsWith(prefix));
    assert.equal(byPath("/api/facilities")?.role, undefined);
    assert.equal(byPath("/api/facility/")?.role, undefined);
    assert.equal(byPath("/api/explain")?.role, undefined);
    assert.equal(byPath("/api/schedule")?.role, "regulator");
    assert.equal(byPath("/api/simulate")?.role, "regulator");
    assert.equal(byPath("/api/predictability")?.role, "regulator");
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

describe("regulator lists", () => {
  test("hides zero probabilities and keeps the top predictability scores", () => {
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

    const rows = Array.from({ length: 25 }, (_, index) => ({
      ccn: String(index).padStart(6, "0"),
      name: `Home ${index}`,
      p_next_60d: index / 100,
    }));
    const top = topPredictability(rows);
    assert.equal(top.length, 20);
    assert.equal(top[0]?.ccn, "000024");
    assert.ok(top[0].p_next_60d > top[19].p_next_60d);
  });
});
describe("scores and simulation copy", () => {
  test("null scores and labels are not filled in", () => {
    assert.equal(isScored(null, null, null), false);
    assert.equal(scoreHeadline(null, 0, 0, null), null);
    assert.equal(scoreSummary(null, null, null), UNSCORED_COPY);
    assert.equal(pinColor(null, 4.2), "#8a8478");
    assert.equal(pinColor("Watch", null), "#8a8478");
    assert.equal(pinColor("Low", 4.2), "#a33b32");
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

  test("a small simulation reduction stays a short-run gap", () => {
    const caption = reductionCaption(3.5);
    assert.ok(caption);
    assert.match(caption, /3\.5%/);
    assert.match(caption, /small short-run gap/);
    assert.match(caption, /40–60 week window/);
    assert.match(reductionCaption(-16) ?? "", /more undetected shirk/);
    assert.doesNotMatch(reductionCaption(43.9) ?? "", /small short-run gap/);
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
    assert.doesNotMatch(family, /p_next_60d|predictability|X-Demo-Role|getPredictability/);

    const familySurfaces = [
      path.join(webRoot, "app", "page.tsx"),
      path.join(webRoot, "app", "facility", "[ccn]", "page.tsx"),
      path.join(webRoot, "components", "FacilityMap.tsx"),
      path.join(webRoot, "components", "MapView.tsx"),
      path.join(webRoot, "components", "StaffingChart.tsx"),
    ];
    const surfaceText = familySurfaces.map((file) => readFileSync(file, "utf8")).join("\n");
    assert.doesNotMatch(surfaceText, /p_next_60d|getPredictability|PredictabilityPanel/);
    assert.match(text, /not enough inspections/);
    assert.match(text, /Illustrative model/);
    assert.match(text, /undetected shirk resident-months/);
    assert.match(text, /never shown to families/);
  });
});
