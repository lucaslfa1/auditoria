"""Filtro de duracao das chamadas Huawei antes do download.

Este modulo existe para deixar explicita uma regra operacional simples que
antes ficava perdida dentro do loop grande de `core.huawei_sync`:

- chamada com duracao conhecida MENOR que o minimo configurado nao entra no lote;
- chamada com duracao conhecida MAIOR que o maximo configurado tambem nao entra,
  quando existir maximo (> 0);
- chamada sem duracao confiavel NAO e descartada por este filtro. Ela segue para
  as proximas etapas e incrementa `sem_duracao_consideradas`, porque a Huawei
  pode entregar manifesto incompleto e ainda assim o audio ser valido.

O valor minimo atual vem de `DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS` ou das
configs runtime `HUAWEI_SYNC_MIN_DURATION_SECONDS`,
`huawei_sync_min_duration_seconds` e `huawei_d1_min_duration_seconds`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.automation_rules import get_call_duration_seconds
from core.huawei.download_candidates import _call_duration_is_known


@dataclass(frozen=True)
class ResultadoFiltroDuracao:
    """Resultado auditavel da avaliacao de duracao de uma chamada.

    `contador` e o nome exato do contador usado pelo sync e pela UI. Quando ele
    vier preenchido, quem chamou deve incrementar o contador correspondente.
    `descartar` indica se a chamada deve parar antes do download.
    """

    descartar: bool
    contador: Optional[str]
    duracao_segundos: int
    duracao_conhecida: bool
    minimo_segundos: int
    maximo_segundos: int


def avaliar_filtro_duracao(
    interacao: dict,
    *,
    minimo_segundos: int,
    maximo_segundos: int,
) -> ResultadoFiltroDuracao:
    """Decide se uma interacao Huawei deve ser filtrada por duracao.

    Regra de borda importante para implantacao: o minimo e inclusivo. Com
    `minimo_segundos=110`, uma ligacao de 109s e descartada, mas 110s passa.
    """

    minimo_segundos = max(0, int(minimo_segundos or 0))
    maximo_segundos = max(0, int(maximo_segundos or 0))
    duracao_conhecida = _call_duration_is_known(interacao)
    duracao_segundos = get_call_duration_seconds(interacao)

    if not duracao_conhecida:
        return ResultadoFiltroDuracao(
            descartar=False,
            contador="sem_duracao_consideradas",
            duracao_segundos=duracao_segundos,
            duracao_conhecida=False,
            minimo_segundos=minimo_segundos,
            maximo_segundos=maximo_segundos,
        )

    if duracao_segundos < minimo_segundos:
        return ResultadoFiltroDuracao(
            descartar=True,
            contador="ignoradas_duracao_minima",
            duracao_segundos=duracao_segundos,
            duracao_conhecida=True,
            minimo_segundos=minimo_segundos,
            maximo_segundos=maximo_segundos,
        )

    if maximo_segundos > 0 and duracao_segundos > maximo_segundos:
        return ResultadoFiltroDuracao(
            descartar=True,
            contador="ignoradas_duracao_maxima",
            duracao_segundos=duracao_segundos,
            duracao_conhecida=True,
            minimo_segundos=minimo_segundos,
            maximo_segundos=maximo_segundos,
        )

    return ResultadoFiltroDuracao(
        descartar=False,
        contador=None,
        duracao_segundos=duracao_segundos,
        duracao_conhecida=True,
        minimo_segundos=minimo_segundos,
        maximo_segundos=maximo_segundos,
    )


def aplicar_filtro_duracao(
    contadores: dict,
    interacao: dict,
    *,
    minimo_segundos: int,
    maximo_segundos: int,
) -> bool:
    """Aplica a regra e atualiza os contadores operacionais do sync.

    Retorna True quando a chamada deve ser descartada antes do download. Retorna
    False quando ela deve continuar no funil de selecao.
    """

    resultado = avaliar_filtro_duracao(
        interacao,
        minimo_segundos=minimo_segundos,
        maximo_segundos=maximo_segundos,
    )
    if resultado.contador:
        contadores.setdefault(resultado.contador, 0)
        contadores[resultado.contador] += 1
    return resultado.descartar
