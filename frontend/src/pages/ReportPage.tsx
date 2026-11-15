import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Download, Eye, Save, Send } from 'lucide-react';
import { formatInTimeZone, fromZonedTime } from 'date-fns-tz';
import { isValid, parse } from 'date-fns';
import PageHeader from '../components/PageHeader';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import {
  Button,
  ErrorState,
  FormField,
  LoadingSkeleton,
  Modal,
  QuietButton,
  controlClass,
} from '../components/Ui';
import { getReportPdfUrl } from '../lib/api';
import { useReport, usePutReport, useReportSubmitted } from '../lib/queries';
import { formatIST } from '../lib/time';
import type { Report, ReportFields } from '../lib/types';

const fieldRows: Array<{ key: keyof Omit<ReportFields, 'evidence'>; label: string; multiline?: boolean }> = [
  { key: 'organisation_name', label: 'Organisation name' },
  { key: 'reporter_name', label: 'Reporter name' },
  { key: 'reporter_role', label: 'Reporter role' },
  { key: 'reporter_contact', label: 'Reporter contact' },
  { key: 'incident_type', label: 'Incident type' },
  { key: 'detected_at_ist', label: 'Detected at (IST)' },
  { key: 'detected_at_utc', label: 'Detected at (IST; saved as UTC)' },
  { key: 'first_activity_at_ist', label: 'First activity at (IST)' },
  { key: 'affected_systems', label: 'Affected systems', multiline: true },
  { key: 'description', label: 'Incident description', multiline: true },
  { key: 'impact_assessment', label: 'Impact assessment', multiline: true },
  { key: 'actions_taken', label: 'Actions taken', multiline: true },
  { key: 'logs_preserved', label: 'Logs preserved', multiline: true },
];

function exportError(response: Response): Promise<string> {
  return response.json().then((body: unknown) => {
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') return body.detail;
    return response.statusText || 'PDF export failed.';
  }).catch(() => response.statusText || 'PDF export failed.');
}

function copyReportVersion(source: Report): ReportFields {
  return structuredClone(source.fields);
}

function evidenceForEditor(fields: ReportFields): string {
  const evidence = fields.evidence.map((item) => ({ ...item, time: formatIST(item.time) }));
  return JSON.stringify(evidence, null, 2);
}

function evidenceForApi(text: string): ReportFields['evidence'] {
  const evidence = JSON.parse(text) as ReportFields['evidence'];
  if (!Array.isArray(evidence)) throw new Error('Evidence must be a JSON array.');
  return evidence.map((item) => {
    if (!item || typeof item.time !== 'string' || !item.time.endsWith(' IST')) {
      throw new Error('Each evidence time must be entered and labelled in IST.');
    }
    const parsed = parse(item.time.slice(0, -4), 'd MMM yyyy, HH:mm', new Date());
    if (!isValid(parsed)) throw new Error(`Evidence time is not valid: ${item.time}`);
    return { ...item, time: fromZonedTime(parsed, 'Asia/Kolkata').toISOString() };
  });
}

export default function ReportPage() {
  const routeParams = useParams();
  const reportId = Number(routeParams.id);
  const query = useReport(reportId);
  const saveMutation = usePutReport(reportId);
  const submitMutation = useReportSubmitted(reportId);
  useErrorToast(query.error);
  const { notify } = useToast();
  const [fields, setFields] = useState<ReportFields | null>(null);
  const [narrative, setNarrative] = useState('');
  const [evidenceText, setEvidenceText] = useState('[]');
  const [evidenceError, setEvidenceError] = useState('');
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [submissionOpen, setSubmissionOpen] = useState(false);
  const [referenceNumber, setReferenceNumber] = useState('');
  const [submittedBy, setSubmittedBy] = useState('');

  const selectedReport = useMemo(() => {
    if (!query.data) return undefined;
    if (selectedVersion === null || selectedVersion === query.data.version) return query.data;
    return query.data.history.find((item) => item.version === selectedVersion);
  }, [query.data, selectedVersion]);

  useEffect(() => {
    if (!selectedReport) return;
    setFields(copyReportVersion(selectedReport));
    setNarrative(selectedReport.narrative ?? '');
    setEvidenceText(evidenceForEditor(selectedReport.fields));
    setEvidenceError('');
  }, [selectedReport]);

  const isHistorical = Boolean(selectedReport && query.data && selectedReport.version !== query.data.version);
  const updateField = <K extends keyof ReportFields>(key: K, value: ReportFields[K]) => {
    setFields((current) => current ? { ...current, [key]: value } : current);
  };
  const saveVersion = async () => {
    if (!fields) return;
    let evidence: ReportFields['evidence'];
    try {
      evidence = evidenceForApi(evidenceText);
      setEvidenceError('');
    } catch (reason) {
      setEvidenceError(reason instanceof Error ? reason.message : 'Evidence must be valid JSON.');
      return;
    }
    try {
      await saveMutation.mutateAsync({
        fields: { ...fields, evidence },
        narrative,
        incident_type: fields.incident_type,
      });
      setSelectedVersion(null);
      notify('Saved as a new report version.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };
  const downloadPdf = async () => {
    try {
      const response = await fetch(getReportPdfUrl(reportId));
      if (!response.ok) throw new Error(await exportError(response));
      const file = await response.blob();
      const objectUrl = URL.createObjectURL(file);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `prahari-report-${reportId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      notify('Report PDF exported.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };
  const markSubmitted = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!referenceNumber.trim() || !submittedBy.trim()) return;
    try {
      await submitMutation.mutateAsync({
        reference_number: referenceNumber.trim(),
        submitted_by: submittedBy.trim(),
      });
      setSubmissionOpen(false);
      notify('Report marked as submitted manually.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };

  if (query.isLoading) return <LoadingSkeleton rows={8} />;
  if (query.isError) return <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} />;
  if (!query.data || !fields || !selectedReport) {
    return <PageHeader title="Report not found" description={`No report exists with reference ${routeParams.id ?? 'unknown'}.`} />;
  }
  const editable = !isHistorical && selectedReport.status !== 'submitted_manually';
  const versions = [query.data, ...query.data.history].sort((a, b) => b.version - a.version);

  return (
    <>
      <Link to={`/cases/${query.data.case_id}`} className="mb-3 inline-block text-13 font-medium text-info underline underline-offset-2">Back to case {query.data.case_id}</Link>
      <PageHeader
        title={`CERT-In report · ${query.data.id}`}
        description={`Version ${selectedReport.version} · Generated ${formatIST(selectedReport.generated_at)} · ${selectedReport.status.replaceAll('_', ' ')}`}
      />
      <div role="note" className="sticky top-14 z-20 mb-6 rounded-2xl border border-warning bg-chip-medium-bg px-4 py-3 text-13 font-semibold text-chip-medium-fg">
        DRAFT, for analyst review. Verify against the official CERT-In form before submission.
      </div>
      {isHistorical ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-3 shadow-sm">
          <p className="text-13">Viewing saved version {selectedReport.version}. This version cannot be edited.</p>
          <QuietButton type="button" onClick={() => setSelectedVersion(null)}>Return to current version</QuietButton>
        </div>
      ) : null}

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <form className="min-w-0 space-y-6" onSubmit={(event) => { event.preventDefault(); void saveVersion(); }}>
          <section aria-labelledby="report-fields-heading" className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <h2 id="report-fields-heading" className="mb-4 text-16 font-semibold">Report details</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {fieldRows.map(({ key, label, multiline }) => (
                <FormField key={key} label={label}>
                  {multiline ? (
                    <textarea
                      className={controlClass('min-h-24 resize-y')}
                      value={fields[key]}
                      onChange={(event) => updateField(key, event.target.value)}
                      disabled={!editable}
                    />
                  ) : key === 'detected_at_utc' ? (
                    <input
                      type="datetime-local"
                      className={controlClass()}
                      value={fields.detected_at_utc ? formatInTimeZone(new Date(fields.detected_at_utc), 'Asia/Kolkata', "yyyy-MM-dd'T'HH:mm") : ''}
                      onChange={(event) => updateField('detected_at_utc', event.target.value ? fromZonedTime(event.target.value, 'Asia/Kolkata').toISOString() : '')}
                      disabled={!editable}
                    />
                  ) : key === 'incident_type' ? (
                    <select className={controlClass()} value={fields.incident_type} onChange={(event) => updateField('incident_type', event.target.value)} disabled={!editable}>
                      {['Suspected cybersecurity incident', 'Account compromise', 'Phishing attempt', 'Malware or ransomware', 'Data exposure', 'Other'].map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  ) : (
                    <input className={controlClass()} value={fields[key]} onChange={(event) => updateField(key, event.target.value)} disabled={!editable} />
                  )}
                </FormField>
              ))}
            </div>
            <div className="mt-4">
              <FormField label="Evidence (JSON array)" hint="Each entry contains an alert ID, source, title and timestamp labelled IST. Times are saved as UTC ISO values.">
                <textarea
                  className={controlClass('min-h-36 resize-y font-mono text-12')}
                  value={evidenceText}
                  onChange={(event) => setEvidenceText(event.target.value)}
                  disabled={!editable}
                  aria-describedby={evidenceError ? 'evidence-error' : undefined}
                />
              </FormField>
              {evidenceError ? <p id="evidence-error" role="alert" className="mt-1 text-12 text-error">{evidenceError}</p> : null}
            </div>
          </section>
          <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <FormField label="Narrative">
              <textarea className={controlClass('min-h-48 resize-y')} value={narrative} onChange={(event) => setNarrative(event.target.value)} disabled={!editable} />
            </FormField>
          </section>
          <div className="flex flex-wrap gap-2 border-t border-border pt-4">
            <Button type="submit" disabled={!editable || saveMutation.isPending}>
              <Save size={15} aria-hidden="true" />{saveMutation.isPending ? 'Saving version…' : 'Save as new version'}
            </Button>
            <QuietButton type="button" onClick={downloadPdf}><Download size={15} aria-hidden="true" />Export PDF</QuietButton>
            {!isHistorical && selectedReport.status !== 'submitted_manually' ? (
              <QuietButton type="button" onClick={() => setSubmissionOpen(true)}><Send size={15} aria-hidden="true" />Mark as submitted manually</QuietButton>
            ) : null}
          </div>
        </form>

        <aside aria-labelledby="history-heading" className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
          <h2 id="history-heading" className="text-16 font-semibold">Version history</h2>
          <ol className="mt-3 space-y-3">
            {versions.map((version) => (
              <li key={version.version} className="border-b border-border pb-3 last:border-0">
                <p className="text-13 font-semibold">Version {version.version}{version.version === query.data.version ? ' · current' : ''}</p>
                <p className="mt-1 text-12 text-text-secondary">{formatIST(version.generated_at)}</p>
                {version.version !== selectedReport.version ? (
                  <button type="button" onClick={() => setSelectedVersion(version.version)} className="mt-2 inline-flex min-h-9 items-center gap-1 rounded-full border border-transparent px-3 text-12 font-medium text-text underline underline-offset-2 hover:bg-sunken">
                    <Eye size={14} aria-hidden="true" />View this version
                  </button>
                ) : <span className="mt-2 block text-12 text-text-muted">Currently viewing</span>}
              </li>
            ))}
          </ol>
        </aside>
      </div>

      {submissionOpen ? (
        <Modal title="Record manual submission" onClose={() => setSubmissionOpen(false)} describedBy="manual-submission-note">
          <form onSubmit={markSubmitted}>
            <p id="manual-submission-note" className="mb-4 text-13 text-text-secondary">
              Prahari will only record the reference. It does not submit this report to CERT-In.
            </p>
            <div className="space-y-4">
              <FormField label="Reference number">
                <input className={controlClass()} value={referenceNumber} onChange={(event) => setReferenceNumber(event.target.value)} required />
              </FormField>
              <FormField label="Submitted by">
                <input className={controlClass()} value={submittedBy} onChange={(event) => setSubmittedBy(event.target.value)} required />
              </FormField>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <QuietButton type="button" onClick={() => setSubmissionOpen(false)}>Cancel</QuietButton>
              <Button type="submit" disabled={!referenceNumber.trim() || !submittedBy.trim() || submitMutation.isPending}>
                {submitMutation.isPending ? 'Saving reference…' : 'Record submission'}
              </Button>
            </div>
          </form>
        </Modal>
      ) : null}
    </>
  );
}
