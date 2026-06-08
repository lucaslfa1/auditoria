from typing import Any


from db.domain_constants import (
    AUDIT_SCOPES,
    AUDIT_STATUS_AWAITING_PAIR,
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    AUDIT_STATUS_PENDING_APPROVAL,
    AUDIT_STATUSES,
    DEFAULT_AUDIT_SCOPE,
    DEFAULT_REVIEW_QUEUE_STATUS,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_USER_ROLE,
    LEGACY_AUDIT_STATUS_CONTESTED,
    LEGACY_AUDIT_STATUS_FALLBACK,
    REVIEW_QUEUE_PRIORITIES,
    REVIEW_QUEUE_STATUSES,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY,
    SOURCE_TYPES,
    USER_ROLES,
)
from db.schema_tools import set_schema_metadata


MIGRATION_NAME = "20260308_004_domain_invariants"


def _sql_text_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_trigger(cursor: Any, name: str, sql: str) -> None:
    cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
    cursor.execute(sql)


def _create_users_triggers(cursor: Any) -> None:
    valid_roles = _sql_text_list(USER_ROLES)
    for action in ("INSERT", "UPDATE"):
        _replace_trigger(
            cursor,
            f"users_guard_{action.lower()}",
            f"""
            CREATE TRIGGER users_guard_{action.lower()}
            BEFORE {action} ON users
            FOR EACH ROW
            BEGIN
                SELECT CASE
                    WHEN NEW.username IS NULL OR TRIM(NEW.username) = ''
                    THEN RAISE(ABORT, 'users.username_required')
                END;
                SELECT CASE
                    WHEN NEW.username != LOWER(TRIM(NEW.username))
                    THEN RAISE(ABORT, 'users.username_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.role IS NULL OR TRIM(NEW.role) = ''
                    THEN RAISE(ABORT, 'users.role_required')
                END;
                SELECT CASE
                    WHEN NEW.role != LOWER(TRIM(NEW.role))
                    THEN RAISE(ABORT, 'users.role_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.role NOT IN ({valid_roles})
                    THEN RAISE(ABORT, 'users.role_invalid')
                END;
            END
            """,
        )


def _create_audits_triggers(cursor: Any) -> None:
    valid_statuses = _sql_text_list(AUDIT_STATUSES)
    valid_source_types = _sql_text_list(SOURCE_TYPES)
    valid_scopes = _sql_text_list(AUDIT_SCOPES)
    for action in ("INSERT", "UPDATE"):
        _replace_trigger(
            cursor,
            f"audits_guard_{action.lower()}",
            f"""
            CREATE TRIGGER audits_guard_{action.lower()}
            BEFORE {action} ON audits
            FOR EACH ROW
            BEGIN
                SELECT CASE
                    WHEN NEW.source_type IS NULL OR TRIM(NEW.source_type) = ''
                    THEN RAISE(ABORT, 'audits.source_type_required')
                END;
                SELECT CASE
                    WHEN NEW.source_type != LOWER(TRIM(NEW.source_type))
                    THEN RAISE(ABORT, 'audits.source_type_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.source_type NOT IN ({valid_source_types})
                    THEN RAISE(ABORT, 'audits.source_type_invalid')
                END;
                SELECT CASE
                    WHEN NEW.audit_scope IS NULL OR TRIM(NEW.audit_scope) = ''
                    THEN RAISE(ABORT, 'audits.audit_scope_required')
                END;
                SELECT CASE
                    WHEN NEW.audit_scope != LOWER(TRIM(NEW.audit_scope))
                    THEN RAISE(ABORT, 'audits.audit_scope_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.audit_scope NOT IN ({valid_scopes})
                    THEN RAISE(ABORT, 'audits.audit_scope_invalid')
                END;
                SELECT CASE
                    WHEN NEW.status IS NULL OR TRIM(NEW.status) = ''
                    THEN RAISE(ABORT, 'audits.status_required')
                END;
                SELECT CASE
                    WHEN NEW.status != LOWER(TRIM(NEW.status))
                    THEN RAISE(ABORT, 'audits.status_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.status NOT IN ({valid_statuses})
                    THEN RAISE(ABORT, 'audits.status_invalid')
                END;
                SELECT CASE
                    WHEN NEW.status = '{AUDIT_STATUS_CONTESTATION_PENDING_REVIEW}'
                         AND TRIM(COALESCE(NEW.contestation_reason, '')) = ''
                    THEN RAISE(ABORT, 'audits.contestation_reason_required')
                END;
                SELECT CASE
                    WHEN NEW.status IN ('{AUDIT_STATUS_AWAITING_PAIR}', '{AUDIT_STATUS_PENDING_APPROVAL}')
                         AND TRIM(COALESCE(NEW.contestation_reason, '')) != ''
                    THEN RAISE(ABORT, 'audits.contestation_reason_not_allowed_for_open_queue')
                END;
            END
            """,
        )


def _create_review_queue_triggers(cursor: Any) -> None:
    valid_statuses = _sql_text_list(REVIEW_QUEUE_STATUSES)
    valid_priorities = _sql_text_list(REVIEW_QUEUE_PRIORITIES)
    for action in ("INSERT", "UPDATE"):
        _replace_trigger(
            cursor,
            f"review_queue_guard_{action.lower()}",
            f"""
            CREATE TRIGGER review_queue_guard_{action.lower()}
            BEFORE {action} ON fila_revisao_classificacao
            FOR EACH ROW
            BEGIN
                SELECT CASE
                    WHEN NEW.input_hash IS NULL OR TRIM(NEW.input_hash) = ''
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.input_hash_required')
                END;
                SELECT CASE
                    WHEN NEW.nome_arquivo IS NULL OR TRIM(NEW.nome_arquivo) = ''
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.nome_arquivo_required')
                END;
                SELECT CASE
                    WHEN NEW.status IS NULL OR TRIM(NEW.status) = ''
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.status_required')
                END;
                SELECT CASE
                    WHEN NEW.status != LOWER(TRIM(NEW.status))
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.status_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.status NOT IN ({valid_statuses})
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.status_invalid')
                END;
                SELECT CASE
                    WHEN NEW.prioridade IS NULL OR TRIM(NEW.prioridade) = ''
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.prioridade_required')
                END;
                SELECT CASE
                    WHEN NEW.prioridade != LOWER(TRIM(NEW.prioridade))
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.prioridade_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.prioridade NOT IN ({valid_priorities})
                    THEN RAISE(ABORT, 'fila_revisao_classificacao.prioridade_invalid')
                END;
            END
            """,
        )


def _create_report_exports_triggers(cursor: Any) -> None:
    valid_source_types = _sql_text_list(SOURCE_TYPES)
    for action in ("INSERT", "UPDATE"):
        _replace_trigger(
            cursor,
            f"report_exports_guard_{action.lower()}",
            f"""
            CREATE TRIGGER report_exports_guard_{action.lower()}
            BEFORE {action} ON report_exports
            FOR EACH ROW
            BEGIN
                SELECT CASE
                    WHEN NEW.report_kind IS NULL OR TRIM(NEW.report_kind) = ''
                    THEN RAISE(ABORT, 'report_exports.report_kind_required')
                END;
                SELECT CASE
                    WHEN NEW.report_kind != LOWER(TRIM(NEW.report_kind))
                    THEN RAISE(ABORT, 'report_exports.report_kind_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.file_format IS NULL OR TRIM(NEW.file_format) = ''
                    THEN RAISE(ABORT, 'report_exports.file_format_required')
                END;
                SELECT CASE
                    WHEN NEW.file_format != LOWER(TRIM(NEW.file_format))
                    THEN RAISE(ABORT, 'report_exports.file_format_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.source_type IS NOT NULL AND TRIM(NEW.source_type) = ''
                    THEN RAISE(ABORT, 'report_exports.source_type_blank_not_allowed')
                END;
                SELECT CASE
                    WHEN NEW.source_type IS NOT NULL
                         AND TRIM(NEW.source_type) != ''
                         AND NEW.source_type != LOWER(TRIM(NEW.source_type))
                    THEN RAISE(ABORT, 'report_exports.source_type_must_be_lowercase_trimmed')
                END;
                SELECT CASE
                    WHEN NEW.source_type IS NOT NULL
                         AND TRIM(NEW.source_type) != ''
                         AND NEW.source_type NOT IN ({valid_source_types})
                    THEN RAISE(ABORT, 'report_exports.source_type_invalid')
                END;
            END
            """,
        )


def apply(cursor: Any) -> None:
    cursor.execute(
        f"""
        UPDATE users
        SET username = LOWER(TRIM(username)),
            role = CASE
                WHEN LOWER(TRIM(COALESCE(role, ''))) IN ({_sql_text_list(USER_ROLES)})
                THEN LOWER(TRIM(role))
                ELSE '{DEFAULT_USER_ROLE}'
            END,
            supervisor_name = TRIM(COALESCE(supervisor_name, ''))
        WHERE username IS NOT NULL
        """
    )

    cursor.execute(
        f"""
        UPDATE audits
        SET sector_id = CASE
                WHEN sector_id IS NULL OR TRIM(sector_id) = '' THEN NULL
                ELSE LOWER(TRIM(sector_id))
            END,
            source_type = CASE
                WHEN LOWER(TRIM(COALESCE(source_type, ''))) IN ({_sql_text_list(SOURCE_TYPES)})
                THEN LOWER(TRIM(source_type))
                ELSE '{DEFAULT_SOURCE_TYPE}'
            END,
            audit_scope = CASE
                WHEN LOWER(TRIM(COALESCE(audit_scope, ''))) IN ({_sql_text_list(AUDIT_SCOPES)})
                THEN LOWER(TRIM(audit_scope))
                ELSE '{DEFAULT_AUDIT_SCOPE}'
            END,
            status = CASE
                WHEN LOWER(TRIM(COALESCE(status, ''))) IN ({_sql_text_list(AUDIT_STATUSES)})
                THEN LOWER(TRIM(status))
                WHEN LOWER(TRIM(COALESCE(status, ''))) = '{LEGACY_AUDIT_STATUS_CONTESTED}'
                THEN '{AUDIT_STATUS_CONTESTATION_PENDING_REVIEW}'
                WHEN TRIM(COALESCE(contestation_reason, '')) != ''
                THEN '{AUDIT_STATUS_CONTESTATION_PENDING_REVIEW}'
                ELSE '{LEGACY_AUDIT_STATUS_FALLBACK}'
            END
        """
    )
    cursor.execute(
        f"""
        UPDATE audits
        SET contestation_reason = CASE
            WHEN status = '{AUDIT_STATUS_CONTESTATION_PENDING_REVIEW}'
                 AND TRIM(COALESCE(contestation_reason, '')) != ''
            THEN TRIM(contestation_reason)
            WHEN status = '{AUDIT_STATUS_CONTESTATION_PENDING_REVIEW}'
            THEN 'Contestacao registrada sem motivo historico.'
            WHEN status NOT IN ('{AUDIT_STATUS_AWAITING_PAIR}', '{AUDIT_STATUS_PENDING_APPROVAL}')
                 AND TRIM(COALESCE(contestation_reason, '')) != ''
            THEN TRIM(contestation_reason)
            ELSE NULL
        END
        """
    )

    cursor.execute(
        f"""
        UPDATE fila_revisao_classificacao
        SET input_hash = TRIM(input_hash),
            nome_arquivo = TRIM(nome_arquivo),
            setor_previsto = CASE
                WHEN setor_previsto IS NULL OR TRIM(setor_previsto) = '' THEN NULL
                ELSE LOWER(TRIM(setor_previsto))
            END,
            prioridade = CASE
                WHEN LOWER(TRIM(COALESCE(prioridade, ''))) IN ({_sql_text_list(REVIEW_QUEUE_PRIORITIES)})
                THEN LOWER(TRIM(prioridade))
                ELSE '{REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY}'
            END,
            status = CASE
                WHEN LOWER(TRIM(COALESCE(status, ''))) IN ({_sql_text_list(REVIEW_QUEUE_STATUSES)})
                THEN LOWER(TRIM(status))
                WHEN LOWER(TRIM(COALESCE(status, ''))) = 'classificado'
                THEN '{REVIEW_QUEUE_STATUS_AUTO_RESOLVED}'
                WHEN LOWER(TRIM(COALESCE(status, ''))) = 'auditado'
                THEN '{REVIEW_QUEUE_STATUS_AUDITED}'
                WHEN LOWER(TRIM(COALESCE(status, ''))) = 'ignorado'
                THEN '{REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}'
                ELSE '{DEFAULT_REVIEW_QUEUE_STATUS}'
            END
        """
    )

    cursor.execute(
        f"""
        UPDATE report_exports
        SET report_kind = COALESCE(NULLIF(LOWER(TRIM(report_kind)), ''), 'unknown'),
            file_format = COALESCE(NULLIF(LOWER(TRIM(file_format)), ''), 'unknown'),
            source_type = CASE
                WHEN source_type IS NULL OR TRIM(source_type) = '' THEN NULL
                WHEN LOWER(TRIM(source_type)) IN ({_sql_text_list(SOURCE_TYPES)})
                THEN LOWER(TRIM(source_type))
                ELSE NULL
            END
        """
    )

    # SQLite triggers use RAISE(ABORT,...) syntax incompatible with PostgreSQL.
    # In PG mode, data validation is handled by the application layer.
    if False:
        _create_users_triggers(cursor)
        _create_audits_triggers(cursor)
        _create_review_queue_triggers(cursor)
        _create_report_exports_triggers(cursor)

    set_schema_metadata(cursor, "schema.source_of_truth", "migrations")
    set_schema_metadata(cursor, "schema.domain_invariants", MIGRATION_NAME)
