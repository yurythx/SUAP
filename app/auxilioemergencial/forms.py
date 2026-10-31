import datetime

from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.backends.utils import format_number

from auxilioemergencial.models import (
    PARECER_CHOICES,
    PARECER_FORM_CHOICES,
    PENDENTE_DOCUMENTACAO,
    SEM_PARECER,
    DocumentoAluno,
    Edital,
    InscricaoAluno,
    InscricaoAlunoConectado,
    InscricaoDispositivo,
    InscricaoInternet,
    InscricaoMaterialPedagogico,
    IntegranteFamiliar,
    TipoAuxilio,
)
from comum.models import Ano, Configuracao
from comum.utils import get_uo
from djtools import forms
from rh.models import UnidadeOrganizacional


class EditalForm(forms.ModelFormPlus):
    descricao = forms.CharFieldPlus(label='Descrição', widget=forms.Textarea())
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().all(), label='Campus')
    tipo_auxilio = forms.ModelMultipleChoiceField(
        label='Tipos de Auxílio', queryset=TipoAuxilio.objects, widget=FilteredSelectMultiple('TipoAuxilio', True), required=True
    )

    class Meta:
        models = Edital
        fields = (
            'descricao',
            'campus',
            'tipo_auxilio',
            'link_edital',
            'data_inicio',
            'data_termino',
            'data_divulgacao',
            'impedir_fic',
            'impedir_pos_graduacao',
            'arquivo_instrucoes',
            'ativo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)
            self.fields['impedir_fic'].initial = True
            self.fields['impedir_pos_graduacao'].initial = True
        self.fields['arquivo_instrucoes'].required = False

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get('data_inicio')
            and self.cleaned_data.get('data_termino')
            and cleaned_data.get('data_inicio') > self.cleaned_data.get('data_termino')
        ):
            self.add_error('data_termino', 'A data de término deve ser maior do que a data de início.')
        return cleaned_data


class InscricaoAlunoForm(forms.ModelFormPlus):
    cpf = forms.BrCpfField(label='CPF', required=False)
    tem_matricula_outro_instituto = forms.ChoiceField(
        label='Possui matrícula em outra Instituição de Ensino?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )
    foi_atendido_outro_instituto = forms.ChoiceField(
        label='Foi atendido por algum auxílio emergencial de inclusão digital ou auxílio semelhante em outra Instituição de Ensino?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )
    mora_com_pessoas_instituto = forms.ChoiceField(
        label='Você mora com outras pessoas que também estão matriculadas no IFRN?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )
    fieldsets = (
        (
            'Informações para Contato',
            {
                'fields': (
                    ('telefones_contato'),
                    ('emails_contato'),
                )
            },
        ),
        (
            'Dados Pessoais',
            {
                'fields': (
                    ('tem_matricula_outro_instituto'),
                    ('foi_atendido_outro_instituto',),
                    ('mora_com_pessoas_instituto'),
                    ('pessoas_do_domicilio'),
                )
            },
        ),
        (
            'Dados Bancários',
            {
                'fields': (
                    ('banco'),
                    ('numero_agencia'),
                    ('numero_conta', 'tipo_conta'),
                    ('operacao'),
                    ('cpf'),
                )
            },
        ),
    )

    class Meta:
        model = InscricaoAluno
        exclude = ('aluno', 'data_cadastro', 'renda_bruta_familiar', 'renda_per_capita')

    class Media:
        js = ['/static/auxilioemergencial/js/inscricaoform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['banco'].required = False
        self.fields['numero_agencia'].required = False
        self.fields['tipo_conta'].required = False
        self.fields['numero_conta'].required = False
        self.fields['operacao'].required = False
        self.fields['cpf'].required = False
        self.fields[
            'banco'
        ].help_text = 'A conta deve estar obrigatoriamente no nome do estudante. Caso não possua conta em seu nome, deixe em branco nesse momento e providencie o mais rápido possível, pois terá que encaminhar ao Serviço Social após a divulgação do resultado, se tiver a solicitação deferida. Atenção: não coloque contas que estão no nome de outras pessoas. Se isso acontecer seu pagamento não será efetivado'
        self.fields[
            'mora_com_pessoas_instituto'
        ].label = f'Você mora com outras pessoas que também estão matriculadas no {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")}?'

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('mora_com_pessoas_instituto') == 'True' and not self.cleaned_data.get('pessoas_do_domicilio'):
            self.add_error('pessoas_do_domicilio', 'Informe os nomes dos estudantes.')
        return cleaned_data


class IntegranteFamiliarForm(forms.ModelFormPlus):
    class Meta:
        model = IntegranteFamiliar
        fields = '__all__'


class InscricaoInternetForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Concluir Inscrição'
    declaracao_1 = forms.BooleanField(
        label='Declaro que as informações na caracterização socioeconômica foram atualizadas no momento dessa inscrição.', required=True
    )
    declaracao_2 = forms.BooleanField(
        label='Declaro que, informarei ao Serviço Social do meu Campus no caso de qualquer alteração da minha condição socioeconômica.', required=True
    )
    declaracao_3 = forms.BooleanField(
        label='Declaro que li e estou de acordo com todas as condições estabelecidas no referido edital, assumo inteira responsabilidade pelas informações prestadas e declaro estar ciente das penalidades cabíveis em caso de omissão de informações ou qualquer falsa declaração prestada em qualquer momento deste processo seletivo.',
        required=True,
    )
    fieldsets = (
        (
            'Dados da Solicitação',
            {
                'fields': (
                    ('situacao_acesso_internet'),
                    ('valor_solicitacao'),
                    ('justificativa_solicitacao'),
                )
            },
        ),
        (
            'Declaração de Aceite',
            {
                'fields': (
                    ('declaracao_1'),
                    ('declaracao_2'),
                    ('declaracao_3'),
                )
            },
        ),
    )

    class Meta:
        model = InscricaoInternet
        fields = ('situacao_acesso_internet', 'justificativa_solicitacao', 'valor_solicitacao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_solicitacao'].widget = forms.Textarea()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('valor_solicitacao') and cleaned_data.get('valor_solicitacao') > 100.00:
            self.add_error('valor_solicitacao', 'O valor máximo deste auxílio é de R$ 100,00.')
        return cleaned_data


class InscricaoDispositivoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Concluir Inscrição'
    declaracao_1 = forms.BooleanField(
        label='Declaro que as informações na caracterização socioeconômica foram atualizadas no momento dessa inscrição.', required=True
    )
    declaracao_2 = forms.BooleanField(
        label='Declaro que, informarei ao Serviço Social do meu Campus no caso de qualquer alteração da minha condição socioeconômica.', required=True
    )
    declaracao_3 = forms.BooleanField(
        label='Declaro que li e estou de acordo com todas as condições estabelecidas no referido edital, assumo inteira responsabilidade pelas informações prestadas e declaro estar ciente das penalidades cabíveis em caso de omissão de informações ou qualquer falsa declaração prestada em qualquer momento deste processo seletivo.',
        required=True,
    )
    fieldsets = (
        (
            'Dados da Solicitação',
            {
                'fields': (
                    ('situacao_equipamento'),
                    ('valor_solicitacao'),
                    ('justificativa_solicitacao'),
                )
            },
        ),
        (
            'Declaração de Aceite',
            {
                'fields': (
                    ('declaracao_1'),
                    ('declaracao_2'),
                    ('declaracao_3'),
                )
            },
        ),
    )

    class Meta:
        model = InscricaoDispositivo
        fields = ('situacao_equipamento', 'justificativa_solicitacao', 'valor_solicitacao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_solicitacao'].widget = forms.Textarea()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('valor_solicitacao') and cleaned_data.get('valor_solicitacao') > 1500.00:
            self.add_error('valor_solicitacao', 'O valor máximo deste auxílio é de R$ 1.500,00.')
        return cleaned_data


class InscricaoMaterialPedagogicoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Concluir Inscrição'

    class Meta:
        model = InscricaoMaterialPedagogico
        fields = ('descricao_material', 'especificacao_material', 'valor_solicitacao', 'justificativa_solicitacao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao_material'].widget = forms.Textarea()
        self.fields['especificacao_material'].widget = forms.Textarea()
        self.fields['justificativa_solicitacao'].widget = forms.Textarea()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('valor_solicitacao') and cleaned_data.get('valor_solicitacao') > 400.00:
            self.add_error('valor_solicitacao', 'O valor máximo deste auxílio é de R$ 400,00.')
        return cleaned_data


class InscricaoAlunoConectadoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Concluir Inscrição'
    declaracao_1 = forms.BooleanField(
        label='Declaro que as informações por mim prestadas no processo seletivo são verdadeiras e que estão sujeitas à verificação em qualquer época do ano por parte do Serviço Social da Diretoria de Gestão de Atividades Estudantis (DIGAE) ou Serviço Social do Campus e, em caso de incompatibilidade entre as informações prestadas por mim e verificadas pelo Serviço Social do Campus, os chips serão desativados.',
        required=True,
    )
    declaracao_2 = forms.BooleanField(
        label='Declaro estar ciente que terei meu chip desativado caso sejam identificadas omissões e/ou fraudes nas informações apresentadas de renda própria e/ou da composição do grupo familiar.',
        required=True,
    )
    declaracao_3 = forms.BooleanField(
        label='Declaro que assumo o compromisso de comunicar ao Serviço Social do Campus, qualquer alteração socioeconômica que interfira na renda do grupo familiar, inclusive início de estágio remunerado.',
        required=True,
    )
    declaracao_4 = forms.BooleanField(
        label='Declaro que estou ciente de que é crime a omissão ou fornecimento de informações falsas, conforme estabelecido no art. 299, do Código Penal Brasileiro, Lei nº 2.848/1940 e que poderei responder às sanções disciplinares previstas no Código de Conduta dos(as) Estudantes e Regimento Geral do IFRN.',
        required=True,
    )
    declaracao_5 = forms.BooleanField(
        label='Declaro que utilizarei o CHIP, exclusivamente, para realização das Atividades Acadêmicas.', required=True
    )
    declaracao_6 = forms.BooleanField(
        label='Declaro estar ciente que a infração a quaisquer artigos do respectivo edital poderá implicar no meu desligamento ou suspensão do referido Projeto.',
        required=True,
    )
    foi_contemplado_servico_internet = forms.ChoiceField(
        label='Você foi contemplado(a) com o auxílio emergencial para contratação de serviço de internet?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )
    localidade_possui_cobertura = forms.ChoiceField(
        label='A localidade que você mora é coberta pelas operadoras Claro ou Oi?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )

    fieldsets = (
        (
            'Dados da Solicitação',
            {
                'fields': (
                    ('casa_possui_servico_internet'),
                    ('foi_contemplado_servico_internet'),
                    ('localidade_possui_cobertura'),
                    ('justificativa_solicitacao'),
                )
            },
        ),
        (
            'Declaração de Aceite',
            {
                'fields': (
                    ('declaracao_1'),
                    ('declaracao_2'),
                    ('declaracao_3'),
                    ('declaracao_4'),
                    ('declaracao_5'),
                    ('declaracao_6'),
                )
            },
        ),
    )

    class Meta:
        model = InscricaoAlunoConectado
        fields = ('casa_possui_servico_internet', 'foi_contemplado_servico_internet', 'localidade_possui_cobertura', 'justificativa_solicitacao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_solicitacao'].widget = forms.Textarea()
        self.fields[
            'declaracao_4'
        ].label = f'Declaro que estou ciente de que é crime a omissão ou fornecimento de informações falsas, conforme estabelecido no art. 299, do Código Penal Brasileiro, Lei nº 2.848/1940 e que poderei responder às sanções disciplinares previstas no Código de Conduta dos(as) Estudantes e Regimento Geral do {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")}.'


class AssinaturaResponsavelForm(forms.ModelFormPlus):
    arquivo = forms.FileFieldPlus(label='Termo de Compromisso Assinado')

    class Meta:
        model = DocumentoAluno
        fields = ('arquivo',)


class InscricaoAusenciaRendaForm(forms.ModelFormPlus):
    valor = forms.DecimalFieldPlus(label='Valor que a família está recebendo de doações e/ou ajuda de terceiros')
    arquivo = forms.FileFieldPlus(label='Declaração de ausência de renda da família')

    class Meta:
        model = DocumentoAluno
        fields = (
            'valor',
            'arquivo',
        )

    def clean(self):
        if self.cleaned_data.get('valor') is not None and self.cleaned_data.get('valor') <= 0:
            self.add_error('valor', 'Informe um valor maior do que 0.00')

        return self.cleaned_data


class ParecerInscricaoForm(forms.FormPlus):
    parecer = forms.ChoiceField(label='Parecer', choices=PARECER_CHOICES)
    valor = forms.DecimalFieldPlus(label='Valor Concedido', required=False)
    documentacao_pendente = forms.CharFieldPlus(label='Indique qual documentação esse estudante deve anexar', required=False)
    data_limite = forms.DateFieldPlus(label='Indique a data limite para que o estudante anexe essa documentação', required=False)
    url = forms.CharField(required=False, label='Url', widget=forms.HiddenInput())

    class Media:
        js = ['/static/auxilioemergencial/js/parecerinscricaoform.js']

    def __init__(self, *args, **kwargs):
        self.inscricao = kwargs.pop('inscricao', None)
        self.url = kwargs.pop('url', None)
        super().__init__(*args, **kwargs)
        self.fields['url'].initial = self.url
        self.fields['parecer'].choices = PARECER_FORM_CHOICES
        if self.inscricao.parecer != SEM_PARECER:
            self.fields['parecer'].initial = self.inscricao.parecer

        if self.inscricao.get_tipo_auxilio() != 'CHP':
            self.fields['valor'].initial = self.inscricao.valor_concedido
        else:
            del self.fields['valor']
        self.fields['documentacao_pendente'].initial = self.inscricao.documentacao_pendente
        self.fields['data_limite'].initial = self.inscricao.data_limite_envio_documentacao

    def clean(self):
        if self.inscricao.get_tipo_auxilio() != 'CHP' and self.cleaned_data.get('parecer') == 'Deferido' and not self.cleaned_data.get('valor'):
            self.add_error('valor', 'Informe o valor concedido.')

        if self.cleaned_data.get('parecer') == PENDENTE_DOCUMENTACAO and not self.cleaned_data.get('documentacao_pendente'):
            self.add_error('documentacao_pendente', 'Informe qual é a documentação pendente.')
        if self.cleaned_data.get('parecer') == PENDENTE_DOCUMENTACAO and not self.cleaned_data.get('data_limite'):
            self.add_error('data_limite', 'Informe a data limite para o envio da documentação pendente.')
        if self.inscricao.get_tipo_auxilio() != 'CHP' and self.cleaned_data.get('valor'):
            try:
                format_number(self.cleaned_data.get('valor'), max_digits=6, decimal_places=2)
            except Exception:
                self.add_error('valor', 'Formato inválido. Use o seguinte formato: "9.999,99"')

        return self.cleaned_data


class AtualizarDadosBancariosForm(forms.ModelFormPlus):
    cpf = forms.BrCpfField(label='CPF', required=True)

    class Meta:
        model = InscricaoAluno
        fields = ('banco', 'numero_agencia', 'tipo_conta', 'numero_conta', 'operacao', 'cpf')


class AssinarTermoForm(forms.FormPlus):
    declaracao_1 = forms.BooleanField(
        label='Das normas que regem os Auxílios e Ações Emergenciais de Assistência Estudantil no contexto do Ensino Remoto do IFRN'
    )
    declaracao_2 = forms.BooleanField(
        label='De que a infração a quaisquer dispositivos deste Edital poderá implicar no meu desligamento ou suspensão dos auxílios constantes no item 1'
    )
    declaracao_3 = forms.BooleanField(label='De que terei de prestar contas dos referidos auxílios, conforme descrito neste Edital')
    declaracao_4 = forms.BooleanField(label='De que terei o dever de zelar pelo meu desempenho acadêmico')
    declaracao_5 = forms.BooleanField(
        label='Autorizo a verificação dos meus dados, sabendo que a omissão ou falsidade de informações resultará nas penalidades cabíveis, além da imediata devolução dos valores indevidamente recebidos'
    )
    declaracao_6 = forms.BooleanField(
        label='Assumo, pois, o compromisso de utilizar o recurso conforme consta neste Edital, bem como em seus anexos, no intuito de garantir o meu acesso às aulas e demais atividades remotas, bem como de cumprir tudo o que está previsto no referido edital'
    )

    def __init__(self, *args, **kwargs):
        self.eh_maior_dezoito_anos = kwargs.pop('eh_maior_dezoito_anos', None)
        super().__init__(*args, **kwargs)
        self.fields[
            'declaracao_1'
        ].label = f'Das normas que regem os Auxílios e Ações Emergenciais de Assistência Estudantil no contexto do Ensino Remoto do {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")}.'
        if not self.eh_maior_dezoito_anos:
            self.fields['termo'] = forms.FileFieldPlus(label='Termo de Compromisso', required=True)


class AdicionarDocumentoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoAluno
        fields = ('descricao', 'arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].required = False
        self.fields['arquivo'].required = False
        if self.instance.pk:
            self.fields['descricao'].widget.attrs['readonly'] = 'readonly'

    def clean(self):
        if not self.cleaned_data.get('descricao'):
            self.add_error('descricao', 'Informe a descrição do documento.')
        if not self.cleaned_data.get('arquivo'):
            self.add_error('arquivo', 'Faça o upload do arquivo.')
        return self.cleaned_data


class AdicionarDocumentoObrigatorioForm(forms.FormPlus):
    comprovante_endereco = forms.FileFieldPlus(label='Comprovante de Endereço')

    def __init__(self, *args, **kwargs):
        self.integrantes = kwargs.pop('integrantes', None)
        self.eh_material = kwargs.pop('eh_material', None)
        self.aluno = kwargs.pop('aluno', None)
        super().__init__(*args, **kwargs)
        tem_documento_atual = False
        if DocumentoAluno.objects.filter(
            descricao='Comprovante de Residência', aluno=self.aluno, data_cadastro__year=datetime.datetime.now().year
        ).exists():
            del self.fields['comprovante_endereco']
            tem_documento_atual = True
        for item in self.integrantes:
            label = f'Comprovante de Renda - {item.nome}'
            if (
                not DocumentoAluno.objects.filter(descricao=label, aluno=self.aluno, data_cadastro__year=datetime.datetime.now().year).exists()
                or item.remuneracao != item.ultima_remuneracao
            ):
                self.fields[f'{item.id}'] = forms.FileFieldPlus(label=label, required=True)
                tem_documento_atual = False
        if self.eh_material:
            if not DocumentoAluno.objects.filter(
                descricao='Parecer emitido pelo NAPNE e/ou ETEP', aluno=self.aluno, data_cadastro__year=datetime.datetime.now().year
            ).exists():
                self.fields['parecer'] = forms.FileFieldPlus(label='Parecer emitido pelo NAPNE e/ou ETEP', required=True)
                tem_documento_atual = False
        if not DocumentoAluno.objects.filter(descricao='Documentos Complementares', aluno=self.aluno).exists():
            self.fields['documentacao_complementar'] = forms.FileFieldPlus(label='Documentos complementares', required=False)
            tem_documento_atual = False
        if tem_documento_atual:
            self.SUBMIT_LABEL = 'Documentação já cadastrada, continue com a sua inscrição >>>'


class FolhaPagamentoForm(forms.FormPlus):
    METHOD = 'GET'
    ver_nome = forms.BooleanField(label='Nome', initial=False, required=False)
    ver_matricula = forms.BooleanField(label='Matrícula', initial=False, required=False)
    ver_cpf = forms.BooleanField(label='CPF', initial=False, required=False)
    ver_banco = forms.BooleanField(label='Banco', initial=False, required=False)
    ver_agencia = forms.BooleanField(label='Agência', initial=False, required=False)
    ver_operacao = forms.BooleanField(label='Operação', initial=False, required=False)
    ver_conta = forms.BooleanField(label='Número da Conta', initial=False, required=False)
    ver_tipo_passe = forms.BooleanField(label='Tipo de Passe', initial=False, required=False)
    ver_valor_padrao = forms.BooleanField(label='Valor Padrão', initial=False, required=False)
    ver_valor_pagar = forms.BooleanField(label='Valor a Pagar', initial=False, required=False)
    campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.uo().all(), label='Campus', required=True)
    ano = forms.ModelChoiceField(queryset=Ano.objects, label='Ano', required=False)
    edital = forms.ModelChoiceFieldPlus(label='Edital', queryset=Edital.objects, required=False)

    mes = forms.ChoiceField(
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
        required=False,
    )
    fieldsets = (
        (
            'Filtros',
            {
                'fields': (
                    ('edital'),
                    ('campus', 'ano', 'mes'),
                )
            },
        ),
        (
            'Opções de Exibição',
            {
                'fields': (
                    ('ver_nome', 'ver_matricula', 'ver_cpf'),
                    ('ver_banco', 'ver_agencia'),
                    ('ver_operacao', 'ver_conta'),
                    ('ver_tipo_passe', 'ver_valor_padrao', 'ver_valor_pagar'),
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.tipo = kwargs.pop('tipo', None)
        super().__init__(*args, **kwargs)
        if self.tipo == 'INT':
            self.fieldsets = (
                (
                    'Filtros',
                    {
                        'fields': (
                            ('edital'),
                            ('campus', 'ano', 'mes'),
                        )
                    },
                ),
                (
                    'Opções de Exibição',
                    {
                        'fields': (
                            ('ver_nome', 'ver_matricula', 'ver_cpf'),
                            ('ver_banco', 'ver_agencia'),
                            ('ver_operacao', 'ver_conta'),
                            ('ver_valor_pagar'),
                        )
                    },
                ),
            )
        elif self.tipo == 'CHP':
            self.fieldsets = (
                (
                    'Filtros',
                    {
                        'fields': (
                            ('edital'),
                            ('campus',),
                        )
                    },
                ),
                (
                    'Opções de Exibição',
                    {'fields': (('ver_nome', 'ver_matricula', 'ver_cpf'),)},
                ),
            )
        else:
            self.fieldsets = (
                (
                    'Filtros',
                    {
                        'fields': (
                            ('edital'),
                            ('campus',),
                        )
                    },
                ),
                (
                    'Opções de Exibição',
                    {
                        'fields': (
                            ('ver_nome', 'ver_matricula', 'ver_cpf'),
                            ('ver_banco', 'ver_agencia'),
                            ('ver_operacao', 'ver_conta'),
                            ('ver_valor_pagar'),
                        )
                    },
                ),
            )

        if not self.request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            id_do_campus = get_uo(self.request.user).id
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=id_do_campus)
            self.fields['campus'].initial = id_do_campus
            self.fields['edital'].queryset = Edital.objects.filter(campus_id=id_do_campus)

    def clean(self):
        if self.tipo == 'INT' and not self.cleaned_data.get('ano'):
            raise forms.ValidationError('Selecione o ano.')
        return self.cleaned_data


class DataEncerramentoForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data de Encerramento do Auxílio')


class PrestacaoContasDispositivoForm(forms.ModelFormPlus):
    url = forms.CharField(required=False, label='Url', widget=forms.HiddenInput())

    class Meta:
        model = InscricaoDispositivo
        fields = ('arquivo_prestacao_contas',)

    def __init__(self, *args, **kwargs):
        self.url = kwargs.pop('url', None)
        super().__init__(*args, **kwargs)
        self.fields['url'].initial = self.url


class PrestacaoContasForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoDispositivo
        fields = ('arquivo_prestacao_contas',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'arquivo_prestacao_contas'
        ].help_text = 'Insira aqui, em arquivo único, todos os documentos necessários para a sua prestação de contas.'
        self.fields['arquivo_prestacao_contas'].label = 'Documento(s) para prestação de contas'


class PrestacaoContasMaterialForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoMaterialPedagogico
        fields = ('arquivo_prestacao_contas',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'arquivo_prestacao_contas'
        ].help_text = 'Insira aqui, em arquivo único, todos os documentos necessários para a sua prestação de contas.'
        self.fields['arquivo_prestacao_contas'].label = 'Documento(s) para prestação de contas'


class PendenciaDispositivoForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoDispositivo
        fields = (
            'pendencia_prestacao_contas',
            'data_limite_envio_prestacao_contas',
        )


class PendenciaMaterialForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoMaterialPedagogico
        fields = (
            'pendencia_prestacao_contas',
            'data_limite_envio_prestacao_contas',
        )


class GRUDispositivoForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoDispositivo
        fields = ('arquivo_gru',)


class GRUMaterialForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoMaterialPedagogico
        fields = ('arquivo_gru',)


class ComprovanteGRUDispositivoForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoDispositivo
        fields = ('comprovante_gru',)


class ComprovanteGRUMaterialForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoMaterialPedagogico
        fields = ('comprovante_gru',)


class FiltraPrestacaoForm(forms.FormPlus):
    METHOD = 'GET'
    busca = forms.CharFieldPlus(label='Buscar aluno', required=False)
    campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.uo().all(), label='Campus', required=False)
    situacao = forms.ChoiceField(label='Filtrar por Situação', choices=InscricaoDispositivo.SITUACAO_PRESTACAO_CHOICES_FORM, required=False)
    edital = forms.ModelChoiceFieldPlus(label='Filtrar por Edital', queryset=Edital.objects, required=False)
    ano = forms.ChoiceField(choices=[], label='Ano letivo', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)
            self.fields['campus'].initial = get_uo(self.request.user).id
        ano_limite = datetime.date.today().year
        ANO_CHOICES = [(ano, f'{ano}') for ano in range(ano_limite, 2019, -1)]
        self.fields['ano'].choices = [['', '-----------'], *ANO_CHOICES]


class RelatorioRendimentoFrequenciaForm(forms.FormPlus):
    METHOD = 'GET'
    PROGRAMA_CHOICES = (
        ('DIS', 'Aquisição de Dispositivos Eletrônicos'),
        ('MAT', 'Material Didático Pedagógico'),
        ('CHP', 'Projetos Alunos Conectados'),
        ('INT', 'Serviço de Internet'),
    )
    campus = forms.ModelChoiceField(label='Filtrar por Campus:', required=True, queryset=UnidadeOrganizacional.objects.uo())
    ano = forms.ChoiceField(choices=[], label='Filtrar por Ano:')
    periodo = forms.ChoiceField(label='Período', choices=[('', '------'), ('1', '1'), ('2', '2')], required=False)
    edital = forms.ModelChoiceFieldPlus(label='Filtrar por Edital', queryset=Edital.objects, required=False)
    programa = forms.ChoiceField(label='Programa', choices=PROGRAMA_CHOICES, widget=forms.Select, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('ae.pode_ver_listas_todos'):
            campus = get_uo(self.request.user)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=campus.id)
            self.fields['campus'].initial = campus.id
        ano_limite = datetime.date.today().year
        ANO_CHOICES = [(ano, f'{ano}') for ano in range(ano_limite, 2019, -1)]
        self.fields['ano'].choices = ANO_CHOICES


class RelatorioAlunosAtendidosForm(forms.FormPlus):
    METHOD = 'GET'
    PROGRAMA_CHOICES = (
        ('DIS', 'Aquisição de Dispositivos Eletrônicos'),
        ('MAT', 'Material Didático Pedagógico'),
        ('CHP', 'Projetos Alunos Conectados'),
        ('INT', 'Serviço de Internet'),
    )
    campus = forms.ModelChoiceField(label='Filtrar por Campus:', required=False, queryset=UnidadeOrganizacional.objects.uo())
    ano = forms.ChoiceField(choices=[], label='Filtrar por Ano:', required=False)
    edital = forms.ModelChoiceFieldPlus(label='Filtrar por Edital', queryset=Edital.objects, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('ae.pode_ver_listas_todos'):
            campus = get_uo(self.request.user)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=campus.id)
            self.fields['campus'].initial = campus.id
        ano_limite = datetime.date.today().year
        ANO_CHOICES = [(ano, f'{ano}') for ano in range(ano_limite, 2019, -1)]
        self.fields['ano'].choices = [['', '-----------'], *ANO_CHOICES]
