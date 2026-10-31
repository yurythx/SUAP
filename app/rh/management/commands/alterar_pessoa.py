from djtools.management.commands import BaseCommandPlus
from rh.models import Pessoa


def atualizar_pessoa(obj_from, obj_to, save=True):
    # one_to_many
    print('------------------')
    print(('From: ', obj_from))
    print(('To: ', obj_to))
    fields = [f for f in obj_from._meta.get_fields() if f.one_to_many]
    for r in fields:
        o2m = r.related_model.objects.filter(**{r.field.name: obj_from})
        print((o2m, r.field.name))
        if save:
            o2m.update(**{r.field.name: obj_to})

    # many_to_many
    fields = [f for f in obj_from._meta.get_fields() if f.many_to_many]
    for field in fields:
        print(field.name)
        if hasattr(field, 'get_accessor_name'):
            objs_related = getattr(obj_from, field.get_accessor_name()).all()
            related_attname = field.field.attname
            for obj_related in objs_related:
                m2m = getattr(obj_related, related_attname)
                print((m2m.all(), obj_related))
                if save:
                    m2m.remove(obj_from)
                    m2m.add(obj_to)
        else:
            objs_related = getattr(obj_from, field.name).all()
            m2m_to = getattr(obj_to, field.name)
            m2m_from = getattr(obj_from, field.name)
            print(m2m_from.all())
            for obj_related in objs_related:
                if save:
                    m2m_from.remove(obj_related)
                    m2m_to.add(obj_related)


class Command(BaseCommandPlus):
    help = 'Altera os relacionamentos de uma pessoa para outra'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)
        parser.add_argument('--save', action='store_true', dest='save', default=False, help='Salva as alterações no banco')

    def handle(self, *args, **options):
        if len(args) != 2:
            print('Quantidade de parâmetros inválida.')
            print('Exemplo: python manage.py alterar_pessoa pk1 pk2')
            return
        obj_from = Pessoa.objects.get(pk=args[0])
        obj_to = Pessoa.objects.get(pk=args[1])
        atualizar_pessoa(obj_from, obj_to, options.get('save'))
