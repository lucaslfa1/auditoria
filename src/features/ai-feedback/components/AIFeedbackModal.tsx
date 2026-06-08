import { useState, useEffect } from 'react';
import { Brain, Check, X, Plus, AlertCircle } from 'lucide-react';
import { apiFetchJson } from '../../../shared/lib/apiClient';

interface AIFeedbackModalProps {
    isOpen: boolean;
    onClose: () => void;
    initialType?: string;
    initialSector?: string;
    initialCriterionId?: string;
    situacaoContext?: string;
    correcaoContext?: string;
    transcriptionContext?: string;
    theme?: 'dark' | 'light';
}

export function AIFeedbackModal({
    isOpen,
    onClose,
    initialType = 'classificacao',
    initialSector = '',
    initialCriterionId = '',
    situacaoContext = '',
    correcaoContext = '',
    transcriptionContext = '',
    theme = 'dark'
}: AIFeedbackModalProps) {
    const [blocks, setBlocks] = useState([{
        situacao: situacaoContext,
        correcao: correcaoContext,
        justificativa: ''
    }]);

    const tipo = initialType;
    const setor = initialSector;
    const criterioId = initialCriterionId;
    const exemplo = transcriptionContext;
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen) {
            setBlocks([{ situacao: situacaoContext, correcao: correcaoContext, justificativa: '' }]);
            setError(null);
            setSaving(false);
        }
    }, [isOpen, situacaoContext, correcaoContext]);

    if (!isOpen) return null;

    const isDark = theme === 'dark';
    const inputClass = isDark
        ? 'bg-slate-800 border-white/15 text-slate-200 placeholder-slate-500'
        : 'bg-white border-slate-300 text-gray-800 placeholder-gray-400';
    const labelClass = isDark ? 'text-slate-400' : 'text-gray-600';

    const handleSubmit = async () => {
        const hasPartial = blocks.some(b =>
            (b.situacao.trim() || b.correcao.trim() || b.justificativa.trim()) &&
            !(b.situacao.trim() && b.correcao.trim() && b.justificativa.trim())
        );
        if (hasPartial) {
            setError('Preencha Situação, Correção e Justificativa para todos os blocos adicionados.');
            return;
        }

        const validBlocks = blocks.filter(b => b.situacao.trim() && b.correcao.trim() && b.justificativa.trim());
        if (validBlocks.length === 0) {
            setError('Situação, Correção e Justificativa são obrigatórios em pelo menos um bloco.');
            return;
        }

        setSaving(true);
        setError(null);
        try {
            const failedBlocks: typeof validBlocks = [];
            for (const block of validBlocks) {
                try {
                    await apiFetchJson('/api/ai-feedback', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            tipo,
                            setor,
                            criterio_id: criterioId,
                            situacao: block.situacao,
                            correcao: block.correcao,
                            justificativa: block.justificativa,
                            exemplo_transcricao: exemplo
                        }),
                    });
                    // Sucesso: remover do estado imediatamente
                    setBlocks(prev => prev.filter(b => b !== block));
                } catch {
                    failedBlocks.push(block);
                }
            }
            if (failedBlocks.length > 0) {
                setError(`${failedBlocks.length} instrução(ões) falharam. Tente novamente.`);
            } else {
                onClose();
            }
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
            <div className={`w-full max-w-2xl rounded-2xl shadow-xl overflow-hidden flex flex-col max-h-[90vh] ${isDark ? 'bg-slate-900 border border-white/10' : 'bg-white border border-slate-200'}`}>
                {/* Header */}
                <div className={`px-6 py-4 flex items-center justify-between border-b ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-xl ${isDark ? 'bg-primary-500/20 text-primary-400' : 'bg-primary-50 text-primary-600'}`}>
                            <Brain size={20} />
                        </div>
                        <div>
                            <h2 className={`font-bold ${isDark ? 'text-white' : 'text-slate-800'}`}>Ensinar IA com esta correção</h2>
                            <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>A correção já foi registrada; use esta conversa para deixar a orientação mais clara.</p>
                        </div>
                    </div>
                    <button onClick={onClose} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-slate-800 text-slate-400' : 'hover:bg-slate-100 text-slate-500'}`}>
                        <X size={20} />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 overflow-y-auto space-y-4">
                    {error && (
                        <div className="p-3 rounded-xl border border-red-500/25 flex items-center gap-2 bg-red-500/10">
                            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                            <span className="text-red-400 text-sm">{error}</span>
                        </div>
                    )}

                    <div className={`rounded-xl border p-4 ${isDark ? 'border-primary-500/25 bg-primary-500/10' : 'border-primary-200 bg-primary-50'}`}>
                        <div className="flex items-start gap-3">
                            <div className={`mt-0.5 rounded-lg p-2 ${isDark ? 'bg-primary-500/15 text-primary-300' : 'bg-white text-primary-600'}`}>
                                <Brain size={18} />
                            </div>
                            <div className="space-y-2">
                                <p className={`text-sm font-semibold ${isDark ? 'text-slate-100' : 'text-slate-800'}`}>Me ajude a entender a regra por trás dessa correção.</p>
                                <ul className={`space-y-1 text-xs ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                                    <li>Qual foi o principal sinal na ligação que levou à correção?</li>
                                    <li>Essa orientação vale só para este caso ou para casos parecidos?</li>
                                    <li>Existe algum critério oficial que limita quando devo aplicar isso?</li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-6">
                        {blocks.map((block, index) => (
                            <div key={index} className={`p-4 rounded-xl border relative ${isDark ? 'bg-slate-900/50 border-white/5' : 'bg-slate-50 border-slate-200'}`}>
                                {blocks.length > 1 && (
                                    <button
                                        onClick={() => setBlocks(prev => prev.filter((_, i) => i !== index))}
                                        className="absolute top-3 right-3 p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-colors"
                                        title="Remover instrução"
                                    >
                                        <X size={16} />
                                    </button>
                                )}
                                <div className="mb-4">
                                    <h4 className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                                        Instrução #{index + 1}
                                    </h4>
                                </div>
                                <div className="space-y-4">
                                    <div>
                                        <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>O que aconteceu *</label>
                                        <textarea
                                            value={block.situacao}
                                            onChange={e => {
                                                setBlocks(prev => prev.map((b, i) => i === index ? { ...b, situacao: e.target.value } : b));
                                            }}
                                            placeholder="Ex: A IA classificou como X mas era Y..."
                                            rows={2}
                                            className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none focus:border-primary-500/50 focus:ring-2 focus:ring-primary-500/20 transition-all ${inputClass}`}
                                        />
                                    </div>
                                    <div>
                                        <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Como a IA deve agir *</label>
                                        <textarea
                                            value={block.correcao}
                                            onChange={e => {
                                                setBlocks(prev => prev.map((b, i) => i === index ? { ...b, correcao: e.target.value } : b));
                                            }}
                                            placeholder="Ex: Deveria ter classificado como Y porque..."
                                            rows={2}
                                            className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/20 transition-all ${inputClass}`}
                                        />
                                    </div>
                                    <div>
                                        <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Resposta do auditor *</label>
                                        <textarea
                                            value={block.justificativa}
                                            onChange={e => {
                                                setBlocks(prev => prev.map((b, i) => i === index ? { ...b, justificativa: e.target.value } : b));
                                            }}
                                            placeholder="Explique o motivo da correção, quando aplicar e quando não aplicar."
                                            rows={2}
                                            className={`w-full text-sm rounded-lg border px-3 py-2.5 resize-none focus:border-primary-500/50 focus:ring-2 focus:ring-primary-500/20 transition-all ${inputClass}`}
                                        />
                                    </div>
                                </div>
                            </div>
                        ))}

                        <button
                            onClick={() => setBlocks(prev => [...prev, { situacao: '', correcao: '', justificativa: '' }])}
                            className={`w-full py-3 rounded-xl flex border border-dashed items-center justify-center gap-2 text-sm font-medium transition-colors cursor-pointer ${isDark
                                ? 'border-white/20 text-slate-300 hover:bg-white/5 hover:border-white/30'
                                : 'border-slate-300 text-slate-600 hover:bg-slate-50 hover:border-slate-400'
                                }`}
                        >
                            <Plus size={16} /> Adicionar mais uma instrução
                        </button>
                        {exemplo && (
                            <div>
                                <label className={`block text-[10px] uppercase tracking-wider font-semibold mb-1.5 ${labelClass}`}>Contexto / Transcrição</label>
                                <div className={`p-3 rounded-lg text-xs font-mono max-h-32 overflow-y-auto ${isDark ? 'bg-slate-950 text-slate-400' : 'bg-slate-50 text-slate-600'}`}>
                                    {exemplo}
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className={`px-6 py-4 flex items-center justify-end gap-3 border-t ${isDark ? 'border-white/10 bg-slate-900/50' : 'border-slate-200 bg-slate-50'}`}>
                    <button
                        onClick={onClose}
                        className="btn-ghost px-4 py-2 text-sm font-medium"
                        disabled={saving}
                    >
                        Cancelar
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={saving}
                        className="btn-primary px-6 py-2 text-sm font-semibold flex items-center gap-2"
                    >
                        <Check size={16} />
                        {saving ? 'Enviando...' : 'Salvar Instrução'}
                    </button>
                </div>
            </div>
        </div>
    );
}
