import { Bot, Loader2 } from 'lucide-react';

import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { RecordingsList } from './RecordingsList';
import { SyncPanel } from './SyncPanel';
import { useTelefoniaSync } from '../hooks/useTelefoniaSync';

export function TelefoniaPage() {
  const {
    config,
    isLoadingConfig,
    isSlowLoading,
    isSyncing,
    syncResult,
    status,
    accessDeniedMessage,
    automationStatus,
    triggerManualSync,
    cancelManualSync,
    pauseManualSync,
    resumeManualSync,
    clearSyncReport,
    resetSyncLock,
  } = useTelefoniaSync();

  // Confia na flag consolidada do backend, que ja considera o auth_mode em uso
  // (proxy exige AK/SK; oauth_direct usa direct_app_key e ignora AK/SK).
  const canSync = !accessDeniedMessage && Boolean(status?.credentials?.configured);

  // v1.3.91: a automacao rodando consome recursos do Cloud Run e deixa esta
  // pagina lenta. Em vez de mostrar um loader vazio, avisamos o motivo.
  const automationRunning = Boolean(
    automationStatus?.is_running || automationStatus?.is_cycle_running,
  );
  const automationStageLabel = automationStatus?.current_stage
    ? String(automationStatus.current_stage).replace(/_/g, ' ')
    : null;

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Telefonia"
        titleFirstWord="Integração"
        titleRest="de Telefonia"
        subtitle="Baixe ligações direto da plataforma e deixe as gravações em fila."
      />

      <ModuleInstructions
        storageKey="instructions:telefonia"
        steps={[
          'Preencha e salve as credenciais da Huawei.',
          'Defina o período de busca e a meta de auditorias.',
          'Baixe as ligações — as gravações entram na fila de Triagem.',
        ]}
      />

      {automationRunning ? (
        <div className="flex items-start gap-3 rounded-xl border border-sky-500/25 bg-sky-500/10 p-4 text-sky-100 theme-light:border-sky-300 theme-light:bg-sky-50 theme-light:text-sky-900">
          <Bot className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="text-sm">
            <p className="font-semibold">Automação em execução</p>
            <p className="mt-0.5 text-sky-100/80 theme-light:text-sky-900/80">
              {automationStatus?.current_message
                || `Ciclo automatico em andamento${automationStageLabel ? ` (${automationStageLabel})` : ''}. Algumas operacoes podem ficar mais lentas ate o ciclo terminar.`}
            </p>
          </div>
        </div>
      ) : null}

      {accessDeniedMessage ? (
        <div className="rounded-[28px] border border-amber-500/25 bg-amber-500/10 p-6 text-amber-100 shadow-[0_24px_80px_rgba(245,158,11,0.12)] theme-light:border-amber-300 theme-light:bg-amber-50 theme-light:text-amber-900">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-amber-300/90 theme-light:text-amber-700">
            Acesso restrito
          </p>
          <h3 className="mt-3 text-lg font-semibold text-amber-50 theme-light:text-amber-950">
            Coleta ad-hoc disponível apenas para administradores
          </h3>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-amber-100/90 theme-light:text-amber-900/90">
            {accessDeniedMessage}
          </p>
        </div>
      ) : (
        <>
          <div className="max-w-3xl">
            {isLoadingConfig ? (
              <div className="panel-box flex flex-col items-center justify-center gap-3 rounded-2xl border border-white/10 bg-slate-900 p-10 text-slate-300 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-700">
                <Loader2 className="h-7 w-7 animate-spin text-primary-500" />
                <p className="text-sm font-medium">Carregando configurações da Huawei…</p>
                {isSlowLoading ? (
                  <p className="max-w-md text-center text-xs text-slate-500 theme-light:text-slate-500">
                    {automationRunning
                      ? 'O ciclo de automação em curso pode estar reduzindo a velocidade da resposta. Aguarde mais alguns segundos.'
                      : 'A resposta está demorando mais que o normal. Pode ser uma rotina em segundo plano.'}
                  </p>
                ) : null}
              </div>
            ) : (
              <SyncPanel
                horasRetroativas={config.huawei_horas_retroativas}
                canSync={canSync}
                isSyncing={isSyncing}
                syncResult={syncResult}
                status={status}
                onTrigger={triggerManualSync}
                onCancel={cancelManualSync}
                onPause={pauseManualSync}
                onResume={resumeManualSync}
                onClearReport={clearSyncReport}
                onResetLock={resetSyncLock}
              />
            )}
          </div>

          <RecordingsList />
        </>
      )}
    </div>
  );
}
