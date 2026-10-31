from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils.safestring import mark_safe

from comum.models import User, Vinculo
from djtools import forms
from djtools.forms import ReadOnlyField
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus
from djtools.utils import to_ascii
from documento_eletronico.models import DocumentoTexto, ModeloDocumento
from edu.models import Disciplina as DisciplinaEdu
from remanejamento.models import (
    AcaoEditalHistorico,
    AfastamentoRemocaoInterna,
    Disciplina,
    DisciplinaItem,
    Edital,
    EditalCriterioClassificacao,
    EditalRecurso,
    Inscricao,
    InscricaoContemplada,
    InscricaoDisciplinaItem,
    InscricaoItem,
    ServidorDataInicioExercicioRemocaoInterna,
    VagaEdital,
)
from remanejamento.utils import ajustar_sigla_campus_lotacao
from rh.models import CargoEmprego, CargoEmpregoArea, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    if 'documento_eletronico' in settings.INSTALLED_APPS:
        modelo_documento_publicacao_resultado = forms.ModelChoiceField(
            ModeloDocumento.objects.filter(ativo=True),
            label='Modelo de Documento para Termo de Juntada por Anexação',
            widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
            help_text='Ex: Edital de Publicação de Resultado de Remoção Interna',
            required=False,
        )


class EditalRecursoForm(forms.FormPlus):
    edital = forms.ModelChoiceField(label='Edital', queryset=Edital.objects.all(), widget=AutocompleteWidget(readonly=True))
    recurso_texto = forms.CharField(
        label='Recurso',
        widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
        help_text='A resposta a este recurso poderá '
        'ser acompanhada clicando no menu "Gestão de Pessoas -> Remoção Interna -> '
        'Recursos ao Edital" na data/hora informada no Edital.',
    )

    def __init__(self, *args, **kwargs):
        if 'id_edital' in kwargs:
            edital_id = kwargs.pop('id_edital')
            super().__init__(*args, **kwargs)
            self.fields['edital'].initial = edital_id


class EditalRecursoRespostaForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Enviar'
    recurso_resposta = forms.CharField(label='Resposta', widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}))

    class Meta:
        model = EditalRecurso
        fields = ('recurso_resposta',)


class DisciplinaForm(forms.FormPlus):
    edital = forms.ModelChoiceField(label='Edital', queryset=Edital.objects.all(), widget=AutocompleteWidget(readonly=True))
    disciplinas = forms.ModelMultipleChoiceField(
        queryset=DisciplinaEdu.objects.all(),
        label='Disciplinas',
        widget=FilteredSelectMultiplePlus('', True),
        required=True,
        help_text='Escolha as disciplinas referentes ao edital',
    )

    def __init__(self, *args, **kwargs):
        if 'id_edital' in kwargs:
            edital_id = kwargs.pop('id_edital')
            super().__init__(*args, **kwargs)
            edital = Edital.objects.get(pk=edital_id)
            self.fields['edital'].initial = edital.id


class DisciplinaItemForm(forms.FormPlus):
    conteudo = forms.CharField(label='Conteúdo', widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}), help_text='disciplina|sequencia|item')

    def save(self, edital):
        def formatar(valor):
            return to_ascii(valor.strip().upper())

        # Indexando as disciplinas por descricao formatada
        edital_disciplinas = {}
        for d in edital.disciplina_set.all():
            edital_disciplinas[formatar(d.descricao)] = d

        conteudo = self.cleaned_data['conteudo']
        for linha in conteudo.split('\n'):
            disciplina_descricao, item_sequencia, item_descricao = linha.split('|')
            disciplina_descricao_formatada = formatar(disciplina_descricao)
            if disciplina_descricao_formatada in edital_disciplinas:
                disciplina = edital_disciplinas[disciplina_descricao_formatada]
                DisciplinaItem.objects.create(disciplina=disciplina, descricao=item_descricao, sequencia=int(item_sequencia))


def CoordenadorInscricaoEditarFormFactory(inscricao):
    """Form para o coordenador definir o avaliador e o status da inscrição"""

    class CoordenadorInscricaoEditarForm(forms.ModelFormPlus):
        class Meta:
            model = Inscricao
            fields = ('avaliacao_avaliador', 'avaliacao_status')

        avaliacao_avaliador = forms.ModelChoiceField(
            queryset=inscricao.disciplina.avaliadores.all(),
            required=False,
            label='Avaliador',
            help_text=f'Só poderá ser escolhido usuário avaliador da disciplina <a href="/admin/remanejamento/disciplina/{inscricao.disciplina.pk}/">{inscricao.disciplina.descricao}</a>.',
        )

    return CoordenadorInscricaoEditarForm


def AvaliadorInscricaoFormFactory(inscricao):
    """Form para o avaliador definir a aptidão para cada item de disciplina"""
    CHOICE_PERCENTUAL = (
        (0, '0%'),
        (10, '10%'),
        (20, '20%'),
        (30, '30%'),
        (40, '40%'),
        (50, '50%'),
        (60, '60%'),
        (70, '70%'),
        (80, '80%'),
        (90, '90%'),
        (100, '100%'),
    )
    CHOICE_PADRAO = ((0, '-'),)

    class AvaliadorInscricaoForm(forms.FormPlus):
        SUBMIT_LABEL = 'Avaliar Inscrição'

        def save(self):
            inscricao.observacao = self.cleaned_data['observacao']
            inscricao.avaliacao_recurso = self.cleaned_data['avaliacao_recurso']
            inscricao.save()
            for key, val in list(self.cleaned_data.items()):
                if not key.startswith('di_'):
                    continue
                idi, _created = InscricaoDisciplinaItem.objects.get_or_create(
                    inscricao=inscricao, disciplina_item=DisciplinaItem.objects.get(pk=key.split('_')[-1])
                )
                idi.apto_percentual = val
                idi.save()
            inscricao.atualizar_score()
            inscricao.avaliacao_status = 'Avaliado'
            inscricao.save()

    for di in inscricao.disciplina.disciplinaitem_set.all():
        try:
            initial = InscricaoDisciplinaItem.objects.get(inscricao=inscricao, disciplina_item=di).apto_percentual

        except Exception:
            initial = 0

        if di.nao_avaliar:
            AvaliadorInscricaoForm.base_fields[f'dh_{di.pk}'] = forms.IntegerField(
                label=mark_safe(f'<strong>{di.descricao}</strong>'),
                required=False,
                initial='-',
                widget=forms.Select(choices=CHOICE_PADRAO, attrs={'disabled': 'disabled'}),
            )
        else:
            AvaliadorInscricaoForm.base_fields[f'di_{di.pk}'] = forms.IntegerField(
                label=di.descricao, required=False, initial=initial, widget=forms.Select(choices=CHOICE_PERCENTUAL)
            )

    AvaliadorInscricaoForm.base_fields['observacao'] = forms.CharField(
        widget=forms.Textarea(), required=False, label='Observações (Os itens não aptos devem ser explicados aqui)', initial=inscricao.observacao
    )

    AvaliadorInscricaoForm.base_fields['avaliacao_recurso'] = forms.CharField(
        widget=forms.Textarea(), required=False, label='Avaliação do recurso', initial=inscricao.avaliacao_recurso
    )

    return AvaliadorInscricaoForm


class DisciplinaAdminForm(forms.ModelFormPlus):
    class Meta:
        model = Disciplina
        exclude = ()

    avaliadores = forms.MultipleModelChoiceFieldPlus(queryset=User.objects.order_by('username'), required=False)


class EditalForm(forms.ModelFormPlus):
    cargos = forms.MultipleModelChoiceFieldPlus(
        queryset=CargoEmprego.utilizados, help_text='Servidores destes cargos poderão se inscrever neste edital.'
    )

    coordenadores = forms.MultipleModelChoiceFieldPlus(
        required=True, queryset=User.objects.all(), help_text='Os coordenadores poderão acompanhar as inscrições deste edital.'
    )

    servidores_permitidos_multiplas_inscricoes = forms.MultipleModelChoiceFieldPlus(
        required=False,
        queryset=Vinculo.objects.filter(tipo_relacionamento__model='servidor'),
        help_text='Servidores que podem realizar mais de uma inscrição.',
    )

    campus = forms.MultipleModelChoiceFieldPlus(
        label='Campi',
        queryset=UnidadeOrganizacional.objects.uo().all(),
        help_text='Informe os campi participantes desta Remoção Interna',
        widget=FilteredSelectMultiplePlus('', True),
        required=True,
    )
    fim_recursos = forms.DateTimeFieldPlus(label='Fim dos recursos do resultado', required=True)
    resultado_recursos = forms.DateTimeFieldPlus(label='Resultado dos recursos:', required=True)
    edital_documentotexto = forms.ModelChoiceFieldPlus(
        label='Edital',
        queryset=DocumentoTexto.objects.filter(modelo__tipo_documento_texto__nome__icontains='Edital'),
        help_text='Edital que normatiza a remoção interna',
        widget=AutocompleteWidget(),
        required=False,
    )

    class Meta:
        model = Edital
        exclude = ()

    def clean_campus(self):
        campus = self.cleaned_data['campus']
        if campus.count() == 0:
            raise forms.ValidationError('Nenhum campus selecionado.')

        return campus

    def clean_data_resultado_parcial(self):
        data_resultado_parcial = self.cleaned_data['data_resultado_parcial']
        if not data_resultado_parcial:
            raise forms.ValidationError('Este campo é obrigatório.')
        if data_resultado_parcial and self.cleaned_data.get('data_resultado_final', None):
            if data_resultado_parcial >= self.cleaned_data['data_resultado_final']:
                raise forms.ValidationError('A data do resultado parcial deve ser anterior à data do resultado final.')
        return data_resultado_parcial

    def clean_data_homologacao_resultado(self):
        data_homologacao_resultado = self.cleaned_data['data_homologacao_resultado']
        if not data_homologacao_resultado:
            raise forms.ValidationError('Este campo é obrigatório.')
        if data_homologacao_resultado and self.cleaned_data.get('data_resultado_final', None):
            if data_homologacao_resultado <= self.cleaned_data['data_resultado_final']:
                raise forms.ValidationError('A data da homologação do resultado deve ser posterior à data do resultado final.')
        return data_homologacao_resultado

    def clean_cargos(self):
        """Validação: para editais da categoria docente, só permitir cargos com código iniciando em '707'.
        O código 707 é o identificador SIAPE exclusivo da carreira Docente (EBTT) conforme Lei nº 12.772/2012 e anexos.
        """
        cargos = self.cleaned_data.get('cargos')
        # Determina a categoria informada no formulário (se houver) ou na instância
        categoria = self.cleaned_data.get('categoria') if 'categoria' in self.cleaned_data else getattr(self.instance, 'categoria', None)

        if categoria == Edital.DOCENTE and cargos:
            invalid = [c for c in cargos if not str(getattr(c, 'codigo', '') or '').strip().startswith('707')]
            if invalid:
                nomes = ', '.join([f'{c.nome} ({c.codigo})' for c in invalid])
                raise forms.ValidationError(
                    f'Para editais da categoria Docente apenas são permitidos cargos cujo código inicia com 707. Remova: {nomes}'
                )

        return cargos


def InscreverFormFactory(edital, user):
    servidor = user.get_relacionamento()

    class InscricaoForm(forms.ModelFormPlus):
        concurso_ingresso_eh_ifrn = forms.ChoiceField(
            label='Concurso para ingresso foi do IFRN?',
            choices=[(True, 'Sim'), (False, 'Não')],
        )

        class Meta:
            model = apps.get_model('remanejamento', 'inscricao')
            exclude = [
                'servidor',
                'edital',
                'frase_pura',
                'frase_pura_com_chave',
                'frase_hash',
                'avaliacao_status',
                'inicio_exercicio',
                'jornada_trabalho',
            ]

        def __init__(self, *args, **kwargs):
            initial = kwargs.get('initial', {})
            super().__init__(*args, **kwargs)
            for field_name in initial:
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs['readonly'] = True

    fieldsets = []

    # Tratando fields para campi
    campi_fields = []

    for campus in UnidadeOrganizacional.objects.suap().filter(pk__in=edital.campus.all().values_list('pk', flat=True)).order_by('setor__sigla'):
        field = forms.IntegerFieldPlus(required=False, label=campus.nome, widget=forms.NumberInput(attrs={'min': '1', 'step': '1'}))
        field_name = 'campus_' + str(campus.pk)
        campi_fields.append(field_name)
        InscricaoForm.base_fields[field_name] = field

    fieldsets = [
        (
            'DOU do Edital de Homologação do Concurso Público para Ingresso na Instituição',
            {
                'fields': [
                    ('concurso_ingresso_eh_ifrn', 'classificacao_concurso'),
                    ('dou_numero', 'dou_data'),
                    ('dou_pagina', 'dou_sessao'),
                ]
            },
        ),
    ]

    # Disciplinas:
    vagas_edital_disciplinas = VagaEdital.objects.filter(edital=edital, disciplina__isnull=False).distinct('cargo', 'disciplina')
    if edital.eh_edital_remocao_docente() and vagas_edital_disciplinas:
        InscricaoForm.base_fields['vaga_edital'] = forms.ModelChoiceField(
            queryset=vagas_edital_disciplinas.all(),
            required=False,
        )
        fieldsets += [('Escolha da disciplina', {'fields': (('vaga_edital',))})]

    # Anexo
    if (edital.tem_anexo or vagas_edital_disciplinas) and edital.eh_edital_remocao_docente():
        InscricaoForm.base_fields['anexo'] = forms.FileFieldPlus(
            help_text='Anexe a documentação necessária conforme edital (Tamanho máximo: 50 Mb). Para docentes, o anexo é obrigatório somente se a disciplina selecionada for diferente da disciplina de ingresso.',
            required=False,
        )
        fieldsets += [('Documentação necessária', {'fields': ('anexo',)})]

    fieldsets += [('Ordem de preferência dos campi', {'fields': tuple(campi_fields)})]

    InscricaoForm.fieldsets = fieldsets

    def clean(form):
        ordens_preferencia = []
        for key in campi_fields:
            ordens_preferencia.append(form.cleaned_data.get(key))
        for i in ordens_preferencia:
            if i is not None and ordens_preferencia.count(i) > 1:
                raise forms.ValidationError('As ordens de preferência dos campi devem ser únicas.')
        if list(set(ordens_preferencia)) == [None]:
            raise forms.ValidationError('Pelo menos uma ordem de preferência por campus deve ser escolhida')

        if servidor.eh_aposentado:
            raise forms.ValidationError('Servidores aposentados não podem se inscrever em editais de remoção interna.')

        if edital.eh_edital_remocao_docente():
            # Para remoção docente: Validação de disciplina / concurso / equivalência / anexo
            vaga = form.cleaned_data.get('vaga_edital')
            # Se não selecionou a disciplna:
            if not vaga:
                form.add_error('vaga_edital', 'É obrigatório selecionar uma disciplina para remoção docente.')
            else:
                # 1 - Verificar se a disciplina selecionado é igual a disciplina de ingresso, neste caso valida a inscrição
                if not (servidor.disciplina_ingresso and vaga.disciplina == servidor.disciplina_ingresso):
                    # Verificar se existe concurso vigente (cadastrado na configuração)
                    disciplina_possui_concurso_vigente = vaga.possui_concurso_vigente
                    # Verifica se a disciplina de ingresso está contida nas correlatas, caso esteja, valida a inscrição
                    if servidor.disciplina_ingresso not in vaga.disciplinas_correlatas.all():
                        form.add_error(
                            'vaga_edital',
                            f'A disciplina de ingresso do servidor ({servidor.disciplina_ingresso}) não está entre as disciplinas correlatas cadastradas para a disciplina {vaga.disciplina}.',
                        )
                    if not disciplina_possui_concurso_vigente:
                        if not form.cleaned_data.get('anexo', False):
                            form.add_error(
                                'anexo',
                                f'Para a disciplina {vaga.disciplina}, é obrigatório adicionar arquivo anexo com documentação necessária para análise de equivalência/correlação da disciplina.',
                            )

        return form.cleaned_data

    def clean_anexo(self):
        if self.cleaned_data['anexo']:
            file_ = self.cleaned_data['anexo']
            # verfica se MIME TYPE é PDF ou Octet-Stream (devido bug no Firefox < v7), e se a extensão é .PDF
            if (('pdf' not in file_.content_type.lower()) and ('application/octet-stream' not in file_.content_type.lower())) or (
                not file_.name.lower().endswith('.pdf')
            ):
                raise forms.ValidationError(f'O anexo deve estar no formato PDF (recebido: {file_.content_type})')
            if file_.size > 52428800:  # 50Mb
                raise forms.ValidationError('O anexo deve ter no maximo 50MB')

            # validação para que quando a disciplina de ingresso é igual a disciplina selecionada não deve permitir adicionar o anexo
            vaga = self.cleaned_data.get('vaga_edital')
            if vaga and servidor.disciplina_ingresso and vaga.disciplina == servidor.disciplina_ingresso:
                # limpa o campo anexo e exibe a mensagem
                self.cleaned_data['anexo'] = None
                raise forms.ValidationError(
                    'Não é necessário anexar documentação quando a disciplina selecionada é igual a disciplina de ingresso do servidor.'
                )

        return self.cleaned_data['anexo']

    def clean_vaga_edital(self):
        if self.cleaned_data['vaga_edital']:
            vaga = self.cleaned_data['vaga_edital']
            if vaga.edital.eh_edital_remocao_docente():
                # Verifica se o servidor possui disciplina de ingresso cadastrada
                if not servidor.disciplina_ingresso:
                    raise forms.ValidationError('Servidor não possui disciplina de ingresso cadastrada no sistema.')

        return self.cleaned_data['vaga_edital']

    def save(form):
        if not edital.is_em_periodo_de_inscricao_servidor(servidor):
            raise Exception('Inscrções fora do periodo')

        form.instance.edital = edital
        form.instance.servidor = servidor
        form.instance.jornada_trabalho = servidor.jornada_trabalho
        form.instance.inicio_exercicio = servidor.data_inicio_exercicio_no_cargo
        inscricao = super(InscricaoForm, form).save()
        for key in campi_fields:
            preferencia = form.cleaned_data[key]
            if not preferencia:
                continue
            campus_pk = int(key.split('_')[1])
            campus = UnidadeOrganizacional.objects.suap().get(pk=campus_pk)
            InscricaoItem.objects.create(inscricao=inscricao, campus=campus, preferencia=preferencia)
            inscricao.atualizar_frases()
        return inscricao

    InscricaoForm.clean = clean
    InscricaoForm.save = save
    if edital.tem_anexo:
        InscricaoForm.clean_anexo = clean_anexo

    return InscricaoForm


class InscricaoRecursoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Enviar'

    class Meta:
        model = Inscricao
        fields = ['recurso_texto']


class InscricaoRespostaRecursoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Enviar'

    class Meta:
        model = Inscricao
        fields = ['avaliacao_recurso', 'situacao_recurso']


class InscricaoContempladaExtraordinariaForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Salvar'
    justificativa = forms.CapitalizeTextField(
        label='Justificativa',
        help_text='Justificativa ou amparo legal da contemplação',
        required=True,
        max_length=300,
        widget=forms.TextInput(attrs={'size': '65'}),
    )
    inscricao = forms.ModelChoiceFieldPlus(Inscricao.objects.none(), required=True)

    class Meta:
        model = InscricaoContemplada
        fields = ['inscricao', 'campus_origem', 'campus_destino', 'justificativa']

    def __init__(self, *args, **kwargs):
        if 'edital_pk' in kwargs:
            edital_pk = kwargs.pop('edital_pk')
        super().__init__(*args, **kwargs)
        self.edital = Edital.objects.get(pk=edital_pk)
        self.fields['inscricao'].queryset = Inscricao.objects.filter(confirmada=True, edital=self.edital).exclude(
            pk__in=[InscricaoContemplada.objects.filter(inscricao__edital__pk=edital_pk).values_list('inscricao__id', flat=True)]
        )
        self.fields['campus_origem'].queryset = self.edital.campus.all()
        self.fields['campus_destino'].queryset = self.edital.campus.all()

    def clean(self) -> dict:
        cleaned_data = super().clean()
        campus_origem = cleaned_data.get('campus_origem')
        campus_destino = cleaned_data.get('campus_destino')
        inscricao = cleaned_data.get('inscricao')
        if inscricao and campus_origem and campus_destino:
            self._validar_campus_origem(inscricao, campus_origem)
            if campus_origem == campus_destino:
                self.add_error('campus_destino', 'Não é possível remoção para o mesmo campus de origem.')

        return cleaned_data

    def _validar_campus_origem(self, inscricao: Inscricao, campus_origem: UnidadeOrganizacional) -> None:
        # Mesma origem do processamento do resultado (Edital.get_lista_inscritos): campus ajustado ou de lotação.
        # O edital lista as UOs SUAP (ex.: SGA), mas a lotação aponta para a UO SIAPE, cuja sigla pode diferir
        # (ex.: CSGA): por isso compara as siglas ajustadas.
        if inscricao.campus_origem_ajustado:
            descricao, sigla_servidor = 'o campus de lotação ajustado na inscrição', inscricao.campus_origem_ajustado.sigla
        else:
            descricao, sigla_servidor = 'o campus de lotação do servidor', inscricao.servidor.setor_lotacao.uo.sigla
        sigla_servidor = ajustar_sigla_campus_lotacao(sigla_servidor)
        if sigla_servidor != ajustar_sigla_campus_lotacao(campus_origem.sigla):
            self.add_error('campus_origem', f'O campus de origem deve ser {descricao}: selecione {sigla_servidor}.')

    @transaction.atomic()
    def save(self, *args, **kwargs):
        situacao_ultima_inscricao_contemplada_valida_do_edital = (
            InscricaoContemplada.objects.filter(
                inscricao__edital=self.edital,
                situacao__in=[
                    InscricaoContemplada.CONTEMPLADO,
                    InscricaoContemplada.PUBLICADA_PARCIAL,
                    InscricaoContemplada.PUBLICADA_FINAL,
                    InscricaoContemplada.HOMOLOGADA,
                ],
            )
            .order_by('-id')
            .last()
            .situacao
        )
        self.instance.situacao = situacao_ultima_inscricao_contemplada_valida_do_edital
        self.instance.atualizado_em = datetime.now()
        self.instance.atualizado_por = self.request.user.get_vinculo()
        if not self.instance.pk:
            acao_realizada = (
                f'Inscrição número {self.instance.inscricao.id} foi registrada como Contemplada de forma extraordinária com a seguinte justificativa: {self.instance.justificativa}\n'
                ']}'
            )
            AcaoEditalHistorico.cadastrar_acao(
                self.instance.inscricao.edital, self.instance.inscricao.edital.get_etapa_atual(), acao_realizada, self.request.user.get_vinculo()
            )
        super().save(*args, **kwargs)


class EditalCriterioClassificacaoForm(forms.ModelFormPlus):
    class Meta:
        model = EditalCriterioClassificacao
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        edital_id = self.request.GET.get('edital')
        ordem = cleaned_data.get('ordem')
        criterio_classificacao = cleaned_data.get('criterio_classificacao')

        if edital_id and criterio_classificacao:
            if EditalCriterioClassificacao.objects.filter(edital=edital_id, criterio_classificacao=criterio_classificacao).exists():
                raise forms.ValidationError('Já existe critério cadastrado.')

        # Verificar se já existe outro objeto cadastrado para o edital com a mesma ordem
        if edital_id and ordem:
            if EditalCriterioClassificacao.objects.filter(edital=edital_id, ordem=ordem).exists():
                raise forms.ValidationError('Já existe critério cadastrado com a mesma ordem.')

        return cleaned_data


class AfastamentoRemocaoInternaForm(forms.ModelFormPlus):
    class Meta:
        model = AfastamentoRemocaoInterna
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        edital_id = self.request.GET.get('edital')
        afastamento = cleaned_data.get('afastamento')

        if edital_id and afastamento:
            if AfastamentoRemocaoInterna.objects.filter(edital=edital_id, afastamento=afastamento).exists():
                raise forms.ValidationError('Já existe Afastamento cadastrado.')

        return cleaned_data


class InabilitarInscricaoForm(forms.FormPlus):
    motivo_inapta = forms.CharField(
        label='Motivo', widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}), help_text='Motivo ou justificativa da inaptidão', required=True
    )

    def __init__(self, *args, **kwargs):
        title = kwargs.pop('title', None)
        super().__init__(*args, **kwargs)
        if title:
            self.TITLE = title


class ReabilitarInscricaoForm(forms.FormPlus):
    observacao = forms.CharField(
        label='Observação',
        widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
        help_text='Motivo ou justificativa da reabilitação',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        title = kwargs.pop('title', None)
        super().__init__(*args, **kwargs)
        if title:
            self.TITLE = title


class EditarDadosInscricaoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Validar e Salvar'
    inicio_exercicio = forms.DateFieldPlus(
        label='Data de Início de Exercício',
        help_text='Ao alterar esse valor será registrado para uso em futuros editais de Remoção Interna',
        required=True,
    )
    campus_origem_ajustado = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.suap().all(), required=False)
    concurso_ingresso_eh_ifrn = forms.ChoiceField(
        label='Concurso para ingresso foi do IFRN?',
        choices=[(True, 'Sim'), (False, 'Não')],
    )

    class Meta:
        model = Inscricao
        fields = [
            'inicio_exercicio',
            'concurso_ingresso_eh_ifrn',
            'dou_numero',
            'dou_data',
            'dou_pagina',
            'dou_sessao',
            'classificacao_concurso',
            'jornada_trabalho',
            'campus_origem_ajustado',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fieldsets = [
                (
                    'Dados Inscrição',
                    {
                        'fields': (
                            'inicio_exercicio',
                            'concurso_ingresso_eh_ifrn',
                            'dou_numero',
                            'dou_data',
                            'dou_pagina',
                            'dou_sessao',
                            'classificacao_concurso',
                            'jornada_trabalho',
                        )
                    },
                ),
                ('Ajuste para Remoção Interna', {'fields': ('campus_origem_ajustado',)}),
            ]

            self.TITLE = f'Inscrição de {self.instance.servidor}'
            if data_inicio_ajustada := ServidorDataInicioExercicioRemocaoInterna.objects.filter(servidor=self.instance.servidor).first():
                self.fields['inicio_exercicio_ajustado'] = ReadOnlyField(label='Data de Início Ajustada')
                self.fields['inicio_exercicio_ajustado'].initial = data_inicio_ajustada.data_inicio_exercicio.strftime('%d/%m/%Y')
                self.fieldsets[1][1]['fields'] += ('inicio_exercicio_ajustado',)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        # Cria ou atualiza a instancia de ServidorDataInicioExercicioRemocaoInterna se a data for diferente da data de inicio do exercicio do servidor
        if self.cleaned_data.get('inicio_exercicio', False) != self.instance.servidor.data_inicio_exercicio_no_cargo:
            ServidorDataInicioExercicioRemocaoInterna.objects.update_or_create(
                servidor=self.instance.servidor,
                defaults={
                    'data_inicio_exercicio': self.cleaned_data['inicio_exercicio'],
                    'atualizado_por': self.request.user.get_vinculo(),
                    'atualizado_em': datetime.now(),
                },
            )
        self.instance.validado_por = self.request.user.get_vinculo()
        self.instance.validado_em = datetime.now()
        self.instance.atualizado_em = datetime.now()
        self.instance.atualizado_por = self.request.user.get_vinculo()
        super().save(*args, **kwargs)


class CadastrarVagasEditalForm(forms.FormPlus):
    TITLE = 'Vagas do Cargo/Área/Disciplina: '
    SUBMIT_LABEL = 'Salvar'

    def __init__(self, *args, **kwargs):
        if 'edital' in kwargs:
            self.edital = kwargs.pop('edital')
        if 'vagaedital' in kwargs:
            vagaedital = kwargs.pop('vagaedital')
            self.cargo_id = vagaedital.cargo.id or None
            if self.edital.eh_edital_remocao_docente():
                self.TITLE = f'Vagas para Disciplina: {vagaedital.disciplina.descricao}'
            else:
                self.TITLE = self.TITLE + vagaedital.get_cargo_area()
                self.cargo_emprego_area_id = vagaedital.cargo_emprego_area.id if vagaedital.cargo_emprego_area else None
        super().__init__(*args, **kwargs)
        if self.edital and self.cargo_id:
            if self.edital.eh_edital_remocao_docente():
                self.vagas_edital = VagaEdital.objects.filter(edital=self.edital, disciplina__id=vagaedital.disciplina.id).order_by('campus__sigla')
            else:
                self.vagas_edital = VagaEdital.objects.filter(
                    edital=self.edital, cargo__id=self.cargo_id, cargo_emprego_area__id=self.cargo_emprego_area_id
                ).order_by('campus__sigla')
            for vagaedital in self.vagas_edital:
                name_field = f'{vagaedital.id}'
                self.fields[name_field] = forms.IntegerFieldPlus(label=vagaedital.campus.sigla, required=False, initial=vagaedital.qtd_edital)

    def processar(self):
        for vagaedital in self.vagas_edital:
            name_field = f'{vagaedital.id}'
            if self.cleaned_data.get(name_field, False):
                qtd_vagas = self.cleaned_data.get(name_field)
                vagaedital.qtd_edital = qtd_vagas
                vagaedital.atualizado_em = datetime.now()
                vagaedital.atualizado_por = self.request.user.get_vinculo()
                vagaedital.save()


class ConfigurarCargosVagasEditalForm(forms.Form):
    TITLE = 'Configurar Cargos e Áreas do Edital'
    SUBMIT_LABEL = 'Salvar'

    def __init__(self, *args, **kwargs):
        if 'edital_id' in kwargs:
            edital_id = kwargs.pop('edital_id')
            self.edital = Edital.objects.get(pk=edital_id)
            self.request = kwargs.pop('request')
            super().__init__(*args, **kwargs)

        if self.edital:
            for cargo in self.edital.cargos.all().order_by('nome'):
                if CargoEmpregoArea.objects.filter(cargo_emprego=cargo).exists():
                    for cargo_emprego_area in CargoEmpregoArea.objects.filter(cargo_emprego=cargo).order_by('descricao'):
                        name_field = f'{cargo.id}_{cargo_emprego_area.id}'
                        label = cargo_emprego_area
                        if name_field and label and not VagaEdital.objects.filter(edital=self.edital, cargo_emprego_area=cargo_emprego_area).exists():
                            self.fields[name_field] = forms.BooleanField(label=label, required=False)
                else:
                    name_field = f'{cargo.id}'
                    if name_field and not VagaEdital.objects.filter(edital=self.edital, cargo=cargo).exists():
                        self.fields[name_field] = forms.BooleanField(label=cargo.nome, required=False, initial=True)

    def processar(self):
        for cargo in self.edital.cargos.all():
            for campus in self.edital.campus.all():
                if CargoEmpregoArea.objects.filter(cargo_emprego=cargo).exists():
                    for cargo_emprego_area in CargoEmpregoArea.objects.filter(cargo_emprego=cargo):
                        name_field = f'{cargo.id}_{cargo_emprego_area.id}'
                        if self.cleaned_data.get(name_field, False):
                            VagaEdital.objects.update_or_create(
                                edital=self.edital,
                                campus=campus,
                                cargo=cargo,
                                cargo_emprego_area=cargo_emprego_area,
                                qtd_edital=0,
                                qtd_remanescente=0,
                            )
                else:
                    name_field = f'{cargo.id}'
                    if self.cleaned_data.get(name_field, False):
                        VagaEdital.objects.update_or_create(edital=self.edital, campus=campus, cargo=cargo, qtd_edital=0, qtd_remanescente=0)


class ConfigurarDisciplinasEditalForm(forms.Form):
    TITLE = 'Configurar Disciplinas do Edital'
    SUBMIT_LABEL = 'Salvar'
    disciplina = forms.ModelChoiceFieldPlus(queryset=DisciplinaEdu.objects.all(), required=True)
    possui_concurso_vigente = forms.BooleanField(label='Possui Concurso vigente?', required=False)

    def __init__(self, *args, **kwargs):
        if 'edital_id' in kwargs:
            edital_id = kwargs.pop('edital_id')
            self.edital = Edital.objects.get(pk=edital_id)
            self.request = kwargs.pop('request')
            super().__init__(*args, **kwargs)

    def processar(self):
        disciplina = self.cleaned_data.get('disciplina', False)
        possui_concurso_vigente = self.cleaned_data.get('possui_concurso_vigente', False)
        if disciplina:
            for cargo in self.edital.cargos.all():
                for campus in self.edital.campus.all():
                    VagaEdital.objects.update_or_create(
                        edital=self.edital,
                        campus=campus,
                        cargo=cargo,
                        disciplina=disciplina,
                        qtd_edital=0,
                        qtd_remanescente=0,
                        possui_concurso_vigente=possui_concurso_vigente,
                    )


class VincularResultadoEditalForm(forms.Form):
    TITLE = 'Vincular documento de Resultado'
    SUBMIT_LABEL = 'Salvar'

    documento = forms.ModelChoiceFieldPlus(
        label='Documento de Resultado',
        queryset=DocumentoTexto.objects.filter(modelo__tipo_documento_texto__nome__icontains='Edital'),
        help_text='Documento que contém o resultado da remoção interna',
        widget=AutocompleteWidget(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)


class CadastrarAreasCorrelatasVagaEditalForm(forms.Form):
    areas_correlatas = forms.MultipleModelChoiceFieldPlus(
        queryset=CargoEmpregoArea.objects.all(), required=True, help_text='Procure pelo nome do cargo ou área.'
    )

    def __init__(self, *args, **kwargs):
        if 'vagaedital_id' in kwargs:
            vagaedital_id = kwargs.pop('vagaedital_id')
            self.vagaedital = VagaEdital.objects.get(pk=vagaedital_id)
            self.TITLE = f'Cargo/Área: {self.vagaedital.get_cargo_area()}'
        super().__init__(*args, **kwargs)
        self.fields['areas_correlatas'].queryset = self.fields['areas_correlatas'].queryset.filter(cargo_emprego__pk=self.vagaedital.cargo.id)
        if self.vagaedital.areas_correlatas.exists():
            self.fields['areas_correlatas'].initial = self.vagaedital.areas_correlatas.all()

    def processar(self):
        areas_correlatas = self.cleaned_data.get('areas_correlatas', False)
        if areas_correlatas:
            for vagaedital in VagaEdital.objects.filter(
                edital=self.vagaedital.edital, cargo=self.vagaedital.cargo, cargo_emprego_area=self.vagaedital.cargo_emprego_area
            ):
                vagaedital.areas_correlatas.set(areas_correlatas)
                vagaedital.save()


class CadastrarCargosCorrelatosVagaEditalForm(forms.Form):
    cargos_correlatos = forms.MultipleModelChoiceFieldPlus(
        queryset=CargoEmprego.objects.all(),
        required=False,
        label='Cargos Correlatos',
        help_text='Servidores destes cargos concorrem às vagas deste cargo. Só é possível escolher cargos do edital.',
    )

    def __init__(self, *args, **kwargs):
        self.vagaedital = VagaEdital.objects.get(pk=kwargs.pop('vagaedital_id'))
        self.TITLE = f'Cargo: {self.vagaedital.get_cargo_area()}'
        super().__init__(*args, **kwargs)
        self.fields['cargos_correlatos'].queryset = self.vagaedital.edital.cargos.exclude(pk=self.vagaedital.cargo_id)
        self.fields['cargos_correlatos'].initial = self.vagaedital.cargos_correlatos.all()

    def processar(self) -> None:
        cargos_correlatos = self.cleaned_data.get('cargos_correlatos') or []
        for vagaedital in VagaEdital.objects.filter(
            edital=self.vagaedital.edital, cargo=self.vagaedital.cargo, cargo_emprego_area=self.vagaedital.cargo_emprego_area
        ):
            vagaedital.cargos_correlatos.set(cargos_correlatos)


class CadastrarDisciplinasCorrelatasVagaEditalForm(forms.Form):
    disciplinas_correlatas = forms.MultipleModelChoiceFieldPlus(
        queryset=DisciplinaEdu.objects.all(), required=True, label='Disciplinas Correlatas', help_text='Procure pelo nome da disciplina.'
    )

    def __init__(self, *args, **kwargs):
        if 'vagaedital_id' in kwargs:
            vagaedital_id = kwargs.pop('vagaedital_id')
            self.vagaedital = VagaEdital.objects.get(pk=vagaedital_id)
            self.TITLE = f'Disciplina: {self.vagaedital.disciplina.descricao}'
        super().__init__(*args, **kwargs)
        if self.vagaedital.disciplinas_correlatas.exists():
            self.fields['disciplinas_correlatas'].initial = self.vagaedital.disciplinas_correlatas.all()

    def processar(self):
        disciplinas_correlatas = self.cleaned_data.get('disciplinas_correlatas', False)
        if disciplinas_correlatas:
            for vagaedital in VagaEdital.objects.filter(
                edital=self.vagaedital.edital, cargo=self.vagaedital.cargo, disciplina=self.vagaedital.disciplina
            ):
                vagaedital.disciplinas_correlatas.set(disciplinas_correlatas)
                vagaedital.save()


class FiltroInscricoesForm(forms.FormPlus):
    METHOD = 'GET'
    TITLE = 'Filtrar Inscrições'
    SUBMIT_LABEL = 'Filtrar'

    texto = forms.CharField(label='Texto', max_length=100, required=False)
    cargo = forms.ModelChoiceField(
        label='Cargo',
        queryset=CargoEmprego.objects.all(),
        widget=AutocompleteWidget(multiple=False),
        required=False,
    )
    disciplina = forms.ModelChoiceField(
        label='Disciplina',
        queryset=DisciplinaEdu.objects.all(),
        widget=AutocompleteWidget(multiple=False),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        if self.edital.eh_edital_remocao_docente():
            self.fields.pop('cargo')
            self.fields['disciplina'].queryset = DisciplinaEdu.objects.filter(
                id__in=VagaEdital.objects.filter(edital=self.edital).values_list('disciplina__id', flat=True).distinct()
            )
        else:
            self.fields.pop('disciplina')
            self.fields['cargo'].queryset = CargoEmprego.objects.filter(
                id__in=VagaEdital.objects.filter(edital=self.edital).values_list('cargo__id', flat=True).distinct()
            )
