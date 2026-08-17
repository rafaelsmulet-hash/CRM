#!/usr/bin/env python3
"""CLI do Jarvis — assistente PESSOAL de mesa para follow-up de operações
estruturadas com derivativos.

IMPORTANTE (escopo): o Jarvis é read-only em relação à operação. Ele nunca
substitui o CRM oficial da corretora, nunca fecha operação, nunca registra
contato oficial e nunca envia nada sozinho. Toda mensagem gerada aqui é um
RASCUNHO pessoal para você revisar; o registro formal de contato com o
cliente continua no sistema homologado da corretora.

Uso (a partir da raiz do projeto, ou via o script `./jarvis` na raiz):
    python3 cli/main.py init-db
    python3 cli/main.py importar --arquivo data/inbox/export_2026-08-16.csv
    python3 cli/main.py hoje
    python3 cli/main.py revisar
    python3 cli/main.py exportar --saida rascunhos_2026-08-16.csv
    python3 cli/main.py briefing --cliente 1001
    python3 cli/main.py nota --cliente 1001 --texto "Ligou perguntando sobre o autocall."
    python3 cli/main.py backup-db
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import queries  # noqa: E402
from db.database import get_connection, init_db  # noqa: E402
from importer.file_reader import ArquivoInvalidoError  # noqa: E402
from importer.import_run import executar_importacao  # noqa: E402
from settings import carregar_column_mapping, carregar_rules_config, carregar_settings  # noqa: E402


# ------------------------------------------------------------------ init-db

def cmd_init_db(args, cfg):
    init_db(cfg["_db_path_absoluto"])
    print(f"Banco inicializado em: {cfg['_db_path_absoluto']}")


# ------------------------------------------------------------------ importar

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
    print(f"  Rascunhos de follow-up gerados: {resultado.follow_ups_gerados}")

    print("\n--- O que mudou desde a extração anterior ---")
    if resultado.diff_novas:
        print(f"Novas operações ({len(resultado.diff_novas)}):")
        for d in resultado.diff_novas:
            print(f"  + {d['cliente']} ({d['cliente_codigo']}) — {d['tipo_estrutura']} / {d['ativo_objeto']} [{d['operacao_ref']}]")
    if resultado.diff_encerradas:
        print(f"Operações que saíram da extração / provavelmente encerradas ({len(resultado.diff_encerradas)}):")
        for d in resultado.diff_encerradas:
            print(f"  - {d['cliente']} ({d['cliente_codigo']}) — {d['tipo_estrutura']} / {d['ativo_objeto']} [{d['operacao_ref']}]")
    if resultado.diff_mudancas_barreira:
        print(f"Mudanças de status de barreira ({len(resultado.diff_mudancas_barreira)}):")
        for d in resultado.diff_mudancas_barreira:
            print(f"  ~ {d['cliente']} ({d['cliente_codigo']}) [{d['operacao_ref']}]: '{d['status_anterior']}' -> '{d['status_atual']}'")
    if not (resultado.diff_novas or resultado.diff_encerradas or resultado.diff_mudancas_barreira):
        print("Nenhuma mudança estrutural detectada desde a última extração.")

    for erro in resultado.erros:
        print(f"    [ERRO] linha {erro['linha']}: {erro['motivo']}")
    for aviso in resultado.avisos:
        print(f"    [AVISO] linha {aviso['linha']}: {aviso['motivo']}")


# ------------------------------------------------------------------ hoje

def cmd_hoje(args, cfg):
    rules_config = carregar_rules_config()
    hoje = date.today()
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        pendentes = queries.contar_pendentes(conn)

        cfg_venc = rules_config.get("regra_vencimento_proximo", {})
        janela_venc = max(cfg_venc.get("dias_antes", [15]) or [15])
        vencimentos = queries.listar_vencimentos_proximos(conn, janela_venc, hoje) if cfg_venc.get("ativa", True) else []

        valores_tocada = rules_config.get("status_barreira_tocada", [])
        barreiras = queries.listar_barreiras_tocadas(conn, valores_tocada)

        cfg_contato = rules_config.get("janela_sem_contato", {})
        sem_contato = []
        if cfg_contato.get("ativa", True):
            sem_contato = queries.listar_clientes_sem_contato(conn, cfg_contato.get("dias", 30), hoje)
    finally:
        conn.close()

    print(f"=== Painel do dia — {hoje.isoformat()} ===\n")

    print(f"Rascunhos de follow-up pendentes de revisão: {pendentes}")
    print("(rode `jarvis revisar` para passar por eles um a um)\n")

    print(f"Vencimentos nos próximos {janela_venc} dia(s): {len(vencimentos)}")
    for op, dias in vencimentos:
        print(f"  {op['cliente_nome']} ({op['cliente_codigo']}) — {op['tipo_estrutura']} / {op['ativo_objeto']} "
              f"— vence em {dias} dia(s) ({op['data_vencimento']})")
    print()

    print(f"Barreiras tocadas ({'/'.join(valores_tocada) or 'nenhum status configurado'}): {len(barreiras)}")
    for op in barreiras:
        print(f"  {op['cliente_nome']} ({op['cliente_codigo']}) — {op['tipo_estrutura']} / {op['ativo_objeto']} "
              f"— status_barreira: {op['status_barreira']}")
    print()

    if cfg_contato.get("ativa", True):
        dias_limite = cfg_contato.get("dias", 30)
        print(f"Clientes sem sinal de atividade há mais de {dias_limite} dia(s) "
              f"(PROXY interno: dias desde a data_fechamento mais recente entre operações ativas — "
              f"NÃO é o registro oficial de contato do CRM): {len(sem_contato)}")
        for c in sem_contato:
            print(f"  {c['cliente_nome']} ({c['cliente_codigo']}) — {c['dias_desde_ultimo_fechamento']} dia(s)")


# ------------------------------------------------------------------ revisar

def _editor_disponivel() -> list[str] | None:
    candidatos = []
    if os.environ.get("EDITOR"):
        candidatos.append(os.environ["EDITOR"])
    candidatos += ["nano", "vi"]
    for candidato in candidatos:
        caminho = shutil.which(candidato.split()[0])
        if caminho:
            return candidato.split()
    return None


def _capturar_texto_via_stdin() -> str:
    print("(digite o novo texto linha a linha; finalize com uma linha contendo só um ponto '.')")
    linhas = []
    while True:
        linha = input()
        if linha.strip() == ".":
            break
        linhas.append(linha)
    return "\n".join(linhas).strip()


def _editar_texto(texto_atual: str) -> str:
    """Abre o texto em $EDITOR (ou nano/vi) para edição manual. Se nenhum
    editor estiver disponível no PATH, se o editor sair com erro, ou se o
    resultado ficar vazio, cai para uma captura simples via stdin — nunca
    devolve silenciosamente um texto que pode não ter sido realmente
    editado (importante num rascunho que vai para revisão de compliance)."""
    comando_editor = _editor_disponivel()
    if comando_editor:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(texto_atual)
            caminho_tmp = f.name
        try:
            codigo_saida = subprocess.call(comando_editor + [caminho_tmp])
            if codigo_saida == 0:
                with open(caminho_tmp, "r", encoding="utf-8") as f:
                    texto_editado = f.read().strip()
                if texto_editado:
                    return texto_editado
                print("(editor devolveu texto vazio; rascunho anterior mantido)")
                return texto_atual
            print(f"(editor saiu com código {codigo_saida}; caindo para edição via terminal)")
        except OSError as e:
            print(f"(falha ao abrir o editor: {e}; caindo para edição via terminal)")
        finally:
            os.unlink(caminho_tmp)
    else:
        print("(nenhum editor encontrado no PATH)")

    return _capturar_texto_via_stdin()


def cmd_revisar(args, cfg):
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        pendentes = queries.listar_pendentes(conn)
        if not pendentes:
            print("Nenhum rascunho de follow-up pendente de revisão.")
            return

        total = len(pendentes)
        for i, item in enumerate(pendentes, start=1):
            follow_up_id = item["id"]
            mensagem_atual = item["mensagem_final"]
            while True:
                print("-" * 78)
                print(f"[{i}/{total}] ID {follow_up_id} | {item['cliente_nome']} ({item['cliente_codigo']})")
                print(f"Operação: {item['tipo_estrutura']} / {item['ativo_objeto']}  |  Vencimento: {item['data_vencimento']}")
                print(f"Regra: {item['regra_disparada']}  |  Motivo: {item['motivo_disparo']}")
                print("Rascunho:")
                for linha in mensagem_atual.splitlines():
                    print(f"  {linha}")
                acao = input("\n[A]provar  [E]ditar  [D]escartar  [P]ular  [Q]uit > ").strip().lower()

                if acao in ("a", "aprovar"):
                    queries.aprovar_follow_up(conn, follow_up_id, mensagem_atual)
                    print("-> aprovado.")
                    break
                if acao in ("e", "editar"):
                    mensagem_atual = _editar_texto(mensagem_atual)
                    continue
                if acao in ("d", "descartar"):
                    queries.descartar_follow_up(conn, follow_up_id)
                    print("-> descartado.")
                    break
                if acao in ("p", "pular", ""):
                    print("-> deixado como pendente.")
                    break
                if acao in ("q", "sair", "quit"):
                    print("Revisão interrompida.")
                    return
                print("Opção inválida.")
    finally:
        conn.close()

    print("-" * 78)
    print("Revisão concluída.")


# ------------------------------------------------------------------ exportar

def cmd_exportar(args, cfg):
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        revisados = queries.listar_revisados_para_exportar(conn)
        if not revisados:
            print("Nenhum rascunho revisado/aprovado pronto para exportar. Rode `jarvis revisar` primeiro.")
            return

        destino = Path(args.saida)
        if destino.suffix.lower() == ".txt":
            with open(destino, "w", encoding="utf-8") as f:
                for item in revisados:
                    f.write(f"=== {item['cliente_nome']} ({item['cliente_codigo']}) — "
                             f"{item['tipo_estrutura']} / {item['ativo_objeto']} ===\n")
                    f.write(item["mensagem_final"].strip() + "\n\n")
        else:
            with open(destino, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "cliente_nome", "cliente_codigo", "tipo_estrutura", "ativo_objeto",
                    "operacao_ref", "data_vencimento", "regra_disparada", "motivo_disparo", "mensagem_final",
                ])
                writer.writeheader()
                for item in revisados:
                    writer.writerow({chave: item[chave] for chave in writer.fieldnames})

        queries.marcar_exportados(conn, [item["id"] for item in revisados])
        print(f"Exportado {len(revisados)} rascunho(s) revisado(s) para: {destino}")
        print("Lembrete: isto é um RASCUNHO pessoal. O registro oficial de contato "
              "com o cliente continua no sistema homologado da corretora.")
    finally:
        conn.close()


# ------------------------------------------------------------------ briefing

def cmd_briefing(args, cfg):
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        info = queries.briefing_cliente(conn, args.cliente)
    finally:
        conn.close()

    if info is None:
        print(f"ERRO: cliente com código '{args.cliente}' não encontrado.", file=sys.stderr)
        sys.exit(1)

    cliente = info["cliente"]
    hoje = date.today()
    print(f"=== Briefing: {cliente['nome']} ({cliente['codigo']}) ===")
    print(f"Perfil de suitability: {cliente['perfil_suitability'] or 'N/D'}\n")

    print(f"Operações ativas ({len(info['operacoes_ativas'])}):")
    for op in info["operacoes_ativas"]:
        dias_venc = (date.fromisoformat(op["data_vencimento"]) - hoje).days
        print(f"  [{op['operacao_ref']}] {op['tipo_estrutura']} / {op['ativo_objeto']} — "
              f"vence em {dias_venc} dia(s) — status_barreira: {op['status_barreira'] or 'N/D'} — "
              f"fonte: {op['fonte_extracao']} @ {op['data_extracao']}")
    if not info["operacoes_ativas"]:
        print("  (nenhuma)")
    print()

    print(f"Rascunhos de follow-up pendentes ({len(info['follow_ups_pendentes'])}):")
    for f in info["follow_ups_pendentes"]:
        print(f"  ID {f['id']} — {f['regra_disparada']}: {f['motivo_disparo']}")
    if not info["follow_ups_pendentes"]:
        print("  (nenhum)")
    print()

    print(f"Notas pessoais ({len(info['notas'])}):")
    for n in info["notas"]:
        print(f"  [{n['data_criacao']}] {n['texto']}")
    if not info["notas"]:
        print("  (nenhuma)")

    datas_fechamento = [date.fromisoformat(op["data_fechamento"]) for op in info["operacoes_ativas"]]
    if datas_fechamento:
        dias = (hoje - max(datas_fechamento)).days
        print(f"\nÚltimo fechamento entre as operações ativas: há {dias} dia(s) "
              f"(proxy interno, não é o contato oficial registrado no CRM).")


# ------------------------------------------------------------------ nota

def cmd_nota(args, cfg):
    conn = get_connection(cfg["_db_path_absoluto"])
    try:
        try:
            nota_id = queries.inserir_nota(conn, args.cliente, args.operacao, args.texto)
        except ValueError as e:
            print(f"ERRO: {e}", file=sys.stderr)
            sys.exit(1)
    finally:
        conn.close()
    print(f"Nota id={nota_id} registrada para o cliente '{args.cliente}'.")


# ------------------------------------------------------------------ backup-db

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


# ------------------------------------------------------------------ parser

def montar_parser():
    parser = argparse.ArgumentParser(prog="jarvis", description=(
        "Jarvis — assistente pessoal de mesa para follow-up de operações estruturadas com derivativos. "
        "Read-only em relação à operação: nunca substitui o CRM oficial."
    ))
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("init-db", help="Cria o banco SQLite e as tabelas, se não existirem.")

    p_importar = sub.add_parser("importar", help="Importa uma extração manual do CRM e roda o motor de regras.")
    p_importar.add_argument("--arquivo", required=True, help="Caminho do arquivo .csv exportado do CRM oficial.")

    sub.add_parser("hoje", help="Painel do dia: pendentes, vencimentos próximos, barreiras tocadas, clientes sem contato.")

    sub.add_parser("revisar", help="Revisa os rascunhos pendentes um a um (aprovar/editar/descartar).")

    p_exportar = sub.add_parser("exportar", help="Exporta os rascunhos aprovados (.csv ou .txt) e marca como 'exportado'.")
    p_exportar.add_argument("--saida", required=True, help="Caminho do arquivo de saída (.csv ou .txt).")

    p_briefing = sub.add_parser("briefing", help="Resumo rápido de um cliente.")
    p_briefing.add_argument("--cliente", required=True, help="Código do cliente (cliente_id no arquivo de origem).")

    p_nota = sub.add_parser("nota", help="Registra uma nota pessoal (só sua) sobre um cliente ou operação.")
    p_nota.add_argument("--cliente", required=True, help="Código do cliente.")
    p_nota.add_argument("--operacao", default=None, help="Referência da operação (operacao_id), opcional.")
    p_nota.add_argument("--texto", required=True, help="Texto da nota.")

    sub.add_parser("backup-db", help="Copia o arquivo .db atual para o diretório de backups, com timestamp.")

    return parser


def main():
    parser = montar_parser()
    args = parser.parse_args()
    cfg = carregar_settings()

    comandos = {
        "init-db": cmd_init_db,
        "importar": cmd_importar,
        "hoje": cmd_hoje,
        "revisar": cmd_revisar,
        "exportar": cmd_exportar,
        "briefing": cmd_briefing,
        "nota": cmd_nota,
        "backup-db": cmd_backup_db,
    }
    comandos[args.comando](args, cfg)


if __name__ == "__main__":
    main()
