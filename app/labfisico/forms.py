#
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.formats import localize

from agendamento.forms import SolicitacaoAgendamentoForm
from agendamento.status import SolicitacaoAgendamentoStatus
from comum.models import UnidadeOrganizacional, User, Vinculo
from djtools import forms

#
from djtools.forms import ReadOnlyField
from djtools.forms.fields import JSONSchemaField
from djtools.forms.widgets import AutocompleteWidget, RenderableSelectMultiple
from djtools.utils import get_datetime_now

#
from edu.models import Aluno, Diario
from labfisico.helpers import build_lab_name
from labfisico.perms import is_group_admin

#
from .models import GuacamoleConnection, GuacamoleConnectionGroup, SolicitacaoLabFisico
from .rdp_schema import (
    rdp_attr_schema,
    rdp_auth_schema,
    rdp_basic_settings_schema,
    rdp_clipboard_schema,
    rdp_device_redirect_schema,
    rdp_display_schema,
    rdp_gateway_schema,
    rdp_load_balancing_schema,
    rdp_network_schema,
    rdp_performance_schema,
    rdp_preconnection_schema,
    rdp_screen_recording_schema,
    rdp_sftp_schema,
    rdp_wol_schema,
)


class GuacamoleConnectionGroupForm(forms.ModelFormPlus):
    name = forms.CharFieldPlus(
        width=50,
        label='Nome do Laboratório',
        help_text="Não é permitido hífens ou espaço. Não use prefixo 'lab', será adicionado pelo sistema",
        required=True,
    )
    campus = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.locals.none(),
        label='Campus',
        required=True,
        help_text='Informe os campi para os quais você deseja vincular o laboratório',
    )

    class Meta:
        model = GuacamoleConnectionGroup
        fields = ('name', 'campus', 'max_connections', 'max_connections_per_user', 'enable_session_affinity')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.eh_sistemico = False
        #
        if is_group_admin(self.request.user):
            self.fields['campus'].queryset = UnidadeOrganizacional.locals.all()
            self.eh_sistemico = True
        else:
            campus = self.request.user.get_vinculo().setor.uo
            if campus:
                self.fields['campus'].initial = campus.pk
                self.fields['campus'].queryset = UnidadeOrganizacional.locals.filter(id=campus.id)

    def clean_name(self):
        name = self.cleaned_data.get('name').strip()
        name = build_lab_name(name)
        if not name.isidentifier():
            self.add_error('name', 'Nome inválido.')
        return name

    def clean_campus(self):
        campus = self.cleaned_data.get('campus')
        if not self.eh_sistemico:
            if campus != self.request.user.get_vinculo().setor.uo:
                self.add_error('campus', f'Você não possui permissão para criar laboratório no campus {campus}.')
        return campus


class GuacamoleConnectionGroupEditForm(forms.ModelFormPlus):
    class Meta:
        model = GuacamoleConnectionGroup
        fields = (
            'max_connections',
            'max_connections_per_user',
            'enable_session_affinity',
        )


class GuacamoleConnectionForm(forms.ModelFormPlus):
    #
    options = {
        'no_additional_properties': True,
        'disable_collapse': True,
        'disable_edit_json': True,
        'disable_properties': True,
        # "remove_empty_properties": True,
    }

    connection_group = forms.ModelChoiceFieldPlus(
        GuacamoleConnectionGroup.objects.none(),
        label='Laboratório Remoto',
        required=True,
        help_text='Informe o laboratório que o cliente será vinculado',
    )

    attrs = JSONSchemaField(schema=rdp_attr_schema, options=options, ajax=False, label='', required=False)
    network = JSONSchemaField(schema=rdp_network_schema, options=options, label='', required=False)
    auth = JSONSchemaField(schema=rdp_auth_schema, options=options, label='', required=False)
    performance = JSONSchemaField(schema=rdp_performance_schema, options=options, label='', required=False)
    basic_settings = JSONSchemaField(schema=rdp_basic_settings_schema, options=options, label='', required=False)
    display = JSONSchemaField(schema=rdp_display_schema, options=options, label='', required=False)
    wol = JSONSchemaField(schema=rdp_wol_schema, options=options, label='', required=False)
    gw = JSONSchemaField(schema=rdp_gateway_schema, options=options, label='', required=False)
    clipboard = JSONSchemaField(schema=rdp_clipboard_schema, options=options, label='', required=False)
    screen = JSONSchemaField(schema=rdp_screen_recording_schema, options=options, label='', required=False)
    sftp = JSONSchemaField(schema=rdp_sftp_schema, options=options, label='', required=False)
    device_redirect = JSONSchemaField(schema=rdp_device_redirect_schema, options=options, label='', required=False)
    preconnection = JSONSchemaField(schema=rdp_preconnection_schema, options=options, label='', required=False)
    load_balancing = JSONSchemaField(schema=rdp_load_balancing_schema, options=options, label='', required=False)

    fieldsets = (
        (
            'Guacamole Connection',
            {
                'fields': (
                    'connection_name',
                    'connection_group',
                )
            },
        ),
        (
            'Connection Attributes',
            {'fields': ('attrs',)},
        ),
        #
        (
            'Network',
            {'fields': ('network',)},
        ),
        (
            'Authentication',
            {'fields': ('auth',)},
        ),
        (
            'Performance',
            {'fields': ('performance',)},
        ),
        (
            'Display',
            {'fields': ('display',)},
        ),
        (
            'Basic Settings',
            {'fields': ('basic_settings',)},
        ),
        (
            'Wake-on-Lan (WoL)',
            {'fields': ('wol',)},
        ),
        (
            'Remote Desktop Gateway',
            {'fields': ('gw',)},
        ),
        (
            'Screen Recording',
            {'fields': ('screen',)},
        ),
        (
            'Clipboard',
            {'fields': ('clipboard',)},
        ),
        (
            'SFTP',
            {'fields': ('sftp',)},
        ),
        (
            'Device Redirect',
            {'fields': ('device_redirect',)},
        ),
        (
            'Load Balancing',
            {'fields': ('load_balancing',)},
        ),
        (
            'Preconnection PDU / Hyper-V',
            {'fields': ('preconnection',)},
        ),
    )

    class Meta:
        model = GuacamoleConnection
        fields = ('connection_name', 'connection_group', 'attrs', 'parameters')

    def __init__(self, *args, **kwargs):
        laboratorio = kwargs.pop('laboratorio_pk', None)
        super().__init__(*args, **kwargs)
        #
        if laboratorio:
            self.fields['connection_group'].initial = laboratorio
            self.fields['connection_group'].widget.attrs['readonly'] = True
        #
        self.fields['connection_group'].queryset = GuacamoleConnectionGroup.objects.my_guacamole_connection_groups(self.request.user)
        if self.instance and self.instance.parameters:
            self.load_parameters(self.instance.parameters)

    def load_parameters(self, json_data):
        fields = [field for field in self.fields.values() if isinstance(field, JSONSchemaField)]
        for field in fields:
            keys = field.schema['properties'].keys()
            field.initial = {key: json_data.get(key, None) for key in keys}
        #

    def extract_parameters(self, cleaned_data):
        keys = [key for (key, field) in self.fields.items() if isinstance(field, JSONSchemaField)]
        data = {}
        for key in keys:
            data.update(cleaned_data[key])
        return data

    def verificar_lab(self, hostname, domain):
        if GuacamoleConnection.objects.filter(hostname=hostname, domain=domain).exists():
            self.add_error('hostname', f'O hostname {hostname} já está sendo usado no domínio {domain}.')

    def clean(self):
        cleaned_data = super().clean()
        if self.is_valid():
            lab = cleaned_data['connection_group']
            if lab not in GuacamoleConnectionGroup.objects.my_guacamole_connection_groups(self.request.user):
                self.add_error('connection_group', f'Você não possui permissão para adicionar clientes ao {lab}.')
        if self.instance is None:
            self.verificar_lab(cleaned_data['parameters']['hostname'], cleaned_data['parameters']['domain'])
        return cleaned_data

    def save(self, *args, **kwargs):
        obj = super().save(commit=False)
        data = self.extract_parameters(self.cleaned_data)
        obj.parameters = data
        return super().save(*args, **kwargs)


class SolicitacaoLabFisicoForm(SolicitacaoAgendamentoForm):
    readonly_fields = ('laboratorio', 'capacidade')
    #
    laboratorio = forms.ModelChoiceField(label='Laboratorio', queryset=GuacamoleConnectionGroup.objects)
    capacidade = forms.CharField(label='Capacidade', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    #
    diario = forms.ModelChoiceField(label='Diario', queryset=Diario.objects.none(), required=False, widget=AutocompleteWidget())
    #
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('laboratorio', 'capacidade'),
                    ('diario'),
                    ('data_inicio', 'data_fim'),
                    ('hora_inicio', 'hora_fim'),
                )
            },
        ),
        (
            'Dias da Semana',
            {
                'fields': (
                    (
                        'recorrencia_segunda',
                        'recorrencia_terca',
                        'recorrencia_quarta',
                        'recorrencia_quinta',
                        'recorrencia_sexta',
                        'recorrencia_sabado',
                        'recorrencia_domingo',
                    ),
                )
            },
        ),
    )

    def __diario_qs(self):
        eh_diretor = self.solicitante.groups.filter(name='Diretor Acadêmico').exists()
        manager = Diario.objects if eh_diretor else Diario.locals
        return manager.get_queryset().em_andamento()

    def __init__(self, *args, **kwargs):
        laboratorio_pk = kwargs.pop('laboratorio_pk', None)
        laboratorio_qs = GuacamoleConnectionGroup.objects.filter(pk=laboratorio_pk)
        self.laboratorio = kwargs.pop('laboratorio', laboratorio_qs.first())
        #
        self.solicitante = kwargs.pop('user', None)
        #
        self.diario = kwargs.pop('diario', None)
        super().__init__(*args, **kwargs)

        # Laboratorio
        self.fields['laboratorio'].queryset = laboratorio_qs
        self.fields['laboratorio'].initial = self.laboratorio.pk
        self.fields['laboratorio'].widget.attrs['readonly'] = True
        # Capacidade
        self.fields['capacidade'].initial = self.laboratorio.connections_count()
        self.fields['capacidade'].widget.attrs['readonly'] = True
        # Diario
        if self.diario:
            self.fields['diario'].initial = self.diario
        #
        self.fields['diario'].queryset = self.__diario_qs()

    def verificar_duplicadas(self, cleaned_data):
        duplicadas = SolicitacaoLabFisico.objects.filter(
            laboratorio=self.laboratorio,
            diario=cleaned_data['diario'],
            status=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO,
            data_inicio=cleaned_data['data_inicio'],
            hora_inicio=cleaned_data['hora_inicio'],
            data_fim=cleaned_data['data_fim'],
            hora_fim=cleaned_data['hora_fim'],
            recorrencia_segunda=cleaned_data['recorrencia_segunda'],
            recorrencia_terca=cleaned_data['recorrencia_terca'],
            recorrencia_quarta=cleaned_data['recorrencia_quarta'],
            recorrencia_quinta=cleaned_data['recorrencia_quinta'],
            recorrencia_sexta=cleaned_data['recorrencia_sexta'],
            recorrencia_sabado=cleaned_data['recorrencia_sabado'],
            recorrencia_domingo=cleaned_data['recorrencia_domingo'],
        ).exists()
        if duplicadas:
            raise ValidationError('Uma solicitação idêntica já existe.\n')

    def verificar_conflitos(self, cleaned_data):
        solicitacao = SolicitacaoLabFisico(
            laboratorio=self.laboratorio,
            solicitante=self.solicitante,
            status=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO,
            data_inicio=cleaned_data['data_inicio'],
            hora_inicio=cleaned_data['hora_inicio'],
            data_fim=cleaned_data['data_fim'],
            hora_fim=cleaned_data['hora_fim'],
            recorrencia_segunda=cleaned_data['recorrencia_segunda'],
            recorrencia_terca=cleaned_data['recorrencia_terca'],
            recorrencia_quarta=cleaned_data['recorrencia_quarta'],
            recorrencia_quinta=cleaned_data['recorrencia_quinta'],
            recorrencia_sexta=cleaned_data['recorrencia_sexta'],
            recorrencia_sabado=cleaned_data['recorrencia_sabado'],
            recorrencia_domingo=cleaned_data['recorrencia_domingo'],
        )
        if solicitacao.tem_conflito_reservas():
            raise ValidationError('O laboratório já possui uma reserva no intervalo especificado pela atual solicitação.\n')
        if len(solicitacao.get_datas_solicitadas()) == 0:
            raise ValidationError('O intervalo especificado não contém nenhum dos dias solicitados.\n')

    def verificar_permissoes(self):
        if not self.laboratorio.pode_solicitar(self.solicitante):
            raise ValidationError(f'O usuário {self.solicitante} não tem permissão para solicitações ao laboratório {self.laboratorio}.')

    def verificar_capacidade(self, cleaned_data):
        capacidade = self.laboratorio.connections_count()
        if capacidade == 0:
            self.add_error('capacidade', 'Não existem clientes cadastrados.')
        else:
            # Remove a capaciadade do cleaned data
            del cleaned_data['capacidade']

    def clean(self):
        cleaned_data = super().clean()
        if self.is_valid():
            self.verificar_duplicadas(cleaned_data)
            self.verificar_conflitos(cleaned_data)
            self.verificar_permissoes()
            self.verificar_capacidade(cleaned_data)
        return cleaned_data


class SolicitacaoLabFisicoMembrosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Enviar Solicitação'
    readonly_fields = ('laboratorio', 'capacidade', 'diario')
    #
    laboratorio = forms.ModelChoiceField(
        label='Laboratorio', queryset=GuacamoleConnectionGroup.objects, widget=AutocompleteWidget(readonly='readonly')
    )
    capacidade = forms.CharField(label='Capacidade', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    diario = forms.ModelChoiceField(label='Diario', queryset=Diario.objects, required=False, widget=AutocompleteWidget(readonly='readonly'))
    alunos = forms.MultipleModelChoiceField(
        required=False, queryset=Aluno.objects.none(), label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html')
    )
    membros = forms.MultipleModelChoiceFieldPlus(required=False, queryset=Vinculo.objects, label='')

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('laboratorio', 'capacidade'),
                    ('diario'),
                )
            },
        ),
        (
            'Alunos',
            {'fields': ('alunos',)},
        ),
        (
            'Membros',
            {'fields': ('membros',)},
        ),
    )

    def __init__(self, *args, **kwargs):
        laboratorio = kwargs.pop('laboratorio', None)
        diario = kwargs.pop('diario', None)
        solicitante = kwargs.pop('solicitante', None)
        super().__init__(*args, **kwargs)

        self.fields['laboratorio'].initial = laboratorio.pk
        self.fields['laboratorio'].widget.attrs['readonly'] = True

        self.fields['capacidade'].initial = laboratorio.connections_count()
        self.fields['capacidade'].widget.attrs['readonly'] = True
        #
        if diario:
            self.fields['diario'].initial = diario.pk
            self.fields['diario'].widget.attrs['readonly'] = True
            alunos_ids = diario.get_alunos_ativos().values_list('matricula_periodo__aluno__id', flat=True)
            self.fields['alunos'].queryset = Aluno.objects.filter(id__in=alunos_ids)
        #
        if solicitante:
            self.fields['membros'].initial = solicitante.get_vinculo()

    def clean(self):
        capacidade = int(self.cleaned_data['capacidade'])
        alunos = self.cleaned_data['alunos']
        membros = self.cleaned_data['membros']
        if len(alunos) + len(membros) > capacidade:
            raise ValidationError('A capacidade máxima do laboatório foi excedida.')
        return self.cleaned_data


class IndeferirSolicitacaoLabFisicoForm(forms.ModelFormPlus):
    readonly_fields = ('avaliador', 'data_avaliacao')
    avaliador = forms.CharField(label='Avaliador', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    data_avaliacao = forms.CharField(label='Data da Avaliação', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    observacao_avaliador = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)

    fieldsets = ((None, {'fields': (('avaliador'), ('data_avaliacao'), ('observacao_avaliador'))}),)

    class Meta:
        model = SolicitacaoLabFisico
        fields = ('observacao_avaliador',)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['avaliador'].initial = self.user
        self.fields['avaliador'].widget.attrs['readonly'] = True
        #
        data_avaliacao = get_datetime_now()
        self.fields['data_avaliacao'].initial = localize(data_avaliacao)
        self.fields['data_avaliacao'].widget.attrs['readonly'] = True
        #

    def clean_observacao_avaliador(self):
        observacao_avaliador = self.cleaned_data.get('observacao_avaliador', None)
        if observacao_avaliador is None:
            self.add_error('observacao_avaliador', 'Informe a justificativa do indeferimento')
        return observacao_avaliador

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.data_avaliacao = get_datetime_now()
        self.instance.avaliador = self.user
        self.instance.indeferir()
        return super().save(*args, **kwargs)


class CancelarSolicitacaoLabFisicoForm(forms.ModelFormPlus):
    cancelado_por = forms.ModelChoiceFieldPlus(User.objects, label='Avaliador', widget=AutocompleteWidget(readonly=True), required=False)
    status = ReadOnlyField(label='Status')
    data_cancelamento = ReadOnlyField(label='Data do Cancelamento')
    justificativa_cancelamento = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)

    fieldsets = ((None, {'fields': (('cancelado_por'), ('data_cancelamento'), ('status'), ('justificativa_cancelamento'))}),)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['cancelado_por'].initial = self.user
        #
        data_cancelamento = get_datetime_now()
        self.fields['data_cancelamento'].initial = data_cancelamento
        self.fields['data_cancelamento'].widget.display_value = localize(data_cancelamento)
        #
        self.fields['status'].widget.display_value = 'Cancelada'

    class Meta:
        model = SolicitacaoLabFisico
        fields = ('justificativa_cancelamento',)

    def clean_justificatiava_cancelamento(self):
        justificatica = self.cleaned_data.get('justificatiava_cancelamento', None)
        if justificatica is None:
            self.add_error('justificativa_cancelamento', 'Informe a justificativa do indeferimento')
        return justificatica

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.data_avaliacao = get_datetime_now()
        self.instance.cancelar()
        return super().save(*args, **kwargs)
