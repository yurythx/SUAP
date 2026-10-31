import calendar
import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, QuerySet
from django.utils.html import format_html

from comum.models import AreaAtuacao, User
from djtools import forms
from djtools.forms import FilteredSelectMultiplePlus
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget
from gerenciador_projetos.enums import PrioridadeTarefa, SituacaoProjeto, SituacaoTarefa, TipoRecorrencia, VisibilidadeProjeto
from gerenciador_projetos.portfolio import projetos_visiveis
from gerenciador_projetos.models import HistoricoEvolucao, LinkTarefa, Lista, ListaProjeto, Projeto, RecorrenciaTarefa, Tag, Tarefa, TipoAtividade
from rh.models import UnidadeOrganizacional


class ProjetoForm(forms.ModelFormPlus):
    areas = forms.MultipleModelChoiceField(AreaAtuacao.objects.filter(ativo=True).order_by('nome'), required=True, label='Áreas de Atuação:')
    descricao = TinyMCEFormField(label='Descrição')
    gerentes = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects,
        label='Gerentes',
        required=True,
    )
    interessados = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects,
        label='Interessados',
        help_text='Interessados são usuários que possuem acesso de leitura a todas as infromações do projeto.',
        required=False,
    )
    membros = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects,
        label='Membros',
        help_text='Membros são usuários que podem contribuir com o projeto no desenvolvimento de suas tarefas.',
        required=False,
    )
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().order_by('sigla'), label='Campus')

    class Meta:
        model = Projeto
        fields = (
            'areas',
            'titulo',
            'descricao',
            'data_conclusao_estimada',
            'uo',
            'gerentes',
            'membros',
            'interessados',
            'visibilidade',
            'situacao',
            'data_conclusao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servidores = User.objects.filter(
            is_active=True,
            vinculo__isnull=False,
            vinculo__tipo_relacionamento__model__in=['servidor', 'prestadorservico'],
        )
        self.fields['gerentes'].queryset = servidores
        self.fields['interessados'].queryset = servidores
        self.fields['membros'].queryset = servidores
        self.fields['situacao'].required = False
        self.instance.situacao = SituacaoProjeto.ABERTO
        self.fields['visibilidade'].widget = forms.RadioSelect(choices=VisibilidadeProjeto.choices)
        if not self.instance.pk:
            self.fields['situacao'].widget = forms.HiddenInput()
        else:
            self.fields['areas'].initial = self.instance.areas.all().values_list('pk', flat=True)
            self.fields['situacao'].widget = forms.RadioSelect(choices=SituacaoProjeto.choices)

    class Media:
        js = ('/static/gerenciador_projetos/js/ProjetoForm.js',)


class AlterarAtribuidosTarefaForm(forms.ModelFormPlus):
    atribuido_a = forms.MultipleModelChoiceFieldPlus(
        label='Atribuído a',
        queryset=User.objects.none(),
        required=False,
        help_text='Vincule ou desvincule usuários atribuídos a esta tarefa.',
    )

    class Meta:
        model = Tarefa
        fields = ('atribuido_a',)

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop('usuario')
        super().__init__(*args, **kwargs)
        projeto = self.instance.projeto
        self.fields['atribuido_a'].queryset = (
            projeto.membros.all() | User.objects.filter(pk__in=projeto.gerentes.values_list('id', flat=True)) | self.instance.atribuido_a.all()
        )

    def save(self, commit: bool = True) -> Tarefa:
        self.instance.atualizar_atribuicoes(list(self.cleaned_data['atribuido_a']), self.usuario)
        return self.instance


class ConfirmarAcaoForm(forms.FormPlus):
    """Só o botão: a confirmação chega por POST com CSRF (um GET nunca altera dados)."""

    def __init__(self, *args, rotulo: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.SUBMIT_LABEL = rotulo


class AlterarSituacaoTarefaForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        self.tarefa = kwargs.pop('tarefa')
        self.situacao = kwargs.pop('situacao')
        super().__init__(*args, **kwargs)
        self.SUBMIT_LABEL = f'Alterar para {dict(SituacaoTarefa.choices)[self.situacao]}'

    def processar(self) -> None:
        if self.situacao == SituacaoTarefa.CONCLUIDA:
            self.tarefa.fechar_tarefa()
        else:
            self.tarefa.situacao = self.situacao
            self.tarefa.save()


class TarefaProjetoFiltroForm(forms.FormPlus):
    METHOD = 'POST'
    TIPO_ORDENACAO_CHOICES = [['', 'Prioridade Crescente'], ['-', 'Prioridade Decrescente']]
    # SITUCAO_CHOICES = [['', '-----'], ['aberta', 'Aberta'], ['em andamento', 'Em Andamento'], ['concluída', 'Concluída']]

    situacao = forms.ChoiceField(label='Situação', choices=[['', '-----'], *SituacaoTarefa.choices], required=False)
    prioridade = forms.ChoiceField(label='Prioridade', choices=[['', '-----'], *PrioridadeTarefa.choices], required=False)
    tipo_ordenacao = forms.ChoiceField(choices=TIPO_ORDENACAO_CHOICES, initial='', required=False)


def TarefaFormFactory(request, projeto, tarefa=None, tarefa_pai=None):
    class TarefaForm(forms.ModelFormPlus):
        descricao = TinyMCEFormField(label='Descrição')
        lista = forms.ModelChoiceFieldPlus(queryset=Lista.objects.none(), label='Lista', required=False)
        atribuido_a = forms.MultipleModelChoiceFieldPlus(
            label='Atribuído a',
            queryset=User.objects.none(),
            required=False,
        )
        # situacao = forms.ChoiceField(label='Situação', choices=[['', '-----']] + SituacaoTarefa.choices)
        observadores = forms.MultipleModelChoiceFieldPlus(
            queryset=User.objects,
            label='Observadores',
            help_text='Vincule a esta tarefa usuários que podem ter interesse em acompanhar o andamento da mesma.',
            required=False,
        )
        tags = forms.MultipleModelChoiceFieldPlus(
            queryset=Tag.objects.filter(projeto_id=projeto.id),
            widget=AutocompleteWidget(multiple=True, search_fields=['nome']),
            label='Tags',
            help_text='Vincule tags a esta tarefa',
            required=False,
        )
        data_inicio = forms.DateFieldPlus(label='Data de Início', required=False)
        data_conclusao_estimada = forms.DateFieldPlus(label='Data de Conclusão Estimada', required=False)
        data_conclusao = forms.DateFieldPlus(label='Data de Conclusão', required=False)

        fieldsets = (
            (
                '',
                {
                    'fields': (
                        'tipo_atividade',
                        'titulo',
                        'descricao',
                        'situacao',
                        'prioridade',
                        'lista',
                        'atribuido_a',
                        ('data_inicio', 'data_conclusao_estimada', 'data_conclusao'),
                        'observadores',
                        'tarefa_pai',
                        'tags',
                    )
                },
            ),
        )

        class Meta:
            model = Tarefa
            fields = [
                'titulo',
                'descricao',
                'situacao',
                'tags',
                'tipo_atividade',
                'atribuido_a',
                'prioridade',
                'lista',
                'data_inicio',
                'data_conclusao_estimada',
                'data_conclusao',
                'observadores',
                'tarefa_pai',
            ]

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)

            servidores = User.objects.filter(
                is_active=True,
                vinculo__isnull=False,
                vinculo__tipo_relacionamento__model='servidor',
                vinculo__tipo_relacionamento__app_label='rh',
            )
            self.fields['observadores'].queryset = projeto.membros.all() if projeto.visibilidade == VisibilidadeProjeto.PRIVADO else servidores
            self.fields['atribuido_a'].queryset = projeto.membros.all() | User.objects.filter(pk__in=projeto.gerentes.values_list('id', flat=True))
            self.fields['situacao'].widget = forms.RadioSelect(choices=SituacaoTarefa.choices)
            self.fields['prioridade'].widget = forms.RadioSelect(choices=PrioridadeTarefa.choices)

            listas_ids = projeto.listaprojeto_set.values_list('lista_id', flat=True)
            if listas_ids:
                self.fields['lista'].queryset = Lista.objects.filter(pk__in=listas_ids)
            else:
                del self.fields['lista']

            if tarefa_pai:
                self.fields['tarefa_pai'].initial = tarefa_pai
                self.fields['tarefa_pai'].widget.attrs.update(readonly='readonly')
            else:
                tarefas = Tarefa.objects.filter(tarefa_pai__isnull=True, projeto=projeto)
                if tarefa:
                    self.fields['tarefa_pai'].queryset = tarefas.exclude(pk=tarefa.pk)
                else:
                    self.fields['tarefa_pai'].queryset = tarefas

    return TarefaForm


class DashboardForm(forms.FormPlus):
    atribuido_a = forms.MultipleModelChoiceFieldPlus(queryset=User.objects.none(), required=False, label='Atribuído a')
    situacao = forms.ChoiceField(label='Situação', choices=[['', '-----'], *SituacaoTarefa.choices], required=False)
    prioridade = forms.ChoiceField(label='Prioridade', choices=[['', '-----'], *PrioridadeTarefa.choices], required=False)

    def __init__(self, *args, **kwargs):
        projeto = kwargs.pop('projeto')
        super().__init__(*args, **kwargs)
        self.fields['atribuido_a'].queryset = projeto.membros.all() | User.objects.filter(pk__in=projeto.gerentes.values_list('id', flat=True))


class PercentualWidget(forms.NumberInput):
    """Slider de 0 a 100% (de 5 em 5) com o valor ao lado.

    Não é componente do Design System: usa o `input type="range"` nativo, sem CSS próprio; o
    `oninput` só atualiza o número exibido. A faixa continua validada no servidor. O tema só põe
    na coluna do campo os tipos de input que conhece; o wrapper `.radiolist` (que só define
    `grid-area: input`) leva o slider para lá.
    """

    input_type = 'range'

    def __init__(self, attrs: dict[str, object] | None = None) -> None:
        oninput = "this.nextElementSibling.value = this.value + '%'"
        super().__init__({'class': 'w-80', 'min': 0, 'max': 100, 'step': 5, 'oninput': oninput, **(attrs or {})})

    def render(self, name: str, value: object, attrs: dict[str, object] | None = None, renderer: object = None) -> str:
        valor = value if value not in (None, '') else 0
        slider = super().render(name, valor, attrs, renderer)
        return format_html('<div class="radiolist d-flex align-items-center gap-2">{}<output>{}%</output></div>', slider, valor)


class HistoricoEvolucaoForm(forms.ModelFormPlus):
    link_titulo = forms.CharField(label='Título do link', required=False)
    link_url = forms.URLField(label='URL do link', required=False, max_length=500)

    class Meta:
        model = HistoricoEvolucao
        fields = ['comentario', 'anexo', 'data_conclusao', 'percentual_executado']
        widgets = {'percentual_executado': PercentualWidget()}

    def __init__(self, *args, **kwargs):
        tarefa = kwargs.pop('tarefa', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:  # Checando se é uma nova instância, ou seja, não tem PK ainda
            # self.fields['data_conclusao'].initial = datetime.date.today()
            if tarefa and tarefa.percentual_executado is not None:
                self.fields['percentual_executado'].initial = tarefa.percentual_executado

    def clean_percentual_executado(self):
        percentual = self.cleaned_data['percentual_executado']
        if percentual is not None:
            if percentual < 0 or percentual > 100:
                raise ValidationError('Percentual executado deve estar entre 0 e 100.')
        return percentual

    def clean(self):
        cleaned_data = super().clean()
        titulo = cleaned_data.get('link_titulo')
        url = cleaned_data.get('link_url')
        if bool(titulo) != bool(url):
            raise ValidationError('Para enviar um link, informe título e URL.')
        return cleaned_data


class ComentarioRapidoTarefaForm(forms.ModelFormPlus):
    """Mini-formulário exibido acima da listagem de Histórico da Tarefa, para registrar
    apenas um comentário (sem anexo/percentual/link, disponíveis no popup completo)."""

    comentario = forms.CharField(label='Novo comentário', widget=forms.Textarea, required=True)

    class Meta:
        model = HistoricoEvolucao
        fields = ('comentario',)


class LinkTarefaForm(forms.ModelFormPlus):
    class Meta:
        model = LinkTarefa
        fields = ('titulo', 'url')


class AdicionarAnexoForm(forms.ModelFormPlus):
    class Meta:
        model = HistoricoEvolucao
        fields = [
            'comentario',
            'anexo',
        ]

    def __init__(self, *args, **kwargs):
        kwargs.pop('tarefa', None)
        super().__init__(*args, **kwargs)

    def clean_anexo(self):
        """Anexo é um campo requerido"""
        anexo = self.cleaned_data['anexo']
        if not anexo:
            raise ValidationError('É necessário informar um anexo.')
        return anexo


class AtribuirTarefaACampus(forms.FormPlus):
    campi = forms.MultipleModelChoiceFieldPlus(
        label='Campi', required=False, queryset=UnidadeOrganizacional.objects.uo().all(), widget=FilteredSelectMultiplePlus('', True)
    )
    manter_atendentes = forms.BooleanField(label='Manter atendentes', required=False)
    manter_checklist = forms.BooleanField(label='Manter checklist', required=False)

    def processar(self, tarefa, usuario):
        with transaction.atomic():
            campi = self.cleaned_data['campi']
            manter_atendentes = self.cleaned_data['manter_atendentes']
            manter_checklist = self.cleaned_data['manter_checklist']
            for uo in campi:
                if not tarefa.uo:
                    tarefa.uo = uo
                    tarefa.save()
                else:
                    nova_tarefa = tarefa.clonar(usuario, manter_atendentes=manter_atendentes, manter_checklist=manter_checklist)
                    nova_tarefa.uo = uo
                    nova_tarefa.save()


class FiltrarCalendarioForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=True)
    data_fim = forms.DateFieldPlus(label='Data de Término', required=True)
    situacao = forms.ChoiceField(label='Situação', choices=[['', '-----'], *SituacaoTarefa.choices], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = datetime.date.today()
        data_inicio = hoje.replace(day=1)
        data_fim = data_inicio.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
        self.fields['data_inicio'].initial = data_inicio
        self.fields['data_fim'].initial = data_fim

    def clean(self):
        cleaned_data = super().clean()
        if not {'data_inicio', 'data_fim'}.issubset(self.cleaned_data.keys()):
            raise forms.ValidationError('Informe a data início e a data fim para executar a consulta.')
        data_inicio = self.cleaned_data['data_inicio']
        data_fim = self.cleaned_data['data_fim']
        if data_inicio > data_fim:
            raise forms.ValidationError('Data inicial não pode ser maior que data final.')
        if (data_fim - data_inicio).days > 90:
            raise forms.ValidationError('O intervalo entre as datas não pode ser maior que 90 dias.')
        return cleaned_data


class RecorrenciaTarefaForm(forms.ModelFormPlus):
    dia_do_mes = forms.TypedChoiceField(label='Dia do Mês', choices=[(x, x) for x in range(1, 32)], coerce=int, required=False)

    class Meta:
        model = RecorrenciaTarefa
        fields = ['tipo_recorrencia', 'dia_da_semana', 'dia_do_mes', 'mes_do_ano', 'data_fim']

    class Media:
        js = ('/static/gerenciador_projetos/js/RecorrenciaTarefaForm.js',)

    def clean(self):
        tipo_recorrencia = self.cleaned_data.get('tipo_recorrencia')
        if tipo_recorrencia == TipoRecorrencia.SEMANALMENTE and not self.cleaned_data.get('dia_da_semana'):
            raise forms.ValidationError('É necessário informar o dia da semana para a recorrêncial semanal.')
        elif tipo_recorrencia == TipoRecorrencia.MENSALMENTE and not self.cleaned_data.get('dia_do_mes'):
            raise forms.ValidationError('É necessário informar o dia do mês para a recorrêncial mensal.')
        elif tipo_recorrencia == TipoRecorrencia.ANUALMENTE and (not self.cleaned_data.get('dia_do_mes') or not self.cleaned_data.get('mes_do_ano')):
            raise forms.ValidationError('É necessário informar o dia e mês para a recorrêncial anual.')
        elif tipo_recorrencia == TipoRecorrencia.ANUALMENTE and self.cleaned_data.get('dia_do_mes') and self.cleaned_data.get('mes_do_ano'):
            try:
                datetime.datetime(datetime.date.today().year, int(self.cleaned_data.get('mes_do_ano')), int(self.cleaned_data.get('dia_do_mes')))
            except ValueError:
                raise forms.ValidationError(
                    'O Dia/Mês informado ({}/{}) não é válido.'.format(self.cleaned_data.get('dia_do_mes'), self.cleaned_data.get('mes_do_ano'))
                )

        return self.cleaned_data

    def clean_data_fim(self):
        if (
            self.cleaned_data['data_fim']
            and self.instance.tarefa.data_conclusao_estimada
            and (self.cleaned_data['data_fim'] > self.instance.tarefa.data_conclusao_estimada)
        ):
            raise forms.ValidationError('A data fim da recorrência não pode ser maior que a data de conclusão estimada da tarefa.')

        return self.cleaned_data['data_fim']


class AtualizarPosicaoListaProjetoForm(forms.FormPlus):
    posicao = forms.IntegerFieldPlus(label='Posição', help_text='Informe a nova posição desta lista no projeto.')


class AdicionarOuVincularListaProjetoForm(forms.FormPlus):
    acao = forms.ChoiceField(label='Ação', widget=forms.RadioSelect(), choices=[['A', 'Adicionar'], ['V', 'Vincular']], initial='A')
    posicao = forms.IntegerFieldPlus(label='Posição', initial=1)
    titulo = forms.CharField(label='Nome', required=False)
    lista = forms.ModelChoiceFieldPlus(queryset=Lista.objects.none(), widget=forms.Select(), required=False, label='Listas Disponíveis')

    class Media:
        js = ('/static/gerenciador_projetos/js/AdicionarOuVincularListaProjetoForm.js',)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto')
        super().__init__(*args, **kwargs)
        posicao = ListaProjeto.objects.filter(projeto=self.projeto).aggregate(Max('posicao'))['posicao__max']
        self.fields['lista'].queryset = Lista.get_disponiveis(self.request.user, self.projeto)
        self.fields['posicao'].initial = posicao + 1 if posicao else 1

    def clean(self):
        acao = self.cleaned_data.get('acao')
        lista = self.cleaned_data.get('lista')
        titulo = self.cleaned_data.get('titulo')
        if acao == 'V' and not lista:
            raise ValidationError('Nenhuma lista foi vinculada. Por favor verifique.')
        elif acao == 'A' and not titulo:
            raise ValidationError('Informe um título para criar uma lista vinculada ao projeto.')

        return self.cleaned_data

    def save(self):
        acao = self.cleaned_data.get('acao')
        if acao == 'V':
            ListaProjeto.objects.get_or_create(lista=self.cleaned_data.get('lista'), projeto=self.projeto, posicao=self.cleaned_data.get('posicao'))
        else:
            lista = Lista.objects.get_or_create(nome=self.cleaned_data.get('titulo'), criada_por=self.request.user)[0]
            ListaProjeto.objects.get_or_create(lista=lista, projeto=self.projeto, posicao=self.cleaned_data.get('posicao'))


""" Inicio Admin Forms """


class ListaForm(forms.ModelFormPlus):
    class Meta:
        model = Lista
        fields = ['nome', 'ativa']


class TagForm(forms.ModelFormPlus):
    class Meta:
        model = Tag
        fields = ['nome', 'cor']  # , 'projeto'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['nome'].initial = self.instance.nome
            self.fields['cor'].initial = self.instance.cor


class TipoAtividadeForm(forms.ModelFormPlus):
    class Meta:
        model = TipoAtividade
        fields = ['nome']


class MinhasTarefasForm(forms.FormPlus):
    projeto = forms.ModelChoiceFieldPlus(label='Projetos', queryset=Projeto.objects)

    def __init__(self, *args, **kwargs):
        usuario = kwargs.pop('usuario')
        super().__init__(*args, **kwargs)
        self.fields['projeto'].queryset = Projeto.objects.filter(tarefa__atribuido_a=usuario).distinct()


class BuscaHistoricoEvolucaoForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data Inicial', required=False)
    data_final = forms.DateFieldPlus(label='Data Final', required=False)


class CompararProjetosForm(forms.FormPlus):
    """Seleção dos projetos comparados; só oferece os que o usuário pode ver."""

    METHOD = 'GET'
    SUBMIT_LABEL = 'Comparar'

    projeto = forms.MultipleModelChoiceFieldPlus(
        Projeto.objects.none(),
        label='Projetos',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=['titulo']),
        help_text='Digite parte do título para incluir outro projeto.',
    )

    def __init__(self, *args: object, usuario: User, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['projeto'].queryset = projetos_visiveis(usuario).order_by('titulo')


class CompararCalendarioForm(FiltrarCalendarioForm):
    """Filtro do calendário da comparação: em GET, carregando a seleção de projetos em campos ocultos."""

    METHOD = 'GET'
    SUBMIT_LABEL = 'Filtrar'

    projeto = forms.MultipleModelChoiceField(Projeto.objects.none(), widget=forms.MultipleHiddenInput, required=False)

    def __init__(self, *args: object, projetos: QuerySet[Projeto], **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields['projeto'].queryset = projetos
        self.fields['projeto'].initial = list(projetos.values_list('pk', flat=True))
