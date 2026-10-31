"""
Comando para gerar bolsas na aplicação AE
"""

from django.db import DatabaseError, connection, transaction

from djtools.management.commands import BaseCommandPlus
from pesquisa import models as pesquisa


def get_related_object(cls):
    all_related_objects = [f for f in cls._meta.get_fields() if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete]
    for related_object in all_related_objects:
        alias_varname = related_object.get_accessor_name()
        # field_fk = related_object.field.get_attname_column()[1]
        getattr(cls.objects.model, alias_varname)

        # projeto_table_name = cls.objects.model._meta.db_table
        # nome_tabela_pesquisa = 'pesquisa_%s' %cls.objects.model._meta.model_name
        nome_tabela_extensao = f'projetos_{related_object.model._meta.model_name}'

        # sql_join='inner join %s on %s.%s = %s.id_legado' %(projeto_table_name, nome_tabela_extensao, field_fk, projeto_table_name)
        # print 'importar(pesquisa.%s, sql_join=\'%s\')' %(related_object.model.__name__, sql_join)
        # importar(related_objects, sql_join = sql_join)
        print(nome_tabela_extensao)


def dictfetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [dict(list(zip([col[0] for col in desc], row, strict=False))) for row in cursor.fetchall()]


def get_sql_insert(cls):
    sql = cls.objects.all().query.__str__()

    # remove o order by da instrução sql
    pos = sql.find('ORDER BY')
    if pos > 0:
        sql = sql[0:pos]

    # remove inner join
    pos = sql.find('INNER JOIN')
    while pos > 0:
        sql = sql[0:pos]
        pos = sql.find('INNER JOIN')

    nome_tabela = cls.objects.model._meta.db_table
    sql = sql.replace('"', '').replace(f'{nome_tabela}.', '').replace('SELECT id,', f'INSERT INTO {nome_tabela}(').replace(f'FROM {nome_tabela}', ')')

    return sql


def importar(cls, sql=None, sql_where=None, sql_join=None):
    cursor = connection.cursor()
    nome_tabela_pesquisa = f'pesquisa_{cls.objects.model._meta.model_name}'
    nome_tabela_extensao = f'projetos_{cls.objects.model._meta.model_name}'
    print(f'Importando tabela {nome_tabela_pesquisa} ...')

    sql_select = cls.objects.all().query.__str__()

    # remove o order by da instrução sql
    pos = sql_select.find('ORDER BY')
    if pos > 0:
        sql_select = sql_select[0:pos]

    # se já existir registros na tabela, é porque já foi importado, logo não continua
    cursor.execute(f'select exists({sql_select})')
    tem_registros = cursor.fetchall()[0][0]
    if tem_registros:
        print('\t registros já importados')
        return True

    # remove inner join
    pos = sql_select.find('INNER JOIN')
    while pos > 0:
        sql_select = sql_select[0:pos]
        pos = sql_select.find('INNER JOIN')

    # substituir tabela pesquisa por projetos
    sql_select = (
        sql_select.replace(f'"{nome_tabela_pesquisa}"."id",', '')
        .replace(f'"{nome_tabela_pesquisa}"."id_legado"', f'"{nome_tabela_pesquisa}"."id" as id_legado')
        .replace('pesquisa_', 'projetos_')
    )

    if sql_join:
        sql_select = f'{sql_select} {sql_join}'
        # substitui foreign key por id_legado
        for sjoin in sql_join.split('inner join'):
            sjoin = sjoin.strip()
            pos = sjoin.find(nome_tabela_extensao)
            if pos > 0:
                campos_igualdade = sjoin[pos + len(nome_tabela_extensao) + 1 :].split('=')
                campo_fk = campos_igualdade[0].strip()
                campo_id = campos_igualdade[1].split('.')[0].strip() + '.id'
                sql_select = sql_select.replace(f'"{nome_tabela_extensao.strip()}"."{campo_fk}"', f'{campo_id} as {campo_fk}')

    if sql_where:
        sql_select = f'{sql_select} {filter}'

    sql_insert = get_sql_insert(cls)
    sql = sql_insert + ' ' + sql_select

    try:
        cursor.execute(sql)
        transaction.commit_unless_managed()
    except DatabaseError as e:
        print(sql)
        raise e
    else:
        return True
    return False


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # get_related_object(pesquisa.Projeto)
        # return
        importar(pesquisa.Edital, sql_where="where tipo_edital in ('2', '3', '5')")
        importar(pesquisa.ParametroEdital, sql_join='inner join pesquisa_edital on projetos_parametroedital.edital_id = pesquisa_edital.id_legado')
        importar(
            pesquisa.CriterioAvaliacao, sql_join='inner join pesquisa_edital on projetos_criterioavaliacao.edital_id = pesquisa_edital.id_legado'
        )
        importar(pesquisa.Recurso, sql_join='inner join pesquisa_edital on projetos_recurso.edital_id = pesquisa_edital.id_legado')
        importar(pesquisa.BolsaDisponivel, sql_join='inner join pesquisa_edital on projetos_bolsadisponivel.edital_id = pesquisa_edital.id_legado')
        importar(pesquisa.EditalAnexo, sql_join='inner join pesquisa_edital on projetos_editalanexo.edital_id = pesquisa_edital.id_legado')
        importar(pesquisa.Projeto, sql_join='inner join pesquisa_edital on projetos_projeto.edital_id = pesquisa_edital.id_legado')
        importar(
            pesquisa.EditalAnexoAuxiliar, sql_join='inner join pesquisa_edital on projetos_editalanexoauxiliar.edital_id = pesquisa_edital.id_legado'
        )
        importar(
            pesquisa.ComissaoEditalPesquisa,
            sql_join='inner join pesquisa_edital on projetos_comissaoeditalpesquisa.edital_id = pesquisa_edital.id_legado',
        )

        importar(
            pesquisa.AvaliadorIndicado, sql_join='inner join pesquisa_projeto on projetos_avaliadorindicado.projeto_id = pesquisa_projeto.id_legado'
        )
        importar(pesquisa.Avaliacao, sql_join='inner join pesquisa_projeto on projetos_avaliacao.projeto_id = pesquisa_projeto.id_legado')
        importar(
            pesquisa.ItemMemoriaCalculo, sql_join='inner join pesquisa_projeto on projetos_itemmemoriacalculo.projeto_id = pesquisa_projeto.id_legado'
        )
        importar(
            pesquisa.ParametroProjeto,
            sql_join="""inner join pesquisa_projeto on projetos_parametroprojeto.projeto_id = pesquisa_projeto.id_legado
                                                        inner join pesquisa_parametroedital on projetos_parametroprojeto.parametro_edital_id = pesquisa_parametroedital.id_legado
                                                      """,
        )
        importar(
            pesquisa.Desembolso,
            sql_join="""inner join pesquisa_projeto on projetos_desembolso.projeto_id = pesquisa_projeto.id_legado
                                                  inner join pesquisa_itemmemoriacalculo on projetos_desembolso.item__id = pesquisa_itemmemoriacalculo.id_legado
        """,
        )
        importar(
            pesquisa.ProjetoAnexo,
            sql_join="""inner join pesquisa_projeto on projetos_projetoanexo.projeto_id = pesquisa_projeto.id_legado
                                                    inner join pesquisa_editalanexo on projetos_projetoanexo.anexo_edital_id = pesquisa_editalanexo.id_legado
        """,
        )
        importar(pesquisa.Meta, sql_join='inner join pesquisa_projeto on projetos_meta.projeto_id = pesquisa_projeto.id_legado')
        importar(
            pesquisa.RegistroConclusaoProjeto,
            sql_join='inner join pesquisa_projeto on projetos_registroconclusaoprojeto.projeto_id = pesquisa_projeto.id_legado',
        )
        importar(pesquisa.Participacao, sql_join='inner join pesquisa_projeto on projetos_participacao.projeto_id = pesquisa_projeto.id_legado')
        importar(pesquisa.FotoProjeto, sql_join='inner join pesquisa_projeto on projetos_fotoprojeto.projeto_id = pesquisa_projeto.id_legado')
        importar(
            pesquisa.HistoricoEquipe,
            sql_join="""inner join pesquisa_projeto on projetos_historicoequipe.projeto_id = pesquisa_projeto.id_legado
                                                       inner join pesquisa_participacao on projetos_historicoequipe.participante_id = pesquisa_participacao.id_legado
        """,
        )
        importar(
            pesquisa.ProjetoHistoricoDeEnvio,
            sql_join='inner join pesquisa_projeto on projetos_projetohistoricodeenvio.projeto_id = pesquisa_projeto.id_legado',
        )
        importar(
            pesquisa.ProjetoCancelado,
            sql_join="""inner join pesquisa_projeto on projetos_projetocancelado.projeto_id = pesquisa_projeto.id_legado
                                                        inner join pesquisa_projeto on projetos_projetocancelado.proximo_projeto_id = pesquisa_projeto.id_legado
        """,
        )
        importar(pesquisa.RecursoProjeto, sql_join='inner join pesquisa_projeto on projetos_recursoprojeto.projeto_id = pesquisa_projeto.id_legado')

        # faltando Importar
        # AvaliadorExterno
        # Etapas
        # Etapas_integrantes
        # ItemAvaliacao
        # RegistroExecucaoEtapa
        # RegistroGasto
        # ComissaoEditalPesquisa_membros

        # via fixtures
        # AreaConhecimento
        # Parametro
