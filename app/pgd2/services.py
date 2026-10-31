"""Camada de serviço do ``pgd2`` para lançamento de execuções (RIT) via GitLab.

Concentra a lógica de domínio que liga um MR do GitLab ao ``RelatorioIndividualTrabalho``
(RIT) nativo do PGD, reusando as regras e validações já existentes nos modelos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied

from rh.models import Servidor

if TYPE_CHECKING:
    from django.http import HttpRequest

    from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoEntregas, RelatorioIndividualTrabalho


def resolver_servidor_por_gitlab_username(username_gitlab: str) -> Servidor:
    """Resolve o ``rh.Servidor`` a partir do username do GitLab.

    Args:
        username_gitlab: username do autor no GitLab.

    Returns:
        O servidor vinculado ao analista/desenvolvedor ativo com esse username.

    Raises:
        ValueError: se não houver analista/desenvolvedor ativo com esse username,
            ou se o usuário não estiver vinculado a um servidor.
    """
    # Import local: evita acoplamento estático pgd2 -> demandas no carregamento do app.
    from demandas.models import AnalistaDesenvolvedor

    dev = AnalistaDesenvolvedor.objects.filter(username_gitlab=username_gitlab, ativo=True).first()
    if dev is None:
        raise ValueError(f'Nenhum analista/desenvolvedor ativo com username_gitlab={username_gitlab!r}.')
    servidor = dev.usuario.get_relacionamento()
    if not isinstance(servidor, Servidor):
        raise ValueError(f'Usuário {dev.usuario} não está vinculado a um servidor.')
    return servidor


def get_entregas_disponiveis_para_servidor(servidor: Servidor) -> list[PlanoIndividualTrabalhoEntregas]:
    """Lista as ``PlanoIndividualTrabalhoEntregas`` em que o servidor pode lançar RIT agora.

    Percorre as adesões não canceladas do servidor, seus PITs, e — quando o PIT
    permite cadastrar RIT (validação básica) — coleta as entregas elegíveis a RIT
    (``get_entregas_pit_para_rit``: não canceladas e homologadas). Não restringe ao
    período corrente: lista as entregas de todos os PITs abertos.

    Args:
        servidor: servidor cujas entregas serão listadas.

    Returns:
        Lista das entregas do PIT elegíveis a RIT.
    """
    resultado: list[PlanoIndividualTrabalhoEntregas] = []
    for pit in get_pits_abertos_para_rit(servidor):
        resultado.extend(pit.get_entregas_pit_para_rit())
    return resultado


def get_pits_abertos_para_rit(servidor: Servidor) -> list[PlanoIndividualTrabalho]:
    """Lista os PITs do servidor que ainda aceitam cadastro de RIT (validação básica).

    Args:
        servidor: servidor cujos PITs serão listados.

    Returns:
        PITs não cancelados, das adesões do servidor, em que o RIT ainda pode ser cadastrado.
    """
    from pgd2.models import SolicitacaoAdesaoServidor

    user = servidor.get_user()
    return [
        pit
        for adesao in SolicitacaoAdesaoServidor.objects.filter(servidor=servidor)
        for pit in adesao.get_pits()
        if pit.pode_cadastrar_entrega_rit(user, valida_apenas_o_basico=True)
    ]


def lancar_rit_via_gitlab(
    entrega_pit: PlanoIndividualTrabalhoEntregas,
    dados: dict[str, Any],
    *,
    gitlab_project_id: int | None = None,
    gitlab_mr_iid: int | None = None,
    request: HttpRequest | None = None,
) -> RelatorioIndividualTrabalho:
    """Cria/atualiza o ``RelatorioIndividualTrabalho`` a partir de um MR do GitLab, ou sem MR.

    Com MR, é idempotente por ``(gitlab_project_id, gitlab_mr_iid)``: se já existe RIT para esse MR,
    atualiza-o (upsert); senão cria. Sem MR (deploy, investigação), sempre cria um RIT novo.
    Reusa a regra do form manual (cálculo do tempo em teletrabalho + ``calcular_pit``).

    Args:
        entrega_pit: ``PlanoIndividualTrabalhoEntregas`` inferida para a execução.
        dados: campos do RIT (titulo, descricao, tempo_executado,
            perc_executada_em_teletrabalho, data_inicio, data_fim, quantidade_progresso).
        gitlab_project_id: ID do projeto no GitLab; ignorado sem MR.
        gitlab_mr_iid: IID do MR no GitLab; ``None`` lança o RIT sem MR.
        request: requisição HTTP, usada apenas para auditoria (quando ausente, é pulada).

    Returns:
        O ``RelatorioIndividualTrabalho`` criado/atualizado.

    Raises:
        PermissionDenied: se o PGD não permite cadastrar RIT nesta entrega agora
            (período fechado, mês já enviado, servidor errado).
    """
    from pgd2.models import RegistroAcaoPlanoIndividualTrabalho, RelatorioIndividualTrabalho

    pit = entrega_pit.pit
    servidor = pit.adesao.servidor
    user = servidor.get_user()

    if not pit.pode_cadastrar_entrega_rit(user, entrega_pit.id):
        raise PermissionDenied('Servidor não pode cadastrar RIT nesta entrega agora (período fechado, mês já enviado ou regra do PGD).')

    if gitlab_mr_iid is None:
        # sem MR não há chave: filtrar por None viraria IS NULL e casaria com qualquer RIT lançado à mão
        rit = RelatorioIndividualTrabalho()
    else:
        rit = RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=gitlab_project_id, gitlab_mr_iid=gitlab_mr_iid).first()
        rit = rit or RelatorioIndividualTrabalho(gitlab_project_id=gitlab_project_id, gitlab_mr_iid=gitlab_mr_iid)

    rit.entrega_pit = entrega_pit
    rit.titulo = dados.get('titulo')
    rit.descricao = dados.get('descricao', '')
    rit.tempo_executado = dados.get('tempo_executado')
    rit.perc_executada_em_teletrabalho = dados.get('perc_executada_em_teletrabalho') or 0
    rit.data_inicio = dados.get('data_inicio')
    rit.data_fim = dados.get('data_fim')
    rit.quantidade_progresso = dados.get('quantidade_progresso') or 0

    if rit.perc_executada_em_teletrabalho and rit.tempo_executado:
        rit.tempo_executada_em_teletrabalho = (rit.perc_executada_em_teletrabalho / 100) * rit.tempo_executado
    else:
        rit.tempo_executada_em_teletrabalho = 0
    rit.save()

    pit.calcular_pit()

    if request is not None:
        from djtools.middleware import threadlocals as tl

        # Sob token de máquina (TrustedAppAuth), o threadlocal carrega o usuário do app OAuth (um User real),
        # não o ``AnonymousUser``. Forçamos o autor da auditoria (``CurrentUserField`` ``user`` do registro)
        # a ser o servidor dono do RIT — semântica correta da ação.
        usuario_anterior = tl.context.user if hasattr(tl.context, 'user') else None
        tl.context.user = user
        try:
            RegistroAcaoPlanoIndividualTrabalho.registrar(
                request=request,
                tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CADASTROU_ENTREGA_RIT,
                pit=pit,
                obs=f'Lançado automaticamente a partir do MR !{gitlab_mr_iid}.' if gitlab_mr_iid else 'Lançado automaticamente, sem MR associado.',
            )
        finally:
            tl.context.user = usuario_anterior

    return rit
