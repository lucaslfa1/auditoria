# Log de Revisão Gramatical - 2026-03-12

## Escopo
- Revisão de textos visíveis no frontend.
- Padronização de mensagens principais da API.
- Normalização visual de setores e escalas, com remoção do sufixo `ou padrão` quando usado apenas como fallback textual.

## Ajustes aplicados
- Corrigidos acentuação e redação em `Colaboradores`, `Ajustes`, `Auditoria` e `Triagem`.
- Padronizados rótulos como `Auditável`, `Matrícula`, `Ações`, `Usuários`, `Módulos` e `Inteligência artificial`.
- Tornadas mais objetivas as mensagens da tela de colaboradores, incluindo subtítulo e regra da auditoria.
- Corrigida a exibição de `BAS`, `Fenix`, setores compostos e escalas em múltiplas telas.
- Removido o sufixo `ou padrão` da exibição quando ele não representa informação operacional útil.
- Revisadas mensagens de erro da API em `admin`, `classifier` e `audit`.
- Compactada a coluna de ações em `Colaboradores`, trocando botões largos por ícones com `title` e `aria-label`.
- Deduplicado o filtro de setores em `Colaboradores` com chave canônica de exibição.
- Ao selecionar um supervisor em `Colaboradores`, o setor passa a ser preenchido automaticamente quando houver um único setor válido para ele.
- Quando o supervisor tiver mais de um setor em `Colaboradores`, a tela agora exibe um aviso curto pedindo a seleção manual do setor.
- Removida a redundancia visual entre `Status` e `Auditável` na tabela de `Colaboradores`: a listagem passou a usar uma única coluna `Situação`, com destaque apenas para a exceção `Ativo fora da auditoria`.
- O card `Auditáveis` foi trocado por `Fora da auditoria`, e o filtro/formulário foram renomeados para uma linguagem mais direta de operação.
- Padronizada a exibição de nomes e supervisores em `Colaboradores`, normalizando caixa alta para apresentação e salvamento sem apagar os dados antigos da base.
- Ocultados da gestão os quatro cadastros técnicos de telefonia `Contenção 1-4`, que não representam colaboradores reais e só poluíam a listagem.

## Arquivos principais
- `src/shared/lib/operationalLabels.ts`
- `src/features/settings/components/OperadorManagement.tsx`
- `src/features/settings/components/Settings.tsx`
- `src/shared/components/OperatorAutocompleteFields.tsx`
- `src/features/dashboard/components/Dashboard.tsx`
- `src/features/supervisor/components/SupervisorPortal.tsx`
- `src/features/saved-files/components/SavedFiles.tsx`
- `src/features/classifier/hooks/useClassifier.ts`
- `backend/routers/admin.py`
- `backend/routers/classifier.py`
- `backend/routers/audit.py`

## Validação
- `python -m py_compile backend/routers/admin.py backend/routers/classifier.py backend/routers/audit.py`
- `python -m pytest backend/tests -q`
- `npm run test:frontend`
- `npm run build`
