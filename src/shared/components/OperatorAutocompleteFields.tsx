import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { createPortal } from 'react-dom';
import { apiFetchJson } from '../lib/apiClient';
import { formatOperationalLabel } from '../lib/operationalLabels';
import type { OperatorLookupItem } from '../types/audit';

interface OperatorAutocompleteFieldsProps {
  sectorId?: string | null;
  operatorName: string;
  operatorId: string;
  onOperatorNameChange: (value: string) => void;
  onOperatorIdChange: (value: string) => void;
  onOperatorSelect?: (operator: OperatorLookupItem) => void;
  theme: 'dark' | 'light';
  requiredId?: boolean;
  compact?: boolean;
}

const normalizeValue = (value: string | undefined | null) =>
  (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase();

const resolveOperatorIdentifiers = (operator: OperatorLookupItem) =>
  [
    operator.matricula,
    operator.preferredId,
  ]
    .filter(Boolean)
    .map((value) => normalizeValue(String(value)));

export function OperatorAutocompleteFields({
  sectorId,
  operatorName,
  operatorId,
  onOperatorNameChange,
  onOperatorIdChange,
  onOperatorSelect,
  theme,
  requiredId = false,
}: OperatorAutocompleteFieldsProps) {
  const [operators, setOperators] = useState<OperatorLookupItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSuggestionsOpen, setIsSuggestionsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [suggestionPanelStyle, setSuggestionPanelStyle] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
  } | null>(null);
  const listId = useId().replace(/:/g, '');
  const blurTimeoutRef = useRef<number | null>(null);
  const operatorInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let isMounted = true;

    if (!sectorId) {
      setOperators([]);
      setLoadError(null);
      return () => {
        isMounted = false;
      };
    }

    const abortController = new AbortController();
    const fetchOperators = async () => {
      setIsLoading(true);
      setLoadError(null);
      try {
        const params = new URLSearchParams({
          sector_id: sectorId,
          limit: '250',
          _t: Date.now().toString(),
        });
        const data = await apiFetchJson<OperatorLookupItem[]>(`/api/rh/operadores/lookup?${params.toString()}`, {
          timeoutMs: 10000,
          signal: abortController.signal,
        });
        if (isMounted) {
          setOperators(Array.isArray(data) ? data : []);
        }
      } catch (err: any) {
        if (err.name === 'AbortError') {
          return;
        }
        if (isMounted) {
          setOperators([]);
          setLoadError('Não foi possível carregar os operadores deste setor.');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchOperators();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [sectorId]);

  const matchedOperatorByName = useMemo(() => {
    const normalizedName = normalizeValue(operatorName);
    if (!normalizedName) {
      return null;
    }
    return operators.find((operator) => normalizeValue(operator.name) === normalizedName) ?? null;
  }, [operatorName, operators]);

  const matchedOperatorById = useMemo(() => {
    const normalizedIdentifier = normalizeValue(operatorId);
    if (!normalizedIdentifier) {
      return null;
    }

    return (
      operators.find((operator) =>
        resolveOperatorIdentifiers(operator).includes(normalizedIdentifier)
      ) ?? null
    );
  }, [operatorId, operators]);

  const matchedOperator = matchedOperatorById ?? matchedOperatorByName;

  const filteredOperators = useMemo(() => {
    if (!sectorId) {
      return [];
    }

    const normalizedName = normalizeValue(operatorName);
    const normalizedIdentifier = normalizeValue(operatorId);
    const query = normalizedName || normalizedIdentifier;

    const filtered = operators.filter((operator) => {
      if (!query) {
        return true;
      }

      const searchableValues = [
        operator.name,
        operator.supervisor,
        operator.preferredId,
        operator.idHuawei,
        operator.idTelefonia,
        operator.softphoneNumber,
        operator.matricula,
      ]
        .filter(Boolean)
        .map((value) => normalizeValue(String(value)));

      return searchableValues.some((value) => value.includes(query));
    });

    return filtered.slice(0, 8);
  }, [operators, operatorId, operatorName, sectorId]);

  useEffect(() => {
    if (!operatorId && matchedOperatorByName?.preferredId) {
      onOperatorIdChange(matchedOperatorByName.preferredId);
    }
  }, [matchedOperatorByName?.preferredId, onOperatorIdChange, operatorId]);

  useEffect(() => {
    if (!operatorName && matchedOperatorById?.name) {
      onOperatorNameChange(matchedOperatorById.name);
    }
  }, [matchedOperatorById?.name, onOperatorNameChange, operatorName]);

  useEffect(() => {
    setHighlightedIndex(filteredOperators.length > 0 ? 0 : -1);
  }, [filteredOperators]);

  useEffect(() => {
    if (matchedOperator && onOperatorSelect) {
      onOperatorSelect(matchedOperator);
    }
  }, [matchedOperator, onOperatorSelect]);

  useEffect(() => {
    return () => {
      if (blurTimeoutRef.current !== null) {
        window.clearTimeout(blurTimeoutRef.current);
      }
    };
  }, []);

  const applyOperatorSelection = (operator: OperatorLookupItem) => {
    onOperatorNameChange(operator.name);
    onOperatorIdChange(operator.matricula || operator.preferredId || '');
    setIsSuggestionsOpen(false);
    setHighlightedIndex(-1);
  };

  const openSuggestions = () => {
    if (blurTimeoutRef.current !== null) {
      window.clearTimeout(blurTimeoutRef.current);
    }
    setIsSuggestionsOpen(true);
  };

  const closeSuggestions = () => {
    blurTimeoutRef.current = window.setTimeout(() => {
      setIsSuggestionsOpen(false);
      setHighlightedIndex(-1);
    }, 120);
  };

  const labelClassName = `text-sm font-semibold ml-1 ${theme === 'dark' ? 'text-slate-300' : 'text-slate-700'}`;
  const inputClassName = `w-full p-3 pl-4 rounded-lg outline-none border ${theme === 'dark'
    ? 'glass-input border-white/10 text-white placeholder-slate-500'
    : 'bg-white border-slate-300 text-slate-900 placeholder-slate-400'
    }`;
  const helperClassName = `text-xs mt-2 ${theme === 'dark' ? 'text-slate-500' : 'text-slate-500'}`;
  const suggestionPanelClassName = `touch-scroll overflow-y-auto overscroll-contain rounded-xl border shadow-2xl ${theme === 'dark'
    ? 'border-white/10 bg-slate-950/98'
    : 'border-slate-200 bg-white'
    }`;
  const showSuggestions = !!sectorId && isSuggestionsOpen && filteredOperators.length > 0;

  const updateSuggestionPanelPosition = useCallback(() => {
    const input = operatorInputRef.current;
    if (!input || typeof window === 'undefined') {
      return;
    }

    const rect = input.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const gutter = 16;
    const gap = 8;
    const width = Math.min(rect.width, viewportWidth - gutter * 2);
    const left = Math.min(Math.max(gutter, rect.left), viewportWidth - width - gutter);
    const spaceBelow = viewportHeight - rect.bottom - gutter;
    const spaceAbove = rect.top - gutter;
    const shouldOpenAbove = spaceBelow < 220 && spaceAbove > spaceBelow;
    const availableHeight = shouldOpenAbove ? spaceAbove - gap : spaceBelow - gap;
    const maxHeight = Math.max(160, Math.min(320, availableHeight));
    const top = shouldOpenAbove
      ? Math.max(gutter, rect.top - maxHeight - gap)
      : Math.min(viewportHeight - maxHeight - gutter, rect.bottom + gap);

    setSuggestionPanelStyle({
      top,
      left,
      width,
      maxHeight,
    });
  }, []);

  useLayoutEffect(() => {
    if (!showSuggestions) {
      setSuggestionPanelStyle(null);
      return;
    }

    updateSuggestionPanelPosition();

    const handleReposition = () => updateSuggestionPanelPosition();

    window.addEventListener('resize', handleReposition);
    window.addEventListener('scroll', handleReposition, true);

    return () => {
      window.removeEventListener('resize', handleReposition);
      window.removeEventListener('scroll', handleReposition, true);
    };
  }, [showSuggestions, updateSuggestionPanelPosition]);

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="relative space-y-3">
        <label className={labelClassName}>Nome do operador</label>
        <input
          ref={operatorInputRef}
          type="text"
          className={inputClassName}
          placeholder={sectorId ? 'Digite para buscar no setor selecionado' : 'Selecione um setor primeiro'}
          value={operatorName}
          onChange={(event) => onOperatorNameChange(event.target.value)}
          onFocus={openSuggestions}
          onBlur={closeSuggestions}
          onKeyDown={(event) => {
            if (!filteredOperators.length) {
              if (event.key === 'Escape') {
                setIsSuggestionsOpen(false);
              }
              return;
            }

            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setIsSuggestionsOpen(true);
              setHighlightedIndex((currentIndex) => (currentIndex + 1) % filteredOperators.length);
            }

            if (event.key === 'ArrowUp') {
              event.preventDefault();
              setIsSuggestionsOpen(true);
              setHighlightedIndex((currentIndex) => (
                currentIndex <= 0 ? filteredOperators.length - 1 : currentIndex - 1
              ));
            }

            if (event.key === 'Enter' && highlightedIndex >= 0) {
              event.preventDefault();
              applyOperatorSelection(filteredOperators[highlightedIndex]);
            }

            if (event.key === 'Escape') {
              setIsSuggestionsOpen(false);
              setHighlightedIndex(-1);
            }
          }}
          autoComplete="off"
          disabled={!sectorId && !operatorName}
          role="combobox"
          aria-expanded={showSuggestions}
          aria-controls={`${listId}-operators`}
          aria-autocomplete="list"
        />
        {showSuggestions && suggestionPanelStyle && typeof document !== 'undefined'
          ? createPortal(
            <div
              id={`${listId}-operators`}
              role="listbox"
              className={suggestionPanelClassName}
              style={{
                position: 'fixed',
                top: suggestionPanelStyle.top,
                left: suggestionPanelStyle.left,
                width: suggestionPanelStyle.width,
                maxHeight: suggestionPanelStyle.maxHeight,
                zIndex: 140,
              }}
            >
              {filteredOperators.map((operator, index) => {
                const isHighlighted = index === highlightedIndex;
                const metaLabel = [
                  operator.preferredId ? `${operator.preferredIdSource}: ${operator.preferredId}` : '',
                  (operator.idHuawei || operator.idTelefonia)
                    ? `ID Huawei: ${operator.idHuawei || operator.idTelefonia}`
                    : '',
                  operator.supervisor ? `Supervisor: ${operator.supervisor}` : '',
                ]
                  .filter(Boolean)
                  .join(' • ');

                return (
                  <button
                    key={`${operator.name}-${operator.preferredId || operator.softphoneNumber || 'sem-id'}`}
                    type="button"
                    role="option"
                    aria-selected={isHighlighted}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => applyOperatorSelection(operator)}
                    className={`block w-full px-4 py-3 text-left transition-colors ${isHighlighted
                      ? theme === 'dark'
                        ? 'bg-primary-500/15 text-white'
                        : 'bg-primary-50 text-slate-900'
                      : theme === 'dark'
                        ? 'text-slate-200 hover:bg-white/5'
                        : 'text-slate-700 hover:bg-slate-50'
                      }`}
                  >
                    <div className="font-medium">{operator.name}</div>
                    <div className={`mt-1 text-xs ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>
                      {metaLabel || 'Operador sem identificador adicional.'}
                    </div>
                  </button>
                );
              })}
            </div>,
            document.body,
          )
          : null}
        <div className={helperClassName}>
          {isLoading ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" />
              Carregando operadores do setor...
            </span>
          ) : loadError ? (
            loadError
          ) : !sectorId ? (
            'Selecione o setor para carregar a base de operadores.'
          ) : matchedOperator ? (
            <>
              ID preenchido automaticamente via {matchedOperator.preferredIdSource || 'base interna'}
              {matchedOperator.supervisor ? ` • Supervisor: ${matchedOperator.supervisor}` : ''}
              {matchedOperator.escala ? ` • Escala: ${formatOperationalLabel(matchedOperator.escala) || matchedOperator.escala}` : ''}
            </>
          ) : operators.length > 0 ? (
            `${operators.length} operadores disponíveis neste setor.`
          ) : (
            'Nenhum operador auditável neste setor. Cadastre ou ative no módulo Operadores.'
          )}
        </div>
      </div>

      <div className="space-y-3">
        <label className={labelClassName}>
          Matrícula
          {requiredId && <span className="text-red-400"> *</span>}
        </label>
        <input
          type="text"
          className={inputClassName}
          placeholder="Ex: 4218"
          value={operatorId}
          onChange={(event) => onOperatorIdChange(event.target.value)}
        />
        <div className={helperClassName}>
          {matchedOperator?.matricula
            ? `Matrícula: ${matchedOperator.matricula}${matchedOperator.idHuawei ? ` • ID Huawei: ${matchedOperator.idHuawei}` : ''}`
            : 'Aceita apenas matrícula do operador.'}
        </div>
      </div>
    </div>
  );
}
