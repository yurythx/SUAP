import datetime

from tinymce.models import HTMLField
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from comum.models import Configuracao

from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.utils import send_mail, send_notification
from rh import utils


PRIVATE_ROOT_DIR = 'private-media/rsc'


class ProcessoRSC(models.EncryptedPKModel):
    SEARCH_FIELDS = ('processo__servidor__matricula', 'processo__servidor__pessoa_fisica__nome', 'avaliador__vinculo__pessoa__nome')
    """
    RESOLUÇÃO Nº 1, DE 20 DE FEVEREIRO DE 2014
    Art. 15. A presente Resolução entra em vigor na data de sua publicação e seus efeitos retroagem a 1º de março de 2013.
    """
    DATA_LEI_RETROATIVIDADE = datetime.date(2013, 3, 1)

    STATUS_APROVADO = 0
    STATUS_REPROVADO = 1
    STATUS_AGUARDANDO_VALIDACAO_CPPD = 2
    STATUS_AGUARDANDO_ENVIO_CPPD = 3
    STATUS_AGUARDANDO_AVALIADORES = 4
    STATUS_AGUARDANDO_AJUSTES_USUARIO = 5
    STATUS_REJEITADO = 6
    STATUS_AGUARDANDO_NOVA_VALIDACAO = 7
    STATUS_AGUARDANDO_ACEITE_AVALIADOR = 8
    STATUS_EM_AVALIACAO = 9
    STATUS_CIENTE_DO_RESULTADO = 10
    STATUS_AGUARDANDO_CIENCIA = 11
    STATUS_ANALISADO = 12

    TIPO_PROCESSO_APOSENTADO = 0
    TIPO_PROCESSO_GERAL = 1

    CONCORDA_DEFERIMENTO = 1
    DISCORDA_DEFERIMENTO = 2
    CONCORDA_DEFERIMENTO_CHOICES = [
        [CONCORDA_DEFERIMENTO, 'Concorda com o resultado da avaliação(deferimento/indeferimento)'],
        [DISCORDA_DEFERIMENTO, 'Discorda do resultado da avaliação(deferimento/indeferimento)'],
    ]

    CONCORDA_DATA_RETROATIVIDADE = 1
    DISCORDA_DATA_RETROATIVIDADE = 2
    CONCORDA_DATA_RETROATIVIDADE_CHOICES = [
        [CONCORDA_DATA_RETROATIVIDADE, 'Concorda com a data de retroatividade concedida'],
        [DISCORDA_DATA_RETROATIVIDADE, 'Discorda da data de retroatividade concedida'],
    ]

    STATUS_CHOICES = [
        [STATUS_APROVADO, 'Deferido'],
        [STATUS_REPROVADO, 'Indeferido'],
        [STATUS_AGUARDANDO_VALIDACAO_CPPD, 'Aguardando validação CPPD'],
        [STATUS_AGUARDANDO_ENVIO_CPPD, 'Aguardando envio para CPPD'],
        [STATUS_AGUARDANDO_AVALIADORES, 'Aguardando avaliadores'],
        [STATUS_AGUARDANDO_AJUSTES_USUARIO, 'Aguardando ajustes do usuário'],
        [STATUS_REJEITADO, 'Rejeitado'],
        [STATUS_AGUARDANDO_NOVA_VALIDACAO, 'Aguardando nova validação'],
        [STATUS_AGUARDANDO_ACEITE_AVALIADOR, 'Aguardando aceite dos avaliadores'],
        [STATUS_EM_AVALIACAO, 'Em avaliação'],
        [STATUS_CIENTE_DO_RESULTADO, 'Ciente do resultado'],
        [STATUS_AGUARDANDO_CIENCIA, 'Aguardando ciência'],
        [STATUS_ANALISADO, 'Analisado'],
    ]

    TIPO_PROCESSO_CHOICES = [[TIPO_PROCESSO_APOSENTADO, 'Tipo de Processo Aposentado'], [TIPO_PROCESSO_GERAL, 'Tipo de Processo Geral']]
    protocolo = models.ForeignKeyPlus('protocolo.Processo', blank=True, null=True, on_delete=models.CASCADE)
    processo_eletronico = models.ForeignKeyPlus('processo_eletronico.Processo', null=True, editable=False)
    servidor = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    tipo_rsc = models.ForeignKeyPlus('rsc.TipoRsc', blank=False, null=False, verbose_name='RSC Pretendido', on_delete=models.CASCADE)
    numero = models.IntegerField('Número do Processo', blank=True, null=True)
    pontuacao_validada_com_corte = models.DecimalFieldPlus('Pontuação Validada', blank=True, null=True)
    pontuacao_validada_sem_corte = models.DecimalFieldPlus('Pontuação Validada Sem Corte', blank=True, null=True)
    pontuacao_pretendida = models.DecimalFieldPlus('Pontuação Requerida', blank=True, null=True)
    pontuacao_pretendida_rsc1 = models.DecimalFieldPlus(blank=True, null=True)
    pontuacao_pretendida_rsc2 = models.DecimalFieldPlus(blank=True, null=True)
    pontuacao_pretendida_rsc3 = models.DecimalFieldPlus(blank=True, null=True)
    status = models.IntegerField('Situação do Processo', choices=STATUS_CHOICES)
    tipo_processo = models.IntegerField('Tipo de processo', choices=TIPO_PROCESSO_CHOICES, default=TIPO_PROCESSO_GERAL)
    introducao_relatorio_descritivo = models.TextField(blank=True)
    conclusao_relatorio_descritivo = models.TextField(blank=True)
    itinerario_formacao = models.TextField(blank=True)
    atuacao_docente = models.TextField(blank=True)
    producao_cademica = models.TextField(blank=True)
    prestacao_servicos = models.TextField(blank=True)
    atividade_adm = models.TextField(blank=True)
    titulos_homenagens = models.TextField(blank=True)
    data_concessao_ultima_rt = models.DateFieldPlus('Data de Concessão', blank=False, null=True)
    data_exercio_carreira = models.DateFieldPlus('Data de Exercício na Carreira', blank=False, null=True)
    data_conclusao_titulacao_rsc_pretendido = models.DateFieldPlus('Data de Conclusão da Titulação para RSC Pretendido', blank=False, null=True)
    concorda_deferimento = models.IntegerField('Concorda com o deferimento', blank=True, null=True, choices=CONCORDA_DEFERIMENTO_CHOICES)
    concorda_data_retroatividade = models.IntegerField(
        'Concorda com a data de retroatividade', blank=True, null=True, choices=CONCORDA_DATA_RETROATIVIDADE_CHOICES
    )
    data_ciencia = models.DateTimeFieldPlus('Data da Ciência', blank=True, null=True, default=None)
    data_finalizacao_processo = models.DateTimeFieldPlus('Data de Finalização do Processo', blank=True, null=True, default=None)
    assinatura_requerimento = models.TextField('Assinatura do Requerimento', blank=True, null=True, default='')

    clonado = models.BooleanField('Clonado', default=False)

    objects = models.EncryptedPKModelManager()

    class Meta:
        verbose_name = 'Processo de RSC'
        verbose_name_plural = 'Processos de RSC'
        permissions = (('pode_validar_processorsc', 'Pode validar ProcessoRSC'), ('pode_ver_relatorio_rsc', 'Pode ver relatório RSC'))

    def __str__(self):
        return f'{self.tipo_rsc} - {self.servidor}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = ConfiguracaoRSC.objects.first()

    """
    quantidade de avaliadores internos reservas no processo
    """

    def qtd_avaliadores_internos_reserva(self):
        return ProcessoAvaliador.objects.filter(
            processo=self, tipo_avaliador=ProcessoAvaliador.AVALIADOR_INTERNO, status=ProcessoAvaliador.EM_ESPERA
        ).count()

    """
    quantidade de avaliadores externos reservas no processo
    """

    def qtd_avaliadores_externos_reserva(self):
        return ProcessoAvaliador.objects.filter(
            processo=self, tipo_avaliador=ProcessoAvaliador.AVALIADOR_EXTERNO, status=ProcessoAvaliador.EM_ESPERA
        ).count()

    """
    quantidade de avaliadores internos que estão ativos no processo
    """

    def qtd_avaliadores_internos_ativos(self):
        return ProcessoAvaliador.objects.filter(
            processo=self,
            tipo_avaliador=ProcessoAvaliador.AVALIADOR_INTERNO,
            status__in=[ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.AVALIACAO_FINALIZADA, ProcessoAvaliador.EM_AVALIACAO],
        ).count()

    """
    quantidade de avaliadores externos que estão ativos no processo
    """

    def qtd_avaliadores_externos_ativos(self):
        return ProcessoAvaliador.objects.filter(
            processo=self,
            tipo_avaliador=ProcessoAvaliador.AVALIADOR_EXTERNO,
            status__in=[ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.AVALIACAO_FINALIZADA, ProcessoAvaliador.EM_AVALIACAO],
        ).count()

    def tem_algum_avaliador_ativo(self) -> bool:
        """Indica se há ao menos um avaliador ativo (interno ou externo) no processo.

        Usado para iniciar as avaliações assim que o primeiro avaliador é
        cadastrado, sem aguardar a banca completa (1 interno + 2 externos). A
        conclusão do processo continua exigindo 3 avaliações finalizadas.
        """
        return ProcessoAvaliador.objects.filter(
            processo=self,
            status__in=[ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.AVALIACAO_FINALIZADA, ProcessoAvaliador.EM_AVALIACAO],
        ).exists()

    def avaliador_interno_pagamento(self):
        return ProcessoAvaliador.objects.filter(
            processo=self, status=ProcessoAvaliador.AVALIACAO_FINALIZADA, tipo_avaliador=ProcessoAvaliador.AVALIADOR_INTERNO
        )

    def avaliadores_externos_pagamento(self):
        return ProcessoAvaliador.objects.filter(
            processo=self, status=ProcessoAvaliador.AVALIACAO_FINALIZADA, tipo_avaliador=ProcessoAvaliador.AVALIADOR_EXTERNO
        )

    def pode_mostrar_avaliacao(self):
        retorno = False
        if self.status in [
            self.STATUS_APROVADO,
            self.STATUS_REPROVADO,
            self.STATUS_AGUARDANDO_CIENCIA,
            self.STATUS_CIENTE_DO_RESULTADO,
            self.STATUS_ANALISADO,
        ]:
            retorno = True
        return retorno

    def pode_selecionar_avaliadores(self):
        retorno = False
        if (
            self.status == self.STATUS_AGUARDANDO_AVALIADORES
            or self.status == self.STATUS_AGUARDANDO_ACEITE_AVALIADOR
            or self.status == self.STATUS_EM_AVALIACAO
        ):
            retorno = True
        return retorno

    def pode_ser_validado(self):
        retorno = False
        if self.status == ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD or self.status == ProcessoRSC.STATUS_AGUARDANDO_NOVA_VALIDACAO:
            retorno = True
        return retorno

    def ultima_validacao_processo(self):
        retorno = None
        qs = ValidacaoCPPD.objects.filter(processo=self).order_by('-data')
        if qs.exists():
            retorno = qs[0]
        return retorno

    """
    editar: o usuário pode editar antes de enviar a CPPD
    """

    def avaliado_pode_editar(self):
        retorno = False
        if self.status in [self.STATUS_AGUARDANDO_ENVIO_CPPD, self.STATUS_AGUARDANDO_AJUSTES_USUARIO]:
            retorno = True
        return retorno

    """
    ajustar: o usuário pode ajustar depois que a CPPD avaliou e rejeitou o processo
    OBS: só poderá o avaliado ajustar os campos texto do processo
    """

    def avaliado_pode_ajustar(self):
        retorno = False
        if self.status == self.STATUS_AGUARDANDO_AJUSTES_USUARIO:
            retorno = True
        return retorno

    def get_pontuacao_pretendida_rsc1(self):
        retorno = self.pontuacao_pretendida_rsc1
        if not retorno:
            retorno = 0
        return retorno

    def get_pontuacao_pretendida_rsc2(self):
        retorno = self.pontuacao_pretendida_rsc2
        if not retorno:
            retorno = 0
        return retorno

    def get_pontuacao_pretendida_rsc3(self):
        retorno = self.pontuacao_pretendida_rsc3
        if not retorno:
            retorno = 0
        return retorno

    @classmethod
    def lista_processos(cls, request):
        processos = cls.objects.filter(servidor__id=request.user.get_profile().id)
        return processos

    def get_arquivo_titulacao(self):
        retorno = None
        qs = self.arquivosexigidos_set.filter(tipo=ArquivosExigidos.TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO)
        if qs.exists():
            retorno = qs[0]
        return retorno

    def get_arquivo_inicio_exercicio(self):
        retorno = None
        qs = self.arquivosexigidos_set.filter(tipo=ArquivosExigidos.INICIO_EXERCIO_CARREIRA)
        if qs.exists():
            retorno = qs[0]
        return retorno

    def get_arquivo_ultima_concessao_rt(self):
        retorno = None
        qs = self.arquivosexigidos_set.filter(tipo=ArquivosExigidos.CONCESSAO_ULTIMA_RT)
        if qs.exists():
            retorno = qs[0]
        return retorno

    def get_arquivos_rsc_pretendido(self):
        return self.arquivo_set.filter(criterio__diretriz__tipo_rsc=self.tipo_rsc).order_by('data_referencia')

    """
    método que devolte as datas validadas pelos avaliadores, levando em consideração as regras:
    1-se duas datas avaliadas coincidir, será esta a data validada;
    2-se todas as datas divergirem, será adotada a pior data para o avaliado (mais recente).
    """

    def get_arquivos_avaliacoes(self, rsc_pretendido=True, avaliador=None, exclude_arquivo_ids=None):
        # selecionando as avaliações do processo
        if exclude_arquivo_ids is None:
            exclude_arquivo_ids = []
        avaliacoes = Avaliacao.objects.filter(processo=self, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA, Avaliacao.EM_AVALIACAO])

        # caso o avaliador seja passado por parâmetro, será filtrado na avaliação
        if avaliador:
            avaliacoes = avaliacoes.filter(avaliador=avaliador)

        datas_por_arquivo = {}
        for avaliacao in avaliacoes:
            itens_avaliacao = avaliacao.avaliacaoitem_set.all()

            if exclude_arquivo_ids:
                itens_avaliacao = itens_avaliacao.exclude(arquivo__pk__in=exclude_arquivo_ids)

            if rsc_pretendido:
                itens_avaliacao = itens_avaliacao.filter(arquivo__criterio__diretriz__tipo_rsc=self.tipo_rsc)

            for item in itens_avaliacao:
                # verificando se o item possui data de referência validada e se o item não foi invalidado pelo avaliador
                if item.data_referencia and item.qtd_itens_validado and item.qtd_itens_validado > 0:
                    if item.arquivo_id in datas_por_arquivo:
                        datas_por_arquivo[item.arquivo_id].append(item.data_referencia)
                    else:
                        datas_por_arquivo[item.arquivo_id] = [item.arquivo, item.data_referencia]

        qtd_igualdade = 2
        result = []
        for values in list(datas_por_arquivo.values()):
            arquivo = values.pop(0)
            for data in values:
                qtd = values.count(data)
                if qtd >= qtd_igualdade:
                    data_validada = data
                    break
                else:
                    data_validada = max(values)

            arquivo.data_referencia_validada = data_validada
            result.append(arquivo)

        result = sorted(result, key=lambda arquivo: arquivo.data_referencia_validada)

        return result

    def get_data_referencia_retroativa(self, validada=False, soh_arquivos=False, avaliador=None):
        data_referencia = None

        # Verificando se o avaliador tem uma avaliação e se esta é indeferida. Caso positivo, não
        # existirá data de retroatividade.
        if validada and avaliador is not None:
            qs_avaliacao = Avaliacao.objects.filter(processo=self, avaliador=avaliador, status__in=[Avaliacao.INDEFERIDA])
            if qs_avaliacao.exists():
                return None

        arquivos_rsc_pretendido = None
        if validada:
            arquivos_rsc_pretendido = self.get_arquivos_avaliacoes(True, avaliador)
        else:
            arquivos_rsc_pretendido = self.get_arquivos_rsc_pretendido()

        pontos_diretriz = {}
        id_arquivos_utilizados_rsc_pretendida = []
        """
        verificando se o requerente tem os 25 pontos na rsc pretendida
        """
        for arquivo in arquivos_rsc_pretendido:
            """
            somando valores por diretriz para verificação posterior do teto
            """
            if arquivo.criterio.diretriz_id in pontos_diretriz:
                pontos_diretriz[arquivo.criterio.diretriz_id].append(arquivo.nota_pretendida)
            else:
                pontos_diretriz[arquivo.criterio.diretriz_id] = [arquivo.nota_pretendida]

            if sum(pontos_diretriz[arquivo.criterio.diretriz_id]) >= arquivo.criterio.diretriz.teto:
                pontos_diretriz[arquivo.criterio.diretriz_id] = [arquivo.criterio.diretriz.teto]

            pontos = self._soma_pontos(list(pontos_diretriz.values()))
            id_arquivos_utilizados_rsc_pretendida.append(arquivo.id)
            if pontos >= 25:
                if validada:
                    data_referencia = arquivo.data_referencia_validada
                else:
                    data_referencia = arquivo.data_referencia
                break

        """
        verificando se o requerente tem os 50 pontos na soma das rsc's
        """
        arquivos_restantes = Arquivo.objects.none()
        if validada:
            arquivos_restantes = self.get_arquivos_avaliacoes(False, avaliador, id_arquivos_utilizados_rsc_pretendida)
        else:
            arquivos_restantes = self.arquivo_set.all().exclude(pk__in=id_arquivos_utilizados_rsc_pretendida).order_by('data_referencia')

        for arquivo in arquivos_restantes:
            """
            somando valores por diretriz para verificação posterior do teto
            """
            if arquivo.criterio.diretriz_id in pontos_diretriz:
                pontos_diretriz[arquivo.criterio.diretriz_id].append(arquivo.nota_pretendida)
            else:
                pontos_diretriz[arquivo.criterio.diretriz_id] = [arquivo.nota_pretendida]

            if sum(pontos_diretriz[arquivo.criterio.diretriz_id]) >= arquivo.criterio.diretriz.teto:
                pontos_diretriz[arquivo.criterio.diretriz_id] = [arquivo.criterio.diretriz.teto]

            """
            verificando se o arquivo tem data de referência maior que a já armazenada
            """
            if validada:
                if data_referencia and arquivo.data_referencia_validada > data_referencia:
                    data_referencia = arquivo.data_referencia_validada
            else:
                if data_referencia and arquivo.data_referencia and arquivo.data_referencia > data_referencia:
                    data_referencia = arquivo.data_referencia

            pontos = self._soma_pontos(list(pontos_diretriz.values()))
            if pontos >= 50:
                break

        if soh_arquivos:
            return data_referencia

        """
        selecionando ultima validação realizada no processo (se existir)
        """
        ultima_validacao = self.ultima_validacao_processo()

        """
        verificando se a data da titulação é maior que a data de referência setada
        """
        if ultima_validacao and ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada:
            data_titulacao = ultima_validacao.data_conclusao_titulacao_rsc_pretendido_validada
        else:
            data_titulacao = self.data_conclusao_titulacao_rsc_pretendido

        if data_titulacao and data_referencia and data_titulacao > data_referencia:
            data_referencia = data_titulacao

        """
        verificando se a data de início de exercício é maior que a data de referência setada
        """
        if ultima_validacao and ultima_validacao.data_exercio_carreira_validada:
            data_exercicio = ultima_validacao.data_exercio_carreira_validada
        else:
            data_exercicio = self.data_exercio_carreira

        if data_exercicio and data_referencia and data_exercicio > data_referencia:
            data_referencia = data_exercicio

        """
        verificando se a data da última RT é maior que a data de referência setada
        """
        if ultima_validacao and ultima_validacao.data_concessao_ultima_rt_validada:
            data_concessao_ultima_rt = ultima_validacao.data_concessao_ultima_rt_validada
        else:
            data_concessao_ultima_rt = self.data_concessao_ultima_rt

        if data_concessao_ultima_rt and data_referencia and data_concessao_ultima_rt > data_referencia:
            data_referencia = data_concessao_ultima_rt

        """
        verificando se a data de referência calculada é menor que a data de retroatividade prevista em resolução
        caso positivo, a data mínima deverá ser a data prevista na resolução
        """
        if self.DATA_LEI_RETROATIVIDADE and data_referencia and data_referencia < self.DATA_LEI_RETROATIVIDADE:
            data_referencia = self.DATA_LEI_RETROATIVIDADE

        return data_referencia

    """
    Data de referencia final do processo
    É calculada levando em consideração os resultados das avaliações do processo
    """

    def get_data_referencia_final(self):
        if self.status not in [
            ProcessoRSC.STATUS_APROVADO,
            ProcessoRSC.STATUS_REPROVADO,
            ProcessoRSC.STATUS_CIENTE_DO_RESULTADO,
            ProcessoRSC.STATUS_AGUARDANDO_CIENCIA,
            ProcessoRSC.STATUS_ANALISADO,
        ]:
            return None

        if self.estado_atual_processo() == ProcessoRSC.STATUS_REPROVADO:
            return None

        avaliacoes = self.avaliacao_set.filter(status__in=[Avaliacao.DEFERIDA])
        data_referencia = self.DATA_LEI_RETROATIVIDADE
        datas_list = []
        for avaliacao in avaliacoes:
            data_retroatividade_avaliacao = self.get_data_referencia_retroativa(True, False, avaliacao.avaliador)
            datas_list.append(data_retroatividade_avaliacao)

            # se exisitir duas ou mais avaliações com a mesma data validada, esta será a data do processo

            if datas_list.count(data_retroatividade_avaliacao) >= 2 and data_retroatividade_avaliacao:
                return data_retroatividade_avaliacao

            # caso não exista consenso entre as data das avaliações, pegar sempre a maior data
            if data_retroatividade_avaliacao and data_retroatividade_avaliacao > data_referencia:
                data_referencia = data_retroatividade_avaliacao

        return data_referencia

    """
    soma valores de uma lista de listas
    """

    def _soma_pontos(self, lista_de_lista):
        valor = 0
        for item_lista in lista_de_lista:
            for item in item_lista:
                valor += item
        return valor

    @transaction.atomic
    def criar_avaliacao(self, avaliador):
        # criando a avaliação
        avaliacao = Avaliacao()
        avaliacao.processo = self
        avaliacao.avaliador = avaliador
        avaliacao.status = Avaliacao.EM_AVALIACAO
        avaliacao.save()

        # criando os itens que serão avaliados
        for arquivo in self.arquivo_set.all().order_by('data_referencia'):
            avaliacao_item = AvaliacaoItem()
            avaliacao_item.avaliacao = avaliacao
            avaliacao_item.arquivo = arquivo
            avaliacao_item.save()

    """
    método que calcula as pontuações com corte e sem corte para serem utilizados na finalização da avaliação do processo
    """

    def _calculo_pontos(self, status, com_corte=False, avaliador=None):
        pontos = 0
        avaliacoes = Avaliacao.objects.filter(processo=self, status__in=status)
        if avaliador:
            avaliacoes = avaliacoes.filter(avaliador=avaliador)
        pontuacao_avaliador = {}
        for avaliacao in avaliacoes:
            pontuacao = 0
            pontuacao_diretriz = {}
            for item in avaliacao.avaliacaoitem_set.all():
                if item.pontuacao_validada():
                    if com_corte:
                        if item.arquivo.criterio.diretriz_id in pontuacao_diretriz:
                            pontuacao_diretriz[item.arquivo.criterio.diretriz_id] += item.pontuacao_validada()
                        else:
                            pontuacao_diretriz[item.arquivo.criterio.diretriz_id] = item.pontuacao_validada()
                        if pontuacao_diretriz[item.arquivo.criterio.diretriz_id] > item.arquivo.criterio.diretriz.teto:
                            pontuacao_diretriz[item.arquivo.criterio.diretriz_id] = item.arquivo.criterio.diretriz.teto
                    else:
                        pontuacao += item.pontuacao_validada()

            if com_corte:
                pontuacao = sum(pontuacao_diretriz.values())
            if avaliacao.avaliador_id in pontuacao_avaliador:
                pontuacao_avaliador[avaliacao.avaliador_id] += pontuacao
            else:
                pontuacao_avaliador[avaliacao.avaliador_id] = pontuacao

        """
        verificando se existe concordância entre pelo menos dois avaliadores com relação aos pontos
        """
        num_check = 2
        for test_pontuacao in list(pontuacao_avaliador.values()):
            qtd_pontuacao = list(pontuacao_avaliador.values()).count(test_pontuacao)
            if qtd_pontuacao >= num_check:
                pontos = test_pontuacao
                break
        if pontos == 0 and len(list(pontuacao_avaliador.values())) > 0:
            if status == Avaliacao.DEFERIDA:
                pontos = min(pontuacao_avaliador.values())
            else:
                pontos = max(pontuacao_avaliador.values())

        return pontos

    def calcula_aprovacao(self):
        estado_atual = self.status
        avaliacoes_deferidas = Avaliacao.objects.filter(processo=self, status=Avaliacao.DEFERIDA)
        avaliacoes_indeferidas = Avaliacao.objects.filter(processo=self, status=Avaliacao.INDEFERIDA)

        if avaliacoes_indeferidas.count() > avaliacoes_deferidas.count():
            estado_atual = self.STATUS_REPROVADO
        else:
            estado_atual = self.STATUS_APROVADO
        return estado_atual

    def estado_atual_processo(self):
        if not self.servidor.eh_aposentado:
            estado_atual = self.calcula_aprovacao()
        else:
            if self.status not in [self.STATUS_ANALISADO, self.STATUS_APROVADO]:
                estado_atual = self.STATUS_ANALISADO
            else:  # se já analisado
                estado_atual = self.calcula_aprovacao()
        return estado_atual

    def finalizar_processo(self):
        situacao = self.estado_atual_processo()
        if situacao == self.STATUS_REPROVADO:
            self.status = self.STATUS_REPROVADO
        elif situacao == self.STATUS_APROVADO:
            self.status = self.STATUS_APROVADO
        else:
            self.status = self.STATUS_ANALISADO
        self.data_finalizacao_processo = datetime.date.today()
        self.save()

    def deferir_processo_aposentado(self):
        situacao = self.estado_atual_processo()
        if situacao == self.STATUS_REPROVADO:
            self.status = self.STATUS_REPROVADO
        elif situacao == self.STATUS_APROVADO:
            self.status = self.STATUS_APROVADO
        else:
            self.status = self.STATUS_ANALISADO
        self.data_finalizacao_processo = datetime.date.today()
        self.tipo_processo = ProcessoRSC.TIPO_PROCESSO_APOSENTADO
        self.save()

    def dar_ciencia_resultado(self, opcao_ciencia_deferimento, opcao_ciencia_data_retroatividade):
        if opcao_ciencia_deferimento and opcao_ciencia_data_retroatividade:
            if int(opcao_ciencia_deferimento) == 1:
                self.concorda_deferimento = self.CONCORDA_DEFERIMENTO
            else:
                self.concorda_deferimento = self.DISCORDA_DEFERIMENTO

            if int(opcao_ciencia_data_retroatividade) == 1:
                self.concorda_data_retroatividade = self.CONCORDA_DATA_RETROATIVIDADE
            else:
                self.concorda_data_retroatividade = self.DISCORDA_DATA_RETROATIVIDADE

            self.status = self.STATUS_CIENTE_DO_RESULTADO
            self.data_ciencia = datetime.date.today()
            self.save()

    def get_ciencia_display(self):
        retorno = 'Você CONCORDOU com o resultado da avaliação(deferimento/indeferimento) e CONDORDOU com a data de retroatividade concedida.'
        if self.concorda_deferimento == self.CONCORDA_DEFERIMENTO and self.concorda_data_retroatividade == self.DISCORDA_DATA_RETROATIVIDADE:
            retorno = 'Você CONCORDOU com o resultado da avaliação(deferimento/indeferimento) e DISCORDOU da data de referência concedida.'
        elif self.concorda_deferimento == self.DISCORDA_DEFERIMENTO and self.concorda_data_retroatividade == self.CONCORDA_DATA_RETROATIVIDADE:
            retorno = 'Você DISCORDOU do resultado da avaliação(deferimento/indeferimento) e CONCORDOU com a data de referẽncia concedida.'
        elif self.concorda_deferimento == self.DISCORDA_DEFERIMENTO and self.concorda_data_retroatividade == self.DISCORDA_DATA_RETROATIVIDADE:
            retorno = 'Você DISCORDOU do resultado da avaliação(deferimento/indeferimento) e DISCORDOU da data de referẽncia concedida.'
        return retorno

    @property
    def status_estilizado(self):
        class_css = 'status-alert'  # padrao: status a iniciar
        status_display = self.get_status_display()
        if self.status == ProcessoRSC.STATUS_APROVADO:
            class_css = 'status-success'
        if self.status == ProcessoRSC.STATUS_REPROVADO or self.status == ProcessoRSC.STATUS_REJEITADO:
            class_css = 'status-error'
        if self.status == ProcessoRSC.STATUS_CIENTE_DO_RESULTADO:
            class_css = 'status-info'
            status_display = (
                f'{self.get_status_display()}: {self.get_concorda_deferimento_display()} e {self.get_concorda_data_retroatividade_display()}.'
            )
        return f"<span class='status {class_css} text-nowrap-normal'>{status_display}</span>"

    """
    função que diz se o interessado do processo faleceu
    """

    def interessado_falecido(self):
        return self.servidor.servidorocorrencia_set.filter(ocorrencia__nome__startswith='FALECIMENTO').exists()

    """
    função que retorna os avaliadores do processo
    """

    def banca_avaliadora_final(self):
        processos_avaliadores = ProcessoAvaliador.objects.filter(processo=self, status=ProcessoAvaliador.AVALIACAO_FINALIZADA).order_by(
            'avaliador__vinculo__pessoa__nome'
        )

        avaliadores = []
        for processo_avaliador in processos_avaliadores:
            avaliadores.append(processo_avaliador.avaliador)

        return avaliadores

    @property
    def conteudo_a_ser_assinado_do_requerimento(self):
        return f'{self.pk}{self.pontuacao_pretendida}'

    @property
    def chave_a_ser_utilizada_na_assinatura_do_requerimento(self):
        return f'{self.servidor_id}'

    def get_status_aguardando_ciencia(self):
        return self.STATUS_AGUARDANDO_CIENCIA


class Arquivo(models.EncryptedPKModel):
    processo = models.ForeignKeyPlus(
        'rsc.ProcessoRSC', blank=True, null=False, verbose_name='processo associado ao arquivo', on_delete=models.CASCADE
    )
    criterio = models.ForeignKeyPlus('rsc.Criterio', blank=True, null=True, verbose_name='critério associado ao arquivo', on_delete=models.CASCADE)
    nome = models.CharFieldPlus(max_length=255)
    diretorio = models.CharFieldPlus(max_length=255, unique=True)
    nota_pretendida = models.DecimalFieldPlus(default=0, null=True)
    qtd_itens = models.IntegerField(blank=False, null=True)
    data_referencia = models.DateField('Data de Referência', blank=False, null=True)
    tamanho = models.BigIntegerField()
    descricao = models.TextField(blank=True)

    objects = models.EncryptedPKModelManager()

    class Meta:
        verbose_name = 'Arquivo'
        verbose_name_plural = 'Arquivos'

    def get_data_referencia(self):
        avaliacoes_itens = AvaliacaoItem.objects.filter(arquivo=self)
        list_datas = []
        maior_data = self.data_referencia
        for avaliacao_item in avaliacoes_itens:
            if avaliacao_item.data_referencia and avaliacao_item.qtd_itens_validado and avaliacao_item.qtd_itens_validado > 0:
                if not maior_data:
                    maior_data = avaliacao_item.data_referencia
                elif maior_data < avaliacao_item.data_referencia:
                    maior_data = avaliacao_item.data_referencia
                    list_datas.append(maior_data)
                    continue
                list_datas.append(avaliacao_item.data_referencia)

        # verificando se existe pelo menos duas datas de avaliadores que coincidiram. Caso positivo a data de referência será ela.
        num_check = 2
        for test_data in list_datas:
            qtd_data = list_datas.count(test_data)
            if qtd_data >= num_check:
                return test_data  # data de referência escolhida pela maioria dos avaliadores

        # se não houver acordo da data de referência entre os avaliadores, iremos retornar a maior data
        return maior_data

    def get_qtd_itens(self, avaliador):
        qtd_itens = self.qtd_itens
        avaliacao_item = AvaliacaoItem.objects.filter(arquivo=self, avaliacao__avaliador=avaliador)
        if avaliacao_item.exists() and avaliacao_item[0].qtd_itens_validado is not None and avaliacao_item[0].qtd_itens_validado >= 0:
            qtd_itens = avaliacao_item[0].qtd_itens_validado
        return qtd_itens

    def get_nota_pretendida(self, avaliador, validada=False):
        if validada:
            return self.get_qtd_itens(avaliador) * self.criterio.fator * self.criterio.diretriz.peso
        else:
            return self.qtd_itens * self.criterio.fator * self.criterio.diretriz.peso

    @property
    def tem_erro(self):
        """Indica se o item está incompleto/irregular (pendente para envio à CPPD)."""
        return (
            self.qtd_itens is None
            or self.data_referencia is None
            or not (self.descricao or '').strip()
            or self.criterio.fator is None
            or self.nota_pretendida is None
        )


class ArquivosExigidos(models.EncryptedPKModel):
    TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO = 1
    INICIO_EXERCIO_CARREIRA = 2
    CONCESSAO_ULTIMA_RT = 3

    TIPO_DOCUMENTO_EXIGIDO = [
        [TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO, 'Título de mestrado / especialização / graduação'],
        [INICIO_EXERCIO_CARREIRA, 'Início de exercício na carreira'],
        [CONCESSAO_ULTIMA_RT, 'Concessão da última RT'],
    ]

    processo = models.ForeignKeyPlus(
        'rsc.ProcessoRSC', blank=True, null=False, verbose_name='processo associado ao arquivo', on_delete=models.CASCADE
    )
    nome = models.CharFieldPlus(max_length=255)
    diretorio = models.CharFieldPlus(max_length=255, unique=True)
    tamanho = models.BigIntegerField()
    tipo = models.IntegerField(choices=TIPO_DOCUMENTO_EXIGIDO)

    objects = models.EncryptedPKModelManager()

    class Meta:
        verbose_name = 'Arquivo Exigido'
        verbose_name_plural = 'Arquivos Exigidos'

    def save(self, *args, **kwargs):
        # selecionando último registro
        ultimo_registro = ArquivosExigidos.objects.filter(processo=self.processo, tipo=self.tipo).order_by('-id')
        if ultimo_registro.exists():
            ultimo_registro = ultimo_registro[0]
            default_storage.delete(ultimo_registro.diretorio)

            # removendo último registro do banco
            ultimo_registro.delete()

        super(self.__class__, self).save(*args, **kwargs)


class Criterio(models.ModelPlus):
    STATUS_ATIVO = 0
    STATUS_INATIVO = 1

    STATUS_CHOICES = [[STATUS_ATIVO, 'Ativo'], [STATUS_INATIVO, 'Inativo']]

    diretriz = models.ForeignKeyPlus('rsc.Diretriz', blank=False, null=False, on_delete=models.CASCADE)
    numero = models.IntegerField(blank=False, null=False)
    nome = models.TextField(blank=False)
    status = models.IntegerField(choices=STATUS_CHOICES)
    fator = models.DecimalFieldPlus()
    unidade = models.ForeignKeyPlus('rsc.Unidade', blank=False, null=False, verbose_name='Unidade do critério', on_delete=models.CASCADE)
    teto = models.IntegerField('Valor máximo de itens do criterio', blank=False, null=False)
    categoria_memorial_descritivo = models.ForeignKeyPlus('rsc.CategoriaMemorialDescritivo', blank=False, null=False)

    class Meta:
        verbose_name = 'Critério'
        verbose_name_plural = 'Critérios'

    def __str__(self):
        return f'{self.nome} - {self.unidade}'

    def tem_arquivo_sem_descricao(self, processo):
        return self.arquivo_set.filter(processo=processo, descricao='').exists()


class Unidade(models.ModelPlus):
    nome = models.CharFieldPlus(max_length=255, unique=True)
    sigla = models.CharFieldPlus(max_length=50)

    class Meta:
        verbose_name = 'Unidade'
        verbose_name_plural = 'Unidades'

    def __str__(self):
        return f'{self.sigla}'


class TipoRsc(models.ModelPlus):
    nome = models.CharFieldPlus(max_length=255)
    categoria = models.CharFieldPlus(max_length=255)

    class Meta:
        verbose_name = 'Tipo de Rsc'
        verbose_name_plural = 'Tipos de Rsc'
        ordering = ('nome',)
        unique_together = ('nome', 'categoria')

    def __str__(self):
        return f'{self.nome} - {self.categoria}'


class CategoriaMemorialDescritivo(ModelPlus):
    nome = models.CharFieldPlus(max_length=255)

    class Meta:
        verbose_name = 'Categoria Memorial descritivo'
        verbose_name_plural = 'Categorias Memoriais Descritivos'
        ordering = ('nome',)

    def __str__(self):
        return f'{self.nome}'


class Diretriz(models.ModelPlus):
    tipo_rsc = models.ForeignKeyPlus('rsc.TipoRsc', blank=True, null=True, on_delete=models.CASCADE)
    nome = models.CharFieldPlus(max_length=255)
    descricao = models.TextField(blank=False)
    peso = models.IntegerField('Valor do peso', blank=False, null=False)
    teto = models.IntegerField('Teto', blank=False, null=False, help_text='Valor máximo de itens da diretriz ')

    class Meta:
        verbose_name = 'Diretriz'
        verbose_name_plural = 'Diretrizes'
        ordering = ('pk',)
        unique_together = ('tipo_rsc', 'nome')

    def __str__(self):
        return f'{self.nome}-{self.descricao}'


class ValidacaoCPPD(models.ModelPlus):
    ACAO_ACEITAR = 0
    ACAO_DEVOLVER = 1
    ACAO_REJEITAR = 2
    ACAO_CHOICES = [[ACAO_ACEITAR, 'Aceitar'], [ACAO_DEVOLVER, 'Devolver'], [ACAO_REJEITAR, 'Rejeitar']]

    TIPO_VALIDACAO_VALIDADO = 1
    TIPO_VALIDACAO_DATA_ERRADA = 2
    TIPO_VALIDACAO_DOCUMENTACAO_NAO_AUTENTICADA = 3
    TIPO_VALIDACAO_DOCUMENTACAO_NAO_CONDIZ_COM_EXIGIDO = 4
    TIPO_VALIDACAO_CHOICE = [
        [TIPO_VALIDACAO_VALIDADO, 'Validado'],
        [TIPO_VALIDACAO_DATA_ERRADA, 'Data errada'],
        [TIPO_VALIDACAO_DOCUMENTACAO_NAO_AUTENTICADA, 'Documentação não autenticada'],
        [TIPO_VALIDACAO_DOCUMENTACAO_NAO_CONDIZ_COM_EXIGIDO, 'Documentação não condiz com o exigido'],
    ]

    processo = models.ForeignKeyPlus('rsc.ProcessoRSC', blank=True, null=False, verbose_name='ProcessoRSC', on_delete=models.CASCADE)
    # titulacao
    data_conclusao_titulacao_rsc_pretendido_validada = models.DateFieldPlus('Data de Conclusão Validada', blank=False, null=True)
    titulacao_status = models.IntegerField('Situação da Titulação', choices=TIPO_VALIDACAO_CHOICE, blank=False, null=True)

    # exercicio na carreira
    data_exercio_carreira_validada = models.DateFieldPlus('Data de Exercício na Carreira Validada', blank=False, null=True)
    inicio_exercicio_status = models.IntegerField('Situação de Início na Carreira', choices=TIPO_VALIDACAO_CHOICE, blank=False, null=True)

    # concessão da última rt
    data_concessao_ultima_rt_validada = models.DateFieldPlus('Data de Concessão Validada', blank=False, null=True)
    ultima_concessao_rt_status = models.IntegerField('Situação da Última Concessão de RT', choices=TIPO_VALIDACAO_CHOICE, blank=False, null=True)

    # formulário de pontuação
    formulario_pontuacao_status = models.IntegerField('Situação do Formulário de Pontuação', blank=False, null=True)

    # situação do relatório descritivo
    relatorio_descritivo_status = models.IntegerField('Situação do Relatório Descritivo', blank=False, null=True)

    validador = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    acao = models.IntegerField(choices=ACAO_CHOICES)
    motivo_rejeicao = models.CharField('Motivo da rejeição', max_length=2000)
    data = models.DateTimeFieldPlus(auto_now_add=True, blank=True)
    ajustado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Validação CPPD'
        verbose_name_plural = 'Validações CPPD'

    def __str__(self):
        return f'Validação do processo {self.processo}'


class ProcessoAvaliador(models.ModelPlus):
    """
    status
    """

    EM_ESPERA = 0
    AGUARDANDO_ACEITE = 1
    EM_AVALIACAO = 2
    AVALIACAO_FINALIZADA = 3
    EXCEDEU_TEMPO_ACEITE = 4
    EXCEDEU_TEMPO_AVALIACAO = 5
    REJEITADO_PELO_AVALIADOR = 6

    STATUS_CHOICES = [
        [EM_ESPERA, 'Em espera'],
        [AGUARDANDO_ACEITE, 'Aguardando aceite'],
        [EM_AVALIACAO, 'Aguardando avaliação'],
        [AVALIACAO_FINALIZADA, 'Avaliação finalizada'],
        [EXCEDEU_TEMPO_ACEITE, 'Excedeu tempo de aceite'],
        [EXCEDEU_TEMPO_AVALIACAO, 'Excedeu tempo de avaliação'],
        [REJEITADO_PELO_AVALIADOR, 'Rejeitado pelo avaliador'],
    ]

    AVALIADOR_INTERNO = 'avaliador_interno'
    AVALIADOR_EXTERNO = 'avaliador_externo'
    TIPO_AVALIADOR_CHOICES = [[AVALIADOR_INTERNO, 'Avaliador Interno'], [AVALIADOR_EXTERNO, 'Avaliador Externo']]

    RELACIONADO_PROCESSO_ANALISE = 1
    DE_ORDER_PESSOAL = 2
    DE_ORDER_PROFISSIONAL = 3
    OUTROS = 4
    TIPO_RECUSA_CHOICES = [
        [RELACIONADO_PROCESSO_ANALISE, 'Relacionado ao Processo em Análise'],
        [DE_ORDER_PESSOAL, 'De Ordem Pessoal'],
        [DE_ORDER_PROFISSIONAL, 'De Ordem Profissional'],
        [OUTROS, 'Outros'],
    ]

    processo = models.ForeignKeyPlus('rsc.ProcessoRSC', blank=True, null=False, verbose_name='ProcessoRSC', on_delete=models.CASCADE)
    avaliador = models.ForeignKeyPlus(
        'rh.Avaliador', blank=True, null=True, verbose_name='Avaliador', related_name='processo_avaliador_rsc', on_delete=models.CASCADE
    )
    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True, blank=True)
    data_convite = models.DateTimeFieldPlus('Data do Convite', blank=True, null=True, default=None)
    data_aceite = models.DateTimeFieldPlus('Data do Aceite', blank=True, null=True, default=None)
    status = models.IntegerField('Situação do Avaliador no Processo', choices=STATUS_CHOICES)
    tipo_avaliador = models.CharFieldPlus(choices=TIPO_AVALIADOR_CHOICES)
    tipo_recusa = models.IntegerField(choices=TIPO_RECUSA_CHOICES, blank=True, null=True)
    motivo_recusa = models.CharField('Motivo da Recusa', max_length=2000, blank=True, null=True)
    responsavel_cadastro = models.ForeignKeyPlus(
        'comum.Vinculo', on_delete=models.CASCADE, null=True, blank=True, related_name='%(app_label)s_%(class)s_responsavel_cadastro'
    )

    class Meta:
        verbose_name = 'Avaliador do Processo'
        verbose_name_plural = 'Avaliadores do Processo'
        # unique_together = ('processo', 'avaliador')
        permissions = (
            ('pode_avaliar_processorsc', 'Pode avaliar ProcessoRSC'),
            ('pode_atualizar_dados_cadastrais', 'Pode atualizar dados cadastrais'),
        )

    def __str__(self):
        return f'{self.processo} - {self.avaliador}'

    def pode_aceitar_avaliacao(self):
        check_telefone = self.avaliador.vinculo.pessoa.pessoatelefone_set.all()
        return bool(
            check_telefone and self.avaliador.banco and self.avaliador.numero_agencia and self.avaliador.tipo_conta and self.avaliador.numero_conta
        )

    def aceitar(self):
        if self.pode_aceitar_avaliacao():
            self.status = self.EM_AVALIACAO
            self.data_aceite = datetime.date.today()
            self.processo.status = ProcessoRSC.STATUS_EM_AVALIACAO
            self.processo.save()
            self.save()

    @transaction.atomic
    def rejeitar(self, dados):
        # configuração
        config = ConfiguracaoRSC.objects.first()
        if config is None:
            raise Exception('Configuração de email não encontrada.')
        #
        if self.pode_aceitar_avaliacao():
            self.status = self.REJEITADO_PELO_AVALIADOR
            self.tipo_recusa = dados.get('tipo')
            self.motivo_recusa = dados.get('motivo_recusa')
            self.save()

            """
            selecionando avaliadores em espera
            """
            processos = ProcessoAvaliador.objects.filter(processo=self.processo, status=self.EM_ESPERA)
            if self.avaliador.eh_interno():
                processos = processos.filter(status=ProcessoAvaliador.EM_ESPERA, tipo_avaliador=ProcessoAvaliador.AVALIADOR_INTERNO)
            if self.avaliador.eh_externo():
                processos = processos.filter(status=ProcessoAvaliador.EM_ESPERA, tipo_avaliador=ProcessoAvaliador.AVALIADOR_EXTERNO)

            if processos:
                """
                pegando o primeiro registro em espera para setar o status para "AGUARDANDO ACEITE"
                """
                processo = processos[0]
                processo.status = ProcessoAvaliador.AGUARDANDO_ACEITE
                processo.data_convite = datetime.datetime.today()
                processo.save()

                """
                enviando e-mail para o avaliador selecionado
                """
                dados = {
                    'NOME_AVALIADOR': str(processo.avaliador.vinculo.user.get_profile().nome),
                    'NOME_PROFESSOR_AVALIADO': str(processo.processo.servidor.pessoa_fisica.nome),
                    'DATA_LIMITE_ACEITE_AVALIACAO': str(processo.data_limite()),
                    'DIAS_PARA_AVALIACAO': config.dias_para_avaliacao,
                    'SITE_URL': settings.SITE_URL,
                }
                assunto = '[SUAP] Avaliação de Processo RSC'
                mensagem = utils.substituir_marcacoes(config.email_professor_sorteado, dados)
                send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [processo.avaliador.email_contato])

            else:
                """
                enviando e-mail para a CPPD informando que não há mais avaliadores reservas para este processo
                """
                dados = {
                    'PROCESSO_RSC': str(self.processo),
                    'SITE_URL': settings.SITE_URL,
                }
                assunto = '[SUAP] Processo RSC sem Avaliador Reserva'
                mensagem = utils.substituir_marcacoes(config.email_sem_avaliador_reserva, dados)
                email_cppd = Configuracao.get_valor_por_chave('rsc', 'email_cppd')
                if email_cppd:
                    send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [email_cppd])

    def data_limite(self):
        # configuração
        config = ConfiguracaoRSC.objects.first()
        if config is None:
            raise Exception('Configuração de email não encontrada.')
        #
        nova_data = self.data_convite
        dias = config.dias_para_aceite

        if self.data_aceite:
            nova_data = self.data_aceite
            dias = config.dias_para_avaliacao

        falta_dias = True
        cont = 0
        while falta_dias:
            cont = cont + 1
            nova_data = nova_data + datetime.timedelta(days=1)
            if nova_data.weekday() == 5 or nova_data.weekday() == 6:
                nova_data = nova_data + datetime.timedelta(days=1)
                cont = cont - 1
            if cont == dias:
                falta_dias = False

        return nova_data.strftime('%d/%m/%Y')

    def data_limite_display(self):
        if self.status == self.AVALIACAO_FINALIZADA:
            str_data_limite = '-'
        else:
            str_data_limite = f'<span class="negrito">Data limite para aceite: </span>{self.data_limite()}'
            if self.data_aceite:
                str_data_limite = f'<span class="negrito">Data limite término da avaliação: </span>{self.data_limite()}'
        return str_data_limite

    def situacao_avaliador(self):
        situacao = ''
        if self.status in [
            self.EM_ESPERA,
            self.AGUARDANDO_ACEITE,
            self.REJEITADO_PELO_AVALIADOR,
            self.EXCEDEU_TEMPO_ACEITE,
            self.EXCEDEU_TEMPO_AVALIACAO,
        ]:
            if self.status == self.EM_ESPERA:
                css = 'alert'
            elif self.status == self.AGUARDANDO_ACEITE:
                css = 'info'
            else:
                css = 'error'
            situacao = f'<span class="status status-{css}">{self.get_status_display()}</span>'
        elif self.status == self.EM_AVALIACAO or self.status == self.AVALIACAO_FINALIZADA:
            situacao = f'<div class="progress"><p>{self.calcula_porcentagem_avaliacao()}</p></div>'

        return situacao

    def calcula_porcentagem_avaliacao(self):
        avaliacao = Avaliacao.objects.filter(processo=self.processo, avaliador=self.avaliador).first()
        porcentagem = 0
        if avaliacao:
            qtd_total_itens_zerados = avaliacao.avaliacaoitem_set.filter(qtd_itens_validado__lte=0).count()
            qtd_total_itens = avaliacao.avaliacaoitem_set.all().count() * 2
            qtd_itens_preenchidos = (
                avaliacao.avaliacaoitem_set.filter(data_referencia__isnull=False).count()
                + avaliacao.avaliacaoitem_set.filter(qtd_itens_validado__isnull=False).count()
            )
            porcentagem = 100 * qtd_itens_preenchidos / (qtd_total_itens - qtd_total_itens_zerados)

        if int(porcentagem) >= 100:
            porcentagem = 100
        return f'{int(porcentagem)}%'

    def avaliador_excluido_processo(self):
        retorno = None
        if self.status == self.EXCEDEU_TEMPO_ACEITE or self.status == self.EXCEDEU_TEMPO_AVALIACAO or self.status == self.REJEITADO_PELO_AVALIADOR:
            retorno = True
        return retorno

    def avaliador_principal(self):
        retorno = None
        if self.status == self.AGUARDANDO_ACEITE or self.status == self.EM_AVALIACAO or self.status == self.AVALIACAO_FINALIZADA:
            retorno = True
        return retorno

    def avaliador_reserva(self):
        retorno = None
        if self.status == self.EM_ESPERA:
            retorno = True
        return retorno

    def avaliacao_correspondente(self):
        qs_avaliacao = Avaliacao.objects.filter(processo=self.processo, avaliador=self.avaliador)
        if qs_avaliacao.exists():
            return qs_avaliacao[0]
        return None

    def pode_reenviar_email(self) -> bool:
        if self.status == self.AGUARDANDO_ACEITE:
            return True
        if self.status == self.EM_AVALIACAO:
            return not Avaliacao.objects.filter(processo=self.processo, avaliador=self.avaliador, status=Avaliacao.EM_AVALIACAO).exists()
        return False

    def reenviar_email(self) -> str:
        config = ConfiguracaoRSC.objects.first()
        if config is None:
            raise Exception('Configuração de email não encontrada.')
        if not self.pode_reenviar_email():
            raise Exception('Não é possível reenviar e-mail para esta situação.')

        if self.status == self.AGUARDANDO_ACEITE:
            template = config.email_professor_sorteado
        else:  # EM_AVALIACAO sem avaliação iniciada
            template = config.email_lembrete_avaliacao

        if template is None:
            raise Exception('Template de e-mail não configurado.')

        dados = {
            'NOME_AVALIADOR': str(self.avaliador.vinculo.user.get_profile().nome),
            'NOME_PROFESSOR_AVALIADO': str(self.processo.servidor.pessoa_fisica.nome),
            'DATA_LIMITE_ACEITE_AVALIACAO': str(self.data_limite()),
            'DIAS_PARA_AVALIACAO': config.dias_para_avaliacao,
            'SITE_URL': settings.SITE_URL,
        }
        assunto = '[SUAP] Avaliação de Processo RSC'
        mensagem = utils.substituir_marcacoes(template, dados)
        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [self.avaliador.vinculo], so_notificar=True)
        send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [self.avaliador.email_contato])
        return self.avaliador.email_contato


class Avaliacao(models.ModelPlus):
    EM_AVALIACAO = 0
    DEFERIDA = 1
    INDEFERIDA = 2
    INTERROMPIDA = 3
    DESISTENCIA = 4

    STATUS_CHOICES = [
        [EM_AVALIACAO, 'Em Avaliação'],
        [DEFERIDA, 'Deferida'],
        [INDEFERIDA, 'Indeferida'],
        [INTERROMPIDA, 'Interrompida'],
        [DESISTENCIA, 'Desistência'],
    ]

    RELACIONADO_PROCESSO_ANALISE = 1
    DE_ORDER_PESSOAL = 2
    DE_ORDER_PROFISSIONAL = 3
    OUTROS = 4
    TIPO_DESISTENCIA_CHOICES = [
        [RELACIONADO_PROCESSO_ANALISE, 'Relacionado ao Processo em Análise'],
        [DE_ORDER_PESSOAL, 'De Ordem Pessoal'],
        [DE_ORDER_PROFISSIONAL, 'De Ordem Profissional'],
        [OUTROS, 'Outros'],
    ]

    AVALIADOR_INTERNO = 'avaliador_interno'
    AVALIADOR_EXTERNO = 'avaliador_externo'
    TIPO_AVALIADOR_CHOICES = [[AVALIADOR_INTERNO, 'Avaliador Interno'], [AVALIADOR_EXTERNO, 'Avaliador Externo']]

    status = models.IntegerField('Situação da Avaliação', choices=STATUS_CHOICES)
    processo = models.ForeignKeyPlus('rsc.ProcessoRSC', blank=True, null=False, verbose_name='ProcessoRSC', on_delete=models.CASCADE)
    avaliador = models.ForeignKeyPlus(
        'rh.Avaliador', blank=True, null=False, verbose_name='Avaliador', related_name='avaliacao_avaliador_rsc', on_delete=models.CASCADE
    )
    motivo_indeferimento = models.CharField('Motivo do Indeferimento', max_length=2000)
    tipo_desistencia = models.IntegerField(choices=TIPO_DESISTENCIA_CHOICES, blank=True, null=True)
    motivo_desistencia = models.CharField('Motivo da Desistência', max_length=2000, blank=True, null=True)
    data_finalizacao = models.DateTimeFieldPlus('Data da Finalização da Avaliação', blank=True, null=True, default=None)
    avaliacao_paga = models.BooleanField(default=False)
    data_pagamento = models.DateTimeFieldPlus('Data do Pagamento', blank=True, null=True, default=None)
    tipo_avaliador = models.CharFieldPlus(choices=TIPO_AVALIADOR_CHOICES, null=True)

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'

    def avaliacao_finalizada(self):
        retorno = False
        if self.status in [self.DEFERIDA, self.INDEFERIDA]:
            retorno = True
        return retorno

    def pode_avaliar(self):
        retorno = False
        if self.status == self.EM_AVALIACAO:
            retorno = True
        return retorno

    def desistir_avaliacao(self, dados):
        self.status = self.DESISTENCIA
        self.tipo_desistencia = dados.get('tipo')
        self.motivo_desistencia = dados.get('justificativa')
        self.save()

        """
        selecionando o processo avaliador
        """
        processoavaliador = ProcessoAvaliador.objects.filter(processo=self.processo, avaliador=self.avaliador)
        if processoavaliador:
            processoavaliador = processoavaliador[0]
            dados_rejeitar = {}
            dados_rejeitar['tipo'] = dados.get('tipo')
            dados_rejeitar['motivo_recusa'] = dados.get('justificativa')
            processoavaliador.rejeitar(dados_rejeitar)

    def finalizar_avaliacao(self):
        ## configuração
        config = ConfiguracaoRSC.objects.first()
        if not config:
            raise Exception('Configuração de email não encontrada.')
        #
        avaliacao = self
        itens_avaliacao = avaliacao.avaliacaoitem_set.all()
        avaliacao.status = self.DEFERIDA
        avaliacao.data_finalizacao = datetime.date.today()
        """
        verificando se todos os itens já foram preenchidos
        """
        for item in itens_avaliacao:
            if item.qtd_itens_validado and item.qtd_itens_validado < 0:
                raise Exception('Não é permitido quantidade de items negativo. Por favor, corrija e tente finalizar novamente.')

            if (not item.data_referencia and item.qtd_itens_validado is not None and item.qtd_itens_validado > 0) or item.qtd_itens_validado is None:
                raise Exception('Você não pode finalizar a avaliação sem avaliar todos os quesitos de todos os itens.')

        """
        verificando se a avaliação será deferida ou indeferida
        """
        arquivos_rsc_pretendido = self.processo.get_arquivos_rsc_pretendido()
        pontos_diretriz = {}
        id_arquivos_utilizados_rsc_pretendida = []

        """
        verificando se o requerente tem os 25 pontos na rsc pretendida
        """
        for arquivo in arquivos_rsc_pretendido:
            """
            somando valores por diretriz para verificação posterior do teto
            """
            if arquivo.criterio.diretriz_id in pontos_diretriz:
                pontos_diretriz[arquivo.criterio.diretriz_id] += arquivo.get_nota_pretendida(self.avaliador, True)
            else:
                pontos_diretriz[arquivo.criterio.diretriz_id] = arquivo.get_nota_pretendida(self.avaliador, True)

            if pontos_diretriz[arquivo.criterio.diretriz_id] > arquivo.criterio.diretriz.teto:
                pontos_diretriz[arquivo.criterio.diretriz_id] = arquivo.criterio.diretriz.teto

            pontos = sum(pontos_diretriz.values())
            id_arquivos_utilizados_rsc_pretendida.append(arquivo.id)

        if pontos < config.pontos_rsc_pretendido:
            avaliacao.status = self.INDEFERIDA
            avaliacao.motivo_indeferimento = 'A avaliação fez com que o processo não atingisse a pontuação mínima necessária no RSC pretendido.'
        else:
            """
            verificando se o requerente tem os 50 pontos na soma das rsc's
            """
            arquivos_restantes = self.processo.arquivo_set.all().exclude(pk__in=id_arquivos_utilizados_rsc_pretendida).order_by('data_referencia')
            for arquivo in arquivos_restantes:
                """
                somando valores por diretriz para verificação posterior do teto
                """
                if arquivo.criterio.diretriz_id in pontos_diretriz:
                    pontos_diretriz[arquivo.criterio.diretriz_id] += arquivo.get_nota_pretendida(self.avaliador, True)
                else:
                    pontos_diretriz[arquivo.criterio.diretriz_id] = arquivo.get_nota_pretendida(self.avaliador, True)

                if pontos_diretriz[arquivo.criterio.diretriz_id] > arquivo.criterio.diretriz.teto:
                    pontos_diretriz[arquivo.criterio.diretriz_id] = arquivo.criterio.diretriz.teto

            pontos = sum(pontos_diretriz.values())
            if pontos < config.pontos_soma_rsc:
                avaliacao.status = self.INDEFERIDA
                avaliacao.motivo_indeferimento = (
                    'A avaliação fez com que o processo não atingisse a pontuação mínima necessária na soma do RSC-I, RSC-II e RSC-III.'
                )

        avaliacao.save()

        """
        finalizando processo avaliador
        """
        processo_avaliador = ProcessoAvaliador.objects.filter(
            processo=avaliacao.processo, avaliador=avaliacao.avaliador, status=ProcessoAvaliador.EM_AVALIACAO
        )
        if processo_avaliador:
            processo_avaliador = processo_avaliador[0]
            processo_avaliador.status = ProcessoAvaliador.AVALIACAO_FINALIZADA
            processo_avaliador.save()

        """
        verificando se é a terceira avaliação do processo
        """
        finalizadas = Avaliacao.objects.filter(processo=avaliacao.processo, status__in=[Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA]).count()
        if finalizadas >= 3:
            processo = avaliacao.processo
            processo.status = ProcessoRSC.STATUS_AGUARDANDO_CIENCIA
            processo.pontuacao_validada_com_corte = processo._calculo_pontos([Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA], True)
            processo.pontuacao_validada_sem_corte = processo._calculo_pontos([Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA], False)
            processo.save()

            # verificando se o interessado é falecido
            if processo.interessado_falecido():
                processo.dar_ciencia_resultado(1, 1)  # neste caso, a ciencia é data concordando com a pontuação e data de referência validada


class AvaliacaoItem(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus('rsc.Avaliacao', blank=True, null=False, verbose_name='Avaliação', on_delete=models.CASCADE)
    arquivo = models.ForeignKeyPlus('rsc.Arquivo', blank=True, null=False, verbose_name='Arquivo', on_delete=models.CASCADE)
    data_referencia = models.DateField('Data de Referência Validada', blank=True, null=True)
    qtd_itens_validado = models.IntegerField('Quantidade de Itens Validados', blank=True, null=True)
    justificativa = models.CharField('Justificativa da Avaliação', max_length=2000, blank=True, null=True)

    class Meta:
        verbose_name = 'Avaliação do Item'
        verbose_name_plural = 'Avaliações dos Itens'

    """
    método que informa se houve alteração na data de referência ou quantidade de itens na avaliação
    """

    def houve_alteracao_avaliacao(self):
        retorno = False
        if self.data_referencia and self.data_referencia != self.arquivo.data_referencia:
            retorno = True
        if self.qtd_itens_validado and int(self.qtd_itens_validado) != self.arquivo.qtd_itens:
            retorno = True
        return retorno

    """
    método que informa se o item foi avaliado
    """

    def item_validado(self):
        validado = False
        if self.qtd_itens_validado is not None and self.qtd_itens_validado >= 0:
            if (self.qtd_itens_validado > 0 and self.data_referencia) or (self.qtd_itens_validado == 0):
                validado = True
        return validado

    """
    Método que retorna a pontuação validada pelo avaliador
    """

    def pontuacao_validada(self):
        if self.qtd_itens_validado and self.qtd_itens_validado > 0:
            return self.arquivo.get_nota_pretendida(self.avaliacao.avaliador, True)
        else:
            return None


class ParametroPagamento(models.ModelPlus):
    valor_por_avaliacao = models.FloatField('Valor por Avaliação', null=False, blank=False)
    hora_por_avaliacao = models.IntegerField('Hora por Avaliação', null=False, blank=False)
    data_cadastro = models.DateField('Data de Cadastro', auto_now_add=True, blank=False, null=False)

    class Meta:
        verbose_name = 'Parâmetro para Pagamento'
        verbose_name_plural = 'Parâmetros para Pagamentos'


class CloneArquivoErro(models.ModelPlus):
    ARQUIVO_EXIGIDO = 1
    ARQUIVO = 2
    TIPO_ARQUIVO_CHOICES = [[ARQUIVO_EXIGIDO, 'Arquivo Exigido'], [ARQUIVO, 'Arquivo']]

    tipo_arquivo = models.IntegerFieldPlus('Tipo de Arquivo', choices=TIPO_ARQUIVO_CHOICES)
    nome_arquivo = models.CharFieldPlus('Arquivo')
    processo_rsc = models.ForeignKeyPlus('rsc.ProcessoRSC', on_delete=models.CASCADE)

    # quando arquivos exigidos
    tipo_documento_exigido = models.CharFieldPlus('Tipo de Documento Exigido', null=True, blank=True)

    # quando arquivos comuns
    criterio = models.ForeignKeyPlus('rsc.Criterio', blank=True, null=True, verbose_name='Critério', on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'Arquivo com problema na clonagem'
        verbose_name_plural = 'Arquivos com problema na clonagem'

    def __str__(self):
        return self.nome_arquivo

    def get_localizacao(self):
        if self.tipo_arquivo == self.ARQUIVO_EXIGIDO:
            return self.tipo_documento_exigido
        else:
            return f'{self.criterio.diretriz.tipo_rsc} >> {self.criterio.diretriz} >> {self.criterio}'


class ConfiguracaoRSC(models.ModelPlus):
    descricao = models.CharFieldPlus(max_length=500, unique=True, verbose_name='Descrição')
    # Campos de configuração
    dias_para_aceite = models.PositiveIntegerFieldPlus(
        verbose_name='Tempo para aceite de avaliação', help_text='Tempo em dias', null=True, blank=False
    )
    dias_para_avaliacao = models.PositiveIntegerFieldPlus(
        verbose_name='Tempo para realizar a avaliação', help_text='Tempo em dias', null=True, blank=False
    )
    pontos_soma_rsc = models.PositiveIntegerFieldPlus(
        verbose_name='Pontuação mínima na soma dos RSCs', help_text='Pontuação mínima nos três RSCs (RSC-I, RSC-II e RSC-III)', null=True, blank=False
    )
    pontos_rsc_pretendido = models.PositiveIntegerFieldPlus(
        verbose_name='Pontuação mínima no RSC pretendido', help_text='Pontuação mínima no RSC pretendido', null=True, blank=False
    )

    #
    # textos
    email_professor_sorteado = HTMLField(
        verbose_name='E-mail para o professor sorteado',
        help_text='Texto que será enviado para o professor sorteado.',
        max_length=5000,
        null=True,
        blank=False,
    )
    email_sem_avaliador_reserva = HTMLField(
        verbose_name='Texto para o e-mail sem avaliador reserva',
        help_text='Texto que será enviado para a CPPD quando não houver avaliador reserva.',
        max_length=5000,
        null=True,
        blank=False,
    )
    email_professor_perdeu_prazo = HTMLField(
        verbose_name='Texto para o e-mail do professor que perdeu o prazo',
        help_text='Texto que será enviado para o professor quando perder o prazo.',
        max_length=5000,
        null=True,
        blank=False,
    )
    instrucoes_gerais = HTMLField(
        verbose_name='Texto de instruções gerais - Avaliado',
        help_text='Instruções gerais para o professor avalaidor no processo de RSC.',
        max_length=10000,
        null=True,
        blank=False,
    )
    instrucoes_gerais_avaliador = HTMLField(
        verbose_name='Texto de instruções gerais - Avaliador',
        help_text='Instruções gerais para o processo de RSC.',
        max_length=10000,
        null=True,
        blank=False,
    )
    email_lembrete_avaliacao = HTMLField(
        verbose_name='Texto para o e-mail de lembrete de avaliação',
        help_text='Texto enviado ao avaliador que aceitou mas ainda não iniciou a avaliação.',
        max_length=5000,
        null=True,
        blank=False,
    )

    class Meta:
        verbose_name = 'Configuração RSC'
        verbose_name_plural = 'Configurações RSC'

    def __str__(self):
        return self.descricao
