import pytest

from app.services.orbit_parsing import ErroEstrutural, ler_linhas_brutas, mapear_e_validar

MAPEAMENTO = {
    "cliente_nome": "Nome Cliente",
    "cliente_codigo": "Codigo Cliente",
    "operacao_ref": "Numero Operacao",
    "tipo_estrutura": "Produto",
    "ativo_principal": "Ativo Referencia",
    "notional": "Notional",
    "data_inicio": "Data Operacao",
    "data_vencimento": "Data Vencimento",
    "valor_entrada": "Valor Investido",
    "barreira_1_nivel": "Barreira Nivel",
    "barreira_1_tipo": "Barreira Tipo",
    "barreira_1_regra_observacao": "Barreira Regra",
    "fixing_1_data": "Data Fixing",
    "fixing_1_tipo": "Tipo Fixing",
    "preco_ativo": "Preco Atual",
    "preco_data": "Data Preco",
}

CABECALHO = (
    "Codigo Cliente,Nome Cliente,Numero Operacao,Produto,Ativo Referencia,Notional,"
    "Data Operacao,Data Vencimento,Valor Investido,Barreira Nivel,Barreira Tipo,"
    "Barreira Regra,Data Fixing,Tipo Fixing,Preco Atual,Data Preco\n"
)


def _csv(linhas: str) -> bytes:
    return (CABECALHO + linhas).encode("utf-8")


def test_arquivo_vazio_e_erro_estrutural():
    with pytest.raises(ErroEstrutural):
        ler_linhas_brutas(b"", "arquivo.csv")


def test_extensao_nao_suportada_e_erro_estrutural():
    with pytest.raises(ErroEstrutural):
        ler_linhas_brutas(b"qualquer coisa", "arquivo.txt")


def test_linha_valida_e_processada():
    conteudo = _csv(
        "CLI1,Fulano,OP-1,capital_protegido,PETR4,\"500000,00\","
        "18/08/2026,18/08/2027,\"500000,00\",\"32,50\",protecao,fechamento,,,\"33,20\",18/08/2026\n"
    )
    linhas_brutas = ler_linhas_brutas(conteudo, "arquivo.csv")
    resultado = mapear_e_validar(linhas_brutas, MAPEAMENTO, "%d/%m/%Y", ",")

    assert len(resultado.linhas) == 1
    assert not resultado.erros
    dados = resultado.linhas[0].dados
    assert dados["cliente_nome"] == "Fulano"
    assert dados["operacao_ref"] == "OP-1"
    assert dados["notional"] == 500000.00
    assert dados["barreira_1_nivel"] == 32.50
    assert dados["preco_ativo"] == 33.20


def test_linha_sem_campo_obrigatorio_vira_erro_de_linha_sem_abortar():
    conteudo = _csv(
        "CLI1,,OP-1,capital_protegido,PETR4,,18/08/2026,18/08/2027,,,,,,,,\n"
        "CLI2,Beltrano,OP-2,autocall,VALE3,,18/08/2026,18/08/2027,,,,,,,,\n"
    )
    linhas_brutas = ler_linhas_brutas(conteudo, "arquivo.csv")
    resultado = mapear_e_validar(linhas_brutas, MAPEAMENTO, "%d/%m/%Y", ",")

    assert len(resultado.linhas) == 1
    assert resultado.linhas[0].dados["operacao_ref"] == "OP-2"
    assert len(resultado.erros) == 1
    assert resultado.erros[0].numero_linha == 2


def test_coluna_obrigatoria_ausente_no_arquivo_e_erro_estrutural():
    conteudo = b"Coluna Qualquer\nvalor\n"
    linhas_brutas = ler_linhas_brutas(conteudo, "arquivo.csv")
    with pytest.raises(ErroEstrutural):
        mapear_e_validar(linhas_brutas, MAPEAMENTO, "%d/%m/%Y", ",")


def test_campo_opcional_invalido_vira_aviso_nao_erro():
    conteudo = _csv(
        "CLI1,Fulano,OP-1,capital_protegido,PETR4,não-é-numero,"
        "18/08/2026,18/08/2027,,,,,,,,\n"
    )
    linhas_brutas = ler_linhas_brutas(conteudo, "arquivo.csv")
    resultado = mapear_e_validar(linhas_brutas, MAPEAMENTO, "%d/%m/%Y", ",")

    assert len(resultado.linhas) == 1
    assert resultado.linhas[0].dados["notional"] is None
    assert resultado.linhas[0].avisos
