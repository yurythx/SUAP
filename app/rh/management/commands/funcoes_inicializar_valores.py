from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from rh.models import Funcao

Configuracao = apps.get_model('comum', 'configuracao')


class Command(BaseCommandPlus):
    help = """
        Comando a ser executado dentro do contexto do Erro 5232 (novembro/2023):
            - Inicializar os atributos "eh_funcao_chefia" e "ch_semanal" de todas as funções cadastradas (rh.models.Funcao);
            - Inicializar a configuração "rh.funcoes_codigos_e_niveis_liberados_frequencia";
    """

    def handle(self, *args, **options):
        ###
        # atributos "eh_funcao_chefia" e "ch_semanal" de todas as funções cadastradas (rh.models.Funcao)

        FUNCAO_CODIGO_CD = 'CD'
        FUNCAO_CODIGO_FG = 'FG'

        FUNCAO_CODIGO_FUC = 'FUC'
        funcao_fuc_eh_considerado_chefia = Configuracao.get_valor_por_chave(app='rh', chave='fuc_considerado_chefia')

        FUNCAO_CODIGO_SUBST_CHEFIA = Configuracao.get_valor_por_chave(app='rh', chave='sigla_funcao_substituicao_chefia')

        funcao_fag_eh_considerado_chefia = Configuracao.get_valor_por_chave(app='rh', chave='fag_considerado_chefia')
        FUNCAO_CODIGO_APOIO_GESTAO = Configuracao.get_valor_por_chave(app='rh', chave='sigla_funcao_apoio_gestao')

        for funcao in Funcao.objects.all():
            atributos_aplica_valores_default = (
                funcao.codigo == FUNCAO_CODIGO_FG
                or funcao.codigo == FUNCAO_CODIGO_CD
                or (funcao_fuc_eh_considerado_chefia and funcao.codigo == FUNCAO_CODIGO_FUC)
                or (FUNCAO_CODIGO_SUBST_CHEFIA and funcao.codigo == FUNCAO_CODIGO_SUBST_CHEFIA)
                or (funcao_fag_eh_considerado_chefia and FUNCAO_CODIGO_APOIO_GESTAO and funcao.codigo == FUNCAO_CODIGO_APOIO_GESTAO)
            )

            if atributos_aplica_valores_default:
                funcao.eh_funcao_chefia = True
                funcao.ch_semanal = 40
            else:
                funcao.eh_funcao_chefia = False
                funcao.ch_semanal = None

            funcao.save()

            print(funcao)

        ###
        # configuração "rh.funcoes_codigos_e_niveis_liberados_frequencia"

        SERVIDORFUNCAOHISTORICO_FUNCOES_LIBERADO_FREQUENCIA = ['CD']
        SERVIDORFUNCAOHISTORICO_NIVEIS_LIBERADO_FREQUENCIA = ['1', '2', '3']
        CODIGOS_E_NIVEIS_LIBERADO_FREQUENCIA = []

        for codigo in SERVIDORFUNCAOHISTORICO_FUNCOES_LIBERADO_FREQUENCIA:
            for nivel in SERVIDORFUNCAOHISTORICO_NIVEIS_LIBERADO_FREQUENCIA:
                CODIGOS_E_NIVEIS_LIBERADO_FREQUENCIA.append(f'{codigo}-{nivel}')

        conf = Configuracao.objects.filter(app='rh', chave='funcoes_codigos_e_niveis_liberados_frequencia').first()
        if not conf:
            conf = Configuracao()

        conf.app = 'rh'
        conf.chave = 'funcoes_codigos_e_niveis_liberados_frequencia'
        conf.valor = ','.join(CODIGOS_E_NIVEIS_LIBERADO_FREQUENCIA)

        conf.save()
