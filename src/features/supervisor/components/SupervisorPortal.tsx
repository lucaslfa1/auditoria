import { useState, useEffect, useCallback, useRef } from 'react';
import { Search, Download, FileText, ChevronDown, CheckCircle2, XCircle, AlertCircle, MessageSquarePlus, Loader2, Volume2, Clock } from 'lucide-react';
import { apiFetchJson, apiFetchBlob } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';
import { PageHeader } from '../../../shared/components/PageHeader';
import { formatOperationalLabel } from '../../../shared/lib/operationalLabels';
import { AuthenticatedAudioPlayer } from '../../../shared/components/AuthenticatedAudioPlayer';
import { ReadOnlyTranscription } from '../../../shared/components/ReadOnlyTranscription';

// Types
interface FeedbackData {
  id: number;
  audit_id: number;
  gestor_nome: string;
  feedback_texto: string;
  pontos_melhoria: string;
  criado_em: string;
}

interface AuditItem {
  id: number;
  timestamp: string;
  operator_name: string;
  operator_id: string;
  score: number;
  max_score: number;
  summary: string;
  details: string | CriterionDetail[];
  alert_id: string | null;
  alert_label: string | null;
  status?: string;
  contestation_reason?: string | null;
  contestation_verdict?: 'accepted' | 'rejected' | null;
  contested_criteria?: string | null;
  review_defense?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  sector_id: string | null;
  supervisor: string;
  escala: string;
  transcription?: string | TranscriptionSegment[] | null;
  audio_available?: boolean;
  audio_url?: string | null;
  feedback: FeedbackData | null;
  is_missing?: boolean;
}

interface KPIs {
  total_auditorias: number;
  nota_media: number;
  taxa_aprovacao: number;
  total_aprovadas: number;
  total_reprovadas: number;
}

interface CriterionDetail {
  criterionId?: string;
  label: string;
  status: 'pass' | 'fail';
  weight?: number;
  obtainedScore?: number;
  comment?: string;
  timestamp?: string;
  evidence_text?: string;
}

interface TranscriptionSegment {
  start: string;
  end: string;
  text: string;
  // Optional diarization metadata from backend
  speaker_confidence?: number;
  speaker_risk?: 'low' | 'medium' | 'high';
  speaker_ambiguous?: boolean;
  speaker_source_ids?: number[];
  speaker_persona_ids?: number[];
}

interface SupervisorPortalProps {
  userRole: 'admin' | 'supervisor' | null;
}

const APPROVAL_THRESHOLD_RATIO = 0.8;
const SHOW_SUPERVISOR_FEEDBACK = false;
const MATCH_STOPWORDS = new Set([
  'a', 'o', 'os', 'as', 'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'no', 'na', 'nos', 'nas',
  'para', 'por', 'com', 'sem', 'uma', 'um', 'uns', 'umas', 'que', 'foi', 'ser', 'ter', 'ao',
  'aos', 'ou', 'se', 'sua', 'seu', 'suas', 'seus', 'esta', 'esse', 'essa', 'isso', 'como',
  'mais', 'menos', 'sobre', 'antes', 'depois', 'durante', 'porque', 'motivo', 'criterio',
  'criterios', 'operador', 'ligacao', 'auditoria', 'atende', 'nao', 'não', 'motorista', 'cliente', 'policia', 'polícia', 'telefone', 'telefonia',
]);

// Helpers
function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return '';
  const d = new Date(isoString);
  return d.toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
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

function parseTranscription(raw: string | TranscriptionSegment[] | null | undefined): TranscriptionSegment[] {
  if (!raw) return [];
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function normalizeMatchText(value: string | null | undefined): string {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractMatchKeywords(detail: CriterionDetail): string[] {
  const source = normalizeMatchText(`${detail.label} ${detail.comment || ''}`);
  return Array.from(new Set(
    source
      .split(' ')
      .filter((token) => token.length >= 3 && !MATCH_STOPWORDS.has(token))
      .sort((a, b) => b.length - a.length),
  )).slice(0, 8);
}

function findCriterionEvidence(detail: CriterionDetail, transcription: TranscriptionSegment[]): TranscriptionSegment | null {
  if (!transcription.length) {
    return null;
  }

  const keywords = extractMatchKeywords(detail);
  if (!keywords.length) {
    return null;
  }

  let bestSegment: TranscriptionSegment | null = null;
  let bestScore = 0;

  for (const segment of transcription) {
    const textWithoutSpeaker = segment.text.replace(/^[^:]+:\s*/, '');
    const normalizedSegment = normalizeMatchText(textWithoutSpeaker);
    if (!normalizedSegment) {
      continue;
    }

    let score = 0;
    for (const keyword of keywords) {
      if (normalizedSegment.includes(keyword)) {
        score += keyword.length >= 6 ? 2 : 1;
      }
    }

    if (score > bestScore) {
      bestScore = score;
      bestSegment = segment;
    }
  }

  return bestScore >= 2 ? bestSegment : null;
}

function groupByOperator(audits: AuditItem[]): Record<string, AuditItem[]> {
  const groups: Record<string, AuditItem[]> = {};
  for (const a of audits) {
    const key = a.operator_name || 'Operador Desconhecido';
    if (!groups[key]) groups[key] = [];
    groups[key].push(a);
  }
  return groups;
}

function getAuditListStatusMeta(audit: AuditItem): { label: string; className: string } {
  if (audit.is_missing) {
    return {
      label: 'Não auditado',
      className: 'border border-slate-600/30 bg-slate-800/40 text-slate-400 theme-light:border-slate-300 theme-light:bg-slate-200 theme-light:text-slate-600',
    };
  }

  if (audit.status === 'contestation_pending_review') {
    return {
      label: 'Contestacao em analise',
      className: 'border border-amber-500/20 bg-amber-500/10 text-amber-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800',
    };
  }

  if (audit.status === 'contestation_accepted' || audit.contestation_verdict === 'accepted') {
    return {
      label: 'Contestacao aceita',
      className: 'border border-red-500/20 bg-red-500/10 text-red-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800',
    };
  }

  if (audit.contestation_verdict === 'rejected') {
    return {
      label: 'Contestacao negada',
      className: 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800',
    };
  }

  if (audit.status === 'approved') {
    return {
      label: 'Publicada',
      className: 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800',
    };
  }

  if (audit.status === 'pending_approval') {
    return {
      label: 'Aguardando decisao',
      className: 'border border-primary-500/20 bg-primary-500/10 text-primary-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800',
    };
  }

  return {
    label: 'Em andamento',
    className: 'border border-slate-600/30 bg-slate-800/40 text-slate-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-700',
  };
}

function getAuditRecordLabel(index: number, timestamp: string): string {
  const formattedDate = formatDate(timestamp)?.split(',')[0]?.trim();
  return formattedDate ? `Registro ${index + 1} · ${formattedDate}` : `Registro ${index + 1}`;
}

// Sub-components

function KPICards({ kpis }: { kpis: KPIs, isAdmin: boolean }) {
  const cards = [
    { label: 'Total de auditorias', value: kpis.total_auditorias, note: 'Amostra operacional do período' },
    { label: 'Nota média', value: `${(kpis.nota_media / 10).toFixed(1)} / 10`, note: 'Média das avaliações consolidadas' },
    { label: 'Taxa de aprovação', value: `${kpis.taxa_aprovacao}%`, note: 'Registros acima do corte oficial' },
    { label: 'Aprovadas / Reprovadas', value: `${kpis.total_aprovadas} / ${kpis.total_reprovadas}`, note: 'Visão imediata do saldo de qualidade' },
  ];

  return (
    <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((c) => (
        <div key={c.label} className="metric-card">
          <p className="metric-label">{c.label}</p>
          <p className="metric-value !text-2xl md:!text-3xl">{c.value}</p>
          <p className="metric-note">{c.note}</p>
        </div>
      ))}
    </div>
  );
}

function CriterionIcon({ status }: { status: string }) {
  switch (status) {
    case 'pass':
      return <CheckCircle2 size={16} className="text-primary-300 shrink-0 theme-light:text-slate-700" />;
    case 'fail':
    default:
      return <XCircle size={16} className="text-slate-500 shrink-0 theme-light:text-slate-600" />;
  }
}

function FeedbackForm({ audit, onSaved }: { audit: AuditItem; onSaved: () => void }) {
  const { showToast } = useToast();
  const hasFeedback = !!audit.feedback;
  const [isEditing, setIsEditing] = useState(!hasFeedback);
  const [gestorNome, setGestorNome] = useState(audit.feedback?.gestor_nome || '');
  const [feedbackTexto, setFeedbackTexto] = useState(audit.feedback?.feedback_texto || '');
  const [pontosMelhoria, setPontosMelhoria] = useState(audit.feedback?.pontos_melhoria || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!gestorNome.trim() || !feedbackTexto.trim()) {
      showToast({
        variant: 'warning',
        title: 'Campos obrigatórios',
        description: 'Preencha seu nome e o feedback antes de salvar.',
      });
      return;
    }
    setSaving(true);
    try {
      await apiFetchJson('/api/gestores/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audit_id: audit.id,
          gestor_nome: gestorNome.trim(),
          feedback_texto: feedbackTexto.trim(),
          pontos_melhoria: pontosMelhoria.trim(),
        }),
      });
      setIsEditing(false);
      onSaved();
      showToast({
        variant: 'success',
        title: 'Feedback salvo',
        description: 'O registro foi atualizado com sucesso.',
      });
    } catch (err) {
      console.error(err);
      showToast({
        variant: 'error',
        title: 'Falha ao salvar feedback',
        description: 'Tente novamente em alguns instantes.',
      });
    } finally {
      setSaving(false);
    }
  };

  if (!isEditing && hasFeedback) {
    return (
      <div className="space-y-3">
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-sm text-emerald-400 theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:text-slate-800">
          Registrado por <strong>{audit.feedback!.gestor_nome}</strong> em {formatDate(audit.feedback!.criado_em)}
        </div>
        <div className="text-sm text-slate-300">
          <p className="font-semibold text-slate-400 mb-1">Feedback:</p>
          <p className="whitespace-pre-wrap">{audit.feedback!.feedback_texto}</p>
        </div>
        {audit.feedback!.pontos_melhoria && (
          <div className="text-sm text-slate-300">
            <p className="font-semibold text-slate-400 mb-1">Plano de ação:</p>
            <p className="whitespace-pre-wrap">{audit.feedback!.pontos_melhoria}</p>
          </div>
        )}
        <button
          onClick={() => setIsEditing(true)}
          className="btn-accent px-3 py-1.5 text-xs font-semibold"
        >
          Editar feedback
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Nome do supervisor</label>
        <input
          type="text"
          value={gestorNome}
          onChange={(e) => setGestorNome(e.target.value)}
          placeholder="Ex: Supervisor Silva..."
          className="w-full bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 theme-light:placeholder-slate-400"
        />
      </div>
      <div>
        <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Feedback ao operador</label>
        <textarea
          value={feedbackTexto}
          onChange={(e) => setFeedbackTexto(e.target.value)}
          placeholder="Descreva o feedback principal para o operador."
          rows={3}
          className="w-full bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-primary-500/50 focus:outline-none transition-colors resize-y theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 theme-light:placeholder-slate-400"
        />
      </div>
      <div>
        <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Orientação adicional</label>
        <textarea
          value={pontosMelhoria}
          onChange={(e) => setPontosMelhoria(e.target.value)}
          placeholder="Informe o que o operador deve priorizar na próxima ação."
          rows={3}
          className="w-full bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-primary-500/50 focus:outline-none transition-colors resize-y theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 theme-light:placeholder-slate-400"
        />
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary flex-1 px-4 py-2 text-sm font-semibold"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <MessageSquarePlus size={14} />}
          {saving ? 'Salvando...' : 'Salvar feedback'}
        </button>
        {hasFeedback && (
          <button
            onClick={() => setIsEditing(false)}
            className="btn-ghost px-4 py-2 text-sm"
          >
            Cancelar
          </button>
        )}
      </div>
    </div>
  );
}

function AuditTab({
  audit,
  onFeedbackSaved,
  onAuditActionComplete,
}: {
  audit: AuditItem;
  onFeedbackSaved: () => void;
  onAuditActionComplete: (auditId: number) => void;
  isAdmin: boolean;
}) {
  const { showToast } = useToast();
  const criteria = parseDetails(audit.details);
  const transcription = parseTranscription(audit.transcription);
  const audioUrl = audit.audio_url ?? null;
  const criteriaWithEvidence = criteria.map((detail) => ({
    detail,
    evidence: findCriterionEvidence(detail, transcription),
  }));
  const pass = audit.max_score > 0 && (audit.score / audit.max_score) >= APPROVAL_THRESHOLD_RATIO;


  const audioRef = useRef<HTMLAudioElement | null>(null);
  const pendingSeekSecondsRef = useRef<number | null>(null);
  const [shouldLoadAudio, setShouldLoadAudio] = useState(false);

  useEffect(() => {
    pendingSeekSecondsRef.current = null;
    setShouldLoadAudio(false);
  }, [audit.id]);

  const playFromSeconds = useCallback((seconds: number) => {
    if (!audioRef.current || Number.isNaN(seconds)) return;
    audioRef.current.currentTime = seconds;
    audioRef.current.play().catch(console.error);
  }, []);

  const seekAudio = useCallback((timeStr: string) => {
    if (!timeStr) return;
    const parts = timeStr.split(':');
    let seconds = 0;
    if (parts.length === 3) {
      seconds = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseFloat(parts[2].replace(',', '.'));
    } else if (parts.length === 2) {
      seconds = parseInt(parts[0]) * 60 + parseFloat(parts[1].replace(',', '.'));
    }
    if (isNaN(seconds)) {
      return;
    }

    if (!audioRef.current && audioUrl) {
      pendingSeekSecondsRef.current = seconds;
      setShouldLoadAudio(true);
      return;
    }

    playFromSeconds(seconds);
  }, [audioUrl, playFromSeconds]);

  const handleAudioCanPlay = useCallback(() => {
    const pendingSeconds = pendingSeekSecondsRef.current;
    if (pendingSeconds === null) {
      return;
    }
    pendingSeekSecondsRef.current = null;
    playFromSeconds(pendingSeconds);
  }, [playFromSeconds]);

  const [savingAction, setSavingAction] = useState(false);
  const [contestReason, setContestReason] = useState('');
  const [selectedCriteria, setSelectedCriteria] = useState<Map<string, string>>(new Map());

  const toggleCriterion = (label: string) => {
    setSelectedCriteria((prev) => {
      const next = new Map(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.set(label, '');
      }
      return next;
    });
  };

  const updateCriterionReason = (label: string, reason: string) => {
    setSelectedCriteria((prev) => {
      const next = new Map(prev);
      if (next.has(label)) {
        next.set(label, reason);
      }
      return next;
    });
  };

  const handleAction = async (action: 'approve' | 'contest') => {
    if (action === 'contest' && !contestReason.trim()) {
      showToast({
        variant: 'warning',
        title: 'Contestação do supervisor obrigatória',
        description: 'Descreva o que o supervisor discorda da análise antes de enviar.',
      });
      return;
    }
    setSavingAction(true);
    try {
      const contestedArray = Array.from(selectedCriteria.entries()).map(([label, reason]) => ({ label, reason }));
      await apiFetchJson(`/api/gestores/auditorias/${audit.id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: action === 'contest'
          ? JSON.stringify({ reason: contestReason, contested_criteria: contestedArray })
          : JSON.stringify({}),
      });
      // Optimistic UI: remove o card da lista sem reload global, preservando o scroll/contexto do supervisor.
      onAuditActionComplete(audit.id);
      showToast({
        variant: 'success',
        title: action === 'approve' ? 'Auditoria aprovada' : 'Contestação enviada',
        description: action === 'approve'
          ? 'A auditoria foi publicada no painel oficial.'
          : 'A contestação foi enviada para revisão técnica.',
      });
    } catch (err) {
      console.error(err);
      showToast({
        variant: 'error',
        title: action === 'approve' ? 'Falha ao aprovar' : 'Falha ao contestar',
        description: 'Não foi possível concluir a ação solicitada.',
      });
    } finally {
      setSavingAction(false);
      setContestReason('');
      setSelectedCriteria(new Map());
    }
  };



  const handleExport = async (format: 'excel' | 'pdf') => {
    try {
      const endpoint = format === 'excel' ? '/api/export/gestores' : '/api/export/gestores/pdf';
      const blob = await apiFetchBlob(`${endpoint}?audit_id=${audit.id}&sector_id=${audit.sector_id || ''}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          timestamp: audit.timestamp,
          operatorName: audit.operator_name,
          operatorId: audit.operator_id,
          score: audit.score,
          maxPossibleScore: audit.max_score,
          summary: audit.summary,
          details: criteria,
          transcription,
          source_type: 'audio',
        }),
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `relatorio_${audit.operator_name?.replace(/\s+/g, '_') || 'audit'}_${audit.id}.${format === 'excel' ? 'xlsx' : 'pdf'}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
      showToast({
        variant: 'error',
        title: 'Falha na exportação',
        description: 'Não foi possível gerar o arquivo solicitado.',
      });
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 p-5 animate-in fade-in duration-300">
      {/* Left: Criteria */}
      <div>
        <div className="mb-4">
          <p className="section-title-sm">
            Alerta: <span className="text-primary-400">{audit.alert_label || 'Sem alerta informado'}</span>
          </p>
          <p className="text-xs text-slate-500 mt-1">Data: {formatDate(audit.timestamp)}</p>
        </div>

        <div className="bg-slate-800/40 rounded-xl border border-white/5 p-4 theme-light:bg-white theme-light:border-slate-300">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Critérios avaliados</p>
          {criteriaWithEvidence.length > 0 ? (
            <div className="space-y-0.5">
              {criteriaWithEvidence.map(({ detail, evidence }, i) => (
                <div key={i} className="flex items-start gap-3 py-3 border-b border-white/[0.03] last:border-0">
                  {audit.status === 'pending_approval' && (
                    <label className="flex items-center mt-0.5 cursor-pointer shrink-0">
                      <input
                        type="checkbox"
                        checked={selectedCriteria.has(detail.label)}
                        onChange={() => toggleCriterion(detail.label)}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-primary-500 focus:ring-primary-500 cursor-pointer"
                      />
                    </label>
                  )}
                  <CriterionIcon status={detail.status} />
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <span className="text-[13px] text-slate-300 leading-relaxed">{detail.label}</span>
                    {(detail.timestamp || evidence) && (
                      <div className="flex items-center gap-1.5">
                        <Clock size={11} className="text-primary-400 shrink-0 theme-light:text-slate-500" />
                        <span 
                          onClick={() => {
                            const t = detail.timestamp || evidence?.start;
                            if (t) seekAudio(t.split(' ')[0]);
                          }}
                          className="text-[11px] font-semibold font-mono text-primary-300 theme-light:text-slate-600 cursor-pointer hover:underline hover:text-primary-400 transition-colors"
                          title="Clique para ouvir o áudio neste momento"
                        >
                          {detail.timestamp
                            ? detail.timestamp
                            : `${evidence!.start}${evidence!.end ? ` — ${evidence!.end}` : ''}`}
                        </span>
                      </div>
                    )}
                    {detail.comment ? (
                      <p className="text-xs leading-relaxed text-slate-400 theme-light:text-slate-700">{detail.comment}</p>
                    ) : null}
                    {detail.evidence_text ? (
                      <p className="text-xs leading-relaxed italic text-slate-500 theme-light:text-slate-500 border-l-2 border-slate-700 pl-2 ml-1">
                        &ldquo;{detail.evidence_text}&rdquo;
                      </p>
                    ) : (evidence && !detail.timestamp) ? (
                      <p className="text-xs leading-relaxed italic text-slate-500 theme-light:text-slate-500 border-l-2 border-slate-700 pl-2 ml-1">
                        &ldquo;{evidence.text.replace(/^[^:]+:\s*/, '')}&rdquo;
                      </p>
                    ) : null}
                    {selectedCriteria.has(detail.label) && (
                      <div className="mt-3">
                        <textarea
                          placeholder="Detalhe por que este critério está sendo contestado..."
                          value={selectedCriteria.get(detail.label) || ''}
                          onChange={(e) => updateCriterionReason(detail.label, e.target.value)}
                          className="w-full bg-slate-900/50 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-300 outline-none resize-y theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 placeholder-slate-600 focus:border-primary-500/50 transition-colors"
                          rows={2}
                        />
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Critérios não detalhados nesta auditoria.</p>
          )}
        </div>

        <div className="mt-4 bg-slate-800/40 rounded-xl border border-white/5 p-4 theme-light:bg-white theme-light:border-slate-300">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{'Transcri\u00e7\u00e3o'}</p>
            {transcription.length > 0 ? (
              <span className="text-[11px] text-slate-500">{transcription.length} trechos</span>
            ) : null}
          </div>

          {audioUrl && (
            <div className="mb-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                <Volume2 size={13} className="text-primary-400" />
                Gravação da ligação
              </p>
              <AuthenticatedAudioPlayer
                audioUrl={audioUrl}
                ref={audioRef}
                autoLoad={shouldLoadAudio}
                preload="metadata"
                onCanPlay={handleAudioCanPlay}
              />
            </div>
          )}

          <ReadOnlyTranscription transcription={transcription} maxHeightClass="max-h-[24rem]" onSeekAudio={seekAudio} />
        </div>
      </div>

      {/* Right: Score + Feedback */}
      <div className="space-y-4">

        {audit.status === 'approved' && !audit.contestation_verdict && (
          <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 theme-light:bg-slate-100 theme-light:border-slate-300">
            <p className="section-title-sm flex items-center gap-2"><CheckCircle2 size={16} /> Publicada no painel</p>
          </div>
        )}
        {audit.status === 'contestation_pending_review' && (
          <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 theme-light:bg-slate-100 theme-light:border-slate-300">
            <p className="section-title-sm flex items-center gap-2"><AlertCircle size={16} /> Contestação em revisão técnica</p>
            <p className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 theme-light:text-slate-700">Contestação do supervisor</p>
            <p className="text-xs text-slate-400 mt-1 theme-light:text-slate-700">{audit.contestation_reason}</p>
          </div>
        )}
        {audit.contestation_verdict === 'rejected' && (
          <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 theme-light:bg-slate-100 theme-light:border-slate-300">
            <p className="section-title-sm flex items-center gap-2"><CheckCircle2 size={16} /> Contestação negada</p>
            {audit.contested_criteria && (
              <div className="mt-2 text-xs text-slate-400 theme-light:text-slate-600">
                <span className="font-semibold text-slate-300 theme-light:text-slate-800">Tópicos avaliados: </span>
                {(() => {
                  if (Array.isArray(audit.contested_criteria)) {
                    return (audit.contested_criteria as any[]).map((item: any) => typeof item === 'string' ? item : item.label).join(' • ');
                  }
                  try {
                    const parsed = JSON.parse(audit.contested_criteria as string);
                    if (Array.isArray(parsed)) {
                      return parsed.map((item: any) => typeof item === 'string' ? item : item.label).join(' • ');
                    }
                    return String(parsed);
                  } catch {
                    return typeof audit.contested_criteria === 'string' ? audit.contested_criteria : 'N/A';
                  }
                })()}
              </div>
            )}
            <p className="text-xs text-slate-400 mt-2 theme-light:text-slate-700">Defesa técnica: {audit.review_defense || 'Sem defesa registrada.'}</p>
            {(audit.reviewed_by || audit.reviewed_at) && (
              <p className="text-[11px] text-slate-500 mt-1.5 theme-light:text-slate-600">
                Revisado por <span className="font-semibold text-slate-300 theme-light:text-slate-800">{audit.reviewed_by || '—'}</span>
                {audit.reviewed_at ? ` em ${formatDate(audit.reviewed_at)}` : ''}
              </p>
            )}
          </div>
        )}
        {(audit.status === 'contestation_accepted' || audit.contestation_verdict === 'accepted') && (
          <div className="rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 theme-light:bg-slate-100 theme-light:border-slate-300">
            <p className="section-title-sm flex items-center gap-2"><XCircle size={16} /> Contestação aceita</p>
            {audit.contested_criteria && (
              <div className="mt-2 text-xs text-slate-400 theme-light:text-slate-600">
                <span className="font-semibold text-slate-300 theme-light:text-slate-800">Tópicos revisados: </span>
                {(() => {
                  if (Array.isArray(audit.contested_criteria)) {
                    return (audit.contested_criteria as any[]).map((item: any) => typeof item === 'string' ? item : item.label).join(' • ');
                  }
                  try {
                    const parsed = JSON.parse(audit.contested_criteria as string);
                    if (Array.isArray(parsed)) {
                      return parsed.map((item: any) => typeof item === 'string' ? item : item.label).join(' • ');
                    }
                    return String(parsed);
                  } catch {
                    return typeof audit.contested_criteria === 'string' ? audit.contested_criteria : 'N/A';
                  }
                })()}
              </div>
            )}
            <p className="text-xs text-slate-400 mt-2 theme-light:text-slate-700">Defesa técnica: {audit.review_defense || 'Sem defesa registrada.'}</p>
            {(audit.reviewed_by || audit.reviewed_at) && (
              <p className="text-[11px] text-slate-500 mt-1.5 theme-light:text-slate-600">
                Revisado por <span className="font-semibold text-slate-300 theme-light:text-slate-800">{audit.reviewed_by || '—'}</span>
                {audit.reviewed_at ? ` em ${formatDate(audit.reviewed_at)}` : ''}
              </p>
            )}
          </div>
        )}

        <div className="bg-slate-800/40 rounded-xl border border-white/5 p-4 text-center theme-light:bg-white theme-light:border-slate-300">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">Resultado</p>
          <p className={`text-3xl font-extrabold ${audit.is_missing ? 'text-slate-400 theme-light:text-slate-500' : pass ? 'text-primary-300 theme-light:text-slate-900' : 'text-slate-300 theme-light:text-slate-800'}`}>
            {audit.is_missing ? '—' : audit.max_score > 0 ? ((audit.score / audit.max_score) * 10).toFixed(2) : '0.00'} <span className="text-sm font-medium text-slate-500">{audit.is_missing ? '' : '/ 10'}</span>
          </p>
          <div className="mt-2">
            {audit.is_missing ? (
              <span className="inline-block text-[11px] font-semibold uppercase px-2.5 py-1 rounded-md bg-slate-500/10 text-slate-400 border border-slate-500/20 theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:text-slate-700">
                Pendente
              </span>
            ) : pass ? (
              <span className="inline-block text-[11px] font-semibold uppercase px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:text-slate-800">
                Aprovado
              </span>
            ) : (
              <span className="inline-block text-[11px] font-semibold uppercase px-2.5 py-1 rounded-md bg-red-500/10 text-red-400 border border-red-500/20 theme-light:bg-slate-200 theme-light:border-slate-300 theme-light:text-slate-700">
                Reprovado
              </span>
            )}
          </div>
        </div>

        {audit.summary && (
          <div className="bg-slate-800/40 rounded-xl border-l-2 border-primary-500 p-3 text-[13px] text-slate-400 leading-relaxed">
            {audit.summary}
          </div>
        )}

        {/* Export buttons */}
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            onClick={() => handleExport('excel')}
            className="btn-ghost flex-1 px-3 py-2 text-xs font-medium"
          >
            <Download size={13} />
            Excel
          </button>
          <button
            onClick={() => handleExport('pdf')}
            className="btn-ghost flex-1 px-3 py-2 text-xs font-medium"
          >
            <FileText size={13} />
            PDF
          </button>
        </div>

        {audit.status === 'pending_approval' && (
          <div className="bg-slate-800/40 rounded-xl border border-white/5 p-4 space-y-3 theme-light:bg-white theme-light:border-slate-300">
            <div className="flex items-center justify-between mb-2">
              <p className="section-title-sm">Aprovação pendente</p>
            </div>
            <p className="text-xs text-slate-400 mb-2">Esta auditoria aguarda sua revisão para seguir para o painel oficial.</p>
            <div className="space-y-2">
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Contestação do supervisor
              </label>
              <textarea
                placeholder="Descreva o que está incorreto ou frágil na análise. Ex.: critério, trecho e motivo da discordância."
                className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-slate-300 outline-none resize-none theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                value={contestReason}
                onChange={e => setContestReason(e.target.value)}
                rows={3}
              />
              <p className="text-xs text-slate-500 theme-light:text-slate-600">
                Esse texto segue para a análise técnica como justificativa formal do supervisor.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <button onClick={() => handleAction('approve')} disabled={savingAction} className="btn-primary flex-1 px-3 py-2 text-sm font-medium">
                  {savingAction ? 'Salvando...' : 'Aprovar análise'}
                </button>
                <button
                  onClick={() => handleAction('contest')}
                  disabled={savingAction || !contestReason.trim()}
                  className="btn-danger flex-1 px-3 py-2 text-sm font-medium"
                >
                  {savingAction ? 'Enviando...' : 'Enviar contestação'}
                </button>
              </div>
            </div>
          </div>
        )}

        {SHOW_SUPERVISOR_FEEDBACK ? (
          <div className="bg-slate-800/40 rounded-xl border border-white/5 p-4 theme-light:bg-white theme-light:border-slate-300">
            <p className="section-title-sm mb-3 flex items-center gap-2">
              <MessageSquarePlus size={16} className="text-primary-400" />
              Feedback do supervisor
            </p>
            <FeedbackForm audit={audit} onSaved={onFeedbackSaved} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function OperatorCard({
  operatorName,
  audits,
  onFeedbackSaved,
  onAuditActionComplete,
  isAdmin,
}: {
  operatorName: string;
  audits: AuditItem[];
  onFeedbackSaved: () => void;
  onAuditActionComplete: (auditId: number) => void;
  isAdmin: boolean;
}) {
  const [activeTab, setActiveTab] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);
  const firstAudit = audits[0];
  const activeAudit = audits[activeTab] ?? firstAudit;
  const sectorLabel = formatOperationalLabel(firstAudit.sector_id) || 'N/A';
  const scaleLabel = formatOperationalLabel(firstAudit.escala) || firstAudit.escala;
  const activeStatus = getAuditListStatusMeta(activeAudit);
  const reviewSummary = audits.map((audit, index) => ({
    id: audit.id,
    recordLabel: getAuditRecordLabel(index, audit.timestamp),
    ...getAuditListStatusMeta(audit),
  }));

  useEffect(() => {
    if (activeTab >= audits.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveTab(Math.max(0, audits.length - 1));
    }
  }, [activeTab, audits.length]);

  return (
    <div className="glass-panel rounded-xl border border-white/5 overflow-hidden theme-light:bg-white theme-light:border-slate-300">
      {/* Header */}
      <div className="flex flex-col gap-3 border-b border-white/5 bg-white/[0.02] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <p className="section-title">{operatorName}</p>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-400 tracking-wider">
              {sectorLabel}
            </span>
            {firstAudit.escala && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-primary-500/10 border border-primary-500/20 text-primary-400 tracking-wider theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:text-slate-700">
                {scaleLabel}
              </span>
            )}
            {firstAudit.supervisor && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-500/10 border border-slate-500/20 text-slate-400 tracking-wider theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:text-slate-700">
                Sup: {firstAudit.supervisor}
              </span>
            )}
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded tracking-wider ${activeStatus.className}`}>
              {activeStatus.label}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {reviewSummary.map((summary) => (
              <span
                key={summary.id}
                className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-wide ${summary.className}`}
              >
                {summary.recordLabel}: {summary.label}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:items-end">
          {firstAudit.operator_id && (
            <span className="text-xs text-slate-500">ID Huawei: {firstAudit.operator_id}</span>
          )}
          <button
            type="button"
            onClick={() => setIsExpanded((current) => !current)}
            className="btn-ghost inline-flex items-center justify-center gap-2 px-3 py-2 text-xs font-semibold"
            aria-expanded={isExpanded}
          >
            <ChevronDown size={14} className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
            {isExpanded ? 'Ocultar análise' : 'Abrir análise'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      {isExpanded && audits.length > 1 && (
        <div className="overflow-x-auto border-b border-white/5 bg-slate-900/50 hide-scrollbar theme-light:bg-slate-50 theme-light:border-slate-300">
          <div className="flex min-w-max">
            {audits.map((audit, idx) => {
              const auditStatus = getAuditListStatusMeta(audit);
              return (
                <button
                  key={audit.id}
                  onClick={() => setActiveTab(idx)}
                  className={`btn-filter rounded-none border-x-0 border-t-0 px-5 py-3 text-left text-sm font-semibold ${activeTab === idx ? 'btn-filter-active !bg-primary-500/5' : '!border-transparent !bg-transparent'}`}
                >
                  <div>
                    {getAuditRecordLabel(idx, audit.timestamp)}
                  </div>
                  <span className={`mt-2 inline-flex rounded px-2 py-0.5 text-[10px] font-semibold ${auditStatus.className}`}>
                    {auditStatus.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Active tab content */}
      {isExpanded && (
        <AuditTab
          audit={activeAudit}
          onFeedbackSaved={onFeedbackSaved}
          onAuditActionComplete={onAuditActionComplete}
          isAdmin={isAdmin}
        />
      )}
    </div>
  );
}

// Main component
export function SupervisorPortal({ userRole }: SupervisorPortalProps) {
  const [audits, setAudits] = useState<AuditItem[]>([]);
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState('');
  const [supervisorFilter, setSupervisorFilter] = useState('');
  const [escalaFilter, setEscalaFilter] = useState('');
  const [sectorFilter, setSectorFilter] = useState('');

  // Date filters
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState<string>((now.getMonth() + 1).toString());
  const [selectedYear, setSelectedYear] = useState<string>(now.getFullYear().toString());

  const [supervisorsData, setSupervisorsData] = useState<Record<string, string[]>>({});
  const [sectors, setSectors] = useState<string[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');

  const isAdmin = userRole === 'admin';

  // Load supervisors data
  useEffect(() => {
    apiFetchJson<Record<string, string[]>>('/api/rh/supervisores')
      .then(setSupervisorsData)
      .catch(console.error);
  }, []);

  // Debounce search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => setDebouncedSearch(searchText), 400);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchText]);

  // Fetch audits
  const fetchAudits = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '500' });
      if (sectorFilter) params.append('sector_id', sectorFilter);
      if (supervisorFilter) params.append('supervisor', supervisorFilter);
      if (escalaFilter) params.append('escala', escalaFilter);
      if (debouncedSearch) params.append('operator_name', debouncedSearch);

      // Add month/year filters
      if (selectedMonth) params.append('month', selectedMonth);
      if (selectedYear) params.append('year', selectedYear);

      const data = await apiFetchJson<{ kpis: KPIs; auditorias: AuditItem[] }>(`/api/gestores/auditorias?${params}`);
      setAudits(data.auditorias || []);
      setKpis(data.kpis);

      const uniqueSectors = [...new Set((data.auditorias || []).map((a) => a.sector_id).filter(Boolean))] as string[];
      setSectors(uniqueSectors);
    } catch (err) {
      console.error('Error fetching audits:', err);
    } finally {
      setLoading(false);
    }
  }, [sectorFilter, supervisorFilter, escalaFilter, debouncedSearch, selectedMonth, selectedYear]);

  useEffect(() => {
    fetchAudits();
  }, [fetchAudits]);

  const handleAuditActionComplete = useCallback((auditId: number) => {
    setAudits((prev) => prev.filter((a) => a.id !== auditId));
  }, []);

  // Months list
  const allMonths = [
    { v: '1', l: 'Janeiro' }, { v: '2', l: 'Fevereiro' }, { v: '3', l: 'Março' },
    { v: '4', l: 'Abril' }, { v: '5', l: 'Maio' }, { v: '6', l: 'Junho' },
    { v: '7', l: 'Julho' }, { v: '8', l: 'Agosto' }, { v: '9', l: 'Setembro' },
    { v: '10', l: 'Outubro' }, { v: '11', l: 'Novembro' }, { v: '12', l: 'Dezembro' }
  ];

  // Restrict to April onwards for 2026, show all for other years
  const availableMonths = selectedYear === '2026' ? allMonths.slice(3) : allMonths;
  
  const years = ['2026', '2027'];

  // Handle month selection when switching to 2026
  useEffect(() => {
    if (selectedYear === '2026' && parseInt(selectedMonth) < 4) {
      setSelectedMonth('4'); // Force April if previous month was Jan/Feb/Mar
    }
  }, [selectedYear, selectedMonth]);

  // Compute escalas for selected supervisor
  const availableEscalas: string[] = (() => {
    if (supervisorFilter && supervisorsData[supervisorFilter]) {
      return [...supervisorsData[supervisorFilter]].sort();
    }
    const all = new Set<string>();
    Object.values(supervisorsData).forEach((list) => list.forEach((e) => all.add(e)));
    return [...all].sort();
  })();

  const grouped = groupByOperator(audits);

  return (
    <div className="space-y-6 pb-10">
      {/* Header */}
      <PageHeader
        eyebrow="nstech | Supervisão"
        titleFirstWord="Revisão"
        titleRest="de Auditorias"
        subtitle="Revise registros e acompanhe aprovações."
      />

      {/* KPIs */}
      {kpis && <KPICards kpis={kpis} isAdmin={isAdmin} />}

      {/* Export Actions (Temporarily Disabled) */}
      {/* Export Actions (Temporarily Disabled) */}
      {/*
      <ExportActions
        selectedMonth={selectedMonth}
        selectedYear={selectedYear}
        sectorFilter={sectorFilter}
      />
      */}

      {/* Filters */}
      <div className="surface-toolbar">
        <div className={`grid grid-cols-1 sm:grid-cols-2 ${isAdmin ? 'lg:grid-cols-3' : ''} gap-4 ${isAdmin ? 'mb-4' : ''}`}>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Mês</label>
              <div className="relative">
                <select
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  className="w-full appearance-none bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 pr-8 text-sm text-slate-200 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                >
                  {availableMonths.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Ano</label>
              <div className="relative">
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(e.target.value)}
                  className="w-full appearance-none bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 pr-8 text-sm text-slate-200 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                >
                  {years.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Buscar operador</label>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Busque por nome..."
                className="w-full bg-slate-800/60 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 theme-light:placeholder-slate-400"
              />
            </div>
          </div>

          {isAdmin && (
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Setor</label>
              <div className="relative">
                <select
                  value={sectorFilter}
                  onChange={(e) => setSectorFilter(e.target.value)}
                  className="w-full appearance-none bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 pr-8 text-sm text-slate-200 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                >
                  <option value="">Todos os setores</option>
                  {sectors.map((s) => (
                    <option key={s} value={s}>{formatOperationalLabel(s) || s}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            </div>
          )}
        </div>

        {isAdmin && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Supervisor</label>
              <div className="relative">
                <select
                  value={supervisorFilter}
                  onChange={(e) => {
                    setSupervisorFilter(e.target.value);
                    setEscalaFilter('');
                  }}
                  className="w-full appearance-none bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 pr-8 text-sm text-slate-200 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                >
                  <option value="">Todos os supervisores</option>
                  {Object.keys(supervisorsData).sort().map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Escala</label>
              <div className="relative">
                <select
                  value={escalaFilter}
                  onChange={(e) => setEscalaFilter(e.target.value)}
                  className="w-full appearance-none bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 pr-8 text-sm text-slate-200 focus:border-primary-500/50 focus:outline-none transition-colors theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                >
                  <option value="">Todas as escalas</option>
                  {availableEscalas.map((e) => (
                    <option key={e} value={e}>{formatOperationalLabel(e) || e}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-16 theme-light:text-slate-700">
          <Loader2 className="animate-spin text-primary-400" size={28} />
          <span className="ml-3 text-slate-400 text-sm">Carregando auditorias...</span>
        </div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="glass-panel rounded-xl border border-dashed border-white/10 py-16 text-center theme-light:bg-white theme-light:border-slate-300">
          <p className="text-slate-500">Nenhuma auditoria encontrada com os filtros atuais.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([opName, opAudits]) => (
            <OperatorCard
              key={opName}
              operatorName={opName}
              audits={opAudits}
              onFeedbackSaved={fetchAudits}
              onAuditActionComplete={handleAuditActionComplete}
              isAdmin={isAdmin}
            />
          ))}
        </div>
      )}
    </div>
  );
}

