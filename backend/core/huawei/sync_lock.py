"""Lock de execução do sync Huawei (table lock cooperativo em `configuracoes`).

Garante uma única execução de `executar_sync_huawei` por vez via a chave
`sync_lock` na tabela `configuracoes` (libera locks travados há +30 min).
Extraído de `core.huawei_sync`, que reexporta `_HuaweiSyncExecutionLock` p/
compat (callers + `patch.object(huawei_sync._HuaweiSyncExecutionLock, ...)`).

Sem imports de topo: `db.database` e `logging` são importados lazy dentro dos
métodos (igual ao original) para não acoplar o boot.
"""


class _HuaweiSyncExecutionLock:
    def __init__(self) -> None:
        self._conn = None
        self.acquired = False

    def acquire(self) -> bool:
        import db.database as database
        self._conn = database.get_connection()
        try:
            cursor = self._conn.cursor()
            
            # Limpa locks travados ha mais de 30 mins
            cursor.execute("""
                UPDATE configuracoes 
                SET valor = 'false' 
                WHERE chave = 'sync_lock' 
                AND valor = 'true' 
                AND atualizado_em::timestamp < NOW() - INTERVAL '30 minutes'
            """)
            
            # Tenta adquirir
            cursor.execute("""
                INSERT INTO configuracoes (chave, valor, atualizado_em) 
                VALUES ('sync_lock', 'true', NOW()::text)
                ON CONFLICT (chave) DO UPDATE 
                SET valor = 'true', atualizado_em = NOW()::text
                WHERE configuracoes.valor = 'false' OR configuracoes.valor IS NULL
                RETURNING valor
            """)
            row = cursor.fetchone()
            self._conn.commit()
            
            if row:
                self.acquired = True
                return True
            return False
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Falha ao adquirir table lock do sync Huawei: {exc}")
            if self._conn:
                self._conn.rollback()
            return False

    def release(self) -> None:
        if self._conn is None:
            return
        try:
            if self.acquired:
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE configuracoes SET valor = 'false', atualizado_em = NOW() WHERE chave = 'sync_lock'"
                )
                self._conn.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"Falha ao liberar table lock do sync Huawei: {exc}")
        finally:
            self.acquired = False
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
