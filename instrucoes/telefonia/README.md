# Telefonia

Esta pasta existe para receber insumos locais da operacao de telefonia, usados pelo importador `backend/import_telefonia.py`.

## O que fica local
- planilhas reais com nomes, IDs, supervisor, status e demais dados operacionais;
- exports temporarios de fornecedor ou telefonia;
- qualquer arquivo com dado pessoal, identificador interno ou snapshot operacional.

## O que pode ser versionado
- este `README.md`;
- este `.gitignore`;
- exemplos anonimizados ou templates, se forem realmente necessarios no futuro.

## Regra pratica
- mantenha os `.xlsx` reais aqui no ambiente local;
- nao suba essas planilhas para o Git;
- o importador ja procura automaticamente o arquivo `.xlsx` mais recente desta pasta.
