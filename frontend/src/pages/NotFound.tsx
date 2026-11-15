import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" description="That address does not match any screen." />
      <Link to="/" className="text-14 text-link-focus underline underline-offset-2">
        Back to the dashboard
      </Link>
    </>
  );
}