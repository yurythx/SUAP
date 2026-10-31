from djtools.management.commands import BaseCommandPlus
from materiais.models import Material


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        import tempfile

        import pandas as pd

        data = []
        for material in Material.objects.all():
            tags = [tag.descricao for tag in material.tags.all()]
            data.append(
                {
                    'ID': material.id,
                    'CATMAT': material.codigo_catmat,
                    'DESCRIÇÃO': material.especificacao,
                    'ID CATEGORIA': material.categoria.codigo_completo,
                    'CATEGORIA': material.categoria.descricao,
                    'UNIDADE MEDIDA': material.unidade_medida.descricao,
                    'TAGS': ''.join(tags),
                }
            )

        df = pd.DataFrame(data)

        tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        self.stdout.write(tmp.name)
        df.to_excel(tmp.name, index=False, engine='openpyxl')
