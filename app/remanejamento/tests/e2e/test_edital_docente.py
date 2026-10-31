"""Fluxo: o ramo **docente** do edital — disciplinas no lugar de cargos/áreas.

``Edital.eh_edital_remocao_docente`` (``models.py:929``) troca metade da interface: a aba
Edital passa a oferecer "Configurar disciplinas" em vez de "Configurar cargos", as vagas
passam a ser por ``edu.Disciplina`` e as correlatas deixam de ser áreas do cargo para serem
disciplinas. Nada disso é alcançável a partir de um edital TAE, então sem este arquivo três
rotas e um formulário inteiro ficariam sem execução nenhuma.

Cobre também a **avaliação da documentação anexa**, que só existe no ramo docente: o campo
``anexo`` é acrescentado ao formulário de inscrição apenas quando o edital é docente
(``forms.py:344``), e é dele que depende ``existem_anexos_nao_avaliados``
(``models.py:976``) — a trava que impede processar o resultado com documentação pendente.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

GERENCIAR = '/remanejamento/edital/{}/gerenciar/'
CONFIGURAR_DISCIPLINAS = '/remanejamento/edital/{}/configurar_disciplinas/'
CADASTRAR_DISCIPLINAS_CORRELATAS = '/remanejamento/edital/vagaedital_id/{}/cadastrar_disciplinas_correlatas_edital/'
AVALIAR_ANEXO = '/remanejamento/inscricao/{}/avaliar_anexo_inscricao/'


def test_configura_disciplina_do_edital_docente(logado_remanejamento, edital_docente, disciplina_edu):
    """Adiciona uma disciplina ao edital docente e confere a vaga criada em cada campus.

    ``ConfigurarDisciplinasEditalForm.processar`` (``forms.py:782``) replica a disciplina por
    (cargo x campus) com ``qtd_edital=0``, do mesmo jeito que a configuração de cargos faz no
    ramo TAE — o número de vagas continua vindo da tela "Editar vagas". ``possui_concurso
    vigente`` viaja junto porque é ele que, na inscrição, dispensa (ou exige) o anexo de
    equivalência (``forms.py:385-390``).
    """
    from remanejamento.models import VagaEdital

    tela = Tela(logado_remanejamento('coordenador')).ir(CONFIGURAR_DISCIPLINAS.format(edital_docente.pk))
    tela.quadro('Disciplinas do edital').ver_texto('Nenhuma disciplina adicionada.')

    tela.preencher_formulario(
        [
            ('Disciplina', 'autocomplete', disciplina_edu['principal'].descricao),
            ('Possui Concurso vigente?', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Disciplina adicionada com sucesso')
    vagas = VagaEdital.objects.filter(edital=edital_docente, disciplina=disciplina_edu['principal'])
    assert vagas.count() == 2, f'esperava uma vaga por campus do edital, veio {vagas.count()}'
    assert all(vaga.possui_concurso_vigente for vaga in vagas), 'o "possui concurso vigente" não foi gravado'
    tela.quadro('Disciplinas do edital').linha(disciplina_edu['principal'].descricao)


def test_cadastra_disciplinas_correlatas_da_vaga(logado_remanejamento, edital_docente, disciplina_edu):
    """Liga uma disciplina correlata à vaga — o equivalente docente da área correlata.

    É o que permite ao professor de uma disciplina concorrer à vaga de outra: sem a correlata,
    ``InscreverFormFactory.clean`` recusa a inscrição dizendo que a disciplina de ingresso não
    está entre as correlatas (``forms.py:380-384``).
    """
    from remanejamento.models import VagaEdital

    vaga = VagaEdital.objects.create(
        edital=edital_docente,
        campus=edital_docente.campus.first(),
        cargo=edital_docente.cargos.first(),
        disciplina=disciplina_edu['principal'],
        qtd_edital=1,
        qtd_remanescente=1,
    )

    tela = Tela(logado_remanejamento('coordenador')).ir(CADASTRAR_DISCIPLINAS_CORRELATAS.format(vaga.pk))
    tela.ver_texto(f'Disciplina: {disciplina_edu["principal"].descricao}')
    tela.preencher('Disciplinas Correlatas', 'autocomplete multiplo', disciplina_edu['correlata'].descricao)
    tela.clicar_botao('Enviar')

    tela.sucesso('Disciplinas correlatas cadastradas com sucesso')
    assert list(vaga.disciplinas_correlatas.values_list('descricao', flat=True)) == [disciplina_edu['correlata'].descricao], (
        'a UI disse que salvou, mas a correlata não ficou na vaga'
    )


def test_coordenador_defere_documentacao_anexa_da_inscricao(logado_remanejamento, servidores, edital_docente, disciplina_edu):
    """Defere o anexo da inscrição e destrava o processamento do resultado.

    ``existem_anexos_nao_avaliados`` (``models.py:976``) bloqueia ``processar_resultado``
    enquanto houver inscrição confirmada com anexo sem avaliação — por isso o teste afirma os
    dois lados: o carimbo da avaliação **e** a trava liberada. Indeferir, no mesmo caminho,
    inabilita a inscrição (``views.py:983``); o caso feliz é o que sustenta o fluxo.
    """
    from django.core.files.base import ContentFile

    from remanejamento.models import Inscricao
    from remanejamento.tests.e2e.conftest import criar_inscricao

    edital_docente.tem_anexo = True
    edital_docente.save()
    inscricao = criar_inscricao(edital_docente, servidores['candidato'])
    inscricao.anexo.save('comprovante-e2e.pdf', ContentFile(b'%PDF-1.4 documentacao de equivalencia'), save=True)
    assert edital_docente.existem_anexos_nao_avaliados(), 'a inscrição deveria nascer com anexo pendente de avaliação'

    tela = Tela(logado_remanejamento('coordenador')).ir(AVALIAR_ANEXO.format(inscricao.pk))
    tela.quadro('Documento Anexo da Inscrição').ver_texto(str(servidores['candidato']))

    tela.clicar_botao('Deferir')

    tela.sucesso('Anexo da inscrição foi deferido')
    inscricao = Inscricao.objects.get(pk=inscricao.pk)
    assert inscricao.anexo_deferido, 'a UI disse que deferiu, mas o anexo continua não deferido'
    assert inscricao.anexo_avaliado_por == servidores['coordenador'].get_vinculo(), 'o deferimento não registrou o avaliador'
    assert not edital_docente.existem_anexos_nao_avaliados(), 'o deferimento não destravou o processamento do resultado'
