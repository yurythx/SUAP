from decimal import Decimal
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from comum import utils
from comum.models import Ano, Configuracao, Vinculo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    RenderableSelectMultiple,
)
from djtools.utils import running_tests
from edu import tasks
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    AproveitamentoComponente,
    AproveitamentoEstudo,
    AtoRegulatorioCurso,
    AvaliadorEquivalenciaComponente,
    CertificacaoConhecimento,
    ClassificacaoComplementarComponenteCurricular,
    Componente,
    ComponenteCurricular,
    ComponenteCurricularCertificacaoParcial,
    ConfiguracaoCertificacaoParcial,
    ConfiguracaoCreditosEspeciais,
    CursoCampus,
    CursoTecnico,
    Diario,
    Diretoria,
    EquivalenciaComponente,
    EquivalenciaComponenteMatriz,
    EquivalenciaComponenteQAcademico,
    EstruturaCurso,
    JustificativaDispensaENADE,
    MatriculaDiario,
    MatriculaDiarioResumida,
    Matriz,
    MatrizCurso,
    Modalidade,
    ModalidadePraticaProfissional,
    NivelEnsino,
    Nucleo,
    RegistroHistorico,
    RotuloModulo,
    SituacaoMatricula,
    TipoComponente,
    TramitacaoProcessoEMEC,
)
from rh.models import UnidadeOrganizacional
from edu.q_academico import DAO, MockDAO

from .utils import RedirectForm


class EquivalenciaComponenteForm(forms.ModelFormPlus):
    tipo = forms.ModelChoiceField(TipoComponente.objects, label='Tipo')
    componentes = forms.MultipleModelChoiceField(
        Componente.objects,
        label='Componentes A',
        required=True,
        widget=AutocompleteWidget(
            search_fields=Componente.SEARCH_FIELDS,
            multiple=True,
            form_filters=[('tipo', 'tipo')],
        ),
    )
    equivalentes = forms.MultipleModelChoiceField(
        Componente.objects,
        label='Componentes B',
        required=True,
        widget=AutocompleteWidget(
            search_fields=Componente.SEARCH_FIELDS,
            multiple=True,
            form_filters=[('tipo', 'tipo')],
        ),
    )

    fieldsets = (('Dados gerais', {'fields': ('tipo', 'componentes', 'equivalentes')}),)

    class Meta:
        model = EquivalenciaComponente
        fields = 'componentes', 'equivalentes'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id:
            componente = self.instance.componentes.first()
            self.initial['tipo'] = componente.tipo_id if componente else None


class AvaliadorEquivalenciaComponenteForm(forms.ModelFormPlus):
    class Meta:
        model = AvaliadorEquivalenciaComponente
        fields = ('vinculo',)

    def __init__(self, *args, **kwargs):
        equivalencia = kwargs.pop('equivalencia')
        super().__init__(*args, **kwargs)
        self.instance.equivalencia_componente = equivalencia
        self.fields['vinculo'].queryset = self.fields['vinculo'].queryset.exclude(
            id__in=equivalencia.avaliadorequivalenciacomponente_set.values('vinculo_id')
        )


class AvaliarEquivalenciaComponenteForm(forms.FormPlus):
    aprovada = forms.ChoiceField(label='Aprovada', choices=[['', ''], ['S', 'Sim'], ['N', 'Não']])
    observacao = forms.CharField(label='Observação', widget=forms.Textarea(), required=True)

    senha = forms.PasswordField(label='Senha', help_text='Confirme a operação com a sua senha do SUAP')

    def __init__(self, *args, **kwargs):
        self.equivalencias = kwargs.pop('equivalencias')
        super().__init__(*args, **kwargs)

    def clean_observacao(self):
        if self.cleaned_data.get('aprovada') == 'N' and not self.data.get('observacao'):
            raise forms.ValidationError('Informe a justificativa')
        return self.cleaned_data.get('observacao')

    def clean(self):
        if self.equivalencias.filter(equivalenciacomponentematriz__isnull=True).exists():
            raise forms.ValidationError('Não é possível avaliar equivalência que não possuem matrizes de origem e destino.')
        return self.cleaned_data


class ReplicacaoCursoCampusForm(forms.FormPlus):
    SUBMIT_LABEL = 'Replicar Curso'
    diretoria = forms.ModelChoiceField(
        Diretoria.objects, label='Diretoria', required=True, help_text='Informe o campus para o qual você deseja replicar o curso'
    )
    codigo = forms.CharField(label='Código')
    coordenador = forms.ModelChoiceFieldPlus(Vinculo.objects, label='Coordenador', required=False, help_text='Informe o coordenador do curso')
    coordenador_2 = forms.ModelChoiceFieldPlus(
        Vinculo.objects, label='Coordenador substituto', required=False, help_text='Informe o coordenador substituto do curso'
    )

    def __init__(self, *args, **kwargs):
        curso_campus = kwargs.pop('curso_campus')
        super().__init__(*args, **kwargs)
        self.fields['codigo'].initial = curso_campus.codigo
        self.fields['coordenador'].queryset = Vinculo.objects.funcionarios()
        self.fields['coordenador_2'].queryset = Vinculo.objects.funcionarios()

    def processar(self, campus_curso):
        campus_curso.replicar(
            self.cleaned_data['diretoria'], self.cleaned_data['codigo'], self.cleaned_data['coordenador'], self.cleaned_data['coordenador_2']
        )
        return campus_curso


class DataFuncionamentoCursoCampusForm(forms.ModelFormPlus):
    class Meta:
        model = CursoCampus
        fields = ('data_funcionamento', 'data_solicitacao_reconhecimento', 'data_limite_reconhecimento')


class AtoRegulatorioCursoCampusForm(forms.ModelFormPlus):
    tipo_cadastro = forms.ChoiceField(
        label='Tipo de cadastro',
        widget=forms.RadioSelect(),
        choices=[['1', 'Documento eletrônico'], ['2', 'Upload de documento'], ['3', 'Link do D.O.U.']],
    )
    sigla_orgao_campus = forms.CharFieldPlus(required=False, widget=forms.HiddenInput())
    sigla_instituicao = forms.CharFieldPlus(required=False, widget=forms.HiddenInput())
    modalidade = forms.CharFieldPlus(required=False, widget=forms.HiddenInput())

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'tipo',
                    'validade',
                    'quantidade_vagas',
                    'tipo_cadastro',
                    'id_documento',
                    'arquivo_documento',
                    'url_documento',
                    'ad_referendum',
                )
            },
        ),
        (
            'Dados do documento',
            {
                'fields': (
                    'tipo_documento',
                    'data',
                    'numero',
                    'orgao',
                    'sigla_orgao_campus',
                    'sigla_instituicao',
                    'modalidade',
                    'ato_homologador',
                )
            },
        ),
        (
            'Dados da publicação',
            {'fields': ('veiculo_publicacao', ('numero_publicacao', 'data_publicacao'), ('pagina_publicacao', 'secao_publicacao'))},
        ),
    )

    class Meta:
        model = AtoRegulatorioCurso
        exclude = ('curso', 'id_pafc')

    class Media:
        js = ('/static/edu/js/AtoRegulatorioCursoCampusForm.js',)

    def __init__(self, *args, **kwargs):
        curso_id = kwargs.pop('curso_id', None)
        ato_ad_referendum_pk = kwargs.pop('ato_ad_referendum_pk', None)
        super().__init__(*args, **kwargs)

        if curso_id:
            self.instance.curso_id = curso_id

        if self.instance.id:
            self.ato_ad_referendum = self.instance.atoregulatoriocurso_set.first()
            self.fields['tipo'].widget = forms.HiddenInput()
        else:
            self.ato_ad_referendum = (
                ato_ad_referendum_pk and AtoRegulatorioCurso.objects.filter(id=ato_ad_referendum_pk, ad_referendum=True).first() or None
            )
        if self.ato_ad_referendum:
            self.initial['tipo'] = self.ato_ad_referendum.tipo
            self.fields['tipo'].widget = forms.HiddenInput()
            del self.fields['ad_referendum']
            del self.fields['quantidade_vagas']
            del self.fields['validade']

        sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        sigla_reitoria = Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')
        sigla_reitoria = sigla_reitoria != sigla_instituicao and f'/{sigla_reitoria}' or ''

        self.initial['sigla_instituicao'] = sigla_instituicao
        self.initial['sigla_orgao_campus'] = f'DG/{self.instance.curso.diretoria.setor.uo.sigla}{sigla_reitoria}/{sigla_instituicao}'
        self.initial['modalidade'] = self.instance.curso.modalidade_id

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

            if self.instance.id_pafc:
                self.INFO = mark_safe(f'Este ato regulatório foi criado automaticamente pelo <a href="/pafc/pafc/{self.instance.id_pafc}/">PAFC</a>.')

                self.fieldsets = (
                    (
                        'Dados da publicação',
                        {'fields': ('veiculo_publicacao', ('numero_publicacao', 'data_publicacao'), ('pagina_publicacao', 'secao_publicacao'))},
                    ),
                )

                del self.fields['tipo']
                if 'validade' in self.fields:
                    del self.fields['validade']
                if 'quantidade_vagas' in self.fields:
                    del self.fields['quantidade_vagas']
                del self.fields['tipo_cadastro']
                del self.fields['id_documento']
                del self.fields['arquivo_documento']
                del self.fields['url_documento']
                del self.fields['tipo_documento']
                del self.fields['data']
                del self.fields['numero']
                del self.fields['orgao']
        elif curso_id:
            from pafc.models import PAFC

            if pafc := PAFC.objects.filter(curso_id=self.instance.curso_id).exclude(situacao__in=PAFC.SITUACOES_TERMINAIS).first():
                self.INFO = mark_safe(
                    f'Há um <a href="{pafc.get_absolute_url()}">PAFC em andamento</a> para esse curso. '
                    f'Evite adicionar manualmente os atos regulatórios relativos a ele, pois o sistema o fará automaticamente ao final do processo.'
                )

        self.fields['ato_homologador'].widget = forms.HiddenInput()

    def clean_id_documento(self):
        documento = self.cleaned_data.get('id_documento')
        return documento and documento.id or None

    def clean_quantidade_vagas(self):
        quantidade_vagas = self.cleaned_data.get('quantidade_vagas')
        tipo = self.cleaned_data.get('tipo')
        if tipo == AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS and not quantidade_vagas:
            raise forms.ValidationError('Informe a quantidade de vagas anuais autorizadas.')
        if tipo != AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS and quantidade_vagas:
            raise forms.ValidationError('O campo Quantidade de vagas anuais autorizadas não pode ser preenchido.')
        return quantidade_vagas

    def clean_validade(self):
        validade = self.cleaned_data.get('validade')
        tipo = self.cleaned_data.get('tipo')
        if tipo not in [AtoRegulatorioCurso.TIPO_RECONHECIMENTO, AtoRegulatorioCurso.TIPO_RENOVACAO] and validade:
            raise forms.ValidationError('O campo Validade não pode ser preenchido.')
        return validade

    def clean_numero(self):
        numero = self.cleaned_data['numero']
        if numero:
            if not numero.isdigit():
                raise forms.ValidationError('Informe um número.')
            if numero[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return numero

    def clean_data(self):
        data = self.cleaned_data['data']
        if data and self.ato_ad_referendum and data < self.ato_ad_referendum.data:
            data_ad = self.ato_ad_referendum.data.strftime('%d/%m/%Y')
            data_ho = data.strftime('%d/%m/%Y')
            raise forms.ValidationError(
                f'A data do ato Ad Referendum ({data_ad}) não pode ser maior que a data deste ato de homologação ({data_ho}).'
            )
        return data

    def clean_numero_publicacao(self):
        numero_publicacao = self.cleaned_data['numero_publicacao']
        if numero_publicacao:
            if not numero_publicacao.isdigit():
                raise forms.ValidationError('Informe um número.')
            if numero_publicacao[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return numero_publicacao

    def clean_secao_publicacao(self):
        secao_publicacao = self.cleaned_data['secao_publicacao']
        if secao_publicacao:
            if not secao_publicacao.isdigit():
                raise forms.ValidationError('Informe um número.')
            if secao_publicacao[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return secao_publicacao

    def clean_pagina_publicacao(self):
        pagina_publicacao = self.cleaned_data['pagina_publicacao']
        if pagina_publicacao:
            if not pagina_publicacao.isdigit():
                raise forms.ValidationError('Informe um número.')
            if pagina_publicacao[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return pagina_publicacao

    def clean_tipo(self):
        tipo = self.cleaned_data['tipo']
        if (
            tipo
            and self.ato_ad_referendum is None
            and self.instance.id is None
            and self.instance.curso.atoregulatoriocurso_set.filter(tipo=tipo, ad_referendum=True, ato_homologador__isnull=True).exists()
        ):
            raise forms.ValidationError('Existe um ato regulatório Ad Referendum deste tipo que ainda não foi homologado.')
        return tipo

    def clean(self):
        if self.instance.id_pafc is None:
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

            tipo_documento = self.cleaned_data.get('tipo_documento')
            if (arquivo_documento or url_documento) and not tipo_documento:
                raise forms.ValidationError('Informe o tipo de documento.')

            data = self.cleaned_data.get('data')
            if (arquivo_documento or url_documento) and not data:
                raise forms.ValidationError('Informe a data.')

            numero = self.cleaned_data.get('numero')
            if (arquivo_documento or url_documento) and not numero:
                raise forms.ValidationError('Informe o número.')

            orgao = self.cleaned_data.get('orgao')
            if (arquivo_documento or url_documento) and not orgao:
                raise forms.ValidationError('Informe o órgão.')

        return self.cleaned_data

    def processar(self):
        id_documento = self.cleaned_data.get('id_documento')
        arquivo_documento = self.cleaned_data.get('arquivo_documento')
        url_documento = self.cleaned_data.get('url_documento')
        self.instance.gerar_ato(id_documento, arquivo_documento, url_documento, self.ato_ad_referendum)


class TramitacaoProcessoEMECForm(forms.ModelFormPlus):
    class Meta:
        model = TramitacaoProcessoEMEC
        exclude = ('curso',)

    def __init__(self, *args, **kwargs):
        curso_id = kwargs.pop('curso_id', None)
        super().__init__(*args, **kwargs)
        if curso_id:
            self.instance.curso_id = curso_id


class ReplicacaoMatrizForm(forms.FormPlus):
    SUBMIT_LABEL = 'Replicar Matriz'
    descricao = forms.CharFieldPlus(width=500, label='Descrição', required=True)

    def __init__(self, matriz, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.matriz = matriz
        self.fields['descricao'].initial = f'{self.matriz.descricao} [REPLICADO]'

    def processar(self):
        self.matriz.replicar(self.cleaned_data['descricao'])
        return self.matriz


class ComponenteCurricularForm(forms.ModelFormPlus):
    periodo_letivo = forms.ChoiceField(required=False)
    matriz = forms.ModelChoiceField(queryset=Matriz.objects, widget=forms.HiddenInput())
    componente = forms.ModelChoiceFieldPlus(Componente.objects)
    componente_curricular_associado = forms.ModelChoiceField(
        queryset=ComponenteCurricular.objects,
        widget=AutocompleteWidget(search_fields=ComponenteCurricular.SEARCH_FIELDS),
        label='Componente Associado',
        required=False,
        help_text='Caso a nota desse componente não precise ser lançada no sistema em virtude de estar associado a um outro, informe aqui o componente cuja nota será registrada através de um diário, aproveitamento de estudo ou certificação do conhecimento.',
    )

    # Atributos para CH decimal de componentes
    ch_presencial_decimal = forms.DecimalFieldPlus(label='Teórica', required=False, min_value=0, help_text='Hora-Relógio')
    ch_pratica_decimal = forms.DecimalFieldPlus(label='Prática', required=False, min_value=0, help_text='Hora-Relógio')
    ch_pcc_decimal = forms.DecimalFieldPlus(label='Prática como Componente Curricular', required=False, min_value=0, help_text='Hora-Relógio')
    ch_visita_tecnica_decimal = forms.DecimalFieldPlus(label='Visita Técnica/Aula de Campo', required=False, min_value=0, help_text='Hora-Relógio')
    ch_extensao_decimal = forms.DecimalFieldPlus(label='Extensão', required=False, min_value=0, help_text='Hora-Relógio')
    ch_projeto_integrador_decimal = forms.DecimalFieldPlus(label='Carga Horária', required=False, min_value=0, help_text='Hora-Relógio')

    SUBMIT_LABEL = 'Vincular Componente'
    EXTRA_BUTTONS = [{'name': 'continuar', 'value': 'Vincular Componente e continuar vinculando'}]

    field_dados_gerais = (
        'Dados gerais',
        {
            'fields': (
                'matriz',
                'componente',
                'classificacao_complementar',
                ('optativo', 'pode_fechar_pendencia'),
                ('periodo_letivo', 'tipo'),
                ('qtd_avaliacoes', 'nucleo'),
                ('ch_semanal_1s', 'ch_semanal_2s'),
                ('avaliacao_por_conceito', 'is_dinamico', 'segundo_semestre'),
            )
        },
    )
    field_ch = ('Carga Horária', {'fields': (('ch_presencial', 'ch_pratica'), ('ch_pcc', 'ch_visita_tecnica'), 'ch_extensao')})
    field_ch_decimal = (
        'Carga Horária',
        {'fields': (('ch_presencial_decimal', 'ch_pratica_decimal'), ('ch_pcc_decimal', 'ch_visita_tecnica_decimal'), 'ch_extensao_decimal')},
    )

    class Meta:
        model = ComponenteCurricular
        if settings.COMPONENTE_CH_DECIMAL:
            exclude = ('pre_requisitos', 'co_requisitos', 'ch_presencial', 'ch_pratica', 'ch_pcc', 'ch_visita_tecnica', 'ch_extensao')
        else:
            exclude = (
                'pre_requisitos',
                'co_requisitos',
            )

    class Media:
        js = ('/static/edu/js/ComponenteCurricularForm.js',)

    def __init__(self, matriz, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if settings.COMPONENTE_CH_DECIMAL:
            self.fields['ch_presencial_decimal'].required = True
            self.fields['ch_pratica_decimal'].required = True
            self.fields['ch_pcc_decimal'].required = True
            self.fields['ch_visita_tecnica_decimal'].required = True
            self.fields['ch_extensao_decimal'].required = True

        if self.instance.id:
            self.fields['componentes_associados_projeto_integrador'].queryset = self.instance.matriz.componentecurricular_set.exclude(
                pk=self.instance.id
            )
        else:
            self.fields['componentes_associados_projeto_integrador'].queryset = ComponenteCurricular.objects.none()

        # contrução dos fieldsets
        self.fieldsets = [self.field_dados_gerais]
        self.fieldsets.append(('Estágio Docente', {'fields': ('is_seminario_estagio_docente', 'tipo_estagio_docente')}))
        if settings.COMPONENTE_CH_DECIMAL:
            self.fieldsets.append(self.field_ch_decimal)
            if self.instance.pk:
                self.initial['ch_presencial_decimal'] = Decimal(self.instance.ch_presencial / 100).quantize(Decimal('0.00'))
                self.initial['ch_pratica_decimal'] = Decimal(self.instance.ch_pratica / 100).quantize(Decimal('0.00'))
                self.initial['ch_pcc_decimal'] = Decimal(self.instance.ch_pcc / 100).quantize(Decimal('0.00'))
                self.initial['ch_visita_tecnica_decimal'] = Decimal(self.instance.ch_visita_tecnica / 100).quantize(Decimal('0.00'))
                self.initial['ch_extensao_decimal'] = Decimal(self.instance.ch_extensao / 100).quantize(Decimal('0.00'))
                self.initial['ch_projeto_integrador_decimal'] = Decimal(self.instance.ch_projeto_integrador / 100).quantize(Decimal('0.00'))
            else:
                self.initial['ch_presencial_decimal'] = 0
                self.initial['ch_pratica_decimal'] = 0
                self.initial['ch_pcc_decimal'] = 0
                self.initial['ch_visita_tecnica_decimal'] = 0
                self.initial['ch_extensao_decimal'] = 0
                self.initial['ch_projeto_integrador_decimal'] = 0
        else:
            self.fieldsets.append(self.field_ch)
            self.fields['ch_pratica'].initial = 0
            self.fields['ch_presencial'].initial = 0
        self.fieldsets.append(
            (
                'Aula à Distância (EAD)',
                {
                    'fields': (
                        'qtd_aulas_ead',
                        'percentual_maximo_ead',
                    )
                },
            )
        )
        self.fieldsets.append(('Regime Modular', {'fields': ('tipo_modulo',)}))
        self.fieldsets.append(('Associação', {'fields': ('componente_curricular_associado',)}))
        self.fieldsets.append(('Plano de Ensino', {'fields': ('ementa',)}))
        self.matriz = matriz
        if self.matriz.ch_projeto_integrador:
            self.fields['modalidade_pratica_profissional_projeto_integrador'].queryset = self.fields[
                'modalidade_pratica_profissional_projeto_integrador'
            ].queryset.filter(id__in=ModalidadePraticaProfissional.get_ids_modalidades_projeto_integrador())
            self.fieldsets.append(
                (
                    'Projeto Integrador',
                    {
                        'fields': (
                            'ch_projeto_integrador',
                            'modalidade_pratica_profissional_projeto_integrador',
                            'componentes_associados_projeto_integrador',
                        )
                    },
                )
            )

        self.fields['componente'].queryset = self.fields['componente'].queryset.filter(nivel_ensino=self.matriz.nivel_ensino)
        self.fields['periodo_letivo'].choices = [['', '-----']] + [[x, x] for x in range(1, self.matriz.qtd_periodos_letivos + 1)]
        self.fields['componente_curricular_associado'].queryset = self.fields['componente_curricular_associado'].queryset.filter(matriz=self.matriz)
        self.fields['matriz'].initial = self.matriz.pk
        if not ClassificacaoComplementarComponenteCurricular.objects.exists():
            self.fields['classificacao_complementar'].widget = forms.HiddenInput()
        if matriz.is_regime_modular() and matriz.estrutura.componente_sem_periodo:
            self.fields['periodo_letivo'].widget = forms.HiddenInput()
            self.initial['periodo_letivo'] = ''
            self.fields['optativo'].widget = forms.HiddenInput()
            self.initial['optativo'] = True
        else:
            self.fields['tipo_modulo'].widget = forms.HiddenInput()

    def clean_avaliacao_por_conceito(self):
        avaliacao_por_conceito = self.cleaned_data.get('avaliacao_por_conceito')
        if avaliacao_por_conceito and not self.matriz.estrutura.representacaoconceitual_set.exists():
            raise forms.ValidationError(
                'Não é possível vincular componente por conceito em matrizes cuja estrutura de curso não possua representação conceitual cadastrada.'
            )
        return avaliacao_por_conceito

    def clean_periodo_letivo(self):
        if self.cleaned_data.get('periodo_letivo') and self.data.get('optativo'):
            raise forms.ValidationError('Componentes Optativos não devem possuir um período letivo.')
        if not self.cleaned_data.get('periodo_letivo') and not self.data.get('optativo'):
            raise forms.ValidationError('Componentes Obrigatórios devem possuir um período letivo.')
        return self.cleaned_data['periodo_letivo'] or None

    def clean_ch_extensao(self):
        if self.cleaned_data.get('tipo') == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO and not self.matriz.ch_componentes_extensao:
            raise forms.ValidationError(
                'Só é possível vincular componente de atividade de extensão em matrizes que requer carga horária desse tipo de componente.'
            )
        return self.cleaned_data['ch_extensao']

    def clean_componente(self):
        qs = ComponenteCurricular.objects.filter(matriz=self.matriz, componente=self.cleaned_data['componente'])
        if self.instance.pk:
            qs = qs.exclude(id=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Componente já vinculado a esta matriz.')
        return self.cleaned_data['componente']

    def clean_componente_curricular_associado(self):
        cc_associado = self.cleaned_data['componente_curricular_associado']
        if self.instance.pk and cc_associado:
            if self.instance.pk == cc_associado.id:
                raise forms.ValidationError('Não é permitido associar um Componente Curricular a si mesmo.')
            if Diario.objects.filter(turma__matriz=self.matriz, componente_curricular=cc_associado).exists():
                raise forms.ValidationError('Não é possível associar componente, pois ele já está vinculado a um ou mais diários desta matriz.')
        return cc_associado

    def clean_tipo(self):
        if self.cleaned_data['tipo'] == ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL and self.cleaned_data['matriz'].ch_pratica_profissional <= 0:
            raise forms.ValidationError(
                'Não foi possível vincular o componente, pois na matriz não foi informada a carga horária de prática profissional.'
            )
        return self.cleaned_data['tipo']

    def clean_tipo_modulo(self):
        if self.cleaned_data['matriz'].is_regime_modular() and not self.cleaned_data['tipo_modulo']:
            raise forms.ValidationError('Este campo é obrigatório quando a estrutura de curso da matriz é modular.')
        return self.cleaned_data['tipo_modulo']

    def clean_ementa(self):
        matriz = self.cleaned_data['matriz']
        ementa = self.cleaned_data['ementa']
        if (
            not ementa
            and CursoCampus.objects.filter(
                plano_ensino=True,
                matrizes__in=[
                    matriz,
                ],
            ).exists()
        ):
            raise forms.ValidationError(
                'Necessário informar a ementa do componente curricular pois há cursos vinculados a esta matriz que exigem o cadastro do plano de ensino.'
            )
        return ementa

    def clean_ch_projeto_integrador(self):
        ch_projeto_integrador = self.cleaned_data.get('ch_projeto_integrador')
        if ch_projeto_integrador:
            if not self.matriz.ch_projeto_integrador:
                raise forms.ValidationError('Não está previsto projeto integrador para essa matriz.')
            ch_definida = self.matriz.get_ch_projeto_integrador_definida(self.instance)
            if ch_projeto_integrador + ch_definida > self.matriz.ch_projeto_integrador:
                raise forms.ValidationError(
                    f'A matriz já definiu {ch_definida} horas de projeto integrador em um total de {self.matriz.ch_projeto_integrador} horas. Ao definir mais {ch_projeto_integrador} o limite será ultrapassado.'
                )
        return ch_projeto_integrador

    def clean_ch_semanal_1s(self):
        ch_semanal_1s = self.cleaned_data.get('ch_semanal_1s')
        componente = self.cleaned_data.get('componente')
        if componente and ch_semanal_1s and ch_semanal_1s > componente.ch_qtd_creditos:
            raise forms.ValidationError(
                f'A CH semanal do primeiro semestre não pode ser maior que a quantidade de créditos ({componente.ch_qtd_creditos}) do componentes.'
            )
        return ch_semanal_1s

    def clean_ch_semanal_2s(self):
        ch_semanal_2s = self.cleaned_data.get('ch_semanal_2s')
        componente = self.cleaned_data.get('componente')
        if componente and ch_semanal_2s and ch_semanal_2s > componente.ch_qtd_creditos:
            raise forms.ValidationError(
                f'A CH semanal do primeiro semestre não pode ser maior que a quantidade de créditos ({componente.ch_qtd_creditos}) do componentes.'
            )
        return ch_semanal_2s

    def clean(self):
        if self.instance.pk:
            cc_salvo = ComponenteCurricular.objects.get(pk=self.instance.pk)
            periodo_letivo = self.cleaned_data.get('periodo_letivo')
            if periodo_letivo and int(periodo_letivo) != cc_salvo.periodo_letivo and (cc_salvo.co_requisitos.all() or cc_salvo.pre_requisitos.all()):
                raise forms.ValidationError('Não é possível alterar o período do componente na matriz, pois ele possui pré/co-requisitos.')
        if self.cleaned_data.get('segundo_semestre') and self.cleaned_data.get('qtd_avaliacoes') != 2:
            raise forms.ValidationError('Componentes semestrais devem ter apenas 2 avaliações.')
        if self.cleaned_data.get('qtd_avaliacoes') == 4 and (
            self.cleaned_data.get('ch_semanal_1s') is None or self.cleaned_data.get('ch_semanal_2s') is None
        ):
            raise forms.ValidationError('Informe a CH semanal para o primeiro e segundo semestre deste componente curricular.')

        if self.cleaned_data.get('qtd_aulas_ead') and self.cleaned_data.get('percentual_maximo_ead'):
            raise forms.ValidationError('Informe apenas um dos campos "Quantidade de horas/aulas EAD" ou "Percentual máximo EAD".')

        if settings.COMPONENTE_CH_DECIMAL:
            ch_presencial_decimal = self.cleaned_data.get('ch_presencial_decimal')
            ch_pratica_decimal = self.cleaned_data.get('ch_pratica_decimal')
            ch_pcc_decimal = self.cleaned_data.get('ch_pcc_decimal')
            ch_visita_tecnica_decimal = self.cleaned_data.get('ch_visita_tecnica_decimal')
            ch_extensao_decimal = self.cleaned_data.get('ch_extensao_decimal')
            self.instance.ch_presencial = int(ch_presencial_decimal * 100)
            self.instance.ch_pratica = int(ch_pratica_decimal * 100)
            self.instance.ch_pcc = int(ch_pcc_decimal * 100)
            self.instance.ch_visita_tecnica = int(ch_visita_tecnica_decimal * 100)
            self.instance.ch_extensao = int(ch_extensao_decimal * 100)

        return self.cleaned_data

    def processar(self):
        qtd_avaliacoes = self.cleaned_data['qtd_avaliacoes']
        componente = self.cleaned_data['componente']
        if qtd_avaliacoes:
            if qtd_avaliacoes == 2:
                segundo_semestre = self.cleaned_data['segundo_semestre']
                if segundo_semestre:
                    self.instance.ch_semanal_2s = componente.ch_qtd_creditos
                else:
                    self.instance.ch_semanal_1s = componente.ch_qtd_creditos
            elif qtd_avaliacoes != 4:
                self.instance.ch_semanal_1s = componente.ch_qtd_creditos
                self.instance.ch_semanal_2s = componente.ch_qtd_creditos
        self.instance.save()

        for cc in self.cleaned_data.get('componentes_associados_projeto_integrador') or ():
            self.instance.componentes_associados_projeto_integrador.add(cc)


class RequisitosComponenteCurricularForm(forms.ModelForm):
    SUBMIT_LABEL = 'Salvar'

    pre_requisitos = forms.MultipleModelChoiceField(
        ComponenteCurricular.objects, required=False, label='', widget=RenderableSelectMultiple('widgets/componentes_widget.html')
    )
    co_requisitos = forms.MultipleModelChoiceField(
        ComponenteCurricular.objects, required=False, label='', widget=RenderableSelectMultiple('widgets/componentes_widget.html')
    )
    componente_curricular_associado = forms.ModelChoiceField(
        queryset=ComponenteCurricular.objects,
        widget=AutocompleteWidget(search_fields=ComponenteCurricular.SEARCH_FIELDS),
        label='Componente Associado',
        required=False,
        help_text='Caso a nota desse componente não precise ser lançada no sistema em virtude de estar associado a um outro, informe aqui o componente cuja nota será registrada através de um diário, aproveitamento de estudo ou certificação do conhecimento.',
    )

    class Meta:
        model = ComponenteCurricular
        fields = ('pre_requisitos', 'co_requisitos', 'componente_curricular_associado')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.periodo_letivo:
            self.fields['pre_requisitos'].queryset = ComponenteCurricular.objects.filter(
                periodo_letivo__lt=self.instance.periodo_letivo, matriz=self.instance.matriz
            )
            self.fields['co_requisitos'].queryset = ComponenteCurricular.objects.filter(
                periodo_letivo__lte=self.instance.periodo_letivo, matriz=self.instance.matriz
            ).exclude(id=self.instance.id)
        else:
            qs = ComponenteCurricular.objects.filter(matriz=self.instance.matriz).exclude(id=self.instance.id)
            self.fields['pre_requisitos'].queryset = qs
            self.fields['co_requisitos'].queryset = qs

        self.fields['componente_curricular_associado'].queryset = self.fields['componente_curricular_associado'].queryset.filter(
            matriz=self.instance.matriz
        )

    fieldsets = (
        ('Pré-requisitos', {'fields': (('pre_requisitos'),)}),
        ('Co-requisitos', {'fields': (('co_requisitos'),)}),
        ('Componente Associado', {'fields': (('componente_curricular_associado'),)}),
    )


class RotuloModuloForm(forms.ModelFormPlus):
    class Meta:
        model = RotuloModulo
        exclude = ()
        fields = ('matriz', 'tipo_modulo', 'descricao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'matriz' in self.request.GET:
            self.fields['matriz'].initial = self.request.GET['matriz']
            self.fields['matriz'].widget = forms.HiddenInput()


class MatrizCursoForm(forms.ModelFormPlus):
    curso_campus = forms.ModelChoiceField(queryset=CursoCampus.objects, widget=forms.HiddenInput())
    matriz = forms.ModelChoiceField(
        queryset=Matriz.objects, widget=AutocompleteWidget(search_fields=Matriz.SEARCH_FIELDS), label='Matriz', required=True
    )

    class Meta:
        model = MatrizCurso
        exclude = ()

    fieldsets = (('Dados gerais', {'fields': ('curso_campus', 'matriz')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['curso_campus'].queryset = CursoCampus.locals.exclude(modalidade_id=Modalidade.FIC_MENOS)

    def clean(self):
        cleaned_data = super().clean()
        curso = cleaned_data.get('curso_campus')
        if curso and curso.is_minicurso():
            raise forms.ValidationError('Cursos da modalidade FIC- (Minicurso) não podem possuir matriz curricular.')
        return cleaned_data

    def clean_matriz(self):
        matriz = self.cleaned_data['matriz']
        curso = self.cleaned_data['curso_campus']
        if MatrizCurso.locals.filter(matriz=matriz, curso_campus=curso).exclude(pk=self.instance.pk or 0).exists():
            raise forms.ValidationError(f'A matriz {matriz} já está vinculada ao curso {curso}.')
        if matriz.is_regime_modular() and curso.periodicidade != CursoCampus.PERIODICIDADE_LIVRE:
            raise forms.ValidationError('Matrizes de estrutura modular podem ser vinculadas apenas a cursos de periodicidade livre.')
        return matriz


class ComponenteForm(forms.ModelFormPlus):
    ch_hora_relogio_decimal = forms.DecimalFieldPlus(label='Hora/relógio', required=False, min_value=0)

    class Meta:
        model = Componente
        exclude = ('sigla',)

    class Media:
        js = ('/static/edu/js/ComponenteForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.get_planodisciplina() is None:
            situacoes = [SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO]
            qs_componente_curricular = ComponenteCurricular.objects.filter(componente_id=self.instance.pk or 0)
            # desabilita a edição da carga horária caso já exista algum aluno formado
            editar_matriz_alunos_concluidos = Configuracao.get_valor_por_chave('edu', 'editar_matriz_alunos_concluidos')
            md = (
                MatriculaDiario.objects.filter(matricula_periodo__aluno__situacao__in=situacoes)
                .filter(diario__componente_curricular__componente_id=self.instance.pk or 0)
                .exists()
            )
            mdr = (
                MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno__situacao__in=situacoes)
                .filter(equivalencia_componente__componente_id=self.instance.pk or 0)
                .exists()
            )
            cc = (
                CertificacaoConhecimento.objects.filter(matricula_periodo__aluno__situacao__in=situacoes)
                .filter(componente_curricular__componente_id=self.instance.pk or 0)
                .exists()
            )
            ae = (
                AproveitamentoEstudo.objects.filter(matricula_periodo__aluno__situacao__in=situacoes)
                .filter(componente_curricular__componente_id=self.instance.pk or 0)
                .exists()
            )
            ac = (
                AproveitamentoComponente.objects.filter(matricula_periodo__aluno__situacao__in=situacoes)
                .filter(componente_curricular__componente_id=self.instance.pk or 0)
                .exists()
            )
            rh = (
                RegistroHistorico.objects.filter(matricula_periodo__aluno__situacao__in=situacoes)
                .filter(componente_id=self.instance.pk or 0)
                .exists()
            )
            if self.instance.pk and not editar_matriz_alunos_concluidos and (md or mdr or cc or ae or ac or rh):
                if settings.COMPONENTE_CH_DECIMAL:
                    self.fields['ch_hora_relogio_decimal'].widget.attrs.update(readonly='readonly')
                    self.fields[
                        'ch_hora_relogio_decimal'
                    ].help_text = 'Impossível editar este campo. Componente já vinculado a uma matriz com aluno formado.'
                else:
                    self.fields['ch_hora_relogio'].widget.attrs.update(readonly='readonly')
                    self.fields['ch_hora_relogio'].help_text = 'Impossível editar este campo. Componente já vinculado a uma matriz com aluno formado.'
                self.fields['ch_hora_aula'].widget.attrs.update(readonly='readonly')
                self.fields['ch_hora_aula'].help_text = 'Impossível editar este campo. Componente já vinculado a uma matriz com aluno formado.'
                self.fields['ch_qtd_creditos'].widget.attrs.update(readonly='readonly')
                self.fields['ch_qtd_creditos'].help_text = 'Impossível editar este campo. Componente já vinculado a uma matriz com aluno formado.'
            else:
                self.fields[
                    'ch_hora_aula'
                ].help_text = 'Esta carga horária não pode ser 0 e não poderá ser editada caso este componente já esteja vinculado a uma matriz que possua um aluno formado.'
                help_ch_hora_relogio = 'Esta carga horária não pode ser 0 e não poderá ser editada caso este componente já esteja vinculado a uma matriz que possua um aluno formado.'
                if qs_componente_curricular.filter(ch_pratica__gt=0).exists():
                    help_ch_hora_relogio = mark_safe(
                        f'<strong>Atenção! Este componente já está vinculado com carga horária prática a uma matriz. Não será possível atualizar automaticamente os campos Carga Horária Teórica e Prática do componente na matriz.</strong><br/>{help_ch_hora_relogio}'
                    )
                if settings.COMPONENTE_CH_DECIMAL:
                    self.fields['ch_hora_relogio_decimal'].help_text = help_ch_hora_relogio
                else:
                    self.fields['ch_hora_relogio'].help_text = help_ch_hora_relogio

            if self.instance.pk:
                if settings.COMPONENTE_CH_DECIMAL:
                    self.initial['ch_hora_relogio_decimal'] = Decimal(self.instance.ch_hora_relogio / 100).quantize(Decimal('0.00'))
                    self.initial['ch_hora_aula'] = int(self.instance.ch_hora_aula / 100)
            else:
                diretoria = Diretoria.objects.filter(setor__sigla=Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')).only('id').first()
                if diretoria:
                    self.initial['diretoria'] = diretoria.id
        if settings.COMPONENTE_CH_DECIMAL:
            self.fields['ch_hora_relogio_decimal'].required = True

    def save(self, *args, **kwargs):
        if settings.COMPONENTE_CH_DECIMAL:
            ch_hora_relogio_decimal = self.cleaned_data.get('ch_hora_relogio_decimal')
            self.instance.ch_hora_relogio = int(ch_hora_relogio_decimal * 100)
            self.instance.ch_hora_aula = self.cleaned_data.get('ch_hora_aula') * 100

        componente = super().save(*args, **kwargs)
        if self.instance.get_planodisciplina() is None and componente.pk:
            ComponenteCurricular.objects.filter(componente=componente, ch_pratica=0).update(ch_presencial=componente.ch_hora_relogio)

        return componente


class CursoCampusForm(forms.ModelFormPlus):
    titulo_certificado_masculino = forms.CharField(label='Masculino', required=True)
    titulo_certificado_feminino = forms.CharFieldPlus(label='Feminino', required=True)

    curso_tecnico = forms.ModelChoiceFieldPlus(
        CursoTecnico.objects,
        label='Curso técnico',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoTecnico.SEARCH_FIELDS, form_filters=[('eixo', 'eixo_tecnologico__in')]),
    )

    class Meta:
        model = CursoCampus
        exclude = ()

    class Media:
        js = ('/static/edu/js/CursoCampusForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coordenador'].queryset = Vinculo.objects.funcionarios().filter(ativo=True)
        if 'modalidade' in self.fields:
            self.fields['modalidade'].queryset = self.fields['modalidade'].queryset.exclude(id=Modalidade.FIC_MENOS)
        if self.instance.id and not self.instance.cursocampus_set.exists():
            self.fields['mesmo_curso'].queryset = CursoCampus.objects.filter(
                modalidade_id=self.instance.modalidade_id, diretoria_id=self.instance.diretoria_id
            ).exclude(id=self.instance.id)
        else:
            self.fields['mesmo_curso'].queryset = CursoCampus.objects.none()
            self.fields['mesmo_curso'].widget = forms.HiddenInput()
        self.fields['justificativa_dispensa_ingressante'].queryset = JustificativaDispensaENADE.objects.filter(ativo=True)

    def clean_modalidade(self):
        mesmo_curso = self.cleaned_data.get('mesmo_curso')
        modalidade = self.cleaned_data.get('modalidade')
        if modalidade and modalidade.pk == Modalidade.FIC_MENOS:
            raise forms.ValidationError('A modalidade FIC- é exclusiva de Minicursos e não pode ser selecionada em cursos regulares.')
        if mesmo_curso is None:
            if modalidade.pk in [
                Modalidade.TECNOLOGIA,
                Modalidade.FIC,
                Modalidade.INTEGRADO,
                Modalidade.INTEGRADO_EJA,
                Modalidade.FIC_INTEGRADO_EJA,
                Modalidade.CONCOMITANTE,
                Modalidade.SUBSEQUENTE,
            ]:
                if 'eixo' not in self.data or not self.data['eixo']:
                    raise forms.ValidationError('O campo "Eixo tecnológico" é obrigatório para cursos tecnológicos e FIC.')
            elif modalidade.pk in [Modalidade.ESPECIALIZACAO, Modalidade.MESTRADO, Modalidade.DOUTORADO]:
                if 'area_capes' not in self.data or not self.data['area_capes']:
                    raise forms.ValidationError('O campo "Área capes" é obrigatório para cursos de pós-graduação.')
            else:
                if 'area' not in self.data or not self.data['area']:
                    raise forms.ValidationError('O campo "Área de curso" é obrigatório para a modalidade selecionada.')
            if modalidade.pk in [
                Modalidade.CONCOMITANTE,
                Modalidade.SUBSEQUENTE,
            ]:
                if 'curso_tecnico' not in self.data or not self.data['curso_tecnico']:
                    raise forms.ValidationError('O campo "Curso técnico" é obrigatório para cursos concomitante e subsequente.')
        return modalidade

    def clean_area_curso_formacao_superior(self):
        area_curso_formacao_superior = self.cleaned_data.get('area_curso_formacao_superior')
        modalidade = self.cleaned_data.get('modalidade')
        if modalidade and modalidade.nivel_ensino_id == NivelEnsino.GRADUACAO and area_curso_formacao_superior is None:
            raise forms.ValidationError(f'Este campo é obrigatório para a modalidade {modalidade}.')
        elif modalidade and modalidade.nivel_ensino_id != NivelEnsino.GRADUACAO and area_curso_formacao_superior:
            raise forms.ValidationError(f'Este campo não pode ser preenchido para a modalidade {modalidade}.')
        return area_curso_formacao_superior

    def clean_quantidade_vagas(self):
        quantidade_vagas = self.cleaned_data.get('quantidade_vagas')
        mesmo_curso = self.cleaned_data.get('mesmo_curso')
        modalidade_id = int(self.data.get('modalidade', 0))
        if mesmo_curso is None and modalidade_id != Modalidade.FIC and not quantidade_vagas:
            raise forms.ValidationError('Informe a quantidade de vagas anuais autorizadas para este curso.')
        return quantidade_vagas

    def clean_justificativa_dispensa_ingressante(self):
        exige_enade = self.cleaned_data.get('exige_enade')
        justificativa_dispensa_ingressante = self.cleaned_data.get('justificativa_dispensa_ingressante')
        if not exige_enade and justificativa_dispensa_ingressante:
            raise forms.ValidationError('Este campo deve ser preenchido apenas para cursos que exigem o ENADE.')
        return justificativa_dispensa_ingressante

    def clean_assinatura_eletronica(self):
        modalidade_id = int(self.data.get('modalidade', 0))
        assinatura_eletronica = self.cleaned_data['assinatura_eletronica']
        if (
            assinatura_eletronica
            and modalidade_id
            and modalidade_id
            not in (
                Modalidade.FIC,
                Modalidade.INTEGRADO,
                Modalidade.INTEGRADO_EJA,
                Modalidade.FIC_INTEGRADO_EJA,
                Modalidade.SUBSEQUENTE,
                Modalidade.CONCOMITANTE,
                Modalidade.ESPECIALIZACAO,
                Modalidade.MESTRADO,
                Modalidade.DOUTORADO,
                Modalidade.APERFEICOAMENTO,
                Modalidade.PROEJA_FIC_FUNDAMENTAL,
                Modalidade.ENSINO_MEDIO,
            )
        ):
            raise forms.ValidationError('Apenas cursos FIC, técnicos e de pós-graduação podem ter certificados assinados eletronicamente')
        return assinatura_eletronica

    @transaction.atomic
    def save(self, *args, **kwargs):
        mesmo_curso = self.cleaned_data.get('mesmo_curso')
        if mesmo_curso:
            self.instance.codigo_censup = mesmo_curso.codigo_censup
            self.instance.codigo_emec = mesmo_curso.codigo_emec
            self.instance.codigo_sistec = mesmo_curso.codigo_sistec
            self.instance.codigo_educacenso = mesmo_curso.codigo_educacenso
            self.instance.ciencia_sem_fronteira = mesmo_curso.ciencia_sem_fronteira
            self.instance.formacao_de_professores = mesmo_curso.formacao_de_professores
            self.instance.data_inicio = mesmo_curso.data_inicio
            self.instance.data_funcionamento = mesmo_curso.data_funcionamento
            self.instance.ano_letivo = mesmo_curso.ano_letivo
            self.instance.periodo_letivo = mesmo_curso.periodo_letivo
            self.instance.quantidade_vagas = mesmo_curso.quantidade_vagas
            self.instance.ativo = mesmo_curso.ativo
            self.instance.extinto = mesmo_curso.extinto
            self.instance.em_extincao = mesmo_curso.em_extincao
            self.instance.suspenso = mesmo_curso.suspenso
            self.instance.coordenador_id = mesmo_curso.coordenador_id
            self.instance.numero_portaria_coordenador = mesmo_curso.numero_portaria_coordenador
            self.instance.coordenador_2_id = mesmo_curso.coordenador_2_id
            self.instance.numero_portaria_coordenador_2 = mesmo_curso.numero_portaria_coordenador_2
            self.instance.area_id = mesmo_curso.area_id
            self.instance.eixo_id = mesmo_curso.eixo_id
            self.instance.curso_tecnico_id = mesmo_curso.curso_tecnico_id
            self.instance.area_capes_id = mesmo_curso.area_capes_id
            self.instance.periodicidade = mesmo_curso.periodicidade

        curso_campus = super().save(*args, **kwargs)
        curso_campus.processar_grupo_coordenadores()
        return curso_campus


class EstruturaCursoForm(forms.ModelFormPlus):
    tipo_avaliacao = forms.ChoiceField(label='Tipo de Avaliação', widget=forms.RadioSelect(), choices=EstruturaCurso.TIPO_AVALIACAO_CHOICES)
    criterio_avaliacao = forms.ChoiceField(
        label='Critério de Avaliação', widget=forms.RadioSelect(), choices=EstruturaCurso.CRITERIO_AVALIACAO_CHOICES
    )

    ira = forms.ChoiceField(label='Forma de Cálculo', widget=forms.RadioSelect(), choices=EstruturaCurso.IRA_CHOICES)

    class Meta:
        model = EstruturaCurso
        exclude = ()

    class Media:
        js = ('/static/edu/js/EstruturaCursoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.numero_max_certificacoes is None:
            self.initial.update(numero_max_certificacoes=4)
        if hasattr(settings, 'REPRESENTACAO_CONCEITUAL'):
            conceitos = ', '.join(settings.REPRESENTACAO_CONCEITUAL.keys())
            self.fields['conceito_minimo_aprovacao'].help_text = f'Valores permitidos: {conceitos}.'
        else:
            self.fields['criterio_avaliacao'].choices = [
                [EstruturaCurso.CRITERIO_AVALIACAO_NOTA, 'Nota'],
                [EstruturaCurso.CRITERIO_AVALIACAO_FREQUENCIA, 'Frequência'],
            ]

    def clean_reprovacao_por_falta_disciplina(self):
        reprovacao_por_falta_disciplina = self.cleaned_data.get('reprovacao_por_falta_disciplina')
        if not reprovacao_por_falta_disciplina and self.cleaned_data.get('tipo_avaliacao') == EstruturaCurso.TIPO_AVALIACAO_MODULAR:
            raise forms.ValidationError('Quando o tipo de avaliação for modular, a opção "Reprovação por Disciplina" deverá estar marcada.')
        return reprovacao_por_falta_disciplina


class BuscaMatrizForm(RedirectForm):
    matriz = forms.ModelChoiceFieldPlus(Matriz.objects, label='Código/Descrição', widget=AutocompleteWidget(search_fields=Matriz.SEARCH_FIELDS))

    def get_url(self):
        return self.cleaned_data['matriz'].get_absolute_url()


class EquivalenciaComponenteQAcademicoForm(forms.ModelFormPlus):
    componente = forms.ModelChoiceField(queryset=Componente.objects, widget=AutocompleteWidget(search_fields=Componente.SEARCH_FIELDS))

    class Meta:
        model = EquivalenciaComponenteQAcademico
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sigla'].widget.attrs.update(readonly='readonly')
        self.fields['descricao'].widget.attrs.update(readonly='readonly')
        self.fields['q_academico'].widget.attrs.update(readonly='readonly')
        self.fields['carga_horaria'].widget.attrs.update(readonly='readonly')


class ImportarAlunosAtivosForm(forms.FormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos())
    periodo_letivo = forms.ChoiceField(choices=PERIODO_LETIVO_CHOICES)
    arquivo = forms.FileFieldPlus(
        help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, e contendo a matrícula na primeira coluna.', required=False
    )
    matricula = forms.CharFieldPlus(required=False)

    def __init__(self, matriz_id, *args, **kwargs):
        self.matriz_id = matriz_id
        self.matriculas = []
        super().__init__(*args, **kwargs)

    def clean(self):
        """Valida e importa alunos ativos a partir de arquivo ou matrícula informada.

        Returns:
            dict: dados limpos do formulário.

        Raises:
            ValidationError: se nenhum arquivo ou matrícula for informado, ou se
                houver erros na importação.
        """
        import pandas as pd

        arquivo_up = self.cleaned_data.get('arquivo')
        matricula_up = self.cleaned_data.get('matricula')
        matriculas = []
        matriculas_validas = []
        if not arquivo_up and not matricula_up:
            raise forms.ValidationError('Preencha o campo arquivo ou o campo matrícula.')

        if matricula_up:
            matriculas.append(matricula_up)

        if arquivo_up:
            df = pd.read_excel(arquivo_up, header=None)
            for _index, row in df.iterrows():
                # testando se o fluxo da integração foi seguido corretamente
                matricula = row.iloc[0]
                try:
                    matricula = str(int(row.iloc[0]))
                except Exception:
                    raise forms.ValidationError(f'A matrícula ({matricula}) está incorreta.')

                matriculas.append(matricula)
        for matricula in matriculas:
            qs_aluno = Aluno.objects.filter(matricula=matricula)
            if qs_aluno.exists():
                aluno = qs_aluno[0]
                if not aluno.curso_campus.ativo:
                    raise forms.ValidationError(f'Aluno ({aluno.matricula}) com curso ({aluno.curso_campus}) não ativo.')

                qs_matrizcurso = MatrizCurso.objects.filter(curso_campus=aluno.curso_campus, matriz__id=self.matriz_id)
                if qs_matrizcurso.exists():
                    if not ComponenteCurricular.objects.filter(matriz=qs_matrizcurso[0].matriz).exists():
                        raise forms.ValidationError('A matriz escolhida não possui nenhum componente vinculado.')
                else:
                    raise forms.ValidationError(
                        f'Curso ({aluno.curso_campus}) do aluno ({aluno.matricula}) não possui nenhuma matriz ou a migração está sendo feita na matriz errada.'
                    )
            else:
                raise forms.ValidationError(f'Matrícula({matricula}) inexistente no SUAP.')
            matriculas_validas.append(matricula)

        self.matriculas = matriculas_validas

        if running_tests():
            dao = MockDAO()
        else:
            dao = DAO()

        self.erros = dao.importar_historico_resumo(
            self.matriculas, self.matriz_id, self.cleaned_data['ano_letivo'], int(self.cleaned_data['periodo_letivo'])
        )
        if self.erros:
            raise ValidationError('')
        else:
            return self.cleaned_data

    def processar(self, request):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = int(self.cleaned_data['periodo_letivo'])
        return tasks.migrar_alunos(self.matriculas, self.matriz_id, ano_letivo, periodo_letivo)


class MatrizForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'configuracao_creditos_especiais' in self.fields:
            self.fields['configuracao_creditos_especiais'].queryset = ConfiguracaoCreditosEspeciais.objects.filter(ativo=True)

    class Meta:
        model = Matriz
        exclude = ()

    def clean(self):
        if self.instance.get_matrizppc() is None:
            try:
                ch_complementares = int(self.cleaned_data.get('ch_atividades_complementares', 0))
                ch_aprofundamento = int(self.cleaned_data.get('ch_atividades_aprofundamento', 0))
            except Exception:
                raise forms.ValidationError('Cargas horárias inválidas.')

            configuracao_academica = self.cleaned_data.get('configuracao_atividade_academica')
            configuracao_aprofundamento = self.cleaned_data.get('configuracao_atividade_aprofundamento')

            if ch_complementares > 0 and not configuracao_academica:
                raise forms.ValidationError('Selecione a configuração de AACC. Existe carga horária de atividades complementares.')
            if ch_aprofundamento > 0 and not configuracao_aprofundamento:
                raise forms.ValidationError('Selecione a configuração de ATPA. Existe carga horária de atividades de aprofundamento.')

            if self.cleaned_data.get('exige_estagio') and not self.cleaned_data.get('ch_minima_estagio'):
                raise forms.ValidationError('Informe a Carga Horária Mínima de Estágio e Afins quando a opção Exige Estágio e Afins estiver marcada.')

        return self.cleaned_data


class ImportarComponentesForm(forms.FormPlus):
    planilha = forms.FileFieldPlus(
        required=True,
        help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, contendo as seguintes colunas: Descrição, Núcleo, Carga Horária - Relógio, Carga Horária - Aula, Qtd. de Créditos, Tipo do Componente e Nível de Ensino.',
    )

    def clean(self):
        """Valida e importa componentes curriculares a partir de planilha.

        Returns:
            dict: dados limpos do formulário.

        Raises:
            ValidationError: se a planilha estiver em formato inválido ou
                contiver dados inconsistentes.
        """
        import pandas as pd

        try:
            self.componentes = []
            planilha = self.cleaned_data['planilha'].file
            df = pd.read_excel(planilha, header=None)

            for _index, row in df.iterrows():
                descricao = str(row.iloc[0])
                nucleo = str(row.iloc[1])
                carga_horaria_relogio = int(row.iloc[2])
                carga_horaria_aula = int(row.iloc[3])
                qtd_creditos = int(row.iloc[4])
                tipo_componente = str(row.iloc[5])
                nivel_ensino = str(row.iloc[6])

                try:
                    componente = {
                        'descricao': f'{descricao} ({nucleo})',
                        'descricao_historico': descricao,
                        'ch_hora_relogio': carga_horaria_relogio,
                        'ch_hora_aula': carga_horaria_aula,
                        'ch_qtd_creditos': qtd_creditos,
                        'tipo': TipoComponente.objects.get(descricao=tipo_componente),
                        'nivel_ensino': NivelEnsino.objects.get(descricao=nivel_ensino),
                        'diretoria': Diretoria.objects.get(setor__sigla=utils.get_sigla_reitoria()),
                    }

                    self.componentes.append(componente)
                except TipoComponente.DoesNotExist:
                    raise ValidationError(f'O Tipo do Componente "{tipo_componente}" não foi encontrado.')
                except NivelEnsino.DoesNotExist:
                    raise ValidationError(f'O Nível de Ensino "{nivel_ensino}" não foi encontrado.')
        except Exception:
            raise ValidationError(
                'Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx, sem cabeçalho e se contém as seguintes colunas: Descrição, Núcleo, Carga Horária - Relógio, Carga Horária - Aula, Qtd. de Créditos, Tipo do Componente e Nível de Ensino.'
            )

        return self.cleaned_data

    def processar(self):
        for componente in self.componentes:
            Componente.objects.get_or_create(**componente)


class ImportarComponentesMatrizForm(forms.FormPlus):
    tipo_componente = forms.ModelChoiceField(TipoComponente.objects, required=True, label='Tipo dos Componentes')
    planilha = forms.FileFieldPlus(
        filetypes=[
            'xlsx',
        ],
        required=True,
    )

    def __init__(self, matriz, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.matriz = matriz
        self.componentes_curriculares = []
        self.dict_abreviaturas_componentes = {}
        self.componentes_com_pre_requisitos = {}
        self.componentes_com_correquisitos = {}

    def clean(self):
        """Valida e importa componentes curriculares de matriz a partir de planilha.

        Returns:
            dict: dados limpos do formulário.

        Raises:
            ValidationError: se a planilha estiver em formato inválido ou
                contiver dados inconsistentes.
        """
        import pandas as pd

        todos_os_pre_requisitos = set()
        todos_os_correquisitos = set()
        try:
            planilha = self.cleaned_data['planilha'].file
            df = pd.read_excel(planilha, header=None)

            nivel_ensino = self.matriz.nivel_ensino
            tipo_componente = self.cleaned_data['tipo_componente']
            componentes_duplicados = []

            for i, row in df.iloc[1:].iterrows():
                try:
                    periodo_letivo = int(row.iloc[0])
                    descricao = str(row.iloc[1])
                    observacao = str(row.iloc[2])
                    carga_horaria_relogio = int(row.iloc[3])
                    carga_horaria_aula = int(row.iloc[4])
                    qtd_creditos = int(row.iloc[5])
                    optativo = int(row.iloc[6])
                    nucleo = str(row.iloc[7])
                    qtd_avaliacoes = int(row.iloc[8])
                    tipo_componente_curricular_descricao = str(row.iloc[9])
                    avaliacao_por_conceito = int(row.iloc[10])
                    carga_horaria_pratica = int(row.iloc[11])
                    abreviatura = str(row.iloc[12])
                    ch_extensao = int(row.iloc[13])

                    col_pre_requisitos = row.iloc[14]
                    pre_requisitos = '' if pd.isna(col_pre_requisitos) else str(col_pre_requisitos)

                    col_co_requisitos = row.iloc[15]
                    co_requisitos = '' if pd.isna(col_co_requisitos) else str(col_co_requisitos)

                    col_segundo_semestre = row.iloc[16]
                    segundo_semestre = None if pd.isna(col_segundo_semestre) else int(col_segundo_semestre)

                    try:
                        col_ch_semanal_1s = row.iloc[17]
                        ch_semanal_1s = None if pd.isna(col_ch_semanal_1s) else int(col_ch_semanal_1s)
                    except Exception:
                        raise ValidationError(f'A coluna CH Semanal Semestre 1 da planilha possui um valor inválido na {i + 1}ª linha.')
                    try:
                        col_ch_semanal_2s = row.iloc[18]
                        ch_semanal_2s = None if pd.isna(col_ch_semanal_2s) else int(col_ch_semanal_2s)
                    except Exception:
                        raise ValidationError(f'A coluna CH Semanal Semestre 2 da planilha possui um valor inválido na {i + 1}ª linha.')

                    try:
                        col_modulo = row.iloc[19]
                        modulo = None if pd.isna(col_modulo) else int(col_modulo)
                        if self.matriz.is_regime_modular():
                            if modulo is None:
                                raise forms.ValidationError(f'Componente ({descricao}) não possui informação do módulo.')
                            if modulo > 12 or modulo < 1:
                                raise ValidationError(f'A coluna Módulo (1 a 12) da planilha possui um valor inválido na {i + 1}ª linha.')
                        else:
                            modulo = None
                    except Exception:
                        raise ValidationError(f'A coluna Módulo (1 a 12) da planilha possui um valor inválido na {i + 1}ª linha.')

                    try:
                        sigla_qacademico = str(row.iloc[20])
                    except Exception:
                        sigla_qacademico = None

                    ch_presencial = carga_horaria_relogio - carga_horaria_pratica

                    # validando periodo_letivo
                    if periodo_letivo < 1 and not optativo:
                        raise ValidationError(f'Componente ({descricao}) obrigatório com período letivo menor que 1.')
                    if periodo_letivo != 0 and optativo:
                        raise ValidationError(f'Componente ({descricao}) optativo com período letivo diferente de 0.')
                    if periodo_letivo > self.matriz.qtd_periodos_letivos:
                        raise ValidationError(
                            f'Componente ({descricao}) com período letivo maior que a quantidade de periodos letivos cadastrado na matriz.'
                        )

                    # validando descricao
                    if not descricao:
                        raise ValidationError('Componente sem descrição.')

                    # validando carga_horaria_relogio
                    if carga_horaria_relogio < 0:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária - Relógio menor que 0.')

                    # validando carga_horaria_aula
                    if carga_horaria_aula < 0:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária - Aula menor que 0.')

                    # validando qtd_creditos
                    if qtd_creditos < 0:
                        raise ValidationError(f'Componente({descricao}) com quantiade de créditos menor que 0.')

                    # validando carga_horaria_relogio e carga_horaria_aula e qtd_creditos
                    if carga_horaria_relogio > 0 and carga_horaria_aula < 1:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária - Relógio informada sem Carga Horária - Aula.')
                    if carga_horaria_aula > 0 and carga_horaria_relogio < 1:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária - Aula informada sem Carga Horária - Relógio.')

                    # validando optativo
                    if optativo not in [0, 1]:
                        raise ValidationError(f'Componente ({descricao}) com coluna Optativo diferente de 0 ou 1.')

                    # validando qtd de avaliações
                    if not (0 <= qtd_avaliacoes < 5):
                        raise ValidationError(f'A quantidade de avaliações do componente({descricao}) esta incorreta.')

                    # validando avaliacao_por_conceito
                    if avaliacao_por_conceito not in [0, 1]:
                        raise ValidationError(f'Componente({descricao}) com coluna Avaliação por Conceito diferente de 0 ou 1.')

                    # validando carga_horaria_pratica
                    if carga_horaria_pratica < 0:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária Prática menor que 0.')

                    # validando ch_presencial
                    if ch_presencial < 0:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária Prática maior que a Carga Horária - Relógio.')

                    # validando segundo_semestre
                    if segundo_semestre not in [0, 1]:
                        raise ValidationError(f'Componente({descricao}) com coluna Segundo Semestre diferente de 0 ou 1.')

                    # validando ch semanal
                    if ch_semanal_1s is not None and ch_semanal_1s < 0:
                        raise ValidationError(f'Componente({descricao}) com coluna CH Semanal Semestre 1 possui valor inválido.')
                    if ch_semanal_2s is not None and ch_semanal_2s < 0:
                        raise ValidationError(f'Componente({descricao}) com coluna CH Semanal Semestre 2 possui valor inválido.')

                    # validando tipo de componente curricular
                    tipo_componente_curricular = None
                    for tpc in ComponenteCurricular.TIPO_CHOICES:
                        if tpc[1] == tipo_componente_curricular_descricao:
                            tipo_componente_curricular = tpc[0]

                    if not tipo_componente_curricular:
                        raise ValidationError(f'O Tipo do Componente Curricular "{tipo_componente_curricular_descricao}" não foi encontrado.')

                    # validando ch_extensao
                    if ch_extensao < 0:
                        raise ValidationError(f'Componente({descricao}) com Carga Horária de Extensão menor que 0.')

                    # lendo pré-requisitos
                    if pre_requisitos.strip():
                        lista_pre_requisitos = [requisito.strip() for requisito in pre_requisitos.split(';') if requisito.strip()]
                        self.componentes_com_pre_requisitos.update({abreviatura: lista_pre_requisitos})
                        todos_os_pre_requisitos.update(lista_pre_requisitos)

                    # lendo co-requisitos
                    if co_requisitos.strip():
                        lista_correquisitos = [requisito.strip() for requisito in co_requisitos.split(';') if requisito.strip()]
                        self.componentes_com_correquisitos.update({abreviatura: lista_correquisitos})
                        todos_os_correquisitos.update(lista_correquisitos)

                    # recuperando componente único
                    chaves = {
                        'descricao': descricao,
                        'ch_hora_relogio': carga_horaria_relogio,
                        'ch_hora_aula': carga_horaria_aula,
                        'nivel_ensino': NivelEnsino.objects.get(descricao=nivel_ensino),
                        'observacao': observacao,
                    }
                    qs_componente = Componente.objects.filter(**chaves)
                    componente = None
                    if not qs_componente.exists():
                        # criando novo componente caso não exista
                        chaves2 = {
                            'descricao_historico': descricao,
                            'ch_qtd_creditos': qtd_creditos,
                            'tipo': TipoComponente.objects.get(descricao=tipo_componente),
                            'diretoria': Diretoria.objects.get(setor__sigla=utils.get_sigla_reitoria()),
                            'abreviatura': abreviatura,
                        }
                        chaves.update(chaves2)
                        if sigla_qacademico is not None:
                            chaves.update(sigla_qacademico=sigla_qacademico)
                        componente = Componente.objects.get_or_create(**chaves)[0]
                    elif qs_componente.count() == 1:
                        componente = qs_componente[0]
                        if componente.tipo != tipo_componente:
                            raise ValidationError(
                                f'O Componente Curricular encontrado "{componente}" é de um tipo diferente do informado na importação ({tipo_componente.descricao}).'
                            )
                    else:
                        componentes_duplicados.append(descricao)

                    if componente and not componentes_duplicados:
                        if ch_semanal_1s is None:
                            ch_semanal_1s = componente.ch_qtd_creditos
                            if qtd_avaliacoes == 4:
                                ch_semanal_1s = componente.ch_qtd_creditos // 2
                            elif qtd_avaliacoes == 2 and segundo_semestre:
                                ch_semanal_1s = None
                        if ch_semanal_2s is None:
                            ch_semanal_2s = componente.ch_qtd_creditos
                            if qtd_avaliacoes == 4:
                                ch_semanal_2s = componente.ch_qtd_creditos // 2
                            elif qtd_avaliacoes == 2 and not segundo_semestre:
                                ch_semanal_2s = None

                        if sigla_qacademico is not None:
                            componente.sigla_qacademico = sigla_qacademico
                        componente.save()

                        self.dict_abreviaturas_componentes.update({abreviatura: componente})

                        # vinculando o componente a matriz
                        componente_curricular = {
                            'matriz': self.matriz,
                            'componente': componente,
                            'optativo': optativo,
                            'periodo_letivo': periodo_letivo > 0 and periodo_letivo or None,
                            'tipo': tipo_componente_curricular,
                            'qtd_avaliacoes': qtd_avaliacoes,
                            'nucleo': Nucleo.objects.get(descricao=nucleo),
                            'avaliacao_por_conceito': avaliacao_por_conceito,
                            'ch_presencial': ch_presencial,
                            'ch_pratica': carga_horaria_pratica,
                            'ch_extensao': ch_extensao,
                            'segundo_semestre': segundo_semestre,
                            'ch_semanal_1s': ch_semanal_1s,
                            'ch_semanal_2s': ch_semanal_2s,
                            'tipo_modulo': modulo,
                        }

                        qs_componente_curricular = ComponenteCurricular.objects.filter(componente=componente, matriz=self.matriz)
                        if not qs_componente_curricular.exists():
                            self.componentes_curriculares.append(componente_curricular)

                except ValueError:
                    raise ValidationError(f'Alguma coluna da planilha possui o valor incorreto na {i + 1}ª linha.')
                except IndexError:
                    raise ValidationError('A planilha não contém todas as colunas esperadas.')
                except TipoComponente.DoesNotExist:
                    raise ValidationError(f'O Tipo do Componente "{tipo_componente}" não foi encontrado.')
                except NivelEnsino.DoesNotExist:
                    raise ValidationError(f'O Nível de Ensino "{nivel_ensino}" não foi encontrado.')
                except Nucleo.DoesNotExist:
                    raise ValidationError(f'O Núcleo "{nucleo}" não foi encontrado.')
            if componentes_duplicados:
                raise ValidationError(
                    f'Existe mais de um cadastro de componente para os seguintes dados informados na planilha: {componentes_duplicados}.'
                )

            # validando os pré-requisitos
            for pre_req in todos_os_pre_requisitos:
                qs_cc_pre_requisitos = ComponenteCurricular.objects.filter(matriz=self.matriz, componente__sigla=pre_req)
                if pre_req not in self.dict_abreviaturas_componentes and not qs_cc_pre_requisitos.exists():
                    raise ValidationError(
                        f'A componente "{pre_req}", indicada como pré-requisito, não foi encontrada nem na planilha, nem nos dados existentes da matriz.'
                    )

            # validando os co-requisitos
            for correq in todos_os_correquisitos:
                qs_cc_correquisitos = ComponenteCurricular.objects.filter(matriz=self.matriz, componente__sigla=correq)
                if correq not in self.dict_abreviaturas_componentes and not qs_cc_correquisitos.exists():
                    raise ValidationError(
                        f'A componente "{correq}", indicada como co-requisito, não foi encontrada nem na planilha, nem nos dados existentes da matriz.'
                    )

        except Exception as e:
            raise ValidationError(e)

        return self.cleaned_data

    def processar(self):
        for componente_curricular in self.componentes_curriculares:
            ComponenteCurricular.objects.get_or_create(**componente_curricular)

        # vinculando pré-requisitos
        for abreviatura_componente, abreviaturas_e_siglas_pre_requisitos in self.componentes_com_pre_requisitos.items():
            componente = self.dict_abreviaturas_componentes.get(abreviatura_componente)
            componente_curricular = ComponenteCurricular.objects.get(componente=componente, matriz=self.matriz)
            ids_pre_requisitos = [
                componente.id for componente in self.buscar_componentes_por_abreviaturas_e_siglas(abreviaturas_e_siglas_pre_requisitos)
            ]
            componente_curricular.pre_requisitos.add(*ids_pre_requisitos)

        # vinculando co-requisitos
        for abreviatura_componente, abreviaturas_e_siglas_correquisitos in self.componentes_com_correquisitos.items():
            componente = self.dict_abreviaturas_componentes.get(abreviatura_componente)
            componente_curricular = ComponenteCurricular.objects.get(componente=componente, matriz=self.matriz)
            ids_co_requisitos = [
                componente.id for componente in self.buscar_componentes_por_abreviaturas_e_siglas(abreviaturas_e_siglas_correquisitos)
            ]
            componente_curricular.co_requisitos.add(*ids_co_requisitos)

    def buscar_componentes_por_abreviaturas_e_siglas(self, abreviaturas_e_siglas):
        """
        Procura uma componente por abreviatura ou sigla. Abreviatura, se procurando na própria planilha. Sigla, se buscando no banco.
        A busca no banco só ocorrerá se a componente não for encontrada na própria planilha.

        :param list[str] abreviaturas_e_siglas: A lista de abreviaturas e/ou siglas de componentes a procurar.
        :return: uma lista com as componentes encontradas.
        :rtype: list[Componente]
        :raises ValidationError: se uma abreviatura ou sigla não corresponder a nenhuma componente.
        """

        lista_componentes = []
        for abreviatura_ou_sigla in abreviaturas_e_siglas:
            componente = self.dict_abreviaturas_componentes.get(abreviatura_ou_sigla)
            if componente:
                lista_componentes.append(ComponenteCurricular.objects.get(matriz=self.matriz, componente=componente))
            else:
                lista_componentes.append(ComponenteCurricular.objects.get(matriz=self.matriz, componente__sigla=abreviatura_ou_sigla))

        return lista_componentes


class EditarDiretoriaCurso(forms.ModelFormPlus):
    class Meta:
        model = CursoCampus
        fields = ('diretoria',)

    @transaction.atomic
    def processar(self):
        self.save()
        self.instance.processar_grupo_coordenadores()


class EditarAbreviaturaComponenteForm(forms.ModelForm):
    class Meta:
        model = Componente
        fields = ('abreviatura',)


class EditarLegislacaoForm(forms.ModelForm):
    class Meta:
        model = MatrizCurso
        fields = ('resolucao_criacao', 'resolucao_data', 'reconhecimento_texto', 'reconhecimento_data')

    fieldsets = (
        ('Ato Normativo', {'fields': ('resolucao_criacao', 'resolucao_data')}),
        ('Ato de Reconhecimento', {'fields': ('reconhecimento_texto', 'reconhecimento_data')}),
    )


class EquivalenciaComponenteMatrizFormset(forms.models.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.fields['matriz_origem'] = forms.ModelChoiceFieldPlus(
                Matriz.objects,
                label='Matriz A',
                required=True,
                widget=AutocompleteWidget(search_fields=Matriz.SEARCH_FIELDS, form_filters=[('tipo', 'componentecurricular__componente__tipo')]),
            )
            form.fields['matriz_destino'] = forms.ModelChoiceFieldPlus(
                Matriz.objects,
                label='Matriz B',
                required=True,
                widget=AutocompleteWidget(search_fields=Matriz.SEARCH_FIELDS, form_filters=[('tipo', 'componentecurricular__componente__tipo')]),
            )

    def clean(self):
        qs_componentes_origem = Componente.objects.filter(pk__in=self.data.getlist('componentes'))
        qs_componentes_destino = Componente.objects.filter(pk__in=self.data.getlist('equivalentes'))
        for form in self.forms:
            matriz_origem = form.cleaned_data.get('matriz_origem')
            if matriz_origem and not form.cleaned_data.get('DELETE'):
                for componente in qs_componentes_origem:
                    if not matriz_origem.componentecurricular_set.filter(componente=componente).exists():
                        raise forms.ValidationError(f'A matriz "{matriz_origem}" não possui o componente "{componente}".')
            matriz_destino = form.cleaned_data.get('matriz_destino')
            if matriz_destino and not form.cleaned_data.get('DELETE'):
                for componente in qs_componentes_destino:
                    if not matriz_destino.componentecurricular_set.filter(componente=componente).exists():
                        raise forms.ValidationError(f'A matriz "{matriz_destino}" não possui o componente "{componente}".')
            if 'matriz_origem' in form.cleaned_data and 'matriz_destino' in form.cleaned_data:
                matriz_origem = form.cleaned_data['matriz_origem'].id if form.cleaned_data['matriz_origem'] else None
                matriz_destino = form.cleaned_data['matriz_destino'].id if form.cleaned_data['matriz_destino'] else None
                form.instance.gerar_chaves(
                    list(self.data.getlist('componentes')), list(self.data.getlist('equivalentes')), matriz_origem, matriz_destino
                )
                qs1 = EquivalenciaComponenteMatriz.objects.filter(chave_unica_1=form.instance.chave_unica_1)
                qs2 = EquivalenciaComponenteMatriz.objects.filter(chave_unica_1=form.instance.chave_unica_2)
                if form.instance.id:
                    qs1 = qs1.exclude(pk=form.instance.id)
                    qs2 = qs2.exclude(pk=form.instance.id)
                e1 = qs1.first()
                e2 = qs2.first()
                if e1:
                    link = f'<a href="/edu/equivalenciacomponente/{e1.equivalencia_componente_id}/" target="_blank" rel="noopener">Acesse a equivalência</a>.'
                    raise forms.ValidationError(
                        mark_safe(
                            f'A equivalência de componente com identficador "{e1.equivalencia_componente_id}" possui um registro com os mesmos componentes com equivalência da matriz "{matriz_origem}" para "{matriz_destino}". {link}'
                        )
                    )
                if e2:
                    link = f'<a href="/edu/equivalenciacomponente/{e2.equivalencia_componente_id}/" target="_blank" rel="noopener">Acesse a equivalência</a>.'
                    raise forms.ValidationError(
                        mark_safe(
                            f'A equivalência de componente com identficador "{e2.equivalencia_componente_id}" possui um registro com os mesmos componentes com equivalência da matriz "{matriz_origem}" para "{matriz_destino}". {link}'
                        )
                    )


class ConfiguracaoCertificacaoParcialForm(forms.ModelFormPlus):
    fieldsets = (
        ('Dados gerais', {'fields': ('descricao', 'modalidade_certificacao', 'ch_componentes_optativos')}),
        (
            'Titulação',
            {
                'fields': (
                    'titulacao_masculino',
                    'titulacao_feminino',
                )
            },
        ),
    )

    class Meta:
        model = ConfiguracaoCertificacaoParcial
        exclude = ('matriz',)

    def __init__(self, *args, **kwargs):
        matriz_id = kwargs.pop('matriz_id', None)
        super().__init__(*args, **kwargs)

        if matriz_id:
            self.instance.matriz_id = matriz_id

    def clean_ch_componentes_optativos(self):
        ch_componentes_optativos = self.cleaned_data.get('ch_componentes_optativos')
        if (
            self.instance.id
            and not ch_componentes_optativos
            and self.instance.componentecurricularcertificacaoparcial_set.filter(componente_curricular__optativo=True).exists()
        ):
            raise forms.ValidationError('Informe a CH de componentes optativos exigidas para esta configuração de certificação parcial.')
        return ch_componentes_optativos

    def processar(self):
        self.save()


class VincularComponenteCurricularConfiguracaoCertificacaoParcialForm(forms.ModelFormPlus):
    class Meta:
        model = ComponenteCurricularCertificacaoParcial
        exclude = ('configuracao_certificacao_parcial',)

    def __init__(self, *args, **kwargs):
        configuracao_id = kwargs.pop('configuracao_id', None)
        super().__init__(*args, **kwargs)
        self.instance.configuracao_certificacao_parcial_id = configuracao_id
        self.fields['componente_curricular'].queryset = ComponenteCurricular.objects.filter(
            matriz_id=self.instance.configuracao_certificacao_parcial.matriz_id
        ).exclude(componentecurricularcertificacaoparcial__configuracao_certificacao_parcial_id=configuracao_id)

    def clean_componente_curricular(self):
        componente_curricular = self.cleaned_data.get('componente_curricular')
        if componente_curricular.optativo and self.instance.configuracao_certificacao_parcial.ch_componentes_optativos == 0:
            raise forms.ValidationError(
                'Este componente é optativo. Edite a CH de componentes optativos no cadastro desta configuração de certificação parcial.'
            )
        if ComponenteCurricularCertificacaoParcial.objects.filter(
            componente_curricular_id=componente_curricular.id, configuracao_certificacao_parcial_id=self.instance.configuracao_certificacao_parcial_id
        ).exists():
            raise forms.ValidationError('Este componente curricular já foi adicionado a esta configuração de certificação parcial.')
        return componente_curricular

    def processar(self):
        self.save()


class VincularModuloConfiguracaoCertificacaoParcialForm(forms.FormPlus):
    modulo = forms.ChoiceField(label='Módulo', choices=ComponenteCurricular.TIPO_MODULO_CHOICES)

    def __init__(self, *args, **kwargs):
        self.ccp = kwargs.pop('ccp', None)
        super().__init__(*args, **kwargs)

    def clean_modulo(self):
        modulo = self.cleaned_data.get('modulo')
        if not ComponenteCurricular.objects.filter(matriz_id=self.ccp.matriz_id, tipo_modulo=modulo).exists():
            raise forms.ValidationError('Este módulo não possui componente curricular vinculado.')

        if ComponenteCurricularCertificacaoParcial.objects.filter(
            configuracao_certificacao_parcial_id=self.ccp.id, componente_curricular__tipo_modulo=modulo
        ).exists():
            raise forms.ValidationError('Este módulo já foi adicionado a esta configuração de certificação parcial.')

        return modulo

    def processar(self):
        modulo = self.cleaned_data.get('modulo')
        for cc in ComponenteCurricular.objects.filter(matriz_id=self.ccp.matriz_id, tipo_modulo=modulo).only('id'):
            ComponenteCurricularCertificacaoParcial.objects.create(configuracao_certificacao_parcial_id=self.ccp.id, componente_curricular_id=cc.id)


class RelatorioDisciplinasEADForm(forms.FormPlus):
    METHOD = 'GET'
    INFO = 'Serão retornados apenas disciplinas associadas a diários no ano letivo informado.'

    # Filtros
    ano_letivo = forms.ModelChoiceFieldPlus(Ano.objects.ultimos(), label='Ano Letivo')
    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.campi(), label='Campus')
    modalidades = forms.MultipleModelChoiceFieldPlus(Modalidade.objects, label='Modalidade', required=False)
    matrizes = forms.MultipleModelChoiceFieldPlus(Matriz.objects, label='Matriz', required=False)
    cursos = forms.MultipleModelChoiceFieldPlus(CursoCampus.objects, label='Curso', required=False)

    # Exibição
    exibicao = forms.ChoiceField(
        label='Forma de Exibição', choices=[('tela', 'Tela'), ('arquivo', 'Planilha')], widget=forms.RadioSelect(), initial='tela'
    )

    # fieldsets
    fieldsets = (
        ('Filtros', {'fields': (('uo', 'ano_letivo'), 'modalidades', 'matrizes', 'cursos')}),
        ('Exibição', {'fields': ('exibicao',)}),
    )

    def processar(self):
        qs = ComponenteCurricular.objects
        qs = qs.filter(matriz__matrizcurso__curso_campus__diretoria__setor__uo=self.cleaned_data['uo'])
        if self.cleaned_data.get('modalidades'):
            qs = qs.filter(matriz__matrizcurso__curso_campus__modalidade__in=self.cleaned_data['modalidades'])
        if self.cleaned_data.get('matrizes'):
            qs = qs.filter(matriz__in=self.cleaned_data['matrizes'])
        if self.cleaned_data.get('cursos'):
            qs = qs.filter(matriz__matrizcurso__curso_campus__in=self.cleaned_data['cursos'])
        pks = (
            qs.filter(qtd_aulas_ead__gt=0, diario__calendario_academico__ano_letivo=self.cleaned_data['ano_letivo'])
            .order_by('pk')
            .values_list('pk', flat=True)
            .distinct()
        )
        return self.cleaned_data['ano_letivo'], ComponenteCurricular.objects.filter(pk__in=pks)
