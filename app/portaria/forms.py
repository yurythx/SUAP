from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.formats import localize

from comum.models import Sala, Vinculo
from djtools import forms
from djtools.forms import AutocompleteWidget, ReadOnlyField
from djtools.forms.fields import ImageViewField
from portaria.models import AcessoExterno, AcessoInterno, SolicitacaoEntrada, Visitante
from portaria.util import get_configuracao
from rh.models import UnidadeOrganizacional


class ListarAcessosCampusForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    plac = forms.CharField(
        max_length=255,
        label='Buscar',
        required=False,
        help_text='É possível buscar registros de visitas por: nome, matrícula e número do crachá do servidor; nome e matrícula do aluno; ou RG/CPF de pessoas sem vínculo com a instituição.',
    )
    filtro = forms.ChoiceField(
        required=False, label='Filtrar por', choices=[('hoje', 'Visitas de hoje'), ('nestemes', 'Visitas neste mês'), ('todos', 'Todos as visitas')]
    )


class ListarPessoasForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    pb_pessoa = forms.CharFieldPlus(
        min_length=3,
        max_length=255,
        label='Buscar',
        help_text='É possível buscar registros de visitas por: nome e matrícula do servidor ou do aluno, ou por RG ou CPF (com pontos e traços) de pessoas sem vínculo com a instituição.',
    )
    tipo_pessoa = forms.ChoiceField(label='Tipo de Pessoas', required=True, initial=1, choices=[[0, 'Sem Vínculo'], [1, 'Com Vínculo']])


class AcessoInternoForm(forms.ModelFormPlus):
    vinculo = ReadOnlyField(label='Vinculo')
    local_acesso = ReadOnlyField(label='Campus')

    fieldsets = (
        ('Visitante', {'fields': ('vinculo', 'foto_pessoa')}),
        ('Descrição da Visita', {'fields': ('local_acesso', 'objetivo', 'cracha', 'gerar_chave_wifi', 'quantidade_dias_chave_wifi')}),
    )

    class Meta:
        model = AcessoInterno
        fields = ('vinculo', 'local_acesso', 'objetivo', 'cracha')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['vinculo'].initial = self.instance.vinculo
        self.fields['vinculo'].widget.display_value = str(self.instance.vinculo)

        self.fields['local_acesso'].initial = self.instance.local_acesso
        self.fields['local_acesso'].widget.display_value = str(self.instance.local_acesso)

        self.fields['foto_pessoa'] = ImageViewField(label='Foto', url_image=self.instance.vinculo.get_foto_150x200_url())

        self.fields['cracha'].required = get_configuracao('cracha_obrigatorio')

        if get_configuracao('habilitar_geracao_chave_wifi'):
            self.fields['gerar_chave_wifi'] = forms.BooleanField(label='Deseja gerar chave do WI-FI?', widget=forms.CheckboxInput(), required=False)
            self.fields['quantidade_dias_chave_wifi'] = forms.ChoiceField(
                label='Quantidade de Dias Validade Chave do WI-FI', required=False, choices=[[num, num] for num in range(1, 8)]
            )


class AcessoExternoForm(forms.ModelFormPlus):
    pessoa_externa = ReadOnlyField(label='Pessoa')
    local_acesso = ReadOnlyField(label='Campus')

    fieldsets = (
        ('Visitante', {'fields': ('pessoa_externa', 'foto_pessoa')}),
        ('Descrição da Visita', {'fields': ('local_acesso', 'objetivo', 'cracha', 'gerar_chave_wifi', 'quantidade_dias_chave_wifi')}),
    )

    class Meta:
        model = AcessoExterno
        fields = ('pessoa_externa', 'local_acesso', 'objetivo', 'cracha')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['pessoa_externa'].initial = self.instance.pessoa_externa
        self.fields['pessoa_externa'].widget.display_value = self.instance.pessoa_externa.get_nome_rg_cpf

        self.fields['local_acesso'].initial = self.instance.local_acesso
        self.fields['local_acesso'].widget.display_value = self.instance.local_acesso

        self.fields['cracha'].required = get_configuracao('cracha_obrigatorio')

        if get_configuracao('habilitar_geracao_chave_wifi'):
            self.fields['gerar_chave_wifi'] = forms.BooleanField(label='Deseja gerar chave do WI-FI?', widget=forms.CheckboxInput(), required=False)
            self.fields['quantidade_dias_chave_wifi'] = forms.ChoiceField(
                label='Quantidade de Dias Validade Chave do WI-FI', required=False, choices=[[num, num] for num in range(1, 8)]
            )

        self.fields['foto_pessoa'] = ImageViewField(label='Foto', url_image=self.instance.pessoa_externa.get_foto_150x200_url())


class CadastrarVisitanteForm(forms.ModelFormPlus):
    rg = forms.CharField(
        max_length=20,
        required=False,
        label='Documento de Identificação',
        help_text='RG para nacionalidade brasileira ou Passaporte para estrangeiros',
    )
    cpf = forms.BrCpfField(required=False)
    registrar_acesso = forms.BooleanField(
        label='Deseja registrar uma visita para essa pessoa logo depois do seu cadastro?', widget=forms.CheckboxInput(), required=False
    )
    email = forms.EmailField(max_length=255, required=False, label='E-mail')

    METHOD = 'POST'

    class Meta:
        model = Visitante
        fields = ('nome', 'sexo', 'rg', 'cpf', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.request.user.groups.filter(name='Coordenador de Visitantes Sistêmico').exists() and self.instance and self.instance.pk:
            self.fields['data_cadastro'] = ReadOnlyField(label='Data de Cadastro')
            self.fields['data_cadastro'].initial = self.instance.data_cadastro
            self.fields['data_cadastro'].widget.display_value = localize(self.instance.data_cadastro)

            self.fields['user_cadastro'] = ReadOnlyField(label='Usuário do Cadastro')
            self.fields['user_cadastro'].initial = self.instance.user_cadastro.id
            self.fields['user_cadastro'].widget.display_value = self.instance.user_cadastro.get_profile().nome

            if self.instance.data_ultima_alteracao:
                self.fields['data_ultima_alteracao'] = ReadOnlyField(label='Data da Última Alteração')
                self.fields['data_ultima_alteracao'].initial = self.instance.data_ultima_alteracao
                self.fields['data_ultima_alteracao'].widget.display_value = localize(self.instance.data_ultima_alteracao)

                self.fields['user_ultima_alteracao'] = ReadOnlyField(label='Usuário da Última Alteração')
                self.fields['user_ultima_alteracao'].initial = self.instance.user_ultima_alteracao.id
                self.fields['user_ultima_alteracao'].widget.display_value = self.instance.user_ultima_alteracao.get_profile().nome

        if get_configuracao('habilitar_camera'):
            self.fields['foto'] = forms.PhotoCaptureField(required=False)

    def clean_rg(self):
        rg = self.cleaned_data.get('rg')
        nome = self.cleaned_data.get('nome')
        if rg and nome:
            for visitante in Visitante.objects.filter(rg=rg).exclude(id=self.instance.id):
                if visitante.nome.split()[0].lower() == nome.split()[0].lower():
                    raise forms.ValidationError('Já existe um visitante cadastrado com esse Nome/RG.')
        return rg

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if cpf and Visitante.objects.filter(cpf=cpf).exclude(id=self.instance.id).exists():
            raise forms.ValidationError('Já existe um visitante cadastrado com esse CPF.')
        return cpf


class BaixaEmAcessoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Confirmar'
    acesso_id = forms.IntegerField(required=False, widget=forms.HiddenInput())


class RegistrarChaveWifiForm(forms.Form):
    SUBMIT_LABEL = 'Confirmar'
    METHOD = 'POST'

    acesso_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    quantidade_dias_chave_wifi = forms.ChoiceField(
        label='Quantidade de Dias Validade Chave do WI-FI', required=False, choices=[[num, num] for num in range(1, 8)]
    )


class ListarHistoricoAcessoGeralForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    valor = forms.CharField(max_length=255, label='Buscar', required=False)
    campus = forms.ModelChoiceField(label='Campus', required=False, queryset=UnidadeOrganizacional.objects.suap().all())

    data_inicial = forms.DateTimeFieldPlus(required=False, label='Inicial')
    data_final = forms.DateTimeFieldPlus(required=False, label='Final')


class SolicitacaoEntradaForm(forms.ModelFormPlus):
    sala = forms.ModelChoiceField(queryset=Sala.ativas, widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS), label='Sala', required=True)

    solicitantes = forms.MultipleModelChoiceFieldPlus(
        queryset=Vinculo.objects.filter(tipo_relacionamento__in=ContentType.objects.filter(Q(Vinculo.SERVIDOR | Vinculo.PRESTADOR))),
        required=True,
        help_text='Somente é possível buscar por Servidores e/ou Prestadores de Serviços',
    )

    class Meta:
        model = SolicitacaoEntrada
        exclude = ('deferida', 'cancelada')


class SolicitacaoEntradaBalcaoDigitalForm(forms.ModelFormPlus):
    sala = forms.ModelChoiceField(queryset=Sala.ativas, widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS), label='Sala', required=True)

    def __init__(self, *args, **kwargs):
        campus_id = kwargs.pop('campus')

        super().__init__(*args, **kwargs)
        if campus_id:
            self.fields['sala'].queryset = Sala.ativas.filter(predio__uo__id=campus_id)

    class Meta:
        model = SolicitacaoEntrada
        exclude = ('solicitantes', 'deferida', 'cancelada')
