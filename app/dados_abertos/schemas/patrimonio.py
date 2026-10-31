from ninja import Schema


class InventarioSchema(Schema):
    numero: int
    descricao: str
    status: str
    estado_conservacao: str
    valor_inicial: float
    valor: float
    campus: str

    @staticmethod
    def resolve_valor_inicial(inventario):
        return inventario.entrada_permanente.valor

    @staticmethod
    def resolve_campus(inventario):
        return inventario.carga_contabil.campus.sigla

    @staticmethod
    def resolve_status(inventario):
        return inventario.status.nome
