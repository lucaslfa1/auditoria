import { logToTelemetry } from './telemetry';

const API_BASE_URL = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_URL || '');
const LOCAL_DEV_BASES = [
    'http://localhost:8080',
    'http://localhost:8081',
    'http://127.0.0.1:8080',
    'http://127.0.0.1:8081',
];

export type ApiRequestInit = RequestInit & {
    timeoutMs?: number;
};

export class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}

// Global Event Emitter for API Errors
export const apiErrorEventTarget = new EventTarget();

const emitApiError = (error: ApiError, path: string) => {
    // Only emit global errors for 5xx or network errors (0), not for expected business validation errors (4xx)
    if (error.status >= 500 || error.status === 0 || error.status === 408) {
        apiErrorEventTarget.dispatchEvent(new CustomEvent('apiError', { 
            detail: { message: error.message, status: error.status, path } 
        }));
        logToTelemetry('error', `API Request Failed: [${error.status}] ${path} - ${error.message}`);
    }
};

const isAbsoluteUrl = (path: string) => path.startsWith('http://') || path.startsWith('https://');

const buildUrl = (path: string, baseUrl: string = API_BASE_URL) => {
    if (path.startsWith('http://') || path.startsWith('https://')) {
        return path;
    }
    if (!baseUrl) {
        return path;
    }
    return `${baseUrl}${path}`;
};

const buildCandidateUrls = (path: string): string[] => {
    const primary = buildUrl(path);
    const urls: string[] = [];
    const pushUnique = (url: string) => {
        if (!urls.includes(url)) {
            urls.push(url);
        }
    };

    pushUnique(primary);

    if (!import.meta.env.DEV || isAbsoluteUrl(path)) {
        return urls;
    }

    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    pushUnique(normalizedPath);

    for (const base of LOCAL_DEV_BASES) {
        pushUnique(buildUrl(normalizedPath, base));
    }

    return urls;
};

const fetchWithTimeout = async (url: string, fetchInit: RequestInit, timeoutMs: number): Promise<Response> => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    // If the caller provided an external signal (e.g. for unmount cleanup),
    // forward its abort to our internal controller so both timeout and external
    // cancellation are honoured.
    const externalSignal = fetchInit.signal;
    if (externalSignal) {
        if (externalSignal.aborted) {
            controller.abort();
        } else {
            externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
        }
    }

    try {
        return await fetch(url, {
            credentials: 'include',
            ...fetchInit,
            signal: controller.signal,
        });
    } finally {
        window.clearTimeout(timeoutId);
    }
};

const toApiError = async (response: Response) => {
    let message = `Request failed (${response.status})`;
    try {
        const data = await response.json();
        if (typeof data?.detail === 'string' && data.detail.trim()) {
            message = data.detail;
        }
    } catch {
        // Keep fallback message when response body is not JSON.
    }
    return new ApiError(message, response.status);
};

const hasContentTypeHeader = (headers: HeadersInit | undefined): boolean => {
    if (!headers) return false;
    if (headers instanceof Headers) return headers.has('Content-Type');
    if (Array.isArray(headers)) return headers.some(([k]) => k.toLowerCase() === 'content-type');
    return Object.keys(headers).some((k) => k.toLowerCase() === 'content-type');
};

const isJsonBodyCandidate = (body: BodyInit | null | undefined): boolean => {
    if (typeof body !== 'string') return false;
    if (body.length === 0) return false;
    const head = body.trimStart()[0];
    return head === '{' || head === '[' || head === '"';
};

export const apiFetch = async (path: string, init: RequestInit = {}) => {
    const { timeoutMs = 900000, ...fetchInit } = init as ApiRequestInit;
    // Auto-add Content-Type: application/json when body is a JSON string and
    // caller didn't specify a content type. Without this, FastAPI/Pydantic
    // rejects the request as 422 dict_type. Preserves FormData/Blob uploads
    // (typeof body !== 'string'), so multipart auto-detection by the browser
    // still works.
    if (isJsonBodyCandidate(fetchInit.body) && !hasContentTypeHeader(fetchInit.headers)) {
        fetchInit.headers = {
            ...(fetchInit.headers as Record<string, string> | undefined),
            'Content-Type': 'application/json',
        };
    }
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const requestUrls = buildCandidateUrls(path);

    for (const requestUrl of requestUrls) {
        try {
            const response = await fetchWithTimeout(requestUrl, fetchInit, timeoutMs);

            if (!response.ok) {
                const shouldTryFallback =
                    import.meta.env.DEV &&
                    requestUrl === normalizedPath &&
                    (response.status === 404 || response.status === 502 || response.status === 503);
                if (shouldTryFallback) {
                    continue;
                }
                const apiErr = await toApiError(response);
                emitApiError(apiErr, path);
                throw apiErr;
            }

            return response;
        } catch (error) {
            if (error instanceof ApiError) {
                // If it was already emitted above, this is just passing it up, but if it came from a lower level, emit it
                throw error;
            }
            if (error instanceof DOMException && error.name === 'AbortError') {
                const timeoutErr = new ApiError('Request timeout. Please try again.', 408);
                emitApiError(timeoutErr, path);
                throw timeoutErr;
            }
        }
    }

    const finalErr = new ApiError('Unable to connect to server.', 0);
    emitApiError(finalErr, path);
    throw finalErr;
};

export const apiFetchJson = async <T>(path: string, init: ApiRequestInit = {}) => {
    const response = await apiFetch(path, init);
    return response.json() as Promise<T>;
};

export const apiFetchBlob = async (path: string, init: ApiRequestInit = {}) => {
    const response = await apiFetch(path, init);
    return response.blob();
};
