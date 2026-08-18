# Jarvis — Monitoramento de Estruturas de Derivativos

Sistema interno para a mesa de Sales Trading acompanhar automaticamente
estruturas de derivativos de clientes: status, distância/atingimento de
barreiras, fixings, vencimentos, alertas e panorama mensal para o cliente.

**Princípio central:** o sistema monitora tudo — o Sales Trader só recebe o
que exige atenção, na área **"🚨 Atenção hoje"** do dashboard.

Esta é a segunda geração do projeto. A primeira (Jarvis CLI: offline,
single-user, importação manual de CSV) foi descontinuada — decisão
registrada e não revertida. Este README documenta só o sistema atual.

## O que este sistema é (e não é)

- **Fonte de verdade do cadastro e do preço: o Orbit**, o sistema da área de
  derivativos. Jarvis não inventa dado de operação — ele importa
  diariamente o arquivo exportado do Orbit (cadastro + preço do ativo, num
  arquivo só) e monitora a partir daí. Cadastro manual existe só para
  exceções fora do Orbit.
- **Motor roda no fechamento (EOD), sem observação intradiária.** "Barreira
  atingida" = o fechamento do dia anterior ficou do lado errado do nível.
- **Nenhuma mensagem sai para cliente sem aprovação humana.** O panorama
  mensal é sempre um rascunho — aprovar/editar/rejeitar é manual, e o envio
  em si continua fora do Jarvis, pelo canal oficial da corretora.
- **Dado real de cliente nunca deve ser compartilhado fora do seu
  ambiente** — nem em chat, nem em ferramenta externa. O mapeamento de
  colunas do Orbit (`config/column_mapping.ini`) é calibrado por você,
  localmente, com o arquivo real em mãos.

## Stack

FastAPI + PostgreSQL + SQLAlchemy/Alembic + Jinja2/HTMX (server-rendered,
sem build JS). Ver a proposta de arquitetura original para o raciocínio
completo por trás dessas escolhas.

## Rodando com Docker (recomendado para uso real)

```bash
cp .env.example .env
# edite .env: gere uma SECRET_KEY própria
#   python -c "import secrets; print(secrets.token_hex(32))"

docker compose up -d --build
docker compose exec app python scripts/seed_admin.py voce@corretora.com "Seu Nome" "senha-temporaria"
```

Acesse `http://localhost:8000`, faça login e troque a senha no primeiro
acesso (ainda não há tela de troca de senha — via banco por enquanto, ver
`app/security.py:hash_senha`).

## Rodando localmente para desenvolvimento

Requer Python 3.11+ e um Postgres acessível (local ou container).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

cp .env.example .env  # ajuste DATABASE_URL se necessário

# banco (ajuste usuário/senha/host conforme seu Postgres local)
createdb jarvis
createdb jarvis_test   # usado pelos testes

.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_admin.py voce@local.dev "Seu Nome" "senha-dev"

.venv/bin/uvicorn app.main:app --reload
```

## Testes

```bash
.venv/bin/pytest
```

Cobre: regras puras (barreira/fixing/vencimento), parsing e validação do
arquivo do Orbit (estrutural vs. linha a linha), upsert/diff do importador,
autenticação, e um fluxo de integração completo via HTTP (importar → motor
→ dashboard → panorama → aprovação → auditoria). Roda contra um Postgres
real (`jarvis_test`), não SQLite — o schema usa ENUM e JSONB nativos.

## Importação do Orbit

O Orbit não tem API — a entrada é sempre um arquivo exportado (`.xlsx` ou
`.csv`), importado em **Importação Orbit** no menu. `config/column_mapping.ini`
mapeia cada campo interno para o nome real da coluna no seu arquivo — **os
nomes hoje configurados são um ponto de partida assumido** (padrão comum em
planilhas de estruturas), não confirmados com uma amostra real do Orbit.
Ajuste esse `.ini` no seu ambiente antes da primeira importação real, sem
precisar mexer em código.

Campos obrigatórios: `cliente_nome`, `operacao_ref`, `tipo_estrutura`,
`ativo_principal`, `data_inicio`, `data_vencimento`. Opcionais:
`cliente_codigo`, `notional`, `moeda`, `valor_entrada`, `barreira_1_nivel`,
`barreira_1_tipo`, `barreira_1_regra_observacao`, `fixing_1_data`,
`fixing_1_tipo`, `preco_ativo`, `preco_data`.

- **Erro estrutural** (arquivo vazio, sem cabeçalho, coluna obrigatória
  ausente do mapeamento): a importação inteira é abortada, nada é gravado.
- **Erro numa linha** (campo obrigatório vazio/inválido): só aquela linha é
  descartada; o resto do arquivo é importado normalmente, com o motivo
  listado na tela.
- **Upsert por `operacao_ref`.** Estrutura de origem Orbit que estava ativa
  e não aparece mais no arquivo é encerrada automaticamente. Estruturas
  cadastradas manualmente (exceção) nunca são encerradas por um import —
  estão fora do alcance do Orbit por definição.
- O motor (avaliação de barreira/fixing/vencimento) roda automaticamente
  logo após cada importação bem-sucedida. Para reprocessar sem reimportar:
  `python scripts/run_motor.py [YYYY-MM-DD]`.

## Modelo de dados

Ver `app/models/__init__.py` (comentado) para o schema completo. Resumo:
`clientes`, `estruturas` (parâmetros específicos por tipo em
`parametros_especificos` JSONB — estruturas não presumem ter as mesmas
regras), `barreiras`, `fixings`, `precos_mercado`, `eventos` (linha do
tempo), `alertas` (com dedupe por `chave_dedupe`), `importacoes_orbit`
(relatório de diff de cada import), `log_execucoes_motor`,
`panoramas_mensais`, `audit_log` (quem alterou o quê, quando, de/para).

## Papéis (RBAC)

`sales_trader`, `gestor`, `compliance` (acesso à auditoria, somente
leitura), `admin`. Login local (Argon2 + JWT em cookie httpOnly) nesta
fase — sem SSO corporativo ainda (decisão registrada: revisitar antes de
produção com dados reais).

## Fora do escopo desta primeira entrega (deliberado)

- Integração automática com provedor de dados de mercado (fonte é sempre o
  arquivo do Orbit nesta fase).
- Monitoramento intradiário de barreira contínua (motor é EOD).
- Alertas por Telegram/e-mail (hoje só no dashboard).
- SSO corporativo.
- Módulo de saída antecipada (o Orbit não traz valuation de estrutura, só
  preço do ativo — mecanismo de entrada desse valor ainda não foi
  definido).
- Painel de exposição consolidada por cliente/ativo.

## Auditoria

Toda mutação de `clientes`/`estruturas` — seja pelo importador do Orbit,
seja por cadastro manual — passa por `app/services/auditoria.py` e fica em
`audit_log`, consultável (somente leitura, papéis `compliance`/`admin`) em
**Auditoria** no menu.
