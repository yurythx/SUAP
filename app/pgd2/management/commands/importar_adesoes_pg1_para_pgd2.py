# -------------------------------------
# Importa adesões PGD e PES do PGD 1 para o 2
# -------------------------------------

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd import models as pgd1
        from pgd2 import models as pgd2

        """
        - Obter lista das adesões vigentes no PGD 1
        - Importa para o PGD 2
        """

        pgd1_adesoes_pgd = pgd1.SolicitacaoAdesaoServidor.get_adesoes_vigentes()
        documento_adesao_pgd2 = pgd2.DocumentoAdesaoServidor.get_vigente()

        pgd1_adesoes_pts = pgd1.SolicitacaoAdesaoPtsServidor.objects.filter(
            situacao=pgd1.SolicitacaoAdesaoPtsServidor.DEFERIDO, data_desligamento__isnull=True, adesao__in=pgd1_adesoes_pgd
        )
        documento_adesao_pes_pgd2 = pgd2.DocumentoAdesaoPesServidor.get_vigente()

        if not documento_adesao_pgd2:
            print('ERRO: é necessário que se tenha "Documento de Regras relacionadas à Adesão do Servidor" vigente no PGD2')

        if not documento_adesao_pes_pgd2:
            print('ERRO: é necessário que se tenha "Observações/Regras relacionadas à Adesão do Servidor a um PES" vigente no PGD2')

        # pgd1_adesoes_pgd = pgd1_adesoes_pgd.filter(servidor__matricula='2027733')
        # pgd1_adesoes_pts = pgd1_adesoes_pts.filter(adesao__servidor__matricula='2027733')

        if documento_adesao_pgd2 and documento_adesao_pes_pgd2:
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

                pgd2_adesao_pgd.codigo_contato_pais = 55  # no PGD1 não tem código do país e por isso fica o padrão 55
                pgd2_adesao_pgd.telefone = pgd1_adesao_pgd.telefone
                pgd2_adesao_pgd.preferencia_contato = pgd1_adesao_pgd.preferencia_contato

                pgd2_adesao_pgd.situacao = pgd2.SolicitacaoAdesaoServidor.DEFERIDO
                pgd2_adesao_pgd.data_inicio = pgd1_adesao_pgd.get_data_inicio_adesao().date()

                pgd2_adesao_pgd.save()

                # Registra ação
                ra_obs = 'Esta adesão foi importada do PGD 1'
                pgd2.RegistroAcaoSolicitacaoAdesaoServidor.objects.create(
                    tipo=pgd2.SolicitacaoAdesaoServidor.DEFERIDO, solicitacao=pgd2_adesao_pgd, ip='127.0.0.1', observacao=ra_obs
                )

                print('> Importou adesão')
                print('---------------------------------')

            print('=================================')
            print(' Importação das Adesões PES')
            print('=================================')
            for pgd1_adesoao_pts in pgd1_adesoes_pts:
                print('---------------------------------')
                print('>>> Importando adesão PES do servidor: ', pgd1_adesoao_pts.adesao.servidor)

                # Cria as adesões no PGD2
                pgd2_adesao_pgd = pgd2.SolicitacaoAdesaoPesServidor()
                pgd2_adesao_pgd.adesao = pgd2.SolicitacaoAdesaoServidor.objects.get(servidor=pgd1_adesoao_pts.adesao.servidor)
                pgd2_adesao_pgd.setor = pgd1_adesoao_pts.plano_trabalho_setorial.setor
                pgd2_adesao_pgd.documento_adesao = documento_adesao_pes_pgd2
                pgd2_adesao_pgd.situacao = pgd2.SolicitacaoAdesaoPesServidor.DEFERIDO
                pgd2_adesao_pgd.save()

                # Registra ação
                ra_obs = 'Esta adesão foi importada do PGD 1'
                pgd2.RegistroAcaoSolicitacaoAdesaoPesServidor.objects.create(
                    tipo=pgd2.SolicitacaoAdesaoPesServidor.DEFERIDO, solicitacao=pgd2_adesao_pgd, ip='127.0.0.1', observacao=ra_obs
                )

                print('> Importou adesão')
                print('---------------------------------')

        print('>>> FIM')
