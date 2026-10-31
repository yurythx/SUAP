from djtools.management.commands import BaseCommandPlus
from gestao.models import Indicador


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        'A rotina abaixo foi criara para auxiliar na montagem dos UPDATEs que serão
        aplicados nos Indicadores que usam variáveis do acadêmico. Com o advento
        das variáveis "irmãs", "com e sem convênio", os indicadores tem que ser ajustados
        para usar as variáveis "sem convênio" para manter a coerência.
        Ex: A variável 'AM' antes levava em contato todos os alunos excluindo os
        PRONATEC. Agora ela traz todos os alunos, e a variável que traz somente os
        alunos sem convênio é a 'AM_OR'.
        """
        # Variáveis do Acadêmico (exceto AMNF)
        # for v in Variavel.objects.filter(sigla__in=['AM', 'AC', 'AE', 'AR', 'AJ', 'AI', 'AIC']):
        #     for i in Indicador.objects.all():
        #         if v in i.get_variaveis():
        #             print '# Variavel {}  -  Indicador: {} ({})  -  Formula Antiga: {}' % (v.sigla, i.sigla, i.nome, i.formula)
        #             print "Indicador.objects.filter(sigla='{}').update(formula='{}', nome='{}')" % (i.sigla, i.formula, i.nome)
        #             print ''

        print('Inicializando ajuste dos indicares acadêmicos...')

        # Variavel AM  -  Indicador: A/DTI (Relação Alunos/Docente em Tempo Integral)  -  Formula Antiga: AM/DTI
        Indicador.objects.filter(sigla='A/DTI').update(formula='AM_SC/DTI', nome='Relação Alunos (sem convênio)/Docente em Tempo Integral')

        # Variavel AM  -  Indicador: GCA (Gastos Correntes por Aluno)  -  Formula Antiga: GCO/AM
        Indicador.objects.filter(sigla='GCA').update(formula='GCO/AM_OR', nome='Gastos Correntes por Aluno (sem convênio)')

        # Variavel AM  -  Indicador: RA/C (Relação Alunos/Computador)  -  Formula Antiga: AM/C
        Indicador.objects.filter(sigla='RA/C').update(formula='AM_SC/C', nome='Relação Alunos (sem convênio) / Computador')

        # Variavel AM  -  Indicador: I/A (Relação de Ingressos/Alunos)  -  Formula Antiga: (AI*100)/AM
        # Variavel AI  -  Indicador: I/A (Relação de Ingressos/Alunos)  -  Formula Antiga: (AI*100)/AM
        Indicador.objects.filter(sigla='I/A').update(formula='(AI_SC*100)/AM_OR', nome='Relação de Ingressos (sem convênio) / Alunos (sem convênio)')

        # Variavel AM  -  Indicador: RC/A (Relação Concluintes/Alunos (RC/A))  -  Formula Antiga: (AC*100)/AM
        # Variavel AC  -  Indicador: RC/A (Relação Concluintes/Alunos (RC/A))  -  Formula Antiga: (AC*100)/AM
        Indicador.objects.filter(sigla='RC/A').update(formula='(AC_SC*100)/AM_OR', nome='Relação Concluintes (sem convênio) / Alunos (sem convênio)')

        # Variavel AM  -  Indicador: RFE (Índice de Retenção do Fluxo Escolar)  -  Formula Antiga: (AR*100)/AM
        # Variavel AR  -  Indicador: RFE (Índice de Retenção do Fluxo Escolar)  -  Formula Antiga: (AR*100)/AM
        Indicador.objects.filter(sigla='RFE').update(formula='(AR_SC*100)/AM_OR', nome='Índice de Retenção do Fluxo Escolar (alunos sem convênio)')

        # Variavel AC  -  Indicador: IEAC (Índice de Eficiência Acadêmica de Concluintes)  -  Formula Antiga: (AC*100)/AIC
        # Variavel AIC -  Indicador: IEAC (Índice de Eficiência Acadêmica de Concluintes)  -  Formula Antiga: (AC*100)/AIC
        Indicador.objects.filter(sigla='IEAC').update(
            formula='(AC_SC*100)/AIC_OR', nome='Índice de Eficiência Acadêmica de Concluintes (sem convênio)'
        )

        print('Atualização concluída - OK')
