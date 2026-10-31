from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        infos = []
        infos.append(['8', 'Sítio Lagoa do Clementino, nº 999, RN 233, Km 2', 'Apodi-RN', '59700-971', '(84) 4005-4101'])
        infos.append(['7', 'RN 288, s/n, Nova Caicó', 'Caicó-RN', '59300-000', '(84) 4005-4102'])
        infos.append(['3', 'Rua Manoel Lopes Filho, nº773, Valfredo Galvão', 'Currais Novos-RN', '59380-000 ', '(84) 4005-4112'])
        infos.append(['6', 'RN 118, S/N, Povoado Base Física, Zona Rural', 'Ipanguaçu-RN', '59508-000', '(84) 4005-4104'])
        infos.append(['9', 'BR 406, Km 73, nº 3500, Perímetro Rural', 'João Câmara-RN', '59550-000', '(84) 4005-4105'])
        infos.append(['10', 'Rua das Margaridas, 300, COHAB', 'Macau-RN', '59500-000', '(84) 3521-1230'])
        infos.append(['4', 'Rua Raimundo Firmino de Oliveira, 400, Conj. Ulrick Graff', 'Mossoró-RN', '59.628-330', '(84) 3422-2652'])
        infos.append(['1', 'Avenida Senador Salgado Filho, 1559, Tirol', 'Natal-RN', '59015-000', '(84) 4005-9843'])
        infos.append(['13', 'Avenida Rio Branco, 743, Cidade Alta', 'Natal-RN', '59025-002', '(84) 4005-0950'])
        infos.append(['2', 'Rua Brusque, 2926, Conjunto Santa Catarina, Potengi', 'Natal-RN', '59112-490', '(84) 4006-9500'])
        infos.append(['16', 'Av. José Rodrigues de Aquino Filho, Nº 640, RN 120, Alto de Santa Luzia', 'Nova Cruz-RN', '59215-000', '(84) 4005-4107'])
        infos.append(['15', 'Rua Antônia de Lima Paiva, 155 - Bairro Nova Esperança', 'Parnamirim', '59143-455', '(84) 4005-4108'])
        infos.append(['11', 'BR 405, KM 154, Bairro Chico Cajá', 'Pau dos Ferros-RN', '59.900-000', '(84) 4005-4109'])
        infos.append(['12', 'Rua São Braz, 304, Bairro Paraíso', 'Santa Cruz-RN', '59200-000', '(84) 3291-4700'])
        infos.append(['17', 'Rua Alexandre Cavalcanti, S.N., Centro', 'São Gonçalo do Amarante-RN', '59290-000', '(84) 4005-4111'])
        infos.append(['14', 'Av. Senador Salgado Filho, 1559, Tirol', 'Natal-RN', '59015-000', '(84) 3092-8907'])

        from django.db import connection

        cur = connection.cursor()
        for info in infos:
            sql = f"UPDATE unidadeorganizacional set endereco = '{info[1]}', cep = '{info[3]}', telefone = '{info[4]}' WHERE id = {info[0]}"
            cur.execute(sql)
        connection._commit()
