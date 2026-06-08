# Auditoria documental (PDF de chat Service Cloud) — Design

**Data:** 2026-06-03
**Autor:** Claude (brainstorming com Lucas)
**Status:** aprovado para seguir (Lucas autorizou execução autônoma até encerrar)
**Versão alvo:** 1.3.x (definir no log de versão)

## Problema

A auditoria 92 (`source_type='pdf'`, setor Célula, alerta "Atendimento ao Cliente - Receptivo",
arquivo `5 - RECEPTIVO.pdf`) trouxe a "transcrição" com formatação quebrada. Não é falha do
pipeline de áudio — é **extração de PDF**. O arquivo é um export de chat do **Service Cloud**
(atendimento receptivo via chatbot "Tati" + operadora), HTML impresso para PDF.

Causa raiz, em `backend/core/audit.py`:

1. **`extract_text_from_pdf` (linha ~286)** — one-liner de `pypdf` sem limpeza. Em PDF impresso
   de HTML (layout em colunas) produz: cabeçalhos (nome+hora) deslocados, quebra de palavra por
   word-wrap (`ao n\nosso`, `correspo\nndente`, `Por f\navor`), rodapés de impressão no meio do
   diálogo (`06/05/2026, 15:59 Service Cloud` / `file:///...html N/N`) e o artefato `Leitura`
   (read-receipt).
2. **`parse_whatsapp_log` (linha ~293)** — só reconhece o formato `[DD/MM/AAAA HH:MM:SS] Fulano: msg`
   (WhatsApp). O Service Cloud não bate; cai no fallback `[{text: raw_text}]` → **um único
   segmento cru** com `start/end = 00:00`.

Setores que operam por PDF (informados por Lucas): **Receptivo, Checklist, Operação Taborda,
Célula**.

## Objetivos

1. Extrair e **estruturar por locutor** o texto do PDF de chat, removendo artefatos.
2. Avaliação por critérios **editável**, no mesmo padrão das auditorias de áudio, **adaptada a
   documento** (sem campos de timestamp de áudio, sem player).
3. **Deletar** as auditorias de PDF antigas com texto sujo (a 92).

## Não-objetivos

- Não tocar no pipeline de áudio (`hybrid_dual`, transcrição, etc.).
- Não suportar DOCX/HTML/TXT agora — só PDF (extensível depois).
- Não reprocessar auditorias antigas (serão deletadas).

## Decisões

- **Parser determinístico** (não IA), conforme escolha de Lucas.
- **Locutor embutido no texto** (`"Operador: ..."`, `"Cliente: ..."`, `"Bot: ..."`), seguindo a
  convenção já existente no projeto: `ReadOnlyTranscription.parseSpeakerPrefix` e o caminho de
  avaliação IA já leem o locutor do prefixo do texto. **Sem** novo campo `speaker` no tipo
  (evita mexer em pydantic, serialização e no prompt da IA).
- **Editor de documento**: cards de fala com **textarea**, **sem** campos `start`/`end` e **sem**
  player. Edição de critérios reaproveita `useAuditResultEditor` (já é agnóstico ao tipo).
- **Extração isolada** numa função própria (`extract_raw_text`), para a Fase 2 trocar
  `pypdf → pdfplumber` sem reescrever o parser.

## Arquitetura

### Backend — novo módulo `backend/core/document_parsing.py`

- `extract_raw_text(file_content: bytes) -> str` — Fase 1 usa `pypdf` (isolado aqui).
- `detect_document_format(text) -> "service_cloud" | "whatsapp" | "generic"`.
- `parse_service_cloud(text, operator_name=None) -> list[dict]` — pipeline:
  1. **Limpeza** (regex no texto inteiro): remove `\d{2}/\d{2}/\d{4},? \d{2}:\d{2} Service Cloud`
     e `file:///...\.html \d+/\d+`; remove linhas `^Leitura$`.
  2. **Word-wrap**: junta `linha_longa(termina em letra) + próxima(inicia minúscula)` sem espaço;
     demais quebras dentro do turno viram espaço. Limiar de comprimento evita juntar mensagens
     curtas legítimas (`Bom dia`).
  3. **Cabeçalhos**: regex `^(.+?)(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})$` separa
     locutor + data + hora; conteúdo seguinte pertence ao cabeçalho anterior.
  4. **Papel canônico** (`classify_role`): `BOT *`/atendente virtual → `Bot`; nome com sufixo de
     setor (`Selma - Célula`) ou que bate com `operator_name` → `Operador`; demais → `Cliente`.
  5. **Reordenação por timestamp** (rede de segurança contra a troca de coluna do PDF).
  6. Saída: `[{"start": "HH:MM:SS", "end": "HH:MM:SS", "text": "Papel: conteúdo"}]`.
- `parse_whatsapp_log` movido para cá (regressão preservada).
- `parse_document(text, operator_name=None)` — dispatcher por formato; `generic` → 1 segmento
  com o texto limpo.

### Backend — `backend/core/audit.py`

- `extract_text_from_pdf` delega para `document_parsing.extract_raw_text`.
- `process_pdf_audit` chama `document_parsing.parse_document(raw_text, operator_name)` no lugar de
  `parse_whatsapp_log(...) or [{...raw...}]`.

### Frontend — editor adaptado

- `AuditTranscriptPanel` (modo `'pdf'`): no modo edição, **ocultar** os inputs `start`/`end`;
  manter apenas o `textarea` por fala + inserir/remover. Cabeçalho "Texto extraído". Sem player
  (já é o comportamento atual).
- `ReadOnlyTranscription`: para doc, suprimir a coluna de tempo quando `onSeekAudio` ausente já
  resolve o clique; manter badge de locutor (já funciona com o prefixo `Papel:`).
- Edição de critérios: **nenhuma mudança** — `useAuditResultEditor` + `/api/audit/reevaluate`
  (que já respeita `source_type='pdf'`, pulando diarização) já cobrem doc.

### Dados — limpeza

- Preservar o texto cru da 92 como fixture (`tests/backend/fixtures/pdf_chat/`).
- Deletar a auditoria 92 do banco (autorizado).

## Fases

- **Fase 1 (esta):** módulo + limpeza + parser + reordenação por timestamp, testados contra a 92;
  editor de doc; deleção das antigas. A associação de **respostas curtas do cliente** (ex: "2",
  CPF, senha) ao locutor certo é **best-effort** — o PDF cru já vem com colunas trocadas.
- **Fase 2 (quando chegarem PDFs reais dos 4 setores):** validar formatos; avaliar troca para
  `pdfplumber` (extração com coordenadas resolve a ordem na origem); refinar heurística de papel
  e a associação de turnos.

## Testes (determinísticos, fixture = texto cru da 92)

- Limpeza remove `Service Cloud`, `file:///...html`, `Leitura`.
- Word-wrap corrige `nosso`, `correspondente`, `Agendado`, `Atendimento`, `favor`, `mais`.
- Cabeçalhos detectados; papéis canônicos (`Operador:`, `Cliente:`, `Bot:`) presentes.
- Segmentos ordenados por timestamp crescente.
- `detect_document_format` classifica Service Cloud vs WhatsApp vs genérico.
- `parse_whatsapp_log` mantém comportamento (regressão).
- `generic` → 1 segmento limpo.

## Riscos

- **Ordem de coluna sem o PDF binário:** mitigado por reordenação via timestamp + Fase 2
  (pdfplumber). Documentado como best-effort.
- **Heurística de papel** pode errar em nomes atípicos: fallback para `operator_name`; refino na
  Fase 2 com exemplos reais.
- **Word-wrap agressivo** poderia juntar mensagens curtas: mitigado pelo limiar de comprimento.
