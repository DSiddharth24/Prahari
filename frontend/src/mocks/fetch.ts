import type { AlertStatus, ReportFields, Settings } from '../lib/types';
import {
  alerts,
  audit,
  caseAction,
  caseById,
  cases,
  createCaseReport,
  dashboard,
  ingestAlerts,
  loadDemo,
  markReportSubmitted,
  reportById,
  resetDemo,
  restoreAlert,
  settings,
  updateDetectedAt,
  updateReport,
  updateSettings,
} from './store';

let originalFetch: typeof fetch | undefined;

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const error = (detail: string, status = 400) => json({ detail }, status);

async function handleMockRequest(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const requestUrl = typeof input === 'string'
    ? input
    : input instanceof URL
      ? input.href
      : input.url;
  const url = new URL(requestUrl, window.location.origin);
  const path = url.pathname;
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  const bodyText = typeof init?.body === 'string' ? init.body : '{}';
  let body: Record<string, unknown> = {};
  try {
    body = JSON.parse(bodyText) as Record<string, unknown>;
  } catch {
    body = {};
  }

  if (method === 'GET' && path === '/api/health') return json({ status: 'ok' });
  if (method === 'POST' && path === '/api/demo/load') return json(loadDemo());
  if (method === 'POST' && path === '/api/demo/reset') {
    resetDemo();
    return json({ ok: true });
  }
  if (method === 'GET' && path === '/api/dashboard') return json(dashboard());
  if (method === 'GET' && path === '/api/cases') return json(cases(url.searchParams));
  if (path === '/api/alerts/ingest' && method === 'POST') {
    const form = init?.body instanceof FormData ? init.body : null;
    const file = form?.get('file');
    if (!(file instanceof File)) return error('Choose a JSON or CSV file to ingest.', 422);
    try {
      const contents = await file.text();
      const count = file.name.toLowerCase().endsWith('.csv')
        ? Math.max(0, contents.trim().split(/\r?\n/).length - 1)
        : Array.isArray(JSON.parse(contents))
          ? (JSON.parse(contents) as unknown[]).length
          : 1;
      return json(ingestAlerts(count, file.name));
    } catch {
      return error('The uploaded file is not valid JSON or CSV.', 422);
    }
  }
  if (method === 'GET' && path === '/api/alerts') {
    const status = url.searchParams.get('status') as AlertStatus | null;
    return json(alerts(status ?? undefined));
  }
  if (path === '/api/audit/export' && method === 'GET') {
    const format = url.searchParams.get('format');
    const events = audit(new URLSearchParams({ limit: '10000' }));
    const content = format === 'json'
      ? JSON.stringify(events, null, 2)
      : [
        'timestamp,actor,action,target_type,target_id,details',
        ...events.map((event) => [
          event.timestamp,
          event.actor,
          event.action,
          event.target_type ?? '',
          event.target_id ?? '',
          JSON.stringify(event.details ?? ''),
        ].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')),
      ].join('\r\n');
    return new Response(content, {
      headers: { 'Content-Type': format === 'json' ? 'application/json' : 'text/csv' },
    });
  }
  if (method === 'GET' && path === '/api/audit') return json(audit(url.searchParams));
  if (method === 'GET' && path === '/api/settings') return json(settings());
  if (method === 'PUT' && path === '/api/settings') {
    try {
      return json(updateSettings({
        settings: body.settings as Partial<Settings> | undefined,
        rules_yaml: body.rules_yaml as string | undefined,
      }));
    } catch (reason) {
      return error(reason instanceof Error ? reason.message : 'Settings could not be saved.', 400);
    }
  }

  const caseActionMatch = path.match(/^\/api\/cases\/(\d+)\/action$/);
  if (method === 'POST' && caseActionMatch) {
    const action = body.action;
    const note = typeof body.note === 'string' ? body.note.trim() : '';
    if (!note) return error('A note is required for this case action.', 422);
    if (!['confirm', 'dismiss', 'escalate'].includes(String(action))) return error('Choose a valid case action.', 422);
    const result = caseAction(Number(caseActionMatch[1]), action as 'confirm' | 'dismiss' | 'escalate', note);
    return result ? json(result) : error('Case not found.', 404);
  }
  const detectedAtMatch = path.match(/^\/api\/cases\/(\d+)\/detected_at$/);
  if (method === 'PATCH' && detectedAtMatch) {
    const detectedAt = body.detected_at;
    const reason = typeof body.reason === 'string' ? body.reason.trim() : '';
    if (typeof detectedAt !== 'string' || !detectedAt || !reason) {
      return error('Detected-at time and adjustment reason are required.', 422);
    }
    const result = updateDetectedAt(Number(detectedAtMatch[1]), detectedAt, reason);
    return result ? json(result) : error('Case not found.', 404);
  }
  const caseReportMatch = path.match(/^\/api\/cases\/(\d+)\/report$/);
  if (method === 'POST' && caseReportMatch) {
    const result = createCaseReport(Number(caseReportMatch[1]));
    return result ? json(result) : error('Case not found.', 404);
  }
  const caseMatch = path.match(/^\/api\/cases\/(\d+)$/);
  if (method === 'GET' && caseMatch) {
    const result = caseById(Number(caseMatch[1]));
    return result ? json(result) : error('Case not found.', 404);
  }
  const reportPdfMatch = path.match(/^\/api\/reports\/(\d+)\/pdf$/);
  if (method === 'GET' && reportPdfMatch) {
    const report = reportById(Number(reportPdfMatch[1]));
    if (!report) return error('Report not found.', 404);
    const pdfText = [
      'Prahari CERT-In report draft',
      `Report ${report.id}, case ${report.case_id}, version ${report.version}`,
      'DRAFT, for analyst review.',
      report.fields.organisation_name,
      report.fields.incident_type,
      report.fields.description,
    ].filter(Boolean);
    const escapePdf = (line: string) => line.replace(/[\\()]/g, '\\$&').replace(/[^\x20-\x7E]/g, '?');
    const commands = pdfText
      .map((line, index) => `1 0 0 1 54 ${740 - index * 24} Tm (${escapePdf(line)}) Tj`)
      .join('\n');
    const stream = `BT\n/F1 12 Tf\n${commands}\nET`;
    const objects = [
      '<< /Type /Catalog /Pages 2 0 R >>',
      '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
      '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
      `<< /Length ${new TextEncoder().encode(stream).length} >>\nstream\n${stream}\nendstream`,
    ];
    let pdf = '%PDF-1.4\n';
    const offsets = [0];
    objects.forEach((object, index) => {
      offsets.push(new TextEncoder().encode(pdf).length);
      pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
    });
    const xrefOffset = new TextEncoder().encode(pdf).length;
    pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
    offsets.slice(1).forEach((offset) => {
      pdf += `${String(offset).padStart(10, '0')} 00000 n \n`;
    });
    pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
    return new Response(new Blob([pdf], { type: 'application/pdf' }), {
      headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': `attachment; filename="prahari-report-${reportPdfMatch[1]}.pdf"` },
    });
  }
  const reportSubmittedMatch = path.match(/^\/api\/reports\/(\d+)\/submitted$/);
  if (method === 'POST' && reportSubmittedMatch) {
    const ref = typeof body.reference_number === 'string' ? body.reference_number.trim() : '';
    const name = typeof body.submitted_by === 'string' ? body.submitted_by.trim() : '';
    if (!ref || !name) return error('Reference number and submitted-by name are required.', 422);
    const result = markReportSubmitted(Number(reportSubmittedMatch[1]), ref, name);
    return result ? json(result) : error('Report not found.', 404);
  }
  const reportMatch = path.match(/^\/api\/reports\/(\d+)$/);
  if (reportMatch && method === 'GET') {
    const result = reportById(Number(reportMatch[1]));
    return result ? json(result) : error('Report not found.', 404);
  }
  if (reportMatch && method === 'PUT') {
    const fields = body.fields;
    if (fields && (typeof fields !== 'object' || Array.isArray(fields))) return error('Report fields must be an object.', 422);
    const result = updateReport(Number(reportMatch[1]), {
      fields: fields as ReportFields | undefined,
      narrative: body.narrative as string | undefined,
      incident_type: body.incident_type as string | undefined,
    });
    return result ? json(result) : error('Report not found.', 404);
  }
  const restoreMatch = path.match(/^\/api\/alerts\/(\d+)\/restore$/);
  if (method === 'POST' && restoreMatch) {
    return restoreAlert(Number(restoreMatch[1])) ? json({ ok: true }) : error('Alert not found.', 404);
  }
  return error(`No mock endpoint for ${method} ${path}.`, 404);
}

export function installMockApi(): void {
  if (originalFetch) return;
  originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
    if (new URL(url, window.location.origin).pathname.startsWith('/api/')) {
      return handleMockRequest(input, init);
    }
    return originalFetch!(input, init);
  };
}

export function restoreFetch(): void {
  if (originalFetch) {
    globalThis.fetch = originalFetch;
    originalFetch = undefined;
  }
}

export function isMockInstalled(): boolean {
  return Boolean(originalFetch);
}


