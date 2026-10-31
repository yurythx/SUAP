"""Rotas que antes eram dispensadas: geração de arquivo e ação de estado por GET.

A dispensa dessas rotas dizia "corromperia a cadeia num banco reusado" — motivo de harness,
não de navegabilidade. Elas **são** navegáveis: o que faltava era objeto próprio para gravar
em cima. Aqui cada ação atua sobre objeto criado por ``edu/tests/e2e/seed_rotas.py``,
pertencente ao aluno do smoke, e as cinco transições de ``AtividadePraticaProfissional`` têm
**uma linha cada** — compartilhar uma só faria o resultado depender da ordem dos grupos.

As rotas de arquivo afirmam mais do que "abriu": ``content-type`` de documento e corpo
não-vazio (``abrir_rotas(..., arquivo=True)``). O SUAP responde 200 com HTML quando recusa a
geração, e um smoke que só olha o status chama isso de sucesso.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# `exportar_xls_aluno` lê escopo/turma/xls da querystring que a listagem monta. O literal fica
# **limpo** para o gate continuar casando o padrão da rota; a querystring vai à parte. É a
# única destas que devolve arquivo de verdade (`HttpResponse` com o XLS).
EXPORTACAO = (('/edu/exportar_xls_aluno/', '?escopo=turma&turma={turma_da_cadeia}&xls=alunos_na_turma'),)

# Os "documentos" do aluno são `@rtr()`: devolvem HTML, e o PDF sai de um parâmetro da própria
# tela. Medido — a asserção de arquivo os reprovava por `content-type: text/html`. Usam o aluno
# da CADEIA porque `atestadofrequencia_pdf` (`edu/views/pdfs.py:421`) recusa quem não tem
# histórico; são rotas de leitura, não alteram nada.
DOCUMENTOS = (
    '/edu/atestado_frequencia_digital/{aluno}/',
    '/edu/atestado_frequencia_fisico/{aluno}/',
)

# Ações de estado sobre objetos do smoke. Cancelar e desfazer vêm em par e nesta ordem: juntas
# devolvem a matrícula-diário ao estado inicial, e é o que torna o grupo re-executável.
ACOES = (
    '/edu/processar_pedidos_matricula/{configuracao_pedido_matricula}/',
    '/edu/publicar_questaoeducacenso/{registro_educacenso}/{um}/',
    '/edu/auditoria/{auditoria_ensino}/{acao_auditoria}/',
    # O par vem nesta ordem de propósito: cancelar e desfazer devolvem a matrícula-diário
    # ao estado inicial, e é isso que deixa o grupo re-executável no mesmo banco.
    '/edu/cancelar_matricula_diario/{matricula_diario_smoke}/',
    '/edu/desfazer_cancelamento_matricula_diario/{matricula_diario_smoke}/',
    # `emitir_historico_legado_pdf` é `@rtr('emitir_historico_pdf.html')`: devolve HTML, não
    # arquivo — o PDF sai de um parâmetro da própria tela. Fica no grupo comum.
    '/edu/emitir_historico_legado_pdf/{aluno}/',
)

PRATICA_PROFISSIONAL = (
    '/edu/atividadepraticaprofissional/{pratica_iniciar}/iniciar/',
    '/edu/atividadepraticaprofissional/{pratica_deferir}/deferir/',
    '/edu/atividadepraticaprofissional/{pratica_indeferir}/indeferir/',
    '/edu/atividadepraticaprofissional/{pratica_desconsiderar}/desconsiderar/',
    '/edu/atividadepraticaprofissional/{pratica_reconsiderar}/reconsiderar/',
)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', EXPORTACAO, id='exportacao'),
    ],
)
def test_rotas_de_arquivo_geram_documento(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo, arquivo=True)


@pytest.mark.parametrize(
    ('papel', 'grupo'),
    [
        pytest.param('admin_academico', DOCUMENTOS, id='documentos'),
        pytest.param('admin_academico', ACOES, id='acoes'),
        pytest.param('admin_academico', PRATICA_PROFISSIONAL, id='pratica-profissional'),
    ],
)
def test_rotas_de_acao_abrem(abrir_rotas, papel, grupo):
    abrir_rotas(papel, grupo)
