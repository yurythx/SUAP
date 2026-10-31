import datetime

from django.conf import settings

from djtools.utils import render_to_string, send_notification


class Notificar:
    @staticmethod
    def comentar_erro(comentario):
        titulo = '[SUAP] Erros: Nota Interna' if comentario.tipo == 'nota_interna' else '[SUAP] Erros: Novo Comentário'
        notificados = comentario.erro.get_notificados(comentario.vinculo, so_atendentes=True)
        texto = render_to_string('notificacoes/comentar_erro.html', {'comentario': comentario})
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, notificados, objeto=comentario.erro)

    @staticmethod
    def alterar_situacao_erro(erro, responsavel, motivo):
        titulo = '[SUAP] Erros: Nova Situação'
        texto = render_to_string(
            'notificacoes/alterar_situacao_erro.html',
            {'erro': erro, 'motivo': motivo, 'responsavel': responsavel, 'data_hora': datetime.datetime.now()},
        )
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, erro.get_notificados(responsavel), objeto=erro)

    @staticmethod
    def adicionar_anexo(anexo_erro):
        titulo = '[SUAP] Erros: Novo Anexo'
        texto = render_to_string('notificacoes/adicionar_anexo.html', {'anexo_erro': anexo_erro})
        send_notification(
            titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, anexo_erro.erro.get_notificados(anexo_erro.anexado_por), objeto=anexo_erro.erro
        )

    @staticmethod
    def atribuir_erro(erro, atribuinte):
        titulo = '[SUAP] Erros: Nova Atribuição'
        texto = render_to_string('notificacoes/atribuir_erro.html', {'erro': erro, 'atribuinte': atribuinte})
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, erro.get_notificados(atribuinte), objeto=erro)
