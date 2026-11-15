import type {
  Alert,
  AlertStatus,
  AuditEvent,
  CaseDetail,
  CaseListItem,
  CaseStatus,
  Dashboard,
  Report,
  ReportFields,
  Settings,
  Source,
} from '../lib/types';
import type { LoadResult, ReportWithHistory, SettingsResponse } from '../lib/api';
import { formatIST } from '../lib/time';

type Store = {
  loaded: boolean;
  ingestedAdditional: number;
  dashboard: Dashboard;
  cases: CaseDetail[];
  alerts: Alert[];
  reports: Map<number, Report>;
  reportHistory: Map<number, Report[]>;
  audit: AuditEvent[];
  settings: Settings;
  rulesYaml: string;
};

const emptyDashboard = (): Dashboard => ({
  funnel: { ingested: 0, suppressed: 0, merged: 0, in_cases: 0, cases: 0 },
  time_saved_minutes: 0,
  time_saved_note: 'No alerts have been processed yet.',
  cases_by_severity: { low: 0, medium: 0, high: 0, critical: 0 },
  open_cases: [],
});

const defaultSettings = (): Settings => ({
  correlation_window_hours: 6,
  dedupe_window_minutes: 10,
  minutes_saved_per_alert: 2,
  critical_assets: ['payments-db-01', 'broker-portal', 'identity-prod'],
  outbound_bytes_threshold: 100000000,
});

export const initialRulesYaml = `rules:
  - name: routine_health_check
    category: informational
    description: Suppress known daily health checks from managed devices
  - name: repeated_auth_failure
    category: failed_login
    merge_within_minutes: 10
`;

const iso = (date: Date) => date.toISOString();
const ago = (minutes: number) => iso(new Date(Date.now() - minutes * 60_000));
const after = (hours: number, minutes = 0) => iso(new Date(Date.now() + (hours * 60 + minutes) * 60_000));

function makeAlert(
  id: number,
  source: Source,
  timestamp: string,
  title: string,
  details: Partial<Alert> = {},
): Alert {
  const alert: Alert = {
    id,
    source,
    source_alert_id: `${source.toUpperCase()}-${id}`,
    timestamp,
    title,
    description: null,
    severity_raw: 'high',
    category: 'suspicious_login',
    user: null,
    host: null,
    src_ip: null,
    dst_ip: null,
    file: null,
    process: null,
    raw: null,
    status: 'in_case',
    suppression_reason: null,
    duplicate_of: null,
    duplicate_count: 0,
    ...details,
  };
  alert.raw ??= JSON.stringify({
    source: alert.source,
    source_alert_id: alert.source_alert_id,
    timestamp: alert.timestamp,
    title: alert.title,
    user: alert.user,
    host: alert.host,
    src_ip: alert.src_ip,
    dst_ip: alert.dst_ip,
    category: alert.category,
    severity: alert.severity_raw,
  }, null, 2);
  return alert;
}

function makeHeroCase(): CaseDetail {
  const timeline = [
    makeAlert(101, 'identity_provider', ago(62), 'Sign-in from an unfamiliar location', {
      user: 'ananya.rao@northstar-finance.in',
      src_ip: '198.51.100.27',
      severity_raw: 'high',
      category: 'suspicious_login',
      description: 'Successful sign-in followed repeated MFA prompts from a new network.',
    }),
    makeAlert(102, 'dlp', ago(49), 'Customer export attempted outside business hours', {
      user: 'ananya.rao@northstar-finance.in',
      host: 'finance-ws-044',
      file: 'customer_accounts_2026-11.csv',
      severity_raw: 'critical',
      category: 'data_exfiltration',
      description: 'A large customer-data export was blocked by the endpoint policy.',
    }),
    makeAlert(103, 'endpoint_av', ago(38), 'Unusual browser child process observed', {
      user: 'ananya.rao@northstar-finance.in',
      host: 'finance-ws-044',
      process: 'powershell.exe',
      severity_raw: 'high',
      category: 'malware',
      description: 'The browser launched a script interpreter shortly after the sign-in.',
    }),
    makeAlert(104, 'firewall', ago(26), 'Outbound transfer to a new external host', {
      user: 'ananya.rao@northstar-finance.in',
      host: 'finance-ws-044',
      src_ip: '10.24.8.44',
      dst_ip: '203.0.113.71',
      severity_raw: 'critical',
      category: 'data_exfiltration',
      description: 'The firewall recorded an unusual outbound connection from the affected workstation.',
    }),
  ];
  return {
    id: 1001,
    title: 'Account takeover followed by customer-data export',
    score: 88,
    severity: 'critical',
    status: 'open',
    pattern: 'account_takeover_then_exfiltration',
    sources_count: 4,
    first_alert_at: timeline[0].timestamp,
    detected_at: timeline[0].timestamp,
    deadline_at: after(5, 12),
    seconds_remaining: 5 * 3600 + 12 * 60,
    countdown_state: 'green',
    timeline,
    summary:
      'A successful sign-in from a new location was followed by an attempted customer-data export and an unusual outbound connection from the same workstation. The evidence spans identity, data-loss, endpoint and firewall alerts.',
    summary_source: 'template',
    recommended_actions: [
      'Verify the sign-in with the account holder and review active sessions.',
      'Preserve the workstation and firewall evidence before containment.',
      'Review the blocked export and confirm whether customer records left the environment.',
    ],
    score_breakdown: [
      { factor: 'High-impact alert', points: 28, explanation: 'A critical data-loss alert is present.' },
      { factor: 'Distinct evidence sources', points: 24, explanation: 'Four separate tools support the same sequence.' },
      { factor: 'Account and host overlap', points: 18, explanation: 'The alerts share an account and affected workstation.' },
      { factor: 'Time proximity', points: 18, explanation: 'The alerts occurred within a short window.' },
    ],
    entities: {
      users: ['ananya.rao@northstar-finance.in'],
      hosts: ['finance-ws-044'],
      ips: ['198.51.100.27', '10.24.8.44', '203.0.113.71'],
    },
    report_id: null,
  };
}

function makeOtherCases(): CaseDetail[] {
  const phishing = makeAlert(201, 'email_security', ago(94), 'Credential lure reported by a finance analyst', {
    user: 'rohan.mehta@northstar-finance.in',
    severity_raw: 'high',
    category: 'phishing',
    description: 'A message imitated the internal payroll portal.',
  });
  const ransomware = [
    makeAlert(301, 'endpoint_av', ago(164), 'Rapid file changes on a shared workstation', {
      user: 'ops.service@northstar-finance.in',
      host: 'ops-ws-019',
      process: 'archive_sync.exe',
      severity_raw: 'critical',
      category: 'ransomware_behaviour',
    }),
    makeAlert(302, 'cloud_audit', ago(151), 'Backup retention setting changed', {
      user: 'ops.service@northstar-finance.in',
      host: 'ops-ws-019',
      severity_raw: 'high',
      category: 'backup_activity',
    }),
  ];
  const medium = makeAlert(401, 'identity_provider', ago(33), 'Repeated access attempts to a dormant account', {
    user: 'vendor.audit@northstar-finance.in',
    src_ip: '192.0.2.83',
    severity_raw: 'medium',
    category: 'failed_login',
  });
  const cases: CaseDetail[] = [
    {
      id: 1002,
      title: 'Phishing message targeting the payroll team',
      score: 72,
      severity: 'high',
      status: 'open',
      pattern: 'phishing_to_compromise',
      sources_count: 1,
      first_alert_at: phishing.timestamp,
      detected_at: phishing.timestamp,
      deadline_at: after(2, 24),
      seconds_remaining: 2 * 3600 + 24 * 60,
      countdown_state: 'amber',
      timeline: [phishing],
      summary: 'A payroll-themed message was reported by an analyst. No credential use is linked in the available evidence yet.',
      summary_source: 'template',
      recommended_actions: ['Check mail delivery and click records.', 'Ask the recipient whether credentials were entered.'],
      score_breakdown: [
        { factor: 'High-severity report', points: 30, explanation: 'The message was reported as a credential lure.' },
        { factor: 'Known account context', points: 22, explanation: 'The recipient is a finance team member.' },
        { factor: 'Evidence completeness', points: 20, explanation: 'Email evidence is available; endpoint evidence is not linked.' },
      ],
      entities: { users: ['rohan.mehta@northstar-finance.in'], hosts: [], ips: [] },
      report_id: 1402,
    },
    {
      id: 1003,
      title: 'Ransomware-like file activity on operations workstation',
      score: 91,
      severity: 'critical',
      status: 'open',
      pattern: 'ransomware_behaviour',
      sources_count: 2,
      first_alert_at: ransomware[0].timestamp,
      detected_at: ransomware[0].timestamp,
      deadline_at: after(7, 5),
      seconds_remaining: 7 * 3600 + 5 * 60,
      countdown_state: 'green',
      timeline: ransomware,
      summary: 'Rapid file changes and a backup-retention change were recorded for the same operations account.',
      summary_source: 'template',
      recommended_actions: ['Preserve endpoint and cloud audit logs.', 'Check whether backup retention was restored.'],
      score_breakdown: [
        { factor: 'Critical endpoint alert', points: 35, explanation: 'The endpoint reported rapid file changes.' },
        { factor: 'Backup activity', points: 30, explanation: 'A cloud audit alert shows a retention change.' },
        { factor: 'Shared account and host', points: 26, explanation: 'Both alerts identify the same service account and host.' },
      ],
      entities: { users: ['ops.service@northstar-finance.in'], hosts: ['ops-ws-019'], ips: [] },
      report_id: null,
    },
    {
      id: 1004,
      title: 'Repeated sign-in attempts on a dormant vendor account',
      score: 48,
      severity: 'medium',
      status: 'open',
      pattern: 'recon_then_access',
      sources_count: 1,
      first_alert_at: medium.timestamp,
      detected_at: medium.timestamp,
      deadline_at: after(9, 10),
      seconds_remaining: 9 * 3600 + 10 * 60,
      countdown_state: 'green',
      timeline: [medium],
      summary: 'A dormant vendor account received repeated access attempts from an address not seen for this account.',
      summary_source: 'template',
      recommended_actions: ['Confirm the account is still required.', 'Review sign-in history for successful access.'],
      score_breakdown: [
        { factor: 'Repeated failures', points: 18, explanation: 'Several failed attempts occurred in a short period.' },
        { factor: 'Dormant account', points: 17, explanation: 'The account has not recently been active.' },
        { factor: 'No linked endpoint evidence', points: 13, explanation: 'No second tool has corroborated the activity.' },
      ],
      entities: { users: ['vendor.audit@northstar-finance.in'], hosts: [], ips: ['192.0.2.83'] },
      report_id: null,
    },
  ];
  cases[0].timeline = [phishing];
  return cases;
}

function makeReport(caseData: CaseDetail, id: number): Report {
  const first = caseData.timeline[0];
  const fields: ReportFields = {
    organisation_name: 'Northstar Finance Ltd.',
    reporter_name: 'Security Operations Analyst',
    reporter_role: 'Incident response',
    reporter_contact: 'security@example.invalid',
    incident_type: caseData.pattern === 'phishing_to_compromise' ? 'Phishing attempt' : 'Suspected cybersecurity incident',
    detected_at_ist: first ? formatIST(first.timestamp) : formatIST(iso(new Date())),
    detected_at_utc: first ? first.timestamp : iso(new Date()),
    first_activity_at_ist: first ? formatIST(first.timestamp) : formatIST(iso(new Date())),
    affected_systems: caseData.entities.hosts.join(', ') || 'Under review',
    description: caseData.summary ?? '',
    impact_assessment: 'Impact is being assessed. Verify affected users, systems and records before submission.',
    actions_taken: 'Alerts linked for analyst review. No external submission has been made.',
    evidence: caseData.timeline.map((alert) => ({
      alert_id: alert.id,
      source: alert.source,
      time: alert.timestamp,
      title: alert.title,
    })),
    logs_preserved: 'Identity, endpoint and network records are available in the linked evidence timeline.',
  };
  return {
    id,
    case_id: caseData.id,
    incident_type: fields.incident_type,
    fields,
    narrative: `${caseData.title}. ${caseData.summary ?? ''}\n\nThis draft is for analyst review. Verify all facts and required fields against the official CERT-In form.`,
    generated_at: iso(new Date()),
    status: 'draft',
    version: 1,
  };
}

function makeDroppedAlerts(): Alert[] {
  const reasons = [
    'Known maintenance scanner: rule routine_health_check',
    'Duplicate of a higher-fidelity alert within the dedupe window',
    'Low-priority activity with no matching case evidence',
    'Known internal health check from a managed device',
    'Repeated authentication failure merged with the first alert',
  ];
  const sources: Source[] = ['identity_provider', 'firewall', 'endpoint_av', 'cloud_audit', 'dlp', 'email_security'];
  return Array.from({ length: 30 }, (_, index) => {
    const id = 501 + index;
    const isSuppressed = index < 14;
    const isMerged = index >= 14 && index < 24;
    const status: AlertStatus = isSuppressed
      ? 'suppressed_benign'
      : isMerged
        ? 'merged_duplicate'
        : 'unlinked_low_priority';
    const source = sources[index % sources.length];
    return makeAlert(
      id,
      source,
      ago(20 + index * 6),
      isSuppressed ? 'Routine device health check' : isMerged ? 'Repeated authentication warning' : 'Low-priority access event',
      {
        status,
        severity_raw: isSuppressed ? 'low' : 'medium',
        category: isSuppressed ? 'informational' : 'failed_login',
        description: 'Sample alert retained for analyst review.',
        suppression_reason: reasons[index % reasons.length],
        duplicate_of: isMerged ? 101 + (index % 4) : null,
        duplicate_count: isMerged ? 2 + (index % 3) : 0,
      },
    );
  });
}

function makeAuditEvents(): AuditEvent[] {
  const actions = [
    'demo_loaded', 'case_viewed', 'alert_suppressed', 'duplicate_merged', 'report_generated',
    'settings_saved', 'evidence_linked', 'case_scored', 'low_priority_unlinked', 'audit_exported',
  ];
  return Array.from({ length: 19 }, (_, index) => ({
    id: index + 1,
    timestamp: ago(index * 9 + 2),
    actor: index % 4 === 0 ? 'analyst@northstar-finance.in' : 'prahari-demo',
    action: actions[index % actions.length],
    target_type: index % 3 === 0 ? 'case' : 'alert',
    target_id: String(index % 3 === 0 ? 1001 + (index % 4) : 501 + index),
    details: { note: 'Sample audit event for demo review.' },
  }));
}

export function createStore(): Store {
  return {
    loaded: false,
    ingestedAdditional: 0,
    dashboard: emptyDashboard(),
    cases: [],
    alerts: [],
    reports: new Map(),
    reportHistory: new Map(),
    audit: [],
    settings: defaultSettings(),
    rulesYaml: initialRulesYaml,
  };
}

export const store = createStore();

function listItem(caseData: CaseDetail): CaseListItem {
  const seconds = caseData.deadline_at
    ? Math.floor((new Date(caseData.deadline_at).getTime() - Date.now()) / 1000)
    : null;
  let state: CaseListItem['countdown_state'] = 'none';
  if (caseData.status !== 'dismissed' && caseData.status !== 'reported' && seconds !== null) {
    state = seconds <= 0 ? 'overdue' : seconds < 3600 ? 'red' : seconds <= 10800 ? 'amber' : 'green';
  }
  return { ...caseData, seconds_remaining: seconds, countdown_state: state };
}

function recordAudit(action: string, targetType: string, targetId: number, details: unknown): void {
  store.audit.unshift({
    id: store.audit.length ? Math.max(...store.audit.map((event) => event.id)) + 1 : 1,
    timestamp: iso(new Date()),
    actor: 'analyst@northstar-finance.in',
    action,
    target_type: targetType,
    target_id: String(targetId),
    details,
  });
}

function recalculateDashboard(): void {
  const baselineIngested = store.loaded ? 400 : 0;
  const suppressed = store.alerts.filter((alert) => alert.status === 'suppressed_benign').length;
  const merged = store.alerts.filter((alert) => alert.status === 'merged_duplicate').length;
  const severities = { low: 0, medium: 0, high: 0, critical: 0 };
  store.cases.forEach((caseData) => { severities[caseData.severity] += 1; });
  const ingested = baselineIngested + store.ingestedAdditional;
  const timeSaved = ingested * store.settings.minutes_saved_per_alert;
  store.dashboard = {
    funnel: {
      ingested,
      suppressed: store.loaded ? Math.max(0, 280 - (14 - suppressed)) : 0,
      merged: store.loaded ? Math.max(0, 60 - (10 - merged)) : 0,
      in_cases: store.loaded ? 40 : 0,
      cases: store.cases.length,
    },
    time_saved_minutes: timeSaved,
    time_saved_note: `Estimate: ${ingested.toLocaleString('en-IN')} alerts × ${store.settings.minutes_saved_per_alert} minutes per alert. This is a planning estimate, not measured analyst time.`,
    cases_by_severity: severities,
    open_cases: store.cases
      .filter((caseData) => !['dismissed', 'reported'].includes(caseData.status))
      .map(listItem),
  };
}

export function loadDemo(): LoadResult {
  store.loaded = true;
  store.ingestedAdditional = 0;
  const hero = makeHeroCase();
  store.cases = [hero, ...makeOtherCases()];
  store.alerts = [...hero.timeline, ...store.cases.slice(1).flatMap((caseData) => caseData.timeline), ...makeDroppedAlerts()];
  store.reports = new Map();
  store.reportHistory = new Map();
  store.audit = makeAuditEvents();
  const draft = makeReport(store.cases[1], 1402);
  store.reports.set(draft.id, draft);
  store.cases[1].report_id = draft.id;
  store.settings = defaultSettings();
  store.rulesYaml = initialRulesYaml;
  recalculateDashboard();
  recordAudit('demo_loaded', 'demo', 1, { cases: 4, alerts: 400 });
  return {
    ingest: { received: 400, new: 400, already_seen: 0 },
    pipeline: { suppressed: 280, merged: 60, in_cases: 40, cases_created: 4, unlinked_low_priority: 6 },
  };
}

export function resetDemo(): void {
  const fresh = createStore();
  Object.assign(store, fresh);
}

export function dashboard(): Dashboard {
  recalculateDashboard();
  return structuredClone(store.dashboard);
}

export function cases(params: URLSearchParams): CaseListItem[] {
  const severity = params.get('severity');
  const status = params.get('status');
  const pattern = params.get('pattern');
  return store.cases
    .filter((item) => (!severity || item.severity === severity)
      && (!status || item.status === status)
      && (!pattern || item.pattern === pattern))
    .map(listItem);
}

export function caseById(id: number): CaseDetail | undefined {
  const item = store.cases.find((entry) => entry.id === id);
  return item ? { ...listItem(item), ...structuredClone(item), ...listItem(item) } : undefined;
}

export function caseAction(
  id: number,
  action: 'confirm' | 'dismiss' | 'escalate',
  note: string,
): CaseDetail | undefined {
  const item = store.cases.find((entry) => entry.id === id);
  if (!item) return undefined;
  const status: Record<typeof action, CaseStatus> = {
    confirm: 'confirmed',
    dismiss: 'dismissed',
    escalate: 'escalated',
  };
  item.status = status[action];
  recordAudit(`case_${action}`, 'case', id, { note });
  recalculateDashboard();
  return caseById(id);
}

export function updateDetectedAt(id: number, detectedAt: string, reason: string): CaseDetail | undefined {
  const item = store.cases.find((entry) => entry.id === id);
  if (!item) return undefined;
  item.detected_at = detectedAt;
  item.deadline_at = iso(new Date(new Date(detectedAt).getTime() + 6 * 60 * 60_000));
  recordAudit('case_detected_at_adjusted', 'case', id, { detected_at: detectedAt, reason });
  recalculateDashboard();
  return caseById(id);
}

export function createCaseReport(id: number): Report | undefined {
  const item = store.cases.find((entry) => entry.id === id);
  if (!item) return undefined;
  if (item.report_id && store.reports.has(item.report_id)) return structuredClone(store.reports.get(item.report_id)!);
  const reportId = Math.max(1400, ...store.reports.keys()) + 1;
  const report = makeReport(item, reportId);
  store.reports.set(report.id, report);
  store.reportHistory.set(report.id, []);
  item.report_id = report.id;
  recordAudit('report_generated', 'report', report.id, { case_id: id });
  recalculateDashboard();
  return structuredClone(report);
}

export function reportById(id: number): ReportWithHistory | undefined {
  const report = store.reports.get(id);
  if (!report) return undefined;
  return {
    ...structuredClone(report),
    history: structuredClone(store.reportHistory.get(id) ?? []),
  };
}

export function updateReport(
  id: number,
  update: { fields?: ReportFields; narrative?: string; incident_type?: string },
): Report | undefined {
  const report = store.reports.get(id);
  if (!report) return undefined;
  const history = store.reportHistory.get(id) ?? [];
  history.unshift(structuredClone(report));
  store.reportHistory.set(id, history);
  if (update.fields) report.fields = structuredClone(update.fields);
  if (update.narrative !== undefined) report.narrative = update.narrative;
  if (update.incident_type !== undefined) {
    report.incident_type = update.incident_type;
    report.fields.incident_type = update.incident_type;
  }
  report.version += 1;
  report.generated_at = iso(new Date());
  recordAudit('report_version_saved', 'report', id, { version: report.version });
  return structuredClone(report);
}

export function markReportSubmitted(
  id: number,
  referenceNumber: string,
  submittedBy: string,
): Report | undefined {
  const report = store.reports.get(id);
  if (!report) return undefined;
  report.status = 'submitted_manually';
  recordAudit('report_marked_submitted_manually', 'report', id, {
    reference_number: referenceNumber,
    submitted_by: submittedBy,
  });
  const linkedCase = store.cases.find((item) => item.id === report.case_id);
  if (linkedCase) linkedCase.status = 'reported';
  recalculateDashboard();
  return structuredClone(report);
}

export function alerts(status?: AlertStatus): Alert[] {
  return structuredClone(store.alerts.filter((item) => !status || item.status === status));
}

export function restoreAlert(id: number): boolean {
  const alert = store.alerts.find((item) => item.id === id);
  if (!alert) return false;
  const previous = alert.status;
  alert.status = 'new';
  alert.suppression_reason = null;
  recordAudit('alert_restored', 'alert', id, { previous_status: previous });
  recalculateDashboard();
  return true;
}

export function audit(params: URLSearchParams): AuditEvent[] {
  const action = params.get('action')?.toLowerCase();
  const targetType = params.get('target_type');
  const targetId = params.get('target_id');
  const limit = Number(params.get('limit') ?? 100);
  return structuredClone(store.audit.filter((event) =>
    (!action || event.action.toLowerCase().includes(action))
    && (!targetType || event.target_type === targetType)
    && (!targetId || event.target_id === targetId),
  ).slice(0, Math.max(0, limit)));
}

export function settings(): SettingsResponse {
  return { settings: structuredClone(store.settings), rules_yaml: store.rulesYaml };
}

export function updateSettings(payload: { settings?: Partial<Settings>; rules_yaml?: string }): SettingsResponse {
  if (payload.rules_yaml !== undefined && payload.rules_yaml.trim() && !/^\s*rules\s*:/m.test(payload.rules_yaml)) {
    throw new Error('Rules must start with a "rules:" key.');
  }
  store.settings = { ...store.settings, ...payload.settings };
  if (payload.rules_yaml !== undefined) store.rulesYaml = payload.rules_yaml;
  recalculateDashboard();
  recordAudit('settings_saved', 'settings', 1, { rules_updated: payload.rules_yaml !== undefined });
  return settings();
}

export function ingestAlerts(count: number, description: string): LoadResult {
  const created = Math.max(1, count);
  store.ingestedAdditional += created;
  const id = Math.max(0, ...store.alerts.map((alert) => alert.id)) + 1;
  store.alerts.push(makeAlert(id, 'email_security', iso(new Date()), `Uploaded alert batch: ${description}`, {
    status: 'unlinked_low_priority',
    severity_raw: 'low',
    category: 'informational',
    suppression_reason: 'Awaiting correlation with additional evidence.',
  }));
  recordAudit('alerts_ingested', 'alert_batch', id, { received: created });
  recalculateDashboard();
  return {
    ingest: { received: created, new: created, already_seen: 0 },
    pipeline: { suppressed: 0, merged: 0, in_cases: 0, cases_created: 0, unlinked_low_priority: created },
  };
}

