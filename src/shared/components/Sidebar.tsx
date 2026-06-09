import * as React from 'react';
import {
  AudioLines,
  Bot,
  Brain,
  Building2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ClipboardCheck,
  Eye,
  FileText,
  LayoutDashboard,
  Lightbulb,
  Link,
  LogOut,
  MessageSquare,
  PhoneCall,
  Scale,
  Settings,
  Users
} from 'lucide-react';
import { useDialogFocusTrap } from '../hooks/useDialogFocusTrap';

type ViewType = 'audit' | 'dashboard' | 'classifier' | 'colaboradores' | 'settings' | 'supervisor' | 'review' | 'salvos' | 'ia' | 'criterios' | 'admin' | 'admin-aliases' | 'admin-sectors' | 'admin-prompts' | 'telefonia' | 'automacao' | 'fechamento' | 'pending-dispatch';

interface SidebarProps {
  view: ViewType;
  setView: (view: ViewType) => void;
  onLogout: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  userRole: 'admin' | 'supervisor' | null;
  username: string;
}

export function Sidebar({
  view,
  setView,
  onLogout,
  mobileOpen,
  onCloseMobile,
  userRole,
  username,
}: SidebarProps) {
  const drawerRef = React.useRef<HTMLElement | null>(null);
  const [userPanelOpen, setUserPanelOpen] = React.useState(true);
  const [isCollapsedState, setIsCollapsedState] = React.useState(() => localStorage.getItem('nstech-sidebar-collapsed') === 'true');
  const [aiMenuOpen, setAiMenuOpen] = React.useState(false);

  useDialogFocusTrap(drawerRef, mobileOpen, {
    onDismiss: onCloseMobile,
    initialFocusSelector: '[data-autofocus="true"]',
  });

  const handleViewChange = (nextView: ViewType) => {
    setView(nextView);
    onCloseMobile();
  };

  const toggleCollapse = () => {
    const nextState = !isCollapsedState;
    setIsCollapsedState(nextState);
    localStorage.setItem('nstech-sidebar-collapsed', String(nextState));
  };

  const isAdmin = userRole === 'admin';
  const isSupervisor = userRole === 'supervisor';
  const isCriteriaView = view === 'criterios' || view === 'admin';

  const navItemClass = (isActive: boolean, collapsed: boolean) =>
    `w-full flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3.5 px-[1.05rem]'} py-[0.95rem] rounded-2xl text-[15px] font-semibold transition-all duration-300 border ${isActive
      ? 'bg-slate-800 text-primary-300 border-primary-500/35 shadow-[0_10px_24px_rgba(201,63,15,0.14)] theme-light:bg-white theme-light:text-primary-500 theme-light:border-primary-500/25 theme-light:shadow-[0_10px_22px_rgba(201,63,15,0.12)]'
      : 'bg-slate-900 text-slate-300 border-slate-800 hover:text-slate-100 hover:bg-slate-800 hover:border-slate-700 theme-light:bg-slate-200 theme-light:text-slate-700 theme-light:border-slate-300 theme-light:hover:bg-white theme-light:hover:text-slate-900 theme-light:hover:border-slate-400'
    }`;

  const navIconClass = (isActive: boolean) =>
    isActive
      ? 'text-primary-400 theme-light:text-primary-500 shrink-0'
      : 'text-slate-500 theme-light:text-slate-600 shrink-0';

  const renderNavContent = (collapsed: boolean) => (
    <>
      <div className={`p-7 pb-6 flex flex-col gap-2 border-b border-white/5 relative transition-all duration-300 ${collapsed ? 'px-4 items-center justify-center' : ''}`}>
        <div className={`flex items-center w-full ${collapsed ? 'justify-center mb-1' : 'justify-between'}`}>
          {!collapsed && <img src="/nstech-logo.png" alt="nstech" className="h-9 w-auto opacity-95" />}
          {collapsed && (
            <div className="h-8 w-8 bg-primary-500 rounded-lg flex items-center justify-center font-black text-white shadow-lg mx-auto">
              N
            </div>
          )}
          <button
            type="button"
            onClick={onCloseMobile}
            data-autofocus="true"
            aria-label="Fechar menu lateral"
            className="md:hidden px-3 py-2 rounded-xl text-sm font-medium text-slate-400 hover:text-white hover:bg-white/5"
          >
            Fechar
          </button>
        </div>
        {!collapsed && (
          <div className="mt-3 flex items-center gap-2.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary-500 shadow-[0_0_10px_rgba(201,63,15,0.8)] shrink-0" />
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500 leading-none truncate block">
              Auditoria de qualidade
            </p>
          </div>
        )}
      </div>

      <nav className={`touch-scroll flex-1 overflow-y-auto overscroll-y-contain py-6 space-y-2 ${collapsed ? 'px-2' : 'px-4'}`}>
        {/* --- SEÇÃO AUTOMAÇÃO (Admin Only) --- */}
        {isAdmin && (
          <>
            {!collapsed && (
              <div className="mb-2 px-[1.05rem]">
                <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-primary-500/80 leading-none truncate block">
                  Automação
                </p>
              </div>
            )}
            <button onClick={() => handleViewChange('automacao')} className={navItemClass(view === 'automacao', collapsed)} title={collapsed ? 'Automação' : ''}>
              <Bot size={20} className={navIconClass(view === 'automacao')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Automação de Processos</span>}
              {!collapsed && <span className="md:hidden block">Automação de Processos</span>}
            </button>
          </>
        )}

        {/* --- SEÇÃO OPERAÇÃO (Admin Only = Auditor) --- */}
        {isAdmin && (
          <>
            {!collapsed && (
              <div className="mt-4 mb-2 px-[1.05rem]">
                <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500/80 leading-none truncate block">
                  Operação
                </p>
              </div>
            )}
            {collapsed && <div className="mt-4 mb-2 border-t border-white/5 mx-2" />}

            <button onClick={() => handleViewChange('telefonia')} className={navItemClass(view === 'telefonia', collapsed)} title={collapsed ? 'Telefonia' : ''}>
              <PhoneCall size={20} className={navIconClass(view === 'telefonia')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Telefonia</span>}
              {!collapsed && <span className="md:hidden block">Telefonia</span>}
            </button>

            <button onClick={() => handleViewChange('classifier')} className={navItemClass(view === 'classifier', collapsed)} title={collapsed ? 'Triagem' : ''}>
              <AudioLines size={20} className={navIconClass(view === 'classifier')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Triagem</span>}
              {!collapsed && <span className="md:hidden block">Triagem</span>}
            </button>

            <button onClick={() => handleViewChange('audit')} className={navItemClass(view === 'audit', collapsed)} title={collapsed ? 'Auditoria' : ''}>
              <ClipboardCheck size={20} className={navIconClass(view === 'audit')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Auditoria</span>}
              {!collapsed && <span className="md:hidden block">Auditoria</span>}
            </button>

            <button onClick={() => handleViewChange('salvos')} className={navItemClass(view === 'salvos', collapsed)} title={collapsed ? 'Arquivos' : ''}>
              <FileText size={20} className={navIconClass(view === 'salvos')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Arquivos</span>}
              {!collapsed && <span className="md:hidden block">Arquivos</span>}
            </button>
          </>
        )}

        {/* --- SEÇÃO SUPERVISÃO (Admin, Supervisor) --- */}
        {!collapsed && (
          <div className="mt-4 mb-2 px-[1.05rem]">
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500/80 leading-none truncate block">
              Supervisão
            </p>
          </div>
        )}
        {collapsed && <div className="mt-4 mb-2 border-t border-white/5 mx-2" />}

        <button onClick={() => handleViewChange('supervisor')} className={navItemClass(view === 'supervisor', collapsed)} title={collapsed ? 'Supervisão' : ''}>
          <Eye size={20} className={navIconClass(view === 'supervisor')} />
          {!collapsed && <span className="truncate block hidden md:block lg:block">Supervisão</span>}
          {!collapsed && <span className="md:hidden block">Supervisão</span>}
        </button>

        {(isAdmin || isSupervisor) && (
          <>
            <button onClick={() => handleViewChange('review')} className={navItemClass(view === 'review', collapsed)} title={collapsed ? 'Contestações' : ''}>
              <Scale size={20} className={navIconClass(view === 'review')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Contestações</span>}
              {!collapsed && <span className="md:hidden block">Contestações</span>}
            </button>

            <button onClick={() => handleViewChange('colaboradores')} className={navItemClass(view === 'colaboradores', collapsed)} title={collapsed ? 'Operadores' : ''}>
              <Users size={20} className={navIconClass(view === 'colaboradores')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Operadores</span>}
              {!collapsed && <span className="md:hidden block">Operadores</span>}
            </button>

            {isAdmin && (
              <>
                <button onClick={() => handleViewChange('admin-sectors')} className={navItemClass(view === 'admin-sectors', collapsed)} title={collapsed ? 'Setores' : ''}>
                  <Building2 size={20} className={navIconClass(view === 'admin-sectors')} />
                  {!collapsed && <span className="truncate block hidden md:block lg:block">Setores</span>}
                  {!collapsed && <span className="md:hidden block">Setores</span>}
                </button>

                <button onClick={() => handleViewChange('criterios')} className={navItemClass(isCriteriaView, collapsed)} title={collapsed ? 'Critérios' : ''}>
                  <ClipboardCheck size={20} className={navIconClass(isCriteriaView)} />
                  {!collapsed && <span className="truncate block hidden md:block lg:block">Critérios</span>}
                  {!collapsed && <span className="md:hidden block">Critérios</span>}
                </button>
              </>
            )}
          </>
        )}

        {/* --- SEÇÃO INTELIGÊNCIA ARTIFICIAL (Admin Only) --- */}
        {isAdmin && (
          <div className="flex flex-col gap-1">
            <button
              onClick={() => {
                if (collapsed) {
                  toggleCollapse();
                  setAiMenuOpen(true);
                } else {
                  setAiMenuOpen(!aiMenuOpen);
                }
              }}
              className={navItemClass(['ia', 'admin-aliases', 'admin-prompts'].includes(view), collapsed)}
              title={collapsed ? 'Inteligência Artificial' : ''}
              aria-expanded={aiMenuOpen}
              aria-controls="ai-submenu"
            >
              <Brain size={20} className={navIconClass(['ia', 'admin-aliases', 'admin-prompts'].includes(view))} />
              {!collapsed && (
                <>
                  <span className="truncate flex-1 text-left hidden md:block lg:block">Inteligência Artificial</span>
                  <span className="md:hidden block flex-1 text-left">Inteligência Artificial</span>
                  {aiMenuOpen ? <ChevronUp size={16} className="opacity-50" /> : <ChevronDown size={16} className="opacity-50" />}
                </>
              )}
            </button>

            {aiMenuOpen && !collapsed && (
              <div
                id="ai-submenu"
                role="group"
                aria-label="Submenu Inteligência Artificial"
                className="flex flex-col gap-1 pr-2 py-1 mt-1 border-l-2 border-white/5 ml-5 pl-4 theme-light:border-slate-200"
              >
                <button
                  onClick={() => handleViewChange('ia')}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all duration-200 ${
                    view === 'ia'
                      ? 'bg-slate-800 text-primary-300 theme-light:bg-slate-100 theme-light:text-primary-600 font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 theme-light:text-slate-600 theme-light:hover:text-slate-800 theme-light:hover:bg-slate-50'
                  }`}
                >
                  <Lightbulb size={16} className="shrink-0" />
                  <span className="truncate">Aprendizado da IA</span>
                </button>

                <button
                  onClick={() => handleViewChange('admin-aliases')}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all duration-200 ${
                    view === 'admin-aliases'
                      ? 'bg-slate-800 text-primary-300 theme-light:bg-slate-100 theme-light:text-primary-600 font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 theme-light:text-slate-600 theme-light:hover:text-slate-800 theme-light:hover:bg-slate-50'
                  }`}
                >
                  <Link size={16} className="shrink-0" />
                  <span className="truncate">Nomes de Setor</span>
                </button>

                <button
                  onClick={() => handleViewChange('admin-prompts')}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all duration-200 ${
                    view === 'admin-prompts'
                      ? 'bg-slate-800 text-primary-300 theme-light:bg-slate-100 theme-light:text-primary-600 font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 theme-light:text-slate-600 theme-light:hover:text-slate-800 theme-light:hover:bg-slate-50'
                  }`}
                >
                  <MessageSquare size={16} className="shrink-0" />
                  <span className="truncate">Prompts de IA</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* --- SEÇÃO VISÃO & RELATÓRIOS (Admin, Supervisor) --- */}
        {(isAdmin || isSupervisor) && (
          <>
            {!collapsed && (
              <div className="mt-6 mb-2 px-[1.05rem]">
                <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-500/80 leading-none truncate block">
                  Visão & Relatórios
                </p>
              </div>
            )}
            {collapsed && <div className="mt-6 mb-2 border-t border-white/5 mx-2" />}

            <button onClick={() => handleViewChange('dashboard')} className={navItemClass(view === 'dashboard', collapsed)} title={collapsed ? 'Dashboard' : ''}>
              <LayoutDashboard size={20} className={navIconClass(view === 'dashboard')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Dashboard de Qualidade</span>}
              {!collapsed && <span className="md:hidden block">Dashboard</span>}
            </button>

            <button onClick={() => handleViewChange('fechamento')} className={navItemClass(view === 'fechamento', collapsed)} title={collapsed ? 'Fechamento' : ''}>
              <ClipboardCheck size={20} className={navIconClass(view === 'fechamento')} />
              {!collapsed && <span className="truncate block hidden md:block lg:block">Fechamento</span>}
              {!collapsed && <span className="md:hidden block">Fechamento</span>}
            </button>
          </>
        )}

        {/* --- SEÇÃO CONFIGURAÇÕES (Admin Only) --- */}
        {isAdmin && (
          <button onClick={() => handleViewChange('settings')} className={navItemClass(view === 'settings', collapsed)} title={collapsed ? 'Configurações' : ''}>
            <Settings size={20} className={navIconClass(view === 'settings')} />
            {!collapsed && <span className="truncate block hidden md:block lg:block">Configurações</span>}
            {!collapsed && <span className="md:hidden block">Configurações</span>}
          </button>
        )}
      </nav>

      <div className="mt-auto border-t border-white/[0.03]">
        {!collapsed ? (
          <button
            type="button"
            onClick={() => setUserPanelOpen(!userPanelOpen)}
            className="w-full flex items-center justify-between px-4 py-2 text-slate-600 hover:text-slate-400 transition-colors duration-200"
            aria-label={userPanelOpen ? 'Ocultar painel do usuário' : 'Mostrar painel do usuário'}
          >
            <span className="text-[10px] font-mono tracking-[0.18em] uppercase opacity-50 block truncate">
              Build v{__APP_VERSION__}
            </span>
            {userPanelOpen ? <ChevronDown size={14} className="shrink-0" /> : <ChevronUp size={14} className="shrink-0" />}
          </button>
        ) : (
          <div className="w-full flex justify-center py-2 text-slate-600" title={`Build v${__APP_VERSION__}`}>
            <span className="text-[9px] font-mono tracking-[0.1em] opacity-40">Bld</span>
          </div>
        )}

        {(userPanelOpen || collapsed) && (
          <div className={`px-4 pb-3 flex items-center ${collapsed ? 'justify-center' : 'justify-between gap-2'}`}>
            <div className="flex items-center gap-2 min-w-0" title={collapsed ? (username || 'Usuário') : undefined}>
              <div className="h-7 w-7 rounded-full bg-white/[0.06] flex items-center justify-center shrink-0 theme-light:bg-slate-200/60">
                <span className="text-[11px] font-bold text-slate-300 uppercase theme-light:text-slate-600">
                  {username ? username.charAt(0) : '?'}
                </span>
              </div>
              {!collapsed && (
                <div className="min-w-0">
                  <p className="text-[13px] text-slate-400 font-medium truncate leading-tight theme-light:text-slate-600">
                    {username || 'Usuário'}
                  </p>
                  {userRole && (
                    <p className="text-[10px] text-slate-600 leading-tight block truncate uppercase tracking-wider font-semibold">
                      {isAdmin ? 'Admin' : 'Supervisor'}
                    </p>
                  )}
                </div>
              )}
            </div>
            {!collapsed && (
              <button
                onClick={onLogout}
                title="Sair"
                className="shrink-0 p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
              >
                <LogOut size={16} />
              </button>
            )}
            {collapsed && (
              <button
                onClick={onLogout}
                title="Sair"
                className="hidden"
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );

  return (
    <>
      <aside className={`sidebar-shell relative hidden md:flex h-[100dvh] bg-slate-900/45 backdrop-blur-md border-r border-white/10 flex-col shrink-0 z-50 transition-[width] duration-300 ease-in-out ${isCollapsedState ? 'w-20' : 'w-72'} theme-light:bg-slate-100 theme-light:border-slate-300 theme-light:shadow-[4px_0_24px_rgba(0,0,0,0.05)]`}>
        {renderNavContent(isCollapsedState)}

        <button
          type="button"
          onClick={toggleCollapse}
          className="absolute -right-3.5 top-1/2 -translate-y-1/2 h-7 w-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-700 shadow-md transition-all focus:outline-none theme-light:bg-white theme-light:border-slate-200 theme-light:text-slate-500 theme-light:hover:text-slate-800 theme-light:hover:border-slate-300 z-[60] cursor-pointer"
          title={isCollapsedState ? "Expandir menu" : "Ocultar menu"}
        >
          {isCollapsedState ? <ChevronRight size={14} strokeWidth={2.5} /> : <ChevronLeft size={14} strokeWidth={2.5} />}
        </button>
      </aside>

      {mobileOpen ? (
        <button
          type="button"
          className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={onCloseMobile}
          aria-label="Fechar menu lateral"
        />
      ) : null}

      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu lateral"
        aria-hidden={!mobileOpen}
        tabIndex={-1}
        className={`safe-area-sheet sidebar-drawer-shell md:hidden fixed top-0 left-0 z-50 h-[100dvh] w-[min(21rem,88vw)] bg-slate-900/80 backdrop-blur-md border-r border-white/10 flex flex-col shadow-[0_20px_40px_rgba(0,0,0,0.35)] transition-transform duration-200 theme-light:bg-slate-100 theme-light:border-slate-300 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
      >
        {renderNavContent(false)}
      </aside>
    </>
  );
}
