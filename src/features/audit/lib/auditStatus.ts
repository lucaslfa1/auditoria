import type { AuditResultDetail } from '../types/audit';

export type AuditStatus = AuditResultDetail['status'];

const AUDIT_STATUS_LABELS: Record<AuditStatus, string> = {
  pass: 'Atende',
  fail: 'Não atende',
};

const AUDIT_STATUS_BADGE_CLASSES: Record<AuditStatus, string> = {
  pass: 'bg-green-500/10 text-green-400 border border-green-500/20',
  fail: 'bg-red-500/10 text-red-400 border border-red-500/20',
};

export function getAuditStatusLabel(status: AuditStatus): string {
  return AUDIT_STATUS_LABELS[status] || 'Atende';
}

export function getAuditStatusBadgeClass(status: AuditStatus): string {
  return AUDIT_STATUS_BADGE_CLASSES[status] || AUDIT_STATUS_BADGE_CLASSES.pass;
}

export function normalizeAuditStatus(rawStatus: string): AuditStatus | null {
  const normalized = rawStatus.trim().toLowerCase();

  switch (normalized) {
    case 'pass':
    case 'passou':
    case 'atende':
    case 'conforme':
    case 'na':
    case 'n/a':
    case 'nao se aplica':
    case 'não se aplica':
      return 'pass';
    case 'fail':
    case 'falhou':
    case 'nao atende':
    case 'não atende':
    case 'reprovado':
    case 'partial':
    case 'parcial':
    case 'atende parcialmente':
      return 'fail';
    default:
      return null;
  }
}
