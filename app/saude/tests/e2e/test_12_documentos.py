"""Fluxo de documentos e anexos do prontuário (modo 2).

O médico emite o documento em dois passos — escolhe o tipo e depois preenche a data e o texto
com o editor rico — e o prontuário passa a oferecer a visualização do documento emitido. Os
anexos seguem o mesmo ciclo (cadastrar, editar, excluir) com arquivo. O ciclo é exercitado
pelos ícones da própria tabela, que é onde o produto oferece cada ação.

A pré-visualização do documento fica dispensada: é um POST por AJAX que abre um blob de PDF
numa janela nova, sem tela persistente para asserir.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRONTUARIO = '/saude/prontuario/{}/'
ADICIONAR_DOCUMENTO = '/saude/adicionar_documento_prontuario/{}/'
PREENCHER_DOCUMENTO = '/saude/preencher_documento_prontuario/{}/{}/'
IMPRIMIR_DOCUMENTO = '/saude/imprimir_documento_prontuario/{}/'
EXCLUIR_DOCUMENTO = '/saude/excluir_documento_prontuario/{}/'
ADICIONAR_ANEXO = '/saude/adicionar_anexo_prontuario/{}/'
EDITAR_ANEXO = '/saude/editar_anexo_prontuario/{}/'
EXCLUIR_ANEXO = '/saude/excluir_anexo_prontuario/{}/'

TEXTO_ATESTADO = 'Atesto que o aluno esteve sob cuidados E2E.'
TIPO_ATESTADO = 0


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def test_documento_do_prontuario_emitido_e_excluido(logado_saude: Callable[[str], Page]) -> None:
    """O médico emite um atestado, vê o documento emitido e depois o exclui."""
    tela = Tela(logado_saude('medico'))

    from saude.models import DocumentoProntuario

    _aluno, prontuario = _aluno_e_prontuario()
    vinculo = prontuario.vinculo
    tela.ir(PRONTUARIO.format(vinculo.pk)).ver_titulo('Prontuário').clicar_aba('Documentos')
    tela.aba('Documentos').clicar_botao('Adicionar Documento')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_DOCUMENTO.format(vinculo.pk)}$'))
    tela.preencher('Tipo do Documento', 'Lista', 'Atestado')
    tela.clicar_botao('Continuar >>')
    expect(tela.pagina).to_have_url(re.compile(rf'{PREENCHER_DOCUMENTO.format(vinculo.pk, TIPO_ATESTADO)}$'))

    # O texto vem pré-preenchido pela view com o nome do paciente; o teste troca por um texto
    # próprio para afirmar a persistência sem depender do modelo do produto.
    tela.preencher('Data', 'Data', '21/01/2019')
    tela.preencher('Texto', 'Texto rico', TEXTO_ATESTADO)
    tela.clicar_botao('Salvar').sucesso('Documento cadastrado com sucesso.')
    documento = DocumentoProntuario.objects.get(prontuario=prontuario, tipo=DocumentoProntuario.ATESTADO)
    assert TEXTO_ATESTADO in documento.texto, 'a UI disse que salvou, mas o texto do documento não persistiu'
    assert documento.cadastrado_por_vinculo is not None, 'o documento precisa registrar quem o emitiu'

    # "Ver documento" é o mesmo template de impressão renderizado na tela (em teste o decorator
    # `@documento` devolve o HTML, sem converter para PDF).
    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Documentos')
    expect(tela.aba('Documentos').linha('Atestado').botao('Ver documento')).to_have_attribute('href', IMPRIMIR_DOCUMENTO.format(documento.pk))
    tela.aba('Documentos').linha('Atestado').clicar_botao('Ver documento')
    expect(tela.pagina).to_have_url(re.compile(rf'{IMPRIMIR_DOCUMENTO.format(documento.pk)}$'))
    tela.ver_texto(TEXTO_ATESTADO)

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Documentos')
    tela.aba('Documentos').linha('Atestado').clicar_icone('remoção')
    tela.sucesso('Documento excluído com sucesso.')
    assert not DocumentoProntuario.objects.filter(pk=documento.pk).exists(), 'a UI disse que excluiu, mas o documento permanece'


def test_anexo_do_prontuario_ciclo_completo(logado_saude: Callable[[str], Page]) -> None:
    """O médico anexa um arquivo ao prontuário, edita a descrição e o exclui."""
    tela = Tela(logado_saude('medico'))

    from saude.models import AnexoProntuario

    _aluno, prontuario = _aluno_e_prontuario()
    vinculo = prontuario.vinculo
    tela.ir(PRONTUARIO.format(vinculo.pk)).ver_titulo('Prontuário').clicar_aba('Anexos')
    tela.aba('Anexos').clicar_botao('Adicionar Anexo')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ANEXO.format(vinculo.pk)}$'))
    tela.preencher_formulario([('Descrição', 'Texto', 'Anexo E2E'), ('Arquivo', 'Arquivo', 'arquivo.pdf')])
    tela.clicar_botao('Salvar').sucesso('Anexo cadastrado com sucesso.')
    anexo = AnexoProntuario.objects.get(prontuario=prontuario, descricao='Anexo E2E')
    assert anexo.cadastrado_por is not None, 'o anexo precisa registrar quem o cadastrou'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Anexos')
    expect(tela.aba('Anexos').linha('Anexo E2E').loc('//a[contains(@class, "icon-edit")]')).to_have_attribute('href', EDITAR_ANEXO.format(anexo.pk))
    tela.aba('Anexos').linha('Anexo E2E').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_ANEXO.format(anexo.pk)}$'))
    tela.preencher('Descrição', 'Texto', 'Anexo E2E revisado')
    tela.clicar_botao('Salvar').sucesso('Anexo editado com sucesso.')
    anexo.refresh_from_db()
    assert anexo.descricao == 'Anexo E2E revisado', 'a UI disse que editou, mas a descrição do anexo não mudou'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Anexos')
    expect(tela.aba('Anexos').linha('Anexo E2E revisado').loc('//a[contains(@class, "icon-delete")]')).to_have_attribute(
        'href', EXCLUIR_ANEXO.format(anexo.pk)
    )
    tela.aba('Anexos').linha('Anexo E2E revisado').clicar_icone('remoção')
    tela.sucesso('Anexo excluído com sucesso.')
    assert not AnexoProntuario.objects.filter(pk=anexo.pk).exists(), 'a UI disse que excluiu, mas o anexo permanece'
