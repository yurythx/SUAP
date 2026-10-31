"""Fábricas ORM do seed das tarefas navegadas (não são passos documentados).

Os testes de doc documentam apenas as telas que navegam; o que antecede a tela (o edital
aberto, o projeto enviado, a comissão formada) é preparado por ORM aqui, com datas relativas
a hoje — a mesma decisão de relógio do ``eventos`` (sem congelar a data do sistema).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from comum.models import Ano
from djtools.e2e_fixtures import campus
from rh.models import Servidor, Setor, UnidadeOrganizacional

if TYPE_CHECKING:
    from projetos_ensino.models import (
        CaracterizacaoBeneficiario,
        ComissaoEdital,
        CriterioAvaliacao,
        Desembolso,
        Edital,
        Etapa,
        FotoProjeto,
        ItemMemoriaCalculo,
        Meta,
        OfertaProjeto,
        Projeto,
        Recurso,
        RegistroConclusaoProjeto,
        RegistroExecucaoEtapa,
        RegistroGasto,
    )


def _salvar(instancia):
    """Salva pela instância: vários models do módulo redefinem ``save()`` sem aceitar
    ``force_insert``, que ``QuerySet.create`` passa sempre (ex.: ``Edital.save``,
    ``Desembolso.save``)."""
    instancia.save()
    return instancia


def uo_czn() -> UnidadeOrganizacional:
    """A unidade organizacional do campus CZN (a UO do setor SUAP 'CZN')."""
    return UnidadeOrganizacional.objects.suap().get(setor=setor_czn())


def setor_czn() -> Setor:
    """O setor SUAP do campus CZN (criado pelo ``doc_seed``)."""
    return campus('CZN', 'Campus Zona Norte')


def criar_edital(
    titulo: str,
    *,
    inicio_inscricoes: int = -30,
    fim_inscricoes: int = -20,
    inicio_pre_selecao: int = -10,
    inicio_selecao: int = 10,
    fim_selecao: int = 20,
    divulgacao_selecao: int = 30,
    **extra,
) -> Edital:
    """Edital com todas as datas relativas a ``date.today()`` (dias corridos).

    Defaults: inscrições encerradas, pré-seleção em curso (essas são as fases de que os
    testes 3-10 precisam); os testes de fase de inscrição passam ``inicio_inscricoes=-1`` e
    ``fim_inscricoes=+5`` explícitos.
    """
    from projetos_ensino.models import Edital

    hoje = date.today()
    edital = Edital(
        titulo=titulo,
        descricao='Edital criado pelo seed de doc',
        tipo_edital=Edital.ENSINO,
        forma_selecao=Edital.CAMPUS,
        campus_especifico=True,
        qtd_projetos_selecionados=5,
        inicio_inscricoes=hoje + timedelta(days=inicio_inscricoes),
        fim_inscricoes=hoje + timedelta(days=fim_inscricoes),
        inicio_pre_selecao=hoje + timedelta(days=inicio_pre_selecao),
        inicio_selecao=hoje + timedelta(days=inicio_selecao),
        fim_selecao=hoje + timedelta(days=fim_selecao),
        divulgacao_selecao=hoje + timedelta(days=divulgacao_selecao),
        exige_aluno=True,
        exige_servidor=True,
        valor_financiado_por_projeto='10000.00',
        cadastrado_em=datetime.now(),
        **extra,
    )
    # `Edital.save` redefine `save()` e não aceita `force_insert` (o `.create` do manager o
    # passa sempre) — salva-se pela instância.
    edital.save()
    return edital


def criar_oferta(edital: Edital, qtd_aprovados: int = 10, qtd_selecionados: int = 3) -> OfertaProjeto:
    """Plano de oferta do edital para o campus CZN."""
    from projetos_ensino.models import OfertaProjeto

    return _salvar(OfertaProjeto(edital=edital, uo=uo_czn(), qtd_aprovados=qtd_aprovados, qtd_selecionados=qtd_selecionados))


def criar_recurso(edital: Edital, origem: str = 'CAMPUS', valor: str = '10000.00') -> Recurso:
    """Fonte de recurso do edital na rubrica de auxílio a estudantes."""
    from financeiro.models import NaturezaDespesa
    from projetos_ensino.models import Recurso

    natureza = NaturezaDespesa.objects.get(codigo='339018')
    return _salvar(Recurso(edital=edital, origem=origem, valor=valor, despesa=natureza))


def criar_criterio(edital: Edital, descricao: str = 'Adequação da proposta ao tema', pontuacao: str = '10.00') -> CriterioAvaliacao:
    from projetos_ensino.models import CriterioAvaliacao

    return _salvar(CriterioAvaliacao(edital=edital, descricao=descricao, pontuacao_maxima=pontuacao, ordem_desempate=1))


def criar_comissao(edital: Edital, membros: list[str]) -> ComissaoEdital:
    """Comissão de avaliação do edital com os vínculos dos avaliadores indicados."""
    from comum.models import Vinculo
    from projetos_ensino.models import ComissaoEdital

    comissao = _salvar(ComissaoEdital(edital=edital))
    for matricula in membros:
        comissao.vinculos_membros.add(Vinculo.objects.get(user__username=matricula))
    return comissao


def criar_projeto(titulo: str, edital: Edital, *, enviado: bool = True, **extra) -> Projeto:
    """Projeto da coordenadora do doc (158003) com equipe, meta e atividade mínimas.

    ``enviado=True`` grava ``data_conclusao_planejamento`` — o estado que as telas de
    pré-seleção/avaliação/execução esperam. ``extra`` permite marcar ``pre_aprovado``,
    ``aprovado``, ``vinculo_monitor`` etc. para os testes seguintes.
    """
    from projetos_ensino.models import EixoTematico, Participacao, Projeto, TipoVinculo

    hoje = date.today()
    setor = setor_czn()
    coordenador = Servidor.objects.get(matricula='158003')
    base = {
        'edital': edital,
        'uo': uo_czn(),
        'setor': setor,
        'titulo': titulo,
        'eixo_tematico': EixoTematico.objects.filter(ativo=True).first(),
        'inicio_execucao': hoje + timedelta(days=15),
        'fim_execucao': hoje + timedelta(days=150),
        'ch_total': 400,
        'resumo': '<p>Resumo do projeto</p>',
        'introducao': '<p>Introdução do projeto</p>',
        'justificativa': '<p>Justificativa do projeto</p>',
        'objetivo_geral': '<p>Objetivo geral do projeto</p>',
        'metodologia': '<p>Metodologia do projeto</p>',
        'acompanhamento_e_avaliacao': '<p>Acompanhamento do projeto</p>',
        'resultados_esperados': '<p>Resultados esperados</p>',
        'referencias': '<p>Referências</p>',
        'vinculo_coordenador': coordenador.get_vinculo(),
    }
    base.update(extra)
    projeto = _salvar(Projeto(**base))
    _salvar(
        Participacao(
            projeto=projeto,
            vinculo_pessoa=coordenador.get_vinculo(),
            responsavel=True,
            vinculo=TipoVinculo.VOLUNTARIO,
            carga_horaria=6,
            ativo=True,
        )
    )
    if enviado:
        projeto.data_conclusao_planejamento = datetime.now()
        projeto.save()
    return projeto


def criar_equipe(projeto: Projeto, *, membro: bool = True, aluno: bool = True) -> None:
    """Participações ativas do projeto: servidor membro (158004) e/ou aluno (158007)."""
    from comum.models import Vinculo
    from projetos_ensino.models import Participacao, TipoVinculo

    if membro:
        _salvar(
            Participacao(
                projeto=projeto,
                vinculo_pessoa=Vinculo.objects.get(user__username='158004'),
                responsavel=False,
                vinculo=TipoVinculo.VOLUNTARIO,
                carga_horaria=6,
                ativo=True,
            )
        )
    if aluno:
        _salvar(
            Participacao(
                projeto=projeto,
                vinculo_pessoa=Vinculo.objects.get(user__username='2020010115807'),
                responsavel=False,
                vinculo=TipoVinculo.VOLUNTARIO,
                carga_horaria=6,
                ativo=True,
            )
        )


def criar_meta_atividade(projeto: Projeto) -> tuple[Meta, Etapa]:
    """Uma meta com uma atividade, responsável = o servidor membro (158004)."""
    from datetime import timedelta

    from projetos_ensino.models import Etapa, Meta

    hoje = date.today()
    meta = _salvar(Meta(projeto=projeto, ordem=1, descricao='Meta 1 do projeto'))
    participacao = projeto.participacao_set.filter(vinculo_pessoa__user__username='158004').first()
    etapa = _salvar(
        Etapa(
            meta=meta,
            ordem=1,
            descricao='Atividade 1 da meta',
            unidade_medida='Unidade',
            qtd=4,
            indicadores_qualitativos='Atendido parcialmente',
            responsavel=participacao,
            inicio_execucao=hoje + timedelta(days=20),
            fim_execucao=hoje + timedelta(days=30),
        )
    )
    return meta, etapa


def criar_memoria_e_desembolso(projeto: Projeto) -> tuple[ItemMemoriaCalculo, Desembolso]:
    """Item de memória de cálculo + desembolso de 100% do recurso do edital."""
    from financeiro.models import NaturezaDespesa
    from projetos_ensino.models import Desembolso, ItemMemoriaCalculo, Recurso

    recurso = Recurso.objects.filter(edital=projeto.edital).first()
    item = _salvar(
        ItemMemoriaCalculo(
            projeto=projeto,
            despesa=recurso.despesa,
            descricao='Pagamento de bolsas',
            unidade_medida='Unidade',
            qtd=1,
            valor_unitario='10000.00',
            origem=recurso.origem,
        )
    )
    ano = Ano.objects.get_or_create(ano=str(date.today().year))[0]
    desembolso = _salvar(Desembolso(projeto=projeto, ano=ano, mes=1, despesa=recurso.despesa, valor='10000.00', item=item))
    return item, desembolso


def criar_caracterizacao(projeto: Projeto, *, atendida: bool = False) -> CaracterizacaoBeneficiario:
    """Caracterização de beneficiários (tipos do seed do behave: 'Movimentos Sociais')."""
    from projetos_ensino.models import CaracterizacaoBeneficiario, TipoBeneficiario

    tipo = TipoBeneficiario.objects.filter(ativo=True).first()
    return _salvar(
        CaracterizacaoBeneficiario(
            projeto=projeto,
            tipo_beneficiario=tipo,
            quantidade=12,
            quantidade_atendida=12 if atendida else None,
            descricao_beneficiario='Descrição dos beneficiários' if atendida else None,
        )
    )


def criar_registro_execucao(etapa: Etapa, *, aprovado: bool = False) -> RegistroExecucaoEtapa:
    """Registro de execução da atividade, opcionalmente já aprovado pelo monitor."""
    from projetos_ensino.models import RegistroExecucaoEtapa

    hoje = date.today()
    reg = _salvar(
        RegistroExecucaoEtapa(
            tipo_indicador_qualitativo='1',  # Atendido
            etapa=etapa,
            qtd=etapa.qtd,
            inicio_execucao=hoje - timedelta(days=30),
            fim_execucao=hoje - timedelta(days=20),
            info_ind_qualitativo='Execução verificada',
            data_cadastro_execucao=hoje - timedelta(days=21),
        )
    )
    if aprovado:
        reg.dt_avaliacao = hoje - timedelta(days=18)
        reg.avaliador = Servidor.objects.get(matricula='158002')
        reg.aprovado = True
        reg.save()
    return reg


def criar_registro_gasto(desembolso: Desembolso, *, aprovado: bool = False) -> RegistroGasto:
    """Registro de gasto do desembolso (100% do valor), opcionalmente aprovado."""
    from projetos_ensino.models import RegistroGasto

    hoje = date.today()
    ano = Ano.objects.get_or_create(ano=str(hoje.year))[0]
    reg = _salvar(
        RegistroGasto(
            item=desembolso.item,
            ano=ano,
            mes=1,
            descricao='Exercício financeiro',
            qtd=1,
            valor_unitario=desembolso.valor,
            observacao='Gasto executado',
            desembolso=desembolso,
            data_cadastro=hoje - timedelta(days=5),
        )
    )
    if aprovado:
        reg.dt_avaliacao = hoje - timedelta(days=2)
        reg.avaliador = Servidor.objects.get(matricula='158002')
        reg.aprovado = True
        reg.save()
    return reg


def criar_foto(projeto: Projeto) -> FotoProjeto:
    from projetos_ensino.models import FotoProjeto

    return _salvar(FotoProjeto(projeto=projeto, legenda='Registro fotográfico', imagem='projetos_ensino/fotos/foto.png'))


def criar_registro_conclusao(projeto: Projeto) -> RegistroConclusaoProjeto:
    from projetos_ensino.models import RegistroConclusaoProjeto

    return _salvar(
        RegistroConclusaoProjeto(
            projeto=projeto,
            resultados_alcancados='Resultados alcançados pelo projeto',
            disseminacao_resultados='Disseminação dos resultados',
        )
    )
