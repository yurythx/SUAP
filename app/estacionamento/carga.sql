-- insere os registro na tabela de especie de veiculos
INSERT INTO estacionamento_veiculoespecie (descricao) 
    VALUES ('Carga'),('Especial'),('Misto'),('Passageiro'),('Tração');

-- insere os registro na tabela de tipo de veiculos
INSERT INTO estacionamento_veiculotipo (descricao) 
    VALUES  ('Automóvel'),
            ('Caminhão'),
            ('Caminhão-Trator'),
            ('Caminhonete'),
            ('Camioneta'),
            ('Ciclomotor'),
            ('Microônibus'),
            ('Motocicleta'),
            ('Motoneta'),
            ('Motorcasa'),
            ('Ônibus'),
            ('Quadriciclo'),
            ('Reboque'),
            ('Semi-reboque'),
            ('Trator de esteiras'),
            ('Trator de rodas'),
            ('Trator misto'),
            ('Triciclo'),
            ('Utilitário');
            
-- insere os registros de relacionamento entre especies e tipos de veiculos
INSERT INTO estacionamento_veiculotipoespecie 
            (id, tipo_id, especie_id) 
            VALUES (1, 6, 4),(2, 9, 1),(3, 9, 4),(4, 8, 1),(5, 8, 4),(6, 18, 1),(7, 18, 4),(8, 1, 2),(9, 1, 4),
                   (10, 11, 4),(11, 7, 4),(12, 13, 1),(13, 13, 2),(14, 13, 4),(15, 14, 1),(16, 14, 2),(17, 14, 4),
                   (18, 5, 2),(19, 5, 3),(20, 2, 1),(21, 2, 2),(22, 3, 5),(23, 15, 5),(24, 16, 5),(25, 17, 5),
                   (26, 12, 1),(27, 12, 4),(30, 4, 1),(31, 4, 2),(32, 19, 3),(33, 10, 2);

-- insere os registro na tabela de combustiveis de veiculos
INSERT INTO estacionamento_veiculocombustivel (nome) 
    VALUES  ('Gasolina'),
            ('Álcool'),
            ('Diesel'),
            ('Gás Natural');
  
-- DROP TABLE "estacionamento_veiculotipoespecie", "estacionamento_veiculo", "estacionamento_veiculomodelo", "estacionamento_veiculomarca", "estacionamento_veiculotipo", "estacionamento_veiculoespecie" cascade;
