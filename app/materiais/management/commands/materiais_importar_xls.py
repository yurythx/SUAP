from decimal import Decimal

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from materiais.models import Categoria, Material, MaterialCotacao, MaterialTag


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        # cadastra/atualiza material
        def cadastra_material(id_material, catmat, descricao, especificacao, categoria_id, unidade_id, tag_id, p1, o1, p2, o2, p3, o3):
            # se não tem ID, cadastra, se tem, atualiza
            material = None
            inserindo = False

            if id_material == '' or id_material == '-':
                inserindo = True
                material = Material()
            else:
                self.stdout.write(f'Buscando material... {int(id_material)}')
                material = Material.objects.get(pk=id_material)

            material.codigo_catmat = catmat
            material.descricao = descricao
            material.especificacao = especificacao
            material.unidade_medida_id = unidade_id

            if categoria_id:
                material.categoria_id = categoria_id

            material.save()

            self.stdout.write(f'Procurando tag_id {int(tag_id)}')
            tag = MaterialTag.objects.get(pk=int(tag_id))

            if not inserindo:
                # antes de atualizar limpa as cotações de preços antigas
                self.stdout.write(f'Excluindo cotacoes antigas do material {material.descricao}')
                material.materialcotacao_set.all().delete()

            # cadastra/atualiza tags
            material.tags.add(tag)

            # cotação 1?
            if p1:
                self.stdout.write('     <<< Cadastrando cotação 1')
                cotacao = MaterialCotacao()
                cotacao.referencia = o1
                cotacao.valor = Decimal(str(p1))  # sem esse cast ocorre erro em produção (Python 2.6)
                material.materialcotacao_set.add(cotacao)

            # cotação 2?
            if p2:
                self.stdout.write('     <<< Cadastrando cotação 2')
                cotacao = MaterialCotacao()
                cotacao.referencia = o2
                cotacao.valor = Decimal(str(p2))
                material.materialcotacao_set.add(cotacao)

            # cotação 3?
            if p3:
                self.stdout.write('     <<< Cadastrando cotação 3')
                cotacao = MaterialCotacao()
                cotacao.referencia = o3
                cotacao.valor = Decimal(str(p3))
                material.materialcotacao_set.add(cotacao)

        # parâmetros informados?
        if len(args) != 1:
            self.stdout.write('Arquivo XLS não informado.\n')
            self.stdout.write('python manage.py materiais_importar_xls /tmp/arquivo.xls\n')
            return

        # tratando XLS
        arquivo_xls = args[0]
        self.stdout.write(f'Importando materiais a partir do arquivo XLS: {args[0]}')
        import pandas as pd

        df = pd.read_excel(arquivo_xls, header=None)
        self.stdout.write('Verificando planilha...')

        for index, row in df.iloc[1:].iterrows():
            id = row.iloc[2]
            catmat = row.iloc[3]
            descricao = str(row.iloc[4]).strip()
            especificacao = str(row.iloc[5]).strip()
            unidade_id = row.iloc[6]
            tag_id = row.iloc[8]
            categoria_id = None
            p1 = str(row.iloc[10]).replace('.', '').replace(',', '.')
            o1 = str(row.iloc[11]).strip()
            p2 = str(row.iloc[12]).replace('.', '').replace(',', '.')
            o2 = str(row.iloc[13]).strip()
            p3 = str(row.iloc[14]).replace('.', '').replace(',', '.')
            o3 = str(row.iloc[15]).strip()

            # ajustando CATMAT vazio
            if pd.isna(catmat) or catmat == '' or catmat == '-':
                catmat = '000000'
            else:
                catmat = str(int(catmat))  # ao importar o xls insere um ".0" no final (float)

            # verificando linhas sem categorias
            if not pd.isna(row.iloc[17]) and row.iloc[17] != '':
                categoria_id = Categoria.objects.get(codigo_completo=str(row.iloc[17])).pk
            else:
                categoria_id = None
                self.stdout.write(f'Categoria nao informada na linha {index} / {descricao}')

            self.stdout.write(f'Cadastrando item {index}... (id: {id})')
            cadastra_material(id, catmat, descricao, especificacao, categoria_id, unidade_id, tag_id, p1, o1, p2, o2, p3, o3)
