import { StrictMode, Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ToastProvider } from './shared/components/ToastProvider.tsx'
import { AuditCriteriaProvider } from './contexts/AuditCriteriaContext.tsx'
import { logToTelemetry } from './shared/lib/telemetry.ts'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Global telemetry for uncaught errors
window.addEventListener('error', (event) => {
  logToTelemetry('error', `[Window] Uncaught error: ${event.message}`, event.error?.stack);
});
window.addEventListener('unhandledrejection', (event) => {
  logToTelemetry('error', `[Window] Unhandled promise rejection: ${event.reason?.message || event.reason}`, event.reason?.stack);
});

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Application error:', error, info.componentStack);
    logToTelemetry('error', `[React] Root ErrorBoundary caught error: ${error.message}`, info.componentStack || error.stack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'sans-serif', color: '#e6eefc', background: '#09162d' }}>
          <div style={{ textAlign: 'center', maxWidth: 420, padding: 32 }}>
            <h1 style={{ fontSize: 24, marginBottom: 12 }}>Algo deu errado</h1>
            <p style={{ color: '#94a3b8', marginBottom: 24 }}>Ocorreu um erro inesperado. Tente recarregar a pagina.</p>
            <button onClick={() => window.location.reload()} style={{ padding: '10px 24px', borderRadius: 10, border: 'none', background: '#ff3d03', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>
              Recarregar
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AuditCriteriaProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AuditCriteriaProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
