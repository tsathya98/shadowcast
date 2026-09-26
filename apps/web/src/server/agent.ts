/**
 * The ShadowCast duty analyst: a Gemini agent that explains the deterministic ranking and drafts advisories. Gemini
 * never scores anything; every number it quotes comes from the geo API through a tool, and an advisory is issued
 * only after an officer approves the tool call.
 */
import { type InferAgentUIMessage, isStepCount, tool, ToolLoopAgent } from "ai";
import { z } from "zod";

import { advisorySchema, toCapXml } from "@/lib/advisory";
import { kindLabel, utcAndIst } from "@/lib/format";
import type { Asset, ForecastAsset, Page, ScenarioDetail } from "@/lib/types";
import { geoFetch } from "@/server/geo";
import { recordDecision, vertex } from "@/server/google";

export const agentContextSchema = z.object({
  scenarioId: z.string().regex(/^[a-z0-9-]{1,40}$/),
  forecastKey: z
    .string()
    .regex(/^\d{8}T\d{2}Z$/)
    .nullable(),
  selectedAssetId: z.string().max(120).nullish(),
});

export type AgentContext = z.infer<typeof agentContextSchema>;

const MODEL_ID = "gemini-3.8-flash";
const MAX_STEPS = 8;
// Vertex AI pay-as-you-go capacity is shared and briefly throttles bursts (429); back off 2, 4, 8, 16 s.
const MAX_RETRIES = 4;

/** The fields Gemini needs to reason about an asset; observed satellite loss only in hindsight (best-track) replays. */
function toolAsset(asset: Asset | ForecastAsset, hindsight: boolean) {
  return {
    asset_id: asset.asset_id,
    rank: asset.rank,
    kind: asset.kind,
    name: asset.name,
    p_outage: asset.p_outage,
    peak_wind_kt: asset.peak_wind_kt,
    peak_time: asset.peak_time,
    gale_arrival: asset.gale_arrival,
    min_dist_km: asset.min_dist_km,
    population_2km: asset.population,
    elevation_m: asset.elevation_m,
    ...("p34" in asset && { p_gale_34kt: asset.p34, p_hurricane_64kt: asset.p64, members: asset.members }),
    ...(hindsight && { observed_night_light_loss_pct: asset.observed_loss_pct }),
    reasons: asset.reasons,
  };
}

function instructions(scenario: ScenarioDetail, context: AgentContext): string {
  const forecast = scenario.forecasts.find((f) => f.key === context.forecastKey);
  const replay = forecast
    ? `the ECMWF ensemble forecast issued ${utcAndIst(forecast.issued)} (${forecast.lead_h.toFixed(0)} h before ` +
      `landfall, ${forecast.members} members). Treat the issue time as "now": nothing after it is known. ` +
      `${forecast.assets_likely_gale} assets are likely (>50% of members) to get gales and ` +
      `${forecast.assets_likely_hurricane} hurricane-force winds.`
    : "the observed best track, in hindsight. Satellite night-light loss after landfall is available per asset.";
  const { model, skill } = scenario;
  const bands = scenario.loss_by_band
    .map((b) => `${b.low_kt}-${b.high_kt} kt: median ${b.median.toFixed(0)}% night-light loss (n=${b.n})`)
    .join("; ");
  // This storm's own backtest is hindsight: only quote it when replaying the observed track.
  const backtest = forecast
    ? ""
    : `
- Backtest for this storm (${skill.out_of_sample ? "out of sample: the model was never fitted on it" : "in sample"}): AUC ${skill.auc?.toFixed(2) ?? "n/a"}, Brier ${skill.brier?.toFixed(3) ?? "n/a"}, Spearman ${skill.spearman?.toFixed(2) ?? "n/a"}. Loss by modelled wind: ${bands || "not available"}.` +
      (skill.spatial_holdout
        ? ` Spatial holdout (${skill.spatial_holdout.folds} stretches of coast each hidden in turn): out-of-fold AUC ${skill.spatial_holdout.auc?.toFixed(2) ?? "n/a"}.`
        : "");
  return `You are ShadowCast's duty analyst, working beside a district emergency operations officer in Odisha, India.

Storm: ${scenario.storm} ${scenario.season}, ${scenario.region.name}. Landfall ${utcAndIst(scenario.landfall)}.
The officer is replaying ${replay}
${context.selectedAssetId ? `The officer has selected asset_id "${context.selectedAssetId}" on the map; "this asset" means it.` : ""}

How ShadowCast works (explain only when asked, in one or two sentences):
- Wind at each asset comes from a Holland parametric wind field along the storm track, every 15 minutes.
- P(outage) is a logistic model of peak wind against a loss of at least half the night lights seen by NASA's VIIRS satellite, fitted on ${model.trained_on} (${model.n} substations, AUC ${model.auc?.toFixed(2) ?? "n/a"}).
- Priority = P(outage) × criticality (hospital and cyclone shelter 5, substation and health centre 4, school 2); ties go to gale exposure, then population.${backtest}

Rules:
- Every number, name and time you state must come from a tool result or this message. Never estimate or invent. If the tools do not have it, say so.
- Answer in a few short sentences or "-" bullet lines. Plain text: no Markdown headings, bold or tables. Give times in IST.
- To draft an advisory, first gather the facts with searchAssets, then call issueAdvisory exactly once, with no accompanying text: the officer reviews it on a card and approves or rejects it. Nothing is issued without approval. Once the decision comes back, confirm it in one short sentence.
- Advisory content: base onset on the earliest gale arrival among the covered assets; order officer actions by priority; write Hindi and Odia in native script with simple words a villager understands.
- If the officer rejects an advisory, do not call issueAdvisory again until they say what to change.
- This is a replay of a past storm, so every advisory is a CAP "Exercise" message, not an official warning. IMD and OSDMA remain the authority.`;
}

/** Build the agent for one request: the scenario and replay the officer is viewing scope every tool call. */
export function createAgent(scenario: ScenarioDetail, context: AgentContext) {
  const replay = context.forecastKey ?? "best-track";
  const assetsPath = context.forecastKey
    ? `/scenarios/${scenario.id}/forecasts/${context.forecastKey}/assets`
    : `/scenarios/${scenario.id}/assets`;
  const kinds = Object.keys(scenario.asset_counts) as [string, ...string[]];

  return new ToolLoopAgent({
    model: vertex(MODEL_ID),
    instructions: instructions(scenario, context),
    stopWhen: isStepCount(MAX_STEPS),
    maxRetries: MAX_RETRIES,
    tools: {
      searchAssets: tool({
        description:
          "Assets in priority order for the replay the officer is viewing, optionally filtered by name or asset_id and by kind. " +
          "Each asset carries its rank, outage probability, winds, timing, population and the model's reasons.",
        inputSchema: z.object({
          query: z.string().min(2).optional().describe("Part of the asset's name, or its asset_id"),
          kinds: z
            .array(z.enum(kinds))
            .optional()
            .describe(`Asset kinds: ${kinds.map((k) => `${k} (${kindLabel(k)})`).join(", ")}`),
          limit: z.number().int().min(1).max(25).default(10),
        }),
        execute: async ({ query, kinds: selected, limit }) => {
          const params = new URLSearchParams({ limit: String(limit) });
          if (query) params.set("q", query);
          for (const kind of selected ?? []) params.append("kind", kind);
          const page = await geoFetch<Page<Asset | ForecastAsset>>(`${assetsPath}?${params}`);
          return { total: page.total, assets: page.items.map((asset) => toolAsset(asset, !context.forecastKey)) };
        },
      }),
      issueAdvisory: tool({
        description:
          "Submit a drafted advisory (officer actions plus the public CAP 1.2 message per language) for the officer's approval. " +
          "On approval it is issued as a CAP Exercise message and written to the audit log.",
        inputSchema: advisorySchema,
        execute: async (advisory, { toolCallId }) => {
          const sent = new Date().toISOString();
          const capXml = toCapXml(advisory, {
            identifier: `shadowcast-${toolCallId}`,
            sent,
            note: `ShadowCast replay of ${scenario.storm} ${scenario.season} (${replay}); an exercise, not an official warning.`,
          });
          await recordDecision(toolCallId, {
            status: "issued",
            scenarioId: scenario.id,
            replay,
            advisory,
            capXml,
            reason: null,
            decidedAt: sent,
          });
          return { advisoryId: toolCallId, sent, capXml };
        },
      }),
    },
    toolApproval: { issueAdvisory: "user-approval" },
    experimental_toolApprovalSecret: process.env.TOOL_APPROVAL_SECRET,
  });
}

export type ShadowCastMessage = InferAgentUIMessage<ReturnType<typeof createAgent>>;
