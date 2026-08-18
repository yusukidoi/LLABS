const API_URL =
  typeof window === "undefined"
    ? process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ExecutionListItem {
  id: string;
  tenant_id: string;
  workflow_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  duration_ms: number | null;
  retry_count: number;
}

export interface Attempt {
  id: string;
  attempt_number: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_type: string | null;
  error_message: string | null;
  metadata: Record<string, unknown> | null;
}

export interface Step {
  id: string;
  name: string;
  step_type: string;
  sequence_number: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  attempts: Attempt[];
}

export interface ExecutionDetail {
  id: string;
  workflow_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  step_count: number;
  attempt_count: number;
  retry_count: number;
}

export interface Evaluation {
  execution_id: string;
  successful: boolean;
  total_steps: number;
  total_attempts: number;
  retry_count: number;
  failed_step_count: number;
  total_duration_ms: number | null;
  human_review_status: string;
  final_outcome: string;
  reliability_score: number;
}

export interface RawEvent {
  id: string;
  event_type: string;
  timestamp: string;
  payload: Record<string, unknown> | null;
  step_id: string | null;
  attempt_id: string | null;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json();
}

export function listExecutions(): Promise<ExecutionListItem[]> {
  return fetchApi("/api/executions");
}

export function getExecution(id: string): Promise<ExecutionDetail> {
  return fetchApi(`/api/executions/${id}`);
}

export function getTimeline(id: string): Promise<{ steps: Step[] }> {
  return fetchApi(`/api/executions/${id}/timeline`);
}

export function getEvaluation(id: string): Promise<Evaluation> {
  return fetchApi(`/api/executions/${id}/evaluation`);
}

export function getEvents(id: string): Promise<RawEvent[]> {
  return fetchApi(`/api/executions/${id}/events`);
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}
