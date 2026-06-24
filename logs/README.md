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

## Indice das versoes

O indice real e a propria pasta `logs/versions/` — um arquivo `x.y.z.md` por
versao, em ordem. Liste o diretorio para ver todas (vai ate **1.3.204** no
momento desta nota). **Nao** mantemos uma lista manual aqui: ela ficava
desatualizada (estava congelada no 1.3.42 enquanto a pasta ja tinha ~170
arquivos). O gerador `npm run log:new` cria o arquivo da versao, mas nao edita
este README.

- Versao mais recente: o maior `x.y.z` em `logs/versions/`.
- Criar a proxima: `npm run log:new` (proximo patch) ou `npm run log:new -- 1.3.x`.

## Registros operacionais (fora do versionamento x.y.z)

- `logs/versions/deploy_troubleshooting_2026-03-27.md`
- `logs/migracao_compliance_07_abril.md`
