export interface AuditCriterion {
    id: string;
    label: string;
    weight: number;
    description?: string;
}

export interface AuditAlert {
    id: string;
    label: string;
    context: string;
    criteria: AuditCriterion[];
}

export interface AuditSector {
    id: string;
    label: string;
    alerts: AuditAlert[];
}

export interface OperatorLookupItem {
    name: string;
    preferredId: string;
    preferredIdSource: string;
    supervisor?: string;
    escala?: string;
    sectorId?: string;
    displaySector?: string;
    matricula?: string;
    idHuawei?: string;
    idTelefonia?: string;
    softphoneNumber?: string;
    telefoniaAccount?: string;
    organizacaoTelefonia?: string;
    tipoAgente?: string;
    statusTelefonia?: string;
    auditavel?: boolean;
}

export interface AuditResultDetail {
    criterionId: string;
    label: string;
    status: 'pass' | 'fail';
    weight: number;
    deflator?: number | null;
    obtainedScore: number;
    comment: string;
    timestamp?: string;
    evidence_text?: string;
    evidence_validation?: {
        status?: string;
        matched?: boolean;
        method?: string;
    } | null;
}

export interface TranscriptionSegment {
    start: string;
    end: string;
    text: string;
}

export interface SentimentSentence {
    text: string;
    sentiment: string;
    confidenceScores?: Record<string, number>;
}

export interface SentimentResult {
    overall: string;
    confidenceScores?: Record<string, number>;
    sentences?: SentimentSentence[];
}

export interface AudioQualityDetails {
    duration_seconds?: number;
    average_dbfs?: number;
    max_dbfs?: number;
    sample_rate?: number;
    channels?: number;
    silence_ratio?: number;
    bitrate_kbps?: number;
}

export interface AudioQualityResult {
    score: number;
    quality?: 'boa' | 'regular' | 'baixa' | 'muito_baixa' | 'desconhecida';
    notes?: string[];
    details?: AudioQualityDetails;
    review_recommended?: boolean;
    review_priority?: 'low' | 'medium' | 'high' | string;
    review_reasons?: string[];
    diarization?: {
        score?: number;
        quality?: string;
        swap_risk?: string;
        raw_speaker_count?: number;
        human_segment_count?: number;
        telephony_segment_count?: number;
        notes?: string[];
    };
    transcription_quality?: {
        score?: number;
        audit_readiness?: 'ready' | 'review_required' | 'blocked' | string;
        review_recommended?: boolean;
        reasons?: string[];
        metrics?: Record<string, unknown>;
    };
    evidence_quality?: {
        quality?: string;
        review_recommended?: boolean;
        reason?: string;
        evaluable_details?: number;
        matched_evidence?: number;
        missing_evidence?: number;
        missing_criteria_count?: number;
        expected_details?: number;
        missing_criteria_ids?: string[];
        unverified_evidence?: number;
        matched_ratio?: number;
    };
    transcription_provider?: {
        selected_strategy?: string;
        selected_provider?: string;
        selected_reason?: string;
        attempts?: Array<Record<string, unknown>>;
    };
}

export interface AuditResult {
    score: number;
    maxPossibleScore: number;
    summary: string;
    ai_feedback?: string;
    details: AuditResultDetail[];
    transcription: TranscriptionSegment[];
    fatal_flags?: string[];
    source_type?: 'audio' | 'pdf';
    audit_scope?: 'call_quality';
    sentiment?: SentimentResult | null;
    audio_quality?: AudioQualityResult | null;
    audio_date?: string | null;
    operatorName?: string;
    operatorId?: string;
    timestamp?: string;
    input_hash?: string | null;
}
