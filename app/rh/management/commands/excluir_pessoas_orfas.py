import sys
from datetime import datetime
from itertools import chain

from django.contrib.admin.utils import NestedObjects
from django.db import router
from django.utils import termcolors

from comum.models import Vinculo
from djtools.management.commands import BaseCommandPlus
from protocolo.models import Processo
from rh.models import Pessoa, PessoaExterna, PessoaFisica


def format_time(dt):
    """
    Retira a parte não significativa de objetos datetime ou timedelta.
    formato padrão para datetime: 2014-05-13 16:03:26.087286
    formato padrão para timedelta: 0:01:22.473183
    """
    return str(dt).split('.')[0]


def get_sub_instances(instance):
    """Retorna todas as heranças de um objeto"""

    def inner(instance, children=None):
        if children is None:
            children = []
        children.append(instance)
        # Recupera os campos criados que relacionam um para muitos ou um para um
        fields = [field for field in instance._meta.get_fields() if field.one_to_one]
        for field in fields:
            if issubclass(field.related_model, instance._meta.model) or issubclass(instance._meta.model, field.related_model):
                if hasattr(instance, field.name):
                    obj = getattr(instance, field.name)
                    if obj not in children:
                        inner(obj, children)
        return list(set(children))

    return inner(instance, [])


def pode_remover_sub_instances(pessoa_fisica):
    """Só pode remover se herdar da classe Pessoa ou PessoaFisica"""
    sub_instances = get_sub_instances(pessoa_fisica)
    return all(sub_instance.__class__ in (Pessoa, PessoaFisica) for sub_instance in sub_instances)


def get_objetos_relacionados(obj):
    """Return a generator to the objects that would be deleted if we delete "obj" (excluding obj)"""
    collector = NestedObjects(using=router.db_for_write(obj))
    collector.collect([obj])

    def flatten(elem):
        if isinstance(elem, list):
            return chain.from_iterable(list(map(flatten, elem)))
        elif obj != elem:
            return (elem,)
        return ()

    result = flatten(collector.nested())
    return result


def pode_remover_com_objetos_relacionados(obj, modelos_permitidos=None):
    if not modelos_permitidos:
        modelos_permitidos = (Pessoa, PessoaFisica, PessoaExterna, Vinculo, Processo)
    # field.one_to_one pode ser herança, mas tb só o OneToOneField
    # field.one_to_many nos models que usam ForeignKey
    # [field for field in PessoaFisica._meta.get_fields() if field.one_to_many]
    # field.many_to_one NÃO interessam, são os que o model tem ForeignKey
    # [field for field in PessoaFisica._meta.get_fields() if field.many_to_one]
    # field.many_to_one nos models que usam ManyToManyField
    # [field for field in PessoaFisica._meta.get_fields() if field.many_to_many]
    fields = [field for field in obj._meta.get_fields() if field.one_to_one or field.one_to_many or field.many_to_many]
    retorno = True
    # print obj
    for field in fields:
        try:
            # field_obj = hasattr(field, 'get_accessor_name') and hasattr(obj, field.get_accessor_name()) and getattr(obj, field.get_accessor_name()) \
            #             or hasattr(obj, field.name) and getattr(obj, field.name)
            field_obj = None
            if hasattr(field, 'get_accessor_name') and hasattr(obj, field.get_accessor_name()):
                field_obj = getattr(obj, field.get_accessor_name())
            elif hasattr(obj, field.name):
                field_obj = getattr(obj, field.name)
            # else:
            # try:
            #     pf.projetos_avaliador_externo
            # except ObjectDoesNotExist as erro:
            #     print 'erro ', erro
            # print 'else'
            # print field.name, field.get_accessor_name()
            # import ipdb; ipdb.set_trace()
            # pass

            if field_obj is None:
                continue
            elif hasattr(field_obj, '_meta'):
                if field.model not in modelos_permitidos:
                    # print field
                    # print '>>', field_obj
                    # print '>>', '>>', field_obj
                    retorno = False

            else:
                if field_obj.exists():
                    if field.related_model not in modelos_permitidos:
                        # print field
                        # print '>>', field_obj
                        # print '>>', '>>', field_obj.all()
                        retorno = False
        except Exception:
            pass

    return retorno


def pode_remover_objetos_relacionados(pessoa_fisica):
    """Só pode deletar se herdar da classe Pessoa ou PessoaFisica"""
    objetos_relacionados = get_objetos_relacionados(pessoa_fisica)
    for objeto_relacionado in objetos_relacionados:
        if objeto_relacionado.__class__ not in (Pessoa, PessoaFisica, PessoaExterna, Vinculo, Processo):
            return False
    return True


def pode_remover(obj, modelos_permitidos=None):
    if not modelos_permitidos:
        modelos_permitidos = (Pessoa, PessoaFisica, PessoaExterna, Vinculo, Processo)

    def flatten(elem):
        if isinstance(elem, list):
            return chain.from_iterable(list(map(flatten, elem)))
        elif obj != elem:
            return (elem,)
        return ()

    collector = NestedObjects(using='default')
    collector.collect([obj])
    return all(model.__class__ in modelos_permitidos for model in flatten(collector.nested()))


class Command(BaseCommandPlus):
    help = 'Exclui as pessoas físicas sem nenhum relacionamento'

    def handle(self, *args, **options):
        modelos_permitidos = (Pessoa, PessoaFisica, PessoaExterna, Vinculo)

        pessoas_fisicas = PessoaFisica.objects.filter(pessoaexterna__isnull=False)
        total = pessoas_fisicas.count()
        count = 0
        sys.stdout.write('\n')
        x0 = datetime.now()
        ids = []
        for pessoa_fisica in pessoas_fisicas:
            count += 1
            porcentagem = int(float(count) / total * 100)
            sys.stdout.write(
                termcolors.make_style(fg='cyan', opts=('bold',))(
                    '\r[{}] {}% - testando {} de {} em {}'.format(
                        '#' * (porcentagem / 10), porcentagem, count, total, format_time(datetime.now() - x0)
                    )
                )
            )
            sys.stdout.flush()
            if pode_remover(pessoa_fisica, modelos_permitidos):
                ids.append(pessoa_fisica.id)

        dados = PessoaFisica.objects.filter(id__in=ids).delete()

        print([(model, qtd_deleted) for model, qtd_deleted in list(dados[1].items()) if qtd_deleted != 0])
        modelos_permitidos = [modelo._meta.label for modelo in modelos_permitidos]
        print([(model, qtd_deleted) for model, qtd_deleted in list(dados[1].items()) if qtd_deleted != 0 and model not in modelos_permitidos])
