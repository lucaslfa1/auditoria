/**
 * Tela do FECHAMENTO mensal — consolida as auditorias aprovadas para o BI.
 *
 * Carrega dados via `/api/fechamento/dados` e `/api/fechamento/supervisores`,
 * resolve operadores em `/api/operadores/`, gerencia o layout/seleção de
 * operadores (`/api/fechamento/layout/operadores` [+ `/remover`]) e exporta em
 * `/api/fechamento/exportar`. ATENÇÃO: o formato/labels do fechamento são
 * CONTRATO com o BI — não alterar (ver memória "Fechamento intocável").
 */
import { useState, useEffect, useMemo } from 'react';
import { Download, Save, RefreshCw, Trash2, UserPlus } from 'lucide-react';
import { ApiError, apiFetchJson, apiFetchBlob } from '../../../shared/lib/apiClient';
import { useToast } from '../../../shared/components/ToastProvider';
import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';

interface FechamentoRow {
  layout_id?: number | null;
  colab_id: number;
  id: number;
  mes_str: string;
  matricula: string;
  nome: string;
  operacional: string;
  telefonica: string;
  desempenho: string;
  status: string;
  turno: string;
  supervisor: string;
  setor: string;
  nota_mot: number;
  nota_pa: number;
  nota_cli: number;
  nota_policia: number;
  processo: string;
  final: string;
  huawei: string;
  weon: string;
}

interface OperadorDisponivel {
  id: number;
  nome: string;
  matricula: string | null;
  supervisor: string | null;
  setor: string | null;
  escala: string | null;
}

const OPERACAO_OPCOES = [
  'CADASTRO', 'CHECKLIST', 'DISTRIBUIÇÃO', 'FÊNIX',
  'UTI - COMBO - Alternativo', 'UTI - Amarela - BBM', 'BAS - AZUL ', 'UTI - CINZA',
  'UTI - CINZA - BBM', 'UTI - VERDE', 'LOGÍSTICA', 'MONDELEZ', 'UNILEVER',
  'CENTRAL - AMARELA', 'CENTRAL - AZUL', 'CENTRAL - CINZA', 'CENTRAL - VERDE',
];

const SETOR_OPCOES = [
  'CADASTRO', 'CHECKLIST', 'DISTRIBUIÇÃO', 'TRANSFERÊNCIA', 'UTI', 'BAS', 'LOGÍSTICA',
];

function stripAccents(value: string): string {
  return (value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function isUtiRj(setor: string, turno: string): boolean {
  const text = ` ${stripAccents(setor)} ${stripAccents(turno)} `;
  return / rj |[-/]rj|rj[-/]/.test(text);
}

function isUti(setor: string, turno: string): boolean {
  const text = `${stripAccents(setor)} ${stripAccents(turno)}`;
  return text.includes('uti');
}

type NotaField = 'mot' | 'pa' | 'cli' | 'pol';
type NotaRowField = 'nota_mot' | 'nota_pa' | 'nota_cli' | 'nota_policia';

function maxNotaFor(setor: string, turno: string, field: NotaField): number {
  if (isUtiRj(setor, turno)) {
    return field === 'pa' ? 1 : 1.5;
  }
  if (!isUti(setor, turno)) return 0;
  return 1;
}

function rowFieldFor(field: NotaField): NotaRowField {
  if (field === 'mot') return 'nota_mot';
  if (field === 'pa') return 'nota_pa';
  if (field === 'cli') return 'nota_cli';
  return 'nota_policia';
}

function isCadeiaApplicable(row: FechamentoRow): boolean {
  return isUtiRj(row.setor, row.turno) || isUti(row.setor, row.turno);
}

function isOperadorRj(op: OperadorDisponivel): boolean {
  return isUtiRj(op.setor ?? '', op.escala ?? '');
}

function processoPercentForSum(sum: number): number {
  const rounded = Math.round(sum * 100) / 100;
  if (rounded >= 4) return 110;
  if (rounded === 3) return 100;
  if (rounded === 2 || rounded === 2.5) return 90;
  if (rounded === 1) return 80;
  return 70;
}

function finalForProcess(status: string, processoPercent: number): string {
  if ((status || '').toUpperCase() === 'INATIVO') return 'Adeus';
  if (processoPercent === 70) return '-4%';
  if (processoPercent > 80 && processoPercent < 100) return '-2%';
  if (processoPercent === 100) return '2%';
  if (processoPercent > 100) return '4%';
  return '';
}

function cadeiaSum(row: FechamentoRow): number {
  return Number(row.nota_mot || 0) + Number(row.nota_pa || 0) + Number(row.nota_cli || 0) + Number(row.nota_policia || 0);
}

export default function FechamentoPage() {
  const [mes, setMes] = useState<number>(new Date().getMonth() + 1);
  const [ano, setAno] = useState<number>(new Date().getFullYear());
  const [rows, setRows] = useState<FechamentoRow[]>([]);
  const [supervisores, setSupervisores] = useState<string[]>([]);
  const [selectedCalculoIndex, setSelectedCalculoIndex] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [showAddOperador, setShowAddOperador] = useState(false);
  const [operadoresDisponiveis, setOperadoresDisponiveis] = useState<OperadorDisponivel[]>([]);
  const [buscaOperador, setBuscaOperador] = useState('');
  const [addingOperadorId, setAddingOperadorId] = useState<number | null>(null);
  const [removingRowKey, setRemovingRowKey] = useState<string | null>(null);
  const { showToast } = useToast();

  const describeRequestError = (error: unknown, fallback: string) => {
    if (error instanceof ApiError && error.message) {
      return error.message;
    }
    return fallback;
  };

  const fetchDados = async () => {
    setIsLoading(true);
    try {
      const data = await apiFetchJson<FechamentoRow[]>(`/api/fechamento/dados?mes=${mes}&ano=${ano}`);
      setRows(data);
    } catch (error) {
      showToast({
        title: 'Erro ao carregar dados do fechamento',
        description: describeRequestError(error, 'Tente novamente em alguns instantes.'),
        variant: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSupervisores = async () => {
    try {
      const data = await apiFetchJson<string[]>('/api/fechamento/supervisores');
      setSupervisores(Array.isArray(data) ? data.filter(Boolean) : []);
    } catch (error) {
      showToast({
        title: 'Erro ao carregar supervisores',
        description: describeRequestError(error, 'A lista de supervisores não foi carregada.'),
        variant: 'error',
      });
    }
  };

  useEffect(() => {
    fetchDados();
  }, [mes, ano]);

  useEffect(() => {
    fetchSupervisores();
  }, []);

  useEffect(() => {
    if (rows.length === 0) {
      setSelectedCalculoIndex(null);
      return;
    }

    setSelectedCalculoIndex(prev => {
      if (prev !== null && rows[prev] && isCadeiaApplicable(rows[prev])) {
        return prev;
      }

      const firstApplicable = rows.findIndex(isCadeiaApplicable);
      return firstApplicable >= 0 ? firstApplicable : null;
    });
  }, [rows]);

  const handleCellChange = (rowIndex: number, field: keyof FechamentoRow, value: string | number) => {
    setRows(prev => {
      const newRows = [...prev];
      newRows[rowIndex] = { ...newRows[rowIndex], [field]: value };
      return newRows;
    });
  };

  const handleNotaChange = (rowIndex: number, field: NotaField, value: number) => {
    setRows(prev => {
      const row = prev[rowIndex];
      if (!row) return prev;

      const maxVal = maxNotaFor(row.setor, row.turno, field);
      const boundedValue = Math.min(Math.max(Number.isFinite(value) ? value : 0, 0), maxVal);
      const rowField = rowFieldFor(field);
      const updatedRow = { ...row, [rowField]: boundedValue };
      const processoPercent = processoPercentForSum(cadeiaSum(updatedRow));

      updatedRow.processo = `${processoPercent}%`;
      updatedRow.final = finalForProcess(updatedRow.status, processoPercent);

      const newRows = [...prev];
      newRows[rowIndex] = updatedRow;
      return newRows;
    });
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await apiFetchJson(`/api/fechamento/dados?mes=${mes}&ano=${ano}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rows)
      });
      showToast({
        title: 'Cálculo gravado com sucesso!',
        description: 'Dados cadastrais editados na tela continuam vindo do cadastro ao recarregar.',
        variant: 'success',
      });
      fetchDados();
    } catch (error) {
      showToast({
        title: 'Erro ao gravar cálculo',
        description: describeRequestError(error, 'Tente novamente em alguns instantes.'),
        variant: 'error',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const toggleAddOperador = async () => {
    const opening = !showAddOperador;
    setShowAddOperador(opening);
    if (opening && operadoresDisponiveis.length === 0) {
      try {
        const data = await apiFetchJson<OperadorDisponivel[]>('/api/operadores/');
        setOperadoresDisponiveis(Array.isArray(data) ? data : []);
      } catch (error) {
        showToast({
          title: 'Erro ao carregar colaboradores',
          description: describeRequestError(error, 'Tente novamente em alguns instantes.'),
          variant: 'error',
        });
      }
    }
  };

  const handleAddOperador = async (colaboradorId: number) => {
    setAddingOperadorId(colaboradorId);
    try {
      await apiFetchJson('/api/fechamento/layout/operadores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ colaborador_id: colaboradorId }),
      });
      showToast({ title: 'Operador RJ adicionado ao fechamento!', variant: 'success' });
      setShowAddOperador(false);
      setBuscaOperador('');
      fetchDados();
    } catch (error) {
      showToast({
        title: 'Erro ao adicionar operador',
        description: describeRequestError(error, 'Tente novamente em alguns instantes.'),
        variant: 'error',
      });
    } finally {
      setAddingOperadorId(null);
    }
  };

  const handleRemoveRow = async (row: FechamentoRow, idx: number) => {
    if (!row.layout_id && !row.colab_id) {
      showToast({ title: 'Linha sem vínculo — não é possível remover.', variant: 'error' });
      return;
    }
    if (!isUtiRj(row.setor, row.turno)) {
      showToast({ title: 'A remoção rápida é apenas para operador RJ.', variant: 'error' });
      return;
    }
    if (!window.confirm(`Remover operador RJ "${row.nome}" do fechamento? A remoção vale para todos os meses e pode ser desfeita adicionando o operador de novo.`)) {
      return;
    }
    const rowKey = `${row.layout_id ?? 'c'}-${row.colab_id}-${idx}`;
    setRemovingRowKey(rowKey);
    try {
      await apiFetchJson('/api/fechamento/layout/operadores/remover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layout_id: row.layout_id ?? null,
          colaborador_id: row.colab_id || null,
        }),
      });
      showToast({ title: 'Operador RJ removido do fechamento.', variant: 'success' });
      fetchDados();
    } catch (error) {
      showToast({
        title: 'Erro ao remover operador',
        description: describeRequestError(error, 'Tente novamente em alguns instantes.'),
        variant: 'error',
      });
    } finally {
      setRemovingRowKey(null);
    }
  };

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const blob = await apiFetchBlob(`/api/fechamento/exportar?mes=${mes}&ano=${ano}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rows),
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fechamento_${ano}_${mes.toString().padStart(2, '0')}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      showToast({
        title: 'Planilha exportada com sucesso!',
        description: 'O Excel usou a tela atual; edições cadastrais não foram gravadas.',
        variant: 'success',
      });
    } catch (error) {
      showToast({
        title: 'Erro ao exportar planilha',
        description: describeRequestError(error, 'Tente novamente em alguns instantes.'),
        variant: 'error',
      });
    } finally {
      setIsExporting(false);
    }
  };

  const calculoRows = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => isCadeiaApplicable(row));
  const selectedCalculoRow = selectedCalculoIndex !== null ? rows[selectedCalculoIndex] : null;
  const selectedCalculoSum = selectedCalculoRow ? cadeiaSum(selectedCalculoRow) : 0;
  const selectedCalculoTipo = selectedCalculoRow
    ? (isUtiRj(selectedCalculoRow.setor, selectedCalculoRow.turno) ? 'UTI/RJ' : 'UTI')
    : '';
  const supervisorOptions = useMemo(() => {
    const options = new Set<string>();
    supervisores.forEach(supervisor => {
      if (supervisor.trim()) options.add(supervisor.trim());
    });
    // Mantem o supervisor atual da linha visivel mesmo se o cadastro de usuarios
    // supervisores estiver incompleto; a origem segue sendo o cadastro do operador.
    rows.forEach(row => {
      if (row.supervisor.trim()) options.add(row.supervisor.trim());
    });
    return Array.from(options).sort((a, b) => a.localeCompare(b, 'pt-BR'));
  }, [rows, supervisores]);

  const colabIdsNaPlanilha = useMemo(
    () => new Set(rows.map(row => row.colab_id).filter(Boolean)),
    [rows],
  );
  const operadoresFiltrados = useMemo(() => {
    const busca = stripAccents(buscaOperador.trim());
    return operadoresDisponiveis
      .filter(isOperadorRj)
      .filter(op => !colabIdsNaPlanilha.has(op.id))
      .filter(op => !busca || stripAccents(`${op.nome} ${op.matricula ?? ''} ${op.setor ?? ''} ${op.escala ?? ''} ${op.supervisor ?? ''}`).includes(busca))
      .slice(0, 30);
  }, [operadoresDisponiveis, colabIdsNaPlanilha, buscaOperador]);

  return (
    <div className="max-w-screen-2xl mx-auto space-y-6 animate-fade-in pb-12 px-4">
      <PageHeader
        eyebrow="nstech | Fechamento"
        titleFirstWord="Fechamento"
        titleRest="do Mês"
        subtitle="Validação e Edição Pré-Exportação Oficial"
        aside={(
          <>
            <select 
              value={mes} 
              onChange={e => setMes(parseInt(e.target.value))}
              className="input-field max-w-[120px] bg-slate-800 border-slate-700"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
                <option key={m} value={m}>{m.toString().padStart(2, '0')} - {new Date(2000, m - 1).toLocaleString('pt-BR', { month: 'long', timeZone: 'America/Sao_Paulo' })}</option>
              ))}
            </select>
            <input 
              type="number" 
              value={ano} 
              onChange={e => setAno(parseInt(e.target.value))}
              className="input-field w-24 bg-slate-800 border-slate-700"
            />
            <button 
              onClick={fetchDados}
              disabled={isLoading}
              className="btn-secondary flex items-center gap-2"
              title="Recarregar Dados"
            >
              <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
            </button>
            <button 
              onClick={handleExport}
              disabled={isExporting}
              className="btn-primary flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 border-emerald-500/50 shadow-[0_0_15px_rgba(5,150,105,0.3)]"
            >
              <Download size={18} />
              {isExporting ? 'Exportando...' : 'Baixar Excel'}
            </button>
          </>
        )}
      />

      <ModuleInstructions
        storageKey="instructions:fechamento"
        steps={[
          'Escolha o mês e o ano e carregue os dados.',
          'Dados cadastrais vêm do cadastro de operadores; ajustes na tabela são temporários.',
          'Baixe o Excel no formato oficial usando a tela atual.',
        ]}
      />

      <div className="glass-panel p-4 rounded-2xl border border-white/5 shadow-xl flex flex-col h-[calc(100vh-200px)] min-h-[500px]">
        <div className="flex justify-between items-center mb-4 shrink-0">
          <h2 className="text-lg font-semibold text-slate-200">Visão Geral ({rows.length} registros)</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={toggleAddOperador}
              className="btn-secondary flex items-center gap-2 px-4 py-2"
            >
              <UserPlus size={18} />
              {showAddOperador ? 'Fechar' : 'Adicionar operador RJ'}
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || rows.length === 0}
              className="btn-primary flex items-center gap-2 px-4 py-2"
            >
              <Save size={18} />
              {isSaving ? 'Gravando...' : 'Gravar Cálculo'}
            </button>
          </div>
        </div>

        {showAddOperador && (
          <div className="shrink-0 mb-4 p-3 rounded-xl border border-white/10 bg-slate-800/40">
            <div className="flex items-center gap-3 mb-2">
              <input
                type="text"
                value={buscaOperador}
                onChange={e => setBuscaOperador(e.target.value)}
                placeholder="Buscar operador RJ por nome, matrícula, setor ou supervisor..."
                className="input-field flex-1 bg-slate-900/60 border-slate-700 text-sm"
                autoFocus
              />
              <span className="text-xs text-slate-500 whitespace-nowrap">
                {operadoresFiltrados.length} disponíveis
              </span>
            </div>
            <div className="max-h-48 overflow-y-auto custom-scrollbar divide-y divide-white/5">
              {operadoresFiltrados.length === 0 ? (
                <p className="text-xs text-slate-500 py-2">Nenhum operador RJ disponível fora da planilha.</p>
              ) : (
                operadoresFiltrados.map(op => (
                  <button
                    key={op.id}
                    onClick={() => handleAddOperador(op.id)}
                    disabled={addingOperadorId !== null}
                    className="w-full flex items-center justify-between gap-3 py-1.5 px-2 text-left text-xs text-slate-300 hover:bg-primary-500/10 rounded transition-colors disabled:opacity-50"
                  >
                    <span className="font-medium">{op.nome}</span>
                    <span className="text-slate-500 whitespace-nowrap">
                      {[op.matricula, op.escala || op.setor, op.supervisor].filter(Boolean).join(' · ')}
                    </span>
                    <span className="text-primary-400 whitespace-nowrap">
                      {addingOperadorId === op.id ? 'Adicionando...' : '+ Adicionar RJ'}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        {rows.length > 0 && (
          <div className="shrink-0 mb-4 py-3 border-y border-white/10">
            <div className="flex flex-col xl:flex-row xl:items-end gap-3">
              <div className="min-w-[260px] flex-1">
                <h3 className="text-sm font-semibold text-slate-200">Cálculo da cadeia de contatos</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Use para calcular Processo e Final. As notas não entram no Excel.
                </p>
              </div>

              <label className="flex flex-col gap-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 min-w-[260px]">
                Colaborador
                <select
                  value={selectedCalculoIndex ?? ''}
                  onChange={e => setSelectedCalculoIndex(e.target.value === '' ? null : parseInt(e.target.value))}
                  disabled={calculoRows.length === 0}
                  className="input-field bg-slate-800 border-slate-700 text-xs normal-case tracking-normal font-medium"
                >
                  {calculoRows.length === 0 ? (
                    <option value="">Nenhum operador UTI/RJ</option>
                  ) : (
                    calculoRows.map(({ row, index }) => (
                      <option key={`${row.colab_id}-${index}`} value={index}>
                        {row.nome} - {isUtiRj(row.setor, row.turno) ? 'UTI/RJ' : 'UTI'}
                      </option>
                    ))
                  )}
                </select>
              </label>

              {selectedCalculoRow && selectedCalculoIndex !== null && (
                <div className="flex flex-wrap items-end gap-3">
                  {(['mot', 'pa', 'cli', 'pol'] as const).map(field => {
                    const maxVal = maxNotaFor(selectedCalculoRow.setor, selectedCalculoRow.turno, field);
                    const rowField = rowFieldFor(field);
                    const label = field === 'mot' ? 'Mot' : field === 'pa' ? 'PA' : field === 'cli' ? 'Cli' : 'Pol';

                    return (
                      <label key={field} className="flex flex-col gap-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {label}
                        <input
                          type="number"
                          step={maxVal === 1.5 ? 1.5 : 1}
                          min={0}
                          max={maxVal}
                          value={selectedCalculoRow[rowField]}
                          onChange={e => handleNotaChange(selectedCalculoIndex, field, parseFloat(e.target.value) || 0)}
                          className="w-16 text-center bg-slate-900/50 border border-white/10 focus:ring-1 focus:ring-primary-500 px-2 py-2 rounded text-primary-300"
                          title={`Máx ${maxVal}`}
                        />
                      </label>
                    );
                  })}

                  <div className="flex items-center gap-3 text-xs text-slate-300 pb-2">
                    <span>{selectedCalculoTipo}</span>
                    <span>Soma {selectedCalculoSum}</span>
                    <span>Processo {selectedCalculoRow.processo}</span>
                    <span>Final {selectedCalculoRow.final || '-'}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="flex-1 text-slate-400 flex flex-col items-center justify-center">
            <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mb-4" />
            Processando fechamento...
          </div>
        ) : rows.length === 0 ? (
          <div className="flex-1 text-slate-400 flex items-center justify-center bg-slate-800/30 rounded-xl border border-slate-800/50">
            Nenhum dado encontrado para o período.
          </div>
        ) : (
          <div className="flex-1 overflow-auto rounded-xl border border-white/10 custom-scrollbar">
            <table className="w-max min-w-full text-left border-collapse bg-slate-900/50">
              <thead className="sticky top-0 z-10 bg-slate-800 shadow-md">
                <tr className="border-b border-white/10 text-[10px] font-bold text-slate-300 uppercase tracking-wider">
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap">ID</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap">MÊS</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[90px]">MATRÍCULA</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[200px]">COLABORADOR</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[100px]">OPERACIONAL</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[100px]">TELEFÔNICA</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[110px]">DESEMPENHO</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[90px]">STATUS</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[150px]">TURNO / OPERAÇÃO</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[150px]">SUPERVISOR</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[120px]">SETOR</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[100px]">PROCESSO</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[80px]">FINAL</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[90px]">HUAWEI</th>
                  <th className="py-2 px-3 border-r border-white/5 whitespace-nowrap min-w-[90px]">WEON</th>
                  <th className="py-2 px-3 whitespace-nowrap w-10" title="Remover operador RJ do fechamento"></th>
                </tr>
              </thead>
              <tbody className="text-xs">
                {rows.map((row, idx) => {
                  const rowKey = `${row.layout_id ?? 'c'}-${row.colab_id}-${idx}`;
                  const isRjRow = isUtiRj(row.setor, row.turno);

                  return (
                  <tr key={`${row.layout_id ?? row.colab_id}-${idx}`} className="border-b border-white/5 hover:bg-primary-500/10 transition-colors">
                    <td className="py-1 px-1 border-r border-white/5">
                      {row.layout_id ? (
                        <input
                          type="number"
                          value={row.id}
                          onChange={e => handleCellChange(idx, 'id', parseInt(e.target.value) || 0)}
                          className="w-14 text-center bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-1 py-1 rounded text-slate-400"
                          title="ID temporário para exportação; não é salvo pelo Gravar Cálculo"
                        />
                      ) : (
                        <span className="block text-center text-slate-500 px-2 py-1">{row.id}</span>
                      )}
                    </td>
                    <td className="py-1.5 px-3 border-r border-white/5 text-slate-500">{row.mes_str}</td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.matricula} onChange={e => handleCellChange(idx, 'matricula', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-300"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.nome} onChange={e => handleCellChange(idx, 'nome', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-200 font-medium"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input
                        type="text"
                        value={row.operacional}
                        onChange={e => handleCellChange(idx, 'operacional', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-300"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input
                        type="text"
                        value={row.telefonica}
                        onChange={e => handleCellChange(idx, 'telefonica', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-300"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.desempenho} onChange={e => handleCellChange(idx, 'desempenho', e.target.value)}
                        className={`w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded font-semibold ${row.desempenho === 'BOM' ? 'text-emerald-400' : row.desempenho === 'RUIM' ? 'text-red-400' : 'text-slate-400'}`}
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.status} onChange={e => handleCellChange(idx, 'status', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-400"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <select
                        value={row.turno}
                        onChange={e => handleCellChange(idx, 'turno', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-300 uppercase"
                      >
                        {!OPERACAO_OPCOES.includes(row.turno) && row.turno && (
                          <option value={row.turno}>{row.turno}</option>
                        )}
                        <option value="">-</option>
                        {OPERACAO_OPCOES.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <select
                        value={row.supervisor}
                        onChange={e => handleCellChange(idx, 'supervisor', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-300"
                      >
                        {/* Default vem do cadastro; auditor pode trocar. Mantem
                            o valor atual como opcao mesmo fora da lista de ativos. */}
                        {row.supervisor && !supervisorOptions.includes(row.supervisor) && (
                          <option value={row.supervisor}>{row.supervisor}</option>
                        )}
                        <option value="">-</option>
                        {supervisorOptions.map(supervisor => (
                          <option key={supervisor} value={supervisor}>{supervisor}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <select
                        value={row.setor}
                        onChange={e => handleCellChange(idx, 'setor', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-400 uppercase text-[10px]"
                      >
                        {!SETOR_OPCOES.includes(row.setor) && row.setor && (
                          <option value={row.setor}>{row.setor}</option>
                        )}
                        <option value="">-</option>
                        {SETOR_OPCOES.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.processo} onChange={e => handleCellChange(idx, 'processo', e.target.value)}
                        className="w-full text-center bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-300"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.final} onChange={e => handleCellChange(idx, 'final', e.target.value)}
                        className="w-full text-center bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded font-bold text-orange-400"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input 
                        type="text" value={row.huawei} onChange={e => handleCellChange(idx, 'huawei', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-400"
                      />
                    </td>
                    <td className="py-1 px-1 border-r border-white/5">
                      <input
                        type="text" value={row.weon || ''} onChange={e => handleCellChange(idx, 'weon', e.target.value)}
                        className="w-full bg-transparent border-none focus:ring-1 focus:ring-primary-500 px-2 py-1 rounded text-slate-400"
                      />
                    </td>
                    <td className="py-1 px-1 text-center">
                      <button
                        onClick={() => handleRemoveRow(row, idx)}
                        disabled={removingRowKey !== null || !isRjRow}
                        className="p-1 rounded text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                        title={isRjRow ? `Remover operador RJ ${row.nome} do fechamento` : 'Remoção rápida disponível apenas para operador RJ'}
                      >
                        <Trash2 size={14} className={removingRowKey === rowKey ? 'animate-pulse' : ''} />
                      </button>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
