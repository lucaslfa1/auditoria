import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { apiErrorEventTarget } from '../lib/apiClient';

type ToastVariant = 'success' | 'error' | 'warning' | 'info';

interface ToastInput {
  title: string;
  description?: string;
  variant?: ToastVariant;
  durationMs?: number;
}

interface ToastRecord extends ToastInput {
  id: number;
}

interface ToastContextValue {
  showToast: (toast: ToastInput) => number;
  dismissToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastCounter = 0;

const toastIcons = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
} satisfies Record<ToastVariant, typeof CheckCircle2>;

function ToastCard({
  toast,
  onDismiss,
}: {
  toast: ToastRecord;
  onDismiss: (id: number) => void;
}) {
  const Icon = toastIcons[toast.variant ?? 'info'];

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      onDismiss(toast.id);
    }, toast.durationMs ?? 3800);

    return () => window.clearTimeout(timeoutId);
  }, [onDismiss, toast.durationMs, toast.id]);

  return (
    <div className={`toast-panel toast-${toast.variant ?? 'info'} animate-fade-in reveal-soft`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-full border border-white/10 bg-white/5 p-2">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-white theme-light:text-slate-900">
            {toast.title}
          </p>
          {toast.description ? (
            <p className="mt-1 text-xs leading-relaxed text-slate-300 theme-light:text-slate-700">
              {toast.description}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => onDismiss(toast.id)}
          aria-label="Fechar notificação"
          className="rounded-full p-1 text-slate-500 transition-colors hover:bg-white/5 hover:text-white theme-light:text-slate-600 theme-light:hover:bg-slate-100 theme-light:hover:text-slate-900"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((toast: ToastInput) => {
    const id = ++toastCounter;
    setToasts((current) => {
      const isDuplicate = current.some(
        (t) => t.title === toast.title && t.description === toast.description
      );
      
      if (isDuplicate) {
        return current;
      }

      const newToasts = [
        ...current,
        {
          id,
          variant: toast.variant ?? 'info',
          durationMs: toast.durationMs ?? 3000,
          title: toast.title,
          description: toast.description,
        },
      ];
      
      return newToasts.slice(-3);
    });
    return id;
  }, []);

  const value = useMemo(
    () => ({
      showToast,
      dismissToast,
    }),
    [dismissToast, showToast],
  );

  useEffect(() => {
    const handleApiError = (event: Event) => {
      const customEvent = event as CustomEvent<{ message: string; status: number; path: string }>;
      showToast({
        title: customEvent.detail.status === 0 ? 'Erro de Conexão' : 'Erro no Servidor',
        description: customEvent.detail.message,
        variant: 'error',
        durationMs: 5000,
      });
    };

    apiErrorEventTarget.addEventListener('apiError', handleApiError);
    return () => {
      apiErrorEventTarget.removeEventListener('apiError', handleApiError);
    };
  }, [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack safe-area-overlay" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={dismissToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}
