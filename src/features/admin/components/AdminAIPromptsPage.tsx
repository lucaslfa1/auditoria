/**
 * Tela de admin dos PROMPTS da IA (externalizados, editáveis sem novo deploy).
 *
 * Lista/edita prompts via `/api/admin/ai-prompts` (GET; PUT `/{chave}`) e limpa o
 * cache em `/api/admin/ai-prompts/cache/invalidate`. Os prompts alimentam a
 * classificação/avaliação; o custo de IA NÃO ocorre aqui — só quando uma
 * auditoria roda depois usando o prompt salvo.
 */
import { useEffect, useState } from 'react';
import { Loader2, Pencil, RefreshCw } from 'lucide-react';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';

export function AdminAIPromptsPage() {
    const { showToast } = useToast();
    const [prompts, setPrompts] = useState<{ chave: string; valor: string }[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [formOpen, setFormOpen] = useState(false);
    const [editingChave, setEditingChave] = useState<string>('');
    const [editValor, setEditValor] = useState('');
    const [editMotivo, setEditMotivo] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const flattenObject = (ob: any, prefix = ''): { chave: string, valor: string }[] => {
        let result: { chave: string, valor: string }[] = [];
        for (const i in ob) {
            if (!ob.hasOwnProperty(i)) continue;
            if ((typeof ob[i]) === 'object' && ob[i] !== null && !Array.isArray(ob[i])) {
                result = result.concat(flattenObject(ob[i], prefix + i + '.'));
            } else {
                result.push({ chave: prefix + i, valor: String(ob[i]) });
            }
        }
        return result;
    };

    const fetchData = async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            setError(null);
            const data = await apiFetchJson<any>('/api/admin/ai-prompts');
            const flat = flattenObject(data);
            setPrompts(flat.sort((a, b) => a.chave.localeCompare(b.chave)));
        } catch (err: any) {
            setError(err.message || 'Erro ao carregar prompts');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleInvalidateCache = async () => {
        try {
            await apiFetchJson('/api/admin/ai-prompts/cache/invalidate', { method: 'POST' });
            showToast({ variant: 'success', title: 'Cache invalidado', description: 'O cache de prompts de IA foi limpo com sucesso.' });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro ao invalidar cache', description: err.message });
        }
    };

    const handleSave = async () => {
        if (!editMotivo.trim()) {
            showToast({ variant: 'error', title: 'Motivo obrigatório', description: 'Descreva o motivo da alteração.' });
            return;
        }

        try {
            setSubmitting(true);
            await apiFetchJson(`/api/admin/ai-prompts/${encodeURIComponent(editingChave)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ valor: editValor, motivo: editMotivo })
            });
            setFormOpen(false);
            await fetchData(true);
            showToast({ variant: 'success', title: 'Sucesso', description: 'Prompt atualizado.' });
        } catch (err: any) {
            showToast({ variant: 'error', title: 'Erro', description: err.message });
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return <div className="p-10 flex justify-center"><Loader2 className="animate-spin text-primary-500 w-8 h-8" /></div>
    }

    return (
        <div className="space-y-6 pb-10">
            <PageHeader
                eyebrow="nstech | Administração"
                titleFirstWord="Prompts"
                titleRest="de IA"
                subtitle="Edite as instruções e vocabulários base que a inteligência artificial usa para analisar as ligações."
            />

            <ModuleInstructions
                storageKey="instructions:prompts"
                steps={[
                    'Edite os prompts e vocabulários que a IA usa nas análises.',
                    'Ajuste com cuidado — afeta transcrição e auditoria.',
                    'Invalide o cache para aplicar as mudanças.',
                ]}
            />
            {error && <div className="text-red-400 p-4 rounded bg-red-500/10 border border-red-500/20">{error}</div>}

            <div className="flex justify-end mb-4">
                <button onClick={handleInvalidateCache} className="btn-ghost text-sm px-4 py-2 flex items-center gap-2 text-slate-300 hover:text-white">
                    <RefreshCw size={16} /> Invalidar Cache
                </button>
            </div>

            <div className="bg-slate-800/40 border border-white/10 rounded-xl overflow-hidden shadow-sm">
                {prompts.length === 0 ? (
                    <div className="p-6 text-center text-slate-400">Nenhum prompt encontrado.</div>
                ) : (
                    <table className="w-full text-left text-sm text-slate-300">
                        <thead className="bg-slate-900/50 border-b border-white/10 text-slate-400 text-xs uppercase">
                            <tr>
                                <th className="px-4 py-3 font-medium w-1/3">Chave</th>
                                <th className="px-4 py-3 font-medium w-7/12">Valor Atual</th>
                                <th className="px-4 py-3 font-medium w-1/12 text-right">Ações</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {prompts.map(prompt => (
                                <tr key={prompt.chave} className="hover:bg-slate-800/40 transition-colors">
                                    <td className="px-4 py-3 font-mono text-xs text-primary-300 break-all align-top">{prompt.chave}</td>
                                    <td className="px-4 py-3">
                                        <div className="line-clamp-3 text-xs bg-slate-900/50 p-2 rounded border border-white/5 whitespace-pre-wrap font-mono">
                                            {prompt.valor}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 flex items-center justify-end align-top">
                                        <button onClick={() => {
                                            setEditingChave(prompt.chave);
                                            setEditValor(prompt.valor);
                                            setEditMotivo('');
                                            setFormOpen(true);
                                        }} className="p-2 text-slate-400 hover:text-primary-300 hover:bg-white/5 rounded-lg transition-colors"><Pencil size={16} /></button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {formOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className="w-full max-w-4xl bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl flex flex-col max-h-[90vh]">
                        <h3 className="text-lg font-semibold text-white mb-2">Editar Prompt</h3>
                        <p className="text-sm font-mono text-primary-300 mb-4 bg-slate-800/50 p-2 rounded">{editingChave}</p>
                        
                        <div className="space-y-4 flex-1 flex flex-col overflow-hidden min-h-0">
                            <label className="flex-1 flex flex-col min-h-0">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Valor do Prompt *</span>
                                <textarea 
                                    value={editValor} 
                                    onChange={e => setEditValor(e.target.value)} 
                                    className="flex-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 font-mono resize-none" 
                                />
                            </label>
                            <label className="block shrink-0">
                                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Motivo da Alteração *</span>
                                <textarea 
                                    value={editMotivo} 
                                    onChange={e => setEditMotivo(e.target.value)} 
                                    className="mt-1 w-full bg-slate-800 border border-white/10 rounded-xl p-3 text-sm text-slate-200 outline-none focus:border-primary-500/50 resize-y" 
                                    rows={2} 
                                    placeholder="Obrigatório para registro em auditoria"
                                />
                            </label>
                        </div>
                        <div className="mt-6 flex justify-end gap-3 shrink-0">
                            <button onClick={() => setFormOpen(false)} className="btn-ghost px-4 py-2 text-sm font-semibold">Cancelar</button>
                            <button disabled={submitting} onClick={handleSave} className="btn-primary px-4 py-2 text-sm font-semibold disabled:opacity-50">{submitting ? 'Salvando...' : 'Salvar'}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}