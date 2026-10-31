class Nacionalidade:
    BRASILEIRO_NATO = 1
    BRASILEIRO_NATZ = 2
    EQUIPARADO = 3
    ESTRANGEIRO = 4

    NACIONALIDADE_DICT = {
        BRASILEIRO_NATO: 'Brasileiro Nato',
        BRASILEIRO_NATZ: 'Brasileiro Naturalizado',
        EQUIPARADO: 'Equiparado',
        ESTRANGEIRO: 'Estrangeiro',
    }

    @classmethod
    def get_choices(cls):
        return [[x, y] for x, y in cls.NACIONALIDADE_DICT.items()]


class TipoExtracao:
    TIPO_EXTRATOR_SIAPE = 1
    TIPO_WEBSERVICE = 2
    TIPO_SISTEMA = 3
    TIPO_EXTRACAO_CHOICE = {TIPO_EXTRATOR_SIAPE: 'Extrator SIAPE', TIPO_WEBSERVICE: 'Webservice', TIPO_SISTEMA: 'Sistema'}

    @classmethod
    def get_choices(cls):
        return [[k, v] for k, v in cls.TIPO_EXTRACAO_CHOICE.items()]
