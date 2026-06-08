const WHOLE_LABEL_OVERRIDES: Record<string, string> = {
  BAS: 'BAS',
  UTI: 'UTI',
  LP: 'LP',
  G2L: 'G2L',
  FENIX: 'Fenix',
  TRANSFERENCIA: 'Transferência',
  DISTRIBUICAO: 'Distribuição',
  LOGISTICA: 'Logística',
  'LOGISTICA UNILEVER': 'Logística Unilever',
  RASTREAMENTO: 'Rastreamento',
  'CELULA ATENDIMENTO': 'Célula de Atendimento',
  'OPERACAO TABORDA': 'Operação Taborda',
  'RISK MONITORING': 'Monitoramento de Riscos',
  CHECKLIST: 'Checklist',
  CADASTRO: 'Cadastro',
  MONDELEZ: 'Mondelez',
  TREINAMENTO: 'Treinamento',
};

const PRESERVE_UPPERCASE = new Set(['BAS', 'UTI', 'LP', 'G2L', 'RH', 'TI', 'IA', 'URA', 'CPF']);
const TITLE_CASE_OVERRIDES: Record<string, string> = {
  FENIX: 'Fenix',
};

function stripFallbackSuffix(value: string): string {
  return value.replace(/\s*(?:[/-]\s*)?ou\s+padr[aã]o\b/giu, '').replace(/\s+/g, ' ').trim();
}

function buildOperationalKey(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[_-]+/g, ' ')
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase();
}

export function getOperationalFilterKey(value: string | null | undefined): string {
  const rawValue = typeof value === 'string' ? value : value == null ? '' : String(value);
  const cleanedValue = stripFallbackSuffix(rawValue);

  if (!cleanedValue) {
    return '';
  }

  return buildOperationalKey(cleanedValue);
}

export function formatOperationalLabel(value: string | null | undefined): string {
  const rawValue = typeof value === 'string' ? value : value == null ? '' : String(value);
  const operationalKey = getOperationalFilterKey(rawValue);
  if (!operationalKey) {
    return '';
  }

  const wholeLabel = WHOLE_LABEL_OVERRIDES[operationalKey];
  if (wholeLabel) {
    return wholeLabel;
  }

  return operationalKey
    .split(' ')
    .filter(Boolean)
    .map((part) => {
      if (TITLE_CASE_OVERRIDES[part]) {
        return TITLE_CASE_OVERRIDES[part];
      }
      if (PRESERVE_UPPERCASE.has(part)) {
        return part;
      }
      return part.charAt(0) + part.slice(1).toLowerCase();
    })
    .join(' ');
}
