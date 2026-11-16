import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { formatInTimeZone, fromZonedTime } from 'date-fns-tz';
import PageHeader from '../components/PageHeader';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import {
  Button,
  CountdownBadge,
  ErrorState,
  FormField,
  InfoTip,
  LoadingSkeleton,
  Modal,
  QuietButton,
  SeverityBadge,
  SourceMark,
  StatusBadge,
  controlClass,
} from '../components/Ui';
import { useCase, useCaseAction, useCaseDetectedAt, useCaseReport } from '../lib/queries';
import { formatIST } from '../lib/time';
import type { Alert } from '../lib/types';
import { Clock3, FileText } from 'lucide-react';

type CaseAction = 'confirm' | 'dismiss' | 'escalate';

function localInputValue(iso: string | null): string {
  if (!iso) return '';
  return formatInTimeZone(new Date(iso), 'Asia/Kolkata', "yyyy-MM-dd'T'HH:mm");
}

function rawEvidence(raw: string | null): string {
  if (!raw) return 'No raw evidence was supplied for this alert.';
  try {
    return JSON.stringify(JSON.parse(raw) as unknown, null, 2);
  } catch {
    return raw;
  }
}

function ActionDialog({ action, onClose, onSubmit, pending }: {
  action: CaseAction;
  onClose: () => void;
  onSubmit: (note: string) => Promise<void>;
  pending: boolean;
}) {
  const [note, setNote] = useState('');
  const title = `${action[0].toUpperCase()}${action.slice(1)} case`;
  const onFormSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!note.trim()) return;
    await onSubmit(note.trim());
  };
  return (
    <Modal title={title} onClose={onClose} describedBy="case-action-help">
      <form onSubmit={onFormSubmit}>
        <p id="case-action-help" className="mb-4 text-13 text-text-secondary">
          Record why you are {action === 'confirm' ? 'confirming' : action === 'dismiss' ? 'dismissing' : 'escalating'} this case. This note will appear in the audit log.
        </p>
        <FormField label="Review note">
          <textarea
            autoFocus
            className={controlClass('min-h-28 resize-y')}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Describe the evidence or decision"
            required
            aria-required="true"
          />
        </FormField>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <QuietButton type="button" onClick={onClose}>Cancel</QuietButton>
          <Button type="submit" disabled={!note.trim() || pending}>
            {pending ? 'Saving note…' : `${title}`}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function DetectedAtDialog({ value, onClose, onSave, pending }: {
  value: string;
  onClose: () => void;
  onSave: (detectedAt: string, reason: string) => Promise<void>;
  pending: boolean;
}) {
  const [detectedAt, setDetectedAt] = useState(value);
  const [reason, setReason] = useState('');
  const onFormSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detectedAt || !reason.trim()) return;
    await onSave(fromZonedTime(detectedAt, 'Asia/Kolkata').toISOString(), reason.trim());
  };
  return (
    <Modal title="Adjust detected-at time" onClose={onClose} describedBy="detected-at-help">
      <form onSubmit={onFormSubmit}>
        <p id="detected-at-help" className="mb-4 text-13 text-text-secondary">
          Changing this time also recalculates the six-hour reminder deadline. Add the source for this correction.
        </p>
        <div className="space-y-4">
          <FormField label="Detected at (IST)">
            <input type="datetime-local" className={controlClass()} value={detectedAt} onChange={(event) => setDetectedAt(event.target.value)} required />
          </FormField>
          <FormField label="Reason for adjustment">
            <textarea className={controlClass('min-h-24 resize-y')} value={reason} onChange={(event) => setReason(event.target.value)} required placeholder="For example, confirmed against the original provider log" />
          </FormField>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <QuietButton type="button" onClick={onClose}>Cancel</QuietButton>
          <Button type="submit" disabled={!detectedAt || !reason.trim() || pending}>{pending ? 'Saving…' : 'Save detected-at time'}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function CaseDetail() {
  const routeParams = useParams();
  const caseId = Number(routeParams.id);
  const navigate = useNavigate();
  const query = useCase(caseId);
  const actionMutation = useCaseAction(caseId);
  const detectedAtMutation = useCaseDetectedAt(caseId);
  const reportMutation = useCaseReport(caseId);
  useErrorToast(query.error);
  const { notify } = useToast();
  const [action, setAction] = useState<CaseAction | null>(null);
  const [adjustingDetectedAt, setAdjustingDetectedAt] = useState(false);

  const timeline = useMemo(
    () => [...(query.data?.timeline ?? [])].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp)),
    [query.data?.timeline],
  );

  const submitAction = async (note: string) => {
    if (!action) return;
    try {
      await actionMutation.mutateAsync({ action, note });
      notify(`Case ${action}ed with an audit note.`);
      setAction(null);
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };
  const saveDetectedAt = async (detectedAt: string, reason: string) => {
    try {
      await detectedAtMutation.mutateAsync({ detected_at: detectedAt, reason });
      notify('Detected-at time and reminder deadline updated.');
      setAdjustingDetectedAt(false);
    } catch (failure) {
      notify(errorDetail(failure), 'error');
    }
  };
  const createReport = async () => {
    try {
      const report = await reportMutation.mutateAsync();
      notify('CERT-In report draft created for analyst review.');
      navigate(`/reports/${report.id}`);
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };

  if (query.isLoading) return <LoadingSkeleton rows={8} />;
  if (query.isError) return <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} />;
  if (!query.data) return <PageHeader title="Case not found" description={`No case exists with reference ${routeParams.id ?? 'unknown'}.`} />;
  const caseData = query.data;
  const scoreTotal = caseData.score_breakdown.reduce((sum, item) => sum + item.points, 0) || 1;

  return (
    <>
      <div className="mb-6">
        <Link to="/cases" className="mb-3 inline-block text-13 font-medium text-info underline underline-offset-2">All cases</Link>
        <PageHeader title={caseData.title} description={`Case ${caseData.id} · ${caseData.sources_count} evidence sources · first seen ${caseData.first_alert_at ? formatIST(caseData.first_alert_at) : 'not available'}`} />
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={caseData.severity} />
          <StatusBadge status={caseData.status} />
          <span className="inline-flex items-center gap-1 text-14 font-semibold tabular-nums">
            Score {caseData.score}
            <InfoTip text="A prioritization aid based on severity, evidence from distinct sources, overlapping entities and how close together alerts occurred. It is not a probability." label={`How score ${caseData.score} is calculated`} />
          </span>
        </div>
      </div>

      <section aria-labelledby="deadline-heading" className="mb-8 grid gap-3 rounded-3xl bg-surface px-5 py-5 shadow-sm sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-6">
        <div>
          <h2 id="deadline-heading" className="flex items-center gap-2 text-13 font-semibold text-text-secondary">
            <Clock3 size={16} aria-hidden="true" />
            6-hour reporting reminder
          </h2>
          <p className="mt-1 text-12 text-text-secondary">Reminder only. Prahari does not submit to CERT-In.</p>
          <button type="button" className="mt-2 inline-flex min-h-9 items-center rounded-full border border-border-strong px-4 text-12 font-medium text-text hover:bg-sunken" onClick={() => setAdjustingDetectedAt(true)}>
            Adjust detected-at
          </button>
        </div>
        <CountdownBadge deadlineAt={caseData.deadline_at} status={caseData.status} large />
      </section>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1.3fr)_minmax(20rem,0.7fr)]">
        <div className="min-w-0">
          <section aria-labelledby="summary-heading" className="mb-8 rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 id="summary-heading" className="text-19 font-semibold tracking-heading">What the evidence shows</h2>
              <span className="rounded-full border border-border-strong px-2.5 py-1 text-12 font-medium">
                {caseData.summary_source === 'llm' ? 'AI summary' : 'Template summary'}
              </span>
            </div>
            <p className="max-w-[75ch] text-14 leading-relaxed text-text-secondary">{caseData.summary ?? 'No summary is available. Review the timeline evidence below.'}</p>
            {caseData.recommended_actions.length > 0 ? (
              <div className="mt-4 border-l-2 border-border-strong pl-4">
                <h3 className="text-13 font-semibold">Recommended review steps</h3>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-13 text-text-secondary">
                  {caseData.recommended_actions.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                </ol>
              </div>
            ) : null}
          </section>

          <section aria-labelledby="timeline-heading" className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2 id="timeline-heading" className="text-19 font-semibold tracking-heading">Evidence timeline</h2>
              <span className="text-12 text-text-secondary">{timeline.length} linked alerts</span>
            </div>
            {timeline.length ? (
              <ol className="relative space-y-0 border-l border-border-strong pl-5">
                {timeline.map((alert: Alert, index) => (
                  <li key={alert.id} className="relative pb-6 last:pb-0">
                    <span aria-hidden="true" className="absolute -left-[1.65rem] top-1 grid h-6 w-6 place-items-center rounded-full border border-border-strong bg-paper">
                      <span className="h-2 w-2 rounded-full bg-primary" />
                    </span>
                    <article className="min-w-0 border-b border-border pb-4 last:border-0">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <SourceMark source={alert.source} />
                          <h3 className="mt-1 break-anywhere font-semibold">{alert.title}</h3>
                        </div>
                        <span className="whitespace-nowrap text-12 tabular-nums text-text-secondary" title={formatIST(alert.timestamp)}>
                          {formatIST(alert.timestamp)}
                        </span>
                      </div>
                      {alert.description ? <p className="mt-2 max-w-[70ch] text-13 text-text-secondary">{alert.description}</p> : null}
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-12 text-text-secondary">
                        {alert.user ? <span>User: {alert.user}</span> : null}
                        {alert.host ? <span>Host: {alert.host}</span> : null}
                        {alert.src_ip ? <span>Source IP: {alert.src_ip}</span> : null}
                        {alert.dst_ip ? <span>Destination IP: {alert.dst_ip}</span> : null}
                        {alert.file ? <span>File: {alert.file}</span> : null}
                        {alert.process ? <span>Process: {alert.process}</span> : null}
                      </div>
                      <details className="mt-3">
                        <summary className="min-h-8 cursor-pointer text-12 font-medium text-info underline underline-offset-2">
                          View raw JSON evidence {index + 1}
                        </summary>
                        <pre className="mt-2 max-h-80 overflow-auto border border-border bg-sunken p-3 font-mono text-12 leading-relaxed">{rawEvidence(alert.raw)}</pre>
                      </details>
                    </article>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="border-y border-border py-4 text-13 text-text-secondary">No alert evidence is linked to this case yet.</p>
            )}
          </section>
        </div>

        <aside className="min-w-0">
          <section aria-labelledby="score-heading" className="mb-8 rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <h2 id="score-heading" className="flex items-center text-16 font-semibold">
              Score breakdown <InfoTip text="Points show which evidence features contributed to the triage score. They explain the score; they are not a confidence percentage." label="About score breakdown" />
            </h2>
            <p className="mt-1 text-12 text-text-secondary">Score {caseData.score} from {scoreTotal} evidence points</p>
            <ul className="mt-4 space-y-4">
              {caseData.score_breakdown.map((factor, index) => (
                <li key={`${factor.factor}-${index}`} className="border-b border-border pb-3 last:border-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-13 font-medium">{factor.factor}</span>
                    <span className="text-13 font-semibold tabular-nums">{factor.points}</span>
                  </div>
                  <div className="mt-2 h-1.5 bg-sunken" role="img" aria-label={`${factor.factor}: ${factor.points} points`}>
                    <div className="h-1.5 bg-primary" style={{ width: `${Math.min(100, (factor.points / scoreTotal) * 100)}%` }} />
                  </div>
                  {factor.explanation ? <p className="mt-2 text-12 leading-relaxed text-text-secondary">{factor.explanation}</p> : null}
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="entities-heading" className="mb-8 rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <h2 id="entities-heading" className="text-16 font-semibold">Linked entities</h2>
            <dl className="mt-3 space-y-2 text-13">
              {([
                ['Users', caseData.entities.users],
                ['Hosts', caseData.entities.hosts],
                ['IP addresses', caseData.entities.ips],
              ] as const).map(([label, values]) => (
                <div key={label} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 border-b border-border py-2">
                  <dt className="text-text-secondary">{label}</dt>
                  <dd className="break-anywhere">{values.length ? values.join(', ') : 'None linked'}</dd>
                </div>
              ))}
            </dl>
          </section>
        </aside>
      </div>

      <section aria-label="Case actions" className="mt-8 rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={() => setAction('confirm')}><FileText size={15} aria-hidden="true" />Confirm</Button>
          <QuietButton type="button" onClick={() => setAction('dismiss')}>Dismiss</QuietButton>
          <QuietButton type="button" className="border-error text-error" onClick={() => setAction('escalate')}>Escalate</QuietButton>
          {caseData.report_id ? (
            <Link to={`/reports/${caseData.report_id}`} className="inline-flex min-h-10 items-center gap-2 rounded-full border border-border-strong bg-surface px-4 text-13 font-semibold hover:bg-sunken">
              <FileText size={15} aria-hidden="true" />View report
            </Link>
          ) : (
            <Button type="button" onClick={createReport} disabled={reportMutation.isPending} className="sm:ml-auto">
              <FileText size={15} aria-hidden="true" />{reportMutation.isPending ? 'Preparing report…' : 'Generate CERT-In report'}
            </Button>
          )}
        </div>
      </section>

      {action ? <ActionDialog action={action} onClose={() => setAction(null)} onSubmit={submitAction} pending={actionMutation.isPending} /> : null}
      {adjustingDetectedAt ? (
        <DetectedAtDialog
          value={localInputValue(caseData.detected_at)}
          onClose={() => setAdjustingDetectedAt(false)}
          onSave={saveDetectedAt}
          pending={detectedAtMutation.isPending}
        />
      ) : null}
    </>
  );
}
