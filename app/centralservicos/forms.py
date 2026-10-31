import uuid
from datetime import date, datetime

from django.template.defaultfilters import truncatewords

from django.forms.models import inlineformset_factory
from django.utils.safestring import mark_safe

from centralservicos.models import (
    AVALIACAO_CHOICES,
    AtendimentoAtribuicao,
    BaseConhecimento,
    CategoriaServico,
    CentroAtendimento,
    Chamado,
    ChamadoAnexo,
    Comunicacao,
    GestorAreaServico,
    GrupoAtendimento,
    GrupoInteressado,
    GrupoServico,
    Monitoramento,
    RespostaPadrao,
    Servico,
    StatusChamado,
    Tag,
    Tarefa,
    TarefaChamado,
)

from tinymce.widgets import TinyMCE
from comum.models import AreaAtuacao, Publico, User
from comum.utils import get_uo
from djtools import forms
from djtools.db import models
from djtools.forms.widgets import AutocompleteWidget
from rh.models import Setor, UnidadeOrganizacional
from centralservicos.widgets import BaseConhecimentoSelectMultiple, ChamadoSelectMultiple
from patrimonio.models import Inventario


class ConfiguracaoForm(forms.FormPlus):
    servico = forms.ModelChoiceFieldPlus(Servico.objects, label='Serviço de Informar erro do SUAP', help_text='Informar erro do SUAP', required=False)

    centro_atendimento = forms.ModelChoiceFieldPlus(
        CentroAtendimento.objects, label='Centro de Atendimento de erros do SUAP', help_text='Sistêmico (Sistemas)', required=False
    )


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['nome', 'area']


class GestorAreaServicoForm(forms.ModelForm):
    gestor = forms.ModelChoiceFieldPlus(
        queryset=User.objects.filter(is_active=True, vinculo__ativo=True),
        widget=AutocompleteWidget(search_fields=User.SEARCH_FIELDS),
        label='Gestor',
        help_text='Informe o nome do gestor desta área de serviço.',
    )

    class Meta:
        model = GestorAreaServico
        fields = ['gestor', 'area']


class CentroAtendimentoForm(forms.ModelForm):
    class Meta:
        model = CentroAtendimento
        exclude = ()


class CategoriaServicoForm(forms.ModelForm):
    class Meta:
        model = CategoriaServico
        exclude = ()


class GrupoServicoForm(forms.ModelForm):
    detalhamento = forms.CharField(label='Detalhamento', widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}))

    class Meta:
        model = GrupoServico
        exclude = ()


class ServicoForm(forms.ModelForm):
    publico_direcionado = forms.ModelMultipleChoiceField(
        label='Público',
        queryset=Publico.objects.all(),
        widget=forms.CheckboxSelectMultiplePlus(),
        required=False,
        help_text='Caso deseje restringir este serviço a apenas alguns tipos de usuário, selecione um ou mais.',
    )

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)

    class Meta:
        model = Servico
        exclude = ()

    class Media:
        js = ('/static/centralservicos/js/ServicoForm.js',)


class GrupoAtendimentoForm(forms.ModelForm):
    class Meta:
        model = GrupoAtendimento
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuarios_ativos = User.objects.filter(is_active=True, vinculo__pessoa__isnull=False, eh_aluno=False, vinculo__ativo=True)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap()
        self.fields['responsaveis'].queryset = usuarios_ativos
        self.fields['atendentes'].queryset = usuarios_ativos

    def clean_grupo_atendimento_superior(self):
        """
        Verifica se informou o Grupo de Atendimento Superior
        Em caso positivo, verifica se o id do Grupo de Atendimento atual
        é igual ao id do Grupo de Atendimento Superior
        """
        if self.cleaned_data['grupo_atendimento_superior'] and self.instance.id == self.cleaned_data['grupo_atendimento_superior'].id:
            raise forms.ValidationError('O Grupo de Atendimento Superior não pode ser o próprio Grupo de Atendimento.')

        return self.cleaned_data['grupo_atendimento_superior']

    def clean(self):
        super().clean()

        if not self.cleaned_data.get('grupo_atendimento_superior'):
            centro_atendimento = self.cleaned_data.get('centro_atendimento')
            if not centro_atendimento:
                raise forms.ValidationError('Escolha um centro de atendimento.')
            qs = GrupoAtendimento.objects.filter(grupo_atendimento_superior__isnull=True, centro_atendimento__area=centro_atendimento.area).exclude(
                id=self.instance.id
            )
            if qs.exists():
                raise forms.ValidationError('Não é possível mais um grupo Raiz.')


class BaseConhecimentoForm(forms.ModelFormPlus):
    solucao = forms.CharField(label='Solução', widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}))

    class Meta:
        model = BaseConhecimento
        fields = ['area', 'titulo', 'resumo', 'solucao', 'ativo', 'tags', 'visibilidade', 'grupos_atendimento', 'servicos']

    class Media:
        js = ('/static/tinymce/tiny_mce_toolbar.js', '/static/centralservicos/js/BaseConhecimentoForm.js')

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)

    def clean_grupos_atendimento(self):
        if (self.cleaned_data.get('visibilidade') != BaseConhecimento.VISIBILIDADE_SIGILOSA) and (self.cleaned_data.get('grupos_atendimento')):
            return ''
        else:
            return self.cleaned_data.get('grupos_atendimento')

    def clean(self):
        if (
            not self.request.user.has_perm('centralservicos.add_public_baseconhecimento')
            and self.instance.visibilidade == BaseConhecimento.VISIBILIDADE_PUBLICA
        ):
            raise forms.ValidationError('Você não tem permissão para adicionar uma base de conhecimento com visibilidade pública.')
        return self.cleaned_data

    def save(self, *args, **kwargs):
        if self.instance.pk:
            atual = BaseConhecimento.objects.get(pk=self.instance.pk)
            if (self.instance.resumo != atual.resumo) or (self.instance.solucao != atual.solucao):
                self.instance.atualizado_em = datetime.now()
                self.instance.atualizado_por = self.request.user
        else:
            self.instance.atualizado_por = self.request.user
        return super().save(*args, **kwargs)


def ChamadoAtoresFormFieldsFactory(fields_queryset_exclude_vinculo_pks: dict | None = None, fields_required: dict | None = None):
    """
    Os atores de um chamado são instâncias de User. Mas os choices fields correspondentes, no formulário,
    trabalham com instâncias de Vinculo.

    Será usado o template definido em 'Vinculo.get_ext_combo_template'
    para renderizar o item do 'combo' no resultado da busca, mostrando as
    informações conforme o relacionamento em questão.
    """

    from comum.models import Vinculo

    if fields_required is None:
        fields_required = {}
    if fields_queryset_exclude_vinculo_pks is None:
        fields_queryset_exclude_vinculo_pks = {}
    vinculos_qs_base = Vinculo.objects.filter(user__isnull=False).select_related('user')
    autocomplete_search_fields = ['pessoa__search_fields_optimized', 'pessoa__nome_usual', 'pessoa__nome_social', 'pessoa__nome_registro']

    return {
        'aberto_por': forms.ModelChoiceFieldPlus(
            label='Aberto por',
            queryset=vinculos_qs_base.exclude(pk__in=fields_queryset_exclude_vinculo_pks.get('aberto_por', [])),
            required=fields_required.get('aberto_por', False),
            widget=AutocompleteWidget(search_fields=autocomplete_search_fields),
        ),
        'requisitante': forms.ModelChoiceFieldPlus(
            label='Requisitante',
            queryset=vinculos_qs_base.exclude(pk__in=fields_queryset_exclude_vinculo_pks.get('requisitante', [])),
            required=fields_required.get('requisitante', False),
            widget=AutocompleteWidget(search_fields=autocomplete_search_fields),
        ),
        'interessado': forms.ModelChoiceFieldPlus(
            label='Interessado',
            queryset=vinculos_qs_base.exclude(pk__in=fields_queryset_exclude_vinculo_pks.get('interessado', [])),
            required=fields_required.get('interessado', False),
            widget=AutocompleteWidget(search_fields=autocomplete_search_fields),
        ),
        'outros_interessados': forms.MultipleModelChoiceFieldPlus(
            label='Outros Interessados',
            help_text='Vincule outros usuários a este chamado. Eles poderão acompanhar as alterações e comentários deste chamado.',
            queryset=vinculos_qs_base.exclude(pk__in=fields_queryset_exclude_vinculo_pks.get('outros_interessados', [])),
            required=fields_required.get('outros_interessados', False),
            widget=AutocompleteWidget(search_fields=autocomplete_search_fields, multiple=True),
        ),
        'atendente': forms.ModelChoiceFieldPlus(
            label='Atendente',
            queryset=vinculos_qs_base.exclude(pk__in=fields_queryset_exclude_vinculo_pks.get('atendente', []))
            .prefetch_related(
                'user__atendentes_set',
                'user__responsaveis_set',
            )
            .filter(models.Q(user__atendentes_set__isnull=False) | models.Q(user__responsaveis_set__isnull=False))
            .distinct(),
            required=fields_required.get('atendente', False),
            widget=AutocompleteWidget(search_fields=autocomplete_search_fields),
        ),
    }


def _ajustar_campos_do_formulario_de_chamado(form, request, servico):
    """Remove/ajusta campos do ChamadoForm conforme permissão do usuário e configuração do serviço."""
    if not request.user.has_perm('centralservicos.change_chamado'):
        del form.fields['meio_abertura']
        del form.fields['requisitante']
    if not request.user.has_perm('centralservicos.change_chamado') and servico.permite_abertura_terceiros is False:
        del form.fields['interessado']

    if request.user.has_perm('centralservicos.change_chamado') and servico.permite_abertura_terceiros is False:
        del form.fields['requisitante']

    if servico.requer_numero_patrimonio is False:
        del form.fields['patrimonio']
    if servico.permite_telefone_adicional is False:
        del form.fields['telefone_adicional']

    centros_atendimento_ativos = servico.centros_atendimento.filter(ativo=True)
    if centros_atendimento_ativos.count() == 1:
        form.fields['centro_atendimento'].initial = centros_atendimento_ativos.first()

    if servico.solicitar_local_atendimento is False:
        del form.fields['local_atendimento']


def _validar_centro_atendimento_informado(form):
    if not form.cleaned_data.get('centro_atendimento'):
        raise forms.ValidationError('É necessário informar um centro de atendimento.')
    return form.cleaned_data.get('centro_atendimento')


def _vinculo_como_user(vinculo):
    return vinculo.user if vinculo else None


def _outros_interessados_como_users(outros_interessados):
    return [outro_interessado.user for outro_interessado in outros_interessados]


def _configurar_form_class_de_chamado(form_class, request, servico):
    form_class.base_fields['meio_abertura'].initial = Chamado.MEIO_ABERTURA_WEB
    if not request.user.has_perm('centralservicos.change_chamado'):
        form_class.base_fields['interessado'].initial = request.user.vinculo
    if servico.requer_numero_patrimonio:
        form_class.base_fields['patrimonio'].required = True


def _limpar_requisitante_do_chamado(form):
    """Se possui interessado e não possui requisitante, o interessado é o próprio requisitante."""
    if not form.errors:
        if form.cleaned_data['interessado'] and not form.cleaned_data['requisitante']:
            return form.cleaned_data.get('interessado')
        return _vinculo_como_user(form.cleaned_data.get('requisitante'))
    raise forms.ValidationError('Verifique o preenchimento de campos obrigatórios.')


def _validar_grupo_atendimento_do_chamado(form, servico):
    """Garante que exista Grupo de Atendimento de primeiro nível para o campus/centro escolhidos."""
    if not form.errors and form.cleaned_data.get('uo'):
        uo = form.cleaned_data['uo']
        centroatendimento = form.cleaned_data.get('centro_atendimento')
        grupo = GrupoAtendimento.get_grupo_primeiro_nivel(uo, centroatendimento) if centroatendimento else None

        if not grupo:
            campus = UnidadeOrganizacional.objects.get(pk=uo)
            mensagem = mark_safe(
                f'Nenhum grupo de atendimento de primeiro nível foi cadastrado para o campus {campus.nome} '
                f'no centro de atendimento {centroatendimento}. Para resolver este problema, <a href="/admin/centralservicos/gestorareaservico/?area={servico.area.id}">'
                'entre em contato com o gestor da área do serviço solicitado</a>.'
            )
            raise forms.ValidationError(mensagem)
    return form.cleaned_data


def ChamadoFormFactory(request, chamado=None, servico=None):
    if chamado:
        servico = chamado.servico

    atores_fields = ChamadoAtoresFormFieldsFactory(fields_required={'interessado': True})

    class ChamadoForm(forms.ModelForm):
        local_atendimento = forms.CharField(label='Sala/local de atendimento', required=False)
        interessado = atores_fields['interessado']
        requisitante = atores_fields['requisitante']
        outros_interessados = atores_fields['outros_interessados']

        uo = forms.CharField(label='Campus', widget=forms.Select(), required=True)
        centro_atendimento = forms.ModelChoiceFieldPlus(
            queryset=servico.centros_atendimento.filter(ativo=True),
            label='Centro de Atendimento',
            required=True,
            widget=forms.RadioSelect(),
            help_text='Selecione o Centro de Atendimento que mais se adequa ao seu problema.',
        )

        enviar_copia_email = forms.BooleanField(
            widget=forms.CheckboxInput, required=False, label='Enviar cópia de abertura deste chamado para os interessados?'
        )

        patrimonio = forms.ModelChoiceFieldPlus(
            label='Patrimônio',
            queryset=Inventario.ativos,
            required=True,
            widget=AutocompleteWidget(search_fields=Inventario.SEARCH_FIELDS),
        )

        class Meta:
            model = Chamado
            fields = [
                'descricao',
                'local_atendimento',
                'patrimonio',
                'interessado',
                'requisitante',
                'telefone_adicional',
                'uo',
                'centro_atendimento',
                'meio_abertura',
                'outros_interessados',
                'enviar_copia_email',
            ]

        class Media:
            js = ('/static/centralservicos/js/get_centros_atendimento_por_campus.js',)

        def __init__(self, *args, **kwargs):
            """
            Se o usuário logado não for um Atendente, os campos Meio de Abertura e
            Requisitante não devem aparecer
            """
            super().__init__(*args, **kwargs)
            self.fields['uo'].widget.attrs['data-servico_id'] = servico.id
            self.fields['requisitante'].required = False
            _ajustar_campos_do_formulario_de_chamado(self, request, servico)

        def clean(self):
            return _validar_grupo_atendimento_do_chamado(self, servico)

        def clean_centro_atendimento(self):
            return _validar_centro_atendimento_informado(self)

        # o clean nos fields atores (mapeando Vinculo para User) se faz necessário por se tratar de um ModelForm,
        # já que os atributos atores em form.instance são User, o que geraria um erro (atributo ator deve ser User e não Vinculo)

        def clean_interessado(self):
            return _vinculo_como_user(self.cleaned_data.get('interessado'))

        def clean_requisitante(self):
            return _limpar_requisitante_do_chamado(self)

        def clean_outros_interessados(self):
            return _outros_interessados_como_users(self.cleaned_data.get('outros_interessados', []))

    _configurar_form_class_de_chamado(ChamadoForm, request, servico)
    return ChamadoForm


ChamadoAnexoFormset = inlineformset_factory(Chamado, ChamadoAnexo, extra=3, exclude=['chamado', 'anexado_em', 'anexado_por'], can_delete=False)


class ChamadoAnexoForm(forms.ModelForm):
    class Meta:
        model = ChamadoAnexo
        fields = ['descricao', 'anexo']


def ComunicacaoFormFactory(request, chamado, operacao=None):
    atribuicao = chamado.get_atendimento_atribuicao_atual()
    grupo_atendimento_destino = None
    if operacao == 'escalar':
        grupo_atendimento_destino = atribuicao.grupo_atendimento.grupo_atendimento_superior
    elif operacao == 'retornar':
        grupo_atendimento_destino = atribuicao.grupo_atendimento.get_grupo_antendimento_inferior(chamado)

    class ComunicacaoForm(forms.ModelFormPlus):
        atribuido_para = forms.ModelChoiceField(required=False, queryset=User.objects.none())
        texto = forms.CharField(label='Texto', widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}))
        usuarios_citados = forms.MultipleModelChoiceFieldPlus(
            label='Citar Outros Atendentes',
            required=False,
            queryset=User.objects.none(),
            help_text='Caso deseje enviar uma notificação com o texto deste comunicado a outros atendentes, especifique-os aqui. Atendentes sem emails não serão listados.',
        )
        bases_conhecimento = forms.MultipleModelChoiceFieldPlus(
            label='Sugerir Artigos da Base de Conhecimentos',
            required=False,
            widget=forms.CheckboxSelectMultiplePlus(),
            queryset=chamado.servico.get_bases_conhecimento_faq(),
            help_text='Caso deseje sugerir algum Artigo da Base de Conhecimentos para o(s) interessado(s) deste chamado, especifique-as.',
        )

        if grupo_atendimento_destino:
            if operacao == 'escalar':
                EXTRA_INFO = f'Escalando para <strong>{grupo_atendimento_destino}</strong>.'
            elif operacao == 'retornar':
                EXTRA_INFO = f'Retornando para <strong>{grupo_atendimento_destino}</strong>.'

        class Meta:
            model = Comunicacao
            fields = ['texto', 'usuarios_citados', 'bases_conhecimento']

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            atendentes = list(chamado.get_atendentes_equipe_atendimento().values_list('id', flat=True))
            responsaveis = list(chamado.get_responsaveis_equipe_atendimento().values_list('id', flat=True))
            ids = atendentes + responsaveis
            if chamado.get_atendente_do_chamado():
                self.fields['usuarios_citados'].queryset = (
                    User.objects.filter(id__in=ids).exclude(id=chamado.get_atendente_do_chamado().id).exclude(email='')
                )
            else:
                self.fields['usuarios_citados'].queryset = User.objects.filter(id__in=ids).exclude(email='')

            atribuicao = chamado.get_atendimento_atribuicao_atual()
            if operacao is not None:
                del self.fields['bases_conhecimento']
            if operacao == 'escalar':
                if not (
                    request.user.is_superuser
                    or atribuicao.grupo_atendimento.grupo_atendimento_superior.responsaveis.filter(pk=request.user.pk).exists()
                ):
                    del self.fields['atribuido_para']
                else:
                    self.fields['atribuido_para'].queryset = atribuicao.grupo_atendimento.grupo_atendimento_superior.atendentes_disponiveis()
            elif operacao == 'retornar':
                if not (
                    request.user.is_superuser
                    or (atribuicao.grupo_atendimento.get_grupo_antendimento_inferior(chamado).responsaveis.filter(pk=request.user.pk).exists())
                ):
                    del self.fields['atribuido_para']
                else:
                    self.fields['atribuido_para'].queryset = atribuicao.grupo_atendimento.get_grupo_antendimento_inferior(
                        chamado
                    ).atendentes_disponiveis()

    return ComunicacaoForm


def AtendimentoAtribuicaoFormFactory(request, grupo_atendimento):
    class AtendimentoAtribuicaoForm(forms.ModelForm):
        atribuido_para = forms.ModelChoiceField(grupo_atendimento.atendentes_disponiveis(request.user))
        # atribuido_para = forms.ModelChoiceField(queryset=grupo_atendimento.atendentes.exclude(id__in=[request.user.id]))

        class Meta:
            model = AtendimentoAtribuicao
            fields = ['atribuido_para']

    return AtendimentoAtribuicaoForm


def BuscarChamadoUsuarioFormFactory(request):
    fields = {
        'chamado_id': forms.IntegerFieldPlus(required=False, label='ID'),
        'area': forms.ModelChoiceFieldPlus2(AreaAtuacao.objects, label='Área de Serviços', required=False),
        'data_inicial': forms.DateFieldPlus(required=False, label='Data Inicial'),
        'data_final': forms.DateFieldPlus(required=False, label='Data Final'),
        'tipo_usuario': forms.ChoiceField(label='Minha Relação com o Chamado:', choices=Chamado.TIPO_USUARIO_CHOICES, required=False),
    }

    fieldsets = ((None, {'fields': ('chamado_id', 'area', ('data_inicial', 'data_final'), 'tipo_usuario')}),)

    def clean(self):
        msg = {'erro': 'O campo data inicial não pode ser maior que data final.'}
        if not self.errors:
            if self.cleaned_data['data_inicial'] and self.cleaned_data['data_final']:
                if self.cleaned_data['data_inicial'] > self.cleaned_data['data_final']:
                    self.errors['data_inicial'] = [msg['erro']]
        return self.cleaned_data

    return type('BuscarChamadoUsuarioForm', (forms.BaseForm,), {'base_fields': fields, 'clean': clean, 'fieldsets': fieldsets, 'METHOD': 'GET'})


def BuscarChamadoSuporteFormFactory(request, area=None):
    """
    Cria uma classe para o formulário de busca de chamados para Equipe do Suporte
    """
    ORDENAR_POR_SITUACAO = 'status'
    ORDENAR_POR_SERVICO = 'servico__nome'
    ORDENAR_POR_ABERTO_EM = 'aberto_em'
    ORDENAR_POR_ABERTO_POR = 'aberto_por__vinculo__pessoa__pessoafisica__nome'
    ORDENAR_POR_INTERESSADO = 'interessado__vinculo__pessoa__pessoafisica__nome'
    ORDENAR_POR_DATA_LIMITE_ATENDIMENTO = 'data_limite_atendimento'
    ORDENAR_POR_DATA_ULTIMA_INTERACAO = 'data_ultima_interacao'

    ORDENACAO_CRESCENTE = ''
    ORDENACAO_DECRESCENTE = '-'

    ORDERNAR_POR_CHOICES = [
        [ORDENAR_POR_DATA_LIMITE_ATENDIMENTO, 'Data Limite do Atendimento'],
        [ORDENAR_POR_DATA_ULTIMA_INTERACAO, 'Data da última interação'],
        [ORDENAR_POR_ABERTO_EM, 'Data Abertura'],
        [ORDENAR_POR_SITUACAO, 'Situação'],
        [ORDENAR_POR_SERVICO, 'Serviço'],
        [ORDENAR_POR_ABERTO_POR, 'Aberto Por'],
        [ORDENAR_POR_INTERESSADO, 'Interessado'],
    ]
    TIPO_ORDENACAO_CHOICES = [[ORDENACAO_CRESCENTE, 'Crescente'], [ORDENACAO_DECRESCENTE, 'Decrescente']]

    atores_fields = ChamadoAtoresFormFieldsFactory()

    fields = {
        'chamado_id': forms.IntegerFieldPlus(required=False, label='ID'),
        'data_inicial': forms.DateFieldPlus(required=False, label='Data Inicial'),
        'data_final': forms.DateFieldPlus(required=False, label='Data Final'),
        'tipo': forms.ChoiceField(choices=[('', '---------'), *Servico.TIPO_CHOICES], required=False, label='Tipo'),
        'status': forms.MultipleChoiceField(choices=StatusChamado.STATUS, widget=forms.CheckboxSelectMultiplePlus, required=False, label='Situação'),
        'todos_status': forms.BooleanField(required=False, label='Todas as Situações'),
        'nota_avaliacao': forms.ChoiceField(choices=[('', '---------'), *AVALIACAO_CHOICES], required=False, label='Nota da Avaliação'),
        'uo': forms.MultipleModelChoiceFieldPlus(
            UnidadeOrganizacional.objects.suap().filter(pk__in=GrupoAtendimento.meus_grupos(request.user).values_list('campus', flat=True)),
            required=False,
            label='Unidade Organizacional',
        ),
        'area': forms.MultipleModelChoiceFieldPlus(
            GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user),
            required=False,
            label='Área',
        ),
        'grupo_atendimento': forms.MultipleModelChoiceFieldPlus(
            GrupoAtendimento.meus_grupos(request.user, area), required=False, label='Grupo de Atendimento'
        ),
        'atribuicoes': forms.ChoiceField(
            label='Atribuições', widget=forms.RadioSelect(), choices=[('', 'Todas'), *Chamado.ATRIBUICOES_CHOICES], required=False
        ),
        'texto': forms.CharField(
            label='Buscar por',
            required=False,
            help_text='Conteúdo a ser pesquisado nas descrições, número de patrimônio, comentários e notas internas dos chamados',
        ),
        'considerar_escalados': forms.BooleanField(required=False, label='Considerar chamados escalados/retornados'),
        'servico': forms.ModelChoiceFieldPlus(
            Servico.objects.filter(ativo=True), required=False, label='Serviço', widget=AutocompleteWidget(search_fields=Servico.SEARCH_FIELDS)
        ),
        'grupo_servico': forms.ModelChoiceFieldPlus(GrupoServico.objects.all(), required=False, label='Grupo de Serviço'),
        'interessado': atores_fields['interessado'],
        'aberto_por': atores_fields['aberto_por'],
        'atendente': atores_fields['atendente'],
        'ordenar_por': forms.ChoiceField(choices=ORDERNAR_POR_CHOICES, initial=ORDENAR_POR_DATA_LIMITE_ATENDIMENTO, required=False),
        'tipo_ordenacao': forms.ChoiceField(widget=forms.RadioSelect, choices=TIPO_ORDENACAO_CHOICES, initial=ORDENACAO_CRESCENTE, required=False),
        'sla_estourado': forms.BooleanField(required=False, label='Somente com SLA estourado'),
        'numero_patrimonio': forms.IntegerFieldPlus(
            label='Número do Patrimônio',
            required=False,
        ),
    }

    fieldsets = (
        (
            None,
            {
                'fields': (
                    ('chamado_id', 'texto'),
                    ('data_inicial', 'data_final', 'numero_patrimonio'),
                    'uo',
                    ('area', 'grupo_atendimento'),
                    ('grupo_servico', 'servico'),
                    ('status', 'todos_status', 'considerar_escalados'),
                    'atribuicoes',
                    'atendente',
                    ('interessado', 'aberto_por'),
                    ('tipo', 'nota_avaliacao'),
                    ('ordenar_por', 'tipo_ordenacao'),
                    ('sla_estourado'),
                )
            },
        ),
    )

    def interessado_as_user(self) -> User:
        interessado = self.cleaned_data.get('interessado')
        return interessado.user if interessado else None

    def aberto_por_as_user(self) -> User:
        aberto_por = self.cleaned_data.get('aberto_por')
        return aberto_por.user if aberto_por else None

    def atendente_as_user(self) -> User:
        atentende = self.cleaned_data.get('atendente')
        return atentende.user if atentende else None

    def clean(self):
        msg = {'erro': 'O campo Data Inicial não pode ser maior que Data Final.'}
        if not self.errors:
            if self.cleaned_data['data_inicial'] and self.cleaned_data['data_final']:
                if self.cleaned_data['data_inicial'] > self.cleaned_data['data_final']:
                    self.errors['data_inicial'] = [msg['erro']]
        return self.cleaned_data

    return type(
        'BuscarChamadoSuporteForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'clean': clean,
            'fieldsets': fieldsets,
            'METHOD': 'GET',
            'interessado_as_user': interessado_as_user,
            'aberto_por_as_user': aberto_por_as_user,
            'atendente_as_user': atendente_as_user,
        },
    )


def BuscarServicoFormFactory(servicos):
    fields = {
        'servico': forms.ModelChoiceFieldPlus(
            queryset=servicos,
            widget=AutocompleteWidget(search_fields=Servico.SEARCH_FIELDS, submit_on_select=True),
            label='Busque um serviço:',
            required=False,
        )
    }

    fieldsets = ((None, {'fields': ('servico',)}),)

    return type('BuscarServicoFormForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'POST'})


class BuscarArtigoForm(forms.FormPlus):
    METHOD = 'POST'

    baseconhecimento = forms.ModelChoiceFieldPlus(
        queryset=BaseConhecimento.objects,
        label='Busque um artigo:',
        required=False,
        widget=AutocompleteWidget(search_fields=BaseConhecimento.SEARCH_FIELDS, submit_on_select=True),
    )

    def __init__(self, *args, **kwargs):
        self.eh_atendente_desta_area = kwargs.pop('eh_atendente_desta_area', None)
        area = kwargs.pop('area') if kwargs.get('area') else None
        super().__init__(*args, **kwargs)
        if self.eh_atendente_desta_area and area:
            self.fields['baseconhecimento'].queryset = BaseConhecimento.objects.filter(area=area, ativo=True)
        else:
            self.fields['baseconhecimento'].queryset = BaseConhecimento.objects.filter(visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA, ativo=True)


def ReclassificarChamadoFormFactory(request, chamado=None, troca_area=None, centros_validos=None):
    class ReclassificarChamadoForm(forms.ModelFormPlus):
        consulta = Servico.objects.filter(ativo=True, area=chamado.servico.area).order_by('grupo_servico', 'nome')
        if troca_area is True:
            consulta = Servico.objects.filter(ativo=True).order_by('grupo_servico', 'nome')

        if chamado and chamado.servico.interno is False:
            servico = forms.ModelPopupChoiceField(queryset=consulta.filter(interno=False), label='Novo Serviço', initial=chamado.servico.id)
        else:
            servico = forms.ModelPopupChoiceField(queryset=consulta, label='Novo Serviço', initial=chamado.servico.id)
        uo = forms.CharField(label='Campus', widget=forms.Select(), required=True, initial=chamado.campus.id)
        centro_atendimento = forms.ModelChoiceField(
            queryset=centros_validos,
            label='Centro de Atendimento',
            required=True,
            widget=forms.RadioSelect(),
            help_text='Selecione o Centro de Atendimento que mais se adequa ao seu problema.',
            initial=chamado.get_atendimento_atribuicao_atual().grupo_atendimento.centro_atendimento.id,
        )
        justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}))

        class Meta:
            model = Chamado
            fields = ['servico', 'uo', 'centro_atendimento', 'justificativa']

        class Media:
            js = ('/static/centralservicos/js/get_centros_atendimento_por_campus.js',)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['uo'].widget.attrs['data-servico_id'] = chamado.servico.id
            self.fields['uo'].widget.attrs['data-chamado_id'] = chamado.id

        def clean(self):
            if not self.errors:
                centro_atendimento_old = chamado.get_atendimento_atribuicao_atual().grupo_atendimento.centro_atendimento
                if (
                    chamado.servico == self.cleaned_data.get('servico')
                    and centro_atendimento_old == self.cleaned_data.get('centro_atendimento')
                    and (not centro_atendimento_old.eh_local or str(chamado.campus.id) == str(self.cleaned_data.get('uo')))
                ):
                    raise forms.ValidationError(
                        'Nenhuma mudança foi identificada na reclassificação do chamado. Por favor, verifique se o serviço selecionado, o campus, ou o centro de atendimento são diferentes do atual.'
                    )

                if self.cleaned_data.get('uo') and self.cleaned_data.get('centro_atendimento'):
                    campus = UnidadeOrganizacional.objects.suap().get(pk=self.cleaned_data.get('uo'))
                    centro_atendimento = self.cleaned_data.get('centro_atendimento')
                    grupo = GrupoAtendimento.get_grupo_primeiro_nivel(campus, centro_atendimento)
                    if not grupo:
                        raise forms.ValidationError(
                            f'Nenhum grupo de atendimento foi cadastrado para o campus ({campus}) '
                            f'do servidor Interessado, no centro de atendimento ({centro_atendimento}).'
                        )
            return self.cleaned_data

    return ReclassificarChamadoForm


class FecharEAvaliarChamadoForm(forms.FormPlus):
    class Media:
        js = ('/static/centralservicos/js/stars.js',)

    METHOD = 'POST'
    nota_avaliacao = forms.ChoiceField(
        label='Nota para Atendimento do Chamado',
        widget=forms.RadioSelect(),
        choices=AVALIACAO_CHOICES,
        required=False,
        help_text='Avalie o atendimento deste chamado.',
    )
    comentario = forms.CharField(
        label='Comentário',
        widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
        required=False,
        help_text='Se desejar, faça um comentário sobre sua avaliação.',
    )


def GraficosFormFactory(request, data_inicio, data_termino):
    user_uo = get_uo(request.user)
    uo_pk = user_uo and user_uo.pk or None
    fields = {
        'inicio': forms.DateFieldPlus(label='Data de Início', required=True, initial=data_inicio),
        'termino': forms.DateFieldPlus(label='Data de Término', required=True, initial=data_termino),
        'uo': forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().all(), required=False, label='Unidade Organizacional', initial=uo_pk),
        'grupo_atendimento': forms.ModelChoiceField(GrupoAtendimento.meus_grupos(request.user), required=False, label='Grupo de Atendimento'),
    }

    if GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user).count() > 1:
        fields['area'] = forms.ModelChoiceField(
            GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user), required=False, label='Área do Serviço'
        )

    fieldsets = ((None, {'fields': ('area', 'inicio', 'termino', 'uo', 'grupo_atendimento')}),)

    return type('GraficosForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'GET'})


class AtendimentosPorAnoForm(forms.FormPlus):
    inicio = forms.IntegerFieldPlus(label='Ano de Início', required=True)
    termino = forms.IntegerFieldPlus(label='Ano de Término', required=True)
    area = forms.ModelChoiceField(GrupoAtendimento.objects, required=False, label='Área do Serviço')

    fieldsets = ((None, {'fields': ('area', 'inicio', 'termino', 'uo', 'grupo_atendimento')}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = date.today()
        choices_anos = ((ano, ano) for ano in Chamado.objects.filter().values_list('aberto_em__year').distinct())
        self.fields['inicio'].choices = choices_anos
        self.fields['termino'].choices = choices_anos
        self.fields['inicio'].initial = hoje.year
        self.fields['termino'].initial = hoje.year
        self.fields['area'].queryset = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(self.request.user)


def AtendentesFormFactory(request):
    fields = {
        'uo': forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().all(), required=False, label='Unidade Organizacional'),
        'grupo_atendimento': forms.ModelChoiceField(GrupoAtendimento.meus_grupos(request.user), required=False, label='Grupo de Atendimento'),
        'setor': forms.ModelChoiceFieldPlus(Setor.objects.suap_ativos().filter(excluido=False), required=False, label='Setor'),
    }

    if GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user).count() > 1:
        fields['area'] = forms.ModelChoiceField(
            GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user), required=False, label='Área do Serviço'
        )

    fieldsets = ((None, {'fields': ('area', 'grupo_atendimento', 'setor', 'uo')}),)

    return type('AtendentesForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'GET'})


def AlterarStatusChamadoFormFactory(request, servico, grupo_atendimento):
    class AlterarStatusChamadoForm(forms.ModelForm):
        """
        O objetivo é listar as bases de conhecimento disponíveis ao serviço,
        apenas no grupo de atendimento do usuário
        """

        bases_conhecimento = forms.ModelMultipleChoiceField(
            label='Bases de Conhecimento',
            queryset=servico.get_bases_de_conhecimento_disponiveis_para_resolucao(grupo_atendimento),
            widget=forms.CheckboxSelectMultiplePlus(),
            help_text='Selecione uma ou mais bases de conhecimento',
        )

        observacao = forms.CharField(
            label='Comentário',
            help_text='Este comentário será adicionado à Linha do Tempo deste Chamado',
            widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not grupo_atendimento:
                del self.fields['bases_conhecimento']

        class Meta:
            model = Chamado
            fields = [
                'bases_conhecimento',
            ]

        class Media:
            js = ('/static/centralservicos/js/AlterarStatusChamadoFormFactory.js',)

    return AlterarStatusChamadoForm


def ResolverChamadoFormFactory(request, chamado):
    servico = chamado.servico
    grupo_atendimento = chamado.get_atendimento_atribuicao_atual().grupo_atendimento

    outros_chamados_em_andamento_mesmo_servico_e_atribuicao = Chamado.chamados_em_andamento_por_servico_e_atribuicao_atual(
        servico=servico, atribuido_a=request.user
    ).exclude(pk=chamado.pk)

    class ResolverChamadoForm(forms.Form):
        bases_conhecimento = forms.ModelMultipleChoiceField(
            label='Artigos relacionados',
            queryset=servico.get_bases_de_conhecimento_disponiveis_para_resolucao(grupo_atendimento),
            widget=BaseConhecimentoSelectMultiple(request),
            required=True,
            help_text='Selecione uma ou mais bases de conhecimento',
        )

        if outros_chamados_em_andamento_mesmo_servico_e_atribuicao.exists():
            outros_chamados_a_resolver = forms.ModelMultipleChoiceField(
                label='Resolver também os seguintes chamados',
                queryset=outros_chamados_em_andamento_mesmo_servico_e_atribuicao,
                widget=ChamadoSelectMultiple(),
                required=False,
                help_text='Os chamados selecionados também serão resolvidos em conjunto com o chamado principal',
            )

        resposta_padrao = forms.ChoiceField(
            label='Resposta Padrão',
            choices=[
                [None, '-'],
                *[[resposta.texto, truncatewords(resposta.texto, 10)] for resposta in RespostaPadrao.objects.filter(atendente=request.user)],
            ],
            required=False,
            help_text='A resposta padrão selecionada será adicionada ao campo de comentário',
        )

        comentario = forms.CharField(
            label='Comentário',
            widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
            required=True,
            help_text='Este comentário será adicionado à Linha do Tempo deste Chamado',
        )

        SUBMIT_LABEL = 'Alterar para Resolvido'

        class Media:
            js = ('/static/centralservicos/js/ResolverChamadoForm.js',)

        def __init__(self, *args, **kargs):
            super().__init__(*args, **kargs)
            self.chamado = chamado
            self.request = request

        def clean(self):
            clean = super().clean()
            pode_resolver_info = self.chamado.pode_resolver_info(self.request.user)
            if not pode_resolver_info['pode_resolver']:
                self.add_error(None, pode_resolver_info['msg_erro_permissao'])
            return clean

        def resolver_chamado(self) -> list[str]:
            chamados_resolvidos_ids = []

            # resolve o chamando principal
            if self.chamado.resolver_chamado(
                self.request.user, bases_conhecimento=self.cleaned_data.get('bases_conhecimento'), observacao=self.cleaned_data.get('comentario')
            ):
                chamados_resolvidos_ids.append(f'{self.chamado.id}')

            # resolve outros chamados em conjunto com o principal
            for outro_chamado_a_resolver in self.cleaned_data.get('outros_chamados_a_resolver') or []:
                try:
                    if outro_chamado_a_resolver.resolver_chamado(
                        self.request.user,
                        bases_conhecimento=self.cleaned_data.get('bases_conhecimento'),
                        observacao=self.cleaned_data.get('comentario'),
                    ):
                        chamados_resolvidos_ids.append(f'{outro_chamado_a_resolver.id}')
                except Exception:
                    # não deve haver prejuízo na resolução do chamado principal
                    pass

            return chamados_resolvidos_ids

    return ResolverChamadoForm


def AdicionarOutrosInteressadosFormFactory(request, chamado):
    omitir_vinculos_pks = []
    for user in chamado.outros_interessados.all():
        user_vinculo = user.get_vinculo()
        if user_vinculo:
            omitir_vinculos_pks.append(user_vinculo.pk)

    atores_fields = ChamadoAtoresFormFieldsFactory(
        fields_queryset_exclude_vinculo_pks={'outros_interessados': omitir_vinculos_pks}, fields_required={'outros_interessados': True}
    )

    class AdicionarOutrosInteressadosForm(forms.Form):
        outros_interessados = atores_fields['outros_interessados']

        METHOD = 'POST'

        def outros_interessados_as_users(self) -> list[User]:
            outros_interessados = self.cleaned_data.get('outros_interessados', [])
            return [outro_interessado.user for outro_interessado in outros_interessados]

    return AdicionarOutrosInteressadosForm


def AdicionarTagsAoChamadoFormFactory(request, chamado):
    class AdicionarTagsAoChamadoForm(forms.Form):
        METHOD = 'POST'
        tags = forms.ModelMultipleChoiceField(
            queryset=Tag.objects.exclude(id__in=chamado.tags.all()).filter(
                area__in=GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user)
            ),
            widget=forms.CheckboxSelectMultiplePlus(),
            label='Tags',
            help_text='Vincule tags a este chamado para facilitar a identificação do mesmo.',
            required=True,
        )

    return AdicionarTagsAoChamadoForm


class MarcarParaCorrecaoForm(forms.FormPlus):
    comentario = forms.CharField(
        label='Comentário',
        required=True,
        help_text='Informe o motivo da necessidade de correção da base de conhecimento.',
        widget=forms.Textarea(attrs={'rows': '50', 'cols': '100'}),
    )


class MonitoramentoForm(forms.ModelFormPlus):
    class Meta:
        model = Monitoramento
        fields = ['titulo', 'grupos', 'organizar_por_tipo']

    def save(self, *args, **kwargs):
        if not self.instance.pk:
            self.instance.token = uuid.uuid4().hex[:32].upper()
            self.instance.cadastrado_por = self.request.user
        return super().save(*args, **kwargs)


class RespostaPadraoForm(forms.ModelFormPlus):
    class Meta:
        model = RespostaPadrao
        fields = ['texto']


class GrupoInteressadoForm(forms.ModelForm):
    grupo_atendimento = forms.ModelChoiceFieldPlus(GrupoAtendimento.objects, widget=forms.Select(), label='Grupo de Atendimento')
    interessados = forms.MultipleModelChoiceFieldPlus(queryset=User.objects.filter(is_active=True, vinculo__ativo=True), label='Interessados')

    class Meta:
        model = GrupoInteressado
        fields = ['titulo', 'grupo_atendimento', 'interessados']

    def __init__(self, *args, **kargs):
        super().__init__(*args, **kargs)
        self.fields['grupo_atendimento'].queryset = GrupoAtendimento.meus_grupos(self.request.user).filter(ativo=True)


def AdicionarGrupoInteressadosFormFactory(request, chamado):
    class AdicionarGrupoInteressadosForm(forms.Form):
        METHOD = 'POST'
        grupos_interessados = forms.ModelMultipleChoiceField(
            queryset=GrupoInteressado.objects.filter(grupo_atendimento=chamado.get_atendimento_atribuicao_atual().grupo_atendimento),
            widget=forms.CheckboxSelectMultiplePlus(),
            label='Grupos de Interessado',
            required=True,
        )

    return AdicionarGrupoInteressadosForm


class EditarPatrimonioRelacionadoChamadoForm(forms.ModelFormPlus):
    patrimonio = forms.ModelChoiceFieldPlus(
        queryset=Inventario.ativos,
        label='Patrimônio',
        widget=AutocompleteWidget(search_fields=Inventario.SEARCH_FIELDS),
        required=False,
    )

    class Meta:
        model = Chamado
        fields = ['patrimonio']


def TarefaFormFactory(areas: list[AreaAtuacao]):
    class TarefaForm(forms.ModelFormPlus):
        servico = forms.ModelChoiceFieldPlus(
            queryset=Servico.get_servicos_por_areas(areas),
            label='Serviço',
            widget=AutocompleteWidget(search_fields=Servico.SEARCH_FIELDS),
            required=True,
        )

        class Meta:
            model = Tarefa
            fields = ['servico', 'titulo', 'descricao']

    return TarefaForm


def TarefaChamadoAddFormFactory(chamado: Chamado):
    atendimento_atual = chamado.get_atendimento_atual()

    class TarefaChamadoAddForm(forms.ModelFormPlus):
        tarefa = forms.ModelChoiceFieldPlus(
            queryset=Tarefa.get_tarefas_por_servicos([chamado.servico] if chamado.servico else []),
            label='Tarefa',
            help_text=f'Cadastro prévio de tarefas relacionadas ao serviço {chamado.servico or "do chamado"}.',
            widget=AutocompleteWidget(search_fields=Tarefa.SEARCH_FIELDS),
            required=True,
        )

        responsavel = forms.ModelChoiceFieldPlus(
            queryset=(atendimento_atual['responsaveis_grupo_atendimento'] | atendimento_atual['atendentes_grupo_atendimento']).distinct(),
            initial=atendimento_atual['atendente'],
            label='Responsável',
            help_text=f'Atendentes do grupo {atendimento_atual["grupo_atendimento"] or "de atendimento do chamado"}.',
            widget=AutocompleteWidget(search_fields=User.SEARCH_FIELDS),
            required=True,
        )

        class Meta:
            model = TarefaChamado
            fields = ['tarefa', 'responsavel', 'situacao']

        def save(self, *args, **kwargs):
            self.instance.chamado = chamado
            return super().save(*args, **kwargs)

    return TarefaChamadoAddForm


def TarefaChamadoChangeFormFactory(tarefa_chamado: TarefaChamado, somente_situacao: bool = False, somente_responsavel: bool = False) -> type:
    chamado = tarefa_chamado.chamado
    atendimento_atual = chamado.get_atendimento_atual()
    # O responsável atual continua válido mesmo fora do grupo atual (chamado reclassificado/escalado ou
    # atendente removido do grupo): sem isso, ele não consegue nem finalizar a própria tarefa (#17794).
    responsaveis = (
        atendimento_atual['responsaveis_grupo_atendimento']
        | atendimento_atual['atendentes_grupo_atendimento']
        | User.objects.filter(pk=tarefa_chamado.responsavel_id)
    ).distinct()

    class TarefaChamadoChangeForm(forms.ModelFormPlus):
        responsavel = forms.ModelChoiceFieldPlus(
            queryset=responsaveis,
            initial=None,
            label='Responsável',
            help_text=f'Atendentes do grupo {atendimento_atual["grupo_atendimento"] or "de atendimento do chamado"}.',
            widget=AutocompleteWidget(search_fields=User.SEARCH_FIELDS),
            required=True,
        )

        class Meta:
            model = TarefaChamado
            fields = ['situacao', 'responsavel']

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if somente_situacao:
                del self.fields['responsavel']
            if somente_responsavel:
                del self.fields['situacao']
            elif not chamado.admite_tarefa_pendente():
                # chamado resolvido/fechado/cancelado: a tarefa só pode ser encerrada
                encerramentos = (TarefaChamado.SITUACAO_FINALIZADA, TarefaChamado.SITUACAO_CANCELADA)
                self.fields['situacao'].choices = [(valor, rotulo) for valor, rotulo in TarefaChamado.SITUACAO_CHOICES if valor in encerramentos]

        def clean(self):
            clean = super().clean()
            change_situacao = clean.get('situacao', self.instance.situacao)
            change_responsavel = clean.get('responsavel', self.instance.responsavel)
            if (change_situacao, change_responsavel) == (self.instance.situacao, self.instance.responsavel):
                self.add_error(None, 'Você deve fazer alguma alteração.')
            return clean

    return TarefaChamadoChangeForm


def EditarAreaBaseConhecimentoFormFactory(user: User):
    class EditarAreaBaseConhecimentoForm(forms.ModelFormPlus):
        area = forms.ModelChoiceFieldPlus(
            queryset=GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(user),
            label='Área do Serviço',
            widget=AutocompleteWidget(search_fields=['nome']),
            required=True,
        )

        class Meta:
            model = BaseConhecimento
            fields = ('area',)

    return EditarAreaBaseConhecimentoForm


def ConfirmarAcaoFormFactory(msg: str):
    class ConfirmarAcaoForm(forms.FormPlus):
        EXTRA_INFO = msg or 'Você precisa confirmar esta ação.'
        METHOD = 'POST'
        SUBMIT_LABEL = 'Confirmo'

    return ConfirmarAcaoForm
