"""Cadastros do AE (modo 2).

Cada teste parametrizado cria os registros que o domínio exige — tipo de programa, programa,
edital, oferta e período — antes de qualquer inscrição existir.
"""

from datetime import date
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

TIPOS = (
    ('Alimentação Estudantil', 'ALM'),
    ('Apoio à Formação Estudantil', 'TRB'),
    ('Auxílio Transporte', 'PAS'),
    ('Curso de Idiomas', 'IDM'),
)


def test_cadastra_tipos_de_programa(logado_ae):
    from ae.models import TipoPrograma

    criados = []
    for titulo, _sigla in TIPOS:
        titulo_e2e = f'{titulo} E2E {uuid4().hex[:8]}'
        tela = Tela(logado_ae('coordenador')).ir('/admin/ae/tipoprograma/add/')
        tela.ver_titulo('Adicionar Tipo de Programa')
        tela.preencher_formulario(
            [
                ('Título', 'texto', titulo_e2e),
                ('Descrição', 'textarea', 'descrição do tipo do programa'),
                ('Ativo', 'checkbox', 'marcar'),
            ]
        ).clicar_botao('Salvar')
        tela.sucesso('Cadastro realizado com sucesso.')
        criados.append(titulo_e2e)

    assert TipoPrograma.objects.filter(titulo__in=criados, ativo=True).count() == len(criados)


def test_cadastra_programas_por_tipo(logado_ae, ae_fluxos):
    from ae.models import DemandaAluno, Programa
    from rh.models import UnidadeOrganizacional

    campus = UnidadeOrganizacional.objects.uo().get(sigla='CZN')
    descricoes = []
    for sigla, (titulo, _programa) in zip(
        [Programa.TIPO_ALIMENTACAO, Programa.TIPO_TRABALHO, Programa.TIPO_TRANSPORTE, Programa.TIPO_IDIOMA], TIPOS, strict=True
    ):
        descricao = f'descrição do programa E2E {uuid4().hex[:8]}'
        dados = [
            ('Tipo de Programa', 'autocomplete', titulo),
            ('Descrição', 'textarea', descricao),
            ('Campus', 'autocomplete', 'CZN'),
            ('Impedir que aluno solicite benefício', 'checkbox', 'marcar'),
            ('Público-Alvo', 'filteredselectmultiple', str(campus.pk)),
        ]
        if sigla == Programa.TIPO_ALIMENTACAO:
            dados.append(('Atendimentos incluídos', 'filteredselectmultiple', ','.join(map(str, [1, 2]))))
            dados.append(
                ('Quantidade de faltas para suspender participação', 'lista', '3'),
            )

        tela = Tela(logado_ae('coordenador')).ir('/admin/ae/programa/add/')
        tela.ver_titulo('Adicionar Programa').preencher_formulario(dados).clicar_botao('Salvar')
        tela.sucesso('Cadastro realizado com sucesso.')
        descricoes.append(descricao)

    assert Programa.objects.filter(descricao__in=descricoes, instituicao=campus).count() == len(descricoes)
    assert Programa.objects.get(descricao=descricoes[0]).demandas.filter(pk__in=[1, 2]).count() == DemandaAluno.objects.filter(pk__in=[1, 2]).count()


def test_cadastra_editais_dos_programas(logado_ae):
    from ae.models import Edital, TipoPrograma

    tipos = []
    for titulo, sigla in TIPOS:
        tipo = TipoPrograma.objects.create(
            titulo=f'{titulo} Edital E2E {uuid4().hex[:8]}', descricao='tipo de edital E2E', sigla=f'{sigla}E2E', ativo=True
        )
        tipos.append(tipo)

    descricoes = []
    for tipo in tipos:
        descricao = f'Edital E2E do Programa {tipo.titulo}'
        tela = Tela(logado_ae('coordenador')).ir('/admin/ae/edital/add/')
        tela.ver_titulo('Adicionar Edital da Assistência Estudantil').preencher_formulario(
            [
                ('Descrição', 'textarea', descricao),
                ('Tipos de Programa', 'autocomplete multiplo', tipo.titulo),
                ('Link para o Edital', 'texto', 'http://portal.ifrn.edu.br/link_edital.pdf'),
            ]
        ).clicar_botao('Salvar')
        tela.sucesso('Cadastro realizado com sucesso.')
        descricoes.append(descricao)

    assert Edital.objects.filter(descricao__in=descricoes, ativo=True).count() == len(descricoes)


def test_cadastra_oferta_de_alimentacao(logado_ae):
    from ae.models import OfertaAlimentacao

    inicio = date(2024, 6, 10)
    tela = Tela(logado_ae('assistente_social')).ir('/admin/ae/ofertaalimentacao/add/')
    tela.ver_titulo('Adicionar Oferta de Refeições').preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Segunda-feira do Início da Oferta', 'data', inicio.strftime('%d/%m/%Y')),
            ('Sexta-feira do Término da Oferta', 'data', '14/06/2024'),
            ('Almoço/Segunda', 'texto', '100'),
            ('Almoço/Terça', 'texto', '100'),
            ('Almoço/Quarta', 'texto', '100'),
            ('Almoço/Quinta', 'texto', '100'),
            ('Almoço/Sexta', 'texto', '100'),
        ]
    ).clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert OfertaAlimentacao.objects.filter(dia_inicio=inicio, almoco_seg=100).exists()


def test_cadastra_turmas_de_idioma(logado_ae):
    from ae.models import Idioma, OfertaTurma

    valores = [
        ('Inglês', '1', 'Segunda', 'Quarta', '10:00', '11:00', 5),
        ('Espanhol', '2', 'Terça', 'Quinta', '15:00', '16:00', 4),
    ]
    turmas = []
    for idioma, semestre, dia1, dia2, inicio, termino, vagas in valores:
        turma = f'E2E {uuid4().hex[:8]}'
        tela = Tela(logado_ae('assistente_social')).ir('/admin/ae/ofertaturma/add/')
        tela.ver_titulo('Adicionar Oferta de Turmas de Idioma').preencher_formulario(
            [
                ('Campus', 'lista', 'CZN'),
                ('Turma', 'texto', turma),
                ('Idioma', 'autocomplete', idioma),
                ('Ano', 'texto', '2024'),
                ('Semestre', 'lista', semestre),
                ('1º Dia', 'lista', dia1),
                ('2º Dia', 'lista', dia2),
                ('Horário de Início', 'texto', inicio),
                ('Horário de Término', 'texto', termino),
                ('Professor(a)', 'texto', f'Professor E2E {turma}'),
                ('Número de Vagas', 'texto', str(vagas)),
            ]
        ).clicar_botao('Salvar')
        tela.sucesso('Cadastro realizado com sucesso.')
        turmas.append(turma)

    assert OfertaTurma.objects.filter(turma__in=turmas, idioma__in=Idioma.objects.filter(descricao__in=['Inglês', 'Espanhol'])).count() == 2


def test_cadastra_periodo_de_inscricao(logado_ae, ae_fluxos):
    from ae.models import Edital, PeriodoInscricao, TipoPrograma

    tipo = TipoPrograma.objects.get(titulo='Alimentação Estudantil')
    edital = Edital.objects.create(
        descricao=f'Edital E2E período {uuid4().hex[:8]}', link_edital='http://portal.ifrn.edu.br/link_edital.pdf', ativo=True
    )
    edital.tipo_programa.set([tipo])
    programa = ae_fluxos['programas']['ALM']
    tela = Tela(logado_ae('coordenador')).ir('/admin/ae/periodoinscricao/add/')
    tela.ver_titulo('Adicionar Período de Inscrição').preencher_formulario(
        [
            ('Edital', 'autocomplete', edital.descricao),
            ('Campus', 'autocomplete', 'CZN'),
            ('Programas Vinculados', 'autocomplete multiplo', programa.titulo),
            ('Data de Início das Inscrições', 'data', '01/07/2024'),
            ('Data de Término das Inscrições', 'data', '31/07/2024'),
        ]
    ).clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert PeriodoInscricao.objects.filter(edital=edital, programa=programa).exists()
