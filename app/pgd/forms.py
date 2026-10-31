import datetime
from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404

from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms import ReadOnlyField
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget, BrTelefoneWidget
from djtools.templatetags.filters import format_datetime
from djtools.utils import full_check_file, ha_choque_de_periodo
from pgd.models import (
    Atividade,
    AtividadeEntrega,
    ComissaoPGD,
    ComplexidadeAtividade,
    ConfiguracaoOrientacaoPit,
    ConfiguracaoOrientacaoPlanoSetorial,
    ConfiguracaoPerfilServidor,
    DocumentoAdesaoPtsServidor,
    DocumentoAdesaoServidor,
    JustificativaDesligamentoPgd,
    PeriodoPitRit,
    PlanoIndividualTrabalho,
    PlanoTrabalhoSetorial,
    PlanoTrabalhoSetorialAtividades,
    RelatorioIndividualTrabalho,
    RelatorioIndividualTrabalhoAtividade,
    RelatorioIndividualTrabalhoAtividadeEntrega,
    RelatorioIndividualTrabalhoQuestionario,
    ServicoAtividade,
    SolicitacaoAdesaoServidor,
    SubtematicaAtividade,
    TematicaAtividade,
)
from pgd.utils import get_datetime_now, setores_que_sou_chefe_hoje
from rh.models import Setor, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    data_fim_pgd1 = forms.DateFieldPlus(
        label='Data final do PGD 1 na instituição',
        required=False,
        help_text='Esta data somente é necessária se a instituição utilizou o SUAP para PGD 1.0.',
    )


def get_ext_combo_template_hierarquia_atividade(obj):
    return obj.hierarquia_atividade()


def get_ext_combo_template_hierarquia_atividade_pts(obj):
    return obj.atividade.hierarquia_atividade()


def get_ext_combo_template_tipo_entrega(obj):
    return obj.titulo


class SelecionarHierarquiaAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_por = forms.ChoiceField(
        label='Buscar por:',
        widget=forms.RadioSelect(attrs={'class': 'checkboxes'}),
        required=True,
        initial='tematica',
        choices=(('tematica', 'Temática'), ('subtematica', 'Temática -> Macroprocesso'), ('servico', 'Temática -> Macroprocesso -> Serviço')),
    )

    buscar_str = forms.CharField(label='Título:', required=False)

    def processar(self):
        buscar_por = self.cleaned_data.get('buscar_por')
        buscar_str = self.cleaned_data.get('buscar_str')

        hierarquia = None
        model_busca = None

        tematicas = []
        # Se for apenas administrador de tematica
        # - Lista apenas as da tematica dele
        eh_apenas_administrador_tematica = Atividade.eh_apenas_administrador_tematica(self.request.user)
        if eh_apenas_administrador_tematica:
            tematicas = list(TematicaAtividade.objects.filter(administradores__in=[self.request.user.get_vinculo()]).values_list('id', flat=True))

        # Regra retirada até que redefina
        # Se for apenas chefe de setor
        # - Lista apenas as da tematica dele
        # eh_apenas_chefe_setor = Atividade.eh_apenas_chefe_setor(self.request.user)
        # if eh_apenas_chefe_setor:
        #    setores = setores_que_sou_chefe_hoje(self.request.user.get_relacionamento())
        #    tematicas = list(TematicaAtividade.objects.filter(setor__in=setores).values_list('id', flat=True))

        if buscar_por == 'tematica':
            model_busca = TematicaAtividade.objects.filter(ativo=True)
            if buscar_str:
                model_busca = model_busca.filter(titulo__icontains=buscar_str)
            if tematicas:
                model_busca = model_busca.filter(id__in=tematicas)
            hierarquia = 'Temática'
        elif buscar_por == 'subtematica':
            model_busca = SubtematicaAtividade.objects.filter(ativo=True)
            if buscar_str:
                model_busca = model_busca.filter(Q(tematica__titulo__icontains=buscar_str) | Q(titulo__icontains=buscar_str))
            if tematicas:
                model_busca = model_busca.filter(tematica__id__in=tematicas)
            hierarquia = 'Temática -> Macroprocesso'
        else:
            model_busca = ServicoAtividade.objects.filter(ativo=True)
            if buscar_str:
                model_busca = model_busca.filter(
                    Q(subtematica__tematica__titulo__icontains=buscar_str)
                    | Q(subtematica__titulo__icontains=buscar_str)
                    | Q(titulo__icontains=buscar_str)
                )
            if tematicas:
                model_busca = model_busca.filter(subtematica__tematica__id__in=tematicas)
            hierarquia = 'Temática -> Macroprocesso -> Serviço'
        model_busca = model_busca.filter(ativo=True)

        return model_busca, hierarquia, buscar_por


class BuscarAtividadeQuadroForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Buscar no Título e Descrição da Atividade', required=False)

    buscar_str2 = forms.CharField(label='Buscar no Título da Entrega', required=False)

    tematica = forms.ModelChoiceFieldPlus(
        TematicaAtividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Temática', required=False
    )
    subtematica = forms.ModelChoiceFieldPlus(
        SubtematicaAtividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Macroprocesso', required=False
    )
    servico = forms.ModelChoiceFieldPlus(ServicoAtividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Serviço', required=False)
    atividade = forms.ModelChoiceFieldPlus(Atividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Atividade', required=False)

    pode_ser_teletrabalho = forms.ChoiceField(
        label='Pode ser executada na modalidade Teletrabalho?',
        initial=None,
        required=False,
        choices=[(None, '-------------'), ('1', 'Sim'), ('2', 'Não')],
    )
    ativo = forms.ChoiceField(
        label='Ativo?',
        required=False,
        initial=None,
        choices=[(None, '-------------'), ('1', 'Sim'), ('2', 'Não'), ('3', 'Com inativação programada')],
    )

    ordenar_por = forms.ChoiceField(
        label='Ordenar por:',
        required=False,
        initial='hierarquia',
        choices=(
            ('hierarquia', 'Hierarquia'),
            ('tematica__titulo', 'Título da Temática'),
            ('subtematica__titulo', 'Título do Macroprocesso'),
            ('servico__titulo', 'Título do Serviço'),
            ('titulo', 'Título da Atividade'),
        ),
    )

    organizacao = forms.ChoiceField(
        label='Organizar por:',
        required=False,
        initial='aba_por_tematica',
        choices=(
            ('aba_por_tematica', 'Em Abas por Temática'),
            ('lista_paginada', 'Atividades em Lista Paginada'),
        ),
    )


class BuscarSelecionarAtividadeAdicionarPitForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Buscar no Título e Descrição da Atividade', required=False)

    buscar_str2 = forms.CharField(label='Buscar no Título da Entrega', required=False)

    pts = forms.ModelChoiceFieldPlus(PlanoTrabalhoSetorial.objects.all(), widget=AutocompleteWidget(multiple=False), label='PTS', required=False)

    tematica = forms.ModelChoiceFieldPlus(
        TematicaAtividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Temática', required=False
    )
    subtematica = forms.ModelChoiceFieldPlus(
        SubtematicaAtividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Macroprocesso', required=False
    )
    servico = forms.ModelChoiceFieldPlus(ServicoAtividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Serviço', required=False)
    atividade = forms.ModelChoiceFieldPlus(Atividade.objects.all(), widget=AutocompleteWidget(multiple=False), label='Atividade', required=False)

    pode_ser_teletrabalho = forms.ChoiceField(
        label='Pode ser executada na modalidade Teletrabalho?',
        initial=None,
        required=False,
        choices=[(None, '-------------'), ('1', 'Sim'), ('2', 'Não')],
    )
    ativo = forms.ChoiceField(label='Ativo?', required=False, initial=None, choices=[(None, '-------------'), ('1', 'Sim'), ('2', 'Não')])

    ordenar_por = forms.ChoiceField(
        label='Ordenar por:',
        required=False,
        initial='hierarquia',
        choices=(
            ('hierarquia', 'Hierarquia'),
            ('atividade__tematica__titulo', 'Título da Temática'),
            ('atividade__subtematica__titulo', 'Título do Macroprocesso'),
            ('atividade__servico__titulo', 'Título do Serviço'),
            ('atividade__titulo', 'Título da Atividade'),
        ),
    )

    organizacao = forms.ChoiceField(
        label='Organizar por:',
        required=False,
        initial='aba_por_tematica',
        choices=(
            ('aba_por_tematica', 'Em Abas por Temática'),
            ('lista_paginada', 'Atividades em Lista Paginada'),
        ),
    )

    def __init__(self, *args, **kwargs):
        self.pts_aptos = kwargs.pop('pts_aptos', None)
        super().__init__(*args, **kwargs)
        self.fields['pts'].queryset = self.pts_aptos


class AtividadeCadastrarForm(forms.ModelFormPlus):
    # Utilizado na cadastro de nova atividade

    tematica = ReadOnlyField(label='Temática')
    subtematica = ReadOnlyField(label='Submetática')
    servico = ReadOnlyField(label='Serviço')

    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    class Meta:
        model = Atividade
        exclude = 'ativo', 'situacao_cadastro', 'solicitado_por'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        hierarquia_nivel = self.request.GET.get('hierarquia_nivel')
        hierarquia_id = self.request.GET.get('hierarquia_id')

        tematica = None
        subtematica = None
        servico = None

        if hierarquia_nivel == 'tematica':
            tematica = get_object_or_404(TematicaAtividade, id=hierarquia_id)
        elif hierarquia_nivel == 'subtematica':
            subtematica = get_object_or_404(SubtematicaAtividade, id=hierarquia_id)
            tematica = subtematica.tematica
        else:
            servico = get_object_or_404(ServicoAtividade, id=hierarquia_id)
            subtematica = servico.subtematica
            tematica = subtematica.tematica

        self.fields['tematica'].widget.display_value = tematica.titulo
        self.fields['tematica'].initial = tematica
        self.fields['subtematica'].widget.display_value = subtematica.titulo if subtematica else '-'
        self.fields['subtematica'].initial = subtematica
        self.fields['servico'].widget.display_value = servico.titulo if servico else '-'
        self.fields['servico'].initial = servico

        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(self.request.user)
        if not pode_solicitar_cadastro_alteracao:
            del self.fields['justificativa']
            del self.fields['confirmacao']
            del self.fields['senha']

    def clean(self):
        tematica = self.cleaned_data.get('tematica')

        # Se for apenas administrador de tematica
        # - Só pode cadastrar ou alterar se for Adm da tematica desta atividade
        eh_apenas_administrador_tematica = Atividade.eh_apenas_administrador_tematica(self.request.user)
        if eh_apenas_administrador_tematica:
            estah_como_adm_tematica_desta_atividade = tematica.administradores.filter(id=self.request.user.get_vinculo().id).exists()
            if not estah_como_adm_tematica_desta_atividade:
                raise ValidationError(
                    'O usuário deve ser administrador desta atividade (se o usuário for apenas administrador de Temática de atividade). '
                )

        # Regra retirada até que redefina
        # Se for apenas chefe de setor
        # - Só pode cadastrar se for chefe do setor da tematica
        # eh_apenas_chefe_setor = Atividade.eh_apenas_chefe_setor(self.request.user)
        # if eh_apenas_chefe_setor and tematica.setor:
        #     setores = setores_que_sou_chefe_hoje(self.request.user.get_relacionamento())
        #     if tematica.setor not in setores:
        #        raise ValidationError('O usuário deve ser chefe do setor desta temática (se o usuário for apenas Chefe de Setor). ')

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)

        obj.ativo = True
        obj.situacao_cadastro = Atividade.CADASTRADO

        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(self.request.user)
        if pode_solicitar_cadastro_alteracao:
            obj.situacao_cadastro = Atividade.SOLICITADO
            obj.solicitado_por = self.request.user
            obj.justificativa_solicitacao = self.cleaned_data.get('justificativa')
            obj.ativo = False

        obj.save()
        return obj


class AtividadeForm(forms.ModelFormPlus):
    # Utilizado na edição da atividade

    tematica = ReadOnlyField(label='Temática')
    subtematica = ReadOnlyField(label='Submetática')
    servico = ReadOnlyField(label='Serviço')

    class Meta:
        model = Atividade
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['tematica'].widget.display_value = self.instance.tematica.titulo
        self.fields['tematica'].initial = self.instance.tematica
        self.fields['subtematica'].widget.display_value = self.instance.subtematica.titulo if self.instance.subtematica else '-'
        self.fields['subtematica'].initial = self.instance.subtematica or None
        self.fields['servico'].widget.display_value = self.instance.servico.titulo if self.instance.servico else '-'
        self.fields['servico'].initial = self.instance.servico or None

    def clean(self):
        tematica = self.cleaned_data.get('tematica')

        # Se for apenas administrador de tematica
        # - Só pode cadastrar ou alterar se for Adm da tematica desta atividade
        eh_apenas_administrador_tematica = Atividade.eh_apenas_administrador_tematica(self.request.user)
        if eh_apenas_administrador_tematica:
            estah_como_adm_tematica_desta_atividade = tematica.administradores.filter(id=self.request.user.get_vinculo().id).exists()
            if not estah_como_adm_tematica_desta_atividade:
                raise ValidationError(
                    'O usuário deve ser administrador desta atividade (se o usuário for apenas administrador de Temática de atividade). '
                )

        # Se for apenas chefe de setor
        # - Só pode cadastrar se for chefe do setor da tematica
        # eh_apenas_chefe_setor = Atividade.eh_apenas_chefe_setor(self.request.user)
        # if eh_apenas_chefe_setor and tematica.setor:
        #     setores = setores_que_sou_chefe_hoje(self.request.user.get_relacionamento())
        #     if tematica.setor not in setores:
        #        raise ValidationError('O usuário deve ser chefe do setor desta temática (se o usuário for apenas Chefe de Setor). ')


class AtividadeEntregaFormset(forms.models.BaseInlineFormSet):
    def clean(self):
        qtd = 0
        for form in self.forms:
            if hasattr(form, 'cleaned_data') and form.cleaned_data.get('ativo'):
                qtd += 1
        if qtd < 1:
            raise forms.ValidationError('Você deve cadastrar ao menos uma entrega ativa')

        if hasattr(self, 'cleaned_data'):
            lista_ids_apagar = []
            for item in self.cleaned_data:
                if item.get('DELETE'):
                    if item.get('id'):
                        lista_ids_apagar.append(item.get('id').id)
                        if item.get('id').atividade.original:
                            raise forms.ValidationError('Impossível apagar uma entrega relacionada a uma solicitação de alteração de atividade.')
                        if not item.get('id').pode_apagar_uma_atividade_entrega():
                            raise forms.ValidationError('Impossível apagar uma entrega que tenha vínculo com algum RIT.')
            if lista_ids_apagar and not AtividadeEntrega.pode_apagar_atividades_entrega(lista_ids_apagar):
                raise forms.ValidationError('A atividade deve ter, no mínimo, uma entrega ativa.')


class ComplexidadeAtividadeForm(forms.ModelFormPlus):
    class Meta:
        model = ComplexidadeAtividade
        exclude = ()

    def clean(self):
        if (
            self.data.get('ativo')
            and self.instance.faixa_complexidade.ativo
            and not (self.cleaned_data.get('tempo_execucao_remoto', 0) > 0 or self.cleaned_data.get('tempo_execucao_presencial', 0) > 0)
        ):
            raise ValidationError(
                'Se você deseja Ativar a atividade, deve informar um valor maior que zero em pelo menos um tempo de execução para cada Faixa de Complexidade.'
            )


class PlanoTrabalhoSetorialAddForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoTrabalhoSetorial
        fields = ('setor', 'data_inicio', 'data_fim', 'auxiliares')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = setores_que_sou_chefe_hoje(self.request.user.get_relacionamento())


class PlanoTrabalhoSetorialEditarSetorForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoTrabalhoSetorial
        fields = ('setor',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = setores_que_sou_chefe_hoje(self.request.user.get_relacionamento())


class PlanoTrabalhoSetorialEditarAuxiliaresForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoTrabalhoSetorial
        fields = ('auxiliares',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['auxiliares'].queryset = Vinculo.objects.filter(user__is_active=True).servidores()


class PlanoTrabalhoSetorialEditarVigenciaForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoTrabalhoSetorial
        fields = ('data_inicio', 'data_fim')


class EditarTelefonePgdForm(forms.ModelFormPlus):
    telefone = forms.BrTelefoneField(label='Telefone para Contato PGD', max_length=14, widget=BrTelefoneWidget(), required=True)

    class Meta:
        model = SolicitacaoAdesaoServidor
        fields = (
            'preferencia_contato',
            'telefone',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preferencia_contato'].required = True


class PlanoTrabalhoSetorialEditarDocumentacaoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoTrabalhoSetorial
        fields = (
            'doc_horario_funcionamento_setor',
            'doc_escala_trabalho_setor',
            'doc_regras_planejamento_setor',
            'doc_infraestrutura_minima',
            'doc_cohecimento_tecnico',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields['doc_horario_funcionamento_setor'] = TinyMCEFormField(label='Horário de funcionamento semanal do setor', required=False)
        self.fields['doc_escala_trabalho_setor'] = TinyMCEFormField(label='Escala de trabalho presencial', required=False)
        self.fields['doc_regras_planejamento_setor'] = TinyMCEFormField(label='Periodicidade e os horários de planejamento do setor', required=False)
        self.fields['doc_infraestrutura_minima'] = TinyMCEFormField(
            label='Infraestrutura física, material e tecnológica mínima necessária', required=False
        )
        self.fields['doc_cohecimento_tecnico'] = TinyMCEFormField(label='Conhecimento técnico necessário', required=False)


class PlanoTrabalhoSetorialVincularAtividadeForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoTrabalhoSetorialAtividades
        # COmentdo depois da implementacao do vincular em lote
        # Comentado pois dava erro no ruserver
        # fields = ('plano_trabalho_setorial', 'atividade', 'modalidades_execucao')
        exclude = ()

    def __init__(self, *args, **kwargs):
        self.plano_trabalho_setorial = kwargs.pop('pts', None)
        self.atividades_ja_vinculados = kwargs.pop('atividades_ja_vinculados', None)

        super().__init__(*args, **kwargs)

        self.fields['plano_trabalho_setorial'].widget = forms.HiddenInput()
        self.fields['plano_trabalho_setorial'].initial = self.plano_trabalho_setorial.id

        # self.fields['atividade'].queryset = Atividade.objects.filter(ativo=True).exclude(id__in=self.atividades_ja_vinculados.values_list('atividade__id', flat=True))
        self.fields['atividade'].queryset = self.plano_trabalho_setorial.get_atividades_para_adicionar()


class PlanoTrabalhoSetorialVincularAtividadeEmLoteForm(forms.FormPlus):
    atividades = forms.MultipleModelChoiceFieldPlus(
        Atividade.objects.all(),
        widget=AutocompleteWidget(multiple=True, extraParams={'ext_combo_template': get_ext_combo_template_hierarquia_atividade}),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        self.atividades_para_adicionar = kwargs.pop('atividades_para_adicionar', None)

        super().__init__(*args, **kwargs)

        self.fields['atividades'].queryset = self.atividades_para_adicionar


class JustificativaForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa/Observação')


class JustificativaComSenhaForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class EntregarRitForm(forms.FormPlus):
    justificativa_entrega = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa')
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class DevolverRitConfirmacaoForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa/Observação')

    confirmacao2 = forms.BooleanField(
        label='Estou ciente que todas as distribuições de horas deste RIT serão desfeitas (caso existam)', initial=False, required=True
    )
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class JustificativaComSenhaIrreverssivelForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação e estou ciente de que é IRREVERSSÍVEL', initial=False, required=True)
    senha = forms.PasswordField()


class HomologarRitForm(forms.FormPlus):
    justificativa_homologacao = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa')
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class DistribuirHorasAutoRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(
        label='Todas as distribuições de horas referentes a este RIT serão DESFEITAS e será realizada uma NOVA DISTRIBUIÇÃO.',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(
        label='Distribuir CH apenas para o período do RIT (caso selecione esta opção o SUAP irá distribuir CH apenas para o período do RIT não para irá distribuir para o semestre e para compensações específicas).',
        initial=False,
        required=False,
    )
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class DesfazerDistribuirHorasAutoRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(
        label='Todas as distribuições de horas referentes a este RIT serão DESFEITAS e será realizada uma NOVA DISTRIBUIÇÃO.',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA', initial=False, required=True)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class AjustarHorasSemestreRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(
        label='Todas as distribuições de horas referentes ao semestre deste RIT serão DESFEITAS e será realizada uma NOVA DISTRIBUIÇÃO.',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(
        label='Desejo utilizar as horas distribuídas para compensar automaticamente os débitos referentes ao semestre', initial=False, required=False
    )
    horas = forms.TimeFieldPlus(label='Qtd de horas que desejo distribuir', required=False)
    confirmacao4 = forms.BooleanField(label='Desejo distribuir todas as horas ainda não distribuídas', initial=False, required=False)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.rit = kwargs.pop('rit', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        horas = self.cleaned_data.get('horas')
        confirmacao4 = self.cleaned_data.get('confirmacao4')
        if not horas and not confirmacao4:
            raise ValidationError(
                'É preciso informar uma quantidade de horas a distribuir OU informar que deseja distribuir todas as horas ainda não distribuídas '
            )
        if horas and confirmacao4:
            raise ValidationError(
                'Impossível informar uma quantidade de horas a distribuir e ao mesmo tempo informar que deseja distribuir todas as horas ainda não distribuídas '
            )
        if horas:
            segundos = horas.hour * 60 * 60 + horas.minute * 60 + horas.second
            if segundos > self.rit.ch_a_distribuir:
                raise ValidationError(
                    'Impossível informar uma quantidade de horas a distribuir maior que a quatidade de horas ainda disponíveis a distribuir'
                )


class DesfazerDistribuirHorasSemestreRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(label='A distribuição de horas referente ao semestre deste RIT será DESFEITA.', initial=False, required=True)
    confirmacao2 = forms.BooleanField(label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA', initial=False, required=True)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class DesfazerDistribuirHorasCompensacaoEspecificaRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(label='A distribuição de horas referente a compensação específica será DESFEITA.', initial=False, required=True)
    confirmacao2 = forms.BooleanField(label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA', initial=False, required=True)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class ConfirmacaoComSenhaForm(forms.FormPlus):
    # justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class SolicitarAdesaoPtsForm(forms.FormPlus):
    adesao_pgd = forms.ModelChoiceFieldPlus(SolicitacaoAdesaoServidor.objects.all(), label='Selecione a adesão', required=True)
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.adesoes_pgd = kwargs.pop('adesoes_pgd', None)
        super().__init__(*args, **kwargs)
        self.fields['adesao_pgd'].queryset = self.adesoes_pgd


class ConfirmacaoDeferirSolicitacaoAlteracaoAtividadeForm(forms.FormPlus):
    operacao = forms.ChoiceField(
        label='Como deseja deferir esta solicitação?',
        required=True,
        initial='deferir_alterar',
        choices=(
            ('deferir_alterar', 'Alterar/Adicionar dados na atividade original com base na atividade da solicitação E Deferir Solicitação.'),
            ('deferir', 'Somente Deferir Solicitação sem Alterar/Adicionar dados na atividade original.'),
        ),
    )

    confirmacao_def = forms.BooleanField(
        label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA.', initial=False, required=True
    )
    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.permite_editar_dados_da_original = kwargs.pop('permite_editar_dados_da_original', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        operacao = self.cleaned_data.get('operacao')
        if not self.permite_editar_dados_da_original and operacao == 'deferir_alterar':
            raise ValidationError(
                'Se a atividade da solicitação teve alterações nas Entregas ou nas Complexidades não é possível Alterar/Adicionar dados na atividade original. Você deve selecionar a opção de Somente Deferir'
            )


class EnviarEmailComSenhaForm(forms.FormPlus):
    mensagem = forms.CharField(widget=forms.Textarea, required=True, label='Mensagem')

    senha = forms.PasswordField()


class SolicitarAdesaoPgdForm(forms.FormPlus):
    telefone = forms.BrTelefoneField(label='Telefone para Contato PGD', max_length=14, widget=BrTelefoneWidget(), required=True)
    preferencia_contato = forms.ChoiceField(
        label='Preferência de Contato',
        required=True,
        initial=SolicitacaoAdesaoServidor.PREFERENCIA_CONTATO_LIGACAO,
        choices=SolicitacaoAdesaoServidor.PREFERENCIA_CONTATO_CHOICES,
    )
    confirmacao = forms.BooleanField(
        label='Confirmo esta Solicitação de Adesão e estou de acordo com todas as regras aqui descritas', initial=False, required=True
    )
    senha = forms.PasswordField()


class CadastrarDesligamentoInicioPgdForm(forms.FormPlus):
    data_desligamento_efeitos_a_partir_de = forms.DateFieldPlus(label='Com efeitos a partir de', required=True)


class CadastrarDesligamentoPgdForm(forms.FormPlus):
    justificativa = forms.ModelChoiceFieldPlus(JustificativaDesligamentoPgd.objects.all(), label='Justificativa', required=True)
    data_desligamento_efeitos_a_partir_de = forms.DateFieldPlus(label='Com efeitos a partir de', required=True)
    observacao = forms.CharField(widget=forms.Textarea, required=False, label='Observação')

    confirmacao = forms.BooleanField(label='Confirmo o cadastro do Desligamento do PGD', initial=False, required=True)
    confirmacao2 = forms.BooleanField(initial=False, required=True)
    confirmacao3 = forms.BooleanField(
        label='Confirmo que estou ciente de que este desligamento só poderá ser cancelado até o dia anterior da data de efeitos',
        initial=False,
        required=True,
    )
    senha = forms.PasswordField()

    fieldsets = (
        ('Dados do desligamento', {'fields': ('justificativa', 'data_desligamento_efeitos_a_partir_de', 'observacao')}),
        ('Confirmações', {'fields': ('confirmacao', 'confirmacao2', 'confirmacao3')}),
        ('Senha', {'fields': ('senha',)}),
    )

    def __init__(self, *args, **kwargs):
        self.lista_justificativas = kwargs.pop('lista_justificativas', None)
        self.perfil_user_estah_cadastrando = kwargs.pop('perfil_user_estah_cadastrando', None)
        super().__init__(*args, **kwargs)
        self.fields['justificativa'].queryset = self.lista_justificativas
        self.fields[
            'confirmacao2'
        ].label = f'Tem certeza que deseja cadastrar este desligamento com a data de efeitos informada mesmo considerando que a data de hoje é {format_datetime(get_datetime_now().date())}?'

    def clean(self):
        data_desligamento_efeitos_a_partir_de = self.cleaned_data.get('data_desligamento_efeitos_a_partir_de')

        if self.perfil_user_estah_cadastrando == 'chefe':
            # - A data de efeitos não será retroativo e esta deve ser escolhida pela chefia
            #   num intervalo de no mínimo 10 dias corridos pra frente e no máximo 30 dias.
            dez_dias_depois = get_datetime_now().date() + relativedelta(days=10)
            trinta_dias_depois = get_datetime_now().date() + relativedelta(days=30)
            if not (data_desligamento_efeitos_a_partir_de >= dez_dias_depois and data_desligamento_efeitos_a_partir_de <= trinta_dias_depois):
                raise ValidationError(
                    'A data de efeitos não será retroativo e esta deve ser escolhida pela chefia num intervalo de no mínimo 10 dias corridos pra frente e no máximo 30 dias.'
                )


class SolicitarDesligamentoPgdForm(forms.FormPlus):
    justificativa = forms.ModelChoiceFieldPlus(JustificativaDesligamentoPgd.objects.all(), label='Justificativa', required=True)
    data_desligamento_efeitos_a_partir_de = forms.DateFieldPlus(label='Com efeitos a partir de', required=True)
    observacao = forms.CharField(widget=forms.Textarea, required=False, label='Observação')

    confirmacao = forms.BooleanField(
        label='Confirmo este Desligamento e estou de acordo com todas as regras aqui descritas', initial=False, required=True
    )
    senha = forms.PasswordField()


class CriarPitForm(forms.FormPlus):
    adesao_pgd = forms.ModelChoiceFieldPlus(SolicitacaoAdesaoServidor.objects.all(), label='Selecione a adesão', required=True)
    periodo_pit_rit = forms.ModelChoiceFieldPlus(
        PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'), label='Competência', required=True
    )

    confirmacao = forms.BooleanField(
        label='Confirmo esta Solicitação de Adesão e estou de acordo com todos as regras aqui descritas', initial=False, required=True
    )
    senha = forms.PasswordField()

    fieldsets = (
        ('Dados básicos', {'fields': ('periodo_pit_rit', 'adesao_pgd')}),
        ('Confirmação', {'fields': ('confirmacao', 'senha')}),
    )

    def __init__(self, *args, **kwargs):
        self.adesoes_pgd = kwargs.pop('adesoes_pgd', None)
        super().__init__(*args, **kwargs)
        self.fields['adesao_pgd'].queryset = self.adesoes_pgd

    def clean(self):
        periodo_pit_rit = self.cleaned_data.get('periodo_pit_rit')
        adesao_pgd = self.cleaned_data.get('adesao_pgd')
        pode_finalizar_cadastro, erros = PlanoIndividualTrabalho.pode_finalizar_cadastro(
            user=self.request.user, periodo_pit_rit=periodo_pit_rit, adesao_pgd=adesao_pgd, retornar_lista_erros=True
        )
        if not pode_finalizar_cadastro:
            erro = ' / '.join(list(erros))
            raise forms.ValidationError(f'Erro ao cadastrar o PIT: {erro}')
        return super().clean()


class ComissaoPGDForm(forms.ModelFormPlus):
    confirmacao = forms.BooleanField(label='Confirmo as informações', initial=False, required=True)
    senha = forms.PasswordField()

    class Meta:
        model = ComissaoPGD
        exclude = ()

    def clean(self):
        cancelado = self.cleaned_data.get('cancelado')
        campus_abragencia = self.cleaned_data.get('campus_abragencia')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        eh_sistemica = self.cleaned_data.get('eh_sistemica')

        # Uma comissão Sistêmica não pode ter campus_abragencia
        if eh_sistemica and campus_abragencia:
            raise ValidationError('Se a comissão é sistêmica não pode ter Abrangência (campus).')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos para as mesmas UOs ou Sistêmica
        if not cancelado:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = ComissaoPGD.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.instance.id)
            if eh_sistemica:
                ja_salvos = ja_salvos.filter(eh_sistemica=True).distinct()
            else:
                ja_salvos = ja_salvos.filter(eh_sistemica=False, campus_abragencia__in=campus_abragencia.all()).distinct()
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (data_inicio, data_fim) if data_fim else (data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos em comissões com a mesma Abrangência (Sistêmica ou Campus)')


class ConfiguracaoOrientacaoPlanoSetorialForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoOrientacaoPlanoSetorial
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['orientacao'] = TinyMCEFormField(label='Orientações')

    def clean(self):
        cancelado = self.cleaned_data.get('cancelado')
        campus_abragencia = self.cleaned_data.get('campus_abragencia')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        eh_sistemica = self.cleaned_data.get('eh_sistemica')

        # Uma comissão Sistêmica não pode ter campus_abragencia
        if eh_sistemica and campus_abragencia:
            raise ValidationError('Se a orientação é sistêmica não pode ter Abrangência (campus).')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos para as mesmas UOs ou Sistêmica
        if not cancelado and data_inicio:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = ConfiguracaoOrientacaoPlanoSetorial.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.instance.id)
            if eh_sistemica:
                ja_salvos = ja_salvos.filter(eh_sistemica=True).distinct()
            else:
                ja_salvos = ja_salvos.filter(eh_sistemica=False, campus_abragencia__in=campus_abragencia.all()).distinct()
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (data_inicio, data_fim) if data_fim else (data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos em orientações com a mesma Abrangência (Sistêmica ou Campus).')


class ConfiguracaoOrientacaoPitForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoOrientacaoPit
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['orientacao'] = TinyMCEFormField(label='Orientações')

    def clean(self):
        cancelado = self.cleaned_data.get('cancelado')
        campus_abragencia = self.cleaned_data.get('campus_abragencia')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        eh_sistemica = self.cleaned_data.get('eh_sistemica')

        # Uma comissão Sistêmica não pode ter campus_abragencia
        if eh_sistemica and campus_abragencia:
            raise ValidationError('Se a orientação é sistêmica não pode ter Abrangência (campus).')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos para as mesmas UOs ou Sistêmica
        if not cancelado and data_inicio:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = ConfiguracaoOrientacaoPit.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.instance.id)
            if eh_sistemica:
                ja_salvos = ja_salvos.filter(eh_sistemica=True).distinct()
            else:
                ja_salvos = ja_salvos.filter(eh_sistemica=False, campus_abragencia__in=campus_abragencia.all()).distinct()
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (data_inicio, data_fim) if data_fim else (data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos em orientações com a mesma Abrangência (Sistêmica ou Campus).')


class ConfiguracaoPerfilServidorForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoPerfilServidor
        exclude = ()

    def clean(self):
        deve_ter_funcao = self.cleaned_data.get('deve_ter_funcao')
        funcoes = self.cleaned_data.get('funcoes')

        # Se deve ter obrigatoriamente funcao deve dizer quais
        if deve_ter_funcao and not (funcoes):
            raise ValidationError('Se o Servidor deve ter função você deve informar quais.')


class DocumentoAdesaoServidorForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAdesaoServidor
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'] = TinyMCEFormField(label='Descrição')


class DocumentoAdesaoPtsServidorForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAdesaoPtsServidor
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'] = TinyMCEFormField(label='Descrição')


class PeriodoPitRitForm(forms.ModelFormPlus):
    class Meta:
        model = PeriodoPitRit
        exclude = ()

    def clean(self):
        cancelado = self.cleaned_data.get('cancelado')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos
        if not cancelado:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = PeriodoPitRit.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.instance.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (data_inicio, data_fim) if data_fim else (data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos.')


class PlanoIndividualTrabalhoEditarEspecificosForm(forms.ModelFormPlus):
    data_inicial = ReadOnlyField(label='Data Inicial')

    class Meta:
        model = PlanoIndividualTrabalho
        fields = ('data_inicial', 'percentual_presencial', 'percentual_teletrabalho')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_inicial'].widget.display_value = format_datetime(self.instance.data_inicial)
        self.fields['data_inicial'].initial = self.instance.data_inicial


class BuscarAtividadeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Título:', required=False)


class AdicionarAtividadeRitForm(forms.FormPlus):
    atividade = ReadOnlyField(label='Atividade')

    tempo_planejado = forms.DecimalFieldPlus(initial='0,00', label='Tempo planejado (Em horas)', required=True)
    descricao = forms.CharField(widget=forms.Textarea, required=False, label='Descrição')
    data_prazo = forms.DateFieldPlus(label='Prazo', required=False)

    class Media:
        js = ['/static/pgd/js/ConverteHoras.js']

    def __init__(self, *args, **kwargs):
        self.pts_atividade = kwargs.pop('pts_atividade', None)
        self.rit = kwargs.pop('rit', None)

        super().__init__(*args, **kwargs)

        self.fields['atividade'].widget.display_value = str(self.pts_atividade.atividade)
        self.fields['atividade'].initial = self.pts_atividade

    def clean(self):
        if not (self.cleaned_data.get('tempo_planejado', 0) > 0):
            raise ValidationError('O tempo planejado deve ser maior que zero.')
        if self.cleaned_data.get('data_prazo'):
            data_ini = self.rit.get_datas_periodo_planejamento_rit()[0]
            # data_fim = self.rit.get_datas_periodo_planejamento_rit()[1]
            data_fim = self.rit.get_data_final()
            if not (data_ini <= self.cleaned_data.get('data_prazo') <= data_fim):
                raise ValidationError('O prazo não pode extrapolar o período do planejamento.')
            # Se tiver desligamento na adesão
            if self.rit.pit.adesao.data_desligamento_efeitos_a_partir_de:
                if self.cleaned_data.get('data_prazo') > self.rit.pit.adesao.data_desligamento_efeitos_a_partir_de:
                    raise ValidationError('O prazo não pode extrapolar a data dda efetivação do Desligamento.')


class EditarAtividadeRitForm(forms.ModelFormPlus):
    class Media:
        js = ['/static/pgd/js/ConverteHoras.js']

    class Meta:
        model = RelatorioIndividualTrabalhoAtividade
        fields = ('tempo_planejado', 'descricao', 'data_prazo')

    def clean(self):
        if not (self.cleaned_data.get('tempo_planejado', 0) > 0):
            raise ValidationError('O tempo planejado deve ser maior que zero.')
        if self.cleaned_data.get('data_prazo'):
            data_ini = self.instance.rit.get_datas_periodo_planejamento_rit()[0]
            # data_fim = self.instance.rit.get_datas_periodo_planejamento_rit()[1]
            data_fim = self.instance.rit.get_data_final()
            if not (data_ini <= self.cleaned_data.get('data_prazo') <= data_fim):
                raise ValidationError('O prazo não pode extrapolar o período do planejamento.')


class CadastrarEntregaForm(forms.ModelFormPlus):
    fieldsets = (
        (
            '',
            {
                'fields': (
                    'rit_atividade',
                    'tipo_entrega',
                    'descricao',
                    'prioridade',
                    ('qtd_entregas', 'tempo_executado', 'executada_em_teletrabalho'),
                    ('data_iniciou', 'data_finalizou'),
                    'anexo',
                )
            },
        ),
    )

    class Meta:
        model = RelatorioIndividualTrabalhoAtividadeEntrega
        fields = (
            'rit_atividade',
            'tipo_entrega',
            'prioridade',
            'descricao',
            'executada_em_teletrabalho',
            'qtd_entregas',
            'tempo_executado',
            'data_iniciou',
            'data_finalizou',
            'anexo',
        )

    class Media:
        js = ['/static/pgd/js/ConverteHoras.js']

    def __init__(self, *args, **kwargs):
        self.rit_atividade = kwargs.pop('rit_atividade', False)
        super().__init__(*args, **kwargs)
        self.fields['qtd_entregas'].initial = 1
        self.fields['data_iniciou'].initial = min(datetime.date.today(), self.rit_atividade.rit.pit.periodo_pit_rit.data_fim)
        self.fields['data_finalizou'].initial = min(datetime.date.today(), self.rit_atividade.rit.pit.periodo_pit_rit.data_fim)
        self.fields['anexo'].max_file_size = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        self.fields['tipo_entrega'] = forms.ModelChoiceFieldPlus(
            self.rit_atividade.atividade_pts.atividade.get_entregas(),
            widget=AutocompleteWidget(multiple=False, ext_combo_template=get_ext_combo_template_tipo_entrega),
            required=True,
        )
        self.fields['rit_atividade'].initial = self.rit_atividade.id
        self.fields['rit_atividade'].widget = forms.HiddenInput()

    def clean_anexo(self):
        content = self.cleaned_data.get('anexo', None)
        full_check_file(content, check_required=False)
        return content

    def clean(self):
        # A data das entregas não podem extrapolar os limites das datas do planejamento
        data_ini_rit = self.rit_atividade.rit.get_datas_periodo_planejamento_rit()[0]
        # data_fim_rit = self.rit_atividade.rit.get_datas_periodo_planejamento_rit()[1]
        data_fim_rit = self.rit_atividade.rit.get_data_final()
        data_iniciou = self.cleaned_data.get('data_iniciou')
        data_finalizou = self.cleaned_data.get('data_finalizou')
        if not data_iniciou or not data_finalizou:
            raise forms.ValidationError('Informe as data de início e final')
        if not (data_iniciou <= data_finalizou):
            raise forms.ValidationError('A data de início deve ser menor que a de finalização')
        if not (data_ini_rit <= data_iniciou <= data_fim_rit) or not (data_ini_rit <= data_finalizou <= data_fim_rit):
            raise forms.ValidationError('A data de início e de finalização não devem extrapolar o período de planejamento')

        adesao_pgd_vigente = self.rit_atividade.rit.pit.adesao
        if (
            adesao_pgd_vigente
            and adesao_pgd_vigente.data_desligamento_efeitos_a_partir_de
            and not (data_finalizou <= adesao_pgd_vigente.data_desligamento_efeitos_a_partir_de)
        ):
            raise forms.ValidationError(
                'A data de finalização não deve extrapolar o período da adesão ao PGD (verifique a partir de qual data sua adesão não estará mais vigente SEM CONSIDERAR A CARÊNCIA)'
            )

        # Valida quantidade de entregas
        qtd_entregas = self.cleaned_data.get('qtd_entregas')
        if not (qtd_entregas and qtd_entregas > 0):
            raise forms.ValidationError('Informe a quantidade de entregas.')

        return self.cleaned_data


class EditarEntregaForm(forms.ModelFormPlus):
    fieldsets = (
        (
            '',
            {
                'fields': (
                    'rit_atividade',
                    'tipo_entrega',
                    'descricao',
                    'prioridade',
                    ('qtd_entregas', 'tempo_executado', 'executada_em_teletrabalho'),
                    ('data_iniciou', 'data_finalizou'),
                    'anexo',
                )
            },
        ),
    )

    class Meta:
        model = RelatorioIndividualTrabalhoAtividadeEntrega
        fields = (
            'prioridade',
            'tipo_entrega',
            'descricao',
            'executada_em_teletrabalho',
            'qtd_entregas',
            'tempo_executado',
            'data_iniciou',
            'data_finalizou',
            'anexo',
        )

    class Media:
        js = ['/static/pgd/js/ConverteHoras.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['anexo'].max_file_size = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        self.fields['tipo_entrega'] = forms.ModelChoiceFieldPlus(
            self.instance.rit_atividade.atividade_pts.atividade.get_entregas(),
            widget=AutocompleteWidget(multiple=False, ext_combo_template=get_ext_combo_template_tipo_entrega),
            required=True,
        )

    def clean_anexo(self):
        content = self.cleaned_data.get('anexo', None)
        full_check_file(content, check_required=False)
        return content

    def clean(self):
        # A data das entregas não podem extrapolar os limites das datas do planejamento
        data_ini_rit = self.instance.rit_atividade.rit.get_datas_periodo_planejamento_rit()[0]
        # data_fim_rit = self.instance.rit_atividade.rit.get_datas_periodo_planejamento_rit()[1]
        data_fim_rit = self.instance.rit_atividade.rit.get_data_final()
        data_iniciou = self.cleaned_data.get('data_iniciou')
        data_finalizou = self.cleaned_data.get('data_finalizou')
        if not data_iniciou or not data_finalizou:
            raise forms.ValidationError('Informe as data de início e final')
        if not (data_iniciou <= data_finalizou):
            raise forms.ValidationError('A data de início deve ser menor que a de finalização')
        if not (data_ini_rit <= data_iniciou <= data_fim_rit) or not (data_ini_rit <= data_finalizou <= data_fim_rit):
            raise forms.ValidationError('A data de início e de finalização não devem extrapolar o período de planejamento')

        # Valida quantidade de entregas
        qtd_entregas = self.cleaned_data.get('qtd_entregas')
        if not (qtd_entregas and qtd_entregas > 0):
            raise forms.ValidationError('Informe a quantidade de entregas.')

        return self.cleaned_data


class EditarEntregaEmLoteForm(forms.ModelFormPlus):
    class Meta:
        model = RelatorioIndividualTrabalhoAtividadeEntrega
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if hasattr(self, 'instance') and hasattr(self.instance, 'rit_atividade'):
            self.fields['tipo_entrega'] = forms.ModelChoiceFieldPlus(
                self.instance.rit_atividade.atividade_pts.atividade.get_entregas(),
                widget=AutocompleteWidget(multiple=False, ext_combo_template=get_ext_combo_template_tipo_entrega),
                required=True,
            )

    def clean(self):
        # A data das entregas não podem extrapolar os limites das datas do planejamento
        data_ini_rit = self.instance.rit_atividade.rit.get_datas_periodo_planejamento_rit()[0]
        # data_fim_rit = self.instance.rit_atividade.rit.get_datas_periodo_planejamento_rit()[1]
        data_fim_rit = self.instance.rit_atividade.rit.get_data_final()
        data_iniciou = self.cleaned_data.get('data_iniciou')
        data_finalizou = self.cleaned_data.get('data_finalizou')
        if not (data_iniciou <= data_finalizou):
            raise forms.ValidationError('A data de início deve ser menor que a de finalização')
        if not (data_ini_rit <= data_iniciou <= data_fim_rit) or not (data_ini_rit <= data_finalizou <= data_fim_rit):
            raise forms.ValidationError('A data de início e de finalização não devem extrapolar o período de planejamento')

        # Valida quantidade de entregas
        qtd_entregas = self.cleaned_data.get('qtd_entregas')
        if not (qtd_entregas and qtd_entregas > 0):
            raise forms.ValidationError('Informe a quantidade de entregas.')

        return self.cleaned_data


class RelatorioIndividualTrabalhoAtividadeEntregaAvaliarForm(forms.FormPlus):
    tempo_homologado = forms.DecimalFieldPlus(initial='0,00', label='Tempo Homologado (Em horas)', required=True)
    nota = forms.DecimalFieldPlus(initial='0,00', label='Nota', required=True)
    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')
    homologa = forms.BooleanField(label='Homologa?', initial=False, required=False)

    confirmacao = forms.BooleanField(label='Confirmo esta operação?', initial=False, required=True)
    senha = forms.PasswordField()

    fieldsets = (
        ('Avaliação', {'fields': ('tempo_homologado', 'nota', 'justificativa', 'homologa')}),
        ('Confirmação', {'fields': ('confirmacao', 'senha')}),
    )

    def __init__(self, *args, **kwargs):
        self.rit_entrega = kwargs.pop('rit_entrega', False)
        super().__init__(*args, **kwargs)
        self.fields['tempo_homologado'].initial = self.rit_entrega.tempo_executado

    def clean(self):
        nota = self.cleaned_data.get('nota')
        if not nota or not (10 >= nota >= 0):
            raise forms.ValidationError('Nota deve ser entre 0 e 10.')

        # Homologou
        # -------------------
        tempo_homologado = self.cleaned_data.get('tempo_homologado')
        if self.cleaned_data.get('homologa'):
            # Deve ter tempo homologado
            if not tempo_homologado or not tempo_homologado > 0:
                raise forms.ValidationError('Para homologar a nota deve ser tempo homologado.')
            # Deve ter nota maior q 5
            if not nota or not nota >= 5:
                raise forms.ValidationError('Para homologar a nota deve ser maior ou igual que 5.')
        else:
            # Nao Homologou
            # -------------------
            # Nao pode ter tempo homologado
            if tempo_homologado and tempo_homologado > 0:
                raise forms.ValidationError('Para não homologar não pode ter tempo homologado.')
            # Nota deve ser menor que 5
            if not nota or not nota < 5:
                raise forms.ValidationError('Para não homologar a nota deve ser menor que 5.')
            # Deve ter justificativa
            if not (self.cleaned_data.get('justificativa')):
                raise forms.ValidationError('Para não homologar deve ter justificativa.')

        return self.cleaned_data


class RelatorioIndividualTrabalhoAtividadeEntregaAvaliarSimplesForm(forms.FormPlus):
    nota = forms.DecimalFieldPlus(initial='0,00', label='Nota', required=True)
    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')
    homologa = forms.BooleanField(label='Homologa?', initial=False, required=False)

    confirmacao = forms.BooleanField(label='Confirmo esta operação?', initial=False, required=True)
    senha = forms.PasswordField()

    fieldsets = (('Avaliação', {'fields': ('nota', 'justificativa', 'homologa')}), ('Confirmação', {'fields': ('confirmacao', 'senha')}))

    def clean(self):
        nota = self.cleaned_data.get('nota')
        if not nota or not (10 >= nota >= 0):
            raise forms.ValidationError('Nota deve ser entre 0 e 10.')

        # Homologou
        # -------------------
        if self.cleaned_data.get('homologa'):
            # Deve ter nota maior q 5
            if not nota or not nota >= 5:
                raise forms.ValidationError('Para homologar a nota deve ser maior ou igual que 5.')
        else:
            # Nao Homologou
            # -------------------
            # Nota deve ser menor que 5
            if not nota or not nota < 5:
                raise forms.ValidationError('Para não homologar a nota deve ser menor que 5.')
            # Deve ter justificativa
            if not (self.cleaned_data.get('justificativa')):
                raise forms.ValidationError('Para não homologar deve ter justificativa.')

        return self.cleaned_data


def get_ext_combo_template_cop_planejamento(obj):
    return obj.get_verbose_planejamento()


class CopiarPlanejamentoForm(forms.FormPlus):
    planejamento_copia = forms.ModelChoiceFieldPlus(RelatorioIndividualTrabalho.objects, required=True, label='Planejamento que será copiado')

    confirmacao = forms.BooleanField(
        label='Confirmo esta operação e estou de acordo que apenas as atividades que serão copiadas são apenas as relacionadas a PTSs aderidos e que já não estejam no planejamento ',
        initial=False,
        required=True,
    )
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.planejamentos_para_copiar = kwargs.pop('planejamentos_para_copiar', None)
        super().__init__(*args, **kwargs)
        self.fields['planejamento_copia'].queryset = self.planejamentos_para_copiar


class BuscarRelatorioDesligamentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    mes_ini = forms.ChoiceField(
        choices=[
            [1, 'Janeiro'],
            [2, 'Fevereiro'],
            [3, 'Março'],
            [4, 'Abril'],
            [5, 'Maio'],
            [6, 'Junho'],
            [7, 'Julho'],
            [8, 'Agosto'],
            [9, 'Setembro'],
            [10, 'Outubro'],
            [11, 'Novembro'],
            [12, 'Dezembro'],
        ],
        label='Mês',
        required=True,
    )
    ano_ini = forms.ModelChoiceField(queryset=Ano.objects, label='Ano', required=True)

    mes_fim = forms.ChoiceField(
        choices=[
            [1, 'Janeiro'],
            [2, 'Fevereiro'],
            [3, 'Março'],
            [4, 'Abril'],
            [5, 'Maio'],
            [6, 'Junho'],
            [7, 'Julho'],
            [8, 'Agosto'],
            [9, 'Setembro'],
            [10, 'Outubro'],
            [11, 'Novembro'],
            [12, 'Dezembro'],
        ],
        label='Mês',
        required=True,
    )
    ano_fim = forms.ModelChoiceField(queryset=Ano.objects, label='Ano', required=True)

    def clean(self):
        mes_ini = self.cleaned_data.get('mes_ini')
        ano_ini = self.cleaned_data.get('ano_ini')
        mes_fim = self.cleaned_data.get('mes_fim')
        ano_fim = self.cleaned_data.get('ano_fim')

        if mes_ini and ano_ini and mes_fim and ano_fim:
            data_inicio = date(ano_ini.ano, int(mes_ini), 1)
            data_final = date(ano_fim.ano, int(mes_fim), 1)
            if data_inicio > data_final:
                raise forms.ValidationError('Mês/Ano final tem que ser maior que inicial')
            if not (relativedelta(data_final, data_inicio).months < 6):
                raise forms.ValidationError('O período máximo de consulta é de 6 meses')

        return self.cleaned_data


class QuestionarioRitServidorForm(forms.ModelFormPlus):
    confirmacao = forms.BooleanField(label='Confirmo as informações', initial=False, required=True)
    senha = forms.PasswordField()

    class Meta:
        model = RelatorioIndividualTrabalhoQuestionario
        fields = (
            'pergunta_1',
            'pergunta_2',
            'pergunta_3',
            'pergunta_3_complemento',
            'pergunta_4',
            'pergunta_5',
            'pergunta_6',
            'confirmacao',
            'senha',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pergunta_1'].required = False
        self.fields['pergunta_2'].required = False
        self.fields['pergunta_3'].required = True
        self.fields['pergunta_3_complemento'].required = False
        self.fields['pergunta_4'].required = True
        self.fields['pergunta_5'].required = True
        self.fields['pergunta_6'].required = True

    def clean(self):
        pergunta_3 = self.cleaned_data.get('pergunta_3')
        pergunta_3_complemento = self.cleaned_data.get('pergunta_3_complemento')
        if pergunta_3 == RelatorioIndividualTrabalhoQuestionario.NAO and not pergunta_3_complemento:
            raise forms.ValidationError('Deve informar: Percentual de PGD que considera adequado para o seu setor ')

        return self.cleaned_data


class QuestionarioRitChefeForm(forms.ModelFormPlus):
    confirmacao = forms.BooleanField(label='Confirmo as informações', initial=False, required=True)
    senha = forms.PasswordField()

    class Meta:
        model = RelatorioIndividualTrabalhoQuestionario
        fields = (
            'pergunta_1',
            'pergunta_2',
            'pergunta_3',
            'pergunta_3_complemento',
            'pergunta_4',
            'pergunta_7',
            'pergunta_8',
            'pergunta_9',
            'pergunta_10',
            'pergunta_11',
            'pergunta_11_complemento',
            'confirmacao',
            'senha',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pergunta_1'].required = True
        self.fields['pergunta_2'].required = True
        self.fields['pergunta_3'].required = False
        self.fields['pergunta_3_complemento'].required = False
        self.fields['pergunta_4'].required = False
        self.fields['pergunta_7'].required = False
        self.fields['pergunta_8'].required = False
        self.fields['pergunta_9'].required = True
        self.fields['pergunta_10'].required = True
        self.fields['pergunta_11'].required = True
        self.fields['pergunta_11_complemento'].required = False

    def clean(self):
        pergunta_3 = self.cleaned_data.get('pergunta_3')
        pergunta_3_complemento = self.cleaned_data.get('pergunta_3_complemento')
        if pergunta_3 == RelatorioIndividualTrabalhoQuestionario.NAO and not pergunta_3_complemento:
            raise forms.ValidationError('Deve informar: Percentual de PGD que considera adequado para o seu setor ')

        pergunta_11 = self.cleaned_data.get('pergunta_11')
        pergunta_11_complemento = self.cleaned_data.get('pergunta_11_complemento')
        if pergunta_11 == RelatorioIndividualTrabalhoQuestionario.NAO and not pergunta_11_complemento:
            raise forms.ValidationError('Deve informar: Percentual de PGD que considera adequado para o setor ')

        return self.cleaned_data


class BuscarRelatorioQuestionarioRitForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    periodo = forms.ChoiceField(label='Período PIT/RIT', required=True)

    def get_choices_perguntas(self):
        fields = RelatorioIndividualTrabalhoQuestionario.objects.all()[0]._meta.get_fields()
        choice_perguntas = []
        for field in fields:
            if 'pergunta_' in field.name and '_complemento' not in field.name:
                perfil = 'Servidor/Chefe'
                if field.name in RelatorioIndividualTrabalhoQuestionario.PERGUNTAS_SERVIDOR:
                    perfil = 'Servidor'
                if field.name in RelatorioIndividualTrabalhoQuestionario.PERGUNTAS_CHEFE:
                    perfil = 'Chefe'
                choice_perguntas.append((field.name, f'{field.verbose_name} ({perfil})'))
        return choice_perguntas

    pergunta = forms.ChoiceField(label='Perguntas', required=True)

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.campis = kwargs.pop('campis', None)

        super().__init__(*args, **kwargs)

        periodos = PeriodoPitRit.objects.filter(cancelado=False).order_by('data_inicio')
        lista_periodos = []
        for s in periodos:
            d = f'{s.ano} - {s.titulo} - ({format_datetime(s.rit_data_inicio_1)} a {format_datetime(s.rit_data_fim_1)})'
            lista_periodos.append((s.id, d))
        self.fields['periodo'].choices = lista_periodos

        if self.campis:
            self.fields['campus'].queryset = self.campis

        self.fields['pergunta'].choices = self.get_choices_perguntas()


class BuscarServidoresPgdForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False
    )

    def __init__(self, *args, **kwargs):
        self.setores_chefe = kwargs.pop('setores_chefe', None)
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = self.setores_chefe
