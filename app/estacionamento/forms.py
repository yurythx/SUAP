from comum.models import Configuracao, Municipio, Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from estacionamento.models import Veiculo, VeiculoCombustivel, VeiculoCor, VeiculoMarca, VeiculoModelo


class VeiculoModeloForm(forms.ModelFormPlus):
    nome = forms.CapitalizeTextField(label='Nome', max_length=20)

    class Meta:
        model = VeiculoModelo
        exclude = ()


class VeiculoCorForm(forms.ModelFormPlus):
    nome = forms.CapitalizeTextField(label='Nome', max_length=20)

    class Meta:
        model = VeiculoCor
        exclude = ()


class VeiculoCombustivelForm(forms.ModelFormPlus):
    nome = forms.CapitalizeTextField(label='Nome', max_length=20)

    class Meta:
        model = VeiculoCombustivel
        exclude = ()


class VeiculoMarcaForm(forms.ModelFormPlus):
    nome = forms.CapitalizeTextField(label='Nome', max_length=20)

    class Meta:
        model = VeiculoMarca
        exclude = ()


class VeiculoForm(forms.ModelFormPlus):
    # modelo = forms.ModelChoiceField(label=u'Modelo', queryset=VeiculoModelo.objects.all())
    ano_fabric = forms.IntegerFieldPlus(label='Ano', help_text='Ano de Fabricação, ex: 2010', max_length=4)
    placa_codigo_atual = forms.BrPlacaVeicularField(label='Placa', help_text='ex: "AAA-1111 (Padrão Antigo)" ou "AAA1A11 (Padrão Mercosul)"')
    placa_municipio_atual = forms.ModelChoiceField(
        label='Localização',
        queryset=Municipio.objects.all(),
        widget=AutocompleteWidget(search_fields=Municipio.SEARCH_FIELDS, show=False, help_text='ex: RN - Natal'),
        required=False,
    )
    vinculos_condutores = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects.all(), label='Condutores')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'placa_municipio_atual'
        ].help_text = (
            f'ex: {Configuracao.get_valor_por_chave("comum", "instituicao_estado")} - {Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
        )

    class Meta:
        model = Veiculo
        fields = (
            'modelo',
            'cor',
            'ano_fabric',
            'placa_codigo_atual',
            'placa_municipio_atual',
            'vinculos_condutores',
        )
