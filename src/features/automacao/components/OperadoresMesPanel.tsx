/**
 * Quadro "Auditorias por operador" da tela de Automação.
 *
 * Mostra, para cada operador auditável que a coleta tenta baixar, quantas
 * auditorias ele já teve no mês corrente frente à cota mensal (`n / cota`).
 * A ordem vem do backend (mais auditorias primeiro); aqui só filtramos por busca.
 * "cheio" é um rótulo de texto neutro quando o operador atingiu a cota — não é
 * alerta. O número explica a cota do supervisor, não o download em si.
 */
import { useMemo, useState } from 'react';
import { Loader2, Search, Users } from 'lucide-react';

import type { OperadoresMes } from '../schemas';

interface OperadoresMesPanelProps {
  data: OperadoresMes | null;
  isLoading: boolean;
}

const MONTH_NAMES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

function formatMes(mes: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(mes || '');
  if (!match) return mes || '';
  const monthName = MONTH_NAMES[Number(match[2]) - 1];
  return monthName ? `${monthName} de ${match[1]}` : mes;
}

export function OperadoresMesPanel({ data, isLoading }: OperadoresMesPanelProps) {
  const [query, setQuery] = useState('');

  const operadores = data?.operadores ?? [];
  const cota = data?.cota ?? 0;

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return operadores;
    return operadores.filter((operador) => operador.nome.toLowerCase().includes(term));
  }, [operadores, query]);

  const cheiosCount = useMemo(() => operadores.filter((operador) => operador.cheio).length, [operadores]);

  return (
    <section className="panel-box-lg space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-xl font-bold text-slate-50 theme-light:text-slate-950">
            <Users className="h-5 w-5 text-primary-400" />
            Auditorias por operador
          </h3>
          <p className="mt-1 text-sm text-slate-400 theme-light:text-slate-700">
            {`Quantas auditorias cada operador já teve em ${formatMes(data?.mes ?? '')}, frente à cota mensal. "cheio" = atingiu a cota.`}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {cheiosCount > 0 && (
            <span className="shrink-0 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-semibold text-slate-300 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-700">
              {cheiosCount} no limite
            </span>
          )}
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar operador"
              className="glass-input w-full rounded-xl py-2 pl-9 pr-3 text-sm outline-none sm:w-56"
            />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-slate-400 theme-light:text-slate-700">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : operadores.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-slate-950/30 p-8 text-center text-sm text-slate-400 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-700">
          Nenhum operador auditável encontrado.
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-slate-950/30 p-8 text-center text-sm text-slate-400 theme-light:border-slate-300 theme-light:bg-white theme-light:text-slate-700">
          Nenhum operador corresponde à busca.
        </div>
      ) : (
        <div className="max-h-[28rem] overflow-y-auto rounded-2xl border border-white/10 theme-light:border-slate-300">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-slate-950/80 backdrop-blur theme-light:bg-slate-100">
              <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-slate-400 theme-light:text-slate-600">
                <th className="px-4 py-2.5">Operador</th>
                <th className="px-4 py-2.5">Setor</th>
                <th className="px-4 py-2.5 text-right">Cota Mensal</th>
                <th className="px-4 py-2.5 text-right" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((operador) => (
                <tr
                  key={`${operador.operator_id}|${operador.nome}`}
                  className="border-t border-white/5 theme-light:border-slate-200"
                >
                  <td className="px-4 py-2.5 font-medium text-slate-100 theme-light:text-slate-900">
                    {operador.nome || 'Operador não identificado'}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 theme-light:text-slate-700">
                    {operador.setor || '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-slate-200 theme-light:text-slate-900">
                    {operador.auditorias_mes} / {cota}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {operador.cheio && (
                      <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] font-semibold text-slate-300 theme-light:border-slate-300 theme-light:bg-slate-100 theme-light:text-slate-700">
                        cheio
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
