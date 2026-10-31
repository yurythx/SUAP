from django.contrib.auth.models import Group

from djtools.management.commands import BaseCommandPlus
from edu.models import Professor
from rh.models import Servidor


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        grupo_professor = Group.objects.get(name='Professor')

        for servidor in Servidor.objects.vinculados().filter(eh_docente=True, vinculos__professor__isnull=True):
            if servidor.get_user():
                servidor.get_user().groups.add(grupo_professor)
                Professor.objects.get_or_create(vinculo=servidor.get_vinculo())

        lista = []

        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='M',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(titulacao__nome__unaccent__icontains='doutor').values_list(
                        'id', flat=True
                    ),
                ).exclude(titulacao__icontains='doutor'),
                'Doutor',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='F',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(titulacao__nome__unaccent__icontains='doutor').values_list(
                        'id', flat=True
                    ),
                ).exclude(titulacao__icontains='doutor'),
                'Doutora',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='M',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(titulacao__nome__unaccent__icontains='mestr').values_list('id', flat=True),
                )
                .exclude(titulacao__icontains='doutor')
                .exclude(titulacao__icontains='mestr'),
                'Mestre',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='F',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(titulacao__nome__unaccent__icontains='mestr').values_list('id', flat=True),
                )
                .exclude(titulacao__icontains='doutor')
                .exclude(titulacao__icontains='mestr'),
                'Mestra',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__id_relacionamento__in=Servidor.objects.filter(titulacao__nome__unaccent__icontains='especiali').values_list(
                        'id', flat=True
                    )
                )
                .exclude(titulacao__icontains='doutor')
                .exclude(titulacao__icontains='mestr')
                .exclude(titulacao__icontains='especiali'),
                'Especialista',
            )
        )

        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='M',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(nivel_escolaridade__nome__unaccent__icontains='doutor').values_list(
                        'id', flat=True
                    ),
                ).exclude(titulacao__icontains='doutor'),
                'Doutor',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='F',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(nivel_escolaridade__nome__unaccent__icontains='doutor').values_list(
                        'id', flat=True
                    ),
                ).exclude(titulacao__icontains='doutor'),
                'Doutora',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='M',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(nivel_escolaridade__nome__unaccent__icontains='mestr').values_list(
                        'id', flat=True
                    ),
                )
                .exclude(titulacao__icontains='doutor')
                .exclude(titulacao__icontains='mestr'),
                'Mestre',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__pessoa__pessoafisica__sexo='F',
                    vinculo__id_relacionamento__in=Servidor.objects.filter(nivel_escolaridade__nome__unaccent__icontains='mestr').values_list(
                        'id', flat=True
                    ),
                )
                .exclude(titulacao__icontains='doutor')
                .exclude(titulacao__icontains='mestr'),
                'Mestra',
            )
        )
        lista.append(
            (
                Professor.servidores.filter(
                    vinculo__id_relacionamento__in=Servidor.objects.filter(nivel_escolaridade__nome__unaccent__icontains='especiali').values_list(
                        'id', flat=True
                    )
                )
                .exclude(titulacao__icontains='doutor')
                .exclude(titulacao__icontains='mestr')
                .exclude(titulacao__icontains='especiali'),
                'Especialista',
            )
        )

        lista.append((Professor.servidores_docentes.filter(vinculo__pessoa__pessoafisica__sexo='M', titulacao__isnull=True), 'Graduado'))
        lista.append((Professor.servidores_docentes.filter(vinculo__pessoa__pessoafisica__sexo='F', titulacao__isnull=True), 'Graduada'))

        for qs, titulacao in lista:
            qs.update(titulacao=titulacao)
