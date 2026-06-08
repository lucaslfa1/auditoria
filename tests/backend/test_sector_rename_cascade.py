"""Testes da cascata de rename de setor (setores editaveis, v1.3.106).

Camadas:
  - `MatchCanonicalSectorTests` / `GetSectorMembersTests`: puros (sem banco), rodam
    sempre. Cobrem a deteccao de membros (reverse-resolution) e a garantia de que o
    novo nome continua resolvendo para o mesmo `sector_id` (regras intactas).
  - `RenameSectorCascadeIntegrationTests`: integracao real, guardada por
    `_pg_available`. So roda contra um BANCO DE TESTE (skip caso contrario). NUNCA
    rodar contra producao (guard no conftest).
"""
import os
import sys
import unittest
import uuid
from unittest import mock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories import sector_aliases
from repositories.admin_criteria import get_sector_members, rename_sector_with_cascade


def _rule(pattern_type, pattern_value, target, priority=100):
    """Constroi uma regra ja com pattern_value NORMALIZADO (como vem do banco)."""
    return {
        "pattern_type": pattern_type,
        "pattern_value": sector_aliases._norm(pattern_value),
        "canonical_sector_id": target,
        "priority": priority,
    }


class MatchCanonicalSectorTests(unittest.TestCase):
    """Matcher puro: a base da deteccao de membros e do 'regras intactas'."""

    def test_setor_exact_ignora_acento_e_caixa(self):
        rules = [_rule("setor_exact", "fenix", "fenix")]
        self.assertEqual(sector_aliases.match_canonical_sector(rules, setor="FÊNIX"), "fenix")

    def test_setor_contains(self):
        rules = [_rule("setor_contains", "celula", "celula_atendimento")]
        self.assertEqual(
            sector_aliases.match_canonical_sector(rules, setor="Célula de Atendimento"),
            "celula_atendimento",
        )

    def test_escala_contains(self):
        rules = [_rule("escala_contains", "central", "transferencia")]
        self.assertEqual(
            sector_aliases.match_canonical_sector(rules, escala="CENTRAL - VERDE"),
            "transferencia",
        )

    def test_sem_match_retorna_none(self):
        rules = [_rule("setor_exact", "fenix", "fenix")]
        self.assertIsNone(sector_aliases.match_canonical_sector(rules, setor="logistica"))

    def test_regras_vazias_retorna_none(self):
        self.assertIsNone(sector_aliases.match_canonical_sector([], setor="fenix"))

    def test_primeira_regra_que_casa_vence(self):
        # caller ja ordena por priority DESC; o matcher retorna o primeiro match.
        rules = [
            _rule("setor_exact", "x", "sector_a"),
            _rule("setor_contains", "x", "sector_b"),
        ]
        self.assertEqual(sector_aliases.match_canonical_sector(rules, setor="x"), "sector_a")

    def test_novo_rotulo_resolve_para_o_mesmo_setor(self):
        # Apos renomear para "Fênix Premium", o alias setor_exact do novo nome garante
        # que colaboradores com o novo nome continuem resolvendo para 'fenix'
        # (regra de auditoria intacta).
        rules = [_rule("setor_exact", "Fênix Premium", "fenix", priority=200)]
        self.assertEqual(
            sector_aliases.match_canonical_sector(rules, setor="Fênix Premium"),
            "fenix",
        )


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        return None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def close(self):
        pass


class GetSectorMembersTests(unittest.TestCase):
    """Deteccao de membros sem banco: regras mockadas + colaboradores fake."""

    def _factory(self, colaboradores):
        return lambda: _FakeConn(colaboradores)

    def test_detecta_apenas_quem_resolve_para_o_setor(self):
        rules = [
            _rule("setor_exact", "fenix", "fenix"),
            _rule("setor_contains", "uti", "uti"),
        ]
        colaboradores = [
            {"id": 1, "nome": "A", "setor": "FÊNIX", "escala": "", "supervisor": "", "organizacao_telefonia": ""},
            {"id": 2, "nome": "B", "setor": "UTI", "escala": "", "supervisor": "", "organizacao_telefonia": ""},
            {"id": 3, "nome": "C", "setor": "LOGISTICA", "escala": "", "supervisor": "", "organizacao_telefonia": ""},
        ]
        with mock.patch.object(sector_aliases, "list_active_rules", return_value=rules):
            members = get_sector_members(self._factory(colaboradores), "fenix")

        self.assertEqual([m["id"] for m in members], [1])
        self.assertEqual(members[0]["nome"], "A")
        self.assertEqual(members[0]["setor"], "FÊNIX")

    def test_setor_sem_membros_retorna_vazio(self):
        rules = [_rule("setor_exact", "fenix", "fenix")]
        colaboradores = [
            {"id": 1, "nome": "A", "setor": "LOGISTICA", "escala": "", "supervisor": "", "organizacao_telefonia": ""},
        ]
        with mock.patch.object(sector_aliases, "list_active_rules", return_value=rules):
            members = get_sector_members(self._factory(colaboradores), "fenix")
        self.assertEqual(members, [])


# ── Integracao (so com banco de TESTE) ───────────────────────────────────────
try:
    from db.connection import get_connection

    _pg_available = True
    try:
        _probe = get_connection()
        _probe.close()
    except Exception:
        _pg_available = False
except Exception:
    _pg_available = False


@unittest.skipUnless(_pg_available, "PostgreSQL not available - integration test")
class RenameSectorCascadeIntegrationTests(unittest.TestCase):
    """Fim-a-fim: rename cascateia colaboradores.setor e mantem as regras presas ao id.

    Usa entidades descartaveis com sufixo aleatorio e limpa tudo no tearDown.
    """

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.sector_id = f"ztest_sector_{self.suffix}"
        self.old_label = f"ZTest Old {self.suffix}"
        self.new_label = f"ZTest New {self.suffix}"
        self.setor_string = f"ZTESTSETOR{self.suffix}"
        self.alert_id = f"ZTEST-ALERT-{self.suffix}"
        self.colab_id = None

        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO audit_sectors (id, label, description) VALUES (%s, %s, %s)",
                (self.sector_id, self.old_label, "teste de rename"),
            )
            c.execute(
                "INSERT INTO audit_alerts (id, sector_id, label) VALUES (%s, %s, %s)",
                (self.alert_id, self.sector_id, "Alerta de teste"),
            )
            c.execute(
                "INSERT INTO audit_criteria (alert_id, chave, label, weight) VALUES (%s, %s, %s, %s)",
                (self.alert_id, "saudacao", "Saudação", 1.0),
            )
            c.execute(
                "INSERT INTO colaboradores (nome, setor, status) VALUES (%s, %s, %s) RETURNING id",
                (f"ZTest Colab {self.suffix}", self.setor_string, "ATIVO"),
            )
            self.colab_id = c.fetchone()[0]
            conn.commit()
        finally:
            conn.close()

        # Alias para o setor cru do colaborador resolver ao sector_id de teste.
        sector_aliases.create_alias(
            get_connection,
            pattern_type="setor_exact",
            pattern_value=self.setor_string,
            canonical_sector_id=self.sector_id,
            priority=200,
            alterado_por="test",
            origem="script",
        )
        sector_aliases.clear_cache()

    def tearDown(self):
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM audit_criteria WHERE alert_id = %s", (self.alert_id,))
            c.execute("DELETE FROM audit_alerts WHERE id = %s", (self.alert_id,))
            if self.colab_id is not None:
                c.execute("DELETE FROM colaboradores WHERE id = %s", (self.colab_id,))
                c.execute("DELETE FROM colaboradores_audit_log WHERE entity_id = %s", (str(self.colab_id),))
            c.execute("DELETE FROM sector_aliases WHERE canonical_sector_id = %s", (self.sector_id,))
            c.execute("DELETE FROM audit_sectors WHERE id = %s", (self.sector_id,))
            c.execute("DELETE FROM audit_sectors_audit_log WHERE entity_id = %s", (self.sector_id,))
            conn.commit()
        finally:
            conn.close()
        sector_aliases.clear_cache()

    def _fetch_one(self, sql, params):
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute(sql, params)
            return c.fetchone()
        finally:
            conn.close()

    def test_rename_cascateia_colaborador_e_mantem_regras(self):
        result = rename_sector_with_cascade(
            get_connection,
            self.sector_id,
            self.new_label,
            cascade=True,
            alterado_por="test",
            origem="script",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["affected"], 1)

        # 1. label do setor atualizado
        row = self._fetch_one("SELECT label FROM audit_sectors WHERE id = %s", (self.sector_id,))
        self.assertEqual(row[0], self.new_label)

        # 2. colaborador cascateado para o novo nome
        row = self._fetch_one("SELECT setor FROM colaboradores WHERE id = %s", (self.colab_id,))
        self.assertEqual(row[0], self.new_label)

        # 3. regras intactas: o novo nome resolve para o MESMO sector_id
        sector_aliases.clear_cache()
        canon = sector_aliases.resolve_canonical_sector(get_connection, setor=self.new_label)
        self.assertEqual(canon, self.sector_id)

        # 4. o id (a que os criterios estao presos) nao mudou: alerta/criterio seguem la
        row = self._fetch_one("SELECT COUNT(*) FROM audit_alerts WHERE sector_id = %s", (self.sector_id,))
        self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main()
