from django.db import migrations


def marcar_certificados_emitidos_como_enviados(apps, schema_editor):
    Participante = apps.get_model('eventos', 'Participante')
    Participante.objects.filter(
        certificado_enviado=False,
        codigo_geracao_certificado__isnull=False,
    ).exclude(codigo_geracao_certificado='').update(certificado_enviado=True)


class Migration(migrations.Migration):
    dependencies = [
        ('eventos', '0084_evento_exigir_avaliacao_para_certificado'),
    ]

    operations = [
        migrations.RunPython(marcar_certificados_emitidos_como_enviados, migrations.RunPython.noop),
    ]
