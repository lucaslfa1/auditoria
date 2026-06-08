# SQL Server DBA Checklist

Data de referencia: 2026-03-06

## Objetivo
Checklist objetivo do que pedir para o DBA quando a integracao read-only com SQL Server for iniciada.

## Acesso
- Nome do servidor ou instancia
- Porta TCP
- Nome do banco
- Tipo de autenticacao
- Usuario read-only dedicado
- Confirmacao de que o usuario tem apenas `SELECT`
- IPs, hostname ou VPN necessarios para conexao

## Seguranca
- TLS obrigatorio ou opcional
- Driver recomendado
- Necessidade de `TrustServerCertificate`
- Politica de troca de senha
- Janela de manutencao que possa afetar consultas

## Objetos de consulta
- Schema padrao
- Lista de `views` liberadas
- Lista de tabelas liberadas, se nao houver `views`
- Qual objeto deve ser considerado fonte oficial para operadores
- Coluna de chave unica por registro
- Coluna de ultima atualizacao para sync incremental

## Dados
- Significado exato de cada coluna
- Regras de nulidade
- Regras de status ativo/inativo
- Coluna correta de supervisor
- Coluna correta de escala
- Coluna correta de identificador de telefonia
- Coluna correta de setor ou organizacao

## Volume e operacao
- Volume aproximado de linhas por objeto
- Frequencia esperada de atualizacao
- Limite de consulta recomendado
- Horario de menor impacto para sincronizacao

## Preferencia tecnica
- Pedir `views` read-only estaveis em vez de consultar tabelas cruas
- Pedir uma coluna `updated_at` ou equivalente
- Pedir exemplos de consulta aprovados pelo DBA

## Consulta minima recomendada para operadores
- chave unica
- nome
- supervisor
- escala
- setor
- matricula
- id_huawei
- id_telefonia
- softphone_number
- status
- ultima_atualizacao

## Criterio de pronto antes da implementacao
- credencial testada
- objeto fonte definido
- amostra real validada
- regra de mapeamento para a base local aprovada
