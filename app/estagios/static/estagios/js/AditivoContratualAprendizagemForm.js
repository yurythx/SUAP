function configurar_form(){
    var tipos = $('input[name="tipos_aditivo"]');

    // orientador
    if($(tipos[0]).is(":checked")){
        exibir('[name=orientador]');
    } else {
        esconder('[name=orientador]');
    }

    // monitor
    if($(tipos[2]).is(":checked")){
        exibir('[name=nome_monitor]');
        exibir('[name=cpf_monitor]');
        exibir('[name=telefone_monitor]');
        exibir('[name=cargo_monitor]');
        exibir('[name=email_monitor]');
        exibir('[name=observacao_monitor]');
    } else {
        esconder('[name=nome_monitor]');
        esconder('[name=cpf_monitor]');
        esconder('[name=telefone_monitor]');
        esconder('[name=cargo_monitor]');
        esconder('[name=email_monitor]');
        esconder('[name=observacao_monitor]');
    }

    // turno
    if($(tipos[3]).is(":checked")){
        exibir('[name=turno]');
    } else {
        esconder('[name=turno]');
    }

    // tempo
    if($(tipos[1]).is(":checked")){
        exibir('[name=controla_tempo]');
    } else {
        esconder('[name=controla_tempo]');
    }

    // filial
    if($(tipos[4]).is(":checked")){
        exibir('[name=empresa]');
        exibir('[name=cidade]');
        exibir('[name=logradouro]');
        exibir('[name=numero]');
        exibir('[name=complemento]');
        exibir('[name=bairro]');
        exibir('[name=cep]');
    } else {
        esconder('[name=empresa]');
        esconder('[name=cidade]');
        esconder('[name=logradouro]');
        esconder('[name=numero]');
        esconder('[name=complemento]');
        esconder('[name=bairro]');
        esconder('[name=cep]');
    }
}

function exibir(seletor){
    $(seletor).closest('fieldset').show();
}

function esconder(seletor){
    $(seletor).closest('fieldset').hide();
}

jQuery(document).ready(function(){
    configurar_form();

    $('input[name="tipos_aditivo"]').change(function() {
        configurar_form();
    });
});
