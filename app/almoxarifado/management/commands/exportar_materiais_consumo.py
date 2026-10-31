from django.db import connection

from djtools.db import has_column
from djtools.management.commands import BaseCommandPlus
from materiais.models import Categoria


class Command(BaseCommandPlus):
    def executar_sql(self, sql):
        cur = connection.cursor()
        cur.execute(sql)
        connection._commit()

    def evoluir_tabelas(self):
        sql = """
            ALTER TABLE "materiais_categoria" ADD COLUMN "ativa" boolean  DEFAULT True;
            ALTER TABLE "materiais_categoria" ALTER COLUMN "ativa" DROP DEFAULT;
            ALTER TABLE "materiais_categoria" ALTER COLUMN "ativa" SET NOT NULL;
        """
        if not has_column('materiais_categoria', 'ativa'):
            self.executar_sql(sql)

    def remover_chaves_estrangeiras(self):
        sql = """
            ALTER TABLE almoxarifado_configuracaoestoque DROP CONSTRAINT "almoxarifado_configuracaoestoque_material_id_fkey";
            ALTER TABLE empenhoconsumo DROP CONSTRAINT "material_id_referencing_materialconsumo_id";
            ALTER TABLE requisicaoalmoxuomaterial DROP CONSTRAINT "material_id_referencing_materialconsumo_id_1";
            ALTER TABLE movimentoalmoxentrada DROP CONSTRAINT "movimentoalmoxentrada_material_id_fkey";
            ALTER TABLE movimentoalmoxsaida DROP CONSTRAINT "movimentoalmoxsaida_material_id_fkey";
            ALTER TABLE requisicaoalmoxusermaterial DROP CONSTRAINT "requisicaoalmoxusermaterial_material_id_fkey";
        """
        self.executar_sql(sql)

    def adicionar_chaves_estrangeiras(self):
        sql = """
            ALTER TABLE almoxarifado_configuracaoestoque ADD CONSTRAINT "almoxarifado_configuracaoestoque_material_id_fkey" FOREIGN KEY (material_id) REFERENCES materiais_material (id);
            ALTER TABLE empenhoconsumo ADD CONSTRAINT "material_id_referencing_materialconsumo_id" FOREIGN KEY (material_id) REFERENCES materiais_material (id);
            ALTER TABLE requisicaoalmoxuomaterial ADD CONSTRAINT "material_id_referencing_materialconsumo_id_1" FOREIGN KEY (material_id) REFERENCES materiais_material (id);
            ALTER TABLE movimentoalmoxentrada ADD CONSTRAINT "movimentoalmoxentrada_material_id_fkey" FOREIGN KEY (material_id) REFERENCES materiais_material (id);
            ALTER TABLE movimentoalmoxsaida ADD CONSTRAINT "movimentoalmoxsaida_material_id_fkey" FOREIGN KEY (material_id) REFERENCES materiais_material (id);
            ALTER TABLE requisicaoalmoxusermaterial ADD CONSTRAINT "requisicaoalmoxusermaterial_material_id_fkey" FOREIGN KEY (material_id) REFERENCES materiais_material (id);
        """
        self.executar_sql(sql)

    def inativar_categorias(self):
        Categoria.objects.filter(codigo='00').update(ativa=False)

    def handle(self, *args, **options):
        self.evoluir_tabelas()
        self.stdout.write('tabelas evoluidas')
        self.exportar_materiais()
        self.stdout.write('materiais exportados')
        self.remover_chaves_estrangeiras()
        self.stdout.write('chaves estrangeiras removidas')
        self.atualizar_referencias()
        self.stdout.write('referencias atualizadas')
        self.adicionar_chaves_estrangeiras()
        self.stdout.write('chaves estrangeiras adicionadas')
        self.inativar_categorias()
        self.stdout.write('categorias inativadas')
        self.stdout.write('MIGRACAO CONCLUIDA COM SUCESSO!')
