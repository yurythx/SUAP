from django.core.exceptions import ValidationError

from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from documento_eletronico.models import DocumentoTexto
from processo_eletronico.models import Processo
from professor_sv.models import Configuracao, Contrato, ContratoAditivo, ContratoAditivoTempo, ContratoPublicacaoDocumento, Grupo, Perfil, Vaga
from rh.models import Servidor


class ConfiguracaoProfessorSvForm(forms.ModelFormPlus):
    fieldsets = (
        (
            'Limites',
            {
                'fields': (
                    'qtd_docentes_efetivo_exercicio',
                    'qtd_limite_professor_substituto',
                    'qtd_limite_professor_visitante',
                    'qtd_limite_professor_substituto_visitante',
                    'percentual_limite_de_psv_sobre_ee',
                )
            },
        ),
        (
            'Vagas',
            {
                'fields': (
                    'prefixo_vaga_substituto',
                    'prefixo_vaga_visitante',
                )
            },
        ),
        (
            'Outros',
            {
                'fields': (
                    'mov_emprest_re_campus_requer_justificativa',
                    'mov_emprest_campus_campus_requer_justificativa',
                    'qtd_dias_alertar_expiracao_emprestimo_vaga',
                    'qtd_dias_alertar_expiracao_contrato',
                )
            },
        ),
    )

    class Meta:
        model = Configuracao
        exclude = ()


class GrupoForm(forms.ModelFormPlus):
    class Meta:
        model = Grupo
        exclude = ()

    """
    def clean(self):
        vinculos_pode_gerenciar_vaga = self.cleaned_data.get('vinculos_pode_gerenciar_vaga')
        setores_cogpe_gerenciar = self.cleaned_data.get('setores_cogpe_gerenciar')
        vinculos_pode_gerenciar_vaga = vinculos_pode_gerenciar_vaga and vinculos_pode_gerenciar_vaga.count()
        setores_cogpe_gerenciar = setores_cogpe_gerenciar and setores_cogpe_gerenciar.count()
        if not vinculos_pode_gerenciar_vaga and not setores_cogpe_gerenciar:
            raise ValidationError('É preciso selecionar quem (setor ou pessoa) pode gerenciar as vagas relacionadas a este grupo.')
    """


class VagaAddForm(forms.ModelFormPlus):
    quantidade_substituto = forms.IntegerFieldPlus(label='Quantidade vagas que deseja gerar para Substituto', required=False)
    quantidade_visitante = forms.IntegerFieldPlus(label='Quantidade vagas que deseja gerar para Visitante', required=False)

    class Meta:
        model = Vaga
        fields = ('grupo_dono', 'quantidade_substituto', 'quantidade_visitante')

    def __init__(self, *args, **kwargs):
        self.categoria_selecionada = kwargs.pop('categoria')
        super().__init__(*args, **kwargs)
        if not self.categoria_selecionada.permite_substituto():
            self.fields['quantidade_substituto'].widget = forms.HiddenInput()
        if not self.categoria_selecionada.permite_visitante():
            self.fields['quantidade_visitante'].widget = forms.HiddenInput()

    def clean(self):
        quantidade_substituto = self.cleaned_data.get('quantidade_substituto')
        quantidade_visitante = self.cleaned_data.get('quantidade_visitante')

        if self.categoria_selecionada.permite_substituto() and self.categoria_selecionada.permite_visitante():
            if not quantidade_substituto and not quantidade_visitante:
                raise ValidationError('A quantidade de substitutos ou visitantes deve ser maior que zero')
        if self.categoria_selecionada.permite_substituto() and (quantidade_substituto and quantidade_substituto <= 0):
            raise ValidationError('A quantidade de substitutos deve ser maior que zero')
        if self.categoria_selecionada.permite_visitante() and (quantidade_visitante and quantidade_visitante <= 0):
            raise ValidationError('A quantidade de visitantes deve ser maior que zero')


class EmprestarVagaForm(forms.FormPlus):
    tomador = forms.ModelChoiceField(
        label='Tomador',
        queryset=Grupo.objects.all(),
        required=True,
    )

    processo = forms.ModelChoiceFieldPlus(
        Processo.objects.all(), label='Processo Eletrônico', widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS), required=True
    )

    emprestimo_ate = forms.DateFieldPlus(label='Empréstimo até', required=False)

    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', False)
        self.vaga = kwargs.pop('vaga', False)
        super().__init__(*args, **kwargs)

    def clean(self):
        tomador = self.cleaned_data.get('tomador')
        justificativa = self.cleaned_data.get('justificativa')

        pode = self.vaga.pode_emprestar_vaga(self.user, tomador=tomador, justificativa=justificativa)
        if not pode[0]:
            raise ValidationError(pode[1])


class BuscarVagasForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    grupo = forms.ModelChoiceFieldPlus(
        queryset=Grupo.objects.all().order_by('titulo'), widget=AutocompleteWidget(multiple=False), label='Grupo', required=True
    )

    tipo = forms.ChoiceField(required=False, choices=[[1, 'Todas'], [2, 'Apenas que é dono'], [3, 'Apenas as emprestadas']], label='Tipo de busca')

    def __init__(self, *args, **kwargs):
        self.grupos_pode_cadastrar = kwargs.pop('grupos_pode_cadastrar', None)

        super().__init__(*args, **kwargs)
        self.fields['grupo'].queryset = self.grupos_pode_cadastrar


class ContratoForm(forms.ModelFormPlus):
    documento_eletronico = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects.finalizados(),
        label='Documento Eletrônico Contrato',
        required=True,
    )

    servidor_docente_titular = forms.ModelChoiceFieldPlus(
        Servidor.objects.ativos().docentes(),
        label='Docente Efetivo',
        widget=AutocompleteWidget(search_fields=[*Servidor.SEARCH_FIELDS, 'codigo_vaga']),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.vaga = kwargs.pop('vaga', None)

        super().__init__(*args, **kwargs)

        self._vaga = None
        if self.instance and self.instance.pk:
            self._vaga = self.instance.vaga
        else:
            self._vaga = self.vaga

        uo_grupo = self._vaga.get_grupo_localizacao().uo
        if self._vaga.perfil == Perfil.SUBSTITUTO:
            self.fields['servidor_docente'].queryset = Servidor.objects.substitutos().filter(setor__uo=uo_grupo)
            self.fields['servidor_docente'].label = 'Professor Substituto'
        else:
            self.fields['servidor_docente'].queryset = Servidor.objects.visitantes().filter(setor__uo=uo_grupo)
            self.fields['servidor_docente'].label = 'Professor Visitante'
            self.fields['servidor_docente_titular'].widget = forms.HiddenInput()
            self.fields['codigo_vaga_servidor_docente_titular'].widget = forms.HiddenInput()

    class Meta:
        model = Contrato
        fields = (
            'servidor_docente',
            'documento_eletronico',
            'data_inicio',
            'data_fim',
            'servidor_docente_titular',
            'codigo_vaga_servidor_docente_titular',
        )

    def clean(self):
        servidor_docente = self.cleaned_data.get('servidor_docente')
        documento_eletronico = self.cleaned_data.get('documento_eletronico')
        servidor_docente_titular = self.cleaned_data.get('servidor_docente_titular')
        codigo_vaga_servidor_docente_titular = self.cleaned_data.get('codigo_vaga_servidor_docente_titular')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        if self._vaga.perfil == Perfil.SUBSTITUTO:
            if not (servidor_docente_titular or codigo_vaga_servidor_docente_titular):
                raise ValidationError('É necessário selecionar o Docente Efetivo ou informar o Código de Vaga')
            if servidor_docente_titular and codigo_vaga_servidor_docente_titular:
                raise ValidationError('Informe apenas o Docente Efetivo ou o Código de Vaga')

        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        ignore_este_contrato = None
        if self.instance and self.instance.pk:
            ignore_este_contrato = self.instance
        pode_finalizar_cadastro_contrato = Contrato.pode_finalizar_cadastro_contrato(
            servidor_docente=servidor_docente,
            documento_eletronico=documento_eletronico,
            vaga=self._vaga,
            data_fim=data_fim,
            servidor_docente_titular=servidor_docente_titular,
            codigo_vaga_servidor_docente_titular=codigo_vaga_servidor_docente_titular,
            ignore_este_contrato=ignore_este_contrato,
        )
        if not pode_finalizar_cadastro_contrato[0]:
            raise ValidationError(pode_finalizar_cadastro_contrato[1])

        # Só edita data_fim se não tiver aditivos
        if self.instance and self.instance.pk:
            alterou_data = data_inicio != self.instance.data_inicio or data_fim != self.instance.data_fim
            if alterou_data and self.instance.contratoaditivotempo_set.all().exists():
                raise ValidationError('A Data de Início/Término só pode ser alterada se não tiver aditivo.')


class ContratoPublicacaoDocumentoForm(forms.ModelFormPlus):
    documento_eletronico = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects.finalizados(),
        label='Documento Eletrônico',
        required=True,
    )

    class Meta:
        model = ContratoPublicacaoDocumento
        exclude = ('contrato',)


class ContratoAditivoForm(forms.ModelFormPlus):
    documento_eletronico = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects.finalizados(),
        label='Documento Eletrônico',
        required=True,
    )

    class Meta:
        model = ContratoAditivo
        exclude = ('contrato',)


class ContratoAditivoTempoForm(forms.ModelFormPlus):
    documento_eletronico = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects.finalizados(),
        label='Documento Eletrônico',
        required=True,
    )

    class Meta:
        model = ContratoAditivoTempo
        exclude = ('contrato',)

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', False)
        super().__init__(*args, **kwargs)

    def clean(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        if data_inicio and not (data_inicio > self.contrato.data_expira):
            raise ValidationError('O aditivo de tempo deve iniciar depois da data de expiração do contrato.')

        ignore_este_contrato = self.contrato
        pode_finalizar_cadastro_contrato = Contrato.pode_finalizar_cadastro_contrato(
            servidor_docente=ignore_este_contrato.servidor_docente,
            documento_eletronico=ignore_este_contrato.documento_eletronico,
            vaga=ignore_este_contrato.vaga,
            data_fim=data_fim,
            servidor_docente_titular=ignore_este_contrato.servidor_docente_titular,
            codigo_vaga_servidor_docente_titular=ignore_este_contrato.codigo_vaga_servidor_docente_titular,
            ignore_este_contrato=ignore_este_contrato,
        )
        if not pode_finalizar_cadastro_contrato[0]:
            raise ValidationError(pode_finalizar_cadastro_contrato[1])


class ContratoFinalizarForm(forms.FormPlus):
    data_conclusao = forms.DateFieldPlus(label='Data de conclusão', required=True)

    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa')

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        data_conclusao = self.cleaned_data.get('data_conclusao')
        if data_conclusao and self.contrato:
            if not (data_conclusao > self.contrato.data_inicio):
                raise ValidationError('A data de conclusão do contrato deve ser posterior ao seu início.')


class ComSenhaIrreversivelForm(forms.FormPlus):
    confirmacao = forms.BooleanField(label='Confirmo esta operação e estou ciente de que é IRREVERSSÍVEL', initial=False, required=True)
    senha = forms.PasswordField()
