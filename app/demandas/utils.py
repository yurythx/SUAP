import datetime

import gitlab
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from requests.exceptions import ConnectTimeout
from sentry_sdk import capture_exception

from comum.models import Comentario, Configuracao
from djtools.utils import send_notification, get_apps_suap


def adicionar_comentario(usuario, mensagem, demanda):
    demanda_content = ContentType.objects.get(app_label='demandas', model='demanda')
    comentario = Comentario()
    comentario.cadastrado_por = usuario
    comentario.texto = mensagem
    comentario.content_type = demanda_content
    comentario.content_object = demanda
    comentario.object_id = demanda.id
    comentario.save()


def get_demandantes(demandantes):
    lista = []
    for demandante in demandantes:
        lista.append(demandante.get_profile().nome_usual)
    return ', '.join(lista)


def dados_gerais(demanda):
    texto = '<div class="dados-gerais">'
    texto += '<h3>Dados gerais</h3>'
    texto += '<dl>'
    texto += f'<dt>Descrição:</dt><dd>{demanda.descricao}</dd>'
    texto += f'<dt>Etapa atual:</dt><dd>{demanda.situacao}</dd>'
    texto += f'<dt>Área de atuação:</dt><dd>{demanda.area}</dd>'
    if demanda.prioridade:
        texto += f'<dt>Prioridade para desenvolvimento:</dt><dd>{demanda.prioridade}</dd>'
    texto += f'<dt>Demandantes:</dt><dd>{get_demandantes(demanda.demandantes.all())}</dd>'
    texto += '<dt>Criada em:</dt><dd>{}</dd>'.format(demanda.aberto_em.strftime('%d/%m/%Y %H:%M'))
    texto += '</dl>'
    texto += '<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(demanda.get_visualizar_demanda_url())
    return texto


class Notificar:
    @staticmethod
    def demanda_aberta(demanda):
        titulo = '[SUAP] Nova Demanda'
        texto = []
        texto.append('<h1>Nova Demanda</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append(f'<p>{demanda.descricao}</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Demandantes:</dt><dd>{get_demandantes(demanda.demandantes.all())}</dd>')
        texto.append(f'<dt>Tipo:</dt><dd>{demanda.tipo}</dd>')
        if demanda.tags.all():
            texto.append(f'<dt>Módulos:</dt><dd>{", ".join([tag.nome for tag in demanda.tags.all()])}</dd>')
        texto.append(f'<dt>Criada em:</dt><dd>{demanda.aberto_em.strftime("%d/%m/%Y %H:%M")}</dd>')
        if demanda.privada:
            texto.append(f'<dt>Privada:</dt><dd>{demanda.privada}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(demanda.get_visualizar_demanda_url()))
        vinculos = set().union(demanda.get_vinculos_recebedores_novas_demandas(), demanda.get_vinculos_interessados())
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=demanda)

    @staticmethod
    def _texto_entrega(entrega, titulo_h1):
        url = f'{settings.SITE_URL}{entrega.get_absolute_url()}'
        texto = [
            f'<h1>{titulo_h1}</h1>',
            f'<h2>{entrega.demanda}</h2>',
            f'<h3>{entrega.titulo}</h3>',
            '<dl>',
            f'<dt>Status:</dt><dd>{entrega.get_status_display()}</dd>',
        ]
        if entrega.descricao:
            texto.append(f'<dt>Descrição:</dt><dd>{entrega.descricao}</dd>')
        if entrega.prazo_feedback:
            texto.append('<dt>Prazo para feedback:</dt><dd>{}</dd>'.format(entrega.prazo_feedback.strftime('%d/%m/%Y')))
        if entrega.motivo_rejeicao:
            texto.append(f'<dt>Motivo da reprovação:</dt><dd>{entrega.motivo_rejeicao}</dd>')
        texto.append('</dl>')
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{url!s}">{url!s}</a></p>')
        return ''.join(texto)

    @staticmethod
    def _notificar_entrega(entrega, titulo, titulo_h1, vinculos, categoria):
        if not vinculos:
            return
        texto = Notificar._texto_entrega(entrega, titulo_h1)
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=entrega.demanda)

    @staticmethod
    def entrega_criada(entrega):
        """
        Notifica demandantes e interessados que uma nova entrega foi registrada.
        """
        demanda = entrega.demanda
        vinculos = set().union(demanda.get_vinculos_demandantes(), demanda.get_vinculos_interessados())
        Notificar._notificar_entrega(
            entrega,
            f'[SUAP] Demanda #{demanda.pk}: Nova Entrega para Homologação',
            'Nova Entrega para Homologação',
            vinculos,
            'Demanda: Nova Entrega',
        )

    @staticmethod
    def entrega_aprovada(entrega):
        """
        Notifica demandantes e interessados que a entrega foi aprovada.
        """
        demanda = entrega.demanda
        vinculos = set().union(demanda.get_vinculos_demandantes(), demanda.get_vinculos_interessados())
        Notificar._notificar_entrega(
            entrega, f'[SUAP] Demanda #{demanda.pk}: Entrega Aprovada', 'Entrega Aprovada', vinculos, 'Demanda: Entrega Aprovada'
        )

    @staticmethod
    def entrega_reprovada(entrega):
        """
        Notifica demandantes e interessados que a entrega foi reprovada.
        """
        demanda = entrega.demanda
        vinculos = set().union(demanda.get_vinculos_demandantes(), demanda.get_vinculos_interessados())
        Notificar._notificar_entrega(
            entrega, f'[SUAP] Demanda #{demanda.pk}: Entrega Reprovada', 'Entrega Reprovada', vinculos, 'Demanda: Entrega Reprovada'
        )

    @staticmethod
    def subdemanda_criada(subdemanda, usuario):
        """
        Notifica demandantes do pai sobre criação de sub-demanda.
        """
        pai = subdemanda.parent
        if not pai:
            return
        titulo = f'[SUAP] Demanda #{pai.pk}: Nova Sub-demanda'
        texto = [
            '<h1>Nova Sub-demanda</h1>',
            f'<h2>{pai}</h2>',
            f'<p>Uma nova sub-demanda foi criada: <strong>{subdemanda}</strong>.</p>',
            dados_gerais(subdemanda),
        ]
        vinculos = set(pai.get_vinculos_demandantes())
        if usuario:
            vinculos.discard(usuario.get_vinculo())
        if vinculos:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Demanda: Nova Sub-demanda', objeto=pai)

    @staticmethod
    def alteracao_demanda(demanda):
        titulo = f'[SUAP] Atualização de Demanda #{demanda.pk}'
        texto = []
        texto.append('<h1>Atualização da Descrição da Demanda</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append('<h3>Novo Conteúdo</h3>')
        texto.append(f'<p>{demanda.descricao}</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Demandantes:</dt><dd>{get_demandantes(demanda.demandantes.all())}</dd>')
        if demanda.prioridade:
            texto.append(f'<dt>Prioridade para Desenvolvimento:</dt><dd>{demanda.prioridade}</dd>')
        texto.append('<dt>Criada em:</dt><dd>{}</dd>'.format(demanda.aberto_em.strftime('%d/%m/%Y %H:%M')))
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(demanda.get_visualizar_demanda_url()))
        responsaveis = demanda.get_vinculos_analistas() or demanda.get_vinculos_recebedores_novas_demandas()
        vinculos = set().union(responsaveis, demanda.get_vinculos_interessados())
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Atualização de Demanda', objeto=demanda)

    @staticmethod
    def situacao_alterada(demanda, texto_comentario=None, estado_em_analise=False, eh_observador=False):
        ultimo_historico_situacao = demanda.get_ultimo_historico_situacao()
        titulo = f'[SUAP] Demanda #{demanda.pk}: Alteração de Etapa'
        texto = []
        texto.append('<h1>Alteração de Etapa da Demanda</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        msg_atualizador = f'por {ultimo_historico_situacao.usuario}' if ultimo_historico_situacao.usuario else 'pelo sistema'
        texto.append(f'<p>Etapa alterada para <strong>{ultimo_historico_situacao.situacao}</strong>; atualização realizada {msg_atualizador}.</p>')
        if not eh_observador:
            if estado_em_analise:
                texto.append('<p>A consolidação da demanda foi liberada para avaliação.</p>')
                texto.append("<p>Você deve acessar a demanda, acessar a aba 'Consolidação' e revisar o conteúdo.</p>")
                texto.append(
                    '<p>Caso você seja o Demandante, você deve, após revisão do conteúdo, selecionar uma das opções: Aprovar ou Reprovar.</p>'
                )
            if texto_comentario or ultimo_historico_situacao.data_previsao or ultimo_historico_situacao.data_conclusao:
                texto.append('<h3>Dados da atualização</h3>')
                texto.append('<dl>')
                if texto_comentario:
                    texto.append(f'<dt>Comentário:</dt><dd>{texto_comentario}</dd>')
                if ultimo_historico_situacao.data_previsao:
                    texto.append(
                        '<dt>Data de previsão para conclusão desta etapa:</dt><dd>{}</dd>'.format(
                            ultimo_historico_situacao.data_previsao.strftime('%d/%m/%Y')
                        )
                    )
                if ultimo_historico_situacao.data_conclusao:
                    texto.append(
                        '<dt>Data de conclusão da etapa anterior:</dt><dd>{}</dd>'.format(
                            ultimo_historico_situacao.data_conclusao.strftime('%d/%m/%Y')
                        )
                    )
                texto.append('</dl>')
        texto.append(dados_gerais(demanda))
        if demanda.get_vinculos_analistas() or demanda.get_vinculos_desenvolvedores():
            responsaveis = set().union(demanda.get_vinculos_analistas(), demanda.get_vinculos_desenvolvedores())
        else:
            responsaveis = demanda.get_vinculos_recebedores_novas_demandas()
        vinculos = set().union(responsaveis, demanda.get_vinculos_interessados(), demanda.get_vinculos_observadores())
        if ultimo_historico_situacao.usuario:
            vinculos.discard(ultimo_historico_situacao.usuario.get_vinculo())
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Demanda: Alteração de Etapa', objeto=demanda)

    @staticmethod
    def nota_interna_criada(nota_interna):
        demanda = nota_interna.demanda
        titulo = f'[SUAP] Demanda #{demanda.pk}: Nova Nota Interna'
        texto = []
        texto.append('<h1>Nova Nota Interna</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append('<p>Uma nova nota interna foi adicionada à esta demanda.</p>')
        texto.append(dados_gerais(demanda))
        vinculos = set().union(demanda.get_vinculos_analistas(), demanda.get_vinculos_desenvolvedores())
        vinculos = [vinculo for vinculo in vinculos if vinculo != nota_interna.usuario.get_vinculo()]
        if vinculos:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Demanda: Nova Nota Interna', objeto=demanda)

    @staticmethod
    def novo_comentario(comentario):
        demanda = comentario.content_object
        usuario = comentario.cadastrado_por.get_profile().nome_usual
        texto = []
        if comentario.texto:
            titulo = f'[SUAP] Demanda #{demanda.pk}: Novo comentário'
            texto.append('<h1>Novo Comentário</h1>')
        else:
            titulo = f'[SUAP] Demanda #{demanda.pk}: Novo anexo'
            texto.append('<h1>Novo Anexo</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        if comentario.texto:
            texto.append('<dl>')
            texto.append(f'<dt>Comentário por {usuario}:</dt><dd class="featured-info">{comentario.texto}</dd>')
            if comentario.resposta:
                texto.append(
                    f'<dt>Em resposta ao comentário de {comentario.resposta.cadastrado_por.get_profile().nome_usual}:</dt><dd class="featured-info">{comentario.resposta.texto}</dd>'
                )
        else:
            texto.append('<dl>')
            texto.append(f'<dt>Arquivo anexado por {usuario}:</dt><dd>Para visualizar o anexo, acesse o link da demanda e clique em Anexos.</dd>')
        texto.append('</dl>')
        texto.append(dados_gerais(demanda))
        if demanda.get_vinculos_analistas() or demanda.get_vinculos_desenvolvedores():
            responsaveis = set().union(demanda.get_vinculos_analistas(), demanda.get_vinculos_desenvolvedores())
        else:
            responsaveis = demanda.get_vinculos_recebedores_novas_demandas()
        vinculos = set().union(responsaveis, demanda.get_vinculos_interessados())
        if comentario.cadastrado_por:
            vinculos.discard(comentario.cadastrado_por.get_vinculo())
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Demanda: Novo Comentário', objeto=demanda)

    @staticmethod
    def usuarios_vinculados_a_demanda(demanda, novos_usuarios, vinculado_por, papel):
        titulo = f'[SUAP] Vinculação à Demanda #{demanda.pk}'
        texto = []
        texto.append('<h1>Vinculação à Demanda</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append(f'<p>Você foi vinculado a esta demanda como <strong>{papel}</strong>.</p>')
        texto.append(dados_gerais(demanda))
        usuarios_vinculos = [usuario.get_vinculo() for usuario in novos_usuarios if usuario != vinculado_por]
        if usuarios_vinculos:
            send_notification(
                titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, usuarios_vinculos, categoria='Vinculação à Demanda', objeto=demanda
            )

    @staticmethod
    def usuarios_desvinculados_a_demanda(demanda, usuarios_removidos, desvinculado_por, papel):
        titulo = f'[SUAP] Desvinculação da Demanda #{demanda.pk}'
        texto = []
        texto.append('<h1>Desvinculação da Demanda</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append(f'<p>Você foi desvinculado desta demanda como <strong>{papel}</strong>.</p>')
        texto.append(dados_gerais(demanda))
        usuarios_vinculos = [usuario.get_vinculo() for usuario in usuarios_removidos if usuario != desvinculado_por]
        if usuarios_vinculos:
            send_notification(
                titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, usuarios_vinculos, categoria='Desvinculação da demanda', objeto=demanda
            )

    @staticmethod
    def desenvolvedores_vinculados_a_demanda(demanda, novos_desenvolvedores, vinculado_por):
        Notificar.usuarios_vinculados_a_demanda(demanda, novos_desenvolvedores, vinculado_por, 'Desenvolvedor')

    @staticmethod
    def analistas_vinculados_a_demanda(demanda, novos_analistas, vinculado_por):
        Notificar.usuarios_vinculados_a_demanda(demanda, novos_analistas, vinculado_por, 'Analista')

    @staticmethod
    def demandantes_vinculados_a_demanda(demanda, novos_demandantes, vinculado_por):
        Notificar.usuarios_vinculados_a_demanda(demanda, novos_demandantes, vinculado_por, 'Demandante')

    @staticmethod
    def solicitacao_observador(demanda):
        titulo = f'[SUAP] Solicitação de Acompanhamento da Demanda #{demanda.pk}'
        categoria = 'Solicitação de Acompanhamento da Demanda'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append('<p>Um usuário solicitou acompanhamento desta demanda como <strong>Observador</strong>.</p>')
        texto.append(dados_gerais(demanda))
        send_notification(
            titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, demanda.get_vinculos_demandantes(), categoria=categoria, objeto=demanda
        )

    @staticmethod
    def solicitacao_aprovacao_modificacoes_especificacao(demanda):
        titulo = f'[SUAP] Solicitação de aprovação de modificações na demanda #{demanda.pk}'
        categoria = 'Solicitação de aprovação de modificações na demanda'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append('<p>Foram realizadas alterações na consolidação da demanda que requerem sua validação.</p>')
        texto.append(dados_gerais(demanda))
        send_notification(
            titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, demanda.get_vinculos_demandantes(), categoria=categoria, objeto=demanda
        )

    @staticmethod
    def adicao_como_observador(demanda, user):
        titulo = f'[SUAP] Vinculação à Demanda #{demanda.pk}'
        categoria = 'Vinculação à Demanda'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append('<p>Você foi vinculado a esta demanda como <strong>Observador</strong>.</p>')
        texto.append(dados_gerais(demanda))

        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [user.get_vinculo()], categoria=categoria, objeto=demanda)

    @staticmethod
    def remocao_como_observador_pendente(demanda, user):
        titulo = f'[SUAP] Solicitação de Acompanhamento da Demanda #{demanda.pk}'
        categoria = 'Solicitação de Acompanhamento da Demanda'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(f'<h2>{demanda}</h2>')
        texto.append('<p>Sua solicitação de acompanhamento a esta demanda como Observador foi <strong>negada</strong> pelos demandantes.</p>')
        texto.append(dados_gerais(demanda))

        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [user.get_vinculo()], categoria=categoria, objeto=demanda)

    @staticmethod
    def nova_sugestao_melhoria(sugestao_melhoria):
        # notifica os demandantes da área de atuação da sugestão
        vinculos_users_to = [_.get_vinculo() for _ in sugestao_melhoria.demandantes]

        titulo = '[SUAP] Nova Sugestão de Melhoria na sua Área de Atuação'
        url = f'{settings.SITE_URL}{sugestao_melhoria.get_absolute_url()}'

        texto = [
            '<h1>Sugestão de Melhoria</h1>',
            f'<h2>{sugestao_melhoria.titulo}</h2>',
            '<dl>',
            f'<dt>Descrição:</dt><dd>{sugestao_melhoria.descricao}</dd>',
            f'<dt>Requisitante:</dt><dd>{sugestao_melhoria.requisitante.get_vinculo()}</dd>',
            '</dl>',
            f'<p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>',
        ]

        send_notification(
            titulo,
            ''.join(texto),
            settings.DEFAULT_FROM_EMAIL,
            vinculos_users_to,
            categoria='Sugestão de Melhoria: Nova Sugestão',
            objeto=sugestao_melhoria,
        )

    @staticmethod
    def nova_situacao_em_sugestao_melhoria(sugestao_melhoria, user_editor):
        # notifica o requisitante, os interessados e o responsável da sugestão, exceto quem fez a edição
        vinculos_users_to = set().union(
            [sugestao_melhoria.requisitante.get_vinculo()],
            [_.get_vinculo() for _ in sugestao_melhoria.interessados.all()],
            [_.get_vinculo() for _ in [sugestao_melhoria.responsavel] if _],
        )
        vinculos_users_to.discard(user_editor.get_vinculo())

        titulo = f'[SUAP] Sugestão de Melhoria #{sugestao_melhoria.pk}: Nova Situação'
        url = f'{settings.SITE_URL}{sugestao_melhoria.get_absolute_url()}'

        texto = [
            '<h1>Sugestão de Melhoria</h1>',
            f'<h2>{sugestao_melhoria.titulo}</h2>',
            '<dl>',
            f'<dt>Situação alterada para:</dt><dd>{sugestao_melhoria.get_situacao_display()}</dd>',
            f'<dt>Alteração feita por:</dt><dd>{user_editor.get_vinculo()}</dd>',
            '</dl>',
            f'<p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>',
        ]

        send_notification(
            titulo,
            ''.join(texto),
            settings.DEFAULT_FROM_EMAIL,
            vinculos_users_to,
            categoria='Sugestão de Melhoria: Nova Situação',
            objeto=sugestao_melhoria,
        )

    @staticmethod
    def novo_comentario_em_sugestao_melhoria(sugestao_melhoria, comentario):
        if not comentario.content_object == sugestao_melhoria:
            raise Exception('O comentário não pode ser notificado nesta sugestão de melhoria.')

        # notifica o requisitante, os interessados e o responsável da sugestão, exceto quem fez o comentário
        vinculos_users_to = set().union(
            [sugestao_melhoria.requisitante.get_vinculo()],
            [_.get_vinculo() for _ in sugestao_melhoria.interessados.all()],
            [_.get_vinculo() for _ in [sugestao_melhoria.responsavel] if _],
        )
        vinculos_users_to.discard(comentario.cadastrado_por.get_vinculo())

        titulo = f'[SUAP] Sugestão de Melhoria #{sugestao_melhoria.pk}: Novo Comentário'
        url = f'{settings.SITE_URL}{sugestao_melhoria.get_absolute_url()}'

        texto = [
            '<h1>Sugestão de Melhoria</h1>',
            f'<h2>{sugestao_melhoria.titulo}</h2>',
            '<dl>',
            f'<dt>Comentário:</dt><dd>{comentario.texto}</dd>',
            f'<dt>Comentário feito por:</dt><dd>{comentario.cadastrado_por.get_profile().nome_usual}</dd>',
        ]

        if comentario.resposta:
            texto.append(
                f'<dt>Em resposta ao comentário de {comentario.resposta.cadastrado_por.get_profile().nome_usual}:</dt><dd>{comentario.resposta.texto}</dd>'
            )

        texto.append('</dl>')
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{url!s}">{url!s}</a></p>')

        send_notification(
            titulo,
            ''.join(texto),
            settings.DEFAULT_FROM_EMAIL,
            vinculos_users_to,
            categoria='Sugestão de Melhoria: Novo Comentário',
            objeto=sugestao_melhoria,
        )

    @staticmethod
    def ambiente_homologacao_expira_em_1_dia(ambiente):
        titulo = f'[SUAP] Ambiente de Homologação #{ambiente.branch}: Aviso de Expiração e Remoção'

        categoria = 'Ambientes de Homologação - SUAPDevs'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(f'<h2>#{ambiente.pk} {ambiente.branch}</h2>')
        texto.append(
            f'<p>Seu ambiente referente a branch {ambiente.branch} irá expirar em {ambiente.data_expiracao.strftime("%d/%m/%Y")} e será removido definitivamente.</p>'
        )
        texto.append('<p>Atualize a data de expiração, se necessário, para manter o ambiente ativo.</p>')
        if ambiente.demanda_set.exists():
            texto.append('<h2>Este ambiente afeta as seguintes demandas: </h2>')
            for demanda in ambiente.demanda_set.all():
                texto.append(f'<h3><a href="{demanda.get_visualizar_demanda_url()}">{demanda}</a> ({demanda.situacao})</h3>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Branch:</dt><dd>{ambiente.branch}</dd>')
        texto.append(f'<dt>Url gitlab:</dt><dd>{ambiente.url_gitlab}</dd>')
        texto.append('<dt>Criado em:</dt><dd>{}</dd>'.format(ambiente.data_criacao.strftime('%d/%m/%Y')))
        texto.append('</dl>')
        url = f'{settings.SITE_URL}{ambiente.get_absolute_url()}'
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{url!s}">{url!s}</a></p>')

        send_notification(
            titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [ambiente.criador.usuario.get_vinculo()], categoria=categoria, objeto=ambiente
        )


def sincronizar_demandas_atualizacoes(demanda):
    gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url')
    gitlab_token = Configuracao.get_valor_por_chave('demandas', 'gitlab_token')
    gitlab_suap_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')
    if not all([gitlab_url, gitlab_token, gitlab_suap_id]):
        return 'Gitlab não está configurado no SUAP.'
    try:
        from demandas.models import AnalistaDesenvolvedor, Situacao

        git = gitlab.Gitlab(gitlab_url, private_token=gitlab_token, timeout=60)
        merge_request = git.projects.get(gitlab_suap_id).mergerequests.get(demanda.id_merge_request)
        if merge_request.state == 'merged' and merge_request.merged_by:
            analista_mr = AnalistaDesenvolvedor.objects.filter(username_gitlab=merge_request.merged_by['username']).first()
            hoje = datetime.date.today()
            demanda.alterar_situacao(analista_mr.usuario, Situacao.ESTADO_CONCLUIDO, data_conclusao=hoje)
    except ConnectTimeout:
        return 'Gitlab indisponível.'
    except Exception as e:
        capture_exception(e)


def get_auto_apps_relacionadas(tag_nome: str) -> str:
    """Tenta automaticamente relacionar uma Tag às apps do SUAP.
    O parâmetro `tag_nome` será usado como o nome da app definido
    no atributo `verbose_name` da configuração da app (em apps.py).
    OBS: Não há nenhuma segurança em considerar `tag_nome` como sendo
    uma área do SUAP definida no atributo `area` também em apps.py.
    """
    return ','.join([app.label for app in get_apps_suap() if getattr(app, 'verbose_name', None) == tag_nome])
