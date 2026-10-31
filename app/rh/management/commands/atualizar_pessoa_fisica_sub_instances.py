from django.db.models import Exists, OuterRef, Q

from comum.models import User
from djtools.management.commands import BaseCommandPlus
from rh.models import PessoaFisica, Servidor


def flags_do_vinculo() -> dict[str, Q]:
    """Condição de cada flag do ``User`` pelo vínculo do login, como no ``user_post_save``.

    A pessoa física é compartilhada por todos os vínculos da pessoa (servidor, aluno, prestador): olhar
    o ``servidor_set``/``aluno_set`` dela marcaria o login de aluno como servidor e vice-versa.
    """
    servidor = Q(vinculo__tipo_relacionamento__model='servidor')
    do_login = Servidor.objects.filter(pk=OuterRef('vinculo__id_relacionamento'))
    return {
        'eh_servidor': servidor,
        'eh_docente': servidor & Q(Exists(do_login.filter(eh_docente=True))),
        'eh_tecnico_administrativo': servidor & Q(Exists(do_login.filter(eh_tecnico_administrativo=True))),
        'eh_prestador': Q(vinculo__tipo_relacionamento__model='prestadorservico'),
        'eh_aluno': Q(vinculo__tipo_relacionamento__model='aluno'),
    }


class Command(BaseCommandPlus):
    help = 'Verifica se a pessoa fisica tem aluno, servidor ou prestador'

    def handle(self, *args, **options):
        self.stdout.write('Atualizando Users')
        for flag, condicao in flags_do_vinculo().items():
            User.objects.filter(condicao, **{flag: False}).update(**{flag: True})
            User.objects.exclude(condicao).filter(**{flag: True}).update(**{flag: False})

        self.stdout.write('Atualizando Pessoas')
        for pessoa in PessoaFisica.objects.filter(
            Q(eh_aluno=False, aluno_set__isnull=False)
            | Q(eh_aluno=True, aluno_set__isnull=True)
            | Q(eh_servidor=False, servidor_set__isnull=False)
            | Q(eh_servidor=True, servidor_set__isnull=True)
            | Q(eh_prestador=False, prestadorservico_set__isnull=False)
            | Q(eh_prestador=True, prestadorservico_set__isnull=True)
        ):
            pessoa.save()
