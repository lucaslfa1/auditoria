import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const read = (relativePath) => readFileSync(resolve(process.cwd(), relativePath), 'utf8');

const appSource = read('src/App.tsx');
const cssSource = read('src/index.css');
const auditSetupSource = read('src/features/audit/components/AuditSetupStep.tsx');
const auditWorkspaceSource = read('src/features/audit/components/AuditWorkspace.tsx');
const auditActionsSource = read('src/features/audit/components/AuditResultActions.tsx');
const auditDetailsSource = read('src/features/audit/components/AuditEvaluationDetailsPanel.tsx');
const useTranscriptionSource = read('src/features/audit/hooks/useTranscription.ts');
const authenticatedAudioPlayerSource = read('src/shared/components/AuthenticatedAudioPlayer.tsx');
const classifierSource = read('src/features/classifier/components/Classifier.tsx');
const operatorAutocompleteSource = read('src/shared/components/OperatorAutocompleteFields.tsx');
const sidebarSource = read('src/shared/components/Sidebar.tsx');
const settingsSource = read('src/features/settings/components/Settings.tsx');
const adminCriteriaSource = read('src/features/admin/components/AdminCriteriaPage.tsx');
const supervisorPortalSource = read('src/features/supervisor/components/SupervisorPortal.tsx');
const reviewSource = read('src/features/review/components/ReviewPage.tsx');
const savedFilesSource = read('src/features/saved-files/components/SavedFiles.tsx');
const fechamentoSource = read('src/features/fechamento/components/FechamentoPage.tsx');
const automacaoPageSource = read('src/features/automacao/components/AutomacaoPage.tsx');
const automacaoRuntimePanelSource = read('src/features/automacao/components/AutomationRuntimePanel.tsx');
const automacaoConfigPanelSource = read('src/features/automacao/components/AutomationConfigPanel.tsx');
const automacaoHookSource = read('src/features/automacao/hooks/useAutomacaoDashboard.ts');
const automacaoSchemasSource = read('src/features/automacao/schemas.ts');
const automacaoViewModelSource = read('src/features/automacao/automationViewModel.ts');
const operadoresMesPanelSource = read('src/features/automacao/components/OperadoresMesPanel.tsx');
// Mojibake real (UTF-8 lido como Latin-1) gera C3/C2 seguidos de simbolo ou minuscula.
// Portugues legitimo usa essas letras apenas antes de outra maiuscula ou espaco
// (ex.: APROVACAO com cedilha/til, CAMARA com circunflexo) - o lookahead negativo
// evita esses falsos positivos sem deixar de pegar mojibake verdadeiro.
const mojibakePattern = /Ã(?![A-ZÀ-Ü\s])|Â(?![A-ZÀ-Ü\s])|\uFFFD/;

assert.match(appSource, /document\.body\.classList\.add\('theme-switching'\)/);
assert.match(appSource, /window\.setTimeout\(\(\) => \{\s*document\.body\.classList\.remove\('theme-switching'\);\s*\}, 70\)/);
assert.match(appSource, /duration-(100|150)/);
assert.match(appSource, /min-h-\[100dvh\].*md:h-screen/);
assert.match(appSource, /useBodyScrollLock\(isMobileSidebarOpen\)/);
assert.match(appSource, /import \{ AuditWorkspace \} from '\.\/features\/audit\/components\/AuditWorkspace';/);
assert.match(appSource, /import \{ useAuditFlow \} from '\.\/features\/audit\/hooks\/useAuditFlow';/);
assert.match(appSource, /<AuditWorkspace/);
assert.match(appSource, /ACTIVE_THEME_PRESET_CLASSNAME = 'theme-preset-corporativo'/);
assert.doesNotMatch(appSource, /\/api\/ui\/theme/);
assert.match(appSource, /authenticated: boolean/);
assert.match(appSource, /if \(data\.authenticated\)/);
assert.match(appSource, /Informe usu\u00e1rio e senha\./);

assert.match(auditWorkspaceSource, /import \{ AuditSetupStep \} from '\.\/AuditSetupStep';/);
assert.match(auditWorkspaceSource, /import \{ AuditUploadStep \} from '\.\/AuditUploadStep';/);
assert.match(auditWorkspaceSource, /flex flex-col gap-6/);
assert.match(auditWorkspaceSource, /showContinueButton=\{false\}/);
assert.match(auditWorkspaceSource, /showBackButton=\{false\}/);
assert.match(auditWorkspaceSource, /titleFirstWord="Central"/);
assert.match(auditWorkspaceSource, /titleRest="de Auditoria"/);
assert.match(auditWorkspaceSource, /Nome do operador/);
assert.match(auditWorkspaceSource, /Matr\u00edcula/);
assert.doesNotMatch(auditWorkspaceSource, /Auditoria de Qualidade/);
assert.doesNotMatch(auditWorkspaceSource, /Auditoria em uma tela/);
assert.doesNotMatch(auditWorkspaceSource, mojibakePattern);
assert.doesNotMatch(auditWorkspaceSource, /AuditStepRail|flow\.currentStep|handleBackToSetup|handleContinueToUpload/);
assert.doesNotMatch(useTranscriptionSource, mojibakePattern);

assert.match(auditActionsSource, /Baixar Relatório/);
assert.match(auditActionsSource, /Enviar ao supervisor/);
assert.match(auditActionsSource, /Modelo gestores/);
assert.match(auditActionsSource, /onSaveToDashboard/);
assert.match(auditActionsSource, /savedStatusLabel/);
assert.match(authenticatedAudioPlayerSource, /isBrowserObjectUrl/);
assert.match(authenticatedAudioPlayerSource, /url\.startsWith\('blob:'\)/);
assert.match(authenticatedAudioPlayerSource, /apiFetchBlob\(audioUrl,\s*\{\s*signal:\s*controller\.signal\s*\}\)/);
assert.match(auditDetailsSource, /N\u00e3o atende/);
assert.doesNotMatch(auditDetailsSource, /value="na"/);
assert.match(auditDetailsSource, /Crit\u00e9rios avaliados/);
assert.match(savedFilesSource, /titleFirstWord="Auditorias"/);
assert.match(savedFilesSource, /titleRest="em Arquivos"/);
assert.match(savedFilesSource, /Leitura detalhada/);
assert.match(savedFilesSource, /Resumo principal/);
assert.match(savedFilesSource, /ID Huawei/);
assert.doesNotMatch(savedFilesSource, /<option value="partial">Parcial<\/option>/);
assert.doesNotMatch(savedFilesSource, /<option value="na">Não se aplica<\/option>/);
assert.doesNotMatch(savedFilesSource, /Edição bloqueada/);
assert.doesNotMatch(savedFilesSource, /item\.score != null/);
assert.match(automacaoHookSource, /useQuery\(/);
assert.match(automacaoHookSource, /useMutation\(/);
assert.match(automacaoHookSource, /refetchInterval/);
assert.doesNotMatch(automacaoHookSource, /setInterval/);
assert.doesNotMatch(automacaoPageSource, /setInterval/);
assert.match(automacaoSchemasSource, /PipelineSummarySchema/);
assert.match(automacaoSchemasSource, /EngineStatusSchema/);
assert.match(automacaoSchemasSource, /z\.object/);
assert.match(automacaoSchemasSource, /discarded: numberValue\(0\)/);
assert.match(automacaoSchemasSource, /item_timeout_seconds: numberValue\(0\)/);
assert.match(automacaoSchemasSource, /limite_auditorias: numberValue\(10\)/);
assert.match(automacaoSchemasSource, /target_count: numberValue\(0\)/);
assert.match(automacaoSchemasSource, /last_volume_plan: CycleVolumePlanSchema/);
assert.match(automacaoSchemasSource, /operational_batch_size: numberValue\(0\)/);
assert.match(automacaoSchemasSource, /HealthStatusSchema/);
assert.match(automacaoHookSource, /limite_auditorias: 'automacao_audit_target_count'/);
assert.match(automacaoHookSource, /limite_auditorias: \{ min: 1 \}/);
assert.match(automacaoConfigPanelSource, /Meta de auditorias/);
assert.match(automacaoViewModelSource, /getProgressCounts/);
assert.match(automacaoViewModelSource, /completed \+ failed \+ discarded/);
assert.match(automacaoViewModelSource, /requested_audits/);
assert.match(automacaoViewModelSource, /last_heartbeat_at \?\? progress\?\.last_step_at/);
assert.doesNotMatch(automacaoViewModelSource, /stepAge[^;]+> 300/);
assert.match(automacaoHookSource, /buildAutomationGateStatus/);
assert.doesNotMatch(automacaoHookSource, /enabled: allAutomationGatesEnabled/);
assert.match(automacaoPageSource, /gates=\{gates\}/);
assert.doesNotMatch(automacaoPageSource, /AutomationHealthPanel/);
assert.doesNotMatch(automacaoPageSource, /Saúde da automação/);

// Painel "Auditorias por operador" (auditorias do mês × cota mensal por operador).
assert.match(automacaoPageSource, /import \{ OperadoresMesPanel \} from '\.\/OperadoresMesPanel';/);
assert.match(automacaoPageSource, /<OperadoresMesPanel data=\{operadoresMes\} isLoading=\{operadoresMesLoading\} \/>/);
assert.match(automacaoSchemasSource, /OperadoresMesSchema/);
assert.match(automacaoHookSource, /fetchOperadoresMes/);
assert.match(automacaoHookSource, /'operadores-mes'/);
assert.match(automacaoHookSource, /\/api\/automation\/operadores-mes/);
assert.match(automacaoHookSource, /operadoresMes: operadoresMesQuery\.data \?\? null/);
// Coluna renomeada para "Cota Mensal" e rótulo "cheio" em texto neutro.
assert.match(operadoresMesPanelSource, /Cota Mensal/);
assert.match(operadoresMesPanelSource, /cheio/);
assert.match(operadoresMesPanelSource, /Buscar operador/);
// Decisão do usuário: SEM ícone de alerta no "cheio".
assert.doesNotMatch(operadoresMesPanelSource, /AlertTriangle|AlertCircle/);
assert.doesNotMatch(operadoresMesPanelSource, mojibakePattern);
assert.match(automacaoRuntimePanelSource, /não processados/);
assert.match(automacaoRuntimePanelSource, /Meta do ciclo/);
assert.match(automacaoRuntimePanelSource, /Volume elegível menor que a meta/);
assert.match(automacaoViewModelSource, /Aguardando atualização do processamento/);
assert.doesNotMatch(automacaoRuntimePanelSource, /O ciclo travou|Item sem heartbeat|AlertMessage|falhas/);
assert.doesNotMatch(automacaoViewModelSource, /pode ter travado|heartbeat parou/);
assert.match(settingsSource, /setActiveTab\('telephony'\)/);
assert.match(settingsSource, /titleFirstWord="Configurações"/);
assert.match(settingsSource, /titleRest="do Sistema"/);
assert.doesNotMatch(settingsSource, /ThemeSettings/);
assert.doesNotMatch(settingsSource, />\s*Tema\s*</);
assert.match(adminCriteriaSource, /\/api\/admin\/sectors\/\$\{encodeURIComponent\(editingSectorId\)\}\/rename/);
assert.match(adminCriteriaSource, /new_label: sectorForm\.label/);
assert.match(adminCriteriaSource, /cascade: true/);

assert.match(auditSetupSource, /const selectOptionClass = theme === 'dark' \? 'bg-slate-900 text-slate-100' : 'bg-white text-slate-900'/);
assert.match(auditSetupSource, /const selectPlaceholderOptionClass = theme === 'dark' \? 'bg-slate-900 text-slate-500' : 'bg-white text-slate-500'/);
assert.match(auditSetupSource, /Defina o contexto/);
assert.match(auditSetupSource, /<option value="" className=\{selectPlaceholderOptionClass\}>Selecione o setor<\/option>/);
assert.match(auditSetupSource, /<option value="" className=\{selectPlaceholderOptionClass\}>Selecione o alerta<\/option>/);
for (const sectorId of ['cadastro', 'logistica_unilever', 'logistica', 'mondelez', 'checklist', 'receptivo']) {
  assert.match(
    auditSetupSource,
    new RegExp(`DOCUMENT_AUDIT_SECTOR_IDS[\\s\\S]*'${sectorId}'`),
    `Expected document audit sector ${sectorId} to be available in PDF flow.`,
  );
}
assert.doesNotMatch(auditSetupSource, /const pdfSectors/);
assert.doesNotMatch(auditSetupSource, /celula_atendimento|operacao_taborda/);

assert.doesNotMatch(cssSource, /body\.theme-preset-corporativo \{/);
assert.match(cssSource, /--color-primary-500: #ff3d03;/i);
assert.match(cssSource, /body\.theme-light select\.glass-input option \{\s*background-color: [^;]+;\s*color: [^;]+;/);
assert.match(cssSource, /html,\s*body,\s*#root\s*\{\s*min-height: 100dvh;/);
assert.match(cssSource, /html \{\s*-webkit-text-size-adjust: 100%;/);
assert.match(cssSource, /\.touch-scroll \{\s*-webkit-overflow-scrolling: touch;/);
assert.match(cssSource, /\.safe-area-overlay \{/);
assert.match(cssSource, /\.hide-scrollbar \{/);
assert.match(cssSource, /@media \(max-width: 767px\) \{\s*body \{\s*background-attachment: scroll;/);

assert.match(sidebarSource, /w-\[min\(21rem,88vw\)\]/);
assert.match(sidebarSource, /touch-scroll flex-1 overflow-y-auto overscroll-y-contain/);
assert.match(sidebarSource, /aria-label="Fechar menu lateral"/);
assert.match(sidebarSource, /Auditoria de qualidade/);
assert.match(sidebarSource, /<span[^>]*>Arquivos<\/span>/);
assert.match(sidebarSource, /Supervis\u00e3o/);
assert.match(sidebarSource, /Configurações/);

assert.match(supervisorPortalSource, /grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4/);
assert.match(supervisorPortalSource, /overflow-x-auto border-b border-white\/5 bg-slate-900\/50 hide-scrollbar/);
assert.match(supervisorPortalSource, /Taxa de aprova\u00e7\u00e3o/);
assert.match(supervisorPortalSource, /Crit\u00e9rios avaliados/);
assert.match(supervisorPortalSource, /titleFirstWord="Revis\u00e3o"/);
assert.match(supervisorPortalSource, /const APPROVAL_THRESHOLD_RATIO = 0\.8;/);
assert.doesNotMatch(supervisorPortalSource, mojibakePattern);
assert.doesNotMatch(reviewSource, /\{ value: 'partial', label: 'Parcial' \}/);
assert.doesNotMatch(reviewSource, /\{ value: 'na', label: 'N\/A' \}/);
assert.match(reviewSource, /else if \(c\.status === 'fail'\) \{\s*dynamicMax \+= w;\s*\}/);
assert.doesNotMatch(reviewSource, /else\s*\{\s*dynamicMax \+= w;\s*\}/);

assert.match(classifierSource, /useBodyScrollLock\(showOperatorModal\)/);
assert.match(classifierSource, /max-h-\[calc\(100dvh-1\.5rem\)\] overflow-y-auto overscroll-contain/);
assert.match(classifierSource, /titleFirstWord="Classifica\u00e7\u00e3o"/);
assert.match(classifierSource, /titleRest="de Arquivos"/);
assert.match(classifierSource, /ID Huawei/);
assert.match(classifierSource, /getOperatorDisplayName/);
assert.match(classifierSource, /getSupervisorDisplayName/);
assert.match(classifierSource, />\s*Operador\s*</);
assert.match(classifierSource, />\s*Supervisor\s*</);
assert.doesNotMatch(classifierSource, /Nome do operador/);

assert.match(operatorAutocompleteSource, /role="combobox"/);
assert.match(operatorAutocompleteSource, /role="listbox"/);
assert.match(operatorAutocompleteSource, /event\.key === 'ArrowDown'/);
assert.match(operatorAutocompleteSource, /ID Huawei/);
assert.doesNotMatch(operatorAutocompleteSource, /<datalist/);

assert.match(fechamentoSource, /apiFetchBlob\(`\/api\/fechamento\/exportar\?mes=\$\{mes\}&ano=\$\{ano\}`,\s*\{/);
assert.match(fechamentoSource, /method: 'POST'/);
assert.match(fechamentoSource, /body: JSON\.stringify\(rows\)/);
assert.match(fechamentoSource, /function isOperadorRj\(op: OperadorDisponivel\): boolean/);
assert.match(fechamentoSource, /isUtiRj\(op\.setor \?\? '', op\.escala \?\? ''\)/);
assert.match(fechamentoSource, /\.filter\(isOperadorRj\)/);
assert.match(fechamentoSource, /Adicionar operador RJ/);
assert.match(fechamentoSource, /Remover operador RJ/);
assert.match(fechamentoSource, /ID temporário para exportação/);
assert.match(fechamentoSource, /Dados cadastrais vêm do cadastro de operadores; ajustes na tabela são temporários\./);

// Triagem paralela: utilitario de concorrencia client-side.
const runWithConcurrencySource = read('src/shared/lib/runWithConcurrency.ts');
assert.match(runWithConcurrencySource, /export async function runWithConcurrency</);
// cap de concorrencia: no maximo `limit` runners em voo
assert.match(runWithConcurrencySource, /Math\.min\(Math\.floor\(limit\)/);
assert.match(runWithConcurrencySource, /Array\.from\(\{ length: effectiveLimit \}/);
// isolamento de erro por item (try/catch -> ok:false; nunca rejeita o lote inteiro)
assert.match(runWithConcurrencySource, /catch \(error\)/);
assert.match(runWithConcurrencySource, /ok: false/);

// Triagem paralela na fila: multi-select + "Triar selecionados" (cap 3, max 20).
const remoteTriageSource = read('src/features/classifier/components/RemoteTriageQueue.tsx');
assert.match(remoteTriageSource, /import \{ runWithConcurrency \} from '\.\.\/\.\.\/\.\.\/shared\/lib\/runWithConcurrency'/);
assert.match(remoteTriageSource, /const TRIAGE_CONCURRENCY = 3/);
assert.match(remoteTriageSource, /const MAX_BATCH_TRIAGE = 20/);
assert.match(remoteTriageSource, /Triar selecionados \(\{selectedHashes\.size\}\)/);
assert.match(remoteTriageSource, /runWithConcurrency\(hashes, TRIAGE_CONCURRENCY, classifyOne\)/);
// checkbox de selecao so aparece em itens elegiveis (mesma regra do botao Triar)
assert.match(remoteTriageSource, /\{isTriableItem\(item\) && \(/);
// progresso por item via Set (substitui o classifyingHash unico)
assert.match(remoteTriageSource, /classifyingHashes\.has/);
// classify individual nao usa mais alert() nativo (passou a usar toast)
assert.doesNotMatch(remoteTriageSource, /alert\(err\.message \|\| 'Erro ao classificar/);

// Editar tipo de alerta + trocar interlocutor com reavaliacao por IA, em Arquivos
// Salvos e Auditorias do mes (AuditModal). Reusa /api/audit/reevaluate.
const auditModalSource = read('src/features/automacao/components/AuditModal.tsx');
const speakerLabelsSource = read('src/features/audit/lib/speakerLabels.ts');
const alertCatalogSource = read('src/features/audit/lib/alertCatalog.ts');
const useReauditSource = read('src/features/audit/hooks/useReaudit.ts');

// hook de reavaliacao usa o endpoint existente (sem motor novo)
assert.match(useReauditSource, /\/api\/audit\/reevaluate/);
assert.match(useReauditSource, /export function useReaudit/);
// helpers puros de locutor
assert.match(speakerLabelsSource, /export function setSegmentSpeaker/);
assert.match(speakerLabelsSource, /export const SPEAKER_OPTIONS/);
// troca global de interlocutor (de X para Y em todas as falas)
assert.match(speakerLabelsSource, /export function renameSpeakerEverywhere/);
// helpers do catalogo de alerta (em arquivo proprio, nao no componente)
assert.match(alertCatalogSource, /export function buildAuditAlertFromCriteria/);
assert.match(alertCatalogSource, /export function findAlertIdByLabel/);

// As duas telas fiam: seletor de alerta + Reavaliar + inverter/trocar locutor
for (const source of [savedFilesSource, auditModalSource]) {
  assert.match(source, /import \{ AlertTypeSelect \} from '\.\.\/\.\.\/audit\/components\/AlertTypeSelect'/);
  assert.match(source, /import \{ useReaudit \} from '\.\.\/\.\.\/audit\/hooks\/useReaudit'/);
  assert.match(source, /buildAuditAlertFromCriteria/);
  assert.match(source, /<AlertTypeSelect/);
  assert.match(source, />Refazer Auditoria</);
  assert.match(source, /setSegmentSpeakerAt/);
  assert.match(source, /<SpeakerRenameControl/);
  // nota da IA prevalece quando ha reavaliacao (senao recalculo local)
  assert.match(source, /reevaluatedScore != null/);
  // o PUT carrega o alerta trocado
  assert.match(source, /putBody\.alert_id = editAlertId/);
}

console.log('Frontend regression checks passed.');
