from __future__ import annotations

import pandas as pd
import sentry_sdk
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction

from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from djtools.templatetags.filters import in_group
from djtools.utils import cpf_valido, email_valido, mask_cpf
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    Diretoria,
    Minicurso,
    Modalidade,
    MonitorMinicurso,
    ParticipanteTurmaMinicurso,
    Professor,
    ProfessorMinicurso,
    SituacaoMatricula,
    TurmaMinicurso,
)
from rh.deduplicacao.entrada import Politica
from rh.models import PessoaFisica


class ClonarMinicursoForm(forms.FormPlus):
    diretorias = forms.ModelMultiplePopupChoiceField(
        Diretoria.objects.all(),
        label='Diretorias',
        required=False,
        help_text='Informe as diretorias para as quais deseja ter esse curso clonado.',
    )


class ConteudoMinicursoFormset(forms.models.BaseInlineFormSet):
    def clean(self):
        ch_somada = 0
        for form in self.forms:
            if form.cleaned_data:
                ch_somada += form.cleaned_data.get('ch') or 0
                if ch_somada > 160:
                    raise forms.ValidationError('O limite para carga horária total é de 160 horas.')


class MinicursoForm(forms.ModelFormPlus):
    descricao_certificado = forms.CharFieldPlus(label='Descrição para o certificado', widget=forms.TextInput(attrs={'class': ''}))
    diretoria = forms.ModelChoiceField(Diretoria.objects.none(), widget=forms.Select())
    ppc = forms.FileFieldPlus(label='PPC', required=False)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=True)
    periodo_letivo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=True)
    ch_total = forms.IntegerField(label='Carga Horária Total h/r', min_value=0)

    class Meta:
        model = Minicurso
        exclude = ()

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'descricao_certificado',
                    ('diretoria', 'extensao'),
                    ('autoinstrucional', 'tipo_curso_autoinstrucional'),
                    'codigo_sistec',
                    'resolucao_criacao',
                )
            },
        ),
        ('Dados de Criação', {'fields': (('ano_letivo', 'periodo_letivo'), 'ppc')}),
        ('Informação da Carga Horária', {'fields': (('ch_total', 'tipo_hora_aula'),)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals
        self.initial['diretoria'] = self.instance.diretoria
        self.initial['descricao_certificado'] = self.instance.descricao_historico
        self.initial['ano_letivo'] = self.instance.ano_letivo
        self.initial['periodo_letivo'] = self.instance.periodo_letivo

        is_administrador = in_group(self.request.user, 'Administrador Acadêmico')
        if not is_administrador:
            self.fields['codigo_sistec'].widget.attrs['disabled'] = 'disabled'

        for field_name in ['descricao_certificado']:
            self.fields[field_name].widget.attrs['class'] = self.fields[field_name].widget.attrs.get('class')

        choices = [[0, '---']]
        choices.extend(settings.TIPO_HORA_AULA_CHOICES)
        self.fields['tipo_hora_aula'] = forms.ChoiceField(choices=choices, label='Tipo Hora Aula', required=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.instance.descricao = 'FIC- {}'.format(self.cleaned_data['descricao_certificado'])
        self.instance.descricao_historico = self.cleaned_data['descricao_certificado']
        self.instance.modalidade_id = Modalidade.FIC_MENOS
        return super().save(*args, **kwargs)


class TurmaMinicursoForm(forms.ModelFormPlus):
    professores = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Professores', required=True)
    planilha = forms.FileFieldPlus(
        help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, contendo as seguintes colunas: CPF, Nome e E-mail.', required=False
    )

    class Meta:
        model = TurmaMinicurso
        exclude = ('minicurso', 'participantes', 'codigo')

    def __init__(self, minicurso=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.minicurso = minicurso
        self.participantes = []
        for field_name in ['descricao']:
            self.fields[field_name].widget.attrs['class'] = self.fields[field_name].widget.attrs.get('class')

        if self.minicurso.ch_total >= 20:
            self.fields['gerar_matricula'].required = True
            self.initial['gerar_matricula'] = True

    def clean_professores(self):
        for vinculo in self.cleaned_data['professores'].all():
            if not hasattr(vinculo, 'user'):
                raise forms.ValidationError('O funcionário {} não pode ser adicionado pois não possui usuário no sistema.')
        return self.cleaned_data['professores']

    def clean(self):
        if self.cleaned_data['planilha']:
            try:
                planilha = self.cleaned_data['planilha'].file
                df = pd.read_excel(planilha, header=None)
                for _index, row in df.iterrows():
                    cpf = mask_cpf(str(row.iloc[0]))
                    if not cpf_valido(cpf):
                        raise ValidationError(f'O cpf {cpf} é inválido.')
                    nome = str(row.iloc[1])
                    email = str(row.iloc[2])
                    if not email_valido(email):
                        raise ValidationError(f'O e-mail {email} é inválido.')
                    participante = {'cpf': cpf, 'nome': nome, 'email': email}
                    if self.instance.pk:
                        qs = self.instance.participanteturmaminicurso_set.filter(turma=self.instance, aluno__pessoa_fisica__cpf=cpf)
                        if not qs.exists():
                            self.participantes.append(participante)
                    else:
                        self.participantes.append(participante)
            except Exception:
                raise ValidationError(
                    'Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx, sem cabeçalho e se contém as seguintes colunas: CPF, Nome e E-mail.'
                )
        return self.cleaned_data

    @transaction.atomic
    def processar(self) -> None:
        self.instance.minicurso = self.minicurso
        if self.instance.pk:
            self.instance.professores.clear()
        self.instance.minicurso = self.minicurso
        self.instance.ano_letivo = self.cleaned_data['ano_letivo']
        self.instance.periodo_letivo = self.cleaned_data['periodo_letivo']
        self.instance.data_inicio = self.cleaned_data['data_inicio']
        self.instance.data_fim = self.cleaned_data['data_fim']
        self.instance.gerar_matricula = self.cleaned_data['gerar_matricula']
        self.instance.save()
        for vinculo in self.cleaned_data['professores'].all():
            qs = Professor.objects.filter(vinculo__id=vinculo.pk)
            if qs.exists():
                professor = qs[0]
                self.instance.professores.add(professor)
            else:
                professor = Professor()
                professor.vinculo = vinculo
                professor.save()
                self.instance.professores.add(professor)
        for participante in self.participantes:
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': participante['cpf'], 'nome': participante['nome']}, Politica.PREENCHER)
            aluno = self.instance.adicionar_novo_aluno(pessoa_fisica)
            if participante['email'] and aluno:
                v = aluno.get_vinculo()
                if v:
                    v.email_pessoal = participante['email']
                    v.save(update_fields=['email_pessoal'])


class EditarTurmaMinicursoForm(forms.ModelFormPlus):
    class Meta:
        model = TurmaMinicurso
        exclude = ('participantes',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.participanteturmaminicurso_set.exclude(aluno__situacao=SituacaoMatricula.MATRICULADO).exists():
            self.fields['descricao'].widget = forms.HiddenInput()
            self.fields['ano_letivo'].widget = forms.HiddenInput()
            self.fields['periodo_letivo'].widget = forms.HiddenInput()
            self.fields['data_inicio'].widget = forms.HiddenInput()
            self.fields['data_fim'].widget = forms.HiddenInput()
            self.fields['gerar_matricula'].widget = forms.HiddenInput()
        minicurso_id = self.request.GET.get('minicurso')
        self.participantes = []
        if minicurso_id:
            self.fields['minicurso'].initial = minicurso_id
            self.fields['minicurso'].widget = forms.HiddenInput()
            minicurso = Minicurso.objects.get(pk=minicurso_id)
            if minicurso.ch_total >= 20:
                self.fields['gerar_matricula'].required = True
                self.initial['gerar_matricula'] = True

        for field_name in ['descricao']:
            self.fields[field_name].widget.attrs['class'] = self.fields[field_name].widget.attrs.get('class')

    def clean(self):
        if self.instance.pk and self.instance.participanteturmaminicurso_set.exclude(aluno__situacao=SituacaoMatricula.MATRICULADO).exists():
            old = TurmaMinicurso.objects.get(pk=self.instance.pk)
            if (
                old.descricao != self.cleaned_data.get('descricao')
                or old.ano_letivo != self.cleaned_data.get('ano_letivo')
                or old.periodo_letivo != self.cleaned_data.get('periodo_letivo')
                or old.data_inicio != self.cleaned_data.get('data_inicio')
                or old.data_fim != self.cleaned_data.get('data_fim')
                or old.gerar_matricula != self.cleaned_data.get('gerar_matricula')
            ):
                raise forms.ValidationError('Esta turma de minicurso não pode ser editada pois já possui aluno cadastrado.')

        return self.cleaned_data

    @transaction.atomic
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class MonitorMinicursoForm(forms.ModelFormPlus):
    class Meta:
        model = MonitorMinicurso
        fields = ('aluno', 'carga_horaria')

    def clean_aluno(self) -> Aluno | None:
        aluno: Aluno | None = self.cleaned_data.get('aluno')
        turma_minicurso_id = getattr(self.instance, 'turma_minicurso_id', None)
        if aluno and turma_minicurso_id:
            qs = MonitorMinicurso.objects.filter(turma_minicurso_id=turma_minicurso_id, aluno=aluno)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Este aluno já está cadastrado como monitor desta turma.')
        return aluno


class ProfessorMinicursoForm(forms.ModelFormPlus):
    vinculo = forms.ModelChoiceField(
        queryset=Vinculo.objects, label='Professor', required=True, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )

    fieldsets = (('', {'fields': ('tipo', 'vinculo', 'carga_horaria')}),)

    class Meta:
        model = ProfessorMinicurso
        fields = ('carga_horaria', 'tipo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        qs_prestadores = Vinculo.objects.prestadores().filter(ativo=True, professor__isnull=False)
        qs_docentes = Vinculo.objects.servidores_docentes().filter(ativo=True)
        qs_tecnicos = Vinculo.objects.servidores_tecnicos_administrativos().filter(ativo=True)

        if self.instance.pk:
            qs_docentes = qs_docentes | qs_docentes.filter(ativo=False, pk=self.instance.professor.vinculo.id)
            qs_tecnicos = qs_tecnicos | qs_tecnicos.filter(ativo=False, pk=self.instance.professor.vinculo.id)
        self.fields['vinculo'].queryset = (qs_docentes | qs_tecnicos | qs_prestadores).distinct()

        if self.instance.pk:
            self.fields['vinculo'].initial = self.instance.professor.vinculo.pk

    def save(self, *args, **kwargs):
        vinculo = self.cleaned_data['vinculo']
        obj = super().save(False)
        qs = Professor.objects.filter(vinculo__id=vinculo.pk)
        if qs.exists():
            obj.professor = qs[0]
        else:
            professor = Professor()
            professor.vinculo = vinculo
            professor.save()
            obj.professor = professor
            Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)
        obj.save()


class EditarParticipanteTurmaMinicursoForm(forms.ModelFormPlus):
    INFO = 'O CPF do participante não pode ser alterado. Caso precise alterá-lo, exclua este participante e adicione-o novamente com o CPF correto.'
    email = forms.EmailField(label='E-mail', required=False)

    class Meta:
        model = PessoaFisica
        fields = ('nome',)

    def processar(self, *args, **kwargs):
        self.instance.nome_registro = self.cleaned_data['nome']
        self.instance.save()
        email = self.cleaned_data.get('email')
        if email:
            v = self.instance.get_vinculo()
            if v:
                v.email_pessoal = email
                v.save(update_fields=['email_pessoal'])


class AutenticarCertificadoMinicursoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Autenticar Certificado'
    METHOD = 'get'
    cpf = forms.BrCpfField(label='CPF')
    data_conclusao = forms.DateFieldPlus(label='Data de Conclusão')
    codigo_turma = forms.IntegerField(label='Código da Turma')

    def processar(self):
        aluno = Aluno.objects.filter(
            pessoa_fisica__cpf=self.cleaned_data['cpf'],
            situacao__codigo_academico=SituacaoMatricula.CONCLUIDO,
            participanteturmaminicurso__turma__data_fim__lte=self.cleaned_data['data_conclusao'],
            participanteturmaminicurso__turma__data_fim__gte=self.cleaned_data['data_conclusao'],
            participanteturmaminicurso__turma__pk=int(self.cleaned_data['codigo_turma']),
        ).first()
        if aluno:
            return aluno, aluno.participanteturmaminicurso_set.first().turma
        else:
            return None, None


class AdicionarParticipanteTurmaMinicursoForm(forms.FormPlus):
    cpf = forms.BrCpfField()
    nome = forms.CharFieldPlus()
    email = forms.EmailField()

    def __init__(self, turma_minicurso, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turma_minicurso = turma_minicurso

    def clean_cpf(self):
        qs = self.turma_minicurso.participanteturmaminicurso_set.filter(aluno__pessoa_fisica__cpf=self.cleaned_data.get('cpf'))
        if qs.exists():
            raise forms.ValidationError('Já existe um participante com o CPF informado.')
        return self.cleaned_data.get('cpf')

    @transaction.atomic
    def processar(self) -> None:
        pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(
            {'cpf': self.cleaned_data['cpf'], 'nome': self.cleaned_data['nome']}, Politica.PREENCHER
        )
        participante = self.turma_minicurso.adicionar_novo_aluno(pessoa_fisica)
        aluno = participante.aluno
        if aluno:
            v = aluno.get_vinculo()
            if v:
                v.email_pessoal = self.cleaned_data['email']
                v.save(update_fields=['email_pessoal'])


class VincularParticipanteSemTurmaMinicursoForm(forms.FormPlus):
    alunos = forms.MultipleModelChoiceFieldPlus(
        Aluno.locals.none(),
        label='Alunos',
        required=True,
        widget=forms.CheckboxSelectMultiplePlus(),
    )

    def __init__(self, *args, **kwargs):
        self.minicurso_id = kwargs.pop('minicurso_id')
        self.turma_minicurso_id = kwargs.pop('turma_minicurso_id')
        super().__init__(*args, **kwargs)
        self.fields['alunos'].queryset = (
            Aluno.locals.filter(curso_campus_id=self.minicurso_id, participanteturmaminicurso__isnull=True)
            .select_related('pessoa_fisica')
            .only('id', 'pk', 'matricula', 'pessoa_fisica__nome_registro', 'pessoa_fisica__nome_social', 'pessoa_fisica__nome')
        )

    @transaction.atomic
    def processar(self):
        for aluno in self.cleaned_data['alunos']:
            ParticipanteTurmaMinicurso.objects.create(aluno_id=aluno.id, turma_id=self.turma_minicurso_id)


class ImportarParticipantesTurmaMinicursoForm(forms.FormPlus):
    planilha = forms.FileFieldPlus(
        help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, contendo as seguintes colunas: CPF, Nome e E-mail.'
    )

    def __init__(self, turma_minicurso, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turma_minicurso = turma_minicurso
        self.participantes = []

    def clean(self):
        try:
            cpfs_importados = []
            if self.cleaned_data.get('planilha'):
                planilha = self.cleaned_data['planilha'].file
                df = pd.read_excel(planilha, header=None)
                for _index, row in df.iterrows():
                    cpf = mask_cpf(str(row.iloc[0]).strip())
                    if not cpf_valido(cpf):
                        raise ValidationError(f'O cpf {cpf} é inválido.')
                    nome = str(row.iloc[1]).strip()
                    email = str(row.iloc[2]).strip()
                    if not email_valido(email):
                        raise ValidationError(f'O e-mail {email} é inválido.')
                    qs = self.turma_minicurso.participanteturmaminicurso_set.filter(aluno__pessoa_fisica__cpf=cpf)
                    if not qs.exists() and cpf not in cpfs_importados:
                        cpfs_importados.append(cpf)
                        participante = {'cpf': cpf, 'nome': nome, 'email': email}
                        self.participantes.append(participante)
        except ValidationError:
            raise
        except Exception:
            sentry_sdk.capture_exception()
            raise ValidationError(
                'Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx, sem cabeçalho e se contém as seguintes colunas: CPF, Nome e E-mail.'
            )
        return self.cleaned_data

    def processar(self) -> None:
        for participante in self.participantes:
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': participante['cpf'], 'nome': participante['nome']}, Politica.PREENCHER)
            participante_turma = self.turma_minicurso.adicionar_novo_aluno(pessoa_fisica)
            if participante['email']:
                aluno = participante_turma.aluno
                if aluno:
                    v = aluno.get_vinculo()
                    if v:
                        v.email_pessoal = participante['email']
                        v.save(update_fields=['email_pessoal'])
