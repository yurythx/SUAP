"""Fluxo: o que o coordenador administra sobre cada aluno da equipe — plano de trabalho, orientação, carga horária de extensão e encerramentos em lote.

* **Plano de trabalho** — as atividades em que o membro está (``Etapa.integrantes``): a tela, a
  versão para impressão e o "Desvincular Participante" de todas elas.
* **Orientador** — o servidor da equipe que orienta o aluno; cada troca fecha a orientação
  anterior e abre outra em ``HistoricoOrientacaoProjeto`` (é o que a declaração de orientação lê).
* **CH de extensão** — a carga horária curricular do aluno de curso com extensão na matriz,
  ajustada depois de encerrada a participação: é ela que o ``edu`` credita ao aluno
  (``AtividadeCurricularExtensao``) — o efeito cruzado é afirmado.
* **Em lote** — encerrar as participações de vários alunos; adicionar os alunos de um diário
  (só professor).

As sondas cobrem quem não coordena o projeto, a participação ALHEIA forjada no POST do
encerramento em lote (controle positivo: o formulário filtra pelo projeto) e as duas telas do
plano de trabalho.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela, adicionar_ao_filteredselect
from projetos.tests.e2e.conftest import clicar_em, membro

if TYPE_CHECKING:
    from types import SimpleNamespace

    from projetos.models import Participacao


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
VER_PLANO = '/projetos/ver_plano_trabalho/{}/{}/'
IMPRIMIR_PLANO = '/projetos/plano_trabalho_participante/{}/{}/'
DESVINCULAR = '/projetos/desvincular_participante_atividades/{}/'
INDICAR_ORIENTADOR = '/projetos/indicar_orientador/{}/'
EDITAR_CH_EXTENSAO = '/projetos/editar_ch_extensao/{}/'
ENCERRAR_EM_LOTE = '/projetos/encerrar_participacoes_em_lote/{}/'
ALUNOS_EM_LOTE = '/projetos/adicionar_participante_alunos_em_lote/{}/'

NOME_DO_ALUNO = 'Aluno Extensão E2E'


def _data(dia: datetime.date) -> str:
    return dia.strftime('%d/%m/%Y')


@pytest.fixture
def aluno_numa_atividade(projeto_em_execucao) -> tuple[SimpleNamespace, Participacao]:
    """Projeto em execução com o ``aluno`` na equipe e integrante da atividade (``execucao.etapa``)."""
    execucao = projeto_em_execucao()
    participacao = membro(execucao.projeto, 'aluno')
    execucao.etapa.integrantes.add(participacao)
    return execucao, participacao


# -------------------------------------------------------------------- plano de trabalho


def test_plano_de_trabalho_imprimir_e_desvincular(logado_projetos, aluno_numa_atividade):
    """ "Plano de Trabalho" do membro → "Imprimir" → "Desvincular Participante": o aluno sai de todas as atividades."""
    execucao, participacao = aluno_numa_atividade
    projeto = execucao.projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk)).clicar_aba('Equipe')

    # Popup sem `<form>` (armadilha 38): afirma o botão do membro e abre a rota na página.
    expect(tela.loc(f'//a[@href="{VER_PLANO.format(projeto.pk, participacao.pk)}"]')).to_have_count(1)
    tela.ir(VER_PLANO.format(projeto.pk, participacao.pk)).ver_titulo(f'Plano de Trabalho - {NOME_DO_ALUNO}')
    tela.ver_texto('ATIVIDADES DESENVOLVIDAS').ver_texto(execucao.etapa.descricao)

    clicar_em(tela, IMPRIMIR_PLANO.format(projeto.pk, participacao.pk))
    tela.ver_texto('ATIVIDADES DESENVOLVIDAS').ver_texto(execucao.etapa.descricao)  # o nome do membro falta (xfail abaixo)

    tela.ir(VER_PLANO.format(projeto.pk, participacao.pk))
    clicar_em(tela, DESVINCULAR.format(participacao.pk))  # `.confirm`: o `logado` aceita
    tela.esperar().sucesso('Participante removido das atividades com sucesso.')
    assert not execucao.etapa.integrantes.filter(pk=participacao.pk).exists(), 'a UI disse que desvinculou, mas o aluno segue na atividade'


def test_plano_de_trabalho_sem_atividade(logado_projetos, projeto_em_execucao):
    projeto = projeto_em_execucao().projeto
    participacao = membro(projeto, 'aluno')
    tela = Tela(logado_projetos('coordenador_projeto')).ir(VER_PLANO.format(projeto.pk, participacao.pk))

    tela.ver_texto('O participante não foi relacionado à nenhuma atividade do projeto.')
    assert tela.loc(f'//a[@href="{DESVINCULAR.format(participacao.pk)}"]').count() == 0


def test_so_o_coordenador_desvincula(logado_projetos, aluno_numa_atividade):
    """O próprio aluno (membro, abre o projeto) e o coordenador de outro projeto: 403, e o GET não desvincula."""
    execucao, participacao = aluno_numa_atividade

    respostas = {papel: Tela(logado_projetos(papel)).buscar(DESVINCULAR.format(participacao.pk)).status for papel in ('aluno', 'outro_coordenador')}
    assert respostas == {'aluno': 403, 'outro_coordenador': 403}
    assert execucao.etapa.integrantes.filter(pk=participacao.pk).exists(), 'uma rota que respondeu 403 tirou o aluno da atividade'


def test_estranho_nao_ve_o_plano_de_trabalho(logado_projetos, aluno_numa_atividade):
    execucao, participacao = aluno_numa_atividade
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {}
    for rota in (VER_PLANO, IMPRIMIR_PLANO):
        resposta = tela.buscar(rota.format(execucao.projeto.pk, participacao.pk))
        respostas[rota] = (resposta.status, execucao.etapa.descricao in resposta.text())
    assert all(status in (302, 403) and not vazou for status, vazou in respostas.values()), f'estranho viu o plano de trabalho: {respostas}'


def test_plano_de_trabalho_com_projeto_alheio_na_url(logado_projetos, projeto_em_execucao, aluno_numa_atividade):
    """A participação do próprio projeto com o ``projeto_id`` de outro na URL: 404, sem o título do projeto alheio (#17568)."""
    _, participacao = aluno_numa_atividade
    alheio = projeto_em_execucao(coordenador='outro_coordenador', sufixo='alheio').projeto
    tela = Tela(logado_projetos('coordenador_projeto'))

    respostas = {}
    for rota in (VER_PLANO, IMPRIMIR_PLANO):
        resposta = tela.buscar(rota.format(alheio.pk, participacao.pk))
        respostas[rota] = (resposta.status, alheio.titulo in resposta.text())
    assert respostas == dict.fromkeys((VER_PLANO, IMPRIMIR_PLANO), (404, False)), f'o plano saiu com o projeto da URL: {respostas}'


def test_impressao_do_plano_traz_o_nome_do_membro(logado_projetos, aluno_numa_atividade):
    execucao, participacao = aluno_numa_atividade
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(IMPRIMIR_PLANO.format(execucao.projeto.pk, participacao.pk))

    assert resposta.status == 200
    assert f'Plano de Trabalho de {NOME_DO_ALUNO}' in resposta.text(), 'o plano impresso não diz de quem é'


# ---------------------------------------------------------------------------- orientador


def test_indicar_orientador_do_aluno(logado_projetos, projeto_em_execucao):
    """ "Indicar orientador" (popup): só os servidores ativos da equipe são opção; a orientação abre no histórico."""
    from projetos.models import HistoricoOrientacaoProjeto

    projeto = projeto_em_execucao().projeto
    aluno = membro(projeto, 'aluno')
    orientador = membro(projeto, 'segundo_avaliador')
    inicio = projeto.inicio_execucao + datetime.timedelta(days=1)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk)).clicar_aba('Equipe')

    clicar_em(tela, INDICAR_ORIENTADOR.format(aluno.pk))
    popup = popup_em(tela, INDICAR_ORIENTADOR.format(aluno.pk))
    assert 'Aluno Extensão E2E' not in popup.campo('Novo Orientador', 'lista').first.inner_text(), 'o aluno aparece como opção de orientador'
    popup.preencher_formulario([('Novo Orientador', 'lista', 'Segundo Avaliador E2E'), ('Início da Orientação', 'data', _data(inicio))])
    popup.salvar_no_popup('Enviar').sucesso('Orientador alterado com sucesso.')

    aluno.refresh_from_db()
    assert aluno.orientador == orientador, 'a UI disse que indicou, mas o orientador não persistiu'
    assert HistoricoOrientacaoProjeto.objects.filter(orientado=aluno, orientador=orientador, data_inicio=inicio, data_termino=None).exists(), (
        'a orientação não foi aberta no histórico'
    )


def test_servidor_nao_recebe_orientador(logado_projetos, projeto_em_execucao):
    projeto = projeto_em_execucao().projeto
    servidor = membro(projeto, 'segundo_avaliador')
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.ir(INDICAR_ORIENTADOR.format(servidor.pk)).erro('O participante não é aluno.')
    servidor.refresh_from_db()
    assert servidor.orientador is None


# ------------------------------------------------------------------ CH de extensão


@pytest.fixture
def aluno_de_extensao_encerrado(projeto_em_execucao, aluno_de_extensao, sem_atividades_de_extensao) -> Participacao:
    """Participação ENCERRADA do aluno com matriz de extensão — o único caso em que a CH total se edita."""
    projeto = projeto_em_execucao().projeto
    saida = projeto.inicio_execucao + datetime.timedelta(days=20)
    return membro(projeto, 'aluno', vinculo_pessoa=aluno_de_extensao.get_vinculo(), ativo=False, data_inativacao=saida)


def test_editar_ch_de_extensao_credita_no_edu(logado_projetos, aluno_de_extensao_encerrado):
    """ "Editar CH total de atividade de extensão" → a participação guarda a CH e o ``edu`` passa a creditá-la ao aluno."""
    from django.contrib.contenttypes.models import ContentType

    from edu.models import AtividadeCurricularExtensao
    from projetos.models import Participacao

    participacao = aluno_de_extensao_encerrado
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(participacao.projeto_id)).clicar_aba('Equipe')

    clicar_em(tela, EDITAR_CH_EXTENSAO.format(participacao.pk))
    tela.ver_titulo(f'Editar CH total de atividade de extensão - {participacao}')
    tela.preencher('Carga Horária de Extensão', 'número', '30').clicar_botao('Salvar')
    tela.esperar().sucesso('Carga horária editada com sucesso.')

    participacao.refresh_from_db()
    assert participacao.ch_extensao == 30, 'a UI disse que editou, mas a CH de extensão não persistiu'
    atividade = AtividadeCurricularExtensao.objects.filter(
        tipo_referencia=ContentType.objects.get_for_model(Participacao), id_referencia=participacao.pk
    ).first()
    assert atividade is not None, 'a CH de extensão não chegou ao edu (AtividadeCurricularExtensao)'
    assert (atividade.carga_horaria, atividade.concluida) == (30, True), 'o edu recebeu a CH errada, ou como atividade em andamento'


@pytest.mark.parametrize(
    ('caso', 'papel'), [('ativa', 'coordenador_projeto'), ('sem matriz de extensão', 'coordenador_projeto'), ('estranho', 'outro_coordenador')]
)
def test_ch_de_extensao_so_de_aluno_de_extensao_encerrado(logado_projetos, projeto_em_execucao, aluno_de_extensao_encerrado, caso, papel):
    """Participação ativa, aluno cuja matriz não tem extensão, ou quem não gerencia o projeto: 403."""
    from projetos.models import Participacao

    alvo = aluno_de_extensao_encerrado
    if caso == 'ativa':
        Participacao.objects.filter(pk=alvo.pk).update(ativo=True, data_inativacao=None)
    elif caso == 'sem matriz de extensão':
        alvo = membro(alvo.projeto, 'aluno', ativo=False, data_inativacao=alvo.data_inativacao)

    assert Tela(logado_projetos(papel)).buscar(EDITAR_CH_EXTENSAO.format(alvo.pk)).status == 403


# --------------------------------------------------------------------- encerrar em lote


def test_encerrar_participacoes_em_lote(logado_projetos, projeto_em_execucao):
    """Encerra os alunos escolhidos com data e justificativa; os servidores nem aparecem na lista."""
    from projetos.models import HistoricoEquipe

    projeto = projeto_em_execucao().projeto
    aluno = membro(projeto, 'aluno')
    saida = projeto.inicio_execucao + datetime.timedelta(days=15)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(ENCERRAR_EM_LOTE.format(projeto.pk))

    tela.ver_titulo('Encerrar participações dos alunos em Lote')
    adicionar_ao_filteredselect(tela.pagina, 'id_participacoes_from', NOME_DO_ALUNO)
    tela.preencher_formulario([('Data de Inativação', 'data', _data(saida)), ('Justificativa', 'textarea', 'Fim do semestre letivo')])
    tela.clicar_botao('Enviar')
    tela.esperar().sucesso('Participações encerradas com sucesso.')

    aluno.refresh_from_db()
    assert (aluno.ativo, aluno.data_inativacao) == (False, saida), 'a UI disse que encerrou, mas o aluno segue ativo'
    assert HistoricoEquipe.objects.filter(
        participante=aluno, tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, obs='Fim do semestre letivo'
    ).exists()


def test_encerrar_em_lote_recusa_participacao_de_projeto_alheio(logado_projetos, projeto_em_execucao):
    """Controle positivo de "validação só na lista": a participação alheia forjada no POST é recusada pelo formulário."""
    proprio = projeto_em_execucao(sufixo='proprio').projeto
    membro(proprio, 'aluno')
    alheio = projeto_em_execucao(coordenador='outro_coordenador', sufixo='alheio').projeto
    forjada = membro(alheio, 'aluno')
    tela = Tela(logado_projetos('coordenador_projeto')).ir(ENCERRAR_EM_LOTE.format(proprio.pk))

    adicionar_ao_filteredselect(tela.pagina, 'id_participacoes_from', NOME_DO_ALUNO)
    tela.pagina.evaluate(f'() => document.getElementById("id_participacoes_to").add(new Option("forjada", "{forjada.pk}", true, true))')
    tela.preencher_formulario([('Data de Inativação', 'data', _data(proprio.inicio_execucao)), ('Justificativa', 'textarea', 'Forjada')])
    tela.clicar_botao('Enviar')
    tela.esperar().erro('Escolha(s) inválida(s)')

    forjada.refresh_from_db()
    assert forjada.ativo, 'a participação do projeto alheio foi encerrada pelo lote de outro projeto'


# --------------------------------------------------------------------- alunos em lote


def test_alunos_em_lote_exige_professor(logado_projetos, projeto_em_execucao, professor_de):
    """O assistente lista os diários do professor: sem ``edu.Professor`` é 404; com ele, o primeiro passo pede o diário.

    O caminho feliz (escolher diário e alunos) não é exercitado: exige o grafo de diário do
    ``edu`` (turma, componente com extensão, matrículas), que não se monta à mão
    (``edu/tests/e2e/seed_rotas.py``, nota antes de ``criar_diario_descartavel``).
    """
    projeto = projeto_em_execucao().projeto
    tela = Tela(logado_projetos('coordenador_projeto'))

    assert tela.buscar(ALUNOS_EM_LOTE.format(projeto.pk)).status == 404, 'quem não é professor abriu o assistente'

    professor_de('coordenador_projeto')
    tela.ir(ALUNOS_EM_LOTE.format(projeto.pk)).ver_titulo('Adicionar Alunos em Lote')
    tela.clicar_botao('Continuar')  # passo 1 do `FormWizardPlus`
    tela.esperar().erro('Este campo é obrigatório.')


def test_estranho_nao_administra_os_alunos(logado_projetos, projeto_em_execucao):
    """Coordenador de outro projeto: 403 em orientador, CH, encerramento e adição em lote — e nada é encerrado."""
    projeto = projeto_em_execucao().projeto
    aluno = membro(projeto, 'aluno')
    rotas = [
        INDICAR_ORIENTADOR.format(aluno.pk),
        EDITAR_CH_EXTENSAO.format(aluno.pk),
        ENCERRAR_EM_LOTE.format(projeto.pk),
        ALUNOS_EM_LOTE.format(projeto.pk),
    ]
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {rota: tela.buscar(rota).status for rota in rotas}
    assert respostas == dict.fromkeys(rotas, 403), f'rotas que não barraram o estranho: { {r: s for r, s in respostas.items() if s != 403} }'
    aluno.refresh_from_db()
    assert aluno.ativo
