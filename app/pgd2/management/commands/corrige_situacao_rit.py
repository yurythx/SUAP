# -------------------------------------
# Sincronizar Permissões comissão
# -------------------------------------

from djtools.management.commands import BaseCommandPlus
import tqdm


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd2.models import PlanoIndividualTrabalho

        def pode_cadastrar_entrega_rit(pit, user):
            # Situacao da adesão
            # - Adesão do PIT deve estar vigente ou desligado na carencia
            if not pit.adesao.estah_vigente_ou_desligado_na_carencia:
                return False

            # Situação do PIT
            if pit.situacao != pit.HOMOLOGADO or not pit.se_pit_ja_foi_homologado_ao_menos_uma_vez():
                return False

            r = True
            if pit.existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit(user)[0]:
                r = False

            return r

        lista_ids_pit_corrigir_rit = []
        for pit in tqdm.tqdm(PlanoIndividualTrabalho.objects.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)):
            if pode_cadastrar_entrega_rit(pit, pit.adesao.servidor.get_user()) and pit.situacao_rit is None:
                if not pit.situacao_rit:
                    lista_ids_pit_corrigir_rit.append(pit.id)

        PlanoIndividualTrabalho.objects.filter(id__in=lista_ids_pit_corrigir_rit).update(situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT)
