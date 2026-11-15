import { useState } from 'react';
import { FileUp } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import LoadDemoButton from '../components/LoadDemoButton';
import { Button, ErrorState, LoadingSkeleton, QuietButton } from '../components/Ui';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import { useDashboard, useIngestFile } from '../lib/queries';
import type { LoadResult } from '../lib/api';

export default function Ingest() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<LoadResult | null>(null);
  const upload = useIngestFile();
  const dashboard = useDashboard();
  useErrorToast(dashboard.error);
  const { notify } = useToast();
  const chooseFile = (candidate: File | null) => {
    if (!candidate) {
      setFile(null);
    } else if (/\.(json|csv)$/i.test(candidate.name)) {
      setFile(candidate);
    } else {
      notify('Choose a JSON or CSV file.', 'error');
    }
  };
  const sendFile = async () => {
    if (!file) return;
    try {
      const outcome = await upload.mutateAsync(file);
      setResult(outcome);
      notify(`${outcome.ingest.new} new alerts received.`);
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };

  return (
    <>
      <PageHeader title="Ingest alerts" description="Bring JSON or CSV alerts into the review queue. Prahari groups evidence; it does not replace your source tools." />
      {dashboard.isLoading ? <LoadingSkeleton rows={3} /> : null}
      {dashboard.isError ? <ErrorState message={errorDetail(dashboard.error)} onRetry={() => void dashboard.refetch()} /> : null}
      {!dashboard.data?.funnel.ingested && !result ? (
        <EmptyState title="No alerts ingested yet" body="Start with the included sample set, or upload a file exported from an alert source.">
          <LoadDemoButton />
        </EmptyState>
      ) : (
        <div className="max-w-3xl space-y-7">
          <section aria-labelledby="upload-heading">
            <h2 id="upload-heading" className="mb-3 text-16 font-semibold">Upload alert file</h2>
            <label
              htmlFor="alert-file"
              className="flex min-h-44 cursor-pointer flex-col items-center justify-center border border-dashed border-border-strong bg-surface px-5 py-6 text-center hover:bg-sunken"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                const dropped = event.dataTransfer.files[0];
                if (dropped) chooseFile(dropped);
              }}
            >
              <FileUp size={24} className="mb-2 text-info" aria-hidden="true" />
              <span className="font-medium">Choose a JSON or CSV file</span>
              <span className="mt-1 text-12 text-text-secondary">Or drag a file here. The file stays in this browser session.</span>
              <input id="alert-file" type="file" accept=".json,.csv,application/json,text/csv" className="sr-only" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} />
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <span className="min-w-0 flex-1 break-anywhere text-13 text-text-secondary">{file?.name ?? 'No file selected'}</span>
              <Button type="button" onClick={sendFile} disabled={!file || upload.isPending}>
                {upload.isPending ? 'Ingesting alerts…' : 'Ingest file'}
              </Button>
              {file ? <QuietButton type="button" onClick={() => setFile(null)}>Clear file</QuietButton> : null}
            </div>
          </section>
          {result ? (
            <section aria-labelledby="ingest-result-heading" role="status" className="border-y border-border bg-surface px-4 py-4">
              <h2 id="ingest-result-heading" className="text-16 font-semibold">Ingest result</h2>
              <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                {[
                  ['Received', result.ingest.received],
                  ['New', result.ingest.new],
                  ['Already seen', result.ingest.already_seen],
                  ['Suppressed', result.pipeline.suppressed],
                  ['Merged', result.pipeline.merged],
                  ['Cases created', result.pipeline.cases_created],
                ].map(([label, count]) => (
                  <div key={label} className="border-l border-border-strong pl-3">
                    <dt className="text-12 text-text-secondary">{label}</dt>
                    <dd className="text-19 font-semibold tabular-nums">{count}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ) : null}
          <section className="border-t border-border pt-5">
            <h2 className="text-16 font-semibold">Try the sample alerts</h2>
            <p className="mt-1 mb-3 text-13 text-text-secondary">The sample set includes four linked cases and reviewable suppressed and merged alerts.</p>
            <LoadDemoButton />
          </section>
        </div>
      )}
    </>
  );
}
