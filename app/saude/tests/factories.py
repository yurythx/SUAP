"""Factories dos models do app ``saude``."""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from rh.tests.factories import SetorFactory
from saude.models import (
    AcuidadeVisual,
    AntecedentesFamiliares,
    Antropometria,
    Cid,
    DesenvolvimentoPessoal,
    DificuldadeOral,
    Doenca,
    Droga,
    Especialidades,
    ExameFisico,
    GrupoAlimento,
    HabitosDeVida,
    HipoteseDiagnostica,
    HorarioAtendimento,
    MetodoContraceptivo,
    NutricaoAlimentacao,
    Odontograma,
    PercepcaoSaudeBucal,
    PlanoAlimentar,
    ProcessoSaudeDoenca,
    SinaisVitais,
)


class HorarioAtendimentoFactory(DjangoModelFactory):
    """Horário livre da agenda de atendimentos, num campus próprio."""

    class Meta:
        model = HorarioAtendimento

    data = factory.LazyFunction(datetime.date.today)
    hora_inicio = datetime.time(9, 0)
    hora_termino = datetime.time(9, 30)
    cadastrado_em = factory.LazyFunction(datetime.datetime.now)
    especialidade = Especialidades.MEDICO
    campus = factory.LazyFunction(lambda: SetorFactory().uo)


# Cadastros de apoio das fichas (opções de M2M/FK).


class DoencaFactory(DjangoModelFactory):
    class Meta:
        model = Doenca
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Doença {n}')


class DrogaFactory(DjangoModelFactory):
    class Meta:
        model = Droga
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Droga {n}')


class MetodoContraceptivoFactory(DjangoModelFactory):
    class Meta:
        model = MetodoContraceptivo
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Método {n}')


class DificuldadeOralFactory(DjangoModelFactory):
    class Meta:
        model = DificuldadeOral
        django_get_or_create = ('dificuldade',)

    dificuldade = factory.Sequence(lambda n: f'Dificuldade {n}')


# Fichas da avaliação biomédica: `atendimento` e `profissional` vêm de quem chama.


class AcuidadeVisualFactory(DjangoModelFactory):
    class Meta:
        model = AcuidadeVisual


class AntropometriaFactory(DjangoModelFactory):
    class Meta:
        model = Antropometria

    estatura = 170
    peso = 70
    cintura = 80
    quadril = 95


class DesenvolvimentoPessoalFactory(DjangoModelFactory):
    class Meta:
        model = DesenvolvimentoPessoal


class ExameFisicoFactory(DjangoModelFactory):
    class Meta:
        model = ExameFisico


class HabitosDeVidaFactory(DjangoModelFactory):
    """``respondida=True``: ficha com todas as perguntas dos 18 gráficos respondidas com "sim".

    Inclui as que o form atual não grava (Demanda 2301), sem as quais o gráfico some (#17622), e as que o form
    atual grava (#17624), mais a ficha de nutrição do mesmo atendimento (refeições por dia).
    """

    class Meta:
        model = HabitosDeVida

    class Params:
        respondida = factory.Trait(
            atividade_fisica=True,
            frequencia_semanal=3,
            duracao_atividade=3,
            fuma=True,
            bebe=True,
            frequencia_bebida=2,
            usa_drogas=True,
            que_drogas=factory.PostGeneration(lambda ficha, create, extraido, **kwargs: ficha.que_drogas.add(DrogaFactory())),
            dificuldade_dormir=True,
            horas_sono=3,
            refeicoes_por_dia=4,
            vida_sexual_ativa=True,
            metodo_contraceptivo=True,
            qual_metodo_contraceptivo=factory.PostGeneration(
                lambda ficha, create, extraido, **kwargs: ficha.qual_metodo_contraceptivo.add(MetodoContraceptivoFactory())
            ),
            uso_internet=True,
            tempo_uso_internet=2,
            objetivo_uso_internet='Jogos,Redes Sociais',
            frequencia_uso_bebida=HabitosDeVida.FrequenciaUso.DUAS_SEMANA,
            nutricao=factory.PostGeneration(
                lambda ficha, create, extraido, **kwargs: NutricaoAlimentacaoFactory(atendimento=ficha.atendimento, profissional=ficha.profissional)
            ),
        )


def _grau_e_motivo_das_dificuldades(grau: int) -> dict:
    motivo = factory.SubFactory(DificuldadeOralFactory, dificuldade='Dor')
    respostas = {}
    for sufixo in ('sorrir', 'falar', 'comer', 'relacionar', 'manter_humor', 'estudar', 'trabalhar', 'higienizar', 'dormir'):
        respostas[f'grau_dificuldade_{sufixo}'] = grau
        respostas[f'motivo_dificuldade_{sufixo}'] = motivo
    return respostas


class PercepcaoSaudeBucalFactory(DjangoModelFactory):
    """``respondida=True``: ficha com todas as perguntas dos 29 gráficos respondidas.

    Inclui as que o form atual não grava (Demanda 2301), sem as quais o gráfico some (#17622), e as que o form
    atual grava (#17624). Ficha que nenhum form grava: serve só para montar todos os gráficos de uma vez.
    """

    class Meta:
        model = PercepcaoSaudeBucal

    class Params:
        respondida = factory.Trait(
            foi_dentista_anteriormente=True,
            tempo_ultima_vez_dentista=2,
            qtd_vezes_fio_dental_ultima_semana=3,
            qtd_dias_consumiu_doce_ultima_semana=2,
            dificuldades=True,
            **_grau_e_motivo_das_dificuldades(grau=1),
            # Perguntas do form atual (#17624).
            usa_fio_dental=True,
            qts_dias_fio_dental_ultima_semana=3,
            qtd_por_dia_consome_acucar=PercepcaoSaudeBucal.FrequenciaDoces.UMA_VEZ,
            motivo_dificuldade_estudar_trabalhar=factory.SubFactory(DificuldadeOralFactory, dificuldade='Dor'),
        )


class ProcessoSaudeDoencaFactory(DjangoModelFactory):
    class Meta:
        model = ProcessoSaudeDoenca


class CidFactory(DjangoModelFactory):
    class Meta:
        model = Cid
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'A{n % 100:02d}')
    denominacao = factory.Sequence(lambda n: f'Diagnóstico {n}')


class HipoteseDiagnosticaFactory(DjangoModelFactory):
    class Meta:
        model = HipoteseDiagnostica

    cid = factory.SubFactory(CidFactory)


class SinaisVitaisFactory(DjangoModelFactory):
    class Meta:
        model = SinaisVitais


class AntecedentesFamiliaresFactory(DjangoModelFactory):
    class Meta:
        model = AntecedentesFamiliares

    @factory.post_generation
    def agravos_primeiro_grau(self, create: bool, extracted: list | None, **kwargs: object) -> None:
        if create and extracted:
            self.agravos_primeiro_grau.set(extracted)


class OdontogramaFactory(DjangoModelFactory):
    class Meta:
        model = Odontograma

    dentes_alterados = ''


class PlanoAlimentarFactory(DjangoModelFactory):
    class Meta:
        model = PlanoAlimentar


class GrupoAlimentoFactory(DjangoModelFactory):
    class Meta:
        model = GrupoAlimento
        django_get_or_create = ('descricao',)

    descricao = factory.Sequence(lambda n: f'Grupo de alimentos {n}')


class NutricaoAlimentacaoFactory(DjangoModelFactory):
    """Ficha de nutrição da avaliação (os campos de texto obrigatórios já vêm com resposta)."""

    class Meta:
        model = NutricaoAlimentacao

    refeicoes_por_dia = NutricaoAlimentacao.RefeicaoDia.TRES
    faz_refeicao_distraido = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_feijao_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_frutas_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_verduras_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_hamburguer_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_bebidas_adocadas_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_macarrao_instantaneo_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
    consumiu_biscoito_ontem = NutricaoAlimentacao.SIMNAOTALVEZ.NAO
