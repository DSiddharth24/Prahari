import { Link } from 'react-router-dom';
import {
  Archive,
  BriefcaseBusiness,
  Clock3,
  CopyCheck,
  Inbox,
  Layers3,
  RotateCcw,
} from 'lucide-react';
import EmptyState from '../components/EmptyState';
import LoadDemoButton from '../components/LoadDemoButton';
import { CountdownBadge, ErrorState, InfoTip, LoadingSkeleton, QuietButton, SeverityBadge } from '../components/Ui';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import { useDashboard, useResetDemo } from '../lib/queries';
import type { CaseListItem, Severity } from '../lib/types';
import { formatIST } from '../lib/time';

const severityChartOrder: Severity[] = ['low', 'medium', 'high', 'critical'];

type StatCardProps = {
  label: string;
  value: string;
  explanation: string;
  Icon: typeof Inbox;
  testId?: string;
  highlighted?: boolean;
};

function StatCard({ label, value, explanation, Icon, testId, highlighted = false }: StatCardProps) {
  return (
    <article
      data-testid={testId}
      className={`flex min-h-36 min-w-0 flex-col items-start rounded-3xl border p-4 shadow-sm sm:p-5 ${
        highlighted
          ? 'border-text bg-text text-primary-text'
          : 'border-white bg-surface text-text'
      }`}
    >
      <span className={`grid h-10 w-10 place-items-center rounded-full ${highlighted ? 'bg-surface/15 text-primary-text' : 'bg-sunken text-text-secondary'}`}>
        <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
      </span>
      <span className="mt-4 flex min-w-0 items-center gap-1">
        <span className="truncate text-23 font-semibold tabular-nums tracking-heading" title={explanation}>{value}</span>
        <span className={highlighted ? '[&_button]:border-white/70 [&_button]:text-white' : ''}>
          <InfoTip text={explanation} label={`How ${label.toLowerCase()} is counted`} />
        </span>
      </span>
      <span className={`mt-1 text-12 leading-snug ${highlighted ? 'text-primary-text/75' : 'text-text-secondary'}`}>{label}</span>
    </article>
  );
}

function SeverityChart({ values }: { values: Record<Severity, number> }) {
  const data = severityChartOrder.map((severity) => ({
    label: severity,
    count: values[severity],
  }));
  const maximumCount = Math.max(0, ...data.map((item) => item.count));
  const axisMaximum = Math.max(4, Math.ceil(maximumCount / 4) * 4);
  const chart = { left: 48, top: 38, width: 560, height: 194 };
  const baseline = chart.top + chart.height;
  const slot = chart.width / data.length;
  const barWidth = 48;

  return (
    <div className="min-w-[34rem]">
      <svg
        viewBox="0 0 640 288"
        className="h-auto w-full overflow-visible"
        role="img"
        aria-label={`Cases by severity: ${data.map(({ label, count }) => `${label}, ${count}`).join('; ')}`}
      >
        {Array.from({ length: 5 }, (_, index) => {
          const value = axisMaximum - (axisMaximum / 4) * index;
          const y = chart.top + (chart.height / 4) * index;
          return (
            <g key={index}>
              <line
                x1={chart.left}
                x2={chart.left + chart.width}
                y1={y}
                y2={y}
                stroke="var(--color-border)"
                strokeDasharray="2 7"
                strokeLinecap="round"
              />
              <text
                x={chart.left - 12}
                y={y + 4}
                textAnchor="end"
                fill="var(--color-text-muted)"
                fontSize="12"
              >
                {Math.round(value)}
              </text>
            </g>
          );
        })}
        {data.map(({ label, count }, index) => {
          const height = count === 0 ? 0 : (count / axisMaximum) * chart.height;
          const x = chart.left + slot * index + (slot - barWidth) / 2;
          const y = baseline - height;
          const bubbleWidth = 88;
          const bubbleHeight = 32;
          const bubbleX = x + barWidth / 2 - bubbleWidth / 2;
          const bubbleY = Math.max(2, y - bubbleHeight - 10);
          return (
            <g
              key={label}
              className="group"
              tabIndex={0}
              role="img"
              aria-label={`${label}: ${count} ${count === 1 ? 'case' : 'cases'}`}
            >
              <rect
                x={x}
                y={height === 0 ? baseline - 2 : y}
                width={barWidth}
                height={Math.max(2, height)}
                rx={barWidth / 2}
                fill="var(--color-text)"
              />
              <g className="pointer-events-none opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100">
                <rect x={bubbleX} y={bubbleY} width={bubbleWidth} height={bubbleHeight} rx="16" fill="var(--color-text)" />
                <text
                  x={x + barWidth / 2}
                  y={bubbleY + 21}
                  textAnchor="middle"
                  fill="var(--color-primary-text)"
                  fontSize="12"
                  fontWeight="600"
                >
                  {count} {count === 1 ? 'case' : 'cases'}
                </text>
              </g>
              <text
                x={x + barWidth / 2}
                y={baseline + 28}
                textAnchor="middle"
                fill="var(--color-text-secondary)"
                fontSize="12"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function UrgentCase({ item }: { item: CaseListItem }) {
  return (
    <Link
      to={`/cases/${item.id}`}
      className="grid min-h-16 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border py-3 last:border-0"
    >
      <span className="min-w-0">
        <span className="block break-anywhere text-13 font-semibold text-text">{item.title}</span>
        <span className="mt-1 block text-12 text-text-secondary">
          {item.first_alert_at ? formatIST(item.first_alert_at) : 'First alert time not available'}
        </span>
      </span>
      <CountdownBadge deadlineAt={item.deadline_at} status={item.status} />
    </Link>
  );
}

function OpenCaseRow({ item }: { item: CaseListItem }) {
  return (
    <tr className="group">
      <td className="max-w-[22rem] rounded-l-2xl bg-sunken px-4 py-4">
        <Link to={`/cases/${item.id}`} className="break-anywhere font-semibold text-text underline-offset-2 hover:underline">
          {item.title}
        </Link>
        <span className="mt-1 block text-12 text-text-secondary">
          {item.first_alert_at ? formatIST(item.first_alert_at) : 'First alert time not available'}
        </span>
      </td>
      <td className="whitespace-nowrap bg-sunken px-4 py-4"><SeverityBadge severity={item.severity} /></td>
      <td className="whitespace-nowrap bg-sunken px-4 py-4 text-13 font-semibold tabular-nums">
        <span title="Triage score from linked evidence">{item.score}</span>
        <InfoTip text="A prioritization aid from severity, linked evidence sources, entity overlap and time proximity. Review the case evidence before deciding." label={`How score ${item.score} is calculated`} />
      </td>
      <td className="whitespace-nowrap bg-sunken px-4 py-4 text-13">
        {item.sources_count} {item.sources_count === 1 ? 'source' : 'sources'}
      </td>
      <td className="whitespace-nowrap bg-sunken px-4 py-4 text-12 text-text-secondary">
        {item.first_alert_at ? formatIST(item.first_alert_at) : 'Not available'}
      </td>
      <td className="whitespace-nowrap bg-sunken px-4 py-4 text-13 capitalize">{item.status}</td>
      <td className="whitespace-nowrap rounded-r-2xl bg-sunken px-4 py-4">
        <CountdownBadge deadlineAt={item.deadline_at} status={item.status} />
      </td>
    </tr>
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

  const dashboard = query.data;
  const hasCases = Boolean(dashboard?.funnel.cases);
  const afterCleaning = dashboard
    ? Math.max(0, dashboard.funnel.ingested - dashboard.funnel.suppressed - dashboard.funnel.merged)
    : 0;
  const explanation = {
    ingested: 'Total alerts received by Prahari, including alerts later suppressed, merged or linked to cases.',
    suppressed: 'Routine or benign alerts kept out of case grouping. These alerts remain visible and can be restored.',
    merged: 'Duplicate alerts combined with an existing alert inside the deduplication window.',
    inCases: 'Alerts linked to the sample cases. One case can contain several alerts.',
    cases: 'Distinct evidence groups created for analyst review.',
    timeSaved: dashboard?.time_saved_note ?? 'Estimate based on the configured time saved per alert.',
  };

  return (
    <div className="space-y-6">
      {query.isLoading ? (
        <div className="space-y-6" aria-label="Loading dashboard" role="status">
          <span className="sr-only">Loading dashboard</span>
          <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <LoadingSkeleton rows={2} />
          </section>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(18rem,0.9fr)]">
            <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6"><LoadingSkeleton rows={4} /></section>
            <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6"><LoadingSkeleton rows={3} /></section>
          </div>
          <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6"><LoadingSkeleton rows={5} /></section>
        </div>
      ) : null}

      {query.isError ? (
        <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
          <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} />
        </section>
      ) : null}

      {dashboard && !hasCases ? (
        <>
          <section aria-labelledby="quick-stats-heading" className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <div className="grid gap-4 lg:grid-cols-[9rem_minmax(0,1fr)] lg:items-start lg:gap-6">
              <div className="lg:pt-1">
                <h1 id="quick-stats-heading" className="text-19 font-semibold tracking-heading">Quick Stats</h1>
                <p className="mt-2 max-w-[14rem] text-13 text-text-secondary">Alerts, evidence and review deadlines.</p>
                <span className="mt-4 block h-1 w-12 rounded-full bg-text" aria-hidden="true" />
              </div>
              <EmptyState
                title="No cases yet"
                body="Security teams at mid-size Indian firms receive more alerts than they can read. Load sample evidence to see how Prahari links alerts into cases for human review."
              />
            </div>
          </section>
          <section className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-16 font-semibold">Open cases</h2>
              <div className="flex flex-wrap gap-2">
                <span className="[&_button]:!border-text [&_button]:!bg-text [&_button]:hover:!bg-text/90">
                  <LoadDemoButton compact />
                </span>
                <QuietButton type="button" onClick={onReset}>
                  <RotateCcw size={15} aria-hidden="true" />Reset demo
                </QuietButton>
              </div>
            </div>
            <p className="mt-4 border-t border-border pt-4 text-13 text-text-secondary">Load the demo to see sample alert evidence grouped into four cases.</p>
          </section>
        </>
      ) : null}

      {dashboard && hasCases ? (
        <>
          <section aria-labelledby="quick-stats-heading" className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <div className="grid gap-4 lg:grid-cols-[9rem_minmax(0,1fr)] lg:items-start lg:gap-6">
              <div className="lg:pt-1">
                <h1 id="quick-stats-heading" className="text-19 font-semibold tracking-heading">Quick Stats</h1>
                <p className="mt-2 max-w-[14rem] text-13 text-text-secondary">Alert counts and review effort.</p>
                <span className="mt-4 block h-1 w-12 rounded-full bg-text" aria-hidden="true" />
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
                <StatCard
                  label="Alerts ingested"
                  value={dashboard.funnel.ingested.toLocaleString('en-IN')}
                  explanation={explanation.ingested}
                  Icon={Inbox}
                  testId="funnel-ingested"
                />
                <StatCard
                  label="Suppressed"
                  value={dashboard.funnel.suppressed.toLocaleString('en-IN')}
                  explanation={explanation.suppressed}
                  Icon={Archive}
                />
                <StatCard
                  label="Merged"
                  value={dashboard.funnel.merged.toLocaleString('en-IN')}
                  explanation={explanation.merged}
                  Icon={CopyCheck}
                />
                <StatCard
                  label="In cases"
                  value={dashboard.funnel.in_cases.toLocaleString('en-IN')}
                  explanation={explanation.inCases}
                  Icon={Layers3}
                  testId="funnel-in-cases"
                />
                <StatCard
                  label="Cases"
                  value={dashboard.funnel.cases.toLocaleString('en-IN')}
                  explanation={explanation.cases}
                  Icon={BriefcaseBusiness}
                  testId="funnel-cases"
                  highlighted
                />
                <StatCard
                  label="Time saved estimate"
                  value={`${dashboard.time_saved_minutes.toLocaleString('en-IN')} min`}
                  explanation={explanation.timeSaved}
                  Icon={Clock3}
                />
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-border pt-3 text-12 text-text-secondary">
              <span>
                Cleaning kept {dashboard.funnel.suppressed.toLocaleString('en-IN')} routine alerts out and merged {dashboard.funnel.merged.toLocaleString('en-IN')} duplicates. Each group remains available in Suppressed.
              </span>
              <span data-testid="funnel-after-cleaning" className="text-text-muted">
                After cleaning: {afterCleaning.toLocaleString('en-IN')} alerts remain.
              </span>
              <InfoTip
                text={`${dashboard.funnel.ingested.toLocaleString('en-IN')} ingested minus ${dashboard.funnel.suppressed.toLocaleString('en-IN')} suppressed and ${dashboard.funnel.merged.toLocaleString('en-IN')} merged alerts.`}
                label="How the after-cleaning number is calculated"
              />
            </div>
          </section>

          <div className="grid items-stretch gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(19rem,0.9fr)]">
            <section aria-labelledby="statistics-heading" className="min-w-0 overflow-hidden rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 id="statistics-heading" className="text-19 font-semibold tracking-heading">Statistics</h2>
                  <p className="mt-1 text-12 text-text-secondary">Open cases by severity</p>
                </div>
                <span className="inline-flex items-center gap-2 text-12 text-text-secondary">
                  <span className="h-2.5 w-2.5 rounded-full bg-text" aria-hidden="true" />
                  Cases
                  <InfoTip text="Counts the cases currently grouped by low, medium, high and critical severity." label="About the severity chart" />
                </span>
              </div>
              <div className="overflow-x-auto pb-1">
                <SeverityChart values={dashboard.cases_by_severity} />
              </div>
            </section>

            <section aria-labelledby="urgent-heading" className="rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div>
                  <h2 id="urgent-heading" className="text-19 font-semibold tracking-heading">Most urgent cases</h2>
                  <p className="mt-1 text-12 text-text-secondary">Next cases to review</p>
                </div>
                <Link to="/cases" className="text-12 font-medium text-text-secondary underline underline-offset-2 hover:text-text">All cases</Link>
              </div>
              {dashboard.open_cases.length ? (
                <ul>
                  {dashboard.open_cases.slice(0, 3).map((item) => (
                    <li key={item.id}><UrgentCase item={item} /></li>
                  ))}
                </ul>
              ) : (
                <p className="border-t border-border py-4 text-13 text-text-secondary">No open cases need review.</p>
              )}
            </section>
          </div>

          <section aria-labelledby="cases-heading" className="min-w-0 rounded-3xl bg-surface p-5 shadow-sm sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 id="cases-heading" className="text-19 font-semibold tracking-heading">Open cases</h2>
                <p className="mt-1 text-12 text-text-secondary">Evidence groups awaiting analyst review.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="[&_button]:!border-text [&_button]:!bg-text [&_button]:hover:!bg-text/90">
                  <LoadDemoButton compact />
                </span>
                <QuietButton type="button" onClick={onReset} disabled={reset.isPending}>
                  <RotateCcw size={15} aria-hidden="true" />
                  {reset.isPending ? 'Resetting…' : 'Reset demo'}
                </QuietButton>
              </div>
            </div>
            <span className="sr-only" role="heading" aria-level={2}>Alert flow</span>
            {dashboard.open_cases.length ? (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] border-separate border-spacing-y-2 text-left text-13">
                    <thead>
                      <tr className="text-12 text-text-secondary">
                        <th scope="col" className="px-4 pb-1 font-medium">Title</th>
                        <th scope="col" className="px-4 pb-1 font-medium">Severity</th>
                        <th scope="col" className="px-4 pb-1 font-medium">Score</th>
                        <th scope="col" className="px-4 pb-1 font-medium">Sources</th>
                        <th scope="col" className="px-4 pb-1 font-medium">First seen (IST)</th>
                        <th scope="col" className="px-4 pb-1 font-medium">Status</th>
                        <th scope="col" className="px-4 pb-1 font-medium">Countdown</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.open_cases.map((item) => <OpenCaseRow key={item.id} item={item} />)}
                    </tbody>
                  </table>
                </div>
                <div className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
                  <span className="text-12 text-text-secondary">{dashboard.open_cases.length} cases · first-seen times shown in IST</span>
                  <Link to="/cases" className="text-13 font-medium text-text underline underline-offset-2">View all cases</Link>
                </div>
              </>
            ) : (
              <p className="border-t border-border py-4 text-13 text-text-secondary">No open cases. Dismissed and reported cases remain available in the cases list.</p>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
