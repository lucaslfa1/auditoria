"""Camada central de persistência — fachada histórica do banco (PostgreSQL).

Papel no sistema: este módulo nasceu monolítico e hoje atua em dois modos:

1. **Fachada de delegação** — a maioria das funções apenas repassa para o
   repositório correspondente em `repositories/` (audits, saved_files,
   classification_review, configuration...). Callers antigos continuam
   importando `database.X`; a implementação real vive no repository.
   Decisão documentada (v1.3.127): NÃO dividir este arquivo — os reexports
   preservam compatibilidade e o custo/risco do split não se paga.
2. **Lógica própria** — bootstrap do banco (`init_db`: migrations + seeds).
   A persistência de artefatos de auditoria e o anexo/recuperação de áudio
   vivem em `db.audit_media`; a montagem de Arquivos Salvos vive em
   `db.saved_audits` — ambos reexportados aqui para compatibilidade.

CUSTO DE API: zero — nenhuma chamada a serviços pagos; somente PostgreSQL.
"""

import logging
import os
import json
import unicodedata
from datetime import datetime, timezone
from typing import Optional, Any
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)

from storage.audit_storage import resolve_stored_audit_audio_path, store_audit_audio_file
from db.connection import create_connection, is_production_environment
from db.domain_constants import (
    DEFAULT_AUDIT_STATUS,
    DEFAULT_REVIEW_QUEUE_STATUS,
    DEFAULT_USER_ROLE,
    REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_PENDING,
)
from db.migrations import run_pending_migrations
from db.schema_tools import (
    ensure_schema_metadata_table,
    set_schema_metadata,
)
from repositories.common import normalize_huawei_agent_id, normalize_source_type, normalize_user_role
from schemas import AuditResult

# ── Reexports: lógica movida para módulos dedicados (fachada fina) ─────────
# Callers e testes continuam acessando estes nomes via `db.database.<nome>`
# (inclusive os com underscore — ex.: monkeypatch de
# `db.database._sync_arquivo_salvo_for_audit_inline`).
from db.saved_audits import (
    BRASILIA_TZ,
    SAVED_AUDIT_SOURCE_METADATA_KEYS,
    _as_dict,
    _as_plain_dicts,
    _build_saved_audit_content,
    _build_saved_audit_filename,
    _build_saved_audit_metadata,
    _coerce_saved_audit_call_iso,
    _find_nested_value,
    _format_saved_audit_call_timestamp,
    _json_safe_number,
    _saved_audit_call_timestamp,
    _saved_audit_source_metadata,
    _slug_file_part,
    _sync_arquivo_salvo_for_audit_inline,
)
from db.audit_media import (
    _attach_audio_to_audit_record,
    attach_audio_to_audit_record,
    persist_audit_artifacts,
    recover_audit_audio_from_classified_queue,
)


def get_connection():
    """Abre conexão PostgreSQL via pool (`db.connection.create_connection`) — passada como factory aos repositories."""
    return create_connection()


def _is_production_environment() -> bool:
    """True em produção (ENVIRONMENT=production explícito ou K_SERVICE do Cloud Run)."""
    return is_production_environment()


def _resolve_auth_users_seed_path(raw_path: str) -> str:
    """Resolve o path do seed de usuários (relativo vira relativo a backend/db/)."""
    candidate = (raw_path or "").strip()
    if not candidate:
        return ""
    if os.path.isabs(candidate):
        return candidate
    return os.path.join(os.path.dirname(__file__), candidate)


def _load_auth_seed_users_from_config() -> list[dict]:
    """Carrega usuários para o seed inicial: env AUTH_USERS_JSON > arquivo AUTH_USERS_FILE.

    Em produção, a ausência de ambos é ERRO (não existe fallback local, por
    segurança). Em dev/teste, retorna lista vazia.
    """
    raw_inline_users = (os.getenv("AUTH_USERS_JSON", "") or "").strip()
    if raw_inline_users:
        try:
            data = json.loads(raw_inline_users)
        except json.JSONDecodeError as exc:
            import logging
            logging.getLogger(__name__).warning("AUTH_USERS_JSON invalido: %s", exc)
            raise RuntimeError("AUTH_USERS_JSON inválido.") from exc
        if not isinstance(data, list):
            raise RuntimeError("AUTH_USERS_JSON deve conter uma lista de usuários.")
        return data

    explicit_users_file = (os.getenv("AUTH_USERS_FILE", "") or "").strip()
    if explicit_users_file:
        resolved_path = _resolve_auth_users_seed_path(explicit_users_file)
        if not resolved_path or not os.path.exists(resolved_path):
            raise RuntimeError("AUTH_USERS_FILE configurado, mas o arquivo não foi encontrado.")
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("AUTH_USERS_FILE inválido.") from exc
        if not isinstance(data, list):
            raise RuntimeError("AUTH_USERS_FILE deve conter uma lista de usuários.")
        return data

    if _is_production_environment():
        raise RuntimeError(
            "Em produção, seed de usuários exige AUTH_USERS_JSON ou AUTH_USERS_FILE. "
            "A fallback local padrão está desativada por segurança."
        )

    return []


def _is_isolated_test_database() -> bool:
    """True quando rodando sob pytest (seeds pesados são pulados para isolar os testes)."""
    return os.getenv("PYTEST_CURRENT_TEST") is not None


def _should_seed_operadores_from_json() -> bool:
    """Controla seed de operadores no init_db.

    Em ambiente de teste (bancos temporarios `test_*.db`), o seed automatico deve
    ficar desativado para manter isolamento e previsibilidade dos testes.
    """
    raw_flag = (os.getenv("AUDITORIA_SEED_OPERADORES_JSON", "auto") or "").strip().lower()
    if raw_flag in {"1", "true", "yes", "on"}:
        return True
    if raw_flag in {"0", "false", "no", "off"}:
        return False

    if os.getenv("PYTEST_CURRENT_TEST") is not None:
        return False

    return True


def init_db():
    """Bootstrap do banco no startup do app (chamado pelo prestart/lifespan).

    Sequência: tabela de metadados → migrations pendentes (commit por step,
    v1.3.113) → configs default → seeds idempotentes (usuários, critérios,
    catálogo oficial v1.3.120, operadores). Seguro rodar em todo boot: cada
    seed tem guarda própria e não sobrescreve dados existentes.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        ensure_schema_metadata_table(c)
        run_pending_migrations(c)

        # Default settings para o RPA Telefonia
        default_configs = [
            ('tema_visual', 'corporativo', 'Tema visual padrao da interface'),
            ('robo_habilitado', 'false', 'Ativa ou desativa o robô de importação'),
            ('rpa_url_login', '', 'URL de acesso ao sistema de telefonia'),
            ('rpa_usuario', '', 'Usuário para acesso ao sistema'),
            ('rpa_senha', '', 'Senha para acesso ao sistema'),
            ('ia_prompt_global', '''REGRA CRÍTICA 1: IDENTIFICAÇÃO E SAUDAÇÃO (OBRIGATÓRIO):
O operador DEVE informar ao menos: Saudação (bom dia/boa tarde/boa noite) + Nome próprio.
Se NÃO houver saudação E NÃO houver nome, marque FAIL no critério de identificação.
Se houver saudação OU nome (mas não ambos), marque PARTIAL.
Se houver ambos (saudação + nome), marque PASS mesmo que não tenha citado empresa/setor.

REGRA CRÍTICA SEVERIDADE:
- Seja RIGOROSO na avaliação. Na dúvida entre pass e partial, prefira partial.
- Na dúvida entre partial e fail, considere o impacto: se o item é essencial ao procedimento, prefira fail.
- Omissão completa de um procedimento obrigatório = FAIL, não partial.
- Procedimento feito de forma incompleta mas com esforço evidente = PARTIAL.
- Apenas marque NA se o critério for genuinamente inaplicável ao tipo de ligação.''',
             'Prompt global de regras da IA auditora'),
        ]
        for chave, valor, desc in default_configs:
            c.execute(
                "INSERT INTO configuracoes (chave, valor, descricao) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (chave, valor, desc),
            )

        # Seed: setores, alertas e critérios de auditoria
        _seed_audit_criteria(c)

        # Seed: catálogo OFICIAL completo (dump de produção) em banco novo.
        # Sem ele, um banco recém-criado fica só com o setor 'logistica' do
        # seed legado — classificação/guardrails dos demais setores quebram.
        _seed_official_catalog(c)

        # Seed: aliases de setor (Fase 2 — DB-first sem hardcoded)
        _seed_sector_aliases(c)

        # Seed: Migrar os usuários para bcrypt se o banco estiver vazio
        _seed_users(c)
        set_schema_metadata(c, "db.engine", "postgresql")
        set_schema_metadata(c, "schema.bootstrap", "init_db_with_migrations")
        set_schema_metadata(c, "schema.last_init_at", datetime.now().isoformat())

        conn.commit()
    finally:
        conn.close()

    # Seed: operadores do RH a partir do JSON exportado (Cloud Run)
    if _should_seed_operadores_from_json():
        seed_operadores_from_json()


def seed_operadores_from_json():
    """Popula colaboradores a partir do operadores_seed.json se a tabela estiver vazia."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM colaboradores")
        count = c.fetchone()[0]
        if count > 0:
            logger.info("[seed] colaboradores ja possui %d registros. Pulando seed.", count)
            return

        seed_path = os.path.join(os.path.dirname(__file__), "data", "operadores_seed.json")
        if not os.path.exists(seed_path):
            logger.info("[seed] operadores_seed.json nao encontrado. Pulando seed.")
            return

        with open(seed_path, "r", encoding="utf-8") as f:
            operators = json.load(f)

        for op in operators:
            c.execute('''
                INSERT INTO colaboradores (
                    matricula, nome, supervisor, setor, escala, status,
                    auditavel, id_weon, id_huawei, id_telefonia, softphone_number,
                    telefonia_account, organizacao_telefonia, tipo_agente, status_telefonia
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                op.get("matricula", ""),
                op.get("nome", ""),
                op.get("supervisor", ""),
                op.get("setor", ""),
                op.get("escala", ""),
                op.get("status", "ATIVO"),
                1 if str(op.get("status", "ATIVO")).strip().upper() == "ATIVO" else 0,
                op.get("id_weon", ""),
                op.get("id_huawei", ""),
                op.get("id_telefonia", ""),
                op.get("softphone_number", ""),
                op.get("telefonia_account", ""),
                op.get("organizacao_telefonia", ""),
                op.get("tipo_agente", ""),
                op.get("status_telefonia", ""),
            ))

        conn.commit()
        logger.info("[seed] %d operadores importados de operadores_seed.json.", len(operators))
    except Exception as e:
        logger.error("[seed] Erro ao importar operadores: %s", e)
    finally:
        conn.close()


def get_database_runtime_info() -> dict:
    """Snapshot do banco para diagnóstico: engine, ambiente, nº de tabelas, migrations aplicadas e schema_metadata."""
    info = {
        "engine": "postgresql",
        "path": "",
        "environment": "production" if _is_production_environment() else "development",
        "table_count": 0,
        "applied_migrations": [],
        "schema_metadata": {},
    }

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
        row = cursor.fetchone()
        info["table_count"] = int(row[0]) if row else 0

        # Check schema_metadata table exists
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'schema_metadata'"
        )
        meta_exists = cursor.fetchone()
        if meta_exists and int(meta_exists[0]) > 0:
            cursor.execute("SELECT key, value FROM schema_metadata ORDER BY key")
            info["schema_metadata"] = {
                str(row["key"]): str(row["value"] or "")
                for row in cursor.fetchall()
            }

        # Check schema_migrations table exists
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'schema_migrations'"
        )
        mig_exists = cursor.fetchone()
        if mig_exists and int(mig_exists[0]) > 0:
            cursor.execute("SELECT name FROM schema_migrations ORDER BY name")
            info["applied_migrations"] = [str(row["name"]) if isinstance(row, dict) else str(row[0]) for row in cursor.fetchall()]
    finally:
        conn.close()

    return info


def _seed_users(c):
    """Seed inicial de `users` (só roda com a tabela VAZIA).

    Fonte: AUTH_USERS_JSON/AUTH_USERS_FILE. Banco vazio sem bootstrap
    configurado é erro fatal fora de teste — evita subir app sem login.
    Senhas entram com hash bcrypt.
    """
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        import bcrypt

        users = _load_auth_seed_users_from_config()

        if not users:
            if _is_isolated_test_database():
                logger.info("Banco de teste sem bootstrap de usuarios explicito. Seed de usuarios ignorado.")
                return
            raise RuntimeError(
                "Banco sem usuarios e nenhum bootstrap configurado. "
                "Defina AUTH_USERS_JSON ou AUTH_USERS_FILE antes de inicializar um banco vazio."
            )

        for u in users:
            normalized_username = str(u.get("username", "")).strip().lower()
            normalized_role = normalize_user_role(u.get("role"), default=None)
            if not normalized_username:
                raise RuntimeError("AUTH_USERS_* contem usuario inicial sem username valido.")
            if normalized_role is None:
                raise RuntimeError(f"AUTH_USERS_* contem role invalido para o usuario {normalized_username}.")
            pw = u.get("password", "admin").encode("utf-8")
            pw_hash = bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")
            c.execute(
                "INSERT INTO users (username, password_hash, role, supervisor_name) VALUES (%s, %s, %s, %s)",
                (normalized_username, pw_hash, normalized_role, u.get("supervisor_name", ""))
            )



# Backward-compatible alias


def _seed_audit_criteria(c):
    """Sincroniza setores, alertas e critérios com scoring_rules.bootstrap.yaml (Fase 1.2 DB-first).

    Roda apenas uma vez no bootstrap inicial do ambiente. Usa DO NOTHING
    para garantir idempotência caso o banco já tenha dados parciais.
    NUNCA apaga ou sobrescreve registros em deploys subsequentes, para
    preservar as edições feitas pelos usuários via UI (audit_log).
    """
    from pathlib import Path
    from psycopg2.extras import execute_values
    from db.scoring_loader import _YAML_PATH

    # ── 1. Abortar se o banco já estiver populado ────────────────────────
    c.execute("SELECT COUNT(*) FROM audit_sectors")
    if c.fetchone()[0] > 0:
        logger.info("[seed] Catálogo de critérios já populado no banco. Seed ignorado (preservando DB).")
        return

    if not _YAML_PATH.exists():
        logger.warning("[seed] Arquivo %s não encontrado. Pulando seed de critérios.", _YAML_PATH)
        return

    logger.info("[seed] Banco vazio. Carregando catálogo inicial de %s...", _YAML_PATH.name)

    # ── 2. INSERT setores (batch) ────────────────────────────────────────
    _sectors = _build_sector_seed_data()
    execute_values(
        c,
        """INSERT INTO audit_sectors (id, label, description) VALUES %s
           ON CONFLICT(id) DO NOTHING""",
        [(sid, label, desc) for sid, label, desc in _sectors],
    )

    # ── 3. INSERT alertas (batch) ────────────────────────────────────────
    _alerts = _build_alert_seed_data()
    alert_rows = [(a[0], a[1], a[2], a[3], a[4], a[5]) for a in _alerts]

    execute_values(
        c,
        """INSERT INTO audit_alerts (id, sector_id, label, context, pop_ref, expected_direction) VALUES %s
           ON CONFLICT(id) DO NOTHING""",
        alert_rows,
    )

    # ── 4. INSERT critérios (batch) ──────────────────────────────────────
    criteria_rows = []
    for alert_id, _sector_id, _label, _context, _pop_ref, _expected_direction, criteria in _alerts:
        for crit_tuple in criteria:
            if len(crit_tuple) >= 5:
                crit_label, weight, desc, eval_type, deflator = crit_tuple[:5]
            elif len(crit_tuple) == 4:
                crit_label, weight, desc, eval_type = crit_tuple
                deflator = 0.0
            else:
                crit_label, weight, desc = crit_tuple[:3]
                eval_type = "auto"
                deflator = 0.0
            criteria_rows.append((alert_id, crit_label, desc or "", weight, eval_type, deflator))

    if criteria_rows:
        execute_values(
            c,
            "INSERT INTO audit_criteria (alert_id, label, description, weight, evaluation_type, deflator) VALUES %s",
            criteria_rows,
        )

    logger.info(
        "[seed] Catálogo inicial populado (%d setores, %d alertas, %d critérios)",
        len(_sectors), len(_alerts), len(criteria_rows),
    )



# Seed data extracted to db/seed_data.py (backed by scoring_rules.yaml).
from db.seed_data import build_alert_seed_data as _build_alert_seed_data
from db.seed_data import build_sector_seed_data as _build_sector_seed_data


# Seed inicial de sector_aliases — Fase 2 do plano DB-first.
# Roda apenas em ambientes novos (count == 0). Mesma estrategia da Fase 1.2:
# nao destrutivo, preserva edicoes via UI.
_SECTOR_ALIASES_BOOTSTRAP: tuple[tuple[str, str, str, int, str], ...] = (
    ("supervisor_contains", "miralha", "transferencia", 1000, "Supervisor Miralha gerencia Longo Percurso/Transferência"),
    ("setor_startswith", "uti", "uti", 900, "Setor RH 'UTI - AZUL/CINZA/...' aglutinado em UTI"),
    ("setor_startswith", "rj", "uti", 900, "Setor RH 'RJ - AZUL/CINZA/...' representa UTI de RJ"),
    ("setor_startswith", "bas", "bas", 900, "Setor RH 'BAS - Amarela/BASE PR/...' aglutinado em BAS (cobre BASE também)"),
    ("setor_contains", "transferencia", "transferencia", 870, "Setor RH literal contém 'transferencia'"),
    ("setor_contains", "fenix", "fenix", 860, "Setor RH 'FENIX'/'Fênix' → fenix"),
    ("escala_contains", "fenix", "fenix", 860, "Escala 'FÊNIX' (supervisor Adryan Celso) → setor fenix"),
    ("setor_contains", "distribuicao", "distribuicao", 850, "Setor RH 'Distribuição' (com/sem acento, normalizado)"),
    ("setor_contains", "cadastro", "cadastro", 840, "Setor RH 'Cadastro'"),
    ("setor_contains", "checklist", "checklist", 830, "Setor RH 'Checklist'"),
    ("escala_contains", "checklist", "checklist", 830, "Escala 'CHECKLIST'"),
    ("setor_contains", "celula", "celula_atendimento", 820, "Setor RH 'Célula' → setor celula_atendimento"),
    ("escala_contains", "celula", "celula_atendimento", 820, "Escala 'CÉLULA'"),
    ("setor_contains", "receptivo", "celula_atendimento", 810, "Setor RH 'Receptivo' → celula_atendimento"),
    ("escala_contains", "unilever", "logistica_unilever", 800, "Escala 'UNILEVER'"),
    ("setor_contains", "unilever", "logistica_unilever", 800, "Setor RH 'Unilever'"),
    ("escala_contains", "mondelez", "mondelez", 790, "Escala 'MONDELEZ'"),
    ("setor_contains", "mondelez", "mondelez", 790, "Setor RH 'Mondelez'"),
    ("escala_contains", "taborda", "logistica", 780, "Escala 'TABORDA' → logistica (campanha)"),
    ("setor_contains", "taborda", "logistica", 780, "Setor RH 'Taborda' → logistica"),
    ("setor_exact", "logistica", "logistica", 770, "Setor RH 'Logística' literal"),
    ("organizacao_contains", "cadastro", "cadastro", 700, "Organização Huawei 'Cadastro'"),
    ("organizacao_contains", "unilever", "logistica_unilever", 700, "Organização Huawei 'Unilever'"),
    ("organizacao_contains", "mondelez", "mondelez", 700, "Organização Huawei 'Mondelez'"),
    ("organizacao_contains", "taborda", "logistica", 700, "Organização Huawei 'Taborda'"),
    ("organizacao_contains", "fenix", "fenix", 700, "Organização Huawei 'Fênix'"),
    ("organizacao_contains", "checklist", "checklist", 700, "Organização Huawei 'Checklist'"),
    ("organizacao_contains", "celula", "celula_atendimento", 700, "Organização Huawei 'Célula'"),
    ("organizacao_contains", "base de sinistro", "bas", 700, "Organização Huawei 'Base de Sinistro'"),
    ("organizacao_contains", "distribu", "distribuicao", 700, "Organização Huawei 'Distribu...'"),
    ("organizacao_startswith", "uti", "uti", 695, "Organização Huawei começando com 'UTI'"),
    ("organizacao_contains", " uti", "uti", 695, "Organização Huawei contendo ' UTI ' isolado"),
    ("organizacao_contains", "rastreamento", "transferencia", 650, "Organização Huawei 'Rastreamento' → transferencia"),
    ("organizacao_contains", "lp", "transferencia", 650, "Organização Huawei 'LP' (Longo Percurso)"),
    ("organizacao_contains", "bbm", "distribuicao", 650, "Organização Huawei 'BBM' absorvida por Distribuição"),
    ("organizacao_contains", "logistica", "logistica", 600, "Organização Huawei 'Logística' genérica"),
    ("organizacao_contains", "profarma", "logistica", 600, "Organização Huawei 'Profarma' → logistica"),
    ("organizacao_contains", "comandolog", "logistica", 600, "Organização Huawei 'Comandolog' → logistica"),
    ("organizacao_contains", "tora", "logistica", 600, "Organização Huawei 'Tora' → logistica"),
    ("organizacao_contains", "sanofi", "logistica", 600, "Organização Huawei 'Sanofi' → logistica"),
    ("setor_exact", "grs", "uti", 200, "Legado: 'GRS' renomeado para UTI"),
    ("setor_exact", "rastreamento", "transferencia", 200, "Legado: setor 'rastreamento' renomeado"),
    ("setor_exact", "rast", "transferencia", 200, "Legado: abreviação 'rast' → transferencia"),
    ("setor_exact", "longo percurso", "transferencia", 200, "Legado: 'Longo Percurso' → transferencia"),
    ("setor_exact", "longo_percurso", "transferencia", 200, "Legado: 'longo_percurso' → transferencia"),
    ("setor_exact", "dist", "distribuicao", 200, "Legado: abreviação 'dist' → distribuicao"),
    ("setor_exact", "sinistro", "bas", 200, "Legado: 'sinistro' → BAS"),
    ("setor_exact", "sinistros", "bas", 200, "Legado: 'sinistros' → BAS"),
    ("setor_exact", "unilever", "logistica_unilever", 200, "Legado: 'unilever' sem prefixo"),
    ("setor_exact", "receptivo", "celula_atendimento", 200, "Legado: 'receptivo' sem prefixo"),
    ("setor_exact", "celula atendimento", "celula_atendimento", 200, "Legado: 'celula atendimento' com espaço"),
    ("setor_exact", "celula_atendimento", "celula_atendimento", 200, "Identidade: já canônico"),
)


def _seed_official_catalog(c):
    """Aplica o catálogo OFICIAL de setores/alertas/critérios em banco NOVO.

    Fonte: backend/db/seeds/audit_catalog_oficial.sql — dump --data-only do
    banco de produção (12 setores, 71 alertas, 1051 critérios em 2026-06-11;
    catálogo é a ground truth da auditoria, mantido pela auditora oficial).

    Guarda de segurança: só roda quando audit_sectors tem <= 1 linha (banco
    recém-criado, contendo no máximo o seed legado 'logistica'). Em qualquer
    banco real (>= 2 setores) é no-op — edições via UI nunca são tocadas.

    Em banco novo, o seed legado é REMOVIDO antes do dump para evitar colisão
    de ids seriais de audit_criteria (ON CONFLICT DO NOTHING esconderia
    critérios oficiais cujos ids coincidissem com os do seed legado).
    """
    c.execute("SELECT COUNT(*) FROM audit_sectors")
    if (c.fetchone() or [0])[0] > 1:
        return

    seed_path = os.path.join(os.path.dirname(__file__), "seeds", "audit_catalog_oficial.sql")
    if not os.path.exists(seed_path):
        logger.warning("[seed] catálogo oficial ausente em %s — banco fica só com o seed legado.", seed_path)
        return

    with open(seed_path, "r", encoding="utf-8") as fh:
        raw_lines = fh.read().splitlines()

    # O cabeçalho do pg_dump tem meta-comandos psql (\restrict) e SETs de
    # sessão de versões mais novas do Postgres (ex.: transaction_timeout é
    # PG17+) que quebram em servidores mais antigos/psycopg2. Os dados são
    # só INSERTs — aplica do primeiro INSERT em diante.
    first_insert = next(
        (i for i, line in enumerate(raw_lines) if line.startswith("INSERT INTO")), None
    )
    if first_insert is None:
        logger.warning("[seed] catálogo oficial sem INSERTs em %s — ignorado.", seed_path)
        return
    # Meta-comandos psql (\unrestrict) também aparecem no RODAPÉ do dump.
    sql_text = "\n".join(
        line for line in raw_lines[first_insert:] if not line.startswith("\\")
    )

    c.execute("DELETE FROM audit_criteria")
    c.execute("DELETE FROM audit_alerts")
    c.execute("DELETE FROM audit_sectors")
    c.execute(sql_text)

    # INSERTs vieram com ids explícitos: realinha a sequência serial para o
    # próximo INSERT via UI não colidir.
    c.execute("SELECT pg_get_serial_sequence('audit_criteria', 'id')")
    seq_row = c.fetchone()
    seq_name = seq_row[0] if seq_row else None
    if seq_name:
        c.execute(
            "SELECT setval(%s, COALESCE((SELECT MAX(id) FROM audit_criteria), 1))",
            (seq_name,),
        )

    c.execute("SELECT COUNT(*) FROM audit_sectors")
    total = (c.fetchone() or [0])[0]
    logger.info("[seed] catálogo oficial aplicado: %d setores.", total)


def _seed_sector_aliases(c):
    """Popula sector_aliases apenas em DB vazio. Idempotente (aborta se ja populado).

    Fase 2 do plano DB-first. Apos esta versao, edicoes via UI sao permanentes —
    o seed nao mais sobrescreve.
    """
    from psycopg2.extras import execute_values

    c.execute("SELECT COUNT(*) FROM sector_aliases")
    if c.fetchone()[0] > 0:
        logger.info("[seed] sector_aliases ja populado. Seed ignorado (preservando DB).")
        return

    rows = [
        (pt, pv, csid, prio, desc)
        for pt, pv, csid, prio, desc in _SECTOR_ALIASES_BOOTSTRAP
    ]
    execute_values(
        c,
        """INSERT INTO sector_aliases
               (pattern_type, pattern_value, canonical_sector_id, priority, descricao)
           VALUES %s
           ON CONFLICT DO NOTHING""",
        rows,
    )
    logger.info("[seed] sector_aliases populado com %d regras.", len(rows))


def _seed_ai_prompts(c):
    """Popula ai_prompts copiando do prompts.json se a tabela estiver vazia. Idempotente."""
    c.execute("SELECT COUNT(*) FROM ai_prompts")
    if c.fetchone()[0] > 0:
        logger.info("[seed] ai_prompts ja populado. Seed ignorado.")
        return

    from core.config import _load_json_config
    import json
    prompts_dict = _load_json_config("prompts.json")
    if not prompts_dict:
        return

    # Achata o dict em chaves dot-path (ex.: "classification.system")
    def _flatten(d, parent_key=''):
        """Achata o JSON de prompts em pares (dot-path, valor-json); `safety_nets.*` fica como JSON inteiro."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict) and k != "safety_nets": # we want safety_nets.mondelez to be the JSON value
                if parent_key == "safety_nets":
                    items.append((new_key, json.dumps(v)))
                else:
                    items.extend(_flatten(v, new_key).items())
            else:
                items.append((new_key, json.dumps(v)))
        return dict(items)
        
    flat_prompts = _flatten(prompts_dict)
    
    from psycopg2.extras import execute_values
    rows = [(k, v) for k, v in flat_prompts.items()]
    execute_values(
        c,
        "INSERT INTO ai_prompts (chave, valor) VALUES %s ON CONFLICT DO NOTHING",
        rows
    )
    logger.info("[seed] ai_prompts populado com %d regras via prompts.json.", len(rows))


# --- Operators (legacy, redirected to colaboradores) -----------------











def upsert_ligacao_auditada(
    nome_arquivo: str,
    caminho_relativo: str,
    hash_arquivo: str,
    grupo: Optional[str] = None,
    subgrupo: Optional[str] = None,
    setor_referencia: Optional[str] = None,
    alerta_referencia: Optional[str] = None,
    qualidade_referencia: Optional[str] = None,
    observacao: Optional[str] = None,
) -> int:
    """Fachada: delega para `repositories.classification_review.upsert_ligacao_auditada` (implementação e docstring lá)."""
    from repositories.classification_review import upsert_ligacao_auditada as repository_upsert_ligacao_auditada

    return repository_upsert_ligacao_auditada(
        get_connection,
        nome_arquivo,
        caminho_relativo,
        hash_arquivo,
        grupo,
        subgrupo,
        setor_referencia,
        alerta_referencia,
        qualidade_referencia,
        observacao,
    )


def get_ligacao_auditada_por_hash(hash_arquivo: str) -> Optional[dict]:
    """Fachada: delega para `repositories.classification_review.get_ligacao_auditada_por_hash` (implementação e docstring lá)."""
    from repositories.classification_review import get_ligacao_auditada_por_hash as repository_get_ligacao_auditada_por_hash

    return repository_get_ligacao_auditada_por_hash(get_connection, hash_arquivo)


def registrar_resultado_classificacao(
    ligacao_id: int,
    setor_previsto: Optional[str] = None,
    alerta_previsto: Optional[str] = None,
    confianca: Optional[float] = None,
    operador_previsto: Optional[str] = None,
    modelo: Optional[str] = None,
    versao_prompt: Optional[str] = None,
    acertou_setor: Optional[bool] = None,
    acertou_alerta: Optional[bool] = None,
    erro: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Fachada: delega para `repositories.classification_review.registrar_resultado_classificacao` (implementação e docstring lá)."""
    from repositories.classification_review import registrar_resultado_classificacao as repository_registrar_resultado_classificacao

    return repository_registrar_resultado_classificacao(
        get_connection,
        ligacao_id,
        setor_previsto,
        alerta_previsto,
        confianca,
        operador_previsto,
        modelo,
        versao_prompt,
        acertou_setor,
        acertou_alerta,
        erro,
        metadata,
    )


def sincronizar_fila_revisao_classificacao(
    input_hash: str,
    nome_arquivo: str,
    setor_previsto: Optional[str] = None,
    alerta_previsto: Optional[str] = None,
    confianca: Optional[float] = None,
    operador_previsto: Optional[str] = None,
    erro: Optional[str] = None,
    precisa_revisao: bool = False,
    prioridade: str = REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    motivos_revisao: Optional[list[str]] = None,        
    metadata: Optional[dict] = None,
    status_override: Optional[str] = None,
    ) -> Optional[int]:
    """Fachada: delega para `repositories.classification_review.sincronizar_fila_revisao_classificacao` (implementação e docstring lá)."""
    from repositories.classification_review import sincronizar_fila_revisao_classificacao as repository_sincronizar_fila_revisao_classificacao

    return repository_sincronizar_fila_revisao_classificacao(
        get_connection,
        input_hash,
        nome_arquivo,
        setor_previsto=setor_previsto,
        alerta_previsto=alerta_previsto,
        confianca=confianca,
        operador_previsto=operador_previsto,
        erro=erro,
        precisa_revisao=precisa_revisao,
        prioridade=prioridade,
        motivos_revisao=motivos_revisao,
        metadata=metadata,
        status_override=status_override,
    )


def limpar_fila_revisao_classificacao_antiga(hours_old: int = 24) -> dict:
    """Fachada: delega para `repositories.classification_review.limpar_fila_revisao_classificacao_antiga` (implementação e docstring lá)."""
    from repositories.classification_review import limpar_fila_revisao_classificacao_antiga as repository_limpar_fila
    return repository_limpar_fila(get_connection, hours_old)


def listar_fila_revisao_classificacao(
    limit: Optional[int] = None,
    status: Optional[str] = REVIEW_QUEUE_STATUS_PENDING,
    sector_id: Optional[str] = None,
    origem: Optional[str] = None,
    order_by: str = "priority",
) -> list[dict]:
    """Fachada: delega para `repositories.classification_review.listar_fila_revisao_classificacao` (implementação e docstring lá)."""
    from repositories.classification_review import listar_fila_revisao_classificacao as repository_listar_fila_revisao_classificacao

    return repository_listar_fila_revisao_classificacao(get_connection, limit, status, sector_id, origem, order_by)


def obter_fila_revisao_classificacao_por_hash(input_hash: str) -> Optional[dict]:
    """Fachada: delega para `repositories.classification_review.obter_fila_revisao_classificacao_por_hash` (implementação e docstring lá)."""
    from repositories.classification_review import obter_fila_revisao_classificacao_por_hash as repository_obter_fila_revisao_classificacao_por_hash

    return repository_obter_fila_revisao_classificacao_por_hash(get_connection, input_hash)


def descartar_item_automacao(
    input_hash: str,
    *,
    motivo: str,
    tombstone: bool = False,
    tombstone_motivo: Optional[str] = None,
    loop_limit: int = 3,
    log_fields: Optional[dict] = None,
) -> dict:
    """Fachada: delega para `repositories.classification_review.descartar_item_automacao` (implementação e docstring lá)."""
    from repositories.classification_review import descartar_item_automacao as repository_descartar_item_automacao

    return repository_descartar_item_automacao(
        get_connection,
        input_hash,
        motivo=motivo,
        tombstone=tombstone,
        tombstone_motivo=tombstone_motivo,
        loop_limit=loop_limit,
        log_fields=log_fields,
    )


def obter_fila_revisao_classificacao_por_auditoria(
    audit_id: int,
    audit_input_hash: Optional[str] = None,
) -> Optional[dict]:
    """Fachada: delega para `repositories.classification_review.obter_fila_revisao_classificacao_por_auditoria` (implementação e docstring lá)."""
    from repositories.classification_review import (
        obter_fila_revisao_classificacao_por_auditoria as repository_obter_fila_revisao_classificacao_por_auditoria,
    )

    return repository_obter_fila_revisao_classificacao_por_auditoria(
        get_connection,
        audit_id,
        audit_input_hash,
    )


def listar_paths_audio_classificado_fila_revisao() -> list[str]:
    """Fachada: delega para `repositories.classification_review.listar_paths_audio_classificado_fila_revisao` (implementação e docstring lá)."""
    from repositories.classification_review import listar_paths_audio_classificado_fila_revisao as repository_listar_paths_audio_classificado_fila_revisao

    return repository_listar_paths_audio_classificado_fila_revisao(get_connection)


def atualizar_status_fila_revisao_classificacao(
    input_hash: str,
    *,
    status: str,
    erro: Optional[str] = None,
    motivos_revisao_append: Optional[list[str]] = None,
    metadata_merge: Optional[dict] = None,
) -> bool:
    """Fachada: delega para `repositories.classification_review.atualizar_status_fila_revisao_classificacao` (implementação e docstring lá)."""
    from repositories.classification_review import atualizar_status_fila_revisao_classificacao as repository_atualizar_status_fila_revisao_classificacao

    return repository_atualizar_status_fila_revisao_classificacao(
        get_connection,
        input_hash,
        status=status,
        erro=erro,
        motivos_revisao_append=motivos_revisao_append,
        metadata_merge=metadata_merge,
    )


def corrigir_classificacao_fila_revisao(
    input_hash: str,
    *,
    setor_previsto: str,
    alerta_previsto: str,
    operador_previsto: Optional[str] = None,
    operator_id: Optional[str] = None,
    revisado_por: Optional[str] = None,
) -> Optional[dict]:
    """Fachada: delega para `repositories.classification_review.corrigir_classificacao_fila_revisao` (implementação e docstring lá)."""
    from repositories.classification_review import corrigir_classificacao_fila_revisao as repository_corrigir_classificacao_fila_revisao

    return repository_corrigir_classificacao_fila_revisao(
        get_connection,
        input_hash,
        setor_previsto=setor_previsto,
        alerta_previsto=alerta_previsto,
        operador_previsto=operador_previsto,
        operator_id=operator_id,
        revisado_por=revisado_por,
    )


def registrar_resultado_auditoria(
    ligacao_id: int,
    nota: Optional[float] = None,
    nota_maxima: Optional[float] = None,
    resumo: Optional[str] = None,
    detalhes: Optional[list[dict]] = None,
) -> int:
    """Fachada: delega para `repositories.classification_review.registrar_resultado_auditoria` (implementação e docstring lá)."""
    from repositories.classification_review import registrar_resultado_auditoria as repository_registrar_resultado_auditoria

    return repository_registrar_resultado_auditoria(get_connection, ligacao_id, nota, nota_maxima, resumo, detalhes)


def get_resumo_ligacoes_auditadas(setor: Optional[str] = None) -> dict:
    """Fachada: delega para `repositories.classification_review.get_resumo_ligacoes_auditadas` (implementação e docstring lá)."""
    from repositories.classification_review import get_resumo_ligacoes_auditadas as repository_get_resumo_ligacoes_auditadas

    return repository_get_resumo_ligacoes_auditadas(get_connection, setor)


def listar_ligacoes_auditadas(limit: int = 100, qualidade: Optional[str] = None, setor: Optional[str] = None) -> list[dict]:
    """Fachada: delega para `repositories.classification_review.listar_ligacoes_auditadas` (implementação e docstring lá)."""
    from repositories.classification_review import listar_ligacoes_auditadas as repository_listar_ligacoes_auditadas

    return repository_listar_ligacoes_auditadas(get_connection, limit, qualidade, setor)


def save_audit(
    result: AuditResult,
    input_hash: Optional[str] = None,
    alert_id: Optional[str] = None,
    alert_label: Optional[str] = None,
    operator_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    sector_id: Optional[str] = None,
    ai_feedback: Optional[str] = None,
    status: str = DEFAULT_AUDIT_STATUS,
    colaborador_id: Optional[int] = None,
    criado_por: str = "",
):
    """Salva a auditoria (delega ao repository) e espelha em Arquivos Salvos.

    Diferente da fachada pura: após o INSERT, chama
    `_sync_arquivo_salvo_for_audit` para o item aparecer na tela de revisão.
    """
    from repositories.audits import save_audit as repository_save_audit

    audit_id = repository_save_audit(
        get_connection,
        result,
        input_hash,
        alert_id,
        alert_label,
        operator_id,
        driver_name,
        sector_id,
        ai_feedback,
        status,
        colaborador_id=colaborador_id,
    )
    if audit_id:
        _sync_arquivo_salvo_for_audit(audit_id, criado_por=criado_por)
    return audit_id


def queue_audit_for_supervisor_review(
    result: AuditResult,
    input_hash: Optional[str] = None,
    alert_id: Optional[str] = None,
    alert_label: Optional[str] = None,
    operator_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    sector_id: Optional[str] = None,
    ai_feedback: Optional[str] = None,
    rebalance: bool = True,
) -> dict:
    """Enfileira a auditoria para aprovação do supervisor e espelha em Arquivos Salvos."""
    from repositories.audits import enqueue_audit_for_supervisor_review as repository_enqueue_audit_for_supervisor_review

    queued = repository_enqueue_audit_for_supervisor_review(
        get_connection,
        result,
        input_hash=input_hash,
        alert_id=alert_id,
        alert_label=alert_label,
        operator_id=operator_id,
        driver_name=driver_name,
        sector_id=sector_id,
        ai_feedback=ai_feedback,
        rebalance=rebalance,
    )
    audit_id = queued.get("audit_id") if isinstance(queued, dict) else None
    if audit_id:
        _sync_arquivo_salvo_for_audit(int(audit_id))
    return queued


def get_audit_media_record(audit_id: int) -> Optional[dict]:
    """Fachada: delega para `repositories.audits.get_audit_media_record_by_id` (implementação e docstring lá)."""
    from repositories.audits import get_audit_media_record_by_id as repository_get_audit_media_record_by_id

    return repository_get_audit_media_record_by_id(get_connection, audit_id)


def update_audit_result(input_hash: str, result: AuditResult, ai_feedback: Optional[str] = None) -> Optional[int]:
    """Atualiza o resultado da auditoria localizada pelo input_hash e re-espelha em Arquivos Salvos."""
    from repositories.audits import update_audit_result as repository_update_audit_result

    audit_id = repository_update_audit_result(get_connection, input_hash, result, ai_feedback)
    if audit_id:
        _sync_arquivo_salvo_for_audit(audit_id)
    return audit_id


def get_latest_audit_id_by_input_hash(input_hash: str) -> Optional[int]:
    """Fachada: delega para `repositories.audits.get_latest_audit_id_by_input_hash` (implementação e docstring lá)."""
    from repositories.audits import get_latest_audit_id_by_input_hash as repository_get_latest_audit_id_by_input_hash

    return repository_get_latest_audit_id_by_input_hash(get_connection, input_hash)


def get_audit_by_id(audit_id: int) -> Optional[dict]:
    """Fachada: delega para `repositories.audits.get_audit_by_id` (implementação e docstring lá).

    Era a única leitura de audits SEM fachada — `finalize_contestation_review`
    e `db.audit_media.recover_audit_audio_from_classified_queue` a chamavam e
    quebrariam com NameError/AttributeError se o branch executasse (BUG latente
    pré-v1.3.134).
    """
    from repositories.audits import get_audit_by_id as repository_get_audit_by_id

    return repository_get_audit_by_id(get_connection, audit_id)


def update_audit_result_by_id(
    audit_id: int,
    result: AuditResult,
    ai_feedback: Optional[str] = None,
) -> Optional[int]:
    """Atualiza o resultado de uma auditoria existente e re-espelha em Arquivos Salvos."""
    from repositories.audits import update_audit_result_by_id as repository_update_audit_result_by_id

    updated_id = repository_update_audit_result_by_id(get_connection, audit_id, result, ai_feedback)
    if updated_id:
        _sync_arquivo_salvo_for_audit(updated_id)
    return updated_id


def _sync_arquivo_salvo_for_audit(audit_id: int, *, criado_por: str = "") -> None:
    """Dispatch the saved_files sync (async in prod, inline under tests).

    Closes C3 from the 2026-05-10 review: the synchronous body used to be
    invoked inside `bulk_update_audits` loops, blocking the entire automation
    cycle on Postgres round-trips. The actual work now happens on a single
    background worker thread; producers return immediately. See
    `core.saved_files_sync_queue` for the dispatch policy.
    """
    from core.saved_files_sync_queue import enqueue as _enqueue_sync

    _enqueue_sync(audit_id, criado_por=criado_por)


def sync_arquivo_salvo_for_audit(audit_id: int) -> None:
    """Versão pública de `_sync_arquivo_salvo_for_audit` (despacho assíncrono do espelho)."""
    _sync_arquivo_salvo_for_audit(audit_id)


def update_audit_by_id(audit_id: int, result: AuditResult, ai_feedback: Optional[str] = None) -> Optional[dict]:
    """Wrapper para repositories.audits.update_audit_by_id.

    v1.3.90: agora retorna o dict completo do repository ({"updated", "rag_payload"})
    ou None se nao encontrar. Caller deve verificar `if not retorno:` para 404 e
    `retorno.get("rag_payload")` para agendar BackgroundTask de feedback RAG.
    """
    from repositories.audits import update_audit_by_id as repository_update_audit_by_id

    outcome = repository_update_audit_by_id(get_connection, audit_id, result, ai_feedback)
    if outcome and outcome.get("updated"):
        _sync_arquivo_salvo_for_audit(audit_id)
    return outcome






def get_stats():
    """Fachada: delega para `repositories.analytics.get_stats` (implementação e docstring lá)."""
    from repositories.analytics import get_stats as repository_get_stats

    return repository_get_stats(get_connection)

def get_history(limit=10):
    """Fachada: delega para `repositories.analytics.get_history` (implementação e docstring lá)."""
    from repositories.analytics import get_history as repository_get_history

    return repository_get_history(get_connection, limit)

class _SharedConnection:
    """Proxy de conexão que NEUTRALIZA o close() durante uso compartilhado.

    Permite passar a MESMA conexão para vários repositories em sequência
    (cada um chama close() ao terminar) sem fechá-la de fato — quem fecha é
    o caller, no finally. Todo o resto é delegado à conexão real.
    """
    __slots__ = ("_conn",)

    def __init__(self, conn):
        """Guarda a conexão real (via object.__setattr__, por causa do __setattr__ custom)."""
        object.__setattr__(self, "_conn", conn)

    def close(self):
        """No-op proposital: o dono da conexão fecha ao final do bloco."""
        pass

    def __getattr__(self, name):
        """Delega leitura de atributos/métodos à conexão real."""
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        """Delega escrita de atributos à conexão real (exceto o slot interno)."""
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)


def update_audit_status(audit_id: int, status: str, reason: Optional[str] = None, contested_criteria: Optional[str] = None):
    """Atualiza o status da auditoria e, na MESMA conexão, rebalanceia a fila do operador e re-espelha o Arquivo Salvo."""
    from repositories.audits import update_audit_status as repository_update_audit_status
    from repositories.audits import rebalance_operator_review_queue as repository_rebalance_operator_review_queue
    from repositories.audits import get_audit_by_id as repository_get_audit_by_id

    conn = get_connection()
    shared = _SharedConnection(conn)
    try:
        result = repository_update_audit_status(lambda: shared, audit_id, status, reason, contested_criteria)
        audit = repository_get_audit_by_id(lambda: shared, audit_id)
        if audit and (audit.get("operator_id") or audit.get("operator_name")):
            repository_rebalance_operator_review_queue(
                lambda: shared,
                operator_name=audit.get("operator_name"),
                operator_id=audit.get("operator_id"),
            )
        if audit:
            _sync_arquivo_salvo_for_audit(audit_id)
        return result
    finally:
        conn.close()


def discard_audit(audit_id: int, *, discarded_by: str, reason: Optional[str] = None) -> dict:
    """Descarta a auditoria e rebalanceia a fila pareada do operador (par órfão em awaiting_pair é promovido)."""
    from repositories.audits import discard_audit as repository_discard_audit
    from repositories.audits import rebalance_operator_review_queue as repository_rebalance_operator_review_queue
    from repositories.audits import get_audit_by_id as repository_get_audit_by_id

    conn = get_connection()
    shared = _SharedConnection(conn)
    try:
        audit = repository_get_audit_by_id(lambda: shared, audit_id)
        if audit is None:
            raise ValueError(f"Auditoria {audit_id} nao encontrada.")
        result = repository_discard_audit(
            lambda: shared,
            audit_id,
            discarded_by=discarded_by,
            reason=reason,
        )
        # Rebalancea a fila pareada do operador: se a descartada deixou um par orfao
        # em awaiting_pair, este chama promove o remanescente a pending_approval.
        if audit.get("operator_id") or audit.get("operator_name"):
            repository_rebalance_operator_review_queue(
                lambda: shared,
                operator_name=audit.get("operator_name"),
                operator_id=audit.get("operator_id"),
            )
        return result
    finally:
        conn.close()


def restore_audit(audit_id: int, *, restored_by: str) -> dict:
    """Restaura uma auditoria descartada e rebalanceia a fila pareada do operador."""
    from repositories.audits import restore_audit as repository_restore_audit
    from repositories.audits import rebalance_operator_review_queue as repository_rebalance_operator_review_queue
    from repositories.audits import get_audit_by_id as repository_get_audit_by_id

    conn = get_connection()
    shared = _SharedConnection(conn)
    try:
        audit = repository_get_audit_by_id(lambda: shared, audit_id)
        if audit is None:
            raise ValueError(f"Auditoria {audit_id} nao encontrada.")
        result = repository_restore_audit(
            lambda: shared,
            audit_id,
            restored_by=restored_by,
        )
        # Rebalancea a fila pareada: restaurar pode recriar um par, promovendo
        # eventualmente um awaiting_pair a pending_approval (ou vice-versa).
        if not result.get("already_restored") and (
            audit.get("operator_id") or audit.get("operator_name")
        ):
            repository_rebalance_operator_review_queue(
                lambda: shared,
                operator_name=audit.get("operator_name"),
                operator_id=audit.get("operator_id"),
            )
        if not result.get("already_restored"):
            _sync_arquivo_salvo_for_audit(audit_id)
        return result
    finally:
        conn.close()


def get_audits_for_export(
    month: int = None,
    year: int = None,
    supervisor: str = None,
    escala: str = None,
    sector_id: str = None,
    operator_name: str = None,
    statuses: Optional[list[str]] = None,
    limit: int = None,
    skip: int = 0,
    max_per_operator: Optional[int] = None,
) -> list[dict]:
    """Fachada: delega para `repositories.audits.get_audits_for_export` (implementação e docstring lá)."""
    from repositories.audits import get_audits_for_export as repository_get_audits_for_export

    return repository_get_audits_for_export(
        get_connection,
        month,
        year,
        supervisor,
        escala,
        sector_id,
        operator_name,
        statuses,
        limit,
        skip,
        max_per_operator,
    )


def finalize_contestation_review(
    audit_id: int,
    *,
    verdict: str,
    defense: str,
    reviewed_by: str,
    updated_details: Optional[list] = None,
) -> dict:
    """Conclui a revisão de contestação (veredito + defesa) e re-espelha o Arquivo Salvo."""
    from repositories.audits import finalize_contestation_review as repository_finalize_contestation_review

    result = repository_finalize_contestation_review(
        get_connection,
        audit_id,
        verdict=verdict,
        defense=defense,
        reviewed_by=reviewed_by,
        updated_details=updated_details,
    )
    audit = get_audit_by_id(audit_id)
    if audit and (audit.get("operator_id") or audit.get("operator_name")):
        from repositories.audits import rebalance_operator_review_queue as repository_rebalance_operator_review_queue

        repository_rebalance_operator_review_queue(
            get_connection,
            operator_name=audit.get("operator_name"),
            operator_id=audit.get("operator_id"),
        )

    _sync_arquivo_salvo_for_audit(audit_id)
    return result


def save_gestor_feedback(audit_id: int, gestor_nome: str, feedback_texto: str, pontos_melhoria: str) -> bool:
    """Fachada: delega para `repositories.supervisor_feedback.save_gestor_feedback` (implementação e docstring lá)."""
    from repositories.supervisor_feedback import save_gestor_feedback as repository_save_gestor_feedback

    return repository_save_gestor_feedback(get_connection, audit_id, gestor_nome, feedback_texto, pontos_melhoria)


def get_gestor_feedback(audit_id: int) -> dict | None:
    """Fachada: delega para `repositories.supervisor_feedback.get_gestor_feedback` (implementação e docstring lá)."""
    from repositories.supervisor_feedback import get_gestor_feedback as repository_get_gestor_feedback

    return repository_get_gestor_feedback(get_connection, audit_id)


def save_report_export(
    report_kind: str,
    file_format: str,
    filename: str = "",
    media_type: str = "",
    generated_by: str = "",
    operator_name: str = "",
    operator_id: str = "",
    alert_id: str = "",
    alert_label: str = "",
    sector_id: str = "",
    score: Optional[float] = None,
    max_score: Optional[float] = None,
    source_type: str = "",
    audit_timestamp: str = "",
    file_size_bytes: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Fachada: delega para `repositories.report_exports.save_report_export` (implementação e docstring lá)."""
    from repositories.report_exports import save_report_export as repository_save_report_export

    return repository_save_report_export(
        get_connection,
        report_kind,
        file_format,
        filename,
        media_type,
        generated_by,
        operator_name,
        operator_id,
        alert_id,
        alert_label,
        sector_id,
        score,
        max_score,
        source_type,
        audit_timestamp,
        file_size_bytes,
        metadata,
    )


def list_report_exports(
    limit: int = 100,
    report_kind: Optional[str] = None,
    file_format: Optional[str] = None,
    operator_name: Optional[str] = None,
) -> list[dict]:
    """Fachada: delega para `repositories.report_exports.list_report_exports` (implementação e docstring lá)."""
    from repositories.report_exports import list_report_exports as repository_list_report_exports

    return repository_list_report_exports(get_connection, limit, report_kind, file_format, operator_name)


def get_sectors():
    """Fachada: delega para `repositories.analytics.get_sectors` (implementação e docstring lá)."""
    from repositories.analytics import get_sectors as repository_get_sectors

    return repository_get_sectors(get_connection)


def get_technical_incidents(limit: int = 50, sector_id: str = None):
    """Fachada: delega para `repositories.analytics.get_technical_incidents` (implementação e docstring lá)."""
    from repositories.analytics import get_technical_incidents as repository_get_technical_incidents

    return repository_get_technical_incidents(limit, sector_id)


def get_all_configs() -> dict:
    """Fachada: delega para `repositories.configuration.get_all_configs` (implementação e docstring lá)."""
    from repositories.configuration import get_all_configs as repository_get_all_configs

    return repository_get_all_configs(get_connection)


def update_config(
    chave: str,
    valor: str,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
) -> bool:
    """Fachada: delega para `repositories.configuration.update_config` (implementação e docstring lá)."""
    from repositories.configuration import update_config as repository_update_config

    return repository_update_config(
        get_connection,
        chave,
        valor,
        alterado_por=alterado_por,
        motivo=motivo,
        origem=origem,
    )


def get_config_value(chave: str, default: str = "") -> str:
    """Fachada: delega para `repositories.configuration.get_config_value` (implementação e docstring lá)."""
    from repositories.configuration import get_config_value as repository_get_config_value

    return repository_get_config_value(get_connection, chave, default)


# Backward-compatible alias



# Backward-compatible alias







# Backward-compatible alias












def huawei_sync_log_exists(call_id: str) -> bool:
    """Idempotencia: ja sincronizamos essa ligacao Huawei antes (e com sucesso ou cota)?
    Ignora skips reversiveis para permitir retentativa se cota/regra/direcao mudarem.

    'discarded_recoverable' tambem e reversivel: o item foi descartado pela automacao
    mas pode voltar num proximo sync (alerta desconhecido/sem criterio pode mudar).
    'discarded_permanent' (tombstone) NAO esta na lista reversivel -> nunca rebaixa.
    """
    if not call_id:
        return False
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM huawei_sync_logs WHERE call_id = %s AND status NOT IN ('failed', 'skipped_quota', 'skipped_direction', 'discarded_recoverable') LIMIT 1",
            (str(call_id),),
        )
        return cursor.fetchone() is not None
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def huawei_sync_log_tombstone(
    cursor,
    call_id: str,
    *,
    permanent: bool,
    motivo: Optional[str] = None,
    loop_limit: int = 3,
) -> tuple[int, str]:
    """Marca um call_id como descartado em huawei_sync_logs, operando no cursor/transacao
    do chamador (nao abre conexao, nao commita — o descarte e atomico com a fila).

    permanent=True  -> status 'discarded_permanent' (tombstone definitivo; nunca rebaixa).
    permanent=False -> incrementa discard_attempts e mantem 'discarded_recoverable' (rebaixa
                       no proximo sync) ate atingir loop_limit, quando vira 'discarded_permanent'.

    Retorna (discard_attempts, status_final). Reusa a linha existente via ON CONFLICT, entao
    o contador sobrevive ao DELETE da fila.
    """
    if not call_id:
        return (0, "")
    if permanent:
        cursor.execute(
            """
            INSERT INTO huawei_sync_logs (call_id, status, failure_reason, discard_attempts)
            VALUES (%s, 'discarded_permanent', %s, 1)
            ON CONFLICT (call_id) DO UPDATE SET
                status = 'discarded_permanent',
                failure_reason = COALESCE(EXCLUDED.failure_reason, huawei_sync_logs.failure_reason),
                discard_attempts = huawei_sync_logs.discard_attempts + 1,
                sincronizado_em = CURRENT_TIMESTAMP
            RETURNING discard_attempts, status
            """,
            (str(call_id), motivo),
        )
    else:
        cursor.execute(
            """
            INSERT INTO huawei_sync_logs (call_id, status, failure_reason, discard_attempts)
            VALUES (%s, 'discarded_recoverable', %s, 1)
            ON CONFLICT (call_id) DO UPDATE SET
                discard_attempts = huawei_sync_logs.discard_attempts + 1,
                status = CASE
                    WHEN huawei_sync_logs.discard_attempts + 1 >= %s THEN 'discarded_permanent'
                    ELSE 'discarded_recoverable'
                END,
                failure_reason = COALESCE(EXCLUDED.failure_reason, huawei_sync_logs.failure_reason),
                sincronizado_em = CURRENT_TIMESTAMP
            RETURNING discard_attempts, status
            """,
            (str(call_id), motivo, int(loop_limit)),
        )
    row = cursor.fetchone()
    if row is None:
        return (0, "")

    def _val(key, idx):
        """Lê a coluna do RETURNING por nome ou índice (cursor pode devolver dict ou tupla)."""
        try:
            return row[key]
        except (TypeError, KeyError, IndexError):
            try:
                return row[idx]
            except (TypeError, KeyError, IndexError):
                return None

    try:
        return (int(_val("discard_attempts", 0) or 0), str(_val("status", 1) or ""))
    except (TypeError, ValueError):
        return (0, "")


def huawei_sync_log_discard_attempts(call_id: str) -> int:
    """Quantas vezes este call_id ja foi descartado pela automacao (read-only)."""
    if not call_id:
        return 0
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT discard_attempts FROM huawei_sync_logs WHERE call_id = %s",
            (str(call_id),),
        )
        row = cursor.fetchone()
        if not row:
            return 0
        try:
            return int(row["discard_attempts"] or 0)
        except (TypeError, KeyError, IndexError):
            return int(row[0] or 0)
    except Exception:
        return 0
    finally:
        if conn is not None:
            conn.close()



def huawei_sync_log_registrar(
    call_id: str,
    agent_id: Optional[str] = None,
    media_url: Optional[str] = None,
    status: str = 'success',
    failure_reason: Optional[str] = None,
    operator_name: Optional[str] = None,
    huawei_skill_id: Optional[str] = None,
) -> None:
    """Grava marcacao de sincronizacao. ON CONFLICT atualiza para promover failure para success.

    operator_name e huawei_skill_id sao opcionais e preservam contexto do
    operador reportado pela Huawei para diagnostico e rastreabilidade.
    Preserve valores existentes via COALESCE para nao apagar dados quando um registro for
    promovido (ex.: skip -> success em retry).
    Tombstone permanente e terminal: nenhuma redescoberta pode promover
    discarded_permanent para success/skipped/failed.
    """
    if not call_id:
        return
    agent_id = normalize_huawei_agent_id(agent_id) or None
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO huawei_sync_logs (
                call_id, agent_id, media_url, status, failure_reason,
                operator_name, huawei_skill_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (call_id) DO UPDATE SET
                status = EXCLUDED.status,
                failure_reason = EXCLUDED.failure_reason,
                media_url = COALESCE(EXCLUDED.media_url, huawei_sync_logs.media_url),
                operator_name = COALESCE(EXCLUDED.operator_name, huawei_sync_logs.operator_name),
                huawei_skill_id = COALESCE(EXCLUDED.huawei_skill_id, huawei_sync_logs.huawei_skill_id),
                sincronizado_em = CURRENT_TIMESTAMP
            WHERE huawei_sync_logs.status IS DISTINCT FROM 'discarded_permanent'
            """,
            (
                str(call_id), agent_id, media_url, status, failure_reason,
                operator_name, huawei_skill_id,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Falha ao registrar huawei_sync_log call=%s: %s", call_id, exc)
    finally:
        if conn is not None:
            conn.close()


def save_telefonia_sync_history(
    *,
    started_at: str,
    finished_at: Optional[str],
    status: str,
    horas_retroativas: int,
    baixadas: int,
    enfileiradas: int,
    erros_totais: int,
    mensagem_erro: Optional[str],
    trigger_type: str,
) -> int:
    """Fachada: delega para `repositories.telefonia.save_telefonia_sync_history` (implementação e docstring lá)."""
    from repositories.telefonia import save_telefonia_sync_history as repository_save_history

    return repository_save_history(
        get_connection,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        horas_retroativas=horas_retroativas,
        baixadas=baixadas,
        enfileiradas=enfileiradas,
        erros_totais=erros_totais,
        mensagem_erro=mensagem_erro,
        trigger_type=trigger_type,
    )


def list_telefonia_sync_history(limit: int = 50) -> list[dict]:
    """Fachada: delega para `repositories.telefonia.list_telefonia_sync_history` (implementação e docstring lá)."""
    from repositories.telefonia import list_telefonia_sync_history as repository_list_history

    return repository_list_history(get_connection, limit=limit)


def get_operator_audit_count_for_month_safe(
    operator_name: Optional[str],
    operator_id: Optional[str] = None,
) -> int:
    """Wrapper de `get_operator_audit_count_for_month` usando mes/ano atuais."""
    from datetime import datetime

    from repositories.audits import get_operator_audit_count_for_month as repository_count

    hoje = datetime.now()
    try:
        return repository_count(
            get_connection,
            operator_name=operator_name or "",
            year=hoje.year,
            month=hoje.month,
            operator_id=operator_id,
        )
    except Exception:
        return 0





# Backward-compatible alias



# Backward-compatible alias



# Backward-compatible alias



# Backward-compatible alias





# Backward-compatible alias



# Backward-compatible alias

def save_arquivo(
    tipo: str,
    conteudo: str,
    arquivo: str = "",
    audit_id: Optional[int] = None,
    operator_name: str = "",
    sector_id: str = "",
    alert_label: str = "",
    score: Optional[float] = None,
    metadata: Optional[dict] = None,
    criado_por: str = "",
    data_analise: Optional[str] = None,
) -> int:
    """Fachada: delega para `repositories.saved_files.save_arquivo` (implementação e docstring lá)."""
    from repositories.saved_files import save_arquivo as repository_save_arquivo

    return repository_save_arquivo(
        get_connection,
        tipo,
        conteudo,
        arquivo,
        audit_id,
        operator_name,
        sector_id,
        alert_label,
        score,
        metadata,
        criado_por,
        data_analise,
    )


def list_arquivos_salvos(
    limit: int = 100,
    offset: int = 0,
    tipo: Optional[str] = None,
    include_audits: bool = True,
) -> list[dict]:
    """Fachada: delega para `repositories.saved_files.list_arquivos_salvos` (implementação e docstring lá)."""
    from repositories.saved_files import list_arquivos_salvos as repository_list_arquivos_salvos

    return repository_list_arquivos_salvos(get_connection, limit, offset, tipo, include_audits)


def get_arquivo_salvo(arquivo_id: int) -> Optional[dict]:
    """Fachada: delega para `repositories.saved_files.get_arquivo_salvo` (implementação e docstring lá)."""
    from repositories.saved_files import get_arquivo_salvo as repository_get_arquivo_salvo

    return repository_get_arquivo_salvo(get_connection, arquivo_id)


def update_arquivo_salvo(arquivo_id: int, conteudo: str, score: float | None = None, metadata: dict | None = None) -> bool:
    """Fachada: delega para `repositories.saved_files.update_arquivo_salvo` (implementação e docstring lá)."""
    from repositories.saved_files import update_arquivo_salvo as repository_update_arquivo_salvo

    return repository_update_arquivo_salvo(get_connection, arquivo_id, conteudo, score=score, metadata=metadata)


def delete_arquivo_salvo(arquivo_id: int) -> bool:
    """Fachada: delega para `repositories.saved_files.delete_arquivo_salvo` (implementação e docstring lá)."""
    from repositories.saved_files import delete_arquivo_salvo as repository_delete_arquivo_salvo

    return repository_delete_arquivo_salvo(get_connection, arquivo_id)


def count_arquivos_salvos(tipo: Optional[str] = None, include_audits: bool = True) -> int:
    """Fachada: delega para `repositories.saved_files.count_arquivos_salvos` (implementação e docstring lá)."""
    from repositories.saved_files import count_arquivos_salvos as repository_count_arquivos_salvos

    return repository_count_arquivos_salvos(get_connection, tipo, include_audits)


def get_arquivo_by_audit_id(audit_id: int) -> Optional[dict]:
    """Fachada: delega para `repositories.saved_files.get_arquivo_by_audit_id` (implementação e docstring lá)."""
    from repositories.saved_files import get_arquivo_by_audit_id as repository_get_arquivo_by_audit_id

    return repository_get_arquivo_by_audit_id(get_connection, audit_id)


def update_arquivo_by_audit_id(
    audit_id: int,
    conteudo: str,
    score: Optional[float] = None,
    metadata: Optional[dict] = None,
    arquivo: Optional[str] = None,
    data_analise: Optional[str] = None,
    criado_por: Optional[str] = None,
) -> bool:
    """Fachada: delega para `repositories.saved_files.update_arquivo_by_audit_id` (implementação e docstring lá)."""
    from repositories.saved_files import update_arquivo_by_audit_id as repository_update_arquivo_by_audit_id

    return repository_update_arquivo_by_audit_id(get_connection, audit_id, conteudo, score, metadata, arquivo=arquivo, data_analise=data_analise, criado_por=criado_por)




def list_pending_dispatch_audits(older_than_hours: Optional[int] = None) -> list[dict]:
    """Fachada: delega para `repositories.audits.list_pending_dispatch_audits`."""
    from repositories.audits import list_pending_dispatch_audits as repo_list
    return repo_list(get_connection, older_than_hours)

def upsert_audit_draft(input_hash: str, user_id: str, details_json: str, transcription_json: str) -> None:
    """Fachada: delega para `repositories.audits.upsert_audit_draft`."""
    from repositories.audits import upsert_audit_draft as repo_upsert
    return repo_upsert(get_connection, input_hash, user_id, details_json, transcription_json)

def get_audit_draft(input_hash: str, user_id: str) -> Optional[dict]:
    """Fachada: delega para `repositories.audits.get_audit_draft`."""
    from repositories.audits import get_audit_draft as repo_get
    return repo_get(get_connection, input_hash, user_id)
