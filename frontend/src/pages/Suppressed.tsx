import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function Suppressed() {
  return (
    <>
      <PageHeader title="Suppressed and merged alerts" description="Everything Prahari dropped stays visible here with the reason, and can be restored." />
      <EmptyState title="Nothing dropped yet" body="Alerts that match a benign rule or duplicate another alert appear here." />
    </>
  );
}