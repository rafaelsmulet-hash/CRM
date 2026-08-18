"""Modelos SQLAlchemy — ver arquitetura aprovada (seção 3) para o desenho completo.

Um módulo só, deliberadamente: são ~13 tabelas pequenas e fortemente
relacionadas: navegar entre vários arquivos custaria mais do que ajudaria
neste tamanho de projeto.
"""
import datetime
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Papel(str, enum.Enum):
    sales_trader = "sales_trader"
    gestor = "gestor"
    compliance = "compliance"
    admin = "admin"


class StatusEstrutura(str, enum.Enum):
    ativa = "ativa"
    encerrada = "encerrada"
    cancelada = "cancelada"


class StatusBarreira(str, enum.Enum):
    normal = "normal"
    proxima = "proxima"
    atingida = "atingida"


class StatusFixing(str, enum.Enum):
    pendente = "pendente"
    observado = "observado"
    nao_aplica = "nao_aplica"


class Severidade(str, enum.Enum):
    info = "info"
    atencao = "atencao"
    critico = "critico"


class StatusAprovacaoPanorama(str, enum.Enum):
    rascunho = "rascunho"
    aprovado = "aprovado"
    rejeitado = "rejeitado"


class AcaoAuditoria(str, enum.Enum):
    insert = "insert"
    update = "update"
    delete = "delete"


def agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(200))
    papel: Mapped[Papel] = mapped_column(Enum(Papel, name="papel"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_orbit: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    suitability: Mapped[str | None] = mapped_column(String(50))
    sales_trader_responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    atualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    estruturas: Mapped[list["Estrutura"]] = relationship(back_populates="cliente")


class Estrutura(Base):
    __tablename__ = "estruturas"
    __table_args__ = (UniqueConstraint("operacao_ref", name="uq_estrutura_operacao_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    operacao_ref: Mapped[str] = mapped_column(String(100), index=True)
    tipo_estrutura: Mapped[str] = mapped_column(String(100), index=True)
    ativo_principal: Mapped[str] = mapped_column(String(50))
    notional: Mapped[float | None] = mapped_column(Numeric(18, 2))
    moeda: Mapped[str] = mapped_column(String(10), default="BRL")
    data_inicio: Mapped[datetime.date | None] = mapped_column(Date)
    data_vencimento: Mapped[datetime.date | None] = mapped_column(Date, index=True)
    valor_entrada: Mapped[float | None] = mapped_column(Numeric(18, 4))
    status: Mapped[StatusEstrutura] = mapped_column(
        Enum(StatusEstrutura, name="status_estrutura"), default=StatusEstrutura.ativa, index=True
    )
    parametros_especificos: Mapped[dict] = mapped_column(JSON, default=dict)
    fonte_importacao: Mapped[str] = mapped_column(String(20), default="manual")
    data_importacao: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    atualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    cliente: Mapped[Cliente] = relationship(back_populates="estruturas")
    barreiras: Mapped[list["Barreira"]] = relationship(
        back_populates="estrutura", cascade="all, delete-orphan"
    )
    fixings: Mapped[list["Fixing"]] = relationship(
        back_populates="estrutura", cascade="all, delete-orphan"
    )
    eventos: Mapped[list["Evento"]] = relationship(
        back_populates="estrutura", cascade="all, delete-orphan", order_by="Evento.data_hora.desc()"
    )


class Barreira(Base):
    __tablename__ = "barreiras"

    id: Mapped[int] = mapped_column(primary_key=True)
    estrutura_id: Mapped[int] = mapped_column(ForeignKey("estruturas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(50))
    nivel: Mapped[float] = mapped_column(Numeric(18, 6))
    # "queda": atingida quando o preço cai para nível ou abaixo (ex.: proteção, knock-in de baixa)
    # "alta": atingida quando o preço sobe para nível ou acima (ex.: autocall, knock-out de alta)
    direcao: Mapped[str] = mapped_column(String(10), default="queda")
    regra_observacao: Mapped[str] = mapped_column(String(30), default="fechamento")
    ativo_referencia: Mapped[str] = mapped_column(String(50))
    status_atual: Mapped[StatusBarreira] = mapped_column(
        Enum(StatusBarreira, name="status_barreira"), default=StatusBarreira.normal
    )
    status_anterior: Mapped[StatusBarreira | None] = mapped_column(
        Enum(StatusBarreira, name="status_barreira")
    )
    atualizado_em: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    estrutura: Mapped[Estrutura] = relationship(back_populates="barreiras")


class Fixing(Base):
    __tablename__ = "fixings"

    id: Mapped[int] = mapped_column(primary_key=True)
    estrutura_id: Mapped[int] = mapped_column(ForeignKey("estruturas.id"), index=True)
    data_fixing: Mapped[datetime.date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(50), default="cupom")
    regra: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[StatusFixing] = mapped_column(
        Enum(StatusFixing, name="status_fixing"), default=StatusFixing.pendente
    )
    resultado_observado: Mapped[str | None] = mapped_column(String(200))

    estrutura: Mapped[Estrutura] = relationship(back_populates="fixings")


class PrecoMercado(Base):
    __tablename__ = "precos_mercado"
    __table_args__ = (UniqueConstraint("ticker", "data", name="uq_preco_ticker_data"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(50), index=True)
    data: Mapped[datetime.date] = mapped_column(Date, index=True)
    preco: Mapped[float] = mapped_column(Numeric(18, 6))
    fonte: Mapped[str] = mapped_column(String(30), default="orbit")
    hora_captura: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Evento(Base):
    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    estrutura_id: Mapped[int] = mapped_column(ForeignKey("estruturas.id"), index=True)
    tipo_evento: Mapped[str] = mapped_column(String(50), index=True)
    data_hora: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    preco_referencia: Mapped[float | None] = mapped_column(Numeric(18, 6))
    fonte: Mapped[str] = mapped_column(String(30), default="orbit")
    regra_utilizada: Mapped[str] = mapped_column(String(200))
    status_anterior: Mapped[str | None] = mapped_column(String(50))
    status_novo: Mapped[str | None] = mapped_column(String(50))
    detalhes: Mapped[dict] = mapped_column(JSON, default=dict)

    estrutura: Mapped[Estrutura] = relationship(back_populates="eventos")


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(primary_key=True)
    estrutura_id: Mapped[int | None] = mapped_column(ForeignKey("estruturas.id"), index=True)
    evento_id: Mapped[int | None] = mapped_column(ForeignKey("eventos.id"))
    tipo: Mapped[str] = mapped_column(String(50), index=True)
    severidade: Mapped[Severidade] = mapped_column(Enum(Severidade, name="severidade_alerta"))
    mensagem: Mapped[str] = mapped_column(Text)
    chave_dedupe: Mapped[str] = mapped_column(String(300), index=True)
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    lido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    lido_em: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    resolvido: Mapped[bool] = mapped_column(Boolean, default=False)

    estrutura: Mapped[Estrutura | None] = relationship()


class ImportacaoOrbit(Base):
    __tablename__ = "importacoes_orbit"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    arquivo: Mapped[str] = mapped_column(String(300))
    linhas_processadas: Mapped[int] = mapped_column(default=0)
    novas: Mapped[int] = mapped_column(default=0)
    atualizadas: Mapped[int] = mapped_column(default=0)
    encerradas: Mapped[int] = mapped_column(default=0)
    erros: Mapped[list] = mapped_column(JSON, default=list)
    importado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))


class LogExecucaoMotor(Base):
    __tablename__ = "log_execucoes_motor"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_execucao: Mapped[datetime.date] = mapped_column(Date, index=True)
    inicio: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    fim: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    estruturas_processadas: Mapped[int] = mapped_column(default=0)
    eventos_gerados: Mapped[int] = mapped_column(default=0)
    erros: Mapped[list] = mapped_column(JSON, default=list)


class PanoramaMensal(Base):
    __tablename__ = "panoramas_mensais"
    __table_args__ = (
        UniqueConstraint("estrutura_id", "competencia", name="uq_panorama_estrutura_competencia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    estrutura_id: Mapped[int] = mapped_column(ForeignKey("estruturas.id"), index=True)
    competencia: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    conteudo_gerado: Mapped[str] = mapped_column(Text)
    conteudo_final: Mapped[str | None] = mapped_column(Text)
    status_aprovacao: Mapped[StatusAprovacaoPanorama] = mapped_column(
        Enum(StatusAprovacaoPanorama, name="status_aprovacao_panorama"),
        default=StatusAprovacaoPanorama.rascunho,
        index=True,
    )
    aprovado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    aprovado_em: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    cliente: Mapped[Cliente] = relationship()
    estrutura: Mapped[Estrutura] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    tabela: Mapped[str] = mapped_column(String(100), index=True)
    registro_id: Mapped[int] = mapped_column(index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    data_hora: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    campo: Mapped[str] = mapped_column(String(100))
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_novo: Mapped[str | None] = mapped_column(Text)
    acao: Mapped[AcaoAuditoria] = mapped_column(Enum(AcaoAuditoria, name="acao_auditoria"))
