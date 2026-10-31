import copy
import datetime

from django.conf import settings
from django.utils.safestring import mark_safe
from comum.models import Configuracao
from comum.utils import (
    get_setor_proen,
    get_setor_proex,
    get_setor_propi,
    get_sigla_reitoria,
)
from djtools import forms
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget
from comum.models import Vinculo
from edu.models import Diretoria, EixoTecnologico, Modalidade, NivelEnsino, Nucleo
from ppc.models import (
    AdministradorTipoOferta,
    AtualizacaoComissaoElaboracao,
    Camara,
    CertificacaoParcial,
    ColaboradorPPC,
    ComentarioConteudoPPC,
    ComentarioRevisaoPlanoDisciplina,
    ComissaoPTDEM,
    ComponenteExigidoDiretriz,
    ConfiguracaoOptativasMatrizPPC,
    Conteudo,
    ConteudoPPC,
    Diretriz,
    DocumentoPPC,
    EixoTecnologicoDiretriz,
    ElaboradorPPC,
    IndicacaoElaboradorPPC,
    MatrizPPC,
    MembroColegiado,
    ModalidadePraticaProfissionalDiretriz,
    ModalidadePraticaProfissionalPPC,
    ModeloPlanoDisciplina,
    ModeloPPC,
    ModeloSecaoPlanoDisciplina,
    NucleoDiretriz,
    PeriodoDiretriz,
    PlanoDisciplina,
    PlanoDisciplinaCertificacaoParcial,
    PlanoDisciplinaPPC,
    ProjetoPedagogicoCurso,
    ProReitoria,
    RevisorPPC,
    Secao,
    SecaoPlanoDisciplina,
    SolicitacaoPPC,
)
from rh.models import Setor


class ConfiguracaoForm(forms.FormPlus):
    nome_modelo_ata = forms.CharFieldPlus(
        label='Modelo de ata',
        help_text='Nome do modelo de ata utilizado na geração automática de documento eletrônico da solicitação de PPC.',
        required=False,
    )
    nome_modelo_portaria = forms.CharFieldPlus(
        label='Modelo de portaria',
        help_text='Nome do modelo de portaria utilizado na geração automática de documento eletrônico da solicitação de PPC.',
        required=False,
    )
    nome_modelo_parecer_revisao = forms.CharFieldPlus(
        label='Modelo de parecer da revisão',
        help_text='Nome do modelo de parecer utilizado pela revisão na geração automática de documento eletrônico do PPC.',
        required=False,
    )
    nome_modelo_parecer_camara = forms.CharFieldPlus(
        label='Modelo de parecer da câmara',
        help_text='Nome do modelo de parecer utilizado pela câmara na geração automática de documento eletrônico do PPC.',
        required=False,
    )
    nome_modelo_deliberacao = forms.CharFieldPlus(
        label='Modelo de deliberação',
        help_text='Nome do modelo de deliberação utilizado pelo CONSEPX na geração automática de documento eletrônico do PPC.',
        required=False,
    )
    nome_modelo_resolucao = forms.CharFieldPlus(
        label='Modelo de resolução',
        help_text='Nome do modelo de resolução utilizado pelo CONSUP na geração automática de documento eletrônico do PPC.',
        required=False,
    )
    nome_modelo_despacho = forms.CharFieldPlus(
        label='Modelo de despacho',
        help_text='Nome do modelo de despacho utilizado na geração automática de documento eletrônico do PPC.',
        required=False,
    )
    setor_revisao_plano_disciplina = forms.ModelChoiceField(
        Setor.objects,
        label='Setor de revisão de planos de disciplinas',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
        help_text='Informe o setor responsável pela revisão e aprovação dos planos de disciplinas. Este setor também fará o deferimento das indicações de membros da comissão de elaboração do PPC.',
        required=True,
    )
    setor_secretaria_conselhos = forms.ModelChoiceField(
        Setor.objects,
        label='Setor da secretaria dos conselhos',
        widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS),
        help_text='Informe o setor de lotação dos servidores que atuam como secretário do CONSEPEX e CONSUP.',
        required=True,
    )
    permite_revisao_planodisciplina_em_elaboracao = forms.BooleanField(
        label='Permite revisão de PPC com plano de disciplina em elaboração',
        initial=False,
        help_text='Marque esta opção para permitir que o PPC avance para a fase de revisão com planos de disciplinas não homologados.',
        required=False,
    )
    permite_vincular_portaria_solicitacao = forms.BooleanField(
        label='Permite o vínculo de portaria de comissão de elaboração do PPC',
        initial=False,
        help_text='Marque esta opção para permitir que o solicitante vincule uma portaria finalizada da comissão de elaboração do PPC.',
        required=False,
    )
    permite_gerar_curso_matriz = forms.BooleanField(
        label='Permite gerar curso e matriz sem aprovação dos conselhos',
        initial=False,
        help_text='Marque esta opção para permitir que o Administrador Acadêmico possa gerar curso e matriz de PPC que ainda não foi aprovado pelos conselhos, É necessário que a matriz curricular e a prática profissional estejam aprovadas pelos revisores.',
        required=False,
    )
    permite_gerar_curso_sem_pafc = forms.BooleanField(
        label='Permite criar curso sem PAFC aprovado',
        initial=False,
        help_text='Marque esta opção para permitir que o Administrador Acadêmico possa gerar curso de PPC aprovado para campi sem PAFC aprovado.',
        required=False,
    )


class NucleoDiretrizForm(forms.ModelFormPlus):
    class Meta:
        model = NucleoDiretriz
        exclude = ('diretriz',)

    class Media:
        js = ('/static/ppc/js/NucleoDiretrizForm.js',)

    def __init__(self, *args, **kwargs):
        diretriz_id = kwargs.pop('diretriz_id', None)
        super().__init__(*args, **kwargs)
        if diretriz_id:
            self.instance.diretriz_id = diretriz_id
            ids = NucleoDiretriz.objects.filter(diretriz_id=diretriz_id).values_list('nucleo_id', flat=True)
            self.fields['nucleo'].queryset = Nucleo.objects.exclude(id__in=ids)

        if self.instance.id:
            del self.fields['nucleo']


class EixoTecnologicoDiretrizForm(forms.ModelFormPlus):
    class Meta:
        model = EixoTecnologicoDiretriz
        exclude = ('nucleo_diretriz',)

    def __init__(self, *args, **kwargs):
        nucleodiretriz_id = kwargs.pop('nucleodiretriz_id', None)
        super().__init__(*args, **kwargs)
        if nucleodiretriz_id:
            self.instance.nucleo_diretriz_id = nucleodiretriz_id
            ids = EixoTecnologicoDiretriz.objects.filter(nucleo_diretriz_id=nucleodiretriz_id).values_list('eixo_tecnologico_id', flat=True)
            self.fields['eixo_tecnologico'].queryset = EixoTecnologico.objects.exclude(id__in=ids)

        if self.instance.pk:
            del self.fields['eixo_tecnologico']


class PeriodoDiretrizForm(forms.ModelFormPlus):
    class Meta:
        model = PeriodoDiretriz
        exclude = ('diretriz',)

    def __init__(self, *args, **kwargs):
        diretriz = kwargs.pop('diretriz', None)
        super().__init__(*args, **kwargs)
        if diretriz:
            self.instance.diretriz = diretriz


class ComponenteExigidoDiretrizForm(forms.ModelFormPlus):
    class Meta:
        model = ComponenteExigidoDiretriz
        exclude = ('diretriz',)

    def cadastrar(self, diretriz_id):
        self.instance.diretriz_id = diretriz_id
        self.save()


class SecaoForm(forms.ModelFormPlus):
    class Meta:
        model = Secao
        exclude = ('modelo_ppc',)

    def __init__(self, *args, **kwargs):
        modelo_ppc_id = kwargs.pop('modelo_ppc_id', None)
        super().__init__(*args, **kwargs)
        if modelo_ppc_id:
            self.instance.modelo_ppc_id = modelo_ppc_id
            self.initial['ordem_exibicao'] = Secao.objects.filter(modelo_ppc_id=modelo_ppc_id).count() + 1


class ConteudoForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Ao salvar a edição o sistema irá remover as tags de formatação de texto.'

    texto = TinyMCEFormField(label='Texto', required=False, config='custom_ppc')
    remover_formatacao = forms.BooleanField(
        label='Remover formatação',
        initial=True,
        help_text='Mantenha esta opção marcada para remover do texto qualquer formatação html.',
        required=False,
    )

    fieldsets = (
        (
            '',
            {
                'fields': (
                    'secao',
                    'texto',
                    'remover_formatacao',
                    'ordem_exibicao',
                )
            },
        ),
        ('Outras informações', {'fields': ('editavel', 'orientacao_preenchimento')}),
    )

    class Meta:
        model = Conteudo
        exclude = ()

    def __init__(self, *args, **kwargs):
        modelo_ppc_id = kwargs.pop('modelo_ppc_id', None)
        super().__init__(*args, **kwargs)
        modelo_ppc_id = modelo_ppc_id or self.instance.secao.modelo_ppc_id
        self.fields['secao'].queryset = Secao.objects.filter(modelo_ppc_id=modelo_ppc_id)
        if self.instance.id and self.instance.secao.modelo_ppc.possui_ppc():
            del self.fields['texto']
            del self.fields['editavel']
            del self.fields['remover_formatacao']

    def processar(self):
        texto = self.cleaned_data.get('texto')
        remover_formatacao = self.cleaned_data.get('remover_formatacao')
        if remover_formatacao:
            self.instance.texto = PlanoDisciplina.remover_formatacao(texto)
        self.instance.save()


class EditarTextoConteudoForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Ao salvar a edição o sistema irá remover as tags de formatação de texto.'

    texto = TinyMCEFormField(label='Texto', config='custom_ppc', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.editavel:
            self.conteudos_ppcs_naohomologados = self.instance.conteudoppc_set.exclude(situacao=ConteudoPPC.HOMOLOGADO)
            lista_ppcs = (
                '<ul>\n'
                + '\n'.join(
                    [
                        f'<li><a href="{conteudoppc.ppc.get_absolute_url()}">{conteudoppc.ppc}</a></li>'
                        for conteudoppc in self.conteudos_ppcs_naohomologados
                    ]
                )
                + '\n</ul>'
            )
            if self.conteudos_ppcs_naohomologados:
                self.ALERT = mark_safe(f'A edição do texto deste conteúdo irá sobrescrever o texto dos PPCs:\n{lista_ppcs}')

            self.conteudos_ppcs_homologados = self.instance.conteudoppc_set.filter(situacao=ConteudoPPC.HOMOLOGADO)
            lista_ppcs = (
                '<ul>\n'
                + '\n'.join(
                    [
                        f'<li><a href="{conteudoppc.ppc.get_absolute_url()}">{conteudoppc.ppc}</a></li>'
                        for conteudoppc in self.conteudos_ppcs_homologados
                    ]
                )
                + '\n</ul>'
            )
            if self.conteudos_ppcs_homologados:
                self.CRITICAL = mark_safe(f'A edição do texto deste conteúdo <strong>não</strong> irá sobrescrever o texto dos PPCs:\n{lista_ppcs}')
        else:
            self.conteudos_ppcs_em_analise = self.instance.conteudoppc_set.filter(
                ppc__situacao__in=[ProjetoPedagogicoCurso.INICIADO, ProjetoPedagogicoCurso.EM_ELABORACAO, ProjetoPedagogicoCurso.EM_REVISAO]
            )
            lista_ppcs = (
                '<ul>\n'
                + '\n'.join(
                    [
                        f'<li><a href="{conteudoppc.ppc.get_absolute_url()}">{conteudoppc.ppc}</a></li>'
                        for conteudoppc in self.conteudos_ppcs_em_analise
                    ]
                )
                + '\n</ul>'
            )
            if self.conteudos_ppcs_em_analise:
                self.ALERT = mark_safe(f'A edição do texto deste conteúdo irá sobrescrever o texto dos PPCs:\n{lista_ppcs}')

    class Meta:
        model = Conteudo
        fields = ('texto',)

    def processar(self):
        texto = self.cleaned_data.get('texto')
        self.instance.atualizar_texto(PlanoDisciplina.remover_formatacao(texto))


class ConteudoPPCForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Ao salvar a edição o sistema irá remover as tags de formatação de texto.'

    texto = TinyMCEFormField(label='Texto', config='custom_ppc', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['texto'].help_text = self.instance.conteudo_modelo.orientacao_preenchimento

    def clean_texto(self):
        texto = self.cleaned_data.get('texto')
        return texto and PlanoDisciplina.remover_formatacao(texto) or self.cleaned_data.get('texto')


class RevisarConteudoPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ConteudoPPC
        fields = ('parecer_revisor',)

    def processar(self, user):
        return self.instance.enviar_para_correcao(user)


class ReplicarDiretrizForm(forms.ModelFormPlus):
    class Meta:
        model = Diretriz
        fields = ('descricao', 'ano', 'estrutura_curso', 'tipo_oferta', 'modalidade', 'arquivo')

    def __init__(self, *args, **kwargs):
        origem = kwargs.pop('diretriz', None)
        super().__init__(*args, **kwargs)
        if origem:
            self.initial['ano'] = origem.ano
            self.initial['estrutura_curso'] = origem.estrutura_curso
            self.initial['tipo_oferta'] = origem.tipo_oferta
            self.initial['modalidade'] = origem.modalidade

    def replicar(self, diretriz):
        descricao = self.cleaned_data.get('descricao')
        ano = self.cleaned_data.get('ano')
        estrutura_curso = self.cleaned_data.get('estrutura_curso')
        tipo_oferta = self.cleaned_data.get('tipo_oferta')
        modalidade = self.cleaned_data.get('modalidade')
        arquivo = self.cleaned_data.get('arquivo')
        return diretriz.replicar(descricao, ano, estrutura_curso, tipo_oferta, modalidade, arquivo)


class ReplicarModeloPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ModeloPPC
        fields = ('descricao', 'tipo_oferta', 'modalidade')

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and not user.has_perm('comum.is_administrador_academico') and not user.has_perm('comum.is_administrador_de_ppc'):
            ids = AdministradorTipoOferta.objects.filter(servidores__matricula=user.username).values_list('tipo_oferta_id', flat=True)
            self.fields['tipo_oferta'].queryset = Modalidade.objects.filter(id__in=ids)

    def clean(self):
        data = self.cleaned_data
        tipo_oferta = data.get('tipo_oferta')
        modalidade = data.get('modalidade')
        if ModeloPPC.objects.filter(ativo=True, tipo_oferta_id=tipo_oferta.id, modalidade_id=modalidade.id).exists():
            raise forms.ValidationError('Já existe um modelo de PPC ativo para este tipo de oferta e modalidade.')
        return data

    def replicar(self, modelo):
        descricao = self.cleaned_data.get('descricao')
        tipo_oferta = self.cleaned_data.get('tipo_oferta')
        modalidade = self.cleaned_data.get('modalidade')
        return modelo.replicar(descricao, tipo_oferta, modalidade)


class ReplicarModeloPlanoDisciplinaForm(forms.ModelFormPlus):
    class Meta:
        model = ModeloPlanoDisciplina
        fields = ('descricao', 'nivel_ensino')

    def clean(self):
        data = self.cleaned_data
        nivel_ensino = data.get('nivel_ensino')
        if ModeloPlanoDisciplina.objects.filter(ativo=True, nivel_ensino_id=nivel_ensino.id).exists():
            raise forms.ValidationError('Já existe um modelo de plano de disciplina ativo para este nível de ensino.')
        return data

    def replicar(self, modelo):
        descricao = self.cleaned_data.get('descricao')
        nivel_ensino = self.cleaned_data.get('nivel_ensino')
        return modelo.replicar(descricao, nivel_ensino)


class ModeloSecaoPlanoDisciplinaForm(forms.ModelFormPlus):
    class Meta:
        model = ModeloSecaoPlanoDisciplina
        exclude = ('modelo_plano_disciplina',)

    def __init__(self, *args, **kwargs):
        modelo_plano_disciplina_id = kwargs.pop('modelo_plano_disciplina_id', None)
        super().__init__(*args, **kwargs)
        if modelo_plano_disciplina_id:
            self.instance.modelo_plano_disciplina_id = modelo_plano_disciplina_id
            self.initial['ordem_exibicao'] = (
                ModeloSecaoPlanoDisciplina.objects.filter(modelo_plano_disciplina_id=modelo_plano_disciplina_id).count() + 1
            )


class SolicitacaoPPCForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.id:
            self.instance.tipo_solicitacao = self.request.GET.get('tipo', SolicitacaoPPC.TIPO_CRIACAO)
        if self.instance.tipo_solicitacao == SolicitacaoPPC.TIPO_ADEQUACAO:
            self.fields['ppc_adequacao'].queryset = ProjetoPedagogicoCurso.objects.filter(situacao=ProjetoPedagogicoCurso.FINALIZADO)
            self.fields['ppc_adequacao'].required = True
        else:
            self.fields['nome_curso'].required = True
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            from processo_eletronico.models import Processo

            self.fields['id_processo_convenio'] = forms.ModelChoiceFieldPlus(
                Processo.objects.all(), label='Processo do convênio', widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS), required=False
            )

    def clean_id_processo_convenio(self):
        processo = self.cleaned_data.get('id_processo_convenio')
        return processo and processo.id or None

    def save(self, *args, **kwargs):
        self.instance.solicitante = self.request.user.get_vinculo().relacionamento
        self.instance.setor_solicitacao = self.request.user.get_vinculo().setor
        if self.instance.is_adequacao():
            self.instance.tipo_oferta = self.instance.ppc_adequacao.tipo_oferta
            self.instance.modalidade = self.instance.ppc_adequacao.modalidade
        if self.instance.tipo_oferta.nivel_ensino_id != NivelEnsino.MEDIO:
            self.instance.eixo_tecnologico_id = None
        return super().save(*args, **kwargs)


class VincularPortariaSolicitacaoPPCForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoPPC
        fields = ('id_portaria',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            self.fields['id_portaria'] = forms.ModelChoiceFieldPlus(
                DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO),
                label='Portaria de elaboração do PPC',
                widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
                required=False,
            )

    def clean_id_portaria(self):
        portaria = self.cleaned_data.get('id_portaria')
        return portaria and portaria.id or None


class MembroColegiadoForm(forms.ModelFormPlus):
    class Meta:
        model = MembroColegiado
        exclude = ('solicitacao',)

    def cadastrar(self, pk):
        self.instance.solicitacao_id = pk
        self.save()


class SolicitarAvaliacaoElaboradorForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoPPC
        fields = ('setor_avaliacao',)

    def processar(self, user):
        self.instance.enviar_analise(user)


class IndicacaoElaboradorPPCForm(forms.ModelFormPlus):
    class Meta:
        model = IndicacaoElaboradorPPC
        fields = ('vinculo', 'funcao', 'representacao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id:
            del self.fields['vinculo']
        else:
            self.fields['vinculo'].queryset = Vinculo.objects.filter(ativo=True, tipo_relacionamento__model__in=['prestadorservico', 'servidor'])

    def cadastrar(self, pk, user):
        solicitacao = SolicitacaoPPC.objects.get(id=pk)
        if solicitacao.is_avaliador_indicacao(user):
            self.instance.deferido = True
            self.instance.avaliador = user.get_relacionamento()
        self.instance.solicitacao_id = pk
        self.save()


class RejeitarIndicacaoElaboradorPPCForm(forms.ModelFormPlus):
    class Meta:
        model = IndicacaoElaboradorPPC
        fields = ('justificativa_rejeicao',)

    def processar(self, user):
        self.instance.negar(user)


class RejeitarSolicitacaoPPCForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoPPC
        fields = ('motivo_rejeicao',)

    def processar(self, user):
        self.instance.rejeitar(user)


class DevolverSolicitacaoPPCForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoPPC
        fields = ('justificativa_correcao',)

    def processar(self, user):
        self.instance.devolver(user)


class ElaboradorPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ElaboradorPPC
        exclude = ('ppc', 'servidor')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['data_inicial'] = datetime.date.today()
        if self.instance.id:
            del self.fields['vinculo']
            del self.fields['funcao']
            del self.fields['data_inicial']

    def cadastrar(self, ppc_id):
        self.instance.adicionar_elaborador(ppc_id)


class ColaboradorPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ColaboradorPPC
        exclude = ('ppc',)

    def __init__(self, *args, **kwargs):
        ppc_id = kwargs.pop('ppc_id', None)
        super().__init__(*args, **kwargs)
        if ppc_id:
            self.instance.ppc_id = ppc_id

        if self.instance.id:
            del self.fields['servidor']
        else:
            del self.fields['ativo']


class RevisorPPCForm(forms.ModelFormPlus):
    class Meta:
        model = RevisorPPC
        exclude = ('ppc', 'data_inicial', 'data_final')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id:
            del self.fields['servidor']

    def cadastrar(self, ppc_id):
        self.instance.ppc_id = ppc_id
        self.instance.data_inicial = datetime.date.today()
        return self.save()


class ComentarioConteudoPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ComentarioConteudoPPC
        exclude = ('conteudo_ppc', 'revisor')

    def cadastrar(self, conteudo_ppc_id, user):
        self.instance.conteudo_ppc_id = conteudo_ppc_id
        self.instance.revisor = user.get_relacionamento()
        return self.save()


class SecaoPlanoDisciplinaForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Isso pode causar erros de visualização na geração do PDF.'

    texto = TinyMCEFormField(label='Texto', config='custom_ppc', required=True)
    remover_formatacao = forms.BooleanField(
        label='Remover formatação',
        initial=True,
        help_text='Mantenha esta opção marcada para remover do texto qualquer formatação html.',
        required=False,
    )

    class Meta:
        model = SecaoPlanoDisciplina
        fields = ('texto',)

    def __init__(self, *args, **kwargs):
        plano_disciplina_id = kwargs.pop('plano_disciplina_id', None)
        super().__init__(*args, **kwargs)
        if plano_disciplina_id:
            self.instance.plano_disciplina_id = plano_disciplina_id
            self.initial['ordem_exibicao'] = SecaoPlanoDisciplina.objects.filter(plano_disciplina_id=plano_disciplina_id).count() + 1

    def processar(self):
        texto = self.cleaned_data.get('texto')
        remover_formatacao = self.cleaned_data.get('remover_formatacao')
        if remover_formatacao:
            self.instance.texto = PlanoDisciplina.remover_formatacao(texto)
        self.instance.save()


class PlanoDisciplinaForm(forms.ModelFormPlus):
    equivalencia_hr_ha = forms.CharFieldPlus(widget=forms.HiddenInput())

    class Meta:
        model = PlanoDisciplina
        fields = (
            'nome_disciplina',
            'diretriz',
            'ch_disciplina',
            'desconsiderar_qtd_credito',
            'periodicidade',
            'comissao_ptdem',
            'nucleo',
            'topico_especifico',
        )

    class Media:
        js = ('/static/ppc/js/PlanoDisciplinaForm.js',)

    def __init__(self, *args, **kwargs):
        nucleo_id = kwargs.pop('nucleo_id', None)
        diretriz_id = kwargs.pop('diretriz_id', None)
        super().__init__(*args, **kwargs)
        if nucleo_id and diretriz_id:
            # criação a partir do PPC
            del self.fields['comissao_ptdem']
        elif self.instance.id and self.instance.comissao_ptdem is None:
            # edição a partir do PPC
            self.fields['comissao_ptdem'].widget = forms.HiddenInput()
        else:
            # criação por membro da PTDEM
            self.fields['comissao_ptdem'].required = True
            comissoes = ComissaoPTDEM.objects.filter(servidores__matricula=self.request.user.username)
            ids_nucleos = list(comissoes.values_list('nucleos', flat=True))
            if comissoes:
                self.fields['comissao_ptdem'].queryset = comissoes
                if ids_nucleos != [None]:
                    self.fields['nucleo'].queryset = Nucleo.objects.filter(id__in=ids_nucleos)
            else:
                self.fields['comissao_ptdem'].queryset = ComissaoPTDEM.objects.none()
            if comissoes.count() == 1:
                self.initial['comissao_ptdem'] = comissoes[0]
            if len(ids_nucleos) == 1 and ids_nucleos != [None]:
                self.initial['nucleo'] = ids_nucleos[0]

        if nucleo_id:
            del self.fields['nucleo']
            self.instance.nucleo_id = nucleo_id
        elif self.instance.id and self.instance.comissao_ptdem is None:
            self.fields['nucleo'].widget = forms.HiddenInput()

        if diretriz_id:
            del self.fields['diretriz']
            self.instance.diretriz_id = diretriz_id
        elif self.instance.id and self.instance.comissao_ptdem is None:
            self.fields['diretriz'].widget = forms.HiddenInput()

        if self.instance.diretriz:
            self.fields['equivalencia_hr_ha'].initial = self.instance.diretriz.equivalencia_hr_ha

        self.fields['ch_disciplina'].help_text = ' '

    def clean_nucleo(self):
        nucleo = self.cleaned_data.get('nucleo')
        comissao_ptdem = self.cleaned_data.get('comissao_ptdem')
        if comissao_ptdem and comissao_ptdem.nucleos.count() and nucleo not in comissao_ptdem.nucleos.all():
            raise forms.ValidationError(f'O núcleo informado não faz parte da comissão de {comissao_ptdem}.')
        return nucleo

    def clean_ch_disciplina(self):
        ch_disciplina = self.cleaned_data.get('ch_disciplina')
        if self.instance.id and self.instance.planodisciplinappc_set.exists() and self.instance.comissao_ptdem is not None:
            old = PlanoDisciplina.objects.filter(id=self.instance.id).only('ch_disciplina')[0]
            if ch_disciplina != old.ch_disciplina:
                raise forms.ValidationError('A CH não pode ser alterada, pois este plano está associado a um ou mais PPCs.')
        return ch_disciplina

    def processar(self, matriz_ppc, user):
        return self.instance.vincular_planodisciplinappc(matriz_ppc, user)


class EmentaPlanoDisciplinaForm(forms.ModelFormPlus):
    INFO = 'Evite copiar o conteúdo de outro editor de texto. Isso pode causar erros de visualização na geração do PDF.'

    ementa = TinyMCEFormField(label='Ementa', config='custom_ppc', required=True)
    remover_formatacao = forms.BooleanField(
        label='Remover formatação',
        initial=True,
        help_text='Mantenha esta opção marcada para remover do texto qualquer formatação html.',
        required=False,
    )

    class Meta:
        model = PlanoDisciplina
        fields = ('ementa',)

    def processar(self):
        ementa = self.cleaned_data.get('ementa')
        remover_formatacao = self.cleaned_data.get('remover_formatacao')
        if remover_formatacao:
            self.instance.ementa = PlanoDisciplina.remover_formatacao(ementa)
        self.instance.save()


class RequisitosPlanoDisciplinaPPCForm(forms.ModelForm):
    pre_requisitos = forms.MultipleModelChoiceFieldPlus(PlanoDisciplinaPPC.objects, label='Pré-requisitos', required=False)
    co_requisitos = forms.MultipleModelChoiceFieldPlus(PlanoDisciplinaPPC.objects, label='Co-requisitos', required=False)

    class Meta:
        model = PlanoDisciplinaPPC
        fields = (
            'pre_requisitos',
            'co_requisitos',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = PlanoDisciplinaPPC.objects.filter(
            matriz_ppc_id=self.instance.matriz_ppc_id, plano_disciplina__tipo_oferta_id=self.instance.plano_disciplina.tipo_oferta_id
        ).exclude(id=self.instance.id)
        if self.instance.periodo_oferta:
            self.fields['pre_requisitos'].queryset = qs.filter(periodo_oferta__lt=self.instance.periodo_oferta)
            self.fields['co_requisitos'].queryset = qs.filter(periodo_oferta__lte=self.instance.periodo_oferta)
        else:
            self.fields['pre_requisitos'].queryset = qs
            self.fields['co_requisitos'].queryset = qs


class PlanoDisciplinaPPCForm(forms.ModelFormPlus):
    info_ead = forms.CharFieldPlus(widget=forms.HiddenInput(), required=False)
    ch_disciplina = forms.CharFieldPlus(widget=forms.HiddenInput(), required=False)

    fieldsets = [
        (
            'Dados gerais',
            {
                'fields': (
                    'plano_disciplina',
                    ('tipo', 'quantidade_etapas'),
                    ('periodo_oferta', 'optativo'),
                    ('segundo_semestre', 'pode_fechar_pendencia'),
                    ('qtd_aulas_1s',),
                    'plano_disciplinappc_associado',
                )
            },
        ),
        (
            'Carga horária',
            {
                'fields': (
                    ('ch_teorica', 'ch_extensao'),
                    (
                        'info_ead',
                        'ch_disciplina',
                    ),
                )
            },
        ),
        (
            'Configuração EAD',
            {
                'fields': (
                    'qtd_aulas_ead',
                    ('qtd_aulas_sincronas_ead', 'qtd_aulas_assincronas_ead'),
                )
            },
        ),
        (
            'Projeto integrador',
            {'fields': ('modalidade_projetointegrador', 'planos_associados_projetointegrador')},
        ),
    ]

    class Meta:
        model = PlanoDisciplinaPPC
        fields = (
            'plano_disciplina',
            'periodo_oferta',
            'optativo',
            'tipo',
            'quantidade_etapas',
            'qtd_aulas_1s',
            'segundo_semestre',
            'pode_fechar_pendencia',
            'qtd_aulas_ead',
            'ch_teorica',
            'ch_extensao',
            'qtd_aulas_sincronas_ead',
            'qtd_aulas_assincronas_ead',
            'plano_disciplinappc_associado',
            'modalidade_projetointegrador',
            'planos_associados_projetointegrador',
        )

    class Media:
        js = ('/static/ppc/js/PlanoDisciplinaPPCForm.js',)

    def __init__(self, *args, **kwargs):
        nucleo_id = kwargs.pop('nucleo_id', None)
        matrizppc = kwargs.pop('matrizppc', None)
        plano_disciplina_id = kwargs.pop('plano_disciplina_id', None)
        super().__init__(*args, **kwargs)
        if nucleo_id and matrizppc:
            self.instance.matriz_ppc = matrizppc
            plano_disciplinas_vinculadas = PlanoDisciplinaPPC.objects.filter(matriz_ppc_id=matrizppc.id).values_list('plano_disciplina_id', flat=True)
            qs_pd = (
                PlanoDisciplina.objects.filter(nucleo_id=nucleo_id, diretriz__tipo_oferta_id=matrizppc.ppc.diretriz.tipo_oferta_id, ativo=True)
                .exclude(id__in=plano_disciplinas_vinculadas)
                .exclude(situacao=PlanoDisciplina.REJEITADO)
            )
            if not matrizppc.ppc.diretriz.permite_plano_nao_aprovado:
                qs_pd = qs_pd.exclude(situacao=PlanoDisciplina.ELABORACAO, comissao_ptdem__isnull=True) | qs_pd.filter(
                    planodisciplinappc__matriz_ppc__ppc_id=matrizppc.ppc_id
                )
            if matrizppc.ppc.is_curso_semestral():
                qs_pd = qs_pd.exclude(periodicidade=PlanoDisciplina.PERIODICIDADE_ANUAL)
            self.fields['plano_disciplina'].queryset = qs_pd.distinct()

        if plano_disciplina_id:
            self.initial['plano_disciplina'] = plano_disciplina_id

        if matrizppc is None:
            matrizppc = self.instance.matriz_ppc_id and self.instance.matriz_ppc or None

        if matrizppc:
            self.fields['periodo_oferta'].help_text = f'O período de oferta deste plano não pode exceder {matrizppc.quantidade_periodos}.'

            if matrizppc.ppc.is_curso_semestral():
                self.fields['quantidade_etapas'].choices = [[0, 'Zero'], [1, 'Uma'], [2, 'Duas']]

            plano = (
                plano_disciplina_id
                and PlanoDisciplina.objects.get(id=plano_disciplina_id)
                or self.instance.plano_disciplina_id
                and self.instance.plano_disciplina
                or None
            )

            if matrizppc.ppc.diretriz.possui_ch_ead():
                self.fields['info_ead'].initial = matrizppc.ppc.diretriz.equivalencia_hr_ha
                self.fields['ch_disciplina'].initial = plano.ch_disciplina if plano else 0
                self.fields['qtd_aulas_ead'].help_text = ' '
            else:
                self.fields['qtd_aulas_ead'].widget = forms.HiddenInput()
                self.initial['qtd_aulas_ead'] = 0
                self.initial['info_ead'] = 0
                self.initial['ch_disciplina'] = 0

            if matrizppc.ppc.diretriz.exige_etapa_unica:
                self.initial['quantidade_etapas'] = 1
                self.fields['quantidade_etapas'].widget = forms.HiddenInput()
            else:
                if plano and matrizppc.ppc.is_curso_anual():
                    if plano.periodicidade == PlanoDisciplina.PERIODICIDADE_ANUAL:
                        self.initial['quantidade_etapas'] = 4
                        self.fields['quantidade_etapas'].widget = forms.HiddenInput()
                    elif plano.periodicidade == PlanoDisciplina.PERIODICIDADE_SEMESTRAL:
                        self.initial['quantidade_etapas'] = 2
                        self.fields['quantidade_etapas'].widget = forms.HiddenInput()

            if (
                self.instance.qtd_aulas_1s is None
                and not (matrizppc.ppc.is_curso_anual() and (self.instance.quantidade_etapas == 4 or self.instance.quantidade_etapas is None))
                or (plano and plano.desconsiderar_qtd_credito)
            ):
                self.fields['qtd_aulas_1s'].widget = forms.HiddenInput()

            qs_planos_matriz = matrizppc.get_planos_disciplinappc()
            if plano:
                qs_planos_matriz = qs_planos_matriz.exclude(plano_disciplina_id=plano.id)

            # projeto integrador
            qs_modalidade_projetointegrador = self.fields['modalidade_projetointegrador'].queryset.filter(
                id__in=matrizppc.get_modalidades_praticaprofissionalppc_projeto_integrador().values_list(
                    'modalidade_pratica_profissional_id', flat=True
                )
            )
            if qs_modalidade_projetointegrador.exists():
                self.fields['modalidade_projetointegrador'].queryset = qs_modalidade_projetointegrador
                self.fields['planos_associados_projetointegrador'].queryset = qs_planos_matriz
            else:
                self.fields['modalidade_projetointegrador'].widget = forms.HiddenInput()
                self.fields['planos_associados_projetointegrador'].widget = forms.MultipleHiddenInput()

            if self.instance.periodo_oferta:
                qs_planos_matriz = qs_planos_matriz.filter(periodo_oferta=self.instance.periodo_oferta)
            self.fields['plano_disciplinappc_associado'].queryset = qs_planos_matriz

            plano_principal = self.instance.get_plano_disciplinappc_principal()
            if plano_principal:
                self.fields['periodo_oferta'].widget = forms.HiddenInput()
                self.fields['optativo'].widget = forms.HiddenInput()
                self.fields['pode_fechar_pendencia'].widget = forms.HiddenInput()
                self.fields['segundo_semestre'].widget = forms.HiddenInput()
                self.fields['plano_disciplinappc_associado'].widget = forms.HiddenInput()
                self.instance.plano_principal = plano_principal

    def clean(self):
        total = self.cleaned_data.get('qtd_aulas_ead') or 0
        sincrona = self.cleaned_data.get('qtd_aulas_sincronas_ead') or 0
        assincrona = self.cleaned_data.get('qtd_aulas_assincronas_ead') or 0
        if total != (sincrona + assincrona):
            raise forms.ValidationError('A soma da carga horária síncrona e assíncrona EAD tem que ser igual à carga horária EAD.')
        return super().clean()

    def clean_planos_associados_projetointegrador(self):
        planos_associados_projetointegrador = self.cleaned_data.get(
            'planos_associados_projetointegrador',
        )
        modalidade_projetointegrador = self.cleaned_data.get('modalidade_projetointegrador', None)
        if planos_associados_projetointegrador and modalidade_projetointegrador is None:
            raise forms.ValidationError(
                'Não é possível associar planos de projeto integrador pois nenhuma modalidade de prática profissional foi informada.'
            )
        return planos_associados_projetointegrador


class ModalidadePraticaProfissionalDiretrizForm(forms.ModelFormPlus):
    class Meta:
        model = ModalidadePraticaProfissionalDiretriz
        exclude = ('nucleo_diretriz',)

    def __init__(self, *args, **kwargs):
        nucleo_diretriz_id = kwargs.pop('nucleo_diretriz_id', None)
        super().__init__(*args, **kwargs)
        if nucleo_diretriz_id:
            self.instance.nucleo_diretriz_id = nucleo_diretriz_id


class ModalidadePraticaProfissionalPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ModalidadePraticaProfissionalPPC
        exclude = ('matriz_ppc', 'nucleo', 'exigido_diretriz', 'ppc')

    def __init__(self, *args, **kwargs):
        matriz_ppc_id = kwargs.pop('matriz_ppc_id', None)
        nucleo_id = kwargs.pop('nucleo_id', None)
        super().__init__(*args, **kwargs)
        if nucleo_id:
            self.instance.nucleo_id = nucleo_id
        if matriz_ppc_id:
            self.instance.matriz_ppc_id = matriz_ppc_id


class GerarMatrizPPCForm(forms.ModelFormPlus):
    tipo_tramitacao = forms.ChoiceField(
        label='Tipo de tramitação', widget=forms.RadioSelect(), choices=ProjetoPedagogicoCurso.TIPO_TRAMITACAO_CHOICES, required=True
    )
    vincular_curso = forms.BooleanField(
        label='Vincular matriz a curso',
        initial=False,
        help_text='Marque esta opção para que a matriz curricular criada possa ser vinculada automaticamente aos cursos existentes deste PPC de adequação.',
        required=False,
    )
    cod_outros_cursos = forms.CharFieldPlus(
        label='Outros códigos de curso',
        help_text='Utilize este campo para indicar os códigos de curso que devem ser vinculados a esta matriz e que não estão no padrão [CÓDIGO CAMPUS][IDENTIFICADOR PPC]. Caso exista mais de um (1), separe por ";" sem espaços.',
        required=False,
    )
    diretorias = forms.MultipleModelChoiceFieldPlus(
        Diretoria.objects.all(),
        label='Diretorias Acadêmicas',
        required=False,
        widget=forms.CheckboxSelectMultiplePlus(),
        help_text='Informe as diretorias acadêmicas que terão cursos gerados a partir deste PPC de criação.',
    )
    confirmacao = forms.BooleanField(
        label='Gerar matriz curricular',
        initial=False,
        help_text='Confirme que você deseja gerar a matriz curricular deste PPC. Esta ação é irreversível.',
        required=True,
    )

    fieldsets = (
        (
            'Dados do PPC',
            {
                'fields': (
                    'identificador_ppc',
                    'nome_diploma_historico',
                    'titulo_certificado_masculino',
                    'titulo_certificado_feminino',
                    'tipo_tramitacao',
                    'vincular_curso',
                    'cod_outros_cursos',
                    'diretorias',
                )
            },
        ),
        ('Confirme a operação', {'fields': ('confirmacao',)}),
    )

    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('identificador_ppc', 'tipo_tramitacao', 'nome_diploma_historico', 'titulo_certificado_masculino', 'titulo_certificado_feminino')

    class Media:
        js = ('/static/ppc/js/GerarMatrizPPCForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['identificador_ppc'].required = True

        ids_diretorias = self.instance.matrizppc_set.first().cursos.values_list('diretoria_id', flat=True)
        self.fields['diretorias'].queryset = Diretoria.objects.exclude(id__in=ids_diretorias)

        if self.instance.data_aprovacao:
            del self.fields['tipo_tramitacao']
            if not Configuracao.get_valor_por_chave('ppc', 'permite_gerar_curso_sem_pafc'):
                if 'pafc' in settings.INSTALLED_APPS:
                    pass
                    # TODO: exibir apenas campus com pafc aprovado vinculado a este PPC
                    # self.fields['diretorias'].queryset = Diretoria.objects.filter(?)
                    # PAFC: pafc terá referencia a ppc. Pafc deverá verificar se curso já foi criado pelo PPC. PAFC exibe alerta de curso criado sem aprovação de PAFC e alerta de pafc aprovado sem curso criado. PAFC terá ação de criar curso quando PAFC aprovado e PPC aprovado. PAFC deverá atualizar lista de cursos criados do PPC após criação de curso pelo PAFC

        else:
            self.ALERT = mark_safe(
                'A matriz curricular deste PPC será gerada sem a aprovação dos conselhos. <strong>Não</strong> será possível desfazer a aprovação da matriz curricular ou prática profissional deste PPC após isso.'
            )

        if self.instance.is_tramite_criacao():
            self.initial['vincular_curso'] = False
            # self.fields['vincular_curso'].widget = forms.HiddenInput()
            # self.fields['cod_outros_cursos'].widget = forms.HiddenInput()
        elif self.instance.is_tramite_adequacao():
            self.initial['diretorias'] = []
            # self.fields['diretorias'].widget = forms.HiddenInput()

        if self.instance.nome_diploma_historico:
            self.fields['nome_diploma_historico'].widget = forms.HiddenInput()
        else:
            self.fields['nome_diploma_historico'].required = True

        if self.instance.titulo_certificado_masculino:
            self.fields['titulo_certificado_masculino'].widget = forms.HiddenInput()
        else:
            self.fields['titulo_certificado_masculino'].required = True

        if self.instance.titulo_certificado_feminino:
            self.fields['titulo_certificado_feminino'].widget = forms.HiddenInput()
        else:
            self.fields['titulo_certificado_feminino'].required = True

    def processar(self, user):
        if self.cleaned_data.get('confirmacao', False):
            vincular_curso = self.cleaned_data.get('vincular_curso', False)
            cod_outros_cursos = self.cleaned_data.get('cod_outros_cursos', '')
            diretorias = self.cleaned_data.get('diretorias', [])
            self.instance.gerar_matrizes(user, vincular_curso, cod_outros_cursos, diretorias)


class VincularCursoPPCForm(forms.ModelFormPlus):
    vincular_curso = forms.BooleanField(
        label='Vincular matriz a curso',
        initial=False,
        help_text='Marque esta opção para que a matriz curricular criada possa ser vinculada automaticamente aos cursos existentes deste PPC de adequação.',
        required=False,
    )
    cod_outros_cursos = forms.CharFieldPlus(
        label='Outros códigos de curso',
        help_text='Utilize este campo para indicar os códigos de curso que devem ser vinculados a esta matriz e que não estão no padrão [CÓDIGO CAMPUS][IDENTIFICADOR PPC]. Caso exista mais de um (1), separe por ";" sem espaços.',
        required=False,
    )
    confirmacao = forms.BooleanField(
        label='Vincular cursos à matriz curricular',
        initial=False,
        help_text='Confirme que você deseja vincular os cursos à matriz curricular deste PPC.',
        required=True,
    )

    fieldsets = (
        (
            'Dados de curso',
            {
                'fields': (
                    'vincular_curso',
                    'cod_outros_cursos',
                )
            },
        ),
        ('Confirme a operação', {'fields': ('confirmacao',)}),
    )

    class Meta:
        model = MatrizPPC
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.INFO = mark_safe(f'O código identificador deste PPC é <strong>{self.instance.ppc.identificador_ppc}</strong>.')

    def processar(self, user):
        if self.cleaned_data.get('confirmacao', False):
            vincular_curso = self.cleaned_data.get('vincular_curso', False)
            cod_outros_cursos = self.cleaned_data.get('cod_outros_cursos', '')
            self.instance.gerar_matriz(user, vincular_curso, cod_outros_cursos, None)


class GerarCursoPPCForm(forms.ModelFormPlus):
    diretorias = forms.MultipleModelChoiceFieldPlus(
        Diretoria.objects.all(),
        label='Diretorias Acadêmicas',
        required=False,
        widget=forms.CheckboxSelectMultiplePlus(),
        help_text='Informe as diretorias acadêmicas que terão cursos gerados a partir deste PPC de criação.',
    )
    confirmacao = forms.BooleanField(
        label='Gerar cursos',
        initial=False,
        help_text='Confirme que você deseja criar os cursos vinculados à matriz curricular deste PPC. Esta ação é irreversível.',
        required=True,
    )

    fieldsets = (
        ('Dados de Curso', {'fields': ('diretorias',)}),
        ('Confirme a operação', {'fields': ('confirmacao',)}),
    )

    class Meta:
        model = MatrizPPC
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        ids_diretorias = self.instance.cursos.values_list('diretoria_id', flat=True)
        self.fields['diretorias'].queryset = Diretoria.objects.exclude(id__in=ids_diretorias)

        if self.instance.ppc.data_aprovacao:
            if not Configuracao.get_valor_por_chave('ppc', 'permite_gerar_curso_sem_pafc'):
                if 'pafc' in settings.INSTALLED_APPS:
                    pass
                    # TODO: exibir apenas campus com pafc aprovado vinculado a este PPC
                    # self.fields['diretorias'].queryset = Diretoria.objects.filter(?)

        self.INFO = mark_safe(f'O código identificador deste PPC é <strong>{self.instance.ppc.identificador_ppc}</strong>.')

    def processar(self, user):
        if self.cleaned_data.get('confirmacao', False):
            diretorias = self.cleaned_data.get('diretorias', [])
            self.instance.gerar_matriz(user, None, None, diretorias)


class VincularDocumentoPPCForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoPPC
        fields = ('id_documento',)

    def __init__(self, *args, **kwargs):
        documentoppc_referencia = kwargs.pop('documentoppc', None)
        super().__init__(*args, **kwargs)
        self.instance.ppc_id = documentoppc_referencia.ppc_id
        self.instance.situacao_ppc = documentoppc_referencia.situacao_ppc
        self.instance.situacao_documento = DocumentoPPC.DOCUMENTO_FINALIZADO
        self.instance.tipo_documento = documentoppc_referencia.tipo_documento
        self.instance.ad_referendum = documentoppc_referencia.ad_referendum
        self.instance.rejeicao = documentoppc_referencia.rejeicao
        self.instance.decisao = documentoppc_referencia.decisao

        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            self.fields['id_documento'] = forms.ModelChoiceFieldPlus(
                DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO),
                label='Documento eletrônico',
                widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
                required=True,
            )

    def clean_id_documento(self):
        documento = self.cleaned_data.get('id_documento')
        if documento:
            self.instance.emissor = documento.usuario_criacao.get_relacionamento()
            self.instance.data_emissao = documento.data_criacao
            return documento.id
        raise forms.ValidationError('Este campo é obrigatório.')


class EmitirDocumentoForm(forms.ModelFormPlus):
    setor = forms.ModelChoiceField(
        Setor.objects.suap_ativos(), label='Setor de emissão', widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS), required=True
    )
    documento_eletronico = forms.CharFieldPlus(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ()

    def __init__(self, *args, **kwargs):
        setor_id = kwargs.pop('setor_id', None)
        documento_existe = kwargs.pop('documento_existe', False)
        super().__init__(*args, **kwargs)

        if documento_existe:
            if 'documento_eletronico' in settings.INSTALLED_APPS:
                from documento_eletronico.models import DocumentoStatus, DocumentoTexto

                self.fields['documento_eletronico'] = forms.ModelChoiceFieldPlus(
                    DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO),
                    label='Documento eletrônico',
                    widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
                    required=True,
                )
                self.fields['setor'].widget = forms.HiddenInput()

        if setor_id:
            self.initial['setor'] = setor_id

    def processar(self):
        ppc = self.save()
        return ppc, self.cleaned_data.get('setor'), self.cleaned_data.get('documento_eletronico')


class EmitirParecerRevisaoForm(EmitirDocumentoForm):
    tipo_tramitacao = forms.ChoiceField(
        label='Tipo de tramitação', widget=forms.RadioSelect(), choices=ProjetoPedagogicoCurso.TIPO_TRAMITACAO_CHOICES, required=True
    )

    class Meta:
        model = ProjetoPedagogicoCurso
        fields = (
            'tipo_tramitacao',
            'resolucao_criacao',
            'url_resolucao_criacao',
            'proreitoria',
        )

    class Media:
        js = ('/static/ppc/js/EmitirParecerRevisaoForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.decisao_camara:
            del self.fields['proreitoria']
        else:
            qs = ProReitoria.objects.filter(ativo=True, tipos_oferta__id=self.instance.diretriz.tipo_oferta_id)
            if qs.count() == 1:
                self.instance.proreitoria = qs[0]
                del self.fields['proreitoria']
            else:
                self.fields['proreitoria'].queryset = qs

        if self.instance.matrizppc_set.filter(matriz_id__isnull=False).exists():
            del self.fields['tipo_tramitacao']
            if self.instance.is_tramite_criacao():
                del self.fields['resolucao_criacao']
                del self.fields['url_resolucao_criacao']

    def clean(self):
        data = self.cleaned_data
        tipo_tramitacao = data.get('tipo_tramitacao') or self.instance.tipo_tramitacao
        resolucao_criacao = data.get('resolucao_criacao')
        if tipo_tramitacao and int(tipo_tramitacao) == ProjetoPedagogicoCurso.TIPO_TRAMITACAO_ADEQUACAO and resolucao_criacao is None:
            raise forms.ValidationError('Informe a resolução de aprovação do curso deste PPC.')
        return data


class EmitirDespachoProReitoriaForm(EmitirDocumentoForm):
    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('rejeitado_proreitoria', 'camara', 'ad_referendum', 'pular_camara')

    class Media:
        js = ('/static/ppc/js/EmitirDespachoProReitoriaForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        qs = Camara.objects.filter(ativo=True, tipos_oferta__id=self.instance.diretriz.tipo_oferta_id)
        if qs.count() == 1:
            self.instance.camara = qs[0]
            del self.fields['camara']
        else:
            self.fields['camara'].queryset = qs

        if self.instance.matrizppc_set.filter(matriz_id__isnull=False).exists():
            del self.fields['rejeitado_proreitoria']

    def clean_camara(self):
        rejeitado_proreitoria = self.cleaned_data.get('rejeitado_proreitoria')
        camara = self.cleaned_data.get('camara') or self.instance.camara
        if rejeitado_proreitoria is False and camara is None:
            raise forms.ValidationError('Este campo é obrigatório.')
        return camara

    def clean_pular_camara(self):
        ad_referendum = self.cleaned_data.get('ad_referendum')
        pular_camara = self.cleaned_data.get('pular_camara')
        if ad_referendum is False and pular_camara is True:
            raise forms.ValidationError('Este campo não pode ser marcado se a tramitação não for Ad Referendum.')
        return pular_camara


class EmitirParecerCamaraForm(EmitirDocumentoForm):
    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('decisao_camara',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.matrizppc_set.filter(matriz_id__isnull=False).exists():
            situacoes = copy.copy(ProjetoPedagogicoCurso.DECISAO_CHOICES)
            situacoes.pop(int(ProjetoPedagogicoCurso.DECISAO_REJEITAR) - 1)
            self.fields['decisao_camara'].choices = situacoes

        info = 'Após finalização do documento a ser emitido o sistema irá se comportar da seguinte forma:<br><ul>'
        for sit in self.fields['decisao_camara'].choices:
            if sit[0] != '':
                info = f'{info}<li><b>{sit[1]}</b>: {ProjetoPedagogicoCurso.DECISAO_INFO_CHOICES[int(sit[0]) - 1][1]}</li>'
        self.INFO = mark_safe(f'{info}</ul>')


class EmitirDeliberacaoCONSEPEXForm(EmitirDocumentoForm):
    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('decisao_consepex',)

    def __init__(self, *args, **kwargs):
        documento = kwargs.pop('documento', None)
        super().__init__(*args, **kwargs)

        if documento in ['Deliberação de homologação', 'Deliberação Ad Referendum']:
            self.fields['decisao_consepex'].choices = [
                [ProjetoPedagogicoCurso.DECISAO_APROVAR, 'Aprovar'],
            ]

        elif self.instance.matrizppc_set.filter(matriz_id__isnull=False).exists():
            situacoes = copy.copy(ProjetoPedagogicoCurso.DECISAO_CHOICES)
            situacoes.pop(int(ProjetoPedagogicoCurso.DECISAO_REJEITAR) - 1)
            self.fields['decisao_consepex'].choices = situacoes

        info = 'Após finalização do documento a ser emitido o sistema irá se comportar da seguinte forma:<br><ul>'
        for sit in self.fields['decisao_consepex'].choices:
            if sit[0] != '':
                info = f'{info}<li><b>{sit[1]}</b>: {ProjetoPedagogicoCurso.DECISAO_INFO_CHOICES[int(sit[0]) - 1][1]}</li>'
        self.INFO = mark_safe(f'{info}</ul>')


class EmitirResolucaoCONSUPForm(EmitirDocumentoForm):
    setor = forms.ModelChoiceField(
        Setor.objects.suap_ativos(), label='Setor de emissão', widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS), required=True
    )

    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('decisao_consup',)

    def __init__(self, *args, **kwargs):
        documento = kwargs.pop('documento', None)
        super().__init__(*args, **kwargs)

        if documento in ['Resolução de homologação', 'Resolução Ad Referendum']:
            self.fields['decisao_consup'].choices = [
                [ProjetoPedagogicoCurso.DECISAO_APROVAR, 'Aprovar'],
            ]

        elif self.instance.matrizppc_set.filter(matriz_id__isnull=False).exists():
            situacoes = copy.copy(ProjetoPedagogicoCurso.DECISAO_CHOICES)
            situacoes.pop(int(ProjetoPedagogicoCurso.DECISAO_REJEITAR) - 1)
            self.fields['decisao_consup'].choices = situacoes

        info = 'Após finalização do documento a ser emitido o sistema irá se comportar da seguinte forma:<br><ul>'
        for sit in self.fields['decisao_consup'].choices:
            if sit[0] != '':
                info = f'{info}<li><b>{sit[1]}</b>: {ProjetoPedagogicoCurso.DECISAO_INFO_CHOICES[int(sit[0]) - 1][1]}</li>'
        self.INFO = mark_safe(f'{info}</ul>')


class AdicionarConfiguracaoOptativasMatrizPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoOptativasMatrizPPC
        fields = ('periodo', 'ch_exigida', 'nucleo_diretriz')

    def __init__(self, *args, **kwargs):
        matriz_ppc = kwargs.pop('matriz_ppc')
        super().__init__(*args, **kwargs)
        self.fields['nucleo_diretriz'].queryset = NucleoDiretriz.objects.filter(diretriz_id=matriz_ppc.ppc.diretriz_id)
        self.instance.matriz_ppc_id = matriz_ppc.id


class ConfiguracaoOptativasMatrizPPCForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoOptativasMatrizPPC
        fields = ('ch_exigida', 'nucleo_diretriz')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nucleo_diretriz'].queryset = NucleoDiretriz.objects.filter(diretriz_id=self.instance.matriz_ppc.ppc.diretriz_id)


class MatrizPPCForm(forms.ModelFormPlus):
    class Meta:
        model = MatrizPPC
        fields = ('nome', 'quantidade_periodos', 'turno')

    def __init__(self, *args, **kwargs):
        ppc = kwargs.pop('ppc', None)
        super().__init__(*args, **kwargs)
        if ppc:
            self.instance.ppc = ppc
        diretriz = self.instance.ppc.diretriz
        if diretriz.qtd_max_periodos == diretriz.qtd_min_periodos:
            del self.fields['quantidade_periodos']
            self.instance.quantidade_periodos = diretriz.qtd_max_periodos

    def processar(self):
        if not self.instance.ppc.diretriz.possui_modalidadepraticaprofissional():
            self.instance.situacao_modalidadepraticaprofissional = MatrizPPC.MODALIDADEPRATICAPROFISSIONAL_APROVADA
        self.save()


class ReplicarMatrizPPCForm(forms.ModelFormPlus):
    class Meta:
        model = MatrizPPC
        fields = (
            'nome',
            'quantidade_periodos',
            'turno',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['nome'] = f'{self.instance.nome} [REPLICADO]'
        self.initial['quantidade_periodos'] = ''
        self.initial['turno'] = None

    def clean(self):
        quantidade_periodos = self.cleaned_data.get('quantidade_periodos')
        turno = self.cleaned_data.get('turno')
        if MatrizPPC.objects.filter(ppc_id=self.instance.ppc_id, quantidade_periodos=quantidade_periodos, turno=turno).exists():
            raise forms.ValidationError('Já existe uma matriz cadastrada para este PPC com a mesma quantidade de períodos e turno.')
        return self.cleaned_data

    def processar(self):
        return self.instance.replicar()


class InformarReitoriaForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('reitor', 'proen', 'proex', 'propi')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['reitor'].queryset = Setor.objects.suap_ativos().get(sigla=get_sigla_reitoria()).chefes
        self.fields['proen'].queryset = get_setor_proen().chefes
        self.fields['proex'].queryset = get_setor_proex().chefes
        self.fields['propi'].queryset = get_setor_propi().chefes

        for nome in ['reitor', 'proen', 'proex', 'propi']:
            if self.initial[nome] is None:
                self.initial[nome] = self.fields[nome].queryset.first().pk


class ConvocarCamaraForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoPedagogicoCurso
        fields = (
            'data_convocacao_camara',
            'camara_inexistente',
        )

    def clean(self):
        data_convocacao = self.cleaned_data.get('data_convocacao_camara')
        camara_inexistente = self.cleaned_data.get('camara_inexistente')
        if not data_convocacao and not camara_inexistente:
            raise forms.ValidationError('Informe a data de convocação ou marque que a Câmara não está instituída.')
        if data_convocacao and camara_inexistente:
            raise forms.ValidationError('Não é possível informar a data de convocação e marcar que a Câmara não está instituída ao mesmo tempo.')
        return super().clean()


class ConvocarCONSEPEXForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoPedagogicoCurso
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
            raise forms.ValidationError('Não é possível informar a data de convocação e marcar que o CONSEPEX não está instituído ao mesmo tempo.')
        return super().clean()


class ConvocarCONSUPForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoPedagogicoCurso
        fields = ('data_convocacao_consup',)


class DevolverMatrizCurricularForm(forms.ModelFormPlus):
    class Meta:
        model = MatrizPPC
        fields = ('justificativa_matriz',)

    def processar(self):
        self.instance.devolver_matrizcurricular()


class DevolverModalidadePraticaProfissionalForm(forms.ModelFormPlus):
    class Meta:
        model = MatrizPPC
        fields = ('justificativa_modalidadepraticaprofissional',)

    def processar(self):
        self.instance.devolver_modalidadepraticaprofissional()


class AtualizacaoComissaoElaboracaoForm(forms.ModelFormPlus):
    INFO = 'A adição e remoção de membros da comissão será habilitada após inclusão da nova portaria.'

    class Meta:
        model = AtualizacaoComissaoElaboracao
        fields = ('id_portaria',)

    def __init__(self, *args, **kwargs):
        self.ppc_id = kwargs.pop('ppc_id', None)
        super().__init__(*args, **kwargs)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            self.fields['id_portaria'] = forms.ModelChoiceFieldPlus(
                DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO),
                label='Portaria atualizada da comissão de elaboração do PPC',
                widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
                required=True,
            )

    def clean_id_portaria(self):
        portaria = self.cleaned_data.get('id_portaria')
        return portaria and portaria.id or None

    def processar(self, ppc_id):
        self.instance.ppc_id = ppc_id
        self.save()


class ComentarioRevisaoPlanoDisciplinaForm(forms.ModelFormPlus):
    class Meta:
        model = ComentarioRevisaoPlanoDisciplina
        fields = ['texto']

    def processar(self, revisao, vinculo):
        self.instance.revisao = revisao
        self.instance.vinculo = vinculo
        self.save()
        mensagem = (
            f'Existe um novo comentário na revisão de {revisao.vinculo.user.get_relacionamento()} adicionado por {vinculo.user.get_relacionamento()}'
        )
        self.instance.revisao.plano_disciplina.notificar(mensagem=mensagem, notificar_elaboradores=True, notificar_avaliadores=True)


class CertificacaoParcialForm(forms.ModelFormPlus):
    fieldsets = (
        (
            '',
            {
                'fields': (
                    'descricao',
                    'modalidade_certificacao',
                    'titulacao_masculino',
                    'titulacao_feminino',
                    'ch_componentes_optativos',
                )
            },
        ),
    )

    class Meta:
        model = CertificacaoParcial
        exclude = ('ppc',)

    def processar(self, ppc_id):
        self.instance.ppc_id = ppc_id
        self.save()


class PlanoDisciplinaCertificacaoParcialForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoDisciplinaCertificacaoParcial
        fields = ('plano_disciplina',)

    def __init__(self, *args, **kwargs):
        certificacao_parcial = kwargs.pop('certificacao_parcial', None)
        super().__init__(*args, **kwargs)
        ids = PlanoDisciplinaCertificacaoParcial.objects.filter(certificacao_parcial_id=certificacao_parcial.id).values_list(
            'plano_disciplina_id', flat=True
        )
        self.fields['plano_disciplina'].queryset = PlanoDisciplina.objects.filter(
            diretriz__tipo_oferta_id=certificacao_parcial.ppc.diretriz.tipo_oferta_id
        ).exclude(id__in=ids)
        self.instance.certificacao_parcial = certificacao_parcial


class DuplicarPlanoDisciplinaForm(forms.FormPlus):
    tipo_oferta = forms.ModelChoiceField(Modalidade.objects.none(), label='Tipo de Oferta')
    diretriz = forms.ModelChoiceField(
        Diretriz.objects, label='Diretriz', widget=AutocompleteWidget(search_fields=['nome'], form_filters=[('tipo_oferta', 'tipo_oferta')])
    )

    def __init__(self, *args, **kwargs):
        self.plano_disciplina = kwargs.pop('plano_disciplina')
        super().__init__(*args, **kwargs)
        self.fields['tipo_oferta'].queryset = Modalidade.objects.exclude(pk=self.plano_disciplina.tipo_oferta_id)

    def clean_tipo_oferta(self):
        tipo_oferta = self.cleaned_data['tipo_oferta']
        qs = PlanoDisciplina.objects.filter(
            nome_disciplina=self.plano_disciplina.nome_disciplina, tipo_oferta=tipo_oferta, nucleo=self.plano_disciplina.nucleo, ativo=True
        )
        if qs.exists():
            raise forms.ValidationError('Já existe esse plano para o tipo de oferta informado.')
        return tipo_oferta

    def processar(self):
        self.plano_disciplina.duplicar(self.cleaned_data['tipo_oferta'], self.cleaned_data['diretriz'])
