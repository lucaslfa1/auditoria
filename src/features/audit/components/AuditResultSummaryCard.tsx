import type { ReactNode } from 'react';
import type { AuditResult } from '../types/audit';

import { useId } from 'react';
import { Loader2, ShieldCheck, Undo2 } from 'lucide-react';

interface AuditResultSummaryCardProps {
  auditResult: AuditResult;
  isEditingResult: boolean;
  tempSummary: string;
  tempFeedback: string;
  showInfo: boolean;
  scoreChart: ReactNode;
  onToggleInfo: () => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onApplyEdit: () => void;
  onSummaryChange: (value: string) => void;
  onFeedbackChange: (value: string) => void;
  onRegenerateSummary?: () => Promise<void>;
  isRegeneratingSummary?: boolean;
  isSummaryStale?: boolean;
  canUndoRegeneration?: boolean;
  onUndoRegeneration?: () => void;
}

export function AuditResultSummaryCard({
  auditResult,
  isEditingResult,
  tempSummary,
  tempFeedback,
  showInfo,
  scoreChart,
  onToggleInfo,
  onStartEdit,
  onCancelEdit,
  onApplyEdit,
  onSummaryChange,
  onFeedbackChange,
  onRegenerateSummary,
  isRegeneratingSummary,
  isSummaryStale,
  canUndoRegeneration,
  onUndoRegeneration,
}: AuditResultSummaryCardProps) {
  const infoPanelId = useId();
  const infoTitleId = useId();
  const audioQuality = auditResult.audio_quality;
  const transcriptionQuality = audioQuality?.transcription_quality;
  const evidenceQuality = audioQuality?.evidence_quality;
  const qualityNeedsReview = Boolean(
    audioQuality?.review_recommended ||
    transcriptionQuality?.review_recommended ||
    evidenceQuality?.review_recommended
  );

  return (
    <div className={`glass-panel rounded-[1.75rem] ${showInfo ? 'overflow-visible' : 'overflow-hidden'}`}>
      {isEditingResult ? (
        <div className="flex items-center justify-between px-8 pt-5 pb-0">
          <span className="text-sm text-primary-400 font-semibold uppercase tracking-[0.14em]">
            Modo de edição ativo
          </span>
          <div className="flex gap-2">
            <button
              onClick={onCancelEdit}
              className="btn-ghost px-3.5 py-2 text-sm"
            >
              Cancelar
            </button>
            <button
              onClick={onApplyEdit}
              className="btn-success px-3.5 py-2 text-sm"
            >
              Aplicar Correções
            </button>
          </div>
        </div>
      ) : null}
      <div className="grid md:grid-cols-3 gap-8 p-8 md:p-9 items-center">
        <div className="text-center md:text-left col-span-1 relative">
          <div className="flex items-center gap-2.5 mb-4">
            <h2 className="section-title-sm">Nota final</h2>
            <button
              type="button"
              onClick={onToggleInfo}
              aria-expanded={showInfo}
              aria-controls={infoPanelId}
              aria-label={showInfo ? 'Ocultar detalhes da nota' : 'Mostrar detalhes da nota'}
              title={showInfo ? 'Ocultar detalhes da nota' : 'Mostrar detalhes da nota'}
              className="btn-ghost px-2.5 py-1 text-sm"
            >
              {showInfo ? 'Ocultar' : 'Sobre'}
            </button>
          </div>

          {showInfo ? (
            <div
              id={infoPanelId}
              role="note"
              aria-labelledby={infoTitleId}
              className="absolute top-10 left-1/2 z-20 w-[min(19rem,calc(100vw-2.5rem))] -translate-x-1/2 glass-panel rounded-xl border border-primary-500/30 p-4 text-left animate-fade-in md:left-0 md:w-80 md:translate-x-0"
            >
              <>
                <h4 id={infoTitleId} className="section-title mb-2 text-primary-400">Como a nota é calculada</h4>
                <p className="text-sm text-slate-300 leading-relaxed mb-2">
                  A pontuação máxima ({auditResult.maxPossibleScore}) ignora critérios marcados como não se aplica.
                </p>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Isso evita penalização por itens que não se aplicam.
                </p>
              </>
            </div>
          ) : null}

          {scoreChart}

          {auditResult.fatal_flags && auditResult.fatal_flags.length > 0 ? (
            <div className="mt-4 space-y-1.5">
              <h4 className="text-[10px] font-black uppercase tracking-[0.18em] text-red-400">
                Auditoria Zerada
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {auditResult.fatal_flags.map((flag) => (
                  <span
                    key={flag}
                    className="inline-block px-2.5 py-1 text-[11px] font-bold rounded-lg bg-red-500/15 text-red-400 border border-red-500/25"
                  >
                    {flag.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="col-span-2 bg-slate-900/40 rounded-2xl p-6 md:p-7 border border-white/5">
          <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
            <div className="flex items-center gap-2.5 min-w-0">
              <h3 className="section-title-lg">Resumo da auditoria</h3>
              {isEditingResult && isSummaryStale ? (
                <span
                  title="Você modificou critérios após a última geração. Clique em Reescrever para atualizar o texto."
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[10px] font-bold uppercase tracking-[0.1em] animate-pulse"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  Desatualizado
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!isEditingResult ? (
                <button
                  onClick={onStartEdit}
                  className="btn-ghost px-3 py-1.5 text-sm"
                >
                  Editar
                </button>
              ) : (
                <>
                  {canUndoRegeneration && onUndoRegeneration ? (
                    <button
                      onClick={onUndoRegeneration}
                      title="Restaurar o resumo e feedback anteriores à última reescrita da I.A."
                      className="btn-ghost px-3 py-1.5 text-sm flex items-center gap-1.5"
                    >
                      <Undo2 className="w-3.5 h-3.5" />
                      <span>Desfazer reescrita</span>
                    </button>
                  ) : null}
                  {onRegenerateSummary ? (
                    <button
                      onClick={onRegenerateSummary}
                      disabled={isRegeneratingSummary}
                      title="Reescrever resumo e feedback (com base nos critérios modificados)"
                      className={`px-3 py-1.5 text-sm flex items-center gap-2 relative rounded-xl border transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                        isSummaryStale
                          ? 'bg-amber-500/15 text-amber-200 border-amber-500/40 hover:bg-amber-500/25'
                          : 'bg-primary-500/10 text-primary-400 border-primary-500/20 hover:bg-primary-500/20 hover:text-white'
                      }`}
                    >
                      {isRegeneratingSummary ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <span>✨</span>
                      )}
                      <span>Reescrever com I.A.</span>
                    </button>
                  ) : null}
                </>
              )}
            </div>
          </div>
          {audioQuality && !qualityNeedsReview ? (
            <div className="mb-5 flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
              <ShieldCheck className="h-4 w-4" />
              <span>Transcricao e evidencias sem alerta critico.</span>
            </div>
          ) : null}
          {isEditingResult ? (
            <textarea
              value={tempSummary}
              onChange={(e) => onSummaryChange(e.target.value)}
              className="w-full bg-slate-900 border border-white/10 rounded-xl p-4 text-[15px] text-slate-200 outline-none focus:border-primary-500/50 resize-none leading-relaxed"
              rows={5}
            />
          ) : (
            <p className="text-slate-300 leading-relaxed text-[15px] md:text-base">{auditResult.summary}</p>
          )}
          {isEditingResult || auditResult.ai_feedback ? (
            <div className="mt-5 p-5 rounded-2xl bg-primary-500/5 border border-primary-500/10">
              <h4 className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary-400 mb-3">
                Feedback para o operador
              </h4>
              {isEditingResult ? (
                <textarea
                  value={tempFeedback}
                  onChange={(e) => onFeedbackChange(e.target.value)}
                  placeholder="Escreva o feedback para o operador..."
                  className="w-full bg-slate-900 border border-white/10 rounded-xl p-4 text-[15px] text-slate-200 outline-none focus:border-primary-500/50 resize-none leading-relaxed italic"
                  rows={3}
                />
              ) : (
                <p className="text-slate-300 text-[15px] md:text-base leading-relaxed italic">"{auditResult.ai_feedback}"</p>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
