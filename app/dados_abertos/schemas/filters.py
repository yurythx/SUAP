from ninja import FilterSchema


class AnoFilter(FilterSchema):
    ano: int


class MesAnoFilter(FilterSchema):
    ano: int
    mes: int | None = None
