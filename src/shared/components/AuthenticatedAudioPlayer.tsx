import { forwardRef, useEffect, useState, useRef } from 'react';
import { Loader2, RefreshCw, Volume2, XCircle } from 'lucide-react';
import { ApiError, apiFetchBlob } from '../lib/apiClient';

interface AuthenticatedAudioPlayerProps extends React.AudioHTMLAttributes<HTMLAudioElement> {
  audioUrl: string;
  autoLoad?: boolean;
}

const isBrowserObjectUrl = (url: string) => url.startsWith('blob:') || url.startsWith('data:');

const describeAudioError = (error: unknown): string => {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'Gravação não disponível no servidor.';
    if (error.status === 403) return 'Sem permissão para acessar esta gravação.';
    if (error.status === 401) return 'Sessão expirada — faça login novamente.';
    if (error.status === 408 || error.status === 0) return 'Falha de conexão ao carregar o áudio.';
    if (error.status >= 500) return 'Erro no servidor ao carregar o áudio.';
    return `Erro ao carregar o áudio (${error.status}).`;
  }
  return 'Não foi possível carregar o áudio.';
};

export const AuthenticatedAudioPlayer = forwardRef<HTMLAudioElement, AuthenticatedAudioPlayerProps>(
  ({ audioUrl, autoLoad = true, className = "w-full rounded-lg", ...props }, ref) => {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [loadState, setLoadState] = useState<'idle' | 'loading' | 'ready' | 'error'>(autoLoad ? 'loading' : 'idle');
    const [errorMessage, setErrorMessage] = useState<string>('Não foi possível carregar o áudio.');
    const [retryToken, setRetryToken] = useState(0);
    const [requestedUrl, setRequestedUrl] = useState<string | null>(() => (autoLoad ? audioUrl : null));
    const blobUrlRef = useRef<string | null>(null);

    useEffect(() => {
      let cancelled = false;
      const controller = new AbortController();

      if (autoLoad && requestedUrl !== audioUrl) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setRequestedUrl(audioUrl);
        return () => {
          cancelled = true;
          controller.abort();
        };
      }

      if (requestedUrl !== audioUrl) {
        setBlobUrl(null);
        setLoadState('idle');
        return () => {
          cancelled = true;
          controller.abort();
        };
      }

      const load = async () => {
        try {
          if (isBrowserObjectUrl(audioUrl)) {
            setBlobUrl(audioUrl);
            setLoadState('ready');
            return;
          }
          const blob = await apiFetchBlob(audioUrl, { signal: controller.signal });
          if (cancelled) return;
          const url = URL.createObjectURL(blob);
          blobUrlRef.current = url;
          setBlobUrl(url);
          setLoadState('ready');
        } catch (err) {
          if (cancelled || controller.signal.aborted) return;
          console.error('[AuthenticatedAudioPlayer] Falha ao carregar áudio', { audioUrl, error: err });
          setErrorMessage(describeAudioError(err));
          setLoadState('error');
        }
      };

      setLoadState('loading');
      load();

      return () => {
        cancelled = true;
        controller.abort();
        if (blobUrlRef.current && !isBrowserObjectUrl(audioUrl)) {
          URL.revokeObjectURL(blobUrlRef.current);
          blobUrlRef.current = null;
        }
      };
    }, [audioUrl, autoLoad, requestedUrl, retryToken]);

    const requestAudioLoad = () => {
      setRequestedUrl(audioUrl);
      setRetryToken((token) => token + 1);
    };

    if (loadState === 'idle') {
      return (
        <div className="flex w-full items-center justify-between gap-3 rounded-lg border border-white/10 bg-slate-800/40 px-4 py-3 text-sm text-slate-400 theme-light:bg-slate-100 theme-light:border-slate-200">
          <div className="flex items-center gap-2.5 min-w-0">
            <Volume2 size={15} className="shrink-0 text-primary-400" />
            <span className="truncate">Gravação disponível.</span>
          </div>
          <button
            type="button"
            onClick={requestAudioLoad}
            className="flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-300 transition hover:bg-white/10 hover:text-slate-100 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-700"
          >
            <Volume2 size={12} className="shrink-0" />
            Carregar
          </button>
        </div>
      );
    }

    if (loadState === 'loading') {
      return (
        <div className="flex w-full items-center gap-2.5 rounded-lg border border-white/10 bg-slate-800/40 px-4 py-3 text-sm text-slate-400 theme-light:bg-slate-100 theme-light:border-slate-200">
          <Loader2 size={15} className="animate-spin shrink-0" />
          Carregando gravação...
        </div>
      );
    }

    if (loadState === 'error') {
      return (
        <div className="flex w-full items-center justify-between gap-3 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <div className="flex items-center gap-2.5 min-w-0">
            <XCircle size={15} className="shrink-0" />
            <span className="truncate">{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={requestAudioLoad}
            className="flex items-center gap-1.5 rounded-md border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-300 transition hover:bg-red-500/20 hover:text-red-200"
          >
            <RefreshCw size={12} className="shrink-0" />
            Tentar novamente
          </button>
        </div>
      );
    }

    return (
      <audio
        ref={ref}
        key={blobUrl!}
        controls
        className={className}
        preload="auto"
        {...props}
      >
        <source src={blobUrl!} />
        Seu navegador não suporta o elemento de áudio.
      </audio>
    );
  }
);
AuthenticatedAudioPlayer.displayName = 'AuthenticatedAudioPlayer';
