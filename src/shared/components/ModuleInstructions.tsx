import { useState } from 'react';
import { ChevronDown, ChevronRight, Info } from 'lucide-react';

interface ModuleInstructionsProps {
  /** Passos objetivos de "como usar" o módulo. */
  steps: string[];
  /** Rótulo do cabeçalho recolhível. */
  title?: string;
  /** Chave de localStorage para lembrar aberto/fechado. Omita para não persistir. */
  storageKey?: string;
  /** Estado inicial quando não houver valor salvo. */
  defaultOpen?: boolean;
}

/**
 * Bloco recolhível de "Como usar" exibido abaixo do PageHeader de um módulo.
 * Mantém título/subtítulo intactos e oferece orientação de interface sob demanda,
 * lembrando a preferência aberto/fechado do usuário quando recebe `storageKey`.
 */
export function ModuleInstructions({
  steps,
  title = 'Como usar',
  storageKey,
  defaultOpen = false,
}: ModuleInstructionsProps) {
  const [open, setOpen] = useState<boolean>(() => {
    if (storageKey) {
      const saved = localStorage.getItem(storageKey);
      if (saved !== null) return saved === 'true';
    }
    return defaultOpen;
  });

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (storageKey) localStorage.setItem(storageKey, String(next));
      return next;
    });
  };

  return (
    <section className="rounded-2xl border border-white/10 bg-slate-900/40 theme-light:border-slate-200 theme-light:bg-slate-50">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-2xl px-4 py-3 text-sm font-semibold text-slate-200 transition hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 theme-light:text-slate-700 theme-light:hover:text-slate-900"
      >
        <Info className="h-4 w-4 shrink-0 text-primary-400" />
        <span className="flex-1 text-left">{title}</span>
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0 opacity-60" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 opacity-60" />
        )}
      </button>
      {open && (
        <ol className="list-decimal space-y-1.5 px-5 pb-4 pl-9 text-sm leading-6 text-slate-400 theme-light:text-slate-600">
          {steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
