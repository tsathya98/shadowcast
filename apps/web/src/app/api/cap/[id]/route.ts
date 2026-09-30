import { ADVISORY_ID } from "@/lib/advisory";
import { getAdvisory } from "@/server/google";

/** One issued advisory as its CAP 1.2 message. Issued advisories never change, so it is cached indefinitely. */
export async function GET(_request: Request, ctx: RouteContext<"/api/cap/[id]">) {
  const { id } = await ctx.params;
  const record = ADVISORY_ID.test(id) ? await getAdvisory(id) : null;
  if (record?.status !== "issued" || !record.capXml)
    return new Response("No issued advisory with that id", { status: 404 });
  return new Response(record.capXml, {
    headers: {
      "Content-Type": "application/cap+xml; charset=utf-8",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}
