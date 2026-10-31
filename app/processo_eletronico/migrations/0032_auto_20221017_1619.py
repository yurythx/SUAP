import tqdm
import datetime
import pandas as pd
from django.db import migrations, models
import django.db.models.deletion
import djtools.db.models
from django.core.management import call_command


WORK_DIR = '/tmp/processo_eletronico'


def criar_vinculo_para_pj(apps, pessoa_id):
    ContentType = apps.get_model('contenttypes.ContentType')
    PessoaJuridica = apps.get_model('rh.PessoaJuridica')
    tipo_relacionamento = ContentType.objects.get(model='pessoajuridica', app_label='rh')
    pessoa = PessoaJuridica.objects.filter(pk=pessoa_id).first()
    Vinculo = apps.get_model('comum.Vinculo')
    return Vinculo.objects.create(
        pessoa=pessoa, id_relacionamento=pessoa.pk,
        tipo_relacionamento=tipo_relacionamento, secret=pessoa.id
    )


def get_relacionamento(apps, pessoa_fisica):
    ContentType = apps.get_model('contenttypes.ContentType')
    tipo_relacionamento = None
    id_relacionamento = None
    if pessoa_fisica.eh_aluno:
        tipo_relacionamento = ContentType.objects.get(model='aluno', app_label='edu')
        id_relacionamento = pessoa_fisica.aluno_edu_set.all().first().pk
    elif pessoa_fisica.eh_prestador:
        tipo_relacionamento = ContentType.objects.get(model='prestador', app_label='rh')
        id_relacionamento = pessoa_fisica.prestadores.all().first().pk
    elif pessoa_fisica.eh_servidor:
        tipo_relacionamento = ContentType.objects.get(model='servidor', app_label='rh')
        id_relacionamento = pessoa_fisica.servidores.all().first().pk
    #
    return id_relacionamento, tipo_relacionamento


def criar_vinculo_para_pf(apps, pessoa):
    PessoaExterna = apps.get_model('rh.PessoaExterna')
    Vinculo = apps.get_model('comum.Vinculo')
    ContentType = apps.get_model('contenttypes.ContentType')

    pf = pessoa.pessoafisica
    vinculo = None
    if not pf.aluno_edu_set.all() and not pf.prestadores.all() and not pf.servidores.all() and not pf.pessoaexterna_set.all():
        tipo_relacionamento = ContentType.objects.get(model='pessoaexterna', app_label='rh')
        pe = PessoaExterna.objects.create(pessoa_fisica=pf, nome=pessoa.nome, cpf=pf.cpf)
        vinculo = Vinculo.objects.create(
            pessoa=pessoa, id_relacionamento=pe.pk,
            tipo_relacionamento=tipo_relacionamento,
            secret=pessoa.id
        )
    else:
        id_relacionamento, tipo_relacionamento = get_relacionamento(apps, pf)
        vinculo = Vinculo.objects.create(
            pessoa=pessoa, id_relacionamento=id_relacionamento,
            tipo_relacionamento=tipo_relacionamento, secret=pessoa.id
        )

    return vinculo


def criar_pessoa_externa(apps, dic, pessoa):
    if pessoa.id not in dic:
        #
        PessoaFisica = apps.get_model('rh.PessoaFisica')
        eh_pf = PessoaFisica.objects.filter(pk=pessoa.id).exists()
        vinculo = criar_vinculo_para_pf(apps, pessoa) if eh_pf else criar_vinculo_para_pj(apps, pessoa)
        dic[pessoa.id] = vinculo.pk


def migrar_fk_processo(apps, dic):
    Pessoa = apps.get_model('rh.Pessoa')
    ProcessoIntressado = apps.get_model('processo_eletronico.ProcessoInteressado')
    ProcessoAcompanhante = apps.get_model('processo_eletronico.ProcessoAcompanhante')
    ComentarioProcesso = apps.get_model('processo_eletronico.ComentarioProcesso')
    #
    print("\nAtualizando Model Processo - Interessados\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(processointeressado__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        ProcessoIntressado.objects.filter(pessoa_id=pessoa.id).update(vinculo_id=dic[pessoa.id], skip_history=True)
        ProcessoAcompanhante.objects.filter(pessoa_id=pessoa.id).update(vinculo_id=dic[pessoa.id], skip_history=True)
    #
    print("\nAtualizando Model Processo - Acompanhantes....\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(processoacompanhante__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        ProcessoAcompanhante.objects.filter(pessoa_id=pessoa.id).update(vinculo_id=dic[pessoa.id], skip_history=True)

    print("\nAtualizando Model ComentarioProcesso\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(comentarioprocesso__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        ComentarioProcesso.objects.filter(pessoa_id=pessoa.id).update(vinculo=dic[pessoa.id], skip_history=True)


def migrar_fk_requerimento_Digitalizado_compartilhamento(apps, dic):
    Pessoa = apps.get_model('rh.Pessoa')
    RequerimentoDigitalizadoCompartilhamento = apps.get_model('processo_eletronico.RequerimentoDigitalizadoCompartilhamento')
    print("\nAtualizando Model RequerimentoDigitalizadoCompartilhamento\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(requerimentodigitalizadocompartilhamento__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        RequerimentoDigitalizadoCompartilhamento.objects.filter(pessoa_id=pessoa.id).update(vinculo_id=dic[pessoa.id], skip_history=True)


def migrar_fk_tramite(apps, dic):
    Pessoa = apps.get_model('rh.Pessoa')
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    Tramite = apps.get_model('processo_eletronico.Tramite')

    print("\nAtualizando Model Tramite\n")

    print("\n\t\tAtualizando Model Tramite - Pessoa Recebimento\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(tramites_recebidos_pessoa__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        Tramite.objects.filter(pessoa_recebimento_id=pessoa.id).update(recebido_por=dic[pessoa.id], skip_history=True)

    print("\n\t\tAtualizando Model Tramite - Atualizando Remetente\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(tramites_remetente__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        Tramite.objects.filter(remetente_pessoa_id=pessoa.id).update(remetente_vinculo=dic[pessoa.id], skip_history=True)

    print("\n\t\tAtualizando Model Tramite - Destinatario Pessoa\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(tramites_destinatario_pessoa__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        Tramite.objects.filter(destinatario_pessoa_id=pessoa.id).update(destinatario_vinculo=dic[pessoa.id], skip_history=True)

    print("\n\t\tAtualizando Model Tramite - Atribuido para\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(tramites_pe_atribuido_para__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        Tramite.objects.filter(atribuido_para_id=pessoa.id).update(vinculo_atribuido_para=dic[pessoa.id], skip_history=True)

    print("\n\t\tAtualizando Model Tramite - Atribuido por\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(tramites_pe_atribuido_por__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        Tramite.objects.filter(atribuido_por_id=pessoa.id).update(vinculo_atribuido_por=dic[pessoa.id], skip_history=True)


def migrar_fk_tramite_distribuicao(apps, dic):
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    TramiteDistribuicao = apps.get_model('processo_eletronico.TramiteDistribuicao')
    print("\nAtualizando Model TramiteDistribuicao\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(atribuir_tramite_para__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        TramiteDistribuicao.objects.filter(pessoa_para_distribuir_id=pessoa.id).update(distribuir_para=dic[pessoa.id], skip_history=True)


def migrar_fk_solicitacoes_ciencia(apps, dic):
    Pessoa = apps.get_model('rh.Pessoa')
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    SolicitacaoCiencia = apps.get_model('processo_eletronico.SolicitacaoCiencia')
    #
    print("\nAtualizando Model SolicitacaoCiencia\n")
    print("\n\t\tAtualizando Model SolicitacaoCiencia - Solicitado\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(processo_eletronico_solicitacaociencia_solicitado_a__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoCiencia.objects.filter(solicitado_id=pessoa.id).update(solicitado_vinculo=dic[pessoa.id], skip_history=True)
    #
    print("\n\t\tAtualizando Model SolicitacaoCiencia - Cancelado\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(processo_eletronico_solicitacaociencia_cancelada_por__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoCiencia.objects.filter(cancelada_por_id=pessoa.id).update(vinculo_cancelada_por=dic[pessoa.id], skip_history=True)


def migrar_fk_solicitacoes_juntada(apps, dic):
    Pessoa = apps.get_model('rh.Pessoa')
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    SolicitacaoJuntada = apps.get_model('processo_eletronico.SolicitacaoJuntada')
    SolicitacaoJuntadaDocumento = apps.get_model('processo_eletronico.SolicitacaoJuntadaDocumento')
    #
    print("\nAtualizando Model SolicitacaoJuntada\n")
    print("\n\t\tAtualizando Model SolicitacaoJuntada - Solicitado\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(processo_eletronico_solicitacaojuntada_solicitado_a__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoJuntada.objects.filter(solicitado_id=pessoa.id).update(solicitado_vinculo=dic[pessoa.id], skip_history=True)

    print("\n\t\tAtualizando Model SolicitacaoJuntada - Cancelado por\n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(processo_eletronico_solicitacaojuntada_cancelada_por__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoJuntada.objects.filter(cancelada_por_id=pessoa.id).update(vinculo_cancelada_por=dic[pessoa.id], skip_history=True)

    print("\nAtualizando Model SolicitacaoJuntadaDocumento\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(processo_eletronico_solicitacaojuntadadocumento_avaliado_por__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoJuntadaDocumento.objects.filter(avaliado_por_id=pessoa.id).update(vinculo_avaliado_por=dic[pessoa.id], skip_history=True)


def migrar_fk_solicitacoes_despacho(apps, dic):
    Pessoa = apps.get_model('rh.Pessoa')
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    SolicitacaoDespacho = apps.get_model('processo_eletronico.SolicitacaoDespacho')
    #
    print("\nAtualizando Model SolicitacaoDespacho\n")
    print("\n\t\tAtualizando Model SolicitacaoDespacho - Remetente Pessoa \n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(processo_eletronico_solicitacaodespacho_remetente_pessoa__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoDespacho.objects.filter(remetente_pessoa_id=pessoa.id).update(remetente_vinculo=dic[pessoa.id], skip_history=True)
    #
    print("\n\t\tAtualizando Model SolicitacaoDespacho - Solicitado  \n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(processo_eletronico_solicitacaodespacho_solicitado_a__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoDespacho.objects.filter(solicitado_id=pessoa.id).update(solicitado_vinculo=dic[pessoa.id], skip_history=True)

    print("\n\t\tAtualizando Model SolicitacaoDespacho - Destinatario Pessoa \n")
    for pessoa in tqdm.tqdm(Pessoa.objects.filter(destinatario_pessoa_tramite__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoDespacho.objects.filter(destinatario_pessoa_tramite_id=pessoa.id).update(destinatario_vinculo_tramite=dic[pessoa.id], skip_history=True)


def migrar_compartilhamentos(apps, dic):
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    CompartilhamentoProcessoEletronicoSetorPessoa = apps.get_model('processo_eletronico.CompartilhamentoProcessoEletronicoSetorPessoa')
    CompartilhamentoProcessoEletronicoPoderDeChefe = apps.get_model('processo_eletronico.CompartilhamentoProcessoEletronicoPoderDeChefe')
    CompartilhamentoProcessoEletronicoLog = apps.get_model('processo_eletronico.CompartilhamentoProcessoEletronicoPoderDeChefe')

    print("\nAtualizando Model CompartilhamentoProcessoEletronicoSetorPessoa\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(compartilhamentoprocessoeletronicosetorpessoa_pessoa_permitida_set__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(pessoa_permitida_id=pessoa.id).update(vinculo_permitido=dic[pessoa.id], skip_history=True)

    print("\nAtualizando Model CompartilhamentoProcessoEletronicoPoderDeChefe\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(compartilhamentoprocessoeletronicopoderchefe_pessoa_permitida_set__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(pessoa_permitida_id=pessoa.id).update(vinculo_permitido=dic[pessoa.id], skip_history=True)

    print("\nAtualizando Model CompartilhamentoProcessoEletronicoLog\n")
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(compartilhamentoprocessoeletronicolog_pessoa_permitida_set__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        CompartilhamentoProcessoEletronicoLog.objects.filter(pessoa_permitida_id=pessoa.id).update(vinculo_permitido=dic[pessoa.id], skip_history=True)


def migrar_pessoas_distribuir(apps, dic):
    print("\nAtualizando Model SolicitacaoAssinaturaComAnexacaoProcesso\n")
    PessoaFisica = apps.get_model('rh.PessoaFisica')
    SolicitacaoAssinaturaComAnexacaoProcesso = apps.get_model('processo_eletronico.SolicitacaoAssinaturaComAnexacaoProcesso')
    for pessoa in tqdm.tqdm(PessoaFisica.objects.filter(solicitacaoassinaturacomanexacaoprocesso__isnull=False).distinct()):
        criar_pessoa_externa(apps, dic, pessoa)
        SolicitacaoAssinaturaComAnexacaoProcesso.objects.filter(
            pessoa_para_distribuir_id=pessoa.id
        ).update(vinculo_para_distribuir=dic[pessoa.id], skip_history=True)


def migrar_fk_pessoa_para_fk_vinculo(apps, schema_editor):
    start_time_all = datetime.datetime.now()

    Vinculo = apps.get_model('comum.Vinculo')
    #
    vinculos = Vinculo.objects.all()
    dic = {vinculo.pessoa_id: vinculo.pk for vinculo in vinculos}
    #
    migrar_fk_processo(apps, dic)
    migrar_fk_requerimento_Digitalizado_compartilhamento(apps, dic)
    migrar_fk_tramite(apps, dic)
    migrar_fk_tramite_distribuicao(apps, dic)
    migrar_fk_solicitacoes_ciencia(apps, dic)
    migrar_fk_solicitacoes_despacho(apps, dic)
    migrar_fk_solicitacoes_juntada(apps, dic)
    migrar_compartilhamentos(apps, dic)
    migrar_pessoas_distribuir(apps, dic)

    #
    print(f'Total Duration: {datetime.datetime.now() - start_time_all}')


def _instalacao_vazia(apps):
    """Homolog/fresh: sem processos, dumps de sanity check são no-op."""
    try:
        return not apps.get_model('processo_eletronico', 'Processo').objects.exists()
    except Exception:
        return True


def dump_processo_eletronico_pessoa_fisica(apps, schema_editor):
    if _instalacao_vazia(apps):
        print('Skip dump pessoa_fisica: instalação sem processos')
        return
    call_command('processo_eletronico_dump_pessoafisica', executar_command_via_migration=True, directory=WORK_DIR)


def dump_processo_eletronico_vinculo(apps, schema_editor):
    if _instalacao_vazia(apps):
        print('Skip dump vinculo: instalação sem processos')
        return
    call_command('processo_eletronico_dump_vinculo', executar_command_via_migration=True, directory=WORK_DIR)


def check_dumps(apps, schema_editor):
    if _instalacao_vazia(apps):
        print('Skip check_dumps: instalação sem processos')
        return
    file1_data = pd.read_csv(f'{WORK_DIR}/processo_eletronico_pessoa_md5sum.csv')
    file2_data = pd.read_csv(f'{WORK_DIR}/processo_eletronico_vinculo_md5sum.csv')
    for row1, row2 in zip(file1_data, file2_data):
        if row1 != row2:
            print("Checkagem falhou..... Rollback........")
            raise Exception("Sanity checking failed...........")
    print("Checagem de migracao de Pessoa para Vinculo, em Processo Eletronico, executada com sucesso.")


class Migration(migrations.Migration):

    dependencies = [
        ('processo_eletronico', '0031_anexacao_termo_juntada_documentotexto'),
    ]

    state_operations = [
        migrations.CreateModel(
            name='RequerimentoDigitalizadoCompartilhamento',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requerimentodigitalizado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='processo_eletronico.requerimentodigitalizado')),
                ('pessoa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rh.pessoa')),
            ],
            options={
                'db_table': 'processo_eletronico_requerimentodigitalizado_compartilhamento',
            },
        ),
        migrations.CreateModel(
            name='ProcessoInteressado',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pessoa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rh.pessoa')),
                ('processo', djtools.db.models.ForeignKeyPlus(on_delete=django.db.models.deletion.CASCADE, to='processo_eletronico.processo')),
            ],
            options={
                'db_table': 'processo_eletronico_processo_interessados',
            },
        ),
        migrations.CreateModel(
            name='ProcessoAcompanhante',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pessoa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rh.pessoa')),
                ('processo', djtools.db.models.ForeignKeyPlus(on_delete=django.db.models.deletion.CASCADE, to='processo_eletronico.processo')),
            ],
            options={
                'db_table': 'processo_eletronico_processo_acompanhantes_processo',
            },
        ),
        migrations.AlterField(
            model_name='processo',
            name='interessados',
            field=djtools.db.models.ManyToManyFieldPlus(through='processo_eletronico.ProcessoInteressado', to='rh.Pessoa'),
        ),
        migrations.AlterField(
            model_name='processo',
            name='acompanhantes_processo',
            field=djtools.db.models.ManyToManyFieldPlus(blank=True, related_name='acompanhantes_processo', through='processo_eletronico.ProcessoAcompanhante', to='rh.Pessoa', verbose_name='Usuários Que Marcaram o Processo como Interesse'),
        ),
        migrations.AlterField(
            model_name='requerimentodigitalizado',
            name='compartilhamento',
            field=djtools.db.models.ManyToManyFieldPlus(through='processo_eletronico.RequerimentoDigitalizadoCompartilhamento', to='rh.Pessoa', verbose_name='Compartilhamento com pessoas'),
        ),
    ]

    operations = [
        migrations.RunPython(dump_processo_eletronico_pessoa_fisica),
        migrations.RenameModel(
            old_name='DocumentoDigitalizadoRequerimento',
            new_name='RequerimentoDigitalizado',
        ),
        migrations.AlterModelOptions(
            name='requerimentodigitalizado',
            options={'verbose_name': 'Requerimento Digitalizado', 'verbose_name_plural': 'Requerimentos Digitalizados'},
        ),
        migrations.RenameField(
            model_name='requerimentodigitalizado',
            old_name='compartilhamento_pessoa',
            new_name='compartilhamento',
        ),

        migrations.RenameField(
            model_name='processo',
            old_name='pessoas_acompanhando_processo',
            new_name='acompanhantes_processo',
        ),
        migrations.SeparateDatabaseAndState(state_operations=state_operations),
        migrations.RunSQL('SET CONSTRAINTS ALL IMMEDIATE;'),

        ####################################################################################################
        # Fase 1 - Alterando os campos
        ####################################################################################################
        migrations.AddField(
            model_name='comentarioprocesso',
            name='vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='compartilhamentoprocessoeletronicolog',
            name='vinculo_permitido',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_compartilhamentoprocessoeletronicolog_vinculo_permitido', to='comum.vinculo', verbose_name='Vínculo com Poder de Chefe'),
        ),
        migrations.AddField(
            model_name='compartilhamentoprocessoeletronicopoderdechefe',
            name='vinculo_permitido',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_compartilhamentoprocessoeletronicopoderdechefe_vinculo_permitido', to='comum.vinculo', verbose_name='Vinculo com Poder de Chefe'),
        ),
        migrations.AddField(
            model_name='compartilhamentoprocessoeletronicosetorpessoa',
            name='vinculo_permitido',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_compartilhamentoprocessoeletronicosetorpessoa_vinculo_permitido', to='comum.vinculo', verbose_name='Vinculo Colaboradoro'),
        ),
        migrations.AddField(
            model_name='processoacompanhante',
            name='vinculo',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='processointeressado',
            name='vinculo',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='requerimentodigitalizadocompartilhamento',
            name='vinculo',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaociencia',
            name='solicitado_vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaociencia_solicitado_ao_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaociencia',
            name='vinculo_cancelada_por',
            field=djtools.db.models.ForeignKeyPlus(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaociencia_cancelada_pelo_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaodespacho',
            name='destinatario_vinculo_tramite',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='destinatario_vinculo_tramite', to='comum.vinculo', verbose_name='Pessoa de Destino de Trâmite'),
        ),
        migrations.AddField(
            model_name='solicitacaodespacho',
            name='remetente_vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaodespacho_remetente_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaodespacho',
            name='solicitado_vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaodespacho_solicitado_ao_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaojuntada',
            name='solicitado_vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaojuntada_solicitado_ao_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaojuntada',
            name='vinculo_cancelada_por',
            field=djtools.db.models.ForeignKeyPlus(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaojuntada_cancelada_pelo_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='solicitacaojuntadadocumento',
            name='vinculo_avaliado_por',
            field=djtools.db.models.ForeignKeyPlus(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='processo_eletronico_solicitacaojuntadadocumento_avaliado_pelo_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='tramite',
            name='destinatario_vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_destinatario_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='tramite',
            name='recebido_por',
            field=djtools.db.models.ForeignKeyPlus(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_recebidos_por', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='tramite',
            name='remetente_vinculo',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_remetente_vinculo', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='tramite',
            name='vinculo_atribuido_para',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_atribuidos_para', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='tramite',
            name='vinculo_atribuido_por',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_atribuidos_por', to='comum.vinculo'),
        ),
        migrations.AddField(
            model_name='tramitedistribuicao',
            name='distribuir_para',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='distribuir_tramite_para', to='comum.vinculo', verbose_name='Distribuir para'),
        ),
        migrations.AlterField(
            model_name='tramite',
            name='atribuido_para',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_pe_atribuido_para', to='rh.pessoafisica'),
        ),
        migrations.AlterField(
            model_name='tramite',
            name='atribuido_por',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_pe_atribuido_por', to='rh.pessoafisica'),
        ),
        migrations.AlterField(
            model_name='tramite',
            name='destinatario_pessoa',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_destinatario_pessoa', to='rh.pessoa'),
        ),
        migrations.AlterField(
            model_name='tramite',
            name='destinatario_setor',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_destinatario_setor', to='rh.setor'),
        ),
        migrations.AlterField(
            model_name='tramite',
            name='pessoa_recebimento',
            field=djtools.db.models.ForeignKeyPlus(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_recebidos_pessoa', to='rh.pessoa'),
        ),
        migrations.AlterField(
            model_name='tramite',
            name='remetente_setor',
            field=djtools.db.models.ForeignKeyPlus(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='tramites_remetente_setor', to='rh.setor'),
        ),
        migrations.AddField(
            model_name="solicitacaoassinaturacomanexacaoprocesso",
            name="vinculo_para_distribuir",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="comum.vinculo",
                verbose_name="Distribuir para",
            ),
        ),
        ####################################################################################################
        # Fase 2 - migrando
        ####################################################################################################
        migrations.RunPython(migrar_fk_pessoa_para_fk_vinculo),
        migrations.RunSQL('SET CONSTRAINTS ALL DEFERRED;'),
        migrations.RunPython(dump_processo_eletronico_vinculo),
        migrations.RunPython(check_dumps)

    ]
