# Relatório de Melhorias Identificadas pela Auditoria

> [!IMPORTANT]
> Relatório baseado nos 3 documentos de ajustes enviados pelo setor de auditoria após uso do sistema.

---

## 📋 Resumo Executivo

A equipe de auditoria identificou **3 grandes áreas de melhoria** no sistema, documentadas nos arquivos da pasta `ajustes/`:

| Documento | Setor | Foco |
|-----------|-------|------|
| `Ajustes IA - Cadastro.docx` | Cadastro / Antecedentes | Detalhamento dos critérios existentes |
| `Ajustes IA - Checklist.docx` | Checklist / WhatsApp | Detalhamento e renomeação de plataforma |
| [auditoria_2026-03-03.docx](file:///c:/Users/lucas.afonso/projetos/auditoria/ajustes/auditoria_2026-03-03.docx) | Distribuição / Rastreamento / UTI / Fênix | **10 processos** com critérios revisados + regras de zerar auditoria |

---

## 🔴 Mudanças Críticas

### 1. Regras de "Zerar Auditoria" na Senha de Segurança (NOVO)
Os documentos trazem regras detalhadas que **não existem nos prompts atuais** sobre quando a auditoria inteira deve ser zerada:

| Situação que ZERA a auditoria | Presente no sistema atual? |
|-------------------------------|:-------------------------:|
| Operador não pede senha em nenhum momento | ❌ Não |
| Operador passa informação da viagem ANTES de confirmar a senha | ❌ Não |
| Operador solicita CPF no lugar da senha | ❌ Não |
| Motorista confirma CPF completo (11 dígitos) no lugar da senha | ❌ Não |
| Motorista informa senha incorreta e operador diz logo que está errada | ❌ Não |
| Operador dá dicas sobre a senha (quantidade de dígitos, "é o final da AE") | ❌ Não |
| Regra especial: se senha errada, confirmar outros dados e só no FINAL avisar | ❌ Não |
| Exceções: CPF aceito se motorista diz que não recebeu senha / está dirigindo | ❌ Não |

> [!CAUTION]
> Estas são **falhas críticas de segurança**. Quando ocorrem, a nota da auditoria inteira vai para ZERO. Isso precisa ser implementado como regra especial no prompt da IA.

### 2. Critério "Registro no sistema" → **REMOVER ou deixar para auditor**
Em **TODOS** os processos do arquivo [auditoria_2026-03-03.docx](file:///c:/Users/lucas.afonso/projetos/auditoria/ajustes/auditoria_2026-03-03.docx), o critério:
> *"O operador registrou corretamente o contato no sistema, incluindo número de telefone, nome do responsável, e resumo da conversa?"*

Tem a anotação: **"Retirar esse critério, pois não tem como a IA verificar essa informação. Ou deixar para que seja uma análise feita pelo auditor."**

Processos afetados: Alertas Prioritários (motorista/cliente), Posição em Atraso (motorista/cliente), Parada Indevida (motorista/cliente), Desvio de Rota (motorista/cliente), Ponto de Apoio, Acionamento Policial.

### 3. Critério "Bloqueio/Cadastro Negativado" → **FALHA CRÍTICA que ZERA**
No Cadastro, o documento detalha que se o operador informar que o cadastro está "bloqueado", "reprovado" ou que o condutor "não pode carregar", **a auditoria deve ser zerada**, pois isso pode gerar processo judicial.

---

## 🟡 Mudanças nos Critérios Existentes

### Cadastro – Antecedentes

| Critério | Mudança solicitada |
|----------|-------------------|
| Identificação (saudação, nome, setor, empresa) | Adicionado: "apenas primeiro nome já é suficiente", "pode informar setor OU empresa, não obrigatório os dois" |
| Bloqueio/cadastro negativado | 🔴 **Agora é falha crítica que ZERA** (detalhe acima) + texto explicativo sobre risco judicial |
| Inquérito/processo/apontamento | Adicionado: lista de documentos específicos (carta precatória, certidão de objeto e pé, certidão de homonímia) + necessidade de informar o ano |
| Estado/justiça federal | Detalhado: citar cidade, estado, ou informar que é justiça federal |
| Documento necessário | Lista expandida de documentos possíveis |
| Despedida | Adicionado: aceitar "amém", felicitações em datas comemorativas → atendimento humanizado |
| Silêncio prolongado | Limite mantido em **60 segundos** (diferente dos 45s da Distribuição) |
| Qualificação do atendimento | Adicionado: detalhamento que qualificação errada gera retrabalho para o auditor |
| Tom de voz | Detalhado: verificar proximidade ao microfone, respiração, ironia, sarcasmo, gírias repetidas |

### Checklist – WhatsApp

| Critério | Mudança solicitada |
|----------|-------------------|
| Identificação | Esclarecido: **só saudação** (sem nome, setor, empresa), pois é WhatsApp direto |
| Auto texto tipo de veículo | Texto exato especificado para copiar |
| Encerramento na plataforma | **"Weon" → "Huawei"** (nome da plataforma mudou) |
| Reprovação | Detalhado: informar motivo específico (sensor que não gerou, sinal não espelhado) |
| Imagens no SIL | Detalhado: precisam constar placa do veículo OU número do rastreador |
| Despedida | Padrão simplificado (sem "obrigada igualmente", sem "amém") |

### Distribuição – Processos Operacionais (10 processos)

#### Mudanças aplicáveis a TODOS os processos de contato motorista:
- Silêncio prolongado: **45 segundos** (confirmado, já correto no sistema)
- Detalhamento extensivo do critério de senha de segurança (regras de zerar)
- Motivo do contato: operador deve **evitar informar o tipo de alerta** diretamente por segurança

#### Novos processos / critérios detalhados:

| Processo | Critérios novos ou significativamente alterados |
|----------|-------------------------------------------------|
| **Alertas Prioritários – Motorista** | Regra de não informar o alerta específico; vídeo 360° com data/hora/senha; regras de zerar |
| **Posição em Atraso – Motorista** | Procedimentos para forçar posicionamento; identificação do motivo da perda de sinal; riscos de seguro |
| **Parada Indevida – Motorista** | Confirmar plano de viagem; orientar reinício imediato; riscos de seguro |
| **Desvio de Rota – Motorista** | Coletar itinerário alternativo; verificar plano de viagem; riscos de seguro |
| **Alertas Prioritários – Cliente** | Confirmar contatos do condutor; enfatizar suspeita de sinistro; informar ações adotadas |
| **Posição em Atraso – Cliente** | Questionar equipamento de contingência (isca, rastreador secundário); informações recentes |
| **Parada Indevida – Cliente** | Confirmar se pontos autorizados foram passados; medidas de segurança (escolta, pronta resposta) |
| **Desvio de Rota – Cliente** | Questionar se motorista avisou antecipadamente; trajeto programado vs realizado |
| **Ponto de Apoio** | Processo completo com critérios específicos (dados do veículo, referência de posição, verificar violações, chamar motorista) |
| **Acionamento Policial** | Processo completo com **alfabeto fonético** obrigatório; dados do conjunto e motorista; solicitar deslocamento; deixar 0800 |

---

## 🟢 Ações Recomendadas

### Prioridade Alta 🔴
1. **Implementar regras de "zerar auditoria"** no prompt da IA para senha de segurança
2. **Implementar regra de zerar** para bloqueio/cadastro negativado no Cadastro
3. **Remover/marcar critério "registro no sistema"** como análise exclusiva do auditor (não-IA)

### Prioridade Média 🟡
4. **Atualizar todos os prompts** com as descrições detalhadas dos critérios
5. **Renomear "Weon" → "Huawei"** no Checklist
6. **Adicionar novos processos**: Ponto de Apoio e Acionamento Policial (se não existem)
7. **Atualizar criteria.json** e banco de dados com as mudanças

### Prioridade Baixa 🟢
8. **Padronizar regras de despedida** com o texto sobre atendimento humanizado
9. **Adicionar detalhes de tom de voz** nos prompts

---

## 📊 Impacto no Sistema

| Componente | Arquivos afetados |
|------------|-------------------|
| Prompts IA | [audit-prompt/CRITÉRIOS DA AUDITORIA - CADASTRO-prompt.txt](file:///c:/Users/lucas.afonso/projetos/auditoria/audit-prompt/CRIT%C3%89RIOS%20DA%20AUDITORIA%20-%20CADASTRO-prompt.txt) |
| | [audit-prompt/CRITÉRIOS DA AUDITORIA - CHECKLIST-prompt.txt](file:///c:/Users/lucas.afonso/projetos/auditoria/audit-prompt/CRIT%C3%89RIOS%20DA%20AUDITORIA%20-%20CHECKLIST-prompt.txt) |
| | [audit-prompt/CRITÉRIOS DA AUDITORIA - DISTRIBUIÇÃO-prompt.txt](file:///c:/Users/lucas.afonso/projetos/auditoria/audit-prompt/CRIT%C3%89RIOS%20DA%20AUDITORIA%20-%20DISTRIBUI%C3%87%C3%83O-prompt.txt) |
| | `audit-prompt/normalized/` (mesmos arquivos) |
| Critérios JSON | `src/data/criteria.json`, `src/features/audit/data/auditCriteria.json` |
| Backend Config | `backend/config/prompts.json` |
| Banco de Dados | Critérios na tabela do SQLite (via `admin_criteria`) |
