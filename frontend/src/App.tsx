import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Ingest from './pages/Ingest';
import Cases from './pages/Cases';
import CaseDetail from './pages/CaseDetail';
import ReportPage from './pages/ReportPage';
import Suppressed from './pages/Suppressed';
import Audit from './pages/Audit';
import Settings from './pages/Settings';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="ingest" element={<Ingest />} />
          <Route path="cases" element={<Cases />} />
          <Route path="cases/:id" element={<CaseDetail />} />
          <Route path="reports/:id" element={<ReportPage />} />
          <Route path="suppressed" element={<Suppressed />} />
          <Route path="audit" element={<Audit />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}