from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from comum.models import Ano, Sala, UsuarioGrupoSetor, UsuarioGrupo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from djtools.utils import send_notification
from edu import tasks
from edu.models import (
    AberturaExtemporanea,
    AlteracaoRespostaJustificativaCensup,
    Aluno,
    Cidade,
    Convenio,
    CursoCampus,
    Diretoria,
    ExecucaoPlanoLaboratorio,
    Laboratorio,
    MatriculaPeriodo,
    Modalidade,
    NivelEnsino,
    Polo,
    QuestaoEducacenso,
    RegistroEducacenso,
    RespostaEducacenso,
    RespostaJustificativaCensup,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turma,
)
from edu.sttu import MODALIDADES as MODALIDADES_STTU
from rh.models import UnidadeOrganizacional


class PreencherRelatorioCensupForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Pesquisar'
    CAMPUS_CURSO = 1
    CAMPUS_PROFESSOR = 2
    CAMPUS_ALUNO = 3
    CURSO_ALUNO = 4

    BUSCA_CPF = 1
    BUSCA_MATRICULA = 2

    # add javascripit.. se for CAMPUS_CURSO esconder tipo_busca

    tipo_relatorio = forms.ChoiceField(
        label='Tipo de relatório',
        choices=[
            [CAMPUS_CURSO, 'Campus do Curso'],
            [CAMPUS_PROFESSOR, 'Campus do Professor'],
            [CAMPUS_ALUNO, 'Campus do Aluno'],
            [CURSO_ALUNO, 'Curso do Aluno'],
        ],
        required=True,
    )

    planilha = forms.FileFieldPlus(required=True, filetypes=['xls'])
    tipo_busca = forms.ChoiceField(
        label='Tipo de busca',
        choices=[
            [BUSCA_CPF, 'CPF'],
            [BUSCA_MATRICULA, 'Matrícula'],
        ],
        required=True,
    )
    coluna_busca = forms.IntegerFieldPlus(label='Coluna de busca', help_text='Número da coluna que o sistema buscará.', required=True)
    coluna_salva = forms.IntegerFieldPlus(label='Coluna de salvamento', help_text='Número da coluna que o sistema salvará.', required=True)

    class Media:
        js = ('/static/edu/js/PreencherRelatorioCensupForm.js',)

    def clean_coluna_busca(self):
        if self.cleaned_data.get('coluna_busca') < 1:
            return ValidationError('Coluna inválida.')
        return self.cleaned_data.get('coluna_busca')

    def clean_coluna_salva(self):
        if self.cleaned_data.get('coluna_salva') < 1:
            return ValidationError('Coluna inválida.')
        return self.cleaned_data.get('coluna_salva')


class AtualizarCodigoEducacensoForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Pesquisar'

    arquivo = forms.FileFieldPlus(required=True, help_text='Arquivo TXT de retorno do MEC contendo os prováveis registros.')

    def processar(self):
        arquivo = self.cleaned_data['arquivo'].file
        registros = list(arquivo.readlines())
        return tasks.atualizar_codigo_educacenso(registros)


class PreencherRelatorioSistecForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Pesquisar'

    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.campi().all(), label='Campus')
    planilha = forms.FileFieldPlus(
        label='Planilha',
        required=True,
        filetypes=['csv'],
        max_file_size='20971520',
        help_text='O arquivo deve possuir uma coluna chamada "NO_STATUS_MATRICULA".',
    )


class AtualizarSistecAlunoForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Atualizar'

    INFO = mark_safe(
        """
        <ul>
            <li>O arquivo deve ser no formato CSV delimitado por ponto e vírgula (;).</li>
            <li>A identificação do aluno pode ocorrer de três formas:
                <ol>
                    <li>Pela matrícula SUAP: colunas <strong>"MATRICULA"</strong> e <strong>"CO_MATRICULA"</strong>.</li>
                    <li>Por CPF: colunas <strong>"CO_MATRICULA"</strong>, <strong>"CO_CURSO"</strong>, <strong>"DT_DATA_INICIO"</strong> e <strong>"NU_CPF"</strong>.</li>
                    <li>Para alunos sem CPF: colunas <strong>"CO_MATRICULA"</strong>, <strong>"CO_CURSO"</strong>, <strong>"DT_DATA_INICIO"</strong>, <strong>"NO_ALUNO"</strong> e <strong>"DT_DATA_NASCIMENTO"</strong>.</li>
                </ol>
            </li>
            <li>A coluna <strong>"CO_MATRICULA"</strong> deve possuir o código SISTEC do aluno.</li>
            <li>A coluna <strong>"DT_DATA_FIM_PREVISTO"</strong> pode ser informada para definir a data prevista de término do ciclo. Caso não informada na planilha, a data será calculada pelo SUAP.</li>
        </ul>
        """
    )

    planilha = forms.FileFieldPlus(label='Arquivo', required=True, filetypes=['csv'], max_file_size=20971520)
    sobrescrever = forms.BooleanField(
        label='Sobrescrever código SISTEC',
        required=False,
        help_text='Se marcado, substitui o código SISTEC mesmo para alunos que já possuam um código cadastrado. Se desmarcado, atualiza apenas alunos sem código cadastrado.',
    )
    atualizar = forms.BooleanField(
        label='Sobrescrever data de início do ciclo',
        required=False,
        help_text='Se marcado, substitui a data de início do ciclo mesmo para alunos que já possuam essa data cadastrada. Se desmarcado, define a data apenas para alunos que ainda não a possuam.',
    )
    atualizar_data_fim = forms.BooleanField(
        label='Sobrescrever data prevista de término do ciclo',
        required=False,
        help_text='Se marcado, substitui a data prevista de término do ciclo mesmo para alunos que já possuam essa data cadastrada. Se desmarcado, define a data apenas para alunos que ainda não a possuam.',
    )

    def clean_planilha(self):
        planilha = self.cleaned_data.get('planilha')
        if planilha:
            import csv
            import os
            import tempfile

            # Salvar o arquivo em um caminho temporário
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_file:
                temp_file.write(planilha.file.read())
                temp_file_path = temp_file.name

            try:
                with open(temp_file_path, encoding='iso-8859-1') as csvfile:
                    reader = csv.DictReader(csvfile, delimiter=';')
                    headers = reader.fieldnames or []
                    tem_matricula = all(column in headers for column in ['CO_MATRICULA', 'MATRICULA'])
                    tem_cpf = all(column in headers for column in ['CO_MATRICULA', 'CO_CURSO', 'DT_DATA_INICIO', 'NU_CPF'])
                    tem_sem_cpf = all(
                        column in headers for column in ['CO_MATRICULA', 'CO_CURSO', 'DT_DATA_INICIO', 'NO_ALUNO', 'DT_DATA_NASCIMENTO']
                    )
                    if not (tem_matricula or tem_cpf or tem_sem_cpf):
                        raise ValidationError(f'O cabeçalho {";".join(headers)} não está no formato esperado.')
            finally:
                planilha.seek(0)
                os.unlink(temp_file_path)
        return planilha


class PreencherRelatorioAlunosNaoExistentesNoSistecForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Pesquisar'

    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.campi().all(), label='Campus')
    ano_letivo = forms.ModelMultiplePopupChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    excluir_convenio = forms.ModelMultiplePopupChoiceField(Convenio.objects, label='Excluir Convênios', required=False)
    planilha = forms.FileFieldPlus(
        label='Planilha',
        required=True,
        filetypes=['csv'],
        max_file_size='20971520',
        help_text='O arquivo deve possuir as coluna "NU_CPF e CO_CURSO".',
    )


class RelatorioIsFForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Gerar Relatório XLS'

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)

    def processar(self):
        return self.cleaned_data['ano_letivo'], self.cleaned_data['periodo_letivo']


class AuditoriaCensoForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Gerar Relatório'
    TIPOS_RELATORIO = [
        # [1, 'Dados Divergentes com a Receita Federal'],
        # [2, 'Matrículas na mesma Modalidade'],
        # [3, 'Nome com Pontuação/Caracter Especial']
    ]

    tipo_relatorio = forms.ChoiceField(label='Tipo de Relatório', choices=TIPOS_RELATORIO, required=True)
    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.locals, label='Campus', required=False)
    curso = forms.ModelChoiceFieldPlus(
        CursoCampus.locals,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo')]),
    )
    nivel_ensino = forms.MultipleModelChoiceFieldPlus(NivelEnsino.objects, label='Nível de Ensino', required=False)
    modalidade = forms.MultipleModelChoiceFieldPlus(Modalidade.objects, label='Modalidade', required=False)
    situacao = forms.MultipleModelChoiceFieldPlus(SituacaoMatricula.objects, label='Situação', required=False)

    def clean_situacao(self):
        tipo = self.cleaned_data.get('tipo_relatorio')
        situacao = self.cleaned_data.get('situacao')
        if int(tipo) == 2 and not situacao:
            raise ValidationError('Informe pelo menos uma situação de matrícula.')
        return situacao

    def processar(self):
        tipo = int(self.cleaned_data['tipo_relatorio'])
        uo = self.cleaned_data.get('uo') or None
        curso = self.cleaned_data.get('curso') or None
        nivel_ensino = self.cleaned_data.get('nivel_ensino') or None
        modalidade = self.cleaned_data.get('modalidade') or None
        situacao = self.cleaned_data.get('situacao') or None
        cpf_operador = self.request.user.get_profile().cpf
        return tasks.exportar_auditoria_censos(tipo, uo, curso, nivel_ensino, modalidade, situacao, cpf_operador)


class RelatorioSTTUForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Gerar Relatório STTU'
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=[[None, '----'], *Aluno.PERIODO_LETIVO_CHOICES], required=False)
    ano_letivo_ingresso = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo de Ingresso', required=False)
    periodo_letivo_ingresso = forms.ChoiceField(
        label='Período Letivo de Ingresso', required=False, choices=[[None, '----'], *Aluno.PERIODO_LETIVO_CHOICES]
    )
    uos = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.locals, label='Campus', required=False)
    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.locals,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uos', 'diretoria__setor__uo__in')]),
    )
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects.none(),
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS, form_filters=[('curso_campus', 'curso_campus'), ('uos', 'curso_campus__diretoria__setor__uo__in')]
        ),
    )
    cidade = forms.ModelChoiceFieldPlus(Cidade.objects, label='Cidade', required=False)
    polos = forms.ModelMultiplePopupChoiceField(Polo.objects, required=False, label='Polo EAD', help_text='Apenas para o Turno EAD.')

    fieldsets = (
        ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'),)}),
        ('Filtros', {'fields': (('ano_letivo_ingresso', 'periodo_letivo_ingresso'), 'uos', ('curso_campus', 'turma'), 'cidade', 'polos')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        MUNICIPIO_NATAL = '1761'
        MUNICIPIO_CEARA_MIRIM = '1651'
        MUNICIPIO_SAO_GONCALO = '1837'
        MUNICIPIO_PARNAMIRIM = '1779'
        self.MUNICIPIO_ABRANGENCIA_STTU = (MUNICIPIO_NATAL, MUNICIPIO_CEARA_MIRIM, MUNICIPIO_SAO_GONCALO, MUNICIPIO_PARNAMIRIM)
        uos = UnidadeOrganizacional.locals.filter(municipio__codigo__in=self.MUNICIPIO_ABRANGENCIA_STTU)
        self.fields['uos'].queryset = uos
        self.fields['curso_campus'].queryset = CursoCampus.locals.filter(diretoria__setor__uo__in=uos, modalidade__in=MODALIDADES_STTU)
        self.fields['turma'].queryset = Turma.locals.filter(curso_campus__diretoria__setor__uo__in=uos)

        if not self.request.user.get_vinculo().setor.uo.eh_reitoria:
            self.fields['uos'].initial = (self.request.user.get_vinculo().setor.uo_id,)

    def clean(self):
        data = self.cleaned_data.copy()
        data.pop('ano_letivo', '')
        empty = True
        for value in data.values():
            if value:
                empty = False
                break
        if empty:
            raise forms.ValidationError('Escolha pelo menos um filtro')
        return self.cleaned_data

    def processar(self):
        situacoes_matricula = (SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL)
        ano_letivo = self.cleaned_data.get('ano_letivo')

        qs = MatriculaPeriodo.objects.filter(
            aluno__matriz__isnull=False,
            aluno__curso_campus__modalidade__in=MODALIDADES_STTU,
            situacao__in=situacoes_matricula,
            aluno__pessoa_fisica__nascimento_data__isnull=False,
            ano_letivo=ano_letivo,
        )

        qs = qs.exclude(aluno__nome_mae__isnull=True).exclude(aluno__nome_mae='').select_related('aluno__pessoa_fisica')

        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        if periodo_letivo:
            qs = qs.filter(periodo_letivo=periodo_letivo)

        polos = self.cleaned_data.get('polos')
        if polos:
            qs = qs.filter(aluno__polo__in=polos)

        uos = self.cleaned_data.get('uos')
        if not uos:
            uos = UnidadeOrganizacional.locals.filter(municipio__codigo=self.MUNICIPIO_ABRANGENCIA_STTU)
        qs = qs.filter(aluno__curso_campus__diretoria__setor__uo__in=uos)

        curso = self.cleaned_data.get('curso_campus')
        if curso:
            qs = qs.filter(aluno__curso_campus=curso)

        turma = self.cleaned_data.get('turma')
        if turma:
            qs = qs.filter(turma=turma)

        cidade = self.cleaned_data.get('cidade')
        if cidade:
            qs = qs.filter(aluno__cidade_id=cidade)

        ano_letivo_ingresso = self.cleaned_data.get('ano_letivo_ingresso')
        if ano_letivo_ingresso:
            qs = qs.filter(aluno__ano_letivo=ano_letivo_ingresso)

        periodo_letivo_ingresso = self.cleaned_data.get('periodo_letivo_ingresso')
        if periodo_letivo_ingresso:
            qs = qs.filter(aluno__periodo_letivo=periodo_letivo_ingresso)
        return qs


class RelatorioCensupForm(forms.FormPlus):
    METHOD = 'POST'
    SUBMIT_LABEL = 'Gerar Relatório CENSUP'

    tipo = forms.ChoiceField(choices=[['', '---'], [1, 'Docente'], [2, 'Aluno'], [3, 'Laboratório']], required=True)
    uos = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.campi().all(), label='Campus', required=False)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')

    amostra = forms.BooleanField(
        label='Amostra?', help_text='Marque essa opção caso deseje gerar uma amostra contendo apenas 10 registros', required=False
    )

    ignorar_data_conclusao = forms.BooleanField(
        label='Ignorar Data de Conclusão',
        help_text='Marque essa opção caso deseje ignorar a verificação da data de conclusão do curso pelo aluno.',
        required=False,
    )

    cpfs = forms.CharField(
        label='Selecionar CPFs',
        help_text='Informe os CPFs (sem pontuação e em linhas separadas) que deverão ser mantidos na listagem.',
        required=False,
        widget=forms.Textarea(),
    )
    ignorar_cpfs = forms.CharField(
        label='Ignorar CPFs',
        help_text='Informe os CPFs (sem pontuação e em linhas separadas) que deverão ser excluídos da listagem.',
        required=False,
        widget=forms.Textarea(),
    )

    fieldsets = (
        ('Dados gerais', {'fields': (('tipo', 'ano_letivo'),)}),
        ('Outras Informações', {'fields': ('uos', 'amostra', 'ignorar_cpfs', 'cpfs', 'ignorar_data_conclusao')}),
    )

    def processar(self):
        cpfs = self.cleaned_data['cpfs'].replace(' ', '').replace('\r', '')
        ignorar_cpfs = self.cleaned_data['ignorar_cpfs'].replace(' ', '').replace('\r', '')
        amostra = self.cleaned_data['amostra']
        tipo = int(self.cleaned_data['tipo'])
        uos = list(self.cleaned_data['uos'].values_list('id', flat=True))
        ano = self.cleaned_data['ano_letivo'].ano
        cpfs = cpfs and cpfs.split('\n') or ''
        ignorar_cpfs = ignorar_cpfs and ignorar_cpfs.split('\n') or []
        ignorar_data_conclusao = self.cleaned_data.get('ignorar_data_conclusao', False)
        return tasks.exportar_dados_censup(tipo, ano, uos, amostra, cpfs, ignorar_cpfs, ignorar_data_conclusao)


class RelatorioEducacensoForm(forms.FormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.campi().all(), label='Campus')
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano letivo')
    ignorar_erros = forms.BooleanField(
        label='Ignorar erros',
        required=False,
        help_text='Marque esta opção para gerar o arquivo de exportação, ignorando os registros que apresentarem erros de validação.',
    )
    validar_alunos = forms.BooleanField(
        label='Validar alunos',
        required=False,
        help_text='Marque esta opção para que o sistema interrompa o processamento caso encontre erros de validação nos dados de aluno, emitindo o relatório de erros antes de prosseguir com a validação dos demais registros.',
    )
    ignorar_matriculas = forms.CharField(
        label='Ignorar matrículas',
        help_text='Informe, em linhas separadas, as matrículas que deverão ser excluídas do arquivo de exportação.',
        required=False,
        widget=forms.Textarea(),
    )

    filtrar_matriculas = forms.CharField(
        label='Filtrar matrículas',
        help_text='Informe, em linhas separadas, as matrículas que deverão ser consideradas na geração do arquivo de exportação.',
        required=False,
        widget=forms.Textarea(),
    )

    inferir_turma = forms.BooleanField(
        label='Inferir turma',
        required=False,
        help_text='Marque esta opção para que o sistema atribua uma turma aos alunos que não possuem turma vinculada ao período letivo do Censo.',
    )

    partiu_if = forms.BooleanField(
        label='Programa PartiuIF',
        required=False,
        help_text='Marque esta opção para restringir a exportação aos cursos FIC do programa PartiuIF.',
    )

    fieldsets = (
        ('Dados gerais', {'fields': (('uo', 'ano_letivo'),)}),
        (
            'Filtros adicionais',
            {'fields': ('inferir_turma', 'partiu_if', 'validar_alunos', 'ignorar_erros', 'ignorar_matriculas', 'filtrar_matriculas')},
        ),
    )

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        uo = self.cleaned_data['uo']
        validar_alunos = self.cleaned_data.get('validar_alunos', False)
        ignorar_erros = self.cleaned_data.get('ignorar_erros', False)
        inferir_turma = self.cleaned_data.get('inferir_turma', False)
        partiu_if = self.cleaned_data.get('partiu_if', False)
        ignorar_matriculas = self.cleaned_data.get('ignorar_matriculas', '').replace(' ', '').replace('\r', '').split('\n')
        filtrar_matriculas = self.cleaned_data.get('filtrar_matriculas', '').replace(' ', '').replace('\r', '').split('\n')
        return tasks.exportar_dados_educacenso(
            ano_letivo.ano, uo, validar_alunos, ignorar_erros, ignorar_matriculas, filtrar_matriculas, inferir_turma, partiu_if
        )


class RelatorioEducacensoEtapa2Form(forms.FormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.campi().all(), label='Campus')
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano letivo')
    ignorar_erros = forms.BooleanField(
        label='Ignorar erros',
        required=False,
        help_text='Marque essa opção caso deseje que o arquivo de exportação seja gerado independentemente se todos os registros de alunos e professores tiverem sido validados ou não.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ignorar_erros'].initial = True

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        uo = self.cleaned_data['uo']
        ignorar_erros = self.cleaned_data['ignorar_erros']
        return tasks.exportar_dados_educacenso2(ano_letivo.ano, uo, ignorar_erros)


class ImportarEducacensoEtapa2Form(forms.FormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    arquivo = forms.FileFieldPlus(label='Arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        conteudo = self.cleaned_data['arquivo'].read().decode('latin1')
        return tasks.importar_dados_educacenso2(ano_letivo, conteudo)


class ClonarRegistroEducacensoForm(forms.FormPlus):
    INFO = 'Selecione o registro do EDUCACENSO que terá o questionário clonado e o ano do novo registro EDUCANCESO que será criado.'

    registro = forms.ModelChoiceFieldPlus(
        RegistroEducacenso.objects,
        label='Origem',
        widget=AutocompleteWidget(search_fields=RegistroEducacenso.SEARCH_FIELDS),
    )
    ano = forms.ModelChoiceField(Ano.objects.ultimos(), required=True, label='Ano do Censo')
    copiar_respostas = forms.BooleanField(label='Copiar Respostas', required=False)

    def processar(self):
        ano = self.cleaned_data.get('ano')
        respostas = self.cleaned_data.get('copiar_respostas')
        return self.cleaned_data.get('registro').clonar(ano, respostas)


class QuestaoEducacensoForm(forms.ModelFormPlus):
    class Meta:
        model = QuestaoEducacenso
        fields = 'registro', 'numero_campo', 'nome_campo', 'tipo_resposta', 'tipo_obrigatoriedade', 'resposta_privada', 'regra_resposta'

    def __init__(self, *args, **kwargs):
        registro = kwargs.pop('registro', None)
        clone = kwargs.pop('clone', None)
        super().__init__(*args, **kwargs)

        if self.instance.id is None:
            self.initial['numero_campo'] = QuestaoEducacenso.objects.filter(registro_id=registro).order_by('numero_campo').count() + 1

        if self.instance.id or registro:
            self.fields['registro'].widget = forms.HiddenInput()

        if registro:
            self.initial['registro'] = registro

        if clone:
            self.initial['resposta_privada'] = clone.resposta_privada
            self.initial['regra_resposta'] = clone.regra_resposta
            self.initial['tipo_resposta'] = clone.tipo_resposta
            self.initial['tipo_obrigatoriedade'] = clone.tipo_obrigatoriedade

    def processar(self):
        self.instance.save()
        return tasks.processar_questao_educacenso(self.instance, True)


def RespostaQuestaoEducacensoFormFactory(request, pk_questao, pk_campus=None):
    fields = {}
    questao = QuestaoEducacenso.objects.get(pk=pk_questao)
    qs_resposta = RespostaEducacenso.objects.filter(questao__pk=pk_questao)
    if pk_campus:
        qs_resposta = qs_resposta.filter(campus__pk=pk_campus)

    label = f'{questao}'
    if questao.tipo_resposta == QuestaoEducacenso.TIPO_REPOSTA_SIM_NAO:
        fields[f'resposta_{questao.numero_campo}'] = forms.NullBooleanField(label=label)
    else:
        fields[f'resposta_{questao.numero_campo}'] = forms.IntegerFieldPlus(label=label)

    if questao.tipo_obrigatoriedade == QuestaoEducacenso.TIPO_OBRIGATORIEDADE_OBRIGATORIO:
        fields[f'resposta_{questao.numero_campo}'].required = True
    else:
        fields[f'resposta_{questao.numero_campo}'].required = False
    fields[f'resposta_{questao.numero_campo}'].help_text = questao.regra_resposta or ''

    if pk_campus:
        fields[f'resposta_{questao.numero_campo}'].initial = str(qs_resposta.first().resposta).lower()

    def save(self, *args, **kwargs):
        field_name = f'resposta_{questao.numero_campo}'
        qs_resposta.update(resposta=self.cleaned_data.get(field_name))

    return type(
        'EducacensoForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'METHOD': 'POST',
            'SUBMIT_LABEL': 'Salvar',
            'save': save,
        },
    )


def RespostaEducacensoFormFactory(request, registroeducacenso_id, uo_id):
    fields = {}
    registro = RegistroEducacenso.objects.get(pk=registroeducacenso_id)
    questionario = registro.get_questoes_para_resposta(uo_id)
    for resposta in questionario:
        label = f'{resposta.questao}'

        if resposta.questao.tipo_resposta == QuestaoEducacenso.TIPO_REPOSTA_SIM_NAO:
            choices = [
                ('0', 'Não'),
                ('1', 'Sim'),
            ]
            if resposta.questao.tipo_obrigatoriedade != QuestaoEducacenso.TIPO_OBRIGATORIEDADE_OBRIGATORIO:
                choices.append(('', 'Sem resposta'))
            fields[f'resposta_{resposta.questao.numero_campo}'] = forms.ChoiceField(label=label, choices=choices, widget=forms.RadioSelect())
        else:
            fields[f'resposta_{resposta.questao.numero_campo}'] = forms.IntegerField(
                label=label, min_value=0 if resposta.questao.tipo_resposta == QuestaoEducacenso.TIPO_RESPOSTA_NUMERICA_COM_ZERO else 1
            )

        help_text = ''
        if resposta.questao.tipo_obrigatoriedade == QuestaoEducacenso.TIPO_OBRIGATORIEDADE_OBRIGATORIO:
            help_text = '<span class="false">Obrigatório.</span><br>'
        elif resposta.questao.tipo_obrigatoriedade == QuestaoEducacenso.TIPO_OBRIGATORIEDADE_CONDICIONAL:
            help_text = '<span class="false">Obrigatoriedade condicional.</span><br>'
        if resposta.questao.regra_resposta:
            help_text = f'{help_text}{resposta.questao.regra_resposta}'
        fields[f'resposta_{resposta.questao.numero_campo}'].help_text = help_text
        fields[f'resposta_{resposta.questao.numero_campo}'].required = False

        if resposta.questao.resposta_privada and not request.user.has_perm('edu.add_registroeducacenso'):
            fields[f'resposta_{resposta.questao.numero_campo}'].widget.attrs.update(readonly='readonly')

        if resposta.resposta:
            initial = resposta.resposta.lower()
            initial = '1' if initial == 'true' else '0' if initial == 'false' else initial
            fields[f'resposta_{resposta.questao.numero_campo}'].initial = initial

    def clean(self):
        # A validação só roda se o usuário clicou em "Concluir"
        cleaned_data = self.cleaned_data
        concluir = 'salvar_concluir' in self.data
        is_admin = request.user.has_group_cached('Administrador Acadêmico')
        if concluir:
            for resposta in questionario:
                if is_admin or not resposta.questao.resposta_privada:
                    campo_obrigatorio = resposta.questao.tipo_obrigatoriedade == QuestaoEducacenso.TIPO_OBRIGATORIEDADE_OBRIGATORIO
                    field_name = f'resposta_{resposta.questao.numero_campo}'
                    valor = cleaned_data.get(field_name)
                    if campo_obrigatorio and (valor is None or valor == ''):
                        self.add_error(field_name, 'Esta questão precisa ser respondida para concluir.')

        return cleaned_data

    def save(self, concluir=False, *args, **kwargs):
        for resposta in questionario:
            field_name = f'resposta_{resposta.questao.numero_campo}'
            resposta.resposta = self.cleaned_data.get(field_name)
            if concluir:
                resposta.situacao = RespostaEducacenso.SITUACAO_CONCLUIDO
                # Notificar os administradores acadêmicos e operadores de censo
                qs_usuario_grupo = (
                    UsuarioGrupo.objects.filter(group__name__in=['Administrador Acadêmico', 'Operador de Censo']).select_related('user').distinct()
                )
                usuarios_para_notificar = [ug.user.get_vinculo() for ug in qs_usuario_grupo]
                titulo = f'[SUAP] Questionário Educacenso foi concluído pelo campus {resposta.campus.nome}'
                texto = (
                    f'<h2>Questionário Educacenso foi concluído pelo campus {resposta.campus.nome}</h2>'
                    f'<p>Acesse {settings.SITE_URL}/edu/registroeducacenso/{resposta.questao.registro.id}/ </p>'
                )

                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, usuarios_para_notificar, fail_silently=True)
            else:
                resposta.situacao = RespostaEducacenso.SITUACAO_EDICAO
            resposta.save()

    return type(
        'EducacensoForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'EXTRA_BUTTONS': [{'type': 'submit', 'class': 'btn success', 'name': 'salvar_concluir', 'value': 'Salvar e Concluir'}],
            'clean': clean,
            'METHOD': 'POST',
            'SUBMIT_LABEL': 'Salvar e continuar depois',
            'save': save,
        },
    )


class SolicitarAberturaExtemporaneaForm(forms.ModelFormPlus):
    cursos = forms.MultipleModelChoiceField(
        CursoCampus.objects,
        label='Cursos',
        required=True,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, multiple=True, form_filters=[('diretoria', 'diretoria__in')]),
    )

    class Meta:
        model = AberturaExtemporanea
        fields = 'diretoria', 'cursos', 'data_inicio_ciclo', 'data_fim_ciclo', 'qtd_alunos', 'justificativa'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals.all()

    def processar(self, user):
        self.instance.solicitar(user, self.cleaned_data['cursos'])


class SolicitarAberturaExtemporaneaAdministradorForm(forms.ModelFormPlus):
    class Meta:
        model = AberturaExtemporanea
        fields = 'data_inicio_ciclo', 'data_fim_ciclo', 'periodo_abertura', 'justificativa', 'campi'

    def processar(self, user):
        self.instance.solicitar(user)


class IniciarAberturaExtemporaneaForm(forms.ModelFormPlus):
    class Meta:
        model = AberturaExtemporanea
        fields = ('data_inicio', 'periodo_abertura')

    def processar(self, user):
        self.instance.iniciar(user)


class RespostaJustificativaCensupForm(forms.ModelFormPlus):
    class Meta:
        model = RespostaJustificativaCensup
        fields = ('resposta',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resposta'].choices = [['', '----'], *self.instance.get_opcoes_choices()]

    def processar(self, user):
        self.instance.responder(user)


class AlterarRespostaJustificativaCensupForm(forms.ModelFormPlus):
    class Meta:
        model = AlteracaoRespostaJustificativaCensup
        fields = ('resposta',)

    def __init__(self, *args, **kwargs):
        resposta_justificativa_censup = kwargs.pop('resposta_justificativa_censup', None)
        super().__init__(*args, **kwargs)
        self.instance.resposta_justificativa_censup = resposta_justificativa_censup
        self.fields['resposta'].choices = [['', '----'], *self.instance.get_opcoes_choices()]

    def processar(self, user):
        self.instance.solicitar(user)


class ExecucaoPlanoLaboratorioForm(forms.ModelFormPlus):
    tipo_cadastro = forms.ChoiceField(
        label='Tipo de cadastro',
        widget=forms.RadioSelect(),
        choices=[['1', 'Documento eletrônico'], ['2', 'Upload de documento'], ['3', 'Link do D.O.U.']],
    )

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'ano',
                    'plano_politica_acesso',
                    'plano_manutencao',
                    'plano_riscos',
                    'plano_residuos',
                    'tipo_cadastro',
                    'id_documento',
                    'arquivo_documento',
                    'url_documento',
                )
            },
        ),
    )

    class Meta:
        model = ExecucaoPlanoLaboratorio
        exclude = ('laboratorio',)

    class Media:
        js = ('/static/edu/js/ExecucaoPlanoLaboratorioForm.js',)

    def __init__(self, *args, **kwargs):
        laboratorio_id = kwargs.pop('laboratorio_id', None)
        super().__init__(*args, **kwargs)
        if laboratorio_id:
            self.instance.laboratorio_id = laboratorio_id

        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            self.fields['id_documento'] = forms.ModelChoiceFieldPlus(
                DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO),
                label='Documento',
                widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
                required=False,
            )

        if self.instance.pk:
            if self.instance.id_documento:
                self.initial['tipo_cadastro'] = '1'
            elif self.instance.arquivo_documento:
                self.initial['tipo_cadastro'] = '2'
            else:
                self.initial['tipo_cadastro'] = '3'

    def clean_id_documento(self):
        documento = self.cleaned_data.get('id_documento')
        return documento and documento.id or None

    def clean(self):
        id_documento = self.cleaned_data.get('id_documento')
        arquivo_documento = self.cleaned_data.get('arquivo_documento')
        url_documento = self.cleaned_data.get('url_documento')
        if id_documento is None and arquivo_documento is None and url_documento is None:
            raise forms.ValidationError('Informe um documento eletrônico ou faça o upload de um documento em pdf ou informe o link do D.O.U.')
        if id_documento and arquivo_documento:
            raise forms.ValidationError('Não pode ser informado simultaneamente um documento eletrônico e um upload de documento.')
        if id_documento and url_documento:
            raise forms.ValidationError('Não pode ser informado simultaneamente um documento eletrônico e um link do D.O.U.')
        if arquivo_documento and url_documento:
            raise forms.ValidationError('Não pode ser informado simultaneamente um upload de documento e um link do D.O.U.')
        return self.cleaned_data

    def processar(self):
        id_documento = self.cleaned_data.get('id_documento')
        arquivo_documento = self.cleaned_data.get('arquivo_documento')
        url_documento = self.cleaned_data.get('url_documento')
        if id_documento:
            self.instance.id_documento = id_documento
        elif arquivo_documento:
            self.instance.arquivo_documento = arquivo_documento
        elif url_documento:
            self.instance.url_documento = url_documento
        self.instance.save()


class LaboratorioForm(forms.ModelFormPlus):
    capacidade = forms.IntegerFieldPlus(
        label='Capacidade da sala',
        help_text='Informe a capacidade máxima de pessoas que o laboratório pode acomodar.',
        required=False,
    )

    area_util = forms.DecimalFieldPlus(
        label='Área útil',
        help_text='Informe a área útil do laboratório em metros quadrados.',
        required=False,
        decimal_places=2,
    )

    class Meta:
        model = Laboratorio
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user = self.request.user
        if not user.has_perm('comum.is_administrador_academico'):
            ids = (
                UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user, usuario_grupo__group__name='Coordenador de Laboratório')
                .values_list('setor__uo_id', flat=True)
                .distinct()
            )
            self.fields['sala'].queryset = Sala.ativas.filter(predio__uo_id__in=ids)

        if self.instance.pk:
            self.initial['capacidade'] = self.instance.sala.capacidade if self.instance.sala else None
            self.initial['area_util'] = self.instance.sala.area_util if self.instance.sala else None

    def save(self, *args, **kwargs):
        sala = self.cleaned_data.get('sala')
        if sala:
            update_sala = False
            capacidade = self.cleaned_data.get('capacidade')
            if capacidade and capacidade != sala.capacidade:
                sala.capacidade = capacidade
                update_sala = True
            area_util = self.cleaned_data.get('area_util')
            if area_util and area_util != sala.area_util:
                sala.area_util = area_util
                update_sala = True
            if update_sala:
                sala.save()
        return super().save(*args, **kwargs)
