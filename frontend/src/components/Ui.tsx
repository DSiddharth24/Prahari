import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { useCountdown } from '../lib/countdown';
import type { Alert, CaseStatus, CountdownState, Severity } from '../lib/types';
import {
  AlertTriangle,
  Cloud,
  Database,
  Globe,
  KeyRound,
  Mail,
  Shield,
  ShieldAlert,
  X,
} from 'lucide-react';

const severityStyles: Record<Severity, string> = {
  low: 'bg-chip-low-bg text-chip-low-fg',
  medium: 'bg-chip-medium-bg text-chip-medium-fg',
  high: 'bg-chip-high-bg text-chip-high-fg',
  critical: 'bg-chip-critical-bg text-chip-critical-fg',
};

const statusStyles: Record<CaseStatus, string> = {
  open: 'border-info text-info',
  confirmed: 'border-primary text-primary',
  dismissed: 'border-border-strong text-text-secondary',
  escalated: 'border-error text-error',
  reported: 'border-success text-success',
};

const countdownStyles: Record<CountdownState, string> = {
  green: 'bg-countdown-green-bg text-countdown-green-fg',
  amber: 'bg-countdown-amber-bg text-countdown-amber-fg',
  red: 'bg-countdown-red-bg text-countdown-red-fg',
  overdue: 'bg-countdown-overdue-bg text-countdown-overdue-fg',
  none: 'bg-sunken text-text-secondary',
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`inline-flex min-h-6 items-center rounded-full px-2.5 text-12 font-semibold capitalize ${severityStyles[severity]}`}>{severity}</span>;
}

export function StatusBadge({ status }: { status: CaseStatus }) {
  return <span className={`inline-flex min-h-6 items-center rounded-full border bg-surface px-2.5 text-12 font-medium capitalize ${statusStyles[status]}`}>{status.replaceAll('_', ' ')}</span>;
}

export function CountdownBadge({ deadlineAt, status = 'open', large = false }: {
  deadlineAt: string | null;
  status?: CaseStatus;
  large?: boolean;
}) {
  const countdown = useCountdown(deadlineAt, status);
  if (countdown.state === 'none') return <span className="text-13 text-text-muted">No active deadline</span>;
  return (
    <span className={`inline-flex items-center gap-2 rounded-full font-semibold tabular-nums ${large ? 'px-4 py-2 text-28' : 'px-2.5 py-1 text-12'} ${countdownStyles[countdown.state]}`}>
      {countdown.state === 'overdue' ? <AlertTriangle size={large ? 19 : 14} aria-hidden="true" /> : null}
      <span className={large ? 'countdown-numeral' : ''}>{countdown.state === 'overdue' ? countdown.formatted : `${countdown.formatted} left`}</span>
      <span className="sr-only">, {countdown.state} countdown</span>
    </span>
  );
}

export function Tooltip({ children, label }: { children: ReactNode; label: string }) {
  return (
    <span className="group relative inline-flex items-center">
      {children}
      <span role="tooltip" className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden w-64 -translate-x-1/2 rounded-sm bg-primary px-3 py-2 text-left text-12 font-normal leading-relaxed text-primary-text shadow-menu group-hover:block group-focus-within:block">
        {label}
      </span>
    </span>
  );
}

export function InfoTip({ text, label = 'More information' }: { text: string; label?: string }) {
  return (
    <Tooltip label={text}>
      <button type="button" aria-label={label} title={text} className="ml-1 inline-grid h-5 w-5 place-items-center rounded-full border border-border-strong text-12 font-semibold text-text-secondary hover:bg-sunken focus-visible:outline">
        i
      </button>
    </Tooltip>
  );
}

export function LoadingSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-label="Loading" role="status" className="space-y-3">
      <span className="sr-only">Loading data</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-12 animate-pulse border-b border-border bg-sunken" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="border-l-4 border-error bg-surface px-4 py-3">
      <p className="font-medium text-error">Could not load this view</p>
      <p className="mt-1 break-words text-13 text-text-secondary">{message}</p>
      <button type="button" onClick={onRetry} className="mt-3 min-h-10 rounded-sm border border-border-strong px-3 text-13 font-medium hover:bg-sunken">Try again</button>
    </div>
  );
}

export function FormField({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-13 font-medium text-text-secondary">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-12 text-text-muted">{hint}</span> : null}
    </label>
  );
}

export function controlClass(extra = ''): string {
  return `min-h-10 w-full rounded-sm border border-border-strong bg-surface px-3 py-2 text-14 text-text placeholder:text-text-muted ${extra}`;
}

export function Button({ children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-sm border border-primary bg-primary px-4 py-2 text-13 font-semibold text-primary-text transition-colors duration-micro hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-55 ${className}`}
    >
      {children}
    </button>
  );
}

export function QuietButton({ children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-sm border border-border-strong bg-surface px-3 py-2 text-13 font-medium text-text-secondary transition-colors duration-micro hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-55 ${className}`}
    >
      {children}
    </button>
  );
}

export function Modal({ title, children, onClose, describedBy }: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  describedBy?: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLElement>('textarea, input, select, button')?.focus();
    if (!dialog?.querySelector('textarea, input, select, button')) dialog?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const controls = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]'));
      if (!controls.length) {
        event.preventDefault();
        return;
      }
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previousFocus.current?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-40 grid place-items-center overflow-y-auto bg-primary/45 p-4" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-heading"
        aria-describedby={describedBy}
        tabIndex={-1}
        className="my-auto max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-md border border-border bg-surface p-5 shadow-modal"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="modal-heading" className="text-19 font-semibold tracking-heading">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close dialog" className="grid h-10 w-10 shrink-0 place-items-center rounded-sm text-text-secondary hover:bg-sunken">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const sourceIcons = {
  email_security: Mail,
  endpoint_av: ShieldAlert,
  firewall: Shield,
  identity_provider: KeyRound,
  cloud_audit: Cloud,
  dlp: Database,
} satisfies Record<Alert['source'], typeof Mail>;

const sourceNames: Record<Alert['source'], string> = {
  email_security: 'Email security',
  endpoint_av: 'Endpoint',
  firewall: 'Firewall',
  identity_provider: 'Identity provider',
  cloud_audit: 'Cloud audit',
  dlp: 'DLP',
};

export function SourceMark({ source, size = 17 }: { source: Alert['source']; size?: number }) {
  const Icon = sourceIcons[source] ?? Globe;
  return (
    <span className="inline-flex items-center gap-2 text-13 text-text-secondary">
      <Icon size={size} strokeWidth={1.8} aria-hidden="true" />
      {sourceNames[source]}
    </span>
  );
}
