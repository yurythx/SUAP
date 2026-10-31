from datetime import datetime

from django.db.models import Count

from comum.models import User
from djtools.management.commands import BaseCommandPlus
from gestao import tasks
from gestao.models import PeriodoReferencia, Variavel
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('--forcar', action='store_true', dest='forcar', default=False, help='Forçar a importação de todos.')

    def set_periodo_ano_passado(self):
        ano = datetime.now().year - 1
        self.stdout.write(f'Período, ano anterior: {ano}')
        periodo = PeriodoReferencia.objects.filter(data_base=datetime(ano, 1, 1), data_limite=datetime(ano, 12, 31)).first()
        if not periodo:
            periodo = PeriodoReferencia.objects.create(
                data_base=datetime(ano, 1, 1), data_limite=datetime(ano, 12, 31), ano=ano, user=User.objects.order_by('id').first()
            )
        periodo.set_cache(None, periodo.pk)
        self.stdout.write(f'\t[{periodo.pk}] {datetime(ano, 1, 1)} - {datetime(ano, 12, 31)}')
        return periodo

    def set_periodo_mais_utilizado_ano_atual(self):
        ano = datetime.now().year
        self.stdout.write(f'\nPeríodo, mais utilizado no ano atual: {ano}')
        qs = PeriodoReferencia.objects.filter(data_base__year=ano) | PeriodoReferencia.objects.filter(data_limite__year=ano)
        if qs.exists():
            data_base, data_limite, _quant = qs.values_list('data_base', 'data_limite').annotate(quant=Count('id')).order_by('-quant')[:1][0]
            periodo = PeriodoReferencia.objects.filter(data_base=data_base, data_limite=data_limite)[0]
            periodo.set_cache(None, periodo.pk)
            self.stdout.write(f'\t[{periodo.pk}] {datetime(ano, 1, 1)} - {datetime(ano, 12, 31)}')
            return periodo
        else:
            self.stdout.write('Não há dados')
            return None

    def processar(self, variaveis, uos):
        tasks.recuperar_valor(variaveis, uos)

    def handle(self, *args, **options):
        self.stdout.write('Processando variáveis de ambiente')
        forcar = options.get('forcar', False)
        if datetime.now().weekday() == 0 or forcar:
            variaveis = Variavel.objects.all().order_by('sigla')
            uos = UnidadeOrganizacional.objects.uo()

            if self.set_periodo_ano_passado():
                self.processar(variaveis, uos)

            if self.set_periodo_mais_utilizado_ano_atual():
                self.processar(variaveis, uos)
        else:
            self.stdout.write('Não executado, processamento ocorre somente nas segundas-feiras.')
