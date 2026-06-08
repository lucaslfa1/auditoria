import { Component } from 'react';
import type { ReactNode, ErrorInfo } from 'react';
import { logToTelemetry } from '../lib/telemetry';

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Lightweight error boundary for lazy-loaded components.
 * Catches load failures (network errors, chunk 404s) and renders
 * a recovery UI instead of crashing the whole app.
 */
export class LazyErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[LazyErrorBoundary] ${this.props.fallbackLabel || 'Component'} failed:`, error, info.componentStack);
    logToTelemetry('error', `[React] LazyErrorBoundary caught error in ${this.props.fallbackLabel || 'Component'}: ${error.message}`, info.componentStack || error.stack);
  }

  handleRetry = () => {
    // If it's a chunk loading error (new version deployed), we need a full page reload
    // to fetch the new index.html with the new module hashes.
    if (this.state.error?.message?.includes('Failed to fetch dynamically imported module')) {
      window.location.reload();
      return;
    }
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="glass-panel rounded-2xl p-8 text-center max-w-md mx-auto mt-12">
          <div className="text-3xl mb-3">⚠️</div>
          <h2 className="text-lg font-semibold text-slate-200 mb-2">
            {this.state.error?.message?.includes('Failed to fetch dynamically imported module') 
              ? 'Nova versão detectada' 
              : `Falha ao carregar ${this.props.fallbackLabel || 'componente'}`}
          </h2>
          <p className="text-sm text-slate-400 mb-6">
            {this.state.error?.message?.includes('Failed to fetch dynamically imported module') 
              ? 'O sistema foi atualizado. Clique abaixo para recarregar a página e obter a versão mais recente.'
              : (this.state.error?.message || 'Ocorreu um erro inesperado.')}
          </p>
          <button
            onClick={this.handleRetry}
            className="px-5 py-2.5 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors text-sm"
          >
            Tentar Novamente
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
