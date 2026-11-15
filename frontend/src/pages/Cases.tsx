import { useMemo } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import LoadDemoButton from '../components/LoadDemoButton';
import { CountdownBadge, ErrorState, FormField, InfoTip, LoadingSkeleton, SeverityBadge, StatusBadge, controlClass } from '../components/Ui';
import { errorDetail, useErrorToast } from '../components/Toast';
import { useCases } from '../lib/queries';
import type { CaseStatus, Pattern, Severity } from '../lib/types';
import { formatIST } from '../lib/time';

const severities: Severity[] = ['critical', 'high', 'medium', 'low'];
const statuses: CaseStatus[] = ['open', 'confirmed', 'dismissed', 'escalated', 'reported'];
const patterns: Array<{ value: Exclude<Pattern, null>; label: string }> = [
  { value: 'account_takeover_then_exfiltration', label: 'Account takeover and data export' },
  { value: 'ransomware_behaviour', label: 'Ransomware-like activity' },
  { value: 'phishing_to_compromise', label: 'Phishing to compromise' },
  { value: 'recon_then_access', label: 'Reconnaissance then access' },
];

const patternLabel = (pattern: Pattern) =>
  patterns.find((item) => item.value === pattern)?.label ?? 'No pattern linked';

export default function Cases() {
  const [search, setSearch] = useSearchParams();
  const navigate = useNavigate();
  const severityRaw = search.get('severity');
  const statusRaw = search.get('status');
  const patternRaw = search.get('pattern');
  const severity = severities.includes(severityRaw as Severity) ? severityRaw as Severity : undefined;
  const status = statuses.includes(statusRaw as CaseStatus) ? statusRaw as CaseStatus : undefined;
  const pattern = patterns.some((item) => item.value === patternRaw) ? patternRaw as Exclude<Pattern, null> : undefined;
  const query = useCases({ severity, status, pattern });
  useErrorToast(query.error);
  const items = useMemo(() => query.data?.filter((item) => patternRaw !== 'none' || item.pattern === null) ?? [], [query.data, patternRaw]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearch(next, { replace: true });
  };
  const clearFilters = () => setSearch({}, { replace: true });
  const openRow = (id: number) => navigate(`/cases/${id}`);

  return (
    <>
      <PageHeader title="Cases" description="Review related alerts together. The score is a triage aid, not a finding." />
      <section aria-label="Case filters" className="mb-5 grid gap-3 border-y border-border py-4 sm:grid-cols-3">
        <FormField label="Severity">
          <select className={controlClass()} value={severity ?? ''} onChange={(event) => setFilter('severity', event.target.value)}>
            <option value="">All severities</option>
            {severities.map((value) => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}
          </select>
        </FormField>
        <FormField label="Status">
          <select className={controlClass()} value={status ?? ''} onChange={(event) => setFilter('status', event.target.value)}>
            <option value="">All statuses</option>
            {statuses.map((value) => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}
          </select>
        </FormField>
        <FormField label="Pattern">
          <select className={controlClass()} value={patternRaw ?? ''} onChange={(event) => setFilter('pattern', event.target.value)}>
            <option value="">All patterns</option>
            <option value="none">No pattern linked</option>
            {patterns.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </FormField>
      </section>
      {query.isLoading ? <LoadingSkeleton rows={5} /> : null}
      {query.isError ? <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} /> : null}
      {query.data && items.length === 0 ? (
        severity || status || patternRaw ? (
          <div className="border-y border-border bg-surface px-5 py-6">
            <h2 className="text-16 font-semibold">No cases match these filters</h2>
            <p className="mt-1 text-13 text-text-secondary">Clear a filter to broaden the case list.</p>
            <button type="button" className="mt-3 min-h-10 rounded-sm border border-border-strong px-3 text-13 font-medium hover:bg-sunken" onClick={clearFilters}>Clear filters</button>
          </div>
        ) : (
          <EmptyState title="No cases yet" body="Load the sample cases to see linked alerts, scores and review deadlines.">
            <LoadDemoButton />
          </EmptyState>
        )
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="hidden overflow-x-auto lg:block">
            <table className="w-full border-collapse text-left text-13">
              <thead>
                <tr className="border-y border-border bg-sunken text-12 uppercase tracking-label text-text-secondary">
                  <th scope="col" className="px-3 py-3 font-semibold">Title</th>
                  <th scope="col" className="px-3 py-3 font-semibold">Severity</th>
                  <th scope="col" className="px-3 py-3 font-semibold">Score</th>
                  <th scope="col" className="px-3 py-3 font-semibold">Sources</th>
                  <th scope="col" className="px-3 py-3 font-semibold">First seen</th>
                  <th scope="col" className="px-3 py-3 font-semibold">Status</th>
                  <th scope="col" className="px-3 py-3 font-semibold">Deadline</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    tabIndex={0}
                    aria-label={`Open case: ${item.title}`}
                    onClick={() => openRow(item.id)}
                    onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openRow(item.id); } }}
                    className="cursor-pointer border-b border-border bg-surface hover:bg-sunken focus-visible:outline"
                  >
                    <td className="max-w-sm px-3 py-3">
                      <Link to={`/cases/${item.id}`} onClick={(event) => event.stopPropagation()} className="font-medium text-text underline-offset-2 hover:underline">
                        {item.title}
                      </Link>
                      <span className="mt-1 block text-12 text-text-muted">{patternLabel(item.pattern)}</span>
                    </td>
                    <td className="px-3 py-3"><SeverityBadge severity={item.severity} /></td>
                    <td className="px-3 py-3">
                      <span className="inline-flex items-center font-semibold tabular-nums" title="Triage score from linked evidence">{item.score}<InfoTip text="A prioritization aid from severity, evidence sources, entity overlap and time proximity. Review the case evidence before deciding." label={`How score ${item.score} is calculated`} /></span>
                    </td>
                    <td className="px-3 py-3 tabular-nums">{item.sources_count} {item.sources_count === 1 ? 'source' : 'sources'}</td>
                    <td className="whitespace-nowrap px-3 py-3">{item.first_alert_at ? formatIST(item.first_alert_at) : 'Not available'}</td>
                    <td className="px-3 py-3"><StatusBadge status={item.status} /></td>
                    <td className="whitespace-nowrap px-3 py-3"><CountdownBadge deadlineAt={item.deadline_at} status={item.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="divide-y divide-border border-y border-border lg:hidden">
            {items.map((item) => (
              <li key={item.id}>
                <Link to={`/cases/${item.id}`} className="block bg-surface px-3 py-4 hover:bg-sunken">
                  <span className="block break-anywhere font-semibold text-text">{item.title}</span>
                  <span className="mt-2 flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={item.severity} />
                    <StatusBadge status={item.status} />
                    <span className="text-12 text-text-secondary">Score {item.score}</span>
                    <span className="text-12 text-text-secondary">{item.sources_count} {item.sources_count === 1 ? 'source' : 'sources'}</span>
                  </span>
                  <span className="mt-2 flex flex-wrap items-center justify-between gap-2 text-12 text-text-secondary">
                    <span>{item.first_alert_at ? formatIST(item.first_alert_at) : 'Not available'}</span>
                    <CountdownBadge deadlineAt={item.deadline_at} status={item.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}
