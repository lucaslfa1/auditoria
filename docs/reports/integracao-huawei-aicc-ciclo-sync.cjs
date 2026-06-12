const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageNumber, PageBreak, TabStopType, TabStopPosition,
} = require('docx');

const NODE_GLOBAL = process.env.npm_config_prefix || require('os').homedir();
require('module').globalPaths.push(path.join(NODE_GLOBAL, 'node_modules'));

const BLUE = "1F4E79";
const GREY = "595959";
const LIGHT = "D9E2F3";
const BORDER = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };
const CELL_MARGINS = { top: 80, bottom: 80, left: 120, right: 120 };

const h1 = (txt) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text: txt })],
});
const h2 = (txt) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({ text: txt })],
});
const h3 = (txt) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  children: [new TextRun({ text: txt })],
});
const p = (txt, opts = {}) => new Paragraph({
  spacing: { after: 120 },
  children: [new TextRun({ text: txt, ...opts })],
});
const pRich = (runs) => new Paragraph({
  spacing: { after: 120 },
  children: runs,
});
const bullet = (txt) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  spacing: { after: 60 },
  children: [new TextRun({ text: txt })],
});
const bulletRich = (runs) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  spacing: { after: 60 },
  children: runs,
});
const code = (txt) => new Paragraph({
  spacing: { before: 80, after: 80 },
  shading: { fill: "F2F2F2", type: ShadingType.CLEAR },
  children: [new TextRun({ text: txt, font: "Consolas", size: 20 })],
});

const headerCell = (txt, width) => new TableCell({
  borders: BORDERS,
  width: { size: width, type: WidthType.DXA },
  shading: { fill: BLUE, type: ShadingType.CLEAR },
  margins: CELL_MARGINS,
  children: [new Paragraph({
    children: [new TextRun({ text: txt, bold: true, color: "FFFFFF", size: 20 })],
  })],
});
const cell = (txt, width, opts = {}) => new TableCell({
  borders: BORDERS,
  width: { size: width, type: WidthType.DXA },
  shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
  margins: CELL_MARGINS,
  children: [new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    children: [new TextRun({ text: String(txt), size: 20, bold: !!opts.bold })],
  })],
});

function tabela(headers, rows, widths) {
  const totalWidth = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        children: headers.map((h, i) => headerCell(h, widths[i])),
        tableHeader: true,
      }),
      ...rows.map((r) =>
        new TableRow({
          children: r.map((c, i) => {
            if (typeof c === 'object' && c !== null && 'text' in c) {
              return cell(c.text, widths[i], c);
            }
            return cell(c, widths[i]);
          }),
        })
      ),
    ],
  });
}

const doc = new Document({
  creator: "NSTECH Auditoria",
  title: "Integração Huawei AICC — Ciclo de Sincronização",
  description: "Documentação técnica do ciclo de download automático de gravações.",
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: BLUE, font: "Calibri" },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: BLUE, font: "Calibri" },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: GREY, font: "Calibri" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [
            new TextRun({ text: "NSTECH Auditoria · Integração Huawei AICC", color: GREY, size: 18 }),
            new TextRun({ text: "\t" }),
            new TextRun({ text: "Documento técnico", color: GREY, size: 18 }),
          ],
          tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Página ", color: GREY, size: 18 }),
            new TextRun({ children: [PageNumber.CURRENT], color: GREY, size: 18 }),
          ],
        })],
      }),
    },
    children: [
      // ============ CAPA ============
      new Paragraph({
        alignment: AlignmentType.LEFT,
        spacing: { before: 1200, after: 240 },
        children: [new TextRun({ text: "INTEGRAÇÃO HUAWEI AICC", bold: true, size: 48, color: BLUE })],
      }),
      new Paragraph({
        alignment: AlignmentType.LEFT,
        spacing: { after: 240 },
        children: [new TextRun({ text: "Ciclo de Sincronização Automática de Gravações", size: 32, color: GREY })],
      }),
      new Paragraph({
        alignment: AlignmentType.LEFT,
        spacing: { after: 600 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: BLUE, space: 4 } },
        children: [new TextRun({ text: "Auditoria de Ligações · NSTECH", size: 22, color: GREY })],
      }),
      new Paragraph({
        spacing: { after: 120 },
        children: [
          new TextRun({ text: "Autor: ", bold: true }),
          new TextRun({ text: "Lucas Afonso" }),
        ],
      }),
      new Paragraph({
        spacing: { after: 120 },
        children: [
          new TextRun({ text: "Data: ", bold: true }),
          new TextRun({ text: "24 de abril de 2026" }),
        ],
      }),
      new Paragraph({
        spacing: { after: 120 },
        children: [
          new TextRun({ text: "Versão do sistema: ", bold: true }),
          new TextRun({ text: "1.3.x (módulo Telefonia)" }),
        ],
      }),
      new Paragraph({
        spacing: { after: 120 },
        children: [
          new TextRun({ text: "Plataforma: ", bold: true }),
          new TextRun({ text: "Huawei AICC Cloud (BrazilSaaS) — brazilsaas.aicccloud.com:28443" }),
        ],
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // ============ 1. RESUMO EXECUTIVO ============
      h1("1. Resumo executivo"),
      p("Este documento descreve a integração entre o sistema de Auditoria NSTECH e a plataforma Huawei AICC Cloud (BrazilSaaS), responsável pelo download automático das gravações de chamadas que alimentam o pipeline de transcrição, classificação e auditoria assistida por IA."),
      p("A integração foi configurada para operar em modo loop residente, executando um ciclo completo a cada 8 horas com janela retroativa de 9 horas. Esse intervalo foi escolhido para minimizar custos de API Azure (Speech + GPT-4o) mantendo cobertura completa do dia."),
      h3("Principais resultados validados"),
      bullet("Conectividade Huawei AICC operacional (HTTP 200 em todos os endpoints CMS e CC-FS)."),
      bullet("Autenticação via proxy SDK-HMAC-SHA256 funcionando (c2Authorization.php — Teledata)."),
      bullet("IP whitelisted 34.171.63.68 configurado e em uso para downloads OBS."),
      bullet("Lock distribuído em PostgreSQL impede execuções concorrentes sem perda de dados."),
      bullet("Deduplicação por callId evita reprocessamento mesmo com sobreposição de janelas."),

      // ============ 2. ARQUITETURA ============
      h1("2. Arquitetura da integração"),
      h2("2.1 Fluxo de dados"),
      p("O ciclo completo segue a sequência:"),
      pRich([new TextRun({ text: "Huawei AICC → backend (huawei_sync.py) → fila de revisão (Postgres) → Triagem → Auditoria", font: "Consolas", size: 20 })]),
      h2("2.2 Componentes principais"),
      tabela(
        ["Componente", "Caminho", "Função"],
        [
          ["Cliente HTTP", "backend/core/huawei_client.py", "Encapsula chamadas REST à Huawei AICC e CC-FS"],
          ["Orquestrador", "backend/core/huawei_sync.py", "Executa o ciclo de sync com lock distribuído"],
          ["Loop residente", "backend/automation_engine.py", "Dispara ciclos no intervalo configurado"],
          ["Router API", "backend/routers/telefonia.py", "Expõe endpoints HTTP de sync e status"],
          ["Página frontend", "src/features/telefonia/", "Painel admin de sincronização e listagem"],
        ],
        [2200, 3800, 3360]
      ),
      h2("2.3 Endpoints Huawei utilizados"),
      tabela(
        ["Finalidade", "Endpoint", "Método interno"],
        [
          ["Listar chamadas (janela)", "/rest/cmsapp/v2/openapi/vdn/querycalls", "buscar_historico_chamadas"],
          ["Detalhe de chamada", "/rest/cmsapp/v1/openapi/calldata/querybasiccallinfo", "consultar_detalhe_chamada"],
          ["Download por callId", "/CCFS/resource/ccfs/downloadRecord", "baixar_gravacao_por_callid"],
          ["Download por fileName", "/CCFS/resource/ccfs/downloadRecordFile", "baixar_gravacao_por_filename"],
          ["URL pré-assinada OBS", "/CCFS/resource/ccfs/getRecordFileUrlFromObs", "obter_url_audio_obs"],
          ["Auth proxy (HMAC)", "/aicc/auth/c2Authorization.php (Teledata)", "_assinar_via_proxy"],
        ],
        [2400, 4760, 2200]
      ),

      // ============ 3. AUTENTICAÇÃO E IP WHITELIST ============
      h1("3. Autenticação e IP whitelist"),
      h2("3.1 Modo proxy (padrão)"),
      p("A Huawei exige assinatura SDK-HMAC-SHA256 em todos os requests. Como o ambiente de execução pode não estar em IP liberado pela Huawei, a NSTECH delega a etapa de assinatura ao endpoint c2Authorization.php hospedado pela Teledata Brasil. Esse endpoint recebe AK, SK, URL alvo e body, e retorna o header Authorization já assinado."),
      p("Este modo é ativado por:"),
      code("HUAWEI_AUTH_MODE=proxy\nHUAWEI_PROXY_URL=https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php"),
      h2("3.2 IP whitelisted (34.171.63.68)"),
      p("Mesmo com a assinatura via proxy, a requisição final precisa originar de um IP liberado no whitelist da Huawei. Para resolver isso em ambientes que não estão no whitelist (ex.: desenvolvimento local, Cloud Run dinâmico), o cliente faz reescrita transparente do host:"),
      bullet("A URL brazilsaas.aicccloud.com é substituída pelo IP estático 34.171.63.68."),
      bullet("O header Host: brazilsaas.aicccloud.com é mantido para preservar SNI/TLS."),
      bullet("Há também DNS override no resolver via core/network_utils.py."),
      p("Esse mecanismo é controlado pela variável:"),
      code("HUAWEI_PROXY_IP=34.171.63.68"),

      // ============ 4. CONFIGURAÇÃO DO CICLO ============
      h1("4. Configuração do ciclo de sincronização"),
      h2("4.1 Modos disponíveis"),
      tabela(
        ["Modo", "Variável de controle", "Como funciona"],
        [
          [{ text: "Loop interno (escolhido)", bold: true, fill: LIGHT }, { text: "ENABLE_IN_PROCESS_AUTOMATION_ENGINE=true", fill: LIGHT }, { text: "Backend FastAPI roda ciclo a cada N segundos. Auto-inicia no startup.", fill: LIGHT }],
          ["Cron externo", "ENABLE_IN_PROCESS_AUTOMATION_ENGINE=false + CRON_SECRET_TOKEN", "Cloud Scheduler bate POST /api/telefonia/cron/sync com Bearer token"],
          ["Manual", "—", "Admin clica em 'Sincronizar agora' no painel Telefonia"],
        ],
        [2400, 4400, 2560]
      ),
      h2("4.2 Decisão pelo ciclo de 8 horas"),
      p("Análise feita a partir de execução real do sync em 24/04/2026 (janela de 1 hora):"),
      bullet("132 chamadas avaliadas pela API querycalls."),
      bullet("4 áudios efetivamente baixados (≈3% de conversão — restante são IVR e abandonadas sem gravação)."),
      bullet("Tempo de execução: aproximadamente 6 minutos."),
      p("Escalando linearmente para diferentes intervalos:"),
      tabela(
        ["Intervalo", "Janela retroativa", "Chamadas/ciclo", "Áudios/ciclo", "Duração estimada", "Ciclos/dia", "Custo Azure"],
        [
          ["1h", "2h", "~264", "~8", "~12 min", "24", "Alto"],
          ["4h", "5h", "~660", "~20", "~30 min", "6", "Médio"],
          [{ text: "8h (escolhido)", bold: true, fill: LIGHT }, { text: "9h", fill: LIGHT }, { text: "~1.200", fill: LIGHT }, { text: "~36", fill: LIGHT }, { text: "~55 min", fill: LIGHT }, { text: "3", fill: LIGHT }, { text: "Baixo", fill: LIGHT }],
          ["24h", "25h", "~3.300", "~100", "~2,5h", "1", "Mínimo"],
        ],
        [1100, 1500, 1500, 1300, 1500, 1100, 1360]
      ),
      h3("Por que 8 horas"),
      bullet("Custo Azure (Speech + GPT-4o) controlado — fator decisivo no ambiente atual em conta pessoal."),
      bullet("Cobertura completa do dia: 3 ciclos cobrem manhã, tarde e madrugada."),
      bullet("Janela de 9h dá 1h de overlap entre ciclos para absorver atrasos da Huawei na indexação de CDR."),
      bullet("Lock distribuído + deduplicação por callId garantem que overlap não gera reprocessamento."),
      bullet("Duração de ciclo (~55min) ainda dentro da janela segura de timeouts e com folga para outras cargas no backend."),
      h3("Quando reduzir para 4h ou 1h"),
      bullet("Se a auditoria precisar ser revisada várias vezes ao dia."),
      bullet("Se a operação crescer e ultrapassar 50 áudios reais por hora."),
      bullet("Se houver SLA com supervisão exigindo detecção de incidentes em tempo quase real."),

      // ============ 5. CONFIGURAÇÃO APLICADA ============
      h1("5. Configuração aplicada (estado atual)"),
      h2("5.1 Variáveis de ambiente — backend/.env"),
      code(`HUAWEI_CMS_URL=https://brazilsaas.aicccloud.com:28443
HUAWEI_FS_URL=https://brazilsaas.aicccloud.com:28443
HUAWEI_CC_ID=1
HUAWEI_VDN=25
HUAWEI_AK=<HUAWEI_AK>
HUAWEI_SK=<HUAWEI_SK>
HUAWEI_APP_KEY=<HUAWEI_DIRECT_APP_KEY>

HUAWEI_AUTH_MODE=proxy
HUAWEI_PROXY_URL=https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php
HUAWEI_PROXY_IP=34.171.63.68

ENABLE_HUAWEI_SYNC=true
HUAWEI_SYNC_HORAS_RETROATIVAS=9

ENABLE_IN_PROCESS_AUTOMATION_ENGINE=true`),
      h2("5.2 Configurações no banco de dados"),
      tabela(
        ["Chave", "Valor", "Significado"],
        [
          ["automacao_hibrida_ativa", "true", "Liga o ciclo de sync+auditoria do loop residente"],
          ["automacao_intervalo_segundos", "28800", "Intervalo entre ciclos = 28800s = 8 horas"],
          ["huawei_horas_retroativas", "9", "Janela de busca em querycalls = 9h (overlap de 1h)"],
        ],
        [3000, 1800, 4560]
      ),
      p("Para alterar via SQL:"),
      code(`UPDATE configuracoes SET valor = '14400' WHERE chave = 'automacao_intervalo_segundos';
UPDATE configuracoes SET valor = '5'     WHERE chave = 'huawei_horas_retroativas';`),

      // ============ 6. SEGURANÇA E RESILIÊNCIA ============
      h1("6. Segurança e resiliência"),
      h2("6.1 Lock distribuído (proteção contra ciclos paralelos)"),
      p("O método executar_sync_huawei usa um Postgres advisory lock com chave _HUAWEI_SYNC_LOCK_KEY = 2026042202 que protege contra qualquer execução concorrente, independentemente da origem (loop interno, cron externo, botão admin, script standalone). A segunda execução simultânea retorna status: skipped sem efeito colateral."),
      h2("6.2 Deduplicação por callId"),
      p("Antes de enfileirar uma gravação para revisão, o sync verifica se o callId já existe na fila. O resultado do ciclo expõe contadores baixadas, enfileiradas e duplicadas para auditoria."),
      h2("6.3 Tratamento de credenciais"),
      bullet("AK, SK e APP_KEY ficam apenas em backend/.env (NÃO commitado)."),
      bullet("Em produção, devem ser injetados via Secret Manager do Cloud Run."),
      bullet("O proxy c2Authorization.php nunca recebe credenciais Azure — apenas Huawei AK/SK."),
      h2("6.4 Códigos de retorno conhecidos"),
      tabela(
        ["Código Huawei", "Significado", "Tratamento no código"],
        [
          ["0100000", "Sucesso", "Processa o resultDesc.data"],
          ["0300012", "No data found (chamada sem gravação)", "Log INFO; descarta callId; segue para próximo"],
          ["HTTP 401/403", "Token expirado ou IP não whitelisted", "Erro fatal; investigar IP e proxy"],
        ],
        [2000, 4360, 3000]
      ),

      // ============ 7. OBSERVABILIDADE ============
      h1("7. Observabilidade e operação"),
      h2("7.1 Onde acompanhar"),
      tabela(
        ["Recurso", "Localização", "O que mostra"],
        [
          ["Painel Admin", "Frontend → sidebar → Telefonia", "Status do último sync, lista das gravações enfileiradas"],
          ["Endpoint status", "GET /api/telefonia/sync/status", "JSON com started_at, finished_at, status, credentials"],
          ["Logs estruturados", "backend/logs/huawei_sync/<timestamp>.log", "Histórico completo de cada execução standalone"],
          ["Logs FastAPI", "stdout do uvicorn / Cloud Run", "Logs do loop residente"],
        ],
        [2000, 3500, 3860]
      ),
      h2("7.2 Sync manual sob demanda"),
      p("Mesmo com o loop interno ligado, é possível disparar sync manual a qualquer momento:"),
      bullet("Pelo painel: botão 'Sincronizar agora' em /telefonia (requer login admin)."),
      bullet("Por API: POST /api/telefonia/sync/manual com sessão admin autenticada."),
      bullet("Por CLI: cd backend && python scripts/run_huawei_sync.py --horas 9"),
      h2("7.3 Última execução validada"),
      p("Sync executado em 24/04/2026 14:51 com janela de 1h retornou:"),
      code(`{
  "status": "ok",
  "chamadas_consideradas": 132,
  "baixadas": 4,
  "enfileiradas": 4,
  "duplicadas": 0,
  "erros": 1
}`),
      p("O único erro veio de uma falha de transcrição Azure (áudio sem fala diarizada) — não relacionado à integração Huawei."),

      // ============ 8. PRÓXIMOS PASSOS ============
      h1("8. Próximos passos sugeridos"),
      bullet("Adicionar tabela huawei_sync_logs para histórico persistente (hoje só último ciclo em memória)."),
      bullet("Expor métricas Prometheus/Grafana: ciclos/h, áudios/ciclo, duração, taxa de erro."),
      bullet("Alerta automático quando 2 ciclos consecutivos falharem."),
      bullet("Migrar credenciais para Google Secret Manager em produção."),
      bullet("Avaliar passar para 4h se a equipe de auditoria pedir resultados mais frequentes."),

      // ============ APÊNDICE ============
      h1("Apêndice A — Glossário"),
      tabela(
        ["Termo", "Significado"],
        [
          ["AICC", "Active Intelligence Contact Center — plataforma Huawei de call center"],
          ["BrazilSaaS", "Tenant cloud Huawei hospedado no Brasil"],
          ["AK / SK", "Access Key / Secret Key — credenciais para assinatura HMAC"],
          ["CC-CMS", "Contact Center — Call Management System (consulta de chamadas)"],
          ["CC-FS", "Contact Center — File Server (download de gravações)"],
          ["VDN", "Vector Directory Number — identificador lógico do contact center"],
          ["CDR", "Call Detail Record — registro de detalhes de chamada"],
          ["OBS", "Object Storage Service — armazenamento de objetos da Huawei Cloud"],
          ["IVR", "Interactive Voice Response — URA"],
          ["SDK-HMAC-SHA256", "Algoritmo de assinatura proprietário Huawei baseado em HMAC-SHA256"],
        ],
        [2200, 7160]
      ),
    ],
  }],
});

const out = path.join(__dirname, 'integracao-huawei-aicc-ciclo-sync.docx');
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log("OK:", out);
});
