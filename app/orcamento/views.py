from datetime import datetime
from decimal import Decimal

from django.apps import apps
from django.db.models import Q

from comum.models import Configuracao
from comum.utils import get_uo
from djtools import db
from djtools.utils import group_required, httprr, rtr
from financeiro.forms import NotaCreditoConsultaForm, NotaDotacaoConsultaForm
from financeiro.models import Evento, NaturezaDespesa, NEItem, NEListaItens, NotaCredito, NotaDotacao, NotaEmpenho, UnidadeGestora
from financeiro.utils import (
    get_eventos_desatualizados_notascredito,
    get_eventos_desatualizados_notascreditodotacao,
    get_eventos_utilizados_notascreditodotacao,
)
from orcamento.forms import ExecucaoOrcamentariaUGFiltroForm, NotaEmpenhoConsultaForm, NotasFiltroForm
from rh.models import Pessoa


@rtr('orcamento/templates/execucao_orcamentaria.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def execucao_orcamentaria(request):
    title = 'Execução orçamentária'
    config_ug = Configuracao._get_conf_por_chave('orcamento', 'unidade_responsavel')

    # verifica se a unidade gestora responsável ex: ifrn = 158155 foi configurada
    if not config_ug:
        msg = 'A unidade gestora responsável não está configurada.'
        return locals()

    # indica o ano utilizado para filtrar a consulta
    #    anos = get_anos_importados()
    #    if request.method == 'POST':
    #        ano = request.POST['ano_base']
    #    else:
    #        ano = anos[0]

    # consulta as datas dos ultimos arquivos importados
    datas = {}

    try:
        datas['credito'] = NotaCredito.objects.latest('datahora_emissao').datahora_emissao
    except Exception:
        pass

    try:
        datas['dotacao'] = NotaDotacao.objects.latest('datahora_emissao').datahora_emissao
    except Exception:
        pass

    try:
        datas['empenho'] = NotaEmpenho.objects.latest('data_emissao').data_emissao
    except Exception:
        pass

    try:
        ugr = UnidadeGestora.objects.get(codigo=config_ug.valor)

        if request.user.has_group_cached('Administrador de Orçamento'):
            # seleciona quais os eventos estão aparecendo em notas de crédito importadas mas que não estão identificados como crédito ou débito
            eventos = get_eventos_desatualizados_notascredito()

            if len(eventos):
                return locals()

            lista_creditos = ','.join(str(i) for i in Evento.list_creditos())
            lista_debitos = ','.join(str(i) for i in Evento.list_debitos())

            # lista as unidades administrativas que receberam recursos através de notas de crédito emitidos pela ug responsável
            sql = f"""select t.nome as nome,
                            t.id as id,
                            t.setor_id as setor_id,
                            sum(t.credito) as credito,
                            sum(t.debito) as debito
                        from (select u.nome as nome,
                                   u.id as id,
                                   u.setor_id as setor_id,
                                case when e.tipo in ({lista_creditos})
                                then sum(i.valor)
                                end as credito,
                                case when e.tipo in ({lista_debitos})
                                then sum(i.valor)
                                end as debito
                            from financeiro_notacredito n,
                                financeiro_notacreditoitem i,
                                financeiro_evento e,
                                financeiro_unidadegestora u
                            where n.id = i.nota_credito_id and
                                u.id = n.favorecido_ug_id and
                                e.id = i.evento_id and
                                e.tipo is not null
                                group by u.nome, u.id, u.setor_id, e.tipo
                            union
                            select u.nome as nome,
                                   u.id as id,
                                   u.setor_id as setor_id,
                                case when e.tipo in ({lista_debitos})
                                then sum(i.valor)
                                end as credito,
                                case when e.tipo in ({lista_creditos})
                                then sum(i.valor)
                                end as debito
                            from financeiro_notacredito n,
                                financeiro_notacreditoitem i,
                                financeiro_evento e,
                                financeiro_unidadegestora u
                            where n.id = i.nota_credito_id and
                                u.id = n.emitente_ug_id and
                                e.id = i.evento_id and
                                e.tipo is not null
                                group by u.nome, u.id, u.setor_id, e.tipo) t
                            group by t.nome, t.id, t.setor_id
                                order by t.nome;"""

            # descentralizações realizadas pela ug cadastrada como responsável
            orcamentos = []

            for c in db.get_dict(sql):
                credito = c['credito'] or Decimal(0)
                debito = c['debito'] or Decimal(0)

                # evita quebra caso o módulo de planejamento não esteja instalado
                try:
                    if c['setor_id']:
                        ano_atual = apps.get_model('comum', 'ano').objects.get(ano=datetime.now().year)
                        sqlValorPrevisto = """SELECT SUM(pat.quantidade * pat.valor_unitario) as valor
                                                FROM planejamento_atividade pat, planejamento_acao pac, planejamento_metaunidade pmu,
                                                    planejamento_unidadeadministrativa pua, setor str,
                                                    planejamento_configuracao pco, planejamento_origemrecurso por
                                                WHERE pac.id = pat.acao_id
                                                    AND pmu.id = pac.meta_unidade_id
                                                    AND pua.id = pmu.unidade_id
                                                    AND str.id = pua.setor_equivalente_id
                                                    AND pac.status = 'Deferida'
                                                    AND pat.valor_unitario != 0.00
                                                    AND str.id = {}
                                                    AND pco.id = pua.configuracao_id
                                                    AND pco.ano_base_id = {}
                                                    AND por.id = pat.tipo_recurso_id
                                                    AND pco.id = por.configuracao_id
                                                GROUP BY str.sigla
                                                ORDER BY str.sigla;""".format(
                            c['setor_id'],
                            ano_atual.id,
                        )
                        cns = db.get_dict(sqlValorPrevisto)
                        valor_previsto = cns[0]['valor'] if cns else 0
                    else:
                        valor_previsto = 0
                except Exception:
                    valor_previsto = 0

                # evita quebra caso o módulo de planejamento não esteja instalado
                try:
                    lista_empenhos = ','.join(str(i) for i in Evento.list_empenhos())
                    # calcula o valor dos empenhos da ug
                    # apesar de existir a possibilidade de calcular o valor de total de um empenho (contando as anulações e os reforços)
                    # através de métodos do modelo NotaEmpenho, e desta forma não utilizar sql, o tempo destinado a criação do template é grande
                    # por este motivo foi utilizado um recurso do postgres, que permite uma consulta recursida em uma tabela, deste modo
                    # a consulta retorna o valor total de cada empenho, e a partir do tipo de evento utilizado, é possível verificar quando
                    # houve retorno, reforço, anulação ou cancelamento
                    sqlValorEmpenhos = """with recursive empenhos (id, ref, valor) as
                                        (select n.id as empenho, n.referencia_empenho_id as ref, n.valor, e.tipo as evento
                                                from financeiro_notaempenho n, financeiro_evento e
                                                where e.id = n.evento_id and
                                                      n.referencia_empenho_id in (select id
                                                                                        from financeiro_notaempenho ne
                                                                                        where ne.emitente_ug_id = {} and
                                                                                            referencia_empenho_id is null and
                                                                                            referencia_empenho_original = '')
                                        UNION ALL
                                        select n.id as empenho, n.referencia_empenho_id as ref, n.valor, e.tipo as evento
                                                from financeiro_notaempenho n
                                                     INNER JOIN empenhos ON n.referencia_empenho_id = empenhos.id,
                                                     financeiro_evento e
                                                where e.id = n.evento_id
                                        )
                                        select sum(valor) - sum(desconto) as total
                                        from (select case when evento not in ({})
                                                        then sum(valor)
                                                    end as desconto,
                                                    case when evento in ({})
                                                        then sum(valor)
                                                    end as valor from (select n.id as empenho, n.referencia_empenho_id as ref, n.valor, e.tipo as evento
                                                                        from financeiro_notaempenho n, financeiro_evento e
                                                                        where e.id = n.evento_id and n.id in (select id
                                                                                                            from financeiro_notaempenho ne
                                                                                                            where ne.emitente_ug_id = {} and
                                                                                                                referencia_empenho_id is null and
                                                                                                                referencia_empenho_original = '')
                                                                        UNION
                                                                        select id, ref, valor, evento from empenhos) t
                                                        group by evento) g;""".format(
                        c['id'],
                        lista_empenhos,
                        lista_empenhos,
                        c['id'],
                    )
                    valor_gasto = db.get_dict(sqlValorEmpenhos)[0]['total'] or 0
                except Exception:
                    valor_gasto = 0

                orcamentos.append(
                    {
                        'id': c['id'],
                        'nome': c['nome'],
                        'previsto': valor_previsto,
                        'descentralizado': (credito - debito),
                        'gasto': valor_gasto,
                        'saldo_indisponivel': (valor_previsto - (credito - debito)) if valor_previsto else None,
                        'saldo_disponivel': ((credito - debito) - valor_gasto),
                    }
                )

            if not orcamentos:
                msg = f'Não existem notas de crédito emitidas pela unidade gestora responsável. Unidade gestora cadastrada: {config_ug.valor}'

        else:
            try:
                # verifica qual a unidade gestora com o setor do usuário
                uo = get_uo()
                ug = UnidadeGestora.objects.get(setor=uo.setor)

                if ug.funcao == 'Executora':
                    return httprr(f'/orcamento/execucaoorcamentaria/ug/exec/{ug.id}/')
                elif ug.funcao == 'Controle':
                    return httprr(f'/orcamento/execucaoorcamentaria/ug/cont/{ug.id}/')
                else:
                    msg = 'O tipo da unidade gestora não pode ser encontrado.'
            except Exception:
                msg = 'A unidade gestora referente ao setor de lotação do usuário logado não foi encontrada.'
    except Exception:
        msg = f'Não existem notas de crédito emitidas pela unidade gestora responsável. Unidade gestora cadastrada: {config_ug.valor}'

    return locals()


@rtr('orcamento/templates/execucao_orcamentaria_ug_exec.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def execucao_orcamentaria_ug_exec(request, id_ug):
    title = 'Ex. orçamentária da UG'
    ug = UnidadeGestora.objects.get(id=id_ug)

    eventos = get_eventos_desatualizados_notascreditodotacao(ug)

    str_eventos_creditos = ','.join(str(i) for i in Evento.list_creditos())
    str_eventos_debitos = ','.join(str(i) for i in Evento.list_debitos())

    sql = f"""select s.nt_id as nt_id, s.nt_nome as nt_nome,
                   s.fr_id as fr_id, s.fr_nome as fr_nome,
                   s.ug_codigo as ug_codigo,
                   s.ug_id as ug_id, s.ug_nome as ug_nome,
                   sum(s.credito) as credito,
                   sum(s.debito) as debito
            from
            (select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
            from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notacredito n,
                    financeiro_notacreditoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_credito_id and
                    u.id = n.favorecido_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    e.tipo is not null and
                    u.id = {id_ug}
                    group by d.codigo, d.nome, f.codigo,
                         f.nome, e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
            group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo
            union
            select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
            from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notadotacao n,
                    financeiro_notadotacaoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_dotacao_id and
                    u.id = n.emitente_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    e.tipo is not null and
                    u.id = {id_ug}
                    group by d.codigo, d.nome, f.codigo, f.nome,
                         e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
            group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo) s
            group by s.nt_id, s.nt_nome, s.fr_id, s.fr_nome, s.ug_id, s.ug_nome, s.ug_codigo;"""

    despesas = []
    nats = []
    for d in db.get_dict(sql):
        try:
            # identifica se trata-se de uma ug executora ou de controle (conhecida como ugr)
            # calcula o valor dos empenhos e fl's
            if str(id_ug) == str(d['ug_id']):
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr=None,
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )
            else:
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr__id=d['ug_id'],
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )

            valor_utilizado = 0
            for empenho in empenhos:
                valor_utilizado += empenho.get_valor_empenhado()
        except Exception:
            valor_utilizado = 0

        credito = Decimal(d['credito']) if d['credito'] else Decimal(0)
        debito = Decimal(d['debito']) if d['debito'] else Decimal(0)

        item = {
            'natureza_despesa_id': d['nt_id'],
            'natureza_despesa_nome': d['nt_nome'],
            'fonte_recurso_id': d['fr_id'],
            'fonte_recurso_nome': d['fr_nome'],
            'unidade_gestora_codigo': d['ug_codigo'],
            'unidade_gestora_id': d['ug_id'],
            'unidade_gestora_nome': d['ug_nome'],
            'descentralizado': (credito - debito),
            'utilizado': valor_utilizado,
            'saldo_disponivel': ((credito - debito) - valor_utilizado),
        }

        despesas.append(item)

    form = ExecucaoOrcamentariaUGFiltroForm()
    return locals()


@rtr('orcamento/templates/execucao_orcamentaria_ug_cont.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def execucao_orcamentaria_ug_cont(request, id_ug):
    title = 'Ex. orçamentária da UG'
    ug = UnidadeGestora.objects.get(id=id_ug)

    eventos = get_eventos_desatualizados_notascreditodotacao(ug)

    str_eventos_creditos = ','.join(str(i) for i in Evento.list_creditos())
    str_eventos_debitos = ','.join(str(i) for i in Evento.list_debitos())

    sql = f"""select s.nt_id as nt_id, s.nt_nome as nt_nome,
                    s.fr_id as fr_id, s.fr_nome as fr_nome,
                    s.ugr_id as ugr_id, s.ugr_nome as ugr_nome,
                    s.ugr_codigo as ugr_codigo,
                    s.ug_id as ug_id, s.ug_nome as ug_nome,
                    s.ug_codigo as ug_codigo,
                    sum(s.credito) as credito,
                    sum(s.debito) as debito
            from
            (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    u2.id as ugr_id, u2.nome as ugr_nome,
                    u2.codigo as ugr_codigo,
                    u.id as ug_id, u.nome as ug_nome,
                    u.codigo as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                    from financeiro_notacredito n,
                    financeiro_notacreditoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                    where n.id = i.nota_credito_id and
                    u.id = n.favorecido_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u2.id = {id_ug}
                    group by d.codigo, d.nome, f.codigo, f.nome,
                         e.tipo, u.id, u.nome, u.codigo,
                         u2.id, u2.nome, u2.codigo,
                         u.id, u.nome, u.codigo
            union
            select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    u2.id as ugr_id, u2.nome as ugr_nome,
                    u2.codigo as ugr_codigo,
                    u.id as ug_id, u.nome as ug_nome,
                    u.codigo as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                    from financeiro_notadotacao n,
                    financeiro_notadotacaoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                    where n.id = i.nota_dotacao_id and
                    u.id = n.emitente_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u2.id = {id_ug}
                    group by d.codigo, d.nome, f.codigo, f.nome,
                         e.tipo, u.id, u.nome, u.codigo,
                         u2.id, u2.nome, u2.codigo,
                         u.id, u.nome, u.codigo) s
            group by s.nt_id, s.nt_nome, s.fr_id, s.fr_nome,
                s.ugr_id, s.ugr_nome, s.ugr_codigo,
                s.ug_id, s.ug_nome, s.ug_codigo;"""

    despesas = []
    for d in db.get_dict(sql):
        try:
            # identifica se trata-se de uma ug executora ou de controle (conhecida como ugr)
            # calcula o valor dos empenhos e fl's
            empenhos = NotaEmpenho.objects.filter(
                emitente_ug__id=d['ug_id'],
                ugr=id_ug,
                fonte_recurso__codigo=d['fr_id'],
                natureza_despesa__codigo=d['nt_id'],
                referencia_empenho=None,
                referencia_empenho_original='',
            )

            valor_utilizado = 0
            for empenho in empenhos:
                valor_utilizado += empenho.get_valor_empenhado()
        except Exception:
            valor_utilizado = 0

        credito = Decimal(d['credito']) if d['credito'] else Decimal(0)
        debito = Decimal(d['debito']) if d['debito'] else Decimal(0)

        item = {
            'natureza_despesa_id': d['nt_id'],
            'natureza_despesa_nome': d['nt_nome'],
            'fonte_recurso_id': d['fr_id'],
            'fonte_recurso_nome': d['fr_nome'],
            'unidade_gestora_codigo': d['ug_codigo'],
            'unidade_gestora_id': d['ug_id'],
            'unidade_gestora_nome': d['ug_nome'],
            'unidade_gestora_responsavel_codigo': d['ugr_codigo'],
            'unidade_gestora_responsavel_id': d['ugr_id'],
            'unidade_gestora_responsavel_nome': d['ugr_nome'],
            'descentralizado': (credito - debito),
            'utilizado': valor_utilizado,
            'saldo_disponivel': ((credito - debito) - valor_utilizado),
        }

        despesas.append(item)
    form = ExecucaoOrcamentariaUGFiltroForm()
    return locals()


@rtr('orcamento/templates/execucao_orcamentaria_ugr.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def execucao_orcamentaria_ugr(request, id_ug, id_ugr):
    title = 'Ex. orçamentária da UGR'
    ug = UnidadeGestora.objects.get(id=id_ug)
    ugr = UnidadeGestora.objects.get(id=id_ugr)

    # é preciso consultar os seguintes valores
    # 1. notas de credito onde o favorecido é a ug de id_ug
    # 2. notas de dotacao onde o emitente é a ug de id_ug
    # 3. notas de dotacao onde a ugr é id_ug

    str_eventos_creditos = ','.join(str(i) for i in Evento.list_creditos())
    str_eventos_debitos = ','.join(str(i) for i in Evento.list_debitos())

    sql = f"""select * from
            (select s.nt_id as nt_id, s.nt_nome as nt_nome,
                   s.fr_id as fr_id, s.fr_nome as fr_nome,
                   s.ug_codigo as ug_codigo,
                   s.ug_id as ug_id, s.ug_nome as ug_nome,
                   sum(s.credito) as credito,
                   sum(s.debito) as debito
                from
                (select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
                from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notacredito n,
                    financeiro_notacreditoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_credito_id and
                    u.id = n.favorecido_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u.id = {id_ug}
                    group by d.codigo, d.nome, f.codigo,
                     f.nome, e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
                group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo
                union
                select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
                from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notadotacao n,
                    financeiro_notadotacaoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_dotacao_id and
                    u.id = n.emitente_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u.id = {id_ug}
                    group by d.codigo, d.nome, f.codigo, f.nome,
                     e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
                group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo) s
                group by s.nt_id, s.nt_nome, s.fr_id, s.fr_nome, s.ug_id, s.ug_nome, s.ug_codigo
                order by s.ug_codigo desc, s.nt_id, s.nt_nome, s.fr_id, s.fr_nome) r
                where r.ug_id = {id_ugr};"""
    consulta = db.get_dict(sql)

    despesas = []
    for d in consulta:
        # evita quebra caso o módulo de planejamento não esteja instalado
        try:
            ano_atual = apps.get_model('comum', 'ano').objects.get(ano=datetime.now().year)
            sqlValorPrevisto = f"""SELECT SUM(pat.quantidade * pat.valor_unitario) as valor
                                    FROM planejamento_atividade pat, planejamento_acao pac, planejamento_metaunidade pmu,
                                        planejamento_unidadeadministrativa pua, setor str,
                                        planejamento_configuracao pco
                                    WHERE pac.id = pat.acao_id
                                        AND pmu.id = pac.meta_unidade_id
                                        AND pua.id = pmu.unidade_id
                                        AND str.id = pua.setor_equivalente_id
                                        AND pac.status = 'Deferida'
                                        AND pat.valor_unitario != 0.00
                                        AND str.id = {ug.setor.id}
                                        AND pco.id = pua.configuracao_id
                                        AND pco.ano_base_id = {ano_atual.id}
                                    GROUP BY str.sigla
                                    ORDER BY str.sigla;"""
            cns = db.get_dict(sqlValorPrevisto)
            # valor_previsto = cns[0]['valor'] if cns else 0
            valor_previsto = 0
        except Exception:
            valor_previsto = 0

        try:
            # identifica se trata-se de uma ug executora ou de controle (conhecida como ugr)
            # calcula o valor dos empenhos e fl's
            if str(id_ug) == str(d['ug_id']):
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr=None,
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )
            else:
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr__id=d['ug_id'],
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )

            valor_gasto = 0
            for empenho in empenhos:
                valor_gasto += empenho.get_valor_empenhado()
        except Exception:
            valor_gasto = 0

        credito = Decimal(d['credito']) if d['credito'] else Decimal(0)
        debito = Decimal(d['debito']) if d['debito'] else Decimal(0)
        despesas.append(
            {
                'natureza_despesa_id': d['nt_id'],
                'natureza_despesa_nome': d['nt_nome'],
                'fonte_recurso_id': d['fr_id'],
                'fonte_recurso_nome': d['fr_nome'],
                'unidade_gestora_codigo': d['ug_codigo'],
                'unidade_gestora_id': d['ug_id'],
                'unidade_gestora_nome': d['ug_nome'],
                'previsto': valor_previsto,
                'descentralizado': (credito - debito),
                'gasto': valor_gasto,
                'saldo': ((credito - debito) - valor_gasto),
            }
        )

    return locals()


@rtr('orcamento/templates/execucao_orcamentaria_nt.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def execucao_orcamentaria_nt(request, id_ug, cod_nt):
    title = 'Ex. orçamentária por Despesa'
    ug = UnidadeGestora.objects.get(id=id_ug)
    nt = NaturezaDespesa.objects.get(codigo=cod_nt)

    str_eventos_creditos = ','.join(str(i) for i in Evento.list_creditos())
    str_eventos_debitos = ','.join(str(i) for i in Evento.list_debitos())

    sql = f"""select s.nt_id as nt_id, s.nt_nome as nt_nome,
                   s.fr_id as fr_id, s.fr_nome as fr_nome,
                   s.ug_codigo as ug_codigo,
                   s.ug_id as ug_id, s.ug_nome as ug_nome,
                   sum(s.credito) as credito,
                   sum(s.debito) as debito
            from
            (select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
            from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notacredito n,
                    financeiro_notacreditoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_credito_id and
                    u.id = n.favorecido_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u.id = {id_ug} and
                    d.codigo = '{cod_nt}'
                    group by d.codigo, d.nome, f.codigo,
                         f.nome, e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
            group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo
            union
            select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
            from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notadotacao n,
                    financeiro_notadotacaoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_dotacao_id and
                    u.id = n.emitente_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u.id = {id_ug} and
                    d.codigo = '{cod_nt}'
                    group by d.codigo, d.nome, f.codigo, f.nome,
                         e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
            group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo) s
            group by s.nt_id, s.nt_nome, s.fr_id, s.fr_nome, s.ug_id, s.ug_nome, s.ug_codigo
            order by s.ug_codigo desc, s.nt_id, s.nt_nome, s.fr_id, s.fr_nome;
            """
    consulta = db.get_dict(sql)

    despesas = []
    for d in consulta:
        # evita quebra caso o módulo de planejamento não esteja instalado
        try:
            ano_atual = apps.get_model('comum', 'ano').objects.get(ano=datetime.now().year)
            sqlValorPrevisto = f"""SELECT SUM(pat.quantidade * pat.valor_unitario) as valor
                                    FROM planejamento_atividade pat, planejamento_acao pac, planejamento_metaunidade pmu,
                                        planejamento_unidadeadministrativa pua, setor str,
                                        planejamento_configuracao pco
                                    WHERE pac.id = pat.acao_id
                                        AND pmu.id = pac.meta_unidade_id
                                        AND pua.id = pmu.unidade_id
                                        AND str.id = pua.setor_equivalente_id
                                        AND pac.status = 'Deferida'
                                        AND pat.valor_unitario != 0.00
                                        AND str.id = {ug.setor.id}
                                        AND pco.id = pua.configuracao_id
                                        AND pco.ano_base_id = {ano_atual.id}
                                    GROUP BY str.sigla
                                    ORDER BY str.sigla;"""
            cns = db.get_dict(sqlValorPrevisto)
            # valor_previsto = cns[0]['valor'] if cns else 0
            valor_previsto = 0
        except Exception:
            valor_previsto = 0

        try:
            # identifica se trata-se de uma ug executora ou de controle (conhecida como ugr)
            # calcula o valor dos empenhos e fl's
            if str(id_ug) == str(d['ug_id']):
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr=None,
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )
            else:
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr__id=d['ug_id'],
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )

            valor_gasto = 0
            for empenho in empenhos:
                valor_gasto += empenho.get_valor_empenhado()
        except Exception:
            valor_gasto = 0

        credito = Decimal(d['credito']) if d['credito'] else Decimal(0)
        debito = Decimal(d['debito']) if d['debito'] else Decimal(0)
        despesas.append(
            {
                'natureza_despesa_id': d['nt_id'],
                'natureza_despesa_nome': d['nt_nome'],
                'fonte_recurso_id': d['fr_id'],
                'fonte_recurso_nome': d['fr_nome'],
                'unidade_gestora_codigo': d['ug_codigo'],
                'unidade_gestora_id': d['ug_id'],
                'unidade_gestora_nome': d['ug_nome'],
                'previsto': valor_previsto,
                'descentralizado': (credito - debito),
                'gasto': valor_gasto,
                'saldo': ((credito - debito) - valor_gasto),
            }
        )

    return locals()


@rtr('orcamento/templates/execucao_orcamentaria_ugr_nt.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def execucao_orcamentaria_ugr_nt(request, id_ug, id_ugr, cod_nt):
    title = 'Ex. orçamentária por Despesa'
    ug = UnidadeGestora.objects.get(id=id_ug)
    ugr = UnidadeGestora.objects.get(id=id_ugr)
    nt = NaturezaDespesa.objects.get(codigo=cod_nt)

    str_eventos_creditos = ','.join(str(i) for i in Evento.list_creditos())
    str_eventos_debitos = ','.join(str(i) for i in Evento.list_debitos())

    sql = f"""select * from
            (select s.nt_id as nt_id, s.nt_nome as nt_nome,
                   s.fr_id as fr_id, s.fr_nome as fr_nome,
                   s.ug_codigo as ug_codigo,
                   s.ug_id as ug_id, s.ug_nome as ug_nome,
                   sum(s.credito) as credito,
                   sum(s.debito) as debito
                from
                (select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
                from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notacredito n,
                    financeiro_notacreditoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_credito_id and
                    u.id = n.favorecido_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u.id = {id_ug} and
                    d.codigo = '{cod_nt}'
                    group by d.codigo, d.nome, f.codigo,
                     f.nome, e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
                group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo
                union
                select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
                from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    coalesce(u2.id, u.id) as ug_id,
                    coalesce(u2.nome, u.nome) as ug_nome,
                    coalesce(u2.codigo, u.codigo) as ug_codigo,
                    case when e.tipo in ({str_eventos_creditos})
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo in ({str_eventos_debitos})
                    then sum(i.valor)
                    end as debito
                from financeiro_notadotacao n,
                    financeiro_notadotacaoitem i left join
                    financeiro_unidadegestora u2 on
                    u2.id = i.ugr_id,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_dotacao_id and
                    u.id = n.emitente_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    u.id = {id_ug} and
                    d.codigo = '{cod_nt}'
                    group by d.codigo, d.nome, f.codigo, f.nome,
                     e.tipo, u.id, u.nome, u.codigo, u2.id, u2.nome, u2.codigo) t
                group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo) s
                group by s.nt_id, s.nt_nome, s.fr_id, s.fr_nome, s.ug_id, s.ug_nome, s.ug_codigo
                order by s.ug_codigo desc, s.nt_id, s.nt_nome, s.fr_id, s.fr_nome) r
                where r.ug_id = {id_ugr};"""
    consulta = db.get_dict(sql)

    despesas = []
    for d in consulta:
        # evita quebra caso o módulo de planejamento não esteja instalado
        try:
            ano_atual = apps.get_model('comum', 'ano').objects.get(ano=datetime.now().year)
            sqlValorPrevisto = f"""SELECT SUM(pat.quantidade * pat.valor_unitario) as valor
                                    FROM planejamento_atividade pat, planejamento_acao pac, planejamento_metaunidade pmu,
                                        planejamento_unidadeadministrativa pua, setor str,
                                        planejamento_configuracao pco
                                    WHERE pac.id = pat.acao_id
                                        AND pmu.id = pac.meta_unidade_id
                                        AND pua.id = pmu.unidade_id
                                        AND str.id = pua.setor_equivalente_id
                                        AND pac.status = 'Deferida'
                                        AND pat.valor_unitario != 0.00
                                        AND str.id = {ug.setor.id}
                                        AND pco.id = pua.configuracao_id
                                        AND pco.ano_base_id = {ano_atual.id}
                                    GROUP BY str.sigla
                                    ORDER BY str.sigla;"""
            cns = db.get_dict(sqlValorPrevisto)
            # valor_previsto = cns[0]['valor'] if cns else 0
            valor_previsto = 0
        except Exception:
            valor_previsto = 0

        try:
            # identifica se trata-se de uma ug executora ou de controle (conhecida como ugr)
            # calcula o valor dos empenhos e fl's
            if str(id_ug) == str(d['ug_id']):
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr=None,
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )
            else:
                empenhos = NotaEmpenho.objects.filter(
                    emitente_ug__id=id_ug,
                    ugr__id=d['ug_id'],
                    fonte_recurso__codigo=d['fr_id'],
                    natureza_despesa__codigo=d['nt_id'],
                    referencia_empenho=None,
                    referencia_empenho_original='',
                )

            valor_gasto = 0
            for empenho in empenhos:
                valor_gasto += empenho.get_valor_empenhado()
        except Exception:
            valor_gasto = 0

        credito = Decimal(d['credito']) if d['credito'] else Decimal(0)
        debito = Decimal(d['debito']) if d['debito'] else Decimal(0)
        despesas.append(
            {
                'natureza_despesa_id': d['nt_id'],
                'natureza_despesa_nome': d['nt_nome'],
                'fonte_recurso_id': d['fr_id'],
                'fonte_recurso_nome': d['fr_nome'],
                'unidade_gestora_codigo': d['ug_codigo'],
                'unidade_gestora_id': d['ug_id'],
                'unidade_gestora_nome': d['ug_nome'],
                'previsto': valor_previsto,
                'descentralizado': (credito - debito),
                'gasto': valor_gasto,
                'saldo': ((credito - debito) - valor_gasto),
            }
        )

    return locals()


@rtr('orcamento/templates/nota_credito_consulta.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def nota_credito_consulta(request):
    title = 'Consulta Nota de Crédito'
    form = NotaCreditoConsultaForm(request.POST or None)
    if form.is_valid():
        notas = NotaCredito.objects.all()
        if request.POST['numero']:
            notas = notas.filter(numero__icontains=request.POST['numero'])

        if request.POST['natureza_desp']:
            natureza_despesa = NaturezaDespesa.objects.get(id=request.POST['natureza_desp'])
            notas = notas.filter(notacreditoitem__natureza_despesa=natureza_despesa)

        if request.POST['emitente']:
            emitente = UnidadeGestora.objects.get(id=request.POST['emitente'])
            notas = notas.filter(emitente_ug=emitente)

        if request.POST['favorecido']:
            favorecido = UnidadeGestora.objects.get(id=request.POST['favorecido'])
            notas = notas.filter(favorecido_ug=favorecido)

        if request.POST['data_inicial'] and request.POST['data_final']:
            notas = notas.filter(
                datahora_emissao__gte=datetime.strptime(request.POST['data_inicial'], '%d/%m/%Y'),
                datahora_emissao__lte=datetime.strptime(request.POST['data_final'], '%d/%m/%Y'),
            )

    return locals()


@rtr('orcamento/templates/notas_credito.html')
@group_required('Administrador de Orçamento')
def notas_credito(request, id_ug):
    config_ug = Configuracao._get_conf_por_chave('orcamento', 'unidade_responsavel')
    uge = UnidadeGestora.objects.get(codigo=config_ug.valor)
    ugf = UnidadeGestora.objects.get(id=id_ug)
    notas = NotaCredito.objects.filter(emitente_ug=uge, favorecido_ug__id=ugf.id).order_by('-numero', '-datahora_emissao')

    return locals()


@rtr('orcamento/templates/notas_credito.html')
@group_required('Administrador de Orçamento')
def notas_credito_emitente_favorecido(request, id_uge, id_ugf):
    uge = UnidadeGestora.objects.get(id=id_uge)
    ugf = UnidadeGestora.objects.get(id=id_ugf)
    notas = NotaCredito.objects.filter(emitente_ug=uge, favorecido_ug=ugf).order_by('-numero', '-datahora_emissao')

    return locals()


@rtr('orcamento/templates/notas_credito_nt.html')
@group_required('Administrador de Orçamento')
def notas_credito_nt(request, id_ug):
    config_ug = Configuracao._get_conf_por_chave('orcamento', 'unidade_responsavel')
    ugr = UnidadeGestora.objects.get(codigo=config_ug.valor)
    ug = UnidadeGestora.objects.get(id=id_ug)

    sql = f"""select t.nt_id as nt_id, t.nt_nome as nt_nome,
                t.fr_id as fr_id, t.fr_nome as fr_nome,
                t.ug_id as ug_id, t.ug_nome as ug_nome,
                t.ug_codigo as ug_codigo,
                sum(t.credito) as credito,
                sum(t.debito) as debito
            from (select d.codigo as nt_id, d.nome as nt_nome,
                    f.codigo as fr_id, f.nome as fr_nome,
                    u.id as ug_id,
                    u.nome as ug_nome,
                    u.codigo as ug_codigo,
                    case when e.tipo = '1'
                    then sum(i.valor)
                    end as credito,
                    case when e.tipo = '2'
                    then sum(i.valor)
                    end as debito
                from financeiro_notacredito n,
                    financeiro_notacreditoitem i,
                    financeiro_evento e,
                    financeiro_unidadegestora u,
                    financeiro_unidadegestora ue,
                    financeiro_naturezadespesa d,
                    financeiro_fonterecurso f
                where n.id = i.nota_credito_id and
                    u.id = n.favorecido_ug_id and
                    ue.id = n.emitente_ug_id and
                    e.id = i.evento_id and
                    d.id = i.natureza_despesa_id and
                    f.id = i.fonte_recurso_id and
                    ue.id = {ugr.id} and
                    u.id = {ug.id}
                    group by d.codigo, d.nome, f.codigo,
                         f.nome, e.tipo, u.id, u.nome, u.codigo) t
            group by t.nt_id, t.nt_nome, t.fr_id, t.fr_nome, t.ug_id, t.ug_nome, t.ug_codigo"""

    despesas = []
    for d in db.get_dict(sql):
        credito = Decimal(d['credito']) if d['credito'] else Decimal(0)
        debito = Decimal(d['debito']) if d['debito'] else Decimal(0)
        despesas.append(
            {
                'natureza_despesa_id': d['nt_id'],
                'natureza_despesa_nome': d['nt_nome'],
                'fonte_recurso_id': d['fr_id'],
                'fonte_recurso_nome': d['fr_nome'],
                'unidade_gestora_codigo': d['ug_codigo'],
                'unidade_gestora_id': d['ug_id'],
                'unidade_gestora_nome': d['ug_nome'],
                'descentralizado': (credito - debito),
            }
        )

    return locals()


@rtr('orcamento/templates/itens_nota_credito.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def itens_nota_credito(request, id_nc):
    nota = NotaCredito.objects.get(id=id_nc)
    return locals()


@rtr('orcamento/templates/nota_dotacao_consulta.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def nota_dotacao_consulta(request):
    title = 'Consulta Nota de Dotação'
    form = NotaDotacaoConsultaForm(request.POST or None)
    if form.is_valid():
        notas = NotaDotacao.objects.all()
        if request.POST['numero']:
            notas = notas.filter(numero__icontains=request.POST['numero'])

        if request.POST['natureza_desp']:
            natureza_despesa = NaturezaDespesa.objects.get(id=request.POST['natureza_desp'])
            notas = notas.filter(notadotacaoitem__natureza_despesa=natureza_despesa)

        if request.POST['emitente']:
            emitente = UnidadeGestora.objects.get(id=request.POST['emitente'])
            notas = notas.filter(emitente_ug=emitente)

        if request.POST['data_inicial'] and request.POST['data_final']:
            notas = notas.filter(
                datahora_emissao__gte=datetime.strptime(request.POST['data_inicial'], '%d/%m/%Y'),
                datahora_emissao__lte=datetime.strptime(request.POST['data_final'], '%d/%m/%Y'),
            )

    return locals()


@rtr('orcamento/templates/notas_credito_dotacao_ugr.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def notas_credito_dotacao_ugr(request, id_ug, id_ugr):
    ug = UnidadeGestora.objects.get(id=id_ug)
    ugr = UnidadeGestora.objects.get(id=id_ugr)

    notas_credito = NotaCredito.objects.filter(favorecido_ug__id=id_ugr).order_by('-numero', '-datahora_emissao')

    # Opções de consulta
    # Q(emitente_ug__id=id_ugr, notadotacaoitem__ugr__id=None)  => pega os detalhamentos para a própria unidade gestora
    # Q(emitente_ug__id=id_ugr, notadotacaoitem__ugr__id=id_ug) => pega as devoluções
    # Q(emitente_ug__id=id_ug, notadotacaoitem__ugr__id=id_ugr) => pega os detalhamentos comuns e os estornos
    notas_dotacao = (
        NotaDotacao.objects.filter(
            Q(emitente_ug__id=id_ugr, notadotacaoitem__ugr__id=None)
            | Q(emitente_ug__id=id_ugr, notadotacaoitem__ugr__id=id_ug)
            | Q(emitente_ug__id=id_ug, notadotacaoitem__ugr__id=id_ugr)
        )
        .distinct()
        .order_by('-numero', '-datahora_emissao')
    )

    form = NotasFiltroForm()
    return locals()


@rtr('orcamento/templates/itens_nota_dotacao.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def itens_nota_dotacao(request, id_nd):
    nota = NotaDotacao.objects.get(id=id_nd)
    return locals()


@rtr('orcamento/templates/nota_empenho_consulta.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def nota_empenho_consulta(request):
    title = 'Consulta Nota de Empenho'
    form = NotaEmpenhoConsultaForm(request.POST or None)
    if form.is_valid():
        notas = NotaEmpenho.objects.all()

        numero = request.POST.get('numero', None)
        natureza_desp = request.POST.get('natureza_desp', None)
        fornecedor = request.POST.get('fornecedor', None)
        emitente = request.POST.get('emitente', None)
        descricao = request.POST.get('descricao', None)
        if numero:
            notas = notas.filter(numero__icontains=request.POST['numero'])

        if natureza_desp:
            natureza_despesa = NaturezaDespesa.objects.get(id=request.POST['natureza_desp'])
            notas = notas.filter(natureza_despesa=natureza_despesa)

        if fornecedor:
            fornecedor = Pessoa.objects.get(id=request.POST['fornecedor'])
            notas = notas.filter(favorecido=fornecedor)

        if request.POST['data_inicial'] and request.POST['data_final']:
            notas = notas.filter(
                data_emissao__gte=datetime.strptime(request.POST['data_inicial'], '%d/%m/%Y'),
                data_emissao__lte=datetime.strptime(request.POST['data_final'], '%d/%m/%Y'),
            )

        if emitente:
            emitente = UnidadeGestora.objects.get(id=request.POST['emitente'])
            notas = notas.filter(emitente_ug=emitente)

        # verifica se existe alguma nota com itens com a descrição
        if descricao:
            ids = []
            for nota in notas:
                itens = NEItem.objects.filter(lista_itens__nota_empenho=nota, descricao__unaccent__icontains=request.POST['descricao'])
                if not len(itens):
                    ids.append(nota.id)
            notas = notas.exclude(id__in=ids)

        notas = notas.order_by('-data_emissao')
    return locals()


@rtr('orcamento/templates/itens_nota_empenho.html')
@group_required('Administrador de Orçamento,Operador de Orçamento')
def itens_nota_empenho(request, id_ne):
    nota = NotaEmpenho.objects.get(id=id_ne)
    # pode se que um empenho não tenha lista de itens associada, já que não houve registro nos arquivos
    # esse cenário foi identificado durante a importação
    listas = NEListaItens.objects.filter(nota_empenho=nota)
    if listas:
        lista = listas[0]

    return locals()


@rtr('orcamento/templates/eventos_desatualizados.html')
@group_required('Administrador de Orçamento')
def eventos_desatualizados(request):
    title = 'Eventos Desatualizados'
    eventos = get_eventos_desatualizados_notascreditodotacao()
    return locals()


@rtr('orcamento/templates/eventos_utilizados.html')
@group_required('Administrador de Orçamento')
def eventos_utilizados(request):
    title = 'Eventos Utilizados'
    eventos = get_eventos_utilizados_notascreditodotacao()
    return locals()


@rtr('orcamento/templates/historico_importacao.html')
@group_required('Administrador de Orçamento, Operador de Orçamento')
def historico_importacao(request):
    eventos = get_eventos_utilizados_notascreditodotacao()

    return locals()
