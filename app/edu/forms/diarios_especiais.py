from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.aggregates import Sum

from comum.models import Ano, Sala
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from edu.models import (
    Aluno,
    Componente,
    ConfiguracaoCreditosEspeciais,
    CreditoEspecial,
    CursoCampus,
    Diario,
    DiarioEspecial,
    Diretoria,
    Encontro,
    HorarioCampus,
    ItemConfiguracaoCreditosEspeciais,
    Professor,
    SituacaoMatricula,
)


class DiarioEspecialForm(forms.ModelForm):
    professores = forms.MultipleModelChoiceFieldPlus(Professor.objects, label='Professores', required=True)
    participantes = forms.MultipleModelChoiceFieldPlus(Aluno.objects, label='Participantes', required=False)

    # def clean_data_fim(self):
    #     if 'data_inicio' in self.cleaned_data and 'data_fim' in self.cleaned_data:
    #         if self.cleaned_data['data_fim'] < self.cleaned_data['data_inicio']:
    #             raise ValidationError(u'A data de fim deve ser maior que a data de início.')
    #     return self.cleaned_data['data_fim']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['horario_campus'].queryset = HorarioCampus.locals.all()
        self.fields['diretoria'].queryset = Diretoria.objects.filter(pk__in=Diretoria.locals.values_list('pk', flat=True))
        self.fields['participantes'].queryset = Aluno.locals.filter(situacao=SituacaoMatricula.MATRICULADO)
        self.fields['componente'].queryset = Componente.objects.filter(tipo__descricao='ATV')

    def clean_descricao(self):
        descricao = self.cleaned_data.get('descricao')
        if self.cleaned_data.get('is_centro_aprendizagem') and not descricao:
            raise forms.ValidationError('Informe a descrição do centro de aprendizagem.')
        return descricao

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        if 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            ano_letivo = cleaned_data.get('ano_letivo')
            periodo_letivo = cleaned_data.get('periodo_letivo')
            for professor in cleaned_data.get('professores') or []:
                if PlanoIndividualTrabalhoV2.objects.filter(
                    ano_letivo=ano_letivo,
                    periodo_letivo=periodo_letivo,
                    professor=professor,
                    publicado=True,
                ).exists():
                    raise forms.ValidationError(
                        f'Não é possível vincular professor {professor} ao diário. Docente já tem RIT publicado para o período {ano_letivo}.{periodo_letivo}'
                    )
        return cleaned_data

    class Meta:
        model = DiarioEspecial
        exclude = ('sala',)


class DefinirLocalAulaDiarioEspecialForm(forms.FormPlus):
    sala = forms.ModelChoiceFieldPlus(Sala.ativas, required=False)

    def __init__(self, diario_especial, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diario_especial = diario_especial
        uo = diario_especial.diretoria.setor.uo
        self.fields['sala'].queryset = self.fields['sala'].queryset.filter(predio__uo=uo)

    def processar(self):
        self.diario_especial.sala = self.cleaned_data['sala']
        self.diario_especial.save()


class AdicionarAlunosDiarioEspecialForm(forms.FormPlus):
    alunos = forms.MultipleModelChoiceFieldPlus(Aluno.objects, label='Alunos')

    def __init__(self, diario_especial, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['alunos'].queryset = Aluno.locals.filter(situacao=SituacaoMatricula.MATRICULADO)
        self.diario_especial = diario_especial

    def processar(self):
        for aluno in self.cleaned_data.get('alunos'):
            self.diario_especial.participantes.add(aluno)
        self.diario_especial.save()


class AdicionarAlunosDiarioEspecialWizard(FormWizardPlus):
    METHOD = 'GET'

    diario = forms.ModelChoiceFieldPlus(Diario.objects, required=False, label='Diário')

    alunos = forms.MultipleModelChoiceField(
        Aluno.locals.none(), label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html'), required=True
    )

    steps = ([('Diário', {'fields': ('diario',)})], [('Alunos', {'fields': ('alunos',)})])

    def __init__(self, request, diario_especial, *args, **kwargs):
        self.request = request
        self.diario_especial = diario_especial
        super().__init__(*args, **kwargs)

        semestrais = Diario.objects.filter(
            ano_letivo=diario_especial.ano_letivo,
            periodo_letivo=diario_especial.periodo_letivo,
            turma__curso_campus__diretoria__setor__uo=diario_especial.diretoria.setor.uo,
            turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL,
        )

        anuais = Diario.objects.filter(
            ano_letivo=diario_especial.ano_letivo,
            turma__curso_campus__diretoria__setor__uo=diario_especial.diretoria.setor.uo,
            turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL,
        )

        self.fields['diario'].queryset = semestrais | anuais

    def next_step(self):
        diario = self.get_entered_data('diario')
        if 'alunos' in self.fields:
            self.fields['alunos'].queryset = Aluno.objects.filter(matriculaperiodo__matriculadiario__diario=diario)

    def processar(self):
        for aluno in self.cleaned_data.get('alunos'):
            self.diario_especial.participantes.add(aluno)
        self.diario_especial.save()


class AdicionarProfessorDiarioEspecialForm(forms.FormPlus):
    professor = forms.ModelChoiceField(
        queryset=Professor.objects, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS), label='Professor'
    )

    def __init__(self, diario_especial, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['professor'].queryset = Professor.objects.all()
        self.diario_especial = diario_especial

    def processar(self):
        self.diario_especial.professores.add(self.cleaned_data.get('professor'))
        self.diario_especial.save()

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        if 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            diario_especial = self.diario_especial
            professor = cleaned_data.get('professor')
            if PlanoIndividualTrabalhoV2.objects.filter(
                ano_letivo=diario_especial.ano_letivo,
                periodo_letivo=diario_especial.periodo_letivo,
                professor=professor,
                publicado=True,
            ).exists():
                raise forms.ValidationError(
                    f'Não é possível vincular professor {professor} ao diário. Docente já tem RIT publicado para o período {diario_especial.ano_letivo}.{diario_especial.periodo_letivo}'
                )
        return cleaned_data


class AdicionarEncontroDiarioEspecialForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data')
    conteudo = forms.CharField(widget=forms.Textarea(), label='Atividade')
    participantes = forms.MultipleModelChoiceField(
        Aluno.locals.none(), label='Participantes', widget=RenderableSelectMultiple('widgets/alunos_widget.html'), required=False
    )

    def __init__(self, diario_especial, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diario_especial = diario_especial
        self.fields['participantes'].queryset = self.diario_especial.participantes.all()
        self.fields['participantes'].widget.max_result = self.diario_especial.participantes.count()

    def processar(self):
        encontro = Encontro()
        encontro.data = self.cleaned_data.get('data')
        encontro.conteudo = self.cleaned_data.get('conteudo')
        encontro.diario_especial = self.diario_especial
        encontro.save()

        encontro.participantes.set(self.cleaned_data.get('participantes'))
        encontro.save()


class AtualizarEncontroDiarioEspecialForm(forms.ModelForm):
    participantes = forms.MultipleModelChoiceField(
        Aluno.locals.none(), label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html'), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['participantes'].queryset = self.instance.diario_especial.participantes.all()
        self.fields['participantes'].widget.max_result = self.instance.diario_especial.participantes.count()
        self.fields['participantes'].initial = list(self.instance.participantes.values_list('pk', flat=True))

    class Meta:
        model = Encontro
        exclude = ('diario_especial',)


class ItemConfiguracaoCreditosEspeciaisForm(forms.ModelFormPlus):
    class Meta:
        model = ItemConfiguracaoCreditosEspeciais
        exclude = ('configuracao',)


class ConfiguracaoCreditosEspeciaisForm(forms.ModelFormPlus):
    fieldsets = (('Dados gerais', {'fields': ('descricao', 'quantidade_maxima_creditos_especiais', 'ativo')}),)

    class Meta:
        model = ConfiguracaoCreditosEspeciais
        exclude = ()


class CreditoEspecialForm(forms.ModelFormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    item_configuracao_creditos_especiais = forms.ModelChoiceField(ItemConfiguracaoCreditosEspeciais.objects, label='Tipo de Atividade')

    class Meta:
        model = CreditoEspecial
        exclude = ('matricula_periodo',)

    fieldsets = (
        ('Período Letivo', {'fields': (('ano_letivo', 'periodo_letivo'),)}),
        ('Atividade', {'fields': ('item_configuracao_creditos_especiais',)}),
    )

    def __init__(self, aluno, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno
        self.fields['ano_letivo'].queryset = Ano.objects.filter(
            pk__in=aluno.matriculaperiodo_set.order_by('ano_letivo').values_list('ano_letivo', flat=True).distinct()
        )
        self.fields['item_configuracao_creditos_especiais'].queryset = self.fields['item_configuracao_creditos_especiais'].queryset.filter(
            configuracao=aluno.matriz.configuracao_creditos_especiais
        )
        if self.instance.pk:
            self.initial['ano_letivo'] = self.instance.matricula_periodo.ano_letivo.pk
            self.initial['periodo_letivo'] = self.instance.matricula_periodo.periodo_letivo

    def clean(self):
        if not self.instance.pk:
            creditos_ja_cadastrados = (
                CreditoEspecial.objects.filter(matricula_periodo__aluno=self.aluno)
                .aggregate(Sum('item_configuracao_creditos_especiais__equivalencia_creditos'))
                .get('item_configuracao_creditos_especiais__equivalencia_creditos__sum')
                or 0
            )
            if creditos_ja_cadastrados >= self.aluno.matriz.configuracao_creditos_especiais.quantidade_maxima_creditos_especiais:
                raise ValidationError(
                    f'Não é possível cadastrar este crédito especial, pois o aluno já atingiu o limite de {self.aluno.matriz.configuracao_creditos_especiais.quantidade_maxima_creditos_especiais} créditos especiais estipulados na matriz.'
                )
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        if not self.aluno.matriculaperiodo_set.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo).exists():
            raise ValidationError('O aluno não possui matrícula no ano/período selecionado.')
        return self.cleaned_data

    def save(self, *args, **kwargs):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        self.instance.matricula_periodo = self.aluno.matriculaperiodo_set.get(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
        super().save(*args, **kwargs)
