from behave import when


@when('olho para o objetivo estratégico do planejamento "{objetivo_nome}"')
def step_objetivo_estrategico(context, objetivo_nome):
    xpath_objetivo = (
        f'//div[contains(@class, "general-box") and descendant::div[contains(@class, "primary-info") and h4[contains(text(), "{objetivo_nome}")]]]'
    )
    my_xpath = context.xpath
    my_xpath.xpath = xpath_objetivo
    assert my_xpath.get()

    context.xpath.contexto = xpath_objetivo
