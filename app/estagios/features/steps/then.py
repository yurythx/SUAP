from behave import then


@then('vejo o status do estágio "{status}"')
def step_impl(context, status):
    xpath_padrao = f'//span[contains(@class, "active") and contains(text(), "{status}") and ancestor::*[contains(@class, "steps")]]'

    elemento = context.xpath.find_by_xpath(xpath_padrao)

    assert len(elemento) > 0
