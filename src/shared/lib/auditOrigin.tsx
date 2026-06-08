import { Bot, User } from 'lucide-react';

export const AUTOMATION_ORIGINS = new Set([
  'automacao',
  'cron',
  'automation_engine',
  'cloud_scheduler',
  'resident_loop',
]);

export type OriginKind = 'auto' | 'manual' | 'unknown';

export function classifyOrigin(criadoPor: string | null | undefined): OriginKind {
  const origem = (criadoPor || '').trim().toLowerCase();
  if (!origem) return 'unknown';
  return AUTOMATION_ORIGINS.has(origem) ? 'auto' : 'manual';
}

export function isAutoOrigin(criadoPor: string | null | undefined): boolean {
  return classifyOrigin(criadoPor) === 'auto';
}

interface OriginBadgeProps {
  criadoPor: string | null | undefined;
  size?: 'sm' | 'md';
  hideUnknown?: boolean;
  hideOnMobile?: boolean;
  /**
   * Quando true, so renderiza o badge se a origem for "auto". Util em listas
   * pre-auditoria (Telefonia/Triagem) onde manual nao precisa ser sinalizado.
   */
  autoOnly?: boolean;
}

const STYLE_BY_KIND: Record<OriginKind, string> = {
  auto: 'border-sky-500/25 bg-sky-500/10 text-sky-300',
  manual: 'border-violet-500/25 bg-violet-500/10 text-violet-300',
  unknown: 'border-slate-500/25 bg-slate-500/10 text-slate-400',
};

const LABEL_BY_KIND: Record<OriginKind, string> = {
  auto: 'Auto',
  manual: 'Manual',
  unknown: 'Origem desc.',
};

const TITLE_BY_KIND: Record<OriginKind, string> = {
  auto: 'Gerada pela rotina automática',
  manual: 'Auditoria manual',
  unknown: 'Origem não informada',
};

export function OriginBadge({
  criadoPor,
  size = 'md',
  hideUnknown = false,
  hideOnMobile = false,
  autoOnly = false,
}: OriginBadgeProps) {
  const kind = classifyOrigin(criadoPor);
  if (autoOnly && kind !== 'auto') return null;
  if (kind === 'unknown' && hideUnknown) return null;

  const sizeClasses =
    size === 'sm'
      ? 'px-1.5 py-0.5 text-[9px]'
      : 'px-2 py-0.5 text-[10px]';
  const iconSize = size === 'sm' ? 'h-2.5 w-2.5' : 'h-3 w-3';
  const Icon = kind === 'auto' ? Bot : User;
  const visibility = hideOnMobile ? 'hidden sm:inline-flex' : 'inline-flex';

  return (
    <span
      className={`${visibility} items-center gap-1 rounded-full border ${sizeClasses} font-bold uppercase tracking-wide ${STYLE_BY_KIND[kind]}`}
      title={TITLE_BY_KIND[kind]}
    >
      <Icon className={`${iconSize} ${kind === 'unknown' ? 'opacity-50' : ''}`} />
      {LABEL_BY_KIND[kind]}
    </span>
  );
}
