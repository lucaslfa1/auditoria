/**
 * Tela de admin do FEEDBACK da IA (calibração): regras/observações que ajustam
 * o comportamento do classificador/avaliador.
 *
 * CRUD via `/api/ai-feedback` (GET com filtros; POST cria; PUT `/{id}` edita;
 * DELETE `/{id}` remove) e liga/desliga em `/api/ai-feedback/{id}/toggle`. O que
 * está ativo aqui alimenta a calibração aplicada nas próximas classificações/
 * auditorias.
 */
import { useState, useEffect, useCallback } from 'react';
import {
    Brain, Plus, Pencil, Trash2, ToggleLeft, ToggleRight,
    AlertCircle, Check, X, Lightbulb, Shield, Tag, BookOpen, Filter, List
} from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { useAuditCriteria } from '../../../contexts/AuditCriteriaContext';

interface Feedback {
    id: number;
    tipo: string;
    setor: string | null;
    criterio_id: string | null;
    situacao: string;
    correcao: string;
    justificativa: string;
    exemplo_transcricao: string | null;
    criado_por: string;
    ativo: number;
    criado_em: string;
    atualizado_em: string;
}

const TIPO_OPTIONS = [
    { id: 'classificacao', label: 'Classificação', icon: Tag, color: 'text-blue-400', bg: 'bg-blue-500/15 border-blue-500/20' },
    { id: 'avaliacao', label: 'Avaliação', icon: Lightbulb, color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/20' },
    { id: 'fatal_flag', label: 'Zerar Ligação', icon: Shield, color: 'text-red-400', bg: 'bg-red-500/15 border-red-500/20' },
    { id: 'regra_geral', label: 'Regra Geral', icon: BookOpen, color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/20' },
];

interface AIFeedbackPageProps {
    theme?: 'dark' | 'light';
}

interface InstructionBlock {
    situacao: string;
    correcao: string;
    justificativa: string;
    exemplo_transcricao: string;
}

interface FormData {
    tipo: string;
    setor: string;
    criterio_id: string;
    blocks: InstructionBlock[];
}

const EMPTY_BLOCK: InstructionBlock = {
    situacao: '',
    correcao: '',
    justificativa: '',
    exemplo_transcricao: '',
};

const EMPTY_FORM: FormData = {
    tipo: 'classificacao',
    setor: '',
    criterio_id: '',
    blocks: [{ ...EMPTY_BLOCK }],
};

type TabId = 'nova' | 'cadastradas';

export function AIFeedbackPage({ theme = 'dark' }: AIFeedbackPageProps) {
    const [items, setItems] = useState<Feedback[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState<FormData>(EMPTY_FORM);
    const [saving, setSaving] = useState(false);
    const [filterTipo, setFilterTipo] = useState<string>('');
    const [filterSetor, setFilterSetor] = useState<string>('');
    const [activeTab, setActiveTab] = useState<TabId>('nova');

    const { data: auditCriteriaData } = useAuditCriteria();
    const SETOR_OPTIONS = (auditCriteriaData?.sectors || []).map(s => ({ id: s.id, label: s.label }));

    const isDark = theme === 'dark';
    const cardClass = isDark
        ? 'bg-slate-800/50 border-white/10 hover:bg-slate-800'
        : 'bg-white border-slate-200 hover:bg-slate-50';
    const inputClass = isDark
        ? 'bg-slate-800 border-white/15 text-slate-200 placeholder-slate-500'
        : 'bg-white border-slate-300 text-gray-800 placeholder-gray-400';
    const labelClass = isDark
        ? 'text-slate-400'
        : 'text-gray-600';

    const fetchItems = useCallback(async () => {
        try {
            setLoading(true);
            const params = new URLSearchParams();
            if (filterTipo) params.set('tipo', filterTipo);
            if (filterSetor) params.set('setor', filterSetor);
            const qs = params.toString();
            const data = await apiFetchJson<{ items: Feedback[] }>(`/api/ai-feedback${qs ? `?${qs}` : ''}`);
            setItems(data.items);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao carregar orientações');
        } finally {
            setLoading(false);
        }
    }, [filterTipo, filterSetor]);

    useEffect(() => { fetchItems(); }, [fetchItems]);

    const handleSubmit = async () => {
        const hasPartial = form.blocks.some(b =>
            (b.situacao.trim() || b.correcao.trim() || b.justificativa.trim()) &&
            !(b.situacao.trim() && b.correcao.trim() && b.justificativa.trim())
        );
        if (hasPartial) {
            setError('Preencha Situação, Correção e Justificativa para todos os blocos adicionados.');
            return;
        }

        const validBlocks = form.blocks.filter(b => b.situacao.trim() && b.correcao.trim() && b.justificativa.trim());
        if (validBlocks.length === 0) {
            setError('Preencha Situação, Correção e Justificativa em pelo menos um bloco.');
            return;
        }

        // RAG validation: classification instructions MUST have a transcription example for vector embedding.
        const missingTranscription = validBlocks.some(b => !b.exemplo_transcricao.trim());
        if (form.tipo === 'classificacao' && missingTranscription) {
            setError('Para instruções de Classificação, o "Exemplo de transcrição" é obrigatório para a IA gerar o vetor de referência.');
            return;
        }

        setSaving(true);
        setError(null);
        try {
            if (editingId) {
                await apiFetchJson(`/api/ai-feedback/${editingId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tipo: form.tipo,
                        setor: form.setor || null,
                        criterio_id: form.criterio_id || null,
                        situacao: validBlocks[0].situacao,
                        correcao: validBlocks[0].correcao,
                        justificativa: validBlocks[0].justificativa,
                        exemplo_transcricao: validBlocks[0].exemplo_transcricao
                    }),
                });
            } else {
                await Promise.all(validBlocks.map(block =>
                    apiFetchJson('/api/ai-feedback', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            tipo: form.tipo,
                            setor: form.setor || null,
                            criterio_id: form.criterio_id || null,
                            situacao: block.situacao,
                            correcao: block.correcao,
                            justificativa: block.justificativa,
                            exemplo_transcricao: block.exemplo_transcricao
                        }),
                    })
                ));
            }
            setEditingId(null);
            setForm(EMPTY_FORM);
            setActiveTab('cadastradas');
            await fetchItems();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao salvar orientação');
        } finally {
            setSaving(false);
        }
    };

    const handleEdit = (item: Feedback) => {
        setForm({
            tipo: item.tipo,
            setor: item.setor || '',
            criterio_id: item.criterio_id || '',
            blocks: [{
                situacao: item.situacao,
                correcao: item.correcao,
                justificativa: item.justificativa,
                exemplo_transcricao: item.exemplo_transcricao || '',
            }]
        });
        setEditingId(item.id);
        setActiveTab('nova');
    };

    const handleToggle = async (id: number) => {
        try {
            await apiFetchJson(`/api/ai-feedback/${id}/toggle`, { method: 'PATCH' });
            await fetchItems();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao alternar status');
        }
    };

    const handleDelete = async (id: number) => {
        if (!confirm('Tem certeza que deseja excluir esta orientação?')) return;
        try {
            await apiFetchJson(`/api/ai-feedback/${id}`, { method: 'DELETE' });
            await fetchItems();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao excluir');
        }
    };

    const getTipoMeta = (tipo: string) => TIPO_OPTIONS.find(t => t.id === tipo) || TIPO_OPTIONS[0];

    const tabClass = (tab: TabId) =>
        `flex items-center gap-2 px-5 py-3 text-sm font-semibold rounded-xl transition-all duration-300 border ${activeTab === tab
            ? isDark
                ? 'bg-slate-800 text-primary-300 border-primary-500/35 shadow-[0_4px_16px_rgba(201,63,15,0.15)]'
                : 'bg-white text-primary-600 border-primary-500/25 shadow-md'
            : isDark
                ? 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/50'
                : 'text-gray-500 border-transparent hover:text-gray-800 hover:bg-slate-100'
        }`;

    return (
        <div>
            <div className="space-y-6 pb-10">
                <PageHeader
                    eyebrow="nstech | Inteligência Artificial"
                    titleFirstWord="Inteligência"
                    titleRest="Artificial"
                    subtitle="Oriente a IA com correções, exemplos e regras operacionais que serão usadas nas próximas classificações e auditorias."
                />

                <ModuleInstructions
                    storageKey="instructions:ai-feedback"
                    steps={[
                        'Registre correções, exemplos e regras para orientar a IA.',
                        'Defina a prioridade de cada orientação.',
                        'As regras valem para as próximas classificações e auditorias.',
                    ]}
                />

                <div className={`rounded-xl border p-4 ${isDark ? 'border-white/10 bg-slate-900/50' : 'border-slate-200 bg-white'}`}>
                    <div className="grid gap-3 md:grid-cols-3">
                        <div>
                            <div className={`text-[10px] font-bold uppercase tracking-[0.18em] ${labelClass}`}>Prioridade</div>
                            <p className={`mt-1 text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Critérios oficiais e pesos continuam mandando primeiro.</p>
                        </div>
                        <div>
                            <div className={`text-[10px] font-bold uppercase tracking-[0.18em] ${labelClass}`}>Como aprende</div>
                            <p className={`mt-1 text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Orientações ativas entram como referência no prompt/RAG da IA.</p>
                        </div>
                        <div>
                            <div className={`text-[10px] font-bold uppercase tracking-[0.18em] ${labelClass}`}>Controle</div>
                            <p className={`mt-1 text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>Cada orientação guarda autor, data, escopo e pode ser desativada.</p>
                        </div>
                    </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {TIPO_OPTIONS.map(tipo => {
                        const count = items.filter(i => i.tipo === tipo.id && i.ativo).length;
                        const Icon = tipo.icon;
                        return (
                            <div key={tipo.id} className={`glass-panel rounded-xl p-4 border ${tipo.bg}`}>
                                <div className="flex items-center gap-2 mb-1">
                                    <Icon size={16} className={tipo.color} />
                                    <span className={`text-xs font-semibold uppercase tracking-wider ${tipo.color}`}>{tipo.label}</span>
                                </div>
                                <span className={`text-2xl font-black ${tipo.color}`}>{count}</span>
                                <span className={`text-xs ml-1 ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>ativa(s)</span>
                            </div>
                        );
                    })}
                </div>

                {/* Tabs */}
                <div className="flex items-center gap-2">
                    <button onClick={() => { setActiveTab('nova'); setEditingId(null); setForm(EMPTY_FORM); }} className={tabClass('nova')}>
                        <Plus size={16} /> Orientar IA
                    </button>
                    <button onClick={() => setActiveTab('cadastradas')} className={tabClass('cadastradas')}>
                        <List size={16} /> Orientações ativas
                        {items.length > 0 && (
                            <span className={`ml-1 text-[11px] font-bold px-1.5 py-0.5 rounded-full ${isDark ? 'bg-white/10 text-slate-300' : 'bg-slate-200 text-gray-700'}`}>
                                {items.length}
                            </span>
                        )}
                    </button>
                </div>

                {error && (
                    <div className="glass-panel p-3 rounded-xl border border-red-500/25 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                        <span className="text-red-400 text-sm">{error}</span>
                        <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300"><X size={14} /></button>
                    </div>
                )}

                {/* Tab: Orientar IA */}
                {activeTab === 'nova' && (
                    <div className="glass-panel rounded-2xl border border-primary-500/20 p-6 space-y-4 animate-fade-in">
                        <h3 className="text-lg font-bold flex items-center gap-2">
                            <Brain size={20} className="text-primary-400" />
                            {editingId ? 'Editar orientação' : 'Nova orientação para a IA'}
                        </h3>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Tipo *</label>
                                <select
                                    value={form.tipo}
                                    onChange={e => setForm({ ...form, tipo: e.target.value })}
                                    className={`w-full text-sm rounded-lg border px-3 py-2.5 ${inputClass}`}
                                >
                                    {TIPO_OPTIONS.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Setor</label>
                                <select
                                    value={form.setor}
                                    onChange={e => setForm({ ...form, setor: e.target.value })}
                                    className={`w-full text-sm rounded-lg border px-3 py-2.5 ${inputClass}`}
                                >
                                    <option value="">Global (aplica a todos)</option>
                                    {SETOR_OPTIONS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Critério ID</label>
                                <input
                                    type="text"
                                    value={form.criterio_id}
                                    onChange={e => setForm({ ...form, criterio_id: e.target.value })}
                                    placeholder="ex: senha, identificacao"
                                    className={`w-full text-sm rounded-lg border px-3 py-2.5 ${inputClass}`}
                                />
                            </div>
                        </div>

                        <div className="space-y-6">
                            {form.blocks.map((block, index) => (
                                <div key={index} className={`p-4 rounded-xl border relative ${isDark ? 'bg-slate-900/50 border-white/5' : 'bg-slate-50 border-slate-200'}`}>
                                    {form.blocks.length > 1 && !editingId && (
                                        <button
                                            onClick={() => setForm(prev => ({ ...prev, blocks: prev.blocks.filter((_, i) => i !== index) }))}
                                            className="absolute top-3 right-3 p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-colors"
                                            title="Remover orientação"
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    )}
                                    <div className="mb-4">
                                        <h4 className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                            Orientação #{index + 1}
                                        </h4>
                                    </div>
                                    <div className="space-y-4">
                                        <div>
                                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Situação (o que aconteceu) *</label>
                                            <textarea
                                                value={block.situacao}
                                                onChange={e => {
                                                    setForm(prev => ({
                                                        ...prev,
                                                        blocks: prev.blocks.map((b, i) => i === index ? { ...b, situacao: e.target.value } : b)
                                                    }));
                                                }}
                                                placeholder="Descreva o que a IA fez de errado ou a situação que deve ser tratada..."
                                                rows={2}
                                                className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none focus:border-primary-500/50 focus:ring-2 focus:ring-primary-500/20 transition-all ${inputClass}`}
                                            />
                                        </div>

                                        <div>
                                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Correção (o que deveria ter feito) *</label>
                                            <textarea
                                                value={block.correcao}
                                                onChange={e => {
                                                    setForm(prev => ({
                                                        ...prev,
                                                        blocks: prev.blocks.map((b, i) => i === index ? { ...b, correcao: e.target.value } : b)
                                                    }));
                                                }}
                                                placeholder="O que a IA deveria ter feito corretamente..."
                                                rows={2}
                                                className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/20 transition-all ${inputClass}`}
                                            />
                                        </div>

                                        <div>
                                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Justificativa (por quê) *</label>
                                            <textarea
                                                value={block.justificativa}
                                                onChange={e => {
                                                    setForm(prev => ({
                                                        ...prev,
                                                        blocks: prev.blocks.map((b, i) => i === index ? { ...b, justificativa: e.target.value } : b)
                                                    }));
                                                }}
                                                placeholder="Explique por que a IA estava errada e por que a correção está certa..."
                                                rows={2}
                                                className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none focus:border-primary-500/50 focus:ring-2 focus:ring-primary-500/20 transition-all ${inputClass}`}
                                            />
                                        </div>

                                        <div>
                                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Exemplo de transcrição {form.tipo === 'classificacao' ? '*' : '(opcional)'}</label>
                                            <textarea
                                                value={block.exemplo_transcricao}
                                                onChange={e => {
                                                    setForm(prev => ({
                                                        ...prev,
                                                        blocks: prev.blocks.map((b, i) => i === index ? { ...b, exemplo_transcricao: e.target.value } : b)
                                                    }));
                                                }}
                                                placeholder="Cole um trecho de transcrição que exemplifica a situação..."
                                                rows={2}
                                                className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none font-mono ${inputClass}`}
                                            />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="flex items-center gap-3 pt-2">
                            <button
                                onClick={handleSubmit}
                                disabled={saving}
                                className="btn-primary px-6 py-2.5 text-sm font-semibold flex items-center gap-2"
                            >
                                <Check size={16} /> {saving ? 'Salvando...' : editingId ? 'Atualizar' : 'Salvar orientação'}
                            </button>
                            {editingId && (
                                <button
                                    onClick={() => { setEditingId(null); setForm(EMPTY_FORM); setError(null); }}
                                    className="btn-ghost px-4 py-2.5 text-sm"
                                >
                                    Cancelar edição
                                </button>
                            )}
                        </div>
                    </div>
                )}

                {/* Tab: Orientações ativas */}
                {activeTab === 'cadastradas' && (
                    <div className="space-y-4 animate-fade-in">
                        {/* Filters */}
                        <div className="flex items-center gap-2 flex-wrap">
                            <Filter size={14} className={isDark ? 'text-slate-500' : 'text-gray-500'} />
                            <select
                                value={filterTipo}
                                onChange={e => setFilterTipo(e.target.value)}
                                className={`text-xs rounded-lg border px-2.5 py-2 ${inputClass}`}
                            >
                                <option value="">Todos os tipos</option>
                                {TIPO_OPTIONS.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                            </select>
                            <select
                                value={filterSetor}
                                onChange={e => setFilterSetor(e.target.value)}
                                className={`text-xs rounded-lg border px-2.5 py-2 ${inputClass}`}
                            >
                                <option value="">Todos os setores</option>
                                {SETOR_OPTIONS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                            </select>
                        </div>

                        {loading ? (
                            <div className="glass-panel rounded-2xl p-8 text-center">
                                <span className={isDark ? 'text-slate-400' : 'text-gray-500'}>Carregando instruções...</span>
                            </div>
                        ) : items.length === 0 ? (
                            <div className="glass-panel rounded-2xl p-12 text-center">
                                <Brain size={48} className="mx-auto mb-4 text-primary-500/30" />
                                <p className={`text-lg font-semibold mb-2 ${isDark ? 'text-slate-300' : 'text-gray-700'}`}>
                                    Nenhuma orientação cadastrada
                                </p>
                                <p className={`text-sm ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>
                                    Crie orientações na aba "Orientar IA".
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-3 stagger-group">
                                {items.map(item => {
                                    const tipoMeta = getTipoMeta(item.tipo);
                                    const TipoIcon = tipoMeta.icon;
                                    const setorLabel = SETOR_OPTIONS.find(s => s.id === item.setor)?.label || 'Global';
                                    return (
                                        <div
                                            key={item.id}
                                            className={`stagger-item glass-panel rounded-xl border p-4 transition-all duration-300 ${cardClass} ${!item.ativo ? 'opacity-50' : ''}`}
                                        >
                                            <div className="flex items-start gap-3">
                                                <div className={`mt-0.5 p-1.5 rounded-lg ${tipoMeta.bg}`}>
                                                    <TipoIcon size={16} className={tipoMeta.color} />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 flex-wrap mb-1">
                                                        <span className={`text-xs font-bold uppercase tracking-wide ${tipoMeta.color}`}>{tipoMeta.label}</span>
                                                        <span className={`text-xs px-2 py-0.5 rounded-full border ${isDark ? 'border-white/10 text-slate-400' : 'border-slate-200 text-gray-600'}`}>
                                                            {setorLabel}
                                                        </span>
                                                        {item.criterio_id && (
                                                            <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${isDark ? 'bg-slate-700/50 text-slate-400' : 'bg-slate-100 text-gray-600'}`}>
                                                                {item.criterio_id}
                                                            </span>
                                                        )}
                                                        {!item.ativo && (
                                                            <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/20">
                                                                Desativada
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div className="space-y-1.5 mt-2">
                                                        <div>
                                                            <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>Situação</span>
                                                            <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-gray-700'}`}>{item.situacao}</p>
                                                        </div>
                                                        <div>
                                                            <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-emerald-500' : 'text-emerald-700'}`}>Correção</span>
                                                            <p className={`text-sm ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>{item.correcao}</p>
                                                        </div>
                                                        <div>
                                                            <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>Justificativa</span>
                                                            <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-gray-600'}`}>{item.justificativa}</p>
                                                        </div>
                                                        {item.exemplo_transcricao && (
                                                            <div>
                                                                <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>Exemplo</span>
                                                                <p className={`text-xs font-mono p-2 rounded-lg mt-0.5 ${isDark ? 'bg-slate-900/60 text-slate-400' : 'bg-slate-100 text-gray-600'}`}>
                                                                    {item.exemplo_transcricao}
                                                                </p>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className={`mt-3 text-[11px] ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>
                                                        por <strong>{item.criado_por}</strong> em {new Date(item.criado_em).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })}
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1 shrink-0">
                                                    <button
                                                        onClick={() => handleToggle(item.id)}
                                                        className="btn-icon"
                                                        title={item.ativo ? 'Desativar' : 'Ativar'}
                                                    >
                                                        {item.ativo ? <ToggleRight size={18} className="text-emerald-400" /> : <ToggleLeft size={18} className="text-slate-500" />}
                                                    </button>
                                                    <button onClick={() => handleEdit(item)} className="btn-icon" title="Editar">
                                                        <Pencil size={14} />
                                                    </button>
                                                    <button onClick={() => handleDelete(item.id)} className="btn-icon-danger" title="Excluir">
                                                        <Trash2 size={14} />
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

