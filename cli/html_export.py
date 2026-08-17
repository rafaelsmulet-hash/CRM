"""Gera um snapshot estático em HTML do painel `jarvis hoje`.

Arquivo único, autocontido (CSS embutido, sem fontes/scripts externos) —
abre em qualquer navegador via duplo-clique, mesmo numa máquina 100%
offline. Não é um servidor: cada `jarvis hoje --html arquivo.html` gera um
retrato estático do momento da execução, para revisão visual apenas —
nenhuma ação de negócio acontece aqui.
"""
import html as _html

_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f5f6f8; --card-bg: #ffffff; --texto: #1c1e21; --texto-suave: #5f6368;
  --borda: #e3e5e8; --accent: #2f5fd6; --alerta: #b3410c; --ok: #1a7f4e;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #14161a; --card-bg: #1e2126; --texto: #eceff1; --texto-suave: #9aa0a6;
          --borda: #2c2f36; --accent: #7aa2ff; --alerta: #ff8a5c; --ok: #4fd68f; }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.5rem 4rem; background: var(--bg); color: var(--texto);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
.subtitulo { color: var(--texto-suave); margin: 0 0 .5rem; font-size: .9rem; }
.aviso-escopo {
  background: var(--card-bg); border: 1px solid var(--borda); border-left: 4px solid var(--accent);
  border-radius: 6px; padding: .75rem 1rem; margin: 1rem 0 1.5rem; font-size: .85rem; color: var(--texto-suave);
}
main { max-width: 900px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .75rem; margin-bottom: 1.5rem; }
.stat { background: var(--card-bg); border: 1px solid var(--borda); border-radius: 10px; padding: 1rem; }
.stat .n { font-size: 1.8rem; font-weight: 700; }
.stat .rotulo { color: var(--texto-suave); font-size: .8rem; }
section { background: var(--card-bg); border: 1px solid var(--borda); border-radius: 10px;
          padding: 1rem 1.25rem; margin-bottom: 1rem; }
section h2 { font-size: 1rem; margin: 0 0 .75rem; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th, td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid var(--borda); }
th { color: var(--texto-suave); font-weight: 600; font-size: .78rem; text-transform: uppercase; }
tr:last-child td { border-bottom: none; }
.vazio { color: var(--texto-suave); font-size: .85rem; padding: .25rem 0; }
.tag { display: inline-block; padding: .1rem .5rem; border-radius: 999px; font-size: .75rem; font-weight: 600; }
.tag.alerta { background: color-mix(in srgb, var(--alerta) 18%, transparent); color: var(--alerta); }
.tag.ok { background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); }
footer { max-width: 900px; margin: 1.5rem auto 0; font-size: .75rem; color: var(--texto-suave); }
"""


def _esc(valor) -> str:
    return _html.escape(str(valor if valor is not None else ""))


def _tabela(cabecalhos: list[str], linhas: list[list[str]]) -> str:
    if not linhas:
        return '<p class="vazio">Nenhum item.</p>'
    th = "".join(f"<th>{_esc(c)}</th>" for c in cabecalhos)
    corpo = "".join(
        "<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in linha) + "</tr>"
        for linha in linhas
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>"


def gerar_html_painel(dados: dict) -> str:
    """`dados` é o dict produzido por cli/main.py::_montar_dados_hoje."""
    vencimentos = _tabela(
        ["Cliente", "Código", "Estrutura", "Ativo", "Vence em", "Dias"],
        [[v["cliente_nome"], v["cliente_codigo"], v["tipo_estrutura"], v["ativo_objeto"],
          v["data_vencimento"], v["dias_restantes"]] for v in dados["vencimentos_proximos"]],
    )
    barreiras = _tabela(
        ["Cliente", "Código", "Estrutura", "Ativo", "Status barreira"],
        [[b["cliente_nome"], b["cliente_codigo"], b["tipo_estrutura"], b["ativo_objeto"],
          b["status_barreira"]] for b in dados["barreiras_tocadas"]],
    )
    sem_contato = _tabela(
        ["Cliente", "Código", "Dias desde último fechamento"],
        [[c["cliente_nome"], c["cliente_codigo"], c["dias_desde_ultimo_fechamento"]]
         for c in dados["clientes_sem_contato"]],
    )

    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jarvis — Painel do dia {_esc(dados['data'])}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>Painel do dia — Jarvis</h1>
  <p class="subtitulo">{_esc(dados['data'])} — gerado localmente, sem envio de dados a nenhum servidor</p>
  <div class="aviso-escopo">
    Rascunho pessoal de produtividade. Read-only em relação à operação — nunca substitui o CRM oficial.
    Nenhuma ação de negócio real acontece aqui.
  </div>

  <div class="grid">
    <div class="stat"><div class="n">{dados['pendentes']}</div><div class="rotulo">Rascunhos pendentes de revisão</div></div>
    <div class="stat"><div class="n">{len(dados['vencimentos_proximos'])}</div><div class="rotulo">Vencimentos em até {dados['janela_vencimento_dias']} dia(s)</div></div>
    <div class="stat"><div class="n">{len(dados['barreiras_tocadas'])}</div><div class="rotulo">Barreiras tocadas</div></div>
    <div class="stat"><div class="n">{len(dados['clientes_sem_contato'])}</div><div class="rotulo">Sem atividade há mais de {dados['janela_sem_contato_dias']}d</div></div>
  </div>

  <section>
    <h2>Vencimentos próximos</h2>
    {vencimentos}
  </section>

  <section>
    <h2>Barreiras tocadas</h2>
    {barreiras}
  </section>

  <section>
    <h2>Clientes sem sinal de atividade <span class="tag alerta">proxy interno</span></h2>
    <p class="vazio">Dias desde a data_fechamento mais recente entre operações ativas — NÃO é o registro oficial de contato do CRM.</p>
    {sem_contato}
  </section>
</main>
<footer>Gerado por Jarvis · arquivo estático local · abra novamente com <code>jarvis hoje --html arquivo.html</code> para atualizar.</footer>
</body>
</html>
"""
