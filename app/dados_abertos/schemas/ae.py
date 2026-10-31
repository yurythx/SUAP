from ninja import Schema


class AuxilioOut(Schema):
    tipo_do_auxilio: str
    quantidade_de_beneficiarios: int
    valor_executado: float | None
