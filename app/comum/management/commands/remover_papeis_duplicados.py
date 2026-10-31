import tqdm
from django.db.models import Count, Max

from djtools.management.commands import BaseCommandPlus
from rh.models import Papel


class Command(BaseCommandPlus):
    help = 'Remove duplicações de Papéis do tipo TIPO_PAPEL_USUARIOEXTERNO'

    def handle(self, *args, **options):
        # Subquery para obter IDs dos registros duplicados
        papeis_duplicados = (
            Papel.objects.filter(
                tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO,
            )
            .values('vinculo', 'descricao')
            .annotate(max_data_inicio=Max('data_inicio'))
            .annotate(duplicate_count=Count('id'))
            .filter(duplicate_count__gt=1)
            .values('vinculo', 'descricao')
        )

        # Atualizar os registros duplicados
        for duplicate in tqdm.tqdm(papeis_duplicados):
            vinculo = duplicate['vinculo']
            descricao = duplicate['descricao']
            latest_role = (
                Papel.objects.filter(
                    vinculo=vinculo,
                    descricao=descricao,
                    tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO,
                )
                .order_by('-data_inicio')
                .first()
            )

            # Filtrar registros anteriores
            previous_roles = Papel.objects.filter(
                vinculo=vinculo,
                descricao=descricao,
                tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO,
            ).exclude(id=latest_role.id)

            # Atualize a data_fim do registro anterior para null
            latest_role.data_fim = None
            latest_role.save()

            # Excluir registros duplicados (exceto o mais recente)
            previous_roles.exclude(id=latest_role.id).delete()

        self.stdout.write(self.style.SUCCESS('Papéis duplicados removidos com sucesso!'))
