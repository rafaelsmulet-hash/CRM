import datetime

import pytest

from app.models import StatusBarreira, StatusFixing
from app.services.regras import (
    avaliar_barreira,
    calcular_distancia_pct,
    dias_ate,
    fixing_deve_alertar,
    vencimento_deve_alertar,
)


def test_calcular_distancia_pct():
    assert calcular_distancia_pct(33.20, 32.50) == pytest.approx(2.1538, abs=1e-3)
    assert calcular_distancia_pct(32.50, 32.50) == 0.0


def test_barreira_queda_normal_quando_longe():
    r = avaliar_barreira(preco_fechamento_anterior=40.0, nivel=32.50, direcao="queda", proxima_pct_limiar=5.0)
    assert r.status_novo == StatusBarreira.normal


def test_barreira_queda_proxima_dentro_do_limiar():
    r = avaliar_barreira(preco_fechamento_anterior=33.20, nivel=32.50, direcao="queda", proxima_pct_limiar=5.0)
    assert r.status_novo == StatusBarreira.proxima
    assert r.distancia_pct == pytest.approx(2.1538, abs=1e-3)


def test_barreira_queda_atingida_quando_preco_fecha_no_nivel_ou_abaixo():
    assert avaliar_barreira(
        preco_fechamento_anterior=32.50, nivel=32.50, direcao="queda", proxima_pct_limiar=5.0
    ).status_novo == StatusBarreira.atingida
    assert avaliar_barreira(
        preco_fechamento_anterior=30.00, nivel=32.50, direcao="queda", proxima_pct_limiar=5.0
    ).status_novo == StatusBarreira.atingida


def test_barreira_alta_atingida_quando_preco_fecha_no_nivel_ou_acima():
    assert avaliar_barreira(
        preco_fechamento_anterior=70.00, nivel=70.00, direcao="alta", proxima_pct_limiar=5.0
    ).status_novo == StatusBarreira.atingida
    assert avaliar_barreira(
        preco_fechamento_anterior=75.00, nivel=70.00, direcao="alta", proxima_pct_limiar=5.0
    ).status_novo == StatusBarreira.atingida


def test_barreira_alta_normal_quando_preco_abaixo():
    r = avaliar_barreira(preco_fechamento_anterior=50.00, nivel=70.00, direcao="alta", proxima_pct_limiar=5.0)
    assert r.status_novo == StatusBarreira.normal


def test_barreira_direcao_invalida_levanta_erro():
    with pytest.raises(ValueError):
        avaliar_barreira(preco_fechamento_anterior=1, nivel=1, direcao="lateral", proxima_pct_limiar=5.0)


def test_dias_ate():
    assert dias_ate(datetime.date(2026, 8, 25), datetime.date(2026, 8, 18)) == 7
    assert dias_ate(datetime.date(2026, 8, 10), datetime.date(2026, 8, 18)) == -8


@pytest.mark.parametrize("dias_restantes,esperado", [(5, True), (2, True), (1, True), (0, True), (3, False), (-1, False)])
def test_fixing_deve_alertar_respeita_limiares(dias_restantes, esperado):
    resultado = fixing_deve_alertar(
        dias_restantes=dias_restantes, limiares_dias_antes=[5, 2, 1, 0], status=StatusFixing.pendente
    )
    assert resultado is esperado


def test_fixing_ja_observado_nunca_alerta():
    assert fixing_deve_alertar(dias_restantes=1, limiares_dias_antes=[1], status=StatusFixing.observado) is False


def test_vencimento_deve_alertar():
    assert vencimento_deve_alertar(dias_restantes=15, limiares_dias_antes=[30, 15, 5]) is True
    assert vencimento_deve_alertar(dias_restantes=20, limiares_dias_antes=[30, 15, 5]) is False
    assert vencimento_deve_alertar(dias_restantes=-1, limiares_dias_antes=[30, 15, 5]) is False
