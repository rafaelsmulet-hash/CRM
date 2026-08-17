-- Schema do Jarvis: assistente PESSOAL de mesa para follow-up de operações
-- estruturadas com derivativos. 100% SQLite local, sem servidor.
--
-- IMPORTANTE (escopo): este banco é um ESPELHO read-only de dados extraídos
-- manualmente do CRM oficial da corretora. Ele NUNCA é fonte da verdade e
-- nenhuma linha aqui representa uma ação de negócio real. Por isso toda
-- tabela operacional carrega fonte_extracao/data_extracao, deixando
-- explícito que os dados vieram de uma extração manual, não de integração
-- ao vivo com o sistema oficial.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clientes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo                  TEXT NOT NULL UNIQUE,      -- identificador do cliente no CRM oficial (cliente_id do arquivo)
    nome                    TEXT NOT NULL,
    perfil_suitability      TEXT,
    data_criacao            TEXT NOT NULL DEFAULT (datetime('now')),
    data_ultima_atualizacao TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operacoes (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    operacao_ref                TEXT NOT NULL,     -- identificador da operação no CRM oficial (ou sintético, ver importer/validators.py)
    cliente_id                  INTEGER NOT NULL REFERENCES clientes(id),
    tipo_estrutura               TEXT NOT NULL,
    ativo_objeto                 TEXT NOT NULL,
    data_fechamento              TEXT NOT NULL,     -- ISO 8601 (YYYY-MM-DD)
    data_vencimento              TEXT NOT NULL,     -- ISO 8601 (YYYY-MM-DD)
    strike_1                     REAL,
    strike_2                     REAL,
    barreira                     REAL,
    status_barreira               TEXT,             -- valor mais recente (última extração)
    status_barreira_anterior      TEXT,             -- valor da extração anterior (usado para detectar mudança)
    valor_notional                REAL,
    parametros_json                TEXT,            -- payload bruto da linha de origem (auditoria completa)
    status                        TEXT NOT NULL DEFAULT 'ativa',   -- ativa | encerrada (encerrada = saiu da última extração)
    fonte_extracao                 TEXT NOT NULL,    -- nome do arquivo extraído do CRM oficial que originou/atualizou esta linha
    data_extracao                  TEXT NOT NULL,    -- timestamp da extração/importação que originou/atualizou esta linha
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
    mensagem_gerada   TEXT NOT NULL,     -- rascunho original gerado por template (nunca alterado, preservado para auditoria)
    mensagem_final    TEXT NOT NULL,     -- rascunho a ser exportado; começa igual a mensagem_gerada, pode ser editado em `jarvis revisar`
    status_revisao    TEXT NOT NULL DEFAULT 'pendente',  -- pendente | revisado | descartado | exportado
    data_revisao      TEXT               -- quando o status mudou pela última vez (revisado/descartado/exportado)
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
    detalhes             TEXT   -- JSON com {erros, avisos, diff: {novas, encerradas, mudancas_barreira}} — auditoria e base do "o que mudou desde ontem"
);

CREATE TABLE IF NOT EXISTS notas_pessoais (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id     INTEGER NOT NULL REFERENCES clientes(id),
    operacao_id    INTEGER REFERENCES operacoes(id),   -- nullable: nota pode ser sobre o cliente em geral, não uma operação específica
    texto          TEXT NOT NULL,
    data_criacao   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_operacoes_cliente   ON operacoes(cliente_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_status    ON operacoes(status);
CREATE INDEX IF NOT EXISTS idx_followups_operacao  ON follow_ups(operacao_id);
CREATE INDEX IF NOT EXISTS idx_followups_status    ON follow_ups(status_revisao);
CREATE INDEX IF NOT EXISTS idx_followups_regra     ON follow_ups(operacao_id, regra_disparada);
CREATE INDEX IF NOT EXISTS idx_notas_cliente        ON notas_pessoais(cliente_id);
CREATE INDEX IF NOT EXISTS idx_notas_operacao       ON notas_pessoais(operacao_id);
