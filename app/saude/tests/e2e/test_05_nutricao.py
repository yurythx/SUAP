"""Fluxo do atendimento nutricional (modo 2): anamnese, diagnóstico e conduta.

O Nutricionista abre o atendimento pelo prontuário e percorre as abas que sustentam o
atendimento: motivo, anamnese (avaliação gastrointestinal, dados de alimentação, restrições,
marcadores e recordatório), diagnóstico nutricional e conduta (categoria de trabalho, conduta,
plano alimentar com orientações e receitas). As remoções são exercitadas pelos próprios botões
das telas — é o caminho em que o produto as oferece.

``RUF001`` desligado no arquivo: os rótulos dos marcadores são as perguntas gravadas no banco
(com travessão e pontuação próprias), não prosa do teste.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Atendimento, AtendimentoNutricao, Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ATENDIMENTO = '/saude/atendimento_nutricional/{}/'
ADICIONAR_MOTIVO = '/saude/adicionar_motivo_nutricao/{}/'
ADICIONAR_GASTRO = '/saude/adicionar_avaliacao_gastrointestinal/{}/'
ADICIONAR_ALIMENTACAO = '/saude/adicionar_dados_alimentacao/{}/'
ADICIONAR_RESTRICAO = '/saude/adicionar_restricao_alimentar/{}/'
ADICIONAR_MARCADORES = '/saude/adicionar_marcadores_consumo_alimentar/{}/'
ADICIONAR_CONSUMO = '/saude/adicionar_consumo_nutricao/{}/'
EDITAR_CONSUMO = '/saude/editar_consumo/{}/'
ADICIONAR_DIAGNOSTICO = '/saude/adicionar_diagnostico_nutricional/{}/'
ADICIONAR_CATEGORIA = '/saude/adicionar_categoria_trabalho/{}/'
ADICIONAR_CONDUTA = '/saude/adicionar_conduta_nutricao/{}/'
ADICIONAR_PLANO = '/saude/adicionar_plano_alimentar/{}/'
EDITAR_PLANO = '/saude/editar_plano_alimentar/{}/'


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def _ultimo_atendimento_nutricional() -> Atendimento:
    """O atendimento nutricional mais recente materializado pela tela."""
    from saude.models import Atendimento, TipoAtendimento

    atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=TipoAtendimento.NUTRICIONAL).order_by('-id').first()
    assert atendimento is not None, 'o atendimento nutricional não foi criado pela tela'
    return atendimento


def _nutricao_do_atendimento(atendimento: Atendimento) -> AtendimentoNutricao:
    """O registro de atendimento nutricional (o `ModelSaudeFicha` que as fichas alimentam)."""
    from saude.models import AtendimentoNutricao

    registro = AtendimentoNutricao.objects.filter(atendimento=atendimento).order_by('-id').first()
    assert registro is not None, 'a ficha do atendimento nutricional não foi criada'
    return registro


def test_fluxo_nutricional_completo(logado_saude: Callable[[str], Page]) -> None:
    """O Nutricionista preenche anamnese, diagnóstico, conduta e plano, e remove o que criou."""
    tela = Tela(logado_saude('nutricionista'))

    from saude.models import ConsumoNutricao, PlanoAlimentar, RespostaMarcadorNutricao, SituacaoAtendimento, TipoAtendimento

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    tela.ir(f'/saude/prontuario/{vinculo.pk}/').ver_titulo('Prontuário')
    tela.clicar_botao('Atendimento Nutricional')
    expect(tela.pagina).to_have_url(re.compile(r'/saude/atendimento_nutricional/\d+/$'))
    tela.esperar().sucesso('Atendimento Nutricional gerado com sucesso.').ver_titulo('Atendimento Nutricional')
    atendimento = _ultimo_atendimento_nutricional()
    assert atendimento.tipo == TipoAtendimento.NUTRICIONAL, 'a UI abriu um tipo de atendimento incorreto'
    assert atendimento.situacao == SituacaoAtendimento.ABERTO, 'a UI disse que abriu, mas o atendimento não ficou aberto'

    # Motivo do atendimento.
    tela.clicar_aba('Motivo do atendimento')
    tela.aba('Motivo do atendimento').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_MOTIVO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [('Motivo do Atendimento', 'FilteredSelectMultiple', 'Alimentação saudável'), ('Observações', 'TextArea', 'Motivo E2E')]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro = _nutricao_do_atendimento(atendimento)
    assert registro.motivo.filter(descricao='Alimentação saudável').exists(), 'a UI disse que salvou, mas o motivo não persistiu'

    # Anamnese: avaliação gastrointestinal, dados de alimentação, restrições e marcadores.
    tela.clicar_aba('Anamnese')
    tela.quadro('Avaliação gastrointestinal').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_GASTRO.format(atendimento.pk)}$'))
    tela.preencher_formulario([('Avaliação Gastrointestinal', 'FilteredSelectMultiple', 'Pirose')])
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.avaliacao_gastrointestinal.filter(descricao='Pirose').exists(), (
        'a UI disse que salvou, mas a avaliação gastrointestinal não persistiu'
    )

    tela.quadro('Dados gerais da Alimentação').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ALIMENTACAO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Apetite', 'TextArea', 'Bom apetite'),
            ('Aversões', 'TextArea', 'Sem aversões'),
            ('Preferências', 'TextArea', 'Frutas'),
            ('Consumo de Água/Líquidos', 'TextArea', '2 litros por dia'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.apetite == 'Bom apetite', 'a UI disse que salvou, mas os dados de alimentação não persistiram'

    tela.quadro('Restrições alimentares').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_RESTRICAO.format(atendimento.pk)}$'))
    tela.preencher_formulario([('Restrição Alimentar', 'FilteredSelectMultiple', 'Glúten')])
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.restricao_alimentar.filter(descricao='Glúten').exists(), 'a UI disse que salvou, mas a restrição alimentar não persistiu'

    tela.quadro('Marcadores de Práticas e de Consumo Alimentar').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_MARCADORES.format(atendimento.pk)}$'))
    # O formulário monta um campo por pergunta ativa e um por alimento da frequência — os
    # rótulos abaixo são as perguntas do seed global, não texto livre.
    tela.preencher_formulario(
        [
            ('Você tem costume de realizar suas refeições assistindo TV, mexendo no computador ou celular?', 'Lista', 'Não'),
            ('Quais refeições você faz ao longo do dia??', 'checkbox multiplo', 'Café da manhã'),
            (
                'Você costuma fazer alguma dessas refeições – almoço ou jantar – com sua mãe ou responsável ou acompanhado de amigos ou parentes?',
                'Lista',
                'Não',
            ),
            ('Nos últimos 30 dias, você vomitou ou tomou laxantes para perder peso ou evitar ganhar peso?', 'Lista', 'Não'),
            (
                'Nos últimos 30 dias, você tomou algum remédio, fórmula ou outro produto para perder ou manter peso ou ganhar massa muscular sem acompanhamento médico ou nutricional?',
                'Lista',
                'Não',
            ),
            ('Quanto ao seu corpo, você se considera?', 'Lista', 'Normal'),
            ('O que você está fazendo em relação ao seu peso?', 'Lista', 'Não estou fazendo nada'),
            ('Nova Pergunta', 'Lista', 'Sim'),
            (
                'Nos últimos sete dias, em quantos dias você consumiu os seguintes alimentos ou bebidas: Feijão',
                'Lista',
                '5 dias nos últimos 7 dias',
            ),
        ]
    )
    tela.clicar_botao('Enviar').sucesso('Marcadores alterados com sucesso.')
    assert RespostaMarcadorNutricao.objects.filter(atendimento=atendimento).exists(), (
        'a UI disse que salvou, mas as respostas dos marcadores não persistiram'
    )

    tela.quadro('Marcadores de Práticas e de Consumo Alimentar').clicar_botao('Remover')
    tela.sucesso('Marcadores removidos com sucesso.')
    assert not RespostaMarcadorNutricao.objects.filter(atendimento=atendimento).exists(), (
        'a UI disse que removeu, mas as respostas dos marcadores permanecem'
    )

    tela.quadro('Recordatório alimentar').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CONSUMO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Refeição', 'Texto', 'Almoço'),
            ('Horário de Consumo', 'Hora', '12:00'),
            ('Local de Consumo', 'Texto', 'Restaurante'),
            ('Alimentos Consumidos / Medidas Caseiras', 'TextArea', 'Arroz, feijão e salada'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    consumo = ConsumoNutricao.objects.get(atendimento=atendimento, refeicao='Almoço')

    tela.quadro('Recordatório alimentar').linha('Almoço').clicar_icone('edição')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_CONSUMO.format(consumo.pk)}$'))
    tela.preencher('Local de Consumo', 'Texto', 'Cantina')
    tela.clicar_botao('Salvar').sucesso('Consumo editado com sucesso.')
    consumo.refresh_from_db()
    assert consumo.local_consumo_alimentacao == 'Cantina', 'a UI disse que editou, mas o consumo não mudou'

    tela.ir(ATENDIMENTO.format(atendimento.pk)).clicar_aba('Anamnese')
    tela.quadro('Recordatório alimentar').linha('Cantina').clicar_icone('remoção')
    tela.sucesso('Registro de consumo excluído com sucesso.')
    assert not ConsumoNutricao.objects.filter(pk=consumo.pk).exists(), 'a UI disse que excluiu, mas o consumo permanece'

    # Diagnóstico nutricional.
    tela.clicar_aba('Diagnóstico Nutricional')
    tela.aba('Diagnóstico Nutricional').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_DIAGNOSTICO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [('Diagnóstico Nutricional', 'FilteredSelectMultiple', 'Ingestão excessiva de energia'), ('Observações', 'TextArea', 'Diagnóstico E2E')]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.diagnostico_nutricional.filter(descricao='Ingestão excessiva de energia').exists(), (
        'a UI disse que salvou, mas o diagnóstico nutricional não persistiu'
    )

    # Conduta nutricional: categoria de trabalho, conduta e plano alimentar.
    tela.clicar_aba('Conduta Nutricional')
    tela.quadro('Cálculo das Necessidades Energéticas').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CATEGORIA.format(atendimento.pk)}$'))
    tela.preencher('Categoria de Trabalho', 'Lista', 'Leve')
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.categoria_trabalho == 'Leve', 'a UI disse que salvou, mas a categoria de trabalho não persistiu'

    tela.quadro('Conduta').clicar_botao('Adicionar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_CONDUTA.format(atendimento.pk)}$'))
    tela.preencher('Conduta', 'Texto rico', 'Conduta nutricional E2E')
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    registro.refresh_from_db()
    assert 'Conduta nutricional E2E' in (registro.conduta or ''), 'a UI disse que salvou, mas a conduta não persistiu'

    tela.quadro('Plano Alimentar').clicar_botao('Adicionar Plano Alimentar')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_PLANO.format(atendimento.pk)}$'))
    tela.preencher_formulario(
        [
            ('Orientação Nutricional', 'FilteredSelectMultiple', 'Orientação A'),
            ('Receitas', 'FilteredSelectMultiple', 'Receita A'),
            ('Cardápio', 'Texto rico', 'Cardápio E2E'),
            ('Sugestões de Leituras e Links', 'Texto rico', 'Sugestões E2E'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Atendimento registrado com sucesso.')
    plano = PlanoAlimentar.objects.get(atendimento=atendimento)
    assert plano.orientacao_nutricional.filter(titulo='Orientação A').exists(), (
        'a UI disse que salvou, mas a orientação nutricional do plano não persistiu'
    )

    tela.quadro('Plano Alimentar').clicar_botao('Editar Plano')
    expect(tela.pagina).to_have_url(re.compile(rf'{EDITAR_PLANO.format(plano.pk)}$'))
    tela.preencher_formulario(
        [
            ('Orientação Nutricional', 'FilteredSelectMultiple', 'Orientação A'),
            ('Receitas', 'FilteredSelectMultiple', 'Receita A'),
            ('Cardápio', 'Texto rico', 'Cardápio E2E revisado'),
            ('Sugestões de Leituras e Links', 'Texto rico', 'Sugestões E2E'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Plano alimentar editado com sucesso.')
    plano.refresh_from_db()
    assert 'revisado' in plano.cardapio, 'a UI disse que editou, mas o cardápio do plano não mudou'
    assert plano.receita_nutricional.filter(titulo='Receita A').exists(), 'a receita indicada no plano não persistiu'

    # `remover_receita` não tem ponto de entrada em tela nenhuma (rota órfã): a receita sai com
    # o plano, então o que se exercita aqui é a remoção do plano.
    tela.ir(ATENDIMENTO.format(atendimento.pk)).clicar_aba('Conduta Nutricional')
    tela.quadro('Plano Alimentar #1').clicar_botao('Remover Plano')
    tela.sucesso('Plano Alimentar excluído com sucesso.')
    assert not PlanoAlimentar.objects.filter(pk=plano.pk).exists(), 'a UI disse que removeu, mas o plano alimentar permanece'

    tela.quadro('Conduta').linha('Conduta nutricional E2E').clicar_icone('remoção')
    tela.sucesso('Conduta excluída com sucesso.')
    registro.refresh_from_db()
    assert registro.conduta is None, 'a UI disse que excluiu, mas a conduta permanece'
