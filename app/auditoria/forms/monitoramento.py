from auditoria.models.acao import Acao
from auditoria.models.manifestacao import Manifestacao, ManifestacaoStatus, TipoManifestacao
from auditoria.models.monitoramento import IndicacaoServidorMonitoramento, MonitoramentoStatus
from auditoria.models.posicionamento import Motivacao, Posicionamento, TipoPosicionamento
from comum.models import Vinculo
from comum.utils import get_setores_que_sou_chefe_hoje
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import get_datetime_now
from rh.models import Servidor, Setor, UnidadeOrganizacional
from tinymce.widgets import TinyMCE

from ..models import Monitoramento, Recomendacao, SolicitacaoProvidencia


class MonitorarRecomendacaoForm(forms.FormPlus):
    recomendacao = forms.ModelChoiceField(queryset=Recomendacao.objects.none(), label='Recomendação')
    unidades = forms.ModelMultipleChoiceField(Setor.objects.suap_ativos().none(), label='Unidades', widget=forms.CheckboxSelectMultiplePlus())
    motivacao = forms.CharFieldPlus(widget=forms.Textarea, required=True, label='Solicitação de providência')
    prazo = forms.DateFieldPlus(label='Prazo para atendimento', required=True)

    def __init__(self, *args, **kwargs):
        recomendacao: Recomendacao = kwargs.pop('recomendacao', None)
        unidade_id = kwargs.pop('unidade_id', None)
        super().__init__(*args, **kwargs)
        #
        self.fields['recomendacao'].initial = recomendacao.id
        self.fields['recomendacao'].queryset = Recomendacao.objects.filter(id=recomendacao.id)
        self.fields['recomendacao'].widget.attrs['readonly'] = True
        if unidade_id is None:
            self.fields['unidades'].queryset = recomendacao.unidades_nao_monitoradas().all()
        else:
            self.fields['unidades'].queryset = recomendacao.unidades_nao_monitoradas().filter(id=unidade_id)
            self.fields['unidades'].initial = unidade_id
            self.fields['unidades'].widget.attrs['readonly'] = True

    def _enviar_solicitacao(self, monitoramento, motivacao, prazo):
        defaults = {'motivo': motivacao, 'prazo_atendimento': prazo, 'setor': monitoramento.unidade}
        obj, created = SolicitacaoProvidencia.objects.get_or_create(monitoramento=monitoramento, defaults=defaults)
        if created:
            monitoramento.ultima_solicitacao = obj

    def _processar_unidade(self, recomendacao, unidade, motivacao, prazo):
        monitoramento: Monitoramento = Monitoramento.objects.registrados().get(recomendacao=recomendacao, unidade=unidade)
        self._enviar_solicitacao(monitoramento, motivacao, prazo)
        monitoramento.iniciar_monitoramento()
        monitoramento.save()
        return monitoramento

    def processar(self):
        unidades = self.cleaned_data.get('unidades', None)
        recomendacao = self.cleaned_data.get('recomendacao', None)
        prazo = self.cleaned_data.get('prazo')
        motivacao = self.cleaned_data.get('motivacao')
        monitoramentos = []
        for unidade in unidades:
            monitoramento = self._processar_unidade(recomendacao, unidade, motivacao, prazo)
            monitoramentos.append(monitoramento)
        return monitoramentos

    def clean_unidades(self):
        unidades: list[Setor] = self.cleaned_data.get('unidades', None)
        for unidade in unidades:
            if not unidade.obter_chefes_hieraquicamente():
                self.add_error('unidades', f'A unidade {unidade} não possui um chefe associado em toda a hieraquia do SUAP. Procure a TI.')
        #
        return unidades

    def clean_prazo(self):
        today = get_datetime_now().date()
        prazo = self.cleaned_data.get('prazo')
        if today > prazo:
            self.add_error('prazo', 'O prazo de resposta não pode ser no passado.')
        return prazo

    def clean(self):
        cleaned_data = super().clean()
        recomendacao = cleaned_data.get('recomendacao')
        prazo = cleaned_data.get('prazo')
        if prazo and prazo > recomendacao.data_limite:
            self.add_error('prazo', f'O prazo de resposta não pode ser maior que a data limite da recomendação: {recomendacao.data_limite}.')
        #
        return cleaned_data


class IniciarMonitoramentoForm(forms.FormPlus):
    recomendacao = forms.ModelChoiceField(queryset=Recomendacao.objects.none(), label='Recomendação')
    unidade = forms.ModelChoiceField(Setor.objects, label='Unidade')
    descricao = forms.CharFieldPlus(widget=forms.Textarea, required=True, label='Comunicado aos gestores')
    prazo = forms.DateFieldPlus(label='Prazo para atendimento', required=True)

    def __init__(self, *args, **kwargs):
        self.monitoramento: Monitoramento = kwargs.pop('monitoramento', None)
        recomendacao = self.monitoramento.recomendacao
        super().__init__(*args, **kwargs)
        #
        self.fields['recomendacao'].initial = recomendacao.id
        self.fields['recomendacao'].queryset = Recomendacao.objects.filter(id=recomendacao.id)
        self.fields['recomendacao'].widget.attrs['readonly'] = True
        #
        self.fields['unidade'].initial = self.monitoramento.unidade.id
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id=self.monitoramento.unidade_id)
        self.fields['uinidade'].widget.attrs['readonly'] = True

    def clean_unidade(self):
        unidade: Setor = self.cleaned_data.get('unidade', None)
        if not unidade.obter_chefes_hieraquicamente():
            self.add_error('unidades', f'A unidade {unidade} não possui um chefe associado na hieraquia do SUAP.')
        #
        return unidade

    def clean_prazo(self):
        today = get_datetime_now().date()
        prazo = self.cleaned_data.get('prazo')
        recomendacao = self.cleaned_data.get('recomendacao', None)
        if today > prazo:
            self.add_error('prazo', 'O prazo de resposta não pode ser no passado.')
        if prazo > recomendacao.data_limite:
            self.add_error('prazo', f'O prazo de resposta não pode ser maior que a data limite da recomendação: {recomendacao.data_limite}.')
        return prazo

    def processar(self):
        if self.monitoramento.registrada:
            self.monitoramento.iniciar_monitoramento()


class CancelarMonitoramentoForm(forms.ModelFormPlus):
    monitoramento = forms.ModelChoiceField(queryset=Monitoramento.objects.none(), label='Monitoramento')
    unidade = forms.ModelChoiceField(Setor.objects, label='Unidade')
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea, required=True)

    fieldsets = (('Dados gerais', {'fields': ('monitoramento', 'unidade')}), ('Motivação', {'fields': ('justificativa',)}))

    class Meta:
        model = Monitoramento
        fields = ('justificativa',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        self.fields['monitoramento'].initial = self.instance.id
        self.fields['monitoramento'].queryset = Monitoramento.objects.filter(id=self.instance.id)
        self.fields['monitoramento'].widget.attrs['readonly'] = True
        #
        self.fields['unidade'].initial = self.instance.unidade.id
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id=self.instance.unidade_id)
        self.fields['unidade'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.cancelar(self.request.user, self.cleaned_data['justificativa'])
            instance.save()
        return instance


class FinalizarMonitoramentoForm(forms.FormPlus):
    monitoramento = forms.ModelChoiceField(queryset=Monitoramento.objects.none(), label='Monitoramento')
    unidade = forms.ModelChoiceField(Setor.objects, label='Unidade')
    motivacao = forms.ModelChoiceFieldPlus(queryset=Motivacao.objects.none(), label='Motivação', required=True)
    tipo_manifestacao = forms.ChoiceField(label='Manifestação', required=True)
    tipo_posicionamento = forms.ChoiceField(label='Posicionamento', choices=TipoPosicionamento.choices)
    justificativa = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), label='Parecer do auditor', required=True
    )
    fieldsets = (
        ('Dados gerais', {'fields': (('monitoramento', 'unidade'), ('tipo_manifestacao', 'tipo_posicionamento'))}),
        (
            'Motivação',
            {
                'fields': (
                    'motivacao',
                    'justificativa',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.monitoramento: Monitoramento = kwargs.pop('monitoramento', None)
        super().__init__(*args, **kwargs)
        self.user = self.request.user
        #
        self.fields['monitoramento'].initial = self.monitoramento.id
        self.fields['monitoramento'].queryset = Monitoramento.objects.filter(id=self.monitoramento.id)
        self.fields['monitoramento'].widget.attrs['readonly'] = True
        #
        self.fields['unidade'].initial = self.monitoramento.unidade.id
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id=self.monitoramento.unidade_id)
        self.fields['unidade'].widget.attrs['readonly'] = True
        #
        self.fields['motivacao'].queryset = Motivacao.objects.filter(tipo_posicionamento=TipoPosicionamento.FINALIZAR_MONITORAMENTO)
        # Manifestação
        self.fields['tipo_manifestacao'].choices = [
            (TipoManifestacao.AUSENCIA_MANIFESTACAO, TipoManifestacao.get_label(TipoManifestacao.AUSENCIA_MANIFESTACAO))
        ]
        self.fields['tipo_manifestacao'].widget.attrs['readonly'] = True
        # Posicionamento
        self.fields['tipo_posicionamento'].choices = [
            (TipoPosicionamento.FINALIZAR_MONITORAMENTO, TipoPosicionamento.get_label(TipoPosicionamento.FINALIZAR_MONITORAMENTO))
        ]
        self.fields['tipo_posicionamento'].widget.attrs['readonly'] = True

    def processar(self):
        nova_manifestacao = Manifestacao.objects.create(
            monitoramento=self.monitoramento,
            tipo=TipoManifestacao.AUSENCIA_MANIFESTACAO,
            status=ManifestacaoStatus.RECEBIDA,
            solicitacao_providencia=self.monitoramento.ultima_solicitacao,
        )

        posicionamento = Posicionamento.objects.create(
            manifestacao=nova_manifestacao,
            tipo=TipoPosicionamento.FINALIZAR_MONITORAMENTO,
            motivacao=self.cleaned_data['motivacao'],
            parecer=self.cleaned_data['justificativa'],
        )
        posicionamento.publicar(self.user)
        posicionamento.save()


class SetorFilterForm(forms.FormPlus):
    METHOD = 'GET'
    campus = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.uo(),
        label='Campus',
        required=False,
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
    )
    setor = forms.ModelChoiceField(
        Setor.objects,
        label='Setor',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Setor.SEARCH_FIELDS,
            form_filters=[
                ('campus', 'uo__id'),
            ],
        ),
    )


class DesignarServidorMonitoramentoForm(forms.ModelFormPlus):
    recomendacao = forms.ModelChoiceField(queryset=Recomendacao.objects.none(), label='Recomendação')
    unidade = forms.ModelChoiceField(Setor.objects.suap_ativos().none(), label='Unidade')
    instrucoes = forms.CharField(label='Instruções', widget=forms.Textarea, required=True)
    servidor = forms.ModelChoiceFieldPlus(Vinculo.objects.all(), label='Servidor')

    fieldsets = (
        ('Dados gerais', {'fields': ('recomendacao', 'unidade')}),
        ('Dados do Servidor', {'fields': ('servidor', 'instrucoes')}),
    )

    class Meta:
        model = IndicacaoServidorMonitoramento
        fields = ('servidor', 'instrucoes')

    def __init__(self, *args, **kwargs):
        self.monitoramento: Monitoramento = kwargs.pop('monitoramento', None)
        super().__init__(*args, **kwargs)
        self.fields['recomendacao'].initial = self.monitoramento.recomendacao_id
        self.fields['recomendacao'].queryset = Recomendacao.objects.filter(id=self.monitoramento.recomendacao_id)
        self.fields['recomendacao'].widget.attrs['readonly'] = True
        self.fields['unidade'].initial = self.monitoramento.unidade.id
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id=self.monitoramento.unidade_id)
        self.fields['unidade'].widget.attrs['readonly'] = True
        # Servidores do meu setor e abaixo
        setores: list[Setor] = get_setores_que_sou_chefe_hoje(self.request.user)
        servidor_qs = Servidor.objects.none()
        for setor in setores:
            servidor_qs = servidor_qs | setor.get_servidores(recursivo=True)
        vinculo_qs = Vinculo.objects.servidores().filter(id_relacionamento__in=servidor_qs.values_list('id', flat=True))
        self.fields['servidor'].queryset = vinculo_qs.distinct()

    def save(self, commit=True):
        instance: IndicacaoServidorMonitoramento = super().save(commit=False)
        instance.monitoramento = self.monitoramento
        if commit:
            instance.save()
        return instance


class EstoqueMonitoramentoFilterForm(forms.FormPlus):
    METHOD = 'GET'
    unidade = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().none(),
        required=False,
        label='Unidade',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    acao = forms.ModelChoiceFieldPlus(
        queryset=Acao.objects.none(),
        required=False,
        label='Ação',
        widget=AutocompleteWidget(search_fields=Acao.SEARCH_FIELDS),
    )
    situacao = forms.ChoiceField(label='Situação', choices=[('', 'Todas as Situações'), *list(MonitoramentoStatus.CHOICES.items())], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        unidades = Monitoramento.objects.values_list('unidade__id', flat=True)
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id__in=unidades)
        acoes = Monitoramento.objects.values_list('recomendacao__relatorio__acao_id', flat=True)
        self.fields['acao'].queryset = Acao.objects.filter(id__in=acoes)

    def filter_queryset(self, queryset):
        """
        Aplica os filtros ao queryset de Monitoramento
        """
        if self.is_valid():
            unidade = self.cleaned_data.get('unidade')
            situacao = self.cleaned_data.get('situacao')
            acao = self.cleaned_data.get('acao')
            if unidade:
                queryset = queryset.filter(unidade=unidade)
            if situacao:
                queryset = queryset.filter(status=situacao)
            if acao:
                queryset = queryset.filter(recomendacao__relatorio__acao=acao)
        return queryset


class EstoqueRecomendacaoFilterForm(forms.FormPlus):
    METHOD = 'GET'
    unidade = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().none(),
        required=False,
        label='Unidade',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    acao = forms.ModelChoiceFieldPlus(
        queryset=Acao.objects.none(),
        required=False,
        label='Ação',
        widget=AutocompleteWidget(search_fields=Acao.SEARCH_FIELDS),
    )
    situacao = forms.ChoiceField(label='Situação', choices=[('', 'Todas as Situações'), *list(MonitoramentoStatus.CHOICES.items())], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        unidades_ids = Recomendacao.objects.values_list('monitoramentos__unidade__id', flat=True)
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id__in=unidades_ids)
        acoes = Recomendacao.objects.values_list('relatorio__acao_id', flat=True)
        self.fields['acao'].queryset = Acao.objects.filter(id__in=acoes)

    def filter_queryset(self, queryset):
        """
        Aplica os filtros ao queryset de Monitoramento
        """
        if self.is_valid():
            unidade = self.cleaned_data.get('unidade')
            situacao = self.cleaned_data.get('situacao')
            acao = self.cleaned_data.get('acao')
            if unidade:
                queryset = queryset.filter(monitoramentos__unidade=unidade)
            if situacao:
                queryset = queryset.filter(status=situacao)
            if acao:
                queryset = queryset.filter(relatorio__acao=acao)
        return queryset
