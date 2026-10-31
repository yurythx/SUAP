"""
Management command: seed_sla_test_data

Ajusta aleatoriamente as datas de transição de estado dos processos RSC-TAE
para simular diferentes cenários de SLA (dentro do prazo, em alerta, estourado).

Uso:
    python manage.py seed_sla_test_data
    python manage.py seed_sla_test_data --seed 42          # seed fixo (reproduzível)
    python manage.py seed_sla_test_data --dry-run          # apenas imprime o que faria
    python manage.py seed_sla_test_data --reset            # restaura todas as datas para "agora"

Cenários gerados (distribuição configurável via --pct-*):
    ok       (35%) — dentro do prazo, > 3 dias restantes
    alerta   (25%) — dentro do prazo, 0-3 dias restantes
    estourado(40%) — prazo já ultrapassado

Apenas processos em estados com SLA configurado são afetados:
    AGUARDANDO_PREENCHIMENTO · AGUARDANDO_CORRECAO
    AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR · EM_ANALISE
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import ProcessoRSCTae
from rsc_tae.models.configuracao_rsc_tae import ConfiguracaoRSCTae
from rsc_tae.models.processo import HistoricoSituacaoProcessoRSCTae


# Estados que possuem SLA (excluindo legados sem SLA)
ESTADOS_COM_SLA = {
    SituacaoProcesso.AGUARDANDO_PREENCHIMENTO,
    SituacaoProcesso.AGUARDANDO_CORRECAO,
    SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
    SituacaoProcesso.EM_ANALISE,
}

# Nome legível para cada situação
SITUACAO_LABEL = {
    SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: 'Aguardando Preenchimento',
    SituacaoProcesso.AGUARDANDO_CORRECAO: 'Aguardando Correção',
    SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: 'Aguardando Validação RH',
    SituacaoProcesso.EM_ANALISE: 'Em Análise',
}


class Command(BaseCommand):
    help = 'Ajusta datas de transição dos processos RSC-TAE para testes de SLA.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--seed',
            type=int,
            default=None,
            help='Seed para o gerador aleatório (garante reprodutibilidade).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas exibe o que seria alterado, sem salvar.',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Restaura data_transicao de todos os históricos para agora (desfaz o seed).',
        )
        parser.add_argument(
            '--pct-ok',
            type=int,
            default=35,
            help='Porcentagem de processos no cenário "ok" (padrão: 35).',
        )
        parser.add_argument(
            '--pct-alerta',
            type=int,
            default=25,
            help='Porcentagem de processos no cenário "alerta" (padrão: 25).',
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reset = options['reset']
        seed = options['seed']
        pct_ok = options['pct_ok']
        pct_alerta = options['pct_alerta']

        if pct_ok + pct_alerta > 100:
            raise CommandError('--pct-ok + --pct-alerta não pode ultrapassar 100.')

        if seed is not None:
            random.seed(seed)
            self.stdout.write(f'Seed: {seed}')

        if reset:
            self._handle_reset(dry_run)
            return

        config = ConfiguracaoRSCTae.objects.first()
        if not config:
            raise CommandError('Nenhuma ConfiguracaoRSCTae encontrada. Cadastre uma em Admin → RSC-TAE → Configurações antes de rodar este comando.')

        sla_por_situacao = {
            SituacaoProcesso.AGUARDANDO_PREENCHIMENTO: config.dias_prazo_preenchimento,
            SituacaoProcesso.AGUARDANDO_CORRECAO: config.dias_prazo_correcao,
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: config.dias_prazo_validacao_rh,
            SituacaoProcesso.EM_ANALISE: config.dias_prazo_avaliacao,
        }

        self.stdout.write('\nSLAs configurados:')
        for sit, dias in sla_por_situacao.items():
            self.stdout.write(f'  {SITUACAO_LABEL[sit]}: {dias} dias')
        self.stdout.write('')

        processos = ProcessoRSCTae.objects.filter(situacao__in=ESTADOS_COM_SLA).prefetch_related('historico_situacoes').order_by('id')

        total = processos.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('Nenhum processo ativo com SLA encontrado.'))
            return

        self.stdout.write(f'Processos encontrados com SLA ativo: {total}\n')

        contadores = {'ok': 0, 'alerta': 0, 'estourado': 0, 'sem_historico': 0}
        agora = timezone.now()

        for processo in processos:
            dias_sla = sla_por_situacao.get(processo.situacao)
            if not dias_sla:
                continue

            # Determina o cenário aleatoriamente pela distribuição configurada
            roll = random.randint(1, 100)
            if roll <= pct_ok:
                cenario = 'ok'
            elif roll <= pct_ok + pct_alerta:
                cenario = 'alerta'
            else:
                cenario = 'estourado'

            nova_data = self._calcular_data_entrada(agora, dias_sla, cenario)

            # Encontra o registro de histórico que marca a entrada no estado atual
            historico_qs = HistoricoSituacaoProcessoRSCTae.objects.filter(
                processo=processo,
                situacao_nova=processo.situacao,
            ).order_by('-data_transicao')

            historico = historico_qs.first()

            label = SITUACAO_LABEL.get(processo.situacao, str(processo.situacao))
            dias_decorridos = (agora - nova_data).days
            dias_restantes = dias_sla - dias_decorridos
            sinal = '🔴' if dias_restantes < 0 else ('🟡' if dias_restantes <= 3 else '🟢')

            self.stdout.write(
                f'  [{sinal} {cenario.upper():10s}] Processo #{processo.pk} — {label} '
                f'| SLA {dias_sla}d | decorridos {dias_decorridos}d | restantes {dias_restantes:+d}d'
            )

            if dry_run:
                continue

            if historico:
                # auto_now_add impede save(); usar update() passa direto
                HistoricoSituacaoProcessoRSCTae.objects.filter(pk=historico.pk).update(data_transicao=nova_data)
                contadores[cenario] += 1
            else:
                # Processo sem histórico (ex: criado antes do log) → ajusta data_cadastro
                if processo.situacao == SituacaoProcesso.AGUARDANDO_PREENCHIMENTO:
                    ProcessoRSCTae.objects.filter(pk=processo.pk).update(data_cadastro=nova_data)
                    contadores[cenario] += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f'    ↳ Processo #{processo.pk} sem histórico e situação {label} — pulado (crie o histórico manualmente).')
                    )
                    contadores['sem_historico'] += 1

        if not dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Resumo das alterações:'))
            self.stdout.write(f'  🟢 Ok (dentro do prazo):  {contadores["ok"]}')
            self.stdout.write(f'  🟡 Alerta (≤3 dias):       {contadores["alerta"]}')
            self.stdout.write(f'  🔴 Estourado:              {contadores["estourado"]}')
            if contadores['sem_historico']:
                self.stdout.write(self.style.WARNING(f'  ⚠  Sem histórico (pulado): {contadores["sem_historico"]}'))
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Dados de SLA atualizados com sucesso.'))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Modo dry-run: nenhuma alteração foi salva.'))

    # ------------------------------------------------------------------
    def _calcular_data_entrada(self, agora, dias_sla, cenario):
        """Retorna uma data de entrada compatível com o cenário desejado."""
        if cenario == 'ok':
            # Faltam entre 4 e dias_sla dias para o vencimento
            margem_min = 4
            max(dias_sla, margem_min + 1)
            dias_decorridos = random.randint(0, dias_sla - margem_min)
            return agora - timedelta(days=dias_decorridos)

        if cenario == 'alerta':
            # Faltam 0, 1, 2 ou 3 dias para o vencimento
            dias_restantes = random.randint(0, 3)
            dias_decorridos = dias_sla - dias_restantes
            return agora - timedelta(days=max(dias_decorridos, 0))

        # estourado — atrasado entre 1 e 60 dias
        dias_atraso = random.randint(1, 60)
        dias_decorridos = dias_sla + dias_atraso
        return agora - timedelta(days=dias_decorridos)

    # ------------------------------------------------------------------
    def _handle_reset(self, dry_run):
        """Restaura data_transicao de todos os históricos para agora."""
        agora = timezone.now()
        qs = HistoricoSituacaoProcessoRSCTae.objects.filter(
            processo__situacao__in=ESTADOS_COM_SLA,
        )
        count = qs.count()

        if count == 0:
            self.stdout.write(self.style.WARNING('Nenhum registro de histórico ativo encontrado.'))
            return

        self.stdout.write(f'Restaurando {count} registros de histórico para agora...')

        if not dry_run:
            qs.update(data_transicao=agora)
            # Também restaura data_cadastro dos processos sem histórico
            ProcessoRSCTae.objects.filter(
                situacao=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO,
                historico_situacoes__isnull=True,
            ).update(data_cadastro=agora)
            self.stdout.write(self.style.SUCCESS('Reset concluído.'))
        else:
            self.stdout.write(self.style.WARNING('Modo dry-run: nenhuma alteração foi salva.'))
