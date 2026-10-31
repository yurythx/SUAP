from types import SimpleNamespace
from unittest.mock import MagicMock

from documento_eletronico.models import Documento, DocumentoDigitalizadoAnexoSimples, DocumentoTexto


def _criar_anexo(documento_pai: object, **atributos: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        get_vinculo_documento_texto=lambda: SimpleNamespace(documento=documento_pai),
        **atributos,
    )


def test_anexo_simples_publico_respeita_permissao_do_documento_pai() -> None:
    documento_pai = MagicMock()
    documento_pai.pode_ler.return_value = True
    anexo = _criar_anexo(
        documento_pai,
        nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
        eh_publico=True,
    )
    usuario = MagicMock()

    pode_ler = DocumentoDigitalizadoAnexoSimples.pode_ler(anexo, user=usuario)

    assert pode_ler is True
    documento_pai.pode_ler.assert_called_once_with(usuario, None, False, False)


def test_anexo_simples_restrito_nao_aparece_na_consulta_publica() -> None:
    documento_pai = MagicMock()
    documento_pai.pode_ler.return_value = True
    anexo = _criar_anexo(
        documento_pai,
        nivel_acesso=Documento.NIVEL_ACESSO_RESTRITO,
        eh_publico=False,
    )
    usuario = MagicMock()

    pode_ler = DocumentoDigitalizadoAnexoSimples.pode_ler(anexo, user=usuario, eh_consulta_publica=True)

    assert pode_ler is False
    documento_pai.pode_ler.assert_called_once_with(usuario, None, False, True)


def test_anexo_simples_sigiloso_exige_permissao_propria() -> None:
    documento_pai = MagicMock()
    documento_pai.pode_ler.return_value = True
    usuario = MagicMock()
    compartilhamento = MagicMock()
    compartilhamento.filter.return_value.exists.return_value = False
    anexo = _criar_anexo(
        documento_pai,
        nivel_acesso=Documento.NIVEL_ACESSO_SIGILOSO,
        eh_publico=False,
        eh_restrito=False,
        usuario_criacao=MagicMock(),
        compartilhamento_pessoa_documento_digitalizado=compartilhamento,
    )

    pode_ler = DocumentoDigitalizadoAnexoSimples.pode_ler(anexo, user=usuario)

    assert pode_ler is False


def test_anexo_simples_pode_alterar_nivel_quando_usuario_pode_editar_documento_pai() -> None:
    usuario = MagicMock()
    documento_pai = MagicMock()
    documento_pai.tem_permissao_editar.return_value = True
    anexo = _criar_anexo(documento_pai)

    pode_alterar = DocumentoDigitalizadoAnexoSimples.pode_alterar_nivel_acesso(anexo, user=usuario)

    assert pode_alterar is True
    documento_pai.tem_permissao_editar.assert_called_once_with(usuario)


def test_documento_texto_anexo_pode_alterar_nivel_quando_usuario_pode_editar_documento_pai() -> None:
    usuario = MagicMock()
    documento_pai = MagicMock()
    documento_pai.tem_permissao_editar.return_value = True
    documento_anexo = SimpleNamespace(
        get_vinculo_documento_texto_anexado=lambda: SimpleNamespace(documento=documento_pai),
    )

    pode_alterar = DocumentoTexto.pode_alterar_nivel_acesso_como_anexo(documento_anexo, user=usuario)

    assert pode_alterar is True
    documento_pai.tem_permissao_editar.assert_called_once_with(usuario)
