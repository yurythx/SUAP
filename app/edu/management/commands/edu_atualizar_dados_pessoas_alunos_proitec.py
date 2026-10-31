import datetime

import tqdm

from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno
from processo_seletivo.models import Edital


def atualizar_dados(aluno, dados):
    if dados['sexo']:
        aluno.pessoa_fisica.sexo = dados['sexo']

    if dados['data_nascimento']:
        aluno.pessoa_fisica.nascimento_data = datetime.datetime.strptime(dados['data_nascimento'], '%d/%m/%Y')

    if dados['email_pessoal']:
        v = aluno.get_vinculo()
        if v:
            v.email_pessoal = dados['email_pessoal']
            v.save(update_fields=['email_pessoal'])

    if dados['estado_civil']:
        aluno.estado_civil = dados['estado_civil']

    if dados['tipo_sanguineo']:
        aluno.tipo_sanguineo = dados['tipo_sanguineo']

    if dados['nome_mae']:
        aluno.nome_mae = dados['nome_mae']

    if dados['nome_pai']:
        aluno.nome_pai = dados['nome_pai']

    if dados['responsavel']:
        aluno.responsavel = dados['responsavel']

    if dados['parentesco_responsavel']:
        aluno.parentesco_responsavel = dados['parentesco_responsavel']

    if dados['logradouro']:
        aluno.logradouro = dados['logradouro']

    if dados['numero']:
        aluno.numero = dados['numero']

    if dados['complemento']:
        aluno.complemento = dados['complemento']

    if dados['bairro']:
        aluno.bairro = dados['bairro']

    if dados['cidade']:
        aluno.cidade = dados['cidade']

    if dados['cep']:
        aluno.cep = dados['cep']

    if dados['telefone_principal']:
        aluno.telefone_principal = dados['telefone_principal']

    if dados['telefone_secundario']:
        aluno.telefone_secundario = dados['telefone_secundario']

    if dados['numero_rg']:
        aluno.numero_rg = dados['numero_rg']

    if dados['uf_emissao_rg']:
        aluno.uf_emissao_rg_id = dados['uf_emissao_rg']

    if dados['orgao_emissao_rg']:
        aluno.orgao_emissao_rg_id = dados['orgao_emissao_rg']

    if dados['data_emissao_rg']:
        aluno.data_emissao_rg = datetime.datetime.strptime(dados['data_emissao_rg'], '%d/%m/%Y')

    if dados['linha_pesquisa']:
        aluno.linha_pesquisa = dados['linha_pesquisa']

    if dados['tipo_zona_residencial']:
        aluno.tipo_zona_residencial = dados['tipo_zona_residencial']

    if dados['naturalidade']:
        aluno.naturalidade = dados['naturalidade']

    if dados['nacionalidade']:
        aluno.nacionalidade = dados['nacionalidade']

    aluno.save()
    aluno.pessoa_fisica.save()
    if dados['raca']:
        v = aluno.get_vinculo()
        if v:
            v.raca = dados['raca']
            v.save(update_fields=['raca'])


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        edital = Edital.objects.get(pk=447)
        qs = Aluno.objects.filter(candidato_vaga__oferta_vaga__oferta_vaga_curso__edital=edital)
        for aluno in tqdm.tqdm(qs):
            dados = edital.consultar_candidato(aluno.candidato_vaga)
            atualizar_dados(aluno, dados)
