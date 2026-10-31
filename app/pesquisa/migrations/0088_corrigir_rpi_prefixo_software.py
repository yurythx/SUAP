"""Tira o 'C' do número das RPI de software gravado por ``importar_rpi_software`` (#17462).

A revista de software é ``PC<numero>.zip`` e o número era extraído com ``codigo[1:]``, gravando
'C2700' em ``PropriedadeIntelectual.ultima_rpi``, ``RegistroPropriedadeIntelectual.primeira_rpi``
e ``PublicacaoPropriedadeIntelectual.rpi``. Idempotente: só toca valores que casam ``^C\\d+$``.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations

COM_PREFIXO = r'^C\d+$'


def _corrigir_campo(modelo: Any, campo: str) -> None:
    for objeto in modelo.objects.filter(**{f'{campo}__regex': COM_PREFIXO}):
        modelo.objects.filter(pk=objeto.pk).update(**{campo: getattr(objeto, campo)[1:]})


def _herdar_leitura(gemea: Any, despacho: Any) -> None:
    if despacho.lida and not gemea.lida:
        gemea.lida, gemea.lida_por_id, gemea.lida_em = True, despacho.lida_por_id, despacho.lida_em
        gemea.save(update_fields=['lida', 'lida_por', 'lida_em'])


def _corrigir_despachos(publicacao: Any) -> None:
    # A mesma publicação pode já existir com o número certo (importação de patente ou RPI específica):
    # nesse caso fica a gêmea, com a leitura da 'C<n>' se só esta estava lida, e a 'C<n>' é apagada.
    for despacho in publicacao.objects.filter(rpi__regex=COM_PREFIXO).order_by('pk'):
        numero = despacho.rpi[1:]
        gemea = (
            publicacao.objects.filter(propriedadeintelectual_id=despacho.propriedadeintelectual_id, rpi=numero, codigo=despacho.codigo)
            .order_by('pk')
            .first()
        )
        if gemea is None:
            publicacao.objects.filter(pk=despacho.pk).update(rpi=numero)
        else:
            _herdar_leitura(gemea, despacho)
            despacho.delete()


def corrigir_rpi_prefixo_software(apps: Any, schema_editor: Any) -> None:
    _corrigir_campo(apps.get_model('pesquisa', 'PropriedadeIntelectual'), 'ultima_rpi')
    _corrigir_campo(apps.get_model('pesquisa', 'RegistroPropriedadeIntelectual'), 'primeira_rpi')
    _corrigir_despachos(apps.get_model('pesquisa', 'PublicacaoPropriedadeIntelectual'))


class Migration(migrations.Migration):
    dependencies = [
        ('pesquisa', '0087_transferenciatecnologica_anexo_contrato_and_more'),
    ]

    operations = [migrations.RunPython(corrigir_rpi_prefixo_software, reverse_code=migrations.RunPython.noop)]
