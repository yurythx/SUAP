# ruff: noqa: T100

from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus
from tesouro_gerencial.models import DocumentoLiquidacao, DocumentoPagamento


class Command(BaseCommandPlus):
    EXCLUDED_ATTRS_LIQUIDACAO = '_state', 'id', 'numero', 'tipo', 'data_emissao', 'observacao', 'documento_empenho_inicial_id'
    # EXCLUDED_ATTRS_LIQUIDACAO = '_state', 'id', 'numero', 'tipo', 'data_emissao', 'observacao', 'documento_empenho_inicial_id', \
    #                             'ptres_id', 'favorecido_codigo', 'favorecido_nome', 'naturesa_despesa_original', 'grupo_despesa_original', \
    #                             'acao_governo_id', 'plano_interno_id', 'acao_governo_original', 'fonte_recurso_id', 'esfera_orcamentaria_id', \
    #                             'fonte_recurso_original', 'responsavel_ug_id', 'unidade_orcamentaria_id', 'emitente_ug_id'
    #

    def comparar(self, obj1, obj2, excluded_attrs):
        d1, d2 = obj1.__dict__, obj2.__dict__
        for key, value in d1.items():
            if key in excluded_attrs:
                continue
            try:
                if value != d2[key]:
                    self.stdout.write('\n')
                    self.stdout.write(key)
                    import ipdb

                    ipdb.set_trace()

                self.stdout.write(f'{key} => {value} == {d2[key]}')
            except KeyError:
                import ipdb

                ipdb.set_trace()
        # import ipdb; ipdb.set_trace()
        # pass

    def handle(self, *args, **options):
        liquidacoes = DocumentoLiquidacao.objects.all()
        pagamentos = DocumentoPagamento.objects.all()
        total = liquidacoes.count() + pagamentos.count()
        count = 0
        for liquidacao in liquidacoes:
            count += 1
            porcentagem = int(float(count) / total * 100)
            self.stdout.write(
                termcolors.make_style(fg='cyan', opts=('bold',))(
                    '\r[{}] {}% - Extraindo {} de {}'.format('#' * int(porcentagem / 10), porcentagem, count, total)
                )
            )
            self.stdout.flush()
            for item in liquidacao.itens.all():
                empenho = item.documento_empenho_inicial
                self.comparar(empenho, liquidacao, self.EXCLUDED_ATTRS_LIQUIDACAO)

        # for pagamento in pagamentos:
        #     count += 1
        #     porcentagem = int(float(count) / total * 100)
        #     sys.stdout.write(termcolors.make_style(fg='cyan', opts=('bold',))('\r[{0}] {1}% - Extraindo {2} de {3}'.format('#' * int(porcentagem / 10), porcentagem, count, total)))
        #     sys.stdout.flush()
        #     for item in pagamento.itens.all():
        #         empenho = item.documento_empenho_inicial
        #         self.comparar(empenho, liquidacao, self.EXCLUDED_ATTRS_PAGAMENTO)
