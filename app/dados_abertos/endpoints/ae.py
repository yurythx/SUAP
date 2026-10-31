import datetime

from django.db.models import Q
from ninja import Query, Router

from ae.models import Participacao, TipoPrograma
from ae.utils import calcula_valor_programa_generico, calcula_valor_refeicao, calcula_valor_trabalho, calcula_valor_transporte
from djtools.ninja.router import get

from ..schemas.ae import AuxilioOut
from ..schemas.filters import MesAnoFilter

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/auxilios/',
    response=list[AuxilioOut],
    auth=False,
    summary='Tipos de Auxílio',
    description='Retorna o tipo de auxílio, valor executado e quantidade de beneficiários.',
)
def auxilios(request, filtros: MesAnoFilter = Query(...)):  # noqa: B008
    ano = filtros.ano
    mes = filtros.mes
    if mes:
        data_inicio = datetime.date(ano, mes, 1)
        if mes == 12:
            data_termino = datetime.date(ano + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            data_termino = datetime.date(ano, mes + 1, 1) - datetime.timedelta(days=1)
    else:
        data_inicio = datetime.date(ano, 1, 1)
        data_termino = datetime.date(ano, 12, 31)
    # Filtra
    participantes = Participacao.objects.filter(Q(data_inicio__lte=data_termino), Q(data_termino__gte=data_inicio) | Q(data_termino=None)).only(
        'data_inicio', 'data_termino', 'aluno', 'programa', 'programa__tipo_programa'
    )
    lista = []
    for tipo in TipoPrograma.objects.all().order_by('titulo'):
        query = participantes.filter(programa__tipo_programa_id=tipo.id).only('aluno_id')
        valor_executado = None
        total = len(set(query.values_list('aluno_id', flat=True)))
        if tipo.sigla == 'PAS':
            valor_executado = calcula_valor_transporte(query, data_inicio, data_termino)
        elif tipo.sigla == 'TRB':
            valor_executado = calcula_valor_trabalho(query, data_inicio, data_termino)
        elif tipo.sigla == 'ALM':
            valor_executado, total = calcula_valor_refeicao(data_inicio, data_termino)
        elif not tipo.sigla:
            valor_executado = calcula_valor_programa_generico(query, data_inicio, data_termino)
        if total:
            lista.append({'tipo_do_auxilio': tipo.titulo, 'quantidade_de_beneficiarios': total, 'valor_executado': valor_executado})
    return lista
