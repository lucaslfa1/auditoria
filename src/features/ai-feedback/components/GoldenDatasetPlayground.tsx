import { useState, useEffect, useCallback } from 'react';
import {
    FlaskConical, Plus, Trash2, X,
    AlertCircle, DownloadCloud, Database, Code, CheckCircle2
} from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';

interface GoldenExample {
    id: string;
    filename: string;
    audit_id: number | null;
    cenario: string;
    categoria: string;
    created_at: number;
}

export function GoldenDatasetPlayground({ isDark }: { isDark: boolean }) {
    const [items, setItems] = useState<GoldenExample[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Modal Form State
    const [isFormOpen, setIsFormOpen] = useState(false);
    const [auditIdInput, setAuditIdInput] = useState('');
    const [importing, setImporting] = useState(false);
    
    const [formData, setFormData] = useState({
        audit_id: null as number | null,
        categoria: 'boa',
        cenario: '',
        transcricao_resumida: [] as string[],
        gabarito_avaliacao: {} as Record<string, any>
    });

    const cardClass = isDark
        ? 'bg-slate-800/50 border-white/10 hover:bg-slate-800'
        : 'bg-white border-slate-200 hover:bg-slate-50';
    const inputClass = isDark
        ? 'bg-slate-800 border-white/15 text-slate-200 placeholder-slate-500'
        : 'bg-white border-slate-300 text-gray-800 placeholder-gray-400';
    const labelClass = isDark ? 'text-slate-400' : 'text-gray-600';

    const fetchItems = useCallback(async () => {
        try {
            setLoading(true);
            const data = await apiFetchJson<GoldenExample[]>('/api/golden-dataset');
            setItems(data);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao carregar exemplos do Golden Dataset');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchItems(); }, [fetchItems]);

    const handleImportAudit = async () => {
        if (!auditIdInput.trim()) return;
        setImporting(true);
        setError(null);
        try {
            const data = await apiFetchJson<any>(`/api/golden-dataset/${auditIdInput}/extract`);
            setFormData({
                audit_id: data.audit_id,
                categoria: 'boa',
                cenario: `Auditoria ${data.audit_id} - ${data.alert_label}`,
                transcricao_resumida: data.transcricao_resumida || [],
                gabarito_avaliacao: data.gabarito_avaliacao || {}
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao importar auditoria');
        } finally {
            setImporting(false);
        }
    };

    const handleSave = async () => {
        if (!formData.cenario.trim()) {
            setError('O cenário é obrigatório.');
            return;
        }

        setImporting(true);
        try {
            await apiFetchJson('/api/golden-dataset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });
            setIsFormOpen(false);
            setFormData({
                audit_id: null,
                categoria: 'boa',
                cenario: '',
                transcricao_resumida: [],
                gabarito_avaliacao: {}
            });
            setAuditIdInput('');
            await fetchItems();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao salvar exemplo');
        } finally {
            setImporting(false);
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Excluir este exemplo de treinamento?')) return;
        try {
            await apiFetchJson(`/api/golden-dataset/${id}`, { method: 'DELETE' });
            await fetchItems();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao excluir');
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className={`text-lg font-bold flex items-center gap-2 ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                        <Database className="text-primary-500" size={20} />
                        Exemplos de Treinamento
                    </h3>
                    <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                        Forneça exemplos de ligações para ensinar a IA.
                    </p>
                </div>
                <button
                    onClick={() => setIsFormOpen(true)}
                    className="btn-primary px-4 py-2 text-sm flex items-center gap-2"
                >
                    <Plus size={16} /> Novo Exemplo
                </button>
            </div>

            {error && !isFormOpen && (
                <div className="glass-panel p-3 rounded-xl border border-red-500/25 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                    <span className="text-red-400 text-sm">{error}</span>
                    <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300"><X size={14} /></button>
                </div>
            )}

            {isFormOpen && (
                <div className="glass-panel rounded-2xl border border-primary-500/20 p-6 space-y-6 animate-fade-in relative">
                    <button onClick={() => setIsFormOpen(false)} className="absolute top-4 right-4 text-slate-400 hover:text-slate-200">
                        <X size={20} />
                    </button>
                    
                    <h4 className="text-md font-bold flex items-center gap-2">
                        <FlaskConical size={18} className="text-primary-400" />
                        Novo Exemplo de Treinamento
                    </h4>

                    {error && (
                        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                            {error}
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Passo 1: Importação */}
                        <div className={`p-4 rounded-xl border ${isDark ? 'bg-slate-900/50 border-white/5' : 'bg-slate-50 border-slate-200'}`}>
                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-2 ${labelClass}`}>
                                Importar de Auditoria (Opcional)
                            </label>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={auditIdInput}
                                    onChange={e => setAuditIdInput(e.target.value)}
                                    placeholder="ID da Auditoria (ex: 483)"
                                    className={`flex-1 text-sm rounded-lg border px-3 py-2 ${inputClass}`}
                                />
                                <button
                                    onClick={handleImportAudit}
                                    disabled={importing || !auditIdInput.trim()}
                                    className="btn-ghost px-3 py-2 flex items-center gap-2"
                                >
                                    <DownloadCloud size={16} /> Importar
                                </button>
                            </div>
                        </div>

                        {/* Passo 2: Categoria */}
                        <div className={`p-4 rounded-xl border ${isDark ? 'bg-slate-900/50 border-white/5' : 'bg-slate-50 border-slate-200'}`}>
                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-2 ${labelClass}`}>
                                Categoria do Exemplo
                            </label>
                            <div className="flex gap-3">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input 
                                        type="radio" 
                                        name="categoria" 
                                        value="boa" 
                                        checked={formData.categoria === 'boa'}
                                        onChange={e => setFormData({...formData, categoria: e.target.value})}
                                        className="text-emerald-500 focus:ring-emerald-500"
                                    />
                                    <span className={`text-sm font-medium ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>Exemplo de Boa Avaliação</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input 
                                        type="radio" 
                                        name="categoria" 
                                        value="ruim" 
                                        checked={formData.categoria === 'ruim'}
                                        onChange={e => setFormData({...formData, categoria: e.target.value})}
                                        className="text-red-500 focus:ring-red-500"
                                    />
                                    <span className={`text-sm font-medium ${isDark ? 'text-red-400' : 'text-red-600'}`}>Falha (Como NÃO avaliar)</span>
                                </label>
                            </div>
                        </div>
                    </div>

                    {/* Passo 3: Configuração */}
                    <div className="space-y-4">
                        <div>
                            <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Cenário (Contexto da Regra)</label>
                            <input
                                type="text"
                                value={formData.cenario}
                                onChange={e => setFormData({...formData, cenario: e.target.value})}
                                placeholder="ex: Ligação receptiva de setor de risco que não deve ser auditada..."
                                className={`w-full text-sm rounded-lg border px-3 py-2.5 ${inputClass}`}
                            />
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            <div>
                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Transcrição Resumida</label>
                                <textarea
                                    value={formData.transcricao_resumida.join('\n')}
                                    onChange={e => setFormData({...formData, transcricao_resumida: e.target.value.split('\n')})}
                                    rows={8}
                                    placeholder="Operador: Alô...&#10;Motorista: Oi..."
                                    className={`w-full text-sm rounded-lg border px-3 py-2.5 font-mono text-xs ${inputClass}`}
                                />
                                <p className={`text-[10px] mt-1 ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>Apague os trechos irrelevantes para focar só no que importa.</p>
                            </div>
                            
                            <div>
                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Gabarito Esperado (JSON)</label>
                                <textarea
                                    value={JSON.stringify(formData.gabarito_avaliacao, null, 2)}
                                    onChange={e => {
                                        try {
                                            const parsed = JSON.parse(e.target.value);
                                            setFormData({...formData, gabarito_avaliacao: parsed});
                                        } catch (_) {
                                            // Let them type invalid JSON temporarily, but maybe show a subtle warning
                                        }
                                    }}
                                    rows={8}
                                    placeholder='{\n  "criterio_senha": "pass",\n  "justificativa_ia": "Atende pelo princípio de benevolência..."\n}'
                                    className={`w-full text-sm rounded-lg border px-3 py-2.5 font-mono text-xs ${inputClass}`}
                                />
                            </div>
                        </div>
                    </div>

                    <div className="flex justify-end pt-4 border-t border-white/10">
                        <button
                            onClick={handleSave}
                            disabled={importing}
                            className="btn-primary px-6 py-2.5 text-sm font-semibold flex items-center gap-2"
                        >
                            <CheckCircle2 size={16} /> {importing ? 'Salvando...' : 'Salvar no Treinamento'}
                        </button>
                    </div>
                </div>
            )}

            {/* List */}
            {loading ? (
                <div className="glass-panel rounded-2xl p-8 text-center">
                    <span className={isDark ? 'text-slate-400' : 'text-gray-500'}>Carregando exemplos de treinamento...</span>
                </div>
            ) : items.length === 0 && !isFormOpen ? (
                <div className="glass-panel rounded-2xl p-12 text-center">
                    <Database size={48} className="mx-auto mb-4 text-primary-500/30" />
                    <p className={`text-lg font-semibold mb-2 ${isDark ? 'text-slate-300' : 'text-gray-700'}`}>
                        Nenhum exemplo de treinamento cadastrado
                    </p>
                    <p className={`text-sm max-w-md mx-auto ${isDark ? 'text-slate-500' : 'text-gray-500'}`}>
                        Adicione exemplos de auditorias para treinar o modelo de inteligência artificial.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 stagger-group">
                    {items.map(item => (
                        <div key={item.id} className={`stagger-item glass-panel rounded-xl border p-4 transition-all duration-300 ${cardClass}`}>
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-2">
                                    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                                        item.categoria === 'boa' 
                                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                                        : 'bg-red-500/10 text-red-400 border-red-500/20'
                                    }`}>
                                        {item.categoria === 'boa' ? 'Boa Avaliação' : 'Avaliação Ruim'}
                                    </span>
                                    {item.audit_id && (
                                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${isDark ? 'bg-slate-700/50 text-slate-400' : 'bg-slate-100 text-gray-600'}`}>
                                            ID: {item.audit_id}
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-1">
                                    <button onClick={() => handleDelete(item.id)} className="btn-icon-danger p-1" title="Excluir">
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            </div>
                            
                            <h4 className={`text-sm font-semibold mb-2 ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                                {item.cenario}
                            </h4>
                            
                            <div className={`mt-3 text-[10px] ${isDark ? 'text-slate-500' : 'text-gray-500'} flex items-center justify-between`}>
                                <span className="flex items-center gap-1">
                                    <Code size={12} /> {item.filename}
                                </span>
                                <span>{new Date(item.created_at * 1000).toLocaleDateString('pt-BR')}</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
