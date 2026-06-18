/**
 * useAutomacaoDashboard — hook central do painel de Automação (React Query).
 *
 * Agrega numa visão única: resumo do pipeline D-1, status do motor de automação,
 * health do backend e as auditorias do mês (que caem em Arquivos Salvos junto
 * com as manuais — gate humano por design). Expõe as ações de configuração,
 * liga/desliga, execução manual e controle do ciclo.
 *
 * Dados (API):
 * - GET  /api/telefonia/sync/d-minus-1/summary → resumo + config do pipeline D-1
 * - GET  /api/automation/engine/status         → motor (rodando? ciclo? progresso)
 * - GET  /api/health                           → health do backend
 * - GET  /api/salvos?tipo=auditoria&limit=100  → auditorias (mês corrente filtrado no cliente)
 * - POST /api/configuracoes                    → grava chave/valor de config
 * - POST /api/automation/engine/toggle         → liga/desliga (atômico: auditor + D-1 + coletor)
 * - POST /api/automation/run-now               → dispara ciclo manual
 * - POST /api/automation/{pause|resume|cancel} → controla o ciclo em execução
 *
 * Particularidades:
 * - Polling adaptativo p/ economizar compute do banco: refetch a cada 5s com
 *   ciclo rodando, 30s em repouso.
 * - Config editada vira "draft" com dirty-tracking: refetches do servidor NÃO
 *   sobrescrevem campos alterados e ainda não salvos pelo usuário.
 * - Mutações usam update otimista (snapshot do cache + rollback no erro).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';
import {
  EngineStatusSchema,
  HealthStatusSchema,
  PipelineSummarySchema,
  type EngineStatus,
  type HealthStatus,
  type PipelineConfig,
  type PipelineSummary,
} from '../schemas';
import type { AutomationGateStatus } from '../automationViewModel';

const AUTOMACAO_QUERY_KEY = ['automacao', 'dashboard'] as const;
const AUDITORIAS_MES_QUERY_KEY = ['automacao', 'auditorias-mes'] as const;
const RETRYABLE_CYCLE_STATUSES = new Set(['error', 'partial']);

/** Auditoria listada no painel (subset do registro de `arquivo_salvo`). */
export interface AuditoriaDoMes {
  id: number;
  tipo: string;
  arquivo: string;
  data_analise: string;
  audit_id: number | null;
  operator_name: string;
  sector_id: string;
  alert_label: string;
  score: number | null;
  criado_por: string;
}

interface AuditoriasResponse {
  items: AuditoriaDoMes[];
  total: number;
}

/** Busca as auditorias salvas e filtra client-side as do mês corrente. */
async function fetchAuditoriasDoMes(): Promise<AuditoriaDoMes[]> {
  const response = await apiFetchJson<AuditoriasResponse>('/api/salvos?tipo=auditoria&limit=100');
  const items = Array.isArray(response?.items) ? response.items : [];
  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
  return items.filter((item) => {
    if (!item.data_analise) return false;
    const ts = new Date(item.data_analise).getTime();
    return Number.isFinite(ts) && ts >= startOfMonth;
  });
}

type ConfigField = keyof PipelineConfig;

/** Visão agregada do painel, cacheada sob AUTOMACAO_QUERY_KEY. */
interface AutomationDashboardData {
  summary: PipelineSummary;
  engineStatus: EngineStatus;
  health: HealthStatus;
  gates: AutomationGateStatus;
  fetchedAt: string;
}

interface SaveConfigVariables {
  field: ConfigField;
  chave: string;
  valor: string;
  value: PipelineConfig[ConfigField];
}

type ControlAction = 'pause' | 'resume' | 'cancel';

// Mapeia campo da UI → chave persistida na tabela `configuracoes`.
const CONFIG_KEY_BY_FIELD: Partial<Record<ConfigField, string>> = {
  horario_execucao: 'huawei_d1_horario_execucao',
  max_retries: 'huawei_d1_max_retries',
  retry_intervalo_minutos: 'huawei_d1_retry_intervalo_minutos',
  lookback_dias: 'huawei_d1_lookback_dias',
  cota_max_por_operador_mes: 'huawei_cota_max_por_operador_mes',
  limite_ligacoes: 'huawei_d1_limite_ligacoes',
  limite_auditorias: 'automacao_audit_target_count',
};

// Clamps de UI por campo numérico (o backend só garante o mínimo).
const FIELD_LIMITS: Partial<Record<ConfigField, { min: number; max?: number }>> = {
  max_retries: { min: 1, max: 20 },
  retry_intervalo_minutos: { min: 5, max: 480 },
  lookback_dias: { min: 1, max: 30 },
  cota_max_por_operador_mes: { min: 1, max: 50 },
  // sem teto de UI: o valor passa a ser 100% definido pela config (o backend só garante mínimo 1).
  limite_ligacoes: { min: 1 },
  limite_auditorias: { min: 1 },
};

const CONFIG_FIELDS: ConfigField[] = [
  'enabled',
  'horario_execucao',
  'max_retries',
  'retry_intervalo_minutos',
  'lookback_dias',
  'cota_max_por_operador_mes',
  'limite_ligacoes',
  'limite_auditorias',
];

const DEFAULT_PIPELINE_CONFIG = PipelineSummarySchema.parse({}).config;

/** Consolida os 2 gates (D-1, motor) p/ o banner "tudo ligado?". */
function buildAutomationGateStatus(summary: PipelineSummary, engineStatus: EngineStatus): AutomationGateStatus {
  const items: AutomationGateStatus['items'] = [
    { id: 'pipeline', label: 'D-1', enabled: summary.config.enabled },
    { id: 'engine', label: 'Motor', enabled: engineStatus.is_enabled },
  ];
  const disabledLabels = items.filter((item) => !item.enabled).map((item) => item.label);
  return {
    allEnabled: disabledLabels.length === 0,
    disabledLabels,
    items,
  };
}

/** Busca summary+engine+health em paralelo; engine/health toleram falha (parse com defaults do schema). */
async function fetchAutomacaoDashboard(): Promise<AutomationDashboardData> {
  const [summaryRaw, engineRaw, healthRaw] = await Promise.all([
    apiFetchJson('/api/telefonia/sync/d-minus-1/summary'),
    apiFetchJson('/api/automation/engine/status').catch(() => null),
    apiFetchJson('/api/health').catch(() => null),
  ]);

  const summary = PipelineSummarySchema.parse(summaryRaw);
  const parsedEngine = EngineStatusSchema.parse(engineRaw);
  const engineStatus =
    engineRaw == null
      ? EngineStatusSchema.parse({ ...parsedEngine, is_enabled: summary.config.enabled })
      : parsedEngine;
  const summaryWithNextExecution = {
    ...summary,
    proxima_execucao_sp: resolveNextExecution(summary, engineStatus),
  };

  return {
    summary: summaryWithNextExecution,
    engineStatus,
    health: HealthStatusSchema.parse(healthRaw),
    gates: buildAutomationGateStatus(summaryWithNextExecution, engineStatus),
    fetchedAt: new Date().toISOString(),
  };
}

/**
 * Converte um campo do draft no payload de POST /api/configuracoes
 * (horário valida HH:MM; números são clampados em FIELD_LIMITS).
 */
function serializeConfigField(field: ConfigField, draft: PipelineConfig): SaveConfigVariables | null {
  const chave = CONFIG_KEY_BY_FIELD[field];
  if (!chave) return null;

  if (field === 'horario_execucao') {
    const value = draft.horario_execucao.trim();
    if (!/^\d{2}:\d{2}$/.test(value)) {
      return { field, chave, valor: '', value };
    }
    return { field, chave, valor: value, value };
  }

  // Booleanos precisam virar "true"/"false" — caso contrário Number(true)=1 grava "1"
  // no banco, divergindo do que o backend espera para flags em `configuracoes`.
  const rawDraftValue = draft[field];
  if (typeof rawDraftValue === 'boolean') {
    return { field, chave, valor: rawDraftValue ? 'true' : 'false', value: rawDraftValue };
  }

  const rawValue = Number(rawDraftValue);
  const limits = FIELD_LIMITS[field] ?? { min: 0, max: 9999 };
  const sanitized = Math.max(limits.min, Math.min(limits.max ?? Infinity, Math.floor(rawValue || limits.min)));
  return { field, chave, valor: String(sanitized), value: sanitized };
}

/** Imutável: devolve a config com um único campo substituído. */
function withConfigValue(
  config: PipelineConfig,
  field: ConfigField,
  value: PipelineConfig[ConfigField],
): PipelineConfig {
  return { ...config, [field]: value } as PipelineConfig;
}

/** Aplica patch otimista no cache (config e/ou engineStatus) e recalcula os gates. */
function patchDashboardConfig(
  oldData: AutomationDashboardData | undefined,
  configPatch: Partial<PipelineConfig>,
  engineStatusPatch?: Partial<EngineStatus>,
): AutomationDashboardData | undefined {
  if (!oldData) return oldData;
  const summary = {
    ...oldData.summary,
    config: { ...oldData.summary.config, ...configPatch },
  };
  const engineStatus = engineStatusPatch ? { ...oldData.engineStatus, ...engineStatusPatch } : oldData.engineStatus;
  return {
    ...oldData,
    summary,
    engineStatus,
    gates: buildAutomationGateStatus(summary, engineStatus),
  };
}

/**
 * Resolve a "próxima execução" exibida: se o último ciclo terminou em
 * error/partial, antecipa para o horário de retry — espelhando o gate do
 * backend (_calcular_proxima_execucao_d1_sp). Caso contrário, horário diário.
 */
function resolveNextExecution(summary: PipelineSummary, engineStatus: EngineStatus): string | null {
  if (
    !summary.config.enabled ||
    !engineStatus.is_enabled ||
    engineStatus.is_running ||
    engineStatus.is_cycle_running
  ) {
    return summary.proxima_execucao_sp;
  }

  const latestStatus = String(engineStatus.latest_run?.status ?? '').toLowerCase();
  const finishedAt = engineStatus.latest_run?.finished_at ?? engineStatus.finished_at;
  if (!RETRYABLE_CYCLE_STATUSES.has(latestStatus) || !finishedAt) {
    return summary.proxima_execucao_sp;
  }

  const finishedTs = new Date(finishedAt).getTime();
  if (!Number.isFinite(finishedTs)) return summary.proxima_execucao_sp;

  const retryMinutes = Math.max(1, Number(summary.config.retry_intervalo_minutos) || 1);
  const retryTs = finishedTs + retryMinutes * 60_000;

  // Retry ja vencido: NAO fabricar "agora + 1 min" — isso prendia o aviso
  // "Proxima: em 1 min" na UI, pois era recalculado a cada render. Cai para o
  // horario diario real, espelhando o gate do backend (_calcular_proxima_execucao_d1_sp).
  if (retryTs <= Date.now()) {
    return summary.proxima_execucao_sp;
  }

  const dailyTs = summary.proxima_execucao_sp ? new Date(summary.proxima_execucao_sp).getTime() : Number.POSITIVE_INFINITY;

  // Retry futuro: usa o que vier primeiro (retry ou horario diario).
  if (Number.isFinite(dailyTs) && dailyTs <= retryTs) {
    return summary.proxima_execucao_sp;
  }

  return new Date(retryTs).toISOString();
}

/** Igualdade campo a campo (Object.is) sobre CONFIG_FIELDS. */
function configsAreEqual(left: PipelineConfig, right: PipelineConfig): boolean {
  return CONFIG_FIELDS.every((field) => Object.is(left[field], right[field]));
}

/** Mescla a config do servidor preservando os campos dirty do draft (edição local vence). */
function mergeServerConfigWithDraft(
  serverConfig: PipelineConfig,
  previous: PipelineConfig | null,
  dirtyFields: ReadonlySet<ConfigField>,
): PipelineConfig {
  if (!previous) return serverConfig;
  if (dirtyFields.size === 0) {
    return configsAreEqual(previous, serverConfig) ? previous : serverConfig;
  }

  let next = serverConfig;
  for (const field of dirtyFields) {
    next = withConfigValue(next, field, previous[field]);
  }

  return configsAreEqual(previous, next) ? previous : next;
}

/** Ver doc do módulo. Retorna dados agregados, draft de config, flags de pending e ações. */
export function useAutomacaoDashboard() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  // ── Draft de config com dirty-tracking (preservado contra refetches) ──
  const [draft, setDraft] = useState<PipelineConfig | null>(null);
  const draftRef = useRef<PipelineConfig | null>(null);
  const [dirtyFields, setDirtyFields] = useState<Set<ConfigField>>(() => new Set());

  // ── Queries: dashboard + auditorias do mês (polling adaptativo 5s/30s) ──
  const dashboardQuery = useQuery({
    queryKey: AUTOMACAO_QUERY_KEY,
    queryFn: fetchAutomacaoDashboard,
    refetchInterval: (query) => {
      const status = query.state.data?.engineStatus;
      return status?.is_running || status?.is_cycle_running ? 5000 : 30000;
    },
    refetchOnWindowFocus: true,
  });

  const auditoriasMesQuery = useQuery({
    queryKey: AUDITORIAS_MES_QUERY_KEY,
    queryFn: fetchAuditoriasDoMes,
    refetchInterval: () => {
      const status = dashboardQuery.data?.engineStatus;
      return status?.is_running || status?.is_cycle_running ? 5000 : 30000;
    },
    refetchOnWindowFocus: true,
  });

  const serverConfig = dashboardQuery.data?.summary.config ?? null;

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    if (!serverConfig) return;
    setDraft((previous) => {
      const next = mergeServerConfigWithDraft(serverConfig, previous, dirtyFields);
      draftRef.current = next;
      return next;
    });
  }, [dirtyFields, serverConfig]);

  const invalidateAutomation = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['automacao'] });
  }, [queryClient]);

  const markDirtyField = useCallback((field: ConfigField) => {
    setDirtyFields((previous) => {
      if (previous.has(field)) return previous;
      const next = new Set(previous);
      next.add(field);
      return next;
    });
  }, []);

  const updateDraftField = useCallback((field: ConfigField, value: string | number | boolean) => {
    setDraft((previous) => {
      const base = previous ?? DEFAULT_PIPELINE_CONFIG;
      const next = withConfigValue(base, field, value);
      draftRef.current = next;
      return next;
    });
    markDirtyField(field);
  }, [markDirtyField]);

  const clearDirtyField = useCallback((field: ConfigField, expectedValue?: PipelineConfig[ConfigField]) => {
    setDirtyFields((previous) => {
      if (!previous.has(field)) return previous;
      if (expectedValue !== undefined && !Object.is(draftRef.current?.[field], expectedValue)) {
        return previous;
      }
      const next = new Set(previous);
      next.delete(field);
      return next;
    });
  }, []);

  // ── Mutações: salvar config / toggle / run-now / controle do ciclo (todas otimistas) ──
  const saveConfigMutation = useMutation({
    mutationFn: async ({ chave, valor }: SaveConfigVariables) => {
      await apiFetchJson('/api/configuracoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chave, valor }),
      });
    },
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: AUTOMACAO_QUERY_KEY });
      const previous = queryClient.getQueryData<AutomationDashboardData>(AUTOMACAO_QUERY_KEY);
      queryClient.setQueryData<AutomationDashboardData | undefined>(
        AUTOMACAO_QUERY_KEY,
        (oldData) => patchDashboardConfig(oldData, { [variables.field]: variables.value } as Partial<PipelineConfig>),
      );
      setDraft((previousDraft) => {
        const base = previousDraft ?? previous?.summary.config ?? DEFAULT_PIPELINE_CONFIG;
        const next = withConfigValue(base, variables.field, variables.value);
        draftRef.current = next;
        return next;
      });
      return { previous };
    },
    onSuccess: (_data, variables) => {
      clearDirtyField(variables.field, variables.value);
      invalidateAutomation();
    },
    onError: (_err, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(AUTOMACAO_QUERY_KEY, context.previous);
      }
      showToast({
        title: 'Erro ao salvar configuração',
        description: 'Tente novamente em instantes.',
        variant: 'error',
      });
    },
  });

  const saveDraftField = useCallback(
    (field: ConfigField) => {
      if (!draft) return;
      const payload = serializeConfigField(field, draft);
      if (!payload) return;

      if (field === 'horario_execucao' && !payload.valor) {
        showToast({
          title: 'Horário inválido',
          description: 'Use o formato HH:MM, por exemplo 06:00.',
          variant: 'warning',
        });
        const restoredValue = serverConfig?.horario_execucao ?? DEFAULT_PIPELINE_CONFIG.horario_execucao;
        setDraft((previous) => {
          if (!previous) return previous;
          const next = withConfigValue(previous, 'horario_execucao', restoredValue);
          draftRef.current = next;
          return next;
        });
        clearDirtyField(field);
        return;
      }

      if (field !== 'horario_execucao' && !Object.is(draft[field], payload.value)) {
        setDraft((previous) => {
          if (!previous) return previous;
          const next = withConfigValue(previous, field, payload.value);
          draftRef.current = next;
          return next;
        });
      }

      saveConfigMutation.mutate(payload);
    },
    [clearDirtyField, draft, saveConfigMutation, serverConfig, showToast],
  );

  // Padrão canônico de update otimista do React Query: onMutate tira snapshot
  // do cache e aplica o novo valor na hora; onError restaura o snapshot.
  // O toggle do backend é uma chamada atômica que atualiza os gates do
  // auditor e do D-1 de uma vez (o coletor respeita o gate do D-1).
  const toggleMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      await apiFetchJson('/api/automation/engine/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      return enabled;
    },
    onMutate: async (enabled) => {
      await queryClient.cancelQueries({ queryKey: AUTOMACAO_QUERY_KEY });
      const previous = queryClient.getQueryData<AutomationDashboardData>(AUTOMACAO_QUERY_KEY);
      queryClient.setQueryData<AutomationDashboardData | undefined>(
        AUTOMACAO_QUERY_KEY,
        (oldData) => patchDashboardConfig(
          oldData,
          { enabled },
          { is_enabled: enabled },
        ),
      );
      setDraft((previousDraft) => {
        const base = previousDraft ?? previous?.summary.config ?? DEFAULT_PIPELINE_CONFIG;
        const next = withConfigValue(base, 'enabled', enabled);
        draftRef.current = next;
        return next;
      });
      markDirtyField('enabled');
      return { previous };
    },
    onSuccess: (enabled) => {
      clearDirtyField('enabled', enabled);
      showToast({
        title: enabled ? 'Automação ligada' : 'Automação desligada',
        variant: 'success',
      });
    },
    onError: (_err, _vars, context) => {
      const previous = (context as { previous?: AutomationDashboardData } | undefined)?.previous;
      if (previous) {
        queryClient.setQueryData(AUTOMACAO_QUERY_KEY, previous);
      }
      setDraft((previousDraft) => {
        const restoredValue = previous?.summary.config.enabled ?? serverConfig?.enabled ?? DEFAULT_PIPELINE_CONFIG.enabled;
        const base = previousDraft ?? previous?.summary.config ?? serverConfig ?? DEFAULT_PIPELINE_CONFIG;
        const next = withConfigValue(base, 'enabled', restoredValue);
        draftRef.current = next;
        return next;
      });
      clearDirtyField('enabled');
      showToast({ title: 'Erro ao alterar automação', variant: 'error' });
    },
    onSettled: () => {
      // Sempre reconcilia com o servidor ao final, para capturar qualquer
      // divergência entre o valor otimista e o que o backend persistiu.
      invalidateAutomation();
    },
  });

  const runNowMutation = useMutation({
    mutationFn: async () =>
      apiFetchJson<{
        status: string;
        message?: string;
        result?: { status?: string; baixadas?: number; auditadas?: number; message?: string };
      }>('/api/automation/run-now', { method: 'POST' }),
    onSuccess: (response) => {
      const status = String(response.status || '').toLowerCase();
      if (status === 'started') {
        const startedAt = new Date().toISOString();
        queryClient.setQueryData<AutomationDashboardData | undefined>(
          AUTOMACAO_QUERY_KEY,
          (oldData) => {
            if (!oldData) return oldData;
            return {
              ...oldData,
              engineStatus: {
                ...oldData.engineStatus,
                is_running: true,
                is_cycle_running: true,
                is_paused: false,
                is_cancelled: false,
                latest_run_is_stale: false,
                current_stage: 'starting',
                current_message: 'Ciclo manual iniciado. Atualizando progresso.',
                current_run_source: 'manual_ui',
                started_at: startedAt,
                finished_at: null,
                audit_progress: {
                  ...oldData.engineStatus.audit_progress,
                  is_running: true,
                  is_paused: false,
                  is_cancelled: false,
                  current_step: 'syncing_d1',
                  message: 'Preparando coleta e auditoria.',
                  started_at: oldData.engineStatus.audit_progress.started_at ?? startedAt,
                  finished_at: null,
                  last_step_at: startedAt,
                  last_heartbeat_at: startedAt,
                },
              },
            };
          },
        );
        showToast({
          title: 'Ciclo iniciado',
          description: 'Acompanhe o andamento nesta tela.',
          variant: 'info',
        });
        queryClient.refetchQueries({ queryKey: AUDITORIAS_MES_QUERY_KEY });
        return;
      } else if (status === 'skipped') {
        // "skipped" pode vir de um ciclo em andamento OU do sync_lock (30min,
        // compartilhado com a coleta da Telefonia) estar preso. A mensagem cobre
        // os dois casos e aponta a recuperação; se o backend mandar um motivo
        // específico em response.message, ele prevalece.
        showToast({
          title: 'Já há uma coleta ou ciclo em andamento',
          description:
            response.message ??
            "Aguarde o término. Se a coleta parecer travada, use 'Destravar Coleta' na aba Telefonia.",
          variant: 'warning',
        });
      } else if (status === 'disabled') {
        showToast({
          title: 'Automação desligada',
          description: 'Ligue a automação para executar agora.',
          variant: 'warning',
        });
      } else if (status === 'error' || status === 'partial') {
        showToast({
          title: 'Ciclo terminou com atenção',
          description: response.result?.message ?? 'Verifique o status do ciclo.',
          variant: 'warning',
        });
      } else {
        showToast({
          title: 'Ciclo concluído',
          description: `Baixadas: ${response.result?.baixadas ?? 0}. Auditorias: ${response.result?.auditadas ?? 0}.`,
          variant: 'success',
        });
      }
      queryClient.refetchQueries({ queryKey: ['automacao'] });
    },
    onError: () => {
      showToast({
        title: 'Erro ao executar automação',
        description: 'O ciclo não pôde ser iniciado pela tela.',
        variant: 'error',
      });
    },
  });

  const controlMutation = useMutation({
    mutationFn: async (action: ControlAction) => {
      await apiFetchJson(`/api/automation/${action}`, { method: 'POST' });
      return action;
    },
    onSuccess: (action) => {
      const labels: Record<ControlAction, string> = {
        pause: 'Ciclo pausado',
        resume: 'Ciclo retomado',
        cancel: 'Cancelamento solicitado',
      };
      showToast({ title: labels[action], variant: 'info' });
      queryClient.refetchQueries({ queryKey: ['automacao'] });
    },
    onError: () => {
      showToast({ title: 'Erro ao executar ação', variant: 'error' });
    },
  });

  // ── API pública do hook ──
  const actions = useMemo(
    () => ({
      refresh: () => {
        dashboardQuery.refetch();
        auditoriasMesQuery.refetch();
      },
      refreshAuditorias: () => auditoriasMesQuery.refetch(),
      updateDraftField,
      saveDraftField,
      toggleAutomation: (enabled: boolean) => toggleMutation.mutate(enabled),
      runNow: () => runNowMutation.mutate(),
      controlCycle: (action: ControlAction) => controlMutation.mutate(action),
    }),
    [
      auditoriasMesQuery,
      controlMutation,
      dashboardQuery,
      runNowMutation,
      saveDraftField,
      toggleMutation,
      updateDraftField,
    ],
  );

  return {
    data: dashboardQuery.data,
    draft,
    isLoading: dashboardQuery.isLoading,
    isFetching: dashboardQuery.isFetching,
    loadError: dashboardQuery.error,
    auditoriasDoMes: auditoriasMesQuery.data ?? [],
    auditoriasLoading: auditoriasMesQuery.isLoading,
    actions,
    pending: {
      savingConfig: saveConfigMutation.isPending ? saveConfigMutation.variables?.field ?? null : null,
      toggling: toggleMutation.isPending,
      runningNow: runNowMutation.isPending,
      controlAction: controlMutation.isPending ? controlMutation.variables ?? null : null,
    },
  };
}
