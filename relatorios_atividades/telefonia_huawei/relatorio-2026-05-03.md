# Relatório de Atividades - 03 de Maio de 2026

## Demandas Resolvidas (Módulo de Telefonia)

1. **Botão de Remover Ligações na Triagem:**
   - Adicionado um botão "Remover" (com ícone de "X") ao lado do botão de auditar na tabela de gravações (`RecordingsList.tsx`).
   - Criada a rota de backend `DELETE /api/telefonia/recordings/{hash}` em `telefonia.py`.
   - Comportamento implementado: Ligações já auditadas ou com cota mensal atingida são apenas **ocultadas da tela** (marcadas como `archived`). Ligações não auditadas (pendentes ou classificadas) são apagadas definitivamente do banco e do log de sincronização, liberando espaço e permitindo que a integração as baixe novamente no futuro.

2. **Edição de Ligações (Scroll e Setor UTI-RJ):**
   - Adicionadas classes Tailwind (`max-h-72 overflow-y-auto`) na caixa de edição in-line, habilitando a **barra de rolagem (scrollbar)** para a escolha de Supervisor, Setor e Escala sem quebrar o layout da tabela.
   - Ajustada a lógica do dropdown de "Classificação" para suportar setores que não possuam alertas cadastrados (como frequentemente ocorre com **UTI-RJ**). O botão de salvar agora é destravado corretamente mesmo que a lista de classificações esteja vazia para o setor selecionado.

3. **Correção na Busca por Intervalo e Download OBS:**
   - Corrigido o erro de `fuso horário` no interpretador de datas da Huawei (`_coerce_to_epoch_ms` em `huawei_obs_client.py`). Ao invés de interpretar os relatórios do `Contact_Record` em UTC (+3h acima do Brasil), forçamos o sistema a ler a data como `America/Sao_Paulo`. 
   - Isso elimina o problema reportado onde a VDN devolvia "0" resultados e os arquivos "falhavam" no OBS porque o fuso jogava a hora fora do intervalo válido.

4. **Correção de Bloqueio Falso de Credenciais:**
   - Removido o travamento estrito no formulário em `useTelefoniaSync.ts`. Antes o sistema bloqueava a busca padrão alegando "Credenciais Ausentes" (faltando AK/SK) caso o intervalo manual fosse desmarcado. Agora o frontend delega a validação ao backend, o que resolve o problema caso o sistema já funcione perfeitamente com Proxy (CCID + VDN apenas).

## Status
- **Repositório:** Alterações consolidadas, com `commit` efetuado no GitHub.
- **Produção:** Imagem construída manualmente no Artifact Registry e deploy via `gcloud run` no Cloud Run efetuado com sucesso.
