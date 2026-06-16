"""Configuração de logging estruturado (JSON) do backend.

Papel no fluxo: define um formatter que emite cada log como uma linha JSON
(time/level/name/message + exceção quando houver) e uma função de setup que
instala esse formatter no root logger e alinha os loggers do Uvicorn/FastAPI.
Usado no boot da aplicação para padronizar logs em produção.

Sem custo de API (só configuração de logging em memória/stdout).
"""
import logging
import json

class JsonFormatter(logging.Formatter):
    """Formatter de logging que serializa cada registro como uma linha JSON.

    Emite as chaves `time`, `level`, `name` e `message`; quando o registro tem
    `exc_info`, adiciona `exc_info` com o traceback formatado.
    """
    def format(self, record):
        """Serializa o `LogRecord` em uma string JSON (uma linha por log)."""
        log_record = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_logging():
    """Instala o `JsonFormatter` no logging da aplicação.

    Limpa os handlers do root logger, adiciona um `StreamHandler` com o
    `JsonFormatter` e fixa o nível em INFO. Em seguida, reaponta os loggers já
    existentes do Uvicorn/FastAPI para o mesmo handler e desliga a propagação
    deles (evita logs duplicados). Efeito colateral: muda a configuração global
    de logging do processo. Sem retorno.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    
    # Configura o root logger
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
    
    # Também atualiza loggers do Uvicorn e FastAPI se eles já existirem
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith("uvicorn") or logger_name.startswith("fastapi"):
            logger = logging.getLogger(logger_name)
            logger.handlers.clear()
            logger.addHandler(handler)
            logger.propagate = False
