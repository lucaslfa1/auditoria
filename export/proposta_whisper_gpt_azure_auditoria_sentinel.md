# Proposta (PPT) - Transcricao e Analise de Transcricoes (Auditoria + Sentinel)

## Slide 1 - Titulo
**Transcricao e Analise Automatizada de Ligacoes e Ocorrencias**
- Projetos: Auditoria e Sentinel
- Proposta: Whisper (transcricao) + GPT no Azure (analise)
- Objetivo: ganhar escala, padronizar qualidade e gerar evidencias auditaveis

Notas do apresentador:
- Hoje temos um volume crescente de chamadas/ocorrencias. A informacao esta no audio, mas nao vira dado acionavel com rapidez.
- A proposta cria um pipeline padrao: transcrever com alta qualidade e analisar com modelo no Azure para gerar achados, evidencias e relatorios.

Visual sugerido:
- Um fluxo simples: Audio -> Transcricao -> Analise -> Insights/Relatorio/Alertas.

---

## Slide 2 - Contexto e Dor (Operacoes)
- Tempo alto para revisar chamadas e escrever relatorios
- Variacao de criterio entre analistas (inconsistencia)
- Baixa rastreabilidade: "por que" um item foi marcado
- Dificuldade de pesquisar: audio nao e indexavel como texto

Notas do apresentador:
- A dor e operacional: custo de tempo e perda de padrao. Isso impacta velocidade de resposta e qualidade do atendimento/controle.

Visual sugerido:
- Tabela "Antes": manual, lento, pouco padrao, pouca evidencia.

---

## Slide 3 - Objetivo e Resultado Esperado
- Transformar audio em texto confiavel e pesquisavel
- Gerar analises padronizadas: resumo, achados, riscos, recomendacoes
- Evidencia auditavel: trechos citados + timestamps
- Aumentar cobertura: mais chamadas avaliadas com o mesmo time

Notas do apresentador:
- Nao e "substituir auditor". E aumentar produtividade e consistencia, com trilha de evidencia para revisao humana quando necessario.

---

## Slide 4 - O Que Entra e o Que Sai (Auditoria e Sentinel)
- Entradas: audio (wav/mp3/mpeg), metadados (cliente, canal, operador, data, tipo)
- Saidas Auditoria: checklist preenchido, pontuacao/score, nao conformidades, evidencias
- Saidas Sentinel: alertas, categorias de risco, severidade, resumo acionavel, recomendacoes

Notas do apresentador:
- Importante para TI: outputs podem ser estruturados (JSON) para integracao com banco/dashboards.

---

## Slide 5 - Por que Whisper (API) para Transcricao
- Foco em acuracia para linguagem natural e cenarios ruidosos
- Suporte a timestamps para evidencias e navegacao no audio
- Pipeline escalavel (processamento por lotes ou fila)
- Resultado padrao para alimentar modelos/relatorios de forma consistente

Notas do apresentador:
- A transcricao e a fundacao. Se a transcricao for fraca, toda analise fica fraca.
- Whisper e escolhido pelo custo-beneficio e qualidade em PT-BR e variacoes de fala do dia a dia.

---

## Slide 6 - Por que GPT no Azure para Analise
- Extracao e sumarizacao: itens acionaveis a partir de texto longo
- Classificacao e padronizacao: aplicar criterios e gerar saidas consistentes
- Governanca corporativa: controle de acesso, auditoria de uso, integracao com Azure (Key Vault/Monitor)
- Flexibilidade: ajustar prompts/criterios sem reescrever codigo

Notas do apresentador:
- Aqui esta o "cerebro": transformar transcricao em decisao e relatorio padronizado.
- A escolha do Azure ajuda TI com governanca e integracao.

---

## Slide 7 - Arquitetura Proposta (Alto Nivel)
- 1) Ingestao: upload do audio + metadados (Auditoria/Sentinel)
- 2) Transcricao: Whisper -> texto + timestamps
- 3) Normalizacao: limpeza, segmentacao, opcional mascaramento de PII
- 4) Analise: GPT (Azure) -> JSON de achados/score/evidencias
- 5) Persistencia: DB/Storage + indexacao para busca + trilha de auditoria

Notas do apresentador:
- Componentes desacoplados. Se um provedor/motor mudar, nao recomeçamos do zero.
- Processamento via fila para controle de custo e priorizacao.

Visual sugerido:
- Diagrama em caixas com setas e um "queue" no meio.

---

## Slide 8 - Seguranca, Privacidade e Compliance (Pontos Para TI)
- Dados minimizados: enviar apenas o necessario para transcrever/analisar
- Segredos em Key Vault, acesso via Managed Identity (quando aplicavel)
- Criptografia em transito e repouso (Storage/DB)
- Retencao por politica: audio/transcricao/relatorio com prazos definidos
- PII: estrategia de redacao/mascaramento antes de analises mais amplas (quando exigido)

Notas do apresentador:
- O foco e reduzir risco: controles de acesso, observabilidade e politica clara de retencao.
- A trilha de auditoria inclui: versao do prompt, modelo, data/hora, e id do processamento.

---

## Slide 9 - Qualidade e Confiabilidade (Evidencia + Revisao)
- Saidas com citacoes: cada achado aponta trecho e timestamp
- Regras anti-alucinacao: respostas estruturadas (JSON) + validacao de schema
- Thresholds e filas de revisao: itens criticos sempre revisados por humano
- Monitoramento de qualidade: amostragem e comparacao por canal/cliente

Notas do apresentador:
- O modelo nao "decide sozinho" em itens criticos. Ele sugere com evidencias para o auditor validar.

---

## Slide 10 - Custos e Controle (Como Evitar Surpresa)
- Custo variavel por minuto de audio (transcricao) + por tokens (analise)
- Controles: limites por cliente/projeto, batch, cache de transcricoes
- Estrategia em camadas:
  - Triagem barata (resumo + classificacao simples)
  - Analise completa apenas quando necessario
- Relatorios de consumo e custo por unidade (time/cliente/canal)

Notas do apresentador:
- TI costuma perguntar "vai explodir custo?". A resposta e: governamos via fila, limites e processamento por camadas.

---

## Slide 11 - Plano de Implantacao (30/60/90)
- 0-30 dias: MVP com transcricao + resumo + busca + exportacao
- 31-60 dias: criterios de auditoria automatizados + score + evidencias
- 61-90 dias: alertas Sentinel, governanca completa (PII/retencao), dashboards

Notas do apresentador:
- Entregas incrementais: valor cedo e evolucao controlada.

---

## Slide 12 - Metricas de Sucesso (Operacoes + TI)
- Operacoes: tempo por caso, cobertura (% chamadas analisadas), retrabalho
- Qualidade: concordancia com auditoria humana, taxa de falso positivo em alertas
- TI: custo por hora analisada, latencia, disponibilidade, auditoria de acesso

Notas do apresentador:
- Isso vira compromisso de acompanhamento (mensal) e ajustes de criterios/prompt.

---

## Slide 13 - Pedido de Aprovacao / Decisoes
- Aprovar o uso de:
  - Whisper API para transcricao
  - Azure OpenAI (GPT) para analise
- Aprovar a arquitetura com fila + storage + logs de auditoria
- Definir 1 piloto: cliente/canal e volume (para calibrar custo e qualidade)

Notas do apresentador:
- Objetivo hoje: "sim" para piloto controlado e governado, com metricas claras.

---

## Slide 14 (Opcional) - Alternativas e Por que Esta Combinacao
- Manual: nao escala e e inconsistente
- Somente STT: vira texto, mas nao vira decisao/relatorio
- Regras fixas: fragil para linguagem natural e muda muito com operacao
- STT + LLM governado: melhor equilibrio entre escala, qualidade e controle

---

# Appendix (para TI, se perguntarem)

## A1 - Saida Estruturada (Exemplo de Campos)
- call_id, cliente, data
- resumo
- score_geral
- itens: criterio_id, status, evidencias[{inicio,fim,trecho}], recomendacao
- riscos: categoria, severidade, justificativa_com_trecho

## A2 - Controles Tecnicos Recomendados
- Rate limiting por projeto/cliente
- Filas com reprocessamento e DLQ
- Logs sem payload sensivel (quando possivel), com ids correlacionaveis
- Versionamento de prompts e criterios (ex.: arquivos em repo + hash no processamento)

## A3 - Opcao de "Plano B" (Se TI exigir 100% Azure)
- Manter o mesmo desenho, mas trocar o motor de transcricao por um servico de STT do Azure
- Mantem o GPT no Azure e reaproveita toda a camada de normalizacao/analise

