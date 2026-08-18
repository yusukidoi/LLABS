import Link from "next/link";
import { formatDuration, formatTime, listExecutions } from "@/lib/api";

const statusColors: Record<string, string> = {
  completed: "bg-emerald-500/20 text-emerald-300",
  running: "bg-blue-500/20 text-blue-300",
  failed: "bg-red-500/20 text-red-300",
  pending: "bg-slate-500/20 text-slate-300",
  waiting: "bg-amber-500/20 text-amber-300",
  cancelled: "bg-slate-500/20 text-slate-400",
};

export default async function HomePage() {
  let executions;
  try {
    executions = await listExecutions();
  } catch {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/40 p-6">
        <h1 className="text-xl font-semibold text-red-200">API unavailable</h1>
        <p className="mt-2 text-sm text-red-300/80">
          Start the stack with <code className="rounded bg-slate-800 px-1">docker compose up</code>
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Executions</h1>
        <p className="mt-1 text-sm text-slate-400">
          Agent workflow runs with normalized state and retry visibility
        </p>
      </div>

      {executions.length === 0 ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
          No executions yet. Run{" "}
          <code className="rounded bg-slate-800 px-1 text-slate-200">
            python scripts/simulate_document_review.py
          </code>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Execution ID</th>
                <th className="px-4 py-3 font-medium">Workflow</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Started</th>
                <th className="px-4 py-3 font-medium">Duration</th>
                <th className="px-4 py-3 font-medium">Retries</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-slate-900/30">
              {executions.map((ex) => (
                <tr key={ex.id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-mono text-xs">
                    <Link href={`/executions/${ex.id}`} className="text-blue-400 hover:underline">
                      {ex.id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="px-4 py-3">{ex.workflow_name}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        statusColors[ex.status] || statusColors.pending
                      }`}
                    >
                      {ex.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{formatTime(ex.started_at)}</td>
                  <td className="px-4 py-3">{formatDuration(ex.duration_ms)}</td>
                  <td className="px-4 py-3">
                    {ex.retry_count > 0 ? (
                      <span className="font-medium text-amber-400">{ex.retry_count}</span>
                    ) : (
                      <span className="text-slate-500">0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
