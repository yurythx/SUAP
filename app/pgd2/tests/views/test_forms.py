from pgd2.forms import AvaliacaoRitForm


class AvaliacaoRitFormTest:
    def test_rejects_tempo_homologado_when_seconds_exceed_integer_field_limit(self):
        form = AvaliacaoRitForm(
            data={
                'avaliacao_rit': '1',
                'justificativa': '',
                'tempo_homologado': '596.523,24',
                'confirmacao': 'on',
                'senha': '123',
            }
        )

        assert not form.is_valid()
        assert 'tempo_homologado' in form.errors
