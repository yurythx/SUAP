# Imports padrão
import re
from itertools import combinations

# Imports de terceiros
import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Count
from django.forms import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

# Imports internos
from comum.models import Pais, TipoArquivo, Vinculo
from comum.utils import get_uo
from djtools import forms
from djtools.forms import ReCaptchaField
from djtools.forms.fields import BrCpfField
from djtools.templatetags.filters import format_
from djtools.utils import getattr_coalesce
from eventos.enums import (
    EtapaPeriodoSubmissao,
    FormaParticipacaoEvento,
    Nacionalidade,
    ResultadoAvaliacao,
    SituacaoConvite,
    SituacaoSubmissao,
    TipoLimitePorTexto,
    TipoPergunta,
    TipoQuestionario,
    TipoSubmissao,
)
from eventos.models import (
    AnexoEvento,
    AreaTematica,
    AtendimentoPublico,
    AtividadeEvento,
    AutorSubmissao,
    AvaliacaoSubmissao,
    AvaliadorModalidade,
    Banner,
    ClassificacaoEvento,
    Configuracao,
    CriterioAvaliacao,
    Dimensao,
    Espacialidade,
    Evento,
    FluxoSubmissao,
    FotoEvento,
    HistoricoEvento,
    Internacionalizacao,
    Modalidade,
    OpcaoResposta,
    Participante,
    Pergunta,
    PorteEvento,
    PublicoAlvoEvento,
    RespostaParticipante,
    Submissao,
    SubtipoEvento,
    TipoAtividade,
    TipoEvento,
    TipoModalidade,
    TipoParticipacao,
    TipoParticipante,
    VersaoSubmissao,
    VideoEvento,
)
from eventos.utils import Notificar
from rh.models import Setor, UnidadeOrganizacional


class CustomRenderableSelectMultiple(forms.RenderableSelectMultiple):
    def __init__(self, attrs=None, participante=None):
        self.participante = participante
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs['participante'] = self.participante
        return super().render(name, value, attrs=attrs, renderer=renderer)


class PerfilParticipanteForm(forms.ModelFormPlus):
    atividades = forms.MultipleModelChoiceField(
        AtividadeEvento.objects,
        label=_('Atividades'),
        widget=CustomRenderableSelectMultiple('widgets/atividades_disponiveis_widget.html'),
        required=False,
    )

    class Meta:
        model = Participante
        fields = ('nome', 'cpf', 'email', 'telefone', 'foto', 'curriculo', 'atividades')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipo = getattr_coalesce(self, 'instance.tipo', None)
        atividades = getattr_coalesce(self, 'instance.evento.atividadeevento_set', None)
        if not tipo or not tipo.eh_convidado():
            del self.fields['foto']
            del self.fields['curriculo']
        if self.instance.nacionalidade in (Nacionalidade.ESTRANGEIRO, str(Nacionalidade.ESTRANGEIRO)):
            del self.fields['cpf']
        if atividades and atividades.exists():
            self.fields['atividades'].queryset = atividades.all()
            self.fields['atividades'].widget.participante = self.instance
        else:
            del self.fields['atividades']

    def clean_atividades(self):
        atividades = self.cleaned_data.get('atividades')
        for atividade in atividades:
            qtd_disponiveis = atividade.get_qtd_vagas_disponiveis()
            # Se não há limite de vagas (None) ou há vagas disponíveis, tudo ok
            if qtd_disponiveis is None or qtd_disponiveis > 0:
                continue
            # Se não há vagas, verificar se o participante atual já está inscrito nesta atividade
            if hasattr(self, 'instance') and self.instance.pk:
                esta_inscrito = self.instance.atividades.filter(pk=atividade.pk).exists()
                if esta_inscrito:
                    # Participante já está inscrito, pode manter a inscrição
                    continue
            # Só gera erro se não tem vagas E o participante não está inscrito
            raise forms.ValidationError(f'Todas as vagas já foram preenchidas para atividade: {atividade}.')
        return atividades

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if self.instance.nacionalidade not in (Nacionalidade.ESTRANGEIRO, str(Nacionalidade.ESTRANGEIRO)):
            if Participante.objects.filter(cpf=cpf, tipo=self.instance.tipo, evento=self.instance.evento).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('CPF já cadastrado para este evento, neste tipo de participação.')
        return cpf

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if (
            Participante.objects.filter(email__iexact=email, tipo=self.instance.tipo, evento=self.instance.evento)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError('E-mail já cadastrado para este evento, neste tipo de participação.')
        return email

    def _post_clean(self) -> None:
        # O vínculo depende do CPF já aplicado na instância (o que o super()._post_clean faz);
        # checado aqui, CPF sem vínculo do perfil vira erro do formulário, não 500 no save().
        super()._post_clean()
        if self.errors or self.instance.nacionalidade in (Nacionalidade.ESTRANGEIRO, str(Nacionalidade.ESTRANGEIRO)):
            return
        try:
            self.instance.checar_vinculo()
        except ValidationError as erro:
            self.add_error('cpf' if 'cpf' in self.fields else None, erro)


class CriterioAvaliacaoInlineFormSet(BaseInlineFormSet):
    def clean(self):
        if any(self.errors):
            return
        ordens_por_etapa = {}
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue

            etapa = form.cleaned_data.get('etapa')
            ordem_desempate = form.cleaned_data.get('ordem_desempate')
            if etapa and ordem_desempate:
                if etapa not in ordens_por_etapa:
                    ordens_por_etapa[etapa] = set()
                if ordem_desempate in ordens_por_etapa[etapa]:
                    temp_instance = CriterioAvaliacao(etapa=etapa)
                    etapa_display = temp_instance.get_etapa_display()
                    raise forms.ValidationError(
                        f'Já existe um critério de avaliação com ordem de desempate igual a {ordem_desempate} na etapa {etapa_display}.'
                    )
                ordens_por_etapa[etapa].add(ordem_desempate)


class CriterioAvaliacaoForm(forms.ModelFormPlus):
    fieldsets = (('Critério de Avaliação', {'fields': ('descricao', ('nota_minima', 'nota_maxima'), 'ordem_desempate', 'etapa')}),)

    class Meta:
        model = CriterioAvaliacao
        fields = ('etapa', 'descricao', 'nota_minima', 'nota_maxima', 'ordem_desempate')

    def __init__(self, *args, **kwargs):
        self.modalidade = kwargs.pop('modalidade', None)
        super().__init__(*args, **kwargs)

    def clean_ordem_desempate(self):
        ordem_desempate = self.cleaned_data.get('ordem_desempate')
        etapa = self.cleaned_data.get('etapa')
        modalidade = self.modalidade or self.instance.modalidade
        if (
            CriterioAvaliacao.objects.filter(modalidade=modalidade, ordem_desempate=ordem_desempate, etapa=etapa)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            # Criar uma instância temporária para usar get_etapa_display()
            temp_instance = CriterioAvaliacao(etapa=etapa)
            etapa_display = temp_instance.get_etapa_display()
            raise forms.ValidationError(
                f'Já existe um critério de avaliação com ordem de desempate igual a {ordem_desempate} na etapa {etapa_display}.'
            )
        return ordem_desempate

    def save(self):
        if self.modalidade:
            self.instance.modalidade = self.modalidade
        super().save()


class VincularAreaTematicaEventoForm(forms.ModelFormPlus):
    areas_tematicas = forms.MultipleModelChoiceFieldPlus(label='Áreas temáticas', queryset=AreaTematica.objects.none())

    class Meta:
        model = Evento
        fields = ('areas_tematicas',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['areas_tematicas'].queryset = AreaTematica.objects.filter(Q(evento=self.instance) | Q(evento__isnull=True), ativa=True).order_by(
            'titulo'
        )


class ConsultaParticipanteForm(forms.FormPlus):
    SUBMIT_LABEL = _('Consultar')
    email = forms.EmailField(label=_('E-mail'), required=False)
    cpf = forms.BrCpfField(label=_('CPF'), help_text=_('Formato: "XXX.XXX.XXX-XX"'), required=False)

    def clean(self):
        cleaned_data = super().clean()
        cpf = self.cleaned_data.get('cpf')
        email = self.cleaned_data.get('email')

        if not (email or cpf):
            raise forms.ValidationError('É necessário informar um email ou cpf para realizar esta consulta.')

        return cleaned_data


class LoginParticipanteForm(forms.FormPlus):
    SUBMIT_LABEL = 'Acessar'
    email = forms.CharField(label='E-mail')
    chave_acesso = forms.CharField(label='Chave de Acesso', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        chave_acesso = self.cleaned_data.get('chave_acesso')
        participante = Participante.objects.filter(evento=self.evento, email=email, chave_acesso=chave_acesso)
        retorno = None
        if participante.exists() and participante.count() == 1:
            retorno = participante.first()
            if retorno.tipo.eh_avaliador_de_trabalho() and not retorno.situacao_convite == SituacaoConvite.ACEITO:
                raise forms.ValidationError(
                    'É necessário aceitar o convite de avaliação antes de efetuar login como avaliador. Entre em contato com a administração do evento.'
                )
        return self.cleaned_data

    def autenticar(self):
        email = self.cleaned_data.get('email')
        chave_acesso = self.cleaned_data.get('chave_acesso')
        return Participante.objects.filter(evento=self.evento, email=email, chave_acesso=chave_acesso).first()


class SubstituirAvaliadorSubmissaoForm(forms.FormPlus):
    avaliador = forms.ModelChoiceFieldPlus(label='Novo avaliador', queryset=Participante.objects, widget=forms.Select, required=True)

    def __init__(self, *args, **kwargs):
        self.avaliacao_submissao = kwargs.pop('avaliacao_submissao')
        self.versao = self.avaliacao_submissao.versao
        self.submissao = self.versao.submissao
        super().__init__(*args, **kwargs)
        pks = [avaliador_modalidade.avaliador.pk for avaliador_modalidade in self.submissao.get_avaliador_modalidade()]
        avaliadores = Participante.objects.filter(
            avaliadormodalidade__modalidade=self.submissao.modalidade, avaliadormodalidade__avaliador__situacao_convite=SituacaoConvite.ACEITO
        ).exclude(pk__in=pks)
        self.fields['avaliador'].queryset = avaliadores

    @transaction.atomic()
    def save(self):
        avaliador = self.cleaned_data.get('avaliador')
        avaliador_modalidade = AvaliadorModalidade.objects.get(avaliador=avaliador, modalidade=self.submissao.modalidade)
        AvaliacaoSubmissao.objects.create(avaliador_modalidade=avaliador_modalidade, versao=self.versao)
        self.avaliacao_submissao.delete()


class VincularAvaliadorSubmissaoForm(forms.FormPlus):
    avaliadores = forms.MultipleModelChoiceFieldPlus(label='Avaliadores', queryset=Participante.objects, required=True)

    def __init__(self, *args, **kwargs):
        self.submissao = kwargs.pop('submissao')
        self.qtd_atual_avaliadores = len(self.submissao.get_avaliador_modalidade())
        super().__init__(*args, **kwargs)
        pks = [avaliador_modalidade.avaliador.pk for avaliador_modalidade in self.submissao.get_avaliador_modalidade()]
        avaliadores = Participante.objects.filter(
            avaliadormodalidade__modalidade=self.submissao.modalidade, avaliadormodalidade__avaliador__situacao_convite=SituacaoConvite.ACEITO
        ).exclude(pk__in=pks)
        self.fields['avaliadores'].queryset = avaliadores
        limite_avaliadores = self.submissao.modalidade.evento.configuracao.limite_avaliadores
        limite_avaliadores = limite_avaliadores - self.qtd_atual_avaliadores
        self.fields['avaliadores'].help_text = f'Limite de avaliadores para esta submissão: {limite_avaliadores}'

    def clean(self):
        cleaned_data = super().clean()
        qtd_form = len(self.cleaned_data.get('avaliadores', []))
        limite_avaliadores = self.submissao.modalidade.evento.configuracao.limite_avaliadores
        if self.qtd_atual_avaliadores + qtd_form > limite_avaliadores:
            self.add_error('avaliadores', f'A quantidade limite de avaliadores para este trabalho é de {limite_avaliadores} avaliadores.')
        versao = self.submissao.versoes.first()
        if versao is None:
            self.add_error('avaliadores', 'Não é possível vincular avaliadores a uma submissão que não possui versão.')
        return cleaned_data

    @transaction.atomic()
    def save(self):
        versao = self.submissao.versoes.first()
        for avaliador in self.cleaned_data.get('avaliadores'):
            avaliador_modalidade = AvaliadorModalidade.objects.get(avaliador=avaliador, modalidade=self.submissao.modalidade)
            AvaliacaoSubmissao.objects.create(avaliador_modalidade=avaliador_modalidade, versao=versao)


class AvaliadorModalidadeForm(forms.ModelFormPlus):
    modalidade = forms.ModelChoiceFieldPlus(label='Modalidade', queryset=Modalidade.objects, widget=forms.Select)
    areas_tematicas = forms.MultipleModelChoiceFieldPlus(
        label='Áreas Temáticas', queryset=AreaTematica.objects.all(), required=True, widget=forms.CheckboxSelectMultiplePlus()
    )

    class Meta:
        model = AvaliadorModalidade
        fields = ('modalidade', 'areas_tematicas')

    class Media:
        js = ['/static/eventos/js/ModalidadeForm.js']

    fieldsets = (('Dados gerais', {'fields': (('modalidade'), ('areas_tematicas'))}),)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        self.avaliador = kwargs.pop('avaliador')
        super().__init__(*args, **kwargs)
        self.fields['modalidade'].queryset = self.evento.modalidade_set.all()
        self.fields['areas_tematicas'].queryset = self.evento.areas_tematicas.all()

    def clean(self):
        cleaned_data = super().clean()
        modalidade = cleaned_data.get('modalidade')
        if modalidade and self.avaliador:
            if AvaliadorModalidade.objects.filter(avaliador=self.avaliador, modalidade=modalidade).exists():
                self.add_error('modalidade', f'O avaliador [{self.avaliador}] selecionado já está vinculado a esta modalidade.')
        return cleaned_data

    def save(self):
        self.instance.avaliador = self.avaliador
        super().save()


class AreaTematicaForm(forms.ModelFormPlus):
    class Meta:
        model = AreaTematica
        fields = ('titulo',)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        super().__init__(*args, **kwargs)
        self.instance.evento = self.evento


class ConfiguracaoEventosForm(forms.ModelFormPlus):
    class Meta:
        model = Configuracao
        fields = (
            'submissao_limite_autores',
            'submissao_limite_trabalhos_pessoa',
            'avaliacao_nota_aprovacao',
            'limite_avaliadores',
            'notificar_resultados_automaticamente',
        )

    fieldsets = (
        (
            'Submissão',
            {'fields': (('submissao_limite_autores', 'submissao_limite_trabalhos_pessoa'))},
        ),
        ('Avaliação', {'fields': (('avaliacao_nota_aprovacao', 'limite_avaliadores'))}),
        ('Notificações', {'fields': ('notificar_resultados_automaticamente',)}),
    )

    def save(self, evento):
        super().save()
        evento.configuracao = self.instance
        evento.save()

    def clean_submissao_limite_autores(self):
        submissao_limite_autores = self.cleaned_data.get('submissao_limite_autores')
        if not submissao_limite_autores >= 0:
            raise forms.ValidationError('A quantidade limite de autores deve ser maior que zero.')
        return submissao_limite_autores

    def clean_submissao_limite_trabalhos_pessoa(self):
        submissao_limite_trabalhos_pessoa = self.cleaned_data.get('submissao_limite_trabalhos_pessoa')
        if not submissao_limite_trabalhos_pessoa >= 0:
            raise forms.ValidationError('A quantidade limite de submissões de trabalhos por pessoa deve ser maior que zero.')
        return submissao_limite_trabalhos_pessoa

    def clean_avaliacao_nota_aprovacao(self):
        avaliacao_nota_aprovacao = self.cleaned_data.get('avaliacao_nota_aprovacao')
        if not (0 <= avaliacao_nota_aprovacao <= 100):
            raise forms.ValidationError('A nota para aprovação deve estar entre 0 e 100.')
        return avaliacao_nota_aprovacao

    def clean_limite_avaliadores(self):
        limite_avaliadores = self.cleaned_data.get('limite_avaliadores')
        if not limite_avaliadores >= 0:
            raise forms.ValidationError('A quantidade limite de avaliadores por trabalho deve ser maior que zero.')
        return limite_avaliadores


class PerguntaForm(forms.ModelFormPlus):
    class Meta:
        model = Pergunta
        fields = ('ordem', 'titulo', 'tipo_pergunta', 'obrigatoria', 'numerico')

    fieldsets = (('Dados gerais', {'fields': (('ordem', 'tipo_pergunta', 'obrigatoria'), 'titulo', 'numerico')}),)

    class Media:
        js = ['/static/eventos/js/PerguntaForm.js']

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        self.tipo_questionario = kwargs.pop('tipo_questionario', None)
        super().__init__(*args, **kwargs)

    def save(self):
        if self.evento:
            self.instance.evento = self.evento
        if self.tipo_questionario:
            self.instance.tipo_questionario = self.tipo_questionario
        return super().save()


class OpcaoRespostaForm(forms.ModelFormPlus):
    class Meta:
        model = OpcaoResposta
        fields = ('ordem', 'texto')

    fieldsets = (('Dados gerais', {'fields': ('ordem', 'texto')}),)

    def __init__(self, *args, **kwargs):
        self.pergunta = kwargs.pop('pergunta', None)
        self.evento = kwargs.pop('evento', None)
        super().__init__(*args, **kwargs)

    def save(self):
        if self.pergunta:
            self.instance.pergunta = self.pergunta
        if self.evento:
            self.instance.evento = self.evento
        return super().save()


class FluxoSubmissaoForm(forms.ModelFormPlus):
    data_fim = forms.DateFieldPlus(
        label='Data final', required=False, help_text='Este campo é obrigatório para todas as etapas, exceto para a etapa "Resultado Final".'
    )

    class Meta:
        model = FluxoSubmissao
        fields = ('etapa', 'data_inicio', 'data_fim')

    fieldsets = (('Dados gerais', {'fields': ('etapa', 'data_inicio', 'data_fim')}),)

    class Media:
        js = ['/static/eventos/js/FluxoSubmissaoForm.js']

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        if not self.evento:
            self.evento = kwargs.get('instance').evento
        super().__init__(*args, **kwargs)

    def save(self):
        if self.evento:
            self.instance.evento = self.evento
        super().save()

    def clean(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        etapa = self.cleaned_data.get('etapa')

        if etapa == EtapaPeriodoSubmissao.RESULTADO_FINAL:
            self.cleaned_data['data_fim'] = None
        elif etapa != EtapaPeriodoSubmissao.RESULTADO_FINAL and not data_fim:
            raise forms.ValidationError('O campo "Data final" é obrigatório para esta etapa.')
        else:
            if data_inicio > data_fim:
                raise forms.ValidationError('A data de início deve ser anterior à data de fim.')

        # Regras de dependência entre etapas do fluxo
        if etapa == EtapaPeriodoSubmissao.AVALIACAO:
            if not FluxoSubmissao.objects.filter(evento=self.evento, etapa=EtapaPeriodoSubmissao.SUBMISSAO).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Só é possível criar a etapa de Avaliação se já houver uma etapa de Submissão cadastrada.')
        elif etapa == EtapaPeriodoSubmissao.CORRECOES:
            if not FluxoSubmissao.objects.filter(evento=self.evento, etapa=EtapaPeriodoSubmissao.AVALIACAO).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Só é possível criar a etapa de Correções se já houver uma etapa de Avaliação cadastrada.')
        elif etapa == EtapaPeriodoSubmissao.REAVALIACAO:
            if not FluxoSubmissao.objects.filter(evento=self.evento, etapa=EtapaPeriodoSubmissao.CORRECOES).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Só é possível criar a etapa de Reavaliação se já houver uma etapa de Correções cadastrada.')

        # Permitir sobreposição entre "Submissão" e "Avaliação", mas garantir ordem correta
        if etapa in [
            EtapaPeriodoSubmissao.SUBMISSAO,
            EtapaPeriodoSubmissao.AVALIACAO,
            EtapaPeriodoSubmissao.CORRECOES,
            EtapaPeriodoSubmissao.REAVALIACAO,
        ]:
            qs = FluxoSubmissao.objects.filter(evento=self.evento).exclude(pk=self.instance.pk)
            etapa_submissao = qs.filter(etapa=EtapaPeriodoSubmissao.SUBMISSAO).first()
            etapa_avaliacao = qs.filter(etapa=EtapaPeriodoSubmissao.AVALIACAO).first()
            etapa_correcoes = qs.filter(etapa=EtapaPeriodoSubmissao.CORRECOES).first()
            # etapa_reavaliacao = qs.filter(etapa=EtapaPeriodoSubmissao.REAVALIACAO).first()

            # Submissão/Avaliação: garantir ordem
            if etapa == EtapaPeriodoSubmissao.AVALIACAO and etapa_submissao:
                fim_submissao = etapa_submissao.data_fim
                if fim_submissao and data_fim and data_fim < fim_submissao:
                    raise forms.ValidationError('A etapa de avaliação não pode terminar antes do término da etapa de submissão.')

            if etapa == EtapaPeriodoSubmissao.SUBMISSAO and etapa_avaliacao:
                fim_avaliacao = etapa_avaliacao.data_fim
                if fim_avaliacao and data_fim and data_fim > fim_avaliacao:
                    raise forms.ValidationError('A etapa de submissão não pode terminar depois do término da etapa de avaliação.')

            # Correções/Reavaliação: garantir ordem
            if etapa == EtapaPeriodoSubmissao.REAVALIACAO and etapa_correcoes:
                fim_correcoes = etapa_correcoes.data_fim
                if fim_correcoes and data_fim and data_fim < fim_correcoes:
                    raise forms.ValidationError('A etapa de reavaliação não pode terminar antes do término da etapa de correções.')

            # if etapa == EtapaPeriodoSubmissao.CORRECOES and etapa_avaliacao:
            #     fim_avaliacao = etapa_avaliacao.data_fim
            #     if fim_avaliacao and data_fim and data_fim > fim_avaliacao:
            #         raise forms.ValidationError('A etapa de correções não pode terminar depois do término da etapa de avaliação.')

        # Não impede sobreposição entre essas duas etapas
        else:
            # Para as demais etapas, impede sobreposição de períodos
            if data_fim:
                conflitos = (
                    FluxoSubmissao.objects.filter(
                        evento=self.evento,
                        data_inicio__lte=data_fim,
                    )
                    .filter(Q(data_fim__isnull=True) | Q(data_fim__gte=data_inicio))
                    .exclude(pk=self.instance.pk)
                )
            else:
                conflitos = (
                    FluxoSubmissao.objects.filter(
                        evento=self.evento,
                        data_inicio__lte=data_inicio,
                    )
                    .filter(Q(data_fim__isnull=True) | Q(data_fim__gte=data_inicio))
                    .exclude(pk=self.instance.pk)
                )
            if conflitos.exists():
                raise forms.ValidationError('Os períodos do fluxo de submissão não podem se sobrepor dentro do mesmo evento.')

        return super().clean()


class ModalidadeForm(forms.ModelFormPlus):
    tipo_arquivos_permitidos = forms.MultipleModelChoiceFieldPlus(
        label='Tipo de arquivos permitidos', queryset=TipoArquivo.objects.all(), required=False
    )

    class Meta:
        model = Modalidade
        fields = (
            'tipo',
            'tipo_submissao',
            'limite_submissoes',
            'regras_submissao',
            'regras_avaliacao',
            'tipo_limite_por_texto',
            'limite_por_texto',
            'tipo_arquivos_permitidos',
            'template',
        )

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'tipo',
                    'limite_submissoes',
                    ('regras_submissao', 'regras_avaliacao', 'template'),
                    'tipo_submissao',
                    ('tipo_limite_por_texto', 'limite_por_texto'),
                    'tipo_arquivos_permitidos',
                )
            },
        ),
    )

    class Media:
        js = ['/static/eventos/js/ModalidadeForm.js']

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        if not self.evento:
            self.evento = kwargs.get('instance').evento
        super().__init__(*args, **kwargs)
        self.fields['tipo'].queryset = TipoModalidade.objects.filter(Q(evento__isnull=True) | Q(evento=self.evento)).order_by('titulo')

    def save(self, evento):
        self.instance.evento = evento
        super().save()

    def clean_limite_submissoes(self):
        limite_submissoes = self.cleaned_data.get('limite_submissoes')
        if not limite_submissoes >= 0:
            raise forms.ValidationError('A quantidade limite de submissões de trabalhos deve ser maior que zero.')
        return limite_submissoes

    def clean_tipo_arquivos_permitidos(self):
        tipo_submissao = self.cleaned_data.get('tipo_submissao')
        tipo_arquivos_permitidos = self.cleaned_data.get('tipo_arquivos_permitidos')
        if tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_ARQUIVO:
            if not tipo_arquivos_permitidos:
                raise forms.ValidationError('É necessário selecionar pelo menos um tipo de arquivo permitido.')
        return tipo_arquivos_permitidos

    def clean_tipo_limite_por_texto(self):
        tipo_submissao = self.cleaned_data.get('tipo_submissao')
        tipo_limite_por_texto = self.cleaned_data.get('tipo_limite_por_texto')
        if tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO:
            if not tipo_limite_por_texto:
                raise forms.ValidationError('É necessário selecionar o tipo de limite por texto (palavras ou caracteres).')
        return tipo_limite_por_texto

    def clean_limite_por_texto(self):
        tipo_submissao = self.cleaned_data.get('tipo_submissao')
        limite_por_texto = self.cleaned_data.get('limite_por_texto')
        if tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO:
            if not limite_por_texto:
                raise forms.ValidationError('É necessário selecionar o de limite de palavras/caracteres nos trabalhos.')
        return limite_por_texto


class FileInputWithAccept(forms.FileInput):
    def __init__(self, attrs=None, accept_exts=None):
        self.accept_exts = accept_exts
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs['accept'] = ','.join(f'.{ext}' for ext in self.accept_exts)
        return super().render(name, value, attrs=attrs, renderer=renderer)


class FiltroSubmissaoForm(forms.FormPlus):
    METHOD = 'GET'
    codigo = forms.CharField(label='ID', required=False)
    modalidade = forms.ModelChoiceFieldPlus(label='Modalidade', queryset=Modalidade.objects, required=False)
    area_tematica = forms.ModelChoiceFieldPlus(label='Área temática', queryset=AreaTematica.objects, required=False)
    situacao = forms.ChoiceField(label='Situação', choices=[('', 'Todas'), *SituacaoSubmissao.choices], required=False)
    resultado_avaliacao = forms.ChoiceField(
        label='Avaliação', choices=[('', 'Todos'), ('SA', 'Sem avaliação'), *ResultadoAvaliacao.choices], required=False
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.evento = kwargs.pop('evento')
        super().__init__(*args, **kwargs)
        self.fields['modalidade'].queryset = self.evento.modalidade_set.all()
        self.fields['area_tematica'].queryset = self.evento.areas_tematicas.all()
        if not self.evento.pode_divulgar_resultado_final():
            self.fields['resultado_avaliacao'].choices = [('', 'Todos'), ('SA', 'Sem avaliação'), (ResultadoAvaliacao.PENDENTE, 'Avaliação pendente')]


class SubmissaoForm(forms.ModelFormPlus):
    class Meta:
        model = Submissao
        fields = ('titulo', 'texto', 'arquivo', 'link_video')

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        self.modalidade = kwargs.pop('modalidade', None)
        self.area_tematica = kwargs.pop('area_tematica', None)
        super().__init__(*args, **kwargs)
        if self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO:
            del self.fields['arquivo']
            del self.fields['link_video']
        else:
            del self.fields['texto']
            self.fields['arquivo'].widget = FileInputWithAccept(accept_exts=self.modalidade.extensoes_permitidas())
            qtd_arquivos_permitidos = self.modalidade.tipo_arquivos_permitidos.count()
            arquivos_de_video = self.modalidade.tipo_arquivos_permitidos.filter(eh_video=True)
            if arquivos_de_video.exists() and qtd_arquivos_permitidos == 1:
                del self.fields['arquivo']
            elif not arquivos_de_video.exists():
                del self.fields['link_video']

    @transaction.atomic()
    def save(self, autores, autores_tipo, autor_correspondente):
        self.instance.evento = self.evento
        self.instance.modalidade = self.modalidade
        self.instance.area_tematica = self.area_tematica
        if autores is None:
            raise forms.ValidationError('É necessário informar ao menos um autor para a submissão.')
        if autor_correspondente is None:
            raise forms.ValidationError('É necessário informar o autor correspondente.')

        super().save()
        # Associa os autores e seus tipos no modelo AutorSubmissao
        for autor in autores:
            eh_autor_correspondente = int(autor_correspondente) == int(autor.id)
            AutorSubmissao.objects.create(
                submissao=self.instance,
                participante=autor,
                tipo_autor=autores_tipo.get(str(autor.id), AutorSubmissao.AUTOR),
                autor_correspondente=eh_autor_correspondente,
            )
        self.instance.save()

    def clean_link_video(self):
        link = self.cleaned_data.get('link_video')
        if link:
            # if not re.match(r'^https?://(www\.)?(youtube|vimeo)\.com/', link):
            youtube_url_pattern = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'
            vimeo_url_pattern = r'^(https?://)?(www\.)?(vimeo\.com)/\d+'
            if not re.match(youtube_url_pattern, link) and not re.match(vimeo_url_pattern, link):
                raise forms.ValidationError('Insira um link válido para Youtube ou Vimeo.')
        return link

    def clean_texto(self):
        texto = self.cleaned_data.get('texto')
        if self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO and texto:
            if self.modalidade.tipo_limite_por_texto == TipoLimitePorTexto.PALAVRAS:
                palavras = texto.split()
                if len(palavras) > self.modalidade.limite_por_texto:
                    raise forms.ValidationError(f'O campo texto deve ter no máximo {self.modalidade.limite_por_texto} palavras.')
            elif self.modalidade.tipo_limite_por_texto == TipoLimitePorTexto.CARACTERES:
                if len(texto) > self.modalidade.limite_por_texto:
                    raise forms.ValidationError(f'O campo texto deve ter no máximo {self.modalidade.limite_por_texto} caracteres.')
        elif self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO and not texto:
            raise forms.ValidationError(f'O campo texto é de preenchimento obrigatório para a modalidade {self.modalidade.tipo.titulo}.')
        return texto

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo is None:
            raise forms.ValidationError('O campo arquivo é de preenchimento obrigatório para esta modalidade.')
        if arquivo and self.modalidade:
            ext = arquivo.name.split('.')[-1].lower()
            if ext not in self.modalidade.extensoes_permitidas():
                raise forms.ValidationError('Extensão de arquivo não permitida para esta modalidade.')
        return arquivo

    def clean(self):
        cleaned_data = super().clean()
        arquivo = cleaned_data.get('arquivo')
        link = cleaned_data.get('link_video')
        qtd_submissoes = Submissao.objects.filter(modalidade=self.modalidade).count()
        if qtd_submissoes >= self.modalidade.limite_submissoes:
            raise forms.ValidationError('O limite de submissões para esta modalidade foi atingido.')
        if self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_ARQUIVO and not (arquivo or link):
            raise forms.ValidationError(f'O campo arquivo ou link é de preenchimento obrigatório para a modalidade {self.modalidade.tipo.titulo}.')
        return cleaned_data


class EventoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Submeter'
    dimensoes = forms.MultipleModelChoiceFieldPlus(
        label='Dimensões', queryset=Dimensao.objects.all(), required=True, widget=forms.CheckboxSelectMultiplePlus()
    )
    setor = forms.ModelChoiceFieldPlus(queryset=Setor.objects.suap_ativos().all(), required=False, label='Setor')  # , widget=TreeWidget()
    classificacao = forms.ModelChoiceField(
        queryset=ClassificacaoEvento.objects.all(),
        label='Localização',
        widget=forms.RadioSelect(),
        empty_label=None,
        help_text='A classificação de um evento quanto à localização depende do envolvimento (parceria e articulação), participação (inscrição no evento) e localização do público-alvo (local de residência) para assim ser dimensionado.',
    )
    porte = forms.ModelChoiceField(
        queryset=PorteEvento.objects.all(), label='Porte', widget=forms.RenderableRadioSelect('widgets/porteevento_widget.html'), empty_label=None
    )
    espacialidades = forms.MultipleModelChoiceFieldPlus(
        label='Espacialidades', queryset=Espacialidade.ativas.all(), widget=forms.CheckboxSelectMultiplePlus()
    )
    tipo = forms.ModelChoiceField(queryset=TipoEvento.objects.all(), label='Tipo', required=True, widget=forms.RadioSelect())
    subtipo = forms.ModelChoiceField(
        label='Subtipo', queryset=SubtipoEvento.objects.all(), required=True, widget=forms.RenderableRadioSelect('widgets/subtipoevento_widget.html')
    )
    publico_alvo = forms.MultipleModelChoiceFieldPlus(
        label='Público Alvo', queryset=PublicoAlvoEvento.objects.filter(ativo=True), required=True, widget=forms.CheckboxSelectMultiplePlus()
    )
    hora_inicio = forms.TimeFieldPlus(label='Hora de Início', required=True)
    hora_fim = forms.TimeFieldPlus(label='Hora de Fim', required=True)
    campus = forms.ModelChoiceFieldPlus(label='Local de realização', queryset=UnidadeOrganizacional.objects.uo())
    organizadores = forms.MultipleModelChoiceFieldPlus(Vinculo.objects.pessoas_fisicas(), label='Organizadores')
    carga_horaria = forms.RegexField(
        label='Carga Horária do Evento', regex=r'^\d{1,}:([0-5]{1}[0-9]{1})$', required=False, help_text='Formato: "99:59"'
    )

    class Meta:
        model = Evento
        exclude = (
            'deferido',
            'motivo_indeferimento',
            'ativo',
            'data_inicio_inscricoes',
            'hora_inicio_inscricoes',
            'data_fim_inscricoes',
            'hora_fim_inscricoes',
        )

    class Media:
        js = ['/static/eventos/js/EventoForm.js']

    def __init__(self, *args, **kwargs):
        tipos_eventos = TipoEvento.objects.filter(subtipoevento__isnull=False).distinct()
        if kwargs.get('instance') and kwargs.get('instance').pk:
            instance = kwargs.get('instance')
            initial = kwargs.setdefault('initial', {})
            initial['carga_horaria'] = instance.carga_horaria_str
            if instance.get_carga_horaria():
                initial['carga_horaria'] = instance.get_carga_horaria()
        super().__init__(*args, **kwargs)
        self.is_avaliador_sistemico = Dimensao.is_avaliador_sistemico(self.request.user)
        self.is_avaliador_local = Dimensao.is_avaliador_local(self.request.user)
        if not self.is_avaliador_sistemico and not self.is_avaliador_local:
            if not self.instance.pk:
                servidor = self.request.user.get_relacionamento()
                self.fields['coordenador'].initial = servidor.pk
                self.fields['campus'].initial = servidor.setor.uo
                self.fields['setor'].initial = servidor.setor
            self.fields['coordenador'].widget = forms.HiddenInput()
            self.fields['campus'].widget = forms.HiddenInput()
            self.fields['setor'].widget = forms.HiddenInput()
        else:
            self.fields['coordenador'].required = True

        if self.instance.pk:
            try:
                tipo_participacao = TipoParticipacao.objects.get(descricao='Organizador')
                self.fields['organizadores'].initial = list(
                    self.instance.participantes.filter(tipo__tipo_participacao=tipo_participacao).values_list('vinculo_id', flat=True).distinct()
                )
            except TipoParticipacao.DoesNotExist:
                msg = 'Para funcionamento do módulo de Eventos, é necessário cadastrar um Tipo de Participação com descrição igual a "Organizador". Esse cadastro pode ser feito pelos usuários do grupo Comunicador Social Sistêmico.'
                raise forms.ValidationError(msg)
        self.fields['tipo'].queryset = tipos_eventos

    def save(self, commit=True):
        pk = self.instance.pk
        super().save(commit=True)
        if not pk:
            HistoricoEvento.objects.create(evento=self.instance, descricao='Cadastrou o evento', user=self.request.user)

        return self.instance

    def save_m2m(self, *args, **kwargs):
        pass

    def clean_carga_horaria(self):
        carga_horaria = self.cleaned_data.get('carga_horaria')
        carga_horaria = Participante.tempo_para_segundos(carga_horaria)
        subtipo = self.data.get('subtipo')
        if subtipo and not SubtipoEvento.objects.get(pk=subtipo).multiplas_atividades and not carga_horaria:
            raise forms.ValidationError('A carga horária é obrigatória para eventos com uma única atividade.')
        return carga_horaria

    def clean_publico_alvo(self):
        publico_alvo = self.cleaned_data.get('publico_alvo')
        dimensoes = self.cleaned_data.get('dimensoes', [])
        for dimensao in dimensoes:
            if dimensao.publico_alvo_requerido.exists():
                if not dimensao.publico_alvo_requerido.filter(id__in=publico_alvo.values_list('id', flat=True)):
                    publico_alvo_requerido = dimensao.publico_alvo_requerido.values_list('descricao', flat=True)
                    publico_alvo_requerido = ' e '.join(publico_alvo_requerido)
                    raise forms.ValidationError(f'O púbico alvo "{publico_alvo_requerido}" deve ser selecionado em eventos da dimensão "{dimensao}".')
        return publico_alvo

    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')

        if data_inicio and data_fim:
            if data_inicio > data_fim:
                raise forms.ValidationError('A data inicial não pode ser maior que a data final do evento.')

        return cleaned_data


class IndeferirEventoForm(forms.ModelFormPlus):
    motivo_indeferimento = forms.CharField(widget=forms.Textarea(), label='Motivo do Indeferimento')

    class Meta:
        model = Evento
        fields = ['motivo_indeferimento']

    def save(self, *args, **kwargs):
        instance = super().save(commit=False)
        self.instance.indeferir(self.instance.motivo_indeferimento, self.request.user)
        return instance


class JustificativaForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea(), label='Justificativa')


class RelatorioEventosForm(forms.FormPlus):
    campus = forms.ModelChoiceField(label='Filtrar por Campus:', required=False, queryset=UnidadeOrganizacional.objects.suap(), empty_label='Todos')
    dimensao = forms.ModelChoiceField(label='Filtrar por Dimensão:', required=False, queryset=Dimensao.objects, empty_label='Todas')
    ano = forms.ChoiceField(label='Filtrar por Ano:', required=False, choices=[])
    setor = forms.ChoiceField(label='Filtrar por Setor:', required=False, choices=[])
    capacitacao = forms.BooleanField(label='Apenas eventos de capacitação', required=False)
    possui_cunho_social = forms.BooleanField(label='Apenas eventos com cunho social', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        ANO_CHOICES = [['Todos', 'Todos']]
        _anos = (
            Evento.objects.extra({'year': 'CAST(EXTRACT(YEAR FROM data_inicio) AS TEXT)'})
            .values_list('year')
            .annotate(total_item=Count('data_inicio'))
            .values_list('year', flat=True)
            .order_by('-year')
        )
        for a in _anos:
            ANO_CHOICES.append([str(a), str(a)])
        self.fields['ano'].choices = ANO_CHOICES

        SETOR_CHOICES = [['Todos', 'Todos']]
        pks = Evento.objects.filter(deferido=True, setor__isnull=False).values_list('setor', flat=True).order_by('setor')
        for pk in pks:
            sigla = Setor.objects.filter(pk=pk).values_list('sigla', flat=True).first()
            if sigla:
                SETOR_CHOICES.append([str(pk), str(sigla)])
        self.fields['setor'].choices = SETOR_CHOICES


class RelatorioParticipantesEventosForm(forms.FormPlus):
    METHOD = 'GET'
    titulo = forms.CharFieldPlus(
        label='Por Título:',
        required=False,
    )
    campus = forms.ModelChoiceField(label='Por Campus:', required=False, queryset=UnidadeOrganizacional.objects.suap(), empty_label='Todos')
    dimensao = forms.ModelChoiceField(label='Por Dimensão:', required=False, queryset=Dimensao.objects, empty_label='Todas')
    ano = forms.ChoiceField(label='Por Ano:', required=False, choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        ANO_CHOICES = [['Todos', 'Todos']]
        _anos = (
            Evento.objects.extra({'year': 'CAST(EXTRACT(YEAR FROM data_inicio) AS TEXT)'})
            .values_list('year')
            .annotate(total_item=Count('data_inicio'))
            .values_list('year', flat=True)
            .order_by('-year')
        )
        for a in _anos:
            ANO_CHOICES.append([str(a), str(a)])
        self.fields['ano'].choices = ANO_CHOICES


class PerguntasInscricaoForm(forms.FormPlus):
    def __init__(self, evento, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for pergunta in evento.get_perguntas_inscricao():
            field_id = f'pergunta_{pergunta.id}'
            field_required = pergunta.obrigatoria

            if pergunta.tipo_pergunta in (TipoPergunta.SUBJETIVA_LONGA, TipoPergunta.SUBJETIVA_CURTA):
                if pergunta.numerico:
                    self.fields[field_id] = forms.IntegerField(label=pergunta.titulo, required=field_required)
                elif pergunta.tipo_pergunta == TipoPergunta.SUBJETIVA_LONGA:
                    self.fields[field_id] = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), label=pergunta.titulo, required=field_required)
                else:
                    self.fields[field_id] = forms.CharField(label=pergunta.titulo, required=field_required)
            else:
                opcoes_resposta = OpcaoResposta.objects.filter(pergunta=pergunta)
                if opcoes_resposta.count() < 2:
                    opcoes_resposta = OpcaoResposta.objects.filter(evento=evento, pergunta__isnull=True)
                opcao_choices = [(opcao.id, opcao.texto) for opcao in opcoes_resposta]
                if pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                    self.fields[field_id] = forms.MultipleChoiceField(
                        widget=forms.CheckboxSelectMultiplePlus, choices=opcao_choices, label=pergunta.titulo, required=field_required
                    )
                else:
                    self.fields[field_id] = forms.ChoiceField(
                        widget=forms.RadioSelect, choices=opcao_choices, label=pergunta.titulo, required=field_required
                    )

    def _get_fields(self):
        return [field_name for field_name in self.fields if field_name.startswith('pergunta_')]


class RealizarInscricaoEventoNacionalidadeForm(forms.FormPlus):
    SUBMIT_LABEL = _('Continuar')
    nacionalidade = forms.ChoiceField(label=_('Nacionalidade'), choices=Nacionalidade.choices, required=True)
    cpf = forms.BrCpfField(label=_('CPF'), help_text=_('Formato: "XXX.XXX.XXX-XX"'), required=False)
    pais_origem = forms.ModelChoiceFieldPlus2(Pais.objects.all(), label=_('País de Origem'), required=False)
    passaporte = forms.CharFieldPlus(max_length=12, label=_('Nº do Passaporte'), required=False)
    recaptcha = ReCaptchaField(label=_('Verificação'))
    termos_condicoes = forms.CharField(label='Termos e condições', widget=forms.Textarea(attrs={'readonly': True}), required=False)
    leu_termos_condicoes = forms.BooleanField(label='Li e concordo com os termos e condições.')

    fieldsets = (
        (_(''), {'fields': ('nacionalidade', 'cpf', ('pais_origem', 'passaporte'), 'termos_condicoes', 'leu_termos_condicoes', 'recaptcha')}),
    )

    class Media:
        js = ['/static/eventos/js/NacionalidadeFormToggle.js']

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        super().__init__(*args, **kwargs)
        if self.evento.termo_aceite_condicoes:
            self.fields['termos_condicoes'].initial = self.evento.termo_aceite_condicoes
        else:
            del self.fields['termos_condicoes']
            del self.fields['leu_termos_condicoes']

    def clean(self):
        cleaned_data = super().clean()
        cpf = self.cleaned_data.get('cpf')
        passaporte = self.cleaned_data.get('passaporte')
        nacionalidade = self.cleaned_data.get('nacionalidade')
        if nacionalidade == str(Nacionalidade.ESTRANGEIRO):
            if not passaporte:
                raise forms.ValidationError('Para realizar a inscrição de participante estrangeiro é necessário informar o Passaporte.')

            if not self.evento.participante_pode_se_inscrever_area_publica(False, passaporte):
                raise forms.ValidationError('Limite de inscrições atigindas para este número de passaporte.')
        else:
            if not cpf:
                raise forms.ValidationError('Para realizar a inscrição de participante é necessário informar o CPF.')

            if not self.evento.participante_pode_se_inscrever_area_publica(True, cpf):
                raise forms.ValidationError('Limite de inscrições atigindas para este CPF.')

        return cleaned_data


class RealizarInscricaoEventoDadosPessoaisForm(forms.FormPlus):
    SUBMIT_LABEL = _('Continuar')
    nome = forms.CharField(label=_('Nome'))
    email = forms.EmailField(label=_('E-mail'))
    telefone = forms.BrTelefoneField(label=_('Telefone'), help_text=_('Formato: "(99) 99999-9999"'), required=False)

    fieldsets = ((_(''), {'fields': ('nome', ('email', 'telefone'))}),)


class RealizarInscricaoEventoAtividadesForm(forms.FormPlus):
    SUBMIT_LABEL = _('Confirmar inscrição')
    tipo_participante = forms.ModelChoiceFieldPlus2(TipoParticipante.objects.none(), required=False, widget=forms.HiddenInput())
    tipo_participacao = forms.ModelChoiceFieldPlus2(TipoParticipacao.objects.none(), label=_('Tipo de participação'))
    forma_participacao = forms.ChoiceField(
        label=_('De que forma participará do evento?'), choices=[('', ''), *FormaParticipacaoEvento.choices], required=True
    )
    atividades = forms.MultipleModelChoiceField(
        AtividadeEvento.objects, label=_('Atividades'), widget=forms.RenderableSelectMultiple('widgets/atividades_disponiveis_widget.html')
    )

    fieldsets = ((_(''), {'fields': ('forma_participacao', 'tipo_participacao', 'atividades')}),)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        self.cpf = kwargs.pop('cpf')
        self.passaporte = kwargs.pop('passaporte')
        super().__init__(*args, **kwargs)
        if not self.evento.espacialidades.filter(ambiente_virtual=True).exists():
            del self.fields['forma_participacao']

        if self.evento.perguntas_corretamente_configuradas():
            resposta_form = PerguntasInscricaoForm(evento=self.evento)
            self.fields.update(resposta_form.fields)
            self.fieldsets += (('Perguntas', {'fields': (*resposta_form._get_fields(),)}),)

        if self.evento.atividadeevento_set.exists():
            self.fields['atividades'].queryset = self.evento.atividadeevento_set.all()
        else:
            del self.fields['atividades']

        tipos_participante = self.evento.get_tipo_participacoes_area_publica()
        if tipos_participante.exists():
            if self.cpf:
                tipos_participante = tipos_participante.exclude(
                    tipo_participacao__id__in=Participante.objects.filter(evento=self.evento, cpf=self.cpf).values_list(
                        'tipo__tipo_participacao__id', flat=True
                    )
                ).values_list('tipo_participacao__id', flat=True)
            else:
                tipos_participante = tipos_participante.exclude(
                    tipo_participacao__id__in=Participante.objects.filter(evento=self.evento, passaporte=self.passaporte).values_list(
                        'tipo__tipo_participacao__id', flat=True
                    )
                ).values_list('tipo_participacao__id', flat=True)

            if tipos_participante.exists():
                self.fields['tipo_participacao'].queryset = TipoParticipacao.objects.filter(pk__in=tipos_participante).order_by('descricao')

        else:
            del self.fields['tipo_participacao']

    def _get_default_tipo_participacao(self):
        try:
            return TipoParticipacao.objects.get(descricao='Participante')
        except TipoParticipacao.DoesNotExist:
            msg = 'Para funcionamento do módulo de Eventos, é necessário cadastrar um Tipo de Participação com descrição igual a "Participante". Esse cadastro pode ser feito pelos usuários do grupo Comunicador Social Sistêmico.'
            raise forms.ValidationError(msg)

    def _get_tipo_participante(self, tipo_participacao):
        return TipoParticipante.objects.filter(evento=self.evento, tipo_participacao=tipo_participacao).first()

    def clean_atividades(self):
        atividades = self.cleaned_data.get('atividades')
        for atividade in atividades:
            qtd_disponiveis = atividade.get_qtd_vagas_disponiveis()
            if qtd_disponiveis is not None and qtd_disponiveis < 1:
                raise forms.ValidationError(f'Todas as vagas já foram preenchidas para atividade: {atividade}.')
        return atividades

    def clean_tipo_participacao(self):
        tipo_participacao = self.cleaned_data.get('tipo_participacao')
        if not tipo_participacao:
            raise forms.ValidationError('O campo tipo de participação é requerido.')
        return tipo_participacao

    def clean(self):
        cleaned_data = super().clean()
        fields = list(cleaned_data.items())

        for field_name, resposta in fields:
            if field_name.startswith('pergunta_'):
                pergunta_id = int(field_name.replace('pergunta_', ''))
                pergunta = Pergunta.objects.get(id=pergunta_id, evento=self.evento, tipo_questionario=TipoQuestionario.INSCRICAO)
                if pergunta.numerico:
                    try:
                        valor = int(resposta)
                        if not (-2147483648 < valor < 2147483647):
                            self.add_error(field_name, 'O número precisa estar no intervalo entre -2147483647 e 2147483646.')
                    except Exception:
                        self.add_error(field_name, 'Este não é um número válido.')

        # Verificação do tipo de participação informado
        tipo_participacao = cleaned_data.get('tipo_participacao')
        if not tipo_participacao:
            tipo_participacao = self._get_default_tipo_participacao()

        tipo_participante = self._get_tipo_participante(tipo_participacao)
        cleaned_data['tipo_participante'] = tipo_participante

        if self.cpf and Participante.objects.filter(cpf=self.cpf, tipo=tipo_participante, evento=self.evento).exists():
            raise forms.ValidationError('CPF já inscrito no evento para este tipo de participação.')

        qtd_disponiveis = tipo_participante.get_qtd_vagas_disponiveis()
        if qtd_disponiveis is not None and qtd_disponiveis < 1:
            raise forms.ValidationError('Todas as vagas já foram preenchidas.')

        atividades = cleaned_data.get('atividades', [])
        for atividade1, atividade2 in combinations(atividades, 2):
            if atividade1.data != atividade2.data:
                continue  # ignorar se não forem no mesmo dia

            inicio1, fim1 = atividade1.hora, atividade1.hora_fim or atividade1.hora
            inicio2, fim2 = atividade2.hora, atividade2.hora_fim or atividade2.hora

            # Corrigido: checagem de interseção de intervalos
            if inicio1 < fim2 and inicio2 < fim1:
                raise forms.ValidationError(
                    f'As atividades "{atividade1}" e "{atividade2}" se sobrepõem no mesmo dia e horário. '
                    'Não é possível selecionar mais de uma atividade no mesmo dia e horário.'
                )

        return cleaned_data

    def processar(self, dados_completos):
        cpf = dados_completos.get('cpf')
        passaporte = dados_completos.get('passaporte')
        nacionalidade = dados_completos.get('nacionalidade')
        publico_alvo_id = dados_completos.get('publico_alvo_id')
        nome = dados_completos.get('nome')
        email = dados_completos.get('email')
        telefone = dados_completos.get('telefone')
        tipo_participante = dados_completos.get('tipo_participante')
        forma_participacao = dados_completos.get('forma_participacao')
        vinculo_id = dados_completos.get('vinculo_id')

        # Usa get_or_create para evitar duplicatas por race condition
        if nacionalidade == str(Nacionalidade.ESTRANGEIRO):
            participante, created = Participante.objects.get_or_create(
                evento=self.evento,
                tipo=tipo_participante,
                passaporte=passaporte,
                email=email,
                defaults={
                    'nome': nome,
                    'cpf': cpf,
                    'telefone': telefone,
                    'inscricao_validada': False,
                    'publico_alvo_id': publico_alvo_id,
                    'forma_participacao': forma_participacao,
                    'vinculo_id': vinculo_id,
                },
            )
        else:
            participante, created = Participante.objects.get_or_create(
                evento=self.evento,
                tipo=tipo_participante,
                cpf=cpf,
                email=email,
                defaults={
                    'nome': nome,
                    'passaporte': passaporte,
                    'telefone': telefone,
                    'inscricao_validada': False,
                    'publico_alvo_id': publico_alvo_id,
                    'forma_participacao': forma_participacao,
                    'vinculo_id': vinculo_id,
                },
            )

        # Atualiza campos caso o participante já existisse
        if not created:
            participante.nome = nome
            participante.telefone = telefone
            participante.forma_participacao = forma_participacao
            participante.vinculo_id = vinculo_id
            if publico_alvo_id:
                participante.publico_alvo_id = publico_alvo_id
            participante.save(update_fields=['nome', 'telefone', 'forma_participacao', 'vinculo_id', 'publico_alvo_id'])

        if 'atividades' in self.cleaned_data and self.cleaned_data.get('atividades'):
            for atividade in self.cleaned_data.get('atividades'):
                participante.atividades.add(atividade)

        for field_name, resposta in self.cleaned_data.items():
            if field_name.startswith('pergunta_'):
                pergunta_id = int(field_name.replace('pergunta_', ''))
                pergunta = Pergunta.objects.get(id=pergunta_id, evento=self.evento, tipo_questionario=TipoQuestionario.INSCRICAO)

                if pergunta.tipo_pergunta in (TipoPergunta.SUBJETIVA_LONGA, TipoPergunta.SUBJETIVA_CURTA):
                    if pergunta.numerico:
                        RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, resposta_numero=resposta)
                    else:
                        RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, resposta_texto=resposta)
                elif pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                    for opcao_id in resposta:
                        opcao_resposta = OpcaoResposta.objects.get(id=opcao_id)
                        RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, opcao_resposta=opcao_resposta)
                elif resposta:
                    opcao_resposta = OpcaoResposta.objects.get(id=resposta)
                    RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, opcao_resposta=opcao_resposta)

        if self.evento.confirmacao_automatica_inscricao:
            participante.inscricao_validada = True
            participante.save()
            Notificar.inscricao_no_evento(self.evento, participante)

        return participante


class AvaliacaoParticipanteForm(forms.FormPlus):
    SUBMIT_LABEL = _('Enviar avaliação')

    def __init__(self, evento, *args, **kwargs):
        self.evento = evento
        self.perguntas = list(evento.get_perguntas_avaliacao())
        super().__init__(*args, **kwargs)

        for pergunta in self.perguntas:
            field_id = f'pergunta_{pergunta.id}'
            required = pergunta.obrigatoria
            if pergunta.tipo_pergunta == TipoPergunta.SUBJETIVA_LONGA:
                self.fields[field_id] = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), label=pergunta.titulo, required=required)
                continue
            if pergunta.tipo_pergunta == TipoPergunta.SUBJETIVA_CURTA:
                if pergunta.numerico:
                    self.fields[field_id] = forms.IntegerField(label=pergunta.titulo, required=required)
                else:
                    self.fields[field_id] = forms.CharField(label=pergunta.titulo, required=required)
                continue

            opcoes_resposta = list(OpcaoResposta.objects.filter(pergunta=pergunta).order_by('ordem'))
            if len(opcoes_resposta) < 2:
                opcoes_resposta = list(OpcaoResposta.objects.filter(evento=evento, pergunta__isnull=True).order_by('ordem'))
            opcao_choices = [(opcao.id, opcao.texto) for opcao in opcoes_resposta]
            if pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                self.fields[field_id] = forms.MultipleChoiceField(
                    widget=forms.CheckboxSelectMultiplePlus, choices=opcao_choices, label=pergunta.titulo, required=required
                )
            else:
                self.fields[field_id] = forms.ChoiceField(widget=forms.RadioSelect, choices=opcao_choices, label=pergunta.titulo, required=required)

    def _iter_respostas(self):
        for pergunta in self.perguntas:
            field_name = f'pergunta_{pergunta.id}'
            yield pergunta, self.cleaned_data.get(field_name)

    def processar(self, participante):
        for pergunta, resposta in self._iter_respostas():
            if pergunta.tipo_pergunta in (TipoPergunta.SUBJETIVA_LONGA, TipoPergunta.SUBJETIVA_CURTA):
                if pergunta.numerico and resposta is not None:
                    RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, resposta_numero=resposta)
                else:
                    RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, resposta_texto=resposta)
            elif pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                for opcao_id in resposta or []:
                    RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, opcao_resposta_id=opcao_id)
            elif resposta:
                RespostaParticipante.objects.create(participante=participante, pergunta=pergunta, opcao_resposta_id=resposta)


class InformarAtividadesForm(forms.ModelFormPlus):
    atividades = forms.MultipleModelChoiceField(
        AtividadeEvento.objects, label='Atividades', widget=forms.RenderableSelectMultiple('widgets/atividades_widget.html'), required=False
    )

    class Meta:
        model = Participante
        fields = ('atividades',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atividades'].queryset = self.instance.evento.atividadeevento_set.all()


class InformarParticipantesForm(forms.FormPlus):
    cpfs = forms.CharField(
        label='CPFs', help_text='Informar CPF dos participantes seperados por espaço ou em linhas diferentes.', required=True, widget=forms.Textarea()
    )

    def processar(self, atividade_pk):
        atividade = AtividadeEvento.objects.get(pk=atividade_pk)
        cpfs = self.cleaned_data['cpfs'].replace('\n', ' ').split()
        for participante in atividade.evento.participantes.filter(cpf__in=cpfs):
            participante.atividades.add(atividade)


class AdicionarParticipanteEventoForm(forms.ModelFormPlus):
    nacionalidade = forms.ChoiceField(label=_('Nacionalidade'), choices=Nacionalidade.choices, required=True)
    cpf = forms.BrCpfField(label=_('CPF'), help_text=_('Formato: "XXX.XXX.XXX-XX"'), required=False)
    pais_origem = forms.ModelChoiceFieldPlus2(Pais.objects.all(), label=_('País de Origem'), required=False)
    passaporte = forms.CharFieldPlus(max_length=12, label=_('Nº do Passaporte'), required=False)

    atividades = forms.MultipleModelChoiceField(
        AtividadeEvento.objects, label='', widget=forms.RenderableSelectMultiple('widgets/atividades_widget.html'), required=False
    )

    class Meta:
        model = Participante
        fields = 'nome', 'nacionalidade', 'cpf', 'pais_origem', 'passaporte', 'email', 'telefone', 'publico_alvo', 'ch_extensao', 'foto', 'curriculo'

    class Media:
        js = ['/static/eventos/js/NacionalidadeFormToggle.js']

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('nacionalidade'),
                    ('nome'),
                    ('cpf'),
                    ('pais_origem'),
                    ('passaporte'),
                    ('email', 'telefone'),
                    'publico_alvo',
                    'foto',
                    'curriculo',
                )
            },
        ),
        ('Atividades do Evento', {'fields': ('atividades',)}),
    )

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        self.publico_alvo = kwargs.pop('publico_alvo')
        self.tipo_participante = kwargs.pop('tipo_participante')
        super().__init__(*args, **kwargs)
        self.fields['atividades'].queryset = AtividadeEvento.objects.filter(evento=self.evento)
        self.fields['publico_alvo'].queryset = self.evento.publico_alvo.all()
        if not self.fields['atividades'].queryset.exists():
            self.fieldsets = (self.fieldsets[0],)
        if self.tipo_participante.tipo_participacao.descricao.lower() != 'convidado':
            del self.fields['foto']
            del self.fields['curriculo']
        publicos_ativos = self.evento.publico_alvo.filter(ativo=True).values_list('pk', flat=True)
        if PublicoAlvoEvento.PUBLICO_EXTERNO not in publicos_ativos:
            del self.fields['nacionalidade']
            del self.fields['pais_origem']
            del self.fields['passaporte']
            self.fields['cpf'].required = True

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        nacionalidade = self.cleaned_data.get('nacionalidade')
        if nacionalidade != str(Nacionalidade.ESTRANGEIRO):
            if Participante.objects.filter(cpf=cpf, tipo=self.tipo_participante, evento=self.instance.evento).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('CPF já cadastrado para este evento, neste tipo de participação.')
        return cpf

    def clean_passaporte(self):
        passaporte = self.cleaned_data.get('passaporte')
        nacionalidade = self.cleaned_data.get('nacionalidade')
        if nacionalidade == str(Nacionalidade.ESTRANGEIRO):
            if (
                Participante.objects.filter(passaporte=passaporte, tipo=self.tipo_participante, evento=self.instance.evento)
                .exclude(pk=self.instance.pk)
                .exists()
            ):
                raise forms.ValidationError('Passaporte já cadastrado para este evento, neste tipo de participação.')
        return passaporte

    def clean_ch_extensao(self):
        ch_extensao = self.cleaned_data.get('ch_extensao')
        self.instance.cpf = self.data.get('cpf')
        if ch_extensao and not self.instance.is_aluno_extensao():
            raise forms.ValidationError('Não existe uma matrícula ativa para esse participante em curso que requer atividade curricular de extensão.')
        return ch_extensao

    def clean_publico_alvo(self):
        self.instance.passaporte = self.cleaned_data.get('passaporte')
        self.instance.nacionalidade = self.cleaned_data.get('nacionalidade')
        self.instance.cpf = self.cleaned_data.get('cpf')
        if self.instance.nacionalidade != str(Nacionalidade.ESTRANGEIRO):
            self.instance.publico_alvo = self.cleaned_data.get('publico_alvo')
            self.instance.checar_vinculo()
            return self.instance.publico_alvo
        else:
            self.instance.publico_alvo = PublicoAlvoEvento.objects.get(id=PublicoAlvoEvento.PUBLICO_EXTERNO)
            return self.instance.publico_alvo

    def clean(self):
        cleaned_data = super().clean()
        nacionalidade = cleaned_data.get('nacionalidade')
        cpf = cleaned_data.get('cpf')
        passaporte = cleaned_data.get('passaporte')

        if nacionalidade == str(Nacionalidade.ESTRANGEIRO):
            if not passaporte:
                raise forms.ValidationError('Para realizar a inscrição de participante estrangeiro é necessário informar o Passaporte.')
        else:
            if not cpf:
                raise forms.ValidationError('Para realizar a inscrição de participante é necessário informar o CPF.')
        return cleaned_data

    def save(self, *args, **kwargs):
        participante = super().save(*args, **kwargs)
        for atividade in self.cleaned_data['atividades']:
            participante.atividades.add(atividade)
        if participante.evento.confirmacao_automatica_inscricao:
            participante.inscricao_validada = True
            participante.save()
            Notificar.inscricao_no_evento(self.evento, participante)


class EditarParticipanteEventoForm(forms.ModelFormPlus):
    class Meta:
        model = Participante
        fields = (
            'nome',
            'cpf',
            'email',
            'telefone',
            'publico_alvo',
            'inscricao_validada',
            'presenca_confirmada',
            'situacao_convite',
            'ch_extensao',
            'foto',
            'curriculo',
        )

    fieldsets = (
        ('Dados gerais', {'fields': (('nome', 'cpf'), ('email', 'telefone'), 'publico_alvo', 'foto', 'curriculo')}),
        (
            'Dados da Participação',
            {
                'fields': (
                    (
                        'inscricao_validada',
                        'presenca_confirmada',
                        'situacao_convite',
                    )
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.get('initial', {})
        initial['atividades'] = kwargs['instance'].atividades.values_list('pk', flat=True)
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        if self.instance.tipo.tipo_participacao.descricao.lower() != 'convidado':
            del self.fields['foto']
            del self.fields['curriculo']
        if self.instance.tipo.tipo_participacao.descricao.lower() != 'avaliador de trabalho':
            del self.fields['situacao_convite']
        self.fields['publico_alvo'].queryset = self.instance.evento.publico_alvo.all()

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if Participante.objects.filter(cpf=cpf, tipo=self.instance.tipo, evento=self.instance.evento).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('CPF já cadastrado para este evento.')
        return cpf

    def clean_ch_extensao(self):
        ch_extensao = self.cleaned_data.get('ch_extensao')
        if ch_extensao and not self.instance.is_aluno_extensao():
            raise forms.ValidationError('Não existe uma matrícula ativa para esse participante em curso que requer atividade curricular de extensão.')
        return ch_extensao

    def clean_publico_alvo(self):
        self.instance.cpf = self.cleaned_data.get('cpf')
        self.instance.publico_alvo = self.cleaned_data.get('publico_alvo')
        self.instance.checar_vinculo()
        return self.instance.publico_alvo


class ImportarParticipantesForm(forms.FormPlus):
    planilha = forms.FileFieldPlus(
        help_text='O arquivo deve ser no formato "xlsx" ou "xls", sem cabeçalho, contendo as seguintes colunas: CPF, Nome, E-mail, Perfil e Telefone.',
        filetypes=['xlsx', 'xls'],
    )

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        self.tipo_participante = kwargs.pop('tipo_participante')
        super().__init__(*args, **kwargs)

        self.participantes = []
        publico_alvo_exibicao = format_(self.evento.publico_alvo)
        self.fields[
            'planilha'
        ].help_text = f'{self.fields["planilha"].help_text} A coluna <b>Perfil</b> aceita as seguintes opções: {publico_alvo_exibicao}.'

    def clean(self):
        arquivo = self.cleaned_data.get('planilha')
        if arquivo:
            # Valida se eh XLS
            # -------------------------
            try:
                df = pd.read_excel(arquivo, header=None)
            except Exception:
                raise forms.ValidationError('Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx,')

            # Valida se existem 5 colunas
            # -------------------------
            if df.shape[1] < 4:
                raise forms.ValidationError('A planilha deve conter pelo menos 4 colunas das 5 solicitadas.')

            erro = []
            cpf_set = set()  # Para controlar CPFs únicos
            cpf_validator = BrCpfField()
            for index, row in df.iterrows():
                publico_alvo = None
                linha = index + 1

                # Valida se cada uma das colunas tem os dados esperados na planilha
                # CPF, Nome, E-mail, Perfil e Telefone

                # Valida Nome
                nome = row.iloc[1]
                if not nome:
                    erro.append(f'Nome inválido na linha {linha}')

                # Valida Cpf
                cpf = str(row.iloc[0])
                cpf = cpf.zfill(11)
                try:
                    cpf = cpf_validator.clean(cpf)
                except forms.ValidationError:
                    erro.append(f'CPF inválido "{cpf}" na linha {linha}')

                # if Participante.objects.filter(cpf=cpf, evento=self.evento, tipo=self.tipo_participante).exists():
                #    erro.append(f'CPF repetido "{cpf}" na linha {linha}')
                if cpf in cpf_set:
                    erro.append(f'CPF repetido "{cpf}" na linha {linha}')
                cpf_set.add(cpf)

                # Valida Email
                email = row.iloc[2]
                try:
                    email_field = forms.EmailField()
                    email = email_field.clean(email)
                except forms.ValidationError:
                    erro.append(f'Email inválido "{email}" na linha {linha}')

                # Valida Perfil
                descricao_publico_alvo = row.iloc[3]
                if descricao_publico_alvo:
                    publico_alvo = self.evento.publico_alvo.filter(descricao__unaccent__iexact=descricao_publico_alvo).first()
                    if not publico_alvo:
                        erro.append(f'Perfil inválido "{descricao_publico_alvo}" na linha {linha}')
                else:
                    erro.append(f'Perfil inválido "{descricao_publico_alvo}" na linha {linha}')

                # Valida Telefone se ele estiver na planilha
                telefone = None
                if len(row) >= 5:
                    telefone = row.iloc[4]
                    if telefone:
                        if isinstance(telefone, float) and telefone.is_integer():
                            telefone = str(int(telefone))
                        try:
                            telefone_field = forms.BrTelefoneField()
                            telefone = telefone_field.clean(telefone)
                        except forms.ValidationError:
                            erro.append(f'Telefone inválido "{telefone}" na linha {linha}')

                participante = self.evento.participantes.filter(cpf=cpf, tipo=self.tipo_participante).first()
                if participante:
                    dados_atualizados = participante.nome != nome or participante.email != email
                else:
                    dados_atualizados = False
                    participante = Participante()
                participante.evento = self.evento
                participante.cpf = cpf
                participante.nome = nome
                participante.email = email
                participante.telefone = telefone
                participante.inscricao_validada = True
                if dados_atualizados and participante.certificado_enviado:
                    participante.certificado_enviado = False
                participante.publico_alvo = publico_alvo
                participante.checar_vinculo()
                self.participantes.append(participante)

            if erro:
                raise forms.ValidationError('A planilha contém o(s) seguinte(s) erro(s): </br>{}'.format('</br> '.join(erro)))

        return self.cleaned_data

    @transaction.atomic
    def processar(self):
        for participante in self.participantes:
            participante.tipo = self.tipo_participante
            participante.save()


class BannerForm(forms.ModelFormPlus):
    class Meta:
        model = Banner
        fields = ('titulo', 'imagem', 'tipo', 'data_inicio', 'data_termino', 'link')

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('data_inicio') and cleaned_data.get('data_termino'):
            banners = Banner.objects.filter(data_inicio__lte=cleaned_data.get('data_termino'), data_termino__gte=cleaned_data.get('data_inicio'))
            if self.instance.pk:
                banners = banners.exclude(id=self.instance.id)
            if banners.exists():
                self.add_error('data_inicio', 'Já existe um banner ativo no período escolhido.')
        return cleaned_data


class AtendimentoPublicoForm(forms.ModelFormPlus):
    class Meta:
        model = AtendimentoPublico
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.request.user
        if not user.has_perm('ae.add_tipoatendimento'):
            self.fields['campus'].queryset = self.fields['campus'].queryset.filter(id=get_uo(user).id)


class FotoEventoForm(forms.ModelFormPlus):
    class Meta:
        model = FotoEvento
        fields = ('imagem', 'descricao')

    fieldsets = (('Dados gerais', {'fields': ('imagem', 'descricao')}),)

    def save(self, evento):
        self.instance.evento = evento
        super().save()


class VideoEventoForm(forms.ModelFormPlus):
    class Meta:
        model = VideoEvento
        fields = ('video', 'descricao')

    fieldsets = (('Dados gerais', {'fields': ('video', 'descricao')}),)

    def save(self, evento):
        self.instance.evento = evento
        super().save()


class AnexoEventoForm(forms.ModelFormPlus):
    class Meta:
        model = AnexoEvento
        fields = ('arquivo', 'descricao')

    fieldsets = (('Dados gerais', {'fields': ('arquivo', 'descricao')}),)

    def save(self, evento):
        self.instance.evento = evento
        super().save()


class ImportarListaPresencaForm(forms.FormPlus):
    planilha = forms.FileFieldPlus(help_text='O arquivo deve ser no formato "xlsx", sem cabeçalho, contendo o CPF dos participantes.')

    def __init__(self, evento, tipo_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evento = evento
        self.tipo_id = tipo_id
        self.participantes = []

    @staticmethod
    def _ler_planilha(arquivo: UploadedFile) -> pd.DataFrame:
        try:
            return pd.read_excel(arquivo, header=None)
        except Exception:
            raise forms.ValidationError(
                'Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx, sem cabeçalho e se contém o CPF.'
            )

    @staticmethod
    def _celula_do_cpf(linha: pd.Series) -> object | None:
        """CPF da linha: a 1ª coluna ou, quando vazia, a 2ª. ``None`` se não houver (inclusive em planilha de uma coluna)."""
        for celula in linha.iloc[:2]:
            if not pd.isna(celula):
                return celula
        return None

    @staticmethod
    def _texto_do_cpf(celula: object) -> str:
        """Texto da célula; CPF numérico (``float`` do Excel) perde o ``.0``."""
        try:
            return str(int(celula))  # type: ignore[call-overload]
        except ValueError, TypeError:
            return str(celula)

    @staticmethod
    def _cpf_validado(texto: str) -> str | None:
        """CPF formatado, ou ``None`` quando o texto não é um CPF válido."""
        try:
            return BrCpfField().clean(texto)
        except forms.ValidationError:
            return None

    def clean(self) -> dict[str, object]:
        arquivo = self.cleaned_data.get('planilha')
        if arquivo:
            df = self._ler_planilha(arquivo)
            cpfs_invalidos: list[str] = []
            for indice, linha in df.iterrows():
                celula = self._celula_do_cpf(linha)
                if celula is None:
                    cpfs_invalidos.append(f'(linha {int(indice) + 1} sem CPF)')  # type: ignore[call-overload]
                    continue
                texto = self._texto_do_cpf(celula)
                cpf = self._cpf_validado(texto)
                if cpf is None:
                    cpfs_invalidos.append(texto)
                    continue

                participante = self.evento.participantes.filter(tipo_id=self.tipo_id, cpf=cpf).first()
                self.participantes.append(participante)

            if cpfs_invalidos:
                raise forms.ValidationError(
                    'A planilha contém os participantes com CPF inválido: {}. Faça a correção antes de importar a planilha.'.format(
                        ', '.join(cpfs_invalidos)
                    )
                )

        return self.cleaned_data

    @transaction.atomic
    def processar(self):
        for participante in self.participantes:
            if participante:
                participante.presenca_confirmada = True
                participante.save()


class EnviarMensagemForm(forms.Form):
    assunto = forms.CharField(label='Assunto')
    mensagem = forms.CharField(label='Mensagem', widget=forms.Textarea())

    def __init__(self, evento, *args, **kwargs):
        self.evento = evento
        super().__init__(*args, **kwargs)

    def processar(self):
        pass


class TipoModalidadeForm(forms.ModelFormPlus):
    class Meta:
        model = TipoModalidade
        fields = ('titulo',)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        super().__init__(*args, **kwargs)

    def save(self):
        self.instance.evento = self.evento
        super().save()


class InternacionalizacaoForm(forms.ModelFormPlus):
    class Meta:
        model = Internacionalizacao
        fields = ('idioma', 'titulo', 'apresentacao', 'local')

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        super().__init__(*args, **kwargs)
        self.fields['idioma'].choices = [['', '']] + [(code, name) for code, name in settings.LANGUAGES if code != 'pt-br']
        # Remove idiomas já utilizados neste evento
        if self.evento:
            idiomas_usados = self.evento.internacionalizacao_set.values_list('idioma', flat=True)
            self.fields['idioma'].choices = [(code, name) for code, name in self.fields['idioma'].choices if code not in idiomas_usados or code == '']

    def save(self):
        self.instance.evento = self.evento
        super().save()


class AtividadeEventoForm(forms.ModelFormPlus):
    tipo = forms.ModelChoiceFieldPlus(
        label='Tipo de Atividade', queryset=TipoAtividade.objects.all().order_by('descricao'), widget=forms.Select, required=True
    )
    data = forms.DateFieldPlus(label='Data de início')
    hora = forms.TimeFieldPlus(label='Hora de início')
    ch = forms.RegexField(label='Carga Horária', regex=r'^\d{1,}:([0-5]{1}[0-9]{1})$', required=True, help_text='Formato: "99:59"')
    data_fim = forms.DateFieldPlus(label='Data de fim', required=False)
    hora_fim = forms.TimeFieldPlus(label='Hora de fim', required=False)

    class Meta:
        model = AtividadeEvento
        fields = ('tipo', 'descricao', 'data', 'hora', 'data_fim', 'hora_fim', 'ch', 'limite_inscricoes')

    fieldsets = (('', {'fields': ('tipo', 'descricao', ('data', 'hora', 'data_fim', 'hora_fim'), ('ch', 'limite_inscricoes'))}),)

    def __init__(self, *args, **kwargs):
        if kwargs.get('instance') and kwargs.get('instance').pk:
            initial = kwargs.setdefault('initial', {})
            initial['ch'] = kwargs.get('instance').get_ch()
        self.evento = kwargs.pop('evento', None)
        super().__init__(*args, **kwargs)

    def clean_ch(self):
        tempo_ch = self.cleaned_data.get('ch')
        return Participante.tempo_para_segundos(tempo_ch)

    def save(self):
        self.instance.evento = self.evento
        super().save()

    def clean(self):
        cleaned_data = super().clean()
        data = cleaned_data.get('data', None)
        data_fim = cleaned_data.get('data_fim', None)

        if data and self.evento and self.evento.data_inicio and self.evento.data_fim:
            if not (self.evento.data_inicio <= data <= self.evento.data_fim):
                self.add_error('data', 'A data de início de uma atividade não pode ser antes ou depois do período de realização do evento.')

        if data_fim and self.evento and self.evento.data_inicio and self.evento.data_fim:
            if not (self.evento.data_inicio <= data_fim <= self.evento.data_fim):
                self.add_error('data_fim', 'A data fim de uma atividade não pode ser antes ou depois do período de realização do evento.')

        return cleaned_data


class TipoParticipanteForm(forms.ModelFormPlus):
    tipo_participacao = forms.ModelChoiceFieldPlus(label='Tipo de Participação', queryset=TipoParticipacao.objects.all(), required=True)
    permite_inscricao_direta = forms.BooleanField(label='Permite Inscrição Direta', required=False)
    data_inicio_inscricoes = forms.DateFieldPlus(label='Início das Inscrições', required=False)
    hora_inicio_inscricoes = forms.TimeFieldPlus(
        label='Hora de Início das Inscrições',
        required=False,
    )
    data_fim_inscricoes = forms.DateFieldPlus(label='Fim das Inscrições', required=False)
    hora_fim_inscricoes = forms.TimeFieldPlus(
        label='Hora de Fim das Inscrições',
        required=False,
    )

    class Meta:
        model = TipoParticipante
        fields = (
            'tipo_participacao',
            'limite_inscricoes',
            'modelo_certificado',
            'permite_inscricao_direta',
            'exibir_participantes_inscricao',
            'data_inicio_inscricoes',
            'hora_inicio_inscricoes',
            'data_fim_inscricoes',
            'hora_fim_inscricoes',
        )

    fieldsets = (
        (
            '',
            {
                'fields': (
                    'evento',
                    ('tipo_participacao', 'limite_inscricoes'),
                    'modelo_certificado',
                    'permite_inscricao_direta',
                    ('data_inicio_inscricoes', 'hora_inicio_inscricoes'),
                    ('data_fim_inscricoes', 'hora_fim_inscricoes'),
                    'exibir_participantes_inscricao',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento', None)
        super().__init__(*args, **kwargs)

    def save(self):
        self.instance.evento = self.evento
        super().save()

    def clean_data_inicio_inscricoes(self):
        data_inicio_inscricoes = self.cleaned_data.get('data_inicio_inscricoes')
        permite_inscricao_direta = self.cleaned_data.get('permite_inscricao_direta')
        data_inicio = self.evento.data_inicio
        if self.cleaned_data.get('tipo_participacao') and data_inicio and data_inicio_inscricoes and data_inicio_inscricoes > data_inicio:
            raise forms.ValidationError('A data de início das inscrições deve ser menor ou igual a data de início do evento.')
        if permite_inscricao_direta is True and not data_inicio_inscricoes:
            raise forms.ValidationError('A data de início das inscrições é obrigatória para tipos de participantes que permitem inscrição direta.')
        return data_inicio_inscricoes

    def clean_data_fim_inscricoes(self):
        data_fim_inscricoes = self.cleaned_data.get('data_fim_inscricoes')
        permite_inscricao_direta = self.cleaned_data.get('permite_inscricao_direta')
        data_fim = self.evento.data_fim
        if self.cleaned_data.get('tipo_participacao') and data_fim and data_fim_inscricoes and data_fim_inscricoes > data_fim:
            raise forms.ValidationError('A data de fim das inscrições deve ser menor ou igual a data de término do evento.')
        if permite_inscricao_direta is True and not data_fim_inscricoes:
            raise forms.ValidationError('A data de fim das inscrições é obrigatória para tipos de participantes que permitem inscrição direta.')
        return data_fim_inscricoes

    def clean(self):
        cleaned_data = super().clean()
        tipo_participacao = cleaned_data.get('tipo_participacao')
        permite_inscricao_direta = cleaned_data.get('permite_inscricao_direta')
        if permite_inscricao_direta is True and tipo_participacao and tipo_participacao.permite_inscricao_direta is False:
            self.add_error('permite_inscricao_direta', 'Não é possível habilitar a inscrição direta para este tipo de participante.')

        data_inicio_inscricoes = cleaned_data.get('data_inicio_inscricoes')
        data_fim_inscricoes = cleaned_data.get('data_fim_inscricoes')
        if data_inicio_inscricoes and data_fim_inscricoes:
            if data_inicio_inscricoes > data_fim_inscricoes:
                self.add_error('data_inicio_inscricoes', 'A data de início das inscrições não pode ser maior que a data de fim das inscrições.')

        qs = TipoParticipante.objects.filter(evento=self.evento, tipo_participacao=tipo_participacao)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error('tipo_participacao', 'Já existe um tipo de participante com este tipo de participação para este evento.')
        return cleaned_data


class SubmeterNovaVersaoForm(forms.ModelFormPlus):
    class Meta:
        model = VersaoSubmissao
        fields = ('texto', 'arquivo', 'comentario')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.submissao = self.instance.submissao
        self.modalidade = self.submissao.modalidade
        if self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO:
            del self.fields['arquivo']
        else:
            del self.fields['texto']
            self.fields['arquivo'].widget = FileInputWithAccept(accept_exts=self.modalidade.extensoes_permitidas())

    @transaction.atomic()
    def save(self):
        super().save()
        self.submissao.situacao = SituacaoSubmissao.RESSUBMETIDO
        self.submissao.arquivo = self.instance.arquivo
        self.submissao.texto = self.instance.texto
        self.submissao.save()

    def clean_texto(self):
        texto = self.cleaned_data.get('texto')
        if self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO and texto:
            if self.modalidade.tipo_limite_por_texto == TipoLimitePorTexto.PALAVRAS:
                palavras = texto.split()
                if len(palavras) > self.modalidade.limite_por_texto:
                    raise forms.ValidationError(f'O campo texto deve ter no máximo {self.modalidade.limite_por_texto} palavras.')
            elif self.modalidade.tipo_limite_por_texto == TipoLimitePorTexto.CARACTERES:
                if len(texto) > self.modalidade.limite_por_texto:
                    raise forms.ValidationError(f'O campo texto deve ter no máximo {self.modalidade.limite_por_texto} caracteres.')
        elif self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO and not texto:
            raise forms.ValidationError(f'O campo texto é de preenchimento obrigatório para a modalidade {self.modalidade.tipo.titulo}.')
        return texto

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo and self.modalidade:
            ext = arquivo.name.split('.')[-1].lower()
            if ext not in self.modalidade.extensoes_permitidas():
                raise forms.ValidationError('Extensão de arquivo não permitida para esta modalidade.')
        return arquivo

    def clean(self):
        cleaned_data = super().clean()
        texto = cleaned_data.get('texto')
        arquivo = cleaned_data.get('arquivo')

        if self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO and not texto:
            raise forms.ValidationError('O campo texto é obrigatório.')
        elif self.modalidade.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_ARQUIVO and not arquivo:
            raise forms.ValidationError('O campo arquivo é obrigatório.')

        return cleaned_data


class MigrarTipoParticipanteForm(forms.FormPlus):
    SUBMIT_LABEL = 'Processar migração'

    cpfs = forms.CharField(
        label='CPFs dos participantes',
        widget=forms.Textarea(
            attrs={'rows': 5, 'placeholder': 'Digite os CPFs dos participantes (um por linha)\nExemplo:\n123.456.789-00\n987.654.321-11'}
        ),
        help_text='Digite os CPFs dos participantes que deseja migrar, um por linha, formatados (XXX.XXX.XXX-XX)',
    )
    tipo_origem = forms.ModelChoiceField(label='Tipo de participação origem', queryset=None, help_text='Tipo de participação atual dos participantes')
    tipo_destino = forms.ModelChoiceField(
        label='Tipo de participação destino', queryset=None, help_text='Tipo de participação para onde os participantes serão migrados'
    )
    senha_confirmacao = forms.PasswordField(label='Confirme sua senha', required=True)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        super().__init__(*args, **kwargs)

        # Filtra os tipos de participante disponíveis para o evento
        self.fields['tipo_origem'].queryset = TipoParticipante.objects.filter(evento=self.evento)
        self.fields['tipo_destino'].queryset = TipoParticipante.objects.filter(evento=self.evento)

    def clean_cpfs(self):
        cpfs_texto = self.cleaned_data.get('cpfs')
        if not cpfs_texto:
            raise forms.ValidationError('É necessário informar pelo menos um CPF.')

        # Separa os CPFs por linha e remove espaços em branco
        cpfs_lista = [cpf.strip() for cpf in cpfs_texto.split('\n') if cpf.strip()]

        if not cpfs_lista:
            raise forms.ValidationError('É necessário informar pelo menos um CPF válido.')

        # Valida cada CPF e verifica duplicidade
        cpfs_validos = []
        cpfs_vistos = set()

        for cpf in cpfs_lista:
            try:
                # Usa o campo BrCpfField para validar o formato
                campo_cpf = BrCpfField()
                cpf_validado = campo_cpf.clean(cpf)

                # Verifica duplicidade
                if cpf_validado in cpfs_vistos:
                    raise forms.ValidationError(f'CPF duplicado encontrado: {cpf_validado}')

                cpfs_vistos.add(cpf_validado)
                cpfs_validos.append(cpf_validado)

            except forms.ValidationError as e:
                if 'duplicado' in str(e):
                    raise  # Re-raise validation error for duplicates
                else:
                    raise forms.ValidationError(f'CPF inválido: {cpf}')

        return cpfs_validos

    def clean(self):
        cleaned_data = super().clean()
        tipo_origem = cleaned_data.get('tipo_origem')
        tipo_destino = cleaned_data.get('tipo_destino')

        if tipo_origem and tipo_destino and tipo_origem == tipo_destino:
            raise forms.ValidationError('O tipo de participação origem deve ser diferente do tipo destino.')

        return cleaned_data

    def processar_migracao(self):
        """
        Processa a migração dos participantes.
        Retorna uma tupla (sucesso, lista_erros, qtd_migrados)
        """
        cpfs = self.cleaned_data['cpfs']
        tipo_origem = self.cleaned_data['tipo_origem']
        tipo_destino = self.cleaned_data['tipo_destino']

        erros = []
        participantes_para_migrar = []

        # Verifica cada participante
        for cpf in cpfs:
            # Verifica se existe na origem
            participante_origem = Participante.objects.filter(evento=self.evento, cpf=cpf, tipo=tipo_origem).first()

            if not participante_origem:
                erros.append(f'Participante com CPF {cpf} não encontrado no tipo de participação "{tipo_origem.tipo_participacao.descricao}".')
                continue

            # Verifica se já existe no destino
            participante_destino = Participante.objects.filter(evento=self.evento, cpf=cpf, tipo=tipo_destino).first()

            if participante_destino:
                erros.append(f'Participante com CPF {cpf} já existe no tipo de participação "{tipo_destino.tipo_participacao.descricao}".')
                continue

            participantes_para_migrar.append(participante_origem)

        # Se há erros, não prossegue com a migração
        if erros:
            return False, erros, 0

        # Realiza a migração usando transação
        qtd_migrados = 0
        try:
            with transaction.atomic():
                for participante in participantes_para_migrar:
                    participante.tipo = tipo_destino
                    participante.save()
                    qtd_migrados += 1

            return True, [], qtd_migrados

        except Exception as e:
            return False, [f'Erro ao realizar migração: {e!s}'], 0
