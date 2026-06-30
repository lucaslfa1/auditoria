from datetime import datetime

from core.huawei.cobertura_operador import (
    calcular_dividas_cobertura,
    chave_operador_cobertura,
    cobertura_inicial_ativa,
    teto_por_cobertura,
)


def test_calcular_dividas_cobertura_usa_nome_e_matricula():
    operadores = [
        {"nome": "Operador A", "matricula": "MAT-A"},
        {"nome": "Operador B", "matricula": "MAT-B"},
    ]

    dividas = calcular_dividas_cobertura(
        operadores,
        {
            ("operador a", "mat-a"): 1,
            ("operador b", "mat-b"): 2,
        },
        minimo_por_operador=2,
    )

    assert chave_operador_cobertura(operadores[0]) == ("operador a", "mat-a")
    assert dividas[("operador a", "mat-a")] == 1
    assert dividas[("operador b", "mat-b")] == 0


def test_cobertura_inicial_ativa_respeita_janela_e_mantem_foco_com_divida():
    assert cobertura_inicial_ativa(
        datetime(2026, 6, 3, 12, 0, 0),
        dias_iniciais=3,
        minimo_por_operador=2,
        divida_total=0,
    )
    assert cobertura_inicial_ativa(
        datetime(2026, 6, 4, 12, 0, 0),
        dias_iniciais=3,
        minimo_por_operador=2,
        divida_total=1,
    )
    assert not cobertura_inicial_ativa(
        datetime(2026, 6, 4, 12, 0, 0),
        dias_iniciais=3,
        minimo_por_operador=2,
        divida_total=0,
    )
    assert not cobertura_inicial_ativa(
        datetime(2026, 6, 1, 12, 0, 0),
        dias_iniciais=0,
        minimo_por_operador=2,
        divida_total=1,
    )


def test_teto_por_cobertura_limita_operador_abaixo_e_preserva_coberto():
    assert teto_por_cobertura(10, 2) == 2
    assert teto_por_cobertura(0, 2) == 2
    assert teto_por_cobertura(10, 0) == 10
    assert teto_por_cobertura(0, 0) == 0
