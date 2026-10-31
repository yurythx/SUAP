import datetime

from django.apps.registry import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import OuterRef, Subquery

from comum.models import Ano, Configuracao, Municipio, Ocupacao, OcupacaoPrestador, Pais, PessoaFisica, PrestadorServico, User
from comum.types import PessoaEnderecoCadastro, PessoaFisicaCadastro, PessoaTelefoneCadastro, PrestadorServicoCadastro
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from djtools.utils import CsvResponse, mask_cpf, retira_acentos
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    ConfiguracaoDadosDocentes,
    CursoFormacaoSuperior,
    Disciplina,
    MatriculaDiario,
    NucleoCentralEstruturante,
    ProcedimentoMatricula,
    Professor,
    ProjetoFinal,
    VinculoProfessorEAD,
)
from edu.models.cadastros_gerais import Deficiencia, SituacaoMatricula, TipoNEE
from edu.models.logs import Log, RegistroDiferenca
from rh.deduplicacao.entrada import (
    recusar_cadastro_de_prestador,
    filtro_par_passaporte,
    recusar_passaporte_de_outra_pessoa,
    travar_documentos_na_edicao,
)
from rh.enums import Nacionalidade
from rh.models import Servidor, UnidadeOrganizacional


class AtualizarFotoProfessorForm(forms.FormPlus):
    professor = forms.ModelChoiceField(Professor.objects, widget=forms.HiddenInput())
    foto = forms.PhotoCaptureField(required=False)
    arquivo = forms.ImageFieldPlus(required=False)

    fieldsets = (('Captura da foto com câmera', {'fields': ('professor', 'foto')}), ('Upload de arquivo', {'fields': ('arquivo',)}))

    def clean(self):
        if not self.cleaned_data['foto'] and not self.cleaned_data['arquivo']:
            raise forms.ValidationError('Retire a foto com a câmera ou forneça um arquivo.')
        else:
            return self.cleaned_data

    def processar(self, request):
        professor = self.cleaned_data['professor']
        if self.cleaned_data.get('foto'):
            dados = self.cleaned_data['foto']
        else:
            dados = self.cleaned_data['arquivo'].read()
        if request.user.has_perm('edu.efetuar_matricula'):
            professor.foto.save(f'{professor.pk}.jpg', ContentFile(dados))
            return 'Foto atualizada com sucesso.'
        else:
            return 'Esta funcionalidade encontra-se temporariamente indisponível.'


class VincularProfessorNCEForm(forms.FormPlus):
    professores = forms.MultipleModelChoiceFieldPlus(Professor.objects, label='Professor', required=True)

    def __init__(self, *args, **kwargs):
        self.nce = kwargs.pop('nce')
        super().__init__(*args, **kwargs)

    def processar(self):
        for professor in self.cleaned_data['professores']:
            self.nce.professor_set.add(professor)
        self.nce.save()


class ProfessorExternoForm(forms.ModelFormPlus):
    nome = forms.CharFieldPlus(width=300, label='Nome')
    sexo = forms.ChoiceField(choices=[['M', 'Masculino'], ['F', 'Feminino']])
    cpf = forms.BrCpfField(required=False)
    passaporte = forms.CharField(label='Nº do Passaporte', required=False, help_text='Esse campo é obrigatório para estrangeiros. Ex: BR123456')
    pais_origem = forms.ModelChoiceFieldPlus(
        Pais.objects.all(),
        label='País de Origem',
        required=False,
        help_text='Obrigatório para estrangeiros sem CPF: o passaporte vale junto com o país emissor.',
    )
    nacionalidade = forms.ChoiceField(choices=Nacionalidade.get_choices(), required=True, label='Nacionalidade')
    rg = forms.CharFieldPlus(label='Registro Geral', required=False)
    rg_orgao = forms.CharFieldPlus(label='Órgão Emissor', required=False, max_length=10)
    rg_data = forms.DateFieldPlus(label='Data de Emissão', required=False)
    rg_uf = forms.BrEstadoBrasileiroField(label='Unidade da Federação', required=False)
    nascimento_data = forms.DateFieldPlus(label='Data de Nascimento', required=False)
    nome_pai = forms.CharFieldPlus(label='Nome do Pai', required=False)
    nome_mae = forms.CharFieldPlus(label='Nome da Mãe', required=False)
    naturalidade = forms.ModelChoiceFieldPlus(Municipio.objects, required=False, label='Naturalidade')

    logradouro = forms.CharFieldPlus(max_length=255, required=False, label='Logradouro', width=500)
    numero = forms.CharFieldPlus(max_length=255, required=False, label='Número', width=100)
    complemento = forms.CharField(max_length=255, required=False, label='Complemento')
    bairro = forms.CharField(max_length=255, required=False, label='Bairro')
    cep = forms.BrCepField(max_length=255, required=False, label='CEP')
    municipio = forms.ModelChoiceFieldPlus(
        Municipio.objects.all().order_by('pk'), required=False, label='Cidade', help_text='Preencha o nome da cidade sem acento.'
    )

    email = forms.EmailField(max_length=255, label='E-mail')
    telefone = forms.BrTelefoneField(max_length=255, required=False, label='Telefone', help_text='Formato: "(XX) XXXXX-XXXX"')
    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus')
    titulacao = forms.ChoiceField(label='Titulação', choices=[['', '-----'], *Professor.TITULACAO_CHOICES], required=True)
    ultima_instituicao_de_titulacao = forms.CharFieldPlus(
        label='Instituição', required=False, help_text='Instituição onde recebeu a última titulação'
    )
    area_ultima_titulacao = forms.ChoiceField(
        label='Área da Última Titulação', required=False, choices=[['', '-----'], *Professor.AREA_ULTIMA_TITULACAO_CHOICES]
    )
    ano_ultima_titulacao = forms.ModelChoiceField(Ano.objects, label='Ano', required=False, help_text='Ano em que obteu a última titulação')
    vinculo_professor_ead = forms.ModelChoiceField(
        VinculoProfessorEAD.objects, label='Vínculo', required=False, help_text='Vínculo EAD caso seja professor à distância'
    )
    nce = forms.MultipleModelChoiceFieldPlus(NucleoCentralEstruturante.objects, label='NCE', required=False)

    fieldsets = (
        (
            'Dados Pessoais',
            {
                'fields': (
                    'nome',
                    'cpf',
                    'passaporte',
                    'pais_origem',
                    'nacionalidade',
                    'sexo',
                    'nascimento_data',
                    'nome_pai',
                    'nome_mae',
                    'naturalidade',
                )
            },
        ),
        ('RG', {'fields': ('rg', 'rg_orgao', 'rg_data', 'rg_uf')}),
        ('Endereço', {'fields': ('cep', 'municipio', 'logradouro', 'numero', 'complemento', 'bairro')}),
        ('Dados para Contato', {'fields': ('email', 'telefone')}),
        ('Dados do Professor', {'fields': ('tipo', 'uo', 'nce')}),
        (
            'Dados da Formação',
            {
                'fields': (
                    ('ano_inicio_curso_superior', 'ano_conclusao_curso_superior'),
                    ('curso_superior', 'instituicao_ensino_superior'),
                    ('titulacao', 'possui_formacao_complementar'),
                    ('ultima_instituicao_de_titulacao',),
                    ('area_ultima_titulacao', 'ano_ultima_titulacao'),
                )
            },
        ),
        ('EAD', {'fields': ('vinculo_professor_ead',)}),
        ('Plano de Oferta', {'fields': ('ch_sala_aula_semanal',)}),
    )

    class Meta:
        model = Professor
        exclude = ('vinculo', 'foto', 'cursos_lecionados')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['nce'].queryset = NucleoCentralEstruturante.objects.all().order_by('descricao')
        self.fields['ano_inicio_curso_superior'].required = True
        self.fields['ano_conclusao_curso_superior'].required = True
        self.fields['curso_superior'].required = True
        self.fields['curso_superior'].queryset = CursoFormacaoSuperior.objects.filter(ativo=True)
        self.fields['instituicao_ensino_superior'].required = True

        if self.instance.pk:
            if self.instance.vinculo.pessoa.pessoafisica.nacionalidade == Nacionalidade.ESTRANGEIRO:
                self.fields['instituicao_ensino_superior'].required = False
            self.fields['nome'].initial = self.instance.vinculo.pessoa.nome
            self.fields['pais_origem'].initial = self.instance.vinculo.pessoa.pessoafisica.pais_origem
            travar_documentos_na_edicao(self, self.instance.vinculo.pessoa.pessoafisica)
            self.fields['nacionalidade'].initial = self.instance.vinculo.pessoa.pessoafisica.nacionalidade
            self.fields['sexo'].initial = self.instance.vinculo.pessoa.pessoafisica.sexo
            self.fields['email'].initial = self.instance.vinculo.email_pessoal
            if self.instance.vinculo.pessoa.pessoatelefone_set.all().exists():
                self.fields['telefone'].initial = self.instance.vinculo.pessoa.pessoatelefone_set.all()[0].numero
            self.fields['rg'].initial = self.instance.vinculo.pessoa.pessoafisica.rg
            self.fields['rg_orgao'].initial = self.instance.vinculo.pessoa.pessoafisica.rg_orgao
            self.fields['rg_data'].initial = self.instance.vinculo.pessoa.pessoafisica.rg_data
            self.fields['rg_uf'].initial = self.instance.vinculo.pessoa.pessoafisica.rg_uf
            self.fields['nascimento_data'].initial = self.instance.vinculo.pessoa.pessoafisica.nascimento_data
            self.fields['naturalidade'].initial = self.instance.vinculo.pessoa.pessoafisica.nascimento_municipio
            self.fields['nome_pai'].initial = self.instance.vinculo.pessoa.pessoafisica.nome_pai
            self.fields['nome_mae'].initial = self.instance.vinculo.pessoa.pessoafisica.nome_mae
            self.fields['municipio'].initial = self.instance.vinculo.pessoa.endereco_municipio
            self.fields['logradouro'].initial = self.instance.vinculo.pessoa.endereco_logradouro
            self.fields['numero'].initial = self.instance.vinculo.pessoa.endereco_numero
            self.fields['bairro'].initial = self.instance.vinculo.pessoa.endereco_bairro
            self.fields['complemento'].initial = self.instance.vinculo.pessoa.endereco_complemento
            self.fields['cep'].initial = self.instance.vinculo.pessoa.endereco_cep

            if self.instance.vinculo.setor:
                self.fields['uo'].initial = self.instance.vinculo.setor.uo

            if self.is_servidor():
                for field_name in [
                    'nome',
                    'cpf',
                    'passaporte',
                    'pais_origem',
                    'nacionalidade',
                    'sexo',
                    'email',
                    'rg',
                    'rg_orgao',
                    'rg_data',
                    'rg_uf',
                    'nascimento_data',
                    'naturalidade',
                    'nome_pai',
                    'nome_mae',
                    'uo',
                    'cep',
                    'municipio',
                    'logradouro',
                    'numero',
                    'complemento',
                    'bairro',
                    'tipo',
                ]:
                    self.fields[field_name].widget = forms.HiddenInput()
                    self.fields[field_name].required = False

        if self.request.POST.get('tipo') == str(Professor.TIPO_FIC):
            for name in 'ano_inicio_curso_superior', 'ano_conclusao_curso_superior', 'curso_superior', 'instituicao_ensino_superior', 'titulacao':
                self.fields[name].required = False

    def is_servidor(self):
        return self.instance.pk and self.instance.vinculo.eh_servidor()

    def clean_email(self):
        if not self.is_servidor():
            if not Configuracao.get_valor_por_chave('comum', 'permite_email_institucional_email_secundario') and Configuracao.eh_email_institucional(
                self.cleaned_data['email']
            ):
                raise forms.ValidationError('Escolha um e-mail que não seja institucional.')
        return self.cleaned_data['email']

    def clean_naturalidade(self):
        naturalidade = self.cleaned_data['naturalidade']
        if not self.is_servidor():
            nacionalidade = self.cleaned_data['nacionalidade']
            if nacionalidade and int(nacionalidade) == Nacionalidade.BRASILEIRO_NATO and naturalidade is None:
                self.add_error('naturalidade', 'O campo Naturalidade é obrigatório para nacionalidade Brasileiro Nato')
        return naturalidade

    def clean_cpf(self):
        if self.instance.pk is None:
            prestador = PrestadorServico.objects.filter(pessoa_fisica__cpf=self.cleaned_data['cpf']).first()
            if prestador and Professor.objects.filter(vinculo=prestador.get_vinculo()):
                raise forms.ValidationError('Já existe um professor externo cadastrado com este CPF.')
        return self.cleaned_data['cpf']

    def clean_passaporte(self):
        # value(): na edição o campo é somente leitura e não vem no POST
        passaporte = self['passaporte'].value()
        nacionalidade = self['nacionalidade'].value()
        eh_estrangeiro = int(nacionalidade) == Nacionalidade.ESTRANGEIRO if nacionalidade else False
        if eh_estrangeiro and not passaporte:
            self.add_error('passaporte', 'Informe o passaporte.')
        return passaporte

    def clean(self) -> dict:
        # Realizando verificação para permitir o cadastro da ocupação padrão do professor externo
        if not self.is_servidor():
            self._validar_nao_servidor()

        titulacao = self.cleaned_data.get('titulacao')
        if titulacao and titulacao not in ['Graduado', 'Graduada']:
            if not self.cleaned_data.get('ultima_instituicao_de_titulacao'):
                self.add_error('ultima_instituicao_de_titulacao', f'Este campo é obrigatório para a titulação {titulacao}')
            if not self.cleaned_data.get('area_ultima_titulacao'):
                self.add_error('area_ultima_titulacao', f'Este campo é obrigatório para a titulação {titulacao}')
            if not self.cleaned_data.get('ano_ultima_titulacao'):
                self.add_error('ano_ultima_titulacao', f'Este campo é obrigatório para a titulação {titulacao}')
        return super().clean()

    def _validar_nao_servidor(self) -> None:
        """Validações do professor que não é servidor: documento, usuário e configuração da ocupação padrão."""
        cpf = self.cleaned_data.get('cpf')
        passaporte = self.cleaned_data.get('passaporte')
        nacionalidade = self['nacionalidade'].value()
        eh_estrangeiro = int(nacionalidade) == Nacionalidade.ESTRANGEIRO if nacionalidade else False
        prestador_ja_cadastrado = False
        if not cpf and not eh_estrangeiro:
            self.add_error('cpf', 'O campo CPF é obrigatório para nacionalidades Brasileira')
        if eh_estrangeiro and not cpf:
            username = PrestadorServico.matricula_do_passaporte(passaporte, self.cleaned_data.get('pais_origem'))
            campo_erro = 'passaporte'
        else:
            username = PrestadorServico.gerar_matricula(cpf)
            campo_erro = 'cpf'

        professor_externo_ocupacao_padrao = Ocupacao.objects.filter(
            pk=Configuracao.get_valor_por_chave('edu', 'professor_externo_ocupacao_padrao') or 0
        ).first()
        professor_externo_dias_vencimento_contrato = int(
            Configuracao.get_valor_por_chave('edu', 'professor_externo_dias_vencimento_contrato') or '720'
        )
        if not (professor_externo_ocupacao_padrao and professor_externo_dias_vencimento_contrato):
            self.add_error('uo', 'É necessário preencher as configurações padrão do Professor Externo. Entre em contato com a equipe de TI.')

        # será vinculado a um cadastro de pretador existente
        if cpf and PrestadorServico.objects.filter(pessoa_fisica__cpf=cpf).first():
            prestador_ja_cadastrado = True
        if eh_estrangeiro:
            self._validar_pais_do_passaporte(cpf, passaporte)
        recusar_passaporte_de_outra_pessoa(self, cpf, passaporte, self.cleaned_data.get('pais_origem'))
        # anexa só pelo par exato país + passaporte; o legado sem país (login só o número) cai no "usuário já existe" abaixo
        if PrestadorServico.objects.filter(filtro_par_passaporte(passaporte, self.cleaned_data.get('pais_origem'), 'pessoa_fisica__')).exists():
            prestador_ja_cadastrado = True

        if not self.instance.pk and User.objects.filter(username=username).exists() and not prestador_ja_cadastrado:
            self.add_error(campo_erro, f'O usuário {username} já existe.')

        # antes do super().clean(), que levanta se já houver erro de campo. Só na criação: o mesmo caminho do
        # PrestadorServico.update_or_create (a PF do login não recebe documento de outra pessoa; a achada pelo documento,
        # outro nascimento).
        if not self.instance.pk:
            recusar_cadastro_de_prestador(self)

    def _validar_pais_do_passaporte(self, cpf: str | None, passaporte: str | None) -> None:
        """Estrangeiro sem CPF: o passaporte só identifica a pessoa junto com o país emissor."""
        pais = self.cleaned_data.get('pais_origem')
        if cpf or not passaporte:
            return
        if not pais:
            self.add_error('pais_origem', 'Informe o país de origem do passaporte.')

    def save(self, *args, **kwargs) -> Professor:
        if self.instance.pk is None:
            professor = super().save(commit=False)
        else:
            professor = self.instance
        if self.is_servidor():
            professor.save()
        else:
            cpf = self.cleaned_data.get('cpf', '')
            passaporte = self.cleaned_data.get('passaporte', '')
            pessoa_fisica: PessoaFisicaCadastro = {
                'cpf': cpf,
                'nome_registro': self.cleaned_data['nome'],
                'nacionalidade': int(self.cleaned_data['nacionalidade'] or 1),
                'passaporte': passaporte,
                'pais_origem': self.cleaned_data.get('pais_origem'),
                'email_secundario': self.cleaned_data['email'],
                'email': self.cleaned_data['email'],
                'rg': self.cleaned_data['rg'],
                'rg_orgao': self.cleaned_data['rg_orgao'],
                'rg_data': self.cleaned_data['rg_data'],
                'rg_uf': self.cleaned_data['rg_uf'],
                'nascimento_data': self.cleaned_data['nascimento_data'],
                'nascimento_municipio': self.cleaned_data['naturalidade'],
                'sexo': self.cleaned_data['sexo'],
                'nome_pai': self.cleaned_data['nome_pai'],
                'nome_mae': self.cleaned_data['nome_mae'],
            }
            endereco: PessoaEnderecoCadastro = {
                'municipio': self.cleaned_data['municipio'],
                'logradouro': self.cleaned_data['logradouro'],
                'numero': self.cleaned_data['numero'],
                'bairro': self.cleaned_data['bairro'],
                'complemento': self.cleaned_data['complemento'],
                'cep': self.cleaned_data['cep'],
            }
            telefone: PessoaTelefoneCadastro = {
                'numero': self.cleaned_data['telefone'],
            }
            dados: PrestadorServicoCadastro = {
                'pessoa_fisica': pessoa_fisica,
                'endereco': endereco,
                'setor': self.cleaned_data['uo'].setor,
                'ativo': True,
                'telefone': telefone,
            }
            prestador = PrestadorServico.update_or_create(dados, enviar_email=False)['prestador']
            professor.vinculo = prestador.get_vinculo()
            super().save(*args, **kwargs)
            professor_externo_ocupacao_padrao = Ocupacao.objects.filter(
                pk=Configuracao.get_valor_por_chave('edu', 'professor_externo_ocupacao_padrao') or 0
            ).first()
            professor_externo_dias_vencimento_contrato = int(
                Configuracao.get_valor_por_chave('edu', 'professor_externo_dias_vencimento_contrato') or '720'
            )
            professor_externo_pessoa_juridica = self.cleaned_data['uo'].get_pessoa_juridica()
            if professor_externo_ocupacao_padrao and professor_externo_pessoa_juridica and professor_externo_dias_vencimento_contrato:
                OcupacaoPrestador.objects.get_or_create(
                    prestador=prestador,
                    ocupacao=professor_externo_ocupacao_padrao,
                    empresa=professor_externo_pessoa_juridica,
                    data_inicio=datetime.date.today(),
                    data_fim=datetime.date.today() + datetime.timedelta(days=professor_externo_dias_vencimento_contrato),
                    setor_suap=self.cleaned_data['uo'].setor,
                )
        super().save(*args, **kwargs)
        return self.instance


class DisciplinaIngressoProfessorForm(forms.ModelFormPlus):
    disciplina = forms.ModelChoiceFieldPlus(
        Disciplina.objects.all(), label='Disciplina de Ingresso', widget=AutocompleteWidget(search_fields=Disciplina.SEARCH_FIELDS), required=True
    )

    class Meta:
        model = Professor
        fields = ('disciplina',)


class ExportarDadosPNP(forms.Form):
    ETNIA = 'Etnia dos alunos'
    INGRESSO = 'Forma de ingresso dos alunos'
    IDENTIDADE_GENERO = 'Identidade de gênero dos alunos'
    RENDA = 'Renda dos alunos'
    SITUACAO_MATRICULA = 'Situação de matrícula dos alunos'
    TIPO_DEFICIENCIA = 'Tipo de deficiência dos alunos'
    TIPO_NEE = 'Tipo de NEE dos alunos'
    TITULACAO = 'Titulação dos servidores'
    TURNO = 'Turno dos alunos'

    SUBMIT_STYLE = 'success dontdisable'

    tipo = forms.ChoiceField(
        label='Tipo',
        choices=[[x, x] for x in (ETNIA, INGRESSO, IDENTIDADE_GENERO, RENDA, SITUACAO_MATRICULA, TIPO_DEFICIENCIA, TIPO_NEE, TITULACAO, TURNO)],
    )
    codigos = forms.CharField(
        label='Códigos SISTEC',
        widget=forms.Textarea(),
        help_text='Informe os códigos SISTEC de aluno, cada um em uma linha separada.',
        required=False,
    )
    cpfs = forms.CharField(label='CPFs', widget=forms.Textarea(), help_text='Informe os CPFs, cada um em uma linha separada.', required=False)

    class Media:
        js = ['/static/edu/js/ExportarDadosPNP.js']

    def clean_cpfs(self):
        cpfs = self.cleaned_data['cpfs']
        tipo = self.cleaned_data['tipo']
        if not cpfs and tipo == ExportarDadosPNP.TITULACAO:
            raise forms.ValidationError('Este campo é obrigatório.')
        else:
            result = []
            for cpf in cpfs.split('\n'):
                if len(cpf.strip()) < 11:
                    cpf = cpf.strip().zfill(11)
                if len(cpf.strip()) != 11 and len(cpf.strip()) != 14:
                    raise forms.ValidationError(f'O CPF "{cpf}" é inválido')
                result.append(cpf)
            return result

    def clean_codigos(self):
        codigos = self.cleaned_data['codigos']
        tipo = self.cleaned_data['tipo']
        if not codigos and tipo != ExportarDadosPNP.TITULACAO:
            raise forms.ValidationError('Este campo é obrigatório.')
        return codigos

    def processar(self):
        def remover_pontuacao(cpf):
            return cpf.replace('.', '').replace('-', '') if cpf else ''

        tipo = self.cleaned_data['tipo']
        codigos = [cod.strip() for cod in self.cleaned_data['codigos'].split('\n')]
        cpfs = {mask_cpf(remover_pontuacao(cpf)) for cpf in self.cleaned_data['cpfs'] if cpf}

        if tipo == ExportarDadosPNP.TURNO:
            lista = [
                ['Matrícula', 'Turno do Aluno'],
            ]
        elif tipo == ExportarDadosPNP.INGRESSO:
            lista = [
                ['Matrícula', 'Cota'],
            ]
        elif tipo == ExportarDadosPNP.RENDA:
            lista = [['Matrícula', 'Faixa de Renda']]
        elif tipo == ExportarDadosPNP.ETNIA:
            lista = [['Matrícula', 'Cor/Raça']]
        elif tipo == ExportarDadosPNP.SITUACAO_MATRICULA:
            lista = [['Matrícula', 'Situação', 'Data da Ocorrência']]
        elif tipo == ExportarDadosPNP.TIPO_DEFICIENCIA:
            lista = [['Matrícula', 'Tipo de Deficiência']]
        elif tipo == ExportarDadosPNP.TIPO_NEE:
            lista = [['Matrícula', 'NEE']]
        elif tipo == ExportarDadosPNP.IDENTIDADE_GENERO:
            lista = [['Matrícula', 'Identidade de Gênero']]
        else:
            lista = [
                ['CPF', 'Valor'],
            ]

        if tipo == ExportarDadosPNP.RENDA and 'ae' in settings.INSTALLED_APPS:
            Caracterizacao = apps.get_model('ae', 'Caracterizacao')
            qs = Caracterizacao.objects.filter(aluno__codigo_sistec__in=codigos).order_by('-id')
            for caracterizacao in qs:
                cod = caracterizacao.aluno.codigo_sistec
                if cod in codigos:
                    renda_per_capita = caracterizacao.renda_per_capita
                    s = 'Nao Declarada'
                    if renda_per_capita is not None:
                        if renda_per_capita <= 0.5:
                            s = '0<RFP<=0,5'
                        elif renda_per_capita >= 0.5 and renda_per_capita <= 1.0:
                            s = '0,5<RFP<=1,0'
                        elif renda_per_capita >= 1.0 and renda_per_capita <= 1.5:
                            s = '1,0<RFP<=1,5'
                        elif renda_per_capita >= 1.5 and renda_per_capita <= 2.5:
                            s = '1,5<RFP<=2,5'
                        elif renda_per_capita >= 2.5 and renda_per_capita <= 3.5:
                            s = '2,5<RFP<=3,5'
                        elif renda_per_capita >= 3.5:
                            s = 'RFP>3,5'
                    lista.append([cod, s])
                    codigos.remove(cod)
            for cod in codigos:
                lista.append([cod, 'Nao Declarada'])
        elif tipo == ExportarDadosPNP.ETNIA and 'ae' in settings.INSTALLED_APPS:
            Caracterizacao = apps.get_model('ae', 'Caracterizacao')

            carac_recente = (
                Caracterizacao.objects.filter(
                    aluno__codigo_sistec=OuterRef('codigo_sistec'),
                    raca__isnull=False,
                )
                .exclude(raca__descricao='Não declarado')
                .order_by('-id')
            )

            alunos_qs = (
                Aluno.objects.filter(codigo_sistec__in=set(codigos))
                .prefetch_related('vinculos__raca')  # ponytail: raca migrada p/ Vinculo; select_related/only incompatíveis c/ GenericRelation
                .annotate(
                    raca_carac=Subquery(carac_recente.values('raca__descricao')[:1]),
                )
            )

            map_alunos = {a.codigo_sistec: a for a in alunos_qs}
            alunos_nao_encontrados = []
            for cod in codigos:
                aluno = map_alunos.get(cod)
                if not aluno:
                    alunos_nao_encontrados.append(cod)
                    continue

                if aluno.raca_carac:  # Prioridade 1: Caracterizacao
                    etnia = aluno.raca_carac
                elif aluno.raca and aluno.raca.descricao != 'Não declarado':  # Fallback 1: raça no vínculo
                    etnia = aluno.raca.descricao
                else:
                    etnia = 'Não Declarada'
                lista.append([cod, retira_acentos(etnia)])

            if alunos_nao_encontrados:
                lista.append(['Matrícula não localizada'])
                for cod in alunos_nao_encontrados:
                    lista.append([cod])

        elif tipo == ExportarDadosPNP.TITULACAO:
            qs = Servidor.objects.ativos().filter(cpf__in=cpfs)
            rsc = ''
            for cpf, nome_siape, nome_suap, titulacao_edu, nivel_escolaridade in qs.values_list(
                'cpf', 'titulacao__nome', 'titulacao__titulo_masculino', 'professor__titulacao', 'nivel_escolaridade__nome'
            ):
                if nome_siape:
                    if 'RSC-I ' in nome_siape:
                        rsc = 'RSC-I'
                    elif 'RSC-II ' in nome_siape:
                        rsc = 'RSC-II'
                    elif 'RSC-III ' in nome_siape:
                        rsc = 'RSC-III'
                titulacao = (nome_suap or titulacao_edu or nivel_escolaridade or 'Nao Declarada').upper()
                if 'FUNDAMENTAL' in titulacao:
                    titulacao = 'ENSINO FUNDAMENTAL'
                if 'MÉDIO' in titulacao or 'MEDIO' in titulacao:
                    titulacao = 'ENSINO MEDIO'
                if 'TÉCNICO' in titulacao or 'TECNICO' in titulacao:
                    titulacao = 'TECNICO'
                if 'GRADUA' in titulacao:
                    titulacao = 'GRADUACAO'
                if 'APERFEI' in titulacao:
                    titulacao = 'APERFEICOAMENTO'
                if 'ESPECIAL' in titulacao:
                    titulacao = 'ESPECIALIZACAO'
                if 'MESTR' in titulacao:
                    titulacao = 'MESTRADO'
                if 'DOUTOR' in titulacao:
                    titulacao = 'DOUTORADO'
                if ('PÓS' in titulacao or 'POS' in titulacao) and 'DOUTOR' in titulacao:
                    titulacao = 'POS-DOUTORADO'
                lista.append([remover_pontuacao(cpf), titulacao, rsc])
        elif tipo == ExportarDadosPNP.INGRESSO:
            for aluno in (
                Aluno.objects.filter(codigo_sistec__in=codigos)
                .distinct()
                .select_related('forma_ingresso', 'pessoa_fisica', 'matriz__estrutura')
                .only(
                    'matricula', 'codigo_sistec', 'forma_ingresso__descricao', 'pessoa_fisica__cpf', 'matriz__estrutura__proitec', 'data_inicio_ciclo'
                )
            ):
                descricao = aluno.forma_ingresso.descricao if aluno.forma_ingresso else 'AC'

                if aluno.is_proitec():
                    descricao = 'L5' if aluno.data_inicio_ciclo.year < 2024 else 'LI_EP'

                matricula_atual = aluno.matricula
                while 'transfer' in descricao.lower():
                    descricao, matricula_atual = self.get_matricula_original(matricula_atual)

                if '-' in descricao:
                    descricao = descricao.split('-')[0].strip()

                # de/para ciclo 2024
                ano_inicio = aluno.data_inicio_ciclo.year if aluno.data_inicio_ciclo else aluno.ano_letivo.ano
                if ano_inicio >= 2024:
                    if descricao == 'L1':
                        descricao = 'LB_EP'
                    elif descricao == 'L2':
                        descricao = 'LB_PPI'
                    elif descricao == 'L5':
                        descricao = 'LI_EP'
                    elif descricao == 'L6':
                        descricao = 'LI_PPI'
                    elif descricao == 'L9' or descricao == 'L10':
                        descricao = 'LB_PCD'
                    elif descricao == 'L13' or descricao == 'L14':
                        descricao = 'LI_PCD'

                if descricao not in [
                    'AC',
                    'L1',
                    'L2',
                    'L5',
                    'L6',
                    'L9',
                    'L10',
                    'L13',
                    'L14',
                    'LB_EP',
                    'LB_PCD',
                    'LB_PPI',
                    'LB_Q',
                    'LI_EP',
                    'LI_PCD',
                    'LI_PPI',
                    'LI_Q',
                ]:
                    descricao = 'AC'

                lista.append([aluno.codigo_sistec, descricao])
        elif tipo == ExportarDadosPNP.TURNO:
            for aluno in Aluno.objects.filter(codigo_sistec__in=set(codigos)).select_related('turno').only('codigo_sistec', 'turno__descricao'):
                descricao = aluno.turno.descricao if aluno.turno else ' '
                lista.append([aluno.codigo_sistec, descricao])
        elif tipo == ExportarDadosPNP.SITUACAO_MATRICULA:
            ano = datetime.date.today().year
            situacoes_ignoradas = [
                SituacaoMatricula.AGUARDANDO_SEMINARIO,
                SituacaoMatricula.CONCLUDENTE,
                SituacaoMatricula.ESTAGIARIO_CONCLUDENTE,
                SituacaoMatricula.INTERCAMBIO,
                SituacaoMatricula.MATRICULADO,
                SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                SituacaoMatricula.TRANCADO,
                SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
            ]

            situacoes_map = {situacao.descricao: situacao.id for situacao in SituacaoMatricula.objects.all()}
            alunos_em_curso = []
            for aluno in Aluno.objects.filter(codigo_sistec__in=codigos, data_matricula__year__lt=ano).only(
                'id', 'situacao_id', 'codigo_sistec', 'dt_conclusao_curso', 'data_matricula'
            ):
                if (
                    aluno.situacao_id in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]
                    and aluno.dt_conclusao_curso
                    and aluno.dt_conclusao_curso.year < ano
                ):
                    situacao = 'CONCLUÍDA'
                    data = aluno.dt_conclusao_curso
                elif aluno.situacao_id == SituacaoMatricula.NAO_CONCLUIDO and aluno.dt_conclusao_curso and aluno.dt_conclusao_curso.year < ano:
                    situacao = 'ABANDONO'
                    data = aluno.dt_conclusao_curso
                else:
                    situacao = 'NÃO DECLARADA'
                    rd = (
                        RegistroDiferenca.objects.filter(
                            log__ref=aluno.id,
                            log__nome_modelo='Aluno',
                            log__dt__year__lt=ano,
                            campo='Situação',
                            log__tipo=Log.EDICAO,
                        )
                        .order_by('id')
                        .select_related('log')
                        .only('valor_atual', 'log__dt')
                        .last()
                    )
                    if rd:
                        data = rd.log.dt
                        situacao_id = situacoes_map[rd.valor_atual]
                    else:
                        # aluno não teve situação alterada desde a matrícula
                        alunos_em_curso.append([aluno.codigo_sistec, aluno.data_matricula, aluno.eh_aluno_minicurso()])
                        continue
                    if situacao_id in situacoes_ignoradas:
                        alunos_em_curso.append([aluno.codigo_sistec, data, aluno.eh_aluno_minicurso()])
                        continue
                    elif situacao_id in [SituacaoMatricula.EVASAO, SituacaoMatricula.AFASTADO, SituacaoMatricula.NAO_CONCLUIDO]:
                        situacao = 'ABANDONO'
                    elif situacao_id == SituacaoMatricula.TRANSFERIDO_INTERNO:
                        situacao = 'TRANSF_INT'
                    elif situacao_id == SituacaoMatricula.TRANSFERIDO_EXTERNO:
                        situacao = 'TRANSF_EXT'
                    elif situacao_id in [
                        SituacaoMatricula.CONCLUIDO,
                        SituacaoMatricula.EGRESSO,
                        SituacaoMatricula.FORMADO,
                        SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
                        SituacaoMatricula.AGUARDANDO_ENADE,
                    ]:
                        situacao = 'CONCLUÍDA'
                    elif situacao_id in [
                        SituacaoMatricula.FALECIDO,
                        SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                        SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
                        SituacaoMatricula.JUBILADO,
                    ]:
                        situacao = 'DESLIGADA'
                    elif situacao_id == SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE:
                        situacao = 'EXCLUÍDO'
                    elif situacao_id == SituacaoMatricula.CANCELADO:
                        situacao = 'CANCELADA'
                    elif situacao_id == SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO:
                        situacao = 'INTEGRALIZADA'

                lista.append([aluno.codigo_sistec, situacao, data.strftime('%d/%m/%Y')])
            if alunos_em_curso:
                lista.append(['Matrícula', 'Situação', 'Data da Ocorrência', 'Frequência'])
                for aluno in alunos_em_curso:
                    codigo_sistec = aluno[0]
                    data = aluno[1]
                    aluno_minicurso = aluno[2]
                    cursou_diario = MatriculaDiario.objects.filter(
                        matricula_periodo__aluno__codigo_sistec=codigo_sistec, matricula_periodo__ano_letivo__ano=ano - 1
                    ).exists()
                    tem_frequencia = 'SIM' if cursou_diario or aluno_minicurso else 'NÃO'
                    lista.append([codigo_sistec, 'EM_CURSO', data.strftime('%d/%m/%Y'), tem_frequencia])
        elif tipo == ExportarDadosPNP.TIPO_DEFICIENCIA:
            for aluno in Aluno.objects.filter(codigo_sistec__in=codigos).only('codigo_sistec'):
                descricao = 'Não possui deficiência'

                if aluno.is_pcd():
                    deficiencias = aluno.get_deficiencias_educacenso()
                    if not deficiencias:
                        descricao = 'Não declarado'
                    elif len(deficiencias) > 1:
                        descricao = 'Pessoa com Deficiência Múltipla'
                    else:
                        deficiencia = next(iter(deficiencias))
                        if deficiencia in [Deficiencia.BAIXA_VISAO, Deficiencia.VISAO_MONOCULAR, Deficiencia.CEGUEIRA]:
                            descricao = 'Pessoa com Deficiência Visual'
                        elif deficiencia in [
                            Deficiencia.DEFICIENCIA_AUDITIVA,
                            Deficiencia.SURDEZ,
                        ]:
                            descricao = 'Pessoa com Deficiência Auditiva'
                        elif deficiencia == Deficiencia.DEFICIENCIA_FISICA:
                            descricao = 'Pessoa com Deficiência Física'
                        elif deficiencia == Deficiencia.DEFICIENCIA_INTELECTUAL:
                            descricao = 'Pessoa com Deficiência Intelectual'
                        elif deficiencia == Deficiencia.SURDOCEGUEIRA:
                            descricao = 'Pessoa com Deficiência Múltipla'
                        elif deficiencia == Deficiencia.TEA:
                            descricao = 'Transtorno do Espectro Autista (TEA)'

                lista.append([aluno.codigo_sistec, descricao])
        elif tipo == ExportarDadosPNP.TIPO_NEE:
            for aluno in Aluno.objects.filter(codigo_sistec__in=codigos).only('codigo_sistec'):
                descricao = 'Não possui NEE'
                qs_deficiencias = aluno.deficiencias.filter(classificacao_educacenso=Deficiencia.TEA)
                qs_nees = aluno.outras_nees.filter(classificacao_educacenso__isnull=False)
                if qs_nees.exists() or qs_deficiencias.exists():
                    nees = set(qs_nees.values_list('classificacao_educacenso', flat=True))
                    deficiencias = set(qs_deficiencias.values_list('classificacao_educacenso', flat=True))
                    if len(deficiencias) + len(nees) > 1:
                        descricao = 'Múltiplas NEE'
                    else:
                        if deficiencias:
                            descricao = 'Transtorno do Espectro Autista (TEA)'
                        elif nees:
                            nee = next(iter(nees))
                            if nee == TipoNEE.ALTAS_HABILIDADES:
                                descricao = 'Altas Habilidades/Superdotação (AH/SD)'
                            elif nee in [TipoNEE.DISCALCULIA, TipoNEE.DISGRAFIA, TipoNEE.DISLALIA, TipoNEE.DISLEXIA]:
                                descricao = 'Transtornos Específicos de Aprendizagem'
                            elif nee == TipoNEE.TDAH:
                                descricao = 'Transtorno de Déficit de Atenção e Hiperatividade (TDAH)'
                            else:
                                descricao = 'Outras NEE'
                lista.append([aluno.codigo_sistec, descricao])
        elif tipo == ExportarDadosPNP.IDENTIDADE_GENERO:
            for aluno in (
                Aluno.objects.filter(codigo_sistec__in=codigos).select_related('pessoa_fisica').only('codigo_sistec', 'pessoa_fisica__genero')
            ):
                genero = aluno.pessoa_fisica.genero
                descricao = 'Não Declarada'
                if genero == PessoaFisica.GENERO_MASCULINO:
                    descricao = 'Homem Cisgênero'
                elif genero == PessoaFisica.GENERO_HOMEM_TRANS:
                    descricao = 'Homem Transgênero'
                elif genero == PessoaFisica.GENERO_FEMININO:
                    descricao = 'Mulher Cisgênero'
                elif genero in [PessoaFisica.GENERO_MULHER_TRANS, PessoaFisica.GENERO_TRAVESTI]:
                    descricao = 'Mulher Transgênero'
                elif genero == PessoaFisica.GENERO_NAO_BINARIO:
                    descricao = 'Pessoa Não Binária'
                lista.append([aluno.codigo_sistec, descricao])
        return CsvResponse(lista, delimiter=';')

    def get_matricula_original(self, matricula_atual):
        descricao = 'AC'
        matricula_anterior = ''
        pm = (
            ProcedimentoMatricula.objects.filter(nova_matricula=matricula_atual)
            .select_related('matricula_periodo__aluno__forma_ingresso')
            .only('matricula_periodo__aluno__forma_ingresso__descricao', 'matricula_periodo__aluno__matricula')
            .first()
        )
        if pm:
            descricao = pm.matricula_periodo.aluno.forma_ingresso.descricao
            matricula_anterior = pm.matricula_periodo.aluno.matricula

        return descricao, matricula_anterior


class InformarDadosTitulacaoForm(forms.ModelFormPlus):
    ALERT = 'De acordo com a exigência do Censo da Educação Básica (EDUCACENSO) 2022 é necessário informar a sua titulação mais elevada, instituição onde obteve a titulação, área de conhecimento e ano de conclusão.'

    titulacao = forms.ChoiceField(label='Titulação', choices=[['', '-----'], *Professor.TITULACAO_CHOICES], required=True)
    ultima_instituicao_de_titulacao = forms.CharFieldPlus(label='Instituição', required=True, help_text='Instituição onde recebeu a última titulação')
    area_ultima_titulacao = forms.ChoiceField(
        label='Área da Última Titulação', required=True, choices=[['', '-----'], *Professor.AREA_ULTIMA_TITULACAO_CHOICES]
    )
    ano_ultima_titulacao = forms.ModelChoiceField(Ano.objects, label='Ano', required=True, help_text='Ano em que obteu a última titulação')

    class Meta:
        model = Professor
        fields = 'titulacao', 'ultima_instituicao_de_titulacao', 'area_ultima_titulacao', 'ano_ultima_titulacao'


class ParticipacaoBancaForm(forms.FormPlus):
    METHOD = 'POST'
    ORDERNAR_POR_CHOICES = [
        ['matricula_periodo__ano_letivo__ano', 'Ano Letivo'],
        ['tipo', 'Tipo'],
        ['titulo', 'Título'],
        ['nota', 'Nota'],
        ['resultado_data', 'Data da Apresentação'],
    ]
    TIPO_ORDENACAO_CHOICES = [['', 'Crescente'], ['-', 'Decrescente']]
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=False)
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=[['', '----'], *PERIODO_LETIVO_CHOICES], required=False)
    tipo = forms.ChoiceField(choices=[['', '----'], *ProjetoFinal.TIPO_PROJETO_CHOICES], required=False)
    data_inicio = forms.DateFieldPlus(label='Data Inicial da Apresentação', required=False)
    data_fim = forms.DateFieldPlus(label='Data Final da Apresentação', required=False)
    ordenar_por = forms.ChoiceField(choices=ORDERNAR_POR_CHOICES, required=False)
    tipo_ordenacao = forms.ChoiceField(choices=TIPO_ORDENACAO_CHOICES, initial='', required=False)


class ConfiguracaoDadosDocentesForm(forms.ModelFormPlus):
    modo_exibicao = forms.ChoiceField(label='Modo de exibição', choices=ConfiguracaoDadosDocentes.EXIBICAO_CHOICES, required=True)
    senha_confirmacao = forms.PasswordField(label='Confirme sua senha', required=True)

    fieldsets = (
        ('Configuração de exibição', {'fields': ('modo_exibicao',)}),
        (
            'Detalhes',
            {
                'fields': (
                    'exibir_foto',
                    'exibir_email',
                    'exibir_lattes',
                    'instagram_url',
                    'facebook_url',
                    'youtube_url',
                    'linkedin_url',
                    'spotify_url',
                ),
                'classes': ('detalhes',),
            },
        ),
        (
            'Termos de responsabilidade',
            {
                'fields': ('atesto_responsabilidade_autor', 'atesto_responsabilidade_terceiros', 'atesto_responsabilidade_instituicao'),
                'classes': ('termos-responsabilidade',),
            },
        ),
        ('Confirmação', {'fields': ('senha_confirmacao',)}),
    )

    class Meta:
        model = ConfiguracaoDadosDocentes
        exclude = ('professor', 'datahora_publicacao', 'slug')

    class Media:
        js = ['/static/edu/js/ConfiguracaoDadosDocentesForm.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['autocomplete'] = 'off'

    def clean(self):
        cleaned = super().clean()

        if cleaned.get('modo_exibicao') == 'COMPLETA':
            for campo in [
                'atesto_responsabilidade_autor',
                'atesto_responsabilidade_terceiros',
                'atesto_responsabilidade_instituicao',
            ]:
                if not cleaned.get(campo):
                    self.add_error(campo, 'Este campo é obrigatório para exibição completa.')

        return cleaned
