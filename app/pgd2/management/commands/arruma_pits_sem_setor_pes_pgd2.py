from djtools.management.commands import BaseCommandPlus
from django.apps.registry import apps
from django.db.models import Q


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        Exemplo do problema
        - PIT - 01/09/2024 a 30/09/2024 | Madja Cristhellen Gomes de Araujo Chaves (1887195) -
        <strong>Não foi possível calcular o PES principal e apto para homologar.</strong> <ul><li>
        (1) Verificar o seu último setor do período relacionado a este plano.
            Isso pode ser verificado por você mesmo ou pela Gestão de Pessoas. </li> <li>
        (2) Verifique se o seu último setor do período relacionado a este plano possui PES homologado
            para o mesmo período. Isso pode ser verficado por você mesmo ou pelo chefe do seu último
            setor do período relacionado a este plano</li> </ul>
        Resumo: mudou setor retrotivamente e bagunçou a relação do PIT com setor e pes principais
        Maiores detalhes em https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/15122#note_233299

        COMMAND: arruma_pits_sem_setor_pes_pgd2
        """

        PlanoIndividualTrabalho = apps.get_model('pgd2', 'PlanoIndividualTrabalho')
        PitSolicitacaoAnaliseSetor = apps.get_model('pgd2', 'PitSolicitacaoAnaliseSetor')
        PitSolicitacaoAnalise = apps.get_model('pgd2', 'PitSolicitacaoAnalise')
        PitSetores = apps.get_model('pgd2', 'PitSetores')
        PeriodoPitRit = apps.get_model('pgd2', 'PeriodoPitRit')
        PlanoEntregasSetorial = apps.get_model('pgd2', 'PlanoEntregasSetorial')

        def get_pits_para_ajustar(periodos):
            pits_enviar = PlanoIndividualTrabalho.objects.exclude(
                Q(situacao=PlanoIndividualTrabalho.EM_CADASTRO) | Q(situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)
            )
            pits_enviar = pits_enviar.filter(periodo_pit_rit__in=periodos)

            ja_foram_homologados = PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
                solicitacao__finalizado=True,
                parecer=True,
                tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
            ).values('solicitacao__pit__id')
            pits_enviar = pits_enviar.filter(id__in=ja_foram_homologados)

            # filtra pelos que tem problema
            problemas = PitSetores.objects.filter(pode_homologar=True).filter(
                Q(pes__isnull=True) | Q(setor__isnull=True) | Q(pit__setor_pode_homologar_pit_rit__isnull=True)
            )
            pits_enviar = pits_enviar.filter(id__in=problemas.values_list('pit_id', flat=True))

            return pits_enviar

        # ----------------
        # PITs antes de 10/2025 (meses anteriores ao atual)
        # ----------------

        periodos_anteriores = PeriodoPitRit.objects.filter(id__lte=14).order_by('id')
        pits = get_pits_para_ajustar(periodos_anteriores)

        lista_possiveis = []

        for pit in pits:
            setor, pes = None, None

            # Tenta inferir qual o setor do servidor na época
            # - Pelo setor que principal responsavel pela pimeira homologacao
            # - Pelo PES vinculado as entregas
            # Pelo setor
            primeira_homologacao = pit.get_primeira_analise_de_homologacao_do_pit()
            if primeira_homologacao:
                setor = primeira_homologacao.setor
            # Pelo PES
            ids_pess = (
                pit.get_entregas_pit_para_rit()
                .order_by('entrega_pes__pes_id')
                .distinct('entrega_pes__pes_id')
                .values_list('entrega_pes__pes_id', flat=True)
            )
            pess_relacionados = PlanoEntregasSetorial.objects.filter(id__in=ids_pess)
            if pess_relacionados.count() == 1:
                pes = pess_relacionados.first()
            else:
                if pit.id in [1587, 2545, 2895, 1200, 918]:
                    pes = pess_relacionados.filter(setor__sigla='DIAC/IP').first()

            lista_possiveis.append((pit, setor, pes))

        for lista in lista_possiveis:
            pit_setor = PitSetores.objects.filter(pode_homologar=True, pit=lista[0].id).first()
            pit_setor.setor = lista[1]
            pit_setor.pes = lista[2]
            pit_setor.save()
            pit = pit_setor.pit
            pit.setor_pode_homologar_pit_rit = lista[1]
            pit.save()

        # ----------------
        # PITs de 10/2025
        # ----------------

        periodo_atual = PeriodoPitRit.objects.get(id=15)
        pits = get_pits_para_ajustar([periodo_atual])

        for pit in pits:
            pit.calcular_pit_setores_envolvidos()
