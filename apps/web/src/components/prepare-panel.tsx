"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, lastAssistantMessageIsCompleteWithApprovalResponses } from "ai";
import { clsx } from "clsx";
import { ArrowUp, LoaderCircle, Search, Square } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { AdvisoryCard } from "@/components/advisory-card";
import type { AgentContext, ShadowCastMessage } from "@/server/agent";

interface PreparePanelProps {
  context: AgentContext;
  suggestions: string[];
  onSelectAsset: (assetId: string) => void;
}

/** The Gemini duty analyst: explains the ranking and drafts advisories that the officer approves or rejects. */
export function PreparePanel({ context, suggestions, onSelectAsset }: PreparePanelProps) {
  // One conversation per replay (the parent keys this panel by it); the map selection travels with each message.
  const [transport] = useState(
    () =>
      new DefaultChatTransport<ShadowCastMessage>({
        api: "/api/agent",
        body: { scenarioId: context.scenarioId, forecastKey: context.forecastKey },
      }),
  );
  const { messages, sendMessage, status, error, stop, addToolApprovalResponse } = useChat<ShadowCastMessage>({
    transport,
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
  });
  const [input, setInput] = useState("");
  const busy = status === "submitted" || status === "streaming";

  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const send = (text: string) => {
    if (!text.trim() || busy) return;
    void sendMessage({ text: text.trim() }, { body: { selectedAssetId: context.selectedAssetId } });
    setInput("");
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    send(input);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pb-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="space-y-3 pt-1">
            <div className="label">Duty analyst · Gemini 3.8 Flash</div>
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
              Ask why an asset is at risk, or have Gemini draft an advisory with officer actions and a public message in
              English, Hindi and the local language. Nothing is issued until you approve it.
            </p>
            <div className="flex flex-col items-start gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => send(suggestion)}
                  className="rounded-2xl border border-[var(--line)] bg-[var(--surface-2)] px-3.5 py-2.5 text-left text-sm text-[var(--text-primary)] transition-colors hover:border-[var(--line-strong)] hover:bg-[var(--surface-3)]"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={clsx(
              "flex flex-col gap-2 text-sm",
              message.role === "user" && "ml-10 self-end rounded-2xl rounded-br-md bg-[var(--surface-3)] px-3.5 py-2.5",
            )}
          >
            {message.parts.map((part, index) => {
              switch (part.type) {
                case "text":
                  return (
                    <p key={index} className="whitespace-pre-wrap leading-relaxed text-[var(--text-primary)]">
                      {part.text}
                    </p>
                  );
                case "tool-searchAssets":
                  return (
                    <p key={part.toolCallId} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                      <Search className="size-3.5" />
                      {part.state === "output-available"
                        ? `Looked up ${part.output.total} matching assets${part.input.query ? ` for "${part.input.query}"` : ""}`
                        : part.state === "output-error"
                          ? `Asset lookup failed: ${part.errorText}`
                          : "Looking up assets…"}
                    </p>
                  );
                case "tool-issueAdvisory":
                  if (part.state === "input-streaming" || part.state === "input-available") {
                    return (
                      <p key={part.toolCallId} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                        <LoaderCircle className="size-3.5 animate-spin" /> Drafting advisory…
                      </p>
                    );
                  }
                  if (part.state === "output-error") {
                    return (
                      <p key={part.toolCallId} className="text-xs text-red-300">
                        Issuing failed: {part.errorText}
                      </p>
                    );
                  }
                  return (
                    <AdvisoryCard
                      key={part.toolCallId}
                      advisory={part.input}
                      onSelectAsset={onSelectAsset}
                      decision={
                        part.state === "approval-requested"
                          ? {
                              state: "pending",
                              onDecide: (approved) =>
                                addToolApprovalResponse({
                                  id: part.approval.id,
                                  approved,
                                  reason: approved ? undefined : "Rejected by the officer",
                                }),
                            }
                          : part.state === "output-available"
                            ? { state: "issued", issued: part.output }
                            : part.state === "output-denied"
                              ? { state: "rejected" }
                              : { state: "deciding" }
                      }
                    />
                  );
                default:
                  return null;
              }
            })}
          </div>
        ))}
        {status === "submitted" && (
          <LoaderCircle className="size-4 animate-spin text-[var(--text-muted)]" aria-label="Thinking" />
        )}
        {error && <p className="text-xs text-red-300">Something went wrong: {error.message}</p>}
        <div ref={end} />
      </div>

      <form onSubmit={submit} className="flex items-end gap-2 border-t border-[var(--line)] p-3">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) submit(event);
          }}
          rows={2}
          maxLength={2000}
          placeholder="Ask the duty analyst…"
          aria-label="Message the duty analyst"
          className="min-h-0 flex-1 resize-none rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-2)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none"
        />
        {busy ? (
          <button
            type="button"
            onClick={() => void stop()}
            aria-label="Stop"
            className="btn-ghost grid size-10 place-items-center"
          >
            <Square className="size-3.5" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            aria-label="Send"
            className="btn-primary grid size-10 place-items-center disabled:opacity-40"
          >
            <ArrowUp className="size-4" />
          </button>
        )}
      </form>
    </div>
  );
}
