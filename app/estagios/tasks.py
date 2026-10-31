import datetime

from django.conf import settings

from comum.models import Configuracao
from djtools.assincrono import task
from djtools.utils import send_notification
from estagios.models import RelatorioModuloAprendizagem, RelatorioSemestralEstagio


@task('Enviando Emails de Oferta de Estágio')
def enviar_emails(obj, task=None):
    if obj.data_fim >= datetime.date.today():
        contador = 0
        for curso in obj.cursos.all():
            contador += curso.aluno_set.count()
        task.start_progress(contador)
        for curso in obj.cursos.all():
            for aluno in task.iterate(curso.aluno_set.all()):
                if obj in aluno.get_ofertas_pratica_profissional():
                    url_servidor = Configuracao.get_valor_por_chave('protocolo', 'url_consulta_publica')
                    titulo = '[SUAP] Oferta de Estágio ou Jovem Aprendiz para seu Curso Cadastrada'
                    assunto = (
                        '<h1>Oferta de Estágio ou Jovem Aprendiz para seu Curso Cadastrada</h1>'
                        f'<p>Uma oferta de estágio ou jovem aprendiz para o curso {curso} foi cadastrada no SUAP. Para visualizá-la acesse o sistema ou acesse: '
                        f'<a href="{url_servidor}/estagios/oferta_pratica_profissional/{obj.pk}/">Ofertas de Estágios ou Jovem Aprendiz</a>.</p>'
                    )

                    send_notification(titulo, assunto, settings.DEFAULT_FROM_EMAIL, [aluno.get_vinculo()])
    task.finalize('Emails enviados com sucesso.', obj.get_absolute_url())


@task('Notificar Pendência de Assinatura em Relatório de Atividades de Estágio')
def notificar_pendencia_assinatura_relatorio_semestral_estagio(relatorio: RelatorioSemestralEstagio, task=None):
    task.start_progress()

    relatorio.notificar_pendencia_de_assinatura_estagiario()
    task.update_progress(33)
    relatorio.notificar_pendencia_de_assinatura_orientador()
    task.update_progress(66)
    relatorio.notificar_pendencia_de_assinatura_supervisor()

    task.finalize('Pendências notificadas com sucesso.', '..')


@task('Notificar Pendência de Assinatura em Relatório de Atividades da Aprendizagem')
def notificar_pendencia_assinatura_relatorio_modulo_aprendizagem(relatorio: RelatorioModuloAprendizagem, task=None):
    task.start_progress()

    relatorio.notificar_pendencia_de_assinatura_aprendiz()
    task.update_progress(33)
    relatorio.notificar_pendencia_de_assinatura_orientador()
    task.update_progress(66)
    relatorio.notificar_pendencia_de_assinatura_monitor()

    task.finalize('Pendências notificadas com sucesso.', '..')
