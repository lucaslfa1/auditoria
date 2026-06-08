import { useState } from 'react';
import { Loader2, Brain } from 'lucide-react';
import type { ReviewQueueState, SaveToSupervisorResult } from '../hooks/useTranscription';
import type { AuditResult } from '../types/audit';
import { useToast } from '../../../shared/components/ToastProvider';

interface AuditResultActionsProps {
  isSaved: boolean;
  saveState: ReviewQueueState;
  actionError?: string | null;
  onSaveToDashboard: (resultOverride?: AuditResult) => Promise<SaveToSupervisorResult | null>;
  onForceSendToSupervisor: () => Promise<boolean>;
  onDiscardSavedAudit: () => Promise<boolean>;
  isEditingResult?: boolean;
  onApplyPendingEdits?: () => Promise<AuditResult | null | void>;
  onDownloadExcel: (resultOverride?: AuditResult) => void | Promise<void>;
  onDownloadReportPdf: (resultOverride?: AuditResult) => void | Promise<void>;
  onDownloadReportDocx: (resultOverride?: AuditResult) => void | Promise<void>;
  onDownloadTranscriptionPdf: (resultOverride?: AuditResult) => void | Promise<void>;
  onDownloadTranscriptionDocx: (resultOverride?: AuditResult) => void | Promise<void>;
  onDownloadGestores: (resultOverride?: AuditResult) => void | Promise<void>;
  onDownloadGestoresPdf: (resultOverride?: AuditResult) => void | Promise<void>;
  onReset: () => void;
  onOpenFeedback?: () => void;
}

export function AuditResultActions({
  isSaved,
  saveState,
  actionError,
  onSaveToDashboard,
  onForceSendToSupervisor,
  onDiscardSavedAudit,
  isEditingResult,
  onApplyPendingEdits,
  onDownloadReportPdf,
  onDownloadGestores,
  onDownloadGestoresPdf,
  onReset,
  onOpenFeedback,
}: AuditResultActionsProps) {
  const { showToast } = useToast();
  const [isSendingSupervisor, setIsSendingSupervisor] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Garante que exports e envios usem o snapshot editado, sem depender do
  // próximo render do React depois de aplicar correções.
  const ensurePendingEditsApplied = async (): Promise<AuditResult | undefined> => {
    if (isEditingResult && onApplyPendingEdits) {
      const updatedResult = await onApplyPendingEdits();
      if (!updatedResult) {
        throw new Error('Não foi possível salvar as edições pendentes.');
      }
      return updatedResult || undefined;
    }
    return undefined;
  };

  const handleExport = async (fn: (resultOverride?: AuditResult) => void | Promise<void>) => {
    setIsExporting(true);
    try {
      const updatedResult = await ensurePendingEditsApplied();
      await fn(updatedResult);
    } catch (err: any) {
      showToast({ variant: 'error', title: 'Erro na exportação', description: err?.message || 'Falha ao gerar arquivo' });
    } finally {
      setIsExporting(false);
    }
  };
  const savedStatusLabel =
    saveState === 'awaiting_pair' ? 'Arquivada' : 'Enviado ao supervisor';
  const savedStatusClass =
    saveState === 'awaiting_pair'
      ? 'text-amber-300 bg-amber-500/10 border-amber-500/30 theme-light:text-slate-800 theme-light:bg-slate-100 theme-light:border-slate-300'
      : 'text-green-400 bg-green-500/10 border-green-500/30 theme-light:text-slate-800 theme-light:bg-slate-100 theme-light:border-slate-300';

  const handleSendToSupervisor = async () => {
    setIsSendingSupervisor(true);
    try {
      const updatedResult = await ensurePendingEditsApplied();
      const saved = await onSaveToDashboard(updatedResult);
      if (saved) {
        showToast({
          variant: 'success',
          title: saved.review_status === 'pending_approval' ? 'Enviada ao supervisor' : 'Auditoria arquivada',
          description: saved.message,
        });
      } else {
        showToast({
          variant: 'error',
          title: 'Falha no envio',
          description: 'O envio para o supervisor não foi concluído.',
        });
      }
    } catch (err: any) {
      showToast({
        variant: 'error',
        title: 'Falha no envio',
        description: err?.message || 'O envio para o supervisor não foi concluído.',
      });
    } finally {
      setIsSendingSupervisor(false);
    }
  };

  const handleForceSend = async () => {
    setIsSendingSupervisor(true);
    try {
      await ensurePendingEditsApplied();
      const success = await onForceSendToSupervisor();
      if (success) {
        showToast({
          variant: 'success',
          title: 'Enviada ao supervisor',
          description: 'Auditoria liberada para a fila de revisão.',
        });
      }
    } catch (err: any) {
      showToast({
        variant: 'error',
        title: 'Falha no envio',
        description: err?.message || 'Não foi possível liberar a auditoria para supervisão.',
      });
    } finally {
      setIsSendingSupervisor(false);
    }
  };

  const handleDiscardSaved = async () => {
    if (!window.confirm('Descartar esta auditoria arquivada? Ela não será enviada ao supervisor.')) {
      return;
    }
    setIsSendingSupervisor(true);
    try {
      const success = await onDiscardSavedAudit();
      if (success) {
        showToast({
          variant: 'success',
          title: 'Auditoria descartada',
          description: 'A auditoria saiu do arquivo e não será enviada ao supervisor.',
        });
      }
    } finally {
      setIsSendingSupervisor(false);
    }
  };

  return (
    <div className="grid gap-3 pt-3">
      <div className="flex flex-col gap-3 sm:flex-row">
        <button
          onClick={() => handleExport(onDownloadReportPdf)}
          disabled={isExporting || isSendingSupervisor}
          className="w-full sm:flex-1 btn-primary py-4 rounded-xl font-semibold text-base flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {isExporting ? 'Exportando...' : 'Baixar Relatório (PDF)'}
        </button>
        {!isSaved ? (
          <button
            onClick={handleSendToSupervisor}
            disabled={isSendingSupervisor}
            className="btn-success w-full sm:w-auto px-6 sm:px-8 py-4 font-semibold"
          >
            {isSendingSupervisor ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {isSendingSupervisor ? 'Arquivando...' : 'Arquivar auditoria'}
          </button>
        ) : (
          <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto items-center">
            <div className={`w-full sm:w-auto px-6 sm:px-8 py-4 rounded-xl font-semibold border flex items-center justify-center gap-2 ${savedStatusClass}`}>
              {savedStatusLabel}
            </div>
            {saveState === 'awaiting_pair' && (
              <button
                onClick={handleForceSend}
                disabled={isSendingSupervisor}
                title="Libera esta auditoria arquivada para a fila do supervisor"
                className="btn-ghost text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 px-4 py-4 sm:py-2 text-sm w-full sm:w-auto whitespace-nowrap"
              >
                {isSendingSupervisor ? <Loader2 className="h-3 w-3 animate-spin mr-1 inline" /> : null}
                Enviar ao supervisor
              </button>
            )}
            {saveState !== 'discarded' && (
              <button
                onClick={handleDiscardSaved}
                disabled={isSendingSupervisor}
                title="Descarta esta auditoria do painel"
                className="btn-ghost text-red-400 hover:text-red-300 hover:bg-red-500/10 px-4 py-4 sm:py-2 text-sm w-full sm:w-auto whitespace-nowrap"
              >
                Descartar auditoria
              </button>
            )}
          </div>
        )}
        {onOpenFeedback && (
          <button
            onClick={onOpenFeedback}
            className="btn-primary flex items-center justify-center gap-2 w-full sm:w-auto px-6 sm:px-8 py-4 font-semibold bg-blue-600 hover:bg-blue-500 border-blue-500"
          >
            <Brain className="w-5 h-5" />
            Instruir IA
          </button>
        )}

        <button
          onClick={onReset}
          className="btn-ghost w-full sm:w-auto px-6 sm:px-8 py-4 font-semibold"
        >
          Nova auditoria
        </button>
      </div>

      <div className="glass-card rounded-xl p-4">
        <div className="text-sm text-slate-500 font-semibold mb-3">Modelo gestores</div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => handleExport(onDownloadGestores)}
            disabled={isExporting || isSendingSupervisor}
            className="btn-success px-4 py-2.5 text-[15px] font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
            title="Exportar no formato da planilha dos gestores"
          >
            Excel Gestores
          </button>
          <button
            onClick={() => handleExport(onDownloadGestoresPdf)}
            disabled={isExporting || isSendingSupervisor}
            className="btn-success px-4 py-2.5 text-[15px] font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
            title="Exportar PDF no formato dos gestores"
          >
            PDF Gestores
          </button>
        </div>
      </div>

      {actionError ? (
        <div className="p-4 bg-red-500/10 text-red-400 rounded-lg border border-red-500/20">
          {actionError}
        </div>
      ) : null}
    </div>
  );
}
