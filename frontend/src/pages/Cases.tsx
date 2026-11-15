import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function Cases() {
  return (
    <>
      <PageHeader title="Cases" description="Related alerts grouped into possible incidents." />
      <EmptyState title="No cases yet" body="Load the demo data to see cases here." />
    </>
  );
}