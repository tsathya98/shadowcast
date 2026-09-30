import { z } from "zod";

import { speak } from "@/server/google";

export const maxDuration = 60;

const bodySchema = z.object({ text: z.string().trim().min(1).max(1500) });

/** Read one of the duty analyst's replies aloud with Gemini-TTS, in whatever language the reply is written. */
export async function POST(request: Request) {
  const body = bodySchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return Response.json({ error: z.prettifyError(body.error) }, { status: 400 });
  const { bytes, mediaType } = await speak(body.data.text);
  return new Response(bytes, { headers: { "Content-Type": mediaType, "Cache-Control": "no-store" } });
}
