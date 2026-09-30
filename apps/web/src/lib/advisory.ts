/**
 * The advisory the agent drafts and an officer approves: officer actions per asset plus a public CAP 1.2 message in
 * each language. The schema doubles as the agent tool's input schema, so Gemini's draft is validated before anyone
 * sees it.
 */
import { z } from "zod";

export const LANGUAGES = {
  en: { cap: "en-IN", label: "English", name: "English" },
  hi: { cap: "hi-IN", label: "हिन्दी", name: "Hindi" },
  or: { cap: "or-IN", label: "ଓଡ଼ିଆ", name: "Odia" },
  te: { cap: "te-IN", label: "తెలుగు", name: "Telugu" },
  bn: { cap: "bn-IN", label: "বাংলা", name: "Bengali" },
  ta: { cap: "ta-IN", label: "தமிழ்", name: "Tamil" },
} as const;

export type Language = keyof typeof LANGUAGES;

/** The first language of the public in each study region; advisories go out in English, Hindi and this language. */
export const REGION_LANGUAGE: Record<string, Language> = {
  "odisha-coast": "or",
  "north-andhra-coast": "te",
  "west-bengal-coast": "bn",
};

/** The state each study region lies in, as NDMA SACHET names it in warning areas. */
export const REGION_STATE: Record<string, string> = {
  "odisha-coast": "Odisha",
  "north-andhra-coast": "Andhra Pradesh",
  "west-bengal-coast": "West Bengal",
};

export const LANGUAGE_CODES = Object.keys(LANGUAGES) as [Language, ...Language[]];

export const advisorySchema = z.object({
  event: z.string().max(80).describe("CAP event, e.g. 'Extremely Severe Cyclonic Storm Fani'"),
  responseType: z.enum(["Evacuate", "Shelter", "Prepare", "Monitor"]).describe("CAP responseType for the public"),
  urgency: z.enum(["Immediate", "Expected", "Future"]),
  severity: z.enum(["Extreme", "Severe", "Moderate"]),
  certainty: z.enum(["Observed", "Likely", "Possible"]),
  onset: z.iso.datetime({ offset: true }).describe("When gales are expected to begin (from the tool results)"),
  expires: z.iso.datetime({ offset: true }).describe("When the advisory lapses"),
  areas: z.array(z.string().max(40)).min(1).max(15).describe("Districts the advisory covers"),
  actions: z
    .array(
      z.object({
        assetId: z.string().describe("asset_id exactly as returned by searchAssets"),
        assetName: z.string().max(80),
        action: z.string().max(200).describe("One concrete preparatory action for officials"),
      }),
    )
    .max(12)
    .describe("Officer actions for the highest-priority assets, most urgent first"),
  infos: z
    .array(
      z.object({
        language: z.enum(LANGUAGE_CODES),
        headline: z.string().max(160),
        description: z.string().max(700).describe("What is expected, where and when"),
        instruction: z.string().max(700).describe("What the public should do"),
      }),
    )
    .min(1)
    .max(LANGUAGE_CODES.length)
    .refine((infos) => new Set(infos.map((info) => info.language)).size === infos.length, "one info per language")
    .describe("The public message, once per language (native script for Hindi and the local language)"),
});

export type Advisory = z.infer<typeof advisorySchema>;

/** An officer's audited decision as the brief lists it: what was decided, without the full CAP message. */
export interface AdvisorySummary {
  id: string;
  status: "issued" | "rejected";
  /** "best-track" or the forecast key the officer was replaying. */
  replay: string;
  headline: string;
  /** Districts the advisory covers. */
  areas: string[];
  decidedAt: string;
}

/** Audit-log ids are the agent's tool-call ids; anything else in a URL is rejected before Firestore is asked. */
export const ADVISORY_ID = /^[\w-]{1,100}$/;

export interface CapEnvelope {
  identifier: string;
  sent: string;
  /** Plain-language note carried in the CAP <note>, e.g. that this is a replay exercise. */
  note: string;
}

const XML_ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" };

const escapeXml = (text: string) => text.replace(/[&<>"']/g, (char) => XML_ESCAPES[char]);

const element = (tag: string, value: string) => `<${tag}>${escapeXml(value)}</${tag}>`;

/** CAP 1.2 forbids the "Z" designator: render any ISO time as UTC with an explicit +00:00 offset, to the second. */
export function capTime(iso: string): string {
  return new Date(iso).toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

/**
 * Render the advisory as a CAP 1.2 alert with one <info> block per language. The status is always "Exercise":
 * ShadowCast drafts for the authorities (IMD, OSDMA) and never issues real warnings.
 */
export function toCapXml(advisory: Advisory, envelope: CapEnvelope): string {
  const infos = advisory.infos.map((info) =>
    [
      "<info>",
      element("language", LANGUAGES[info.language].cap),
      element("category", "Met"),
      element("event", advisory.event),
      element("responseType", advisory.responseType),
      element("urgency", advisory.urgency),
      element("severity", advisory.severity),
      element("certainty", advisory.certainty),
      element("onset", capTime(advisory.onset)),
      element("expires", capTime(advisory.expires)),
      element("senderName", "ShadowCast (exercise)"),
      element("headline", info.headline),
      element("description", info.description),
      element("instruction", info.instruction),
      `<area>${element("areaDesc", advisory.areas.join(", "))}</area>`,
      "</info>",
    ].join(""),
  );
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">',
    element("identifier", envelope.identifier),
    element("sender", "shadowcast.exercise"),
    element("sent", capTime(envelope.sent)),
    element("status", "Exercise"),
    element("msgType", "Alert"),
    element("scope", "Public"),
    element("note", envelope.note),
    ...infos,
    "</alert>",
  ].join("\n");
}

/**
 * Render issued advisories as an Atom feed of CAP alerts: the form in which an alerting authority publishes its
 * warnings for aggregators (NDMA SACHET, Google Public Alerts, WMO Alert Hub) to poll. Approving an advisory is
 * therefore enough to dispatch it: the next poll picks it up, with no further human step.
 *
 * @param issued Issued advisories, newest first.
 * @param origin Absolute origin of the site, e.g. "https://shadowcast-two.vercel.app", for the entry links.
 * @returns Atom 1.0 XML; each entry links to its CAP 1.2 message at /api/cap/<id>.
 */
export function toCapFeed(issued: AdvisorySummary[], origin: string): string {
  const entries = issued.map((advisory) =>
    [
      "<entry>",
      element("id", `${origin}/api/cap/${advisory.id}`),
      element("title", advisory.headline),
      element("updated", capTime(advisory.decidedAt)),
      element("summary", `Exercise. Areas: ${advisory.areas.join(", ")}`),
      `<link rel="alternate" type="application/cap+xml" href="${escapeXml(`${origin}/api/cap/${advisory.id}`)}"/>`,
      "</entry>",
    ].join(""),
  );
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom">',
    element("id", `${origin}/api/cap`),
    element("title", "ShadowCast CAP alerts (exercise)"),
    element("updated", capTime(issued[0]?.decidedAt ?? new Date(0).toISOString())),
    `<author>${element("name", "ShadowCast (exercise)")}</author>`,
    `<link rel="self" href="${escapeXml(`${origin}/api/cap`)}"/>`,
    ...entries,
    "</feed>",
  ].join("\n");
}
