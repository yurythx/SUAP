import tempfile
import threading

from django.apps.registry import apps
from django.conf import settings

from comum.models import Ano, User, UsuarioGrupoSetor
from djtools import forms
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.utils import send_mail
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    ConfiguracaoPedidoMatricula,
    ConvocacaoENADE,
    CursoCampus,
    Diario,
    Diretoria,
    MatriculaDiario,
    MatriculaPeriodo,
    Mensagem,
    Modalidade,
    PeriodoLetivoAtual,
    Polo,
    Professor,
    RegistroConvocacaoENADE,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turma,
)
from rh.models import UnidadeOrganizacional


class MensagemComplementarForm(forms.FormPlus):
    LAST_SUBMIT_LABEL = 'Enviar Mensagem Complementar'
    METHOD = 'POST'
    assunto = forms.CharFieldPlus(width=500)
    conteudo = forms.CharField(widget=forms.Textarea(), label='Conteúdo', required=True)
    anexo = forms.FileFieldPlus(
        required=False,
        help_text='Caso deseje adicionar mais de um anexo, compacte-os utilizando uma ferramenta de zip. Tamanho máximo de 2,5Mb.',
        max_file_size=2621440,
    )

    def __init__(self, mensagem_original, *args, **kwargs):
        self.mensagem_original = mensagem_original
        super().__init__(*args, **kwargs)

    def processar(self):
        anexo = self.cleaned_data['anexo']
        filename = None
        if anexo:
            extensao = '.' + anexo.name.split('.')[-1]
            temp = tempfile.NamedTemporaryFile(suffix=extensao, delete=False)
            filename = temp.name
            temp.writelines(anexo.chunks())
            temp.close()

        mensagem = Mensagem()
        mensagem.remetente = self.mensagem_original.remetente
        mensagem.assunto = self.cleaned_data['assunto']
        mensagem.conteudo = self.cleaned_data['conteudo']
        mensagem.anexo = anexo
        mensagem.via_suap = self.mensagem_original.via_suap
        mensagem.via_email = self.mensagem_original.via_email
        mensagem.save()
        emails = []
        for destinatario in self.mensagem_original.destinatarios.all():
            emails.append(destinatario.email)
            mensagem.destinatarios.add(destinatario)
        mensagem.save()
        if mensagem.via_email:

            def do():
                files = []
                if filename:
                    files.append(filename)
                send_mail(mensagem.assunto, mensagem.conteudo, settings.DEFAULT_FROM_EMAIL, emails, fail_silently=True, files=files)

            thread = threading.Thread(target=do)
            thread.start()
        return mensagem


class MensagemForm(FormWizardPlus):
    LAST_SUBMIT_LABEL = 'Enviar mensagem'
    METHOD = 'POST'
    assunto = forms.CharFieldPlus(width=500)
    anexo = forms.FileFieldPlus(
        required=False,
        help_text='Caso deseje adicionar mais de um anexo, compacte-os utilizando uma ferramenta de zip. Tamanho máximo de 2,5Mb.',
        max_file_size=2621440,
    )

    forma_envio = forms.ChoiceField(
        label='Forma de Envio',
        required=True,
        help_text='Se forma de envio via email for marcada será enviada uma cópia do email para você.',
        choices=[
            [
                1,
                'Via Suap',
            ],
            [2, 'Via Email'],
            [3, 'Ambos'],
        ],
    )
    enviar_coordenador = forms.BooleanField(
        label='Copiar Coordenador',
        required=False,
        help_text='Será enviada uma cópia do email para cada coordenador de curso dos alunos selecionados.',
    )
    enviar_diretor = forms.BooleanField(
        label='Copiar Diretor Acadêmico',
        required=False,
        help_text='Será enviada uma cópia do email para o diretor acadêmico dos alunos selecionados.',
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
        CursoCampus.objects,
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

    turmas_atuais = forms.MultipleModelChoiceFieldPlus(
        Turma.objects.none(), label='Turmas Atuais', required=False, widget=forms.CheckboxSelectMultiplePlus()
    )

    turma = forms.MultipleModelChoiceField(
        Turma.objects,
        label='Outras Turmas',
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'curso_campus__diretoria__setor__uo__in'),
                ('diretoria', 'curso_campus__diretoria__in'),
                ('modalidade', 'curso_campus__modalidade_id__in'),
                ('ano_letivo', 'ano_letivo__pk'),
                ('perido_letivo', 'periodo_letivo'),
                ('curso_campus', 'curso_campus__in'),
            ],
        ),
    )

    diarios_atuais = forms.MultipleModelChoiceField(
        Diario.objects.none(),
        required=False,
        label='Diários Atuais',
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário.',
        widget=forms.CheckboxSelectMultiplePlus(),
    )

    diario = forms.MultipleModelChoiceFieldPlus(
        Diario.objects,
        required=False,
        label='Outros Diários',
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
        queryset=Aluno.objects,
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Aluno.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'curso_campus__diretoria__setor__uo__in'),
                ('diretoria', 'curso_campus__diretoria__in'),
                ('curso_campus', 'curso_campus__in'),
                ('turma', 'matriculaperiodo__matriculadiario__diario__turma__pk__in'),
                ('situacao_matricula', 'situacao__id__in'),
                ('ano_letivo', 'ano_letivo__pk'),
                ('periodo_letivo', 'periodo_letivo'),
            ],
        ),
    )

    polo = forms.MultipleModelChoiceFieldPlus(Polo.objects, required=False, label='Polo EAD')
    configuracoes_pedido_matricula = forms.MultipleModelChoiceFieldPlus(
        queryset=ConfiguracaoPedidoMatricula.objects,
        label='Renovação de Matrícula',
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=ConfiguracaoPedidoMatricula.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'diretorias__setor__uo__in'),
                ('ano_letivo', 'ano_letivo'),
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

    enade = forms.ModelChoiceFieldPlus(ConvocacaoENADE.objects.none(), label='ENADE', required=False)
    tipo_convocacao = forms.ChoiceField(
        label='Tipo de convocação',
        required=False,
        choices=[['', '----'], *RegistroConvocacaoENADE.TIPO_CONVOCACAO_CHOICES],
    )
    periodo = forms.IntegerFieldPlus(
        label='Período de convocação',
        required=False,
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
                        'configuracoes_pedido_matricula',
                        'turmas_atuais',
                        'diarios_atuais',
                        'turma',
                        'diario',
                        'aluno',
                        'polo',
                        'enade',
                        'tipo_convocacao',
                        'periodo',
                    )
                },
            )
        ],
    )

    step_2 = (
        [
            ('Forma de envio', {'fields': ('forma_envio', 'enviar_coordenador', 'enviar_diretor')}),
            ('Destinatários', {'fields': ('alunos',)}),
        ],
    )

    step_3 = (
        [
            ('Mensagem', {'fields': ('assunto', 'conteudo', 'anexo')}),
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

    def first_step(self):
        if 'ae' in settings.INSTALLED_APPS:
            ProgramaSocial = apps.get_model('ae', 'Programa')
            self.fields['programa'] = forms.ModelMultiplePopupChoiceField(ProgramaSocial.objects, label='Participantes do Programa', required=False)
        self.fields['aluno'].queryset = Aluno.objects.filter(vinculos__user__isnull=False)
        self.fields['curso_campus'].queryset = CursoCampus.objects.filter(ativo=True)
        self.fields['diretoria'].queryset = Diretoria.locals.all()
        self.fields['polo'].queryset = Polo.locals.all()
        self.fields['diario'].queryset = Diario.locals.all()
        self.fields['enade'].queryset = ConvocacaoENADE.objects.all()

        periodo_letivo_atual = PeriodoLetivoAtual.get_instance(self.request)
        professor = Professor.objects.filter(vinculo=self.request.user.get_vinculo()).first()
        if periodo_letivo_atual and professor:
            qs_diarios_atuais = Diario.objects.filter(ano_letivo__ano=periodo_letivo_atual.ano, professordiario__professor=professor)
            qs_diarios_atuais = qs_diarios_atuais.filter(
                turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL
            ) | qs_diarios_atuais.exclude(turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL).filter(
                periodo_letivo=periodo_letivo_atual.periodo
            )
            self.fields['diarios_atuais'].queryset = qs_diarios_atuais
            qs_turmas_atuais = Turma.objects.filter(pk__in=qs_diarios_atuais.values_list('turma', flat=True).distinct())
            self.fields['turmas_atuais'].queryset = qs_turmas_atuais

        if not self.request.GET:
            self.fields['situacao_matricula'].initial = (SituacaoMatricula.MATRICULADO,)
            self.fields['situacao_matricula_periodo'].initial = (SituacaoMatriculaPeriodo.MATRICULADO,)
            try:
                if not self.request.user.get_vinculo().setor.uo.eh_reitoria:
                    self.fields['uo'].queryset = UnidadeOrganizacional.objects.campi().filter(id=self.request.user.get_vinculo().setor.uo_id)
                    self.fields['uo'].initial = (self.request.user.get_vinculo().setor.uo_id,)
            except Exception:
                pass

        # não visivel no formulário padrão. Utilizado apenas para o envio direto da convaocação ENADE.
        self.fields['enade'].widget = forms.HiddenInput()
        self.fields['tipo_convocacao'].widget = forms.HiddenInput()
        self.fields['periodo'].widget = forms.HiddenInput()

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
        turmas_atuais = self.get_entered_data('turmas_atuais', is_list=True) or []
        configuracoes_pedido_matricula = self.get_entered_data('configuracoes_pedido_matricula', is_list=True)
        diarios_atuais = self.get_entered_data('diarios_atuais', is_list=True) or []
        turmas = self.get_entered_data('turma', is_list=True) or []
        diarios = self.get_entered_data('diario', is_list=True) or []
        polos = self.get_entered_data('polo', is_list=True)
        matriculas = self.get_entered_data('aluno', is_list=True)
        enade = self.get_entered_data('enade')
        tipo_convocacao = self.get_entered_data('tipo_convocacao')
        periodo = self.get_entered_data('periodo')

        # esconde os campos que não são necessários para o envio de mensagem ENADE
        if self.request.GET.get('enade'):
            for field in self.step_1[0][0][1]['fields']:
                if field != 'curso_campus':
                    self.fields[field].widget = forms.HiddenInput()
                    self.fields[field].required = False

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

            if configuracoes_pedido_matricula:
                pks = []
                for configuracao_pedido_matricula in configuracoes_pedido_matricula:
                    pks.extend(configuracao_pedido_matricula.get_alunos_aptos().values_list('pk', flat=True))
                qs_mp = qs_mp.filter(pk__in=set(pks))

            if turmas or turmas_atuais:
                ids_turmas = [turma.id for turma in turmas] + [turma.id for turma in turmas_atuais]
                qs_mp = qs_mp.filter(aluno__curso_campus__ativo=True, matriculadiario__diario__turma_id__in=ids_turmas)

            if diarios or diarios_atuais:
                ids_diarios = [diario.id for diario in diarios] + [diario.id for diario in diarios_atuais]
                qs_mp = qs_mp.filter(aluno__curso_campus__ativo=True, matriculadiario__diario__in=ids_diarios)
                qs_md = MatriculaDiario.objects.none()
                for diario in Diario.objects.filter(pk__in=ids_diarios):
                    qs_md = qs_md | MatriculaDiario.objects.filter(diario_id=diario.id).exclude(
                        situacao__in=[MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_CANCELADO, MatriculaDiario.SITUACAO_TRANCADO]
                    )
                qs_mp = qs_mp.filter(matriculadiario__in=qs_md.distinct())

            if polos:
                ids_polos = [polo.id for polo in polos]
                qs_mp = qs_mp.filter(aluno__polo_id__in=ids_polos)

            if matriculas:
                ids_alunos = [matricula.id for matricula in matriculas]
                qs_mp = qs_mp.filter(aluno_id__in=ids_alunos)

            qs_a = Aluno.objects.filter(id__in=qs_mp.order_by('aluno_id').values_list('aluno_id', flat=True).distinct())

            if enade:
                qs_a = qs_a.filter(registroconvocacaoenade__convocacao_enade_id=enade.id)

            if tipo_convocacao:
                qs_a = qs_a.filter(registroconvocacaoenade__convocacao_enade_id=enade.id, registroconvocacaoenade__tipo_convocacao=tipo_convocacao)

            if periodo:
                qs_a = qs_a.filter(
                    registroconvocacaoenade__convocacao_enade_id=enade.id, registroconvocacaoenade__periodo_convocacao_regencia_id=periodo
                )

            self.qs = qs_a
            self.fields['alunos'].queryset = qs_a
            qtd_alunos_qs = qs_a.count()
            if qtd_alunos_qs > 100:
                if 'alunos' in self.fields:
                    # esconde listagem de alunos quando tem mais de 100 destinatários
                    msg = f'Serão notificados {qtd_alunos_qs} alunos.'
                    self.fields['alunos'].widget = forms.AlertWidget(msg)
                    self.fields['alunos'].required = False
                    if self.step == 1 and self.data:
                        self.ALERT = f'A mensagem será enviada para {qtd_alunos_qs} alunos. Caso deseje visualizar cada um deles, refine a sua pesquisa com mais informações de modo que o total de destinatários não ultrapasse 100 alunos.'
                    if self.step > 1:
                        self.ALERT = msg
                    if 'senha' in self.fields:
                        self.fields['senha'].help_text = f'Confirmo que desejo enviar a mensagem para {qtd_alunos_qs} alunos.'

            else:
                alunos_selecionados = self.get_entered_data('alunos', is_list=True)
                if alunos_selecionados and len(alunos_selecionados) <= 100:
                    # retira confirmação com senha quando tem 100 ou menos destinatários
                    if 'senha' in self.fields:
                        del self.fields['senha']
                    if self.step > 1:
                        self.INFO = f'A mensagem será enviada para {len(alunos_selecionados)} alunos.'

    def clean(self):
        uo = self.get_entered_data('uo', is_list=True)
        programa = self.get_entered_data('programa', is_list=True)
        modalidade = self.get_entered_data('modalidade', is_list=True)
        situacao_matricula = self.get_entered_data('situacao_matricula', is_list=True)
        situacao_matricula_periodo = self.get_entered_data('situacao_matricula_periodo', is_list=True)
        curso_campus = self.get_entered_data('curso_campus', is_list=True)
        turma = self.get_entered_data('turma', is_list=True) or self.get_entered_data('turmas_atuais', is_list=True)
        diario = self.get_entered_data('diario', is_list=True) or self.get_entered_data('diarios_atuais', is_list=True)
        aluno = self.get_entered_data('aluno', is_list=True)
        if not (uo or programa or modalidade or situacao_matricula or situacao_matricula_periodo or curso_campus or turma or diario or aluno):
            raise forms.ValidationError('Selecione, no mínimo, um filtro para os destinatários da mensagem.')
        return self.cleaned_data

    def processar(self, request):
        alunos = self.get_entered_data('alunos', is_list=True)
        if alunos and alunos.exists():
            self.qs = alunos
        coordenadores = []
        if self.get_entered_data('enviar_coordenador'):
            coordenadores = self.qs.values_list('curso_campus__coordenador__user__id', flat=True).distinct()
            coordenadores = User.objects.filter(id__in=coordenadores)
        diretores = []
        if self.get_entered_data('enviar_diretor'):
            setores_diretorias = self.qs.values_list('curso_campus__diretoria__setor__id', flat=True).distinct()
            ids_usuarios = (
                UsuarioGrupoSetor.objects.filter(setor__in=setores_diretorias, usuario_grupo__group__name='Diretor Acadêmico')
                .values_list('usuario_grupo__user', flat=True)
                .order_by('usuario_grupo__user')
                .distinct()
            )
            diretores = User.objects.filter(id__in=ids_usuarios)

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

            mensagem = Mensagem()
            mensagem.remetente = request.user
            mensagem.assunto = self.cleaned_data['assunto']
            mensagem.conteudo = self.cleaned_data['conteudo']
            mensagem.anexo = anexo
            forma_envio = int(self.cleaned_data['forma_envio'])
            if forma_envio in [1, 3]:
                mensagem.via_suap = True
            if forma_envio in [2, 3]:
                mensagem.via_email = True
            mensagem.save()
            for aluno in self.qs:
                user = aluno.get_user()
                if user:
                    mensagem.destinatarios.add(user)
            for coordenador in coordenadores:
                if coordenador:
                    mensagem.destinatarios.add(coordenador)
            mensagem.save()

            if mensagem.via_email:
                return mensagem.enviar_emails(self.qs, filename, coordenadores, diretores)

        return total
