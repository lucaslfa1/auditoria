# Validacao Real de Diarizacao 2026-03-04

## Ambiente
- Backend local: `http://localhost:8000`
- Frontend build: `npm run build` OK
- Testes backend: `32` testes OK

## Casos validados

### 1. Ponto de Apoio
- Arquivo: `Ligações/RAST.-UTI-DIST-BAS/PONTO DE APOIO/RUIM-PONTO DE APOIO-20251223152017944_Priscila_Cabral_Fenix_Voz.wav`
- Resultado:
  - abertura identificada como `Ponto de Apoio`
  - apresentação `Aqui é a Priscila do rastreamento da Opentech` identificada como `Operador`
  - perguntas operacionais principais ficaram com `Operador`
  - resposta `É, ele é da Compran.` passou a sair com `Ponto de Apoio`
  - resposta curta final foi quebrada em `Operador: Pode.` e `Ponto de Apoio: Uns quinze?`
- Residual:
  - o bloco `Nós somos da Opentech... Qual que é a placa dele?` ainda depende de o ASR separar corretamente as duas vozes

### 2. Policia Boa
- Arquivo: `Ligações/RAST.-UTI-DIST-BAS/POLÍCIA/BOA-POLICIA-22-09-2025_01-58-05_1700_8633026366.mp3`
- Resultado:
  - `Com PRF Alves.` passou a ficar com `Policia`
  - apresentação do operador como base de sinistro/rastreamento ficou com `Operador`
  - perguntas de confirmação (`Quarto o que?`, `Ele estava aonde no final?`) ficaram com `Policia`
  - o bloco misto em `00:24` foi quebrado em `Policia: Hum.`, fala longa do operador e `Policia: Pode deixar.`
- Residual:
  - ainda pode haver microquebras no mesmo segundo quando o ASR devolve um bloco unico longo

### 3. Policia Ruim
- Arquivo: `Ligações/RAST.-UTI-DIST-BAS/POLÍCIA/RUIM-POLICIA-agent-10610-4_11_2025_1_55_31-node01-1762232128-715 - Copia.wav`
- Resultado:
  - apresentação `Eu falo em nome do rastreamento da Opentech` ficou com `Operador`
  - resposta curta `Consegue sim, só um segundo.` ficou com `Policia`
  - troca de pergunta/resposta no miolo da ligação ficou mais coerente
- Residual:
  - ainda existem trechos mistos em falas longas quando o ASR junta duas vozes em um mesmo bloco

## Conclusao
- A diarizacao ficou mais confiavel para `Motorista`, `Ponto de Apoio` e `Policia`
- O sistema esta apto para uso operacional local
- O risco residual principal nao esta mais na heuristica de speaker isolada, e sim em blocos longos que o ASR do Azure devolve ja agregados
- A quebra de blocos mistos passou a corrigir respostas curtas do interlocutor dentro de falas longas do operador
