import Link from "next/link";
import { RawEventsPanel, Timeline } from "@/components/Timeline";
import {
  formatDuration,
  formatTime,
  getEvaluation,
  getEvents,
  getExecution,
  getTimeline,
} from "@/lib/api";

export default async function ExecutionDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;

  let execution, timeline, evaluation, events;
  try {
    [execution, timeline, evaluation, events] = await Promise.all([
      getExecution(id),
      getTimeline(id),
      getEvaluation(id),
      getEvents(id),
    ]);
  } catch {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/40 p-6">
        <p className="text-red-200">Execution not found or API unavailable.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-blue-400 hover:underline">
          ← Back to list
        </Link>
      </div>
    );
  }

  return (
    <div>
      <Link href="/" className="text-sm text-blue-400 hover:underline">
        ← Executions
      </Link>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{execution.workflow_name}</h1>
          <p className="mt-1 font-mono text-xs text-slate-500">{execution.id}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-sm font-medium ${
            execution.status === "completed"
              ? "bg-emerald-500/20 text-emerald-300"
              : execution.status === "failed"
                ? "bg-red-500/20 text-red-300"
                : "bg-slate-500/20 text-slate-300"
          }`}
        >
          {execution.status}
        </span>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Duration" value={formatDuration(evaluation.total_duration_ms)} />
        <Stat label="Retries" value={String(evaluation.retry_count)} highlight={evaluation.retry_count > 0} />
        <Stat label="Steps / Attempts" value={`${evaluation.total_steps} / ${evaluation.total_attempts}`} />
        <Stat label="Human review" value={evaluation.human_review_status} />
      </div>

      <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <h2 className="text-sm font-medium text-slate-400">Evaluation</h2>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <Row label="Successful" value={evaluation.successful ? "yes" : "no"} />
          <Row label="Final outcome" value={evaluation.final_outcome} />
          <Row label="Failed steps" value={String(evaluation.failed_step_count)} />
          <Row
            label="Reliability score"
            value={`${(evaluation.reliability_score * 100).toFixed(0)}% (illustrative)`}
          />
          <Row label="Started" value={formatTime(execution.started_at)} />
          <Row label="Completed" value={formatTime(execution.completed_at)} />
        </dl>
      </div>

      <div className="mt-8">
        <h2 className="mb-4 text-lg font-medium">Execution timeline</h2>
        <Timeline steps={timeline.steps} />
      </div>

      <RawEventsPanel events={events} />
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${highlight ? "text-amber-400" : ""}`}>{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-800/60 py-1">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
