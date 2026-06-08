import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

export interface HuaweiConfig {
  huawei_ccid: string;
  huawei_vdn: string;
  huawei_app_key: string;
  huawei_ak: string;
  huawei_sk: string;
  huawei_horas_retroativas: string;
}

export interface SyncResult {
  status?: string;
  message?: string;
  cancelado?: boolean;
  baixadas?: number;
  enfileiradas?: number;
  duplicadas?: number;
  operadores_considerados?: number;
  chamadas_na_vdn?: number;
  chamadas_no_manifest_obs?: number;
  chamadas_descobertas_total?: number;
  chamadas_validas_pos_filtro?: number;
  candidatos_download?: number;
  limite_downloads?: number;
  min_duracao_padrao_segundos?: number;
  max_duracao_padrao_segundos?: number;
  ignoradas_duracao_minima?: number;
  ignoradas_receptiva_setor_risco?: number;
  ignoradas_receptiva_setor_desconhecido?: number;
  ignoradas_ja_sincronizadas?: number;
  ignoradas_cota_mensal_pre_download?: number;
  tentativas_download?: number;
  obs_primary_tentativas?: number;
  obs_primary_hits?: number;
  obs_primary_misses?: number;
  obs_primary_pulado_sem_record_id?: number;
  fs_fallback_tentativas?: number;
  fs_fallback_hits?: number;
  fs_fallback_misses?: number;
  url_fallback_tentativas?: number;
  url_fallback_hits?: number;
  url_fallback_misses?: number;
  erros?: string[];
}

export interface SyncStatus {
  status: 'idle' | 'running' | 'cancelling' | 'cancelled' | 'paused' | 'ok' | 'failed' | 'stub' | string;
  started_at: string | null;
  finished_at: string | null;
  result: SyncResult | null;
  cancel_requested?: boolean;
  message?: string;
  credentials?: {
    configured: boolean;
    missing: string[];
    fields: Record<string, { has_value: boolean; from_env: boolean }>;
  };
}

const DEFAULT_CONFIG: HuaweiConfig = {
  huawei_ccid: '1',
  huawei_vdn: '170',
  huawei_app_key: '',
  huawei_ak: '',
  huawei_sk: '',
  huawei_horas_retroativas: '2',
};

const CONFIG_KEYS = Object.keys(DEFAULT_CONFIG) as Array<keyof HuaweiConfig>;

interface AutomationStatusLite {
  is_running?: boolean;
  is_cycle_running?: boolean;
  current_stage?: string | null;
  current_message?: string | null;
}

export function useTelefoniaSync() {
  const { showToast } = useToast();
  const [config, setConfig] = useState<HuaweiConfig>(DEFAULT_CONFIG);
  const [isLoadingConfig, setIsLoadingConfig] = useState(true);
  const [isSlowLoading, setIsSlowLoading] = useState(false);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [accessDeniedMessage, setAccessDeniedMessage] = useState<string | null>(null);
  const [automationStatus, setAutomationStatus] = useState<AutomationStatusLite | null>(null);
  const previousSyncStatusRef = useRef<string | null>(null);

  const fetchAutomationStatus = useCallback(async () => {
    try {
      const data = await apiFetchJson<AutomationStatusLite>('/api/automation/engine/status');
      setAutomationStatus({
        is_running: Boolean(data?.is_running),
        is_cycle_running: Boolean(data?.is_cycle_running),
        current_stage: data?.current_stage ?? null,
        current_message: data?.current_message ?? null,
      });
    } catch {
      // Status da automacao eh informativo; falhas silenciosas.
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    // v1.3.91: timer pra trocar mensagem do loading apos 4s e dar pista
    // ao usuario quando o request fica lento (ex: automacao consumindo
    // recursos no Cloud Run).
    const slowTimer = window.setTimeout(() => setIsSlowLoading(true), 4000);
    try {
      setIsLoadingConfig(true);
      setIsSlowLoading(false);
      const data = await apiFetchJson<Record<string, { valor?: string }>>('/api/configuracoes');
      setAccessDeniedMessage(null);
      setConfig({
        huawei_ccid: data.huawei_ccid?.valor || DEFAULT_CONFIG.huawei_ccid,
        huawei_vdn: data.huawei_vdn?.valor || DEFAULT_CONFIG.huawei_vdn,
        huawei_app_key: data.huawei_app_key?.valor || '',
        huawei_ak: data.huawei_ak?.valor || '',
        huawei_sk: data.huawei_sk?.valor || '',
        huawei_horas_retroativas: data.huawei_horas_retroativas?.valor || DEFAULT_CONFIG.huawei_horas_retroativas,
      });
      } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setAccessDeniedMessage('A coleta ad-hoc da Huawei é restrita a administradores. Faça login com um usuário admin para habilitar esta tela.');
        return;
      }
      showToast({
        variant: 'error',
        title: 'Erro ao carregar configurações',
        description: 'Não foi possível ler as credenciais Huawei do backend.',
      });
    } finally {
      window.clearTimeout(slowTimer);
      setIsSlowLoading(false);
      setIsLoadingConfig(false);
    }
  }, [showToast]);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiFetchJson<SyncStatus>('/api/telefonia/sync/status');
      setAccessDeniedMessage(null);
      setStatus(data);
      const isRunning = data.status === 'running' || data.status === 'cancelling' || data.status === 'paused';
      setIsSyncing(isRunning);

      if (!isRunning && data.result) {
        setSyncResult(data.result);
      }

      if (
        (previousSyncStatusRef.current === 'running'
          || previousSyncStatusRef.current === 'cancelling'
          || previousSyncStatusRef.current === 'paused')
        && !isRunning
        && data.result
      ) {
        const isFailure = data.status === 'failed' || String(data.result.status || '').toLowerCase() === 'error';
        const isCancelled = data.status === 'cancelled' || String(data.result.status || '').toLowerCase() === 'cancelled';
        showToast({
          variant: isFailure ? 'error' : isCancelled ? 'info' : 'success',
          title: isFailure ? 'Sync concluído com falha' : isCancelled ? 'Coleta cancelada' : 'Sync concluído',
          description: data.result.message || 'Coleta finalizada.',
        });
      }

      previousSyncStatusRef.current = data.status;
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setAccessDeniedMessage('A coleta ad-hoc da Huawei é restrita a administradores. Faça login com um usuário admin para habilitar esta tela.');
      }
      // Status é informativo; silencie erros transitórios.
    }
  }, [showToast]);

  useEffect(() => {
    fetchConfig();
    fetchStatus();
    fetchAutomationStatus();
  }, [fetchConfig, fetchStatus, fetchAutomationStatus]);

  // Polling do status de automacao enquanto a tela esta aberta. Permite a UI
  // mostrar/esconder banner de "automacao rodando" sem o usuario refresh.
  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetchAutomationStatus();
    }, 8000);
    return () => window.clearInterval(intervalId);
  }, [fetchAutomationStatus]);

  useEffect(() => {
    if (
      !isSyncing
      && status?.status !== 'running'
      && status?.status !== 'cancelling'
      && status?.status !== 'paused'
    ) {
      return;
    }

    const intervalId = window.setInterval(() => {
      fetchStatus();
    }, 5000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [fetchStatus, isSyncing, status?.status]);

  const cancelManualSync = useCallback(async () => {
    try {
      const result = await apiFetchJson<{ status?: string; message?: string; result?: SyncResult }>(
        '/api/telefonia/sync/cancel',
        { method: 'POST' },
      );
      setStatus((prev) => ({
        ...(prev ?? {
          started_at: null,
          finished_at: null,
          result: null,
          credentials: undefined,
        }),
        status: result.status || 'cancelling',
        cancel_requested: true,
      }));
      showToast({
        variant: 'info',
        title: 'Cancelamento imediato',
        description: result.message || 'Coleta sendo interrompida agora.',
      });
      fetchStatus();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Falha ao cancelar',
        description: err instanceof Error ? err.message : 'Não foi possível solicitar o cancelamento.',
      });
    }
  }, [fetchStatus, showToast]);

  const pauseManualSync = useCallback(async () => {
    try {
      const result = await apiFetchJson<{ status?: string; message?: string; result?: SyncResult }>(
        '/api/telefonia/sync/pause',
        { method: 'POST' },
      );
      setStatus((prev) => ({
        ...(prev ?? {
          started_at: null,
          finished_at: null,
          result: null,
          credentials: undefined,
        }),
        status: result.status || 'paused',
      }));
      showToast({
        variant: 'info',
        title: 'Coleta pausada',
        description: result.message || 'Use Retomar para continuar.',
      });
      fetchStatus();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Falha ao pausar',
        description: err instanceof Error ? err.message : 'Não foi possível pausar a coleta.',
      });
    }
  }, [fetchStatus, showToast]);

  const resumeManualSync = useCallback(async () => {
    try {
      const result = await apiFetchJson<{ status?: string; message?: string; result?: SyncResult }>(
        '/api/telefonia/sync/resume',
        { method: 'POST' },
      );
      setStatus((prev) => ({
        ...(prev ?? {
          started_at: null,
          finished_at: null,
          result: null,
          credentials: undefined,
        }),
        status: result.status || 'running',
      }));
      showToast({
        variant: 'info',
        title: 'Coleta retomada',
        description: result.message || 'A coleta voltou a rodar.',
      });
      fetchStatus();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Falha ao retomar',
        description: err instanceof Error ? err.message : 'Não foi possível retomar a coleta.',
      });
    }
  }, [fetchStatus, showToast]);

  const clearSyncReport = useCallback(async () => {
    try {
      await apiFetchJson('/api/telefonia/sync/clear', { method: 'POST' });
      setSyncResult(null);
      showToast({
        variant: 'success',
        title: 'Relatório limpo',
        description: 'O relatório de execução foi removido da tela.',
      });
      fetchStatus();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Erro ao limpar',
        description: err instanceof Error ? err.message : 'Não foi possível limpar o relatório.',
      });
    }
  }, [fetchStatus, showToast]);

  const updateField = useCallback((key: keyof HuaweiConfig, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }, []);

  const saveConfig = useCallback(async () => {
    try {
      setIsSavingConfig(true);
      for (const key of CONFIG_KEYS) {
        await apiFetchJson('/api/configuracoes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chave: key, valor: config[key] }),
        });
      }
      showToast({
        variant: 'success',
        title: 'Cofre atualizado',
        description: 'Credenciais Huawei salvas com segurança.',
      });
      fetchStatus();
    } catch {
      showToast({
        variant: 'error',
        title: 'Falha ao salvar',
        description: 'Não foi possível persistir as credenciais.',
      });
    } finally {
      setIsSavingConfig(false);
    }
  }, [config, fetchStatus, showToast]);

  const triggerManualSync = useCallback(async (window?: { beginAt?: string; endAt?: string; horasRetroativas?: string }) => {
    // Sem pre-check de credenciais aqui: o backend valida e devolve um 400 com
    // a lista exata de campos ausentes. Pre-checar via `status` causava o falso
    // positivo "Parametros incompletos" quando o status ainda estava carregando
    // ou tinha falhado uma fetch transitoria.

    const useExplicitWindow = Boolean(window?.beginAt && window?.endAt);
    const useExplicitRetroactive = !useExplicitWindow && Boolean(window?.horasRetroativas);
    const horasParaConfirm = useExplicitRetroactive
      ? window!.horasRetroativas!
      : config.huawei_horas_retroativas;
    const confirmMessage = useExplicitWindow
      ? `A coleta irá buscar chamadas no intervalo selecionado. Deseja continuar?`
      : `A coleta irá procurar chamadas das últimas ${horasParaConfirm} horas na Huawei AICC. Deseja continuar?`;
    const confirmed = globalThis.confirm(confirmMessage);
    if (!confirmed) return;

    let keepPolling = false;

    let bodyPayload: Record<string, unknown> | null = null;
    if (useExplicitWindow) {
      bodyPayload = { begin_at: window!.beginAt, end_at: window!.endAt };
    } else if (useExplicitRetroactive) {
      bodyPayload = { horas_retroativas: Number(window!.horasRetroativas) };
    }

    try {
      setIsSyncing(true);
      setSyncResult(null);
      showToast({
        variant: 'info',
        title: 'Coleta iniciada',
        description: 'Conectando ao Huawei AICC...',
      });
      const result = await apiFetchJson<{ status?: string; message?: string; result?: SyncResult }>(
        '/api/telefonia/sync/manual',
        {
          method: 'POST',
          timeoutMs: 300000,
          headers: bodyPayload ? { 'Content-Type': 'application/json' } : undefined,
          body: bodyPayload ? JSON.stringify(bodyPayload) : undefined,
        },
      );
      const payload: SyncResult = {
        ...(result.result ?? {}),
        status: result.status,
        message: result.message,
      };
      const responseStatus = String(result.status || '').toLowerCase();
      const resultStatus = String(payload.status || '').toLowerCase();

      if (responseStatus === 'accepted' || responseStatus === 'running' || resultStatus === 'running') {
        keepPolling = true;
        showToast({
          variant: 'info',
          title: 'Coleta em andamento',
          description: result.message || 'Acompanhe o progresso nesta tela.',
        });
        fetchStatus();
        return;
      }

      setSyncResult(payload);
      showToast({
        variant: 'success',
        title: 'Ciclo concluído',
        description: result.message || 'Sync finalizado.',
      });
      fetchStatus();
    } catch (err) {
      const description = err instanceof Error ? err.message : 'Erro de comunicação com a API.';
      showToast({
        variant: 'error',
        title: 'Falha na coleta',
        description,
      });
      setIsSyncing(false);
    } finally {
      if (!keepPolling) {
        setIsSyncing(false);
      }
    }
  }, [config, fetchStatus, showToast]);

  const resetSyncLock = useCallback(async () => {
    try {
      const confirmed = globalThis.confirm('Deseja realmente destravar a coleta? Faça isso apenas se tiver certeza de que não há nenhum processo rodando de fato (ex: após um travamento do sistema).');
      if (!confirmed) return;

      const result = await apiFetchJson<{ status: string; message: string }>('/api/telefonia/sync/reset-lock', { method: 'POST' });
      showToast({
        variant: 'success',
        title: 'Lock liberado',
        description: result.message || 'O sistema agora permite novas coletas.',
      });
      fetchStatus();
    } catch (err) {
      showToast({
        variant: 'error',
        title: 'Falha ao destravar',
        description: err instanceof Error ? err.message : 'Não foi possível liberar o lock.',
      });
    }
  }, [fetchStatus, showToast]);

  return {
    config,
    isLoadingConfig,
    isSlowLoading,
    isSavingConfig,
    isSyncing,
    syncResult,
    status,
    accessDeniedMessage,
    automationStatus,
    updateField,
    saveConfig,
    triggerManualSync,
    cancelManualSync,
    pauseManualSync,
    resumeManualSync,
    clearSyncReport,
    resetSyncLock,
    refreshStatus: fetchStatus,
  };
}
