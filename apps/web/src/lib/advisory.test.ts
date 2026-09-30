import { describe, expect, it } from "vitest";

import { type Advisory, advisorySchema, capTime, toCapFeed, toCapXml } from "./advisory";

const advisory: Advisory = {
  event: "Extremely Severe Cyclonic Storm Fani",
  responseType: "Shelter",
  urgency: "Expected",
  severity: "Extreme",
  certainty: "Likely",
  onset: "2019-05-02T11:15:00Z",
  expires: "2019-05-03T18:00:00+05:30",
  areas: ["Puri", "Khordha"],
  actions: [{ assetId: "osm:node/1", assetName: "Puri 132 kV", action: "Stage line crews" }],
  infos: [
    { language: "en", headline: "Move to shelters", description: "Winds <100 kt> & rain", instruction: "Go now" },
    {
      language: "or",
      headline: "ବାତ୍ୟା ଆଶ୍ରୟସ୍ଥଳୀକୁ ଯାଆନ୍ତୁ",
      description: "ପ୍ରବଳ ପବନ",
      instruction: "ତୁରନ୍ତ ଯାଆନ୍ତୁ",
    },
  ],
};

describe("capTime", () => {
  it.each([
    ["2019-05-02T11:15:00Z", "2019-05-02T11:15:00+00:00"],
    ["2019-05-03T18:00:00+05:30", "2019-05-03T12:30:00+00:00"],
    ["2019-05-02T11:15:00.250Z", "2019-05-02T11:15:00+00:00"],
  ])("renders %s without the Z designator", (iso, expected) => {
    expect(capTime(iso)).toBe(expected);
  });
});

describe("toCapXml", () => {
  const xml = toCapXml(advisory, { identifier: "shadowcast-call_1", sent: "2026-09-26T15:46:03.426Z", note: "A & B" });

  it("builds a CAP 1.2 exercise alert with one info block per language", () => {
    expect(xml).toContain('<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">');
    expect(xml).toContain("<identifier>shadowcast-call_1</identifier>");
    expect(xml).toContain("<sent>2026-09-26T15:46:03+00:00</sent>");
    expect(xml).toContain("<status>Exercise</status>");
    expect(xml.match(/<info>/g)).toHaveLength(2);
    expect(xml).toContain("<language>or-IN</language>");
    expect(xml).toContain("<headline>ବାତ୍ୟା ଆଶ୍ରୟସ୍ଥଳୀକୁ ଯାଆନ୍ତୁ</headline>");
    expect(xml).toContain("<areaDesc>Puri, Khordha</areaDesc>");
    expect(xml).toContain("<onset>2019-05-02T11:15:00+00:00</onset>");
  });

  it("escapes XML special characters", () => {
    expect(xml).toContain("<note>A &amp; B</note>");
    expect(xml).toContain("<description>Winds &lt;100 kt&gt; &amp; rain</description>");
  });

  it("keeps officer actions out of the public message", () => {
    expect(xml).not.toContain("Stage line crews");
  });
});

describe("advisorySchema", () => {
  it("accepts a valid advisory, in any supported language", () => {
    expect(advisorySchema.safeParse(advisory).success).toBe(true);
    expect(advisorySchema.safeParse({ ...advisory, infos: [{ ...advisory.infos[0], language: "te" }] }).success).toBe(
      true,
    );
  });

  it.each([
    ["a repeated language", { infos: [advisory.infos[0], advisory.infos[0]] }],
    ["an unsupported language", { infos: [{ ...advisory.infos[0], language: "fr" }] }],
    ["no areas", { areas: [] }],
    ["a time without an offset", { onset: "2019-05-02T11:15:00" }],
  ])("rejects %s", (_, override) => {
    expect(advisorySchema.safeParse({ ...advisory, ...override }).success).toBe(false);
  });
});

describe("toCapFeed", () => {
  const origin = "https://shadowcast.example";

  it.each([
    [
      [
        {
          id: "call_2",
          status: "issued" as const,
          replay: "best-track",
          headline: "Move <now>",
          areas: ["Puri", "Khordha"],
          decidedAt: "2026-09-30T10:00:00.500Z",
        },
        {
          id: "call_1",
          status: "issued" as const,
          replay: "best-track",
          headline: "Prepare",
          areas: ["Ganjam"],
          decidedAt: "2026-09-29T08:00:00Z",
        },
      ],
      "2026-09-30T10:00:00+00:00",
      2,
    ],
    [[], "1970-01-01T00:00:00+00:00", 0],
  ])("lists issued advisories as Atom entries linking to their CAP messages", (issued, updated, count) => {
    const feed = toCapFeed(issued, origin);
    expect(feed).toContain('<feed xmlns="http://www.w3.org/2005/Atom">');
    expect(feed).toContain(`<link rel="self" href="${origin}/api/cap"/>`);
    expect(feed).toContain(`<updated>${updated}</updated>`);
    expect(feed.match(/<entry>/g) ?? []).toHaveLength(count);
    if (count) {
      expect(feed).toContain(`<link rel="alternate" type="application/cap+xml" href="${origin}/api/cap/call_2"/>`);
      expect(feed).toContain("<title>Move &lt;now&gt;</title>");
      expect(feed).toContain("<summary>Exercise. Areas: Puri, Khordha</summary>");
    }
  });
});
