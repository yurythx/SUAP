class Servidor:
    """
    Sobrescrevendo o método get_titulação do modelo Servidor
    """

    def get_titulacao(self):
        return 'LPS Titulacao'

    """
    Sobrescrevendo __str__ onde tinha:
        Xico / 1111111 ---> Xixo - 1111111
    """

    def __str__(self):
        return f'{self.nome} - {self.matricula}'
