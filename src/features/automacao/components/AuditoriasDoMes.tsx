import { useMemo, useState } from 'react';
import { Bot, ExternalLink, FileAudio, Loader2, User } from 'lucide-react';

import type { AuditoriaDoMes } from '../hooks/useAutomacaoDashboard';

type FilterMode = 'todas' | 'auto' | 'manual' | 'desconhecida';

interface AuditoriasDoMesProps {
  items: AuditoriaDoMes[];
  isLoading: boolean;
  onOpenInArquivos: (id: number) => void;
}

const MONTH_NAMES = [
  'Janeiro',
  'Fevereiro',
  'Março',
  'Abril',
  'Maio',
  'Junho',
  'Julho',
  'Agosto',
  'Setembro',
  'Outubro',
  'Novembro',
  'Dezembro',
];

const AUTOMATION_ORIGINS = new Set([
  'automacao',
  'cron',
  'automation_engine',
  'cloud_scheduler',
  'resident_loop',
]);

function isAuto(item: AuditoriaDoMes): boolean {
  const origem = (item.criado_por || '').trim().toLowerCase();
  return AUTOMATION_ORIGINS.has(origem);
}

function formatDateTime(value: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function scoreClass(score: number | null): string {
  if (score == null) return 'border-slate-500/25 bg-slate-500/10 text-slate-300';
  if (score >= 80) return 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300';
  if (score >= 60) return 'border-amber-500/25 bg-amber-500/10 text-amber-300';
  return 'border-rose-500/25 bg-rose-500/10 text-rose-300';
}

export function AuditoriasDoMes({ items, isLoading, onOpenInArquivos }: AuditoriasDoMesProps) {
  const [filter, setFilter] = useState<FilterMode>('todas');

  const monthLabel = useMemo(() => {
    const now = new Date();
    return `${MONTH_NAMES[now.getMonth()]} de ${now.getFullYear()}`;
  }, []);

  const counts = useMemo(() => {
    let auto = 0;
    let manual = 0;
    let desconhecida = 0;
    for (const item of items) {
      const origem = (item.criado_por || '').trim().toLowerCase();
      if (!origem) desconhecida += 1;
      else if (isAuto(item)) auto += 1;
      else manual += 1;
    }
    return { todas: items.length, auto, manual, desconhecida };
  }, [items]);

  const filtered = useMemo(() => {
    if (filter === 'todas') return items;
    return items.filter((item) => {
      const origem = (item.criado_por || '').trim().toLowerCase();
      if (filter === 'desconhecida') return !origem;
      if (filter === 'auto') return !!origem && isAuto(item);
      return !!origem && !isAuto(item);
    });
  }, [filter, items]);

  return (
    <section className="panel-box-lg space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-xl font-bold text-slate-50 theme-light:text-slate-950">
            Auditorias de {monthLabel}
          </h3>
          <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-700">
            Tudo que foi auditado neste mês — automático e manual.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <FilterChip
            active={filter === 'todas'}
            onClick={() => setFilter('todas')}
            label="Todas"
            count={counts.todas}
          />
          <FilterChip
            active={filter === 'auto'}
            onClick={() => setFilter('auto')}
            label="Automáticas"
            count={counts.auto}
          />
          <FilterChip
            active={filter === 'manual'}
            onClick={() => setFilter('manual')}
            label="Manuais"
            count={counts.manual}
          />
          {counts.desconhecida > 0 && (
            <FilterChip
              active={filter === 'desconhecida'}
              onClick={() => setFilter('desconhecida')}
              label="Origem desc."
              count={counts.desconhecida}
            />
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-slate-400 theme-light:text-slate-700">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-slate-950/30 p-8 text-center text-sm text-slate-400 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-700">
          Nenhuma auditoria neste filtro.
        </div>
      ) : (
        <ul className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
          {filtered.map((item) => {
            const origem = (item.criado_por || '').trim().toLowerCase();
            const isDesc = !origem;
            const auto = !isDesc && isAuto(item);
            return (
              <li
                key={item.id}
                className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-950/30 p-3 transition hover:bg-slate-950/50 theme-light:border-slate-300 theme-light:bg-white theme-light:hover:bg-slate-50"
              >
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/5 text-slate-300 theme-light:bg-slate-100 theme-light:text-slate-700">
                  <FileAudio className="h-4 w-4" />
                </span>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-100 theme-light:text-slate-950">
                    {item.arquivo || `Auditoria #${item.id}`}
                  </p>
                  <p className="truncate text-xs text-slate-400 theme-light:text-slate-700">
                    {item.operator_name || 'Operador não identificado'}
                    {item.sector_id ? ` · ${item.sector_id}` : ''}
                    {' · '}
                    {formatDateTime(item.data_analise)}
                  </p>
                </div>

                <span
                  className={`hidden shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide sm:inline-flex ${
                    isDesc
                      ? 'border-slate-500/25 bg-slate-500/10 text-slate-400'
                      : auto
                      ? 'border-sky-500/25 bg-sky-500/10 text-sky-300'
                      : 'border-violet-500/25 bg-violet-500/10 text-violet-300'
                  }`}
                  title={isDesc ? 'Origem não informada' : auto ? 'Gerada pela rotina automática' : 'Auditoria manual'}
                >
                  {isDesc ? <User className="h-3 w-3 opacity-50" /> : auto ? <Bot className="h-3 w-3" /> : <User className="h-3 w-3" />}
                  {isDesc ? 'Origem desc.' : auto ? 'Auto' : 'Manual'}
                </span>

                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold ${scoreClass(item.score != null ? item.score * 10 : null)}`}
                >
                  {item.score != null ? Number(item.score).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 }) : '—'}
                </span>

                <button
                  type="button"
                  onClick={() => onOpenInArquivos(item.id)}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-slate-300 transition hover:bg-white/10 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-800"
                  aria-label="Abrir auditoria"
                  title="Visualizar Auditoria"
                >
                  <ExternalLink className="h-4 w-4" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition ${
        active
          ? 'border-primary-500/50 bg-primary-500/15 text-primary-300'
          : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-800'
      }`}
    >
      {label}
      <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] theme-light:bg-slate-100">
        {count}
      </span>
    </button>
  );
}
