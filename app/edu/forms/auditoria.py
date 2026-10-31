from comum.models import User, Vinculo, UsuarioGrupo, UsuarioGrupoSetor
from datetime import timedelta
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.templatetags.filters import in_group
from edu.models import (
    Aluno,
    AuditoriaEnsino,
    Diario,
    Log,
    Professor,
    RegistroAuditoriaEnsino,
)
from rh.models import UnidadeOrganizacional


class LogForm(forms.ModelFormPlus):
    id = forms.CharField(label='Identificador', widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = Log
        fields = ['id']


class RealizarAuditoriaForm(forms.FormPlus):
    METHOD = 'GET'
    user = forms.ModelChoiceFieldPlus(User.objects, label='Usuário', required=False)
    aluno = forms.ModelChoiceFieldPlus(
        Aluno.objects.autocomplete(), label='Aluno', required=False, widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS)
    )
    diario = forms.ModelChoiceFieldPlus(
        Diario.objects,
        label='Diário',
        required=False,
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário.',
        widget=AutocompleteWidget(search_fields=Diario.SEARCH_FIELDS),
    )
    professor = forms.ModelChoiceFieldPlus(
        Professor.objects, label='Professor', required=False, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS)
    )
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=False)
    data_fim = forms.DateFieldPlus(label='Data de Fim', required=False)

    acao = forms.ChoiceField(label='Ação', choices=[['', '-----------'], *Log.TIPO_CHOICES], required=False)
    modelo = forms.CharField(label='Modelo', required=False)
    ref = forms.IntegerField(label='Referência', required=False)

    def processar(self):
        user = 'user' in self.cleaned_data and self.cleaned_data['user'] or None
        aluno = 'aluno' in self.cleaned_data and self.cleaned_data['aluno'] or None
        diario = 'diario' in self.cleaned_data and self.cleaned_data['diario'] or None
        data_inicio = 'data_inicio' in self.cleaned_data and self.cleaned_data['data_inicio'] or None
        data_fim = 'data_fim' in self.cleaned_data and self.cleaned_data['data_fim'] or None
        professor = 'professor' in self.cleaned_data and self.cleaned_data['professor'] or None

        acao = 'acao' in self.cleaned_data and self.cleaned_data['acao'] or None
        modelo = 'modelo' in self.cleaned_data and self.cleaned_data['modelo'] or None
        ref = 'ref' in self.cleaned_data and self.cleaned_data['ref'] or None

        qs = Log.objects.all()

        if user:
            qs = qs.filter(user=user)
        if aluno:
            qs = qs.filter(ref_aluno=aluno.pk) | qs.filter(ref=aluno.pk, modelo='Aluno')
        if diario:
            qs = qs.filter(ref_diario=diario.pk) | qs.filter(ref=diario.pk, modelo='Diario')
        if data_inicio:
            qs = qs.filter(dt__gt=data_inicio)
        if data_fim:
            qs = qs.filter(dt__lt=data_fim + timedelta(days=1))
        if professor:
            qs = qs.filter(modelo='Professor', ref=professor.pk)

        if acao:
            qs = qs.filter(tipo=acao)
        if ref and modelo:
            if modelo == 'Aluno':
                qs = qs.filter(ref=ref, modelo=modelo) | qs.filter(ref_aluno=ref).exclude(modelo=modelo)
            elif modelo == 'Diario':
                qs = qs.filter(ref=ref, modelo=modelo) | qs.filter(ref_diario=ref).exclude(modelo=modelo)
            else:
                qs = qs.filter(ref=ref, modelo=modelo)
        else:
            if ref:
                qs = qs.filter(ref=ref)
            if modelo:
                qs = qs.filter(modelo=modelo)

        return qs.distinct().order_by('-dt')


class SolicitarAuditoriaEnsinoForm(forms.ModelFormPlus):
    class Meta:
        model = AuditoriaEnsino
        fields = 'campus', 'nivel_ensino', 'tipo_auditoria', 'data_inicio_auditoria', 'data_fim_auditoria', 'fonte_dados'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.locals.campi()
        self.fields['tipo_auditoria'].choices = AuditoriaEnsino.TIPO_AUDITORIA_SOLICITAVEL_CHOICES

        is_administrador = in_group(self.request.user, 'Administrador Acadêmico')
        if not is_administrador:
            self.fields['fonte_dados'].widget = forms.HiddenInput()

    def processar(self):
        return self.instance.solicitar(self.request.user)


class ResolverAuditoriaEnsinoForm(forms.ModelFormPlus):
    class Meta:
        model = AuditoriaEnsino
        fields = 'resolvido_parcialmente', 'justificativa'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resolvido_parcialmente'].required = True

    def clean_justificativa(self):
        resolvido_parcialmente = self.cleaned_data.get('resolvido_parcialmente')
        justificativa = self.cleaned_data.get('justificativa')
        if resolvido_parcialmente and not justificativa:
            raise forms.ValidationError('Informe a justificativa dos registros que ficaram sem resolução nesta auditoria.')
        return justificativa

    def processar(self):
        self.instance.resolver(self.request.user)


class EditarAtendenteAuditoriaEnsinoForm(forms.ModelFormPlus):
    class Meta:
        model = AuditoriaEnsino
        fields = ('atendente',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.is_auditoria_administrador():
            usuarios = UsuarioGrupo.objects.filter(group__name='Administrador Acadêmico').values_list('user_id', flat=True)
        else:
            usuarios = UsuarioGrupoSetor.objects.filter(
                usuario_grupo__group__name='Secretário Acadêmico', setor__uo_id=self.instance.campus_id
            ).values_list('usuario_grupo__user_id', flat=True)
        self.fields['atendente'].queryset = Vinculo.objects.filter(user_id__in=usuarios, tipo_relacionamento__model='servidor')
        self.fields['atendente'].required = False

    def processar(self):
        self.instance.editar_atendente(self.request.user)


class InformarFonteDadosAuditoriaEnsinoForm(forms.ModelFormPlus):
    class Meta:
        model = AuditoriaEnsino
        fields = 'data_inicio_auditoria', 'data_fim_auditoria', 'fonte_dados'


class InformarSituacaoRegistroAuditoriaForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroAuditoriaEnsino
        fields = ('situacao',)

    def processar(self, user):
        self.instance.registrar_situacao(user)


class InformarCorrecaoAlunoSemSISTECForm(forms.FormPlus):
    codigo_sistec = forms.CharFieldPlus(label='Código SISTEC', required=True)

    def __init__(self, *args, **kwargs):
        self.registro = kwargs.pop('registro')
        super().__init__(*args, **kwargs)
        matricula = self.registro.get_matricula()
        self.aluno = Aluno.objects.get(matricula=matricula)
        self.initial['codigo_sistec'] = self.aluno.codigo_sistec

    def processar(self, user):
        codigo_sistec = self.cleaned_data.get('codigo_sistec')
        self.aluno.codigo_sistec = codigo_sistec
        self.aluno.save()
        self.registro.situacao = RegistroAuditoriaEnsino.SITUACAO_RESOLVIDO
        self.registro.registrar_situacao(user)


class InformarCorrecaoReceitaFederalForm(forms.FormPlus):
    nome_registro = forms.CharFieldPlus(label='Nome do aluno', required=True)
    data_nacimento = forms.DateFieldPlus(label='Data de nascimento', required=True)
    nome_mae = forms.CharFieldPlus(label='Nome da mãe', required=True)

    def __init__(self, *args, **kwargs):
        self.registro = kwargs.pop('registro')
        super().__init__(*args, **kwargs)
        itens = self.registro.get_itens()
        matricula = itens[0]
        nome_registro_rf = itens[3]
        data_nacimento_rf = itens[5]
        nome_mae_rf = itens[7]
        self.aluno = Aluno.objects.get(matricula=matricula)
        if nome_registro_rf != '-':
            self.initial['nome_registro'] = self.aluno.pessoa_fisica.nome_registro
            self.fields['nome_registro'].help_text = f'Receita Federal: {nome_registro_rf}'
        else:
            del self.fields['nome_registro']
        if data_nacimento_rf != '-':
            self.initial['data_nacimento'] = self.aluno.pessoa_fisica.nascimento_data
            self.fields['data_nacimento'].help_text = f'Receita Federal: {data_nacimento_rf}'
        else:
            del self.fields['data_nacimento']
        if nome_mae_rf != '-':
            self.initial['nome_mae'] = self.aluno.nome_mae
            self.fields['nome_mae'].help_text = f'Receita Federal: {nome_mae_rf}'
        else:
            del self.fields['nome_mae']

    def processar(self, user):
        nome_registro = self.cleaned_data.get('nome_registro')
        data_nacimento = self.cleaned_data.get('data_nacimento')
        nome_mae = self.cleaned_data.get('nome_mae')

        if nome_registro:
            self.aluno.pessoa_fisica.nome_registro = nome_registro
        if data_nacimento:
            self.aluno.pessoa_fisica.nascimento_data = data_nacimento
        if nome_registro or data_nacimento:
            self.aluno.pessoa_fisica.save()
        if nome_mae:
            self.aluno.nome_mae = nome_mae
            self.aluno.save()
        self.registro.situacao = RegistroAuditoriaEnsino.SITUACAO_RESOLVIDO
        self.registro.registrar_situacao(user)


class InformarCorrecaoNomePaisForm(forms.FormPlus):
    nome_mae = forms.CharFieldPlus(label='Nome da mãe', required=True)
    nome_pai = forms.CharFieldPlus(label='Nome do pai', required=True)

    def __init__(self, *args, **kwargs):
        self.registro = kwargs.pop('registro')
        super().__init__(*args, **kwargs)
        itens = self.registro.get_itens()
        matricula = itens[0]
        parentesco = itens[2]
        self.aluno = Aluno.objects.get(matricula=matricula)
        if parentesco == 'Pai':
            self.initial['nome_pai'] = self.aluno.nome_pai
            del self.fields['nome_mae']
        else:
            self.initial['nome_mae'] = self.aluno.nome_mae
            del self.fields['nome_pai']

    def processar(self, user):
        nome_pai = self.cleaned_data.get('nome_pai')
        nome_mae = self.cleaned_data.get('nome_mae')
        if nome_pai:
            self.aluno.nome_pai = nome_pai
        if nome_mae:
            self.aluno.nome_mae = nome_mae
        self.aluno.save()
        self.registro.situacao = RegistroAuditoriaEnsino.SITUACAO_RESOLVIDO
        self.registro.registrar_situacao(user)


class InformarCorrecaoNomeAlunoForm(forms.FormPlus):
    nome_registro = forms.CharFieldPlus(label='Nome do aluno', required=True)

    def __init__(self, *args, **kwargs):
        self.registro = kwargs.pop('registro')
        super().__init__(*args, **kwargs)
        matricula = self.registro.get_matricula()
        self.aluno = Aluno.objects.get(matricula=matricula)
        self.initial['nome_registro'] = self.aluno.pessoa_fisica.nome_registro

    def processar(self, user):
        nome_registro = self.cleaned_data.get('nome_registro')
        self.aluno.pessoa_fisica.nome_registro = nome_registro
        self.aluno.pessoa_fisica.save()
        self.registro.situacao = RegistroAuditoriaEnsino.SITUACAO_RESOLVIDO
        self.registro.registrar_situacao(user)
