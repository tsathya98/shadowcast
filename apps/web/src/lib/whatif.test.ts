import { describe, expect, it } from "vitest";

import type { Asset, OutageModel } from "./types";
import { applyWhatIf, AS_MODELLED } from "./whatif";

const model = { intercept: -10, slope: 0.1 } as OutageModel; // 50% outage at 100 kt

function site(id: string, wind: number | null, criticality: number, extra: Partial<Asset> = {}) {
  return { asset_id: id, peak_wind_kt: wind, criticality, population: 0, ...extra } as Asset;
}

const coastal = site("shelter", 100, 5, { surge_m: 2, coast_km: 14.5, elevation_m: 1, flood_m: 0, rain_mm: 200 });
const inland = site("hospital", 110, 4, { elevation_m: null, flood_m: null, rain_mm: null });
const unknown = site("school", null, 1, { population: 10 });
const unmapped = site("clinic", null, 1, { population: null, surge_m: 1, coast_km: null, flood_m: 0.2 }); // ties: population decides

describe("applyWhatIf", () => {
  it("returns the assets untouched for the storm as modelled", () => {
    const assets = [coastal, inland];
    expect(applyWhatIf(assets, model, AS_MODELLED)).toBe(assets);
  });

  it.each([
    // wind, tide, rain → shelter outage, shelter flood depth, shelter rain, first-ranked site
    [1.2, 0, 1, 1 / (1 + Math.exp(-2)), 0.88, 200, "shelter"],
    [1, 1.5, 2, 0.5, 1.5, 400, "hospital"],
    [0.5, 0, 0.5, 1 / (1 + Math.exp(5)), 0, 100, "hospital"],
  ])("wind ×%s, tide +%s m, rain ×%s re-scores and re-ranks", (wind, tide_m, rain, p, flood, rainMm, first) => {
    const result = applyWhatIf([coastal, inland, unmapped, unknown], model, { wind, tide_m, rain });
    const shelter = result.find((a) => a.asset_id === "shelter")!;

    expect(shelter.p_outage).toBeCloseTo(p, 6);
    expect(shelter.score).toBeCloseTo(p, 6);
    expect(shelter.flood_m).toBeCloseTo(flood, 6);
    expect(shelter.rain_mm).toBeCloseTo(rainMm, 6);
    expect(result[0].asset_id).toBe(first);
    expect(result.map((a) => a.asset_id).slice(2)).toEqual(["school", "clinic"]);
    expect(result.map((a) => a.rank)).toEqual([1, 2, 3, 4]);
    // Sites without the inputs keep what they had (no elevation, no rain, no wind → the model's floor).
    const hospital = result.find((a) => a.asset_id === "hospital")!;
    expect([hospital.flood_m, hospital.rain_mm]).toEqual([null, null]);
    expect(result.find((a) => a.asset_id === "clinic")!.flood_m).toBe(0.2);
    expect(result.find((a) => a.asset_id === "school")!.peak_wind_kt).toBeNull();
  });
});
