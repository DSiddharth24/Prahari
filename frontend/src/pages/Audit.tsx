import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function Audit() {
  return (
    <>
      <PageHeader title="Audit log" description="Every action in order. Entries cannot be edited or deleted." />
      <EmptyState title="No actions logged yet" body="Confirming, dismissing or escalating a case is recorded here." />
    </>
  );
}