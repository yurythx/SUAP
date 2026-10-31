"""Smoke das rotas próprias do Documento Eletrônico.

Cada literal cobre uma rota declarada em ``urls.py``. O GET usa sessão autenticada e confirma
que a view responde sem erro 5xx; endpoints que exigem POST devolvem 405, enquanto ids
inexistentes podem devolver 404 após a rota ser efetivamente despachada.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ROTAS = [
    '/documento_eletronico/alterar_nivel_acesso_documento_digitalizado/1/',
    '/documento_eletronico/alterar_nivel_acesso_documento_digitalizado_anexo_simples/1/',
    '/documento_eletronico/alterar_nivel_acesso_documento_texto/1/',
    '/documento_eletronico/alterar_nivel_acesso_documento_texto_anexo/1/',
    '/documento_eletronico/anexar_documento_a_documentotexto/1/1/',
    '/documento_eletronico/assinar_documento/1/',
    '/documento_eletronico/assinar_documento_lote/',
    '/documento_eletronico/assinar_via_senha_documento_pessoal/1/',
    '/documento_eletronico/autenticar_documento/',
    '/documento_eletronico/avaliar_solicitacao_compartilhamento_documento_digitalizado/1/1/',
    '/documento_eletronico/cancelar_documento/1/',
    '/documento_eletronico/cancelar_revisao/1/',
    '/documento_eletronico/clonar_documento/1/',
    '/documento_eletronico/clonar_modelo_documento/1/',
    '/documento_eletronico/clonar_tipo_documento/1/',
    '/documento_eletronico/concluir_documento/1/',
    '/documento_eletronico/criar_documento_relacionado/1/',
    '/documento_eletronico/consulta_publica/',
    '/documento_eletronico/conteudo_documento/1/',
    '/documento_eletronico/dashboard/',
    '/documento_eletronico/desanexar_documento/1/1/',
    '/documento_eletronico/documento_texto_editar_interessados/1/',
    '/documento_eletronico/documento_texto_reprocessar_interessados/1/',
    '/documento_eletronico/editar_documento/1/',
    '/documento_eletronico/editar_documento/1/remontar_corpo/',
    '/documento_eletronico/editar_documento_digitalizado_anexo_simples/1/',
    '/documento_eletronico/editar_modelo_documento/1/',
    '/documento_eletronico/editar_tags_anonimizacao/1/',
    '/documento_eletronico/enviar_codigo_verificacao_email',
    '/documento_eletronico/excluir_documento_texto/1/',
    '/documento_eletronico/exportar_pdfa/1/retrato/',
    '/documento_eletronico/finalizar_documento/1/',
    '/documento_eletronico/gerenciar_compartilhamento_documento/1/',
    '/documento_eletronico/gerenciar_compartilhamento_setor/',
    '/documento_eletronico/gerenciar_favoritos/1/add/',
    '/documento_eletronico/get_hipoteses_legais_by_documento_nivel_acesso/1/',
    '/documento_eletronico/imprimir_documento_pdf/1/retrato/',
    '/documento_eletronico/listar_documentos_anexar/1/',
    '/documento_eletronico/modelos_tipo_documento/1/',
    '/documento_eletronico/nivel_acesso_padrao_classificacoes_modelo_documento/1/',
    '/documento_eletronico/rejeitar_assinatura/1/',
    '/documento_eletronico/rejeitar_revisao/1/',
    '/documento_eletronico/remover_solicitacao_assinatura/1/',
    '/documento_eletronico/remover_vinculo_documento_texto/1/1/',
    '/documento_eletronico/retornar_para_rascunho/1/',
    '/documento_eletronico/revisar_documento/1/',
    '/documento_eletronico/solicitar_assinatura/1/',
    '/documento_eletronico/solicitar_assinatura_com_anexacao/1/',
    '/documento_eletronico/solicitar_compartilhamento_documento_digitalizado/1/1/',
    '/documento_eletronico/solicitar_revisao/1/',
    '/documento_eletronico/verificar_documento_externo/',
    '/documento_eletronico/verificar_integridade/1/',
    '/documento_eletronico/vincular_documentos/1/',
    '/documento_eletronico/visualizar_documento/1/',
    '/documento_eletronico/visualizar_documento_digitalizado/1/',
    '/documento_eletronico/visualizar_documento_digitalizado_pessoal/1/',
    '/documento_eletronico/visualizar_documento_digitalizado_anexo_simples/1/',
    '/documento_eletronico/visualizar_variaveis/',
]


def test_rotas_respondem_sem_erro_5xx(logado_documento, documento_seed) -> None:
    """Executa smoke de todas as rotas, aceitando 4xx esperado por método/id/permissão."""
    tela = Tela(logado_documento('gerente'))
    for rota in ROTAS:
        if rota == '/documento_eletronico/meus_documentos/':
            continue
        resposta = tela.buscar(rota)
        assert 100 <= resposta.status < 500, f'{rota}: view respondeu {resposta.status}'
