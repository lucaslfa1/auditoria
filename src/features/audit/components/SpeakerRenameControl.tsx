/**
 * Controle de troca GLOBAL de interlocutor na transcrição em edição.
 *
 * Escolhe um locutor presente ("De") e um destino ("Para") e, ao aplicar, troca
 * TODAS as falas daquele locutor de uma vez (ex.: Polícia → Motorista em toda a
 * ligação). Usado no editor de transcrição de Arquivos Salvos e Auditorias do
 * mês, ao lado do seletor por fala. A troca em si é feita pelo pai via
 * `renameSpeakerEverywhere`; aqui só montamos as opções e emitimos (from, to).
 */
import { useState } from 'react';

import { SPEAKER_OPTIONS, listSpeakers } from '../lib/speakerLabels';

interface SpeakerRenameControlProps {
  /** Segmentos atuais (para listar os locutores presentes em "De"). */
  segments: { text: string }[];
  /** Aplica a troca global de `from` para `to` em todas as falas. */
  onApply: (from: string, to: string) => void;
  disabled?: boolean;
}

export function SpeakerRenameControl({ segments, onApply, disabled }: SpeakerRenameControlProps) {
  const present = listSpeakers(segments);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  if (present.length === 0) return null;

  const selectClass =
    'text-xs rounded-lg border px-2 py-1.5 bg-slate-900 border-white/10 text-slate-200 focus:outline-none focus:border-primary-500/50 theme-light:bg-white theme-light:border-slate-300 theme-light:text-slate-900';

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-white/5 bg-black/20 px-3 py-2 theme-light:bg-slate-50 theme-light:border-slate-200">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Trocar em todas as falas</span>
      <select
        value={from}
        disabled={disabled}
        onChange={(e) => setFrom(e.target.value)}
        className={selectClass}
        title="Locutor atual (De)"
      >
        <option value="">De…</option>
        {present.map((sp) => (
          <option key={sp} value={sp}>{sp}</option>
        ))}
      </select>
      <span className="text-xs text-slate-500">→</span>
      <select
        value={to}
        disabled={disabled}
        onChange={(e) => setTo(e.target.value)}
        className={selectClass}
        title="Novo locutor (Para)"
      >
        <option value="">Para…</option>
        {SPEAKER_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <button
        type="button"
        disabled={disabled || !from || !to || from.toLowerCase() === to.toLowerCase()}
        onClick={() => {
          onApply(from, to);
          setFrom('');
          setTo('');
        }}
        className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-50"
      >
        Aplicar a todas
      </button>
    </div>
  );
}
