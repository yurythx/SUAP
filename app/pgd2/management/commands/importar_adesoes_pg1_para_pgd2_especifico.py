# -------------------------------------
# Importa adesões PGD e PES do PGD 1 para o 2
# - Utilizado apenas para casos de servidores que aderiam ao PGD depois da importação oficial que ocorreu
#   o módulo do PGD2 foi para produção
# -------------------------------------

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd import models as pgd1
        from pgd2 import models as pgd2
        from rh.models import Servidor

        # - A matrícula 2141254 foi importada para atender ao processo
        #   - https://suap.ifrn.edu.br/processo_eletronico/processo/373960/
        # - Issue
        #   - https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/12396

        servidores = Servidor.objects.filter(matricula__in=['2141254'])

        pgd1_adesoes_pgd = pgd1.SolicitacaoAdesaoServidor.get_adesoes_vigentes().filter(servidor__in=servidores)
        documento_adesao_pgd2 = pgd2.DocumentoAdesaoServidor.get_vigente()

        print('=================================')
        print(' Importação das Adesões PGD')
        print('=================================')
        for pgd1_adesao_pgd in pgd1_adesoes_pgd:
            print('---------------------------------')
            print('>>> Importando adesão do servidor: ', pgd1_adesao_pgd.servidor)

            # Apaga se já existe no PGD2
            adesao_ja_existente_pgd2 = pgd2.SolicitacaoAdesaoServidor.objects.filter(servidor=pgd1_adesao_pgd.servidor)
            if adesao_ja_existente_pgd2:
                adesao_ja_existente_pgd2.delete()
                print('> Exclui adesão já existente no PGD2')

            # Cria as adesões no PGD2
            pgd2_adesao_pgd = pgd2.SolicitacaoAdesaoServidor()
            pgd2_adesao_pgd.servidor = pgd1_adesao_pgd.servidor
            pgd2_adesao_pgd.documento_adesao = documento_adesao_pgd2
            #
            pgd2_adesao_pgd.codigo_contato_pais = 55  # no PGD1 não tem código do país e por isso fica o padrão 55
            pgd2_adesao_pgd.telefone = pgd1_adesao_pgd.telefone
            pgd2_adesao_pgd.preferencia_contato = pgd1_adesao_pgd.preferencia_contato
            #
            pgd2_adesao_pgd.situacao = pgd2.SolicitacaoAdesaoServidor.DEFERIDO
            pgd2_adesao_pgd.data_inicio = pgd1_adesao_pgd.get_data_inicio_adesao().date()
            #
            pgd2_adesao_pgd.save()

            # Registra ação
            ra_obs = 'Esta adesão foi importada do PGD 1'
            pgd2.RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                tipo=pgd2.SolicitacaoAdesaoServidor.DEFERIDO, solicitacao=pgd2_adesao_pgd, ip='127.0.0.1', observacao=ra_obs
            )

            print('> Importou adesão')
            print('---------------------------------')

        print('>>> FIM')
