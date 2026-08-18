from app.security import decodificar_token_sessao, gerar_token_sessao, hash_senha, verificar_senha


def test_hash_e_verificacao_de_senha():
    hash_ = hash_senha("minha-senha-123")
    assert hash_ != "minha-senha-123"
    assert verificar_senha("minha-senha-123", hash_) is True
    assert verificar_senha("senha-errada", hash_) is False


def test_token_de_sessao_roundtrip():
    token = gerar_token_sessao(usuario_id=42)
    assert decodificar_token_sessao(token) == 42


def test_token_invalido_retorna_none():
    assert decodificar_token_sessao("token-invalido") is None
