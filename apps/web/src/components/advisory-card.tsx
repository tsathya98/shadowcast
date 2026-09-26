"use client";

import { clsx } from "clsx";
import { Check, Download, X } from "lucide-react";
import { useState } from "react";

import { type Advisory, type Language, LANGUAGES } from "@/lib/advisory";
import { utcAndIst } from "@/lib/format";

export interface IssuedAdvisory {
  advisoryId: string;
  sent: string;
  capXml: string;
}

type Decision =
  | { state: "pending"; onDecide: (approved: boolean) => void }
  | { state: "deciding" }
  | { state: "issued"; issued: IssuedAdvisory }
  | { state: "rejected" };

interface AdvisoryCardProps {
  advisory: Advisory;
  decision: Decision;
  onSelectAsset: (assetId: string) => void;
}

/** A drafted advisory for the officer: officer actions, the public message per language, and the approval gate. */
export function AdvisoryCard({ advisory, decision, onSelectAsset }: AdvisoryCardProps) {
  const [language, setLanguage] = useState<Language>(advisory.infos.at(-1)?.language ?? "en");
  const info = advisory.infos.find((i) => i.language === language) ?? advisory.infos[0];

  return (
    <article className="rounded-xl border border-white/10 bg-[var(--surface-2)] p-3 text-sm">
      <header className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            Draft advisory · CAP 1.2 exercise
          </div>
          <h3 className="font-medium text-[var(--text-primary)]">{advisory.event}</h3>
        </div>
        <span className="shrink-0 rounded-md bg-white/10 px-2 py-0.5 text-xs text-[var(--text-primary)]">
          {advisory.responseType}
        </span>
      </header>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        {advisory.severity} · {advisory.urgency} · {advisory.certainty} · {advisory.areas.join(", ")}
      </p>
      <p className="text-xs text-[var(--text-secondary)]">
        From {utcAndIst(advisory.onset)} until {utcAndIst(advisory.expires)}
      </p>

      {advisory.actions.length > 0 && (
        <section className="mt-3">
          <h4 className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Officer actions</h4>
          <ol className="mt-1 space-y-1">
            {advisory.actions.map((action, i) => (
              <li key={`${action.assetId}-${i}`} className="text-[var(--text-secondary)]">
                <button
                  type="button"
                  onClick={() => onSelectAsset(action.assetId)}
                  className="font-medium text-[var(--text-primary)] underline decoration-white/20 underline-offset-2 hover:decoration-white/60"
                >
                  {action.assetName}
                </button>
                : {action.action}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="mt-3">
        <div className="flex gap-1" role="tablist" aria-label="Advisory language">
          {advisory.infos.map((i) => (
            <button
              key={i.language}
              type="button"
              role="tab"
              aria-selected={i.language === info.language}
              onClick={() => setLanguage(i.language)}
              className={clsx(
                "rounded-md px-2 py-0.5 text-xs",
                i.language === info.language
                  ? "bg-white/15 text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
            >
              {LANGUAGES[i.language].label}
            </button>
          ))}
        </div>
        <div className="mt-2 space-y-1.5" lang={LANGUAGES[info.language].cap}>
          <p className="font-medium text-[var(--text-primary)]">{info.headline}</p>
          <p className="text-[var(--text-secondary)]">{info.description}</p>
          <p className="text-[var(--text-primary)]">{info.instruction}</p>
        </div>
        {decision.state === "issued" && (
          <audio
            key={info.language}
            controls
            preload="none"
            className="mt-2 h-8 w-full"
            src={`/api/advisories/${decision.issued.advisoryId}/audio?lang=${info.language}`}
            aria-label={`Listen in ${LANGUAGES[info.language].label}`}
          />
        )}
      </section>

      <footer className="mt-3 border-t border-white/10 pt-3">
        {decision.state === "pending" && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => decision.onDecide(true)}
              className="flex items-center gap-1.5 rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white hover:brightness-110"
            >
              <Check className="size-4" /> Approve and issue
            </button>
            <button
              type="button"
              onClick={() => decision.onDecide(false)}
              className="flex items-center gap-1.5 rounded-md bg-white/10 px-3 py-1.5 text-sm text-[var(--text-primary)] hover:bg-white/20"
            >
              <X className="size-4" /> Reject
            </button>
          </div>
        )}
        {decision.state === "deciding" && <p className="text-xs text-[var(--text-secondary)]">Recording decision…</p>}
        {decision.state === "rejected" && (
          <p className="text-xs text-[var(--text-secondary)]">
            Rejected by the officer. Not issued; logged in the audit trail.
          </p>
        )}
        {decision.state === "issued" && (
          <div className="flex items-center justify-between gap-2 text-xs text-[var(--text-secondary)]">
            <span>Approved and issued {utcAndIst(decision.issued.sent)} · logged in the audit trail</span>
            <a
              href={`data:application/xml;charset=utf-8,${encodeURIComponent(decision.issued.capXml)}`}
              download={`${decision.issued.advisoryId}.cap.xml`}
              className="flex shrink-0 items-center gap-1 text-[var(--text-primary)] hover:underline"
            >
              <Download className="size-3.5" /> CAP XML
            </a>
          </div>
        )}
      </footer>
    </article>
  );
}
