import datetime
import random
from datetime import date, timedelta

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.forms import HiddenInput
from pycpfcnpj import cpfcnpj

from comum.models import Ano, APIExterna, Configuracao, Municipio, PessoaEndereco, PovoIndigena, PrestadorServico, TrocarSenha, Vinculo
from comum.types import PessoaFisicaCadastro, PessoaTelefoneCadastro, PrestadorServicoCadastro
from comum.utils import get_setor_cppd
from djtools import forms
from djtools.choices import Anos, Meses
from djtools.forms import ReadOnlyField
from djtools.forms.widgets import AutocompleteWidget, BRCpfWidget, TreeWidget
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import in_group
from djtools.thumbs import ImageFormFieldWithThumbs
from djtools.utils import get_datetime_now, mask_numbers, retirar_preposicoes_nome, send_mail, sync_ldap_user, to_ascii
from rh.deduplicacao.documentos import eh_sintetico
from rh.deduplicacao.entrada import (
    recusar_cadastro_de_prestador,
    MENSAGEM_CPF_DE_OUTRA_PESSOA,
    MENSAGEM_PASSAPORTE_OUTRA_PESSOA,
    dona_do_cpf,
    filtro_par_passaporte,
    recusar_documento_de_outra_pessoa,
)
from rh.importador_ws import ImportadorWs
from rh.management.commands import importador_pj
from rh.models import (
    PCA,
    AcaoSaude,
    AfastamentoSiape,
    AgendaAtendimentoHorario,
    AreaVinculacao,
    Atividade,
    Avaliador,
    Banco,
    CampoExcecao,
    CargaHorariaReduzida,
    CargoClasse,
    CargoEmprego,
    CargoEmpregoArea,
    DataConsultaBloqueada,
    Deficiencia,
    ExcecaoDado,
    FormaProvimentoVacancia,
    Funcao,
    HorarioAgendado,
    HorarioSemanal,
    Instituicao,
    JornadaTrabalho,
    JornadaTrabalhoPCA,
    Ocorrencia,
    PessoaExterna,
    PessoaFisica,
    PessoaInfoComplementar,
    PessoaJuridica,
    PessoaJuridicaContato,
    PosicionamentoPCA,
    QuantitativoCargoClassePorCampus,
    RegimeJuridico,
    RegimeJuridicoPCA,
    Servidor,
    ServidorAfastamento,
    ServidorFuncaoHistorico,
    ServidorOcorrencia,
    ServidorReativacaoPermanente,
    ServidorReativacaoTemporaria,
    ServidorSetorHistorico,
    Setor,
    SetorJornadaHistorico,
    Situacao,
    SolicitacaoAlteracaoFoto,
    Titulacao,
    UnidadeOrganizacional,
)
from suap import nomenclatura


def situacoes_usadas():
    servidores = Servidor.objects.filter(situacao=OuterRef('pk'))
    return Situacao.objects.annotate(has_servidor=Exists(servidores)).filter(has_servidor=True).order_by('id')


def ocorrencias_usadas():
    return Ocorrencia.objects.filter(
        id__in=ServidorOcorrencia.objects.filter(ocorrencia__isnull=False).values_list('ocorrencia', flat=True).order_by('ocorrencia').distinct()
    )


def get_classe_usadas():
    return (
        CargoClasse.objects.annotate(tem_servidor=Exists(Servidor.objects.filter(cargo_classe=OuterRef('pk'))))
        .filter(tem_servidor=True)
        .order_by('id')
    )


def get_funcao_choices():
    funcao_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    [funcao_choices.append((funcao.id, str(funcao))) for funcao in Funcao.objects.usadas()]
    return funcao_choices


def get_atividade_usadas():
    return (
        Atividade.objects.annotate(tem_servidor=Exists(Servidor.objects.filter(funcao_atividade=OuterRef('pk'))))
        .filter(tem_servidor=True)
        .order_by('id')
    )


def get_jornada_usadas():
    jornadas = (
        JornadaTrabalho.objects.annotate(tem_servidor=Exists(Servidor.objects.filter(jornada_trabalho=OuterRef('pk'))))
        .filter(tem_servidor=True)
        .order_by('id')
    )
    return jornadas


def get_jornada_setor_choices():
    setores = SetorJornadaHistorico.objects.all()
    jornada_setor_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    jornadas_setores = (
        setores.filter(jornada_trabalho__isnull=False).values_list('jornada_trabalho', flat=True).order_by('jornada_trabalho').distinct()
    )
    jornadas_setor = JornadaTrabalho.objects.filter(id__in=jornadas_setores).order_by('nome').distinct()
    for jornada in jornadas_setor:
        jornada_setor_choices.append((jornada.id, str(jornada)))
    return jornada_setor_choices


def get_regime_usados():
    regimes = (
        RegimeJuridico.objects.annotate(tem_servidor=Exists(Servidor.objects.filter(regime_juridico=OuterRef('pk'))))
        .filter(tem_servidor=True)
        .order_by('id')
    )
    return regimes


def get_campus_lotacao_siape_choices():
    campus_lotacao_siape_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    campi = UnidadeOrganizacional.objects.siape().all()
    for campus in campi:
        campus_lotacao_siape_choices.append((campus.id, str(campus)))
    return campus_lotacao_siape_choices


def get_setor_exercicio_siape_choices():
    setor_exercicio_siape_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    setores = Setor.objects.siape().all()
    for setor in setores:
        setor_exercicio_siape_choices.append((setor.id, str(setor)))
    return setor_exercicio_siape_choices


def get_campus_exercicio_siape_choices():
    campus_exercicio_siape_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    campi = UnidadeOrganizacional.objects.siape().all()
    for campus in campi:
        campus_exercicio_siape_choices.append((campus.id, str(campus)))
    return campus_exercicio_siape_choices


def get_deficiencia_choices():
    deficiencia_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    qs_deficiencia = Deficiencia.objects.all()
    for d in qs_deficiencia:
        deficiencia_choices.append((d.id, str(d.descricao)))
    return deficiencia_choices


def get_nivel_choices():  # FIX-ME: há algum model com essas informações?
    """
    nível = XYY
    X = nível de capacitação (1 a 4)
    YY = nível por mérito (1 a 16)
    nível inicial = 101
    nível final = 416
    """
    nivel_choices = [('qualquer', '--Qualquer--'), ('vazio', '--Vazio--'), ('nao_vazio', '--Não vazio--')]
    for capacitacao in range(1, 5):  # 1 a 4
        for merito in range(1, 17):  # 1 a 16
            capacitacao_merito = '{}{}'.format(capacitacao, ((merito < 10 and f'0{merito}') or merito))
            nivel_choices.append((capacitacao_merito, capacitacao_merito))
    return nivel_choices


class ConfiguracaoForm(forms.FormPlus):
    setor_rh = forms.ModelChoiceFieldPlus(Setor.objects, label='Setor da Diretoria de Gestão de Pessoas', help_text='DIGPE', required=False)
    setor_procuradoria = forms.ModelChoiceFieldPlus(Setor.objects, label='Setor da Procuradoria Jurídica', help_text='PROJU', required=False)
    setor_auditoria_geral = forms.ModelChoiceFieldPlus(Setor.objects, label='Setor da Auditoria Geral', help_text='AUDGE', required=False)
    setor_remocaointerna_rh = forms.ModelChoiceFieldPlus(
        Setor.objects, label='Setor de Gestão da Remoção Interna', help_text='CODEPE', required=False
    )

    sigla_funcao_substituicao_chefia = forms.CharFieldPlus(label='Sigla Função para Substituição de Chefia', help_text='SUB-CHEFIA', required=False)
    sigla_funcao_apoio_gestao = forms.CharFieldPlus(label='Sigla Função de Apoio à Gestão', help_text='FAG-IFXX', required=False)
    fag_considerado_chefia = forms.BooleanField(
        label='Função de Apoio à Gestão - é considerado de chefia?',
        help_text='Marque essa opção e entenda que uma Função de Apoio à Gestão permitirá gerenciar dados e informações dos servidores como chefe do setor.',
        required=False,
    )
    funcoes_codigos_e_niveis_liberados_frequencia = forms.CharFieldPlus(
        label='Códigos e Níveis das Funções Liberadas do Controle de Frequência',
        help_text="Informe os códigos e níveis no formato 'código-nível' e separados por vírgula (Ex: CD-1,CD-2,CD-3,CD-0001,AB-4).",
        required=False,
    )
    afastamentos_pgd = forms.MultipleModelChoiceFieldPlus(
        label='Afastamentos que representam o PGD',
        queryset=AfastamentoSiape.objects,
        required=False,
        help_text='Escolha os afastamentos do SIAPE que serão a representação de que o servidor está em PGD. Esses afastamentos não irão impactar em redução de CH do dia e o servidor com esse afastamento será considerado em efetivo exercício.',
    )

    permite_email_institucional_email_secundario = forms.BooleanField(
        label='Permite email institucional no email secundário?',
        help_text='Marque essa opção caso permita que na escolha do email secundário possa ser escolhido email institucional.',
        required=False,
    )

    email_cppd = forms.CharFieldPlus(
        label='Email CPPD',
        help_text='Informe o email CPPD que será utilizado.',
        required=False,
    )

    ajustar_setores_na_reitoria = forms.BooleanField(
        label='Ajustar setores na reitoria?',
        help_text='Ao marcar esta opção, todos os setores que estão com o código de setor pai apontando para o instituto (ex.: IFRN) serão movidos para dentro da Reitoria.',
        required=False,
    )

    codigo_uorg_vinculacao = forms.CharFieldPlus(
        label='Código UORG da Instituição', required=False, help_text='Código uorg de 9 dígitos (ex.: 000000001) que vem nos arquivos de extração.'
    )

    nao_permitir_servidor_na_raiz = forms.BooleanField(
        label='NÃO permitir servidores na raiz',
        help_text='Quando marcar esta opção, todos os servidores que estiverem com o setor de exercício igual a IFRN, por exemplo, serão movidos para a reitoria.',
        required=False,
    )

    # aplicação das novas inconsistências a partir da demanda 1547
    inconsistencia_intervalo_inferior_1h_data_inicio = forms.DateFieldPlus(
        label='Data início para aplicação da inconsistência de intervalo inferior a 1h',
        required=False,
        help_text='Para fins de controle do ponto do servidor.',
    )
    inconsistencia_intervalo_superior_3h_data_inicio = forms.DateFieldPlus(
        label='Data início para aplicação da inconsistência de intervalo superior a 3h',
        required=False,
        help_text='Para fins de controle do ponto do servidor.',
    )
    inconsistencia_nenhum_intervalo_data_inicio = forms.DateFieldPlus(
        label='Data início para aplicação da inconsistência de ausência de intervalo',
        required=False,
        help_text='Para fins de controle do ponto do servidor.',
    )
    # inconsistencia_turno_insuficiente_data_inicio = forms.DateFieldPlus(
    #     label='Data início para aplicação da inconsistência de turno insuficiente (menor que 2h)',
    #     required=False,
    #     help_text='Para fins de controle do ponto do servidor.'
    # )
    # inconsistencia_turno_excessivo_data_inicio = forms.DateFieldPlus(
    #     label='Data início para aplicação da inconsistência de turno excessivo (maior que 6h15min)',
    #     required=False,
    #     help_text='Para fins de controle do ponto do servidor.',
    # )
    permite_desconto_de_carga_horaria = forms.BooleanField(
        label='Permite desconto de carga horária por parte do chefe imediato durante as avaliações de frequência?',
        required=False,
        help_text='Para fins de controle do ponto do servidor.',
    )
    permite_solicitacao_abono_parcial = forms.BooleanField(
        label='Permite solicitação de abonos parciais por parte dos servidores?',
        required=False,
        help_text='Para fins de controle do ponto do servidor.',
    )
    deixa_apenas_uma_funcao_siape_ativa = forms.BooleanField(
        label='Manter apenas um função SIAPE ativa?',
        help_text='Ao marcar esta opção, será mantida apenas a função mais nova ativa, marcando em todas as outras ainda ativas uma data fim.',
        required=False,
    )
    executar_save_pos_importacao = forms.BooleanField(
        label="Executar um 'save' após a importação SIAPE?",
        help_text="Ao marcar esta opção, será executado um 'save' em todos os servidores ativos para que as rotinas do save da classe servidor seja executada. Existem institutos/órgão que essa rotina não está sendo executada durante o processo de importação.",
        required=False,
    )
    importacao_siape_workers = forms.IntegerField(
        label='Arquivos do extrator importados em paralelo',
        required=False,
        min_value=1,
        max_value=16,
        help_text='Quantos layouts do extrator SIAPE são importados ao mesmo tempo. Em branco: 4. Use 1 para importar em série.',
    )
    importacao_siape_tamanho_lote = forms.IntegerField(
        label='Tamanho do lote da importação SIAPE',
        required=False,
        min_value=500,
        max_value=100000,
        help_text='Layouts do extrator com mais linhas que isto são divididos em lotes processados em paralelo. Em branco: 5000.',
    )
    permite_multiplas_funcoes = forms.BooleanField(
        label='Permite multiplas funções para um mesmo servidor',
        required=False,
        help_text='Ao marcar essa opção, será permitido que um servidor tenha mais de uma função ao mesmo tempo.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        afastamentos_pgd = Configuracao.get_valor_por_chave(app='rh', chave='afastamentos_pgd')
        self.fields['afastamentos_pgd'].initial = list(afastamentos_pgd.split(',')) if afastamentos_pgd else []


def GetBuscarServidorForm():
    # Nota: deixei que este form seja acessado via factory porque o correto
    # funcionamento do campo setor precisa que o usuário esteja logado; assim,
    # o formulário não pode ser carregado estaticamente.

    class BuscaServidorForm(forms.FormPlus):
        EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO = (
            ('qualquer', '--Qualquer--'),
            ('vazio', '--Vazio--'),
            ('nao_vazio', '--Não vazio--'),
        )
        EXTRA_CHOICES_DISCIPLINA_INGRESSO = (
            ('vazio', '--Vazio--'),
            ('nulo', '--Docente sem disciplina de ingresso cadastrada--'),
        )

        matricula = forms.CharField(max_length=10, required=False, label='Matrícula', help_text='Filtrar por exatamente esta matrícula')
        nome = forms.CharField(max_length=80, required=False, help_text='Filtrar por parte do nome')
        cpf = forms.CharField(max_length=14, required=False, label='CPF', help_text='Filtrar por exatamente este CPF')

        categoria_choices = (
            ('todos', 'Todos os Servidores'),
            ('docente', 'Apenas Docentes'),
            ('tecnico_administrativo', 'Apenas Administrativos'),
        )
        categoria = forms.ChoiceField(choices=categoria_choices, required=False)

        ativo_choices = (
            ('', 'Qualquer servidor'),
            ('0', 'Servidores com ocorrência de exclusão'),
            ('1', 'Servidores sem ocorrência de exclusão'),
        )
        ativo = forms.ChoiceField(label='Escopo da Pesquisa', choices=ativo_choices, required=False, initial='1', help_text='')

        cargo_emprego = forms.ModelChoiceFieldPlus(
            CargoEmprego.utilizados.all().order_by('nome').select_related('grupo_cargo_emprego'),
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        cargo_emprego_area = forms.ModelChoiceFieldPlus(
            CargoEmpregoArea.objects.all().order_by('descricao').select_related('cargo_emprego'),
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        classe = forms.ModelChoiceFieldPlus(
            get_classe_usadas(),
            required=False,
            help_text='Mostrando somente as classes utilizadas pela instituição',
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        nivel_choices = get_nivel_choices()
        nivel = forms.ChoiceField(label='Nível', choices=nivel_choices, required=False)

        funcao = forms.ModelChoiceFieldPlus(
            Funcao.objects.usadas(),
            label='Função',
            help_text='Mostrando somente as funções utilizadas pela instituição',
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        funcao_atividade = forms.ModelChoiceFieldPlus(
            get_atividade_usadas(),
            label='Atividade',
            help_text='Mostrando somente as atividades utilizadas pela instituição',
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        jornada_trabalho = forms.ModelChoiceFieldPlus(
            get_jornada_usadas(),
            label='Jornada de Trabalho do Servidor',
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )
        if 'pgd2' in settings.INSTALLED_APPS:
            modalidade_regime_trabalho_choices = [('qualquer', '--Qualquer--'), ('presencial', 'Presencial'), ('pgd', 'PGD')]
            modalidade_regime_trabalho = forms.ChoiceField(
                label='Modalidade de regime de trabalho', choices=modalidade_regime_trabalho_choices, required=False
            )

        jornada_setor_choices = get_jornada_setor_choices()
        jornada_setor_trabalho = forms.ChoiceField(label='Jornada de Trabalho do Setor', choices=jornada_setor_choices, required=False)

        regime_juridico = forms.ModelChoiceFieldPlus(
            get_regime_usados(),
            label='Regime Jurídico',
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        titulacao = forms.ModelChoiceFieldPlus(
            Titulacao.objects.all().order_by('nome'),
            label='Titulação',
            required=False,
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )
        afastamento = forms.ModelChoiceFieldPlus(
            AfastamentoSiape.objects.all().order_by('nome'),
            label='Afastamento',
            required=False,
            help_text='Filtra pelos servidores que já tiveram ou tem esse tipo de afastamento.',
        )

        situacao = forms.ModelChoiceFieldPlus(
            queryset=situacoes_usadas(), label='Situação', required=False, extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO, initial=None
        )

        setor = forms.ModelChoiceFieldPlus(Setor.objects.suap_ativos().all(), label='Setor SUAP', required=False, help_text='Selecione um setor SUAP')
        setor_contem = forms.CharField(label='Setor SUAP', required=False, help_text='Parte do nome ou da sigla do setor SUAP')

        setor_lotacao_siape = forms.ModelChoiceFieldPlus(
            Setor.objects.siape().all(),
            label='Setor lotação SIAPE',
            required=False,
            help_text='Selecione um setor de lotação SIAPE',
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        campus_lotacao_siape = forms.ModelChoiceFieldPlus(
            UnidadeOrganizacional.objects.siape().all(),
            label=f'{nomenclatura.campus} Lotação SIAPE',
            required=False,
            help_text='Selecione um campus de lotação SIAPE',
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        setor_exercicio_siape = forms.ModelChoiceFieldPlus(
            Setor.objects.siape().all(),
            label='Setor Exercício SIAPE',
            required=False,
            help_text='Selecione um setor de exercício SIAPE',
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        campus_exercicio_siape = forms.ModelChoiceFieldPlus(
            UnidadeOrganizacional.objects.siape().all(),
            label=f'{nomenclatura.campus} Exercício SIAPE',
            required=False,
            help_text='Selecione um campus de exercício SIAPE',
            extra_choices=EXTRA_CHOICES_QUALQUER_VAZIO_NAO_VAZIO,
        )

        recursivo = forms.BooleanField(required=False, help_text='Incluir sub-setores para filtro "Setor SUAP"')

        agrupador = forms.CharField(
            label='Agrupar por',
            required=False,
            widget=forms.Select(),
            help_text='Para agrupar, marque pelo menos uma das informações na caixa abaixo',
        )

        subagrupador = forms.CharField(
            label='Sub-agrupar por',
            required=False,
            widget=forms.Select(),
            help_text='Para agrupar, marque pelo menos uma das informações na caixa abaixo',
        )

        tem_digital_choices = (('', 'Qualquer'), ('sim', 'Sim'), ('nao', 'Não'))
        tem_digital = forms.ChoiceField(label='Tem digital cadastrada', choices=tem_digital_choices, required=False, help_text='')

        aniversariantes = forms.MesField(label='Aniversariantes', required=False, empty_label='Todos')
        if 'edu' in settings.INSTALLED_APPS:
            from edu.models import Disciplina

            disciplina_ingresso = forms.ModelChoiceFieldPlus(
                Disciplina.objects.all(),
                label='Disciplina de Ingresso',
                required=False,
                help_text='No caso de docentes',
                extra_choices=EXTRA_CHOICES_DISCIPLINA_INGRESSO,
            )

        deficiencia = forms.ChoiceField(label='Deficiência', choices=get_deficiencia_choices(), required=False)
        jornada_fields = ''
        if 'pgd2' in settings.INSTALLED_APPS:
            # Adiciona o campo modalidade_regime_trabalho após jornada_trabalho
            jornada_fields = ('modalidade_regime_trabalho',)
        fieldsets = (
            ('Filtro Geral', {'fields': ('ativo',)}),
            ('Filtro por Dados Pessoais', {'fields': (('nome', 'cpf'), 'deficiencia')}),
            (
                'Filtro por Dados Funcionais',
                {
                    'fields': (
                        ('matricula', 'categoria'),
                        'situacao',
                        'cargo_emprego',
                        'cargo_emprego_area',
                        ('classe', 'nivel'),
                        ('funcao', 'funcao_atividade'),
                        ('jornada_trabalho', 'regime_juridico', 'jornada_setor_trabalho'),
                        jornada_fields,
                    )
                },
            ),
            ('Filtro por Dados como Professor', {'fields': ('disciplina_ingresso',)}),
            (
                'Filtro por Setor Lotação/Exercício',
                {
                    'fields': (
                        'setor',
                        'recursivo',
                        'setor_contem',
                        ('setor_lotacao_siape', 'campus_lotacao_siape'),
                        ('setor_exercicio_siape', 'campus_exercicio_siape'),
                    )
                },
            ),
            ('Filtro por Outros dados', {'fields': ('afastamento', 'titulacao', 'aniversariantes', 'tem_digital')}),
            ('Agrupar Resultados', {'fields': ('agrupador', 'subagrupador')}),
        )
        METHOD = 'GET'

    return BuscaServidorForm


def get_campus_choices():
    campus_choices = [('', 'Todos')]
    campi = UnidadeOrganizacional.objects.suap().all()
    for campus in campi:
        campus_choices.append((campus.id, str(campus)))
    return campus_choices


def get_funcaoservidor_choices():
    funcao_choices = [('', 'Todas')]
    funcoes = Funcao.objects.usadas()
    for funcao in funcoes:
        funcao_choices.append((funcao.id, str(funcao)))
    return funcao_choices


def ServidorFuncaoFormFactory():
    """
    Cria uma classe para construir filtros para a busca de servidores
    com funcao.

    """

    class CampusFuncao(forms.FormPlus):
        campus_choices = get_campus_choices()
        campus = forms.ChoiceField(
            choices=campus_choices, label=nomenclatura.campus, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}), required=False
        )
        funcao_choices = get_funcaoservidor_choices()
        funcao = forms.ChoiceField(
            choices=funcao_choices, label='Função', widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}), required=False
        )

    return CampusFuncao


def CampusAnoFormFactory():
    class CampusAnoForm(forms.FormPlus):
        campus_choices = get_campus_choices()
        campus = forms.ChoiceField(choices=campus_choices, label=nomenclatura.campus, required=False)

        ano = forms.ChoiceField(choices=Anos.get_choices(), label='Ano', required=True)

    return CampusAnoForm


class SetorForm(forms.ModelFormPlus):
    setores_compartilhados = forms.MultipleModelChoiceFieldPlus(required=False, queryset=Setor.objects.suap_ativos().all())
    superior = forms.ModelChoiceField(label='Setor Superior', queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(), required=False)

    class Meta:
        model = Setor
        exclude = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto') if 'documento_eletronico' in settings.INSTALLED_APPS else None
        if DocumentoTexto:
            documentos_publicos_assinados = DocumentoTexto.objects.publicos_assinados()
            self.fields['portaria_criacao'].required = documentos_publicos_assinados.exists()
            self.fields[
                'portaria_criacao'
            ].help_text = 'Caso a portaria já esteja em formato digital no módulo de documentos eletrônicos use esse campo.'
            self.fields['portaria_criacao'].queryset = documentos_publicos_assinados
        self.fieldsets = [
            ('Dados gerais', {'fields': ['codigo', 'codigo_siorg', 'superior', 'sigla', 'nome', 'excluido']}),
            ('Protocolo', {'fields': ['setores_compartilhados']}),
            ('Avaliação Integrada', {'fields': ['areas_vinculacao']}),
            (
                'Funcionamento',
                {'fields': ['data_criacao', 'portaria_criacao', 'horario_funcionamento', 'bases_legais_internas', 'bases_legais_externas']},
            ),
        ]

        if not self.request.user.is_superuser:
            del self.fieldsets[0][1]['fields'][0]

    def clean_superior(self):
        if self.cleaned_data['superior'] and self.instance.id == self.cleaned_data['superior'].id:
            raise forms.ValidationError('O setor superior não pode ser o próprio setor.')
        return self.cleaned_data['superior']


class BasesLegaisSetorForm(forms.ModelFormPlus):
    class Meta:
        model = Setor
        fields = ('data_criacao', 'horario_funcionamento', 'bases_legais_internas', 'bases_legais_externas')


class SetorAddForm(SetorForm):
    # jornada de trabalho atual APENAS durante a inclusão de um novo setor
    jornada_trabalho = forms.ModelChoiceField(label='Jornada de Trabalho Atual', queryset=JornadaTrabalho.objects, required=False)
    data_inicio_da_jornada = forms.DateFieldPlus(label='Data Inicial da Jornada de Trabalho Atual', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fieldsets += ('Carga Horária Atual', {'fields': ['jornada_trabalho', 'data_inicio_da_jornada']})

    def clean(self):
        cleaned_data = super().clean()
        #
        jornada_trabalho = cleaned_data.get('jornada_trabalho', None)
        data_inicio_da_jornada = cleaned_data.get('data_inicio_da_jornada', None)
        if jornada_trabalho or data_inicio_da_jornada:
            if jornada_trabalho and not data_inicio_da_jornada:
                self.add_error('data_inicio_da_jornada', 'A Data Inicial da Jornada de Trabalho Atual deve ser informada.')
            if data_inicio_da_jornada and not jornada_trabalho:
                self.add_error('jornada_trabalho', 'A Jornada de Trabalho Atual deve ser informada.')
        #
        return cleaned_data

    def _save_m2m(self):
        super()._save_m2m()
        #
        # adiciona jornada de trabalho que foi informada durante a inclusão do novo setor
        jornada_trabalho = self.cleaned_data.get('jornada_trabalho', None)
        data_inicio_da_jornada = self.cleaned_data.get('data_inicio_da_jornada', None)
        if jornada_trabalho and data_inicio_da_jornada:
            nova_jornada = SetorJornadaHistorico()
            nova_jornada.setor = self.instance  # nesse ponto, o setor já foi salvo e tem ID
            nova_jornada.jornada_trabalho = jornada_trabalho
            nova_jornada.data_inicio_da_jornada = data_inicio_da_jornada
            nova_jornada.save()


def SetorJornadaHistoricoFormFactory(request):
    raiz = Setor.objects.suap_ativos().none()
    if request.user.has_perm('rh.eh_rh_sistemico'):
        raiz = Setor.raiz_suap()
    elif request.user.has_perm('rh.pode_gerenciar_setor_jornada_historico'):
        funcionario = request.user.get_relacionamento()
        raiz = funcionario.setor.superior if funcionario.setor else raiz

    class SetorJornadaHistoricoForm(forms.ModelForm):
        setor = forms.ModelChoiceField(queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(root_nodes=[raiz]))

        class Meta:
            model = SetorJornadaHistorico
            fields = ('setor', 'jornada_trabalho', 'data_inicio_da_jornada', 'data_fim_da_jornada')

        def clean(self):
            super().clean()
            if not self.errors:
                #
                # periodo adicionado/editado
                #
                periodo_data_inicio = self.cleaned_data['data_inicio_da_jornada']
                periodo_data_fim = self.cleaned_data['data_fim_da_jornada']

                #
                # valida o período
                #
                if periodo_data_fim and periodo_data_inicio > periodo_data_fim:
                    self._errors['data_inicio_da_jornada'] = self.error_class(['A data inicial deve ser menor ou igual à data final.'])
                    del self.cleaned_data['data_fim_da_jornada']

            return self.cleaned_data

    return SetorJornadaHistoricoForm


class PessoaEnderecoForm(forms.ModelFormPlus):
    municipio = forms.ModelChoiceFieldPlus(Municipio.objects, label='Município')
    complemento = forms.CharFieldPlus(label='Complemento', required=False)
    cep = forms.BrCepField(max_length=255, required=True, label='CEP')

    class Meta:
        model = PessoaEndereco
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['via_form_suap'].widget = forms.HiddenInput()
        self.fields['via_form_suap'].initial = True


class PessoaFisicaForm(forms.ModelFormPlus):
    class Meta:
        model = PessoaFisica
        exclude = ()

    cpf = forms.BrCpfField()
    nascimento_data = forms.DateFieldPlus(required=False, label='Data de Nascimento')

    def clean_cpf(self) -> str:
        cpf = self.cleaned_data.get('cpf')
        # só quando o CPF muda: a PF com duplicata legada segue editável até a deduplicação rodar
        cpf_mudou = 'cpf' in self.changed_data or not self.instance.pk
        if not cpfcnpj.validate(cpf):
            self.add_error('cpf', 'O CPF informado não é válido')
        elif cpf_mudou and dona_do_cpf(cpf, self.instance.pk):
            self.add_error('cpf', MENSAGEM_CPF_DE_OUTRA_PESSOA)
        return cpf

    def clean(self) -> dict:
        # antes do super().clean(), que levanta se já houver erro de campo. Só quando o documento muda, como no clean_cpf.
        if {'passaporte', 'pais_origem'} & set(self.changed_data) or not self.instance.pk:
            self._recusar_passaporte_de_outra_pessoa()
        return super().clean()

    def _recusar_passaporte_de_outra_pessoa(self) -> None:
        """O par país + passaporte de outra PF: na Release 2 seria IntegrityError; na 1, par repetido que o planejar separaria."""
        pais = self.cleaned_data.get('pais_origem') or self.instance.pais_origem  # o admin não mostra o país: vale o da instância
        par = filtro_par_passaporte(self.cleaned_data.get('passaporte'), pais)
        if PessoaFisica.objects.filter(par).exclude(pk=self.instance.pk).exists():
            self.add_error('passaporte', MENSAGEM_PASSAPORTE_OUTRA_PESSOA)


class PessoaExternaForm(forms.ModelFormPlus):
    class Meta:
        model = PessoaExterna
        fields = ('nome', 'nome_social', 'sexo', 'cpf', 'nascimento_data')

    cpf = forms.BrCpfField()
    email = forms.EmailField(required=True)
    nascimento_data = forms.DateFieldPlus(required=False, label='Data de Nascimento')

    def clean_cpf(self) -> str:
        cpf = self.cleaned_data.get('cpf')
        if not cpfcnpj.validate(cpf):
            self.add_error('cpf', 'O CPF informado não é válido.')
        if self.instance and not self.instance.pk and PessoaExterna.objects.filter(cpf=cpf):
            self.add_error('cpf', 'O CPF informado já está cadastrado.')
        if self.instance.pk and self.instance.cpf_diverge_da_pessoa_fisica(cpf, self.instance.cpf):
            self.add_error('cpf', PessoaExterna.MENSAGEM_TROCA_DE_CPF)

        return cpf

    def clean(self) -> dict:
        # na edição a PF já está vinculada e o save() não a verifica
        if not self.instance.pk and 'cpf' in self.cleaned_data:
            recusar_documento_de_outra_pessoa(self, 'cpf', self.cleaned_data.get('cpf'), self.cleaned_data.get('nascimento_data'))
        return super().clean()


class PessoaJuridicaForm(forms.ModelFormPlus):
    nome = forms.CharField(label='Razão Social', required=True)
    nome_fantasia = forms.CharField(label='Nome Fantasia', required=False, help_text='Na ausência do nome fantasia, é para repetir a razão social')
    cnpj = forms.BrCnpjField()
    email = forms.EmailField(label='E-mail', required=False)  # migrado p/ Vinculo.email_pessoal

    class Meta:
        model = PessoaJuridica
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # email vive no Vinculo; popula o valor inicial a partir do vínculo da PJ (edição).
        if self.instance and self.instance.pk:
            vinculo = self.instance.get_vinculo()
            if vinculo:
                self.fields['email'].initial = vinculo.email_pessoal

    def clean_cnpj(self):
        cnpj = self.cleaned_data.get('cnpj')
        if not cpfcnpj.validate(cnpj):
            self.add_error('cnpj', 'O CNPJ informado não é válido')
        return cnpj


class PessoaJuridicaContatoForm(forms.ModelFormPlus):
    descricao = forms.CharField(label='Descrição', required=False)
    telefone = forms.CharField(label='Telefone', required=False)
    email = forms.EmailField(label='E-mail', required=False)

    class Meta:
        model = PessoaJuridicaContato
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['via_form_suap'].widget = forms.HiddenInput()
        self.fields['via_form_suap'].initial = True


class ImportacaoPJForm(forms.FormPlus):
    pj = forms.FileFieldPlus(
        label='Pessoa Jurídica',
        required=False,
        help_text='Arquivo em formato CSV contendo as colunas Razão Social, CNPJ, Endereco, Bairro, Telefone, Cep ,Cidade UF',
    )

    def processar(self):
        command = importador_pj.Command()
        errors = command.handle(*[], pj=self.cleaned_data['pj'])
        return errors


############
# Servidor #
############


def get_choices_nome_usual(nome):
    nome_capitalizado = retirar_preposicoes_nome(nome)
    choices = [['', '---']]
    for token in nome_capitalizado.split():
        for token1 in nome_capitalizado.split():
            if token != token1:
                choice = to_ascii(f'{token} {token1}')
                choices.append([choice, choice])
    if len(choices) == 1:
        choice = to_ascii(nome_capitalizado)
        choices.append([choice, choice])
    return choices


class ServidorInformacoesPessoaisForm(forms.ModelFormPlus):
    nome_usual = forms.ChoiceField(label='Nome Usual', required=True, help_text='Nome que será exibido no SUAP')
    nascimento_municipio = forms.ModelChoiceFieldPlus(Municipio.objects.all(), required=False, label='Naturalidade')
    orcid = forms.URLField(label='ORCID', help_text='Endereço do ORCID, por exemplo, https://orcid.org/0000-0000-0000-0000', required=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        choices = get_choices_nome_usual(self.instance.pessoa_fisica.nome) if self.instance.id else []
        self.fields['nome_usual'].choices = choices
        if len(choices) < 3:
            self.fields['nome_usual'].required = False
        if 'nascimento_municipio' in self.fields and self.instance.id:
            self.fields['nascimento_municipio'].initial = self.instance.pessoa_fisica.nascimento_municipio
        if self.instance.id:
            self.fields['orcid'].initial = self.instance.pessoa_fisica.orcid
            self._preselecionar_nome_usual()

    def _preselecionar_nome_usual(self) -> None:
        """Deixa o nome usual gravado marcado no select ao abrir o formulário.

        ``nome_usual`` é um ``ChoiceField`` avulso (``Meta.fields`` é vazio), então o
        ``initial`` não vem da instância sozinho. O valor gravado também nem sempre é uma das
        combinações de ``get_choices_nome_usual``, que são ASCII: o ``save`` de
        ``PessoaFisica`` auto-gera ``primeiro + último nome`` preservando os acentos. Nesse
        caso o valor atual entra na lista, para renderizar selecionado e sobreviver ao
        re-envio.

        A lista é **reatribuída**, não mutada: o setter de ``choices`` normaliza o valor uma
        vez para o campo e outra para o widget, então as duas listas são objetos distintos e
        um ``append`` no campo não chegaria ao ``<select>``.
        """
        nome_usual = self.instance.pessoa_fisica.nome_usual
        if not nome_usual:
            return
        choices = list(self.fields['nome_usual'].choices)
        if (nome_usual, nome_usual) not in choices:
            self.fields['nome_usual'].choices = [*choices, (nome_usual, nome_usual)]
        self.fields['nome_usual'].initial = nome_usual

    fieldsets = (('Dados Pessoais', {'fields': ('nome_usual', 'nascimento_municipio', 'orcid')}),)

    class Meta:
        model = Servidor
        fields = []

    def save(self, commit: bool = True) -> Servidor:
        if self.instance.pessoa_fisica_id:
            self.instance.pessoa_fisica.nome_usual = self.cleaned_data['nome_usual']
            self.instance.pessoa_fisica.nascimento_municipio = self.cleaned_data['nascimento_municipio']
            self.instance.pessoa_fisica.orcid = self.cleaned_data['orcid']
            self.instance.pessoa_fisica.save()
        return super().save(commit)

    def clean_orcid(self) -> str:
        orcid = self.cleaned_data.get('orcid')
        if orcid and len(orcid) > 200:
            raise forms.ValidationError('Endereço do ORCID inválido. Informe a URL curta, por exemplo, https://orcid.org/0000-0000-0000-0000')
        return orcid


class PessoaFisicaInformacoesDigitaisFracasForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'senha_ponto' in self.fields:
            self.fields['senha_ponto'].widget = forms.PasswordInput(attrs={'autocomplete': 'off'})

    class Meta:
        model = PessoaFisica
        fields = ['tem_digital_fraca', 'senha_ponto']

    def clean_senha_ponto(self):
        # Usado para criptografar a senha
        if self.cleaned_data['senha_ponto']:
            from hashlib import md5

            m = md5()
            m.update(self.cleaned_data['senha_ponto'].encode())
            self.cleaned_data['senha_ponto'] = m.hexdigest()
        return self.cleaned_data['senha_ponto']


class PessoaFisicaAlterarSenhaPontoForm(forms.ModelFormPlus):
    senha = forms.PasswordField()
    confirmar = forms.BooleanField(label='Confirma a operação', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'senha_ponto' in self.fields:
            self.fields['senha_ponto'].widget = forms.PasswordInput(attrs={'autocomplete': 'off'})

    class Meta:
        model = PessoaFisica
        fields = ['senha_ponto']

    def clean_senha_ponto(self):
        # Usado para criptografar a senha
        if self.cleaned_data['senha_ponto']:
            from hashlib import md5

            m = md5()
            m.update(self.cleaned_data['senha_ponto'].encode())
            self.cleaned_data['senha_ponto'] = m.hexdigest()
        return self.cleaned_data['senha_ponto']


class ServidorForm(ServidorInformacoesPessoaisForm):
    nome_social = forms.CharField(label='Nome Social', max_length=200, required=False)
    nome_registro = forms.CharField(label='Nome de Registro', max_length=200, required=False)

    nome_pai = forms.CharField(label='Nome do Pai', max_length=100, required=False)
    grupo_sanguineo = forms.ChoiceField(
        label='Grupo sanguíneo', required=False, choices=[[None, '-------'], ['A', 'A'], ['B', 'B'], ['AB', 'AB'], ['O', 'O']]
    )
    foto = ImageFormFieldWithThumbs(required=False)
    fator_rh = forms.ChoiceField(label='Fator RH', required=False, choices=[[None, '-------'], ['+', '+'], ['-', '-']])
    tem_digital_fraca = forms.BooleanField(
        initial=False,
        required=False,
        label='Permitir registro de ponto sem impressão digital',
        help_text='Servidores com impressão digital fraca devem ter essa opção marcada',
    )
    senha_ponto = forms.CharField(
        max_length=128,
        required=False,
        label='Senha para registro de ponto sem impressão digital',
        help_text='Servidores com impressão digital fraca devem ter uma senha definida para bater o ponto',
        widget=forms.PasswordInput(attrs={'autocomplete': 'off'}),
    )
    setor = forms.ModelChoiceField(label='Setor SUAP', queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(), required=False)
    setor_exercicio = forms.ModelChoiceField(
        label='Setor de Exercício SIAPE', queryset=Setor.objects.siape().all(), widget=TreeWidget(), required=False
    )
    setores_adicionais = forms.MultipleModelChoiceFieldPlus(
        required=False,
        queryset=Setor.objects.suap_ativos().all(),
        help_text='Os setores adicionais estarão visíveis para o servidor no módulo de protocolo',
    )
    cpf = forms.CharField(label='CPF', widget=BRCpfWidget, required=False)
    data_base_progressao = forms.DateFieldPlus(label='Data Base Progressão', required=False)
    povo_indigena = forms.ModelChoiceField(
        label='Povo indígena',
        queryset=PovoIndigena.objects.all(),
        required=True,
        widget=AutocompleteWidget(search_fields=PovoIndigena.SEARCH_FIELDS),
        help_text='A informação sobre o povo indígena é obrigatória quando a raça for declarada como indígena.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pessoa_fisica_fields = [
            'nome_usual',
            'nome_registro',
            'nome_social',
            'nome_pai',
            'grupo_sanguineo',
            'foto',
            'fator_rh',
            'orcid',
            'tem_digital_fraca',
            'cpf',
            'senha_ponto',
            'povo_indigena',
        ]
        #
        if self.instance.id and (not self.instance.raca or not self.instance.raca.is_indigena()):
            self.fields['povo_indigena'].widget = forms.HiddenInput()
        self.fields['povo_indigena'].required = False
        #
        if self.instance and self.instance.id:
            self.fields['setores_adicionais'].initial = self.instance.setores_adicionais.all()
        #
        # Campos que migraram para Vinculo: lidos via property do papel, não via pessoa_fisica
        campos_via_vinculo = {'povo_indigena', 'raca', 'deficiencia', 'foto'}
        for field in pessoa_fisica_fields:
            if field in self.fields and self.instance.id:
                if field in campos_via_vinculo:
                    self.fields[field].initial = getattr(self.instance, field, None)
                else:
                    self.fields[field].initial = getattr(self.instance.pessoa_fisica, field)

        if 'cargo_emprego' in self.fields:
            qs_cargoemprego = CargoEmprego.utilizados
            if self.request.user.has_perm('rh.pode_editar_cargo_emprego_externo'):
                qs_cargoemprego = CargoEmprego.objects

            self.fields['cargo_emprego'] = forms.ModelChoiceField(
                label='Cargo Emprego',
                queryset=qs_cargoemprego,
                required=False,
                widget=AutocompleteWidget(search_fields=CargoEmprego.SEARCH_FIELDS),
            )

    def clean_setor(self):
        """
        Assegura que o setor SUAP seja do mesmo campus (equivalente) do setor de
        exercício SIAPE. Essa condição só vale quando as árvores de Setor SUAP e
        SIAPE são distintas.
        """
        if settings.TIPO_ARVORE_SETORES == 'SUAP':
            obj = self.instance
            # Tentando encontrar o setor_exercicio.uo.equivalente
            try:
                uo_equivalente = obj.setor_exercicio.uo.equivalente
            except AttributeError:
                uo_equivalente = None

            if obj.setor_exercicio and self.cleaned_data['setor'] and uo_equivalente != self.cleaned_data['setor'].uo and not obj.eh_estagiario:
                raise forms.ValidationError(f'O setor SUAP deve estar no mesmo campus do setor de exercício SIAPE: {uo_equivalente}')

        return self.cleaned_data['setor']

    def clean_nome(self):
        """
        Assegura que o nome SUAP seja do mesmo que veio do SIAPE
        """
        if to_ascii(self.instance.nome).lower() and to_ascii(self.instance.nome).lower() != to_ascii(self.cleaned_data['nome']).lower():
            raise forms.ValidationError('O nome do servidor deve ser igual ao nome que vem no SIAPE')
        return self.cleaned_data['nome']

    def clean_senha_ponto(self):
        # Usado para criptografar a senha
        if self.cleaned_data['senha_ponto']:
            from hashlib import md5

            m = md5()
            m.update(self.cleaned_data['senha_ponto'].encode())
            self.cleaned_data['senha_ponto'] = m.hexdigest()
        return self.cleaned_data['senha_ponto']

    def clean_povo_indigena(self):
        povo_indigena = self.cleaned_data.get('povo_indigena')
        # raca não é campo do form (não editável aqui); usa o valor do vínculo via property
        raca = self.cleaned_data.get('raca') or (self.instance.raca if self.instance.id else None)
        if raca and raca.is_indigena() and not povo_indigena:
            raise forms.ValidationError('É necessário informar o Povo indígena quando a Raça for Indígena')
        return povo_indigena

    def clean_ativo(self):
        from processo_eletronico.models import ProcessoStatus

        impedir_inativacao_servidor = Configuracao.get_valor_por_chave('processo_eletronico', 'impedir_inativacao_servidor')
        ativo = self.cleaned_data.get('ativo')
        if impedir_inativacao_servidor and not ativo:
            for pk, ultimo_tramite in (
                self.instance.get_vinculo()
                .tramites_destinatario_vinculo.all()
                .exclude(processo__status=ProcessoStatus.STATUS_FINALIZADO)
                .values_list('pk', 'processo__ultimo_tramite')
            ):
                if pk == ultimo_tramite:
                    raise ValidationError(
                        'Existem processos privados destinados para esse servidor ou em posse dele. Por favor, solicite sua tramitação antes de inativá-lo.'
                    )
        return ativo


class ServidorSetorHistoricoForm(forms.ModelFormPlus):
    class Meta:
        model = ServidorSetorHistorico
        fields = ('servidor', 'setor', 'data_inicio_no_setor', 'data_fim_no_setor')

    servidor = forms.ModelChoiceField(
        label='Servidor', queryset=Servidor.objects.all(), required=True, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
    )
    setor = forms.ModelChoiceField(label='Setor SUAP', queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(), required=True)
    fieldsets = [('', {'fields': ['servidor', 'setor', 'data_inicio_no_setor', 'data_fim_no_setor']})]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['servidor'].widget.readonly = True

    def clean(self):
        super().clean()
        if not self.errors:
            if not self.instance.pk:
                servidor = self.cleaned_data['servidor']
                data_inicio_no_setor = self.cleaned_data['data_inicio_no_setor']
                setor = self.cleaned_data['setor']
                historico = ServidorSetorHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_no_setor')
                if historico:
                    historico_atual = historico[0]
                    if setor != historico_atual.setor:
                        if data_inicio_no_setor > historico_atual.data_inicio_no_setor:
                            #
                            # atualizando a data fim do então período mais atual
                            dia_subtr = timedelta(days=1)
                            ServidorSetorHistorico.objects.filter(pk=historico_atual.pk).update(data_fim_no_setor=(data_inicio_no_setor - dia_subtr))

                            # raise forms.ValidationError(
                            #     u'Não é possível criar Histórico para periodos a frente do mais atual')
            else:
                servidor = self.cleaned_data['servidor']
                servidor_historico_atual = ServidorSetorHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_no_setor')[0]
                if servidor_historico_atual.pk == self.instance.pk:
                    if self.cleaned_data['data_fim_no_setor']:
                        raise forms.ValidationError('Não é possível fechar o este periodo. Ele é o mais atual')
        return self.cleaned_data


def GetServidorFuncaoHistoricoForm(request):
    funcionario = request.user.get_relacionamento()
    setor_funcionario = funcionario.setor
    setor_exercicio_funcionario = funcionario.setor_exercicio
    qs_suap = Setor.objects.suap().none()
    qs_siape = Setor.objects.siape().none()
    if request.user.has_perm('rh.eh_rh_sistemico'):
        qs_suap = Setor.objects.suap().filter(excluido=False)
        qs_siape = Setor.objects.siape().filter(excluido=False)

    elif request.user.has_perm('rh.eh_rh_campus') or request.user.has_perm('rh.gabinete'):
        qs_suap = Setor.objects.suap().filter(excluido=False, uo=setor_funcionario.uo)
        if setor_exercicio_funcionario:
            qs_siape = Setor.objects.siape().filter(excluido=False, uo=setor_exercicio_funcionario.uo)
        else:
            qs_siape = Setor.objects.siape().filter(excluido=False, uo__equivalente=setor_funcionario.uo)

    class ServidorFuncaoHistoricoForm(forms.ModelFormPlus):
        servidor = forms.ModelChoiceField(label='Servidor', queryset=Servidor.objects.all(), required=True, widget=AutocompleteWidget())
        data_inicio_funcao = forms.DateFieldPlus(label='Data Início na Função', required=True)
        data_fim_funcao = forms.DateFieldPlus(
            label='Data Fim na Função', required=False, help_text='Deixar em branco caso essa seja a função atual do servidor.'
        )
        funcao = forms.ModelChoiceField(label='Função', queryset=Funcao.objects.filter(funcao_suap=True), required=True)
        atividade = forms.ModelChoiceField(label='Atividade', queryset=Atividade.usadas, required=False)
        setor = forms.ModelChoiceField(label='Setor SIAPE', queryset=qs_siape, widget=AutocompleteWidget(), required=True)
        setor_suap = forms.ModelChoiceField(label='Setor SUAP', queryset=qs_suap, widget=AutocompleteWidget(), required=True)
        nome_amigavel = forms.CharFieldPlus(label='Nome Amigável da Função', required=False)
        nivel = forms.CharFieldPlus(max_length=4, required=False, label='Nível')
        atualiza_pelo_extrator = forms.BooleanField(
            label='Atualiza pelo extrator?', required=False, help_text='Informar se esse registro será afetado pelo extrator siape.'
        )

        class Meta:
            model = ServidorFuncaoHistorico
            fields = (
                'servidor',
                'data_inicio_funcao',
                'data_fim_funcao',
                'funcao',
                'nivel',
                'atividade',
                'setor',
                'setor_suap',
                'nome_amigavel',
                'atualiza_pelo_extrator',
            )

    return ServidorFuncaoHistoricoForm


def GetServidorFuncaoSiapeHistoricoForm(request):
    request.user.get_relacionamento()
    if request.user.has_perm('rh.eh_rh_sistemico'):
        Setor.raiz_suap()
    elif request.user.has_perm('rh.eh_rh_campus') or request.user.has_perm('rh.gabinete'):
        pass

    class ServidorFuncaoSiapeHistoricoForm(forms.ModelFormPlus):
        servidor = forms.ModelChoiceField(label='Servidor', queryset=Servidor.objects, required=True, widget=AutocompleteWidget(readonly=True))
        funcao = forms.ModelChoiceField(label='Função', queryset=Funcao.objects, required=True, widget=AutocompleteWidget(readonly=True))
        atividade = forms.ModelChoiceField(label='Atividade', queryset=Atividade.usadas, required=True, widget=AutocompleteWidget())
        setor_suap = forms.ModelChoiceField(
            label='Setor SUAP', queryset=Setor.objects.suap().filter(excluido=False), widget=AutocompleteWidget(), required=True
        )
        nome_amigavel = forms.CharFieldPlus(label='Nome Amigável da Função', required=False)
        data_fim_funcao = forms.DateFieldPlus(
            label='Data Fim na Função', required=False, help_text='Deixar em branco caso essa seja a função atual do servidor.'
        )
        atualiza_pelo_extrator = forms.BooleanField(
            label='Atualiza pelo extrator?', required=False, help_text='Informar se esse registro será afetado pelo extrator siape.'
        )

        class Meta:
            model = ServidorFuncaoHistorico
            fields = ('servidor', 'funcao', 'atividade', 'setor_suap', 'data_fim_funcao', 'nome_amigavel', 'atualiza_pelo_extrator')

    return ServidorFuncaoSiapeHistoricoForm


class AvaliadorExternoForm(forms.ModelFormPlus):
    matricula_siape = forms.CharFieldPlus(width=300, label='Matrícula SIAPE')
    nome = forms.CharFieldPlus(width=300, label='Nome')
    sexo = forms.ChoiceField(choices=[['M', 'Masculino'], ['F', 'Feminino']], required=False)
    nascimento_data = forms.DateFieldPlus(label='Data de nascimento', required=False, help_text='Formato: dd/mm/aaaa')
    cpf = forms.BrCpfField(label='CPF')
    email = forms.EmailField(max_length=255, label='E-mail para contato')
    numero_telefone = forms.BrTelefoneField(max_length=45, label='Telefone para contato')
    instituicao_origem = forms.ModelChoiceField(Instituicao.objects, label='Instituição de origem', required=False)

    numero_documento_identificacao = forms.CharFieldPlus(
        label='Número do documento de identificação',
        max_length=50,
        required=False,
        help_text='Ex: RG, CNH, Passaporte, etc.',
        widget=forms.TextInput(attrs={'placeholder': 'Ex: RG, CNH, Passaporte, etc.'}),
    )
    emissor_documento_identificacao = forms.CharFieldPlus(
        label='Emissor do documento de identificação',
        max_length=50,
        required=False,
        help_text='Ex: SSP, DETRAN, Polícia Federal, etc.',
        widget=forms.TextInput(attrs={'placeholder': 'Ex: SSP, DETRAN, Polícia Federal, etc.'}),
    )
    pis_pasep = forms.CharFieldPlus(
        label='PIS/PASEP',
        max_length=50,
        required=False,
        help_text='Número do PIS/PASEP do avaliador, se houver.',
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 12345678901'}),
    )

    # dados bancários
    banco = forms.ModelChoiceFieldPlus(Banco.objects, label='Banco', required=False, help_text='Selecione o banco onde o avaliador possui conta')
    numero_agencia = forms.CharFieldPlus(
        label='Número da Agência',
        max_length=50,
        required=False,
        help_text='Ex: 1234-5',
    )
    tipo_conta = forms.CharFieldPlus(
        label='Tipo de conta',
        required=False,
        help_text='Informe o tipo de conta do avaliador. Ex: Conta Corrente, Poupança, etc.',
        widget=forms.Select(
            choices=Avaliador.TIPOCONTA_CHOICES,
        ),
    )
    numero_conta = forms.CharFieldPlus(
        label='Número da conta',
        max_length=50,
        help_text='Ex: 123456-7',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 123456-7'}),
    )
    operacao = forms.CharFieldPlus(
        label='Operação',
        max_length=50,
        required=False,
        help_text='Ex: 001, 002, etc. (deixe em branco se não houver operação)',
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 001, 002, etc.'}),
    )
    nivel_atual = forms.ChoiceField(
        label='Nível atual',
        choices=Avaliador.NOVOS_NIVEIS,
        required=False,
        help_text='Selecione o nível atual do avaliador, se houver.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Apenas rh sistêmico pode ver todos os campos
            if not self.request.user.has_perm('rh.eh_rh_sistemico'):
                self.fields['cpf'] = ReadOnlyField(label='CPF')
                self.fields['email'] = ReadOnlyField(label='E-mail para contato')
            #
            self.fields['matricula_siape'].initial = self.instance.matricula_siape
            self.fields['nome'].initial = self.instance.vinculo.pessoa.pessoafisica.nome
            self.fields['cpf'].initial = self.instance.vinculo.pessoa.pessoafisica.cpf
            self.fields['email'].initial = self.instance.vinculo.email_pessoal
            self.fields['instituicao_origem'].initial = self.instance.instituicao_origem
            self.fields['nivel_atual'].initial = self.instance.nivel_atual
            self.fields['nivel_atual'].choices = [('', '--Selecione--'), *list(Avaliador.NOVOS_NIVEIS.items())]
            telefones = self.instance.vinculo.pessoa.pessoafisica.pessoatelefone_set.filter(observacao=Avaliador.TELEFONE_CELULAR)
            if telefones.exists():
                telefone = telefones[0]
                self.fields['numero_telefone'].initial = telefone.numero

    class Meta:
        model = Avaliador
        exclude = ()

    def clean_cpf(self):
        if not self.instance.id:
            prestador = PrestadorServico.objects.filter(pessoa_fisica__cpf=self.cleaned_data['cpf'])
            if prestador.exists() and Avaliador.objects.filter(vinculo__pessoa=prestador[0].pessoa_fisica.pessoa_ptr).exists():
                raise forms.ValidationError('Já existe um avaliador externo cadastrado com este CPF.')

        return self.cleaned_data['cpf']

    def clean(self) -> dict:
        # antes do super(): o clean() do ModelFormPlus levanta erro se já houver erro de campo.
        # Só na criação: na edição é o próprio avaliador corrigindo seus dados (o nascimento novo é auditado no save).
        if not self.instance.pk:
            recusar_cadastro_de_prestador(self)
        return super().clean()

    def clean_email(self):
        Configuracao = apps.get_model('comum', 'configuracao')
        if not Configuracao.get_valor_por_chave('rh', 'permite_email_institucional_email_secundario') and Configuracao.eh_email_institucional(
            self.cleaned_data['email']
        ):
            raise forms.ValidationError('Escolha um e-mail que não seja institucional.')

        return self.cleaned_data['email']

    @transaction.atomic
    def save(self, commit=True):
        matricula_siape = self.cleaned_data.get('matricula_siape')
        email = self.cleaned_data.get('email')
        instituicao_origem = self.cleaned_data.get('instituicao_origem')

        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': self.cleaned_data['cpf'] or '',
            'nome_registro': self.cleaned_data['nome'],
            'email_secundario': self.cleaned_data['email'],
            'email': self.cleaned_data['email'],
            'nascimento_data': self.cleaned_data.get('nascimento_data') or None,
            'sexo': self.cleaned_data['sexo'],
        }
        telefone: PessoaTelefoneCadastro = {
            'numero': self.cleaned_data['numero_telefone'],
        }
        dados: PrestadorServicoCadastro = {'pessoa_fisica': pessoa_fisica, 'setor': get_setor_cppd(), 'ativo': True, 'telefone': telefone}
        retorno = PrestadorServico.update_or_create(dados)
        prestador = retorno['prestador']
        prestador_created = retorno['prestador_created']

        avaliador = super().save(False)
        avaliador.matricula_siape = matricula_siape
        avaliador.vinculo = prestador.vinculos.first()
        avaliador.email_contato = email
        avaliador.instituicao_origem = instituicao_origem
        avaliador.save()

        if prestador_created:
            self.enviar_email(prestador.matricula, email)

        return avaliador

    def enviar_email(self, username, email):
        obj = TrocarSenha.objects.create(username=username)
        url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
        conteudo = f"""
            <h1>Cadastro de Avaliador Externo</h1>
            <p>Prezado usuário,</p>
            <br />
            <p>Você acaba de ser cadastrado no banco de dados de avaliadores externos do IFRN e poderá ser selecionado
            para eventuais processos de RSC ou Professor titular, para definição de senha referente às suas credenciais
            da rede, por favor, acesse o endereço: {url}.</p>
            """
        return send_mail('[SUAP] Cadastro de Avaliador Externo', conteudo, settings.DEFAULT_FROM_EMAIL, [email])


class AtualizarDadosAvaliadorForm(forms.FormPlus):
    nome = forms.CharFieldPlus(max_length=200)
    sexo = forms.ChoiceField(choices=[['M', 'Masculino'], ['F', 'Feminino']], required=False)
    nascimento_data = forms.DateFieldPlus(label='Data de Nascimento')
    email = forms.EmailField(max_length=255, label='E-mail para Contato')

    matricula_siape = forms.CharFieldPlus(label='Matrícula SIAPE', max_length=50)
    instituicao_origem = forms.ModelChoiceFieldPlus(Instituicao.objects)

    numero_documento_identificacao = forms.CharField(label='Número do Documento de Identificação', max_length=50, help_text='Somente números')
    emissor_documento_identificacao = forms.CharField(label='Emissor do Documento de Identificação', max_length=50)
    pis_pasep = forms.CharFieldPlus(label='PIS/PASEP', max_length=50)

    telefone_celular = forms.BrTelefoneField(max_length=45, label='Telefone Celular')
    telefone_residencial = forms.BrTelefoneField(max_length=45, required=False, label='Telefone Residencial')
    telefone_comercial = forms.BrTelefoneField(max_length=45, required=False, label='Telefone Comercial')

    municipio = forms.CharFieldPlus(max_length=255, label='Município', required=False)
    logradouro = forms.CharFieldPlus(max_length=255, label='Logradouro', required=False)
    numero = forms.CharFieldPlus(max_length=255, label='Número', width=100, required=False)
    bairro = forms.CharFieldPlus(max_length=255, label='Bairro', required=False)
    complemento = forms.CharFieldPlus(max_length=255, label='Complemento', required=False)
    cep = forms.BrCepField(max_length=255, label='CEP', required=False)

    banco = forms.ModelChoiceFieldPlus(Banco.objects)
    numero_agencia = forms.CharField(label='Número da Agência', max_length=50, help_text='Ex: 3293-X')
    tipo_conta = forms.ChoiceField(label='Tipo da Conta', choices=Avaliador.TIPOCONTA_CHOICES)
    numero_conta = forms.CharField(label='Número da Conta', max_length=50, help_text='Ex: 23384-6')
    operacao = forms.CharField(label='Operação', max_length=50, required=False)

    fieldsets = (
        (
            'Dados Pessoais',
            {
                'fields': (
                    'nome',
                    'sexo',
                    'nascimento_data',
                    'email',
                    'matricula_siape',
                    'instituicao_origem',
                ),
            },
        ),
        (
            'Documentos',
            {
                'fields': (
                    'numero_documento_identificacao',
                    'emissor_documento_identificacao',
                    'pis_pasep',
                ),
            },
        ),
        (
            'Telefones',
            {
                'fields': (
                    'telefone_celular',
                    'telefone_residencial',
                    'telefone_comercial',
                ),
            },
        ),
        (
            'Endereço',
            {
                'fields': (
                    'municipio',
                    'logradouro',
                    'numero',
                    'bairro',
                    'complemento',
                    'cep',
                ),
            },
        ),
        (
            'Dados Bancários',
            {
                'fields': (
                    'banco',
                    'numero_agencia',
                    'tipo_conta',
                    'numero_conta',
                    'operacao',
                ),
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pessoa_fisica = self.request.user.get_profile()
        avaliador = Avaliador.objects.get(vinculo__pessoa=pessoa_fisica.pessoa_ptr)

        self.fields['nome'].initial = pessoa_fisica.nome
        self.fields['nascimento_data'].initial = pessoa_fisica.nascimento_data
        self.fields['email'].initial = avaliador.email_contato
        self.fields['sexo'].initial = pessoa_fisica.sexo

        self.fields['matricula_siape'].initial = avaliador.matricula_siape
        self.fields['instituicao_origem'].initial = avaliador.instituicao_origem

        self.fields['numero_documento_identificacao'].initial = avaliador.numero_documento_identificacao
        self.fields['emissor_documento_identificacao'].initial = avaliador.emissor_documento_identificacao
        self.fields['pis_pasep'].initial = avaliador.pis_pasep

        telefones = pessoa_fisica.pessoatelefone_set
        if telefones.exists():
            telefone_celular = telefones.filter(observacao=Avaliador.TELEFONE_CELULAR)
            if telefone_celular.exists():
                self.fields['telefone_celular'].initial = telefone_celular[0].numero

            telefone_residencial = telefones.filter(observacao=Avaliador.TELEFONE_RESIDENCIAL)
            if telefone_residencial.exists():
                self.fields['telefone_residencial'].initial = telefone_residencial[0].numero

            telefone_comercial = telefones.filter(observacao=Avaliador.TELEFONE_COMERCIAL)
            if telefone_comercial.exists():
                self.fields['telefone_comercial'].initial = telefone_comercial[0].numero

        self.fields['municipio'].initial = avaliador.endereco_municipio
        self.fields['logradouro'].initial = avaliador.endereco_logradouro
        self.fields['numero'].initial = avaliador.endereco_numero
        self.fields['bairro'].initial = avaliador.endereco_bairro
        self.fields['complemento'].initial = avaliador.endereco_complemento
        self.fields['cep'].initial = avaliador.endereco_cep

        self.fields['banco'].queryset = Banco.objects.filter(excluido=False)
        self.fields['banco'].initial = avaliador.banco

        self.fields['numero_agencia'].initial = avaliador.numero_agencia
        self.fields['tipo_conta'].initial = avaliador.tipo_conta
        self.fields['numero_conta'].initial = avaliador.numero_conta
        self.fields['operacao'].initial = avaliador.operacao

    @transaction.atomic
    def save(self, commit=True):
        pessoa_fisica = self.request.user.get_profile()
        avaliador = Avaliador.objects.get(vinculo__pessoa=pessoa_fisica.pessoa_ptr)
        pessoa_fisica.nome = self.cleaned_data['nome']
        pessoa_fisica.nascimento_data = self.cleaned_data['nascimento_data']
        avaliador.email_contato = self.cleaned_data['email']
        pessoa_fisica.sexo = self.cleaned_data['sexo']

        avaliador.matricula_siape = self.cleaned_data['matricula_siape']
        avaliador.instituicao_origem = self.cleaned_data['instituicao_origem']

        avaliador.numero_documento_identificacao = self.cleaned_data['numero_documento_identificacao']
        avaliador.emissor_documento_identificacao = self.cleaned_data['emissor_documento_identificacao']
        avaliador.pis_pasep = self.cleaned_data['pis_pasep']

        telefones = pessoa_fisica.pessoatelefone_set
        telefone_celular = telefones.filter(observacao=Avaliador.TELEFONE_CELULAR)
        if telefone_celular.exists():
            telefone_celular[0].numero = self.cleaned_data['telefone_celular']
            telefone_celular[0].observacao = Avaliador.TELEFONE_CELULAR
            telefone_celular[0].save()
        else:
            pessoa_fisica.pessoatelefone_set.create(numero=self.cleaned_data['telefone_celular'], observacao=Avaliador.TELEFONE_CELULAR)

        telefone_residencial = telefones.filter(observacao=Avaliador.TELEFONE_RESIDENCIAL)
        if telefone_residencial.exists():
            telefone_residencial[0].numero = self.cleaned_data['telefone_residencial']
            telefone_celular[0].observacao = Avaliador.TELEFONE_RESIDENCIAL
            telefone_residencial[0].save()
        else:
            pessoa_fisica.pessoatelefone_set.create(numero=self.cleaned_data['telefone_residencial'], observacao=Avaliador.TELEFONE_RESIDENCIAL)

        telefone_comercial = telefones.filter(observacao=Avaliador.TELEFONE_COMERCIAL)
        if telefone_comercial.exists():
            telefone_comercial[0].numero = self.cleaned_data['telefone_comercial']
            telefone_celular[0].observacao = Avaliador.TELEFONE_COMERCIAL
            telefone_comercial[0].save()
        else:
            pessoa_fisica.pessoatelefone_set.create(numero=self.cleaned_data['telefone_comercial'], observacao=Avaliador.TELEFONE_COMERCIAL)

        avaliador.endereco_municipio = self.cleaned_data['municipio']
        avaliador.endereco_logradouro = self.cleaned_data['logradouro']
        avaliador.endereco_numero = self.cleaned_data['numero']
        avaliador.endereco_bairro = self.cleaned_data['bairro']
        avaliador.endereco_complemento = self.cleaned_data['complemento']
        avaliador.endereco_cep = self.cleaned_data['cep']

        avaliador.banco = self.cleaned_data['banco']
        avaliador.numero_agencia = self.cleaned_data['numero_agencia']
        avaliador.tipo_conta = self.cleaned_data['tipo_conta']
        avaliador.numero_conta = self.cleaned_data['numero_conta']
        avaliador.operacao = self.cleaned_data['operacao']

        pessoa_fisica.save()
        avaliador.save()
        sync_ldap_user(self.request.user.username)


class AfastamentosServidoresForm(forms.FormPlus):
    TIPO_AFASTAMENTO_CHOICES = [['Todos', 'Todos']]
    TIPO_AFASTAMENTO_CHOICES += list(map(list, AfastamentoSiape.TIPO_AFASTAMENTO_CHOICES))

    CATEGORIA_CHOICES = [
        ['Todos', 'Todos os Servidores'],
        ['docente', 'Apenas Docentes'],
        ['tecnico_administrativo', 'Apenas Administrativos'],
    ]
    CANCELADO_CHOICES = [['Todos', 'Todos'], [False, 'Ativos'], [True, 'Cancelados']]

    tipo_afastamento = forms.ChoiceField(choices=TIPO_AFASTAMENTO_CHOICES)
    afastamento = forms.ModelChoiceFieldPlus(
        queryset=AfastamentoSiape.objects,
        label='Afastamento',
        required=False,
        help_text='Caso você não escolha nenhum afastamento específico, a consulta irá considerar todos os tipos de afastamento.',
    )
    uo = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(),
        label='Campi',
        required=False,
        help_text='Caso você não escolha nenhum campus, a consulta irá considerar todos os campi.',
    )
    categoria = forms.ChoiceField(label='Categoria', choices=CATEGORIA_CHOICES, required=False)
    situacao = forms.ChoiceField(label='Situação de Afastamento', initial=False, choices=CANCELADO_CHOICES, required=False)

    data_inicio = forms.DateFieldPlus(label='Data de Início')
    data_termino = forms.DateFieldPlus(label='Data de Término')

    def clean(self):
        super().clean()
        if not self.errors:
            #
            # periodo adicionado/editado
            #
            periodo_data_inicio = self.cleaned_data['data_inicio']
            periodo_data_termino = self.cleaned_data['data_termino']

            #
            # valida o período
            #
            if periodo_data_termino and periodo_data_inicio > periodo_data_termino:
                self._errors['data_inicio'] = self.error_class(['A data de início deve ser menor ou igual à data término.'])
                del self.cleaned_data['data_termino']

        return self.cleaned_data


class ViagensPorCampusForm(forms.FormPlus):
    ano = forms.ModelChoiceField(Ano.objects.all(), label='Ano', required=True)
    mes = forms.ChoiceField(label='Mês', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mes'].choices = [[0, 'Todos'], *Meses.get_choices()]


class ImportarArquivoSCDPForm(forms.FormPlus):
    CHOICES = ((0, 'Viagens'), (1, 'Bilhetes'))
    tipo = forms.ChoiceField(choices=CHOICES, label='Tipo de Arquivo', required=True)
    arquivo = forms.FileFieldPlus(required=True, label='Arquivo', allow_empty_file=False)

    def clean(self):
        if len(self.files) != 1:
            # evitar o não envio de arquivo
            raise ValidationError('Nenhum arquivo selecionado.')
        if self.files['arquivo'].size == 0:
            # evitar o envio de arquivos vazios
            raise ValidationError('O arquivo enviado está vazio.')
        return self.cleaned_data['arquivo']


class DefinirAreasVinculacaoWizard(FormWizardPlus):
    arvore_setores = forms.ModelChoiceField(
        label='Árvore de Setores', queryset=Setor.objects, widget=TreeWidget(attrs={'readonly': 'readonly'}), required=False
    )
    palavra_chave = forms.CharFieldPlus(width=255, label='Palavra-chave')
    setores = forms.ModelMultipleChoiceField(queryset=Setor.objects, widget=forms.CheckboxSelectMultiplePlus())
    areas_vinculacao = forms.ModelMultipleChoiceField(
        queryset=AreaVinculacao.objects, widget=forms.CheckboxSelectMultiplePlus(), label='Áreas de Vinculação'
    )
    recursivamente = forms.BooleanField(label='Definir Recursivamente', required=False)

    steps = (
        [('Filtro', {'fields': ('arvore_setores', 'palavra_chave')})],
        [('Seleção dos Setores', {'fields': ('setores', 'areas_vinculacao', 'recursivamente')})],
    )

    def next_step(self):
        palavra_chave = self.get_entered_data('palavra_chave')
        if 'setores' in self.fields:
            if palavra_chave:
                self.fields['setores'].queryset = Setor.objects.suap_ativos().filter(sigla__icontains=palavra_chave)

    def processar(self):
        for setor in self.cleaned_data['setores']:
            for area_vinculacao in self.cleaned_data['areas_vinculacao']:
                setor.areas_vinculacao.add(area_vinculacao)
            if self.cleaned_data['recursivamente']:
                setor.salvar_areas_vinculacao_recursivamente(self.cleaned_data['areas_vinculacao'])
            setor.save()


class AreaVinculacaoForm(forms.ModelFormPlus):
    ordem = forms.ChoiceField(choices=[])

    class Meta:
        model = AreaVinculacao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        ordem_choices = []
        qtd = AreaVinculacao.objects.count()

        for ordem in range(1, qtd + 2):
            ordem_choices.append([ordem, ordem])

        self.fields['ordem'].choices = ordem_choices

    def save(self, *args: object, **kwargs: object) -> AreaVinculacao:
        # Reordena por enumeração: as demais áreas, sem a instância, ganham 1..N pulando a posição escolhida.
        # Não depende de ``count()``, que muda conforme a instância é nova (add) ou já existente (edição).
        outras = list(AreaVinculacao.objects.exclude(pk=self.instance.pk).order_by('ordem', 'pk'))
        posicao = max(1, min(self.instance.ordem, len(outras) + 1))
        self.instance.ordem = posicao
        outras.insert(posicao - 1, self.instance)

        for ordem, area in enumerate(outras, start=1):
            if area is not self.instance and area.ordem != ordem:
                area.ordem = ordem
                area.save()

        return super().save(*args, **kwargs)


class ServidoresParaCapacitacaoPorSetorForm(forms.FormPlus):
    setor = forms.ModelChoiceField(
        label='Setor SUAP',
        queryset=Setor.objects.suap_ativos().all(),
        widget=AutocompleteWidget(),
        required=True,
        help_text='Selecione um setor SUAP',
    )

    setores_filhos = forms.BooleanField(required=False, label='Incluir setores filhos')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario_logado = self.request.user
        servidor = usuario_logado.get_relacionamento()
        raiz = None
        if usuario_logado.is_superuser:
            raiz = Setor.raiz_suap()
        elif servidor.setor:
            raiz = servidor.setor

        self.fields['setor'].widget.root_nodes = [raiz]


class InstituicaoForm(forms.ModelFormPlus):
    unidade_gestora = forms.IntegerField(label='Unidade Gestora', required=False)
    uasg = forms.IntegerField(label='UASG', required=False)

    class Meta:
        model = Instituicao
        fields = ('nome', 'unidade_gestora', 'uasg', 'ativo')


###############
# CH Reduzida #
###############


class ProcessoCargaHorariaReduzidaRHForm(forms.ModelFormPlus):
    # Form do RH para cadastrar CH reduzida
    PROCESSO_ELETRONICO = 'eletronico'
    PROCESSO_FISICO = 'fisico'
    TIPO_PROTOCOLO_CHOICE = ((PROCESSO_ELETRONICO, 'Protocolo eletrônico'), (PROCESSO_FISICO, 'Protocolo físico'))

    servidor = forms.ModelChoiceFieldPlus(queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS), required=True)

    if 'processo_eletronico' in settings.INSTALLED_APPS:
        from processo_eletronico.models import Processo as ProcessoEletronico

        protocolo_eletronico = forms.ModelChoiceFieldPlus(
            queryset=ProcessoEletronico.objects,
            widget=AutocompleteWidget(search_fields=ProcessoEletronico.SEARCH_FIELDS),
            required=False,
            label='Protocolo eletrônico',
        )

    if 'protocolo' in settings.INSTALLED_APPS:
        from protocolo.models import Processo as ProcessoFisico

        protocolo_fisico = forms.ModelChoiceFieldPlus(
            queryset=ProcessoFisico.objects,
            widget=AutocompleteWidget(search_fields=ProcessoFisico.SEARCH_FIELDS),
            required=False,
            label='Protocolo físico',
        )

    tipo_protocolo = forms.ChoiceField(widget=forms.RadioSelect(), choices=TIPO_PROTOCOLO_CHOICE, label='Tipo de protocolo:')

    class Meta:
        model = CargaHorariaReduzida
        fields = ('servidor', 'data_inicio', 'data_termino', 'tipo')
        if 'protocolo' in settings.INSTALLED_APPS:
            fields += ('protocolo_fisico',)
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            fields += ('protocolo_eletronico',)
        if 'protocolo' in settings.INSTALLED_APPS or 'processo_eletronico' in settings.INSTALLED_APPS:
            fields += ('tipo_protocolo',)

    class Media:
        js = ('/static/rh/js/TipoProcoloCHReduzida.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario_logado_eh_rh_sistemico = in_group(self.request.user, 'Coordenador de Gestão de Pessoas Sistêmico')
        servidor_logado = self.request.user.get_relacionamento()
        uo_id = servidor_logado.setor.uo_id
        if not (usuario_logado_eh_rh_sistemico or self.request.user.is_superuser):
            self.fields['servidor'].queryset = Servidor.objects.ativos().filter(setor__uo_id=uo_id)

        if self.instance:
            if 'protocolo_fisico' in self.fields:
                from protocolo.models import Processo as ProcessoFisico

                if isinstance(self.instance.protocolo_content_object, ProcessoFisico):
                    self.fields['tipo_protocolo'].initial = self.PROCESSO_FISICO
                    self.fields['protocolo_fisico'].initial = self.instance.protocolo_content_id

            if 'protocolo_eletronico' in self.fields:
                from processo_eletronico.models import Processo as ProcessoEletronico

                if isinstance(self.instance.protocolo_content_object, ProcessoEletronico):
                    self.fields['tipo_protocolo'].initial = self.PROCESSO_ELETRONICO
                    self.fields['protocolo_eletronico'].initial = self.instance.protocolo_content_id

    def clean(self):
        clean = super().clean()
        if clean.get('data_inicio') and clean.get('data_termino'):
            if clean.get('tipo') == CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL:
                if clean.get('data_inicio') >= clean.get('data_termino'):
                    self.add_error('data_inicio', 'Data início deve ser menor que data término')
                elif clean.get('data_termino') < clean.get('data_inicio') + timedelta(days=30):
                    self.add_error(
                        'data_termino',
                        'A data mínima do término do afastamento, deve ser {}'.format(
                            (clean.get('data_inicio') + timedelta(days=31)).strftime('%d/%m/%Y')
                        ),
                    )
        if clean.get('servidor'):
            servidor_solicitante = clean.get('servidor')
            if not servidor_solicitante.setor:
                self.add_error('servidor', 'Servidor não tem setor.')

        if self.is_tipo_protocolo_eletronico() and not self.cleaned_data.get('protocolo_eletronico'):
            self.add_error('protocolo_eletronico', 'É obrigatório informar um protocolo. ')

        if self.is_tipo_protocolo_fisico() and not self.cleaned_data.get('protocolo_fisico'):
            self.add_error('protocolo_fisico', 'É obrigatório informar um protocolo. ')
        return clean

    def save(self, commit=True):
        if not self.instance.id:
            if self.instance.tipo == CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL:
                self.instance.status = CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH
            else:
                self.instance.status = CargaHorariaReduzida.STATUS_AGUARDANDO_CADASTRAR_HORARIO

            self.instance.ano = datetime.date.today().year

        if self.is_tipo_protocolo_eletronico() and self.cleaned_data['protocolo_eletronico']:
            self.instance.protocolo_content_object = self.cleaned_data['protocolo_eletronico']
        elif self.is_tipo_protocolo_fisico() and self.cleaned_data['protocolo_fisico']:
            self.instance.protocolo_content_object = self.cleaned_data['protocolo_fisico']
        return super().save(commit)

    def is_tipo_protocolo_eletronico(self):
        return self.cleaned_data.get('tipo_protocolo') == 'eletronico'

    def is_tipo_protocolo_fisico(self):
        return self.cleaned_data.get('tipo_protocolo') == 'fisico'


class DocumentacaoExigidaUploadForm(forms.FormPlus):
    arquivo = forms.AjaxFileUploadField('/rh/afastamento_pacial_upload/', 'onCompleteUpload')
    SUBMIT_LABEL = 'Salvar'

    def __init__(self, *args, **kwargs):
        processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].widget.request = self.request
        self.fields['arquivo'].widget.params['processo'] = processo.id


class SalvarProcessoAfastamentoForm(forms.FormPlus):
    data_inicial = forms.DateFieldPlus()
    data_final = forms.DateFieldPlus()
    nova_jornada = forms.ChoiceField(label='Jornada pretendida', choices=())
    processo = None

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        # self.processo = self.instance
        super().__init__(*args, **kwargs)

        self.fields['nova_jornada'].choices = self.processo.get_carga_horaria_disponivel_choice()

        # inicializando os campos
        self.fields['data_inicial'].initial = self.processo.data_inicio
        self.fields['data_final'].initial = self.processo.data_termino

        if self.processo.nova_jornada:
            self.fields['nova_jornada'].initial = self.processo.nova_jornada.split('HORAS SEMANAIS')[0].strip()

        if (
            self.processo.status == CargaHorariaReduzida.STATUS_NOVOS_DOCUMENTOS_SOLICITADOS
            or self.processo.status == CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_CHEFE
        ):
            self.fields['data_inicial'].widget.attrs['disabled'] = True
            self.fields['data_inicial'].widget.attrs['readonly'] = True

            self.fields['data_final'].widget.attrs['disabled'] = True
            self.fields['data_final'].widget.attrs['readonly'] = True

            self.fields['nova_jornada'].widget.attrs['disabled'] = True
            self.fields['nova_jornada'].widget.attrs['readonly'] = True

    def clean(self):
        clean = super().clean()
        if not self.processo.documentos.all().exists():
            raise Exception('Adicone pelo menos um arquivo.')
        if clean.get('data_inicial') and clean.get('data_final'):
            if clean.get('data_inicial') >= clean.get('data_final'):
                self.add_error('data_inicial', 'Data início deve ser menor que data término')
            elif clean.get('data_inicial') < datetime.date.today():
                self.add_error('data_inicial', 'Não poderá haver solicitação de afastamento com datas passadas')
            elif clean.get('data_inicial') < datetime.date.today() + timedelta(days=30):
                data_inicial = (datetime.date.today() + timedelta(days=30)).strftime('%d/%m/%Y')
                self.add_error(
                    'data_inicial',
                    f'A data do início do afastamento, deve ser no mínimo {data_inicial}',
                )
            elif clean.get('data_final') < clean.get('data_inicial') + timedelta(days=30):
                data_final = (clean.get('data_inicial') + timedelta(days=31)).strftime('%d/%m/%Y')
                self.add_error(
                    'data_final',
                    f'A data mínima do término do afastamento, deve ser {data_final}',
                )
        return clean

    def save(self):
        data_inicio = self.cleaned_data.get('data_inicial')
        data_final = self.cleaned_data.get('data_final')
        nova_jornada = self.cleaned_data['nova_jornada']

        self.processo.data_inicio = data_inicio
        self.processo.data_termino = data_final
        self.processo.nova_jornada = f'{nova_jornada} HORAS SEMANAIS '
        self.processo.save()


class AdicionarHorarioAfastamentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'

    data_inicial_horario = forms.DateFieldPlus(label='Data inicial')
    data_fim_horario = forms.DateFieldPlus(label='Data final')
    nova_jornada = forms.ChoiceField(label='Jornada pretendida', choices=())
    seg = forms.ChoiceField(label='SEG', choices=())
    ter = forms.ChoiceField(label='TER', choices=())
    qua = forms.ChoiceField(label='QUA', choices=())
    qui = forms.ChoiceField(label='QUI', choices=())
    sex = forms.ChoiceField(label='SEX', choices=())
    processo = None

    fieldsets = ((None, {'fields': ('data_inicial_horario', 'data_fim_horario', 'nova_jornada', ('seg', 'ter', 'qua', 'qui', 'sex'))}),)

    class Media:
        js = ['/static/rh/js/AdicionarHorarioAfastamentoForm.js']

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        # inicializando os campos
        self.fields['nova_jornada'].choices = self.processo.get_carga_horaria_disponivel_choice()
        choices = self.processo.get_carga_horaria_disponivel_choice(diaria=True)
        for name in ('seg', 'ter', 'qua', 'qui', 'sex'):
            self.fields[name].choices = choices
        # recuperando dados ja gravados
        self.fields['data_inicial_horario'].initial = self.processo.data_inicio
        self.fields['data_fim_horario'].initial = self.processo.data_termino

        nova_jornada = self.processo.nova_jornada or self.processo.servidor.jornada_trabalho.nome
        if nova_jornada:
            if nova_jornada == 'DEDICACAO EXCLUSIVA':
                jornada_semanal = '40'
            else:
                jornada_semanal = nova_jornada.split('HORAS SEMANAIS')[0].strip()

            self.fields['nova_jornada'].initial = float(jornada_semanal)

            ch_diaria = float(float(jornada_semanal) / 5)
            for name in ('seg', 'ter', 'qua', 'qui', 'sex'):
                self.fields[name].initial = ch_diaria

        if (
            self.processo.status == CargaHorariaReduzida.STATUS_NOVOS_DOCUMENTOS_SOLICITADOS
            or self.processo.status == CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_CHEFE
        ):
            self.fields['data_inicial'].widget.attrs['disabled'] = True
            self.fields['data_inicial'].widget.attrs['readonly'] = True

            self.fields['data_final'].widget.attrs['disabled'] = True
            self.fields['data_final'].widget.attrs['readonly'] = True

            self.fields['nova_jornada'].widget.attrs['disabled'] = True
            self.fields['nova_jornada'].widget.attrs['readonly'] = True

    def clean(self):
        clean = super().clean()
        soma = 0
        for name in ('seg', 'ter', 'qua', 'qui', 'sex'):
            ch = self.cleaned_data.get(name)
            soma += float(ch) if ch else 0
        if soma != float(self.cleaned_data['nova_jornada']):
            self.add_error('nova_jornada', 'A carga horária escolhida não corresponde à soma semanal. Corrija e tente novamente.')
        return clean

    def save(self):
        data_inicio = self.cleaned_data.get('data_inicial_horario')
        data_final = self.cleaned_data.get('data_fim_horario')
        seg = self.cleaned_data.get('seg')
        ter = self.cleaned_data.get('ter')
        qua = self.cleaned_data.get('qua')
        qui = self.cleaned_data.get('qui')
        sex = self.cleaned_data.get('sex')
        nova_jornada = self.cleaned_data['nova_jornada']

        horario = HorarioSemanal()
        horario.data_inicio = data_inicio
        horario.data_fim = data_final
        horario.seg = seg
        horario.ter = ter
        horario.qua = qua
        horario.qui = qui
        horario.sex = sex
        horario.processo_reducao_ch = self.processo
        horario.jornada_semanal = nova_jornada
        horario.save()

        if self.processo.status == CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH:
            self.processo.status = CargaHorariaReduzida.STATUS_ALTERANDO_HORARIO
            self.processo.save()


class EditarHorarioAfastamentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'

    data_inicial_horario = forms.DateFieldPlus(label='Data inicial')
    data_fim_horario = forms.DateFieldPlus(label='Data final')
    nova_jornada = forms.ChoiceField(label='Jornada pretendida', choices=())
    seg = forms.ChoiceField(label='SEG', choices=())
    ter = forms.ChoiceField(label='TER', choices=())
    qua = forms.ChoiceField(label='QUA', choices=())
    qui = forms.ChoiceField(label='QUI', choices=())
    sex = forms.ChoiceField(label='SEX', choices=())
    horario = None

    fieldsets = ((None, {'fields': ('data_inicial_horario', 'data_fim_horario', 'nova_jornada', ('seg', 'ter', 'qua', 'qui', 'sex'))}),)

    class Media:
        js = ['/static/rh/js/AdicionarHorarioAfastamentoForm.js']

    def __init__(self, *args, **kwargs):
        self.horario = kwargs.pop('horario')
        self.processo = CargaHorariaReduzida.objects.filter(id=self.horario.processo_reducao_ch.id)[0]
        super().__init__(*args, **kwargs)

        # inicializando os campos
        self.fields['nova_jornada'].choices = self.processo.get_carga_horaria_disponivel_choice()
        choices = self.processo.get_carga_horaria_disponivel_choice(diaria=True)
        for name in ('seg', 'ter', 'qua', 'qui', 'sex'):
            self.fields[name].choices = choices

        # recuperando dados ja gravados
        self.fields['data_inicial_horario'].initial = self.horario.data_inicio
        self.fields['data_fim_horario'].initial = self.horario.data_fim
        self.fields['nova_jornada'].initial = float(self.horario.jornada_semanal)
        self.fields['seg'].initial = self.horario.seg
        self.fields['ter'].initial = self.horario.ter
        self.fields['qua'].initial = self.horario.qua
        self.fields['qui'].initial = self.horario.qui
        self.fields['sex'].initial = self.horario.sex

    def clean(self):
        clean = super().clean()
        soma = (
            float(self.cleaned_data.get('seg', 0))
            + float(self.cleaned_data.get('ter', 0))
            + float(self.cleaned_data.get('qua', 0))
            + float(self.cleaned_data.get('qui', 0))
            + float(self.cleaned_data.get('sex', 0))
        )
        if soma != float(self.cleaned_data['nova_jornada']):
            self.add_error('nova_jornada', 'A carga horária escolhida não corresponde à soma semanal. Corrija e tente novamente.')
        return clean

    def save(self):
        data_inicio = self.cleaned_data.get('data_inicial_horario')
        data_final = self.cleaned_data.get('data_fim_horario')
        seg = self.cleaned_data.get('seg')
        ter = self.cleaned_data.get('ter')
        qua = self.cleaned_data.get('qua')
        qui = self.cleaned_data.get('qui')
        sex = self.cleaned_data.get('sex')
        nova_jornada = self.cleaned_data['nova_jornada']

        horario = self.horario
        horario.data_inicio = data_inicio
        horario.data_fim = data_final
        horario.seg = seg
        horario.ter = ter
        horario.qua = qua
        horario.qui = qui
        horario.sex = sex
        horario.processo_reducao_ch = self.processo
        horario.jornada_semanal = nova_jornada
        horario.save()

        if self.processo.status == CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH:
            self.processo.status = CargaHorariaReduzida.STATUS_ALTERANDO_HORARIO
            self.processo.save()


class IndeferirProcessoAfastamentoParcialRHForm(forms.ModelFormPlus):
    class Meta:
        model = CargaHorariaReduzida
        fields = ('motivo_indeferimento_rh',)
        widgets = {'motivo_indeferimento_rh': forms.Textarea}


class AniversarianteForm(forms.FormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().order_by('sigla'), label=nomenclatura.campus, required=False)
    setor = forms.ChainedModelChoiceField(
        Setor.objects.suap().filter(excluido=False),
        label='Setor:',
        empty_label='Selecione o Campus',
        initial='Todos',
        required=False,
        obj_label='sigla',
        form_filters=[('uo', 'uo__id')],
    )
    mes = forms.IntegerFieldPlus(label='Mês', widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        mes_selecionado = kwargs.pop('mes', date.today().month)
        super().__init__(*args, **kwargs)
        self.fields['mes'].initial = mes_selecionado

    METHOD = 'GET'

    class Meta:
        exclude = ()


class PosicionamentoPCAForm(forms.ModelForm):
    pca = forms.ModelChoiceField(queryset=PCA.objects, widget=AutocompleteWidget(search_fields=PCA.SEARCH_FIELDS), label='PCA')
    data_inicio_posicionamento_pca = forms.DateFieldPlus(label='Data de Início do Posicionamento')
    data_fim_posicionamento_pca = forms.DateFieldPlus(label='Data de Fim do Posicionamento', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codigo_pca_posicionamento'].initial = str(random.randint(10**8, 10**9 - 1))
        # self.fields["codigo_pca_posicionamento"].widget = HiddenInput()
        self.fields['codigo_posicionamento_pca'].initial = str(random.randint(10**8, 10**9 - 1))
        # self.fields["codigo_posicionamento_pca"].widget = HiddenInput()

    class Meta:
        model = PosicionamentoPCA
        exclude = ()


class CronogramaFolhaForm(forms.ModelFormPlus):
    mes = forms.ChoiceField(choices=Meses.get_choices(), required=True, label='Mês')
    ano = forms.ModelChoiceFieldPlus(Ano.objects, required=True, widget=forms.Select(), label='Ano')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ano'].queryset = Ano.objects.all()

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)

        data = datetime.date.min

        data_abertura_atualizacao_folha = self.cleaned_data.get('data_abertura_atualizacao_folha', data)
        data_fechamento_processamento_folha = self.cleaned_data.get('data_fechamento_processamento_folha', data)
        data_consulta_previa_folha = self.cleaned_data.get('data_consulta_previa_folha', data)
        data_abertura_proxima_folha = self.cleaned_data.get('data_abertura_proxima_folha', data)

        if data_abertura_atualizacao_folha > data_fechamento_processamento_folha:
            self.add_error(
                'data_abertura_atualizacao_folha',
                'A data da abertura para atualização da folha deve ser menor que a data de fechamento para o processamento da folha.',
            )
        if data_abertura_atualizacao_folha > data_consulta_previa_folha:
            self.add_error(
                'data_abertura_atualizacao_folha',
                'A data da abertura para atualização da folha deve ser menor que a data de consulta da prévia.',
            )
        if data_abertura_atualizacao_folha > data_abertura_proxima_folha:
            self.add_error(
                'data_abertura_atualizacao_folha',
                'A data da abertura para atualização da folha deve ser menor que a data de abertura da próxima folha.',
            )

        if data_fechamento_processamento_folha < data_abertura_atualizacao_folha:
            self.add_error(
                'data_fechamento_processamento_folha',
                'A data de fechamento para o processamento da folha não pode ser menor que a data de abertura para atualização da folha.',
            )
        if data_fechamento_processamento_folha > data_consulta_previa_folha:
            self.add_error(
                'data_fechamento_processamento_folha',
                'A data de fechamento para o processamento da folha não pode ser maior que a data de consulta da prévia.',
            )
        if data_fechamento_processamento_folha > data_abertura_proxima_folha:
            self.add_error(
                'data_fechamento_processamento_folha',
                'A data de fechamento para o processamento da folha não pode ser maior que a data de abertura da próxima folha.',
            )

        if data_consulta_previa_folha < data_abertura_atualizacao_folha:
            self.add_error(
                'data_consulta_previa_folha',
                'A data de consulta da prévia não pode ser menor que a data de abertura para atualização da folha.',
            )
        if data_consulta_previa_folha < data_fechamento_processamento_folha:
            self.add_error(
                'data_consulta_previa_folha',
                'A data de consulta da prévia não pode ser menor que a data de fechamento para processamento da folha.',
            )
        if data_consulta_previa_folha > data_abertura_proxima_folha:
            self.add_error('data_consulta_previa_folha', 'A data de consulta da prévia não pode ser maior que a data de abertura da próxima folha.')

        if data_abertura_proxima_folha < data_abertura_atualizacao_folha:
            self.add_error(
                'data_abertura_proxima_folha',
                'A data de abertura da próxima folha não pode ser menor que a data de abertura para atualização da folha.',
            )
        if data_abertura_proxima_folha < data_fechamento_processamento_folha:
            self.add_error(
                'data_abertura_proxima_folha',
                'A data de abertura da próxima folha não pode ser menor que a data de fechamento para processamento da folha.',
            )
        if data_abertura_proxima_folha < data_consulta_previa_folha:
            self.add_error(
                'data_abertura_proxima_folha',
                'A data de abertura da próxima folha não pode ser menor que a data de consulta da próxima folha.',
            )

        return cleaned_data


class AcaoSaudeForm(forms.ModelFormPlus):
    DOMINGO = 0
    SEGUNDA = 1
    TERCA = 2
    QUARTA = 3
    QUINTA = 4
    SEXTA = 5
    SABADO = 6
    DIAS_RESUMIDO_CHOICES = (
        (SEGUNDA, 'Segunda'),
        (TERCA, 'Terça'),
        (QUARTA, 'Quarta'),
        (QUINTA, 'Quinta'),
        (SEXTA, 'Sexta'),
        (SABADO, 'Sábado'),
        (DOMINGO, 'Domingo'),
    )

    dias_semanas = forms.MultipleChoiceField(
        choices=DIAS_RESUMIDO_CHOICES, widget=forms.CheckboxSelectMultiplePlus, required=True, label='Dias da Semana'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_dias_semanas(self):
        return ','.join(self.cleaned_data.get('dias_semanas'))


class AdicionarHorarioAcaoSaudeForm(forms.ModelFormPlus):
    class Meta:
        model = AgendaAtendimentoHorario
        exclude = ()

    def __init__(self, *args, **kwrags):
        acao_saude = kwrags.pop('acao_saude', None)
        super().__init__(*args, **kwrags)
        if acao_saude:
            self.fields['acao_saude'].initial = acao_saude.id
            self.fields['acao_saude'].widget = forms.HiddenInput()


class AgendaAtendimentoHorarioForm(forms.ModelFormPlus):
    hora_inicio = forms.TimeFieldPlus()
    hora_fim = forms.TimeFieldPlus()
    quantidade_vaga = forms.IntegerFieldPlus()
    profissional = forms.ModelChoiceFieldPlus(
        queryset=Servidor.objects.all(),
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
        required=True,
        label='Profissionais',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = AgendaAtendimentoHorario
        exclude = ()


class AgendarAtendimentoForm(forms.ModelFormPlus):
    data_consulta = forms.DateFieldPlus(label='Data da Consulta')
    solicitante = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS, help_text='Você pode selecionar outro servidor ou prestador de serviço.'),
    )
    horario = forms.ModelChoiceFieldPlus(queryset=AgendaAtendimentoHorario.objects, widget=forms.Select())

    class Meta:
        model = HorarioAgendado
        exclude = ()

    fieldsets = [('', {'fields': ['horario', 'solicitante', 'data_consulta', 'retorno']})]

    class Media:
        js = ('/static/rh/js/datepicker-week-restriction.js',)

    def __init__(self, *args, **kwargs):
        horario = kwargs.pop('horario', None)
        acao_saude = kwargs.pop('acao_saude', None)
        super().__init__(*args, **kwargs)

        usuario_logado = self.request.user
        self.fields['solicitante'].queryset = Vinculo.objects.funcionarios()

        if not acao_saude and horario:
            acao_saude = horario.acao_saude

        if acao_saude:
            # verificando datas bloqueadas
            qs_datas = DataConsultaBloqueada.objects.filter(acao_saude=acao_saude)
            lista_datas = []
            for data in qs_datas:
                lista_datas.append(data.data_consulta_bloqueada.strftime('%Y-%m-%d'))

            self.fields['horario'].queryset = acao_saude.agendaatendimentohorario_set.all()
            self.fields['data_consulta'].widget.attrs.update({'weeks': acao_saude.dias_semanas, 'dates': lista_datas})

        if self.request.GET.get('v'):
            self.fields['horario'].initial = int(self.request.GET.get('v'))

        if horario:
            self.fields['horario'].initial = horario.id
            self.fields['horario'].widget = forms.HiddenInput()

        if not usuario_logado.has_perm('rh.add_acaosaude'):
            self.fields['solicitante'].initial = usuario_logado.get_vinculo().id
            self.fields['solicitante'].widget = forms.HiddenInput()

    def clean(self):
        super().clean()
        horario_agenda = self.cleaned_data.get('horario')
        solicitante = self.cleaned_data.get('solicitante')
        data_consulta = self.cleaned_data.get('data_consulta')
        if horario_agenda:
            if not horario_agenda.tem_vaga_disponivel(data_consulta):
                raise ValidationError('Não há vagas para o horário e dia selecionados.')
            if horario_agenda.esta_agendado_em_algum_horario(solicitante):
                raise ValidationError('Você já está agendado nesta ação de saúde.')

            # verificando datas bloqueadas
            for i in horario_agenda.acao_saude.dataconsultabloqueada_set.all():
                if data_consulta and data_consulta == i.data_consulta_bloqueada:
                    raise ValidationError(f'A data {i.data_consulta_bloqueada.strftime("%d-%m-%Y")} está bloqueada para consultas.')

            # verificando dia de semana bloqueados
            if data_consulta:
                dia_semana = 0 if data_consulta.isoweekday() == 7 else data_consulta.isoweekday()
                if str(dia_semana) not in horario_agenda.acao_saude.dias_semanas.split(','):
                    weekday = [
                        'no domingo',
                        'na segunda-feira',
                        'na terça-feira',
                        'na quarta-feira',
                        'na quinta-feira',
                        'na sexta-feira',
                        'no sábado',
                    ]
                    raise ValidationError(f'Não é permitido para este evento agendamento {weekday[data_consulta.weekday()]} ')
        else:
            raise ValidationError('Nenhum horário foi selecionado.')


class DataConsultaBloqueadaForm(forms.ModelFormPlus):
    acao_saude = forms.ModelChoiceFieldPlus(AcaoSaude.ativas, label='Ação de Saúde', widget=AutocompleteWidget(search_fields=AcaoSaude.SEARCH_FIELDS))

    class Meta:
        model = DataConsultaBloqueada
        exclude = ('houve_remarcacao',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['acao_saude'].queryset = AcaoSaude.ativas.all()


class PCAForm(forms.ModelFormPlus):
    servidor = forms.ModelChoiceFieldPlus(Servidor.objects, label='Servidor', widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS))
    servidor_matricula_crh = forms.CharFieldPlus(
        label='Matrícula CRH do Servidor',
        help_text='Preencha caso cadastro do servidor no SUAP não tenha ainda a matricula CRH',
        required=False,
    )
    forma_entrada_pca = forms.ModelChoiceFieldPlus(
        FormaProvimentoVacancia.objects,
        label='Forma de Entrada',
        widget=AutocompleteWidget(search_fields=FormaProvimentoVacancia.SEARCH_FIELDS),
    )
    cargo_pca = forms.ModelChoiceFieldPlus(CargoEmprego.objects, label='Cargo Emprego')
    servidor_vaga_pca = forms.CharFieldPlus(label='Código de Vaga', required=False)
    data_entrada_pca = forms.DateFieldPlus(label='Data de Entrada')

    forma_vacancia_pca = forms.ModelChoiceFieldPlus(
        FormaProvimentoVacancia.objects,
        label='Forma de Vacância',
        widget=AutocompleteWidget(search_fields=FormaProvimentoVacancia.SEARCH_FIELDS),
        required=False,
    )
    data_vacancia_pca = forms.DateFieldPlus(label='Data de Vacância', required=False)

    class Meta:
        model = PCA
        fields = (
            'servidor',
            'servidor_matricula_crh',
            'cargo_pca',
            'codigo_pca',
            'servidor_vaga_pca',
            'data_entrada_pca',
            'forma_entrada_pca',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        matricula = self.request.GET.get('m')
        if matricula:
            qs_servidor = Servidor.objects.filter(matricula=matricula)
            if qs_servidor.exists():
                servidor = qs_servidor[0]
                self.fields['servidor'].initial = servidor
                self.fields['servidor_matricula_crh'].initial = servidor.matricula_crh
                self.fields['codigo_pca'].initial = str(random.randint(10**10, 10**11 - 1))
                self.fields['codigo_pca'].widget = HiddenInput()
        self.fields['forma_entrada_pca'].queryset = FormaProvimentoVacancia.objects.exclude(
            descricao=f'Atualize o cadastro de {self.Meta.model._meta.verbose_name_plural}'
        )

    def save(self, *args, **kwargs):
        self.instance.servidor_matricula_crh = self.instance.servidor_matricula_crh
        if not self.instance.data_vacancia_pca:
            # Deixamos essa data preenchida para manter padronização com o SIAPE
            self.instance.data_vacancia_pca = datetime.date(2500, 12, 31)
        return super().save(*args, **kwargs)


class JornadaTrabalhoPCAForm(forms.ModelFormPlus):
    pca = forms.ModelChoiceField(queryset=PCA.objects, widget=AutocompleteWidget(search_fields=PCA.SEARCH_FIELDS), label='PCA')
    data_inicio_jornada_trabalho_pca = forms.DateFieldPlus(label='Data de Início da Jornada de Trabalho')
    data_fim_jornada_trabalho_pca = forms.DateFieldPlus(label='Data de Fim da Jornada de Trabalho', required=False)

    class Meta:
        model = JornadaTrabalhoPCA
        fields = ('pca', 'qtde_jornada_trabalho_pca', 'data_inicio_jornada_trabalho_pca', 'data_fim_jornada_trabalho_pca')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_inicio_jornada_trabalho_pca'].label = 'Data inicial'
        self.fields['data_fim_jornada_trabalho_pca'].label = 'Data final'
        self.fields['data_fim_jornada_trabalho_pca'].required = False
        self.fields['qtde_jornada_trabalho_pca'].label = 'Qtd de Horas'
        self.fields['qtde_jornada_trabalho_pca'].help_text = 'Exemplos de Jornada: 20, 30, 40 ou Dedicação Exclusiva'

    def save(self, *args, **kwargs):
        if not self.instance.data_fim_jornada_trabalho_pca:
            # Deixamos essa data preenchida para manter padronização com o SIAPE
            self.instance.data_fim_jornada_trabalho_pca = datetime.date(2500, 12, 31)
        #
        return super().save(*args, **kwargs)


class RegimeJuridicoPCAForm(forms.ModelFormPlus):
    pca = forms.ModelChoiceField(queryset=PCA.objects, widget=AutocompleteWidget(search_fields=PCA.SEARCH_FIELDS), label='PCA')
    regime_juridico = forms.ModelChoiceField(
        queryset=RegimeJuridico.objects, widget=AutocompleteWidget(search_fields=RegimeJuridico.SEARCH_FIELDS), label='Regime Jurídico'
    )
    data_inicio_regime_juridico_pca = forms.DateFieldPlus(label='Data de Início do Regime Jurídico')
    data_fim_regime_juridico_pca = forms.DateFieldPlus(label='Data de Início do Regime Jurídico', required=False)
    valor_fator_tempo_regime_juridico_pca = forms.DecimalFieldPlus(label='Fator de Tempo', help_text='Exemplo: 1.0')

    class Meta:
        model = RegimeJuridicoPCA
        fields = (
            'pca',
            'regime_juridico',
            'data_inicio_regime_juridico_pca',
            'data_fim_regime_juridico_pca',
            'valor_fator_tempo_regime_juridico_pca',
        )


class RelatorioAfastamentosCriticosForm(forms.FormPlus):
    METHOD = 'GET'
    CATEGORIA_CHOICES = [
        ['Todos', 'Todos os Servidores'],
        ['docente', 'Apenas Docentes'],
        ['tecnico_administrativo', 'Apenas Administrativos'],
    ]

    uo = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.suap(),
        label='Campi',
        required=False,
        help_text='Caso você não escolha nenhum campus, a consulta irá considerar todos os campi.',
    )
    categoria = forms.ChoiceField(choices=CATEGORIA_CHOICES, required=False)


class WebserviceSIAPEForm(forms.FormPlus):
    """
    getPensionista(cpfPensionista, cpf, siglaSistema, nomeSistema, senha)
    consultaDadosRepresentanteLegal(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosFuncionais(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosDependentes(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    obterVersao(siglaSistema)
    consultaDadosPA(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    listaUorgs(siglaSistema, nomeSistema, senha, cpf, codOrgao, codUorg)
    consultaDadosEscolares(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosPessoais(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosAfastamento(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosEnderecoResidencial(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaTotalizadorVagasOrgao(siglaSistema, nomeSistema, senha, cpf, codOrgao)
    consultaPensaoRecebida(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosFinanceiros(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    listaServidores(siglaSistema, nomeSistema, senha, cpf, codOrgao, codUorg)
    consultaDadosDocumentacao(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosBancarios(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaPensoesInstituidas(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosSICAJ(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    verificaVinculo(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    dadosUorg(siglaSistema, nomeSistema, senha, cpf, codOrgao, codUorg)
    consultaDadosUorg(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    consultaDadosCurriculo(siglaSistema, nomeSistema, senha, cpf, codOrgao, parmExistPag, parmTipoVinculo)
    """

    cpf = forms.CharFieldPlus(label='CPF', required=False)
    cpf_pensionista = forms.CharFieldPlus(label='CPF Pensionista', required=False)
    consulta = forms.ChoiceField(label='Consulta', choices=())
    codUorg = forms.ChoiceField(label='Setor', choices=(), required=False)
    parmExistPag = forms.ChoiceField(label='ParmExistPag', choices=(['a', 'a'], ['b', 'b']))
    parmTipoVinculo = forms.ChoiceField(label='ParmTipoVinculo', choices=(['a', 'a'], ['b', 'b'], ['c', 'c']))

    SUBMIT_LABEL = 'Consultar'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ws = ImportadorWs()
        self.fields['consulta'].choices = ws._get_services_siape()
        setores = []
        for setor in Setor.objects.siape().filter(uo__sigla__isnull=False).values_list('codigo', 'sigla'):
            setores.append([int(setor[0]), setor[1]])
        self.fields['codUorg'].choices = setores

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        return mask_numbers(cpf)


class ImportarServidorWSForm(forms.FormPlus):
    cpf = forms.BrCpfField(label='CPF', required=False)
    apenas_servidores_em_exercicio = forms.BooleanField(
        label='Pesquisar somente servidor em exercício na instituicão?',
        help_text='Ao marcar esta opção, serão desconsiderados aposentados, pensionistas, cedidos ou em exercício externo ao órgão de lotação.',
        required=False,
    )
    SUBMIT_LABEL = 'Consultar'

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        return mask_numbers(cpf)


class DocentesPorDisciplinaFiltroForm(forms.Form):
    filtro_disciplinas_cadastradas = (
        (0, 'Todos'),
        (1, 'Docentes sem disciplina de ingresso cadastrada'),
        (2, 'Docentes com disciplina de ingresso cadastrada'),
    )
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), label=nomenclatura.campus, required=False)
    disciplinas = forms.ChoiceField(label='Filtro de docentes por disciplina', choices=filtro_disciplinas_cadastradas, required=False)

    fieldsets = (('', {'fields': (('campus', 'disciplinas'),)}),)


class BancoForm(forms.ModelFormPlus):
    class Meta:
        model = Banco
        fields = ('codigo', 'sigla', 'nome', 'excluido')

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        erro = False
        if self.cleaned_data.get('codigo'):
            if (
                not self.instance.pk
                and Banco.objects.filter(codigo=self.cleaned_data.get('codigo')).exists()
                or self.instance.pk
                and Banco.objects.exclude(id=self.instance.pk).filter(codigo=self.cleaned_data.get('codigo')).exists()
            ):
                erro = True
        if erro:
            self.add_error('codigo', 'Um banco com o código informado já foi cadastrado.')
        return cleaned_data


def SetorRaizFormFactory(request):
    setor_usuario = request.user.get_relacionamento().setor

    class SetorRaizForm(forms.FormPlus):
        raiz = forms.ModelChoiceFieldPlus(
            queryset=Setor.objects.suap_ativos(), widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS), initial=setor_usuario, label='Setor'
        )

    return SetorRaizForm


class EditarServidorCargoEmpregoAreaForm(forms.ModelFormPlus):
    class Meta:
        model = Servidor
        fields = ('cargo_emprego_area',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['cargo_emprego_area'].queryset = self.instance.cargo_emprego.cargoempregoarea_set.all()


class ServidoresPorAreaFiltroForm(forms.Form):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    filtro_cargo_area_cadastradas = ((0, 'Todos'), (1, 'Com área cadastrada'), (2, 'Sem área cadastrada'))

    com_area_cadastrada = forms.ChoiceField(label='Escopo dos Servidores', choices=filtro_cargo_area_cadastradas, required=False)
    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo().all(), label=nomenclatura.campus, required=False)
    cargo_emprego = forms.ModelChoiceFieldPlus(
        CargoEmprego.utilizados.filter(cargoempregoarea__isnull=False).distinct(), label='Cargo Emprego', required=False
    )
    cargo_emprego_area = forms.ModelChoiceFieldPlus(CargoEmpregoArea.objects, label='Área', required=False)


class ServidorReativacaoTemporariaForm(forms.ModelFormPlus):
    class Meta:
        model = ServidorReativacaoTemporaria
        fields = (
            'servidor',
            'data_inicio',
            'data_fim',
            'justificativa',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Servidor.objects.filter(ativo=False)
        if 'justificativa' in self.fields:
            self.fields['justificativa'].help_text = 'Descreva a justificativa e, quando existir, referencie o chamado ou processo administrativo.'
        if 'servidor' in self.fields:
            self.fields['servidor'].help_text = 'A reativação solicitada será efetivada pela Gestão de Pessoas Sistêmica.'
        if 'data_inicio' in self.fields:
            self.fields['data_inicio'].initial = get_datetime_now().date()
            self.fields['data_inicio'].widget.attrs['readonly'] = True
            self.fields['data_inicio'].help_text = 'A data de início é sempre a data atual.'
        if self.instance.pk and 'data_inicio' in self.fields:
            self.fields['data_inicio'].widget.attrs['readonly'] = True

        request = getattr(self, 'request', None)
        if request and request.user.has_perm('rh.eh_rh_campus') and not request.user.has_perm('rh.eh_rh_sistemico'):
            campus = request.user.get_relacionamento().setor.uo
            queryset = queryset.filter(setor__uo=campus)

        if self.instance.pk and self.instance.servidor.ativo:
            queryset |= Servidor.objects.filter(pk=self.instance.servidor_id)
        if 'servidor' in self.fields:
            self.fields['servidor'].queryset = queryset.distinct()

    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        servidor = cleaned_data.get('servidor')
        hoje = get_datetime_now().date()
        if data_inicio and data_fim and data_fim < data_inicio:
            self.add_error('data_fim', 'A data de fim deve ser maior ou igual à data de início.')
        if data_inicio and not self.instance.pk and data_inicio != hoje:
            self.add_error('data_inicio', 'A data de início deve ser a data atual.')
        if data_inicio and self.instance.pk and data_inicio != self.instance.data_inicio:
            self.add_error('data_inicio', 'A data de início não pode ser alterada.')
        if data_inicio and data_fim and (data_fim - data_inicio).days > 90:
            self.add_error('data_fim', 'A duração da reativação temporária não pode ultrapassar 90 dias.')
        request = getattr(self, 'request', None)
        if servidor and request and request.user.has_perm('rh.eh_rh_campus') and not request.user.has_perm('rh.eh_rh_sistemico'):
            campus = request.user.get_relacionamento().setor.uo
            if servidor.setor and servidor.setor.uo != campus:
                self.add_error('servidor', 'Você só pode reativar vínculos do seu campus.')
        return cleaned_data


class ServidorReativacaoPermanenteForm(forms.ModelFormPlus):
    class Meta:
        model = ServidorReativacaoPermanente
        fields = ('servidor', 'justificativa')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servidores = Servidor.objects.filter(ativo=False)
        if 'justificativa' in self.fields:
            self.fields['justificativa'].help_text = 'Descreva a justificativa e, quando existir, referencie o chamado ou processo administrativo.'
        if 'servidor' in self.fields:
            self.fields[
                'servidor'
            ].help_text = (
                'A ocorrência de exclusão a ser removida será definida automaticamente quando a Gestão de Pessoas Sistêmica efetivar a solicitação.'
            )

        request = getattr(self, 'request', None)
        if request and request.user.has_perm('rh.eh_rh_campus') and not request.user.has_perm('rh.eh_rh_sistemico'):
            campus = request.user.get_relacionamento().setor.uo
            servidores = servidores.filter(setor__uo=campus)

        if self.instance.pk and self.instance.servidor_id:
            servidores |= Servidor.objects.filter(pk=self.instance.servidor_id)

        if 'servidor' in self.fields:
            self.fields['servidor'].queryset = servidores.distinct()

    def clean(self):
        cleaned_data = super().clean()
        servidor = cleaned_data.get('servidor')
        request = getattr(self, 'request', None)
        if servidor and request and request.user.has_perm('rh.eh_rh_campus') and not request.user.has_perm('rh.eh_rh_sistemico'):
            campus = request.user.get_relacionamento().setor.uo
            if servidor.setor and servidor.setor.uo != campus:
                self.add_error('servidor', 'Você só pode reativar vínculos do seu campus.')
        if servidor and not self.instance.pk and not servidor.get_ocorrencias_exclusao().exists():
            self.add_error('servidor', 'O servidor selecionado não possui ocorrências de exclusão para análise.')
        return cleaned_data


class ExcecaoDadoForm(forms.ModelFormPlus):
    campos = forms.MultipleModelChoiceFieldPlus(label='Dados', required=False, queryset=CampoExcecao.objects.all())

    class Meta:
        model = ExcecaoDado
        exclude = ()


class SolicitacaoAlteracaoFotoForm(forms.ModelFormPlus):
    solicitante = forms.ModelChoiceField(
        queryset=Servidor.objects,
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
        label='Solicitante',
        help_text='O servidor selecionado neste campo deve ser o mesmo da foto.',
    )

    class Meta:
        model = SolicitacaoAlteracaoFoto
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        # carregando o queryset do autocomplete
        self.fields['solicitante'].queryset = Servidor.objects.filter(ativo=True)
        # setando um solicitante padrão quando é rh sistêmico
        if self.request.user.has_perm('rh.eh_rh_sistemico'):
            self.fields['solicitante'].initial = self.request.user.get_relacionamento()
        else:
            self.fields['solicitante'].required = False  # para não dar problema no clean do form

    def _get_solicitante(self):
        #
        # o cleaned_data tem o solicitante quando é o RH realizando uma solicitação
        solicitante = self.cleaned_data.get('solicitante')
        #
        # case não tenha um solicitante no cleaned_data, o solicitante é um servidor "comum" (sem permissão de RH)
        if not solicitante:
            solicitante = self.request.user.get_relacionamento()
        return solicitante

    def clean(self):
        cleaned_data = super().clean()

        foto = self.cleaned_data.get('foto')
        if not foto:
            raise forms.ValidationError('Você precisa selecionar e ajustar uma foto para salvar.')

        form = ImageFormFieldWithThumbs()
        try:
            if foto:
                content = foto.read()
                foto.file.seek(0)
                form.is_compatible(content)
        except Exception:
            raise forms.ValidationError('Formato da foto inválido, por favor escolha outra foto.')

        solicitante = self._get_solicitante()
        _qs = SolicitacaoAlteracaoFoto.objects.filter(solicitante=solicitante, situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO)
        #
        # vericando se é uma edição
        if self.instance and self.instance.pk:
            # verificando a quantidade de solicitações existentes
            if _qs.count() == 1 and _qs[0] == self.instance:
                # é edição do único registro, logo é permitido...
                return cleaned_data
        if solicitante:
            if _qs.exists():
                raise forms.ValidationError(
                    f'Já existe uma solicitação para {solicitante} aguardando validação. Não é possível realizar uma nova solicitação.'
                )
        else:
            raise forms.ValidationError('Não foi possível identificar o solicitante do registro. Tente novamente.')
        return cleaned_data

    def save(self, commit=True):
        self.instance.solicitante = self._get_solicitante()
        return super().save(commit)


class RejeitarSolicitacaoAlteracaoFotoForm(forms.FormPlus):
    motivo_rejeicao = forms.CharField(widget=forms.Textarea, required=True, label='Motivo da Rejeição')
    solicitacao = forms.IntegerFieldPlus(label='Solicitação', widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if instance.id:
            self.fields['solicitacao'].initial = instance.id

    def processar(self, request):
        s = SolicitacaoAlteracaoFoto.objects.get(id=request.POST.get('solicitacao'))
        s.rejeitar(request)


class ServidorAfastamentoSiapeForm(forms.ModelForm):
    class Meta:
        model = ServidorAfastamento
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.id:
            if self.instance.afastamento.codigo not in ServidorAfastamento.DESCONSIDERAR_REGRA_30_DIAS_CODIGOS:
                self.fields['desconsiderar_regra_30_dias'].widget.attrs['disabled'] = True

    def clean(self):
        cleaned_data = super().clean()
        instance = self.instance

        #
        # verificando se o campo para desconsiderar regra dos 20 dias foi marcada
        desconsiderar_30_dias = cleaned_data.get('desconsiderar_regra_30_dias')
        if desconsiderar_30_dias:
            #
            # verifica se o afastamento pode desconsiderar a regra dos 30 dias
            if instance.afastamento.codigo not in ServidorAfastamento.DESCONSIDERAR_REGRA_30_DIAS_CODIGOS:
                raise forms.ValidationError(f'O afastamento {instance} não está configurado para desconsiderar a regra dos 30 dias.')

        return cleaned_data


class CargoEmpregoForm(forms.ModelForm):
    """Cadastro manual de cargo emprego.

    O cargo nasce gerenciado pelo SUAP e ainda não confirmado pelo SIAPE. Quando a extração da
    tabela de cargos trouxer o mesmo código, o importador atualiza este registro (a chave é o
    código) e marca `cargo_siape`, sem duplicar e sem perder os vínculos já criados.
    """

    class Meta:
        model = CargoEmprego
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['cargo_suap'].initial = True
            self.fields['cargo_siape'].initial = False


class FuncaoForm(forms.ModelForm):
    class Meta:
        model = Funcao
        exclude = ()

    def clean(self):
        clean = super().clean()
        return clean


class ObterDadosCompletaresPessoaForm(forms.FormPlus):
    api = forms.ModelChoiceFieldPlus(APIExterna.objects.filter(ativo=True))

    def processar(self, pessoa, user):
        try:
            PessoaInfoComplementar.get_instance(pessoa=pessoa, api_origem=self.cleaned_data['api'], usuario_consulta=user, force=True)
            mensagem = 'Informações Atualizadas com Sucesso.'
        except Exception as e:
            mensagem = f'Ocorreu um erro ao executar o comando: {e!s}'

        return mensagem


class QuantitativoCargoClassePorCampusForm(forms.ModelFormPlus):
    class Meta:
        model = QuantitativoCargoClassePorCampus
        fields = ('uo', 'cargo_classe', 'quantidade')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uo'].queryset = UnidadeOrganizacional.objects.siape()
        self.fields['cargo_classe'].queryset = CargoClasse.objects.filter(codigo__in=('A', 'B', 'C', 'D', 'E')).order_by('codigo')


class BuscarPessoaJuridicaApiRFBForm(forms.FormPlus):
    cnpj = forms.BrCnpjField(label='CNPJ da Empresa', required=False)

    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    def buscar(self) -> tuple[bool, dict[str, object]]:
        """
        Realiza requisição para a API do ComprasGov para buscar contrato
        """
        cnpj = self.cleaned_data['cnpj']
        api_externa = APIExterna.CNPJ
        if not api_externa.ativo:
            return False, {}
        api_service = api_externa.get_service()
        return api_service.consulta_empresa(cnpj)


class EquivalenciaSetorForm(forms.ModelFormPlus):
    setor_siape = forms.ModelChoiceFieldPlus(Setor.objects, label='Setor SIAPE', widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS))

    class Meta:
        model = Setor
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        self.fields['setor_siape'].queryset = Setor.objects.siape()
        if self.instance and self.instance.pk and self.instance.equivalencia_codigo is not None:
            _setor_equivalence = Setor.objects.filter(codigo=self.instance.equivalencia_codigo).first()
            self.fields['setor_siape'].initial = _setor_equivalence
            #
            if _setor_equivalence:
                #
                self.fields['equivalencia_info'] = forms.CharFieldPlus(
                    label='Equivalência (código)',
                    initial=f'{_setor_equivalence} ({_setor_equivalence.codigo})',
                    required=False,
                    disabled=True,  # impede edição/validação
                    widget=forms.TextInput(attrs={'class': 'form-control-plaintext', 'readonly': 'readonly', 'disable': 'disable'}),
                    help_text='Informação apenas para consulta.',
                )

                # (Opcional) define a ordem de exibição
                self.order_fields(['setor_siape', 'equivalencia_info'])

    def save(self, commit=...):
        setor_siape = self.cleaned_data.get('setor_siape')
        if self.instance and setor_siape:
            self.instance.equivalencia_codigo = setor_siape.codigo
        return super().save(commit)


class UnificarPessoasForm(forms.FormPlus):
    sobrevivente = forms.ModelChoiceFieldPlus(
        PessoaFisica.objects, label='Pessoa que fica', help_text='Recebe os vínculos e as referências da outra.', widget=AutocompleteWidget(min=3)
    )
    perdedora = forms.ModelChoiceFieldPlus(
        PessoaFisica.objects, label='Pessoa que sai', help_text='É apagada depois da unificação.', widget=AutocompleteWidget(min=3)
    )
    confirmar = forms.BooleanField(label='Confirmo a unificação (não há desfazer)', required=False)

    def clean(self):
        cleaned_data = super().clean()
        fica, sai = cleaned_data['sobrevivente'], cleaned_data['perdedora']
        if fica == sai:
            raise forms.ValidationError('Escolha duas pessoas diferentes.')
        if eh_sintetico(fica.documento_identificador) and not eh_sintetico(sai.documento_identificador):
            raise forms.ValidationError(
                f'A pessoa que fica tem documento provisório ({fica.documento_identificador}) e a que sai tem documento '
                f'({sai.documento_identificador}): inverta as duas.'
            )
        cleaned_data['pessoas'] = [fica, sai]
        return cleaned_data
