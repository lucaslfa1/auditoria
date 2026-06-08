import type { StageInfo } from '../automationViewModel';

export const STAGE_LABELS: Record<string, StageInfo> = {
  idle: {
    label: 'Parada',
    description: 'Sem ciclo em andamento.',
    tone: 'neutral',
  },
  starting: {
    label: 'Iniciando',
    description: 'Preparando o próximo passo.',
    tone: 'info',
  },
  syncing_d1: {
    label: 'Coletando ligações',
    description: 'Baixando as ligações do lote.',
    tone: 'info',
  },
  auditing: {
    label: 'Auditando',
    description: 'IA avaliando as ligações baixadas.',
    tone: 'warning',
  },
  paused: {
    label: 'Pausada',
    description: 'Ciclo pausado. Use Retomar para continuar.',
    tone: 'warning',
  },
  completed: {
    label: 'Concluída',
    description: 'Último ciclo finalizado.',
    tone: 'success',
  },
  error: {
    label: 'Erro',
    description: 'Último ciclo falhou ou ficou pendente.',
    tone: 'danger',
  },
  stale: {
    label: 'Verificando',
    description: 'Aguardando atualização do processamento.',
    tone: 'warning',
  },
  disabled: {
    label: 'Desligada',
    description: '',
    tone: 'neutral',
  },
};

export function getStageLabel(stage: string): StageInfo {
  return STAGE_LABELS[stage] ?? STAGE_LABELS.idle;
}
