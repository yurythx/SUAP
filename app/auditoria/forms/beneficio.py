from tinymce.widgets import TinyMCE
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.db.models import CharField, F, QuerySet, Value
from django.db.models.functions import Concat

from comum.models import Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import get_datetime_now
from rh.models import Setor

from ..forms.documento import DocumentoDigitalizadoForm
from ..models import (
    AlcanceEstrategico,
    Beneficio,
    BeneficioDocumento,
    BeneficioStatus,
    ClasseBeneficio,
    DetalhamentoFinanceiro,
    DetalhamentoQualitativo,
    Monitoramento,
    NaturezaFinanceira,
    ParcelaFinanceira,
    TipoBeneficio,
    UnidadeAfetada,
)
from ..papeis import eh_auditor_chefe, get_auditores_ativos


class BeneficioForm(forms.ModelFormPlus):
    descricao = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), label='Descrição do benefício', required=True
    )
    tipo = (forms.ChoiceField(label='Tipo do benefício', choices=TipoBeneficio.choices, required=True),)
    classe = forms.ModelChoiceField(
        ClasseBeneficio.objects,
        label='Classe',
        required=True,
        widget=AutocompleteWidget(
            search_fields=ClasseBeneficio.SEARCH_FIELDS,
            form_filters=[
                ('tipo', 'tipo'),
            ],
        ),
    )
    monitoramento = forms.ModelChoiceField(
        queryset=Monitoramento.objects.none(),
        required=False,
        label='Recomendação Associada',
        widget=AutocompleteWidget(search_fields=['identificador_annotated'], multiple=False),
    )
    origem_beneficio = forms.ChoiceField(choices=Beneficio.OrigemBeneficio.choices, required=True)
    nexo_causal = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), required=True, label='Nexo Causal'
    )
    # Campos específicos para Detalhamento Financeiro
    natureza = forms.ChoiceField(choices=NaturezaFinanceira.choices, required=False)
    valor_beneficio = forms.DecimalField(required=False, label='Valor Total do Benefício', max_digits=15, decimal_places=2)
    responsavel_calculo = forms.ModelChoiceFieldPlus(label='Responsável pelo cálculo', queryset=Vinculo.objects.none(), required=False)

    # Campos específicos para Detalhamento Qualitativo
    unidade_afetada = forms.ModelChoiceFieldPlus(queryset=UnidadeAfetada.objects, required=False, label='Unidade Afetada')
    alcance_estrategico = forms.ModelChoiceFieldPlus(queryset=AlcanceEstrategico.objects, required=False, label='Alcance Estratégico')

    monitor = forms.ModelChoiceFieldPlus(label='Monitor', queryset=Vinculo.objects.none(), required=True)
    metodologia_calculo = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), required=False, label='Metodologia Cálculo'
    )

    fieldsets = (
        (
            'Informações Gerais',
            {
                'fields': ('ano', 'tipo', 'descricao', 'classe', 'monitor'),
            },
        ),
        (
            'Serviço de Auditoria',
            {
                'fields': ('servico_auditoria', 'servico_auditoria_outros'),
            },
        ),
        ('Origem do Benefício', {'fields': ('origem_beneficio', 'monitoramento'), 'description': 'Selecione a origem do benefício.'}),
        (
            'Detalhamento do Benefício',
            {
                'fields': (
                    'nexo_causal',
                    'metodologia_calculo',
                    ('responsavel_calculo', 'valor_beneficio', 'natureza'),  # Financeiro
                    ('unidade_afetada', 'alcance_estrategico'),  # Qualitativo
                ),
                'description': 'Preencha os campos conforme o tipo de benefício selecionado.',
            },
        ),
    )

    class Meta:
        model = Beneficio
        fields = [
            'ano',
            'tipo',
            'descricao',
            'classe',
            'monitor',
            'servico_auditoria',
            'servico_auditoria_outros',
            'origem_beneficio',
            'nexo_causal',
            'responsavel_calculo',
            'valor_beneficio',
            'natureza',
            'unidade_afetada',
            'alcance_estrategico',
            'metodologia_calculo',
        ]

    class Media:
        js = ('auditoria/js/beneficio_form.js',)

    def __init__(self, *args, content_object=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsavel_calculo'].queryset = get_auditores_ativos()
        self.fields['monitor'].queryset = get_auditores_ativos()
        self.fields['monitoramento'].queryset = Monitoramento.objects.annotate(
            identificador_annotated=Concat(
                F('recomendacao__numero'),
                Value('/'),
                F('recomendacao__ano'),
                Value(' - '),
                F('unidade__sigla'),
                output_field=CharField(),  # Explicitly define the output type as CharField
            )
        ).all()
        if self.instance.pk:
            self.fields['tipo'].widget.attrs['readonly'] = True
            self.fields['tipo'].choices = [choice for choice in TipoBeneficio.choices if choice[0] == self.instance.tipo]
            self.fields['tipo'].initial = self.instance.tipo
            self.fields['monitor'].initial = self.instance.monitor
            if self.instance.eh_financeiro:
                self.fields['valor_beneficio'].initial = self.instance.detalhamento_financeiro.valor_beneficio
                self.fields['responsavel_calculo'].initial = self.instance.detalhamento_financeiro.responsavel_calculo
                self.fields['metodologia_calculo'].initial = self.instance.detalhamento_financeiro.metodologia_calculo
            else:
                self.fields['unidade_afetada'].initial = self.instance.detalhamento_qualitativo.unidade_afetada
                self.fields['alcance_estrategico'].initial = self.instance.detalhamento_qualitativo.alcance_estrategico
            if self.instance.origem_beneficio == Beneficio.OrigemBeneficio.RECOMENDACAO:
                self.fields['monitoramento'].initial = self.instance.content_object
        elif content_object:
            self.fields['origem_beneficio'].initial = Beneficio.OrigemBeneficio.RECOMENDACAO
            self.fields['origem_beneficio'].widget.attrs['readonly'] = True
            self.fields['monitoramento'].initial = content_object
            self.fields['monitoramento'].widget.attrs['readonly'] = True
        #

    def clean_nexo_causal(self):
        nexo_causal = self.cleaned_data['nexo_causal']
        if not nexo_causal.strip():
            raise forms.ValidationError('O nexo causal não pode estar vazio.')
        return nexo_causal

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        tipo_beneficio = cleaned_data.get('tipo')
        monitoramento = cleaned_data.get('monitoramento')
        origem_beneficio = int(cleaned_data.get('origem_beneficio'))
        servico_auditoria = cleaned_data.get('servico_auditoria')
        origem_outros = cleaned_data.get('servico_auditoria_outros')
        origem_outros = cleaned_data.get('servico_auditoria_outros')

        if tipo_beneficio == TipoBeneficio.FINANCEIRO:
            if not cleaned_data.get('valor_beneficio'):
                self.add_error('valor_beneficio', 'Informe o valor do benefício.')
            if not cleaned_data.get('responsavel_calculo'):
                self.add_error('responsavel_calculo', 'Informe o auditor responsável pelo cálculo.')
            if not cleaned_data.get('natureza'):
                self.add_error('natureza', 'Informe a natureza do benefício financeiro.')
            if not cleaned_data.get('metodologia_calculo'):
                self.add_error('metodologia_calculo', 'Informe a metodologia de cálculo.')

        elif tipo_beneficio == TipoBeneficio.QUALITATIVO:
            if not cleaned_data.get('unidade_afetada'):
                self.add_error('unidade_afetada', 'Informe a unidade afetada.')
            if not cleaned_data.get('alcance_estrategico'):
                self.add_error('alcance_estrategico', 'Informe o alcance estratégico.')
        else:
            self.add_error('tipo', 'Informe o tipo do benefício.')
        # Validação: content_type e object_id obrigatórios para "Recomendação"
        if origem_beneficio == Beneficio.OrigemBeneficio.RECOMENDACAO:
            if monitoramento:
                # Preenche os campos de content_type e object_id
                cleaned_data['content_type'] = ContentType.objects.get_for_model(monitoramento)
                cleaned_data['object_id'] = monitoramento.id
            else:
                self.add_error('monitoramento', "É necessário informar um monitoramento'.")
        # Validação: servico_auditoria_outros obrigatório se a origem for "Outros"
        if servico_auditoria.nome == 'Outros' and not origem_outros:
            self.add_error('Outros', "Informe a descrição de 'Outros' para a origem do trabalho.")
        try:
            # Preenche a instância com os dados do form, pois ela ainda não tem os atributos atualizados
            for field in ['content_type', 'object_id', 'classe']:
                setattr(self.instance, field, cleaned_data.get(field))
            self.instance.clean()
        except ModelValidationError as e:
            self.add_error('classe', e.message)
        return cleaned_data

    def _save_detalhamento_finaceiro(self, beneficio):
        DetalhamentoFinanceiro.objects.update_or_create(
            beneficio=beneficio,
            defaults={
                'valor_beneficio': self.cleaned_data['valor_beneficio'],
                'responsavel_calculo': self.cleaned_data['responsavel_calculo'],
                'natureza': self.cleaned_data['natureza'],
                'metodologia_calculo': self.cleaned_data['metodologia_calculo'],
            },
        )

    def _save_detalhamento_qualitativo(self, beneficio):
        DetalhamentoQualitativo.objects.update_or_create(
            beneficio=beneficio,
            defaults={'unidade_afetada': self.cleaned_data['unidade_afetada'], 'alcance_estrategico': self.cleaned_data['alcance_estrategico']},
        )

    @transaction.atomic()
    def do_save(self, beneficio: Beneficio):
        beneficio.clean()
        beneficio.save()
        if beneficio.eh_financeiro:
            self._save_detalhamento_finaceiro(beneficio)
        elif beneficio.eh_qualitativo:
            self._save_detalhamento_qualitativo(beneficio)
        else:
            raise forms.ValidationError('Tipo de benefício invalido!')
        return beneficio

    def save(self, commit=True):
        beneficio: Beneficio = super().save(commit=False)
        if commit:
            # Preenche os campos genéricos com os dados do cleaned_data
            beneficio.content_type = self.cleaned_data.get('content_type')
            beneficio.object_id = self.cleaned_data.get('object_id')
            return self.do_save(beneficio)
        return beneficio


class DetalhamentoBeneficioForm(forms.ModelFormPlus):
    """
    Classe base para formulários de detalhamento de benefício.
    Recebe o benefício como argumento na inicialização e associa ao objeto salvo.
    """

    def __init__(self, *args, **kwargs):
        self.beneficio = kwargs.pop('beneficio', None)  # Recebe o benefício
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.beneficio = self.beneficio  # Associa o benefício
        if not instance.pk:
            instance.criado_por = self.request.user
        else:
            instance.atualizado_por = self.request.user
        if commit:
            instance.save()
        return instance


class DetalhamentoFinanceiroForm(DetalhamentoBeneficioForm):
    class Meta:
        model = DetalhamentoFinanceiro
        fields = ['valor_beneficio', 'responsavel_calculo']


class DetalhamentoQualitativoForm(DetalhamentoBeneficioForm):
    class Meta:
        model = DetalhamentoQualitativo
        fields = ['unidade_afetada', 'alcance_estrategico']


class ParcelaFinanceiraForm(forms.ModelFormPlus):
    data_prevista = forms.DateFieldPlus(label='Data Prevista para Parcela', required=True)
    valor_esperado = forms.DecimalField(label='Valor Esperado da Parcela', required=True, initial=0)
    data_pagamento = forms.DateFieldPlus(label='Data da Efetivação do Benefício', required=False)
    valor_efetivo = forms.DecimalField(label='Valor Efetivo', required=False, initial=0)

    class Meta:
        model = ParcelaFinanceira
        fields = ['data_prevista', 'valor_esperado', 'data_pagamento', 'valor_efetivo', 'observacao']

    def __init__(self, *args, **kwargs):
        detalhamento = kwargs.pop('detalhamento', None)
        super().__init__(*args, **kwargs)
        self.detalhamento = detalhamento or getattr(self.instance, 'detalhamento', None)
        self.beneficio: Beneficio = getattr(self.detalhamento, 'beneficio', None)
        self.eh_chefe_auditoria = eh_auditor_chefe(self.request.user)
        # Se está editando e o benefício está em monitoramento, tornamos campos readonly
        if self.instance.pk:
            self.fields['data_prevista'].widget.attrs['readonly'] = True
            self.fields['valor_esperado'].widget.attrs['readonly'] = True

    def clean_data_prevista(self):
        data_prevista = self.cleaned_data.get('data_prevista')
        hoje = get_datetime_now().date()
        # validação geral
        if not self.instance.pk and not self.eh_chefe_auditoria and data_prevista < hoje:
            raise forms.ValidationError('A data prevista não pode ser anterior à data atual.')
        # na edição: não permito alterar
        if self.instance.pk and self.beneficio.em_monitoramento:
            if data_prevista != self.instance.data_prevista:
                raise forms.ValidationError('A data prevista não pode ser alterada.')
        return data_prevista

    def clean_valor_esperado(self):
        valor = self.cleaned_data.get('valor_esperado')
        if valor is not None and valor <= 0:
            raise forms.ValidationError('O valor esperado deve ser positivo.')
        if self.instance.pk and self.beneficio.em_monitoramento:
            if valor != self.instance.valor_esperado:
                raise forms.ValidationError('O valor esperado não pode ser alterado.')
        return valor

    def clean_data_pagamento(self):
        hoje = get_datetime_now().date()
        data_pagamento = self.cleaned_data.get('data_pagamento')
        if data_pagamento and data_pagamento > hoje:
            self.add_error('data_pagamento', 'A data de pagamento não pode ser futura.')
        return data_pagamento

    def clean_valor_efetivo(self):
        valor = self.cleaned_data.get('valor_efetivo')
        return 0 if valor is None else valor

    def clean(self):
        cleaned_data = super().clean()
        data_pagamento = cleaned_data.get('data_pagamento')
        data_prevista = self.cleaned_data.get('data_prevista')
        valor_efetivo = cleaned_data.get('valor_efetivo')

        # Validações relacionadas a pagamento
        if data_pagamento is not None:
            if valor_efetivo == 0:
                self.add_error('valor_efetivo', 'Informe o valor efetivo da parcela ou remova a data de pagamento.')
            if data_prevista is not None and data_pagamento < data_prevista:
                self.add_error('data_pagamento', 'A data de pagamento não pode ser anterior à data prevista.')

        if valor_efetivo > 0 and data_pagamento is None:
            self.add_error('data_pagamento', 'A data de pagamento não pode ser nula.')

        if valor_efetivo < 0:
            self.add_error('valor_efetivo', 'O valor efetivo deve ser positivo ou zero.')

        return cleaned_data

    def save(self, commit=True):
        parcela = super().save(commit=False)
        if not self.instance.pk:
            # Nova parcela
            parcela.cadastrado_por = self.request.user
            parcela.detalhamento = self.detalhamento  # Garante que o detalhamento está correto
        else:
            # Edição
            parcela.modificado_por = self.request.user

        if commit:
            parcela.save()
        return parcela


class BeneficioDocumentoDigitalizadoForm(DocumentoDigitalizadoForm):
    dono_documento = forms.ModelChoiceFieldPlus(
        Vinculo.objects.none(),
        label='Responsável pelo Documento',
        required=True,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dono_documento'].queryset = Vinculo.objects.servidores()


class CancelarFinalizarBeneficioForm(forms.ModelFormPlus):
    beneficio = forms.ModelChoiceField(label='Benefício', queryset=Beneficio.objects.none())
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'beneficio',
                    'justificativa',
                )
            },
        ),
    )

    class Meta:
        model = Beneficio
        fields = ('justificativa',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['beneficio'].queryset = Beneficio.objects.filter(id=self.instance.id)
        self.fields['beneficio'].initial = self.instance.id
        self.fields['beneficio'].widget.attrs['readonly'] = True


class CancelarBeneficioForm(CancelarFinalizarBeneficioForm):
    def save(self, commit=True):
        if commit:
            self.instance.cancelar(self.request.user, self.cleaned_data['justificativa'])
        return super().save(commit)


class FinalizarBeneficioForm(CancelarFinalizarBeneficioForm):
    def save(self, commit=True):
        if commit:
            self.instance.finalizar(self.request.user, self.cleaned_data['justificativa'])
        return super().save(commit)


class EstoqueBeneficioFilterForm(forms.FormPlus):
    METHOD = 'GET'
    unidade = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().none(),
        required=False,
        label='Unidade',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
    )
    situacao = forms.ChoiceField(label='Situação', choices=[('', 'Todas as Situações'), *list(BeneficioStatus.CHOICES.items())], required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ct_monitoramento = ContentType.objects.get_for_model(Monitoramento)
        unidades_ids = (
            Monitoramento.objects.filter(id__in=Beneficio.objects.filter(content_type=ct_monitoramento).values_list('object_id', flat=True))
            .values_list('unidade__id', flat=True)
            .distinct()
        )
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id__in=unidades_ids)

    def filter_queryset(self, queryset):
        """
        Aplica os filtros ao queryset de Monitoramento
        """
        if self.is_valid():
            unidade = self.cleaned_data.get('unidade')
            situacao = self.cleaned_data.get('situacao')
            if unidade:
                monitoramentos = Monitoramento.objects.filter(unidade=unidade)
                queryset = queryset.filter(monitoramentos__in=monitoramentos)
            if situacao:
                queryset = queryset.filter(status=situacao)
        return queryset


class RelatorioFinanceiroFilterForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.IntegerField(required=False, label='Ano')
    classe = forms.ModelChoiceFieldPlus(
        queryset=ClasseBeneficio.objects,
        required=False,
        label='Classe do Benefício',
    )
    origem_beneficio = forms.ModelChoiceField(queryset=None, required=False, label='Origem do Benefício')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Limita ContentType
        self.fields['origem_beneficio'].queryset = ContentType.objects.filter(app_label='auditoria', model='monitoramento')

    def filter(self, queryset: QuerySet[DetalhamentoQualitativo]):
        """
        Aplica os filtros ao queryset de Monitoramento
        """
        ano = self.cleaned_data.get('ano')
        classe = self.cleaned_data.get('classe')
        origem_beneficio = self.cleaned_data.get('origem_beneficio')
        if ano:
            queryset = queryset.filter(beneficio__ano=ano)
        if classe:
            queryset = queryset.filter(beneficio__classe=classe)
        if origem_beneficio:
            ct = ContentType.objects.get_for_model(origem_beneficio)
            queryset = queryset.filter(
                beneficio__content_type=ct,
                beneficio__object_id=origem_beneficio.id,
            )
        return queryset


class RelatorioQualitativoFilterForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.IntegerField(
        required=False,
    )
    unidade_afetada = forms.ModelChoiceFieldPlus(
        queryset=UnidadeAfetada.objects,
        required=False,
        label='Unidade Afetada',
    )
    alcance_estrategico = forms.ModelChoiceFieldPlus(
        queryset=AlcanceEstrategico.objects,
        required=False,
        label='Alcance Estratégico',
    )

    def filter(self, queryset: QuerySet[DetalhamentoQualitativo]):
        """
        Aplica os filtros ao queryset de Monitoramento
        """
        ano = self.cleaned_data.get('ano')
        unidade_afetada = self.cleaned_data.get('unidade_afetada')
        alcance_estrategico = self.cleaned_data.get('alcance_estrategico')
        if ano:
            queryset = queryset.filter(beneficio__ano=ano)
        if unidade_afetada:
            queryset = queryset.filter(unidade_afetada=unidade_afetada)
        if alcance_estrategico:
            queryset = queryset.filter(alcance_estrategico=alcance_estrategico)

        return queryset


class RemoverDocumentoBeneficioForm(forms.ModelFormPlus):
    justificativa_remocao = forms.CharField(label='Justificativa', widget=forms.Textarea, required=True)

    class Meta:
        model = BeneficioDocumento
        fields = ['justificativa_remocao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance: BeneficioDocumento = super().save(commit=False)
        instance.remover_documento(self.request.user)
        return super().save(commit)
