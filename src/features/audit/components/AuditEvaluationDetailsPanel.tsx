import type { AuditResultDetail } from '../types/audit';
import { getAuditStatusBadgeClass, getAuditStatusLabel } from '../lib/auditStatus';
import { CheckCircle2, Clock, Quote } from 'lucide-react';

interface AuditEvaluationDetailsPanelProps {
  details: AuditResultDetail[];
  isEditingResult: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onApplyEdit: () => void;
  onUpdateDetail: (index: number, field: keyof AuditResultDetail, value: string) => void;
}

export function AuditEvaluationDetailsPanel({
  details,
  isEditingResult,
  onStartEdit,
  onCancelEdit,
  onApplyEdit,
  onUpdateDetail,
}: AuditEvaluationDetailsPanelProps) {
  return (
    <>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="section-title-lg">Critérios avaliados</h3>
        {!isEditingResult ? (
          <button
            onClick={onStartEdit}
            className="btn-ghost px-3.5 py-2 text-sm"
          >
            Editar critérios
          </button>
        ) : (
          <div className="flex flex-col gap-2 sm:flex-row">
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
              Aplicar correções
            </button>
          </div>
        )}
      </div>

      {isEditingResult ? (
        <div className="mb-4 rounded-xl border border-primary-500/20 bg-primary-500/10 px-4 py-3 text-sm text-primary-200 theme-light:bg-slate-100 theme-light:text-slate-700 theme-light:border-slate-300">
          Ao aplicar correções, os critérios alterados são registrados como referência para as próximas avaliações da IA.
        </div>
      ) : null}

      <div className="grid gap-4">
        {details.map((item, idx) => (
          <div
            key={item.criterionId}
            className="glass-card group flex flex-col gap-4 rounded-2xl p-5 sm:flex-row"
            style={{ animationDelay: `${idx * 50}ms` }}
          >
            {isEditingResult ? (
              <select
                value={item.status}
                onChange={(e) => onUpdateDetail(idx, 'status', e.target.value)}
                className="mt-1 bg-slate-900 border border-slate-700 text-slate-200 rounded-xl text-sm px-3 py-2 outline-none h-10"
              >
                <option value="pass">Atende</option>
                <option value="fail">Não atende</option>
              </select>
            ) : (
              <div
                className={`mt-1 px-3 h-10 rounded-xl flex items-center justify-center shrink-0 text-[11px] font-semibold uppercase tracking-[0.14em] ${getAuditStatusBadgeClass(item.status)}`}
              >
                {getAuditStatusLabel(item.status)}
              </div>
            )}

            <div className="flex-1">
              <div className="flex justify-between items-start mb-2">
                <h4 className="section-title">{item.label}</h4>
              </div>
              {isEditingResult ? (
                <textarea
                  defaultValue={item.comment}
                  onBlur={(e) => onUpdateDetail(idx, 'comment', e.target.value)}
                  className="w-full mt-2 bg-slate-900 border border-slate-700 rounded-xl p-3 text-[15px] text-slate-300 outline-none focus:border-primary-500 resize-none"
                  rows={2}
                />
              ) : (
                <>
                  <p className="text-slate-400 text-[15px] leading-relaxed">{item.comment}</p>
                  {item.timestamp ? (
                    <div className="mt-2 flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 text-slate-500" />
                      <span className="font-mono text-[13px] text-slate-500">{item.timestamp}</span>
                    </div>
                  ) : null}
                  {item.evidence_text ? (
                    <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/35 p-3">
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
                          <Quote className="h-3.5 w-3.5" />
                          Evidencia
                        </div>
                        {item.evidence_validation?.matched ? (
                          <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
                            <CheckCircle2 className="h-3 w-3" />
                            localizada
                          </span>
                        ) : null}
                      </div>
                      <p className="text-[13px] leading-relaxed text-slate-300">{item.evidence_text}</p>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
