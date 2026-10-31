"""Quantidades de material permanente são inteiras: cada unidade vira um tombamento.

Regressão do Sentry SUAP-VP8: com `qtd` decimal, `EntradaPermanente.save()` chamava
`range(proximo_numero, proximo_numero + self.qtd)` e estourava
`TypeError: 'decimal.Decimal' object cannot be interpreted as an integer`.
"""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError

from almoxarifado.forms import EmpenhoPermanenteForm

Empenho = apps.get_model('almoxarifado', 'Empenho')
EmpenhoPermanente = apps.get_model('patrimonio', 'EmpenhoPermanente')
EntradaPermanente = apps.get_model('patrimonio', 'EntradaPermanente')
MaterialTipo = apps.get_model('almoxarifado', 'MaterialTipo')

pytestmark = pytest.mark.django_db

OPERADOR = 'Operador de Almoxarifado'


def _adicionar_item(contexto, qtd):
    return contexto.client.post(
        f'/almoxarifado/entrada/{contexto.entrada.pk}/adicionar_item/',
        {'categoria': contexto.categoria.pk, 'descricao': 'Notebook doado', 'qtd': qtd, 'valor': '1.000,000000'},
    )


def _empenhar(contexto, qtd_empenhada, valor='100.00'):
    empenho = Empenho.objects.create(
        uo=contexto.campus,
        numero=f'2019NE{Empenho.objects.count():06d}',
        tipo_material=MaterialTipo.PERMANENTE(),
    )
    item = EmpenhoPermanente.objects.create(
        empenho=empenho, categoria=contexto.categoria, descricao='Notebook empenhado', qtd_empenhada=qtd_empenhada, valor=valor
    )
    return empenho, item


@pytest.mark.parametrize(
    ('modelo', 'nome_do_campo'),
    [
        (EntradaPermanente, 'qtd'),
        (EmpenhoPermanente, 'qtd_empenhada'),
        (EmpenhoPermanente, 'qtd_adquirida'),
    ],
)
def test_quantidades_de_permanente_sao_inteiras_no_modelo(modelo, nome_do_campo):
    campo = modelo._meta.get_field(nome_do_campo)

    assert campo.get_internal_type() == 'PositiveIntegerField'


def test_formulario_de_empenho_permanente_recusa_qtd_fracionaria():
    """`qtd_adquirida` é a soma das `EntradaPermanente.qtd`; empenhar fração reabriria a fresta."""
    campo = EmpenhoPermanenteForm.base_fields['qtd_empenhada']

    assert campo.clean('2') == 2
    for invalido in ('2,5', '2.5', '0'):
        with pytest.raises(ValidationError):
            campo.clean(invalido)


def test_save_gera_um_inventario_por_unidade(patrimonio_context):
    item = EntradaPermanente.objects.create(
        entrada=patrimonio_context.entrada, categoria=patrimonio_context.categoria, descricao='Notebook doado', qtd=3, valor='100.00'
    )

    assert item.inventario_set.count() == 3


@pytest.mark.parametrize('qtd', ['2,5', '2.5', '-1'])
def test_formulario_recusa_qtd_nao_inteira(patrimonio_context, qtd):
    patrimonio_context.login(patrimonio_context.servidor, OPERADOR)
    itens_antes = EntradaPermanente.objects.count()

    resposta = _adicionar_item(patrimonio_context, qtd)

    assert resposta.status_code == 200
    assert EntradaPermanente.objects.count() == itens_antes


def test_formulario_aceita_qtd_inteira(patrimonio_context):
    patrimonio_context.login(patrimonio_context.servidor, OPERADOR)

    resposta = _adicionar_item(patrimonio_context, '2')

    assert resposta.status_code == 302
    item = EntradaPermanente.objects.get(descricao='Notebook doado')
    assert item.inventario_set.count() == 2


def test_valores_do_empenho_permanente_agregam_com_qtd_inteira(patrimonio_context):
    """`Sum(F('valor') * F('qtd_empenhada'))` precisa de `output_field` desde que a qtd virou inteira.

    Sem ele o Django recusa a expressão de tipos mistos (`FieldError`) e a tela de empenho quebra.
    """
    empenho, _ = _empenhar(patrimonio_context, qtd_empenhada=3, valor='100.00')

    categorias = empenho.get_categoria_empenho()

    assert [item['categoria'] for item in categorias] == [patrimonio_context.categoria]
    assert categorias[0]['valor'] == '300,00'


def test_qtd_pendente_do_empenho_permanente_e_inteira(patrimonio_context):
    _, item = _empenhar(patrimonio_context, qtd_empenhada=5)

    assert item.get_qtd_pendente() == 5
    assert isinstance(item.get_qtd_pendente(), int)
