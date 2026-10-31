from terminais.models import Release


class ReleaseService:
    @staticmethod
    def criar_release(versao, descricao, manifest, activo=False):
        release = Release.objects.create(
            versao=versao,
            descricao=descricao,
            manifest=manifest,
        )
        return release

    @staticmethod
    def adicionar_artefato(release, componente, url, checksum):
        artefato = release.artefatos.create(componente=componente, url=url, checksum=checksum)
        return artefato

    @staticmethod
    def get_release(versao):
        return Release.objects.filter(versao=versao).first()

    @staticmethod
    def get_release_ativa():
        return Release.objects.filter(activo=True).first()
