import { describe, expect, it, vi } from "vitest";

import { blobToDataUrl, encodeWav, fromPcm16, recordingToWavUrl, toPcm16, voiceCallUrl } from "./media";

describe("encodeWav", () => {
  it("writes a 16-bit mono PCM header and clipped little-endian samples", () => {
    const wav = new DataView(encodeWav(new Float32Array([0, 1, -1, 2, -0.5]), 16_000));
    const ascii = (offset: number) => String.fromCharCode(...[0, 1, 2, 3].map((i) => wav.getUint8(offset + i)));

    expect([ascii(0), ascii(8), ascii(12), ascii(36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
    expect(wav.byteLength).toBe(44 + 5 * 2);
    expect(wav.getUint32(4, true)).toBe(36 + 10);
    expect([wav.getUint16(20, true), wav.getUint16(22, true), wav.getUint16(34, true)]).toEqual([1, 1, 16]);
    expect(wav.getUint32(24, true)).toBe(16_000);
    expect(wav.getUint32(28, true)).toBe(32_000);
    expect([0, 1, 2, 3, 4].map((i) => wav.getInt16(44 + i * 2, true))).toEqual([0, 32767, -32768, 32767, -16384]);
  });
});

describe("recordingToWavUrl", () => {
  it("decodes the recording at 16 kHz, re-encodes it as WAV and closes the audio context", async () => {
    const close = vi.fn(() => Promise.resolve());
    class FakeAudioContext {
      constructor(readonly options: { sampleRate: number }) {}
      decodeAudioData = () => Promise.resolve({ getChannelData: () => new Float32Array([0.5, -0.5]) });
      close = close;
    }
    class FakeFileReader {
      result: string | null = null;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      error = null;
      readAsDataURL(blob: Blob) {
        void blob.arrayBuffer().then((bytes) => {
          this.result = `data:${blob.type};base64,${Buffer.from(bytes).toString("base64")}`;
          this.onload?.();
        });
      }
    }
    vi.stubGlobal("AudioContext", FakeAudioContext);
    vi.stubGlobal("FileReader", FakeFileReader);

    const url = await recordingToWavUrl(new Blob(["opus"], { type: "audio/webm" }));

    expect(url.startsWith("data:audio/wav;base64,")).toBe(true);
    expect(Buffer.from(url.split(",")[1], "base64").byteLength).toBe(44 + 4);
    expect(close).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("rejects when the file cannot be read", async () => {
    class BrokenFileReader {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      error = new Error("unreadable");
      readAsDataURL() {
        queueMicrotask(() => this.onerror?.());
      }
    }
    vi.stubGlobal("FileReader", BrokenFileReader);

    await expect(blobToDataUrl(new Blob(["x"]))).rejects.toThrow("unreadable");
    vi.unstubAllGlobals();
  });
});

describe("toPcm16 and fromPcm16", () => {
  it("clips to 16-bit PCM and reads Gemini's PCM back into [-1, 1]", () => {
    const pcm = toPcm16(new Float32Array([0, 1, -1, 2, -0.5]));
    expect([...pcm]).toEqual([0, 32767, -32768, 32767, -16384]);
    expect([...fromPcm16(new Int16Array([0, -32768, 16384]).buffer)]).toEqual([0, -1, 0.5]);
  });
});

describe("voiceCallUrl", () => {
  it.each([
    [{ scenarioId: "fani-2019", forecastKey: null, language: null }, "wss://geo.example/scenarios/fani-2019/voice"],
    [
      { scenarioId: "dana-2024", forecastKey: "20241022T00Z", selectedAssetId: "osm:node/1", language: "or" as const },
      "wss://geo.example/scenarios/dana-2024/voice?forecast=20241022T00Z&asset=osm%3Anode%2F1&language=or",
    ],
  ])("opens the call on the geo service for the replay being viewed", (context, expected) => {
    expect(voiceCallUrl("https://geo.example", context)).toBe(expected);
  });
});
