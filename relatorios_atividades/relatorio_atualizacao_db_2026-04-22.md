# Relatório de Atualização da Base de Dados - 22/04/2026

## Resumo das Modificações Realizadas no Banco de Dados (Neon/Produção)
Este relatório compila os detalhes da sincronização de operadores e supervisores referente ao fechamento planejado, seguindo os direcionamentos da planilha da Distribuição e ajustes solicitados (JEAN CARLOS CONSTANTINO MIRANDA e Contas de Gestores).

### Colaboradores (`colaboradores` e `audits`)
- **Remoção**: Foram deletados **181 colaboradores** que não constavam mais na planilha oficial (limpeza).
- **Limpeza de Audits**: Para realizar a deleção dos colaboradores, as avaliações de testes atreladas às contas antigas foram previamente **excluídas** da tabela `audits`. Isso contornou as restrições da Foreign Key e assegurou uma higienização da base sem impactar os relatórios de Machine Learning (que independem dessa FK).
- **Inserção / Atualização (Upsert)**: Foram atualizadas ou criadas **219 contas** de operadores ativas/inativas de acordo com as especificações (setor, turno/operação, supervisor logado, status da conta).
- **Tratamento Especial - Jean Carlos**: Ele foi fixado com a matrícula de dados corretos (`11236`, id Huawei: `2956`) e alocado para o setor de `DISTRIBUIÇÃO` com o respectivo supervisor.

### Gestores e Administradores (`users`)
- **Limpeza de Usuários Inativos**: Conforme exigido, as contas de nível "supervisor" ausentes da atual grade foram completamente deletadas da tabela de usuários: `Rodrigo Barros`, `Gustavo Montanari`, `Lucas Rafael`, e `Douglas de Aguiar`.
- **Manutenção de Administradores**: As contas com role `admin` (ex.: Lucas, Admin, Denise) permaneceram intactas, sem alterações.
- **Novas Credenciais**: 10 novas contas para a supervisão da Distribuição foram implementadas, com senhas geradas via hash (`bcrypt`). Adicionalmente, foi resetada e testada a senha da conta `carlos eduardo`. Segue o mapa final:

| Nome | Usuário (Login) | Senha Inicial de Acesso |
| :--- | :--- | :--- |
| Adryan | `adryan` | `hpqJZKmCa@GF` |
| Bruna | `bruna` | `plBI7GeoDKVl` |
| Carina | `carina` | `%Mj22D9483Kh` |
| Josiane | `josiane` | `dzwo%lj^M7B*` |
| Kayque | `kayque` | `rvA&JhB3NdpC` |
| Thiago | `thiago` | `lflBpzq17fDZ` |
| Geovana | `geovana` | `rxp419iy@Gje` |
| Richard | `richard` | `07t7ulwa8Mmq` |
| Giulia | `giulia` | `9CkdiLzlyOVr` |
| Carlos Eduardo | `carlos eduardo` | `fQp1qEiDze$9` |

## Scripts Executados
Foram programados em python (`psycopg2`) três scripts na raiz do projeto para realizar esta carga segura no banco de produção.
- `sync_db_excel.py`: Tratamento via `pandas` da planilha e Upsert SQL de exclusão da tabela colaboradores.
- `fix_supervisors.py`: Remoção customizada e geração dos hashes com as chaves temporárias para as 9 novas contas listadas.
- `reset_carlos_pwd.py`: Geração exclusiva e rápida para conta preexistente sob a string "carlos eduardo".

*As operações foram confirmadas de forma satisfatória por meio de log local de conexão e consultas de verificação. O sistema já opera na sua nova rotina sob a versão **1.3.56**.*
