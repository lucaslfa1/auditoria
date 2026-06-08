import { CheckCircle2, Circle, Disc3 } from 'lucide-react';

interface AuditStepRailProps {
  currentStep: number;
  auditType: 'audio' | 'pdf';
  selectedSectorLabel?: string | null;
  selectedAlertLabel?: string | null;
}

const steps = [
  {
    id: 1,
    eyebrow: 'Passo 1',
    title: 'Contexto',
    description: 'Defina setor, alerta e operador antes de iniciar a análise.',
  },
  {
    id: 2,
    eyebrow: 'Passo 2',
    title: 'Arquivo',
    description: 'Envie o material certo para evitar retrabalho na auditoria.',
  },
  {
    id: 3,
    eyebrow: 'Passo 3',
    title: 'Revisão',
    description: 'Edite, exporte e publique o resultado final com controle.',
  },
];

export function AuditStepRail({
  currentStep,
  auditType,
  selectedSectorLabel,
  selectedAlertLabel,
}: AuditStepRailProps) {
  return (
    <div className="mb-6 rounded-2xl border border-white/10 bg-slate-950/45 p-4 shadow-[0_18px_40px_rgba(7,17,34,0.16)] backdrop-blur-sm md:p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary-400">
            Fluxo de Auditoria
          </p>
          <h2 className="section-title-lg mt-1">
            Pipeline {auditType === 'audio' ? 'de ligação' : 'documental'}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-400 theme-light:text-slate-600">
            O fluxo foi separado para reduzir erros operacionais: primeiro contexto, depois envio do arquivo e, por fim, revisão e distribuição.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full border border-primary-500/20 bg-primary-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-primary-300">
            {auditType === 'audio' ? 'Áudio' : 'Documento'}
          </span>
          {selectedSectorLabel ? (
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-slate-300 theme-light:text-slate-700">
              {selectedSectorLabel}
            </span>
          ) : null}
          {selectedAlertLabel ? (
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-slate-300 theme-light:text-slate-700">
              {selectedAlertLabel}
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {steps.map((step) => {
          const isCompleted = currentStep > step.id;
          const isActive = currentStep === step.id;
          const Icon = isCompleted ? CheckCircle2 : isActive ? Disc3 : Circle;

          return (
            <div
              key={step.id}
              className={`rounded-2xl border p-4 transition-colors ${
                isActive
                  ? 'border-primary-500/35 bg-primary-500/10'
                  : isCompleted
                    ? 'border-emerald-500/30 bg-emerald-500/10'
                    : 'border-white/10 bg-slate-900/45'
              }`}
            >
              <div className="flex items-center gap-3">
                <div
                  className={`rounded-full border p-2 ${
                    isActive
                      ? 'border-primary-500/40 text-primary-300'
                      : isCompleted
                        ? 'border-emerald-500/35 text-emerald-300'
                        : 'border-white/10 text-slate-500'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    {step.eyebrow}
                  </p>
                  <p className="section-title-sm">
                    {step.title}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-400 theme-light:text-slate-600">
                {step.description}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
