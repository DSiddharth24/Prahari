import { useSearchParams } from 'react-router-dom';
import { Download } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import LoadDemoButton from '../components/LoadDemoButton';
import { Button, ErrorState, FormField, LoadingSkeleton, controlClass } from '../components/Ui';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import { exportAudit } from '../lib/api';
import { useAudit, useDashboard } from '../lib/queries';
import { formatIST } from '../lib/time';

export default function Audit() {
  const [search, setSearch] = useSearchParams();
  const action = search.get('action') ?? '';
  const targetType = search.get('target_type') ?? '';
  const targetId = search.get('target_id') ?? '';
  const query = useAudit({
    action: action || undefined,
    target_type: targetType || undefined,
    target_id: targetId || undefined,
    limit: 100,
  });
  const dashboard = useDashboard();
  useErrorToast(query.error);
  useErrorToast(dashboard.error);
  const { notify } = useToast();
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearch(next, { replace: true });
  };
  const downloadCsv = async () => {
    try {
      const file = await exportAudit('csv');
      const objectUrl = URL.createObjectURL(file.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = file.filename;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
      notify('Audit entries exported as CSV.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <PageHeader title="Audit log" description="Case decisions, report changes and alert restores are recorded with an actor and time." />
        <Button type="button" onClick={downloadCsv}><Download size={15} aria-hidden="true" />Export CSV</Button>
      </div>
      <section aria-label="Audit filters" className="mb-5 grid gap-3 rounded-3xl bg-surface p-5 shadow-sm sm:grid-cols-3">
        <FormField label="Action contains">
          <input className={controlClass()} value={action} onChange={(event) => setFilter('action', event.target.value)} placeholder="For example, confirm" />
        </FormField>
        <FormField label="Target type">
          <select className={controlClass()} value={targetType} onChange={(event) => setFilter('target_type', event.target.value)}>
            <option value="">All targets</option><option value="case">Case</option><option value="alert">Alert</option><option value="report">Report</option><option value="settings">Settings</option>
          </select>
        </FormField>
        <FormField label="Target ID">
          <input className={controlClass()} value={targetId} onChange={(event) => setFilter('target_id', event.target.value)} inputMode="numeric" />
        </FormField>
      </section>
      {query.isLoading ? <LoadingSkeleton rows={6} /> : null}
      {query.isError ? <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} /> : null}
      {query.data && !dashboard.data?.funnel.ingested && !query.data.length ? (
        <EmptyState title="No audit entries yet" body="Load the sample data or review a case action to see who changed what and when.">
          <LoadDemoButton />
        </EmptyState>
      ) : null}
      {query.data && query.data.length ? (
        <div className="overflow-x-auto rounded-3xl bg-surface p-4 shadow-sm">
          <table className="w-full min-w-[760px] border-separate border-spacing-y-2 text-left text-13">
            <thead>
              <tr className="bg-sunken text-12 uppercase tracking-label text-text-secondary">
                <th scope="col" className="px-3 py-3 font-semibold">Time</th>
                <th scope="col" className="px-3 py-3 font-semibold">Actor</th>
                <th scope="col" className="px-3 py-3 font-semibold">Action</th>
                <th scope="col" className="px-3 py-3 font-semibold">Target</th>
                <th scope="col" className="px-3 py-3 font-semibold">Details</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((event) => (
                <tr key={event.id} className="align-top">
                  <td className="whitespace-nowrap rounded-l-2xl bg-sunken px-3 py-4">{formatIST(event.timestamp)}</td>
                  <td className="break-anywhere bg-sunken px-3 py-4">{event.actor}</td>
                  <td className="bg-sunken px-3 py-4">{event.action.replaceAll('_', ' ')}</td>
                  <td className="whitespace-nowrap bg-sunken px-3 py-4">{event.target_type ?? '—'} {event.target_id ?? ''}</td>
                  <td className="max-w-sm break-anywhere rounded-r-2xl bg-sunken px-3 py-4 text-text-secondary">{typeof event.details === 'string' ? event.details : JSON.stringify(event.details ?? {})}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {query.data && !query.data.length && dashboard.data?.funnel.ingested ? (
        <p className="border-y border-border py-5 text-13 text-text-secondary">No audit entries match the current filters. Clear filters to broaden the list.</p>
      ) : null}
    </>
  );
}
