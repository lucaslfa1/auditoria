# Relatório de Investigação de Testes Falhos
**Data:** 28 de Abril de 2026

Ao executar a bateria de testes automatizados (`npm run test:backend`) antes de prosseguir com o deploy, o sistema de Integração Contínua (CI) detectou **3 falhas** no Backend. Para garantir a estabilidade da aplicação, o deploy foi paralisado e as falhas foram investigadas. 

Abaixo estão os resultados detalhados da investigação e as raízes de cada problema:

---

## 1. Arquivo de Teste Corrompido (`test_audit_discard.py`)
**Erro Técnico:** `SyntaxError: source code string cannot contain null bytes`
*   **Investigação:** O arquivo `backend/tests/test_audit_discard.py` foi modificado na última atualização remota (`origin/main`) e acabou sendo salvo no Git com um formato de codificação binário/errado (provavelmente UTF-16 com bytes nulos, ao invés do padrão UTF-8 para código).
*   **Impacto:** O Python e o Pytest não conseguem ler o arquivo para rodar os testes contidos nele, quebrando a bateria inteira logo no início.
*   **Correção Necessária:** Converter o arquivo novamente para a codificação de texto correta (UTF-8) e enviar essa correção para o Git.

## 2. Falha na Lógica de Transcrição (`test_core_logic.py`)
**Erro Técnico:** `KeyError: 'selected_provider'` no teste `test_transcribe_audio_return_metadata_includes_selected_provider`
*   **Investigação:** O teste exige que, após processar o áudio, o sistema retorne nos metadados de qual provedor de IA a transcrição veio (a chave `selected_provider`, ex: "GPT-4o-transcribe-diarize"). Analisei o código principal em `backend/core/transcription.py` (linha ~830). Atualmente, a função que escolhe a melhor transcrição (Azure Speech, Fast, ou GPT-4o) está preenchendo a `selected_strategy` e `selected_reason`, mas está **esquecendo de adicionar a chave `selected_provider`** no dicionário de resposta principal. A chave só está sendo preenchida na rota de "fallback" (Primary AI).
*   **Impacto:** Partes do sistema ou relatórios do frontend que dependem da informação "Qual motor transcreveu isso?" podem quebrar ou exibir dados vazios.
*   **Correção Necessária:** Ajustar o arquivo `transcription.py` para adicionar o campo `selected_provider` no objeto de metadados antes de retorná-lo.

## 3. Falha no Catálogo de Regras de Gestores (`test_gestores_export_config.py`)
**Erro Técnico:** `AssertionError: None != 'MONDELEZ-MONITORAMENTO-II'`
*   **Investigação:** O teste de exportação simula o sistema procurando uma etiqueta chamada `"Monitoramento II - Receptivo"` para vinculá-la ao ID oficial `"MONDELEZ-MONITORAMENTO-II"`. Ao verificar o arquivo de regras oficial (`backend/db/scoring_rules.yaml`), notei que esse alerta/critério não existe mais lá. Atualmente o catálogo de Mondelez possui apenas o `"MONDELEZ-MONITORAMENTO-I"` e `"MONDELEZ-LOGISTICA-REVERSA"`. Como a regra não existe, a busca retorna `None`, e o teste quebra.
*   **Impacto:** Impede a validação das exportações de relatórios de gestão, embora o impacto prático na produção hoje dependa apenas das regras ativas no YAML.
*   **Correção Necessária:** Atualizar o teste automatizado para refletir o catálogo atualizado (por exemplo, testando com a label `"Monitoramento I - Receptivo"` que existe).

---

**Recomendação:** Autorizar a correção desses 3 itens antes de realizar o deploy, garantindo assim que a master/produção sempre possua testes 100% passando.