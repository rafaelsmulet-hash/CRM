# Jarvis — Assistente pessoal de mesa para follow-up de derivativos

Ferramenta **pessoal** de produtividade para um Sales Trader que precisa
identificar, todo dia, quais operações estruturadas com derivativos
(capital protegido, autocall, dual currency etc.) merecem um follow-up com
o cliente — e preparar um **rascunho de mensagem** pronto para revisão
manual.

## Escopo (leia antes de tudo)

- **Jarvis é read-only em relação à operação.** Ele só reflete dados
  extraídos manualmente do CRM oficial da corretora. **Nunca é fonte da
  verdade.** Toda linha das tabelas operacionais carrega `fonte_extracao`
  (nome do arquivo) e `data_extracao` (timestamp), deixando explícito que é
  um espelho, não o dado original.
- **Nenhuma ação de negócio real acontece aqui.** O Jarvis não fecha
  operação, não registra contato oficial, não envia nada sozinho.
- **Mensagens geradas são RASCUNHOS pessoais.** O registro formal de
  contato com o cliente continua no sistema homologado da corretora.
- **Usuário único.** Sem autenticação, sem permissões multiusuário —
  é uma ferramenta pessoal de mesa, não um sistema compartilhado.
- **100% offline, zero dependências de terceiros.** Nenhuma chamada de
  rede, API externa, telemetria, ou biblioteca de terceiros — nem mesmo
  para instalar (ver seção abaixo). Nenhum LLM (local ou externo) gera
  texto: tudo por templates parametrizados, para saída previsível e
  auditável.

Se alguma vez você pedir uma funcionalidade que pareça fechar essa fronteira
read-only (por exemplo, "marcar como contatado no CRM" ou "enviar
automaticamente"), o Jarvis deve recusar/perguntar antes de implementar —
essa é uma regra de escopo inegociável do projeto.

## Zero dependências, zero rede — inclusive na instalação

Este projeto usa **exclusivamente a biblioteca padrão do Python 3.11+**
(`sqlite3`, `csv`, `configparser`, `hashlib`, `unicodedata`, `datetime`,
`pathlib`, `argparse`, `shutil`, `json`, `subprocess`, `tempfile`). Não há
`pandas` nem qualquer outra biblioteca de terceiros — mesmo que a stack
sugerida originalmente mencionasse `pandas`, mantive a base 100% biblioteca
padrão porque o ambiente de uso não pode acessar nenhum servidor externo,
nem mesmo para um `pip install` inicial.

Copie a pasta do projeto para a máquina onde vai usar e confirme que o
Python está disponível:

```bash
python3 --version   # precisa ser 3.11 ou superior
```

Pronto — nada mais a instalar.

## Estrutura de pastas

```
CRM/
├── README.md
├── requirements.txt              # documenta a ausência de dependências
├── jarvis / jarvis.cmd            # wrappers para rodar `./jarvis <comando>`
├── settings.py                    # carregamento centralizado de config (.ini)
├── config/
│   ├── settings.ini               # caminhos: banco, inbox, backups
│   ├── column_mapping.ini         # mapeamento de colunas do arquivo de origem -> campos internos
│   └── rules_config.ini           # limiares das regras + parâmetros do painel `hoje`
├── db/
│   ├── schema.sql                  # schema SQLite completo
│   ├── database.py                 # conexão + inicialização do banco
│   └── queries.py                  # consultas/escritas usadas pela CLI
├── importer/
│   ├── file_reader.py              # leitura de .csv (erros estruturais de arquivo)
│   ├── validators.py               # validação/parsing linha a linha (erros de dados)
│   └── import_run.py               # upsert + fechamento de operações + relatório de diff
├── rules/
│   ├── rules_definitions.py        # funções puras das regras (100% testáveis)
│   └── engine.py                   # aplica as regras sobre o banco, evita duplicidade
├── templates/
│   ├── mensagens/                  # 1 arquivo .txt por tipo_estrutura (editável sem tocar em código)
│   └── message_generator.py        # renderiza template com os dados da operação
├── cli/
│   ├── main.py                      # `jarvis importar/hoje/revisar/exportar/briefing/nota/...`
│   └── html_export.py               # painel visual estático (`jarvis hoje --html`)
├── tests/                           # testes automatizados (unittest da stdlib)
├── data/
│   ├── inbox/                       # onde você coloca a extração manual do CRM oficial
│   └── processed/                   # (opcional) extrações já importadas, para arquivo histórico
└── backups/                         # cópias do .db com timestamp (ver `jarvis backup-db`)
```

`crm_derivativos.db` é criado na raiz na primeira execução e **nunca é
versionado** (está no `.gitignore`, junto com `data/inbox`/`data/processed`,
pois podem conter dados de clientes).

## Uso diário

```bash
# 1. Uma única vez: cria o banco e as tabelas
./jarvis init-db

# 2. Todo dia: importa a extração manual do CRM oficial + roda o motor de regras
./jarvis importar --arquivo data/inbox/extracao_2026-08-17.csv
# imprime também um relatório do que mudou desde a extração anterior:
# operações novas, que sumiram (provavelmente encerradas), mudanças de status de barreira

# 3. Painel do dia (texto no terminal)
./jarvis hoje

# 3b. Ou um painel visual em HTML, para abrir no navegador (sem servidor, sem rede)
./jarvis hoje --html painel.html
# ou os mesmos dados em JSON, para quem quiser automatizar depois
./jarvis hoje --json painel.json

# 4. Revisa os rascunhos pendentes um a um (aprovar / editar / descartar)
./jarvis revisar

# 5. Exporta os rascunhos já aprovados, prontos para copiar/colar onde for enviar de fato
./jarvis exportar --saida rascunhos_2026-08-17.csv

# 6. Resumo rápido de um cliente
./jarvis briefing --cliente 1001

# 7. Nota pessoal (só sua) sobre um cliente ou operação
./jarvis nota --cliente 1001 --texto "Ligou perguntando sobre o autocall."
./jarvis nota --cliente 1001 --operacao OPX1 --texto "Quer aumentar notional na renovação."

# 8. Backup do banco (rode sempre depois da importação diária)
./jarvis backup-db
```

(`./jarvis` é um wrapper de uma linha para `python3 cli/main.py`; se
preferir, use `python3 cli/main.py <comando>` diretamente — funciona igual.)

### `jarvis revisar`

Passa pelos rascunhos pendentes um a um. Para cada um:

- **[A]provar** — marca `status_revisao = revisado`, pronto para `exportar`.
- **[E]ditar** — abre o texto no seu `$EDITOR` (ou `nano`/`vi`, o que
  estiver disponível no PATH; se nenhum editor funcionar, cai para uma
  captura simples via terminal). O texto editado fica em `mensagem_final`;
  `mensagem_gerada` (o rascunho original do template) nunca é alterado,
  preservado para auditoria. Depois de editar, o item volta a perguntar a
  ação (pode editar de novo, aprovar ou descartar).
- **[D]escartar** — marca `status_revisao = descartado`. Fica registrado,
  mas não entra em `exportar`.
- **[P]ular** — deixa `pendente`, decide depois.
- **[Q]uit** — sai da revisão a qualquer momento; o que não foi decidido
  continua `pendente`.

### `jarvis exportar`

Pega todos os rascunhos com `status_revisao = revisado`, escreve num
`.csv` ou `.txt` (pela extensão do `--saida`) e marca cada um como
`exportado` — para não duplicar na próxima exportação. **O arquivo gerado
é só um rascunho pessoal para copiar/colar** — o envio em si e o registro
oficial de contato continuam fora do Jarvis, no sistema da corretora.

## Formato do arquivo de entrada

Apenas **CSV** é suportado (não `.xlsx`, por decisão deliberada de manter
zero dependências de terceiros — se seu CRM só exporta Excel, "Salvar
como... > CSV" resolve em segundos).

O parser não está amarrado a nomes de coluna fixos: `config/column_mapping.ini`
mapeia cada campo interno para o nome exato da coluna do seu arquivo — edite
esse `.ini` se o cabeçalho real do seu CRM for diferente, sem tocar em código.

Campos obrigatórios: `cliente_id`, `nome`, `tipo_estrutura`, `ativo_objeto`,
`data_fechamento`, `data_vencimento`. Opcionais: `operacao_id` (se ausente,
um ID sintético estável é gerado — ver `importer/validators.py`),
`strike_1`, `strike_2`, `barreira`, `status_barreira`, `valor_notional`,
`perfil_suitability`. `formato_data` e `separador_decimal` também ficam em
`column_mapping.ini`.

> Ainda não recebi o cabeçalho real do seu CRM oficial — quando tiver, é só
> ajustar `config/column_mapping.ini` (e `formato_data`/`separador_decimal`
> se necessário). Nenhum código muda.

### Tratamento de erros

- **Erro estrutural** (arquivo não encontrado, formato não suportado,
  vazio, sem cabeçalho, coluna obrigatória ausente): a importação inteira é
  abortada — nada é gravado.
- **Erro em uma linha** (campo obrigatório vazio/inválido): só aquela linha
  é descartada; o resto do arquivo é importado normalmente. Motivo exato
  registrado em `log_importacoes.detalhes` (JSON) e impresso no terminal.
- **Erro em campo opcional**: o campo fica `NULL`, um aviso é registrado, a
  operação continua sendo importada.

## Modelo de dados (SQLite)

Ver `db/schema.sql` para o schema completo e comentado.

- **clientes**: `id`, `codigo` (id do cliente no CRM oficial), `nome`,
  `perfil_suitability`.
- **operacoes**: `id`, `operacao_ref`, `cliente_id` (FK), `tipo_estrutura`,
  `ativo_objeto`, `data_fechamento`, `data_vencimento`, `strike_1`,
  `strike_2`, `barreira`, `status_barreira`, `status_barreira_anterior`
  (uso interno da regra de evento), `valor_notional`, `parametros_json`
  (linha bruta original, auditoria completa), `status` (`ativa`/`encerrada`),
  **`fonte_extracao`, `data_extracao`** (deixam explícito que é um espelho).
- **follow_ups**: `id`, `operacao_id` (FK), `data_gerado`, `regra_disparada`,
  `motivo_disparo`, `mensagem_gerada` (original, imutável), `mensagem_final`
  (editável em `revisar`), `status_revisao`
  (`pendente`/`revisado`/`descartado`/`exportado`), `data_revisao`.
- **log_importacoes**: `id`, `data`, `arquivo`, `linhas_processadas`,
  `novas`, `atualizadas`, `encerradas`, `erros`, `detalhes` (JSON com
  erros/avisos linha a linha + o relatório de diff da importação).
- **notas_pessoais**: `id`, `cliente_id` (FK), `operacao_id` (FK, opcional),
  `texto`, `data_criacao` — anotações livres, só suas.

Upsert de operações usa a chave `(cliente_id, operacao_ref)`. Operações
`ativa` que não aparecem mais na extração são marcadas `encerrada`
automaticamente — e listadas no relatório de diff do `jarvis importar`.

## Motor de regras

Configurável em `config/rules_config.ini`, sem mexer em código:

1. **Tempo decorrido**: dispara (uma única vez por limiar) quando os meses
   desde `data_fechamento` atingem cada valor de `meses` (default: `1,3,6,12`).
2. **Proximidade de vencimento**: dispara (uma única vez por limiar) quando
   faltam N dias ou menos para `data_vencimento` (default: `15`), e a
   operação ainda não venceu.
3. **Evento de barreira**: dispara quando `status_barreira` muda de valor
   entre duas extrações consecutivas da mesma operação.

**Deduplicação**: cada `(operação, regra_disparada)` gera um rascunho **uma
única vez**, independentemente do que você decidiu depois (`revisado`,
`descartado` ou `exportado`) — evita spam ao reimportar diariamente
enquanto a condição continuar verdadeira. As funções que avaliam cada regra
(`rules/rules_definitions.py`) são puras, sem acesso a banco — 100%
testáveis isoladamente.

O painel `jarvis hoje` usa mais dois parâmetros de `rules_config.ini`, que
**não geram rascunhos**, só destacam informação:

- `[status_barreira_tocada]`: quais valores de `status_barreira` contam
  como "tocada" no painel.
- `[janela_sem_contato]`: sinaliza clientes sem sinal de atividade no
  Jarvis há mais de N dias (default: 30). **Isto é um PROXY interno** —
  dias desde a `data_fechamento` mais recente entre as operações ativas do
  cliente. Não é, e não tenta ser, o registro oficial de contato — esse
  vive no CRM da corretora, fora do escopo do Jarvis.

## Templates de mensagem

`templates/mensagens/` tem um `.txt` por `tipo_estrutura` (nome do arquivo
= slug do tipo, ex. `capital_protegido.txt`) mais um `default.txt`
obrigatório. Placeholders: `{cliente}`/`{nome}`, `{codigo}`,
`{tipo_estrutura}`, `{ativo_objeto}`, `{data_fechamento}`,
`{data_vencimento}`, `{dias_restantes}`, `{strike_1}`, `{strike_2}`,
`{barreira}`, `{status_barreira}`, `{valor_notional}`, `{motivo_disparo}`.

Texto puro, sem YAML/JSON — qualquer um edita sem saber programar. Um
placeholder digitado errado aparece como `[nome_errado?]` na mensagem em
vez de quebrar a geração, ficando visível já na revisão manual (`jarvis
revisar`).

## Rodando os testes

```bash
python3 -m unittest discover -s tests -v
```

Cobre: parsing de datas/números, validação linha a linha, as 3 regras
isoladamente, geração de mensagens, as consultas/escritas de `db/queries.py`
(aprovar/descartar/exportar, painel `hoje`, briefing, notas pessoais), e um
fluxo de integração completo de 3 importações (incluindo o relatório de
diff) usando um banco SQLite temporário. Nenhum teste depende de rede.

## Backup do banco

```bash
./jarvis backup-db
```

Copia `crm_derivativos.db` para `backups/crm_derivativos_<timestamp>.db`.
Recomendado rodar logo após a importação diária. Restauração: pare o uso,
copie o backup desejado de volta para o caminho em `config/settings.ini`
(`db_path`) — arquivo único, sem migração, sem servidor.

## Limitações conhecidas (documentadas por transparência)

- Apenas `.csv` como entrada, por decisão deliberada de manter zero
  dependências de terceiros.
- "Sem sinal de atividade há mais de N dias" no painel `hoje` é um **proxy**
  (dias desde `data_fechamento`), não o contato oficial real — decisão
  tomada explicitamente ao definir o escopo desta fase.
- Sem `operacao_id` no arquivo de origem, o sistema gera um ID sintético a
  partir de `cliente_id + tipo_estrutura + ativo_objeto + data_fechamento +
  strikes + barreira`. Se algum desses campos mudar entre extrações para a
  "mesma" operação real, o Jarvis vai tratá-la como uma operação nova.
- O motor de regras roda sobre operações `ativa` no momento da importação;
  operações que já chegam `encerrada` na primeira extração nunca geram
  rascunho.

## Próximas fases (não implementadas nesta entrega)

Conforme escopo combinado, só entram depois da Fase 1 validada em uso real:

- **Fase 2**: score de prioridade de contato (sempre sugestão, nunca
  decisão automática) e painel de exposição consolidada por cliente/ativo.
- **Fase 3** (opcional): métricas pessoais de produtividade, simulador de
  cenário de barreira com inputs manuais (sem dado de mercado externo), e
  relatório mensal de atividade exportável.

Se/quando a mesa crescer e fizer sentido uma tela local (Streamlit) em vez
da CLI, isso também fica para depois — e exigiria avaliar se o ambiente
permite introduzir essa dependência de terceiros, já que hoje a prioridade
é zero contato com qualquer servidor externo.
