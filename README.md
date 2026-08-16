# Follow-up de Operações Estruturadas com Derivativos

Sistema local, **100% offline e air-gapped**, para identificar diariamente
quais operações estruturadas (capital protegido, autocall, dual currency
etc.) da carteira precisam de follow-up com o cliente, e gerar uma
**mensagem pronta a partir de templates** para revisão manual.

**O sistema nunca envia nada sozinho.** Ele só lê um arquivo local, atualiza
um banco SQLite local, aplica regras determinísticas e produz mensagens a
partir de templates fixos. Toda mensagem passa por revisão humana antes de
ser considerada "enviada" (e o envio em si é sempre manual, fora do sistema).

## Zero dependências, zero rede — inclusive na instalação

Este projeto usa **exclusivamente a biblioteca padrão do Python 3.11+**
(`sqlite3`, `csv`, `configparser`, `hashlib`, `unicodedata`, `datetime`,
`pathlib`, `argparse`, `shutil`, `json`). Não há `pandas`, `openpyxl`,
`PyYAML` nem nenhuma outra biblioteca de terceiros.

Na prática isso significa:

- **Nenhum `pip install` é necessário**, nem mesmo na primeira execução —
  basta ter o interpretador Python 3.11+ já instalado na máquina.
- **Nenhum contato com PyPI, GitHub ou qualquer servidor externo** é
  necessário para instalar, rodar ou usar o sistema no dia a dia.
- É seguro copiar esta pasta inteira (por exemplo, via USB aprovado pela
  sua área de segurança, ou qualquer outro meio de transferência já
  homologado internamente) para uma máquina 100% air-gapped e rodar
  diretamente, sem qualquer etapa de "instalação" prévia.

O único pré-requisito é o **próprio Python** estar disponível na máquina de
destino — o mesmo runtime que qualquer outro sistema em Python exigiria, e
que normalmente já é fornecido/homologado pela área de infraestrutura,
independente deste projeto.

## Por que essas escolhas técnicas

- **SQLite (arquivo `.db` local)**: sem servidor, sem porta de rede, sem
  processo em background. O arquivo pode ser copiado, versionado por backup
  e auditado diretamente com qualquer leitor de SQLite.
- **CSV puro (módulo `csv` da stdlib) em vez de leitura de `.xlsx`**: ler
  planilhas binárias exige uma biblioteca de terceiros (`openpyxl`), que é
  mais uma superfície de risco/dependência para auditar. Em vez disso, o
  sistema lê CSV — se o seu sistema interno só exporta Excel, um "Salvar
  como... > CSV" resolve em segundos, e a leitura em si passa a ser 100%
  biblioteca padrão. Todas as colunas são lidas como texto e convertidas
  explicitamente em `importer/validators.py` — nada de inferência
  automática de tipo que possa corromper valores silenciosamente.
- **Mensagens por template (arquivos `.txt` em `templates/mensagens/`),
  nunca por LLM**: saída 100% previsível, revisável e aprovável por
  Compliance sem depender de uma IA externa e sem risco de alucinação.
  Trocar o texto de uma mensagem é editar um `.txt` — qualquer pessoa
  consegue, sem saber programar.
- **Configuração em `.ini` (módulo `configparser` da stdlib)** em vez de
  YAML: elimina a dependência do `PyYAML` mantendo comentários e edição
  manual fáceis.
- **CLI em vez de interface web**: menor superfície de risco (nenhum
  processo escutando rede, mesmo que "só localmente"), mais fácil de rodar
  em ambiente air-gapped/regulado, e mais fácil de auditar (todo comando
  fica no histórico do shell). Ver [Evoluindo para uma tela](#evoluindo-para-uma-tela-streamlit)
  para quando fizer sentido migrar — e note que mesmo esse upgrade opcional
  exigiria introduzir uma dependência externa (`streamlit`), o que só faz
  sentido se as restrições de rede permitirem.

## Estrutura de pastas

```
CRM/
├── README.md
├── requirements.txt              # documenta a ausência de dependências (não há nada a instalar)
├── settings.py                   # carregamento centralizado de config (.ini)
├── config/
│   ├── settings.ini              # caminhos: banco, inbox, backups
│   ├── column_mapping.ini        # mapeamento de colunas do arquivo de origem -> campos internos
│   └── rules_config.ini          # limiares das regras (meses, dias, evento de barreira)
├── db/
│   ├── schema.sql                 # schema SQLite completo
│   └── database.py                # conexão + inicialização do banco
├── importer/
│   ├── file_reader.py             # leitura de .csv (erros estruturais de arquivo)
│   ├── validators.py              # validação/parsing linha a linha (erros de dados)
│   └── import_run.py              # orquestra upsert + fechamento de operações + log
├── rules/
│   ├── rules_definitions.py       # funções puras das 3 regras (100% testáveis)
│   └── engine.py                  # aplica as regras sobre o banco, evita duplicidade
├── templates/
│   ├── mensagens/                 # 1 arquivo .txt por tipo_estrutura (editável por Compliance)
│   │   ├── default.txt
│   │   ├── capital_protegido.txt
│   │   ├── autocall.txt
│   │   └── dual_currency.txt
│   └── message_generator.py       # renderiza template com os dados da operação
├── cli/
│   └── main.py                    # interface de linha de comando (importar, revisar, etc.)
├── tests/                          # testes automatizados (unittest da stdlib)
├── data/
│   ├── inbox/                      # onde você coloca o arquivo exportado do sistema interno
│   └── processed/                  # (opcional) arquivos já importados, para arquivo histórico
└── backups/                        # cópias do .db com timestamp (ver `backup-db`)
```

`crm_derivativos.db` é criado na raiz do projeto na primeira execução e
**nunca é versionado** (está no `.gitignore`, junto com tudo em `data/inbox`
e `data/processed`, pois pode conter dados de clientes).

## Instalação

Não há instalação. Copie a pasta do projeto para a máquina onde vai rodar
(ela já tem tudo que precisa) e confirme que o Python está disponível:

```bash
python3 --version   # precisa ser 3.11 ou superior
```

Pronto — pode usar imediatamente, offline, a partir daqui.

## Uso diário

```bash
# 1. Uma única vez: cria o banco e as tabelas
python3 cli/main.py init-db

# 2. Todo dia: importa o arquivo exportado manualmente do sistema interno
python3 cli/main.py importar --arquivo data/inbox/export_2026-08-16.csv

# 3. Revisa os follow-ups pendentes gerados
python3 cli/main.py listar-pendentes

# 4. (opcional) exporta a lista para CSV, para revisar fora do terminal (abre no Excel)
python3 cli/main.py exportar-pendentes --saida pendentes_2026-08-16.csv

# 5. Depois de revisar (e, se for o caso, enviar manualmente) uma mensagem:
python3 cli/main.py revisar --id 12 --usuario "rafael" --status revisado
# ou, após o envio manual ter sido feito:
python3 cli/main.py revisar --id 12 --usuario "rafael" --status enviado

# 6. Backup do banco (recomendado rodar sempre após a importação diária)
python3 cli/main.py backup-db
```

O comando `importar` já roda o motor de regras automaticamente logo após
consolidar a importação — não é necessário nenhum passo manual adicional.

## Formato do arquivo de entrada

Apenas **CSV** é suportado (não `.xlsx`/`.xls` — ver justificativa acima).
Se o seu sistema interno exporta em Excel, use "Salvar como... > CSV" antes
de importar.

O parser **não está amarrado a nomes de coluna fixos**. Ele lê
`config/column_mapping.ini`, onde cada campo interno (`cliente_id`, `nome`,
`tipo_estrutura`, ...) é mapeado para o nome exato da coluna como ela
aparece no seu arquivo. Se o seu sistema exporta `ID Cliente` em vez de
`cliente_id`, basta editar esse `.ini` — nenhum código Python precisa mudar.

Campos obrigatórios (a linha inteira é rejeitada se um deles faltar/for
inválido): `cliente_id`, `nome`, `tipo_estrutura`, `ativo_objeto`,
`data_fechamento`, `data_vencimento`.

Campos opcionais: `operacao_id` (se ausente, um ID sintético estável é
gerado a partir dos demais campos — ver `importer/validators.py`),
`strike_1`, `strike_2`, `barreira`, `status_barreira`, `valor_notional`,
`perfil_suitability`.

Também em `column_mapping.ini` (seção `[geral]`): `formato_data` (padrão
`%d/%m/%Y`) e `separador_decimal` (`,` para `1.234,56`, `.` para
`1,234.56`). O delimitador do CSV (vírgula, ponto-e-vírgula ou tabulação) é
detectado automaticamente linha a linha.

> Assim que você tiver um exemplo real de cabeçalho/linha do seu sistema
> interno, é só ajustar `config/column_mapping.ini` (e `formato_data` /
> `separador_decimal` se necessário) — não é preciso alterar código.

### Tratamento de erros na importação

- **Erro estrutural** (arquivo não encontrado, formato não suportado, vazio,
  sem cabeçalho, ou coluna obrigatória ausente): a importação inteira é
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

Configurável em `config/rules_config.ini`, sem precisar mexer em código:

1. **Tempo decorrido**: dispara (uma única vez por limiar) quando o número
   de meses desde `data_fechamento` atinge cada valor de uma lista
   (default: `1,3,6,12`).
2. **Proximidade de vencimento**: dispara (uma única vez por limiar) quando
   faltam N dias ou menos para `data_vencimento` (default: `30,15,5`), e a
   operação ainda não venceu.
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

`templates/mensagens/` tem um arquivo `.txt` por `tipo_estrutura` (nome do
arquivo = slug do tipo, ex. `capital_protegido.txt`), mais um
`default.txt` obrigatório, usado quando não há um template específico.
Placeholders disponíveis: `{cliente}`/`{nome}`, `{codigo}`,
`{tipo_estrutura}`, `{ativo_objeto}`, `{data_fechamento}`,
`{data_vencimento}`, `{dias_restantes}`, `{strike_1}`, `{strike_2}`,
`{barreira}`, `{status_barreira}`, `{valor_notional}`, `{motivo_disparo}`.

Cada template é texto puro — pode ser revisado e aprovado por Compliance
sem tocar em código Python nem entender YAML/JSON. Um placeholder digitado
errado no template aparece na mensagem gerada como `[nome_errado?]` em vez
de quebrar a geração, tornando o erro visível já na etapa de revisão
manual.

## Rodando os testes

```bash
python3 -m unittest discover -s tests -v
```

Cobre: parsing de datas/números, validação linha a linha, avaliação das 3
regras isoladamente, geração de mensagens (incluindo determinismo e
fallback de template), e um fluxo de integração completo (3 importações +
fechamento de operação + deduplicação de regras) usando um banco SQLite
temporário. Nenhum teste depende de rede nem de bibliotecas de terceiros.

## Backup do banco

```bash
python3 cli/main.py backup-db
```

Copia `crm_derivativos.db` para `backups/crm_derivativos_<timestamp>.db`.
Recomendado rodar isso logo após a importação diária. Como é um arquivo
único, a restauração é trivial: pare o uso do sistema, copie o backup
desejado de volta para o caminho configurado em `config/settings.ini`
(`db_path`), e pronto — sem migração, sem servidor para reiniciar.

Para retenção de longo prazo, copie periodicamente o conteúdo de
`backups/` para o seu backup corporativo padrão (fora deste diretório) —
este projeto não versiona nem transmite o `.db` para lugar nenhum.

## Evoluindo para uma tela (Streamlit)

A CLI cobre bem o fluxo de revisão para uma pessoa. Se a mesa crescer (mais
de um Sales Trader revisando a mesma base, necessidade de filtrar/ordenar
visualmente, ou marcar vários follow-ups de uma vez), vale considerar uma
tela local como upgrade futuro — mas isso **exigiria introduzir uma
dependência de terceiros** (ex. `streamlit`), o que só faz sentido se o seu
ambiente permitir esse tipo de instalação. Dado que hoje o ambiente-alvo
não pode acessar nenhum servidor externo, este projeto **deliberadamente
não inclui** essa dependência — a base de código já está organizada para
isso (`importer`, `rules`, `templates` são independentes de interface),
então a migração fica pronta para o dia em que fizer sentido, sem reescrever
nada da lógica de negócio.

## Limitações conhecidas (documentadas por transparência)

- Apenas `.csv` é suportado como entrada (não `.xlsx`/`.xls`), por decisão
  deliberada de manter zero dependências de terceiros — ver seção acima.
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
