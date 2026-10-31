Checklist de verificações
-Valores das variáveis do módulo de gestão
-Comando de importação dos dados dos alunos do Q-Acadêmico
-Comando de importação das digitais dos alunos do Siabi
-Comando de importação das fotos dos alunos
-Área restrita do aluno
-Funcionalidades gerais do módulo de assitência estudantil
-Exportação dos alunos para o terminal do refeitório (/ae/get_pessoas/) 
-Exportação dos alunos para o campus EAD (/edu/alunos_ws/?campus=XXX)

Dúvidas (Ver com Túlio)
-view indicadores em tempo real OK
-view exportar dados acadêmico (Gugu)
-view exportar alunos acadêmico (Gugu)
-funcao importar_xls() em academico.importacao.importador.py OK
-tabelas: OK
	academico_atuacaodisciplina
	academico_atuacaodisciplinagrupo
	academico_atuacaodocente
	academico_atuacaoeixo
academico_configuracaogestao

Usuário utilizados nos testes com Prof. Alessandro
131	Administrador EDU -> Ribamar Oliveira 	(271865)
133	Coordenador EDU -> Matheus Amorim (1584889)
134	Diretor EDU -> Alessandro Souza (2488657)
132	Pedagogo EDU -> Ana Lucia Pascoal Diniz (1674090)
135	Secretário EDU -> Emiliano (1672960)


git pull origin edu-5
pg_dump -U postgres suap_dev -f suapdev3edu.sql
psql -U postgres -c "create database suapdev3edu;"
psql -U postgres -d suapdev3edu -f suapdev3edu.sql
rm suapdev3edu.sql
psql -U postgres -d suapdev3edu -c "ALTER TABLE "unidadeorganizacional" ADD COLUMN "fax" varchar(255) NULL ; ALTER TABLE "unidadeorganizacional" ADD COLUMN "cep" varchar(255) NULL ; ALTER TABLE "unidadeorganizacional" ADD COLUMN "telefone" varchar(255) NULL ; ALTER TABLE "unidadeorganizacional" ADD COLUMN "endereco" varchar(255) NULL ;"
python manage.py drop_app edu
python manage.py sync
python manage.py edu_realizar_migracao
python manage.py edu_importar_professores
python manage.py edu_importar_sistec
#supervisorctl restart suapdev3