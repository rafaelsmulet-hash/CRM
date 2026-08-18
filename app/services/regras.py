"""Regras de negócio como funções puras e testáveis — sem acesso a banco.

Herda a ideia mais valiosa do Jarvis CLI: cada regra é uma função isolada,
fácil de testar sem precisar de infraestrutura. `app/services/motor.py` é
quem orquestra essas funções sobre os dados reais do banco.
"""
import dataclasses
import datetime

from app.models import StatusBarreira, StatusFixing


@dataclasses.dataclass(frozen=True)
class ResultadoBarreira:
    status_novo: StatusBarreira
    distancia_pct: float


def calcular_distancia_pct(preco: float, nivel: float) -> float:
    """Distância percentual entre o preço e o nível da barreira.

    Sempre positiva quando o preço ainda não cruzou a barreira; usada tanto
    para barreiras de queda quanto de alta — só o sinal do cruzamento muda.
    """
    if nivel == 0:
        return 0.0
    return round(abs(preco - nivel) / nivel * 100, 4)


def avaliar_barreira(
    *, preco_fechamento_anterior: float, nivel: float, direcao: str, proxima_pct_limiar: float
) -> ResultadoBarreira:
    """Avalia uma barreira EOD: compara o fechamento do dia anterior com o nível.

    direcao="queda": atingida quando o preço fecha em nível ou abaixo.
    direcao="alta":  atingida quando o preço fecha em nível ou acima.
    Sem observação intradiária nesta fase (decisão registrada na arquitetura).
    """
    distancia_pct = calcular_distancia_pct(preco_fechamento_anterior, nivel)

    if direcao == "queda":
        atingida = preco_fechamento_anterior <= nivel
    elif direcao == "alta":
        atingida = preco_fechamento_anterior >= nivel
    else:
        raise ValueError(f"direção de barreira desconhecida: {direcao!r}")

    if atingida:
        status = StatusBarreira.atingida
    elif distancia_pct <= proxima_pct_limiar:
        status = StatusBarreira.proxima
    else:
        status = StatusBarreira.normal

    return ResultadoBarreira(status_novo=status, distancia_pct=distancia_pct)


def dias_ate(data_alvo: datetime.date, data_referencia: datetime.date) -> int:
    return (data_alvo - data_referencia).days


def fixing_deve_alertar(
    *, dias_restantes: int, limiares_dias_antes: list[int], status: StatusFixing
) -> bool:
    """Alerta uma única vez por limiar cruzado — mesmo espírito de dedupe do Jarvis CLI.

    A dedupe real (não repetir o mesmo alerta) é responsabilidade da camada
    que grava eventos/alertas (chave única por estrutura+tipo+limiar+data),
    não desta função — ela só decide se o limiar de hoje é relevante.
    """
    if status != StatusFixing.pendente:
        return False
    return dias_restantes in limiares_dias_antes


def vencimento_deve_alertar(*, dias_restantes: int, limiares_dias_antes: list[int]) -> bool:
    return dias_restantes >= 0 and dias_restantes in limiares_dias_antes
