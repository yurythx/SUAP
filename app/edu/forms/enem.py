import datetime
import hashlib

from dateutil import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from comum.models import Vinculo
from djtools import forms
from djtools.forms import ReCaptchaField
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from djtools.utils import mask_cpf, normalizar_nome_proprio, running_tests
from edu.models import (
    ConfiguracaoCertificadoENEM,
    RegistroAlunoINEP,
    RegistroEmissaoCertificadoENEM,
    RegistroEmissaoDiploma,
    SolicitacaoCertificadoENEM,
)
from protocolo.models import Processo
from rh.models import Funcao, Servidor, UnidadeOrganizacional


class ConfiguracaoCertificadoENEMForm(forms.ModelForm):
    responsaveis_vinculos = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, required=True, label='Responsáveis pela Certificação do ENEM')
    planilha_inep = forms.FileFieldPlus(
        required=False,
        label='Planilha do INEP',
        help_text='Arquivo .xls gerado no sistema do INEP que contém os pedidos de Certificação do ENEM para a Instituição',
    )
    uo_planilha = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus da Planilha', required=False)

    class Meta:
        exclude = ()
        model = ConfiguracaoCertificadoENEM

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsaveis_vinculos'].queryset = Vinculo.objects.funcionarios().filter(ativo=True)

    def clean_uo_planilha(self):
        planilha_inep = self.cleaned_data.get('planilha_inep')
        uo_planilha = self.cleaned_data.get('uo_planilha')

        if planilha_inep and not uo_planilha:
            raise ValidationError('Você precisa informar o Campus da Planilha.')
        return self.cleaned_data.get('uo_planilha')

    def save(self, *args, **kwargs):
        """Salva a configuração e processa a planilha de certificados ENEM.

        Returns:
            ConfiguracaoCertificadoENEM: instância salva da configuração.
        """
        import pandas as pd

        super().save(*args, **kwargs)
        self.instance.save()

        # Adicionando os responsáveis pela certificação no grupo Certificador ENEM
        responsaveis_vinculos = self.cleaned_data['responsaveis_vinculos']
        grupo = Group.objects.get_or_create(name='Certificador ENEM')[0]

        for responsavel in responsaveis_vinculos:
            responsavel.user.groups.add(grupo)

        if self.cleaned_data['planilha_inep']:
            planilha_inep = self.cleaned_data['planilha_inep'].file
            uo_planilha = self.cleaned_data.get('uo_planilha')

            df = pd.read_excel(planilha_inep, header=None)

            for _index, row in df.iloc[1:].iterrows():
                inscricao = int(row.iloc[0])
                nome = normalizar_nome_proprio(row.iloc[1])
                nome_mae = normalizar_nome_proprio(row.iloc[2])

                # Tratando o RG
                rg = str(row.iloc[3]).replace(',', '').replace('.', '').replace('-', '').replace(' ', '')

                # Tratando o CPF
                cpf = str(int(row.iloc[4]))
                cpf = cpf.rjust(11, '0')
                cpf = mask_cpf(cpf)

                # Lendo o campo de data do Excel para o formato do Python
                data_nascimento = pd.to_datetime(row.iloc[5]).to_pydatetime()

                nota_cn = row.iloc[6]
                if nota_cn == '-':
                    nota_cn = 0

                nota_ch = row.iloc[7]
                if nota_ch == '-':
                    nota_ch = 0

                nota_lc = row.iloc[8]
                if nota_lc == '-':
                    nota_lc = 0

                nota_mt = row.iloc[9]
                if nota_mt == '-':
                    nota_mt = 0

                nota_redacao = row.iloc[10]
                if nota_redacao == '-':
                    nota_redacao = 0

                # Criando ou capturando o objeto RegistroAlunoINEP
                r = RegistroAlunoINEP.objects.filter(cpf=cpf, configuracao_certificado_enem=self.instance)

                if not r.exists():
                    r = RegistroAlunoINEP()
                else:
                    r = r[0]

                r.numero_inscricao = inscricao
                r.nome = nome
                r.nome_mae = nome_mae
                r.rg = rg
                r.cpf = cpf
                r.data_nascimento = data_nascimento
                r.nota_ch = nota_ch
                r.nota_cn = nota_cn
                r.nota_lc = nota_lc
                r.nota_mt = nota_mt
                r.nota_redacao = nota_redacao
                r.configuracao_certificado_enem = self.instance
                r.uo = uo_planilha
                r.save()

        return self.instance


class SolicitacaoCertificadoENEMForm(forms.ModelForm):
    id = forms.CharField(label='Id', widget=forms.TextInput(attrs={'readonly': True}))

    class Meta:
        model = SolicitacaoCertificadoENEM
        fields = ('id',)


class SolicitarCertificadoENEMForm(forms.ModelForm):
    cpf = forms.BrCpfField()
    email = forms.EmailField()
    confirmacao_email = forms.EmailField(label='Confirmação do Email')
    telefone = forms.BrTelefoneField(max_length=255, required=False, label='Telefone', help_text='Formato: "(XX) XXXX-XXXX"')
    documento_identidade_frente = forms.FileFieldPlus(
        label='Documento de Identidade - Frente',
        max_file_size=10485760,
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        help_text='Cópia do documento de identidade - Frente. O formato do arquivo deve ser ".pdf", ".jpeg", ".jpg" ou ".png"',
    )
    documento_identidade_verso = forms.FileFieldPlus(
        label='Documento de Identidade - Verso',
        max_file_size=10485760,
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        help_text='Cópia do documento de identidade - Verso. O formato do arquivo deve ser ".pdf", ".jpeg", ".jpg" ou ".png"',
    )
    recaptcha = ReCaptchaField(label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['configuracao_certificado_enem'].queryset = ConfiguracaoCertificadoENEM.objects.filter(manual=False)

        if running_tests():
            self.fields.pop('recaptcha')

    def clean_confirmacao_email(self):
        email = self.cleaned_data.get('email')
        confirmacao_email = self.cleaned_data.get('confirmacao_email')

        if email is not None and confirmacao_email is not None:
            if email != confirmacao_email:
                raise ValidationError('Os emails informados não conferem.')

        return confirmacao_email

    def clean(self):
        if (
            not running_tests()
            and self.cleaned_data.get('configuracao_certificado_enem') is not None
            and self.cleaned_data.get('tipo_certificado') is not None
            and self.cleaned_data.get('cpf') is not None
            and self.cleaned_data.get('email') is not None
            and self.cleaned_data.get('confirmacao_email') is not None
            and self.cleaned_data.get('documento_identidade_frente') is not None
            and self.cleaned_data.get('documento_identidade_verso') is not None
            and self.cleaned_data.get('recaptcha') is not None
        ):
            qs_candidato_habilitado = RegistroAlunoINEP.objects.filter(
                configuracao_certificado_enem=self.cleaned_data['configuracao_certificado_enem'], cpf=self.cleaned_data['cpf']
            )

            # O candidato está habilitado a emitir o certificado pela instituição?
            if qs_candidato_habilitado.exists():
                # O candidato já possui um registro de certificado não cancelada para esta edição do ENEM?
                qs_candidato_possui_certificado = RegistroEmissaoCertificadoENEM.objects.filter(
                    solicitacao__cpf=self.cleaned_data.get('cpf'),
                    solicitacao__configuracao_certificado_enem=self.cleaned_data['configuracao_certificado_enem'],
                    solicitacao__tipo_certificado=self.cleaned_data['tipo_certificado'],
                    cancelado=False,
                )
                if qs_candidato_possui_certificado.exists():
                    raise ValidationError(
                        'O candidado já possui um certificado emitido para esta edição do ENEM. <a href="/edu/gerar_certificado_enem/{}/">Não recebeu o certificado por email ou deseja reimprimir?</a>'.format(
                            qs_candidato_possui_certificado.latest('via').codigo_geracao_certificado
                        )
                    )

                # O candidato possui alguma solicitação em aberto?
                qs_candidato_possui_solicitacao_aberta = SolicitacaoCertificadoENEM.objects.filter(
                    cpf=self.cleaned_data.get('cpf'),
                    configuracao_certificado_enem=self.cleaned_data['configuracao_certificado_enem'],
                    tipo_certificado=self.cleaned_data['tipo_certificado'],
                    avaliador__isnull=True,
                )
                if qs_candidato_possui_solicitacao_aberta.exists():
                    raise ValidationError('O candidado já possui uma solicitação em aberto para esta edição do ENEM.')

                configuracao_enem = self.cleaned_data['configuracao_certificado_enem']
                candidato = qs_candidato_habilitado[0]
                diferenca_em_anos = relativedelta.relativedelta(configuracao_enem.data_primeira_prova, candidato.data_nascimento).years

                # O candidado é maior de idade?
                if diferenca_em_anos < 18:
                    raise ValidationError(
                        'O candidato não está habilitado para solicitar o Certificado ENEM pois não completou 18 anos antes da data de realização da primeira prova.'
                    )

                # O tipo do certificado é completo?
                if self.cleaned_data['tipo_certificado'] == 1:
                    # O candidato atingiu a nota mínima em cada uma das áreas de conhecimento e redação?
                    if not candidato.apto_certificado_completo():
                        raise ValidationError(
                            'O candidato não está habilitado para solicitar o Certificado ENEM pois não atingiu a pontuação mínima necessária em cada uma das áreas de conhecimento e na redação.'
                        )
                else:
                    # O candidato selecionou a opção certificado "Parcial" porém tem nota suficiente para emitir o certificado "Completo"
                    if candidato.apto_certificado_completo():
                        raise ValidationError(
                            'Atenção: Você atingiu a pontuação necessária para a emissão do certificado completo. Portanto a solocitação do certificado parcial não pode ser concluída.'
                        )

                    # O candidato atingiu a nota mínima em alguma das áreas de conhecimento ou redação?
                    if not candidato.apto_certificado_parcial():
                        raise ValidationError(
                            'O candidato não está habilitado para solicitar o Certificado ENEM pois não atingiu a pontuação mínima necessária em nenhuma das áreas de conhecimento ou na redação.'
                        )
            else:
                # O candidato não está apto a solicitar o certificado.
                raise ValidationError('O candidato não está habilitado para solicitar o Certificado ENEM por esta instituição.')

        return self.cleaned_data

    def processar(self):
        self.instance.nome = normalizar_nome_proprio(self.instance.nome)
        self.instance.codigo_geracao_solicitacao = hashlib.sha1(
            f'{self.instance.cpf}{self.instance.tipo_certificado}{datetime.datetime.now()}{settings.SECRET_KEY}'.encode()
        ).hexdigest()[0:16]
        self.instance.save()
        return self.instance

    class Meta:
        model = SolicitacaoCertificadoENEM
        fields = (
            'configuracao_certificado_enem',
            'tipo_certificado',
            'nome',
            'cpf',
            'email',
            'confirmacao_email',
            'telefone',
            'documento_identidade_frente',
            'documento_identidade_verso',
        )


class ConsultarAndamentoSolicitacaoCertificadoENEMForm(forms.FormPlus):
    codigo_autenticacao = forms.CharFieldPlus(
        width=130,
        max_length=16,
        label='Código de Autenticação',
        help_text='O código é composto de 16 dígitos alfanuméricos e se encontra na parte inferior do comprovante da solicitação.',
    )
    cpf = forms.BrCpfField(label='CPF do Solicitante')

    def processar(self):
        try:
            obj = SolicitacaoCertificadoENEM.objects.get(
                codigo_geracao_solicitacao=self.cleaned_data.get('codigo_autenticacao'), cpf=self.cleaned_data.get('cpf')
            )
        except SolicitacaoCertificadoENEM.DoesNotExist:
            return None

        return obj


class CadastrarSolicitacaoCertificadoENEMForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus')
    nome_mae = forms.CharFieldPlus(width=500, label='Nome da Mãe')
    numero_rg = forms.CharField(max_length=255, label='Número do RG')
    cpf = forms.BrCpfField()
    data_nascimento = forms.DateFieldPlus(label='Data de Nascimento')
    email = forms.EmailField(required=False)
    telefone = forms.BrTelefoneField(max_length=255, required=False, label='Telefone', help_text='Formato: "(XX) XXXX-XXXX"')
    numero_inscricao = forms.CharField(max_length=255, label='Número de Inscrição')
    nota_ch = forms.DecimalFieldPlus(label='Nota - Ciências Humanas e suas Tecnologias', help_text='Formato: 500,00')
    nota_cn = forms.DecimalFieldPlus(label='Nota - Ciências da Natureza e suas Tecnologias', help_text='Formato: 500,00')
    nota_lc = forms.DecimalFieldPlus(label='Nota - Linguagens, Códigos e suas Tecnologias', help_text='Formato: 500,00')
    nota_mt = forms.DecimalFieldPlus(label='Nota - Matemática e suas Tecnologias', help_text='Formato: 500,00')
    nota_redacao = forms.DecimalFieldPlus(label='Nota - Redação', help_text='Formato: 500,00')
    processo = forms.ModelChoiceFieldPlus(Processo.objects, label='Processo', required=False)

    fieldsets = (
        ('Dados da Solicitação', {'fields': (('configuracao_certificado_enem', 'uo'), ('tipo_certificado', 'processo'))}),
        ('Dados do Solicitante', {'fields': ('nome', 'nome_mae', 'numero_rg', 'cpf', 'data_nascimento', 'email', 'telefone')}),
        ('Dados do Extrato de Desempenho do ENEM', {'fields': ('numero_inscricao', 'nota_cn', 'nota_ch', 'nota_lc', 'nota_mt', 'nota_redacao')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields['processo'].required = False

            registro_inep = RegistroAlunoINEP.objects.get(
                configuracao_certificado_enem=self.instance.configuracao_certificado_enem, cpf=self.instance.cpf
            )
            self.initial['nome_mae'] = registro_inep.nome_mae
            self.initial['numero_rg'] = registro_inep.rg
            self.initial['data_nascimento'] = registro_inep.data_nascimento
            self.initial['numero_inscricao'] = registro_inep.numero_inscricao
            self.initial['nota_ch'] = registro_inep.nota_ch
            self.initial['nota_cn'] = registro_inep.nota_cn
            self.initial['nota_lc'] = registro_inep.nota_lc
            self.initial['nota_mt'] = registro_inep.nota_mt
            self.initial['nota_redacao'] = registro_inep.nota_redacao

    def clean(self):
        if (
            not self.instance.pk
            and 'configuracao_certificado_enem' in self.cleaned_data
            and 'uo' in self.cleaned_data
            and 'tipo_certificado' in self.cleaned_data
            and 'cpf' in self.cleaned_data
            and 'data_nascimento' in self.cleaned_data
            and 'nota_ch' in self.cleaned_data
            and 'nota_lc' in self.cleaned_data
            and 'nota_mt' in self.cleaned_data
            and 'nota_redacao' in self.cleaned_data
        ):
            # O candidato já possui um registro de certificado não cancelada para esta edição do ENEM?
            qs_candidato_possui_certificado = RegistroEmissaoCertificadoENEM.objects.filter(
                solicitacao__cpf=self.cleaned_data.get('cpf'),
                solicitacao__configuracao_certificado_enem=self.cleaned_data['configuracao_certificado_enem'],
                solicitacao__tipo_certificado=self.cleaned_data['tipo_certificado'],
                cancelado=False,
            )
            if qs_candidato_possui_certificado.exists():
                raise ValidationError(
                    'O candidado já possui um certificado emitido para esta edição do ENEM. <a href="/edu/gerar_certificado_enem/{}/">Não recebeu o certificado por email ou deseja reimprimir?</a>'.format(
                        qs_candidato_possui_certificado.latest('via').codigo_geracao_certificado
                    )
                )

            qs_candidato_possui_solicitacao_aberta = SolicitacaoCertificadoENEM.objects.filter(
                cpf=self.cleaned_data.get('cpf'),
                configuracao_certificado_enem=self.cleaned_data['configuracao_certificado_enem'],
                tipo_certificado=self.cleaned_data['tipo_certificado'],
                avaliada=False,
            ).exclude(pk=self.instance.pk)
            if qs_candidato_possui_solicitacao_aberta.exists():
                raise ValidationError('O candidado já possui uma solicitação em aberto para esta edição do ENEM.')

            configuracao_enem = self.cleaned_data['configuracao_certificado_enem']
            nota_minima_necessaria_areas_conhecimento = configuracao_enem.pontuacao_necessaria_areas_conhecimento
            nota_minima_necessaria_redacao = configuracao_enem.pontuacao_necessaria_redacao
            # diferenca_em_anos = relativedelta.relativedelta(configuracao_enem.data_primeira_prova, self.cleaned_data.get('data_nascimento')).years

            # O candidado é maior de idade?
            # if diferenca_em_anos < 18:
            # raise ValidationError(u'O candidato não está habilitado para solicitar o Certificado ENEM pois não completou 18 anos antes da data de realização da primeira prova.')

            # O tipo do certificado é completo?
            if self.cleaned_data['tipo_certificado'] == 1:
                # O candidato atingiu a nota mínima em cada uma das áreas de conhecimento e redação?
                if not (
                    self.cleaned_data['nota_ch'] >= nota_minima_necessaria_areas_conhecimento
                    and self.cleaned_data['nota_cn'] >= nota_minima_necessaria_areas_conhecimento
                    and self.cleaned_data['nota_lc'] >= nota_minima_necessaria_areas_conhecimento
                    and self.cleaned_data['nota_mt'] >= nota_minima_necessaria_areas_conhecimento
                    and self.cleaned_data['nota_redacao'] >= nota_minima_necessaria_redacao
                ):
                    raise ValidationError(
                        'O candidato não está habilitado para solicitar o Certificado ENEM pois não atingiu a pontuação mínima necessária em cada uma das áreas de conhecimento e na redação.'
                    )
            else:
                # O candidato atingiu a nota mínima em alguma das áreas de conhecimento ou na redação?
                if not (
                    self.cleaned_data['nota_ch'] >= nota_minima_necessaria_areas_conhecimento
                    or self.cleaned_data['nota_cn'] >= nota_minima_necessaria_areas_conhecimento
                    or (
                        self.cleaned_data['nota_lc'] >= nota_minima_necessaria_areas_conhecimento
                        and self.cleaned_data['nota_redacao'] >= nota_minima_necessaria_redacao
                    )
                    or self.cleaned_data['nota_mt'] >= nota_minima_necessaria_areas_conhecimento
                ):
                    raise ValidationError(
                        'O candidato não está habilitado para solicitar o Certificado ENEM pois não atingiu a pontuação mínima necessária em nenhuma das áreas de conhecimento ou na redação.'
                    )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        self.instance.nome = normalizar_nome_proprio(self.instance.nome)
        self.instance.solicitacao_manual = True

        if not self.instance.codigo_geracao_solicitacao:
            self.instance.codigo_geracao_solicitacao = hashlib.sha1(
                f'{self.instance.cpf}{self.instance.tipo_certificado}{datetime.datetime.now()}{settings.SECRET_KEY}'.encode()
            ).hexdigest()[0:16]

        configuracao_certificado_enem = self.cleaned_data['configuracao_certificado_enem']
        numero_inscricao = self.cleaned_data['numero_inscricao']
        nome = self.cleaned_data['nome']
        nome_mae = self.cleaned_data['nome_mae']
        rg = self.cleaned_data['numero_rg']
        cpf = self.cleaned_data['cpf']
        data_nascimento = self.cleaned_data['data_nascimento']
        nota_ch = self.cleaned_data['nota_ch']
        nota_cn = self.cleaned_data['nota_cn']
        nota_lc = self.cleaned_data['nota_lc']
        nota_mt = self.cleaned_data['nota_mt']
        nota_redacao = self.cleaned_data['nota_redacao']

        # Criando ou capturando o objeto RegistroAlunoINEP
        r = RegistroAlunoINEP.objects.filter(cpf=cpf, configuracao_certificado_enem=configuracao_certificado_enem)

        if not r.exists():
            r = RegistroAlunoINEP()
        else:
            r = r[0]

        r.numero_inscricao = numero_inscricao
        r.nome = nome
        r.nome_mae = nome_mae
        r.rg = rg
        r.cpf = cpf
        r.data_nascimento = data_nascimento
        r.nota_ch = nota_ch
        r.nota_cn = nota_cn
        r.nota_lc = nota_lc
        r.nota_mt = nota_mt
        r.nota_redacao = nota_redacao
        r.configuracao_certificado_enem = configuracao_certificado_enem
        r.save()

        return super().save(*args, **kwargs)

    class Meta:
        model = SolicitacaoCertificadoENEM
        exclude = ('avaliada', 'data_solicitacao', 'solicitacao_manual')


class EditarDadosPessoaisSolicitacaoCertificadoENEM(forms.ModelFormPlus):
    class Meta:
        model = RegistroAlunoINEP
        exclude = ('nome', 'cpf', 'configuracao_certificado_enem', 'numero_inscricao', 'nota_ch', 'nota_cn', 'nota_lc', 'nota_mt', 'nota_redacao')


class RejeitarSolicitacaoCertificadoENEMForm(forms.Form):
    TITLE = 'Rejeitar Solicitação de Certificado ENEM'
    SUBMIT_LABEL = 'Rejeitar Solicitação'
    razao_indeferimento = forms.CharField(widget=forms.Textarea(), required=True, label='Razão do Indeferimento')
    fieldsets = (('Razão do Indeferimento', {'fields': ('razao_indeferimento',)}),)


class ReplicarSolicitacaoCertificadoENEMForm(forms.ModelFormPlus):
    TITLE = 'Replicar Solicitação de Certificado ENEM'
    SUBMIT_LABEL = 'Replicar'

    class Meta:
        model = SolicitacaoCertificadoENEM
        fields = ('nome', 'cpf', 'email', 'telefone', 'processo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.cleaned_data['processo']:
            raise ValidationError('O número do processo é obrigatório para replicar esta solicitação.')

    def save(self, *args, **kwargs):
        self.instance.replicar(self.request.user)
        return self.instance


class AtenderComRessalvaSolicitacaoCertificadoENEMForm(forms.Form):
    TITLE = 'Atender com Ressalva a Solicitação de Certificado ENEM'
    SUBMIT_LABEL = 'Atender com Ressalva a Solicitação'
    razao_ressalva = forms.CharField(widget=forms.Textarea(), required=True, label='Razão da Ressalva')
    fieldsets = (('Razão da Ressalva', {'fields': ('razao_ressalva',)}),)


class CancelarRegistroEmissaoCertificadoENEMForm(forms.Form):
    TITLE = 'Cancelar o Registro de Emissão de Certificado ENEM'
    SUBMIT_LABEL = 'Cancelar Registro'
    razao_cancelamento = forms.CharField(widget=forms.Textarea(), required=True, label='Razão do Cancelamento')
    fieldsets = (('Razão do Cancelamento', {'fields': ('razao_cancelamento',)}),)

    def __init__(self, *args, **kwargs):
        self.registro = kwargs.pop('instance')
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.registro.eh_ultima_via():
            raise ValidationError('Apenas a última via pode ser cancelada.')


class RegistroEmissaoCertificadoENEMForm(forms.ModelForm):
    id = forms.CharField(label='Código', widget=forms.TextInput(attrs={'readonly': True}))

    class Meta:
        model = RegistroEmissaoDiploma
        fields = ['id']


class PesquisarRegistroAlunoINEPForm(forms.Form):
    METHOD = 'GET'
    TITLE = 'Buscar Candidadatos'
    SUBMIT_LABEL = 'Buscar'
    candidato = forms.ModelChoiceFieldPlus(
        RegistroAlunoINEP.objects, required=False, widget=AutocompleteWidget(search_fields=RegistroAlunoINEP.SEARCH_FIELDS)
    )
    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus', required=False)

    def __init__(self, configuracao_certificado_enem=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if configuracao_certificado_enem:
            self.fields['candidato'].queryset = RegistroAlunoINEP.objects.filter(configuracao_certificado_enem=configuracao_certificado_enem.pk)

    def processar(self, configuracao_certificado_enem):
        qs = RegistroAlunoINEP.objects.filter(configuracao_certificado_enem=configuracao_certificado_enem.pk).order_by('nome')
        candidato = self.cleaned_data['candidato']
        uo = self.cleaned_data['uo']

        if candidato:
            qs = qs.filter(pk=candidato.pk)

        if uo:
            qs = qs.filter(uo=uo.pk)

        return qs


class EditarRegistroAlunoINEPForm(forms.ModelForm):
    class Meta:
        model = RegistroAlunoINEP
        fields = ['nome', 'rg', 'cpf', 'numero_inscricao', 'data_nascimento', 'nome_mae']


class EscolherReitorDiretorGeralForm(forms.FormPlus):
    reitor = forms.ModelChoiceField(Servidor.objects, required=True, label='Reitor')
    diretor_geral = forms.ModelChoiceField(Vinculo.objects, required=True, label='Diretor Geral')

    fieldsets = (
        ('Reitor', {'fields': ('reitor', 'reitor_em_exercicio')}),
        ('Diretor Geral', {'fields': ('diretor_geral', 'diretor_geral_em_exercicio')}),
    )

    def __init__(self, diretores_gerais, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reitor'].queryset = Servidor.objects.filter(
            ativo=True, funcao__codigo=Funcao.CODIGO_CD, funcao_codigo__in=['1', '0001', '2', '0002']
        )

        self.fields['diretor_geral'].queryset = diretores_gerais
