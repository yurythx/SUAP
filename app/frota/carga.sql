-- insere os registros de grupos de viaturas
 

INSERT INTO frota_viaturagrupo
            (codigo, nome, descricao)
            VALUES ('I', 'Veículos de representação', 'Representação oficial'),
                   ('II', 'Veículos especiais', 'Ex-Presidentes da República nos termos da Lei 7.474/86 e atividades peculiares do Ministério das Relações Exteriores e Comandos Militares, não alcançadas pelo art.3o'),
                   ('III', 'Veículos de transporte institucional', 'Autoridades em serviço'),
                   ('IV', 'Veículos de serviços comuns', 'Pessoal a serviço/carga e realização de atividades específicas'),
                   ('V', 'Veículos de serviços especiais', 'Realização de atividades de segurança pública, saúde pública, fiscalização, segurança nacional e coleta de dados'); 

-- insere os status das viaturas
INSERT INTO frota_viaturastatus
            (descricao)
            VALUES ('Disponível'),
                   ('Em Trânsito'),
                   ('Em Manutenção');
                   
