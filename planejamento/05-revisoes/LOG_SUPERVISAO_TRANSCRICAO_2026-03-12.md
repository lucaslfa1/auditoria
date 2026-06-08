# Log de ajuste - Supervisão com transcrição

Data: 2026-03-12

## Objetivo

Melhorar a tela de Supervisão para o supervisor conseguir apresentar a nota ao operador com base visível na própria auditoria.

## Alterações

- Adicionado endpoint de detalhe da auditoria em `backend/routers/supervisor.py` para carregar uma auditoria individual com `details`, `transcription` e `feedback`.
- A tela `SupervisorPortal` passou a buscar esse detalhe sob demanda ao abrir a auditoria.
- O bloco `Critérios avaliados` agora tenta localizar um trecho relacionado da transcrição para cada critério e mostra o timestamp quando houver evidência textual suficiente.
- Adicionado bloco `Transcrição` logo abaixo de `Critérios avaliados`.
- Mantida regra conservadora: sem correspondência confiável, o sistema não exibe timestamp nem trecho inventado.

## Validação

- `python -m py_compile backend/routers/supervisor.py`
- `npm run test:frontend`
- `npm run build`

## Observação

O vínculo entre critério e transcrição é heurístico e depende do texto disponível em `details.comment`, `details.label` e nos segmentos da transcrição. O sistema evita falso positivo priorizando ausência de evidência em vez de sugerir um timestamp incorreto.
