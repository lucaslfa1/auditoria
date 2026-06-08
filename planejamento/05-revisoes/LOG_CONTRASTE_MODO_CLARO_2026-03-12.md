# Log de Contraste do Modo Claro - 2026-03-12

## Escopo
- Reforco de legibilidade no modo claro.
- Mais contraste entre texto, borda e superficie.
- Ajuste global para evitar correcoes isoladas por tela.

## Ajustes aplicados
- Escurecidas as variaveis de texto do tema claro em `src/index.css`.
- Reforcadas as bordas do modo claro com niveis `soft`, `subtle` e `strong`.
- Escurecidas as superficies claras de painel, card, toolbar, metricas e hero.
- Ajustados os fundos de `bg-slate-*`, `bg-white/*` e bordas `border-slate-*` no modo claro.
- Aumentado o contraste de botoes secundarios, ghost, filtros, navegacao e icones.
- Ajustados placeholders e inputs para leitura mais clara no modo claro.
- Escurecido o tom de destaque laranja quando exibido como texto no modo claro.
- Atualizado o teste de regressao do frontend para validar a regra de `select.glass-input option` sem prender em cores literais antigas.
- Escurecido o fundo base do modo claro para um cinza mais presente, com menos branco estourado no plano de fundo.
- Corrigidos estados desativados no modo claro para evitar botoes e campos apagados por opacidade baixa.
- Neutralizadas opacidades `disabled` no tema claro para manter leitura mesmo quando a acao estiver indisponivel.
- Removida a transparencia residual dos botoes no modo claro, incluindo variantes com `bg-transparent`, `bg-white/*` e tons de destaque com alpha.
- Convertidos os fundos dos componentes `.btn-*` do modo claro para superficies opacas.
- Ajustados de forma explicita em `Colaboradores` o badge de `Status`, o botao `Inativar selecionados` e o botao de inativar na linha para fundos opacos no modo claro.

## Arquivos principais
- `src/index.css`
- `tests/frontend-regressions.test.mjs`

## Validacao
- `npm run test:frontend`
- `npm run build`
