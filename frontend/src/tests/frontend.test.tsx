// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';
import { installMockApi, restoreFetch } from '../mocks/fetch';
import { loadDemo, resetDemo } from '../mocks/store';

function renderApp(path: string) {
  window.history.replaceState({}, '', path);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  resetDemo();
  loadDemo();
  installMockApi();
});

afterEach(() => {
  cleanup();
  restoreFetch();
});

describe('mock-mode frontend', () => {
  it('renders the hero case with four timeline entries', async () => {
    renderApp('/cases/1001');
    const timeline = await screen.findByRole('region', { name: 'Evidence timeline' });
    expect(within(timeline).getAllByText(/View raw JSON evidence/)).toHaveLength(4);
  });

  it('labels every hero timeline time as IST', async () => {
    renderApp('/cases/1001');
    const timeline = await screen.findByRole('region', { name: 'Evidence timeline' });
    expect(within(timeline).getAllByText(/IST/).length).toBeGreaterThanOrEqual(4);
  });

  it('keeps the case action disabled when the note is empty or spaces only', async () => {
    renderApp('/cases/1001');
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));
    const submit = await screen.findByRole('button', { name: 'Confirm case' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Review note'), { target: { value: '   ' } });
    expect(submit).toBeDisabled();
  });

  it('shows the dashboard funnel values from demo data', async () => {
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Alert flow' })).toBeInTheDocument();
    expect(screen.getByTestId('funnel-ingested')).toHaveTextContent('400');
    expect(screen.getByTestId('funnel-after-cleaning')).toHaveTextContent('60');
    expect(screen.getByTestId('funnel-in-cases')).toHaveTextContent('40');
    expect(screen.getByTestId('funnel-cases')).toHaveTextContent('4');
    expect(screen.getByText(/Cleaning kept 280 routine alerts out and merged 60 duplicates/)).toBeInTheDocument();
  });

  it('filters the case list by severity', async () => {
    renderApp('/cases');
    expect((await screen.findAllByText('Account takeover followed by customer-data export')).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('Severity'), { target: { value: 'medium' } });
    expect((await screen.findAllByText('Repeated sign-in attempts on a dormant vendor account')).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.queryAllByText('Account takeover followed by customer-data export')).toHaveLength(0);
    });
  });

  it('saves a report as a new version in mock mode', async () => {
    renderApp('/reports/1402');
    expect(await screen.findByRole('heading', { name: 'CERT-In report · 1402' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Reporter name'), { target: { value: 'Riya Sen' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save as new version' }));
    expect(await screen.findByText('Version 2 · current')).toBeInTheDocument();
    expect(screen.getByText('Version 1')).toBeInTheDocument();
  });
});
