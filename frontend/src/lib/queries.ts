/**
 * React Query data layer for the Prahari frontend (TanStack Query v5).
 * Typed hooks for every endpoint in src/lib/api.ts.
 */
import {
  keepPreviousData,
  QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import {
  getAlerts,
  getAudit,
  getCase,
  getCases,
  getDashboard,
  getHealth,
  getReport,
  getSettings,
  ingestFile,
  loadDemo,
  patchCaseDetectedAt,
  postCaseAction,
  postCaseReport,
  postReportSubmitted,
  putReport,
  putSettings,
  resetDemo,
  restoreAlert,
} from './api';
import type { ReportWithHistory, SettingsResponse } from './api';
import type { AlertStatus, CaseStatus, Pattern, Severity } from './types';

/*** Queries ***/

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: getHealth });

export const useDashboard = () => useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });

export const useCases = (params?: { severity?: Severity; status?: CaseStatus; pattern?: Pattern }) =>
  useQuery({
    queryKey: ['cases', params ?? {}],
    queryFn: () => getCases(params),
    placeholderData: keepPreviousData,
  });

export const useCase = (id: number) =>
  useQuery({ queryKey: ['case', id], queryFn: () => getCase(id), enabled: !!id });

export const useAlerts = (status?: AlertStatus) =>
  useQuery({ queryKey: ['alerts', status ?? 'all'], queryFn: () => getAlerts(status) });

export const useAudit = (params?: {
  action?: string;
  target_type?: string;
  target_id?: string;
  limit?: number;
}) => useQuery({ queryKey: ['audit', params ?? {}], queryFn: () => getAudit(params) });

export const useSettings = () =>
  useQuery<SettingsResponse>({ queryKey: ['settings'], queryFn: getSettings });

export const useReport = (id: number) =>
  useQuery<ReportWithHistory>({ queryKey: ['report', id], queryFn: () => getReport(id), enabled: !!id });

/*** Invalidation helper ***
 * Query keys match by prefix: ['case'] matches ['case', 7], but NOT ['cases'].
 * Every mutation writes an audit event, so most of them also refresh ['audit'].
 */
type Key = readonly unknown[];

const invalidateAll = (qc: QueryClient, keys: Key[]) =>
  Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })));

/*** Mutations ***/

export const useLoadDemo = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: loadDemo,
    onSuccess: () =>
      invalidateAll(qc, [['dashboard'], ['cases'], ['case'], ['alerts'], ['report'], ['audit']]),
  });
};

export const useResetDemo = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: resetDemo,
    onSuccess: () =>
      invalidateAll(qc, [['dashboard'], ['cases'], ['case'], ['alerts'], ['report'], ['audit']]),
  });
};

export const useIngestFile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ingestFile,
    onSuccess: () => invalidateAll(qc, [['dashboard'], ['cases'], ['case'], ['alerts'], ['audit']]),
  });
};

export const useCaseAction = (id: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { action: 'confirm' | 'dismiss' | 'escalate'; note: string; actor?: string }) =>
      postCaseAction(id, payload),
    onSuccess: () => invalidateAll(qc, [['case', id], ['cases'], ['dashboard'], ['audit']]),
  });
};

export const useCaseDetectedAt = (id: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { detected_at: string; reason: string }) => patchCaseDetectedAt(id, payload),
    onSuccess: () => invalidateAll(qc, [['case', id], ['cases'], ['dashboard'], ['audit']]),
  });
};

export const useCaseReport = (caseId: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postCaseReport(caseId),
    onSuccess: (report) =>
      invalidateAll(qc, [['case', caseId], ['cases'], ['report', report.id], ['audit']]),
  });
};

export const usePutReport = (reportId: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Parameters<typeof putReport>[1]) => putReport(reportId, payload),
    // Refetch instead of setQueryData: PUT returns a Report without `history`.
    onSuccess: () => invalidateAll(qc, [['report', reportId], ['audit']]),
  });
};

export const useReportSubmitted = (reportId: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { reference_number: string; submitted_by: string }) =>
      postReportSubmitted(reportId, payload),
    onSuccess: () =>
      invalidateAll(qc, [['report', reportId], ['case'], ['cases'], ['dashboard'], ['audit']]),
  });
};

export const useRestoreAlert = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: number) => restoreAlert(alertId),
    onSuccess: () => invalidateAll(qc, [['alerts'], ['cases'], ['case'], ['dashboard'], ['audit']]),
  });
};

export const usePutSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: putSettings,
    onSuccess: (data: SettingsResponse) => {
      qc.setQueryData<SettingsResponse>(['settings'], data); // full {settings, rules_yaml}
      return invalidateAll(qc, [['audit']]);
    },
  });
};

/** Pre-configured QueryClient for the app entry point (main.tsx). */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30 * 1000, retry: false },
    mutations: { retry: false },
  },
});