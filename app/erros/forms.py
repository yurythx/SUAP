import datetime

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.forms import Textarea, TextInput

from comum.models import Vinculo
from djtools import forms
from djtools.forms.wizard import FormWizardPlus
from djtools.utils import get_client_ip
from erros.models import Erro, HistoricoComentarioErro, RespostaFrequente
from erros.utils import get_custom_view_name_from_url, get_hostname, get_sentry_issue_id_from_url


class ConfiguracaoForm(forms.FormPlus):
    milestone_erros_suap_id = forms.CharFieldPlus(label='ID da milestone de erros do SUAP no GITLAB', required=False, initial='312')
    label_todo_erros_suap = forms.CharFieldPlus(label='Label de erros do SUAP criados no GITLAB', required=False, initial='Planned')
    label_doing_erros_suap = forms.CharFieldPlus(label='Label de erros do SUAP em atendimento no GITLAB', required=False, initial='Doing')
    label_done_erros_suap = forms.CharFieldPlus(label='Label de erros do SUAP concluídos no GITLAB', required=False, initial='Done')
    label_feedback_erros_suap = forms.CharFieldPlus(
        label='Label de erros do SUAP aguardando feedback do usuário no GITLAB', required=False, initial='Waiting Feedback'
    )


class ErroForm(forms.ModelFormPlus):
    url = forms.CharFieldPlus(label='URL do SUAP')
    url_sentry = forms.CharFieldPlus(label='URL da Issue do Sentry', required=False)
    gitlab_issue_url = forms.CharFieldPlus(label='URL da Issue do Gitlab', required=False)

    class Meta:
        model = Erro
        exclude = ('view', 'qtd_vinculos_afetados')

    def clean_url(self):
        if not get_custom_view_name_from_url(self.cleaned_data.get('url')):
            raise ValidationError('URL inválida.')
        self.instance.view = get_custom_view_name_from_url(self.cleaned_data.get('url'))
        return self.cleaned_data['url']

    def clean_url_sentry(self):
        if not self.cleaned_data['url_sentry']:
            return None
        return self.cleaned_data['url_sentry']


class ReportarErroForm(FormWizardPlus):
    url = forms.CharField(
        label='URL com Erro',
        widget=TextInput(attrs={'readonly': 'readonly'}),
        required=True,
        help_text='É importante reportar o erro diretamente da página em que o erro esteja acontecendo, ou, diante da impossibilidade, da página imediatamente anterior',
    )
    descricao = forms.CharField(
        label='Descreva a operação que você estava realizando antes de ocorrer o erro e a mensagem de erro que o sistema apresentou',
        help_text='Esta descrição necessariamente não deverá conter dados privados, pois será um erro visível a todos os usuários',
        widget=Textarea(),
        required=True,
    )
    confirmacao_leitura = forms.BooleanField(label='Li as instruções', required=True, help_text='Confirmo que li as Instruções para Abertura de Erro')
    confirmacao_dados = forms.BooleanField(
        label='Concordo em compartilhar meus dados',
        required=True,
        help_text='Concordo em compartilhar com a equipe de Desenvolvimento do SUAP as informações do meu navegador e o meu IP',
    )

    steps = (
        [
            (
                'Confirmação de Ciência',
                {
                    'fields': (
                        'confirmacao_leitura',
                        'confirmacao_dados',
                    )
                },
            )
        ],
        [('Descrição do erro', {'fields': ('url', 'descricao')})],
    )

    def __init__(self, *args, **kwargs):
        self.url = kwargs.pop('url')
        super().__init__(*args, **kwargs)

    def next_step(self):
        if 'url' in self.fields:
            self.initial['url'] = self.url

    def clean_url(self):
        if not get_custom_view_name_from_url(self.cleaned_data.get('url', '')):
            raise ValidationError('URL inválida.')
        return self.cleaned_data['url']

    def processar(self):
        erro = Erro()
        erro.descricao = self.cleaned_data.get('descricao')
        erro.url = self.cleaned_data.get('url')
        erro.view = get_custom_view_name_from_url(erro.url)
        erro.informante = self.request.user.get_vinculo()
        erro.agent = self.request.META.get('HTTP_USER_AGENT', '-')
        erro.ip_address = get_client_ip(self.request)
        erro.maquina = get_hostname()
        erro.criar()
        return erro


class ReportarErroPorChamadoForm(forms.FormPlus):
    url = forms.CharField(label='URL com Erro', required=True, help_text='Informe a URL completa da página onde o erro ocorre.')
    descricao = forms.CharField(
        label='Descreva a operação que você estava realizando antes de ocorrer o erro',
        help_text='Esta descrição necessariamente não deverá conter dados privados, pois será um erro visível a todos os usuários',
        widget=Textarea(),
        required=True,
    )

    def clean_url(self):
        if not get_custom_view_name_from_url(self.cleaned_data.get('url', '')):
            raise ValidationError('URL inválida.')
        return self.cleaned_data['url']

    def processar(self, chamado):
        interessados_chamado = chamado.get_vinculos_interessados()
        erro = Erro()
        erro.descricao = self.cleaned_data.get('descricao')
        erro.url = self.cleaned_data.get('url')
        erro.view = get_custom_view_name_from_url(erro.url)
        erro.informante = self.request.user.get_vinculo()
        erro.agent = self.request.META.get('HTTP_USER_AGENT', '-')
        erro.ip_address = get_client_ip(self.request)
        erro.criar()

        descricao = f'Erro reportado a partir do chamado <a href="{chamado.get_absolute_url()}">#{chamado.pk}</a>.'
        HistoricoComentarioErro.objects.create(erro=erro, descricao=descricao, tipo=HistoricoComentarioErro.TIPO_COMENTARIO, automatico=True)

        for interessado in interessados_chamado:
            erro.gerenciar_interessado(
                interessado,
                habilitar=True,
                mensagem_customizada=f'foi adicionado automaticamente como interessado a partir do chamado: <a href="{chamado.get_absolute_url()}">#{chamado.pk}</a>.',
            )

        comunicacao = chamado.criar_comunicacao(
            self.request.user,
            datetime.datetime.now(),
            f'Foi reportado o erro <a href="{erro.get_absolute_url()}">#{erro.pk}</a> relacionado a este chamado.',
        )
        comunicacao.mensagem_automatica = True
        comunicacao.save()


class ComentarioErroForm(forms.FormPlus):
    descricao = forms.CharField(label='Descrição da atividade', widget=Textarea())
    situacao = forms.ChoiceField(
        label='Alterar situação',
        choices=[
            (Erro.SITUACAO_AGUARDANDO_FEEDBACK, 'Aguardando feedback'),
            (Erro.SITUACAO_RESOLVIDO, 'Resolvido'),
            (Erro.SITUACAO_EM_CORRECAO, 'Em correção'),
            (Erro.SITUACAO_CANCELADO, 'Cancelado'),
        ],
        widget=forms.RadioSelect,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        situacao_atual = kwargs.pop('situacao_atual')
        eh_atendente = kwargs.pop('eh_atendente')
        super().__init__(*args, **kwargs)
        novo_choices = [tupla for tupla in self.fields['situacao'].choices if int(tupla[0]) != situacao_atual]
        if not eh_atendente and situacao_atual == Erro.SITUACAO_AGUARDANDO_FEEDBACK:
            novo_choices = (
                (Erro.SITUACAO_EM_ANALISE, 'O erro ainda não foi resolvido'),
                (Erro.SITUACAO_RESOLVIDO, 'O erro foi resolvido'),
            )
            self.fields['situacao'].initial = Erro.SITUACAO_EM_ANALISE
        self.fields['situacao'].choices = novo_choices

    def processar(self, erro, vinculo, tipo):
        erro.comentar(vinculo=vinculo, descricao=self.cleaned_data.get('descricao'), tipo=tipo)


class SituacaoErroForm(forms.FormPlus):
    descricao = forms.CharField(label='Motivo', widget=Textarea(), required=True)

    def processar(self, erro, vinculo, situacao_id):
        erro.gerenciar_situacao(vinculo=vinculo, situacao=situacao_id, motivo=self.cleaned_data.get('descricao'))


class AlterarURLErroForm(forms.FormPlus):
    url = forms.CharFieldPlus(label='Nova URL com Erro')

    def __init__(self, *args, **kwargs):
        self.erro = kwargs.pop('erro')
        self.vinculo = kwargs.pop('vinculo')
        self.tipo = kwargs.pop('tipo')
        self.issue_id = None
        super().__init__(*args, **kwargs)
        required = False
        if self.tipo == 'erro':
            label = 'Nova URL do Erro'
            required = True
        elif self.tipo == 'sentry':
            label = 'Nova URL do Erro do Sentry'
        elif self.tipo == 'gitlab':
            label = 'Nova URL da Issue no Gitlab'
        else:
            label = 'Nova URL'
        self.fields['url'].label = label
        self.fields['url'].required = required

    def clean_url(self):
        url = self.cleaned_data.get('url')
        if self.tipo == 'erro':
            view = get_custom_view_name_from_url(url)
            if not view:
                raise ValidationError('URL inválida.')
        elif self.tipo == 'sentry':
            if url:
                URLValidator()(url)
                self.issue_id = get_sentry_issue_id_from_url(url)
                if not self.issue_id:
                    raise ValidationError('URL do Sentry inválida.')
                else:
                    self.issue_id = str(self.issue_id)
            else:
                self.issue_id = None
        else:
            if url:
                URLValidator()(url)
        return url

    def processar(self):
        url = self.cleaned_data.get('url')
        self.erro.alterar_url(self.vinculo, url, self.tipo, self.issue_id)


class AnexoErroForm(forms.FormPlus):
    descricao = forms.CharFieldPlus(label='Descrição', max_length=80)
    arquivo = forms.FileFieldPlus(filetypes=['xls', 'csv', 'doc', 'pdf', 'jpg', 'png', 'xlsx', 'txt'])

    ALERT = 'Este anexo terá visibilidade pública para todos os usuários do SUAP. Cuidado ao enviar informações que podem conter dados pessoais.'

    def __init__(self, *args, **kwargs):
        self.erro = kwargs.pop('erro')
        self.anexado_por = kwargs.pop('vinculo')
        super().__init__(*args, **kwargs)

    def processar(self):
        descricao = self.cleaned_data.get('descricao')
        arquivo = self.cleaned_data.get('arquivo')
        self.erro.anexar(self.anexado_por, descricao, arquivo)


class AtribuirErroForm(forms.FormPlus):
    atendente = forms.ModelChoiceFieldPlus(Vinculo.objects, required=True)

    def __init__(self, *args, **kwargs):
        self.erro = kwargs.pop('erro')
        self.atribuinte = kwargs.pop('atribuinte')
        super().__init__(*args, **kwargs)
        self.fields['atendente'].queryset = Vinculo.objects.filter(ativo=True, user__usuariogrupo__group__name='Analista').distinct()

    def processar(self):
        atribuido = self.cleaned_data.get('atendente')
        self.erro.atribuir(self.atribuinte, atribuido)


class UnificarErroForm(forms.FormPlus):
    erros = forms.MultipleModelChoiceFieldPlus(
        Erro.objects,
        help_text='Serão listados apenas os erros que possuem a view idêntica a do erro principal. Pode-se usar o id e a url para realizar a busca.',
    )

    def __init__(self, *args, **kwargs):
        self.erro = kwargs.pop('erro')
        self.vinculo = kwargs.pop('vinculo')
        super().__init__(*args, **kwargs)
        self.fields['erros'].queryset = (
            Erro.objects.filter(view=self.erro.view).exclude(situacao__in=Erro.SITUACOES_FINAIS).exclude(id=self.erro.id).order_by('-id')
        )

    def processar(self):
        erros = self.cleaned_data.get('erros')
        self.erro.unificar(self.vinculo, erros)


class EditarAtualizacaoErroForm(forms.ModelFormPlus):
    class Meta:
        model = Erro
        fields = ('titulo_atualizacao', 'tipo_atualizacao', 'grupos_atualizacao')

    def __init__(self, *args, **kwargs):
        self.required = kwargs.pop('required', True)
        super().__init__(*args, **kwargs)
        self.fields['tipo_atualizacao'].choices = (('', ''), *Erro.TIPO_CHOICES)
        if not self.required:
            self.fields['titulo_atualizacao'].required = False
            self.fields['tipo_atualizacao'].required = False
            self.fields['grupos_atualizacao'].required = False
            self.EXTRA_BUTTONS = [{'name': 'pular', 'value': 'Pular'}]

    def clean(self):
        titulo_atualizacao = self.cleaned_data.get('titulo_atualizacao')
        tipo_atualizacao = self.cleaned_data.get('tipo_atualizacao')
        grupos_atualizacao = self.cleaned_data.get('grupos_atualizacao')
        if self.request.POST.get('pular'):
            return self.cleaned_data
        if not self.required and not (
            (titulo_atualizacao and tipo_atualizacao and grupos_atualizacao)
            or (not titulo_atualizacao and not tipo_atualizacao and not grupos_atualizacao)
        ):
            raise ValidationError(
                'Para criar uma atualização, você deve preencher todos os campos. Deixe todos os campos vazios, se não quiser criar uma atualização.'
            )


class RespostaFrequenteForm(forms.ModelFormPlus):
    class Meta:
        model = RespostaFrequente
        fields = ['texto']
