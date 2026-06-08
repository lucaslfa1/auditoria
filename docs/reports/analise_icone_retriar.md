# Relatório de Análise: Ícones "Triar" e "Re-triar" em Itens Concluídos na Fila de Triagem

## Problema Reportado
Na fila de Triagem (painel de telefonia), alguns itens que já tiveram seu processamento de triagem concluído (já passaram pela IA) ainda continuam exibindo o botão "Re-triar". O usuário deseja entender o motivo desse comportamento.

## Análise do Código (Frontend)
Ao inspecionarmos o componente responsável por renderizar a fila de triagem (`src/features/classifier/components/RemoteTriageQueue.tsx`), identificamos a seguinte lógica responsável por determinar se o botão de Triar/Re-triar deve ser exibido:

```typescript
const classificationStatus = item.metadata?.classification_status;

// Verifica se o Alerta está ausente ou inválido
const alertEmpty = !item.alerta_previsto
  || item.alerta_previsto === 'erro'
  || item.alerta_previsto === 'desconhecido';

// Verifica se o Setor está ausente ou inválido
const sectorEmpty = !item.setor_previsto
  || item.setor_previsto === 'erro'
  || item.setor_previsto === 'desconhecido';

// Regra de exibição do botão
const showTriar = classificationStatus !== 'done' || alertEmpty || sectorEmpty;
const isRetry = classificationStatus === 'done';
```

## Motivo (Root Cause)
O botão "Re-triar" é ativado **intencionalmente** por uma regra de resiliência visual. 

Mesmo que a IA termine o trabalho dela (marcando o `classification_status` internamente como `'done'`), o sistema não considera a triagem como **plenamente satisfatória** se a IA não conseguiu decidir um setor válido ou um alerta válido.

Portanto, o botão "Re-triar" aparecerá em um item "completado" se:
1. A IA falhou em descobrir qual era o Setor (ficou vazio, 'erro' ou 'desconhecido').
2. A IA falhou em descobrir qual era o Alerta/Motivo da chamada (ficou vazio, 'erro' ou 'desconhecido').

O objetivo desse botão é permitir que o usuário ordene à IA tentar ouvir e classificar o áudio de novo, presumindo que a primeira tentativa "bateu na trave". 

## Como Contornar ou Resolver?
1. **Ação do Usuário:** Em vez de clicar em "Re-triar" esperando que a IA acerte de segunda, o auditor/gestor pode clicar no botão **"Editar"** ao lado, preencher manualmente qual é o Setor e o Alerta correto, e então enviá-lo.
2. **Alteração Sistêmica (Se desejado):** Se preferirmos que o botão de Triar desapareça *permanentemente* assim que a IA rodar 1 vez (mesmo que ela não descubra o setor/alerta), podemos alterar a linha `const showTriar = classificationStatus !== 'done'` no arquivo `RemoteTriageQueue.tsx`, removendo as travas `|| alertEmpty || sectorEmpty`.
