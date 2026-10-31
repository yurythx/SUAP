from datetime import datetime, timedelta

from comum.models import UsuarioGrupo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification
from edu.models import RegistroEducacenso
from suap import settings


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = RegistroEducacenso.objects.filter(privado=False, data_limite=datetime.today() - timedelta(days=1))

        # Fechar e Notificar grupos "Administrador Acadêmico" e "Operador de Censo" quando, após fechamento do questionário, se houver campus com questionário pendente.
        for registro in qs:
            registro.fechar()
            campi_pendentes = registro.get_campi_questionario_pendente()
            if campi_pendentes:
                qs_usuario_grupo = (
                    UsuarioGrupo.objects.filter(group__name__in=['Administrador Acadêmico', 'Operador de Censo']).select_related('user').distinct()
                )
                usuarios_para_notificar = [ug.user.get_vinculo() for ug in qs_usuario_grupo]
                titulo = '[SUAP] Existem campi com questionário Educacenso ainda pendente de preenchimento'
                texto = (
                    f'<h2>Questionários Educacenso foram fechados na data limite {registro.data_limite.strftime("%d/%m/%Y")}</h2>'
                    f'<p> O{"s" if len(campi_pendentes) > 1 else ""} camp{"i" if len(campi_pendentes) > 1 else "us"} {", ".join(campi_pendentes)} está{"o" if len(campi_pendentes) == 1 else "m"} com questionário pendente.</p>'
                    f'<p>Acesse {settings.SITE_URL}/edu/registroeducacenso/{registro.id}/ </p>'
                )

                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, usuarios_para_notificar, fail_silently=True)
