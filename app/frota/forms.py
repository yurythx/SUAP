import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.forms.utils import ErrorList

from comum.models import Configuracao, Municipio, PrestadorServico, Vinculo
from comum.utils import get_uo
from djtools import forms
from djtools.choices import Situacao
from djtools.forms.widgets import AutocompleteWidget, BrTelefoneWidget, FilteredSelectMultiplePlus
from edu.models import Diario, Turma
from estacionamento.forms import VeiculoForm
from estacionamento.models import Veiculo, VeiculoCombustivel
from frota.models import (
    ManutencaoViatura,
    Maquina,
    MaquinaOrdemAbastecimento,
    MotoristaTemporario,
    Viagem,
    ViagemAgendamento,
    ViagemAgendamentoResposta,
    Viatura,
    ViaturaGrupo,
    ViaturaOrdemAbastecimento,
    ViaturaStatus,
    ManutencaoMaquina,
    TipoServicoMaquina,
    EdicaoAgendamentoDeferido,
    MultaViagem,
)
from patrimonio.models import Inventario
from rh.models import Servidor, UnidadeOrganizacional


def viaturas_disponiveis_as_choices(viaturas_indisponiveis, campus=None):
    choices = [['', '-----------------']]
    if campus:
        for viatura in Viatura.ativas.filter(campus=campus).exclude(id__in=viaturas_indisponiveis):
            choices.append([viatura.id, str(viatura)])
    else:
        for viatura in Viatura.ativas.exclude(id__in=viaturas_indisponiveis):
            choices.append([viatura.id, str(viatura)])

    return choices


def status_as_choices():
    return [[Situacao.DEFERIDA, Situacao.DEFERIDA], [Situacao.INDEFERIDA, Situacao.INDEFERIDA]]


def motoristas_disponiveis_as_queryset(motoristas_indisponiveis=None, retroativo=None):
    prazo = datetime.date.today()
    if retroativo:
        prazo = prazo + relativedelta(months=-6)
    motoristas = MotoristaTemporario.objects.filter(Q(validade_final__gte=prazo) | Q(validade_final__isnull=True))
    if motoristas_indisponiveis:
        motoristas = motoristas.exclude(vinculo_pessoa__in=motoristas_indisponiveis)

    return Vinculo.objects.filter(id__in=motoristas.values_list('vinculo_pessoa_id', flat=True)).distinct()


def grupos_viaturas_as_choices():
    grupos_viaturas = ViaturaGrupo.objects.all()
    grupos_viaturas_choices = [[0, 'Todos']]
    for grupo_viatura in grupos_viaturas:
        grupos_viaturas_choices.append([grupo_viatura.id, grupo_viatura.__str__()])
    return grupos_viaturas_choices


class ConfiguracaoForm(forms.FormPlus):
    viatura_sem_patrimonio = forms.BooleanField(
        label='Permitir Viatura sem Patrimônio',
        required=False,
        help_text='Marque esta opção para poder cadastrar uma viatura sem indicar o patrimônio dela.',
    )


class ViaturaForm(VeiculoForm):
    combustiveis = forms.ModelMultipleChoiceField(label='Combustíveis', widget=forms.CheckboxSelectMultiplePlus, queryset=VeiculoCombustivel.objects)
    vinculos_condutores = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects, required=False)
    grupo = forms.ModelChoiceField(queryset=ViaturaGrupo.objects)
    patrimonio = forms.ModelChoiceField(label='Patrimônio', queryset=Inventario.objects, widget=AutocompleteWidget(minChars=5))
    placa_codigo_anterior = forms.BrPlacaVeicularField(label='Placa Anterior', help_text='ex: NAT-1010', required=False)
    placa_municipio_anterior = forms.ModelChoiceField(
        queryset=Municipio.objects,
        widget=AutocompleteWidget(search_fields=Municipio.SEARCH_FIELDS, show=False, help_text='ex: RN - Natal'),
        required=False,
    )
    lotacao = forms.IntegerFieldPlus(label='Lotação', help_text='Capacidade máxima de ocupantes incluindo o motorista', max_length=2)
    odometro = forms.IntegerFieldPlus(label='Odômetro', help_text='Km rodados', max_length=6)
    chassi = forms.AlphaNumericUpperCaseField(label='Chassi', max_length=17, min_length=17)
    renavam = forms.IntegerFieldPlus(label='Renavam', max_length=11, min_length=9)
    potencia = forms.IntegerFieldPlus(label='Potência', help_text='Potência em hp', max_length=3)
    cilindrada = forms.IntegerFieldPlus(label='Cilindrada', help_text='Cilindrada em cc', max_length=3)
    capacidade_tanque = forms.IntegerFieldPlus(label='Tanque', help_text='Capacidade (l)', max_length=3)
    capacidade_gnv = forms.IntegerFieldPlus(label='Cilindro', help_text='Capacidade (m³)', max_length=3, required=False)
    status = forms.ModelChoiceField(label='Situação', widget=forms.Select(), queryset=ViaturaStatus.objects, initial=1, required=False)

    class Meta:
        model = Viatura
        exclude = ('condutores', 'ultima_revisao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'placa_municipio_anterior'
        ].help_text = (
            f'ex: {Configuracao.get_valor_por_chave("comum", "instituicao_estado")} - {Configuracao.get_valor_por_chave("comum", "municipio_sede")}'
        )
        permite_sem_patrimonio = Configuracao.get_valor_por_chave('frota', 'viatura_sem_patrimonio')
        self.fields['propria_instituicao'].required = False
        if permite_sem_patrimonio == 'True':
            self.fields['patrimonio'].required = False
        else:
            self.fields['campus'].required = False

        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(id=get_uo(self.request.user).id)

    def clean_placa_codigo_atual(self):
        if 'placa_codigo_atual' in self.cleaned_data:
            veiculo = Veiculo.objects.filter(placa_codigo_atual=self.cleaned_data['placa_codigo_atual'])
            if len(veiculo):
                if self.instance.pk is None:
                    veiculo[0].delete()
        return self.cleaned_data['placa_codigo_atual']

    def clean_lotacao(self):
        if 'lotacao' in self.cleaned_data:
            if self.cleaned_data['lotacao'] < 1:
                self._errors['lotacao'] = ErrorList(['A viatura deve possuir no mínimo um ocupante.'])
        return self.cleaned_data['lotacao']

    def clean_status(self):
        if 'status' in self.cleaned_data:
            situacao = ViaturaStatus.objects.filter(descricao='Disponível')
            if not len(situacao):
                self._errors['__all__'] = ErrorList(['O registro que indica a disponibilidade da viatura não foi encontrado.'])
            else:
                self.instance.status = ViaturaStatus.objects.get(descricao='Disponível')
        return self.cleaned_data['status']

    def clean(self):
        combLiq = False
        combGnv = False
        chassi_ja_cadastrado = Veiculo.objects.filter(chassi=self.cleaned_data.get('chassi'))
        renavam_ja_cadastrado = Veiculo.objects.filter(renavam=self.cleaned_data.get('renavam'))

        if self.instance.pk:
            chassi_ja_cadastrado = chassi_ja_cadastrado.exclude(id=self.instance.pk)
            renavam_ja_cadastrado = renavam_ja_cadastrado.exclude(id=self.instance.pk)

        if 'chassi' in self.cleaned_data and chassi_ja_cadastrado.exists():
            self._errors['chassi'] = ErrorList(['Já existe um veículo cadastrado com o chassi informado.'])

        if 'renavam' in self.cleaned_data and renavam_ja_cadastrado.exists():
            self._errors['renavam'] = ErrorList(['Já existe um veículo cadastrado com o renavam informado.'])

        if 'combustiveis' in self.cleaned_data:
            for combustivel in self.cleaned_data['combustiveis']:
                if combustivel.nome == 'Gás Natural':
                    combGnv = True
                    if self.cleaned_data['capacidade_gnv'] is None:
                        self._errors['capacidade_gnv'] = ErrorList(['Este campo é obrigatório se o combustível gás natural for selecionado.'])
                else:
                    combLiq = True

            if combLiq is False:
                self._errors['combustiveis'] = ErrorList(['Selecione também um combustível líquido.'])

        if combGnv is False and self.cleaned_data['capacidade_gnv'] is not None:
            self._errors['capacidade_gnv'] = ErrorList(
                ['Selecione o combustível gás natural quando fornecer um valor para a capacidade do cilindro.']
            )

        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        if not self.instance.campus and self.instance.patrimonio and self.instance.patrimonio.carga_contabil:
            self.instance.campus = self.instance.patrimonio.carga_contabil.campus

        return super().save(*args, **kwargs)


class MotoristaTemporarioForm(forms.ModelFormPlus):
    vinculo_pessoa = forms.ModelChoiceField(
        label='Pessoa',
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        help_text='A pessoa deve ser obrigatoriamente um servidor ou um prestador de serviço',
    )
    portaria = forms.AlphaNumericField(max_length=20, required=True)
    ano_portaria = forms.AlphaNumericField(label='Ano da Portaria', max_length=4, required=True)
    validade_inicial = forms.DateFieldPlus(label='Data Inicial')
    validade_final = forms.DateFieldPlus(label='Data Final', required=False)
    arquivo = forms.FileFieldPlus(label='Portaria', required=False)

    class Meta:
        model = MotoristaTemporario
        fields = ('vinculo_pessoa', 'portaria', 'ano_portaria', 'validade_inicial', 'validade_final', 'obs', 'arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculo_pessoa'].queryset = Vinculo.objects.filter(
            Q(tipo_relacionamento__model='servidor', id_relacionamento__in=Servidor.objects.filter(ativo=True).values_list('id', flat=True))
            | Q(
                tipo_relacionamento__model='prestadorservico',
                id_relacionamento__in=PrestadorServico.objects.filter(ativo=True).values_list('id', flat=True),
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        validade_inicial = cleaned_data.get('validade_inicial')
        validade_final = cleaned_data.get('validade_final')
        if validade_final and validade_inicial and validade_final <= validade_inicial:
            self.add_error('validade_final', 'A validade final não pode ser inferior a validade inicial.')
        return cleaned_data


class ViagemAgendamentoForm(forms.ModelFormPlus):
    vinculo_solicitante = forms.ModelChoiceField(
        label='Solicitante',
        queryset=Vinculo.objects.filter(setor__isnull=False),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS, minChars=5),
    )
    data_saida = forms.DateTimeFieldPlus(label='Saída', help_text='Data/hora Prevista da Saída')
    data_chegada = forms.DateTimeFieldPlus(label='Chegada', help_text='Data/hora Prevista da Chegada')
    telefone_responsavel = forms.BrTelefoneField(max_length=14, label='Telefone do Responsável', widget=BrTelefoneWidget())

    vinculos_passageiros = forms.MultipleModelChoiceFieldPlus(label='Passageiros', queryset=Vinculo.objects, required=False)
    turma = forms.MultipleModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        help_text='Selecione uma turma para adicionar todos os alunos como passageiros',
        required=False,
    )
    diario = forms.MultipleModelChoiceFieldPlus(
        Diario.objects,
        label='Diário',
        required=False,
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário.',
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Diario.SEARCH_FIELDS,
            form_filters=[
                ('turma', 'turma__in'),
                ('uo', 'turma__curso_campus__diretoria__setor__uo__in'),
                ('polo', 'turma__polo__in'),
                ('curso_campus', 'turma__curso_campus'),
                ('estrutura', 'turma__curso_campus__estrutura'),
                ('modalidade', 'turma__curso_campus__modalidade'),
            ],
        ),
    )
    lista_alunos = forms.CharFieldPlus(
        label='Alunos', help_text='Informe uma lista de matrículas separadas por vírgulas para adicionar vários alunos', required=False
    )
    local_saida = forms.CharField(label='Local de Saída', required=True)

    vinculos_interessados = forms.MultipleModelChoiceFieldPlus(label='Interessados', queryset=Vinculo.objects, required=False)
    texto_aceite = forms.CharFieldPlus(label='Termo de Responsabilidade', required=False, max_length=1000, widget=forms.Textarea)
    aceite = forms.BooleanField(label='Aceito o Termo de Responsabilidade', required=False, initial=False)

    class Meta:
        model = ViagemAgendamento
        fields = (
            'vinculo_solicitante',
            'objetivo',
            'intinerario',
            'data_saida',
            'data_chegada',
            'nome_responsavel',
            'telefone_responsavel',
            'vinculos_passageiros',
            'turma',
            'diario',
            'lista_alunos',
            'local_saida',
            'quantidade_diarias',
            'vinculos_interessados',
            'arquivo',
            'texto_aceite',
            'aceite',
        )

    class Media:
        js = ['/static/frota/js/agendamentoform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
            self.fields['vinculo_solicitante'].queryset = Vinculo.objects.filter(setor__uo=get_uo(self.request.user))
        self.fields['vinculo_solicitante'].initial = self.request.user.get_vinculo()
        if self.request.user.has_perm('frota.tem_acesso_agendamento_agendador'):
            self.fields['vinculo_solicitante'].widget.readonly = True
        if self.request.user.has_perm('frota.change_viagemagendamento') and (
            self.request.user.has_perm('frota.tem_acesso_viagem_sistemico')
            or self.request.user.has_perm('frota.tem_acesso_viagem_campus')
            or (self.instance.pk and (self.instance.vinculo_solicitante == self.request.user.get_vinculo()))
        ):
            self.fields['nome_responsavel'].required = True

        sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        self.fields['texto_aceite'].widget.attrs['readonly'] = True
        self.fields[
            'texto_aceite'
        ].initial = f'Declaro que estou ciente da minha responsabilidade em relação a locomoção dos alunos menores de idade e que eu sou o responsável pela verificação da existência das autorizações dos pais ou responsáveis legais para o deslocamento dos alunos a eventos organizados pelo {sigla}.'

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('data_saida'):
            if cleaned_data.get('data_saida') <= datetime.datetime.now():
                self.add_error('data_saida', 'A data de saída não pode ser inferior a data atual.')

        if cleaned_data.get('data_chegada') and cleaned_data.get('data_saida'):
            if cleaned_data.get('data_chegada') <= cleaned_data.get('data_saida'):
                self.add_error('data_chegada', 'A data de chegada não pode ser inferior a data de saída.')

        if self.instance.status == Situacao.DEFERIDA or self.instance.status == Situacao.INDEFERIDA:
            if not self.request.user.has_perm('frota.tem_acesso_agendamento_sistemico'):
                raise forms.ValidationError('Agendamentos avaliados não podem ser atualizados.')

        if (self.cleaned_data.get('lista_alunos') or self.cleaned_data.get('turma') or self.cleaned_data.get('diario')) and not self.cleaned_data.get(
            'aceite'
        ):
            self.add_error('aceite', 'Você precisa registrar o aceite do termo de compromisso.')

        return self.cleaned_data


class ViagemRetroativaForm(forms.FormPlus):
    vinculo_solicitante = forms.ModelChoiceFieldPlus(label='Solicitante', queryset=Vinculo.objects)
    agendamento_resposta = forms.ModelChoiceField(label='Agendamento', queryset=ViagemAgendamentoResposta.objects, required=False)
    data_saida = forms.DateTimeFieldPlus(label='Saída', required=True)
    data_chegada = forms.DateTimeFieldPlus(label='Chegada', required=True)
    objetivo = forms.CharField(label='Objetivo', widget=forms.Textarea())
    itinerario = forms.CharField(label='Itinerário', widget=forms.Textarea())
    viatura = forms.ModelChoiceField(label='Viatura', queryset=Viatura.objects.filter(ativo=True), required=True)
    motoristas = forms.MultipleModelChoiceFieldPlus(
        label='Motoristas Disponíveis', queryset=Vinculo.objects, required=False, widget=FilteredSelectMultiplePlus('', True)
    )
    saida_odometro = forms.IntegerFieldPlus(label='Quilometragem Inicial', max_length=6)
    local_saida = forms.CharField(label='Local de Saída', required=True)
    saida_obs = forms.CharField(label='Observações da Saída', widget=forms.Textarea(), required=False)
    chegada_odometro = forms.IntegerFieldPlus(label='Quilometragem Final', max_length=6)
    chegada_obs = forms.CharField(label='Observacões da Chegada', widget=forms.Textarea(), required=False)
    vinculos_passageiros = forms.MultipleModelChoiceFieldPlus(label='Passageiros', queryset=Vinculo.objects)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motoristas'].queryset = motoristas_disponiveis_as_queryset(retroativo=True).order_by('pessoa__nome')
        if not self.request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
            self.fields['vinculo_solicitante'].queryset = Vinculo.objects.filter(setor__uo=get_uo(self.request.user))
        self.fields['vinculo_solicitante'].initial = self.request.user.get_vinculo()

        agendamentos_viagem = list(
            Viagem.objects.filter(agendamento_resposta__agendamento__setor__uo=get_uo(self.request.user)).values_list(
                'agendamento_resposta_id', flat=True
            )
        )
        resp_agendamentos = (
            ViagemAgendamentoResposta.objects.filter(
                agendamento__setor__uo=get_uo(self.request.user),
                agendamento__status=Situacao.DEFERIDA,
                agendamento__data_saida__lte=datetime.date.today() + datetime.timedelta(7),
                agendamento__data_saida__gte=datetime.date.today() + datetime.timedelta(-60),
            )
            .exclude(id__in=agendamentos_viagem)
            .order_by('-agendamento__id')
        )
        self.fields[
            'agendamento_resposta'
        ].help_text = 'Caso esta viagem retroativa se refira a algum agendamento, selecione o agendamento. <a href="/frota/viagem_retroativa/">Limpar Formulário</a>'
        self.fields['agendamento_resposta'].widget = forms.Select(
            attrs={
                'onchange': "this.options[this.selectedIndex].value && (window.location = '{}?ag=' + this.options[this.selectedIndex].value);".format(
                    self.request.META.get('PATH_INFO')
                )
            }
        )
        self.fields['agendamento_resposta'].queryset = resp_agendamentos
        try:
            id_resposta_agendamento = int(self.request.GET.get('ag'))
        except Exception:
            return
        if id_resposta_agendamento and id_resposta_agendamento in resp_agendamentos.values_list('id', flat=True):
            busca_resposta = ViagemAgendamentoResposta.objects.filter(id=id_resposta_agendamento)
            if busca_resposta.exists():
                resposta_agendamento = busca_resposta[0]
                self.fields['agendamento_resposta'].initial = resposta_agendamento.id
                self.fields['data_saida'].initial = resposta_agendamento.agendamento.data_saida
                self.fields['local_saida'].initial = resposta_agendamento.agendamento.local_saida
                self.fields['data_chegada'].initial = resposta_agendamento.agendamento.data_chegada
                self.fields['objetivo'].initial = resposta_agendamento.agendamento.objetivo
                self.fields['itinerario'].initial = resposta_agendamento.agendamento.intinerario
                if resposta_agendamento.viatura:
                    self.fields['viatura'].initial = resposta_agendamento.viatura.id
                if resposta_agendamento.motoristas.exists():
                    self.initial['motoristas'] = [t.pk for t in resposta_agendamento.motoristas.all()]
                self.fields['vinculos_passageiros'].initial = resposta_agendamento.agendamento.vinculos_passageiros.all()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('data_saida'):
            if cleaned_data.get('data_saida') >= datetime.datetime.now():
                raise forms.ValidationError('A data de saída não pode ser superior a data atual.')
            if self.cleaned_data.get('motoristas'):
                for motorista in self.cleaned_data.get('motoristas'):
                    if motorista not in Vinculo.objects.filter(
                        id__in=MotoristaTemporario.objects.filter(
                            Q(validade_final__gte=self.cleaned_data.get('data_saida')) | Q(validade_final__isnull=True)
                        ).values_list('vinculo_pessoa', flat=True)
                    ):
                        self.add_error(
                            'motoristas',
                            f'O motorista {motorista.relacionamento.pessoa_fisica.nome} não possui portaria válida na data de saída desta viagem.',
                        )

        if cleaned_data.get('data_chegada') and cleaned_data.get('data_saida'):
            if cleaned_data.get('data_chegada') <= cleaned_data.get('data_saida'):
                self.add_error('data_chegada', 'A data de chegada não pode ser inferior a data de saída.')

        if cleaned_data.get('saida_odometro') and cleaned_data.get('chegada_odometro'):
            if cleaned_data['saida_odometro'] > cleaned_data['chegada_odometro']:
                self.add_error('saida_odometro', 'O valor do odômetro na saída não pode ser maior do que o valor da chegada.')

        return cleaned_data


class ViagemAgendamentoRespostaForm(forms.ModelFormPlus):
    agendamento = forms.ModelChoiceField(queryset=ViagemAgendamento.objects, widget=forms.HiddenInput())
    status = forms.CharField(label='Situação', widget=forms.Select(choices=status_as_choices()), required=True)
    viatura = forms.ModelChoiceField(
        label='Viaturas Disponíveis',
        queryset=Viatura.objects.filter(ativo=True),
        required=False,
        help_text='Só serão exibidas as viaturas do campus do solicitante e que não estejam escaladas para nenhum agendamento deferido no mesmo período deste agendamento.',
    )
    motoristas = forms.MultipleModelChoiceFieldPlus(
        label='Motoristas Disponíveis',
        queryset=Vinculo.objects,
        required=False,
        widget=FilteredSelectMultiplePlus('', True),
        help_text='Só serão exibidos os motoristas que não estão escalados para nenhum agendamento deferido no mesmo período deste agendamento.',
    )
    local_saida = forms.CharField(label='Local de Saída', required=False)

    fieldsets = ((None, {'fields': ('agendamento', 'status', 'viatura', 'motoristas', 'local_saida', 'obs')}),)

    class Meta:
        model = ViagemAgendamentoResposta
        fields = ('status', 'viatura', 'motoristas', 'obs')

    def __init__(self, *args, **kwargs):
        agendamento_id = kwargs.pop('agendamento_id')
        self.agendamento = ViagemAgendamento.objects.get(id=agendamento_id)
        viaturas_indisponiveis = kwargs.pop('viaturas_indisponiveis')
        motoristas_indisponiveis = kwargs.pop('motoristas_indisponiveis')

        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields['status'].initial = self.agendamento.status
        self.fields['agendamento'].initial = self.agendamento.id
        self.fields['local_saida'].initial = self.agendamento.local_saida
        self.fields['viatura'].widget.choices = viaturas_disponiveis_as_choices(viaturas_indisponiveis)
        self.fields['obs'].widget.attrs['cols'] = '100'
        self.fields['motoristas'].queryset = motoristas_disponiveis_as_queryset(motoristas_indisponiveis).order_by('pessoa__nome')
        self.fields['obs'].help_text = 'Esta viagem ainda não foi autorizada pela chefia. Em caso de deferimento, justifique o motivo.'
        if self.instance.pk:
            self.initial['motoristas'] = [t.pk for t in self.instance.motoristas.all()]

    def clean(self):
        if 'status' in self.cleaned_data and 'viatura' in self.cleaned_data:
            if self.cleaned_data['viatura'] is None and self.data['status'] == Situacao.DEFERIDA:  # indica que a solicitação foi deferida
                self.errors['viatura'] = ErrorList(['Indique a viatura reservada para a viagem.'])

        if 'status' in self.cleaned_data and 'motoristas' in self.cleaned_data:
            if not self.cleaned_data['motoristas'] and self.data['status'] == Situacao.DEFERIDA:  # indica que a solicitação foi deferida
                self.errors['motoristas'] = ErrorList(['Indique o(s) motorista(s) reservado(s) para a viagem.'])

        if self.data['status'] == Situacao.INDEFERIDA:
            self.cleaned_data['viatura'] = None
            self.cleaned_data['motoristas'] = Vinculo.objects.none()
        elif not self.agendamento.avaliado_em and not self.cleaned_data.get('obs'):
            self.errors['obs'] = ErrorList(['Esta viagem ainda não foi autorizada pela chefia. Justifique o motivo do deferimento.'])

        if self.cleaned_data.get('viatura'):
            if self.agendamento.vinculos_passageiros.count() > self.cleaned_data.get('viatura').lotacao:
                self.add_error(
                    'viatura',
                    'A quantidade de passageiros é maior do que a lotação máxima informada da viatura ({} lugares).'.format(
                        self.cleaned_data.get('viatura').lotacao
                    ),
                )

        return self.cleaned_data


class ViagemSaidaForm(forms.ModelFormPlus):
    agendamento_resposta = forms.ModelChoiceField(queryset=ViagemAgendamentoResposta.objects, widget=forms.HiddenInput())
    viatura = forms.ModelChoiceField(queryset=Viatura.objects, widget=forms.Select(), required=True)
    motoristas = forms.MultipleModelChoiceFieldPlus(
        label='Motoristas Disponíveis', queryset=Vinculo.objects, required=True, widget=FilteredSelectMultiplePlus('', True)
    )
    vinculos_passageiros = forms.MultipleModelChoiceFieldPlus(label='Passageiros', queryset=Vinculo.objects, required=True)
    turma = forms.ModelChoiceFieldPlus(
        Turma.objects,
        label='Turma',
        help_text='Selecione uma turma para adicionar todos os alunos como passageiros',
        required=False,
        widget=AutocompleteWidget(search_fields=Turma.SEARCH_FIELDS),
    )
    diario = forms.ModelChoiceFieldPlus(
        Diario.objects,
        label='Diário',
        required=False,
        help_text='Para encontrar um diário entre com a sigla do componente ou o id do diário.',
        widget=AutocompleteWidget(
            search_fields=Diario.SEARCH_FIELDS,
            form_filters=[
                ('turma', 'turma'),
                ('uo', 'turma__curso_campus__diretoria__setor__uo__in'),
                ('polo', 'turma__polo__in'),
                ('curso_campus', 'turma__curso_campus'),
                ('estrutura', 'turma__curso_campus__estrutura'),
                ('modalidade', 'turma__curso_campus__modalidade'),
            ],
        ),
    )
    lista_alunos = forms.CharFieldPlus(
        label='Alunos', help_text='Informe uma lista de matrículas separadas por vírgulas para adicionar vários alunos', required=False
    )
    saida_data = forms.DateTimeFieldPlus(label='Data e Hora')
    saida_odometro = forms.IntegerFieldPlus(
        label='Odômetro', help_text='Km rodados', max_length=6, widget=forms.TextInput(attrs={'class': 'integer-widget', 'size': '11'})
    )  # , 'readonly': 'readonly'

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'agendamento_resposta',
                    'saida_data',
                    'viatura',
                    'motoristas',
                    'saida_odometro',
                    'vinculos_passageiros',
                    'turma',
                    'diario',
                    'lista_alunos',
                    'saida_obs',
                )
            },
        ),
    )

    class Meta:
        model = Viagem
        fields = (
            'agendamento_resposta',
            'saida_data',
            'viatura',
            'motoristas',
            'saida_odometro',
            'vinculos_passageiros',
            'turma',
            'diario',
            'lista_alunos',
            'saida_obs',
        )

    def __init__(self, *args, **kwargs):
        resp_agendamento_id = kwargs.pop('resp_agendamento_id')
        self.resp_agendamento = ViagemAgendamentoResposta.objects.get(id=resp_agendamento_id)
        super().__init__(*args, **kwargs)
        if self.request.user.has_perm('frota.tem_acesso_viagem_operador'):
            self.fields['viatura'].widget.choices = viaturas_disponiveis_as_choices(
                [], self.resp_agendamento.agendamento.vinculo_solicitante.setor.uo
            )
        else:
            self.fields['viatura'].widget.choices = viaturas_disponiveis_as_choices([])
        if self.resp_agendamento.viatura:
            self.fields['viatura'].initial = self.resp_agendamento.viatura.id
            self.fields['saida_odometro'].initial = self.resp_agendamento.viatura.odometro
        self.fields['motoristas'].queryset = motoristas_disponiveis_as_queryset(retroativo=True).order_by('pessoa__nome')
        self.fields['vinculos_passageiros'].initial = self.resp_agendamento.agendamento.vinculos_passageiros.all()
        self.fields['agendamento_resposta'].initial = self.resp_agendamento.id
        self.fields['saida_data'].initial = self.resp_agendamento.agendamento.data_saida
        self.fields['saida_obs'].widget.attrs['cols'] = '100'

        if self.resp_agendamento.motoristas.exists():
            self.initial['motoristas'] = [t.pk for t in self.resp_agendamento.motoristas.all()]

    def clean_vinculos_passageiros(self):
        if 'vinculos_passageiros' in self.cleaned_data:
            resp_agendamento = self.cleaned_data['agendamento_resposta']
            if len(self.cleaned_data['vinculos_passageiros']) > resp_agendamento.viatura.lotacao - 1:
                self._errors['vinculos_passageiros'] = ErrorList(
                    [f'Este veículo tem capacidade para {resp_agendamento.viatura.lotacao} pessoas, incluindo o motorista']
                )
        return self.cleaned_data['vinculos_passageiros']

    def clean(self):
        if 'motoristas' not in self.cleaned_data:
            raise forms.ValidationError('Selecione o(s) motorista(s).')

        if 'viatura' in self.cleaned_data:
            ultima_viagem = Viagem.objects.filter(viatura=self.cleaned_data['viatura'], chegada_odometro__isnull=False).order_by('-chegada_data')
            if ultima_viagem.exists():
                if self.cleaned_data['saida_odometro'] and self.cleaned_data['saida_odometro'] < ultima_viagem[0].chegada_odometro:
                    self._errors['saida_odometro'] = ErrorList(
                        [
                            f'A quilometragem inicial não pode ser menor do que a quilometragem final da última viagem ({ultima_viagem[0].chegada_odometro} km).'
                        ]
                    )
        else:
            self._errors['viatura'] = ErrorList(['Selecione uma viatura.'])

        if self.cleaned_data.get('saida_data'):
            limite_inferior = self.cleaned_data['saida_data']
            limite_superior = self.resp_agendamento.agendamento.data_chegada

            viagens_em_andamento = Viagem.objects.filter(
                Q(saida_data__gte=limite_inferior, chegada_data__lte=limite_superior)
                | Q(saida_data__lte=limite_inferior, chegada_data__gte=limite_superior)
                | Q(saida_data__lte=limite_inferior, chegada_data__gte=limite_inferior, chegada_data__lte=limite_superior)
                | Q(saida_data__gte=limite_inferior, saida_data__lte=limite_superior, chegada_data__gte=limite_superior)
            )

            if self.cleaned_data.get('viatura') and viagens_em_andamento.filter(viatura=self.cleaned_data['viatura']).exists():
                raise forms.ValidationError(
                    'A viatura selecionada já está em uso na data de saída informada. <a href="/frota/viagem/{}/">Ver Viagem</a>.'.format(
                        viagens_em_andamento.filter(viatura=self.cleaned_data['viatura'])[0].id
                    )
                )

            if self.cleaned_data.get('motoristas'):
                for motorista in self.cleaned_data.get('motoristas'):
                    if viagens_em_andamento.filter(motoristas=motorista).exists():
                        raise forms.ValidationError(
                            f'O motorista selecionado já está em viagem na data de saída informada. <a href="/frota/viagem/{viagens_em_andamento.filter(motoristas=motorista)[0].id}">Ver Viagem</a>.'
                        )
                    if motorista not in Vinculo.objects.filter(
                        id__in=MotoristaTemporario.objects.filter(
                            Q(validade_final__gte=self.cleaned_data.get('saida_data')) | Q(validade_final__isnull=True)
                        ).values_list('vinculo_pessoa', flat=True)
                    ):
                        self.add_error(
                            'motoristas',
                            f'O motorista {motorista.relacionamento.pessoa_fisica.nome} não possui portaria válida na data de saída desta viagem.',
                        )

        return self.cleaned_data

    def save(self, *args, **kwargs):
        viagem = super().save()
        viagem.viatura.status = ViaturaStatus.objects.get(descricao='Em Trânsito')
        viagem.viatura.save()
        return viagem


class ViagemChegadaForm(forms.ModelFormPlus):
    chegada_data = forms.DateTimeFieldPlus(label='Data e Hora')
    chegada_odometro = forms.IntegerFieldPlus(
        label='Odômetro',
        help_text='Valor mostrado no odômetro na chegada',
        max_length=6,
        widget=forms.TextInput(attrs={'class': 'integer-widget', 'size': '11'}),
    )

    class Meta:
        model = Viagem
        fields = ('chegada_data', 'chegada_odometro', 'chegada_obs')

    def __init__(self, *args, **kwargs):
        resp_agendamento_id = kwargs.pop('resp_agendamento_id')
        resp_agendamento = ViagemAgendamentoResposta.objects.get(id=resp_agendamento_id)
        super().__init__(*args, **kwargs)
        self.fields['chegada_data'].initial = resp_agendamento.agendamento.data_chegada
        self.fields['chegada_obs'].widget.attrs['cols'] = '100'

    def clean_chegada_data(self):
        if 'chegada_data' in self.cleaned_data:
            if self.cleaned_data['chegada_data'] < self.instance.saida_data:
                self._errors['chegada_data'] = ErrorList(['A data de término da viagem não pode ser inferior a data de saída.'])
        return self.cleaned_data['chegada_data']

    def clean_chegada_odometro(self):
        if 'chegada_odometro' in self.cleaned_data:
            if self.cleaned_data['chegada_odometro'] < self.instance.saida_odometro:
                self._errors['chegada_odometro'] = ErrorList(['O valor de chegada do odômetro não pode ser inferior ao valor de saída do odômetro.'])
        return self.cleaned_data['chegada_odometro']

    def clean(self):
        return self.cleaned_data

    def save(self, force_insert=False, force_update=False, commit=True):
        viagem = super().save(commit=False)
        if commit:
            viagem.viatura.status = ViaturaStatus.objects.get(descricao='Disponível')
            viagem.viatura.odometro = self.data['chegada_odometro']
            viagem.viatura.save()
            viagem.save()
        return viagem


class ViaturaOrdemAbastecimentoForm(forms.ModelFormPlus):
    viatura = forms.ModelChoiceField(queryset=Viatura.objects, widget=forms.Select, required=True, empty_label=None)
    data = forms.DateTimeFieldPlus()
    odometro = forms.IntegerField(label='Odômetro', min_value=0)
    cupom_fiscal = forms.IntegerFieldPlus(label='Cupom Fiscal', help_text='Número do cupom fiscal', max_length=10)
    combustivel = forms.ModelChoiceField(label='Combustível', queryset=VeiculoCombustivel.objects)
    quantidade = forms.DecimalFieldPlus(label='Quantidade', help_text='Quantidade de litros ou de metros cúbicos utilizada no abastecimento')
    arquivo = forms.FileFieldPlus(label='Nota Fiscal', required=False)

    class Meta:
        model = ViaturaOrdemAbastecimento
        fields = ['viatura', 'data', 'odometro', 'cupom_fiscal', 'combustivel', 'quantidade', 'valor_total_nf', 'arquivo']

    def __init__(self, *args, **kwargs):
        viagem_id = None
        if 'viagem_id' in kwargs:
            viagem_id = kwargs.pop('viagem_id')
        super().__init__(*args, **kwargs)
        if viagem_id is not None:
            viagem = Viagem.objects.get(id=viagem_id)
            self.fields['viatura'].queryset = Viatura.objects.filter(pk=viagem.viatura.pk)
            self.fields['combustivel'].queryset = viagem.viatura.combustiveis.all()
        else:
            if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
                self.fields['viatura'].queryset = Viatura.objects.filter(campus=get_uo(self.request.user))

    def clean(self):
        if 'quantidade' in self.cleaned_data:
            if self.cleaned_data['quantidade'] == Decimal('0.00'):
                self._errors['quantidade'] = ErrorList(['Indique um valor diferente de "0,00".'])

        viatura = self.cleaned_data['viatura']
        if 'combustivel' in self.cleaned_data and self.cleaned_data['combustivel'].nome == 'Gás Natural':
            if self.cleaned_data.get('quantidade') and self.cleaned_data['quantidade'] > (viatura.capacidade_gnv or Decimal('0.00')):
                self._errors['quantidade'] = ErrorList(['Valor supera a capacidade do cilindro da viatura.'])
        elif 'quantidade' in self.cleaned_data and self.cleaned_data['quantidade'] > viatura.capacidade_tanque:
            self._errors['quantidade'] = ErrorList(['Valor supera a capacidade do tanque da viatura.'])

        if 'valor_unidade' in self.cleaned_data:
            if self.cleaned_data['valor_unidade'] == Decimal('0.00'):
                self._errors['valor_unidade'] = ErrorList(['Indique um valor diferente de "0,00".'])

        if 'oleo' in self.cleaned_data:
            if self.cleaned_data['oleo'] != '' and (self.cleaned_data['valor_oleo'] is None or self.cleaned_data['valor_oleo'] == Decimal('0.00')):
                if self.cleaned_data['valor_oleo'] == Decimal('0.00'):
                    self._errors['valor_oleo'] = ErrorList(['Indique um valor diferente de "0,00".'])
                else:
                    self._errors['valor_oleo'] = ErrorList(['Indique o valor gasto com o óleo.'])
            if self.cleaned_data['oleo'] == '' and (
                self.cleaned_data['valor_oleo'] is not None or self.cleaned_data['valor_oleo'] == Decimal('0.00')
            ):
                self._errors['oleo'] = ErrorList(['Indique a especificação do óleo.'])

        return self.cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        eh_motorista = (
            not self.request.user.has_perm('frota.tem_acesso_viagem_sistemico')
            and not self.request.user.has_perm('frota.tem_acesso_viagem_campus')
            and not self.request.user.has_perm('frota.tem_acesso_viagem_operador')
        )
        if eh_motorista:
            self.instance.validada = False
        else:
            self.instance.validada_por = self.request.user.get_vinculo()
            self.instance.validada_em = datetime.datetime.now()
        self.instance.informada_por = self.request.user.get_vinculo()
        self.instance.informada_em = datetime.datetime.now()

        return super().save(*args, **kwargs)


class PeriodoForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Saída')
    data_termino = forms.DateFieldPlus(label='Chegada')
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')
    grupo_viatura = forms.IntegerField(label='Grupo de Viaturas', required=False)
    id_viagem = forms.CharField(label='ID da Viagem', required=False)
    passageiro = forms.ModelChoiceField(
        label='Nome do Passageiro', required=False, queryset=Vinculo.objects, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['grupo_viatura'].widget = forms.Select(choices=grupos_viaturas_as_choices())
        if not self.request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(self.request.user).id)
            self.fields['uo'].empty_label = None


class FiltroViaturaForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Saída')
    data_termino = forms.DateFieldPlus(label='Chegada')
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')
    viatura = forms.ChainedModelChoiceField(
        Viatura.objects,
        label='Filtrar por Viatura:',
        empty_label='Selecione o Campus',
        initial='Todos',
        required=False,
        obj_label='placa_codigo_atual',
        form_filters=[('uo', 'campus')],
    )
    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['viatura'].empty_label = 'Todos'
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(id=get_uo(self.request.user).id)
            self.fields['uo'].initial = get_uo(self.request.user).id
            self.fields['uo'].empty_label = None
        else:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().all()


class CampusViaturaForm(forms.FormPlus):
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')
    grupo_viatura = forms.IntegerField(label='Grupo de Viaturas', required=False)

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['grupo_viatura'].widget = forms.Select(choices=grupos_viaturas_as_choices())
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(self.request.user).id)
            self.fields['uo'].empty_label = None


class MotoristaTemporarioFilterForm(forms.FormPlus):
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')
    categoria = forms.ChoiceField(label='Categoria', choices=MotoristaTemporario.CATEGORIA_CHOICES)
    disponibilidade = forms.ChoiceField(label='Disponibilidade', choices=MotoristaTemporario.DISPONIBILIDADE_CHOICES)
    nome = forms.CharField(label='Nome do Motorista', required=False)

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(self.request.user).id)
            self.fields['uo'].empty_label = None


class PeriodoRelatorioViagemForm(forms.FormPlus):
    METHOD = 'GET'
    data_inicio = forms.DateFieldPlus(label='Saída')
    data_termino = forms.DateFieldPlus(label='Chegada')
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')
    viatura = forms.ChainedModelChoiceField(
        Viatura.objects,
        label='Filtrar por Viatura:',
        empty_label='Selecione o Campus',
        initial='Todos',
        required=False,
        obj_label='placa_codigo_atual',
        form_filters=[('uo', 'campus')],
    )
    motorista = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(search_fields=('pessoa__nome',)),
        label='Motorista',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['viatura'].empty_label = 'Todos'
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(id=get_uo(self.request.user).id)
            self.fields['uo'].initial = get_uo(self.request.user).id
            self.fields['uo'].empty_label = None
        else:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().all()


class SolicitanteViagemForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Início')
    data_termino = forms.DateFieldPlus(label='Término')
    uo = forms.ModelChoiceField(label='Campus dos Solicitantes', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(self.request.user).id)
            self.fields['uo'].empty_label = None


class EstatisticasViagemForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Início')
    data_termino = forms.DateFieldPlus(label='Término')
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uo'].empty_label = None
        if not self.request.user.has_perm('frota.tem_acesso_viagem_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(pk=get_uo(self.request.user).id)


class ViagemForm(forms.ModelFormPlus):
    saida_data = forms.DateTimeFieldPlus(label='Data da Saída', help_text='dd/mm/aaaa')
    chegada_data = forms.DateTimeFieldPlus(label='Data da Chegada', help_text='dd/mm/aaaa')
    viatura = forms.ModelChoiceField(label='Viatura', queryset=Viatura.objects.filter(ativo=True), required=True)

    saida_odometro = forms.IntegerFieldPlus(
        label='Km Inicial', help_text='Quilometragem Inicial', max_length=6, widget=forms.TextInput(attrs={'class': 'integer-widget', 'size': '11'})
    )  # , 'readonly': 'readonly'
    saida_obs = forms.CharField(label='Obs na Saída', widget=forms.Textarea(), required=False)
    chegada_odometro = forms.IntegerFieldPlus(
        label='Km Final', help_text='Quilometragem Final', max_length=6, widget=forms.TextInput(attrs={'class': 'integer-widget', 'size': '11'})
    )  # , 'readonly': 'readonly'
    chegada_obs = forms.CharField(label='Obs na Chegada', widget=forms.Textarea(), required=False)
    vinculos_passageiros = forms.MultipleModelChoiceFieldPlus(label='Passageiros', queryset=Vinculo.objects)

    class Meta:
        model = Viagem
        fields = (
            'viatura',
            'motoristas',
            'vinculos_passageiros',
            'saida_odometro',
            'saida_data',
            'saida_obs',
            'chegada_odometro',
            'chegada_data',
            'chegada_obs',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculos_passageiros'].initial = self.instance.agendamento_resposta.agendamento.vinculos_passageiros.all()

    def clean(self):
        if self.cleaned_data.get('viatura') and self.cleaned_data.get('saida_data'):
            ultima_viagem = Viagem.objects.filter(
                viatura=self.cleaned_data['viatura'], chegada_odometro__isnull=False, chegada_data__lt=self.cleaned_data.get('saida_data')
            ).order_by('-chegada_data')
            if (
                ultima_viagem.exists()
                and self.cleaned_data.get('saida_odometro')
                and self.cleaned_data.get('saida_odometro') < ultima_viagem[0].chegada_odometro
            ):
                self._errors['saida_odometro'] = ErrorList(
                    [
                        f'A quilometragem inicial não pode ser menor do que a quilometragem final da última viagem ({ultima_viagem[0].chegada_odometro} - Viagem #{ultima_viagem[0].agendamento_resposta.agendamento.id}).'
                    ]
                )
        return self.cleaned_data


class ManutencaoViaturaForm(forms.ModelFormPlus):
    arquivo_nf_pecas = forms.FileFieldPlus(label='Nota Fiscal das Peças', required=False)
    arquivo_nf_servicos = forms.FileFieldPlus(label='Nota Fiscal dos Serviços')
    obs = forms.CharField(widget=forms.Textarea(), label='Observação', required=False)
    odometro = forms.IntegerFieldPlus(label='Odômetro')

    class Meta:
        model = ManutencaoViatura
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['viatura'].queryset = Viatura.objects.filter(campus=get_uo(self.request.user))


class MaquinaForm(forms.ModelFormPlus):
    combustiveis = forms.ModelMultipleChoiceField(label='Combustíveis', widget=forms.CheckboxSelectMultiplePlus, queryset=VeiculoCombustivel.objects)
    patrimonio = forms.ModelChoiceField(label='Patrimônio', queryset=Inventario.objects, widget=AutocompleteWidget(minChars=5))

    class Meta:
        model = Maquina
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        permite_sem_patrimonio = Configuracao.get_valor_por_chave('frota', 'viatura_sem_patrimonio')
        if permite_sem_patrimonio == 'True':
            self.fields['patrimonio'].required = False
        else:
            self.fields['campus'].required = False
            self.fields['campus'].widget = forms.HiddenInput()

    @transaction.atomic()
    def save(self, *args, **kwargs):
        if self.instance.patrimonio and self.instance.patrimonio.carga_contabil:
            self.instance.campus = self.instance.patrimonio.carga_contabil.campus

        return super().save(*args, **kwargs)


class FiltroMaquinaForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Saída')
    data_termino = forms.DateFieldPlus(label='Chegada')
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.request.user.has_perm('frota.tem_acesso_maquina_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(id=get_uo(self.request.user).id)
            self.fields['uo'].initial = get_uo(self.request.user).id
            self.fields['uo'].empty_label = None
        else:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().all()


class MaquinaOrdemAbastecimentoForm(forms.ModelFormPlus):
    obs = forms.CharField(label='Observações', widget=forms.Textarea(), required=False)

    class Meta:
        model = MaquinaOrdemAbastecimento
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['maquina'].queryset = Maquina.objects.filter(campus=get_uo(self.request.user))

    def clean(self):
        quantidade = self.cleaned_data.get('quantidade')
        if quantidade:
            if quantidade == Decimal('0.00'):
                self._errors['quantidade'] = ErrorList(['Indique um valor diferente de "0,00".'])

            maquina = self.cleaned_data.get('maquina')

            if maquina and quantidade and maquina.capacidade_tanque and quantidade > maquina.capacidade_tanque:
                self._errors['quantidade'] = ErrorList(['Valor supera a capacidade do tanque da viatura.'])

        return self.cleaned_data


class ViagemMotoristaForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Saída')
    data_termino = forms.DateFieldPlus(label='Chegada')
    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.suap(), required=False, empty_label='Todos')
    motorista = forms.ModelChoiceFieldPlus(
        queryset=MotoristaTemporario.objects,
        widget=AutocompleteWidget(search_fields=('vinculo_pessoa__pessoa__nome',)),
        label='Nome do Motorista',
        required=True,
    )
    quantidade_diarias = forms.IntegerFieldPlus(label='Quantidade de Diárias', required=False)

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motorista'].queryset = MotoristaTemporario.objects.filter(
            vinculo_pessoa__tipo_relacionamento__model__in=['servidor', 'prestadorservico']
        )
        if not self.request.user.has_perm('frota.tem_acesso_maquina_sistemico'):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().filter(id=get_uo(self.request.user).id)
            self.fields['uo'].initial = get_uo(self.request.user).id
            self.fields['uo'].empty_label = None
        else:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.suap().all()


class ControleRevisaoForm(forms.FormPlus):
    METHOD = 'GET'

    SITUACAO_ATRASO = 'Revisão com atraso de mais de 30 dias ou 1000km'
    SITUACAO_PREVISTA = 'Revisão com atraso de até 30 dias ou 1000km'
    SITUACAO_REVISAO_KM = 'Odômetro com menos de 1000km para a próxima revisão'

    uo = forms.ModelChoiceField(label='Campus', queryset=UnidadeOrganizacional.objects.uo(), required=False, empty_label='Todos')
    viatura = forms.ChainedModelChoiceField(
        Viatura.objects,
        label='Filtrar por Viatura:',
        empty_label='Selecione o Campus',
        initial='Todos',
        required=False,
        obj_label='placa_codigo_atual',
        form_filters=[('uo', 'campus')],
    )
    situacao = forms.ChoiceField(
        label='Filtrar por Situação',
        required=False,
        choices=[
            ('', 'Todos'),
            (SITUACAO_ATRASO, SITUACAO_ATRASO),
            (SITUACAO_PREVISTA, SITUACAO_PREVISTA),
            (SITUACAO_REVISAO_KM, SITUACAO_REVISAO_KM),
        ],
    )


class EditarDataProximaRevisaoForm(forms.ModelFormPlus):
    data_proxima_revisao = forms.DateFieldPlus(label='Data da Próxima Revisão')
    url = forms.CharField(required=False, label='Url', widget=forms.HiddenInput())

    class Meta:
        model = Viatura
        fields = ('data_proxima_revisao',)

    def __init__(self, *args, **kwargs):
        self.url = kwargs.pop('url')
        super().__init__(*args, **kwargs)
        self.fields['url'].initial = self.url


class ManutencaoMaquinaForm(forms.ModelFormPlus):
    arquivo_nf_pecas = forms.FileFieldPlus(label='Nota Fiscal das Peças', required=False)
    arquivo_nf_servicos = forms.FileFieldPlus(label='Nota Fiscal dos Serviços')

    class Meta:
        model = ManutencaoMaquina
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('frota.tem_acesso_viatura_sistemico'):
            self.fields['maquina'].queryset = Maquina.objects.filter(campus=get_uo(self.request.user))
        self.fields['tipo_servico'].queryset = TipoServicoMaquina.objects.filter(ativo=True)


class EditarAgendamentoDeferidoForm(forms.ModelFormPlus):
    data_saida = forms.DateTimeFieldPlus(label='Saída', required=True)
    data_chegada = forms.DateTimeFieldPlus(label='Chegada', required=True)
    vinculos_passageiros = forms.MultipleModelChoiceFieldPlus(label='Passageiros', queryset=Vinculo.objects, required=False)

    class Meta:
        model = EdicaoAgendamentoDeferido
        fields = ('data_saida', 'data_chegada', 'vinculos_passageiros')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['data_saida'] = self.instance.agendamento.data_saida
        self.initial['data_chegada'] = self.instance.agendamento.data_chegada
        self.initial['vinculos_passageiros'] = [pessoa.id for pessoa in self.instance.agendamento.vinculos_passageiros.all()]


class MultaViagemForm(forms.ModelFormPlus):
    condutor = forms.ModelChoiceField(
        label='Condutor',
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    class Meta:
        model = MultaViagem
        fields = ('motivo', 'valor', 'condutor', 'pontuacao_cnh', 'data_vencimento', 'comprovante')
