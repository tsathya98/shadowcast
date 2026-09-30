"use client";

import { clsx } from "clsx";
import { LoaderCircle, PhoneOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { type CallContext, CALL_OUTPUT_RATE, fromPcm16, toPcm16, VOICE_SAMPLE_RATE, voiceCallUrl } from "@/lib/media";

const GEO_URL = process.env.NEXT_PUBLIC_GEO_URL ?? "";
const FRAME_SAMPLES = VOICE_SAMPLE_RATE / 10; // 100 ms of microphone audio per message

// Runs on the audio thread: hands each 128-sample block of microphone audio to the page.
const MIC_WORKLET = `class ShadowCastMic extends AudioWorkletProcessor {
  process(inputs) { const channel = inputs[0][0]; if (channel) this.port.postMessage(channel.slice(0)); return true; }
}
registerProcessor("shadowcast-mic", ShadowCastMic);`;

type CallState = "connecting" | "listening" | "looking-up" | "ended";

interface Line {
  role: "user" | "model";
  text: string;
}

interface CallEvent {
  type: "ready" | "transcript" | "interrupted" | "tool" | "turn" | "end";
  role?: Line["role"];
  text?: string;
  reason?: string;
}

interface VoiceCallProps {
  context: CallContext;
  onClose: () => void;
}

/**
 * A live voice call with the duty analyst (Gemini Live through the geo service): the officer talks, Gemini answers
 * aloud and can be interrupted mid-sentence, and both sides are captioned as they speak.
 */
export function VoiceCall({ context, onClose }: VoiceCallProps) {
  const [state, setState] = useState<CallState>("connecting");
  const [lines, setLines] = useState<Line[]>([]);
  const [reason, setReason] = useState<string | null>(null);
  const hangUp = useRef<() => void>(() => undefined);

  useEffect(() => {
    const socket = new WebSocket(voiceCallUrl(GEO_URL, context));
    socket.binaryType = "arraybuffer";
    const speaker = new AudioContext({ sampleRate: CALL_OUTPUT_RATE });
    const playing = new Set<AudioBufferSourceNode>();
    let playAt = 0;
    let microphone: { stream: MediaStream; context: AudioContext } | null = null;
    let closed = false;

    const stopPlayback = () => {
      playing.forEach((source) => source.stop());
      playing.clear();
      playAt = 0;
    };
    // Queue each chunk of Gemini's speech right after the previous one, so the answer plays without gaps.
    const play = (bytes: ArrayBuffer) => {
      const samples = fromPcm16(bytes);
      const buffer = speaker.createBuffer(1, samples.length, CALL_OUTPUT_RATE);
      buffer.copyToChannel(samples, 0);
      const source = speaker.createBufferSource();
      source.buffer = buffer;
      source.connect(speaker.destination);
      source.onended = () => playing.delete(source);
      playAt = Math.max(playAt, speaker.currentTime);
      source.start(playAt);
      playAt += buffer.duration;
      playing.add(source);
    };
    const caption = (role: Line["role"], text: string) =>
      setLines((current) => {
        const last = current.at(-1);
        return last?.role === role
          ? [...current.slice(0, -1), { role, text: last.text + text }]
          : [...current, { role, text }];
      });
    const finish = (why: string | null) => {
      if (closed) return;
      closed = true;
      setState("ended");
      setReason(why);
      stopPlayback();
      microphone?.stream.getTracks().forEach((track) => track.stop());
      void microphone?.context.close();
      void speaker.close();
      if (socket.readyState <= WebSocket.OPEN) socket.close();
    };
    hangUp.current = () => finish(null);

    const startMicrophone = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const capture = new AudioContext({ sampleRate: VOICE_SAMPLE_RATE });
      microphone = { stream, context: capture };
      if (closed) return finish(null);
      const worklet = URL.createObjectURL(new Blob([MIC_WORKLET], { type: "text/javascript" }));
      await capture.audioWorklet.addModule(worklet);
      URL.revokeObjectURL(worklet);
      const node = new AudioWorkletNode(capture, "shadowcast-mic");
      let frame = new Float32Array(0);
      node.port.onmessage = (event: MessageEvent<Float32Array>) => {
        const joined = new Float32Array(frame.length + event.data.length);
        joined.set(frame);
        joined.set(event.data, frame.length);
        frame = joined;
        if (frame.length >= FRAME_SAMPLES && socket.readyState === WebSocket.OPEN) {
          socket.send(toPcm16(frame));
          frame = new Float32Array(0);
        }
      };
      capture.createMediaStreamSource(stream).connect(node);
    };

    socket.onmessage = (message: MessageEvent<ArrayBuffer | string>) => {
      if (typeof message.data !== "string") return play(message.data);
      const event = JSON.parse(message.data) as CallEvent;
      if (event.type === "ready") {
        setState("listening");
        startMicrophone().catch(() => finish("Microphone unavailable: allow access in the browser to call."));
      } else if (event.type === "transcript" && event.role && event.text) {
        caption(event.role, event.text);
        setState("listening");
      } else if (event.type === "interrupted") {
        stopPlayback();
      } else if (event.type === "tool") {
        setState("looking-up");
      } else if (event.type === "end") {
        finish(event.reason === "call ended" ? null : (event.reason ?? null));
      }
    };
    socket.onclose = (event) =>
      finish(
        event.code === 1013 ? "All voice lines are busy. Try again in a minute." : closed ? null : "Call dropped.",
      );
    return () => finish(null);
    // A call is scoped to the replay it started on; the parent remounts the panel when the replay changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ended = state === "ended";
  return (
    <section
      aria-label="Voice call with the duty analyst"
      className="flex flex-col gap-3 rounded-2xl border border-[var(--accent)] bg-[var(--surface-2)] p-3.5"
    >
      <div className="flex items-center gap-2">
        <span
          className={clsx("size-2 rounded-full", ended ? "bg-[var(--text-muted)]" : "animate-pulse bg-[var(--accent)]")}
          aria-hidden
        />
        <span className="label flex-1 !text-[var(--text-primary)]">
          {state === "connecting"
            ? "Connecting to Gemini Live…"
            : state === "looking-up"
              ? "Live call · looking up sites…"
              : ended
                ? "Call ended"
                : "Live call · speak any time"}
        </span>
        {state === "connecting" && <LoaderCircle className="size-3.5 animate-spin text-[var(--text-muted)]" />}
        <button
          type="button"
          onClick={() => (ended ? onClose() : hangUp.current())}
          className={clsx("flex items-center gap-1 px-3 py-1.5 text-xs", ended ? "btn-ghost" : "btn-primary")}
        >
          <PhoneOff className="size-3.5" /> {ended ? "Close" : "End call"}
        </button>
      </div>
      {reason && <p className="text-xs text-[var(--text-secondary)]">{reason}</p>}
      {lines.length === 0 && !ended && (
        <p className="text-xs text-[var(--text-muted)]">
          Ask about any site in any language. You can interrupt the answer. Headphones stop the analyst hearing itself.
        </p>
      )}
      <div className="flex max-h-60 flex-col gap-1.5 overflow-y-auto text-sm" aria-live="polite">
        {lines.map((line, index) => (
          <p
            key={index}
            className={line.role === "user" ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)]"}
          >
            <span className="label mr-1.5">{line.role === "user" ? "You" : "Analyst"}</span>
            {line.text}
          </p>
        ))}
      </div>
    </section>
  );
}
