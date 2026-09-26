import { Console } from "@/components/console";
import type { ScenarioSummary } from "@/lib/types";

const GEO_API_URL = process.env.GEO_API_URL ?? "https://shadowcast-geo-489356738785.asia-south1.run.app";

async function loadScenarios(): Promise<ScenarioSummary[] | Error> {
  try {
    const response = await fetch(`${GEO_API_URL}/scenarios`, { cache: "no-store" });
    if (!response.ok) return new Error(`geo API responded ${response.status}`);
    return (await response.json()) as ScenarioSummary[];
  } catch (error) {
    return error instanceof Error ? error : new Error(String(error));
  }
}

export default async function Home() {
  const scenarios = await loadScenarios();
  if (scenarios instanceof Error || scenarios.length === 0) {
    return (
      <main className="grid h-dvh place-items-center bg-[var(--surface-0)] p-6 text-center text-[var(--text-secondary)]">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">ShadowCast</h1>
          <p className="mt-2 text-sm">
            {scenarios instanceof Error
              ? `The geo API is unreachable (${scenarios.message}).`
              : "No scenarios are built yet."}
          </p>
        </div>
      </main>
    );
  }
  return <Console scenarios={scenarios} mapsApiKey={process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? ""} />;
}
