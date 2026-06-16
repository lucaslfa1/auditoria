"""Lock de execução do sync Huawei (table lock cooperativo em `configuracoes`).

Garante uma única execução de `executar_sync_huawei` por vez via a chave
`sync_lock` na tabela `configuracoes` (libera locks travados há +30 min).
Extraído de `core.huawei_sync`, que reexporta `_HuaweiSyncExecutionLock` p/
compat (callers + `patch.object(huawei_sync._HuaweiSyncExecutionLock, ...)`).

Sem imports de topo: `db.database` e `logging` são importados lazy dentro dos
métodos (igual ao original) para não acoplar o boot.
"""


class _HuaweiSyncExecutionLock:
    """Lock cooperativo (singleton lógico) que serializa o sync Huawei.

    Usa a linha `chave='sync_lock'` da tabela `configuracoes` como mutex
    distribuído: enquanto `valor='true'` nenhuma outra instância consegue
    adquirir o lock. Não é um lock de banco nativo (advisory/row lock); é um
    flag persistido, então mantém a sua própria conexão aberta entre
    `acquire()` e `release()`. Sem custo de API (só acesso a banco).
    """

    def __init__(self) -> None:
        self._conn = None
        self.acquired = False

    def acquire(self) -> bool:
        """Tenta adquirir o lock; devolve True se conseguiu, False caso contrário.

        Efeitos colaterais (banco): abre uma conexão (guardada em `self._conn`),
        primeiro libera locks presos há mais de 30 minutos (UPDATE de
        `sync_lock` para 'false') e então faz um INSERT ... ON CONFLICT que só
        marca 'true' quando o valor atual é 'false'/NULL. Em sucesso seta
        `self.acquired=True` e mantém a conexão aberta para o `release()`. Em
        erro faz rollback, loga e retorna False (a conexão pode ficar pendente
        e ser fechada por GC). Não levanta exceção.
        """
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
        """Libera o lock e fecha a conexão. Idempotente / seguro chamar sempre.

        Efeitos colaterais (banco): se o lock foi de fato adquirido, marca
        `sync_lock='false'` e faz commit; ao final sempre zera `self.acquired`
        e fecha a conexão (`self._conn=None`). Engole exceções (só loga
        warning) para nunca quebrar o `finally` do chamador. No-op se nenhuma
        conexão estiver aberta.
        """
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
