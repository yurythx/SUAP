Coisas a Fazer ou a Analizar
============================
save_session_cache
Ao analisar o código foi observado algumas utilizações que devem ser melhor trabalhada. Assim, iremos listar
todos os itens para, em um segundo momento, poder avaliar com mais cuidado.

- Verificar importos do djtools para comum
- Normalizar a utilização de cache:
    - djtools.utils.save_session_cache
    - djtools.utils.get_session_cache
    - djtools.utils.get_cache
- djtools.utils.years_between
    - Usar timedelta?
- djtools.utils.db_is_postgres
    - Verificar pois mudou o driver de utilização no settings
- djtools.utils.imprimir_percentual
    - Usar o tqdm?
- djtools.utils.class_herdar
    - Qual a utilidade?
- djtools.utils.html_email_template
    - HTML fixo? Utilizar template?
- djtools.utils.send_notification
    - Import para comum

