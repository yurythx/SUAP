"""Infraestrutura dos e2e do AE.

O módulo não tem mais ``features/``: o behave dele foi removido ao converter a suíte para o
**modo 2**, em que a unidade de cobertura é a rota — o gate é
``bin/scripts/paridade_e2e.py ae --rotas`` — e a rastreabilidade de cada arquivo é a sua docstring
de módulo. Os dados de apoio que eram os dois cenários de setup viraram o seed
``ae/tests/e2e/seed.py``; o estado de cada fluxo é montado por fixture (``ae_fluxos``,
``caracterizacao_pronta``, ``inscricao_deferida``) porque a receita exige que um teste possa ser
executado isoladamente.

O relógio fica em 03/06/2024. Essa era a data dos cenários do behave, e mantém o período de
inscrição aberto e a data de entrada das participações aceita. O aquecimento da URLconf ocorre
antes do congelamento, conforme a receita de e2e.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from freezegun import freeze_time

from djtools.e2e_fixtures import *  # noqa: F403

if TYPE_CHECKING:
    from ae.models import Programa
    from edu.models import Aluno

DATA_BASE = '03/06/2024'
PAPEIS = {
    'coordenador': '103001',
    'assistente_social': '103002',
    'aluno': '20191101011031',
}

# Rotas que não viram teste. Cada motivo é uma condição verificável no código.
#
# As seis ações de estado da inscrição (ativar/inativar/priorizar/despriorizar/selecionar/
# desselecionar), as remoções, os cancelamentos e os recálculos **mudam estado por GET**
# (nenhuma tem ``require_POST``): visitá-las no smoke alteraria o dado que as outras suítes
# compartilham. Travar um teste nelas seria endossar o comportamento — o achado vai no MR.
# As demais exigem um estado que o seed não cria, e a condição está na própria view.
ROTAS_DISPENSADAS = {
    '/ae/ativar_inscricao/<int:inscricao_id>/': 'muda estado por GET: ``inscricao.ativa = True; save()`` sem ``require_POST``.',
    '/ae/inativar_inscricao/<int:inscricao_id>/': 'muda estado por GET: ``inscricao.ativa = False; save()`` sem ``require_POST``.',
    '/ae/priorizar_inscricao/<int:inscricao_id>/': 'muda estado por GET: ``inscricao.prioritaria = True; save()``.',
    '/ae/despriorizar_inscricao/<int:inscricao_id>/': 'muda estado por GET: ``inscricao.prioritaria = False; save()``.',
    '/ae/selecionar_inscricao/<int:inscricao_id>/': 'muda estado por GET: ``inscricao.selecionada = True; save()``.',
    '/ae/desselecionar_inscricao/<int:inscricao_id>/': 'muda estado por GET: ``inscricao.selecionada = False; save()``.',
    '/ae/cancelar_solicitacao_refeicao/<int:solicitacao_id>/': (
        'cancela a solicitação e o agendamento por GET (``solicitacao.ativa = False``, ``agendamento.cancelado = True``) e o seed não cria solicitações.'
    ),
    '/ae/cancelar_justificativa_falta/<int:solicitacao_id>/': 'marca a falta como cancelada por GET; exige ``HistoricoFaltasAlimentacao`` que o seed não cria.',
    '/ae/informar_ausencia_documentacao/': (
        'invalida a documentação do aluno por GET (``aluno.documentada = False``) a partir de ``?ids=``; sem ``ids`` a view estourava ``AttributeError`` e passou a tratar a ausência.'
    ),
    '/ae/cancelar_atividade_diversa/<int:atividade_id>/': 'inverte ``cancelada`` por GET (``atividade.save()`` sem ``require_POST``).',
    '/ae/cancelar_acao_educativa/<int:acao_id>/': 'inverte ``cancelada`` por GET (``acao.save()`` sem ``require_POST``).',
    '/ae/remover_documentacao_aluno/<int:documento_id>/': 'remove o documento por GET: ``documento.delete()`` sem ``require_POST``.',
    '/ae/alterar_situacao_edital/<int:edital_id>/': 'inverte ``edital.ativo`` por GET, com efeito no período de inscrição.',
    '/ae/validar_documento_inscricao/<int:documento_id>/<int:opcao>/': 'valida/invalida o documento por GET (``documento.validado = True/False; save()``).',
    '/ae/validar_comprovante_mensal/<int:comprovante_id>/': 'marca o comprovante como válido por GET (``comprovante.valido = True; save()``).',
    '/ae/excluir_analise_aluno/<int:analise_id>/': 'remove a análise por GET: ``analise.delete()`` sem ``require_POST``.',
    '/ae/excluir_obs_analise/<int:analise_id>/': 'limpa as observações da análise por GET (``analise.observacoes = None; save()``).',
    '/ae/registrar_ciencia_participacao/<int:participacaotrabalho_id>/': (
        'exige ``ParticipacaoTrabalho.pendente_ciencia`` e chefia do setor da bolsa; o seed não cria essa combinação.'
    ),
    '/ae/deferir_solicitacao_alteracao/<int:solicitacao_id>/': 'exige ``AlteracaoParticipacaoAlimentacao`` pendente; o seed não cria alterações de participação.',
    '/ae/indeferir_solicitacao_alteracao/<int:solicitacao_id>/': 'idem ``deferir_solicitacao_alteracao``: exige alteração pendente, que o seed não cria.',
}


class _Relogio:
    def __init__(self) -> None:
        self._congelador = None
        self._data: str | None = None
        self._suspensa: str | None = None

    def congelar(self, data_br: str) -> None:
        self.descongelar()
        dia, mes, ano = (int(parte) for parte in data_br.split('/'))
        self._congelador = freeze_time(datetime(ano, mes, dia, 12, 0))
        self._congelador.start()
        self._data = data_br

    def descongelar(self) -> None:
        if self._congelador:
            self._congelador.stop()
            self._congelador = None

    def suspender(self) -> None:
        """Solta o relógio ao sair do módulo, lembrando a data para ``retomar``."""
        if self._congelador:
            self._suspensa = self._data
            self.descongelar()

    def retomar(self) -> None:
        if self._suspensa is not None:
            self.congelar(self._suspensa)
            self._suspensa = None


# Único por processo: os hooks abaixo precisam alcançar o mesmo relógio que a fixture entrega.
_RELOGIO = _Relogio()
_MODULO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session')
def relogio():
    from django.urls import get_resolver

    _ = get_resolver().url_patterns
    _RELOGIO.congelar(DATA_BASE)
    yield _RELOGIO
    _RELOGIO.descongelar()


def pytest_runtest_setup(item: pytest.Item) -> None:
    _RELOGIO.retomar()


def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Não deixa 03/06/2024 vazar para o próximo módulo.

    O ``relogio`` é de sessão e congela sem ``tick``: no ``pytest -m doc`` do job
    ``gerar-doc`` (todos os módulos num processo só), quem vem depois do ae veria o tempo
    parado — duas atribuições do ``centralservicos`` empatam em ``atribuido_em`` e a
    "atual" sai a antiga. Estes hooks só disparam para itens deste diretório.
    """
    if nextitem is None or not nextitem.path.is_relative_to(_MODULO):
        _RELOGIO.suspender()


@pytest.fixture(autouse=True)
def data_do_modulo(relogio):
    relogio.congelar(DATA_BASE)
    return


@pytest.fixture(scope='session')
def ae_seed(e2e_seed, relogio) -> None:
    """Cadastra os usuários e os dados de apoio do módulo antes da primeira request.

    O corpo é o dos antigos steps de setup do behave, hoje em ``ae/tests/e2e/seed.py``; os
    usuários (servidores e aluno) saem de factories em ``seed.criar_usuarios``.
    """
    from ae.tests.e2e import seed as seed_ae

    seed_ae.criar_usuarios()
    seed_ae.dados_demanda_aluno_ae()
    seed_ae.dados_basicos_ae()
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def ae_fluxos(ae_seed, relogio) -> dict[str, object]:
    """Cria o estado mínimo que os dez cenários de ``002.AE.fluxos`` consomem."""
    from ae.models import (
        CategoriaAlimentacao,
        DemandaAluno,
        Edital,
        Idioma,
        Inscricao,
        InscricaoAlimentacao,
        InscricaoIdioma,
        InscricaoPasseEstudantil,
        InscricaoTrabalho,
        MotivoSolicitacaoRefeicao,
        OfertaAlimentacao,
        OfertaTurma,
        Participacao,
        PeriodoInscricao,
        Programa,
        SolicitacaoAlimentacao,
        TipoPrograma,
    )
    from comum.models import Ano
    from djtools.choices import DiaSemanaChoices
    from edu.models import Aluno
    from rh.models import UnidadeOrganizacional

    campus = UnidadeOrganizacional.objects.uo().get(sigla='CZN')
    Ano.objects.get_or_create(ano=datetime.now().year)
    aluno = Aluno.objects.get(matricula=PAPEIS['aluno'])
    siglas = {
        'Alimentação Estudantil': Programa.TIPO_ALIMENTACAO,
        'Auxílio Transporte': Programa.TIPO_TRANSPORTE,
        'Apoio à Formação Estudantil': Programa.TIPO_TRABALHO,
        'Curso de Idiomas': Programa.TIPO_IDIOMA,
    }
    programas: dict[str, Programa] = {}
    periodos: dict[str, PeriodoInscricao] = {}
    for titulo, sigla in siglas.items():
        tipo, _ = TipoPrograma.objects.update_or_create(
            titulo=titulo,
            defaults={'descricao': 'E2E tipo de programa', 'sigla': sigla, 'ativo': True},
        )
        programa, _ = Programa.objects.get_or_create(
            tipo_programa=tipo,
            instituicao=campus,
            descricao='E2E programa base',
            defaults={'tipo': sigla, 'titulo': f'{titulo} (CZN)', 'impedir_solicitacao_beneficio': True},
        )
        programa.tipo = sigla
        programa.titulo = f'{titulo} (CZN)'
        programa.impedir_solicitacao_beneficio = True
        programa.save(update_fields=['tipo', 'titulo', 'impedir_solicitacao_beneficio'])
        programa.publico_alvo.set([campus])
        if sigla == Programa.TIPO_ALIMENTACAO:
            programa.demandas.set(DemandaAluno.objects.filter(pk__in=[1, 2]))
        programas[sigla] = programa

        edital, _ = Edital.objects.get_or_create(
            descricao=f'E2E edital base {titulo}', defaults={'link_edital': 'http://example.com/edital.pdf', 'ativo': True}
        )
        edital.tipo_programa.set([tipo])
        periodo = PeriodoInscricao.objects.filter(edital=edital, campus=campus, programa=programa).first()
        if not periodo:
            periodo = PeriodoInscricao.objects.create(
                edital=edital,
                campus=campus,
                data_inicio=datetime(2024, 6, 1),
                data_termino=datetime(2024, 6, 30, 23, 59),
            )
            periodo.programa.set([programa])
        periodos[sigla] = periodo

    Participacao.objects.filter(aluno=aluno, programa__in=programas.values()).delete()
    Inscricao.objects.filter(aluno=aluno, programa__in=programas.values()).delete()

    OfertaAlimentacao.objects.get_or_create(
        campus=campus,
        dia_inicio=date(2024, 6, 3),
        defaults={'dia_termino': date(2024, 6, 7), 'almoco_seg': 100, 'almoco_ter': 100, 'almoco_qua': 100, 'almoco_qui': 100, 'almoco_sex': 100},
    )
    idiomas = {idioma.descricao: idioma for idioma in Idioma.objects.filter(descricao__in=['Inglês', 'Espanhol'])}
    ofertas = []
    for turma, idioma, semestre, dia1, dia2, inicio, termino, professor, vagas in [
        ('01', idiomas['Inglês'], 1, DiaSemanaChoices.SEGUNDA, DiaSemanaChoices.QUARTA, '10:00', '11:00', 'Nome do professor 1', 5),
        ('02', idiomas['Espanhol'], 2, DiaSemanaChoices.TERCA, DiaSemanaChoices.QUINTA, '15:00', '16:00', 'Nome do professor 2', 4),
    ]:
        oferta, _ = OfertaTurma.objects.get_or_create(
            campus=campus,
            turma=turma,
            idioma=idioma,
            ano=2024,
            defaults={
                'semestre': semestre,
                'dia1': dia1,
                'dia2': dia2,
                'horario1': inicio,
                'horario2': termino,
                'professor': professor,
                'numero_vagas': vagas,
            },
        )
        ofertas.append(oferta)

    relogio.congelar(DATA_BASE)
    return {'aluno': aluno, 'programas': programas, 'periodos': periodos, 'ofertas': ofertas}


@pytest.fixture
def caracterizacao_pronta(ae_fluxos):
    """Cria a caracterização socioeconômica do aluno (helper em ``seed.criar_caracterizacao``)."""
    from ae.tests.e2e import seed as seed_ae

    seed_ae.criar_caracterizacao(ae_fluxos['aluno'])
    return ae_fluxos['aluno']


@pytest.fixture
def logado_ae(logado, ae_seed):
    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def inscricao_deferida(ae_fluxos, django_db_blocker):
    def _criar(programa: Programa):
        from ae.models import (
            Inscricao,
            InscricaoAlimentacao,
            InscricaoIdioma,
            InscricaoPasseEstudantil,
            InscricaoTrabalho,
            MotivoSolicitacaoRefeicao,
            Participacao,
            SolicitacaoAlimentacao,
        )

        with django_db_blocker.unblock():
            from ae.tests.e2e import seed as seed_ae

            aluno = ae_fluxos['aluno']
            seed_ae.criar_caracterizacao(aluno)
            aluno.documentada = True
            aluno.data_documentacao = datetime(2024, 6, 3)
            aluno.save(update_fields=['documentada', 'data_documentacao'])
            Participacao.objects.filter(aluno=aluno, programa=programa).delete()
            Inscricao.objects.filter(aluno=aluno, programa=programa).delete()
            campos = {
                'aluno': aluno,
                'programa': programa,
                'data_cadastro': datetime(2024, 6, 3),
                'motivo': 'E2E participação',
                'ativa': True,
                'documentada': True,
                'data_documentacao': datetime(2024, 6, 3),
                'situacao_parecer': Inscricao.DEFERIDO,
                'periodo_inscricao': ae_fluxos['periodos'][programa.tipo_programa.sigla],
            }
            sigla = programa.tipo_programa.sigla
            if sigla == programa.TIPO_ALIMENTACAO:
                inscricao = InscricaoAlimentacao.objects.create(
                    **campos,
                    solicitacao_cafe=SolicitacaoAlimentacao.objects.create(),
                    solicitacao_almoco=SolicitacaoAlimentacao.objects.create(seg=True),
                    solicitacao_janta=SolicitacaoAlimentacao.objects.create(),
                    motivo_atendimento=MotivoSolicitacaoRefeicao.objects.get(descricao='Aula no turno inverso'),
                )
            elif sigla == programa.TIPO_IDIOMA:
                inscricao = InscricaoIdioma.objects.create(**campos, primeira_opcao=ae_fluxos['ofertas'][0], segunda_opcao=ae_fluxos['ofertas'][1])
            elif sigla == programa.TIPO_TRABALHO:
                inscricao = InscricaoTrabalho.objects.create(**campos, turno='Tarde', habilidades='E2E habilidades')
            else:
                inscricao = InscricaoPasseEstudantil.objects.create(
                    **campos,
                    tipo_passe='INT',
                    valor_transporte=10,
                    trajeto='E2E trajeto',
                    oferta_transporte_gratuito='Não',
                )
            return inscricao

    return _criar
