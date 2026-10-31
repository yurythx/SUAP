import csv
import datetime
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.safestring import mark_safe

from comum import signer
from comum.models import CertificadoDigital, Vinculo
from comum.utils import get_uo, get_sigla_reitoria
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.storages import cache_file
from djtools.templatetags.filters import in_group
from djtools.utils import mask_cpf
from edu.models import (
    Aluno,
    CertificadoDiploma,
    CodigoAutenticadorSistec,
    ConfiguracaoCertificacaoParcial,
    ConfiguracaoLivro,
    CoordenadorRegistroAcademico,
    Credenciamento,
    Diretoria,
    Modalidade,
    ModeloDocumento,
    NaturezaParticipacao,
    NivelEnsino,
    RegistroEmissaoDiploma,
    SituacaoMatricula,
    Turma,
)
from protocolo.models import Processo
from rh.models import Servidor, UnidadeOrganizacional

from .utils import RedirectForm


class RegistroEmissaoDiplomaForm(forms.ModelFormPlus):
    id = forms.CharField(label='Código', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    pasta = forms.CharField(label='Pasta', required=True)

    class Meta:
        model = RegistroEmissaoDiploma
        fields = ['id', 'pasta', 'autenticacao_sistec', 'observacao']


class PublicaoDOURegistroEmissaoDiplomaForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroEmissaoDiploma
        fields = ['data_publicacao_dou', 'url_publicacao_dou']


class RegistroEmissaoDiplomaPublicForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    aluno = forms.CharField(label='Nome, Matrícula ou CPF', required=False, widget=forms.TextInput(attrs={'size': 20}))
    campus = forms.ModelChoiceField(required=False, queryset=UnidadeOrganizacional.objects.campi().all(), label='Campus')
    modalidade = forms.ModelChoiceField(required=False, queryset=Modalidade.objects.all(), label='Modalidade')

    def processar(self):
        qs = RegistroEmissaoDiploma.objects.exclude(cancelado=True)
        nome = self.cleaned_data['aluno']
        campus = self.cleaned_data['campus']
        modalidade = self.cleaned_data['modalidade']
        if nome:
            qs = qs.filter(aluno__pessoa_fisica__nome__icontains=nome) | qs.filter(aluno__pessoa_fisica__cpf=nome) | qs.filter(aluno__matricula=nome)
        if campus:
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo=campus)
        if modalidade:
            qs = qs.filter(aluno__curso_campus__modalidade=modalidade)
        return qs


class EmitirSegundaViaDiplomaForm(forms.FormPlus):
    processo = forms.ModelChoiceFieldPlus(Processo.objects, label='Processo')
    numero_formulario = forms.CharField(
        label='Número do Formulário', required=False, help_text='Número de série do papel em caso de utilização de papel moeda/timbrado.'
    )
    autenticacao_sistec = forms.CharField(
        label='Autenticação SISTEC', required=False, help_text='Código de autenticação SISTEC. Obrigatório para alunos de cursos técnicos.'
    )

    def processar(self, registro):
        processo = self.cleaned_data['processo']
        numero_formulario = self.cleaned_data['numero_formulario']
        autenticacao_sistec = self.cleaned_data['autenticacao_sistec']
        return RegistroEmissaoDiploma.gerar_registro(registro.aluno, processo, numero_formulario, registro.pasta, autenticacao_sistec)


class EmitirCertificacaoParcialForm(forms.FormPlus):
    aluno = forms.ModelChoiceFieldPlus(Aluno.locals, label='Aluno', required=True)
    config_certificacao = forms.ModelChoiceFieldPlus(
        ConfiguracaoCertificacaoParcial.objects,
        label='Certificado',
        required=True,
        widget=AutocompleteWidget(
            search_fields=ConfiguracaoCertificacaoParcial.SEARCH_FIELDS,
            form_filters=[
                ('aluno', 'matriz__aluno'),
            ],
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Aluno.locals.filter(matriz__emite_certificacao_parcial=True)
        qs = qs.filter(matriz__certificado_parcial_acumulavel=True) | qs.filter(
            matriz__certificado_parcial_acumulavel=False,
            situacao_id__in=[
                SituacaoMatricula.JUBILADO,
                SituacaoMatricula.EVASAO,
                SituacaoMatricula.CANCELADO,
                SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            ],
        )
        self.fields['aluno'].queryset = qs.distinct()

    def clean_config_certificacao(self):
        config_certificacao = self.cleaned_data.get('config_certificacao')
        aluno = self.cleaned_data.get('aluno')
        if config_certificacao.matriz_id != aluno.matriz_id:
            raise forms.ValidationError('Este certificado não faz parte da matriz do aluno.')
        componentes_certificacao = list(
            config_certificacao.componentecurricularcertificacaoparcial_set.values_list('componente_curricular__componente_id', flat=True)
        )
        componentes_cumpridos = aluno.get_ids_componentes_cumpridos()
        if not all(item in componentes_cumpridos for item in componentes_certificacao):
            raise forms.ValidationError('O aluno não cumpriu todos os requisitos para emissão deste certificado.')
        return config_certificacao

    def processar(self):
        aluno = self.cleaned_data['aluno']
        config_certificacao = self.cleaned_data['config_certificacao']
        registro = RegistroEmissaoDiploma.gerar_registro_certificacao_parcial(aluno, config_certificacao)
        registro.registrar(config_certificacao)
        return registro.id


class EmitirDiplomaForm(FormWizardPlus):
    processo = forms.ModelChoiceFieldPlus(Processo.objects, label='Processo')
    numero_pasta = forms.CharField(
        label='Nome da Pasta', required=False, help_text='Nome da pasta na qual o registro de emissão de diploma será guardado'
    )

    def validar(self, aluno):
        if (
            RegistroEmissaoDiploma.objects.filter(aluno_id=aluno.id, situacao__isnull=False)
            .exclude(situacao__in=[RegistroEmissaoDiploma.CANCELADO, RegistroEmissaoDiploma.FINALIZADO])
            .exists()
        ):
            raise forms.ValidationError('Este aluno possui registro de emissão de diploma que não foi finalizado ou cancelado.')

        curso_pode_emitir_diploma, msg = aluno.curso_campus.pode_emitir_diploma(return_message_error=True)
        if not curso_pode_emitir_diploma:
            raise ValidationError(msg)

        if not aluno.is_fic() and not self.usuario_pode_emitir_para_cursos_regulares():
            raise forms.ValidationError('Apenas Diretores e Coordenadores de Registro Acadêmico podem emitir diplomas de cursos regulares.')

        if not aluno.is_proitec():
            link_edicao_aluno = f"<a href='/admin/edu/aluno/{aluno.id}/'>Clique aqui para informá-la.</a>"
            if not aluno.pessoa_fisica.nascimento_data:
                raise forms.ValidationError(mark_safe(f'Aluno sem data de nascimento definida. {link_edicao_aluno}'))

            if not aluno.naturalidade:
                raise forms.ValidationError(mark_safe(f'Aluno sem naturalidade definida. {link_edicao_aluno}'))

        fisico = not aluno.curso_campus.assinatura_digital and not aluno.curso_campus.assinatura_eletronica
        if (
            fisico
            and not ConfiguracaoLivro.objects.filter(
                uo=aluno.curso_campus.diretoria.setor.uo, modalidades__in=[aluno.curso_campus.modalidade]
            ).exists()
        ):
            raise forms.ValidationError('Não há configuração de livro para o campus e modalidade do curso do aluno.')

        if not (
            aluno.situacao_id in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO]
            or aluno.is_integralizado_cursando
        ):
            raise forms.ValidationError('Apenas alunos que concluíram podem ter seu diploma/certificado emitido.')

        natureza_participacao_id = aluno.get_natureza_participacao_id()
        if not Credenciamento.objects.filter(natureza_participacao=natureza_participacao_id, tipo=Credenciamento.CREDECIAMENTO).exists():
            natureza = NaturezaParticipacao.objects.get(id=natureza_participacao_id).descricao
            raise forms.ValidationError(f'Credenciamento da natureza de participação {natureza} não encontrado.')

        if aluno.possui_pendencia_nada_consta('Emissão de Diploma'):
            raise forms.ValidationError('É necessário dar baixa nos registros de "Nada Consta" antes da realização do procedimento.')

        return aluno

    def usuario_pode_emitir_para_cursos_regulares(self):
        return self.request.user.groups.filter(
            name__in=['Coordenador de Registros Acadêmicos', 'Diretor Acadêmico', 'Administrador Acadêmico']
        ).exists()

    @transaction.atomic
    def processar(self):
        ids = []
        if 'aluno' in self.fields:
            alunos = [self.cleaned_data['aluno']]
        else:
            alunos = self.cleaned_data['alunos']
        numero_pasta = None
        numero_formulario = 'numero_formulario' in self.cleaned_data and self.cleaned_data['numero_formulario'] or None
        autenticacao_sistec = 'autenticacao_sistec' in self.cleaned_data and self.cleaned_data['autenticacao_sistec'] or None
        processo = self.cleaned_data['processo']

        for aluno in alunos:
            # Emissão de diploma em lote
            if 'prefixo' in self.cleaned_data:
                if numero_pasta is None and self.cleaned_data['numero_pasta']:
                    numero_pasta = int(self.cleaned_data['numero_pasta'])
                pasta = '{}{}'.format(self.cleaned_data['prefixo'], numero_pasta or '')
                if numero_pasta is not None:
                    numero_pasta += 1
            # Emissão de diploma individualizado
            else:
                pasta = self.cleaned_data['numero_pasta']
            via = self.cleaned_data.get('via')
            registro = RegistroEmissaoDiploma.gerar_registro(aluno, processo, numero_formulario, pasta, autenticacao_sistec, via)
            if self.is_emissao_em_lote() or aluno.curso_campus.assinatura_eletronica or aluno.curso_campus.assinatura_digital:
                registro.registrar()
            ids.append(str(registro.id))
        return ids


class EmitirDiplomaAlunoForm(EmitirDiplomaForm):
    aluno = forms.ModelChoiceFieldPlus(
        Aluno.locals,
        label='Aluno',
        widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS),
        help_text='Lista alunos com cursos ativos e situação "CONCLUÍDO" ou "FORMADO"',
    )
    numero_formulario = forms.CharField(
        label='Número do Formulário', required=False, help_text='Número de série do papel em caso de utilização de papel moeda/timbrado.'
    )
    autenticacao_sistec = forms.CharField(
        label='Autenticação SISTEC', required=False, help_text='Código de autenticação SISTEC. Obrigatório para alunos de cursos técnicos.'
    )
    via = forms.IntegerField(label='Via', required=False, min_value=1)

    steps = (
        [('Seleção do Aluno', {'fields': ('aluno',)})],
        [('Dados da Emissão', {'fields': ('processo', 'numero_formulario', 'numero_pasta', 'via', 'autenticacao_sistec')})],
    )

    def next_step(self):
        if 'autenticacao_sistec' in self.fields:
            aluno = self.get_entered_data('aluno')
            if aluno:
                if aluno.requer_autenticacao_sistec_para_emissao_diploma():
                    if not self.get_entered_data('autenticacao_sistec'):
                        list_codigo_sistec = aluno.curso_campus.codigo_sistec.split(';')
                        codigo = (
                            CodigoAutenticadorSistec.objects.filter(
                                cpf=aluno.pessoa_fisica.cpf,
                                codigo_unidade=aluno.curso_campus.diretoria.setor.uo.codigo_sistec,
                                codigo_curso__in=list_codigo_sistec,
                            )
                            .values_list('codigo_autenticacao', flat=True)
                            .first()
                        )
                        if codigo:
                            self.initial['autenticacao_sistec'] = codigo
                            self.fields['autenticacao_sistec'].initial = codigo
                if not aluno.eh_aluno_migrado_apos_conclusao_curso() or aluno.registroemissaodiploma_set.exclude(cancelado=True).exists():
                    self.fields['via'].widget = forms.HiddenInput()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Aluno.locals.filter(
            situacao__id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO]
        )
        qs = qs | Aluno.locals.filter(integralizou_ensino_medio=True)
        qs = qs.filter(matriz__isnull=False) | qs.filter(codigo_academico__isnull=False)
        if 'sica' in settings.INSTALLED_APPS:
            qs = qs | Aluno.objects.filter(historico__isnull=False)
        if not in_group(self.request.user, 'Administrador Acadêmico') and not in_group(self.request.user, 'Coordenador de Registro Acadêmico - SICA'):
            qs = qs.filter(curso_campus__diretoria__setor__uo=get_uo(self.request.user))

        self.fields['aluno'].queryset = qs.distinct()

    def clean_aluno(self):
        aluno = self.get_entered_data('aluno')
        aluno.solicitar_quitacao_nada_consta(procedimento='Emissão de Diploma')
        self.validar(aluno)
        return aluno

    def is_emissao_em_lote(self):
        return False

    def _clean_autenticacao_sistec(self):
        autenticacao_sistec = self.cleaned_data.get('autenticacao_sistec')
        aluno = self.get_entered_data('aluno')
        if aluno:
            if aluno.requer_autenticacao_sistec_para_emissao_diploma():
                if not autenticacao_sistec:
                    raise forms.ValidationError('A autenticação SISTEC é necessária para alunos dos cursos técnicos.')
        return autenticacao_sistec


class EmitirDiplomaLoteForm(EmitirDiplomaForm):
    alunos = forms.MultipleModelChoiceField(Aluno.locals, label='', widget=RenderableSelectMultiple('widgets/diploma_alunos_widget.html'))
    apenas_primeira_via = forms.BooleanField(label='1º Via', required=False, help_text='Listar apenas alunos sem registros de emissão de diploma.')
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects.none(),
        label='Turma',
        widget=AutocompleteWidget(search_fields=Turma.SEARCH_FIELDS),
        help_text='Apenas para turmas de cursos da modalidade FIC.',
    )
    prefixo = forms.CharField(
        label='Prefixo da Pasta',
        required=False,
        help_text='Prefixo que será usado para composição do nome da pasta na qual o registro de emissão de diploma será guardado. Ex: Caso deseje\
        que os registros de emissão de diploma sejam distribuídos nas pastas com numeração PASTA100, PASTA101, PASTA103, etc., informe o prefixo PASTA nesse campo e o número 100\
        no campo a seguir.',
    )

    numero_pasta = forms.CharField(
        label='Número da Pasta',
        required=False,
        help_text='Número inteiro que será utilizado na composição do nome da pasta no qual o registro de emissão de diploma será guardado',
    )

    steps = (
        [('Seleção da Turma', {'fields': ('turma', 'apenas_primeira_via')})],
        [('Seleção dos Alunos', {'fields': ('alunos',)})],
        [('Dados da Emissão', {'fields': ('processo', 'prefixo', 'numero_pasta')})],
    )

    def first_step(self, *args, **kwargs):
        qs = Turma.locals.filter(matriculaperiodo__aluno__situacao__id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO])
        qs = (
            qs.filter(curso_campus__modalidade__id=Modalidade.FIC)
            | qs.filter(curso_campus__assinatura_eletronica=True)
            | qs.filter(curso_campus__assinatura_digital=True)
        )
        self.fields['turma'].queryset = qs.distinct()

    def next_step(self):
        turma = self.get_entered_data('turma')
        if 'alunos' in self.fields:
            self.fields['alunos'].queryset = Aluno.locals.all()
        if 'alunos' in self.fields and turma:
            self.fields['alunos'].queryset = (
                self.fields['alunos']
                .queryset.filter(
                    matriz__isnull=False,
                    matriculaperiodo__turma=turma,
                    situacao__id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO],
                )
                .filter(Q(curso_campus__emite_diploma=True) | Q(curso_campus__assinatura_digital=True) | Q(curso_campus__assinatura_eletronica=True))
            ).distinct()
            apenas_primeira_via = self.get_entered_data('apenas_primeira_via')
            if apenas_primeira_via:
                self.fields['alunos'].queryset = self.fields['alunos'].queryset.filter(registroemissaodiploma__isnull=True)

    def clean_numero_pasta(self):
        numero_pasta = self.get_entered_data('numero_pasta')
        if numero_pasta:
            try:
                int(numero_pasta)
            except Exception:
                raise forms.ValidationError('Informe um valor inteiro para esse campo.')
        return numero_pasta

    def clean_alunos(self):
        alunos = self.cleaned_data['alunos']
        for aluno in alunos:
            aluno.solicitar_quitacao_nada_consta(procedimento='Emissão de Diploma')
        for aluno in alunos:
            self.validar(aluno)
        return alunos

    def is_emissao_em_lote(self):
        return True


class ImprimirDiplomaForm(forms.FormPlus):
    reitor = forms.ModelChoiceField(Servidor.objects.none(), required=True, label='Reitor')
    reitor_protempore = forms.BooleanField(label='Reitor Pro tempore?', required=False)
    diretor_geral = forms.ModelChoiceField(Vinculo.objects, label='Diretor Geral')
    diretor_geral_protempore = forms.BooleanField(label='Diretor Geral Pro tempore?', required=False)
    diretor_academico = forms.ModelChoiceField(Vinculo.objects, label='Diretor Acadêmico', required=False)
    diretor_ensino = forms.ModelChoiceField(Vinculo.objects, label='Diretor de Ensino', required=False)
    coordenador_registro_academico = forms.ModelChoiceField(
        CoordenadorRegistroAcademico.objects.none(), required=False, label='Coordenador de Registro Acadêmico'
    )

    modelo_documento = forms.ModelChoiceField(ModeloDocumento.objects, label='Modelo')

    fieldsets = (
        ('Reitor', {'fields': (('reitor', 'reitor_protempore'),)}),
        ('Diretores', {'fields': (('diretor_geral', 'diretor_geral_protempore'), ('diretor_academico', 'diretor_ensino'))}),
        ('Registro Escolar', {'fields': ('coordenador_registro_academico',)}),
        ('Modelo', {'fields': ('modelo_documento',)}),
    )

    SUBMIT_STYLE = 'success dontdisable'

    def __init__(self, *args, **kwargs):
        diretoria = kwargs.pop('diretoria', None)
        modalidade = kwargs.pop('modalidade', None)
        aluno_sica = kwargs.pop('aluno_sica', False)
        super().__init__(*args, **kwargs)

        # reitor
        diretoria_sistemica = Diretoria.objects.filter(tipo=Diretoria.TIPO_SISTEMICA).first()
        if diretoria_sistemica:
            self.fields['reitor'].queryset = diretoria_sistemica.get_reitores()
            reitoria = UnidadeOrganizacional.objects.suap().filter(sigla=get_sigla_reitoria()).first()
            self.reitor = reitoria.get_diretor_geral(True).first() if reitoria else None

            if self.reitor and self.fields['reitor'].queryset.filter(id=self.reitor.id).exists():
                self.fields['reitor'].initial = self.reitor.id

        # Coordenador de registros acadêmicos
        qs_cra = CoordenadorRegistroAcademico.objects.filter(diretoria__setor__uo_id=diretoria.setor.uo_id)
        if not self.request.user.has_group_cached('Administrador Acadêmico'):
            qs_cra = qs_cra.filter(eh_coordenador_registro=True)
            if not qs_cra.exists():
                qs_cra = CoordenadorRegistroAcademico.objects.filter(servidor__matricula=self.request.user.username)
        if qs_cra.exists():
            self.fields['coordenador_registro_academico'].queryset = qs_cra
            self.initial['coordenador_registro_academico'] = qs_cra[0].pk

        # diretores
        self.fields['diretor_geral'].queryset = diretoria.get_diretores_gerais()
        self.initial['diretor_geral'] = diretoria.diretor_geral_exercicio_id

        self.fields['diretor_academico'].queryset = diretoria.get_diretores_academicos()
        self.initial['diretor_academico'] = diretoria.diretor_academico_exercicio_id

        self.fields['diretor_ensino'].queryset = diretoria.get_diretores_de_ensino()

        # modelo de documento
        qs_modelo_documento = ModeloDocumento.objects.filter(modalidade_id=modalidade, ativo=True)
        if aluno_sica:
            qs_modelo_documento = qs_modelo_documento.filter(descricao__contains='SICA')
        else:
            qs_modelo_documento = qs_modelo_documento.exclude(descricao__contains='SICA')
        self.fields['modelo_documento'].queryset = qs_modelo_documento

    def clean(self):
        if not self.cleaned_data.get('diretor_academico') and not self.cleaned_data.get('diretor_ensino'):
            raise forms.ValidationError('Infome o Diretor Acadêmico ou o Diretor de Ensino.')
        return self.cleaned_data


class CancelarRegistroEmissaoDiplomaForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroEmissaoDiploma
        fields = ('motivo_cancelamento',)

    def processar(self):
        self.instance.cancelar()


class ImprimirRegistroDiplomaAlunoForm(RedirectForm):
    registro = forms.ModelChoiceFieldPlus(
        RegistroEmissaoDiploma.objects, label='Matrícula/Nome', widget=AutocompleteWidget(search_fields=RegistroEmissaoDiploma.SEARCH_FIELDS)
    )

    def get_url(self):
        return '/edu/registroemissaodiploma_pdf/{}/'.format(self.cleaned_data['registro'].pk)


class IniciarSessaoAssinaturaSenhaForm(forms.FormPlus):
    senha = forms.PasswordField()


class IniciarSessaoAssinaturaEletronicaForm(forms.FormPlus):
    senha = forms.PasswordField()
    certificado = forms.ModelChoiceFieldPlus(CertificadoDigital.objects, label='Certificado', required=True)
    senha_certificado = forms.CharField(label='Senha do Certificado', widget=forms.PasswordInput, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['certificado'].queryset = CertificadoDigital.objects.filter(user=self.request.user, validade__gte=datetime.date.today())

    def clean_senha_certificado(self):
        senha_certificado = self.cleaned_data.get('senha_certificado')
        try:
            certificado = self.cleaned_data.get('certificado')
            local_filename = cache_file(certificado.arquivo.name)
            validade = signer.expiration_date(local_filename, senha_certificado)
            os.unlink(local_filename)
            if validade < datetime.datetime.now():
                raise forms.ValidationError('Certificado com prazo de validade expirado.')
            self.request.session['sessao_assinatura_eletronica'] = (certificado.pk, senha_certificado)
            self.request.session.save()
        except BaseException:
            raise forms.ValidationError('Senha do certificado inválida.')
        return senha_certificado


class IniciarSessaoAssinaturaEletronicaViaApiForm(forms.FormPlus):
    senha = forms.PasswordField()

    def clean(self):
        cleaned_data = super().clean()
        self.request.session['sessao_assinatura_eletronica'] = (True, True)
        self.request.session.save()
        return cleaned_data


class RevogarDiplomaForm(forms.FormPlus):
    motivo = forms.CharFieldPlus(label='Motivo', widget=forms.Textarea())


class ImportarAutenticacaoSistecForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(label='Arquivo CSV')

    def processar(self):
        c = 0
        file_content = self.cleaned_data['arquivo'].read()

        content = file_content.decode('iso-8859-1')
        csv_reader = csv.reader(content.splitlines(), delimiter=';', quotechar='"')

        codigos_to_create = []

        for row in csv_reader:
            cpf, codigo_unidade, codigo_curso, codigo_autenticacao = row[1], row[16], row[21], row[17]

            if not CodigoAutenticadorSistec.objects.filter(codigo_unidade=codigo_unidade, codigo_curso=codigo_curso, cpf=mask_cpf(cpf)).exists():
                codigos_to_create.append(
                    CodigoAutenticadorSistec(
                        codigo_unidade=codigo_unidade, codigo_curso=codigo_curso, cpf=mask_cpf(cpf), codigo_autenticacao=codigo_autenticacao
                    )
                )
            c += 1

        if codigos_to_create:
            CodigoAutenticadorSistec.objects.bulk_create(codigos_to_create, ignore_conflicts=True)

        return c


class CertificadoDiplomaForm(forms.ModelFormPlus):
    class Meta:
        model = CertificadoDiploma
        fields = (
            'aluno',
            'processo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['aluno'].queryset = Aluno.objects.filter(
            matriz__isnull=False,
            situacao__in=(SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO),
            curso_campus__modalidade__nivel_ensino__pk__in=[NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO, NivelEnsino.MEDIO],
        )
