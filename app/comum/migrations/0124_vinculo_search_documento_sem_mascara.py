from django.db import migrations
from django.db.models import Case, CharField, Exists, F, Func, Max, Min, OuterRef, Subquery, Value, When
from django.db.models.functions import NullIf, RTrim, StrIndex, Upper

# lote pequeno: cada UPDATE trava as linhas do lote e reescreve o índice trigram do search (8 a 58 s por 10 mil no dev)
LOTE = 2_000


def _documento_sem_mascara(apps):
    """CPF (pessoa física) ou CNPJ (jurídica) do vínculo, sem pontuação e em maiúsculas, como ``Vinculo.cpf_ou_cnpj_sem_mascara``."""
    pf = apps.get_model('rh', 'PessoaFisica')._base_manager.filter(pk=OuterRef('pessoa_id')).order_by()
    pj = apps.get_model('rh', 'PessoaJuridica')._base_manager.filter(pk=OuterRef('pessoa_id')).order_by()
    documento = Case(When(Exists(pf), then=Subquery(pf.values('cpf'))), default=Subquery(pj.values('cnpj')), output_field=CharField())
    return Upper(Func(documento, Value(r'\W'), Value(''), Value('g'), function='REGEXP_REPLACE', output_field=CharField()))


def anexar_documento_sem_mascara(apps, schema_editor):
    """Anexa ao ``Vinculo.search`` o documento sem máscara, na forma que o ``SearchField.pre_save`` grava (último atributo).

    Idempotente: pula o vínculo cujo ``search`` já contém o documento.
    """
    vinculos = apps.get_model('comum', 'Vinculo')._base_manager
    faixa = vinculos.aggregate(inicio=Min('id'), fim=Max('id'))
    if faixa['inicio'] is None:
        return
    a_atualizar = (
        vinculos.annotate(documento=_documento_sem_mascara(apps))
        .filter(documento__gt='')
        .annotate(posicao=StrIndex('search', F('documento')))
        .filter(posicao=0)
    )
    # o mesmo que o pre_save: separado por espaço, sem o espaço que o legado deixava no fim
    novo_search = Func(Value(' '), NullIf(RTrim('search'), Value('')), F('documento'), function='CONCAT_WS', output_field=CharField())
    # lotes por faixa de id, cada um na sua transação (atomic = False): não trava a tabela inteira de uma vez
    for de in range(faixa['inicio'], faixa['fim'] + 1, LOTE):
        a_atualizar.filter(id__gte=de, id__lt=de + LOTE).update(search=novo_search)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('comum', '0123_pais_iso_alfa3'),
    ]

    operations = [migrations.RunPython(anexar_documento_sem_mascara, migrations.RunPython.noop, elidable=True)]
