"""Capturas das tarefas de alteração de nível de acesso.

As imagens são geradas por ``pytest -m doc`` e não fazem parte do repositório.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/documento_eletronico/documentotexto/'
VISUALIZACAO = '/documento_eletronico/visualizar_documento/{documento_id}/'

Logado = Callable[[str], Page]
Capturar = Callable[..., object]


def _documento_id() -> int:
    """Obtém o documento preparado pela fixture compartilhada do módulo."""
    from documento_eletronico.models import DocumentoTexto

    return DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ').pk


def _capturar(tela: Tela, capturar: Capturar, titulo: str, slug: str) -> None:
    """Anota e captura uma tela documental."""
    anotar_tela(titulo, tela)
    capturar(tela.pagina, slug)


def _abrir_documento(logado: Logado, capturar: Capturar, papel: str, prefixo: str | None = None) -> Tela:
    """Navega pela listagem real até o documento-alvo."""
    tela = Tela(logado(papel)).ir(LISTAGEM)
    if prefixo:
        _capturar(tela, capturar, f'{prefixo}-lista', f'nivel-acesso-{prefixo}-lista')
    tela.linha('DIDE/CEN').clicar_icone().ver_titulo('Documento')
    if prefixo:
        _capturar(tela, capturar, f'{prefixo}-documento', f'nivel-acesso-{prefixo}-documento')
    return tela


def _preencher_senha(tela: Tela) -> Tela:
    """Preenche a senha de confirmação da janela de alteração."""
    tela.raiz.locator('input[type="password"]').first.fill(SENHA_E2E)
    return tela


def _solicitar(tela: Tela, hipotese: object) -> None:
    """Executa a solicitação pela tela de alteração de nível."""
    tela.clicar_botao('Nível de acesso').clicar_botao('Solicitar alteração de nível de acesso')
    tela.preencher('Para', 'lista', 'Restrito')
    tela.raiz.locator('#id_hipotese_legal option').nth(1).wait_for(state='attached')
    tela.raiz.locator('#id_hipotese_legal').select_option(index=1)
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Solicitação realizada com sucesso com sucesso.')


def test_alterando_nivel_de_acesso(logado_documento: Logado, capturar: Capturar) -> None:
    """Captura a alteração direta feita pelo chefe do setor."""
    from documento_eletronico.models import HipoteseLegal

    from documento_eletronico.models import DocumentoTexto
    from documento_eletronico.status import DocumentoStatus

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    DocumentoTexto.objects.filter(pk=documento.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)
    hipotese = HipoteseLegal.objects.filter(nivel_acesso='SIGILOSO').first()
    if hipotese is None:
        pytest.fail('seed sem hipótese legal sigilosa; tentativa: consulta ao cadastro de HipoteseLegal')

    tela = _abrir_documento(logado_documento, capturar, 'chefe', 'alteracao')
    tela.clicar_botao('Nível de acesso').clicar_botao('Editar nível de acesso')
    tela.preencher('Para', 'lista', 'Sigiloso')
    tela.raiz.locator('#id_hipotese_legal option').nth(1).wait_for(state='attached')
    _capturar(tela, capturar, 'alteracao-formulario', 'nivel-acesso-alteracao-formulario')
    tela.preencher('Hipótese Legal', 'lista', str(hipotese))
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Nível de Acesso alterado com sucesso.')
    _capturar(tela, capturar, 'alteracao-sucesso', 'nivel-acesso-alteracao-sucesso')


def test_solicitacao_de_alteracao_de_nivel_de_acesso(logado_documento: Logado, capturar: Capturar) -> None:
    """Captura a solicitação feita pelo servidor sem poder de alteração direta."""
    from documento_eletronico.models import HipoteseLegal

    from documento_eletronico.models import DocumentoTexto
    from documento_eletronico.status import DocumentoStatus

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    DocumentoTexto.objects.filter(pk=documento.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)
    hipotese = HipoteseLegal.objects.filter(nivel_acesso='RESTRITO').first()
    if hipotese is None:
        pytest.fail('seed sem hipótese legal restrita; tentativa: consulta ao cadastro de HipoteseLegal')

    tela = _abrir_documento(logado_documento, capturar, 'gerente', 'solicitacao')
    tela.clicar_botao('Nível de acesso').clicar_botao('Solicitar alteração de nível de acesso')
    tela.preencher('Para', 'lista', 'Restrito')
    tela.raiz.locator('#id_hipotese_legal option').nth(1).wait_for(state='attached')
    _capturar(tela, capturar, 'solicitacao-formulario', 'nivel-acesso-solicitacao-formulario')
    tela.raiz.locator('#id_hipotese_legal').select_option(index=1)
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Solicitação realizada com sucesso com sucesso.')
    _capturar(tela, capturar, 'solicitacao-sucesso', 'nivel-acesso-solicitacao-sucesso')


def test_autorizacao_de_alteracao_de_nivel_de_acesso(logado_documento: Logado, capturar: Capturar) -> None:
    """Cria uma solicitação pela UI e captura sua análise e autorização."""
    from documento_eletronico.models import HipoteseLegal

    from documento_eletronico.models import DocumentoTexto
    from documento_eletronico.status import DocumentoStatus

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    DocumentoTexto.objects.filter(pk=documento.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)
    hipotese = HipoteseLegal.objects.filter(nivel_acesso='RESTRITO').first()
    if hipotese is None:
        pytest.fail('seed sem hipótese legal restrita; tentativa: consulta ao cadastro de HipoteseLegal')

    tela = _abrir_documento(logado_documento, capturar, 'gerente')
    _solicitar(tela, hipotese)

    tela = _abrir_documento(logado_documento, capturar, 'chefe', 'autorizacao')
    tela.clicar_botao('Nível de acesso').clicar_botao('Analisar/Visualizar solicitações de alteração de nível de acesso')
    tela.ver_titulo('Solicitações de alteração de nível de acesso de documento')
    _capturar(tela, capturar, 'autorizacao-solicitacoes', 'nivel-acesso-autorizacao-solicitacoes')
    tela.clicar_botao('Deferir').ver_titulo('Analisar solicitação de alteração de nível de acesso')
    _capturar(tela, capturar, 'autorizacao-formulario', 'nivel-acesso-autorizacao-formulario')
    tela.preencher_formulario([('Confirmar', 'checkbox', 'marcar')])
    _preencher_senha(tela).clicar_botao('Enviar').sucesso('Nível de Acesso alterado com sucesso.')
    _capturar(tela, capturar, 'autorizacao-sucesso', 'nivel-acesso-autorizacao-sucesso')
