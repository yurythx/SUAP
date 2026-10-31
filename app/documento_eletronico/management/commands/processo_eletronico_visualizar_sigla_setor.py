from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Command criado para reassinar os depachos devido a um erro ao processamento
    das variáveis
    """

    def handle(self, *args, **options):
        self.gerar_numero_protocolo_fisico()

    def gerar_numero_protocolo_fisico(self):
        Setor = apps.get_model('rh', 'Setor')

        setores = Setor.objects.suap_ativos().filter(uo__sigla__in=['LAJ', 'CNAT', 'RE', 'CA']).order_by('uo__sigla')

        for setor in setores:
            setor_arvore_completa = setor.get_caminho(ordem_descendente=False)
            setor_sigla_arvore_completa = '/'.join(str(s) for s in setor_arvore_completa)

            setor_sigla_arvore_completa_simplificada = ''
            for s in setor_arvore_completa:
                # print s.sigla
                s_eh_campus = s.unidadeorganizacional if hasattr(s, 'unidadeorganizacional') else ''

                if not s.uo or s_eh_campus:
                    setor_sigla_arvore_completa_simplificada = setor_sigla_arvore_completa_simplificada + s.sigla + '#'
                else:
                    setor_sigla_arvore_completa_simplificada = setor_sigla_arvore_completa_simplificada + s.sigla.replace('/' + s.uo.sigla, '') + '#'

            setor_sigla_arvore_completa_simplificada = setor_sigla_arvore_completa_simplificada[:-1]

            print(f'Setor {setor.nome}')
            print(f'Sigla: {setor.sigla}')
            print(f'Sigla da Árvore Completa: {setor_sigla_arvore_completa} (tamanho: {len(setor_sigla_arvore_completa)})')
            print(
                f'Sigla da Árvore Completa Simplificada: {setor_sigla_arvore_completa_simplificada} (tamanho: {len(setor_sigla_arvore_completa_simplificada)})'
            )

            setor_eh_campus = setor.unidadeorganizacional if hasattr(setor, 'unidadeorganizacional') else ''
            if setor_eh_campus:
                print(f'Setor é campus: Sim ({setor_eh_campus})')
            else:
                print('Setor é campus: Não')

            print()
