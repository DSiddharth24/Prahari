/**
 * Types matching Prahari backend contract (CONTEXT.pdf, PROMPT_3, backend models).
 */

// Vocabulary string‑literal unions – exact values from backend/models.py
export type Source =
  | 'email_security'
  | 'endpoint_av'
  | 'firewall'
  | 'identity_provider'
  | 'cloud_audit'
  | 'dlp';

export type Category =
  | 'suspicious_login'
  | 'failed_login'
  | 'malware'
  | 'data_exfiltration'
  | 'mass_file_access'
  | 'privilege_change'
  | 'phishing'
  | 'mailbox_rule_change'
  | 'port_scan'
  | 'ransomware_behaviour'
  | 'backup_activity'
  | 'informational';

export type Severity = 'low' | 'medium' | 'high' | 'critical';

export type CaseStatus = 'open' | 'confirmed' | 'dismissed' | 'escalated' | 'reported';

export type AlertStatus =
  | 'new'
  | 'suppressed_benign'
  | 'merged_duplicate'
  | 'in_case'
  | 'unlinked_low_priority';

export type Pattern =
  | 'account_takeover_then_exfiltration'
  | 'ransomware_behaviour'
  | 'phishing_to_compromise'
  | 'recon_then_access'
  | null; // nullable as per backend spec

export type ReportStatus = 'draft' | 'approved' | 'submitted_manually';

export type CountdownState = 'green' | 'amber' | 'red' | 'overdue' | 'none';

// Core data models – field names exactly as returned by the backend `.to_dict()` methods.
export interface Alert {
  id: number;
  source: Source;
  source_alert_id: string;
  timestamp: string; // ISO 8601
  title: string;
  description: string | null;
  severity_raw: Severity | null;
  category: Category | null;
  user: string | null;
  host: string | null;
  src_ip: string | null;
  dst_ip: string | null;
  file: string | null;
  process: string | null;
  raw: string | null; // original JSON payload
  status: AlertStatus;
  suppression_reason: string | null;
  duplicate_of: number | null;
  duplicate_count: number;
}

export interface CaseListItem {
  id: number;
  title: string;
  score: number;
  severity: Severity;
  status: CaseStatus;
  pattern: Pattern;
  sources_count: number;
  first_alert_at: string | null;
  detected_at: string | null;
  deadline_at: string | null;
  seconds_remaining: number | null;
  countdown_state: CountdownState;
}

export interface CaseDetail extends CaseListItem {
  timeline: Alert[]; // ordered list of alerts from case
  summary: string | null;
  summary_source: 'llm' | 'template' | null;
  recommended_actions: string[];
  score_breakdown: { factor: string; points: number; explanation?: string }[];
  entities: { users: string[]; hosts: string[]; ips: string[] };
  report_id: number | null;
}

export interface Dashboard {
  funnel: {
    ingested: number;
    suppressed: number;
    merged: number;
    in_cases: number;
    cases: number;
  };
  time_saved_minutes: number;
  time_saved_note: string;
  cases_by_severity: { low: number; medium: number; high: number; critical: number };
  open_cases: CaseListItem[];
}

export interface EvidenceItem {
  alert_id: number;
  source: Source;
  time: string; // ISO 8601
  title: string;
}

export interface ReportFields {
  organisation_name: string;
  reporter_name: string;
  reporter_role: string;
  reporter_contact: string;
  incident_type: string;
  detected_at_ist: string;
  detected_at_utc: string;
  first_activity_at_ist: string;
  affected_systems: string;
  description: string;
  impact_assessment: string;
  actions_taken: string;
  evidence: EvidenceItem[];
  logs_preserved: string;
}

export interface Report {
  id: number;
  case_id: number;
  incident_type: string | null;
  fields: ReportFields;
  narrative: string | null;
  generated_at: string; // ISO 8601
  status: ReportStatus;
  version: number;
  history?: unknown; // optional audit trail
}

export interface AuditEvent {
  id: number;
  timestamp: string; // ISO 8601
  actor: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: unknown | null;
}

export interface Settings {
  correlation_window_hours: number;
  dedupe_window_minutes: number;
  minutes_saved_per_alert: number;
  critical_assets: string[];
  outbound_bytes_threshold: number;
}

export interface IngestResult {
  received: number;
  new: number;
  already_seen: number;
}

export interface PipelineResult {
  suppressed: number;
  merged: number;
  in_cases: number;
  cases_created: number;
  unlinked_low_priority: number;
}
