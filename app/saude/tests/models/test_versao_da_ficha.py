"""TMB e abertura de atendimento leem sempre a versão mais recente da ficha (#17630).

Cada salvamento de uma ficha grava uma linha nova no mesmo atendimento. Os models não têm ``Meta.ordering``,
então ``[0]`` sem ``order_by`` devolvia uma versão arbitrária (em geral a mais antiga).
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User

from edu.models import Aluno
from rh.models import Servidor
from saude.models import (
    AntecedentesFamiliares,
    Antropometria,
    Atendimento,
    AtendimentoNutricao,
    Odontograma,
    ProcessoSaudeDoenca,
    Prontuario,
    SituacaoAtendimento,
    TipoAtendimento,
)
from saude.tests.factories import (
    AntecedentesFamiliaresFactory,
    AntropometriaFactory,
    DoencaFactory,
    OdontogramaFactory,
    ProcessoSaudeDoencaFactory,
)


def _fechar(atendimento: Atendimento) -> Atendimento:
    Atendimento.objects.filter(pk=atendimento.pk).update(situacao=SituacaoAtendimento.FECHADO, data_fechado=datetime.datetime.now())
    atendimento.refresh_from_db()
    return atendimento


@pytest.fixture
def anterior(prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor) -> Atendimento:
    """Atendimento médico/enfermagem já fechado, de onde o próximo herda as fichas."""
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, servidor_profissional.get_user())
    return _fechar(atendimento)


def test_tmb_usa_a_ultima_versao_da_antropometria(prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor) -> None:
    user = servidor_profissional.get_user()
    user.groups.add(Group.objects.get(name='Nutricionista'))
    aluno.pessoa_fisica.sexo = 'M'
    aluno.pessoa_fisica.save()
    atendimento = Atendimento.abrir(TipoAtendimento.NUTRICIONAL, prontuario, aluno, user)
    AntropometriaFactory(atendimento=atendimento, profissional=user, peso=70)
    AntropometriaFactory(atendimento=atendimento, profissional=user, peso=65)
    nutricao = atendimento.atendimentonutricao_set.get()

    tmb_com_historico = nutricao.get_tmb()

    Antropometria.objects.filter(atendimento=atendimento, peso=70).delete()
    assert tmb_com_historico > 0
    assert tmb_com_historico == nutricao.get_tmb()


@pytest.mark.parametrize(
    ('sexo', 'categoria', 'esperado'),
    [
        ('M', None, '1775.36'),
        ('M', AtendimentoNutricao.LEVE, '2751.808'),
        ('M', AtendimentoNutricao.MODERADA, '3160.1408'),
        ('M', AtendimentoNutricao.PESADA, '3728.256'),
        ('F', None, '1572.6'),
        ('F', AtendimentoNutricao.LEVE, '2453.256'),
        ('F', AtendimentoNutricao.MODERADA, '2579.064'),
        ('F', AtendimentoNutricao.PESADA, '2862.132'),
        (None, AtendimentoNutricao.LEVE, '0'),
    ],
)
def test_tmb_por_sexo_e_categoria_de_trabalho(
    prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor, sexo: str | None, categoria: str | None, esperado: str
) -> None:
    """Peso 65 kg, 170 cm e idade 0 (aluno da factory sem data de nascimento)."""
    user = servidor_profissional.get_user()
    aluno.pessoa_fisica.sexo = sexo
    aluno.pessoa_fisica.save()
    atendimento = Atendimento.abrir(TipoAtendimento.NUTRICIONAL, prontuario, aluno, user)
    AntropometriaFactory(atendimento=atendimento, profissional=user, peso=65)
    AtendimentoNutricao.objects.filter(atendimento=atendimento).update(categoria_trabalho=categoria)

    assert AtendimentoNutricao.objects.get(atendimento=atendimento).get_tmb() == Decimal(esperado)


def test_tmb_sem_antropometria_e_zero(prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor) -> None:
    atendimento = Atendimento.abrir(TipoAtendimento.NUTRICIONAL, prontuario, aluno, servidor_profissional.get_user())

    assert atendimento.atendimentonutricao_set.get().get_tmb() == 0


def _abrir_em(dias_atras: int, prontuario: Prontuario, aluno: Aluno, user: User) -> Atendimento:
    """Atendimento médico/enfermagem fechado cuja data de abertura é ``dias_atras`` dias atrás (o id segue a ordem de criação)."""
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    Atendimento.objects.filter(pk=atendimento.pk).update(data_aberto=datetime.datetime.now() - datetime.timedelta(days=dias_atras))
    return _fechar(atendimento)


def test_abrir_copia_do_atendimento_de_abertura_mais_recente_e_nao_do_de_maior_id(
    prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    """#17632: o de maior id (criado por último) foi aberto antes; a origem é o de abertura mais recente."""
    user = servidor_profissional.get_user()
    aberto_depois = _abrir_em(1, prontuario, aluno, user)
    aberto_antes = _abrir_em(10, prontuario, aluno, user)
    assert aberto_antes.pk > aberto_depois.pk
    for atendimento, texto in ((aberto_depois, 'aberto depois'), (aberto_antes, 'aberto antes')):
        ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, que_cirurgia=texto)
        AntecedentesFamiliaresFactory(atendimento=atendimento, profissional=user, tem_agravos_primeiro_grau=texto == 'aberto depois')

    novo = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)

    assert ProcessoSaudeDoenca.objects.get(atendimento=novo).que_cirurgia == 'aberto depois'
    assert AntecedentesFamiliares.objects.get(atendimento=novo).tem_agravos_primeiro_grau is True


def test_abrir_copia_da_avaliacao_biomedica_aberta_mais_recente_que_os_fechados(
    atendimento_aberto: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    user = servidor_profissional.get_user()
    fechado = _abrir_em(10, prontuario, aluno, user)
    ProcessoSaudeDoencaFactory(atendimento=fechado, profissional=user, que_cirurgia='do fechado')
    ProcessoSaudeDoencaFactory(atendimento=atendimento_aberto, profissional=user, que_cirurgia='da biomédica aberta')
    Atendimento.objects.filter(pk=atendimento_aberto.pk).update(data_aberto=datetime.datetime.now() + datetime.timedelta(days=1))

    novo = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)

    assert ProcessoSaudeDoenca.objects.get(atendimento=novo).que_cirurgia == 'da biomédica aberta'


def test_atendimento_anterior_com_ficha_nunca_devolve_o_proprio_atendimento(
    prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    user = servidor_profissional.get_user()
    outro = _abrir_em(10, prontuario, aluno, user)
    proprio = _abrir_em(1, prontuario, aluno, user)
    for atendimento in (outro, proprio):
        ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user)

    assert Atendimento.atendimento_anterior_com_ficha(prontuario, 'processosaudedoenca', proprio) == outro
    ProcessoSaudeDoenca.objects.filter(atendimento=outro).delete()
    assert Atendimento.atendimento_anterior_com_ficha(prontuario, 'processosaudedoenca', proprio) is None


def test_abrir_copia_a_versao_mais_recente_do_saude_doenca_com_as_doencas_dela(
    anterior: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    user = servidor_profissional.get_user()
    antiga, recente = DoencaFactory(), DoencaFactory()
    ficha = {'atendimento': anterior, 'profissional': user}
    ProcessoSaudeDoencaFactory(**ficha, fez_cirurgia=True, que_cirurgia='versão antiga').doencas_cronicas.set([antiga])
    ProcessoSaudeDoencaFactory(**ficha, fez_cirurgia=False, que_cirurgia='versão recente').doencas_cronicas.set([recente])

    novo = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)

    copia = ProcessoSaudeDoenca.objects.get(atendimento=novo)
    assert (copia.fez_cirurgia, copia.que_cirurgia) == (False, 'versão recente')
    assert list(copia.doencas_cronicas.all()) == [recente]


def test_abrir_pega_as_doencas_da_mesma_ficha_de_origem_e_nao_de_outro_atendimento(
    atendimento_aberto: Atendimento, anterior: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    """A biomédica aberta (``data_fechado`` NULL) vem primeiro por ``-data_fechado``, mas a ficha vem do maior id."""
    user = servidor_profissional.get_user()
    da_aberta, do_anterior = DoencaFactory(), DoencaFactory()
    ProcessoSaudeDoencaFactory(atendimento=atendimento_aberto, profissional=user, que_cirurgia='da aberta').doencas_cronicas.set([da_aberta])
    ProcessoSaudeDoencaFactory(atendimento=anterior, profissional=user, que_cirurgia='do anterior').doencas_cronicas.set([do_anterior])
    assert anterior.pk > atendimento_aberto.pk

    novo = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)

    copia = ProcessoSaudeDoenca.objects.get(atendimento=novo)
    assert copia.que_cirurgia == 'do anterior'
    assert list(copia.doencas_cronicas.all()) == [do_anterior]


def test_abrir_copia_a_versao_mais_recente_dos_antecedentes_familiares(
    anterior: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    user = servidor_profissional.get_user()
    antiga, recente = DoencaFactory(), DoencaFactory()
    ficha = {'atendimento': anterior, 'profissional': user}
    AntecedentesFamiliaresFactory(**ficha, tem_agravos_primeiro_grau=True).agravos_primeiro_grau.set([antiga])
    AntecedentesFamiliaresFactory(**ficha, tem_agravos_primeiro_grau=False).agravos_primeiro_grau.set([recente])

    novo = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)

    copia = AntecedentesFamiliares.objects.get(atendimento=novo)
    assert copia.tem_agravos_primeiro_grau is False
    assert list(copia.agravos_primeiro_grau.all()) == [recente]


def test_abrir_odontologico_copia_a_versao_mais_recente_do_odontograma(prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor) -> None:
    user = servidor_profissional.get_user()
    anterior = Atendimento.abrir(TipoAtendimento.ODONTOLOGICO, prontuario, aluno, user)
    Odontograma.objects.filter(atendimento=anterior).delete()
    OdontogramaFactory(atendimento=anterior, profissional=user, dentes_alterados='versão antiga')
    OdontogramaFactory(atendimento=anterior, profissional=user, dentes_alterados='versão recente')
    _fechar(anterior)

    novo = Atendimento.abrir(TipoAtendimento.ODONTOLOGICO, prontuario, aluno, user)

    assert Odontograma.objects.get(atendimento=novo).dentes_alterados == 'versão recente'
