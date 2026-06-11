/**
 * App — shell raiz: autenticação, tema, roteamento por view e orquestração da
 * auditoria manual.
 *
 * Fluxo de negócio coberto pelas rotas: triagem/classificação (/classifier) →
 * auditoria (rota padrão sem match, AuditWorkspace) → Arquivos Salvos (/salvos,
 * gate humano onde automáticas e manuais se misturam por design) → aprovação
 * (/supervisor) → fechamento (/fechamento). Telefonia e Automação alimentam a
 * entrada do funil.
 *
 * Responsabilidades:
 * - Sessão por cookie: GET /api/auth/me na carga; POST /api/auth/login e
 *   /api/auth/logout. Role 'supervisor' cai direto no portal; telas admin
 *   (ia, criterios, admin-*) redirecionam não-admin para o portal.
 * - Roteamento: o 1º segmento do path define a view (default 'automacao');
 *   todas as páginas são lazy (code-splitting) com Suspense + LazyErrorBoundary.
 * - Tema dark/light persistido em localStorage e aplicado via classes no <body>.
 * - Auditoria manual: composição useTranscription + useAuditFlow +
 *   useAuditOrchestrator + useAuditResultEditor repassada ao AuditWorkspace.
 *
 * Particularidades:
 * - O Classifier fica SEMPRE montado (display:none fora da rota) para o estado
 *   da triagem sobreviver à navegação entre telas.
 * - A ordem dos gates de loading importa (auth ANTES de criteria) — ver
 *   comentário antes do primeiro return.
 */
import { useState, useEffect, lazy, Suspense } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Sun, Moon } from 'lucide-react';
import { useTranscription } from './features/audit/hooks/useTranscription';
import { useAuditCriteria } from './contexts/AuditCriteriaContext';
import { Sidebar } from './shared/components/Sidebar';
import { AuditWorkspace } from './features/audit/components/AuditWorkspace';
import { apiFetchJson } from './shared/lib/apiClient';
import { useBodyScrollLock } from './shared/hooks/useBodyScrollLock';
import { useAuditResultEditor } from './features/audit/hooks/useAuditResultEditor';
import { useAuditFlow } from './features/audit/hooks/useAuditFlow';
import { useAuditOrchestrator } from './features/audit/hooks/useAuditOrchestrator';
import { LazyErrorBoundary } from './shared/components/LazyErrorBoundary';

// ── Páginas carregadas sob demanda (code-splitting por feature) ──
const Dashboard = lazy(() =>
  import('./features/dashboard/components/Dashboard').then((module) => ({ default: module.Dashboard }))
);
const PerformanceDashboard = lazy(() =>
  import('./features/dashboard/components/PerformanceDashboard').then((module) => ({ default: module.PerformanceDashboard }))
);
const Classifier = lazy(() =>
  import('./features/classifier/components/Classifier').then((module) => ({ default: module.Classifier }))
);
const AuditScoreChart = lazy(() =>
  import('./features/audit/components/AuditScoreChart').then((module) => ({ default: module.AuditScoreChart }))
);
const Settings = lazy(() =>
  import('./features/settings/components/Settings').then((module) => ({ default: module.Settings }))
);
const ColaboradoresPage = lazy(() =>
  import('./features/colaboradores/components/ColaboradoresPage').then((module) => ({ default: module.ColaboradoresPage }))
);
const SupervisorPortal = lazy(() =>
  import('./features/supervisor/components/SupervisorPortal').then((module) => ({ default: module.SupervisorPortal }))
);
const ReviewPage = lazy(() =>
  import('./features/review/components/ReviewPage').then((module) => ({ default: module.ReviewPage }))
);
const SavedFiles = lazy(() =>
  import('./features/saved-files/components/SavedFiles').then((module) => ({ default: module.SavedFiles }))
);
const AIFeedbackPage = lazy(() =>
  import('./features/ai-feedback/components/AIFeedbackPage').then((module) => ({ default: module.AIFeedbackPage }))
);
const AdminCriteriaPage = lazy(() =>
  import('./features/admin/components/AdminCriteriaPage').then((module) => ({ default: module.AdminCriteriaPage }))
);
const AdminSectorAliasesPage = lazy(() =>
  import('./features/admin/components/AdminSectorAliasesPage').then((module) => ({ default: module.AdminSectorAliasesPage }))
);
const SectorManagement = lazy(() =>
  import('./features/admin/components/SectorManagement').then((module) => ({ default: module.SectorManagement }))
);
const AdminAIPromptsPage = lazy(() =>
  import('./features/admin/components/AdminAIPromptsPage').then((module) => ({ default: module.AdminAIPromptsPage }))
);

const TelefoniaPage = lazy(() =>
  import('./features/telefonia/components/TelefoniaPage').then((module) => ({ default: module.TelefoniaPage }))
);
const AutomacaoPage = lazy(() =>
  import('./features/automacao/components/AutomacaoPage').then((module) => ({ default: module.AutomacaoPage }))
);
const FechamentoPage = lazy(() =>
  import('./features/fechamento/components/FechamentoPage').then((module) => ({ default: module.default }))     
);
const PendingDispatch = lazy(() =>
  import('./features/audit/components/PendingDispatch').then((module) => ({ default: module.PendingDispatch }))     
);

type ThemeMode = 'dark' | 'light';

// Preset visual ativo; os legados são removidos do <body> a cada troca de tema.
const ACTIVE_THEME_PRESET_CLASSNAME = 'theme-preset-corporativo';
const LEGACY_THEME_PRESET_CLASSNAMES = [
  'theme-preset-corporativo',
  'theme-preset-opentech',
  'theme-preset-nstech',
];

function App() {
  const {
    processAudio,
    forceProcessAudio,
    reevaluateTranscription,
    regenerateSummaryText,
    isRegeneratingSummary,
    downloadExcel,
    downloadReportDocx,
    downloadReportPdf,
    downloadTranscriptionDocx,
    downloadTranscriptionPdf,
    downloadGestores,
    downloadGestoresPdf,
    saveToDashboard,
    isProcessing,
    auditResult,
    error,
    quotaExceeded,
    actionError,
    isSaved,
    saveState,
    setTranscription,
    setAuditResult,
    resetSavedState,
    clearActionError,
    forceSendToSupervisor,
    discardSavedAudit,
    updateSavedAudit,
    recordAuditCorrections
  } = useTranscription();

  // ── Roteamento: 1º segmento do path = view; default 'automacao' ──
  const location = useLocation();
  const navigate = useNavigate();
  let view = location.pathname.split('/')[1] as any;
  if (!view || view === '') view = 'automacao';

  const setView = (v: string) => navigate(`/${v}`);

  // ── Estado: tema, sessão/role e UI do shell ──
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const savedTheme = localStorage.getItem('nstech-theme');
    return savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : 'dark';
  });
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [userRole, setUserRole] = useState<'admin' | 'supervisor' | null>(null);
  const [loggedUsername, setLoggedUsername] = useState<string>('');
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isLoginSubmitting, setIsLoginSubmitting] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [hasMountedClassifier, setHasMountedClassifier] = useState(false);

  // ── Auditoria manual: critérios + fluxo + orquestração + edição do resultado ──
  const { data: auditData, isLoading: isAuditDataLoading, error: auditDataError, refresh: refreshAuditData } = useAuditCriteria();

  const flow = useAuditFlow({
    sectors: auditData?.sectors || [],
    processAudio,
    clearActionError,
    resetSavedState,
    setTranscription,
    setAuditResult,
  });

  const orchestrator = useAuditOrchestrator({
    flow,
    sectors: auditData?.sectors || [],
    processAudio,
    clearActionError,
  });

  const editor = useAuditResultEditor({
    auditResult,
    selectedAlert: flow.selectedAlert,
    operatorName: flow.operatorName,
    operatorId: flow.operatorId,
    selectedSectorId: flow.selectedSector?.id,
    reevaluateTranscription,
    regenerateSummaryText,
    isRegeneratingSummary,
    setAuditResult,
    updateSavedAudit,
    recordAuditCorrections,
  });

  useBodyScrollLock(isMobileSidebarOpen);

  // Monta o Classifier na 1ª visita à rota e nunca mais desmonta (ver render).
  useEffect(() => {
    if (view === 'classifier' && !hasMountedClassifier) setHasMountedClassifier(true);
  }, [view, hasMountedClassifier]);

  // Aplica o tema no <body> e persiste; 'theme-switching' suprime transições durante a troca.
  useEffect(() => {
    document.body.classList.add('theme-switching');
    document.body.classList.toggle('theme-light', theme === 'light');
    LEGACY_THEME_PRESET_CLASSNAMES.forEach((className) => {
      document.body.classList.remove(className);
    });
    document.body.classList.add(ACTIVE_THEME_PRESET_CLASSNAME);
    localStorage.setItem('nstech-theme', theme);

    const timeoutId = window.setTimeout(() => {
      document.body.classList.remove('theme-switching');
    }, 70);

    return () => {
      window.clearTimeout(timeoutId);
      document.body.classList.remove('theme-switching');
    };
  }, [theme]);

  // Checa a sessão na carga (GET /api/auth/me); supervisor cai direto no portal.
  useEffect(() => {
    let isMounted = true;

    const checkSession = async () => {
      try {
        const data = await apiFetchJson<{ authenticated: boolean; username: string; role: string }>('/api/auth/me', {
          method: 'GET',
          timeoutMs: 2500,
        });
        if (isMounted) {
          if (data.authenticated) {
            setIsAuthenticated(true);
            setUserRole(data.role as 'admin' | 'supervisor');
            setLoggedUsername(data.username);
            if (data.role === 'supervisor') {
              setView('supervisor');
            }
          } else {
            setIsAuthenticated(false);
            setUserRole(null);
            setLoggedUsername('');
          }
        }
      } catch {
        if (isMounted) {
          setIsAuthenticated(false);
        }
      }
    };

    checkSession();

    return () => {
      isMounted = false;
    };
  }, []);

  /** Login por sessão (cookie); refaz o fetch de critérios após autenticar. */
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    const trimmedUsername = loginUsername.trim();
    if (!trimmedUsername || !loginPassword) {
      setLoginError('Informe usuário e senha.');
      return;
    }

    setIsLoginSubmitting(true);
    try {
      const res = await apiFetchJson<{ username: string; role: string }>('/api/auth/login', {
        method: 'POST',
        timeoutMs: 12000,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: trimmedUsername,
          password: loginPassword,
        }),
      });

      setIsAuthenticated(true);
      setUserRole(res.role as 'admin' | 'supervisor');
      setLoggedUsername(res.username);
      setLoginUsername(trimmedUsername);
      setLoginPassword('');
      setLoginError(null);
      // Recarrega os critérios agora que o cookie de sessão existe
      refreshAuditData();
      if (res.role === 'supervisor') {
        setView('supervisor');
      }
    } catch (error) {
      if (
        error instanceof Error
        && (error.message === 'Credenciais inválidas.' || error.message === 'Credenciais invalidas.')
      ) {
        setLoginError('Usuário ou senha inválidos.');
      } else if (error instanceof Error) {
        setLoginError(error.message);
      } else {
        setLoginError('Falha ao conectar com o servidor.');
      }
    } finally {
      setIsLoginSubmitting(false);
    }
  };

  /** Encerra a sessão no backend (best-effort) e limpa o estado local. */
  const handleLogout = async () => {
    try {
      await apiFetchJson<{ success: boolean }>('/api/auth/logout', {
        method: 'POST',
      });
    } catch {
      // best-effort: força o logout local mesmo se a rede falhar
    }
    setIsAuthenticated(false);
    setUserRole(null);
    setLoggedUsername('');
    setView('audit');
    setLoginPassword('');
    setLoginError(null);
  };

  // ── Render: resolve a view atual (telas admin redirecionam supervisor pro portal) ──
  const renderCurrentView = () => {
    if (view === 'supervisor') {
      return (
        <LazyErrorBoundary fallbackLabel="Portal do Supervisor">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando portal...</span></div>}>
            <SupervisorPortal userRole={userRole} />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'dashboard') {
      return (
        <LazyErrorBoundary fallbackLabel="Dashboard">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando dashboard...</span></div>}>
            <Dashboard onNavigateToFiles={() => setView('salvos')} />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'performance') {
      return (
        <LazyErrorBoundary fallbackLabel="Performance">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando performance...</span></div>}>
            <PerformanceDashboard />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'review') {
      return (
        <LazyErrorBoundary fallbackLabel="Contestações">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando contestações...</span></div>}>
            <ReviewPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'colaboradores') {
      return (
        <LazyErrorBoundary fallbackLabel="Operadores">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando operadores...</span></div>}>
            <ColaboradoresPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'settings') {
      return (
        <LazyErrorBoundary fallbackLabel="Configurações">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando configurações...</span></div>}>
            <Settings />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'telefonia') {
      return (
        <LazyErrorBoundary fallbackLabel="Telefonia">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando telefonia...</span></div>}>
            <TelefoniaPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'automacao') {
      return (
        <LazyErrorBoundary fallbackLabel="Automação">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando automação...</span></div>}>
            <AutomacaoPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'fechamento') {
      return (
        <LazyErrorBoundary fallbackLabel="Fechamento">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando fechamento...</span></div>}>
            <FechamentoPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'pending-dispatch') {
      return (
        <LazyErrorBoundary fallbackLabel="Pendentes">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando fila...</span></div>}>
            <PendingDispatch />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'salvos') {
      return (
        <LazyErrorBoundary fallbackLabel="Rascunhos">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando rascunhos...</span></div>}>
            <SavedFiles />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'ia') {
      if (userRole !== 'admin') {
        setTimeout(() => setView('supervisor'), 0);
        return null;
      }
      return (
        <LazyErrorBoundary fallbackLabel="IA">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando IA...</span></div>}>
            <AIFeedbackPage theme={theme} />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'criterios' || view === 'admin') {
      if (userRole !== 'admin') {
        setTimeout(() => setView('supervisor'), 0);
        return null;
      }
      return (
        <LazyErrorBoundary fallbackLabel="Critérios">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando critérios...</span></div>}>
            <AdminCriteriaPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'admin-aliases') {
      if (userRole !== 'admin') {
        setTimeout(() => setView('supervisor'), 0);
        return null;
      }
      return (
        <LazyErrorBoundary fallbackLabel="Apelidos">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando apelidos...</span></div>}>
            <AdminSectorAliasesPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'admin-sectors') {
      if (userRole !== 'admin') {
        setTimeout(() => setView('supervisor'), 0);
        return null;
      }
      return (
        <LazyErrorBoundary fallbackLabel="Setores">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando setores...</span></div>}>
            <SectorManagement />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'admin-prompts') {
      if (userRole !== 'admin') {
        setTimeout(() => setView('supervisor'), 0);
        return null;
      }
      return (
        <LazyErrorBoundary fallbackLabel="Prompts de IA">
          <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando prompts...</span></div>}>
            <AdminAIPromptsPage />
          </Suspense>
        </LazyErrorBoundary>
      );
    }

    if (view === 'classifier') {
      return null; // Classifier fica sempre montado mais abaixo; só alterna via CSS
    }

    return (
      <AuditWorkspace
        AuditScoreChart={AuditScoreChart}
        flow={flow}
        editor={editor}
        sectors={auditData?.sectors || []}
        theme={theme}
        isProcessing={isProcessing}
        auditResult={auditResult}
        error={error}
        quotaExceeded={quotaExceeded}
        onForceProcess={forceProcessAudio}
        actionError={actionError}
        isSaved={isSaved}
        saveState={saveState}
        clearActionError={clearActionError}
        saveToDashboard={saveToDashboard}
        forceSendToSupervisor={forceSendToSupervisor}
        discardSavedAudit={discardSavedAudit}
        downloadExcel={downloadExcel}
        downloadReportDocx={downloadReportDocx}
        downloadReportPdf={downloadReportPdf}
        downloadTranscriptionDocx={downloadTranscriptionDocx}
        downloadTranscriptionPdf={downloadTranscriptionPdf}
        downloadGestores={downloadGestores}
        downloadGestoresPdf={downloadGestoresPdf}
      />
    );
  };

  // O gate de auth PRECISA vir primeiro para evitar race condition:
  // o AuditCriteriaProvider dispara /api/criteria/export já no mount, que
  // retorna 401 enquanto não há cookie de sessão. Se isAuditDataLoading fosse
  // checado antes, o React alternaria rápido entre loading→login→app enquanto
  // o auth/me resolve, causando crashes de removeChild no DOM.
  if (isAuthenticated === null) {
    return (
      <div className="app-theme min-h-[100dvh] text-slate-200 font-sans selection:bg-primary-500/30">
        <div className="login-container">
          <div className="login-box relative overflow-hidden">
            <div className="absolute -top-14 left-1/2 -translate-x-1/2 w-56 h-56 bg-primary-500/20 blur-[90px] rounded-full pointer-events-none"></div>
            <div className="w-8 h-8 mx-auto border-4 border-primary-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm text-slate-400">Verificando sessão...</p>
          </div>
        </div>
      </div>
    );
  }

  if (isAuthenticated && isAuditDataLoading) {
    return (
      <div className="app-theme min-h-[100dvh] text-slate-200 font-sans selection:bg-primary-500/30">
        <div className="login-container">
          <div className="login-box relative overflow-hidden">
            <div className="absolute -top-14 left-1/2 -translate-x-1/2 w-56 h-56 bg-primary-500/20 blur-[90px] rounded-full pointer-events-none"></div>
            <div className="w-8 h-8 mx-auto border-4 border-primary-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm text-slate-400">Carregando critérios de auditoria...</p>
          </div>
        </div>
      </div>
    );
  }

  if (auditDataError && isAuthenticated) {
    return (
      <div className="app-theme min-h-[100dvh] text-slate-200 font-sans selection:bg-primary-500/30">
        <div className="login-container">
          <div className="login-box relative overflow-hidden text-center">
            <h2 className="text-xl font-bold text-red-500 mb-4">Erro Crítico</h2>
            <p className="text-sm text-slate-300 mb-6">{auditDataError}</p>
            <button
              onClick={() => refreshAuditData()}
              className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
            >
              Tentar Novamente
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="app-theme min-h-[100dvh] text-slate-200 font-sans selection:bg-primary-500/30">
        <div className="login-container">
          <div className="login-box relative overflow-hidden theme-light:bg-slate-50 theme-light:border-slate-200 theme-light:shadow-[0_20px_50px_rgba(0,0,0,0.1)]">
            <div className="absolute -top-14 left-1/2 -translate-x-1/2 w-56 h-56 bg-primary-500/20 blur-[90px] rounded-full pointer-events-none theme-light:bg-primary-500/10"></div>

            <img src="/nstech-logo.png" alt="nstech" className="h-12 md:h-14 w-auto mx-auto mb-10 animate-fade-in opacity-95" />

            <div className="space-y-3 mb-9 text-left">
              <p className="page-eyebrow">nstech | Acesso</p>
              <h1 className="page-title">
                Acesso ao <span className="page-title-accent">sistema</span>
              </h1>
              <p className="page-subtitle">Entre para acessar o ambiente de auditoria.</p>
            </div>

            <form onSubmit={handleLogin} className="space-y-6">
              <div className="space-y-2 text-left">
                <label className="text-[11px] uppercase tracking-[0.16em] font-black text-slate-500 ml-1 theme-light:text-slate-600">Usuário</label>
                <input
                  type="text"
                  className="login-input theme-light:bg-white theme-light:border-slate-200 theme-light:text-slate-900"
                  placeholder="Seu usuário"
                  autoComplete="username"
                  required
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                />
              </div>
              <div className="space-y-2 text-left">
                <label className="text-[11px] uppercase tracking-[0.16em] font-black text-slate-500 ml-1 theme-light:text-slate-600">Senha</label>
                <input
                  type="password"
                  className="login-input theme-light:bg-white theme-light:border-slate-200 theme-light:text-slate-900"
                  placeholder="********"
                  autoComplete="current-password"
                  required
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                />
              </div>
              {loginError && (
                <div className="text-xs text-red-400 bg-red-400/10 py-3 rounded-xl border border-red-400/20 animate-fade-in text-center">
                  {loginError}
                </div>
              )}
              <button
                type="submit"
                disabled={isLoginSubmitting}
                className={`btn-primary w-full py-[1.05rem] rounded-xl font-black text-sm tracking-[0.14em] mt-3 ${isLoginSubmitting ? 'opacity-70 cursor-not-allowed' : ''}`}
              >
                {isLoginSubmitting ? 'ACESSANDO...' : 'ENTRAR NO SISTEMA'}
              </button>
            </form>
            <div className="mt-8 flex items-center justify-center">
              <button
                type="button"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                className="theme-toggle theme-light:bg-slate-200 theme-light:border-slate-300"
                aria-label="Alternar tema"
              >
                {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-theme flex min-h-[100dvh] overflow-x-hidden text-slate-200 font-sans selection:bg-primary-500/30 md:h-screen md:overflow-hidden">

      <Sidebar
        view={view}
        setView={setView}
        onLogout={handleLogout}
        mobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        userRole={userRole}
        username={loggedUsername}
      />

      <main className="relative z-10 min-w-0 flex-1 overflow-y-auto overscroll-y-contain">
        <div className="safe-area-top safe-area-bottom app-content-shell">
          <div className="mb-4 flex items-center justify-end gap-3">
            <div className="md:hidden mr-auto">
              <button
                type="button"
                onClick={() => setIsMobileSidebarOpen(true)}
                className="btn-ghost px-4 py-2.5 text-sm font-medium"
              >
                Menu
              </button>
            </div>
            <button
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className={`relative inline-flex h-9 w-16 items-center rounded-full border transition-all duration-100 hover:-translate-y-px ${theme === 'dark'
                ? 'border-white/10 bg-primary-600/60 hover:border-primary-500/40 hover:bg-primary-600/70'
                : 'border-slate-300 bg-slate-200/90 hover:border-primary-500/40 hover:bg-slate-200'
                }`}
              aria-label="Alternar tema"
              title={theme === 'dark' ? 'Alternar para modo claro' : 'Alternar para modo escuro'}
            >
              <span
                className={`absolute left-1 inline-flex h-7 w-7 items-center justify-center rounded-full bg-white shadow-md transition-transform duration-100 ${theme === 'dark' ? 'translate-x-7' : 'translate-x-0'
                  }`}
              >
                {theme === 'dark' ? (
                  <Moon className="h-4 w-4 text-primary-600" />
                ) : (
                  <Sun className="h-4 w-4 text-primary-500" />
                )}
              </span>
            </button>
          </div>
          <div key={view}>
            {renderCurrentView()}
          </div>
          {/* Classifier sempre montado (oculto fora da rota) para preservar o estado da triagem */}
          <div style={{ display: view === 'classifier' ? 'block' : 'none' }}>
            {hasMountedClassifier && (
              <LazyErrorBoundary fallbackLabel="Triagem">
                <Suspense fallback={<div className="glass-panel rounded-2xl p-6 text-slate-400"><span translate="no">Carregando triagem...</span></div>}>
                  <Classifier
                    theme={theme}
                    auditedIndices={orchestrator.auditedIndices}
                    onStartAudit={(audioFile, sectorId, sectorLabel, alertId, alertLabel, opName, opId, fileIndex) => {
                      orchestrator.startFromClassifier(audioFile, sectorId, sectorLabel, alertId, alertLabel, opName, opId, fileIndex, setView);
                    }}
                  />
                </Suspense>
              </LazyErrorBoundary>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
