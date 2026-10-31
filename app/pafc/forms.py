from django.apps import apps
from django.db.models import Q, Case, When, Value, BooleanField, Exists, OuterRef
from django.forms import modelform_factory
from django.template.defaultfilters import pluralize

from comum.forms import ConfirmarComSenhaForm
from comum.models import Sala, Vinculo
from comum.utils import get_setor_proen, get_setor_proex, get_setor_propi, get_sigla_reitoria, tl
from djtools import forms
from djtools.forms import AutocompleteWidget, RadioSelect
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.utils import get_datetime_now, transaction
from documento_eletronico.models import DocumentoTexto, AssinaturaDocumentoTexto
from edu.models import CursoCampus, Diretoria
from pafc.models import (
    PAFC,
    ComentarioGeralPAFC,
    ComentarioRevisao,
    Conteudo,
    ConteudoPAFC,
    DisciplinaPAFC,
    DocumentoHibrido,
    MembroComissaoPAFC,
    ModeloPAFC,
    MovimentacaoPAFC,
    RevisorTecnicoPAFC,
    Secao,
    SecaoPAFC,
    ValidadorPAFC,
    MatrizPAFC,
    BibliografiaPAFC,
    DocumentoEmitidoPAFC,
    SecaoProgramaPlanoDisciplinaModificado,
    PlanoDisciplinaModificado,
    InfraestruturaExternaPAFC,
    PoloEadPAFC,
    TutorMediadorEadPAFC,
    MapeamentoVersaoPAFCModalidades,
)
from pafc.utils import modulo_documento_eletronico_esta_ativo
from ppc.models import Camara, ProReitoria, MatrizPPC, PlanoDisciplina
from rh.models import Servidor, Setor


class ConfiguracaoForm(forms.FormPlus):
    nome_modelo_portaria_comissao_elaboracao = forms.CharFieldPlus(
        label='Modelo da portaria da Comissão de Elaboração',
        required=False,
        help_text='Nome do modelo de portaria utilizado na geração da Portaria da Comissão de Elaboração do PAFC. '
        'O modelo pode inserir, automaticamente, o nome do campus e do curso através das variáveis '
        '<b>{{ campus }}</b> e <b>{{ nome_curso }}</b> (ou <b>{{ campus_maiusculas }}</b> '
        'e <b>{{ nome_curso_maiusculas }}</b>, para formatar texto em letras maiúsculas). '
        'Outras variáveis também disponíveis: <b>{{ tipo_tramitacao }}</b>, para inserir a natureza do PAFC (criação/adequação); '
        '<b>{{ tabela_comissao_elaboracao }}</b>, para inserir a tabela com os membros da comissão.',
    )
    nome_modelo_parecer_validacao = forms.CharFieldPlus(
        label='Modelo de parecer dos validadores',
        help_text='Nome do modelo de parecer utilizado pelos validadores na geração automática de documento eletrônico do PAFC.',
        required=False,
    )
    nome_modelo_parecer_proreitoria = forms.CharFieldPlus(
        label='Modelo de parecer da pró-reitoria',
        help_text='Nome do modelo de parecer utilizado pela pró-reitoria na geração automática de documento eletrônico do PAFC.',
        required=False,
    )
    nome_modelo_parecer_camara = forms.CharFieldPlus(
        label='Modelo de parecer da câmara',
        help_text='Nome do modelo de parecer utilizado pela câmara na geração automática de documento eletrônico do PAFC.',
        required=False,
    )
    nome_modelo_deliberacao = forms.CharFieldPlus(
        label='Modelo de deliberação',
        help_text='Nome do modelo de deliberação utilizado pelo CONSEPX na geração automática de documento eletrônico do PAFC.',
        required=False,
    )
    nome_modelo_despacho_consepex = forms.CharFieldPlus(
        label='Modelo de despacho do CONSEPEX',
        help_text='Nome do modelo de despacho utilizado pelo CONSEPX na geração automática de documento eletrônico do PAFC.',
        required=False,
    )
    nome_modelo_ata_conselhos = forms.CharFieldPlus(
        label='Modelo de ata dos conselhos',
        help_text='Nome do modelo de ata de reunião dos Conselhos a ser utilizado na geração automática de documento eletrônico do PAFC.',
        required=False,
    )
    nome_modelo_resolucao = forms.CharFieldPlus(
        label='Modelo de resolução',
        help_text='Nome do modelo de resolução utilizado pelo CONSUP na geração automática de documento eletrônico do PAFC.',
        required=False,
    )

    setor_diare = forms.ModelChoiceFieldPlus(Setor.objects, label='Setor responsável pela avaliação e regulação do Ensino', required=False)

    setor_consepex = forms.ModelChoiceFieldPlus(
        Setor.objects,
        label='Setor que representa o Conselho de Ensino, Pesquisa e Extensão (Consepex)',
        required=False,
        help_text='Esse setor será usado na definição do setor dono ao emitir as deliberações do Consepex.',
    )
    setor_consup = forms.ModelChoiceField(
        Setor.objects,
        label='Setor que representa o Conselho Superior (Consup)',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
        required=False,
        help_text='Esse setor será usado na definição do setor dono ao emitir as resoluções do Consup.',
    )


class MapeamentoVersaoPAFCModalidadesForm(forms.ModelFormPlus):
    class Meta:
        model = MapeamentoVersaoPAFCModalidades
        fields = '__all__'


class PAFCForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = '__all__'

    class Media:
        js = ('/static/pafc/js/PAFCForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'modelo' in self.fields:
            self.fields['modelo'].queryset = ModeloPAFC.objects.ativos()

        vinculo_usuario = self.request.user.get_vinculo()
        campus_usuario = vinculo_usuario.setor.uo
        diretorias = Diretoria.objects
        if not campus_usuario.eh_reitoria:
            diretorias = Diretoria.objects.filter(setor__uo=campus_usuario)

        if 'reitor' in self.fields:
            self.fields['previsto_pdi'] = forms.BooleanRequiredField(label='Curso previsto no PDI?')
            self.fields['curso_ja_ofertado_campus'] = forms.BooleanRequiredField(
                label='Curso já ofertado no campus?', help_text='Informe se o PAFC trata da autorização de um novo curso ou de uma adequação textual.'
            )
            self.fields['curso'].label = 'Curso a atualizar'
            self.fields['curso'].queryset = self.fields['curso'].queryset.filter(ativo=True)
            self.fields['ata_reuniao_codiac'].queryset = DocumentoTexto.objects.finalizados().filter(modelo__tipo_documento_texto__nome__iexact='ata')
            if not campus_usuario.eh_reitoria:
                self.fields['curso'].queryset = self.fields['curso'].queryset.filter(diretoria__setor__uo=campus_usuario)
                subquery_assinaturas_usuario = AssinaturaDocumentoTexto.objects.filter(documento=OuterRef('pk'), assinatura__vinculo=vinculo_usuario)
                self.fields['ata_reuniao_codiac'].queryset = self.fields['ata_reuniao_codiac'].queryset.filter(
                    Q(setor_dono__uo=campus_usuario) | Q(Exists(subquery_assinaturas_usuario))
                )

            self.fields['reitor'].queryset = Setor.objects.suap_ativos().get(sigla=get_sigla_reitoria()).chefes
            # abaixo, a redundância no get_setor_proXX().chefes.filter(setor=get_setor_proXX()) visa a
            # garantir que apenas os titulares virão no queryset
            self.fields['pro_reitor_ensino'].queryset = get_setor_proen().chefes.filter(setor=get_setor_proen())
            self.fields['pro_reitor_pesquisa'].queryset = get_setor_propi().chefes.filter(setor=get_setor_propi())
            self.fields['pro_reitor_extensao'].queryset = get_setor_proex().chefes.filter(setor=get_setor_proex())

            self.fields['diretor_geral'].queryset = self.fields['diretor_geral'].queryset.filter(
                pessoa_fisica__in=diretorias.values_list('diretor_geral__pessoa', flat=True).distinct()
            )
            self.fields['diretor_academico'].queryset = self.fields['diretor_academico'].queryset.filter(
                pessoa_fisica__in=diretorias.values_list('diretor_academico__pessoa', flat=True).distinct()
            )

            qs_servidores_campus = Servidor.objects.ativos()
            possui_setor = hasattr(self.instance, 'setor') and self.instance.setor is not None
            if possui_setor or not campus_usuario.eh_reitoria:
                campus = self.instance.setor.uo if possui_setor else campus_usuario
                qs_servidores_campus = qs_servidores_campus.filter(
                    Q(setor_lotacao__uo=campus)
                    | Q(setor_lotacao__uo__equivalente=campus)
                    | Q(setor_exercicio__uo=campus)
                    | Q(setor_exercicio__uo__equivalente=campus)
                )

            self.fields['coordenador_pesquisa'].queryset = qs_servidores_campus.filter(vinculos__user__groups__name='Coordenador de Pesquisa')
            self.fields['coordenador_extensao'].queryset = qs_servidores_campus.filter(vinculos__user__groups__name='Coordenador de Extensão')

            for nome in ('reitor', 'pro_reitor_ensino', 'pro_reitor_pesquisa', 'pro_reitor_extensao'):
                if self.fields[nome].initial is None and self.fields[nome].queryset.count() == 1:
                    primeiro_resultado = self.fields[nome].queryset.first()
                    pk = primeiro_resultado.pk
                    self.fields[nome].initial = pk
                    self.initial[nome] = pk

            if self.fields['diretor_geral'].initial is None and not campus_usuario.eh_reitoria:
                if primeiro_dg := self.fields['diretor_geral'].queryset.first():
                    pk = primeiro_dg.pk
                    self.fields['diretor_geral'].initial = pk
                    self.initial['diretor_geral'] = pk

            diretor_academico_logado = self.fields['diretor_academico'].queryset.filter(pessoa_fisica__pk=self.request.user.get_profile().pk).first()
            if diretor_academico_logado:
                self.fields['diretor_academico'].initial = diretor_academico_logado.pk
                self.initial['diretor_academico'] = diretor_academico_logado.pk

    def clean_ppc(self):
        modelo = self.cleaned_data.get('modelo')
        ppc = self.cleaned_data['ppc']
        if modelo:
            # Validando o tipo da oferta (Técnico Integrado, Subsequente, Graduação etc.)
            if ppc.modelo_ppc.tipo_oferta != modelo.tipo_oferta:
                raise forms.ValidationError(f'O PPC selecionado deve ser da mesma modalidade do Modelo de PAFC escolhido ({modelo.tipo_oferta}).')
            # Validando modalidade (Presencial, EaD, etc.)
            modalidades_permitidas = MapeamentoVersaoPAFCModalidades.objects.filter(versao_modelo=modelo.versao_modelo).values_list(
                'modalidades_de_ensino__pk', flat=True
            )
            if ppc.modelo_ppc.modalidade.pk not in modalidades_permitidas:
                raise forms.ValidationError(
                    f'A modalidade do PPC selecionado ({ppc.modelo_ppc.modalidade}) não é compatível com o modelo de PAFC escolhido (versão {modelo.get_versao_modelo_display()}).'
                )
        return ppc

    def clean_ata_reuniao_codiac(self):
        if not self.is_edicao_inlines():
            curso_ja_ofertado_campus = self.cleaned_data.get('curso_ja_ofertado_campus')
            ata_reuniao_codiac = self.cleaned_data['ata_reuniao_codiac']
            if curso_ja_ofertado_campus is False:
                if ata_reuniao_codiac is None:
                    raise forms.ValidationError('Campo obrigatório se for a primeira oferta do curso no campus.')
            else:
                ata_reuniao_codiac = None
            return ata_reuniao_codiac
        return None

    def clean_curso(self):
        if not self.is_edicao_inlines():
            curso_ja_ofertado_campus = self.cleaned_data.get('curso_ja_ofertado_campus')
            curso = self.cleaned_data['curso']
            if curso_ja_ofertado_campus:
                if curso is None:
                    raise forms.ValidationError('Campo obrigatório se curso já for ofertado no campus.')
                modelo = self.cleaned_data.get('modelo')
                if modelo and curso.modalidade != modelo.tipo_oferta:
                    raise forms.ValidationError(
                        f'O curso selecionado deve ser da mesma modalidade do Modelo de PAFC escolhido ({modelo.tipo_oferta}).'
                    )
            else:
                curso = None
            return curso
        return None

    def clean_justificativa_ausencia_pdi(self):
        if not self.is_edicao_inlines():
            previsto_pdi = self.cleaned_data.get('previsto_pdi')
            justificativa_ausencia_pdi = self.cleaned_data['justificativa_ausencia_pdi']
            if previsto_pdi is False:
                if not justificativa_ausencia_pdi:
                    raise forms.ValidationError('Campo obrigatório se o curso não estiver previsto no PDI.')
            else:
                justificativa_ausencia_pdi = ''
            return justificativa_ausencia_pdi
        return None

    def clean(self):
        super().clean()
        if not self.instance.pk and not self.is_edicao_inlines():
            diretor_academico = self.cleaned_data.get('diretor_academico')
            ppc = self.cleaned_data.get('ppc')
            if (
                diretor_academico
                and ppc
                and PAFC.objects.filter(ppc=ppc, setor__uo=diretor_academico.setor.uo)
                .exclude(situacao__in=[PAFC.APROVADO, *PAFC.SITUACOES_TERMINAIS])
                .exists()
            ):
                raise forms.ValidationError({'ppc': 'No campus, já existe um PAFC em elaboração associado a este PPC.'})
        if self.instance.pk:
            if 'qtd_prevista_tutores' in self.cleaned_data:
                qtd_prevista_tutores = self.cleaned_data.get('qtd_prevista_tutores')
                if qtd_prevista_tutores < 0:
                    raise forms.ValidationError({'qtd_prevista_tutores': 'A quantidade prevista de tutores/mediadores não pode ser negativa.'})
                elif qtd_prevista_tutores == 0 and not self.cleaned_data.get('justificativa_indisponibilidade_tutores'):
                    raise forms.ValidationError(
                        {'justificativa_indisponibilidade_tutores': 'A justificativa é obrigatória quando a quantidade prevista for nula.'}
                    )
        return self.cleaned_data

    def is_edicao_inlines(self):
        GET = self.request.GET or {}
        parametros_dos_inlines = ['comissao', 'revisao_tecnica', 'validacao', 'polos', 'tutores']
        return any(GET.get(parametro) == '1' for parametro in parametros_dos_inlines)


class SecaoForm(forms.ModelFormPlus):
    class Meta:
        model = Secao
        exclude = ('modelo_pafc',)

    def __init__(self, *args, **kwargs):
        modelo_pafc_id = kwargs.pop('modelo_pafc_id', None)
        super().__init__(*args, **kwargs)
        if modelo_pafc_id:
            self.instance.modelo_pafc_id = modelo_pafc_id
            self.initial['ordem_exibicao'] = Secao.objects.filter(modelo_pafc_id=modelo_pafc_id).count() + 1


class ConteudoForm(forms.ModelFormPlus):
    texto = TinyMCEFormField(label='Texto', required=False, config='basic_suap')

    class Meta:
        model = Conteudo
        exclude = ()

    def __init__(self, *args, **kwargs):
        modelo_pafc_id = kwargs.pop('modelo_pafc_id', None)
        super().__init__(*args, **kwargs)
        modelo_pafc_id = modelo_pafc_id or self.instance.secao.modelo_pafc_id
        self.fields['secao'].queryset = Secao.objects.filter(modelo_pafc_id=modelo_pafc_id)

    def clean(self):
        data = super().clean()
        editavel = data.get('editavel')
        texto = data.get('texto')
        if not editavel and not texto:
            raise forms.ValidationError('O preenchimento do texto é obrigatório para um conteúdo não editável.')
        return data


class ReplicarModeloPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = ModeloPAFC
        fields = ('descricao', 'tipo_oferta', 'versao_modelo')

    def clean(self):
        data = super().clean()
        tipo_oferta = data.get('tipo_oferta')
        versao_modelo = data.get('versao_modelo')
        if modelo_existente := ModeloPAFC.objects.ativos().filter(tipo_oferta_id=tipo_oferta.id, versao_modelo=versao_modelo).first():
            raise forms.ValidationError(
                {
                    'tipo_oferta': f'Já existe um modelo de PAFC ativo para este tipo de oferta na versão {modelo_existente.get_versao_modelo_display()}.'
                }
            )
        return data

    def replicar(self, modelo):
        descricao = self.cleaned_data.get('descricao')
        tipo_oferta = self.cleaned_data.get('tipo_oferta')
        versao_modelo = self.cleaned_data.get('versao_modelo')
        return modelo.replicar(descricao, tipo_oferta, versao_modelo)


class SecaoPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = SecaoPAFC
        fields = ('titulo', 'ordem_exibicao')

    def __init__(self, *args, **kwargs):
        pafc_id = kwargs.pop('pafc_id', None)
        super().__init__(*args, **kwargs)
        if pafc_id:
            self.instance.pafc_id = pafc_id
            self.initial['ordem_exibicao'] = SecaoPAFC.objects.filter(pafc_id=pafc_id).count() + 1


class ConteudoPAFCForm(forms.ModelFormPlus):
    texto = TinyMCEFormField(label='Texto', required=False, config='basic_suap')

    class Meta:
        model = ConteudoPAFC
        exclude = ()

    def __init__(self, *args, **kwargs):
        pafc_id = kwargs.pop('pafc_id', None)
        super().__init__(*args, **kwargs)
        pafc_id = pafc_id or self.instance.secao.pafc_id
        self.fields['secao'].queryset = SecaoPAFC.objects.filter(pafc_id=pafc_id)
        if self.instance.id:
            for name in [name for name in self.fields if name != 'texto']:
                del self.fields[name]

    def clean_texto(self):
        texto = self.cleaned_data.get('texto')
        if texto:
            marcadores_invalidos = ModeloPAFC.identificar_marcadores_invalidos(texto)
            if marcadores_invalidos:
                raise forms.ValidationError(
                    f'Os seguintes marcadores são inválidos: {", ".join(marcadores_invalidos)}. '
                    'Volte para a aba de Conteúdo para visualizar a lista de marcadores permitidos.'
                )
        return texto


class ComentarioRevisaoForm(forms.ModelFormPlus):
    class Meta:
        model = ComentarioRevisao
        fields = ('comentario',)

    def __init__(self, conteudo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.servidor = self.request.user.get_relacionamento()
        self.instance.conteudo = conteudo
        self.instance.tipo_revisao = {
            PAFC.EM_ANALISE_PRELIMINAR: ComentarioRevisao.ANALISE_PRELIMINAR,
            PAFC.AGUARDANDO_REVISAO_TECNICA: ComentarioRevisao.REVISAO_TECNICA,
            PAFC.AGUARDANDO_VALIDACAO: ComentarioRevisao.VALIDACAO,
        }[conteudo.secao.pafc.situacao]


class ComentarioGeralForm(forms.ModelFormPlus):
    class Meta:
        model = ComentarioGeralPAFC
        fields = ('comentario',)

    def __init__(self, pafc, escopo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pafc = pafc
        self.escopo = escopo

    def save(self, commit=True):
        if not self.instance.pk:
            self.instance.pafc = self.pafc
            self.instance.servidor = self.request.user.get_relacionamento()
            if self.pafc.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA:
                self.instance.tipo_revisao = ComentarioGeralPAFC.REVISAO_TECNICA
            elif self.pafc.situacao == PAFC.AGUARDANDO_VALIDACAO:
                self.instance.tipo_revisao = ComentarioGeralPAFC.VALIDACAO
            self.instance.escopo = self.escopo
        if commit:
            self.instance.save()


class EditarDadosCursoForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = (
            'numero_vagas_curso',
            'ano_letivo_primeira_oferta',
            'periodo_letivo_primeira_oferta',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['numero_vagas_curso'].required = True
        if self.instance.curso:
            del self.fields['ano_letivo_primeira_oferta']
            del self.fields['periodo_letivo_primeira_oferta']
        else:
            self.fields['ano_letivo_primeira_oferta'].required = True
            self.fields['periodo_letivo_primeira_oferta'].required = True

    def save(self, commit=True):
        pafc = super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(
                self.request.user,
                pafc,
                f'Dados do curso editados (número de vagas: {pafc.numero_vagas_curso}, '
                f'período letivo inicial: {pafc.ano_letivo_primeira_oferta}.{pafc.periodo_letivo_primeira_oferta}).',
            )


class ConfirmacaoForm(forms.FormPlus):
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)


class MembroComissaoPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = MembroComissaoPAFC
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs_servidor = self.fields['servidor'].queryset.ativos()
        if (
            self.request.user
            and not self.request.user.get_vinculo().setor.uo.eh_reitoria
            and not self.request.user.has_group_cached('Administrador de PAFC')
        ):
            # Diretores acadêmicos poderão selecionar apenas servidores vinculados a seu campus.
            campi_diac = [self.request.user.get_vinculo().setor.uo]
            if self.request.user.get_vinculo().setor.uo.equivalente:
                campi_diac.append(self.request.user.get_vinculo().setor.uo.equivalente)
            qs_servidor = qs_servidor.filter(
                Q(setor__uo__in=campi_diac)
                | Q(setor__uo__equivalente__in=campi_diac)
                | Q(setor_lotacao__uo__in=campi_diac)
                | Q(setor_lotacao__uo__equivalente__in=campi_diac)
                | Q(setor_exercicio__uo__in=campi_diac)
                | Q(setor_exercicio__uo__equivalente__in=campi_diac)
                | Q(setor_funcao__uo__in=campi_diac)
                | Q(setor_funcao__uo__equivalente__in=campi_diac)
            )

        self.fields['servidor'].queryset = qs_servidor

    def clean_servidor(self):
        pafc = self.cleaned_data.get('pafc')
        servidor = self.cleaned_data.get('servidor')
        if pafc and pafc.id is not None and servidor:
            if servidor.id in pafc.revisortecnicopafc_set.values_list('servidor_id', flat=True):
                raise forms.ValidationError(
                    f'O servidor "{servidor}" não pode participar da Comissão de Elaboração, porque pertence à equipe de Revisão técnica.'
                )
            if servidor.id in pafc.validadorpafc_set.values_list('servidor_id', flat=True):
                raise forms.ValidationError(
                    f'O servidor "{servidor}" não pode participar da Comissão de Elaboração, porque pertence à equipe de Validadores.'
                )
        return servidor


class RevisorTecnicoPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = RevisorTecnicoPAFC
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['servidor'].queryset = self.fields['servidor'].queryset.ativos()

    def clean_servidor(self):
        pafc = self.cleaned_data.get('pafc')
        servidor = self.cleaned_data.get('servidor')
        if pafc and pafc.id is not None and servidor and servidor.id in pafc.membrocomissaopafc_set.values_list('servidor_id', flat=True):
            raise forms.ValidationError(
                f'O servidor "{servidor}" não pode ser um revisor técnico deste PAFC, porque já pertence à Comissão de Elaboração.'
            )
        return servidor


class ValidadorPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = ValidadorPAFC
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['servidor'].queryset = self.fields['servidor'].queryset.ativos()

    def clean_servidor(self):
        pafc = self.cleaned_data.get('pafc')
        servidor = self.cleaned_data.get('servidor')
        if pafc and pafc.id is not None and servidor and servidor.id in pafc.membrocomissaopafc_set.values_list('servidor_id', flat=True):
            raise forms.ValidationError(f'O servidor "{servidor}" não pode ser um validador deste PAFC, porque já pertence à Comissão de Elaboração.')
        return servidor


class MembroComissaoPAFCFormset(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuracao_atual = set()
        if self.instance.pk:
            for membro in self.instance.membrocomissaopafc_set.all():
                self.configuracao_atual.add(f'{membro.servidor_id}_{membro.funcao}')

    def clean(self):
        super().clean()
        qtd_coordenadores = 0
        servidores = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            # Validando unicidade de servidores
            servidor = form.cleaned_data.get('servidor')
            if servidor:
                if servidor in servidores:
                    raise forms.ValidationError(f'O servidor "{servidor}" foi adicionado mais de uma vez.')
                servidores.append(servidor)
            # Validando unicidade de coordenadores
            funcao = form.cleaned_data.get('funcao')
            if funcao == MembroComissaoPAFC.FUNCAO_COORDENADOR:
                qtd_coordenadores += 1
        if qtd_coordenadores == 0:
            raise forms.ValidationError('A comissão de elaboração precisa ter um coordenador.')
        elif qtd_coordenadores > 1:
            raise forms.ValidationError('Só pode haver um coordenador por comissão de elaboração.')

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed() and self.houve_mudancas_equipe():
            self.instance.portaria_comissao_elaboracao_vigente = None
            if self.instance.situacao > PAFC.AGUARDANDO_PORTARIA:
                self.instance.situacao = PAFC.AGUARDANDO_PORTARIA
            self.instance.save()
            MovimentacaoPAFC.registrar_movimentacao(self.forms and self.forms[0].request.user, self.instance, 'Comissão de elaboração editada.')

    def houve_mudancas_equipe(self):
        """
        Complementa o teste do self.has_changed(), verificando se de fato houve mudanças na configuração da equipe.
        Dependendo de como o usuário operar, é possível o formulário detectar mudanças, mas a equipe permanecer a mesma.
        """
        configuracao_nova = set()
        forms_validos = set(self.forms) - set(self.deleted_forms)
        for form in forms_validos:
            servidor = form.cleaned_data.get('servidor')
            funcao = form.cleaned_data.get('funcao')
            if servidor and funcao:
                configuracao_nova.add(f'{servidor.id}_{funcao}')
        diferenca = self.configuracao_atual.symmetric_difference(configuracao_nova)
        return len(diferenca) > 0


class RevisorTecnicoPAFCFormset(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        qtd_coordenadores = 0
        servidores = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            # Validando unicidade de servidores
            servidor = form.cleaned_data.get('servidor')
            if servidor:
                if servidor in servidores:
                    raise forms.ValidationError(f'O servidor "{servidor}" foi adicionado mais de uma vez.')
                servidores.append(servidor)
            # Validando unicidade de coordenadores
            funcao = form.cleaned_data.get('funcao')
            if funcao == RevisorTecnicoPAFC.FUNCAO_COORDENADOR:
                qtd_coordenadores += 1
        if qtd_coordenadores == 0:
            raise forms.ValidationError('A equipe de revisores precisa ter um coordenador.')
        elif qtd_coordenadores > 1:
            raise forms.ValidationError('Só pode haver um coordenador entre os revisores.')

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.forms and self.forms[0].request.user, self.instance, 'Lista de revisores técnicos editada.')


class ValidadorPAFCFormset(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        qtd_coordenadores = 0
        servidores = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            # Validando unicidade de servidores
            servidor = form.cleaned_data.get('servidor')
            if servidor:
                if servidor in servidores:
                    raise forms.ValidationError(f'O servidor "{servidor}" foi adicionado mais de uma vez.')
                servidores.append(servidor)
            # Validando unicidade de coordenadores
            funcao = form.cleaned_data.get('funcao')
            if funcao == ValidadorPAFC.FUNCAO_COORDENADOR:
                qtd_coordenadores += 1
        if qtd_coordenadores == 0:
            raise forms.ValidationError('A equipe de validadores precisa ter um coordenador.')
        elif qtd_coordenadores > 1:
            raise forms.ValidationError('Só pode haver um coordenador entre os validadores.')

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.forms and self.forms[0].request.user, self.instance, 'Lista de validadores editada.')


class EditarMembroEquipePAFCForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'
    permissao = forms.ChoiceField(label='Permissão', required=True)

    def __init__(self, instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        is_coordenador = False
        permissao_choices = []
        permissao_padrao = None
        if isinstance(self.instance, MembroComissaoPAFC):
            is_coordenador = self.instance.funcao and self.instance.funcao == MembroComissaoPAFC.FUNCAO_COORDENADOR
            permissao_choices = MembroComissaoPAFC.PERMISSAO_CHOICES
            permissao_padrao = MembroComissaoPAFC.PERMISSAO_LEITURA
        elif isinstance(self.instance, RevisorTecnicoPAFC):
            is_coordenador = self.instance.funcao and self.instance.funcao == RevisorTecnicoPAFC.FUNCAO_COORDENADOR
            permissao_choices = RevisorTecnicoPAFC.PERMISSAO_CHOICES
            permissao_padrao = RevisorTecnicoPAFC.PERMISSAO_LEITURA
        elif isinstance(self.instance, ValidadorPAFC):
            is_coordenador = self.instance.funcao and self.instance.funcao == ValidadorPAFC.FUNCAO_COORDENADOR
            permissao_choices = ValidadorPAFC.PERMISSAO_CHOICES
            permissao_padrao = ValidadorPAFC.PERMISSAO_LEITURA

        self.fields['permissao'].choices = permissao_choices
        if self.instance.pk:
            self.fields['permissao'].initial = self.instance.permissao
            if is_coordenador:
                self.fields['permissao'].disabled = True
                self.fields['permissao'].widget.attrs['disabled'] = 'disabled'
                self.fields['permissao'].help_text = 'O coordenador sempre terá permissão de edição.'
        else:
            self.fields['permissao'].initial = permissao_padrao

    def save(self, commit=True):
        self.instance.permissao = self.cleaned_data['permissao']
        if commit:
            self.instance.save()


class InformarColaboradoresForm(forms.ModelFormPlus):
    colaboradores = forms.MultipleModelChoiceFieldPlus(
        label='Colaboradores', queryset=Vinculo.objects.ativos().pessoas_fisicas().order_by('pessoa__nome')
    )

    class Meta:
        model = PAFC
        fields = ('colaboradores',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['colaboradores'].queryset = self.fields['colaboradores'].queryset.filter(setor__uo=self.instance.setor.uo)

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Lista de colaboradores editada.')


class InformarCoordenadorCursoForm(forms.ModelFormPlus):
    coordenador_curso = forms.ModelChoiceFieldPlus(
        queryset=Servidor.objects.ativos().docentes().filter(jornada_trabalho__nome__icontains='DEDICACAO EXCLUSIVA')
    )

    class Meta:
        model = PAFC
        fields = ('coordenador_curso',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coordenador_curso'].queryset = self.fields['coordenador_curso'].queryset.filter(setor__uo=self.instance.setor.uo)
        self.coordenador_cadastrado = self.instance.coordenador_curso
        if not self.coordenador_cadastrado:
            coordenador_sugerido = None
            help_text = None
            if self.instance.curso:
                coordenador_sugerido = self.instance.curso.coordenador or self.instance.curso.coordenador_2
                help_text = (
                    'O sistema usou o curso associado ao PAFC como referência para autopreencher o coordenador. Você ainda pode escolher outro.'
                )
            else:
                qs_curso_inferido = CursoCampus.objects.filter(
                    descricao__istartswith=self.instance.ppc.nome_curso, diretoria__setor__uo=self.instance.setor.uo, ativo=True
                )
                if qs_curso_inferido.count() == 1:
                    curso_inferido = qs_curso_inferido.first()
                    coordenador_sugerido = curso_inferido.coordenador or curso_inferido.coordenador_2
                    help_text = (
                        'O sistema detectou um curso existente que parece estar associado a este PAFC e '
                        'usou-o para autopreencher o coordenador. Você ainda pode escolher outro.'
                    )
            if coordenador_sugerido:
                self.initial['coordenador_curso'] = coordenador_sugerido.id_relacionamento
                self.fields['coordenador_curso'].initial = self.initial['coordenador_curso']
                self.fields['coordenador_curso'].help_text = help_text

    def save(self, commit=True):
        super().save(commit)
        if commit and self.coordenador_cadastrado != self.instance.coordenador_curso:
            MovimentacaoPAFC.registrar_movimentacao(
                self.request.user, self.instance, f'Coordenador de curso editado para: {self.instance.coordenador_curso}.'
            )


class InformarTecnicosAdministrativosForm(forms.ModelFormPlus):
    tecnicos_administrativos = forms.MultipleModelChoiceFieldPlus(
        label='Técnicos Administrativos', queryset=Servidor.objects.ativos().tecnicos_administrativos()
    )

    class Meta:
        model = PAFC
        fields = ('tecnicos_administrativos',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campus_pafc = self.instance.setor.uo
        self.fields['tecnicos_administrativos'].queryset = self.fields['tecnicos_administrativos'].queryset.filter(
            Q(setor__uo=campus_pafc) | Q(setor_lotacao__uo__equivalente=campus_pafc)
        )

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Lista de técnicos-administrativos editada.')


class EditarDocentesDisciplinaForm(forms.ModelFormPlus):
    docentes = forms.MultipleModelChoiceFieldPlus(label='Docentes', required=False, queryset=Servidor.objects.ativos().docentes())

    class Meta:
        model = DisciplinaPAFC
        fields = ('docentes',)

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(
                self.request.user,
                self.instance.pafc,
                f'Lista de docentes editada para a disciplina: {self.instance.plano_disciplina.nome_disciplina}.',
            )


class JustificarIndisponibilidadeDocentesForm(forms.ModelFormPlus):
    class Meta:
        model = DisciplinaPAFC
        fields = ('justificativa_indisponibilidade_docentes',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_indisponibilidade_docentes'].label = 'Justificativa'
        self.fields['justificativa_indisponibilidade_docentes'].required = True

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(
                self.request.user,
                self.instance.pafc,
                f'Justificada a indisponibilidade de docentes para disciplina "{self.instance.plano_disciplina.nome_disciplina}".',
            )


class InformarLaboratoriosForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = ('salas',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uo_pafc = self.instance.setor.uo
        self.fields['salas'].required = True
        # Exibe apenas salas configuradas como laboratórios e as ordena por campus, depois por nome
        self.fields['salas'].queryset = (
            Sala.ativas.filter(laboratorio__isnull=False)
            .annotate(
                mesmo_campus=Case(
                    When(predio__uo__in=[uo_pafc, uo_pafc.equivalente], then=Value(True)), default=Value(False), output_field=BooleanField()
                )
            )
            .order_by('-mesmo_campus', 'nome')
        )

    def save(self, commit=True):
        pafc = super().save(commit)
        if commit and self.has_changed():
            InfraestruturaExternaPAFC.processar_mudancas_na_infraestrutura(pafc)
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, pafc, 'Lista de laboratórios editada.')
        return pafc


class EditarLaboratorioForm(forms.ModelFormPlus):
    class Meta:
        model = Sala
        fields = ('descricao',)


PoloEadPAFCForm = modelform_factory(PoloEadPAFC, forms.ModelFormPlus, fields='__all__')


class PoloEadPAFCInlineFormset(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        qtd_unidades_sede_informadas = 0
        total_vagas_ofertadas = 0
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue

            # Validando soma de vagas (deve ser igual à quantidade de vagas ofertadas pelo curso)
            total_vagas_ofertadas += form.cleaned_data.get('vagas_ofertadas') or 0
            if form.cleaned_data.get('tipo') == PoloEadPAFC.TIPO_SEDE:
                qtd_unidades_sede_informadas += 1
        if qtd_unidades_sede_informadas == 0:
            raise forms.ValidationError('Você precisa informar uma unidade sede.')
        elif qtd_unidades_sede_informadas > 1:
            raise forms.ValidationError('Você pode informar apenas uma unidade sede.')
        if total_vagas_ofertadas != self.instance.numero_vagas_curso:
            raise forms.ValidationError(
                f'A soma das vagas dos polos ({total_vagas_ofertadas}) deve corresponder ao total de vagas ofertadas pelo curso ({self.instance.numero_vagas_curso}).'
            )

    def save(self, commit=True):
        instancias = super().save(commit)
        if commit and self.has_changed():
            user = tl.get_user()
            MovimentacaoPAFC.registrar_movimentacao(user, self.instance, 'Relação de polos EaD editada.')
        return instancias


class TutorMediadorEadPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = TutorMediadorEadPAFC
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.ativos().pessoas_fisicas()


class TutorMediadorEadPAFCFormset(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        qtd_tutores_informados = 0
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            vinculo = form.cleaned_data.get('vinculo') if hasattr(form, 'cleaned_data') else None
            if vinculo:
                qtd_tutores_informados += 1

        if self.instance.qtd_prevista_tutores is not None:
            if qtd_tutores_informados > self.instance.qtd_prevista_tutores:
                raise forms.ValidationError(
                    f'A quantidade de tutores/mediadores informados ({qtd_tutores_informados}) não pode exceder a quantidade prevista ({self.instance.qtd_prevista_tutores}).'
                )
            if qtd_tutores_informados < self.instance.qtd_prevista_tutores and not self.instance.justificativa_indisponibilidade_tutores:
                raise forms.ValidationError(
                    f'A quantidade de tutores/mediadores informada ({qtd_tutores_informados}) é menor que a quantidade prevista ({self.instance.qtd_prevista_tutores}), '
                    f'mas não foi informada uma justificativa.'
                )

    def save(self, commit=True):
        instancias = super().save(commit)
        if commit and self.has_changed():
            user = tl.get_user()
            MovimentacaoPAFC.registrar_movimentacao(user, self.instance, 'Relação de tutores/mediadores EaD editada.')
        return instancias


def ext_combo_template_matriz_ppc(obj):
    turno = str(obj.turno).upper() if obj.turno else 'Turno indefinido'
    qtd_periodos = (
        f'{obj.quantidade_periodos} período{pluralize(obj.quantidade_periodos)}' if obj.quantidade_periodos else 'Quantidade de períodos indefinida'
    )
    return f'{obj.nome} ({turno}; {qtd_periodos})'


class VincularMatrizPAFCForm(forms.ModelFormPlus):
    matriz_ppc = forms.ModelChoiceFieldPlus(
        label='Matriz do PPC',
        queryset=MatrizPPC.objects.none(),
        widget=AutocompleteWidget(extraParams={'ext_combo_template': ext_combo_template_matriz_ppc}),
        required=True,
    )

    class Meta:
        model = MatrizPAFC
        fields = ('matriz_ppc',)

    def __init__(self, pafc, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.pafc = pafc
        matrizes_vinculadas = pafc.matrizpafc_set.values_list('matriz_ppc_id', flat=True)
        self.fields['matriz_ppc'].queryset = pafc.ppc.matrizppc_set.filter(situacao_matriz=MatrizPPC.MATRIZ_APROVADA).exclude(
            pk__in=matrizes_vinculadas
        )


class AtualizarBibliografiaPAFC(forms.ModelFormPlus):
    class Meta:
        model = BibliografiaPAFC
        fields = (
            'quantidade_no_campus',
            'observacao',
            'detalhes_observacao',
        )

    def clean(self):
        cleaned_data = super().clean()
        quantidade_no_campus = cleaned_data.get('quantidade_no_campus')
        observacao = cleaned_data.get('observacao')
        detalhes_observacao = cleaned_data.get('detalhes_observacao')
        if quantidade_no_campus == 0:
            if not observacao:
                raise forms.ValidationError({'observacao': 'A observação é obrigatória quando não houver exemplares no campus.'})
            elif observacao == BibliografiaPAFC.OBSERVACAO_OUTRA and not detalhes_observacao:
                raise forms.ValidationError({'detalhes_observacao': 'Faltou especificar a observação (a opção "Outra" foi escolhida).'})
        return cleaned_data


class AnexarRelatorioAnalisePreliminarForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = ('relatorio_analise_preliminar',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['relatorio_analise_preliminar'].required = True

    def save(self, commit=True):
        pafc = super().save(False)
        if commit and self.has_changed():
            pafc.data_upload_relatorio_analise_preliminar = get_datetime_now()
            pafc.relatorio_analise_preliminar_cadastrado_por = self.request.user.vinculo
            pafc.save()
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Relatório da Análise Preliminar editado.')


class AnexarFichaRevisaoTecnicaForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = ('ficha_revisao_tecnica',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ficha_revisao_tecnica'].required = True

    def save(self, commit=True):
        pafc = super().save(False)
        if commit and self.has_changed():
            pafc.data_upload_ficha_revisao_tecnica = get_datetime_now()
            pafc.ficha_revisao_tecnica_cadastrada_por = self.request.user.vinculo
            pafc.save()
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Ficha de Revisão Técnica editada.')


class EditarProReitoriaForm(forms.ModelFormPlus):
    proreitoria = forms.ModelChoiceFieldPlus(label='Pró-Reitoria', queryset=ProReitoria.objects, required=True)

    class Meta:
        model = PAFC
        fields = ('proreitoria',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proreitoria'].queryset = ProReitoria.objects.filter(ativo=True, tipos_oferta__id=self.instance.ppc.diretriz.tipo_oferta_id)


class EmitirDocumentoPAFCBaseForm(ConfirmacaoForm):
    ACAO_EMITIR = 'emitir'
    ACAO_VINCULAR = 'vincular'
    ACAO_CHOICES = (
        (ACAO_EMITIR, 'Emitir documento'),
        (ACAO_VINCULAR, 'Vincular documento existente'),
    )

    acao = forms.ChoiceField(
        label='Ação',
        choices=ACAO_CHOICES,
        required=True,
        initial=ACAO_EMITIR,
        widget=RadioSelect,
        help_text='Escolha se você quer emitir o documento ou utilizar um existente no SUAP. Apenas documentos FINALIZADOS poderão ser vinculados.',
    )
    documento_existente = forms.FileFieldPlus(label='Documento existente', required=False)

    # Usado apenas ao usar a opção de upload
    assunto_documento = forms.CharFieldPlus(label='Assunto do documento', required=True)
    # Usado apenas ao usar a opção de upload
    identificador_documento = forms.CharFieldPlus(
        label='Identificador do documento', required=True, help_text='Exemplo: PORTARIA Nº XX/2025 - SETOR/INSTITUIÇÃO'
    )

    decisao = forms.ChoiceField(label='Decisão', choices=PAFC.DECISAO_CHOICES, required=True)

    class Media:
        js = ('/static/pafc/js/EmitirDocumentoPAFCForm.js',)

    def __init__(self, pafc, tipo_documento, exibir_decisao_choices=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pafc = pafc
        self.tipo_documento = tipo_documento

        # TODO: implementar alternativa que não utiliza Doc. Eletrônico, mesmo quando o módulo estiver instalado, fechando ideia do DocumentoHibrido.
        if modulo_documento_eletronico_esta_ativo():
            DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
            self.fields['documento_existente'] = forms.ModelChoiceFieldPlus(
                label='Documento existente', queryset=DocumentoTexto.objects.finalizados(), required=False
            )
            del self.fields['assunto_documento']
            del self.fields['identificador_documento']
        else:
            # remove possibilidade de emissão
            self.fields['acao'].choices = self.ACAO_CHOICES[:-1]

        if exibir_decisao_choices:
            if 'homologação' in tipo_documento:
                self.fields['decisao'].choices = [
                    (PAFC.DECISAO_APROVAR, 'Aprovar'),
                ]

            info = (
                '<p>Após finalização do documento emitido (ou vinculação de documento existente), o sistema irá se comportar da seguinte forma:<ul>'
            )
            for decisao in self.fields['decisao'].choices:
                if decisao[0] != '':
                    info = f'{info}<li><b>{decisao[1]}</b>: {PAFC.DECISAO_INFO_CHOICES[int(decisao[0]) - 1][1]}</li>'
            self.INFO = f'{info}</ul></p>'
        else:
            del self.fields['decisao']

        # Tratando situação de avanço automático após vinculação de documento.
        if not hasattr(self, 'INFO') and 'decisao' not in self.fields and len(self.fields['acao'].choices) > 1:
            self.INFO = '<p>Ao vincular um documento existente, o PAFC seguirá automaticamente para a próxima etapa.</p>'

        # Mantendo o campo de confirmação como o último do form.
        self.order_fields([field for field in self.fields if field != 'confirmacao'] + ['confirmacao'])

    def clean_documento_existente(self):
        cleaned_data = self.cleaned_data
        acao = cleaned_data.get('acao')
        documento_existente = cleaned_data.get('documento_existente')
        if acao == self.ACAO_VINCULAR and documento_existente is None:
            raise forms.ValidationError('É preciso informar um documento para vincular.')
        return documento_existente

    def acao_eh_vincular(self):
        return self.cleaned_data.get('acao') == self.ACAO_VINCULAR

    def pre_processar(self):
        """
        Realiza todo o processamento antes de emitir/vincular de fato o documento.
        Por exemplo, atualiza o PAFC com as decisões da etapa.

        Deve ser implementado pelas subclasses.
        """
        raise NotImplementedError

    def processar(self):
        with transaction.atomic():
            self.pre_processar()
            if self.acao_eh_vincular():
                documento_existente = self.cleaned_data.get('documento_existente')
                return DocumentoEmitidoPAFC.vincular_documento(self.pafc, self.request.user, self.tipo_documento, documento_existente)
            else:
                return DocumentoEmitidoPAFC.emitir_documento(self.pafc, self.request.user, self.tipo_documento)


class EmitirPortariaComissaoElaboracaoForm(EmitirDocumentoPAFCBaseForm):
    def pre_processar(self):
        pass

    def processar(self):
        doc_emitido_pafc = super().processar()
        self.pafc.portaria_comissao_elaboracao_vigente = doc_emitido_pafc.documento
        self.pafc.save()


class EmitirParecerValidacaoForm(EmitirDocumentoPAFCBaseForm):
    proreitoria = forms.ModelChoiceFieldPlus(label='Pró-Reitoria', queryset=ProReitoria.objects, required=True)

    def __init__(self, pafc, tipo_documento, *args, **kwargs):
        super().__init__(pafc, tipo_documento, *args, **kwargs)

        if pafc.decisao_camara:
            del self.fields['proreitoria']
        else:
            qs = ProReitoria.objects.filter(ativo=True, tipos_oferta__id=self.pafc.ppc.diretriz.tipo_oferta_id)
            if qs.count() == 1:
                self.pafc.proreitoria = qs[0]
                del self.fields['proreitoria']
            else:
                self.fields['proreitoria'].queryset = qs

    def pre_processar(self):
        self.pafc.proreitoria = self.pafc.proreitoria or self.cleaned_data.get('proreitoria')
        self.pafc.save()


class EmitirParecerProReitoriaForm(EmitirDocumentoPAFCBaseForm):
    reprovado_proreitoria = forms.BooleanField(
        label='Reprovado',
        help_text='Defina se o PAFC deve ser reprovado. A reprovação será efetivada após finalização do parecer emitido.',
        required=False,
    )
    ad_referendum = forms.BooleanField(
        label='Sugerir Ad Referendum',
        help_text='Marque esta opção para sugerir que o PAFC seja tramitado Ad Referendum nos conselhos.',
        required=False,
    )
    camara = forms.ModelChoiceFieldPlus(label='Câmara', queryset=Camara.objects, help_text='Informe a Câmara que irá continuar a análise deste PAFC.')
    pular_camara = forms.BooleanField(
        label='Avançar para o CONSEPEX',
        help_text='Marque esta opção para o sistema ignorar a análise da Câmara e avançar o PAFC diretamente para a análise do CONSEPEX.',
        required=False,
    )

    class Media:
        js = ('/static/pafc/js/EmitirParecerProReitoriaForm.js',)

    def __init__(self, pafc, tipo_documento, *args, **kwargs):
        super().__init__(pafc, tipo_documento, *args, **kwargs)

        qs = self.fields['camara'].queryset.filter(ativo=True, tipos_oferta__id=self.pafc.ppc.diretriz.tipo_oferta_id)
        if len(qs) == 1:
            self.pafc.camara = qs.first()
            del self.fields['camara']
        else:
            self.fields['camara'].queryset = qs

    def clean_camara(self):
        reprovado_proreitoria = self.cleaned_data.get('reprovado_proreitoria')
        camara = self.cleaned_data.get('camara') or self.pafc.camara
        if reprovado_proreitoria is False and camara is None:
            raise forms.ValidationError('Este campo é obrigatório.')
        return camara

    def clean_pular_camara(self):
        ad_referendum = self.cleaned_data.get('ad_referendum')
        pular_camara = self.cleaned_data.get('pular_camara')
        if ad_referendum is False and pular_camara is True:
            raise forms.ValidationError('Este campo não pode ser marcado se a tramitação não for Ad Referendum.')
        return pular_camara

    def pre_processar(self):
        cleaned_data = self.cleaned_data
        self.pafc.reprovado_proreitoria = cleaned_data.get('reprovado_proreitoria')
        if 'camara' in self.fields:
            self.pafc.camara = cleaned_data.get('camara')
        self.pafc.ad_referendum = cleaned_data.get('ad_referendum')
        self.pafc.pular_camara = cleaned_data.get('pular_camara')
        self.pafc.save()


class EmitirDocumentoPAFCSolicitandoDecisaoForm(EmitirDocumentoPAFCBaseForm):
    def __init__(self, pafc, tipo_documento, *args, **kwargs):
        super().__init__(pafc, tipo_documento, *args, **kwargs, exibir_decisao_choices=True)

    def get_decisao(self):
        return self.cleaned_data.get('decisao')


class EmitirParecerCamaraForm(EmitirDocumentoPAFCSolicitandoDecisaoForm):
    def pre_processar(self):
        self.pafc.decisao_camara = self.get_decisao()
        self.pafc.save()


class EmitirDeliberacaoCONSEPEXForm(EmitirDocumentoPAFCSolicitandoDecisaoForm):
    def __init__(self, pafc, tipo_documento, *args, **kwargs):
        super().__init__(pafc, tipo_documento, *args, **kwargs)
        self.fields['decisao'].choices = [decisao for decisao in PAFC.DECISAO_CHOICES if decisao[0] != PAFC.DECISAO_SOLICITAR_CORRECAO]

    def pre_processar(self):
        self.pafc.decisao_consepex = self.get_decisao()
        self.pafc.save()


class EmitirResolucaoCONSUPForm(EmitirDocumentoPAFCSolicitandoDecisaoForm):
    def __init__(self, pafc, tipo_documento, *args, **kwargs):
        super().__init__(pafc, tipo_documento, *args, **kwargs)
        self.fields['decisao'].choices = [decisao for decisao in PAFC.DECISAO_CHOICES if decisao[0] != PAFC.DECISAO_SOLICITAR_CORRECAO]

    def pre_processar(self):
        self.pafc.decisao_consup = self.get_decisao()
        self.pafc.save()


class SolicitarCorrecaoEmConselhosForm(EmitirDocumentoPAFCBaseForm):
    INFO = 'Descreva e justifique a correção necessária e informe a ata da reunião que decidiu pelo pedido de correção.'

    justificativa = forms.CharField(label='Justificativa da correção', max_length=None, widget=forms.Textarea())

    def __init__(self, pafc, *args, **kwargs):
        super().__init__(pafc, 'Ata', *args, **kwargs)
        self.fields['acao'].label = 'Escolha como a ata será registrada'

    def pre_processar(self):
        justificativa = self.cleaned_data['justificativa']
        if self.pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
            self.pafc.decisao_consepex = PAFC.DECISAO_SOLICITAR_CORRECAO
            self.pafc.justificativa_decisao_consepex = justificativa
        else:
            self.pafc.decisao_consup = PAFC.DECISAO_SOLICITAR_CORRECAO
            self.pafc.justificativa_decisao_consup = justificativa
        self.pafc.save()


class EmitirDespachoCONSEPEXForm(EmitirDocumentoPAFCBaseForm):
    def pre_processar(self):
        pass


def emitir_documento_pafc_formfactory(request, pafc, tipo_documento):
    form_class = None

    if tipo_documento == 'Ata':
        if pafc.situacao in [PAFC.AGUARDANDO_APROVACAO_CONSEPEX, PAFC.AGUARDANDO_APROVACAO_CONSUP]:
            form_class = SolicitarCorrecaoEmConselhosForm

    elif tipo_documento == 'Portaria da Comissão de Elaboração':
        if pafc.situacao == PAFC.AGUARDANDO_PORTARIA:
            form_class = EmitirPortariaComissaoElaboracaoForm

    elif tipo_documento == 'Parecer':
        if pafc.situacao == PAFC.AGUARDANDO_VALIDACAO:
            form_class = EmitirParecerValidacaoForm
        elif pafc.situacao == PAFC.EM_ANALISE_PROREITORIA:
            form_class = EmitirParecerProReitoriaForm
        elif pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA:
            form_class = EmitirParecerCamaraForm

    elif tipo_documento in ['Deliberação', 'Deliberação Ad Referendum', 'Deliberação de homologação']:
        if (
            pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX
            or pafc.situacao in [PAFC.AGUARDANDO_APROVACAO_CONSUP, PAFC.APROVADO]
            and 'homologação' in tipo_documento
        ):
            form_class = EmitirDeliberacaoCONSEPEXForm

    elif tipo_documento in ['Resolução', 'Resolução Ad Referendum', 'Resolução de homologação']:
        if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSUP or pafc.situacao == PAFC.APROVADO and 'homologação' in tipo_documento:
            form_class = EmitirResolucaoCONSUPForm

    elif tipo_documento == 'Despacho':
        if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX and pafc.consepex_inexistente:
            form_class = EmitirDespachoCONSEPEXForm

    else:
        raise ValueError(f'Tipo de documento inválido: {tipo_documento}.')

    if form_class is None:
        raise forms.ValidationError(f'A situação {pafc.get_situacao_display()} não permite emissão de {tipo_documento.lower()}.')

    return form_class(data=request.POST or None, pafc=pafc, tipo_documento=tipo_documento, request=request)


class DocumentoHibridoForm(forms.ModelFormPlus):
    TIPO_DOC_ELETRONICO = 'doc_eletronico'
    TIPO_ARQUIVO = 'arquivo'
    TIPO_DOCUMENTO_CHOICES = (
        (TIPO_DOC_ELETRONICO, 'Documento Eletrônico'),
        (TIPO_ARQUIVO, 'Arquivo'),
    )

    tipo_documento = forms.ChoiceField(
        label='Tipo do documento',
        choices=TIPO_DOCUMENTO_CHOICES,
        required=True,
        initial=TIPO_DOC_ELETRONICO,
        widget=RadioSelect,
        help_text='Escolha se você pretende usar um documento eletrônico ou enviar um arquivo.',
    )

    class Meta:
        model = DocumentoHibrido
        fields = ('id_documento_eletronico', 'identificador_arquivo', 'assunto_arquivo', 'arquivo')

    class Media:
        js = ('/static/pafc/js/DocumentoHibridoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if modulo_documento_eletronico_esta_ativo():
            DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
            self.fields['id_documento_eletronico'] = forms.ModelChoiceFieldPlus(
                label='Documento eletrônico',
                queryset=DocumentoTexto.objects.finalizados() | DocumentoTexto.objects.filter(pk=self.instance.id_documento_eletronico),
                help_text='Apenas documentos finalizados podem ser vinculados.',
                required=False,
            )
        else:
            del self.fields['id_documento_eletronico']
            self.fields['tipo_documento'].initial = self.TIPO_ARQUIVO
            self.fields['tipo_documento'].widget = forms.HiddenInput()

        for field in self.fields:
            if field != 'tipo_documento':
                self.fields[field].required = False

        if self.instance.pk:
            self.fields['tipo_documento'].initial = self.TIPO_ARQUIVO if self.instance.arquivo else self.TIPO_DOC_ELETRONICO

        self.order_fields(['tipo_documento'] + [field for field in self.fields if field != 'tipo_documento'])

    def get_tipo_documento(self):
        return self.cleaned_data.get('tipo_documento')

    def clean_id_documento_eletronico(self):
        if self.get_tipo_documento() == self.TIPO_DOC_ELETRONICO:
            documento = self.cleaned_data.get('id_documento_eletronico')
            return documento.id if documento else None
        return None

    def clean_identificador_arquivo(self):
        if self.get_tipo_documento() == self.TIPO_ARQUIVO:
            return self.cleaned_data.get('identificador_arquivo')
        return None

    def clean_assunto_arquivo(self):
        if self.get_tipo_documento() == self.TIPO_ARQUIVO:
            return self.cleaned_data.get('assunto_arquivo')
        return None

    def clean_arquivo(self):
        if self.get_tipo_documento() == self.TIPO_ARQUIVO:
            return self.cleaned_data.get('arquivo')
        return None

    def clean(self):
        cleaned_data = super().clean()
        tipo_documento = self.cleaned_data.get('tipo_documento')
        if tipo_documento == self.TIPO_DOC_ELETRONICO:
            if not cleaned_data.get('id_documento_eletronico'):
                self.add_error('id_documento_eletronico', 'Documento eletrônico não informado.')
        elif tipo_documento == self.TIPO_ARQUIVO:
            for campo in ['identificador_arquivo', 'assunto_arquivo', 'arquivo']:
                label_campo = self.fields[campo].label
                if not cleaned_data.get(campo):
                    self.add_error(campo, f'{label_campo} não informado.')
        else:
            self.add_error('tipo_documento', 'Tipo de documento inválido.')

        return cleaned_data

    def save(self, commit=True):
        doc_hibrido = super().save(commit=commit)
        if commit and self.has_changed():
            doc_hibrido.situacao = DocumentoHibrido.DOCUMENTO_FINALIZADO
            doc_hibrido.save()
        return doc_hibrido


class EditarEmentaPlanoDisciplinaModificadoForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Isso pode causar erros de visualização na geração do PDF.'

    ementa = TinyMCEFormField(label='Ementa', config='custom_ppc', required=True)

    class Meta:
        model = PlanoDisciplinaModificado
        fields = (
            'ementa',
            'edicao_ementa_concluida',
        )

    def clean_ementa(self):
        ementa = self.cleaned_data['ementa']
        return PlanoDisciplina.remover_formatacao(ementa)


class SecaoProgramaPlanoDisciplinaModificadoForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Isso pode causar erros de visualização na geração do PDF.'

    texto = TinyMCEFormField(label='Texto', config='custom_ppc', required=True)

    class Meta:
        model = SecaoProgramaPlanoDisciplinaModificado
        fields = ('texto', 'edicao_concluida')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_texto(self):
        texto = self.cleaned_data['texto']
        return PlanoDisciplina.remover_formatacao(texto)


class ConvocarCamaraPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = ('data_convocacao_camara',)

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Dados da Câmara editados.')


class ConvocarConsepexPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = (
            'data_convocacao_consepex',
            'consepex_inexistente',
        )

    def clean(self):
        data_convocacao = self.cleaned_data.get('data_convocacao_consepex')
        consepex_inexistente = self.cleaned_data.get('consepex_inexistente')
        if not data_convocacao and not consepex_inexistente:
            raise forms.ValidationError('Informe a data de convocação ou marque que o CONSEPEX não está instituído.')
        if data_convocacao and consepex_inexistente:
            raise forms.ValidationError('Não é permitido informar a data de convocação e marcar que o CONSEPEX não está instituído ao mesmo tempo.')
        return super().clean()

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Dados do CONSEPEX editados.')


class ConvocarConsupPAFCForm(forms.ModelFormPlus):
    class Meta:
        model = PAFC
        fields = ('data_convocacao_consup',)

    def save(self, commit=True):
        super().save(commit)
        if commit and self.has_changed():
            MovimentacaoPAFC.registrar_movimentacao(self.request.user, self.instance, 'Dados do CONSUP editados.')


class IndeferirSolicitacaoTramitacaoAdReferendumForm(ConfirmarComSenhaForm):
    motivo_indeferimento = forms.CharFieldPlus(label='Motivo de indeferimento', max_length=None, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mantendo o campo do motivo como o primeiro do form.
        self.order_fields(['motivo_indeferimento'] + [field for field in self.fields if field != 'motivo_indeferimento'])

    def get_motivo_informado(self):
        return self.cleaned_data['motivo_indeferimento']
