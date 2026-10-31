from decimal import Decimal

from django.conf import settings
from django.db.models.aggregates import Sum

from tinymce.widgets import TinyMCE
from comum.models import Ano, Sala
from djtools import forms
from edu.models import Aluno
from pit_rit.models import AtividadeDocente, PlanoIndividualTrabalho, TipoAtividadeDocente
from rh.models import UnidadeOrganizacional


class ConfiguracaoForm(forms.Form):
    ponto_docente_ativado = forms.BooleanField(label='Ponto Docente Ativado', help_text='Ativação do Ponto Docente', required=False)


class AdicionarAtividadeDocenteForm(forms.ModelFormPlus):
    descricao = forms.CharFieldPlus(label='Descrição', max_length=100, width=500)
    ch_aula = forms.IntegerFieldPlus(label='C.H', width=50, help_text='Caga-horária semanal prevista na normativa')
    qtd_dias = forms.IntegerFieldPlus(label='Qtd. Dias', width=50, required=False)
    sala = forms.ModelChoiceFieldPlus(Sala.ativas, label='Sala', required=False)
    periodicidade = forms.ChoiceField(label='Periodicidade', choices=[[x, x] for x in ['Semestral', 'Eventual']], widget=forms.RadioSelect())

    class Meta:
        model = AtividadeDocente
        fields = 'descricao', 'tipo_atividade', 'periodicidade', 'ch_aula', 'qtd_dias', 'comprovante', 'sala'

    class Media:
        js = ('/static/pit_rit/js/AdicionarAtividadeDocenteForm.js',)

    fieldsets = (
        ('Dados gerais', {'fields': ('descricao', 'tipo_atividade')}),
        ('Carga Horária', {'fields': (('periodicidade',), ('ch_aula', 'qtd_dias'))}),
        ('Documentação', {'fields': ('comprovante',)}),
        ('Localização', {'fields': ('sala',)}),
    )

    def __init__(self, pit, tipo, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pit = pit
        self.fields['tipo_atividade'].queryset = TipoAtividadeDocente.objects.filter(categoria=tipo, ativo=True)
        servidor = pit.professor.vinculo.relacionamento
        uo_lotacao = servidor.setor_lotacao and servidor.setor_lotacao.uo.equivalente or None
        uo_exercicio = servidor.setor.uo
        self.fields['sala'].queryset = Sala.ativas.filter(predio__uo__in=[uo_lotacao, uo_exercicio])

    def clean_comprovante(self):
        tipo_atividade = self.cleaned_data.get('tipo_atividade')
        comprovante = self.cleaned_data.get('comprovante')
        if tipo_atividade and tipo_atividade.exige_documentacao:
            if not comprovante:
                raise forms.ValidationError(f'Atividades do tipo {tipo_atividade} requerem comprovação.')
        return comprovante

    def clean_tipo_atividade(self):
        tipo_atividade = self.cleaned_data.get('tipo_atividade')
        periodicidade = self.cleaned_data.get('periodicidade')
        ch_aula_cadastradas = (
            self.pit.atividadedocente_set.filter(tipo_atividade=tipo_atividade).aggregate(Sum('ch_aula_efetiva')).get('ch_aula_efetiva__sum')
        )

        if tipo_atividade and periodicidade == 'Semestral':
            if ch_aula_cadastradas > tipo_atividade.ch_maxima_semanal:
                raise forms.ValidationError(
                    'Não é possível cadastrar a atividade docente, pois a carga horária semanal para este tipo de atividade já foi atingida.'
                )

        if tipo_atividade == TipoAtividadeDocente.EXTENSAO:
            from projetos.models import Participacao

            if Participacao.objects.filter(
                pessoa__id=self.pit.professor.vinculo.pessoa.id, ativo=True, projeto__data_finalizacao_conclusao__isnull=True
            ):
                raise forms.ValidationError(
                    'O professor não se encontra cadastrado como participante ativo em nenhum projeto de extensão em andamento.'
                )

        if tipo_atividade == TipoAtividadeDocente.PESQUISA:
            from pesquisa.models import Participacao as ParticipacaoPesquisa

            if ParticipacaoPesquisa.objects.filter(
                pessoa__id=self.pit.professor.vinculo.pessoa.id, ativo=True, projeto__data_finalizacao_conclusao__isnull=True
            ):
                raise forms.ValidationError(
                    'O professor não se encontra cadastrado como participante ativo em nenhum projeto de pesquisa em andamento.'
                )

        return self.cleaned_data.get('tipo_atividade')

    def clean_ch_aula(self):
        ch_aula = int(self.data.get('ch_aula'))
        qtd_dias = int(self.cleaned_data.get('qtd_dias', 0))
        if 'ch_aula' in self.cleaned_data and 'tipo_atividade' in self.cleaned_data:
            tipo_atividade = self.cleaned_data.get('tipo_atividade')
            qs_atividade = self.pit.atividadedocente_set.filter(tipo_atividade=tipo_atividade)
            if self.instance.pk:
                qs_atividade = qs_atividade.exclude(pk=self.instance.pk)
            ch_aula_cadastradas = qs_atividade.aggregate(Sum('ch_aula_efetiva')).get('ch_aula_efetiva__sum') or 0

            ch_total = int(ch_aula + ch_aula_cadastradas)
            if ch_total > tipo_atividade.ch_maxima_semanal:
                raise forms.ValidationError(
                    f'A soma das cargas horárias semanais cadastradas ({ch_total}) para esta atividade '
                    f'não deve ser maior que {tipo_atividade.ch_maxima_semanal}.'
                )

            # Verificando se a CH da atividade é compatível com a CH do Tipo de Atividade
            if not tipo_atividade.ch_minima_semanal <= ch_aula <= tipo_atividade.ch_maxima_semanal:
                if tipo_atividade.ch_minima_semanal == tipo_atividade.ch_maxima_semanal:
                    raise forms.ValidationError(f'A carga horária semanal deve igual a {tipo_atividade.ch_maxima_semanal}.')
                else:
                    raise forms.ValidationError(
                        f'A carga horária semanal deve ser entre {tipo_atividade.ch_minima_semanal} e {tipo_atividade.ch_maxima_semanal}.'
                    )
            try:
                ch_futura = ch_aula_cadastradas + (ch_aula * qtd_dias / 100)
            except Exception:
                ch_futura = ch_aula_cadastradas + Decimal(ch_aula * qtd_dias / 100)
            if not self.instance.pk and ch_futura > tipo_atividade.ch_maxima_semanal:
                raise forms.ValidationError(
                    'Não é possível cadastrar a atividade docente, pois a carga horária semanal informada '
                    f'excederá ({ch_futura}) a quantidade máxima permitida ({tipo_atividade.ch_maxima_semanal}) para este tipo de atividade.'
                )
        return ch_aula

    def clean_qtd_dias(self):
        qtd_dias = self.cleaned_data.get('qtd_dias', 0)
        periodicidade = self.cleaned_data.get('periodicidade')
        if periodicidade == 'Eventual' and not qtd_dias:
            raise forms.ValidationError('A quantidade de dias é necessária para atividades eventuais.')
        return qtd_dias


class PlanoIndividualTrabalhoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalho
        fields = 'relatos_ensino', 'relatos_pesquisa', 'relatos_extensao', 'relatos_gestao'

    fieldsets = (
        ('Ensino', {'fields': ('relatos_ensino',)}),
        ('Pesquisa', {'fields': ('relatos_pesquisa',)}),
        ('Extensão', {'fields': ('relatos_extensao',)}),
        ('Gestão', {'fields': ('relatos_gestao',)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in 'relatos_ensino', 'relatos_pesquisa', 'relatos_extensao', 'relatos_gestao':
            self.fields[field_name].widget = TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'})
            self.fields[field_name].label = ''


class BuscaPlanoIndividualTrabalhoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'

    nome = forms.CharField(label='Nome/Matrícula/CPF', required=False, widget=forms.TextInput(attrs={'size': 20}))
    campus = forms.ModelChoiceField(required=False, queryset=UnidadeOrganizacional.objects.suap().all(), label='Filtrar por Campus')
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos().filter(ano__gte=2017), label='Ano Letivo', required=False)
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=[['', '----'], *Aluno.PERIODO_LETIVO_CHOICES], required=False)

    def processar(self):
        qs = PlanoIndividualTrabalho.objects.filter(ano_letivo__ano__gte=2017, deferida=True).exclude(ano_letivo__ano=2017, periodo_letivo=1)
        qs2 = PlanoIndividualTrabalho.objects.none()
        if 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            qs2 = PlanoIndividualTrabalhoV2.objects.filter(publicado=True)
        nome = self.cleaned_data['nome']
        campus = self.cleaned_data['campus']
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']

        if nome:
            qs = (
                qs.filter(professor__vinculo__pessoa__nome__icontains=nome)
                | qs.filter(professor__vinculo__pessoa__pessoafisica__cpf=nome)
                | qs.filter(professor__vinculo__user__username=nome)
            )

            qs2 = (
                qs2.filter(professor__vinculo__pessoa__nome__icontains=nome)
                | qs2.filter(professor__vinculo__pessoa__pessoafisica__cpf=nome)
                | qs2.filter(professor__vinculo__user__username=nome)
            )

        if campus:
            qs = qs.filter(professor__vinculo__setor__uo=campus)
            qs2 = qs2.filter(professor__vinculo__setor__uo=campus)
        if ano_letivo:
            qs = qs.filter(ano_letivo=ano_letivo)
            qs2 = qs2.filter(ano_letivo=ano_letivo)
        if periodo_letivo:
            qs = qs.filter(periodo_letivo=periodo_letivo)
            qs2 = qs2.filter(periodo_letivo=periodo_letivo)
        return qs, qs2
