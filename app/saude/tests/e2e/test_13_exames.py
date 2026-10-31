"""Fluxo dos exames complementares do prontuário: laboratoriais e de imagem (modo 2).

O médico registra o exame laboratorial em dois passos — a categoria e a data, e depois os
valores de cada tipo de exame da categoria —, consulta os valores de referência e percorre o
ciclo de ver, editar e excluir pela lista de exames. O exame de imagem segue o mesmo ciclo num
formulário único. Os ícones de cada linha são o único ponto de entrada das ações.
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
ADICIONAR_LABORATORIAL = '/saude/adicionar_exame_laboratorial/{}/'
ADICIONAR_VALORES = '/saude/adicionar_valores_exame_laboratorial/{}/'
VER_LABORATORIAL = '/saude/ver_exame_laboratorial/{}/'
EDITAR_LABORATORIAL = '/saude/editar_exame_laboratorial/{}/'
EXCLUIR_LABORATORIAL = '/saude/excluir_exame_laboratorial/{}/'
VALORES_REFERENCIA = '/saude/exame_laboratorial_valores_referencia/'
ADICIONAR_IMAGEM = '/saude/adicionar_exame_imagem/{}/'
VER_IMAGEM = '/saude/ver_exame_imagem/{}/'
EDITAR_IMAGEM = '/saude/editar_exame_imagem/{}/'
EXCLUIR_IMAGEM = '/saude/excluir_exame_imagem/{}/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _abrir_lista_de_exames(tela: Tela) -> Tela:
    """Expande o quadro "Lista de exames", que o produto renderiza recolhido.

    Os ícones de ver/editar/excluir vivem dentro dele — recolhido, o Playwright não os
    considera visíveis.
    """
    tela.clicar_botao('Lista de exames')
    return tela


def test_exame_laboratorial_completo(logado_saude: Callable[[str], Page]) -> None:
    """O médico registra o exame e seus valores, vê, edita e exclui pela lista de exames."""
    tela = Tela(logado_saude('medico'))

    from saude.models import ExameLaboratorial, ValorExameLaboratorial

    _aluno, prontuario = _aluno_e_prontuario()
    vinculo = prontuario.vinculo
    tela.ir(PRONTUARIO.format(vinculo.pk)).ver_titulo('Prontuário').clicar_aba('Exames laboratoriais')
    tela.aba('Exames laboratoriais').clicar_botao('Exame')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_LABORATORIAL.format(prontuario.pk)}$'))
    tela.preencher_formulario(
        [
            ('Categoria', 'Autocomplete', 'Perfil Glicêmico'),
            ('Data de Realização', 'Data', '21/01/2019'),
            ('Observação', 'TextArea', 'Exame laboratorial E2E'),
        ]
    )
    tela.clicar_botao('Continuar >>')
    exame = ExameLaboratorial.objects.get(prontuario=prontuario, observacao='Exame laboratorial E2E')

    # Com tipo de exame cadastrado na categoria, o produto encadeia para os valores.
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_VALORES.format(exame.pk)}\?url='))
    tela.sucesso('Exame registrado com sucesso. Preencha os valores do exame.')
    tela.preencher('Glicemia de jejum (mg/dL)', 'Texto', '92')
    tela.clicar_botao('Enviar').sucesso('Exame registrado com sucesso.')
    valor = ValorExameLaboratorial.objects.get(exame=exame)
    assert valor.valor == '92', 'a UI disse que salvou, mas o valor do exame não persistiu'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames laboratoriais')
    tela.aba('Exames laboratoriais').clicar_botao('Valores de referência')
    tela.popup().ver_texto('Glicemia de jejum').ver_texto('Valores de Referência dos Exames Laboratoriais')

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames laboratoriais')
    _abrir_lista_de_exames(tela)
    expect(tela.aba('Exames laboratoriais').linha('Perfil Glicêmico').loc('//a[contains(@class, "icon-view")]')).to_have_attribute(
        'href', VER_LABORATORIAL.format(exame.pk)
    )
    tela.aba('Exames laboratoriais').linha('Perfil Glicêmico').clicar_icone('exibição')
    expect(tela.pagina).to_have_url(re.compile(rf'{VER_LABORATORIAL.format(exame.pk)}$'))
    tela.ver_titulo('Exame Laboratorial').ver_texto('Glicemia de jejum')

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames laboratoriais')
    _abrir_lista_de_exames(tela)
    tela.aba('Exames laboratoriais').linha('Perfil Glicêmico').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_LABORATORIAL.format(exame.pk)}$'))
    tela.preencher_formulario([('Observação', 'TextArea', 'Exame laboratorial E2E revisado'), ('Glicemia de jejum (mg/dL)', 'Texto', '101')])
    tela.clicar_botao('Salvar').sucesso('Exame alterado com sucesso.')
    exame.refresh_from_db()
    assert exame.observacao == 'Exame laboratorial E2E revisado', 'a UI disse que editou, mas a observação não mudou'
    valor.refresh_from_db()
    assert valor.valor == '101', 'a UI disse que editou, mas o valor do exame não mudou'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames laboratoriais')
    _abrir_lista_de_exames(tela)
    expect(tela.aba('Exames laboratoriais').linha('Perfil Glicêmico').loc('//a[contains(@class, "icon-delete")]')).to_have_attribute(
        'href', EXCLUIR_LABORATORIAL.format(exame.pk)
    )
    tela.aba('Exames laboratoriais').linha('Perfil Glicêmico').clicar_icone('remoção')
    tela.sucesso('Exame alterado com sucesso.')
    assert not ExameLaboratorial.objects.filter(pk=exame.pk).exists(), 'a UI disse que excluiu, mas o exame permanece'


def test_exame_de_imagem_ciclo_completo(logado_saude: Callable[[str], Page]) -> None:
    """O médico registra o exame de imagem, vê, edita e exclui pela lista do prontuário."""
    tela = Tela(logado_saude('medico'))

    from saude.models import ExameImagem

    _aluno, prontuario = _aluno_e_prontuario()
    vinculo = prontuario.vinculo
    tela.ir(PRONTUARIO.format(vinculo.pk)).ver_titulo('Prontuário').clicar_aba('Exames de Imagem')
    tela.aba('Exames de Imagem').clicar_botao('Adicionar Exame')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_IMAGEM.format(prontuario.pk)}$'))
    tela.preencher_formulario(
        [
            ('Nome', 'Texto', 'Radiografia E2E'),
            ('Data de Realização', 'Data', '21/01/2019'),
            ('Resultado', 'TextArea', 'Sem alterações'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Exame registrado com sucesso.')
    exame = ExameImagem.objects.get(prontuario=prontuario, nome='Radiografia E2E')
    assert exame.resultado == 'Sem alterações', 'a UI disse que salvou, mas o resultado do exame não persistiu'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames de Imagem')
    expect(tela.aba('Exames de Imagem').linha('Radiografia E2E').loc('//a[contains(@class, "icon-view")]')).to_have_attribute(
        'href', VER_IMAGEM.format(exame.pk)
    )
    tela.aba('Exames de Imagem').linha('Radiografia E2E').clicar_icone('exibição')
    expect(tela.pagina).to_have_url(re.compile(rf'{VER_IMAGEM.format(exame.pk)}$'))
    tela.ver_titulo('Exame de Imagem').ver_texto('Sem alterações')

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames de Imagem')
    expect(tela.aba('Exames de Imagem').linha('Radiografia E2E').loc('//a[contains(@class, "icon-edit")]')).to_have_attribute(
        'href', EDITAR_IMAGEM.format(exame.pk)
    )
    tela.aba('Exames de Imagem').linha('Radiografia E2E').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_IMAGEM.format(exame.pk)}$'))
    tela.preencher('Resultado', 'TextArea', 'Resultado revisado E2E')
    tela.clicar_botao('Salvar').sucesso('Exame alterado com sucesso.')
    exame.refresh_from_db()
    assert exame.resultado == 'Resultado revisado E2E', 'a UI disse que editou, mas o resultado não mudou'

    tela.ir(PRONTUARIO.format(vinculo.pk)).clicar_aba('Exames de Imagem')
    expect(tela.aba('Exames de Imagem').linha('Radiografia E2E').loc('//a[contains(@class, "icon-delete")]')).to_have_attribute(
        'href', EXCLUIR_IMAGEM.format(exame.pk)
    )
    tela.aba('Exames de Imagem').linha('Radiografia E2E').clicar_icone('remoção')
    tela.sucesso('Exame alterado com sucesso.')
    assert not ExameImagem.objects.filter(pk=exame.pk).exists(), 'a UI disse que excluiu, mas o exame de imagem permanece'
