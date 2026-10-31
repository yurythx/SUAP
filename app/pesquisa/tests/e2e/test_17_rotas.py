"""Smoke de rota do módulo `pesquisa` (o eixo do modo 2: a unidade é a rota).

O módulo tem 343 rotas em `urls.py` e 338 views distintas — quase tudo endpoint de ação,
não tela de menu. Este arquivo cobre o que **pode** ser aberto: as telas de leitura e as
páginas de formulário, que renderizam sem mudar estado. Tudo o mais entra em
`ROTAS_DISPENSADAS`, no `conftest.py`, com o motivo medido rota a rota.

A abertura é em lote e por papel, com `Tela.buscar` — GET pela sessão do browser, sem
renderizar (ver a docstring de lá): um módulo com centenas de rotas custaria dezenas de
minutos a `ir`, e o que se afirma num smoke é só "a view respondeu". A falha lista **todas**
as rotas quebradas de uma vez, senão cada execução revelaria uma só.

Este arquivo é o eixo de rota: o behave do módulo foi aposentado, e aqui a unidade de cobertura é
a rota. As rotas de obra e de propriedade intelectual ficam em `test_18_rotas_editora_pi.py`: os
alvos delas vêm do 12-14 e do 16, que rodam numa suíte à parte (`pesquisa-2`, ver `DIVISOES_E2E`
no `suap_check`) — aqui ficam só as que dependem da cadeia 01-11 e dos laboratórios (15).
"""

import pytest

from pesquisa.tests.e2e.alvos_rotas import relatorio_de_guardadas

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas que não recebem parâmetro, **agrupadas pelo papel que as alcança**. O papel é medido,
# não deduzido: as três primeiras rodadas deste smoke moveram três rotas de `diretor` para
# `parecerista_obra` e `integrante_editora` porque o Diretor levava 403 nelas.
ROTAS_DO_PARECERISTA = [
    '/pesquisa/emitir_declaracao_parecerista_obra/',
    '/pesquisa/indicar_areas_conhecimento_de_interesse/',
]

ROTAS_DA_EDITORA = [
    '/pesquisa/listar_pareceristas_obras/',
]

ROTAS_DO_DIRETOR = [
    '/pesquisa/adicionar_comissao/',
    '/pesquisa/atividades_dos_avaliadores/',
    '/pesquisa/autocadastro_parecerista/',
    '/pesquisa/avaliacao/',
    '/pesquisa/avaliar_recursos/',
    '/pesquisa/cadastrar_parceria/',
    '/pesquisa/cadastrar_transferencia/',
    '/pesquisa/classificacao_projetos/',
    '/pesquisa/distribuir_bolsas/',
    '/pesquisa/editais/',
    '/pesquisa/editais_abertos/',
    '/pesquisa/editais_abertos_submissao_obra/',
    '/pesquisa/emitir_declaracao_avaliador/',
    '/pesquisa/estatistica_projetos_por_campus/',
    '/pesquisa/estatisticas/',
    '/pesquisa/gerenciar_supervisores/',
    '/pesquisa/indicadores/',
    '/pesquisa/laboratorios_pesquisa/',
    '/pesquisa/lista_email_coordenadores/',
    '/pesquisa/lista_mensal_bolsistas/',
    '/pesquisa/listar_avaliadores/',
    '/pesquisa/listar_equipes_dos_projetos/',
    '/pesquisa/listar_projetos_em_atraso/',
    '/pesquisa/metodologia_trl/',
    '/pesquisa/meus_projetos/',
    '/pesquisa/meus_projetos_autorizados_sem_fomento/',
    '/pesquisa/meus_recursos/',
    '/pesquisa/minhas_obras/',
    '/pesquisa/minhas_solicitacoes_servicos/',
    '/pesquisa/parcerias_dashboard/',
    '/pesquisa/pi_dashboard/',
    '/pesquisa/pre_avaliacao/selecionar_avaliadores/',
    '/pesquisa/projetos_em_execucao/',
    '/pesquisa/projetos_pendentes_anuencia/',
    '/pesquisa/relatorio_dados_cartao_pesquisador/',
    '/pesquisa/relatorio_dimensao/',
    '/pesquisa/relatorio_empreendimentos_incubadora/',
    '/pesquisa/relatorio_estatistica_laboratorios/',
    '/pesquisa/relatorio_propriedades/',
    '/pesquisa/relatorio_quantitativo_docentes_por_campus/',
    '/pesquisa/relatorio_quantitativo_taes_por_campus/',
    '/pesquisa/relatorio_transferencias/',
    '/pesquisa/resultado_edital/',
    '/pesquisa/resultado_edital_parcial/',
    '/pesquisa/solicitacoes_alteracao_equipe/',
    '/pesquisa/solicitacoes_de_cancelamento/',
    '/pesquisa/solicitacoes_de_recurso/',
    '/pesquisa/solicitacoes_inclusao_equipe/',
    '/pesquisa/tipo_laboratorio_multiusuario/',
    '/pesquisa/tornar_avaliador/',
]


def test_rotas_abrem(abrir_rotas, alvos, guardadas):
    """Cada papel abre as rotas que lhe cabem — leitura e formulários.

    Uma asserção por papel, e não por rota, porque o login é real a cada teste: parametrizar 54
    rotas custaria 54 logins. Em compensação a falha lista **todas** as rotas quebradas de uma
    vez, senão cada execução revelaria uma só.
    """
    for papel, rotas in (
        ('diretor', ROTAS_DO_DIRETOR),
        ('parecerista_obra', ROTAS_DO_PARECERISTA),
        ('integrante_editora', ROTAS_DA_EDITORA),
    ):
        abrir_rotas(papel, rotas)

    for papel, rotas in ROTAS_COM_PARAMETRO.items():
        abrir_rotas(papel, list(rotas), alvos)
    relatorio_de_guardadas(guardadas)


# Rotas que só abrem numa **janela** do edital — a view recusa fora do período. Elas ficam num
# teste próprio com a data, e não no primeiro, porque a data é do módulo inteiro: mover o
# relógio para a seleção quebraria as rotas que dependem da inscrição.
ROTAS_EM_SELECAO = ['/pesquisa/projetos_especial_pre_aprovados/{edital}/']


def test_rotas_que_dependem_da_janela_do_edital(abrir_rotas, alvos, em_data, guardadas):
    """O avaliador abre a lista de projetos no período de seleção do edital.

    `projetos_especial_pre_aprovados` levanta `PermissionDenied` fora do período
    (`views.py:1238`), então elas não abrem com a data base do arquivo — o behave as roda
    depois de mover a data, e aqui é o `em_data` que faz o mesmo.
    """
    em_data('16/01/2018')
    abrir_rotas('avaliador_1', ROTAS_EM_SELECAO, alvos)
    relatorio_de_guardadas(guardadas)


ROTAS_COM_PARAMETRO_COORDENADOR_LABORATORIO = [
    '/pesquisa/avaliar_laboratorio/{laboratorio}/',
    '/pesquisa/cadastrar_equipamento_laboratorio/{laboratorio}/',
    '/pesquisa/cadastrar_foto_laboratorio/{laboratorio}/',
    '/pesquisa/cadastrar_material_laboratorio/{laboratorio}/',
    '/pesquisa/cadastrar_servico_laboratorio/{laboratorio}/',
    '/pesquisa/laboratorio_pesquisa/{laboratorio}/',
    '/pesquisa/solicitar_servico_laboratorio/{laboratorio}/',
    '/pesquisa/vincular_projeto_laboratorio/{laboratorio}/',
]


ROTAS_COM_PARAMETRO_DIRETOR = [
    '/pesquisa/adicionar_anexo_diverso_projeto/{projeto}/',
    '/pesquisa/adicionar_anexo_do_projeto/{participacao}/',
    '/pesquisa/adicionar_comissao_por_area/{comissao}/',
    '/pesquisa/adicionar_recurso/{edital}/',
    '/pesquisa/adicionar_relatorio/{projeto}/',
    '/pesquisa/alterar_coordenador/{projeto}/',
    '/pesquisa/aprovar_projetos_com_bolsa/{edital}/',
    '/pesquisa/aprovar_projetos_sem_fomento/{edital}/',
    '/pesquisa/cadastrar_dados_bancarios/{participacao}/',
    '/pesquisa/classificacao_projetos_edital/{edital}/',
    '/pesquisa/clonar_edital/{edital}/',
    '/pesquisa/clonar_etapa/{meta}/',
    '/pesquisa/divulgar_resultado_edital/{edital}/',
    '/pesquisa/edital/{edital}/',
    '/pesquisa/editar_participante_aluno/{projeto}/{participacao}/',
    '/pesquisa/editar_participante_colaborador/{projeto}/{participacao}/',
    '/pesquisa/editar_participante_servidor/{projeto}/{participacao}/',
    '/pesquisa/exportar_atividades_projeto_xls/{projeto}/',
    '/pesquisa/gerar_lista_frequencia/{projeto}/',
    '/pesquisa/gerenciar_bolsas/{edital}/',
    '/pesquisa/gerenciar_historico_projeto/{projeto}/',
    '/pesquisa/historico_equipe/{participacao}/',
    '/pesquisa/imprimir_projeto/{projeto}/',
    '/pesquisa/inativar_projeto/{projeto}/',
    '/pesquisa/indicar_auxiliar_projeto/{projeto}/',
    '/pesquisa/indicar_coorientador_projeto/{projeto}/',
    '/pesquisa/indicar_orientador_projeto/{projeto}/',
    '/pesquisa/lista_emails_comissao/{comissao}/',
    '/pesquisa/notificar_servidores_edital/{edital}/',
    '/pesquisa/plano_trabalho_participante/{projeto}/{participacao}/',
    '/pesquisa/projeto/{projeto}/',
    '/pesquisa/projetos_lista_espera/{edital}/',
    '/pesquisa/reabrir_projeto/{projeto}/',
    '/pesquisa/relatorio_projeto/{projeto}/',
    '/pesquisa/remover_participante/{participacao}/',
    '/pesquisa/salvar_membros_da_comissao/{comissao}/',
    '/pesquisa/selecionar_avaliadores/{edital}/',
    '/pesquisa/selecionar_supervisor/{edital}/',
    '/pesquisa/selecionar_supervisor_do_projeto/{projeto}/',
    '/pesquisa/solicitar_alteracao_equipe/{projeto}/',
    '/pesquisa/solicitar_inclusao_equipe/{projeto}/',
    '/pesquisa/ver_membros_comissao/{comissao}/',
    '/pesquisa/visualizar_projetos_avaliador/{edital}/',
]


ROTAS_COM_PARAMETRO_INTEGRANTE_EDITORA = [
    '/pesquisa/itens_selecionados_para_recursos/{projeto}/',
]


ROTAS_COM_PARAMETRO_COORDENADOR_PROJETO = []


ROTAS_COM_PARAMETRO_COORDENADOR_PESQUISA = []

ROTAS_COM_PARAMETRO_AVALIADOR_1 = []

ROTAS_COM_PARAMETRO = {
    'avaliador_1': ROTAS_COM_PARAMETRO_AVALIADOR_1,
    'coordenador_pesquisa': ROTAS_COM_PARAMETRO_COORDENADOR_PESQUISA,
    'coordenador_projeto': ROTAS_COM_PARAMETRO_COORDENADOR_PROJETO,
    'diretor': ROTAS_COM_PARAMETRO_DIRETOR,
    'integrante_editora': ROTAS_COM_PARAMETRO_INTEGRANTE_EDITORA,
    'coordenador_laboratorio': ROTAS_COM_PARAMETRO_COORDENADOR_LABORATORIO,
}
