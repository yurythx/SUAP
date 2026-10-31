"""Testes unitários (sem DB) dos cálculos de CH de ``AtividadeCurricularExtensao``."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from edu.models.atividades import AtividadeCurricularExtensao
from edu.models.cursos import ComponenteCurricular


def test_percentual_ch_vinculada():
    atividade = AtividadeCurricularExtensao()
    atividade.carga_horaria_vinculada = 40
    atividade.carga_horaria = 100
    assert atividade.get_percentual_ch_vinculada() == 40


def test_percentual_ch_vinculada_protege_divisao_por_zero():
    atividade = AtividadeCurricularExtensao()
    atividade.carga_horaria_vinculada = 40
    atividade.carga_horaria = 0
    assert atividade.get_percentual_ch_vinculada() == 0


def test_ch_nao_vinculada_e_a_diferenca():
    with (
        patch.object(AtividadeCurricularExtensao, 'get_carga_horaria', return_value=100),
        patch.object(AtividadeCurricularExtensao, 'get_carga_horaria_vinculada', return_value=40),
    ):
        assert AtividadeCurricularExtensao().get_ch_nao_vinculada() == 60


def test_extra_can_delete_sem_atividade_extensao_generica():
    from edu.models.atividades import AtividadeCurricularExtensaoExtra

    extra = AtividadeCurricularExtensaoExtra()
    extra.pk = 1
    with patch.object(AtividadeCurricularExtensao.objects, 'filter') as mock_filter:
        mock_filter.return_value.first.return_value = None
        assert extra.can_delete() is True


def test_extra_can_delete_quando_nao_requer_distribuicao_ch():
    from edu.models.atividades import AtividadeCurricularExtensaoExtra

    extra = AtividadeCurricularExtensaoExtra()
    extra.pk = 1

    atividade = AtividadeCurricularExtensao()
    atividade.pk = 10
    atividade.requer_distribuicao_ch = False
    atividade.carga_horaria_vinculada = 40

    mock_rel = MagicMock()
    mock_rel.exists.return_value = False

    with (
        patch.object(AtividadeCurricularExtensao.objects, 'filter') as mock_filter,
        patch.object(AtividadeCurricularExtensao, 'atividadecurricularextensao_set', new_callable=PropertyMock, return_value=mock_rel),
    ):
        mock_filter.return_value.first.return_value = atividade
        assert extra.can_delete() is True


def test_extra_can_delete_quando_requer_distribuicao_e_carga_vinculada_zerada():
    from edu.models.atividades import AtividadeCurricularExtensaoExtra

    extra = AtividadeCurricularExtensaoExtra()
    extra.pk = 1

    atividade = AtividadeCurricularExtensao()
    atividade.pk = 10
    atividade.requer_distribuicao_ch = True
    atividade.carga_horaria_vinculada = 0

    mock_rel = MagicMock()
    mock_rel.exists.return_value = False

    with (
        patch.object(AtividadeCurricularExtensao.objects, 'filter') as mock_filter,
        patch.object(AtividadeCurricularExtensao, 'atividadecurricularextensao_set', new_callable=PropertyMock, return_value=mock_rel),
    ):
        mock_filter.return_value.first.return_value = atividade
        assert extra.can_delete() is True


def test_extra_can_delete_bloqueia_quando_requer_distribuicao_e_possui_carga_vinculada():
    from edu.models.atividades import AtividadeCurricularExtensaoExtra

    extra = AtividadeCurricularExtensaoExtra()
    extra.pk = 1

    atividade = AtividadeCurricularExtensao()
    atividade.pk = 10
    atividade.requer_distribuicao_ch = True
    atividade.carga_horaria_vinculada = 30

    mock_rel = MagicMock()
    mock_rel.exists.return_value = False

    with (
        patch.object(AtividadeCurricularExtensao.objects, 'filter') as mock_filter,
        patch.object(AtividadeCurricularExtensao, 'atividadecurricularextensao_set', new_callable=PropertyMock, return_value=mock_rel),
    ):
        mock_filter.return_value.first.return_value = atividade
        assert extra.can_delete() is False


def test_extra_can_delete_bloqueia_quando_substitui_outras_atividades():
    from edu.models.atividades import AtividadeCurricularExtensaoExtra

    extra = AtividadeCurricularExtensaoExtra()
    extra.pk = 1

    atividade = AtividadeCurricularExtensao()
    atividade.pk = 10
    atividade.requer_distribuicao_ch = False

    mock_rel = MagicMock()
    mock_rel.exists.return_value = True

    with (
        patch.object(AtividadeCurricularExtensao.objects, 'filter') as mock_filter,
        patch.object(AtividadeCurricularExtensao, 'atividadecurricularextensao_set', new_callable=PropertyMock, return_value=mock_rel),
    ):
        mock_filter.return_value.first.return_value = atividade
        assert extra.can_delete() is False


def test_extra_delete_recalcula_situacao_do_aluno():
    from unittest.mock import MagicMock, PropertyMock
    from edu.models.atividades import AtividadeCurricularExtensaoExtra

    extra = AtividadeCurricularExtensaoExtra()
    extra.pk = 1
    aluno_mock = MagicMock()
    mp_mock = MagicMock(aluno=aluno_mock)

    with (
        patch.object(AtividadeCurricularExtensaoExtra, 'matricula_periodo', new_callable=PropertyMock, return_value=mp_mock),
        patch.object(AtividadeCurricularExtensao, 'registrar') as mock_registrar,
        patch('djtools.db.models.ModelPlus.delete', return_value=(1, {'edu.AtividadeCurricularExtensaoExtra': 1})),
    ):
        extra.delete.__wrapped__(extra)

        mock_registrar.assert_called_once_with(aluno_mock, AtividadeCurricularExtensaoExtra, 1, 0, None)
        aluno_mock.atualizar_situacao.assert_called_once_with('Exclusão de atividade curricular de extensão extra')


def test_componente_curricular_get_ch_extensao_exigida():
    cc = ComponenteCurricular()
    cc.ch_extensao = 30
    cc.componente_curricular_associado = None
    assert cc.get_ch_extensao() == 30
    assert cc.get_ch_extensao(incluir_associado=True) == 30
    assert cc.get_ch_extensao_exigida() == 30

    cc_associado = ComponenteCurricular()
    cc_associado.tipo = ComponenteCurricular.TIPO_REGULAR
    cc_associado.ch_extensao = 20

    cc.componente_curricular_associado = cc_associado

    assert cc.get_ch_extensao(incluir_associado=False) == 30
    assert cc.get_ch_extensao(incluir_associado=True) == 50
    assert cc.get_ch_extensao_exigida() == 50

    # Quando o associado é do tipo 100% extensão, a CH dele não entra como CH parcial
    cc_associado.tipo = ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
    assert cc.get_ch_extensao(incluir_associado=True) == 30
    assert cc.get_ch_extensao_exigida() == 30


def test_componente_curricular_get_ch_extensao_a_registrar():
    from edu.models.cursos import Componente

    comp_regular = Componente(ch_hora_relogio=60)
    cc = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30, componente=comp_regular)
    cc.componente_curricular_associado = None

    # 1. Componente regular sem associado -> registra ch_extensao (30)
    assert cc.get_ch_extensao_a_registrar() == 30

    # 2. Componente 100% extensão sem associado -> registra componente.ch_hora_relogio (60)
    cc.tipo = ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
    assert cc.get_ch_extensao_a_registrar() == 60

    # 3. Componente regular (30) + associado regular (20) -> registra 50
    cc.tipo = ComponenteCurricular.TIPO_REGULAR
    comp_assoc = Componente(ch_hora_relogio=40)
    cc_assoc = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=20, componente=comp_assoc)
    cc.componente_curricular_associado = cc_assoc
    assert cc.get_ch_extensao_a_registrar() == 50

    # 4. Componente regular (30) + associado 100% extensão (40) -> registra 70 (30 + 40)
    cc_assoc.tipo = ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
    assert cc.get_ch_extensao_a_registrar() == 70

    # 5. Componente com ch_extensao None -> trata como 0 com segurança
    cc.ch_extensao = None
    cc.componente_curricular_associado = None
    assert cc.get_ch_extensao_a_registrar() == 0


@pytest.mark.django_db
def test_matricula_diario_get_situacao_diario_reprova_extensao_com_associado():
    from edu.models.cursos import ComponenteCurricular
    from edu.models.historico import MatriculaDiario
    from edu.tests.factories import (
        AlunoFactory,
        ComponenteCurricularFactory,
        ConfiguracaoAvaliacaoFactory,
        DiarioFactory,
        MatriculaDiarioFactory,
        MatriculaPeriodoFactory,
        MatrizFactory,
        TurmaFactory,
        VinculacaoAtividadeExtensaoFactory,
    )

    ConfiguracaoAvaliacaoFactory()
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    cc_assoc = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=20,
    )
    cc = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc_assoc,
        qtd_avaliacoes=1,
    )
    turma = TurmaFactory(matriz=matriz)
    diario = DiarioFactory(turma=turma, componente_curricular=cc)
    aluno = AlunoFactory(matriz=matriz, curso_campus=turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(
        diario=diario,
        matricula_periodo=mp,
        situacao=MatriculaDiario.SITUACAO_CURSANDO,
    )
    MatriculaDiario.objects.filter(pk=md.pk).update(nota_1=80)
    md.refresh_from_db()

    # 1. CH cumprida de 10h < 20h exigidas (0h do principal + 20h do associado) -> Reprov. Extensão
    VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=10, homologada=True)
    res = md.get_situacao_diario(ignorar_fechamento_carga_horaria=True)
    assert res['constant'] == MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO
    assert res['rotulo'] == 'Reprov. Extensão'

    # 2. CH cumprida adicional de 10h (total de 20h >= 20h exigidas) -> Aprovado
    VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=10, homologada=True)
    res = md.get_situacao_diario(ignorar_fechamento_carga_horaria=True)
    assert res['constant'] == MatriculaDiario.SITUACAO_APROVADO
    assert res['rotulo'] == 'Aprovado'


def test_is_componente_com_extensao_aproveitado_com_associado():
    atividade = AtividadeCurricularExtensao()

    cc_assoc = ComponenteCurricular()
    cc_assoc.tipo = ComponenteCurricular.TIPO_REGULAR
    cc_assoc.ch_extensao = 15

    cc = ComponenteCurricular()
    cc.tipo = ComponenteCurricular.TIPO_REGULAR
    cc.ch_extensao = 0
    cc.componente_curricular_associado = cc_assoc

    referencia = MagicMock()
    referencia.componente_curricular = cc

    mock_tipo = MagicMock(model='aproveitamentoestudo')
    with (
        patch.object(AtividadeCurricularExtensao, 'tipo_referencia', new_callable=PropertyMock, return_value=mock_tipo),
        patch.object(AtividadeCurricularExtensao, 'referencia', new_callable=PropertyMock, return_value=referencia),
    ):
        assert atividade.is_componente_com_extensao_aproveitado() is True


def test_vinculacao_atividade_extensao_get_codigo_situacao():
    from edu.models.historico import VinculacaoAtividadeExtensao

    vinc = VinculacaoAtividadeExtensao()
    vinc.homologada = None
    assert vinc.get_codigo_situacao() == '0'

    vinc.homologada = True
    assert vinc.get_codigo_situacao() == '1'

    vinc.homologada = False
    assert vinc.get_codigo_situacao() == '2'


@pytest.mark.django_db
def test_diario_pode_avaliar_atividade_extensao(sync_permissions):
    from django.contrib.auth.models import Group
    from comum.tests.factories import UserFactory
    from edu.models.diarios import Diario
    from edu.tests.factories import DiarioFactory, ProfessorDiarioFactory, ProfessorFactory

    # 1. Diário em posse do professor (posse_etapa_5 != POSSE_REGISTRO_ESCOLAR)
    diario = DiarioFactory(
        componente_curricular__qtd_avaliacoes=0,
        posse_etapa_5=Diario.POSSE_PROFESSOR,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    prof_user = professor.vinculo.user
    outro_user = UserFactory()

    assert diario.em_posse_do_registro() is False
    # Professor do diário pode avaliar quando não está na posse do registro
    assert diario.pode_avaliar_atividade_extensao(prof_user) is True
    # Usuário sem relação com o diário não pode
    assert diario.pode_avaliar_atividade_extensao(outro_user) is False

    # 2. Diário entregue ao registro escolar (posse_etapa_5 == POSSE_REGISTRO_ESCOLAR)
    diario.posse_etapa_5 = Diario.POSSE_REGISTRO_ESCOLAR
    diario.save()
    assert diario.em_posse_do_registro() is True

    # Professor do diário sem permissão de registro acadêmico perde o acesso
    assert diario.pode_avaliar_atividade_extensao(prof_user) is False

    # Administrador acadêmico com permissão can_change pode avaliar
    admin_user = UserFactory()
    admin_user.groups.add(Group.objects.get(name='Administrador Acadêmico'))
    assert diario.pode_avaliar_atividade_extensao(admin_user) is True

    # Usuário comum sem permissão não pode avaliar
    assert diario.pode_avaliar_atividade_extensao(outro_user) is False


def test_componente_curricular_tem_ch_extensao_exigida():
    # 1. Componente regular com ch_extensao > 0
    cc1 = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30)
    assert cc1.tem_ch_extensao_exigida() is True

    # 2. Componente regular com ch_extensao = 0 e associado regular com ch_extensao = 30
    cc2_assoc = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30)
    cc2 = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=0)
    cc2.componente_curricular_associado = cc2_assoc
    assert cc2.tem_ch_extensao_exigida() is True

    # 3. Componente regular com associado TIPO_ATIVIDADE_EXTENSAO
    cc3_assoc = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=30)
    cc3 = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=0)
    cc3.componente_curricular_associado = cc3_assoc
    assert cc3.tem_ch_extensao_exigida() is False

    # 4. Componente TIPO_ATIVIDADE_EXTENSAO
    cc4 = ComponenteCurricular(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=30)
    assert cc4.tem_ch_extensao_exigida() is False


@pytest.mark.django_db
def test_componente_curricular_objects_com_extensao():
    from edu.models.cursos import ComponenteCurricular
    from edu.models.diarios import Diario
    from edu.tests.factories import (
        ComponenteCurricularFactory,
        ConfiguracaoAvaliacaoFactory,
        DiarioFactory,
    )

    ConfiguracaoAvaliacaoFactory()

    # 1. Componente regular com ch_extensao > 0 -> DEVE ENTRAR
    cc1 = ComponenteCurricularFactory(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30)

    # 2. Componente regular com ch_extensao == 0 cujo associado é REGULAR com ch_extensao > 0 -> DEVE ENTRAR
    cc2_assoc = ComponenteCurricularFactory(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=20)
    cc2 = ComponenteCurricularFactory(
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc2_assoc,
    )

    # 3. Componente regular com associado TIPO_ATIVIDADE_EXTENSAO -> NÃO DEVE ENTRAR
    cc3_assoc = ComponenteCurricularFactory(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=40)
    cc3 = ComponenteCurricularFactory(
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc3_assoc,
    )

    # 4. Componente cujo tipo é TIPO_ATIVIDADE_EXTENSAO -> NÃO DEVE ENTRAR
    cc4 = ComponenteCurricularFactory(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=30)

    # 5. Componente regular sem CH de extensão e sem associado -> NÃO DEVE ENTRAR
    cc5 = ComponenteCurricularFactory(tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=0, componente_curricular_associado=None)

    # 1) Validação direta do QuerySet ComponenteCurricular.objects.com_extensao()
    qs_com_extensao = ComponenteCurricular.objects.com_extensao()
    ids_com_extensao = list(qs_com_extensao.filter(pk__in=[cc1.pk, cc2.pk, cc3.pk, cc4.pk, cc5.pk]).values_list('pk', flat=True))

    assert cc1.pk in ids_com_extensao
    assert cc2.pk in ids_com_extensao
    assert cc3.pk not in ids_com_extensao
    assert cc4.pk not in ids_com_extensao
    assert cc5.pk not in ids_com_extensao

    # 2) Validação do método get_filtro_com_extensao com prefixo via Diario
    d1 = DiarioFactory(componente_curricular=cc1)
    d2 = DiarioFactory(componente_curricular=cc2)
    d3 = DiarioFactory(componente_curricular=cc3)
    d4 = DiarioFactory(componente_curricular=cc4)
    d5 = DiarioFactory(componente_curricular=cc5)

    filtro_prefixado = ComponenteCurricular.get_filtro_com_extensao('componente_curricular')
    ids_diarios_extensao = list(Diario.objects.filter(filtro_prefixado, pk__in=[d1.pk, d2.pk, d3.pk, d4.pk, d5.pk]).values_list('pk', flat=True))

    assert d1.pk in ids_diarios_extensao
    assert d2.pk in ids_diarios_extensao
    assert d3.pk not in ids_diarios_extensao
    assert d4.pk not in ids_diarios_extensao
    assert d5.pk not in ids_diarios_extensao


@pytest.mark.django_db
def test_aluno_get_atividades_extensao_outros_componentes_matricula_diario():
    from edu.models import MatriculaDiario
    from edu.tests.factories import (
        AlunoFactory,
        ComponenteCurricularFactory,
        ConfiguracaoAvaliacaoFactory,
        CursoCampusFactory,
        DiarioFactory,
        MatriculaDiarioFactory,
        MatriculaPeriodoFactory,
        MatrizFactory,
    )

    ConfiguracaoAvaliacaoFactory()
    matriz = MatrizFactory()
    aluno = AlunoFactory(matriz=matriz, curso_campus=CursoCampusFactory())
    mp = MatriculaPeriodoFactory(aluno=aluno)

    cc1 = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30)
    cc2_assoc = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=20)
    cc2 = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc2_assoc,
    )
    cc3_assoc = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=40)
    cc3 = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc3_assoc,
    )
    cc4 = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=0)

    d1 = DiarioFactory(componente_curricular=cc1)
    d2 = DiarioFactory(componente_curricular=cc2)
    d3 = DiarioFactory(componente_curricular=cc3)
    d4 = DiarioFactory(componente_curricular=cc4)

    md1 = MatriculaDiarioFactory(diario=d1, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_APROVADO)
    md2 = MatriculaDiarioFactory(diario=d2, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_APROVADO)
    md3 = MatriculaDiarioFactory(diario=d3, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_APROVADO)
    md4 = MatriculaDiarioFactory(diario=d4, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_APROVADO)

    atv1 = AtividadeCurricularExtensao.registrar(aluno, MatriculaDiario, md1.pk, 30, 'Atv 1', concluida=True, aprovada=True, matricula_periodo=mp)
    atv2 = AtividadeCurricularExtensao.registrar(aluno, MatriculaDiario, md2.pk, 20, 'Atv 2', concluida=True, aprovada=True, matricula_periodo=mp)
    atv3 = AtividadeCurricularExtensao.registrar(aluno, MatriculaDiario, md3.pk, 40, 'Atv 3', concluida=True, aprovada=True, matricula_periodo=mp)
    atv4 = AtividadeCurricularExtensao.registrar(aluno, MatriculaDiario, md4.pk, 60, 'Atv 4', concluida=True, aprovada=True, matricula_periodo=mp)

    qs = aluno.get_atividades_extensao()
    ids_validos = aluno.get_ids_atividades_extensao_outros_componentes_por_tipo(qs, 'matriculadiario')

    assert atv1.pk in ids_validos
    assert atv2.pk in ids_validos
    assert atv3.pk not in ids_validos
    assert atv4.pk not in ids_validos

    outros = aluno.get_atividades_extensao_outros_componentes()
    assert atv1 in outros
    assert atv2 in outros
    assert atv3 not in outros
    assert atv4 not in outros


@pytest.mark.django_db
def test_aluno_get_atividades_extensao_outros_componentes_aproveitamento_estudo():
    from edu.models import AproveitamentoEstudo
    from edu.tests.factories import (
        AlunoFactory,
        AproveitamentoEstudoFactory,
        ComponenteCurricularFactory,
        CursoCampusFactory,
        MatriculaPeriodoFactory,
        MatrizFactory,
    )

    matriz = MatrizFactory()
    aluno = AlunoFactory(matriz=matriz, curso_campus=CursoCampusFactory())
    mp = MatriculaPeriodoFactory(aluno=aluno)

    cc1 = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30)
    cc2_assoc = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=20)
    cc2 = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc2_assoc,
    )
    cc3_assoc = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=40)
    cc3 = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc3_assoc,
    )

    ap1 = AproveitamentoEstudoFactory(matricula_periodo=mp, componente_curricular=cc1)
    ap2 = AproveitamentoEstudoFactory(matricula_periodo=mp, componente_curricular=cc2)
    ap3 = AproveitamentoEstudoFactory(matricula_periodo=mp, componente_curricular=cc3)

    atv1 = AtividadeCurricularExtensao.registrar(aluno, AproveitamentoEstudo, ap1.pk, 30, 'Ap 1', concluida=True, aprovada=True, matricula_periodo=mp)
    atv2 = AtividadeCurricularExtensao.registrar(aluno, AproveitamentoEstudo, ap2.pk, 20, 'Ap 2', concluida=True, aprovada=True, matricula_periodo=mp)
    atv3 = AtividadeCurricularExtensao.registrar(aluno, AproveitamentoEstudo, ap3.pk, 40, 'Ap 3', concluida=True, aprovada=True, matricula_periodo=mp)

    qs = aluno.get_atividades_extensao()
    ids_validos = aluno.get_ids_atividades_extensao_outros_componentes_por_tipo(qs, 'aproveitamentoestudo')

    assert atv1.pk in ids_validos
    assert atv2.pk in ids_validos
    assert atv3.pk not in ids_validos

    outros = aluno.get_atividades_extensao_outros_componentes()
    assert atv1 in outros
    assert atv2 in outros
    assert atv3 not in outros


@pytest.mark.django_db
def test_aluno_get_atividades_extensao_outros_componentes_registro_historico():
    from edu.models import RegistroHistorico
    from edu.tests.factories import (
        AlunoFactory,
        ComponenteCurricularFactory,
        CursoCampusFactory,
        MatriculaPeriodoFactory,
        MatrizFactory,
        RegistroHistoricoFactory,
    )

    matriz = MatrizFactory()
    aluno = AlunoFactory(matriz=matriz, curso_campus=CursoCampusFactory())
    mp = MatriculaPeriodoFactory(aluno=aluno)

    cc1 = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=30)
    cc2_assoc = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_REGULAR, ch_extensao=20)
    cc2 = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc2_assoc,
    )
    cc3_assoc = ComponenteCurricularFactory(matriz=matriz, tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO, ch_extensao=40)
    cc3 = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=0,
        componente_curricular_associado=cc3_assoc,
    )

    rh1 = RegistroHistoricoFactory(matricula_periodo=mp, componente=cc1.componente)
    rh2 = RegistroHistoricoFactory(matricula_periodo=mp, componente=cc2.componente)
    rh3 = RegistroHistoricoFactory(matricula_periodo=mp, componente=cc3.componente)

    atv1 = AtividadeCurricularExtensao.registrar(aluno, RegistroHistorico, rh1.pk, 30, 'RH 1', concluida=True, aprovada=True, matricula_periodo=mp)
    atv2 = AtividadeCurricularExtensao.registrar(aluno, RegistroHistorico, rh2.pk, 20, 'RH 2', concluida=True, aprovada=True, matricula_periodo=mp)
    atv3 = AtividadeCurricularExtensao.registrar(aluno, RegistroHistorico, rh3.pk, 40, 'RH 3', concluida=True, aprovada=True, matricula_periodo=mp)

    qs = aluno.get_atividades_extensao()
    ids_validos = aluno.get_ids_atividades_extensao_outros_componentes_por_tipo(qs, 'registrohistorico')

    assert atv1.pk in ids_validos
    assert atv2.pk in ids_validos
    assert atv3.pk not in ids_validos

    outros = aluno.get_atividades_extensao_outros_componentes()
    assert atv1 in outros
    assert atv2 in outros
    assert atv3 not in outros


@pytest.mark.django_db
def test_vinculacao_atividade_extensao_get_ch_vinculada_outros_e_totais():
    from edu.models import VinculacaoAtividadeExtensao
    from edu.tests.factories import (
        AtividadeCurricularExtensaoFactory,
        MatriculaDiarioFactory,
        VinculacaoAtividadeExtensaoFactory,
    )

    md = MatriculaDiarioFactory()
    atv1 = AtividadeCurricularExtensaoFactory(matricula_periodo=md.matricula_periodo)
    atv2 = AtividadeCurricularExtensaoFactory(matricula_periodo=md.matricula_periodo)
    atv3 = AtividadeCurricularExtensaoFactory(matricula_periodo=md.matricula_periodo)

    v1 = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, atividade_extensao=atv1, carga_horaria=10, homologada=True)
    v2 = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, atividade_extensao=atv2, carga_horaria=15, homologada=None)
    VinculacaoAtividadeExtensaoFactory(matricula_diario=md, atividade_extensao=atv3, carga_horaria=20, homologada=False)

    # 1. get_ch_vinculada_outros para v2 (exclui v2):
    # incluir_pendentes=False -> apenas v1 (homologada=True) -> 10h
    assert v2.get_ch_vinculada_outros(incluir_pendentes=False) == 10

    # incluir_pendentes=True para v1 -> v2 (15h pendente) entra -> 15h
    assert v1.get_ch_vinculada_outros(incluir_pendentes=True) == 15

    # 2. get_totais_ch_por_matricula_diario:
    # excluir_atividade=atv3 (que tem 20h rejeitadas)
    totais_homologados = VinculacaoAtividadeExtensao.get_totais_ch_por_matricula_diario([md.pk], excluir_atividade=atv3, incluir_pendentes=False)
    assert totais_homologados == {md.pk: 10}

    totais_com_pendentes = VinculacaoAtividadeExtensao.get_totais_ch_por_matricula_diario([md.pk], excluir_atividade=atv3, incluir_pendentes=True)
    assert totais_com_pendentes == {md.pk: 25}


@pytest.mark.django_db
def test_matricula_diario_get_situacao_diario_matriz_sem_vinculacao_extensao():
    from edu.models.cursos import ComponenteCurricular
    from edu.models.historico import MatriculaDiario
    from edu.tests.factories import (
        AlunoFactory,
        ComponenteCurricularFactory,
        ConfiguracaoAvaliacaoFactory,
        DiarioFactory,
        MatriculaDiarioFactory,
        MatriculaPeriodoFactory,
        MatrizFactory,
        TurmaFactory,
    )

    ConfiguracaoAvaliacaoFactory()
    # Matriz com requer_vinculacao_extensao_diarios = False
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=False)
    cc = ComponenteCurricularFactory(
        matriz=matriz,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=30,
        qtd_avaliacoes=1,
    )
    turma = TurmaFactory(matriz=matriz)
    diario = DiarioFactory(turma=turma, componente_curricular=cc)
    aluno = AlunoFactory(matriz=matriz, curso_campus=turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(
        diario=diario,
        matricula_periodo=mp,
        situacao=MatriculaDiario.SITUACAO_CURSANDO,
    )
    MatriculaDiario.objects.filter(pk=md.pk).update(nota_1=80)
    md.refresh_from_db()

    # 0h de extensão cumpridas não provocam reprovação porque a matriz não requer vinculação em diários
    res = md.get_situacao_diario(ignorar_fechamento_carga_horaria=True)
    assert res['constant'] == MatriculaDiario.SITUACAO_APROVADO
    assert res['rotulo'] == 'Aprovado'


@pytest.mark.django_db
def test_matricula_diario_get_situacao_diario_aluno_matriz_diferente_diario():
    from edu.models.cursos import ComponenteCurricular
    from edu.models.historico import MatriculaDiario
    from edu.tests.factories import (
        AlunoFactory,
        ComponenteCurricularFactory,
        ComponenteFactory,
        ConfiguracaoAvaliacaoFactory,
        DiarioFactory,
        MatriculaDiarioFactory,
        MatriculaPeriodoFactory,
        MatrizFactory,
        TurmaFactory,
        VinculacaoAtividadeExtensaoFactory,
    )

    ConfiguracaoAvaliacaoFactory()
    componente = ComponenteFactory()

    # Matriz do diário: componente exige 10h de extensão
    matriz_diario = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    cc_diario = ComponenteCurricularFactory(
        matriz=matriz_diario,
        componente=componente,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=10,
        qtd_avaliacoes=1,
    )
    turma = TurmaFactory(matriz=matriz_diario)
    diario = DiarioFactory(turma=turma, componente_curricular=cc_diario)

    # Matriz do aluno: mesmo componente exige 30h de extensão
    matriz_aluno = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    ComponenteCurricularFactory(
        matriz=matriz_aluno,
        componente=componente,
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=30,
        qtd_avaliacoes=1,
    )
    aluno = AlunoFactory(matriz=matriz_aluno, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(
        diario=diario,
        matricula_periodo=mp,
        situacao=MatriculaDiario.SITUACAO_CURSANDO,
    )
    MatriculaDiario.objects.filter(pk=md.pk).update(nota_1=80)
    md.refresh_from_db()

    # 1. Aluno cumpriu 10h (suficiente para o diário, mas insuficiente para os 30h da sua matriz) -> Reprov. Extensão
    VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=10, homologada=True)
    res = md.get_situacao_diario(ignorar_fechamento_carga_horaria=True)
    assert res['constant'] == MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO
    assert res['rotulo'] == 'Reprov. Extensão'

    # 2. Ao cumprir mais 20h (total de 30h = exigência da matriz do aluno) -> Aprovado
    VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=20, homologada=True)
    res = md.get_situacao_diario(ignorar_fechamento_carga_horaria=True)
    assert res['constant'] == MatriculaDiario.SITUACAO_APROVADO
    assert res['rotulo'] == 'Aprovado'


@pytest.mark.django_db
def test_atividade_curricular_extensao_pode_distribuir(sync_permissions):
    from django.contrib.auth.models import AnonymousUser, Group
    from comum.tests.factories import UserFactory
    from edu.tests.factories import AlunoFactory, AtividadeCurricularExtensaoFactory

    aluno = AlunoFactory()
    aluno_user = UserFactory(username=aluno.matricula)
    atividade = AtividadeCurricularExtensaoFactory(matricula_periodo__aluno=aluno)

    # 1. Próprio aluno pode distribuir
    assert atividade.pode_distribuir(aluno_user) is True

    # 2. Outro aluno não pode distribuir
    outro_aluno = AlunoFactory()
    outro_aluno_user = UserFactory(username=outro_aluno.matricula)
    assert atividade.pode_distribuir(outro_aluno_user) is False

    # 3. Administrador acadêmico com permissão pode distribuir
    admin_user = UserFactory()
    admin_user.groups.add(Group.objects.get(name='Administrador Acadêmico'))
    assert atividade.pode_distribuir(admin_user) is True

    # 4. Usuário comum/sem permissão acadêmica não pode distribuir
    user_comum = UserFactory()
    assert atividade.pode_distribuir(user_comum) is False

    # 5. Usuário anônimo ou None não pode distribuir
    assert atividade.pode_distribuir(AnonymousUser()) is False
    assert atividade.pode_distribuir(None) is False
