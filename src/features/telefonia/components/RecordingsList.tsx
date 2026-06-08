import { Fragment, useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Loader2, PhoneCall, RefreshCw, X } from 'lucide-react';

import { apiFetchJson } from '../../../shared/lib/apiClient';
import { AuthenticatedAudioPlayer } from '../../../shared/components/AuthenticatedAudioPlayer';
import { OriginBadge } from '../../../shared/lib/auditOrigin';
import { useToast } from '../../../shared/components/ToastProvider';

interface RecordingItem {
  id?: number | string;
  input_hash?: string;
  audio_path?: string;
  audio_url?: string | null;
  audio_available?: boolean;
  operator_name?: string;
  sector?: string;
  classification?: string;
  created_at?: string;
  call_started_at?: string | null;
  duration?: number | string;
  triage_status?: string;
  triage_status_label?: string;
  confianca?: number | null;
  precisa_revisao?: boolean;
  motivos_revisao?: string[];
  motivos_json?: string[] | string | null;
  classification_status?: 'pending' | 'processing' | 'done' | 'error' | null;
  classification_error?: string | null;
  can_send_to_triage?: boolean;
  metadata?: Record<string, unknown> | null;
  is_oficial?: boolean;
  [key: string]: unknown;
}

interface RecordingsResponse {
  items: RecordingItem[];
  total: number;
}

const formatTimestamp = (value: string | null | undefined): string => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('pt-BR', {
      timeZone: 'America/Sao_Paulo',
      dateStyle: 'short',
      timeStyle: 'short',
    });
  } catch {
    return value;
  }
};

const formatDuration = (value: number | string | undefined): string => {
  if (value === undefined || value === null || value === '') return '—';
  const seconds = typeof value === 'number' ? value : Number.parseInt(value, 10);
  if (Number.isNaN(seconds)) return '—';
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${String(rest).padStart(2, '0')}s`;
};

const TERMINAL_STATUSES = new Set(['audited', 'monthly_capped']);

const isTerminalStatus = (item: RecordingItem): boolean => {
  const status = String(item.triage_status || '').toLowerCase();
  return TERMINAL_STATUSES.has(status);
};

const getTerminalLabel = (item: RecordingItem): string => {
  const status = String(item.triage_status || '').toLowerCase();
  if (status === 'audited') return 'Auditada';
  if (status === 'monthly_capped') return 'Cota mensal';
  return item.triage_status_label || '';
};

const hasReviewReason = (value: unknown, reason: string): boolean => {
  if (Array.isArray(value)) {
    return value.some((item) => String(item) === reason);
  }
  return typeof value === 'string' && value.includes(reason);
};

export function RecordingsList() {
  const { showToast } = useToast();
  const [items, setItems] = useState<RecordingItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sendingHash, setSendingHash] = useState<string | null>(null);
  const [searchOperator, setSearchOperator] = useState('');

  const fetchItems = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const qs = searchOperator ? `?operator=${encodeURIComponent(searchOperator)}` : '';
      const data = await apiFetchJson<RecordingsResponse>(`/api/telefonia/recordings${qs}`);
      setItems(Array.isArray(data.items) ? data.items : []);
      setTotal(typeof data.total === 'number' ? data.total : 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao carregar gravações recentes.');
    } finally {
      setIsLoading(false);
    }
  }, [searchOperator]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Polling enquanto houver itens com classificacao pendente. Encerra automaticamente
  // quando todos terminam (done/error) ou quando a aba perde foco. Limite duro de 5min.
  useEffect(() => {
    const hasPending = items.some(
      (it) => it.classification_status === 'pending' || it.classification_status === 'processing',
    );
    if (!hasPending) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      if (Date.now() - startedAt > 5 * 60 * 1000) {
        window.clearInterval(interval);
        return;
      }
      if (typeof document !== 'undefined' && document.hidden) return;
      fetchItems();
    }, 4000);
    return () => window.clearInterval(interval);
  }, [items, fetchItems]);

  const handleDeleteRecord = useCallback(async (item: RecordingItem) => {
    const inputHash = String(item.input_hash || '').trim();
    if (!inputHash) return;
    
    if (!globalThis.confirm('Tem certeza que deseja remover esta gravação da fila?')) return;
    
    setSendingHash(inputHash);
    try {
      const result = await apiFetchJson<{ status?: string; message?: string; action?: string }>(
        `/api/telefonia/recordings/${encodeURIComponent(inputHash)}`,
        { method: 'DELETE' },
      );
      showToast({
        variant: 'success',
        title: 'Sucesso',
        description: result.message || 'Gravação removida da tela.',
      });
      await fetchItems();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Erro ao remover',
        description: err instanceof Error ? err.message : 'Não foi possível remover a gravação.',
      });
    } finally {
      setSendingHash(null);
    }
  }, [fetchItems, showToast]);

  const handleSendToTriage = useCallback(async (item: RecordingItem) => {
    const inputHash = String(item.input_hash || '').trim();
    if (!inputHash) return;
    
    setSendingHash(inputHash);
    try {
      const result = await apiFetchJson<{ status?: string; message?: string; success?: boolean }>(
        `/api/telefonia/recordings/${encodeURIComponent(inputHash)}/triage`,
        { method: 'POST' },
      );
      showToast({
        variant: 'success',
        title: 'Sucesso',
        description: result.message || 'Enviado para triagem.',
      });
      await fetchItems();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Erro ao enviar',
        description: err instanceof Error ? err.message : 'Não foi possível enviar para triagem.',
      });
    } finally {
      setSendingHash(null);
    }
  }, [fetchItems, showToast]);

  return (
    <div className="panel-box bg-slate-900 border border-white/10 rounded-2xl p-6 theme-light:bg-white theme-light:border-slate-300">
      <div className="flex items-center justify-between gap-3 mb-4 border-b border-white/10 pb-4 theme-light:border-slate-300">
        <div className="flex items-center gap-2">
          <PhoneCall className="text-primary-500 w-5 h-5" />
          <div>
            <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Gravações recentes da Huawei</h3>
            <p className="text-xs text-slate-400 theme-light:text-slate-600 mt-0.5">
              Itens vindos do último sync (enfileirados em Triagem). Total: {total}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <input
            type="text"
            placeholder="Buscar por operador..."
            value={searchOperator}
            onChange={(e) => setSearchOperator(e.target.value)}
            className="w-48 px-3 py-1.5 text-sm rounded-lg border border-slate-700 bg-slate-800 text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-primary-500 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
          />
          {items.some(it => !isTerminalStatus(it)) && (
            <button
              type="button"
              onClick={async () => {
                if (!globalThis.confirm('Tem certeza que deseja remover TODAS as ligações que estão aguardando triagem?')) return;
                setIsLoading(true);
                try {
                  const result = await apiFetchJson<{ status?: string; message?: string }>(
                    '/api/telefonia/recordings',
                    { method: 'DELETE' }
                  );
                  showToast({
                    variant: 'success',
                    title: 'Sucesso',
                    description: result.message || 'Fila limpa com sucesso.',
                  });
                  await fetchItems();
                } catch (err) {
                  showToast({
                    variant: 'error',
                    title: 'Erro ao limpar',
                    description: err instanceof Error ? err.message : 'Não foi possível limpar a fila.',
                  });
                  setIsLoading(false);
                }
              }}
              disabled={isLoading || sendingHash !== null}
              className="btn-ghost px-3 py-2 text-xs font-semibold flex items-center gap-2 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 disabled:opacity-50"
              title="Remove todas as ligações da tela que ainda não foram auditadas"
            >
              <X className="w-3.5 h-3.5" />
              Limpar Pendentes
            </button>
          )}
          <button
            type="button"
            onClick={fetchItems}
            disabled={isLoading}
            className="btn-ghost px-3 py-2 text-xs font-semibold flex items-center gap-2 disabled:opacity-50"
          >
            {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Atualizar
          </button>
        </div>
      </div>

      {error ? (
        <div className="p-4 rounded-xl border border-red-500/20 bg-red-500/10 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {isLoading && !error && items.length === 0 ? (
        <div className="flex items-center justify-center py-10 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : null}

      {!isLoading && !error && items.length === 0 ? (
        <div className="py-8 text-center text-sm text-slate-400 theme-light:text-slate-600">
          Nenhuma gravação vinda do Huawei ainda. Dispare o sync acima para popular esta lista.
        </div>
      ) : null}

      {!error && items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wide text-slate-500 theme-light:text-slate-600">
              <tr>
                <th className="py-2 pr-3 font-semibold">Início da ligação</th>
                <th className="py-2 pr-3 font-semibold">Operador</th>
                <th className="py-2 pr-3 font-semibold">Setor</th>
                <th className="py-2 pr-3 font-semibold">Duração</th>
                <th className="py-2 pr-3 font-semibold">Áudio</th>
                <th className="py-2 pr-3 font-semibold text-right">Fila</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 theme-light:divide-slate-200">
              {items.map((item, index) => {
                const inputHash = String(item.input_hash || item.id || index);
                const metadataAlert = typeof item.metadata?.alerta_previsto === 'string'
                  ? item.metadata.alerta_previsto
                  : '';
                const metadataAlertId = typeof item.metadata?.alert_id === 'string'
                  ? item.metadata.alert_id
                  : '';
                return (
                  <Fragment key={inputHash}>
                    <tr className="text-slate-200 theme-light:text-slate-800">
                      <td className="py-3 pr-3 whitespace-nowrap text-slate-400 theme-light:text-slate-600">
                        {formatTimestamp(item.call_started_at || item.created_at)}
                      </td>
                      <td className="py-3 pr-3">
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium">
                            {!item.operator_name || ['op mock', 'não identificado', 'nao identificado', 'desconhecido'].includes(String(item.operator_name).toLowerCase())
                              ? '—'
                              : item.operator_name}
                          </span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {item.metadata?.is_manual !== true && item.metadata?.is_manual !== 'true' && (
                              <OriginBadge criadoPor="automacao" size="sm" autoOnly />
                            )}
                            {item.is_oficial === false && (
                              <span className="inline-flex items-center rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-500 ring-1 ring-inset ring-amber-500/20">
                                Operador sem cadastro
                              </span>
                            )}
                            {(metadataAlert.includes('Auditavel') || metadataAlert.includes('Auditável') || metadataAlertId === 'INFORMATIVO') && (
                              <span className="inline-flex items-center rounded-md bg-slate-500/10 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 ring-1 ring-inset ring-slate-500/20">
                                Não Auditável
                              </span>
                            )}
                            {(hasReviewReason(item.motivos_json, 'verificar_setor') || hasReviewReason(item.metadata?.motivos_json, 'verificar_setor')) && (
                              <span className="inline-flex items-center rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-400 ring-1 ring-inset ring-blue-500/20">
                                Verificar Setor
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="py-3 pr-3">{item.sector || '—'}</td>
                      <td className="py-3 pr-3 whitespace-nowrap text-slate-400 theme-light:text-slate-600">
                        {formatDuration(item.duration as number | string | undefined)}
                      </td>
                      <td className="py-3 pr-3 min-w-[300px]">
                        {item.audio_url ? (
                          <AuthenticatedAudioPlayer
                            audioUrl={item.audio_url}
                            autoLoad={false}
                            className="w-full min-w-[280px] rounded-lg"
                          />
                        ) : (
                          <span className="inline-flex rounded-lg border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-300 theme-light:text-amber-800">
                            Áudio ausente
                          </span>
                        )}
                      </td>
                      <td className="py-3 pr-0 text-right">
                        <div className="flex flex-col items-end gap-1.5">
                          {isTerminalStatus(item) ? (
                            <span
                              className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-500/20 bg-slate-500/10 px-3 py-2 text-xs font-semibold text-slate-300 theme-light:text-slate-700"
                              title={getTerminalLabel(item)}
                            >
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              {getTerminalLabel(item)}
                            </span>
                          ) : null}
                          {item.can_send_to_triage ? (
                            <button
                              type="button"
                              onClick={() => handleSendToTriage(item)}
                              disabled={sendingHash === inputHash}
                              className="inline-flex items-center gap-1.5 rounded-lg border border-primary-500/30 bg-primary-500/10 px-3 py-1.5 text-xs font-semibold text-primary-400 transition hover:bg-primary-500/20 hover:text-primary-300 disabled:cursor-wait disabled:opacity-60 theme-light:border-primary-500/40 theme-light:bg-primary-50 theme-light:text-primary-700 theme-light:hover:bg-primary-100"
                              title="Enviar para Triagem"
                            >
                              Enviar para Triagem
                            </button>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => handleDeleteRecord(item)}
                            disabled={sendingHash === inputHash}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/20 hover:text-rose-200 disabled:cursor-wait disabled:opacity-60 theme-light:border-rose-500/40 theme-light:bg-rose-50 theme-light:text-rose-700 theme-light:hover:bg-rose-100 mt-1"
                            title="Remover ou arquivar gravação da fila"
                          >
                            <X className="w-3.5 h-3.5" />
                            Remover
                          </button>
                        </div>
                      </td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
