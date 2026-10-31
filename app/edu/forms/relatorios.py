import datetime
from collections import OrderedDict
from datetime import date
from operator import itemgetter

from django.apps.registry import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import F
from django.db.models.aggregates import Count
from django.template import defaultfilters

from comum.models import Ano, Configuracao, Raca, Sala, UsuarioGrupoSetor
from comum.utils import get_uo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    CheckboxSelectMultiplePlus,
    TreeWidget,
)
from djtools.html.graficos import ColumnChart, LineChart, PieChart
from djtools.templatetags.filters import format_, format_iterable, in_group
from edu import perms
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    Aula,
    CalendarioAcademico,
    Cidade,
    Componente,
    Convenio,
    CursoCampus,
    Deficiencia,
    Diario,
    Diretoria,
    Disciplina,
    Estado,
    EstruturaCurso,
    FormaIngresso,
    HistoricoRelatorio,
    HorarioAulaDiario,
    HorarioAulaDiarioEspecial,
    LinhaPesquisa,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
    Matriz,
    Modalidade,
    NivelEnsino,
    NucleoCentralEstruturante,
    Polo,
    Professor,
    ProfessorDiario,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    TipoAlunoArquivo,
    TipoMedidaDisciplinar,
    TipoNEE,
    TipoProfessorDiario,
    Turma,
    Turno,
)
from rh.models import JornadaTrabalho, Servidor, Setor, Situacao, UnidadeOrganizacional


class RelatorioForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    SITUACAO_SISTEMA_TODOS = 'TODOS'
    SITUACAO_SISTEMA_SUAP = 'SUAP'
    SITUACAO_SISTEMA_MIGRADOS = 'MIGRADOS'
    SITUACAO_SISTEMA_NAO_MIGRADOS = 'NAO_MIGRADOS'

    uo = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.campi().all(), label='Campus', required=False)
    diretoria = forms.ModelMultiplePopupChoiceField(Diretoria.objects, label='Diretoria', required=False)
    estrutura_curso = forms.ModelMultiplePopupChoiceField(EstruturaCurso.objects, label='Estrutura', required=False)
    modalidade = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidade', required=False)
    convenio = forms.ModelMultiplePopupChoiceField(Convenio.objects, label='Convênio', required=False)
    nivel_ensino = forms.ModelMultiplePopupChoiceField(NivelEnsino.objects, label='Nível de Ensino', required=False)
    matriz = forms.ModelChoiceFieldPlus(Matriz.objects, label='Matriz', required=False)
    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
    )
    situacao_matricula = forms.ModelMultiplePopupChoiceField(SituacaoMatricula.objects, label='Situação da Matrícula', required=False)

    turma = forms.MultipleModelChoiceField(
        Turma.objects,
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS,
            multiple=True,
            form_filters=[('curso_campus', 'curso_campus'), ('uo', 'curso_campus__diretoria__setor__uo__in'), ('polo', 'polo__in')],
        ),
    )

    diario_da_turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Em diário da Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[('curso_campus', 'curso_campus'), ('uo', 'curso_campus__diretoria__setor__uo__in'), ('polo', 'polo__in')],
        ),
    )

    diario = forms.MultipleModelChoiceField(
        Diario.objects,
        label='Diário',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Diario.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('turma', 'turma'),
                ('uo', 'turma__curso_campus__diretoria__setor__uo__in'),
                ('polo', 'turma__polo__in'),
                ('curso_campus', 'turma__curso_campus'),
                ('estrutura_curso', 'turma__matriz__estrutura__in'),
                ('modalidade', 'turma__curso_campus__modalidade__in'),
            ],
        ),
    )

    estado = forms.ModelChoiceFieldPlus(Estado.objects, label='Estado', required=False, widget=AutocompleteWidget(search_fields=Estado.SEARCH_FIELDS))
    cidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Cidade',
        required=False,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS, form_filters=[('estado', 'estado')]),
    )

    situacao_matricula_periodo = forms.ModelMultiplePopupChoiceField(SituacaoMatriculaPeriodo.objects, label='Situação no Período', required=False)
    situacao_diario = forms.ChoiceField(choices=[[0, '----'], *MatriculaDiario.SITUACAO_CHOICES], label='Situação no Diário', required=False)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=False)
    periodo_letivo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=False)
    periodo_referencia = forms.ChoiceField(
        label='Período de Referência Atual', required=False, choices=[[0, '----']] + [[x, x] for x in range(1, 11)]
    )
    periodo_matriz = forms.ChoiceField(label='Período da Matriz', required=False, choices=[[0, '----']] + [[x, x] for x in range(1, 11)])
    aluno_especial = forms.ChoiceField(choices=[['', '----'], *Aluno.TIPO_ALUNO_CHOICES], required=False, label='Tipo de Aluno')

    ano_ingresso_inicio = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de Ingresso a Partir de', required=False)
    ano_ingresso_fim = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de Ingresso Até', required=False)
    periodo_ingresso_inicio = forms.ChoiceField(
        choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de Ingresso a Partir de', required=False
    )
    periodo_ingresso_fim = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de Ingresso Até', required=False)

    forma_ingresso = forms.ModelPopupChoiceField(FormaIngresso.objects, label='Forma de Ingresso', required=False)
    linha_pesquisa = forms.ModelPopupChoiceField(LinhaPesquisa.objects, label='Linha de pesquisa', required=False)

    polo = forms.ModelMultiplePopupChoiceField(Polo.objects, label='Polo', required=False)
    situacao_sistema = forms.ChoiceField(choices=[], label='Situação no Sistema', required=False)

    tipos_documentos = forms.ModelMultiplePopupChoiceField(TipoAlunoArquivo.objects, label='Tipos de Documento', required=False)

    medida_disciplinar = forms.ChoiceField(choices=[], label='Medida Disciplinar', required=False)
    com_qualquer_deficiencia_ou_nee = forms.BooleanField(label='Qualquer Deficiência ou NEE', required=False)

    deficiencias = forms.MultipleModelChoiceField(
        Deficiencia.objects,
        label='Deficiências',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Deficiencia.SEARCH_FIELDS,
            multiple=True,
        ),
    )
    outras_nees = forms.MultipleModelChoiceField(
        TipoNEE.objects,
        label='Outras NEEs',
        required=False,
        widget=AutocompleteWidget(
            search_fields=TipoNEE.SEARCH_FIELDS,
            multiple=True,
        ),
    )

    ano_conclusao = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano de Conclusão', required=False)

    turno = forms.ModelChoiceField(Turno.objects, label='Turno', required=False)

    percentual_conclusao_curso_inicial = forms.IntegerField(label='Percentual de Progresso Inicial', max_value=100, min_value=0, required=False)
    percentual_conclusao_curso_final = forms.IntegerField(label='Percentual de Progresso Final', max_value=100, min_value=0, required=False)

    ch_maior_20h = forms.BooleanField(label='Cursos com CH maior ou igual a 20h', required=False)

    formatacao = forms.ChoiceField(
        choices=[
            ['simples', 'Listagem Simples'],
            ['educacenso', 'Relatório Educacenso'],
            ['censup', 'Relatório Censup'],
            ['tcc', 'Relatório de TCCs'],
            ['pordisciplinacursando', 'Relatório de Disciplinas Cursando'],
            ['pordisciplinapendente', 'Relatório de Disciplinas Pendentes'],
            ['pe_de_meia', 'Programa Pé-de-Meia'],
            ['relatorio_conselho_classe', 'Relatório para Conselho de Classe'],
        ],
        label='Tipo',
        help_text='O tipo de formatação "Listagem Simples" permitirá a impressão de etiquetas, carômetros e assinatura dos alunos.',
    )
    quantidade_itens = forms.ChoiceField(choices=[[25, '25'], [50, '50'], [100, '100'], [200, '200'], [500, '500']], label='Quantidade de Itens')
    ordenacao = forms.ChoiceField(choices=[['Nome', 'Nome'], ['Matrícula', 'Matrícula']], label='Ordenação')
    agrupamento = forms.ChoiceField(choices=[['Campus', 'Campus'], ['Curso', 'Curso'], ['Turma', 'Turma']], label='Agrupamento')
    EXIBICAO_CHOICES = [
        ['curso_campus.diretoria.setor.uo', 'Campus'],
        ['curso_campus.codigo', 'Código Curso'],
        ['curso_campus.descricao', 'Descrição do Curso'],
        ['situacao', 'Situação no Curso'],
        ['get_situacao_periodo_referencia', 'Situação no Período'],
        ['get_frequencia_periodo_referencia', 'Frequência no Período'],
        ['get_media_final_periodo_referencia', 'Média Final no Período'],
        ['get_ultima_matricula_periodo.turma', 'Turma'],
        ['email_academico', 'Email Acadêmico'],
        ['email_google_classroom', 'Email Google Classroom'],
        ['polo', 'Polo'],
        ['nacionalidade', 'Nacionalidade'],
        ['pais_origem', 'País de Origem'],
        ['ano_letivo', 'Ano de Ingresso'],
        ['periodo_letivo', 'Período de Ingresso'],
        ['data_matricula', 'Data de Matrícula'],
        ['data_inicio_ciclo', 'Data de Início do Ciclo'],
        ['turno', 'Turno'],
        ['forma_ingresso', 'Forma de Ingresso'],
        ['linha_pesquisa', 'Linha de pesquisa'],
        ['cota_sistec', 'Cota Sistec'],
        ['codigo_sistec', 'Código Sistec'],
        ['get_codigo_sgp', 'Último Código SGP'],
        ['cota_mec', 'Cota MEC'],
        ['convenio', 'Convênio'],
        ['data_conclusao_intercambio', 'Data de Conclusão do Intercâmbio'],
        ['matriz', 'Matriz'],
        ['dt_conclusao_curso', 'Data de Conclusão de Curso'],
        ['ano_conclusao_estudo_anterior', 'Ano de Conclusão do Ensino Anterior'],
        ['ano_let_prev_conclusao', 'Ano Letivo de Previsão de Conclusão'],
        ['tipo_instituicao_origem', 'Tipo de Escola de Origem'],
        ['periodo_atual', 'Período Atual'],
        ['data_integralizacao', 'Data de Integralização'],
        ['ano_letivo_integralizacao', 'Ano Letivo de Integralização'],
        ['periodo_letivo_integralizacao', 'Período Letivo de Integralização'],
        ['pendencias', 'Pendências de Requisitos de Conclusão'],
        ['raca', 'Etnia/Raça'],
        ['codigo_educacenso', 'Código Educacenso'],
        ['get_data_ultimo_procedimento_periodo_referencia', 'Data do Último Procedimento'],
        ['curso_campus.diretoria', 'Diretoria'],
        ['numero_pasta', 'Nº da Pasta'],
        ['curso_campus.modalidade', 'Modalidade'],
        ['curso_campus.modalidade.nivel_ensino', 'Nível de Ensino'],
        ['get_poder_publico_responsavel_transporte_display', 'Transporte Escolar: Poder Público'],
        ['percentual_ch_cumprida', 'Percentual de Progresso'],
        ['get_tipo_veiculo_display', 'Transporte Escolar: Tipo de Veículo'],
        ['get_projeto_final_aprovado.data_defesa', 'Data previsa de defesa do TCC'],
        ['get_projeto_final_aprovado.resultado_data', 'Data da defesa do TCC'],
        ['matriz.natureza_participacao', 'Natureza de Participação'],
        ['candidato_vaga.candidato.edital', 'Edital de Ingresso'],
        ['ano_conclusao', 'Ano de Conclusão'],
        ['get_tipo_diploma', 'Tipo do Diploma (Digital/Físico)'],
        ['get_dados_emissao_diploma', 'Registro de Emissão de Diploma'],
        ['get_tipos_documentos_cadastrados', 'Pasta Documental'],
        ['get_dados_processo_seletivo', 'Dados do Processo Seletivo'],
        ['data_expedicao_diploma', 'Data de Expedição do Diploma'],
    ]

    EXIBICAO_COMUNICACAO = [['email_pessoal', 'Email Pessoal']]

    EXIBICAO_DADOS_PESSOAIS = [
        ['pessoa_fisica.cpf', 'CPF'],
        ['pessoa_fisica.passaporte', 'Passaporte'],
        ['pessoa_fisica.nascimento_data', 'Data de Nascimento'],
        ['get_endereco', 'Endereço'],
        ['cidade', 'Município de Residência'],
        ['cidade.codigo', 'Município de Residência (Código IBGE)'],
        ['get_rg', 'RG'],
        ['get_telefones', 'Telefone'],
        ['pessoa_fisica.sexo', 'Sexo'],
        ['pessoa_fisica.genero', 'Gênero'],
        ['estado_civil', 'Estado Civil'],
        ['nome_pai', 'Nome do Pai'],
        ['nome_mae', 'Nome da Mãe'],
        ['pessoa_fisica.nome_social', 'Nome Social'],
        ['responsavel', 'Responsável'],
        ['email_responsavel', 'Email do Responsável'],
        ['naturalidade', 'Naturalidade'],
        ['naturalidade.codigo', 'Naturalidade (Código IBGE)'],
        ['ira', 'I.R.A.'],
        ['caracterizacao.renda_per_capita', 'Renda Per Capita'],
        ['observacao_historico', 'Observação Histórico'],
        ['cidade.nome', 'Cidade'],
        ['deficiencias', 'Deficiências'],
        ['outras_nees', 'Outras NEEs'],
        ['cidade.estado.get_sigla', 'Estado'],
        ['get_chave_responsavel', 'Chave do Responsável'],
        ['get_observacoes', 'Observações'],
        ['get_tipo_zona_residencial_display', 'Zona Residencial'],
        ['bairro', 'Bairro'],
    ]

    EXIBICAO_INICIAS = [
        ['curso_campus.diretoria.setor.uo', 'Campus'],
        ['curso_campus.codigo', 'Código Curso'],
        ['curso_campus.descricao', 'Descrição do Curso'],
        ['situacao', 'Situação no Curso'],
        ['get_situacao_periodo_referencia', 'Situação no Período'],
    ]

    PENDENCIAS_EXIBICAO_CHOICES = [
        ('pendencia_pratica_profissional', 'Prática Profissional Pendente'),
        ('pendencia_colacao_grau', 'Colação de Grau Pendente'),
        ('pendencia_ch_atividade_complementar', 'Atividades Complementares Pendente'),
        ('pendencia_ch_tcc', 'Carga Horária de TCC Pendente'),
        ('pendencia_ch_pratica_profissional', 'Carga Horária de Prática Profissional Pendente'),
        ('pendencia_tcc', 'Registro de TCC Pendente'),
        ('pendencia_ch_seminario', 'Carga Horária de Seminário Pendente'),
        ('pendencia_ch_eletiva', 'Carga Horária Eletiva Pendente'),
        ('pendencia_ch_optativa', 'Carga Horária Optativa Pendente'),
        ('pendencia_ch_obrigatoria', 'Carga Horária Obrigatória Pendente'),
        ('pendencia_enade', 'Registro do ENADE'),
    ]

    exibicao = forms.MultipleChoiceField(label='Campos Adicionais', choices=[], widget=CheckboxSelectMultiplePlus(), required=False)

    PENDENCIA_CHOICES = [
        ('colacao_grau', 'Colação de Grau'),
        ('pratica_profissional', 'Prática Profissional'),
        ('tcc', 'Trabalho de conclusão de curso - TCC'),
        ('seminarios', 'Carga Horária de Seminário'),
        ('disciplinas_optativa', 'Carga Horária Optativa'),
        ('enad', 'Registro de ENADE'),
        ('atividades_complementares', 'Atividades Complementares'),
    ]

    pendencias = forms.ChoiceField(
        label='Requisitos de Conclusão Pendentes (apenas)', choices=[('', '--------------'), *PENDENCIA_CHOICES], required=False
    )

    fieldsets = (
        (
            'Filtros de Pesquisa',
            {
                'fields': (
                    ('uo', 'diretoria'),
                    ('estrutura_curso', 'modalidade'),
                    ('convenio', 'polo'),
                    ('estado', 'cidade'),
                    ('matriz', 'curso_campus'),
                    ('turma', 'diario', 'diario_da_turma'),
                    ('ano_letivo', 'periodo_letivo', 'periodo_matriz'),
                    ('periodo_referencia', 'ano_conclusao'),
                    ('situacao_diario', 'turno'),
                    ('situacao_matricula', 'situacao_matricula_periodo'),
                    ('ano_ingresso_inicio', 'periodo_ingresso_inicio'),
                    ('ano_ingresso_fim', 'periodo_ingresso_fim'),
                    ('forma_ingresso', 'linha_pesquisa'),
                    ('aluno_especial', 'situacao_sistema'),
                    ('tipos_documentos', 'medida_disciplinar'),
                    ('ch_maior_20h',),
                )
            },
        ),
        ('Percentual de Progresso', {'fields': (('percentual_conclusao_curso_inicial', 'percentual_conclusao_curso_final'),)}),
        (
            'Deficiências e outras NEEs',
            {'fields': ('com_qualquer_deficiencia_ou_nee', 'deficiencias', 'outras_nees')},
        ),
        ('Requisitos de Conclusão', {'fields': ('pendencias',)}),
        ('Formatação', {'fields': ('formatacao', ('quantidade_itens', 'ordenacao', 'agrupamento'))}),
        ('Exibição', {'fields': (('exibicao',),)}),
    )

    class Media:
        js = ('/static/edu/js/RelatorioForm.js',)

    @staticmethod
    def get_exibiacao_choices(request):
        exibicao_final_choices = []
        exibicao_final_choices.extend(RelatorioForm.EXIBICAO_CHOICES)
        if request.user.has_perm('edu.view_dados_pessoais'):
            exibicao_final_choices.extend(RelatorioForm.EXIBICAO_DADOS_PESSOAIS)

        if in_group(
            request.user,
            'Assistente Social, Coordenador de Atividades Estudantis, Coordenador de Atividades Estudantis Sistêmico, Coordenador de Curso, '
            'Coordenador de Egressos, Coordenador de Egressos Sistêmico, Coordenador de Estágio, Coordenador de Estágio Sistêmico, '
            'Administrador Acadêmico, Secretário Acadêmico,Diretor Acadêmico, Pedagogo',
        ):
            exibicao_final_choices.extend(RelatorioForm.EXIBICAO_COMUNICACAO)

        return sorted(exibicao_final_choices, key=itemgetter(1))

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['situacao_sistema'].choices = [
            [RelatorioForm.SITUACAO_SISTEMA_TODOS, 'Todos'],
            [RelatorioForm.SITUACAO_SISTEMA_SUAP, 'Alunos que iniciaram no SUAP'],
            [RelatorioForm.SITUACAO_SISTEMA_MIGRADOS, f'Alunos migrados do {Configuracao.get_valor_por_chave("edu", "academico_nome_sistema")}'],
            [
                RelatorioForm.SITUACAO_SISTEMA_NAO_MIGRADOS,
                f'Alunos NÃO migrados do {Configuracao.get_valor_por_chave("edu", "academico_nome_sistema")}',
            ],
        ]

        setor = getattr(request.user.get_vinculo(), 'setor', None)
        uo = setor and setor.uo or None

        if uo and not in_group(request.user, 'Administrador Acadêmico'):
            self.fields['uo'].initial = [uo.pk]

        self.fields['exibicao'].choices = RelatorioForm.get_exibiacao_choices(request)
        self.fields['exibicao'].initial = [campo[0] for campo in self.EXIBICAO_INICIAS]

        self.fields['curso_campus'].queryset = self.fields['curso_campus'].queryset.all()
        self.fields['situacao_matricula'].queryset = self.fields['situacao_matricula'].queryset.exclude(
            pk__in=(
                SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
                SituacaoMatricula.CERTIFICADO_ENEM,
                SituacaoMatricula.AGUARDANDO_SEMINARIO,
                SituacaoMatricula.AGUARDANDO_ENADE,
                SituacaoMatricula.TRANSFERIDO_SUAP,
            )
        )

        if request.user.has_perm('edu.view_medidadisciplinar'):
            self.fields['medida_disciplinar'].choices = [[0, '---------'], ['TODOS', 'Todos']] + [
                [tipo.pk, tipo.descricao] for tipo in TipoMedidaDisciplinar.objects.all()
            ]
        else:
            self.fields['medida_disciplinar'].widget = forms.HiddenInput()

        formatacao_choices = []
        if perms.pode_ver_dados_anonimos_aluno(request.user):
            for choice in self.fields['formatacao'].choices:
                _, valor = choice
                if 'Resumo' in valor:
                    if request.user.is_superuser or in_group(request.user, 'Administrador Acadêmico'):
                        formatacao_choices.append(choice)
                else:
                    formatacao_choices.append(choice)
        else:
            formatacao_choices = [
                ['simples', 'Listagem Simples'],
            ]
        self.fields['formatacao'].choices = formatacao_choices

    def get_periodo(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo'] or 0
        if ano_letivo and int(periodo_letivo):
            return [ano_letivo, periodo_letivo]

    def processar(self):
        qs = MatriculaPeriodo.objects.exclude(aluno__participanteturmaminicurso__turma__gerar_matricula=False)

        uo = self.cleaned_data['uo']
        diretoria = self.cleaned_data['diretoria']
        estrutura_curso = self.cleaned_data['estrutura_curso']
        modalidade = self.cleaned_data['modalidade']
        convenio = self.cleaned_data['convenio']
        matriz = self.cleaned_data['matriz']
        curso_campus = self.cleaned_data['curso_campus']
        diario = self.cleaned_data['diario']
        situacao_matricula = self.cleaned_data['situacao_matricula']
        turma = self.cleaned_data['turma']
        diario_da_turma = self.cleaned_data['diario_da_turma']
        cidade = self.cleaned_data['cidade']
        estado = self.cleaned_data['estado']
        situacao_matricula_periodo = self.cleaned_data['situacao_matricula_periodo']
        percentual_conclusao_curso_inicial = self.cleaned_data['percentual_conclusao_curso_inicial']
        percentual_conclusao_curso_final = self.cleaned_data['percentual_conclusao_curso_final']
        situacao_diario = self.cleaned_data['situacao_diario'] or 0
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo'] or 0
        ano_ingresso_inicio = self.cleaned_data['ano_ingresso_inicio']
        ano_ingresso_fim = self.cleaned_data['ano_ingresso_fim']
        periodo_ingresso_inicio = self.cleaned_data['periodo_ingresso_inicio'] or 0
        periodo_ingresso_fim = self.cleaned_data['periodo_ingresso_fim'] or 0
        periodo_referencia = self.cleaned_data['periodo_referencia'] or 0
        periodo_matriz = self.cleaned_data['periodo_matriz'] or 0
        forma_ingresso = self.cleaned_data['forma_ingresso']
        linha_pesquisa = self.cleaned_data['linha_pesquisa']
        turno = self.cleaned_data['turno']
        polo = self.cleaned_data['polo']
        aluno_especial = self.cleaned_data['aluno_especial']
        situacao_sistema = self.cleaned_data['situacao_sistema']
        medida_disciplinar = self.cleaned_data['medida_disciplinar']
        tipos_documentos = self.cleaned_data['tipos_documentos']
        ch_maior_20h = self.cleaned_data['ch_maior_20h']
        deficiencias = self.cleaned_data['deficiencias']
        outras_nees = self.cleaned_data['outras_nees']
        ano_conclusao = self.cleaned_data['ano_conclusao']
        pendencias = self.cleaned_data['pendencias']
        com_qualquer_deficiencia_ou_nee = self.cleaned_data['com_qualquer_deficiencia_ou_nee']
        filtros = []

        if uo:
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo__in=uo)
            filtros.append({'chave': 'Campus', 'valor': format_iterable(uo)})
        if diretoria:
            qs = qs.filter(aluno__curso_campus__diretoria__in=diretoria)
            filtros.append({'chave': 'Diretoria', 'valor': format_iterable(diretoria)})
        if estrutura_curso:
            qs = qs.filter(aluno__matriz__estrutura__id__in=estrutura_curso)
            filtros.append({'chave': 'Estrutura de Curso', 'valor': format_iterable(estrutura_curso)})
        if modalidade:
            qs = qs.filter(aluno__curso_campus__modalidade__id__in=modalidade)
            filtros.append({'chave': 'Modalidade', 'valor': format_iterable(modalidade)})
        if convenio:
            qs = qs.filter(aluno__convenio__id__in=convenio)
            filtros.append({'chave': 'Convênio', 'valor': format_iterable(convenio)})
        if situacao_matricula:
            qs = qs.filter(aluno__situacao__id__in=situacao_matricula)
            filtros.append({'chave': 'Situação no Curso', 'valor': format_iterable(situacao_matricula)})
        if matriz:
            qs = qs.filter(aluno__matriz=matriz)
            filtros.append({'chave': 'Matriz', 'valor': str(matriz)})
        if curso_campus:
            qs = qs.filter(aluno__curso_campus=curso_campus)
            filtros.append({'chave': 'Curso', 'valor': str(curso_campus)})
        if diario and not int(situacao_diario):
            qs = qs.filter(matriculadiario__diario__in=diario)
            filtros.append({'chave': 'Diário', 'valor': format_iterable(diario)})
        if turma:
            qs = qs.filter(turma__in=turma)
            filtros.append({'chave': 'Turma', 'valor': format_iterable(turma)})
        if diario_da_turma:
            qs = qs.filter(aluno__curso_campus__ativo=True, matriculadiario__diario__turma=diario_da_turma).exclude(
                matriculadiario__situacao=MatriculaDiario.SITUACAO_TRANSFERIDO
            )
            filtros.append({'chave': 'Em diário da Turma', 'valor': str(diario_da_turma)})
        if cidade:
            qs = qs.filter(aluno__cidade=cidade)
            filtros.append({'chave': 'Cidade', 'valor': str(cidade)})
        if estado:
            qs = qs.filter(aluno__cidade__estado=estado)
            filtros.append({'chave': 'Estado', 'valor': str(estado)})
        if situacao_matricula_periodo:
            qs = qs.filter(situacao__id__in=situacao_matricula_periodo)
            filtros.append({'chave': 'Situação no Período', 'valor': format_iterable(situacao_matricula_periodo)})
        if (percentual_conclusao_curso_inicial and percentual_conclusao_curso_inicial >= 0) or (
            percentual_conclusao_curso_final and percentual_conclusao_curso_final <= 100
        ):
            percentual_conclusao_curso_inicial = percentual_conclusao_curso_inicial or 0
            percentual_conclusao_curso_final = percentual_conclusao_curso_final or 100
            qs = qs.filter(
                aluno__percentual_ch_cumprida__gte=percentual_conclusao_curso_inicial,
                aluno__percentual_ch_cumprida__lte=percentual_conclusao_curso_final,
            )
            filtros.append(
                {'chave': 'Percentual de Progresso', 'valor': f'{percentual_conclusao_curso_inicial}% a {percentual_conclusao_curso_final}% '}
            )
        if int(situacao_diario) and not diario:
            qs = qs.filter(aluno__curso_campus__ativo=True, matriculadiario__situacao=situacao_diario)
            filtros.append({'chave': 'Situação no Diário', 'valor': str(situacao_diario)})
        if int(situacao_diario) and diario:
            qs = qs.filter(aluno__curso_campus__ativo=True, matriculadiario__diario__in=diario, matriculadiario__situacao=situacao_diario)
            pks = list(diario.values_list('pk', flat=True))
            filtros.append({'chave': f'Situação no Diário {pks}', 'valor': str(situacao_diario)})
        if ano_letivo:
            qs = qs.filter(ano_letivo=ano_letivo)
            filtros.append({'chave': 'Ano Letivo', 'valor': str(ano_letivo)})
        if int(periodo_letivo):
            qs = qs.filter(periodo_letivo=periodo_letivo)
            filtros.append({'chave': 'Período Letivo', 'valor': str(periodo_letivo)})
        if int(periodo_matriz):
            qs = qs.filter(periodo_matriz=periodo_matriz)
            filtros.append({'chave': 'Período da Matriz', 'valor': str(periodo_matriz)})
        if ano_conclusao:
            qs = qs.filter(aluno__ano_conclusao=ano_conclusao.ano)
            filtros.append({'chave': 'Ano de Conclusão', 'valor': str(ano_conclusao)})
        if int(periodo_referencia):
            qs = qs.filter(aluno__periodo_atual=periodo_referencia)
            filtros.append({'chave': 'Período de Referência', 'valor': str(periodo_referencia)})
        if ano_ingresso_inicio:
            qs = qs.filter(aluno__ano_letivo__ano__gte=ano_ingresso_inicio.ano)
            filtros.append({'chave': 'Ano de Ingresso a Partir de', 'valor': str(ano_ingresso_inicio)})
            if int(periodo_ingresso_inicio) == 2:
                qs = qs.exclude(aluno__ano_letivo=ano_ingresso_inicio, aluno__periodo_letivo=1)
            if int(periodo_ingresso_inicio) != 0:
                filtros.append({'chave': 'Período de Ingresso a Partir de', 'valor': int(periodo_ingresso_inicio)})
        if ano_ingresso_fim:
            qs = qs.filter(aluno__ano_letivo__ano__lte=ano_ingresso_fim.ano)
            filtros.append({'chave': 'Ano de Ingresso Até', 'valor': str(ano_ingresso_fim)})
            if int(periodo_ingresso_fim) == 1:
                qs = qs.exclude(aluno__ano_letivo=ano_ingresso_fim, aluno__periodo_letivo=2)
            if int(periodo_ingresso_fim) != 0:
                filtros.append({'chave': 'Período de Ingresso Até', 'valor': int(periodo_ingresso_fim)})
        if forma_ingresso:
            qs = qs.filter(aluno__forma_ingresso=forma_ingresso)
            filtros.append({'chave': 'Forma de Ingresso', 'valor': str(forma_ingresso)})
        if linha_pesquisa:
            qs = qs.filter(aluno__linha_pesquisa=linha_pesquisa)
            filtros.append({'chave': 'Linha de pesquisa', 'valor': str(linha_pesquisa)})
        if turno:
            qs = qs.filter(aluno__turno=turno)
            filtros.append({'chave': 'Turno', 'valor': str(turno)})
        if polo:
            qs = qs.filter(aluno__polo__in=polo)
            filtros.append({'chave': 'Polo', 'valor': format_iterable(polo)})
        if aluno_especial:
            if aluno_especial == 'Especial':
                qs = qs.filter(aluno__aluno_especial=True)
            if aluno_especial == 'Regular':
                qs = qs.filter(aluno__aluno_especial=False)
            filtros.append({'chave': 'Aluno Especial', 'valor': format_(aluno_especial)})
        if situacao_sistema and situacao_sistema != self.SITUACAO_SISTEMA_TODOS:
            academico_nome_sistema = {Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema')}
            if situacao_sistema == self.SITUACAO_SISTEMA_SUAP:
                qs = qs.filter(aluno__matriz__isnull=False, aluno__data_integralizacao__isnull=True)
                filtros.append({'chave': 'Situação no Sistema', 'valor': 'Alunos que iniciaram no SUAP'})
            elif situacao_sistema == self.SITUACAO_SISTEMA_MIGRADOS:
                qs = qs.filter(aluno__matriz__isnull=False, aluno__data_integralizacao__isnull=False)
                filtros.append({'chave': 'Situação no Sistema', 'valor': f'Alunos migrados do {academico_nome_sistema}'})
            elif situacao_sistema == self.SITUACAO_SISTEMA_NAO_MIGRADOS:
                qs = qs.filter(aluno__matriz__isnull=True, aluno__data_integralizacao__isnull=True)
                filtros.append({'chave': 'Situação no Sistema', 'valor': f'Alunos NÃO migrados do {academico_nome_sistema}'})

        if tipos_documentos:
            qs = qs.filter(aluno__alunoarquivo__tipo__in=tipos_documentos)
            filtros.append({'chave': 'Tipos de Documento', 'valor': ', '.join([tmp.nome for tmp in tipos_documentos])})

        if ch_maior_20h:
            qs = qs.exclude(aluno__curso_campus__ch_total__lt=20)  # mantém minicursos com CH maior ou igual a 20h e cursos regulares
            filtros.append({'chave': 'CH maior ou igual a 20h', 'valor': 'Sim'})

        if medida_disciplinar and medida_disciplinar != '0':
            if medida_disciplinar == 'TODOS':
                qs = qs.filter(aluno__medidadisciplinar__isnull=False)
            else:
                qs = qs.filter(aluno__medidadisciplinar__tipo=medida_disciplinar)
            filtros.append({'chave': 'Medida Disciplinar', 'valor': format_(medida_disciplinar)})

        if com_qualquer_deficiencia_ou_nee:
            qs = qs.filter(aluno__deficiencias__isnull=False) | qs.filter(aluno__outras_nees__isnull=False)
            filtros.append({'chave': 'Qualquer Deficiência ou NEE', 'valor': 'Sim'})

        if deficiencias:
            qs = qs.filter(aluno__deficiencias__in=deficiencias)
            filtros.append({'chave': 'Deficiências', 'valor': format_iterable(deficiencias)})

        if outras_nees:
            qs = qs.filter(aluno__outras_nees__in=outras_nees)
            filtros.append({'chave': 'Outras NEEs', 'valor': format_iterable(outras_nees)})

        if pendencias:
            d = {
                'aluno__pendencia_tcc': True,
                'aluno__pendencia_enade': True,
                'aluno__pendencia_pratica_profissional': True,
                'aluno__pendencia_colacao_grau': True,
                'aluno__pendencia_ch_atividade_complementar': True,
                'aluno__pendencia_ch_tcc': True,
                'aluno__pendencia_ch_pratica_profissional': True,
                'aluno__pendencia_ch_seminario': True,
                'aluno__pendencia_ch_eletiva': True,
                'aluno__pendencia_ch_optativa': True,
                'aluno__pendencia_ch_obrigatoria': True,
            }
            if pendencias == 'colacao_grau':
                del d['aluno__pendencia_colacao_grau']
                qs1 = qs.filter(aluno__situacao=SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU)
                qs2 = qs.exclude(aluno__situacao=SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU)
                for lookup in d:
                    qs2 = qs2.exclude(**{lookup: True})
                qs2 = qs2.filter(aluno__pendencia_colacao_grau=True)
                qs = qs1 | qs2
                pendencias = 'Aguardando colação de grau'
            elif pendencias == 'pratica_profissional':
                del d['aluno__pendencia_colacao_grau']
                del d['aluno__pendencia_ch_pratica_profissional']
                del d['aluno__pendencia_pratica_profissional']
                for lookup in d:
                    qs = qs.exclude(**{lookup: True})
                qs = qs.filter(aluno__pendencia_ch_pratica_profissional=True) | qs.filter(aluno__pendencia_pratica_profissional=True)
                pendencias = 'Prática profissional pendente'
            elif pendencias == 'tcc':
                del d['aluno__pendencia_colacao_grau']
                del d['aluno__pendencia_tcc']
                del d['aluno__pendencia_ch_tcc']
                for lookup in d:
                    qs = qs.exclude(**{lookup: True})
                qs = qs.filter(aluno__pendencia_tcc=True) | qs.filter(aluno__pendencia_ch_tcc=True)
                pendencias = 'Trabalho de conclusão de curso (TCC) endente'
            elif pendencias == 'seminarios':
                del d['aluno__pendencia_colacao_grau']
                del d['aluno__pendencia_ch_seminario']
                qs1 = qs.filter(aluno__situacao=SituacaoMatricula.AGUARDANDO_SEMINARIO)
                qs2 = qs.exclude(aluno__situacao=SituacaoMatricula.AGUARDANDO_SEMINARIO)
                for lookup in d:
                    qs2 = qs2.exclude(**{lookup: True})
                qs2 = qs2.filter(aluno__pendencia_ch_seminario=True)
                qs = qs1 | qs2
                pendencias = 'Seminários pendentes'
            elif pendencias == 'disciplinas_optativa':
                del d['aluno__pendencia_colacao_grau']
                del d['aluno__pendencia_ch_optativa']
                for lookup in d:
                    qs = qs.exclude(**{lookup: True})
                qs = qs.filter(aluno__pendencia_ch_optativa=True)
                pendencias = 'Carga horária de disciplinas optativas pendentes'
            elif pendencias == 'enad':
                del d['aluno__pendencia_colacao_grau']
                del d['aluno__pendencia_enade']
                qs1 = qs.filter(aluno__situacao=SituacaoMatricula.AGUARDANDO_ENADE)
                qs2 = qs.exclude(aluno__situacao=SituacaoMatricula.AGUARDANDO_ENADE)
                for lookup in d:
                    qs2 = qs2.exclude(**{lookup: True})
                qs2 = qs2.filter(aluno__pendencia_enade=True)
                qs = qs1 | qs2
                pendencias = 'Registro de participação/dispensa do ENAD pendente'
            elif pendencias == 'atividades_complementares':
                del d['aluno__pendencia_colacao_grau']
                del d['aluno__pendencia_ch_atividade_complementar']
                for lookup in d:
                    qs = qs.exclude(**{lookup: True})
                qs = qs.filter(aluno__pendencia_ch_atividade_complementar=True)
                pendencias = 'Carga horária de atividades complementares pendentes'
            filtros.append({'chave': 'Pendências', 'valor': pendencias})

        # open('/tmp/query.txt', 'w').write(str(qs.query))
        alunos = Aluno.objects.filter(id__in=qs.order_by('aluno__id').values_list('aluno__id', flat=True).distinct())

        alunos = alunos.select_related('curso_campus', 'curso_campus__diretoria__setor__uo', 'pessoa_fisica')

        return alunos, filtros

    def clean(self):
        cleaned_data = super().clean()
        formatacao = cleaned_data.get('formatacao')
        ano_letivo = cleaned_data.get('ano_letivo')
        periodo_letivo = cleaned_data.get('periodo_letivo')

        if formatacao == 'relatorio_conselho_classe':
            if not ano_letivo:
                self.add_error('ano_letivo', 'Informe o ano letivo')
            if not periodo_letivo or periodo_letivo == '0':
                self.add_error('periodo_letivo', 'Informe o período letivo')

        return cleaned_data


class RelatorioDependenteForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    PERIODO_CURSO_CHOICES = [[x, x] for x in range(1, 13)]

    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.locals,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('diretoria', 'diretoria'), ('modalidade', 'modalidade')]),
    )
    periodo_matriz = forms.ChoiceField(choices=[[0, '----'], *PERIODO_CURSO_CHOICES], label='Período da Matriz', required=False)

    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.none(), label='Campus', required=False)
    diretoria = forms.ModelChoiceFieldPlus(Diretoria.objects.none(), label='Diretoria', required=False)
    modalidade = forms.ModelChoiceFieldPlus(Modalidade.objects, label='Modalidade', required=False)
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[('diretoria', 'curso_campus__diretoria'), ('curso_campus', 'curso_campus'), ('modalidade', 'curso_campus__modalidade')],
        ),
    )

    diario = forms.ModelChoiceFieldPlus(
        Diario.objects,
        label='Diário',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Diario.SEARCH_FIELDS,
            form_filters=[
                ('diretoria', 'turma__curso_campus__diretoria'),
                ('curso_campus', 'turma__curso_campus'),
                ('turma', 'turma'),
                ('modalidade', 'turma__curso_campus__modalidade'),
            ],
        ),
        help_text='Para encontrar um diário entre com a sigla do componente ou o código do diário.',
    )

    componente = forms.ModelChoiceFieldPlus(
        Componente.objects,
        label='Componente',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Componente.SEARCH_FIELDS,
            form_filters=[('uo', 'componentecurricular__matriz__matrizcurso__curso_campus__diretoria__setor__uo')],
        ),
    )

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo')
    situacao = forms.MultipleModelChoiceField(
        SituacaoMatriculaPeriodo.objects, label='Situação no Período', required=False, initial=[SituacaoMatriculaPeriodo.DEPENDENCIA]
    )

    fieldsets = (
        ('Período', {'fields': (('ano_letivo', 'periodo_letivo'), ('situacao', 'periodo_matriz'))}),
        ('Filtros de Pesquisa', {'fields': ('uo', 'diretoria', 'modalidade', 'curso_campus', 'turma', 'diario', 'componente')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['situacao'].queryset = SituacaoMatriculaPeriodo.objects.filter(
            id__in=[SituacaoMatriculaPeriodo.DEPENDENCIA, SituacaoMatriculaPeriodo.REPROVADO, SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA]
        )
        self.fields['uo'].queryset = UnidadeOrganizacional.locals.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)
        self.fields['diretoria'].queryset = Diretoria.locals.all()
        self.fields['curso_campus'].queryset = CursoCampus.locals.filter(diretoria__in=Diretoria.locals.values_list('id', flat=True))
        self.fields['turma'].queryset = Turma.locals.all()
        self.fields['diario'].queryset = Diario.locals.all()
        if 'ae' in settings.INSTALLED_APPS:
            BeneficioGovernoFederal = apps.get_model('ae', 'BeneficioGovernoFederal')
            ProgramaSocial = apps.get_model('ae', 'Programa')
            self.fields['beneficio'] = forms.ModelChoiceField(
                BeneficioGovernoFederal.objects.all(),
                label='Programa Social',
                required=False,
                help_text='O aluno deverá ter informado a participação no programa social em sua caracterização social.',
            )
            self.fields['programa'] = forms.ModelMultiplePopupChoiceField(
                ProgramaSocial.objects.all(),
                label='Programa de Assistência Estudantil',
                required=False,
                help_text='Serão exibidos todos os alunos com participação ativa ou inativa nos programas selecionados',
            )
            self.fieldsets = (*self.fieldsets, ('Filtros Adicionais', {'fields': ('beneficio', 'programa')}))

        if self.fields['uo'].queryset.count() == 1:
            self.fields['uo'].initial = self.fields['uo'].queryset.values_list('pk', flat=True).first()

    def clean(self):
        filtros = []
        qs = MatriculaDiario.objects.all()
        qs_resumida = MatriculaDiarioResumida.objects.all()

        uo = self.cleaned_data.get('uo')
        diretoria = self.cleaned_data.get('diretoria')
        curso_campus = self.cleaned_data.get('curso_campus')
        periodo_matriz = self.cleaned_data.get('periodo_matriz')
        modalidade = self.cleaned_data.get('modalidade')
        turma = self.cleaned_data.get('turma')
        diario = self.cleaned_data.get('diario')
        componente = self.cleaned_data.get('componente')
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        situacao = self.cleaned_data.get('situacao')
        programa = self.cleaned_data.get('programa')
        beneficio = self.cleaned_data.get('beneficio')

        if uo:
            qs = qs.filter(matricula_periodo__aluno__curso_campus__diretoria__setor__uo=uo)
            qs_resumida = qs_resumida.filter(matricula_periodo__aluno__curso_campus__diretoria__setor__uo=uo)
            filtros.append({'chave': 'Campus', 'valor': uo})
        if diretoria:
            qs = qs.filter(matricula_periodo__aluno__curso_campus__diretoria=diretoria)
            qs_resumida = qs_resumida.filter(matricula_periodo__aluno__curso_campus__diretoria=diretoria)
            filtros.append({'chave': 'Diretoria', 'valor': diretoria})
        if curso_campus:
            qs = qs.filter(matricula_periodo__aluno__curso_campus=curso_campus)
            qs_resumida = qs_resumida.filter(matricula_periodo__aluno__curso_campus=curso_campus)
            filtros.append({'chave': 'Curso', 'valor': curso_campus})
        if modalidade:
            qs = qs.filter(matricula_periodo__aluno__curso_campus__modalidade=modalidade)
            qs_resumida = qs_resumida.filter(matricula_periodo__aluno__curso_campus__modalidade=modalidade)
            filtros.append({'chave': 'Modalidade', 'valor': modalidade})
        if turma:
            qs = qs.filter(matricula_periodo__turma=turma)
            qs_resumida = qs_resumida.filter(matricula_periodo__turma=turma)
            filtros.append({'chave': 'Turma', 'valor': turma})
        if diario:
            qs = qs.filter(diario=diario)
            filtros.append({'chave': 'Diário', 'valor': diario})
        if componente:
            qs = qs.filter(diario__componente_curricular__componente=componente)
            filtros.append({'chave': 'Componente', 'valor': componente})
        if not filtros:
            raise forms.ValidationError('Por favor, selecione, um campus, diretoria, curso, turma ou diário.')

        if int(periodo_matriz) > 0:
            qs = qs.filter(matricula_periodo__periodo_matriz=periodo_matriz)
            qs_resumida = qs_resumida.filter(matricula_periodo__aluno__curso_campus=curso_campus)
            filtros.append({'chave': 'Período da Matriz', 'valor': periodo_matriz})

        qs = qs.filter(
            matricula_periodo__ano_letivo=ano_letivo,
            matricula_periodo__periodo_letivo=periodo_letivo,
            situacao__in=[
                MatriculaDiario.SITUACAO_REPROVADO,
                MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
                MatriculaDiario.SITUACAO_TRANCADO,
                MatriculaDiario.SITUACAO_CANCELADO,
            ],
        )
        qs_resumida = qs_resumida.filter(
            matricula_periodo__ano_letivo=ano_letivo,
            matricula_periodo__periodo_letivo=periodo_letivo,
            situacao__in=[
                MatriculaDiario.SITUACAO_REPROVADO,
                MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
                MatriculaDiario.SITUACAO_TRANCADO,
                MatriculaDiario.SITUACAO_CANCELADO,
            ],
        )
        filtros.append({'chave': 'Ano Letivo', 'valor': ano_letivo})
        filtros.append({'chave': 'Período Letivo', 'valor': periodo_letivo})

        if situacao:
            qs = qs.filter(matricula_periodo__situacao__id__in=situacao)
            qs_resumida = qs_resumida.filter(matricula_periodo__situacao__id__in=situacao)
            filtros.append({'chave': 'Situação na Matrícula Período', 'valor': situacao})
        else:
            raise forms.ValidationError('Selecione pelo menos uma situação no período')

        if programa:
            qs = qs.filter(matricula_periodo__aluno__participacao__programa__in=programa)
            qs_resumida = qs_resumida.filter(matricula_periodo__aluno__participacao__programa__in=programa)
            filtros.append({'chave': 'Programa', 'valor': programa})
        if beneficio:
            qs = qs.filter(matricula_periodo__aluno__caracterizacao__beneficiario_programa_social=beneficio)

        ordenacao = ['matricula_periodo__situacao', 'matricula_periodo__aluno__pessoa_fisica__nome']
        ordenacao_resumida = ['matricula_periodo__situacao', 'matricula_periodo__aluno__pessoa_fisica__nome']
        qs = qs.order_by(*ordenacao).distinct()
        qs_resumida = qs_resumida.order_by(*ordenacao_resumida).distinct()

        self.qs = list(qs) + list(qs_resumida)
        self.filtros = filtros
        return self.cleaned_data

    def processar(self):
        return self.qs, self.filtros


class RelatorioProfessorForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    uo = forms.ModelChoiceField(UnidadeOrganizacional.locals, label='Campus', required=False)
    categoria = forms.ChoiceField(
        choices=[
            ['Todos', 'Todos'],
            ['Docente', 'Docente'],
            ['Técnico-Administrativo', 'Técnico-Administrativo'],
            ['Prestador de Serviço', 'Prestador de Serviço'],
        ],
        label='Categorias',
        required=False,
    )
    ano_letivo = forms.ModelChoiceField(
        Ano.objects.ultimos(), label='Ano Letivo', required=False, help_text='Ano/Período letivo em que o professor possuiu algum diário'
    )
    periodo_letivo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=False)
    tipo_professor = forms.ModelChoiceField(
        TipoProfessorDiario.objects, label='Tipo no Diário', required=False, help_text='Tipo de vínculo do professor no diário'
    )
    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidades Lecionadas', required=False)
    setor_suap = forms.ModelChoiceField(
        Setor.objects,
        label='Setor de Exercício (SUAP)',
        widget=TreeWidget(),
        required=False,
        help_text='Setor no qual o servidor se encontra em exercício no SUAP',
    )
    setor_lotacao = forms.ModelMultiplePopupChoiceField(
        Setor.objects.none(), label='Setor de Lotação (SIAPE)', required=False, help_text='Setor no qual o servidor se encontra lotado no SIAPE'
    )
    disciplina_ingresso = forms.ModelMultiplePopupChoiceField(Disciplina.objects, label='Disciplina de Ingresso', required=False)
    jornada_trabalho = forms.ModelMultiplePopupChoiceField(JornadaTrabalho.objects, label='Jornada de Trabalho', required=False)
    regime = forms.ChoiceField(
        choices=[['Todos', 'Todos'], ['Efetivo', 'Efetivo'], ['Substituto', 'Substituto'], ['Temporário', 'Temporário'], ['Visitante', 'Visitante']],
        label='Regime',
        required=False,
    )
    nce = forms.ModelMultiplePopupChoiceField(NucleoCentralEstruturante.objects, label='Núcleo Central Estruturante', required=False)
    apenas_ativo = forms.BooleanField(label='Apenas Ativo', required=False, initial=True)

    ordenacao = forms.ChoiceField(choices=[['Nome', 'Nome']], label='Ordenação')

    EXIBICAO_CHOICES = sorted(
        [
            ['vinculo.setor.uo', 'Campus'],
            ['vinculo.email_notificacao', 'E-mail de Notificação'],
            ['vinculo.relacionamento.pessoa_fisica.nascimento_municipio', 'Naturalidade'],
            ['vinculo.setor', 'Setor de Lotação SUAP'],
            ['vinculo.relacionamento.setor_exercicio', 'Setor de Exercício SIAPE'],
            ['vinculo.relacionamento.setor_lotacao', 'Setor de Lotação SIAPE'],
            ['disciplina', 'Disciplina de Ingresso'],
            ['vinculo.relacionamento.jornada_trabalho', 'Jornada de Trabalho'],
            ['vinculo.relacionamento.cargo_emprego', 'Cargo'],
            ['nce', 'Núcleo Central Estruturante'],
            ['vinculo.realacionamento.pessoa_fisica.lattes', 'Currículo Lattes'],
            ['vinculo.relacionamento.pessoa_fisica.orcid', 'ORCID'],
            ['titulacao', 'Titulação'],
            ['get_qtd_alunos', 'Qtd de Alunos em Diários com Situação "Cursando"'],
            ['get_qtd_diarios', 'Qtd de Diários de Cursos Regulares no Período Letivo Informado'],
            ['get_ch_semanal', 'C.H. Semanal de Cursos Regulares no Período Letivo Informado'],
            ['instituicao_ensino_superior', 'Formação - Instituição de Ensino Superior'],
            ['curso_superior.descricao', 'Formação - Nome do Curso Superior'],
            ['curso_superior.grau', 'Formação - Grau do Curso Superior'],
            ['possui_formacao_complementar', 'Formação - Possui formação/complementação pedagógica'],
            ['get_qtd_diarios_total', 'Quantidade de diários'],
            ['get_ch_total', 'Carga horária total'],
            ['get_ch_total_pit', 'Carga horária total do PIT'],
        ],
        key=itemgetter(1),
    )
    EXIBICAO_INICIAS = [['vinculo.setor.uo', 'Campus'], ['disciplina', 'Disciplina de Ingresso']]
    exibicao = forms.MultipleChoiceField(label='Campos Adicionais', choices=EXIBICAO_CHOICES, widget=CheckboxSelectMultiplePlus(), required=False)
    fieldsets = (
        (
            'Filtros de Pesquisa',
            {
                'fields': (
                    ('uo', 'categoria'),
                    ('ano_letivo', 'periodo_letivo'),
                    'tipo_professor',
                    'modalidades',
                    'setor_lotacao',
                    'setor_suap',
                    'disciplina_ingresso',
                    'jornada_trabalho',
                    'regime',
                    'nce',
                    'apenas_ativo',
                )
            },
        ),
        ('Formatação', {'fields': (('ordenacao'),)}),
        ('Exibição', {'fields': (('exibicao',),)}),
    )

    def __init__(self, pode_ver_endereco, *args, **kwargs):
        super().__init__(*args, **kwargs)

        qs_setores_siape_lotacao = Setor.objects.siape().filter(
            id__in=Servidor.objects.docentes().values_list('setor_lotacao__id', flat=True).distinct()
        )
        self.fields['setor_lotacao'].queryset = qs_setores_siape_lotacao
        self.fields['setor_suap'].queryset = Setor.objects.siape()
        qs_jornada_trabalho = JornadaTrabalho.objects.filter(
            id__in=Servidor.objects.docentes().values_list('jornada_trabalho__id', flat=True).distinct()
        )
        self.fields['jornada_trabalho'].queryset = qs_jornada_trabalho

        if pode_ver_endereco:
            self.EXIBICAO_CHOICES = [
                *self.EXIBICAO_CHOICES,
                ['vinculo.pessoa.pessoaendereco', 'Endereço'],
                ['vinculo.pessoa.pessoaendereco.municipio', 'Cidade'],
            ]
            self.fields['exibicao'].choices = sorted(self.EXIBICAO_CHOICES, key=itemgetter(1))
        self.fields['exibicao'].initial = [campo[0] for campo in self.EXIBICAO_INICIAS]
        self.fields['tipo_professor'].queryset = TipoProfessorDiario.objects.order_by('descricao')
        self.fields['disciplina_ingresso'].queryset = Disciplina.objects.order_by('pk')

    def clean(self):
        filtros = []

        categoria = self.cleaned_data['categoria']
        filtros.append({'chave': 'Categorias', 'valor': categoria})

        qs_docentes = Professor.servidores_docentes.all()
        qs_tecnicos = Professor.servidores_tecnicos.filter(professordiario__isnull=False)
        qs_prestadores = Professor.nao_servidores.all()

        apenas_ativo = self.cleaned_data['apenas_ativo']
        filtros.append({'chave': 'Apenas Ativo', 'valor': apenas_ativo})

        if apenas_ativo:
            qs_docentes = qs_docentes.filter(
                vinculo__pessoa__id__in=Servidor.objects.filter(
                    situacao__codigo__in=Situacao.SITUACOES_ATIVOS, data_fim_servico_na_instituicao__isnull=True
                ).values_list('pessoa_fisica__id', flat=True)
            )

            qs_tecnicos = qs_tecnicos.filter(
                vinculo__pessoa__id__in=Servidor.objects.filter(
                    situacao__codigo__in=Situacao.SITUACOES_ATIVOS, data_fim_servico_na_instituicao__isnull=True
                ).values_list('pessoa_fisica__id', flat=True)
            )

        if categoria == 'Docente':
            qs = qs_docentes
        elif categoria == 'Técnico-Administrativo':
            qs = qs_tecnicos
        elif categoria == 'Prestador de Serviço':
            qs = qs_prestadores
        else:
            qs = qs_docentes | qs_tecnicos | qs_prestadores

        setor_suap = self.cleaned_data.get('setor_suap')
        uo = self.cleaned_data.get('uo')
        setor_lotacao = self.cleaned_data.get('setor_lotacao')
        disciplina_ingresso = self.cleaned_data.get('disciplina_ingresso')
        jornada_trabalho = self.cleaned_data.get('jornada_trabalho')
        regime = self.cleaned_data.get('regime')
        nce = self.cleaned_data.get('nce')

        if uo:
            qs = qs.filter(vinculo__setor__uo=uo)
            filtros.append({'chave': 'Campus', 'valor': (f'{uo}')})
        if setor_suap:
            qs = qs.filter(vinculo__setor__in=setor_suap.descendentes)
            filtros.append({'chave': 'Setor de Exercício', 'valor': (f'{setor_suap}')})
        if setor_lotacao:
            qs = qs.filter(
                vinculo__pessoa__id__in=Servidor.objects.filter(setor_lotacao__in=setor_lotacao).values_list('pessoa_fisica__id', flat=True)
            )
            filtros.append({'chave': 'Setor de Lotação SIAPE', 'valor': format_iterable(setor_lotacao)})
        if disciplina_ingresso:
            qs = qs.filter(disciplina__in=disciplina_ingresso)
            filtros.append({'chave': 'Disciplina de Ingresso', 'valor': format_iterable(disciplina_ingresso)})
        if jornada_trabalho:
            qs = qs.filter(
                vinculo__pessoa__id__in=Servidor.objects.filter(jornada_trabalho__in=jornada_trabalho).values_list('pessoa_fisica__id', flat=True)
            )
            filtros.append({'chave': 'Jornada de Trabalho', 'valor': format_iterable(jornada_trabalho)})
        if regime:
            if regime == 'Efetivo':
                qs = qs.filter(
                    vinculo__pessoa__id__in=Servidor.objects.filter(situacao__codigo__in=Situacao.SITUACOES_EFETIVOS).values_list(
                        'pessoa_fisica__id', flat=True
                    )
                )
            elif regime == 'Substituto':
                qs = qs.filter(
                    vinculo__pessoa__id__in=Servidor.objects.filter(situacao__codigo=Situacao.CONT_PROF_SUBSTITUTO).values_list(
                        'pessoa_fisica__id', flat=True
                    )
                )
            elif regime == 'Temporário':
                qs = qs.filter(
                    vinculo__pessoa__id__in=Servidor.objects.filter(situacao__codigo=Situacao.CONT_PROF_TEMPORARIO).values_list(
                        'pessoa_fisica__id', flat=True
                    )
                )
            elif regime == 'Visitante':
                qs = qs.filter(
                    vinculo__pessoa__id__in=Servidor.objects.filter(situacao__codigo=Situacao.CONTR_PROF_VISITANTE).values_list(
                        'pessoa_fisica__id', flat=True
                    )
                )
            filtros.append({'chave': 'Regime', 'valor': regime})
        if nce:
            qs = qs.filter(nce__in=nce)
            filtros.append({'chave': 'Núcleo Central Estruturante', 'valor': format_iterable(nce)})

        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        modalidades = self.cleaned_data['modalidades']
        tipo_professor = self.cleaned_data.get('tipo_professor')
        qs_professordiario = ProfessorDiario.objects.all()
        if ano_letivo:
            qs_professordiario = qs_professordiario.filter(diario__ano_letivo=ano_letivo)
            filtros.append({'chave': 'Ano Letivo', 'valor': str(ano_letivo)})
        if periodo_letivo != '' and int(periodo_letivo):
            qs_professordiario = qs_professordiario.filter(diario__periodo_letivo=periodo_letivo)
            filtros.append({'chave': 'Período Letivo', 'valor': str(periodo_letivo)})
        if modalidades:
            qs_professordiario = qs_professordiario.filter(diario__turma__curso_campus__modalidade__in=modalidades)
            filtros.append({'chave': 'Modalidades', 'valor': ', '.join(modalidades.values_list('descricao', flat=True))})
        if tipo_professor:
            qs_professordiario = qs_professordiario.filter(tipo=tipo_professor)
            filtros.append({'chave': 'Tipo', 'valor': str(tipo_professor)})
        ids_professor = qs_professordiario.values_list('professor_id', flat=True)

        if ids_professor:
            qs = qs.filter(id__in=ids_professor)

        ordenacao = []
        if self.cleaned_data.get('ordenacao') == 'Nome':
            ordenacao.append('vinculo__pessoa__nome')

        qs = qs.order_by(*ordenacao).distinct()
        qs.filtros = filtros

        if not qs.filtros:
            raise forms.ValidationError('Por favor, selecione, no mínimo, um filtro.')
        else:
            self.qs = qs
            if ano_letivo and periodo_letivo:
                for obj in self.qs:
                    obj.ano_letivo_informado = ano_letivo
                    obj.periodo_letivo_informado = periodo_letivo
            return self.cleaned_data

    def processar(self):
        return self.qs


class RelatorioDiarioForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    ACTION = '/edu/relatorio_diario/'

    nivel_ensino = forms.ModelMultiplePopupChoiceField(NivelEnsino.objects, label='Nível de Ensino', required=False)
    modalidade = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidade', required=False)
    estrutura_curso = forms.ModelMultiplePopupChoiceField(EstruturaCurso.objects, label='Estrutura', required=False)
    uo = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.locals, label='Campus', required=False)
    diretoria = forms.ModelMultiplePopupChoiceField(Diretoria.objects, label='Diretoria', required=False)
    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(
            search_fields=CursoCampus.SEARCH_FIELDS,
            form_filters=[
                ('diretoria', 'diretoria__in'),
                ('nivel_ensino', 'modalidade__nivel_ensino__in'),
                ('modalidade', 'modalidade__in'),
                ('estrutura_curso', 'matrizcurso__matriz__estrutura__in'),
            ],
        ),
    )
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[
                ('curso_campus', 'curso_campus'),
                ('diretoria', 'curso_campus__diretoria__in'),
                ('nivel_ensino', 'curso_campus__modalidade__nivel_ensino__in'),
                ('modalidade', 'curso_campus__modalidade__in'),
                ('ano_letivo', 'ano_letivo'),
                ('turno', 'turno'),
                ('periodo_letivo', 'periodo_letivo'),
            ],
        ),
    )
    componente = forms.ModelChoiceFieldPlus(
        Componente.objects,
        label='Componente',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Componente.SEARCH_FIELDS,
            form_filters=[
                ('nivel_ensino', 'nivel_ensino__in'),
                ('diretoria', 'diretoria__in'),
                ('modalidade', 'componentecurricular__matriz__matrizcurso__curso_campus__modalidade__in'),
            ],
        ),
    )
    professor = forms.ModelChoiceFieldPlus(
        Professor.objects,
        label='Professor',
        required=False,
        widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS, form_filters=[('diretoria', 'vinculo__setor__diretoria__in')]),
    )
    ano_letivo_inicio = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano letivo a partir de', required=False)
    ano_letivo_fim = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano letivo até', required=False)
    periodo_letivo_inicio = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de Ingresso a Partir de', required=False)
    periodo_letivo_fim = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período de Ingresso Até', required=False)

    calendario_academico = forms.ModelChoiceFieldPlus(
        CalendarioAcademico.locals,
        label='Calendário Acadêmico',
        required=False,
        help_text='Selecione o campus, diretoria ou ano letivo de início/fim para restringir as opções desse filtro.',
        widget=AutocompleteWidget(
            search_fields=CursoCampus.SEARCH_FIELDS,
            form_filters=[
                ('uo', 'diretoria__setor__uo'),
                ('diretoria', 'diretoria'),
                ('ano_letivo_inicio', 'ano_letivo__gte'),
                ('ano_letivo_fim', 'ano_letivo__lte'),
            ],
        ),
    )

    turno = forms.ModelChoiceField(Turno.objects, label='Turno', required=False)
    etapa = forms.ChoiceField(choices=Aula.ETAPA_CHOICES, label='Etapa', required=False, help_text='A etapa selecionada será exportada para PDF.')
    quantidade_etapa = forms.MultipleChoiceField(
        choices=[[1, 'Uma'], [2, 'Duas'], [4, 'Quatro']], label='Quantidade de Etapas', widget=forms.CheckboxSelectMultiplePlus(), required=False
    )
    etapa_entregue = forms.MultipleChoiceField(
        choices=Aula.ETAPA_CHOICES, label='Etapas Entregues', widget=forms.CheckboxSelectMultiplePlus(), required=False
    )
    etapa_posse_professor = forms.MultipleChoiceField(
        choices=Aula.ETAPA_CHOICES, label='Etapas em Posse do Professor', widget=forms.CheckboxSelectMultiplePlus(), required=False
    )
    alunos_pendentes = forms.BooleanField(label='Diários com Alunos Dependentes', required=False)
    numero_alunos_abaixo_limite = forms.BooleanField(label='Número de Alunos abaixo do Limite', required=False)
    somente_optativos = forms.BooleanField(
        label='Somente optativos',
        required=False,
        help_text='Exibe apenas os diários de componentes curriculares configurados como optativos na matriz curricular.',
    )
    somente_em_andamento = forms.BooleanField(
        label='Somente em andamento',
        required=False,
        help_text='Exibe apenas os diários cuja data de início e fim abrange a data corrente',
    )
    ordenacao = forms.ChoiceField(choices=[['Nome', 'Nome do Componente'], ['Período', 'Período Letivo']], label='Ordenação')
    agrupamento = forms.ChoiceField(choices=[['Campus', 'Campus'], ['Componente', 'Componente'], ['Curso', 'Curso']], label='Agrupamento')

    EXIBICAO_CHOICES = [
        ['componente_curricular.componente.ch_hora_relogio', 'CH Relógio'],
        ['componente_curricular.componente.ch_hora_aula', 'CH Aula'],
        ['turma', 'Turma'],
        ['turma.curso_campus', 'Curso'],
        ['ano_letivo', 'Ano Letivo'],
        ['periodo_letivo', 'Período Letivo'],
        ['quantidade_vagas', 'Quantidade de Vagas'],
        ['estrutura_curso', 'Estrutura do Curso'],
        ['componente_curricular.qtd_avaliacoes', 'Quantidade de Etapas'],
        ['componente_curricular.componente.tipo', 'Tipo de Componente'],
        ['turma.curso_campus.diretoria', 'Diretoria'],
        ['turno', 'Turno'],
        ['turma.curso_campus.diretoria.setor.uo', 'Campus'],
        ['horario_campus', 'Horário do Campus'],
        ['local_aula', 'Sala de aula'],
        ['local_laboratorio', 'Laboratório'],
        ['get_carga_horaria_cumprida', 'Quantidade de Aulas Ministradas'],
        ['get_quantidade_alunos_ativos', 'Quantidade de Alunos Ativos'],
        ['url_moodle', 'Endereço do Moodle'],
    ]

    EXIBICAO_INICIAS = [
        ['componente_curricular.componente.ch_hora_relogio', 'CH Relógio'],
        ['componente_curricular.componente.ch_hora_aula', 'CH Aula'],
        ['turma', 'Turma'],
        ['turma.curso_campus', 'Curso'],
        ['get_professores', 'Professores'],
    ]

    exibicao = forms.MultipleChoiceField(label='Campos Adicionais', choices=EXIBICAO_CHOICES, widget=CheckboxSelectMultiplePlus(), required=False)

    fieldsets = (
        (
            'Filtros de Pesquisa',
            {
                'fields': (
                    'nivel_ensino',
                    'modalidade',
                    'estrutura_curso',
                    'uo',
                    'diretoria',
                    'curso_campus',
                    ('ano_letivo_inicio', 'periodo_letivo_inicio'),
                    ('ano_letivo_fim', 'periodo_letivo_fim'),
                    'calendario_academico',
                    ('turno'),
                    'turma',
                    'componente',
                    'professor',
                    ('alunos_pendentes', 'numero_alunos_abaixo_limite'),
                    ('somente_optativos', 'somente_em_andamento'),
                )
            },
        ),
        ('Etapa', {'fields': (('quantidade_etapa',), ('etapa_entregue'), ('etapa_posse_professor'), ('etapa'))}),
        ('Formatação', {'fields': (('ordenacao', 'agrupamento'),)}),
        ('Exibição', {'fields': (('exibicao',),)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['curso_campus'].queryset = self.fields['curso_campus'].queryset.all().filter(ativo=True)
        self.fields['exibicao'].initial = [campo[0] for campo in self.EXIBICAO_INICIAS]
        self.fields['uo'].queryset = UnidadeOrganizacional.locals.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)

    def clean(self):
        qs = Diario.objects.all()
        exibicao = self.cleaned_data.get('exibicao', ())
        diretoria = self.cleaned_data.get('diretoria', None)
        uo = self.cleaned_data.get('uo', None)
        professor = self.cleaned_data.get('professor', None)
        turma = self.cleaned_data.get('turma', None)
        curso_campus = self.cleaned_data.get('curso_campus', None)
        componente = self.cleaned_data.get('componente', None)
        estrutura_curso = self.cleaned_data.get('estrutura_curso', None)
        modalidade = self.cleaned_data.get('modalidade', None)
        nivel_ensino = self.cleaned_data.get('nivel_ensino', None)
        ano_letivo_inicio = self.cleaned_data.get('ano_letivo_inicio', None)
        periodo_letivo_inicio = int(self.cleaned_data.get('periodo_letivo_inicio') or 0)
        ano_letivo_fim = self.cleaned_data.get('ano_letivo_fim', None)
        periodo_letivo_fim = int(self.cleaned_data.get('periodo_letivo_fim') or 0)
        calendario_academico = self.cleaned_data.get('calendario_academico')
        turno = self.cleaned_data.get('turno', None)
        etapa = self.cleaned_data.get('etapa', None)
        quantidade_etapa = self.cleaned_data.get('quantidade_etapa', None)
        etapa_entregue = self.cleaned_data.get('etapa_entregue', None)
        etapa_posse_professor = self.cleaned_data.get('etapa_posse_professor', None)
        numero_alunos_abaixo_limite = self.cleaned_data.get('numero_alunos_abaixo_limite', None)
        somente_optativos = self.cleaned_data.get('somente_optativos', None)
        somente_em_andamento = self.cleaned_data.get('somente_em_andamento', None)
        filtros = []

        if 'url_moodle' in exibicao:
            qs = qs.filter(url_moodle__isnull=False).exclude(url_moodle='')
            filtros.append({'chave': 'Endereço do Moodle', 'valor': 'Sim'})

        if somente_em_andamento:
            hoje = date.today()
            qs = qs.filter(calendario_academico__data_inicio__lte=hoje, calendario_academico__data_fim__gte=hoje)
            filtros.append({'chave': 'Somente em Andamento', 'valor': 'Sim'})

        if uo:
            qs = qs.filter(turma__curso_campus__diretoria__setor__uo__in=uo)
            filtros.append({'chave': 'Campus', 'valor': format_iterable(uo)})
        if diretoria:
            qs = qs.filter(turma__curso_campus__diretoria__in=diretoria)
            filtros.append({'chave': 'Diretoria', 'valor': format_iterable(diretoria)})
        if professor:
            qs = qs.filter(professordiario__professor=professor)
            filtros.append({'chave': 'Professor', 'valor': str(professor)})
        if estrutura_curso:
            qs = qs.filter(turma__matriz__estrutura__id__in=estrutura_curso)
            filtros.append({'chave': 'Estrutura de Curso', 'valor': format_iterable(estrutura_curso)})
        if modalidade:
            qs = qs.filter(turma__curso_campus__modalidade__id__in=modalidade)
            filtros.append({'chave': 'Modalidade', 'valor': format_iterable(modalidade)})
        if nivel_ensino:
            qs = qs.filter(turma__curso_campus__modalidade__nivel_ensino__id__in=nivel_ensino)
            filtros.append({'chave': 'Nível de Ensino', 'valor': format_iterable(nivel_ensino)})
        if componente:
            qs = qs.filter(componente_curricular__componente=componente)
            filtros.append({'chave': 'Componente', 'valor': str(componente)})
        if curso_campus:
            qs = qs.filter(turma__curso_campus=curso_campus)
            filtros.append({'chave': 'Curso', 'valor': str(curso_campus)})
        if turma:
            qs = qs.filter(turma__curso_campus__ativo=True, matriculadiario__diario__turma=turma)
            filtros.append({'chave': 'Turma', 'valor': str(turma)})

        if ano_letivo_inicio and ano_letivo_fim and ano_letivo_inicio == ano_letivo_fim:
            qs = qs.filter(ano_letivo_id=ano_letivo_inicio.id)
            filtros.append({'chave': 'Ano letivo', 'valor': str(ano_letivo_inicio)})
            if periodo_letivo_inicio == 2:
                qs = qs.filter(periodo_letivo=periodo_letivo_inicio)
                filtros.append({'chave': 'Período letivo', 'valor': str(periodo_letivo_inicio)})
            elif periodo_letivo_fim == 1:
                qs = qs.filter(periodo_letivo=periodo_letivo_fim)
                filtros.append({'chave': 'Período letivo', 'valor': str(periodo_letivo_fim)})
            elif periodo_letivo_inicio != periodo_letivo_fim and periodo_letivo_inicio + periodo_letivo_fim > 0:
                filtros.append({'chave': 'Período letivo', 'valor': '1 e 2'})
        else:
            if ano_letivo_inicio:
                qs = qs.filter(ano_letivo__ano__gte=ano_letivo_inicio.ano)
                if periodo_letivo_inicio == 2:
                    qs = qs.exclude(ano_letivo=ano_letivo_inicio, periodo_letivo=1)
                    filtros.append({'chave': 'Ano/período letivo a partir de', 'valor': f'{ano_letivo_inicio.ano}/{periodo_letivo_inicio}'})
                else:
                    filtros.append({'chave': 'Ano/período letivo a partir de', 'valor': f'{ano_letivo_inicio.ano}/1'})
            if ano_letivo_fim:
                qs = qs.filter(ano_letivo__ano__lte=ano_letivo_fim.ano)
                if periodo_letivo_fim == 1:
                    qs = qs.exclude(ano_letivo=ano_letivo_fim, periodo_letivo=2)
                    filtros.append({'chave': 'Ano/período letivo até', 'valor': f'{ano_letivo_fim.ano}/{periodo_letivo_fim}'})
                else:
                    filtros.append({'chave': 'Ano/período letivo até', 'valor': f'{ano_letivo_fim.ano}/2'})

        if calendario_academico:
            qs = qs.filter(calendario_academico=calendario_academico)
            filtros.append({'chave': 'Calendário Acadêmico', 'valor': str(calendario_academico)})

        if somente_optativos:
            qs = qs.filter(componente_curricular__optativo=True)
            filtros.append({'chave': 'Somente Optativos', 'valor': 'Sim'})
        if turno:
            qs = qs.filter(turno=turno)
            filtros.append({'chave': 'Turno', 'valor': str(turno)})
        if etapa:
            if int(etapa) == 5:
                filtros.append({'chave': 'Etapa', 'valor': 'Final'})
            else:
                filtros.append({'chave': 'Etapa', 'valor': str(etapa)})
        if quantidade_etapa:
            qs = qs.filter(componente_curricular__qtd_avaliacoes__in=quantidade_etapa)
            filtros.append({'chave': 'Quantidade de Etapas', 'valor': ', '.join(quantidade_etapa)})
        if etapa_entregue:
            if '1' in etapa_entregue:
                qs = qs.filter(posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR)
            if '2' in etapa_entregue:
                qs = qs.filter(posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR)
            if '3' in etapa_entregue:
                qs = qs.filter(posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR)
            if '4' in etapa_entregue:
                qs = qs.filter(posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR)
            if '5' in etapa_entregue:
                qs = qs.filter(posse_etapa_5=Diario.POSSE_REGISTRO_ESCOLAR)
            filtros.append({'chave': 'Etapas Entregues', 'valor': ', '.join(etapa_entregue)})
        if etapa_posse_professor:
            if '1' in etapa_posse_professor:
                qs = qs.filter(posse_etapa_1=Diario.POSSE_PROFESSOR)
            if '2' in etapa_posse_professor:
                qs = qs.filter(posse_etapa_2=Diario.POSSE_PROFESSOR)
            if '3' in etapa_posse_professor:
                qs = qs.filter(posse_etapa_3=Diario.POSSE_PROFESSOR)
            if '4' in etapa_posse_professor:
                qs = qs.filter(posse_etapa_4=Diario.POSSE_PROFESSOR)
            if '5' in etapa_posse_professor:
                qs = qs.filter(posse_etapa_5=Diario.POSSE_PROFESSOR)
            filtros.append({'chave': 'Etapas em Posse do Professor', 'valor': ', '.join(etapa_posse_professor)})

        if numero_alunos_abaixo_limite:
            filtros.append({'chave': 'Número de Alunos abaixo do Limite', 'valor': format_(numero_alunos_abaixo_limite)})
            qs = (
                qs.filter(turma__matriz__estrutura__numero_min_alunos_diario__isnull=False)
                .annotate(matriculas=Count('matriculadiario'))
                .filter(matriculas__lt=F('turma__matriz__estrutura__numero_min_alunos_diario'))
            )

        ordenacao = ['turma__curso_campus', 'turma__curso_campus__diretoria__setor__uo']
        if self.cleaned_data.get('ordenacao') == 'Período':
            ordenacao.append('ano_letivo')
            ordenacao.append('periodo_letivo')
        if self.cleaned_data.get('ordenacao') == 'Nome':
            ordenacao.append('componente_curricular__componente__descricao')

        qs = qs.order_by(*ordenacao).distinct()
        qs.filtros = filtros

        self.qs = qs
        return self.cleaned_data

    def processar(self):
        return self.qs


class RelatorioHorarioForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        required=False,
        widget=AutocompleteWidget(
            form_filters=[('ano_letivo', 'ano_letivo'), ('periodo_letivo', 'periodo_letivo')], search_fields=Turma.SEARCH_FIELDS
        ),
    )
    professor = forms.ModelChoiceFieldPlus(
        Professor.objects, label='Professor', required=False, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS)
    )
    sala = forms.ModelChoiceFieldPlus(Sala.ativas, required=False)
    laboratorio = forms.ModelChoiceFieldPlus(Sala.ativas, required=False)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=True)
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, label='Período Letivo', required=True)

    fieldsets = (('Filtros de Pesquisa', {'fields': (('ano_letivo', 'periodo_letivo'), 'turma', 'professor', 'sala')}),)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uo_id = get_uo(user).id
        self.fields['sala'].queryset = Sala.ativas.filter(predio__uo_id=uo_id, laboratorio__isnull=True)
        self.fields['laboratorio'].queryset = Sala.ativas.filter(predio__uo_id=uo_id, laboratorio__isnull=False)

    def clean(self):
        professor = self.cleaned_data['professor']
        turma = self.cleaned_data['turma']
        sala = self.cleaned_data['sala']
        laboratorio = self.cleaned_data['laboratorio']
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data['periodo_letivo']

        if not (professor or turma or sala or laboratorio):
            raise forms.ValidationError('Informe turma, professor, sala ou laboratório.')

        filtros = []
        qs = HorarioAulaDiario.objects.all()
        if professor:
            qs = qs.filter(diario__professordiario__professor=professor)
            filtros.append({'chave': 'Professor', 'valor': str(professor)})
        if turma:
            qs = qs.filter(diario__turma=turma)
            filtros.append({'chave': 'Turma', 'valor': str(turma)})
        if sala:
            qs = qs.filter(diario__local_aula=sala)
            filtros.append({'chave': 'Sala', 'valor': str(sala)})
        if laboratorio:
            qs = qs.filter(diario__local_laboratorio=laboratorio)
            filtros.append({'chave': 'Laboratório', 'valor': str(laboratorio)})
        if ano_letivo:
            qs = qs.filter(diario__ano_letivo=ano_letivo)
            filtros.append({'chave': 'Ano Letivo', 'valor': str(ano_letivo)})
        if int(periodo_letivo):
            qs = qs.filter(diario__periodo_letivo=periodo_letivo)
            filtros.append({'chave': 'Período Letivo', 'valor': str(periodo_letivo)})
        qs.filtros = filtros
        self.qs = qs
        return self.cleaned_data

    def processar(self):
        return self.qs


class RelatorioHorarioDiarioEspecialForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    diretoria = forms.ModelChoiceFieldPlus(
        Diretoria.objects.none(), label='Diretoria', required=False, widget=AutocompleteWidget(search_fields=Diretoria.SEARCH_FIELDS)
    )
    professor = forms.ModelChoiceFieldPlus(
        Professor.objects, label='Professor', required=False, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS)
    )
    sala = forms.ModelChoiceFieldPlus(Sala.ativas, required=False)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=True)
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES, label='Período Letivo', required=True)

    fieldsets = (('Filtros de Pesquisa', {'fields': (('ano_letivo', 'periodo_letivo'), 'diretoria', 'professor', 'sala')}),)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals
        self.fields['sala'].queryset = self.fields['sala'].queryset.all().filter(ativa=True, predio__uo=get_uo(user))

    def clean(self):
        professor = self.cleaned_data['professor']
        diretoria = self.cleaned_data['diretoria']
        sala = self.cleaned_data['sala']
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data['periodo_letivo']

        if not (professor or diretoria or sala):
            raise forms.ValidationError('Informe turma, professor ou sala.')

        filtros = []
        qs = HorarioAulaDiarioEspecial.objects.all()
        if professor:
            qs = qs.filter(diario_especial__professores=professor)
            filtros.append({'chave': 'Professor', 'valor': str(professor)})
        if diretoria:
            qs = qs.filter(diario_especial__diretoria=diretoria)
            filtros.append({'chave': 'Diretoria', 'valor': str(diretoria)})
        if sala:
            qs = qs.filter(diario_especial__sala=sala)
            filtros.append({'chave': 'Sala', 'valor': str(sala)})
        if ano_letivo:
            qs = qs.filter(diario_especial__ano_letivo=ano_letivo)
            filtros.append({'chave': 'Ano Letivo', 'valor': str(ano_letivo)})
        if int(periodo_letivo):
            qs = qs.filter(diario_especial__periodo_letivo=periodo_letivo)
            filtros.append({'chave': 'Período Letivo', 'valor': str(periodo_letivo)})
        qs.filtros = filtros
        self.qs = qs
        return self.cleaned_data

    def processar(self):
        return self.qs


class RelatorioFaltasForm(forms.FormPlus):
    SUBMIT_LABEL = 'Visualizar'
    METHOD = 'GET'

    ACTION = '/edu/relatorio_faltas/'

    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.campi(), label='Campus', required=False)

    diretoria = forms.ModelChoiceFieldPlus(
        Diretoria.objects, label='Diretoria', widget=AutocompleteWidget(form_filters=[('uo', 'setor__uo__in')]), required=False
    )

    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
        required=False,
    )

    turma = forms.ModelChoiceFieldPlus(
        Turma.objects.none(),
        widget=AutocompleteWidget(search_fields=Turma.SEARCH_FIELDS, form_filters=[('uo', 'curso_campus__diretoria__setor__uo__in')]),
        required=False,
    )

    diario = forms.ModelChoiceFieldPlus(
        Diario.objects.none(),
        label='Diário',
        help_text='Para encontrar um diário entre com a sigla do componente ou o código do diário.',
        widget=AutocompleteWidget(search_fields=Diario.SEARCH_FIELDS, form_filters=[('uo', 'turma__curso_campus__diretoria__setor__uo__in')]),
        required=False,
    )
    aluno = forms.ModelChoiceFieldPlus(
        Aluno.locals,
        required=False,
        widget=AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS, form_filters=[('uo', 'curso_campus__diretoria__setor__uo__in')]),
    )

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=False)
    periodo_letivo = forms.ChoiceField(choices=[[None, '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=False, initial=1)
    situacao_periodo = forms.ModelMultiplePopupChoiceField(SituacaoMatriculaPeriodo.objects, label='Situação no Período', required=False)
    intervalo_inicio = forms.DateFieldPlus(label='Início do Intervalo', required=False)
    intervalo_fim = forms.DateFieldPlus(label='Fim do Intervalo', required=False)

    situacoes_inativas = forms.BooleanField(
        label='Desconsiderar Situações Inativas',
        required=False,
        help_text='Exclui do relatório aulas e faltas de alunos que estão com situação Cancelado, Dispensado, Trancado ou Transferido no diário.',
        initial=True,
    )
    fieldsets = (
        ('Período', {'fields': (('ano_letivo', 'periodo_letivo'), ('intervalo_inicio', 'intervalo_fim'))}),
        ('Filtros de Pesquisa', {'fields': ('uo', 'diretoria', 'curso_campus', 'turma', 'diario')}),
        ('Filtros Adicionais', {'fields': ('aluno', ('situacao_periodo', 'situacoes_inativas'))}),
    )

    if 'ae' in settings.INSTALLED_APPS:
        fieldsets = (
            ('Período', {'fields': (('ano_letivo', 'periodo_letivo'), ('intervalo_inicio', 'intervalo_fim'))}),
            ('Filtros de Pesquisa', {'fields': ('uo', 'diretoria', 'curso_campus', 'turma', 'diario')}),
            ('Filtros Adicionais', {'fields': ('aluno', ('situacao_periodo', 'situacoes_inativas'))}),
            ('Filtros Assistenciais', {'fields': ('beneficio', 'programa')}),
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.request.user
        uos_id = []
        if not user.has_group_cached(perms.grupos_sistemicos):
            self.fields['uo'].required = True
            uos_id = list(
                UsuarioGrupoSetor.objects.filter(
                    usuario_grupo__user_id=user.id, usuario_grupo__group__name__in=perms.grupos_diretoria + perms.grupos_campus
                )
                .values_list('setor__uo_id', flat=True)
                .distinct()
            )
            if not uos_id:
                vinculo = self.request.user.get_vinculo()
                campus = vinculo.setor.uo_id if vinculo and vinculo.setor else None
                if campus:
                    uos_id = [campus]
            if uos_id:
                self.fields['uo'].queryset = UnidadeOrganizacional.objects.campi().filter(id__in=uos_id)
            else:
                self.fields['uo'].queryset = UnidadeOrganizacional.objects.none()

            if len(uos_id) == 1:
                self.initial['uo'] = uos_id[0]

        if 'ae' in settings.INSTALLED_APPS:
            ProgramaSocial = apps.get_model('ae', 'Programa')
            BeneficioGovernoFederal = apps.get_model('ae', 'BeneficioGovernoFederal')

            self.fields['programa'] = forms.ModelMultiplePopupChoiceField(
                ProgramaSocial.objects.all(),
                label='Participação nos programa de assistência estudantil',
                required=False,
                help_text='Serão exibidos todos os alunos com participação ativa ou inativa nos programas selecionados',
            )
            if uos_id:
                self.fields['programa'].queryset = ProgramaSocial.objects.filter(instituicao_id__in=uos_id)

            self.fields['beneficio'] = forms.ModelChoiceField(
                BeneficioGovernoFederal.objects.all(),
                label='Programa Social',
                required=False,
                help_text='O aluno deverá ter informado a participação no programa social em sua caracterização social.',
            )

        self.fields['periodo_letivo'].initial = None

        self.fields['diario'].queryset = Diario.locals.by_user(self.request.user)
        self.fields['turma'].queryset = Turma.locals.by_user(self.request.user)

    def clean(self):
        if (
            not self.cleaned_data.get('turma')
            and not self.cleaned_data.get('diario')
            and not self.cleaned_data.get('aluno')
            and not self.cleaned_data.get('curso_campus')
            and not self.cleaned_data.get('uo')
            and not self.cleaned_data.get('diretoria')
        ):
            raise forms.ValidationError('Insira ao menos o campus, diretoria, curso, turma, diário ou aluno nos filtros.')
        filtro_periodo = (self.cleaned_data.get('curso_campus') or self.cleaned_data.get('uo')) and not (
            self.cleaned_data.get('ano_letivo') and self.cleaned_data.get('periodo_letivo')
        )
        # turma, diário e aluno já delimitam o período; o campus pode vir obrigatório junto
        filtro_especifico = self.cleaned_data.get('aluno') or self.cleaned_data.get('turma') or self.cleaned_data.get('diario')
        if filtro_periodo and not filtro_especifico:
            raise forms.ValidationError('Insira ano letivo e período letivo para filtrar por campus ou curso.')

        return self.cleaned_data

    def clean_intervalo_fim(self):
        if not self.cleaned_data.get('intervalo_inicio') and self.cleaned_data.get('intervalo_fim'):
            raise forms.ValidationError('Insira uma data válida no início do intervalo.')
        else:
            return self.cleaned_data['intervalo_fim']


class SalvarRelatorioForm(forms.Form):
    descricao = forms.CharFieldPlus(label='Descrição')

    def __init__(self, *args, **kwargs):
        self.tipo = kwargs.pop('tipo')
        super().__init__(*args, **kwargs)

    def processar(self, query_string):
        h = HistoricoRelatorio()
        h.descricao = self.cleaned_data['descricao']
        h.query_string = query_string
        h.tipo = self.tipo
        h.save()
        return h


class FiltroAlunosForm(forms.Form):
    METHOD = 'GET'
    diretoria = forms.ModelChoiceField(Diretoria.objects.none(), label='Diretoria', required=False)
    curso_campus = forms.ModelChoiceFieldPlus(CursoCampus.locals, label='Curso', required=False)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo de Ingresso', required=False)
    periodo_letivo = forms.ChoiceField(choices=[['', '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo de Ingresso', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretoria'].queryset = Diretoria.locals

    def filtrar(self, alunos):
        diretoria = self.cleaned_data.get('diretoria')
        curso_campus = self.cleaned_data.get('curso_campus')
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        if diretoria:
            alunos = alunos.filter(curso_campus__diretoria=diretoria)
        if curso_campus:
            alunos = alunos.filter(curso_campus=curso_campus)
        if ano_letivo:
            alunos = alunos.filter(ano_letivo=ano_letivo)
        if periodo_letivo:
            alunos = alunos.filter(periodo_letivo=periodo_letivo)
        return alunos


class MonitoramentoForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo', required=True)
    periodo_letivo = forms.ChoiceField(choices=[[0, '----'], *PERIODO_LETIVO_CHOICES], label='Período Letivo', required=True)
    diretorias = forms.ModelMultiplePopupChoiceField(Diretoria.objects.all(), label='Diretoria', required=False)
    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects.all(), label='Modalidade', required=False)
    agrupamento = forms.ChoiceField(
        choices=[['Professor', 'Professor'], ['Data de Fechamento Período', 'Data de Fechamento Período']], label='Agrupamento'
    )

    fieldsets = (('', {'fields': (('ano_letivo', 'periodo_letivo', 'agrupamento'), 'diretorias', 'modalidades')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretorias'].queryset = Diretoria.locals.all()

    def clean_periodo_letivo(self):
        if not self.cleaned_data.get('periodo_letivo') or int(self.cleaned_data.get('periodo_letivo')) == 0:
            raise forms.ValidationError('Este campo é obrigatório.')
        return self.cleaned_data.get('periodo_letivo')


class MonitoramentoFechamentoPeriodoForm(MonitoramentoForm):
    agrupamento = forms.ChoiceField(choices=[['Curso', 'Curso'], ['Data de Fechamento Período', 'Data de Fechamento Período']], label='Agrupamento')

    def processar(self, cleaned_data=None):
        compacto = True
        if not cleaned_data:
            compacto = False
            cleaned_data = self.cleaned_data

        # Tratando filtros da tela de monitoramento
        agrupamento = cleaned_data.get('agrupamento')
        ano_letivo = cleaned_data.get('ano_letivo')
        periodo_letivo = cleaned_data.get('periodo_letivo')
        diretorias = cleaned_data.get('diretorias', [])
        modalidades = cleaned_data.get('modalidades', [])

        qs = MatriculaPeriodo.objects.com_fechamento_pendente(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, diretorias=diretorias)

        if self.request.user and self.request.user.groups.filter(name='Coordenador de Curso').exists():
            qs = qs.filter(aluno__curso_campus__coordenador__user_id=self.request.user.id) | qs.filter(
                aluno__curso_campus__coordenador_2__user_id=self.request.user.id
            )

        if agrupamento == 'Data de Fechamento Período':
            qs = qs.order_by('turma__calendario_academico__data_fechamento_periodo')
        else:
            qs = qs.order_by('aluno__curso_campus__codigo')

        if diretorias:
            qs = qs.filter(aluno__curso_campus__diretoria_id__in=diretorias)
        if modalidades:
            qs = qs.filter(aluno__curso_campus__modalidade_id__in=modalidades)

        self.qs = qs

        # fechamento de período por diretoria

        graficos = []
        inicial = 0
        qtd_por_grafico = 6
        qtd_cursos = qs.values_list('aluno__curso_campus_id', flat=True).distinct().count()

        for i in range(int(qtd_cursos / qtd_por_grafico) + 1):
            series_fechamento = []

            if compacto:
                tmp = qs[0:3]
            else:
                tmp = qs[inicial : inicial + qtd_por_grafico]
            inicial += qtd_por_grafico

            for matricula_periodo in tmp.values('aluno__curso_campus__descricao_historico', 'aluno__curso_campus__codigo').annotate(
                qtd_aluno=Count('id')
            ):
                nome_curso = '{} - {}'.format(
                    matricula_periodo['aluno__curso_campus__codigo'], matricula_periodo['aluno__curso_campus__descricao_historico']
                )
                if compacto:
                    nome_curso = defaultfilters.truncatechars(nome_curso, 33)
                series_fechamento.append([nome_curso, matricula_periodo['qtd_aluno']])

            id_grafico_fechamento = f'graficoFechamentoPeriodo_{i}'
            grafico_fechamento = ColumnChart(
                id_grafico_fechamento,
                title='Períodos Abertos',
                subtitle='Alunos com período letivo não-fechado após o prazo de fechamento',
                data=series_fechamento,
            )
            grafico_fechamento.series[0]['dataLabels'] = {'enabled': True, 'color': '#0A0A0A', 'align': 'center', 'y': 30}
            grafico_fechamento.id = id_grafico_fechamento

            graficos.append(grafico_fechamento)
            if compacto:
                break

        return self.qs, graficos


class MonitoramentoEntregaDiariosForm(MonitoramentoForm):
    def processar(self, com_grafico, cleaned_data=None):
        compacto = True
        if not cleaned_data:
            compacto = False
            cleaned_data = self.cleaned_data

        qs = ProfessorDiario.objects.filter(ativo=True)

        # coordenador de curso
        if self.request.user and self.request.user.groups.filter(name='Coordenador de Curso').exists():
            qs = qs.filter(diario__turma__curso_campus__coordenador__user_id=self.request.user.id) | qs.filter(
                diario__turma__curso_campus__coordenador_2__user_id=self.request.user.id
            )

        # Tratando filtros da tela de monitoramento
        agrupamento = cleaned_data.get('agrupamento')

        ano_letivo = cleaned_data.get('ano_letivo')
        periodo_letivo = cleaned_data.get('periodo_letivo')
        diretorias = cleaned_data.get('diretorias', [])
        modalidades = cleaned_data.get('modalidades', [])

        if diretorias:
            qs = qs.filter(diario__turma__curso_campus__diretoria__id__in=diretorias)

        if modalidades:
            qs = qs.filter(diario__turma__curso_campus__modalidade__id__in=modalidades)

        # diários com etapa(s) em posse do professor na data de fechamento do período
        qs = qs.filter(
            diario__calendario_academico__data_fechamento_periodo__lte=datetime.datetime.now(),
            diario__ano_letivo=ano_letivo,
            diario__periodo_letivo=periodo_letivo,
        )

        qs1 = (
            qs.exclude(diario__componente_curricular__qtd_avaliacoes__in=[0, 1], diario__posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR)
            .exclude(
                diario__componente_curricular__qtd_avaliacoes=2,
                diario__posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR,
            )
            .exclude(
                diario__componente_curricular__qtd_avaliacoes=4,
                diario__posse_etapa_1=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_2=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_3=Diario.POSSE_REGISTRO_ESCOLAR,
                diario__posse_etapa_4=Diario.POSSE_REGISTRO_ESCOLAR,
            )
        )

        qs2 = qs.filter(diario__posse_etapa_5=Diario.POSSE_PROFESSOR)

        qs = (qs1 | qs2).distinct()

        if agrupamento == 'Data de Fechamento Período':
            qs = qs.order_by('diario__calendario_academico__data_fechamento_periodo')
        else:
            qs = qs.order_by('professor')

        graficos = []
        if com_grafico:
            inicial = 0
            qtd_por_grafico = 15
            qtd_professores = qs.values_list('professor__id', flat=True).distinct().count()

            for i in range((qtd_professores // qtd_por_grafico) + 1):
                series_diarios = []

                if compacto:
                    tmp = qs[0:5]
                else:
                    tmp = qs[inicial : inicial + qtd_por_grafico]
                inicial += qtd_por_grafico

                for professor_diario in tmp.values('professor__vinculo__pessoa__nome').annotate(qtd_diario=Count('id')):
                    nome_professor = professor_diario['professor__vinculo__pessoa__nome']
                    if compacto:
                        nome_professor = nome_professor.split(' ')[0]
                    series_diarios.append([nome_professor, professor_diario['qtd_diario']])

                id_grafico = f'graficoDiarioProfessor_{i}'
                grafico = PieChart(
                    id_grafico,
                    title='Diários Não-Entregues',
                    subtitle='Diários com professor após o prazo de fechamento do período',
                    data=series_diarios,
                    groups=['Professores'],
                )
                grafico.id = id_grafico
                graficos.append(grafico)

        return qs, graficos


class RelatorioPeriodosAbertosForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects, required=False)
    cursos = forms.MultipleModelChoiceFieldPlus(CursoCampus.objects, required=False)


class EstatisticaForm(forms.FormPlus):
    class Media:
        js = ('/static/edu/js/EstatisticaForm.js',)

    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'
    FILTRO_CHOICES = [['por_ano_letivo', 'Ano Letivo'], ['por_periodo_letivo', 'Ano/Período Letivo']]

    MAPA_SITUACAO = {
        'SITUACAO_MATRICULADO': [
            SituacaoMatriculaPeriodo.APROVADO,
            SituacaoMatriculaPeriodo.APROVEITA_MODULO,
            SituacaoMatriculaPeriodo.DEPENDENCIA,
            SituacaoMatriculaPeriodo.ESTAGIO_MONOGRAFIA,
            SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA,
            SituacaoMatriculaPeriodo.MATRICULADO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatriculaPeriodo.PERIODO_FECHADO,
            SituacaoMatriculaPeriodo.VINDO_DE_TRANSFERENCIA,
            SituacaoMatriculaPeriodo.REPROVADO,
            SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA,
        ],
        'SITUACAO_CANCELADO': [
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
        ],
        'SITUACAO_EVALIDO': [SituacaoMatriculaPeriodo.EVASAO],
        'SITUACAO_JUBILADO': [SituacaoMatriculaPeriodo.JUBILADO],
        'SITUACAO_CANCELADO_EVADIDO_JUBILADO': [
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
            SituacaoMatriculaPeriodo.JUBILADO,
            SituacaoMatriculaPeriodo.EVASAO,
        ],
        'SITUACAO_RETIDO': [SituacaoMatriculaPeriodo.REPROVADO, SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA],
        'SITUACAO_TRANCADO': [
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
            SituacaoMatriculaPeriodo.INTERCAMBIO,
        ],
        'SITUACAO_DEPENDENCIA': [SituacaoMatriculaPeriodo.DEPENDENCIA],
        'SITUACAO_TRANSFERIDO': [
            SituacaoMatriculaPeriodo.TRANSF_CURSO,
            SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
            SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO,
        ],
        'SITUACAO_INGRESSANTES': [],
        'SITUACAO_CONCLUIDOS': [],
    }

    SITUACOES_CHOICES = [
        ['SITUACAO_MATRICULADO', 'Matriculado'],
        ['SITUACAO_CANCELADO', 'Cancelado'],
        ['SITUACAO_EVALIDO', 'Evadido'],
        ['SITUACAO_JUBILADO', 'Jubiliado'],
        ['SITUACAO_CANCELADO_EVADIDO_JUBILADO', 'Cancelado + Evadido + Jubiliado'],
        ['SITUACAO_RETIDO', 'Retido'],
        ['SITUACAO_TRANCADO', 'Trancado'],
        ['SITUACAO_DEPENDENCIA', 'Dependência'],
        ['SITUACAO_TRANSFERIDO', 'Transferido'],
        ['SITUACAO_INGRESSANTES', 'Ingressante'],
        ['SITUACAO_CONCLUIDOS', 'Concluídos'],
    ]

    RENDA_PER_CAPITA_CHOICES = [
        ['', '---------'],
        ['0', 'Nenhum Salário Mínimo'],
        ['0.5', '0,5 Salário Mínimo'],
        ['1', '1 Salário Mínimo'],
        ['1.5', '1,5 Salários Mínimos'],
        ['2', '2 Salários Mínimos'],
        ['2.5', '2,5 Salários Mínimos'],
        ['3', '3 Salários Mínimos'],
        ['3.5', '3,5 Salários Mínimos'],
    ]

    situacao_matricula_periodo = forms.ChoiceField(choices=SITUACOES_CHOICES, label='Situação')

    periodicidade = forms.ChoiceField(label='Periodicidade', choices=FILTRO_CHOICES, required=True, initial='por_ano_letivo')
    apartir_do_ano = forms.ModelChoiceField(Ano.objects.ultimos(), label='A Partir de', required=True)
    ate_ano = forms.ModelChoiceField(Ano.objects.ultimos(), label='Até', required=False)
    excluir_proitec = forms.BooleanField(label='PROITEC', required=False)

    cursos_campus = forms.MultipleModelChoiceField(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')], multiple=True),
    )

    modalidades = forms.MultipleModelChoiceField(Modalidade.objects.all(), label='Modalidades', required=False, widget=CheckboxSelectMultiplePlus())

    sexo = forms.ChoiceField(label='Sexo', required=False, choices=[['', '---------'], ['M', 'Masculino'], ['F', 'Feminino']])
    racas = forms.ModelMultiplePopupChoiceField(Raca.objects, label='Raça', required=False)
    faixas_de_renda_per_capita = forms.MultipleChoiceField(
        label='Renda Familiar per Capita', required=False, choices=RENDA_PER_CAPITA_CHOICES, widget=CheckboxSelectMultiplePlus()
    )

    ira_apartir_de = forms.IntegerField(label='A Partir de', max_value=100, min_value=0, required=False)
    ira_ate = forms.IntegerField(label='Até', max_value=100, min_value=0, required=False)

    renda_apartir_de = forms.ChoiceField(label='A Partir de', choices=RENDA_PER_CAPITA_CHOICES, required=False)
    renda_ate = forms.ChoiceField(label='Até', choices=RENDA_PER_CAPITA_CHOICES, required=False)

    deficiencias = forms.MultipleModelChoiceField(
        Deficiencia.objects,
        label='Deficiências',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Deficiencia.SEARCH_FIELDS,
            multiple=True,
        ),
    )
    outras_nees = forms.MultipleModelChoiceField(
        TipoNEE.objects,
        label='Outras NEEs',
        required=False,
        widget=AutocompleteWidget(
            search_fields=TipoNEE.SEARCH_FIELDS,
            multiple=True,
        ),
    )

    exibicao = forms.MultipleChoiceField(label='Campos Adicionais', choices=[], widget=CheckboxSelectMultiplePlus(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        convenios_field_name = ['excluir_proitec']
        for convenio in Convenio.objects.all():
            convenio_field_name = f'{convenio.pk}'
            convenios_field_name.append(convenio_field_name)
            self.fields[convenio_field_name] = forms.BooleanField(label=f'{convenio}', required=False)

        self.fieldsets = (
            (
                'Filtros Gerais',
                {
                    'fields': (
                        ('situacao_matricula_periodo', 'periodicidade'),
                        ('apartir_do_ano', 'ate_ano'),
                        ('cursos_campus'),
                        ('sexo', 'racas'),
                        ('modalidades'),
                    )
                },
            ),
            ('Índice de Rendimento Acadêmico', {'fields': (('ira_apartir_de', 'ira_ate'),)}),
            ('Renda Familiar per Capita', {'fields': (('renda_apartir_de', 'renda_ate'),)}),
            (
                'Dificiências e outras NEEs',
                {
                    'fields': (
                        'deficiencias',
                        'outras_nees',
                    )
                },
            ),
            ('Excluir', {'fields': (convenios_field_name,)}),
            ('Exportação', {'fields': ('exibicao',)}),
        )

        self.fields['exibicao'].choices = RelatorioForm.get_exibiacao_choices(self.request)
        self.fields['exibicao'].initial = [campo[0] for campo in RelatorioForm.EXIBICAO_INICIAS]

    def processar(self):
        filtrar_por_ano = self.request.GET.get('ignorar_ano_periodo') is None
        qs = (
            MatriculaPeriodo.objects.filter(aluno__ano_letivo__ano__lte=datetime.date.today().year)
            .exclude(aluno__participanteturmaminicurso__turma__gerar_matricula=False)
            .exclude(aluno__curso_campus__modalidade__isnull=True)
        )

        # filtar por convenio
        if self.cleaned_data['excluir_proitec']:
            qs = qs.filter(aluno__matriz__estrutura_id=None) | qs.filter(aluno__matriz__estrutura__proitec=False)

        for convenio in Convenio.objects.all():
            convenio_field_name = f'{convenio.pk}'
            if self.cleaned_data.get(convenio_field_name, False):
                qs = qs.exclude(aluno__convenio=convenio.pk)

        periodicidade = self.cleaned_data.get('periodicidade')

        # filtro por diretoria
        if in_group(self.request.user, 'Secretário Acadêmico'):
            ids_diretorias = Diretoria.locals.all().values_list('id', flat=True)
            qs = qs.filter(aluno__curso_campus__diretoria__id__in=ids_diretorias)

        # filtro por situacao da matricula no periodo
        situacao = self.cleaned_data.get('situacao_matricula_periodo')
        situacoes = EstatisticaForm.MAPA_SITUACAO[situacao]

        if situacoes:
            qs = qs.filter(situacao_id__in=situacoes)

        # filtros por curso, modalidades, sexo, raça, renda per capita e I.R.A
        cursos = self.cleaned_data.get('cursos_campus')
        modalidades = self.cleaned_data.get('modalidades')
        sexo = self.cleaned_data.get('sexo')
        racas = self.cleaned_data.get('racas')
        ira_apartir_de = self.cleaned_data.get('ira_apartir_de')
        ira_ate = self.cleaned_data.get('ira_ate')
        renda_apartir_de = self.cleaned_data.get('renda_apartir_de')
        renda_ate = self.cleaned_data.get('renda_ate')

        if cursos:
            qs = qs.filter(aluno__curso_campus__in=cursos)
        if modalidades:
            qs = qs.filter(aluno__curso_campus__modalidade__in=modalidades)
        if sexo:
            qs = qs.filter(aluno__pessoa_fisica__sexo__exact=sexo)
        if racas:
            qs = qs.filter(aluno__vinculos__raca__in=racas)

        if renda_apartir_de:
            qs = qs.filter(aluno__renda_per_capita__gte=renda_apartir_de)

        if renda_ate:
            qs = qs.filter(aluno__renda_per_capita__lte=renda_ate)

        if ira_apartir_de or ira_ate:
            ira_apartir_de = ira_apartir_de or 0
            ira_ate = ira_ate or 100
            qs = qs.filter(aluno__ira__gte=ira_apartir_de, aluno__ira__lte=ira_ate)

        # filtros por Necessidades Educacionais Específicas
        deficiencias = self.cleaned_data.get('deficiencias')
        outras_nees = self.cleaned_data.get('outras_nees')

        if deficiencias:
            qs = qs.filter(aluno__deficiencias__in=deficiencias)

        if outras_nees:
            qs = qs.filter(aluno__outras_nees__in=outras_nees)

        # montando a lista de campi
        uos = UnidadeOrganizacional.objects.suap().filter(
            id__in=qs.values_list('aluno__curso_campus__diretoria__setor__uo__id', flat=True).distinct()
        )
        uo_selecionada = None
        if 'uo_selecionada' in self.request.GET:
            uo_id = self.request.GET.get('uo_selecionada', 0)
            if uo_id:
                uo_selecionada = UnidadeOrganizacional.objects.suap().get(pk=uo_id)

        if uo_selecionada:
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo=uo_selecionada)

        # motando a lista de anos letivos a partir do ano informado pelo usuário
        anos = []
        apartir_do_ano = self.cleaned_data.get('apartir_do_ano')
        ate_ano = self.cleaned_data.get('ate_ano') or Ano.objects.get_or_create(ano=datetime.date.today().year)[0]
        if self.cleaned_data.get('apartir_do_ano'):
            anos = Ano.objects.filter(ano__gte=apartir_do_ano.ano, ano__lte=ate_ano.ano).order_by('ano')

        ano_selecionado = datetime.datetime.now().year
        if anos:
            ano_selecionado = anos[0]

        if self.request and self.request.GET.get('ano_selecionado'):
            ano_selecionado = Ano.objects.get(pk=self.request.GET.get('ano_selecionado'))

        # motando a lista de períodos letivos a partir do ano informado pelo usuário
        periodos = []
        if apartir_do_ano:
            anos_periodo_letivo = Ano.objects.filter(ano__gte=apartir_do_ano.ano, ano__lte=ate_ano.ano).order_by('ano')
            for ano in anos_periodo_letivo:
                periodos.append(f'{ano}.{1}')
                periodos.append(f'{ano}.{2}')
            if not periodos:
                periodos.append(f'{date.today().year}.{1}')

        periodo_selecionado = periodos[0]
        if self.request and self.request.GET.get('periodo_selecionado'):
            ano_periodo_split = self.request.GET.get('periodo_selecionado').split('.')
            periodo_selecionado = f'{ano_periodo_split[0]}.{ano_periodo_split[1]}'

        # montando o gráfico de evolução anual

        series_ano = []
        qtd_alunos_ano_selecionado = 0
        qs_alunos_ano_selecionado = None
        tabela_resumo = []

        if situacao == 'SITUACAO_CONCLUIDOS':
            situacoes = [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.EGRESSO]
            qs = qs.filter(aluno__situacao__id__in=situacoes)
            qs = qs.filter(ano_letivo__in=anos)
            aluno_ids = qs.values_list('aluno__pk', flat=True).distinct()
            alunos_concluidos = Aluno.objects.filter(pk__in=aluno_ids)
            for ano in anos:
                alunos_concluidos_ano = alunos_concluidos.filter(ano_conclusao=ano.ano)
                qtd_alunos = alunos_concluidos_ano.order_by('id').values_list('id', flat=True).distinct().count()
                series_ano.append([ano.ano, qtd_alunos])
                tabela_resumo.append([ano.ano, qtd_alunos])
                if ano_selecionado == ano:
                    qtd_alunos_ano_selecionado = qtd_alunos
                    qs_alunos_ano_selecionado = alunos_concluidos_ano

            if filtrar_por_ano and qs_alunos_ano_selecionado:
                alunos_concluidos = qs_alunos_ano_selecionado.filter(dt_conclusao_curso__year__gte=ano_selecionado.ano)

            qs = MatriculaPeriodo.objects.filter(pk__in=[aluno.get_ultima_matricula_periodo().pk for aluno in alunos_concluidos])
        elif situacao == 'SITUACAO_INGRESSANTES':
            qs = qs.filter(aluno__ano_letivo__in=anos)
            if periodicidade == 'por_ano_letivo':
                for item in qs.values('aluno__ano_letivo__ano').order_by('aluno__ano_letivo__ano').annotate(qtd_aluno=Count('aluno', distinct=True)):
                    ano = int(item['aluno__ano_letivo__ano'])
                    qtd_alunos = item['qtd_aluno'] or 0
                    qtd_alunos_ano = qtd_alunos
                    series_ano.append([ano, qtd_alunos_ano])
                    tabela_resumo.append([ano, qtd_alunos])
                    if ano_selecionado.ano == ano:
                        qtd_alunos_ano_selecionado = qtd_alunos

                if filtrar_por_ano:
                    qs = qs.filter(aluno__ano_letivo=ano_selecionado).order_by('aluno__id').distinct()
            else:
                for item in (
                    qs.values('aluno__ano_letivo__ano', 'aluno__periodo_letivo')
                    .order_by('aluno__ano_letivo__ano', 'aluno__periodo_letivo')
                    .annotate(qtd_aluno=Count('aluno', distinct=True))
                ):
                    ano_periodo_letivo = '{}.{}'.format(item['aluno__ano_letivo__ano'], item['aluno__periodo_letivo'])
                    qtd_alunos = item['qtd_aluno'] or 0
                    qtd_alunos_ano = qtd_alunos
                    series_ano.append([ano_periodo_letivo, qtd_alunos_ano])
                    tabela_resumo.append([ano_periodo_letivo, qtd_alunos])
                    if periodo_selecionado == ano_periodo_letivo:
                        qtd_alunos_ano_selecionado = qtd_alunos

                if filtrar_por_ano:
                    ano_periodo_letivo = periodo_selecionado.split('.')
                    qs = (
                        qs.filter(aluno__ano_letivo__ano=ano_periodo_letivo[0], aluno__periodo_letivo=ano_periodo_letivo[1])
                        .order_by('aluno__id')
                        .distinct()
                    )
        else:
            qs = qs.filter(ano_letivo__in=anos)
            if periodicidade == 'por_ano_letivo':
                for item in qs.values('ano_letivo__ano').order_by('ano_letivo__ano').annotate(qtd_aluno=Count('aluno', distinct=True)):
                    ano = int(item['ano_letivo__ano'])
                    qtd_alunos = item['qtd_aluno'] or 0
                    qtd_alunos_ano = qtd_alunos
                    series_ano.append([ano, qtd_alunos_ano])
                    tabela_resumo.append([ano, qtd_alunos])
                    if ano_selecionado.ano == ano:
                        qtd_alunos_ano_selecionado = qtd_alunos

                if filtrar_por_ano:
                    qs = qs.filter(ano_letivo=ano_selecionado).order_by('aluno__id').distinct()
            else:
                for item in qs.values('ano_letivo__ano', 'periodo_letivo').annotate(qtd_aluno=Count('aluno')):
                    ano_periodo_letivo = '{}.{}'.format(item['ano_letivo__ano'], item['periodo_letivo'])
                    qtd_alunos = item['qtd_aluno'] or 0
                    qtd_alunos_ano = qtd_alunos
                    series_ano.append([ano_periodo_letivo, qtd_alunos_ano])
                    tabela_resumo.append([ano_periodo_letivo, qtd_alunos])
                    if periodo_selecionado == ano_periodo_letivo:
                        qtd_alunos_ano_selecionado = qtd_alunos

                if filtrar_por_ano:
                    ano_periodo_letivo = periodo_selecionado.split('.')
                    qs = qs.filter(ano_letivo__ano=ano_periodo_letivo[0], periodo_letivo=ano_periodo_letivo[1])

        id_grafico_evolucao_anual = 'id_grafico_evolucao_anual'
        grafico_evolucao_anual = LineChart(id_grafico_evolucao_anual, title='Total de Alunos por Ano', data=series_ano, groups=['Alunos'])
        grafico_evolucao_anual.id = id_grafico_evolucao_anual
        grafico_evolucao_anual.tabela_resumo = tabela_resumo
        grafico_evolucao_anual.qtd_alunos_ano_selecionado = qtd_alunos_ano_selecionado

        alunos = Aluno.objects.filter(id__in=qs.order_by('aluno__id').values_list('aluno__id', flat=True).distinct()).select_related(
            'curso_campus__diretoria__setor__uo', 'curso_campus__modalidade', 'pessoa_fisica__pessoa_ptr'
        )
        mps = (
            qs.order_by('aluno_id', 'ano_letivo_id')
            .distinct('aluno_id', 'ano_letivo_id')
            .select_related('aluno__curso_campus__diretoria__setor__uo', 'aluno__curso_campus__modalidade', 'aluno__pessoa_fisica__pessoa_ptr')
        )

        return uos, anos, periodos, uo_selecionada, ano_selecionado, periodo_selecionado, grafico_evolucao_anual, alunos, mps


class IndicadoresForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    MAPA_SITUACAO = {
        'ATENDIDOS': [
            SituacaoMatriculaPeriodo.EM_ABERTO,
            SituacaoMatriculaPeriodo.MATRICULADO,
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.DEPENDENCIA,
            SituacaoMatriculaPeriodo.DEPENDENCIA,
            SituacaoMatriculaPeriodo.APROVADO,
            SituacaoMatriculaPeriodo.REPROVADO,
            SituacaoMatriculaPeriodo.VINDO_DE_TRANSFERENCIA,
            SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA,
            SituacaoMatriculaPeriodo.ESTAGIO_MONOGRAFIA,
            SituacaoMatriculaPeriodo.PERIODO_FECHADO,
            SituacaoMatriculaPeriodo.INTERCAMBIO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatriculaPeriodo.APROVEITA_MODULO,
            SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA,
        ],
        'CONCLUIDOS': [
            SituacaoMatricula.EGRESSO,
            SituacaoMatricula.CONCLUIDO,
            SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
            SituacaoMatricula.AGUARDANDO_ENADE,
            SituacaoMatricula.AGUARDANDO_SEMINARIO,
        ],
        'EVADIDOS': [
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
            SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO,
            SituacaoMatriculaPeriodo.JUBILADO,
            SituacaoMatriculaPeriodo.EVASAO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
        ],
        'RETIDOS': [
            SituacaoMatriculaPeriodo.REPROVADO,
            SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA,
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        ],
        'REGULARES': [SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.APROVADO, SituacaoMatriculaPeriodo.ESTAGIO_MONOGRAFIA],
    }

    SITUACOES_CHOICES = [
        ['SITUACAO_MATRICULADO', 'Matriculado'],
        ['SITUACAO_CANCELADO', 'Cancelado'],
        ['SITUACAO_RETIDO', 'Retido'],
        ['SITUACAO_TRANCADO', 'Trancado'],
        ['SITUACAO_DEPENDENCIA', 'Dependência'],
        ['SITUACAO_TRANSFERIDO', 'Transferido'],
        ['SITUACAO_INGRESSANTES', 'Ingressante'],
        ['SITUACAO_CONCLUIDOS', 'Concluído'],
    ]

    INDICADORES = {
        '01_TAXA_RETENCAO': [
            '01 - Taxa de Retenção',
            'Este indicador mede o percentual de alunos retidos em relação ao total de matrículas atendidas. '
            'O resultado desse indicador mostra, do universo total de matrículas atendidas em cada período, '
            'o percentual de alunos que atrasaram a conclusão do seu curso. Esse indicador só dará 100% se '
            'todos as matrículas do curso estiverem retidas. O resultado deste indicador possui relação '
            'direta com a duração dos cursos.',
        ],
        '02_TAXA_CONCLUSAO': [
            '02 - Taxa de Conclusão',
            'Este indicador mede o percentual de conclusão em relação ao total de matrículas atendidas. '
            'O resultado deste indicador possui relação direta com a duração dos cursos e com a quantidade '
            'de vagas ofertadas em cada período de análise. Por exemplo, em um curso com duração de 4 anos, '
            'que oferta em todos os período a mesma quantidade de vagas, e todos os alunos concluem no prazo, '
            'o resultado será de 25%, ou seja, este indicador somente atingirá 100% em curso com início e '
            'término no mesmo ano. Por este motivo, não é recomendável analisá-lo de maneira isolada, mas em '
            'conjunto com os indicadores nº 3, 4, 5 e 6, tendo em vista que os cinco indicadores somados '
            'contemplam todas as matrículas atendidas da instituição no ano, totalizando 100%,',
        ],
        '03_TAXA_EVASAO': [
            '03 - Taxa de Evasão',
            'Este indicador mede o percentual de matrículas finalizadas evadidas em relação ao total de matrículas '
            'atendidas. O resultado deste indicador possui relação direta com a duração dos cursos. Este indicador '
            'é influenciado pela taxa de crescimento das matrículas no período. Somado aos indicadores nº 2, 4, 5 e '
            '6 contempla todas as matrículas atendidas da instituição no ano, totalizando 100%,',
        ],
        '04_TAXA_REPROVACOES': [
            '04 - Taxa de Reprovações',
            'Este indicador mede o percentual de reprovação em relação ao total de matrículas atendidas. O '
            'resultado deste indicador possui relação direta com a duração dos cursos e com a quantidade de '
            'vagas ofertadas em cada ano. Por exemplo, em um curso com duração de 4 anos, que oferta em todos '
            'os anos a mesma quantidade de vagas, que não há retenção e todos os alunos reprovam, o resultado '
            'será de 25%, ou seja, este indicador somente atingirá 100% em curso com início e término no mesmo '
            'ano. Por este motivo, não é recomendável analisá-lo de maneira isolada, mas em conjunto com os '
            'indicadores nº 2, 3, 5 e 6, tendo em vista que os cinco indicadores somados contemplam todas as '
            'matrículas atendidas da instituição no ano, totalizando 100%,',
        ],
        '05_TAXA_ATIVOS_REGULARES': [
            '05 - Taxa de Matrícula Ativa Regular',
            'Este indicador mede o percentual de matrículas que ao final de cada período analisado '
            'continuam ativas sem retenção em relação ao total de matrículas atendidas. O resultado '
            'deste indicador possui relação direta com a duração dos cursos. Este indicador é '
            'influenciado pela taxa de crescimento das matrículas no período. Somado aos indicadores '
            'nº 2, 3, 4 e 6 contempla todas as matrículas atendidas da instituição no ano, totalizando 100%,',
        ],
        '06_TAXA_ATIVOS_RETIDOS': [
            '06 - Taxa de Matrícula Ativa Retida',
            'Este indicador mede o percentual de matrículas retidas que ao final de cada período analisado '
            'continuam ativas em relação ao total de matrículas atendidas. O resultado deste indicador possui '
            'relação direta com a duração dos cursos. Este indicador é influenciado pela taxa de crescimento '
            'das matrículas no período. Somado aos indicadores nº 2, 3, 4 e 5 contempla todas as matrículas '
            'atendidas da instituição no ano, totalizando 100%,',
        ],
        '07_TAXA_EFETIVIDADE': [
            '07 - Índice de Efetividade Acadêmica',
            'Este indicador mede o percentual de conclusão efetiva em relação à conclusão prevista no início do '
            'curso. O resultado deste indicador não depende da duração do curso nem da taxa de crescimento da '
            'matricula no período. Apresenta assim o percentual de concluintes dentro do prazo em relação à '
            'previsão de concluintes para o período. Em uma situação hipotética onde todos os alunos '
            'ingressantes de uma instituição concluem o seu curso no prazo previsto, o resultado desse '
            'indicador será 100.',
        ],
        '08_TAXA_SAIDA_EXITO': [
            '08 - Taxa de Saída com Êxito',
            'Este indicador mede o percentual de alunos que alcançaram êxito no curso dentre aqueles que '
            'finalizam o mesmo. Este indicador não é influenciado pela taxa de crescimento da instituição '
            'nem pela duração do curso.',
        ],
        '09_TAXA_PERMANENCIA_EXITO': [
            '09 - Índice de Permanência e Êxito',
            'Este indicador mede a permanência e o êxito dos estudantes da instituição a partir do '
            'somatório da Taxa de Conclusão e da Taxa de Matrícula Continuada Regular. Quanto menor '
            'for o número de matrículas finalizadas sem êxito, e menor for o número de matrículas '
            'retidas, mais o resultado desse indicador se aproximará de 100%.',
        ],
        '10_INDICE_EFICACIA': [
            '10 - Índice de Eficácia',
            'Este indicador quantifica a eficiência das ofertas educacionais da Instituição, através da relação entre o número de alunos concluintes e o número de vagas ofertadas no processo seletivo para suas respectivas turmas.',
        ],
        '11_INDICE_EFICIENCIA': [
            '11 - Índice de Eficiência',
            'Este indicador quantifica a eficiência das ofertas educacionais da Instituição, através da relação entre o número de alunos concluintes e onúmero de alunos ingressantes nas respectivas turmas.',
        ],
    }

    ano_inicio = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo Inicial', required=True)
    ano_fim = forms.ModelChoiceField(Ano.objects.filter(matriculaperiodo__isnull=False).distinct(), label='Ano Letivo Final')
    uos = forms.MultipleModelChoiceField(UnidadeOrganizacional.objects.campi().all(), label='Campi', widget=CheckboxSelectMultiplePlus())
    modalidades = forms.MultipleModelChoiceField(Modalidade.objects.all(), label='Modalidades', widget=CheckboxSelectMultiplePlus())

    deficiencias = forms.MultipleModelChoiceField(
        Deficiencia.objects,
        label='Deficiências',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Deficiencia.SEARCH_FIELDS,
            multiple=True,
        ),
    )
    outras_nees = forms.MultipleModelChoiceField(
        TipoNEE.objects,
        label='Outras NEEs',
        required=False,
        widget=AutocompleteWidget(
            search_fields=TipoNEE.SEARCH_FIELDS,
            multiple=True,
        ),
    )

    fieldsets = (
        ('', {'fields': (('ano_inicio', 'ano_fim'), 'uos', 'modalidades')}),
        ('Deficiências e outras NEEs', {'fields': ('deficiencias', 'outras_nees')}),
    )

    # escolher as modalidades para aparecer nos bullets
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['modalidades'].initial = [campo.pk for campo in Modalidade.objects.all()]
        self.fields['uos'].initial = [campo.pk for campo in UnidadeOrganizacional.objects.campi().all()]

    def clean(self):
        if (
            self.cleaned_data.get('ano_inicio')
            and self.cleaned_data.get('ano_fim')
            and self.cleaned_data.get('ano_inicio').ano > self.cleaned_data.get('ano_fim').ano
        ):
            raise ValidationError('Ano letivo inicial deve ser menor que o final.')
        return self.cleaned_data

    @staticmethod
    def processar_variaveis(
        ano_inicio,
        ano_fim,
        modalidades_id,
        uos_id,
        uo_id=None,
        curso_id=None,
        deficiencias=None,
        outras_nees=None,
    ):
        REPROVADOS = [SituacaoMatriculaPeriodo.REPROVADO, SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA]

        RETIDOS = [
            SituacaoMatriculaPeriodo.REPROVADO,
            SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        ]

        FINALIZADOS = [
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
            SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO,
            SituacaoMatriculaPeriodo.TRANSF_TURNO,
            SituacaoMatriculaPeriodo.TRANSF_CURSO,
            SituacaoMatriculaPeriodo.JUBILADO,
            SituacaoMatriculaPeriodo.EVASAO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
        ]

        CONCLUINTES = (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.EGRESSO, SituacaoMatricula.FORMADO)
        # no gestao nao aplica filtro de exclusão abaixo
        qs = MatriculaPeriodo.objects.exclude(aluno__participanteturmaminicurso__turma__gerar_matricula=False)
        qs = qs.filter(aluno__curso_campus__modalidade_id__in=modalidades_id)
        qs = qs.filter(aluno__curso_campus__diretoria__setor__uo_id__in=uos_id)

        if deficiencias:
            qs = qs.filter(aluno__deficiencias__in=deficiencias)

        if outras_nees:
            qs = qs.filter(aluno__outras_nees__in=outras_nees)

        if uo_id:
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo_id=uo_id)

        if curso_id:
            qs = qs.filter(aluno__curso_campus_id=curso_id)

        qs = qs.select_related('ano_letivo', 'aluno')
        mp = {}
        mp['CONTINUADOS_RETIDOS'] = {}
        mp['CONTINUADOS_REGULARES'] = {}
        mp['RETIDOS'] = {}
        mp['ATENDIDOS'] = {}
        mp['CONCLUIDOS'] = {}
        mp['CONCLUIDOS_PRAZO'] = {}
        mp['EVADIDOS'] = {}
        mp['FINALIZADOS'] = {}
        mp['REPROVADOS'] = {}
        mp['PREVISTOS'] = {}
        mp['CONCLUINTES'] = {}
        mp['INGRESSOS'] = {}
        mp['INGRESSANTES'] = {}

        for ano in range(ano_inicio, ano_fim + 1):
            # filtrando apenas alunos com matrícula período no ano de análise
            tmp = qs.filter(ano_letivo__ano=ano, periodo_letivo=2)
            qs_atendidos = tmp | qs.filter(ano_letivo__ano=ano, periodo_letivo=1).exclude(aluno__in=tmp.values_list('aluno__id', flat=True))
            # obtendo os que já tiveram ao menos uma reprovação até o período de análise
            qs_alunos_retidos = qs.filter(ano_letivo__ano__gt=2000, ano_letivo__ano__lte=ano, situacao__in=RETIDOS).values_list('aluno_id', flat=True)
            # filtrando os alunos que continuam ativos
            qs_continuadas = qs_atendidos.exclude(aluno__ano_conclusao=ano).exclude(situacao__in=FINALIZADOS)
            # filtrando os alunos que concluíram no ano de análise
            qs_finalizadas_com_exito = qs_atendidos.filter(aluno__ano_conclusao=ano)
            # filtrando os alunos que se deixaram o instituto sem concluir o curso
            qs_finalizadas_sem_exito = qs_atendidos.filter(situacao__in=FINALIZADOS)
            # identificando os alunos que deixam o instituo
            qs_finalizados = qs_finalizadas_com_exito | qs_finalizadas_sem_exito
            # filtrando apenas os alunos que nunca reprovaram no período
            qs_continuadas_regulares = qs_continuadas.exclude(aluno__in=qs_alunos_retidos)
            # filtrando os alunos que já reprovaram ao menos um período
            qs_continuadas_retidos = qs_continuadas.filter(aluno__in=qs_alunos_retidos)
            # filtrando os alunos que concluíram no ano de análise e dentro do prazo previsto
            qs_finalizadas_com_exito_no_prazo = qs_finalizadas_com_exito.extra(
                where=['EXTRACT(YEAR FROM edu_aluno.dt_conclusao_curso) <= edu_aluno.ano_let_prev_conclusao']
            )
            qs_dentro_prazo = qs_atendidos.filter(aluno__ano_let_prev_conclusao=ano)
            qs_fora_prazo = qs_atendidos.filter(aluno__ano_let_prev_conclusao__lt=ano)
            # filtrando os alunos que reprovaram no período de análise
            qs_reprovados = qs_atendidos.filter(situacao__in=REPROVADOS)
            # variável AC_OR - calculo copiado do gestao
            qs_concluintes = qs.filter(
                aluno__dt_conclusao_curso__year=ano, aluno__situacao_id__in=CONCLUINTES, aluno__convenio__isnull=True
            ).distinct()
            # variável AICOR_OR - calculo copiado do gestao
            situacao_matricula_periodo_codigo = (0, 1, 2, 3, 4, 9, 10, 11, 15, 18, 19, 23, 25)
            sql = f"(select t2.codigo_academico from edu_historicosituacaomatriculaperiodo t1 inner join edu_situacaomatriculaperiodo t2 on t1.situacao_id = t2.id where matricula_periodo_id = edu_matriculaperiodo.id and data >= '{ano}-01-01' and data <= '{ano}-12-31' order by data desc limit 1)"
            qs_ingressos = qs.extra(where=[sql + ' IN ' + str(situacao_matricula_periodo_codigo)])
            qs_AICOR_OR_1 = qs_ingressos.filter(ano_letivo__ano=ano, periodo_letivo=1)
            qs_AICOR_OR_2 = qs_ingressos.filter(aluno__ano_letivo__ano=ano, aluno__situacao__ativo=True).exclude(aluno__periodo_letivo=1)
            qs_AICOR_OR_3 = qs_ingressos.filter(
                aluno__ano_letivo__ano=ano - 1, aluno__curso_campus__modalidade__id__in=[8, 1], aluno__situacao__codigo_academico=0
            )
            qs_ingressos = qs_AICOR_OR_1 | qs_AICOR_OR_2 | qs_AICOR_OR_3
            qs_ingressos = qs_ingressos.values('aluno__curso_campus', 'ano_letivo', 'periodo_letivo').distinct()
            qs_tmp = MatriculaPeriodo.objects.none()
            for aip in qs_ingressos:
                qs_tmp = qs_tmp | MatriculaPeriodo.objects.filter(
                    aluno__curso_campus=aip['aluno__curso_campus'], ano_letivo=aip['ano_letivo'], periodo_letivo=aip['periodo_letivo']
                )
            # no gestao retorna mais de uma matricula periodo de um mesmo aluno
            qs_ingressos = qs_tmp.filter(aluno__convenio__isnull=True)  # .distinct()

            # variável AIC_OR - calculo copiado do gestao
            qs_ingressantes = qs.filter(aluno__ano_let_prev_conclusao=ano, aluno__curso_campus__modalidade__id__isnull=False)
            qs_ingressantes = qs_ingressantes | qs.filter(aluno__curso_campus__descricao__unaccent__icontains='PROITEC', aluno__ano_letivo__ano=ano)
            qs_ingressantes = qs_ingressantes.filter(aluno__convenio__isnull=True).distinct()

            mp['ATENDIDOS'][ano] = qs_atendidos.values_list('aluno_id', flat=True)
            mp['RETIDOS'][ano] = qs_fora_prazo.values_list('aluno_id', flat=True)
            mp['EVADIDOS'][ano] = qs_finalizadas_sem_exito.values_list('aluno_id', flat=True)
            mp['FINALIZADOS'][ano] = qs_finalizados.values_list('aluno_id', flat=True)
            mp['CONCLUIDOS'][ano] = qs_finalizadas_com_exito.values_list('aluno_id', flat=True)
            mp['REPROVADOS'][ano] = qs_reprovados.values_list('aluno_id', flat=True)
            mp['CONTINUADOS_REGULARES'][ano] = qs_continuadas_regulares.values_list('aluno_id', flat=True)
            mp['CONTINUADOS_RETIDOS'][ano] = qs_continuadas_retidos.values_list('aluno_id', flat=True)
            mp['CONCLUIDOS_PRAZO'][ano] = qs_finalizadas_com_exito_no_prazo.values_list('aluno_id', flat=True)
            mp['PREVISTOS'][ano] = qs_dentro_prazo.values_list('aluno_id', flat=True)
            mp['CONCLUINTES'][ano] = qs_concluintes.values_list('aluno_id', flat=True)
            mp['INGRESSOS'][ano] = qs_ingressos.values_list('aluno_id', flat=True)
            mp['INGRESSANTES'][ano] = qs_ingressantes.values_list('aluno_id', flat=True)

            # indicadores 2,3,4,5,6 somados deveriam dar 100%
        return mp

    @staticmethod
    def gerar_indicadores(anos, variaveis):
        indicadores = {}
        indicadores['01_TAXA_RETENCAO'] = OrderedDict()
        indicadores['02_TAXA_CONCLUSAO'] = OrderedDict()
        indicadores['03_TAXA_EVASAO'] = OrderedDict()
        indicadores['04_TAXA_REPROVACOES'] = OrderedDict()
        indicadores['05_TAXA_ATIVOS_REGULARES'] = OrderedDict()
        indicadores['06_TAXA_ATIVOS_RETIDOS'] = OrderedDict()
        indicadores['07_TAXA_EFETIVIDADE'] = OrderedDict()
        indicadores['08_TAXA_SAIDA_EXITO'] = OrderedDict()
        indicadores['09_TAXA_PERMANENCIA_EXITO'] = OrderedDict()
        indicadores['10_INDICE_EFICACIA'] = OrderedDict()
        indicadores['11_INDICE_EFICIENCIA'] = OrderedDict()

        for ano in anos:
            atendidos = float(variaveis['ATENDIDOS'][ano].count())
            retidos = float(variaveis['RETIDOS'][ano].count())
            concluidos = float(variaveis['CONCLUIDOS'][ano].count())
            evadidos = float(variaveis['EVADIDOS'][ano].count())
            previstos = float(variaveis['PREVISTOS'][ano].count())
            reprovados = float(variaveis['REPROVADOS'][ano].count())
            continuados_regulares = float(variaveis['CONTINUADOS_REGULARES'][ano].count())
            continuados_retidos = float(variaveis['CONTINUADOS_RETIDOS'][ano].count())
            concluidos_prazo = float(variaveis['CONCLUIDOS_PRAZO'][ano].count())
            finalizados = float(variaveis['FINALIZADOS'][ano].count())
            concluintes = float(variaveis['CONCLUINTES'][ano].count())
            ingressos = float(variaveis['INGRESSOS'][ano].count())
            ingressantes = float(variaveis['INGRESSANTES'][ano].count())

            indicadores['01_TAXA_RETENCAO'][ano] = (retidos / (atendidos or 1)) * 100
            indicadores['02_TAXA_CONCLUSAO'][ano] = (concluidos / (atendidos or 1)) * 100
            indicadores['03_TAXA_EVASAO'][ano] = (evadidos / (atendidos or 1)) * 100
            indicadores['04_TAXA_REPROVACOES'][ano] = (reprovados / (atendidos or 1)) * 100
            indicadores['05_TAXA_ATIVOS_REGULARES'][ano] = (continuados_regulares / (atendidos or 1)) * 100
            indicadores['06_TAXA_ATIVOS_RETIDOS'][ano] = (continuados_retidos / (atendidos or 1)) * 100
            indicadores['07_TAXA_EFETIVIDADE'][ano] = (concluidos_prazo / (previstos or 1)) * 100
            indicadores['08_TAXA_SAIDA_EXITO'][ano] = (concluidos / (finalizados or 1)) * 100
            indicadores['09_TAXA_PERMANENCIA_EXITO'][ano] = indicadores['02_TAXA_CONCLUSAO'][ano] + indicadores['05_TAXA_ATIVOS_REGULARES'][ano]
            indicadores['10_INDICE_EFICACIA'][ano] = (concluintes / (ingressos or 1)) * 100
            indicadores['11_INDICE_EFICIENCIA'][ano] = (concluintes / (ingressantes or 1)) * 100
        return indicadores


class RelatorioMigracaoForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Pesquisar'

    fieldsets = (('', {'fields': (('diretoria', 'ano_letivo', 'periodo_letivo'), 'ignorar_ultimo_periodo', 'modalidades')}),)

    diretoria = forms.ModelChoiceField(Diretoria.objects, label='Diretoria', required=True)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos().order_by('-ano'), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    ignorar_ultimo_periodo = forms.BooleanField(label='Ignorar pendências do último período', initial=True, required=False)
    modalidades = forms.MultipleModelChoiceField(
        Modalidade.objects,
        label='Modalidades',
        required=True,
        widget=forms.CheckboxSelectMultiplePlus(),
        initial=Modalidade.objects.all().values_list('id', flat=True),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modalidades'].queryset = self.fields['modalidades'].queryset.exclude(id__in=[Modalidade.FIC, Modalidade.FIC_MENOS])
        self.fields['diretoria'].initial = Diretoria.objects.all()[0].pk

    def filtrar(self, qs):
        diretoria = self.cleaned_data['diretoria']
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        modalidades = self.cleaned_data['modalidades']

        qs = qs.filter(aluno__curso_campus__diretoria=diretoria)
        qs = qs.filter(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo=ano_letivo) | qs.filter(
            aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo
        )

        if modalidades.count() != Modalidade.objects.count():
            qs = qs.filter(aluno__curso_campus__modalidade__in=modalidades.values_list('id', flat=True))

        return qs


class RelatorioCoordenacaoCursoForm(forms.FormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.campi(), label='Campus', required=False)
    diretoria = forms.ModelChoiceField(Diretoria.objects, label='Diretoria', required=False)
    modalidades = forms.MultipleModelChoiceFieldPlus(Modalidade.objects, label='Modalidades', required=False, widget=CheckboxSelectMultiplePlus())
    apenas_ativo = forms.BooleanField(label='Apenas Ativos', required=False)

    def processar(self):
        uo = self.cleaned_data['uo']
        diretoria = self.cleaned_data['diretoria']
        apenas_ativo = self.cleaned_data['apenas_ativo']
        modalidades = self.cleaned_data['modalidades']
        qs = CursoCampus.objects.all()
        if apenas_ativo:
            qs = qs.filter(ativo=True)
        if diretoria:
            qs = qs.filter(diretoria=diretoria)
        if uo:
            qs = qs.filter(diretoria__setor__uo=uo)
        if modalidades:
            qs = qs.filter(modalidade__in=modalidades)
        return qs
