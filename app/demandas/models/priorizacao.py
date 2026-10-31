from django.db import transaction

from comum.models import Configuracao, User
from demandas.exceptions import DemandaDespriorizadaException, DemandasException
from djtools.db import models

from .demanda import AreaAtuacaoDemanda, Demanda, Situacao


class DemandaPriorizacao:
    QTD_DEMANDAS_PRIORITARIAS_MIN = 1
    QTD_DEMANDAS_PRIORITARIAS_MAX = 20
    QTD_DEMANDAS_PRIORITARIAS_DEFAULT = 5

    class AlterarPrioridadeSuccess:
        def __init__(self, demanda: Demanda, anterior_prioridade: int, nova_prioridade: int, mensagem: str):
            self.demanda = demanda
            self.anterior_prioridade = anterior_prioridade
            self.nova_prioridade = nova_prioridade
            self.mensagem = mensagem

        def __str__(self):
            return f'{self.demanda}: Posição de {self.anterior_prioridade}ª para {self.nova_prioridade}ª. {self.mensagem}'

    @classmethod
    def get_qtd_demandas_prioritarias_por_area(cls) -> int:
        qtd = Configuracao.get_valor_por_chave('demandas', 'qtd_demandas_prioritarias_por_area')
        if not qtd:
            qtd = cls.QTD_DEMANDAS_PRIORITARIAS_DEFAULT
        return int(f'{qtd}')

    @classmethod
    def estah_em_andamento(cls, demanda: Demanda) -> bool:
        return Situacao.eh_estado_em_andamento_priorizacao(demanda.situacao)

    @classmethod
    def truncate_demanda_str(cls, demanda: Demanda, max_length: int | None = None, ellipsis: str | None = None) -> str:
        demanda_str = f'{demanda}'
        if max_length:
            demanda_str_tmp = demanda_str[0:max_length]
            if ellipsis and len(demanda_str_tmp) < len(demanda_str):
                demanda_str_tmp = f'{demanda_str_tmp}{ellipsis}'
            demanda_str = demanda_str_tmp
        return demanda_str

    @classmethod
    def get_ativas_da_area(cls, area: AreaAtuacaoDemanda) -> models.QuerySet[Demanda]:
        return Demanda.objects.ativas().filter(area=area).order_by('prioridade', 'pk')

    @classmethod
    def get_prioritarias_da_area(cls, area: AreaAtuacaoDemanda) -> models.QuerySet[Demanda]:
        return (
            cls.get_ativas_da_area(area)
            .filter(prioridade__gte=1, prioridade__lte=cls.get_qtd_demandas_prioritarias_por_area())
            .order_by('prioridade', 'pk')
        )

    @classmethod
    def alterar_prioridade(
        cls,
        demanda: Demanda,
        nova_prioridade: int,
        usuario: User = None,
        commit: bool = False,
    ) -> list[AlterarPrioridadeSuccess]:
        """
        Altera a prioridade de uma demanda. É possível que ocorram
        reposicionamentos de outras demandas afetadas.

        Regras:
        - Demanda priorizada: tem uma prioridade até get_qtd_demandas_prioritarias_por_area().
        - Demanda não priorizada: tem prioridade a partir de get_qtd_demandas_prioritarias_por_area()+1 (despriorizada).
        - Demanda priorizada em andamento não poderá ser despriorizada.
        - Demanda não priorizada poderá ser priorizada apenas se houver pelo menos uma demanda priorizada que não esteja em andamento.
        - Demais casos de alteração de prioridade: reposicionamento ou manutenção da prioridade.
        """

        result_success: list[cls.AlterarPrioridadeSuccess] = []

        if nova_prioridade < 1:
            raise DemandasException(f'Esta demanda não pode ter a sua prioridade alterada para um valor inválido ({nova_prioridade}).')

        qtd_demandas_prioritarias_por_area = cls.get_qtd_demandas_prioritarias_por_area()

        if demanda.prioridade:
            demanda_estah_priorizada = 1 <= demanda.prioridade <= qtd_demandas_prioritarias_por_area
        else:
            demanda_estah_priorizada = False

        # demandas priorizadas (posição de 1 a qtd_demandas_prioritarias_por_area) em andamento
        # não poderão ter prioridade alterada para qtd_demandas_prioritarias_por_area+1 ou mais.
        if demanda_estah_priorizada and cls.estah_em_andamento(demanda) and nova_prioridade >= qtd_demandas_prioritarias_por_area + 1:
            raise DemandaDespriorizadaException

        demanda_sendo_priorizada = not demanda_estah_priorizada and 1 <= nova_prioridade <= qtd_demandas_prioritarias_por_area

        if demanda_sendo_priorizada:
            prioritarias_da_area = cls.get_prioritarias_da_area(demanda.area)

            prioritarias_paradas = [prioritaria for prioritaria in prioritarias_da_area if not cls.estah_em_andamento(prioritaria)]
            if not prioritarias_paradas:
                raise DemandasException('Esta demanda não pode ser priorizada pois todas as demandas atualmente priorizadas estão em andamento.')

        outras_demandas_ativas_da_area = cls.get_ativas_da_area(demanda.area).exclude(id=demanda.id)
        demandas_nova_ordem = []
        demanda_inserida = False

        for posicao, outra_demanda in enumerate(outras_demandas_ativas_da_area, start=1):
            if posicao == nova_prioridade:
                # insere a demanda na posição da nova prioridade informada
                demandas_nova_ordem.append(demanda)
                demanda_inserida = True
            demandas_nova_ordem.append(outra_demanda)

        if not demanda_inserida:
            # insere a demanda na última posição
            demandas_nova_ordem.append(demanda)

        try:
            # altera a prioridade em lote das demandas na nova ordem definida
            result_success.extend(cls.alterar_prioridade_em_lote(demandas_nova_ordem, usuario, commit))

        except (DemandasException, Exception) as error:
            raise error

        return result_success

    @classmethod
    @transaction.atomic
    def alterar_prioridade_em_lote(
        cls,
        demandas_em_nova_ordem: list[Demanda],
        usuario: User = None,
        commit: bool = False,
    ) -> list[AlterarPrioridadeSuccess]:
        """
        Altera em lote as prioridades de um dado conjunto de demandas em uma ordem final escolhida.

        Args:
        :param demandas_em_nova_ordem: Lista de demandas numa ordem final escolhida.

        Regras:
        - Demanda priorizada: tem uma prioridade até get_qtd_demandas_prioritarias_por_area().
        - Demanda não priorizada: tem prioridade a partir de get_qtd_demandas_prioritarias_por_area() + 1 (despriorizada).
        - Demanda priorizada em andamento não poderá ser despriorizada.
        """

        result_success = []
        qtd_demandas_prioritarias_por_area = cls.get_qtd_demandas_prioritarias_por_area()

        demandas_areas_envolvidas = []
        for demanda in demandas_em_nova_ordem:
            if demanda.area not in demandas_areas_envolvidas:
                demandas_areas_envolvidas.append(demanda.area)
                if len(demandas_areas_envolvidas) > 1:
                    break

        # as demandas informadas devem ser de uma única área
        if len(demandas_areas_envolvidas) > 1:
            raise DemandasException('As demandas informadas devem pertencer a uma única área de atuação.')

        for nova_prioridade, demanda in enumerate(demandas_em_nova_ordem, start=1):
            demanda_prioridade_anterior = demanda.prioridade

            try:
                if demanda_prioridade_anterior:
                    demanda_estah_priorizada = 1 <= demanda_prioridade_anterior <= qtd_demandas_prioritarias_por_area
                else:
                    demanda_estah_priorizada = False

                # demandas priorizadas (posição de 1 a qtd_demandas_prioritarias_por_area) em andamento
                # não poderão ter prioridade alterada para qtd_demandas_prioritarias_por_area+1 ou mais.
                if demanda_estah_priorizada and cls.estah_em_andamento(demanda) and nova_prioridade >= qtd_demandas_prioritarias_por_area + 1:
                    raise DemandaDespriorizadaException

                if demanda_prioridade_anterior != nova_prioridade:
                    result_success.append(
                        cls.AlterarPrioridadeSuccess(
                            demanda,
                            demanda_prioridade_anterior,
                            nova_prioridade,
                            'Prioridade alterada.',
                        )
                    )

            except DemandasException as error:
                if demanda_prioridade_anterior == nova_prioridade:
                    raise DemandasException(
                        f'{cls.truncate_demanda_str(demanda, 80, "...")}: Mantendo a {demanda_prioridade_anterior}ª posição. {error}.'
                    )
                else:
                    raise DemandasException(
                        f'{cls.truncate_demanda_str(demanda, 80, "...")}: Alterando a posição de {demanda_prioridade_anterior}ª para {nova_prioridade}ª. {error}.'
                    )

            except Exception as error:
                raise error

        if commit:
            for demanda_alterada in result_success:
                # salva a prioridade
                demanda_alterada.demanda.prioridade = demanda_alterada.nova_prioridade
                demanda_alterada.demanda.save()
                # atualiza histórico de prioridade
                Demanda.criar_historico_prioridade(demanda_alterada.demanda, usuario, demanda_alterada.nova_prioridade)

            if demandas_areas_envolvidas:
                # finaliza a atualização das prioridades das demandas da área
                area = demandas_areas_envolvidas[0]
                Demanda.atualizar_prioridades(area, usuario)

        return result_success
