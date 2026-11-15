import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function Ingest() {
  return (
    <>
      <PageHeader title="Ingest alerts" description="Upload JSON or CSV alerts, or load the demo set." />
      <EmptyState title="Nothing ingested yet" body="Upload a JSON or CSV file, or load the demo data." />
    </>
  );
}