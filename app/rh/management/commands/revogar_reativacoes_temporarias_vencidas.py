from django.utils.dateparse import parse_date

from comum.models import Vinculo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_datetime_now, sync_ldap_user
from rh.models import ServidorReativacaoTemporaria


class Command(BaseCommandPlus):
    help = 'Sincroniza o encerramento por prazo das reativações temporárias autorizadas que já venceram.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--data-referencia',
            action='store',
            dest='data_referencia',
            default=None,
            help='Data de referência no formato YYYY-MM-DD. Por padrão usa a data atual.',
        )

    def handle(self, *args, **options):
        data_referencia = self._get_data_referencia(options.get('data_referencia'))
        get_datetime_now()
        qs = (
            ServidorReativacaoTemporaria.objects.filter(
                data_fim__lt=data_referencia,
                situacao=ServidorReativacaoTemporaria.STATUS_AUTORIZADA,
            )
            .select_related('servidor__pessoa_fisica')
            .order_by('data_fim', 'pk')
        )

        total = qs.count()
        self.stdout.write(f'{total} reativações temporárias autorizadas vencidas pendentes de sincronização.')

        for reativacao in qs:
            servidor = reativacao.servidor
            self.stdout.write(f'Processando {servidor.matricula} - {servidor.pessoa_fisica.nome}')

            vinculo = servidor.get_vinculo()
            if vinculo and not servidor.ativo and vinculo.ativo:
                Vinculo.objects.filter(pk=vinculo.pk).update(ativo=False)

            user = servidor.get_user()
            if user:
                user.save()

            sync_ldap_user(servidor.matricula)

        self.stdout.write(f'{total} reativações temporárias processadas.')

    def _get_data_referencia(self, valor):
        if not valor:
            return get_datetime_now().date()
        data_referencia = parse_date(valor)
        if not data_referencia:
            raise ValueError('Informe --data-referencia no formato YYYY-MM-DD.')
        return data_referencia
