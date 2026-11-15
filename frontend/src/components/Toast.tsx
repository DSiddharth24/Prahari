import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { CircleCheck, CircleX, X } from 'lucide-react';

type ToastMessage = { id: number; text: string; tone: 'success' | 'error' };
type ToastContextValue = { notify: (text: string, tone?: ToastMessage['tone']) => void };

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const notify = useCallback((text: string, tone: ToastMessage['tone'] = 'success') => {
    const id = Date.now() + Math.random();
    setMessages((current) => [...current, { id, text, tone }]);
    window.setTimeout(() => {
      setMessages((current) => current.filter((message) => message.id !== id));
    }, 5000);
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="fixed right-4 top-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {messages.map((message) => (
          <div
            key={message.id}
            role={message.tone === 'error' ? 'alert' : 'status'}
            className={`flex items-start gap-2 border bg-surface px-3 py-3 shadow-menu ${
              message.tone === 'error' ? 'border-error text-error' : 'border-success text-success'
            }`}
          >
            {message.tone === 'error' ? <CircleX size={18} aria-hidden="true" /> : <CircleCheck size={18} aria-hidden="true" />}
            <p className="min-w-0 flex-1 text-13">{message.text}</p>
            <button type="button" className="rounded-full p-1 text-text-secondary hover:bg-sunken" onClick={() => setMessages((items) => items.filter((item) => item.id !== message.id))} aria-label="Dismiss message">
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside ToastProvider.');
  return context;
}

export function errorDetail(reason: unknown): string {
  if (reason && typeof reason === 'object' && 'detail' in reason && typeof reason.detail === 'string') {
    return reason.detail;
  }
  return reason instanceof Error ? reason.message : 'The request failed. Try again.';
}

export function useErrorToast(reason: unknown): void {
  const { notify } = useToast();
  const previous = useRef<unknown>(null);
  useEffect(() => {
    if (!reason) {
      previous.current = null;
      return;
    }
    if (previous.current !== reason) {
      previous.current = reason;
      notify(errorDetail(reason), 'error');
    }
  }, [reason, notify]);
}
