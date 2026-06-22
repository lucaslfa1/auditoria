/**
 * Casca da tela de AUTOMAÇÃO. Componente de layout que compõe os painéis
 * (controle/herói, runtime de coleta, configuração, saúde e Auditorias do mês +
 * AuditModal), todos alimentados pelo `useAutomacaoDashboard` (polling de
 * `/api/automation/status` e afins). Sem regra de negócio própria aqui.
 */
import { useState } from 'react';
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react';

import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { AutomationConfigPanel } from './AutomationConfigPanel';
import { AutomationControlHero } from './AutomationControlHero';
import { AutomationRuntimePanel } from './AutomationRuntimePanel';
import { AuditoriasDoMes } from './AuditoriasDoMes';
import { AuditModal } from './AuditModal';
import { useAutomacaoDashboard } from '../hooks/useAutomacaoDashboard';

export function AutomacaoPage() {
  const [selectedAuditId, setSelectedAuditId] = useState<number | null>(null);

  const {
    data,
    draft,
    isLoading,
    loadError,
    actions,
    pending,
    auditoriasDoMes,
    auditoriasLoading,
  } = useAutomacaoDashboard();

  if (isLoading) {
    return (
      <div className="flex h-56 items-center justify-center text-slate-400 theme-light:text-slate-700">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (loadError || !data || !draft) {
    return (
      <div className="space-y-6 pb-10">
        <PageHeader
          eyebrow="nstech | Automação"
          titleFirstWord="Automação"
          titleRest="de Auditorias"
          subtitle="Coleta, classifica e audita ligações automaticamente."
          headingTag="h2"
        />
        <div className="panel-box-lg flex gap-3 border-rose-500/25 bg-rose-500/10 text-rose-100 theme-light:text-rose-800">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">Falha ao carregar a automação.</p>
            <p className="mt-1 text-sm opacity-85">
              {loadError instanceof Error ? loadError.message : 'Tente novamente.'}
            </p>
            <button type="button" onClick={actions.refresh} className="btn-secondary mt-4 px-4 py-2">
              <RefreshCw className="h-4 w-4" />
              Tentar novamente
            </button>
          </div>
        </div>
      </div>
    );
  }

  const { summary, engineStatus, gates } = data;
  const effectiveSummary = {
    ...summary,
    config: draft,
  };

  const handleOpenModal = (id: number) => {
    setSelectedAuditId(id);
  };

  const handleCloseModal = () => {
    setSelectedAuditId(null);
  };

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Automação"
        titleFirstWord="Automação"
        titleRest="de auditorias"
        subtitle="Gerencie o ciclo automático que baixa, classifica e audita ligações com Inteligência Artificial."
        headingTag="h2"
      />

      <ModuleInstructions
        storageKey="instructions:automacao"
        steps={[
          'Defina a meta de auditorias do ciclo.',
          'Ligue ou pause a esteira de automação.',
          'O ciclo roda automaticamente 1x por dia, no horário mostrado em Configurações; acompanhe o progresso (baixando, classificando, auditando) em tempo real.',
        ]}
      />

      <AutomationControlHero
        summary={effectiveSummary}
        engineStatus={engineStatus}
        isEnabled={gates.allEnabled}
        pending={{
          toggling: pending.toggling,
          runningNow: pending.runningNow,
        }}
        onToggle={actions.toggleAutomation}
        onRunNow={actions.runNow}
      />

      {(engineStatus.is_running || engineStatus.started_at || engineStatus.latest_run) ? (
        <AutomationRuntimePanel
          summary={effectiveSummary}
          engineStatus={engineStatus}
          gates={gates}
          controlAction={pending.controlAction}
          onControl={actions.controlCycle}
        />
      ) : null}

      <div className="grid gap-6">
        <AutomationConfigPanel
          draft={draft}
          pending={{
            savingConfig: pending.savingConfig,
          }}
          onUpdateField={actions.updateDraftField}
          onSaveField={actions.saveDraftField}
        />
      </div>

      <AuditoriasDoMes
        items={auditoriasDoMes}
        isLoading={auditoriasLoading}
        onOpenInArquivos={handleOpenModal}
      />

      {selectedAuditId !== null && (
        <AuditModal
          auditId={selectedAuditId}
          isOpen={true}
          onClose={handleCloseModal}
          onUpdate={actions.refresh}
        />
      )}
    </div>
  );
}
