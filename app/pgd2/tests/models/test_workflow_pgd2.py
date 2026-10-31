import datetime
from dataclasses import dataclass
from decimal import Decimal

import pytest

from pgd2.models import (
    ConfiguracaoOrientacaoPit,
    ConfiguracaoOrientacaoPlanoEntregasSetorial,
    ConfiguracaoPerfilServidor,
    DocumentoAdesaoPesServidor,
    DocumentoAdesaoServidor,
    PeriodoPes,
    PeriodoPitRit,
    PitSolicitacaoAnalise,
    PitSolicitacaoAnaliseSetor,
    PitSetores,
    PlanoEntregasSetorial,
    PlanoEntregasSetorialEntregas,
    PlanoEntregasSetorialHorarioFuncionamentoSetor,
    PlanoEntregasSetorialHorarioPlanejamentoSetor,
    PlanoIndividualTrabalho,
    PlanoIndividualTrabalhoAtendimento,
    PlanoIndividualTrabalhoEntregas,
    RelatorioIndividualTrabalho,
    SolicitacaoAdesaoPesServidor,
    SolicitacaoAdesaoServidor,
)
from rh.models import Servidor, Setor
from rh.tests.factories import ServidorFactory, SetorFactory


pytestmark = pytest.mark.django_db(databases='__all__')


@dataclass
class Pgd2Workflow:
    servidor: Servidor
    chefe: Servidor
    setor: Setor
    setor_aprovador: Setor
    inicio: datetime.date
    fim: datetime.date
    documento_pgd: DocumentoAdesaoServidor
    documento_pes: DocumentoAdesaoPesServidor

    @property
    def servidor_user(self):
        return self.servidor.get_user()

    @property
    def chefe_user(self):
        return self.chefe.get_user()


@pytest.fixture
def workflow_pgd2(monkeypatch, db, sync_permissions):
    hoje = datetime.date.today()
    inicio = hoje.replace(day=1)
    fim = inicio + datetime.timedelta(days=29)

    # O setor do servidor fica SOB o setor aprovador: o fluxo do PGD sobe a hierarquia
    # para achar quem aprova, e o chefe é dado como chefia dos dois (ver `setores_de_chefia`).
    setor_aprovador = SetorFactory()
    setor = SetorFactory(superior=setor_aprovador)
    servidor = ServidorFactory(setor=setor)
    chefe = ServidorFactory(setor=setor_aprovador)

    def setores_de_chefia(relacionamento):
        if relacionamento.pk == chefe.pk:
            return Setor.objects.filter(pk__in=[setor.pk, setor_aprovador.pk])
        return Setor.objects.none()

    def setores_pgd():
        return Setor.objects.all()

    monkeypatch.setattr('pgd2.models.considerar_auditoria_centralizada', lambda: False)
    monkeypatch.setattr('pgd2.models.utilizar_integracao_com_ponto', lambda: False)
    monkeypatch.setattr('pgd2.models.get_pendencia_geral_servidor_pgd', lambda *args, **kwargs: False)
    monkeypatch.setattr('pgd2.models.get_setores_pgd', setores_pgd)
    monkeypatch.setattr('pgd2.models.SetorHabilitacao.setor_estah_habilitado', lambda setor: True)
    monkeypatch.setattr('pgd2.models.setores_que_sou_chefe_hoje', setores_de_chefia)
    monkeypatch.setattr(
        'pgd2.models.setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo',
        lambda user, data_inicio, data_fim, apenas_setores=False: (setores_de_chefia(user.get_relacionamento()), Servidor.objects.none()),
    )

    documento_pgd = DocumentoAdesaoServidor.objects.create(descricao='Regras de adesão ao PGD', data_inicio=inicio)
    documento_pes = DocumentoAdesaoPesServidor.objects.create(descricao='Regras de adesão ao PES', data_inicio=inicio)
    perfil = ConfiguracaoPerfilServidor.objects.create(
        categoria=ConfiguracaoPerfilServidor.PERFIL_TAE,
        data_inicio=inicio,
        deve_ter_funcao=False,
    )
    perfil.situacoes.add(servidor.situacao)

    ConfiguracaoOrientacaoPlanoEntregasSetorial.objects.create(
        orientacao='Orientação sistêmica para PES',
        eh_sistemica=True,
        data_inicio=inicio,
    )
    ConfiguracaoOrientacaoPit.objects.create(
        orientacao='Orientação sistêmica para PIT',
        eh_sistemica=True,
        data_inicio=inicio,
    )

    return Pgd2Workflow(
        servidor=servidor,
        chefe=chefe,
        setor=setor,
        setor_aprovador=setor_aprovador,
        inicio=inicio,
        fim=fim,
        documento_pgd=documento_pgd,
        documento_pes=documento_pes,
    )


def criar_periodos(workflow):
    periodo_pes = PeriodoPes.objects.create(
        titulo='PES mensal',
        data_inicio=workflow.inicio,
        data_fim=workflow.fim,
        data_prazo_solicitar_avaliacao_execucao=workflow.fim,
    )
    periodo_pit_rit = PeriodoPitRit.objects.create(
        periodo_pes=periodo_pes,
        titulo='PIT/RIT mensal',
        data_inicio=workflow.inicio,
        data_fim=workflow.fim,
        data_prazo_entrega_pit=workflow.fim,
        data_prazo_entrega_rit=workflow.fim,
        data_prazo_homologacao_pit=workflow.fim,
        data_prazo_homologacao_rit=workflow.fim,
    )
    return periodo_pes, periodo_pit_rit


def criar_pes_em_cadastro(workflow, periodo_pes):
    return PlanoEntregasSetorial.objects.create(
        periodo_pes=periodo_pes,
        setor=workflow.setor,
        doc_insfraestrutura='Estrutura suficiente para teletrabalho.',
        doc_tecnica='Ferramentas digitais institucionais.',
    )


def completar_pes_para_aprovacao(pes, workflow):
    PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.create(
        pes=pes,
        data=workflow.inicio,
        hora_inicio=datetime.time(8),
        hora_final=datetime.time(17),
    )
    PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.create(
        pes=pes,
        data=workflow.inicio,
        hora_inicio=datetime.time(9),
        hora_final=datetime.time(10),
        reuniao=PlanoEntregasSetorialHorarioPlanejamentoSetor.REUNIAO_ONLINE,
    )
    return PlanoEntregasSetorialEntregas.objects.create(
        pes=pes,
        titulo='Entrega institucional',
        descricao='Entrega usada no fluxo de trabalho PGD2.',
        criterios_avaliacao='Entrega avaliada por conclusão.',
        metrica=PlanoEntregasSetorialEntregas.PERCENTUAL,
        meta=100,
        data_prazo=workflow.fim,
    )


def deferir_adesao_pgd(workflow):
    return SolicitacaoAdesaoServidor.objects.create(
        servidor=workflow.servidor,
        documento_adesao=workflow.documento_pgd,
        situacao=SolicitacaoAdesaoServidor.DEFERIDO,
        data_inicio=workflow.inicio,
    )


def deferir_adesao_pes(workflow, adesao_pgd):
    return SolicitacaoAdesaoPesServidor.objects.create(
        adesao=adesao_pgd,
        setor=workflow.setor,
        documento_adesao=workflow.documento_pes,
        situacao=SolicitacaoAdesaoPesServidor.DEFERIDO,
    )


def aprovar_pes(pes, workflow):
    pes.situacao = PlanoEntregasSetorial.APROVADO
    pes.setor_para_aprovacao = workflow.setor_aprovador
    pes.save()
    return pes


class TestWorkflowPgd2:
    def test_pes_avaliado_pode_ser_copiado_para_pes_posterior(self, workflow_pgd2: Pgd2Workflow) -> None:
        periodo_origem = PeriodoPes.objects.create(
            titulo='PES origem',
            data_inicio=workflow_pgd2.inicio - datetime.timedelta(days=60),
            data_fim=workflow_pgd2.inicio - datetime.timedelta(days=31),
            data_prazo_solicitar_avaliacao_execucao=workflow_pgd2.inicio - datetime.timedelta(days=31),
        )
        periodo_destino, _ = criar_periodos(workflow_pgd2)
        pes_origem = aprovar_pes(criar_pes_em_cadastro(workflow_pgd2, periodo_origem), workflow_pgd2)
        pes_origem.situacao_avaliacao = PlanoEntregasSetorial.AVALIADO
        pes_origem.save()
        pes_destino = criar_pes_em_cadastro(workflow_pgd2, periodo_destino)

        pess_copiaveis = pes_destino.get_pess_podem_ser_copiados_para_este()

        assert pess_copiaveis.filter(pk=pes_origem.pk).exists()

    def test_servidor_solicita_adesao_pgd_e_depois_nao_pode_abrir_outra_adesao_vigente(self, workflow_pgd2):
        pode_solicitar, erros = SolicitacaoAdesaoServidor.pode_solicitar(workflow_pgd2.servidor_user, retornar_lista_erros=True)
        assert pode_solicitar, erros

        solicitacao = SolicitacaoAdesaoServidor.objects.create(
            servidor=workflow_pgd2.servidor,
            documento_adesao=workflow_pgd2.documento_pgd,
            situacao=SolicitacaoAdesaoServidor.SOLICITADO,
            data_inicio=workflow_pgd2.inicio,
        )

        pode_solicitar_novamente, erros = SolicitacaoAdesaoServidor.pode_solicitar(
            workflow_pgd2.servidor_user,
            retornar_lista_erros=True,
        )
        assert not pode_solicitar_novamente
        assert 'Solicitado e aguardando análise' in ' '.join(erros)
        assert solicitacao.pode_avaliar(workflow_pgd2.chefe_user)

        solicitacao.situacao = SolicitacaoAdesaoServidor.DEFERIDO
        solicitacao.save()

        assert solicitacao.estah_vigente
        assert SolicitacaoAdesaoServidor.get_vigentes(workflow_pgd2.servidor_user).filter(pk=solicitacao.pk).exists()
        assert not SolicitacaoAdesaoServidor.pode_solicitar(workflow_pgd2.servidor_user)[0]

    def test_chefe_completa_pes_solicita_aprovacao_e_aprovador_aprova_o_plano(self, workflow_pgd2):
        periodo_pes, _ = criar_periodos(workflow_pgd2)
        pes = criar_pes_em_cadastro(workflow_pgd2, periodo_pes)

        pode_solicitar, erros = pes.pode_solicitar_aprovacao(workflow_pgd2.chefe_user, retornar_lista_erros=True)
        assert not pode_solicitar
        assert 'horário de funcionamento' in ' '.join(erros)
        assert 'horário de planejamento' in ' '.join(erros)
        assert 'entrega' in ' '.join(erros)

        completar_pes_para_aprovacao(pes, workflow_pgd2)

        pode_solicitar, erros = pes.pode_solicitar_aprovacao(workflow_pgd2.chefe_user, retornar_lista_erros=True)
        assert pode_solicitar, erros

        pes.situacao = PlanoEntregasSetorial.SOLICITADO_APROVACAO
        pes.setor_para_aprovacao = workflow_pgd2.setor_aprovador
        pes.save()

        pode_aprovar, erros = pes.pode_aprovar(workflow_pgd2.chefe_user, retornar_lista_erros=True)
        assert pode_aprovar, erros

        pes.situacao = PlanoEntregasSetorial.APROVADO
        pes.save()

        assert pes.situacao == PlanoEntregasSetorial.APROVADO
        assert PlanoEntregasSetorial.get_pess_aprovados(workflow_pgd2.setor).filter(pk=pes.pk).exists()

    def test_servidor_cria_pit_chefe_homologa_e_servidor_conclui_rit(self, workflow_pgd2):
        periodo_pes, periodo_pit_rit = criar_periodos(workflow_pgd2)
        pes = aprovar_pes(criar_pes_em_cadastro(workflow_pgd2, periodo_pes), workflow_pgd2)
        entrega_pes = completar_pes_para_aprovacao(pes, workflow_pgd2)
        adesao_pgd = deferir_adesao_pgd(workflow_pgd2)
        deferir_adesao_pes(workflow_pgd2, adesao_pgd)

        pode_finalizar, erros = PlanoIndividualTrabalho.pode_finalizar_cadastro(
            workflow_pgd2.servidor_user,
            periodo_pit_rit,
            adesao_pgd,
            workflow_pgd2.inicio,
            workflow_pgd2.fim,
            retornar_lista_erros=True,
        )
        assert pode_finalizar, erros

        pit = PlanoIndividualTrabalho.objects.create(
            adesao=adesao_pgd,
            periodo_pit_rit=periodo_pit_rit,
            data_inicio=workflow_pgd2.inicio,
            data_fim=workflow_pgd2.fim,
            regime_execucacao=PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_INTEGRAL,
            percentual_teletrabalho=100,
            situacao=PlanoIndividualTrabalho.EM_CADASTRO,
        )
        PitSetores.objects.create(pit=pit, pes=pes, setor=workflow_pgd2.setor, pode_homologar=True)
        PlanoIndividualTrabalhoAtendimento.objects.create(
            pit=pit,
            data=workflow_pgd2.inicio,
            hora_inicio=datetime.time(10),
            hora_final=datetime.time(11),
        )
        entrega_pit = PlanoIndividualTrabalhoEntregas.objects.create(
            pit=pit,
            entrega_pes=entrega_pes,
            titulo='Executar entrega institucional',
            descricao='Trabalho planejado para a entrega institucional.',
            tempo_planejado=Decimal('8'),
            data_prazo=workflow_pgd2.fim,
        )

        pode_solicitar_pit, erros = pit.pode_solicitar_aprovacao_homologacao_pit(workflow_pgd2.servidor_user, retornar_lista_erros=True)
        assert pode_solicitar_pit, erros

        pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(PitSolicitacaoAnalise.PIT)
        pit.refresh_from_db()

        assert pit.situacao == PlanoIndividualTrabalho.AGUARDANDO_PARECER
        assert pit.pode_homologar_pit(workflow_pgd2.chefe_user, considera_pendencia_geral_servidor_pgd=False)

        pit.homologar_pit(Setor.objects.filter(pk=workflow_pgd2.setor.pk), workflow_pgd2.chefe)
        pit.refresh_from_db()
        entrega_pit.refresh_from_db()

        assert pit.situacao == PlanoIndividualTrabalho.HOMOLOGADO
        assert pit.situacao_rit == PlanoIndividualTrabalho.EM_CADASTRO_RIT
        assert entrega_pit.homologado

        RelatorioIndividualTrabalho.objects.create(
            entrega_pit=entrega_pit,
            titulo='Execução da entrega institucional',
            descricao='Entrega executada conforme planejado.',
            tempo_executado=Decimal('8'),
            data_inicio=workflow_pgd2.inicio,
            data_fim=workflow_pgd2.fim,
        )

        # A tela visualizar_rit decompõe pode_cadastrar_entrega() em uma checagem de PIT (feita uma
        # única vez) mais a lista de entregas aptas. As duas formas têm que responder igual.
        pode_cadastrar_entrega_rit = pit.pode_cadastrar_entrega_rit(workflow_pgd2.servidor_user)
        ids_entregas_aptas = set(pit.get_entregas_pit_para_rit().values_list('id', flat=True))
        assert pode_cadastrar_entrega_rit
        assert entrega_pit.pode_cadastrar_entrega(workflow_pgd2.servidor_user) == (entrega_pit.id in ids_entregas_aptas)

        pode_solicitar_rit, erros = pit.pode_solicitar_aprovacao_homologacao_rit(workflow_pgd2.servidor_user, retornar_lista_erros=True)
        assert pode_solicitar_rit, erros

        pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(PitSolicitacaoAnalise.RIT)
        pit.refresh_from_db()

        assert pit.situacao_rit == PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT
        assert pit.pode_homologar_rit(workflow_pgd2.chefe_user, considera_pendencia_geral_servidor_pgd=False)

        homologou = pit.homologar_rit(
            Setor.objects.filter(pk=workflow_pgd2.setor.pk),
            PlanoIndividualTrabalho.AVALIACAO_ADEQUADO_RIT,
            Decimal('8'),
            workflow_pgd2.chefe,
            justificativa='Execução adequada.',
        )
        pit.refresh_from_db()

        assert homologou
        assert pit.situacao_rit == PlanoIndividualTrabalho.HOMOLOGADO_RIT
        assert pit.avaliacao_rit == PlanoIndividualTrabalho.AVALIACAO_ADEQUADO_RIT
        assert pit.tempo_executado_homologado_total == Decimal('8')
        assert not PitSolicitacaoAnaliseSetor.objects.filter(solicitacao__pit=pit, parecer__isnull=True).exists()
