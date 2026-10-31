from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.safestring import mark_safe

from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms.fields import BrCpfField
from djtools.forms.widgets import (
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from edu.models import (
    Aluno,
    ColacaoGrau,
    CursoCampus,
    Diretoria,
    Evento,
    MatriculaPeriodo,
    Modalidade,
    ParticipacaoColacaoGrau,
    ParticipanteEvento,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turma,
)
from rh.models import PessoaExterna, UnidadeOrganizacional


class AdicionarAlunosColacaoGrauForm(FormWizardPlus):
    METHOD = 'GET'

    ano_letivo_aluno = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=True)
    periodo_letivo_aluno = forms.ChoiceField(label='Período Letivo', choices=[[None, '----'], *Aluno.PERIODO_LETIVO_CHOICES], required=True)
    cursos_campus = forms.MultipleModelChoiceFieldPlus(CursoCampus.locals, label='Curso', required=False)
    turma = forms.ModelChoiceFieldPlus(Turma.objects, required=False, label='Turma')
    aluno = forms.ModelChoiceFieldPlus(Aluno.locals, label='Aluno', required=False)

    alunos = forms.MultipleModelChoiceField(
        Aluno.locals.none(), label='', widget=RenderableSelectMultiple('widgets/alunos_widget.html'), required=True
    )

    steps = (
        [('Ano/Período Letivo', {'fields': ('ano_letivo_aluno', 'periodo_letivo_aluno')})],
        [('Filtros', {'fields': ('cursos_campus', 'turma', 'aluno')})],
        [('Alunos', {'fields': ('alunos',)})],
    )

    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.colacao_grau = kwargs.pop('colacao_grau')
        self.diretoria_id = self.colacao_grau.diretoria_id
        super().__init__(*args, **kwargs)

    def next_step(self):
        ano_letivo_aluno = self.get_entered_data('ano_letivo_aluno')
        periodo_letivo_aluno = self.get_entered_data('periodo_letivo_aluno')
        cursos_campus = self.request.GET.getlist('cursos_campus')
        turma = self.get_entered_data('turma')
        aluno = self.get_entered_data('aluno')

        qs_alunos = (
            Aluno.objects.filter(
                curso_campus__ativo=True,
                curso_campus__exige_colacao_grau=True,
                situacao__in=[SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL],
                matriz__isnull=False,
                participacaocolacaograu__isnull=True,
                curso_campus__diretoria_id=self.diretoria_id,
                pendencia_colacao_grau=True,
            )
            .exclude(pendencia_tcc=True)
            .exclude(pendencia_ch_atividade_complementar=True)
            .exclude(pendencia_ch_tcc=True, pendencia_ch_pratica_profissional=True)
            .exclude(pendencia_ch_seminario=True)
            .exclude(pendencia_ch_eletiva=True)
            .exclude(pendencia_ch_optativa=True)
            .exclude(pendencia_ch_obrigatoria=True)
            .exclude(pendencia_pratica_profissional=True)
            .exclude(curso_campus__modalidade_id__in=[Modalidade.FIC, Modalidade.FIC_MENOS])
        )
        if 'cursos_campus' in self.fields:
            self.fields['cursos_campus'].queryset = CursoCampus.locals.filter(ativo=True, exige_colacao_grau=True, diretoria_id=self.diretoria_id)
            self.fields['turma'].queryset = Turma.locals.filter(
                curso_campus__ativo=True,
                curso_campus__exige_colacao_grau=True,
                matriculaperiodo__isnull=False,
                curso_campus__diretoria_id=self.diretoria_id,
            ).distinct()
            self.fields['aluno'].queryset = qs_alunos
        if (cursos_campus or turma or aluno) and 'alunos' in self.fields:
            if aluno:
                qs_alunos = qs_alunos.filter(id=aluno.id)
            else:
                # se não filtrar por aluno, remove alunos com pendência de ENADE (clean de aluno faz tratamento especial para pendência de ENADE, então só aplica esse filtro se não tiver filtrado por aluno)
                qs_alunos = qs_alunos.exclude(pendencia_enade=True)
                if cursos_campus:
                    qs_alunos = qs_alunos.filter(curso_campus__in=cursos_campus)
                if turma:
                    qs_alunos = qs_alunos.filter(matriculaperiodo__in=turma.get_alunos_matriculados())
            if ano_letivo_aluno:
                qs_alunos = qs_alunos.filter(matriculaperiodo__ano_letivo=ano_letivo_aluno)
            if periodo_letivo_aluno:
                qs_alunos = qs_alunos.filter(matriculaperiodo__periodo_letivo=periodo_letivo_aluno)
                qs_mps = MatriculaPeriodo.objects.filter(
                    aluno__in=qs_alunos.values('id'),
                    ano_letivo__ano__lte=ano_letivo_aluno.ano,
                    situacao_id__in=[SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.EM_ABERTO],
                )
                if int(periodo_letivo_aluno) == 1:
                    qs_mps = qs_mps.exclude(ano_letivo__ano=ano_letivo_aluno.ano, periodo_letivo=2)
                ids_alunos_matriculas_abertas = set(qs_mps.values_list('aluno_id', flat=True))
                qs_alunos = qs_alunos.exclude(id__in=ids_alunos_matriculas_abertas)

            self.fields['alunos'].queryset = qs_alunos.distinct()

    def clean(self):
        cursos_campus = self.cleaned_data.get('cursos_campus')
        turma = self.cleaned_data.get('turma')
        aluno = self.cleaned_data.get('aluno')
        if 'cursos_campus' in self.fields and not cursos_campus and not turma and not aluno:
            raise forms.ValidationError('Escolha pelo menos um curso, ou turma ou aluno.')
        return self.cleaned_data

    def clean_aluno(self):
        aluno = self.cleaned_data.get('aluno')
        if aluno:
            ano_letivo_aluno = self.get_entered_data('ano_letivo_aluno')
            periodo_letivo_aluno = self.get_entered_data('periodo_letivo_aluno')

            if not aluno.pode_realizar_colacao_grau(ano_letivo_aluno, periodo_letivo_aluno, self.colacao_grau.data_colacao):
                raise forms.ValidationError(
                    mark_safe(
                        'Aluno escolhido ainda não pode colar grau. <a href="/edu/aluno/{}/?tab=requisitos">Reveja os requisitos</a>'.format(
                            self.cleaned_data['aluno'].matricula
                        )
                    )
                )
        return aluno


class ColacaoGrauForm(forms.ModelForm):
    diretoria = forms.ModelChoiceField(queryset=Diretoria.objects.none())

    class Meta:
        model = ColacaoGrau
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals


class DeferirColacaoGrauForm(forms.FormPlus):
    laureados = forms.MultipleModelChoiceFieldPlus(ParticipacaoColacaoGrau.objects, label='Laureados', required=False)

    def __init__(self, colacao_grau, *args, **kwargs):
        self.colacao_grau = colacao_grau
        super().__init__(*args, **kwargs)
        self.fields['laureados'].queryset = colacao_grau.participacaocolacaograu_set.all()
        self.fields['laureados'].initial = list(colacao_grau.participacaocolacaograu_set.filter(laureado=True).values_list('pk', flat=True))

    def processar(self):
        self.colacao_grau.deferir(self.cleaned_data['laureados'])


class EventoForm(forms.ModelFormPlus):
    modelo_certificado_participacao = forms.FileFieldPlus(
        filetypes=['docx'],
        label='Modelo do Certificado de Participação',
        check_mimetype=False,
        help_text='O arquivo de modelo deve ser uma arquivo .docx contendo as marcações #PARTICIPANTE#, #CPF#, #CAMPUS#, #CIDADE#, #UF#, #DATA#, #CODIGOVERIFICADOR#.',
    )
    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus')

    class Meta:
        model = Evento
        exclude = ('participantes', 'modelo_certificado_palestrante', 'modelo_certificado_convidado')


class ModeloCertificadoEventoForm(forms.FormPlus):
    modelo = forms.FileFieldPlus(
        filetypes=['docx'],
        label='Modelo do Certificado',
        check_mimetype=False,
        required=False,
        help_text='O arquivo de modelo deve ser uma arquivo .docx contendo as marcações #PARTICIPANTE#, #CPF#, #CAMPUS#, #CIDADE#, #UF#, #DATA#, #CODIGOVERIFICADOR#.',
    )

    def __init__(self, evento, *args, **kwargs):
        self.tipo = kwargs.pop('tipo', ParticipanteEvento.PARTICIPANTE)
        super().__init__(*args, **kwargs)
        self.evento = evento
        if self.tipo == ParticipanteEvento.PARTICIPANTE:
            self.initial['modelo'] = self.evento.modelo_certificado_participacao
            self.fields['modelo'].required = True
        elif self.tipo == ParticipanteEvento.PALESTRANTE:
            self.initial['modelo'] = self.evento.modelo_certificado_palestrante
        elif self.tipo == ParticipanteEvento.CONVIDADO:
            self.initial['modelo'] = self.evento.modelo_certificado_convidado

    def clean_modelo(self):
        if self.cleaned_data.get('modelo') is False:
            return None
        return self.cleaned_data.get('modelo')

    def processar(self):
        if self.tipo == ParticipanteEvento.PARTICIPANTE:
            self.evento.modelo_certificado_participacao = self.cleaned_data['modelo']
        elif self.tipo == ParticipanteEvento.PALESTRANTE:
            self.evento.modelo_certificado_palestrante = self.cleaned_data['modelo']
        elif self.tipo == ParticipanteEvento.CONVIDADO:
            self.evento.modelo_certificado_convidado = self.cleaned_data['modelo']
        self.evento.save()


class AdicionarParticipanteEventoForm(forms.FormPlus):
    cpf = forms.BrCpfField()
    nome = forms.CharFieldPlus()
    email = forms.EmailField()

    def __init__(self, evento, *args, **kwargs):
        self.tipo = kwargs.pop('tipo', ParticipanteEvento.PARTICIPANTE)
        super().__init__(*args, **kwargs)
        self.evento = evento

    def clean_cpf(self):
        qs = self.evento.participanteevento_set.filter(
            evento=self.evento, participante__pessoa__pessoafisica__cpf=self.cleaned_data.get('cpf'), tipo_participacao=self.tipo
        )
        if qs.exists():
            raise forms.ValidationError(f'Já existe um {self.tipo} com o CPF informado.')
        return self.cleaned_data.get('cpf')

    @transaction.atomic
    def processar(self):
        vinculo = (
            Vinculo.objects.filter(pessoa__pessoafisica__cpf=self.cleaned_data['cpf'])
            .order_by('-ativo', '-pessoa__pessoafisica__eh_servidor', '-pessoa__pessoafisica__eh_aluno', '-pessoa__pessoafisica__eh_prestador')
            .first()
        )
        if not vinculo:
            pessoa_externa = PessoaExterna.objects.filter(cpf=self.cleaned_data['cpf']).first()
            if not pessoa_externa:
                pessoa_externa = PessoaExterna()
            pessoa_externa.cpf = self.cleaned_data['cpf']
            pessoa_externa.nome_registro = self.cleaned_data['nome']
            pessoa_externa.email = self.cleaned_data['email']
            pessoa_externa.save()
            vinculo = pessoa_externa.get_vinculo()

        participante_evento = ParticipanteEvento()
        participante_evento.participante = vinculo
        participante_evento.evento = self.evento
        participante_evento.tipo_participacao = self.tipo
        participante_evento.save()
        self.evento.participanteevento_set.add(participante_evento)
        self.evento.save()


class EditarParticipanteEventoForm(forms.ModelFormPlus):
    email = forms.EmailField()
    cpf = forms.CharFieldPlus(label='CPF', required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    nome_registro = forms.CharFieldPlus(label='Nome')

    class Meta:
        model = PessoaExterna
        fields = ('cpf', 'nome_registro', 'email')


class AlterarVinculoParticipanteEventoForm(forms.ModelFormPlus):
    class Meta:
        model = ParticipanteEvento
        fields = ('participante',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['participante'].queryset = (
            Vinculo.objects.filter(pessoa__pessoafisica__cpf=self.instance.participante.pessoa.pessoafisica.cpf)
            .exclude(pk=self.instance.participante.pk)
            .order_by('user__username')
        )
        self.initial['participante'] = self.instance.participante


class ImportarParticipantesEventoForm(forms.FormPlus):
    planilha = forms.FileFieldPlus(
        help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, contendo as seguintes colunas: CPF, Nome e E-mail.'
    )

    def __init__(self, evento, *args, **kwargs):
        self.tipo = kwargs.pop('tipo', ParticipanteEvento.PARTICIPANTE)
        super().__init__(*args, **kwargs)
        self.evento = evento
        self.participantes = []

    def clean(self):
        """Valida e importa participantes de evento a partir de planilha.

        Returns:
            dict: dados limpos do formulário.

        Raises:
            ValidationError: se a planilha estiver em formato inválido ou
                contiver CPFs inválidos.
        """
        import pandas as pd

        arquivo = self.cleaned_data.get('planilha')
        if arquivo:
            try:
                planilha = arquivo.file
                df = pd.read_excel(planilha, header=None)
                cpfs_invalidos = []
                for _index, row in df.iterrows():
                    nome = str(row.iloc[1])
                    try:
                        cpf = str(row.iloc[0])
                        cpf_field = BrCpfField()
                        cpf = cpf_field.clean(cpf)
                    except ValidationError:
                        cpfs_invalidos.append(f'{nome}({cpf})')
                        continue

                    email = str(row.iloc[2])
                    participante = {'cpf': cpf, 'nome': nome, 'email': email}

                    qs = self.evento.participanteevento_set.filter(evento=self.evento, participante__pessoa__pessoafisica__cpf=cpf)
                    if not qs.exists():
                        self.participantes.append(participante)
            except Exception:
                raise ValidationError(
                    'Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx, sem cabeçalho e se contém as seguintes colunas: CPF, Nome e E-mail.'
                )
            if cpfs_invalidos:
                raise ValidationError(
                    'A planilha contém os participantes com CPF inválido: {}. Faça a correção antes de importar a planilha.'.format(
                        ', '.join(cpfs_invalidos)
                    )
                )

        return self.cleaned_data

    @transaction.atomic
    def processar(self):
        for _participante in self.participantes:
            vinculo = (
                Vinculo.objects.filter(pessoa__pessoafisica__cpf=self.cleaned_data['cpf'])
                .order_by('-ativo', '-pessoa__pessoafisica__eh_servidor', '-pessoa__pessoafisica__eh_aluno', '-pessoa__pessoafisica__eh_prestador')
                .first()
            )
            if not vinculo:
                pessoa_externa = PessoaExterna.objects.filter(cpf=self.cleaned_data['cpf']).first()
                if not pessoa_externa:
                    pessoa_externa = PessoaExterna()
                pessoa_externa.cpf = self.cleaned_data['cpf']
                pessoa_externa.nome_registro = self.cleaned_data['nome']
                pessoa_externa.email = self.cleaned_data['email']
                pessoa_externa.save()
                vinculo = pessoa_externa.get_vinculo()

            participante_evento = ParticipanteEvento()
            participante_evento.participante = vinculo
            participante_evento.evento = self.evento
            participante_evento.tipo_participacao = self.tipo
            participante_evento.save()
            self.evento.participanteevento_set.add(participante_evento)
            self.evento.save()
