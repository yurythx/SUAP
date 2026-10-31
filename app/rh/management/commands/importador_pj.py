import csv
import io
import os

from pycpfcnpj import cpfcnpj

from comum.models import Municipio, PessoaEndereco, PessoaTelefone
from djtools.management.commands import BaseCommandPlus
from djtools.utils import mask_cnpj
from rh.models import PessoaJuridica


class Command(BaseCommandPlus):
    def insert_pj(self, pj_csv):
        errors = []
        list_pj = list(csv.DictReader(pj_csv, delimiter=';'))

        row = len(list_pj) > 0 and list_pj[0] or None

        if (
            row
            and 'nome' in row
            and 'cnpj' in row
            and 'endereco' in row
            and 'bairro' in row
            and 'telefone_fixo' in row
            and 'cep' in row
            and 'cidade' in row
            and 'uf' in row
        ):
            flag_erros = 0
            for row in list_pj:
                if row['cnpj'] == 'NULL' or not cpfcnpj.validate(row['cnpj']):
                    errors.append('[{}] não possui CNPJ válido.'.format(row['nome'].decode('utf-8')))

                else:
                    cnpj = mask_cnpj(row['cnpj'])

                    qs_PJ = PessoaJuridica.objects.filter(cnpj=cnpj)
                    pessoa = qs_PJ.exists() and qs_PJ[0] or None
                    if pessoa is None:
                        pessoaPJ = PessoaJuridica()
                        pessoaPJ.cnpj = cnpj
                        pessoaPJ.nome = row['nome'].decode('utf-8')
                        pessoaPJ.save()
                    else:
                        if flag_erros == 0:
                            errors.append('')
                        errors.append(
                            '[{} - CNPJ:{}] não foi importado pois este CNPJ já está cadastrado no SUAP.'.format(row['nome'].decode('utf-8'), cnpj)
                        )
                        flag_erros += 1
                        continue

                    qs_last = PessoaJuridica.objects.filter(cnpj=cnpj)
                    last = qs_last.exists() and qs_last[0] or None

                    if row['endereco'].decode('utf-8') == 'NULL':
                        endereco = None
                    else:
                        endereco = row['endereco'].decode('utf-8')

                    if row['bairro'].decode('utf-8') == 'NULL':
                        bairro = None
                    else:
                        bairro = row['bairro'].decode('utf-8')

                    if row['cep'].decode('utf-8') == 'NULL':
                        cep = None
                    else:
                        cep = row['cep'].decode('utf-8')

                    if row['cidade'].decode('utf-8') == 'NULL' or row['uf'].decode('utf-8') == 'NULL':
                        municipio = None
                    else:
                        municipio = Municipio.get_or_create(nome=row['cidade'].decode('utf-8'), uf=row['uf'].decode('utf-8'))[0]

                    PessoaEndereco.objects.get_or_create(
                        pessoa_id=last.id, logradouro=endereco, numero='', complemento='', bairro=bairro, municipio=municipio, cep=cep
                    )

                    if row['telefone_fixo'] != 'NULL':
                        telefone = row['telefone_fixo']
                        PessoaTelefone.objects.create(pessoa_id=last.id, numero=telefone)

        else:
            errors.append(
                'Nenhuma Pessoa Jurídica foi cadastrada pois o arquivo CSV está vázio ou inválido. Verifique se ele foi criado corretamente.'
            )
        return errors

    def handle(self, *args, **options):
        pj_csv = (
            'pj' in options and options['pj'] is not None and io.StringIO(options['pj'].read()) or os.path.isfile('pj.csv') and open('pj.csv') or None
        )

        errors = []

        if pj_csv:
            errors.extend(self.insert_pj(pj_csv))

        errors_str = '<br />\n'.join(errors)
        try:
            print(errors_str)
        except Exception:
            pass

        return errors_str
