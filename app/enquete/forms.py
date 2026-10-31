import operator
from functools import reduce

from django.contrib.admin.widgets import FilteredSelectMultiple
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms.widgets import TextInput

from comum.models import Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, TextareaCounterWidget
from enquete.models import Categoria, Enquete, Opcao, OpcaoPergunta, Pergunta, PublicoCampi, Resposta
from rh.models import Servidor, Setor, UnidadeOrganizacional


class CleanOrder:
    def clean_ordem(self):
        ordem = self.cleaned_data.get('ordem')
        if ordem < 0:
            raise ValidationError('A ordem não pode ser negativa.')
        return ordem


class PerguntaForm(forms.ModelFormPlus, CleanOrder):
    objetiva = forms.BooleanField(label='Objetiva', initial=False, required=False)

    fieldsets = (
        ('Dados gerais', {'fields': (('ordem'), ('texto'), ('obrigatoria'))}),
        ('Para Pergunta Subjetiva', {'fields': (('numerico'),)}),
        ('Para Pergunta Objetiva', {'fields': (('objetiva', 'multipla_escolha'), ('layout'))}),
    )

    class Meta:
        model = Pergunta
        fields = ('ordem', 'texto', 'numerico', 'objetiva', 'multipla_escolha', 'layout', 'obrigatoria')

    def __init__(self, *args, **kwargs):
        enquete = None
        categoria = None
        if 'enquete' in kwargs:
            enquete = kwargs.pop('enquete')

        if 'categoria' in kwargs:
            categoria = kwargs.pop('categoria')

        super().__init__(*args, **kwargs)
        if enquete:
            self.instance.enquete = enquete

        if categoria:
            self.instance.categoria = categoria

    def clean_multipla_escolha(self):
        multipla_escolha = self.cleaned_data.get('multipla_escolha')
        objetiva = self.cleaned_data.get('objetiva')
        if multipla_escolha and not objetiva:
            raise ValidationError('Perguntas de múltipla escolha precisam ser objetivas.')

        return multipla_escolha


class EnqueteForm(forms.ModelFormPlus):
    vinculos_responsaveis = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects, label='Responsáveis', required=True)

    class Meta:
        model = Enquete
        exclude = ('publicada',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servidores_inativos = Servidor.objects.inativos().values_list('id', flat=True)
        self.fields['vinculos_responsaveis'].queryset = Vinculo.objects.servidores().exclude(id_relacionamento__in=servidores_inativos)


class PublicoCampiForm(forms.ModelFormPlus):
    campi = forms.ModelMultipleChoiceField(label='Campi', queryset=UnidadeOrganizacional.objects.suap(), widget=FilteredSelectMultiple('', True))
    setores = forms.MultipleModelChoiceFieldPlus(
        label='Setores', queryset=Setor.objects.none(), required=False, widget=AutocompleteWidget(multiple=True, form_filters=[('campi', 'uo__in')])
    )

    class Meta:
        model = PublicoCampi
        fields = ('publico', 'campi', 'setores')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['setores'].queryset = Setor.objects.siape()

    def clean_setores(self):
        campi = self.cleaned_data.get('campi', [])
        setores = self.cleaned_data.get('setores')
        setores_sem_campi_selecionado = setores.exclude(uo__equivalente__in=campi)
        if setores_sem_campi_selecionado.exists():
            raise ValidationError(
                f'Os setores {", ".join([str(setor) for setor in setores_sem_campi_selecionado])} não correspondem aos campi selecionados.'
            )
        return setores


class OpcaoForm(forms.ModelFormPlus, CleanOrder):
    class Meta:
        model = Opcao
        fields = ('ordem', 'texto', 'imagem', 'documento')

    def __init__(self, *args, **kwargs):
        enquete = None
        if 'enquete' in kwargs:
            enquete = kwargs.pop('enquete')

        super().__init__(*args, **kwargs)
        if enquete:
            self.instance.enquete = enquete


class OpcaoPerguntaForm(forms.ModelFormPlus, CleanOrder):
    class Meta:
        model = OpcaoPergunta
        fields = ('ordem', 'texto', 'imagem', 'documento')

    def __init__(self, *args, **kwargs):
        enquete = None
        if 'enquete' in kwargs:
            enquete = kwargs.pop('enquete')

        pergunta = None
        if 'pergunta' in kwargs:
            pergunta = kwargs.pop('pergunta')

        super().__init__(*args, **kwargs)
        if enquete:
            self.instance.enquete = enquete

        if pergunta:
            self.instance.pergunta = pergunta


class CategoriaForm(forms.ModelFormPlus, CleanOrder):
    class Meta:
        model = Categoria
        fields = ('ordem', 'texto', 'orientacao')


def ResponderEnqueteFormFactory(request, enquete):
    fields = {}
    fieldsets = []
    categorias = enquete.get_perguntas_agrupadas_por_categoria()
    for categoria in categorias:
        fields_list = []
        for pergunta in categoria.perguntas.all():
            field_name = f'{pergunta.id}'
            vinculo = request.user.get_vinculo()
            resposta = pergunta.get_resposta(vinculo)
            opcoes = pergunta.opcoes
            if not opcoes.exists():
                opcoes = pergunta.enquete.get_opcoes()

            if pergunta.objetiva:
                if pergunta.multipla_escolha:
                    field = forms.MultipleModelChoiceField(
                        label=pergunta.get_html(),
                        initial=resposta,
                        queryset=opcoes,
                        widget=forms.CheckboxSelectMultiplePlus(),
                        required=pergunta.obrigatoria,
                    )
                else:
                    field = forms.ModelChoiceField(
                        label=pergunta.get_html(),
                        initial=resposta,
                        queryset=opcoes,
                        widget=forms.RadioSelect(),
                        empty_label=None,
                        required=pergunta.obrigatoria,
                    )
            else:
                if pergunta.numerico:
                    field = forms.CharField(
                        label=pergunta.get_html(), initial=resposta, widget=TextInput(attrs={'type': 'number'}), required=pergunta.obrigatoria
                    )
                else:
                    field = forms.CharField(
                        label=pergunta.get_html(), initial=resposta, widget=TextareaCounterWidget(max_length=8000), required=pergunta.obrigatoria
                    )

            fields[field_name] = field
            fields_list.append(field_name)

        # Usado para manter a ordenação dos campos
        fieldsets.append((categoria.texto, {'fields': fields_list}))

    @transaction.atomic()
    def save(self, *args, **kwargs):
        for categoria in categorias:
            for pergunta in categoria.perguntas.all():
                field_name = f'{pergunta.id}'
                vinculo = request.user.get_vinculo()
                resposta = self.cleaned_data.get(field_name)
                pergunta.salvar_resposta(vinculo, resposta)

    return type(
        'ResponderQuestionarioForm',
        (forms.BaseForm,),
        {'base_fields': fields, 'METHOD': 'POST', 'fieldsets': fieldsets, 'save': save, 'categorias': categorias},
    )


class BuscarPublicoForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'
    texto_busca = forms.CharField(label='Por Nome, Matricula ou Username', required=False)
    respondeu = forms.ChoiceField(label='Respondeu?', required=False, choices=[['', '----'], ['Sim', 'Sim'], ['Não', 'Não']], initial='')

    def __init__(self, *args, **kwargs):
        enquete = kwargs.pop('enquete')
        super().__init__(*args, **kwargs)
        self.enquete = enquete
        if not enquete.eh_responsavel(self.request.user):
            del self.fields['respondeu']

    def processar(self):
        vinculos = self.enquete.vinculos_publico.all()
        if self.cleaned_data['texto_busca']:
            texto_busca = self.cleaned_data['texto_busca']
            vinculos = vinculos.filter(
                reduce(
                    operator.or_,
                    [
                        Q(pessoa__pessoafisica__cpf__icontains=texto_busca),
                        Q(user__username__icontains=texto_busca),
                        Q(pessoa__nome__icontains=texto_busca),
                    ],
                )
            )
        if self.cleaned_data.get('respondeu') == 'Sim':
            vinculos = vinculos.filter(enquete_resposta_vinculo__pergunta__enquete=self.enquete)
        if self.cleaned_data.get('respondeu') == 'Não':
            vinculos = vinculos.exclude(enquete_resposta_vinculo__pergunta__enquete=self.enquete)

        return vinculos.distinct().order_by('pessoa__nome')


class FiltrarRespostasForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    TODOS = 0
    DISCENTE = 1
    SERVIDOR = 2
    TEC_ADM = 3
    DOCENTE = 4
    PRESTADOR_SERVICO = 5
    PUBLICO_CHOICES = (
        (TODOS, 'Todos'),
        (DISCENTE, 'Discente'),
        (SERVIDOR, 'Servidor'),
        (TEC_ADM, 'Técnico Administrativo'),
        (DOCENTE, 'Docente'),
        (PRESTADOR_SERVICO, 'Prestador de Serviço'),
    )

    publico = forms.ChoiceField(label='Público', required=False, choices=PUBLICO_CHOICES)
    campus = forms.ModelChoiceField(
        label='Filtrar por Campus:', required=False, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='Todos'
    )
    exportar_xls = forms.BooleanField(label='Exportar para XLS', required=False)

    def __init__(self, *args, **kwargs):
        self.enquete = kwargs.pop('enquete')
        super().__init__(*args, **kwargs)
        campus_enquete = UnidadeOrganizacional.objects.suap().filter(
            Q(id__in=PublicoCampi.objects.filter(enquete=self.enquete).values_list('campi', flat=True))
            | Q(id__in=Enquete.objects.filter(id=self.enquete.id).values_list('vinculos_relacionados_enquete__setor__uo', flat=True))
        )
        self.fields['campus'].queryset = campus_enquete

    def get_respostas_participantes(self):
        respostas = Resposta.objects.filter(pergunta__enquete=self.enquete)
        publico = self.TODOS
        if self.is_valid():
            campus = self.cleaned_data.get('campus')
            if self.cleaned_data.get('publico'):
                publico = int(self.cleaned_data.get('publico'))
            if campus:
                respostas = respostas.filter(uo=campus)

        if publico == self.DISCENTE:
            respostas = respostas.filter(vinculo__tipo_relacionamento__model='aluno')
        elif publico == self.SERVIDOR:
            respostas = respostas.filter(vinculo__tipo_relacionamento__model='servidor')
        elif publico == self.TEC_ADM:
            respostas = respostas.filter(
                vinculo__tipo_relacionamento__model='servidor',
                vinculo__id_relacionamento__in=Servidor.objects.tecnicos_administrativos().values_list('id', flat=True),
            )
        elif publico == self.DOCENTE:
            respostas = respostas.filter(
                vinculo__tipo_relacionamento__model='servidor',
                vinculo__id_relacionamento__in=Servidor.objects.docentes().values_list('id', flat=True),
            )
        elif publico == self.PRESTADOR_SERVICO:
            respostas = respostas.filter(vinculo__tipo_relacionamento__model='prestadorservico')

        return respostas.order_by('vinculo__pessoa__nome').distinct()

    def get_participantes(self):
        vinculos_ids = self.get_respostas_participantes().values_list('vinculo_id', flat=True)
        return Vinculo.objects.filter(id__in=vinculos_ids).distinct()

    def get_respostas(self, pergunta):
        respostas = pergunta.resposta_set.order_by('data_cadastro', 'vinculo__pessoa__nome')
        if self.is_valid():
            campus = self.cleaned_data.get('campus')
            if campus:
                respostas = respostas.filter(uo=campus)

        return respostas
