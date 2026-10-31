# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``estagios``.

``PraticaProfissional`` e ``RelatorioSemestralEstagio`` são gravados por ``bulk_create``: o ``save``
de ambos recalcula pendências, registra a atividade de prática profissional do aluno e dispara
notificações, e o do relatório não aceita os kwargs que o ``Manager.create`` repassa.
"""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from edu.tests.factories import AlunoFactory, CursoCampusFactory, ProfessorFactory, TurnoFactory
from estagios.models import PraticaProfissional, RelatorioSemestralEstagio
from rh.tests.factories import PessoaJuridicaFactory


class _BulkCreateFactory(DjangoModelFactory):
    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class: type, *args: object, **kwargs: object) -> object:
        return model_class._default_manager.bulk_create([model_class(*args, **kwargs)])[0]


class PraticaProfissionalFactory(_BulkCreateFactory):
    """Estágio em andamento: começou há 4 meses e termina daqui a 1, ou seja, um único período semestral já no prazo de relatório."""

    class Meta:
        model = PraticaProfissional

    aluno = factory.SubFactory(AlunoFactory, curso_campus=factory.SubFactory(CursoCampusFactory))
    orientador = factory.SubFactory(ProfessorFactory)
    empresa = factory.LazyFunction(lambda: PessoaJuridicaFactory().get_vinculo())
    turno = factory.SubFactory(TurnoFactory)
    obrigatorio = False
    data_inicio = factory.LazyFunction(lambda: datetime.date.today() - datetime.timedelta(days=120))
    data_prevista_fim = factory.LazyFunction(lambda: datetime.date.today() + datetime.timedelta(days=30))
    ch_semanal = 20
    numero_seguro = '123'
    nome_supervisor = 'Supervisor'
    telefone_supervisor = '84999999999'
    cargo_supervisor = 'Gerente'
    email_supervisor = 'supervisor@example.com'


class RelatorioSemestralEstagioFactory(_BulkCreateFactory):
    """Relatório eletrônico (sem PDF anexado) do estagiário; ``eh_relatorio_do_supervisor=True`` para o do supervisor."""

    class Meta:
        model = RelatorioSemestralEstagio

    pratica_profissional = factory.SubFactory(PraticaProfissionalFactory)
    eh_relatorio_do_supervisor = False
    data_relatorio = factory.LazyFunction(datetime.date.today)
    inicio = factory.SelfAttribute('pratica_profissional.data_inicio')
    fim = factory.SelfAttribute('pratica_profissional.data_prevista_fim')
    relatorio = ''
