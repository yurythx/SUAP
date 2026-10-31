from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from comum.models import Ano, Configuracao, Sala, Vinculo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    AtaEletronica,
    MatriculaPeriodo,
    Professor,
    ProjetoFinal,
    SituacaoMatriculaPeriodo,
)
from rh.models import UnidadeOrganizacional


class ProjetoFinalForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus', required=False)
    local_defesa = forms.ModelChoiceFieldPlus(
        Sala.ativas,
        label='Local',
        required=False,
        widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS, form_filters=[('uo', 'predio__uo__in')]),
    )
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, required=True, label='Período Letivo')
    orientador = forms.ModelChoiceField(
        queryset=Vinculo.objects, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Orientador', required=True
    )
    presidente = forms.ModelChoiceField(
        queryset=Professor.objects, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS), label='Presidente', required=True
    )

    fieldsets = (
        ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), 'titulo', 'resumo', 'tipo', 'informacao_complementar')}),
        ('Dados da Orientação', {'fields': ('orientador', 'coorientadores_vinculos')}),
        ('Dados da Defesa', {'fields': ('data_defesa', 'data_deposito', 'uo', 'local_defesa', 'defesa_online')}),
        (
            'Dados da Banca',
            {
                'fields': (
                    'presidente',
                    'examinador_interno',
                    ('examinador_externo', 'is_examinador_externo'),
                    ('terceiro_examinador', 'is_terceiro_examinador_externo'),
                )
            },
        ),
        (
            'Dados da Suplência da Banca',
            {'fields': ('suplente_interno', ('suplente_externo', 'is_suplente_externo'), ('terceiro_suplente', 'is_terceiro_suplente_externo'))},
        ),
    )

    class Meta:
        model = ProjetoFinal
        fields = (
            'titulo',
            'resumo',
            'tipo',
            'informacao_complementar',
            'suplente_interno',
            'is_suplente_externo',
            'suplente_externo',
            'data_defesa',
            'data_deposito',
            'local_defesa',
            'defesa_online',
            'presidente',
            'examinador_interno',
            'is_examinador_externo',
            'examinador_externo',
            'terceiro_suplente',
            'is_terceiro_suplente_externo',
            'terceiro_examinador',
            'is_terceiro_examinador_externo',
            'coorientadores_vinculos',
        )

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not aluno.matriz or not aluno.matriz.exige_tcc:
            self.fields['tipo'].choices = [['Relatório de Projeto', 'Relatório de Projeto']]
        uo = aluno.curso_campus.diretoria.setor.uo
        self.fields['uo'].initial = uo.id
        if self.instance.pk:
            self.fields['ano_letivo'].initial = self.instance.matricula_periodo.ano_letivo.pk
            self.fields['periodo_letivo'].initial = self.instance.matricula_periodo.periodo_letivo
            if self.instance.local_defesa:
                self.fields['uo'].initial = self.instance.local_defesa.predio.uo.id
        self.aluno = aluno

        qs_vinculos = Vinculo.objects.prestadores() | Vinculo.objects.servidores()
        qs_orientador = Vinculo.objects.none()

        qs_professores = Professor.objects.all()
        qs_presidente = Professor.objects.none()

        if not self.request.user.has_perm('comum.is_administrador_academico'):
            if self.instance.pk:
                qs_orientador = qs_vinculos.filter(ativo=False, pk=self.instance.orientador.vinculo_id)
                qs_presidente = qs_professores.filter(vinculo__ativo=False, pk=self.instance.presidente_id)
            qs_vinculos = qs_vinculos.filter(ativo=True)
            qs_professores = qs_professores.filter(vinculo__ativo=True)

        self.fields['orientador'].queryset = (qs_vinculos | qs_orientador).distinct()
        self.fields['presidente'].queryset = (qs_professores | qs_presidente).distinct()

        if self.instance.pk:
            self.fields['orientador'].initial = self.instance.orientador.vinculo.pk
            # Preenche titulo da pesquisa caso exista no Aluno
            if self.instance.get_aluno().titulo_projeto_pesquisa and not self.instance.titulo:
                self.instance.titulo = self.instance.get_aluno().titulo_projeto_pesquisa
        elif self.aluno.orientador:
            self.fields['orientador'].initial = self.aluno.orientador
            self.fields['orientador'].initial = self.aluno.orientador.pk

        if self.aluno.coorientadores.exists():
            self.fields['coorientadores_vinculos'].initial = self.aluno.coorientadores.all()

        qs_vinculo = Vinculo.objects.filter(ativo=True).exclude(tipo_relacionamento__model='aluno')
        if Configuracao.get_valor_por_chave('edu', 'tipo_ata_projeto_final') == ProjetoFinal.TIPO_ATA_ELETRONICA:
            qs_vinculo = qs_vinculo.filter(user__username__isnull=False)
        self.fields['examinador_interno'].queryset = qs_vinculo.funcionarios()
        self.fields['examinador_externo'].queryset = qs_vinculo
        self.fields['terceiro_examinador'].queryset = qs_vinculo
        self.fields['suplente_interno'].queryset = qs_vinculo
        self.fields['suplente_externo'].queryset = qs_vinculo
        self.fields['terceiro_suplente'].queryset = qs_vinculo
        self.fields['coorientadores_vinculos'].queryset = qs_vinculo

    def clean(self):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')

        if ano_letivo and periodo_letivo:
            qs_matricula_periodo = MatriculaPeriodo.objects.filter(aluno=self.aluno, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo).exclude(
                situacao_id=SituacaoMatriculaPeriodo.EM_ABERTO
            )
            if not qs_matricula_periodo.exists():
                raise forms.ValidationError('O aluno não possui matrícula no ano/período letivo selecionado.')
            else:
                self.matricula_periodo = qs_matricula_periodo[0]
                if self.matricula_periodo.situacao.pk == SituacaoMatriculaPeriodo.EM_ABERTO:
                    raise forms.ValidationError('A situação do aluno no período selecionado é "Em Aberto".')
                if ProjetoFinal.objects.filter(matricula_periodo=self.matricula_periodo).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError('O aluno já possui um trabalho de conclusão de curso no ano/período letivo selecionado.')

        return self.cleaned_data

    def save(self, *args, **kwargs):
        orientador = self.cleaned_data['orientador']
        obj = super().save(False)
        qs = Professor.objects.filter(vinculo__id=orientador.pk)
        if qs.exists():
            obj.orientador = qs[0]
        else:
            professor = Professor()
            professor.vinculo = orientador
            professor.save()
            obj.orientador = professor
            Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)
        obj.matricula_periodo = self.matricula_periodo
        obj.save()
        obj.coorientadores_vinculos.clear()
        for coorientador in self.cleaned_data['coorientadores_vinculos']:
            obj.coorientadores_vinculos.add(coorientador)

        if Configuracao.get_valor_por_chave('edu', 'tipo_ata_projeto_final') == ProjetoFinal.TIPO_ATA_ELETRONICA:
            ata = AtaEletronica.objects.filter(projeto_final=obj).first()
            if ata:
                ata.criar_assinaturas()


class ParticipacaoProjetoFinalForm(forms.Form):
    METHOD = 'GET'
    participante = forms.ChoiceField(choices=[])

    def __init__(self, projeto_final, *args, **kwargs):
        super().__init__(*args, **kwargs)
        participantes = []
        if projeto_final.orientador:
            participantes.append(['orientador', 'Orientador - ' + projeto_final.orientador.vinculo.pessoa.nome])
        if projeto_final.presidente:
            participantes.append(['presidente', 'Presidente - ' + projeto_final.presidente.vinculo.pessoa.nome])
        if projeto_final.examinador_interno:
            participantes.append(['examinador_interno', 'Examinador (Interno) - ' + projeto_final.examinador_interno.pessoa.nome])
        if projeto_final.examinador_externo:
            if projeto_final.is_examinador_externo:
                participantes.append(['examinador_externo', 'Segundo Examinador (Externo) - ' + projeto_final.examinador_externo.pessoa.nome])
            else:
                participantes.append(['examinador_externo', 'Segundo Examinador (Interno) - ' + projeto_final.examinador_externo.pessoa.nome])
        if projeto_final.terceiro_examinador:
            if projeto_final.is_terceiro_examinador_externo:
                participantes.append(['terceiro_examinador', 'Terceiro Examinador (Externo) - ' + projeto_final.terceiro_examinador.pessoa.nome])
            else:
                participantes.append(['terceiro_examinador', 'Terceiro Examinador (Interno) - ' + projeto_final.terceiro_examinador.pessoa.nome])
        if projeto_final.suplente_interno:
            participantes.append(['suplente_interno', 'Examinador Suplente Interno - ' + projeto_final.suplente_interno.pessoa.nome])
        if projeto_final.suplente_externo:
            if projeto_final.is_suplente_externo:
                participantes.append(['suplente_externo', 'Primeiro Suplente (Externo) - ' + projeto_final.suplente_externo.pessoa.nome])
            else:
                participantes.append(['suplente_externo', 'Primeiro Suplente (Interno) - ' + projeto_final.suplente_externo.pessoa.nome])
        if projeto_final.terceiro_suplente:
            if projeto_final.is_terceiro_suplente_externo:
                participantes.append(['suplente_externo', 'Segundo Suplente (Externo) - ' + projeto_final.terceiro_suplente.pessoa.nome])
            else:
                participantes.append(['suplente_externo', 'Segundo Suplente (Interno) - ' + projeto_final.terceiro_suplente.pessoa.nome])

        for coorientador in projeto_final.coorientadores_vinculos.all():
            participantes.append([f'coorientador_{coorientador.pk}', 'Coorientador - ' + coorientador.pessoa.nome])

        self.fields['participante'].choices = participantes


class LancarResultadoProjetoFinalForm(forms.ModelForm):
    DOCUMENTO_URL = 1
    DOCUMENTO_ARQUIVO = 2
    TIPO_DOCUMENTO_CHOICES = [[DOCUMENTO_URL, 'URL'], [DOCUMENTO_ARQUIVO, 'Arquivo']]

    resultado_data = forms.DateTimeFieldPlus(label='Data da apresentação', required=True)
    situacao = forms.ChoiceField(label='Situação', choices=ProjetoFinal.SITUACAO_CHOICES, required=True)
    tipo_documento = forms.ChoiceField(choices=TIPO_DOCUMENTO_CHOICES, widget=forms.RadioSelect(), label='Tipo de Documento')
    ata = forms.FileFieldPlus(label='Ata de Defesa / Documento Comprobatório de Prática', required=True)
    documento = forms.FileFieldPlus(label='Arquivo do TCC / Relatório', required=False, filetypes=['pdf'])

    class Meta:
        model = ProjetoFinal
        fields = ('resultado_data', 'nota', 'situacao', 'tipo_documento', 'documento', 'documento_url', 'ata')

    class Media:
        js = ('/static/edu/js/LancarResultadoProjetoFinalForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipo_ata = Configuracao.get_valor_por_chave('edu', 'tipo_ata_projeto_final') or ProjetoFinal.TIPO_ATA_FISICA
        if self.tipo_ata == ProjetoFinal.TIPO_ATA_ELETRONICA:
            self.fields['consideracoes'] = forms.CharFieldPlus(label='Observação / Apreciações', widget=forms.Textarea(), max_length=2500)
            self.fields['ata'].required = False
            self.fieldsets = (
                ('Resultado', {'fields': (('resultado_data', 'situacao'), 'nota', 'consideracoes')}),
                ('Arquivos', {'fields': ('tipo_documento', 'documento', 'documento_url')}),
            )
        else:
            self.fieldsets = (
                ('Resultado', {'fields': (('resultado_data', 'situacao'), 'nota')}),
                ('Arquivos', {'fields': ('tipo_documento', 'documento', 'documento_url', 'ata')}),
            )

        if self.instance.matricula_periodo.aluno.matriz.estrutura.is_lancamento_conceito():
            choices = [['', '---']]
            for choice in settings.REPRESENTACAO_CONCEITUAL:
                choices.append([settings.REPRESENTACAO_CONCEITUAL[choice], choice])
            self.fields['nota'] = forms.ChoiceField(choices=choices, label='Conceito', required=True)

    def clean_resultado_data(self):
        resultado_data = self.cleaned_data.get('resultado_data')
        if resultado_data and self.instance.data_defesa and resultado_data < self.instance.data_defesa:
            raise ValidationError('A data da apresentação não pode ser menor que a data prevista informada no cadastro do TCC.')
        return resultado_data

    def save(self, *args, **kwargs):
        projeto_final = super().save(*args, **kwargs)
        if self.tipo_ata == ProjetoFinal.TIPO_ATA_ELETRONICA:
            consideracoes = self.cleaned_data['consideracoes']
            if not AtaEletronica.objects.filter(projeto_final=projeto_final).exists():
                ata = AtaEletronica.objects.create(projeto_final=projeto_final, consideracoes=consideracoes)
                ata.criar_assinaturas()
            else:
                ata = AtaEletronica.objects.get(projeto_final=projeto_final)
                ata.consideracoes = consideracoes
                ata.save()


class UploadDocumentoProjetoFinalForm(forms.ModelForm):
    DOCUMENTO_URL = 1
    DOCUMENTO_ARQUIVO = 2
    TIPO_DOCUMENTO_CHOICES = [[DOCUMENTO_URL, 'URL'], [DOCUMENTO_ARQUIVO, 'Arquivo']]

    tipo_documento_final = forms.ChoiceField(choices=TIPO_DOCUMENTO_CHOICES, widget=forms.RadioSelect(), label='Tipo de Documento')
    documento_final = forms.FileFieldPlus(label='Arquivo do TCC / Relatório', required=False, filetypes=['pdf'])

    class Meta:
        model = ProjetoFinal
        fields = ('tipo_documento_final', 'documento_final', 'documento_final_url')

    class Media:
        js = ('/static/edu/js/UploadDocumentoProjetoFinalForm.js',)

    fieldsets = (('Arquivo', {'fields': ('tipo_documento_final', 'documento_final', 'documento_final_url')}),)


class EditarTituloPesquisaForm(forms.ModelFormPlus):
    titulo_projeto_pesquisa = forms.CharFieldPlus(required=True, label='Título do Projeto de Pesquisa', width=500)

    class Meta:
        model = Aluno
        fields = ('titulo_projeto_pesquisa',)
