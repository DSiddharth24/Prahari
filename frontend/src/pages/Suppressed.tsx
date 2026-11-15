import { useSearchParams } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import LoadDemoButton from '../components/LoadDemoButton';
import { ErrorState, LoadingSkeleton, QuietButton, SeverityBadge, SourceMark } from '../components/Ui';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import { useAlerts, useDashboard, useRestoreAlert } from '../lib/queries';
import type { AlertStatus } from '../lib/types';
import { formatIST } from '../lib/time';

const tabs: Array<{ status: AlertStatus; label: string; caption: string }> = [
  { status: 'suppressed_benign', label: 'Suppressed', caption: 'Matched a benign rule' },
  { status: 'merged_duplicate', label: 'Merged', caption: 'Duplicate of another alert' },
  { status: 'unlinked_low_priority', label: 'Unlinked low priority', caption: 'No linked case evidence' },
];

export default function Suppressed() {
  const [search, setSearch] = useSearchParams();
  const requested = search.get('status') as AlertStatus | null;
  const active = tabs.some((tab) => tab.status === requested) ? requested as AlertStatus : tabs[0].status;
  const query = useAlerts(active);
  const dashboard = useDashboard();
  useErrorToast(query.error);
  useErrorToast(dashboard.error);
  const restore = useRestoreAlert();
  const { notify } = useToast();
  const setTab = (status: AlertStatus) => setSearch({ status }, { replace: true });
  const restoreToPipeline = async (id: number) => {
    try {
      await restore.mutateAsync(id);
      notify('Alert restored to the pipeline.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };
  const currentTab = tabs.find((tab) => tab.status === active) ?? tabs[0];

  return (
    <>
      <PageHeader title="Suppressed and merged alerts" description="Alerts removed from case grouping stay visible here. Restore one to return it to the pipeline." />
      <div role="tablist" aria-label="Alert group" className="mb-4 flex flex-wrap border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.status}
            type="button"
            role="tab"
            id={`tab-${tab.status}`}
            aria-selected={active === tab.status}
            aria-controls="alert-list-panel"
            onClick={() => setTab(tab.status)}
            className={`min-h-11 border-b-2 px-4 text-13 font-medium ${active === tab.status ? 'border-primary text-text' : 'border-transparent text-text-secondary hover:bg-sunken'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {query.isLoading ? <LoadingSkeleton rows={5} /> : null}
      {query.isError ? <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} /> : null}
      {query.data && !dashboard.data?.funnel.ingested && query.data.length === 0 ? (
        <EmptyState title="No sample alerts loaded" body="Load the sample set to inspect the reasons alerts were suppressed, merged or left unlinked.">
          <LoadDemoButton />
        </EmptyState>
      ) : null}
      {query.data && dashboard.data?.funnel.ingested ? (
        <section id="alert-list-panel" role="tabpanel" aria-labelledby={`tab-${active}`}>
          <p className="mb-3 text-13 text-text-secondary">{currentTab.caption}. The original source alert remains available in the evidence record.</p>
          {!query.data.length ? (
            <div className="border-y border-border py-5 text-13 text-text-secondary">No {currentTab.label.toLowerCase()} alerts. Restored alerts no longer appear in this list.</div>
          ) : (
            <ul className="divide-y divide-border border-y border-border">
              {query.data.map((alert) => (
                <li key={alert.id} className="grid gap-3 bg-surface px-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="break-anywhere font-semibold">{alert.title}</h2>
                      <SeverityBadge severity={alert.severity_raw ?? 'low'} />
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-12 text-text-secondary">
                      <SourceMark source={alert.source} size={14} />
                      <span>{formatIST(alert.timestamp)}</span>
                      <span>Alert {alert.id}</span>
                    </div>
                    <p className="mt-2 text-13 text-text-secondary">
                      Reason: {alert.suppression_reason ?? currentTab.caption}
                      {alert.duplicate_of ? ` · Duplicate of alert ${alert.duplicate_of} (${alert.duplicate_count} similar alerts)` : ''}
                    </p>
                  </div>
                  <QuietButton type="button" onClick={() => void restoreToPipeline(alert.id)} disabled={restore.isPending}>
                    Restore to pipeline
                  </QuietButton>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </>
  );
}
