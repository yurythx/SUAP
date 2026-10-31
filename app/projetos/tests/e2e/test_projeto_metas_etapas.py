"""Fluxo: metas e atividades do projeto (aba "Metas/Atividades", feature 002).

A atividade é o que a execução do projeto registra e o monitoramento valida; sem ao menos uma
atividade por meta o envio é recusado. Aqui passa o ciclo da meta (popups de adicionar/editar,
remoção por GET) e o da atividade — incluindo clonar dentro da mesma meta (a ordem nova é a
última + 1) e editar só a equipe, tela que no período de inscrição não tem link (o ícone só
aparece quando a atividade deixa de ser editável) e por isso é aberta pela URL.
"""

import datetime
from uuid import uuid4

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA = 'Metas/Atividades'
ADICIONAR_META = '/projetos/adicionar_meta/{}/'
EDITAR_META = '/projetos/editar_meta/{}/'
REMOVER_META = '/projetos/remover_meta/{}/'
ADICIONAR_ETAPA = '/projetos/adicionar_etapa/{}/'
EDITAR_ETAPA = '/projetos/editar_etapa/{}/'
CLONAR_ETAPA = '/projetos/clonar_etapa/{}/'
EDITAR_EQUIPE_ETAPA = '/projetos/editar_equipe_etapa/{}/'
REMOVER_ETAPA = '/projetos/remover_etapa/{}/'


def _data(dia: datetime.date) -> str:
    return dia.strftime('%d/%m/%Y')


def test_meta_ciclo_completo(logado_projetos, projeto_novo):
    """Adicionar (popup) → editar (popup) → remover, pelo coordenador do projeto em edição."""
    from projetos.models import Meta

    projeto = projeto_novo()
    descricao = f'Meta E2E {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, ADICIONAR_META.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_META.format(projeto.pk)).preencher_formulario([('Ordem', 'texto', '1'), ('Descrição', 'textarea', descricao)])
    tela = popup.salvar_no_popup('Salvar').sucesso('Meta adicionada com sucesso.')
    meta = Meta.objects.filter(projeto=projeto, descricao=descricao).first()
    assert meta is not None, 'a UI disse que salvou, mas a meta não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, EDITAR_META.format(meta.pk))
    popup = popup_em(tela, EDITAR_META.format(meta.pk)).preencher('Ordem', 'texto', '2')
    tela = popup.salvar_no_popup('Salvar').sucesso('Meta editada com sucesso.')
    meta.refresh_from_db()
    assert meta.ordem == 2, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, REMOVER_META.format(meta.pk))  # `.btn.danger`: o `logado` aceita o confirm
    tela.esperar().sucesso('Meta removida com sucesso.')
    assert not Meta.objects.filter(pk=meta.pk).exists(), 'a UI disse que removeu, mas a meta continua'


def test_atividade_ciclo_completo(logado_projetos, projeto_novo):
    """Adicionar → editar → clonar → editar a equipe → remover, na mesma meta."""
    from projetos.models import Etapa, Participacao
    from projetos.tests.factories import MetaFactory

    projeto = projeto_novo()
    meta = MetaFactory(projeto=projeto)
    coordenador = Participacao.objects.get(projeto=projeto, responsavel=True)
    descricao = f'Atividade E2E {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, ADICIONAR_ETAPA.format(meta.pk))
    popup = popup_em(tela, ADICIONAR_ETAPA.format(meta.pk)).preencher_formulario(
        [
            ('Ordem', 'texto', '1'),
            ('Descrição', 'textarea', descricao),
            ('Indicador Quantitativo', 'texto', 'Unidade'),
            ('Quantidade', 'texto', '4'),
            ('Indicador(es) Qualitativo(s)', 'textarea', 'Verificação de qualidade'),
            ('Responsável', 'lista', 'Coordenador Projeto E2E'),
            ('Início da Execução', 'data', _data(projeto.inicio_execucao)),
            ('Fim da Execução', 'data', _data(projeto.inicio_execucao + datetime.timedelta(days=30))),
            ('Forma de Comprovação', 'texto', 'Relatório'),
        ]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Atividade adicionada com sucesso.')
    etapa = Etapa.objects.filter(meta=meta, descricao=descricao).first()
    assert etapa is not None, 'a UI disse que salvou, mas a atividade não persistiu'
    assert etapa.responsavel == coordenador, 'o responsável gravado não é o escolhido'

    tela.clicar_aba(ABA)
    clicar_em(tela, EDITAR_ETAPA.format(etapa.pk))
    popup = popup_em(tela, EDITAR_ETAPA.format(etapa.pk)).preencher('Quantidade', 'texto', '6')
    tela = popup.salvar_no_popup('Salvar').sucesso('Atividade editada com sucesso.')
    etapa.refresh_from_db()
    assert etapa.qtd == 6, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, CLONAR_ETAPA.format(meta.pk))
    popup = popup_em(tela, CLONAR_ETAPA.format(meta.pk)).preencher_formulario(
        [('Selecione a Meta', 'lista', str(meta)), ('Selecione a Atividade', 'lista', descricao)]
    )
    tela = popup.salvar_no_popup('Enviar').sucesso('Atividade clonada com sucesso.')
    clones = Etapa.objects.filter(meta=meta, descricao=descricao).order_by('ordem')
    assert list(clones.values_list('ordem', flat=True)) == [1, 2], 'o clone não entrou na meta com a ordem seguinte'

    tela.ir(EDITAR_EQUIPE_ETAPA.format(etapa.pk)).ver_titulo('Editar Equipe da Atividade')
    tela.preencher('Integrantes da Atividade', 'checkbox multiplo', 'Coordenador Projeto E2E').clicar_botao('Salvar')
    tela.esperar().sucesso('Equipe da atividade editada com sucesso.')
    assert etapa.integrantes.filter(pk=coordenador.pk).exists(), 'a UI disse que editou, mas a equipe não persistiu'

    tela.ir(PROJETO.format(projeto.pk)).clicar_aba(ABA)
    clicar_em(tela, REMOVER_ETAPA.format(etapa.pk))
    tela.esperar().sucesso('Atividade removida com sucesso.')
    assert not Etapa.objects.filter(pk=etapa.pk).exists(), 'a UI disse que removeu, mas a atividade continua'
