from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from edu.models import Log


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        modelos_diario_aluno = []
        modelos_diario = []
        modelos_aluno = []
        modelos_ignore = []
        print('identificando modelos')

        modelos = Log.objects.values_list('modelo', flat=True).distinct()
        for modelo in modelos:
            app = Log.objects.filter(modelo=modelo).values_list('app', flat=True)[0]
            try:
                cls = apps.get_model(app, modelo)
            except Exception:
                tem_diario = False
                tem_aluno = False
            tem_diario = hasattr(cls, 'diario') or hasattr(cls, 'get_diario')
            tem_aluno = hasattr(cls, 'aluno') or hasattr(cls, 'get_aluno')
            if tem_diario and tem_aluno:
                modelos_diario_aluno.append([app, modelo])
            elif tem_diario:
                modelos_diario.append([app, modelo])
            elif tem_aluno:
                modelos_aluno.append([app, modelo])
            else:
                modelos_ignore.append([app, modelo])

        print(('TEM DIARIO: ', modelos_diario))
        print(('TEM ALUNO: ', modelos_aluno))
        print(('TEM DIARIO E ALUNO: ', modelos_diario_aluno))

        for app, modelo in modelos_diario:
            print(f'modelo {modelo}.')
            logs = Log.objects.filter(modelo=modelo, ref_diario__isnull=True).values_list('pk', 'ref')
            qtd = logs.count()
            print(f' - verificando {qtd} logs')
            if qtd > 0:
                self.corrigir(logs, app, modelo, tipo='diario')

        for app, modelo in modelos_aluno:
            print(f'modelo {modelo}.')
            logs = Log.objects.filter(modelo=modelo, ref_aluno__isnull=True).values_list('pk', 'ref')
            qtd = logs.count()
            print(f' - verificando {qtd} logs')
            if qtd > 0:
                self.corrigir(logs, app, modelo, tipo='aluno')

        for app, modelo in modelos_diario_aluno:
            print(f'modelo {modelo}.')
            logs = Log.objects.filter(modelo=modelo).exclude(ref_diario__isnull=False, ref_aluno__isnull=False).values_list('pk', 'ref')
            qtd = logs.count()
            print(f' - verificando {qtd} logs')
            if qtd > 0:
                self.corrigir(logs, app, modelo, tipo='diario_aluno')

    def corrigir(self, logs, app, modelo, tipo):
        try:
            cls = apps.get_model(app, modelo)
            for pk, ref in logs:
                try:
                    instancia = cls.objects.get(pk=ref)
                except Exception:
                    instancia = None
                if instancia:
                    if tipo == 'diario':
                        diario = (
                            hasattr(instancia, 'diario')
                            and instancia.diario
                            and instancia.diario.pk
                            or hasattr(instancia, 'get_diario')
                            and instancia.get_diario()
                            and instancia.get_diario().pk
                            or None
                        )
                        Log.objects.filter(pk=pk).update(ref_diario=diario)
                    elif tipo == 'aluno':
                        aluno = (
                            hasattr(instancia, 'aluno')
                            and instancia.aluno
                            and instancia.aluno.pk
                            or hasattr(instancia, 'get_aluno')
                            and instancia.get_aluno()
                            and instancia.get_aluno().pk
                            or None
                        )
                        Log.objects.filter(pk=pk).update(ref_aluno=aluno)
                    elif tipo == 'diario_aluno':
                        diario = (
                            hasattr(instancia, 'diario')
                            and instancia.diario
                            and instancia.diario.pk
                            or hasattr(instancia, 'get_diario')
                            and instancia.get_diario()
                            and instancia.get_diario().pk
                            or None
                        )
                        aluno = (
                            hasattr(instancia, 'aluno')
                            and instancia.aluno
                            and instancia.aluno.pk
                            or hasattr(instancia, 'get_aluno')
                            and instancia.get_aluno()
                            and instancia.get_aluno().pk
                            or None
                        )
                        Log.objects.filter(pk=pk).update(ref_aluno=aluno, ref_diario=diario)
        except Exception:
            pass
