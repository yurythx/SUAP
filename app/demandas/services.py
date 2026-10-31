import re
from collections.abc import Iterable
from datetime import date
from html import unescape

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.html import strip_tags
from sentry_sdk import capture_exception

from comum.models import User
from demandas.models import (
    Demanda,
    Entrega,
    Especificacao,
    HistoricoEntrega,
    RevisaoEspecificacao,
    Situacao,
    StatusEntrega,
)
from demandas.utils import Notificar, adicionar_comentario


def _texto_para_markdown(valor: object) -> str:
    if not valor:
        return 'Não definido'

    texto = force_str(valor)
    texto = re.sub(r'(?is)<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', _converter_link, texto)
    texto = re.sub(r'(?is)<ol[^>]*>(.*?)</ol>', _converter_lista_ordenada, texto)
    texto = re.sub(r'(?is)<ul[^>]*>(.*?)</ul>', _converter_lista_nao_ordenada, texto)
    texto = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', texto)
    texto = re.sub(r'(?i)</\s*(p|div|h[1-6]|li|tr)\s*>', '\n', texto)
    texto = re.sub(r'(?i)<\s*li[^>]*>', '- ', texto)
    texto = unescape(strip_tags(texto))
    linhas = [re.sub(r'[ \t]+', ' ', linha).strip() for linha in texto.splitlines()]
    linhas = [linha for linha in linhas if linha]
    return '\n'.join(linhas) or 'Não definido'


def _converter_link(match: re.Match[str]) -> str:
    href = match.group(1).strip()
    texto = _texto_para_markdown(match.group(2))
    return f'[{texto}]({href})' if texto != href else href


def _converter_lista_ordenada(match: re.Match[str]) -> str:
    return _converter_lista(match.group(1), ordenada=True)


def _converter_lista_nao_ordenada(match: re.Match[str]) -> str:
    return _converter_lista(match.group(1), ordenada=False)


def _converter_lista(conteudo: str, ordenada: bool) -> str:
    itens = re.findall(r'(?is)<li[^>]*>(.*?)</li>', conteudo)
    linhas = []
    for indice, item in enumerate(itens, start=1):
        prefixo = f'{indice}. ' if ordenada else '- '
        linhas.append(f'{prefixo}{_texto_para_markdown(item)}')
    return '\n'.join(linhas)


def _linha_metadado(rotulo: str, valor: object) -> str:
    return f'- **{rotulo}:** {_texto_para_markdown(valor)}'


class DemandaMarkdownExportService:
    @classmethod
    def gerar(
        cls,
        demanda: Demanda,
        incluir_consolidacao: bool = True,
        exibir_revisoes_de_especificacoes: bool = False,
        exibir_revisoes_sem_especificacao: bool = False,
        incluir_especificacao_tecnica: bool = False,
    ) -> str:
        partes = [
            f'# Demanda {demanda.pk}: {_texto_para_markdown(demanda.titulo)}',
            '',
            '## Identificação',
            _linha_metadado('ID', demanda.pk),
            _linha_metadado('Título', demanda.titulo),
            _linha_metadado('Tipo', demanda.tipo),
            _linha_metadado('Área de atuação', demanda.area),
            '',
        ]

        if incluir_consolidacao:
            partes.extend(cls._gerar_consolidacao(demanda, exibir_revisoes_de_especificacoes, exibir_revisoes_sem_especificacao))

        if incluir_especificacao_tecnica and demanda.especificacao_tecnica:
            partes.extend(['## Especificação Técnica', _texto_para_markdown(demanda.especificacao_tecnica), ''])

        return '\n'.join(partes).strip() + '\n'

    @classmethod
    def _gerar_consolidacao(
        cls,
        demanda: Demanda,
        exibir_revisoes_de_especificacoes: bool,
        exibir_revisoes_sem_especificacao: bool,
    ) -> list[str]:
        dod = demanda.get_dod()
        if not dod:
            return ['## Consolidação', 'Não definida.', '']

        partes = [
            '## Consolidação',
            _texto_para_markdown(dod.descricao),
            '',
        ]
        if dod.detalhamento:
            partes.extend(['### Detalhamento', _texto_para_markdown(dod.detalhamento), ''])

        partes.append('## Especificações da Consolidação')

        especificacoes = dod.especificacao_set.all()
        if not especificacoes:
            partes.extend(['Nenhuma especificação cadastrada.', ''])
        else:
            for especificacao in especificacoes:
                partes.extend(cls._gerar_especificacao(especificacao, exibir_revisoes_de_especificacoes))

        if exibir_revisoes_sem_especificacao:
            for revisao in dod.get_revisoes_sem_especificacao():
                partes.extend(
                    [
                        f'### {revisao.get_titulo()}',
                        'Esta especificação ainda não foi aprovada pelos demandantes.',
                        _texto_para_markdown(revisao.atividades),
                        '',
                    ]
                )

        return partes

    @classmethod
    def _gerar_especificacao(cls, especificacao: Especificacao, exibir_revisao: bool) -> list[str]:
        revisao = especificacao.revisaoespecificacao_set.first()
        partes = [f'### {especificacao}']

        if exibir_revisao and revisao:
            partes.extend(cls._gerar_revisao_especificacao(especificacao, revisao))
        else:
            partes.append(_texto_para_markdown(especificacao.atividades) if especificacao.atividades else 'Nenhuma atividade cadastrada.')

        partes.append('')
        return partes

    @classmethod
    def _gerar_revisao_especificacao(cls, especificacao: Especificacao, revisao: RevisaoEspecificacao) -> list[str]:
        partes = ['A revisão realizada nessa especificação ainda não foi aprovada pelos demandantes.']
        if revisao.nome != especificacao.nome:
            partes.append(f'Novo título: {revisao.nome}')

        if revisao.remocao_solicitada:
            partes.append('Será solicitada a remoção desta especificação da consolidação da demanda.')
        else:
            partes.append(_texto_para_markdown(revisao.atividades))
        return partes


# ─────────────────────────────────────────────────────────────────────────────
# EntregaService
# ─────────────────────────────────────────────────────────────────────────────


class EntregaService:
    """
    Ciclo de vida da entrega e o efeito dela na etapa da demanda.

    "Em homologação" significa que existe uma entrega aguardando o demandante: a etapa
    entra e sai desse estado só por aqui (docs/specs/2026-10-21-demandas-fluxo-entrega-homologacao.md).
    """

    # ── Criação ───────────────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def criar(
        cls,
        demanda: Demanda,
        titulo: str,
        usuario: User,
        prazo_feedback: date,
        descricao: str = '',
        notas: str = '',
        ambiente_homologacao=None,
        url_validacao: str = '',
        senha_homologacao: str = '',
        branch: str = '',
        id_merge_request: int | None = None,
        pipeline_id: int | None = None,
        versionamento: str = '',
        conclui_demanda: bool = False,
        especificacoes: Iterable[Especificacao] | None = None,
    ) -> Entrega:
        """
        Registra uma nova entrega e leva a demanda para "Em homologação".

        Regras aplicadas:
          - A demanda deve estar em desenvolvimento (ou em homologação sem entrega pendente, legado).
          - Só pode haver uma entrega ENVIADA por demanda por vez.
          - O prazo de resposta do demandante é a previsão da etapa "Em homologação".
        """
        cls._validar_situacao_para_entrega(demanda)
        cls._validar_entrega_pendente(demanda)

        entrega = Entrega(
            demanda=demanda,
            titulo=titulo,
            descricao=descricao,
            notas=notas,
            status=StatusEntrega.ENVIADA,
            ambiente_homologacao=ambiente_homologacao,
            url_validacao=url_validacao,
            senha_homologacao=senha_homologacao,
            prazo_feedback=prazo_feedback,
            branch=branch,
            id_merge_request=id_merge_request,
            pipeline_id=pipeline_id,
            versionamento=versionamento,
            conclui_demanda=conclui_demanda,
            cadastrada_por=usuario,
        )
        entrega.save()

        if especificacoes:
            entrega.especificacoes.set(especificacoes)

        HistoricoEntrega.objects.create(
            entrega=entrega,
            usuario=usuario,
            acao=HistoricoEntrega.ACAO_ENVIADA,
            observacao=f'Entrega registrada: {titulo}',
        )

        demanda.alterar_situacao(
            usuario=usuario,
            situacao=Situacao.ESTADO_EM_HOMOLOGACAO,
            comentario=f'Entrega registrada para homologação: <strong>{titulo}</strong>.',
            data_conclusao=date.today(),
            data_previsao=prazo_feedback,
            branch=branch,
        )

        transaction.on_commit(lambda: cls._notificar(Notificar.entrega_criada, entrega))

        return entrega

    # ── Validação pelo demandante ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def aprovar(cls, entrega: Entrega, usuario: User, observacao: str = '') -> Entrega:
        """
        Aprova a entrega.

        Se o escopo da demanda ficou coberto, a demanda vai para "Homologada" (que cria o
        merge request a partir da branch); senão, volta para "Em desenvolvimento".
        """
        demanda = entrega.demanda
        cls._validar_validador(entrega, usuario)
        if cls._tem_consolidacao_modificada(demanda):
            raise ValidationError('A entrega não pode ser aprovada enquanto houver alterações sem validação na consolidação.')

        entrega.encerrar(StatusEntrega.APROVADA, usuario, observacao)

        comentario = f'Entrega <strong>{entrega.titulo}</strong> aprovada.{" " + observacao if observacao else ""}'
        if cls.escopo_coberto(entrega):
            demanda.alterar_situacao(usuario=usuario, situacao=Situacao.ESTADO_HOMOLOGADA, comentario=comentario, data_conclusao=date.today())
        else:
            cls._voltar_para_desenvolvimento(demanda, usuario, comentario)

        transaction.on_commit(lambda: cls._notificar(Notificar.entrega_aprovada, entrega))

        return entrega

    @classmethod
    @transaction.atomic
    def reprovar(cls, entrega: Entrega, usuario: User, motivo: str) -> Entrega:
        """Reprova a entrega e devolve a demanda para "Em desenvolvimento"."""
        cls._validar_validador(entrega, usuario)

        entrega.motivo_rejeicao = motivo
        entrega.encerrar(StatusEntrega.REPROVADA, usuario, motivo)

        cls._voltar_para_desenvolvimento(entrega.demanda, usuario, f'Entrega <strong>{entrega.titulo}</strong> reprovada. Motivo: {motivo}.')

        transaction.on_commit(lambda: cls._notificar(Notificar.entrega_reprovada, entrega))

        return entrega

    # ── Cancelamento ──────────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def cancelar(cls, entrega: Entrega, usuario: User, observacao: str = '') -> Entrega:
        """
        Cancela uma entrega antes da resposta do demandante (ex.: nova versão vai substituí-la)
        e devolve a demanda para "Em desenvolvimento".
        """
        entrega.encerrar(StatusEntrega.CANCELADA, usuario, observacao)

        demanda = entrega.demanda
        comentario = f'Entrega <strong>{entrega.titulo}</strong> cancelada.{" " + observacao if observacao else ""}'
        if demanda.em_homologacao:
            cls._voltar_para_desenvolvimento(demanda, usuario, comentario)
        else:
            adicionar_comentario(usuario=usuario, mensagem=comentario, demanda=demanda)

        return entrega

    # ── Regras ────────────────────────────────────────────────────────────────

    @staticmethod
    def escopo_coberto(entrega: Entrega) -> bool:
        """
        Com especificações, o escopo está coberto quando todas estão em alguma entrega
        aprovada. Sem especificações, quem decide é a marca "Conclui a demanda?".
        """
        demanda = entrega.demanda
        if demanda.tem_especificacoes():
            return not demanda.get_especificacoes_sem_entrega_aprovada().exists()
        return entrega.conclui_demanda

    @staticmethod
    def _voltar_para_desenvolvimento(demanda: Demanda, usuario: User, comentario: str) -> None:
        """Devolve a demanda ao desenvolvimento reaproveitando a última previsão da etapa, se ela ainda não passou.

        Previsão vencida não é reaproveitada: a demanda voltaria já em atraso para os analistas, por uma data
        que ninguém informou agora. Ela volta sem previsão, e o comentário pede a nova.
        """
        previsao = demanda.get_ultima_previsao_da_etapa(Situacao.ESTADO_EM_DESENVOLVIMENTO)
        if previsao and previsao < date.today():
            previsao = None
            comentario = f'{comentario} A previsão anterior de desenvolvimento já passou: informe a nova previsão da etapa.'
        demanda.alterar_situacao(
            usuario=usuario,
            situacao=Situacao.ESTADO_EM_DESENVOLVIMENTO,
            comentario=comentario,
            data_conclusao=date.today(),
            data_previsao=previsao,
        )

    @staticmethod
    def _tem_consolidacao_modificada(demanda: Demanda) -> bool:
        dod = demanda.get_dod()
        return bool(dod and dod.revisaoespecificacao_set.exists())

    # ── Validações internas ───────────────────────────────────────────────────

    @staticmethod
    def _validar_validador(entrega: Entrega, usuario: User):
        if not entrega.demanda.pode_validar_entrega(usuario, entrega):
            raise PermissionDenied('Só os demandantes validam a entrega, e nunca quem a cadastrou.')

    @staticmethod
    def _validar_situacao_para_entrega(demanda: Demanda):
        """
        A demanda deve estar em desenvolvimento para receber uma nova entrega. "Em homologação"
        só é aceito sem entrega pendente: caso legado, anterior às entregas.
        """
        situacoes_permitidas = [
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
        ]
        if demanda.situacao not in situacoes_permitidas:
            raise ValidationError(
                f'Não é possível registrar uma entrega para uma demanda na situação "{demanda.situacao}". A demanda deve estar em desenvolvimento.'
            )

    @staticmethod
    def _validar_entrega_pendente(demanda: Demanda):
        """Impede duas entregas ENVIADA simultâneas para a mesma demanda."""
        if demanda.entrega_pendente:
            raise ValidationError('Já existe uma entrega pendente para esta demanda. Encerre a entrega atual antes de registrar uma nova.')

    # ── Integrações externas (on_commit) ──────────────────────────────────────

    @staticmethod
    def _notificar(notificacao, entrega: Entrega):
        try:
            notificacao(entrega)
        except Exception as e:
            capture_exception(e)


# ─────────────────────────────────────────────────────────────────────────────
# SubdemandaService
# ─────────────────────────────────────────────────────────────────────────────


class SubdemandaService:
    """
    Gerencia criação e priorização de sub-demandas.
    """

    # ── Criação ───────────────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def criar_subdemanda(
        cls,
        pai: Demanda,
        titulo: str,
        descricao: str,
        usuario: User,
        tipo: str | None = None,
        prioridade_interna: int | None = None,
    ) -> Demanda:
        """
        Cria uma sub-demanda vinculada a uma demanda pai.

        Herda: área, tags, demandantes, interessados do pai.
        Prioridade interna: se não informada, é colocada na última posição.
        """
        if prioridade_interna is None:
            prioridade_interna = pai.proxima_prioridade_interna

        subdemanda = Demanda(
            parent=pai,
            area=pai.area,
            tipo=tipo or pai.tipo,
            titulo=titulo,
            descricao=descricao,
            prioridade_interna=prioridade_interna,
            situacao=Situacao.ESTADO_ABERTO,
        )
        subdemanda.full_clean()
        subdemanda.save()

        # Herança de M2M do pai
        subdemanda.tags.set(pai.tags.all())
        subdemanda.demandantes.set(pai.demandantes.all())
        subdemanda.interessados.set(pai.interessados.all())

        adicionar_comentario(
            usuario=usuario,
            mensagem=f'Sub-demanda criada: <strong>{subdemanda}</strong>.',
            demanda=pai,
        )

        transaction.on_commit(lambda: cls._notificar_subdemanda_criada(subdemanda, usuario))

        return subdemanda

    # ── Reordenação de prioridade interna ─────────────────────────────────────

    @classmethod
    @transaction.atomic
    def reordenar(cls, pai: Demanda, subdemandas_em_nova_ordem: list[Demanda], usuario: User):
        """
        Redefine a prioridade interna das sub-demandas de um pai conforme
        a lista fornecida.

        Todas as demandas da lista devem pertencer ao mesmo pai.
        Demandas ausentes da lista não são alteradas.
        """
        ids_esperados = set(pai.subdemandas.values_list('pk', flat=True))
        ids_recebidos = {d.pk for d in subdemandas_em_nova_ordem}

        ids_desconhecidos = ids_recebidos - ids_esperados
        if ids_desconhecidos:
            raise ValidationError(f'As seguintes demandas não são sub-demandas de "{pai}": {ids_desconhecidos}.')

        for nova_prioridade, subdemanda in enumerate(subdemandas_em_nova_ordem, start=1):
            if subdemanda.prioridade_interna != nova_prioridade:
                subdemanda.prioridade_interna = nova_prioridade
                subdemanda.save(update_fields=['prioridade_interna'])

        adicionar_comentario(
            usuario=usuario,
            mensagem='Prioridade interna das sub-demandas reordenada.',
            demanda=pai,
        )

    # ── Conclusão do pai ──────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def concluir_pai(cls, pai: Demanda, usuario: User, comentario: str = '') -> Demanda:
        """
        Conclui a demanda pai após verificar que não há sub-demandas ativas.
        """
        if not pai.pode_concluir_pai:
            subdemandas_ativas = pai.get_subdemandas_ativas()
            nomes = ', '.join(str(s) for s in subdemandas_ativas[:5])
            raise ValidationError(f'Existem sub-demandas ainda ativas que impedem a conclusão: {nomes}.')

        pai.alterar_situacao(
            usuario=usuario,
            situacao=Situacao.ESTADO_CONCLUIDO,
            comentario=comentario or 'Demanda pai concluída após encerramento das sub-demandas.',
        )

        return pai

    # ── Notificações ──────────────────────────────────────────────────────────

    @staticmethod
    def _notificar_subdemanda_criada(subdemanda: Demanda, usuario: User):
        try:
            Notificar.subdemanda_criada(subdemanda, usuario)
        except Exception as e:
            capture_exception(e)
