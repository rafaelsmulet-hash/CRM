#!/usr/bin/env python3
"""CLI de revisão e operação do sistema de follow-up de derivativos.

Uso (a partir da raiz do projeto):
    python cli/main.py init-db
    python cli/main.py importar --arquivo data/inbox/export_2026-08-16.csv
    python cli/main.py listar-pendentes
    python cli/main.py exportar-pendentes --saida pendentes.csv
    python cli/main.py revisar --id 12 --usuario "rafael" --status revisado
    python cli/main.py backup-db

Nenhum comando envia mensagens automaticamente. "revisar" apenas registra,
para fins de auditoria, que um humano revisou (e opcionalmente marcou como
enviada manualmente) uma mensagem gerada pelo sistema.
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import get_connection, init_db  # noqa: E402
from importer.file_reader import ArquivoInvalidoError  # noqa: E402
from importer.import_run import executar_importacao  # noqa: E402
from settings import carregar_column_mapping, carregar_rules_config, carregar_settings  # noqa: E402

STATUS_VALIDOS = ("pendente", "revisado", "enviado")


def cmd_init_db(args, cfg):
    init_db(cfg["_db_path_absoluto"])
    print(f"Banco inicializado em: {cfg['_db_path_absoluto']}")


def cmd_importar(args, cfg):
    init_db(cfg["_db_path_absoluto"])  # garante que as tabelas existem
    mapeamento = carregar_column_mapping()
    rules_config = carregar_rules_config()
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        resultado = executar_importacao(conn, args.arquivo, mapeamento, rules_config)
    except ArquivoInvalidoError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    print(f"Importação concluída: {args.arquivo}")
    print(f"  Linhas processadas : {resultado.linhas_processadas}")
    print(f"  Novas operações    : {resultado.novas}")
    print(f"  Atualizadas        : {resultado.atualizadas}")
    print(f"  Encerradas         : {resultado.encerradas}")
    print(f"  Erros              : {len(resultado.erros)}")
    print(f"  Avisos             : {len(resultado.avisos)}")
    print(f"  Follow-ups gerados : {resultado.follow_ups_gerados}")
    for erro in resultado.erros:
        print(f"    [ERRO] linha {erro['linha']}: {erro['motivo']}")
    for aviso in resultado.avisos:
        print(f"    [AVISO] linha {aviso['linha']}: {aviso['motivo']}")


def _query_pendentes(conn):
    return conn.execute(
        """SELECT f.id, c.nome AS cliente, c.codigo AS cliente_codigo,
                  o.tipo_estrutura, o.ativo_objeto, o.data_vencimento,
                  f.regra_disparada, f.motivo_disparo, f.mensagem_gerada,
                  f.status_revisao, f.data_gerado
           FROM follow_ups f
           JOIN operacoes o ON o.id = f.operacao_id
           JOIN clientes c ON c.id = o.cliente_id
           WHERE f.status_revisao = 'pendente'
           ORDER BY o.data_vencimento ASC, f.data_gerado ASC"""
    ).fetchall()


def cmd_listar_pendentes(args, cfg):
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        pendentes = _query_pendentes(conn)
    finally:
        conn.close()

    if not pendentes:
        print("Nenhum follow-up pendente.")
        return

    for row in pendentes:
        print("-" * 78)
        print(f"ID: {row['id']}  |  Cliente: {row['cliente']} ({row['cliente_codigo']})")
        print(f"Operação: {row['tipo_estrutura']} / {row['ativo_objeto']}  |  Vencimento: {row['data_vencimento']}")
        print(f"Regra disparada: {row['regra_disparada']}  |  Motivo: {row['motivo_disparo']}")
        print(f"Gerado em: {row['data_gerado']}")
        print("Mensagem:")
        for linha in row["mensagem_gerada"].splitlines():
            print(f"  {linha}")
    print("-" * 78)
    print(f"Total pendentes: {len(pendentes)}")


def cmd_exportar_pendentes(args, cfg):
    import csv

    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        pendentes = _query_pendentes(conn)
    finally:
        conn.close()

    if not pendentes:
        print("Nenhum follow-up pendente para exportar.")
        return

    colunas = pendentes[0].keys()
    with open(args.saida, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=colunas)
        writer.writeheader()
        for row in pendentes:
            writer.writerow(dict(row))
    print(f"Exportado {len(pendentes)} follow-up(s) pendente(s) para: {args.saida}")
    print("(Abra normalmente no Excel — codificação utf-8-sig evita acentos quebrados.)")


def cmd_revisar(args, cfg):
    if args.status not in STATUS_VALIDOS:
        print(f"ERRO: status deve ser um de {STATUS_VALIDOS}", file=sys.stderr)
        sys.exit(1)

    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        cur = conn.execute("SELECT id FROM follow_ups WHERE id = ?", (args.id,))
        if cur.fetchone() is None:
            print(f"ERRO: follow_up id={args.id} não encontrado.", file=sys.stderr)
            sys.exit(1)
        conn.execute(
            """UPDATE follow_ups
               SET status_revisao = ?, usuario_revisor = ?, data_revisao = datetime('now')
               WHERE id = ?""",
            (args.status, args.usuario, args.id),
        )
        conn.commit()
    finally:
        conn.close()
    print(f"follow_up id={args.id} marcado como '{args.status}' por '{args.usuario}'.")


def cmd_backup_db(args, cfg):
    origem = Path(cfg["_db_path_absoluto"])
    if not origem.exists():
        print(f"ERRO: banco não encontrado em {origem}. Rode 'init-db' primeiro.", file=sys.stderr)
        sys.exit(1)
    destino_dir = Path(cfg["_backups_absoluto"])
    destino_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = destino_dir / f"{origem.stem}_{timestamp}{origem.suffix}"
    shutil.copy2(origem, destino)
    print(f"Backup criado em: {destino}")


def montar_parser():
    parser = argparse.ArgumentParser(description="CLI de follow-up de operações estruturadas com derivativos.")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("init-db", help="Cria o banco SQLite e as tabelas, se não existirem.")

    p_importar = sub.add_parser("importar", help="Importa um arquivo Excel/CSV e roda o motor de regras.")
    p_importar.add_argument("--arquivo", required=True, help="Caminho do arquivo .csv a importar.")

    sub.add_parser("listar-pendentes", help="Lista os follow-ups pendentes de revisão no terminal.")

    p_export = sub.add_parser("exportar-pendentes", help="Exporta os follow-ups pendentes para um arquivo CSV (abre no Excel).")
    p_export.add_argument("--saida", required=True, help="Caminho do arquivo .csv de saída.")

    p_revisar = sub.add_parser("revisar", help="Marca um follow-up como revisado/enviado (registra auditoria).")
    p_revisar.add_argument("--id", type=int, required=True, help="ID do follow_up (ver listar-pendentes).")
    p_revisar.add_argument("--usuario", required=True, help="Nome/login de quem está revisando.")
    p_revisar.add_argument("--status", default="revisado", choices=STATUS_VALIDOS, help="Novo status (default: revisado).")

    sub.add_parser("backup-db", help="Copia o arquivo .db atual para o diretório de backups, com timestamp.")

    return parser


def main():
    parser = montar_parser()
    args = parser.parse_args()
    cfg = carregar_settings()

    comandos = {
        "init-db": cmd_init_db,
        "importar": cmd_importar,
        "listar-pendentes": cmd_listar_pendentes,
        "exportar-pendentes": cmd_exportar_pendentes,
        "revisar": cmd_revisar,
        "backup-db": cmd_backup_db,
    }
    comandos[args.comando](args, cfg)


if __name__ == "__main__":
    main()
