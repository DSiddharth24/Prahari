import { useParams } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';

export default function CaseDetail() {
  const { id } = useParams();
  return (
    <>
      <PageHeader title={`Case ${id ?? ''}`} description="Timeline, score and decision for one possible incident." />
      <EmptyState title="Case details are not loaded" body="Evidence, score breakdown and the 6-hour countdown appear here." />
    </>
  );
}