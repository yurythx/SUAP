import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.db.models.aggregates import Sum
from django.utils.html import format_html

from comum.models import Configuracao
from djtools.db import models
from djtools.templatetags.filters import format_datetime, in_group
from licenca_capacitacao.utils import eh_servidor, get_e
from rh.models import AfastamentoSiape, Servidor, ServidorAfastamento


class LicCapacitacaoPorDia(models.ModelPlus):
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano')
    mes = models.IntegerField(verbose_name='Mês')
    dia = models.IntegerField(verbose_name='Dia')
    data = models.DateFieldPlus('Data', null=True, blank=True)

    # ----------------------------------
    # SIAPE
    qtd_docentes = models.IntegerField(verbose_name='Docente', default=0)
    qtd_taes = models.IntegerField(verbose_name='Técnico-administrativo', default=0)
    qtd_total = models.IntegerField(verbose_name='Total', default=0)
    #
    # SUAP - Conta quantos pedidos foram aprovados de forma definitiva
    #   mas que ainda nao constam no SIAPE
    qtd_docentes_suap = models.IntegerField(verbose_name='Docente', default=0)
    qtd_taes_suap = models.IntegerField(verbose_name='Técnico-administrativo', default=0)
    qtd_total_suap = models.IntegerField(verbose_name='Total', default=0)
    #
    # Total Geral (SIAPE + SUAP)
    qtd_docentes_geral = models.IntegerField(verbose_name='Docente', default=0)
    qtd_taes_geral = models.IntegerField(verbose_name='Técnico-administrativo', default=0)
    qtd_total_geral = models.IntegerField(verbose_name='Total', default=0)
    # ----------------------------------

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Licença capacitação por dia'
        verbose_name_plural = 'Licenças capacitação por dia'
        unique_together = ('ano', 'mes', 'dia')

    def __str__(self):
        return f'{self.ano} - {self.mes} - {self.dia}'


class EditalLicCapacitacao(models.ModelPlus):
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano')
    titulo = models.CharFieldPlus('Título', max_length=255)
    descricao = models.TextField('Descrição')

    ativo = models.BooleanField('Ativo', default=False)

    # ----------------------
    # Configuracoes gerais da submissao
    # ----------------------
    periodo_abrangencia_inicio = models.DateFieldPlus('Início do período de abragência do edital', null=True, blank=True)
    periodo_abrangencia_final = models.DateFieldPlus('Final do período de abragência do edital', null=True, blank=True)

    # ----------------------
    # Calendario
    # ----------------------
    # - Primeira Etapa de submissão
    # -------------
    periodo_submissao_inscricao_inicio = models.DateTimeFieldPlus('Início das submissões', null=True, blank=True)
    periodo_submissao_inscricao_final = models.DateTimeFieldPlus('Final das submissões', null=True, blank=True)
    #
    periodo_resultado_parcial_inicio = models.DateTimeFieldPlus('Início da publicação do resultado parcial', null=True, blank=True)
    periodo_resultado_parcial_final = models.DateTimeFieldPlus('Final da publicação do resultado parcial', null=True, blank=True)
    #
    periodo_recurso_resultado_parcial_inicio = models.DateTimeFieldPlus('Início dos recursos do resultado parcial', null=True, blank=True)
    periodo_recurso_resultado_parcial_final = models.DateTimeFieldPlus('Final dos recursos do resultado parcial', null=True, blank=True)
    #
    periodo_desistencia_inicio = models.DateTimeFieldPlus('Início das desistências', null=True, blank=True)
    periodo_desistencia_final = models.DateTimeFieldPlus('Final das desistências', null=True, blank=True)
    #
    periodo_resultado_final_inicio = models.DateTimeFieldPlus('Início da publicação do resultado final', null=True, blank=True)
    periodo_resultado_final_final = models.DateTimeFieldPlus('Final da publicação do resultado final', null=True, blank=True)

    # - Segunda Etapa de submissão
    # -------------
    periodo_submissao_segunda_etapa_inicio = models.DateTimeFieldPlus('Início da submissão dos dados finais', null=True, blank=True)
    periodo_submissao_segunda_etapa_final = models.DateTimeFieldPlus('Final da submissão dos dados finais', null=True, blank=True)

    # Parametros do edital
    # ---------------------------------
    qtd_max_periodos_por_pedido = models.PositiveIntegerField('Quantidade de máxima de parcelas em um pedido', default=1)
    # Servidores em exercicio
    total_taes_em_exercicio = models.PositiveIntegerField('Total de Taes em Exercício', default=0)
    total_docentes_em_exercicio = models.PositiveIntegerField('Total de Docentes em Exercício', default=0)
    total_geral_em_exercicio = models.PositiveIntegerField('Total de Geral em Exercício', default=0)
    #
    # Qtd limite de periodos que podem ser solicitados para cada pedido
    percentual_limite_servidores_em_lic_capacitacao = models.DecimalFieldPlus(
        'Percentual limite de servidores em licença capacitação', decimal_places=2, max_digits=6, default=5
    )
    #
    # Qtd max de servidores com lic capac deferida em definitivo
    qtd_limite_servidores_em_lic_capacitacao_por_dia = models.PositiveIntegerField(
        'Quantidade limite de servidores em licença capacitação por dia', default=0
    )
    qtd_limite_taes_em_lic_capacitacao_por_dia = models.PositiveIntegerField(
        'Quantidade limite de técnicos administrativos em licença capacitação por dia', default=0
    )
    qtd_limite_docentes_em_lic_capacitacao_por_dia = models.PositiveIntegerField(
        'Quantidade limite de docentes em licença capacitação por dia', default=0
    )
    #
    processamento_externo = models.BooleanField('Este edital terá seu resultado (parcial e final) processado em estrutura externa.', default=False)
    bloqueia_pedido_servidor_nao_apto = models.BooleanField('Bloquear pedido de servidor em Não Efetivo Exercício.', default=False)
    #

    # codigos_afastamento = models.ManyToManyFieldPlus('rh.AfastamentoSiape', verbose_name='Códigos de Afastamento Capacitação', blank=True)
    # codigos_afastamento_nao_conta_como_efet_exerc = models.ManyToManyFieldPlus('rh.AfastamentoSiape', verbose_name='Códigos dos afastamentos que não contabilizam como efetivo exercício', blank=True)

    # situacoes_servidores_efetivo_exercicio = models.ManyToManyFieldPlus('rh.Situacao', verbose_name='Situações que contabilizam como efetivo exercício', blank=True)

    class Meta:
        verbose_name = 'Edital de Licença para Capacitação'
        verbose_name_plural = 'Editais de Licença para Capacitação'
        ordering = ['-id']

    def __str__(self):
        if self.periodo_abrangencia_inicio:
            return f'{self.titulo}. Abrangência de {format_datetime(self.periodo_abrangencia_inicio)} até {format_datetime(self.periodo_abrangencia_final)}'
        else:
            return f'{self.titulo}'

    def clean(self):
        datas_iniciais = self.get_datas_iniciais()
        datas_finais = self.get_datas_finais()
        for i in range(len(datas_iniciais)):
            if datas_iniciais[i] or datas_finais[i]:
                # Necessário preencher as duas datas
                if not (datas_iniciais[i] and datas_finais[i]):
                    raise ValidationError('É necessário preencher todas as datas de iniciais e finais.')
                # A data inicial tem que ser menor/igual a data final
                if not (datas_iniciais[i] <= datas_finais[i]):
                    raise ValidationError('A data inicial deve ser menor ou igual a data final.')
        if self.ativo:
            for i in range(len(datas_iniciais)):
                if not datas_iniciais[i] and not datas_finais[i]:
                    raise ValidationError('É necessário preencher todas as datas de iniciais e finais para ativar o edital.')
        if self.qtd_max_periodos_por_pedido < 1:
            raise ValidationError('A quantidade máxima de parcelas por pedido deve ser ao menos 1.')
        if self.id and self.processamento_externo:
            if EditalLicCapacitacao.existe_algum_processamento_nao_cancelado_no_edital(self):
                raise ValidationError(
                    'O edital só pode ser configurado para processamento externo se não existirem processamentos cadastrados para este edital.'
                )

    """
    2.5. IFRN estabelecerá, com base em seu planejamento estratégico, quantitativo máximo de
    servidores que usufruirão a licença para capacitação simultaneamente, e o quantitativo
    não poderá ser superior a 2 (dois) por cento dos servidores em exercício no IFRN e
    eventual resultado fracionário será arredondado para o número inteiro imediatamente
    superior.
    2.5.1. O percentual de 2% será dividido proporcionalmente pelo número de servidores das
    duas carreiras (EBTT e TAE), e eventual resultado fracionário será arredondado para o
    número inteiro imediatamente superior, para o caso da carreira dos TAE.
    """

    def get_percentual_limite_servidores_em_lic_capacitacao(self):
        if self.percentual_limite_servidores_em_lic_capacitacao:
            return self.percentual_limite_servidores_em_lic_capacitacao / 100
        return 0

    @staticmethod
    def get_situacoes_servidores_efetivo_exercicio():
        # - Verificar se a contagem da base de servidores em exercício no IFRN e
        #   stá seguindo as situações indicadas abaixo:
        #
        # SITUAÇÃO DO SERVIDOR
        #
        # ATIVO PERMANENTE - 01............... Incluído
        # APOSENTADO - 02.............................. Exceto
        # ESTAGIARIO - 66................................... Exceto
        # CONT.PROF.SUBSTITUTO - 52....... Exceto
        # FUNCAO PROVIS.-EX-TE - 70.......... Exceto
        # CEDIDO/REQUISITADO - 03........... Incluído
        # CONTR.PROF.VISITANTE - 53......... Exceto
        # ATIVO EM OUTRO ORGAO - 08..... Exceto
        # EXCEDENTE A LOTACAO - 11......... Incluído
        # EXERCICIO PROVISORIO - 19,,,,,,,, Incluído
        # EXERC DESCENT CARREI - 18........ Incluído
        # COLAB PCCTAE E MAGIS - 41........ Incluído
        # COLABORADOR ICT - 42.................. Incluído
        """
        ATIVO_PERMANENTE = '01'
        REQUISITADO = '03'
        EXCEDENTE_A_LOTACAO = '11'
        EXERCICIO_PROVISORIO = '19'
        EXERC_DESCENT_CARREI = '18'
        COLABORADOR_PCCTAE = '41'
        COLABORADOR_ICT = '42'

        SITUACOES_EM_EXERCICIO = [
            ATIVO_PERMANENTE,
            REQUISITADO,
            EXCEDENTE_A_LOTACAO,
            EXERCICIO_PROVISORIO,
            EXERC_DESCENT_CARREI,
            COLABORADOR_PCCTAE,
            COLABORADOR_ICT,
        ]
        """

        codigos = list(SituacaoContabilizaExercicio.objects.all().values_list('codigo__codigo', flat=True))

        return codigos

    @staticmethod
    def get_taes_efetivo_exercicio():
        return Servidor.objects.filter(
            ativo=True, situacao__codigo__in=EditalLicCapacitacao.get_situacoes_servidores_efetivo_exercicio(), eh_tecnico_administrativo=True
        )

    @staticmethod
    def get_docentes_efetivo_exercicio():
        return Servidor.objects.filter(
            ativo=True, situacao__codigo__in=EditalLicCapacitacao.get_situacoes_servidores_efetivo_exercicio(), eh_docente=True
        )

    @staticmethod
    def get_servidores_efetivo_exercicio():
        return EditalLicCapacitacao.get_taes_efetivo_exercicio() | EditalLicCapacitacao.get_docentes_efetivo_exercicio()

    @staticmethod
    @transaction.atomic()
    def calcular_parametros(edital):
        # total_taes_em_exercicio = Servidor.objects.filter(ativo=True, eh_tecnico_administrativo=True, situacao__codigo__in=SITUACOES_EM_EXERCICIO).only('id').count()
        total_taes_em_exercicio = EditalLicCapacitacao.get_taes_efetivo_exercicio().only('id').count()
        total_taes_em_exercicio += ServidorComplementar.objects.filter(edital=edital, categoria='tecnico_administrativo').count()

        # total_docentes_em_exercicio = Servidor.objects.filter(ativo=True, eh_docente=True, situacao__codigo__in=SITUACOES_EM_EXERCICIO).only('id').count()
        total_docentes_em_exercicio = EditalLicCapacitacao.get_docentes_efetivo_exercicio().only('id').count()
        total_docentes_em_exercicio += ServidorComplementar.objects.filter(edital=edital, categoria='docente').count()

        total_geral_em_exercicio = total_taes_em_exercicio + total_docentes_em_exercicio

        perc_padrao = edital.get_percentual_limite_servidores_em_lic_capacitacao()
        qtd_limite_taes_em_lic_capacitacao_por_dia = round(total_taes_em_exercicio * perc_padrao)
        qtd_limite_docentes_em_lic_capacitacao_por_dia = round(total_docentes_em_exercicio * perc_padrao)
        qtd_limite_servidores_em_lic_capacitacao_por_dia = round(total_geral_em_exercicio * perc_padrao)

        edital.total_taes_em_exercicio = total_taes_em_exercicio
        edital.total_docentes_em_exercicio = total_docentes_em_exercicio
        edital.total_geral_em_exercicio = total_geral_em_exercicio
        edital.qtd_limite_taes_em_lic_capacitacao_por_dia = qtd_limite_taes_em_lic_capacitacao_por_dia
        edital.qtd_limite_docentes_em_lic_capacitacao_por_dia = qtd_limite_docentes_em_lic_capacitacao_por_dia
        edital.qtd_limite_servidores_em_lic_capacitacao_por_dia = qtd_limite_servidores_em_lic_capacitacao_por_dia

        edital.save()

    def get_datas_iniciais(self):
        datas_iniciais = [
            self.periodo_abrangencia_inicio,
            self.periodo_submissao_inscricao_inicio,
            self.periodo_resultado_parcial_inicio,
            self.periodo_recurso_resultado_parcial_inicio,
            self.periodo_desistencia_inicio,
            self.periodo_resultado_final_inicio,
            self.periodo_submissao_segunda_etapa_inicio,
        ]
        return datas_iniciais

    def get_datas_finais(self):
        datas_finais = [
            self.periodo_abrangencia_final,
            self.periodo_submissao_inscricao_final,
            self.periodo_resultado_parcial_final,
            self.periodo_recurso_resultado_parcial_final,
            self.periodo_desistencia_final,
            self.periodo_resultado_final_final,
            self.periodo_submissao_segunda_etapa_final,
        ]
        return datas_finais

    # ------------------------------------------------------------------------------
    # STATUS DE ACORDO COM O CALENDÁRIO
    # ------------------------------------------------------------------------------
    # - EM ABERTO ANTES DO PERÍODO DE SUBMISSÃO:
    #   - Quando edital estah ativo
    #   - Quando nao esta no no periodo de submissao
    # - EM ABERTO:
    #   - Quando edital estah ativo
    #   - Quando esta no periodo de submissao
    # - EM_ANDAMENTO:
    #   - Quando edital estah ativo
    #   - Quando já passou o período de submissão
    #   - Não aceita mais submissões
    #   - Ainda não foi finalizado (ainda pode ter resultado parcial/final)
    # - FINALIZADO:
    #   - Quando edital estah ativo
    #   - Quando todas as etapas foram finalizadas
    def estah_em_aberto_antes_submissao(self):
        if self.ativo:
            if self.periodo_submissao_inscricao_inicio and self.periodo_submissao_inscricao_final:
                return datetime.datetime.now() < self.periodo_submissao_inscricao_inicio
        return False

    #
    def estah_em_aberto(self):
        if self.ativo:
            if self.periodo_submissao_inscricao_inicio and self.periodo_submissao_inscricao_final:
                return (
                    datetime.datetime.now() >= self.periodo_submissao_inscricao_inicio
                    and datetime.datetime.now() <= self.periodo_submissao_inscricao_final
                )
        return False

    #
    def estah_em_andamento(self):
        # Se esta ativo,
        # Se nao esta em aberto,
        # Se existe periodo de submissao da segunda etapa,
        # Se ainda esta dentro do periodo de periodo_submissao_segunda_etapa_final
        if self.ativo and self.periodo_submissao_segunda_etapa_final:
            if not self.estah_em_aberto() and datetime.datetime.now() <= self.periodo_submissao_segunda_etapa_final:
                return True
        return False

    #
    def estah_finalizado(self):
        if self.ativo and self.periodo_submissao_segunda_etapa_final:
            if datetime.datetime.now() > self.periodo_submissao_segunda_etapa_final:
                return True
        return False

    def estah_em_periodo_de_desistencia(self):
        if self.ativo:
            if self.periodo_desistencia_inicio and self.periodo_desistencia_final:
                return datetime.datetime.now() >= self.periodo_desistencia_inicio and datetime.datetime.now() <= self.periodo_desistencia_final
        return False

    #
    def situacao_atual(self):
        if self.estah_em_aberto():
            return 1
        if self.estah_em_aberto_antes_submissao():
            return 4
        if self.estah_em_andamento():
            return 2
        if self.estah_finalizado():
            return 3
        return None

    #
    def situacao_atual_html(self):
        if not self.situacao_atual():
            return '-'
        display = "<span class='status {} text-nowrap-normal'>{}</span>"
        if self.situacao_atual() == 1:
            return format_html(display.format('status-info', 'Em aberto'))
        if self.situacao_atual() == 4:
            return format_html(display.format('status-info', 'Em aberto antes do Período de Submissão'))
        if self.situacao_atual() == 2:
            return format_html(display.format('status-alert', 'Em andamento'))
        if self.situacao_atual() == 3:
            return format_html(display.format('status-success', 'Finalizado'))

    situacao_atual_html.short_description = 'Situação atual'

    def situacao_atual_str(self):
        if not self.situacao_atual():
            return '-'
        if self.situacao_atual() == 1:
            return 'Em aberto'
        if self.situacao_atual() == 4:
            return 'Em aberto antes do Período de Submissão'
        if self.situacao_atual() == 2:
            return 'Em andamento'
        if self.situacao_atual() == 3:
            'Finalizado'

    def permite_analise_solicitacoes(self):
        """
        Centraliza a regra que determina se a gestão pode analisar solicitações de alteração
        para este edital. Usa a configuração em `comum.Configuracao` (chave
        'analise_permitida_desde' no app 'licenca_capacitacao') quando definida.

        Valores esperados em Configuracao:
          - 'inicio_submissao' -> permite analisar desde o início das inscrições
          - 'fim_submissao' ou None -> só permite quando o edital estiver em andamento
        """
        cfg_val = Configuracao.get_valor_por_chave('licenca_capacitacao', 'analise_permitida_desde')
        now = datetime.datetime.now()

        if cfg_val == 'inicio_submissao':
            if self.ativo and self.periodo_submissao_segunda_etapa_final:
                if self.periodo_submissao_inscricao_inicio and now < self.periodo_submissao_inscricao_inicio:
                    return False
                return not (self.periodo_submissao_segunda_etapa_final and now > self.periodo_submissao_segunda_etapa_final)
            return False
        return self.estah_em_andamento()

    # ------------------------------------------------------------------------------
    # PERFIS
    # ------------------------------------------------------------------------------
    @staticmethod
    def eh_perfil_gestao(user):
        return in_group(user, ['Gerenciador do Editais de Licença Capacitação'])

    # ------------------------------------------------------------------------------
    # OUTROS
    # ------------------------------------------------------------------------------
    def can_change(self, user, lancar_excecao=False):
        if not self.ativo and EditalLicCapacitacao.eh_perfil_gestao(user):
            return True
        else:
            if lancar_excecao:
                raise ValidationError('Para editar este edital você precisa fazer parte da Gestão de Editais e o edital não pode estar ativo.')
            else:
                return False

    def pode_ativar(self, user, lancar_excecao=False):
        if not self.ativo and EditalLicCapacitacao.eh_perfil_gestao(user):
            return True
        else:
            if lancar_excecao:
                raise ValidationError('Este edital não pode ser ativado.')
            else:
                return False

    def pode_inativar(self, user, lancar_excecao=False):
        if self.ativo and EditalLicCapacitacao.eh_perfil_gestao(user):
            return True
        else:
            if lancar_excecao:
                raise ValidationError('Este edital não pode ser inativado.')
            else:
                return False

    def pode_visualizar_como_servidor(self, user, lancar_excecao=False):
        retorno = True

        # O usuario precisa ser servidor
        if not eh_servidor(user):
            if lancar_excecao:
                raise ValidationError('Apenas servidores podem submeter.')
            else:
                retorno = False

        # O servidor soh pode ver editais ativos
        if not self.ativo:
            if lancar_excecao:
                raise ValidationError('Servidores só podem visualizar editais ativos.')
            else:
                retorno = False

        return retorno

    def pode_cadastrar_pedido(self, user, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras se pode cadastrar um pedido em um edital especifico
        #   - Cadastrar um novo pedido para este edital
        # *** SEMPRE QUE HOUVER ALTERAÇÃO NESTE MÉTODO DEVE-SE REVISAR O A VIEW index_inscricoes
        # ----------------------------------------------------

        # Apenas servidores podem submeter ao edital
        # ---------------------------------------------------------------------------
        if not eh_servidor(user):
            if lancar_excecao:
                raise ValidationError('Apenas servidores podem submeter.')
            else:
                return False

        # Edital tem que tá em Aberto
        # ---------------------------------------------------------------------------
        if not self.estah_em_aberto():
            if lancar_excecao:
                raise ValidationError('Só pode cadastrar pedido para edital que estiver em aberto.')
            else:
                return False

        servidor_estah_apto_no_edital = EditalLicCapacitacao.servidor_estah_apto_no_edital(self, user.get_relacionamento())
        if not servidor_estah_apto_no_edital:
            if lancar_excecao:
                raise ValidationError('Servidor não está apto a submeter pedido neste edital.')
            else:
                return False

        return True

    @staticmethod
    def pode_exportar_dados_dos_pedidos(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode exportar dados do pedido.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        if not edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível exportar pedidos de um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível exportar pedidos de um edital sem pedidos.')
            else:
                return False

        # Não permite se tiver alguma solicitacao de alteracao que ainda nao foi analisada
        # ----------------------------
        if EditalLicCapacitacao.existe_solicitacoes_de_servidor_nao_analisadas_no_edital(edital):
            if lancar_excecao:
                raise ValidationError(
                    'Impossível exportar pedidos de um edital que ainda possui solicitações de alteração de dados pendentes de análise.'
                )
            else:
                return False

        return True

    @staticmethod
    def pode_importar_resultado_final(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode importar o resultado final.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        if not edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível importar o resultado final de um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível importar o resultado final de um edital sem pedidos.')
            else:
                return False

        # Se o edital tem processamento externo
        # ----------------------------
        if not edital.processamento_externo:
            if lancar_excecao:
                raise ValidationError('Impossível importar o resultado final para um edital configurado para processamento externo.')
            else:
                return False

        # Não permite se tiver alguma solicitacao de alteracao que ainda nao foi analisada
        # ----------------------------
        if EditalLicCapacitacao.existe_solicitacoes_de_servidor_nao_analisadas_no_edital(edital):
            if lancar_excecao:
                raise ValidationError(
                    'Impossível importar o resultado final para um edital que ainda possui solicitações de alteração de dados pendentes de análise.'
                )
            else:
                return False

        return True

    @staticmethod
    def existe_algum_processamento_possa_editar(user, edital):
        processamentos = ProcessamentoEdital.objects.filter(edital=edital)
        return any(ProcessamentoEdital.pode_editar(user, p, lancar_excecao=False) for p in processamentos)

    @staticmethod
    def existe_algum_processamento_nao_cancelado_no_edital(edital):
        return ProcessamentoEdital.objects.filter(edital=edital, cancelado=False).exists()

    @staticmethod
    def existe_algum_processamento_no_edital(edital):
        return ProcessamentoEdital.objects.filter(edital=edital).exists()

    @staticmethod
    def existe_algum_pedido_pendente_de_submissao_do_servidor_no_edital(edital, servidor):
        return PedidoLicCapacitacao.objects.filter(edital=edital, servidor=servidor, situacao=PedidoLicCapacitacao.PENDENTE_SUBMISSAO).exists()

    @staticmethod
    def existe_algum_pedido_submetido_do_servidor_no_edital(edital, servidor):
        return PedidoLicCapacitacao.objects.filter(edital=edital, servidor=servidor, situacao=PedidoLicCapacitacao.SUBMETIDO).exists()

    @staticmethod
    def existe_algum_pedido_do_servidor_no_edital(edital, servidor):
        return PedidoLicCapacitacao.objects.filter(edital=edital, servidor=servidor).exists()

    @staticmethod
    def existe_somente_pedidos_cancelados_do_servidor_no_edital(edital, servidor):
        return PedidoLicCapacitacao.objects.filter(edital=edital, servidor=servidor).exclude(situacao=PedidoLicCapacitacao.CANCELADO).exists()

    @staticmethod
    def get_dados_calculos_servidor_no_edital(edital, servidor):
        # Gerais
        calculos_exercicio = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor)

        # Período aquisitivo/usofruto
        calculos_quinquenios = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).order_by('periodo')

        # Licencas anteriores - SIAPE
        codigos_lc = EditalLicCapacitacao.get_todos_os_codigos_licenca_capacitacao()
        lista_afastamentos_siape = ServidorAfastamento.objects.filter(servidor=servidor, afastamento__codigo__in=codigos_lc, cancelado=False).extra(
            select={'tipo': "'SIAPE'"}
        )
        # Licencas anteriores - SUAP - Nao cadastrados no SIAPE E Aprovado de forma definitiva no resultado final
        lista_afastamentos_suap = (
            PeriodoPedidoLicCapacitacao.objects.filter(
                pedido__servidor=servidor, pedido__cadastrado_no_siape=False, pedido__aprovado_em_definitivo=True, pedido__cancelado_pela_gestao=False
            )
            .exclude(pedido__edital=edital.id)
            .extra(select={'tipo': "'SUAP'"})
        )
        licencas_capacitacao_servidor = []
        for lic in lista_afastamentos_siape:
            d = {}
            d['afastamento'] = lic.afastamento
            d['data_inicio'] = lic.data_inicio
            d['data_termino'] = lic.data_termino
            d['quantidade_dias_afastamento'] = lic.quantidade_dias_afastamento + 1
            d['tipo'] = 'SIAPE'
            licencas_capacitacao_servidor.append(d)
        for lic in lista_afastamentos_suap:
            d = {}
            d['pedido'] = lic.pedido
            d['afastamento'] = 'Licença Capacitação'
            d['data_inicio'] = lic.data_inicio
            d['data_termino'] = lic.data_termino
            d['quantidade_dias_afastamento'] = lic.pedido.get_qtd_dias_periodos_pedido()
            d['tipo'] = 'SUAP'
            licencas_capacitacao_servidor.append(d)

        # Afasts que nao contam como efetiv exercicios que foram consirados nos parametros de calculo
        from licenca_capacitacao.regras_calculos import (
            get_datetime_now,
            get_inicio_servico_publico,
            get_servidor_afastamento_nao_conta_como_efet_exerc,
        )

        solicitacao_valida = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(servidor=servidor, edital=edital, situacao__isnull=True)
        data_ajustada = ServidorDataInicioExercicioAjustada.get_data_ajustada(servidor)
        _, data_inicio_servico_publico = get_inicio_servico_publico(solicitacao_valida, data_ajustada, servidor)
        afastamentos_nao_conta_como_efet_exerc = get_servidor_afastamento_nao_conta_como_efet_exerc(
            servidor, data_inicio_servico_publico, get_datetime_now(), entre_periodos=True
        )

        return calculos_exercicio, calculos_quinquenios, licencas_capacitacao_servidor, afastamentos_nao_conta_como_efet_exerc

    @staticmethod
    @transaction.atomic()
    def habilitar_analise_das_solicitacoes_do_servidor_no_edital(edital, servidor):
        # Atualiza as solicitacoes de alteracao de dados
        lista_dt = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(edital=edital, servidor=servidor).exclude(
            situacao__in=[
                SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_DEFERIDO,
                SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_INDEFERIDO,
            ]
        )
        lista_ad = SolicitacaoAlteracaoDados.objects.filter(edital=edital, servidor=servidor).exclude(
            situacao__in=[SolicitacaoAlteracaoDados.SITUACAO_SOLICITACAO_DEFERIDO, SolicitacaoAlteracaoDados.SITUACAO_SOLICITACAO_INDEFERIDO]
        )

        pode_analisar = EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(edital, servidor)

        for dt in lista_dt:
            dt.pode_analisar = pode_analisar
            dt.save()
        for ad in lista_ad:
            ad.pode_analisar = pode_analisar
            ad.save()

    @staticmethod
    def existe_solicitacoes_de_servidor_nao_analisadas_no_edital(edital):
        # se existem solicitacoes de alteracao de dados que ainda nao foram analisaas no edital
        lista_dt = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(edital=edital, pode_analisar=True).exclude(
            situacao__in=[
                SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_DEFERIDO,
                SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_INDEFERIDO,
            ]
        )
        lista_ad = SolicitacaoAlteracaoDados.objects.filter(edital=edital, pode_analisar=True).exclude(
            situacao__in=[SolicitacaoAlteracaoDados.SITUACAO_SOLICITACAO_DEFERIDO, SolicitacaoAlteracaoDados.SITUACAO_SOLICITACAO_INDEFERIDO]
        )

        return lista_dt or lista_ad

    @staticmethod
    def servidor_estah_apto_no_edital(edital, servidor):
        if edital.bloqueia_pedido_servidor_nao_apto:
            servidores = EditalLicCapacitacao.get_servidores_efetivo_exercicio().filter(id=servidor.id).exists()
            servidores_complementares = ServidorComplementar.objects.filter(edital=edital, servidor=servidor).exists()
            return servidores or servidores_complementares
        else:
            return True

    @staticmethod
    def get_todos_os_codigos_licenca_capacitacao():
        # Lista todos os codigos de licenca capacitacao independente do edital
        codigos = []
        codigos.append(AfastamentoSiape.LICENCA_CAPACITACAO_3_MESES)
        codigos += list(CodigoLicencaCapacitacao.objects.all().values_list('codigo__codigo', flat=True))
        return list(set(codigos))


class AnexosEdital(models.ModelPlus):
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Pedido')
    descricao = models.CharFieldPlus('Descrição', max_length=255)
    arquivo = models.FileFieldPlus('Arquivo', upload_to='upload/lic_capacitacao/anexos/', max_length=400)

    ARQUIVO_TIPO_GERAL = 1
    ARQUIVO_TIPO_RESULTADO_PARCIAL = 2
    ARQUIVO_TIPO_RESULTADO_FINAL = 3
    ARQUIVO_TIPO_CHOICES = [
        [ARQUIVO_TIPO_GERAL, 'GERAL'],
        [ARQUIVO_TIPO_RESULTADO_PARCIAL, 'RESULTADO PARCIAL'],
        [ARQUIVO_TIPO_RESULTADO_FINAL, 'RESULTADO FINAL'],
    ]
    tipo = models.PositiveIntegerField('Tipo do arquivo', default=1, choices=ARQUIVO_TIPO_CHOICES)

    data_cadastro = models.DateTimeFieldPlus('Data de cadastro', editable=False, auto_now_add=True)

    class Meta:
        ordering = ['data_cadastro']
        verbose_name = 'Anexo do Edital'
        verbose_name_plural = 'Anexos do Edital'

    def __str__(self):
        return f'{self.descricao}'


class MotivoLicencaCapacitacao(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=255)
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Motivo para licença capacitação'
        verbose_name_plural = 'Motivos para licença capacitação'


# --------------------
# PEDIDO E SEUS DADOS
# --------------------


class PedidoLicCapacitacao(models.ModelPlus):
    # -------------------------------------------------
    # Dados gerais
    # -------------------------------------------------
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')

    PENDENTE_SUBMISSAO = 1
    SUBMETIDO = 2
    CANCELADO = 3
    SITUACAO_SUBMISSAO_CHOICES = [[PENDENTE_SUBMISSAO, 'PENDENTE DE SUBMISSÃO'], [SUBMETIDO, 'SUBMETIDO'], [CANCELADO, 'CANCELADO']]
    situacao = models.PositiveIntegerField('Situação da Submissão', default=1, editable=False, choices=SITUACAO_SUBMISSAO_CHOICES)

    data_cadastro = models.DateTimeFieldPlus('Data de cadastro', editable=False, auto_now_add=True, null=True)
    data_ultima_submissao = models.DateTimeFieldPlus('Data da última Submissão', null=True, blank=True, editable=False)
    data_ultimo_cancelamento = models.DateTimeFieldPlus('Data do último Cancelamento', null=True, blank=True, editable=False)

    """
      - Motivo
      - Modalidade: choice com a distancia ou presencial
      - CH Prevista: int em horas
      - Instituição promotora do evento: nome = models.CharFieldPlus('Nome')
      - Outros dados/documentos que poderão ser informados conforme necessidade do servidor
        (poderão ser adicionados por upload de PDF, documento eletrônico ou textarea)
        - Custos previstos relacionados diretamente com a ação, se houver;
          e custos previstos com diárias e passagens, se houver.
        - Justificativa quanto ao interesse da administração pública naquela ação,
          visando o desenvolvimento do servidor;
        - Cópia do trecho do PDP do órgão onde está indicada aquela necessidade de
          desenvolvimento;
      - Parcela(s) de afastamento: formset
    """

    # -------------------------------------------------
    # Dados específicos
    # -------------------------------------------------
    motivo = models.ForeignKeyPlus('licenca_capacitacao.MotivoLicencaCapacitacao', verbose_name='Motivo da licença capacitação')
    PRESENCIAL = 1
    A_DISTANCIA = 2
    MODALIDADE_CHOICES = [[PRESENCIAL, 'PRESENCIAL'], [A_DISTANCIA, 'A DISTÂNCIA']]
    carga_horaria = models.PositiveIntegerField('Carga horária total (horas)')
    instituicao = models.CharFieldPlus('Instituição')
    local = models.CharFieldPlus('Local', help_text='Local em que será realizada', blank=True)
    cnpj_instituicao = models.BrCnpjField(
        verbose_name='CNPJ da Instituição promotora', blank=True, help_text='Esse campo é obrigatório se a empresa promotora for no Brasil.'
    )

    NAO_SE_APLICA = 1
    CUSTEADO_PELO_SERVIDOR = 2
    CUSTEADO_PELA_INSTITUICAO = 3

    ORIGEM_RECURSO = [
        [NAO_SE_APLICA, 'Não Se Aplica'],
        [CUSTEADO_PELO_SERVIDOR, 'Custeado Pelo Servidor'],
        [CUSTEADO_PELA_INSTITUICAO, 'Custeado Pela Instituição'],
    ]

    modalidade = models.PositiveIntegerField('Modalidade', choices=MODALIDADE_CHOICES)
    despesa_custeio = models.DecimalFieldPlus(
        verbose_name='Despesa de Custeio R$',
        null=True,
        help_text='Preencher com as despesas para custeio previstas com inscrição e mensalidade relacionadas com a ação de desenvolvimento. Informar 0.00 R$ se não houver custo.',
    )
    despesa_custeio_origem = models.PositiveIntegerField(verbose_name='Origem do Recurso de Custeio', null=True, choices=ORIGEM_RECURSO)

    custos_diarias_passagens = models.DecimalFieldPlus(
        verbose_name='Custo em Diárias e Passagens R$',
        null=True,
        help_text='Preencher com Custos previstos com diárias e passagens. Informar 0.00 R$ se não houver custo.',
    )
    custos_diarias_passagens_origem = models.PositiveIntegerField(
        verbose_name='Origem do Recurso de Diárias e Passagens', null=True, choices=ORIGEM_RECURSO
    )

    acao = models.CharFieldPlus('Curso/Ação')
    outros_detalhes = models.TextField('Outros detalhes', null=True, blank=True)

    # Solicitacao (pelo servidor) e Analise (por parte da gestão) de Desistencia
    data_solicitacao_desistencia = models.DateTimeFieldPlus('Data da Solicitação da desistência', null=True)
    solicitacao_desistencia = models.TextField('Solicitação da desistência', null=True)
    parecer_desistencia = models.TextField('Parecer da desistência', null=True, blank=True)
    desistencia = models.BooleanField('Desistência', default=False)
    data_parecer_desistencia = models.DateTimeFieldPlus('Data do Parecer da desistência', null=True)
    usuario_cadastro_desistencia = models.ForeignKeyPlus('comum.User', verbose_name='Usuário cadastro desistência', null=True)

    # Resultado parcial ---
    aprovado_resultado_parcial = models.BooleanField(verbose_name='Aprovado no Resultado Parcial', null=True)
    justificativa_nao_aprovacao_resultado_parcial = models.TextField('Justificativa de não aprovação no Resultado Parcial', null=True, blank=True)
    ordem_classificacao_resultado_parcial = models.PositiveIntegerField('Ordem de classificação no Resultado Parcial', null=True, blank=True)
    ordem_classificacao_resultado_parcial_gestao = models.PositiveIntegerField(
        'Ordem de classificação no Resultado Parcial (gestão)', null=True, blank=True
    )

    # Resultado final ---
    aprovado_resultado_final = models.BooleanField(verbose_name='Aprovado no Resultado Final', null=True)
    justificativa_nao_aprovacao_resultado_final = models.TextField('Justificativa de não aprovação no Resultado Final', null=True, blank=True)
    ordem_classificacao_resultado_final = models.PositiveIntegerField('Ordem de classificação no Resultado Final', null=True, blank=True)
    ordem_classificacao_resultado_final_gestao = models.PositiveIntegerField(
        'Ordem de classificação no Resultado Final (gestão)', null=True, blank=True
    )

    # Sincronizado com o SIAPE
    cadastrado_no_siape = models.BooleanField(verbose_name='Sincronizado com o SIAPE', default=False)

    # Se foi aprovado de forma definitiva (depende de regras do tornar processamento definitivo)
    # - se teve resultado final de forma definitiva
    aprovado_em_definitivo = models.BooleanField(verbose_name='Aprovado de forma definitiva', default=False)

    eh_tecnico_administrativo = models.BooleanField(verbose_name='TAE', default=False)
    eh_docente = models.BooleanField(verbose_name='DOCENTE', default=False)

    justificativa_cancelado_pela_gestao = models.TextField('Justificativa do cancelamento pela gestão', null=True, blank=True)
    cancelado_pela_gestao = models.BooleanField('Cancelado pela gestão', default=False)

    class Meta:
        verbose_name = 'Submissão de Pedido de Licença para Capacitação'
        verbose_name_plural = 'Submissões de Pedido de Licença para Capacitação'

    def __str__(self):
        return f'Submissão de {self.servidor} ao {self.edital}'

    def set_categoria_servidor(self):
        self.eh_tecnico_administrativo = False
        self.eh_tecnico_administrativo = False
        if self.servidor.eh_tecnico_administrativo:
            self.eh_tecnico_administrativo = True
        elif self.servidor.eh_docente:
            self.eh_docente = True
        else:
            s = ServidorComplementar.objects.filter(edital=self.edital, servidor=self.servidor)
            if s:
                if s[0].categoria == 'docente':
                    self.eh_docente = True
                if s[0].categoria == 'tecnico_administrativo':
                    self.eh_tecnico_administrativo = True

    def save(self, *args, **kargs):
        self.set_categoria_servidor()
        super().save(*args, **kargs)

    @property
    def categoria_display(self):
        if self.eh_docente:
            return 'Docente'
        elif self.eh_tecnico_administrativo:
            return 'Técnico-administrativo'
        return 'Indefinida'

    @property
    def situacao_atual_html(self):
        display = "<span class='status {} text-nowrap-normal'>{} em: {}</span>"
        display2 = "<span class='status {} text-nowrap-normal'>{}</span>"
        if self.situacao == 1:
            return format_html(display2.format('status-info', 'PENDENTE DE SUBMISSÃO'))
        if self.situacao == 2:
            return format_html(display.format('status-success', 'SUBMETIDO', format_datetime(self.data_ultima_submissao)))
        if self.situacao == 3:
            return format_html(display.format('status-error', 'CANCELADO', format_datetime(self.data_ultimo_cancelamento)))

    @property
    def situacao_atual_str(self):
        if self.situacao == 1:
            return 'Pendente de submissão'
        if self.situacao == 2:
            return 'Submetido'
        if self.situacao == 3:
            return 'Cancelado'

    def pode_editar(self, user, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras se pode ou nao editar uma submissao (SERVIDOR QUE SUBMETEU)
        # ----------------------------------------------------

        if not eh_servidor(user):
            return False

        # A submissao só pode ser editada pelo servidor que a submeteu
        # ---------------------------------------------------------------------------
        # if not self.servidor == user.get_relacionamento() and not self.edital.eh_perfil_gestao(user):
        if self.servidor != user.get_relacionamento():
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser editado pelo servidor que a submeteu.')
            else:
                return False

        # Os dados só podem ser alterados se o pedido tiver como PENDENTE_SUBMISSAO ou o edital puder receber pedidos
        # ---------------------------------------------------------------------------
        if self.situacao != self.PENDENTE_SUBMISSAO:
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser editado se o pedido estiver como PENDENTE DE SUBMISSÃO')
            else:
                return False

        if not self.edital.pode_cadastrar_pedido(user=user):
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser editado se o edital puder receceber pedidos.')
            else:
                return False

        return True

    def pode_visualizar(self, user, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras se pode ou não visualizar um pedido
        # ----------------------------------------------------
        if not eh_servidor(user):
            return False

        # Só pode visualizar um pedido por essa view
        #   - Servidor que a submeteu
        # ---------------------------------------------------------------------------
        if self.servidor != user.get_relacionamento():
            if lancar_excecao:
                raise ValidationError('Só pode ser visualizado pelo servidor que a cadastrou.')
            else:
                return False

        return True

    def servidor_pedido_estah_sem_categoria(self):
        return not (self.eh_tecnico_administrativo or self.eh_docente)

    def pode_submeter(self, user, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras de submeter
        # ----------------------------------------------------
        # Se o edital ainda permite
        # Se os dados da sumissao esteja ok
        # Se nao existe outra ja sbmetida (deve desfazer a submissao para poder submeter outra)
        # ...

        if not self.edital.pode_cadastrar_pedido(user=user):
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser submetido se o edital puder receceber pedidos.')
            else:
                return False

        if self.servidor != user.get_relacionamento():
            if lancar_excecao:
                raise ValidationError('A submissão só pode ser realizada pelo servidor que a cadastrou.')
            else:
                return False

        if self.situacao != self.PENDENTE_SUBMISSAO:
            if lancar_excecao:
                raise ValidationError('A submissão só pode ser realizada se ela tiver como PENDENTE DE SUBMISSÃO.')
            else:
                return False

        if self.servidor_pedido_estah_sem_categoria():
            if lancar_excecao:
                raise ValidationError(
                    'Servidor não pode submeter por não ser possível verificar a qual categoria (Técnico-administrativo ou Docente) o servidor está vinculado.'
                )
            else:
                return False

        return True

    def pode_recalcular_pedido(self, user, lancar_excecao=False):
        if not eh_servidor(user):
            if lancar_excecao:
                raise ValidationError('Apenas servidores podem submeter.')
            else:
                return False

        if not self.edital.estah_em_aberto():
            if lancar_excecao:
                raise ValidationError('Só pode cadastrar pedido para edital que estiver em aberto.')
            else:
                return False

        if self.situacao != self.PENDENTE_SUBMISSAO:
            if lancar_excecao:
                raise ValidationError('A submissão só pode ser realizada se ela tiver como PENDENTE DE SUBMISSÃO.')
            else:
                return False

        return True

    def pode_desfazer_submissao(self, user=None, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras de desfazer uma submissao
        # ----------------------------------------------------
        if not self.edital.pode_cadastrar_pedido(user=user):
            if lancar_excecao:
                raise ValidationError('A submissão só pode ser desfeita se o edital puder receceber pedidos.')
            else:
                return False

        if self.servidor != user.get_relacionamento():
            if lancar_excecao:
                raise ValidationError('A submissão só pode ser desfeita pelo servidor que submeteu.')
            else:
                return False

        if self.situacao != self.SUBMETIDO:
            if lancar_excecao:
                raise ValidationError('A submissão só pode ser desfeita se ela estiver submetida')
            else:
                return False

        return True

    def pode_cancelar(self, user=None, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras de cancelamento de uma subissao
        # ----------------------------------------------------
        if not self.edital.pode_cadastrar_pedido(user=user):
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser cancelado se o edital puder receceber pedidos.')
            else:
                return False

        if self.servidor != user.get_relacionamento():
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser cancelado  pelo servidor que a cadastrou.')
            else:
                return False

        if self.situacao != self.PENDENTE_SUBMISSAO:
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser cancelado se o edital tiver como PENDENTE DE SUBMISSÃO.')
            else:
                return False

        return True

    def pode_descancelar(self, user=None, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras de descancelamento de uma subissao
        # ----------------------------------------------------
        if not self.edital.pode_cadastrar_pedido(user=user):
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser descancelado se o edital puder receceber pedidos.')
            else:
                return False

        if self.servidor != user.get_relacionamento():
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser descancelado pelo servidor que a cadastrou.')
            else:
                return False

        if self.situacao != self.CANCELADO:
            if lancar_excecao:
                raise ValidationError('O pedido só pode ser descancelado se ele tiver como CANCELADO.')
            else:
                return False

        return True

    def pode_visualizar_calculos(self, user):
        gestao_pode_ver = EditalLicCapacitacao.eh_perfil_gestao(user)
        servidor_pode_ver = eh_servidor(user) and self.servidor == user.get_relacionamento()
        return gestao_pode_ver or servidor_pode_ver

    def pode_imprimir_pedido(self, user):
        return (
            self.edital.ativo and eh_servidor(user) and self.servidor == user.get_relacionamento() and self.situacao == PedidoLicCapacitacao.SUBMETIDO
        )

    def pode_solicitar_desistencia_pedido(self, user):
        # Essa funcionalidade não será utilizada inicialmente
        # - Estamos colocando False para desabilitar/ocultar especificamente
        # - Este fluxo será revisado
        """
        return eh_servidor(user) and \
            self.edital.estah_em_periodo_de_desistencia() and \
            not self.data_solicitacao_desistencia and \
            self.servidor == user.get_relacionamento() and \
            self.situacao == PedidoLicCapacitacao.SUBMETIDO
        """
        return False

    def pode_gestao_cancelar(self, user=None, lancar_excecao=False):
        # ----------------------------------------------------
        # Todas as regras de cancelamento de um pedido por parte da gestao
        # ----------------------------------------------------
        if user and not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode cancelar um pedido já aprovado em definitivo.')
            else:
                return False

        if not self.aprovado_em_definitivo:
            if lancar_excecao:
                raise ValidationError('O pedido deve ter sido aprovado em definitivo.')
            else:
                return False

        if self.cadastrado_no_siape:
            if lancar_excecao:
                raise ValidationError('Este pedido não pode ser cancelado pela gestão pode já ter sido cadastrado no SIAPE.')
            else:
                return False

        if self.cancelado_pela_gestao:
            if lancar_excecao:
                raise ValidationError('Este pedido já foi cancelado pela gestão')
            else:
                return False

        return True

    @staticmethod
    @transaction.atomic()
    def submeter_pedido(pedido, user):
        pedido.pode_submeter(user=user, lancar_excecao=True)
        pedido.situacao = PedidoLicCapacitacao.SUBMETIDO
        pedido.data_ultima_submissao = datetime.datetime.now()
        pedido.save()

    @staticmethod
    @transaction.atomic()
    def desfazer_sumbmissao_pedido(pedido, user):
        pedido.pode_desfazer_submissao(user=user, lancar_excecao=True)
        pedido.situacao = PedidoLicCapacitacao.PENDENTE_SUBMISSAO
        pedido.save()

    @staticmethod
    @transaction.atomic()
    def cancelar_pedido(pedido, user):
        pedido.pode_cancelar(user=user, lancar_excecao=True)
        pedido.situacao = PedidoLicCapacitacao.CANCELADO
        pedido.data_ultimo_cancelamento = datetime.datetime.now()
        pedido.save()

    @staticmethod
    @transaction.atomic()
    def descancelar_pedido(pedido, user):
        pedido.pode_descancelar(user=user, lancar_excecao=True)
        pedido.situacao = PedidoLicCapacitacao.PENDENTE_SUBMISSAO
        pedido.save()

    @staticmethod
    def get_pedidos_para_processamento(edital=None):
        # pedidos que foram submetidos e que podem ser utilizados pelo processamento
        pedidos = PedidoLicCapacitacao.objects.filter(situacao=PedidoLicCapacitacao.SUBMETIDO, desistencia=False).order_by('servidor')
        if edital:
            pedidos = pedidos.filter(edital=edital)

        return pedidos

    @staticmethod
    def get_pedidos_submetidos(edital=None):
        # apenas pedidos que foram submetidos
        pedidos = PedidoLicCapacitacao.objects.filter(situacao=PedidoLicCapacitacao.SUBMETIDO).order_by('servidor')
        if edital:
            pedidos = pedidos.filter(edital=edital)

        return pedidos

    @staticmethod
    def get_pedidos_aprovado_em_definitivo(edital=None):
        pedidos = PedidoLicCapacitacao.objects.filter(aprovado_em_definitivo=True).order_by('servidor')
        if edital:
            pedidos = pedidos.filter(edital=edital)
        return pedidos

    @staticmethod
    def get_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape(edital=None):
        pedidos = PedidoLicCapacitacao.objects.filter(aprovado_em_definitivo=True).order_by('servidor')
        pedidos = pedidos.filter(cadastrado_no_siape=False)
        if edital:
            pedidos = pedidos.filter(edital=edital)
        return pedidos

    @staticmethod
    def get_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape_por_data(data, edital=None):
        pedidos = PedidoLicCapacitacao.objects.filter(aprovado_em_definitivo=True).order_by('servidor')
        pedidos = pedidos.filter(cadastrado_no_siape=False)

        if edital:
            pedidos = pedidos.filter(edital=edital)

        periodos = PeriodoPedidoLicCapacitacao.objects.filter(pedido=OuterRef('pk'), data_inicio__lte=data, data_termino__gte=data)
        pedidos = pedidos.annotate(existe=Exists(periodos)).filter(existe=True)

        return pedidos

    # Lic. Cap/ Início (data) -- do pedido
    # Lic. Cap/ Término (data)  -- do pedido
    @staticmethod
    def get_inicio_primeiro_periodo_pedido(pedido):
        pedidos = pedido.periodopedidoliccapacitacao_set.all().order_by('data_inicio')
        if pedidos:
            return pedidos[0].data_inicio
        return None

    # @staticmethod
    # def get_periodos_pedido(pedido):
    #    return pedido.periodopedidoliccapacitacao_set.all().order_by('data_inicio')

    # Lic. Cap/ Início (data) -- do pedido
    # Lic. Cap/ Término (data)  -- do pedido
    def get_lista_periodos_pedido(self):
        return self.periodopedidoliccapacitacao_set.all().order_by('data_inicio')

    def get_lista_periodos_pedido_html(self):
        out = ['<ul>']
        lista = self.get_lista_periodos_pedido()
        if lista:
            for e in lista:
                out.append(f'<li>{format_datetime(e.data_inicio)} a {format_datetime(e.data_termino)}</li>')
            out.append('</ul>')
            return format_html(''.join(out))
        return '-'

    def get_qtd_dias_periodos_pedido(self):
        return self.periodopedidoliccapacitacao_set.aggregate(qtd=Sum('qtd_dias_total'))['qtd']


class PedidoLicCapacitacaoServidor(PedidoLicCapacitacao):
    class Meta:
        proxy = True
        verbose_name = 'Submissão de Pedido de Licença para Capacitação'
        verbose_name_plural = 'Submissões de Pedido de Licença para Capacitação'


class AnexosPedidoLicCapacitacaoSubmissao(models.ModelPlus):
    pedido = models.ForeignKeyPlus('licenca_capacitacao.PedidoLicCapacitacao', verbose_name='Pedido')
    descricao = models.CharFieldPlus('Descrição', max_length=400)
    arquivo = models.FileFieldPlus('Arquivo', upload_to='upload/lic_capacitacao/anexos/', max_length=400, null=True, blank=True)

    class Meta:
        ordering = ['descricao']
        verbose_name = 'Anexo do Pedido'
        verbose_name_plural = 'Anexos do Pedido'


class PeriodoPedidoLicCapacitacao(models.ModelPlus):
    pedido = models.ForeignKeyPlus('licenca_capacitacao.PedidoLicCapacitacao', verbose_name='Pedido')

    data_inicio = models.DateFieldPlus('Data início')
    data_termino = models.DateFieldPlus('Data Final')

    # CalculoAquisitivoUsofrutoServidorEdital
    aquisitivo_uso_fruto = models.ForeignKeyPlus(
        'licenca_capacitacao.CalculoAquisitivoUsofrutoServidorEdital', verbose_name='Aquisitivo/Uso fruto', null=True, blank=True
    )

    qtd_dias_total = models.PositiveIntegerField('Quantidade de dias desta parcela', null=True, blank=True)

    class Meta:
        verbose_name = 'Parcela do Pedido'
        verbose_name_plural = 'Parcelas do Pedido'

    def __str__(self):
        return f'{self.data_inicio} a {self.data_termino}'

    def clean(self):
        if self.data_inicio or self.data_termino:
            if not (self.data_inicio and self.data_termino):
                raise ValidationError('É necessário preencher a data de inicial e final.')
            if not (self.data_inicio <= self.data_termino):
                raise ValidationError('A data inicial deve ser menor ou igual a data final.')

    @staticmethod
    def get_periodos_de_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape(edital, servidor):
        periodos = PeriodoPedidoLicCapacitacao.objects.filter(pedido__aprovado_em_definitivo=True, pedido__servidor=servidor).order_by('data_inicio')
        periodos = periodos.filter(pedido__cadastrado_no_siape=False)
        if edital:
            periodos = periodos.filter(pedido__edital=edital)
        return periodos

    def can_change(self, user):
        return EditalLicCapacitacao.eh_perfil_gestao(user)


class CalculoAquisitivoUsofrutoServidorEdital(models.ModelPlus):
    SEARCH_FIELDS = ['edital__titulo', 'servidor__pessoa_fisica__nome']
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')

    periodo = models.PositiveIntegerField('Período')

    inicio_aquisitivo = models.DateFieldPlus('Início do Aquisitivo', null=True, blank=True)
    final_aquisitivo_teorico = models.DateFieldPlus('Final do Aquisitivo teórico', null=True, blank=True)
    qtd_dias_afast_nao_conta_como_efet_exerc = models.PositiveIntegerField('Qud dias de afastamento (não contabiliza efetivo exercício)')
    final_aquisitivo_na_patrica = models.DateFieldPlus('Final do Aquisitivo na prática', null=True, blank=True)

    inicio_uso_fruto = models.DateFieldPlus('Início do Usufruto', null=True, blank=True)
    final_uso_fruto = models.DateFieldPlus('Final do Usufruto', null=True, blank=True)

    ativo_pelo_edital = models.BooleanField('Ativo pelo edital (Válido para este edital) ', default=False)

    # SIAPE
    qtd_dias_lc_siape = models.PositiveIntegerField('Quantidade de dias cadastradas no SIAPE', null=True, blank=True)
    # SUAP
    qtd_dias_lc_suap = models.PositiveIntegerField('Quantidade de dias cadastradas no SUAP', null=True, blank=True)

    class Meta:
        verbose_name = 'Cálculo do Período Aquisitivo e Usufruto do Servidor no Edital'
        verbose_name_plural = 'Cálculo do Período Aquisitivo e Usufruto do Servidor no Edital'

    def __str__(self):
        return f'{self.edital} - {self.servidor}'

    @staticmethod
    def pode_editar(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar os dados dos cálculos.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        if not edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar dados de cálculos para um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível editar dados de cálculos para um edital sem pedidos.')
            else:
                return False

        # Verifica se existe algum processamento no edital
        # ----------------------------
        if EditalLicCapacitacao.existe_algum_processamento_no_edital(edital):
            if lancar_excecao:
                raise ValidationError('Impossível editar dados de cálculos para um edital que possui algum processamento cadastrado.')
            else:
                return False

        return True


class CalculosGeraisServidorEdital(models.ModelPlus):
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')

    categoria_servidor = models.CharField(
        max_length=30,
        choices=[['docente', 'Docente'], ['tecnico_administrativo', 'Técnico-Administrativo']],
        default='tecnico_administrativo',
        null=True,
        blank=True,
    )

    """
    Inicio do exercicio:  1995-08-18
    > Qtd de dias de exercicio:  9139  dias
    > Qtd de dias afast interrompe exerc:  1064  dias
    > Qtd de dias de efetivo exercicio:  8075  dias
    """
    inicio_exercicio = models.DateFieldPlus('Início do exercício', null=True, blank=True)
    qtd_dias_exercicio = models.PositiveIntegerField('Qtd de dias de exercício', null=True, blank=True)
    qtd_dias_afast_nao_conta_como_efet_exerc = models.PositiveIntegerField(
        'Qtd de dias de afastamento (apenas que o não contabilizam como efetivo exercício)', null=True, blank=True
    )
    qtd_dias_efet_exercicio = models.PositiveIntegerField('Qtd de dias de efetivo exercício', null=True, blank=True)
    qtd_dias_afast_capacitacao = models.PositiveIntegerField('Qtd de dias de afastamento capacitação', null=True, blank=True)

    idade_servidor_inicio_abrangencia_edital = models.PositiveIntegerField(
        'Idade do servidor no dia do início da abrangência do edital', null=True, blank=True
    )

    INICIO_SERVICO_PUBLICO = 1
    INICIO_EXERCICIO_INSTITUICAO = 2
    INICIO_EXERCICIO_SOLICITADA = 3
    INICIO_EXERCICIO_AJUSTADA_PELA_GESTAO = 4
    PARAMETRO_INICIO_EXERCICIO_CHOICES = [
        [INICIO_SERVICO_PUBLICO, 'INÍCIO NO SERVIÇO PÚBLICO'],
        [INICIO_EXERCICIO_INSTITUICAO, 'INÍCIO DO EXERCÍCIO NA INSTITUIÇÃO'],
        [INICIO_EXERCICIO_SOLICITADA, 'SOLICITADA PELO SERVIDOR'],
        [INICIO_EXERCICIO_AJUSTADA_PELA_GESTAO, 'AJUSTADA PELA GESTÃO'],
    ]
    # Usa um dos dois campos de servidor
    # - data_inicio_servico_publico
    # - data_inicio_exercicio_na_instituicao
    parametro_inicio_exercicio = models.PositiveIntegerField(
        'Parâmetro utilizado para obter o início do exercício do servidor', default=1, editable=False, choices=PARAMETRO_INICIO_EXERCICIO_CHOICES
    )

    class Meta:
        verbose_name = 'Cálculo do Exercício do Servidor no Edital'
        verbose_name_plural = 'Cálculo do Exercício do Servidor no Edital'

    def __str__(self):
        return f'{self.edital} - {self.servidor}'

    @staticmethod
    def pode_editar(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar os dados dos cálculos.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        if not edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar dados de cálculos para um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível editar dados de cálculos para um edital sem pedidos.')
            else:
                return False

        # Verifica se existe algum processamento no edital
        # ----------------------------
        if EditalLicCapacitacao.existe_algum_processamento_no_edital(edital):
            if lancar_excecao:
                raise ValidationError('Impossível editar dados de cálculos para um edital que possui algum processamento cadastrado.')
            else:
                return False

        return True


class CadastroDesistencia(PedidoLicCapacitacao):
    class Meta:
        proxy = True
        verbose_name = 'Cadastro de Desistência'
        verbose_name_plural = 'Cadastro de Desistência'

    def clean(self):
        if self.desistencia and not self.parecer_desistencia:
            raise ValidationError('Para cadastrar uma desistência é ncessário informar um parecer.')

    @staticmethod
    def pode_cadastrar(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar cadastrar.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        if not edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível cadastrar desistência para um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível cadastrar desistência para um edital sem pedidos.')
            else:
                return False

        return True

    def can_change(self, user):
        pode_cadastrar = CadastroDesistencia.pode_cadastrar(user, self.edital, False)
        pode_pelo_pedido = self.situacao == PedidoLicCapacitacao.SUBMETIDO
        return pode_cadastrar and pode_pelo_pedido


# --------------------
# PROCESSAMENTO
# --------------------


class ProcessamentoEdital(models.ModelPlus):
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')

    finalizado = models.BooleanField('Processamento finalizado', default=False)
    motivo_cancelamento = models.TextField('Motivo do cancelamento', null=True, blank=True)
    cancelado = models.BooleanField('Processamento cancelado', default=False)

    definitivo = models.BooleanField('Definitivo?', default=False)

    titulo = models.CharFieldPlus('Título', null=True, blank=True)

    # data/hora de criacao: usado para ordenar os processamentos
    data_hora_cadastro = models.DateTimeFieldPlus('Data/hora de cadastro', editable=False, auto_now_add=True)

    # add data/hora de finalizacao
    data_hora_finalizacao = models.DateTimeFieldPlus('Data/hora de finalização', null=True, blank=True)

    # tipo_processamento: parcial, final
    PROCESSAMENTO_PARCIAL = 1
    PROCESSAMENTO_FINAL = 2
    PROCESSAMENTO_CHOICES = [[PROCESSAMENTO_PARCIAL, 'RESULTADO PARCIAL'], [PROCESSAMENTO_FINAL, 'RESULTADO FINAL']]
    tipo_processamento = models.PositiveIntegerField('Tipo de processamento', editable=False, choices=PROCESSAMENTO_CHOICES)

    def __str__(self):
        return f'Processamento de {self.get_tipo_processamento_display()} (criado em {format_datetime(self.data_hora_cadastro)}) para o edital {self.edital}'

    @staticmethod
    def pode_criar_processamento(user, edital, tipo, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode gerar os dados de processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        if not edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível gerar os dados de processamento de um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível gerar os dados de processamento de um edital sem pedidos.')
            else:
                return False

        # Se o edital tem processamento externo
        # ----------------------------
        if edital.processamento_externo:
            if lancar_excecao:
                raise ValidationError('Impossível gerar os dados de processamento para um edital configurado para processamento externo.')
            else:
                return False

        # Não gera se existir algum processamento Não Finalizado e Não Cancelado ao mesmo tempo
        # ----------------------------
        if ProcessamentoEdital.objects.filter(edital=edital, finalizado=False, cancelado=False).exists():
            if lancar_excecao:
                raise ValidationError('Impossível gerar o processamento se houver algum processamento que não tenha sido finalizado ou cancelado.')
            else:
                return False

        # Se for processamento parcial OU final
        # ----------------------------
        if tipo == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            # Nao permite se tiver algum parcial definitivo=True
            # So permite um processamento parcial DEFINITIVO por vez
            if ProcessamentoEdital.objects.filter(
                edital=edital, definitivo=True, tipo_processamento=ProcessamentoEdital.PROCESSAMENTO_PARCIAL
            ).exists():
                if lancar_excecao:
                    raise ValidationError(
                        'Impossível gerar os dados de processamento parcial quando existe um processamento parcial definido como definitivo.'
                    )
                else:
                    return False

            # Não permite se tiver alguma solicitacao de alteracao que ainda nao foi analisada
            if EditalLicCapacitacao.existe_solicitacoes_de_servidor_nao_analisadas_no_edital(edital):
                if lancar_excecao:
                    raise ValidationError(
                        'Impossível gerar os dados de processamento de um edital que ainda possui solicitações de alteração de dados pendentes de análise.'
                    )
                else:
                    return False

        elif tipo == ProcessamentoEdital.PROCESSAMENTO_FINAL:
            # So permite se tiver algum parcial finalizado=True e definitivo=True
            if not ProcessamentoEdital.objects.filter(
                edital=edital, finalizado=True, definitivo=True, tipo_processamento=ProcessamentoEdital.PROCESSAMENTO_PARCIAL
            ).exists():
                if lancar_excecao:
                    raise ValidationError(
                        'Impossível gerar os dados de processamento final para um edital que não possui um processamento parcial já finalizado e definitivo.'
                    )
                else:
                    return False

            # Nao permite se tiver alguma final finalizado=True e definitivo=True
            # So gera se nao existe outro final que seja definitivo
            if ProcessamentoEdital.objects.filter(
                edital=edital, definitivo=True, tipo_processamento=ProcessamentoEdital.PROCESSAMENTO_FINAL
            ).exists():
                if lancar_excecao:
                    raise ValidationError('Impossível gerar os dados de processamento final quando existe um processamento definido como definitivo.')
                else:
                    return False

        else:
            return False

        return True

    @staticmethod
    def pode_recalcular_parametros_edital(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode calcular/recalcular parâmetros do edital.')
            else:
                return False

        # TODO rever essa regra quando for homologar a parte de Processamento
        """
        # - Essa demanda será homologada em duas fases
        # So gera se tem algum processamento que possa ser alterado pela gestao
        algum_proc_pode_ser_editado = EditalLicCapacitacao.existe_algum_processamento_possa_editar(user, edital)
         if not algum_proc_pode_ser_editado:
            if lancar_excecao:
                raise ValidationError(
                    'Impossível gerar os dados de processamento final '
                    'quando existe um processamento definido como definitivo.')
            else:
                return False
        """

        return True

    @staticmethod
    def pode_editar(user, processamento, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao (se ainda pode receber sumissao)
        # ----------------------------
        if not processamento.edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar processamento de um edital que não está em andamento.')
            else:
                return False

        # So altera se processamento nao finalizado e nao cancelado
        # ----------------------------
        if processamento.finalizado or processamento.cancelado or processamento.definitivo:
            if lancar_excecao:
                raise ValidationError('Impossível editar processamento que esteja cancelado, finalizado ou definido como definitivo.')
            else:
                return False

        return True

    @staticmethod
    @transaction.atomic()
    def criar_processamento(user, edital, tipo=None, titulo=None, gravar_dados=True):
        if gravar_dados:
            ProcessamentoEdital.pode_criar_processamento(user, edital, tipo, True)

        pp = None
        if gravar_dados:
            # Cria o registro do processamento
            # ----------------------------
            pp = ProcessamentoEdital()
            pp.edital = edital
            pp.tipo_processamento = ProcessamentoEdital.PROCESSAMENTO_PARCIAL
            if tipo:
                pp.tipo_processamento = tipo
            if titulo:
                pp.titulo = titulo
            pp.save()

        # Reprocessa para ter certeza de que os calculos sao os mais atuais E
        # Cadastra os dados em DadosProcessamentoEdital
        # ----------------------------
        # Recalcular para todos os pedidos
        lista_dados_processamento = []
        calcular_pedidos_para_processamento = PedidoLicCapacitacao.get_pedidos_para_processamento(edital)
        from licenca_capacitacao.regras_calculos import calcular, checklist

        for pedp in calcular_pedidos_para_processamento:
            calcular(edital, pedp.servidor)

        # Gera os dados em DadosProcessamentoEdital
        pedidos_para_processamento = PedidoLicCapacitacao.get_pedidos_para_processamento(edital)
        for pedp in pedidos_para_processamento:
            dado = DadosProcessamentoEdital()
            if pp:
                dado.processamento = pp
            dado.pedido = pedp
            dado.inicio_exercicio = ProcessamentoEdital.get_inicio_exercicio(edital, pedp.servidor)
            dado.qtd_dias_total_licenca_capacitacao_utilizada = ProcessamentoEdital.get_qtd_dias_total_licenca_capacitacao_utilizada(
                edital, pedp.servidor
            )
            dado.periodo_aquisitivo_proximo_do_fim = ProcessamentoEdital.get_periodo_aquisitivo_proximo_do_fim(edital, pedp.servidor)
            dado.qtd_dias_efetivo_exercicio = ProcessamentoEdital.get_qtd_dias_efetivo_exercicio(edital, pedp.servidor)
            dado.qtd_dias_afastamento_capacitacao = ProcessamentoEdital.get_qtd_dias_afastamento_capacitacao(edital, pedp.servidor)
            dado.qtd_dias_afast_nao_conta_como_efet_exerc = ProcessamentoEdital.get_qtd_dias_afast_nao_conta_como_efet_exerc(edital, pedp.servidor)
            dado.idade_servidor_inicio_abrangencia_edital = ProcessamentoEdital.get_idade_servidor_inicio_abrangencia_edital(edital, pedp.servidor)
            dado.ordem_classificacao_resultado_parcial_gestao = pedp.ordem_classificacao_resultado_parcial_gestao
            dado.ordem_classificacao_resultado_final_gestao = pedp.ordem_classificacao_resultado_final_gestao
            tem_erro, _ = checklist(pedp, False)
            dado.tem_erro_checklist = tem_erro
            lista_dados_processamento.append(dado)
        if gravar_dados:
            DadosProcessamentoEdital.objects.bulk_create(lista_dados_processamento)
        else:
            return lista_dados_processamento

    @staticmethod
    @transaction.atomic()
    def regerar_dados_processamento(user, processamento):
        ProcessamentoEdital.pode_editar(user, processamento, True)

        DadosProcessamentoEdital.objects.filter(processamento=processamento).delete()

        # Cadastra os dados em DadosProcessamentoEdital
        # ----------------------------
        pedidos_para_processamento = PedidoLicCapacitacao.get_pedidos_para_processamento(processamento.edital)
        for pedp in pedidos_para_processamento:
            dado = DadosProcessamentoEdital()
            dado.processamento = processamento
            dado.pedido = pedp
            dado.inicio_exercicio = ProcessamentoEdital.get_inicio_exercicio(processamento.edital, pedp.servidor)
            dado.qtd_dias_total_licenca_capacitacao_utilizada = ProcessamentoEdital.get_qtd_dias_total_licenca_capacitacao_utilizada(
                processamento.edital, pedp.servidor
            )
            dado.periodo_aquisitivo_proximo_do_fim = ProcessamentoEdital.get_periodo_aquisitivo_proximo_do_fim(processamento.edital, pedp.servidor)
            dado.qtd_dias_efetivo_exercicio = ProcessamentoEdital.get_qtd_dias_efetivo_exercicio(processamento.edital, pedp.servidor)
            dado.qtd_dias_afastamento_capacitacao = ProcessamentoEdital.get_qtd_dias_afastamento_capacitacao(processamento.edital, pedp.servidor)
            dado.qtd_dias_afast_nao_conta_como_efet_exerc = ProcessamentoEdital.get_qtd_dias_afast_nao_conta_como_efet_exerc(
                processamento.edital, pedp.servidor
            )
            dado.idade_servidor_inicio_abrangencia_edital = ProcessamentoEdital.get_idade_servidor_inicio_abrangencia_edital(
                processamento.edital, pedp.servidor
            )
            dado.ordem_classificacao_resultado_parcial_gestao = pedp.ordem_classificacao_resultado_parcial_gestao
            dado.ordem_classificacao_resultado_final_gestao = pedp.ordem_classificacao_resultado_final_gestao
            dado.save()

    @staticmethod
    def get_ultimo_processamento_finalizado_do_edital(edital):
        return ProcessamentoEdital.objects.filter(edital=edital, finalizado=True).order_by('data_hora_cadastro').last()

    @staticmethod
    def get_processamentos_finalizado_e_definitivos_do_edital(edital):
        return ProcessamentoEdital.objects.filter(edital=edital, finalizado=True, definitivo=True).order_by('data_hora_cadastro')

    @staticmethod
    def get_processamentos_do_edital(edital):
        return ProcessamentoEdital.objects.filter(edital=edital).order_by('data_hora_cadastro')

    @staticmethod
    def existe_empate(processamento, tae_docente=None):
        dados = DadosProcessamentoEdital.objects.filter(processamento=processamento)
        if tae_docente == 'tae':
            dados = dados.filter(pedido__eh_tecnico_administrativo=True)
        elif tae_docente == 'docente':
            dados = dados.filter(pedido__eh_docente=True)
        dados = dados.filter(empatado=True)
        return dados.exists()

    @staticmethod
    def existe_intervencao_da_gestao_na_classificacao(processamento, tae_docente=None):
        dados = DadosProcessamentoEdital.objects.filter(processamento=processamento)
        if tae_docente == 'tae':
            dados = dados.filter(pedido__eh_tecnico_administrativo=True)
        elif tae_docente == 'docente':
            dados = dados.filter(pedido__eh_docente=True)
        if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            dados = dados.filter(ordem_classificacao_resultado_parcial_gestao__isnull=False)
        else:
            dados = dados.filter(ordem_classificacao_resultado_final_gestao__isnull=False)
        return dados.exists()

    @staticmethod
    def get_dados_processamento(processamento, tae_docente=None):
        dados = DadosProcessamentoEdital.objects.filter(processamento=processamento)
        if tae_docente == 'tae':
            dados = dados.filter(pedido__eh_tecnico_administrativo=True)
        elif tae_docente == 'docente':
            dados = dados.filter(pedido__eh_docente=True)
        if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            dados = dados.order_by('ordem_classificacao_resultado_parcial')
        else:
            dados = dados.order_by('ordem_classificacao_resultado_final')

        return dados

    @staticmethod
    def get_dados_processamento_em_ordem_desempate(processamento):
        # --------------------
        # Pega os dados em ordem de desempate
        # --------------------
        """
        4.9. Critérios, por ordem de prioridade, para a concessão da licença para capacitação:
        a) ter menos períodos aquisitivos de licença para capacitação utilizados;
        b) período aquisitivo de quinquênio mais próximo a ser expirado
           (tempo em que se encontra no direito de usufruto do último período
           aquisitivo e sem ainda ter havido a concessão correspondente, considerando
           que não são acumuláveis);
        c) maior tempo de efetivo exercício;
        d) ter menos períodos de afastamentos para pós-graduação stricto sensu no País
           ou no exterior;
        e) ter menos períodos de afastamento por licença para tratar de assuntos
           particulares;
        f) idade, tendo preferência o servidor de maior idade; e
        g) perdurando o empate, a decisão será definida por instância
           superior à Gestão de Pessoas.
        """

        dados = DadosProcessamentoEdital.objects.filter(processamento=processamento)
        dados_taes = dados.filter(pedido__eh_tecnico_administrativo=True)
        dados_docentes = dados.filter(pedido__eh_docente=True)

        # ordem_desempate = ['-qtd_dias_total_licenca_capacitacao_utilizada',
        #                    'periodo_aquisitivo_proximo_do_fim',
        #                    '-qtd_dias_efetivo_exercicio',
        #                    'qtd_dias_afastamento_capacitacao',
        #                    'qtd_dias_afast_nao_conta_como_efet_exerc',
        #                    '-idade_servidor_inicio_abrangencia_edital']

        ordem_desempate = [
            'qtd_dias_total_licenca_capacitacao_utilizada',
            'periodo_aquisitivo_proximo_do_fim',
            '-qtd_dias_efetivo_exercicio',
            'qtd_dias_afastamento_capacitacao',
            'qtd_dias_afast_nao_conta_como_efet_exerc',
            '-idade_servidor_inicio_abrangencia_edital',
        ]

        ordem_desempate_resultado_parcial_gestao = ['ordem_classificacao_resultado_parcial_gestao']
        ordem_desempate_resultado_final_gestao = ['ordem_classificacao_resultado_final_gestao']
        if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            dados_taes = dados_taes.order_by(*(ordem_desempate + ordem_desempate_resultado_parcial_gestao))
            dados_docentes = dados_docentes.order_by(*(ordem_desempate + ordem_desempate_resultado_parcial_gestao))
        elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
            dados_taes = dados_taes.order_by(*(ordem_desempate + ordem_desempate_resultado_final_gestao))
            dados_docentes = dados_docentes.order_by(*(ordem_desempate + ordem_desempate_resultado_final_gestao))

        return ordem_desempate, dados_taes, dados_docentes

    @staticmethod
    @transaction.atomic()
    def processar_resultado(user, processamento, task=None):
        ProcessamentoEdital.pode_editar(user, processamento, True)

        """
        4.9. Critérios, por ordem de prioridade, para a concessão da licença para capacitação:
        a) ter menos períodos aquisitivos de licença para capacitação utilizados;
        b) período aquisitivo de quinquênio mais próximo a ser expirado
           (tempo em que se encontra no direito de usufruto do último período
           aquisitivo e sem ainda ter havido a concessão correspondente, considerando
           que não são acumuláveis);
        c) maior tempo de efetivo exercício;
        d) ter menos períodos de afastamentos para pós-graduação stricto sensu no País
           ou no exterior;
        e) ter menos períodos de afastamento por licença para tratar de assuntos
           particulares;
        f) idade, tendo preferência o servidor de maior idade; e
        g) perdurando o empate, a decisão será definida por instância
           superior à Gestão de Pessoas.
        """

        # --------------------
        # Reseta dados calculados pelo processamento
        # --------------------
        dados = ProcessamentoEdital.get_dados_processamento(processamento)
        for d in dados:
            d.justificativa_nao_aprovacao_resultado_parcial = None
            d.justificativa_nao_aprovacao_resultado_final = None
            d.empatado = None
            d.save()

        # --------------------
        # Calcula se teve empate ou nao (empatado=True)
        # --------------------
        ordem_desempate, dados_taes, dados_docentes = ProcessamentoEdital.get_dados_processamento_em_ordem_desempate(processamento)

        def calcular_empate(ordem_desempate, dados_planilha):
            # Representacao em string dos criterios de desempate
            def get_ordem_desempate_str(obj):
                dados = []
                for a in ordem_desempate:
                    dados.append(str(getattr(obj, a.replace('-', ''))))
                return ''.join(dados)

            lista_dados = []
            for atual in dados_planilha:
                lista_dados.append(get_ordem_desempate_str(atual))

            # Verifica as ocorrencias de cada elemento e seta como empate ou nao
            def get_qtd_repetido(lista, elemento):
                return lista.count(elemento)

            for atual in dados_planilha:
                if get_qtd_repetido(lista_dados, get_ordem_desempate_str(atual)) > 1:
                    atual.empatado = True
                else:
                    atual.empatado = False
                atual.save()

        calcular_empate(ordem_desempate, dados_taes)
        calcular_empate(ordem_desempate, dados_docentes)

        # --------------------
        # Calcula ordem de classificacao para cada pedido
        # --------------------
        _, dados_taes, dados_docentes = ProcessamentoEdital.get_dados_processamento_em_ordem_desempate(processamento)

        def calcular_ordem_classificacao(processamento, dados):
            ordem = 1
            for dt in dados:
                if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                    dt.ordem_classificacao_resultado_parcial = ordem
                elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
                    dt.ordem_classificacao_resultado_final = ordem
                dt.save()
                # Se for empate permanece a mesma ordem/classificacao do anterior
                # if not dt.empatado:
                #    ordem += 1
                ordem += 1

        calcular_ordem_classificacao(processamento, dados_taes)
        calcular_ordem_classificacao(processamento, dados_docentes)

        # --------------------
        # Se teve intervencao da gestao na classificacao
        # Recalcula ordem de classificacao para cada pedido considerando
        # - ordem_classificacao_resultado_parcial_gestao E
        # - ordem_classificacao_resultado_final_gestao
        # --------------------
        dados_taes = ProcessamentoEdital.get_dados_processamento(processamento, 'tae')
        dados_docentes = ProcessamentoEdital.get_dados_processamento(processamento, 'docente')

        def reordenar(processamento, lista_com_ordem_gestao, lista_sem_ordem_gestao):
            # Cria nova lista ordenada com base nas listas sem_ordem_gestao e com_ordem_gestao

            nova_lista_ordenada = []
            qtd_dados = lista_sem_ordem_gestao.count()
            ordem = 1
            i = 0
            while i < qtd_dados:
                if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                    elemento_com_ordem_gestao = lista_com_ordem_gestao.filter(ordem_classificacao_resultado_parcial_gestao=ordem)
                else:
                    elemento_com_ordem_gestao = lista_com_ordem_gestao.filter(ordem_classificacao_resultado_final_gestao=ordem)
                if elemento_com_ordem_gestao:
                    nova_lista_ordenada.append(elemento_com_ordem_gestao[0].pedido.id)
                else:
                    nova_lista_ordenada.append(lista_sem_ordem_gestao[i].pedido.id)
                    i += 1
                ordem += 1

            # Ordena os pedidos da planilha
            ordem = 1
            i = 0
            for np in nova_lista_ordenada:
                d = dados_taes.get(pedido=np)
                if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                    d.ordem_classificacao_resultado_parcial = ordem
                else:
                    d.ordem_classificacao_resultado_final = ordem
                d.save()
                ordem += 1
                i += 1

        if ProcessamentoEdital.existe_intervencao_da_gestao_na_classificacao(processamento):
            if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                # TAES
                lista_dados_taes_sem_ordem_gestao = dados_taes.filter(ordem_classificacao_resultado_parcial_gestao__isnull=True)
                lista_dados_taes_com_ordem_gestao = dados_taes.filter(ordem_classificacao_resultado_parcial_gestao__isnull=False)
                reordenar(processamento, lista_dados_taes_com_ordem_gestao, lista_dados_taes_sem_ordem_gestao)
                # DOCENTES
                lista_dados_docentes_sem_ordem_gestao = dados_docentes.filter(ordem_classificacao_resultado_parcial_gestao__isnull=True)
                lista_dados_docentes_com_ordem_gestao = dados_docentes.filter(ordem_classificacao_resultado_parcial_gestao__isnull=False)
                reordenar(processamento, lista_dados_docentes_com_ordem_gestao, lista_dados_docentes_sem_ordem_gestao)
            elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
                # TAES
                lista_dados_taes_sem_ordem_gestao = dados_taes.filter(ordem_classificacao_resultado_final_gestao__isnull=True)
                lista_dados_taes_com_ordem_gestao = dados_taes.filter(ordem_classificacao_resultado_final_gestao__isnull=False)
                reordenar(processamento, lista_dados_taes_com_ordem_gestao, lista_dados_taes_sem_ordem_gestao)
                # DOCENTES
                lista_dados_docentes_sem_ordem_gestao = dados_docentes.filter(ordem_classificacao_resultado_final_gestao__isnull=True)
                lista_dados_docentes_com_ordem_gestao = dados_docentes.filter(ordem_classificacao_resultado_final_gestao__isnull=False)
                reordenar(processamento, lista_dados_docentes_com_ordem_gestao, lista_dados_docentes_sem_ordem_gestao)

        # --------------------
        # Cria quadro paralelo para comparar com o quadro original
        # Preenche quadro paralelo com os dados originais
        # Preenche quadro paralelo com os dados dos pedidos desse processamento
        # ** DADOS JÁ ORDENADOS **
        # --------------------
        dados_taes = ProcessamentoEdital.get_dados_processamento(processamento, 'tae')
        dados_docentes = ProcessamentoEdital.get_dados_processamento(processamento, 'docente')
        QuadroPedidosTemporario.objects.all().delete()

        def criar_quadro_temporario(dados):
            for dps in dados:
                lista_datas = []
                for p in dps.pedido.get_lista_periodos_pedido():
                    qtd_dias = (p.data_termino - p.data_inicio).days + 1
                    lista_datas += [p.data_inicio + datetime.timedelta(days=x) for x in range(qtd_dias)]
                for d in lista_datas:
                    qvt = QuadroPedidosTemporario()
                    qvt.pedido = dps.pedido
                    qvt.quadro = LicCapacitacaoPorDia.objects.get(data=d)
                    qvt.save()

        criar_quadro_temporario(dados_taes)
        criar_quadro_temporario(dados_docentes)

        # --------------------
        # Calcula se cada solicitacao atende ou nao aos limites definidos em
        # - Edital.percentual_limite_servidores_em_lic_capacitacao
        # - Edital.qtd_limite_servidores_em_lic_capacitacao_por_dia
        # - Edital.qtd_limite_taes_em_lic_capacitacao_por_dia
        # - Edital.qtd_limite_docentes_em_lic_capacitacao_por_dia
        # Pega a planilha em ordem e verifica se alguma data desse pedido esta conflito com
        # algum pedido anterior
        # - Marca como aprovado ou nao
        # - Coloca justificativa
        # ** DADOS JÁ ORDENADOS **
        # --------------------
        dados_taes = ProcessamentoEdital.get_dados_processamento(processamento, 'tae')
        dados_docentes = ProcessamentoEdital.get_dados_processamento(processamento, 'docente')

        qtd_limite_taes = processamento.edital.qtd_limite_taes_em_lic_capacitacao_por_dia
        qtd_limite_docentes = processamento.edital.qtd_limite_docentes_em_lic_capacitacao_por_dia

        # TAES
        for dt in dados_taes:
            qts_do_pedido = QuadroPedidosTemporario.objects.filter(pedido=dt.pedido)

            # Verificando dia a dia se esta ou nao no limite
            # - todos os dias do pedido no quadro temporario
            lista_datas_fora_do_limite = []
            for d in qts_do_pedido:
                # pedidos anteriores ao pedido de d
                qts_anteriores_ao_pedido = QuadroPedidosTemporario.objects.filter(
                    pedido__eh_tecnico_administrativo=True, id__lt=d.id, quadro__data=d.quadro.data
                )
                qtd_qts_anteriores_ao_pedido = qts_anteriores_ao_pedido.count()

                # qtd totol de licenciados no quadro geral no mesmo dia de d
                qtd_total_quadro_oficial = d.quadro.qtd_taes_geral

                # verifica se o total de licenciados estoura o limite do dia
                total = qtd_qts_anteriores_ao_pedido + qtd_total_quadro_oficial
                if total >= qtd_limite_taes:
                    lista_datas_fora_do_limite.append(d.quadro.data)

            lista_datas_fora_do_limite_str = []
            for e in lista_datas_fora_do_limite:
                lista_datas_fora_do_limite_str.append(e.strftime('%d/%m/%Y'))
            just = (
                ' Foi atingido o limite de concessões de Licenças para Capacitação nas datas a seguir devido '
                'à pré-aprovação de pedido de servidor com priorização '
                'superior: '
            )
            just += ', '.join(lista_datas_fora_do_limite_str)
            if lista_datas_fora_do_limite_str:
                if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                    dt.justificativa_nao_aprovacao_resultado_parcial = just
                elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
                    dt.justificativa_nao_aprovacao_resultado_final = just
                dt.save()

        # DOCENTES
        for dt in dados_docentes:
            qts_do_pedido = QuadroPedidosTemporario.objects.filter(pedido=dt.pedido)

            # Verificando dia a dia se esta ou nao no limite
            # - todos os dias do pedido no quadro temporario
            lista_datas_fora_do_limite = []
            for d in qts_do_pedido:
                # pedidos anteriores ao pedido de d
                qts_anteriores_ao_pedido = QuadroPedidosTemporario.objects.filter(pedido__eh_docente=True, id__lt=d.id, quadro__data=d.quadro.data)
                qtd_qts_anteriores_ao_pedido = qts_anteriores_ao_pedido.count()

                # qtd totol de licenciados no quadro geral no mesmo dia de d
                qtd_total_quadro_oficial = d.quadro.qtd_docentes_geral

                # verifica se o total de licenciados estoura o limite do dia
                total = qtd_qts_anteriores_ao_pedido + qtd_total_quadro_oficial
                if total >= qtd_limite_docentes:
                    lista_datas_fora_do_limite.append(d.quadro.data)

            lista_datas_fora_do_limite_str = []
            for e in lista_datas_fora_do_limite:
                lista_datas_fora_do_limite_str.append(e.strftime('%d/%m/%Y'))
            just = (
                ' Foi atingido o limite de concessões de Licenças para Capacitação nas datas a seguir devido '
                'à pré-aprovação de pedido de servidor com priorização '
                'superior: '
            )
            just += ', '.join(lista_datas_fora_do_limite_str)
            if lista_datas_fora_do_limite_str:
                if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                    dt.justificativa_nao_aprovacao_resultado_parcial = just
                elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
                    dt.justificativa_nao_aprovacao_resultado_final = just
                dt.save()

        # --------------------
        # Aprovado ou reprovado
        # ** DADOS JÁ ORDENADOS **
        # --------------------
        task.update_progress(90)
        dados = ProcessamentoEdital.get_dados_processamento(processamento)

        # TAES e DOCENTES
        for dt in dados:
            if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                if dt.justificativa_nao_aprovacao_resultado_parcial:
                    dt.aprovado_resultado_parcial = False
                else:
                    dt.aprovado_resultado_parcial = True
                dt.save()
            elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
                if dt.justificativa_nao_aprovacao_resultado_final:
                    dt.aprovado_resultado_final = False
                else:
                    dt.aprovado_resultado_final = True
                dt.save()

        return None

    @staticmethod
    def get_inicio_exercicio(edital, servidor):
        calc = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
        return calc.inicio_exercicio

    @staticmethod
    def get_qtd_dias_total_licenca_capacitacao_utilizada(edital, servidor):
        calcs = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor)
        qsiap = calcs.aggregate(qtd=Sum('qtd_dias_lc_siape'))['qtd']
        qsuap = calcs.aggregate(qtd=Sum('qtd_dias_lc_suap'))['qtd']
        return qsiap + qsuap

    @staticmethod
    def get_periodo_aquisitivo_proximo_do_fim(edital, servidor):
        calc = (
            CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor, ativo_pelo_edital=True)
            .order_by('inicio_aquisitivo')
            .first()
        )
        return calc.final_aquisitivo_na_patrica

    @staticmethod
    def get_qtd_dias_efetivo_exercicio(edital, servidor):
        calc = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
        return calc.qtd_dias_efet_exercicio

    @staticmethod
    def get_qtd_dias_afastamento_capacitacao(edital, servidor):
        calc = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
        return calc.qtd_dias_afast_capacitacao

    @staticmethod
    def get_qtd_dias_afast_nao_conta_como_efet_exerc(edital, servidor):
        calc = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
        return calc.qtd_dias_afast_nao_conta_como_efet_exerc

    @staticmethod
    def get_idade_servidor_inicio_abrangencia_edital(edital, servidor):
        calc = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
        return calc.idade_servidor_inicio_abrangencia_edital

    @staticmethod
    def get_ordem_classificacao_resultado_final_gestao(edital, servidor):
        calc = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).first()
        return calc.idade_servidor_inicio_abrangencia_edital

    @staticmethod
    @transaction.atomic()
    def pode_desfinalizar_processamento(user, processamento, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao (se ainda pode receber sumissao)
        # ----------------------------
        if not processamento.edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar processamento de um edital que não está em andamento.')
            else:
                return False

        # So altera se estiver finalizado
        # ----------------------------
        if not processamento.finalizado:
            if lancar_excecao:
                raise ValidationError('Impossível desfinalizar processamento não finalizado.')
            else:
                return False

        # So pode desfinalizar o ultimo processamento final
        ultimo_processamento = ProcessamentoEdital.objects.filter(edital=processamento.edital).order_by('-id').first()
        if ultimo_processamento.id != processamento.id:
            if lancar_excecao:
                raise ValidationError('Só é possível desfinalizar o último processamento do edital.')
            else:
                return False

        """
        # So pode desfinalizar um processamento se nao existir algum processamento
        # final finalizado já de forma definitiva
        # - Exceto se o processamento que deseja desfinalizar for o processamento definitivo=True
        if ProcessamentoEdital.objects.filter(edital=processamento.edital,
                                              tipo_processamento=ProcessamentoEdital.PROCESSAMENTO_FINAL,
                                              definitivo=True).exists():
            if lancar_excecao:
                raise ValidationError(
                    'Impossível desfinalizar um processamento se já tiver um processamento final finalizado de forma definitiva.')
            else:
                return False
        if not processamento.definitivo:
            if lancar_excecao:
                raise ValidationError(
                    'Impossível desfinalizar um processamento sem que o parcial ou final definitivos seja .')
            else:
                return False
        """

        return True

    @staticmethod
    @transaction.atomic()
    def pode_descancelar_processamento(user, processamento, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao (se ainda pode receber sumissao)
        # ----------------------------
        if not processamento.edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar processamento de um edital que não está em andamento.')
            else:
                return False

        # So altera se estiver finalizado
        # ----------------------------
        if not processamento.cancelado:
            if lancar_excecao:
                raise ValidationError('Impossível descancelar processamento não cancelado.')
            else:
                return False

        return True

    @staticmethod
    @transaction.atomic()
    def pode_finalizar_processamento(user, processamento, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode finalizar processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao (se ainda pode receber sumissao)
        # ----------------------------
        if not processamento.edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível finalizar processamento de um edital que não está em andamento.')
            else:
                return False

        # So altera se processamento nao finalizado e nao cancelado
        # ----------------------------
        if processamento.finalizado or processamento.cancelado:
            if lancar_excecao:
                raise ValidationError('Impossível finalizar processamento que esteja cancelado ou finalizado...')
            else:
                return False

        return True

    @staticmethod
    @transaction.atomic()
    def finalizar_processamento(user, processamento):
        ProcessamentoEdital.pode_finalizar_processamento(user, processamento, True)
        processamento.finalizado = True
        processamento.data_hora_finalizacao = datetime.datetime.now()
        processamento.save()

    @staticmethod
    @transaction.atomic()
    def desfinalizar_processamento(user, processamento):
        # Se já foi setado como definitivo desfaz isso e também o resultado colocado no pedido
        era_definitivo = processamento.definitivo

        # Desfinaliza
        ProcessamentoEdital.pode_desfinalizar_processamento(user, processamento, True)
        processamento.finalizado = False
        processamento.definitivo = False
        processamento.save()

        if era_definitivo:
            dados = ProcessamentoEdital.get_dados_processamento(processamento)
            if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
                for d in dados:
                    # Resultado parcial ---
                    d.pedido.aprovado_resultado_parcial = None
                    d.pedido.justificativa_nao_aprovacao_resultado_parcial = None
                    d.pedido.ordem_classificacao_resultado_parcial = 0
                    d.pedido.ordem_classificacao_resultado_parcial_gestao = 0
                    d.pedido.aprovado_em_definitivo = False
                    #
                    d.save()
                    d.pedido.save()
            elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
                for d in dados:
                    # Resultado final ---
                    d.pedido.aprovado_resultado_final = None
                    d.pedido.justificativa_nao_aprovacao_resultado_final = None
                    d.pedido.ordem_classificacao_resultado_final = 0
                    d.pedido.ordem_classificacao_resultado_final_gestao = 0
                    d.pedido.aprovado_em_definitivo = False
                    #
                    d.save()
                    d.pedido.save()

    @staticmethod
    @transaction.atomic()
    def cancelar_processamento(user, processamento):
        ProcessamentoEdital.pode_editar(user, processamento, True)

        processamento.cancelado = True
        processamento.save()

    @staticmethod
    @transaction.atomic()
    def descancelar_processamento(user, processamento):
        ProcessamentoEdital.pode_descancelar_processamento(user, processamento, True)

        processamento.cancelado = False
        processamento.save()

    @staticmethod
    @transaction.atomic()
    def pode_definir_processamento_definitivo(user, processamento, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao (se ainda pode receber sumissao)
        # ----------------------------
        if not processamento.edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar processamento de um edital que não está em andamento.')
            else:
                return False

        # So altera se estiver finalizado
        # ----------------------------
        if processamento.finalizado or processamento.cancelado:
            if lancar_excecao:
                raise ValidationError('Impossível tornar DEFINITIVO um processamento que esteja finalizado ou cancelado.')
            else:
                return False

        # Só é possível se nao tiver um PARCIAL ou FINAL já marcado como DEFINITIVO
        if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
            if ProcessamentoEdital.objects.filter(
                edital=processamento.edital, tipo_processamento=ProcessamentoEdital.PROCESSAMENTO_FINAL, definitivo=True
            ).exists():
                if lancar_excecao:
                    raise ValidationError(
                        'Impossível definir como DEFINITIVO um processamento FINAL se já tiver um outro parcial já definido como definitivo.'
                    )
                else:
                    return False
        elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            if ProcessamentoEdital.objects.filter(
                edital=processamento.edital, tipo_processamento=ProcessamentoEdital.PROCESSAMENTO_PARCIAL, definitivo=True
            ).exists():
                if lancar_excecao:
                    raise ValidationError(
                        'Impossível definir como DEFINITIVO um processamento PARCIAL se já tiver um outro final já definido como definitivo.'
                    )
                else:
                    return False

        return True

    @staticmethod
    @transaction.atomic()
    def pode_desfazer_definir_processamento_definitivo(user, processamento, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode editar processamento.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao (se ainda pode receber sumissao)
        # ----------------------------
        if not processamento.edital.estah_em_andamento():
            if lancar_excecao:
                raise ValidationError('Impossível editar processamento de um edital que não está em andamento.')
            else:
                return False

        # So altera se estiver finalizado
        # ----------------------------
        if not processamento.definitivo or processamento.finalizado or processamento.cancelado:
            if lancar_excecao:
                raise ValidationError('Impossível para um processamento que esteja finalizado ou cancelado.')
            else:
                return False

        return True

    @staticmethod
    @transaction.atomic()
    def definir_processamento_definitivo(user, processamento, desfazer=False):
        if desfazer:
            ProcessamentoEdital.pode_desfazer_definir_processamento_definitivo(user, processamento, True)
        else:
            ProcessamentoEdital.pode_definir_processamento_definitivo(user, processamento, True)

        processamento.definitivo = True
        if desfazer:
            processamento.definitivo = False
        processamento.save()

        # Ao definir um processamento como definitivo deve sicronizar o resultado
        # com PedidoLicCapacitacao
        dados = ProcessamentoEdital.get_dados_processamento(processamento)
        if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            for d in dados:
                # Resultado parcial ---
                if desfazer:
                    d.pedido.aprovado_resultado_parcial = None
                    d.pedido.justificativa_nao_aprovacao_resultado_parcial = None
                    d.pedido.ordem_classificacao_resultado_parcial = 0
                    d.pedido.ordem_classificacao_resultado_parcial_gestao = 0
                    d.pedido.aprovado_em_definitivo = False
                else:
                    d.pedido.aprovado_resultado_parcial = d.aprovado_resultado_parcial
                    d.pedido.justificativa_nao_aprovacao_resultado_parcial = d.justificativa_nao_aprovacao_resultado_parcial
                    d.pedido.ordem_classificacao_resultado_parcial = d.ordem_classificacao_resultado_parcial
                    d.pedido.ordem_classificacao_resultado_parcial_gestao = d.ordem_classificacao_resultado_parcial_gestao
                    d.pedido.aprovado_em_definitivo = False
                #
                d.save()
                d.pedido.save()
        elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
            for d in dados:
                # Resultado final ---
                if desfazer:
                    d.pedido.aprovado_resultado_parcial = None
                    d.pedido.justificativa_nao_aprovacao_resultado_parcial = None
                    d.pedido.ordem_classificacao_resultado_parcial = 0
                    d.pedido.ordem_classificacao_resultado_parcial_gestao = 0
                    d.pedido.aprovado_em_definitivo = False
                else:
                    d.pedido.aprovado_resultado_final = d.aprovado_resultado_final
                    d.pedido.justificativa_nao_aprovacao_resultado_final = d.justificativa_nao_aprovacao_resultado_final
                    d.pedido.ordem_classificacao_resultado_final = d.ordem_classificacao_resultado_final
                    d.pedido.ordem_classificacao_resultado_final_gestao = d.ordem_classificacao_resultado_final_gestao
                    d.pedido.aprovado_em_definitivo = True
                #
                d.save()
                d.pedido.save()

    @staticmethod
    def get_processamentos_finalizado_e_definitivos_do_edital_por_servidor(edital, servidor):
        return DadosProcessamentoEdital.objects.filter(
            processamento__edital=edital, processamento__finalizado=True, processamento__definitivo=True, pedido__servidor=servidor
        ).order_by('processamento__data_hora_cadastro')


class DadosProcessamentoEdital(models.ModelPlus):
    processamento = models.ForeignKeyPlus('licenca_capacitacao.ProcessamentoEdital', verbose_name='Processamento')
    pedido = models.ForeignKeyPlus('licenca_capacitacao.PedidoLicCapacitacao', verbose_name='Pedido')

    # Dados gerais
    # -----------------------------

    # Matrícula
    # pedido.servidor

    # Servidor
    # pedido.servidor

    # Categoria
    # pedido.servidor.categoria

    # Campus SUAP
    # pedido.servidor

    # Data iníc serv púb
    inicio_exercicio = models.DateFieldPlus('Início do exercício', null=True, blank=True)

    # Lic. Cap/ Início (data) -- do pedido
    # Lic. Cap/ Término (data)  -- do pedido
    def get_periodos_pedido(self):
        return self.pedido.get_lista_periodos_pedido()

    # Qtd dias -- do pedido
    def get_qtd_dias_periodos_pedido(self):
        return self.pedido.periodopedidoliccapacitacao_set.aggregate(qtd=Sum('qtd_dias_total'))['qtd']

    # Critérios de desempate
    # -----------------------------
    # - [CRITERIO DE DESEMPATE 1] Lic. Capac anterior (qtd de dias de licenca capacitacao
    #   usadas) (soma do qtd_dias_lc_siape+qtd_dias_lc_suap)
    #   - Criterio 1: "a. ter menos períodos aquisitivos de licença para capacitação utilizados"
    #     - Coluna: Utilizo a quantidade de dias de licença de capacitação já utilizado
    qtd_dias_total_licenca_capacitacao_utilizada = models.PositiveIntegerField('Quantidade de dias de licença capacitação já concedidas', default=0)

    # - [CRITERIO DE DESEMPATE 2] Per. aquisit fim (data)
    #   - Criterio 2: "b. período aquisitivo de quinquênio mais próximo a ser expirado (tempo
    #     em que se encontra no direito de usufruto do último período aquisitivo
    #     e sem ainda ter havido a concessão correspondente, considerando que
    #     não são acumuláveis);"
    #     - Coluna: Data final do periodo ativo para o edital
    periodo_aquisitivo_proximo_do_fim = models.DateFieldPlus('Período aquisitivo mais próximo do fim (data final)', null=True, blank=True)

    # - [CRITERIO DE DESEMPATE 3] Tempo de efetivo exercicio -- nova coluna criada pela
    #   verificacao
    #   - Criterio 3: "c. maior tempo de efetivo exercício;"
    #     - Coluna: utilizo a quantidade de dias de efetivo exercício considerando
    qtd_dias_efetivo_exercicio = models.PositiveIntegerField('Quantidade de dias de efetivo exercício', default=0)

    # - [CRITERIO DE DESEMPATE 4] Afast. pósgraduç (qtd de dias)
    #   - Criterio 4: "d. ter menos períodos de afastamentos para pós-graduação stricto sensu
    #     no País ou no exterior;"
    #     - Coluna: SIM, utilizo a quantidade de dias do referido afastamento.
    qtd_dias_afastamento_capacitacao = models.PositiveIntegerField('Quantidade de dias de afastamento capacitação', default=0)

    # - [CRITERIO DE DESEMPATE 5] Afast. assunt partic./acom p. cônjuge
    #    (qtd de dias) -- qtd de dias de afast q nao contam como efet exerc
    #   - Criterio 5: "e. ter menos períodos de afastamento por licença para tratar de
    #      assuntos particulares;"
    #     - Coluna: SIM, utilizo a quantidade de dias do referido afastamento.
    qtd_dias_afast_nao_conta_como_efet_exerc = models.PositiveIntegerField(
        'Quantidade de dias que não contabilizam como efetivo exercício', default=0
    )

    # - [CRITERIO DE DESEMPATE 6]  Idade do servidor no momento no dia de inicio da abrangencia
    #   - Criterio 6: "f. idade, tendo preferência o servidor de maior idade;"
    #     - Coluna: Resposta: Utilize como referêncial uma data única para todos.
    #       Por exemplo, a data de início do período de abrangência do edital.
    #       (referencial flexível de acordo com o evento não deve utilizar)
    idade_servidor_inicio_abrangencia_edital = models.PositiveIntegerField('Idade do servidor (no início da abrangência do edital)', default=0)

    # Resultado parcial
    aprovado_resultado_parcial = models.BooleanField(verbose_name='Aprovado no Resultado Parcial', null=True)
    justificativa_nao_aprovacao_resultado_parcial = models.TextField('Justificativa de não aprovação no Resultado Parcial', null=True, blank=True)
    ordem_classificacao_resultado_parcial = models.PositiveIntegerField('Ordem de classificação no Resultado Parcial', null=True, blank=True)
    ordem_classificacao_resultado_parcial_gestao = models.PositiveIntegerField(
        'Ordem de classificação no Resultado Parcial (gestão)', null=True, blank=True
    )

    # Resultado final
    aprovado_resultado_final = models.BooleanField(verbose_name='Aprovado no Resultado Final', null=True)
    justificativa_nao_aprovacao_resultado_final = models.TextField('Justificativa de não aprovação no Resultado Final', null=True, blank=True)
    ordem_classificacao_resultado_final = models.PositiveIntegerField('Ordem de classificação no Resultado Final', null=True, blank=True)
    ordem_classificacao_resultado_final_gestao = models.PositiveIntegerField(
        'Ordem de classificação no Resultado Final (gestão)', null=True, blank=True
    )

    empatado = models.BooleanField(verbose_name='Empatado', null=True)

    tem_erro_checklist = models.BooleanField(verbose_name='Erro no checklist', null=True)

    @staticmethod
    @transaction.atomic()
    def editar_ordem_classificacao_gestao(user, dado_processamento_edital, nova_ordem_classificacao_gestao):
        processamento = dado_processamento_edital.processamento

        ProcessamentoEdital.pode_editar(user, processamento, True)

        if processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_PARCIAL:
            dado_processamento_edital.ordem_classificacao_resultado_parcial_gestao = nova_ordem_classificacao_gestao
        elif processamento.tipo_processamento == ProcessamentoEdital.PROCESSAMENTO_FINAL:
            dado_processamento_edital.ordem_classificacao_resultado_final_gestao = nova_ordem_classificacao_gestao

        dado_processamento_edital.save()


class QuadroPedidosTemporario(models.ModelPlus):
    quadro = models.ForeignKeyPlus('licenca_capacitacao.LicCapacitacaoPorDia', verbose_name='Quadro original')
    pedido = models.ForeignKeyPlus('licenca_capacitacao.PedidoLicCapacitacao', verbose_name='Pedido')


class SolicitacaoAlteracaoDataInicioExercicio(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')

    data_cadastro = models.DateTimeFieldPlus('Data de cadastro da solicitação', editable=False, auto_now_add=True)

    SITUACAO_SOLICITACAO_DEFERIDO = 1
    SITUACAO_SOLICITACAO_INDEFERIDO = 2
    SITUACAO_SOLICITACAO_CHOICES = [[SITUACAO_SOLICITACAO_DEFERIDO, 'DEFERIDA'], [SITUACAO_SOLICITACAO_INDEFERIDO, 'INDEFERIDA']]
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_SOLICITACAO_CHOICES, null=True)

    pode_analisar = models.BooleanField('Pode analisar', default=False)

    # Solicitação
    # -------------------
    justificativa = models.TextField('Justificativa da solicitação')
    data_suap = models.DateFieldPlus('Data obtida no SUAP pelo módulo de licença capacitação')
    data_solicitada = models.DateFieldPlus('Data solicitada')

    # Parecer
    # -------------------
    parecer_gestao = models.TextField('Parecer/observações da gestão', null=True, blank=True)
    data_hora_parecer = models.DateTimeFieldPlus('Data/hora do parecer', null=True, blank=True)
    usuario_parecer = models.ForeignKeyPlus('comum.User', verbose_name='Usuário do parecer', null=True)
    data_informada_parecer = models.DateFieldPlus('Data de início de exercício informada pela gestão', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Alteração de Data de início de exercício'
        verbose_name_plural = 'Solicitações de Alteração de Data de início de exercício'

    def __str__(self):
        return f'{self.servidor}'

    def get_situacao_html(self):
        if self.situacao == 1:
            retorno = '<span class="status status-success">DEFERIDO</span>'
        elif self.situacao == 2:
            retorno = '<span class="status status-error">INDEFERIDO</span>'
        elif not EditalLicCapacitacao.existe_somente_pedidos_cancelados_do_servidor_no_edital(self.edital, self.servidor):
            retorno = '<span class="status status-alert">ENVIO CANCELADO</span>'
        elif not self.pode_analisar:
            retorno = '<span class="status status-alert">PENDENTE DE ENVIO</span>'
        else:
            retorno = '<span class="status status-info">PENDENTE DE ANÁLISE</span>'
        return format_html(retorno)

    get_situacao_html.short_description = 'Situação'

    def clean(self):
        if self.situacao == SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_INDEFERIDO:
            if not self.data_informada_parecer:
                raise ValidationError('Para indeferir deve-se informar uma "Data de início de exercício informada pela gestão" para INDEFERIMENTO.')
            if not self.parecer_gestao:
                raise ValidationError('Para indeferir deve-se informar o "Parecer/observações da gestão".')

        try:
            SolicitacaoAlteracaoDataInicioExercicio.pode_analisar_solicitacao_alteracao_dt_inicio_exercicio(self.usuario_parecer, self.edital, True)
        except Exception as e:
            raise ValidationError(f'{get_e(e)}')

        # atualiza os dados ajustados do servidor
        dt_valida = None
        if self.situacao == SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_DEFERIDO:
            dt_valida = self.data_solicitada
        if self.situacao == SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_INDEFERIDO:
            dt_valida = self.data_informada_parecer
        if dt_valida:
            ServidorDataInicioExercicioAjustada.ajustar(self.servidor, dt_valida, self.usuario_parecer, self)

    @staticmethod
    def pode_analisar_solicitacao_alteracao_dt_inicio_exercicio(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode analisar pedidos de alteração de data de início de exercício.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        # Usa método centralizado do edital que considera a configuração.
        if not edital.permite_analise_solicitacoes():
            if lancar_excecao:
                raise ValidationError(
                    'Não é possível analisar pedidos de alteração de data de início de exercício para um edital que não está em andamento.'
                )
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível analisar pedidos de alteração de data de início de exercício para um edital sem pedidos.')
            else:
                return False

        if EditalLicCapacitacao.existe_algum_processamento_no_edital(edital):
            if lancar_excecao:
                raise ValidationError(
                    'Impossível analisar uma solicitação de alteração de data de início de exercício para um '
                    'edital que possui algum processamento cadastrado.'
                )
            else:
                return False

        return True


class SolicitacaoAlteracaoDataInicioExercicioAdicionar(SolicitacaoAlteracaoDataInicioExercicio):
    class Meta:
        proxy = True
        verbose_name = 'Adicionar Solicitação de Alteração de Data de início de exercício'
        verbose_name_plural = 'Adicionar Solicitações de Alteração de Data de início de exercício'

    def clean(self):
        if self.data_suap == self.data_solicitada:
            raise ValidationError(
                'Para solicitar alteração de data de início de exercício '
                'é necessário solicitar para uma data diferente da obtida '
                'no SUAP pelo módulo de licença capacitação.'
            )

        try:
            SolicitacaoAlteracaoDataInicioExercicioAdicionar.pode_solicitar(self.servidor.get_user(), self.edital, True)
        except Exception as e:
            raise ValidationError(f'{e}')

    @staticmethod
    def pode_solicitar(user, edital, lancar_excecao=False):
        # Se pode solicitar alteracao de data de inicio de exercicio
        # --------------------------------

        # Só pode se o edital ainda aceitar cadastro/submissao e pedido
        if not edital.pode_cadastrar_pedido(user, False):
            if lancar_excecao:
                raise ValidationError('Impossível solicitar alteração de data de início de exercício para um edital que não possa receber pedidos.')
            else:
                return False

        # Só pode se o servidor nao possui pedidos já submetidos neste edital
        if EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(edital, user.get_relacionamento()):
            if lancar_excecao:
                raise ValidationError(
                    'Impossível solicitar alteração de data de início de exercício para '
                    'um edital que o servidor já tenha submetido ao menos um pedido.'
                )
            else:
                return False

        # Se ja existe uma outra solicitacao de alteracao de dt de ini exerc nao pode
        #  cadastrar uma nova
        if SolicitacaoAlteracaoDataInicioExercicioAdicionar.objects.filter(edital=edital, servidor=user.get_relacionamento()).exists():
            if lancar_excecao:
                raise ValidationError('Impossível solicitar alteração de data de início de exercício se já houver uma solicitação para este edital.')
            else:
                return False

        # So pode cadastrar se o servidor tiver cadastrado algum pedido
        if not EditalLicCapacitacao.existe_algum_pedido_do_servidor_no_edital(edital, user.get_relacionamento()):
            if lancar_excecao:
                raise ValidationError('Não existem pedidos submetidos pelo servidor para este edital.')
            else:
                return False

        # So pode cadastrar se ainda não existe uma ServidorDataInicioExercicioAjustada cadastrada
        #   para este servidor
        if ServidorDataInicioExercicioAjustada.objects.filter(servidor=user.get_relacionamento()).exists():
            if lancar_excecao:
                raise ValidationError('Impossível cadastrar se já houver data ajustada cadastrada.')
            else:
                return False

        return True

    @staticmethod
    def get_solicitacoes_servidor_no_edital(edital, servidor):
        return SolicitacaoAlteracaoDataInicioExercicioAdicionar.objects.filter(edital=edital, servidor=servidor)

    @staticmethod
    def pode_excluir(user, edital, lancar_excecao=False):
        # Se pode solicitar alteracao de data de inicio de exercicio
        # --------------------------------

        # Se o edital aceita pedido
        if not edital.pode_cadastrar_pedido(user, False):
            if lancar_excecao:
                raise ValidationError(
                    'Impossível excluir uma solicitação alteração de data de início de exercício para um edital que não possa receber pedidos.'
                )
            else:
                return False

        if EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(edital, user.get_relacionamento()):
            if lancar_excecao:
                raise ValidationError('Impossível solicitar alteração de dados para um edital que o servidor já tenha submetido ao menos um pedido.')
            else:
                return False

        return True


class SolicitacaoAlteracaoDados(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')

    data_cadastro = models.DateTimeFieldPlus('Data de cadastro da solicitação', editable=False, auto_now_add=True)

    SITUACAO_SOLICITACAO_DEFERIDO = 1
    SITUACAO_SOLICITACAO_INDEFERIDO = 2
    SITUACAO_SOLICITACAO_CHOICES = [[SITUACAO_SOLICITACAO_DEFERIDO, 'DEFERIDA'], [SITUACAO_SOLICITACAO_INDEFERIDO, 'INDEFERIDA']]
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_SOLICITACAO_CHOICES, null=True)
    pode_analisar = models.BooleanField('Pode analisar', default=False)

    # Solicitação
    # -------------------
    justificativa = models.TextField('Justificativa da solicitação')

    # Parecer
    # -------------------
    parecer_gestao = models.TextField('Parecer/observações da gestão', null=True, blank=True)
    data_hora_parecer = models.DateTimeFieldPlus('Data/hora do parecer', null=True, blank=True)
    usuario_parecer = models.ForeignKeyPlus('comum.User', verbose_name='Usuário do parecer', null=True)

    class Meta:
        verbose_name = 'Solicitação de Alteração de Dados'
        verbose_name_plural = 'Solicitações de Alteração de Dados'

    def __str__(self):
        return f'{self.servidor}'

    def get_situacao_html(self):
        if self.situacao == 1:
            retorno = '<span class="status status-success">DEFERIDO</span>'
        elif self.situacao == 2:
            retorno = '<span class="status status-error">INDEFERIDO</span>'
        elif not EditalLicCapacitacao.existe_somente_pedidos_cancelados_do_servidor_no_edital(self.edital, self.servidor):
            retorno = '<span class="status status-alert">ENVIO CANCELADO</span>'
        elif not self.pode_analisar:
            retorno = '<span class="status status-alert">PENDENTE DE ENVIO</span>'
        else:
            retorno = '<span class="status status-info">PENDENTE DE ANÁLISE</span>'
        return format_html(retorno)

    get_situacao_html.short_description = 'Situação'

    def clean(self):
        if self.situacao == SolicitacaoAlteracaoDataInicioExercicio.SITUACAO_SOLICITACAO_INDEFERIDO:
            if not self.parecer_gestao:
                raise ValidationError('Para indeferir deve-se informar o "Parecer/observações da gestão".')

        try:
            SolicitacaoAlteracaoDados.pode_analisar_solicitacao_alteracao(self.usuario_parecer, self.edital, True)
        except Exception as e:
            raise ValidationError(f'{e}')

        self.data_hora_parecer = datetime.datetime.now()

    @staticmethod
    def pode_analisar_solicitacao_alteracao(user, edital, lancar_excecao=False):
        # Verifica se este usuário pode
        # ----------------------------
        if not EditalLicCapacitacao.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Apenas a gestão pode analisar pedidos de alteração de data de início de exercício.')
            else:
                return False

        # Verifica se este edital já finalizou seu periodo de submissao
        # (se nao pode mais receber sumissao)
        # ----------------------------
        # Usa método centralizado do edital que considera a configuração.
        if not edital.permite_analise_solicitacoes():
            if lancar_excecao:
                raise ValidationError('Impossível analisar pedidos de alteração de dados para um edital que não está em andamento.')
            else:
                return False

        # Verifica se existem pedidos que podem ser processados
        # ----------------------------
        if not PedidoLicCapacitacao.get_pedidos_para_processamento(edital).exists():
            if lancar_excecao:
                raise ValidationError('Impossível analisar pedidos de alteração de dados para um edital sem pedidos.')
            else:
                return False

        if EditalLicCapacitacao.existe_algum_processamento_no_edital(edital):
            if lancar_excecao:
                raise ValidationError(
                    'Impossível analisar uma solicitação de alteração de dados para um edital que possui algum processamento cadastrado.'
                )
            else:
                return False

        return True


class SolicitacaoAlteracaoDadosAdicionar(SolicitacaoAlteracaoDados):
    class Meta:
        proxy = True
        verbose_name = 'Adicionar Solicitação de Alteração de Dados'
        verbose_name_plural = 'Adicionar Solicitações de Alteração de Dados'

    def clean(self):
        try:
            SolicitacaoAlteracaoDadosAdicionar.pode_solicitar(self.servidor.get_user(), self.edital, True)
        except Exception as e:
            raise ValidationError(f'{e}')

    @staticmethod
    def pode_solicitar(user, edital, lancar_excecao=False):
        # Se pode solicitar alteracao de dado
        # --------------------------------

        # Se o edital aceita pedido
        if not edital.pode_cadastrar_pedido(user, False):
            if lancar_excecao:
                raise ValidationError('Impossível solicitar alteração de dados para um  edital que não possa receber pedidos.')
            else:
                return False

        # Edital não possui pedidos
        if not EditalLicCapacitacao.existe_algum_pedido_do_servidor_no_edital(edital, user.get_relacionamento()):
            if lancar_excecao:
                raise ValidationError('Não existem pedidos submetidos pelo servidor para este edital.')
            else:
                return False

        # Se pelo o menos um dos pedidos foi submetido
        if EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(edital, user.get_relacionamento()):
            if lancar_excecao:
                raise ValidationError('Impossível solicitar alteração de dados para um edital que o servidor já tenha submetido ao menos um pedido.')
            else:
                return False

        return True

    @staticmethod
    def get_solicitacoes_servidor_no_edital(edital, servidor):
        return SolicitacaoAlteracaoDadosAdicionar.objects.filter(edital=edital, servidor=servidor)

    @staticmethod
    def pode_excluir(user, edital, lancar_excecao=False):
        if not edital.pode_cadastrar_pedido(user, False):
            if lancar_excecao:
                raise ValidationError('Impossível excluir uma solicitação alteração de dados para um edital que não possa receber pedidos.')
            else:
                return False

        if EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(edital, user.get_relacionamento()):
            if lancar_excecao:
                raise ValidationError('Impossível solicitar alteração de dados para um edital que o servidor já tenha submetido ao menos um pedido.')
            else:
                return False

        return True


class ServidorDataInicioExercicioAjustada(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    data_do_ajuste = models.DateFieldPlus('Data do ajuste', editable=False)

    data_inicio_exercicio = models.DateFieldPlus('Data de início de exercício ajustada')
    usuario_ajuste = models.ForeignKeyPlus('comum.User', verbose_name='Usuário responsável pelo ajuste', editable=False)

    solicitacao_alteracao = models.ForeignKeyPlus(
        'licenca_capacitacao.SolicitacaoAlteracaoDataInicioExercicio', verbose_name='Solicitação de alteração', editable=False, null=True
    )

    class Meta:
        verbose_name = 'Ajuste de data de início de exercício'
        verbose_name_plural = 'Ajustes de data de início de exercício'
        unique_together = ('servidor',)

    def __str__(self):
        return f'{self.servidor} - {self.data_inicio_exercicio}'

    @staticmethod
    @transaction.atomic()
    def ajustar(servidor, data_inicio_exercicio, usuario_ajuste, solicitacao_alteracao):
        # - Utilizado pelo SolicitacaoAlteracaoDataInicioExercicio nos
        #   casos em que o servidor fizer solicitação de alteração
        # - Quando não houver solicitação a gestão vai cadastrar manualmente (usar admin pra isso)
        a = ServidorDataInicioExercicioAjustada.objects.filter(servidor=servidor)
        if a:
            a = a[0]
        else:
            a = ServidorDataInicioExercicioAjustada()
        a.servidor = servidor
        a.data_do_ajuste = datetime.datetime.now()
        a.data_inicio_exercicio = data_inicio_exercicio
        a.usuario_ajuste = usuario_ajuste
        a.solicitacao_alteracao = solicitacao_alteracao
        a.save()

    @staticmethod
    def get_data_ajustada(servidor):
        a = ServidorDataInicioExercicioAjustada.objects.filter(servidor=servidor)
        if a:
            return a[0].data_inicio_exercicio
        else:
            return None

    def clean(self):
        # Nao pode cadastrar se tiver uma SolicitacaoAlteracaoDataInicioExercicio nao analisada
        # - situacao == None
        if SolicitacaoAlteracaoDataInicioExercicio.objects.filter(servidor=self.servidor, situacao__isnull=True, pode_analisar=True).exists():
            raise ValidationError(
                'Impossível cadastrar uma data ajustada se o servidor tiver alguma '
                'solicitação de alteração de data de início de exercício que ainda '
                'não foi analisada.'
            )


class ServidorComplementar(models.ModelPlus):
    edital = models.ForeignKeyPlus('licenca_capacitacao.EditalLicCapacitacao', verbose_name='Edital')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    categoria = models.CharField(
        max_length=30, choices=[['docente', 'Docente'], ['tecnico_administrativo', 'Técnico-Administrativo']], default='tecnico_administrativo'
    )
    data_cadastro = models.DateTimeFieldPlus('Data de cadastro', auto_now_add=True)
    justificativa = models.TextField('Justificativa')

    class Meta:
        verbose_name = 'Servidor Complementar'
        verbose_name_plural = 'Servidores Complementares'
        unique_together = ('edital', 'servidor')

    def __str__(self):
        return f'{self.edital} - {self.servidor}'

    @staticmethod
    def pode_cadastrar(user, edital, lancar_excecao=False):
        if not edital.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Somente a gestão pode cadastrar servidores complementares.')
            else:
                return False

        if edital.ativo:
            if lancar_excecao:
                raise ValidationError('Só pode cadastrar para editais inativos')
            else:
                return False

        if edital.periodo_submissao_inscricao_final and not (datetime.datetime.now() <= edital.periodo_submissao_inscricao_final):
            if lancar_excecao:
                raise ValidationError('Não pode cadastrar para editais já passaram o período de submissão')
            else:
                return False

        return True

    @staticmethod
    def pode_visualizar(user, edital, lancar_excecao=False):
        if not edital.eh_perfil_gestao(user):
            if lancar_excecao:
                raise ValidationError('Somente a gestão pode cadastrar servidores complementares.')
            else:
                return False

        if edital.periodo_submissao_inscricao_final and not (datetime.datetime.now() <= edital.periodo_submissao_inscricao_final):
            if lancar_excecao:
                raise ValidationError('Não pode exibir para editais já passaram o período de submissão')
            else:
                return False

        return True


class CodigoLicencaCapacitacao(models.ModelPlus):
    codigo = models.ForeignKeyPlus('rh.AfastamentoSiape', verbose_name='Código de Licença Capacitação')

    class Meta:
        verbose_name = 'Código de Licença Capacitação'
        verbose_name_plural = 'Códigos de Licença Capacitação'

    def __str__(self):
        return f'{self.codigo}'


class CodigoAfastamentoCapacitacao(models.ModelPlus):
    codigo = models.ForeignKeyPlus('rh.AfastamentoSiape', verbose_name='Código de Afastamento Capacitação')

    class Meta:
        verbose_name = 'Código de Afastamento Capacitação'
        verbose_name_plural = 'Códigos de Afastamento Capacitação'

    def __str__(self):
        return f'{self.codigo}'


class CodigoAfastamentoNaoContabilizaExercicio(models.ModelPlus):
    codigo = models.ForeignKeyPlus('rh.AfastamentoSiape', verbose_name='Código de afastamentos que não contabilizam como efetivo exercício')

    class Meta:
        verbose_name = 'Código de afastamentos que não contabilizam como efetivo exercício'
        verbose_name_plural = 'Códigos de afastamentos que não contabilizam como efetivo exercício'

    def __str__(self):
        return f'{self.codigo}'


class SituacaoContabilizaExercicio(models.ModelPlus):
    codigo = models.ForeignKeyPlus('rh.Situacao', verbose_name='Situação que contabiliza como efetivo exercício')

    class Meta:
        verbose_name = 'Situação que contabiliza como efetivo exercício'
        verbose_name_plural = 'Situações que contabilizam como efetivo exercício'

    def __str__(self):
        return f'{self.codigo}'
