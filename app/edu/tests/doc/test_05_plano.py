"""Tarefa 5 — o plano de ensino, do professor à homologação.

Um objetivo, três papéis: o professor preenche e submete, o Coordenador de Curso aprova e
o Diretor Acadêmico homologa. As três telas são a MESMA listagem de planos de ensino, com
abas diferentes por papel — é por isso que a doc as trata como etapas de uma tarefa só.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '21/03/2019'


@pytest.fixture
def diario_do_professor(edu_seed):
    """Diário POS.0001 da turma 2019.1 do curso 10101, com a etapa 1 em posse do professor."""
    from edu.models import Aula, Diario, MatriculaDiario, NotaAvaliacao, SolicitacaoRelancamentoEtapa

    diario = Diario.objects.get(
        componente_curricular__componente__sigla='POS.0001',
        turma__curso_campus__codigo='10101',
        turma__periodo_letivo=1,
    )
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_PROFESSOR, situacao=Diario.SITUACAO_ABERTO)
    Aula.objects.filter(professor_diario__diario=diario, etapa=1).delete()
    NotaAvaliacao.objects.filter(matricula_diario__diario=diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=1).update(nota=None)
    MatriculaDiario.objects.filter(diario=diario).update(nota_1=None, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    SolicitacaoRelancamentoEtapa.objects.filter(professor_diario__diario=diario).delete()
    diario.refresh_from_db()
    return diario


@pytest.fixture
def plano_de_ensino(diario_do_professor):
    """Plano de ensino do diário, com o ciclo de aprovação zerado (é irreversível na tela)."""
    from edu.models import PlanoEnsino

    plano = diario_do_professor.planoensino_set.get()
    PlanoEnsino.objects.filter(pk=plano.pk).update(data_submissao=None, data_aprovacao=None, data_homologacao=None)
    plano.refresh_from_db()
    return plano


def test_preencher_o_plano_de_ensino(logado_edu, plano_de_ensino, capturar):
    """Etapa 1 — o professor preenche ementa, objetivos, metodologia e referências."""
    tela = Tela(logado_edu('professor')).ir('/admin/edu/planoensino/')
    anotar('plano-listagem', tela)
    capturar(tela.pagina, 'plano-listagem')

    tela.ir(f'/admin/edu/planoensino/{plano_de_ensino.pk}/change/')
    anotar('plano-formulario', tela)
    tela.preencher_formulario(
        [
            ('Ementa', 'textarea', 'A origem e a formação da língua portuguesa.'),
            ('Justificativa', 'textarea', 'Análise dos efeitos das mudanças culturais na Educação.'),
            ('Objetivo Geral', 'textarea', 'A evolução fonológica, morfológica e sintática.'),
            ('Objetivos Específicos', 'textarea', 'A expansão da língua portuguesa.'),
            ('Conteúdo Programático', 'textarea', 'Estudo dos elementos das situações de ensino.'),
            ('Metodologia', 'textarea', 'Estudo dos objetivos educacionais.'),
            ('Informações Adicionais', 'textarea', 'Apresentação da disciplina'),
        ]
    )
    tela.preencher_linha(0, 'referencia', 'texto', '82192')
    capturar(tela.pagina, 'plano-formulario')
    # `input[name=_save]` e não "Salvar" por texto: nesta tela convivem o submit e o link
    # "Salvar em PDF".
    tela.pagina.locator('input[name=_save]').first.click()
    tela.esperar()

    plano_de_ensino.refresh_from_db()
    assert plano_de_ensino.metodologia, 'a UI disse que salvou, mas o plano continua vazio'
    assert plano_de_ensino.referenciabibliograficabasica_set.exists(), 'referência bibliográfica não gravada'


def test_ciclo_de_aprovacao_do_plano(logado_edu, plano_de_ensino, capturar):
    """Etapas 2 a 4 — submeter, aprovar e homologar, cada uma na aba do seu papel."""
    passos = [
        ('professor', 'tab_aguardando_minha_subissao', 'Submeter', 'Submissão realizada com sucesso.', 'plano-submeter'),
        ('coordenador_curso', 'tab_aguardando_minha_aprovacao', 'Aprovar', 'Aprovação realizada com sucesso.', 'plano-aprovar'),
        ('diretor_academico', 'tab_aguardando_homologacao', 'Homologar', 'Homologação realizada com sucesso.', 'plano-homologar'),
    ]
    for papel, aba, acao, mensagem, slug in passos:
        tela = Tela(logado_edu(papel)).ir(f'/admin/edu/planoensino/?tab={aba}')
        anotar(slug, tela)
        tela.selecionar_item('POS.0001')
        tela.preencher('Ação', 'lista', acao)
        capturar(tela.pagina, slug)
        tela.clicar_acao('Aplicar')
        tela.sucesso(mensagem)

    plano_de_ensino.refresh_from_db()
    assert plano_de_ensino.data_submissao, 'submissão não registrada'
    assert plano_de_ensino.data_aprovacao, 'aprovação do coordenador não registrada'
    assert plano_de_ensino.data_homologacao, 'homologação do diretor acadêmico não registrada'


def test_consulta_publica_do_plano_homologado(new_context, plano_de_ensino, capturar):
    """Plano homologado é documento público — a tela anônima do SUAP o lista."""
    from datetime import date

    from edu.models import PlanoEnsino

    PlanoEnsino.objects.filter(pk=plano_de_ensino.pk).update(data_homologacao=date(2019, 3, 21))
    tela = Tela(new_context().new_page()).ir('/edu/planoensino_public/')
    anotar('plano-publico', tela)
    tela.preencher('Ano Letivo', 'lista', '2019')
    tela.preencher('Período Letivo', 'lista', '1')
    tela.clicar_botao('Filtrar')
    tela.esperar()

    tela.ver_texto('POS.0001')
    capturar(tela.pagina, 'plano-publico')
