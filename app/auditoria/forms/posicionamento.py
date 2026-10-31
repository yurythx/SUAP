from django.db import transaction

from auditoria.papeis import get_auditores_ativos
from comum.models import Vinculo
from tinymce.widgets import TinyMCE
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget

from ..models import Manifestacao, Motivacao, Posicionamento, ProrrogacaoPrazo, RevisaoPosicionamento, TipoPosicionamento, TipoPosicionamentoValido


class PosicionamentoForm(forms.ModelFormPlus):
    manifestacao = forms.ModelChoiceField(label='Manifestação', queryset=Manifestacao.objects.none())
    tipo = forms.ChoiceField(label='Posicionamento', choices=TipoPosicionamento.choices)
    motivacao = forms.ModelChoiceFieldPlus(
        queryset=Motivacao.objects,
        widget=AutocompleteWidget(
            multiple=False,
            form_filters=[
                ('tipo', 'tipo_posicionamento__in'),
            ],
        ),
        label='Motivação',
        required=True,
    )
    outros = forms.CharField(required=False, label='Justificativa', widget=forms.TextInput(attrs={'id': 'id_descricao_outros'}))
    parecer = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), label='Parecer do auditor', required=True
    )

    fieldsets = (('Dados gerais', {'fields': ('manifestacao', 'tipo', 'motivacao', 'outros')}), ('Parecer', {'fields': ('parecer',)}))

    class Meta:
        model = Posicionamento
        fields = ('manifestacao', 'tipo', 'motivacao', 'outros', 'parecer')

    def __init__(self, *args, **kwargs):
        self.instance: Posicionamento = kwargs.get('instance')
        self.manifestacao: Manifestacao = kwargs.pop('manifestacao', self.instance.manifestacao if self.instance else None)
        super().__init__(*args, **kwargs)
        self.fields['manifestacao'].queryset = Manifestacao.objects.filter(id=self.manifestacao.id)
        self.fields['manifestacao'].initial = self.manifestacao.id
        self.fields['manifestacao'].widget.attrs['readonly'] = True
        tipos_validos = TipoPosicionamentoValido.objects.filter(tipo_manifestacao=self.manifestacao.tipo)
        tipos_validos = [tipo.tipo_posicionamento for tipo in tipos_validos]
        self.fields['tipo'].choices = [(choice, label) for choice, label in self.fields['tipo'].choices if choice in tipos_validos]
        self.fields['motivacao'].widget.attrs['id'] = 'id_motivacao'  # Adicionar o ID ao widget do Select2

    def verificar_motivacao(self):
        motivacao = self.cleaned_data['motivacao']
        tipo_posicionamento = self.cleaned_data['tipo_posicionamento']
        if motivacao.tipo != tipo_posicionamento:
            self.add_error('motivacao', 'Motivação inválida para o tipo de posicionamento selecionado')

    def clean(self):
        cleaned_data = super().clean()
        motivacao = cleaned_data.get('motivacao')
        descricao_outros = cleaned_data.get('outros')
        if motivacao == 'Outros' and not descricao_outros:
            raise self.add_error('É necessário fornecer uma descrição para o motivo "Outros"')
        return cleaned_data


class ProrrogacaoPosicionamentoForm(PosicionamentoForm):
    data_limite = forms.DateFieldPlus(label='Data Limite da Recomendação')
    prazo_solicitado = forms.DateFieldPlus(label='Prazo Solicitado')
    prazo_atual = forms.DateFieldPlus(label='Prazo Atual')
    definir_prazo = forms.BooleanField(label='Definir um prazo', required=False, help_text='Marque se deseja informar outro prazo')
    prazo = forms.DateFieldPlus(label='Prazo Concedido', required=False)

    fieldsets = (
        ('Dados gerais', {'fields': ('manifestacao', 'tipo', 'motivacao', 'outros', 'data_limite')}),
        (
            'Cronograma',
            {
                'fields': (
                    (
                        'prazo_solicitado',
                        'prazo_atual',
                    ),
                    ('definir_prazo', 'prazo'),
                )
            },
        ),
        ('Parecer', {'fields': ('parecer',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = self.request.user
        self.fields['prazo_solicitado'].initial = self.manifestacao.prazo_solicitado
        self.fields['prazo_atual'].initial = self.manifestacao.prazo_atual
        self.fields['data_limite'].initial = self.manifestacao.data_limite
        #
        self.fields['data_limite'].widget.attrs['readonly'] = True
        self.fields['prazo_solicitado'].widget.attrs['readonly'] = True
        self.fields['prazo_atual'].widget.attrs['readonly'] = True

    def clean(self):
        cleaned_data = super().clean()
        definir_prazo = cleaned_data.get('definir_prazo')
        prazo_concedido = cleaned_data.get('prazo')
        prazo_solicitado = cleaned_data.get('prazo_solicitado')
        data_limite = self.manifestacao.data_limite
        if definir_prazo:
            if not prazo_concedido:
                self.add_error('prazo', 'É necessário fornecer um novo prazo')
            elif prazo_concedido > data_limite:
                self.add_error('prazo', f'O prazo não pode ser maior que a data limite da recomendação:{data_limite}')
        #
        # Use o valor de prazo_concedido ou prazo_solicitado conforme necessário
        cleaned_data['prazo_final'] = prazo_concedido if definir_prazo else prazo_solicitado
        return cleaned_data

    def processar(self, posicionamento):
        prorrogacao: ProrrogacaoPrazo = ProrrogacaoPrazo.objects.get(manifestacao=self.manifestacao)
        if self.cleaned_data['tipo'] == TipoPosicionamento.PRORROGACAO_PRAZO:
            prorrogacao.deferir(posicionamento, self.cleaned_data['prazo_final'])
        else:
            prorrogacao.indeferir(posicionamento)
        #
        prorrogacao.save()

    @transaction.atomic()
    def save(self, commit=True):
        posicionamento: Posicionamento = super().save(commit)
        if commit:
            self.processar(posicionamento)
            posicionamento.publicar(self.user)
            posicionamento.save()
        return posicionamento


def PosicionamentoFormFactory(request, manifestacao):
    if not manifestacao.prorrogacao_prazo:
        return PosicionamentoForm(request.POST or None, request=request, manifestacao=manifestacao)
    return ProrrogacaoPosicionamentoForm(request.POST or None, request=request, manifestacao=manifestacao)


class EditarPosicionamentoForm(forms.ModelForm):
    class Meta:
        model = Posicionamento
        fields = ('tipo', 'motivacao', 'parecer')


class SolicitarRevisaoPosicionamentoForm(forms.FormPlus):
    posicionamento = forms.ModelChoiceField(label='Posicionamento', queryset=Posicionamento.objects.none())
    manifestacao = forms.ModelChoiceField(label='Manifestação', queryset=Manifestacao.objects.none())
    revisor = forms.ModelChoiceFieldPlus(label='Revisor', queryset=Vinculo.objects.none())

    def __init__(self, *args, **kwargs):
        self.posicionamento: Posicionamento = kwargs.pop('posicionamento', None)
        self.manifestacao: Manifestacao = self.posicionamento.manifestacao
        super().__init__(*args, **kwargs)
        self.fields['posicionamento'].queryset = Posicionamento.objects.filter(id=self.posicionamento.id)
        self.fields['posicionamento'].initial = self.posicionamento.id
        self.fields['posicionamento'].widget.attrs['readonly'] = True
        # Dados da manifestção
        self.fields['manifestacao'].queryset = Manifestacao.objects.filter(id=self.manifestacao.id)
        self.fields['manifestacao'].initial = self.manifestacao.id
        self.fields['manifestacao'].widget.attrs['readonly'] = True
        # Dado do revisor
        self.fields['revisor'].queryset = get_auditores_ativos()
        self.fields['revisor'].initial = self.posicionamento.revisor

    @transaction.atomic()
    def processar(self):
        self.posicionamento.atribuir_revisor(self.cleaned_data['revisor'])
        self.posicionamento.solicitar_revisao()
        self.posicionamento.save()


class RevisaoPosicionamentoForm(forms.ModelFormPlus):
    posicionamento = forms.ModelChoiceField(label='Posicionamento', queryset=Posicionamento.objects.none())
    tipo = forms.ChoiceField(label='Tipo de Posicionamento', choices=TipoPosicionamento.choices)
    comentario = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), label='Parecer do auditor', required=True
    )

    fieldsets = (
        ('Dados gerais', {'fields': ('posicionamento', 'tipo')}),
        (
            'Parecer',
            {
                'fields': (
                    'parecer',
                    'comentario',
                )
            },
        ),
    )

    class Meta:
        model = RevisaoPosicionamento
        fields = ('posicionamento', 'tipo', 'parecer', 'comentario')

    def __init__(self, *args, **kwargs):
        self.instance: RevisaoPosicionamento = kwargs.get('instance')
        self.posicionamento: Posicionamento = kwargs.pop('posicionamento', self.instance.posicionamento if self.instance else None)
        super().__init__(*args, **kwargs)
        self.fields['posicionamento'].queryset = Posicionamento.objects.filter(id=self.posicionamento.id)
        self.fields['posicionamento'].initial = self.posicionamento.id
        self.fields['posicionamento'].widget.attrs['readonly'] = True
        # Tipo de posicionamentto
        tipos_validos = TipoPosicionamentoValido.objects.filter(tipo_manifestacao=self.posicionamento.manifestacao.tipo)
        tipos_validos = [tipo.tipo_posicionamento for tipo in tipos_validos]
        self.fields['tipo'].initial = self.posicionamento.tipo
        self.fields['tipo'].choices = [(self.posicionamento.tipo, TipoPosicionamento.get_label(self.posicionamento.tipo))]
        self.fields['tipo'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        instance: RevisaoPosicionamento = super().save(commit=False)
        instance.revisor = self.request.user.get_vinculo()
        return super().save(commit)
