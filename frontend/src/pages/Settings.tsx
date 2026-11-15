import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function Settings() {
  return (
    <>
      <PageHeader title="Settings" description="Suppression rules, time windows and critical assets." />
      <EmptyState title="Settings are not loaded" body="Connect to the API or load the demo data to view and edit rules." />
    </>
  );
}