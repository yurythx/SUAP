import tqdm
from django.db import migrations

# setores_adicionais (M2M) fica de fora de CAMPOS_ATUALIZADOS: é copiado via bulk_create do through, não por bulk_update.
CAMPOS_ATUALIZADOS = ['email_pessoal', 'sistema_origem', 'foto', 'raca', 'povo_indigena', 'deficiencia']

# Tamanho do lote para o iterator/bulk_update. Ajuste conforme memória/latência.
BATCH = 2000

# ponytail: backfill em lote (bulk_update) numa transação única (RunPython é atômico). O bulk_update reduz
# drasticamente o nº de queries vs save() por linha, mas a transação/lock ainda cobre a tabela toda —
# rodar em janela de manutenção. Se a Vinculo for enorme a ponto do lock incomodar, quebrar em lotes com
# atomic=False (commit por lote) — perde a atomicidade em troca de locks curtos.
#
# RUNBOOK / RISCO DE DEPLOY: este backfill percorre Vinculo. Pessoas SEM nenhum Vinculo NÃO são copiadas —
# após o RemoveField (rh/0102), os dados legados (email/foto/raca/etc.) dessas pessoas são perdidos. É
# trade-off inerente à decisão "acesso só via vínculo do papel" (pessoa sem papel não tem onde guardar/ler
# o dado). ANTES DO DEPLOY: auditar órfãos, ex.:
#   Pessoa.objects.filter(vinculo__isnull=True).exclude(email='')  # (idem foto/email_secundario/etc.)
# e decidir: aceitar a perda conscientemente OU criar vínculo/preservar o dado antes de migrar.


def _obter_dominios(apps):
    """Obtém os domínios de email do LDAP (configuração)"""
    Configuracao = apps.get_model('comum', 'Configuracao')
    return list(
        Configuracao.objects.filter(
            chave__in=['dominio_institucional', 'dominio_academico', 'dominio_google_classroom'], app='ldap_backend'
        ).values_list('valor', flat=True)
    )


def _eh_email_institucional(email, dominios):
    """True se o email termina com algum dos domínios institucionais."""
    return email and any(email.endswith(f'@{dominio}') for dominio in dominios)


def _copiar_campos_escalares(apps, dominios):
    """email/sistema_origem (Pessoa) + foto/raca/... (PessoaFisica) via bulk_update em lotes.

    select_related('pessoa__pessoafisica') evita o N+1 na leitura da PessoaFisica.
    """
    Vinculo = apps.get_model('comum', 'Vinculo')
    lote = []
    count = Vinculo.objects.count()
    qs = Vinculo.objects.select_related('pessoa__pessoafisica').iterator(chunk_size=BATCH)
    for vinculo in tqdm.tqdm(qs, desc='copiando campos escalares', total=count):
        pessoa = vinculo.pessoa
        if not _eh_email_institucional(pessoa.email_secundario, dominios):
            vinculo.email_pessoal = pessoa.email_secundario
        if not vinculo.email_pessoal and not _eh_email_institucional(pessoa.email, dominios):
            vinculo.email_pessoal = pessoa.email
        vinculo.sistema_origem = pessoa.sistema_origem
        # hasattr(pessoa, 'pessoafisica') é o idioma já usado em Pessoa.__str__; com select_related não gera query.
        pf = pessoa.pessoafisica if hasattr(pessoa, 'pessoafisica') else None
        if pf is not None:
            vinculo.foto = pf.foto.name if pf.foto else None
            vinculo.raca_id = pf.raca_id
            vinculo.povo_indigena_id = pf.povo_indigena_id
            vinculo.deficiencia_id = pf.deficiencia_id
        lote.append(vinculo)
        if len(lote) >= BATCH:
            Vinculo.objects.bulk_update(lote, CAMPOS_ATUALIZADOS, batch_size=BATCH)
            lote.clear()
    if lote:
        Vinculo.objects.bulk_update(lote, CAMPOS_ATUALIZADOS, batch_size=BATCH)
    # AddField (0114) deixa foto='' como default; normaliza '' -> NULL (ambos significam "sem foto").
    Vinculo.objects.filter(foto='').update(foto=None)


def _copiar_setores_adicionais(apps):
    """M2M setores_adicionais: copia o through de Pessoa -> Vinculo com um bulk_create.

    A tabela pessoa.setores_adicionais é pequena, então materializar seus pares é barato.
    """
    from collections import defaultdict

    Vinculo = apps.get_model('comum', 'Vinculo')
    Pessoa = apps.get_model('rh', 'Pessoa')
    ThroughVinculo = Vinculo._meta.get_field('setores_adicionais').remote_field.through
    ThroughPessoa = Pessoa._meta.get_field('setores_adicionais').remote_field.through

    setores_por_pessoa = defaultdict(list)
    for pessoa_id, setor_id in tqdm.tqdm(
        ThroughPessoa.objects.values_list('pessoa_id', 'setor_id').iterator(),
        desc='materializando setores_adicionais',
        total=ThroughPessoa.objects.count(),
    ):
        setores_por_pessoa[pessoa_id].append(setor_id)
    if not setores_por_pessoa:
        return

    novos = []
    pares_vinculo = Vinculo.objects.filter(pessoa_id__in=setores_por_pessoa.keys()).values_list('id', 'pessoa_id')
    for vinculo_id, pessoa_id in tqdm.tqdm(
        pares_vinculo.iterator(), desc='copiando setores_adicionais', total=Vinculo.objects.filter(pessoa_id__in=setores_por_pessoa.keys()).count()
    ):
        for setor_id in setores_por_pessoa[pessoa_id]:
            novos.append(ThroughVinculo(vinculo_id=vinculo_id, setor_id=setor_id))
    ThroughVinculo.objects.bulk_create(novos, batch_size=BATCH, ignore_conflicts=True)


def copiar_campos_para_vinculo(apps, schema_editor):
    """Backfill dos campos de Pessoa/PessoaFisica para o Vinculo (1:1), em lote."""
    dominios = _obter_dominios(apps)
    _copiar_campos_escalares(apps, dominios)
    _copiar_setores_adicionais(apps)


def limpar_campos_vinculo(apps, schema_editor):
    """Reverse: zera os campos migrados (UPDATE set-based) e limpa o M2M."""
    Vinculo = apps.get_model('comum', 'Vinculo')
    ThroughVinculo = Vinculo._meta.get_field('setores_adicionais').remote_field.through
    Vinculo.objects.update(
        email_pessoal='',
        sistema_origem='',
        foto=None,
        raca=None,
        povo_indigena=None,
        deficiencia=None,
    )
    ThroughVinculo.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('comum', '0114_vinculo_campos_pessoa'),
    ]

    operations = [
        migrations.RunPython(copiar_campos_para_vinculo, limpar_campos_vinculo),
    ]
