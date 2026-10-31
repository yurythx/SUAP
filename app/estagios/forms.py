import datetime
from collections import OrderedDict

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.db import transaction
from django.db.models.aggregates import Sum
from django.db.models.fields.files import FieldFile
from django.forms.models import BaseInlineFormSet

from comum.models import Vinculo
from comum.utils import get_uo
from djtools import forms
from djtools.forms import BrCnpjWidget, ReCaptchaField
from djtools.forms.widgets import AutocompleteWidget, Select
from djtools.templatetags.filters import format_, in_group
from djtools.utils import send_notification, get_datetime_now
from documento_eletronico.models import ModeloDocumento
from edu.models import Aluno, Cidade, CursoCampus, Estado, Modalidade, Professor, Turno
from estagios import tasks
from estagios.models import (
    AditivoContratualAprendizagem,
    AnexoAprendizagem,
    AnexoPraticaProfissionalGenerica,
    Aprendizagem,
    Atividade,
    AtividadeProfissionalEfetiva,
    Convenio,
    EstagioAditivoContratual,
    JustificativaVisitaEstagio,
    JustificativaVisitaModuloAprendizagem,
    ModuloAprendizagem,
    OfertaPraticaProfissional,
    OrientacaoAprendizagem,
    OrientacaoAtividadeProfissionalEfetiva,
    OrientacaoEstagio,
    PraticaProfissional,
    RelatorioModuloAprendizagem,
    RelatorioSemestralEstagio,
    RelatorioSemestralEstagioAtividade,
    SolicitacaoCancelamentoEncerramentoEstagio,
    TipoAditivo,
    TipoAditivoAprendizagem,
    TipoRemuneracao,
    VisitaAprendizagem,
    VisitaPraticaProfissional,
    TermoRealizacaoEstagio,
)
from estagios.utils import (
    ListCharField,
    get_divergencias_relatorios_estagio,
    get_divergencias_relatorios_modulo_aprendizagem,
    get_situacoes_irregulares,
    tem_permissao_de_coordenador,
)
from rh.models import PessoaJuridica, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    opcional_registro_visita = forms.BooleanField(
        label='Opcional o Registro de Visita de Estágio',
        required=False,
        help_text='Marque essa opção caso queira deixar o registro de visita de estágio opcional ao registrar encerramento.',
    )
    cadastrar_modulos_aprendizagem_manualmente = forms.BooleanField(
        label='Cadastrar os Módulos de Aprendizagem manualmente',
        required=False,
        help_text='Ao marcar esta opção, o sistema exigirá que o usuário cadastre os Módulos de Aprendizagem manualmente '
        'no momento da criação de uma Aprendizagem. Ele precisará definir de 1 a 4 módulos, descrevendo quais '
        'atividades cada um abordará. Ao desmarcar esta opção, o sistema solicitará apenas uma descrição '
        'geral das atividades a serem desenvolvidas ao longo de toda a aprendizagem, e a subdivisão da '
        'aprendizagem se dará em períodos semestrais, calculados automaticamente pelo sistema, com base '
        'na duração total da aprendizagem.',
    )
    url_manuais_aprendizagem = forms.URLField(
        label='URL - Manuais da Aprendizagem',
        required=False,
        help_text='Endereço para a página onde o usuário poderá acessar e baixar os manuais da Aprendizagem.',
    )
    url_modelos_formularios_aprendizagem = forms.URLField(
        label='URL - Formulários e Modelos de documentos da Aprendizagem',
        required=False,
        help_text='Endereço para a página onde o usuário poderá acessar e baixar modelos de documentos e formulários '
        'usados no cadastro da Aprendizagem.',
    )
    url_manuais_atividade_profissional_efetiva = forms.URLField(
        label='URL - Manuais da Atividade Profissional Efetiva',
        required=False,
        help_text='Endereço para a página onde o usuário poderá acessar e baixar os manuais da Atividade Profissional Efetiva.',
    )
    url_manuais_estagio = forms.URLField(
        label='URL - Manuais do Estágio',
        required=False,
        help_text='Endereço para a página onde o usuário poderá acessar e baixar os manuais do Estágio.',
    )
    url_modelos_formularios_estagio = forms.URLField(
        label='URL - Formulários e Modelos de documentos do Estágio',
        required=False,
        help_text='Endereço para a página onde o usuário poderá acessar e baixar modelos de documentos e formulários '
        'usados no cadastro dos Estágios.',
    )
    opcional_notificar_supervisor = forms.BooleanField(
        label='Opcional o notificar supervisor',
        required=False,
        help_text='Marque essa opção caso queira deixar opcional o envio de notificação de pendências para o supervisor',
    )


class AtLeastOneFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        non_empty_forms = 0
        for form in self:
            if form.cleaned_data:
                non_empty_forms += 1
        if non_empty_forms - len(self.deleted_forms) < 1:
            raise forms.ValidationError('Ao menos uma atividade deve ser adicionada ao plano.')


class PraticaProfissionalForm(forms.ModelFormPlus):
    estado = forms.ModelChoiceField(queryset=Estado.objects, label='Unidade da Federação', required=False, widget=Select())
    cidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Município',
        required=False,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS, form_filters=[('estado', 'estado__in')]),
    )
    orientador = forms.ModelChoiceFieldPlus(
        Professor.objects, label='Professor Orientador', required=True, widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS)
    )
    email_supervisor = forms.EmailField(label='E-mail', help_text='Este e-mail será importante para o envio da avaliação.')
    supervisor = forms.ModelChoiceFieldPlus(
        Vinculo.objects.funcionarios().ativos(),
        label='Supervisor',
        help_text='Só preencher esse campo, se for utilizar a funcionalidade de Documento Eletrônico.',
        required=False,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    fieldsets = (
        ('Dados gerais', {'fields': ('obrigatorio', 'turno', 'aluno', ('convenio', 'orientador'), ('servidor_representante', 'agente_integracao'))}),
        (
            'Concedente e o Endereço de seu Estabelecimento',
            {
                'fields': (
                    'empresa',
                    'representante_concedente',
                    ('nome_representante_concedente', 'cargo_representante_concedente'),
                    'ramo_atividade',
                    ('estado', 'cidade'),
                    ('logradouro', 'numero'),
                    'complemento',
                    ('bairro', 'cep'),
                )
            },
        ),
        (
            'Bolsa',
            {'fields': (('remunerada', 'tipo_remuneracao'), 'valor', ('auxilio_transporte', 'auxilio_alimentacao'), 'descricao_outros_beneficios')},
        ),
        ('Período e Carga Horária', {'fields': (('data_inicio', 'data_prevista_fim'), ('ch_semanal', 'ch_diaria', 'horario'))}),
        (
            'Documentação',
            {
                'fields': (
                    'relatorio_avaliacao_instalacoes',
                    ('plano_atividades', 'termo_compromisso'),
                    ('testemunha1', 'testemunha_1'),
                    ('testemunha2', 'testemunha_2'),
                )
            },
        ),
        ('Seguro', {'fields': (('nome_da_seguradora', 'cnpj_da_seguradora'), 'numero_seguro')}),
        ('Supervisor', {'fields': ('supervisor', 'nome_supervisor', 'cargo_supervisor', ('telefone_supervisor', 'email_supervisor'), 'observacao')}),
    )

    class Meta:
        model = PraticaProfissional
        fields = (
            'tipo',
            'obrigatorio',
            'turno',
            'aluno',
            'convenio',
            'empresa',
            'orientador',
            'remunerada',
            'tipo_remuneracao',
            'valor',
            'data_inicio',
            'data_prevista_fim',
            'ch_semanal',
            'relatorio_avaliacao_instalacoes',
            'plano_atividades',
            'termo_compromisso',
            'numero_seguro',
            'nome_supervisor',
            'telefone_supervisor',
            'cargo_supervisor',
            'email_supervisor',
            'observacao',
            'auxilio_transporte',
            'auxilio_alimentacao',
            'descricao_outros_beneficios',
            'estado',
            'cidade',
            'logradouro',
            'numero',
            'complemento',
            'bairro',
            'cep',
            'nome_representante_concedente',
            'cargo_representante_concedente',
        )

    class Media:
        js = ('/static/estagios/js/EstagioForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields['orientador'].queryset = Professor.servidores_docentes.all()
        self.fields['obrigatorio'].required = True
        self.fields['aluno'].widget = AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS)

        qs_alunos = self.fields['aluno'].queryset.select_related('curso_campus')
        if in_group(self.request.user, ['Coordenador de Estágio']) and not in_group(
            self.request.user, ['Coordenador de Estágio Sistêmico', 'estagios Administrador']
        ):
            qs_alunos = qs_alunos.filter(curso_campus__diretoria__setor__uo=get_uo(self.request.user))

        qs_alunos = (
            qs_alunos.filter(
                matriz__isnull=False,
                curso_campus__modalidade_id__in=Modalidade.modalidades_que_fazem_estagio(),
            )
            .exclude(
                situacao_id__in=get_situacoes_irregulares().values_list('pk', flat=True),
            )
            .order_by('-pk')
        )
        self.fields['aluno'].queryset = qs_alunos

        self.fields['empresa'].widget = AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
        self.fields['empresa'].queryset = self.fields['empresa'].queryset.filter(
            tipo_relacionamento__model__in=['prestadorservico', 'pessoajuridica']
        )
        self.fields['cnpj_da_seguradora'].widget = BrCnpjWidget()
        if self.instance.cidade:
            self.fields['estado'].initial = self.instance.cidade.estado.pk
        self.fields['nome_supervisor'].help_text = ''
        self.fields['supervisor'].help_text = 'Só preencher este campo se for utilizar a funcionalidade de Documento Eletrônico.'

        if self.instance.pk or not self.instance.eh_concluido():
            # Impede vinculação de servidor inativo a estágios em andamento.
            self.fields['servidor_representante'].queryset = self.fields['servidor_representante'].queryset.ativos()

    def clean_aluno(self):
        aluno = self.cleaned_data.get('aluno')
        estagio_obrigatorio = self.cleaned_data.get('obrigatorio')

        # Situações irregulares
        if not self.instance.pk and aluno.situacao in get_situacoes_irregulares():
            raise forms.ValidationError(f'Aluno com situação {aluno.situacao.descricao} não pode estagiar.')

        # Modalidades permitidas para estágio
        if aluno.curso_campus.modalidade not in Modalidade.objects.filter(id__in=Modalidade.modalidades_que_fazem_estagio()):
            raise forms.ValidationError(
                f'Este aluno é da modalidade {aluno.curso_campus.modalidade.descricao}. '
                'Somente alunos de cursos técnicos, superiores e de pós-graduação podem estagiar.'
            )

        # Verificando se aluno pode estagiar com base na integralização
        pode_estagiar, motivos_negativa = aluno.pode_estagiar(obrigatorio=estagio_obrigatorio)
        if not pode_estagiar:
            raise forms.ValidationError(motivos_negativa)

        return aluno

    def clean_ch_semanal(self):
        aluno = self.cleaned_data.get('aluno')
        ch_semanal = self.cleaned_data.get('ch_semanal')
        if not aluno or not ch_semanal:
            return ch_semanal
        limite_ch_semanal = 30  # limite definido no Art. 10 - Lei nº 11.788/2008

        if ch_semanal > limite_ch_semanal:
            raise forms.ValidationError(f'CH Semanal não pode ser superior a {limite_ch_semanal}h.')

        # Evitando que o aluno exceda a ch semanal max
        ch_semanal_outras = (
            aluno.praticaprofissional_set.filter(data_fim__isnull=True).exclude(pk=self.instance.pk).aggregate(Sum('ch_semanal'))['ch_semanal__sum']
            or 0
        )
        if self.instance.data_fim is None and 'ch_semanal' in self.changed_data and (ch_semanal_outras + ch_semanal) > limite_ch_semanal:
            raise forms.ValidationError(
                f'O aluno já possui outra(s) prática(s) profissional em andamento que totalizam {ch_semanal_outras}h. A soma das cargas horárias semanais ultrapassa o limite de {limite_ch_semanal}h.'
            )
        return ch_semanal

    def clean(self):
        cleaned_data = super().clean()
        #
        estagio_eh_obrigatorio = cleaned_data.get('obrigatorio')
        estagio_eh_remunerado = cleaned_data.get('remunerada')
        estagio_tem_valor = cleaned_data.get('valor') or 0 > 0
        if not estagio_eh_obrigatorio and not estagio_eh_remunerado:
            self._errors['remunerada'] = self.error_class(['Estágio não-obrigatório exige remuneração.'])
            del self.cleaned_data['remunerada']
        elif estagio_eh_remunerado and not estagio_tem_valor:
            self._errors['valor'] = self.error_class(['Estágio remunerado exige o valor da bolsa.'])
            if 'valor' in self.cleaned_data:
                del self.cleaned_data['valor']
        elif not estagio_eh_remunerado and estagio_tem_valor:
            self._errors['remunerada'] = self.error_class(['Para ter bolsa, o estágio deve ser remunerado.'])
            del self.cleaned_data['remunerada']

        # Caso a prática profissional seja do tipo prática profissional efetiva, é obrigatório preencher Documentação
        # Comprobatória.
        tipo = cleaned_data.get('tipo')
        documentacao_comprobatoria = cleaned_data.get('documentacao_comprobatoria')
        if tipo == PraticaProfissional.TIPO_ATIVIDADE_PROFISSIONAL and not documentacao_comprobatoria:
            raise forms.ValidationError(
                {
                    'documentacao_comprobatoria': 'Caso a prática profissional seja do tipo Prática '
                    'Profissional Efetiva, a Documentação Comprobatória '
                    'é obrigatória.'
                }
            )

        return cleaned_data

    def save(self, *args, **kwargs):
        pk = self.instance.pk
        email_supervisor = None
        if pk:
            pratica = PraticaProfissional.objects.filter(pk=pk).first()
            if pratica:
                email_supervisor = pratica.email_supervisor
        retorno = super().save(*args, **kwargs)
        if pk:
            if email_supervisor != self.cleaned_data.get('email_supervisor'):
                self.instance.enviar_email_supervisor_recem_cadastrado(self.request.user)
        else:
            self.instance.enviar_emails_estagio_recem_cadastrado(self.request.user)

        return retorno


class AnexoPraticaProfissionalForm(forms.ModelFormPlus):
    arquivo = forms.FileFieldPlus(label='Arquivo', required=True)
    descricao = forms.CharFieldPlus(label='Descrição', required=True, widget=forms.Textarea())

    class Meta:
        model = AnexoPraticaProfissionalGenerica
        fields = ('arquivo', 'descricao')

    def __init__(self, pratica_profissional, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.instance.pratica_profissional = pratica_profissional
        self.instance.usuario = self.request.user


class AnexoAprendizagemForm(AnexoPraticaProfissionalForm):
    class Meta(AnexoPraticaProfissionalForm.Meta):
        model = AnexoAprendizagem

    def __init__(self, aprendizagem, *args, **kwargs):
        super().__init__(None, *args, **kwargs)
        self.instance.aprendizagem = aprendizagem


class EstagioAditivoContratualForm(forms.ModelFormPlus):
    TIPO_CHOICES = [
        [1, 'Professor Orientador'],
        [2, 'Remuneração'],
        [3, 'Transporte'],
        [4, 'Alimentação'],
        [5, 'Tempo'],
        [6, 'Carga Horária'],
        [7, 'Plano de Atividade'],
        [8, 'Supervisor'],
        [9, 'Horário'],
    ]
    # tipos_aditivo = forms.ModelMultipleChoiceField(TipoAditivo.objects.all(), label=u'Tipo', widget=forms.CheckboxSelectMultiplePlus(), )

    # 1
    orientador = forms.ModelChoiceFieldPlus(Professor.objects, label='Orientador', required=False)
    # 2
    remunerada = forms.BooleanField(label='Remunerada', required=False)
    tipo_remuneracao = forms.ModelChoiceField(TipoRemuneracao.objects.all(), label='Tipo de Remuneração', required=False)
    valor = forms.DecimalFieldPlus(label='Bolsa (R$)', required=False)
    # 3
    auxilio_transporte = forms.DecimalFieldPlus(label='Auxílio Transporte (R$)', required=False)
    # 4
    auxilio_alimentacao = forms.DecimalFieldPlus(label='Outros Benefícios (R$)', required=False)
    descricao_outros_beneficios = forms.CharFieldPlus(
        label='Descrição', required=False, help_text='Descrição de outros benefícios recebidos.', widget=forms.Textarea()
    )
    # 5
    data_prevista_fim = forms.DateFieldPlus(label='Data Prevista para Encerramento', required=False)
    # 6
    ch_semanal = forms.IntegerField(label='C.H. Semanal', required=False)
    # 7
    plano_atividades = forms.FileFieldPlus(
        label='Plano de Atividades', required=False, help_text='Adicionar arquivo no caso o plano de atividades vir separado.'
    )
    lista_atividades = ListCharField(label='Atividades', required=False)
    # 8
    nome_supervisor = forms.CharFieldPlus(label='Nome', required=False)
    telefone_supervisor = forms.CharFieldPlus(label='Telefone', required=False)
    cargo_supervisor = forms.CharFieldPlus(label='Cargo', required=False)
    email_supervisor = forms.EmailField(label='E-mail', required=False)
    observacao = forms.CharFieldPlus(label='Observação', required=False, widget=forms.Textarea())
    # 9
    turno = forms.ModelChoiceField(Turno.objects.all(), label='Turno', required=False)
    # 10
    nome_da_seguradora = forms.CharFieldPlus(label='Nome da Seguradora', required=False)
    numero_seguro = forms.CharFieldPlus(label='Número da Apólice do Seguro', required=False)

    class Meta:
        model = EstagioAditivoContratual
        fields = ('tipos_aditivo', 'descricao', 'aditivo', 'inicio_vigencia')

    class Media:
        js = ('/static/estagios/js/EstagioAditivoContratualForm.js',)

    fieldsets = (
        ('Dados gerais', {'fields': ('tipos_aditivo', ('inicio_vigencia', 'aditivo'), 'descricao')}),
        ('Aditivo de Professor Orientador', {'fields': ('orientador',)}),
        ('Aditivo de Remuneração', {'fields': ('remunerada', ('tipo_remuneracao', 'valor'))}),
        ('Aditivo de Auxílio Transporte', {'fields': ('auxilio_transporte',)}),
        ('Aditivo de Outros Benefícios', {'fields': (('auxilio_alimentacao', 'descricao_outros_beneficios'),)}),
        ('Aditivo de Tempo', {'fields': ('data_prevista_fim',)}),
        ('Aditivo de Carga Horária Semanal', {'fields': ('ch_semanal',)}),
        ('Aditivo de Plano de Atividades', {'fields': ('plano_atividades', 'lista_atividades')}),
        ('Aditivo de Supervisor', {'fields': ('nome_supervisor', 'telefone_supervisor', 'cargo_supervisor', 'email_supervisor', 'observacao')}),
        ('Aditivo de Horário', {'fields': ('turno',)}),
        ('Aditivo de Seguro', {'fields': ('nome_da_seguradora', 'numero_seguro')}),
    )

    #     def clean(self):
    #         #tipos_aditivo = self.cleaned_data['tipos_aditivo']
    #         #fields = self.fieldsets[tipos_aditivo][1]['fields']
    #         for field in fields:
    #             if field != 'observacao':
    #                 if not self.cleaned_data.get(field):
    #                     raise forms.ValidationError(u'Preencha todos os campos do formulário')
    #         return self.cleaned_data

    def __init__(self, pratica_profissional, *args, **kwargs):
        TipoAditivo.objects.get_or_create(id=TipoAditivo.PROFESSOR_ORIENTADOR, descricao='Professor Orientador')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.REMUNERACAO, descricao='Remuneração')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.TRANSPORTE, descricao='Transporte')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.OUTROS_BENEFICIOS, descricao='Outros Benefícios')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.TEMPO, descricao='Tempo')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.CARGA_HORARIA, descricao='Carga Horária')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.PLANO_DE_ATIVIDADE, descricao='Plano de Atividade')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.SUPERVISOR, descricao='Supervisor')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.HORARIO, descricao='Horário')
        TipoAditivo.objects.get_or_create(id=TipoAditivo.SEGURO, descricao='Seguro')

        super().__init__(*args, **kwargs)
        # self.fields['orientador'].queryset = Professor.servidores_docentes.all()
        self.fields['tipos_aditivo'].widget = forms.CheckboxSelectMultiplePlus()
        self.fields['tipos_aditivo'].queryset = TipoAditivo.objects.all()
        ####
        # inicializa a lista de atividades (copia da lista atual)
        lista_atividades_atual = []
        for atividade in pratica_profissional.atividade_set.all():
            lista_atividades_atual.append(f'{atividade.descricao}')
        self.fields['lista_atividades'].initial = lista_atividades_atual
        ####
        self.instance.pratica_profissional = pratica_profissional
        self.fields['inicio_vigencia'].label = 'Início da Vigência'

    def clean(self):
        cleaned_data = super().clean()

        def clean_dict(key):
            try:
                del self.cleaned_data[key]
            except Exception:
                pass

        #
        estagio_eh_obrigatorio = self.instance.pratica_profissional.obrigatorio
        estagio_eh_remunerado = cleaned_data.get('remunerada')
        estagio_tem_valor = cleaned_data.get('valor') or 0 > 0
        if 'tipos_aditivo' not in self.cleaned_data:
            self._errors['tipos_aditivo'] = self.error_class(['Selecione pelo menos um tipo de aditivo contratual.'])
        else:
            if TipoAditivo.objects.get(pk=TipoAditivo.REMUNERACAO) in self.cleaned_data['tipos_aditivo']:
                if not estagio_eh_obrigatorio and not estagio_eh_remunerado:
                    self._errors['remunerada'] = self.error_class(['Estágio não-obrigatório exige remuneração.'])
                    clean_dict('remunerada')
                elif estagio_eh_remunerado and not estagio_tem_valor:
                    self._errors['valor'] = self.error_class(['Estágio remunerado exige o valor da bolsa.'])
                    clean_dict('valor')
                elif not estagio_eh_remunerado and estagio_tem_valor:
                    self._errors['remunerada'] = self.error_class(['Para ter bolsa, o estágio deve ser remunerado.'])
                    clean_dict('remunerada')
            #
            if TipoAditivo.objects.get(pk=TipoAditivo.PROFESSOR_ORIENTADOR) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('orientador'):
                    self._errors['orientador'] = self.error_class(['Deve ser informado o novo professor orientador.'])
                    clean_dict('orientador')
            if TipoAditivo.objects.get(pk=TipoAditivo.TRANSPORTE) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('auxilio_transporte'):
                    self._errors['auxilio_transporte'] = self.error_class(['Deve ser informado o valor do auxílio transporte.'])
                    clean_dict('auxilio_transporte')
            if TipoAditivo.objects.get(pk=TipoAditivo.OUTROS_BENEFICIOS) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('auxilio_alimentacao'):
                    self._errors['auxilio_alimentacao'] = self.error_class(['Deve ser informado o valor dos outros benefícios'])
                    clean_dict('auxilio_alimentacao')
                if not cleaned_data.get('descricao_outros_beneficios'):
                    self._errors['descricao_outros_beneficios'] = self.error_class(['Deve ser informada uma descrição para os outros benefícios'])
                    clean_dict('descricao_outros_beneficios')
            if TipoAditivo.objects.get(pk=TipoAditivo.TEMPO) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('data_prevista_fim'):
                    self._errors['data_prevista_fim'] = self.error_class(['Deve ser informada a nova data prevista para encerramento.'])
                    clean_dict('data_prevista_fim')
            if TipoAditivo.objects.get(pk=TipoAditivo.CARGA_HORARIA) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('ch_semanal'):
                    self._errors['ch_semanal'] = self.error_class(['Deve ser informada a nova carga horária deste estágio.'])
                    clean_dict('ch_semanal')
            if TipoAditivo.objects.get(pk=TipoAditivo.SUPERVISOR) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('nome_supervisor'):
                    self._errors['nome_supervisor'] = self.error_class(['Deve ser informado o nome do novo supervisor deste estágio.'])
                    clean_dict('nome_supervisor')
                if not cleaned_data.get('telefone_supervisor'):
                    self._errors['telefone_supervisor'] = self.error_class(['Deve ser informado o telefone do novo supervisor deste estágio.'])
                    clean_dict('telefone_supervisor')
                if not cleaned_data.get('cargo_supervisor'):
                    self._errors['cargo_supervisor'] = self.error_class(['Deve ser informado o cargo do novo supervisor deste estágio.'])
                    clean_dict('cargo_supervisor')
                if not cleaned_data.get('email_supervisor'):
                    self._errors['email_supervisor'] = self.error_class(['Deve ser informado o e-mail do novo supervisor deste estágio.'])
                    clean_dict('email_supervisor')
            if TipoAditivo.objects.get(pk=TipoAditivo.HORARIO) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('turno'):
                    self._errors['turno'] = self.error_class(['Deve ser informado o novo turno deste estágio.'])
                    clean_dict('turno')
            if TipoAditivo.objects.get(pk=TipoAditivo.SEGURO) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('nome_da_seguradora'):
                    self._errors['nome_da_seguradora'] = self.error_class(['Deve ser informado o nome da seguradora.'])
                    clean_dict('nome_da_seguradora')
                if not cleaned_data.get('numero_seguro'):
                    self._errors['numero_seguro'] = self.error_class(['Deve ser informado o número do seguro.'])
                    clean_dict('numero_seguro')
        return cleaned_data

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        nova_lista_de_atividades_estagio = []
        historico = []
        for key, value in list(self.cleaned_data.items()):
            if key != 'tipos_aditivo':
                ha_value = value
                ha_aditivo_remuneracao = key == 'valor' and ha_value  # attr 'Remunerada' pode vir 'False', devendo ser registrado no histórico
                if (ha_value or ha_aditivo_remuneracao) and (key == 'lista_atividades' or hasattr(self.instance.pratica_profissional, key)):
                    if key == 'lista_atividades':
                        if TipoAditivo.objects.get(pk=TipoAditivo.PLANO_DE_ATIVIDADE) in self.cleaned_data['tipos_aditivo']:
                            anterior = [atividade.descricao for atividade in self.instance.pratica_profissional.atividade_set.all()]
                            nova_lista_de_atividades_estagio = value
                            rotulo = 'Relação de Atividades do Estágio'
                            historico.append(f'{rotulo}: {format_(anterior)} → {format_(value)}')
                    else:
                        anterior = getattr(self.instance.pratica_profissional, key, value)
                        if value and value.__class__ in [InMemoryUploadedFile, TemporaryUploadedFile]:
                            value = value.name
                        setattr(self.instance.pratica_profissional, key, value)
                        if isinstance(anterior, FieldFile):
                            anterior = anterior.name
                        if anterior in [True, False]:
                            anterior = anterior and 'Sim' or 'Não'
                        if value in [True, False]:
                            value = value and 'Sim' or 'Não'
                        rotulo = self.instance.pratica_profissional._meta.get_field(key).verbose_name
                        historico.append(f'{rotulo}: {format_(anterior)} → {format_(value)}')

        self.instance.pratica_profissional.save()
        ##
        if nova_lista_de_atividades_estagio:
            # mescla (pela descrição da atividade) as atividades anteriores com as novas atividades
            atividades_anteriores = [atividade.descricao for atividade in self.instance.pratica_profissional.atividade_set.all()]
            for nova_atividade in nova_lista_de_atividades_estagio:
                if nova_atividade and nova_atividade not in atividades_anteriores:
                    atividade = Atividade()
                    atividade.pratica_profissional = self.instance.pratica_profissional
                    atividade.descricao = f'{nova_atividade}'
                    atividade.save()
            for atividade_antiga in Atividade.objects.filter(pratica_profissional=self.instance.pratica_profissional):
                if atividade_antiga.descricao not in nova_lista_de_atividades_estagio:
                    atividade_antiga.delete()

        ##
        self.instance.historico = '\n'.join(historico)
        self.instance.save()
        if self.instance.tipos_aditivo.filter(pk=TipoAditivo.PROFESSOR_ORIENTADOR).exists():
            send_notification(
                '[SUAP] Nova Orientação de Estágio',
                f'<h1>Nova Orientação de Estágio</h1><p>O estagiário {self.instance.pratica_profissional.aluno} passou a ter uma prática profissional sob sua orientação.</p>',
                settings.DEFAULT_FROM_EMAIL,
                [self.instance.pratica_profissional.orientador.vinculo],
            )

        if self.instance.tipos_aditivo.filter(pk=TipoAditivo.SUPERVISOR).exists():
            send_notification(
                '[SUAP] Novo Supervisor de Estágio',
                f'<h1>Novo Supervisor de Estágio</h1><p>O estagiário {self.instance.pratica_profissional.aluno} passou a ter nova supervisão uma prática profissional sob sua orientação.</p>',
                settings.DEFAULT_FROM_EMAIL,
                [self.instance.pratica_profissional.orientador.vinculo],
            )
            send_notification(
                '[SUAP] Novo Supervisor de Estágio',
                '<h1>Novo Supervisor de Estágio</h1><p>Prezado estagiário, foi cadastrado nova supervisão em sua prática profissional.</p>',
                settings.DEFAULT_FROM_EMAIL,
                [self.instance.pratica_profissional.aluno.get_vinculo()],
            )


class EncerrarPraticaProfissionalForm(forms.ModelFormPlus):
    senha = forms.PasswordField(label='Confirme com a senha')

    class Meta:
        model = PraticaProfissional
        fields = (
            'data_fim',
            'movito_encerramento',
            'motivacao_desligamento_encerramento',
            'ch_final',
            'termo_encerramento',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ch_final'].help_text = self.instance.get_sugestao_ch_final()
        if self.instance.tre_eletronico_foi_cadastrado:
            self.SUBMIT_LABEL = 'Confirmar'
            self.INFO = (
                'Os dados abaixo foram obtidos do Termo de Realização de Estágio cadastrado pelo Supervisor. '
                'Informe sua senha e use o botão "Confirmar" para efetivar o encerramento do Estágio.'
            )
            self.initial['data_fim'] = self.instance.termo_realizacao_eletronico.data_encerramento
            del self.fields['termo_encerramento']
            for campo in [c for c in self.fields if c != 'senha']:
                self.fields[campo].disabled = True
                self.fields[campo].widget.attrs['readonly'] = 'readonly'
        else:
            del self.fields['senha']

        self.fieldsets = self.get_fieldsets()

    def get_fieldsets(self):
        fieldsets = [
            (
                'Dados do Encerramento',
                {'fields': ('movito_encerramento', 'motivacao_desligamento_encerramento', 'data_fim', 'ch_final')},
            ),
        ]
        if self.instance.tre_eletronico_foi_cadastrado:
            fieldsets.append(
                (
                    'Confirmação',
                    {'fields': ('senha',)},
                )
            )
        else:
            fieldsets.append(
                (
                    'Documentação',
                    {'fields': ('termo_encerramento',)},
                ),
            )
        return fieldsets

    def clean(self):
        cleaned_data = super().clean()
        data_encerramento = cleaned_data.get('data_fim', None)

        if data_encerramento:
            movito_encerramento = cleaned_data.get('movito_encerramento', None)

            if movito_encerramento == PraticaProfissional.MOTIVO_CONCLUSAO:
                if data_encerramento != self.instance.data_prevista_fim:
                    raise forms.ValidationError('Data do Encerramento diferente da data prevista para o fim.')

                if self.instance.ha_pendencia_de_visita(data_encerramento):
                    raise forms.ValidationError(
                        'Não é possível encerrar o estágio, pois o professor orientador não cadastrou as visitas de cada trimestre.'
                    )
                if self.instance.ha_pendencia_relatorio_estagiario(data_encerramento):
                    raise forms.ValidationError('Não é possível encerrar o estágio, pois o estagiário não cadastrou todos os relatórios semestrais.')
                if self.instance.ha_pendencia_relatorio_supervisor(data_encerramento):
                    raise forms.ValidationError('Não é possível encerrar o estágio, pois o supervisor não realizou todas as avaliações do estágio.')
            elif movito_encerramento == PraticaProfissional.MOTIVO_RESCISAO:
                primeiro_periodo_trimestral = self.instance.get_periodos_trimestrais()[0]
                encerramento_eh_maior_que_3_meses = data_encerramento > primeiro_periodo_trimestral['fim']
                if encerramento_eh_maior_que_3_meses:
                    if self.instance.ha_pendencia_de_visita(data_encerramento):
                        raise forms.ValidationError('Não é possível encerrar o estágio, pois o professor orientador não cadastrou visita alguma.')
                    if self.instance.ha_pendencia_relatorio_estagiario(data_encerramento):
                        raise forms.ValidationError(
                            'Não é possível encerrar o estágio, pois o estagiário não cadastrou todos os relatórios semestrais.'
                        )
                    if self.instance.ha_pendencia_relatorio_supervisor(data_encerramento):
                        raise forms.ValidationError(
                            'Não é possível encerrar o estágio, pois o supervisor não realizou todas as avaliações do estágio.'
                        )
        return cleaned_data


class CadastrarTermoRealizacaoEstagioForm(forms.ModelFormPlus):
    tipo_encerramento = forms.ChoiceField(label='Encerramento por', choices=[[None, '---------'], *PraticaProfissional.MOTIVO_CHOICES])
    motivo_encerramento = forms.ChoiceField(
        label='Motivo do desligamento/ encerramento', choices=[[None, '---------'], *PraticaProfissional.MOTIVACAO_DESLIGAMENTO_ENCERRAMENTO_CHOICHES]
    )
    observacoes = forms.CharFieldPlus(label='Observações', required=False, max_length=None, widget=forms.Textarea())
    ch_final = forms.IntegerFieldPlus(label='Carga horária final', initial=0)

    field_order = ('tipo_encerramento', 'motivo_encerramento', 'avaliacao_estagiario', 'observacoes', 'data_encerramento', 'ch_final')

    class Meta:
        model = TermoRealizacaoEstagio
        fields = (
            'data_encerramento',
            'avaliacao_estagiario',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ch_final'].help_text = self.instance.pratica_profissional.get_sugestao_ch_final()

        self.fields['tipo_encerramento'].initial = self.instance.pratica_profissional.movito_encerramento
        self.fields['motivo_encerramento'].initial = self.instance.pratica_profissional.motivacao_desligamento_encerramento
        self.fields['observacoes'].initial = self.instance.pratica_profissional.motivo_rescisao
        self.fields['ch_final'].initial = self.instance.pratica_profissional.ch_final

    def clean_data_encerramento(self):
        data_encerramento = self.cleaned_data.get('data_encerramento')
        tipo_encerramento = self.cleaned_data.get('tipo_encerramento')
        data_prevista_fim = self.instance.pratica_profissional.data_prevista_fim
        if tipo_encerramento == str(PraticaProfissional.MOTIVO_CONCLUSAO) and data_encerramento != data_prevista_fim:
            raise forms.ValidationError(
                f'Para encerramentos por conclusão, esta data deve ser igual à data prevista para o fim do estágio ({format_(data_prevista_fim)}).'
            )
        return data_encerramento

    def save(self, commit=True):
        termo = super().save(commit=commit)
        if commit:
            if self.has_changed():
                termo.arquivo_interno.delete()
            PraticaProfissional.objects.filter(pk=termo.pratica_profissional_id).update(
                movito_encerramento=self.cleaned_data['tipo_encerramento'],
                motivacao_desligamento_encerramento=self.cleaned_data['motivo_encerramento'],
                motivo_rescisao=self.cleaned_data['observacoes'],
                ch_final=self.cleaned_data['ch_final'],
            )


class EncerrarEstagioAbandonoMatriculaIrregularForm(forms.ModelFormPlus):
    class Meta:
        model = PraticaProfissional
        fields = (
            'data_fim',
            'movito_encerramento',
            'motivacao_desligamento_encerramento',
            'motivo_rescisao',
            'ch_final',
            'desvinculado_matricula_irregular',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ch_final'].help_text = self.instance.get_sugestao_ch_final()
        self.fields['desvinculado_matricula_irregular'].required = True
        self.fields['motivo_rescisao'].required = True

    fieldsets = (
        (
            'Dados do Encerramento',
            {'fields': ('movito_encerramento', 'motivacao_desligamento_encerramento', 'motivo_rescisao', 'data_fim', 'ch_final')},
        ),
        ('Finalizar sem requisitos por abandono do aluno/matrícula irregular', {'fields': ('desvinculado_matricula_irregular',)}),
    )

    def clean(self):
        cleaned_data = super().clean()
        desvinculado_matricula_irregular = cleaned_data.get('desvinculado_matricula_irregular', None)
        if not desvinculado_matricula_irregular:
            self._errors['desvinculado_matricula_irregular'] = self.error_class(['Necessária confirmação.'])


class RelatorioSemestralEstagioForm(forms.ModelFormPlus):
    periodo = forms.ChoiceField(label='Período', required=True)

    class Meta:
        model = RelatorioSemestralEstagio
        exclude = ('pratica_profissional', 'eh_relatorio_do_supervisor', 'inicio', 'fim', 'ultimo_editor', 'relatorio_interno')

    fieldsets = (('Período e Data do Relatório', {'fields': ('periodo', 'data_relatorio')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pratica_profissional = self.instance.pratica_profissional

        self.atividades = set()
        self.fieldsets += (('Atividades Previstas', {'fields': self.atividades}),)
        self.fieldsets += (
            (
                'Sobre o Plano de Atividades',
                {'fields': ('comentarios_atividades', 'realizou_outras_atividades', 'outras_atividades', 'outras_atividades_justificativa')},
            ),
        )

        if not self.instance.eh_relatorio_do_supervisor:
            self.fieldsets += (('Relação Teoria/Prática', {'fields': ('estagio_na_area_formacao', 'estagio_contribuiu', 'aplicou_conhecimento')}),)
            self.fieldsets += (('Avaliação do Estágio', {'fields': ('avaliacao_conceito',)}),)
            self.fieldsets += (('Comentários e Sugestões', {'fields': ('avaliacao_comentarios',)}),)
            del self.fields['nota_estagiario']
        if self.instance.eh_relatorio_do_supervisor:
            self.fieldsets += (('Avaliação do Desempenho do Estagiário', {'fields': ('nota_estagiario',)}),)

        self.fieldsets += (('Relatório', {'fields': ('relatorio',)}),)

        self.atividades.clear()
        for atividade in pratica_profissional.atividade_set.order_by('pk').all():
            pk = str(atividade.pk)
            field_realizada = f'{pk}.realizada'
            field_motivo = f'{pk}.nao_realizada_motivo'
            field_motivo_descricao = f'{pk}.nao_realizada_motivo_descricao'
            if self.instance.pk and self.instance.relatoriosemestralestagioatividade_set.filter(atividade=atividade).exists():
                avaliacao_atividade = self.instance.relatoriosemestralestagioatividade_set.get(atividade=atividade)
            else:
                avaliacao_atividade = RelatorioSemestralEstagioAtividade()

            self.fields[field_realizada] = forms.ChoiceField(
                label=atividade.descricao,
                choices=[[0, '-------'], *RelatorioSemestralEstagioAtividade.REALIZADA_CHOICES],
                initial=avaliacao_atividade.realizada,
            )
            self.fields[field_motivo] = forms.ChoiceField(
                label='Motivo',
                choices=[[None, '-------'], *RelatorioSemestralEstagioAtividade.NAO_REALIZADA_MOTIVO_CHOICES],
                required=False,
                initial=avaliacao_atividade.nao_realizada_motivo,
                help_text='Em caso de atividade não realizada.',
            )
            self.fields[field_motivo_descricao] = forms.CharFieldPlus(
                label='Descrição de Outro Motivo', initial=avaliacao_atividade.nao_realizada_motivo_descricao, required=False
            )
            #
            self.atividades.add((field_realizada, field_motivo, field_motivo_descricao))

        initial, choices, self.qtd_periodos_validos = self.gerar_lista_periodos()
        self.fields['periodo'].initial = initial
        self.fields['periodo'].choices = choices
        self.qtd_periodos_choices = len(choices) - 1

    def gerar_lista_periodos(self):
        pratica_profissional = self.instance.pratica_profissional
        lista_combo = [[0, '-------']]
        qtd_periodos_validos = 0
        initial = 0
        count = 1
        if self.instance.pk:
            lista_combo += ([count, f'[{format_(self.instance.inicio)} até {format_(self.instance.fim)}]'],)
            initial = 1
            count += 1
        usuario_eh_coordenador = tem_permissao_de_coordenador(self.request.user, campus=pratica_profissional.aluno.campus)
        for periodo in pratica_profissional.get_periodos_semestrais():
            data_inicio_submissao = periodo['inicio'] if usuario_eh_coordenador else PraticaProfissional.data_inicio_submissao_relatorios(periodo)
            if data_inicio_submissao < get_datetime_now().date() and not pratica_profissional.relatorio_do_periodo_ja_foi_submetido(
                periodo, eh_relatorio_do_supervisor=self.instance.eh_relatorio_do_supervisor
            ):
                lista_combo += ([count, '[{} até {}]'.format(format_(periodo['inicio']), format_(periodo['fim']))],)
                qtd_periodos_validos += 1
            count += 1
        return initial, lista_combo, qtd_periodos_validos

    def clean(self):
        cleaned_data = super().clean()

        # verifica se é edição de relatório existente; caso contrário, o campo não é exibido
        if self.instance.pk and self.instance.relatorio:
            tamanho_maximo_permitido = 2 * 1024 * 1024
            relatorio = self.cleaned_data.get('relatorio', None)
            if relatorio and relatorio.size > tamanho_maximo_permitido:
                raise forms.ValidationError({'relatorio': 'Tamanho máximo permitido 2MB.'})
        #
        del_atributos = []
        for atividade in self.instance.pratica_profissional.atividade_set.all():
            key_realizada = f'{atividade.pk}.realizada'
            key_motivo = f'{atividade.pk}.nao_realizada_motivo'
            key_motivo_descricao = f'{atividade.pk}.nao_realizada_motivo_descricao'
            #
            realizada = int(cleaned_data.get(key_realizada))
            try:
                motivo = int(cleaned_data.get(key_motivo))
            except Exception:
                motivo = None
            motivo_descricao = cleaned_data.get(key_motivo_descricao)
            #
            if realizada not in [choice[0] for choice in RelatorioSemestralEstagioAtividade.REALIZADA_CHOICES]:
                self._errors[key_realizada] = self.error_class(['Selecione uma opção válida.'])
                del_atributos.append(key_realizada)
            else:
                is_realizada = realizada == RelatorioSemestralEstagioAtividade.REALIZADA_SIM
                if is_realizada:
                    cleaned_data[key_motivo] = None
                    cleaned_data[key_motivo_descricao] = ''
                else:
                    if motivo not in [choice[0] for choice in RelatorioSemestralEstagioAtividade.NAO_REALIZADA_MOTIVO_CHOICES]:
                        self._errors[key_motivo] = self.error_class(['Selecione uma opção válida.'])
                        del_atributos.append(key_motivo)
                    elif motivo == RelatorioSemestralEstagioAtividade.NAO_REALIZADA_MOTIVO_OUTRO_MOTIVO and not motivo_descricao:
                        self._errors[key_motivo_descricao] = self.error_class(['Descreva o motivo.'])
                        del_atributos.append(key_motivo_descricao)
        for del_atributo in del_atributos:
            del self.cleaned_data[del_atributo]
        if 'periodo' not in self.cleaned_data or self.cleaned_data['periodo'] == '0':
            raise forms.ValidationError({'periodo': 'Selecione um período'})

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        eh_criacao_relatorio = self.instance.pk is None

        if self.instance.pk:
            relatorio_semestral = super().save(commit)

            for atividade in relatorio_semestral.pratica_profissional.atividade_set.all():
                realizada = self.cleaned_data[f'{atividade.pk}.realizada']
                nao_realizada_motivo = self.cleaned_data[f'{atividade.pk}.nao_realizada_motivo']
                nao_realizada_motivo_descricao = self.cleaned_data[f'{atividade.pk}.nao_realizada_motivo_descricao']
                if relatorio_semestral.relatoriosemestralestagioatividade_set.filter(atividade=atividade).exists():
                    avaliacao_da_atividade = self.instance.relatoriosemestralestagioatividade_set.get(atividade=atividade)
                    avaliacao_da_atividade.realizada = realizada
                    avaliacao_da_atividade.nao_realizada_motivo = nao_realizada_motivo
                    avaliacao_da_atividade.nao_realizada_motivo_descricao = nao_realizada_motivo_descricao
                    avaliacao_da_atividade.save()
        else:
            relatorio_semestral = super().save(commit)

            for atividade in relatorio_semestral.pratica_profissional.atividade_set.all():
                realizada = self.cleaned_data[f'{atividade.pk}.realizada']
                nao_realizada_motivo = self.cleaned_data[f'{atividade.pk}.nao_realizada_motivo']
                nao_realizada_motivo_descricao = self.cleaned_data[f'{atividade.pk}.nao_realizada_motivo_descricao']
                avaliacao_da_atividade = RelatorioSemestralEstagioAtividade(
                    relatorio_semestral=relatorio_semestral,
                    atividade=atividade,
                    realizada=realizada,
                    nao_realizada_motivo=nao_realizada_motivo,
                    nao_realizada_motivo_descricao=nao_realizada_motivo_descricao,
                )
                avaliacao_da_atividade.save()

        periodo_selecionado = int(self.cleaned_data['periodo'])
        periodos_semestrais = self.instance.pratica_profissional.get_periodos_semestrais()
        inicio = relatorio_semestral.inicio
        fim = relatorio_semestral.fim
        if eh_criacao_relatorio or self.qtd_periodos_choices > self.qtd_periodos_validos:
            # Se self.qtd_periodos_choices for maior que a quantidade de períodos válidos, provavelmente o relatório
            # possui uma incorreção no cadastro do período.
            # Nesse caso, o select exibirá o período incorreto na 1.ª opção da lista e os períodos válidos em seguida.
            # Logo, count deve iniciar em 2, pois é a partir desse índice que os períodos válidos serão listados.
            count = 2 if self.qtd_periodos_choices > self.qtd_periodos_validos else 1
            for periodo in periodos_semestrais:
                if periodo_selecionado == count:
                    inicio = periodo['inicio']
                    fim = periodo['fim']
                    break
                count += 1
        relatorio_semestral.inicio = inicio
        relatorio_semestral.fim = fim

        if not self.instance.pk or self.has_changed():
            relatorio_semestral.resetar_relatorio_eletronico()
            tasks.notificar_pendencia_assinatura_relatorio_semestral_estagio(relatorio_semestral)
        #
        relatorio_semestral.save()
        relatorio_semestral.pratica_profissional.save()
        #
        return relatorio_semestral


class RelatorioSemestralPreenchidoSupervisorForm(RelatorioSemestralEstagioForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fieldsets = ('Identificação do Aluno', {'fields': ('tipo', 'matricula_aluno', 'codigo_verificador')}), +self.fieldsets


class OfertaPraticaProfissionalForm(forms.ModelFormPlus):
    uo = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.suap().all(), label='Campus', required=False)
    cursos = forms.MultipleModelChoiceField(
        CursoCampus.objects,
        label='Cursos Alvo da Oferta',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
    )

    class Meta:
        model = OfertaPraticaProfissional
        fields = (
            'concedente',
            'data_inicio',
            'data_fim',
            'qtd_vagas',
            'uo',
            'cursos',
            'a_partir_do_periodo',
            'turno',
            'ch_semanal',
            'folder',
            'habilidades',
            'descricao_atividades',
            'observacoes',
        )

    fieldsets = (
        ('Dados gerais', {'fields': ('concedente', 'data_inicio', 'data_fim')}),
        ('Direcionamento da Oferta', {'fields': ('tipo_oferta', 'qtd_vagas', 'uo', 'cursos', 'a_partir_do_periodo', 'turno')}),
        ('Carga Horária', {'fields': ('ch_semanal',)}),
        ('Outras Informações', {'fields': ('folder', 'habilidades', 'descricao_atividades', 'observacoes')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = self.fields['cursos'].queryset
        qs = qs.filter(modalidade__in=Modalidade.modalidades_que_fazem_estagio(), ativo=True).distinct()
        self.fields['cursos'].queryset = qs


class VisitaPraticaProfissionalForm(forms.ModelFormPlus):
    class Meta:
        model = VisitaPraticaProfissional
        exclude = ('pratica_profissional', 'orientador', 'ultimo_editor', 'relatorio')

    fieldsets = (
        ('Dados gerais', {'fields': ('data_visita',)}),
        (
            'Parecer da Visita',
            {
                'fields': (
                    ('ambiente_adequado', 'ambiente_adequado_justifique'),  # a)  # a)justifique
                    'desenvolvendo_atividades_previstas',  # b)
                    'desenvolvendo_atividades_fora_competencia',  # c)
                    ('desenvolvendo_atividades_nao_previstas', 'atividades_nao_previstas'),  # d)  # d descricao
                    'apoiado_pelo_supervidor',  # e)
                    ('direitos_respeitados', 'direitos_respeitados_especificar'),  # f)
                    'aprendizagem_satisfatoria',  # g)
                    'informacoes_adicionais',
                )  # sem letra
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'data_visita'
        ].help_text = f'O estágio tem {self.instance.pratica_profissional.get_qtd_trimestres()} períodos trimestrais e deve ser submetido um relatório para cada período. Períodos: <br>'
        count = 1
        for trimestre in self.instance.pratica_profissional.get_periodos_trimestrais():
            visitas = self.instance.pratica_profissional.visitapraticaprofissional_set.filter(
                data_visita__range=(trimestre['inicio'], trimestre['fim'])
            )
            self.fields['data_visita'].help_text = self.fields['data_visita'].help_text + '{}º De {} até {}. Visitas já cadastradas: {}\n'.format(
                count,
                format_(trimestre['inicio']),
                format_(trimestre['fim']),
                visitas.exists() and (', '.join([str(i) for i in visitas])) or 'Nenhuma visita neste período.',
            )
            count += 1
        self.fields['data_visita'].help_text = '<pre>' + self.fields['data_visita'].help_text + '</pre>'

    def clean(self):
        super().clean()
        desenvolvendo_atividades_nao_previstas = self.cleaned_data.get('desenvolvendo_atividades_nao_previstas')
        if desenvolvendo_atividades_nao_previstas is True and not self.cleaned_data.get('atividades_nao_previstas'):
            raise forms.ValidationError(
                {
                    'atividades_nao_previstas': 'Foi marcado que o estagiário está desenvolvendo '
                    'Atividades Não Previstas, neste caso estas '
                    'devem ser especificadas.'
                }
            )
        if self.cleaned_data.get('data_visita') and self.cleaned_data.get('data_visita') > datetime.date.today():
            raise forms.ValidationError({'data_visita': 'Data no futuro: somente devem ser registradas visitas já ocorridas.'})
        if (
            self.cleaned_data.get('data_visita')
            and not self.instance.pratica_profissional.data_inicio
            <= self.cleaned_data.get('data_visita')
            <= self.instance.pratica_profissional.data_prevista_fim
        ):
            raise forms.ValidationError(
                {'data_visita': 'Data não compreendida no intervalo da data de início à data prevista para o fim deste estágio.'}
            )
        return self.cleaned_data


class VisitaAprendizagemForm(forms.ModelFormPlus):
    class Meta:
        model = VisitaAprendizagem
        exclude = ('aprendizagem', 'modulo_aprendizagem', 'orientador', 'ultimo_editor', 'relatorio')

    fieldsets = (
        ('Dados gerais', {'fields': ('data_visita',)}),
        (
            'Parecer da Visita',
            {
                'fields': (
                    ('ambiente_adequado', 'ambiente_adequado_justifique'),  # a)  # a)justifique
                    'desenvolvendo_atividades_previstas',  # b)
                    'desenvolvendo_atividades_fora_competencia',  # c)
                    ('desenvolvendo_atividades_nao_previstas', 'atividades_nao_previstas'),  # d)  # d descricao
                    'apoiado_pelo_supervidor',  # e)
                    ('direitos_respeitados', 'direitos_respeitados_especificar'),  # f)
                    'aprendizagem_satisfatoria',  # g)
                    'informacoes_adicionais',
                )  # sem letra
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # garante nomenclatura correta nos help texts (quanto ao uso de módulo/semestre)
        nomenclatura_periodo = self.instance.aprendizagem.nomenclatura_periodo
        self.fields['desenvolvendo_atividades_previstas'].help_text = self.fields['desenvolvendo_atividades_previstas'].help_text.replace(
            'módulo', nomenclatura_periodo.lower()
        )
        self.fields['desenvolvendo_atividades_nao_previstas'].help_text = self.fields['desenvolvendo_atividades_nao_previstas'].help_text.replace(
            'módulo', nomenclatura_periodo.lower()
        )

    def clean(self):
        cleaned_data = super().clean()
        if 'data_visita' not in cleaned_data:
            raise forms.ValidationError({'data_visita': 'Informe a data da visita.'})
        if self.cleaned_data.get('data_visita') and self.cleaned_data.get('data_visita') > datetime.date.today():
            raise forms.ValidationError({'data_visita': 'Data no futuro: somente devem ser registradas visitas já ocorridas.'})
        if not self.instance.aprendizagem.moduloaprendizagem_set.filter(
            inicio__lte=cleaned_data.get('data_visita'), fim__gte=cleaned_data.get('data_visita')
        ).exists():
            raise forms.ValidationError(
                {'data_visita': 'A data da visita deve estar compreendida entre a data de início e a de fim de algum dos módulos.'}
            )
        desenvolvendo_atividades_nao_previstas = self.cleaned_data.get('desenvolvendo_atividades_nao_previstas')
        if desenvolvendo_atividades_nao_previstas is True and not self.cleaned_data.get('atividades_nao_previstas'):
            raise forms.ValidationError(
                {
                    'atividades_nao_previstas': 'Foi marcado que o estagiário está desenvolvendo '
                    'Atividades Não Previstas, neste caso estas '
                    'devem ser especificadas.'
                }
            )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        self.instance.ultimo_editor = self.request.user
        return super().save(*args, **kwargs)


class AvaliarRelatorioSemestralForm(forms.ModelFormPlus):
    class Meta:
        model = RelatorioSemestralEstagio
        fields = ('inicio', 'fim')


class OrientacaoEstagioForm(forms.ModelFormPlus):
    class Meta:
        model = OrientacaoEstagio
        exclude = ('pratica_profissional', 'orientador')

    def __init__(self, pratica_profissional, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.pratica_profissional = pratica_profissional
        self.instance.orientador = pratica_profissional.orientador
        self.instance.user = self.request.user


class OrientacaoAtividadeProfissionalEfetivaForm(forms.ModelFormPlus):
    class Meta:
        model = OrientacaoAtividadeProfissionalEfetiva
        exclude = ('atividade_profissional_efetiva', 'orientador')

    def __init__(self, atividade_profissional_efetiva, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.atividade_profissional_efetiva = atividade_profissional_efetiva
        self.instance.orientador = atividade_profissional_efetiva.orientador
        self.instance.user = self.request.user


class OrientacaoAprendizagemForm(forms.ModelFormPlus):
    class Meta:
        model = OrientacaoAprendizagem
        exclude = ('aprendizagem', 'orientador')

    def __init__(self, aprendizagem, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.aprendizagem = aprendizagem
        self.instance.orientador = aprendizagem.orientador
        self.instance.user = self.request.user


class EncontrarEstagioForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    email_supervisor = forms.EmailField(label='E-mail do Supervisor', required=True)
    codigo_verificador = forms.CharFieldPlus(label='Código Verificador', min_length=6)
    matricula = forms.CharFieldPlus(label='Matrícula do Aluno')
    recaptcha = ReCaptchaField(label='')

    def get_lookups(self):
        """
        Retorna os filtros para encontrar o estágio, permitindo chamadas como:
            `PraticaProfissional.objects.filter(**form.get_lookups())`

        É preciso chamar o form.is_valid() antes de usar este método.
        """
        return {
            'email_supervisor': self.cleaned_data['email_supervisor'],
            'codigo_verificador__startswith': self.cleaned_data['codigo_verificador'],
            'aluno__matricula': self.cleaned_data['matricula'],
        }


class EncontrarAprendizagemForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    email_monitor = forms.EmailField(label='E-mail do Monitor', required=True)
    codigo_verificador = forms.CharFieldPlus(label='Código Verificador', min_length=6)
    matricula = forms.CharFieldPlus(label='Matrícula do Aluno')
    inicio = forms.DateFieldPlus(label='Data de Início do Módulo Avaliado')
    fim = forms.DateFieldPlus(label='Data de Fim do Módulo Avaliado')
    recaptcha = ReCaptchaField(label='')

    def get_lookups(self):
        """
        Retorna os filtros para encontrar a aprendizagem, permitindo chamadas como:
            `Aprendizagem.objects.filter(**form.get_lookups())`

        É preciso chamar o form.is_valid() antes de usar este método.
        """
        return {
            'aprendizagem__email_monitor': self.cleaned_data['email_monitor'],
            'aprendizagem__codigo_verificador__startswith': self.cleaned_data['codigo_verificador'],
            'aprendizagem__aprendiz__matricula': self.cleaned_data['matricula'],
            'inicio': self.cleaned_data['inicio'],
            'fim': self.cleaned_data['fim'],
        }


class EscolhaTipoContratoAprendizagemFormMixin:
    ACAO_ANEXAR_ARQUIVO = 'anexar_arquivo'
    ACAO_VINCULAR_DOC_ELETRONICO = 'vincular_doc_eletronico'
    ACAO_CRIAR_DOC_ELETRONICO = 'criar_doc_eletronico'
    ACAO_CONTRATO_CHOICES = (
        (ACAO_ANEXAR_ARQUIVO, 'Anexar arquivo digitalizado'),
        (ACAO_VINCULAR_DOC_ELETRONICO, 'Vincular Documento Eletrônico'),
        (ACAO_CRIAR_DOC_ELETRONICO, 'Criar Documento Eletrônico'),
    )

    MEDIA_JS = ('/static/estagios/js/EditarContratoAprendizagemForm.js',)

    @classmethod
    def get_field_estrategia_adicao_contrato(cls, permitir_criar_documento_eletronico=True):
        return forms.ChoiceField(
            label='Escolha como você quer adicionar o contrato',
            choices=cls.ACAO_CONTRATO_CHOICES if permitir_criar_documento_eletronico else cls.ACAO_CONTRATO_CHOICES[:-1],
            required=True,
            initial=cls.ACAO_ANEXAR_ARQUIVO,
            widget=forms.RadioSelect,
            help_text='Você pode adicionar o contrato como um arquivo digitalizado ou como um documento eletrônico.',
        )

    def configurar_campos_contrato(self):
        self.fields['contrato_aprendizagem_documento_eletronico'].queryset = self.fields[
            'contrato_aprendizagem_documento_eletronico'
        ].queryset.finalizados()

        if self.instance.pk and self.instance.contrato_aprendizagem_documento_eletronico:
            self.fields['estrategia_adicao_contrato'].initial = self.ACAO_VINCULAR_DOC_ELETRONICO
            self.fields['contrato_aprendizagem_documento_eletronico'].queryset = self.fields[
                'contrato_aprendizagem_documento_eletronico'
            ].queryset | self.fields['contrato_aprendizagem_documento_eletronico'].queryset.filter(
                pk=self.instance.contrato_aprendizagem_documento_eletronico.id
            )

        self.order_fields(['estrategia_adicao_contrato', 'contrato_aprendizagem', 'contrato_aprendizagem_documento_eletronico'])

    def get_cleaned_estrategia_adicao_contrato(self):
        return self.cleaned_data.get('estrategia_adicao_contrato')

    def clean_monitor(self):
        monitor = self.cleaned_data.get('monitor')
        if self.get_cleaned_estrategia_adicao_contrato() not in (None, self.ACAO_ANEXAR_ARQUIVO):
            if not monitor:
                raise forms.ValidationError('Este campo é obrigatório quando o contrato for um documento eletrônico.')
        return monitor

    def clean_estrategia_adicao_contrato(self):
        estrategia_adicao_contrato = self.get_cleaned_estrategia_adicao_contrato()
        if estrategia_adicao_contrato == self.ACAO_CRIAR_DOC_ELETRONICO:
            if not ModeloDocumento.objects.only('nome').filter(nome='Contrato de Aprendizagem').exists():
                raise forms.ValidationError(
                    'Para criar o documento, é necessário existir um modelo com nome "Contrato de Aprendizagem" no módulo de Documento Eletrônico.'
                )
        return estrategia_adicao_contrato

    def clean_contrato_aprendizagem(self):
        if self.get_cleaned_estrategia_adicao_contrato() == self.ACAO_ANEXAR_ARQUIVO:
            contrato_aprendizagem = self.cleaned_data.get('contrato_aprendizagem')
            if not contrato_aprendizagem:
                raise forms.ValidationError('Este campo é obrigatório.')
            return contrato_aprendizagem
        return None

    def clean_contrato_aprendizagem_documento_eletronico(self):
        if self.get_cleaned_estrategia_adicao_contrato() == self.ACAO_VINCULAR_DOC_ELETRONICO:
            contrato_aprendizagem_documento_eletronico = self.cleaned_data.get('contrato_aprendizagem_documento_eletronico')
            if not contrato_aprendizagem_documento_eletronico:
                raise forms.ValidationError('Este campo é obrigatório.')
            return contrato_aprendizagem_documento_eletronico
        return None

    def _tratar_estrategia_adicao_contrato_pre_save(self):
        estrategia_adicao_contrato = self.get_cleaned_estrategia_adicao_contrato()
        arquivo_a_remover = None
        if estrategia_adicao_contrato == self.ACAO_ANEXAR_ARQUIVO:
            self.instance.contrato_aprendizagem_documento_eletronico = None
        else:
            arquivo_a_remover = self.instance.contrato_aprendizagem
            self.instance.contrato_aprendizagem = None

        deve_criar_doc_eletronico_do_contrato = estrategia_adicao_contrato == self.ACAO_CRIAR_DOC_ELETRONICO

        return arquivo_a_remover, deve_criar_doc_eletronico_do_contrato


class AprendizagemForm(forms.ModelFormPlus, EscolhaTipoContratoAprendizagemFormMixin):
    vinculo = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.servidores_docentes(),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        label='Orientador',
        required=True,
    )
    estado = forms.ModelChoiceField(queryset=Estado.objects, label='Unidade da Federação', widget=Select())
    cidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Município',
        required=True,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS, form_filters=[('estado', 'estado__in')]),
    )

    confirmacao_aprendizagem_eh_remunerada = forms.BooleanField(
        label='Senhor Coordenador de Estágio favor confirmar que esta aprendizagem é remunerada.',
        help_text='A aprendizagem sempre é remunerada por exigência legal, se esta não tem remuneração, o '
        'problema deve ser sanado antes de ser feito o cadastro.',
    )

    estrategia_adicao_contrato = EscolhaTipoContratoAprendizagemFormMixin.get_field_estrategia_adicao_contrato()

    descricao_atividades_1 = forms.CharField(
        label='Descrição das Atividades do Módulo',
        required=False,
        widget=forms.Textarea(),
        help_text='Estas atividades serão utilizadas para as avaliações do módulo.',
    )
    data_inicio_1 = forms.DateFieldPlus(label='Data de Início do Módulo', required=False)
    data_fim_1 = forms.DateFieldPlus(label='Data de Fim do Módulo', required=False)
    ch_teorica_semanal_1 = forms.IntegerFieldPlus(label='Carga Horária Teórica Semanal', required=False)
    ch_pratica_semanal_1 = forms.IntegerFieldPlus(label='Carga Horária Prática Semanal', required=False)

    descricao_atividades_2 = forms.CharField(
        label='Descrição das Atividades do Módulo',
        required=False,
        widget=forms.Textarea(),
        help_text='Estas atividades serão utilizadas para as avaliações do módulo.',
    )
    data_inicio_2 = forms.DateFieldPlus(label='Data de Início do Módulo', required=False)
    data_fim_2 = forms.DateFieldPlus(label='Data de Fim do Módulo', required=False)
    ch_teorica_semanal_2 = forms.IntegerFieldPlus(label='Carga Horária Teórica Semanal', required=False)
    ch_pratica_semanal_2 = forms.IntegerFieldPlus(label='Carga Horária Prática Semanal', required=False)

    descricao_atividades_3 = forms.CharField(
        label='Descrição das Atividades do Módulo',
        required=False,
        widget=forms.Textarea(),
        help_text='Estas atividades serão utilizadas para as avaliações do módulo.',
    )
    data_inicio_3 = forms.DateFieldPlus(label='Data de Início do Módulo', required=False)
    data_fim_3 = forms.DateFieldPlus(label='Data de Fim do Módulo', required=False)
    ch_teorica_semanal_3 = forms.IntegerFieldPlus(label='Carga Horária Teórica Semanal', required=False)
    ch_pratica_semanal_3 = forms.IntegerFieldPlus(label='Carga Horária Prática Semanal', required=False)

    descricao_atividades_4 = forms.CharField(
        label='Descrição das Atividades do Módulo',
        required=False,
        widget=forms.Textarea(),
        help_text='Estas atividades serão utilizadas para as avaliações do módulo.',
    )
    data_inicio_4 = forms.DateFieldPlus(label='Data de Início do Módulo', required=False)
    data_fim_4 = forms.DateFieldPlus(label='Data de Fim do Módulo', required=False)
    ch_teorica_semanal_4 = forms.IntegerFieldPlus(label='Carga Horária Teórica Semanal', required=False)
    ch_pratica_semanal_4 = forms.IntegerFieldPlus(label='Carga Horária Prática Semanal', required=False)

    class Meta:
        model = Aprendizagem
        exclude = (
            'data_encerramento',
            'encerramento_por',
            'motivo_encerramento',
            'motivacao_rescisao',
            'ch_final',
            'laudo_avaliacao',
            'orientador',
            'eh_utilizado_como_pratica_profissional',
            'plano_atividades',
        )

    class Media:
        js = ('/static/estagios/js/AprendizagemForm.js', *EscolhaTipoContratoAprendizagemFormMixin.MEDIA_JS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_campos_contrato()

        self.fields['aprendiz'].widget = AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS)
        self.fields['convenio'].widget = AutocompleteWidget(search_fields=Convenio.SEARCH_FIELDS)
        self.fields['convenio'].queryset = self.fields['convenio'].queryset.all()
        self.fields['empresa'].widget = AutocompleteWidget(search_fields=PessoaJuridica.SEARCH_FIELDS)
        self.fields['empresa'].queryset = self.fields['empresa'].queryset.all()
        self.fields['monitor'].queryset = self.fields['monitor'].queryset.funcionarios().ativos()

        campos_booleanos_cnap = (
            'eh_contratacao_direta',
            'eh_modalidade_alternativa_de_cumprimento_de_cota',
            'o_estabelecimento_eh_de_prestacao_de_servico_a_terceiros',
            'aprendiz_contratado_mediante_centralizacao_de_cota',
        )

        for campo in campos_booleanos_cnap:
            self.fields[campo].required = True
            if not self.instance.pk:
                self.fields[campo].initial = campo == 'eh_contratacao_direta'

        if self.instance.pk and self.instance.orientador:
            try:
                self.fields['vinculo'].initial = self.instance.orientador.vinculo
            except Exception:
                pass

        if in_group(self.request.user, ['Coordenador de Estágio']) and not in_group(
            self.request.user, ['Coordenador de Estágio Sistêmico', 'estagios Administrador']
        ):
            self.fields['aprendiz'].queryset = self.fields['aprendiz'].queryset.filter(
                matriz__isnull=False, curso_campus__diretoria__setor__uo=get_uo(self.request.user)
            )
        else:
            self.fields['aprendiz'].queryset = self.fields['aprendiz'].queryset.filter(matriz__isnull=False)

        if self.instance.pk and self.instance.cidade:
            self.fields['estado'].initial = self.instance.cidade.estado

        if self.instance.pk:
            self.fields['confirmacao_aprendizagem_eh_remunerada'].initial = True

        if Aprendizagem.cadastra_modulos_manualmente(self.instance):
            if self.instance.modulo_1:
                modulo_1 = self.instance.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_I)[0]
                self.fields['descricao_atividades_1'].initial = modulo_1.atividades
                self.fields['data_inicio_1'].initial = modulo_1.inicio
                self.fields['data_fim_1'].initial = modulo_1.fim
                self.fields['ch_teorica_semanal_1'].initial = modulo_1.ch_teorica_semanal
                self.fields['ch_pratica_semanal_1'].initial = modulo_1.ch_pratica_semanal
            if self.instance.modulo_2:
                modulo_2 = self.instance.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_II)[0]
                self.fields['descricao_atividades_2'].initial = modulo_2.atividades
                self.fields['data_inicio_2'].initial = modulo_2.inicio
                self.fields['data_fim_2'].initial = modulo_2.fim
                self.fields['ch_teorica_semanal_2'].initial = modulo_2.ch_teorica_semanal
                self.fields['ch_pratica_semanal_2'].initial = modulo_2.ch_pratica_semanal
            if self.instance.modulo_3:
                modulo_3 = self.instance.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_III)[0]
                self.fields['descricao_atividades_3'].initial = modulo_3.atividades
                self.fields['data_inicio_3'].initial = modulo_3.inicio
                self.fields['data_fim_3'].initial = modulo_3.fim
                self.fields['ch_teorica_semanal_3'].initial = modulo_3.ch_teorica_semanal
                self.fields['ch_pratica_semanal_3'].initial = modulo_3.ch_pratica_semanal
            if self.instance.modulo_4:
                modulo_4 = self.instance.moduloaprendizagem_set.filter(tipo_modulo=ModuloAprendizagem.MODULO_IV)[0]
                self.fields['descricao_atividades_4'].initial = modulo_4.atividades
                self.fields['data_inicio_4'].initial = modulo_4.inicio
                self.fields['data_fim_4'].initial = modulo_4.fim
                self.fields['ch_teorica_semanal_4'].initial = modulo_4.ch_teorica_semanal
                self.fields['ch_pratica_semanal_4'].initial = modulo_4.ch_pratica_semanal

    def clean(self):
        cleaned_data = super().clean()

        del_atributos = []

        if (
            Aprendizagem.cadastra_modulos_manualmente(self.instance)
            and not cleaned_data.get('modulo_1', None)
            and not cleaned_data.get('modulo_2', None)
            and not cleaned_data.get('modulo_3', None)
            and not cleaned_data.get('modulo_4', None)
        ):
            raise forms.ValidationError('Deve ser cadastrado pelo menos um módulo para a aprendizagem.')

        if cleaned_data.get('modulo_1', None):
            if not cleaned_data.get('descricao_atividades_1', None):
                self._errors['descricao_atividades_1'] = self.error_class(['É necessária uma descrição.'])
                del_atributos.append('descricao_atividades_1')
            if not cleaned_data.get('data_inicio_1', None):
                self._errors['data_inicio_1'] = self.error_class(['É necessária uma data de início.'])
                del_atributos.append('data_inicio_1')
            if not cleaned_data.get('data_fim_1', None):
                self._errors['data_fim_1'] = self.error_class(['É necessária uma data de fim.'])
                del_atributos.append('data_fim_1')
            if not cleaned_data.get('ch_teorica_semanal_1', None):
                self._errors['ch_teorica_semanal_1'] = self.error_class(['É necessária uma carga horária teórica semanal.'])
                del_atributos.append('ch_teorica_semanal_1')
            if not cleaned_data.get('ch_pratica_semanal_1', None):
                self._errors['ch_pratica_semanal_1'] = self.error_class(['É necessária uma carga horária prática semanal.'])
                del_atributos.append('ch_pratica_semanal_1')

        if cleaned_data.get('modulo_2', None):
            if not cleaned_data.get('descricao_atividades_2', None):
                self._errors['descricao_atividades_2'] = self.error_class(['É necessária uma descrição.'])
                del_atributos.append('descricao_atividades_2')
            if not cleaned_data.get('data_inicio_2', None):
                self._errors['data_inicio_2'] = self.error_class(['É necessária uma data de início.'])
                del_atributos.append('data_inicio_2')
            if not cleaned_data.get('data_fim_2', None):
                self._errors['data_fim_2'] = self.error_class(['É necessária uma data de fim.'])
                del_atributos.append('data_fim_2')
            if not cleaned_data.get('ch_teorica_semanal_2', None):
                self._errors['ch_teorica_semanal_2'] = self.error_class(['É necessária uma carga horária teórica semanal.'])
                del_atributos.append('ch_teorica_semanal_2')
            if not cleaned_data.get('ch_pratica_semanal_2', None):
                self._errors['ch_pratica_semanal_2'] = self.error_class(['É necessária uma carga horária prática semanal.'])
                del_atributos.append('ch_pratica_semanal_2')

        if cleaned_data.get('modulo_3', None):
            if not cleaned_data.get('descricao_atividades_3', None):
                self._errors['descricao_atividades_3'] = self.error_class(['É necessária uma descrição.'])
                del_atributos.append('descricao_atividades_3')
            if not cleaned_data.get('data_inicio_3', None):
                self._errors['data_inicio_3'] = self.error_class(['É necessária uma data de início.'])
                del_atributos.append('data_inicio_3')
            if not cleaned_data.get('data_fim_3', None):
                self._errors['data_fim_3'] = self.error_class(['É necessária uma data de fim.'])
                del_atributos.append('data_fim_3')
            if not cleaned_data.get('ch_teorica_semanal_3', None):
                self._errors['ch_teorica_semanal_3'] = self.error_class(['É necessária uma carga horária teórica semanal.'])
                del_atributos.append('ch_teorica_semanal_3')
            if not cleaned_data.get('ch_pratica_semanal_3', None):
                self._errors['ch_pratica_semanal_3'] = self.error_class(['É necessária uma carga horária prática semanal.'])
                del_atributos.append('ch_pratica_semanal_3')

        if cleaned_data.get('modulo_4', None):
            if not cleaned_data.get('descricao_atividades_4', None):
                self._errors['descricao_atividades_4'] = self.error_class(['É necessária uma descrição.'])
                del_atributos.append('descricao_atividades_4')
            if not cleaned_data.get('data_inicio_4', None):
                self._errors['data_inicio_4'] = self.error_class(['É necessária uma data de início.'])
                del_atributos.append('data_inicio_4')
            if not cleaned_data.get('data_fim_4', None):
                self._errors['data_fim_4'] = self.error_class(['É necessária uma data de fim.'])
                del_atributos.append('data_fim_4')
            if not cleaned_data.get('ch_teorica_semanal_4', None):
                self._errors['ch_teorica_semanal_4'] = self.error_class(['É necessária uma carga horária teórica semanal.'])
                del_atributos.append('ch_teorica_semanal_4')
            if not cleaned_data.get('ch_pratica_semanal_4', None):
                self._errors['ch_pratica_semanal_4'] = self.error_class(['É necessária uma carga horária prática semanal.'])
                del_atributos.append('ch_pratica_semanal_4')

        datas = []
        if cleaned_data.get('modulo_1', None):
            if cleaned_data.get('data_inicio_1', None):
                datas.append(cleaned_data.get('data_inicio_1', None))
            if cleaned_data.get('data_fim_1', None):
                datas.append(cleaned_data.get('data_fim_1', None))
                if cleaned_data.get('data_inicio_1', None) and cleaned_data.get('data_inicio_1', None) >= cleaned_data.get('data_fim_1', None):
                    raise forms.ValidationError({'data_inicio_1': 'A data de início deve ser menor que a data de fim do módulo.'})
        if cleaned_data.get('modulo_2', None):
            if cleaned_data.get('data_inicio_2', None):
                datas.append(cleaned_data.get('data_inicio_2', None))
            if cleaned_data.get('data_fim_2', None):
                datas.append(cleaned_data.get('data_fim_2', None))
                if cleaned_data.get('data_inicio_2', None) and cleaned_data.get('data_inicio_2', None) >= cleaned_data.get('data_fim_2', None):
                    raise forms.ValidationError({'data_inicio_2': 'A data de início deve ser menor que a data de fim do módulo.'})
        if cleaned_data.get('modulo_3', None):
            if cleaned_data.get('data_inicio_3', None):
                datas.append(cleaned_data.get('data_inicio_3', None))
            if cleaned_data.get('data_fim_3', None):
                datas.append(cleaned_data.get('data_fim_3', None))
                if cleaned_data.get('data_inicio_3', None) and cleaned_data.get('data_inicio_3', None) >= cleaned_data.get('data_fim_3', None):
                    raise forms.ValidationError({'data_inicio_3': 'A data de início deve ser menor que a data de fim do módulo.'})
        if cleaned_data.get('modulo_4', None):
            if cleaned_data.get('data_inicio_4', None):
                datas.append(cleaned_data.get('data_inicio_4', None))
            if cleaned_data.get('data_fim_4', None):
                datas.append(cleaned_data.get('data_fim_4', None))
                if cleaned_data.get('data_inicio_4', None) and cleaned_data.get('data_inicio_4', None) >= cleaned_data.get('data_fim_4', None):
                    raise forms.ValidationError({'data_inicio_4': 'A data de início deve ser menor que a data de fim do módulo.'})

        data_anterior = datetime.date.today() - relativedelta(years=100)
        for data in datas:
            if data > data_anterior:
                data_anterior = data
            else:
                raise forms.ValidationError(
                    'Datas inconsistentes. A data de início de cada módulo deve ser '
                    'menor que a data de fim. A data de início de módulos numericamente '
                    'maiores deve ser maior que a data de fim dos módulos anteriores.'
                )

        for del_atributo in del_atributos:
            if self.cleaned_data.get(del_atributo):
                del self.cleaned_data[del_atributo]

        data_inicio = self.cleaned_data.get('data_inicio')
        data_prevista_encerramento = self.cleaned_data.get('data_prevista_encerramento')
        if data_inicio and data_prevista_encerramento:
            if data_inicio >= data_prevista_encerramento:
                raise forms.ValidationError(
                    {'data_prevista_encerramento': 'A data de previsão de encerramento precisa ser posterior à data de início.'}
                )
            if data_prevista_encerramento > data_inicio + relativedelta(years=2) - datetime.timedelta(days=1):
                raise forms.ValidationError(
                    {
                        'data_inicio': 'A duração da aprendizagem não pode exceder 4 semestres.',
                        'data_prevista_encerramento': 'A duração da aprendizagem não pode exceder 4 semestres.',
                    }
                )

        # verificação dos campos de Configuração para Envio de Relatório de Frequência
        periodicidade_envio_relatorio_frequencia = self.cleaned_data.get('periodicidade_envio_relatorio_frequencia')
        inicio_periodo_frequencia_1 = self.cleaned_data.get('inicio_periodo_frequencia_1')
        fim_periodo_frequencia_1 = self.cleaned_data.get('fim_periodo_frequencia_1')
        inicio_periodo_frequencia_2 = self.cleaned_data.get('inicio_periodo_frequencia_2')
        fim_periodo_frequencia_2 = self.cleaned_data.get('fim_periodo_frequencia_2')
        emails_relatorio_frequencia = self.cleaned_data.get('emails_relatorio_frequencia')
        del_atributos = []
        if periodicidade_envio_relatorio_frequencia is None:
            if inicio_periodo_frequencia_1 or fim_periodo_frequencia_1 or inicio_periodo_frequencia_2 or fim_periodo_frequencia_2:
                self._errors['periodicidade_envio_relatorio_frequencia'] = self.error_class(
                    ['Só é possível definir período de apuração de frequência se a periodicidade de envio também estiver definida.']
                )
                del_atributos.append('periodicidade_envio_relatorio_frequencia')
        elif periodicidade_envio_relatorio_frequencia == Aprendizagem.MENSAL:
            if not inicio_periodo_frequencia_1:
                self._errors['inicio_periodo_frequencia_1'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é mensal, é necessário preencher este campo.']
                )
                del_atributos.append('inicio_periodo_frequencia_1')
            if not fim_periodo_frequencia_1:
                self._errors['fim_periodo_frequencia_1'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é mensal, é necessário preencher este campo.']
                )
                del_atributos.append('fim_periodo_frequencia_1')
            if (
                inicio_periodo_frequencia_1
                and fim_periodo_frequencia_1
                and not (inicio_periodo_frequencia_1 == 1 and fim_periodo_frequencia_1 == 31)
                and not (inicio_periodo_frequencia_1 >= 2 and fim_periodo_frequencia_1 == inicio_periodo_frequencia_1 - 1)
            ):
                self._errors['fim_periodo_frequencia_1'] = self.error_class(
                    [
                        'Se o início do período é no dia 1, o final do período necessariamente será no dia 31. '
                        'Se, por exemplo, o início do período é no dia 2, o fim do período necessariamente será '
                        'no dia 1. Se, por exemplo, o início do período é no dia 3, o fim do período necessariamente '
                        'será no dia 2. E assim sucessivamente.'
                    ]
                )
                del_atributos.append('fim_periodo_frequencia_1')
            if inicio_periodo_frequencia_2:
                self._errors['inicio_periodo_frequencia_2'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é mensal, este campo deve ser deixado em branco.']
                )
                del_atributos.append('inicio_periodo_frequencia_2')
            if fim_periodo_frequencia_2:
                self._errors['fim_periodo_frequencia_2'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é mensal, este campo deve ser deixado em branco.']
                )
                del_atributos.append('fim_periodo_frequencia_2')
        elif periodicidade_envio_relatorio_frequencia == Aprendizagem.QUINZENAL:
            if not inicio_periodo_frequencia_1:
                self._errors['inicio_periodo_frequencia_1'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é quinzenal, é necessário preencher este campo.']
                )
                del_atributos.append('inicio_periodo_frequencia_1')
            if not fim_periodo_frequencia_1:
                self._errors['fim_periodo_frequencia_1'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é quinzenal, é necessário preencher este campo.']
                )
                del_atributos.append('fim_periodo_frequencia_1')

            if not inicio_periodo_frequencia_2:
                self._errors['inicio_periodo_frequencia_2'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é quinzenal, é necessário preencher este campo.']
                )
                del_atributos.append('inicio_periodo_frequencia_2')
            if not fim_periodo_frequencia_2:
                self._errors['fim_periodo_frequencia_2'] = self.error_class(
                    ['Se a periodicidade de envio do relatório de frequência é quinzenal, é necessário preencher este campo.']
                )
                del_atributos.append('fim_periodo_frequencia_2')
            if inicio_periodo_frequencia_1 and fim_periodo_frequencia_1 and inicio_periodo_frequencia_2 and fim_periodo_frequencia_2:
                periodo_1 = self.conjunto_dias(inicio_periodo_frequencia_1, fim_periodo_frequencia_1)
                periodo_2 = self.conjunto_dias(inicio_periodo_frequencia_2, fim_periodo_frequencia_2)
                if len(periodo_1) < 14:
                    self._errors['fim_periodo_frequencia_1'] = self.error_class(['O primeiro período tem menos de 14 dias.'])
                    del_atributos.append('fim_periodo_frequencia_1')
                if len(periodo_1) > 17:
                    self._errors['fim_periodo_frequencia_1'] = self.error_class(['O primeiro período tem mais de 17 dias.'])
                    del_atributos.append('fim_periodo_frequencia_1')
                if len(periodo_2) < 14:
                    self._errors['fim_periodo_frequencia_2'] = self.error_class(['O segundo período tem menos de 14 dias.'])
                    del_atributos.append('fim_periodo_frequencia_2')
                if len(periodo_2) > 17:
                    self._errors['fim_periodo_frequencia_2'] = self.error_class(['O segundo período tem mais de 17 dias.'])
                    del_atributos.append('fim_periodo_frequencia_2')
                if not periodo_1.intersection(periodo_2).issubset(set()):
                    self._errors['fim_periodo_frequencia_2'] = self.error_class(
                        ['Os períodos então entrando um no outro. Eles devem ser conjuntos de dias disjuntos.']
                    )
                    del_atributos.append('fim_periodo_frequencia_2')
                if not self.conjunto_dias(1, 31).issubset(periodo_1.union(periodo_2)):
                    self._errors['fim_periodo_frequencia_2'] = self.error_class(
                        ['Os períodos não estão cobrindo do dia 1 ao 31. A união dos conjuntos de dias dos períodos deve abranger todos estes dias.']
                    )
                    del_atributos.append('fim_periodo_frequencia_2')
        if not emails_relatorio_frequencia:
            if (
                inicio_periodo_frequencia_1
                or fim_periodo_frequencia_1
                or inicio_periodo_frequencia_2
                or fim_periodo_frequencia_2
                or periodicidade_envio_relatorio_frequencia
            ):
                self._errors['emails_relatorio_frequencia'] = self.error_class(
                    ['Para envio do relatório é essencial o cadastro de, no mínimo, um e-mail.']
                )
                del_atributos.append('emails_relatorio_frequencia')
        for del_atributo in del_atributos:
            if del_atributo in self.cleaned_data:
                del self.cleaned_data[del_atributo]

    def conjunto_dias(self, inicio, fim):
        if inicio < fim:
            return set(range(inicio, fim + 1))
        else:
            return set(list(range(inicio, 32)) + list(range(1, fim + 1)))

    def _tratar_criacao_manual_do_modulo(self, num_modulo: int, tipo_modulo: int):
        if num_modulo not in (1, 2, 3, 4):
            raise ValueError(f'Número de módulo inválido: {num_modulo}.')
        if tipo_modulo not in (
            ModuloAprendizagem.MODULO_I,
            ModuloAprendizagem.MODULO_II,
            ModuloAprendizagem.MODULO_III,
            ModuloAprendizagem.MODULO_IV,
        ):
            raise ValueError(f'Tipo de módulo inválido: {tipo_modulo}.')

        chave_modulo = f'modulo_{num_modulo}'
        chave_descricao_atividades = f'descricao_atividades_{num_modulo}'
        chave_data_inicio = f'data_inicio_{num_modulo}'
        chave_data_fim = f'data_fim_{num_modulo}'
        chave_ch_teorica_semanal = f'ch_teorica_semanal_{num_modulo}'
        chave_ch_pratica_semanal = f'ch_pratica_semanal_{num_modulo}'

        if self.cleaned_data.get(chave_modulo):
            modulo = self.instance.moduloaprendizagem_set.filter(tipo_modulo=tipo_modulo).first()

            if modulo is None:
                modulo = ModuloAprendizagem(
                    tipo_modulo=tipo_modulo,
                    aprendizagem=self.instance,
                    atividades=self.cleaned_data.get(chave_descricao_atividades),
                    inicio=self.cleaned_data.get(chave_data_inicio),
                    fim=self.cleaned_data.get(chave_data_fim),
                    ch_teorica_semanal=self.cleaned_data.get(chave_ch_teorica_semanal),
                    ch_pratica_semanal=self.cleaned_data.get(chave_ch_pratica_semanal),
                )
            else:
                modulo.atividades = self.cleaned_data.get(chave_descricao_atividades)
                modulo.inicio = self.cleaned_data.get(chave_data_inicio)
                modulo.fim = self.cleaned_data.get(chave_data_fim)
                modulo.ch_teorica_semanal = self.cleaned_data.get(chave_ch_teorica_semanal)
                modulo.ch_pratica_semanal = self.cleaned_data.get(chave_ch_pratica_semanal)
            modulo.save()
        else:
            modulo = self.instance.moduloaprendizagem_set.filter(tipo_modulo=tipo_modulo).first()
            if modulo is not None:
                modulo.delete()

    @transaction.atomic
    def save(self, *args, **kwargs):
        vinculo = self.cleaned_data['vinculo']
        qs = Professor.objects.filter(vinculo__id=vinculo.id)
        if qs.exists():
            self.instance.orientador = qs[0]
        else:
            professor = Professor()
            professor.vinculo = vinculo
            professor.save()
            self.instance.orientador = professor
            Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)
        self.instance.eh_utilizado_como_pratica_profissional = False

        arquivo_a_remover, deve_criar_doc_eletronico_do_contrato = self._tratar_estrategia_adicao_contrato_pre_save()

        if not Aprendizagem.cadastra_modulos_manualmente(self.instance):
            self.instance.modulo_1 = False
            self.instance.modulo_2 = False
            self.instance.modulo_3 = False
            self.instance.modulo_4 = False

        aprendizagem = super().save()

        if arquivo_a_remover:
            arquivo_a_remover.delete()
        if deve_criar_doc_eletronico_do_contrato:
            aprendizagem.gerar_documento_eletronico_do_contrato(self.request.user)

        if Aprendizagem.cadastra_modulos_manualmente(self.instance):
            self._tratar_criacao_manual_do_modulo(1, ModuloAprendizagem.MODULO_I)
            self._tratar_criacao_manual_do_modulo(2, ModuloAprendizagem.MODULO_II)
            self._tratar_criacao_manual_do_modulo(3, ModuloAprendizagem.MODULO_III)
            self._tratar_criacao_manual_do_modulo(4, ModuloAprendizagem.MODULO_IV)

        notificar = not self.instance.pk
        returno = super().save(*args, **kwargs)
        if notificar:
            self.instance.notificar_professores_diarios(self.request.user)
            self.instance.enviar_email_empregado_monitor_recem_cadastrado(self.request.user)
            self.instance.enviar_email_aprendiz_recem_cadastrado(self.request.user)
            self.instance.enviar_email_orientador_recem_cadastrado(self.request.user)
        return returno


class EditarContratoAprendizagemForm(forms.ModelFormPlus, EscolhaTipoContratoAprendizagemFormMixin):
    estrategia_adicao_contrato = EscolhaTipoContratoAprendizagemFormMixin.get_field_estrategia_adicao_contrato(
        permitir_criar_documento_eletronico=False
    )

    class Meta:
        model = Aprendizagem
        fields = (
            'contrato_aprendizagem',
            'contrato_aprendizagem_documento_eletronico',
        )

    class Media:
        js = EscolhaTipoContratoAprendizagemFormMixin.MEDIA_JS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configurar_campos_contrato()

    @transaction.atomic
    def save(self):
        arquivo_a_remover, _ = self._tratar_estrategia_adicao_contrato_pre_save()
        super().save()

        if arquivo_a_remover:
            arquivo_a_remover.delete()


class AditivoContratualAprendizagemForm(forms.ModelFormPlus):
    # tipo 1 = orientador
    orientador = forms.ModelChoiceFieldPlus(Vinculo.objects.servidores(), label='Orientador', required=False)

    # tipo 3 = monitor
    nome_monitor = forms.CharFieldPlus(label='Nome', required=False)
    telefone_monitor = forms.CharFieldPlus(label='Telefone', required=False)
    cargo_monitor = forms.CharFieldPlus(label='Cargo', required=False)
    email_monitor = forms.EmailField(label='E-mail', required=False)
    observacao = forms.CharFieldPlus(label='Observação', required=False, widget=forms.Textarea())

    # tipo 4 = turno
    turno = forms.ModelChoiceField(Turno.objects.all(), label='Turno', required=False)

    # tipo 5 = filial (demanda 562)
    empresa = forms.ModelChoiceFieldPlus(
        label='Concedente', queryset=PessoaJuridica.objects, widget=AutocompleteWidget(search_fields=PessoaJuridica.SEARCH_FIELDS), required=False
    )
    cidade = forms.ModelChoiceFieldPlus(
        label='Município',
        queryset=Cidade.objects,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS, form_filters=[('estado', 'estado__in')]),
        required=False,
    )
    logradouro = forms.CharField(label='Logradouro', required=False)
    numero = forms.CharField(label='Nº', required=False)
    complemento = forms.CharField(label='Complemento', required=False)
    bairro = forms.CharField(label='Bairro', required=False)
    cep = forms.CharField(label='CEP', required=False)
    controla_tempo = forms.CharFieldPlus(required=False, widget=forms.HiddenInput())

    class Meta:
        model = AditivoContratualAprendizagem
        fields = ('tipos_aditivo', 'descricao', 'aditivo', 'inicio_vigencia')

    class Media:
        js = ('/static/estagios/js/AditivoContratualAprendizagemForm.js',)

    fieldsets = (
        ('Dados gerais', {'fields': ('tipos_aditivo', ('inicio_vigencia', 'aditivo'), 'descricao')}),
        ('Aditivo de Professor Orientador', {'fields': ('orientador',)}),
        ('Aditivo de Empregado Monitor', {'fields': ('nome_monitor', 'telefone_monitor', 'cargo_monitor', 'email_monitor', 'observacao')}),
        ('Aditivo de Horário', {'fields': ('turno',)}),
        ('Aditivo de Mudança de Filial/Empresa', {'fields': ('empresa', 'cidade', 'logradouro', 'numero', 'complemento', 'bairro', 'cep')}),
    )

    def __init__(self, aprendizagem, *args, **kwargs):
        TipoAditivoAprendizagem.popula_tipos_aditivos()

        super().__init__(*args, **kwargs)

        # field 'tipos_aditivo'
        # o domínio são todos os tipos de aditivos, exceto o tipo 'Tempo'
        self.fields['tipos_aditivo'].widget = forms.CheckboxSelectMultiplePlus()
        self.fields['tipos_aditivo'].queryset = TipoAditivoAprendizagem.objects.all().order_by('id')
        lista = []
        if Aprendizagem.cadastra_modulos_manualmente(aprendizagem):
            for modulo in ModuloAprendizagem.objects.filter(aprendizagem=aprendizagem):
                self.fields[f'{modulo.id}_inicio'] = forms.DateFieldPlus(
                    label=f'{modulo.get_tipo_modulo_display()} - Data Início', initial=modulo.inicio
                )
                lista.append(f'{modulo.id}_inicio')
                self.fields[f'{modulo.id}_fim'] = forms.DateFieldPlus(label=f'{modulo.get_tipo_modulo_display()} - Data Fim', initial=modulo.fim)
                lista.append(f'{modulo.id}_fim')
        else:
            self.fields['data_prevista_encerramento'] = forms.DateFieldPlus(
                label='Previsão de encerramento da aprendizagem', initial=aprendizagem.data_prevista_encerramento
            )
            lista.append('data_prevista_encerramento')
        if lista:
            lista.append('controla_tempo')
            self.fieldsets = (*self.fieldsets, ('Aditivo de Tempo', {'fields': lista}))

        self.instance.aprendizagem = aprendizagem

    def clean(self):
        cleaned_data = super().clean()

        if self.cleaned_data.get('tipos_aditivo'):
            # orientador
            if TipoAditivoAprendizagem.objects.get(pk=TipoAditivoAprendizagem.PROFESSOR_ORIENTADOR) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('orientador'):
                    self.add_error('orientador', 'Deve ser informado o novo professor orientador.')

            # monitor
            if TipoAditivoAprendizagem.objects.get(pk=TipoAditivoAprendizagem.EMPREGADO_MONITOR) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('nome_monitor'):
                    self.add_error('nome_monitor', 'Deve ser informado o nome do novo monitor desta aprendizagem.')
                if not cleaned_data.get('telefone_monitor'):
                    self.add_error('telefone_monitor', 'Deve ser informado o telefone do novo monitor desta aprendizagem.')
                if not cleaned_data.get('cargo_monitor'):
                    self.add_error('cargo_monitor', 'Deve ser informado o cargo do novo monitor desta aprendizagem.')
                if not cleaned_data.get('email_monitor'):
                    self.add_error('email_monitor', 'Deve ser informado o e-mail do novo monitor desta aprendizagem.')

            # turno
            if TipoAditivoAprendizagem.objects.get(pk=TipoAditivoAprendizagem.HORARIO) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('turno'):
                    self.add_error('turno', 'Deve ser informado o novo turno desta aprendizagem.')

            # filial (demanda 562)
            if TipoAditivoAprendizagem.objects.get(pk=TipoAditivoAprendizagem.FILIAL) in self.cleaned_data['tipos_aditivo']:
                if not cleaned_data.get('empresa'):
                    self.add_error('empresa', 'Deve ser informado a nova empresa concedente desta aprendizagem.')

                if not cleaned_data.get('cidade'):
                    self.add_error('cidade', 'Deve ser informado a cidade da nova empresa concedente desta aprendizagem.')

                if not cleaned_data.get('logradouro'):
                    self.add_error('logradouro', 'Deve ser informado o logradouro da nova empresa concedente desta aprendizagem.')

                if not cleaned_data.get('numero'):
                    self.add_error('numero', 'Deve ser informado o número da nova empresa concedente desta aprendizagem.')

                if not cleaned_data.get('bairro'):
                    self.add_error('bairro', 'Deve ser informado o bairro da nova empresa concedente desta aprendizagem.')

                if not cleaned_data.get('cep'):
                    self.add_error('cep', 'Deve ser informado o cep da nova empresa concedente desta aprendizagem.')

        return cleaned_data

    @transaction.atomic
    def save(self, *args, **kwargs):
        # salva o aditivo
        super().save(*args, **kwargs)

        aditivo = self.instance

        # atualiza dados da aprendizagem e seta histórico textual no aditivo recém criado informando
        # a mudança de informações que ocorreu na aprendizagem atualizada
        aprendizagem = aditivo.aprendizagem
        historico = []
        atributos_atualizados = OrderedDict()

        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.PROFESSOR_ORIENTADOR).exists():
            atributos_atualizados['orientador'] = ['orientador']
        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.EMPREGADO_MONITOR).exists():
            atributos_atualizados['monitor'] = ['nome_monitor', 'telefone_monitor', 'cargo_monitor', 'email_monitor', 'observacao']
        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.HORARIO).exists():
            atributos_atualizados['turno'] = ['turno']
        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.FILIAL).exists():
            atributos_atualizados['filial'] = ['empresa', 'cidade', 'logradouro', 'numero', 'complemento', 'bairro', 'cep']

        for grupo in atributos_atualizados:
            historico.append(f'{grupo.capitalize()}:'.upper())
            for atributo in atributos_atualizados[grupo]:
                if hasattr(aprendizagem, atributo):
                    value_anterior = getattr(aprendizagem, atributo)
                    value_atual = self.cleaned_data.get(atributo)

                    if value_atual and value_atual.__class__ in [InMemoryUploadedFile, TemporaryUploadedFile]:
                        value_atual = value_atual.name

                    if atributo == 'orientador':
                        vinculo = value_atual
                        qs = Professor.objects.filter(vinculo__id=vinculo.pk)
                        if qs.exists():
                            professor = qs[0]
                        else:
                            professor = Professor()
                            professor.vinculo = vinculo
                            professor.save()
                            Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)
                        value_atual = professor

                    setattr(aprendizagem, atributo, value_atual)

                    # ajustes dos valores para setar o histórico
                    if value_anterior.__class__ == FieldFile:
                        value_anterior = value_anterior.name

                    if value_anterior in [True, False]:
                        value_anterior = 'Sim' if value_anterior else 'Não'

                    if value_atual in [True, False]:
                        value_atual = 'Sim' if value_atual else 'Não'

                    if value_anterior.__class__ == Professor:
                        value_anterior = value_anterior.vinculo

                    if value_atual.__class__ == Professor:
                        value_atual = value_atual.vinculo

                    if value_anterior.__class__ == PessoaJuridica:
                        value_anterior = f'{value_anterior}'

                    if value_atual.__class__ == PessoaJuridica:
                        value_atual = f'{value_atual}'

                    label_field = aprendizagem._meta.get_field(atributo).verbose_name
                    historico.append(f'{label_field}: {format_(value_anterior)} → {format_(value_atual)}')
            historico.append('')
        historico_tempo = []
        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.TEMPO).exists():
            if Aprendizagem.cadastra_modulos_manualmente(aprendizagem):
                for modulo in ModuloAprendizagem.objects.filter(aprendizagem=aprendizagem):
                    campo_inicio = self.cleaned_data.get(f'{modulo.id}_inicio')
                    campo_fim = self.cleaned_data.get(f'{modulo.id}_fim')
                    alterou = False
                    if campo_inicio != modulo.inicio:
                        if not bool(historico_tempo):
                            historico_tempo.append('TEMPO:')
                        historico_tempo.append(
                            f'Data Início - {modulo.get_tipo_modulo_display()}: {format_(modulo.inicio)} → {format_(campo_inicio)}'
                        )
                        modulo.inicio = campo_inicio
                        alterou = True
                    if campo_fim != modulo.fim:
                        if not bool(historico_tempo):
                            historico_tempo.append('TEMPO:')
                        historico_tempo.append(f'Data Fim - {modulo.get_tipo_modulo_display()}: {format_(modulo.fim)} → {format_(campo_fim)}')
                        modulo.fim = campo_fim
                        alterou = True
                    if alterou:
                        modulo.save()
            else:
                nova_data_final = self.cleaned_data.get('data_prevista_encerramento')
                if nova_data_final != aprendizagem.data_prevista_encerramento:
                    if not bool(historico_tempo):
                        historico_tempo.append('TEMPO:')
                    historico_tempo.append(
                        f'Previsão de encerramento da aprendizagem: {format_(aprendizagem.data_prevista_encerramento)} → {format_(nova_data_final)}'
                    )
                    aprendizagem.data_prevista_encerramento = nova_data_final
        if historico_tempo:
            historico.extend(list(historico_tempo))
        aprendizagem.save()
        aditivo.historico = '\n'.join(historico)
        aditivo.save()

        # notifica por email
        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.PROFESSOR_ORIENTADOR).exists():
            aprendizagem.enviar_email_orientador_recem_cadastrado()

        if aditivo.tipos_aditivo.filter(pk=TipoAditivoAprendizagem.EMPREGADO_MONITOR).exists():
            aprendizagem.enviar_email_empregado_monitor_recem_cadastrado()


class RelatorioModuloAprendizagemForm(forms.ModelFormPlus):
    class Meta:
        model = RelatorioModuloAprendizagem
        exclude = ('aprendizagem', 'eh_relatorio_do_empregado_monitor', 'ultimo_editor', 'modulo_aprendizagem', 'relatorio_interno')

    fieldsets = (
        ('Atividades Previstas', {'fields': ('avaliacao_atividades', 'comentarios_atividades')}),
        ('Atividades Não Previstas', {'fields': ('outras_atividades',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.eh_relatorio_do_empregado_monitor:
            self.fieldsets += (('Avaliação do Desempenho do Aprendiz', {'fields': ('nota_aprendiz',)}),)
            del self.fields['aprendizagem_na_area_formacao']
            del self.fields['aprendizagem_contribuiu']
            del self.fields['aplicou_conhecimento']
            del self.fields['avaliacao_conceito']
        else:
            self.fieldsets += (
                ('Relação Teoria/Prática', {'fields': ('aprendizagem_na_area_formacao', 'aprendizagem_contribuiu', 'aplicou_conhecimento')}),
            )
            self.fieldsets += (('Avaliação da Experiência como Aprendiz', {'fields': ('avaliacao_conceito', 'avaliacao_geral_atividades_aprendiz')}),)
            del self.fields['nota_aprendiz']
            self.fields['relatorio'].help_text = 'O relatório do módulo deve estar assinado pelo Aprendiz, Orientador e pelo Empregado Monitor.'
        self.fieldsets += (('Comentários e Sugestões', {'fields': ('avaliacao_comentarios',)}),)
        self.fieldsets += (('Data do Relatório', {'fields': ('data_relatorio',)}),)

        self.fieldsets += (('Relatório', {'fields': ('relatorio',)}),)

        # Adequando labels e help texts à nomenclatura correta do período (módulo/semestre)
        aprendizagem = self.instance.modulo_aprendizagem.aprendizagem
        if not Aprendizagem.cadastra_modulos_manualmente(aprendizagem):
            if not self.instance.eh_relatorio_do_empregado_monitor:
                self.fields['avaliacao_conceito'].help_text = self.fields['avaliacao_conceito'].help_text.replace(
                    'módulo', aprendizagem.nomenclatura_periodo.lower()
                )
            self.fields['avaliacao_comentarios'].help_text = self.fields['avaliacao_comentarios'].help_text.replace(
                'módulo', aprendizagem.nomenclatura_periodo.lower()
            )
            self.fields['relatorio'].label = self.fields['relatorio'].label.replace('Módulo', aprendizagem.nomenclatura_periodo)
            self.fields['relatorio'].help_text = self.fields['relatorio'].help_text.replace('módulo', aprendizagem.nomenclatura_periodo.lower())

    @transaction.atomic
    def save(self, commit=True):
        relatorio_modulo = super().save(commit)
        if not self.instance.pk or self.has_changed():
            relatorio_modulo.requer_revisao_orientador = (
                relatorio_modulo.eh_relatorio_eletronico()
                and relatorio_modulo.relatorio_contraparte is not None
                and relatorio_modulo.avaliacao_atividades == RelatorioModuloAprendizagem.PARCIALMENTE_REALIZADA
            )
            relatorio_modulo.save()

            relatorio_modulo.resetar_relatorio_eletronico()
            tasks.notificar_pendencia_assinatura_relatorio_modulo_aprendizagem(relatorio_modulo)
        return relatorio_modulo


class ResolverDivergenciasRelatoriosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Confirmar escolhas'

    VERSAO_ALUNO = '1'
    VERSAO_SUPERVISOR_MONITOR = '2'

    def __init__(self, eh_relatorio_estagio, rel_aluno, rel_supervisor_monitor, divergencias=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.eh_relatorio_estagio = eh_relatorio_estagio
        self.rel_aluno = rel_aluno
        self.rel_supervisor_monitor = rel_supervisor_monitor
        self.fieldsets = []

        versao_choices = []

        if self.rel_supervisor_monitor.eh_relatorio_eletronico():
            versao_choices.append((self.VERSAO_ALUNO, 'Usar versão do aluno'))
        if self.rel_aluno.eh_relatorio_eletronico():
            versao_choices.append((self.VERSAO_SUPERVISOR_MONITOR, 'Usar versão do supervisor'))

        # Divergências em relatório de estágio
        if eh_relatorio_estagio:
            divergencias = divergencias or get_divergencias_relatorios_estagio(rel_aluno, rel_supervisor_monitor)

            if divergencias.get('atividades_previstas'):
                self.fields['versao_atividades'] = forms.ChoiceField(
                    label='Escolha a versão', choices=[(None, '-------------'), *versao_choices], required=False
                )

            if (divergencias.get('atividades_nao_previstas') or {}).get('realizou_outras_atividades'):
                self.fields['versao_realizou_outras_atividades'] = forms.ChoiceField(
                    label='Escolha a versão', choices=[(None, '-------------'), *versao_choices], required=False
                )
            else:
                for campo in divergencias.get('atividades_nao_previstas') or {}:
                    self.fields[f'versao_{campo}'] = forms.ChoiceField(
                        label='Escolha a versão', choices=[(None, '-------------'), *versao_choices], required=False
                    )

        # Divergências em relatório de aprendizagem
        else:
            if self.rel_aluno.eh_relatorio_eletronico():
                # A opção do supervisor/monitor sempre será a última da lista
                versao_choices[len(versao_choices) - 1] = (self.VERSAO_SUPERVISOR_MONITOR, 'Usar versão do monitor')

            divergencias = divergencias or get_divergencias_relatorios_modulo_aprendizagem(rel_aluno, rel_supervisor_monitor)

            for campo in divergencias or {}:
                self.fields[f'versao_{campo}'] = forms.ChoiceField(
                    label='Escolha a versão', choices=[(None, '-------------'), *versao_choices], required=False
                )

    def clean(self):
        lista_campos = [
            # Estágios
            'versao_atividades',
            'versao_realizou_outras_atividades',
            'versao_outras_atividades',
            'versao_outras_atividades_justificativa',
            # Aprendizagem
            'versao_avaliacao_atividades',
            'versao_comentarios_atividades',
            'versao_outras_atividades',
        ]
        campos_vazios = []
        for campo in lista_campos:
            if self.fields.get(campo) and not self.cleaned_data.get(campo):
                campos_vazios.append(campo)
        if campos_vazios:
            raise forms.ValidationError(dict.fromkeys(campos_vazios, 'Este campo é obrigatório'))
        return self.cleaned_data

    @transaction.atomic()
    def processar(self):
        if self.eh_relatorio_estagio:
            versao_atividades = self.cleaned_data.get('versao_atividades')
            versao_realizou_outras_atividades = self.cleaned_data.get('versao_realizou_outras_atividades')
            versao_outras_atividades = self.cleaned_data.get('versao_outras_atividades')
            versao_outras_atividades_justificativa = self.cleaned_data.get('versao_outras_atividades_justificativa')

            # Realização das atividades (REALIZADAS, NÃO REALIZADAS, PARCIALMENTE REALIZADAS e motivos)
            if versao_atividades:
                rel_origem = self.rel_aluno if versao_atividades == self.VERSAO_ALUNO else self.rel_supervisor_monitor
                rel_destino = self.rel_supervisor_monitor if versao_atividades == self.VERSAO_ALUNO else self.rel_aluno
                for atividade_relatorio in rel_origem.relatoriosemestralestagioatividade_set.all():
                    RelatorioSemestralEstagioAtividade.objects.filter(
                        relatorio_semestral=rel_destino,
                        atividade=atividade_relatorio.atividade,
                    ).update(
                        realizada=atividade_relatorio.realizada,
                        nao_realizada_motivo=atividade_relatorio.nao_realizada_motivo,
                        nao_realizada_motivo_descricao=atividade_relatorio.nao_realizada_motivo_descricao,
                    )
            # Realizou atividades não previstas
            if versao_realizou_outras_atividades:
                if versao_realizou_outras_atividades == self.VERSAO_ALUNO:
                    self.rel_supervisor_monitor.realizou_outras_atividades = self.rel_aluno.realizou_outras_atividades
                    self.rel_supervisor_monitor.outras_atividades = self.rel_aluno.outras_atividades
                    self.rel_supervisor_monitor.outras_atividades_justificativa = self.rel_aluno.outras_atividades_justificativa
                else:
                    self.rel_aluno.realizou_outras_atividades = self.rel_supervisor_monitor.realizou_outras_atividades
                    self.rel_aluno.outras_atividades = self.rel_supervisor_monitor.outras_atividades
                    self.rel_aluno.outras_atividades_justificativa = self.rel_supervisor_monitor.outras_atividades_justificativa
            # Descrição das atividades não previstas
            if versao_outras_atividades:
                if versao_outras_atividades == self.VERSAO_ALUNO:
                    self.rel_supervisor_monitor.outras_atividades = self.rel_aluno.outras_atividades
                else:
                    self.rel_aluno.outras_atividades = self.rel_supervisor_monitor.outras_atividades
            # Justificativa para atividades não previstas
            if versao_outras_atividades_justificativa:
                if versao_outras_atividades_justificativa == self.VERSAO_ALUNO:
                    self.rel_supervisor_monitor.outras_atividades_justificativa = self.rel_aluno.outras_atividades_justificativa
                else:
                    self.rel_aluno.outras_atividades_justificativa = self.rel_supervisor_monitor.outras_atividades_justificativa
        else:
            versao_avaliacao_atividades = self.cleaned_data.get('versao_avaliacao_atividades')
            versao_comentarios_atividades = self.cleaned_data.get('versao_comentarios_atividades')
            versao_outras_atividades = self.cleaned_data.get('versao_outras_atividades')

            # Realização das atividades (REALIZADAS, NÃO REALIZADAS, PARCIALMENTE REALIZADAS)
            if versao_avaliacao_atividades:
                if versao_avaliacao_atividades == self.VERSAO_ALUNO:
                    self.rel_supervisor_monitor.avaliacao_atividades = self.rel_aluno.avaliacao_atividades
                else:
                    self.rel_aluno.avaliacao_atividades = self.rel_supervisor_monitor.avaliacao_atividades
            # Descrição das atividades
            if versao_comentarios_atividades:
                if versao_comentarios_atividades == self.VERSAO_ALUNO:
                    self.rel_supervisor_monitor.comentarios_atividades = self.rel_aluno.comentarios_atividades
                else:
                    self.rel_aluno.comentarios_atividades = self.rel_supervisor_monitor.comentarios_atividades
            # Atividades não previstas
            if versao_outras_atividades:
                if versao_outras_atividades == self.VERSAO_ALUNO:
                    self.rel_supervisor_monitor.outras_atividades = self.rel_aluno.outras_atividades
                else:
                    self.rel_aluno.outras_atividades = self.rel_supervisor_monitor.outras_atividades

            self.rel_aluno.requer_revisao_orientador = False
            self.rel_supervisor_monitor.requer_revisao_orientador = False

        self.rel_aluno.save()
        self.rel_supervisor_monitor.save()


class EncerrarAprendizagemForm(forms.ModelFormPlus):
    class Meta:
        model = Aprendizagem
        fields = (
            'data_encerramento',
            'encerramento_por',
            'motivo_encerramento',
            'motivacao_rescisao',
            'ch_final',
            'laudo_avaliacao',
            'comprovante_encerramento',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ch_final'].help_text = self.instance.get_sugestao_ch_final()

    fieldsets = (
        ('Dados do Encerramento', {'fields': ('encerramento_por', 'motivo_encerramento', 'motivacao_rescisao', 'data_encerramento', 'ch_final')}),
        ('Documentação', {'fields': ('comprovante_encerramento', 'laudo_avaliacao')}),
    )

    def clean(self):
        cleaned_data = super().clean()
        data_encerramento = cleaned_data.get('data_encerramento', None)
        if data_encerramento:
            if cleaned_data.get('encerramento_por') and cleaned_data['encerramento_por'] == Aprendizagem.CONCLUSAO:
                if data_encerramento != self.instance.data_prevista_encerramento:
                    raise forms.ValidationError(
                        'No encerramento por conclusão, a data de encerramento deve ser a data prevista para o fim, que é a data de encerramento do último módulo.'
                    )
                if self.instance.ha_pendencia_relatorio_aprendiz(data_encerramento):
                    raise forms.ValidationError('Não é possível encerrar a aprendizagem, pois o aprendiz não cadastrou todos os relatórios.')
                if self.instance.ha_pendencia_relatorio_monitor(data_encerramento):
                    raise forms.ValidationError('Não é possível encerrar a aprendizagem, pois o monitor não realizou todas as avaliações do estágio.')
            if cleaned_data.get('encerramento_por') and cleaned_data['encerramento_por'] == Aprendizagem.RESCISAO:
                if (
                    not cleaned_data['laudo_avaliacao']
                    and cleaned_data.get('motivo_encerramento')
                    and cleaned_data['motivo_encerramento'] == Aprendizagem.MOTIVO_DESEMPENHO_INSUFICIENTE_INADAPTACAO
                ):
                    self._errors['laudo_avaliacao'] = self.error_class(
                        ['Na rescisão por desempenho insuficiente ou inadaptação do aprendiz é necessário anexar o Laudo de Avaliação.']
                    )
                    del self.cleaned_data['laudo_avaliacao']
                if self.instance.ha_pendencia_relatorio_aprendiz(data_encerramento):
                    raise forms.ValidationError('Não é possível encerrar a aprendizagem, pois o aprendiz não cadastrou seus relatórios pendentes.')
                if self.instance.ha_pendencia_relatorio_monitor(data_encerramento):
                    raise forms.ValidationError('Não é possível encerrar a aprendizagem, pois o monitor não cadastrou seus relatórios pendentes.')
        return cleaned_data


class EncerrarAprendizagemAbandonoMatriculaIrregularForm(forms.ModelFormPlus):
    class Meta:
        model = Aprendizagem
        fields = (
            'data_encerramento',
            'encerramento_por',
            'motivo_encerramento',
            'motivacao_rescisao',
            'ch_final',
            'desvinculado_matricula_irregular',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ch_final'].help_text = self.instance.get_sugestao_ch_final()
        self.fields['desvinculado_matricula_irregular'].required = True
        self.fields['motivacao_rescisao'].required = True

    fieldsets = (
        ('Dados do Encerramento', {'fields': ('encerramento_por', 'motivo_encerramento', 'motivacao_rescisao', 'data_encerramento', 'ch_final')}),
        ('Finalizar sem requisitos por abandono do aluno/matrícula irregular', {'fields': ('desvinculado_matricula_irregular',)}),
    )

    def clean(self):
        cleaned_data = super().clean()
        desvinculado_matricula_irregular = cleaned_data.get('desvinculado_matricula_irregular', None)
        if not desvinculado_matricula_irregular:
            self._errors['desvinculado_matricula_irregular'] = self.error_class(['Necessária confirmação.'])
        return cleaned_data


class EncerrarAtividadeProfissionalEfetivaForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadeProfissionalEfetiva
        fields = ('encerramento', 'ch_final', 'observacoes')

    fieldsets = (('Dados do Encerramento', {'fields': ('encerramento', 'ch_final', 'observacoes')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ch_final'].help_text = self.instance.get_sugestao_ch_final()

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.relatorio_final_aluno:
            raise forms.ValidationError(
                'Só é possível encerrar normalmente uma atividade profissional efetiva se a '
                'Declaração de Realização de Atividade Profissional Efetiva já estiver cadastrada.'
            )
        return cleaned_data

    def save(self, *args, **kwargs):
        self.instance.situacao = AtividadeProfissionalEfetiva.CONCLUIDA
        return super().save(*args, **kwargs)


class CadastrarCancelamentoAtividadeProfissionalEfetivaForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadeProfissionalEfetiva
        fields = ('cancelamento', 'motivo_cancelamento', 'descricao_cancelamento')

    fieldsets = (('Dados do Encerramento', {'fields': ('cancelamento', 'motivo_cancelamento', 'descricao_cancelamento')}),)

    def save(self, *args, **kwargs):
        self.instance.situacao = AtividadeProfissionalEfetiva.NAO_CONCLUIDA
        return super().save(*args, **kwargs)


class SolicitacaoCancelamentoEncerramentoEstagioForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoCancelamentoEncerramentoEstagio
        fields = ('justificativa',)


class SolicitacaoCancelamentoEncerramentoAprendizagemForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoCancelamentoEncerramentoEstagio
        fields = ('justificativa',)


class SolicitacaoCancelamentoEncerramentoAtividadeProfissionalEfetivaForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoCancelamentoEncerramentoEstagio
        fields = ('justificativa',)


class RelatorioAtividadeProfissionalEfetivaForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadeProfissionalEfetiva
        fields = (
            'avaliacao_atividades',
            'comentarios_atividades',
            'outras_atividades',
            'area_formacao',
            'contribuiu',
            'aplicou_conhecimento',
            'avaliacao_conceito',
            'data_relatorio',
            'relatorio_final_aluno',
        )

    fieldsets = (
        ('Atividades Previstas', {'fields': ('avaliacao_atividades', 'comentarios_atividades')}),
        ('Atividades Não Previstas', {'fields': ('outras_atividades',)}),
        ('Relação Teoria/Prática', {'fields': ('area_formacao', 'contribuiu', 'aplicou_conhecimento')}),
        ('Avaliação do Estágio', {'fields': ('avaliacao_conceito',)}),
        ('Relatório', {'fields': ('data_relatorio', 'relatorio_final_aluno')}),
    )

    def save(self, *args, **kwargs):
        self.instance.notificar_orientador_envio_relatorio_final_aluno(self.request.user)
        return super().save(*args, **kwargs)


class AtividadeProfissionalEfetivaForm(forms.ModelFormPlus):
    SITUACOES = [('', '---------'), ('em_andamento', 'Em Andamento'), ('concluida', 'Concluída')]

    situacao_atividade = forms.ChoiceField(label='Situação da Atividade', choices=SITUACOES)
    vinculo = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.servidores(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Orientador', required=True
    )

    class Meta:
        model = AtividadeProfissionalEfetiva
        exclude = ('orientador',)

    class Media:
        js = ('/static/estagios/js/AtividadeProfissionalEfetivaForm.js',)

    fieldsets = (
        ('Dados gerais', {'fields': ('aluno', 'instituicao', 'razao_social', 'vinculo', 'tipo', 'descricao_outro_tipo', 'situacao_atividade')}),
        ('Período e Carga Horária', {'fields': ('inicio', 'data_prevista_encerramento', 'ch_semanal')}),
        ('Documentação', {'fields': ('documentacao_comprobatoria', 'plano_ atividades')}),
        ('Relação das Atividades', {'fields': ('atividades',)}),
        ('Encerramento', {'fields': ('anterior_20171', 'encerramento', 'ch_final', 'relatorio_final_aluno', 'observacoes')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['aluno'].widget = AutocompleteWidget(search_fields=Aluno.SEARCH_FIELDS)
        self.fields['aluno'].queryset = self.fields['aluno'].queryset.filter(matriz__isnull=False)
        self.fields['ch_semanal'].widget = forms.IntegerWidget()
        if self.instance.pk:
            del self.fields['situacao_atividade']

        if self.instance.pk and self.instance.orientador:
            try:
                vinculo = self.instance.orientador.vinculo
                self.fields['vinculo'].initial = vinculo
            except Exception:
                pass

        if 'encerramento' in self.fields:
            self.fields['encerramento'].required = False
            self.fields['ch_final'].required = False
            self.fields['relatorio_final_aluno'].required = False

    def clean(self):
        cleaned_data = super().clean()
        if not bool(self.errors) and not self.instance.pk:
            if cleaned_data['situacao_atividade'] == 'concluida':
                if not cleaned_data['encerramento']:
                    self._errors['encerramento'] = self.error_class(
                        ['É necessário preencher a data do encerramento numa Atividade Profissional Efetiva já concluída.']
                    )
                    del self.cleaned_data['encerramento']
                if not cleaned_data['ch_final']:
                    self._errors['ch_final'] = self.error_class(
                        ['É necessário preencher a C.H. cumprida numa Atividade Profissional Efetiva já concluída.']
                    )
                    del self.cleaned_data['ch_final']
                if not cleaned_data['relatorio_final_aluno'] and not cleaned_data['anterior_20171']:
                    self._errors['relatorio_final_aluno'] = self.error_class(
                        ['É necessário preencher o relatório final do aluno numa Atividade Profissional Efetiva já concluída.']
                    )
                    del self.cleaned_data['relatorio_final_aluno']

        return cleaned_data

    @transaction.atomic
    def save(self, *args, **kwargs):
        vinculo = self.cleaned_data['vinculo']
        qs = Professor.objects.filter(vinculo__id=vinculo.pk)
        if qs.exists():
            self.instance.orientador = qs[0]
        else:
            professor = Professor()
            professor.vinculo = vinculo
            professor.save()
            self.instance.orientador = professor
            Group.objects.get(name='Professor').user_set.add(professor.vinculo.user)

        if self.cleaned_data.get('situacao_atividade', None) == 'concluida':
            self.instance.situacao = AtividadeProfissionalEfetiva.CONCLUIDA
        else:
            self.instance.situacao = AtividadeProfissionalEfetiva.EM_ANDAMENTO

        notificar = not self.instance.pk
        retorno = super().save(*args, **kwargs)
        if notificar:
            self.instance.notificar_aluno_inicialmente()
            self.instance.orientador_recem_cadastrado()
        return retorno


class JustificativaVisitaEstagioForm(forms.ModelFormPlus):
    class Meta:
        model = JustificativaVisitaEstagio
        exclude = ('pratica_profissional', 'inicio', 'fim', 'formulario_justificativa', 'relatorio_interno')

    fieldsets = (
        ('Justificativa', {'fields': ('motivos',)}),
        ('Outros Acompanhamentos', {'fields': ('outros_acompanhamentos',)}),
    )

    def save(self, commit=True):
        instance = super().save(commit)
        if commit and self.has_changed():
            instance.relatorio_interno.delete()
        return instance


class JustificativaVisitaModuloAprendizagemForm(forms.ModelFormPlus):
    class Meta:
        model = JustificativaVisitaModuloAprendizagem
        fields = (
            'motivos',
            'outros_acompanhamentos',
        )

    fieldsets = (
        ('Justificativa', {'fields': ('motivos',)}),
        ('Outros Acompanhamentos', {'fields': ('outros_acompanhamentos',)}),
    )

    def save(self, commit=True):
        instance = super().save(commit)
        if not self.instance.pk or self.has_changed():
            instance.resetar_documento_eletronico()
        return instance


class IniciarSessaoAssinaturaSenhaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Assinar'
    senha = forms.PasswordField()


class NotificacoesEstagioForm(forms.FormPlus):
    INFO = 'Selecione abaixo as pendências ou assuntos que você deseja notificar.'
    SUBMIT_LABEL = 'Confirmar'

    cadastro_rel_atividades = forms.BooleanField(
        label='Cadastro de Relatório de Atividades',
        required=False,
        initial=True,
        help_text='Notificar aluno e supervisor se houver pendência no envio do Relatório de Atividades.',
    )
    assinatura_rel_atividades = forms.BooleanField(
        label='Assinatura de Relatório de Atividades',
        required=False,
        initial=True,
        help_text='Notificar signatários que ainda não assinaram o Relatório de Atividades eletrônico.',
    )
    registro_visitas = forms.BooleanField(
        label='Registro de visitas do Orientador',
        required=False,
        initial=True,
        help_text='Notificar orientador se houver pendências relacionadas ao registro de visitas.',
    )
    matricula_irregular = forms.BooleanField(
        label='Matrícula irregular do estagiário',
        required=False,
        initial=True,
        help_text='Verificar e notificar se aluno possui irregularidades na matrícula.',
    )
    assinatura_tre = forms.BooleanField(
        label='Assinatura do Termo de Realização de Estágio',
        required=False,
        initial=True,
        help_text='Notificar signatários que ainda não assinaram o Termo de Realização de Estágio.',
    )

    def __init__(self, *args, pratica_profissional=None, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        # apenas uma das opções deve ser escolhida.
        if (pratica_profissional is None) == (queryset is None):
            raise ValueError('Estágio(s) não informado(s).')

        self.pratica_profissional = pratica_profissional
        self.queryset = queryset
        if self.queryset:
            self.INFO += ' A operação será realizada para todos os estágios ativos.'

        if not PraticaProfissional.registro_visita_obrigatorio() or (
            self.pratica_profissional and not self.pratica_profissional.requer_acompanhamento_de_visitas
        ):
            del self.fields['registro_visitas']

    def _get_notificar_kwargs(self):
        return {
            'cadastro_rel_atividades': self.cleaned_data.get('cadastro_rel_atividades'),
            'assinatura_rel_atividades': self.cleaned_data.get('assinatura_rel_atividades'),
            'registro_visitas': self.cleaned_data.get('registro_visitas'),
            'matricula_irregular': self.cleaned_data.get('matricula_irregular'),
            'assinatura_tre': self.cleaned_data.get('assinatura_tre'),
        }

    def processar(self):
        kwargs = self._get_notificar_kwargs()
        if self.pratica_profissional:
            self.pratica_profissional.notificar(user=self.request.user, **kwargs)
        else:
            for obj in self.queryset.order_by('-id').distinct():
                obj.notificar(user=self.request.user, **kwargs)


class NotificacoesAprendizagemForm(forms.FormPlus):
    INFO = 'Selecione abaixo as pendências ou assuntos que você deseja notificar.'
    SUBMIT_LABEL = 'Confirmar'

    cadastro_rel_atividades = forms.BooleanField(
        label='Cadastro de Relatório de Atividades',
        required=False,
        initial=True,
        help_text='Notificar aluno e empregado monitor se houver pendência no envio do Relatório de Atividades.',
    )
    assinatura_rel_atividades = forms.BooleanField(
        label='Assinatura de Relatório de Atividades',
        required=False,
        initial=True,
        help_text='Notificar signatários que ainda não assinaram o Relatório de Atividades eletrônico.',
    )
    revisao_rel_atividades = forms.BooleanField(
        label='Revisão de Relatório de Atividades',
        required=False,
        initial=True,
        help_text='Notificar orientador sobre potenciais divergências ou pendência de revisão nos Relatórios de Atividades.',
    )
    matricula_irregular = forms.BooleanField(
        label='Matrícula irregular do aprendiz',
        required=False,
        initial=True,
        help_text='Verificar e notificar se aprendiz possui irregularidades na matrícula.',
    )
    relatorio_frequencia = forms.BooleanField(
        label='Relatório de frequência do Aprendiz',
        required=False,
        initial=True,
        help_text='Enviar relatório de frequência do aprendiz aos destinatários configurados na Aprendizagem.',
    )

    def __init__(self, *args, aprendizagem=None, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        # apenas uma das opções deve ser escolhida.
        if (aprendizagem is None) == (queryset is None):
            raise ValueError('Aprendizagem(ns) não informada(s).')

        self.aprendizagem = aprendizagem
        self.queryset = queryset

        if self.queryset:
            self.INFO += ' A operação será realizada para todas as aprendizagens ativas.'

    def _get_notificar_kwargs(self):
        return {
            'cadastro_rel_atividades': self.cleaned_data.get('cadastro_rel_atividades'),
            'assinatura_rel_atividades': self.cleaned_data.get('assinatura_rel_atividades'),
            'revisao_rel_atividades': self.cleaned_data.get('revisao_rel_atividades'),
            'matricula_irregular': self.cleaned_data.get('matricula_irregular'),
            'relatorio_frequencia': self.cleaned_data.get('relatorio_frequencia'),
        }

    def processar(self):
        kwargs = self._get_notificar_kwargs()
        if self.aprendizagem:
            self.aprendizagem.notificar(**kwargs)
        else:
            for obj in self.queryset.order_by('-id').distinct():
                obj.notificar(**kwargs)
