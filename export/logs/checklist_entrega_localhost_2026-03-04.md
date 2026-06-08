# Checklist de Entrega Localhost 2026-03-04

## Antes de comecar
- Confirmar backend em `http://localhost:8000`
- Confirmar `GET /api/health` com status `200`
- Confirmar login no sistema

## Validacao minima
1. Subir um audio de `CADASTRO`
- Esperado:
  - transcricao concluida
  - resumo sem inventar regra de senha se o alerta nao exigir senha
  - `ai_feedback` aparece na tela

2. Subir um audio de `Ponto de Apoio`
- Esperado:
  - interlocutor com rotulo `Ponto de Apoio`
  - operador identificado nas perguntas operacionais principais

3. Subir um audio de `Policia`
- Esperado:
  - interlocutor com rotulo `Policia`
  - apresentacao do operador como rastreamento/sinistro com `Operador`

4. Editar a transcricao e reavaliar
- Esperado:
  - reauditoria sem reenviar audio
  - preservacao de `source_type`
  - preservacao de `audio_quality`

5. Forcar um caso de zeragem
- Esperado:
  - resumo com motivo concreto da nota zero
  - nao usar texto generico como `violacao nao negociavel`

## Sinais de alerta
- speaker invertido logo na abertura
- resumo citando senha/despedida fora do contexto
- nota zerada sem explicar o motivo
- reavaliacao apagando contexto de audio/pdf

## Se algo falhar
1. Reiniciar o backend com `powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1`
2. Repetir o caso no `localhost`
3. Conferir os logs em `export/logs/`
