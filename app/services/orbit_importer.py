"""Upsert de cliente/estrutura/barreira/fixing/preço a partir do arquivo do Orbit.

Chave natural = operacao_ref (mesmo princípio do upsert por
(cliente_id, operacao_ref) do Jarvis CLI). Estrutura ativa de origem Orbit
que não aparece mais no arquivo é encerrada automaticamente — estruturas de
origem manual nunca são encerradas por um import, porque estão fora do
alcance do Orbit por definição.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import carregar_column_mapping
from app.models import (
    AcaoAuditoria,
    Barreira,
    Cliente,
    Estrutura,
    Evento,
    Fixing,
    ImportacaoOrbit,
    PrecoMercado,
    StatusBarreira,
    StatusEstrutura,
    StatusFixing,
)
from app.services import auditoria
from app.services.orbit_parsing import ErroEstrutural, ler_linhas_brutas, mapear_e_validar

DIRECOES_ALTA = {"ko", "knock-out", "knockout", "autocall", "cupom_alta"}


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _upsert_cliente(db: Session, dados: dict) -> Cliente:
    codigo = dados.get("cliente_codigo")
    cliente = None
    if codigo:
        cliente = db.scalar(select(Cliente).where(Cliente.codigo_orbit == codigo))
    if cliente is None and not codigo:
        cliente = db.scalar(
            select(Cliente).where(Cliente.nome == dados["cliente_nome"], Cliente.codigo_orbit.is_(None))
        )
    if cliente is None:
        cliente = Cliente(codigo_orbit=codigo, nome=dados["cliente_nome"])
        db.add(cliente)
        db.flush()
    elif cliente.nome != dados["cliente_nome"]:
        cliente.nome = dados["cliente_nome"]
    return cliente


def _upsert_estrutura(db: Session, cliente: Cliente, dados: dict, usuario_id: int) -> tuple[Estrutura, bool]:
    estrutura = db.scalar(select(Estrutura).where(Estrutura.operacao_ref == dados["operacao_ref"]))
    valores_novos = {
        "tipo_estrutura": dados["tipo_estrutura"],
        "ativo_principal": dados["ativo_principal"].upper(),
        "notional": dados.get("notional"),
        "moeda": dados.get("moeda") or "BRL",
        "data_inicio": dados["data_inicio"],
        "data_vencimento": dados["data_vencimento"],
        "valor_entrada": dados.get("valor_entrada"),
    }

    if estrutura is None:
        estrutura = Estrutura(
            cliente_id=cliente.id,
            operacao_ref=dados["operacao_ref"],
            status=StatusEstrutura.ativa,
            fonte_importacao="orbit",
            data_importacao=_agora(),
            criado_por_id=usuario_id,
            atualizado_por_id=usuario_id,
            **valores_novos,
        )
        db.add(estrutura)
        db.flush()
        auditoria.registrar_criacao(
            db,
            tabela="estruturas",
            registro_id=estrutura.id,
            usuario_id=usuario_id,
            campos={"operacao_ref": estrutura.operacao_ref, "fonte": "orbit", **valores_novos},
        )
        return estrutura, True

    anteriores = {campo: getattr(estrutura, campo) for campo in valores_novos}
    for campo, valor in valores_novos.items():
        setattr(estrutura, campo, valor)
    estrutura.status = StatusEstrutura.ativa
    estrutura.fonte_importacao = "orbit"
    estrutura.data_importacao = _agora()
    estrutura.atualizado_por_id = usuario_id
    auditoria.registrar_alteracoes(
        db,
        tabela="estruturas",
        registro_id=estrutura.id,
        usuario_id=usuario_id,
        valores_anteriores=anteriores,
        valores_novos=valores_novos,
    )
    return estrutura, False


def _upsert_barreira(db: Session, estrutura: Estrutura, dados: dict) -> None:
    if dados.get("barreira_1_nivel") is None:
        return
    tipo = dados.get("barreira_1_tipo") or "protecao"
    direcao = "alta" if tipo.strip().lower() in DIRECOES_ALTA else "queda"
    regra = dados.get("barreira_1_regra_observacao") or "fechamento"

    barreira = db.scalar(select(Barreira).where(Barreira.estrutura_id == estrutura.id))
    if barreira is None:
        db.add(
            Barreira(
                estrutura_id=estrutura.id,
                tipo=tipo,
                nivel=dados["barreira_1_nivel"],
                direcao=direcao,
                regra_observacao=regra,
                ativo_referencia=estrutura.ativo_principal,
                status_atual=StatusBarreira.normal,
            )
        )
    else:
        barreira.tipo = tipo
        barreira.nivel = dados["barreira_1_nivel"]
        barreira.direcao = direcao
        barreira.regra_observacao = regra
        barreira.ativo_referencia = estrutura.ativo_principal


def _upsert_fixing(db: Session, estrutura: Estrutura, dados: dict) -> None:
    if dados.get("fixing_1_data") is None:
        return
    existente = db.scalar(
        select(Fixing).where(
            Fixing.estrutura_id == estrutura.id, Fixing.data_fixing == dados["fixing_1_data"]
        )
    )
    if existente is None:
        db.add(
            Fixing(
                estrutura_id=estrutura.id,
                data_fixing=dados["fixing_1_data"],
                tipo=dados.get("fixing_1_tipo") or "cupom",
                status=StatusFixing.pendente,
            )
        )


def _upsert_preco(db: Session, ticker: str, dados: dict, data_padrao: datetime.date) -> None:
    if dados.get("preco_ativo") is None:
        return
    data = dados.get("preco_data") or data_padrao
    registro = db.scalar(
        select(PrecoMercado).where(PrecoMercado.ticker == ticker, PrecoMercado.data == data)
    )
    if registro is None:
        db.add(PrecoMercado(ticker=ticker, data=data, preco=dados["preco_ativo"], fonte="orbit"))
    else:
        registro.preco = dados["preco_ativo"]
        registro.hora_captura = _agora()


def _encerrar_ausentes(
    db: Session, operacoes_no_arquivo: set[str], usuario_id: int, agora_dt: datetime.datetime
) -> int:
    ativas_de_orbit = db.scalars(
        select(Estrutura).where(
            Estrutura.status == StatusEstrutura.ativa, Estrutura.fonte_importacao == "orbit"
        )
    ).all()
    total = 0
    for estrutura in ativas_de_orbit:
        if estrutura.operacao_ref in operacoes_no_arquivo:
            continue
        anterior = estrutura.status
        estrutura.status = StatusEstrutura.encerrada
        auditoria.registrar(
            db,
            tabela="estruturas",
            registro_id=estrutura.id,
            usuario_id=usuario_id,
            campo="status",
            valor_anterior=anterior.value,
            valor_novo=estrutura.status.value,
            acao=AcaoAuditoria.update,
        )
        db.add(
            Evento(
                estrutura_id=estrutura.id,
                tipo_evento="estrutura_encerrada",
                data_hora=agora_dt,
                fonte="orbit",
                regra_utilizada="operação ausente na importação do Orbit",
                status_anterior=anterior.value,
                status_novo=estrutura.status.value,
            )
        )
        total += 1
    return total


def importar(db: Session, *, conteudo: bytes, nome_arquivo: str, usuario_id: int) -> ImportacaoOrbit:
    """Ponto de entrada único do importador. Levanta ErroEstrutural sem gravar nada."""
    mapeamento = carregar_column_mapping()
    linhas_brutas = ler_linhas_brutas(conteudo, nome_arquivo)
    resultado = mapear_e_validar(
        linhas_brutas, mapeamento["colunas"], mapeamento["formato_data"], mapeamento["separador_decimal"]
    )

    agora_dt = _agora()
    hoje = agora_dt.date()
    novas = 0
    atualizadas = 0
    operacoes_no_arquivo: set[str] = set()
    erros = [{"linha": e.numero_linha, "motivo": e.motivo} for e in resultado.erros]

    for linha in resultado.linhas:
        try:
            cliente = _upsert_cliente(db, linha.dados)
            estrutura, criada = _upsert_estrutura(db, cliente, linha.dados, usuario_id)
            _upsert_barreira(db, estrutura, linha.dados)
            _upsert_fixing(db, estrutura, linha.dados)
            _upsert_preco(db, estrutura.ativo_principal, linha.dados, hoje)
            operacoes_no_arquivo.add(estrutura.operacao_ref)
            novas += int(criada)
            atualizadas += int(not criada)
        except Exception as exc:  # noqa: BLE001 — uma linha ruim não pode abortar as outras
            erros.append({"linha": linha.numero_linha, "motivo": f"erro ao gravar: {exc}"})

    encerradas = _encerrar_ausentes(db, operacoes_no_arquivo, usuario_id, agora_dt)

    importacao = ImportacaoOrbit(
        data=agora_dt,
        arquivo=nome_arquivo,
        linhas_processadas=len(linhas_brutas),
        novas=novas,
        atualizadas=atualizadas,
        encerradas=encerradas,
        erros=erros,
        importado_por_id=usuario_id,
    )
    db.add(importacao)
    db.flush()
    return importacao


__all__ = ["importar", "ErroEstrutural"]
