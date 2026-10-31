from django.conf import settings
from django.urls import reverse_lazy
from django.utils.html import escape

from djtools.utils import send_notification


class Notificar:
    @staticmethod
    def solicitacao_homologacao_paint(solicitacao):
        url = reverse_lazy('auditoria:solicitacao_homologacao_paint', current_app='auditoria', kwargs={'solicitacao_id': solicitacao.id})
        titulo = f'[SUAP] Homologação do PAINT {solicitacao.paint}'
        texto = []
        texto.append('<h1>Solicitação de homologação</h1>')
        texto.append('<p>Prezado presidente do CONSUP,</p>')
        texto.append(
            f'<p>Estamos solicitando a homologação dos Plano Anual de Atividades de Auditoria Interna(PAINT) referente ao exercício {solicitacao.paint.ano}.</p>'
        )
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{url}">Solicitação de Homologação do {solicitacao.paint}</a></p>')
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitacao.solicitado], objeto=solicitacao)

    @staticmethod
    def emissao_ordem_servico(acao, ordem_servico):
        titulo = '[SUAP] Ordem de Serviço Emitida'
        texto = []
        texto.append('<h1>Ordem de Serviço Emitida</h1>')
        texto.append(f'<h2>{escape(acao)}</h2>')
        texto.append('<p>Você faz parte da Equipe de Trabalho desta Ordem de Serviço.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>PAINT:</dt><dd>{acao.paint}</dd>')
        texto.append(f'<dt>Ordem de Serviço:</dt><dd>{ordem_servico}</dd>')
        texto.append('</dl>')
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{acao.get_absolute_url()}">{acao.get_absolute_url()}</a></p>')
        vinculos = [*list(acao.get_equipe()), acao.revisor]
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=acao)

    def inicio_acao(acao):
        titulo = '[SUAP] Notificação de Ação Iniciada'
        texto = []
        texto.append(f'<h1>Ação {escape(acao)} Iniciada</h1>')
        texto.append(f'<h2>{escape(acao)} - {escape(acao.objeto)}</h2>')
        texto.append('<p>Você faz parte da Equipe de Trabalho desta ação de auditoria.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>PAINT:</dt><dd>{acao.paint}</dd>')
        texto.append('</dl>')
        texto.append(f'<p class="more-info">Para mais informações, acesse: <a href="{acao.get_absolute_url()}">{acao.get_absolute_url()}</a></p>')
        vinculos = [*list(acao.get_equipe()), acao.revisor]
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=acao)

    @staticmethod
    def emitir_acao(acao, ordem_servico=None):
        if ordem_servico:
            Notificar.emissao_ordem_servico(acao, ordem_servico)
        else:
            Notificar.inicio_acao(acao)

    @staticmethod
    def solicitacao_alteracao_cronograma_acao(solicitacao):
        url = reverse_lazy('auditoria:solicitacao_alteracao_cronograma_acao', current_app='auditoria', kwargs={'solicitacao_id': solicitacao.id})
        titulo = f'[SUAP] Solicitação de Altração do Cronogama da Ação {solicitacao.acao}'
        texto = []
        texto.append('<h1>Solicitação de Alteração de Cronograma de Ação</h1>')
        texto.append('<p>Prezado(a) chefe da auditoria,</p>')
        texto.append(
            f'<p>A equipe de trabalho da ação {escape(solicitacao.acao)} solicita alteração no cronograma estabelecido no PAINT para tal ação.</p>'
        )
        texto.append(
            f'<p>Para mais informações, acesse: <a href="{url}">Solicitação de Alteração de Cronograma da Ação {escape(solicitacao.acao)}</a></p>'
        )
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitacao.solicitado], objeto=solicitacao)

    @staticmethod
    def alteracao_cronograma_acao(solicitacao):
        url = reverse_lazy('auditoria:analisar_alteracao_cronograma_acao', current_app='auditoria', kwargs={'solicitacao_id': solicitacao.id})
        titulo = f'[SUAP] Solicitação de Altração do Cronogama da Ação {solicitacao.acao}'
        texto = []
        texto.append('<h1>Solicitação de Alteração de Cronograma de Ação</h1>')
        texto.append('<p>Prezado(a) auditor,</p>')
        texto.append('<p>A chefia respondeu a sua requisição.</p>')
        texto.append(
            f'<p>Para mais informações, acesse: <a href="{url}">Solicitação de Alteração de Cronograma da Ação {escape(solicitacao.acao)}</a></p>'
        )
        vinculos = list(solicitacao.acao.get_equipe())
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=solicitacao)

    @staticmethod
    def comunicacao_inicio_trabalhos(comunicacao):
        url = comunicacao.acao.get_absolute_url()
        titulo = '[SUAP] Comunicação de Início dos Trabalhos de Auditoria'
        texto = []
        texto.append('<h1>Comunicação de Início dos Trabalhos de Auditoria</h1>')
        texto.append(f'<h2>{escape(comunicacao.acao)}</h2>')
        texto.append('<p>Prezado gestor(a),</p>')
        texto.append(
            '<p>Estamos iniciando um trabalho de auditoria que será realizado no setor(es) sob sua responsabilidade. Assim, solicitamos à área sistêmica que providencie a respectiva manifestação de ciência da atividade no SUAP, bem como comunique aos servidores acerca do início da ação de auditagem, visto que poderão ser demandados a fornecer documentos e informações, além de prestar esclarecimentos sobre eventuais dúvidas e/ou fragilidades identificadas em seus processos de trabalho.</p>'
        )
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>PAINT:</dt><dd>{comunicacao.acao.paint}</dd>')
        texto.append('</dl>')
        texto.append('<p>--</p>')
        texto.append(f'<p>Para mais informações, acesse: <a href="{url}">{url}</a></p>')
        vinculos = comunicacao.get_vinculos_chefes()
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=comunicacao.acao)

    @staticmethod
    def comunicacao_inicio_monitoramento(monitoramento):
        url = reverse_lazy('auditoria:visualizar_monitoramento', kwargs={'monitoramento_id': monitoramento.pk})
        titulo = '[SUAP] Comunicação de Início dos Trabalhos de Auditoria'
        texto = []
        texto.append('<h1>Comunicação de Início dos Trabalhos de Auditoria</h1>')
        texto.append(f'<h2>{monitoramento}</h2>')
        texto.append('<p>Prezado gestor(a),</p>')
        texto.append(
            '<p>Estamos iniciando um trabalho de monitoramento da referida recomendação que será realizado no setor sob sua responsabilidade. Assim, solicitamos à área sistêmica que providencie a respectiva manifestação de ciência da atividade no SUAP, bem como comunique aos servidores acerca do início da ação de auditagem, visto que poderão ser demandados a fornecer documentos e informações, além de prestar esclarecimentos sobre eventuais dúvidas e/ou fragilidades identificadas em seus processos de trabalho.</p>'
        )
        texto.append('<p>--</p>')
        texto.append(f'<p>Para mais informações, acesse: <a href="{url}">{url}</a></p>')
        vinculos = monitoramento.get_vinculos_chefes()
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=monitoramento)

    @staticmethod
    def enviar_solicitacao_auditoria(comunicacao):
        titulo = '[SUAP] Solicitação de Auditoria'
        url = comunicacao.acao.get_absolute_url()
        texto = []
        texto.append('<h1>Solicitação de Auditoria</h1>')
        texto.append(f'<h2>{escape(comunicacao.acao)}</h2>')
        texto.append('<p>Prezado gestor(a),</p>')
        texto.append(
            '<p>Estamos iniciando um trabalho de auditoria que será realizado no setor(es) sob sua responsabilidade. Assim, solicitamos à área sistêmica que providencie a respectiva manifestação de ciência da atividade no SUAP, bem como comunique aos servidores acerca do início da ação de auditagem, visto que poderão ser demandados a fornecer documentos e informações, além de prestar esclarecimentos sobre eventuais dúvidas e/ou fragilidades identificadas em seus processos de trabalho.</p>'
        )
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>PAINT:</dt><dd>{comunicacao.acao.paint}</dd>')
        texto.append('</dl>')
        texto.append('<p>--</p>')
        texto.append(f'<p>Para mais informações, acesse: <a href="{url}">{url}</a></p>')
        vinculos = comunicacao.get_vinculos_chefes()
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=comunicacao.acao)

    @staticmethod
    def enviar_nota_auditoria(comunicacao):
        titulo = '[SUAP] Nota de Auditoria'
        texto = []
        url = comunicacao.acao.get_absolute_url()
        texto.append('<h1>Nota de Auditoria</h1>')
        texto.append(f'<h2>{escape(comunicacao.acao)}</h2>')
        texto.append('<p>Prezado gestor(a),</p>')
        texto.append(
            '<p>Estamos iniciando um trabalho de auditoria que será realizado no setor(es) sob sua responsabilidade. Assim, solicitamos à área sistêmica que providencie a respectiva manifestação de ciência da atividade no SUAP, bem como comunique aos servidores acerca do início da ação de auditagem, visto que poderão ser demandados a fornecer documentos e informações, além de prestar esclarecimentos sobre eventuais dúvidas e/ou fragilidades identificadas em seus processos de trabalho.</p>'
        )
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>PAINT:</dt><dd>{comunicacao.acao.paint}</dd>')
        texto.append('</dl>')
        texto.append('<p>--</p>')
        texto.append(f'<p>Para mais informações, acesse: <a href="{url}">{url}</a></p>')
        vinculos = comunicacao.get_vinculos_chefes()
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=comunicacao.acao)

    @staticmethod
    def enviar_notificacao_ciencia(ciencia, destinatarios):
        comunicacao = ciencia.comunicacao
        data_solicitacao = ciencia.data_solicitacao.strftime('%d/%m/%Y %H:%M')
        data_limite = ciencia.prazo_atual().strftime('%d/%m/%Y %H:%M')
        #
        titulo = '[SUAP] Nota de Auditoria'
        texto = []
        texto.append('<h1>Solicitação de Ciência</h1>')
        texto.append('<p>Prezado gestor(a),</p>')
        texto.append(
            f'<p>Estamos solicitando à área sistêmica que providencie a respectiva manifestação de ciência no SUAP devido a {escape(ciencia.motivo)}.</p>'
        )
        texto.append('<h3>Dados gerais:</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>PAINT:</dt><dd>{comunicacao.acao.paint}</dd>')
        texto.append(f'<dt>Ação: {escape(comunicacao.acao)}</dt>')
        texto.append(f'<dt>Data:</dt><dd>{data_solicitacao}</dd>')
        texto.append(f'<dt>Assunto:</dt><dd>{escape(comunicacao.objetivo)}</dd>')
        texto.append(f'<dt>Solicitante:</dt><dd>{ciencia.solicitante}</dd>')
        texto.append(f'<dt>Motivação:</dt><dd>{escape(ciencia.motivo)}</dd>')
        texto.append(f'<dt>Data Limite:</dt><dd>{data_limite}</dd>')
        texto.append('</dl>')
        texto.append('<p>--</p>')
        texto.append('<p>Para mais informações, acesse: <a href=# </a></p>')
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, destinatarios, objeto=comunicacao.acao)

    @staticmethod
    def notificar_manifestacao(manifestacao):
        url = manifestacao.get_absolute_url()
        solicitacao = manifestacao.solicitacao_providencia
        setor = solicitacao.setor
        monitoramento = manifestacao.content_object
        titulo = f'[SUAP] Manifestação da unidade {setor}'
        texto = []
        texto.append('<h1>Manifestação do Auditado </h1>')
        texto.append(f'<h2>{monitoramento}</h2>')
        texto.append('<p>Prezado auditor(a),</p>')
        texto.append(f'a unidade {setor} se manifestou em relação a solicitação de providências #{solicitacao.id}</h1>')
        texto.append('<p>--</p>')
        texto.append(f'<p>Para mais informações, acesse: <a href="{url}">{url}</a></p>')
        vinculos = [monitoramento.monitor]
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, objeto=manifestacao)
