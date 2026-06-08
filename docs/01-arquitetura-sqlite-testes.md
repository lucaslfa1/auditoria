# Decisão Arquitetural: Uso de SQLite para Testes Automatizados

## Contexto
O sistema foi atualizado para utilizar o **Neon (Serverless PostgreSQL)** como banco de dados tanto no ambiente **Local** quanto no de **Produção** (Google Cloud Run).

No entanto, o código-fonte ainda retém funcionalidades transacionais voltadas ao banco local **SQLite** (por meio do mapeamento em `database.py` e `db/connection.py`).

## Decisão
**A funcionalidade de mapeamento envolvendo SQLite foi mantida estritamente com a finalidade de servir de banco virtual (Mock) para o ambiente de Testes Automatizados da aplicação.**

## Justificativas Técnicas

1. **Velocidade Extrema de Execução (Velocidade do Pipeline)**
   O projeto conta atualmente com centenas de testes unitários e de integração (quase 200 testes no back-end em Abril de 2026).
   Forçar a suíte de testes automáticos a bater em um banco real na nuvem a cada `INSERT`, `CREATE` ou `DELETE` para configurar e limpar o cenário de cada teste envolveria chamadas prolongadas de rede (Internet Rount-Trip).
   Utilizando um banco SQLite descartável in-memory (ou `test_*.db`), todo o ambiente do arquivo sobe imediatamente e os testes terminam em menos de 1 minuto.

2. **Isolamento Contíguo contra Acidentes (Segurança e Destrutibilidade)**
   Usar o PostgreSQL (Neon) para testar métodos de exclusão, edição forçada de arquivos acarreta um forte risco de que, se o teste falhar no meio, as rotinas deixem "lixo" no servidor da nuvem, ou corrompam tabelas importantes de Desenvolvimento. 
   O SQLite afasta 100% esse risco isolando os testes agressivos em um arquivo "fantasma" que automaticamente desaparece e volta ao lixo após a esteira aprovar o código.

3. **Isolamento de Credenciais na CI/CD (DevOps)**
   Possuir uma suíte de testes capaz de ser executada usando o SQLite local significa que a Pipeline do GitHub Actions (CI) pode levantar, rodar o `npm run test:backend` e validar toda a saúde da regra de negócio sem obrigar você a expor a String de Conexão sensível do Neon (PostgreSQL) para o container cego da automação do CI.

## Conclusão
- **Local (npm run up):** PostgreSQL (Neon)
- **Production (Google Cloud):** PostgreSQL (Neon)
- **Pipelines e Testes Automatizados:** Banco Mock (SQLite Isolado)
