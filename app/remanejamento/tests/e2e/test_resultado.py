"""Fluxo: processamento, publicação e os portões de data do resultado.

É o coração do módulo — onde a classificação vira alocação de gente em campus — e a parte com
mais regra por linha de tela. Quatro coisas deste arquivo não se verificam em lugar nenhum:

* **processar** é assíncrono por desenho (``remanejamento/tasks.py`` decora com
  ``djtools.assincrono.task``): o clique leva a ``/djtools/process/<uuid>/``, e é essa página
  que diz se terminou. Sob teste a tarefa roda na própria request (``running_tests()``,
  ``djtools/assincrono/__init__.py:131``), mas a tela é a mesma de produção;
* a **classificação** é o que decide quem é removido: com uma vaga e dois candidatos do mesmo
  cargo, o critério de maior tempo de serviço tem de escolher um e deixar o outro fora;
* a **área correlata** faz um servidor de outra área concorrer à vaga (``models.py:570-584``);
* os **portões de data** de resultado final e homologação: publicar antes da hora é o erro
  caro, e os dois recusam com mensagem explicando o que falta (``views.py:483`` e ``:360``).
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

GERENCIAR = '/remanejamento/edital/{}/gerenciar/'
PROCESSAR = '/remanejamento/edital/{}/processar/'
PUBLICAR_PARCIAL = '/remanejamento/edital/{}/publicar_resultado_parcial/'
PUBLICAR_FINAL = '/remanejamento/edital/{}/publicar_resultado_final/'
PUBLICAR_HOMOLOGACAO = '/remanejamento/edital/{}/publicar_homologacao_resultado_final/'
INSCRICOES_CSV = '/remanejamento/inscricoes_csv/{}/'
CONTEMPLADA_EXTRAORDINARIA = '/remanejamento/adicionar_inscricao_contemplada_extraordinaria/{}/'
VINCULAR_DOCUMENTO = '/remanejamento/edital/{}/resultado_parcialvincular_documento_resultado/'


def test_processa_resultado_e_classifica_os_inscritos(logado_remanejamento, servidores, edital_para_processar):
    """Processa pelo botão da tela e confere quem foi contemplado, e para onde.

    As três asserções são independentes de propósito: ``candidato`` entra pelo cargo simples e
    ganha do ``concorrente`` pelo tempo de serviço (única vaga); ``candidata_correlata`` entra
    pela área correlata, que é outro ramo do classificador; e o ``concorrente`` **não** pode
    ter registro nenhum — "sobrou de fora" é um estado, não uma ausência de linha.
    """
    from remanejamento.models import InscricaoContemplada
    from remanejamento.tests.e2e.conftest import nome_na_listagem

    edital, _inscricoes = edital_para_processar
    tela = Tela(logado_remanejamento('coordenador')).ir(GERENCIAR.format(edital.pk))
    tela.clicar_botao('Processar Resultado')

    tela.ver_texto('Processamento de Resultado concluído com sucesso')
    assert PROCESSAR.format(edital.pk) in tela.pagina.url or '/djtools/process/' in tela.pagina.url, (
        f'o botão deveria levar ao processamento (ou à página da tarefa), foi para {tela.pagina.url!r}'
    )

    contempladas = {c.inscricao.servidor.matricula: c.campus_destino.sigla for c in InscricaoContemplada.objects.filter(inscricao__edital=edital)}
    assert contempladas == {
        servidores['candidato'].matricula: 'B0',
        servidores['candidata_correlata'].matricula: 'B0',
    }, f'a classificação contemplou {contempladas}'

    tela.ir(GERENCIAR.format(edital.pk))
    resultados = tela.quadro('Resultados')
    resultados.linha(nome_na_listagem(servidores['candidato'])).ver_texto('B0')
    resultados.linha(nome_na_listagem(servidores['candidata_correlata'])).ver_texto('B0')


def test_publica_resultado_parcial_como_documento_eletronico(logado_remanejamento, edital_para_processar):
    """Publicar é gerar um ``DocumentoTexto`` e amarrá-lo ao edital.

    O botão "Publicar Resultado Parcial" só aparece quando ``pode_publicar_resultado_parcial``
    (``models.py:931``) — a data do resultado parcial já passou e ainda não há documento
    assinado. A publicação leva para o documento gerado, compartilha-o com os coordenadores e
    muda a situação das contempladas para "Publicada em Resultado Parcial": é essa mudança de
    situação que impede o reprocessamento de recriá-las (``models.py:504``).
    """
    from remanejamento.models import InscricaoContemplada

    edital, _ = edital_para_processar
    tela = Tela(logado_remanejamento('coordenador')).ir(PROCESSAR.format(edital.pk))
    tela.ver_texto('Processamento de Resultado concluído com sucesso')

    tela.ir(GERENCIAR.format(edital.pk))
    tela.clicar_botao('Publicar Resultado Parcial')

    tela.sucesso('Resultado Parcial de Remoção Interna gerado com sucesso')
    edital.refresh_from_db()
    assert edital.resultado_parcial_documentotexto, 'a UI disse que publicou, mas o edital não aponta para documento nenhum'
    assert edital.resultado_parcial_documentotexto.assunto.startswith('Resultado Parcial'), (
        f'o documento nasceu com o assunto {edital.resultado_parcial_documentotexto.assunto!r}'
    )
    situacoes = set(InscricaoContemplada.objects.filter(inscricao__edital=edital).values_list('situacao', flat=True))
    assert situacoes == {InscricaoContemplada.PUBLICADA_PARCIAL}, f'as contempladas ficaram em {situacoes}'

    tela.ir(GERENCIAR.format(edital.pk))
    tela.clicar_aba('Resultado Parcial')
    tela.aba('Resultado Parcial').ver_botao('Visualizar documento')


def test_resultado_final_e_homologacao_recusam_publicacao_fora_de_ordem(logado_remanejamento, edital_para_processar):
    """Os dois portões de data, medidos na tela: nenhum documento é criado antes da hora.

    A ordem é lei no processo: o resultado final exige o parcial **finalizado** e o fim do
    prazo de recursos (``models.py:951``); a homologação exige o final finalizado e a data de
    homologação (``:959``). Como o edital desta fixture nem publicou o parcial, os dois recusam
    — e recusam com a mensagem que diz o que falta, que é o que o coordenador lê.

    Um teste para os dois porque é a mesma invariante em dois degraus, e porque a recusa do
    segundo pressupõe a do primeiro.
    """
    edital, _ = edital_para_processar

    tela = Tela(logado_remanejamento('coordenador')).ir(PUBLICAR_FINAL.format(edital.pk))
    tela.erro('Resultado Final somente pode ser publicado')
    edital.refresh_from_db()
    assert edital.resultado_final_documentotexto is None, 'a tela recusou, mas o documento do resultado final foi criado assim mesmo'

    tela.ir(PUBLICAR_HOMOLOGACAO.format(edital.pk))
    tela.erro('somente pode ser publicada')
    edital.refresh_from_db()
    assert edital.resultado_final_homologacao_documentotexto is None, 'a tela recusou, mas o documento de homologação foi criado assim mesmo'


def test_coordenador_exporta_a_planilha_de_inscritos(logado_remanejamento, edital_para_processar):
    """A exportação da listagem de inscritos responde uma planilha, não uma tela.

    ``inscricoes_csv`` (``views.py:961``) devolve ``XlsResponse`` — não há o que afirmar pela
    interface além do desfecho da requisição, por isso a rota é exercitada com ``Tela.buscar``,
    que usa a sessão do browser sem renderizar. O ``content-type`` é a prova de que a planilha
    foi gerada, e não uma tela de erro com status 200.
    """
    edital, _ = edital_para_processar
    tela = Tela(logado_remanejamento('coordenador')).ir(GERENCIAR.format(edital.pk))

    resposta = tela.buscar(INSCRICOES_CSV.format(edital.pk))

    assert resposta.status == 200, f'a exportação respondeu {resposta.status}'
    assert 'spreadsheetml' in resposta.headers.get('content-type', ''), (
        f'a exportação não devolveu planilha: {resposta.headers.get("content-type")!r}'
    )
    assert '.xlsx' in resposta.headers.get('content-disposition', ''), f'a planilha veio sem anexo: {resposta.headers.get("content-disposition")!r}'


def test_tela_de_vinculo_de_documento_de_resultado_abre_para_o_coordenador(logado_remanejamento, edital_para_processar):
    """A tela que amarra um documento já existente ao resultado do edital.

    É o caminho de exceção do RH sistêmico: quando o resultado foi redigido fora do SUAP, o
    documento é **vinculado** em vez de gerado (``views.py:861-885``). O teste afirma só a
    abertura da tela e a oferta do campo, porque submeter exigiria um ``DocumentoTexto`` de
    tipo "Edital" já existente — que nada neste módulo cria, e cuja criação é fluxo do
    ``documento_eletronico``, não deste módulo.

    ``tipo_doc`` é parte do caminho sem separador (``urls.py:34``): a rota é
    ``.../resultado_parcialvincular_documento_resultado/``, e não um segmento próprio.
    """
    edital, _ = edital_para_processar

    tela = Tela(logado_remanejamento('coordenador')).ir(VINCULAR_DOCUMENTO.format(edital.pk))

    tela.ver_texto('Vincular documento de Resultado')
    tela.ver_botao('Salvar')
    assert 'Documento de Resultado:' in tela.rotulos_na_tela(), f'a tela abriu sem o campo do documento: {tela.rotulos_na_tela()}'


def test_inclui_inscricao_contemplada_extraordinaria(logado_remanejamento, servidores, edital_para_processar):
    """Contempla, com justificativa, quem o processamento deixou de fora.

    É a válvula de escape do resultado — decisão judicial, erro de dado, desistência de outro
    contemplado — e por isso a justificativa é obrigatória (``forms.py:471``). A tela só abre
    depois de existir resultado processado (``views.py:616-631``), e o ``save`` herda a
    **situação da última contemplada válida** (``forms.py:517-531``): a inclusão extraordinária
    entra na mesma fase do resultado corrente, não numa fase anterior.

    O campus de origem é validado contra a lotação real do servidor (``forms.py:500-509``), o
    que amarra este formulário ao mesmo dado que o processamento usa.
    """
    from remanejamento.models import InscricaoContemplada

    edital, inscricoes = edital_para_processar
    tela = Tela(logado_remanejamento('coordenador')).ir(PROCESSAR.format(edital.pk))
    tela.ver_texto('Processamento de Resultado concluído com sucesso')
    excluido = inscricoes['concorrente']
    assert not InscricaoContemplada.objects.filter(inscricao=excluido).exists(), 'o concorrente já estava contemplado antes da inclusão'

    tela.ir(CONTEMPLADA_EXTRAORDINARIA.format(edital.pk))
    tela.preencher_formulario(
        [
            # "Inscricao", sem acento: o campo é declarado sem `label` (`forms.py:478`) e o
            # Django deriva o rótulo do nome do atributo, não do `verbose_name` do model.
            # A busca é pelo número do DOU porque `Inscricao` não tem `SEARCH_FIELDS` e o
            # autocomplete cai no fallback "todo CharField do model"
            # (`djtools/utils/autocomplete.py:75-81`) — o pk NÃO é pesquisável, embora seja o
            # que aparece no rótulo. Daí o par busca/opção.
            ('Inscricao', 'autocomplete', excluido.dou_numero, str(excluido)),
            # Os dois campi são autocomplete e não lista: `MetaModelFormPlus` troca o widget de
            # toda `ModelChoiceField` por `AutocompleteWidget` (o `select` renderizado vem
            # `aria-hidden` e vazio, com as opções vindo por AJAX).
            ('Campus origem', 'autocomplete', 'A0'),
            ('Campus destino', 'autocomplete', 'B0'),
            ('Justificativa', 'texto', 'Determinação judicial no processo 0000000-00.2026.4.05.8400.'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Inscrição Contemplada Extraordinária incluída com sucesso')
    contemplada = InscricaoContemplada.objects.filter(inscricao=excluido).first()
    assert contemplada, 'a UI disse que incluiu, mas a contemplação não persistiu'
    assert contemplada.campus_destino.sigla == 'B0', f'o destino gravado foi {contemplada.campus_destino.sigla!r}'
    assert contemplada.situacao == InscricaoContemplada.CONTEMPLADO, f'a inclusão entrou na situação {contemplada.situacao!r}'
    assert contemplada.justificativa.startswith('Determinação judicial'), 'a justificativa não foi gravada'
