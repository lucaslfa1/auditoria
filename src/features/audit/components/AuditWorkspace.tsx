import { Suspense, useEffect, useRef, useState } from 'react';
import type { ComponentType } from 'react';
import { Loader2 } from 'lucide-react';
import type { AuditResult, AuditSector } from '../types/audit';
import type { AuditFlowState } from '../hooks/useAuditFlow';
import type { AuditResultEditorState } from '../hooks/useAuditResultEditor';
import type { ReviewQueueState, SaveToSupervisorResult } from '../hooks/useTranscription';
import { AuditSetupStep } from './AuditSetupStep';
import { AuditUploadStep } from './AuditUploadStep';
import { AuditResultSummaryCard } from './AuditResultSummaryCard';
import { AuditTranscriptPanel } from './AuditTranscriptPanel';
import { AuditEvaluationDetailsPanel } from './AuditEvaluationDetailsPanel';
import { AuditResultActions } from './AuditResultActions';
import { AIFeedbackModal } from '../../ai-feedback/components/AIFeedbackModal';
import { PageHeader } from '../../../shared/components/PageHeader';

interface AuditWorkspaceProps {
  AuditScoreChart: ComponentType<{ score: number; maxScore: number }>;
  flow: AuditFlowState;
  editor: AuditResultEditorState;
  sectors: AuditSector[];
  theme: 'dark' | 'light';
  isProcessing: boolean;
  auditResult: AuditResult | null;
  error: string | null;
  quotaExceeded: string | null;
  onForceProcess: () => Promise<boolean>;
  actionError: string | null;
  isSaved: boolean;
  saveState: ReviewQueueState;
  clearActionError: () => void;
  saveToDashboard: (
    result: AuditResult,
    alertId?: string,
    alertLabel?: string,
    operatorId?: string,
    sectorId?: string,
    audioDate?: string
  ) => Promise<SaveToSupervisorResult | null>;
  forceSendToSupervisor: () => Promise<boolean>;
  discardSavedAudit: () => Promise<boolean>;
  downloadExcel: (result: AuditResult) => Promise<void>;
  downloadReportDocx: (result: AuditResult) => Promise<void>;
  downloadReportPdf: (result: AuditResult) => Promise<void>;
  downloadTranscriptionDocx: (result: AuditResult) => Promise<void>;
  downloadTranscriptionPdf: (result: AuditResult) => Promise<void>;
  downloadGestores: (
    result: AuditResult,
    alertId?: string,
    alertLabel?: string,
    sectorId?: string
  ) => Promise<void>;
  downloadGestoresPdf: (
    result: AuditResult,
    alertId?: string,
    alertLabel?: string,
    sectorId?: string
  ) => Promise<void>;
}

const parseTime = (timeStr: string) => {
  const parts = timeStr.split(':').map(Number);
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  }
  return parts[0];
};

function ContextTag({ label, value }: { label: string; value: string }) {
  return (
    <span className="min-w-[10rem] rounded-xl border border-white/10 bg-slate-900/50 px-4 py-2 text-left text-slate-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-700">
      <span className="block text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 theme-light:text-slate-500">
        {label}
      </span>
      <span className="mt-1 block text-sm font-medium text-slate-200 theme-light:text-slate-900">
        {value}
      </span>
    </span>
  );
}

export function AuditWorkspace({
  AuditScoreChart,
  flow,
  editor,
  sectors,
  theme,
  isProcessing,
  auditResult,
  error,
  quotaExceeded,
  onForceProcess,
  actionError,
  isSaved,
  saveState,
  clearActionError,
  saveToDashboard,
  forceSendToSupervisor,
  discardSavedAudit,
  downloadExcel,
  downloadReportDocx,
  downloadReportPdf,
  downloadTranscriptionDocx,
  downloadTranscriptionPdf,
  downloadGestores,
  downloadGestoresPdf,
}: AuditWorkspaceProps) {
  const [showInfo, setShowInfo] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const intakeError = flow.inputError || error;
  const contextLocked = !!auditResult;
  const resolveResult = (resultOverride?: AuditResult | null) => resultOverride || auditResult;

  // AI Feedback Modal state
  const [feedbackModalData, setFeedbackModalData] = useState<{
    isOpen: boolean;
    tipo: string;
    setor: string;
    criterioId?: string;
    situacao: string;
    correcao: string;
    transcription: string;
  } | null>(null);

  const handleOpenFeedback = () => {
    // Collect context for the feedback
    const originalText = auditResult?.transcription?.map(t => t.text).join('\n') || '';
    const editedText = editor.tempTranscription?.map(t => t.text).join('\n') || '';
    const transcriptChanged = originalText !== editedText;

    let situacao = '';
    let correcao = '';

    if (transcriptChanged) {
      situacao = `A IA transcreveu ou atribuiu o locutor incorretamente no áudio da auditoria.`;
      correcao = `Foi necessário editar a transcrição.`;
    } else {
      situacao = `A IA avaliou de forma incorreta o áudio de auditoria (Setor: ${flow.selectedSector?.label}, Alerta: ${flow.selectedAlert?.label}).`;
      correcao = `Foram necessários ajustes na nota ou comentários.`;
    }

    setFeedbackModalData({
      isOpen: true,
      tipo: 'avaliacao',
      setor: flow.selectedSector?.id || '',
      criterioId: '',
      situacao,
      correcao,
      transcription: editedText || originalText
    });
  };

  useEffect(() => {
    if (!editor.lastCorrectionLearning) {
      return;
    }

    const payload = editor.lastCorrectionLearning;
    const corrections = payload.corrections || [];
    const situacao = corrections
      .map((item) => {
        const previous = item.previous_status || 'nao informado';
        const comment = item.previous_comment ? ` Comentario original: ${item.previous_comment}` : '';
        return `A IA avaliou "${item.label}" como ${previous}.${comment}`;
      })
      .join('\n');
    const correcao = corrections
      .map((item) => {
        const comment = item.corrected_comment ? ` Comentario correto: ${item.corrected_comment}` : '';
        return `O auditor corrigiu "${item.label}" para ${item.corrected_status}.${comment}`;
      })
      .join('\n');

    setFeedbackModalData({
      isOpen: true,
      tipo: 'avaliacao',
      setor: payload.setor || flow.selectedSector?.id || '',
      criterioId: corrections.length === 1 ? corrections[0].criterion_id : '',
      situacao,
      correcao,
      transcription: payload.exemplo_transcricao || auditResult?.transcription?.map((segment) => segment.text).join('\n') || '',
    });
    editor.clearLastCorrectionLearning();
  }, [auditResult?.transcription, editor, flow.selectedSector?.id]);

  const seekAudio = (timeStr: string) => {
    if (!audioRef.current) {
      return;
    }
    audioRef.current.currentTime = parseTime(timeStr);
    audioRef.current.play();
  };

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Auditoria"
        titleFirstWord="Central"
        titleRest="de Auditoria"
        subtitle="Configure o contexto, envie o arquivo e revise o resultado no mesmo fluxo."
        aside={(
          <>
            <ContextTag label="Auditoria" value={flow.auditType === 'audio' ? 'Áudio' : 'Documento'} />
            <ContextTag label="Setor" value={flow.selectedSector?.label || 'Não informado'} />
            <ContextTag label="Alerta" value={flow.selectedAlert?.label || 'Não informado'} />
            <ContextTag label="Nome do operador" value={flow.operatorName.trim() || 'Não informado'} />
            <ContextTag label="Matrícula" value={flow.operatorId.trim() || 'Não informado'} />
            {flow.audioDate ? <ContextTag label="Data do áudio" value={new Date(flow.audioDate + 'T00:00:00').toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })} /> : null}
          </>
        )}
      />

      {(() => {
        const contextReady = !!flow.selectedSector && !!flow.selectedAlert;
        return (
          <div className="flex flex-col gap-6 items-center">
            <div className="w-full max-w-2xl">
              <AuditSetupStep
                auditType={flow.auditType}
                sectors={sectors}
                selectedSector={flow.selectedSector}
                selectedAlert={flow.selectedAlert}
                operatorName={flow.operatorName}
                operatorId={flow.operatorId}
                theme={theme}
                onAuditTypeChange={flow.handleAuditTypeChange}
                onSectorChange={flow.handleSectorChange}
                onAlertChange={flow.handleAlertChange}
                onOperatorNameChange={flow.setOperatorName}
                onOperatorIdChange={flow.setOperatorId}
                audioDate={flow.audioDate}
                onAudioDateChange={flow.setAudioDate}
                showContinueButton={false}
                disabled={contextLocked}
                className="h-full"
              />
            </div>
            {contextReady ? (
              <div className="w-full max-w-2xl">
                <AuditUploadStep
                  auditType={flow.auditType}
                  file={flow.file}
                  isDragging={flow.isDragging}
                  isProcessing={isProcessing}
                  selectedSectorLabel={flow.selectedSector?.label}
                  selectedAlertLabel={flow.selectedAlert?.label}
                  stepError={intakeError}
                  quotaExceeded={quotaExceeded}
                  onForceProcess={onForceProcess}
                  onDragOver={flow.handleDragOver}
                  onDragLeave={flow.handleDragLeave}
                  onDrop={flow.handleDrop}
                  onFileChange={flow.handleFileChange}
                  onClearFile={flow.clearSelectedFile}
                  onProcess={flow.handleProcess}
                  showBackButton={false}
                  className="h-full max-w-none mx-0"
                />
              </div>
            ) : null}
          </div>
        );
      })()}

      {auditResult ? (
        <div className="space-y-7 md:space-y-8 relative">
          {isProcessing ? (
            <div className="absolute inset-0 z-30 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm rounded-[1.75rem]">
              <div className="text-center">
                <Loader2 className="w-11 h-11 animate-spin text-primary-400 mx-auto mb-3" />
                <p className="text-white font-semibold text-base">Reprocessando análise...</p>
                <p className="text-slate-400 text-sm mt-1">Analisando a transcrição editada.</p>
              </div>
            </div>
          ) : null}

          {actionError ? (
            <div className="p-4 bg-red-500/10 text-red-400 rounded-2xl border border-red-500/20 animate-fade-in flex items-center justify-between gap-3">
              <span className="text-base">{actionError}</span>
              <button
                type="button"
                onClick={clearActionError}
                className="text-red-400 hover:text-red-300 text-sm px-3 py-1.5 rounded-xl border border-red-500/20 hover:bg-red-500/10 transition-colors shrink-0"
              >
                Fechar
              </button>
            </div>
          ) : null}

          <AuditResultSummaryCard
            auditResult={auditResult}
            isEditingResult={editor.isEditingResult}
            tempSummary={editor.tempSummary}
            tempFeedback={editor.tempFeedback}
            showInfo={showInfo}
            scoreChart={
              <Suspense fallback={<div className="h-48 w-full rounded-xl bg-slate-900/30 animate-pulse" />}>
                <AuditScoreChart score={auditResult.score} maxScore={auditResult.maxPossibleScore} />
              </Suspense>
            }
            onToggleInfo={() => setShowInfo(!showInfo)}
            onStartEdit={editor.startEditResult}
            onCancelEdit={editor.cancelEditResult}
            onApplyEdit={editor.applyEditResult}
            onSummaryChange={editor.setTempSummary}
            onFeedbackChange={editor.setTempFeedback}
            onRegenerateSummary={editor.generateAITexts}
            isRegeneratingSummary={editor.isRegeneratingSummary}
            isSummaryStale={editor.isSummaryStale}
            canUndoRegeneration={editor.canUndoRegeneration}
            onUndoRegeneration={editor.undoRegeneration}
          />

          <AuditTranscriptPanel
            auditType={flow.auditType}
            audioUrl={flow.audioUrl}
            audioSourceType={flow.file?.type}
            fileName={flow.file?.name}
            audioRef={audioRef}
            transcription={auditResult.transcription || []}
            isEditingTranscription={editor.isEditingTranscription}
            tempTranscription={editor.tempTranscription}
            isProcessing={isProcessing}
            onEditTranscription={editor.handleEditTranscription}
            onCancelEditing={() => editor.setIsEditingTranscription(false)}
            onSaveTranscription={editor.handleSaveTranscription}
            onUpdateTranscriptionSegment={editor.updateTranscriptionSegment}
            onAddTranscriptionSegment={editor.addTranscriptionSegment}
            onRemoveTranscriptionSegment={editor.removeTranscriptionSegment}
            onSeekAudio={seekAudio}
          />

          <AuditEvaluationDetailsPanel
            details={editor.visibleDetails}
            isEditingResult={editor.isEditingResult}
            onStartEdit={editor.startEditResult}
            onCancelEdit={editor.cancelEditResult}
            onApplyEdit={editor.applyEditResult}
            onUpdateDetail={editor.updateTempDetail}
          />

          <AuditResultActions
            isSaved={isSaved}
            saveState={saveState}
            actionError={actionError}
            isEditingResult={editor.isEditingResult}
            onApplyPendingEdits={editor.applyEditResult}
            onSaveToDashboard={(resultOverride) => {
              const resultToSave = resolveResult(resultOverride);
              if (!resultToSave) return Promise.resolve(null);
              return saveToDashboard(
                resultToSave,
                flow.selectedAlert?.id,
                flow.selectedAlert?.label,
                flow.operatorId,
                flow.selectedSector?.id,
                flow.audioDate,
              );
            }}
            onForceSendToSupervisor={forceSendToSupervisor}
            onDiscardSavedAudit={discardSavedAudit}
            onDownloadExcel={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              return resultToExport ? downloadExcel(resultToExport) : Promise.resolve();
            }}
            onDownloadReportPdf={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              return resultToExport ? downloadReportPdf(resultToExport) : Promise.resolve();
            }}
            onDownloadReportDocx={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              return resultToExport ? downloadReportDocx(resultToExport) : Promise.resolve();
            }}
            onDownloadTranscriptionPdf={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              return resultToExport ? downloadTranscriptionPdf(resultToExport) : Promise.resolve();
            }}
            onDownloadTranscriptionDocx={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              return resultToExport ? downloadTranscriptionDocx(resultToExport) : Promise.resolve();
            }}
            onDownloadGestores={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              if (!resultToExport) return Promise.resolve();
              return downloadGestores(
                resultToExport,
                flow.selectedAlert?.id,
                flow.selectedAlert?.label,
                flow.selectedSector?.id,
              );
            }}
            onDownloadGestoresPdf={(resultOverride) => {
              const resultToExport = resolveResult(resultOverride);
              if (!resultToExport) return Promise.resolve();
              return downloadGestoresPdf(
                resultToExport,
                flow.selectedAlert?.id,
                flow.selectedAlert?.label,
                flow.selectedSector?.id,
              );
            }}
            onReset={flow.resetAuditFlow}
            onOpenFeedback={handleOpenFeedback}
          />
        </div>
      ) : null}

      {/* AI Feedback Modal */}
      {feedbackModalData && (
        <AIFeedbackModal
          isOpen={feedbackModalData.isOpen}
          onClose={() => setFeedbackModalData({ ...feedbackModalData, isOpen: false })}
          theme={theme}
          initialType={feedbackModalData.tipo}
          initialSector={feedbackModalData.setor}
          initialCriterionId={feedbackModalData.criterioId}
          situacaoContext={feedbackModalData.situacao}
          correcaoContext={feedbackModalData.correcao}
          transcriptionContext={feedbackModalData.transcription}
        />
      )}
    </div>
  );
}
