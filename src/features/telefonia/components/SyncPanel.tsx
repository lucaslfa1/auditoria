import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Loader2, Pause, Play, Trash2, XCircle } from 'lucide-react';

import type { SyncResult, SyncStatus } from '../hooks/useTelefoniaSync';

type CollectionMode = 'retroativo' | 'manual' | 'ultima_sync';

interface SyncPanelProps {
  horasRetroativas: string;
  canSync: boolean;
  isSyncing: boolean;
  syncResult: SyncResult | null;
  status: SyncStatus | null;
  onTrigger: (window?: { beginAt?: string; endAt?: string; horasRetroativas?: string }) => void;
  onCancel: () => void;
  onPause: () => void;
  onResume: () => void;
  onClearReport: () => void;
  onResetLock: () => void;
}

const pad = (n: number) => String(n).padStart(2, '0');

const toLocalIsoMinutes = (date: Date): string =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;

const defaultBegin = (): string => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return toLocalIsoMinutes(d);
};

const defaultEnd = (): string => toLocalIsoMinutes(new Date());

const STORAGE_MODE_KEY = 'telefonia_collection_mode';
const STORAGE_RETROACTIVE_KEY = 'telefonia_retroactive_hours';
const STORAGE_BEGIN_AT_KEY = 'telefonia_manual_begin_at';
const STORAGE_END_AT_KEY = 'telefonia_manual_end_at';

const RETROACTIVE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '24', label: 'Últimas 24 horas' },
  { value: '12', label: 'Últimas 12 horas' },
  { value: '6', label: 'Últimas 6 horas' },
  { value: '4', label: 'Últimas 4 horas' },
  { value: '2', label: 'Últimas 2 horas' },
  { value: '1', label: 'Última 1 hora' },
  { value: '0.5', label: 'Últimos 30 minutos' },
];

const isCollectionMode = (value: string | null): value is CollectionMode =>
  value === 'retroativo' || value === 'manual';

const computeWindowSummary = (begin: string, end: string): string => {
  if (!begin || !end) return '';
  const beginDate = new Date(begin);
  const endDate = new Date(end);
  if (Number.isNaN(beginDate.getTime()) || Number.isNaN(endDate.getTime())) return '';
  const diffMs = endDate.getTime() - beginDate.getTime();
  if (diffMs <= 0) return 'Janela inválida: data inicial deve ser anterior à final.';
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  return `Período: ${hours}h ${pad(minutes)}m`;
};

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

const statusBadgeClass = (status: string | undefined) => {
  switch ((status || '').toLowerCase()) {
    case 'running':
      return 'bg-sky-500/10 border-sky-500/30 text-sky-400';
    case 'paused':
      return 'bg-amber-500/10 border-amber-500/30 text-amber-400';
    case 'cancelling':
      return 'bg-rose-500/10 border-rose-500/30 text-rose-400';
    case 'ok':
    case 'success':
      return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400';
    case 'failed':
    case 'error':
      return 'bg-red-500/10 border-red-500/30 text-red-400';
    case 'stub':
      return 'bg-amber-500/10 border-amber-500/30 text-amber-400';
    default:
      return 'bg-slate-500/10 border-slate-500/30 text-slate-400';
  }
};

export function SyncPanel({
  horasRetroativas,
  canSync,
  isSyncing,
  syncResult,
  status,
  onTrigger,
  onCancel,
  onPause,
  onResume,
  onClearReport,
  onResetLock,
}: SyncPanelProps) {
  const currentStatus = status?.status || 'idle';
  const statusMessage = status?.message || '';
  const isCronSync = statusMessage.toLowerCase().includes('cron') || statusMessage.toLowerCase().includes('background');

  const credentialsConfigured = status?.credentials?.configured ?? true;
  const missingFields = status?.credentials?.missing ?? [];
  const isCancelling = currentStatus === 'cancelling' || Boolean(status?.cancel_requested);
  const isPaused = currentStatus === 'paused';

  const [mode, setMode] = useState<CollectionMode>(() => {
    if (typeof window === 'undefined') return 'retroativo';
    const saved = window.localStorage.getItem(STORAGE_MODE_KEY);
    return isCollectionMode(saved) ? saved : 'retroativo';
  });
  const [retroactiveHours, setRetroactiveHours] = useState<string>(() => {
    if (typeof window === 'undefined') return '24';
    return window.localStorage.getItem(STORAGE_RETROACTIVE_KEY) || '24';
  });
  const [beginAt, setBeginAt] = useState<string>(() => {
    if (typeof window === 'undefined') return defaultBegin();
    return window.localStorage.getItem(STORAGE_BEGIN_AT_KEY) || defaultBegin();
  });
  const [endAt, setEndAt] = useState<string>(() => {
    if (typeof window === 'undefined') return defaultEnd();
    return window.localStorage.getItem(STORAGE_END_AT_KEY) || defaultEnd();
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_MODE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_RETROACTIVE_KEY, retroactiveHours);
  }, [retroactiveHours]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_BEGIN_AT_KEY, beginAt);
  }, [beginAt]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_END_AT_KEY, endAt);
  }, [endAt]);

  const windowSummary = useMemo(
    () => (mode === 'manual' ? computeWindowSummary(beginAt, endAt) : ''),
    [beginAt, endAt, mode],
  );
  const windowInvalid = windowSummary.startsWith('Janela inválida');

  const headerDescription = useMemo(() => {
    if (mode === 'manual') {
      return 'Escolha o intervalo desejado e baixe as ligações da Huawei.';
    }
    if (mode === 'retroativo') {
      if (retroactiveHours === '0.5') {
        return 'Busca chamadas do período de 30 minutos na VDN.';
      }
      if (retroactiveHours === '1') {
        return 'Busca chamadas do período de 1 hora na VDN.';
      }
      return `Busca chamadas do período de ${retroactiveHours} horas na VDN.`;
    }
    return `Usa configuração padrão do servidor (${horasRetroativas}h retroativas).`;
  }, [mode, retroactiveHours, horasRetroativas]);

  const handleTrigger = () => {
    if (mode === 'manual') {
      if (windowInvalid || !beginAt || !endAt) return;
      onTrigger({ beginAt, endAt });
      return;
    }
    if (mode === 'retroativo') {
      onTrigger({ horasRetroativas: retroactiveHours });
      return;
    }
    onTrigger();
  };

  const triggerDisabled =
    isSyncing || !canSync || (mode === 'manual' && (windowInvalid || !beginAt || !endAt));

  const radioRowClass = (active: boolean) =>
    `flex items-start gap-3 rounded-lg border px-3 py-3 transition-colors ${
      active
        ? 'border-primary-500/40 bg-primary-500/5 theme-light:bg-primary-50'
        : 'border-white/10 hover:border-white/20 theme-light:border-slate-200 theme-light:hover:border-slate-300'
    }`;

  return (
    <div className="space-y-6">
      <div className="panel-box bg-primary-500/5 border border-primary-500/20 rounded-2xl p-6 theme-light:bg-primary-50 theme-light:border-primary-200">
        <div className="flex items-start gap-3 mb-4">
          <Activity className="text-primary-500 shrink-0 mt-1" />
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white theme-light:text-slate-900">Download de ligações</h3>
            </div>
            <p className="text-sm text-slate-400 mt-1 theme-light:text-slate-600">{headerDescription}</p>
          </div>
        </div>

        <div className="mb-4 rounded-xl border border-white/10 bg-slate-900/40 p-4 theme-light:border-slate-300 theme-light:bg-white">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200 theme-light:text-slate-800 mb-3">
            Tipo de Download
          </div>

          <div className="space-y-2">
            <label className={radioRowClass(mode === 'retroativo')}>
              <input
                type="radio"
                name="collection-mode"
                value="retroativo"
                checked={mode === 'retroativo'}
                onChange={() => setMode('retroativo')}
                className="mt-1 accent-primary-500"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-slate-100 theme-light:text-slate-900">
                  Período retroativo
                </div>
                <p className="text-xs text-slate-400 theme-light:text-slate-600 mt-0.5">
                  Busca as ligações ocorridas no intervalo de horas selecionado abaixo.
                </p>
                {mode === 'retroativo' ? (
                  <select
                    value={retroactiveHours}
                    onChange={(e) => setRetroactiveHours(e.target.value)}
                    className="mt-2 w-full sm:w-64 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-900"
                  >
                    {RETROACTIVE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                ) : null}
              </div>
            </label>

            <label className={radioRowClass(mode === 'manual')}>
              <input
                type="radio"
                name="collection-mode"
                value="manual"
                checked={mode === 'manual'}
                onChange={() => setMode('manual')}
                className="mt-1 accent-primary-500"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-slate-100 theme-light:text-slate-900">
                  Intervalo manual
                </div>
                <p className="text-xs text-slate-400 theme-light:text-slate-600 mt-0.5">
                  Escolhe data/hora de início e fim.
                </p>
                {mode === 'manual' ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 theme-light:text-slate-600">
                        Início
                      </label>
                      <input
                        type="datetime-local"
                        value={beginAt}
                        onChange={(e) => setBeginAt(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-900"
                      />
                    </div>
                    <div>
                      <label className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 theme-light:text-slate-600">
                        Fim
                      </label>
                      <input
                        type="datetime-local"
                        value={endAt}
                        onChange={(e) => setEndAt(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-900"
                      />
                    </div>
                    <div className={`sm:col-span-2 text-xs ${windowInvalid ? 'text-rose-400' : 'text-slate-400 theme-light:text-slate-600'}`}>
                      {windowSummary}
                    </div>
                  </div>
                ) : null}
              </div>
            </label>


          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs mb-4">
          <span className={`px-2.5 py-1 rounded-full border font-semibold ${statusBadgeClass(currentStatus)}`}>
            Status: {currentStatus === 'running'
              ? (isCronSync ? 'Automático' : 'Manual')
              : currentStatus === 'paused'
                ? 'Pausada'
                : currentStatus === 'cancelling'
                  ? 'Cancelando'
                  : currentStatus}
          </span>
          {currentStatus === 'running' && (
            <span className="animate-pulse text-primary-400 font-medium">
              ({isCronSync ? 'Pipeline em background' : 'Sua solicitação manual'})
            </span>
          )}
          {currentStatus === 'paused' && (
            <span className="text-amber-400 font-medium">
              (Aguardando Retomar)
            </span>
          )}
          <span className="text-slate-500 theme-light:text-slate-600">
            Último início: {formatTimestamp(status?.started_at)}
          </span>
          {isSyncing && (
            <button
              onClick={onResetLock}
              className="ml-auto text-rose-400 hover:text-rose-300 underline underline-offset-2 transition-colors font-medium"
            >
              Destravar Coleta
            </button>
          )}
        </div>

        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          <button
            type="button"
            onClick={handleTrigger}
            disabled={triggerDisabled}
            className={`w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all ${
              isSyncing
                ? isPaused
                  ? 'bg-amber-500/30 text-amber-100 cursor-default'
                  : 'bg-primary-500/50 text-white cursor-wait'
                : canSync
                  ? 'bg-primary-500 hover:bg-primary-400 text-white shadow-lg hover:-translate-y-0.5'
                  : 'bg-slate-700 text-slate-400 cursor-not-allowed'
            }`}
          >
            {isSyncing ? (
              isPaused ? <Pause className="w-5 h-5" /> : <Loader2 className="w-5 h-5 animate-spin" />
            ) : <Play className="w-5 h-5 fill-current" />}
            {isSyncing
              ? (isCancelling ? 'Cancelando...' : isPaused ? 'Coleta pausada' : 'Coletando na Huawei...')
              : 'Puxar ligações agora'}
          </button>
          {isSyncing ? (
            isPaused ? (
              <button
                type="button"
                onClick={onResume}
                className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-4 text-sm font-bold text-emerald-300 transition hover:bg-emerald-500/20 theme-light:text-emerald-700"
              >
                <span className="inline-flex items-center justify-center gap-2 whitespace-nowrap">
                  <Play className="h-4 w-4 fill-current" />
                  Retomar
                </span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onPause}
                disabled={isCancelling}
                className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-4 text-sm font-bold text-amber-300 transition hover:bg-amber-500/20 disabled:cursor-wait disabled:opacity-60 theme-light:text-amber-700"
                title="Pausa a coleta — pode retomar depois sem perder progresso"
              >
                <span className="inline-flex items-center justify-center gap-2 whitespace-nowrap">
                  <Pause className="h-4 w-4" />
                  Pausar
                </span>
              </button>
            )
          ) : null}
          {isSyncing ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={isCancelling}
              className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-4 text-sm font-bold text-rose-300 transition hover:bg-rose-500/20 disabled:cursor-wait disabled:opacity-60 theme-light:text-rose-700"
              title="Cancela imediatamente — descarta o que ainda nao baixou"
            >
              <span className="inline-flex items-center justify-center gap-2 whitespace-nowrap">
                {isCancelling ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                Cancelar
              </span>
            </button>
          ) : null}
        </div>

        {syncResult ? (
          <div className="mt-6 p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 animate-fade-in relative group">
            <button
              onClick={onClearReport}
              className="absolute top-4 right-4 p-1.5 rounded-lg text-emerald-400/50 hover:bg-emerald-500/20 hover:text-emerald-300 transition-colors opacity-0 group-hover:opacity-100 theme-light:text-emerald-600/50 theme-light:hover:text-emerald-700"
              title="Limpar relatório"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <h4 className="text-sm font-bold text-emerald-400 mb-2 flex items-center gap-2 pr-8">
              <CheckCircle2 className="w-4 h-4" /> Relatório de execução
            </h4>
            <ul className="text-sm text-emerald-200/80 space-y-1 theme-light:text-emerald-800">
              {syncResult.message ? <li>• {syncResult.message}</li> : null}
              {typeof syncResult.baixadas === 'number' ? (
                <li>
                  • Novos áudios/chats baixados: <strong>{syncResult.baixadas}</strong>
                </li>
              ) : null}
              {typeof syncResult.enfileiradas === 'number' ? (
                <li>
                  • Enfileirados na triagem: <strong>{syncResult.enfileiradas}</strong>
                </li>
              ) : null}
              {typeof syncResult.chamadas_na_vdn === 'number' ? (
                <li>
                  • Chamadas encontradas na VDN: <strong>{syncResult.chamadas_na_vdn}</strong>
                </li>
              ) : null}
              {typeof syncResult.chamadas_no_manifest_obs === 'number' ? (
                <li>
                  • Chamadas encontradas no manifesto OBS: <strong>{syncResult.chamadas_no_manifest_obs}</strong>
                </li>
              ) : null}
              {typeof syncResult.chamadas_descobertas_total === 'number' ? (
                <li>
                  • Chamadas descobertas no total: <strong>{syncResult.chamadas_descobertas_total}</strong>
                </li>
              ) : null}
              {typeof syncResult.chamadas_validas_pos_filtro === 'number' ? (
                <li>
                  • Elegíveis após filtros: <strong>{syncResult.chamadas_validas_pos_filtro}</strong>
                </li>
              ) : null}
              {typeof syncResult.limite_downloads === 'number' ? (
                <li>
                  • Limite do ciclo: <strong>{syncResult.limite_downloads}</strong>
                </li>
              ) : null}
              {typeof syncResult.min_duracao_padrao_segundos === 'number' ? (
                <li>
                  • Duração mínima configurada: <strong>{syncResult.min_duracao_padrao_segundos}s</strong>
                </li>
              ) : null}
              {typeof syncResult.ignoradas_duracao_minima === 'number' ? (
                <li>
                  • Ignoradas por duração mínima: <strong>{syncResult.ignoradas_duracao_minima}</strong>
                </li>
              ) : null}
              {typeof syncResult.ignoradas_cota_mensal_pre_download === 'number'
                && syncResult.ignoradas_cota_mensal_pre_download > 0 ? (
                <li>
                  • Ignoradas por cota mensal atingida:{' '}
                  <strong className="text-yellow-600">{syncResult.ignoradas_cota_mensal_pre_download}</strong>
                </li>
              ) : null}
              {typeof syncResult.ignoradas_receptiva_setor_risco === 'number'
                && syncResult.ignoradas_receptiva_setor_risco > 0 ? (
                <li>
                  • Receptivas ignoradas (setor de risco):{' '}
                  <strong>{syncResult.ignoradas_receptiva_setor_risco}</strong>
                </li>
              ) : null}
              {typeof syncResult.ignoradas_receptiva_setor_desconhecido === 'number'
                && syncResult.ignoradas_receptiva_setor_desconhecido > 0 ? (
                <li>
                  • Receptivas ignoradas (setor desconhecido):{' '}
                  <strong>{syncResult.ignoradas_receptiva_setor_desconhecido}</strong>
                </li>
              ) : null}
              {typeof syncResult.candidatos_download === 'number' ? (
                <li>
                  • Candidatas selecionadas para download: <strong>{syncResult.candidatos_download}</strong>
                </li>
              ) : null}
              {typeof syncResult.tentativas_download === 'number' ? (
                <li>
                  • Tentativas novas de download: <strong>{syncResult.tentativas_download}</strong>
                </li>
              ) : null}
              {(typeof syncResult.obs_primary_tentativas === 'number'
                || typeof syncResult.fs_fallback_tentativas === 'number'
                || typeof syncResult.url_fallback_tentativas === 'number') ? (
                <li className="mt-1">
                  • Tentativas por método:
                  <ul className="ml-4 mt-1 space-y-0.5">
                    {typeof syncResult.obs_primary_tentativas === 'number' ? (
                      <li>
                        OBS direto: <strong>{syncResult.obs_primary_tentativas}</strong> tentadas,{' '}
                        <strong>{syncResult.obs_primary_hits ?? 0}</strong> sucesso,{' '}
                        <strong>{syncResult.obs_primary_misses ?? 0}</strong> falha
                      </li>
                    ) : null}
                    {typeof syncResult.fs_fallback_tentativas === 'number' ? (
                      <li>
                        FS fallback: <strong>{syncResult.fs_fallback_tentativas}</strong> tentadas,{' '}
                        <strong>{syncResult.fs_fallback_hits ?? 0}</strong> sucesso,{' '}
                        <strong>{syncResult.fs_fallback_misses ?? 0}</strong> falha
                      </li>
                    ) : null}
                    {typeof syncResult.url_fallback_tentativas === 'number' ? (
                      <li>
                        URL pré-assinada: <strong>{syncResult.url_fallback_tentativas}</strong> tentadas,{' '}
                        <strong>{syncResult.url_fallback_hits ?? 0}</strong> sucesso,{' '}
                        <strong>{syncResult.url_fallback_misses ?? 0}</strong> falha
                      </li>
                    ) : null}
                  </ul>
                </li>
              ) : null}
              {typeof syncResult.ignoradas_ja_sincronizadas === 'number' ? (
                <li>
                  • Já sincronizadas ignoradas: <strong>{syncResult.ignoradas_ja_sincronizadas}</strong>
                </li>
              ) : null}
              {syncResult.erros && syncResult.erros.length > 0 ? (
                <li className="text-rose-400 theme-light:text-rose-600 mt-2">
                  • Falhas de download: <strong>{syncResult.erros.length}</strong>
                  <ul className="ml-4 mt-1 space-y-1 list-disc opacity-80">
                    {syncResult.erros.slice(0, 5).map((e, idx) => (
                      <li key={idx} className="text-xs">{e}</li>
                    ))}
                    {syncResult.erros.length > 5 && (
                      <li className="text-xs italic">... e mais {syncResult.erros.length - 5} erros (ver logs)</li>
                    )}
                  </ul>
                </li>
              ) : null}
            </ul>
          </div>
        ) : null}
      </div>

      {!credentialsConfigured && (
        <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/10 flex gap-3 text-amber-200/80 text-sm theme-light:bg-amber-50 theme-light:text-amber-800 theme-light:border-amber-200">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 theme-light:text-amber-600" />
          <p>
            <strong>Credenciais incompletas:</strong> preencha {missingFields.join(', ') || 'os campos obrigatórios'} no
            cofre ao lado antes de disparar o sync.
          </p>
        </div>
      )}
    </div>
  );
}
