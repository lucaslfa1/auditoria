"""Teto de downloads por operador dentro de um ciclo Huawei.

Esta regra NAO e a cota mensal de envio ao supervisor.

Historico importante para quem for manter:
- `huawei_cota_max_por_operador_mes` governa compliance/relatorio do supervisor.
- `huawei_download_max_por_operador_ciclo` governa quantas gravacoes do mesmo
  operador entram no lote de download de UM ciclo da automacao.
- O contador legado `ignoradas_cota_mensal_pre_download` continua com esse nome
  porque telas e relatorios ja consomem a chave. No comportamento atual, ele
  representa cortes do teto por operador antes do download.

Este modulo e propositalmente puro: nao acessa banco, rede nem filesystem. O
orquestrador (`core.huawei_sync`) chama estas funcoes e, quando necessario,
persiste o skip em `huawei_sync_logs`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CONTADOR_TETO_OPERADOR = "ignoradas_cota_mensal_pre_download"
STATUS_LOG_TETO_OPERADOR = "skipped_quota"
MOTIVO_LOG_TETO_OPERADOR = "teto_download_por_operador_ciclo"

ChaveOperador = tuple[str, str]


@dataclass(frozen=True)
class ResultadoTetoOperador:
    """Resultado auditavel da avaliacao do teto por operador."""

    descartar: bool
    chave_operador: ChaveOperador
    contador: Optional[str]
    status_log: Optional[str]
    motivo_log: Optional[str]
    agent_id: Optional[str]
    downloads_atuais: int
    teto_por_operador: int


def chave_operador_download(operador: dict) -> ChaveOperador:
    """Chave usada para contar downloads do mesmo operador no ciclo atual.

    Usamos nome + id para manter compatibilidade com o comportamento antigo do
    sync. O id preferencial e `id_telefonia`, caindo para `id_huawei`.
    """

    nome = str(operador.get("nome") or operador.get("name") or "").strip().lower()
    operador_id = str(
        operador.get("id_telefonia") or operador.get("id_huawei") or ""
    ).strip().lower()
    return nome, operador_id


def avaliar_teto_operador(
    downloads_por_operador: dict[ChaveOperador, int],
    operador: dict,
    *,
    teto_por_operador: int,
) -> ResultadoTetoOperador:
    """Decide se o operador ja atingiu o teto de download do ciclo.

    Regra de implantacao:
    - `teto_por_operador == 0` significa ilimitado;
    - operador sem nome/id resolvido nao e bloqueado por este teto;
    - o contador e fresco por ciclo, sem olhar historico mensal.
    """

    teto_por_operador = max(0, int(teto_por_operador or 0))
    chave = chave_operador_download(operador)
    nome_norm, operador_id_norm = chave
    downloads_atuais = int(downloads_por_operador.get(chave, 0) or 0)
    tem_identidade = bool(nome_norm or operador_id_norm)
    excedeu_teto = (
        teto_por_operador > 0
        and tem_identidade
        and downloads_atuais >= teto_por_operador
    )

    if not excedeu_teto:
        return ResultadoTetoOperador(
            descartar=False,
            chave_operador=chave,
            contador=None,
            status_log=None,
            motivo_log=None,
            agent_id=operador_id_norm or None,
            downloads_atuais=downloads_atuais,
            teto_por_operador=teto_por_operador,
        )

    return ResultadoTetoOperador(
        descartar=True,
        chave_operador=chave,
        contador=CONTADOR_TETO_OPERADOR,
        status_log=STATUS_LOG_TETO_OPERADOR,
        motivo_log=MOTIVO_LOG_TETO_OPERADOR,
        agent_id=operador_id_norm or None,
        downloads_atuais=downloads_atuais,
        teto_por_operador=teto_por_operador,
    )


def aplicar_teto_operador(
    contadores: dict,
    downloads_por_operador: dict[ChaveOperador, int],
    operador: dict,
    *,
    teto_por_operador: int,
) -> ResultadoTetoOperador:
    """Avalia o teto e atualiza contador de descarte quando houver bloqueio."""

    resultado = avaliar_teto_operador(
        downloads_por_operador,
        operador,
        teto_por_operador=teto_por_operador,
    )
    if resultado.contador:
        contadores.setdefault(resultado.contador, 0)
        contadores[resultado.contador] += 1
    return resultado


def registrar_download_operador(
    downloads_por_operador: dict[ChaveOperador, int],
    resultado: ResultadoTetoOperador,
) -> None:
    """Conta um download aceito para que os proximos candidatos respeitem o teto."""

    chave = resultado.chave_operador
    downloads_por_operador[chave] = int(downloads_por_operador.get(chave, 0) or 0) + 1
