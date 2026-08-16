# Follow-up de Operações Estruturadas com Derivativos

Sistema local, **100% offline**, para identificar diariamente quais operações
estruturadas (capital protegido, autocall, dual currency etc.) da carteira
precisam de follow-up com o cliente, e gerar uma **mensagem pronta a partir de
templates** para revisão manual.

**O sistema nunca envia nada sozinho.** Ele só lê um arquivo local, atualiza
um banco SQLite local, aplica regras determinísticas e produz mensagens a
partir de templates fixos. Toda mensagem passa por revisão humana antes de
ser considerada "enviada" (e o envio em si é sempre manual, fora do sistema).

## Por que essas escolhas técnicas

- **SQLite (arquivo `.db` local)**: sem servidor, sem porta de rede, sem
  processo em background. O arquivo pode ser copiado, versionado por backup
  e auditado diretamente com qualquer leitor de SQLite.
- **pandas + openpyxl**: leitura de Excel/CSV sem depender de rede após a
  instalação inicial via pip. Todas as colunas são lidas como texto
  (`dtype=str`) e convertidas explicitamente em `importer/validators.py` —
  evita que o pandas "adivinhe" tipos e corrompa silenciosamente valores.
- **Mensagens por template (`templates/templates.yaml`), nunca por LLM**:
  saída 100% previsível, revisável por Compliance sem depender de uma IA
  externa e sem risco de alucinação. Trocar o texto de uma mensagem é editar
  uma string em um arquivo YAML.
- **CLI em vez de interface web**: menor superfície de risco (nenhum
  processo escutando rede, mesmo que "só localmente"), mais fácil de rodar
  em um ambiente air-gapped/regulado, e mais fácil de auditar (todo comando
  fica no histórico do shell). Ver seção [Evoluindo para uma tela](#evoluindo-para-uma-tela-streamlit)
  para quando fizer sentido migrar.

Nenhuma dependência faz chamada de rede em tempo de execução. `pandas`,
`openpyxl` e `PyYAML` são bibliotecas puramente locais depois de instaladas.

## Estrutura de pastas

```
CRM/
├── README.md
├── requirements.txt
├── settings.py                  # carregamento centralizado de config (YAML)
├── config/
│   ├── settings.yaml            # caminhos: banco, inbox, backups
│   ├── column_mapping.yaml      # mapeamento de colunas do arquivo de origem -> campos internos
│   └── rules_config.yaml        # limiares das regras (meses, dias, evento de barreira)
├── db/
│   ├── schema.sql                # schema SQLite completo
│   └── database.py               # conexão + inicialização do banco
├── importer/
│   ├── file_reader.py            # leitura de .csv/.xlsx (erros estruturais de arquivo)
│   ├── validators.py             # validação/parsing linha a linha (erros de dados)
│   └── import_run.py             # orquestra upsert + fechamento de operações + log
├── rules/
│   ├── rules_definitions.py      # funções puras das 3 regras (100% testáveis)
│   └── engine.py                 # aplica as regras sobre o banco, evita duplicidade
├── templates/
│   ├── templates.yaml            # 1 template por tipo_estrutura (editável por Compliance)
│   └── message_generator.py      # renderiza template com os dados da operação
├── cli/
│   └── main.py                   # interface de linha de comando (importar, revisar, etc.)
├── tests/                         # testes automatizados (unittest, sem dependências extras)
├── data/
│   ├── inbox/                     # onde você coloca o arquivo exportado do sistema interno
│   └── processed/                 # (opcional) arquivos já importados, para arquivo histórico
└── backups/                       # cópias do .db com timestamp (ver `backup-db`)
```

`crm_derivativos.db` é criado na raiz do projeto na primeira execução e
**nunca é versionado** (está no `.gitignore`, junto com tudo em `data/inbox`
e `data/processed`, pois pode conter dados de clientes).

## Instalação (única etapa que precisa de rede)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A partir daqui, tudo roda offline — pode desligar a rede/usar em ambiente
air-gapped.

## Uso diário

```bash
# 1. Uma única vez: cria o banco e as tabelas
python cli/main.py init-db

# 2. Todo dia: importa o arquivo exportado manualmente do sistema interno
python cli/main.py importar --arquivo data/inbox/export_2026-08-16.xlsx

# 3. Revisa os follow-ups pendentes gerados
python cli/main.py listar-pendentes

# 4. (opcional) exporta a lista para Excel, para revisar fora do terminal
python cli/main.py exportar-pendentes --saida pendentes_2026-08-16.xlsx

# 5. Depois de revisar (e, se for o caso, enviar manualmente) uma mensagem:
python cli/main.py revisar --id 12 --usuario "rafael" --status revisado
# ou, após o envio manual ter sido feito:
python cli/main.py revisar --id 12 --usuario "rafael" --status enviado

# 6. Backup do banco (recomendado rodar sempre após a importação diária)
python cli/main.py backup-db
```

O comando `importar` já roda o motor de regras automaticamente logo após
consolidar a importação — não é necessário nenhum passo manual adicional.

## Formato do arquivo de entrada

O parser **não está amarrado a nomes de coluna fixos**. Ele lê
`config/column_mapping.yaml`, onde cada campo interno (`cliente_id`, `nome`,
`tipo_estrutura`, ...) é mapeado para o nome exato da coluna como ela
aparece no seu arquivo. Se o seu sistema exporta `ID Cliente` em vez de
`cliente_id`, basta editar esse YAML — nenhum código Python precisa mudar.

Campos obrigatórios (a linha inteira é rejeitada se um deles faltar/for
inválido): `cliente_id`, `nome`, `tipo_estrutura`, `ativo_objeto`,
`data_fechamento`, `data_vencimento`.

Campos opcionais: `operacao_id` (se ausente, um ID sintético estável é
gerado a partir dos demais campos — ver `importer/validators.py`),
`strike_1`, `strike_2`, `barreira`, `status_barreira`, `valor_notional`,
`perfil_suitability`.

Também em `column_mapping.yaml`: `formato_data` (padrão `%d/%m/%Y`) e
`separador_decimal` (`,` para `1.234,56`, `.` para `1,234.56`).

> Assim que você tiver um exemplo real de cabeçalho/linha do seu sistema
> interno, é só ajustar `config/column_mapping.yaml` (e `formato_data` /
> `separador_decimal` se necessário) — não é preciso alterar código.

### Tratamento de erros na importação

- **Erro estrutural** (arquivo não encontrado, formato não suportado, vazio,
  ou coluna obrigatória ausente do cabeçalho): a importação inteira é
  **abortada** com uma mensagem clara — nada é gravado no banco.
- **Erro em uma linha** (campo obrigatório vazio, data inválida): **só
  aquela linha** é descartada; o restante do arquivo é importado
  normalmente. O motivo exato fica registrado em
  `log_importacoes.detalhes_erros` (JSON) e é impresso no terminal.
- **Erro em campo opcional** (ex.: `barreira` com valor não numérico): o
  campo fica `NULL` e um aviso é registrado — a operação continua sendo
  importada.

## Modelo de dados (SQLite)

Ver `db/schema.sql` para o schema completo e comentado. Resumo:

- **clientes**: `id`, `codigo` (identificador do sistema de origem),
  `nome`, `perfil_suitability`.
- **operacoes**: `id`, `operacao_ref`, `cliente_id` (FK), `tipo_estrutura`,
  `ativo_objeto`, `data_fechamento`, `data_vencimento`, `strike_1`,
  `strike_2`, `barreira`, `status_barreira`, `status_barreira_anterior`
  (usado pela regra de evento), `valor_notional`, `parametros_json` (linha
  bruta original, para auditoria completa), `status` (`ativa`/`encerrada`).
- **follow_ups**: `id`, `operacao_id` (FK), `data_gerado`,
  `regra_disparada`, `motivo_disparo`, `mensagem_gerada`, `status_revisao`
  (`pendente`/`revisado`/`enviado`), `usuario_revisor`, `data_revisao`.
- **log_importacoes**: `id`, `data`, `arquivo`, `linhas_processadas`,
  `novas`, `atualizadas`, `encerradas`, `erros`, `detalhes_erros` (JSON).

Upsert de operações usa a chave `(cliente_id, operacao_ref)`. Operações que
estavam `ativa` e não aparecem mais no arquivo importado são marcadas como
`encerrada` automaticamente.

## Motor de regras

Configurável em `config/rules_config.yaml`, sem precisar mexer em código:

1. **Tempo decorrido**: dispara (uma única vez por limiar) quando o número
   de meses desde `data_fechamento` atinge cada valor de uma lista
   (default: `[1, 3, 6, 12]`).
2. **Proximidade de vencimento**: dispara (uma única vez por limiar) quando
   faltam N dias ou menos para `data_vencimento` (default:
   `[30, 15, 5]`), e a operação ainda não venceu.
3. **Evento de barreira**: dispara quando `status_barreira` muda de valor
   entre duas importações consecutivas da mesma operação. Opcionalmente
   restrito a uma lista de status relevantes (`status_relevantes`).

**Regra de deduplicação**: cada `(operação, regra_disparada)` só gera um
follow-up **uma única vez**, independentemente do `status_revisao` do
registro gerado. Isso evita spam ao reimportar o arquivo diariamente
enquanto a condição de tempo/vencimento continuar verdadeira. O evento de
barreira, por natureza, só é reavaliado quando o status realmente muda de
novo — a própria comparação com `status_barreira_anterior` já evita
duplicidade sem precisar consultar o histórico de follow-ups.

As funções que avaliam cada regra (`rules/rules_definitions.py`) são puras
(sem acesso a banco), o que as torna 100% testáveis isoladamente — ver
`tests/test_rules_definitions.py`.

## Templates de mensagem

`templates/templates.yaml` tem um template por `tipo_estrutura` (chave =
slug do tipo, ex. `capital_protegido`), mais um template `default` usado
quando não há um template específico. Placeholders disponíveis:
`{cliente}`/`{nome}`, `{codigo}`, `{tipo_estrutura}`, `{ativo_objeto}`,
`{data_fechamento}`, `{data_vencimento}`, `{dias_restantes}`, `{strike_1}`,
`{strike_2}`, `{barreira}`, `{status_barreira}`, `{valor_notional}`,
`{motivo_disparo}`.

Este arquivo é YAML puro — pode ser revisado e aprovado por Compliance sem
tocar em código Python. Um placeholder digitado errado no template aparece
na mensagem gerada como `[nome_errado?]` em vez de quebrar a geração,
tornando o erro visível já na etapa de revisão manual.

## Rodando os testes

```bash
python -m unittest discover -s tests -v
```

Cobre: parsing de datas/números, validação linha a linha, avaliação das 3
regras isoladamente, geração de mensagens (incluindo determinismo e
fallback de template), e um fluxo de integração completo (2 importações +
fechamento de operação + deduplicação de regras) usando um banco SQLite
temporário.

## Backup do banco

```bash
python cli/main.py backup-db
```

Copia `crm_derivativos.db` para `backups/crm_derivativos_<timestamp>.db`.
Recomendado rodar isso logo após a importação diária. Como é um arquivo
único, a restauração é trivial: pare o uso do sistema, copie o backup
desejado de volta para o caminho configurado em `config/settings.yaml`
(`db_path`), e pronto — sem migração, sem servidor para reiniciar.

Para retenção de longo prazo, copie periodicamente o conteúdo de
`backups/` para o seu backup corporativo padrão (fora do repositório de
código) — este projeto não versiona nem transmite o `.db` para lugar
nenhum.

## Evoluindo para uma tela (Streamlit)

A CLI cobre bem o fluxo de revisão para uma pessoa. Se a mesa crescer (mais
de um Sales Trader revisando a mesma base, necessidade de filtrar/ordenar
visualmente, ou marcar vários follow-ups de uma vez), vale considerar
**Streamlit rodando localmente** (`streamlit run app.py`, sem
`--server.headless` exposto para fora do localhost) como upgrade:

- Mantém tudo local (o servidor Streamlit escuta em `127.0.0.1`, não em
  `0.0.0.0` — não expor a rede).
- Reaproveita 100% da lógica já construída aqui (`importer`, `rules`,
  `templates` são independentes de interface) — a tela seria só uma nova
  camada fina sobre essas mesmas funções.
- Não é necessário nesta fase: a CLI já entrega auditoria e simplicidade,
  que são a prioridade para um sistema de compliance.

## Limitações conhecidas (documentadas por transparência)

- Quando o arquivo de origem não traz um `operacao_id` próprio, o sistema
  gera um ID sintético a partir de `cliente_id + tipo_estrutura +
  ativo_objeto + data_fechamento + strikes + barreira`. Se qualquer um
  desses campos mudar entre importações para a "mesma" operação real, o
  sistema vai tratá-la como uma operação nova. Recomendação: peça ao time
  responsável pelo sistema de origem para incluir um ID de operação estável
  na exportação.
- O motor de regras roda sobre operações com `status = 'ativa'` no momento
  da importação; operações que já chegam `encerrada` no primeiro arquivo
  importado nunca geram follow-up.
