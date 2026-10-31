from ninja import Schema

from cnpq.models import ProducaoBibliografica


class ProducaoBibiograficaOut(Schema):
    titulo: str
    autor: str
    campus: str
    tipo: str
    # Lattes e ORCID são do servidor do IFRN dono do currículo de onde a produção foi extraída,
    # não necessariamente de quem aparece em `autor` (o primeiro autor declarado no Lattes).
    lattes_servidor_ifrn: str
    orcid_servidor_ifrn: str | None

    @staticmethod
    def resolve_autor(obj):
        autor = obj.autores.all().order_by('ordem').first()
        return autor and autor.nome_completo or 'não informado'

    @staticmethod
    def resolve_campus(obj):
        try:
            return obj.curriculo.vinculo.setor.uo.nome
        except Exception:
            return 'não informado'

    @staticmethod
    def resolve_tipo(obj):
        return obj.get_tipo()

    @staticmethod
    def resolve_lattes_servidor_ifrn(obj: ProducaoBibliografica) -> str:
        return f'http://lattes.cnpq.br/{obj.curriculo.numero_identificador}'

    @staticmethod
    def resolve_orcid_servidor_ifrn(obj: ProducaoBibliografica) -> str | None:
        try:
            return obj.curriculo.vinculo.pessoa.pessoafisica.orcid
        except Exception:
            return None
