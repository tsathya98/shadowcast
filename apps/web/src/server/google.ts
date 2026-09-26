/**
 * Google Cloud clients for the server: Gemini on Vertex AI and the Firestore audit log. Both authenticate with
 * Application Default Credentials (gcloud locally; Workload Identity Federation on Vercel).
 */
import { Firestore } from "@google-cloud/firestore";
import { createVertex } from "@ai-sdk/google-vertex";

import type { Advisory } from "@/lib/advisory";

const PROJECT = process.env.GOOGLE_CLOUD_PROJECT ?? "argmax-cyclone-2026";

/** Gemini 3.x models are served only from the global Vertex AI endpoint. */
export const vertex = createVertex({ project: PROJECT, location: "global" });

const advisories = new Firestore({ projectId: PROJECT }).collection("advisories");

const ALREADY_EXISTS = 6; // gRPC status code

export interface AdvisoryRecord {
  status: "issued" | "rejected";
  scenarioId: string;
  /** "best-track" or the forecast key the officer was replaying. */
  replay: string;
  advisory: Advisory;
  capXml: string | null;
  reason: string | null;
  decidedAt: string;
}

/**
 * Append an officer's decision to the audit log, keyed by the tool call it answers. The log is append-only: a
 * decision is written once, and replays of the same conversation (the client resends history) are no-ops.
 */
export async function recordDecision(toolCallId: string, record: AdvisoryRecord): Promise<void> {
  try {
    await advisories.doc(toolCallId).create(record);
  } catch (error) {
    if ((error as { code?: number }).code !== ALREADY_EXISTS) throw error;
  }
}

/** An audited advisory by id, or null when there is none. */
export async function getAdvisory(id: string): Promise<AdvisoryRecord | null> {
  const snapshot = await advisories.doc(id).get();
  return snapshot.exists ? (snapshot.data() as AdvisoryRecord) : null;
}
