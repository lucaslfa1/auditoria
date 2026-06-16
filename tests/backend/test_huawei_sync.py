import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import huawei_sync
from core.huawei_discovery import HuaweiDiscoveryService
from core.huawei_download_chain import DownloadResult
from core.classification import ClassificationResult


def _registered_operator(setor: str, **extra):
    operador = {"setor": setor, "id_huawei": "189", "huawei_registered": True}
    operador.update(extra)
    return operador


class TestHuaweiSync(unittest.IsolatedAsyncioTestCase):
    def test_missing_credentials_oauth_direct_requires_direct_keys(self):
        missing = huawei_sync._missing_credentials(
            {
                "auth_mode": "oauth_direct",
                "cc_id": "1",
                "vdn": "25",
                "ak": "proxy-ak",
                "sk": "proxy-sk",
            }
        )

        self.assertEqual(missing, ["direct_app_key", "direct_app_secret"])

    def test_missing_credentials_proxy_requires_ak_sk(self):
        missing = huawei_sync._missing_credentials(
            {
                "auth_mode": "proxy",
                "cc_id": "1",
                "vdn": "25",
                "direct_app_key": "direct-key",
                "direct_app_secret": "direct-secret",
            }
        )

        self.assertEqual(missing, ["ak", "sk"])

    def test_query_time_windows_splits_without_overlap(self):
        with patch.dict(os.environ, {"HUAWEI_QUERYCALLS_WINDOW_MINUTES": "60"}):
            windows = HuaweiDiscoveryService._query_time_windows(1000, 7_201_000)

        self.assertEqual(
            windows,
            [
                (1000, 3_601_000),
                (3_601_001, 7_201_000),
            ],
        )

    def test_query_time_windows_does_not_create_zero_length_tail(self):
        with patch.dict(os.environ, {"HUAWEI_QUERYCALLS_WINDOW_MINUTES": "60"}):
            windows = HuaweiDiscoveryService._query_time_windows(1000, 3_601_000)

        self.assertEqual(windows, [(1000, 3_601_000)])

    def test_make_filename_uses_telefonia_pattern(self):
        self.assertEqual(
            huawei_sync._make_filename("Joao da Silva", "CALL 123/ABC", "wav"),
            "ligacao_huawei_joao_da_silva_call_123_abc.wav",
        )
        self.assertEqual(
            huawei_sync._make_filename("Nao Identificado", "CALL-9", ".wav"),
            "ligacao_huawei_operador_nao_identificado_call_9.wav",
        )

    async def test_round_trip_preserva_direcao_real(self):
        """
        Camada 2 - Integration test de round-trip (mock servidor + dedupe).
        Garante que HuaweiDiscoveryService.buscar_chamadas_globais não embaralha as direções.
        """
        client = AsyncMock()

        # Mock retorna chamadas diferentes para cada direção
        # Importante: isCallIn NÃO vem na resposta do querycalls da Huawei,
        # o sync é que adiciona baseado na direção da query.
        client.buscar_historico_chamadas.side_effect = [
            [{"callId": "IN-1", "duration": 100}],  # Resposta para INBOUND
            [{"callId": "OUT-1", "duration": 150}], # Resposta para OUTBOUND
        ]

        result = await HuaweiDiscoveryService.buscar_chamadas_globais(
            client, 1000, 2000, limit_per_page=100, max_rows=100
        )

        by_id = {c["callId"]: c for c in result}
        self.assertEqual(by_id["IN-1"]["isCallIn"], "true", "Falha: Chamada de query INBOUND deve ser marcada como 'true'")
        self.assertEqual(by_id["OUT-1"]["isCallIn"], "false", "Falha: Chamada de query OUTBOUND deve ser marcada como 'false'")

    async def test_buscar_historico_chamadas_envia_polaridade_correta(self):
        """
        Camada 1 - Unit test de polaridade do payload (HuaweiAICCClient).
        Contrato CC-CMS V2 §4.1.1.13: isCallIn='true' = INBOUND, 'false' = OUTBOUND.
        """
        from core.huawei_client import HuaweiAICCClient
        client = HuaweiAICCClient(
            cms_url="http://cms", fs_url="http://fs",
            cc_id=1, vdn=1, ak="ak", sk="sk",
            app_key="ak", app_secret="as",
            direct_app_key="dk", direct_app_secret="ds"
        )

        captured_payloads = []

        async def fake_post(url, payload):
            captured_payloads.append(payload)
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.json = lambda: {"resultCode": "0100000", "resultDesc": {"data": []}}
            return mock_resp

        with patch.object(client, "_post_json", side_effect=fake_post):
            await client.buscar_historico_chamadas(1000, 2000, call_direction="INBOUND")
            self.assertEqual(captured_payloads[0]["isCallIn"], "true")

            await client.buscar_historico_chamadas(1000, 2000, call_direction="OUTBOUND")
            self.assertEqual(captured_payloads[1]["isCallIn"], "false")

    async def test_busca_global_nao_envia_agent_id_nem_media_type(self):
        client = AsyncMock()
        client.buscar_historico_chamadas = AsyncMock(
            side_effect=[
                [
                    {"callId": "shared-1", "duration": 100},
                    {"callId": "in-1", "duration": 120},
                ],
                [
                    {"callId": "shared-1", "duration": 100},
                    {"callId": "out-1", "duration": 150},
                ],
            ]
        )

        result = await HuaweiDiscoveryService.buscar_chamadas_globais(
            client,
            1000,
            2000,
            limit_per_page=100,
            max_rows=100,
        )

        self.assertEqual(
            result,
            [
                {"callId": "shared-1", "duration": 100, "isCallIn": "true", "source": "vdn"},
                {"callId": "in-1", "duration": 120, "isCallIn": "true", "source": "vdn"},
                {"callId": "out-1", "duration": 150, "isCallIn": "false", "source": "vdn"},
            ],
        )
        self.assertEqual(
            client.buscar_historico_chamadas.await_args_list,
            [
                call(1000, 2000, call_direction="INBOUND"),
                call(1000, 2000, call_direction="OUTBOUND"),
            ],
        )

    def test_discovery_manifest_row_to_interacao_mapeia_identificadores_do_obs(self):
        # Cobertura abrangente do mapeamento OBS-row -> interacao na versao canonica
        # (HuaweiDiscoveryService). A copia morta em huawei_sync foi removida (v1.3.174);
        # este teste passou a exercitar a unica implementacao viva.
        result = HuaweiDiscoveryService._manifest_row_to_interacao(
            {
                "callId": "1777093663-792075",
                "recordId": "792075",
                "contactId": "contact-1",
                "callSerialno": "serial-1",
                "caller": "0016996299520",
                "called": "61197",
                "beginTime": "2026-04-25 12:00:00",
                "endTime": "2026-04-25 12:01:05",
                "calllDuration": "65",
                "workNo": "666",
                "countName": "Agata",
                "mediaTypeId": "5",
                "talkReason": "PARADA",
                "talkRemark": "motorista parado no cliente",
                "callReasonCode": "P01",
            }
        )

        self.assertEqual(result["callId"], "1777093663-792075")
        self.assertEqual(result["recordId"], "792075")
        self.assertEqual(result["callerNo"], "0016996299520")
        self.assertEqual(result["calleeNo"], "61197")
        self.assertEqual(result["duration"], 65)
        self.assertEqual(result["workNo"], "666")
        self.assertEqual(result["operatorName"], "Agata")
        self.assertEqual(result["callReason"], "PARADA")
        self.assertEqual(result["talkReason"], "PARADA")
        self.assertEqual(result["talkRemark"], "motorista parado no cliente")
        self.assertEqual(result["callReasonCode"], "P01")
        self.assertEqual(result["isCallIn"], "true")
        self.assertEqual(result["source"], "obs_contact_record")

    def test_discovery_manifest_row_infere_outbound_quando_workno_e_caller(self):
        result = HuaweiDiscoveryService._manifest_row_to_interacao(
            {
                "callId": "outbound-1",
                "caller": "61197",
                "called": "0016996299520",
                "workNo": "61197",
                "beginTime": "2026-04-25 12:00:00",
                "endTime": "2026-04-25 12:02:00",
            }
        )

        self.assertEqual(result["isCallIn"], "false")

    def test_discovery_manifest_row_infere_inbound_quando_workno_e_called(self):
        result = HuaweiDiscoveryService._manifest_row_to_interacao(
            {
                "callId": "inbound-1",
                "caller": "0016996299520",
                "called": "61197",
                "workNo": "61197",
                "beginTime": "2026-04-25 12:00:00",
                "endTime": "2026-04-25 12:02:00",
            }
        )

        self.assertEqual(result["isCallIn"], "true")

    def test_discovery_manifest_row_mantem_direcao_desconhecida_quando_ambigua(self):
        result = HuaweiDiscoveryService._manifest_row_to_interacao(
            {
                "callId": "ambigua-1",
                "caller": "61197",
                "called": "61198",
                "workNo": "99999",
                "beginTime": "2026-04-25 12:00:00",
                "endTime": "2026-04-25 12:02:00",
            }
        )

        self.assertIsNone(result["isCallIn"])

    def test_discovery_manifest_row_usa_direcao_explicita_quando_endpoints_ambiguos(self):
        result = HuaweiDiscoveryService._manifest_row_to_interacao(
            {
                "callId": "explicit-1",
                "caller": "08001234567",
                "called": "40041234",
                "workNo": "99999",
                "isCallIn": "false",
                "beginTime": "2026-04-25 12:00:00",
                "endTime": "2026-04-25 12:02:00",
            }
        )

        self.assertEqual(result["isCallIn"], "false")

    def test_coerce_huawei_time_ms_iso_string_assumes_utc(self):
        # CSV manifesto da Huawei envia beginTime como ISO em UTC.
        # 2026-05-26 12:23:47 UTC == epoch 1779798227 s == 1779798227000 ms.
        # Bug observado: ao assumir BRT, retornava 1779809027000 (+3h drift).
        result = HuaweiDiscoveryService._coerce_huawei_time_ms("2026-05-26 12:23:47")
        self.assertEqual(result, 1779798227000)

    def test_manifest_row_iso_string_preserves_call_id_epoch(self):
        # Regressao: itens vindos so do CSV (`huawei_source='obs_contact_record'`)
        # chegavam com `huawei_begin_time` +3h adiantado, causando audio_not_found
        # em chamadas perto da meia-noite.
        row = {
            "callId": "1779798227-598393",
            "beginTime": "2026-05-26 12:23:47",
            "endTime": "2026-05-26 12:32:17",
        }
        result = HuaweiDiscoveryService._manifest_row_to_interacao(row)
        self.assertEqual(result["beginTime"], 1779798227000)
        self.assertEqual(result["endTime"], 1779798737000)

    async def test_busca_respeita_direcao_explicita(self):
        client = AsyncMock()
        client.buscar_historico_chamadas = AsyncMock(
            return_value=[{"callId": "out-1", "duration": 180}]
        )

        result = await huawei_sync._buscar_chamadas_por_regra(
            client,
            1000,
            2000,
            {"id_huawei": "agente-1"},
            {"media_type": "VOICE", "call_direction": "OUTBOUND"},
        )

        self.assertEqual(result, [{"callId": "out-1", "duration": 180}])
        client.buscar_historico_chamadas.assert_awaited_once_with(
            1000,
            2000,
            call_direction="OUTBOUND",
        )

    async def test_busca_sem_direcao_consulta_ambos_sentidos_e_deduplica_por_callid(self):
        client = AsyncMock()
        client.buscar_historico_chamadas = AsyncMock(
            side_effect=[
                [
                    {"callId": "shared-1", "duration": 100},
                    {"callId": "in-1", "duration": 120},
                ],
                [
                    {"callId": "shared-1", "duration": 100},
                    {"callId": "out-1", "duration": 150},
                ],
            ]
        )

        result = await huawei_sync._buscar_chamadas_por_regra(
            client,
            1000,
            2000,
            {"id_huawei": "agente-1"},
            {"media_type": "VOICE"},
        )

        self.assertEqual(
            result,
            [
                {"callId": "shared-1", "duration": 100},
                {"callId": "in-1", "duration": 120},
                {"callId": "out-1", "duration": 150},
            ],
        )
        self.assertEqual(client.buscar_historico_chamadas.await_count, 2)
        client.buscar_historico_chamadas.assert_any_await(
            1000,
            2000,
            call_direction="INBOUND",
        )
        client.buscar_historico_chamadas.assert_any_await(
            1000,
            2000,
            call_direction="OUTBOUND",
        )

    async def test_executar_sync_huawei_skips_when_another_sync_holds_the_lock(self):
        with patch.object(huawei_sync._HuaweiSyncExecutionLock, "acquire", return_value=False):
            result = await huawei_sync.executar_sync_huawei(horas_retroativas=1)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["baixadas"], 0)
        self.assertEqual(result["enfileiradas"], 0)

    async def test_executar_sync_nao_baixa_sem_operador_huawei_cadastrado(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(return_value=None)
        client.obter_url_audio_obs = AsyncMock(return_value=None)

        with patch.object(huawei_sync._HuaweiSyncExecutionLock, "acquire", return_value=True):
            with patch.object(huawei_sync._HuaweiSyncExecutionLock, "release", return_value=None):
                with patch.object(huawei_sync, "_ensure_enabled", return_value=True):
                    with patch.object(
                        huawei_sync,
                        "_load_config",
                        return_value={
                            "ak": "ak",
                            "sk": "sk",
                            "cc_id": "1",
                            "vdn": "170",
                            "obs_ak": "ak",
                            "obs_sk": "sk",
                        },
                    ):
                        with patch.object(huawei_sync.HuaweiAICCClient, "from_config", return_value=client):
                            with patch("repositories.operators.listar_auditaveis_com_id_huawei",
                                return_value=[],
                            ):
                                with patch.object(
                                    HuaweiDiscoveryService,
                                    "fetch_all",
                                    AsyncMock(
                                        return_value=([
                                            {
                                                "callId": "call-1",
                                                "duration": 200,
                                                "beginTime": 1000,
                                                "endTime": 201000,
                                            }
                                        ], set(["call-1"]), set(), set(["call-1"]))
                                    ),
                                ):
                                        with patch.object(
                                            huawei_sync.database,
                                            "huawei_sync_log_exists",
                                            return_value=False,
                                        ):
                                            with patch.object(
                                                huawei_sync.database,
                                                "huawei_sync_log_registrar",
                                            ) as sync_log:
                                                with patch.object(
                                                    huawei_sync.database,
                                                    "get_operator_audit_count_for_month_safe",
                                                    return_value=0,
                                                ) as audit_count:
                                                    result = await huawei_sync.executar_sync_huawei(
                                                        horas_retroativas=1
                                                    )

        self.assertEqual(result["operadores_considerados"], 0)
        self.assertEqual(result["chamadas_na_vdn"], 1)
        self.assertEqual(result["chamadas_validas_pos_filtro"], 0)
        self.assertEqual(result["candidatos_download"], 0)
        self.assertEqual(result["tentativas_download"], 0)
        self.assertEqual(result["ignoradas_operador_huawei_nao_cadastrado"], 1)
        self.assertEqual(result["obs_primary_tentativas"], 0)
        client.baixar_gravacao_por_callid.assert_not_awaited()
        sync_log.assert_called_once()
        self.assertEqual(sync_log.call_args.kwargs["status"], "skipped_operator")
        self.assertEqual(sync_log.call_args.kwargs["failure_reason"], "operador_huawei_nao_cadastrado")
        audit_count.assert_not_called()

    async def test_executar_sync_respeita_cancelamento_antes_da_busca(self):
        client = AsyncMock()

        with patch.object(huawei_sync._HuaweiSyncExecutionLock, "acquire", return_value=True):
            with patch.object(huawei_sync._HuaweiSyncExecutionLock, "release", return_value=None):
                with patch.object(huawei_sync, "_ensure_enabled", return_value=True):
                    with patch.object(
                        huawei_sync,
                        "_load_config",
                        return_value={
                            "ak": "ak",
                            "sk": "sk",
                            "cc_id": "1",
                            "vdn": "170",
                            "obs_ak": "ak",
                            "obs_sk": "sk",
                        },
                    ):
                        with patch.object(huawei_sync.HuaweiAICCClient, "from_config", return_value=client):
                            with patch("repositories.operators.listar_auditaveis_com_id_huawei",
                                return_value=[],
                            ):
                                with patch.object(
                                    huawei_sync.HuaweiDiscoveryService,
                                    "fetch_all",
                                    AsyncMock(return_value=([], set(), set(), set())),
                                ) as buscar_vdn:
                                    result = await huawei_sync.executar_sync_huawei(
                                        horas_retroativas=1,
                                        should_cancel=lambda: True,
                                    )

        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(result["cancelado"])
        self.assertEqual(result["baixadas"], 0)
        buscar_vdn.assert_not_awaited()

    def test_enfileirar_classificado_uses_detected_operator_identity(self):
        classification = ClassificationResult(
            filename="huawei_call.wav",
            sector_id="logistica_unilever",
            sector_label="Logistica Unilever",
            alert_id="UNILEVER-ENTREGA",
            alert_label="Entrega",
            confidence=0.91,
            operator_name="Operadora Unilever",
            id_huawei="HUA-777",
            matricula="MAT-777",
        )

        with patch.object(huawei_sync.database, "obter_fila_revisao_classificacao_por_hash", return_value=None):
            with patch.object(huawei_sync, "store_classified_audio", return_value="media.wav"):
                with patch.object(huawei_sync.database, "sincronizar_fila_revisao_classificacao") as sync:
                    result = huawei_sync._enfileirar_classificado(
                        b"audio-bytes",
                        "huawei_call.wav",
                        {"nome": "Nao Identificado", "id_huawei": None},
                        classification,
                        source_type="audio",
                    )

        self.assertEqual(result["status"], "queued")
        sync.assert_called_once()
        kwargs = sync.call_args.kwargs
        self.assertEqual(kwargs["operador_previsto"], "Operadora Unilever")
        self.assertEqual(kwargs["metadata"]["operator_id"], "HUA-777")
        self.assertEqual(kwargs["metadata"]["id_huawei"], "HUA-777")

    async def test_enfileirar_audio_marks_pending_for_triage(self):
        """Telefonia baixa e enfileira; a classificacao do alerta fica para a triagem."""
        with patch.object(huawei_sync.database, "obter_fila_revisao_classificacao_por_hash", return_value=None):
            with patch.object(huawei_sync, "store_classified_audio", return_value="media.wav"):
                with patch.object(huawei_sync.database, "sincronizar_fila_revisao_classificacao") as sync:
                    result = await huawei_sync._enfileirar_audio(
                        b"audio-bytes",
                        "huawei_call.wav",
                        {
                            "nome": "Operadora Huawei",
                            "id_huawei": "HUA-123",
                            "matricula": "MAT-123",
                            "setor": "Cadastro",
                            "escala": "12x36 Noite",
                        },
                    )

        self.assertEqual(result["status"], "queued")
        sync.assert_called_once()
        kwargs = sync.call_args.kwargs
        self.assertTrue(kwargs["precisa_revisao"])
        self.assertEqual(kwargs["alerta_previsto"], "desconhecido")
        self.assertEqual(kwargs["setor_previsto"], "cadastro")
        self.assertEqual(kwargs["operador_previsto"], "Operadora Huawei")
        self.assertIn("aguardando_triagem", kwargs["motivos_revisao"])
        self.assertEqual(kwargs["metadata"]["operator_id"], "HUA-123")
        self.assertEqual(kwargs["metadata"]["matricula"], "MAT-123")
        self.assertEqual(kwargs["metadata"]["escala"], "12x36 Noite")
        self.assertEqual(kwargs["metadata"]["operator_sector_real"], "Cadastro")
        self.assertEqual(kwargs["metadata"]["operator_sector_id"], "cadastro")
        self.assertEqual(kwargs["metadata"]["classification_status"], "pending")

    async def test_enfileirar_audio_manual_marca_is_manual_em_metadata(self):
        """Fluxo unificado (v1.3.92): manual entra na fila sem status_override.

        Status do row segue regra padrao (pending/auto_resolved por
        precisa_revisao); a distincao manual x auto fica no metadata.is_manual,
        usado pelo badge "Auto" do frontend.
        """
        with patch.object(huawei_sync.database, "obter_fila_revisao_classificacao_por_hash", return_value=None):
            with patch.object(huawei_sync, "store_classified_audio", return_value="media.wav"):
                with patch.object(huawei_sync.database, "sincronizar_fila_revisao_classificacao") as sync:
                    result = await huawei_sync._enfileirar_audio(
                        b"audio-bytes",
                        "huawei_call.wav",
                        {
                            "nome": "Operadora Huawei",
                            "id_huawei": "HUA-123",
                            "matricula": "MAT-123",
                            "setor": "Cadastro",
                            "escala": "12x36 Noite",
                        },
                        is_manual=True,
                    )

        self.assertEqual(result["status"], "queued")
        sync.assert_called_once()
        kwargs = sync.call_args.kwargs
        self.assertIsNone(kwargs["status_override"])
        self.assertTrue(kwargs["metadata"]["is_manual"])

    def test_normalize_setor_regra_applies_known_aliases(self):
        self.assertEqual(huawei_sync._normalize_setor_regra("RASTREAMENTO - AZUL"), "transferencia")
        self.assertEqual(huawei_sync._normalize_setor_regra("UTI - RJ"), "uti")
        self.assertEqual(huawei_sync._normalize_setor_regra("Unilever"), "logistica_unilever")
        self.assertEqual(huawei_sync._normalize_setor_regra("DIST - VERDE"), "distribuicao")
        self.assertEqual(huawei_sync._normalize_setor_regra("DIST E CELULA - VERDE"), "celula_atendimento")
        self.assertEqual(huawei_sync._normalize_setor_regra("RECEPTIVO"), "celula_atendimento")
        self.assertEqual(huawei_sync._normalize_setor_regra("GRS - CINZA"), "uti")
        self.assertEqual(huawei_sync._normalize_setor_regra("BASE DE SINISTROS"), "bas")

    def test_duration_limits_use_operational_defaults_without_sector_caps(self):
        self.assertEqual(
            huawei_sync._get_duration_limits_for_sector("UTI - RJ", 10, 0),
            (10, 0),
        )
        self.assertEqual(
            huawei_sync._get_duration_limits_for_sector("Distribuicao", 0, 900),
            (0, 900),
        )

    def test_auto_classification_after_sync_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(huawei_sync._should_run_auto_classification_after_sync())

    def test_auto_classification_after_sync_can_be_enabled_explicitly(self):
        with patch.dict(os.environ, {"HUAWEI_SYNC_ENABLE_CLASSIFY": "true"}, clear=True):
            self.assertTrue(huawei_sync._should_run_auto_classification_after_sync())

    def test_auto_classification_after_sync_honors_legacy_skip_flag(self):
        with patch.dict(os.environ, {"HUAWEI_SYNC_SKIP_CLASSIFY": "true"}, clear=True):
            self.assertFalse(huawei_sync._should_run_auto_classification_after_sync())
        with patch.dict(os.environ, {"HUAWEI_SYNC_SKIP_CLASSIFY": "false"}, clear=True):
            self.assertTrue(huawei_sync._should_run_auto_classification_after_sync())

    def test_download_limit_follows_audit_target_when_larger(self):
        def fake_get_config(key, default=""):
            values = {
                "huawei_d1_limite_ligacoes": "100",
                "automacao_audit_target_count": "300",
            }
            return values.get(key, default)

        with patch.dict(os.environ, {}, clear=True), patch.object(
            huawei_sync.database,
            "get_config_value",
            side_effect=fake_get_config,
        ):
            self.assertEqual(huawei_sync._effective_download_attempt_limit(), 300)

    async def test_executar_sync_limits_downloads_to_twenty_and_defers_to_triage(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(
            side_effect=lambda call_id: f"audio-{call_id}".encode("utf-8")
        )
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        chamadas = [
            {
                "callId": f"call-{index:02d}",
                "duration": 12,
                "beginTime": 1777516670000 + index * 1000,
                "endTime": 1777516670000 + 13_000 + index * 1000,
                "isCallIn": "false",
                "workNo": "HUA-123",
                "operatorName": "Operadora Huawei",
            }
            for index in range(25)
        ]

        with patch.dict(
            os.environ,
            {
                "HUAWEI_SYNC_MIN_DURATION_SECONDS": "10",
                "HUAWEI_SYNC_MAX_DURATION_SECONDS": "0",
                "HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS": "20",
            },
        ):
            with patch.object(huawei_sync._HuaweiSyncExecutionLock, "acquire", return_value=True):
                with patch.object(huawei_sync._HuaweiSyncExecutionLock, "release", return_value=None):
                    with patch.object(huawei_sync, "_ensure_enabled", return_value=True):
                        with patch.object(
                            huawei_sync,
                            "_load_config",
                            return_value={
                                "ak": "ak",
                                "sk": "sk",
                                "cc_id": "1",
                                "vdn": "170",
                                "obs_ak": "ak",
                                "obs_sk": "sk",
                            },
                        ):
                            mock_obs_cls = MagicMock()
                            mock_obs_cls._candidate_dates.return_value = ["20260425"]
                            mock_obs_cls.return_value = AsyncMock(baixar_voice_por_callid=AsyncMock(return_value=b"RIFF"), listar_diretorio=AsyncMock(return_value=[{"Key": "test"}]))
                            with patch.object(huawei_sync.HuaweiAICCClient, "from_config", return_value=client):
                                with patch("core.huawei_sync.HuaweiOBSClient", new=mock_obs_cls):
                                    with patch("repositories.operators.listar_auditaveis_com_id_huawei",
                                        return_value=[{
                                            "id": 1,
                                            "id_huawei": "HUA-123",
                                            "id_telefonia": "HUA-123",
                                            "nome": "Operadora Huawei",
                                            "setor": "uti",
                                            "escala": "",
                                            "matricula": "",
                                            "supervisor": "",
                                        }],
                                    ):
                                        with patch.object(
                                            HuaweiDiscoveryService,
                                            "fetch_all",
                                            AsyncMock(return_value=(chamadas, set([c["callId"] for c in chamadas]), set(), set([c["callId"] for c in chamadas]))),
                                        ):
                                            with patch.object(
                                                huawei_sync.database,
                                                "huawei_sync_log_exists",
                                                return_value=False,
                                            ):
                                                with patch.object(
                                                    huawei_sync.database,
                                                    "huawei_sync_log_registrar",
                                                ):
                                                    with patch.object(
                                                        huawei_sync.database,
                                                        "get_operator_audit_count_for_month_safe",
                                                        return_value=99,
                                                    ) as quota_count, patch(
                                                        "repositories.audits.get_operator_audit_counts_for_month_bulk",
                                                        return_value={},
                                                    ):
                                                        with patch.object(
                                                            huawei_sync.database,
                                                            "get_config_value",
                                                            return_value="99",
                                                        ):
                                                            with patch.object(
                                                                huawei_sync,
                                                                "_enfileirar_audio",
                                                                AsyncMock(return_value={"status": "queued"}),
                                                            ) as enqueue:
                                                                print(f"DEBUG: cfg obs_ak: {huawei_sync._load_config()['obs_ak']}")
                                                                result = await huawei_sync.executar_sync_huawei(
                                                                    horas_retroativas=1
                                                                )
                                                                print(f"DEBUG: tentativas: {result['tentativas_download']}, baixadas: {result['baixadas']}")

        self.assertEqual(result["min_duracao_padrao_segundos"], 10)
        self.assertEqual(result["max_duracao_padrao_segundos"], 0)
        self.assertEqual(result["limite_downloads"], 20)
        self.assertEqual(result["chamadas_validas_pos_filtro"], 25)
        self.assertEqual(result["candidatos_download"], 20)
        self.assertEqual(result["tentativas_download"], 20)
        self.assertEqual(result["baixadas"], 20)
        self.assertEqual(result["enfileiradas"], 20)
        self.assertEqual(client.baixar_gravacao_por_callid.await_count, 20)
        self.assertEqual(enqueue.await_count, 20)
        quota_count.assert_not_called()
        for kwargs in [call_item.kwargs for call_item in enqueue.await_args_list]:
            self.assertNotIn("pular_triagem", kwargs)

    def test_obs_prefix_candidates_uses_call_phones_before_agent_id(self):
        result = huawei_sync._obs_prefix_candidates(
            {
                "callerNo": "011139033478",
                "calleeNo": "0016996299520",
            },
            "666",
        )

        self.assertEqual(result, ["011139033478", "0016996299520", "666"])

    def test_obs_prefix_candidates_ignores_empty_values_and_deduplicates(self):
        result = huawei_sync._obs_prefix_candidates(
            {
                "callerNo": None,
                "caller_no": "0016996299520",
                "calleeNo": "null",
                "callee_no": "0016996299520",
            },
            "666",
        )

        self.assertEqual(result, ["0016996299520", "666"])

    def test_obs_match_ids_includes_record_identifiers(self):
        result = huawei_sync._obs_match_ids(
            {
                "recordId": "792075",
                "contactId": "contact-1",
                "callSerialno": "serial-1",
            },
            "1777093663-792075",
        )

        self.assertEqual(
            result,
            ["1777093663-792075", "792075", "contact-1", "serial-1"],
        )

    def test_obs_match_ids_usa_sufixo_do_call_id_sem_record_id(self):
        result = huawei_sync._obs_match_ids(
            {
                "recordId": "",
                "contactId": "",
                "callSerialno": "",
            },
            "1777516248-17256970",
        )

        self.assertEqual(result, ["1777516248-17256970", "17256970"])

    def test_call_duration_known_accepts_datetime_strings(self):
        chamada = {
            "callId": "1777516248-17256970",
            "beginTime": "2026-04-25 12:00:00",
            "endTime": "2026-04-25 12:01:05",
        }

        self.assertTrue(huawei_sync._call_duration_is_known(chamada))
        self.assertEqual(huawei_sync.get_call_duration_seconds(chamada), 65)

    def test_call_duration_unknown_is_distinguishable_from_zero(self):
        self.assertFalse(huawei_sync._call_duration_is_known({"callId": "call-1"}))
        self.assertTrue(huawei_sync._call_duration_is_known({"callId": "call-2", "duration": 0}))

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
            "candidatos com recordId preenchido devem vir antes dos sem recordId,"
            " mesmo que estes tenham duracao maior",
        )

    async def test_processar_candidato_pula_obs_quando_record_id_vazio_e_eh_manifesto(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(return_value=None)
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        client.baixar_audio_ram = AsyncMock(return_value=None)

        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock(return_value=b"deveria-nao-ser-chamado")

        with patch("core.huawei_sync.database.huawei_sync_log_registrar") as mock_reg:
            delta = await huawei_sync._processar_candidato(
                {
                    "callId": "1777516248-17256970",
                    "recordId": "",
                    "source": "obs_contact_record",
                    "isCallIn": "true",
                    "callerNo": "5511999999999",
                    "calleeNo": "61197",
                    "workNo": "189",
                    "beginTime": 1777516248000,
                    "endTime": 1777516840000,
                    "duration": 591,
                },
                client=client,
                obs_client=obs_client,
                operator_by_id={"189": {"setor": "cadastro", "id_huawei": "189", "nome": "Operador Logistica"}},
                operator_by_name={},
                should_cancel=None,
            
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval")
            )

        obs_client.baixar_voice_por_callid.assert_not_awaited()
        self.assertEqual(delta["obs_primary_pulado_sem_record_id"], 1)
        self.assertEqual(delta["obs_primary_tentativas"], 0)
        self.assertEqual(delta["baixadas"], 0)

    async def test_processar_candidato_tenta_obs_quando_record_id_vazio(self):

        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(return_value=None)
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        client.baixar_audio_ram = AsyncMock(return_value=None)

        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock(return_value=None)

        with patch("core.huawei_sync.database.huawei_sync_log_registrar") as mock_reg:
            delta = await huawei_sync._processar_candidato(
                {
                    "callId": "1777516248-17256970",
                    "recordId": "",
                    "source": "vdn",
                    "isCallIn": "true",
                    "callerNo": "5511999999999",
                    "calleeNo": "61197",
                    "workNo": "189",
                    "beginTime": 1777516248000,
                    "endTime": 1777516840000,
                    "duration": 591,
                },
                client=client,
                obs_client=obs_client,
                operator_by_id={"189": {"setor": "cadastro", "id_huawei": "189", "nome": "Operador Logistica"}},
                operator_by_name={},
                should_cancel=None,
            
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval")
            )

        obs_client.baixar_voice_por_callid.assert_awaited_once()
        obs_kwargs = obs_client.baixar_voice_por_callid.await_args.kwargs
        self.assertEqual(obs_kwargs["call_id"], "1777516248-17256970")
        self.assertIn("17256970", obs_kwargs["extra_match_ids"])
        self.assertEqual(delta["obs_primary_sem_record_id_tentativas"], 1)
        self.assertEqual(delta["obs_primary_tentativas"], 1)
        self.assertEqual(delta["obs_primary_misses"], 1)
        self.assertEqual(delta["obs_primary_pulado_sem_record_id"], 0)
        self.assertEqual(delta["baixadas"], 0)

    async def test_processar_candidato_tenta_obs_mesmo_sem_record_id_se_vier_da_vdn(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(return_value=None)
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        client.baixar_audio_ram = AsyncMock(return_value=None)

        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock(return_value=b"sucesso-vdn-obs")

        delta = await huawei_sync._processar_candidato(
            {
                "callId": "1777516248-17256970",
                "recordId": "",
                "source": "vdn",
                "isCallIn": "true",
                "workNo": "189",
                "beginTime": 1777516248000,
                "endTime": 1777516840000,
                "duration": 591,
            },
            client=client,
            obs_client=obs_client,
            operator_by_id={"189": {"setor": "cadastro", "id_huawei": "189", "nome": "Operador Logistica"}},
            operator_by_name={},
            should_cancel=None,
        
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
            )

        obs_client.baixar_voice_por_callid.assert_awaited()
        self.assertEqual(delta["obs_primary_hits"], 1)
        self.assertEqual(delta["baixadas"], 1)

    async def test_processar_candidato_tenta_obs_quando_record_id_existe(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(return_value=None)
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        client.baixar_audio_ram = AsyncMock(return_value=None)

        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock(return_value=None)

        with patch("core.huawei_sync.database.huawei_sync_log_registrar"):
            delta = await huawei_sync._processar_candidato(
                {
                    "callId": "1777516670-407526",
                    "recordId": "177751674560989921373222786316",
                    "isCallIn": "true",
                    "callerNo": "5511999999999",
                    "calleeNo": "61197",
                    "workNo": "189",
                    "beginTime": 1777516670000,
                    "endTime": 1777516741000,
                    "duration": 71,
                },
                client=client,
                obs_client=obs_client,
                operator_by_id={"189": {"setor": "cadastro", "id_huawei": "189", "nome": "Operador Logistica"}},
                operator_by_name={},
                should_cancel=None,
            
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
            )

        obs_client.baixar_voice_por_callid.assert_awaited_once()
        self.assertEqual(delta["obs_primary_tentativas"], 1)
        self.assertEqual(delta["obs_primary_misses"], 1)
        self.assertEqual(delta["obs_primary_pulado_sem_record_id"], 0)

    async def test_processar_candidato_tenta_fs_com_ids_alternativos(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(side_effect=[None, b"RIFFdata"])
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        client.baixar_audio_ram = AsyncMock(return_value=None)

        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock(return_value=None)

        with patch("core.huawei_sync.database.huawei_sync_log_registrar"):
            with patch(
                "core.huawei_sync._enfileirar_audio",
                AsyncMock(return_value={"status": "queued", "filename": "media.wav"}),
            ):
                delta = await huawei_sync._processar_candidato(
                    {
                        "callId": "1777516670-407526",
                        "recordId": "407526",
                        "isCallIn": "true",
                        "callerNo": "5511999999999",
                        "calleeNo": "61197",
                        "workNo": "189",
                        "beginTime": 1777516670000,
                        "endTime": 1777516741000,
                        "duration": 71,
                    },
                    client=client,
                    obs_client=obs_client,
                    operator_by_id={"189": {"setor": "cadastro", "id_huawei": "189", "nome": "Operador Logistica"}},
                    operator_by_name={},
                    should_cancel=None,
                
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
            )

        client.obter_url_audio_obs.assert_not_awaited() 
        self.assertEqual(delta["baixadas"], 1)
    async def test_processar_candidato_injeta_operador_real_resolvido_por_id_huawei(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock(return_value=b"RIFFdata")
        client.obter_url_audio_obs = AsyncMock(return_value=None)
        client.baixar_audio_ram = AsyncMock(return_value=None)

        operador_real = {
            "id_huawei": "189",
            "nome": "Nome Real",
            "setor": "Cadastro",
            "escala": "Diurna",
            "matricula": "MAT-189",
        }
        
        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock(return_value=b"RIFFdata")

        with patch("core.huawei_sync.database.huawei_sync_log_registrar"):
            with patch(
                "core.huawei_sync._enfileirar_audio",
                AsyncMock(return_value={"status": "queued", "filename": "media.wav"}),
            ) as enqueue:
                delta = await huawei_sync._processar_candidato(
                    {
                        "callId": "1777516670-407526",
                        "recordId": "407526",
                        "isCallIn": "true",
                        "workNo": "189",
                        "beginTime": 1777516670000,
                        "endTime": 1777516741000,
                        "duration": 71,
                    },
                    client=client,
                    obs_client=obs_client,
                    operator_by_id={"189": operador_real},
                    operator_by_name={},
                    should_cancel=None,
                
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
                is_manual=True,
            )

        self.assertEqual(delta["baixadas"], 1)
        enqueue.assert_awaited_once()
        operador_enfileirado = enqueue.await_args.args[2]
        self.assertEqual(operador_enfileirado["nome"], operador_real["nome"])
        self.assertEqual(operador_enfileirado["id_huawei"], operador_real["id_huawei"])
        self.assertEqual(operador_enfileirado["setor"], operador_real["setor"])
        self.assertTrue(operador_enfileirado["huawei_registered"])
        self.assertEqual(operador_enfileirado["huawei_match_source"], "id_huawei")
        metadata = enqueue.await_args.kwargs["extra_metadata"]
        self.assertEqual(metadata["operator_name_real"], "Nome Real")
        self.assertEqual(metadata["operator_sector_real"], "Cadastro")
        self.assertEqual(metadata["operator_sector_id"], "cadastro")
        self.assertEqual(metadata["operator_escala"], "Diurna")
        self.assertEqual(metadata["operator_matricula"], "MAT-189")
        self.assertEqual(metadata["operator_id_huawei_real"], "189")
        self.assertTrue(metadata["huawei_is_call_in"])
        self.assertTrue(enqueue.await_args.kwargs["is_manual"])

    def test_should_skip_call_descarta_inbound_huawei_em_setor_de_risco(self):
        # Setores de risco aceitam somente ligacoes ativas (OUTBOUND).
        for setor in ("transferencia", "uti", "bas", "distribuicao", "fenix"):
            self.assertEqual(
                huawei_sync._should_skip_call(
                    {"isCallIn": "true"},
                    _registered_operator(setor),
                ),
                "risk_inbound",
                f"Falha ao descartar receptiva para o setor {setor}",
            )

    def test_should_skip_call_descarta_aliases_reais_de_setor_de_risco(self):
        for setor in ("DIST - VERDE", "GRS - AZUL", "BASE DE SINISTROS"):
            self.assertEqual(
                huawei_sync._should_skip_call(
                    {"isCallIn": "true"},
                    _registered_operator(setor),
                ),
                "risk_inbound",
                f"Falha ao descartar receptiva para o setor {setor}",
            )

    def test_should_skip_call_descarta_celula_fora_da_telefonia(self):
        for setor in ("DIST E CELULA - VERDE", "RECEPTIVO"):
            for direction in ("true", "false", None):
                payload = {"isCallIn": direction} if direction is not None else {}
                self.assertEqual(
                    huawei_sync._should_skip_call(
                        payload,
                        _registered_operator(setor),
                    ),
                    "non_telefonia_sector",
                )

    def test_resolve_huawei_direction_prefere_rotulo_explicito_aos_endpoints(self):
        # Instrucao de Negocio: O sistema deve priorizar a flag explicita da Huawei ('isCallIn')
        # em vez de tentar inferir pelo numero de origem/destino.
        # Motivo (Bug Antigo): Quando uma chamada receptiva cai numa URA e eh transferida internamente,
        # os ramais (caller/callee) parecem ser internos, fazendo a inferencia classificar erroneamente
        # como 'outbound' (ativa), o que burlava o bloqueio de setores de risco.
        
        # Cenario 1: O payload diz 'isCallIn': 'false' (outbound), mas os telefones 
        # (se inferidos) diriam que e inbound. Devemos respeitar o payload ('false').
        self.assertFalse(
            huawei_sync._resolve_huawei_is_call_in(
                {
                    "isCallIn": "false",
                    "callerNo": "0011999999999",
                    "calleeNo": "61197",
                    "workNo": "61197",
                }
            )
        )
        
        # Cenario 2: O payload diz 'isCallIn': 'true' (inbound/receptiva), mas os telefones
        # (se inferidos) diriam outbound. Devemos respeitar o payload ('true').
        self.assertTrue(
            huawei_sync._resolve_huawei_is_call_in(
                {
                    "isCallIn": "true",
                    "callerNo": "61197",
                    "calleeNo": "0011999999999",
                    "workNo": "61197",
                }
            )
        )

    def test_should_skip_call_aceita_outbound_em_setor_de_risco(self):
        self.assertIsNone(
            huawei_sync._should_skip_call(
                {"isCallIn": "false"},
                _registered_operator("uti"),
            ),
        )

    def test_should_skip_call_aceita_inbound_em_setor_sem_risco(self):
        self.assertIsNone(
            huawei_sync._should_skip_call(
                {"isCallIn": "true"},
                _registered_operator("cadastro"),
            ),
        )

    def test_should_skip_call_aceita_outbound_em_setor_sem_risco(self):
        self.assertIsNone(
            huawei_sync._should_skip_call(
                {"isCallIn": "false"},
                _registered_operator("cadastro"),
            ),
        )

    def test_should_skip_call_descarta_direcao_desconhecida_em_setor_de_risco(self):
        self.assertEqual(
            huawei_sync._should_skip_call(
                {"callerNo": "61197", "calleeNo": "61198", "workNo": "99999"},
                _registered_operator("uti"),
            ),
            "direction_unknown",
        )

    def test_should_skip_call_descarta_operador_huawei_nao_cadastrado(self):
        self.assertEqual(
            huawei_sync._should_skip_call(
                {"isCallIn": "false"},
                {
                    "setor": "",
                    "id_huawei": "2992",
                    "nome": "Operadora fora do cadastro",
                    "auditavel_db": False,
                },
            ),
            "operator_huawei_not_registered",
        )

    def test_should_skip_call_descarta_receptiva_quando_setor_desconhecido(self):
        # Operador nao cadastrado (fallback de _resolve_operador_interacao retorna
        # setor=""): receptiva nao deve ser baixada para evitar vazamento de
        # chamadas de setores de risco ainda nao mapeados.
        self.assertEqual(
            huawei_sync._should_skip_call(
                {"isCallIn": "true"},
                {"setor": "", "id_huawei": "", "nome": "Nao Identificado"},
            ),
            "operator_huawei_not_registered",
        )

    def test_should_skip_call_descarta_outbound_quando_operador_sem_id_huawei(self):
        self.assertEqual(
            huawei_sync._should_skip_call(
                {"isCallIn": "false"},
                {"setor": "", "id_huawei": "", "nome": "Nao Identificado"},
            ),
            "operator_huawei_not_registered",
        )

    def test_should_skip_call_descarta_id_huawei_nao_cadastrado(self):
        operador = huawei_sync._resolve_operador_interacao(
            {"workNo": "99999", "operatorName": "Operador Externo"},
            by_id={},
            by_name={},
        )

        self.assertEqual(operador["id_huawei"], "99999")
        self.assertFalse(operador["huawei_registered"])
        self.assertEqual(
            huawei_sync._should_skip_call({"isCallIn": "false"}, operador),
            "operator_huawei_not_registered",
        )

    def test_resolve_operador_nao_autoriza_por_nome_quando_id_huawei_diverge(self):
        colaborador = {
            "id": 10,
            "nome": "Amanda Muslera",
            "setor": "logistica",
            "id_huawei": "189",
            "id_telefonia": "189",
            "auditavel_db": True,
            "huawei_registered": True,
        }
        by_name = {huawei_sync._normalize_identity_text("Amanda Muslera"): colaborador}

        operador = huawei_sync._resolve_operador_interacao(
            {"workNo": "99999", "operatorName": "Amanda Muslera", "isCallIn": "false"},
            by_id={"189": colaborador},
            by_name=by_name,
        )

        self.assertEqual(operador["nome"], "Amanda Muslera")
        self.assertEqual(operador["id_huawei"], "99999")
        self.assertFalse(operador["huawei_registered"])
        self.assertEqual(operador["huawei_match_source"], "name_only")
        self.assertEqual(operador["matched_operator_id_huawei"], "189")
        self.assertEqual(
            huawei_sync._should_skip_call({"isCallIn": "false"}, operador),
            "operator_huawei_not_registered",
        )

    def test_resolve_operador_nao_autoriza_por_nome_quando_chamada_nao_tem_id_huawei(self):
        colaborador = {
            "id": 10,
            "nome": "Amanda Muslera",
            "setor": "logistica",
            "id_huawei": "189",
            "id_telefonia": "189",
            "auditavel_db": True,
            "huawei_registered": True,
        }
        by_name = {huawei_sync._normalize_identity_text("Amanda Muslera"): colaborador}

        operador = huawei_sync._resolve_operador_interacao(
            {"operatorName": "Amanda Muslera", "isCallIn": "false"},
            by_id={"189": colaborador},
            by_name=by_name,
        )

        self.assertEqual(operador["id_huawei"], "")
        self.assertFalse(operador["huawei_registered"])
        self.assertEqual(operador["huawei_match_source"], "name_only")
        self.assertEqual(
            huawei_sync._should_skip_call({"isCallIn": "false"}, operador),
            "operator_huawei_not_registered",
        )

    def test_resolve_operador_autoriza_quando_id_huawei_bate(self):
        colaborador = {
            "id": 10,
            "nome": "Amanda Muslera",
            "setor": "logistica",
            "id_huawei": "189",
            "id_telefonia": "189",
            "auditavel_db": True,
            "huawei_registered": True,
        }

        operador = huawei_sync._resolve_operador_interacao(
            {"workNo": "189", "operatorName": "Nome Vindo Huawei", "isCallIn": "false"},
            by_id={"189": colaborador},
            by_name={huawei_sync._normalize_identity_text("Amanda Muslera"): colaborador},
        )

        self.assertEqual(operador["id_huawei"], "189")
        self.assertTrue(operador["huawei_registered"])
        self.assertEqual(operador["huawei_match_source"], "id_huawei")
        self.assertIsNone(huawei_sync._should_skip_call({"isCallIn": "false"}, operador))

    async def test_processar_candidato_nao_baixa_quando_apenas_nome_bate(self):
        colaborador = {
            "id": 10,
            "nome": "Amanda Muslera",
            "setor": "logistica",
            "id_huawei": "189",
            "id_telefonia": "189",
            "auditavel_db": True,
            "huawei_registered": True,
        }
        download_chain = AsyncMock()
        download_chain.download = AsyncMock()

        with patch.object(huawei_sync.database, "huawei_sync_log_registrar") as sync_log:
            delta = await huawei_sync._processar_candidato(
                {
                    "callId": "call-name-only",
                    "workNo": "99999",
                    "operatorName": "Amanda Muslera",
                    "isCallIn": "false",
                    "duration": 180,
                },
                client=AsyncMock(),
                obs_client=None,
                download_chain=download_chain,
                operator_by_id={"189": colaborador},
                operator_by_name={huawei_sync._normalize_identity_text("Amanda Muslera"): colaborador},
                should_cancel=None,
            )

        self.assertEqual(delta["tentativas_download"], 0)
        self.assertEqual(delta["ignoradas_operador_huawei_nao_cadastrado"], 1)
        download_chain.download.assert_not_awaited()
        sync_log.assert_called_once()
        self.assertEqual(sync_log.call_args.kwargs["status"], "skipped_operator")

    def test_should_skip_call_descarta_direcao_indefinida_quando_operador_sem_id_huawei(self):
        self.assertEqual(
            huawei_sync._should_skip_call(
                {},
                {"setor": "", "id_huawei": "", "nome": "Nao Identificado"},
            ),
            "operator_huawei_not_registered",
        )

    def test_register_operator_skip_persists_context(self):
        with patch.object(huawei_sync.database, "huawei_sync_log_registrar") as mock_reg:
            huawei_sync._register_direction_skip(
                call_id="call-op",
                interacao={
                    "callId": "call-op",
                    "workNo": "2992",
                    "operatorName": "Amanda Muslera",
                    "skillId": "42",
                },
                operador={
                    "setor": "",
                    "id_huawei": "2992",
                    "nome": "Amanda Muslera",
                    "auditavel_db": False,
                },
                reason="operator_not_registered",
            )

        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs["status"], "skipped_operator")
        self.assertEqual(kwargs["failure_reason"], "operador_huawei_nao_cadastrado")
        self.assertEqual(kwargs["agent_id"], "2992")
        self.assertEqual(kwargs["operator_name"], "Amanda Muslera")

    def test_register_direction_skip_persists_operator_name_and_skill_id(self):
        # Quando uma chamada de operador desconhecido eh ignorada, o registro
        # do log precisa capturar operator_name e huawei_skill_id para manter
        # contexto operacional da origem Huawei.
        with patch.object(huawei_sync.database, "huawei_sync_log_registrar") as mock_reg:
            huawei_sync._register_direction_skip(
                call_id="call-xyz",
                interacao={
                    "callId": "call-xyz",
                    "isCallIn": "true",
                    "workNo": "9999",
                    "operatorName": "Joao Operador Novo",
                    "skillId": "42",
                },
                operador={
                    "setor": "",
                    "id_huawei": "",
                    "nome": "Nao Identificado",
                },
                reason="receptiva_setor_desconhecido",
            )
        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs.get("operator_name"), "Joao Operador Novo")
        self.assertEqual(kwargs.get("huawei_skill_id"), "42")
        self.assertEqual(kwargs.get("status"), "skipped_direction")
        self.assertEqual(kwargs.get("failure_reason"), "receptiva_setor_desconhecido")

    def test_register_direction_skip_usa_countname_quando_operatorname_ausente(self):
        # Manifest CSV do OBS usa countName, nao operatorName. O helper precisa
        # cobrir os dois formatos pra nao deixar pendencia sem nome.
        with patch.object(huawei_sync.database, "huawei_sync_log_registrar") as mock_reg:
            huawei_sync._register_direction_skip(
                call_id="call-csv",
                interacao={
                    "callId": "call-csv",
                    "isCallIn": "true",
                    "workNo": "555",
                    "countName": "Maria do OBS",
                },
                operador={"setor": "", "id_huawei": "", "nome": "Nao Identificado"},
                reason="receptiva_setor_desconhecido",
            )
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs.get("operator_name"), "Maria do OBS")
        # Sem skillId na chamada, registramos None — nao quebra schema mas
        # tambem nao polui o log com string vazia.
        self.assertIsNone(kwargs.get("huawei_skill_id"))

    def test_register_skip_for_operator_without_huawei_id(self):
        with patch.object(huawei_sync.database, "huawei_sync_log_registrar") as mock_reg:
            huawei_sync._register_direction_skip(
                call_id="call-no-operator",
                interacao={"callId": "call-no-operator", "workNo": "9999", "operatorName": "Operador Sem Cadastro"},
                operador={"setor": "", "id_huawei": "", "nome": "Nao Identificado"},
                reason="operator_huawei_not_registered",
            )
        kwargs = mock_reg.call_args.kwargs
        self.assertEqual(kwargs.get("status"), "skipped_operator")
        self.assertEqual(kwargs.get("failure_reason"), "operador_huawei_nao_cadastrado")
        self.assertEqual(kwargs.get("operator_name"), "Operador Sem Cadastro")

    def test_should_skip_call_aceita_direcao_desconhecida_quando_regra_e_any(self):
        self.assertIsNone(
            huawei_sync._should_skip_call(
                {"callerNo": "61197", "calleeNo": "61198", "workNo": "99999"},
                _registered_operator("logistica"),
            )
        )

    def test_required_query_directions_busca_ambos_sentidos_para_setor_de_risco(self):
        self.assertEqual(
            huawei_sync._required_query_directions_for_operators([{"setor": "Cadastro"}]),
            ["INBOUND", "OUTBOUND"],
        )
        self.assertEqual(
            huawei_sync._required_query_directions_for_operators([{"setor": "UTI"}]),
            ["OUTBOUND"],
        )
        self.assertEqual(
            huawei_sync._required_query_directions_for_operators([{"setor": "Logistica"}]),
            ["INBOUND", "OUTBOUND"],
        )

    async def test_triagem_setorial_prefiltra_tabulacao_nativa_em_setor_sem_risco(self):
        chamadas = [
            {
                "callId": "match",
                "duration": 180,
                "callReason": "PARADA",
                "operatorSectorIdResolved": "logistica",
            },
            {
                "callId": "mismatch",
                "duration": 180,
                "callReason": "ASSUNTO ADMINISTRATIVO",
                "operatorSectorIdResolved": "logistica",
            },
        ]

        async def _echo(calls, setor, regra):
            return calls

        contadores = {}
        with patch.object(huawei_sync, "filtrar_ligacoes_com_llm", new=AsyncMock(side_effect=_echo)) as llm:
            result = await huawei_sync._aplicar_triagem_setorial(chamadas, contadores)

        self.assertEqual([item["callId"] for item in result], ["match", "mismatch"])
        llm.assert_awaited_once()
        sent_to_llm = llm.await_args.args[0]
        self.assertEqual([item["callId"] for item in sent_to_llm], ["match", "mismatch"])
        self.assertEqual([item.get("native_reason_match") for item in sent_to_llm], [True, False])
        self.assertEqual(contadores["triagem_por_setor"]["logistica"]["pre_filtro_nativo"], 2)

    async def test_classificar_audio_huawei_injeta_tabulacao_nativa_em_setor_sem_risco(self):
        classification_payload = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "LOGISTICA-PARADA",
            "alert_label": "Parada Indevida",
            "confidence": 0.91,
            "operator_name": "Usuario",
        }
        resolved_operator = type(
            "Resolved",
            (),
            {
                "operator_name": "Usuario",
                "id_huawei": "189",
                "matricula": "MAT-189",
                "db_sector": "logistica",
                "source": "test",
            },
        )()

        with patch.object(huawei_sync, "transcribe_for_classification", new=AsyncMock(return_value="Motorista informou parada.")):
            with patch.object(huawei_sync, "classify_with_gpt", new=AsyncMock(return_value=classification_payload)) as classify:
                with patch("core.classification.resolve_operator_identity", return_value=resolved_operator):
                    result = await huawei_sync._classificar_audio_huawei(
                        b"RIFFdemo",
                        "call.wav",
                        _registered_operator("logistica", nome="Usuario"),
                        native_call_reason="PARADA",
                        native_call_reason_code="PAR",
                    )

        self.assertEqual(result.alert_id, "LOGISTICA-PARADA")
        prompt = classify.await_args.args[0]
        self.assertIn("TABULACAO NATIVA HUAWEI", prompt)
        self.assertIn("PARADA", prompt)
        self.assertIn("TRANSCRICAO:", prompt)

    async def test_classificar_audio_huawei_confianca_media_fica_em_triagem_na_automacao(self):
        classification_payload = {
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "LOGISTICA-PARADA",
            "alert_label": "Parada Indevida",
            "confidence": 0.85,
            "operator_name": "Usuario",
        }
        resolved_operator = type(
            "Resolved",
            (),
            {
                "operator_name": "Usuario",
                "id_huawei": "189",
                "matricula": "MAT-189",
                "db_sector": "logistica",
                "source": "test",
            },
        )()

        with patch.dict(os.environ, {"HUAWEI_AUTO_AUDIT_CONFIDENCE_THRESHOLD": "0.90"}, clear=False):
            with patch.object(huawei_sync, "transcribe_for_classification", new=AsyncMock(return_value="Motorista informou parada.")):
                with patch.object(huawei_sync, "classify_with_gpt", new=AsyncMock(return_value=classification_payload)):
                    with patch("core.classification.resolve_operator_identity", return_value=resolved_operator):
                        result = await huawei_sync._classificar_audio_huawei(
                            b"RIFFdemo",
                            "call.wav",
                            _registered_operator("logistica", nome="Usuario"),
                        )

        self.assertEqual(result.alert_id, "LOGISTICA-PARADA")
        self.assertTrue(result.needs_review)
        self.assertIn("confianca_insuficiente_automacao", result.review_reasons)
        self.assertEqual(result.review_priority, "medium")

    async def test_classificar_audio_huawei_nao_injeta_tabulacao_nativa_em_setor_de_risco(self):
        classification_payload = {
            "sector_id": "uti",
            "sector_label": "UTI",
            "alert_id": "UTI-PARADA-MOT",
            "alert_label": "Parada Indevida - Motorista",
            "confidence": 0.91,
            "operator_name": "Usuario",
        }
        resolved_operator = type(
            "Resolved",
            (),
            {
                "operator_name": "Usuario",
                "id_huawei": "189",
                "matricula": "MAT-189",
                "db_sector": "uti",
                "source": "test",
            },
        )()

        with patch.object(huawei_sync, "transcribe_for_classification", new=AsyncMock(return_value="Motorista informou parada.")):
            with patch.object(huawei_sync, "classify_with_gpt", new=AsyncMock(return_value=classification_payload)) as classify:
                with patch("core.classification.resolve_operator_identity", return_value=resolved_operator):
                    result = await huawei_sync._classificar_audio_huawei(
                        b"RIFFdemo",
                        "call.wav",
                        _registered_operator("uti", nome="Usuario"),
                        native_call_reason="PARADA",
                        native_call_reason_code="PAR",
                    )

        self.assertEqual(result.alert_id, "UTI-PARADA-MOT")
        prompt = classify.await_args.args[0]
        self.assertNotIn("TABULACAO NATIVA HUAWEI", prompt)
        self.assertEqual(prompt, "Motorista informou parada.")

    def test_should_skip_call_descarta_mondelez(self):
        self.assertEqual(
            huawei_sync._should_skip_call(
                {"isCallIn": "true"},
                _registered_operator("Operacao Mondelez"),
            ),
            "mondelez",
        )

    def test_should_skip_call_normaliza_acentos(self):
        # "fenix" e "FÊNIX" devem mapear para o mesmo grupo de risco (OUTBOUND only).
        self.assertIsNone(
            huawei_sync._should_skip_call(
                {"isCallIn": "false"},
                _registered_operator("FÊNIX"),
            ),
        )

    async def test_processar_candidato_risco_descarta_receptiva_pela_consulta_vdn(self):
        """A consulta VDN por callId (evidencia real) vence o isCallIn sintetico
        dos metadados: VDN diz receptiva => descarta mesmo com isCallIn='false'."""
        client = AsyncMock()
        client.consultar_direcao_chamada = AsyncMock(return_value=True)
        operador_real = {"id_huawei": "189", "nome": "Usuario", "setor": "UTI"}
        download_result = DownloadResult(
            audio_bytes=b"RIFFdata",
            method_used="fs_fallback",
            methods_tried=["fs_fallback"],
            attempts_per_method={"fs_fallback": 1},
        )

        if True:
            with patch("core.huawei_sync.database.huawei_sync_log_registrar") as sync_log:
                    with patch(
                        "core.huawei_sync._enfileirar_audio",
                        AsyncMock(return_value={"status": "queued", "filename": "media.wav"}),
                    ) as enqueue:
                        delta = await huawei_sync._processar_candidato(
                            {
                                "callId": "1777516670-407526",
                                "recordId": "407526",
                                "isCallIn": "false",
                                "workNo": "189",
                                "beginTime": 1777516670000,
                                "endTime": 1777516741000,
                                "duration": 71,
                            },
                            client=client,
                            obs_client=None,
                            operator_by_id={"189": operador_real},
                            operator_by_name={},
                            should_cancel=None,
                        
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
            )

        client.consultar_direcao_chamada.assert_awaited_once()
        enqueue.assert_not_awaited()
        sync_log.assert_called()
        self.assertEqual(delta["tentativas_download"], 1)
        self.assertEqual(delta["fs_fallback_hits"], 1)
        self.assertEqual(delta["baixadas"], 0)
        self.assertEqual(delta["enfileiradas"], 0)
        self.assertEqual(delta["pretriagem_direcao_receptiva_descartadas"], 1)

    async def test_processar_candidato_risco_descarta_direcao_indefinida(self):
        """Defesa em profundidade: item que passou pelo skip upstream mas cuja
        direção segue indeterminada (VDN sem resposta + metadados ambíguos)
        => DESCARTA (na dúvida não audita receptiva).

        Nota: no fluxo real, direção desconhecida costuma ser descartada antes
        do download por _should_skip_call; este teste força a passagem para
        exercitar o último gate."""
        client = AsyncMock()
        client.consultar_direcao_chamada = AsyncMock(return_value=None)
        operador_real = {"id_huawei": "189", "nome": "Usuario", "setor": "UTI"}

        with patch("core.huawei_sync._should_skip_call", return_value=None), \
             patch("core.huawei_sync.database.huawei_sync_log_registrar") as sync_log:
            with patch(
                "core.huawei_sync._enfileirar_audio",
                AsyncMock(return_value={"status": "queued", "filename": "media.wav"}),
            ) as enqueue:
                delta = await huawei_sync._processar_candidato(
                    {
                        # Sem isCallIn e sem callerNo/calleeNo: metadados nao
                        # resolvem a direcao; VDN mockada tambem nao.
                        "callId": "1777516670-407526",
                        "recordId": "407526",
                        "workNo": "189",
                        "beginTime": 1777516670000,
                        "endTime": 1777516741000,
                        "duration": 71,
                    },
                    client=client,
                    obs_client=None,
                    operator_by_id={"189": operador_real},
                    operator_by_name={},
                    should_cancel=None,
                    download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
                )

        client.consultar_direcao_chamada.assert_awaited_once()
        enqueue.assert_not_awaited()
        sync_log.assert_called()
        self.assertEqual(delta["enfileiradas"], 0)
        self.assertEqual(delta["pretriagem_direcao_indefinida"], 1)

    async def test_processar_candidato_risco_enfileira_ativa_pela_consulta_vdn(self):
        client = AsyncMock()
        client.consultar_direcao_chamada = AsyncMock(return_value=False)
        operador_real = {"id_huawei": "189", "nome": "Usuario", "setor": "UTI"}
        download_result = DownloadResult(
            audio_bytes=b"RIFFdata",
            method_used="fs_fallback",
            methods_tried=["fs_fallback"],
            attempts_per_method={"fs_fallback": 1},
        )

        if True:
            with patch("core.huawei_sync.database.huawei_sync_log_registrar"):
                    with patch(
                        "core.huawei_sync._enfileirar_audio",
                        AsyncMock(return_value={"status": "queued", "filename": "media.wav"}),
                    ) as enqueue:
                        delta = await huawei_sync._processar_candidato(
                            {
                                "callId": "1777516670-407526",
                                "recordId": "407526",
                                "isCallIn": "false",
                                "workNo": "189",
                                "beginTime": 1777516670000,
                                "endTime": 1777516741000,
                                "duration": 71,
                            },
                            client=client,
                            obs_client=None,
                            operator_by_id={"189": operador_real},
                            operator_by_name={},
                            should_cancel=None,
                        
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
            )

        enqueue.assert_awaited_once()
        metadata = enqueue.await_args.kwargs["extra_metadata"]
        self.assertEqual(metadata["audio_direction_pre_triage"], "outbound")

    async def test_processar_candidato_risco_usa_metadados_quando_vdn_indisponivel(self):
        """VDN falhando (excecao) nao pode travar o setor de risco: cai para a
        direcao dos metadados (isCallIn='false' => ativa => enfileira)."""
        client = AsyncMock()
        client.consultar_direcao_chamada = AsyncMock(side_effect=RuntimeError("vdn down"))
        operador_real = {"id_huawei": "189", "nome": "Usuario", "setor": "UTI"}

        with patch("core.huawei_sync.database.huawei_sync_log_registrar"):
            with patch(
                "core.huawei_sync._enfileirar_audio",
                AsyncMock(return_value={"status": "queued", "filename": "media.wav"}),
            ) as enqueue:
                delta = await huawei_sync._processar_candidato(
                    {
                        "callId": "1777516670-407526",
                        "recordId": "407526",
                        "isCallIn": "false",
                        "workNo": "189",
                        "beginTime": 1777516670000,
                        "endTime": 1777516741000,
                        "duration": 71,
                    },
                    client=client,
                    obs_client=None,
                    operator_by_id={"189": operador_real},
                    operator_by_name={},
                    should_cancel=None,
                    download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
                )

        enqueue.assert_awaited_once()
        metadata = enqueue.await_args.kwargs["extra_metadata"]
        self.assertEqual(metadata["audio_direction_pre_triage"], "outbound")
        self.assertEqual(delta["pretriagem_direcao_ativa_aprovadas"], 1)

    async def test_fase2_gate_bloqueia_item_inelegivel_sem_gastar_gpt(self):
        """Item que o AutomationGatekeeper bloquearia (setor nao-telefonia) e
        descartado ANTES da classificacao GPT — nem o audio e carregado."""
        item = {
            "input_hash": "hash_gate_1",
            "nome_arquivo": "receptivo.wav",
            "metadata": {
                "classification_status": "pending",
                "origem": "huawei_sync",
                "operator_sector_id": "celula_atendimento",
                "classified_audio_path": "classified/hash_gate_1.wav",
            },
        }
        with patch.object(huawei_sync.database, "listar_fila_revisao_classificacao", return_value=[item]):
            with patch.object(huawei_sync, "execute_discard") as discard:
                with patch.object(huawei_sync, "load_classified_audio") as load_audio:
                    with patch.object(huawei_sync, "_classificar_audio_huawei", new=AsyncMock()) as classify:
                        with patch.object(huawei_sync.cost_guard, "budget_exceeded", return_value=None):
                            result = await huawei_sync._classificar_pendentes_async(
                                concurrency=1,
                                operator_by_id={},
                                operator_by_name={},
                            )

        classify.assert_not_awaited()
        load_audio.assert_not_called()
        discard.assert_called_once()
        self.assertEqual(discard.call_args.args[1], huawei_sync.Disposition.DISCARD_IMPOSSIBLE)
        self.assertEqual(discard.call_args.kwargs["status_result"], "discarded_non_telephony")
        self.assertEqual(result["bloqueadas_pre_classificacao"], 1)
        self.assertEqual(result["classificadas"], 0)
        self.assertEqual(result["pendentes_restantes"], 0)

    async def test_fase2_gate_receptiva_setor_risco_nao_classifica(self):
        """Receptiva ja sinalizada (inbound_quarantine) em setor de risco nao
        chega ao GPT."""
        item = {
            "input_hash": "hash_gate_2",
            "nome_arquivo": "uti_receptiva.wav",
            "metadata": {
                "classification_status": "pending",
                "origem": "huawei_sync",
                "operator_sector_id": "uti",
                "audio_direction_pre_triage": "inbound_quarantine",
                "classified_audio_path": "classified/hash_gate_2.wav",
            },
        }
        with patch.object(huawei_sync.database, "listar_fila_revisao_classificacao", return_value=[item]):
            with patch.object(huawei_sync, "execute_discard") as discard:
                with patch.object(huawei_sync, "_classificar_audio_huawei", new=AsyncMock()) as classify:
                    with patch.object(huawei_sync.cost_guard, "budget_exceeded", return_value=None):
                        result = await huawei_sync._classificar_pendentes_async(
                            concurrency=1,
                            operator_by_id={},
                            operator_by_name={},
                        )

        classify.assert_not_awaited()
        discard.assert_called_once()
        self.assertEqual(result["bloqueadas_pre_classificacao"], 1)

    async def test_fase2_gate_item_elegivel_segue_para_classificacao(self):
        """Item elegivel (ativa em setor de risco) passa pelo gate e chega ao
        classificador normalmente."""
        classification_payload = type(
            "Resultado", (), {
                "sector_id": "uti", "alert_id": "UTI-PARADA-MOT", "confidence": 0.95,
                "operator_name": "Usuario", "needs_review": False, "review_reasons": [],
                "review_priority": "low", "error": None, "id_huawei": "189", "matricula": None,
            },
        )()
        item = {
            "input_hash": "hash_gate_3",
            "nome_arquivo": "uti_ativa.wav",
            "metadata": {
                "classification_status": "pending",
                "origem": "huawei_sync",
                "operator_sector_id": "uti",
                "huawei_is_call_in": "false",
                "classified_audio_path": "classified/hash_gate_3.wav",
            },
        }
        with patch.object(huawei_sync.database, "listar_fila_revisao_classificacao", return_value=[item]):
            with patch.object(huawei_sync, "execute_discard") as discard:
                with patch.object(huawei_sync, "load_classified_audio", return_value=b"RIFFdata"):
                    with patch.object(huawei_sync, "_classificar_audio_huawei", new=AsyncMock(return_value=classification_payload)) as classify:
                        with patch.object(huawei_sync, "_aplicar_auto_classificacao") as apply_cls:
                            with patch.object(huawei_sync.cost_guard, "budget_exceeded", return_value=None):
                                result = await huawei_sync._classificar_pendentes_async(
                                    concurrency=1,
                                    operator_by_id={},
                                    operator_by_name={},
                                )

        classify.assert_awaited_once()
        discard.assert_not_called()
        apply_cls.assert_called_once()
        self.assertEqual(result["classificadas"], 1)
        self.assertEqual(result["bloqueadas_pre_classificacao"], 0)

    async def test_processar_candidato_descarta_mondelez_antes_do_download(self):
        client = AsyncMock()
        client.baixar_gravacao_por_callid = AsyncMock()
        obs_client = AsyncMock()
        obs_client.baixar_voice_por_callid = AsyncMock()

        operator_by_id = {"189": {"id_huawei": "189", "nome": "Usuario", "setor": "Operacao Mondelez"}}

        delta = await huawei_sync._processar_candidato(
            {
                "callId": "1777516670-407526",
                "recordId": "abc",
                "isCallIn": "true",
                "workNo": "189",
                "beginTime": 1777516670000,
                "endTime": 1777516741000,
                "duration": 71,
            },
            client=client,
            obs_client=obs_client,
            operator_by_id=operator_by_id,
            operator_by_name={},
            should_cancel=None,
        
                download_chain=huawei_sync.HuaweiDownloadChain(mode="manual_interval"),
            )

        # Filtro deve abortar antes de qualquer download.
        client.baixar_gravacao_por_callid.assert_not_awaited()
        obs_client.baixar_voice_por_callid.assert_not_awaited()
        self.assertEqual(delta["ignoradas_mondelez"], 1)
        self.assertEqual(delta["tentativas_download"], 0)


class TestObsClientDateWindow(unittest.TestCase):
    def test_date_with_neighbors_skips_d_minus_1(self):
        from core.huawei_obs_client import HuaweiOBSClient

        # Chamada no meio do dia (12:00 BRT = 15:00 UTC) — sem cruzar virada.
        # Esperado: apenas o dia atual (UTC e BRT podem ou nao coincidir).
        begin_ms = int(datetime(2026, 4, 30, 15, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        dates = HuaweiOBSClient._date_with_neighbors(begin_ms)

        self.assertNotIn("20260429", dates, "D-1 nao deve mais ser consultado")
        self.assertIn("20260430", dates)

    def test_date_with_neighbors_includes_end_time_day_when_call_crosses_midnight(self):
        from core.huawei_obs_client import HuaweiOBSClient

        # Comeca 23:55 UTC, termina 00:30 UTC do dia seguinte.
        begin_ms = int(datetime(2026, 4, 30, 23, 55, 0, tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(datetime(2026, 5, 1, 0, 30, 0, tzinfo=timezone.utc).timestamp() * 1000)
        dates = HuaweiOBSClient._date_with_neighbors(begin_ms, end_ms)

        self.assertIn("20260430", dates)
        self.assertIn("20260501", dates)
        self.assertNotIn("20260429", dates)

    def test_date_with_neighbors_no_end_time_returns_only_begin(self):
        from core.huawei_obs_client import HuaweiOBSClient

        begin_ms = int(datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        dates = HuaweiOBSClient._date_with_neighbors(begin_ms)

        # Sem end_time nao expande para o dia seguinte (ate `huawei_sync` passa
        # endTime sempre que disponivel; o uso sem endTime e fallback inocuo).
        self.assertEqual(set(dates), {"20260430"})


if __name__ == "__main__":
    unittest.main()
