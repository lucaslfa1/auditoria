# Correção da Coleta Huawei AICC — Priorização por `recordId`

**Data:** 02/05/2026
**Autor:** Lucas (com diagnóstico assistido)
**Componente:** `backend/core/huawei_sync.py`
**Severidade:** Alta — quase nenhuma ligação era baixada, derrubando o pipeline de auditoria de telefonia.

## Resumo Executivo

O sync da Huawei AICC executava normalmente, descobria milhares de chamadas por janela e ainda assim baixava 0–1 ligação por ciclo (taxa ≈ 5 %). O orçamento de 20 tentativas por execução era integralmente consumido por chamadas **sem gravação**, devido à forma como os candidatos eram ordenados (apenas por duração e horário). Após adicionar `bool(recordId)` como primeira chave do sort, a taxa subiu para **20/20 (100 %)** no mesmo ambiente, sem mais alterações.

## Sintoma Observado

| Métrica em prod (`huawei_sync_logs` — 27/04 a 02/05) | Valor |
|---|---|
| Tentativas registradas | 42 |
| Sucessos | 2 |
| Falhas com `failure_reason='audio_not_found'` | 40 |

O usuário relatou: "sync executa mas baixa 0 ligações". Apenas duas ligações dos dias 26/04 21:00 e 27/04 00:00 estavam disponíveis no ambiente em nuvem, e novas tentativas não produziam mais downloads.

## Investigação

### 1. Configuração e credenciais — íntegras
Tabela `configuracoes` continha os mesmos valores do último ciclo bem-sucedido (26/04 21:00):
- `huawei_auth_mode = proxy`
- `huawei_proxy_ip = 163.176.162.83`
- `huawei_obs_ak/sk/bucket/endpoint` válidos
- Auth via Teledata respondendo HTTP 200
- VDN `querycalls` respondendo HTTP 200

### 2. Conectividade e fallback OBS — íntegros
- Acesso ao bucket `obs-nstech-opentech` validado.
- Listagem direta de `Voice/{date}/{phone}/` retorna milhares de subpastas e arquivos `.V3` para datas recentes.
- Listagem de `Contact_Record/contact-record/10-minutes/{date}/` retorna manifests CSV completos.

### 3. A pista — análise dos manifests CSV
Lendo `Contact_Record/contact-record/10-minutes/20260430/TLD_Contact_Rec_*.csv` ficou evidente que o manifesto contém **dois tipos de chamadas misturadas**:

| `callId` | `recordId` | Tem `.V3` no OBS? |
|---|---|---|
| `1777516670-407526` | `177751674560989921373222786316` | **Sim** |
| `1777516659-407524` | `177751667585577219141725867365` | **Sim** |
| `1777516364-407498` | `177751645408464429815555566811` | **Sim** |
| `1777516248-17256970` | (vazio) | **Não** |
| `1777516862-407537` | (vazio) | **Não** |

**Conclusão**: chamadas com `callId` no formato `{epoch}-{17xxxxxxx}` (8 dígitos no `part2`) representam interações sem gravação (chamadas em fila, transferências, eventos sem áudio), e o `recordId` desses registros vem **vazio** no manifest. Nestes casos, tanto `CC-FS/downloadRecord` quanto o fallback OBS direto retornam vazio (FS responde `0300012 "No data found"`).

### 4. A causa
Em `_download_candidate_sort_key` (`backend/core/huawei_sync.py:480`), o sort original era:

```python
def _download_candidate_sort_key(interacao: dict) -> tuple[int, int]:
    return (
        get_call_duration_seconds(interacao),
        _coerce_huawei_time_ms(interacao.get("beginTime")) or 0,
    )
```

Com `reverse=True`, isso prioriza chamadas **mais longas e mais recentes**. Ocorre que chamadas longas tendem a ser exatamente as **sem gravação** (filas e transferências costumam ter duração maior que ligações reais). Resultado: as 20 tentativas por ciclo eram consumidas por candidatos sem áudio, deixando ligações realmente gravadas de fora.

## Correção

`backend/core/huawei_sync.py:480` — adicionada `bool(recordId)` como primeira chave do sort:

```python
def _download_candidate_sort_key(interacao: dict) -> tuple[int, int, int]:
    record_id = str(interacao.get("recordId") or "").strip()
    return (
        1 if record_id else 0,
        get_call_duration_seconds(interacao),
        _coerce_huawei_time_ms(interacao.get("beginTime")) or 0,
    )
```

Mudança mínima e localizada: candidatos com `recordId` preenchido vão antes; entre estes, mantém-se a ordem original (maior duração, mais recente). Nenhum filtro foi adicionado — chamadas sem `recordId` ainda podem ser tentadas se houver orçamento sobrando.

## Validação

Mesmo ambiente, mesma janela (`--horas 48`), mesmo limite de tentativas (`HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS=20`):

| Métrica | Antes da correção | Depois da correção |
|---|---|---|
| `chamadas_descobertas_total` | 9 843 | 9 441 |
| `candidatos_download` | 20 | 20 |
| `tentativas_download` | 20 | 20 |
| `download_fs_miss` | **19** | **0** |
| `obs_fallback_misses` | 19 | 0 |
| `baixadas` | **1** | **20** |
| `enfileiradas` | 1 | 20 |
| Taxa de sucesso | 5 % | **100 %** |

Logs de execução em `backend/logs/huawei_sync/`.

## Teste de Regressão

Adicionado em `backend/tests/test_huawei_sync.py`:

```python
def test_download_candidate_sort_prioritizes_calls_with_record_id(self):
    gravada_curta = {"recordId": "792075", "duration": 30, "beginTime": 1000}
    nao_gravada_longa = {"recordId": "", "duration": 600, "beginTime": 2000}
    gravada_longa_recente = {"recordId": "792100", "duration": 120, "beginTime": 3000}

    ordered = sorted(
        [nao_gravada_longa, gravada_curta, gravada_longa_recente],
        key=huawei_sync._download_candidate_sort_key,
        reverse=True,
    )

    self.assertEqual(
        [c["recordId"] for c in ordered],
        ["792100", "792075", ""],
    )
```

Suite completa: `21 passed`.

## Pontos de Atenção (não cobertos por esta correção)

1. **Cron em produção parou em 30/04 09:06** — a tabela `huawei_sync_logs` não tem nenhuma tentativa em prod entre 30/04 e 02/05. O Cloud Scheduler que dispara `POST /api/telefonia/cron/sync` precisa ser verificado.
2. **Janela retroativa** atualmente em 48 h (`huawei_horas_retroativas = 48`). Combinada com o limite de 20 downloads por ciclo, ainda é necessário rodar várias vezes para drenar a fila de gravações disponíveis. Considerar elevar `HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS` em produção quando o cron voltar a rodar.
3. **Manifesto de rede atualizado** (`docs/infra/HUAWEI_NETWORK_MANIFEST.md`): os IPs `34.171.63.68` (us-central1) e `189.38.107.13` (rede NSTECH) deixam de figurar como descontinuados e passam a constar como **validados na whitelist**, junto com `35.199.111.152` (SP).

## Arquivos Alterados

- `backend/core/huawei_sync.py` — sort priorizando `recordId`.
- `backend/tests/test_huawei_sync.py` — teste de regressão.
- `docs/infra/HUAWEI_NETWORK_MANIFEST.md` — revalidação dos IPs de saída.
- `docs/reports/relatorio-fix-coleta-huawei-record-id-2026-05-02.md` — este relatório.
