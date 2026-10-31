import datetime
import decimal
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Sum
from django.db.models.functions import Length

from comum.models import Ano, Configuracao, UsuarioGrupo, Vinculo
from comum.utils import get_setor, tl
from djtools import forms
from djtools.forms import ModelFormPlus, ReadOnlyField
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus, RenderableSelectMultiple
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import format_money, in_group
from djtools.utils import send_notification
from documento_eletronico.assinar_documento import assinar_documento_com_senha
from documento_eletronico.models import Documento, DocumentoTexto, ModeloDocumento, SolicitacaoAssinatura, TipoDocumento
from financeiro.models import Acao, AcaoAno, ClassificacaoInstitucional, NaturezaDespesa, ProgramaTrabalhoResumido
from plan_estrategico.models import (
    PDI,
    ArquivoMeta,
    AtividadeEtapa,
    EtapaProjeto,
    EtapaProjetoPlanoAtividade,
    Indicador,
    MetaIndicador,
    MovimentacaoCredito,
    MovimentacaoCreditoHistorico,
    MovimentacaoCreditoUnidade,
    NaturezaDespesaPlanoAtividade,
    NotaCredito,
    NotaDotacao,
    NotaEmpenho,
    ObjetivoEstrategico,
    ObjetivoIndicador,
    OrigemRecurso,
    OrigemRecursoProjeto,
    OrigemRecursoProjetoEtapa,
    PDIIndicador,
    PDIObjetivoEstrategico,
    PDIPerspectiva,
    PeriodoPreenchimentoVariavel,
    Perspectiva,
    PlanoAtividade,
    PlanoInterno,
    PlanoInternoPlanoAtividade,
    ProjetoEstrategico,
    ProjetoPlanoAtividade,
    RequisicaoDespesa,
    RequisicaoDespesaHistorico,
    RequisicaoRealocacao,
    RequisicaoRealocacaoHistorico,
    TematicaVariavel,
    UnidadeGestora,
    UnidadeGestoraEtapa,
    UnidadeOrigemEtapa,
    VariavelCampus,
    ler_planilha_metas,
    validar_planilha_metas,
)
from plan_estrategico.utils import get_setor_unidade_administrativa, get_setor_unidade_gestora
from processo_eletronico.models import Processo as ProcessoEletronico
from processo_eletronico.models import ProcessoStatus, Tramite
from protocolo.models import Processo
from rh.models import Papel, Servidor, Setor, UnidadeOrganizacional
from tesouro_gerencial.models import DocumentoEmpenho
from tesouro_gerencial.models import UnidadeGestora as UnidadeGestoraSiafi


class ConfiguracaoForm(forms.FormPlus):
    setor_licitacoes = forms.ModelChoiceField(
        queryset=Setor.objects, label='Setor de Licitações (DILIC)', widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS), required=False
    )
    setor_proju = forms.ModelChoiceField(
        queryset=Setor.objects,
        label='Setor Jurídico',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
        required=False,
        help_text='Setor de destino para RDs com finalidade de Contratação/Aditivo sem parecer jurídico referencial.',
    )
    tipo_documento_requisicao_despesa = forms.ModelChoiceField(
        TipoDocumento.objects.filter(ativo=True),
        label='Tipo de Documento para Requisição de Despesa',
        required=False,
    )
    codigo_unidade_orcamentaria = forms.CharFieldPlus(
        label='Código da Unidade Orçamentária da Instituição',
        max_length=5,
        required=False,
        help_text='Código SIAFI da UO (gestão) da instituição, ex.: 26435. Restringe os empenhos sem requisição às NEs desta UO.',
    )


class PDIForm(forms.ModelFormPlus):
    ano_inicial_pdi = forms.ModelChoiceField(label='Ano Inicial', help_text='Vigência inicial do PDI', queryset=Ano.objects)
    ano_final_pdi = forms.ModelChoiceField(label='Ano Final', help_text='Vigência final do PDI', queryset=Ano.objects)
    qtd_anos = forms.IntegerField(label='Duração do PDI em anos')

    class Meta:
        model = PDI
        fields = ('qtd_anos', 'ano_inicial_pdi', 'ano_final_pdi', 'documento', 'mapa_estrategico', 'manual')

    def clean(self):
        super().clean()
        if 'ano_inicial_pdi' in self.cleaned_data and 'ano_final_pdi' in self.cleaned_data:
            if self.cleaned_data['ano_inicial_pdi'].ano > self.cleaned_data['ano_final_pdi'].ano:
                self.add_error('ano_final_pdi', 'O ano final deve ser maior que o inicial.')

            elif (
                'qtd_anos' in self.cleaned_data
                and self.cleaned_data['qtd_anos']
                and self.cleaned_data['ano_final_pdi'].ano - self.cleaned_data['ano_inicial_pdi'].ano != (self.cleaned_data['qtd_anos'] - 1)
            ):
                self.add_error('ano_final_pdi', 'O período não corresponde a duração do PDI.')

        return self.cleaned_data


class PerspectivaForm(forms.ModelFormPlus):
    class Meta:
        model = Perspectiva
        fields = ('sigla', 'nome', 'descricao')


class AssociarPerspectivaPDIForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    perspectivas = forms.MultipleModelChoiceField(
        Perspectiva.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/perspectivas_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)

        m_initial = PDIPerspectiva.objects.filter(pdi=self.pdi).values_list('perspectiva__pk', flat=True)

        qs = Perspectiva.objects.all()

        self.fields['perspectivas'].queryset = qs
        self.fields['perspectivas'].initial = m_initial

    @transaction.atomic()
    def save(self):
        # Adiciona as perspectivas novas
        m_ids = []
        for perspectiva in self.cleaned_data['perspectivas']:
            m_ids.append(perspectiva.pk)
            if not PDIPerspectiva.objects.filter(pdi=self.pdi, perspectiva=perspectiva).exists():
                PDIPerspectiva.objects.create(pdi=self.pdi, perspectiva=perspectiva)

        for pdi_perspectiva in PDIPerspectiva.objects.filter(pdi=self.pdi).exclude(perspectiva__pk__in=m_ids):
            pdi_perspectiva.delete()


class AssociarObjetivoPDIForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    objetivos = forms.MultipleModelChoiceField(
        queryset=ObjetivoEstrategico.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/objetivos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        self.pdi_perspectiva = kwargs.pop('perspectiva')

        super().__init__(*args, **kwargs)

        selecionados = PDIObjetivoEstrategico.objects.filter(pdi_perspectiva=self.pdi_perspectiva).values_list('objetivo__pk', flat=True)
        qs = ObjetivoEstrategico.objects.filter(
            Q(pdiobjetivoestrategico__isnull=True) | Q(pdiobjetivoestrategico__pdi_perspectiva=self.pdi_perspectiva)
        )
        self.fields['objetivos'].queryset = qs

        if selecionados:
            self.fields['objetivos'].initial = selecionados

    @transaction.atomic()
    def save(self):
        m_ids = []
        for objetivo in self.cleaned_data['objetivos']:
            m_ids.append(objetivo.pk)
            if not PDIObjetivoEstrategico.objects.filter(pdi_perspectiva=self.pdi_perspectiva, objetivo=objetivo).exists():
                PDIObjetivoEstrategico.objects.create(pdi_perspectiva=self.pdi_perspectiva, objetivo=objetivo)

        for pdi_objetivo in PDIObjetivoEstrategico.objects.filter(pdi_perspectiva=self.pdi_perspectiva).exclude(objetivo__pk__in=m_ids):
            pdi_objetivo.delete()


class AssociarIndicadorPDIForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    indicadores = forms.MultipleModelChoiceField(
        Indicador.objects.filter(nivel_rede=False), label='', required=False, widget=RenderableSelectMultiple('widgets/indicadores_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.pdi = kwargs.pop('pdi')
        self.pdi_objetivo = kwargs.pop('objetivo')
        super().__init__(*args, **kwargs)

        selecionados = PDIIndicador.objects.filter(objetivos=self.pdi_objetivo).values_list('indicador__pk', flat=True)

        self.fields['indicadores'].querset = Indicador.objects.filter(nivel_rede=False)
        self.fields['indicadores'].initial = selecionados

    @transaction.atomic()
    def save(self):
        m_ids = []

        for indicador in self.cleaned_data['indicadores']:
            m_ids.append(indicador.pk)
            if not PDIIndicador.objects.filter(pdi=self.pdi, indicador=indicador).exists():
                pdi_indicador = PDIIndicador.objects.create(pdi=self.pdi, indicador=indicador)
                pdi_indicador.objetivos.add(self.pdi_objetivo)

                ObjetivoIndicador.objects.create(indicador=pdi_indicador, objetivo_estrategico=self.pdi_objetivo, relevancia=0)
            else:
                pdi_indicador = PDIIndicador.objects.get(pdi=self.pdi, indicador=indicador)
                if not pdi_indicador.objetivos.filter(id=self.pdi_objetivo.pk).exists():
                    pdi_indicador.objetivos.add(self.pdi_objetivo)
                    objetivo_indicador = ObjetivoIndicador.objects.filter(indicador=pdi_indicador, objetivo_estrategico=self.pdi_objetivo)
                    if objetivo_indicador.exists():
                        objetivo_indicador[0].relevancia = 0
                    else:
                        ObjetivoIndicador.objects.create(indicador=pdi_indicador, objetivo_estrategico=self.pdi_objetivo, relevancia=0)

        for pdi_indicador in PDIIndicador.objects.filter(pdi=self.pdi, objetivos=self.pdi_objetivo).exclude(indicador__pk__in=m_ids):
            pdi_indicador.objetivos.remove(self.pdi_objetivo)
            ObjetivoIndicador.objects.filter(indicador=pdi_indicador, objetivo_estrategico=self.pdi_objetivo).delete()


class UnidadeGestoraForm(forms.ModelFormPlus):
    setor_equivalente = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor',
        help_text='Setor que responde pela unidade gestora',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    setor_financeiro = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor responsável financeiro',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    setor_administrativo = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor Responsável Administrativo',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    setor_ordenador_despesa = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor responsável ordenador de despesa',
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    setor_anuencia_despesa = forms.ModelChoiceFieldPlus2(
        label_template='{{obj.sigla|rjust:"15"}} - {{obj.nome}}',
        label='Setor Anuência da Despesa',
        required=False,
        queryset=Setor.objects.suap_ativos().all().order_by('sigla', 'nome'),
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )

    class Meta:
        model = UnidadeGestora
        fields = (
            'tipo',
            'setor_equivalente',
            'setor_financeiro',
            'setor_administrativo',
            'setor_ordenador_despesa',
            'setor_anuencia_despesa',
            'codigo_projeto',
            'codigo_macroprocesso',
            'codigo_ug',
            'codigo_ugr',
            'ug_secundaria',
            'recurso_total',
        )

    def __init__(self, *args, **kwargs):
        pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)
        self.instance.pdi = pdi

    def clean(self):
        if not self.errors:
            if self.cleaned_data['setor_equivalente']:
                if (
                    UnidadeGestora.objects.filter(setor_equivalente=self.cleaned_data['setor_equivalente'], pdi=self.instance.pdi)
                    .exclude(pk=self.instance.pk)
                    .exists()
                ):
                    self.add_error('setor_equivalente', 'Unidade Gestora com este Setor Equivalente já existe para este PDI.')
            if self.cleaned_data['tipo'] == UnidadeGestora.TIPO_GESTOR_SISTEMICO and self.cleaned_data['codigo_macroprocesso'] is None:
                self.add_error('codigo_macroprocesso', 'Este campo é obrigatório para o tipo de unidade gestora selecionado.')
            if 'codigo_macroprocesso' in self.cleaned_data:
                if self.cleaned_data['tipo'] == UnidadeGestora.TIPO_GESTOR_SISTEMICO and len(self.cleaned_data['codigo_macroprocesso']) != 2:
                    self.add_error('codigo_macroprocesso', 'O código de macroprocesso deve conter 2 letras.')
        return self.cleaned_data


class AtividadeEtapaForm(forms.ModelFormPlus):
    origem_recurso_etapa = forms.ModelChoiceFieldPlus2(
        label='Origem de recurso',
        help_text='Origem de recurso do componente funcional',
        queryset=OrigemRecursoProjetoEtapa.objects.all(),
        required=False,
    )

    naturezadespesa = forms.ModelChoiceFieldPlus2(
        label='Natureza de despesa',
        queryset=NaturezaDespesaPlanoAtividade.objects.all(),
        required=False,
        widget=AutocompleteWidget(search_fields=NaturezaDespesaPlanoAtividade.SEARCH_FIELDS),
    )

    unidade_gestora = forms.ModelChoiceFieldPlus2(
        label='Unidade gestora',
        queryset=UnidadeGestora.objects.all(),
        required=False,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS, readonly=True),
    )

    valor = forms.DecimalFieldPlus(label='Valor Proposto R$', required=False)

    class Meta:
        model = AtividadeEtapa
        fields = ('nome', 'descricao', 'valor', 'origem_recurso_etapa', 'naturezadespesa', 'plano_interno', 'unidade_gestora')

    def __init__(self, *args, **kwargs):
        etapa = kwargs.pop('etapa')
        super().__init__(*args, **kwargs)
        self.instance.etapa_projeto_plano_atividade = etapa

        naturezas_planoatividade = NaturezaDespesaPlanoAtividade.objects.filter(
            plano_atividade=self.instance.etapa_projeto_plano_atividade.projeto_plano_atividade.plano_atividade
        )
        self.fields['naturezadespesa'].queryset = naturezas_planoatividade

        self.fields['plano_interno'].queryset = PlanoInternoPlanoAtividade.objects.filter(
            plano_interno__projeto_estrategico__codigo=self.instance.etapa_projeto_plano_atividade.projeto_plano_atividade.projeto.codigo,
            plano_atividade=self.instance.etapa_projeto_plano_atividade.projeto_plano_atividade.plano_atividade,
        )
        # sobrescrevendo o querySet de origem_recurso_etapa
        qs = OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade=self.instance.etapa_projeto_plano_atividade)

        self.fields['origem_recurso_etapa'].queryset = qs

        qs = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))[0]

        self.fields['unidade_gestora'].initial = qs
        self.fields['valor'].initial = Decimal(0)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('valor') is None:
            self.add_error('valor', 'Informe um valor')
        origem_recurso_etapa = cleaned_data.get('origem_recurso_etapa')
        natureza_despesa_atividade = cleaned_data.get('naturezadespesa')
        plano_interno = cleaned_data.get('plano_interno')
        if origem_recurso_etapa is None:
            self.add_error('origem_recurso_etapa', 'Selecione uma origem de recurso')
        if not natureza_despesa_atividade:
            self.add_error('naturezadespesa', 'Selecione uma natureza de despesa')
        if plano_interno is None:
            self.add_error('plano_interno', 'Selecione um plano interno')
        if origem_recurso_etapa and natureza_despesa_atividade:
            origem_gnd_codigo = origem_recurso_etapa.origem_recurso_projeto.origem_recurso.gnd.codigo
            natureza_gnd_codigo = natureza_despesa_atividade.natureza_despesa.grupo_natureza_despesa.codigo
            if origem_gnd_codigo != natureza_gnd_codigo:
                self.add_error('naturezadespesa', 'A natureza de despesa e a origem de recurso devem ter o mesmo GND.')
        if origem_recurso_etapa and plano_interno:
            if origem_recurso_etapa.origem_recurso_projeto.__str__() != plano_interno.plano_interno.codigo_origemrecurso:
                self.add_error('plano_interno', 'A origem de recurso do plano interno deve ser igual a origem de recurso selecionada.')
        return cleaned_data


class ProjetoEstrategicoPDIForm(forms.ModelFormPlus):
    objetivo_estrategico = forms.ModelMultipleChoiceField(
        label='Objetivo Estratégico', required=True, widget=FilteredSelectMultiplePlus('', True), queryset=PDIObjetivoEstrategico.objects.all()
    )
    data_inicio = forms.DateFieldPlus(label='Data Inicial')
    data_fim = forms.DateFieldPlus(label='Data Final')
    recurso_total = forms.DecimalFieldPlus(label='Recurso Total', initial=0)

    fieldsets = (
        (None, {'fields': (('nome',),)}),
        (None, {'fields': (('descricao',),)}),
        ('', {'fields': (('meta_projeto', 'unidade_medida'),)}),
        ('', {'fields': (('objetivo_estrategico',),)}),
        ('', {'fields': (('data_inicio', 'data_fim', 'tipo'),)}),
        ('', {'fields': (('unidade_gestora', 'recurso_total', 'anexo'),)}),
    )

    class Meta:
        model = ProjetoEstrategico
        fields = (
            'nome',
            'descricao',
            'objetivo_estrategico',
            'unidade_gestora',
            'recurso_total',
            'meta_projeto',
            'unidade_medida',
            'anexo',
            'data_inicio',
            'data_fim',
            'tipo',
        )

    def __init__(self, *args, **kwargs):
        pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)
        self.instance.pdi = pdi
        if self.instance.pk:
            self.initial['objetivo_estrategico'] = [o.pk for o in self.instance.objetivo_estrategico.all()]

        # Exibe apenas as unidades gestores do tipo Pró-Reitoria e Diretoria Sistêmica
        qs = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))
        self.fields['unidade_gestora'].queryset = qs

    def clean(self):
        super().clean()

        if 'data_inicio' in self.cleaned_data and 'data_fim' in self.cleaned_data:
            if self.cleaned_data['data_inicio'] > self.cleaned_data['data_fim']:
                self.add_error('data_fim', 'A data final deve ser maior que a data inicial.')

        return self.cleaned_data


class MacroprocessoPDIForm(forms.ModelFormPlus):
    objetivo_estrategico = forms.ModelMultipleChoiceField(
        label='Objetivo Estratégico', required=True, widget=FilteredSelectMultiplePlus('', True), queryset=PDIObjetivoEstrategico.objects.all()
    )
    fieldsets = (
        (None, {'fields': (('nome',),)}),
        ('', {'fields': (('objetivo_estrategico',),)}),
        ('', {'fields': (('unidade_gestora',),)}),
    )

    class Meta:
        model = ProjetoEstrategico
        fields = ('nome', 'objetivo_estrategico', 'unidade_gestora')

    def __init__(self, *args, **kwargs):
        pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)
        self.instance.pdi = pdi
        if self.instance.pk:
            self.initial['objetivo_estrategico'] = [o.pk for o in self.instance.objetivo_estrategico.all()]
        if self.instance.pk and ProjetoPlanoAtividade.objects.filter(projeto=self.instance).exists():
            self.fields['nome'].widget.attrs['readonly'] = 'readonly'
            self.fields['unidade_gestora'].widget.attrs['readonly'] = 'readonly'

        # A IMPLEMENTAR Exibe apenas as unidades gestoras com Macroprocesso cadastrado
        qs = UnidadeGestora.objects.filter(codigo_macroprocesso__isnull=False)
        self.fields['unidade_gestora'].queryset = qs

    def clean(self):
        super().clean()
        return self.cleaned_data


class EtapaProjetoForm(forms.ModelFormPlus):
    data_inicio = forms.DateFieldPlus(label='Data inicial do componente funcional')
    data_fim = forms.DateFieldPlus(label='Data final do componente funcional')

    class Meta:
        model = EtapaProjeto
        fields = (
            'codigo',
            'descricao',
            'data_inicio',
            'data_fim',
            'objetivo_etapa',
            'responsaveis_etapa',
            'meta_etapa',
            'unidade_medida',
            'valor_etapa',
        )

    def __init__(self, *args, **kwargs):
        projeto = kwargs.pop('projeto')
        super().__init__(*args, **kwargs)
        self.instance.projeto = projeto

        q_etapas = EtapaProjeto.objects.filter(projeto=self.instance.projeto).count()
        if self.instance.pk:
            self.fields['codigo'].initial = self.instance.codigo
        else:
            self.fields['codigo'].initial = q_etapas + 1

    def clean(self):
        super().clean()
        if 'codigo' in self.cleaned_data:
            if not self.instance.pk or (self.instance.pk and self.instance.codigo != self.cleaned_data['codigo']):
                if EtapaProjeto.objects.filter(projeto=self.instance.projeto, codigo=self.cleaned_data['codigo']).exists():
                    self.add_error('codigo', 'Este código já está sendo usado por outro componente funcional deste macroprocesso.')
        if 'data_inicio' in self.cleaned_data and 'data_fim' in self.cleaned_data:
            if self.cleaned_data['data_inicio'] > self.cleaned_data['data_fim']:
                self.add_error('data_fim', 'A data final deve ser maior que a data inicial.')
        if 'valor_etapa' in self.cleaned_data:
            if (self.instance.projeto.get_saldo_projeto() + (self.instance.valor_etapa or 0)) < self.cleaned_data['valor_etapa']:
                self.add_error('valor_etapa', 'Valor do componente funcional maior que o saldo do macroprocesso.')
        return self.cleaned_data


class ProcessoForm(forms.ModelFormPlus):
    class Meta:
        model = EtapaProjeto
        fields = (
            'codigo',
            'descricao',
        )

    def __init__(self, *args, **kwargs):
        macroprocesso = kwargs.pop('macroprocesso')
        super().__init__(*args, **kwargs)
        self.instance.projeto = macroprocesso

        q_processos = EtapaProjeto.objects.filter(projeto=self.instance.projeto).count()
        if self.instance.pk:
            self.fields['codigo'].initial = self.instance.codigo
        else:
            self.fields['codigo'].initial = q_processos + 1

    def clean(self):
        super().clean()
        if 'codigo' in self.cleaned_data:
            if not self.instance.pk or (self.instance.pk and self.instance.codigo != self.cleaned_data['codigo']):
                if EtapaProjeto.objects.filter(projeto=self.instance.projeto, codigo=self.cleaned_data['codigo']).exists():
                    self.add_error('codigo', 'Este código já está sendo usado por outro componente funcional deste macroprocesso.')
        return self.cleaned_data


def MetaIndicadorFormFactory(indicador):
    class MetaIndicadorForm(forms.FormPlus):
        valor_referencia = forms.DecimalField(label='Referência', initial=indicador.get_valor_referencia, decimal_places=indicador.casas_decimais)

        SUBMIT_LABEL = 'Atualizar Metas'

        fieldsets = [
            (
                None,
                {
                    'fields': (
                        'valor_referencia',
                        'valor_referencia0',
                        'valor_referencia1',
                        'valor_referencia2',
                        'valor_referencia3',
                        'valor_referencia4',
                    )
                },
            )
        ]

        def save(self):
            self.indicador.valor_referencia = self.cleaned_data['valor_referencia']
            self.indicador.save()

            for nome in list(self.cleaned_data.keys()):
                if not nome.startswith('meta_ano'):
                    continue
                meta = MetaIndicador.objects.get(indicador=self.indicador, ano=nome.split('_')[-1])
                meta.meta = self.cleaned_data[nome]
                meta.save()

    MetaIndicadorForm.indicador = indicador

    fs_fields = []

    for meta in indicador.metaindicador_set.all():
        field_name = f'meta_ano_{meta.ano}'
        fs_fields.append(field_name)
        MetaIndicadorForm.base_fields[field_name] = forms.DecimalField(
            label=f'{meta.ano}', initial=meta.get_valor_meta, decimal_places=indicador.casas_decimais
        )

    MetaIndicadorForm.fieldsets.append(('Anuais', {'fields': fs_fields}))

    return MetaIndicadorForm


def ObjetivoIndicadorFormFactory(objetivo):
    class ObjetivoIndicadorForm(forms.FormPlus):
        SUBMIT_LABEL = 'Atualizar Relevâncias'

        fieldsets = [
            (
                None,
                {
                    'fields': (
                        'valor_relevancia',
                        'valor_relevancia0',
                        'valor_relevancia1',
                        'valor_relevancia2',
                        'valor_relevancia3',
                        'valor_relevancia4',
                    )
                },
            )
        ]

        def clean(self):
            super().clean()
            total = 0
            for nome in list(self.cleaned_data.keys()):
                total += self.cleaned_data[nome]
            if total > 100:
                self.add_error('', ' Percentuais maior que 100%')
            elif total < 100:
                self.add_error('', ' Percentuais menor que 100%')
            return self.cleaned_data

        def save(self):
            for nome in list(self.cleaned_data.keys()):
                if not nome.startswith('objetivoindicador'):
                    continue
                objetivo_indicador = ObjetivoIndicador.objects.get(indicador=nome.split('_')[-1], objetivo_estrategico=self.objetivo)
                objetivo_indicador.relevancia = self.cleaned_data[nome]
                objetivo_indicador.save()

    ObjetivoIndicadorForm.objetivo = objetivo

    fs_fields = []
    for objetivo_indicador in objetivo.objetivoindicador_set.all().order_by('id'):
        field_name = f'objetivoindicador_{objetivo_indicador.indicador.id}'
        fs_fields.append(field_name)
        ObjetivoIndicadorForm.base_fields[field_name] = forms.DecimalField(
            label=f'{objetivo_indicador.indicador}', initial=objetivo_indicador.relevancia, decimal_places=objetivo_indicador.indicador.casas_decimais
        )

    ObjetivoIndicadorForm.fieldsets.append(('indicadores', {'fields': fs_fields}))

    return ObjetivoIndicadorForm


def farol_filtro_formfactory(pdi, sigla_instituicao):
    ano_choices = [[ano, ano] for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1)]

    class FarolFiltro1Form(forms.FormPlus):
        ano = forms.ChoiceField(label='Ano', choices=ano_choices, required=True)
        perspectiva = forms.ModelChoiceField(label='Perspectiva', queryset=Perspectiva.objects, required=False)
        campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=False, empty_label=sigla_instituicao)

        def __init__(self, *args, **kwargs):
            pdi = kwargs.pop('pdi')
            ano_base = kwargs.pop('ano_base')

            uo = kwargs.pop('uo')
            self.base_fields['ano'].initial = ano_base
            if uo:
                self.base_fields['campus'].initial = uo.id
            super().__init__(*args, **kwargs)

            choices = []
            for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano):
                choices.append((ano, ano))

            self.base_fields['ano'].choices = choices

    return FarolFiltro1Form


def farol_indicadores_filtro_formfactory(pdi, sigla_instituicao, objetivo):
    ano_choices = [[ano, ano] for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1)]

    class FarolFiltro2Form(forms.FormPlus):
        ano = forms.ChoiceField(label='Ano', choices=ano_choices, required=True)
        campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=False, empty_label=sigla_instituicao)
        indicador = forms.ModelChoiceField(label='Indicador', queryset=PDIIndicador.objects.filter(pdi=pdi), required=False)

        def __init__(self, *args, **kwargs):
            pdi = kwargs.pop('pdi')
            ano_base = kwargs.pop('ano_base')
            uo = kwargs.pop('uo')

            self.base_fields['ano'].initial = ano_base
            if uo:
                self.base_fields['campus'].initial = uo.id
            self.base_fields['indicador'].queryset = PDIIndicador.objects.filter(objetivoindicador__objetivo_estrategico=objetivo, pdi=pdi)
            super().__init__(*args, **kwargs)

            choices = []
            for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano):
                choices.append((ano, ano))

            self.base_fields['ano'].choices = choices
            self.base_fields['ano'].initial = ano_base

    return FarolFiltro2Form


class VariavelCampusForm(forms.ModelFormPlus):
    class Meta:
        model = VariavelCampus
        fields = ('valor_trimestral',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class VariavelCampusIdealForm(forms.ModelFormPlus):
    class Meta:
        model = VariavelCampus
        fields = ('valor_ideal',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ArquivoMetaForm(forms.ModelFormPlus):
    class Meta:
        model = ArquivoMeta
        fields = ('arquivo',)

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo and hasattr(arquivo, 'file'):
            try:
                df = ler_planilha_metas(arquivo)
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(f'Não foi possível ler a planilha enviada: {e}')
            finally:
                arquivo.seek(0)
            validar_planilha_metas(df)
            self.instance.planilha_metas_validada = df
        return arquivo


# retorna um choice contendo os anos que ainda não foram cadastrados
def anos_disponiveis_as_choices(id_pdi):
    pdi = PDI.objects.get(pk=id_pdi)
    anos_cadastrados = list(PlanoAtividade.objects.filter(pdi=id_pdi).values_list('ano_base__ano', flat=True))

    total_anos = list(range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1))
    for ano in anos_cadastrados:
        if ano == total_anos:
            continue
        if ano in total_anos:
            total_anos.remove(ano)
    anos = Ano.objects.filter(ano__in=total_anos)
    return anos


class PlanoAtividadePDIForm(forms.ModelFormPlus):
    ano_base = forms.ModelChoiceField(label='Ano Base', help_text='Ano de realização das atividades', queryset=Ano.objects.all())
    data_geral_inicial = forms.DateFieldPlus(label='Início')
    data_geral_final = forms.DateFieldPlus(label='Fim')
    data_orcamentario_preloa_inicial = forms.DateFieldPlus(label='Início Orçamentário')
    data_orcamentario_preloa_final = forms.DateFieldPlus(label='Fim Orçamentário')
    data_projetos_preloa_inicial = forms.DateFieldPlus(label='Início Macroprocessos')
    data_projetos_preloa_final = forms.DateFieldPlus(label='Fim Macroprocessos')
    data_atividades_preloa_inicial = forms.DateFieldPlus(label='Início Atividades')
    data_atividades_preloa_final = forms.DateFieldPlus(label='Fim Atividades')
    data_orcamentario_posloa_inicial = forms.DateFieldPlus(label='Início Orçamentário')
    data_orcamentario_posloa_final = forms.DateFieldPlus(label='Fim Orçamentário')
    data_projetos_posloa_inicial = forms.DateFieldPlus(label='Início Macroprocessos')
    data_projetos_posloa_final = forms.DateFieldPlus(label='Fim Macroprocessoss')
    data_atividades_posloa_inicial = forms.DateFieldPlus(label='Início Atividades')
    data_atividades_posloa_final = forms.DateFieldPlus(label='Fim atividades')
    percentual_reserva_tecnica = forms.IntegerField(label='Percentual Reserva Técnica')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # se o pdi foi passado via url (get method) ou se trata de uma edição
        if 'pdi' in self.request.GET:
            pdi_id = self.request.GET['pdi']
            pdi = PDI.objects.get(id=pdi_id)
            self.fields['ano_base'].queryset = anos_disponiveis_as_choices(pdi_id)
            self.fields['pdi'] = ReadOnlyField(label='PDI')
            self.fields['pdi'].initial = pdi
            self.fields['pdi'].widget.display_value = str(pdi)

        if self.instance.pk:
            self.fields['ano_base'].initial = self.instance.ano_base
            queryset = anos_disponiveis_as_choices(self.instance.pdi.id)
            self.fields['ano_base'].queryset = queryset | Ano.objects.filter(id=self.instance.ano_base.id)
            pdi = self.instance.pdi
            self.fields['pdi'] = ReadOnlyField(label='PDI')
            self.fields['pdi'].initial = pdi
            self.fields['pdi'].widget.display_value = str(pdi)

    def clean(self):
        errors = {}
        if not self.errors:
            if self.cleaned_data['percentual_reserva_tecnica']:
                if self.cleaned_data['percentual_reserva_tecnica'] > 100 or self.cleaned_data['percentual_reserva_tecnica'] < 0:
                    self.add_error('percentual_reserva_tecnica', 'O Percentual da reserva técnica deve estar compreendido entre 0 e 100.')

            if self.cleaned_data['data_geral_final'] <= self.cleaned_data['data_geral_inicial']:
                self.add_error('data_geral_final', 'A data final não pode ser menor ou igual à data inicial.')

            if not self.cleaned_data.get('data_orcamentario_preloa_inicial') < self.cleaned_data.get('data_orcamentario_preloa_final'):
                errors['data_orcamentario_preloa_inicial'] = ['Esta data deve ser menor que a data final da fase Pré-LOA Orçamentária.']

            if (
                not self.cleaned_data.get('data_orcamentario_preloa_inicial')
                < self.cleaned_data.get('data_orcamentario_preloa_final')
                < self.cleaned_data.get('data_projetos_preloa_inicial')
            ):
                errors['data_orcamentario_preloa_final'] = [
                    'Esta data deve ser maior que a data inicial da fase Pré-LOA Orçamentária e menor que a data inicial da fase Pré-LOA de macroprocessos.'
                ]

            if (
                not self.cleaned_data.get('data_orcamentario_preloa_final')
                < self.cleaned_data.get('data_projetos_preloa_inicial')
                < self.cleaned_data.get('data_projetos_preloa_final')
            ):
                errors['data_projetos_preloa_inicial'] = [
                    'Esta data deve ser maior que a data final da fase Pré-LOA Orçamentária e menor que a data final da fase Pré-LOA de macroprocessos.'
                ]

            if (
                not self.cleaned_data.get('data_projetos_preloa_inicial')
                < self.cleaned_data.get('data_projetos_preloa_final')
                < self.cleaned_data.get('data_atividades_preloa_inicial')
            ):
                errors['data_projetos_preloa_final'] = [
                    'Esta data deve ser maior que a data inicial da fase Pré-LOA de macroprocessos e menor que a data inicial da fase Pré-LOA de atividades.'
                ]

            if (
                not self.cleaned_data.get('data_projetos_preloa_final')
                < self.cleaned_data.get('data_atividades_preloa_inicial')
                < self.cleaned_data.get('data_atividades_preloa_final')
            ):
                errors['data_atividades_preloa_inicial'] = [
                    'Esta data deve ser maior que a data final da fase Pré-LOA de macroprocessos e menor que a data final da fase Pré-LOA de atividades.'
                ]

            if (
                not self.cleaned_data.get('data_atividades_preloa_inicial')
                < self.cleaned_data.get('data_atividades_preloa_final')
                < self.cleaned_data.get('data_orcamentario_posloa_inicial')
            ):
                errors['data_atividades_preloa_final'] = [
                    'Esta data deve ser maior que a data inicial da fase Pré-LOA de atividades e menor que a data inicial da fase Pós-LOA de Orçamentária.'
                ]

            if (
                not self.cleaned_data.get('data_atividades_preloa_final')
                < self.cleaned_data.get('data_orcamentario_posloa_inicial')
                < self.cleaned_data.get('data_orcamentario_posloa_final')
            ):
                errors['data_orcamentario_posloa_inicial'] = [
                    'Esta data deve ser maior que a data final da fase Pré-LOA de atividades e menor que a data final da fase Pós-LOA de Orçamentária.'
                ]

            if (
                not self.cleaned_data.get('data_orcamentario_posloa_inicial')
                < self.cleaned_data.get('data_orcamentario_posloa_final')
                < self.cleaned_data.get('data_projetos_posloa_inicial')
            ):
                errors['data_orcamentario_posloa_final'] = [
                    'Esta data deve ser maior que a data inicial da fase Pós-LOA Orçamentária e menor que a data final da fase Pós-LOA de macroprocessos.'
                ]

            if (
                not self.cleaned_data.get('data_orcamentario_posloa_final')
                < self.cleaned_data.get('data_projetos_posloa_inicial')
                < self.cleaned_data.get('data_projetos_posloa_final')
            ):
                errors['data_projetos_posloa_inicial'] = [
                    'Esta data deve ser maior que a data final da fase Pós-LOA Orçamentária e menor que a data inicial da fase Pós-LOA de macroprocessos.'
                ]

            if (
                not self.cleaned_data.get('data_projetos_posloa_inicial')
                < self.cleaned_data.get('data_projetos_posloa_final')
                < self.cleaned_data.get('data_atividades_posloa_inicial')
            ):
                errors['data_projetos_posloa_final'] = [
                    'Esta data deve ser maior que a data inicial da fase Pós-LOA macroprocessos e menor que a data inicial da fase Pós-LOA de atividades.'
                ]

            if (
                not self.cleaned_data.get('data_projetos_posloa_final')
                < self.cleaned_data.get('data_atividades_posloa_inicial')
                < self.cleaned_data.get('data_atividades_posloa_final')
            ):
                errors['data_atividades_posloa_inicial'] = [
                    'Esta data deve ser maior que a data final da fase Pós-LOA macroprocessos e menor que a data final da fase Pós-LOA de atividades.'
                ]

            if (
                not self.cleaned_data.get('data_atividades_posloa_inicial')
                < self.cleaned_data.get('data_atividades_posloa_final')
                < self.cleaned_data.get('data_geral_final')
            ):
                errors['data_atividades_posloa_final'] = [
                    'Esta data deve ser maior que a data inicial da fase Pós-LOA atividades e menor que a data final do plano de atividades.'
                ]

        if errors:
            raise ValidationError(errors)
        return self.cleaned_data


class OrigemRecursoForm(forms.ModelFormPlus):
    acao_financeira = forms.ModelChoiceFieldPlus(
        label='Ação Orçamentária',
        help_text='',
        queryset=AcaoAno.objects,
        widget=AutocompleteWidget(label_value='codigo_e_ptres', search_fields=AcaoAno.SEARCH_FIELDS),
    )

    class Meta:
        model = OrigemRecurso
        fields = ('acao_financeira', 'gnd')

    def __init__(self, *args, **kwargs):
        self.plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        self.instance.plano_atividade = self.plano_atividade

        self.fields['acao_financeira'].queryset = AcaoAno.objects.filter(ano_base=self.plano_atividade.ano_base)


class NaturezaDespesaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'
    naturezas_despesa = forms.MultipleModelChoiceField(
        NaturezaDespesa.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/naturezas_despesa_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        nat_initial = NaturezaDespesaPlanoAtividade.objects.filter(plano_atividade=self.plano_atividade).values_list(
            'natureza_despesa__pk', flat=True
        )

        qs = NaturezaDespesa.objects.all()

        self.fields['naturezas_despesa'].queryset = qs
        self.fields['naturezas_despesa'].initial = nat_initial

    @transaction.atomic()
    def save(self):
        # Adiciona as naturezas de despesas novas
        nat_ids = []
        for natureza in self.cleaned_data['naturezas_despesa']:
            nat_ids.append(natureza.pk)
            if not NaturezaDespesaPlanoAtividade.objects.filter(plano_atividade=self.plano_atividade, natureza_despesa=natureza).exists():
                NaturezaDespesaPlanoAtividade.objects.create(plano_atividade=self.plano_atividade, natureza_despesa=natureza)

        for natureza in NaturezaDespesaPlanoAtividade.objects.filter(plano_atividade=self.plano_atividade).exclude(natureza_despesa__pk__in=nat_ids):
            natureza.delete()


class PlanoInternoPlanoAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'
    plano_interno = forms.MultipleModelChoiceField(
        PlanoInterno.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/planos_internos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        pi_initial = PlanoInternoPlanoAtividade.objects.filter(plano_atividade=self.plano_atividade).values_list('plano_interno__pk', flat=True)

        qs = PlanoInterno.objects.all()

        self.fields['plano_interno'].queryset = qs
        self.fields['plano_interno'].initial = pi_initial

    @transaction.atomic()
    def save(self):
        # Adiciona os planos internos ao plano de atividade
        pi_ids = []
        for pi in self.cleaned_data['plano_interno']:
            pi_ids.append(pi.pk)
            if not PlanoInternoPlanoAtividade.objects.filter(plano_atividade=self.plano_atividade, plano_interno=pi).exists():
                PlanoInternoPlanoAtividade.objects.create(plano_atividade=self.plano_atividade, plano_interno=pi)

        for pi in PlanoInternoPlanoAtividade.objects.filter(plano_atividade=self.plano_atividade).exclude(plano_interno__pk__in=pi_ids):
            pi.delete()


class AssociarProjetosPlanoAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    # projetos selecionados
    projetos = forms.MultipleModelChoiceField(
        queryset=ProjetoEstrategico.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/projetos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.plano = kwargs.pop('plano')
        self.servidor = kwargs.pop('servidor')

        super().__init__(*args, **kwargs)
        # recupera todos os projetos do plano de atividade
        m_initial = ProjetoPlanoAtividade.objects.filter(
            plano_atividade=self.plano, projeto__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=self.servidor)
        ).values_list('projeto__pk', flat=True)

        qs = ProjetoEstrategico.objects.filter(macroprocesso=True, unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=self.servidor))

        # Carrega todos os projetos
        self.fields['projetos'].queryset = qs.exclude(id__in=m_initial)

        # Seleciona os projetos que já foram salvos
        self.fields['projetos'].initial = m_initial

    def clean(self):
        selecionados_ids = []
        projetos = self.cleaned_data.get('projetos', None)
        if projetos is None or len(projetos) == 0:
            raise forms.ValidationError('Selecione pelo menos um macroprocesso.')

        for projeto in projetos:
            selecionados_ids.append(projeto.pk)

        return self.cleaned_data

    @transaction.atomic()
    def save(self):
        # lista de novos projetos
        selecionados_ids = []
        # itera sobre os projetos selecionados
        for projeto in self.cleaned_data['projetos']:
            selecionados_ids.append(projeto.pk)
            # se o projeto corrente selecionado ainda não foi salvo, salva.
            if not ProjetoPlanoAtividade.objects.filter(plano_atividade=self.plano, projeto=projeto).exists():
                ProjetoPlanoAtividade.objects.create(plano_atividade=self.plano, projeto=projeto)


class AssociarEtapasProjetoPlanoAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    # etapas selecionados
    etapas = forms.MultipleModelChoiceField(
        queryset=EtapaProjeto.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/etapas_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.projeto_plano_atividade = kwargs.pop('projeto_plano_atividade')
        super().__init__(*args, **kwargs)

        # recupera todas as etapas do projeto do plano de atividade
        m_initial = EtapaProjetoPlanoAtividade.objects.filter(projeto_plano_atividade=self.projeto_plano_atividade).values_list(
            'etapa__pk', flat=True
        )
        qs = EtapaProjeto.objects.filter(projeto=self.projeto_plano_atividade.projeto).order_by('id')

        # Carrega todas as etapas
        self.fields['etapas'].queryset = qs.exclude(id__in=m_initial)

        # Seleciona os projetos que já foram salvos
        self.fields['etapas'].initial = m_initial

    @transaction.atomic()
    def save(self):
        # lista de novas etapas
        selecionadas_ids = []
        # itera sobre as etapas selecionadas
        for etapa in self.cleaned_data['etapas']:
            selecionadas_ids.append(etapa.pk)
            # se a etapa corrente selecionada ainda não foi salva, salva.
            if not EtapaProjetoPlanoAtividade.objects.filter(projeto_plano_atividade=self.projeto_plano_atividade, etapa=etapa).exists():
                EtapaProjetoPlanoAtividade.objects.create(projeto_plano_atividade=self.projeto_plano_atividade, etapa=etapa)


class AssociarOrigemRecursoProjetoPlanoAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    # Origens de recursos selecionados
    origens_recursos = forms.MultipleModelChoiceField(
        queryset=OrigemRecurso.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/origens_recursos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        self.projeto_plano_atividade = kwargs.pop('projeto_plano_atividade')
        super().__init__(*args, **kwargs)

        # recupera todas as origens de recurso do projeto do plano de atividade
        m_initial = OrigemRecursoProjeto.objects.filter(projeto_plano_atividade=self.projeto_plano_atividade).values_list(
            'origem_recurso__pk', flat=True
        )

        qs = OrigemRecurso.objects.filter(plano_atividade=self.projeto_plano_atividade.plano_atividade)

        # Carrega todas as origens de recursos
        self.fields['origens_recursos'].queryset = qs

        # Seleciona as origens que já foram salvas
        self.fields['origens_recursos'].initial = m_initial

    @transaction.atomic()
    def save(self):
        # lista de novas origens
        selecionadas_ids = []
        # itera sobre as origens selecionadas
        for origem_recurso in self.cleaned_data['origens_recursos']:
            selecionadas_ids.append(origem_recurso.pk)
            # se a origem de recurso corrente selecionada ainda não foi salva, salva.
            if not OrigemRecursoProjeto.objects.filter(projeto_plano_atividade=self.projeto_plano_atividade, origem_recurso=origem_recurso).exists():
                OrigemRecursoProjeto.objects.create(projeto_plano_atividade=self.projeto_plano_atividade, origem_recurso=origem_recurso)

        # Exclui todos os componentes funcionais que não estão selecionados
        for origem_recurso_projeto in OrigemRecursoProjeto.objects.filter(projeto_plano_atividade=self.projeto_plano_atividade).exclude(
            origem_recurso__pk__in=selecionadas_ids
        ):
            origem_recurso_projeto.delete()


class OrigemRecursoEspecialForm(forms.Form):
    origens_recurso = forms.ModelChoiceField(queryset=OrigemRecursoProjetoEtapa.objects, label='Origem do componente funcional', required=True)

    def __init__(self, *args, **kwargs):
        self.etapa_projeto_plano_atividade = kwargs.pop('etapa_projeto_plano_atividade')
        super().__init__(*args, **kwargs)

        qs = OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade)
        self.fields['origens_recurso'].queryset = qs

    def save(self):
        origem_recurso_etapa = self.cleaned_data['origens_recurso']
        origem_recurso_etapa = OrigemRecursoProjetoEtapa.objects.filter(
            origem_recurso_projeto=origem_recurso_etapa.origem_recurso_projeto,
            etapa_projeto_plano_atividade=origem_recurso_etapa.etapa_projeto_plano_atividade,
        )[0]
        origem_recurso_etapa.tipo_especial = True
        origem_recurso_etapa.save()
        origem_recurso_etapa.etapa_projeto_plano_atividade.tipo_especial = True
        origem_recurso_etapa.etapa_projeto_plano_atividade.save()


class AssociarOrigemRecursoEtapaProjetoPlanoAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    # Origens de recursos  selecionados
    origens_recursos_projetos = forms.MultipleModelChoiceField(
        queryset=OrigemRecursoProjeto.objects,
        label='',
        required=False,
        widget=RenderableSelectMultiple('widgets/origens_recursos_projetos_widget.html'),
    )

    def __init__(self, *args, **kwargs):
        self.etapa_projeto_plano_atividade = kwargs.pop('etapa_projeto_plano_atividade')
        super().__init__(*args, **kwargs)

        # recupera todas as origens de recurso da etapa do projeto do plano de atividade
        m_initial = OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade).values_list(
            'origem_recurso_projeto__pk', flat=True
        )

        # Mostra somente as origens de recursos do projeto que podem ser selecionadas na etapa
        qs = OrigemRecursoProjeto.objects.filter(projeto_plano_atividade_id=self.etapa_projeto_plano_atividade.projeto_plano_atividade)
        self.fields['origens_recursos_projetos'].queryset = qs

        # Seleciona as origens que já foram salvas
        self.fields['origens_recursos_projetos'].initial = m_initial

    @transaction.atomic()
    def save(self):
        # lista de novas origens
        selecionadas_ids = []
        # itera sobre as origens selecionadas
        for origem_recurso in self.cleaned_data['origens_recursos_projetos']:
            selecionadas_ids.append(origem_recurso.pk)
            # se a origem de recurso corrente selecionada ainda não foi salva, salva.
            if not OrigemRecursoProjetoEtapa.objects.filter(
                etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade, origem_recurso_projeto=origem_recurso
            ).exists():
                OrigemRecursoProjetoEtapa.objects.create(
                    etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade, origem_recurso_projeto=origem_recurso
                )

        # Exclui todas as etapas que não estão selecionadas
        for origem_recurso_projeto in OrigemRecursoProjetoEtapa.objects.filter(
            etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade
        ).exclude(origem_recurso_projeto__pk__in=selecionadas_ids):
            origem_recurso_projeto.delete()


class AssociarUnidadeGestoraEtapaProjetoPlanoAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Adicionar apenas selecionados'

    # Unidades gestoras  selecionados
    unidades_gestoras_campi = forms.MultipleModelChoiceField(
        queryset=UnidadeGestora.objects, label='', required=False, widget=RenderableSelectMultiple('widgets/unidades_gestoras_etapa_widget.html')
    )
    unidades_gestoras_sistemicas = forms.MultipleModelChoiceField(
        queryset=UnidadeGestora.objects,
        label='',
        required=False,
        widget=RenderableSelectMultiple('widgets/unidades_gestoras_sistemicas_etapa_widget.html'),
    )

    def __init__(self, *args, **kwargs):
        self.etapa_projeto_plano_atividade = kwargs.pop('etapa_projeto_plano_atividade')
        super().__init__(*args, **kwargs)

        # recupera todas as Unidades gestoras da etapa do projeto do plano de atividade
        m_initial = UnidadeGestoraEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade).values_list(
            'unidade_gestora__pk', flat=True
        )

        # Mostra as Unidades disponíveis a serem selecionadas
        qs = UnidadeGestora.objects.filter(pdi=self.etapa_projeto_plano_atividade.projeto_plano_atividade.plano_atividade.pdi)
        self.fields['unidades_gestoras_campi'].queryset = qs.filter(tipo=UnidadeGestora.TIPO_CAMPUS)

        self.fields['unidades_gestoras_sistemicas'].queryset = qs.filter(tipo=UnidadeGestora.TIPO_GESTOR_SISTEMICO)
        # Seleciona as Unidades gestoras que já foram salvas
        self.fields['unidades_gestoras_campi'].initial = m_initial.filter(unidade_gestora__tipo=UnidadeGestora.TIPO_CAMPUS)
        self.fields['unidades_gestoras_sistemicas'].initial = m_initial.filter(unidade_gestora__tipo=UnidadeGestora.TIPO_GESTOR_SISTEMICO)

    @transaction.atomic()
    def save(self):
        # lista de novas UG
        selecionadas_ids = []
        # itera sobre as UG
        unidades_gestoras_form = self.cleaned_data['unidades_gestoras_campi'] | self.cleaned_data['unidades_gestoras_sistemicas']
        for unidade_gestora in unidades_gestoras_form:
            selecionadas_ids.append(unidade_gestora.pk)
            # se a UG corrente selecionada ainda não foi salva, salva.
            if not UnidadeGestoraEtapa.objects.filter(
                etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade, unidade_gestora=unidade_gestora
            ).exists():
                UnidadeGestoraEtapa.objects.create(etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade, unidade_gestora=unidade_gestora)

        # Exclui todas as etapas que não estão selecionadas
        for unidade_gestora_etapa in UnidadeGestoraEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa_projeto_plano_atividade).exclude(
            unidade_gestora__pk__in=selecionadas_ids
        ):
            unidade_gestora_etapa.delete()


class OrigemRecursoProjetoForm(forms.ModelFormPlus):
    valor = forms.DecimalFieldPlus('Valor')

    class Meta:
        model = OrigemRecursoProjeto
        fields = ('valor',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        valor = self.cleaned_data.get('valor')
        if valor is None:
            raise ValidationError('Campo obrigatório.')
        valor_executado = OrigemRecursoProjeto.objects.filter(
            projeto_plano_atividade__plano_atividade=self.instance.projeto_plano_atividade.plano_atividade,
            origem_recurso=self.instance.origem_recurso,
        )
        valor_executado_atual = (valor_executado.aggregate(total=Sum('valor'))['total'] or 0) - (self.instance.valor or 0)

        saldo_disponivel = self.instance.origem_recurso.valor_total() - valor_executado_atual
        saldo = self.instance.origem_recurso.valor_total() - (valor_executado_atual + self.cleaned_data['valor'])

        if saldo < 0:
            raise forms.ValidationError(
                f'Este valor ultrapassou o valor disponível para esta Origem de Recurso. Saldo Disponível: {format_money(saldo_disponivel)}'
            )

        return self.cleaned_data


class GerenciarCompartilhamentoGEstorUAForm(forms.FormPlus):
    vinculos_poder_chefe = forms.MultipleModelChoiceFieldPlus(label='Servidores com poder de Gestor', queryset=Vinculo.objects, required=False)

    fieldsets = (('Servidores com poder de Gestor Planejamento Estratégico', {'fields': ('vinculos_poder_chefe',)}),)

    def __init__(self, *args, **kwargs):
        self.setor_escolhido = kwargs.pop('setor_escolhido', None)
        super().__init__(*args, **kwargs)
        self.fields['vinculos_poder_chefe'].label = f'Servidores com poder de gestor no(a) {self.setor_escolhido}'
        self.fields['vinculos_poder_chefe'].queryset = Vinculo.objects.filter(
            tipo_relacionamento__model='servidor',
            id_relacionamento__in=Servidor.objects.filter(setor__in=self.setor_escolhido.descendentes).values_list('id', flat=True),
        )


class ValoresOrigemRecursoEtapaForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.origemrecurso = kwargs.pop('origemrecurso', None)
        super().__init__(*args, **kwargs)
        nome_campos = ''
        for i in OrigemRecursoProjetoEtapa.objects.filter(origem_recurso_projeto=self.origemrecurso).order_by('etapa_projeto_plano_atividade'):
            label = f'{i.etapa_projeto_plano_atividade.etapa.codigo} - {i.etapa_projeto_plano_atividade.etapa}'
            inicial = i.valor or 0
            self.fields[f'{i.id}'] = forms.DecimalFieldPlus(label=label, required=True, initial=inicial)
            nome_campos = nome_campos + f'{i.id}, '

    def clean(self):
        valor_origem_projeto = self.origemrecurso.valor or 0
        total = Decimal(0)
        for valor in self.cleaned_data.values():
            total += valor

        saldo = valor_origem_projeto - total
        if saldo < 0:
            self.add_error(
                '', f'Valor distribuído maior que o valor disponível desta Origem de Recurso.  Valor ultrapassado:  R$  {format_money(saldo)}'
            )

        if saldo > 0:
            self.add_error('', f'Você ainda precisa distribuir nos componentes funcionais para esta Origem de Recurso R$ {format_money(saldo)}')


class ValoresEtapaUnidadesForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.origemrecurso = kwargs.pop('origemrecurso', None)
        self.etapa = kwargs.pop('etapa', None)
        super().__init__(*args, **kwargs)
        nome_campos = ''
        for i in UnidadeGestoraEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa):
            label = f'{i.unidade_gestora.setor_equivalente.sigla}'
            inicial = Decimal(0)
            if UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=self.origemrecurso, unidade_gestora=i).exists():
                inicial = UnidadeOrigemEtapa.objects.filter(origem_recurso_etapa=self.origemrecurso, unidade_gestora=i)[0].valor
            self.fields[f'{i.id}'] = forms.DecimalFieldPlus(label=label, required=True, initial=inicial)
            nome_campos = nome_campos + f'{i.id}, '

    def clean(self):
        valor_origem_etapa = (
            OrigemRecursoProjetoEtapa.objects.filter(
                origem_recurso_projeto=self.origemrecurso.origem_recurso_projeto.id, etapa_projeto_plano_atividade=self.etapa
            )[0].valor
            or 0
        )

        total = Decimal(0)
        for valor in self.cleaned_data.values():
            total += valor

        saldo = valor_origem_etapa - total
        if saldo < 0:
            self.add_error(
                '', f'Valor distribuído maior que o valor disponível desta Origem de Recurso.  Valor ultrapassado:  R$ {format_money(saldo)}'
            )

        if saldo > 0:
            self.add_error('', f'Você ainda precisa distribuir nas Unidades administrativas para esta Origem de Recurso R$ {format_money(saldo)}')


class ValoresEtapaAtividadesForm(forms.Form):
    fieldsets = ()

    def __init__(self, *args, **kwargs):
        self.origemrecurso = kwargs.pop('origemrecurso', None)
        self.etapa = kwargs.pop('etapa', None)
        super().__init__(*args, **kwargs)
        nome_campos = ''
        user = tl.get_user()
        for i in AtividadeEtapa.objects.filter(
            etapa_projeto_plano_atividade=self.etapa,
            origem_recurso_etapa=self.origemrecurso,
            unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=user),
        ):
            label = 'Valor a compatibilizar'
            inicial = Decimal(0)
            inicial_reserva_tecnica = Decimal(0)
            origem_especial = None
            if OrigemRecursoProjetoEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.etapa.projeto_plano_atividade.plano_atividade,
                tipo_especial=True,
            ).exists():
                origem_especial = OrigemRecursoProjetoEtapa.objects.filter(
                    etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.etapa.projeto_plano_atividade.plano_atividade,
                    tipo_especial=True,
                )[0]
            if AtividadeEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa, origem_recurso_etapa=self.origemrecurso, pk=i.pk).exists():
                inicial = AtividadeEtapa.objects.filter(etapa_projeto_plano_atividade=self.etapa, origem_recurso_etapa=self.origemrecurso, pk=i.pk)[
                    0
                ].valor_rateio or Decimal(0)
                inicial_reserva_tecnica = AtividadeEtapa.objects.filter(
                    etapa_projeto_plano_atividade=self.etapa, origem_recurso_etapa=self.origemrecurso, pk=i.pk
                )[0].valor_reserva_tecnica or Decimal(0)
            if i.valor is None:
                i.valor = Decimal(0)
            self.fields[f'valor_proposto_{i.id}'] = forms.DecimalFieldPlus(label='Valor proposto', required=True, initial=i.valor)
            self.fields[f'valor_proposto_{i.id}'].widget.attrs['readonly'] = 'readonly'

            self.fields[f'{i.id}'] = forms.DecimalFieldPlus(label=label, required=True, initial=inicial)

            self.fields[f'reserva_tecnica_{i.id}'] = forms.DecimalFieldPlus(
                label='Valor a complementar', required=True, initial=inicial_reserva_tecnica
            )
            if (
                not origem_especial
                or origem_especial.origem_recurso_projeto.origem_recurso.gnd != self.origemrecurso.origem_recurso_projeto.origem_recurso.gnd
                or origem_especial.origem_recurso_projeto.origem_recurso.acao_financeira.ptres
                != self.origemrecurso.origem_recurso_projeto.origem_recurso.acao_financeira.ptres
                or not UnidadeOrigemEtapa.objects.filter(
                    origem_recurso_etapa=origem_especial,
                    unidade_gestora__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=tl.get_user()),
                ).exists()
            ):
                self.fields[f'reserva_tecnica_{i.id}'].widget.attrs['readonly'] = 'readonly'
            else:
                if self.etapa.eh_especial() and self.origemrecurso.tipo_especial:
                    self.fields[f'reserva_tecnica_{i.id}'].widget.attrs['readonly'] = 'readonly'
            nome_campos = nome_campos + f'{i.descricao},'
            self.fieldsets = (*self.fieldsets, (i.nome, {'fields': ((f'valor_proposto_{i.id}', f'{i.id}', f'reserva_tecnica_{i.id}'),)}))

    def clean(self):
        valor_origem_unidade = (
            UnidadeOrigemEtapa.objects.filter(
                origem_recurso_etapa=self.origemrecurso,
                unidade_gestora__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=tl.get_user()),
            )[0].valor
            or 0
        )

        valor_especial_unidade = 0
        if OrigemRecursoProjetoEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.etapa.projeto_plano_atividade.plano_atividade,
            tipo_especial=True,
        ).exists():
            or_especial = OrigemRecursoProjetoEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.etapa.projeto_plano_atividade.plano_atividade,
                tipo_especial=True,
            )[0]
            if UnidadeOrigemEtapa.objects.filter(
                origem_recurso_etapa=or_especial, unidade_gestora__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=tl.get_user())
            ).exists():
                valor_especial_unidade = (
                    UnidadeOrigemEtapa.objects.filter(
                        origem_recurso_etapa=or_especial,
                        unidade_gestora__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=tl.get_user()),
                    )[0].valor
                    or 0
                )
        user = tl.get_user()
        total_valor = 0
        total_reserva_tecnica = 0
        valor_rateado_ativ = 0
        total_atividades_reserva = 0
        if OrigemRecursoProjetoEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.etapa.projeto_plano_atividade.plano_atividade,
            tipo_especial=True,
        ).exists():
            atividades = AtividadeEtapa.objects.filter(
                origem_recurso_etapa=or_especial, unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=user)
            )
            valor_rateado_ativ = atividades.aggregate(total=Sum('valor_rateio'))['total'] or 0
            atividades_reserva = AtividadeEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.etapa.projeto_plano_atividade.plano_atividade,
                valor_reserva_tecnica__isnull=False,
                unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=user),
            ).exclude(origem_recurso_etapa=self.origemrecurso)
            total_atividades_reserva = atividades_reserva.aggregate(total=Sum('valor_reserva_tecnica'))['total'] or 0
        for i in AtividadeEtapa.objects.filter(
            etapa_projeto_plano_atividade=self.etapa,
            origem_recurso_etapa=self.origemrecurso,
            unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=user),
        ):
            try:
                total_valor += self.cleaned_data[f'{i.id}']
                total_reserva_tecnica += self.cleaned_data[f'reserva_tecnica_{i.id}']
            except KeyError:
                pass

        saldo = valor_origem_unidade - total_valor

        if self.origemrecurso.tipo_especial:
            unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=user))[0]
            if unidade.recurso_total:
                valor_percentual_unidade = valor_origem_unidade
            else:
                valor_percentual_unidade = (
                    valor_origem_unidade * self.etapa.projeto_plano_atividade.plano_atividade.percentual_reserva_tecnica
                ) / 100
            saldo = valor_especial_unidade - (total_reserva_tecnica + total_atividades_reserva)
            if saldo > valor_percentual_unidade:
                saldo = valor_percentual_unidade - total_valor
            else:
                saldo = saldo - total_valor

        if saldo < 0:
            self.add_error('', f'O somatório dos valores a compatibilizar ultrapassa o valor disponível nesta OR em R$ {format_money(saldo)}')

        if not self.etapa.eh_especial() and saldo > 0:
            self.add_error('', f'Você ainda precisa distribuir nas atividades para esta Origem de Recurso R$ {format_money(saldo)}')
        if not self.etapa.eh_especial():
            valor_especial_unidade = valor_especial_unidade - valor_rateado_ativ
            saldo_especial = valor_especial_unidade - (total_reserva_tecnica + total_atividades_reserva)
            if saldo_especial < 0:
                self.add_error('', f'O somatório dos valores a complementar ultrapassa o valor disponível em R$ {format_money(saldo_especial)}')


class PreenchimentoVariavelForm(ModelFormPlus):
    class Meta:
        model = PeriodoPreenchimentoVariavel
        fields = ('pdi', 'ano', 'trimestre', 'data_inicio', 'data_termino')

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            data_inicio = cleaned_data.get('data_inicio')
            data_termino = cleaned_data.get('data_termino')
            if data_termino < data_inicio:
                self.add_error('data_termino', 'Data de término deve ser maior ou igual à Data de início.')
            periodos = PeriodoPreenchimentoVariavel.objects.filter(pdi=self.cleaned_data['pdi'])
            if self.instance.pk:
                periodos = periodos.exclude(pk=self.instance.pk)
            if periodos.exists():
                for periodo in periodos:
                    if periodo.data_inicio <= data_inicio <= periodo.data_termino or periodo.data_inicio <= data_termino <= periodo.data_termino:
                        raise forms.ValidationError('O Periodo selecionado engloba parte de outro período já cadastrado. Escolha outras datas.')
        return self.cleaned_data


def filtro_indicadores_formfactory(pdi, sigla_instituicao):
    ano_choices = [[ano, ano] for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1)]
    ano_choices.append(['Selecione um ano', 'Selecione um ano'])

    class IndicadoresFiltroForm(forms.FormPlus):
        METHOD = 'GET'
        ano = forms.ChoiceField(label='Ano', choices=ano_choices, required=False, initial='Selecione um ano')
        campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=False, empty_label=sigla_instituicao)
        indicador = forms.ModelChoiceField(
            label='Indicador', queryset=PDIIndicador.objects.filter(pdi=pdi).order_by('indicador__sigla'), required=False
        )

        def __init__(self, *args, **kwargs):
            pdi = kwargs.pop('pdi')
            super().__init__(*args, **kwargs)

            choices = []
            for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano):
                choices.append((ano, ano))

            self.base_fields['ano'].choices = choices

    return IndicadoresFiltroForm


class RelatorioDemonstrativoForm(forms.FormPlus):
    unidade_gestora = forms.ModelChoiceField(
        label='Unid. Administrativa',
        queryset=UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla'),
        widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
    )


class RelatorioProjetoForm(forms.FormPlus):
    unidade_gestora = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla'), required=False
    )
    origem_recurso_etapa = forms.ModelChoiceFieldPlus2(label='Origem de recurso', queryset=OrigemRecursoProjetoEtapa.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        projeto = kwargs.pop('projeto')
        super().__init__(*args, **kwargs)
        qs = OrigemRecursoProjetoEtapa.objects.filter(etapa_projeto_plano_atividade__projeto_plano_atividade=projeto).distinct(
            'origem_recurso_projeto'
        )
        self.fields['origem_recurso_etapa'].queryset = qs


class RelatorioPlanoatividadeForm(forms.FormPlus):
    METHOD = 'GET'
    unidade_gestora = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla'), required=False
    )
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all().order_by('projeto__codigo'), required=False)
    etapa = forms.ModelChoiceField(
        label='Componente funcional',
        queryset=EtapaProjetoPlanoAtividade.objects.all().order_by('projeto_plano_atividade__projeto__codigo'),
        required=False,
    )
    origem_recurso = forms.ModelChoiceField(
        label='Origem de recurso', queryset=OrigemRecurso.objects.all().order_by('acao_financeira__acao__codigo_acao'), required=False
    )

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        etapa_qs = EtapaProjetoPlanoAtividade.objects.filter(projeto_plano_atividade__plano_atividade=plano_atividade).order_by(
            'projeto_plano_atividade__projeto__codigo'
        )
        or_qs = OrigemRecurso.objects.filter(plano_atividade=plano_atividade).order_by('acao_financeira__acao__codigo_acao')
        self.fields['projeto'].queryset = qs
        self.fields['etapa'].queryset = etapa_qs
        self.fields['origem_recurso'].queryset = or_qs

        unidade_gestora = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user)).first()
        if unidade_gestora:
            self.fields['unidade_gestora'].initial = unidade_gestora.id

    def is_empty(self):
        return all(not value for value in self.cleaned_data.values())


def filtro_linhadotempo_formfactory(pdi, sigla_instituicao):
    class LinhaTempoFiltroForm(forms.FormPlus):
        METHOD = 'GET'
        campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=False, empty_label=sigla_instituicao)
        indicador = forms.ModelChoiceField(label='Indicador', queryset=PDIIndicador.objects.all().order_by('indicador__sigla'), required=False)

        def __init__(self, *args, **kwargs):
            pdi = kwargs.pop('pdi')
            super().__init__(*args, **kwargs)
            self.fields['indicador'].queryset = PDIIndicador.objects.filter(pdi=pdi).order_by('indicador__sigla')

    return LinhaTempoFiltroForm


class RelatorioRankingForm(forms.FormPlus):
    campus = forms.ModelChoiceField(
        label='Unid. Administrativa',
        required=False,
        queryset=UnidadeOrganizacional.objects.uo().all(),
    )
    tematica = forms.ModelChoiceField(
        label='Temática',
        required=False,
        queryset=TematicaVariavel.objects.all(),
    )
    apenas_variaveis_rede = forms.BooleanField(
        label='Apenas variáveis de Rede',
        required=False,
    )


def get_ext_combo_template_atividade(obj):
    out = [f'<h4>Atividade: {obj.nome}</h4>']
    out.append(f'<h5>Macroprocesso: {obj.etapa_projeto_plano_atividade.projeto_plano_atividade.projeto}</h5>')
    template = """<div>
               <div>
                   {}
               </div>
           </div>
           """.format(''.join(out))
    return template


class RelatorioPlanoConcluidoForm(forms.FormPlus):
    unidade_gestora = forms.ModelChoiceField(
        label='Unid. Administrativa', queryset=UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla'), required=False
    )
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all().order_by('projeto__codigo'), required=False)
    origem_recurso = forms.ModelChoiceField(
        label='Origem de recurso', queryset=OrigemRecurso.objects.all().order_by('acao_financeira__acao__codigo_acao'), required=False
    )

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        or_qs = OrigemRecurso.objects.filter(plano_atividade=plano_atividade).order_by('acao_financeira__acao__codigo_acao')
        self.fields['projeto'].queryset = qs
        self.fields['origem_recurso'].queryset = or_qs

        if UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user)).exists():
            qs_unidades = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))
            self.fields['unidade_gestora'].initial = qs_unidades[0].id


class RequisicaoRealocacaoConcedenteForm(forms.FormPlus):
    unidade_concedente = forms.ModelChoiceFieldPlus(
        label='Unidade Concedente',
        required=True,
        queryset=UnidadeGestora.objects,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS, readonly=True),
    )
    unidade_recebedora = forms.ModelChoiceField(
        label='Unidade Recebedora', required=True, queryset=UnidadeGestora.objects, widget=AutocompleteWidget()
    )
    atividade_concedente = forms.ModelPopupChoiceField(
        label='Atividade Concedente',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_realocacao_concedente.html',
    )
    restringir_ao_mesmo_macroprocesso = forms.BooleanField(
        label='Restringir a atividade recebedora ao mesmo macroprocesso',
        help_text='Se marcado, a Unidade Recebedora somente poderá indicar, no deferimento desta requisição de realocação, uma atividade vinculada ao mesmo macroprocesso da atividade concedente.',
        required=False,
    )
    valor_requisicao = forms.DecimalFieldPlus(label='Valor', required=True)
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)

        setor = get_setor_unidade_gestora(user=self.request.user)

        unidade = UnidadeGestora.objects.filter(setor_equivalente=setor).first()

        if unidade is None:
            self.fields['unidade_concedente'].initial = None
            self.fields['atividade_concedente'].queryset = AtividadeEtapa.objects.none()
            self.fields['unidade_recebedora'].queryset = UnidadeGestora.objects.none()
            return

        self.fields['unidade_concedente'].initial = unidade.id

        self.fields['atividade_concedente'].queryset = AtividadeEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=plano_atividade,
            unidade_gestora=unidade.id,
        ).order_by('etapa_projeto_plano_atividade__projeto_plano_atividade__projeto__codigo')

        self.fields['unidade_recebedora'].queryset = UnidadeGestora.objects.exclude(id=unidade.id)

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        atividade_concedente = cleaned_data.get('atividade_concedente')
        if cleaned_data.get('valor_requisicao') > atividade_concedente.get_limite_a_realocar():
            self.add_error(
                'valor_requisicao',
                f'Valor maior que o limite disponível para realocar da atividade: R$ {format_money(atividade_concedente.get_limite_a_realocar())}',
            )

        return cleaned_data

    @transaction.atomic()
    def save(self):
        unidade_concedente = self.cleaned_data['unidade_concedente']
        atividade_concedente = self.cleaned_data['atividade_concedente']
        projeto_concedente = atividade_concedente.etapa_projeto_plano_atividade.projeto_plano_atividade
        origem_concedente = atividade_concedente.origem_recurso_etapa.origem_recurso_projeto
        unidade_recebedora = self.cleaned_data['unidade_recebedora']
        valor_requisicao = self.cleaned_data['valor_requisicao']
        justificativa = self.cleaned_data['justificativa']
        restringir_ao_mesmo_macroprocesso = self.cleaned_data['restringir_ao_mesmo_macroprocesso']
        tipo_requisicao = RequisicaoRealocacao.TIPO_REALOCACAO_UA_CONCEDENTE
        plano_atividade = atividade_concedente.etapa_projeto_plano_atividade.projeto_plano_atividade.plano_atividade
        status = RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA
        ano = plano_atividade.ano_base.ano
        maior_codigo = RequisicaoRealocacao.objects.filter(numero__startswith=str(ano)).count()
        sequencial = str(int(maior_codigo + 1)).zfill(6)
        numero = f'{ano}RR{sequencial}'
        requisicao = RequisicaoRealocacao.objects.create(
            plano_atividade=plano_atividade,
            unidade_concedente=unidade_concedente,
            atividade_concedente=atividade_concedente,
            unidade_recebedora=unidade_recebedora,
            status=status,
            numero=numero,
            valor_requisicao=valor_requisicao,
            projeto_concedente=projeto_concedente,
            origem_concedente=origem_concedente,
            justificativa=justificativa,
            tipo_requisicao=tipo_requisicao,
            restringir_ao_mesmo_macroprocesso=restringir_ao_mesmo_macroprocesso,
        )
        RequisicaoRealocacaoHistorico.objects.create(
            requisicao=requisicao, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        return requisicao


class RequisicaoRealocacaoRecebedoraForm(forms.FormPlus):
    unidade_recebedora = forms.ModelChoiceFieldPlus(
        label='Unidade Recebedora',
        required=True,
        queryset=UnidadeGestora.objects,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS, readonly=True),
    )
    unidade_concedente = forms.ModelChoiceField(
        label='Unidade Concedente', required=True, queryset=UnidadeGestora.objects, widget=AutocompleteWidget()
    )
    atividade_recebedora = forms.ModelPopupChoiceField(
        label='Atividade Recebedora',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_realocacao_recebedora.html',
    )

    valor_requisicao = forms.DecimalFieldPlus(label='Valor', required=True)
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)

        unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))[0]
        self.fields['unidade_recebedora'].initial = unidade.id

        self.fields['atividade_recebedora'].queryset = AtividadeEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=plano_atividade,
            unidade_gestora=unidade.id,
        ).order_by('etapa_projeto_plano_atividade__projeto_plano_atividade__projeto__codigo')

        self.fields['unidade_concedente'].queryset = UnidadeGestora.objects.exclude(id=unidade.id)

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

    @transaction.atomic()
    def save(self):
        unidade_recebedora = self.cleaned_data['unidade_recebedora']
        atividade_recebedora = self.cleaned_data['atividade_recebedora']
        projeto_recebedor = atividade_recebedora.etapa_projeto_plano_atividade.projeto_plano_atividade
        origem_recebedora = atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto
        unidade_concedente = self.cleaned_data['unidade_concedente']
        valor_requisicao = self.cleaned_data['valor_requisicao']
        justificativa = self.cleaned_data['justificativa']
        tipo_requisicao = RequisicaoRealocacao.TIPO_REALOCACAO_UA_RECEBEDORA
        status = RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE
        plano_atividade = atividade_recebedora.etapa_projeto_plano_atividade.projeto_plano_atividade.plano_atividade
        ano = plano_atividade.ano_base.ano
        maior_codigo = RequisicaoRealocacao.objects.filter(numero__startswith=str(ano)).count()
        sequencial = str(int(maior_codigo + 1)).zfill(6)
        numero = f'{ano}RR{sequencial}'
        requisicao = RequisicaoRealocacao.objects.create(
            plano_atividade=plano_atividade,
            unidade_recebedora=unidade_recebedora,
            atividade_recebedora=atividade_recebedora,
            unidade_concedente=unidade_concedente,
            status=status,
            numero=numero,
            valor_requisicao=valor_requisicao,
            projeto_recebedor=projeto_recebedor,
            origem_recebedora=origem_recebedora,
            justificativa=justificativa,
            tipo_requisicao=tipo_requisicao,
        )
        RequisicaoRealocacaoHistorico.objects.create(
            requisicao=requisicao, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        return requisicao


class RequisicaoRealocacaoAmbasForm(forms.FormPlus):
    unidade_concedente = forms.ModelChoiceFieldPlus(
        label='Unidade Concedente',
        required=True,
        queryset=UnidadeGestora.objects,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS, readonly=True),
    )
    unidade_recebedora = forms.ModelChoiceField(
        label='Unidade Recebedora',
        required=True,
        queryset=UnidadeGestora.objects,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS, readonly=True),
    )
    atividade_concedente = forms.ModelPopupChoiceField(
        label='Atividade Concedente',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_realocacao_concedente_recebedora.html',
    )

    atividade_recebedora = forms.ModelPopupChoiceField(
        label='Atividade Recebedora',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_realocacao_recebedora.html',
    )

    valor_requisicao = forms.DecimalFieldPlus(label='Valor', required=True)
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)

        unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))[0]
        self.fields['unidade_concedente'].initial = unidade.id
        self.fields['unidade_recebedora'].initial = unidade.id

        self.fields['atividade_concedente'].queryset = AtividadeEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=plano_atividade,
            unidade_gestora=unidade.id,
        ).order_by('etapa_projeto_plano_atividade__projeto_plano_atividade__projeto__codigo')
        self.fields['atividade_recebedora'].queryset = AtividadeEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=plano_atividade,
            unidade_gestora=unidade.id,
        ).order_by('etapa_projeto_plano_atividade__projeto_plano_atividade__projeto__codigo')

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        atividade_concedente = cleaned_data.get('atividade_concedente')
        atividade_recebedora = cleaned_data.get('atividade_recebedora')
        limite_a_realocar = atividade_concedente.get_limite_a_realocar()

        if atividade_concedente and atividade_recebedora and atividade_concedente == atividade_recebedora:
            self.add_error('atividade_recebedora', 'A atividade recebedora deve ser diferente da atividade concedente.')
            return cleaned_data

        if (
            atividade_concedente.etapa_projeto_plano_atividade.projeto_plano_atividade
            == atividade_recebedora.etapa_projeto_plano_atividade.projeto_plano_atividade
            and atividade_concedente.plano_interno == atividade_recebedora.plano_interno
        ):
            limite_a_realocar = atividade_concedente.get_limite_a_realocar_mesmo_pi_ua()
        if cleaned_data.get('valor_requisicao') > limite_a_realocar:
            self.add_error(
                'valor_requisicao',
                f'A atividade concedente tem o limite de R$: {format_money(atividade_concedente.get_limite_a_realocar_mesmo_pi_ua())} para realocação para atividade recebedora de mesmo Macroprocesso e Plano interno. E tem o limite de R$ {format_money(atividade_concedente.get_limite_a_realocar())} para realocação para atividade recebedora de Macroprocesso diferente.',
            )
        if (
            atividade_concedente.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.gnd
            != atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.gnd
        ):
            self.add_error('atividade_recebedora', 'O grupo de despesa da origem de recurso deve ser o mesmo da atividade concedente.')
        if (
            atividade_concedente.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.acao_financeira.ptres
            != atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.acao_financeira.ptres
        ):
            self.add_error('atividade_recebedora', 'PTRES diferentes.')
        return cleaned_data

    @transaction.atomic()
    def save(self):
        unidade_concedente = self.cleaned_data['unidade_concedente']
        atividade_concedente = self.cleaned_data['atividade_concedente']
        projeto_concedente = atividade_concedente.etapa_projeto_plano_atividade.projeto_plano_atividade
        origem_concedente = atividade_concedente.origem_recurso_etapa.origem_recurso_projeto
        atividade_recebedora = self.cleaned_data['atividade_recebedora']
        projeto_recebedor = atividade_recebedora.etapa_projeto_plano_atividade.projeto_plano_atividade
        origem_recebedora = atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto
        unidade_recebedora = self.cleaned_data['unidade_recebedora']
        valor_requisicao = self.cleaned_data['valor_requisicao']
        justificativa = self.cleaned_data['justificativa']
        tipo_requisicao = RequisicaoRealocacao.TIPO_REALOCACAO_AMBAS
        plano_atividade = atividade_recebedora.etapa_projeto_plano_atividade.projeto_plano_atividade.plano_atividade
        status = RequisicaoRealocacao.STATUS_DEFERIDA
        ano = plano_atividade.ano_base.ano
        maior_codigo = RequisicaoRealocacao.objects.filter(numero__startswith=str(ano)).count()
        sequencial = str(int(maior_codigo + 1)).zfill(6)
        numero = f'{ano}RR{sequencial}'
        requisicao = RequisicaoRealocacao.objects.create(
            plano_atividade=plano_atividade,
            unidade_concedente=unidade_concedente,
            atividade_concedente=atividade_concedente,
            unidade_recebedora=unidade_recebedora,
            atividade_recebedora=atividade_recebedora,
            status=status,
            numero=numero,
            valor_requisicao=valor_requisicao,
            projeto_concedente=projeto_concedente,
            origem_concedente=origem_concedente,
            projeto_recebedor=projeto_recebedor,
            origem_recebedora=origem_recebedora,
            justificativa=justificativa,
            tipo_requisicao=tipo_requisicao,
        )
        requisicao.deferir_requisicaorealocacao(self.request.user)
        return requisicao


class IndeferirRequisicaoRealocacaoForm(forms.ModelFormPlus):
    comentario_indeferimento = forms.CharField(label='Motivo do Indeferimento', required=True, widget=forms.Textarea)

    class Meta:
        model = RequisicaoRealocacao
        fields = ('comentario_indeferimento',)

    def save(self):
        self.instance.indeferir_requisicaorealocacao(self.request.user)


class CancelarRequisicaoRealocacaoForm(forms.ModelFormPlus):
    motivo_cancelamento = forms.CharField(label='Motivo do cancelamento', required=True, widget=forms.Textarea)

    class Meta:
        model = RequisicaoRealocacao
        fields = ('motivo_cancelamento',)

    def save(self):
        self.instance.cancelar_requisicaorealocacao(self.request.user)


class DeferirRequisicaoRealocacaoForm(forms.ModelFormPlus):
    valor_aprovado_unidade = forms.DecimalFieldPlus(label='Valor Concedido')
    atividade_concedente = forms.ModelPopupChoiceField(
        label='Atividade Concedente',
        required=False,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_realocacao_deferimento.html',
    )
    atividade_recebedora = forms.ModelPopupChoiceField(
        label='Atividade Recebedora',
        required=False,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_realocacao_recebedora.html',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))[0]
        if self.instance.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_UA_CONCEDENTE:
            queryset = AtividadeEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.instance.plano_atividade,
                unidade_gestora=unidade.id,
                origem_recurso_etapa__origem_recurso_projeto__origem_recurso__gnd__id=self.instance.atividade_concedente.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.gnd.id,
            )
            if self.instance.restringir_ao_mesmo_macroprocesso:
                projeto_plano_atividade = self.instance.atividade_concedente.etapa_projeto_plano_atividade.projeto_plano_atividade
                queryset = queryset.filter(etapa_projeto_plano_atividade__projeto_plano_atividade=projeto_plano_atividade)

            self.fields['atividade_recebedora'].queryset = queryset.order_by(
                'etapa_projeto_plano_atividade__projeto_plano_atividade__projeto__codigo'
            )
            self.fields['atividade_recebedora'].required = True
            self.fields['atividade_concedente'].widget = forms.HiddenInput()
        elif self.instance.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_UA_RECEBEDORA:
            self.fields['atividade_concedente'].queryset = AtividadeEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=self.instance.plano_atividade,
                unidade_gestora=unidade.id,
                origem_recurso_etapa__origem_recurso_projeto__origem_recurso__gnd__id=self.instance.atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.gnd.id,
            ).order_by('etapa_projeto_plano_atividade__projeto_plano_atividade__projeto__codigo')
            self.fields['atividade_concedente'].required = True
            self.fields['atividade_recebedora'].widget = forms.HiddenInput()

    class Meta:
        model = RequisicaoRealocacao
        fields = ()

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        requisicao = self.instance
        if cleaned_data.get('valor_aprovado_unidade') <= 0:
            self.add_error('valor_aprovado_unidade', 'O valor deve ser maior que 0,00.')
            return cleaned_data
        if cleaned_data.get('valor_aprovado_unidade') > requisicao.valor_requisicao:
            raise ValidationError(f'Valor informado maior que o valor da requisição: R$ {requisicao.valor_requisicao}')
        if self.instance.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_UA_CONCEDENTE:
            atividade_concedente = requisicao.atividade_concedente
            atividade_recebedora = cleaned_data.get('atividade_recebedora')
            if cleaned_data.get('valor_aprovado_unidade') > atividade_concedente.limitar_deferimento_realocacao(requisicao=requisicao):
                self.add_error(
                    'valor_aprovado_unidade',
                    f'Valor maior que o limite disponível para realocar da atividade: R$ {format_money(atividade_concedente.limitar_deferimento_realocacao(requisicao=requisicao))}',
                )
        elif self.instance.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_UA_RECEBEDORA:
            atividade_concedente = cleaned_data.get('atividade_concedente')
            atividade_recebedora = requisicao.atividade_recebedora
            if cleaned_data.get('valor_aprovado_unidade') > atividade_concedente.limitar_deferimento_realocacao():
                self.add_error(
                    'valor_aprovado_unidade',
                    f'Valor maior que o limite disponível para realocar da atividade: R$ {format_money(atividade_concedente.limitar_deferimento_realocacao(requisicao=requisicao))}',
                )
        if (
            atividade_concedente.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.acao_financeira.ptres
            != atividade_recebedora.origem_recurso_etapa.origem_recurso_projeto.origem_recurso.acao_financeira.ptres
        ):
            raise ValidationError('Atividade escolhida com PTRES diferentes.')
        if cleaned_data.get('valor_aprovado_unidade') == 0.00 and atividade_concedente.get_valor_disponivel_execucao() == 0.00:
            self.add_error('valor_aprovado_unidade', 'Não é possível aprovar o valor de 0,00 quando o valor disponível é 0,00.')
        return cleaned_data

    def save(self):
        if self.instance.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_UA_CONCEDENTE:
            self.instance.deferir_requisicaorealocacao(
                self.request.user,
                valor_aprovado_unidade=self.cleaned_data['valor_aprovado_unidade'],
                atividade_concedente=self.instance.atividade_concedente,
                atividade_recebedora=self.cleaned_data['atividade_recebedora'],
            )
        if self.instance.tipo_requisicao == RequisicaoRealocacao.TIPO_REALOCACAO_UA_RECEBEDORA:
            self.instance.deferir_requisicaorealocacao(
                self.request.user,
                valor_aprovado_unidade=self.cleaned_data['valor_aprovado_unidade'],
                atividade_recebedora=self.instance.atividade_recebedora,
                atividade_concedente=self.cleaned_data['atividade_concedente'],
            )


class RelatorioDistribuicaoUAForm(forms.FormPlus):
    unidade_gestora = forms.ModelChoiceField(
        label='Unid. Administrativa',
        queryset=UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla'),
        required=False,
        widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
    )


class PlanoInternoForm(forms.ModelFormPlus):
    acao = forms.ModelChoiceFieldPlus(
        label='Ação Orçamentária',
        help_text='',
        queryset=Acao.objects,
        widget=AutocompleteWidget(label_value='codigo_e_ptres', search_fields=Acao.SEARCH_FIELDS),
    )
    ptres = forms.ModelChoiceFieldPlus(
        label='PTRES', help_text='', queryset=ProgramaTrabalhoResumido.objects, widget=AutocompleteWidget(label_value='codigo'), required=True
    )

    class Meta:
        model = PlanoInterno
        fields = ('descricao', 'projeto_estrategico', 'acao', 'ptres', 'categoria_apropriacao', 'gnd')

    def __init__(self, *args, **kwargs):
        pdi = kwargs.pop('pdi')
        super().__init__(*args, **kwargs)
        self.instance.pdi = pdi
        # self.fields['projeto_estrategico'].queryset = ProjetoEstrategico.objects.filter(pdi=pdi, macroprocesso=True).order_by('codigo')
        self.fields['projeto_estrategico'].queryset = ProjetoEstrategico.objects.filter(pdi=pdi).order_by('codigo')
        if self.instance.pk:
            self.fields.pop('projeto_estrategico')
            self.fields.pop('acao')
            self.fields.pop('ptres')
            self.fields.pop('categoria_apropriacao')
            self.fields.pop('gnd')

    def clean(self):
        super().clean()

        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        descricao = self.cleaned_data['descricao']
        if self.instance.pk:
            obj = super().save(*args, **kwargs)
            self.descricao = descricao
            self.instance.save()
            return obj
        acao = self.cleaned_data['acao']
        ptres = self.cleaned_data['ptres']
        categoria_apropriacao = self.cleaned_data['categoria_apropriacao']
        projeto = self.cleaned_data['projeto_estrategico']
        gnd = self.cleaned_data['gnd']
        codigo_origemrecurso = f'{projeto.codigo}.{acao.codigo_acao}.{ptres}.{gnd.codigo}'
        codigo = f'L{acao.codigo_acao}P{categoria_apropriacao.codigo}{projeto.codigo}N'
        PlanoInterno.objects.create(
            pdi=self.instance.pdi,
            descricao=descricao,
            codigo=codigo,
            acao=acao,
            categoria_apropriacao=categoria_apropriacao,
            projeto_estrategico=projeto,
            gnd=gnd,
            ptres=ptres,
            codigo_origemrecurso=codigo_origemrecurso,
        )


def indicador_rede_formfactory(pdi, sigla_instituicao):
    ano_choices = [[ano, ano] for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano + 1)]

    class FiltroIndicadorRedeForm(forms.FormPlus):
        ano = forms.ChoiceField(label='Ano', choices=ano_choices, required=False)
        campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=False, empty_label=sigla_instituicao)
        indicador = forms.ModelChoiceField(label='Indicador', queryset=Indicador.objects.filter(nivel_rede=True), required=False)

        def __init__(self, *args, **kwargs):
            pdi = kwargs.pop('pdi')
            ano_base = kwargs.pop('ano_base')
            uo = kwargs.pop('uo')

            self.base_fields['ano'].initial = ano_base
            if uo:
                self.base_fields['campus'].initial = uo.id
            self.base_fields['indicador'].queryset = Indicador.objects.filter(nivel_rede=True)
            super().__init__(*args, **kwargs)

            choices = []
            for ano in range(pdi.ano_inicial_pdi.ano, pdi.ano_final_pdi.ano):
                choices.append((ano, ano))

            self.base_fields['ano'].choices = choices
            self.base_fields['ano'].initial = ano_base

    return FiltroIndicadorRedeForm


class RequisicaoMovimentacaoCreditoForm(FormWizardPlus):
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all(), required=True)
    origem_recurso = forms.ModelChoiceField(label='Origem de recurso', queryset=OrigemRecursoProjeto.objects, required=True)

    plano_interno = forms.ModelChoiceField(label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True)

    unidades = forms.DictInputField(label='Valor a movimentar (R$)', required=False, widget=forms.BrDinheiroWidget)
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)
    steps = (
        [('Filtro', {'fields': ('projeto', 'origem_recurso', 'plano_interno', 'justificativa')})],
        [('Unidades Recebedoras', {'fields': ('unidades',)})],
    )

    class Media:
        js = ['/static/plan_estrategico/js/RequisicaoMovimentacao.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['projeto'].queryset = (
            qs.filter(Q(projeto__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=self.request.user)))
            .order_by('projeto__codigo')
            .distinct()
        )

    def next_step(self):
        projeto = self.get_entered_data('projeto')
        origem_recurso = self.get_entered_data('origem_recurso')
        plano_interno = self.get_entered_data('plano_interno')
        if 'unidades' in self.fields:
            if projeto and origem_recurso:
                dados = {}
                initial = {}
                for uo in UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla'):
                    valor_planejado = 0
                    if plano_interno:
                        valor_planejado = plano_interno.get_disponivel_plano_interno(unidade_gestora=uo)
                    valor_movimentado = MovimentacaoCreditoUnidade.get_total_movimentado_unidade(
                        unidade_gestora=uo, origem_recurso=origem_recurso, projeto=projeto, plano_interno=plano_interno
                    )
                    valor_em_movimentacao = MovimentacaoCreditoUnidade.get_total_em_movimentacao_unidade(
                        unidade_gestora=uo, origem_recurso=origem_recurso, projeto=projeto, plano_interno=plano_interno
                    )
                    valor_a_receber = valor_planejado - (valor_movimentado + valor_em_movimentacao)
                    dados[uo.setor_equivalente.sigla] = {
                        'Unidade': uo.setor_equivalente.sigla,
                        'Valor planejado (R$)': format_money(valor_planejado),
                        'Valor movimentado do plano interno': format_money(valor_movimentado),
                        'Valor em movimentação (R$)': format_money(valor_em_movimentacao),
                        'Valor a Receber (R$)': format_money(valor_a_receber),
                    }
                    initial[uo.setor_equivalente.sigla] = 0
                self.fields['unidades'].widget.items = dados
                self.fields['unidades'].widget.initial = initial

    def clean_unidades(self):
        plano_interno = self.get_entered_data('plano_interno')
        unidades = self.cleaned_data.get('unidades', {})
        for sigla, valor in unidades.items():
            uo = UnidadeGestora.objects.filter(setor_equivalente__sigla=sigla)[0]
            # valor_planejado = 0
            valor_a_receber = 0
            if plano_interno:
                # valor_planejado = plano_interno.get_disponivel_plano_interno(unidade_gestora=uo)
                valor_a_receber = plano_interno.saldo_plano_interno(unidade_gestora=uo)
            # valor_movimentado = MovimentacaoCreditoUnidade.get_total_em_movimentacao_unidade(unidade_gestora=uo,
            #                                                                                 origem_recurso=self.cleaned_data['origem_recurso'],
            #                                                                                 projeto=self.cleaned_data['projeto'])
            if valor and valor > valor_a_receber:
                valor = format_money(valor)
                valor_a_receber = format_money(valor_a_receber)
                mensagem = f'Valor (R$ {valor}) maior que o disponível para movimentar (R$ {valor_a_receber}).'
                self.fields['unidades'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)

        valores_planejados = [valor for valor in unidades.values() if valor != 0]
        if not valores_planejados:
            mensagem = 'Informe o valor a ser movimentado.'
            self.fields['unidades'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        return unidades

    @transaction.atomic
    def processar(self):
        projeto_estrategico = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        justificativa = self.cleaned_data['justificativa']
        tipo_requisicao = MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO
        status = MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS
        plano_atividade = projeto_estrategico.plano_atividade
        ano = plano_atividade.ano_base.ano
        maior_codigo = MovimentacaoCredito.objects.filter(numero__startswith=str(ano)).count()
        sequencial = str(int(maior_codigo + 1)).zfill(6)
        numero = f'{ano}RM{sequencial}'
        movimentacao_credito = MovimentacaoCredito.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            numero=numero,
            projeto_estrategico=projeto_estrategico,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            tipo_requisicao=tipo_requisicao,
            justificativa=justificativa,
        )
        for sigla, valor in self.request.POST.items():
            if sigla.endswith('_item'):
                sigla = sigla.replace('_item', '')
                if valor != '':
                    try:
                        valor_numerico = valor.replace('.', '').replace(',', '.')
                        valor_numerico = Decimal(valor_numerico)

                        if valor_numerico > 0:
                            uo = UnidadeGestora.objects.filter(setor_equivalente__sigla=sigla).first()
                            MovimentacaoCreditoUnidade.objects.create(movimentacao=movimentacao_credito, unidade=uo, valor=valor_numerico)
                    except ValueError, TypeError, decimal.ConversionSyntax:
                        pass
        MovimentacaoCreditoHistorico.objects.create(
            movimentacao=movimentacao_credito, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )

        grupos = Group.objects.filter(name__in=['Gestor Orçamentário Sistêmico:'])
        for grupo in grupos:
            for usuario in UsuarioGrupo.objects.filter(group=grupo):
                titulo = f'[SUAP] Planejamento Estratégico: Requisição de movimentação {numero} aguardando análise'
                texto = (
                    '<h1>Planejamento Estratégico</h1>'
                    '<h2>Análise da requisição de movimentação de crédito</h2>'
                    '<p>A Requisição de movimentação de crédito {0} <strong>está aguardando análise</strong></p>'
                    'Para mais informações, acesse: <a href = "{1}{2}">{1}{2}</a> </p>'.format(
                        numero, settings.SITE_URL, movimentacao_credito.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.user.get_vinculo()],
                    categoria='Planejamento Estratégico: Aguardando aprovação da requisição de movimentação de crédito',
                )
        return movimentacao_credito


class RequisicaoEstornoCreditoForm(FormWizardPlus):
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all(), required=True)

    origem_recurso = forms.ModelChoiceField(label='Origem de recurso', queryset=OrigemRecursoProjeto.objects, required=True)

    plano_interno = forms.ModelChoiceField(label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True)
    unidades = forms.DictInputField(label='Valor a estornar (R$)', required=False, widget=forms.BrDinheiroWidget)
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)
    steps = (
        [('Filtro', {'fields': ('projeto', 'origem_recurso', 'plano_interno', 'justificativa')})],
        [('Unidades Gestoras', {'fields': ('unidades',)})],
    )

    class Media:
        js = ['/static/plan_estrategico/js/RequisicaoMovimentacao.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['projeto'].queryset = qs.order_by('projeto__codigo').distinct()
        if in_group(self.request.user, 'Gestor de Projeto'):
            self.fields['projeto'].queryset = (
                qs.filter(Q(projeto__unidade_gestora__setor_equivalente=get_setor_unidade_gestora(user=self.request.user)))
                .order_by('projeto__codigo')
                .distinct()
            )
        if in_group(self.request.user, 'Gestor Orçamentário Sistêmico'):
            self.fields['projeto'].queryset = (
                ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo').distinct()
            )

    def next_step(self):
        projeto = self.get_entered_data('projeto')
        origem_recurso = self.get_entered_data('origem_recurso')
        plano_interno = self.get_entered_data('plano_interno')
        if 'unidades' in self.fields:
            if projeto and origem_recurso:
                dados = {}
                initial = {}
                unidades_gestoras = UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla')
                if in_group(self.request.user, ['Gestor Orçamentário de UA']):
                    unidades_gestoras = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))
                if in_group(self.request.user, 'Gestor Orçamentário Sistêmico'):
                    unidades_gestoras = UnidadeGestora.objects.all().order_by('tipo', 'setor_equivalente__sigla')
                for uo in unidades_gestoras:
                    valor_planejado = plano_interno.get_disponivel_plano_interno(unidade_gestora=uo)
                    valor_movimentado = plano_interno.valor_disponivel_movimentado(unidade_gestora=uo)
                    credito_disponivel = valor_movimentado
                    dados[uo.setor_equivalente.sigla] = {
                        'Unidade': uo.setor_equivalente.sigla,
                        'Valor planejado (R$)': format_money(valor_planejado),
                        'Valor movimentado disponível (R$)': format_money(valor_movimentado),
                        'Valor comprometido com empenhos (R$)': format_money(0),
                        'Crédito disponível': format_money(credito_disponivel),
                    }
                    initial[uo.setor_equivalente.sigla] = 0
                self.fields['unidades'].widget.items = dados
                self.fields['unidades'].widget.initial = initial

    def clean_unidades(self):
        unidades = self.cleaned_data.get('unidades', {})
        plano_interno = self.cleaned_data.get('plano_interno', {})
        for sigla, valor in unidades.items():
            uo = UnidadeGestora.objects.filter(setor_equivalente__sigla=sigla)[0]
            valor_movimentado = plano_interno.valor_disponivel_movimentado(unidade_gestora=uo)
            credito_disponivel = valor_movimentado
            if valor and valor > credito_disponivel:
                valor = format_money(valor)
                credito_disponivel = format_money(credito_disponivel)
                mensagem = f'Valor (R$ {valor}) maior que o crédito disponível (R$ {credito_disponivel}).'
                self.fields['unidades'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)
        valores_planejados = [valor for valor in unidades.values() if valor != 0]
        if not valores_planejados:
            mensagem = 'Informe o valor a ser estornado.'
            self.fields['unidades'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        return unidades

    @transaction.atomic
    def processar(self):
        projeto_estrategico = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        justificativa = self.cleaned_data['justificativa']
        tipo_requisicao = MovimentacaoCredito.TIPO_ESTORNO_CREDITO
        status = MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS
        plano_atividade = projeto_estrategico.plano_atividade
        ano = plano_atividade.ano_base.ano
        maior_codigo = MovimentacaoCredito.objects.filter(numero__startswith=str(ano)).count()
        sequencial = str(int(maior_codigo + 1)).zfill(6)
        numero = f'{ano}RM{sequencial}'
        movimentacao_credito = MovimentacaoCredito.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            numero=numero,
            projeto_estrategico=projeto_estrategico,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            tipo_requisicao=tipo_requisicao,
            justificativa=justificativa,
        )
        for sigla, valor in self.request.POST.items():
            if sigla.endswith('_item'):
                sigla = sigla.replace('_item', '')
                if valor != '':
                    try:
                        valor_numerico = valor.replace('.', '').replace(',', '.')
                        valor_numerico = Decimal(valor_numerico)

                        if valor_numerico > 0:
                            uo = UnidadeGestora.objects.filter(setor_equivalente__sigla=sigla).first()
                            MovimentacaoCreditoUnidade.objects.create(movimentacao=movimentacao_credito, unidade=uo, valor=valor_numerico)
                    except ValueError, TypeError, decimal.ConversionSyntax:
                        pass
        MovimentacaoCreditoHistorico.objects.create(
            movimentacao=movimentacao_credito, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )

        grupos = Group.objects.filter(name__in=['Gestor Orçamentário Sistêmico:'])
        for grupo in grupos:
            for usuario in UsuarioGrupo.objects.filter(group=grupo):
                titulo = f'[SUAP] Planejamento Estratégico: Requisição de estorno {numero} aguardando análise'
                texto = (
                    '<h1>Planejamento Estratégico</h1>'
                    '<h2>Análise da requisição de estorno de crédito</h2>'
                    '<p>A Requisição de estorno de crédito {0} <strong>está aguardando análise</strong></p>'
                    'Para mais informações, acesse: <a href = "{1}{2}">{1}{2}</a> </p>'.format(
                        numero, settings.SITE_URL, movimentacao_credito.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.user.get_vinculo()],
                    categoria='Planejamento Estratégico: Aguardando aprovação da requisição de estorno de crédito',
                )
        return movimentacao_credito


class RequisicaoAjusteInternoForm(FormWizardPlus):
    projeto = forms.ModelChoiceField(
        label='Macroprocesso concedente',
        queryset=ProjetoPlanoAtividade.objects.all(),
        help_text='Selecione o macroprocesso que o valor será debitado',
    )

    origem_recurso = forms.ModelChoiceField(
        label='Origem de recurso concedente',
        queryset=OrigemRecursoProjeto.objects,
        required=True,
        help_text='Selecione a origem que o valor será debitado',
    )

    plano_interno = forms.ModelChoiceField(label='Plano interno concedente', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True)
    unidades = forms.DictInputField(label='Valor a ajustar (R$)', required=False, widget=forms.BrDinheiroWidget)

    projeto_recebedor = forms.ModelChoiceField(
        label='Macroprocesso recebedor',
        queryset=ProjetoPlanoAtividade.objects.all(),
        help_text='Selecione o macroprocesso que o valor será creditado',
    )

    origem_recurso_recebedor = forms.ModelChoiceField(
        label='Origem de recurso recebedor',
        queryset=OrigemRecursoProjeto.objects,
        required=True,
        help_text='Selecione a origem que o valor será creditado',
    )

    plano_interno_recebedor = forms.ModelChoiceField(
        label='Plano interno recebedor', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True
    )
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(), required=True)
    steps = (
        [
            (
                'Filtro',
                {
                    'fields': (
                        'projeto',
                        'origem_recurso',
                        'plano_interno',
                        'projeto_recebedor',
                        'origem_recurso_recebedor',
                        'plano_interno_recebedor',
                        'justificativa',
                    )
                },
            )
        ],
        [('Unidade Gestora', {'fields': ('unidades',)})],
    )

    class Media:
        js = ['/static/plan_estrategico/js/RequisicaoAjusteInterno.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['projeto'].queryset = qs.order_by('projeto__codigo').distinct()
        self.fields['projeto_recebedor'].queryset = qs.order_by('projeto__codigo').distinct()

    def next_step(self):
        projeto = self.get_entered_data('projeto')
        origem_recurso = self.get_entered_data('origem_recurso')
        plano_interno = self.get_entered_data('plano_interno')
        plano_interno_recebedor = self.get_entered_data('plano_interno_recebedor')
        if 'unidades' in self.fields:
            if projeto and origem_recurso:
                dados = {}
                initial = {}
                for uo in UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user)):
                    if plano_interno:
                        valor_movimentado = plano_interno.valor_disponivel_movimentado(unidade_gestora=uo)
                        credito_disponivel = valor_movimentado
                        previsao_valor_a_receber = plano_interno_recebedor.saldo_plano_interno(unidade_gestora=uo)
                        dados[uo.setor_equivalente.sigla] = {
                            'Unidade': uo.setor_equivalente.sigla,
                            'PI concedente - Crédito disponível': format_money(credito_disponivel),
                            'PI recebedor - Valor a receber': format_money(previsao_valor_a_receber),
                        }
                        initial[uo.setor_equivalente.sigla] = 0
                self.fields['unidades'].widget.items = dados
                self.fields['unidades'].widget.initial = initial

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        origem_recurso_concedente = cleaned_data.get('origem_recurso')
        origem_recurso_destino = cleaned_data.get('origem_recurso_recebedor')
        if origem_recurso_concedente.origem_recurso.gnd != origem_recurso_destino.origem_recurso.gnd:
            self.add_error('', 'GND de origem e destino diferentes.')
        if origem_recurso_concedente.origem_recurso.acao_financeira.acao != origem_recurso_destino.origem_recurso.acao_financeira.acao:
            self.add_error('', 'Ação de origem e destino diferentes.')
        if origem_recurso_concedente.origem_recurso.acao_financeira.ptres != origem_recurso_destino.origem_recurso.acao_financeira.ptres:
            self.add_error('', 'PTRES de origem e destino diferentes.')
        return cleaned_data

    def clean_unidades(self):
        unidades = self.cleaned_data.get('unidades', {})
        plano_interno = self.cleaned_data.get('plano_interno', {})
        plano_interno_recebedor = self.cleaned_data.get('plano_interno_recebedor', {})
        for sigla, valor in unidades.items():
            uo = UnidadeGestora.objects.filter(setor_equivalente__sigla=sigla)[0]
            valor_planejado = plano_interno.get_disponivel_plano_interno(unidade_gestora=uo)
            valor_movimentado = plano_interno.valor_disponivel_movimentado(unidade_gestora=uo)
            credito_disponivel = valor_movimentado
            previsao_valor_a_receber = plano_interno_recebedor.saldo_plano_interno(unidade_gestora=uo)
            if not in_group(self.request.user, 'Administrador de Planejamento Estratégico'):
                if valor and valor > previsao_valor_a_receber:
                    valor = format_money(valor)
                    previsao_valor_a_receber = format_money(previsao_valor_a_receber)
                    mensagem = f'Valor (R$ {valor}) maior que o valor a receber do plano interno recebedor (R$ {previsao_valor_a_receber}).'
                    self.fields['unidades'].widget.error_message = mensagem
                    raise forms.ValidationError(mensagem)
            if valor and valor > credito_disponivel:
                valor = format_money(valor)
                credito_disponivel = format_money(credito_disponivel)
                mensagem = f'Valor (R$ {valor}) maior que o crédito disponível (R$ {credito_disponivel}).'
                self.fields['unidades'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)
            if valor and valor > valor_planejado:
                valor_planejado = format_money(valor_planejado)
                mensagem = (
                    f'Valor da movimentação solicitada superior ao valor a receber no Plano Interno. Valor máximo possível: R$ {valor_planejado}).'
                )
                self.fields['unidades'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)
        valores_planejados = [valor for valor in unidades.values() if valor != 0]
        if not valores_planejados:
            mensagem = 'Informe o valor a ser a ser ajustado.'
            self.fields['unidades'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        return unidades

    @transaction.atomic
    def processar(self):
        projeto_estrategico = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        justificativa = self.cleaned_data['justificativa']
        projeto_recebedor = self.cleaned_data['projeto_recebedor']
        origem_recurso_recebedor = self.cleaned_data['origem_recurso_recebedor']
        plano_interno_recebedor = self.cleaned_data['plano_interno_recebedor']
        tipo_requisicao = MovimentacaoCredito.TIPO_AJUSTE_INTERNO
        status = MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS
        plano_atividade = projeto_estrategico.plano_atividade
        ano = plano_atividade.ano_base.ano
        maior_codigo = MovimentacaoCredito.objects.filter(numero__startswith=str(ano)).count()
        sequencial = str(int(maior_codigo + 1)).zfill(6)
        numero = f'{ano}RM{sequencial}'
        movimentacao_credito = MovimentacaoCredito.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            numero=numero,
            projeto_estrategico=projeto_estrategico,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            justificativa=justificativa,
            tipo_requisicao=tipo_requisicao,
            projeto_recebedor=projeto_recebedor,
            origem_recurso_recebedor=origem_recurso_recebedor,
            plano_interno_recebedor=plano_interno_recebedor,
        )
        for sigla, valor in self.request.POST.items():
            if sigla.endswith('_item'):
                sigla = sigla.replace('_item', '')
                if valor != '':
                    try:
                        valor_numerico = valor.replace('.', '').replace(',', '.')
                        valor_numerico = Decimal(valor_numerico)

                        if valor_numerico > 0:
                            uo = UnidadeGestora.objects.filter(setor_equivalente__sigla=sigla).first()
                            MovimentacaoCreditoUnidade.objects.create(movimentacao=movimentacao_credito, unidade=uo, valor=valor_numerico)
                    except ValueError, TypeError, decimal.ConversionSyntax:
                        pass
        MovimentacaoCreditoHistorico.objects.create(
            movimentacao=movimentacao_credito, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        return movimentacao_credito


class IndeferirMovimentacaoCreditoForm(forms.ModelFormPlus):
    motivo_indeferimento = forms.CharField(label='Motivo do indeferimento', required=True, widget=forms.Textarea)

    class Meta:
        model = MovimentacaoCredito
        fields = ('motivo_indeferimento',)

    def save(self):
        self.instance.indeferir_movimentacaocredito()


class CancelarMovimentacaoCreditoForm(forms.ModelFormPlus):
    motivo_cancelamento = forms.CharField(label='Motivo do cancelamento', required=True, widget=forms.Textarea)

    class Meta:
        model = MovimentacaoCredito
        fields = ('motivo_cancelamento',)

    def save(self):
        self.instance.cancelar_movimentacaocredito(self.request.user)


class NotaCreditoForm(forms.ModelFormPlus):
    documento_siafi = forms.CharFieldPlus(label='Documento SIAFI', required=True, widget=forms.TextInput(), max_length=6)

    class Meta:
        model = NotaCredito
        fields = ('unidade', 'unidade_orcamentaria', 'ano', 'documento_siafi')

    def __init__(self, *args, **kwargs):
        movimentacao = kwargs.pop('movimentacao')
        super().__init__(*args, **kwargs)
        self.instance.movimentacao = movimentacao
        self.fields['unidade'].initial = movimentacao.projeto_estrategico.projeto.unidade_gestora
        self.fields['unidade_orcamentaria'].initial = ClassificacaoInstitucional.objects.get(codigo='26435')
        self.fields['ano'].initial = movimentacao.projeto_estrategico.plano_atividade.ano_base
        self.fields['unidade'].widget.readonly = True
        self.fields['ano'].widget.attrs['readonly'] = True
        self.fields['unidade_orcamentaria'].widget.readonly = True

    def clean(self):
        super().clean()
        documento_siafi = self.cleaned_data.get('documento_siafi')
        unidade = self.cleaned_data.get('unidade')
        unidade_orcamentaria = self.cleaned_data.get('unidade_orcamentaria')
        ano = self.cleaned_data.get('ano')
        numero_nota_credito = f'{unidade.codigo_ug}{unidade_orcamentaria.codigo}{ano}NC{documento_siafi}'

        if documento_siafi:
            if not documento_siafi.isdigit():
                raise forms.ValidationError('O código do documento SIAFI deve conter apenas dígitos numéricos.')
            if NotaCredito.objects.filter(numero=numero_nota_credito).exclude(status=NotaCredito.STATUS_CANCELADA).exists():
                raise ValidationError(f'A nota de crédito {numero_nota_credito} já está associada a uma requisição de movimentação de crédito.')

            documento_siafi_str = str(documento_siafi)
            if len(documento_siafi_str) != 6:
                raise forms.ValidationError('O código do documento SIAFI deve conter 6 dígitos')
        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        unidade = self.cleaned_data['unidade']
        codigo_ug = self.cleaned_data['unidade'].codigo_ug
        unidade_orcamentaria = self.cleaned_data['unidade_orcamentaria']
        ano = self.cleaned_data['ano']
        documemto_siafi = self.cleaned_data['documento_siafi']
        numero = f'{codigo_ug}{unidade_orcamentaria.codigo}{ano}NC{documemto_siafi}'
        NotaCredito.objects.create(
            movimentacao=self.instance.movimentacao,
            unidade=unidade,
            codigo_ug=codigo_ug,
            unidade_orcamentaria=unidade_orcamentaria,
            ano=ano,
            documento_siafi=documemto_siafi,
            numero=numero,
        )


class NotaDotacaoForm(forms.ModelFormPlus):
    documento_siafi = forms.CharFieldPlus(label='Documento SIAFI', required=True, widget=forms.TextInput(), max_length=6)
    unidade_atendida = forms.ModelChoiceFieldPlus2(
        label='Unidade responsável',
        queryset=UnidadeGestora.objects.all(),
        required=True,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS),
    )

    class Meta:
        model = NotaDotacao
        fields = ('unidade', 'unidade_orcamentaria', 'ano', 'documento_siafi', 'unidade_atendida')

    def __init__(self, *args, **kwargs):
        movimentacao = kwargs.pop('movimentacao')
        super().__init__(*args, **kwargs)
        self.instance.movimentacao = movimentacao
        self.fields['unidade'].initial = movimentacao.projeto_estrategico.projeto.unidade_gestora
        if self.instance.movimentacao.tipo_requisicao == MovimentacaoCredito.TIPO_AJUSTE_INTERNO:
            mov_unidade = MovimentacaoCreditoUnidade.objects.filter(movimentacao=movimentacao)[0]
            self.fields['unidade'].initial = mov_unidade.unidade
        self.fields['unidade_orcamentaria'].initial = ClassificacaoInstitucional.objects.get(codigo='26435')
        self.fields['ano'].initial = movimentacao.projeto_estrategico.plano_atividade.ano_base
        self.fields['unidade'].widget.readonly = True
        self.fields['ano'].widget.attrs['readonly'] = True
        self.fields['unidade_orcamentaria'].widget.readonly = True

    def clean(self):
        super().clean()
        documento_siafi = self.cleaned_data.get('documento_siafi')

        if documento_siafi:
            if not documento_siafi.isdigit():
                raise forms.ValidationError('O código do documento SIAFI deve conter apenas dígitos numéricos.')

            documento_siafi_str = str(documento_siafi)
            if len(documento_siafi_str) != 6:
                raise forms.ValidationError('O código do documento SIAFI deve conter 6 dígitos')
        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        unidade = self.cleaned_data['unidade']
        codigo_ug = self.cleaned_data['unidade'].codigo_ug
        unidade_orcamentaria = self.cleaned_data['unidade_orcamentaria']
        ano = self.cleaned_data['ano']
        documemto_siafi = self.cleaned_data['documento_siafi']
        unidade_atendida = self.cleaned_data['unidade_atendida']
        numero = f'{codigo_ug}{unidade_orcamentaria.codigo}{ano}ND{documemto_siafi}'
        NotaDotacao.objects.create(
            movimentacao=self.instance.movimentacao,
            unidade=unidade,
            codigo_ug=codigo_ug,
            unidade_orcamentaria=unidade_orcamentaria,
            ano=ano,
            documento_siafi=documemto_siafi,
            numero=numero,
            unidade_atendida=unidade_atendida,
        )


def ua_vinculada_field() -> forms.TypedChoiceField:
    return forms.TypedChoiceField(
        label='Despesa vinculada à',
        coerce=int,
        choices=RequisicaoDespesa.UA_VINCULADA_CHOICES,
        initial=RequisicaoDespesa.UA_PRINCIPAL,
        required=True,
        widget=forms.RadioSelect,
    )


def remover_ua_vinculada_sem_ug_secundaria(form: FormWizardPlus):
    """Mantém a escolha de UA vinculada só quando a UG do usuário tem UG secundária cadastrada."""
    setor_ug = get_setor_unidade_gestora(user=form.request.user)
    unidade_gestora = UnidadeGestora.objects.filter(setor_equivalente=setor_ug).first() if setor_ug else None
    if not (unidade_gestora and unidade_gestora.ug_secundaria):
        form.original_fields.pop('ua_vinculada', None)
        form.fields.pop('ua_vinculada', None)


class RequisicaoDotacaoProvisoriaForm(FormWizardPlus):
    processo = forms.ModelChoiceField(
        queryset=ProcessoEletronico.objects, widget=AutocompleteWidget(), label='Processo administrativo', required=True
    )
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all(), required=True)

    origem_recurso = forms.ModelChoiceField(label='Origem de recurso', queryset=OrigemRecursoProjeto.objects, required=True)

    plano_interno = forms.ModelChoiceField(label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True)

    atividade = forms.ModelPopupChoiceField(
        label='Atividade',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_requisicaodespesa.html',
    )
    tipo_finalidade = forms.ChoiceField(
        label='Tipo de Finalidade',
        choices=RequisicaoDespesa.FINALIDADE_CHOICES,
        required=True,
        widget=forms.RadioSelect,
        help_text='Selecione o tipo de procedimento. Esta escolha determina o fluxo de tramitação após a autorização do Ordenador de Despesas.',
    )
    finalidade = forms.CharField(label='Finalidade', widget=forms.Textarea(), required=True)
    valor_provisorio = forms.DecimalFieldPlus(label='Valor da requisição provisória R$', required=True)
    ua_vinculada = ua_vinculada_field()
    steps = (
        [('Filtro', {'fields': ('projeto', 'origem_recurso', 'plano_interno', 'processo')})],
        [('Atividades', {'fields': ('atividade', 'ua_vinculada', 'tipo_finalidade', 'finalidade', 'valor_provisorio')})],
    )

    class Media:
        js = ['/static/plan_estrategico/js/RequisicaoMovimentacao.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        remover_ua_vinculada_sem_ug_secundaria(self)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['projeto'].queryset = qs.order_by('projeto__codigo').distinct()
        setores_que_o_usuario_pode_criar_processo = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=True)
        self.fields['plano_interno'].queryset = PlanoInternoPlanoAtividade.objects.filter(plano_atividade=plano_atividade)
        self.fields['processo'].queryset = (
            ProcessoEletronico.ativos.by_user(self.request.user)
            .filter(setor_atual__in=list(setores_que_o_usuario_pode_criar_processo))
            .exclude(
                id__in=RequisicaoDespesa.objects.filter(
                    status__in=[
                        RequisicaoDespesa.STATUS_CADASTRADA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO,
                        RequisicaoDespesa.STATUS_INCONSISTENTE,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
                    ],
                    processo__isnull=False,
                ).values_list('processo__id', flat=True)
            )
        )

    def next_step(self):
        projeto = self.get_entered_data('projeto')
        origem_recurso = self.get_entered_data('origem_recurso')
        plano_interno = self.get_entered_data('plano_interno')
        unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))
        if 'atividade' in self.fields:
            self.fields['atividade'].queryset = AtividadeEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade=projeto,
                unidade_gestora=unidade[0],
                plano_interno=plano_interno,
                origem_recurso_etapa__origem_recurso_projeto=origem_recurso,
            )

    def clean(self):
        super().clean()
        if not get_setor_unidade_administrativa(user=self.request.user):
            raise forms.ValidationError(
                'O Setor responsável administrativo da unidade gestora não está configurado. Entre em contato com a Pró-Reitoria para efetuar o cadastro.'
            )

        return self.cleaned_data

    @transaction.atomic
    def processar(self):
        macroprocesso = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        processo = self.cleaned_data['processo']
        atividade = self.cleaned_data['atividade']
        unidade_gestora = self.cleaned_data['atividade'].unidade_gestora
        tipo_requisicao = RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA
        status = RequisicaoDespesa.STATUS_CADASTRADA
        plano_atividade = macroprocesso.plano_atividade
        # maior_codigo = RequisicaoDespesa.objects.filter(numero__startswith=str(ano)).count()
        # sequencial = str(int(maior_codigo + 1)).zfill(6)
        # numero = f"{ano}RD{sequencial}"
        finalidade = self.cleaned_data['finalidade']
        tipo_finalidade = int(self.cleaned_data['tipo_finalidade'])
        valor_provisorio = self.cleaned_data['valor_provisorio']
        ano_planoatividade = plano_atividade.ano_base
        dotacao_provisoria = RequisicaoDespesa.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            macroprocesso=macroprocesso,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            processo=processo,
            atividade=atividade,
            finalidade=finalidade,
            tipo_finalidade=tipo_finalidade,
            valor_provisorio=valor_provisorio,
            valor_inicial=valor_provisorio,
            tipo_requisicao=tipo_requisicao,
            unidade_gestora=unidade_gestora,
            ua_vinculada=self.cleaned_data.get('ua_vinculada') or RequisicaoDespesa.UA_PRINCIPAL,
            numero=RequisicaoDespesa.get_proximo_numero_requisicao(ano_planoatividade),
        )
        RequisicaoDespesaHistorico.objects.create(
            despesa=dotacao_provisoria, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )

        # dotacao_provisoria.gerar_documento_requisicao(self.request)
        # tramite_novo = Tramite()
        # tramite_novo.processo = processo
        # tramite_novo.tramitar_processo(
        #    remetente_setor=processo.setor_atual,
        #    remetente_vinculo=self.request.user.get_vinculo(),
        #    destinatario_setor=get_setor_unidade_administrativa(user=self.request.user),
        #    papel=self.request.user.get_relacionamento().papeis_ativos.first(),
        #    despacho_corpo=None,
        #    destinatario_vinculo=None,
        #    assinar_tramite=False,
        # )

        return dotacao_provisoria


class RequisicaoDotacaoEmpenhoForm(FormWizardPlus):
    processo = forms.ModelChoiceField(
        queryset=ProcessoEletronico.objects, widget=AutocompleteWidget(), label='Processo administrativo', required=True
    )
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all(), required=True)

    origem_recurso = forms.ModelChoiceField(label='Origem de recurso', queryset=OrigemRecursoProjeto.objects, required=True)

    plano_interno = forms.ModelChoiceField(label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True)

    atividade = forms.ModelPopupChoiceField(
        label='Atividade',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_requisicaodespesa.html',
    )
    finalidade = forms.CharField(label='Finalidade', widget=forms.Textarea(), required=True)
    valor_empenho = forms.DecimalFieldPlus(label='Valor da requisição R$', required=True)
    ua_vinculada = ua_vinculada_field()
    steps = (
        [('Filtro', {'fields': ('projeto', 'origem_recurso', 'plano_interno', 'processo')})],
        [('Atividades', {'fields': ('atividade', 'ua_vinculada', 'finalidade', 'valor_empenho')})],
    )

    class Media:
        js = ['/static/plan_estrategico/js/RequisicaoMovimentacao.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        remover_ua_vinculada_sem_ug_secundaria(self)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['projeto'].queryset = qs.order_by('projeto__codigo').distinct()
        self.fields['plano_interno'].queryset = PlanoInternoPlanoAtividade.objects.filter(plano_atividade=plano_atividade)
        setores_que_o_usuario_pode_criar_processo = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=True)
        self.fields['processo'].queryset = (
            ProcessoEletronico.ativos.by_user(self.request.user)
            .filter(setor_atual__in=list(setores_que_o_usuario_pode_criar_processo))
            .exclude(
                id__in=RequisicaoDespesa.objects.filter(
                    status__in=[
                        RequisicaoDespesa.STATUS_CADASTRADA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO,
                        RequisicaoDespesa.STATUS_INCONSISTENTE,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
                    ],
                    processo__isnull=False,
                ).values_list('processo__id', flat=True)
            )
        )

    def next_step(self):
        projeto = self.get_entered_data('projeto')
        origem_recurso = self.get_entered_data('origem_recurso')
        plano_interno = self.get_entered_data('plano_interno')
        unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))
        if 'atividade' in self.fields:
            self.fields['atividade'].queryset = AtividadeEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade=projeto,
                unidade_gestora=unidade[0],
                plano_interno=plano_interno,
                origem_recurso_etapa__origem_recurso_projeto=origem_recurso,
            )

    def clean(self):
        super().clean()
        if not get_setor_unidade_administrativa(user=self.request.user):
            raise forms.ValidationError(
                'O Setor responsável administrativo da unidade gestora não está configurado. Entre em contato com a Pró-Reitoria para efetuar o cadastro.'
            )
        return self.cleaned_data

    def clean_valor_empenho(self):
        if not self.errors:
            atividade = self.get_entered_data('atividade')
            valor_empenho = self.get_entered_data('valor_empenho')
            saldo_disponivel = atividade.saldo_disponivel_empenho_atividade()
            if valor_empenho < 0:
                mensagem = 'O valor da requisição não pode ser negativo.'
                self.fields['valor_empenho'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)
            if saldo_disponivel == 0:
                mensagem = 'Saldo Indisponível. Para prosseguir, selecione uma atividade com saldo disponível.'
                self.fields['valor_empenho'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)
            if valor_empenho > saldo_disponivel:
                valor_empenho = format_money(valor_empenho)
                saldo_disponivel = format_money(saldo_disponivel)
                mensagem = f'o Valor R$ {valor_empenho} é maior que o saldo disponível R$ {saldo_disponivel}.'
                self.fields['valor_empenho'].widget.error_message = mensagem
                raise forms.ValidationError(mensagem)
        return self.cleaned_data['valor_empenho']

    @transaction.atomic
    def processar(self):
        macroprocesso = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        processo = self.cleaned_data['processo']
        atividade = self.cleaned_data['atividade']
        tipo_requisicao = RequisicaoDespesa.TIPO_DOTACAO_EMPENHO
        status = RequisicaoDespesa.STATUS_CADASTRADA
        plano_atividade = macroprocesso.plano_atividade
        unidade_gestora = self.cleaned_data['atividade'].unidade_gestora
        # maior_codigo = RequisicaoDespesa.objects.filter(numero__startswith=str(ano)).count()
        # sequencial = str(int(maior_codigo + 1)).zfill(6)
        # numero = f"{ano}RD{sequencial}"
        valor_empenho = self.cleaned_data['valor_empenho']
        finalidade = self.cleaned_data['finalidade']
        ano_planoatividade = plano_atividade.ano_base
        dotacaoempenho = RequisicaoDespesa.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            macroprocesso=macroprocesso,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            processo=processo,
            atividade=atividade,
            finalidade=finalidade,
            tipo_requisicao=tipo_requisicao,
            valor=valor_empenho,
            valor_inicial=valor_empenho,
            unidade_gestora=unidade_gestora,
            ua_vinculada=self.cleaned_data.get('ua_vinculada') or RequisicaoDespesa.UA_PRINCIPAL,
            numero=RequisicaoDespesa.get_proximo_numero_requisicao(ano_planoatividade),
        )
        RequisicaoDespesaHistorico.objects.create(
            despesa=dotacaoempenho, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        return dotacaoempenho


class CancelarRequisicaoDespesaForm(forms.ModelFormPlus):
    motivo_cancelamento = forms.CharField(label='Motivo do cancelamento', required=True, widget=forms.Textarea)

    class Meta:
        model = RequisicaoDespesa
        fields = ('motivo_cancelamento',)

    def save(self):
        self.instance.cancelar_requisicaodespesa(self.request.user)
        if self.instance.status != RequisicaoDespesa.STATUS_CONCLUIDA:
            # Adiciona despacho no processo
            self.instance.cancelar_documento_requisicao(self.request)


def validar_setor_destino_cdo(requisicao: RequisicaoDespesa) -> None:
    """Garante que os setores por onde o processo vai passar após o CDO estão configurados."""
    msg = '{} não está configurado. Entre em contato com a Pró-Reitoria para efetuar o cadastro.'
    unidade_gestora = requisicao.get_unidade_gestora_autorizadora()
    if not unidade_gestora:
        raise forms.ValidationError(msg.format(f'A UG Secundária ({requisicao.unidade_gestora.ug_secundaria}) da unidade gestora'))
    if not unidade_gestora.setor_ordenador_despesa:
        raise forms.ValidationError(msg.format(f'O Setor responsável ordenador de despesa da unidade gestora {unidade_gestora}'))
    if requisicao.precisa_anuencia() and not requisicao.unidade_gestora.possui_anuente():
        raise forms.ValidationError(
            f'Não há servidor com função de Diretor, Diretor-Geral ou Reitor na unidade gestora {requisicao.unidade_gestora} para anuir a despesa. '
            'Entre em contato com a Gestão de Pessoas para regularizar o cadastro de funções.'
        )


def validar_destino_emissao_cdo(requisicao: RequisicaoDespesa, autorizacao_declarada: bool) -> None:
    """Com a autorização do ordenador declarada no processo, o CDO segue ao setor financeiro; senão, à anuência ou ao ordenador."""
    if not autorizacao_declarada:
        validar_setor_destino_cdo(requisicao)
    elif not requisicao.unidade_gestora.setor_financeiro:
        raise forms.ValidationError('O setor financeiro não está configurado. Entre em contato com a Pró-Reitoria para realizar o cadastro.')


def configurar_textos_encaminhamento_cdo(form: forms.ModelFormPlus, documento: str, permite_autorizacao_declarada: bool = False) -> None:
    """Ajusta o aviso e o despacho sugerido ao setor para onde o processo vai após o CDO (anuência ou ordenador).

    Quando o form permite declarar a autorização do ordenador no processo, o aviso cita também o setor financeiro, destino nesse caso.
    """
    requisicao = form.instance
    setor_destino = requisicao.get_setor_destino_apos_cdo()
    sigla_destino = setor_destino.sigla if setor_destino else '(setor não configurado)'
    if requisicao.precisa_anuencia():
        etapa = 'anuência da despesa'
        form.despacho_inicial = f'Ao {sigla_destino} para anuência da realização da respectiva despesa.'
    else:
        etapa = 'autorização do ordenador de despesa'
        form.despacho_inicial = f'Ao {sigla_destino} para autorização do ordenador de despesa para a realização da respectiva despesa.'
    form.INFO = (
        f'Ao finalizar será gerado o {documento} e o processo será encaminhado automaticamente para {setor_destino or sigla_destino}, para {etapa}.'
    )
    if permite_autorizacao_declarada:
        setor_financeiro = requisicao.unidade_gestora.setor_financeiro
        form.INFO += (
            ' Se for declarada a autorização do ordenador de despesa no processo, o processo será encaminhado ao setor financeiro '
            f'({setor_financeiro or "setor não configurado"}).'
        )
    form.initial['despacho'] = form.despacho_inicial


class EmitirCDOProvisoriaForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Emitir CDO e Assinar'
    fonte = forms.CharField(label='Fonte', required=True, max_length=10)
    despacho = forms.CharField(label='Despacho', required=True, widget=forms.Textarea, max_length=1000)
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos
        self.fields['fonte'].initial = None
        configurar_textos_encaminhamento_cdo(self, 'CDO provisório')

    class Meta:
        model = RequisicaoDespesa
        fields = ('fonte',)

    def clean(self):
        super().clean()
        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        if processo.setor_atual != self.instance.unidade_gestora.setor_administrativo:
            raise forms.ValidationError(
                f'Para emitir o CDO Provisório o processo {processo} deve estar na caixa do setor {self.instance.unidade_gestora.setor_administrativo}.'
            )

        validar_setor_destino_cdo(self.instance)

        if not ModeloDocumento.objects.filter(nome='Certificado de Dotação Orçamentária CDO').exists():
            raise forms.ValidationError(
                'Não existe o modelo de documento texto com nome de "Certificado de Dotação Orçamentária CDO". Entre em contato com a Pró-Reitoria para efetuar o cadastro.'
            )

        return self.cleaned_data

    def clean_fonte(self):
        fonte = self.cleaned_data.get('fonte')

        if not fonte.isdigit() or len(fonte) != 10:
            raise forms.ValidationError('A fonte deve conter exatamente 10 números.')

        return fonte

    @transaction.atomic()
    def save(self, *args, **kwargs):
        despacho = self.cleaned_data.get('despacho')

        # Cria um novo documento da CDO Provisória
        try:
            modelo = ModeloDocumento.objects.get(nome='Certificado de Dotação Orçamentária CDO')
        except Exception:
            raise ValidationError('Não existe o modelo de documento texto com nome de "Certificado de Dotação Orçamentária CDO".')

        user = self.request.user
        setor_dono = get_setor(self.request.user)
        finalidade = self.instance.finalidade
        origem_recurso = self.instance.origem_recurso
        ua_executora = self.instance.unidade_gestora.setor_equivalente.sigla

        assunto = f'CDO Provisório - {ua_executora} - {origem_recurso} - {finalidade}'
        variaveis = {}
        variaveis['conteudo_html'] = self.instance.get_cdo_provisorio_html(despacho)

        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user,
            setor_dono=setor_dono,
            modelo=modelo,
            assunto=assunto[:255],
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
            variaveis=variaveis,
        )

        # Conclui e assina documento
        documento_novo.concluir()
        documento_novo.save()
        SolicitacaoAssinatura.objects.get_or_create(documento_id=documento_novo.id, solicitado=self.request.user.get_vinculo())
        documento_novo.solicitar_assinatura()
        assinar_documento_com_senha(documento_novo, self.request.user, self.cleaned_data.get('papel'))
        self.instance.processo.adicionar_documento_texto(documento_novo)

        # Encaminha o processo para o GABIN cadastrado na configuração da unidade

        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        tramite_novo = Tramite()
        tramite_novo.processo = processo
        tramite_novo.tramitar_processo(
            remetente_setor=processo.setor_atual,
            remetente_vinculo=self.request.user.get_vinculo(),
            destinatario_setor=self.instance.get_setor_destino_apos_cdo(),
            papel=self.cleaned_data.get('papel'),
            despacho_corpo=None,
            destinatario_vinculo=None,
            assinar_tramite=False,
        )

        # Vincula documento   na requisição e atualiza status
        self.instance.cdo_provisorio = documento_novo
        self.instance.status = self.instance.get_status_apos_cdo()
        self.instance.save()

        # Adiciona o histórico
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=self.instance.status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )


class EmitirCDOForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Emitir CDO e Assinar'
    DESPACHO_AUTORIZACAO_DECLARADA = 'O requisitante declarou que a autorização desta despesa foi realizada pelo ordenador diretamente no processo vinculado. Segue para o setor financeiro para registro do documento do SIAFI.'
    fonte = forms.CharField(label='Fonte', required=True, max_length=10)
    despacho = forms.CharFieldPlus(label='Despacho', required=True, widget=forms.Textarea, max_length=1000)
    autorizacao_ordenador_declarada_no_processo = forms.BooleanField(
        required=False,
        label='Declaro que o processo vinculado já possui a autorização do ordenador de despesa para esta despesa.',
        help_text=(
            'Marque esta opção somente quando o processo administrativo vinculado já contiver despacho ou documento com a autorização expressa do ordenador de despesa. Ao marcar, a RD não passará pela etapa de autorização do ordenador e será tramitada diretamente para o setor financeiro da UA.'
        ),
    )
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos
        self.fields['fonte'].initial = None
        configurar_textos_encaminhamento_cdo(self, 'CDO', permite_autorizacao_declarada=True)

    class Meta:
        model = RequisicaoDespesa
        fields = ('fonte', 'autorizacao_ordenador_declarada_no_processo')

    def get_despacho(self):
        """Despacho do CDO; o sugerido é trocado pelo texto de autorização declarada quando o requisitante marca essa opção."""
        despacho = self.cleaned_data.get('despacho')
        if self.cleaned_data.get('autorizacao_ordenador_declarada_no_processo') and despacho == self.despacho_inicial:
            return self.DESPACHO_AUTORIZACAO_DECLARADA
        return despacho

    def clean(self):
        super().clean()
        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        if processo.setor_atual != self.instance.unidade_gestora.setor_administrativo:
            raise forms.ValidationError(
                f'Para emitir o CDO o processo {processo} deve estar na caixa do setor {self.instance.unidade_gestora.setor_administrativo}.'
            )

        validar_destino_emissao_cdo(self.instance, self.cleaned_data.get('autorizacao_ordenador_declarada_no_processo'))

        if not ModeloDocumento.objects.filter(nome='Certificado de Dotação Orçamentária CDO').exists():
            raise forms.ValidationError(
                'Não existe o modelo de documento texto com nome de "Certificado de Dotação Orçamentária CDO". Entre em contato com a Pró-Reitoria para efetuar o cadastro.'
            )

        eh_definitiva_de_provisoria = (
            self.instance.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO and self.instance.valor_provisorio is not None
        )
        if eh_definitiva_de_provisoria and self.instance.total_naturezas_despesa() != self.instance.valor:
            raise forms.ValidationError(
                f'A soma das naturezas de despesa (R$ {format_money(self.instance.total_naturezas_despesa())}) deve ser igual ao valor definitivo '
                f'da requisição (R$ {format_money(self.instance.valor)}). Ajuste as linhas de natureza de despesa antes de emitir o CDO.'
            )

        return self.cleaned_data

    def clean_fonte(self):
        fonte = self.cleaned_data.get('fonte')

        if not fonte.isdigit() or len(fonte) != 10:
            raise forms.ValidationError('A fonte deve conter exatamente 10 números.')

        return fonte

    @transaction.atomic()
    def save(self, *args, **kwargs):
        despacho = self.get_despacho()
        autorizacao_ordenador_declarada_no_processo = self.cleaned_data.get('autorizacao_ordenador_declarada_no_processo')

        # Requisição vinda de uma provisória só tem o comprovante anexado aqui, com as NDs já ajustadas.
        if self.instance.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_EMPENHO and self.instance.valor_provisorio is not None:
            self.instance.gerar_documento_requisicao_empenho(self.request)

        # Cria um novo documento da CDO
        try:
            modelo = ModeloDocumento.objects.get(nome='Certificado de Dotação Orçamentária CDO')
        except Exception:
            raise ValidationError('Não existe o modelo de documento texto com nome de "Certificado de Dotação Orçamentária CDO".')

        user = self.request.user
        setor_dono = get_setor(self.request.user)
        finalidade = self.instance.finalidade
        origem_recurso = self.instance.origem_recurso
        ua_executora = self.instance.unidade_gestora.setor_equivalente.sigla

        assunto = f'CDO - {ua_executora} - {origem_recurso} - {finalidade}'

        variaveis = {}
        variaveis['conteudo_html'] = self.instance.get_cdo_empenho_html(despacho)

        documento_novo = DocumentoTexto.adicionar_documento_texto(
            usuario=user,
            setor_dono=setor_dono,
            modelo=modelo,
            assunto=assunto[:255],
            nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
            variaveis=variaveis,
        )

        # Conclui e assina documento
        documento_novo.concluir()
        documento_novo.save()
        SolicitacaoAssinatura.objects.get_or_create(documento_id=documento_novo.id, solicitado=self.request.user.get_vinculo())
        documento_novo.solicitar_assinatura()
        assinar_documento_com_senha(documento_novo, self.request.user, self.cleaned_data.get('papel'))
        self.instance.processo.adicionar_documento_texto(documento_novo)
        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        if autorizacao_ordenador_declarada_no_processo:
            tramite_novo = Tramite()
            tramite_novo.processo = processo
            destinatario_setor = self.instance.unidade_gestora.setor_financeiro
            tramite_novo.tramitar_processo(
                remetente_setor=processo.setor_atual,
                remetente_vinculo=self.request.user.get_vinculo(),
                destinatario_setor=destinatario_setor,
                papel=self.cleaned_data.get('papel'),
                despacho_corpo=self.DESPACHO_AUTORIZACAO_DECLARADA,
                destinatario_vinculo=None,
                assinar_tramite=True,
            )

            # Atualiza status
            self.instance.cdo = documento_novo
            self.instance.status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
            self.instance.save()

        else:
            tramite_novo = Tramite()
            tramite_novo.processo = processo
            tramite_novo.tramitar_processo(
                remetente_setor=processo.setor_atual,
                remetente_vinculo=self.request.user.get_vinculo(),
                destinatario_setor=self.instance.get_setor_destino_apos_cdo(),
                papel=self.cleaned_data.get('papel'),
                despacho_corpo=None,
                destinatario_vinculo=None,
                assinar_tramite=False,
            )

            # Vincula documento na requisição e atualiza status
            self.instance.cdo = documento_novo
            self.instance.status = self.instance.get_status_apos_cdo()
            self.instance.save()

        # Adiciona o histórico
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=self.instance.status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )


class AutorizarDespesaProvisoriaForm(forms.ModelFormPlus):
    INFO = 'Ao finalizar será adicionado um despacho autorizando a despesa e o processo será encaminhado automaticamente ao setor correspondente à finalidade selecionada.'
    SUBMIT_LABEL = 'Autorizar Despesa Provisória'
    despacho_autorizacao_provisoria = forms.CharField(label='Despacho', required=True, widget=forms.Textarea())
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    class Meta:
        model = RequisicaoDespesa
        fields = ('despacho_autorizacao_provisoria',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos
        valor = format_money(self.instance.valor_provisorio)
        origem = self.instance.origem_recurso
        ua = self.instance.unidade_gestora
        ano = self.instance.plano_atividade.ano_base
        finalidade = self.instance.finalidade
        tipo = self.instance.tipo_finalidade

        if tipo == RequisicaoDespesa.FINALIDADE_LICITATORIO:
            self.initial['despacho_autorizacao_provisoria'] = (
                f'Autorizo a abertura de processo licitatório para {finalidade}, no valor total de R$ {valor}, '
                f'com dotação orçamentária (Origem de recursos SUAP {origem}), disponível para {ua} '
                f'no plano de atividades de {ano}. À DILIC para as providências necessárias.'
            )
        elif tipo == RequisicaoDespesa.FINALIDADE_CONTRATACAO_COM_PARECER:
            setor_adm = ua.setor_administrativo
            self.initial['despacho_autorizacao_provisoria'] = (
                f'Autorizo o procedimento relativo ao referido contrato administrativo para {finalidade}, '
                f'no valor total de R$ {valor}, com dotação orçamentária (Origem de recursos SUAP {origem}), '
                f'disponível para {ua} no plano de atividades de {ano}. '
                f'À {setor_adm} para certificação de completude processual à luz de parecer jurídico '
                f'referencial e demais providências para a contratação.'
            )
        else:
            self.initial['despacho_autorizacao_provisoria'] = (
                f'Autorizo o procedimento relativo ao referido contrato administrativo para {finalidade}, '
                f'no valor total de R$ {valor}, com dotação orçamentária (Origem de recursos SUAP {origem}), '
                f'disponível para {ua} no plano de atividades de {ano}. '
                f'À PROJU para emissão de parecer jurídico quanto à viabilidade legal da presente contratação.'
            )

    def get_destinatario_setor(self):
        tipo = self.instance.tipo_finalidade
        if tipo == RequisicaoDespesa.FINALIDADE_LICITATORIO:
            return Setor.objects.ativos().filter(pk=Configuracao.get_valor_por_chave('plan_estrategico', 'setor_licitacoes')).first()
        elif tipo == RequisicaoDespesa.FINALIDADE_CONTRATACAO_COM_PARECER:
            return self.instance.unidade_gestora.setor_administrativo
        else:
            return Setor.objects.ativos().filter(pk=Configuracao.get_valor_por_chave('plan_estrategico', 'setor_proju')).first()

    def clean(self):
        super().clean()
        tipo = self.instance.tipo_finalidade

        if tipo == RequisicaoDespesa.FINALIDADE_LICITATORIO:
            if not Configuracao.get_valor_por_chave('plan_estrategico', 'setor_licitacoes'):
                raise forms.ValidationError(
                    'O setor de licitação (DILIC) não está configurado. Entre em contato com a Pró-Reitoria para realizar o cadastro.'
                )
        elif tipo == RequisicaoDespesa.FINALIDADE_CONTRATACAO_SEM_PARECER:
            if not Configuracao.get_valor_por_chave('plan_estrategico', 'setor_proju'):
                raise forms.ValidationError('O setor da PROJU não está configurado. Entre em contato com a Pró-Reitoria para realizar o cadastro.')

        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        despacho_autorizacao_provisoria = self.cleaned_data.get('despacho_autorizacao_provisoria')
        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        tramite_novo = Tramite()
        tramite_novo.processo = processo
        tramite_novo.tramitar_processo(
            remetente_setor=processo.setor_atual,
            remetente_vinculo=self.request.user.get_vinculo(),
            destinatario_setor=self.get_destinatario_setor(),
            papel=self.cleaned_data.get('papel'),
            despacho_corpo=despacho_autorizacao_provisoria,
            destinatario_vinculo=None,
            assinar_tramite=True,
        )

        # Atualiza status — mantido em STATUS_AGUARDANDO_PROCESSO_LICITATORIO para os 3 fluxos
        self.instance.status = RequisicaoDespesa.STATUS_AGUARDANDO_PROCESSO_LICITATORIO
        self.instance.vinculo_autorizacao_provisoria = self.request.user.get_vinculo()
        self.instance.data_autorizacao_provisoria = datetime.datetime.now()
        self.instance.save()

        # Adiciona o histórico
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=RequisicaoDespesa.STATUS_AUTORIZADA, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=self.instance.status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )


class AutorizarDespesaEmpenhoForm(forms.ModelFormPlus):
    INFO = 'Ao finalizar será adicionado um despacho autorizando a despesa e o processo será encaminhado ao setor financeiro.'
    SUBMIT_LABEL = 'Autorizar Despesa'
    despacho_autorizacao_despesa = forms.CharField(label='Despacho', required=True, widget=forms.Textarea())
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    class Meta:
        model = RequisicaoDespesa
        fields = ('despacho_autorizacao_despesa',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos
        valor = format_money(self.instance.valor)
        if self.instance and self.instance.eh_tipo_reforco:
            texto = f"""Autorizo a realização da despesa para {self.instance.finalidade}, no valor total de R$ {valor}, a partir da dotação orçamentária (Origem de recursos SUAP  {self.instance.origem_recurso} ), disponível para {self.instance.unidade_gestora} no plano de atividades de {self.instance.plano_atividade.ano_base}, em reforço à nota de empenho {self.instance.empenhos.first().numero_empenho}.\n À {self.instance.unidade_gestora.setor_financeiro.sigla} para a emissão de reforça à referida nota de empenho e demais providências necessárias."""
        elif self.instance and self.instance.eh_tipo_anulacao:
            texto = f""" Autorizo a anulação de R$ {valor} do saldo da nota de empenho {self.instance.empenhos.first().numero_empenho} com a finalidade de {self.instance.finalidade}. À {self.instance.unidade_gestora.setor_financeiro.sigla} para emissão de registro orçamentário no SIAFI."""
        else:
            texto = f"""Autorizo a realização da despesa para {self.instance.finalidade}, no valor total de R$ {valor}, a partir da dotação orçamentária (Origem de recursos SUAP  {self.instance.origem_recurso} ), disponível para {self.instance.unidade_gestora} no plano de atividades de {self.instance.plano_atividade.ano_base}.\n À {self.instance.unidade_gestora.setor_financeiro.sigla} para a emissão(ões) de nota(s) de empenho e demais providências necessárias."""

        self.initial['despacho_autorizacao_despesa'] = texto

    def clean(self):
        super().clean()
        if not self.instance.unidade_gestora.setor_financeiro:
            raise forms.ValidationError('O setor financeiro não está configurado. Entre em contato com a Pró-Reitoria para realizar o cadastro.')

        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        despacho_autorizacao_despesa = self.cleaned_data.get('despacho_autorizacao_despesa')
        # Encaminha o processo para o setor de licitações cadastrado na configuração da unidade
        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        tramite_novo = Tramite()
        tramite_novo.processo = processo
        destinatario_setor = self.instance.unidade_gestora.setor_financeiro
        tramite_novo.tramitar_processo(
            remetente_setor=processo.setor_atual,
            remetente_vinculo=self.request.user.get_vinculo(),
            destinatario_setor=destinatario_setor,
            papel=self.cleaned_data.get('papel'),
            despacho_corpo=despacho_autorizacao_despesa,
            destinatario_vinculo=None,
            assinar_tramite=True,
        )

        # Atualiza status
        self.instance.status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
        self.instance.vinculo_autorizacao_despesa = self.request.user.get_vinculo()
        self.instance.data_autorizacao_despesa = datetime.datetime.now()
        self.instance.save()

        # Adiciona o histórico
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=RequisicaoDespesa.STATUS_AUTORIZADA, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=self.instance.status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )


class AnuirDespesaForm(forms.ModelFormPlus):
    INFO = 'Ao finalizar será adicionado um despacho de anuência e o processo será encaminhado ao setor responsável ordenador de despesa.'
    SUBMIT_LABEL = 'Anuir Despesa'
    despacho_anuencia = forms.CharField(label='Despacho', required=True, widget=forms.Textarea())
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    class Meta:
        model = RequisicaoDespesa
        fields = ('despacho_anuencia',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos
        valor = format_money(self.instance.valor_provisorio if self.instance.valor is None else self.instance.valor)
        setor_destino = self.instance.get_setor_destino_autorizacao()
        self.initial['despacho_anuencia'] = (
            f'Dou anuência à realização da despesa para {self.instance.finalidade}, no valor total de R$ {valor}, '
            f'a partir da dotação orçamentária (Origem de recursos SUAP {self.instance.origem_recurso}), disponível para {self.instance.unidade_gestora} '
            f'no plano de atividades de {self.instance.plano_atividade.ano_base}.\n Ao {setor_destino} para autorização do ordenador de despesa.'
        )

    def clean(self):
        super().clean()
        validar_setor_destino_cdo(self.instance)
        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        processo = self.instance.processo
        if processo.status == ProcessoStatus.STATUS_ANEXADO:
            processo = self.instance.processo.anexacao_anexadas.first().processo_anexador
        tramite_novo = Tramite()
        tramite_novo.processo = processo
        tramite_novo.tramitar_processo(
            remetente_setor=processo.setor_atual,
            remetente_vinculo=self.request.user.get_vinculo(),
            destinatario_setor=self.instance.get_setor_destino_autorizacao(),
            papel=self.cleaned_data.get('papel'),
            despacho_corpo=self.cleaned_data.get('despacho_anuencia'),
            destinatario_vinculo=None,
            assinar_tramite=True,
        )

        self.instance.status = RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO
        self.instance.vinculo_anuencia = self.request.user.get_vinculo()
        self.instance.data_anuencia = datetime.datetime.now()
        self.instance.save()

        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance, status=self.instance.status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )


class GerarRequisicaoDefinitivaForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Gerar Requisição Definitiva'
    valor = forms.DecimalFieldPlus(label='Valor definitivo R$', required=True)

    class Meta:
        model = RequisicaoDespesa
        fields = ('valor',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos
        # self.fields['despacho_autorizacao_provisoria'].initial = 'Autorizo a despesa.'

    def clean_valor(self):
        atividade = self.instance.atividade
        valor = self.cleaned_data.get('valor')
        saldo_disponivel = atividade.saldo_disponivel_empenho_atividade()
        if saldo_disponivel == 0:
            mensagem = 'Saldo da atividade é 0,00.'
            self.fields['valor'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        if valor > saldo_disponivel:
            valor = format_money(valor)
            saldo_disponivel = format_money(saldo_disponivel)
            mensagem = f'o Valor R$ {valor} é maior que o saldo disponível R$ {saldo_disponivel}.'
            self.fields['valor'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        return self.cleaned_data['valor']

    @transaction.atomic()
    def save(self, *args, **kwargs):
        # Atualiza status
        self.instance.status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO
        self.instance.valor = self.cleaned_data['valor']
        self.instance.tipo_requisicao = RequisicaoDespesa.TIPO_DOTACAO_EMPENHO
        self.instance.save()

        # Adiciona o histórico
        RequisicaoDespesaHistorico.objects.create(
            despesa=self.instance,
            status=RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO,
            alterado_em=datetime.datetime.now(),
            alterado_por=self.request.user,
        )
        # As NDs ainda estão com o valor provisório: o comprovante é anexado na emissão do CDO.


class NotaEmpenhoForm(forms.ModelFormPlus):
    documento_siafi = forms.CharFieldPlus(label='Documento SIAFI', required=True, widget=forms.TextInput(), max_length=6)

    class Meta:
        model = NotaEmpenho
        fields = ('unidade', 'unidade_orcamentaria', 'ano', 'documento_siafi')

    def __init__(self, *args, **kwargs):
        nota_empenho = kwargs.pop('nota_empenho')
        super().__init__(*args, **kwargs)
        requisicao_despesa = nota_empenho.requisicao
        self.instance = nota_empenho
        self.instance.requisicao = requisicao_despesa
        unidade_gestora = requisicao_despesa.atividade.unidade_gestora
        self.fields['unidade'].initial = unidade_gestora
        self.fields['unidade_orcamentaria'].initial = ClassificacaoInstitucional.objects.get(codigo='26435')
        self.fields['ano'].initial = requisicao_despesa.plano_atividade.ano_base
        self.fields['unidade'].widget.readonly = True
        self.fields['ano'].widget.attrs['readonly'] = True
        self.fields['unidade_orcamentaria'].widget.readonly = True

    def clean(self):
        super().clean()
        documento_siafi = self.cleaned_data.get('documento_siafi')
        unidade = self.cleaned_data.get('unidade')
        unidade_orcamentaria = self.cleaned_data.get('unidade_orcamentaria')
        ano = self.cleaned_data.get('ano')
        if documento_siafi:
            if not documento_siafi.isdigit():
                raise forms.ValidationError('O código do documento SIAFI deve conter apenas dígitos numéricos.')

            documento_siafi_str = str(documento_siafi)
            if len(documento_siafi_str) != 6:
                raise forms.ValidationError('O código do documento SIAFI deve conter 6 dígitos')

            numero_empenho = f'{unidade.codigo_ug}{unidade_orcamentaria.codigo}{ano}NE{documento_siafi}'

            if (
                NotaEmpenho.objects.filter(
                    numero_empenho=numero_empenho,
                    numero_ro__isnull=True,
                    requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
                )
                .exclude(status=NotaEmpenho.STATUS_CANCELADA)
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise ValidationError(f'O empenho {numero_empenho} já está associado a uma requisição de despesa.')

        return self.cleaned_data

    @transaction.atomic()
    def save(self, commit=True, *args, **kwargs):
        self.instance.codigo_ug = self.instance.unidade.codigo_ug
        unidade_orcamentaria = self.instance.unidade_orcamentaria
        ano = self.cleaned_data['ano']
        documento_siafi = self.cleaned_data['documento_siafi']

        numero_empenho = f'{self.instance.codigo_ug}{unidade_orcamentaria.codigo}{ano}NE{documento_siafi}'
        self.instance.documento_siafi = documento_siafi
        self.instance.numero_empenho = numero_empenho
        # self.instance.valor = self.instance.requisicao.valor
        if commit:
            self.instance.save()
        return self.instance

        # self.instance.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO
        # self.instance.requisicao.save()
        # RequisicaoDespesaHistorico.objects.create(
        #    despesa=self.instance.requisicao,
        ##    status=self.instance.requisicao.status,
        #    alterado_em=datetime.datetime.now(),
        #    alterado_por=self.request.user,
        # )


class RequisicaoReforcoEmpenhoForm(FormWizardPlus):
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects, required=True)
    origem_recurso = forms.ModelChoiceField(label='Origem de recurso', queryset=OrigemRecursoProjeto.objects, required=True)
    plano_interno = forms.ModelChoiceField(label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects, required=True)
    processo = forms.ModelChoiceField(
        queryset=ProcessoEletronico.objects, widget=AutocompleteWidget(), label='Processo administrativo', required=True
    )

    atividade = forms.ModelPopupChoiceField(
        label='Atividade',
        required=True,
        queryset=AtividadeEtapa.objects,
        list_template='plan_estrategico/templates/widgets/atividades_requisicaodespesa.html',
    )
    finalidade = forms.CharField(label='Finalidade', widget=forms.Textarea(), required=True)
    empenho = forms.ModelChoiceField(label='Empenho', queryset=NotaEmpenho.objects, required=True)
    valor_empenho = forms.DecimalFieldPlus(label='Valor da requisição R$', required=True)
    natureza_despesa = forms.ModelChoiceFieldPlus2(
        label='Natureza de despesa',
        queryset=NaturezaDespesaPlanoAtividade.objects.all(),
        required=True,
        widget=AutocompleteWidget(search_fields=NaturezaDespesaPlanoAtividade.SEARCH_FIELDS),
    )
    ua_vinculada = ua_vinculada_field()
    steps = (
        [('Filtro', {'fields': ('projeto', 'origem_recurso', 'plano_interno', 'processo')})],
        [('Atividades', {'fields': ('atividade', 'ua_vinculada', 'finalidade')})],
        [('Empenhos', {'fields': ('empenho', 'natureza_despesa', 'valor_empenho')})],
    )

    class Media:
        js = ['/static/plan_estrategico/js/RequisicaoMovimentacao.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        remover_ua_vinculada_sem_ug_secundaria(self)
        qs = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['projeto'].queryset = qs.order_by('projeto__codigo').distinct()
        setores_que_o_usuario_pode_criar_processo = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=True)
        self.fields['plano_interno'].queryset = PlanoInternoPlanoAtividade.objects.filter(plano_atividade=plano_atividade)
        self.fields['processo'].queryset = (
            ProcessoEletronico.ativos.by_user(self.request.user)
            .filter(setor_atual__in=list(setores_que_o_usuario_pode_criar_processo))
            .exclude(
                id__in=RequisicaoDespesa.objects.filter(
                    status__in=[
                        RequisicaoDespesa.STATUS_CADASTRADA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
                        RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA,
                        RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO,
                        RequisicaoDespesa.STATUS_INCONSISTENTE,
                        RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
                    ],
                    processo__isnull=False,
                ).values_list('processo__id', flat=True)
            )
        )

    def clean(self):
        super().clean()
        if not get_setor_unidade_administrativa(user=self.request.user):
            raise forms.ValidationError(
                'O Setor responsável administrativo da unidade gestora não está configurado. Entre em contato com a Pró-Reitoria para efetuar o cadastro.'
            )
        return self.cleaned_data

    def next_step(self):
        projeto = self.get_entered_data('projeto')
        origem_recurso = self.get_entered_data('origem_recurso')
        plano_interno = self.get_entered_data('plano_interno')
        unidade = UnidadeGestora.objects.filter(setor_equivalente=get_setor_unidade_gestora(user=self.request.user))
        if 'atividade' in self.fields:
            self.fields['atividade'].queryset = AtividadeEtapa.objects.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade=projeto,
                unidade_gestora=unidade[0],
                plano_interno=plano_interno,
                origem_recurso_etapa__origem_recurso_projeto=origem_recurso,
            )

        if 'empenho' in self.fields:
            self.fields['empenho'].queryset = (
                NotaEmpenho.objects.filter(
                    requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO, requisicao__atividade=self.get_entered_data('atividade')
                )
                .exclude(numero_empenho__isnull=True)
                .exclude(numero_empenho='')
                .exclude(status=NotaEmpenho.STATUS_CANCELADA)
                .annotate(tamanho=Length('numero_empenho'))
                .filter(tamanho=23)
            )

    def clean_atividade(self):
        atividade = self.cleaned_data.get('atividade')
        nes = NotaEmpenho.objects.filter(requisicao__atividade=atividade).exclude(status=NotaEmpenho.STATUS_CANCELADA)
        if not nes.exists():
            raise forms.ValidationError('Não há notas de empenho cadastradas para essa atividade')
        return atividade

    def clean_valor_empenho(self):
        atividade = self.get_entered_data('atividade')
        valor_empenho = self.get_entered_data('valor_empenho')
        saldo_disponivel = atividade.saldo_disponivel_empenho_atividade()
        if valor_empenho < 0:
            mensagem = 'O valor da requisição não pode ser negativo.'
            self.fields['valor_empenho'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        if saldo_disponivel == 0:
            mensagem = 'Saldo Indisponível. Para prosseguir, selecione uma atividade com saldo disponível.'
            self.fields['valor_empenho'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        if valor_empenho > saldo_disponivel:
            valor_empenho = format_money(valor_empenho)
            saldo_disponivel = format_money(saldo_disponivel)
            mensagem = f'o Valor R$ {valor_empenho} é maior que o saldo disponível R$ {saldo_disponivel}.'
            self.fields['valor_empenho'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        return self.cleaned_data['valor_empenho']

    @transaction.atomic
    def processar(self):
        macroprocesso = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        processo = self.cleaned_data['processo']
        atividade = self.cleaned_data['atividade']
        tipo_requisicao = RequisicaoDespesa.TIPO_REFORCO_EMPENHO
        status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO
        plano_atividade = macroprocesso.plano_atividade
        unidade_gestora = self.cleaned_data['atividade'].unidade_gestora
        empenho = self.cleaned_data['empenho']
        valor_empenho = self.cleaned_data['valor_empenho']
        finalidade = self.cleaned_data['finalidade']
        natureza_despesa = self.cleaned_data['natureza_despesa']
        ano_planoatividade = plano_atividade.ano_base
        requisicao_despesa = RequisicaoDespesa.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            macroprocesso=macroprocesso,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            processo=processo,
            atividade=atividade,
            finalidade=finalidade,
            tipo_requisicao=tipo_requisicao,
            valor=valor_empenho,
            valor_inicial=valor_empenho,
            unidade_gestora=unidade_gestora,
            ua_vinculada=self.cleaned_data.get('ua_vinculada') or RequisicaoDespesa.UA_PRINCIPAL,
            numero=RequisicaoDespesa.get_proximo_numero_requisicao(ano_planoatividade),
        )
        RequisicaoDespesaHistorico.objects.create(
            despesa=requisicao_despesa, status=status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        NotaEmpenho.objects.create(requisicao=requisicao_despesa, naturezadespesa=natureza_despesa, numero_empenho=empenho, valor=valor_empenho)
        requisicao_despesa.status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO
        requisicao_despesa.save()
        if requisicao_despesa.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA:
            requisicao_despesa.gerar_documento_requisicao(self.request)
        else:
            requisicao_despesa.gerar_documento_requisicao_empenho(self.request)
        tramite_novo = Tramite()
        tramite_novo.processo = requisicao_despesa.processo
        tramite_novo.tramitar_processo(
            remetente_setor=requisicao_despesa.processo.setor_atual,
            remetente_vinculo=self.request.user.get_vinculo(),
            destinatario_setor=get_setor_unidade_administrativa(user=self.request.user),
            papel=self.request.user.get_relacionamento().papeis_ativos.first(),
            despacho_corpo=None,
            destinatario_vinculo=None,
            assinar_tramite=False,
        )
        return requisicao_despesa


class DocumentoROForm(forms.ModelFormPlus):
    documento_siafi = forms.CharFieldPlus(label='Documento SIAFI', required=True, widget=forms.TextInput(), max_length=6)

    class Meta:
        model = NotaEmpenho
        fields = ('unidade', 'unidade_orcamentaria', 'ano', 'documento_siafi')

    def __init__(self, *args, **kwargs):
        nota_empenho = kwargs.pop('nota_empenho')
        super().__init__(*args, **kwargs)
        requisicao_despesa = nota_empenho.requisicao
        self.instance = nota_empenho
        self.instance.requisicao = requisicao_despesa
        unidade_gestora = requisicao_despesa.atividade.unidade_gestora
        self.fields['unidade'].initial = unidade_gestora
        self.fields['unidade_orcamentaria'].initial = ClassificacaoInstitucional.objects.get(codigo='26435')
        self.fields['ano'].initial = requisicao_despesa.plano_atividade.ano_base
        self.fields['unidade'].widget.readonly = True
        self.fields['ano'].widget.attrs['readonly'] = True
        self.fields['unidade_orcamentaria'].widget.readonly = True

    def clean(self):
        super().clean()
        documento_siafi = self.cleaned_data.get('documento_siafi')
        unidade = self.cleaned_data.get('unidade')
        unidade_orcamentaria = self.cleaned_data.get('unidade_orcamentaria')
        ano = self.cleaned_data.get('ano')
        if documento_siafi:
            if not documento_siafi.isdigit():
                raise forms.ValidationError('O código do documento SIAFI deve conter apenas dígitos numéricos.')

            documento_siafi_str = str(documento_siafi)
            if len(documento_siafi_str) != 6:
                raise forms.ValidationError('O código do documento SIAFI deve conter 6 dígitos')

            numero_ro = f'{unidade.codigo_ug}{unidade_orcamentaria.codigo}{ano}RO{documento_siafi}'

            if NotaEmpenho.objects.filter(numero_ro=numero_ro).exclude(status=NotaEmpenho.STATUS_CANCELADA).exclude(pk=self.instance.pk).exists():
                raise ValidationError(f'O empenho {numero_ro} já está associado a uma requisição de despesa.')
        return self.cleaned_data

    @transaction.atomic()
    def save(self, commit=True, *args, **kwargs):
        self.instance.codigo_ug = self.instance.unidade.codigo_ug
        unidade_orcamentaria = self.instance.unidade_orcamentaria
        ano = self.cleaned_data['ano']
        documento_siafi = self.cleaned_data['documento_siafi']

        numero_ro = f'{self.instance.codigo_ug}{unidade_orcamentaria.codigo}{ano}RO{documento_siafi}'
        self.instance.documento_siafi = documento_siafi
        self.instance.numero_ro = numero_ro
        if commit:
            self.instance.save()
        return self.instance


class ReforcoEmpenhoForm(DocumentoROForm):
    """Vincula um novo reforço à requisição a partir da linha do empenho original.

    A natureza de despesa e o número do empenho são herdados da linha de origem; ao executor
    orçamentário cabe informar apenas o valor do reforço e o RO registrado no SIAFI.
    """

    valor = forms.DecimalFieldPlus(label='Valor do reforço R$', required=True)

    class Meta:
        model = NotaEmpenho
        fields = ('unidade', 'unidade_orcamentaria', 'ano', 'documento_siafi', 'valor')

    def __init__(self, *args, **kwargs):
        nota_empenho = kwargs['nota_empenho']
        super().__init__(*args, **kwargs)
        self.instance = NotaEmpenho(
            requisicao=nota_empenho.requisicao,
            naturezadespesa=nota_empenho.naturezadespesa,
            numero_empenho=nota_empenho.numero_empenho,
        )

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        requisicao = self.instance.requisicao
        saldo = requisicao.valor_inicial - requisicao.total_naturezas_despesa()
        if valor <= 0:
            raise forms.ValidationError('O valor do reforço deve ser maior que zero.')
        if valor > saldo:
            raise forms.ValidationError(f'Valor maior que o disponível: R$ {format_money(saldo)}')
        return valor

    @transaction.atomic()
    def save(self, commit=True, *args, **kwargs):
        instancia = super().save(commit, *args, **kwargs)
        if commit:
            self.instance.requisicao.atualizar_valor_total()
        return instancia


class RequisicaoAnulacaoEmpenhoForm(FormWizardPlus):
    empenho = forms.ModelChoiceField(label='Empenho a ser anulado', queryset=NotaEmpenho.objects, required=True, widget=AutocompleteWidget())
    projeto = forms.ModelChoiceField(
        label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects, required=True, widget=AutocompleteWidget(readonly='readonly')
    )
    origem_recurso = forms.ModelChoiceField(
        label='Origem de recurso', queryset=OrigemRecursoProjeto.objects, required=True, widget=AutocompleteWidget(readonly='readonly')
    )
    plano_interno = forms.ModelChoiceField(
        label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects, required=True, widget=AutocompleteWidget(readonly='readonly')
    )
    processo = forms.ModelChoiceField(label='Processo', queryset=Processo.objects, required=True, widget=AutocompleteWidget())
    atividade = forms.ModelChoiceField(
        label='Atividade', required=True, queryset=AtividadeEtapa.objects, widget=AutocompleteWidget(readonly='readonly')
    )
    finalidade = forms.CharField(label='Finalidade', widget=forms.Textarea(), required=True)
    valor_empenho = forms.DecimalFieldPlus(label='Valor a ser anulado R$', required=True)
    ua_vinculada = ua_vinculada_field()

    autorizacao_ordenador_declarada_no_processo = forms.BooleanField(
        required=False,
        label='Declaro que o processo vinculado já possui a autorização do ordenador de despesa para esta despesa.',
        help_text=(
            'Marque esta opção somente quando o processo administrativo vinculado já contiver despacho ou documento com a autorização expressa do ordenador de despesa. Ao marcar, a RD não passará pela etapa de autorização do ordenador e será tramitada diretamente para o setor financeiro da UA.'
        ),
    )
    steps = (
        [('Empenho', {'fields': ('empenho',)})],
        [
            (
                'Filtro',
                {
                    'fields': (
                        'projeto',
                        'origem_recurso',
                        'plano_interno',
                        'atividade',
                        'ua_vinculada',
                        'processo',
                        'finalidade',
                        'valor_empenho',
                        'autorizacao_ordenador_declarada_no_processo',
                    )
                },
            )
        ],
    )

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        remover_ua_vinculada_sem_ug_secundaria(self)
        self.fields['projeto'] = ReadOnlyField(label='Macroprocesso')
        setor_ug = get_setor_unidade_gestora(user=self.request.user)
        unidade_gestora = None
        if setor_ug:
            unidade_gestora = UnidadeGestora.objects.filter(setor_equivalente=setor_ug).first()

        qs_empenho = NotaEmpenho.objects.filter(
            numero_empenho__isnull=False,
            requisicao__status=RequisicaoDespesa.STATUS_CONCLUIDA,
            requisicao__tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
            requisicao__plano_atividade__ano_base=plano_atividade.ano_base,
        ).exclude(status=NotaEmpenho.STATUS_CANCELADA)

        if not unidade_gestora:
            self.fields['empenho'].queryset = qs_empenho.none()
            return
        if in_group(self.request.user, 'Gestor Orçamentário Sistêmico'):
            qs_empenho = qs_empenho.filter(requisicao__unidade_gestora__codigo_ug=unidade_gestora.codigo_ug)

        elif in_group(self.request.user, 'Gestor de UA, Coordenador de UA'):
            qs_empenho = qs_empenho.filter(requisicao__unidade_gestora=unidade_gestora)

        self.fields['empenho'].queryset = qs_empenho

    def next_step(self):
        empenho = self.get_entered_data('empenho')
        if not empenho:
            return super().next_step()

        req = getattr(empenho, 'requisicao', None)
        if not req:
            return super().next_step()

        iniciais = {
            'projeto': getattr(req, 'macroprocesso_id', None),
            'origem_recurso': getattr(req, 'origem_recurso_id', None),
            'plano_interno': getattr(req, 'plano_interno_id', None),
            'atividade': getattr(req, 'atividade_id', None),
        }

        for nome, valor in iniciais.items():
            if nome in self.fields and valor is not None:
                self.fields[nome].initial = valor

        if 'processo' in self.fields:
            setores_que_o_usuario_pode_criar_processo = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=True)
            self.fields['processo'].queryset = (
                ProcessoEletronico.ativos.by_user(self.request.user)
                .filter(setor_atual__in=list(setores_que_o_usuario_pode_criar_processo))
                .exclude(
                    id__in=RequisicaoDespesa.objects.filter(
                        status__in=[
                            RequisicaoDespesa.STATUS_CADASTRADA,
                            RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO,
                            RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
                            RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA,
                            RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO,
                            RequisicaoDespesa.STATUS_INCONSISTENTE,
                            RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
                        ],
                        processo__isnull=False,
                    ).values_list('processo__id', flat=True)
                )
            )

        return super().next_step()

    def clean(self):
        cleaned_data = super().clean()
        empenho = cleaned_data.get('empenho')
        # Só no último passo, e quando o processo não vai direto para o setor financeiro
        if empenho and 'processo' in self.fields and not cleaned_data.get('autorizacao_ordenador_declarada_no_processo'):
            requisicao = RequisicaoDespesa(
                unidade_gestora=empenho.requisicao.unidade_gestora,
                ua_vinculada=cleaned_data.get('ua_vinculada') or RequisicaoDespesa.UA_PRINCIPAL,
            )
            validar_setor_destino_cdo(requisicao)
        return cleaned_data

    def clean_valor_empenho(self):
        nota_empenho = self.get_entered_data('empenho')
        if not nota_empenho:
            raise forms.ValidationError('Selecione o empenho.')
        if not nota_empenho.numero_empenho:
            raise forms.ValidationError('Empenho selecionado está sem número.')
        empenho = nota_empenho.numero_empenho
        valor_empenho = self.get_entered_data('valor_empenho')
        total_empenho = NotaEmpenho.get_total_empenhado(empenho)
        total_reforco = NotaEmpenho.get_total_reforco_empenho(empenho)
        total_anulado = NotaEmpenho.get_total_anulado(empenho)
        doc = DocumentoEmpenho.objects.get(numero=empenho)
        total_liquidado = doc.get_valor_liquidado()
        saldo_disponivel = total_empenho + total_reforco + total_anulado - total_liquidado

        if saldo_disponivel == 0:
            mensagem = 'Saldo Indisponível. Saldo 0,00'
            self.fields['valor_empenho'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        if valor_empenho > saldo_disponivel:
            valor_empenho = format_money(valor_empenho)
            saldo_disponivel = format_money(saldo_disponivel)
            mensagem = f'o Valor R$ {valor_empenho} é maior que o saldo disponível R$ {saldo_disponivel}.'
            self.fields['valor_empenho'].widget.error_message = mensagem
            raise forms.ValidationError(mensagem)
        return self.cleaned_data['valor_empenho']

    @transaction.atomic
    def processar(self):
        empenho = self.cleaned_data['empenho']
        macroprocesso = self.cleaned_data['projeto']
        origem_recurso = self.cleaned_data['origem_recurso']
        plano_interno = self.cleaned_data['plano_interno']
        processo = self.cleaned_data['processo']
        atividade = self.cleaned_data['atividade']
        autorizacao_ordenador_declarada_no_processo = self.cleaned_data['autorizacao_ordenador_declarada_no_processo']
        tipo_requisicao = RequisicaoDespesa.TIPO_ANULACAO_EMPENHO
        if autorizacao_ordenador_declarada_no_processo:
            status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
        else:
            status = RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO
        plano_atividade = macroprocesso.plano_atividade
        unidade_gestora = self.cleaned_data['empenho'].requisicao.unidade_gestora
        ano_planoatividade = plano_atividade.ano_base
        valor_empenho = -abs(self.cleaned_data['valor_empenho'])
        finalidade = self.cleaned_data['finalidade']
        requisicao_despesa = RequisicaoDespesa.objects.create(
            plano_atividade=plano_atividade,
            status=status,
            numero=RequisicaoDespesa.get_proximo_numero_requisicao(ano_planoatividade),
            macroprocesso=macroprocesso,
            origem_recurso=origem_recurso,
            plano_interno=plano_interno,
            unidade_gestora=unidade_gestora,
            ua_vinculada=self.cleaned_data.get('ua_vinculada') or RequisicaoDespesa.UA_PRINCIPAL,
            processo=processo,
            atividade=atividade,
            tipo_requisicao=tipo_requisicao,
            valor=valor_empenho,
            valor_inicial=valor_empenho,
            finalidade=finalidade,
            autorizacao_ordenador_declarada_no_processo=autorizacao_ordenador_declarada_no_processo,
        )
        if not autorizacao_ordenador_declarada_no_processo:
            requisicao_despesa.status = requisicao_despesa.get_status_apos_cdo()
            requisicao_despesa.save()
        RequisicaoDespesaHistorico.objects.create(
            despesa=requisicao_despesa, status=requisicao_despesa.status, alterado_em=datetime.datetime.now(), alterado_por=self.request.user
        )
        NotaEmpenho.objects.create(
            requisicao=requisicao_despesa, naturezadespesa=empenho.naturezadespesa, numero_empenho=empenho, valor=valor_empenho
        )
        requisicao_despesa.gerar_documento_requisicao_empenho(self.request)
        tramite_novo = Tramite()
        tramite_novo.processo = requisicao_despesa.processo
        if requisicao_despesa.autorizacao_ordenador_declarada_no_processo:
            destinatario_setor = requisicao_despesa.unidade_gestora.setor_financeiro
            tramite_novo.tramitar_processo(
                remetente_setor=processo.setor_atual,
                remetente_vinculo=self.request.user.get_vinculo(),
                destinatario_setor=destinatario_setor,
                papel=self.request.user.get_relacionamento().papeis_ativos.first(),
                despacho_corpo='O requisitante declarou que a autorização de anulação desta despesa foi realizada pelo ordenador diretamente no processo vinculado. Segue para o setor financeiro para registro do documento do SIAFI.',
                destinatario_vinculo=None,
                assinar_tramite=True,
            )
        else:
            tramite_novo.tramitar_processo(
                remetente_setor=requisicao_despesa.processo.setor_atual,
                remetente_vinculo=self.request.user.get_vinculo(),
                destinatario_setor=requisicao_despesa.get_setor_destino_apos_cdo(),
                papel=self.request.user.get_relacionamento().papeis_ativos.first(),
                despacho_corpo=None,
                destinatario_vinculo=None,
                assinar_tramite=False,
            )
        return requisicao_despesa


class AtividadeOrcamentariaForm(forms.ModelFormPlus):
    projeto = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoPlanoAtividade.objects.all(), required=True)
    processo = forms.ModelChoiceField(label='Componente funcional', queryset=EtapaProjetoPlanoAtividade.objects.all(), required=True)
    origem_recurso_etapa = forms.ModelChoiceFieldPlus2(
        label='Origem de recurso',
        help_text='Origem de recurso do componente funcional',
        queryset=OrigemRecursoProjetoEtapa.objects.all(),
        required=True,
    )
    plano_interno = forms.ModelChoiceField(label='Plano interno', queryset=PlanoInternoPlanoAtividade.objects.all(), required=True)
    naturezadespesa = forms.ModelChoiceFieldPlus2(
        label='Natureza de despesa',
        queryset=NaturezaDespesaPlanoAtividade.objects.all(),
        required=True,
        widget=AutocompleteWidget(search_fields=NaturezaDespesaPlanoAtividade.SEARCH_FIELDS),
    )
    unidade_gestora = forms.ModelChoiceFieldPlus2(
        label='Unidade gestora',
        queryset=UnidadeGestora.objects.all(),
        required=True,
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS, readonly=True),
    )
    valor = forms.DecimalFieldPlus(label='Valor Proposto R$', required=False)

    class Media:
        js = ['/static/plan_estrategico/js/AtividadeOrcamentaria.js']

    def __init__(self, *args, **kwargs):
        plano_atividade = kwargs.pop('plano_atividade')
        super().__init__(*args, **kwargs)
        self.fields['projeto'].queryset = ProjetoPlanoAtividade.objects.filter(plano_atividade=plano_atividade).order_by('projeto__codigo')
        self.fields['processo'].queryset = EtapaProjetoPlanoAtividade.objects.filter(
            projeto_plano_atividade__plano_atividade=plano_atividade
        ).order_by('projeto_plano_atividade__projeto__codigo')

        self.fields['origem_recurso_etapa'].queryset = OrigemRecursoProjetoEtapa.objects.filter(
            etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade=plano_atividade
        )
        self.fields['naturezadespesa'].queryset = NaturezaDespesaPlanoAtividade.objects.filter(plano_atividade=plano_atividade)
        self.fields['plano_interno'].queryset = PlanoInternoPlanoAtividade.objects.filter(plano_atividade=plano_atividade)

        self.fields['unidade_gestora'].initial = UnidadeGestora.objects.filter(
            setor_equivalente=get_setor_unidade_gestora(user=self.request.user)
        ).first()
        self.fields['valor'].initial = Decimal(0)
        self.fields['valor'].widget.attrs['disabled'] = 'disabled'

    class Meta:
        model = AtividadeEtapa
        fields = ('projeto', 'processo', 'origem_recurso_etapa', 'plano_interno', 'nome', 'descricao', 'naturezadespesa', 'valor', 'unidade_gestora')

    @transaction.atomic
    def save(self, commit=True):
        self.instance.etapa_projeto_plano_atividade = self.cleaned_data['processo']
        self.instance.atividade_complementar = True
        instance = super().save(commit=commit)
        return instance

    def clean(self):
        cleaned_data = super().clean()
        origem_recurso_etapa = cleaned_data.get('origem_recurso_etapa')
        natureza_despesa_atividade = cleaned_data.get('naturezadespesa')
        plano_interno = cleaned_data.get('plano_interno')
        if origem_recurso_etapa and natureza_despesa_atividade and plano_interno:
            origem_gnd_codigo = origem_recurso_etapa.origem_recurso_projeto.origem_recurso.gnd.codigo
            natureza_gnd_codigo = natureza_despesa_atividade.natureza_despesa.grupo_natureza_despesa.codigo
            if origem_gnd_codigo != natureza_gnd_codigo:
                self.add_error('naturezadespesa', 'A natureza de despesa e a origem de recurso devem ter o mesmo GND.')
            if origem_recurso_etapa and plano_interno:
                if origem_recurso_etapa.origem_recurso_projeto.__str__() != plano_interno.plano_interno.codigo_origemrecurso:
                    self.add_error('plano_interno', 'A origem de recurso do plano interno deve ser igual a origem de recurso selecionada.')
        return self.cleaned_data


class NaturezaDespesaRequisicaoForm(forms.ModelFormPlus):
    naturezadespesa = forms.ModelChoiceFieldPlus2(
        label='Natureza de despesa',
        queryset=NaturezaDespesaPlanoAtividade.objects.all(),
        required=True,
        widget=AutocompleteWidget(search_fields=NaturezaDespesaPlanoAtividade.SEARCH_FIELDS),
    )
    valor = forms.DecimalFieldPlus(label='Valor R$', required=True)

    def __init__(self, *args, **kwargs):
        self.requisicao = kwargs.pop('requisicao', None)
        super().__init__(*args, **kwargs)
        self.fields['naturezadespesa'].queryset = NaturezaDespesaPlanoAtividade.objects.filter(plano_atividade=self.requisicao.plano_atividade)
        if self.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_REFORCO_EMPENHO:
            primeira_linha = self.requisicao.empenhos.order_by('id').first()

            if primeira_linha:
                self.fields['naturezadespesa'].queryset = NaturezaDespesaPlanoAtividade.objects.filter(id=primeira_linha.naturezadespesa_id)
                self.fields['naturezadespesa'].initial = primeira_linha.naturezadespesa
                self.fields['naturezadespesa'].widget.attrs['readonly'] = 'readonly'

    class Meta:
        model = NotaEmpenho
        fields = ('naturezadespesa', 'valor')

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        valor_requisicao = self.requisicao.valor_inicial
        if self.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA:
            valor_requisicao = self.requisicao.valor_provisorio
        saldo = valor_requisicao - self.requisicao.total_naturezas_despesa()
        if valor > saldo:
            raise forms.ValidationError(f'Valor maior que o disponível: R$ {format_money(saldo)}')
        return valor

    def clean_naturezadespesa(self):
        naturezaDespesa_requisicao = self.cleaned_data.get('naturezadespesa')
        origem_recurso_requisicao = self.requisicao.origem_recurso
        origem_gnd = origem_recurso_requisicao.origem_recurso.gnd.codigo
        natureza_gnd = naturezaDespesa_requisicao.natureza_despesa.grupo_natureza_despesa.codigo
        if origem_gnd != natureza_gnd:
            raise forms.ValidationError('A natureza de despesa e a origem de recurso devem ter o mesmo GND.')
        return naturezaDespesa_requisicao

    @transaction.atomic
    def save(self, commit=True):
        self.instance.requisicao = self.requisicao
        self.instance.valor = self.cleaned_data['valor']
        if self.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_REFORCO_EMPENHO:
            primeira_linha = self.requisicao.empenhos.order_by('id').first()

            if primeira_linha:
                self.instance.numero_empenho = primeira_linha.numero_empenho
                self.instance.naturezadespesa = primeira_linha.naturezadespesa
            else:
                self.instance.naturezadespesa = self.cleaned_data['naturezadespesa']
        instance = super().save(commit=commit)
        self.requisicao.atualizar_valor_total()
        return instance


class NaturezaDespesaRequisicaoEditarForm(forms.ModelForm):
    naturezadespesa = forms.ModelChoiceField(
        label='Natureza de Despesa',
        queryset=NaturezaDespesaPlanoAtividade.objects.none(),
        required=True,
        widget=AutocompleteWidget(search_fields=NaturezaDespesaPlanoAtividade.SEARCH_FIELDS),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            plano_atividade = getattr(self.instance.requisicao, 'plano_atividade', None)
            if plano_atividade:
                self.fields['naturezadespesa'].queryset = NaturezaDespesaPlanoAtividade.objects.filter(plano_atividade=plano_atividade)
                self.fields['naturezadespesa'].initial = self.instance.naturezadespesa

    class Meta:
        model = NotaEmpenho
        fields = ('naturezadespesa',)

    def clean_naturezadespesa(self):
        nd = self.cleaned_data.get('naturezadespesa')
        if self.instance.naturezadespesa.natureza_despesa.grupo_natureza_despesa.codigo != nd.natureza_despesa.grupo_natureza_despesa.codigo:
            raise forms.ValidationError('O GND da natureza escolhida deve ser igual ao da natureza cadastrada na requisição.')
        return self.cleaned_data.get('naturezadespesa')

    def save(self, commit=True):
        self.instance.requisicao = self.instance.requisicao
        self.instance.naturezadespesa = self.cleaned_data['naturezadespesa']
        if commit:
            self.instance.save(update_fields=['requisicao', 'naturezadespesa'])
        self.instance.requisicao.atualizar_valor_total()
        return self.instance


class EditarValorNaturezaDespesaForm(forms.ModelForm):
    valor = forms.DecimalFieldPlus(label='Valor R$', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            plano_atividade = getattr(self.instance.requisicao, 'plano_atividade', None)
            if plano_atividade:
                self.fields['valor'].initial = self.instance.valor

    class Meta:
        model = NotaEmpenho
        fields = ('valor',)

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        valor_requisicao = self.instance.requisicao.valor_inicial
        if self.instance.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA:
            valor_requisicao = self.instance.requisicao.valor_provisorio
        total_atual = self.instance.requisicao.total_naturezas_despesa()
        total_sem_esta_natureza = total_atual - (self.instance.valor or 0)
        if valor_requisicao is None:
            raise forms.ValidationError('Valor da requisição não definido.')

        saldo = valor_requisicao - total_sem_esta_natureza
        if self.instance.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_ANULACAO_EMPENHO:
            if abs(valor) > abs(saldo):
                raise forms.ValidationError(f'Valor de anulação maior que o disponível: R$ {format_money(saldo)}')
            return valor
        if valor > saldo:
            raise forms.ValidationError(f'Valor maior que o disponível: R$ {format_money(saldo)}')

        return valor

    @transaction.atomic
    def save(self, commit=True):
        valor = self.cleaned_data['valor']
        if self.instance.requisicao.tipo_requisicao == RequisicaoDespesa.TIPO_ANULACAO_EMPENHO:
            self.instance.valor = -abs(valor)
        else:
            self.instance.valor = valor
        instance = super().save(commit=commit)
        return instance


class EmpenhosSemRequisicaoFiltroForm(forms.FormPlus):
    METHOD = 'GET'
    numero_empenho = forms.CharField(label='Número do empenho', required=False)
    unidade_gestora = forms.ModelChoiceField(label='UG emitente', queryset=UnidadeGestoraSiafi.objects.none(), required=False)
    ugr = forms.ModelChoiceField(label='UGR', queryset=UnidadeGestoraSiafi.objects.none(), required=False)
    macroprocesso = forms.ModelChoiceField(label='Macroprocesso', queryset=ProjetoEstrategico.objects.none(), required=False)

    def __init__(self, *args, codigos_ug: list[str], plano_atividade: PlanoAtividade, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unidade_gestora'].queryset = UnidadeGestoraSiafi.objects.filter(codigo__in=codigos_ug).order_by('codigo')
        # UGRs dos empenhos no escopo da listagem, inclusive a "sem informação" que o SIAFI usa quando não há UGR.
        ugrs = NotaEmpenho.get_documentos_empenho_do_plano(plano_atividade, codigos_ug).values('responsavel_ug')
        self.fields['ugr'].queryset = UnidadeGestoraSiafi.objects.filter(pk__in=ugrs).order_by('codigo')
        self.fields['macroprocesso'].queryset = (
            ProjetoEstrategico.objects.filter(planointerno__planointernoplanoatividade__plano_atividade=plano_atividade).distinct().order_by('codigo')
        )
