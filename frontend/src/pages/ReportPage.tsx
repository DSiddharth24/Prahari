import { useParams } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function ReportPage() {
  const { id } = useParams();
  return (
    <>
      <PageHeader title={`Report ${id ?? ''}`} description="Draft incident report for analyst review." />
      <EmptyState title="Report is not loaded" body="Editable fields, versions and PDF export appear here." />
    </>
  );
}