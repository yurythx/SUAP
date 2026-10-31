"""Tarefa 1 — configurar a diretoria acadêmica e distribuir os perfis do campus.

Primeiro elo da cadeia do ``edu``: sem diretoria não há curso, turma nem matrícula, e é
pela ficha da diretoria que o Administrador Acadêmico atribui TODOS os papéis do módulo.
As nove "Vincular <papel>" da funcionalidade 001 são uma tarefa só, com o mesmo popup em
cada aba — documentá-las separadas seria nove vezes o mesmo passo a passo.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'

LISTAGEM = '/admin/edu/diretoria/'


def test_cadastrar_diretoria(logado_edu, setor_livre, capturar):
    """Etapa 1 — o setor existente vira diretoria acadêmica."""
    from edu.models import Diretoria

    sigla = setor_livre()
    tela = Tela(logado_edu('admin_academico')).ir(LISTAGEM)
    tela.ver_titulo('Diretorias Acadêmicas')
    anotar('diretoria-listagem', tela)
    capturar(tela.pagina, 'diretoria-listagem')

    tela.clicar_botao('Adicionar Diretoria Acadêmica')
    tela.esperar()
    anotar('diretoria-formulario', tela)
    tela.preencher_formulario(
        [
            ('Setor', 'autocomplete', sigla),
            ('Autoridade Máxima (M)', 'texto', 'Reitor'),
            ('Autoridade Máxima (F)', 'texto', 'Reitora'),
            ('Responsável pela Diretoria (M)', 'texto', 'Diretor Acadêmico'),
            ('Responsável pela Diretoria (F)', 'texto', 'Diretora Acadêmica'),
        ]
    )
    capturar(tela.pagina, 'diretoria-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert Diretoria.objects.filter(setor__sigla=sigla).exists(), 'a UI disse que salvou, mas não persistiu'


def test_vincular_perfis_da_diretoria(logado_edu, grupo_temporario, capturar):
    """Etapa 2 — a ficha da diretoria e o popup que atribui um papel a um servidor.

    Um papel só é navegado (Diretor Geral, aba "Direção"): os outros oito usam exatamente o
    mesmo popup em outra aba, e a doc os lista numa tabela em vez de repetir o passo a passo.
    """
    from edu.models import Diretoria

    diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
    vinculos = grupo_temporario('Diretor Geral')

    tela = Tela(logado_edu('admin_academico')).ir(f'/edu/diretoria/{diretoria.pk}/')
    anotar('diretoria-ficha', tela)
    capturar(tela.pagina, 'diretoria-ficha')

    # As sete abas, uma a uma: a tabela "onde encontrar cada perfil" da doc sai daqui. Sem
    # clicar, os botões de cada painel existem no DOM mas em aba oculta, e o despejo não
    # diria a QUAL aba cada "Adicionar <perfil>" pertence.
    for aba in (
        'Direção',
        'Coordenação Acadêmica',
        'Secretaria Acadêmica',
        'Formatura/Diplomas',
        'Atividades Extensão',
        'Ensino a Distância',
        'Outras Atividades',
    ):
        tela.clicar_aba(aba)
        tela.esperar()
        anotar(f'diretoria-aba-{aba}', tela.aba(aba))

    tela.clicar_aba('Direção')
    tela.esperar()
    capturar(tela.pagina, 'diretoria-direcao')
    tela.clicar_botao('Adicionar Diretor Geral')
    popup = tela.popup()
    anotar('diretoria-popup-vinculo', popup)
    capturar(tela.pagina, 'diretoria-vinculo')
    popup.preencher('Usuário', 'autocomplete', '100007')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Usuário adicionado com sucesso.')
    assert vinculos.filter(setor=diretoria.setor).exists(), 'vínculo de Diretor Geral não gravado no setor da diretoria'


def test_responsavel_pela_emissao_de_diploma(logado_edu, grupo_temporario, capturar):
    """A aba "Formatura/Diplomas" pede mais que o usuário: cobra o número da portaria."""
    from edu.models import CoordenadorRegistroAcademico, Diretoria

    diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
    grupo_temporario('Coordenador de Registros Acadêmicos')
    coordenadores = CoordenadorRegistroAcademico.objects.filter(diretoria=diretoria, servidor__matricula='100007')
    try:
        tela = Tela(logado_edu('admin_academico')).ir(f'/edu/diretoria/{diretoria.pk}/')
        tela.clicar_aba('Formatura/Diplomas')
        anotar('diretoria-aba-formatura', tela)
        tela.clicar_botao('Adicionar Coordenador de Registros Acadêmicos')
        popup = tela.popup()
        anotar('diretoria-popup-portaria', popup)
        popup.preencher('Servidor', 'autocomplete', '100007')
        popup.preencher('Número da Portaria', 'texto', '123/2019')
        capturar(tela.pagina, 'diretoria-portaria')
        popup.salvar_no_popup('Salvar')

        tela.sucesso('Responsável pela Emissão do Diploma cadastrado/atualizado com sucesso.')
        assert coordenadores.exists(), 'responsável pela emissão do diploma não persistido'
    finally:
        coordenadores.delete()
