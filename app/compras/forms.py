from datetime import date, timedelta

from django.conf import settings

from compras.models import (
    Calendario,
    CategoriaCompra,
    ComentarioEtapaCompra,
    Compra,
    EtapasProcessoCompra,
    Evento,
    Fase,
    Nucleo,
    Processo,
    ProcessoCompra,
    ProcessoCompraCampusMaterial,
    TipoCalendario,
    TipoCompra,
    TipoEvento,
)
from comum.models import Ano
from djtools import forms
from djtools.forms import DtModelForm
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus
from materiais.models import Material, MaterialTag
from processo_eletronico.models import Processo as ProcessoEletronico
from rh.models import UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    if 'compras' in settings.INSTALLED_APPS:
        criar_compra_apos_novo_processo_licitacao = forms.BooleanField(
            label='Deve criar uma compra (módulo Compras) após a criação de um novo processo de licitação?',
            required=False,
        )


def ProcessoCompraCampusMaterialFormFactory(processo_compra_campus):
    tags = processo_compra_campus.processo_compra.tags.all()

    class FormClass(DtModelForm):
        campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.uo().all(), label='Campus', required=True)

        class Meta:
            model = ProcessoCompraCampusMaterial
            exclude = ['material_tag']

        hidden_fields_ = ['processo_compra_campus']
        material = forms.ModelChoiceField(
            queryset=Material.objects.filter(tags__in=tags),
            widget=AutocompleteWidget(
                qs_filter='tags__in={}'.format(','.join([str(i) for i in tags.all().values_list('id', flat=1)])), search_fields=Material.SEARCH_FIELDS
            ),
        )

    return FormClass


def ProcessoCompraFormFactory(instance=None):
    class ProcessoCompraForm(forms.FormPlus):
        descricao = forms.CharField(label='Descrição', required=True, max_length=25, initial=(instance and instance.descricao) or None)
        observacao = forms.CharField(label='Observação', required=False, widget=forms.Textarea, initial=(instance and instance.observacao) or None)
        data_inicio = forms.DateTimeField(initial=(instance and instance.data_inicio) or None, label='Data início')
        data_fim = forms.DateTimeField(initial=(instance and instance.data_fim) or None, label='Data fim')
        update_data = forms.BooleanField(label='Atualizar todos os processos de compra dos campi com esta data', required=False, initial=False)

    return ProcessoCompraForm


class ProcessoCompraForm(forms.ModelFormPlus):
    aplicar_todos = forms.BooleanField(
        label='Aplicar a todos os campi', help_text='Caso marcado, inclui todos os campos não informados.', required=False
    )
    tags = forms.MultipleModelChoiceFieldPlus(label='Tags', queryset=MaterialTag.objects, widget=FilteredSelectMultiplePlus('', True), required=False)

    class Meta:
        model = ProcessoCompra
        exclude = ()


class EventoForm(forms.ModelFormPlus):
    calendario = forms.ModelChoiceField(label='Calendário', queryset=Calendario.objects.filter(ativo=True))
    tipo_evento = forms.ChainedModelChoiceField(
        queryset=TipoEvento.objects.filter(ativo=True),
        label='Tipo de Evento',
        obj_label='descricao',
        empty_label='Selecione o Calendário',
        form_filters=[('calendario', 'calendario_id')],
    )

    class Meta:
        model = Evento
        fields = (
            'calendario',
            'tipo_evento',
            'data_inicio',
            'data_fim',
            'ativo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['calendario'].initial = self.instance.tipo_evento.calendario.id

    def cleaned_data(self):
        cleaned_data = super().clean()
        if cleaned_data.get('data_inicio') and cleaned_data.get('data_fim') and cleaned_data.get('data_inicio') >= cleaned_data.get('data_fim'):
            self.add_error('data_fim', 'A data de início não pode ser maior ou igual a data de fim.')
        return cleaned_data


class CalendarioForm(forms.FormPlus):
    ano = forms.ModelChoiceField(label='Ano', queryset=Ano.objects, required=False)
    calendario = forms.ModelChoiceField(Calendario.objects.filter(ativo=True), label='Calendário', empty_label='Todos', required=False)


class CalendarioCompraForm(forms.FormPlus):
    ano = forms.ModelChoiceField(label='Ano', queryset=Ano.objects, required=False)
    calendario = forms.ModelChoiceField(Calendario.objects.filter(ativo=True), label='Calendário', required=False)
    processo = forms.ChainedModelChoiceField(
        Processo.objects.all(),
        label='Processo',
        empty_label='Selecione um calendário',
        required=False,
        obj_label='tipo_processo__descricao',
        form_filters=[('calendario', 'tipo_processo__tipo_calendario_id')],
    )
    fase = forms.ChainedModelChoiceField(
        Fase.objects.all(),
        label='Fase',
        empty_label='Selecione um processo',
        required=False,
        obj_label='descricao',
        form_filters=[('processo', 'processo_id')],
    )


class CalendarioProcessoCompraForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ModelChoiceFieldPlus(label='Ano', queryset=Ano.objects, required=False)
    tipo_calendario = forms.ChoiceField(
        label='Calendário', choices=[(None, 'Todos'), *TipoCalendario.TIPO_CALENDARIO_CHOICES], required=False, initial='campus'
    )
    tipo_compra = forms.ChoiceField(
        label='Tipo de aquisição',
        choices=[(None, 'Todos'), *TipoCompra.TIPO_COMPRA_CHOICES],
        required=False,
    )
    etapa_atual = forms.ChoiceField(
        label='Etapa atual',
        choices=[(None, 'Todos'), *EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES],
        required=False,
    )
    categoria = forms.ChoiceField(
        label='Categoria',
        choices=[(None, 'Todos'), *CategoriaCompra.CATEGORIA_CHOICES],
        required=False,
    )
    nucleo_responsavel = forms.ModelChoiceFieldPlus(Nucleo.objects.filter(ativo=True), label='Núcleo', empty_label='Todos', required=False)
    campus_responsavel = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(), label='Campus:', empty_label='Todos', required=False
    )
    processo = forms.ModelChoiceFieldPlus(ProcessoEletronico.objects.filter(compra__isnull=False).distinct(), label='Processo', required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['campus_responsavel'].initial = user.get_relacionamento().setor.uo


class FaseForm(forms.ModelFormPlus):
    class Meta:
        model = Fase
        fields = ('descricao', 'data_inicio', 'data_fim', 'fase_inicial', 'cor', 'ativo')


# Novas classes para gestão do calendário de compras
class EtapaCompraFormset(forms.models.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_delete = True

        # Define valores iniciais para o primeiro formulário do formset
        if not self.instance.pk:
            if self.forms:
                self.forms[0].initial['data_inicio'] = date.today()
                self.forms[0].initial['data_fim'] = date.today() + timedelta(days=1)
            if len(self.forms) == len(EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES):
                for index, etapa in enumerate(EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES):
                    self.forms[index].initial['etapa'] = etapa[0]
                    self.forms[index].fields['etapa'].required = False

    def clean(self):
        qtd = 0
        for form in self.forms:
            if hasattr(form, 'cleaned_data'):
                qtd += 1
        if qtd < 1:
            raise forms.ValidationError('Você deve cadastrar ao menos uma etapa para a compra')

        # Verifica se não há etapas repetidas
        etapas = set()
        for form in self.forms:
            etapa = form.cleaned_data.get('etapa')
            if etapa:
                if etapa in etapas:
                    raise forms.ValidationError(f'A etapa "{EtapasProcessoCompra.get_display(etapa)}" foi repetida. Cada etapa deve ser única.')
                etapas.add(etapa)

        return super().clean()


class CompraForm(forms.ModelFormPlus):
    processo = forms.ModelChoiceField(queryset=ProcessoEletronico.objects, widget=AutocompleteWidget(), label='Processo', required=True)
    categoria = forms.ModelChoiceField(queryset=CategoriaCompra.objects, widget=AutocompleteWidget, label='Categoria', required=True)
    campus_responsavel = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(), label='Campus Responsável:', empty_label='Todos', required=False
    )
    campi_vinculados = forms.MultipleModelChoiceFieldPlus(
        UnidadeOrganizacional.objects.suap(),
        label='Campi vinculados',
        widget=FilteredSelectMultiplePlus('', True),
        required=True,
        help_text='Informe os campi vinculados ao processo de compra',
    )

    class Meta:
        model = Compra
        fields = [
            'processo',
            'objeto',
            'data_abertura',
            'categoria',
            'data_prevista_fim',
            'tipo_compra',
            'tipo_calendario',
            'nucleo_responsavel',
            'campus_responsavel',
            'campi_vinculados',
        ]

    class Media:
        js = ('/static/compras/js/CompraForm.js',)

    def clean_processo(self):
        processo = self.cleaned_data.get('processo')

        if self.instance.pk:
            if Compra.objects.filter(processo=processo).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Já existe outra compra vinculada a este processo.')
        else:
            if Compra.objects.filter(processo=processo).exists():
                raise forms.ValidationError('Já existe uma compra vinculada a este processo.')

        if self.cleaned_data.get('data_abertura') and not processo:
            raise forms.ValidationError('É necessário adicionar o processo eletrônico da compra.')

        return processo

    def clean_nucleo_responsavel(self):
        eh_gerenciador = self.request.user.has_group_cached('Gerenciador de Compras')
        eh_servidor_de_nucleo = Nucleo.objects.filter(componentes=self.request.user.get_vinculo().relacionamento).exists()

        if not eh_gerenciador and eh_servidor_de_nucleo:
            nucleos_que_pertence = Nucleo.objects.filter(componentes=self.request.user.get_vinculo().relacionamento)
            if self.cleaned_data['nucleo_responsavel'] not in nucleos_que_pertence:
                raise forms.ValidationError('Você não pertence a este núcleo de compras!')

        return self.cleaned_data['nucleo_responsavel']

    def clean(self):
        cleaned_data = super().clean()
        nucleo_responsavel = cleaned_data.get('nucleo_responsavel')
        campus_responsavel = cleaned_data.get('campus_responsavel')
        tipo_calendario = self.cleaned_data.get('tipo_calendario')
        campi_vinculados = self.cleaned_data.get('campi_vinculados')

        if not nucleo_responsavel and not campus_responsavel:
            raise forms.ValidationError('É obrigatório preencher pelo menos um dos campos: Núcleo Responsável ou Campus Responsável.')

        if tipo_calendario == 'nucleo_compras':
            if not nucleo_responsavel:
                raise forms.ValidationError('É obrigatório preencher o Núcleo Responsável ')
            else:
                campi_vinculados_compra = set(campi_vinculados.values_list('id', flat=True))
                campi_vinculados_nucleo = set(nucleo_responsavel.campi_vinculados.values_list('id', flat=True))
                campi_siglas = UnidadeOrganizacional.objects.filter(id__in=campi_vinculados_nucleo).values_list('sigla', flat=True)
                siglas_str = ', '.join(campi_siglas)

                if not campi_vinculados_nucleo:
                    self.add_error(
                        'campi_vinculados', 'Atualize o cadastro do núcleo, pois não existem Campi vinculados cadastrados para este Núcleo.'
                    )
                elif campi_vinculados_compra - campi_vinculados_nucleo:
                    self.add_error(
                        'campi_vinculados', f'É obrigatório preencher somente com os Campi {siglas_str} que fazem parte do núcleo selecionado.'
                    )
        elif tipo_calendario == 'campus' and len(campi_vinculados) > 1:
            self.add_error('campi_vinculados', 'Para o tipo de calendário escolhido, só é possível selecionar um campus.')

        return cleaned_data


class AdicionarComentarioForm(forms.ModelFormPlus):
    class Meta:
        model = ComentarioEtapaCompra
        fields = ['comentario']


class AtualizarEtapaAtualForm(forms.ModelFormPlus):
    class Meta:
        model = Compra
        fields = ['etapa_atual']
