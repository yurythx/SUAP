"""
A princípio vamos extrair os dados por aqui
- Considerando a nossa interpretação e realidade
- Existem vários pontos que dependem da análise da realidade local
- Aqui consideramos apenas a realidade local do IFRN
"""

from pgd2.models import PitSetores, PlanoEntregasSetorial, PlanoEntregasSetorialEntregas, PlanoIndividualTrabalho, SolicitacaoAdesaoServidor


class MonitoramentoMGI:
    self_command = None

    def __init__(self, self_command):
        self.self_command = self_command

    def print_msg(self, msg):
        if self.self_command:
            self.self_command.stdout.write(msg)

    def indicador1(self):
        pess_aprovados_2025 = PlanoEntregasSetorial.get_pess_aprovados()
        entregas_pess_aprovados_2025 = PlanoEntregasSetorialEntregas.objects.filter(
            pes__in=pess_aprovados_2025, cancelado=False, pes__periodo_pes__data_inicio__year=2025
        )

        # Nº de entregas PES pactuadas em 2025
        qtd_entregas_pess_aprovados_2025 = entregas_pess_aprovados_2025.count()
        # Nº de entregas PES pactuadas em 2025 - que foram "Vinculado com planejamento estratégico" no SUAP
        qtd_entregas_pess_aprovados_2025_vinculadas = (
            entregas_pess_aprovados_2025.filter(atividade_processo_plan_estrategico__isnull=False).distinct().count()
        )
        # Nº de entregas PES pactuadas em 2025 - que não foram "Vinculado com planejamento estratégico" no SUAP
        qtd_entregas_pess_aprovados_2025_nao_vinculadas = entregas_pess_aprovados_2025.filter(
            atividade_processo_plan_estrategico__isnull=True
        ).count()

        self.print_msg('============================')
        self.print_msg(' INDICADOR 1')
        self.print_msg('============================')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025: {qtd_entregas_pess_aprovados_2025}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Vinculadas: {qtd_entregas_pess_aprovados_2025_vinculadas}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Não Vinculadas: {qtd_entregas_pess_aprovados_2025_nao_vinculadas}')

    def indicador2(self):
        pess_aprovados_2025 = PlanoEntregasSetorial.get_pess_aprovados()
        entregas_pess_aprovados_2025 = PlanoEntregasSetorialEntregas.objects.filter(
            pes__in=pess_aprovados_2025, cancelado=False, pes__periodo_pes__data_inicio__year=2025
        )

        entregas_pess_aprovados__analisados_2025 = entregas_pess_aprovados_2025.filter(
            pes__situacao_avaliacao=PlanoEntregasSetorial.SOLICITADO_AVALIACAO
        )
        entregas_pess_aprovados__avaliados_2025 = entregas_pess_aprovados_2025.filter(pes__situacao_avaliacao=PlanoEntregasSetorial.AVALIADO)

        # Nº de entregas PES pactuadas em 2025 - que foram analisadas como "Executada Totalmente"
        qtd_1 = entregas_pess_aprovados__analisados_2025.filter(entrega_analise=PlanoEntregasSetorialEntregas.EXECUTADA_TOTALMENTE).count()
        # Nº de entregas PES pactuadas em 2025 - que foram analisadas como "Executada Parcialmente"
        qtd_2 = entregas_pess_aprovados__analisados_2025.filter(entrega_analise=PlanoEntregasSetorialEntregas.EXECUTADA_PARCIALMENTE).count()
        # Nº de entregas PES pactuadas em 2025 - que foram analisadas como "Não Executada"
        qtd_3 = entregas_pess_aprovados__analisados_2025.filter(entrega_analise=PlanoEntregasSetorialEntregas.EXECUTADA_NAO).count()
        # Nº de entregas PES pactuadas em 2025 - que foram avalidas como "Executada Totalmente"
        qtd_4 = entregas_pess_aprovados__avaliados_2025.filter(entrega_analise=PlanoEntregasSetorialEntregas.EXECUTADA_TOTALMENTE).count()
        # Nº de entregas PES pactuadas em 2025 - que foram avalidas como "Executada Parcialmente"
        qtd_5 = entregas_pess_aprovados__avaliados_2025.filter(entrega_analise=PlanoEntregasSetorialEntregas.EXECUTADA_PARCIALMENTE).count()
        # Nº de entregas PES pactuadas em 2025 - que foram avalidas como "Não Executada"
        qtd_6 = entregas_pess_aprovados__avaliados_2025.filter(entrega_analise=PlanoEntregasSetorialEntregas.EXECUTADA_NAO).count()

        self.print_msg('============================')
        self.print_msg(' INDICADOR 2')
        self.print_msg('============================')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Analisadas: {entregas_pess_aprovados__analisados_2025.count()}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Analisadas - Executada Totalmente: {qtd_1}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Analisadas - Executada: {qtd_2}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Analisadas - Não Executada: {qtd_3}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Avaliadas: {entregas_pess_aprovados__avaliados_2025.count()}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Avaliadas - Executada Totalmente: {qtd_4}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Avaliadas - Executada: {qtd_5}')
        self.print_msg(f'> Nº de entregas PES pactuadas em 2025 - Avaliadas - Não Executada: {qtd_6}')

    def indicador4(self):
        # Quantidade de servidores que estava em PGD em 31/12/2025
        # - Servidores com adesão deferida em 2025 e sem desligamento com data de efeitos a partir de 01/01/2026
        # - Que tinha algum PIT homologado ao menos uma vez
        # Limitações
        # - Vai contabilzar servidor que foramdesligados em 2025 mas tiveram o desligamenot removido posteriormente
        # - Contabilizar servidores que tiveram pelo o menos um PIT homologado, mesmo que não tenha sido apenas um homologado em 2025
        adesoes = SolicitacaoAdesaoServidor.get_deferidas()
        adesoes = adesoes.filter(data_inicio__year__lte=2025).exclude(
            data_desligamento_efeitos_a_partir_de__lte='2026-01-01',
        )
        pits_homologados = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        pits_homologados = pits_homologados.filter(data_inicio__year__lte=2025)
        adesoes = adesoes.filter(id__in=pits_homologados.values_list('adesao_id', flat=True))
        qtd_servidores_em_pgd_2025 = adesoes.distinct('servidor_id').count()
        qtd_servidores_em_pgd_hoje = SolicitacaoAdesaoServidor.get_servidores_em_pgd().count()

        self.print_msg('============================')
        self.print_msg(' INDICADOR 4')
        self.print_msg('============================')
        self.print_msg(f'> Nº de servidores que estava em PGD em 31/12/2025: {qtd_servidores_em_pgd_2025}')
        self.print_msg(f'> Nº de servidores que está em PGD hoje: {qtd_servidores_em_pgd_hoje}')

    def indicador6(self):
        # Considerando 4 tri 2024, 1 tri 2025, 2 tri 2025 e 3 tri 2025 (excluindo o referente  dez 2025)
        #   - Quantidade de PESs aprovados e avaliados
        #     - Excluindo PESs sem PIT homologado vinculado
        #   - Quantidade de PESs aprovados que eram pra ter sido avaliados
        #     - Excluindo PESs sem PIT homologado vinculado

        # PESs aprovados do 4 tri 2024, 1 tri 2025, 2 tri 2025 e 3 tri 2025
        pess_aprovados = PlanoEntregasSetorial.get_pess_aprovados().filter(periodo_pes__id__in=[2, 3, 4, 5])
        # PITS relacionados aos PESs e que tiverem PIT que foram homologados ao menos uma vez
        pits_homologados = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        ids_pess_com_pit_homologado = PitSetores.objects.filter(pes__in=pess_aprovados, pit__in=pits_homologados).values_list('pes_id', flat=True)

        # PESs com PIT homologado
        pess_aprovados_com_pit_homologado = pess_aprovados.filter(id__in=ids_pess_com_pit_homologado)
        # PESs aprovados e avaliados
        pess_aprovados_com_pit_homologado_e_avaliados = pess_aprovados_com_pit_homologado.filter(
            situacao_avaliacao=PlanoEntregasSetorial.AVALIADO
        ).count()
        # PESs aprovados que eram pra ter sido avaliados
        pess_aprovados_com_pit_homologado_e_precisava_de_avaliacao = pess_aprovados_com_pit_homologado.count()

        self.print_msg('============================')
        self.print_msg(' INDICADOR 6')
        self.print_msg('============================')
        self.print_msg(f'> PESs com PIT homologado: {pess_aprovados_com_pit_homologado.count()}')
        self.print_msg(f'> PESs aprovados, com PIT homologado e avaliados: {pess_aprovados_com_pit_homologado_e_avaliados}')
        self.print_msg(
            f'> PESs aprovados, com PIT homologado e que eram pra ter sido avaliados: {pess_aprovados_com_pit_homologado_e_precisava_de_avaliacao}'
        )

    def indicador7(self):
        # Considerando último RIT de 2024 (dez/2024) até penúltimo de 2025 (nov/2025)
        # - Quantidade de RIT homologados
        # - Quantidade de RIT que deveriam ter sido homologados
        # Limitações
        # - Algum RIT que esteve homologado pode twer sido reaberto

        pits = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().filter(
            periodo_pit_rit_id__in=[5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
        )
        rits_homologados = pits.filter(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT).count()
        rits_eram_pra_ser_homologados = pits.exclude(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT).count()

        self.print_msg('============================')
        self.print_msg(' INDICADOR 7')
        self.print_msg('============================')
        self.print_msg(f'> Do último RIT de 2024 (dez/2024) até penúltimo de 2025 (nov/2025). Todos os RITs: {pits.count()}')
        self.print_msg(f'> Do último RIT de 2024 (dez/2024) até penúltimo de 2025 (nov/2025). RITs homologados: {rits_homologados}')
        self.print_msg(
            f'> Do último RIT de 2024 (dez/2024) até penúltimo de 2025 (nov/2025). RITs que eram pra ser homologados: {rits_eram_pra_ser_homologados}'
        )

    def obter_dados(self):
        self.indicador1(self_command=self.self_command)
        self.indicador2(self_command=self.self_command)
        self.indicador4(self_command=self.self_command)
        self.indicador6(self_command=self.self_command)
        self.indicador7(self_command=self.self_command)
