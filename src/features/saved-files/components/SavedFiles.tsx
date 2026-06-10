import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Camera,
  Download,
  Edit3,
  Eye,
  FileText,
  FolderOpen,
  Mic,
  Plus,
  Save,
  ScrollText,
  Search,
  Trash2,
  Video,
  X,
  Send,
  Loader2,
} from 'lucide-react';
import { useToast } from '../../../shared/components/ToastProvider';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { AuthenticatedAudioPlayer } from '../../../shared/components/AuthenticatedAudioPlayer';
import { ReadOnlyTranscription } from '../../../shared/components/ReadOnlyTranscription';
import type { AuditResultDetail, TranscriptionSegment } from '../../../shared/types/audit';
import { apiFetch, apiFetchJson } from '../../../shared/lib/apiClient';
import { formatAudioMoment } from '../../../shared/lib/auditDates';
import { OriginBadge } from '../../../shared/lib/auditOrigin';
import { formatOperationalLabel } from '../../../shared/lib/operationalLabels';
import {
  getAuditStatusBadgeClass,
  getAuditStatusLabel,
  normalizeAuditStatus,
} from '../../audit/lib/auditStatus';

interface ArquivoSalvo {
  id: number;
  tipo: string;
  conteudo: string;
  arquivo: string;
  data_analise: string;
  audit_id: number | null;
  operator_name: string;
  sector_id: string;
  alert_label: string;
  score: number | null;
  metadata: Record<string, unknown>;
  criado_por: string;
  audit_status?: string;
}

interface ListResponse {
  items: ArquivoSalvo[];
  total: number;
}

interface SavedAuditMetadataDetail {
  criterionId?: string;
  label: string;
  status: AuditResultDetail['status'];
  weight?: number;
  obtainedScore?: number;
  comment: string;
}

interface SavedAuditMetadata {
  kind?: string;
  summary?: string;
  ai_feedback?: string;
  score?: number;
  maxPossibleScore?: number;
  details?: SavedAuditMetadataDetail[];
  transcription?: TranscriptionSegment[];
  source_type?: 'audio' | 'pdf';
  timestamp?: string;
  audio_date?: string;
}

interface SavedAuditView {
  summary: string;
  aiFeedback: string;
  details: SavedAuditMetadataDetail[];
  transcription: TranscriptionSegment[];
  score?: number;
  maxPossibleScore?: number;
  sourceType?: 'audio' | 'pdf';
  timestamp?: string;
  audioDate?: string;
}

function readMetadataText(metadata: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  const nestedOperator = metadata.operator;
  if (nestedOperator && typeof nestedOperator === 'object') {
    const operatorRecord = nestedOperator as Record<string, unknown>;
    for (const key of keys) {
      const value = operatorRecord[key];
      if (typeof value === 'string' && value.trim()) {
        return value.trim();
      }
    }
  }

  return '';
}

const TIPO_CONFIG: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  Auditoria: { icon: FileText, label: 'Auditoria', color: 'text-blue-400' },
  auditoria: { icon: FileText, label: 'Auditoria', color: 'text-blue-400' },
  Transcricao: { icon: ScrollText, label: 'Transcrição', color: 'text-emerald-400' },
  'Transcrição': { icon: ScrollText, label: 'Transcrição', color: 'text-emerald-400' },
  Oitiva: { icon: Mic, label: 'Oitiva', color: 'text-amber-400' },
  Vistoria: { icon: Camera, label: 'Vistoria', color: 'text-purple-400' },
  Video: { icon: Video, label: 'Vídeo', color: 'text-rose-400' },
  'Vídeo': { icon: Video, label: 'Vídeo', color: 'text-rose-400' },
};

function isAuditFileType(tipo: string): boolean {
  return tipo.trim().toLowerCase() === 'auditoria';
}


const DETAIL_LINE_REGEX = /^\[([^\]]+)\]\s*(.+?)\s*:\s*(.+)$/;

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return iso;
  }
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function getTipoConfig(tipo: string) {
  return TIPO_CONFIG[tipo] || { icon: FileText, label: tipo || 'Documento', color: 'text-slate-400' };
}

function readAuditMetadata(item: ArquivoSalvo): SavedAuditMetadata {
  if (!item.metadata || typeof item.metadata !== 'object') {
    return {};
  }
  return item.metadata as SavedAuditMetadata;
}

function extractSavedOperatorId(item: ArquivoSalvo): string {
  if (!item.metadata || typeof item.metadata !== 'object') {
    return '';
  }

  return readMetadataText(item.metadata as Record<string, unknown>, [
    'operator_id',
    'operatorId',
    'operator_telefonia',
    'operatorTelefonia',
    'id_telefonia',
    'idTelefonia',
  ]);
}

function normalizeAuditDetails(rawDetails: unknown): SavedAuditMetadataDetail[] {
  if (!Array.isArray(rawDetails)) {
    return [];
  }

  const normalizedDetails: SavedAuditMetadataDetail[] = [];

  for (const detail of rawDetails) {
    if (!detail || typeof detail !== 'object') {
      continue;
    }

    const candidate = detail as Record<string, unknown>;
    const status = normalizeAuditStatus(String(candidate.status || ''));
    const label = String(candidate.label || '').trim();

    if (!status || !label) {
      continue;
    }

    normalizedDetails.push({
      criterionId: String(candidate.criterionId || ''),
      label,
      status,
      comment: String(candidate.comment || '').trim(),
      weight: typeof candidate.weight === 'number' ? candidate.weight : undefined,
      obtainedScore: typeof candidate.obtainedScore === 'number' ? candidate.obtainedScore : undefined,
    });
  }

  return normalizedDetails;
}

function normalizeTranscription(rawSegments: unknown): TranscriptionSegment[] {
  if (!Array.isArray(rawSegments)) {
    return [];
  }

  return rawSegments
    .map((segment) => {
      if (!segment || typeof segment !== 'object') {
        return null;
      }

      const candidate = segment as Record<string, unknown>;
      const start = String(candidate.start || '').trim();
      const end = String(candidate.end || '').trim();
      const text = String(candidate.text || '').trim();

      if (!text) {
        return null;
      }

      return { start, end, text } satisfies TranscriptionSegment;
    })
    .filter((segment): segment is TranscriptionSegment => segment !== null);
}

function parseAuditContent(content: string): Pick<SavedAuditView, 'summary' | 'details'> {
  const lines = content.split(/\r?\n/);
  const summaryLines: string[] = [];
  const details: SavedAuditMetadataDetail[] = [];
  let skipNextMetadataValue = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    if (skipNextMetadataValue) {
      skipNextMetadataValue = false;
      continue;
    }
    if (line === 'Data/hora da ligação' || line === 'Data/hora da ligacao') {
      skipNextMetadataValue = true;
      continue;
    }
    if (line.startsWith('Data/hora da ligação:') || line.startsWith('Data/hora da ligacao:')) {
      continue;
    }

    const detailMatch = line.match(DETAIL_LINE_REGEX);
    if (detailMatch) {
      const [, rawStatus, rawLabel, rawComment] = detailMatch;
      const status = normalizeAuditStatus(rawStatus);
      if (status) {
        details.push({
          label: rawLabel.trim(),
          status,
          comment: rawComment.trim(),
        });
        continue;
      }
    }

    if (
      line === 'Resumo da auditoria'
      || line === 'Critérios avaliados'
      || line === 'Criterios avaliados'
      || line === 'Feedback ao operador'
    ) {
      continue;
    }

    if (line.startsWith('- ')) {
      const [head, ...tail] = line.slice(2).split('|');
      const status = normalizeAuditStatus(head || '');
      if (status) {
        const joinedTail = tail.join('|').trim();
        const [label, comment = ''] = joinedTail.split(':');
        details.push({
          label: (label || '').trim(),
          status,
          comment: comment.trim(),
        });
        continue;
      }
    }

    summaryLines.push(line);
  }

  return {
    summary: summaryLines.join('\n\n').trim(),
    details,
  };
}

function buildSavedAuditView(item: ArquivoSalvo | null): SavedAuditView | null {
  if (!item || !isAuditFileType(item.tipo)) {
    return null;
  }

  const metadata = readAuditMetadata(item);
  const details = normalizeAuditDetails(metadata.details);
  const transcription = normalizeTranscription(metadata.transcription);

  if (details.length > 0 || metadata.summary || metadata.ai_feedback || transcription.length > 0) {
    return {
      summary: String(metadata.summary || '').trim(),
      aiFeedback: String(metadata.ai_feedback || '').trim(),
      details,
      transcription,
      score: typeof metadata.score === 'number' ? metadata.score : undefined,
      maxPossibleScore: typeof metadata.maxPossibleScore === 'number' ? metadata.maxPossibleScore : undefined,
      sourceType: metadata.source_type,
      timestamp: metadata.timestamp,
      audioDate: metadata.audio_date,
    };
  }

  const parsed = parseAuditContent(item.conteudo);
  if (!parsed.summary && parsed.details.length === 0) {
    return null;
  }

  return {
    summary: parsed.summary,
    aiFeedback: '',
    details: parsed.details,
    transcription: [],
  };
}

function buildAuditExportPayload(item: ArquivoSalvo) {
  const view = buildSavedAuditView(item);
  if (!view) {
    return null;
  }

  const scoreFromDetails = view.details.reduce(
    (total, detail) => total + (typeof detail.obtainedScore === 'number' ? detail.obtainedScore : 0),
    0
  );
  const maxScoreFromDetails = view.details.reduce(
    (total, detail) => total + (typeof detail.weight === 'number' ? detail.weight : 0),
    0
  );

  const score =
    typeof view.score === 'number'
      ? view.score
      : typeof item.score === 'number'
        ? item.score
        : scoreFromDetails > 0
          ? scoreFromDetails
          : null;
  const maxPossibleScore =
    typeof view.maxPossibleScore === 'number'
      ? view.maxPossibleScore
      : maxScoreFromDetails > 0
        ? maxScoreFromDetails
        : null;

  if (score === null || maxPossibleScore === null) {
    return null;
  }

  return {
    score,
    maxPossibleScore,
    summary: view.summary || item.conteudo,
    ai_feedback: view.aiFeedback || undefined,
    details: view.details.map((detail, index) => ({
      criterionId: detail.criterionId || String(index + 1),
      label: detail.label,
      status: detail.status,
      weight: typeof detail.weight === 'number' ? detail.weight : 0,
      obtainedScore: typeof detail.obtainedScore === 'number' ? detail.obtainedScore : 0,
      comment: detail.comment,
    })),
    transcription: view.transcription,
    operatorName: item.operator_name || '',
    operatorId: '',
    timestamp: view.timestamp || item.data_analise,
    source_type: view.sourceType || 'audio',
  };
}

function getObtainedScore(detail: Pick<SavedAuditMetadataDetail, 'status' | 'weight'>): number {
  const weight = typeof detail.weight === 'number' ? detail.weight : 0;
  if (detail.status === 'pass') return weight;
  return 0;
}

function calculateSavedAuditScores(details: SavedAuditMetadataDetail[], sectorId?: string) {
  let score = 0;
  let maxPossibleScore = 0;
  let zeroed = false;

  const trackingSectors = ['bas', 'distribuicao', 'uti', 'transferencia', 'fenix', 'rastreamento'];
  const sector = (sectorId || '').toLowerCase().trim();

  for (const detail of details) {
    maxPossibleScore += typeof detail.weight === 'number' ? detail.weight : 0;
    score += getObtainedScore(detail);

    if (
      trackingSectors.includes(sector)
      && detail.status === 'fail'
      && detail.label.toLowerCase().includes('senha')
    ) {
      zeroed = true;
    }
  }

  if (!zeroed) {
    for (const detail of details) {
      if (detail.status !== 'fail') continue;

      const text = `${detail.label} ${detail.comment || ''}`.toLowerCase();
      if (
        ['cadastro', 'mondelez'].includes(sector)
        && (text.includes('45 segundos')
          || text.includes('comportamento hostil')
          || text.includes('incomum')
          || text.includes('abandono'))
      ) {
        zeroed = true;
        break;
      }

      if (
        ['logistica', 'logistica_unilever', 'operacao_taborda'].includes(sector)
        && (text.includes('comportamento hostil') || text.includes('incomum') || text.includes('abandono'))
      ) {
        zeroed = true;
        break;
      }

      if (
        trackingSectors.includes(sector)
        && (text.includes('comportamento hostil')
          || text.includes('incomum')
          || text.includes('abandono')
          || text.includes('dica de senha')
          || text.includes('dica da senha')
          || text.includes('senha ou cpf'))
      ) {
        zeroed = true;
        break;
      }
    }
  }

  return {
    score: zeroed ? 0 : Number(score.toFixed(2)),
    maxPossibleScore: Number(maxPossibleScore.toFixed(2)),
  };
}

export function SavedFiles() {
  const { showToast } = useToast();
  const [items, setItems] = useState<ArquivoSalvo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState<ArquivoSalvo | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [sendingSupervisorId, setSendingSupervisorId] = useState<number | null>(null);

  const handleSendToSupervisor = async (auditId: number, force: boolean = false) => {
    setSendingSupervisorId(auditId);
    try {
      const url = `/api/dashboard/force-send?audit_id=${auditId}${force ? '&force=true' : ''}`;
      await apiFetchJson(url, { method: 'POST' });
      
      if (selectedItem && selectedItem.audit_id === auditId) {
        setSelectedItem(null);
      }
      
      fetchItems();
      showToast({ variant: 'success', title: 'Sucesso', description: 'Auditoria enviada ao supervisor com sucesso.' });
    } catch (err: any) {
      if (err.status === 429) {
        if (window.confirm(err.message || 'Limite de 2 auditorias mensais atingido. Deseja enviar mesmo assim?')) {
          handleSendToSupervisor(auditId, true);
          return;
        }
      } else {
        console.error('Erro ao enviar ao supervisor:', err);
        showToast({ variant: 'error', title: 'Erro', description: err.message || 'Erro ao enviar ao supervisor.' });
      }
    } finally {
      setSendingSupervisorId(null);
    }
  };

  // Structured editing state for Auditoria items
  const [isStructuredEdit, setIsStructuredEdit] = useState(false);
  const [editSummary, setEditSummary] = useState('');
  const [editFeedback, setEditFeedback] = useState('');
  const [editDetails, setEditDetails] = useState<SavedAuditMetadataDetail[]>([]);
  const [editTranscription, setEditTranscription] = useState<TranscriptionSegment[]>([]);
  const detailsContainerRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const handleSeekAudio = useCallback((timeStr: string) => {
    if (!audioRef.current) return;
    const parts = timeStr.split(':').map(Number);
    let seconds = 0;
    if (parts.length === 3) seconds = parts[0] * 3600 + parts[1] * 60 + parts[2];
    else if (parts.length === 2) seconds = parts[0] * 60 + parts[1];
    else seconds = parts[0];
    audioRef.current.currentTime = seconds;
    audioRef.current.play().catch(() => {});
  }, []);

  const updateEditTranscriptionSegment = (index: number, field: keyof TranscriptionSegment, value: string) => {
    setEditTranscription((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const addEditTranscriptionSegment = (afterIndex: number) => {
    setEditTranscription((prev) => {
      const updated = [...prev];
      const prevSegment = updated[afterIndex];
      updated.splice(afterIndex + 1, 0, {
        start: prevSegment?.end || '00:00',
        end: prevSegment?.end || '00:00',
        text: '',
      });
      return updated;
    });
  };

  const removeEditTranscriptionSegment = (index: number) => {
    setEditTranscription((prev) => prev.filter((_, i) => i !== index));
  };

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetchJson<ListResponse>('/api/salvos?limit=100');
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error('Erro ao carregar arquivos salvos:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleDelete = async (id: number) => {
    if (!confirm('Tem certeza que deseja excluir este arquivo? A auditoria vinculada será descartada e removida da visão do supervisor.')) return;
    try {
      if (selectedItem?.audit_id) {
        try {
          await apiFetchJson(`/api/audit/${selectedItem.audit_id}/discard`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: 'Excluído da tela de arquivos salvos' })
          });
        } catch (discardErr) {
          console.warn('Falha ao descartar auditoria vinculada (pode já ter sido removida):', discardErr);
        }
      }
      
      await apiFetchJson(`/api/salvos/${id}`, { method: 'DELETE' });
      
      if (selectedItem?.id === id) {
        setSelectedItem(null);
        setIsEditing(false);
      }
      showToast({ variant: 'success', title: 'Excluído', description: 'Registro removido com sucesso.' });
      fetchItems();
    } catch (err) {
      console.error('Erro ao excluir:', err);
      showToast({ variant: 'error', title: 'Erro ao excluir', description: 'Não foi possível remover o registro.' });
    }
  };

  const handleSaveEdit = async () => {
    if (!selectedItem) return;
    setSaving(true);
    try {
      if (isStructuredEdit) {
        const recalculatedDetails = editDetails.map((detail) => ({
          ...detail,
          obtainedScore: getObtainedScore(detail),
        }));
        const { score, maxPossibleScore } = calculateSavedAuditScores(recalculatedDetails, selectedItem.sector_id);
        // Build updated metadata from structured fields
        const existingMeta = readAuditMetadata(selectedItem);
        const updatedMetadata: SavedAuditMetadata = {
          ...existingMeta,
          summary: editSummary,
          ai_feedback: editFeedback,
          score,
          maxPossibleScore,
          details: recalculatedDetails,
          transcription: editTranscription,
        };
        // Rebuild conteudo text as well for backwards compat
        const summarySection = editSummary ? `Resumo da auditoria\n${editSummary}` : '';
        const feedbackSection = editFeedback ? `\n\nFeedback ao operador\n${editFeedback}` : '';
        const detailsSection = recalculatedDetails.length > 0
          ? `\n\nCritérios avaliados\n${recalculatedDetails.map(d => `[${getAuditStatusLabel(d.status)}] ${d.label}: ${d.comment || 'Sem justificativa'}`).join('\n')}`
          : '';
        const newConteudo = `${summarySection}${feedbackSection}${detailsSection}`.trim();

        await apiFetchJson(`/api/salvos/${selectedItem.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conteudo: newConteudo,
            score,
            metadata: updatedMetadata,
          }),
        });
        setSelectedItem({
          ...selectedItem,
          conteudo: newConteudo,
          score,
          metadata: updatedMetadata as Record<string, unknown>,
        });
      } else {
        await apiFetchJson(`/api/salvos/${selectedItem.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conteudo: editContent }),
        });
        setSelectedItem({ ...selectedItem, conteudo: editContent });
      }
      setIsEditing(false);
      setIsStructuredEdit(false);
      fetchItems();
    } catch (err: any) {
      console.error('Erro ao salvar edicao:', err);
      alert(err.message || 'Ocorreu um erro ao salvar o arquivo.');
    } finally {
      setSaving(false);
    }
  };

  const handleExportTxt = (item: ArquivoSalvo) => {
    const blob = new Blob([item.conteudo], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${item.tipo}_${item.arquivo || item.id}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportPdf = async (item: ArquivoSalvo) => {
    const payload = buildAuditExportPayload(item);
    if (!payload) {
      handleExportTxt(item);
      return;
    }

    try {
      const resp = await apiFetch('/api/export/report/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${item.tipo}_${item.arquivo || item.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      handleExportTxt(item);
    }
  };

  const startEdit = (item: ArquivoSalvo) => {
    const auditView = buildSavedAuditView(item);
    if (auditView && (auditView.details.length > 0 || auditView.summary)) {
      // Structured edit mode for auditorias
      setEditSummary(auditView.summary);
      setEditFeedback(auditView.aiFeedback);
      setEditDetails(auditView.details.map(d => ({ ...d })));
      setEditTranscription(auditView.transcription.map(t => ({ ...t })));
      setIsStructuredEdit(true);
    } else {
      // Generic textarea mode for other types
      setEditContent(item.conteudo);
      setEditTranscription([]);
      setIsStructuredEdit(false);
    }
    setIsEditing(true);
  };

  const updateEditDetail = (index: number, field: 'status' | 'comment', value: string) => {
    setEditDetails(prev => {
      const updated = [...prev];
      if (field === 'status') {
        const normalized = normalizeAuditStatus(value);
        if (normalized) {
          updated[index] = { ...updated[index], status: normalized };
        }
      } else {
        updated[index] = { ...updated[index], [field]: value };
      }
      return updated;
    });
  };

  const filteredItems = useMemo(() => {
    if (!searchQuery) {
      return items;
    }

    const term = searchQuery.toLowerCase();
    return items.filter(
      (item) => {
        const metadataStr = JSON.stringify(item.metadata || {}).toLowerCase();
        return item.arquivo.toLowerCase().includes(term) ||
               (item.operator_name || '').toLowerCase().includes(term) ||
               (item.sector_id || '').toLowerCase().includes(term) ||
               (item.alert_label || '').toLowerCase().includes(term) ||
               (item.criado_por || '').toLowerCase().includes(term) ||
               metadataStr.includes(term) ||
               item.conteudo.toLowerCase().includes(term);
      }
    );
  }, [items, searchQuery]);

  const selectedAuditView = useMemo(() => buildSavedAuditView(selectedItem), [selectedItem]);
  const selectedOperatorId = useMemo(() => (selectedItem ? extractSavedOperatorId(selectedItem) : ''), [selectedItem]);

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Arquivos"
        titleFirstWord="Auditorias"
        titleRest="em Arquivos"
        subtitle="Consulte, edite e exporte registros salvos."
      />

      <ModuleInstructions
        storageKey="instructions:saved-files"
        steps={[
          'Consulte as auditorias já realizadas (manuais e automáticas).',
          'Abra um registro para revisar transcrição, pontuação e alertas.',
          'Envie ao Supervisor as que devem seguir, ou exporte os dados.',
        ]}
      />

      <div className="panel-box">
        <div className="mb-5 flex items-center gap-3">
          <p className="section-title">Biblioteca de arquivos</p>
          <span className="ml-auto text-xs text-slate-500">
            {total} arquivo{total !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="mb-5">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <input
              type="text"
              placeholder="Buscar por arquivo, operador, setor, supervisor ou conteúdo"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary-500/50 theme-light:bg-slate-200 theme-light:border-slate-300 theme-light:text-slate-900"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:min-h-[26rem]">
          <div className="rounded-xl bg-black/20 border border-white/5 overflow-hidden theme-light:bg-slate-100 theme-light:border-slate-300">
            <div className="px-4 py-2.5 border-b border-white/5 theme-light:border-slate-300">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Arquivos disponíveis
              </span>
            </div>
            <div className="overflow-y-auto lg:max-h-[min(34rem,62vh)]">
              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <div className="h-6 w-6 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : filteredItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-amber-500 bg-amber-500/10 rounded-xl border border-amber-500/20 m-4">
                  <FolderOpen className="h-10 w-10 mb-3 opacity-60" />
                  <p className="text-sm font-semibold">Alerta: Nenhum arquivo encontrado com os filtros informados.</p>
                </div>
              ) : (
                filteredItems.map((item) => {
                  const cfg = getTipoConfig(item.tipo);
                  const Icon = cfg.icon;
                  const isActive = selectedItem?.id === item.id;

                  return (
                    <button
                      key={item.id}
                      onClick={() => {
                        setSelectedItem(item);
                        setIsEditing(false);
                      }}
                      className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-all border-b border-white/5 theme-light:border-slate-200 ${isActive
                        ? 'bg-primary-500/10 border-l-2 border-l-primary-500'
                        : 'hover:bg-white/[0.03] theme-light:hover:bg-slate-200'
                        }`}
                    >
                      <Icon className={`h-4 w-4 shrink-0 ${cfg.color}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate theme-light:text-slate-900">
                          {item.arquivo || `${cfg.label} #${item.id}`}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`text-[10px] font-semibold uppercase ${cfg.color}`}>
                            {cfg.label}
                          </span>
                          {item.operator_name ? (
                            <span className="text-[10px] text-slate-500 truncate">{item.operator_name}</span>
                          ) : null}
                          {item.audit_status === 'pending_approval' && (
                            <span className="ml-1 inline-flex items-center rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-emerald-400 border border-emerald-500/20">
                              Enviado
                            </span>
                          )}
                          {item.audit_id ? (
                            <OriginBadge criadoPor={item.criado_por} size="sm" hideUnknown />
                          ) : null}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-0.5 shrink-0">
                        <span className="text-[10px] text-slate-500">{formatDate(item.data_analise)}</span>
                        <span className="text-[10px] text-slate-600">{formatTime(item.data_analise)}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          <div className="rounded-xl bg-black/20 border border-white/5 overflow-hidden flex flex-col theme-light:bg-slate-100 theme-light:border-slate-300">
            <div className="px-4 py-3 border-b border-white/5 flex items-start gap-3 theme-light:border-slate-300">
              <Eye className="h-4 w-4 text-slate-500 mt-0.5" />
              <div className="min-w-0 flex-1">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block truncate">
                  {selectedItem
                    ? selectedItem.arquivo || `${getTipoConfig(selectedItem.tipo).label} #${selectedItem.id}`
                    : 'Leitura detalhada'}
                </span>
                <p className="mt-1 text-[11px] text-slate-500">
                  {selectedAuditView
                    ? 'Resumo, contexto e critérios organizados para consulta rápida.'
                    : 'Visualize o conteúdo salvo ou edite antes de exportar.'}
                </p>
              </div>
              {selectedItem && !isEditing ? (
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => startEdit(selectedItem)}
                    className="btn-icon"
                    aria-label={`Editar ${selectedItem.arquivo || 'documento salvo'}`}
                    title="Editar"
                  >
                    <Edit3 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExportPdf(selectedItem)}
                    className="btn-icon"
                    aria-label={`Exportar ${selectedItem.arquivo || 'documento salvo'} em PDF`}
                    title="Exportar"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(selectedItem.id)}
                    className="btn-icon-danger"
                    aria-label={`Excluir ${selectedItem.arquivo || 'documento salvo'}`}
                    title="Excluir"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                  {selectedItem.audit_id ? (
                    <button
                      type="button"
                      onClick={() => handleSendToSupervisor(selectedItem.audit_id!)}
                      disabled={sendingSupervisorId === selectedItem.audit_id}
                      className="btn-icon"
                      aria-label="Enviar ao supervisor"
                      title="Enviar ao supervisor"
                    >
                      {sendingSupervisorId === selectedItem.audit_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" />
                      ) : (
                        <Send className="h-3.5 w-3.5 text-amber-500" />
                      )}
                    </button>
                  ) : null}
                </div>
              ) : null}
              {isEditing ? (
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={handleSaveEdit}
                    disabled={saving}
                    className="btn-success px-2.5 py-1 text-xs font-medium"
                  >
                    <Save className="h-3 w-3" />
                    {saving ? 'Salvando...' : 'Salvar'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsEditing(false)}
                    className="btn-icon"
                    aria-label="Cancelar edição"
                    title="Cancelar"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : null}
            </div>

            <div className="flex-1 overflow-y-auto p-4 lg:max-h-[min(34rem,62vh)]">
              {!selectedItem ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-500 py-16">
                  <FileText className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">Selecione um arquivo para visualizar.</p>
                </div>
              ) : isEditing ? (
                isStructuredEdit ? (
                  <div className="space-y-4">
                    {/* Summary */}
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                        Resumo da auditoria
                      </p>
                      <textarea
                        value={editSummary}
                        onChange={(e) => setEditSummary(e.target.value)}
                        className="w-full p-3 rounded-lg bg-black/30 border border-white/10 text-sm text-white resize-none focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 leading-relaxed"
                        rows={4}
                        placeholder="Resumo da auditoria..."
                      />
                    </div>

                    {/* Feedback */}
                    <div className="rounded-xl border border-primary-500/20 bg-primary-500/5 p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-400 mb-2">
                        Feedback ao operador
                      </p>
                      <textarea
                        value={editFeedback}
                        onChange={(e) => setEditFeedback(e.target.value)}
                        className="w-full p-3 rounded-lg bg-black/30 border border-white/10 text-sm text-white resize-none focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900 leading-relaxed italic"
                        rows={3}
                        placeholder="Feedback para o operador..."
                      />
                    </div>

                    {/* Criteria */}
                    {editDetails.length > 0 ? (
                      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
                          Critérios avaliados ({editDetails.length})
                        </p>
                        <div className="space-y-3" ref={detailsContainerRef}>
                          {editDetails.map((detail, index) => (
                            <div
                              key={`edit-${detail.criterionId || detail.label}-${index}`}
                              className="rounded-xl border border-white/5 bg-black/20 px-3 py-3"
                            >
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                <p className="text-sm font-semibold text-white flex-1">{detail.label}</p>
                                <select
                                  value={detail.status}
                                  onChange={(e) => updateEditDetail(index, 'status', e.target.value)}
                                  className="text-xs rounded-lg border px-2.5 py-1.5 min-w-[160px] bg-slate-800 border-white/15 text-slate-200 focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                                >
                                  <option value="pass">Atende</option>
                                  <option value="fail">Não atende</option>
                                </select>                              </div>
                              <textarea
                                value={detail.comment}
                                onChange={(e) => updateEditDetail(index, 'comment', e.target.value)}
                                placeholder="Justificativa..."
                                className="w-full mt-2 p-2 rounded-lg bg-black/30 border border-white/10 text-sm text-slate-300 resize-none focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                                rows={2}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {/* Transcription Edit */}
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
                        Transcrição ({editTranscription.length})
                      </p>
                      <div className="space-y-3">
                        {editTranscription.map((segment, idx) => (
                          <div key={`edit-ts-${idx}`} className="p-4 rounded-xl bg-black/20 border border-white/5 space-y-3">
                            <div className="flex gap-2 items-center">
                              <input
                                type="text"
                                value={segment.start}
                                onChange={(e) => updateEditTranscriptionSegment(idx, 'start', e.target.value)}
                                className="w-24 bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-sm font-mono text-primary-400"
                                placeholder="00:00"
                              />
                              <input
                                type="text"
                                value={segment.end}
                                onChange={(e) => updateEditTranscriptionSegment(idx, 'end', e.target.value)}
                                className="w-24 bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-sm font-mono text-primary-400"
                                placeholder="00:00"
                              />
                              {editTranscription.length > 1 ? (
                                <button
                                  type="button"
                                  onClick={() => removeEditTranscriptionSegment(idx)}
                                  className="ml-auto p-1.5 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                                  title="Remover segmento"
                                >
                                  <Trash2 size={15} />
                                </button>
                              ) : null}
                            </div>
                            <textarea
                              value={segment.text}
                              onChange={(e) => updateEditTranscriptionSegment(idx, 'text', e.target.value)}
                              className="w-full bg-slate-900 border border-white/10 rounded-xl p-3 text-[15px] text-slate-200 outline-none focus:border-primary-500/50 resize-none theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                              rows={2}
                              placeholder="Texto da fala..."
                            />
                            <div className="flex justify-center py-1">
                              <button
                                type="button"
                                onClick={() => addEditTranscriptionSegment(idx)}
                                className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs text-primary-400/70 hover:text-primary-300 hover:bg-primary-500/10 border border-dashed border-primary-500/20 hover:border-primary-500/40 transition-all"
                                title="Inserir nova fala abaixo"
                              >
                                <Plus size={13} />
                                Inserir fala
                              </button>
                            </div>
                          </div>
                        ))}
                        {editTranscription.length === 0 && (
                          <div className="flex justify-center py-1">
                            <button
                              type="button"
                              onClick={() => addEditTranscriptionSegment(-1)}
                              className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs text-primary-400/70 hover:text-primary-300 hover:bg-primary-500/10 border border-dashed border-primary-500/20 hover:border-primary-500/40 transition-all"
                            >
                              <Plus size={13} />
                              Adicionar transcrição
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full h-full min-h-[400px] p-3 rounded-lg bg-black/30 border border-white/10 text-sm text-white font-mono resize-none focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900"
                  />
                )
              ) : (
                <div className="space-y-4">
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {selectedItem.operator_name ? (
                      <div className="rounded-xl border border-blue-500/20 bg-blue-500/10 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-blue-300">Nome do operador</p>
                        <p className="mt-1 text-sm text-blue-100">{selectedItem.operator_name}</p>
                      </div>
                    ) : null}
                    {selectedOperatorId ? (
                      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300">ID Huawei</p>
                        <p className="mt-1 text-sm text-emerald-100">{selectedOperatorId}</p>
                      </div>
                    ) : null}
                    {selectedItem.alert_label ? (
                      <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-300">Alerta</p>
                        <p className="mt-1 text-sm text-amber-100">{selectedItem.alert_label}</p>
                      </div>
                    ) : null}
                    {selectedItem.sector_id ? (
                      <div className="rounded-xl border border-purple-500/20 bg-purple-500/10 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-purple-300">Setor</p>
                        <p className="mt-1 text-sm text-purple-100">{formatOperationalLabel(selectedItem.sector_id) || selectedItem.sector_id}</p>
                      </div>
                    ) : null}
                    {selectedAuditView?.audioDate || selectedAuditView?.timestamp ? (
                      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300">Data/hora da ligação</p>
                        <p className="mt-1 text-sm text-cyan-100">{formatAudioMoment(selectedAuditView.audioDate, selectedAuditView.timestamp)}</p>
                      </div>
                    ) : null}
                    {(typeof selectedItem.score === 'number' || typeof selectedAuditView?.score === 'number') ? (
                      <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-rose-300">Nota</p>
                        <p className="mt-1 text-sm font-semibold text-rose-100">
                          {typeof selectedAuditView?.score === 'number' ? selectedAuditView.score.toFixed(2) : (selectedItem.score != null ? selectedItem.score.toFixed(2) : '')}
                        </p>
                      </div>
                    ) : null}
                    <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Data do arquivo</p>
                      <p className="mt-1 text-sm text-slate-200">
                        {formatDate(selectedItem.data_analise)} {formatTime(selectedItem.data_analise)}
                      </p>
                    </div>
                  </div>

                  {selectedAuditView ? (
                    <>
                      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                          Resumo principal
                        </p>
                        <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
                          {selectedAuditView.summary || 'Resumo não informado.'}
                        </p>
                      </div>

                      {selectedAuditView.aiFeedback ? (
                        <div className="rounded-xl border border-primary-500/20 bg-primary-500/5 p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-400 mb-2">
                            Feedback ao operador
                          </p>
                          <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
                            {selectedAuditView.aiFeedback}
                          </p>
                        </div>
                      ) : null}

                      {selectedAuditView.details.length > 0 ? (
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
                            Critérios avaliados
                          </p>
                          <div className="space-y-3">
                            {selectedAuditView.details.map((detail, index) => (
                              <div
                                key={`${detail.criterionId || detail.label}-${index}`}
                                className="rounded-xl border border-white/5 bg-black/20 px-3 py-3"
                              >
                                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                                  <div>
                                    <p className="text-sm font-semibold text-white">{detail.label}</p>
                                    {typeof detail.weight === 'number' ? (
                                      <p className="text-[11px] text-slate-500 mt-1">
                                        Peso {detail.weight}
                                        {typeof detail.obtainedScore === 'number'
                                          ? ` | Nota obtida ${detail.obtainedScore}`
                                          : ''}
                                      </p>
                                    ) : null}
                                  </div>
                                  <span
                                    className={`inline-flex items-center justify-center rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${getAuditStatusBadgeClass(detail.status)}`}
                                  >
                                    {getAuditStatusLabel(detail.status)}
                                  </span>
                                </div>
                                <p className="mt-3 text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                                  {detail.comment || 'Sem justificativa registrada.'}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {selectedAuditView.transcription.length > 0 ? (
                        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                          <div className="flex items-center justify-between gap-3 mb-3">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                              Transcrição salva
                            </p>
                            <span className="text-[11px] text-slate-500">
                              {selectedAuditView.transcription.length} trecho(s)
                            </span>
                          </div>
                          {selectedItem.audit_id && selectedAuditView.sourceType !== 'pdf' ? (
                            <div className="mb-4">
                              <AuthenticatedAudioPlayer
                                className="w-full custom-audio"
                                audioUrl={`/api/audit/${selectedItem.audit_id}/audio`}
                                ref={audioRef}
                              />
                            </div>
                          ) : null}
                          <ReadOnlyTranscription
                            transcription={selectedAuditView.transcription}
                            onSeekAudio={handleSeekAudio}
                            maxHeightClass="max-h-[300px]"
                          />
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                        Conteúdo salvo
                      </p>
                      <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed theme-light:text-slate-700">
                        {selectedItem.conteudo}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
