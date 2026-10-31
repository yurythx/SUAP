from ninja import Schema


class DocumentoComprobatorioSchema(Schema):
    descricao: str


class ItemRequisitoSchema(Schema):
    numero: int
    titulo: str
    quantidade: str
    unidade_medida: str
    pontuacao_unidade: str
    pontuacao_total: str
    documentos: list[DocumentoComprobatorioSchema]


class RequisitoMemorialSchema(Schema):
    label: str
    descricao: str
    itens: list[ItemRequisitoSchema]


class IdentificacaoServidorSchema(Schema):
    nome: str
    siape: str
    cargo: str
    lotacao: str


class RequerimentoSchema(Schema):
    nivel_rsc_pretendido: str
    processo_anterior_id: int | None


class MemorialSecaoSchema(Schema):
    introducao: str
    requisitos: list[RequisitoMemorialSchema]


class ConclusaoSchema(Schema):
    texto: str
    resumo: str


class MemorialAvaliadoSchema(Schema):
    content_type: str = 'rsc_tae.processorsctae'
    id: int
    identificacao: IdentificacaoServidorSchema
    requerimento: RequerimentoSchema
    memorial: MemorialSecaoSchema
    conclusao: ConclusaoSchema
