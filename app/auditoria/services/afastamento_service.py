from calendar import monthrange
from datetime import date

from django.db import transaction
from django.db.models import QuerySet

from djtools.utils import DateInterval
from ferias.models import Ferias, ParcelaFerias
from rh.models import ServidorAfastamento
from rh.models.afastamento import AfastamentoSiape

from ..models import AfastamentoPlanejado, PlanejamentoAnual, StatusAfastamento, TipoAfastamento
from ..utils import dias_uteis_auditoria, horas_afastadas_no_periodo


class AfastamentoService:
    def __init__(self, planejamento: PlanejamentoAnual):
        self.planejamento = planejamento
        self.servidor = planejamento.auditor
        self.ano = planejamento.ano
        self.jornada = self.servidor.jornada_trabalho.get_jornada_trabalho_diaria()
        self.unidade = self.servidor.setor.uo

    @transaction.atomic
    def importar_afastamentos(self) -> dict:
        """Importa os afastamentos do SUAP e recalcula a carga horária do plano.

        Com a sincronização desligada no PAINT, as fontes externas não são
        consultadas e os afastamentos já importados são preservados: a carga
        horária é recalculada apenas sobre o que já está no planejamento.
        """
        if not self.planejamento.paint.sincronizar_afastamentos_suap:
            return self._processar_consolidacao(ParcelaFerias.objects.none(), ServidorAfastamento.objects.none(), {})

        # Limpa consolidações anteriores
        self.remover_afastamentos_importados()

        # Busca dados fonte homologadas
        ferias = self._buscar_ferias()
        concedidos = self._buscar_concedidos()

        # Prepara tipos de afastamento
        tipos_dict = self._preparar_tipos_afastamento(ferias, concedidos)

        # Processa consolidação mês a mês
        return self._processar_consolidacao(ferias, concedidos, tipos_dict)

    @transaction.atomic
    def remover_afastamentos_importados(self) -> None:
        """Remove os afastamentos importados do SUAP."""
        AfastamentoPlanejado.objects.filter(
            planejamento__planejamento_anual=self.planejamento,
            importado=True,
        ).delete()

    def pode_consolidar(self) -> bool:
        """Verifica se pode ser consolidado."""
        return True

    def _buscar_ferias(self):
        """Busca as férias validadas do servidor no ano.

        Só férias validadas pela chefia são afastamento consolidado — as demais
        ainda podem mudar de data ou não acontecer. É o equivalente, do lado das
        férias, ao ``cancelado=False`` aplicado aos afastamentos do RH.
        """
        ini = date(self.ano, 1, 1)
        fim = date(self.ano, 12, 31)
        ferias_qs = ParcelaFerias.objects.filter(
            ferias__servidor=self.servidor,
            ferias__validado=Ferias.VALIDADO,
            data_inicio__lte=fim,
            data_fim__gte=ini,
        )
        return ferias_qs.select_related('ferias')

    def _buscar_concedidos(self):
        """Busca afastamentos concedidos do servidor no ano."""
        ini = date(self.ano, 1, 1)
        fim = date(self.ano, 12, 31)

        afastamentos_qs = ServidorAfastamento.objects.filter(servidor=self.servidor, cancelado=False, data_inicio__lte=fim, data_termino__gte=ini)
        return afastamentos_qs.only('id', 'data_inicio', 'data_termino', 'afastamento').select_related('afastamento')

    def _preparar_tipos_afastamento(self, ferias: QuerySet[ParcelaFerias], concedidos: QuerySet[ServidorAfastamento]) -> dict[str, TipoAfastamento]:
        """Prepara todos os tipos de afastamento necessários."""
        # Coleta nomes únicos
        nomes_afastamentos = {'Férias'}
        nomes_concedidos = concedidos.values_list('afastamento__nome', flat=True).distinct()
        nomes_afastamentos.update(nomes_concedidos)
        # Verifica existentes
        tipos_existentes = set(TipoAfastamento.objects.filter(nome__in=nomes_afastamentos).values_list('nome', flat=True))
        # Cria novos tipos
        tipos_para_criar = nomes_afastamentos - tipos_existentes
        if tipos_para_criar:
            novos_tipos = [TipoAfastamento(nome=nome, descricao=f'Afastamento consolidado: {nome}') for nome in tipos_para_criar]
            TipoAfastamento.objects.bulk_create(novos_tipos, ignore_conflicts=True)
        # Retorna dicionário para lookup
        return {tipo.nome: tipo for tipo in TipoAfastamento.objects.filter(nome__in=nomes_afastamentos)}

    def _processar_consolidacao(
        self, ferias: QuerySet[ParcelaFerias], concedidos: QuerySet[ServidorAfastamento], tipos_dict: dict[str, TipoAfastamento]
    ) -> dict:
        # trava os mensais durante a consolidação
        mensais = (
            self.planejamento.planejamentos_mensais.select_related('planejamento_anual', 'planejamento_anual__auditor__jornada_trabalho')
            .order_by('mes')
            .select_for_update(of=('self',))
        )

        snapshots = []
        ch_total_afastadas_anual = 0
        ch_total_prevista_anual = 0

        for mensal in mensais:
            inicio_mes = date(self.ano, mensal.mes, 1)
            fim_mes = date(self.ano, mensal.mes, monthrange(self.ano, mensal.mes)[1])
            periodo = DateInterval(inicio_mes, fim_mes)

            # Os intervalos das três fontes se sobrepõem, então são coletados e só
            # depois convertidos em horas — uma vez por dia, não por registro.
            intervalos = self._intervalos_declarados(mensal)
            # Férias
            intervalos += self._processar_ferias(ferias, mensal, periodo, tipos_dict, snapshots)
            # Concedidos (RH)
            intervalos += self._processar_concedidos(concedidos, mensal, periodo, tipos_dict, snapshots)
            ch_afastadas_mes = horas_afastadas_no_periodo(intervalos, periodo.start, periodo.end, self.unidade, self.jornada)

            # Atualiza agregados do mensal
            mensal.carga_horaria_homologada = (mensal.carga_horaria_prevista or 0) - ch_afastadas_mes
            if mensal.carga_horaria_homologada < 0:
                raise ValueError('Carga horária homologada negativa após importação de afastamentos.')
            mensal.save(update_fields=['carga_horaria_homologada'])

            ch_total_afastadas_anual += ch_afastadas_mes
            ch_total_prevista_anual += mensal.carga_horaria_homologada

        if snapshots:
            AfastamentoPlanejado.objects.bulk_create(snapshots, batch_size=500, ignore_conflicts=True)

        # Atualiza agregados do anual
        self.planejamento.carga_horaria_afastada_homologada = ch_total_afastadas_anual
        self.planejamento.carga_horaria_homologada = ch_total_prevista_anual
        self.planejamento.save(update_fields=['carga_horaria_afastada_homologada', 'carga_horaria_homologada'])

        return {
            'mensais_processados': mensais.count(),
            'ch_afastadas_anual': float(ch_total_afastadas_anual),
            'ch_homologadas_anual': float(ch_total_prevista_anual),
        }

    def _processar_ferias(
        self, ferias: QuerySet[ParcelaFerias], mensal, periodo: DateInterval, tipos_dict: dict[str, TipoAfastamento], out_snapshots
    ) -> list[tuple[date, date]]:
        """Cria os snapshots das férias do mês e devolve os intervalos cobertos."""
        tipo_ferias = tipos_dict.get('Férias')
        if tipo_ferias is None:
            # Sem férias a consolidar (nenhuma no ano, ou sincronização desligada).
            return []

        intervalos: list[tuple[date, date]] = []
        for ferias_item in ferias:
            if not self._intersecta(periodo, ferias_item.data_inicio, ferias_item.data_fim):
                continue
            ini = max(periodo.start, ferias_item.data_inicio)
            fim = min(periodo.end, ferias_item.data_fim)

            if not dias_uteis_auditoria(ini, fim, self.unidade, self.jornada):
                continue
            out_snapshots.append(
                AfastamentoPlanejado(
                    planejamento=mensal,
                    data_inicio=ini,
                    data_fim=fim,
                    tipo_afastamento=tipo_ferias,
                    status=StatusAfastamento.HOMOLOGADO,
                    motivo='Importação do SUAP - Férias',
                    importado=True,
                )
            )
            intervalos.append((ini, fim))
        return intervalos

    def _processar_concedidos(self, concedidos, mensal, periodo: DateInterval, tipos_dict: dict, out_snapshots) -> list[tuple[date, date]]:
        """Cria os snapshots dos afastamentos do RH no mês e devolve os intervalos cobertos."""
        intervalos: list[tuple[date, date]] = []
        for concedido in concedidos:
            if not self._intersecta(periodo, concedido.data_inicio, concedido.data_termino):
                continue
            ini = max(periodo.start, concedido.data_inicio)
            fim = min(periodo.end, concedido.data_termino)

            if not concedido.dias_uteis(data_inicio=ini, data_terminio=fim):
                continue

            afast_siape: AfastamentoSiape = concedido.afastamento
            tipo = tipos_dict[afast_siape.nome]
            out_snapshots.append(
                AfastamentoPlanejado(
                    planejamento=mensal,
                    data_inicio=ini,
                    data_fim=fim,
                    tipo_afastamento=tipo,
                    status=StatusAfastamento.HOMOLOGADO,
                    motivo=f'Importação do SUAP - {afast_siape}',
                    importado=True,
                )
            )
            intervalos.append((ini, fim))
        return intervalos

    @staticmethod
    def _intervalos_declarados(mensal) -> list[tuple[date, date]]:
        """Intervalos dos afastamentos homologados já gravados no mês.

        São os que o auditor declarou mais, quando a sincronização está
        desligada, os que ficaram de uma importação anterior.
        """
        return [(afastamento.data_inicio, afastamento.data_fim) for afastamento in mensal.afastamentos.homologados()]

    @staticmethod
    def _intersecta(intervalo_mes: DateInterval, inicio, fim) -> bool:
        return not (fim < intervalo_mes.start or inicio > intervalo_mes.end)
