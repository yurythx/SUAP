import datetime
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from comum.models import Ano, Configuracao, Vinculo
from djtools import forms
from djtools.choices import DiaSemanaChoices
from djtools.forms import SpanField, SpanWidget
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget, BrTelefoneWidget, RenderableSelectMultiple
from djtools.templatetags.filters import format_datetime
from djtools.utils import full_check_file, ha_choque_de_periodo
from documento_eletronico.models import DocumentoTexto
from pgd2.api_pgd2_v2 import ApiPgd2V2
from pgd2.models import (
    ComissaoPGD,
    ConfiguracaoOrientacaoPit,
    ConfiguracaoOrientacaoPlanoEntregasSetorial,
    ConfiguracaoPerfilServidor,
    DocumentoAdesaoPesServidor,
    DocumentoAdesaoServidor,
    JustificativaDesligamentoPgd,
    PeriodoPes,
    PeriodoPitRit,
    PGDExterior,
    PlanoEntregasSetorial,
    PlanoEntregasSetorialEntregas,
    PlanoEntregasSetorialHorarioFuncionamentoSetor,
    PlanoEntregasSetorialHorarioPlanejamentoSetor,
    PlanoIndividualTrabalho,
    PlanoIndividualTrabalhoAtendimento,
    PlanoIndividualTrabalhoCopia,
    PlanoIndividualTrabalhoEntregas,
    PlanoIndividualTrabalhoPresencial,
    RelatorioIndividualTrabalho,
    RelatorioIndividualTrabalhoQuestionario,
    SetorHabilitacao,
    SolicitacaoAdesaoServidor,
)
from pgd2.utils import get_datetime_now, get_setores_pgd, utilizar_integracao_com_pde, utilizar_integracao_com_plan_estrategico
from plan_estrategico.models import AtividadeEtapa
from processo_eletronico.models import Processo
from rh.models import AfastamentoSiape, CargoEmprego, JornadaTrabalho, Servidor, Setor, Situacao, UnidadeOrganizacional
from suap import nomenclatura


class ConfiguracaoForm(forms.FormPlus):
    permite_auditoria_centralizada = forms.BooleanField(label='Utilizar auditoria centralizada', required=False)
    auditoria_centralizada_setor_audge = forms.CharField(required=False, label='Sigla do setor da auditoria central/geral')

    permite_integracao_com_ponto = forms.BooleanField(label='Permite integração com o módulo do ponto', required=False)
    permite_integracao_com_ponto_valida_ponto = forms.BooleanField(label='Verifica pendências no ponto do servidor', required=False)

    permite_integracao_com_plan_estrategico = forms.BooleanField(label='Permite integração com o módulo do planejamento estratégico', required=False)
    permite_integracao_com_pde = forms.BooleanField(label='Permite integração com os módulos de processos e documentos eletrônicos', required=False)

    afastamentos_pgd_exterior = forms.MultipleModelChoiceFieldPlus(
        label='Afastamentos que representam o PGD no Exterior',
        queryset=AfastamentoSiape.objects,
        required=False,
        help_text='Escolha os afastamentos do SIAPE que serão a representação de que o servidor está em PGD no Exterior. Esses afastamentos irão auxiliar o servidor no preenchimento do PIT permitindo que ele informe 100% de teletrabalho.',
    )

    afastamentos_pgd_exterior_tipo1 = forms.MultipleModelChoiceFieldPlus(
        label='API PGD 2 - Afastamentos que representam o PGD no Exterior - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)',
        queryset=AfastamentoSiape.objects,
        required=False,
        help_text='Apenas os afastamentos relacionados a "Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)".',
    )

    afastamentos_pgd_exterior_tipo2 = forms.MultipleModelChoiceFieldPlus(
        label='API PGD 2 - Afastamentos que representam o PGD no Exterior - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)',
        queryset=AfastamentoSiape.objects,
        required=False,
        help_text='Apenas os afastamentos relacionados a "Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)".',
    )

    api_padrao_sigla_setor = forms.ChoiceField(
        choices=[
            [1, 'SETOR/UO ou SETOR-UO'],
            [2, 'UO/SETOR ou UO-SETOR'],
        ],
        label='Padrão de sigla de setor',
        required=True,
        help_text='Escolha um padrão que seja o mais adequado para as siglas do seu setor. ',
    )

    metodo_obter_codigo_siape_setor = forms.ChoiceField(
        choices=[
            [1, '[1] Obter código SIAPE relacionando setor SUAP x SIAPE pela sigla (método padrão)'],
            [2, '[2] Obter código SIAPE direto do setor SIAPE (caso utilize árvore SIAPE)'],
            [3, '[3] Obter código SIAPE considerando relação setor SUAP x SIAPE conferida manualmente.'],
        ],
        label='Método para obter código siape de um setor',
        required=True,
    )

    timeout = forms.IntegerField(label='Timeout para envio dos dados', required=True)
    max_workers = forms.IntegerField(label='Max workers para envio dos dados', required=True)

    permite_habilitacao_dos_setores = forms.BooleanField(label='Permite o bloqueio das ações PGD dos setores não habilitados no PGD', required=False)

    justificativa_desligamento_automatico = forms.ModelChoiceFieldPlus(
        label='Justificativa que será utilizada para o desligamento automático do servidor',
        queryset=JustificativaDesligamentoPgd.objects,
        required=False,
    )

    def clean(self):
        permite_auditoria_centralizada = self.cleaned_data.get('permite_auditoria_centralizada')
        auditoria_centralizada_setor_audge = self.cleaned_data.get('auditoria_centralizada_setor_audge')
        if permite_auditoria_centralizada and not auditoria_centralizada_setor_audge:
            raise forms.ValidationError('Informe a sigla do setor responsável pela auditoria centralizada.')
        if auditoria_centralizada_setor_audge and not permite_auditoria_centralizada:
            raise forms.ValidationError('Ative a auditoria centralizada para informar a sigla do setor responsável pela auditoria.')

        permite_integracao_com_ponto = self.cleaned_data.get('permite_integracao_com_ponto')
        permite_integracao_com_ponto_valida_ponto = self.cleaned_data.get('permite_integracao_com_ponto_valida_ponto')
        if not permite_integracao_com_ponto and permite_integracao_com_ponto_valida_ponto:
            raise forms.ValidationError('Para verificar pendências no ponto, ative primeiro a integração com o módulo do ponto.')

        if not self.cleaned_data.get('timeout') > 0:
            raise forms.ValidationError('Informe um tempo limite maior que zero.')

        if not (self.cleaned_data.get('max_workers') > 0 and self.cleaned_data.get('max_workers') <= 10):
            raise forms.ValidationError('Informe de 1 a 10 processos simultâneos.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        afastamentos_pgd_exterior = Configuracao.get_valor_por_chave(app='pgd2', chave='afastamentos_pgd_exterior')
        self.fields['afastamentos_pgd_exterior'].initial = list(afastamentos_pgd_exterior.split(',')) if afastamentos_pgd_exterior else []


# ====================================================
# GERAL
# ====================================================
class ConfirmacaoComSenhaForm(forms.FormPlus):
    confirmacao = forms.BooleanField(label='Confirmo a operação.', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class JustificativaComSenhaForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class JustificativaObrigatoriaComSenhaForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class JustificativaComSenhaIrreversivelForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação e estou ciente de que é IRREVERSSÍVEL', initial=False, required=True)
    senha = forms.PasswordField()


class ComfirmacaoComSenhaIrreversivelForm(forms.FormPlus):
    confirmacao = forms.BooleanField(label='Confirmo esta operação e estou ciente de que é IRREVERSSÍVEL', initial=False, required=True)
    senha = forms.PasswordField()


# ====================================================
# CADASTROS BÁSICOS
# ====================================================


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

        if not eh_sistemica and not campus_abragencia:
            raise ValidationError('Selecione ao menos um campus para definir a abrangência da comissão.')

        # Uma comissão Sistêmica não pode ter campus_abragencia
        if eh_sistemica and campus_abragencia:
            raise ValidationError('Uma comissão sistêmica abrange toda a instituição. Remova os campi selecionados.')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('Informe uma data inicial anterior ou igual à data final.')

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
                raise ValidationError('O período informado se sobrepõe ao de outra comissão com a mesma abrangência. Escolha outras datas.')


class ConfiguracaoOrientacaoPlanoEntregasSetorialForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoOrientacaoPlanoEntregasSetorial
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

        if not eh_sistemica and not campus_abragencia:
            raise ValidationError('Selecione ao menos um campus para definir a abrangência da orientação.')

        # Uma comissão Sistêmica não pode ter campus_abragencia
        if eh_sistemica and campus_abragencia:
            raise ValidationError('Uma orientação sistêmica vale para toda a instituição. Remova os campi selecionados.')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('Informe uma data inicial anterior ou igual à data final.')

        # Não permite choque entre periodos para as mesmas UOs ou Sistêmica
        if not cancelado and data_inicio:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = ConfiguracaoOrientacaoPlanoEntregasSetorial.objects.exclude(cancelado=True)
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
                raise ValidationError('O período informado se sobrepõe ao de outra orientação com a mesma abrangência. Escolha outras datas.')


class DocumentoAdesaoServidorForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAdesaoServidor
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'] = TinyMCEFormField(label='Descrição')


class ConfiguracaoPerfilServidorForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoPerfilServidor
        exclude = ()

    def clean(self):
        deve_ter_funcao = self.cleaned_data.get('deve_ter_funcao')
        funcoes = self.cleaned_data.get('funcoes')

        # Se deve ter obrigatoriamente funcao deve dizer quais
        if deve_ter_funcao and not (funcoes):
            raise ValidationError('Selecione as funções que o servidor precisa exercer.')


class DocumentoAdesaoPesServidorForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAdesaoPesServidor
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'] = TinyMCEFormField(label='Descrição')


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

        if not eh_sistemica and not campus_abragencia:
            raise ValidationError('Selecione ao menos um campus para definir a abrangência da orientação.')

        # Uma comissão Sistêmica não pode ter campus_abragencia
        if eh_sistemica and campus_abragencia:
            raise ValidationError('Uma orientação sistêmica vale para toda a instituição. Remova os campi selecionados.')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('Informe uma data inicial anterior ou igual à data final.')

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
                raise ValidationError('O período informado se sobrepõe ao de outra orientação com a mesma abrangência. Escolha outras datas.')


class PeriodoPesForm(forms.ModelFormPlus):
    class Meta:
        model = PeriodoPes
        exclude = ()

    def clean(self):
        cancelado = self.cleaned_data.get('cancelado')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('Informe uma data inicial anterior ou igual à data final.')

        # Não permite choque entre periodos
        if not cancelado:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = PeriodoPes.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.instance.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (data_inicio, data_fim) if data_fim else (data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('O período informado se sobrepõe a outro calendário de PES. Escolha outras datas.')


class PeriodoPitRitForm(forms.ModelFormPlus):
    periodo_pes = forms.ModelChoiceField(
        label='Calendário PES',
        queryset=PeriodoPes.objects.filter(cancelado=False).order_by('data_inicio'),
        widget=AutocompleteWidget(search_fields=['titulo', 'data_inicio', 'data_fim']),
    )

    class Meta:
        model = PeriodoPitRit
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_prazo_entrega_pit'].required = True
        self.fields['data_prazo_entrega_rit'].required = True
        self.fields['data_prazo_homologacao_pit'].required = True
        self.fields['data_prazo_homologacao_rit'].required = True

    def clean(self):
        cancelado = self.cleaned_data.get('cancelado')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('Informe uma data inicial anterior ou igual à data final.')

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
                raise ValidationError('O período informado se sobrepõe a outro calendário de PIT/RIT. Escolha outras datas.')


# ====================================================
# PES - Plano de Entregas Setorial
# ====================================================


class PlanoEntregasSetorialAddForm(forms.ModelFormPlus):
    setor = forms.ModelChoiceFieldPlus(get_setores_pgd(), widget=AutocompleteWidget(multiple=False), label='Setor', required=True)
    periodo_pes = forms.ModelChoiceField(
        label='Calendário de PES',
        queryset=PeriodoPes.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(search_fields=['titulo', 'data_inicio', 'data_fim']),
    )

    class Meta:
        model = PlanoEntregasSetorial
        fields = ('periodo_pes', 'setor')

    def clean(self):
        periodo_pes = self.cleaned_data.get('periodo_pes')
        setor = self.cleaned_data.get('setor')
        pode, erros = PlanoEntregasSetorial.pode_cadastrar(setor, periodo_pes, self.request.user, retornar_lista_erros=True)
        if not pode:
            raise ValidationError(mark_safe('</br>'.join(erros)))


class PlanoEntregasSetorialEditarDocumentacaoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoEntregasSetorial
        fields = ('doc_percentual_maximo_teletrabalho', 'doc_insfraestrutura', 'doc_tecnica')

    def clean(self):
        doc_percentual_maximo_teletrabalho = self.cleaned_data.get('doc_percentual_maximo_teletrabalho')

        if not doc_percentual_maximo_teletrabalho or not (0 <= doc_percentual_maximo_teletrabalho <= 100):
            raise ValidationError('Informe o percentual máximo de teletrabalho com um valor entre 0 e 100.')


class PlanoEntregasSetorialHorarioFuncionamentoSetorCadastrarForm(forms.ModelFormPlus):
    recorrencia_dias_semana = forms.MultipleChoiceField(
        label='Repetir toda', choices=DiaSemanaChoices.DIAS_RESUMIDO_CHOICES, widget=forms.CheckboxSelectMultiplePlus, required=False
    )

    data_ate = forms.DateFieldPlus(label='Repetir até', required=False)

    fieldsets = (
        ('Dados', {'fields': ('pes', 'data', 'hora_inicio', 'hora_final')}),
        ('Recorrência', {'fields': ('recorrencia_dias_semana', 'data_ate')}),
    )

    class Meta:
        model = PlanoEntregasSetorialHorarioFuncionamentoSetor
        exclude = ('timestamp_data_hora_inicio',)

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)
        super().__init__(*args, **kwargs)
        self.fields['pes'].initial = self.pes.id
        self.fields['pes'].widget = forms.HiddenInput()

    def clean(self):
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')

        # É preciso informar uma data_ate para selecionar dias
        if recorrencia_dias_semana and not data_ate:
            raise ValidationError('Informe a data final da recorrência para repetir o horário nos dias selecionados.')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('Informe um horário de término posterior ao horário de início.')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.get_data_inicio() <= data <= self.pes.get_data_fim()):
            raise ValidationError('A data do horário deve estar dentro do período do PES.')

        # A data até deve ser maior ou igual a data  informada no cadastro
        if data_ate and data and not (data_ate >= data):
            raise ValidationError('A data final da recorrência deve ser igual ou posterior à data do primeiro horário.')

        # A data até deve estar dentro do período do PES
        if data_ate and not (self.pes.get_data_inicio() <= data_ate <= self.pes.get_data_fim()):
            raise ValidationError('A data final da recorrência deve estar dentro do período do PES.')

        if data:
            if data_ate:
                pode, erro = PlanoEntregasSetorialHorarioFuncionamentoSetor.validar_cadastro_recorrente(
                    self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana
                )
                if not pode:
                    raise ValidationError(erro)
            else:
                pode, erro = PlanoEntregasSetorialHorarioFuncionamentoSetor.validar_cadastro(self.pes, data, hora_inicio, hora_final)
                if not pode:
                    raise ValidationError(erro)

    def save(self, *args, **kwargs):
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        if recorrencia_dias_semana or data_ate:
            # Cadastra Este e a Recorrência
            hora_final = self.cleaned_data.get('hora_final')
            data_ate = self.cleaned_data.get('data_ate')
            PlanoEntregasSetorialHorarioFuncionamentoSetor.cadastrar_recorrente(
                self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana
            )
            return None
        # Cadastra Este
        self.instance.timestamp_data_hora_inicio = datetime.datetime(
            data.year, data.month, data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        obj = super().save(*args, **kwargs)
        return obj


class PlanoEntregasSetorialHorarioFuncionamentoSetorEditarForm(forms.ModelFormPlus):
    TIPO_EDICAO_CHOICE = (
        ('este', 'Apenas este'),
        ('este_e_proximos', 'Este e os próximos da recorrência'),
        ('este_e_anteriores', 'Este e os anteriores da recorrência'),
        ('todos', 'Todos da recorrência'),
    )
    tipo_edicao = forms.ChoiceField(widget=forms.RadioSelect(), required=False, label='Editar')

    class Meta:
        model = PlanoEntregasSetorialHorarioFuncionamentoSetor
        exclude = ('timestamp_data_hora_inicio',)

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)

        super().__init__(*args, **kwargs)

        self.fields['pes'].initial = self.pes.id
        self.fields['pes'].widget = forms.HiddenInput()
        self.fields['data'] = SpanField(widget=SpanWidget(), label='Data')
        self.fields['data'].widget.label_value = format_datetime(self.instance.data)
        self.fields['data'].widget.original_value = self.instance.data
        self.fields['data'].required = False

        if self.instance.recorrencia:
            self.fields['tipo_edicao'].widget = forms.RadioSelect()
            self.fields['tipo_edicao'].choices = self.TIPO_EDICAO_CHOICE
            self.fields['tipo_edicao'].required = True
            self.fields['tipo_edicao'].initial = 'este'
            self.fieldsets = (('Dados', {'fields': ('pes', 'data', 'hora_inicio', 'hora_final')}), ('Edição', {'fields': ('tipo_edicao',)}))
        else:
            self.fields['tipo_edicao'].widget = forms.HiddenInput()
            self.fields['tipo_edicao'].choices = []
            self.fields['tipo_edicao'].required = False
            self.fieldsets = (('Dados', {'fields': ('pes', 'data', 'hora_inicio', 'hora_final')}),)

    def clean(self):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        if (hora_inicio and hora_final) and (self.instance.hora_inicio == hora_inicio and self.instance.hora_final == hora_final):
            raise ValidationError('Nenhum dado foi alterado')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('A hora final deve ser maior que a inicial')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.get_data_inicio() <= data <= self.pes.get_data_fim()):
            raise ValidationError('A data inicial e final não podem extrapolar o período do PES.')

        if self.instance.recorrencia and tipo_edicao != 'este':
            pode, erro = PlanoEntregasSetorialHorarioFuncionamentoSetor.validar_alteracao_recorrente(
                self.pes, self.instance, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao
            )
            if not pode:
                raise ValidationError(erro)
        else:
            pode, erro = PlanoEntregasSetorialHorarioFuncionamentoSetor.validar_cadastro(self.pes, data, hora_inicio, hora_final, [self.instance.id])
            if not pode:
                raise ValidationError(erro)

    def save(self, *args, **kwargs):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        self.instance.recorrencia = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.get(id=self.instance.id).recorrencia

        if self.instance.recorrencia and tipo_edicao != 'este':
            PlanoEntregasSetorialHorarioFuncionamentoSetor.alterar_recorrente(self.instance, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao)
        else:
            obj = super().save(*args, **kwargs)
            return obj


class PlanoEntregasSetorialHorarioPlanejamentoSetorCadastrarForm(forms.ModelFormPlus):
    recorrencia_dias_semana = forms.MultipleChoiceField(
        label='Repetir toda', choices=DiaSemanaChoices.DIAS_RESUMIDO_CHOICES, widget=forms.CheckboxSelectMultiplePlus, required=False
    )

    data_ate = forms.DateFieldPlus(label='Repetir até', required=False)

    fieldsets = (
        ('Dados', {'fields': ('pes', 'data', 'hora_inicio', 'hora_final', 'reuniao')}),
        ('Recorrência', {'fields': ('recorrencia_dias_semana', 'data_ate')}),
    )

    class Meta:
        model = PlanoEntregasSetorialHorarioPlanejamentoSetor
        exclude = ('timestamp_data_hora_inicio',)

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)
        super().__init__(*args, **kwargs)
        self.fields['pes'].initial = self.pes.id
        self.fields['pes'].widget = forms.HiddenInput()

    def clean(self):
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')

        # É preciso informar uma data_ate para selecionar dias
        if recorrencia_dias_semana and not data_ate:
            raise ValidationError('Informe a data final da recorrência para repetir o horário nos dias selecionados.')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('Informe um horário de término posterior ao horário de início.')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.get_data_inicio() <= data <= self.pes.get_data_fim()):
            raise ValidationError('A data do horário deve estar dentro do período do PES.')

        # A data até deve ser maior ou igual a data  informada no cadastro
        if data_ate and data and not (data_ate >= data):
            raise ValidationError('A data final da recorrência deve ser igual ou posterior à data do primeiro horário.')

        # A data até deve estar dentro do período do PES
        if data_ate and not (self.pes.get_data_inicio() <= data_ate <= self.pes.get_data_fim()):
            raise ValidationError('A data final da recorrência deve estar dentro do período do PES.')

        if data:
            if data_ate:
                pode, erro = PlanoEntregasSetorialHorarioPlanejamentoSetor.validar_cadastro_recorrente(
                    self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana
                )
                if not pode:
                    raise ValidationError(erro)
            else:
                pode, erro = PlanoEntregasSetorialHorarioPlanejamentoSetor.validar_cadastro(
                    self.pes, data, hora_inicio, hora_final, [self.instance.id]
                )
                if not pode:
                    raise ValidationError(erro)

    def save(self, *args, **kwargs):
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        if recorrencia_dias_semana or data_ate:
            # Cadastra Este e a Recorrência
            hora_final = self.cleaned_data.get('hora_final')
            data_ate = self.cleaned_data.get('data_ate')
            reuniao = self.cleaned_data.get('reuniao')
            PlanoEntregasSetorialHorarioPlanejamentoSetor.cadastrar_recorrente(
                self.pes, data, hora_inicio, hora_final, data_ate, reuniao, recorrencia_dias_semana
            )
            return None
        # Cadastra Este
        self.instance.timestamp_data_hora_inicio = datetime.datetime(
            data.year, data.month, data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        obj = super().save(*args, **kwargs)
        return obj


class PlanoEntregasSetorialHorarioPlanejamentoSetorEditarForm(forms.ModelFormPlus):
    TIPO_EDICAO_CHOICE = (
        ('este', 'Apenas este'),
        ('este_e_proximos', 'Este e os próximos da recorrência'),
        ('este_e_anteriores', 'Este e os anteriores da recorrência'),
        ('todos', 'Todos da recorrência'),
    )
    tipo_edicao = forms.ChoiceField(widget=forms.RadioSelect(), required=False, label='Editar')

    class Meta:
        model = PlanoEntregasSetorialHorarioPlanejamentoSetor
        exclude = ('timestamp_data_hora_inicio',)

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)

        super().__init__(*args, **kwargs)

        self.fields['pes'].initial = self.pes.id
        self.fields['pes'].widget = forms.HiddenInput()
        self.fields['data'] = SpanField(widget=SpanWidget(), label='Data')
        self.fields['data'].widget.label_value = format_datetime(self.instance.data)
        self.fields['data'].widget.original_value = self.instance.data
        self.fields['data'].required = False
        self.fields['reuniao'] = SpanField(widget=SpanWidget(), label='Reunião')
        self.fields['reuniao'].widget.label_value = self.instance.get_reuniao_display()
        self.fields['reuniao'].widget.original_value = self.instance.reuniao
        self.fields['reuniao'].required = False

        if self.instance.recorrencia:
            self.fields['tipo_edicao'].widget = forms.RadioSelect()
            self.fields['tipo_edicao'].choices = self.TIPO_EDICAO_CHOICE
            self.fields['tipo_edicao'].required = True
            self.fields['tipo_edicao'].initial = 'este'
            self.fieldsets = (
                ('Dados', {'fields': ('pes', 'data', 'hora_inicio', 'hora_final', 'reuniao')}),
                ('Edição', {'fields': ('tipo_edicao',)}),
            )
        else:
            self.fields['tipo_edicao'].widget = forms.HiddenInput()
            self.fields['tipo_edicao'].choices = []
            self.fields['tipo_edicao'].required = False
            self.fieldsets = (('Dados', {'fields': ('pes', 'data', 'hora_inicio', 'hora_final', 'reuniao')}),)

    def clean(self):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        if (hora_inicio and hora_final) and (self.instance.hora_inicio == hora_inicio and self.instance.hora_final == hora_final):
            raise ValidationError('Nenhum dado foi alterado')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('A hora final deve ser maior que a inicial')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.get_data_inicio() <= data <= self.pes.get_data_fim()):
            raise ValidationError('A data inicial e final não podem extrapolar o período do PES.')

        if self.instance.recorrencia and tipo_edicao != 'este':
            pode, erro = PlanoEntregasSetorialHorarioPlanejamentoSetor.validar_alteracao_recorrente(
                self.pes, self.instance, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao
            )
            if not pode:
                raise ValidationError(erro)
        else:
            pode, erro = PlanoEntregasSetorialHorarioPlanejamentoSetor.validar_cadastro(self.pes, data, hora_inicio, hora_final, [self.instance.id])
            if not pode:
                raise ValidationError(erro)

    def save(self, *args, **kwargs):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        self.instance.recorrencia = PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.get(id=self.instance.id).recorrencia

        if self.instance.recorrencia and tipo_edicao != 'este':
            PlanoEntregasSetorialHorarioPlanejamentoSetor.alterar_recorrente(self.instance, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao)
        else:
            obj = super().save(*args, **kwargs)
            return obj


class PlanoEntregasSetorialEntregaCadastrarForm(forms.ModelFormPlus):
    atividade_processo_plan_estrategico = forms.MultipleModelChoiceField(
        AtividadeEtapa.objects, required=False, label='', widget=RenderableSelectMultiple('pgd2/templates/widgets/componentes_widget.html')
    )

    """
    fieldsets = (('Dados gerais', {'fields': ('pes', 'titulo', 'descricao', 'metrica', 'meta', 'data_prazo')}),
                 ('Critérios de avaliação', {'fields': ('criterios_avaliacao',)}),
                 ('Demandantes e Destinatários', {'fields': ('setores_demandantes', 'vinculos_demandantes', 'setores_destinatarios', 'vinculos_destinatarios')}),
                 ('Planejamento estratégico', {'fields': ('atividade_processo_plan_estrategico',)}),
                 )
    fieldsets = (('Dados gerais', {'fields': ('pes', 'titulo', 'descricao', 'metrica', 'meta', 'data_prazo')}),
                 ('Critérios de avaliação', {'fields': ('criterios_avaliacao',)}),
                 ('Demandantes e Destinatários', {'fields': ('setores_demandantes', 'vinculos_demandantes', 'setores_destinatarios', 'vinculos_destinatarios')}),
                 )
    """

    class Meta:
        model = PlanoEntregasSetorialEntregas
        exclude = ()

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)
        super().__init__(*args, **kwargs)
        self.fields['pes'].initial = self.pes.id
        self.fields['pes'].widget = forms.HiddenInput()
        self.fields['vinculos_demandantes'].queryset = Vinculo.objects.ativos()
        self.fields['vinculos_destinatarios'].queryset = Vinculo.objects.ativos()
        self.fields['setores_demandantes'].queryset = get_setores_pgd()
        self.fields['setores_destinatarios'].queryset = get_setores_pgd()

        self.fields['atividade_processo_plan_estrategico'].queryset = self.pes.get_atividades_plan_estrategico_relacionadas_ao_pes()

        if utilizar_integracao_com_plan_estrategico():
            self.fieldsets = (
                ('Dados gerais', {'fields': ('pes', 'titulo', 'descricao', 'metrica', 'meta', 'data_prazo')}),
                ('Critérios de avaliação', {'fields': ('criterios_avaliacao',)}),
                (
                    'Demandantes e Destinatários',
                    {'fields': ('setores_demandantes', 'vinculos_demandantes', 'setores_destinatarios', 'vinculos_destinatarios')},
                ),
                ('Planejamento estratégico', {'fields': ('atividade_processo_plan_estrategico',)}),
            )
        else:
            self.fieldsets = (
                ('Dados gerais', {'fields': ('pes', 'titulo', 'descricao', 'metrica', 'meta', 'data_prazo')}),
                ('Critérios de avaliação', {'fields': ('criterios_avaliacao',)}),
                (
                    'Demandantes e Destinatários',
                    {'fields': ('setores_demandantes', 'vinculos_demandantes', 'setores_destinatarios', 'vinculos_destinatarios')},
                ),
            )

        self.fields['metrica'].required = True
        self.fields['meta'].required = True
        self.fields['meta_analise'].required = False
        self.fields['entrega_analise'].required = False

    def clean(self):
        if not self.cleaned_data.get('meta') or not self.cleaned_data.get('metrica'):
            raise ValidationError('Informe a métrica e a meta da entrega.')
        if self.cleaned_data.get('data_prazo'):
            if not (self.pes.periodo_pes.data_inicio <= self.cleaned_data.get('data_prazo') <= self.pes.periodo_pes.data_fim):
                raise ValidationError('Informe um prazo dentro do período do planejamento.')
        if self.cleaned_data.get('meta'):
            if not self.cleaned_data.get('meta') > 0:
                raise ValidationError('Informe uma meta maior que zero.')
        if self.cleaned_data.get('metrica') == PlanoEntregasSetorialEntregas.QUANTIDADE and not self.cleaned_data.get('meta') % 1 == 0:
            raise ValidationError('Para a métrica de quantidade, informe a meta como um número inteiro.')
        if self.cleaned_data.get('metrica') == PlanoEntregasSetorialEntregas.PERCENTUAL and self.cleaned_data.get('meta') > 100:
            raise ValidationError('Para a métrica percentual, informe uma meta entre 0 e 100.')


class PlanoEntregasSetorialEditarAuxiliaresForm(forms.ModelFormPlus):
    auxiliares = forms.MultipleModelChoiceFieldPlus(label='Servidores', queryset=Vinculo.objects.servidores(), required=False)

    class Meta:
        model = PlanoEntregasSetorial
        fields = ('auxiliares',)


class AvaliacaoPesForm(forms.FormPlus):
    avaliacao_pes = forms.ChoiceField(
        label='Avaliar como:',
        widget=forms.RadioSelect(attrs={'class': 'checkboxes'}),
        required=True,
        choices=PlanoEntregasSetorial.AVALIACAO_PES_CHOICES,
        initial=PlanoEntregasSetorial.AVALIACAO_EXCEPCIONAL_PES,
    )

    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação e que estou de acordo com a execução do PES', initial=False, required=True)
    senha = forms.PasswordField()

    def clean(self):
        avaliacao_rit = int(self.cleaned_data.get('avaliacao_pes'))
        justificativa = self.cleaned_data.get('justificativa')
        if not justificativa and avaliacao_rit in [
            PlanoEntregasSetorial.AVALIACAO_EXCEPCIONAL_PES,
            PlanoEntregasSetorial.AVALIACAO_INADEQUADO_PES,
            PlanoEntregasSetorial.AVALIACAO_NAO_EXECUTADO_PES,
        ]:
            raise ValidationError(
                'É necessário informar a Justificativa/Observação para as seguintes avaliações: "Excepcional", "Inadequado" e Não executado '
            )


# ====================================================
# Adesão PGD
# ====================================================


class SolicitarAdesaoPgdForm(forms.ModelFormPlus):
    confirmacao = forms.BooleanField(
        label='Confirmo esta Solicitação de Adesão e estou de acordo com todas as regras aqui descritas', initial=False, required=True
    )
    senha = forms.PasswordField()

    class Meta:
        model = SolicitacaoAdesaoServidor
        fields = ('preferencia_contato', 'telefone', 'codigo_contato_pais')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['telefone'].required = True
        self.fields['preferencia_contato'].required = True


class EditarTelefonePgdForm(forms.ModelFormPlus):
    telefone = forms.BrTelefoneField(label='Telefone para Contato PGD', max_length=14, widget=BrTelefoneWidget(), required=True)

    class Meta:
        model = SolicitacaoAdesaoServidor
        fields = ('preferencia_contato', 'telefone', 'codigo_contato_pais')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preferencia_contato'].required = True


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
                    'A data de efeitos não será retroativa e esta deve ser escolhida pela chefia em um intervalo de no mínimo 10 dias corridos pra frente e no máximo 30 dias.'
                )


class CadastrarDesligamentoGestaoPgdForm(forms.FormPlus):
    justificativa = forms.ModelChoiceFieldPlus(JustificativaDesligamentoPgd.objects.all(), label='Justificativa', required=True)
    data_desligamento_efeitos_a_partir_de = forms.DateFieldPlus(label='Com efeitos a partir de', required=True)
    observacao = forms.CharField(widget=forms.Textarea, required=False, label='Observação')

    confirmacao = forms.BooleanField(label='Confirmo o cadastro do Desligamento do PGD', initial=False, required=True)
    confirmacao2 = forms.BooleanField(initial=False, required=True)
    senha = forms.PasswordField()

    fieldsets = (
        ('Dados do desligamento', {'fields': ('justificativa', 'data_desligamento_efeitos_a_partir_de', 'observacao')}),
        ('Confirmações', {'fields': ('confirmacao', 'confirmacao2')}),
        ('Senha', {'fields': ('senha',)}),
    )

    def __init__(self, *args, **kwargs):
        self.lista_justificativas = kwargs.pop('lista_justificativas', None)
        super().__init__(*args, **kwargs)
        self.fields['justificativa'].queryset = self.lista_justificativas
        self.fields[
            'confirmacao2'
        ].label = f'Tem certeza que deseja cadastrar este desligamento com a data de efeitos informada mesmo considerando que a data de hoje é {format_datetime(get_datetime_now().date())}?'


class RemoverDesligamentoGestaoPgdForm(forms.FormPlus):
    observacao = forms.CharField(widget=forms.Textarea, required=False, label='Observação')

    senha = forms.PasswordField()


# ====================================================
# Adesão PES
# ====================================================


class SelecionarSetorForm(forms.FormPlus):
    setor = forms.ModelChoiceFieldPlus(get_setores_pgd(), widget=AutocompleteWidget(multiple=False), label='Setor', required=True)


class SolicitarAdesaoPesForm(forms.FormPlus):
    adesao_pgd = forms.ModelChoiceField(SolicitacaoAdesaoServidor.objects.all(), label='Selecione a adesão PGD', required=True)

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.adesoes_pgd = kwargs.pop('adesoes_pgd', None)
        super().__init__(*args, **kwargs)
        self.fields['adesao_pgd'].queryset = self.adesoes_pgd


# ====================================================
# PIT
# ====================================================


class CriarPitForm(forms.FormPlus):
    adesao_pgd = forms.ModelChoiceField(SolicitacaoAdesaoServidor.objects.all(), label='Selecione a adesão', required=True)

    periodo_pit_rit = forms.ModelChoiceField(
        label=f'Calendário {nomenclatura.pit_rit_pgd2}',
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(search_fields=['titulo', 'data_inicio', 'data_fim']),
    )

    # data_inicio = forms.DateFieldPlus(label='Data Início', required=True)

    confirmacao = forms.BooleanField(label='Confirmo este cadastro', initial=False, required=True)
    senha = forms.PasswordField()

    fieldsets = (
        ('Dados básicos', {'fields': ('adesao_pgd', 'periodo_pit_rit')}),
        ('Confirmação', {'fields': ('confirmacao', 'senha')}),
    )

    def __init__(self, *args, **kwargs):
        self.adesoes_pgd = kwargs.pop('adesoes_pgd', None)
        super().__init__(*args, **kwargs)
        self.fields['adesao_pgd'].queryset = self.adesoes_pgd


class EditarDadosBasicosPitForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalho
        fields = ('data_inicio', 'regime_execucacao', 'percentual_teletrabalho')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_inicio'].required = True

    def clean(self):
        nova_data_inicio = self.cleaned_data.get('data_inicio')
        novo_regime_execucacao = self.cleaned_data.get('regime_execucacao')
        novo_percentual_teletrabalho = self.cleaned_data.get('percentual_teletrabalho')

        if nova_data_inicio and novo_regime_execucacao and novo_percentual_teletrabalho:
            pode, erros = self.instance.validar_editar_dados_basicos(
                nova_data_inicio, novo_regime_execucacao, novo_percentual_teletrabalho, retornar_lista_erros=True
            )
            if not pode:
                strs = []
                c = 1
                for m in erros:
                    strs.append(f'({c}) {m}')
                    c += 1
                erro = ' / '.join(strs)
                raise forms.ValidationError(f'Erro ao editar dados básicos do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}: {erro}')
        return super().clean()


class EditarDadosBasicosPitCopiaForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoCopia
        fields = ('data_inicio', 'regime_execucacao', 'percentual_teletrabalho')

    def __init__(self, *args, **kwargs):
        self.pit = kwargs.pop('pit', False)
        super().__init__(*args, **kwargs)
        self.fields['data_inicio'].required = True

    def clean(self):
        nova_data_inicio = self.cleaned_data.get('data_inicio') or datetime.date.min
        novo_regime_execucacao = self.cleaned_data.get('regime_execucacao')
        novo_percentual_teletrabalho = self.cleaned_data.get('percentual_teletrabalho') or 200.0

        pode, erros = self.pit.validar_editar_dados_basicos(
            nova_data_inicio, novo_regime_execucacao, novo_percentual_teletrabalho, retornar_lista_erros=True
        )
        if not pode:
            strs = []
            c = 1
            for m in erros:
                strs.append(f'({c}) {m}')
                c += 1
            erro = ' / '.join(strs)
            raise forms.ValidationError(f'Erro ao editar dados básicos do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}: {erro}')
        return super().clean()


class PlanoIndividualTrabalhoPresencialCadastrarForm(forms.ModelFormPlus):
    recorrencia_dias_semana = forms.MultipleChoiceField(
        label='Repetir toda', choices=DiaSemanaChoices.DIAS_RESUMIDO_CHOICES, widget=forms.CheckboxSelectMultiplePlus, required=False
    )

    data_ate = forms.DateFieldPlus(label='Repetir até', required=False)

    fieldsets = (
        ('Dados', {'fields': ('pit', 'data', 'hora_inicio', 'hora_final')}),
        ('Recorrência', {'fields': ('recorrencia_dias_semana', 'data_ate')}),
    )

    class Meta:
        model = PlanoIndividualTrabalhoPresencial
        exclude = ('timestamp_data_hora_inicio',)

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)
        super().__init__(*args, **kwargs)
        self.fields['pit'].initial = self.pes.id
        self.fields['pit'].widget = forms.HiddenInput()

    def clean(self):
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')

        if not data or not hora_inicio or not hora_final:
            raise ValidationError('Preencha todos os campos obrigatórios.')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('A hora final deve ser maior que a inicial')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.data_inicio <= data <= self.pes.data_fim):
            raise ValidationError(f'A data inicial e final não podem extrapolar o período do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.')

        # A data até deve ser maior ou igual a data  informada no cadastro
        if data_ate and data and not (data_ate >= data):
            raise ValidationError('A "data até" deve ser maior ou igual a data informada.')

        # A data até deve estar dentro do período do PES
        if data_ate and not (self.pes.data_inicio <= data_ate <= self.pes.data_fim):
            raise ValidationError(f'A "data até" não pode extrapolar o período do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.')

        # É preciso informar uma data_ate para selecionar dias
        if recorrencia_dias_semana and not data_ate:
            raise ValidationError('Para selecionar dias para recorrência é necessário informar a data "Repetir até"')

        if data:
            if data_ate:
                pode, erro = PlanoIndividualTrabalhoPresencial.validar_cadastro_recorrente(
                    self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana
                )
                if not pode:
                    raise ValidationError(erro)
            else:
                pode, erro = PlanoIndividualTrabalhoPresencial.validar_cadastro(self.pes, data, hora_inicio, hora_final, [self.instance.id])
                if not pode:
                    raise ValidationError(erro)

    def save(self, *args, **kwargs):
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        if recorrencia_dias_semana or data_ate:
            # Cadastra Este e a Recorrência
            hora_final = self.cleaned_data.get('hora_final')
            data_ate = self.cleaned_data.get('data_ate')
            PlanoIndividualTrabalhoPresencial.cadastrar_recorrente(self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana)
            return None
        # Cadastra Este
        self.instance.timestamp_data_hora_inicio = datetime.datetime(
            data.year, data.month, data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        obj = super().save(*args, **kwargs)
        return obj


class PlanoIndividualTrabalhoPresencialEditarForm(forms.ModelFormPlus):
    TIPO_EDICAO_CHOICE = (
        ('este', 'Apenas este'),
        ('este_e_proximos', 'Este e os próximos da recorrência'),
        ('este_e_anteriores', 'Este e os anteriores da recorrência'),
        ('todos', 'Todos da recorrência'),
    )
    tipo_edicao = forms.ChoiceField(widget=forms.RadioSelect(), required=False, label='Editar')

    class Meta:
        model = PlanoIndividualTrabalhoPresencial
        exclude = ('timestamp_data_hora_inicio', 'pit')

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)

        super().__init__(*args, **kwargs)

        self.fields['data'] = SpanField(widget=SpanWidget(), label='Data')
        self.fields['data'].widget.label_value = format_datetime(self.instance.data)
        self.fields['data'].widget.original_value = self.instance.data
        self.fields['data'].required = False

        if self.instance.recorrencia:
            self.fields['tipo_edicao'].widget = forms.RadioSelect()
            self.fields['tipo_edicao'].choices = self.TIPO_EDICAO_CHOICE
            self.fields['tipo_edicao'].required = True
            self.fields['tipo_edicao'].initial = 'este'
            self.fieldsets = (('Dados', {'fields': ('data', 'hora_inicio', 'hora_final')}), ('Edição', {'fields': ('tipo_edicao',)}))
        else:
            self.fields['tipo_edicao'].widget = forms.HiddenInput()
            self.fields['tipo_edicao'].choices = []
            self.fields['tipo_edicao'].required = False
            self.fieldsets = (('Dados', {'fields': ('data', 'hora_inicio', 'hora_final')}),)

    def clean(self):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        if (hora_inicio and hora_final) and (self.instance.hora_inicio == hora_inicio and self.instance.hora_final == hora_final):
            raise ValidationError('Nenhum dado foi alterado')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('A hora final deve ser maior que a inicial')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.data_inicio <= data <= self.pes.data_fim):
            raise ValidationError(f'A data inicial e final não podem extrapolar o período do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.')

        if self.instance.recorrencia and tipo_edicao != 'este':
            pode, erro = PlanoIndividualTrabalhoPresencial.validar_alteracao_recorrente(
                self.pes, self.instance, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao
            )
            if not pode:
                raise ValidationError(erro)
        else:
            ids_ignore = []
            ids_ignore.append(self.instance.id)
            if self.instance.original:
                ids_ignore.append(self.instance.original.id)
            pode, erro = PlanoIndividualTrabalhoPresencial.validar_cadastro(self.pes, data, hora_inicio, hora_final, [self.instance.id])
            if not pode:
                raise ValidationError(erro)

    def save(self, *args, **kwargs):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        self.instance.recorrencia = PlanoIndividualTrabalhoPresencial.objects.get(id=self.instance.id).recorrencia
        instance_obj = self.instance

        # Cria copia para todos os obj se ele já tiver homologado for homologado e não tiver cópia
        if instance_obj.homologado:
            datas_criar_copia = PlanoIndividualTrabalhoPresencial.objects.filter(pit=instance_obj.pit, homologado=True)
            for original in datas_criar_copia:
                if not PlanoIndividualTrabalhoPresencial.objects.filter(original__id=original.id).exists():
                    copia = original
                    entrega_original = PlanoIndividualTrabalhoPresencial.objects.get(id=original.id)
                    copia.id = None
                    copia.homologado = False
                    copia.original = entrega_original
                    copia.save()
            instance_obj = PlanoIndividualTrabalhoPresencial.objects.filter(original__id=instance_obj.id).first()

        if self.instance.recorrencia and tipo_edicao != 'este':
            PlanoIndividualTrabalhoPresencial.alterar_recorrente(instance_obj, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao)
        else:
            instance_obj.hora_inicio = hora_inicio
            instance_obj.hora_final = hora_final
            instance_obj.alterado = True
            instance_obj.save()

        return instance_obj


class PlanoIndividualTrabalhoAtendimentoTeletrabalhoCadastrarForm(forms.ModelFormPlus):
    recorrencia_dias_semana = forms.MultipleChoiceField(
        label='Repetir toda', choices=DiaSemanaChoices.DIAS_RESUMIDO_CHOICES, widget=forms.CheckboxSelectMultiplePlus, required=False
    )

    data_ate = forms.DateFieldPlus(label='Repetir até', required=False)

    fieldsets = (
        ('Dados', {'fields': ('pit', 'data', 'hora_inicio', 'hora_final')}),
        ('Recorrência', {'fields': ('recorrencia_dias_semana', 'data_ate')}),
    )

    class Meta:
        model = PlanoIndividualTrabalhoAtendimento
        exclude = ('timestamp_data_hora_inicio',)

    def __init__(self, *args, **kwargs):
        self.pes = kwargs.pop('pes', False)
        super().__init__(*args, **kwargs)
        self.fields['pit'].initial = self.pes.id
        self.fields['pit'].widget = forms.HiddenInput()

    def clean(self):
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')

        if not data or not hora_inicio or not hora_final:
            raise ValidationError('Preencha todos os campos obrigatórios.')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('A hora final deve ser maior que a inicial')

        # Não pode ficar fora do período do PES
        if data and not (self.pes.data_inicio <= data <= self.pes.data_fim):
            raise ValidationError(f'A data inicial e final não podem extrapolar o período do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.')

        # A data até deve ser maior ou igual a data  informada no cadastro
        if data_ate and data and not (data_ate >= data):
            raise ValidationError('A "data até" deve ser maior ou igual a data informada.')

        # A data até deve estar dentro do período do PES
        if data_ate and not (self.pes.data_inicio <= data_ate <= self.pes.data_fim):
            raise ValidationError(f'A "data até" não pode extrapolar o período do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.')

        # É preciso informar uma data_ate para selecionar dias
        if recorrencia_dias_semana and not data_ate:
            raise ValidationError('Para selecionar dias para recorrência é necessário informar a data "Repetir até"')

        if data:
            if data_ate:
                pode, erro = PlanoIndividualTrabalhoAtendimento.validar_cadastro_recorrente(
                    self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana
                )
                if not pode:
                    raise ValidationError(erro)
            else:
                pode, erro = PlanoIndividualTrabalhoAtendimento.validar_cadastro(self.pes, data, hora_inicio, hora_final, [self.instance.id])
                if not pode:
                    raise ValidationError(erro)

    def save(self, *args, **kwargs):
        recorrencia_dias_semana = self.cleaned_data.get('recorrencia_dias_semana')
        data_ate = self.cleaned_data.get('data_ate')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        if recorrencia_dias_semana or data_ate:
            # Cadastra Este e a Recorrência
            hora_final = self.cleaned_data.get('hora_final')
            data_ate = self.cleaned_data.get('data_ate')
            PlanoIndividualTrabalhoAtendimento.cadastrar_recorrente(self.pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana)
            return None
        # Cadastra Este
        self.instance.timestamp_data_hora_inicio = datetime.datetime(
            data.year, data.month, data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        obj = super().save(*args, **kwargs)
        return obj


class PlanoIndividualTrabalhoAtendimentoTeletrabalhoEditarForm(forms.ModelFormPlus):
    TIPO_EDICAO_CHOICE = (
        ('este', 'Apenas este'),
        ('este_e_proximos', 'Este e os próximos da recorrência'),
        ('este_e_anteriores', 'Este e os anteriores da recorrência'),
        ('todos', 'Todos da recorrência'),
    )
    tipo_edicao = forms.ChoiceField(widget=forms.RadioSelect(), required=False, label='Editar')

    class Meta:
        model = PlanoIndividualTrabalhoAtendimento
        exclude = ('timestamp_data_hora_inicio', 'pit')

    def __init__(self, *args, **kwargs):
        self.pit = kwargs.pop('pit', False)

        super().__init__(*args, **kwargs)

        self.fields['data'] = SpanField(widget=SpanWidget(), label='Data')
        self.fields['data'].widget.label_value = format_datetime(self.instance.data)
        self.fields['data'].widget.original_value = self.instance.data
        self.fields['data'].required = False

        if self.instance.recorrencia:
            self.fields['tipo_edicao'].widget = forms.RadioSelect()
            self.fields['tipo_edicao'].choices = self.TIPO_EDICAO_CHOICE
            self.fields['tipo_edicao'].required = True
            self.fields['tipo_edicao'].initial = 'este'
            self.fieldsets = (('Dados', {'fields': ('data', 'hora_inicio', 'hora_final')}), ('Edição', {'fields': ('tipo_edicao',)}))
        else:
            self.fields['tipo_edicao'].widget = forms.HiddenInput()
            self.fields['tipo_edicao'].choices = []
            self.fields['tipo_edicao'].required = False
            self.fieldsets = (('Dados', {'fields': ('data', 'hora_inicio', 'hora_final')}),)

    def clean(self):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        if (hora_inicio and hora_final) and (self.instance.hora_inicio == hora_inicio and self.instance.hora_final == hora_final):
            raise ValidationError('Nenhum dado foi alterado')

        # Hora final maior que a final
        if (hora_inicio and hora_final) and not (hora_inicio < hora_final):
            raise ValidationError('A hora final deve ser maior que a inicial')

        # Não pode ficar fora do período do PIT
        if data and not (self.pit.data_inicio <= data <= self.pit.data_fim):
            raise ValidationError(f'A data inicial e final não podem extrapolar o período do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.')

        if self.instance.recorrencia and tipo_edicao != 'este':
            pode, erro = PlanoIndividualTrabalhoAtendimento.validar_alteracao_recorrente(
                self.instance, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao
            )
            if not pode:
                raise ValidationError(erro)
        else:
            ids_ignore = []
            ids_ignore.append(self.instance.id)
            if self.instance.original:
                ids_ignore.append(self.instance.original.id)
            pode, erro = PlanoIndividualTrabalhoAtendimento.validar_cadastro(self.pit, data, hora_inicio, hora_final, ids_ignore)
            if not pode:
                raise ValidationError(erro)

    def save(self, *args, **kwargs):
        tipo_edicao = self.cleaned_data.get('tipo_edicao')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_final = self.cleaned_data.get('hora_final')

        self.instance.recorrencia = PlanoIndividualTrabalhoAtendimento.objects.get(id=self.instance.id).recorrencia
        instance_obj = self.instance

        # Cria copia para todos os obj se ele já tiver homologado for homologado e não tiver cópia
        if instance_obj.homologado:
            datas_criar_copia = PlanoIndividualTrabalhoAtendimento.objects.filter(pit=instance_obj.pit, homologado=True)
            for original in datas_criar_copia:
                if not PlanoIndividualTrabalhoAtendimento.objects.filter(original__id=original.id).exists():
                    copia = original
                    entrega_original = PlanoIndividualTrabalhoAtendimento.objects.get(id=original.id)
                    copia.id = None
                    copia.homologado = False
                    copia.original = entrega_original
                    copia.save()
            instance_obj = PlanoIndividualTrabalhoAtendimento.objects.filter(original__id=instance_obj.id).first()

        if instance_obj.recorrencia and tipo_edicao != 'este':
            PlanoIndividualTrabalhoAtendimento.alterar_recorrente(instance_obj, hora_inicio, hora_final, tipo_recorrencia=tipo_edicao)
        else:
            instance_obj.hora_inicio = hora_inicio
            instance_obj.hora_final = hora_final
            instance_obj.alterado = True
            instance_obj.save()

        return instance_obj


def get_ext_combo_template_entrega_pes_pit(obj):
    return obj.get_verbose_para_pit()


class PlanoIndividualTrabalhoEntregasCadastrarForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoEntregas
        exclude = ('pit', 'cancelado', 'entrega_pes')

    def __init__(self, *args, **kwargs):
        self.pit = kwargs.pop('pit', False)
        super().__init__(*args, **kwargs)

    def clean(self):
        if self.cleaned_data.get('data_prazo'):
            data_ini = self.pit.data_inicio
            data_fim = self.pit.data_fim
            if not (data_ini <= self.cleaned_data.get('data_prazo') <= data_fim):
                raise ValidationError('Informe um prazo dentro do período do PIT.')

            # Se tiver desligamento na adesão
            if self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                if self.cleaned_data.get('data_prazo') >= self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                    raise ValidationError('O prazo da entrega deve ser anterior à data de início do desligamento.')


class PlanoIndividualTrabalhoEntregasEditarForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoEntregas
        exclude = ('pit', 'entrega_pes', 'cancelado')

    def __init__(self, *args, **kwargs):
        self.pit = kwargs.pop('pit', False)
        super().__init__(*args, **kwargs)

    def clean(self):
        if self.cleaned_data.get('data_prazo'):
            data_ini = self.pit.data_inicio
            data_fim = self.pit.data_fim
            if not (data_ini <= self.cleaned_data.get('data_prazo') <= data_fim):
                raise ValidationError('Informe um prazo dentro do período do PIT.')

            # Se tiver desligamento na adesão
            if self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                if self.cleaned_data.get('data_prazo') >= self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                    raise ValidationError('O prazo da entrega deve ser anterior à data de início do desligamento.')


class BuscarPitsChefeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    periodo_pit_rit = forms.ModelChoiceField(
        label=f'Calendário {nomenclatura.pit_rit_pgd2}',
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(
            search_fields=['titulo', 'data_inicio', 'data_fim'],
        ),
        required=False,
    )

    setor = forms.ModelChoiceFieldPlus(
        get_setores_pgd(),
        widget=AutocompleteWidget(multiple=False),
        label=f'Setor relacionado ao {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        required=False,
    )

    situacao = forms.ChoiceField(label='Situação', initial=None, required=False)

    def __init__(self, *args, **kwargs):
        self.setores = kwargs.pop('setores', None)

        super().__init__(*args, **kwargs)

        self.fields['situacao'].choices = [(None, '-------------'), *PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES]
        if self.setores:
            self.fields['setor'].queryset = get_setores_pgd().filter(id__in=self.setores.values_list('id'))


class BuscarPitsChefeFormSimples(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    periodo_pit_rit = forms.ModelChoiceField(
        label=f'Calendário {nomenclatura.pit_rit_pgd2}',
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(
            search_fields=['titulo', 'data_inicio', 'data_fim'],
        ),
        required=False,
    )

    setor = forms.ModelChoiceFieldPlus(
        get_setores_pgd(),
        widget=AutocompleteWidget(multiple=False),
        label=f'Setor relacionado ao {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        required=False,
    )

    situacao = forms.ChoiceField(label='Situação', initial=None, required=False)

    def __init__(self, *args, **kwargs):
        self.setores = kwargs.pop('setores', None)

        super().__init__(*args, **kwargs)

        self.fields['situacao'].choices = [(None, '-------------'), *PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES]
        if self.setores:
            self.fields['setor'].queryset = get_setores_pgd().filter(id__in=self.setores.values_list('id'))


class BuscarPitsChefeFormSimples2(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    periodo_pit_rit = forms.ModelChoiceField(
        label=f'Calendário {nomenclatura.pit_rit_pgd2}',
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(
            search_fields=['titulo', 'data_inicio', 'data_fim'],
        ),
        required=False,
    )


class BuscarNomeMatriculaServidorFormSimples(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)


class HomologarPitForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')

    confirmacao1 = forms.BooleanField(
        label=f'Confirmo Regime individual de execução no PGD informado no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(
        label=f'Confirmo % de Teletrabalho informado no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}', initial=False, required=True
    )
    confirmacao3 = forms.BooleanField(
        label=f'Confirmo Cronograma de Trabalho Presencial informado no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        initial=False,
        required=True,
    )
    confirmacao4 = forms.BooleanField(
        label=f'Confirmo Cronograma de Atendimento em Teletrabalho informado no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        initial=False,
        required=True,
    )
    confirmacao5 = forms.BooleanField(
        label=f'Confirmo Entregas informadas no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}', initial=False, required=True
    )

    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.habilita_confirmacao3 = kwargs.pop('habilita_confirmacao3', False)
        super().__init__(*args, **kwargs)
        if not self.habilita_confirmacao3:
            self.fields['confirmacao3'].widget = forms.HiddenInput()
            self.fields['confirmacao3'].required = False


# ====================================================
# RIT
# ====================================================


class RelatorioIndividualTrabalhoCadastrarForm(forms.ModelFormPlus):
    fieldsets = (
        ('Dados gerais', {'fields': ('titulo', 'descricao', 'data_inicio', 'data_fim', 'anexo')}),
        ('Execução', {'fields': ('tempo_executado', 'perc_executada_em_teletrabalho', 'quantidade_progresso')}),
    )

    class Meta:
        model = RelatorioIndividualTrabalho
        exclude = ('entrega_pit',)

    def __init__(self, *args, **kwargs):
        self.pit = kwargs.pop('pit', None)
        self.entrega_pes = kwargs.pop('entrega_pes', None)
        self.percentual_maximo_teletrabalho_inicial = kwargs.pop('percentual_maximo_teletrabalho_inicial', None)

        super().__init__(*args, **kwargs)

        if self.entrega_pes and self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE:
            self.fields['quantidade_progresso'].required = True
            self.fields['quantidade_progresso'] = forms.IntegerFieldPlus(label='Quantidade executada', required=True)
        else:
            self.fields['quantidade_progresso'].required = False
            self.fields['quantidade_progresso'].widget = forms.HiddenInput()

        self.fields['perc_executada_em_teletrabalho'].initial = self.percentual_maximo_teletrabalho_inicial

        # Se o servidor tiver regime 100% presencial não pode ter perc_executada_em_teletrabalho
        if self.pit.regime_execucacao == PlanoIndividualTrabalho.TRABALHO_PRESENCIAL:
            self.fields['perc_executada_em_teletrabalho'].widget = forms.HiddenInput()

    def clean_anexo(self):
        content = self.cleaned_data.get('anexo', None)
        full_check_file(content, check_required=False)
        return content

    def clean(self):
        if self.cleaned_data.get('perc_executada_em_teletrabalho') and self.cleaned_data.get('perc_executada_em_teletrabalho') > 100:
            raise ValidationError('O percentual executado em teletrabalho não pode ultrapassar 100%.')

        if self.cleaned_data.get('quantidade_progresso'):
            if (
                self.entrega_pes
                and self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.PERCENTUAL
                and self.cleaned_data.get('quantidade_progresso') > 100
            ):
                raise ValidationError('A execução percentual não pode ultrapassar 100% da meta do PES.')

            # Valida a quantidade_progresso de acordo com a métrica da entrega_pes relacionada
            if self.entrega_pes:
                if not self.cleaned_data.get('quantidade_progresso') > 0:
                    raise ValidationError('A quantidade executada deve ser maior que zero.')
                if (
                    self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE
                    and not self.cleaned_data.get('quantidade_progresso') % 1 == 0
                ):
                    raise ValidationError('Informe a quantidade executada como um número inteiro.')

        # Se for pra infomar periodo é preciso informar as duas
        if self.cleaned_data.get('data_inicio') or self.cleaned_data.get('data_fim'):
            if not (self.cleaned_data.get('data_inicio') and self.cleaned_data.get('data_fim')):
                raise ValidationError('Informe as datas de início e término da execução.')

            if not (self.cleaned_data.get('data_inicio') <= self.cleaned_data.get('data_fim')):
                raise ValidationError('A data de início da execução deve ser anterior ou igual à data de término.')

            data_ini_pit = self.pit.data_inicio
            data_fim_pit = self.pit.data_fim
            valida_dt_inicio = data_ini_pit <= self.cleaned_data.get('data_inicio') <= data_fim_pit
            valida_dt_fim = data_ini_pit <= self.cleaned_data.get('data_fim') <= data_fim_pit
            if not (valida_dt_inicio and valida_dt_fim):
                raise ValidationError('As datas de execução devem estar dentro do período do PIT.')

            # Se tiver desligamento na adesão
            if self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                if data_fim_pit >= self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                    raise ValidationError('O prazo não pode extrapolar a data da efetivação do Desligamento.')


class RelatorioIndividualTrabalhoEditarForm(forms.ModelFormPlus):
    fieldsets = (
        ('Dados gerais', {'fields': ('titulo', 'descricao', 'data_inicio', 'data_fim', 'anexo')}),
        ('Execução', {'fields': ('tempo_executado', 'perc_executada_em_teletrabalho', 'quantidade_progresso', 'quantidade_progresso_e')}),
    )

    class Meta:
        model = RelatorioIndividualTrabalho
        exclude = ('entrega_pit',)

    def __init__(self, *args, **kwargs):
        self.pit = kwargs.pop('pit', None)
        self.entrega_pes = kwargs.pop('entrega_pes', None)

        super().__init__(*args, **kwargs)

        self.fields['quantidade_progresso'].widget = forms.HiddenInput()
        self.fields['quantidade_progresso_e'] = forms.IntegerFieldPlus()
        if self.entrega_pes and self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE:
            self.fields['quantidade_progresso_e'] = forms.IntegerFieldPlus(
                label='Quantidade executada', required=True, initial=int(kwargs['instance'].quantidade_progresso)
            )
            self.fields['quantidade_progresso_e'].required = True
        else:
            self.fields['quantidade_progresso_e'].required = False
            self.fields['quantidade_progresso_e'].initial = 0
            self.fields['quantidade_progresso_e'].widget = forms.HiddenInput()

        # Se o servidor tiver regime 100% presencial não pode ter perc_executada_em_teletrabalho
        if self.pit.regime_execucacao == PlanoIndividualTrabalho.TRABALHO_PRESENCIAL:
            self.fields['perc_executada_em_teletrabalho'].widget = forms.HiddenInput()

    def clean_anexo(self):
        content = self.cleaned_data.get('anexo', None)
        full_check_file(content, check_required=False)
        return content

    def clean(self):
        if self.cleaned_data.get('perc_executada_em_teletrabalho') and self.cleaned_data.get('perc_executada_em_teletrabalho') > 100:
            raise ValidationError('O percentual executado em teletrabalho não pode ultrapassar 100%.')

        if self.cleaned_data.get('quantidade_progresso_e'):
            if (
                self.entrega_pes
                and self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.PERCENTUAL
                and self.cleaned_data.get('quantidade_progresso_e') > 100
            ):
                raise ValidationError('A execução percentual não pode ultrapassar 100% da meta do PES.')

            # Valida a quantidade_progresso de acordo com a métrica da entrega_pes relacionada
            if self.entrega_pes:
                if not self.cleaned_data.get('quantidade_progresso_e') > 0:
                    raise ValidationError('A quantidade executada deve ser maior que zero.')
                if (
                    self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE
                    and not self.cleaned_data.get('quantidade_progresso_e') % 1 == 0
                ):
                    raise ValidationError('Informe a quantidade executada como um número inteiro.')

        # Se for pra infomar periodo é preciso informar as duas
        if self.cleaned_data.get('data_inicio') or self.cleaned_data.get('data_fim'):
            if not (self.cleaned_data.get('data_inicio') and self.cleaned_data.get('data_fim')):
                raise ValidationError('Informe as datas de início e término da execução.')

            if not (self.cleaned_data.get('data_inicio') <= self.cleaned_data.get('data_fim')):
                raise ValidationError('A data de início da execução deve ser anterior ou igual à data de término.')

            data_ini_pit = self.pit.data_inicio
            data_fim_pit = self.pit.data_fim
            valida_dt_inicio = data_ini_pit <= self.cleaned_data.get('data_inicio') <= data_fim_pit
            valida_dt_fim = data_ini_pit <= self.cleaned_data.get('data_fim') <= data_fim_pit
            if not (valida_dt_inicio and valida_dt_fim):
                raise ValidationError('As datas de execução devem estar dentro do período do PIT.')

            # Se tiver desligamento na adesão
            if self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                if data_fim_pit >= self.pit.adesao.data_desligamento_efeitos_a_partir_de:
                    raise ValidationError('O prazo não pode extrapolar a data da efetivação do Desligamento.')


class BuscarRitsChefeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    periodo_pit_rit = forms.ModelChoiceField(
        label=f'Calendário {nomenclatura.pit_rit_pgd2}',
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(
            search_fields=['titulo', 'data_inicio', 'data_fim'],
        ),
        required=False,
    )

    setor = forms.ModelChoiceFieldPlus(
        get_setores_pgd(),
        widget=AutocompleteWidget(multiple=False),
        label=f'Setor relacionado ao {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        required=False,
    )

    situacao = forms.ChoiceField(label='Situação', initial=None, required=False)

    def __init__(self, *args, **kwargs):
        self.setores = kwargs.pop('setores', None)
        super().__init__(*args, **kwargs)

        self.fields['situacao'].choices = [(None, '-------------'), *PlanoIndividualTrabalho.SITUACAO_RIT_CHOICES]
        if self.setores:
            self.fields['setor'].queryset = get_setores_pgd().filter(id__in=self.setores.values_list('id'))


class BuscarRitsChefeFormSimples2(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    periodo_pit_rit = forms.ModelChoiceField(
        label=f'Calendário {nomenclatura.pit_rit_pgd2}',
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(
            search_fields=['titulo', 'data_inicio', 'data_fim'],
        ),
        required=False,
    )


class AvaliacaoRitForm(forms.FormPlus):
    MAX_TEMPO_HOMOLOGADO_EM_SEGUNDOS = 2147483647
    MAX_TEMPO_HOMOLOGADO_EM_HORAS = Decimal(MAX_TEMPO_HOMOLOGADO_EM_SEGUNDOS) / Decimal(3600)

    avaliacao_rit = forms.ChoiceField(
        label='Avaliar como:',
        widget=forms.RadioSelect(attrs={'class': 'checkboxes'}),
        required=True,
        choices=PlanoIndividualTrabalho.AVALIACAO_RIT_CHOICES,
        initial=PlanoIndividualTrabalho.AVALIACAO_EXCEPCIONAL_RIT,
    )

    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')
    tempo_homologado = forms.DecimalFieldPlus(initial='0,00', label='Tempo homologado (Em horas)', required=True)

    confirmacao = forms.BooleanField(
        label=f'Confirmo esta operação e que estou de acordo com as entregas informadas no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        initial=False,
        required=True,
    )
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.tempo_executado_total = kwargs.pop('tempo_executado_total', Decimal(0))
        super().__init__(*args, **kwargs)
        self.fields['tempo_homologado'].initial = self.tempo_executado_total

    def clean_tempo_homologado(self):
        tempo_homologado = self.cleaned_data.get('tempo_homologado')
        if tempo_homologado is None:
            return tempo_homologado
        if tempo_homologado < 0:
            raise ValidationError('O tempo homologado deve ser maior ou igual a 0.')
        if tempo_homologado > self.MAX_TEMPO_HOMOLOGADO_EM_HORAS:
            raise ValidationError('O tempo homologado excede o limite suportado para distribuição automática de horas.')
        return tempo_homologado


class DistribuirHorasAutoRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(
        label=f'Todas as distribuições de horas referentes a este {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} serão DESFEITAS e será realizada uma NOVA DISTRIBUIÇÃO.',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(
        label=f'Distribuir CH apenas para o período do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} (caso selecione esta opção o SUAP irá distribuir CH apenas para o período do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} não para irá distribuir para o semestre e para compensações específicas).',
        initial=False,
        required=False,
    )
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class DesfazerDistribuirHorasAutoRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(
        label=f'Todas as distribuições de horas referentes a este {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} serão DESFEITAS e deverá ser realizada uma NOVA DISTRIBUIÇÃO.',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA', initial=False, required=True)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class AjustarHorasSemestreRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(
        label=f'Todas as distribuições de horas referentes ao semestre deste {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} serão DESFEITAS e será realizada uma NOVA DISTRIBUIÇÃO.',
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
    confirmacao1 = forms.BooleanField(
        label=f'A distribuição de horas referente ao semestre deste {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} será DESFEITA.',
        initial=False,
        required=True,
    )
    confirmacao2 = forms.BooleanField(label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA', initial=False, required=True)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class DesfazerDistribuirHorasCompensacaoEspecificaRitForm(forms.FormPlus):
    confirmacao1 = forms.BooleanField(label='A distribuição de horas referente a compensação específica será DESFEITA.', initial=False, required=True)
    confirmacao2 = forms.BooleanField(label='Estou ciente de que esta operação É DEFINITIVA e NÃO PODE SER DESFEITA', initial=False, required=True)
    confirmacao3 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class BuscarServidoresPgdForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )
    cargo_emprego = forms.ModelChoiceFieldPlus(
        queryset=CargoEmprego.utilizados.all(), widget=AutocompleteWidget(multiple=False), label='Cargo emprego', required=False
    )
    jornada_trabalho = forms.ModelChoiceFieldPlus(
        queryset=JornadaTrabalho.objects.all(), widget=AutocompleteWidget(multiple=False), label='Jornada de trabalho', required=False
    )
    situacao = forms.ModelChoiceFieldPlus(
        queryset=Situacao.situacoes_usadas_no_instituto(), widget=AutocompleteWidget(multiple=False), label='Situação', required=False
    )

    def __init__(self, *args, **kwargs):
        self.setores_chefe = kwargs.pop('setores_chefe', None)
        super().__init__(*args, **kwargs)
        if self.setores_chefe:
            self.fields['setor'].queryset = self.setores_chefe


class BuscarServidoresApiPgdForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False
    )


class BuscarPitsPgdForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )

    periodo = forms.ModelChoiceField(
        label='Período',
        required=False,
        queryset=PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(search_fields=['titulo', 'data_inicio', 'data_fim']),
    )

    def __init__(self, *args, **kwargs):
        self.setores_chefe = kwargs.pop('setores_chefe', None)
        super().__init__(*args, **kwargs)
        if self.setores_chefe:
            self.fields['setor'].queryset = self.setores_chefe


class BuscarAdesoesPgdVisaoGeralForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(queryset=get_setores_pgd(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False)

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.campis = kwargs.pop('campis', None)
        super().__init__(*args, **kwargs)
        if self.campis:
            self.fields['campus'].queryset = self.campis


class BuscarServidoresPendenciaPgdForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos().all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.setores_chefe = kwargs.pop('setores_chefe', None)
        self.campis = kwargs.pop('campis', None)
        self.obrigatorio_campus = kwargs.pop('obrigatorio_campus', None)
        super().__init__(*args, **kwargs)
        if self.setores_chefe:
            self.fields['setor'].queryset = self.setores_chefe
        self.fields['campus'].queryset = self.campis
        self.fields['campus'].required = self.obrigatorio_campus


class BuscarSetoresPgdForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    setor = forms.ModelChoiceFieldPlus(queryset=get_setores_pgd(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False)

    def __init__(self, *args, **kwargs):
        self.setores_chefe = kwargs.pop('setores_chefe', None)
        super().__init__(*args, **kwargs)
        if self.setores_chefe:
            self.fields['setor'].queryset = get_setores_pgd().filter(id__in=self.setores_chefe.values('id'))


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
            raise forms.ValidationError('Como você respondeu "Não", informe o percentual de PGD que considera adequado para o seu setor.')

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
            raise forms.ValidationError('Como você respondeu "Não", informe o percentual de PGD que considera adequado para o seu setor.')

        pergunta_11 = self.cleaned_data.get('pergunta_11')
        pergunta_11_complemento = self.cleaned_data.get('pergunta_11_complemento')
        if pergunta_11 == RelatorioIndividualTrabalhoQuestionario.NAO and not pergunta_11_complemento:
            raise forms.ValidationError('Como você respondeu "Não", informe o percentual de PGD que considera adequado para o setor.')

        return self.cleaned_data


class BuscarRelatorioQuestionarioRitForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    periodo = forms.ChoiceField(label=f'Período {nomenclatura.pit_rit_pgd2}', required=True)

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
            d = f'{s.titulo} - ({format_datetime(s.data_inicio)} a {format_datetime(s.data_fim)})'
            lista_periodos.append((s.id, d))
        self.fields['periodo'].choices = lista_periodos

        if self.campis:
            self.fields['campus'].queryset = self.campis

        self.fields['pergunta'].choices = self.get_choices_perguntas()


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
                raise forms.ValidationError('O mês e ano finais devem ser iguais ou posteriores aos iniciais.')
            if not (relativedelta(data_final, data_inicio).months < 6):
                raise forms.ValidationError('Selecione um período de consulta de até 6 meses.')

        return self.cleaned_data


class BuscarAcompanhamentoPesPlanejamentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    FORMATO_CHOICE = (
        ('agrupado_por_periodo_pit', 'Agrupado por período'),
        ('lista', 'Lista'),
    )
    formato = forms.ChoiceField(
        widget=forms.RadioSelect(), required=True, label='Formato', initial='agrupado_por_periodo_pit', choices=FORMATO_CHOICE
    )

    servidores = forms.MultipleModelChoiceFieldPlus(label='Servidores', queryset=Servidor.objects.vinculados(), required=False)

    def __init__(self, *args, **kwargs):
        self.servidores_relacionados = kwargs.pop('servidores_relacionados', None)
        super().__init__(*args, **kwargs)
        if self.servidores_relacionados:
            self.fields['servidores'].queryset = self.servidores_relacionados


class BuscarAcompanhamentoPesExecucaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    servidores = forms.MultipleModelChoiceFieldPlus(label='Servidores', queryset=Servidor.objects.vinculados(), required=False)
    entrega_pes = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        self.servidores_relacionados = kwargs.pop('servidores_relacionados', None)
        self.entrega_pes = kwargs.pop('entrega_pes', None)
        super().__init__(*args, **kwargs)
        if self.servidores_relacionados:
            self.fields['servidores'].queryset = self.servidores_relacionados


class AnaliseSimplificadaExecucaoPesForm(forms.FormPlus):
    observacao = forms.CharField(
        widget=forms.Textarea, required=False, label='Observações', help_text='Pode ser visualizada por quem vai avaliar a execução do PES'
    )

    confirmacao_servidor_sem_rit_homologado = forms.BooleanField(
        label='Confirmo que existem alguns servidores com RIT não homologado para o período do PES', initial=False, required=True
    )

    confirmacao_execucao_total = forms.BooleanField(
        label='Confirmo que todas as entregas do PES foram Executadas Totalmente', initial=False, required=True
    )

    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.tem_servidor_sem_rit_homologado = kwargs.pop('tem_servidor_sem_rit_homologado', False)
        super().__init__(*args, **kwargs)
        if not self.tem_servidor_sem_rit_homologado:
            self.fields['confirmacao_servidor_sem_rit_homologado'].widget = forms.HiddenInput()
            self.fields['confirmacao_servidor_sem_rit_homologado'].required = False


class AnaliseCompletaExecucaoPesForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoEntregasSetorialEntregas
        fields = ('entrega_analise', 'meta_analise', 'observacao_analise')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['meta_analise'].required = True
        if self.instance.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE:
            self.fields['meta_analise'] = forms.IntegerFieldPlus(label='Quantidade executada', required=True)
        elif self.instance.metrica == PlanoEntregasSetorialEntregas.PERCENTUAL:
            self.fields['meta_analise'] = forms.DecimalFieldPlus(label='Percentual executado', required=True)

    def clean(self):
        entrega_analise = self.cleaned_data.get('entrega_analise')
        observacao_analise = self.cleaned_data.get('observacao_analise')

        if (
            self.cleaned_data.get('meta_analise')
            and self.instance.metrica == PlanoEntregasSetorialEntregas.PERCENTUAL
            and (self.cleaned_data.get('meta_analise') < 0 or self.cleaned_data.get('meta_analise') > 100)
        ):
            raise ValidationError('O percentual executado deve ser entre 0 e 100.')

        if (
            entrega_analise in [PlanoEntregasSetorialEntregas.EXECUTADA_PARCIALMENTE, PlanoEntregasSetorialEntregas.EXECUTADA_NAO]
            and not observacao_analise
        ):
            raise forms.ValidationError(
                'Para analisar como "Executada Parcialmente" ou "Não Executada" é necessário informar uma "Justificativa/Observação"'
            )

        return self.cleaned_data


class AnaliseDetalhadaExecucaoPesForm(forms.FormPlus):
    observacao = forms.CharField(
        widget=forms.Textarea, required=False, label='Observações', help_text='Pode ser visualizada por quem vai avaliar a execução do PES'
    )

    confirmacao_servidor_sem_rit_homologado = forms.BooleanField(
        label='Confirmo que existem alguns servidores com RIT não homologado para o período do PES', initial=False, required=True
    )

    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.tem_servidor_sem_rit_homologado = kwargs.pop('tem_servidor_sem_rit_homologado', False)
        super().__init__(*args, **kwargs)
        if not self.tem_servidor_sem_rit_homologado:
            self.fields['confirmacao_servidor_sem_rit_homologado'].widget = forms.HiddenInput()
            self.fields['confirmacao_servidor_sem_rit_homologado'].required = False


class AvaliacaoRitLoteForm(forms.FormPlus):
    avaliacao_rit = forms.ChoiceField(
        label='Avaliar como:',
        widget=forms.RadioSelect(attrs={'class': 'checkboxes'}),
        required=True,
        choices=PlanoIndividualTrabalho.AVALIACAO_RIT_CHOICES,
        initial=PlanoIndividualTrabalho.AVALIACAO_EXCEPCIONAL_RIT,
    )

    justificativa = forms.CharField(widget=forms.Textarea, required=False, label='Justificativa/Observação')

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.lista_pits_homologacao_deve = kwargs.pop('lista_pits_homologacao_deve', None)

        super().__init__(*args, **kwargs)

        if not self.lista_pits_homologacao_deve:
            self.fields['avaliacao_rit'].widget = forms.HiddenInput()
            self.fields['avaliacao_rit'].required = False
            self.fields['justificativa'].widget = forms.HiddenInput()
            self.fields['justificativa'].required = False

    def clean(self):
        if self.lista_pits_homologacao_deve:
            avaliacao_rit = int(self.cleaned_data.get('avaliacao_rit'))
            justificativa = self.cleaned_data.get('justificativa')
            if not justificativa and avaliacao_rit in [
                PlanoIndividualTrabalho.AVALIACAO_EXCEPCIONAL_RIT,
                PlanoIndividualTrabalho.AVALIACAO_INADEQUADO_RIT,
                PlanoIndividualTrabalho.AVALIACAO_NAO_EXECUTADO_RIT,
            ]:
                raise ValidationError(
                    'É necessário informar a Justificativa/Observação para as seguintes avaliações: "Excepcional", "Inadequado" e Não executado '
                )


class AvaliacaoPitLoteForm(forms.FormPlus):
    confirmacao = forms.BooleanField(
        label='Confirmo que TODAS as informações dos selecionados serão Aprovadas/Homologadas', initial=False, required=True
    )
    confirmacao2 = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()


class CopiarPesForm(forms.FormPlus):
    pes_origem = forms.ModelChoiceFieldPlus(
        queryset=PlanoEntregasSetorial.objects,
        required=True,
        label='PEs que será copiado',
        widget=AutocompleteWidget(search_fields=['periodo_pes__data_inicio', 'periodo_pes__data_fim']),
    )
    confirmacao1 = forms.BooleanField(label='Substituir todas as entregas cadastradas', initial=False, required=True)
    confirmacao2 = forms.BooleanField(label='Substituir todos os auxiliares cadastrados', initial=False, required=True)

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.pess_podem_ser_copiados = kwargs.pop('pess_podem_ser_copiados', None)
        super().__init__(*args, **kwargs)
        self.fields['pes_origem'].queryset = self.pess_podem_ser_copiados


class CopiarPitForm(forms.FormPlus):
    SUBMIT_LABEL = 'Selecionar PIT'

    acao = forms.CharField(required=False, widget=forms.HiddenInput(), initial='selecionar_origem')
    pit_origem = forms.ModelChoiceFieldPlus(
        queryset=PlanoIndividualTrabalho.objects,
        required=True,
        label='PIT que será copiado',
        widget=AutocompleteWidget(search_fields=['data_inicio', 'data_fim']),
    )

    def __init__(self, *args, **kwargs):
        self.pits_podem_ser_copiados = kwargs.pop('pits_podem_ser_copiados', None)
        self.pit_destino = kwargs.pop('pit_destino', None)
        super().__init__(*args, **kwargs)
        self.fields['pit_origem'].queryset = self.pits_podem_ser_copiados
        if self.pit_destino and self.pits_podem_ser_copiados and not self.is_bound:
            primeiro_pit = self.pits_podem_ser_copiados.filter(periodo_pit_rit__periodo_pes=self.pit_destino.periodo_pit_rit.periodo_pes).first()
            if not primeiro_pit:
                primeiro_pit = self.pits_podem_ser_copiados.first()
            if primeiro_pit:
                self.fields['pit_origem'].initial = primeiro_pit.id


class CopiarPitRelacionarEntregasForm(forms.FormPlus):
    SUBMIT_LABEL = 'Copiar entregas'

    ACAO_SUBSTITUIR = 'substituir'
    ACAO_SUBSTITUIR_READEQUAR_CH = 'substituir_readequar_ch'
    ACAO_ADICIONAR = 'adicionar'
    ACAO_COPIA_CHOICES = [
        (ACAO_SUBSTITUIR, 'Substituir todas as entregas cadastradas'),
        (ACAO_SUBSTITUIR_READEQUAR_CH, 'Substituir todas as entregas cadastradas e readequar a carga horária do mês'),
        (ACAO_ADICIONAR, 'Somente adicionar novas tarefas'),
    ]

    acao = forms.CharField(required=False, widget=forms.HiddenInput(), initial='copiar')
    pit_origem = forms.ModelChoiceFieldPlus(queryset=PlanoIndividualTrabalho.objects, required=True)
    acao_copia = forms.ChoiceField(
        label='Ação',
        choices=ACAO_COPIA_CHOICES,
        initial=ACAO_SUBSTITUIR,
        help_text=(
            'Substituir: remove todas as entregas atuais e copia as selecionadas. '
            'Substituir e readequar CH: além de substituir, ajusta proporcionalmente os tempos planejados '
            'para aproximar a carga horária planejada da carga horária prevista do mês atual. '
            'Somente adicionar: mantém as entregas atuais e adiciona novas entregas copiadas.'
        ),
    )

    confirmacao = forms.BooleanField(label='Confirmo esta operação', initial=False, required=True)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.pit_destino = kwargs.pop('pit_destino', None)
        self.pit_origem = kwargs.pop('pit_origem', None)
        self.pits_podem_ser_copiados = kwargs.pop('pits_podem_ser_copiados', None)
        self.somente_mapeamento = kwargs.pop('somente_mapeamento', False)
        super().__init__(*args, **kwargs)
        self.fields['pit_origem'].queryset = self.pits_podem_ser_copiados
        self.fields['pit_origem'].widget = forms.HiddenInput()
        self.campos_mapeamento_nomes = []
        self.tem_mapeamento_entre_pes = False
        self.tem_entregas_destino_para_relacionar = True
        self.total_entregas_origem = 0
        self.total_entregas_pre_relacionadas = 0
        self.total_entregas_sem_relacao = 0

        if self.pit_origem:
            self.fields['pit_origem'].initial = self.pit_origem.id
            self.tem_mapeamento_entre_pes = self.pit_destino.periodo_pit_rit.periodo_pes_id != self.pit_origem.periodo_pit_rit.periodo_pes_id
            self._configurar_campos_mapeamento()

        if self.somente_mapeamento:
            campos_mapeamento = [nome_campo for _, nome_campo in self.campos_mapeamento_nomes]
            for nome_campo in ['acao', 'pit_origem', 'acao_copia', 'confirmacao', 'senha']:
                self.fields.pop(nome_campo, None)
            self.fieldsets = [
                (
                    None,
                    {
                        'description': 'Revise as sugestões abaixo apenas quando precisar ajustar a correlação das entregas.',
                        'fields': campos_mapeamento,
                    },
                )
            ]
        else:
            self.fieldsets = [
                (
                    None,
                    {
                        'fields': ['acao', 'pit_origem', 'acao_copia', 'confirmacao', 'senha'],
                    },
                )
            ]

    def _configurar_campos_mapeamento(self):
        entregas_origem = (
            self.pit_origem.get_entregas_pit_para_rit()
            .select_related('entrega_pes__pes')
            .order_by('entrega_pes__pes__setor__sigla', 'entrega_pes__titulo', 'titulo')
        )
        entregas_destino_ids = self.pit_destino.get_entregas_adicionar_pit().values_list('id', flat=True)
        entregas_destino = (
            PlanoEntregasSetorialEntregas.objects.filter(id__in=entregas_destino_ids).select_related('pes').order_by('pes__setor__sigla', 'titulo')
        )
        self.tem_entregas_destino_para_relacionar = entregas_destino.exists()

        entregas_destino_lista = list(entregas_destino)
        for entrega_origem in entregas_origem:
            nome_campo = f'entrega_pes_{entrega_origem.id}'
            self.fields[nome_campo] = forms.ModelChoiceFieldPlus(
                queryset=entregas_destino,
                required=False,
                label=f'Relacionar com a entrega do PES atual para "{entrega_origem.titulo}"',
                help_text='Deixe em branco para não copiar esta entrega.',
            )
            valor_inicial = self._get_entrega_pes_inicial(entrega_origem, entregas_destino_lista)
            self.fields[nome_campo].initial = valor_inicial
            self.campos_mapeamento_nomes.append((entrega_origem.id, nome_campo))
            if valor_inicial:
                self.total_entregas_pre_relacionadas += 1

        self.total_entregas_origem = len(self.campos_mapeamento_nomes)
        self.total_entregas_sem_relacao = self.total_entregas_origem - self.total_entregas_pre_relacionadas

    @staticmethod
    def _get_entrega_pes_inicial(entrega_origem, entregas_destino):
        if entrega_origem.entrega_pes_id:
            for entrega_destino in entregas_destino:
                if entrega_destino.id == entrega_origem.entrega_pes_id:
                    return entrega_destino.id

        titulo_origem = (entrega_origem.entrega_pes.titulo if entrega_origem.entrega_pes else entrega_origem.titulo) or ''
        titulo_origem = titulo_origem.strip().lower()
        for entrega_destino in entregas_destino:
            if entrega_destino.titulo and entrega_destino.titulo.strip().lower() == titulo_origem:
                return entrega_destino.id
        return None

    def clean(self):
        cleaned_data = super().clean()

        if not self.tem_entregas_destino_para_relacionar:
            raise ValidationError('Não há entregas do PES atual disponíveis para relacionar com as entregas do PIT de origem.')

        self.mapa_entregas_pes = {}
        for entrega_origem_id, nome_campo in self.campos_mapeamento_nomes:
            entrega_pes = cleaned_data.get(nome_campo)
            if entrega_pes:
                self.mapa_entregas_pes[entrega_origem_id] = entrega_pes.id

        return cleaned_data


class BuscarServidoresPublicoPgdForm(forms.FormPlus):
    # SUBMIT_LABEL = 'Buscar'
    # METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(queryset=Setor.objects.all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False)

    # campus = forms.ModelChoiceField(
    #    queryset=UnidadeOrganizacional.objects.uo().all(),
    #    widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
    #    label='Campus',
    #    required=True,
    # )
    campus = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=True)


class BuscarServidoresPgdGestaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    setor = forms.ModelChoiceFieldPlus(queryset=Setor.objects.all(), widget=AutocompleteWidget(multiple=False), label='Setor', required=False)

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.setores_chefe = kwargs.pop('setores_chefe', None)
        super().__init__(*args, **kwargs)
        if self.setores_chefe:
            self.fields['setor'].queryset = self.setores_chefe


class SetorHabilitacaoForm(forms.ModelFormPlus):
    class Meta:
        model = SetorHabilitacao
        exclude = ()

    def clean(self):
        setor = self.cleaned_data.get('setor')
        habilitado = self.cleaned_data.get('habilitado')

        if utilizar_integracao_com_pde() and habilitado:
            documentos = self.cleaned_data.get('documentos')
            processos = self.cleaned_data.get('processos')
            tem_documento = documentos and documentos.count() > 0
            tem_processo = processos and processos.count() > 0
            if not tem_documento and not tem_processo:
                raise forms.ValidationError('Anexe ao menos um processo ou documento para habilitar o setor.')

        api_gd_v2 = ApiPgd2V2()
        relacao_setor_siape_suap = api_gd_v2.get_codigo_siape_setor(setor)
        if not relacao_setor_siape_suap:
            raise forms.ValidationError(
                'Este setor não está relacionado a um setor do SIAPE. Cadastre essa relação no módulo PGD antes de habilitá-lo.'
            )

        return self.cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = get_setores_pgd()


def get_ext_combo_template_periodo_pes(obj):
    return f'{format_datetime(obj.data_inicio)} a {format_datetime(obj.data_fim)}'


class ConsultaMonitoramentoPes(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    regra = forms.ChoiceField(label='Regra', required=True, widget=forms.RadioSelect())

    uos = forms.MultipleModelChoiceFieldPlus(label='Campi', queryset=UnidadeOrganizacional.objects.suap().all(), required=False)
    setores = forms.MultipleModelChoiceFieldPlus(label='Setores', queryset=get_setores_pgd(), required=False)

    periodos_pes = forms.MultipleModelChoiceFieldPlus(
        label='Calendário PES',
        required=False,
        queryset=PeriodoPes.objects.filter(cancelado=False).order_by('-data_inicio'),
        widget=AutocompleteWidget(
            extraParams={'ext_combo_template': get_ext_combo_template_periodo_pes},
            search_fields=['titulo', 'data_inicio', 'data_fim'],
            multiple=True,
        ),
    )

    def __init__(self, *args, **kwargs):
        self.mon_coices = kwargs.pop('mon_coices', None)
        self.uos = kwargs.pop('uos', None)
        super().__init__(*args, **kwargs)
        self.fields['regra'].choices = self.mon_coices
        if self.uos:
            self.fields['uos'].queryset = self.uos
            self.fields['setores'].queryset = get_setores_pgd().filter(uo__in=self.uos)


class ConsultaMonitoramentoPit(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    regra = forms.ChoiceField(label='Regra', required=True, widget=forms.RadioSelect())
    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)
    uos = forms.MultipleModelChoiceFieldPlus(label='Campi', queryset=UnidadeOrganizacional.objects.suap().all(), required=False)
    setores = forms.MultipleModelChoiceFieldPlus(label='Setores', queryset=get_setores_pgd(), required=False)

    def __init__(self, *args, **kwargs):
        self.mon_coices = kwargs.pop('mon_coices', None)
        self.uos = kwargs.pop('uos', None)
        super().__init__(*args, **kwargs)
        self.fields['regra'].choices = self.mon_coices
        if self.uos:
            self.fields['uos'].queryset = self.uos
            self.fields['setores'].queryset = get_setores_pgd().filter(uo__in=self.uos)


class ConsultaMonitoramentoServidorSimples(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)
    setores = forms.MultipleModelChoiceFieldPlus(label='Setores', queryset=get_setores_pgd(), required=False)
    consulta = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        self.tipo_consulta = kwargs.pop('tipo_consulta', None)
        super().__init__(*args, **kwargs)
        self.fields['consulta'].initial = self.tipo_consulta
        self.fields['consulta'].widget = forms.HiddenInput()


class PGDExteriorForm(forms.ModelFormPlus):
    processo = forms.ModelChoiceFieldPlus(
        Processo.objects.all(),
        label='Processo Eletrônico PGD Exterior',
        widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS),
        required=True,
    )

    documento_eletronico = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects.finalizados(),
        label='Documento Eletrônico PGD Exterior',
        required=False,
    )

    class Meta:
        model = PGDExterior
        exclude = ()

    def clean(self):
        servidor = self.cleaned_data.get('servidor')
        cancelado = self.cleaned_data.get('cancelado')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        if servidor:
            adesao = SolicitacaoAdesaoServidor.get_vigentes(servidor.get_user())
            if not adesao:
                raise ValidationError('Servidor deve ter adesão vigente.')

        # A data data_inicio maior que data_fim
        if data_inicio and data_fim and not (data_inicio <= data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos para as mesmas UOs ou Sistêmica
        if not cancelado:
            is_insert = not self.instance.id
            lista_periodos = []
            ja_salvos = PGDExterior.objects.filter(servidor=servidor).exclude(cancelado=True).order_by('data_inicio')
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.instance.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append((ja_salvo.data_inicio, ja_salvo.data_fim))
            este = (data_inicio, data_fim) if data_fim else (data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos para o servidor')


class ConsultaDesligamento(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)
    setores = forms.MultipleModelChoiceFieldPlus(label='Setores', queryset=get_setores_pgd(), required=False)
    regra = forms.ChoiceField(label='Agrupamento', required=True)

    def __init__(self, *args, **kwargs):
        self.mon_coices = kwargs.pop('mon_coices', None)
        super().__init__(*args, **kwargs)
        self.fields['regra'].choices = self.mon_coices
