"""Plano alimentar impresso e cópia do saúde-doença leem a versão mais recente da ficha (#17630).

Cada salvamento de uma ficha grava uma linha nova no mesmo atendimento. Os models não têm ``Meta.ordering``,
então ``[0]`` sem ``order_by`` devolvia uma versão arbitrária (em geral a mais antiga).
"""

import datetime

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from edu.models import Aluno
from rh.models import Servidor
from saude.models import Atendimento, Prontuario, SituacaoAtendimento, TipoAtendimento
from saude.tests.factories import AntropometriaFactory, PlanoAlimentarFactory, ProcessoSaudeDoencaFactory


@pytest.fixture
def nutricionista(profissional: Client, servidor_profissional: Servidor) -> Client:
    servidor_profissional.get_user().groups.add(Group.objects.get(name='Nutricionista'))
    return profissional


def _atendimento_nutricional(servidor: Servidor) -> Atendimento:
    """Atendimento do próprio servidor (sem aluno, a view imprime o campus do usuário)."""
    return Atendimento.abrir(TipoAtendimento.NUTRICIONAL, Prontuario.get_prontuario(servidor.get_vinculo()), servidor, servidor.get_user())


def test_plano_alimentar_impresso_mostra_a_ultima_antropometria(nutricionista: Client, servidor_profissional: Servidor) -> None:
    user = servidor_profissional.get_user()
    atendimento = _atendimento_nutricional(servidor_profissional)
    AntropometriaFactory(atendimento=atendimento, profissional=user, peso=70)
    AntropometriaFactory(atendimento=atendimento, profissional=user, peso=65)
    plano = PlanoAlimentarFactory(atendimento=atendimento, profissional=user)

    resposta = nutricionista.get(f'/saude/imprimir_plano_alimentar/{plano.pk}/')

    assert resposta.status_code == 200
    assert resposta.context['peso'] == '65.00 kg'


def test_plano_alimentar_impresso_sem_antropometria_nao_quebra(nutricionista: Client, servidor_profissional: Servidor) -> None:
    atendimento = _atendimento_nutricional(servidor_profissional)
    plano = PlanoAlimentarFactory(atendimento=atendimento, profissional=servidor_profissional.get_user())

    resposta = nutricionista.get(f'/saude/imprimir_plano_alimentar/{plano.pk}/')

    assert resposta.status_code == 200
    assert 'peso' not in resposta.context


def test_saude_doenca_da_biomedica_abre_preenchido_com_a_ultima_versao_do_atendimento_anterior(
    profissional: Client, atendimento_aberto: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    user = servidor_profissional.get_user()
    anterior = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    ficha = {'atendimento': anterior, 'profissional': user}
    ProcessoSaudeDoencaFactory(**ficha, que_cirurgia='versão antiga')
    ProcessoSaudeDoencaFactory(**ficha, que_cirurgia='versão recente')
    Atendimento.objects.filter(pk=anterior.pk).update(situacao=SituacaoAtendimento.FECHADO, data_fechado=datetime.datetime.now())

    resposta = profissional.get(f'/saude/adicionar_processosaudedoenca/{atendimento_aberto.pk}/')

    assert resposta.status_code == 200
    assert resposta.context['form'].instance.que_cirurgia == 'versão recente'


def _anterior(dias_atras: int, texto: str, prontuario: Prontuario, aluno: Aluno, user: User, **datas: datetime.datetime) -> Atendimento:
    """Atendimento médico/enfermagem fechado, aberto ``dias_atras`` dias atrás, com um saúde-doença ``texto``."""
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    abertura = datetime.datetime.now() - datetime.timedelta(days=dias_atras)
    Atendimento.objects.filter(pk=atendimento.pk).update(
        situacao=SituacaoAtendimento.FECHADO, data_aberto=abertura, **{'data_fechado': abertura, **datas}
    )
    ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, que_cirurgia=texto)
    return atendimento


def test_saude_doenca_da_biomedica_copia_do_atendimento_de_abertura_mais_recente_e_nao_do_de_fechamento_mais_recente(
    profissional: Client, atendimento_aberto: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    """#17632: o aberto antes foi fechado por último (maior ``data_fechado``); a origem é o de abertura mais recente."""
    user = servidor_profissional.get_user()
    agora = datetime.datetime.now()
    _anterior(10, 'aberto antes', prontuario, aluno, user, data_fechado=agora)
    _anterior(2, 'aberto depois', prontuario, aluno, user, data_fechado=agora - datetime.timedelta(days=5))

    resposta = profissional.get(f'/saude/adicionar_processosaudedoenca/{atendimento_aberto.pk}/')

    assert resposta.context['form'].instance.que_cirurgia == 'aberto depois'


def test_saude_doenca_da_biomedica_copia_de_outra_biomedica_aberta_mais_recente_que_os_fechados(
    profissional: Client, atendimento_aberto: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor
) -> None:
    user = servidor_profissional.get_user()
    _anterior(10, 'do fechado', prontuario, aluno, user)
    # só pode haver uma biomédica aberta por prontuário (``abrir`` barra a segunda): promove um atendimento aberto a biomédica
    outra = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    Atendimento.objects.filter(pk=outra.pk).update(tipo=TipoAtendimento.AVALIACAO_BIOMEDICA, data_aberto=datetime.datetime.now())
    ProcessoSaudeDoencaFactory(atendimento=outra, profissional=user, que_cirurgia='da outra biomédica aberta')

    resposta = profissional.get(f'/saude/adicionar_processosaudedoenca/{atendimento_aberto.pk}/')

    assert resposta.context['form'].instance.que_cirurgia == 'da outra biomédica aberta'


def test_saude_doenca_da_biomedica_nao_copia_dela_mesma_e_abre_em_branco_sem_anterior(
    profissional: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor
) -> None:
    resposta = profissional.get(f'/saude/adicionar_processosaudedoenca/{atendimento_aberto.pk}/')

    assert resposta.status_code == 200
    assert resposta.context['form'].instance.pk is None
