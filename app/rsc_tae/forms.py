from django.apps import apps as django_apps
from djtools import forms
from django.core.exceptions import ValidationError
from comum.models import Vinculo
from djtools.forms.widgets import AutocompleteWidget
from rsc_tae.enums import AreaCorrecao, MotivoIndeferimento, SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.models import Nivel, ProcessoRSCTae


# Formulário de Configurações do módulo (Configurações > Rsc_tae), descoberto automaticamente por
# comum.forms.ConfiguracaoFormFactory. O NOME de cada campo é a chave gravada em
# comum.Configuracao e o LABEL é a descrição, então renomear um campo aqui equivale a trocar a
# chave — a configuração antiga fica órfã no banco.
class _ConfiguracaoRSCTaeBase(forms.FormPlus):
    """Configurações que existem sempre, independente dos módulos opcionais."""

    data_limite_lembrete = forms.DateFieldPlus(
        label='Data limite do lembrete "Fique atento!"',
        required=False,
        help_text=('Último dia em que o lembrete do RSC-TAE aparece na tela inicial do servidor. Em branco, o lembrete não é exibido para ninguém.'),
    )
    limite_deliberacoes_por_categoria = forms.IntegerField(
        label='Limite de deliberações por categoria da comissão',
        required=False,
        min_value=1,
        help_text=(
            'Máximo de deliberações que cada categoria de membro (CONSUP, DIGPE, CIS-PCCTAE...) registra em '
            'CADA escopo de votação — um escopo por item com divergência e um para a deliberação final. '
            'Em branco, vale 2. O voto de desempate do presidente não consome a cota.'
        ),
    )

    def clean_limite_deliberacoes_por_categoria(self):
        """Recusa o limite que inviabilizaria o quórum de deliberações.

        O teto de votos normais por escopo é a soma, por categoria da comissão ativa, de
        ``min(limite, membros ativos)`` — categoria com menos membros que o limite não chega a
        gastá-lo. Se esse teto for menor que o quórum, nenhum item (nem a deliberação final)
        fecharia. Só é recusado quando os membros bastariam sem o limite: faltando gente, nenhum
        limite resolve, e culpá-lo seria enganoso.

        Returns:
            O limite informado (ou vazio, que significa usar o padrão).

        Raises:
            ValidationError: Se o limite inviabiliza o quórum da comissão ativa.
        """
        from django.db.models import Count

        from rsc_tae.models import MembroComissaoRSCTae
        from rsc_tae.views._helpers import quantidade_deliberacoes_item

        limite = self.cleaned_data.get('limite_deliberacoes_por_categoria')
        if not limite:
            return limite

        membros_por_categoria = list(
            MembroComissaoRSCTae.objects.filter(comissao__ativa=True, ativo=True, categoria__isnull=False)
            .order_by()
            .values('categoria_id')
            .annotate(total=Count('id'))
            .values_list('total', flat=True)
        )
        teto = sum(min(limite, total) for total in membros_por_categoria)
        quorum = quantidade_deliberacoes_item()
        if teto < quorum <= sum(membros_por_categoria):
            raise ValidationError(
                f'Com os membros ativos da comissão, o limite {limite} permite no máximo {teto} deliberações, '
                f'menos que o quórum de {quorum} — nenhuma deliberação fecharia. Aumente o limite ou reduza o quórum por item.'
            )
        return limite


# As chaves de processo eletrônico só existem quando os módulos de Processo/Documento Eletrônico
# estão instalados — usadas pela ação "Criar processo eletrônico". Definidas condicionalmente para
# o módulo funcionar sem o processo_eletronico.
if django_apps.is_installed('processo_eletronico') and django_apps.is_installed('documento_eletronico'):
    from documento_eletronico.models import TipoConferencia, TipoDocumento
    from processo_eletronico.models import TipoProcesso
    from rh.models import Setor

    class ConfiguracaoForm(_ConfiguracaoRSCTaeBase):
        processo_eletronico_tipo_processo = forms.ModelChoiceFieldPlus(
            TipoProcesso.objects,
            label='Tipo de processo (Processo Eletrônico)',
            help_text='Geração do processo eletrônico do RSC-TAE: tipo de processo.',
            required=False,
        )
        processo_eletronico_tipo_documento = forms.ModelChoiceFieldPlus(
            TipoDocumento.objects,
            label='Tipo de documento (Processo Eletrônico)',
            help_text='Geração do processo eletrônico do RSC-TAE: tipo de documento.',
            required=False,
        )
        processo_eletronico_tipo_conferencia = forms.ModelChoiceFieldPlus(
            TipoConferencia.objects,
            label='Tipo de conferência (Processo Eletrônico)',
            help_text='Geração do processo eletrônico do RSC-TAE: tipo de conferência.',
            required=False,
        )
        processo_eletronico_setor = forms.ModelChoiceFieldPlus(
            Setor.objects,
            label='Setor do 1º trâmite (Processo Eletrônico)',
            help_text='Setor de destino do primeiro trâmite. Se vazio, usa o setor de lotação do servidor.',
            required=False,
            widget=AutocompleteWidget(),
        )
else:

    class ConfiguracaoForm(_ConfiguracaoRSCTaeBase):
        """Sem o processo eletrônico, o módulo ainda expõe suas configurações próprias."""


class DocumentoPreliminarUploadForm(forms.FormPlus):
    """Valida apenas o arquivo — a data é preenchida depois, via autosave, no card já com o documento enviado."""

    METHOD = 'POST'

    ROTULOS_ARQUIVO_POR_TIPO = {
        TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO: 'Arquivo do título (diploma/certificado)',
        TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO: 'Arquivo da homologação do estágio probatório',
    }

    arquivo = forms.FileFieldPlus(
        required=True,
        filetypes=['pdf'],
    )

    def __init__(self, *args, tipo=TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].label = self.ROTULOS_ARQUIVO_POR_TIPO[tipo]


class ConcluirPreenchimentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Assinar e concluir preenchimento'
    METHOD = 'POST'

    # Declaração de Conformidade Legal — antes ficava na aba Memorial; agora é assinada aqui.
    declaracao_conformidade = forms.BooleanField(
        label='Declaração de Conformidade Legal',
        help_text=(
            'Declaro que todos os fatos apresentados ocorreram no exercício da carreira; '
            'que nenhuma atividade aqui declarada foi utilizada em requerimentos anteriores; '
            'que toda a documentação anexada é autêntica e comprova integralmente as atividades apresentadas; '
            'e que tenho ciência de que informações falsas implicam responsabilidade administrativa, civil e penal '
            '(Seção 3 do Anexo IV do Decreto RSC-PCCTAE).'
        ),
        required=True,
    )
    # RN05 — cada fato/atividade vinculado a um único critério (sem duplicidade)
    declaracao_rn05 = forms.BooleanField(
        label='Unicidade de critério (RN05)',
        help_text=(
            'Declaro que cada atividade ou fato apresentado está vinculado a um único critério específico, '
            'não sendo o mesmo fato utilizado para comprovação de mais de um item '
            '(Art. 4º, §2º do Decreto RSC-PCCTAE).'
        ),
        required=True,
    )
    # RN08 — atividades ordinárias do cargo não são computadas
    declaracao_rn08 = forms.BooleanField(
        label='Exclusão de atribuições ordinárias (RN08)',
        help_text=(
            'Declaro que nenhuma das atividades apresentadas constitui atribuição ordinária do meu cargo, '
            'conforme vedação do Art. 4º, §1º do Decreto RSC-PCCTAE.'
        ),
        required=True,
    )
    confirmacao = forms.BooleanField(
        label='Confirmação de autenticidade',
        help_text=(
            'Confirmo que todas as informações declaradas são verídicas, que os documentos '
            'anexados são autênticos e que tenho ciência de que informações falsas implicam '
            'responsabilidade administrativa, civil e penal.'
        ),
        required=True,
    )
    senha = forms.PasswordField()


class ConfirmarValidacaoForm(forms.FormPlus):
    """Validação do processo pelo RH — confirma que está tudo conforme e assina."""

    SUBMIT_LABEL = 'Assinar e validar processo'
    METHOD = 'POST'

    confirmacao = forms.BooleanField(
        label='Confirmação',
        help_text='Confirmo que analisei o processo e que ele está em conformidade com os critérios legais.',
        required=True,
    )
    senha = forms.PasswordField()


class SolicitarCorrecaoForm(forms.FormPlus):
    """Solicitação de correção pelo RH — aponta as áreas com problema e descreve cada uma."""

    SUBMIT_LABEL = 'Assinar e solicitar correção'
    METHOD = 'POST'

    # Cada área tem um par (marcador, descrição). O mapa é usado pelo clean e pela view.
    CAMPOS_POR_AREA = {
        AreaCorrecao.DIPLOMA_CERTIFICADO: ('corrigir_diploma', 'descricao_diploma'),
        AreaCorrecao.HOMOLOGACAO_ESTAGIO_PROBATORIO: ('corrigir_homologacao', 'descricao_homologacao'),
        AreaCorrecao.FORMULARIO: ('corrigir_formulario', 'descricao_formulario'),
        AreaCorrecao.MEMORIAL: ('corrigir_memorial', 'descricao_memorial'),
    }

    corrigir_diploma = forms.BooleanField(label='Diploma/certificado', required=False)
    descricao_diploma = forms.CharFieldPlus(
        label='O que corrigir no diploma/certificado',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        max_length=5000,
    )
    corrigir_homologacao = forms.BooleanField(label='Homologação do estágio probatório', required=False)
    descricao_homologacao = forms.CharFieldPlus(
        label='O que corrigir na homologação do estágio probatório',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        max_length=5000,
    )
    corrigir_formulario = forms.BooleanField(label='Formulário de pontuação', required=False)
    descricao_formulario = forms.CharFieldPlus(
        label='O que corrigir no formulário de pontuação',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        max_length=5000,
    )
    corrigir_memorial = forms.BooleanField(label='Memorial descritivo', required=False)
    descricao_memorial = forms.CharFieldPlus(
        label='O que corrigir no memorial descritivo',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        max_length=5000,
    )
    confirmacao = forms.BooleanField(
        label='Confirmação',
        help_text='Confirmo que os apontamentos acima descrevem o que o servidor precisa corrigir.',
        required=True,
    )
    senha = forms.PasswordField()

    def clean(self):
        cleaned = super().clean()

        areas_marcadas = 0
        for campo_bool, campo_desc in self.CAMPOS_POR_AREA.values():
            if cleaned.get(campo_bool):
                areas_marcadas += 1
                if not (cleaned.get(campo_desc) or '').strip():
                    self.add_error(campo_desc, 'Descreva o que precisa ser corrigido nesta área.')

        if areas_marcadas == 0:
            raise ValidationError('Marque ao menos uma área que precisa de correção.')

        return cleaned

    def apontamentos(self):
        """Retorna lista de (area, descricao) para as áreas marcadas. Use após is_valid()."""
        resultado = []
        for area, (campo_bool, campo_desc) in self.CAMPOS_POR_AREA.items():
            if self.cleaned_data.get(campo_bool):
                resultado.append((area, (self.cleaned_data.get(campo_desc) or '').strip()))
        return resultado


class DataExercicioCargoForm(forms.FormPlus):
    """Confirmação/correção da data de exercício no cargo pela comissão, na validação."""

    SUBMIT_LABEL = 'Salvar data de exercício no cargo'
    METHOD = 'POST'

    data_exercicio_cargo = forms.DateFieldPlus(
        label='Data de exercício no cargo',
        required=True,
        help_text='Documentos com período anterior a esta data não devem ser aceitos ou serão ajustados pelos avaliadores.',
    )


class FinalizarAvaliacaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Assinar e confirmar finalização'
    METHOD = 'POST'

    confirmacao = forms.BooleanField(
        label='Confirmação',
        help_text=(
            'Confirmo que realizei a avaliação com critério técnico e imparcialidade, '
            'e que as avaliações registradas refletem fielmente minha análise dos documentos comprobatórios.'
        ),
        required=True,
    )
    senha = forms.PasswordField()


class DefinirAvaliadoresForm(forms.FormPlus):
    avaliadores = forms.MultipleModelChoiceFieldPlus(
        queryset=Vinculo.objects,
        required=False,
        widget=AutocompleteWidget(
            search_fields=Vinculo.SEARCH_FIELDS,
            multiple=True,
            attrs={'extra_style_item': 'width: 80%', 'extra_style_remove_icon': 'float: right; padding-top: 5px; padding-left: 4px'},
        ),
        label='Avaliadores',
    )

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo', None)
        super().__init__(*args, **kwargs)

        from rsc_tae.models import ComissaoRSCTae
        from rsc_tae.views._helpers import _ids_servidores_indisponiveis

        comissao_ativa = ComissaoRSCTae.objects.filter(ativa=True).first()
        if comissao_ativa:
            vinculos_ids = comissao_ativa.membros.values_list('vinculo_id', flat=True)
            qs = Vinculo.objects.filter(id__in=vinculos_ids).select_related('pessoa')
            help_text = f'Exibindo membros da comissão ativa: {comissao_ativa.nome}'
        else:
            qs = Vinculo.objects.funcionarios()
            help_text = ''

        # Exclui membros afastados ou de férias hoje
        ids_indisponiveis = _ids_servidores_indisponiveis()
        if ids_indisponiveis:
            qs = qs.exclude(tipo_relacionamento__model='servidor', id_relacionamento__in=ids_indisponiveis)
            help_text = (help_text + ' — ' if help_text else '') + 'Avaliadores afastados ou de férias foram ocultados.'

        self.fields['avaliadores'].queryset = qs
        if help_text:
            self.fields['avaliadores'].help_text = help_text

    def clean_avaliadores(self):
        avaliadores = self.cleaned_data.get('avaliadores')
        if not avaliadores or not self.processo:
            return avaliadores

        vinculo_dono_id = getattr(self.processo, 'vinculo_id', None)
        if not vinculo_dono_id:
            return avaliadores

        for avaliador in avaliadores:
            if getattr(avaliador, 'id', None) == vinculo_dono_id:
                raise ValidationError('O avaliador não pode ser o próprio dono do processo.')

        return avaliadores


class RemanejamentoAvaliadorForm(forms.FormPlus):
    SUBMIT_LABEL = 'Confirmar remanejamento'
    METHOD = 'POST'

    avaliador_remover = forms.ChoiceField(
        label='Avaliador a remover',
        required=True,
    )
    avaliador_incluir = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects,
        label='Novo avaliador',
        required=True,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )
    motivo = forms.CharFieldPlus(
        label='Motivo do remanejamento',
        required=True,
        widget=forms.Textarea(attrs={'rows': 4}),
        max_length=2000,
        help_text='Descreva o motivo pelo qual o avaliador está sendo substituído. Ficará registrado no histórico.',
    )

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)

        from rsc_tae.models import AvaliadorAuxiliarRSCTae
        from rsc_tae.views._helpers import _ids_servidores_indisponiveis

        # Choices para avaliador_remover: avaliadores atuais do processo
        avaliadores_atuais = list(self.processo.avaliadores.select_related('pessoa').order_by('pessoa__nome'))
        self.fields['avaliador_remover'].choices = [(str(v.id), str(v)) for v in avaliadores_atuais]

        # Candidatos para avaliador_incluir: banco de avaliadores auxiliares ativos e disponíveis
        ids_ja_designados = {v.id for v in avaliadores_atuais}
        ids_ja_designados.add(self.processo.vinculo_id)

        ids_indisponiveis = _ids_servidores_indisponiveis()

        apt_qs = AvaliadorAuxiliarRSCTae.aptos_para_sorteio(excluir_vinculo_ids=list(ids_ja_designados)).select_related(
            'vinculo__pessoa', 'vinculo__setor__uo'
        )
        if ids_indisponiveis:
            apt_qs = apt_qs.exclude(
                vinculo__tipo_relacionamento__model='servidor',
                vinculo__id_relacionamento__in=ids_indisponiveis,
            )

        vinculo_ids = apt_qs.values_list('vinculo_id', flat=True)
        qs = Vinculo.objects.filter(id__in=vinculo_ids).select_related('pessoa', 'setor__uo')

        self.fields['avaliador_incluir'].queryset = qs
        self.fields['avaliador_incluir'].label_from_instance = self._label_avaliador

    @staticmethod
    def _label_avaliador(vinculo):
        try:
            campus = vinculo.setor.uo.sigla if vinculo.setor and vinculo.setor.uo else '?'
        except Exception:
            campus = '?'
        return f'{vinculo.pessoa.nome} — {campus}'

    def clean(self):
        cleaned = super().clean()
        remover_id = cleaned.get('avaliador_remover')
        incluir = cleaned.get('avaliador_incluir')

        if remover_id and incluir and str(incluir.id) == str(remover_id):
            raise ValidationError('O novo avaliador não pode ser o mesmo que está sendo removido.')

        return cleaned


class NivelSelecaoForm(forms.FormPlus):
    """Formulário para o servidor selecionar o nível RSC pretendido (RN01)."""

    SUBMIT_LABEL = 'Confirmar e iniciar processo'
    METHOD = 'POST'

    nivel = forms.ModelChoiceFieldPlus(
        queryset=Nivel.objects.none(),
        label='Nível RSC pretendido',
        required=True,
    )

    def __init__(self, *args, niveis_queryset=None, nivel_inicial=None, **kwargs):
        super().__init__(*args, **kwargs)
        if niveis_queryset is not None:
            self.fields['nivel'].queryset = niveis_queryset.order_by('valor_iq')
            self.fields['nivel'].help_text = (
                'O nível pré-selecionado corresponde à sua titulação registrada no sistema. '
                'Selecione um nível superior apenas se sua titulação ainda não foi atualizada.'
            )
            if not self.is_bound:
                # Usa o nível inicial explícito (maior habilitado); senão cai no maior do queryset
                pre_selecionado = nivel_inicial or niveis_queryset.order_by('-valor_iq').first()
                if pre_selecionado:
                    self.fields['nivel'].initial = pre_selecionado.pk


class AlterarNivelForm(forms.FormPlus):
    """Formulário para o servidor alterar o nível RSC pretendido de um processo em preenchimento/correção.

    Disponível apenas antes da (re)assinatura da conclusão — ao reconcluir, a assinatura e o
    requerimento protocolado são regenerados e passam a cobrir o novo nível.
    """

    SUBMIT_LABEL = 'Confirmar alteração de nível'
    METHOD = 'POST'

    nivel = forms.ModelChoiceFieldPlus(
        queryset=Nivel.objects.none(),
        label='Novo nível RSC pretendido',
        required=True,
    )
    motivo = forms.CharFieldPlus(
        label='Motivo da alteração',
        required=True,
        widget=forms.Textarea(attrs={'rows': 4}),
        max_length=2000,
        help_text='Explique por que o nível está sendo alterado (ex.: apontamento da comissão na validação). Fica registrado na trilha de auditoria.',
    )

    def __init__(self, *args, niveis_queryset=None, nivel_atual=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.nivel_atual = nivel_atual
        if niveis_queryset is not None:
            self.fields['nivel'].queryset = niveis_queryset.order_by('valor_iq')
            self.fields['nivel'].help_text = (
                'Níveis disponíveis para a sua titulação registrada no sistema. '
                'A pontuação e a quantidade mínimas de critérios serão revalidadas para o novo nível ao concluir o preenchimento.'
            )

    def clean_nivel(self):
        nivel = self.cleaned_data['nivel']
        if self.nivel_atual and nivel.pk == self.nivel_atual.pk:
            raise ValidationError('O nível selecionado é o mesmo nível pretendido atual do processo.')
        return nivel


class RecusaAvaliacaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Confirmar recusa'
    METHOD = 'POST'

    motivo = forms.CharFieldPlus(
        label='Motivo da recusa',
        required=True,
        widget=forms.Textarea(attrs={'rows': 5}),
        max_length=2000,
        help_text='Informe o motivo pelo qual não poderá realizar esta avaliação. Ficará registrado para auditoria.',
    )
    confirmacao = forms.BooleanField(
        label='Confirmação',
        help_text='Confirmo que estou recusando esta avaliação e estou ciente de que um substituto será designado automaticamente.',
        required=True,
    )
    senha = forms.PasswordField()


class ImpedimentoAvaliacaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Declarar impedimento'
    METHOD = 'POST'

    motivo = forms.CharFieldPlus(
        label='Motivo do impedimento/suspeição',
        required=True,
        widget=forms.Textarea(attrs={'rows': 5}),
        max_length=2000,
        help_text=(
            'Declare o impedimento ou suspeição conforme a Lei nº 9.784/99 '
            '(ex.: parentesco, interesse direto ou indireto, amizade íntima ou inimizade notória).'
        ),
    )
    confirmacao = forms.BooleanField(
        label='Confirmação',
        help_text='Declaro, sob as penas da lei, que estou impedido(a) ou suspeito(a) de realizar esta avaliação.',
        required=True,
    )
    senha = forms.PasswordField()


class VotoDeliberacaoFinalForm(forms.FormPlus):
    """Voto de um membro da comissão na deliberação final do processo (assinado)."""

    SUBMIT_LABEL = 'Assinar e registrar meu voto'
    METHOD = 'POST'

    resultado = forms.ChoiceField(
        label='Seu voto',
        required=True,
        choices=(
            (str(SituacaoProcesso.DEFERIDO), 'Deferido'),
            (str(SituacaoProcesso.INDEFERIDO), 'Indeferido'),
        ),
        widget=forms.RadioSelect,
    )
    pontuacao_final_crsc = forms.DecimalFieldPlus(
        label='Pontuação final',
        required=False,
        help_text='Vem preenchida com a pontuação final consolidada. Ao deferir sem alterar, esse valor é usado; ao indeferir, conta como 0.',
    )
    motivos_indeferimento = forms.MultipleChoiceField(
        label='Motivos do indeferimento',
        required=False,
        choices=MotivoIndeferimento.get_choices(),
        widget=forms.CheckboxSelectMultiplePlus(disable_mark_all=True),
        help_text='Marque a(s) constatação(ões) que fundamenta(m) o indeferimento — serão exibidas no parecer conclusivo com a redação do Decreto nº 13.048/2026.',
    )
    justificativa = forms.CharFieldPlus(
        label='Justificativa complementar',
        required=False,
        widget=forms.Textarea(attrs={'rows': 6}),
        max_length=10000,
        help_text='Opcional: complementa os motivos marcados no indeferimento (Art. 13, IV).',
    )
    confirmacao = forms.BooleanField(
        label='Confirmação',
        help_text=(
            'Confirmo que este é o meu voto na deliberação final e estou ciente de que o processo '
            'será decidido por maioria simples dos membros da comissão.'
        ),
        required=True,
    )
    senha = forms.PasswordField()

    def clean(self):
        cleaned = super().clean()
        resultado = cleaned.get('resultado')
        motivos = cleaned.get('motivos_indeferimento') or []

        if resultado == str(SituacaoProcesso.INDEFERIDO) and not motivos:
            raise ValidationError('Marque ao menos um motivo do indeferimento — as constatações fundamentam o parecer conclusivo (Art. 13, IV).')
        if resultado == str(SituacaoProcesso.DEFERIDO) and motivos:
            cleaned['motivos_indeferimento'] = []

        return cleaned


class ProcessoRSCTaeAdminForm(forms.ModelFormPlus):
    """Formulário de alteração do processo no admin, com as travas que o modelo não impõe.

    Os campos ``situacao`` e ``avaliadores`` continuam editáveis, mas deixaram de aceitar
    escrita livre: a situação só anda por transições declaradas em ``SituacaoProcesso.TRANSICOES``
    (e o ``save_model`` do admin a grava por ``transicionar()``, para o histórico existir), e o
    M2M de avaliadores não passa de três nem serve para remover alguém — quem remove é o command
    ``remover_avaliador_processo``, que também limpa as avaliações e registra a auditoria.
    """

    MAXIMO_AVALIADORES = ProcessoRSCTae.QUANTIDADE_AVALIADORES

    def clean_avaliador_atual(self):
        avaliador = self.cleaned_data.get('avaliador_atual')
        if not avaliador:
            return avaliador

        processo = self.instance
        vinculo_dono_id = getattr(processo, 'vinculo_id', None)
        if not vinculo_dono_id:
            return avaliador

        if getattr(avaliador, 'id', None) == vinculo_dono_id:
            raise ValidationError('O avaliador atual não pode ser o próprio dono do processo.')

        return avaliador

    def clean_avaliadores(self):
        avaliadores = self.cleaned_data.get('avaliadores')
        if avaliadores is None:
            return avaliadores

        self._recusar_autoavaliacao(avaliadores)
        self._recusar_excesso(avaliadores)
        self._recusar_remocao(avaliadores)
        return avaliadores

    def _recusar_autoavaliacao(self, avaliadores):
        vinculo_dono_id = getattr(self.instance, 'vinculo_id', None)
        if not vinculo_dono_id:
            return
        for av in avaliadores:
            if getattr(av, 'id', None) == vinculo_dono_id:
                raise ValidationError('O avaliador não pode ser o próprio dono do processo.')

    def _recusar_excesso(self, avaliadores):
        if len(avaliadores) > self.MAXIMO_AVALIADORES:
            raise ValidationError(
                f'O processo é avaliado por três avaliadores auxiliares; foram informados {len(avaliadores)}. '
                'Para trocar um avaliador por outro use a tela "Remanejar avaliador".'
            )

    def _recusar_remocao(self, avaliadores):
        """Tirar alguém pelo M2M não desfaz a designação — só a esconde.

        As ``AvaliacaoProcessoRSCTae`` do removido continuam ativas (entram na média e no
        "todos finalizaram") e as ``AvaliacaoAnexoRSCTae`` dele seguem nas divergências que a
        CRSC delibera. Por isso a remoção sai daqui e vai para o command, que fecha os três pontos.
        """
        if not self.instance.pk:
            return
        atuais = {v.id for v in self.instance.avaliadores.all()}
        removidos = atuais - {getattr(av, 'id', None) for av in avaliadores}
        if removidos:
            raise ValidationError(
                'Remover avaliador por este formulário deixaria as avaliações dele ativas no processo. '
                'Use o comando "remover_avaliador_processo" na tela de manutenção do RSC-TAE, que limpa as '
                'avaliações e registra a auditoria da remoção.'
            )

    def clean_situacao(self):
        """Só transições declaradas em ``SituacaoProcesso.TRANSICOES``.

        A situação anterior vem do banco: no momento em que este ``clean_`` roda, ``self.instance``
        ainda não foi tocado pelo ``_post_clean``, mas ler do banco deixa a intenção explícita.
        """
        situacao = self.cleaned_data.get('situacao')
        if situacao is None or not self.instance.pk:
            return situacao

        atual = ProcessoRSCTae.objects.filter(pk=self.instance.pk).values_list('situacao', flat=True).first()
        if atual is None or atual == situacao:
            return situacao

        # Os estados finais são transições VÁLIDAS a partir da CRSC (é por elas que a deliberação
        # finaliza o processo), então `pode_transicionar` sozinho não os barraria — e o formulário
        # viraria um atalho para deferir sem quórum, sem consolidar divergências e sem creditar o
        # banco de pontos, ou para reverter um processo finalizado sem estornar o banco.
        if atual in SituacaoProcesso.FINAIS:
            raise ValidationError(
                'Este processo está finalizado. Para devolvê-lo à deliberação da CRSC use o comando '
                '"reverter_deliberacao_final" na tela de manutenção, que também estorna o banco de pontos.'
            )
        if situacao in SituacaoProcesso.FINAIS:
            raise ValidationError(
                'Deferimento e indeferimento são registrados pela deliberação da CRSC, que exige quórum, '
                'consolida as divergências e credita o banco de pontos. Não é possível finalizar o processo por aqui.'
            )

        if not SituacaoProcesso.pode_transicionar(atual, situacao):
            labels = dict(SituacaoProcesso.get_choices())
            raise ValidationError(f'{labels.get(atual, atual)} → {labels.get(situacao, situacao)} não é uma transição válida para este processo.')
        return situacao

    class Meta:
        model = ProcessoRSCTae
        fields = '__all__'


class DeliberacaoItemCRSCForm(forms.FormPlus):
    """Voto de um membro da comissão sobre um item/anexo com divergência."""

    SUBMIT_LABEL = 'Registrar meu voto'
    METHOD = 'POST'

    decisao = forms.ChoiceField(
        label='Seu voto',
        required=True,
        choices=(
            ('2', 'Deferir'),
            ('3', 'Indeferir'),
        ),
        widget=forms.RadioSelect,
    )
    pontuacao_crsc = forms.DecimalFieldPlus(
        label='Unidades reconhecidas',
        required=False,
        help_text='Informe as unidades ao deferir. Ao indeferir, conta como 0.',
    )
    justificativa = forms.CharFieldPlus(
        label='Justificativa',
        required=True,
        widget=forms.Textarea(attrs={'rows': 4}),
        max_length=5000,
    )

    def clean(self):
        cleaned = super().clean()
        decisao = cleaned.get('decisao')
        pontuacao_crsc = cleaned.get('pontuacao_crsc')

        if decisao == '2':  # Deferir
            if pontuacao_crsc is None:
                self.add_error('pontuacao_crsc', 'Informe as unidades reconhecidas ao deferir.')
            elif pontuacao_crsc < 0:
                self.add_error('pontuacao_crsc', 'A pontuação não pode ser negativa.')

        return cleaned
