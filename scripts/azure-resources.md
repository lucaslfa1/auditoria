# Arquitetura de Inteligência Artificial Azure - NSTECH Audit

> Atualizado em: 2026-04-09 (Revisão Definitiva Pós-Migração)

Devido às pesadas restrições e limites de cota da Microsoft, a estrutura de Inteligência Artificial da NSTECH foi dividida em rotas dedicadas.
O não-cumprimento do mapeamento exato (combinando Região + Endpoint + Deployment Name) abaixo causará erros de **HTTP 404 (Not Found)** e **HTTP 503 (Unavailable)** na Triagem.

---

## 1. O Cérebro Textual (Avaliação Pura)
Hospedado no norte da Europa por possuir as maiores folgas de limite (Rate Limits) para geração de texto denso. Usado para ler a transcrição e gerar o JSON do relatório.

**Recurso:** `lucas-mm2utvqb-swedencentral` (Sweden Central)
* **Endpoint:** `https://lucas-mm2utvqb-swedencentral.cognitiveservices.azure.com/`
* **Implantação (Deployment):** `gpt-4o`
* **Versão Atrelada:** `2024-11-20` (Standard)

## 2. Separação de Locutores (Diarization)
Hospedado via Foundry com foco no modelo híbrido de análise de Áudio para saber *quem está falando o que* na chamada telefônica.

**Recurso:** `Auditoria-IA-E2` (East US 2)
* **Endpoint:** `https://eastus2.api.cognitive.microsoft.com/`
* **Implantação (Deployment):** `gpt-4o-transcribe-diarize`
* **Nota Crítica:** Esse modelo é exclusivamente "transcribe-diarize", tentar passar texto puro para ele resultará em falha.

## 3. Transmissão de Voz (Speech to Text Otimizado)
Substituiu antigas instâncias e centralizou todas as quebras de áudios rápidos e streams da nossa conversão.

**Recurso:** `Auditoria-IA` (East US)
* **Endpoint:** `https://eastus.api.cognitive.microsoft.com/`

## 4. Análise Orgânica / Sentimento 
Recurso gratuito usado para detecção nativa de emoções nas flutuações das avaliações do Nível 1.

**Recurso:** `nstech-voz` (Brazil South)
* **Endpoint:** `https://nstech-voz.cognitiveservices.azure.com/`
* **Tipo:** `TextAnalytics`

## 5. Whisper Isolado (Fallback Legado)
Isolado propositalmente na cota antiga para que as transcrições de longo alcance não consumam a faixa de banda dos nossos modelos inteligentes principais.

**Recurso:** `nstech-bas` (East US 2)
* **Endpoint:** `https://nstech-bas.openai.azure.com/`
* **Implantação (Deployment):** `nstech-bas-whisper`

---

## Mapeamento Rigoroso no `.env` do Cloud Run

Abaixo, os nomes exatos das variáveis consumidas pelo `backend/core/config.py`. Chaves sensíveis ficam omitidas.

```env
# 1. GPT-4o (Leitor / Avaliador Principal -> Suécia)
AZURE_OPENAI_ENDPOINT=https://lucas-mm2utvqb-swedencentral.cognitiveservices.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# 2. Reconhecimento de Múltiplos Locutores (Diarização -> East US 2 / Foundry)
AZURE_GPT4O_DIARIZE_ENDPOINT=https://eastus2.api.cognitive.microsoft.com/
AZURE_GPT4O_DIARIZE_DEPLOYMENT=gpt-4o-transcribe-diarize

# 3. Transcrição Padrão via Speech (East US)
AZURE_SPEECH_REGION=eastus
AZURE_SPEECH_ENDPOINT=https://eastus.api.cognitive.microsoft.com/

# 4. Análise de Sentimentos Textual
AZURE_TEXT_ANALYTICS_ENDPOINT=https://nstech-voz.cognitiveservices.azure.com/

# 5. Transcrição Legada Fallback Whisper (East US 2)
AZURE_WHISPER_ENDPOINT=https://nstech-bas.openai.azure.com/
AZURE_WHISPER_DEPLOYMENT=nstech-bas-whisper
```
