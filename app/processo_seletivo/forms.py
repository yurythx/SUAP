import operator
from datetime import datetime
from functools import reduce
from xml.dom import minidom

from django.db.models import Q

from comum.models import Ano, Vinculo
from comum.utils import get_uo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import in_group
from djtools.utils import running_tests
from edu.models import PERIODO_LETIVO_CHOICES, Aluno, CursoCampus, LinhaPesquisa, Matriz
from processo_seletivo import importacao, tasks
from processo_seletivo.models import (
    Candidato,
    CandidatoVaga,
    ConfiguracaoMigracaoVaga,
    CriacaoClassificacao,
    CriacaoVagaRemanescente,
    Edital,
    EditalAdesao,
    EditalAdesaoCampus,
    EditalPeriodoLiberacao,
    ImportacaoCSV,
    InscricaoFiscal,
    Lista,
    OfertaVagaCurso,
    PrecedenciaMigracao,
    RegistroAjusteCriacaoVagaRemanescente,
    RotuloLista,
    Vaga,
    WebService,
)
from rh.models import Servidor, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    permite_remanejar_geral = forms.BooleanField(
        label='Permite Remanejar',
        help_text='Marque essa opção caso deseje permitir que candidados inaptos a se matricularem em uma lista/cota possam ser remanejados para a lista geral ou ampla concorrência.',
        required=False,
    )


class EditalForm(forms.ModelFormPlus):
    class Meta:
        models = Edital
        fields = (
            'ano',
            'semestre',
            'codigo',
            'descricao',
            'configuracao_migracao_vagas',
            'matricula_no_polo',
            'matricula_online',
            'permite_adicionar_vagas_extras',
        )

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('ano'),
                    ('semestre', 'codigo'),
                    'descricao',
                    ('matricula_online', 'permite_adicionar_vagas_extras', 'permite_adicionar_candidato_classificacao'),
                )
            },
        ),
        ('Migração de Vagas', {'fields': ('configuracao_migracao_vagas',)}),
        ('EAD', {'fields': ('matricula_no_polo',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codigo'].initial = 0
        if (
            not self.instance.id
            or not Candidato.objects.filter(edital=self.instance).exclude(campus_polo__isnull=True).exclude(campus_polo='').exists()
        ):
            self.fieldsets = self.fieldsets[:-1]

    def save(self, *args, **kwargs):
        if not self.instance.pk:
            self.instance.qtd_vagas = 0
            self.instance.qtd_inscricoes = 0
            self.instance.qtd_inscricoes_confirmadas = 0
            self.instance.detalhamento_por_campus = '{}'
        return super().save(commit=True)

    def save_m2m(self):
        pass


class EditalLiberacaoForm(forms.ModelFormPlus):
    class Meta:
        model = EditalPeriodoLiberacao
        fields = (
            'uo',
            'data_inicio_matricula',
            'data_fim_matricula',
            'data_limite_avaliacao',
            'introducao_notifiacao_matricula',
            'detalhamento_notifiacao_matricula',
        )

    fieldsets = (
        ('Dados gerais', {'fields': ('uo',)}),
        ('Período de Matrícula e Avaliação', {'fields': (('data_inicio_matricula', 'data_fim_matricula', 'data_limite_avaliacao'),)}),
        ('Notificação de Matrícula', {'fields': ('introducao_notifiacao_matricula', 'detalhamento_notifiacao_matricula')}),
    )

    def __init__(self, *args, **kwargs):
        edital = kwargs.pop('edital')
        uos_edital = kwargs.pop('uos_edital')
        uos_cadastradas = list(EditalPeriodoLiberacao.objects.filter(edital=edital).values_list('uo', flat=True))

        super().__init__(*args, **kwargs)

        if self.instance.pk:
            if self.instance.uo_id in uos_cadastradas:
                uos_cadastradas.remove(self.instance.uo_id)

        self.instance.edital = edital
        self.instance.usuario = self.request.user

        if self.instance.pk:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(pk=self.instance.uo_id)
        else:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(pk__in=uos_edital).exclude(pk__in=uos_cadastradas)


class EditalAusentarCandidatosForm(forms.FormPlus):
    campus = forms.ModelChoiceFieldPlus(label='Campus', required=True, queryset=UnidadeOrganizacional.objects)
    chamada = forms.ChoiceField(label='Número da Chamada', required=True)
    confirmacao = forms.BooleanField(label='Confirma o Processamento?', required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        edital = kwargs.pop('edital')
        super().__init__(*args, **kwargs)

        candidatos_vaga = (
            CandidatoVaga.objects.filter(candidato__edital=edital, situacao__isnull=True, convocacao__isnull=False)
            .values('convocacao')
            .order_by()
            .distinct()
        )

        self.fields['chamada'].choices = [[x['convocacao'], x['convocacao']] for x in candidatos_vaga]

        if in_group(self.request.user, 'Administrador Acadêmico'):
            uos = OfertaVagaCurso.locals.filter(edital=edital).values_list('curso_campus__diretoria__setor__uo', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(pk__in=uos)
        else:
            vinculo = self.request.user.get_vinculo()
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(pk=vinculo.setor.uo_id)


class ImportarEditalXMLForm(forms.FormPlus):
    xml = forms.FileFieldPlus(label='Arquivo XML', max_file_size=100 * 1024 * 1024, required=True)

    fieldsets = (('Importação', {'fields': ('xml',)}),)

    def processar(self, edital):
        xml = self.cleaned_data.get('xml')
        Aluno.objects.filter(candidato_vaga__oferta_vaga__oferta_vaga_curso__edital=edital).update(candidato_vaga=None)
        edital.lista_set.all().delete()
        edital.ofertavagacurso_set.all().delete()
        edital.candidato_set.all().delete()
        return tasks.importar_edital(xml.read().decode(), edital)


class ImportarEditalCSVForm(forms.ModelFormPlus):
    arquivo_listas = forms.FileFieldPlus(label='Arquivo de Listas', required=True, help_text='Deve conter as seguintes colunas: SIGLA e DESCRICAO.')
    arquivo_vagas = forms.FileFieldPlus(
        label='Arquivo de Vagas',
        required=True,
        help_text='Deve conter as seguintes colunas: COD_CURSO_SUAP, LINHA_PESQUISA, LISTA, VAGAS, QTD_INSCRITOS, TURNO e POLO.',
    )
    arquivo_candidatos = forms.FileFieldPlus(
        label='Arquivo de Candidatos',
        required=True,
        help_text='Deve conter as seguintes colunas: INSCRICAO, CPF, EMAIL, TELEFONE, NOME, COD_CURSO_SUAP, TURNO e POLO.',
    )
    arquivo_resultado = forms.FileFieldPlus(
        label='Arquivo de Resultado',
        help_text='Deve conter as seguintes colunas: INSCRICAO, COD_CURSO_SUAP, LISTA, TURNO, CLASSIFICACAO, APROVADO, ELIMINADO, POLO e LINHA_PESQUISA.',
    )
    arquivo_dados_pessoais = forms.FileFieldPlus(
        label='Arquivo de Dados Pessoais',
        help_text='Deve conter as seguintes colunas: NOME, NOME_MAE, NOME_PAI, GENERO, DATA_NASCIMENTO, CPF, RG, RG_DATA_EMISSAO, RG_ORGAO_EMISSOR, RG_UF, EMAIL, DDD_FONE1, FONE1, DDD_FONE2, FONE2, CEP, LOGRADOURO, NUMERO, BAIRRO, COMPLEMENTO, MUNICIPIO_ENDERECO, UF_ENDERECO.',
    )

    fieldsets = (('Arquivos', {'fields': ('arquivo_listas', 'arquivo_vagas', 'arquivo_candidatos', 'arquivo_resultado', 'arquivo_dados_pessoais')}),)

    class Meta:
        model = ImportacaoCSV
        fields = 'arquivo_listas', 'arquivo_vagas', 'arquivo_candidatos', 'arquivo_resultado', 'arquivo_dados_pessoais'

    def __init__(self, *args, **kwargs):
        self.xml = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        codigos, xml = importacao.processar_arquivos(
            cleaned_data['arquivo_listas'],
            cleaned_data['arquivo_vagas'],
            cleaned_data['arquivo_candidatos'],
            cleaned_data['arquivo_resultado'],
        )
        existentes = CursoCampus.objects.filter(codigo__in=codigos).values_list('codigo', flat=True)
        inexistentes = set(codigos) - set(existentes)
        if inexistentes:
            raise forms.ValidationError(f'Não existem cursos com o(s) código(s) {inexistentes} cadastrados no SUAP.')
        else:
            self.xml = xml
        return cleaned_data

    def processar(self, edital):
        self.instance.edital = edital
        super().save()
        return tasks.importar_edital(self.xml, edital)


class EditarOfertaVagaCursoForm(forms.ModelFormPlus):
    curso_campus = forms.ModelChoiceFieldPlus(CursoCampus.objects, label='Curso')

    class Meta:
        model = OfertaVagaCurso
        fields = ('curso_campus',)

    def save(self, *args, **kwargs):
        retorno = super().save(*args, **kwargs)
        Candidato.objects.filter(candidatovaga__oferta_vaga__oferta_vaga_curso=self.instance).update(curso_campus=self.instance.curso_campus)
        return retorno


class ImportarEditalForm(FormWizardPlus):
    ano = forms.ModelChoiceField(Ano.objects.all(), label='Ano', required=True)
    semestre = periodo_letivo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Semestre', required=True)
    webservice = forms.ModelChoiceField(WebService.objects.all(), label='WebService', required=True)
    configuracao_migracao_vagas = forms.ModelChoiceField(ConfiguracaoMigracaoVaga.objects.all(), required=False)

    edital = forms.ChoiceField(choices=[], label='Edital', widget=forms.Select(attrs={'style': 'width:600px'}))

    steps = (
        [
            ('Fonte de Dados', {'fields': ('webservice',)}),
            ('Período Letivo', {'fields': ('ano', 'semestre')}),
            ('Migração de Vagas Remanescentes', {'fields': ('configuracao_migracao_vagas',)}),
        ],
        [('Seleção do Edital', {'fields': ('edital',)})],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def next_step(self):
        if 'edital' in self.fields:
            self.fields['edital'].choices = self.get_editais_choices()

    def clean(self):
        return self.cleaned_data

    def clean_edital(self):
        codigo_edital = self.cleaned_data['edital']
        descricao_edital = dict(self.fields['edital'].choices)[int(codigo_edital)]
        webservice = self.get_entered_data('webservice')
        if len(descricao_edital) > 255:
            raise forms.ValidationError(
                f'Descrição do edital muito longa. Reduza para até 255 caracteres a descrição deste edital no {webservice.descricao}.'
            )
        try:
            self.xml = webservice.edital(codigo_edital)
            doc = minidom.parseString(self.xml)
        except Exception:
            raise forms.ValidationError('Problemas ao tentar conectar com o Sistema de Gerenciamento de Concursos (SGC) ou equivalente.')

        codigos_cursos = []
        codigos_cursos_invalidos = []
        linhas_pesquisa = []
        # Busca apenas em tags <vaga> para evitar percorrer milhares de candidatos
        for _vaga in doc.getElementsByTagName('vaga'):
            codigo_curso_elem = _vaga.getElementsByTagName('codigo-curso')
            if codigo_curso_elem:
                codigo_curso = codigo_curso_elem[0].firstChild and codigo_curso_elem[0].firstChild.nodeValue or 0
                codigos_cursos.append(codigo_curso)

            linha_pesquisa_elem = _vaga.getElementsByTagName('linha-pesquisa')
            if linha_pesquisa_elem:
                linha_pesquisa = linha_pesquisa_elem[0].firstChild and linha_pesquisa_elem[0].firstChild.nodeValue or 0
                if linha_pesquisa:
                    # se falhar na conversão para inteiro adiciona como string para validação posterior
                    try:
                        linhas_pesquisa.append(int(linha_pesquisa))
                    except ValueError, TypeError:
                        linhas_pesquisa.append(linha_pesquisa)

        # Validação de cursos: uma única query com __in em vez de N queries
        codigos_unicos = set(codigos_cursos)
        if codigos_unicos:
            codigos_existentes = set(CursoCampus.objects.filter(codigo__in=codigos_unicos).values_list('codigo', flat=True))
            codigos_cursos_invalidos = [str(c) for c in codigos_unicos - codigos_existentes]
            if codigos_cursos_invalidos:
                raise forms.ValidationError(
                    f'Os cursos com códigos {codigos_cursos_invalidos} cadastrados no sistema de gerenciamento de concurso não possuem cursos correspondentes no SUAP. Cadastre-os antes de realizar a importação.'
                )

        # Validação de linhas de pesquisa: uma única query com __in
        linhas_pesquisa_invalidas = []
        linhas_uniques = set(linhas_pesquisa)
        if running_tests():
            linhas_uniques = set(LinhaPesquisa.objects.all().values_list('pk', flat=True))

        if linhas_uniques:
            linhas_existentes = set(LinhaPesquisa.objects.filter(pk__in=linhas_uniques).values_list('pk', flat=True))
            linhas_pesquisa_invalidas = [str(linha) for linha in linhas_uniques - linhas_existentes]

        if linhas_pesquisa_invalidas:
            linhas_str = ', '.join(linhas_pesquisa_invalidas)
            raise forms.ValidationError(
                f'As linhas de pesquisa com códigos {linhas_str} cadastrados no sistema de gerenciamento de concurso não possuem linha de pesquisa correspondentes no SUAP. Cadastre-os no suap antes de realizar a importação.'
            )

        return codigo_edital

    def get_editais_choices(self):
        """
        Este método retorna um choices contendo todos os editais disponibilizados pelo webservices do SGC. O usuário irá
        escolhar um dos editais para ser importado.

        Abaixo temos um exemplo do XML retornado pelo serviço do SGC que retornar os editais.

        <editais>
            <edital>
                <codigo>39</codigo>
                <descricao>EDITAL N 09/2016-PROEN/IFRN - Aperfeiçoamento para Professores dos Municípios do Rio Grande do Norte (CAPROM)</descricao>
                <ano>2016</ano>
                <semestre>1</semestre>
                <remanescentes>Não</remanescentes>
                <sisu>Não</sisu>
                <qtd_vagas>60</qtd_vagas>
                <qtd_inscricoes>153</qtd_inscricoes>
                <qtd_inscricoes_confirmadas>24</qtd_inscricoes_confirmadas>
                <detalhamento_por_campus>
                    [{"qtd_inscricoes": 125, "suap_unidade_organizacional_id": "14", "campus": "EaD", "qtd_inscricoes_confirmadas": 18, "qtd_vagas": 30}, {"qtd_inscricoes": 28, "suap_unidade_organizacional_id": "14", "campus": "Polo SC", "qtd_inscricoes_confirmadas": 6, "qtd_vagas": 30}]
                </detalhamento_por_campus>
            </edital>
            <edital>
            ...
            </edital>
        </editais>


        :return:
        """

        self.editais_disponiveis_webservices = {}

        lista = []
        ano_selecionado = self.get_entered_data('ano')
        semestre_selecionado = self.get_entered_data('semestre')
        if ano_selecionado and semestre_selecionado:
            semestre_selecionado = int(semestre_selecionado)
            if self.get_entered_data('webservice') and self.get_entered_data('webservice').url_editais:
                xml = self.get_entered_data('webservice').editais()
                doc = minidom.parseString(xml)
                for _edital in doc.getElementsByTagName('edital'):
                    codigo = _edital.getElementsByTagName('codigo')[0].firstChild.nodeValue
                    ano = _edital.getElementsByTagName('ano')[0].firstChild.nodeValue
                    semestre = _edital.getElementsByTagName('semestre')[0].firstChild.nodeValue
                    remanescentes = _edital.getElementsByTagName('remanescentes')[0].firstChild.nodeValue == 'Sim'

                    sisu = _edital.getElementsByTagName('sisu')[0].firstChild.nodeValue == 'Sim'
                    qtd_vagas = _edital.getElementsByTagName('qtd_vagas')[0].firstChild.nodeValue
                    qtd_inscricoes = _edital.getElementsByTagName('qtd_inscricoes')[0].firstChild.nodeValue
                    qtd_inscricoes_confirmadas = _edital.getElementsByTagName('qtd_inscricoes_confirmadas')[0].firstChild.nodeValue
                    detalhamento_por_campus = _edital.getElementsByTagName('detalhamento_por_campus')[0].firstChild.nodeValue

                    # Se o _edital corrente tiver o mesmo ano e semestre especificados pelo usuário, então ele será montada
                    # uma descrição e este edital estará dispoível para seleção.
                    if (not ano_selecionado or str(ano) == str(ano_selecionado.ano)) and (
                        not semestre_selecionado or str(semestre) == str(semestre_selecionado)
                    ):
                        if _edital.getElementsByTagName('descricao')[0].firstChild:
                            descricao = '{} de {}/{}'.format(_edital.getElementsByTagName('descricao')[0].firstChild.nodeValue, ano, semestre)
                        else:
                            descricao = f'Edital {codigo} de {ano}/{semestre}'
                        lista.append([int(codigo), '{} {}'.format(descricao, remanescentes and '(Vagas Remanescentes)' or '')])

                        # Criando um objeto Edital sem persistí-lo.
                        edital_add = Edital(
                            codigo=codigo,
                            descricao=descricao,
                            remanescentes=remanescentes,
                            sisu=sisu,
                            qtd_vagas=qtd_vagas,
                            qtd_inscricoes=qtd_inscricoes,
                            qtd_inscricoes_confirmadas=qtd_inscricoes_confirmadas,
                            detalhamento_por_campus=detalhamento_por_campus,
                        )
                        # Adicionando o objeto Edital dentro do dicionário que irá armzenar todos os editais disponíveis
                        # para a seleção pelo usuário.
                        self.editais_disponiveis_webservices[codigo] = edital_add

        return lista

    def processar(self, request):
        # Campos do formulário
        codigo_edital = self.cleaned_data['edital']
        configuracao_migracao_vagas = self.cleaned_data['configuracao_migracao_vagas']
        ano = self.cleaned_data['ano']
        semestre = int(self.cleaned_data['semestre'])
        webservice = self.cleaned_data['webservice']

        # Edital "não persistido" selecionado.
        edital_selecionado_webservice = self.editais_disponiveis_webservices[codigo_edital]
        # Complementando algumas informações do Edital "não persistido" selecionado para que ele possa ser persistido
        # mais tarde, seja via INSERT ou UPDATE.
        edital_selecionado_webservice.ano = ano
        edital_selecionado_webservice.semestre = semestre
        edital_selecionado_webservice.webservice = webservice
        # Verificando se o edital já encontra-se persistido. Se sim, ocorrerá uma atualização dos dados, caso contrário
        # uma inserção. A entidade Edital tem uma PK normal, mas uma outra chave única que pode ser usada é o
        # código + webservice.
        qs = Edital.objects.filter(codigo=codigo_edital, webservice=webservice)
        if qs.exists():
            edital = qs[0]
            edital.configuracao_migracao_vagas = configuracao_migracao_vagas
            # edital.codigo = edital_selecionado_webservice.codigo
            edital.descricao = edital_selecionado_webservice.descricao
            edital.ano = edital_selecionado_webservice.ano
            edital.semestre = edital_selecionado_webservice.semestre

            edital.sisu = edital_selecionado_webservice.sisu
            edital.qtd_vagas = edital_selecionado_webservice.qtd_vagas
            edital.qtd_inscricoes = edital_selecionado_webservice.qtd_inscricoes
            edital.qtd_inscricoes_confirmadas = edital_selecionado_webservice.qtd_inscricoes_confirmadas
            edital.detalhamento_por_campus = edital_selecionado_webservice.detalhamento_por_campus

            edital.remanescentes = edital_selecionado_webservice.remanescentes
            # edital.webservice = edital_selecionado_webservice.webservice
            edital.save()
        else:
            # Senão, ocorrerá uma inserção, já que o edital "bruto" não tem id.
            edital_selecionado_webservice.configuracao_migracao_vagas = configuracao_migracao_vagas
            edital_selecionado_webservice.save()
            edital = edital_selecionado_webservice
        return tasks.importar_edital(self.xml, edital)


class MatricularAlunoProitecForm(forms.FormPlus):
    edital = forms.CharField(widget=forms.HiddenInput())
    ano = forms.ModelChoiceField(Ano.objects.all(), label='Ano', required=True)
    periodo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período', required=True)
    matriz = forms.ModelChoiceField(queryset=Matriz.objects.none(), label='Matriz', required=True)

    SUBMIT_LABEL = 'Matricular Candidatos'

    def __init__(self, edital, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['edital'].initial = edital.pk
        self.fields['matriz'].queryset = edital.get_matrizes_pronatec()
        self.edital = edital

    def processar(self, request):
        edital = Edital.objects.get(pk=self.cleaned_data.get('edital'))
        ano_letivo = self.cleaned_data.get('ano')
        periodo_letivo = self.cleaned_data.get('periodo')
        matriz = self.cleaned_data.get('matriz')
        return tasks.matricular_alunos_proitec(edital, ano_letivo, periodo_letivo, matriz)


class ListaForm(forms.ModelFormPlus):
    class Meta:
        model = Lista
        fields = ('forma_ingresso', 'requer_avaliacao_banca')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['forma_ingresso'].queryset = self.fields['forma_ingresso'].queryset.filter(ativo=True)


class EditalAdesaoCampusForm(forms.ModelForm):
    idade_minima = forms.BooleanField(label='Critério de Maioridade', required=False)

    class Meta:
        model = EditalAdesaoCampus
        fields = (
            'nome',
            'edital_regulador',
            'data_inicio_inscricoes',
            'data_encerramento_inscricoes',
            'ano_edital',
            'numero_edital',
            'campus',
            'data_aplicacao_prova',
            'idade_minima',
            'data_aplicacao_prova',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not running_tests():
            now = datetime.now()
            self.fields['edital_regulador'].queryset = self.fields['edital_regulador'].queryset.filter(
                data_inicio_adesao__lte=now, data_limite_adesao__gte=now
            )
        else:
            self.fields['edital_regulador'].queryset = EditalAdesao.objects.all()
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo()

    def clean(self):
        cleaned_data = super().clean()
        data_encerramento_inscricoes = cleaned_data['data_encerramento_inscricoes']
        edital_regulador = cleaned_data.get('edital_regulador', None)
        if edital_regulador and data_encerramento_inscricoes > edital_regulador.data_limite_adesao:
            raise forms.ValidationError('A data de encerramento das inscrições não pode ser superior a data limite de adesão ao edital regulador!')

        idade_minima = cleaned_data.get('idade_minima', False)
        data_aplicacao_prova = cleaned_data.get('data_aplicacao_prova', None)
        if idade_minima:
            if not data_aplicacao_prova:
                raise forms.ValidationError(
                    'O edital exige uma data mínima para a inscrição dos fiscais, portanto a data da aplicação da prova deve ser informada!'
                )

            if data_encerramento_inscricoes.date() > data_aplicacao_prova.date():
                raise forms.ValidationError('A data de encerramento das inscrições não pode ser superior a data da aplicação da prova!')
        return cleaned_data


class InscricaoFiscalForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoFiscal
        exclude = ('fiscal', 'matricula', 'edital', 'campus')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.edital = kwargs.pop('edital')
        self.campus = get_uo(self.user)
        super().__init__(*args, **kwargs)
        self.instance.set_user(self.user)
        self.instance.edital = self.edital
        self.instance.campus = self.campus

        vinculo = self.user.get_vinculo()
        choices = []
        servidor = Servidor.objects.efetivos().filter(pessoa_fisica__cpf=vinculo.pessoa.get_cpf_ou_cnpj(), ativo=True).first()
        if servidor:
            choices.append((InscricaoFiscal.TIPO_SERVIDOR, 'Servidor'))
        aluno = Aluno.objects.filter(pessoa_fisica__cpf=vinculo.pessoa.get_cpf_ou_cnpj(), situacao__ativo=True).exists()
        if aluno:
            choices.append((InscricaoFiscal.TIPO_ALUNO, 'Aluno'))
        self.fields['tipo'] = forms.ChoiceField(choices=choices, label='Tipo do Vínculo')

    def clean(self, *args, **kwargs):
        self.cleaned_data = super().clean(*args, **kwargs)

        tipo_vinculo = self.cleaned_data.get('tipo', None)
        if tipo_vinculo is None:
            raise forms.ValidationError('O tipo do vínculo ser informado')
        self.instance.tipo = tipo_vinculo
        tipo_conta = self.cleaned_data.get('tipo_conta', None)
        if tipo_conta is None:
            raise forms.ValidationError('O tipo da conta deve ser informado')

        if self.cleaned_data['tipo_conta'] == InscricaoFiscal.TIPO_CONTA_POUPANCA:
            if not self.cleaned_data['operacao']:
                raise forms.ValidationError('A operação deve ser informada no caso do tipo da conta ser Poupança')
        if not self.cleaned_data['aceito_termos']:
            raise forms.ValidationError('A inscrição só pode ser validada caso o termo de compromisso for aceito')

        pode_efetuar_inscricao, msg = InscricaoFiscal.pode_efetuar_inscricao(self.user, self.edital)
        if not pode_efetuar_inscricao:
            raise forms.ValidationError(msg)

        return self.cleaned_data


class InscricaoFiscalAdminForm(forms.ModelFormPlus):
    fiscal = forms.ModelChoiceField(
        label='Servidor/Aluno', queryset=Vinculo.objects.none(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )

    class Meta:
        model = InscricaoFiscal
        fields = (
            'edital',
            'fiscal',
            'tipo',
            'matricula',
            'telefones',
            'banco',
            'numero_agencia',
            'tipo_conta',
            'numero_conta',
            'operacao',
            'pis_pasep',
            'outros_processos',
            'aceito_termos',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pred = [Q(pessoa__pessoafisica__eh_aluno=True), Q(pessoa__pessoafisica__eh_servidor=True)]
        self.fields['fiscal'].queryset = Vinculo.objects.filter(reduce(operator.or_, pred))

    def clean(self, *args, **kwargs):
        self.cleaned_data = super().clean(*args, **kwargs)

        tipo_vinculo = self.cleaned_data.get('tipo', None)
        if tipo_vinculo is None:
            raise forms.ValidationError('O tipo do vínculo ser informado')
        self.instance.tipo = tipo_vinculo
        tipo_conta = self.cleaned_data.get('tipo_conta', None)
        if tipo_conta is None:
            raise forms.ValidationError('O tipo da conta deve ser informado')

        if self.cleaned_data['tipo_conta'] == InscricaoFiscal.TIPO_CONTA_POUPANCA:
            if not self.cleaned_data['operacao']:
                raise forms.ValidationError('A operação deve ser informada no caso do tipo da conta ser Poupança')
        if not self.cleaned_data['aceito_termos']:
            raise forms.ValidationError('A inscrição só pode ser validada caso o termo de compromisso for aceito')

        pode_efetuar_inscricao, msg = InscricaoFiscal.pode_efetuar_inscricao(self.user, self.edital)
        if not pode_efetuar_inscricao:
            raise forms.ValidationError(msg)

        return self.cleaned_data


class ConfiguracaoMigracaoVagaForm(forms.ModelFormPlus):
    listas = forms.ModelMultiplePopupChoiceField(RotuloLista.objects.all(), label='Listas', required=True)

    class Meta:
        model = ConfiguracaoMigracaoVaga
        fields = 'descricao', 'is_sisu', 'ativo', 'listas'

    fieldsets = (('Dados gerais', {'fields': ('descricao', ('is_sisu', 'ativo'))}), ('Listas Utilizadas', {'fields': ('listas',)}))


class DefinirConfiguracaoMigracaoVagaForm(forms.ModelFormPlus):
    class Meta:
        model = Edital
        fields = ('configuracao_migracao_vagas',)


class DefinirPrecedenciaMatriculaForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoMigracaoVaga
        exclude = 'descricao', 'is_sisu', 'ativo', 'listas'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in range(1, 16):
            self.fields[f'lista_{i}'].queryset = self.instance.listas.all()
        qtd = self.instance.listas.count() + 1
        self.fieldsets = (('Precedência de Matrícula', {'fields': [f'lista_{i}' for i in range(1, qtd)]}),)


class PrecedenciaMigracaoForm(forms.FormPlus):
    TITLE = 'Precedência de Migração'
    origem = forms.ModelChoiceField(RotuloLista.objects, label='Lista')

    def __init__(self, *args, **kwargs):
        self.configuracao = kwargs.pop('configuracao')
        origem = 'lista_origem' in kwargs and kwargs.pop('lista_origem') or None
        super().__init__(*args, **kwargs)
        self.fields['origem'].queryset = self.configuracao.listas.all()
        qtd = self.configuracao.listas.count()
        lista = []
        for i in range(1, qtd):
            lista.append(str(i))
            self.fields[str(i)] = forms.ModelChoiceField(self.configuracao.listas.all(), label=f'Ordem {i}', required=False)
            if origem:
                qs = PrecedenciaMigracao.objects.filter(configuracao=self.configuracao, origem__nome=origem, precedencia=i)
                if qs.exists():
                    self.initial[str(i)] = qs[0].destino.pk

        self.fieldsets = (('Dados gerais', {'fields': ('origem',)}), ('Ordem de Precedência', {'fields': lista}))
        pks = PrecedenciaMigracao.objects.filter(configuracao=self.configuracao).values_list('origem', flat=True)
        if origem:
            pk = RotuloLista.objects.get(nome=origem).pk
            self.initial['origem'] = pk
            self.fields['origem'].queryset = self.fields['origem'].queryset.filter(pk=pk)
        else:
            self.fields['origem'].queryset = self.fields['origem'].queryset.exclude(pk__in=pks)

    def save(self):
        origem = self.cleaned_data.get('origem')
        PrecedenciaMigracao.objects.filter(configuracao=self.configuracao, origem=origem).delete()
        qtd = self.configuracao.listas.count()
        for i in range(1, qtd):
            destino = self.cleaned_data.get(str(i))
            if destino:
                PrecedenciaMigracao.objects.create(configuracao=self.configuracao, origem=origem, precedencia=i, destino=destino)
            else:
                break


class RealizarAcaoLote(forms.FormPlus):
    acao = forms.ChoiceField(label='Ação', choices=[['ausencia', 'Registrar Ausência'], ['inaptidao', 'Registrar Inaptidão']])
    classificacao_inicial = forms.IntegerField(label='Classificação Inicial')
    classificacao_final = forms.IntegerField(label='Classificação Final')

    def __init__(self, *args, **kwargs):
        self.oferta_vaga = kwargs.pop('oferta_vaga')
        super().__init__(*args, **kwargs)

        if self.request.user.is_superuser:
            self.fields['acao'].choices = [*self.fields['acao'].choices, ['simular_matricula', 'Simular Matrícula']]

    def processar(self):
        classificacao_inicial = self.cleaned_data['classificacao_inicial']
        classificacao_final = self.cleaned_data['classificacao_final']
        acao = self.cleaned_data['acao']
        qs = self.oferta_vaga.get_candidatos_convocados().filter(
            situacao__isnull=True, classificacao__gte=classificacao_inicial, classificacao__lte=classificacao_final
        )
        if acao == 'ausencia':
            for candidato_vaga in qs:
                candidato_vaga.registrar_ausencia()
        elif acao == 'inaptidao':
            for candidato_vaga in qs:
                candidato_vaga.registrar_inaptidao()
        elif acao == 'simular_matricula':
            for candidato_vaga in qs:
                candidato_vaga.simular_matricula()

    def clean(self):
        cleaned_data = self.cleaned_data
        classificacao_inicial = self.cleaned_data.get('classificacao_inicial', 0)
        classificacao_final = self.cleaned_data.get('classificacao_final', 0)
        qs = self.oferta_vaga.get_candidatos_convocados().filter(classificacao__gte=classificacao_inicial, classificacao__lte=classificacao_final)
        if qs.filter(situacao__isnull=False):
            raise forms.ValidationError(
                'O intervalo informado inclui inscrições já processadas. Por favor, informe outro intervalo de classificação.'
            )
        return cleaned_data


class VincularMatriculaForm(forms.FormPlus):
    aluno = forms.ModelChoiceField(queryset=Aluno.objects.none(), label='Aluno', required=True)

    SUBMIT_LABEL = 'Vincular'

    def __init__(self, *args, **kwargs):
        self.candidato_vaga = kwargs.pop('candidato_vaga')
        super().__init__(*args, **kwargs)
        self.fields['aluno'].queryset = Aluno.objects.filter(
            pessoa_fisica__cpf=self.candidato_vaga.candidato.cpf,
            curso_campus=self.candidato_vaga.candidato.curso_campus,
            ano_letivo=self.candidato_vaga.candidato.edital.ano,
            periodo_letivo=self.candidato_vaga.candidato.edital.semestre,
        )

    def processar(self):
        self.candidato_vaga.situacao = CandidatoVaga.MATRICULADO
        self.candidato_vaga.save()
        aluno = self.cleaned_data.get('aluno')
        aluno.candidato_vaga = self.candidato_vaga
        aluno.save()


class CriacaoVagaRemanescenteForm(forms.ModelFormPlus):
    class Meta:
        model = CriacaoVagaRemanescente
        fields = 'qtd', 'justificativa'


class CriacaoClassificacaoForm(forms.FormPlus):
    candidato = forms.ModelChoiceFieldPlus(Candidato.objects.none(), label='Candidato')
    classificacao = forms.IntegerField(label='Classificação')
    convocacao = forms.ChoiceField(label='Chamada', required=False, help_text='Marque essa opção cajo deseje convocar o candidato.')
    criar_vaga = forms.BooleanField(
        label='Criar vaga se necessário',
        required=False,
        help_text='Marque essa opção caso deseje que a vaga seja criada se nenhuma estiver disponível.',
    )
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea())

    fieldsets = (
        ('Dados gerais', {'fields': ('candidato', 'classificacao')}),
        (
            'Convocação',
            {
                'fields': (
                    'convocacao',
                    'criar_vaga',
                )
            },
        ),
        ('Justificativa', {'fields': ('justificativa',)}),
    )

    def __init__(self, oferta_vaga, *args, **kwargs):
        self.oferta_vaga = oferta_vaga
        super().__init__(*args, **kwargs)
        self.fields['candidato'].queryset = Candidato.objects.filter(edital=oferta_vaga.oferta_vaga_curso.edital_id)
        self.fields['convocacao'].choices = [['', 'Não convocar candidato']] + [
            [x, x]
            for x in oferta_vaga.candidatovaga_set.filter(convocacao__isnull=False)
            .order_by('convocacao')
            .values_list('convocacao', flat=True)
            .distinct()
        ]
        qtd_vagas_disponiveis = len(self.oferta_vaga.get_vagas_disponiveis())
        if qtd_vagas_disponiveis:
            self.fields['convocacao'].help_text = f'Vagas disponíveis: {qtd_vagas_disponiveis}'

    def clean_convocacao(self):
        convocacao = self.cleaned_data.get('convocacao')
        criar_vaga = self.cleaned_data.get('criar_vaga')
        if convocacao and not criar_vaga and not self.oferta_vaga.get_vagas_disponiveis():
            raise forms.ValidationError('Não é possível convocar o candidato, pois não há vaga disponível')
        return convocacao

    def save(self):
        candidato = self.cleaned_data['candidato']
        classificacao = self.cleaned_data['classificacao']
        convocacao = self.cleaned_data['convocacao'] or None
        criar_vaga = self.cleaned_data['criar_vaga']
        justificativa = self.cleaned_data['justificativa']
        candidato_vaga = CandidatoVaga.objects.filter(oferta_vaga=self.oferta_vaga, candidato=candidato).first() or CandidatoVaga()
        candidato_vaga.oferta_vaga = self.oferta_vaga
        candidato_vaga.candidato = candidato
        candidato_vaga.classificacao = classificacao
        candidato_vaga.convocacao = convocacao
        vaga_criada = None
        if convocacao:
            if candidato_vaga.id is None or not candidato_vaga.vaga_id:
                vagas = self.oferta_vaga.get_vagas_disponiveis()
                if vagas:
                    vagas[0].candidatovaga_set.update(vaga=None)
                    candidato_vaga.vaga = vagas[0]
                elif criar_vaga:
                    vaga_criada = Vaga.objects.create(oferta_vaga=self.oferta_vaga)
                    candidato_vaga.vaga = vaga_criada
        candidato_vaga.save()
        if vaga_criada:
            CriacaoVagaRemanescente.objects.create(oferta_vaga=self.oferta_vaga, qtd=1, justificativa=justificativa)
        criacao_classificacao = CriacaoClassificacao.objects.filter(candidato_vaga=candidato_vaga).first() or CriacaoClassificacao()
        criacao_classificacao.candidato_vaga = candidato_vaga
        criacao_classificacao.justificativa = justificativa
        criacao_classificacao.data = datetime.now()
        criacao_classificacao.save()


class CorrigirQuantidadeVagaRemanescenteForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroAjusteCriacaoVagaRemanescente
        fields = 'qtd_ajustada', 'justificativa'


class MigrarVagaPoloForm(forms.FormPlus):
    qtd = forms.IntegerField(label='Quantidade')
    polo_destino = forms.ChoiceField(label='Polo', choices=[])

    def processar(self, oferta_vaga_curso_origem):
        vagas = []
        qtd = self.cleaned_data['qtd']
        polo_destino = self.cleaned_data['polo_destino']
        oferta_vaga_curso_destino = OfertaVagaCurso.objects.filter(
            edital=oferta_vaga_curso_origem.edital, curso_campus=oferta_vaga_curso_origem.curso_campus, campus_polo=polo_destino
        ).first()
        if oferta_vaga_curso_destino:
            for oferta_vaga_origem in oferta_vaga_curso_origem.ofertavaga_set.all():
                vagas_disponiveis = oferta_vaga_origem.get_vagas_disponiveis()
                if vagas_disponiveis:
                    oferta_vaga_destino = oferta_vaga_curso_destino.ofertavaga_set.filter(lista=oferta_vaga_origem.lista).first()
                    for vaga in vagas_disponiveis:
                        vagas.append((oferta_vaga_destino, vaga))
            if len(vagas) >= qtd:
                for oferta_vaga_destino, vaga in vagas[0:qtd]:
                    CandidatoVaga.objects.filter(vaga=vaga).update(vaga=None)
                    oferta_vaga_destino.vagas_recebidas_polos.add(vaga)
            else:
                self.add_error('qtd', f'O número de vagas disponíveis é {len(vagas)}.')


class ParticipacaoBancaForm(forms.ModelFormPlus):
    class Meta:
        model = Candidato
        fields = 'aprovado_heteroidentificacao', 'aprovado_quilombola', 'aprovado_escola_publica', 'aprovado_baixa_renda', 'aprovado_deficiencia'
