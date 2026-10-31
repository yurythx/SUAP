$(document).ready(function() {
    const tipoRespondenteField = $('#id_tipo_respondente');
    const matriculaField = $('input[name="matricula"]');
    const cpfField = $('input[name="cpf"]');
    const cnpjField = $('input[name="cnpj"]');
    const form = $('form');
    const emailField = $('input[name="email"]');

    function toggleFields() {
        const tipoRespondente = tipoRespondenteField.val();

        emailField.prev().removeClass('required');

        if (matriculaField.length) {
            matriculaField.closest('.form-row').hide();
            matriculaField.prev().removeClass('required');
            matriculaField.val('');  // Limpa o campo
        }
        if (cpfField.length) {
            cpfField.closest('.form-row').hide();
            cpfField.prev().removeClass('required');
            cpfField.val('');  // Limpa o campo
        }
        if (cnpjField.length) {
            cnpjField.closest('.form-row').hide();
            cnpjField.prev().removeClass('required');
            cnpjField.val('');  // Limpa o campo
        }

        if (tipoRespondente === '10') { // Pais
            matriculaField.closest('.form-row').show();
            matriculaField.prev().addClass('required');
        } else if (['9', '13'].includes(tipoRespondente)) { // Aluno Egresso e Profissional Prestador
            cpfField.closest('.form-row').show();
            cpfField.prev().addClass('required');
        } else if (tipoRespondente === '11') { // Empresa Prestadora de Serviço
            cnpjField.closest('.form-row').show();
            cnpjField.prev().addClass('required');
        } else if (tipoRespondente === '14') { // Supervisor de estágio
            emailField.prev().addClass('required');
        }
    }

    tipoRespondenteField.on('change', toggleFields);
    toggleFields(); // Inicializa com os campos corretos exibidos/ocultos

    function verificaRespondente(event) {
        event.preventDefault();
        const tipo_respondente = tipoRespondenteField.val();
        const email = emailField.val();
        const matricula = matriculaField.val();
        const cpf = cpfField.val();
        const cnpj = cnpjField.val();
        const token = $('input[name="token"]').val();
        const tokenRespodente = $('input[name="token_respondente"]'); // Campo oculto para "confirmar_exclusao"

        // Verifica se pelo menos um dos campos tem valor
        if (matricula || cpf || cnpj || email) {
            // Fazer a requisição para verificar os dados via POST
            // Fazer a requisição para verificar os dados via POST
            $.ajax({
                url: '/avaliacao_integrada/respondente_externo_check/',
                method: 'POST',
                headers: {
                    'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() // CSRF token para segurança
                },
                data: {
                    'tipo_respondente': tipo_respondente,
                    'email': email,
                    'matricula': matricula,
                    'cpf': cpf,
                    'cnpj': cnpj,
                    'token': token
                },
                success: function(data) {
                    if (data.segmento_diferente) {
                        if (data.mensagem_erro) {
                            console.log(data.mensagem_erro);
                            // Verifica se já existe um feedback anterior e remove
                            $('#feedback_message').remove();

                            // Insere a mensagem de erro no corpo
                            $('body').prepend(`
                                <p class="errornote" id="feedback_message">
                                    ${data.mensagem_erro}
                                </p>
                            `);
                        } else if (confirm(data.mensagem_aviso)) {
                            // Se confirmado a exclusão, passa o token_respondente, o qual possui
                            // o id do respondente.
                            tokenRespodente.val(data.token_respondente);

                            // Remove o handler de submit para evitar loop
                            form.off('submit');
                            form.submit(); // Submete o formulário
                        } else {
                            form.on('submit');
                        }
                    } else {
                        // Submete diretamente se não houver dados existentes
                        form.off('submit'); // Remove o handler para evitar loop
                        form.submit();
                    }
                },
                error: function(error) {
                    console.error('Erro ao verificar os dados:', error);
                    form.off('submit'); // Remove o handler para evitar loop
                    form.submit();  // Submete o formulário mesmo se houver erro no AJAX
                }
            });
        } else {
            // Se nenhum campo tiver valor, apenas submete o formulário
            form.off('submit'); // Remove o handler para evitar loop
            form.submit();
        }
    }

    form.on('submit', verificaRespondente);
});
