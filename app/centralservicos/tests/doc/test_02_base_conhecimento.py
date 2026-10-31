"""Roteiro navegado das tarefas 4 e 5 da doc: a Base de Conhecimento.

Tarefa 4 — o contribuinte escreve um artigo (que nasce pendente de supervisão porque o grupo
dele não tem ``add_active_baseconhecimento``), o supervisor revisa e aprova, e publica um
segundo artigo como FAQ pública.

Tarefa 5 — o solicitante consulta a Base de Conhecimento pelo menu.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .conftest import AREA, ARTIGO, ARTIGO_PUBLICO, GRUPO_SERVICO, SERVICO

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

BASE_MENU = '/centralservicos/baseconhecimento/'


def test_escrever_e_aprovar_artigo(logado_doc, capturar):
    """Tarefa 4 — escrever o artigo, aprová-lo e publicá-lo como FAQ.

    O artigo do contribuinte é privado de propósito: privado é o que qualquer atendente usa na
    resolução, e é o único que o grupo dele (sem ``add_active_baseconhecimento``) consegue criar —
    ele nasce "Supervisão pendente" e o supervisor é quem aprova. Já o artigo público, que
    aparece para o solicitante, exige ``add_public_baseconhecimento`` e por isso é criado pelo
    supervisor.
    """
    from centralservicos.models import BaseConhecimento

    BaseConhecimento.objects.filter(titulo__in=[ARTIGO, ARTIGO_PUBLICO]).delete()

    tela = Tela(logado_doc('contribuinte')).ir(BASE_MENU)
    tela.ver_titulo('Listar Áreas de serviço')
    tela.clicar_link(AREA)
    tela.ver_titulo(f'Base de Conhecimentos: {AREA}')
    capturar(tela.pagina, '04-base-conhecimento-area')
    tela.clicar_botao('Adicionar Artigo')
    tela.ver_titulo('Adicionar Base de Conhecimento')
    anotar_tela('artigo-form', tela)
    tela.preencher_formulario(
        [
            ('Área do Serviço', 'autocomplete', AREA),
            ('Título', 'texto', ARTIGO),
            ('Resumo', 'textarea', 'A impressora indica atolamento de papel mesmo sem papel preso.'),
            ('Solução', 'texto rico', 'Verifique e remova o papel atolado da bandeja.'),
            ('Ativo?', 'checkbox', 'marcar'),
            ('Visibilidade', 'lista', 'Privada'),
            ('Restringir aos Serviços', 'filteredselectmultiple', f'{GRUPO_SERVICO} | {SERVICO}'),
        ]
    )
    capturar(tela.pagina, '04-artigo-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    pendente = BaseConhecimento.objects.filter(titulo=ARTIGO).first()
    assert pendente is not None, 'a UI disse que salvou, mas o artigo não existe'
    assert pendente.supervisao_pendente, 'o artigo do contribuinte deveria nascer pendente de supervisão'

    tela = Tela(logado_doc('supervisor')).ir(BASE_MENU)
    tela.clicar_link(AREA)
    tela.ver_titulo(f'Base de Conhecimentos: {AREA}')
    tela.clicar_link(ARTIGO)
    tela.ver_titulo(ARTIGO)
    capturar(tela.pagina, '04-artigo-supervisao-pendente')
    tela.clicar_botao('Aprovar alterações')
    tela.sucesso('Base de conhecimento revisada com sucesso.')
    pendente.refresh_from_db()
    assert not pendente.supervisao_pendente, 'a aprovação não limpou a supervisão pendente'

    tela.ir(BASE_MENU)
    tela.clicar_link(AREA)
    tela.clicar_botao('Adicionar Artigo')
    tela.ver_titulo('Adicionar Base de Conhecimento')
    tela.preencher_formulario(
        [
            ('Área do Serviço', 'autocomplete', AREA),
            ('Título', 'texto', ARTIGO_PUBLICO),
            ('Resumo', 'textarea', 'Passo a passo para digitalizar documentos no scanner do setor.'),
            ('Solução', 'texto rico', 'Abra o aplicativo do scanner, escolha Digitalizar e salve o arquivo.'),
            ('Ativo?', 'checkbox', 'marcar'),
            ('Visibilidade', 'lista', 'Pública'),
            ('Restringir aos Serviços', 'filteredselectmultiple', f'{GRUPO_SERVICO} | {SERVICO}'),
        ]
    )
    capturar(tela.pagina, '04-artigo-publico-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    publico = BaseConhecimento.objects.filter(titulo=ARTIGO_PUBLICO).first()
    assert publico is not None, 'a UI disse que salvou, mas o artigo público não existe'
    assert publico.visibilidade == 'publica', 'o artigo não foi gravado como público'
    assert not publico.supervisao_pendente, 'o supervisor tem add_active_baseconhecimento e não deveria ficar pendente'


def test_consultar_base_de_conhecimento(logado_doc, capturar):
    """Tarefa 5 — o solicitante consulta os artigos públicos da área."""
    tela = Tela(logado_doc('solicitante')).ir(BASE_MENU)
    tela.ver_titulo('Listar Áreas de serviço')
    capturar(tela.pagina, '05-areas-base-conhecimento')
    tela.clicar_link(AREA)
    tela.ver_titulo(f'Base de Conhecimentos: {AREA}')
    tela.ver_texto(ARTIGO_PUBLICO)
    capturar(tela.pagina, '05-base-conhecimento-area')
    tela.clicar_link(ARTIGO_PUBLICO)
    tela.ver_titulo(ARTIGO_PUBLICO)
    capturar(tela.pagina, '05-artigo-publico')

    from centralservicos.models import BaseConhecimento

    artigo = BaseConhecimento.objects.get(titulo=ARTIGO_PUBLICO)
    assert artigo.visibilidade == 'publica', 'o artigo consultado pelo solicitante deveria ser público'
