# Logs de Versao

Esta pasta guarda o historico de mudancas do projeto.

## Estrutura
- `logs/TEMPLATE.md` -> modelo padrao de registro.
- `logs/versions/x.y.z.md` -> registro de cada micro versao.

## Convencao
- Nome do arquivo: `x.y.z.md` (ex: `1.1.1.md`).
- Ordem de incremento: patch (`z`) para ajuste pequeno, minor (`y`) para bloco funcional novo, major (`x`) para quebra de compatibilidade.
- Codificacao: manter texto limpo e estavel; em caso de duvida de terminal/encoding, preferir ASCII.
- Sempre registrar:
  - objetivo;
  - mudancas;
  - arquivos alterados;
  - comandos de validacao e resultado;
  - pendencias.

## Fluxo rapido
1. Copiar `logs/TEMPLATE.md`.
2. Criar novo arquivo em `logs/versions/`.
3. Preencher com fatos objetivos (sem suposicoes).
4. Registrar comandos executados e status real.
5. Documentar bugs com ID sequencial (BUG-NNN) e severidade.
6. Registrar testes com metricas concretas (ex: confianca, accuracy).
7. Incluir conclusoes tecnicas para referencia futura.

## Convencao de autoria
- Consultar os logs existentes antes de fazer alteracoes.
- Criar um registro de versao ao concluir mudancas significativas.

## Geracao automatica
- `npm run log:new` -> cria a proxima versao patch automaticamente (ex: `1.1.4` -> `1.1.5`).
- `npm run log:new -- 1.2.0` -> cria versao especifica.
- `npm run log:new -- --dry-run 1.2.0` -> mostra o conteudo sem gravar arquivo.
- `npm run log:new -- 1.2.0 --authors=user` -> define autores no bloco YAML.

## Versoes registradas
- `1.3.36` -> [logs/versions/1.3.36.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.36.md)
- `1.3.37` -> [logs/versions/1.3.37.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.37.md)
- `1.3.38` -> [logs/versions/1.3.38.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.38.md)
- `1.3.39` -> [logs/versions/1.3.39.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.39.md)
- `1.3.40` -> [logs/versions/1.3.40.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.40.md)
- `1.3.41` -> [logs/versions/1.3.41.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.41.md)
- `1.3.42` -> [logs/versions/1.3.42.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/1.3.42.md)

## Registros operacionais
- `deploy_troubleshooting_2026-03-27` -> [logs/versions/deploy_troubleshooting_2026-03-27.md](/C:/Users/lucas.afonso/projetos/auditoria/logs/versions/deploy_troubleshooting_2026-03-27.md)
