import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Check, Loader2, Pencil, Power, Trash2, UserPlus } from 'lucide-react';

import { PageHeader } from '../../../shared/components/PageHeader';
import { ModuleInstructions } from '../../../shared/components/ModuleInstructions';
import { apiFetchJson } from '../../../shared/lib/apiClient';
import { formatOperationalLabel, getOperationalFilterKey } from '../../../shared/lib/operationalLabels';
import { useToast } from '../../../shared/components/ToastProvider';

interface ColaboradorRow {
  id: number;
  nome: string;
  supervisor: string;
  setor: string;
  escala: string;
  status: string;
  auditavel: boolean;
  matricula: string;
  id_weon: string;
  id_huawei: string;
  id_telefonia: string;
  softphone_number: string;
  telefonia_account: string;
  organizacao_telefonia: string;
  tipo_agente: string;
  status_telefonia: string;
  atualizado_em: string;
}

interface ColaboradorForm {
  nome: string;
  supervisor: string;
  setor: string;
  escala: string;
  status: string;
  auditavel: boolean;
  matricula: string;
  id_weon: string;
  id_huawei: string;
  id_telefonia: string;
  softphone_number: string;
  telefonia_account: string;
  organizacao_telefonia: string;
  tipo_agente: string;
  status_telefonia: string;
}

interface UserRow {
  username: string;
  role: string;
  supervisor_name?: string;
}

type StatusFilter = 'TODOS' | 'ATIVO' | 'INATIVO';

const EMPTY_FORM: ColaboradorForm = {
  nome: '',
  supervisor: '',
  setor: '',
  escala: '',
  status: 'ATIVO',
  auditavel: true,
  matricula: '',
  id_weon: '',
  id_huawei: '',
  id_telefonia: '',
  softphone_number: '',
  telefonia_account: '',
  organizacao_telefonia: '',
  tipo_agente: '',
  status_telefonia: '',
};

const LOWERCASE_NAME_PARTICLES = new Set(['da', 'de', 'do', 'das', 'dos', 'e']);
const UPPERCASE_NAME_SUFFIXES = new Set(['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'JR', 'JR.', 'SR', 'SR.']);
const EXCLUDED_OPERATION_TERMS = [
  'COMANDOLOG',
  'GESTAO E COORDENACAO',
  'OPERACAO PROFARMA',
  'OPERACAO TORA PA',
  'OPERACAO TORA',
  'SANOFI',
];

function normalizeValue(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function buildLooseLookupKey(value: string | null | undefined): string {
  return normalizeValue(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase();
}

function formatNameToken(part: string, index: number): string {
  const normalizedPart = part.trim();
  if (!normalizedPart) {
    return '';
  }

  const uppercaseToken = normalizedPart.toUpperCase();
  if (UPPERCASE_NAME_SUFFIXES.has(uppercaseToken)) {
    return uppercaseToken;
  }

  const lowercaseToken = normalizedPart.toLowerCase();
  if (index > 0 && LOWERCASE_NAME_PARTICLES.has(lowercaseToken)) {
    return lowercaseToken;
  }

  return normalizedPart
    .split('-')
    .map((segment) => (segment ? segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase() : ''))
    .join('-');
}

function formatPersonLabel(value: string | null | undefined): string {
  const rawValue = normalizeValue(value).replace(/\s+/g, ' ').trim();
  if (!rawValue) {
    return '';
  }

  return rawValue
    .split(' ')
    .filter(Boolean)
    .map((part, index) => formatNameToken(part, index))
    .join(' ');
}

function getSituacaoLabel(row: Pick<ColaboradorRow, 'status'>): string {
  return row.status === 'ATIVO' ? 'Ativo' : 'Inativo';
}

function resolveHuaweiId(row: Pick<ColaboradorRow, 'id_huawei' | 'id_telefonia'> | Pick<ColaboradorForm, 'id_huawei' | 'id_telefonia'>): string {
  return normalizeValue(row.id_huawei) || normalizeValue(row.id_telefonia);
}

function isTechnicalTelephonyRow(row: ColaboradorRow): boolean {
  const normalizedName = buildLooseLookupKey(row.nome);
  const normalizedAccount = buildLooseLookupKey(row.telefonia_account);
  const hasTelephonyMetadata = [
    row.telefonia_account,
    row.organizacao_telefonia,
    row.tipo_agente,
    row.status_telefonia,
    row.id_telefonia,
    row.softphone_number,
  ].some((value) => value.trim());

  return !row.matricula.trim()
    && !row.supervisor.trim()
    && (
      normalizedName === 'CONTENCAO'
      || normalizedName.startsWith('CONTENCAO ')
      || normalizedAccount === 'CONTENCAO'
      || normalizedAccount.startsWith('CONTENCAO ')
      || (!normalizedName && hasTelephonyMetadata)
    );
}

function isExcludedOperationRow(row: ColaboradorRow): boolean {
  const operationText = buildLooseLookupKey([
    row.setor,
    row.escala,
    row.organizacao_telefonia,
    row.telefonia_account,
  ].join(' '));
  return EXCLUDED_OPERATION_TERMS.some((term) => operationText.includes(term));
}

function isRemovedOperatorRow(row: ColaboradorRow): boolean {
  return isTechnicalTelephonyRow(row) || isExcludedOperationRow(row);
}

function normalizeColaborador(row: Partial<ColaboradorRow> & Record<string, unknown>): ColaboradorRow {
  return {
    id: Number(row.id ?? 0),
    nome: formatPersonLabel(row.nome),
    supervisor: formatPersonLabel(row.supervisor),
    setor: normalizeValue(row.setor),
    escala: normalizeValue(row.escala),
    status: normalizeValue(row.status || 'ATIVO') || 'ATIVO',
    auditavel: Boolean(row.auditavel ?? true),
    matricula: normalizeValue(row.matricula),
    id_weon: normalizeValue(row.id_weon),
    id_huawei: normalizeValue(row.id_huawei) || normalizeValue(row.id_telefonia),
    id_telefonia: normalizeValue(row.id_telefonia),
    softphone_number: normalizeValue(row.softphone_number),
    telefonia_account: normalizeValue(row.telefonia_account),
    organizacao_telefonia: normalizeValue(row.organizacao_telefonia),
    tipo_agente: normalizeValue(row.tipo_agente),
    status_telefonia: normalizeValue(row.status_telefonia),
    atualizado_em: normalizeValue(row.atualizado_em),
  };
}

function toPayload(row: ColaboradorRow): ColaboradorForm {
  const primaryHuaweiId = resolveHuaweiId(row);
  return {
    nome: formatPersonLabel(row.nome),
    supervisor: formatPersonLabel(row.supervisor),
    setor: row.setor,
    escala: row.escala,
    status: row.status,
    auditavel: row.auditavel,
    matricula: row.matricula,
    id_weon: row.id_weon,
    id_huawei: primaryHuaweiId,
    id_telefonia: primaryHuaweiId,
    softphone_number: row.softphone_number,
    telefonia_account: row.telefonia_account,
    organizacao_telefonia: row.organizacao_telefonia,
    tipo_agente: row.tipo_agente,
    status_telefonia: row.status_telefonia,
  };
}

function collectRegisteredSupervisors(users: UserRow[]): string[] {
  const supervisors = users
    .filter((user) => user.role === 'supervisor')
    .map((user) => formatPersonLabel(user.supervisor_name || user.username))
    .filter(Boolean);

  return Array.from(new Set(supervisors)).sort((a, b) => a.localeCompare(b, 'pt-BR'));
}

function collectDistinctSectorOptions(rows: ColaboradorRow[]): Array<{ value: string; label: string }> {
  const optionsByKey = new Map<string, { value: string; label: string }>();

  rows.forEach((row) => {
    const key = getOperationalFilterKey(row.setor);
    const label = formatOperationalLabel(row.setor);
    if (!key || !label || optionsByKey.has(key)) {
      return;
    }
    optionsByKey.set(key, { value: key, label });
  });

  return Array.from(optionsByKey.values()).sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'));
}


export function ColaboradorManagement() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [colaboradores, setColaboradores] = useState<ColaboradorRow[]>([]);
  const [registeredSupervisors, setRegisteredSupervisors] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ColaboradorForm>({ ...EMPTY_FORM });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshingRowId, setIsRefreshingRowId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [isBulkActing, setIsBulkActing] = useState(false);
  const { showToast } = useToast();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('TODOS');
  const [supervisorFilter, setSupervisorFilter] = useState('');
  const [setorFilter, setSetorFilter] = useState('');

  const fetchColaboradores = async ({ showLoader = true }: { showLoader?: boolean } = {}) => {
    try {
      if (showLoader) setIsLoading(true);
      setError(null);
      const [colaboradoresData, usersData] = await Promise.all([
        apiFetchJson<Array<Record<string, unknown>>>('/api/admin/colaboradores'),
        apiFetchJson<UserRow[]>('/api/admin/users'),
      ]);
      const normalizedRows = colaboradoresData.map(normalizeColaborador).filter((row) => !isRemovedOperatorRow(row));
      const validIds = new Set(normalizedRows.map((row) => row.id));
      setColaboradores(normalizedRows);
      setRegisteredSupervisors(collectRegisteredSupervisors(usersData));
      setSelectedIds((current) => current.filter((id) => validIds.has(id)));
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Falha ao carregar operadores.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchColaboradores();
  }, []);

  useEffect(() => {
    if (searchParams.get('novo') === '1') {
      const idHuawei = searchParams.get('id_huawei') || '';
      const nome = searchParams.get('nome') || '';
      const setor = searchParams.get('setor') || '';

      setEditingId(null);
      setForm({
        ...EMPTY_FORM,
        id_huawei: idHuawei,
        id_telefonia: idHuawei,
        nome: formatPersonLabel(nome),
        setor: setor,
      });
      setIsFormOpen(true);

      const newSearchParams = new URLSearchParams(searchParams);
      newSearchParams.delete('novo');
      newSearchParams.delete('id_huawei');
      newSearchParams.delete('nome');
      newSearchParams.delete('setor');
      setSearchParams(newSearchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const resetForm = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setIsFormOpen(false);
  };

  const openCreateForm = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setIsFormOpen(true);
  };

  const openEditForm = (row: ColaboradorRow) => {
    setEditingId(row.id);
    setForm(toPayload(row));
    setIsFormOpen(true);
  };

  const handleFormSubmit = async () => {
    if (!form.nome.trim()) {
      setError('Nome é obrigatório.');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      const primaryHuaweiId = resolveHuaweiId(form).trim();
      const endpoint = editingId === null
        ? '/api/admin/colaboradores'
        : `/api/admin/colaboradores/${editingId}`;
      const method = editingId === null ? 'POST' : 'PUT';
      const normalizedForm = {
        ...form,
        nome: formatPersonLabel(form.nome),
        supervisor: formatPersonLabel(form.supervisor),
      };

      await apiFetchJson(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...normalizedForm,
          auditavel: normalizedForm.status === 'ATIVO',
          id_huawei: primaryHuaweiId,
          id_telefonia: primaryHuaweiId,
        }),
      });

      resetForm();
      await fetchColaboradores({ showLoader: false });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Falha ao salvar operador.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (row: ColaboradorRow) => {
    if (!window.confirm(`Excluir o operador "${row.nome}"? Use a inativação como fluxo padrão.`)) {
      return;
    }

    try {
      setDeletingId(row.id);
      setError(null);
      await apiFetchJson(`/api/admin/colaboradores/${row.id}`, { method: 'DELETE' });
      await fetchColaboradores({ showLoader: false });
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Falha ao excluir operador.');
    } finally {
      setDeletingId(null);
    }
  };

  const updateRow = async (row: ColaboradorRow, overrides: Partial<ColaboradorForm>) => {
    try {
      setIsRefreshingRowId(row.id);
      setError(null);
      await apiFetchJson(`/api/admin/colaboradores/${row.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...toPayload(row),
          ...overrides,
        }),
      });
      await fetchColaboradores({ showLoader: false });
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Falha ao atualizar operador.');
    } finally {
      setIsRefreshingRowId(null);
    }
  };

  const handleStatusToggle = async (row: ColaboradorRow) => {
    const nextStatus = row.status === 'ATIVO' ? 'INATIVO' : 'ATIVO';
    await updateRow(row, {
      status: nextStatus,
      auditavel: nextStatus === 'ATIVO' ? true : false,
    });
  };

  const handleRowSelection = (colaboradorId: number, checked: boolean) => {
    setSelectedIds((current) => {
      if (checked) {
        return current.includes(colaboradorId) ? current : [...current, colaboradorId];
      }
      return current.filter((id) => id !== colaboradorId);
    });
  };

  const handleBulkAction = async (action: 'activate' | 'inactivate') => {
    if (selectedIds.length === 0) return;
    const label = action === 'activate' ? 'Ativar' : 'Inativar';
    if (!window.confirm(`${label} ${selectedIds.length} operador(es) selecionado(s)?`)) return;
    try {
      setIsBulkActing(true);
      setError(null);
      const result = await apiFetchJson<{ updated: number }>('/api/admin/colaboradores/bulk-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: selectedIds, action }),
      });
      showToast({ variant: 'success', title: 'Ação em lote', description: `${result.updated} operador(es) ${action === 'activate' ? 'ativados' : 'inativados'}.` });
      setSelectedIds([]);
      await fetchColaboradores({ showLoader: false });
    } catch (bulkError) {
      setError(bulkError instanceof Error ? bulkError.message : 'Falha na ação em lote.');
    } finally {
      setIsBulkActing(false);
    }
  };


  const lowerSearch = search.trim().toLowerCase();
  const filteredColaboradores = colaboradores.filter((row) => {
    if (statusFilter !== 'TODOS' && row.status !== statusFilter) {
      return false;
    }
    if (supervisorFilter && row.supervisor !== supervisorFilter) {
      return false;
    }
    if (setorFilter && getOperationalFilterKey(row.setor) !== setorFilter) {
      return false;
    }
    if (!lowerSearch) {
      return true;
    }

    return [row.nome, row.supervisor, row.setor, row.escala, row.matricula, resolveHuaweiId(row), row.id_weon].some((value) =>
      value.toLowerCase().includes(lowerSearch),
    );
  });

  const supervisorOptions = registeredSupervisors;
  const setorOptions = useMemo(() => collectDistinctSectorOptions(
    supervisorFilter ? colaboradores.filter((row) => row.supervisor === supervisorFilter) : colaboradores,
  ), [colaboradores, supervisorFilter]);
  const supervisorSectorOptions = useMemo(() => collectDistinctSectorOptions(
    supervisorFilter ? colaboradores.filter((row) => row.supervisor === supervisorFilter) : [],
  ), [colaboradores, supervisorFilter]);
  const supervisorSectorHint = supervisorFilter && supervisorSectorOptions.length > 1
    ? `Supervisor vinculado a ${supervisorSectorOptions.length} setores. Selecione um para refinar.`
    : null;
  const selectedIdSet = new Set(selectedIds);
  const filteredIds = filteredColaboradores.map((row) => row.id);
  const allFilteredSelected = filteredIds.length > 0 && filteredIds.every((id) => selectedIdSet.has(id));

  useEffect(() => {
    if (!supervisorFilter) {
      return;
    }

    if (!supervisorOptions.includes(supervisorFilter)) {
      setSupervisorFilter('');
      setSetorFilter('');
      return;
    }

    if (supervisorSectorOptions.length === 1) {
      const [onlySector] = supervisorSectorOptions;
      setSetorFilter((current) => (current === onlySector.value ? current : onlySector.value));
      return;
    }

    if (setorFilter && !supervisorSectorOptions.some((option) => option.value === setorFilter)) {
      setSetorFilter('');
    }
  }, [setorFilter, supervisorFilter, supervisorOptions, supervisorSectorOptions]);

  const toggleFilteredSelection = () => {
    if (filteredIds.length === 0) {
      return;
    }

    if (allFilteredSelected) {
      const filteredIdSet = new Set(filteredIds);
      setSelectedIds((current) => current.filter((id) => !filteredIdSet.has(id)));
      return;
    }

    const mergedIds = new Set(selectedIds);
    filteredIds.forEach((id) => mergedIds.add(id));
    setSelectedIds(Array.from(mergedIds));
  };

  const totalColaboradores = colaboradores.length;
  const totalAtivos = colaboradores.filter((row) => row.status === 'ATIVO').length;
  const totalInativos = colaboradores.filter((row) => row.status !== 'ATIVO').length;

  const bulkButtonClass = (tone: 'neutral' | 'success' | 'danger' = 'neutral') =>
    `rounded-xl border px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:brightness-95 ${tone === 'danger'
      ? 'border-red-500/30 bg-red-500/10 text-red-200 hover:bg-red-500/15 theme-light:border-red-300 theme-light:bg-red-100 theme-light:text-red-800 theme-light:hover:bg-red-200'
      : tone === 'success'
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/15 theme-light:border-emerald-300 theme-light:bg-emerald-100 theme-light:text-emerald-900 theme-light:hover:bg-emerald-200'
        : 'border-white/10 bg-white/[0.03] text-slate-200 hover:border-white/20 hover:bg-white/[0.05] theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800 theme-light:hover:bg-slate-200'
    }`;

  const iconButtonClass = (tone: 'neutral' | 'status' | 'success' | 'danger' = 'neutral') =>
    `inline-flex h-9 w-9 items-center justify-center rounded-lg border transition-colors disabled:cursor-not-allowed disabled:brightness-95 ${tone === 'status'
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-200 hover:bg-amber-500/15 theme-light:border-amber-300 theme-light:bg-amber-100 theme-light:text-amber-900 theme-light:hover:bg-amber-200'
      : tone === 'success'
        ? 'border-primary-500/30 bg-primary-500/10 text-primary-300 hover:bg-primary-500/15 theme-light:border-orange-300 theme-light:bg-orange-100 theme-light:text-orange-900 theme-light:hover:bg-orange-200'
        : tone === 'danger'
          ? 'border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/15 theme-light:border-red-300 theme-light:bg-red-100 theme-light:text-red-800 theme-light:hover:bg-red-200'
          : 'border-white/10 bg-white/[0.03] text-slate-200 hover:border-white/20 hover:bg-white/[0.05] theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-800 theme-light:hover:bg-slate-200'
    }`;

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-400 theme-light:text-slate-700">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="nstech | Operadores"
        titleFirstWord="Gestão"
        titleRest="de Operadores"
        subtitle="Cadastre e atualize operadores."
        headingTag="h2"
      />

      <ModuleInstructions
        storageKey="instructions:operadores"
        steps={[
          'Cadastre e edite operadores (matrícula, ID Huawei, setor).',
          'Marque quem está ativo no roteamento.',
          'Só operadores ativos com ID Huawei entram na coleta automática.',
        ]}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="panel-box theme-light:bg-slate-200 theme-light:border-slate-300">
          <p className="metric-label">Base total</p>
          <p className="mt-2 text-3xl font-black text-white theme-light:text-slate-900">{totalColaboradores}</p>
          <p className="mt-2 text-sm text-slate-400 theme-light:text-slate-700">Todos os operadores cadastrados.</p>
        </div>
        <div className="panel-box theme-light:bg-slate-200 theme-light:border-slate-300">
          <p className="metric-label">Ativos</p>
          <p className="mt-2 text-3xl font-black text-white theme-light:text-slate-900">{totalAtivos}</p>
          <p className="mt-2 text-sm text-slate-400 theme-light:text-slate-700">Disponíveis no cadastro operacional.</p>
        </div>
        <div className="panel-box theme-light:bg-slate-200 theme-light:border-slate-300">
          <p className="metric-label">Inativos</p>
          <p className="mt-2 text-3xl font-black text-white theme-light:text-slate-900">{totalInativos}</p>
          <p className="mt-2 text-sm text-slate-400 theme-light:text-slate-700">Operadores temporariamente fora da operação.</p>
        </div>
      </div>

      <div className="panel-box theme-light:bg-slate-200 theme-light:border-slate-300">
        <p className="section-title-sm">Regra operacional</p>
        <p className="mt-2 text-sm text-slate-400 theme-light:text-slate-700">
          Operadores ativos entram na auditoria. Use o status inativo para férias, afastamentos e pausas operacionais.
        </p>
      </div>

      <div className="panel-box theme-light:bg-slate-200 theme-light:border-slate-300">
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="space-y-2 xl:col-span-2">
              <span className="metric-label">Buscar</span>
              <input
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Nome, supervisor, setor, matrícula..."
                className="glass-input w-full rounded-xl p-3 text-sm outline-none"
              />
            </label>

            <label className="space-y-2">
              <span className="metric-label">Status</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                className="glass-input w-full rounded-xl bg-transparent p-3 text-sm outline-none"
              >
                <option value="TODOS">Todos</option>
                <option value="ATIVO">Ativos</option>
                <option value="INATIVO">Inativos</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="metric-label">Supervisor</span>
              <select
                value={supervisorFilter}
                onChange={(event) => setSupervisorFilter(event.target.value)}
                className="glass-input w-full rounded-xl bg-transparent p-3 text-sm outline-none"
              >
                <option value="">Todos</option>
                {supervisorOptions.map((supervisor) => (
                  <option key={supervisor} value={supervisor}>
                    {formatPersonLabel(supervisor)}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-2">
              <span className="metric-label">Setor</span>
              <select
                value={setorFilter}
                onChange={(event) => setSetorFilter(event.target.value)}
                className="glass-input w-full rounded-xl bg-transparent p-3 text-sm outline-none"
              >
                <option value="">Todos</option>
                {setorOptions.map((setor) => (
                  <option key={setor.value} value={setor.value}>
                    {setor.label}
                  </option>
                ))}
              </select>
              {supervisorSectorHint ? (
                <span className="block text-xs text-amber-300 theme-light:text-amber-700">
                  {supervisorSectorHint}
                </span>
              ) : null}
            </label>
          </div>

          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <p className="text-sm text-slate-400 theme-light:text-slate-700">
              {filteredColaboradores.length} encontrados. {selectedIds.length} selecionados.
            </p>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={toggleFilteredSelection}
                disabled={filteredIds.length === 0}
                className={bulkButtonClass()}
              >
                {allFilteredSelected ? 'Desmarcar todos' : 'Marcar todos'}
              </button>
              <button
                type="button"
                onClick={() => setSelectedIds([])}
                disabled={selectedIds.length === 0}
                className={bulkButtonClass()}
              >
                Limpar seleção
              </button>
              {selectedIds.length > 0 && (
                <>
                  <button
                    type="button"
                    onClick={() => handleBulkAction('activate')}
                    disabled={isBulkActing}
                    className={bulkButtonClass('success')}
                  >
                    {isBulkActing ? <Loader2 className="inline h-4 w-4 animate-spin mr-1" /> : null}
                    Ativar ({selectedIds.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => handleBulkAction('inactivate')}
                    disabled={isBulkActing}
                    className={bulkButtonClass('danger')}
                  >
                    {isBulkActing ? <Loader2 className="inline h-4 w-4 animate-spin mr-1" /> : null}
                    Inativar ({selectedIds.length})
                  </button>
                </>
              )}
              <button type="button" onClick={openCreateForm} className="btn-primary px-4 py-3 text-sm font-semibold">
                <span className="inline-flex items-center gap-2">
                  <UserPlus className="h-4 w-4" />
                  Novo operador
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {isFormOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) resetForm(); }}
        >
          <div className="relative mx-4 w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl theme-light:border-slate-300 theme-light:bg-white">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <p className="section-title-sm">{editingId === null ? 'Novo operador' : 'Editar operador'}</p>
                <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-700">
                  Preencha os dados principais do operador.
                </p>
              </div>
              <button type="button" onClick={resetForm} className="btn-ghost px-3 py-2 text-sm font-semibold">
                Fechar
              </button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <label className="space-y-2 xl:col-span-3">
                <span className="metric-label">Nome</span>
                <input
                  type="text"
                  value={form.nome}
                  onChange={(event) => setForm((current) => ({ ...current, nome: event.target.value }))}
                  className="glass-input w-full rounded-xl p-3 text-sm outline-none"
                />
              </label>

              <label className="space-y-2">
                <span className="metric-label">Supervisor</span>
                <select
                  value={form.supervisor}
                  onChange={(event) => setForm((current) => ({ ...current, supervisor: event.target.value }))}
                  className="glass-input w-full rounded-xl bg-transparent p-3 text-sm outline-none"
                >
                  <option value="">Sem supervisor</option>
                  {supervisorOptions.map((sup) => (
                    <option key={sup} value={sup}>{formatPersonLabel(sup)}</option>
                  ))}
                  {form.supervisor && !supervisorOptions.includes(form.supervisor) ? (
                    <option value={form.supervisor}>{formatPersonLabel(form.supervisor)} (fora das configurações)</option>
                  ) : null}
                </select>
                <span className="block text-xs text-slate-500 theme-light:text-slate-600">
                  Cadastre ou remova supervisores em Configurações.
                </span>
              </label>

              <label className="space-y-2">
                <span className="metric-label">Setor</span>
                <select
                  value={form.setor}
                  onChange={(event) => setForm((current) => ({ ...current, setor: event.target.value }))}
                  className="glass-input w-full rounded-xl bg-transparent p-3 text-sm outline-none"
                >
                  <option value="">Selecione...</option>
                  {(() => {
                    const extraOptions = [
                      { value: 'TREINAMENTO', label: 'Treinamento' },
                      { value: 'LOGISTICA', label: 'Logística' }
                    ];
                    const merged = [...setorOptions];
                    extraOptions.forEach(opt => {
                      if (!merged.find(m => m.value === opt.value)) merged.push(opt);
                    });
                    return merged.sort((a, b) => a.label.localeCompare(b.label, 'pt-BR')).map((setor) => (
                      <option key={setor.value} value={setor.value}>{setor.label}</option>
                    ));
                  })()}
                </select>
              </label>

              <label className="space-y-2">
                <span className="metric-label">Escala</span>
                <input
                  type="text"
                  list="escala-options"
                  value={form.escala}
                  onChange={(event) => setForm((current) => ({ ...current, escala: event.target.value }))}
                  placeholder="Livre ou selecione..."
                  className="glass-input w-full rounded-xl p-3 text-sm outline-none"
                />
                <datalist id="escala-options">
                  <option value="Amarela" />
                  <option value="Azul" />
                  <option value="Cinza" />
                  <option value="Verde" />
                </datalist>
              </label>

              <label className="space-y-2">
                <span className="metric-label">Matrícula</span>
                <input
                  type="text"
                  value={form.matricula}
                  onChange={(event) => setForm((current) => ({ ...current, matricula: event.target.value }))}
                  className="glass-input w-full rounded-xl p-3 text-sm outline-none"
                />
              </label>

              <label className="space-y-2">
                <span className="metric-label">Status</span>
                <select
                  value={form.status}
                  onChange={(event) => {
                    const nextStatus = event.target.value;
                    setForm((current) => ({
                      ...current,
                      status: nextStatus,
                      auditavel: nextStatus === 'ATIVO',
                    }));
                  }}
                  className="glass-input w-full rounded-xl bg-transparent p-3 text-sm outline-none"
                >
                  <option value="ATIVO">Ativo</option>
                  <option value="INATIVO">Inativo</option>
                </select>
              </label>

              <label className="space-y-2">
                <span className="metric-label">ID Huawei</span>
                <input
                  type="text"
                  value={resolveHuaweiId(form)}
                  onChange={(event) => {
                    const nextValue = event.target.value;
                    setForm((current) => ({
                      ...current,
                      id_huawei: nextValue,
                      id_telefonia: nextValue,
                    }));
                  }}
                  className="glass-input w-full rounded-xl p-3 text-sm outline-none"
                />
              </label>

              <label className="space-y-2">
                <span className="metric-label">WEON</span>
                <input
                  type="text"
                  value={form.id_weon}
                  onChange={(event) => setForm((current) => ({ ...current, id_weon: event.target.value }))}
                  className="glass-input w-full rounded-xl p-3 text-sm outline-none"
                />
              </label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={resetForm} className="btn-ghost px-4 py-3 text-sm font-semibold">
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleFormSubmit}
                disabled={isSubmitting}
                className="btn-primary px-5 py-3 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-70"
              >
                <span className="inline-flex items-center gap-2">
                  {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  {editingId === null ? 'Criar operador' : 'Salvar operador'}
                </span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="panel-box-plain theme-light:bg-slate-200 theme-light:border-slate-300">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] text-sm">
            <thead>
              <tr className="border-b border-white/10 theme-light:border-slate-300">
                <th className="px-4 py-4 text-left text-xs font-semibold tracking-wide text-slate-400">Sel.</th>
                <th className="px-4 py-4 text-left text-xs font-semibold tracking-wide text-slate-400">Operador</th>
                <th className="px-4 py-4 text-left text-xs font-semibold tracking-wide text-slate-400">Setor</th>
                <th className="px-4 py-4 text-left text-xs font-semibold tracking-wide text-slate-400">Supervisor</th>
                <th className="px-4 py-4 text-left text-xs font-semibold tracking-wide text-slate-400">Situação</th>
                <th className="px-4 py-4 text-left text-xs font-semibold tracking-wide text-slate-400">IDs</th>
                <th className="px-4 py-4 text-right text-xs font-semibold tracking-wide text-slate-400">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filteredColaboradores.map((row) => {
                const isBusy = isRefreshingRowId === row.id || deletingId === row.id;
                return (
                  <tr
                    key={row.id}
                    className="border-b border-white/5 align-top transition-colors hover:bg-white/5 theme-light:border-slate-200"
                  >
                    <td className="px-4 py-4">
                      <input
                        type="checkbox"
                        checked={selectedIdSet.has(row.id)}
                        onChange={(event) => handleRowSelection(row.id, event.target.checked)}
                        disabled={isBusy}
                        aria-label={`Selecionar ${row.nome}`}
                        className="h-4 w-4 rounded border-white/20 bg-transparent"
                      />
                    </td>
                    <td className="px-4 py-4">
                      <div className="space-y-1">
                        <p className="font-semibold text-white theme-light:text-slate-900">{formatPersonLabel(row.nome)}</p>
                        <p className="text-xs text-slate-500 theme-light:text-slate-600">
                          Matrícula: {row.matricula || '-'}
                        </p>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-slate-300 theme-light:text-slate-700">
                      <p>{formatOperationalLabel(row.setor) || '-'}</p>
                      {row.escala ? (
                        <p className="mt-1 text-xs text-slate-500 theme-light:text-slate-600">
                          {formatOperationalLabel(row.escala)}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-4 text-slate-300 theme-light:text-slate-700">{formatPersonLabel(row.supervisor) || '-'}</td>
                    <td className="px-4 py-4">
                      <span
                        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${row.status !== 'ATIVO'
                          ? 'border-red-500/30 bg-red-500/15 text-red-300 theme-light:border-red-300 theme-light:bg-red-100 theme-light:text-red-800'
                          : 'border-green-500/30 bg-green-500/15 text-green-300 theme-light:border-emerald-300 theme-light:bg-emerald-100 theme-light:text-emerald-900'
                          }`}
                      >
                        {getSituacaoLabel(row)}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-xs text-slate-400 theme-light:text-slate-700">
                      <p>ID Huawei: {resolveHuaweiId(row) || '-'}</p>
                      <p className="mt-1">WEON: {row.id_weon || '-'}</p>
                      {row.id_telefonia && row.id_telefonia !== resolveHuaweiId(row) ? (
                        <p className="mt-1">ID de telefonia (legado): {row.id_telefonia}</p>
                      ) : null}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex justify-end">
                        <div className="inline-flex items-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1 theme-light:border-slate-300 theme-light:bg-slate-100">
                          <button
                            type="button"
                            onClick={() => handleStatusToggle(row)}
                            disabled={isBusy}
                            className={iconButtonClass(row.status === 'ATIVO' ? 'success' : 'danger')}
                            title={row.status === 'ATIVO' ? `Inativar ${formatPersonLabel(row.nome)}` : `Ativar ${formatPersonLabel(row.nome)}`}
                            aria-label={row.status === 'ATIVO' ? `Inativar ${formatPersonLabel(row.nome)}` : `Ativar ${formatPersonLabel(row.nome)}`}
                          >
                            <Power className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => openEditForm(row)}
                            disabled={isBusy}
                            className={iconButtonClass()}
                            title={`Editar ${formatPersonLabel(row.nome)}`}
                            aria-label={`Editar ${formatPersonLabel(row.nome)}`}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(row)}
                            disabled={isBusy}
                            className={iconButtonClass('danger')}
                            title={`Excluir ${formatPersonLabel(row.nome)}`}
                            aria-label={`Excluir ${formatPersonLabel(row.nome)}`}
                          >
                            {deletingId === row.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {filteredColaboradores.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-10 text-center text-slate-500 theme-light:text-slate-700">
                    Nenhum operador encontrado para os filtros aplicados.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export const OperadorManagement = ColaboradorManagement;
