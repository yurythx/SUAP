import datetime

from django.conf import settings

from comum.models import Configuracao, UsuarioGrupo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from edu.models import Diretoria


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        if datetime.datetime.today().weekday() > 4:
            return
        diretorias = Diretoria.objects.all()
        for diretoria in diretorias:
            membros_secretaria = UsuarioGrupo.objects.filter(group__name='Secretário Acadêmico', setores__id=diretoria.setor.pk)
            if membros_secretaria.exists():
                texto = (
                    '<h1>Ensino</h1>'
                    '<h2>Notificação de Pendências</h2>'
                    '<p>Caro(a) Secretário(a),</p>'
                    f'<p>Existem algumas pendências relacionadas à diretoria {diretoria.setor}.</p>'
                    '<br /><dl>'
                )
                enviar_email = False
                ano = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or datetime.date.today().year)
                periodo = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)
                pendencias = diretoria.get_pendencias(ano, periodo)
                if pendencias:
                    enviar_email = enviar_email or True
                    texto += f'<dt>No período letivo {ano}.{periodo}:</dt>'
                    secretarios = []
                    for secretario in membros_secretaria:
                        secretarios.append(secretario.user.get_vinculo())
                    for pendencia in pendencias:
                        if 'url' not in pendencia:
                            pendencia['url'] = ''
                        texto += '<dd>* {}: <a href="{}{}">{}</a></dd>'.format(
                            pendencia['nome'], settings.SITE_URL, pendencia['url'], pendencia['quantidade']
                        )
                texto += '</dl>'
                if enviar_email:
                    titulo = f'[SUAP] Notificação de Pendências: {diretoria.setor}.'
                    try:
                        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, secretarios, categoria='Ensino: Notificação de Pendências')
                    except Exception:
                        continue
