import re
import unicodedata

from django.db import models

from djtools.assincrono import task
from edu.models import EixoTecnologico
from pnp.forms import ImportarMatriculaPNPForm
from pnp.matching import IndiceDeAlunos, resolver_aluno
from pnp.models import AreaTematicaPNP, EixoPNP, EstruturaPNP, MatriculaPNP, ServidorPNP
from rh.models import AreaConhecimento, Servidor, UnidadeOrganizacional

LIMITE_DE_ITENS_NO_RELATORIO = 50
TAMANHO_DO_LOTE = 2000


def normalizar(nome: str) -> str:
    """Normaliza o nome de uma unidade para comparação, ignorando acento, pontuação e caixa."""
    texto = unicodedata.normalize('NFKD', str(nome)).encode('ascii', 'ignore').decode().upper()
    return ' '.join(re.sub(r'[^A-Z0-9]+', ' ', texto).split())


def normalizar_matricula(matricula: str) -> str:
    """Normaliza a matrícula SIAPE, que a PNP exporta com zeros à esquerda e o SUAP registra sem."""
    return re.sub(r'\D', '', str(matricula)).lstrip('0')


def indexar_por_nome(registros, campo: str) -> dict[str, models.Model]:
    """Indexa os registros pelo nome normalizado, descartando as chaves ambíguas."""
    indice = {}
    ambiguas = set()
    for registro in registros:
        chave = normalizar(getattr(registro, campo))
        if chave in indice:
            ambiguas.add(chave)
        indice[chave] = registro
    return {chave: registro for chave, registro in indice.items() if chave not in ambiguas}


def get_lista_html(itens: list[str]) -> str:
    """Monta uma lista HTML dos itens, truncada para não gerar um relatório impraticável."""
    exibidos = '</li><li>'.join(itens[:LIMITE_DE_ITENS_NO_RELATORIO])
    restantes = len(itens) - LIMITE_DE_ITENS_NO_RELATORIO
    sufixo = f'<p>+{restantes} não listado(s).</p>' if restantes > 0 else ''
    return f'<ul><li>{exibidos}</li></ul>{sufixo}'


def vincular(registro: models.Model, campo: str, alvo: models.Model | None) -> bool:
    """Grava o vínculo derivado no registro, mantendo o atual se o alvo já pertencer a outro registro."""
    if alvo is None or getattr(registro, f'{campo}_id') == alvo.pk:
        return False
    if type(registro).objects.filter(**{campo: alvo}).exclude(pk=registro.pk).exists():
        return False
    setattr(registro, campo, alvo)
    registro.save()
    return True


def get_mensagem_estruturas(criadas: int, vinculadas: int, sem_vinculo: list[str]) -> str:
    """Monta o relatório HTML exibido ao final da importação de estruturas."""
    msg = f'{criadas} estrutura(s) cadastrada(s) e {vinculadas} vinculada(s) a uma unidade organizacional.'
    if sem_vinculo:
        msg += (
            '<br><br>As estruturas abaixo foram cadastradas sem unidade organizacional, porque nenhuma '
            f'unidade foi localizada pelo nome informado pela PNP. Informe a unidade manualmente: <br>{get_lista_html(sem_vinculo)}'
        )
    return msg


@task('Importando estruturas da PNP')
def importar_estruturas(estruturas: list[list[str]], task=None) -> None:
    unidades = indexar_por_nome(UnidadeOrganizacional.objects.uo(), 'nome')
    criadas = vinculadas = 0
    sem_vinculo = []
    for codigo, nome in task.iterate(estruturas):
        uo = unidades.get(normalizar(nome))
        estrutura, criada = EstruturaPNP.objects.update_or_create(codigo=codigo, defaults={'nome': nome})
        criadas += criada
        vinculadas += vincular(estrutura, 'uo', uo)
        if not estrutura.uo_id:
            sem_vinculo.append(f'{nome} ({codigo})')
    return task.finalize(get_mensagem_estruturas(criadas, vinculadas, sem_vinculo), '..')


def get_mensagem_eixos(criados: int, vinculados: int, sem_vinculo: list[str]) -> str:
    """Monta o relatório HTML exibido ao final da importação de eixos."""
    msg = f'{criados} eixo(s) cadastrado(s) e {vinculados} vinculado(s) a um eixo tecnológico.'
    if sem_vinculo:
        msg += (
            '<br><br>Os itens abaixo foram cadastrados sem eixo tecnológico, porque nenhum eixo foi '
            'localizado pelo nome informado pela PNP. Os subeixos entram aqui, já que o SUAP não os '
            f'cadastra. Informe o eixo manualmente onde couber: <br>{get_lista_html(sem_vinculo)}'
        )
    return msg


@task('Importando eixos da PNP')
def importar_eixos(eixos: list[list[str]], task=None) -> None:
    tecnologicos = indexar_por_nome(EixoTecnologico.objects.all(), 'descricao')
    criados = vinculados = 0
    sem_vinculo = []
    for codigo, nome in task.iterate(eixos):
        tecnologico = tecnologicos.get(normalizar(nome))
        eixo, criado = EixoPNP.objects.update_or_create(codigo=codigo, defaults={'nome': nome})
        criados += criado
        vinculados += vincular(eixo, 'eixo_tecnologico', tecnologico)
        if not eixo.eixo_tecnologico_id:
            sem_vinculo.append(f'{nome} ({codigo})')
    return task.finalize(get_mensagem_eixos(criados, vinculados, sem_vinculo), '..')


def normalizar_codigo_area(codigo: str) -> str:
    """Converte o código do CNPq do formato da PNP (1.03.00.00-7) para o do SUAP (10300007)."""
    return re.sub(r'\D', '', str(codigo))


def get_mensagem_areas(criadas: int, vinculadas: int, sem_vinculo: list[str]) -> str:
    """Monta o relatório HTML exibido ao final da importação de áreas temáticas."""
    msg = f'{criadas} área(s) temática(s) cadastrada(s) e {vinculadas} vinculada(s) a uma área do conhecimento.'
    if sem_vinculo:
        msg += (
            '<br><br>As áreas abaixo foram cadastradas sem área do conhecimento, porque o código '
            f'informado pela PNP não existe na tabela do SUAP. Informe a área manualmente: <br>{get_lista_html(sem_vinculo)}'
        )
    return msg


@task('Importando áreas temáticas da PNP')
def importar_areas_tematicas(areas: list[list[str]], task=None) -> None:
    conhecidas = {a.codigo: a for a in AreaConhecimento.objects.all()}
    criadas = vinculadas = 0
    sem_vinculo = []
    for codigo, nome in task.iterate(areas):
        area_conhecimento = conhecidas.get(normalizar_codigo_area(codigo))
        area, criada = AreaTematicaPNP.objects.update_or_create(codigo=codigo, defaults={'nome': nome})
        criadas += criada
        vinculadas += vincular(area, 'area', area_conhecimento)
        if not area.area_id:
            sem_vinculo.append(f'{nome} ({codigo})')
    return task.finalize(get_mensagem_areas(criadas, vinculadas, sem_vinculo), '..')


def ler_parquet(caminho: str, colunas: tuple[str, ...]) -> list[dict]:
    """Lê do storage temporário o arquivo que o formulário guardou para esta importação."""
    # ponytail: import tardio, pyarrow é pesado e só é usado nas importações da PNP
    import pyarrow.parquet as pq

    from djtools.storages.utils import cache_file, get_temp_storage

    local = cache_file(caminho, remote_storage=get_temp_storage())
    linhas = pq.read_table(local, columns=list(colunas)).to_pylist()
    return [{coluna: str(linha[coluna]).strip() for coluna in colunas} for linha in linhas]


def gravar_matriculas(linhas: list[dict]) -> int:
    """Grava os dados brutos das linhas, sem tocar nos vínculos já existentes."""
    registros = [MatriculaPNP(**linha) for linha in linhas]
    MatriculaPNP.objects.bulk_create(
        registros,
        update_conflicts=True,
        unique_fields=['matricula'],
        update_fields=['nome', 'cpf', 'curso', 'unidade', 'codigo_estrutura'],
    )
    return len(registros)


def gravar_vinculos(vinculos: dict[str, tuple[int | None, int | None]]) -> int:
    """Grava os vínculos derivados apenas nos registros que ainda não têm o seu."""
    pendentes = MatriculaPNP.objects.filter(matricula__in=vinculos).only('matricula', 'aluno', 'estrutura')
    alterados = []
    vinculados = 0
    for registro in pendentes:
        aluno_id, estrutura_id = vinculos[registro.matricula]
        mudou = False
        if aluno_id and not registro.aluno_id:
            registro.aluno_id = aluno_id
            vinculados += 1
            mudou = True
        if estrutura_id and not registro.estrutura_id:
            registro.estrutura_id = estrutura_id
            mudou = True
        if mudou:
            alterados.append(registro)
    MatriculaPNP.objects.bulk_update(alterados, ['aluno', 'estrutura'])
    return vinculados


def get_mensagem_matriculas(gravadas: int, vinculadas: int, sem_vinculo: list[str]) -> str:
    """Monta o relatório HTML exibido ao final da importação de matrículas."""
    msg = f'{gravadas} matrícula(s) importada(s) e {vinculadas} vinculada(s) a um aluno do SUAP.'
    if sem_vinculo:
        msg += (
            f'<br><br>{len(sem_vinculo)} matrícula(s) ficaram sem aluno, porque o CPF não existe no SUAP ou porque '
            'o curso informado pela PNP não identificou qual dos cursos da pessoa é o desta matrícula. '
            f'Informe o aluno manualmente: <br>{get_lista_html(sem_vinculo)}'
        )
    return msg


@task('Importando matrículas da PNP')
def importar_matriculas(caminho: str, task=None) -> None:
    linhas = ler_parquet(caminho, ImportarMatriculaPNPForm.COLUNAS)
    indice = IndiceDeAlunos()
    gravadas = vinculadas = 0
    sem_vinculo = []
    lotes = [linhas[i : i + TAMANHO_DO_LOTE] for i in range(0, len(linhas), TAMANHO_DO_LOTE)]
    for lote in task.iterate(lotes):
        vinculos = {}
        for linha in lote:
            aluno_id = resolver_aluno(linha, indice)
            if aluno_id:
                indice.ja_vinculados.add(aluno_id)
            else:
                sem_vinculo.append(f'{linha["nome"][:80]} ({linha["matricula"]})')
            vinculos[linha['matricula']] = (aluno_id, indice.estrutura_por_codigo.get(linha['codigo_estrutura']))
        gravadas += gravar_matriculas(lote)
        vinculadas += gravar_vinculos(vinculos)
    return task.finalize(get_mensagem_matriculas(gravadas, vinculadas, sem_vinculo), '..')


def get_mensagem_servidores(criados: int, vinculados: int, sem_vinculo: list[str], sem_estrutura: list[str]) -> str:
    """Monta o relatório HTML exibido ao final da importação de servidores."""
    msg = f'{criados} servidor(es) cadastrado(s) e {vinculados} vinculado(s) a um servidor do SUAP.'
    if sem_vinculo:
        msg += (
            '<br><br>Os servidores abaixo foram cadastrados sem vínculo, porque nenhum servidor '
            f'foi localizado pela matrícula informada pela PNP. Informe o servidor manualmente: <br>{get_lista_html(sem_vinculo)}'
        )
    if sem_estrutura:
        if not EstruturaPNP.objects.exists():
            msg += '<br><br>Nenhuma estrutura da PNP foi importada ainda, por isso nenhum servidor ficou associado a uma estrutura. Importe as estruturas e repita esta importação.'
        else:
            msg += f'<br><br>Os servidores abaixo ficaram sem estrutura, porque o código informado pela PNP não foi encontrado: <br>{get_lista_html(sem_estrutura)}'
    return msg


def get_servidores_por_matricula() -> dict[str, int]:
    """Indexa os servidores do SUAP pela matrícula normalizada, descartando as ambíguas."""
    servidores = {}
    ambiguas = set()
    for pk, matricula in Servidor.objects.values_list('id', 'matricula'):
        chave = normalizar_matricula(matricula)
        if not chave:
            continue
        if chave in servidores:
            ambiguas.add(chave)
        servidores[chave] = pk
    return {chave: pk for chave, pk in servidores.items() if chave not in ambiguas}


@task('Importando servidores da PNP')
def importar_servidores(servidores: list[list[str]], task=None) -> None:
    suap = get_servidores_por_matricula()
    estruturas = dict(EstruturaPNP.objects.values_list('codigo', 'id'))
    ja_vinculados = set(ServidorPNP.objects.filter(servidor__isnull=False).values_list('servidor_id', flat=True))
    criados = vinculados = 0
    sem_vinculo = []
    sem_estrutura = []
    for matricula, nome, cpf, unidade, codigo_estrutura in task.iterate(servidores):
        chave = normalizar_matricula(matricula)
        defaults = {'nome': nome, 'cpf': cpf, 'unidade': unidade, 'codigo_estrutura': codigo_estrutura}
        # o vínculo derivado nunca é desfeito nem transferido: só é gravado quando o alvo está livre
        if estruturas.get(codigo_estrutura):
            defaults['estrutura_id'] = estruturas[codigo_estrutura]
        servidor_id = suap.get(chave)
        if servidor_id and servidor_id not in ja_vinculados:
            defaults['servidor_id'] = servidor_id
            ja_vinculados.add(servidor_id)
            vinculados += 1
        registro, criado = ServidorPNP.objects.update_or_create(matricula=chave, defaults=defaults)
        criados += criado
        if not registro.servidor_id:
            sem_vinculo.append(f'{nome} ({matricula})')
        if not registro.estrutura_id:
            sem_estrutura.append(f'{nome} ({codigo_estrutura})')
    return task.finalize(get_mensagem_servidores(criados, vinculados, sem_vinculo, sem_estrutura), '..')
