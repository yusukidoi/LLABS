"use client";

import { useState } from "react";
import type { Attempt, RawEvent, Step } from "@/lib/api";

function attemptLabel(attempt: Attempt): string {
  if (attempt.status === "failed" && attempt.error_type === "timeout") return "timeout";
  if (attempt.status === "succeeded" && attempt.metadata?.decision === "accepted") return "accepted";
  if (attempt.status === "succeeded") return "success";
  if (attempt.status === "failed") return attempt.error_type || "failed";
  if (attempt.status === "running") return "running";
  return attempt.status;
}

function attemptColor(attempt: Attempt): string {
  if (attempt.status === "succeeded") return "border-emerald-500/50 bg-emerald-500/10 text-emerald-300";
  if (attempt.status === "failed") return "border-red-500/50 bg-red-500/10 text-red-300";
  if (attempt.status === "running") return "border-amber-500/50 bg-amber-500/10 text-amber-300";
  return "border-slate-600 bg-slate-800/50 text-slate-300";
}

function stepBorderColor(step: Step): string {
  if (step.status === "completed") return "border-emerald-600";
  if (step.status === "failed") return "border-red-600";
  if (step.status === "waiting") return "border-amber-600";
  return "border-slate-600";
}

export function Timeline({ steps }: { steps: Step[] }) {
  return (
    <div className="relative space-y-0">
      <div className="absolute bottom-0 left-4 top-0 w-px bg-slate-700" />
      {steps.map((step) => (
        <div key={step.id} className="relative pb-8 pl-10">
          <div
            className={`absolute left-2.5 top-1 h-3 w-3 rounded-full border-2 bg-slate-950 ${stepBorderColor(step)}`}
          />
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-slate-100">{step.name}</h3>
              <span className="text-xs text-slate-500">{step.step_type}</span>
            </div>

            {step.attempts.length === 0 ? (
              <p className="mt-2 text-sm text-slate-400">No attempts recorded</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {step.attempts.map((attempt) => (
                  <li
                    key={attempt.id}
                    className={`rounded border px-3 py-2 text-sm ${attemptColor(attempt)}`}
                  >
                    <span className="font-medium">attempt {attempt.attempt_number}:</span>{" "}
                    {attemptLabel(attempt)}
                    {attempt.error_message && (
                      <span className="mt-1 block text-xs opacity-80">{attempt.error_message}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {step.attempts.length > 1 && (
              <p className="mt-2 text-xs text-amber-400/90">
                ↳ retry visible: {step.attempts.length - 1} extra attempt
                {step.attempts.length - 1 !== 1 ? "s" : ""}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function RawEventsPanel({ events }: { events: RawEvent[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-8 rounded-lg border border-slate-800 bg-slate-900/40">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-slate-800/40"
      >
        <span>Raw events ({events.length})</span>
        <span className="text-slate-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="max-h-96 overflow-auto border-t border-slate-800 px-4 py-3">
          <pre className="text-xs leading-relaxed text-slate-300">
            {JSON.stringify(events, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
