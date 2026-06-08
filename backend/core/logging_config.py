import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
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
