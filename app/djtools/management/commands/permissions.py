import json

from django.contrib.auth.models import Group

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Realiza uma verificação nas permissões salvas no arquivo "permissions.json"',
        )

    def handle(self, *args, **options):
        if options['check']:
            d = json.load(open('permissions.json'))
            for name, perms in d.items():
                s1 = set(Group.objects.get(name=name).permissions.values_list('codename', flat=True))
                s2 = set(perms)
                if s1 != s2:
                    print(f'{name}\n{s1}\n{s2}\n\n')
                    return
        d = {}
        for g in Group.objects.all().order_by('id'):
            d[g.name] = list(g.permissions.values_list('codename', flat=True))
        json.dump(d, open('permissions.json', 'w'))
