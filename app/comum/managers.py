import operator
from datetime import datetime, timedelta
from functools import reduce

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models import Case, Q, Value, When
from django.db.models import IntegerField


class VinculoQueryset(models.query.QuerySet):
    def get_model(self):
        return apps.get_model('comum', 'Vinculo')

    def ordenados_para_selecao(self):
        return self.annotate(
            prioridade=Case(
                When(tipo_relacionamento__model='servidor', then=Value(0)),
                When(tipo_relacionamento__model='prestadorservico', then=Value(1)),
                When(tipo_relacionamento__model='aluno', then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by('prioridade', 'user__first_name', 'user__last_name')

    def assinadores(self, permite_alunos=False, permite_maiores_18=False):
        Aluno = apps.get_model('edu', 'Aluno') if 'edu' in settings.INSTALLED_APPS else None
        q_list = [
            Q(user__eh_aluno=False, papel__isnull=False),
        ]
        if Aluno and permite_alunos:
            data_para_maioridade = datetime.now() - timedelta(days=365 * 18)
            alunos = Aluno.objects.filter(situacao__ativo=True)
            if not permite_maiores_18:
                alunos = alunos.filter(pessoa_fisica__nascimento_data__lte=data_para_maioridade)
            q_list.append(Q(id_relacionamento__in=alunos, tipo_relacionamento__model='aluno'))
        return self.ativos().filter(reduce(operator.or_, q_list)).distinct()

    def servidores(self):
        return self.filter(tipo_relacionamento__app_label='rh', tipo_relacionamento__model='servidor')

    def prestadores(self):
        return self.filter(tipo_relacionamento__app_label='comum', tipo_relacionamento__model='prestadorservico')

    def alunos(self):
        return self.filter(tipo_relacionamento__app_label='edu', tipo_relacionamento__model='aluno')

    def funcionarios(self):
        return self.servidores() | self.prestadores()

    def pessoas_externas(self):
        return self.filter(tipo_relacionamento__app_label='rh', tipo_relacionamento__model='pessoaexterna')

    def pessoas_fisicas(self):
        return self.funcionarios() | self.alunos()

    def pessoas_juridicas(self):
        return self.filter(tipo_relacionamento__app_label='rh', tipo_relacionamento__model='pessoajuridica')

    def ativos(self):
        return self.filter(ativo=True)


class VinculoManager(models.Manager):
    # Adicionamos o ordenados_para_selecao() aqui para evitar que tenhamos que lembrar de usá-lo toda vez que formos buscar vínculos para seleção, como em formulários e filtros.
    def get_queryset(self):
        return VinculoQueryset(self.model, using=self._db).ordenados_para_selecao()

    def servidores(self):
        return self.get_queryset().servidores()

    def do_terminal(self, id_terminal: int | str):
        """Vínculo de uma linha da tabela ``pessoa`` dos terminais legados, cujo id é ``-vinculo.id``.

        Id positivo é a PF de um dump anterior à linha por vínculo (dado local ainda não exportado):
        devolve ``None`` e o chamador resolve pela PF, como antes.
        """
        id_terminal = int(id_terminal)
        return self.get(pk=-id_terminal) if id_terminal < 0 else None

    def servidores_tecnicos_administrativos(self):
        Servidor = apps.get_model('rh', 'Servidor')
        return self.servidores().filter(id_relacionamento__in=Servidor.objects.tecnicos_administrativos().values_list('id', flat=True))

    def servidores_docentes(self):
        Servidor = apps.get_model('rh', 'Servidor')
        return self.servidores().filter(id_relacionamento__in=Servidor.objects.docentes().values_list('id', flat=True))

    def estagiarios_siape(self):
        Servidor = apps.get_model('rh', 'Servidor')
        return self.servidores().filter(id_relacionamento__in=Servidor.objects.estagiarios().values_list('id', flat=True))

    def prestadores(self):
        return self.get_queryset().prestadores()

    def alunos(self):
        return self.get_queryset().alunos()

    def pessoas_externas(self):
        return self.get_queryset().pessoas_externas()

    def pessoas_juridicas(self):
        return self.get_queryset().pessoas_juridicas()

    def funcionarios(self):
        return self.get_queryset().funcionarios()

    def funcionarios_ativos(self):
        return self.funcionarios().filter(ativo=True)

    def pessoas_fisicas(self):
        return self.get_queryset().pessoas_fisicas()

    def assinadores(self, permite_alunos=False, permite_maiores_18=False):
        return self.get_queryset().assinadores(permite_alunos, permite_maiores_18)

    def ativos(self):
        return self.get_queryset().ativos()
