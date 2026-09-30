import type { NextRequest } from "next/server";

import { ADVISORY_ID } from "@/lib/advisory";
import { getAdvisory, speak } from "@/server/google";

export const maxDuration = 60;

/**
 * Speak one language of an issued advisory with Gemini-TTS (Cloud Text-to-Speech has no Odia voice). Only audited,
 * approved advisories can be spoken, and they never change, so the audio is cached indefinitely.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/api/advisories/[id]/audio">) {
  const { id } = await ctx.params;
  const language = request.nextUrl.searchParams.get("lang");
  const record = ADVISORY_ID.test(id) ? await getAdvisory(id) : null;
  const info = record?.status === "issued" ? record.advisory.infos.find((i) => i.language === language) : undefined;
  if (!info) return new Response("No issued advisory in that language", { status: 404 });

  const { bytes, mediaType } = await speak(`${info.headline}. ${info.description} ${info.instruction}`);
  return new Response(bytes, {
    headers: { "Content-Type": mediaType, "Cache-Control": "public, max-age=31536000, immutable" },
  });
}
