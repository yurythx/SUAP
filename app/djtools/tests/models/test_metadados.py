import enum

from django.contrib.auth.models import Group, Permission
from django.db import models

from boletim_servico.models import BoletimProgramado
from centralservicos.models import Chamado
from comum.models import Vinculo
from djtools.metadados import coletar, deduplicar, models_no_escopo, valor_choice
from djtools.models import EmailEnviadoLog, MetadadoChoice, Task
from edu.models import ComponenteCurricular, RequerimentoAproveitamentoEstudo


def test_valor_choice() -> None:
    class Cor(models.IntegerChoices):
        AZUL = 1

    class Letra(enum.Enum):
        A = 'x'

    assert [valor_choice(v) for v in (True, False, 1, 'A', None, Cor.AZUL, Letra.A)] == ['true', 'false', '1', 'A', None, '1', 'x']


def test_choices_de_componente_curricular() -> None:
    m = coletar(ComponenteCurricular)
    tipo = [(c.tabela, c.valor, c.rotulo) for c in m.choices if c.coluna == 'tipo']
    assert tipo[0] == ('edu_componentecurricular', '1', 'Regular')
    assert len(tipo) == len(ComponenteCurricular._meta.get_field('tipo').choices)


def test_choice_bool() -> None:
    m = coletar(RequerimentoAproveitamentoEstudo)
    assert ('true', 'Nesta instituição') in {(c.valor, c.rotulo) for c in m.choices if c.coluna == 'interno'}


def test_choices_do_base_field_de_array() -> None:
    m = coletar(BoletimProgramado)
    assert {c.coluna for c in m.choices} >= {'nivel_acesso'}


def test_docstring_real_e_assinatura_automatica() -> None:
    assert coletar(Permission).tabela.docstring.startswith('The permissions system')
    assert coletar(ComponenteCurricular).tabela.docstring == ''


def test_atributos_de_campo() -> None:
    campos = {c.campo: c for c in coletar(Task).campos}
    assert (campos['uuid'].default, campos['uuid'].default_callable) == ('uuid.uuid4', True)
    assert campos['start'].editable is False
    assert campos['user'].coluna == 'user_id'
    assert {c.campo: c for c in coletar(EmailEnviadoLog).campos}['data'].auto_now_add is True


def test_generic_foreign_key_e_limit_choices_to() -> None:
    campos = {c.campo: c for c in coletar(Vinculo).campos}
    assert campos['tipo_relacionamento'].generic_foreign_key == 'relacionamento'
    assert campos['id_relacionamento'].generic_foreign_key == 'relacionamento'
    assert campos['tipo_relacionamento'].tabela_relacionada == 'django_content_type'
    assert "('app_label', 'rh')" in campos['tipo_relacionamento'].limit_choices_to


def test_transicoes_de_chamado() -> None:
    m = coletar(Chamado)
    assert ('status', 'cancelar_chamado_transition', '1', '7') in {(t.coluna, t.nome, t.origem, t.destino) for t in m.transicoes}


def test_escopo() -> None:
    escopo = models_no_escopo()
    assert Group.permissions.through in escopo
    assert MetadadoChoice in escopo
    assert not any(m._meta.proxy or not m._meta.managed for m in escopo)


def test_deduplicar_mantem_o_primeiro() -> None:
    a = MetadadoChoice(tabela='t', coluna='c', valor=None, rotulo='A', ordem=0)
    b = MetadadoChoice(tabela='t', coluna='c', valor=None, rotulo='B', ordem=1)
    mantidos, avisos = deduplicar([a, b], lambda c: (c.tabela, c.coluna, c.valor))
    assert mantidos == [a]
    assert len(avisos) == 1
