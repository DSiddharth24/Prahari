import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function Dashboard() {
  return (
    <>
      <PageHeader title="Dashboard" description="How many alerts came in and how many became cases." />
      <EmptyState title="No cases yet" body="Load the demo data to see alerts grouped into cases." />
    </>
  );
}