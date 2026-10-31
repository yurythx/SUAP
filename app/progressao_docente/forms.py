from django.conf import settings
from django.db.models import Sum
from django.forms import ValidationError
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from djtools import forms
from progressao_docente.models import Avaliacao, AvaliacaoItem, DocenteAProgredir, Item, PontuacaoItem, ProgressaoDocente
from rh.models import Servidor, UnidadeOrganizacional

SuapAssinaturaForm = __import__('progressoes.assinatura', fromlist=['SuapAssinaturaForm']).SuapAssinaturaForm


class ConfiguracaoForm(forms.FormPlus):
    if 'processo_eletronico' in settings.INSTALLED_APPS and 'documento_eletronico' in settings.INSTALLED_APPS:
        # vínculo com processo eletrônico
        from django.apps import apps

        #
        TipoProcesso = apps.get_model('processo_eletronico', 'TipoProcesso')
        TipoDocumento = apps.get_model('documento_eletronico', 'TipoDocumento')
        TipoConferencia = apps.get_model('documento_eletronico', 'TipoConferencia')
        #
        pd_tipo_processo = forms.ModelChoiceFieldPlus(
            TipoProcesso.objects,
            label='Tipo de processo (Processo Eletrônico)',
            help_text='Geração de Processo Eletrônico: Tipo de processo',
            required=False,
        )
        pd_tipo_documento = forms.ModelChoiceFieldPlus(
            TipoDocumento.objects,
            label='Tipo de documento (Processo Eletrônico)',
            help_text='Geração de Processo Eletrônico: Tipo de documento',
            required=False,
        )
        pd_tipo_conferencia = forms.ModelChoiceFieldPlus(
            TipoConferencia.objects,
            label='Tipo de conferência (Processo Eletrônico)',
            help_text='Geração de Processo Eletrônico: Tipo de conferência',
            required=False,
        )
        pd_sigla_setor_primeiro_tramite_reitoria = forms.CharFieldPlus(
            label='Sigla do Setor de Primeiro Trâmite - Reitoria',
            help_text='Define a sigla do setor de primeiro trâmite quando processo na reitoria.',
            required=False,
        )
        pd_sigla_setor_primeiro_tramite_campus = forms.CharFieldPlus(
            label='Siglas do Setores de Primeiro Trâmite - Campus',
            help_text='Define as siglas(separados por virgula) do setor de primeiro trâmite quando processo no campus.',
            required=False,
        )
    #
    # configuração que define se os usuários da progressão serão alertados via e-mail e notificação suap
    pd_alertar_a_progredir = forms.BooleanField(label='Alertar Responsáveis de Docentes a Progredir?', initial=True, required=False)
    #
    # configuração para criar a progressão docente apenas pelo relatório
    pd_criar_progressao_apenas_pelo_relatorio = forms.BooleanField(
        label='Criar Progressão Apenas pelo Relatório de Servidores a Progredir?',
        help_text='Se marcado, os processos de progressão docente serão criados apenas através do relatório de servidores a progredir.',
        initial=True,
        required=False,
    )


class ProgressaoDocenteForm(forms.ModelFormPlus):
    _NIVEL_CHOICES = [('', 'Selecione'), *list(ProgressaoDocente.NOVOS_NIVEIS_ENCADEADOS.items())]

    nivel_atual = forms.ChoiceField(
        choices=_NIVEL_CHOICES,
        label='Nível Atual',
        required=False,
    )
    proximo_nivel = forms.ChoiceField(
        choices=_NIVEL_CHOICES,
        label='Próximo Nível',
        required=False,
    )

    nivel_atual_antigo = forms.ChoiceField(
        choices=dict([('', 'Selecione'), *list(ProgressaoDocente.NIVEIS_ENCADEADOS.items())[:-2]]),
        label='Nível Atual Antigo',
        required=False,
    )
    proximo_nivel_antigo = forms.ChoiceField(
        choices=dict([('', 'Selecione'), *list(ProgressaoDocente.NIVEIS_ENCADEADOS.items())[:-1]]),
        label='Próximo Nível Antigo',
        required=False,
    )
    relatorio_a_progredir = forms.ModelChoiceFieldPlus(DocenteAProgredir.objects, label='Relatório de Docente a Progredir', required=False)
    progressao_principal = forms.ModelChoiceFieldPlus(
        ProgressaoDocente.objects,
        label='Progressão Principal',
        help_text='Selecione a progressão principal caso esta seja uma progressão complementar.',
        required=False,
    )

    class Meta:
        model = ProgressaoDocente
        exclude = ('ids_afastamentos_utilizados', 'pontuacao_final_progressao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliado'].queryset = Servidor.objects.docentes()
        #
        self.fields['tipo'].initial = ProgressaoDocente.TIPO_PROGRESSAO
        self.fields['tipo'].widget = forms.HiddenInput()
        #
        if not self.instance or not self.instance.id:
            self.fields['data_fim_periodo'].widget = forms.HiddenInput()
        #
        if self.instance and self.instance.pk:
            #
            self.fields['progressao_principal'].queryset = ProgressaoDocente.objects.filter(
                avaliado__matricula=self.instance.avaliado.matricula
            ).exclude(pk=self.instance.pk)
            #
            self.fields['nivel_atual_antigo'].initial = self.instance.nivel_atual
            self.fields['proximo_nivel_antigo'].initial = self.instance.proximo_nivel
            #
            self.fields['nivel_atual'].initial = self.instance.nivel_atual
            self.fields['proximo_nivel'].initial = self.instance.proximo_nivel

    def clean(self):
        cleaned_data = super().clean()
        nivel_atual = cleaned_data.get('nivel_atual')
        proximo_nivel = cleaned_data.get('proximo_nivel')
        nivel_atual_antigo = cleaned_data.get('nivel_atual_antigo')
        proximo_nivel_antigo = cleaned_data.get('proximo_nivel_antigo')
        #
        if nivel_atual and nivel_atual_antigo:
            raise ValidationError("Os campos 'Nível Atual' e 'Nível Atual Antigo' não podem ser preenchidos ao mesmo tempo.")
        if proximo_nivel and proximo_nivel_antigo:
            raise ValidationError("Os campos 'Próximo Nível' e 'Próximo Nível Antigo' não podem ser preenchidos ao mesmo tempo.")
        #
        # verificando padrão atual
        if nivel_atual or proximo_nivel:
            if not nivel_atual or not proximo_nivel:
                raise ValidationError("Os campos 'Nível Atual' e 'Próximo Nível' são obrigatórios.")
            # Verifica se o nível atual e o próximo nível são iguais
            if nivel_atual == proximo_nivel:
                raise ValidationError('O nível atual não pode ser igual ao próximo nível.')
        #
        if nivel_atual_antigo or proximo_nivel_antigo:
            if not nivel_atual_antigo or not proximo_nivel_antigo:
                raise ValidationError("Os campos 'Nível Atual Antigo' e 'Próximo Nível Antigo' são obrigatórios.")
            # Verifica se o nível atual e o próximo nível são iguais
            if nivel_atual_antigo == proximo_nivel_antigo:
                raise ValidationError('O nível atual não pode ser igual ao próximo nível.')
        #
        # copiando as informações do nivel antigo para os novos
        if nivel_atual_antigo and proximo_nivel_antigo:
            cleaned_data['nivel_atual'] = nivel_atual_antigo
            cleaned_data['proximo_nivel'] = proximo_nivel_antigo
        #
        # se selecionar uma progressão principal, devemos marcar como progressão complementar
        if cleaned_data.get('progressao_principal'):
            cleaned_data['progressao_complementar'] = True
        return cleaned_data


class AvaliacaoForm(forms.ModelFormPlus):
    class Meta:
        model = Avaliacao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        avaliacao = self.instance
        user = self.request.user
        # na edição, devemos esconder alguns campos
        if avaliacao and avaliacao.progressao and avaliacao.progressao.situacao is not ProgressaoDocente.A_INICIAR and not user.is_superuser:
            self.fields['formulario'].widget = forms.HiddenInput()
        # removendo o avaliado com opção de avaliadores do processo
        if self.request and self.request.GET.get('p'):  # parâmetro passado com o id o processo de progressão
            try:
                progressao = ProgressaoDocente.objects.get(pk=self.request.GET.get('p'))
            except ProgressaoDocente.DoesNotExist:
                raise ProgressaoDocente.DoesNotExist('Parâmetro inválido.')
            self.fields['avaliadores'].queryset = Servidor.objects.ativos().exclude(matricula=progressao.avaliado.matricula)

    def clean(self):
        errors = []
        data = self.cleaned_data
        avaliacao = self.instance
        #
        if not avaliacao:
            raise ValidationError('Não foi possível recuperar a avaliação. Tente novamente.')
        # pode editar avaliador?
        pode_editar_avaliador = True
        if avaliacao and avaliacao.situacao == Avaliacao.EM_AVALIACAO:
            # existem avaliacoes realizadas?
            avaliador = avaliacao.avaliadores.first().get_vinculo()
            qtd_avaliado = avaliacao.percentual_avaliado(avaliador).get('qtd')
            if qtd_avaliado > 0:
                erros_msg = 'Existe avaliação deste avaliador no processo.'
                pode_editar_avaliador = False
        #
        if avaliacao.situacao == Avaliacao.CONCLUIDA:
            erros_msg = 'Avaliação concluída.'
            pode_editar_avaliador = False
        #
        if not pode_editar_avaliador and avaliacao.avaliadores.first().get_vinculo() != self.cleaned_data.get('avaliadores').first().get_vinculo():
            errors.append(ValidationError(f'Não é possível editar o avaliador: Erro > {erros_msg}'))
        #
        # processo de progressão
        progressao = data.get('progressao')
        if not progressao:
            raise ValidationError('Não foi possível recuperar o processo de progressão. Tente novamente.')
        #
        # limitando avaliadores para apenas um por avaliação
        avaliadores = data.get('avaliadores')
        if not avaliadores:
            errors.append(ValidationError('Adicione um avaliador no processo.'))
        elif len(avaliadores) > 1:
            errors.append(ValidationError('A quantidade de avaliadores está bloqueada para apenas 1 (um) avaliador por avaliação.'))
        #
        # não permitir que o avaliado seja adiciona como avaliador
        if avaliadores:
            for avaliador in avaliadores:
                if progressao.avaliado == avaliador:
                    errors.append(ValidationError('Não é permitido adicionar o próprio avaliado como um avaliador.'))
                    break

        #
        qs_avaliacoes = progressao.avaliacao_set
        if self.instance and self.instance.id:
            qs_avaliacoes = qs_avaliacoes.exclude(id=self.instance.id)
        periodos_avaliacoes = qs_avaliacoes.values('periodo_inicio', 'periodo_fim', 'formulario__nome')
        #
        # período de início não pode ser menor que data de início da avaliação
        periodo_inicio = data.get('periodo_inicio')
        if not periodo_inicio:
            raise ValidationError('Preencha o período de início.')
        if periodo_inicio < progressao.data_inicio_periodo:
            errors.append(
                ValidationError(
                    _('A data de início do período não pode ser menor que a data de início do período de avaliação. Valor: %(value)s'),
                    params={'value': periodo_inicio},
                )
            )
        #
        # período de fim não pode ser maior que data de fim da avaliação
        periodo_fim = data.get('periodo_fim')
        if not periodo_fim:
            raise ValidationError('Preencha o período de fim.')
        if periodo_fim > progressao.data_fim_periodo:
            errors.append(
                ValidationError(
                    _('A data de fim do período não pode ser maior que a data de fim do período de avaliação. Valor: %(value)s'),
                    params={'value': periodo_fim},
                )
            )
        #
        # verificando se o período da nova avaliação conflita com período de avaliações já cadastradas
        novo_periodo = {'periodo_inicio': periodo_inicio, 'periodo_fim': periodo_fim}
        check_conflito = self._verificar_conflito_periodo(novo_periodo, periodos_avaliacoes)
        if check_conflito:
            errors.append(
                ValidationError(
                    _('O período %(value)s está conflitando com o período cadastrado para o formulário %(formulario_conflito)s'),
                    params={'value': f'{periodo_inicio} à {periodo_fim}', 'formulario_conflito': check_conflito},
                )
            )
        #
        if errors:
            raise ValidationError(errors)
        #
        return data

    """
    VERIFICAÇÕES DE CONFLITO

    Conflito total: quando o novo período está completamente contido em um período existente ou quando um período existente está completamente contido no novo período.
    Conflito parcial: quando a data de início ou a data de fim do novo período está dentro do intervalo existente.
    Conflito de interseção: quando há uma sobreposição entre o novo período e um período existente, com datas de início e fim em ambos os intervalos.
    """

    def _verificar_conflito_periodo(self, novo_periodo, lista_periodos):
        for periodo in lista_periodos:
            inicio_existente = periodo.get('periodo_inicio')
            fim_existente = periodo.get('periodo_fim')
            #
            if (
                inicio_existente <= novo_periodo.get('periodo_inicio') <= fim_existente
                or inicio_existente <= novo_periodo.get('periodo_fim') <= fim_existente
            ):
                return periodo.get('formulario__nome')
            #
            if novo_periodo.get('periodo_inicio') <= fim_existente and novo_periodo.get('periodo_fim') >= inicio_existente:
                return periodo.get('formulario__nome')
            #
            if novo_periodo.get('periodo_inicio') <= inicio_existente and novo_periodo.get('periodo_fim') >= fim_existente:
                return periodo.get('formulario__nome')
        return None


class AdicionarPontuacaoForm(forms.ModelForm):
    item = forms.ModelChoiceField(Item.objects, label='Item', help_text='Selecione um item')
    pontuacao = forms.ChainedModelChoiceField(
        PontuacaoItem.objects,
        label='Pontuação:',
        empty_label='Selecione a Pontuação',
        initial='Todos',
        required=True,
        obj_label='descricao',
        form_filters=[('item', 'item__id')],
    )

    fieldsets = (
        (
            None,
            {
                'fields': (
                    ('avaliacao',),
                    ('item',),
                    ('pontuacao',),
                    ('arquivo',),
                    ('responsavel',),
                )
            },
        ),
    )

    class Meta:
        model = AvaliacaoItem
        exclude = ()

    class Media:
        js = ['/static/progressao_docente/js/AdicionarPontuacao.js']

    def __init__(self, *args, **kwargs):
        avaliacao = kwargs.pop('avaliacao', None)
        criterio = kwargs.pop('criterio', None)
        responsavel = kwargs.pop('responsavel', None)
        super().__init__(*args, **kwargs)

        if avaliacao and avaliacao.situacao == Avaliacao.REAVALIACAO:
            html_msg = """
                        <p class="alert alert-warning">
                            <strong>Atenção</strong>: A alteração das informações irá acarretar na exclusão da avaliação realizada pelo avaliador, SENDO NECESSÁRIO UMA NOVA AVALIAÇÃO.
                        </p>
                        """
            self.EXTRA_INFO = html_msg

        self.fields['avaliacao'].initial = avaliacao.pk
        self.fields['avaliacao'].widget = forms.HiddenInput()

        self.fields['responsavel'].initial = responsavel.pk
        self.fields['responsavel'].widget = forms.HiddenInput()
        #
        if criterio:
            qs_itens = Item.objects.filter(criterio=criterio)
            # # verificando se existe itens com inseção única e aplicando a regra
            ids_insercao_unica = []
            for i in qs_itens:
                if i.insercao_unica:
                    # verificando se já foi inserido algum item
                    if AvaliacaoItem.objects.filter(avaliacao=avaliacao, item=i).exists():
                        ids_insercao_unica.append(i.pk)
            if ids_insercao_unica:
                qs_itens = qs_itens.exclude(pk__in=ids_insercao_unica)

            self.fields['item'].queryset = qs_itens
        #
        self.fields['pontuacao'].disabled = ''
        self.fields['arquivo'].required = True

    def clean(self):
        errors = []
        data = self.cleaned_data
        #
        # validando limite dos itens
        item = data.get('item')
        avaliacao = data.get('avaliacao')
        pontuacao = data.get('pontuacao')

        if not item or not pontuacao:
            raise ValidationError('Os campos obrigatórios devem ser preenchidos.')
        #
        qs = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item=item, pontuacao=pontuacao)
        if qs.exists() and pontuacao.limite_pontos:
            valor = qs.aggregate(p=Sum(pontuacao.pontos)).get('p')  # total de pontos que já existe cadastrado para o item em questão
            limite = pontuacao.limite_pontos
            if valor >= limite:
                # atingiu o limite
                msg = f"O item '{item.nome}' atingiu o limite de pontos, que é de {limite} pontos por critério de avaliação."
                errors.append(ValidationError(msg))
        #
        if item.insercao_unica:
            # verificando se já foi inserido algum item
            if AvaliacaoItem.objects.filter(avaliacao=avaliacao, item=item).exists():
                errors.append(
                    ValidationError('O item selecionado já foi adicionado no processo. Este item não permite ser adicionado mais de uma vez.')
                )
        #
        if errors:
            raise ValidationError(errors)
        #
        return data

    def save(self, commit=True):
        has_changed = False
        if self.instance and self.instance.pk:
            # Pega o objeto atual se ele existir
            old_object = AvaliacaoItem.objects.get(pk=self.instance.pk)

            # Salva o estado atual dos campos
            old_values = {
                'item': old_object.item,
                'pontuacao': old_object.pontuacao,
                'arquivo_name': old_object.arquivo.name if old_object.arquivo else None,
                'arquivo_size': old_object.arquivo.size if old_object.arquivo else None,
            }

            for field in self.cleaned_data:
                if field == 'arquivo':
                    new_file = self.cleaned_data.get('arquivo', None)
                    if new_file:
                        new_file_name = new_file.name or None
                        new_file_size = new_file.size or None
                    if old_values['arquivo_name'] != new_file_name or old_values['arquivo_size'] != new_file_size:
                        has_changed = True
                        break
                else:
                    new_value = self.cleaned_data.get(field, None)
                    _d = old_values.get(field)
                    if _d and _d != new_value:
                        has_changed = True
                        break
        #
        # Chama o método save() do formulário original
        instance = super().save(commit=commit)
        if commit:
            #
            # se houve alteração do objeto, devemos excluir das validações realizadas pelo avaliador
            if has_changed:
                instance.pontuacao_validada = None
                instance.deferimento = None
                instance.justificativa = None
                instance.responsavel_avaliacao = None
            #
            instance.save()

        return instance


class NotasForm(forms.FormPlus):
    #
    NOTAS_CHOICES = (
        (1.0, '1.0'),
        (2.0, '2.0'),
        (3.0, '3.0'),
        (4.0, '4.0'),
        (5.0, '5.0'),
        (6.0, '6.0'),
        (7.0, '7.0'),
        (8.0, '8.0'),
        (9.0, '9.0'),
        (10.0, '10.0'),
    )
    OPCAO_NAO_SE_APLICA = ((0.0, 'Não se aplica'),)
    #
    # fields
    nota = forms.ChoiceField(choices=NOTAS_CHOICES, required=True, widget=forms.RadioSelect())

    class Media:
        js = ('/static/progressao_docente/js/ProgressaoDocente.js',)

    @staticmethod
    def factory_field_render_nota(item, avaliacao, avaliador, avaliado_processo):
        form = NotasForm()
        nota = 0
        id_item = 0
        if isinstance(item, dict):
            id_item = item.get('id')
        else:
            id_item = item.id
        #
        item = Item.objects.get(pk=id_item)
        #
        # checa se o item tem um limite de pontuação e aplica o limite nas pontuações
        itens_limitados = item.get_range_valores(avaliacao, True)
        if itens_limitados:
            NOVO_NOTA_CHOICES = ()
            for i in itens_limitados:
                valor = f'{i:.1f}'
                NOVO_NOTA_CHOICES += ((float(valor), str(valor)),)
            # verificando NÃO SEM APLICA
            if item.permitir_opcao_nao_se_aplica:
                NOVO_NOTA_CHOICES = NOVO_NOTA_CHOICES + NotasForm.OPCAO_NAO_SE_APLICA
            form.fields['nota'].choices = NOVO_NOTA_CHOICES

        obj = None
        try:
            # verificando se existe uma avaliação item
            if item.criterio and item.criterio.autoavaliacao:
                obj = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item=item, responsavel=avaliado_processo).first()
                # verificando se é avaliação discente e se o avaliador é um aluno
                eh_aluno = avaliador.eh_aluno()
                if item.criterio.avaliacao_discente and eh_aluno:
                    obj = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item=item, responsavel=avaliador).first()
            else:
                obj = AvaliacaoItem.objects.filter(avaliacao=avaliacao, item=item, responsavel=avaliador).first()
                if item.criterio.necessita_arquivos:
                    obj = AvaliacaoItem.objects.filter(
                        avaliacao=avaliacao, item=item, responsavel=avaliado_processo, responsavel_avaliacao=avaliador
                    ).first()
            # obj = AvaliacaoItem.objects.get(item__id=id_item, avaliacao=avaliacao, responsavel=avaliador)
            nota = obj.pontuacao_form
        except Exception:
            pass
        field_nota_name = f'nota_{id_item}'
        if avaliador.eh_aluno():
            field_nota_onclick = 'javascript:;'
        else:
            field_nota_onclick = "save_item(this, '/progressao_docente/avaliacaoitem/');"
        field_nota = form.fields['nota'].widget.render(
            field_nota_name,
            nota,
            {
                'id': f'id_nota_{id_item}',
                'onclick': field_nota_onclick,
                'suap_id_item': id_item,
                'suap_id_avaliacao': avaliacao.id,
            },
        )
        return mark_safe(f'{field_nota}')


class EditarDataBaseProgressaoDocente(forms.ModelFormPlus):
    class Meta:
        model = Servidor
        fields = ('data_base_progressao',)

    data_base_progressao = forms.DateFieldPlus(label='Data Base da Progressão Docente', required=True)


class DataBaseProgressaoDocenteFiltroForm(forms.Form):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), label='Campus', required=False)
    nome = forms.CharFieldPlus(label='Nome/Matrícula', required=False)

    def __init__(self, *args, **kwargs):
        eh_campus = kwargs.pop('eh_campus', None)
        super().__init__(*args, **kwargs)
        if eh_campus:
            self.fields['campus'].widget = forms.HiddenInput()

    fieldsets = (('Filtro', {'fields': (('nome'), ('campus'))}),)


class AceleracaoProgressaoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Submeter'
    METHOD = 'POST'
    tipo_aceleracao = forms.ChoiceField(label='Tipo de Aceleração', required=True, choices=ProgressaoDocente.ACELERACAO_CHOICES)
    arquivo_aceleracao = forms.FileFieldPlus(label='Arquivo Aceleração', required=False, filetypes=['pdf', 'jpeg', 'jpg', 'png'])

    class Meta:
        model = ProgressaoDocente
        fields = (
            'tipo_aceleracao',
            'arquivo_aceleracao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_aceleracao'].choices = [(None, '--selecione--'), *list(ProgressaoDocente.ACELERACAO_CHOICES)]

    def clean(self):
        dados = self.cleaned_data
        if int(dados.get('tipo_aceleracao')) in [ProgressaoDocente.ESPECIALIZACAO, ProgressaoDocente.MESTRADO_DOUTORADO] and not dados.get(
            'arquivo_aceleracao'
        ):
            raise ValidationError(message='É necessário anexar o arquivo que comprova a escolha da aceleração escolhida.')
        return dados


class ReavaliacaoObservacaoForm(forms.Form):
    observacao = forms.CharFieldPlus(
        label='Observações',
        required=True,
        widget=forms.Textarea(),
        max_length=5000,
    )


class ConcluirReavaliacaoForm(forms.Form):
    texto_conclusao_reavaliacao = forms.CharFieldPlus(
        label='Observações de Conclusão da Reavaliação',
        required=True,
        widget=forms.Textarea(),
        max_length=5000,
    )


class AssinaturaAvaliadorForm(SuapAssinaturaForm):
    assinatura_field_exibir = False


class DocenteAProgredirForm(forms.ModelFormPlus):
    nivel_atual = forms.ChoiceField(choices=ProgressaoDocente.NOVOS_NIVEIS_ENCADEADOS.items(), label='Nível Atual', required=True)
    proximo_nivel = forms.ChoiceField(choices=ProgressaoDocente.NOVOS_NIVEIS_ENCADEADOS.items(), label='Próximo Nível', required=True)

    class Meta:
        model = DocenteAProgredir
        exclude = ()


class InconsistenciasRelatorioFiltroForm(forms.Form):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), label='Campus', required=False)
    nome = forms.CharFieldPlus(label='Nome/Matrícula', required=False)

    def __init__(self, *args, **kwargs):
        eh_campus = kwargs.pop('eh_campus', None)
        super().__init__(*args, **kwargs)
        if eh_campus:
            self.fields['campus'].widget = forms.HiddenInput()

    fieldsets = (('Filtro', {'fields': (('nome'), ('campus'))}),)
