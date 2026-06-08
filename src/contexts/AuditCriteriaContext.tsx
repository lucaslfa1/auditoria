import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiFetchJson, ApiError } from '../shared/lib/apiClient';

export interface Criterion {
    id: string; // The `chave` identifier (e.g. 'identificacao', 'senha')
    label: string;
    weight: number;
    description?: string;
    type?: string;
    deflator?: number;
}

export interface Alert {
    id: string; // the string ID like '4.1.1'
    label: string;
    context: string;
    criteria: Criterion[];
}

export interface Sector {
    id: string;
    label: string;
    description: string;
    alerts: Alert[];
}

export interface AuditCriteriaData {
    sectors: Sector[];
}

interface AuditCriteriaContextType {
    data: AuditCriteriaData | null;
    isLoading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
}

const AuditCriteriaContext = createContext<AuditCriteriaContextType | undefined>(undefined);

export function AuditCriteriaProvider({ children }: { children: React.ReactNode }) {
    const [data, setData] = useState<AuditCriteriaData | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchCriteria = async () => {
        try {
            setIsLoading(true);
            setError(null);
            // Calls the backend endpoint designed to return backwards-compatible JSON structure
            const response = await apiFetchJson('/api/criteria/export');
            setData(response as AuditCriteriaData);
        } catch (err: any) {
            // 401 = not authenticated yet — silently ignore so login page can render
            const is401 = (err instanceof ApiError && err.status === 401) || err?.status === 401;
            if (is401) {
                setData(null);
            } else {
                console.error('Failed to fetch audit criteria:', err);
                setError(err.message || 'Erro ao carregar os critérios de auditoria.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchCriteria();
    }, []);

    return (
        <AuditCriteriaContext.Provider value={{ data, isLoading, error, refresh: fetchCriteria }}>
            {children}
        </AuditCriteriaContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuditCriteria() {
    const context = useContext(AuditCriteriaContext);
    if (context === undefined) {
        throw new Error('useAuditCriteria must be used within an AuditCriteriaProvider');
    }
    return context;
}
