import type { NextRequest } from "next/server";

import { toCapFeed } from "@/lib/advisory";
import { listAdvisories } from "@/server/google";

const LIMIT = 50;

/**
 * The public CAP feed: every advisory an officer approved, newest first, as the Atom feed alert aggregators poll.
 * An approval appears here at once (never cached), so approving is dispatching.
 */
export async function GET(request: NextRequest) {
  const issued = (await listAdvisories(null, LIMIT)).filter((advisory) => advisory.status === "issued");
  return new Response(toCapFeed(issued, request.nextUrl.origin), {
    headers: { "Content-Type": "application/atom+xml; charset=utf-8", "Cache-Control": "no-store" },
  });
}
