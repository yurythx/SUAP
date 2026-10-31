"""Fluxo: a equipe do projeto — adicionar, editar, encerrar, reativar e excluir participantes.

O coordenador monta a equipe na aba "Equipe" (servidor, aluno e colaborador externo, cada um
num popup próprio), ajusta vínculo e carga horária, encerra a participação de quem sai (com data
e justificativa, que vão para o histórico) e reativa; na inscrição, exclui quem entrou por
engano. O histórico da participação é o que certificado e declarações leem depois — por isso
cada gesto é afirmado também em ``HistoricoEquipe``.

As sondas de acesso cobrem quem não coordena o projeto (403 e nada alterado, inclusive nas
rotas que gravam por GET: ``ativar_participante``, ``deletar_participante``) e o padrão de #17488:
as três edições recebem o projeto E a participação na URL, checam o acesso ao projeto e buscam a
participação só pelo id.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import PAPEIS, clicar_em, membro, vinculo

if TYPE_CHECKING:
    from collections.abc import Iterator

    from projetos.models import ColaboradorVoluntario, Participacao, Projeto


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ADICIONAR_SERVIDOR = '/projetos/adicionar_participante_servidor/{}/'
ADICIONAR_ALUNO = '/projetos/adicionar_participante_aluno/{}/'
ADICIONAR_COLABORADOR = '/projetos/adicionar_participante_colaborador/{}/'
EDITAR_SERVIDOR = '/projetos/editar_participante_servidor/{}/{}/'
EDITAR_ALUNO = '/projetos/editar_participante_aluno/{}/{}/'
EDITAR_COLABORADOR = '/projetos/editar_participante_colaborador/{}/{}/'
ENCERRAR = '/projetos/remover_participante/{}/'
ATIVAR = '/projetos/ativar_participante/{}/'
EXCLUIR = '/projetos/deletar_participante/{}/'
HISTORICO = '/projetos/historico_equipe/{}/'


def _hoje() -> str:
    return datetime.date.today().strftime('%d/%m/%Y')


def _abrir_equipe(tela: Tela, projeto_pk: int) -> Tela:
    return tela.ir(PROJETO.format(projeto_pk)).clicar_aba('Equipe')


def test_adicionar_servidor_na_equipe(logado_projetos, projeto_novo):
    """ "Adicionar Servidor" (popup): a participação nasce com a entrada "Servidor inserido" no histórico."""
    from projetos.models import HistoricoEquipe, Participacao

    projeto = projeto_novo()
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, ADICIONAR_SERVIDOR.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_SERVIDOR.format(projeto.pk)).preencher_formulario(
        [
            ('Bolsista', 'lista', 'Não'),
            ('Carga Horária', 'texto', '6'),
            ('Participante', 'autocomplete', PAPEIS['segundo_avaliador'], 'Segundo Avaliador E2E'),
            ('Data de Entrada', 'data', _hoje()),
        ]
    )
    popup.salvar_no_popup('Salvar').sucesso('Participante adicionado com sucesso.')

    participacao = Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo('segundo_avaliador')).first()
    assert participacao is not None, 'a UI disse que adicionou, mas a participação não persistiu'
    assert (participacao.carga_horaria, participacao.vinculo, participacao.responsavel) == (6, 'Voluntário', False)
    assert HistoricoEquipe.objects.filter(participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR).exists(), (
        'a participação entrou sem o registro no histórico da equipe'
    )


def test_servidor_repetido_nao_entra_duas_vezes(logado_projetos, projeto_novo):
    from projetos.models import Participacao

    projeto = projeto_novo()
    membro(projeto, 'segundo_avaliador')
    tela = Tela(logado_projetos('coordenador_projeto')).ir(ADICIONAR_SERVIDOR.format(projeto.pk))

    tela.preencher_formulario(
        [
            ('Bolsista', 'lista', 'Não'),
            ('Carga Horária', 'texto', '4'),
            ('Participante', 'autocomplete', PAPEIS['segundo_avaliador'], 'Segundo Avaliador E2E'),
            ('Data de Entrada', 'data', _hoje()),
        ]
    ).clicar_botao('Salvar')
    tela.esperar().erro('Este participante já pertence ao projeto.')
    assert Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo('segundo_avaliador')).count() == 1


def test_adicionar_aluno_na_equipe(logado_projetos, projeto_novo):
    """ "Adicionar Aluno" (popup), voluntário. O aluno do seed não tem matriz de extensão: nada é gravado no ``edu``/``ae``."""
    from ae.models import ParticipacaoBolsa
    from edu.models import AtividadeCurricularExtensao, AtividadePraticaProfissional
    from projetos.models import HistoricoEquipe, Participacao

    projeto = projeto_novo()
    efeitos = (AtividadeCurricularExtensao.objects, AtividadePraticaProfissional.objects, ParticipacaoBolsa.objects)
    antes = [manager.count() for manager in efeitos]
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, ADICIONAR_ALUNO.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_ALUNO.format(projeto.pk)).preencher_formulario(
        [
            ('Bolsista', 'lista', 'Não'),
            ('Carga Horária', 'texto', '8'),
            ('Participante', 'autocomplete', PAPEIS['aluno'], 'Aluno Extensão E2E'),
            ('Data de Entrada', 'data', _hoje()),
        ]
    )
    popup.salvar_no_popup('Salvar').sucesso('Participante adicionado com sucesso.')

    participacao = Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo('aluno')).first()
    assert participacao is not None, 'a UI disse que adicionou, mas a participação do aluno não persistiu'
    assert HistoricoEquipe.objects.filter(participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_ADICIONAR_ALUNO).exists()
    assert [manager.count() for manager in efeitos] == antes, 'a participação de um aluno sem matriz de extensão gravou no edu/ae'


@pytest.fixture
def colaborador_externo(projetos_seed) -> Iterator[ColaboradorVoluntario]:
    """Colaborador externo ativo (prestador de serviço), nome único; apagado no fim com o prestador."""
    from projetos.tests.factories import ColaboradorVoluntarioFactory

    colaborador = ColaboradorVoluntarioFactory(nome=f'Colaboradora Externa {uuid4().hex[:8]}')
    yield colaborador
    colaborador.prestador.delete()


def test_adicionar_colaborador_externo(logado_projetos, projeto_novo, colaborador_externo):
    """Só com o edital permitindo colaborador externo; a data de entrada não pode ser anterior ao início da execução."""
    from projetos.models import Edital, HistoricoEquipe, Participacao

    projeto = projeto_novo()
    Edital.objects.filter(pk=projeto.edital_id).update(permite_colaborador_voluntario=True)
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, ADICIONAR_COLABORADOR.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_COLABORADOR.format(projeto.pk)).preencher_formulario(
        [
            ('Carga Horária', 'texto', '4'),
            ('Participante', 'autocomplete', colaborador_externo.nome),
            ('Data de Entrada', 'data', projeto.inicio_execucao.strftime('%d/%m/%Y')),
        ]
    )
    popup.salvar_no_popup('Salvar').sucesso('Participante adicionado com sucesso.')

    participacao = Participacao.objects.filter(projeto=projeto, vinculo_pessoa=colaborador_externo.prestador.get_vinculo()).first()
    assert participacao is not None, 'a UI disse que adicionou, mas o colaborador não entrou na equipe'
    assert participacao.vinculo == 'Voluntário', 'edital sem "colaborador externo bolsista": o colaborador entra como voluntário'
    assert HistoricoEquipe.objects.filter(participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_ADICIONAR_COLABORADOR).exists()


def test_edital_sem_colaborador_externo_nao_oferece_nem_abre(logado_projetos, projeto_novo):
    projeto = projeto_novo()
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    assert tela.loc(f'//a[@href="{ADICIONAR_SERVIDOR.format(projeto.pk)}"]').count() == 1  # a sonda enxerga os botões da aba
    assert tela.loc(f'//a[@href="{ADICIONAR_COLABORADOR.format(projeto.pk)}"]').count() == 0
    assert tela.buscar(ADICIONAR_COLABORADOR.format(projeto.pk)).status == 403


# ------------------------------------------------------------------------------ edição

EDICOES = {'servidor': EDITAR_SERVIDOR, 'aluno': EDITAR_ALUNO, 'colaborador': EDITAR_COLABORADOR}


def _membro_do_tipo(projeto: Projeto, tipo: str, colaborador: ColaboradorVoluntario) -> Participacao:
    if tipo == 'colaborador':
        return membro(projeto, 'aluno', vinculo_pessoa=colaborador.prestador.get_vinculo())
    return membro(projeto, 'segundo_avaliador' if tipo == 'servidor' else 'aluno')


@pytest.mark.parametrize(
    ('tipo', 'rota', 'evento'),
    [
        ('servidor', EDITAR_SERVIDOR, 'EVENTO_EDICAO_SERVIDOR'),
        ('aluno', EDITAR_ALUNO, 'EVENTO_EDICAO_ALUNO'),
        ('colaborador', EDITAR_COLABORADOR, 'EVENTO_EDICAO_COLABORADOR'),
    ],
)
def test_editar_carga_horaria_do_participante(logado_projetos, projeto_novo, colaborador_externo, tipo, rota, evento):
    """O ícone de edição de cada tipo de membro abre o popup certo; mudar a carga horária grava o evento de edição."""
    from projetos.models import HistoricoEquipe

    projeto = projeto_novo()
    participacao = _membro_do_tipo(projeto, tipo, colaborador_externo)
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, rota.format(projeto.pk, participacao.pk))
    popup = popup_em(tela, rota.format(projeto.pk, participacao.pk)).preencher('Carga Horária', 'texto', '2')
    popup.salvar_no_popup('Salvar').sucesso('Participante editado com sucesso.')

    participacao.refresh_from_db()
    assert participacao.carga_horaria == 2, 'a UI disse que editou, mas a carga horária não mudou'
    assert HistoricoEquipe.objects.filter(participante=participacao, tipo_de_evento=getattr(HistoricoEquipe, evento)).exists(), (
        'a edição da carga horária não ficou no histórico da equipe'
    )


def test_coordenador_nao_edita_membro_de_projeto_alheio(logado_projetos, projeto_novo, projeto_alheio, colaborador_externo):
    from projetos.models import HistoricoEquipe, Participacao

    proprio = projeto_novo()
    alvos = {rota: _membro_do_tipo(projeto_alheio.projeto, tipo, colaborador_externo) for tipo, rota in EDICOES.items()}
    tela = Tela(logado_projetos('coordenador_projeto'))

    for rota, participacao in alvos.items():
        url = rota.format(proprio.pk, participacao.pk)
        if tela.buscar(url).status == 200:  # o defeito: a participação alheia abre, preenchida
            tela.ir(url).preencher('Carga Horária', 'texto', '1').clicar_botao('Salvar')
            tela.esperar()
    cargas = dict(Participacao.objects.filter(pk__in=[p.pk for p in alvos.values()]).values_list('pk', 'carga_horaria'))
    edicoes = (HistoricoEquipe.EVENTO_EDICAO_SERVIDOR, HistoricoEquipe.EVENTO_EDICAO_ALUNO, HistoricoEquipe.EVENTO_EDICAO_COLABORADOR)
    eventos = HistoricoEquipe.objects.filter(projeto=projeto_alheio.projeto, tipo_de_evento__in=edicoes).count()
    # Uma asserção só, para o `--runxfail` mostrar os dois efeitos: a carga alterada E o evento no histórico alheio.
    assert (cargas, eventos) == ({p.pk: p.carga_horaria for p in alvos.values()}, 0), (
        f'membro de projeto alheio alterado pela edição do próprio projeto: cargas {cargas}, eventos de edição no histórico alheio {eventos}'
    )


# -------------------------------------------------------------- encerrar, ativar, excluir


def test_encerrar_e_reativar_a_participacao(logado_projetos, projeto_em_execucao):
    """ "Encerrar participação" (data + justificativa, página inteira) → "Ativar participante" (GET), no projeto em execução.

    A data de inativação é posterior à entrada (o início da execução): é a saída que o
    certificado do membro lê depois.
    """
    from projetos.models import HistoricoEquipe

    projeto = projeto_em_execucao().projeto
    participacao = membro(projeto, 'segundo_avaliador')
    saida = projeto.inicio_execucao + datetime.timedelta(days=10)
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, ENCERRAR.format(participacao.pk))
    tela.ver_titulo('Inativar Participante').preencher_formulario(
        [('Data de Inativação', 'data', saida.strftime('%d/%m/%Y')), ('Justificativa', 'textarea', 'Remoção a pedido do servidor')]
    )
    tela.clicar_botao('Enviar')
    tela.esperar().sucesso('Participação encerrada com sucesso.')
    participacao.refresh_from_db()
    assert (participacao.ativo, participacao.data_inativacao) == (False, saida), 'a UI disse que encerrou, mas a participação segue ativa'
    assert HistoricoEquipe.objects.filter(
        participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, obs='Remoção a pedido do servidor'
    ).exists(), 'o encerramento não ficou no histórico com a justificativa'

    tela.clicar_aba('Equipe')
    clicar_em(tela, ATIVAR.format(participacao.pk))
    tela.sucesso('Participante ativado com sucesso.')
    participacao.refresh_from_db()
    assert (participacao.ativo, participacao.data_inativacao) == (True, None), 'a UI disse que ativou, mas a participação segue inativa'


def test_excluir_participante_na_inscricao(logado_projetos, projeto_novo):
    """O ícone de excluir (``.btn.danger``, o ``logado`` aceita o confirm) apaga a participação e os anexos do membro."""
    from projetos.models import Participacao

    projeto = projeto_novo()
    participacao = membro(projeto, 'segundo_avaliador')
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, EXCLUIR.format(participacao.pk))
    tela.esperar().sucesso('Participante removido com sucesso.')
    assert not Participacao.objects.filter(pk=participacao.pk).exists(), 'a UI disse que removeu, mas a participação continua'


def test_responsavel_por_atividade_nao_e_excluido(logado_projetos, projeto_novo):
    from projetos.models import Participacao
    from projetos.tests.factories import EtapaFactory, MetaFactory

    projeto = projeto_novo()
    participacao = membro(projeto, 'segundo_avaliador')
    EtapaFactory(meta=MetaFactory(projeto=projeto), responsavel=participacao)
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    clicar_em(tela, EXCLUIR.format(participacao.pk))
    tela.esperar().erro('O participante é responsável por uma ou mais atividades.')
    assert Participacao.objects.filter(pk=participacao.pk).exists(), 'o responsável por uma atividade foi excluído da equipe'


def test_historico_da_participacao(logado_projetos, projeto_em_execucao):
    """O ícone "Visualizar" do membro abre o histórico (popup): a entrada e o encerramento, com a justificativa."""
    from projetos.models import HistoricoEquipe, Participacao
    from projetos.tests.factories import HistoricoEquipeFactory

    projeto = projeto_em_execucao().projeto
    participacao = membro(projeto, 'segundo_avaliador')
    saida = projeto.inicio_execucao + datetime.timedelta(days=5)
    HistoricoEquipe.objects.filter(participante=participacao).update(data_movimentacao_saida=saida)
    HistoricoEquipeFactory(
        participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_movimentacao=saida, obs='Concluiu a bolsa'
    )
    Participacao.objects.filter(pk=participacao.pk).update(ativo=False, data_inativacao=saida)
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_projeto')), projeto.pk)

    # Popup sem `<form>` (armadilha 38): afirma o ícone e abre a rota na página.
    expect(tela.loc(f'//a[@href="{HISTORICO.format(participacao.pk)}"]')).to_have_count(1)
    tela.ir(HISTORICO.format(participacao.pk)).ver_titulo('Histórico da Participação')
    tela.ver_texto('Servidor inserido').ver_texto('Participante inativado').ver_texto('Concluiu a bolsa')


# ---------------------------------------------------------------------------- acesso


@pytest.fixture
def equipe_para_sondar(projeto_em_execucao) -> tuple[Projeto, Participacao, Participacao]:
    """Projeto em execução do ``coordenador_projeto`` com um membro ativo e um inativo — os alvos das sondas."""
    projeto = projeto_em_execucao().projeto
    ativo = membro(projeto, 'segundo_avaliador')
    inativo = membro(projeto, 'avaliador', ativo=False, data_inativacao=projeto.inicio_execucao)
    return projeto, ativo, inativo


def test_estranho_nao_mexe_na_equipe(logado_projetos, equipe_para_sondar):
    """Coordenador de OUTRO projeto: todas as rotas da equipe dão 403, e as que gravam por GET não gravam."""
    from projetos.models import Participacao

    projeto, ativo, inativo = equipe_para_sondar
    rotas = [
        ADICIONAR_SERVIDOR.format(projeto.pk),
        ADICIONAR_ALUNO.format(projeto.pk),
        EDITAR_SERVIDOR.format(projeto.pk, ativo.pk),
        EDITAR_ALUNO.format(projeto.pk, ativo.pk),
        EDITAR_COLABORADOR.format(projeto.pk, ativo.pk),
        ENCERRAR.format(ativo.pk),
        ATIVAR.format(inativo.pk),
        EXCLUIR.format(ativo.pk),
    ]
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {rota: tela.buscar(rota).status for rota in rotas}
    assert respostas == dict.fromkeys(rotas, 403), f'rotas que não barraram o estranho: { {r: s for r, s in respostas.items() if s != 403} }'
    estado = dict(Participacao.objects.filter(pk__in=[ativo.pk, inativo.pk]).values_list('pk', 'ativo'))
    assert estado == {ativo.pk: True, inativo.pk: False}, f'uma rota que respondeu 403 mexeu na equipe: {estado}'


def test_coordenador_de_extensao_do_campus_adiciona_servidor(logado_projetos, projeto_em_execucao):
    """O Coordenador de Extensão do campus não coordena o projeto, mas a aba lhe oferece "Adicionar Servidor" (``is_pre_avaliador``).

    Só o servidor: aluno e colaborador passam por ``tem_permissao`` e dão 403.
    """
    from projetos.models import Participacao

    projeto = projeto_em_execucao().projeto
    tela = _abrir_equipe(Tela(logado_projetos('coordenador_extensao')), projeto.pk)

    clicar_em(tela, ADICIONAR_SERVIDOR.format(projeto.pk))
    popup = popup_em(tela, ADICIONAR_SERVIDOR.format(projeto.pk)).preencher_formulario(
        [
            ('Bolsista', 'lista', 'Não'),
            ('Carga Horária', 'texto', '4'),
            ('Participante', 'autocomplete', PAPEIS['segundo_avaliador'], 'Segundo Avaliador E2E'),
            ('Data de Entrada', 'data', _hoje()),
        ]
    )
    popup.salvar_no_popup('Salvar').sucesso('Participante adicionado com sucesso.')
    assert Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo('segundo_avaliador')).exists()
    assert tela.buscar(ADICIONAR_ALUNO.format(projeto.pk)).status == 403, 'só o servidor é aberto ao Coordenador de Extensão'
