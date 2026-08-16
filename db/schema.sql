-- Schema do sistema local de follow-up de operações estruturadas com derivativos.
-- 100% SQLite local (arquivo .db), sem servidor, sem dependências externas.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clientes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo                  TEXT NOT NULL UNIQUE,      -- identificador do cliente no sistema de origem (cliente_id do arquivo)
    nome                    TEXT NOT NULL,
    perfil_suitability      TEXT,
    data_criacao            TEXT NOT NULL DEFAULT (datetime('now')),
    data_ultima_atualizacao TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operacoes (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_ref                TEXT NOT NULL,     -- identificador da operação no sistema de origem (ou sintético, ver importer/validators.py)
    cliente_id                  INTEGER NOT NULL REFERENCES clientes(id),
    tipo_estrutura               TEXT NOT NULL,
    ativo_objeto                 TEXT NOT NULL,
    data_fechamento              TEXT NOT NULL,     -- ISO 8601 (YYYY-MM-DD)
    data_vencimento              TEXT NOT NULL,     -- ISO 8601 (YYYY-MM-DD)
    strike_1                     REAL,
    strike_2                     REAL,
    barreira                     REAL,
    status_barreira               TEXT,             -- valor mais recente (última importação)
    status_barreira_anterior      TEXT,             -- valor anterior à última importação (usado pela regra de evento)
    valor_notional                REAL,
    parametros_json                TEXT,            -- payload bruto da linha de origem (auditoria completa)
    status                        TEXT NOT NULL DEFAULT 'ativa',   -- ativa | encerrada
    data_criacao                  TEXT NOT NULL DEFAULT (datetime('now')),
    data_ultima_atualizacao        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (cliente_id, operacao_ref)
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_id       INTEGER NOT NULL REFERENCES operacoes(id),
    data_gerado       TEXT NOT NULL DEFAULT (datetime('now')),
    regra_disparada   TEXT NOT NULL,     -- ex: tempo_decorrido_3m | vencimento_15d | evento_barreira_tocada
    motivo_disparo    TEXT NOT NULL,     -- descrição legível do motivo (auditoria)
    mensagem_gerada   TEXT NOT NULL,     -- texto pronto, gerado por template (nunca enviado automaticamente)
    status_revisao    TEXT NOT NULL DEFAULT 'pendente',  -- pendente | revisado | enviado
    usuario_revisor   TEXT,
    data_revisao      TEXT
);

CREATE TABLE IF NOT EXISTS log_importacoes (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    data                 TEXT NOT NULL DEFAULT (datetime('now')),
    arquivo              TEXT NOT NULL,
    linhas_processadas   INTEGER NOT NULL DEFAULT 0,
    novas                INTEGER NOT NULL DEFAULT 0,
    atualizadas          INTEGER NOT NULL DEFAULT 0,
    encerradas           INTEGER NOT NULL DEFAULT 0,
    erros                INTEGER NOT NULL DEFAULT 0,
    detalhes_erros       TEXT   -- JSON com lista de {linha, motivo} para auditoria
);

CREATE INDEX IF NOT EXISTS idx_operacoes_cliente   ON operacoes(cliente_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_status    ON operacoes(status);
CREATE INDEX IF NOT EXISTS idx_followups_operacao  ON follow_ups(operacao_id);
CREATE INDEX IF NOT EXISTS idx_followups_status    ON follow_ups(status_revisao);
CREATE INDEX IF NOT EXISTS idx_followups_regra     ON follow_ups(operacao_id, regra_disparada);
