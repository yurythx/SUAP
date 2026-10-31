from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Required, TypedDict

if TYPE_CHECKING:
    from comum.models import JustificativaUsuarioExterno, Municipio, Pais, PessoaEndereco, PessoaTelefone, PrestadorServico
    from rh.models import CargoEmprego, JornadaTrabalho, PessoaFisica, Servidor, Setor, Situacao, Titulacao


class PessoaFisicaCadastro(TypedDict, total=False):
    nome_registro: str
    nome_social: str
    nome_usual: str
    cpf: str
    passaporte: str
    documento_identificador: str
    nacionalidade: int
    sexo: str
    rg: str
    rg_orgao: str
    rg_data: datetime.date
    rg_uf: str
    nascimento_data: datetime.date
    nome_pai: str
    nome_mae: str
    nascimento_municipio: Municipio
    email_secundario: str
    email: str
    tem_digital_fraca: bool
    pais_origem: Pais
    fator_rh: str
    grupo_sanguineo: str
    setores_adicionais: list[Setor]
    senha_ponto: str
    template: bytes


class PessoaEnderecoCadastro(TypedDict, total=False):
    municipio: Municipio
    logradouro: str
    numero: str
    bairro: str
    complemento: str
    cep: str


class PessoaTelefoneCadastro(TypedDict):
    numero: str


class PrestadorServicoCadastro(TypedDict, total=False):
    setor: Setor
    ativo: bool
    usuario_externo: bool
    justificativa_cadastro: JustificativaUsuarioExterno
    pessoa_fisica: Required[PessoaFisicaCadastro]
    endereco: PessoaEnderecoCadastro
    telefone: PessoaTelefoneCadastro


class PrestadorServicoRetorno(TypedDict):
    prestador: PrestadorServico
    prestador_created: bool
    pessoa_fisica: PessoaFisica
    pessoa_fisica_created: bool
    endereco: PessoaEndereco | None
    endereco_created: bool
    telefone: PessoaTelefone | None
    telefone_created: bool


class ServidorCadastro(TypedDict, total=False):
    pk: int | None
    matricula: Required[str]
    setor: Setor | None
    setor_lotacao: Setor | None
    setor_exercicio: Setor | None
    titulacao: Titulacao | None
    situacao: Situacao
    ativo: Required[bool]
    pessoa_fisica: Required[PessoaFisicaCadastro]
    cargo_emprego: CargoEmprego
    jornada_trabalho: JornadaTrabalho
    data_inicio_exercicio_no_cargo: str | None
    email_siape: str
    email_institucional: str


class ServidorRetorno(TypedDict):
    servidor: Required[Servidor]
    servidor_created: Required[bool]
    pessoa_fisica: Required[PessoaFisica]
    pessoa_fisica_created: Required[bool]
