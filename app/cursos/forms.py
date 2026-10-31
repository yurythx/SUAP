from datetime import date, datetime
from threading import Thread

from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms.widgets import Select

from comum.models import Ano
from cursos.enums import SituacaoCurso, SituacaoDetalhamentoAtividadeParticipante, SituacaoParticipante
from cursos.models import Atividade, CotaExtra, Curso, Participante
from djtools import forms
from djtools.choices import Meses
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import send_notification
from protocolo.models import Processo
from rh.models import Servidor, UnidadeOrganizacional


class CursoForm(forms.ModelFormPlus):
    descricao = forms.CharField(label='Descrição', widget=forms.Textarea(attrs={'rows': '2', 'columns': '40'}))
    processos = forms.MultipleModelChoiceFieldPlus(label='Processos relacionados', required=False, queryset=Processo.objects.all())

    responsaveis = forms.MultipleModelChoiceFieldPlus(label='Responsáveis', required=False, queryset=Servidor.objects.ativos())

    campus = forms.ModelChoiceField(required=True, label='Unidade Organizacional', queryset=UnidadeOrganizacional.objects.suap().all())

    situacao = forms.ChoiceField(choices=[], required=False, label='Situação')

    fieldsets = ((None, {'fields': ('descricao', 'ano_pagamento', 'campus', 'participantes', 'tipo', 'edital', 'processos')}),)

    class Meta:
        model = Curso
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        lista_situacao_choices = []
        for k, v in SituacaoCurso.get_choices():
            if k == SituacaoCurso.FINALIZADO:
                continue
            lista_situacao_choices.append([k, v])
        self.fields['situacao'].choices = lista_situacao_choices

        if 'instance' in kwargs:
            atributo_edital = self.instance.edital
            self.fields['situacao'].initial = SituacaoCurso.NAO_INICIADO
            try:
                atributo_processos = self.instance.processos.all()
            except Exception:
                atributo_processos = None
            if atributo_edital:
                self.fields['edital'].help_text = f'<a href="{atributo_edital.url}">Clique para ver edital</a>'
            else:
                self.fields['edital'].help_text = 'Não há edital cadastrado'
            if atributo_processos:
                retorno = ''
                for p in atributo_processos:
                    retorno = retorno + f'<a href="{p.get_absolute_url()}">Clique para ver processo {p.__str__()}</a>'
                    retorno = retorno + '<br / >'
                self.fields['processos'].help_text = retorno
            else:
                self.fields['processos'].help_text = 'Não há processos relacionados.'

    def clean_situacao(self):
        situacao = self.cleaned_data.get('situacao')
        if situacao:
            situacao = int(situacao)

            curso = self.instance
            qs_participantes = curso.participante_set

            if self.instance.pk and situacao != SituacaoCurso.NAO_INICIADO and not qs_participantes.exists():
                raise ValidationError('Você não pode mudar a situação do evento enquanto não existir pelo menos um participante cadastrado.')

            if (
                self.instance.pk
                and situacao == SituacaoCurso.INICIADO
                and (self.instance.tem_participante_problema_horas_insuficientes() or self.instance.tem_participante_aguardando_liberacao)
            ):
                raise ValidationError(
                    'O evento não pode ser iniciado pois existem participantes com problemas de carga horária ou aguardando liberação da chefia imediata.'
                )

            if (
                self.instance.pk
                and (situacao == SituacaoCurso.FINALIZADO or situacao == SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA)
                and self.instance.tem_participante_sem_hora_trabalhada
            ):
                raise ValidationError('O evento não pode ser finalizado pois existem participantes sem hora trabalhada cadastrada.')

            if self.instance.pk and situacao == SituacaoCurso.CADASTRADO_EM_FOLHA and self.instance.situacao != situacao:
                self.instance.informar_cadastro_folha(self.request)

        return situacao


class AtividadeForm(forms.ModelFormPlus):
    valor_hora = forms.DecimalFieldPlus(label='Valor da Hora')

    class Meta:
        model = Atividade
        exclude = ()


class ParticipanteForm(forms.ModelFormPlus):
    atividade = forms.ModelChoiceFieldPlus(Atividade.objects)
    atividade_mes = forms.ChoiceField(choices=Meses.get_choices(), label='Mês da Atividade')

    def __init__(self, *args, **kwargs):
        curso_concurso = kwargs.pop('curso', None)
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.id:
            self.fields['servidor'].widget = forms.HiddenInput()

        if curso_concurso:
            self.fields['curso'].initial = curso_concurso.id
        self.fields['curso'].widget = forms.HiddenInput()

        self.fields['atividade'].queryset = Atividade.objects.filter(ativa=True)

        mes_atual = datetime.now().month
        self.fields['atividade_mes'].initial = mes_atual

    class Meta:
        model = Participante
        exclude = (
            'mes_pagamento',
            'horas_trabalhada',
            'motivo_nao_liberacao',
            'situacao',
            'responsavel_liberacao',
            'data_liberacao',
            'horas_trabalhadas_info',
            'horas_trabalhadas_fora_ch',
            'horas_trabalhadas_dentro_ch',
            'data_inicio_atividade',
            'data_fim_atividade',
            'descricao_atividade',
            'situacao_detalhamento',
            'motivo_nao_deferimento_detalhamento',
            'responsavel_compensacao_especifica',
        )

    def clean(self):
        servidor = self.cleaned_data.get('servidor')
        curso = self.cleaned_data.get('curso')
        atividade = self.cleaned_data.get('atividade')
        atividade_mes = self.cleaned_data.get('atividade_mes')
        """
        Condições para verificar se o servidor já está participando do evento
          1 - o servidor deve estar setado
          2 - o curso deve estar setado
          3 - a instância não deve ter id, essa verificação deve ser feita apenas no cadastro
        """
        if servidor and curso and self.instance.id is None:
            # verificando se o servidor já está cadastrado para o evento/atividade
            if curso.participante_set.filter(servidor=servidor, atividade=atividade, atividade_mes=atividade_mes).exists():
                raise ValidationError(f'O servidor {servidor} já está participando desta atividade no mesmo mês.')
        return self.cleaned_data

    def save(self, commit=True):
        if self.instance and self.instance.id:
            participante = Participante.objects.get(id=self.instance.id)
            # se a hora prevista for alterada, a chefia deve avaliar novamente
            if participante.horas_prevista != self.instance.horas_prevista:
                self.instance.situacao = SituacaoParticipante.AGUARDANDO_LIBERACAO
        super().save()

        t1 = Thread(self._email_para_chefe_imediato(self.instance))
        t1.start()

    def _email_para_chefe_imediato(self, instance):
        if instance:
            url = f'{settings.SITE_URL}/admin/cursos/participante/'
            titulo = '[SUAP] GECC: Participação em Curso/Concurso'
            texto = (
                '<h1>GECC: Participação em Curso/Concurso</h1>'
                '<h2>Pedido de vista à chefia imediata</h2>'
                f'<p>O servidor {instance.servidor.pessoa_fisica.nome} foi selecionado para participar do curso/concurso {instance.curso.descricao}.</p>'
                '<p>No entanto, é necessário um parecer da chefia imediata, deferindo ou indeferindo a participação do servidor no evento.</p>'
                f'<p>Para avaliar a participação do servidor, basta entrar no SUAP e acessar o menu <a href="{url}">Gestão de Pessoas -> Desenvolvimento de Pessoal -> Cursos '
                'e Concursos -> Participantes</a>. Você também receberá um alerta na página inicial do SUAP caso tenha solicitações pendentes.</p>'
            )

            vinculos = []
            for i in instance.servidor.chefes_imediatos():  # chefes_imediatos() devolve um queryset de servidor
                vinculos.append(i.get_vinculo())
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)


class AdicionarHorasTrabalhadasForm(forms.ModelFormPlus):
    # ano_desconto_carga_horaria = forms.ChoiceField(label=u'Ano Carga Horária', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['servidor'].widget = forms.HiddenInput()
            self.fields['servidor'].initial = self.instance.servidor.id
            self.fields['horas_trabalhada'].help_text = 'Se informar 0 (zero) horas, o detalhamento das horas do participante não será exigido.'

        # ano_atual = datetime.now().year
        # self.fields['ano_desconto_carga_horaria'].choices = [[ano_atual-1, ano_atual-1], [ano_atual, ano_atual], [ano_atual+1, ano_atual+1]]
        # self.fields['ano_desconto_carga_horaria'].initial = ano_atual

    class Meta:
        model = Participante
        # fields = ('horas_trabalhada', 'ano_desconto_carga_horaria', 'servidor')
        fields = ('horas_trabalhada', 'servidor')

    def clean_horas_trabalhada(self):
        horas_trabalhada = self.cleaned_data.get('horas_trabalhada')
        if horas_trabalhada is None:
            raise ValidationError('Informe a quantidade de horas trabalhadas.')
        participante = self.instance
        horas_disponiveis = participante.horas_disponiveis_ano + participante.horas_prevista

        # verificando horas disponíveis para o servidor
        if horas_disponiveis < horas_trabalhada:
            raise ValidationError(
                f'Não é possível adicionar a quantidade de {horas_trabalhada} horas trabalhadas, pois o servidor dispõe apenas de {horas_disponiveis} horas.'
            )

        return horas_trabalhada

    def save(self, commit=True):
        save = super().save(commit)
        if save:
            participante: Participante = self.instance
            participante.preparar_preenchimento_detalhamento_atividade()
        return save


class PreencherDetalhamentoAtividadeForm(forms.ModelFormPlus):
    atividade_info = forms.CharFieldPlus(label='Atividade', required=False)
    horas_trabalhadas_info = forms.CharFieldPlus(label='Horas Trabalhadas', required=False)

    class Meta:
        model = Participante
        fields = (
            'atividade_info',
            'horas_trabalhadas_info',
            'horas_trabalhadas_fora_ch',
            'horas_trabalhadas_dentro_ch',
            'data_inicio_atividade',
            'data_fim_atividade',
            'descricao_atividade',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        curso_e_atividade = f'{self.instance.curso} - {self.instance.atividade.descricao}'
        self.fields['atividade_info'].initial = curso_e_atividade
        self.fields['atividade_info'].widget.attrs['value'] = curso_e_atividade
        self.fields['atividade_info'].widget.attrs['readonly'] = 'readonly'

        horas_trabalhada = f'{self.instance.horas_trabalhada}'
        self.fields['horas_trabalhadas_info'].initial = horas_trabalhada
        self.fields['horas_trabalhadas_info'].widget.attrs['value'] = horas_trabalhada
        self.fields['horas_trabalhadas_info'].widget.attrs['readonly'] = 'readonly'

        self.fields['horas_trabalhadas_fora_ch'].label = 'Horas Trabalhadas fora da Carga Horária'
        self.fields['horas_trabalhadas_fora_ch'].required = True

        self.fields['horas_trabalhadas_dentro_ch'].label = 'Horas Trabalhadas dentro da Carga Horária'
        self.fields['horas_trabalhadas_dentro_ch'].required = True

        self.fields['data_inicio_atividade'].required = True
        self.fields['data_fim_atividade'].required = True
        self.fields['descricao_atividade'].required = True

    def clean(self):
        clean = super().clean()

        participante: Participante = self.instance

        h_trabalhada = participante.horas_trabalhada
        h_fora_ch = clean.get('horas_trabalhadas_fora_ch', 0.0)
        h_dentro_ch = clean.get('horas_trabalhadas_dentro_ch', 0.0)

        if h_trabalhada is None:
            self.add_error(None, 'A quantidade de horas trabalhadas ainda não foi informada pelo responsável.')

        if not h_fora_ch >= 0:
            self.add_error('horas_trabalhadas_fora_ch', 'Informe uma quantidade maior ou igual a zero de horas trabalhadas fora da carga horária.')

        if not h_dentro_ch >= 0:
            self.add_error(
                'horas_trabalhadas_dentro_ch', 'Informe uma quantidade maior ou igual a zero de horas trabalhadas dentro da carga horária.'
            )

        if h_fora_ch + h_dentro_ch != h_trabalhada:
            self.add_error(None, f'A soma das horas trabalhadas (dentro e fora da CH) deve ser igual a {h_trabalhada}.')

        return clean

    def save(self, commit=True):
        save = super().save(commit)
        if save:
            participante: Participante = self.instance
            participante.preparar_avaliacao_detalhamento_atividade()
        return save


class IndeferirDetalhamentoAtividadeForm(forms.ModelFormPlus):
    class Meta:
        model = Participante
        fields = ('motivo_nao_deferimento_detalhamento',)
        widgets = {'motivo_nao_deferimento_detalhamento': forms.Textarea}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motivo_nao_deferimento_detalhamento'].required = True

    def save(self, commit=True):
        participante: Participante = self.instance
        participante.indeferir_detalhamento_atividade(motivo=self.cleaned_data.get('motivo_nao_deferimento_detalhamento'), save=commit)
        return participante


class FiltrarParticipanteForm(forms.FormPlus):
    servidor = forms.ModelChoiceFieldPlus(
        label='Servidor', queryset=Servidor.objects, required=False, help_text='Deixe vazio para selecionar o servidor que está logado.'
    )
    ano = forms.IntegerField(label='Ano', required=False)
    situacao_curso = forms.ChoiceField(
        label='Situação do Curso/Concurso',
        choices=[
            [None, 'Qualquer'],
            *SituacaoCurso.get_choices(),
            ['andamento', 'Em Andamento (Iniciado ou Aguardando Cadastro em Folha)'],
            ['concluido', 'Concluído (Cadastrado em Folha ou Finalizado)'],
        ],
        required=False,
    )
    situacao_participante = forms.ChoiceField(
        label='Situação do Participante',
        choices=[[None, 'Qualquer'], *SituacaoParticipante.get_choices(), ['atividade', 'Em Atividade (Deferido ou Pendente de Pagamento)']],
        required=False,
    )
    situacao_detalhamento_horas = forms.ChoiceField(
        label='Situação do Detalhamento das Horas',
        choices=[
            [None, 'Qualquer'],
            *SituacaoDetalhamentoAtividadeParticipante.get_choices(),
            ['pendente', 'Pendente (Aguardando Preenchimento ou Aguardando Avaliação)'],
        ],
        required=False,
    )

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        pode_selecionar_servidor = kwargs.pop('pode_selecionar_servidor', False)
        super().__init__(*args, **kwargs)
        if not pode_selecionar_servidor:
            del self.fields['servidor']
        field_ano_widget_attrs = self.fields['ano'].widget.attrs or {}
        field_ano_widget_attrs.update({'placeholder': 'Qualquer'})
        self.fields['ano'].widget.attrs = field_ano_widget_attrs


class CotaExtraForm(forms.ModelFormPlus):
    servidor = forms.ModelChoiceFieldPlus(Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS))
    ano = forms.ModelChoiceFieldPlus(Ano.objects, widget=Select())
    processos = forms.MultipleModelChoiceFieldPlus(Processo.objects, required=True)

    class Meta:
        model = CotaExtra
        exclude = ('data_cadastro',)

    def clean_horas_permitida(self):
        horas_permitidas = self.cleaned_data.get('horas_permitida')
        servidor = self.cleaned_data.get('servidor')
        ano = self.cleaned_data.get('ano')

        if horas_permitidas > Participante.VALOR_PADRAO_HORAS_TRABALHADAS:
            raise ValidationError('O máximo de horas permitidas para cota extra é de 120 horas.')

        # verificando as cotas já cadastradas para o servidor no ano em questão
        saldo_cadastrado = CotaExtra.cota_extra_servidor_no_ano(servidor, ano)

        saldo_total = saldo_cadastrado + horas_permitidas
        if saldo_total > Participante.VALOR_PADRAO_HORAS_TRABALHADAS:
            raise ValidationError(
                f'A cota extra total ({saldo_total}) do servidor ultrapassa o limite máximo de {Participante.VALOR_PADRAO_HORAS_TRABALHADAS}.'
            )

        return horas_permitidas


class IndeferimentoParticipanteForm(forms.FormPlus):
    motivo = forms.CharFieldPlus(label='Motivo Indeferimento', max_length=500)
    participante = forms.ModelChoiceFieldPlus(queryset=Participante.objects)

    def __init__(self, *args, **kwargs):
        participante = kwargs.pop('participante', None)
        super().__init__(*args, **kwargs)

        self.fields['participante'].widget = forms.HiddenInput()
        self.fields['participante'].initial = participante.id

        self.fields['motivo'].widget = forms.Textarea()

    def processar(self):
        participante = self.cleaned_data.get('participante')
        participante.indeferir_participacao(self.cleaned_data.get('motivo'))

        # email
        titulo = '[SUAP] GECC: Participação em Curso/Concurso'
        texto = (
            '<h1>GECC: Participação em Curso/Concurso</h1>'
            '<h2>Participação indeferida pela chefia imediata</h2>'
            '<p>{},</p>'
            '<p>Sua participação em <strong>{}</strong> foi indeferida pela chefia imediata.</p>'
            '<dl><dt>Motivo do Indeferimento:</dt><dd>{}</dd></dl>'.format(
                participante.servidor.pessoa_fisica.nome, participante.curso.descricao, self.cleaned_data.get('motivo')
            )
        )

        t1 = Thread(send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [participante.servidor.get_vinculo()]))
        t1.start()


class RelatorioFinanceiroPagamentoGECCForm(forms.FormPlus):
    ano = forms.ModelChoiceFieldPlus(Ano.objects, widget=Select(), label='Ano')
    mes = forms.ChoiceField(choices=Meses.get_choices(), label='Mês')


class CotaAnualServidorGECCForm(forms.FormPlus):
    METHOD = 'GET'
    texto_busca = forms.CharFieldPlus(label='Nome do servidor', required=False)
    ano = forms.ModelChoiceFieldPlus(Ano.objects, widget=Select(), label='Ano', required=False)

    fieldsets = ((None, {'fields': ('texto_busca', 'ano')}),)


class EditarMesPagamentoGECCForm(forms.FormPlus):
    participante = forms.ModelChoiceFieldPlus(queryset=Participante.objects)
    mes = forms.ChoiceField(choices=Meses.get_choices(), label='Mês')
    ano = forms.ModelChoiceFieldPlus(queryset=Ano.objects, required=True, widget=AutocompleteWidget(search_fields=Ano.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        participante = kwargs.pop('participante', None)
        super().__init__(*args, **kwargs)

        self.fields['participante'].widget = forms.HiddenInput()
        self.fields['participante'].initial = participante.id

        if participante:
            self.fields['mes'].initial = participante.mes_pagamento
            ano_pagamento = getattr(participante.data_registro_pagamento, 'year', 0)
            self.fields['ano'].initial = Ano.objects.filter(ano=ano_pagamento).first()

    def processar(self):
        participante = self.cleaned_data.get('participante')
        mes = self.cleaned_data.get('mes')
        ano = self.cleaned_data.get('ano')
        data_registro = date(int(ano.ano), int(mes), 1)
        participante.data_registro_pagamento = data_registro
        participante.mes_pagamento = mes
        participante.save()


class FiltroPendentesPagamentoForm(forms.FormPlus):
    METHOD = 'GET'
    participante = forms.CharFieldPlus(label='Nome do Participante', required=False)
    evento = forms.ChoiceField(choices=[], label='Evento', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        lista = [['', '-- Selecione --']]
        for i in Curso.objects.filter(participante__situacao=SituacaoParticipante.PENDENTE).distinct():
            lista.append([i.id, i.descricao])
        self.fields['evento'].choices = lista
