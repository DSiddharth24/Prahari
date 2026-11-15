/**
 * API client for the Prahari backend.
 * Uses fetch and throws ApiError (with the server's `detail`) on non-2xx responses.
 */
import type {
  Alert,
  AlertStatus,
  AuditEvent,
  CaseDetail,
  CaseListItem,
  CaseStatus,
  Dashboard,
  IngestResult,
  Pattern,
  PipelineResult,
  Report,
  ReportFields,
  Settings,
  Severity,
} from './types';

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export type ReportWithHistory = Report & { history: Report[] };
export type SettingsResponse = { settings: Settings; rules_yaml: string };
export type LoadResult = { ingest: IngestResult; pipeline: PipelineResult };

function baseUrl(): string {
  const base = import.meta.env.VITE_API_BASE as string | undefined;
  return base && base.length > 0 ? base : 'http://localhost:8000';
}

async function throwIfNotOk(resp: Response): Promise<void> {
  if (resp.ok) return;
  let detail = resp.statusText || 'Request failed';
  try {
    const body: unknown = await resp.json();
    if (
      body &&
      typeof body === 'object' &&
      'detail' in body &&
      typeof (body as { detail: unknown }).detail === 'string'
    ) {
      detail = (body as { detail: string }).detail;
    }
  } catch (e) {
    void e; // body was not JSON; keep statusText
  }
  throw new ApiError(resp.status, detail);
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  await throwIfNotOk(resp);
  const text = await resp.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

/** GET /api/health */
export const getHealth = () => request<{ status: string }>(`${baseUrl()}/api/health`);

/** POST /api/demo/load */
export const loadDemo = () => request<LoadResult>(`${baseUrl()}/api/demo/load`, { method: 'POST' });

/** POST /api/demo/reset */
export const resetDemo = () => request<unknown>(`${baseUrl()}/api/demo/reset`, { method: 'POST' });

/** POST /api/alerts/ingest (multipart; the browser sets the Content-Type boundary) */
export const ingestFile = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return request<LoadResult>(`${baseUrl()}/api/alerts/ingest`, { method: 'POST', body: form });
};

/** GET /api/dashboard */
export const getDashboard = () => request<Dashboard>(`${baseUrl()}/api/dashboard`);

/** GET /api/cases */
export const getCases = (params?: { severity?: Severity; status?: CaseStatus; pattern?: Pattern }) => {
  const qs = new URLSearchParams();
  if (params?.severity) qs.append('severity', params.severity);
  if (params?.status) qs.append('status', params.status);
  if (params?.pattern) qs.append('pattern', params.pattern);
  const q = qs.toString();
  return request<CaseListItem[]>(`${baseUrl()}/api/cases${q ? `?${q}` : ''}`);
};

/** GET /api/cases/{id} */
export const getCase = (id: number) => request<CaseDetail>(`${baseUrl()}/api/cases/${id}`);

/** POST /api/cases/{id}/action */
export const postCaseAction = (
  id: number,
  payload: { action: 'confirm' | 'dismiss' | 'escalate'; note: string; actor?: string },
) => request<CaseDetail>(`${baseUrl()}/api/cases/${id}/action`, jsonInit('POST', payload));

/** PATCH /api/cases/{id}/detected_at */
export const patchCaseDetectedAt = (id: number, payload: { detected_at: string; reason: string }) =>
  request<CaseDetail>(`${baseUrl()}/api/cases/${id}/detected_at`, jsonInit('PATCH', payload));

/** POST /api/cases/{id}/report */
export const postCaseReport = (id: number) =>
  request<Report>(`${baseUrl()}/api/cases/${id}/report`, { method: 'POST' });

/** GET /api/reports/{id}  ->  Report & { history: Report[] } */
export const getReport = (id: number) => request<ReportWithHistory>(`${baseUrl()}/api/reports/${id}`);

/** PUT /api/reports/{id} */
export const putReport = (
  id: number,
  payload: { fields?: ReportFields; narrative?: string; incident_type?: string },
) => request<Report>(`${baseUrl()}/api/reports/${id}`, jsonInit('PUT', payload));

/** GET /api/reports/{id}/pdf (use as a download link) */
export const getReportPdfUrl = (id: number) => `${baseUrl()}/api/reports/${id}/pdf`;

/** POST /api/reports/{id}/submitted */
export const postReportSubmitted = (
  id: number,
  payload: { reference_number: string; submitted_by: string },
) => request<Report>(`${baseUrl()}/api/reports/${id}/submitted`, jsonInit('POST', payload));

/** GET /api/alerts */
export const getAlerts = (status?: AlertStatus) =>
  request<Alert[]>(`${baseUrl()}/api/alerts${status ? `?status=${status}` : ''}`);

/** POST /api/alerts/{id}/restore */
export const restoreAlert = (id: number) =>
  request<unknown>(`${baseUrl()}/api/alerts/${id}/restore`, { method: 'POST' });

/** GET /api/audit */
export const getAudit = (params?: {
  action?: string;
  target_type?: string;
  target_id?: string;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.action) qs.append('action', params.action);
  if (params?.target_type) qs.append('target_type', params.target_type);
  if (params?.target_id) qs.append('target_id', params.target_id);
  if (params?.limit) qs.append('limit', String(params.limit));
  const q = qs.toString();
  return request<AuditEvent[]>(`${baseUrl()}/api/audit${q ? `?${q}` : ''}`);
};

/** GET /api/audit/export. Returns a Blob for both formats; never JSON-parsed. */
export const exportAudit = async (
  format: 'csv' | 'json',
): Promise<{ blob: Blob; filename: string }> => {
  const resp = await fetch(`${baseUrl()}/api/audit/export?format=${format}`);
  await throwIfNotOk(resp);
  return { blob: await resp.blob(), filename: `prahari-audit.${format}` };
};

/** GET /api/settings */
export const getSettings = () => request<SettingsResponse>(`${baseUrl()}/api/settings`);

/** PUT /api/settings  (body is {settings?, rules_yaml?}) */
export const putSettings = (payload: { settings?: Partial<Settings>; rules_yaml?: string }) =>
  request<SettingsResponse>(`${baseUrl()}/api/settings`, jsonInit('PUT', payload));