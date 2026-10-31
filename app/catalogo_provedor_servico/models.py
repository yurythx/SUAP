import base64
import datetime
import json
from typing import Any

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.query import QuerySet
from django.utils.safestring import mark_safe

from comum.utils import tl
from djtools.db import models
from rh.models import AbstractVinculoArquivoUnico, ArquivoUnico

from .providers.factory import get_service_provider_factory
from .utils import Notificar, obter_choices_por_funcao, reload_choices


class Servico(models.Model):
    """
    Classe **Servico** é o mapeamento dos serviços publicados no *gov.br*. É importante que os serviços que serão
    digitalizados estejam cadastrados.
    """

    SEARCH_FIELDS = ['titulo', 'descricao', 'id_servico_portal_govbr']
    #: Id do serviço no site do *gov.br*.
    id_servico_portal_govbr = models.PositiveIntegerField('Id Gov Br', unique=True)
    # Opções de Ícone: fontawesome
    # https://fontawesome.com/v4.7.0/icons/
    #: Icon a ser apresentado no Balcão de Serviços
    icone = models.CharFieldPlus('Ícone', max_length=50)
    #: Titulo do serviço
    titulo = models.CharFieldPlus('Título', max_length=255, unique=True)
    #: Descrição do serviço
    descricao = models.CharFieldPlus('Descrição', max_length=1000, blank=True, null=True)
    #: Indica se o serviço está ativo ou não
    ativo = models.BooleanField(default=False)
    #: Lista de campos extras que serão utilizados na apresentação
    extra_campo = models.CharFieldPlus('Campo extra a apresentar', blank=True)
    #: Texto apresentado no botão de executar a solicitação
    label_btn_executar_solicitacao = models.CharFieldPlus('Label para Botão de Execução da Solicitação', max_length=50, default='Executar')
    #: Habilitar notificação ao colocar uma solicitação em Análise
    notificar_solicitacao_em_analise = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f'{self.titulo}'

    class Meta:
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'
        ordering = ['id_servico_portal_govbr']
        permissions = (
            ('eh_gerente_sistemico_catalogo', 'É Gerente sistemico do catalogo.'),
            ('eh_gerente_local_catalogo', 'É Gerente local do catalogo.'),
        )

    def clean(self) -> None:
        super().clean()
        if self.ativo and (self.id_servico_portal_govbr or 0) <= 0:
            raise ValidationError({'id_servico_portal_govbr': 'Serviços ativos precisam ter o código "Id Gov Br" definido (maior que zero).'})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def get_service_provider(self) -> object:
        return get_service_provider_factory().get_service_provider(id_servico_portal_govbr=self.id_servico_portal_govbr)


class ServicoEquipe(models.ModelPlus):
    """
    Classe **ServicoEquipe** contêm os usuários que devem ter acesso aos procedimentos junto aos serviços.
    """

    #: Serviço ligado a equipe de trabalho.
    servico = models.ForeignKeyPlus(Servico)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', null=False)
    #: Pessoa física ligada ao usuário de sistema que poderá acessar aos procedimentos nas solicitações
    vinculo = models.ForeignKeyPlus('comum.Vinculo')

    class Meta:
        verbose_name = 'Equipe do Serviço'
        verbose_name_plural = 'Equipe do Serviço'

    def __str__(self):
        try:
            return f'{self.vinculo.relacionamento} - Campus: {self.campus}'
        except Exception:
            return str(self.vinculo.relacionamento)

    def save(self, *args, **kwargs):
        apagar_grupo_vinculo = False
        grupo = Group.objects.get(name='Avaliador do Catálogo Digital')
        if self.pk:
            servico_equipe = ServicoEquipe.objects.filter(pk=self.pk).first()
            if servico_equipe.vinculo != self.vinculo:
                apagar_grupo_vinculo = True
        super().save(*args, **kwargs)
        self.vinculo.user.groups.add(grupo)
        if apagar_grupo_vinculo and not ServicoEquipe.objects.filter(vinculo=servico_equipe.vinculo).exists():
            servico_equipe.vinculo.user.groups.remove(grupo)


class ServicoGerenteEquipeLocal(models.ModelPlus):
    """
    Classe **ServicoGerenteEquipeLocal** contêm os usuários que devem gerênciar os membros da equipe junto aos serviços.
    """

    #: Serviço ligado a equipe de trabalho.
    servico = models.ForeignKeyPlus(Servico)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional')
    #: Pessoa física ligada ao usuário de sistema que poderá acessar aos procedimentos nas solicitações
    vinculo = models.ForeignKeyPlus('comum.Vinculo')

    class Meta:
        verbose_name = 'Gerente Local do Serviço'
        verbose_name_plural = 'Gerentes Locais dos Serviços'

    def __str__(self):
        return f'{self.vinculo.relacionamento} Gerente do serviço {self.servico} - Campus: {self.campus}'

    def save(self, *args, **kwargs):
        apagar_grupo_vinculo = False
        grupo = Group.objects.get(name='Gerente Local do Catalogo Digital')
        if self.pk:
            servico_gerente = ServicoGerenteEquipeLocal.objects.filter(pk=self.pk).first()
            if servico_gerente.vinculo != self.vinculo:
                apagar_grupo_vinculo = True
        super().save(*args, **kwargs)
        self.vinculo.user.groups.add(grupo)
        if apagar_grupo_vinculo and not ServicoGerenteEquipeLocal.objects.filter(vinculo=servico_gerente.vinculo).exists():
            servico_gerente.vinculo.user.groups.remove(grupo)


class Solicitacao(models.Model):
    """
    Classe que mapeia as solicitações realizadas pelos cidadãos. Essas solicitações são originadas no Balcão de Serviços.

    Para controlar as solicitações é utilizada uma máquina de estados descrita a seguir:

    .. graphviz::

        digraph status_machine {
            {
                START [label="Início" shape=circle]
                STATUS_INCOMPLETO [label="Incompleto"]
                STATUS_EM_ANALISE [label="Em Analise"]
                STATUS_PRONTO_PARA_EXECUCAO [label="Pronto para Execução"]
                STATUS_AGUARDANDO_CORRECAO_DE_DADOS [label="Aguardando Correção de Dados"]
                STATUS_DADOS_CORRIGIDOS [label="Dados Corrigidos"]
                STATUS_ATENDIDO [label="Atendido"]
                STATUS_NAO_ATENDIDO [label="Não Atendido"]
                STATUS_EXPIRADO [label="Expirado"]
                END [label="Fim" shape=doublecircle]
            }
            START -> STATUS_INCOMPLETO -> STATUS_EM_ANALISE
            STATUS_EM_ANALISE -> STATUS_AGUARDANDO_CORRECAO_DE_DADOS -> STATUS_DADOS_CORRIGIDOS -> STATUS_AGUARDANDO_CORRECAO_DE_DADOS
            STATUS_DADOS_CORRIGIDOS -> STATUS_PRONTO_PARA_EXECUCAO
            STATUS_EM_ANALISE -> STATUS_NAO_ATENDIDO -> END
            STATUS_EM_ANALISE -> STATUS_PRONTO_PARA_EXECUCAO
            STATUS_PRONTO_PARA_EXECUCAO -> STATUS_ATENDIDO -> END
            STATUS_EXPIRADO -> END
        }

    Descrição dos estados:
        * **Incompleto**: indica que a solicitação foi iniciada, mas, ainda existem passos a completar;
        * **Em Analise**: indica que a solicitação foi enviada para análise da equipe no IFRN;
        * **Aguardando Correção de Dados**: indica que alguma informação prestada deverá ser corrigida pelo cidadão;
        * **Dados Corrigidos**: indica que os dados incorretos foram corrigidos pelo cidadão;
        * **Pronto para Execução**: indica que a solicitação está pronta para ser executada;
        * **Atendido**: indica que a solicitação foi atendida;
        * **Não Atendido**: indica que a solicitação não foi atendida;
        * **Expirado**: indica que o período de análise foi finalizado e as solicitações pendentes foram expiradas.

    Observações:
        * Os estados **Incompleto** e **Aguardando Correção de Dados** permitem edição de dados pelo cidadão;
        * Os estados **Em Analise**, **Aguardando Correção de Dados**, **Dados Corrigidos** e **Pronto para Execução** permitem avaliação dos dados;
        * Os estados **Incompleto**, **Em Analise**, **Aguardando Correção de Dados**, **Dados Corrigidos** e **Pronto para Execução** permitem seu indeferimento.

    """

    SEARCH_FIELDS = ['id', 'cpf', 'nome']

    STATUS_INCOMPLETO = 'INCOMPLETO'
    STATUS_EM_ANALISE = 'EM_ANALISE'
    STATUS_PRONTO_PARA_EXECUCAO = 'PRONTO_PARA_EXECUCAO'
    STATUS_AGUARDANDO_CORRECAO_DE_DADOS = 'AGUARDANDO_CORRECAO_DE_DADOS'
    STATUS_DADOS_CORRIGIDOS = 'DADOS_CORRIGIDOS'
    STATUS_ATENDIDO = 'ATENDIDO'
    STATUS_NAO_ATENDIDO = 'NAO_ATENDIDO'
    STATUS_EXPIRADO = 'EXPIRADO'
    STATUS_CHOICES = (
        (STATUS_INCOMPLETO, 'Incompleto'),
        (STATUS_EM_ANALISE, 'Em Análise'),
        (STATUS_AGUARDANDO_CORRECAO_DE_DADOS, 'Aguardando Correção de Dados'),
        (STATUS_DADOS_CORRIGIDOS, 'Dados Corrigidos'),
        (STATUS_PRONTO_PARA_EXECUCAO, 'Pronto Para Execução'),
        (STATUS_ATENDIDO, 'Atendido'),
        (STATUS_NAO_ATENDIDO, 'Não Atendido'),
        (STATUS_EXPIRADO, 'Expirado'),
    )
    # Agrupamentos de status de acordo com as funções que eles podem habilitar no sistema.
    STATUS_DEFINITIVOS = [STATUS_ATENDIDO, STATUS_NAO_ATENDIDO, STATUS_EXPIRADO]
    STATUS_QUE_PERMITEM_EDICAO_DADOS = [STATUS_INCOMPLETO, STATUS_AGUARDANDO_CORRECAO_DE_DADOS]
    STATUS_QUE_PERMITEM_HABILITACAO_SERVICO = STATUS_QUE_PERMITEM_EDICAO_DADOS + STATUS_DEFINITIVOS
    STATUS_QUE_PERMITEM_AVALIACAO_DADOS = [
        STATUS_EM_ANALISE,
        STATUS_AGUARDANDO_CORRECAO_DE_DADOS,
        STATUS_DADOS_CORRIGIDOS,
        STATUS_PRONTO_PARA_EXECUCAO,
    ]
    STATUS_QUE_PERMITEM_NOTIFICACAO = STATUS_QUE_PERMITEM_AVALIACAO_DADOS + STATUS_DEFINITIVOS
    STATUS_QUE_PERMITEM_INDEFERIMENTO = [
        STATUS_INCOMPLETO,
        STATUS_EM_ANALISE,
        STATUS_AGUARDANDO_CORRECAO_DE_DADOS,
        STATUS_DADOS_CORRIGIDOS,
        STATUS_PRONTO_PARA_EXECUCAO,
    ]

    #: Serviço que originou a solicitação
    servico = models.ForeignKeyPlus(Servico, on_delete=models.CASCADE)
    #: O CPF do cidadão
    cpf = models.CharFieldPlus('CPF', max_length=14)
    #: O nome do cidadão
    nome = models.CharFieldPlus('Solicitante')
    #: Número total de etapas da solicitação. Esse valor é definido pelo provedor específico do serviço associado
    numero_total_etapas = models.PositiveSmallIntegerField('Nº Total de Etapas')
    #: Data da criação do serviço pelo cidadão
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    #: Data da última atualização na solicitação
    data_ultima_atualizacao = models.DateTimeFieldPlus('Data da Última Atualização', auto_now=True)
    #: Indica o estado atual da solicitação, uso da máquina de estados
    status = models.CharFieldPlus(verbose_name='Status', max_length=50, choices=STATUS_CHOICES, default=STATUS_EM_ANALISE)
    #: Detalhamento do estado
    status_detalhamento = models.CharFieldPlus('Detalhamento do Status', max_length=1000, blank=True, null=True)

    #: Armazena os dados extras que servirá para apresentação e filtros. Esse valor é obtido com o uso do campo extra_campo no **Servico**
    extra_dados = models.TextField('Informação Extra', blank=True)

    # Os dados aqui presentes tem a devida cópia existente no SolicitacaoResponsavelHistorico.
    vinculo_atribuinte = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Atribuinte', related_name='solicitacao_atribuinte', blank=True, null=True
    )
    vinculo_responsavel = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável', blank=True, null=True)
    data_associacao_responsavel = models.DateTimeFieldPlus('Data de Associação ao Responsável', blank=True, null=True)
    instrucao = models.CharFieldPlus(verbose_name='Instrução', max_length=1000, blank=True, null=True)

    # Num primeiro momento a ideia era que o atributo UO fosse not null, mas isso não foi possível porque sem sempre
    # saberemos na primeira etapa da solicitação a qual unidade organizacional (campus) pertence a solicitação.
    #: Indica o campus associado a solicitação
    uo = models.ForeignKeyPlus(
        'rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE, related_name='solicitacoes', blank=True, null=True
    )

    # Esse atributo é um JSON contendo uma lista de dicionarios que irá guardar referências dos registros criados/atualizados/removidos durante a execução da solicitação.
    # Ex: [
    #   {app: 'processo_eletronico', model: 'Processo', id: 111222, operation: 'CREATE'},
    #   {app: 'documento_eletronico', model: 'DocumentoDigitalizado', id: 123456, operation: 'CREATE'},
    # ]
    #: Campo que armazena os dados mediante as seguintes operações: CREATE/UPDATE/DELETE
    dados_registros_execucao = models.TextField(verbose_name='Dados dos Registros Criados Durante a Execução', blank=True, null=True, editable=False)

    class Meta:
        verbose_name = 'Solicitação'
        verbose_name_plural = 'Solicitações'
        ordering = ['id']
        permissions = (('pode_avaliar_solicitacoes', 'Pode Avaliar Solicitações'), ('pode_visualizar_relatorio', 'Pode visualizar relatórios'))

    def __str__(self):
        return f'Solicitação {self.id} (CPF: {self.cpf}, Nome: {self.nome})'

    def get_absolute_url(self):
        """
        Monta a URL de edição de dados.

        Returns:
            String contendo a *URL*
        """
        return f'/catalogo_provedor_servico/avaliar_solicitacao/{self.pk}/'

    def add_dado_registro_execucao(self, model_object, operation, registered_on=None):
        """
        Adiciona um registro de execução no atributo dados_registros_execucao.

        Args:
            model_object (Model): o objeto, solicitação, que está sendo atualizado.
            operation (string): indica a operação a ser registrada.
            registered_on (datetime): data e hora da operação.

        Raises:
            ValidationError: a operação de registro não corresponde a uma opção válida.
        """
        valid_operations = ['CREATE', 'UPDATE', 'DELETE']
        if operation not in valid_operations:
            raise ValidationError('As opções disponíveis para registro de execução são: {}.'.format(', '.join(valid_operations)))

        if not hasattr(self, 'add_dados_registros_execucao_cache'):
            self.add_dados_registros_execucao_cache = []

        registered_on = registered_on or datetime.datetime.now()
        self.add_dados_registros_execucao_cache.append(
            {
                'app': model_object._meta.app_label,
                'model': model_object._meta.object_name,
                'id': model_object.id,
                'operation': operation,
                'registered_on': registered_on.strftime('%Y-%m-%d %H:%M:%S.%f'),
            }
        )

    def get_dados_registros_execucao_as_json(self):
        if self.dados_registros_execucao:
            return json.loads(self.dados_registros_execucao)

        return []

    def processar_add_dados_registros_execucao_cache(self):
        """
        Coloca os dados do registro de execução em cache.
        """
        if hasattr(self, 'add_dados_registros_execucao_cache') and self.add_dados_registros_execucao_cache:
            dados_registros_execucao_as_json = self.get_dados_registros_execucao_as_json()
            dados_registros_execucao_as_json.extend(self.add_dados_registros_execucao_cache)
            self.dados_registros_execucao = json.dumps(dados_registros_execucao_as_json, indent=4)
            self.add_dados_registros_execucao_cache = []

    def get_status(self):
        """
        Retorna o estado da solicitação.

        Returns:
            String do estado atual da solicitação.
        """
        return self.status

    def get_status_display(self):
        """
        Retorna o valor, display, do estado atual.

        Returns:
            String contendo o display do estado atual.
        """
        for status in self.STATUS_CHOICES:
            if status[0] == self.get_status():
                return mark_safe(status[1])
        return mark_safe(self.STATUS_CHOICES[0][1])

    # TODO: Dar uma organizada nesse método, preservando a ordem das chamadas.
    @transaction.atomic()
    def save(self, *args, **kwargs):
        """
        Salva a instância atual.
        """
        from catalogo_provedor_servico.providers.factory import get_service_provider_factory

        self.processar_add_dados_registros_execucao_cache()

        is_update = self.pk is not None
        solicitacao_old = None
        if is_update:
            solicitacao_old = Solicitacao.objects.get(pk=self.pk)

        self.enviar_email = kwargs.pop('enviar_email', False)

        self.clean()

        if is_update:
            solicitacao_old = Solicitacao.objects.get(pk=self.pk)
            historico_vinculo_atribuinte = self.vinculo_atribuinte or tl.get_vinculo() or solicitacao_old.vinculo_atribuinte
            # Gerando o registro de histórico de responsável pela solicitação, se tiver ocorrido alguma mudança de responsável.
            if (
                self.vinculo_responsavel is not None
                and historico_vinculo_atribuinte is not None
                and solicitacao_old.vinculo_responsavel != self.vinculo_responsavel
            ):
                self.vinculo_atribuinte = historico_vinculo_atribuinte
                historico = SolicitacaoResponsavelHistorico()
                historico.solicitacao = self
                historico.vinculo_atribuinte = historico_vinculo_atribuinte
                historico.vinculo_responsavel = self.vinculo_responsavel
                historico.data_associacao_responsavel = self.data_associacao_responsavel or datetime.datetime.now()
                historico.instrucao = self.instrucao
                historico.save()

        super().save(*args, **kwargs)
        service_provider = get_service_provider_factory().get_service_provider(id_servico_portal_govbr=self.servico.id_servico_portal_govbr)
        if service_provider is None:
            raise ValidationError({'service_provider': f'Provedor de serviço não encontrado para o serviço {self.servico.titulo}.'})
        dados_email = service_provider.get_dados_email(solicitacao=self)

        if self.status == Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS and self.enviar_email:
            service_provider.registrar_acompanhamento(self)
            Notificar.solicitacao_correcao_de_dados(self, dados_email)
        elif self.status == Solicitacao.STATUS_NAO_ATENDIDO:
            service_provider.registrar_acompanhamento(self)
            Notificar.solicitacao_nao_atendida(self, dados_email)
        elif self.status == Solicitacao.STATUS_EXPIRADO:
            service_provider.registrar_acompanhamento(self)
        elif (
            solicitacao_old
            and solicitacao_old.status == Solicitacao.STATUS_INCOMPLETO
            and self.status == Solicitacao.STATUS_EM_ANALISE
            and self.servico.notificar_solicitacao_em_analise
        ):
            Notificar.solicitacao_recebida(self, dados_email)
        elif (
            solicitacao_old
            and solicitacao_old.status == Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS
            and self.status == Solicitacao.STATUS_DADOS_CORRIGIDOS
        ):
            Notificar.solicitacao_dados_corrigidos(self, dados_email)

        # Registra a situação da Solicitação quando há alteração,
        if not solicitacao_old or solicitacao_old.status != self.status:
            vinculo_responsavel_historico = None
            if not solicitacao_old:  # É uma nova solicitação
                vinculo_responsavel_historico = self.vinculo_responsavel
            else:  # É uma atualização de uma solicitação existente
                if self.vinculo_responsavel:
                    vinculo_responsavel_historico = self.vinculo_responsavel
            SolicitacaoHistoricoSituacao.objects.create(
                solicitacao=self,
                status_detalhamento=self.status_detalhamento,
                status=self.status,
                vinculo_responsavel=vinculo_responsavel_historico,
            )

    def clean(self):
        """
        Realiza validações gerais no modelo.
        """
        service_provider = get_service_provider_factory().get_service_provider(id_servico_portal_govbr=self.servico.id_servico_portal_govbr)
        if not service_provider:
            raise ValidationError(f'Não foi possível obter o provedor de serviço para o serviço {self.servico}.')
        is_update = self.pk is not None
        if is_update:
            solicitacao_old = Solicitacao.objects.get(pk=self.pk)
            if solicitacao_old.has_status_definitivo() and not solicitacao_old.has_status_permite_retornar_para_analise():
                raise ValidationError(
                    f'A solicitação não pode ser mais alterada pois ela está com o status "{solicitacao_old.get_status_display()}".'
                )

    # Os parâmetros atribuinte e responsavel são do tipo PessoaFisica.
    def atribuir_responsavel(self, vinculo_atribuinte, vinculo_responsavel, data_associacao_responsavel, instrucao):
        """
        Faz a atribuição da solicitação a uma pessoa física (usuário do sistema).

        Args:
            vinculo_atribuinte (PessoaFisica): Indica o responsável por atribuir ao responsável.
            vinculo_responsavel (PessoaFisica): Indica a pessoa física responsável por avaliar a solicitação.
            data_associacao_responsavel (datetime.datetime): Data em que o responsável foi associado.
            instrucao (string): Instrução.

        Raises:
            ValidationError:
                * Quando o responsável não é informado;
                * Quando o responsável não pertence a equipe de servidores que avalia solicitações do serviço do campus;
                * Somente o responsável anterior ou gerente sistêmico podem assumir/atribuir a responsabilidade de solicitações.
        """
        if not vinculo_responsavel:
            raise ValidationError({'vinculo_responsavel': 'Responsável não informado.'})

        solicitacao_old = Solicitacao.objects.get(pk=self.pk)
        if solicitacao_old.uo:
            responsavel_eh_membro_equipe = self.servico.servicoequipe_set.filter(vinculo=vinculo_responsavel, campus=self.uo).exists()
            atribuinte_eh_gerente_equipe = self.servico.servicogerenteequipelocal_set.filter(vinculo=vinculo_atribuinte, campus=self.uo).exists()
        else:
            responsavel_eh_membro_equipe = self.servico.servicoequipe_set.filter(vinculo=vinculo_responsavel).exists()
            atribuinte_eh_gerente_equipe = self.servico.servicogerenteequipelocal_set.filter(vinculo=vinculo_atribuinte).exists()

        vai_assumir_solicitacao = vinculo_atribuinte == vinculo_responsavel
        if not responsavel_eh_membro_equipe:
            raise ValidationError(
                f'O usuario {vinculo_responsavel} não pertence a equipe de servidores que avalia solicitações do serviço {self.servico} do campus {self.uo}.'
            )
        if not atribuinte_eh_gerente_equipe and solicitacao_old.vinculo_responsavel and vinculo_atribuinte != solicitacao_old.vinculo_responsavel:
            acao = 'assumir' if vai_assumir_solicitacao else 'atribuir'
            raise ValidationError(f'Somente o responsável anterior ou gerentes sistêmicos podem {acao} a responsabilidade de solicitações.')

        self.vinculo_atribuinte = vinculo_atribuinte
        self.vinculo_responsavel = vinculo_responsavel
        self.data_associacao_responsavel = data_associacao_responsavel
        self.instrucao = instrucao

    def has_status_definitivo(self):
        """
        Verifica se a solicitação está em um estado definitivo/final.

        Returns:
            boolean indicando se o estado é final.
        """
        return self.status in Solicitacao.STATUS_DEFINITIVOS

    def has_status_permite_edicao_dados(self):
        """
        Verifica se a solicitação está em um estado que permite a edição de dados.

        Returns:
            boolean indicando se o estado permite edição dos dados.
        """
        return self.status in Solicitacao.STATUS_QUE_PERMITEM_EDICAO_DADOS

    def has_status_permite_habilitacao_servico(self):
        """
        Verifica se a solicitação permite que o serviço seja habilitado.

        Returns:
            boolean indicando se o estado permite a habilitação de serviço.
        """
        return self.status in Solicitacao.STATUS_QUE_PERMITEM_HABILITACAO_SERVICO

    def has_status_permite_avaliacao_dados(self):
        """
        Verifica se a solicitação permite a avaliação dos dados.

        Returns:
            boolean indicando se o estado permite a avaliação dos dados.
        """
        return self.status in Solicitacao.STATUS_QUE_PERMITEM_AVALIACAO_DADOS

    def has_status_permite_indeferimento(self):
        """
        Verifica se a solicitação permite seu indeferimento.

        Returns:
            boolean indicando se o estado permite o indeferimento.
        """
        return self.status in Solicitacao.STATUS_QUE_PERMITEM_INDEFERIMENTO

    def has_status_permite_retornar_para_analise(self):
        """
        Verifica se a solicitação permite que retorno para análise dos dados.

        Returns:
            boolean indicando se o estado permite o retorno a análise dos dados.
        """
        return self.status == Solicitacao.STATUS_NAO_ATENDIDO

    def get_registroavaliacao_govbr(self):
        """
        Retorna o registro de avaliação, do serviço, junto ao *gov.br*.

        Returns:
            RegistroAvaliacaoGovBR da avaliação.
        """
        return RegistroAvaliacaoGovBR.objects.filter(solicitacao=self).first()

    def get_extra_dados(self):
        """
        Obtem os dados extras, da solicitação, provenientes dos dados prestados pelos cidadãos.

        Raises:
            Exception: quando não foi possível carregar o json.

        Returns:
            Dict contendo os dados.
        """
        try:
            return json.loads(self.extra_dados)
        except Exception:
            return None

    def get_extra_dados_html(self):
        """
        Obtem os dados extras em html, da solicitação, provenientes dos dados prestados pelos cidadãos.

        Returns:
            lista em html contendo os dados.
        """
        retorno = ''
        try:
            dados = self.get_extra_dados()
            if dados:
                retorno = '<ul>'
                for value in dados.values():
                    retorno += f'<li>{value} </li>'
                retorno += '</ul>'
        except Exception:
            pass
        return retorno

    def atualizar_extra_campo(self, etapa, salvar=True):
        """
        Atualiza os dados extras de acordo com o campo *extra_campo* contido no serviço.

        Args:
            etapa (Etapa): etapa para processamento dos dados extras.
            salvar (bool): indica se o registro deve ser salvo.
        """
        # Faz o tratamento dos campos extras
        if self.servico.extra_campo:
            campos_extras = self.servico.extra_campo.split(';')
            dados_extras = {}
            if self.extra_dados:
                dados_extras = json.loads(self.extra_dados)
            for extra_campo in campos_extras:
                etapa_key, etapa_campo = extra_campo.split('.')

                if etapa.nome == etapa_key:
                    valor = etapa.formulario.get_display_value(etapa_campo)
                    if valor:
                        dados_extras[extra_campo] = valor

            if dados_extras:
                self.extra_dados = json.dumps(dados_extras)
                if salvar:
                    try:
                        self.save()
                    except Exception:
                        Solicitacao.objects.filter(pk=self.pk).update(extra_dados=self.extra_dados)


class SolicitacaoResponsavelHistorico(models.ModelPlus):
    """
    Guarda o histórico da mudança dos responsáveis por avaliar as solicitações.
    """

    #: Solicitação do histórico
    solicitacao = models.ForeignKeyPlus(Solicitacao)
    #: Responsável por atribuir ao responsável
    vinculo_atribuinte = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Atribuinte', related_name='solicitacao_historico_atribuinte')
    #: Responsável por avaliar a solicitação
    vinculo_responsavel = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável')
    #: Data na qual o responsável foi associado a solicitação
    data_associacao_responsavel = models.DateTimeFieldPlus('Data de Associação ao Responsável')
    #: Instrução
    instrucao = models.CharFieldPlus(verbose_name='Instrução', max_length=1000, blank=True, null=True)


class SolicitacaoHistoricoSituacao(models.ModelPlus):
    """
    Guarda o histórico da mudança de situação da solicitação.

    """

    #: Solicitação do histórico
    solicitacao = models.ForeignKeyPlus(Solicitacao, on_delete=models.CASCADE)
    #: Estado da solicitação
    status = models.CharFieldPlus(verbose_name='Status', max_length=50)
    #: Detalhamento do estado da situação
    status_detalhamento = models.CharFieldPlus('Detalhamento do Status', max_length=1000, blank=True, null=True)
    #: Data de criação do registro
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    #: Responsável
    vinculo_responsavel = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável', blank=True, null=True)

    class History:
        disabled = True

    def get_status_display(self):
        """
        Obtem o valor amigável do estado da solicitação.

        Returns:
            String contendo o valor detalhado do estado da solicitação.
        """
        for status in Solicitacao.STATUS_CHOICES:
            if status[0] == self.status:
                return mark_safe(status[1])
        return mark_safe(Solicitacao.STATUS_CHOICES[0][1])


class SolicitacaoEtapa(models.Model):
    """
    Mapeia a etapa da solicitação.
    """

    #: Solicitação da etapa
    solicitacao = models.ForeignKeyPlus(Solicitacao, on_delete=models.CASCADE)
    #: Data de criação da etapa
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    #: Data da última atualização nos dados da etapa
    data_ultima_atualizacao = models.DateTimeFieldPlus('Data da Última Atualização', auto_now=True)
    #: Número da etapa da solicitação
    numero_etapa = models.PositiveSmallIntegerField('Número da Etapa')
    #: Dados prestados pelo cidadão. Armazenado no formato **JSON**.
    dados = models.TextField(verbose_name='Dados')

    def __str__(self):
        return f'{self.solicitacao} - Etapa {self.numero_etapa} de {self.solicitacao.numero_total_etapas}'

    class Meta:
        verbose_name = 'Solicitação Etapa'
        verbose_name_plural = 'Solicitações Etapas'
        unique_together = (('solicitacao', 'numero_etapa'),)
        ordering = ['solicitacao', 'numero_etapa']

    def clean(self):
        """
        Realiza validações gerais no modelo.
        """
        if self.numero_etapa > self.solicitacao.numero_total_etapas:
            raise ValidationError(f'O número da etapa excede o número total de etapas para o serviço "{self.solicitacao.servico}"')

    def get_dados_as_json(self):
        """
        Obtem os dados da etapa no formato **JSON**.

        Returns:
            Dict contendo as informações da etapa.
        """
        dados_as_json = json.loads(self.dados)
        # TODO: Rever. Acredito que seja interessante recarregar os choices do JSON somente no momento da edição dos
        # dados pelo cidacão, quando solicitaca a correção.
        if not self.solicitacao.has_status_definitivo():
            dados_as_json['formulario'] = reload_choices(dados_as_json['formulario'])
        return dados_as_json

    @classmethod
    def update_or_create_from_etapa(cls, etapa, solicitacao):
        """
        Método de classe que atualiza ou cria uma etapa para uma determinada solicitação.

        Args:
            etapa (Etapa): dados da etapa pelo cidadão.
            solicitacao (Solicitacao): solicitação que será criada a etapa.

        Raises:
            Exception:

        Returns:
            Tupla contendo os dados da etapa na solicitação e um booleano que aponta se foi criada.
        """

        solicitacao_etapa = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=etapa.numero)
        if solicitacao_etapa.exists():
            solicitacao_etapa = solicitacao_etapa.first()
            solicitacao_etapa_created = False
        else:
            solicitacao_etapa = SolicitacaoEtapa()
            solicitacao_etapa_created = True

        # TODO: Ver com Hugo porque não obter o "display_value" direto Balcão Digital, já que ao submeter o dado ele tem
        # essa informação.
        # Populando o display_value dos choices
        for i, field in enumerate(etapa.formulario.campos):
            if 'choices_resource_id' in field:
                choices = obter_choices_por_funcao(field['choices_resource_id'], field['filters'])
                display_value = ''
                value = field.get('value')
                if value:
                    if isinstance(choices, QuerySet):
                        try:
                            display_value = str(choices.filter(pk=value).first())
                        except Exception:
                            display_value = ''
                    else:
                        if isinstance(choices, dict):
                            choices = choices.items()
                        for choice_key, choice_value in choices:
                            if str(value) == str(choice_key):
                                display_value = choice_value
                etapa.formulario.campos[i]['display_value'] = display_value

        arquivos_unicos_to_delete_in_rollback_case = []
        try:
            with transaction.atomic():
                solicitacao_etapa.solicitacao = solicitacao
                solicitacao_etapa.numero_etapa = etapa.numero
                campos_tipo_file_with_value = etapa.formulario.get_campos_file(has_value=True)
                if not campos_tipo_file_with_value:
                    solicitacao_etapa.dados = etapa.json_dumps(indent=4)
                    solicitacao_etapa.save()
                    return solicitacao_etapa, solicitacao_etapa_created

                solicitacao_etapa.dados = '[CAMPOS_FILE_SENDO_RETIRADOS_DO_JSON]'
                solicitacao_etapa.save()
                # Se houver campos do tipo "file", dentro do JSON, cada um dos campos terá o respectivo arquivo persistido
                # em disco, caso ainda não exista, e em seguida o conteúdo será removido do JSON, afim de otimização do
                # espaço no banco de dados. Além disso, será atribuido ao atributo "value_hash_sha512_link_id" um valor através
                # do qual o registro de SolicitacaoEtapaArquivo poderá ser localizado, e consequentemente, o arquivo a ele
                # associado.
                for campo_file in campos_tipo_file_with_value:
                    name = campo_file['name']
                    value = campo_file['value']

                    solicitacao_etapa_arquivo = (
                        SolicitacaoEtapaArquivo.objects.only('id').filter(solicitacao_etapa=solicitacao_etapa, nome_atributo_json=name).first()
                    )
                    if solicitacao_etapa_arquivo:
                        solicitacao_etapa_arquivo_id = solicitacao_etapa_arquivo.id
                    else:
                        solicitacao_etapa_arquivo_id = None

                    solicitacao_etapa_arquivo, _solicitacao_etapa_arquivo_created, arquivo_unico, arquivo_unico_created = (
                        SolicitacaoEtapaArquivo.update_or_create_from_file_strb64(
                            strb64=value,
                            tipo_conteudo=campo_file['value_content_type'],
                            data_hora_upload=solicitacao_etapa.data_ultima_atualizacao,
                            nome_original=campo_file['value_original_name'],
                            nome_exibicao=campo_file['label_to_file'],
                            descricao=campo_file['label'],
                            solicitacao_etapa=solicitacao_etapa,
                            nome_atributo_json=campo_file['name'],
                            tamanho_em_bytes_para_validar=campo_file['value_size_in_bytes'],
                            hash_sha512_para_validar=campo_file['value_hash_sha512'],
                            solicitacao_etapa_arquivo_id=solicitacao_etapa_arquivo_id,
                        )
                    )
                    if arquivo_unico_created:
                        arquivos_unicos_to_delete_in_rollback_case.append(arquivo_unico)

                    campo_file['value'] = None
                    campo_file['value_hash_sha512_link_id'] = solicitacao_etapa_arquivo.arquivo_unico.hash_sha512_link_id

                solicitacao_etapa.dados = etapa.json_dumps(indent=4)
                solicitacao_etapa.save()
                return solicitacao_etapa, solicitacao_etapa_created
        except IntegrityError:
            if arquivos_unicos_to_delete_in_rollback_case:
                for arquivo_unico in arquivos_unicos_to_delete_in_rollback_case:
                    arquivo_unico.conteudo.delete(save=False)
            label = campo_file['label']
            raise Exception(f'Por favor altere o arquivo "{label}"')
        except Exception as e:
            if arquivos_unicos_to_delete_in_rollback_case:
                for arquivo_unico in arquivos_unicos_to_delete_in_rollback_case:
                    arquivo_unico.conteudo.delete(save=False)
            raise e


class RegistroAcompanhamentoGovBR(models.Model):
    """
    Armazena o registro de acompanhamento junto ao *gov.br*.

    O registro pode ser dos seguintes tipos:
        * **TIPO_ACOMPANHAMENTO**: acompanhamento da solicitação;
        * **TIPO_CONCLUSAO**: indica que o acompanhamento está concluído;
        * **TIPO_REABERTURA**: indica que o acompanhamento foi reaberto pelo cidadão.

    O acomanhamento pode está em um dos seguintes status:
        * **ENVIADO**:
        * **PENDENTE**:
        * **ERRO**:
    """

    TIPO_ACOMPANHAMENTO = 'ACOMPANHAMENTO'
    TIPO_CONCLUSAO = 'CONCLUSAO'
    TIPO_REABERTURA = 'REABERTURA'
    TIPO_CHOICES = ((TIPO_ACOMPANHAMENTO, 'Acompanhamento'), (TIPO_CONCLUSAO, 'Conclusão'), (TIPO_REABERTURA, 'Reabertura'))

    ENVIADO = 'ENVIADO'
    PENDENTE = 'PENDENTE'
    ERRO = 'ERRO'
    STATUS_CHOICES = ((ENVIADO, 'Enviado'), (PENDENTE, 'Pendente'), (ERRO, 'Erro'))

    #: Payload
    payload = models.JSONField(null=True)
    #: Solicitação ligado ao acompanhamento
    solicitacao = models.ForeignKeyPlus(Solicitacao, on_delete=models.CASCADE)
    #: Status code obtido no consumo da API do *gov.br*.
    status_code = models.CharFieldPlus(verbose_name='Status Code HTTP', max_length=50, null=True)
    #: Tipo do acompanhamento, se é um TIPO_ACOMPANHAMENTO, um TIPO_CONCLUSAO ou um TIPO_REABERTURA.
    tipo = models.CharFieldPlus(verbose_name='Tipo de Registro', max_length=50, choices=TIPO_CHOICES, default=TIPO_ACOMPANHAMENTO)
    #: O status do acompanhamento, podendo ser: ENVIADO, PENDENTE ou ERRO
    status = models.CharFieldPlus(verbose_name='Status', max_length=50, choices=STATUS_CHOICES, default=PENDENTE)
    #: Data da criação do registro de acompanhamento
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    #: Indica se a avaliação foi realizada
    avaliado = models.BooleanField(default=False)
    #: Tentativas de envio
    tentativas_envio = models.IntegerField(verbose_name='Tentativas de Envio', default=0)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Registro de Acompanhamento de Serviço'
        verbose_name_plural = 'Registros de Acompanhamentos de Serviços'

    def __str__(self):
        return f'{self.tipo} - {self.status}'


class RegistroAvaliacaoGovBR(models.Model):
    """
    Armazena o registro de avaliação junto ao *gov.br*.

    """

    #: Solicitação ligado a avaliação
    solicitacao = models.ForeignKeyPlus(Solicitacao, on_delete=models.CASCADE)
    #: A URL para a avaliação, junto ao *gov.br*
    url_avaliacao = models.TextField(null=True)
    #: Resposta da avaliação
    resposta_avaliacao = models.TextField(null=True)
    #: Data do cadastro do link do formulário de avaliação
    data_cadastro_link_formulario = models.DateTimeFieldPlus('Data de Cadastro do Formulaŕio', null=True)
    #: Data do cadastro do registro de avaliação no sistema
    data_cadastro_avaliacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    #: Indica se a avaliação foi realizada pelo cidadão
    avaliado = models.BooleanField(default=False)
    #: Indica se a avaliação será notificada por e-mail
    notificado_por_email = models.BooleanField(default=False)
    #: Tentativas de envio
    tentativas_envio = models.IntegerField(verbose_name='Tentativas de Envio', default=0)

    class Meta:
        verbose_name = 'Registro de Avaliação de Serviço'
        verbose_name_plural = 'Registros de Avaliações de Serviços'

    def __str__(self):
        return f'{self.solicitacao}'

    def registrar_notificacao(self):
        """
        Registra que a avaliação deve ser notificada por e-mail.
        """
        self.notificado_por_email = True
        self.save()


class SolicitacaoEtapaArquivo(AbstractVinculoArquivoUnico):
    """
    Armazena os arquivo provenientes das solicitações.
    """

    #: Indica a etapa de solicitação que contem o arquivo
    solicitacao_etapa = models.ForeignKeyPlus(SolicitacaoEtapa, on_delete=models.CASCADE)
    #: Nome atributo *JSON*
    nome_atributo_json = models.CharFieldPlus(verbose_name='Nome do Atributo no Json', max_length=50)

    class Meta:
        verbose_name = 'Arquivo da Etapa da Solicitação'
        verbose_name_plural = 'Arquivos da Etapa da Solicitação'
        unique_together = (('solicitacao_etapa', 'nome_atributo_json'),)

    def __str__(self):
        return f'{self.solicitacao_etapa} - {self.nome_atributo_json}'

    @classmethod
    def update_or_create_from_file_bytes(
        cls,
        bytes,
        tipo_conteudo,
        data_hora_upload,
        nome_original,
        nome_exibicao,
        descricao,
        solicitacao_etapa,
        nome_atributo_json,
        tamanho_em_bytes_para_validar=None,
        hash_sha512_para_validar=None,
        solicitacao_etapa_arquivo_id=None,
    ):
        """
        Método de classe que cria ou atualiza um arquivo com base em seus bytes.

        Args:
            bytes (): Bytes que compõem o arquivo.
            tipo_conteudo (): Tipo do conteúdo.
            data_hora_upload (datetime): Data na qual o arquivo foi submetido.
            nome_original (string): Nome original do arquivo submetido.
            nome_exibicao (string): Nome que deve ser utilizado para a exibição
            descricao (string): Descrição que o cidadão deu para o arquivo.
            solicitacao_etapa (SolicitacaoEtapa): Indica qual é a etapa associada ao arquivo.
            nome_atributo_json:
            tamanho_em_bytes_para_validar (int): Tamanha do arquivo em bytes para validar o arquivo.
            hash_sha512_para_validar (string): Hash, sha512, dos bytes do arquivo para validação.
            solicitacao_etapa_arquivo_id (int): Id do arquivo contido na etapa da solicitação.

        Raises:
            ValidationError: Caso a etapa não exista.
            Exception:

        Returns:
            Tupla contendo:
                * Instância de SolicitacaoEtapaArquivo;
                * Bool indicado se a SolicitacaoEtapaArquivo foi criada;
                * Instãncia de arquivo único;
                * Bool indicando se o arquivo único foi criado.
        """
        if solicitacao_etapa_arquivo_id:
            solicitacao_etapa_arquivo = SolicitacaoEtapaArquivo.objects.filter(pk=solicitacao_etapa_arquivo_id)
            if not solicitacao_etapa_arquivo.exists():
                raise ValidationError('A solicitação de etapa arquivo não existe, portanto não pode ser atualizada.')
            solicitacao_etapa_arquivo = solicitacao_etapa_arquivo.first()
            solicitacao_etapa_arquivo_created = False
        else:
            solicitacao_etapa_arquivo = SolicitacaoEtapaArquivo()
            solicitacao_etapa_arquivo_created = True

        try:
            with transaction.atomic():
                arquivo_unico_created = False
                arquivo_unico, arquivo_unico_created = ArquivoUnico.get_or_create_from_file_bytes(
                    bytes=bytes,
                    tipo_conteudo=tipo_conteudo,
                    nome_original_primeiro_upload=nome_original,
                    data_hora_primeiro_upload=data_hora_upload,
                    tamanho_em_bytes_para_validar=tamanho_em_bytes_para_validar,
                    hash_sha512_para_validar=hash_sha512_para_validar,
                )

                # Setando os atributos da SolicitacaoEtapaArquivo.
                solicitacao_etapa_arquivo.arquivo_unico = arquivo_unico
                solicitacao_etapa_arquivo.nome_original = nome_original
                solicitacao_etapa_arquivo.nome_exibicao = nome_exibicao
                solicitacao_etapa_arquivo.add_extensao_ao_nome_exibicao_com_base_no_nome_original()
                solicitacao_etapa_arquivo.descricao = descricao
                solicitacao_etapa_arquivo.data_hora_upload = data_hora_upload
                solicitacao_etapa_arquivo.solicitacao_etapa = solicitacao_etapa
                solicitacao_etapa_arquivo.nome_atributo_json = nome_atributo_json
                solicitacao_etapa_arquivo.save()

                return solicitacao_etapa_arquivo, solicitacao_etapa_arquivo_created, arquivo_unico, arquivo_unico_created
        except Exception as e:
            if arquivo_unico_created:
                arquivo_unico.conteudo.delete(save=False)
            raise e

    @classmethod
    def update_or_create_from_file_strb64(
        cls,
        strb64,
        tipo_conteudo,
        data_hora_upload,
        nome_original,
        nome_exibicao,
        descricao,
        solicitacao_etapa,
        nome_atributo_json,
        tamanho_em_bytes_para_validar=None,
        hash_sha512_para_validar=None,
        solicitacao_etapa_arquivo_id=None,
    ):
        """
        Método de classe que cria ou atualiza um arquivo com base em string base64.

        Args:
            strb64 (string): String base64 que compõem o arquivo.
            tipo_conteudo (): Tipo do conteúdo.
            data_hora_upload (datetime): Data na qual o arquivo foi submetido.
            nome_original (string): Nome original do arquivo submetido.
            nome_exibicao (string): Nome que deve ser utilizado para a exibição
            descricao (string): Descrição que o cidadão deu para o arquivo.
            solicitacao_etapa (SolicitacaoEtapa): Indica qual é a etapa associada ao arquivo.
            nome_atributo_json:
            tamanho_em_bytes_para_validar (int): Tamanha do arquivo em bytes para validar o arquivo.
            hash_sha512_para_validar (string): Hash, sha512, dos bytes do arquivo para validação.
            solicitacao_etapa_arquivo_id (int): Id do arquivo contido na etapa da solicitação.

        Raises:
            ValidationError: Caso a etapa não exista.
            Exception:

        Returns:
            Tupla contendo:
                * Instância de SolicitacaoEtapaArquivo;
                * Bool indicado se a SolicitacaoEtapaArquivo foi criada;
                * Instãncia de arquivo único;
                * Bool indicando se o arquivo único foi criado.
        """
        bytes_b64 = strb64.encode('utf-8')
        bytes = base64.b64decode(bytes_b64)
        return cls.update_or_create_from_file_bytes(
            bytes,
            tipo_conteudo,
            data_hora_upload,
            nome_original,
            nome_exibicao,
            descricao,
            solicitacao_etapa,
            nome_atributo_json,
            tamanho_em_bytes_para_validar,
            hash_sha512_para_validar,
            solicitacao_etapa_arquivo_id,
        )


class RegistroNotificacaoGovBR(models.Model):
    """
    Armazena o registro de notificações enviadas do SUAP pela plataforma Notifica do GovBR

    """

    SMS = 0
    EMAIL = 1
    APP = 2
    EMAIL_SUAP = 3
    LIGACAO = 4
    TIPO_CHOICES = [[SMS, 'SMS'], [EMAIL, 'Email'], [APP, 'Aplicativo'], [EMAIL_SUAP, 'Email Suap'], [LIGACAO, 'Ligação Telefônica']]
    response_content = models.JSONField(null=True)
    #: Solicitação ligado a notificação
    mensagem = models.TextField('Mensagem', null=True)
    solicitacao = models.ForeignKeyPlus(Solicitacao, on_delete=models.CASCADE)
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)
    data_envio = models.DateTimeFieldPlus('Data de Envio', null=True, blank=True)
    tipo = models.IntegerField(choices=TIPO_CHOICES)
    enviada = models.BooleanField(default=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Registro de Notificação Enviada pela Plataforma Notifica'
        verbose_name_plural = 'Registros de Notificações Enviadas pela Plataforma Notifica'

    def __str__(self):
        return 'Solicitação {} - {} - notificado em {}'.format(
            self.solicitacao.id, self.solicitacao.status, self.data_criacao.strftime('%d/%m/%Y %H:%M')
        )

    def get_tipo_display(self):
        """
        Obtem o valor amigável do tipo da notificacao.

        Returns:
            String contendo o valor detalhado do tipo da notificacao.
        """
        return mark_safe(self.TIPO_CHOICES[self.tipo][1])


class TemplateNotificaGovBR(models.Model):
    """
    Armazena o identificadores dos templates utilizados pelo serviço de notificação do GOV.BR para cada mensagem
    """

    CORRECAO_DADOS = 'CORRECAO_DADOS'
    DADOS_CORRIGIDOS = 'DADOS_CORRIGIDOS'
    NAO_ATENDIDA = 'NAO_ATENDIDA'
    SOLICITACAO_RECEBIDA = 'SOLICITACAO_RECEBIDA'
    CONCLUSAO_SOLICITACAO = 'CONCLUSAO_SOLICITACAO'
    CODIGO_VERIFICADOR = 'CODIGO_VERIFICADOR'

    TIPO_CHOICES = [
        [CORRECAO_DADOS, 'Solicitação de Correção de Dados'],
        [DADOS_CORRIGIDOS, 'Dados Corrigidos'],
        [NAO_ATENDIDA, 'Não Atendida'],
        [SOLICITACAO_RECEBIDA, 'Solicitação Recebida'],
        [CONCLUSAO_SOLICITACAO, 'Conclusão da Solicitação'],
        [CODIGO_VERIFICADOR, 'Código de Verificação'],
    ]

    SMS = 'SMS'
    APP_GOVBR = 'APP_GOVBR'
    CANAL_CHOICES = [[SMS, 'SMS'], [APP_GOVBR, 'Aplicativo Gov.BR']]

    id_template = models.CharFieldPlus(
        'Identificador do template', null=False, help_text='Id do template cadastrado em https://notificacao.servicos.gov.br/'
    )
    tipo_notificacao = models.CharFieldPlus('Tipo de Notificação do Balcão Digital', choices=TIPO_CHOICES, null=False)
    canal_notificacao = models.CharFieldPlus('Canal de Notificação', choices=CANAL_CHOICES, null=False)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Template de Notificação GOV.BR'
        verbose_name_plural = 'Templates de Notificação GOV.BR'

    def __str__(self):
        return self.tipo_notificacao
