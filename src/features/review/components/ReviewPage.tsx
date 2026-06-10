import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Clock, Loader2, ShieldAlert, Volume2, XCircle } from 'lucide-react';

import { ApiError, apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { formatOperationalLabel } from '../../../shared/lib/operationalLabels';
import { AuthenticatedAudioPlayer } from '../../../shared/components/AuthenticatedAudioPlayer';

interface TranscriptionSegment {
  speaker?: string;
  text: string;
  start?: number;
  end?: number;
}

interface ReviewAuditItem {
  id: number;
  timestamp: string;
  operator_name: string;
  operator_id: string;
  score: number;
  max_score: number;
  summary: string;
  details: string | CriterionDetail[];
  transcription?: TranscriptionSegment[];
  sector_id: string | null;
  supervisor: string;
  escala: string;
  contestation_reason?: string | null;
  contested_criteria?: Array<{ label: string; reason: string }> | string[] | null;
  audio_url?: string | null;
}

interface CriterionDetail {
  label: string;
  status: 'pass' | 'fail';
  weight?: number;
  obtainedScore?: number;
  comment?: string;
  timestamp?: string;
  evidence_text?: string;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  return new Date(value).toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

function parseDetails(raw: string | CriterionDetail[] | null | undefined): CriterionDetail[] {
  if (!raw) return [];
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => ({
      ...item,
      status: ['pass', 'na', 'n/a', 'pending_manual'].includes(String(item?.status || '').trim().toLowerCase())
        ? 'pass'
        : 'fail',
    }));
  } catch {
    return [];
  }
}

const STATUS_OPTIONS: { value: CriterionDetail['status']; label: string }[] = [
  { value: 'pass', label: 'Atende' },
  { value: 'fail', label: 'Não atende' },
];

const QUALIFICATION_STATUS_OPTIONS: { value: CriterionDetail['status']; label: string }[] = [
  { value: 'pass', label: 'Atende' },
  { value: 'fail', label: 'Não atende' },
];

const STATUS_COLORS: Record<string, string> = {
  pass: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
  fail: 'bg-red-500/10 border-red-500/30 text-red-400',
};

function isQualificationCriterion(criterion: CriterionDetail): boolean {
  const label = (criterion.label || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
  return label.includes('qualificacao') && label.includes('atendimento');
}

function statusOptionsForCriterion(criterion: CriterionDetail): typeof STATUS_OPTIONS {
  if (!isQualificationCriterion(criterion)) {
    return STATUS_OPTIONS;
  }
  return QUALIFICATION_STATUS_OPTIONS;
}

export function ReviewPage() {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [contestacoes, setContestacoes] = useState<ReviewAuditItem[]>([]);
  const [defenseDrafts, setDefenseDrafts] = useState<Record<number, string>>({});
  const [savingAuditId, setSavingAuditId] = useState<number | null>(null);
  const [compatibilityNotice, setCompatibilityNotice] = useState<string | null>(null);
  const [editedCriteria, setEditedCriteria] = useState<Record<number, CriterionDetail[]>>({});

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetchJson<{ total: number; contestacoes: any[] }>('/api/revisao/contestacoes?limit=100');
      const parsedAudits = (response.contestacoes || []).map((audit: any) => ({
        ...audit,
        details: typeof audit.details === 'string' ? parseDetails(audit.details) : (audit.details || []),
      })) as ReviewAuditItem[];
      setContestacoes(parsedAudits);
      setCompatibilityNotice(null);
    } catch (error) {
      console.error(error);

      if (error instanceof ApiError && error.status === 404) {
        setContestacoes([]);
        setCompatibilityNotice('Contestações indisponíveis no backend ativo.');
      } else {
        setCompatibilityNotice(null);
        showToast({
          variant: 'error',
          title: 'Falha ao carregar contestações',
          description: 'Não foi possível atualizar a fila técnica.',
        });
      }
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const pendingLabel = useMemo(() => {
    if (contestacoes.length === 1) {
      return '1 contestação em análise';
    }

    return `${contestacoes.length} contestações em análise`;
  }, [contestacoes.length]);

  const getEditableCriteria = (audit: ReviewAuditItem): CriterionDetail[] => {
    if (editedCriteria[audit.id]) {
      return editedCriteria[audit.id];
    }
    return audit.details as CriterionDetail[];
  };

  const updateCriterionField = (
    auditId: number,
    criterionIndex: number,
    field: 'status' | 'comment',
    value: string,
    originalDetails: CriterionDetail[],
  ) => {
    setEditedCriteria((prev) => {
      const current = prev[auditId] || originalDetails.map((d) => ({ ...d }));
      const next = current.map((d, i) =>
        i === criterionIndex ? { ...d, [field]: value } : d,
      );
      return { ...prev, [auditId]: next };
    });
  };

  const handleFinalize = async (auditId: number, verdict: 'accepted' | 'rejected') => {
    const defense = (defenseDrafts[auditId] || '').trim();
    if (!defense) {
      showToast({
        variant: 'warning',
        title: 'Defesa técnica obrigatória',
        description: 'Registre a justificativa técnica antes de concluir o veredito.',
      });
      return;
    }

    setSavingAuditId(auditId);
    try {
      const updatedDetails = editedCriteria[auditId] || null;
      await apiFetchJson(`/api/revisao/auditorias/${auditId}/veredito`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verdict, defense, updated_details: updatedDetails }),
      });
      setDefenseDrafts((current) => {
        const next = { ...current };
        delete next[auditId];
        return next;
      });
      setEditedCriteria((current) => {
        const next = { ...current };
        delete next[auditId];
        return next;
      });
      await loadData();
      showToast({
        variant: 'success',
        title: verdict === 'accepted' ? 'Contestação aceita' : 'Contestação negada',
        description: 'O veredito técnico foi registrado.',
      });
    } catch (error) {
      console.error(error);
      showToast({
        variant: 'error',
        title: 'Falha ao registrar veredito',
        description: 'Não foi possível concluir a contestação.',
      });
    } finally {
      setSavingAuditId(null);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Contestações"
        titleFirstWord="Fila"
        titleRest="de Contestações"
        subtitle="Concentre aqui as contestações abertas da auditoria."
      />

      <ModuleInstructions
        storageKey="instructions:review"
        steps={[
          'Veja as contestações abertas pelos operadores e supervisores.',
          'Analise o argumento e as evidências de cada caso.',
          'Aceite ou rejeite, ajustando a pontuação quando necessário.',
        ]}
      />

      <div className="surface-toolbar">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="metric-label">Pendências da contestação</p>
            <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-700">{pendingLabel}</p>
            {compatibilityNotice ? (
              <p className="mt-2 text-xs text-amber-300 theme-light:text-slate-700">{compatibilityNotice}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={loadData} className="btn-ghost px-4 py-2 text-sm font-semibold">
              Atualizar
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="glass-panel rounded-2xl p-8 text-center">
          <div className="inline-flex items-center gap-3 text-slate-400 theme-light:text-slate-700">
            <Loader2 size={18} className="animate-spin" />
            Carregando contestações...
          </div>
        </div>
      ) : contestacoes.length > 0 ? (
        <div className="space-y-5">
          {contestacoes.map((audit) => {
            const originalCriteria = audit.details as CriterionDetail[];
            const criteria = getEditableCriteria(audit);
            const contestedSet = new Set((audit.contested_criteria || []).map((item: any) => typeof item === 'string' ? item : item.label));
            const hasEdits = !!editedCriteria[audit.id];
            const scorePercent = audit.max_score > 0 ? ((audit.score / audit.max_score) * 100).toFixed(2) : '0.00';
            
            // Calculate dynamic score
            let dynamicScore = audit.score;
            let dynamicMax = audit.max_score;
            if (hasEdits) {
              dynamicScore = 0;
              dynamicMax = 0;
              criteria.forEach((c) => {
                const w = c.weight || 1;
                if (c.status === 'pass') {
                  dynamicScore += w;
                  dynamicMax += w;
                } else if (c.status === 'fail') {
                  dynamicMax += w;
                }
              });
              
              const wasFatalZeroed = audit.score === 0 && (audit.details as CriterionDetail[]).some(d => (d.obtainedScore || 0) > 0);
              if (wasFatalZeroed) {
                dynamicScore = 0;
              }
            }
            
            const dynamicPercent = dynamicMax > 0 ? ((dynamicScore / dynamicMax) * 100).toFixed(2) : '0.00';

            const defense = defenseDrafts[audit.id] || '';
            const isSaving = savingAuditId === audit.id;

            return (
              <article key={audit.id} className="glass-panel rounded-2xl p-5 theme-light:bg-white theme-light:border-slate-300">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="section-title">{audit.operator_name || 'Operador sem nome'}</h3>
                      <span className="inline-flex items-center rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800">
                        Em contestação
                      </span>
                    </div>
                    <p className="text-sm text-slate-400 theme-light:text-slate-700">
                      Supervisor: {audit.supervisor || '-'} • Setor: {formatOperationalLabel(audit.sector_id) || '-'} • Escala: {formatOperationalLabel(audit.escala) || audit.escala || '-'}
                    </p>
                    <p className="text-xs text-slate-500 theme-light:text-slate-600">
                      {formatDate(audit.timestamp)} • ID Huawei: {audit.operator_id || '-'}
                    </p>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-900/45 px-4 py-3 text-right theme-light:border-slate-300 theme-light:bg-slate-50">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Nota atual</p>
                    <p className="mt-1 text-2xl font-extrabold text-slate-200 theme-light:text-slate-900">
                      {hasEdits ? dynamicScore : audit.score}
                      <span className="ml-1 text-sm font-medium text-slate-500">/ {hasEdits ? dynamicMax : audit.max_score}</span>
                    </p>
                    <p className="text-xs text-slate-500">{hasEdits ? dynamicPercent : scorePercent}%</p>
                    {hasEdits && (
                      <p className="mt-1 text-[10px] text-amber-400 font-semibold uppercase">Recálculo preditivo</p>
                    )}
                  </div>
                </div>

                <div className="mt-4 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                  <div className="space-y-4">
                    <div className="rounded-xl border border-white/10 bg-slate-900/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-50">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Resumo da auditoria</p>
                      <p className="mt-2 text-sm leading-relaxed text-slate-300 theme-light:text-slate-800">{audit.summary || 'Sem resumo disponível.'}</p>
                    </div>

                    {audit.audio_url ? (
                      <div className="rounded-xl border border-white/10 bg-slate-900/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-50">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                          <Volume2 size={13} className="text-primary-400" />
                          Gravação da ligação
                        </p>
                        <div className="mt-3">
                          <AuthenticatedAudioPlayer audioUrl={audit.audio_url} className="w-full rounded-lg" />
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-white/10 bg-slate-900/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-50">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                          <Volume2 size={13} className="text-slate-500" />
                          Gravação da ligação
                        </p>
                        <p className="mt-2 text-xs text-slate-500 italic">Não foi possível carregar o áudio desta auditoria.</p>
                      </div>
                    )}

                    {(audit.transcription && audit.transcription.length > 0) ? (
                      <div className="rounded-xl border border-white/10 bg-slate-900/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-50">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Transcrição da conversa</p>
                        <div className="max-h-80 overflow-y-auto space-y-2 pr-1 scrollbar-thin">
                          {audit.transcription.map((seg, i) => {
                            const isOperator = (seg.speaker || '').toLowerCase().includes('operador') || (seg.speaker || '').toLowerCase().includes('agent');
                            return (
                              <div key={`${audit.id}-seg-${i}`} className={`rounded-lg px-3 py-2 text-xs leading-relaxed ${
                                isOperator
                                  ? 'bg-primary-500/10 border border-primary-500/20 text-primary-300 theme-light:bg-orange-50 theme-light:border-orange-200 theme-light:text-orange-900'
                                  : 'bg-slate-800/50 border border-white/5 text-slate-300 theme-light:bg-slate-100 theme-light:border-slate-200 theme-light:text-slate-800'
                              }`}>
                                <span className="font-semibold text-[10px] uppercase tracking-wider block mb-0.5 opacity-70">
                                  {seg.speaker || (isOperator ? 'Operador' : 'Cliente')}
                                  {seg.start != null ? ` · ${Math.floor(seg.start / 60)}:${String(Math.floor(seg.start % 60)).padStart(2, '0')}` : ''}
                                </span>
                                {seg.text}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}

                    <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 theme-light:border-slate-300 theme-light:bg-slate-100">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Contestação do supervisor</p>
                      <p className="mt-2 text-sm leading-relaxed text-slate-200 theme-light:text-slate-800">
                        {audit.contestation_reason || 'Motivo não informado.'}
                      </p>
                      {Array.isArray(audit.contested_criteria) && audit.contested_criteria.length > 0 && (
                        <div className="mt-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 mb-1.5">Critérios selecionados pelo supervisor:</p>
                          <div className="flex flex-col gap-2">
                            {audit.contested_criteria.map((item: any) => {
                              const label = typeof item === 'string' ? item : item.label;
                              const reason = typeof item === 'object' && item.reason ? item.reason : null;
                              return (
                                <div key={label} className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2">
                                  <span className="inline-flex items-center rounded bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-300 theme-light:border-slate-300 theme-light:bg-amber-50 theme-light:text-amber-800">
                                    {label}
                                  </span>
                                  {reason && (
                                    <p className="mt-1 text-[12px] text-amber-200/80 italic theme-light:text-amber-900/80">
                                      "{reason}"
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="rounded-xl border border-white/10 bg-slate-900/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-50">
                      <div className="flex items-center justify-between mb-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Critérios avaliados</p>
                        <p className="text-[10px] text-slate-500">Clique nos campos para editar</p>
                      </div>
                      {criteria.length > 0 ? (
                        <div className="space-y-3">
                          {criteria.map((criterion, index) => {
                            const isContested = contestedSet.has(criterion.label);
                            return (
                              <div
                                key={`${audit.id}-criterion-${index}`}
                                className={`rounded-lg border px-3 py-2.5 transition-colors ${isContested
                                  ? 'border-amber-500/30 bg-amber-500/5 ring-1 ring-amber-500/20'
                                  : 'border-white/5 bg-white/[0.02] theme-light:border-slate-200 theme-light:bg-white'
                                  }`}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <div className="flex items-center gap-2 min-w-0 flex-1">
                                    {isContested && (
                                      <span className="shrink-0 w-2 h-2 rounded-full bg-amber-400 animate-pulse" title="Critério contestado" />
                                    )}
                                    <span className="text-sm font-semibold text-slate-200 theme-light:text-slate-900">{criterion.label}</span>
                                  </div>
                                  <select
                                    value={criterion.status}
                                    onChange={(e) =>
                                      updateCriterionField(
                                        audit.id,
                                        index,
                                        'status',
                                        e.target.value,
                                        originalCriteria,
                                      )
                                    }
                                    className={`text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded-md border cursor-pointer outline-none ${STATUS_COLORS[criterion.status] || STATUS_COLORS.fail}`}
                                  >
                                    {statusOptionsForCriterion(criterion).map((opt) => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                  </select>
                                </div>
                                <textarea
                                  value={criterion.comment || ''}
                                  onChange={(e) =>
                                    updateCriterionField(
                                      audit.id,
                                      index,
                                      'comment',
                                      e.target.value,
                                      originalCriteria,
                                    )
                                  }
                                  placeholder="Comentário do critério..."
                                  rows={2}
                                  className="mt-2 w-full rounded-md border border-white/10 bg-slate-900/60 px-2 py-1.5 text-xs text-slate-300 outline-none resize-none focus:border-primary-500/40 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-900"
                                />
                                {criterion.timestamp ? (
                                  <div className="flex items-center gap-1.5 mt-1.5">
                                    <Clock className="w-3 h-3 text-slate-500" />
                                    <span className="text-[11px] font-mono text-slate-500">{criterion.timestamp}</span>
                                  </div>
                                ) : null}
                                {criterion.evidence_text ? (
                                  <p className="mt-2 text-[11px] leading-relaxed italic text-slate-500 theme-light:text-slate-500 border-l-2 border-slate-700 pl-2 ml-1">
                                    &ldquo;{criterion.evidence_text}&rdquo;
                                  </p>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="mt-2 text-sm text-slate-500 theme-light:text-slate-700">Sem critérios detalhados nesta auditoria.</p>
                      )}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/10 bg-slate-900/35 p-4 theme-light:border-slate-300 theme-light:bg-slate-50">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Defesa técnica</p>
                    <textarea
                      value={defense}
                      onChange={(event) =>
                        setDefenseDrafts((current) => ({
                          ...current,
                          [audit.id]: event.target.value,
                        }))
                      }
                      rows={8}
                      placeholder="Registre a análise técnica final para responder ao supervisor."
                      className="mt-3 w-full rounded-xl border border-white/10 bg-slate-900 px-3 py-3 text-sm text-slate-200 outline-none transition-colors focus:border-primary-500/40 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-900"
                    />

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <button
                        onClick={() => handleFinalize(audit.id, 'accepted')}
                        disabled={isSaving}
                        className="btn-secondary px-4 py-2.5 text-sm font-semibold"
                      >
                        {isSaving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={15} />}
                        Aceitar contestação
                      </button>
                      <button
                        onClick={() => handleFinalize(audit.id, 'rejected')}
                        disabled={isSaving}
                        className="btn-primary px-4 py-2.5 text-sm font-semibold"
                      >
                        {isSaving ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={15} />}
                        Negar contestação
                      </button>
                    </div>

                    <p className="mt-3 text-xs leading-relaxed text-slate-500 theme-light:text-slate-600">
                      Após o veredito, a auditoria será encaminhada ao painel de desempenho.
                    </p>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="glass-panel rounded-2xl p-8 text-center">
          <ShieldAlert className="mx-auto h-8 w-8 text-slate-500 theme-light:text-slate-700" />
          <p className="mt-3 text-sm text-slate-400 theme-light:text-slate-700">Nenhuma contestação aguardando análise técnica.</p>
        </div>
      )}
    </div>
  );
}
