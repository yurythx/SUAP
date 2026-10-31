class DemandasException(Exception):
    pass


class DemandaDespriorizadaException(DemandasException):
    def __init__(self):
        mensagem = [
            'Esta demanda não pode ser despriorizada pois já foi iniciada.',
            'Caso deseje despriorizar mesmo assim, faça um comentário na mesma solicitando a suspensão da demanda.',
        ]
        super().__init__(' '.join(mensagem))
