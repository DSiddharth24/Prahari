import { Link } from 'react-router-dom';
import { ArrowDown, ArrowRight, Clock3, RotateCcw } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import LoadDemoButton from '../components/LoadDemoButton';
import { CountdownBadge, ErrorState, InfoTip, LoadingSkeleton, QuietButton, SeverityBadge } from '../components/Ui';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import { useDashboard, useResetDemo } from '../lib/queries';
import type { CaseListItem, Severity } from '../lib/types';
import { formatIST } from '../lib/time';

const severityOrder: Severity[] = ['critical', 'high', 'medium', 'low'];
const severityTrack: Record<Severity, string> = {
  critical: 'bg-chip-critical-fg',
  high: 'bg-chip-high-fg',
  medium: 'bg-chip-medium-fg',
  low: 'bg-chip-low-fg',
};

function FunnelStep({ label, value, explanation, last = false }: {
  label: string;
  value: number;
  explanation: string;
  last?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <div data-testid={`funnel-${label.toLowerCase().replaceAll(' ', '-')}`} className="min-w-0 flex-1 border-t-2 border-primary pt-3">
        <p className="flex items-center text-12 text-text-secondary">
          {label}
          <InfoTip text={explanation} label={`How ${label.toLowerCase()} is counted`} />
        </p>
        <p className="mt-1 text-28 font-semibold tabular-nums tracking-heading" title={explanation}>{value.toLocaleString('en-IN')}</p>
      </div>
      {!last ? <ArrowRight className="hidden shrink-0 text-text-muted sm:block" size={18} aria-hidden="true" /> : <ArrowDown className="mx-auto mt-1 text-text-muted sm:hidden" size={16} aria-hidden="true" />}
    </div>
  );
}

function OpenCase({ item }: { item: CaseListItem }) {
  return (
    <Link
      to={`/cases/${item.id}`}
      className="grid gap-2 border-b border-border py-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center sm:gap-4"
    >
      <span className="min-w-0">
        <span className="block break-anywhere font-medium text-text">{item.title}</span>
        <span className="mt-1 block text-12 text-text-secondary">
          First alert: {item.first_alert_at ? formatIST(item.first_alert_at) : 'Not available'}
        </span>
      </span>
      <span className="flex items-center gap-3">
        <SeverityBadge severity={item.severity} />
        <span className="text-13 font-semibold tabular-nums" title="Triage score from linked evidence">{item.score}</span>
      </span>
      <CountdownBadge deadlineAt={item.deadline_at} status={item.status} />
    </Link>
  );
}

export default function Dashboard() {
  const query = useDashboard();
  useErrorToast(query.error);
  const reset = useResetDemo();
  const { notify } = useToast();
  const onReset = async () => {
    try {
      await reset.mutateAsync();
      notify('Demo data has been reset.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="Dashboard" description="Security alerts at a glance. Review linked evidence before deciding what to do." />
        {query.data?.funnel.cases ? (
          <QuietButton type="button" onClick={onReset} disabled={reset.isPending}>
            <RotateCcw size={15} aria-hidden="true" />
            {reset.isPending ? 'Resetting…' : 'Reset demo'}
          </QuietButton>
        ) : null}
      </div>
      {query.isLoading ? <LoadingSkeleton rows={5} /> : null}
      {query.isError ? <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} /> : null}
      {query.data && !query.data.funnel.cases ? (
        <EmptyState
          title="No cases yet"
          body="Security teams at mid-size Indian firms receive more alerts than they can read. Load sample evidence to see how Prahari links alerts into cases for human review."
        >
          <LoadDemoButton />
        </EmptyState>
      ) : null}
      {query.data && query.data.funnel.cases > 0 ? (
        <div className="space-y-8">
          <section aria-labelledby="funnel-heading">
            <h2 id="funnel-heading" className="mb-4 text-16 font-semibold">Alert flow</h2>
            <div className="grid grid-cols-1 gap-3 rounded-sm border border-border bg-surface px-4 py-4 sm:grid-cols-4 sm:gap-2">
              <FunnelStep label="Ingested" value={query.data.funnel.ingested} explanation="Total alerts received by Prahari, including alerts later suppressed, merged or linked to cases." />
              <FunnelStep label="After cleaning" value={Math.max(0, query.data.funnel.ingested - query.data.funnel.suppressed - query.data.funnel.merged)} explanation={`${query.data.funnel.ingested.toLocaleString('en-IN')} ingested minus ${query.data.funnel.suppressed.toLocaleString('en-IN')} suppressed and ${query.data.funnel.merged.toLocaleString('en-IN')} merged alerts.`} />
              <FunnelStep label="In cases" value={query.data.funnel.in_cases} explanation="Alerts linked to the four sample cases. One case can contain several alerts." />
              <FunnelStep label="Cases" value={query.data.funnel.cases} explanation="Distinct evidence groups created for analyst review." last />
            </div>
            <p className="mt-2 text-12 text-text-muted">
              Cleaning kept {query.data.funnel.suppressed.toLocaleString('en-IN')} routine alerts out and merged {query.data.funnel.merged.toLocaleString('en-IN')} duplicates. Each group remains available in Suppressed.
            </p>
          </section>

          <div className="grid gap-8 xl:grid-cols-[minmax(0,1.4fr)_minmax(17rem,0.6fr)]">
            <section aria-labelledby="cases-heading">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h2 id="cases-heading" className="text-16 font-semibold">Open cases</h2>
                <Link to="/cases" className="text-13 font-medium text-info underline underline-offset-2">View all cases</Link>
              </div>
              {query.data.open_cases.length ? (
                <div className="border-t border-border">
                  {query.data.open_cases.map((item) => <OpenCase key={item.id} item={item} />)}
                </div>
              ) : (
                <p className="border-t border-border py-4 text-13 text-text-secondary">No open cases. Dismissed and reported cases remain available in the cases list.</p>
              )}
            </section>

            <div className="space-y-7">
              <section aria-labelledby="severity-heading">
                <h2 id="severity-heading" className="mb-3 text-16 font-semibold">Cases by severity</h2>
                <ul className="space-y-3">
                  {severityOrder.map((severity) => {
                    const count = query.data.cases_by_severity[severity];
                    const total = Math.max(1, query.data.funnel.cases);
                    return (
                      <li key={severity}>
                        <div className="mb-1 flex items-center justify-between gap-3">
                          <SeverityBadge severity={severity} />
                          <span className="text-13 font-semibold tabular-nums" title={`${count} ${severity} cases`}>{count}</span>
                        </div>
                        <div className="h-2 bg-sunken" role="img" aria-label={`${count} ${severity} cases`}>
                          <div className={`h-2 ${severityTrack[severity]}`} style={{ width: `${(count / total) * 100}%` }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
              <section aria-labelledby="saved-heading" className="border-l-2 border-info bg-surface px-4 py-3">
                <h2 id="saved-heading" className="flex items-center text-13 font-semibold">
                  <Clock3 size={16} className="mr-2 text-info" aria-hidden="true" />
                  Time saved estimate
                  <InfoTip text={query.data.time_saved_note} label="How the time saved estimate is calculated" />
                </h2>
                <p className="mt-2 text-28 font-semibold tabular-nums">{query.data.time_saved_minutes.toLocaleString('en-IN')} <span className="text-14 font-medium">minutes</span></p>
                <p className="mt-1 text-12 text-text-secondary">{query.data.time_saved_note}</p>
              </section>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
