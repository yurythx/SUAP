import abc


class ServiceProvider(metaclass=abc.ABCMeta):
    """
    Interface básica para prover serviços.
    """

    @abc.abstractmethod
    def get_id_servico_portal_govbr(self):
        """
        Método para obter o código do serviço do *gov.br*.

        Returns:
            String do código do serviço cadastrado no portal do *gov.br*.
        """

    @abc.abstractmethod
    def get_numero_total_etapas(self):
        """
        Método para obter o número total de etapas do serviço.

        Returns:
             Inteiro contendo o número total de etapas.
        """

    @abc.abstractmethod
    def get_avaliacao_disponibilidade(self, cpf, verbose=True):
        """
        Método para obter a disponibilidade de um serviço.

        Args:
            cpf (String): **CPF** do cidadão.
            verbose (Bool): Exibe logs ou não.

        Returns:
            XXX
        """

    @abc.abstractmethod
    def receber_solicitacao(self, request, cpf):
        """
        Método para recebmento dos dados de uma etapa.

        Args:
            request (HTTPRequest): request da solicitação.
            cpf (String): **CPF** do cidadão.
        """

    @abc.abstractmethod
    def executar_solicitacao(self, request, solicitacao):
        """
        Método responsável pela execução da solicitação.

        Args:
            request: request (HTTPRequest): request da solicitação.
            solicitacao (Solicitacao): Solicitação pronta para execução.
        """

    @abc.abstractmethod
    def get_dados_email(self, solicitacao):
        """
        Método que obtem o e-mail do cidadão com base na solicitação.

        Args:
            solicitacao (Solicitacao): Solicitação pronta para execução.

        Returns:
            String contendo o e-mail do cidadão.
        """

    @abc.abstractmethod
    def is_em_periodo_avaliacao(self, solicitacao, campus=None):
        """
        Método que verifica se a solicitação está em período de avaliação.

        Args:
            solicitacao (Solicitacao): Solicitação pronta para execução.

        Returns:
            Bool indicando se o período de avaliação está ativo.
        """

    @abc.abstractmethod
    def registrar_acompanhamento(self, solicitacao=None, registro_acompanhamento=None):
        """
        Método que realiza o registro de acompanhamento junto ao *gov.br*.

        Args:
            solicitacao (Solicitacao): Solicitação pronta para execução.
        """

    @abc.abstractmethod
    def registrar_conclusao(self, solicitacao=None, registro_acompanhamento=None):
        """
        Método que realiza o registro de conclusão junto ao *gov.br*.

        Args:
            solicitacao (Solicitacao): Solicitação pronta para execução.
        """

    @abc.abstractmethod
    def obter_formulario_avaliacao(self, solicitacao=None, registro_acompanhamento=None):
        """
        Método que obtem o formulário de avaliação junto ao *gov.br*.

        Args:
            solicitacao (Solicitacao): Solicitação pronta para execução.
            verbose (Boolean): Imprime o processo de obtenção do formulário.
        """


class ServiceProviderFactory(metaclass=abc.ABCMeta):
    """
    Interface básica para fábricas de provedores de serviço.
    """

    @abc.abstractmethod
    def get_service_provider(id_servico_portal_govbr):
        """
        Método que obtem o provedor de serviço.

        Args:
            id_servico_portal_govbr (int): código do serviço cadastrado no portal *gov.br*.
        """

    @abc.abstractmethod
    def get_avaliacoes_disponibilidade_servicos(cpf, id_servico_portal_govbr=None, avaliar_somente_servicos_ativos=False):
        """
        Método que obtem a disponibilidade de um determinado serviço.

        Args:
            cpf (String): **CPF** do cidadão.
            id_servico_portal_govbr (int): código do serviço cadastrado no portal *gov.br*.
            avaliar_somente_servicos_ativos (bool): indica se deve-se avaliar somente serviços ativos.

        Returns:
            XXX
        """

    @abc.abstractmethod
    def get_servicos_disponiveis(cpf, id_servico_portal_govbr=None):
        """
        Método que obtem a disponibilidade de um determinado serviço.

        Args:
            cpf (String): **CPF** do cidadão.
            id_servico_portal_govbr (int): código do serviço cadastrado no portal *gov.br*.

        Returns:
            XXX
        """

    @abc.abstractmethod
    def get_servicos_ativos(id_servico_portal_govbr=None):
        """
        Método que obterm a lista de serviços ativos.

        Args:
            id_servico_portal_govbr (int): código do serviço cadastrado no portal *gov.br*.

        Returns:
            Lista de serviços ativos.
        """
