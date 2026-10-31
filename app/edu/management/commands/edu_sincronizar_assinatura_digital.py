from djtools.management.commands import BaseCommandPlus
from edu.diploma_digital.rap import AssinadorDigital
from edu.models import AssinaturaDigital, HistoricoEscolarParcial


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        assinador = AssinadorDigital(debug=True)
        for assinatura_digital in AssinaturaDigital.objects.filter(concluida=False, data_revogacao__isnull=True):
            try:
                assinador.sincronizar(assinatura_digital)
            except BaseException:
                print(f'Erro ao sincronizar assinatura digital #{assinatura_digital.id}')

        historicos = HistoricoEscolarParcial.objects.all()
        # históricos não enviados
        for historico in historicos.filter(id_rap=0):
            try:
                assinador.enviar_historico_escolar_parcial(historico)
            except BaseException:
                print(f'Erro ao sincronizar histórico digital #{historico.id}')
        # históricos enviados e não consultados
        historicos = historicos.filter(id_rap__gt=0)
        for historico in historicos.filter(status_rap__isnull=True) | historicos.filter(status_rap__lte=9):
            historico.status_rap = assinador.consultar_documento(historico)
            historico.save()
            if historico.registro_emissao_documento_id is None and historico.status_rap > 1:
                historico.gerar_registro_emissao_documento()
