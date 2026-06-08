# APIs Azure Necessárias para os Sistemas Auditoria e Sentinel

> Documento de arquitetura / infraestrutura.
> Escopo: ambiente Azure | Data original: 07/04/2026

1. Resumo Executivo

Para operar Auditoria e Sentinel com foco exclusivo em Azure, o conjunto principal de servicos e composto por Azure OpenAI e Azure AI Speech. O Azure OpenAI cobre a camada de inteligencia textual, laudos, classificacao e parte das transcricoes por audio/transcriptions; o Azure AI Speech cobre a transcricao primaria com diarizacao e melhor resposta operacional. O Azure AI Language pode complementar com sentimento, mas entra como enriquecimento analitico e nao como nucleo do fluxo.

A recomendacao pratica e provisionar um recurso Azure OpenAI com deployments separados para GPT-4o e Whisper, alem de um recurso Azure AI Speech para Fast Transcription. Isso cobre os dois sistemas sem dependencia de Gemini, Vertex ou AssemblyAI.

2. APIs Azure por Sistema

3. Conjunto Azure Recomendado

Um recurso Azure OpenAI com deployment de GPT-4o para Auditoria e Sentinel.

Um deployment de Whisper em Azure OpenAI para fallback de transcricao e cobertura de audio transcriptions.

Um recurso Azure AI Speech com Speech-to-Text / Fast Transcription habilitado, incluindo diarizacao.

Opcionalmente, um endpoint Azure AI Language para sentimento quando houver interesse em enriquecer analise emocional e relatorios.

4. Breve Defesa Tecnica

Padronizacao operacional: concentrar os dois sistemas em Azure reduz heterogeneidade de credenciais, governanca e observabilidade.

Resiliencia: combinar Azure AI Speech com Azure OpenAI Whisper evita dependencia de um unico mecanismo de transcricao.

Qualidade de resultado: GPT-4o cobre a camada decisoria de auditoria, laudo e classificacao com resposta estruturada e baixa variacao.

Escalabilidade: Azure OpenAI e Azure AI Speech podem ser dimensionados por deployment, quota e regiao sem alterar a arquitetura funcional.

Seguranca e compliance: centralizar em Azure simplifica gestao de segredo, controle de acesso e trilha de auditoria corporativa.


### Tabela 1

| Sistema | API Azure | Finalidade | Motivo tecnico |
|---|---|---|---|
| Auditoria | Azure OpenAI Chat Completions (deployment GPT-4o) | Avaliacao de criterios, reavaliacao e classificacao textual | O backend usa Azure OpenAI como caminho principal de avaliacao e classificacao. Sem esse deployment, o nucleo decisorio do sistema fica indisponivel. |
| Auditoria | Azure AI Speech / Fast Transcription | Transcricao primaria de audio com diarizacao | O pipeline Azure do Auditoria entra primeiro em Fast Transcription quando o ambiente esta em modo Azure. E o ponto principal de STT para operacao. |
| Auditoria | Azure OpenAI Audio Transcriptions (Whisper deployment) | Fallback de transcricao | Mantem resiliencia quando a transcricao principal falha ou precisa de rota alternativa controlada. |
| Auditoria | Azure OpenAI Audio Transcriptions com deployment de diarizacao GPT-4o | Diarizacao reforcada e roteamento inteligente por setor | O codigo contem rota Azure para gpt-4o diarize e pode promov?-la como primaria em cenarios especificos, melhorando robustez de falante. |
| Auditoria | Azure AI Language / Text Analytics | Sentimento experimental | A funcionalidade existe no sistema, mas atua como enriquecimento analitico do resultado. |
| Sentinel | Azure OpenAI Chat Completions (deployment GPT-4o) | Laudos, auditoria textual e analise de oitiva | DescricaoAnaliseService depende de Azure OpenAI como provedor efetivo para os fluxos textuais principais. |
| Sentinel | Azure AI Speech / Fast Transcription | STT principal com diarizacao | TranscricaoController e AzureFastTranscricaoService tratam Azure Speech como rota principal de transcricao. |
| Sentinel | Azure OpenAI Audio Transcriptions (Whisper deployment) | Fallback de STT | O Sentinel possui servico dedicado de Whisper em Azure OpenAI para continuidade de processo quando a transcricao principal degrada. |
| Sentinel | Azure AI Language / Text Analytics | Analise de sentimento textual | Quando indisponivel, o controlador faz fallback para analise acustica no microservico Python; portanto agrega valor como complemento. |
