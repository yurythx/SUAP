import tempfile

from django.apps.registry import apps
from django.conf import settings

from comum.models import Ano
from djtools import forms
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from comum.utils import get_uo
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    CursoCampus,
    Diario,
    Diretoria,
    MatriculaPeriodo,
    MensagemResponsavel,
    Modalidade,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turma,
)
from rh.models import UnidadeOrganizacional


class MensagemResponsavelForm(FormWizardPlus):
    LAST_SUBMIT_LABEL = 'Enviar mensagem'
    METHOD = 'POST'
    assunto = forms.CharFieldPlus(width=500)
    anexo = forms.FileFieldPlus(
        required=False,
        help_text='Caso deseje adicionar mais de um anexo, compacte-os utilizando uma ferramenta de zip. Tamanho máximo de 2,5Mb.',
        max_file_size=2621440,
    )

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=False)
    periodo_letivo = forms.ChoiceField(choices=[['', '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=False)
    uo = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.campi().all(), label='Campus', required=False)
    diretoria = forms.ModelMultiplePopupChoiceField(Diretoria.objects.none(), label='Diretoria', required=False)
    modalidade = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidade', required=False)
    situacao_matricula = forms.ModelMultiplePopupChoiceField(SituacaoMatricula.objects, label='Situação do Aluno', required=False)
    situacao_matricula_periodo = forms.ModelMultiplePopupChoiceField(
        SituacaoMatriculaPeriodo.objects, label='Situação da Matrícula Período', required=False
    )
    curso_campus = forms.MultipleModelChoiceFieldPlus(
        CursoCampus.objects.none(),
        label='Curso',
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=CursoCampus.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'diretoria__setor__uo__in'),
                ('diretoria', 'diretoria__in'),
                ('modalidade', 'modalidade_id__in'),
            ],
        ),
    )

    turma = forms.MultipleModelChoiceField(
        Turma.objects.none(),
        label='Turmas',
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'curso_campus__diretoria__setor__uo__in'),
                ('diretoria', 'curso_campus__diretoria__in'),
                ('modalidade', 'curso_campus__modalidade_id__in'),
                ('ano_letivo', 'ano_letivo__pk'),
                ('periodo_letivo', 'periodo_letivo'),
                ('curso_campus', 'curso_campus__in'),
            ],
        ),
    )

    diario = forms.MultipleModelChoiceFieldPlus(
        Diario.objects.none(),
        required=False,
        label='Diários',
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário.',
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Diario.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'turma__curso_campus__diretoria__setor__uo__in'),
                ('diretoria', 'turma__curso_campus__diretoria__in'),
                ('modalidade', 'turma__curso_campus__modalidade_id__in'),
                ('curso_campus', 'turma__curso_campus__in'),
                ('ano_letivo', 'ano_letivo__pk'),
                ('periodo_letivo', 'periodo_letivo'),
                ('turma', 'turma__in'),
            ],
        ),
    )

    aluno = forms.MultipleModelChoiceFieldPlus(
        queryset=Aluno.objects.none(),
        required=False,
        label='Alunos',
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Aluno.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'curso_campus__diretoria__setor__uo__in'),
                ('diretoria', 'curso_campus__diretoria__in'),
                ('modalidade', 'curso_campus__modalidade__in'),
                ('curso_campus', 'curso_campus__in'),
                ('turma', 'matriculaperiodo__matriculadiario__diario__turma__pk__in'),
                ('situacao_matricula', 'situacao__id__in'),
                ('ano_letivo', 'ano_letivo__pk'),
                ('periodo_letivo', 'periodo_letivo'),
            ],
        ),
    )

    conteudo = TinyMCEFormField(label='Conteúdo', required=True)

    alunos = forms.MultipleModelChoiceFieldPlus(
        Aluno.objects,
        required=True,
        label='',
        widget=RenderableSelectMultiple(
            'widgets/alunos_widget.html',
            attrs={'checked': True},
        ),
    )

    pode_interagir = forms.BooleanField(
        label='Pode Interagir?',
        required=False,
        help_text='Marque essa opção caso o responsável possa interagir enviando um comentário ou questionamento.',
    )
    confirmacao = forms.BooleanField(label='Confirmação', required=True, help_text='Confirmo o envio da mensagem.')
    senha = forms.PasswordField()

    step_1 = (
        [
            (
                'Filtros',
                {
                    'fields': (
                        'uo',
                        'diretoria',
                        'modalidade',
                        'programa',
                        'situacao_matricula',
                        'ano_letivo',
                        'periodo_letivo',
                        'situacao_matricula_periodo',
                        'curso_campus',
                        'turma',
                        'diario',
                        'aluno',
                    )
                },
            )
        ],
    )

    step_2 = (
        [
            ('Destinatários', {'fields': ('alunos',)}),
        ],
    )

    step_3 = (
        [
            ('Mensagem', {'fields': ('assunto', 'conteudo', 'anexo')}),
            ('Interação do usuário', {'fields': ('pode_interagir',)}),
            (
                'Confirmação de envio',
                {
                    'fields': (
                        'senha',
                        'confirmacao',
                    )
                },
            ),
        ],
    )

    steps = step_1 + step_2 + step_3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_group_cached(['Administrador Acadêmico']):
            vinculo = self.request.user.get_vinculo()
            uo = get_uo(self.request.user)
            self.fields['uo'].queryset = self.fields['uo'].queryset.model.objects.filter(pk=uo.id)
            if self.request.user.has_group_cached(['Diretor Acadêmico', 'Membro ETEP']):
                self.fields['diretoria'].queryset = Diretoria.objects.filter(setor__uo=uo)
                self.fields['curso_campus'].queryset = CursoCampus.objects.filter(ativo=True, diretoria__setor__uo=uo)
                self.fields['turma'].queryset = Turma.objects.filter(curso_campus__diretoria__setor__uo=uo)
                self.fields['diario'].queryset = Diario.objects.filter(turma__curso_campus__diretoria__setor__uo=uo)
                self.fields['aluno'].queryset = Aluno.objects.filter(curso_campus__diretoria__setor__uo=uo)
            if self.request.user.has_group_cached(['Coordenador de Curso']):
                pks = (
                    (CursoCampus.objects.filter(coordenador_id=vinculo.id) | CursoCampus.objects.filter(coordenador_2_id=vinculo.id))
                    .values_list('pk', flat=True)
                    .distinct()
                )
                self.fields['curso_campus'].queryset = CursoCampus.objects.filter(pk__in=pks)
                self.fields['turma'].queryset = Turma.objects.filter(curso_campus__in=pks)
                self.fields['diario'].queryset = Diario.objects.filter(turma__curso_campus__in=pks)
                self.fields['aluno'].queryset = Aluno.objects.filter(curso_campus__in=pks)

    def first_step(self):
        if 'ae' in settings.INSTALLED_APPS:
            ProgramaSocial = apps.get_model('ae', 'Programa')
            self.fields['programa'] = forms.ModelMultiplePopupChoiceField(ProgramaSocial.objects, label='Participantes do Programa', required=False)
        self.fields['aluno'].queryset = Aluno.objects.filter(vinculos__user__isnull=False)

        if not self.request.GET:
            self.fields['situacao_matricula'].initial = (SituacaoMatricula.MATRICULADO,)
            self.fields['situacao_matricula_periodo'].initial = (SituacaoMatriculaPeriodo.MATRICULADO,)
            try:
                if not self.request.user.get_vinculo().setor.uo.eh_reitoria:
                    self.fields['uo'].queryset = UnidadeOrganizacional.objects.campi().filter(id=self.request.user.get_vinculo().setor.uo_id)
                    self.fields['uo'].initial = (self.request.user.get_vinculo().setor.uo_id,)
            except Exception:
                pass

    def next_step(self):
        ano_letivo = self.get_entered_data('ano_letivo')
        periodo_letivo = self.get_entered_data('periodo_letivo') or 0
        uo = self.get_entered_data('uo', is_list=True)
        diretoria = self.get_entered_data('diretoria', is_list=True)
        programa = self.get_entered_data('programa', is_list=True)
        modalidade = self.get_entered_data('modalidade', is_list=True)
        situacao_matricula = self.get_entered_data('situacao_matricula', is_list=True)
        situacao_matricula_periodo = self.get_entered_data('situacao_matricula_periodo', is_list=True)
        curso_campus = self.get_entered_data('curso_campus', is_list=True)
        matriculas = self.get_entered_data('aluno', is_list=True)

        if 'conteudo' in self.fields:
            user = self.request.user
            setor = user.get_vinculo().setor or ''
            if setor:
                setor = f'{setor}/{setor.superior}'
            assinatura = f'{user.get_profile().nome} ({user.username}) <br /> {setor}'
            self.fields['conteudo'].initial = f'<br />Atenciosamente,<br /> {assinatura}'

        if 'curso_campus' in self.fields:
            self.fields['curso_campus'].queryset = CursoCampus.objects.filter(ativo=True)

        if 'alunos' in self.fields:
            qs_mp = MatriculaPeriodo.objects.all()

            if ano_letivo:
                qs_mp = qs_mp.filter(ano_letivo_id=ano_letivo.id)

            if int(periodo_letivo):
                qs_mp = qs_mp.filter(periodo_letivo=periodo_letivo)

            if uo:
                qs_mp = qs_mp.filter(aluno__curso_campus__diretoria__setor__uo__in=uo)

            if diretoria:
                qs_mp = qs_mp.filter(aluno__curso_campus__diretoria__in=diretoria)

            if programa and 'ae' in settings.INSTALLED_APPS:
                ProgramaSocial = apps.get_model('ae', 'Programa')
                ids_alunos = []
                for item in ProgramaSocial.objects.filter(id__in=programa):
                    ids_alunos += item.get_participacoes_abertas().values_list('aluno', flat=True)
                qs_mp = qs_mp.filter(aluno_id__in=ids_alunos)

            if modalidade:
                qs_mp = qs_mp.filter(aluno__curso_campus__modalidade_id__in=modalidade)

            if situacao_matricula:
                qs_mp = qs_mp.filter(aluno__situacao_id__in=situacao_matricula)

            if situacao_matricula_periodo:
                qs_mp = qs_mp.filter(situacao_id__in=situacao_matricula_periodo)

            if curso_campus:
                ids_cursos = [curso.id for curso in curso_campus]
                qs_mp = qs_mp.filter(aluno__curso_campus_id__in=ids_cursos)

            if matriculas:
                ids_alunos = [matricula.id for matricula in matriculas]
                qs_mp = qs_mp.filter(aluno_id__in=ids_alunos)

            qs_a = Aluno.objects.filter(id__in=qs_mp.order_by('aluno_id').values_list('aluno_id', flat=True).distinct())

            self.qs = qs_a
            self.fields['alunos'].queryset = qs_a
            qtd_alunos_qs = qs_a.count()
            if qtd_alunos_qs > 100:
                if 'alunos' in self.fields:
                    # esconde listagem de alunos quando tem mais de 100 destinatários
                    msg = f'Serão notificados os responsáveis de {qtd_alunos_qs} alunos.'
                    self.fields['alunos'].widget = forms.AlertWidget(msg)
                    self.fields['alunos'].required = False
                    if self.step == 1 and self.data:
                        self.ALERT = f'A mensagem será enviada para os responsáveis de {qtd_alunos_qs} alunos. Caso deseje visualizar cada um deles, refine a sua pesquisa com mais informações de modo que o total de destinatários não ultrapasse 100 alunos.'
                    if self.step > 1:
                        self.ALERT = msg
                    if 'senha' in self.fields:
                        self.fields['senha'].help_text = f'Confirmo que desejo enviar a mensagem para os responsáveis de {qtd_alunos_qs} alunos.'

            else:
                alunos_selecionados = self.get_entered_data('alunos', is_list=True)
                if alunos_selecionados and len(alunos_selecionados) <= 100:
                    # retira confirmação com senha quando tem 100 ou menos destinatários
                    if 'senha' in self.fields:
                        del self.fields['senha']
                    if self.step > 1:
                        self.INFO = f'A mensagem será enviada para os responsáveis de {len(alunos_selecionados)} alunos.'

    def clean(self):
        uo = self.get_entered_data('uo', is_list=True)
        programa = self.get_entered_data('programa', is_list=True)
        modalidade = self.get_entered_data('modalidade', is_list=True)
        situacao_matricula = self.get_entered_data('situacao_matricula', is_list=True)
        situacao_matricula_periodo = self.get_entered_data('situacao_matricula_periodo', is_list=True)
        curso_campus = self.get_entered_data('curso_campus', is_list=True)
        turma = self.get_entered_data('turma', is_list=True)
        diario = self.get_entered_data('diario', is_list=True)
        aluno = self.get_entered_data('aluno', is_list=True)
        if not (uo or programa or modalidade or situacao_matricula or situacao_matricula_periodo or curso_campus or turma or diario or aluno):
            raise forms.ValidationError('Selecione, no mínimo, um filtro para os destinatários da mensagem.')
        return self.cleaned_data

    def processar(self, request):
        alunos = self.get_entered_data('alunos', is_list=True)
        if alunos and alunos.exists():
            self.qs = alunos
        total = self.qs.count()
        if total:
            anexo = self.cleaned_data.get('anexo')
            filename = None
            if anexo:
                extensao = '.' + anexo.name.split('.')[-1]
                temp = tempfile.NamedTemporaryFile(suffix=extensao, delete=False)
                filename = temp.name
                temp.writelines(anexo.chunks())
                temp.close()

            mensagem = MensagemResponsavel()
            mensagem.remetente = request.user
            mensagem.assunto = self.cleaned_data['assunto']
            mensagem.conteudo = self.cleaned_data['conteudo']
            mensagem.pode_interagir = self.cleaned_data['pode_interagir']
            mensagem.anexo = anexo
            mensagem.save()
            mensagem.destinatarios.set(self.qs)
            mensagem.save()

            return mensagem.enviar_emails(self.qs, filename)

        return total


class ResponderMensagemForm(forms.FormPlus):
    resposta = forms.CharField(label='Resposta', widget=forms.Textarea())
