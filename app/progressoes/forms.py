from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from comum.models import Vinculo
from comum.utils import get_sigla_reitoria, get_uo
from djtools import forms
from djtools.forms import ModelFormPlus
from djtools.forms.fields import ModelChoiceFieldPlus
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import send_notification
from documento_eletronico.models import TipoConferencia, TipoDocumento
from processo_eletronico.models import TipoProcesso
from progressoes.assinatura import SuapAssinaturaForm
from progressoes.models import (
    AvaliacaoCriterioNota,
    AvaliacaoModelo,
    AvaliacaoModeloCriterio,
    ProcessoProgressao,
    ProcessoProgressaoAvaliacao,
    ProcessoProgressaoPeriodo,
    ServidorAProgredir,
)
from rh.models import Servidor, Setor


class ConfiguracaoForm(forms.FormPlus):
    processo_eletronico_tipo_processo = forms.ModelChoiceFieldPlus(
        TipoProcesso.objects,
        label='Tipo de processo (Processo Eletrônico)',
        help_text='Geração de Processo Eletrônico: Tipo de processo',
        required=False,
    )
    processo_eletronico_tipo_documento = forms.ModelChoiceFieldPlus(
        TipoDocumento.objects,
        label='Tipo de documento (Processo Eletrônico)',
        help_text='Geração de Processo Eletrônico: Tipo de documento',
        required=False,
    )
    processo_eletronico_tipo_conferencia = forms.ModelChoiceFieldPlus(
        TipoConferencia.objects,
        label='Tipo de conferência (Processo Eletrônico)',
        help_text='Geração de Processo Eletrônico: Tipo de conferência',
        required=False,
    )

    # configuração que define se os usuários da progressão serão alertados via e-mail e notificação suap
    alertar_responsaveis_servidores_a_progredir = forms.BooleanField(
        label='Alertar Responsáveis de Servidores a Progredir?', initial=True, required=False
    )

    criar_progressao_apenas_pelo_relatorio = forms.BooleanField(
        label='Criar Progressão Apenas pelo Relatório de Servidores a Progredir?',
        help_text='Se marcado, os processos de progressão TAE serão criados apenas através do relatório de servidores a progredir: Gestão de Pessoas > Desenvolvimento de Pessoal > Avaliação de Desempenho > Relatórios > A Progredir',
        initial=True,
        required=False,
    )


class AvaliacaoModeloForm(ModelFormPlus):
    itens_avaliados = forms.MultipleModelChoiceFieldPlus(
        queryset=AvaliacaoModeloCriterio.objects,
        required=True,
        label='Critérios Avaliados',
        widget=AutocompleteWidget(
            multiple=True, attrs={'extra_style_item': 'width: 75%', 'extra_style_remove_icon': 'float: right; padding-top: 5px; padding-left: 4px'}
        ),
    )

    class Meta:
        model = AvaliacaoModelo
        exclude = []


class EstagioProbatorioAddForm(ModelFormPlus):
    avaliado = forms.ModelChoiceField(queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.has_perm('progressoes.pode_ver_apenas_processos_do_seu_campus') and not self.request.user.has_perm(
            'progressoes.pode_ver_todos_os_processos'
        ):
            usuario_logado_campus_sigla = self.request.user.get_vinculo().setor.uo.sigla
            self.fields['avaliado'].queryset = Servidor.objects.filter(setor__uo__sigla=usuario_logado_campus_sigla)
        self.instance.tipo = ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO

    class Meta:
        model = ProcessoProgressao
        exclude = ()


class ProcessoProgressaoAddForm(ModelFormPlus):
    avaliado = forms.ModelChoiceField(queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.has_perm('progressoes.pode_ver_apenas_processos_do_seu_campus') and not self.request.user.has_perm(
            'progressoes.pode_ver_todos_os_processos'
        ):
            usuario_logado_campus_sigla = self.request.user.get_vinculo().setor.uo.sigla
            self.fields['avaliado'].queryset = Servidor.objects.filter(setor__uo__sigla=usuario_logado_campus_sigla)
        self.instance.tipo = ProcessoProgressao.TIPO_PROGRESSAO_MERITO

    class Meta:
        model = ProcessoProgressao
        exclude = ()


class ProcessoProgressaoEditForm(ModelFormPlus):
    avaliado = forms.ModelChoiceField(queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS))

    class Meta:
        model = ProcessoProgressao
        exclude = ()


class EstagioProbatorioEditForm(ModelFormPlus):
    avaliado = forms.ModelChoiceField(queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS))

    class Meta:
        model = ProcessoProgressao
        exclude = ()


class ProcessoProgressaoPeriodoForm(ModelFormPlus):
    avaliacao_modelo = forms.ModelChoiceFieldPlus(queryset=AvaliacaoModelo.objects, required=True, label='Modelo de Avaliação')

    def __init__(self, *args, **kwargs):
        processo_tipo = kwargs.pop('processo_tipo', None)
        super().__init__(*args, **kwargs)
        if processo_tipo:
            self.fields['avaliacao_modelo'].queryset = AvaliacaoModelo.objects.filter(tipo=processo_tipo)
        self.fields['setor'].queryset = Setor.objects.suap().filter(excluido=False)

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            data_inicio = cleaned_data.get('data_inicio')
            data_fim = cleaned_data.get('data_fim')
            if data_fim < data_inicio:
                self.errors['data_fim'] = ['Data final deve ser maior ou igual à Data inicial.']
                del cleaned_data['data_fim']
        return cleaned_data

    class Meta:
        model = ProcessoProgressaoPeriodo
        fields = ('setor', 'data_inicio', 'data_fim', 'avaliacao_modelo')


class ProcessoProgressaoPeriodoAvaliadoresForm(ModelFormPlus):
    avaliadores_chefe = ModelChoiceFieldPlus(
        queryset=Vinculo.objects, required=False, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Chefe'
    )
    avaliadores_equipe = forms.MultipleModelChoiceFieldPlus(
        queryset=Vinculo.objects,
        required=False,
        widget=AutocompleteWidget(
            search_fields=Vinculo.SEARCH_FIELDS,
            multiple=True,
            attrs={'extra_style_item': 'width: 80%', 'extra_style_remove_icon': 'float: right; padding-top: 5px; padding-left: 4px'},
        ),
        label='Membro da Equipe',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        self.fields['avaliadores_chefe'].queryset = Vinculo.objects.funcionarios()
        self.fields['avaliadores_equipe'].queryset = Vinculo.objects.funcionarios()

        periodo = self.instance
        avaliacao_do_chefe = periodo.processoprogressaoavaliacao_set.filter(tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE)
        if avaliacao_do_chefe.exists():
            self.fields['avaliadores_chefe'].initial = avaliacao_do_chefe[0].avaliador

        self.fields['avaliadores_equipe'].initial = Vinculo.objects.funcionarios().filter(
            pk__in=periodo.processoprogressaoavaliacao_set.filter(tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_EQUIPE).values_list(
                'avaliador', flat=True
            )
        )
        if periodo.avaliacao_modelo.funcao_gratificada:
            self.fields['avaliadores_equipe'].label = 'Pares'

    class Meta:
        model = ProcessoProgressaoPeriodo
        fields = ('avaliadores_chefe', 'avaliadores_equipe')

    def remove_avaliacoes(self, avaliacoes):
        for avaliacao_removida in avaliacoes:
            # notifica a remoção
            email_avaliado = avaliacao_removida.periodo.processo_progressao.avaliado.email_notificacao
            email_avaliador = avaliacao_removida.avaliador.email_notificacao
            if email_avaliador and email_avaliador != email_avaliado and avaliacao_removida.numero_liberacoes > 0:
                avaliado = avaliacao_removida.periodo.processo_progressao.avaliado
                assunto = '[SUAP] Remoção de Processo de Progressão Funcional'
                mensagem = f"""<h1>Remoção de Processo de Progressão Funcional</h1>
                <p>Você foi <strong>removido</strong> do Processo de Progressão Funcional do Servidor {avaliado.pessoa_fisica.nome}, no
                    qual havia sido selecionado como avaliador.</p>"""
                send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [avaliacao_removida.avaliador])
            # remove a avaliação
            avaliacao_removida.delete()

    @transaction.atomic
    def save(self):
        periodo = self.instance
        avaliado = periodo.processo_progressao.avaliado.get_vinculo()

        # chefes
        chefes = 0
        if self.cleaned_data['avaliadores_chefe']:
            avaliadores_chefes = [self.cleaned_data['avaliadores_chefe']]
        else:
            avaliadores_chefes = []
        for servidor in avaliadores_chefes:
            if servidor != avaliado:
                chefes += 1
                #
                if chefes > 1:
                    raise ValidationError('Selecione, no máximo, um chefe imediato.')
                #
                avaliacao = ProcessoProgressaoAvaliacao.objects.filter(
                    periodo=periodo, avaliador=servidor, tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE
                )
                if not avaliacao.exists():
                    #
                    # salva a avaliacao
                    #
                    avaliacao = ProcessoProgressaoAvaliacao()
                    avaliacao.periodo = periodo
                    avaliacao.avaliador = servidor
                    avaliacao.tipo_avaliador = ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE
                    avaliacao.save()

        #
        # remove os avaliadores/avaliações do tipo chefe que estão no banco e não estão no formulário
        #
        avaliacoes = ProcessoProgressaoAvaliacao.objects.filter(periodo=periodo, tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE)
        self.remove_avaliacoes(avaliacoes.exclude(avaliador__in=avaliadores_chefes))

        #
        # membros da equipe
        #
        equipe = 0
        for servidor in self.cleaned_data['avaliadores_equipe']:
            if servidor != avaliado:
                equipe += 1
                avaliacao = ProcessoProgressaoAvaliacao.objects.filter(
                    periodo=periodo, avaliador=servidor, tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_EQUIPE
                )
                if not avaliacao.exists():
                    #
                    # salva a avaliacao
                    #
                    avaliacao = ProcessoProgressaoAvaliacao()
                    avaliacao.periodo = periodo
                    avaliacao.avaliador = servidor
                    avaliacao.tipo_avaliador = ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_EQUIPE
                    avaliacao.save()

        #
        # remove os avaliadores/avaliações do tipo equipe que estão no banco e não estão no formulário
        #
        avaliacoes = ProcessoProgressaoAvaliacao.objects.filter(periodo=periodo, tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_EQUIPE)
        self.remove_avaliacoes(avaliacoes.exclude(avaliador__in=self.cleaned_data['avaliadores_equipe']))

        #
        # remove as avaliacoes do periodo caso de nao tenha sido informado nenhum avaliador (válido) no formulário
        #
        if not chefes and not equipe:
            self.remove_avaliacoes(ProcessoProgressaoAvaliacao.objects.filter(periodo=periodo))

        #
        # se há pelo menos uma avaliacao no banco, adiciona o proprio avaliado como avaliador (auto-avaliacao)
        #
        if ProcessoProgressaoAvaliacao.objects.filter(periodo=periodo).exists():
            #
            # o proprio avaliado
            #
            avaliacao = ProcessoProgressaoAvaliacao.objects.filter(
                periodo=periodo,
                avaliador=periodo.processo_progressao.avaliado.get_vinculo(),
                tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_AUTO,
            )
            if not avaliacao.exists():
                #
                # salva a avaliacao
                #
                avaliacao = ProcessoProgressaoAvaliacao()
                avaliacao.periodo = periodo
                avaliacao.avaliador = periodo.processo_progressao.avaliado.get_vinculo()
                avaliacao.tipo_avaliador = ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_AUTO
                avaliacao.save()
        #
        # recalcula a média do período (é possível que já exista avaliações realizadas mesmo
        # durante a edição (remoção e adição de avaliadores) da lista dos avaliadores
        #
        periodo.calcular_media_periodo()
        #
        super().save()


class EstagioProbatorioPeriodoAvaliadoresForm(ModelFormPlus):
    avaliadores_chefe = ModelChoiceFieldPlus(queryset=Vinculo.objects, required=False, widget=AutocompleteWidget(), label='Chefe')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        self.fields['avaliadores_chefe'].queryset = Vinculo.objects.funcionarios()
        #
        periodo = self.instance
        #
        avaliacao_do_chefe = periodo.processoprogressaoavaliacao_set.filter(tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE)
        if avaliacao_do_chefe.exists():
            self.fields['avaliadores_chefe'].initial = avaliacao_do_chefe[0].avaliador

    class Meta:
        model = ProcessoProgressaoPeriodo
        fields = ('avaliadores_chefe',)

    def remove_avaliacoes(self, avaliacoes):
        for avaliacao_removida in avaliacoes:
            # notifica a remoção
            email_avaliado = avaliacao_removida.periodo.processo_progressao.avaliado.email_notificacao
            email_avaliador = avaliacao_removida.avaliador.email_notificacao
            if email_avaliador and email_avaliador != email_avaliado and avaliacao_removida.numero_liberacoes > 0:
                avaliado = avaliacao_removida.periodo.processo_progressao.avaliado
                send_notification(
                    '[SUAP] Remoção de Processo de Progressão Funcional',
                    f"""<h1>Remoção de Processo de Progressão Funcional</h1>
                          <p>Você foi removido do Processo de Progressão Funcional do Servidor {avaliado.pessoa_fisica.nome}, no
                            qual havia sido selecionado como avaliador.</p>""",
                    settings.DEFAULT_FROM_EMAIL,
                    [avaliacao_removida.avaliador],
                )
            # remove a avaliação
            avaliacao_removida.delete()

    @transaction.atomic
    def save(self):
        periodo = self.instance
        avaliado = periodo.processo_progressao.avaliado.get_vinculo()

        #
        # chefes
        #
        chefes = 0
        if self.cleaned_data['avaliadores_chefe']:
            avaliadores_chefes = [self.cleaned_data['avaliadores_chefe']]
        else:
            avaliadores_chefes = []
        for servidor in avaliadores_chefes:
            if servidor != avaliado:
                chefes += 1
                #
                if chefes > 1:
                    raise ValidationError('Selecione, no máximo, um chefe imediato.')
                #
                avaliacao = ProcessoProgressaoAvaliacao.objects.filter(
                    periodo=periodo, avaliador=servidor, tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE
                )
                if not avaliacao.exists():
                    #
                    # salva a avaliacao
                    #
                    avaliacao = ProcessoProgressaoAvaliacao()
                    avaliacao.periodo = periodo
                    avaliacao.avaliador = servidor
                    avaliacao.tipo_avaliador = ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE
                    avaliacao.save()

        #
        # remove os avaliadores/avaliações do tipo chefe que estão no banco e não estão no formulário
        #
        avaliacoes = ProcessoProgressaoAvaliacao.objects.filter(periodo=periodo, tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE)
        self.remove_avaliacoes(avaliacoes.exclude(avaliador__in=avaliadores_chefes))

        #
        # remove as avaliacoes do periodo caso de nao tenha sido informado nenhum avaliador (válido) no formulário
        #
        if not chefes:
            self.remove_avaliacoes(ProcessoProgressaoAvaliacao.objects.filter(periodo=periodo))

        #
        # recalcula a média do período (é possível que já exista avaliações realizadas mesmo
        # durante a edição (remoção e adição de avaliadores) da lista dos avaliadores
        #
        periodo.calcular_media_periodo()
        #
        super().save()


def AvaliacaoServidorFormFactory(request, avaliacao):  # avaliacao = instância de ProcessoProgressaoAvaliacao
    def usuarioLogadoIsAvaliador(request, avaliacao):
        usuario_logado = request.user
        #
        return usuario_logado.get_vinculo().id == avaliacao.avaliador.id

    def usuarioLogadoIsAvaliado(request, avaliacao):
        usuario_logado = request.user
        #
        if usuario_logado.eh_servidor:
            return usuario_logado.get_relacionamento().id == avaliacao.processo.avaliado.id
        return False

    def usuarioLogadoIsRH(request, avaliacao):
        usuario_logado = request.user
        avaliado = avaliacao.processo.avaliado
        if not avaliado.setor:
            sigla_uo_avaliado = get_sigla_reitoria()
        else:
            sigla_uo_avaliado = avaliado.setor.uo.sigla

        campus_usuario_logado = get_uo(usuario_logado)
        if not campus_usuario_logado:
            return False
        #
        return (usuario_logado.has_perm('progressoes.pode_ver_todos_os_processos')) or (
            usuario_logado.has_perm('progressoes.pode_ver_apenas_processos_do_seu_campus') and sigla_uo_avaliado == campus_usuario_logado.sigla
        )

    def usuarioLogadoIsChefeImediato(request, avaliacao):
        chefes_periodo_ids = []
        for avaliacao_chefe in avaliacao.periodo.processoprogressaoavaliacao_set.filter(
            tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE
        ):
            chefes_periodo_ids.append(avaliacao_chefe.avaliador.id)
        usuario_logado = request.user.get_vinculo()
        #
        return usuario_logado.id in chefes_periodo_ids

    """
        Ciclo de vida de uma avaliação:
            1 - avaliador responde a avaliação (avaliador respondendo)
            2 - avaliado posta seu comentário na avaliação (avaliado comentando)
            3 - rh posta seu comentário na avaliação (rh comentando)
    """

    def avaliador_respondendo(request, avaliacao):
        # 1. processo em trâmite
        # 2. avaliação pendente
        # 3. usuario logado é o avaliador
        return avaliacao.processo.is_em_tramite and avaliacao.is_pendente and usuarioLogadoIsAvaliador(request, avaliacao)

    def avaliado_comentando(request, avaliacao):
        # 1. processo em trâmite
        # 2. avaliação avaliada
        # 3. usuário logado é o avaliado
        # 4. usuário logado não é o avaliador
        return (
            avaliacao.processo.is_em_tramite
            and avaliacao.is_avaliada
            and usuarioLogadoIsAvaliado(request, avaliacao)
            and not usuarioLogadoIsAvaliador(request, avaliacao)
        )

    def rh_comentando(request, avaliacao):
        # 1. processo em trâmite
        # 2. avaliação avaliada
        # 3. usuário logado é do rh
        return avaliacao.processo.is_em_tramite and avaliacao.is_avaliada and usuarioLogadoIsRH(request, avaliacao)

    fields = {}
    fields_names = []

    questoes_notas = avaliacao.obter_itens_avaliados()
    pode_editar_questoes = True
    for questao_nota in questoes_notas:  # questoes_notas = [instancias de AvaliacaoCriterioNota]
        field_name = f'{avaliacao.id}{questao_nota.criterio_avaliado.id}'
        valor_inicial = f'{questao_nota.nota:.1f}' if questao_nota.nota else None  # nota é um float

        NOTAS_CHOICE = []

        nota_minima = questao_nota.criterio_avaliado.nota_minima
        nota_maxima = questao_nota.criterio_avaliado.nota_maxima
        nota_choice = nota_minima
        nota_passo = questao_nota.criterio_avaliado.passo_nota
        if nota_passo <= 0:
            nota_passo = 1.0  # padrão
        while nota_choice < nota_maxima:
            NOTAS_CHOICE.append([f'{nota_choice:.1f}', f'{nota_choice:.1f}'])
            nota_choice += nota_passo
        # adiciona a nota máxima
        NOTAS_CHOICE.append([f'{nota_maxima:.1f}', f'{nota_maxima:.1f}'])

        if avaliador_respondendo(request, avaliacao):
            field = forms.ChoiceField(
                label=f'{questao_nota.criterio_avaliado.descricao_questao}',
                initial=valor_inicial,
                widget=forms.RadioSelect(uncheck=True),
                choices=NOTAS_CHOICE,
            )
        else:
            #
            field = forms.CharField(label=f'{questao_nota.criterio_avaliado.descricao_questao}', initial=valor_inicial, required=False)
            #
            field.widget.attrs = {'readonly': 'readonly'}
            #
            pode_editar_questoes = False

        fields[field_name] = field  # coleciona os fields {'field_name': field, ...}
        fields_names.append(field_name)  # coleciona os nomes dos fields ['field_name', ...]

    pode_editar_comentario_avaliador = True
    comentario_avaliador = avaliacao.comentario_avaliador
    fields['comentario_avaliador'] = forms.CharField(
        widget=forms.Textarea, initial=comentario_avaliador, required=False, label='Considerações/Comentários do Avaliador'
    )
    if not avaliador_respondendo(request, avaliacao):
        fields['comentario_avaliador'].widget.attrs.update({'readonly': 'readonly'})
        pode_editar_comentario_avaliador = False
    fields_names.append('comentario_avaliador')

    pode_editar_comentario_avaliado = True
    comentario_avaliado = avaliacao.comentario_avaliado
    fields['comentario_avaliado'] = forms.CharField(
        widget=forms.Textarea, initial=comentario_avaliado, required=False, label='Considerações/Comentários do Avaliado'
    )
    if not avaliado_comentando(request, avaliacao):
        fields['comentario_avaliado'].widget.attrs.update({'readonly': 'readonly'})
        pode_editar_comentario_avaliado = False
    fields_names.append('comentario_avaliado')

    pode_editar_comentario_rh = True
    comentario_rh = avaliacao.comentario_rh
    fields['comentario_rh'] = forms.CharField(
        widget=forms.Textarea, initial=comentario_rh, required=False, label='Reservado ao Departamento de Recursos Humanos'
    )
    if not rh_comentando(request, avaliacao):
        fields['comentario_rh'].widget.attrs.update({'readonly': 'readonly'})
        pode_editar_comentario_rh = False
    fields_names.append('comentario_rh')

    avaliacao_somente_leitura = (
        not pode_editar_questoes and not pode_editar_comentario_avaliador and not pode_editar_comentario_avaliado and not pode_editar_comentario_rh
    )

    texto_botao_submit = 'Salvar'
    if avaliacao_somente_leitura:
        texto_botao_submit = 'Ok'

    usuario_pode_abrir = (
        usuarioLogadoIsAvaliador(request, avaliacao)
        or usuarioLogadoIsAvaliado(request, avaliacao)
        or usuarioLogadoIsRH(request, avaliacao)
        or usuarioLogadoIsChefeImediato(request, avaliacao)
    )

    def clean(self):
        request = self.request
        avaliacao = self.avaliacao
        questoes_notas = self.questoes_notas
        #
        if avaliador_respondendo(request, avaliacao):
            for questao_nota in questoes_notas:  # questoes_notas = [instancias de AvaliacaoCriterioNota]
                field_name = f'{avaliacao.id}{questao_nota.criterio_avaliado.id}'

                nota = self.cleaned_data.get(field_name)
                nota_min = questao_nota.criterio_avaliado.nota_minima
                nota_max = questao_nota.criterio_avaliado.nota_maxima
                if not nota or float(nota) < nota_min or float(nota) > nota_max:
                    self._errors[field_name] = self.error_class(['Selecione uma nota válida.'])
                    if self.cleaned_data.get(field_name):
                        del self.cleaned_data[field_name]
        return self.cleaned_data

    # usado para manter a ordenação dos campos
    fieldsets = ((None, {'fields': fields_names}),)

    @transaction.atomic
    def save(self):
        request = self.request
        avaliacao = self.avaliacao
        questoes_notas = self.questoes_notas
        #
        if avaliador_respondendo(request, avaliacao):
            avaliacao.data_avaliacao = date.today()
            #
            for questao_nota in questoes_notas:  # questoes_notas = [instancias de AvaliacaoCriterioNota]
                field_name = f'{avaliacao.id}{questao_nota.criterio_avaliado.id}'

                # salvando a nota
                nota = AvaliacaoCriterioNota.objects.filter(avaliacao=avaliacao, criterio_avaliado=questao_nota.criterio_avaliado)

                if nota.exists():
                    nota = nota[0]
                    nota.nota = float(self.cleaned_data[field_name])
                else:
                    nota = AvaliacaoCriterioNota()
                    nota.avaliacao = avaliacao
                    nota.criterio_avaliado = questao_nota.criterio_avaliado
                    nota.nota = float(self.cleaned_data[field_name])
                #
                nota.save()
            #
            avaliacao.total_pontos = avaliacao.obter_total_pontos()
            #
            avaliacao.comentario_avaliador = self.cleaned_data['comentario_avaliador']
            #
            avaliacao.hash_string = avaliacao.obter_hash_string()
            avaliacao.hash_valor = ProcessoProgressaoAvaliacao.obter_hash_valor(avaliacao.hash_string)
            #
            avaliacao.status_avaliacao = ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA
            #
            avaliacao.save()
        #
        if avaliado_comentando(request, avaliacao):
            avaliacao.comentario_avaliado = self.cleaned_data['comentario_avaliado']
            avaliacao.save()
        #
        if rh_comentando(request, avaliacao):
            avaliacao.comentario_rh = self.cleaned_data['comentario_rh']
            avaliacao.save()
        #
        avaliacao.periodo.calcular_media_periodo()

    return type(
        'AvaliacaoServidorForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'fieldsets': fieldsets,
            'METHOD': 'POST',
            'save': save,
            'clean': clean,
            'SUBMIT_LABEL': texto_botao_submit,
            'avaliacao': avaliacao,
            'questoes_notas': questoes_notas,
            'request': request,
            'avaliacao_somente_leitura': avaliacao_somente_leitura,
            'is_rh_comentando': rh_comentando(request, avaliacao),
            'is_avaliador_respondendo': avaliador_respondendo(request, avaliacao),
            'usuario_pode_abrir': usuario_pode_abrir,
            'usuario_eh_avaliador': usuarioLogadoIsAvaliador(request, avaliacao),
            'usuario_eh_avaliado': usuarioLogadoIsAvaliado(request, avaliacao),
        },
    )


class SelecionarProtocoloForm(forms.ModelForm):
    class Meta:
        model = ProcessoProgressao
        fields = ('protocolo',)


class SelecionarProcessoEletronicoForm(forms.ModelForm):
    class Meta:
        model = ProcessoProgressao
        fields = ('processo_eletronico',)


# ----------------------------------------------------------
# ---------------------------------------------------------
# ------- ASSINATURA DAS AVALIAÇÕES ------------------------
# ---------------------------------------------------------
# ----------------------------------------------------------


def chave_secreta_progressoes():
    return settings.SECRET_KEY


class AssinaturaAvaliacaoForm(SuapAssinaturaForm):
    nome_assinante_field_exibir = False
    avaliacao = None

    def __init__(self, *args, **kwargs):
        self.avaliacao = kwargs.pop('avaliacao')
        super().__init__(*args, **kwargs)

    def prepara_fields(self):
        super().prepara_fields()
        assinatura_pendente = self.assinatura_is_vazia()
        if not assinatura_pendente and self.get_data_assinatura():
            self.fields['data_assinatura'] = forms.DateField(
                label='Data da assinatura',
                required=False,
                initial=self.get_data_assinatura(),
                widget=forms.TextInput(attrs={'value': self.get_data_assinatura(), 'readonly': 'readonly', 'class': 'pq'}),
            )

    def get_data_assinatura(self):
        pass  # implementar nas classes filhas

    def init_conteudo(self):
        return f'{self.avaliacao.obter_hash_string()}{self.get_data_assinatura()}'

    def init_chave(self):
        return f'{chave_secreta_progressoes()}{self.get_assinante().id}'

    def get_assinante(self):
        pass  # implementar nas classes filhas e retornar um objeto pessoa física do SUAP

    def senha_assinante_field_exibir(self):
        processo = self.avaliacao.periodo.processo_progressao
        assinante = self.get_assinante()
        usuario_logado = self.get_usuario_logado()
        if not usuario_logado:
            return False
        else:
            return self.assinatura_is_vazia() and usuario_logado.get_vinculo().id == assinante.id and processo.is_em_tramite

    def save(self):
        self.avaliacao.save()


class AssinaturaAvaliadoForm(AssinaturaAvaliacaoForm):
    nome_assinante_field_name = 'avaliado_assinante'
    senha_assinante_field_name = 'avaliado_senha'
    assinatura_field_name = 'avaliado_assinatura'

    def init_assinatura(self):
        return self.avaliacao.assinatura_avaliado

    def get_data_assinatura(self):
        if self.avaliacao.data_assinatura_avaliado:
            return self.avaliacao.data_assinatura_avaliado.strftime('%d/%m/%Y')
        return ''

    def before_gera_assinatura(self):
        #
        # acrescenta a data da assinatura ao conteúdo que será assinado
        self.avaliacao.data_assinatura_avaliado = date.today()
        self.conteudo = f'{self.conteudo}{self.get_data_assinatura()}'

    def get_assinante(self):
        return self.avaliacao.periodo.processo_progressao.avaliado.get_vinculo()

    def after_gera_assinatura(self):
        self.avaliacao.assinatura_avaliado = self.assinatura


class AssinaturaAvaliadorForm(AssinaturaAvaliacaoForm):
    nome_assinante_field_name = 'avaliador_assinante'
    senha_assinante_field_name = 'avaliador_senha'
    assinatura_field_name = 'avaliador_assinatura'

    def init_assinatura(self):
        return self.avaliacao.assinatura_avaliador

    def get_data_assinatura(self):
        if self.avaliacao.data_assinatura_avaliador:
            return self.avaliacao.data_assinatura_avaliador.strftime('%d/%m/%Y')
        return ''

    def before_gera_assinatura(self):
        #
        # acrescenta a data da assinatura ao conteúdo que será assinado
        self.avaliacao.data_assinatura_avaliador = date.today()
        self.conteudo = f'{self.conteudo}{self.get_data_assinatura()}'

    def get_assinante(self):
        assinante = self.avaliacao.avaliador
        return assinante

    def after_gera_assinatura(self):
        self.avaliacao.assinatura_avaliador = self.assinatura


class AssinaturaChefeForm(AssinaturaAvaliacaoForm):
    nome_assinante_field_name = 'chefe_assinante'
    senha_assinante_field_name = 'chefe_senha'
    assinatura_field_name = 'chefe_assinatura'

    def init_assinatura(self):
        return self.avaliacao.assinatura_chefe_imediato

    def get_data_assinatura(self):
        if self.avaliacao.data_assinatura_chefe_imediato:
            return self.avaliacao.data_assinatura_chefe_imediato.strftime('%d/%m/%Y')
        return ''

    def before_gera_assinatura(self):
        #
        # acrescenta a data da assinatura ao conteúdo que será assinado
        self.avaliacao.data_assinatura_chefe_imediato = date.today()
        self.conteudo = f'{self.conteudo}{self.get_data_assinatura()}'

    def chefes_periodo(self):
        chefes = []
        for avaliacao_chefe in self.avaliacao.periodo.processoprogressaoavaliacao_set.filter(
            tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE
        ):
            chefes.append(avaliacao_chefe.avaliador)
        return chefes

    def get_assinante(self):
        chefe = self.avaliacao.chefe_imediato_assinante  # o que já assinou (se for o caso)
        if not chefe:
            chefes_periodo = self.chefes_periodo()
            if len(chefes_periodo) == 1:  # 1 chefe selecionado para o período (situação normal)
                chefe = chefes_periodo[0]
        #
        return chefe

    def after_gera_assinatura(self):
        self.avaliacao.chefe_imediato_assinante = self.get_assinante()
        self.avaliacao.assinatura_chefe_imediato = self.assinatura


class AssinaturaProcessoForm(SuapAssinaturaForm):
    """
    apenas para confirmar a senha
    """

    assinatura_field_exibir = False

    @property
    def assinante(self):
        return self.request.user.get_relacionamento()  # o usuário logado é o assinante


class UltimaProgressaoForm(forms.FormPlus):
    avaliado = forms.CharFieldPlus(label='Avaliado', required=False)
    data_inicio_contagem_manual = forms.DateFieldPlus(label='Data de Início da Contagem Manual', required=True)

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.id:
            self.fields['avaliado'].initial = self.instance.avaliado.pessoa_fisica.nome
            self.fields['avaliado'].widget.attrs['disabled'] = 'disabled'

    def clean_data_inicio_contagem_manual(self):
        data = self.cleaned_data.get('data_inicio_contagem_manual')
        processo = ProcessoProgressao.calcular_servidores_a_progredir(
            salvar_processos=False, data_referencia=data, matricula=self.instance.avaliado.matricula, ignorar_lista_matricula=True
        )
        if not processo:
            raise forms.ValidationError('Data de progressão inválida.')
        return data

    def processar(self, request):
        data = request.get('data_inicio_contagem_manual')
        self.instance.data_inicio_contagem_manual = data
        processo = ProcessoProgressao.calcular_servidores_a_progredir(
            salvar_processos=False, data_referencia=data, matricula=self.instance.avaliado.matricula, ignorar_lista_matricula=True
        )
        self.instance.data_inicio_contagem = processo[0].data_inicio_contagem_progressao
        self.instance.data_fim_contagem = processo[0].data_fim_contagem_progressao
        self.instance.situacao = ServidorAProgredir.SITUACAO_REGULAR
        self.instance.save()


class EscolherFonteAtualizacaoForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        #
        choices = []
        #
        servidor = self.processo.avaliado  # todo processo tem um avaliado
        progressao = servidor.ultima_progressao_merito_finalizada
        pca = servidor.ultima_mudanca_posicionamento_pca
        #
        if progressao:  # nem sempre teremos uma progressão por mérito
            data_conclusao = progressao.data_fim_contagem_progressao
            choices.append((ServidorAProgredir.VIA_PROGRESSAO, f'Progressão por Mérito - {data_conclusao.strftime("%d/%m/%Y")}'))
        if pca:  # nem sempre teremos um PCA
            data_pca = pca.data_inicio_posicionamento_pca
            choices.append((ServidorAProgredir.VIA_PCA, f'Posicionamento na Carreira Administrativa - {data_pca.strftime("%d/%m/%Y")}'))
        #
        self.fields['tipo_calculo'] = forms.ChoiceField(
            label='Escolha o tipo de cálculo de acordo com a data',
            widget=forms.RadioSelect,
            choices=choices,
            required=True,
        )

    def processar(self):
        tipo_calculo = self.cleaned_data.get('tipo_calculo')
        servidor_a_progredir = self.processo
        try:
            with transaction.atomic():
                data_referencia = date.today()
                if servidor_a_progredir.data_inicio_contagem_manual:
                    data_referencia = servidor_a_progredir.data_inicio_contagem_manual
                # verificando a necessidade de criar registro novo
                ProcessoProgressao.calcular_servidores_a_progredir(
                    salvar_processos=True,
                    data_referencia=data_referencia,
                    matricula=servidor_a_progredir.avaliado.matricula,
                    atualizando=True,
                    ignorar_lista_matricula=True,
                    pk_relatorio=servidor_a_progredir.pk,
                    forcar_calculo=tipo_calculo,
                )
        except Exception as ex:
            raise ValidationError(f'Erro ao atualizar o processo de progressão funcional: {ex!s}')
