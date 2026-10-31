$(document).ready(function() {
    // --- PASSO 1: Guardar todas as opções originais na primeira vez que a página carrega ---
    const todasAsOpcoesIniciais = [];
    $('#id_campi_vinculados option').each(function() {
        todasAsOpcoesIniciais.push({
            value: $(this).val(),
            text: $(this).text(),
            title: $(this).attr('title') || $(this).text() // Guarda o title ou o texto
        });
    });

    // Agora, o seu código original, com as modificações
    $('#id_tipo_calendario').on('change', function() {
        var tipoCalendario = $(this).val();
        var nucleoId = $('select[name="nucleo_responsavel"]').val();

        if (tipoCalendario === 'sistemico' || tipoCalendario === 'nucleo_compras') {

            var requestData = {
                'tipo': tipoCalendario
            };

            if (tipoCalendario === 'nucleo_compras') {
                if (nucleoId) {
                    requestData['nucleo_id'] = nucleoId;
                } else {
                    alert('Por favor, selecione um Núcleo Responsável primeiro.');
                    $(this).val('campus');
                    return;
                }
            }

            $.ajax({
                url: '/compras/get_campi_vinculados_json/',
                data: requestData,
                dataType: 'json',
                success: function(data) {
                    var selectOriginal = $('#id_campi_vinculados');
                    var boxDisponiveis = $('#id_campi_vinculados_from');
                    var boxEscolhidos = $('#id_campi_vinculados_to');

                    // Limpa as seleções anteriores
                    selectOriginal.empty();
                    boxEscolhidos.empty();
                    boxDisponiveis.empty(); // Limpamos aqui para repopular do zero

                    // Guarda os IDs que vieram da API para uma busca rápida
                    const idsEscolhidos = new Set();
                    if (data && data.campi && data.campi.length > 0) {
                        $.each(data.campi, function(index, campus) {
                            idsEscolhidos.add(campus.id.toString()); // Adiciona o ID (como string) ao Set
                        });
                    }

                    // --- PASSO 2: Repopula as duas caixas usando a lista original ---
                    $.each(todasAsOpcoesIniciais, function(i, opcao) {
                        // Verifica se a opção da nossa lista original está na lista de escolhidos da API
                        if (idsEscolhidos.has(opcao.value)) {
                            // Se SIM, adiciona na caixa de "Escolhidos" e no select original como 'selected'
                            var optionVisivel = new Option(opcao.text, opcao.value);
                            $(optionVisivel).attr('title', opcao.title);
                            boxEscolhidos.append(optionVisivel);

                            var optionOculta = new Option(opcao.text, opcao.value, true, true);
                            $(optionOculta).attr('title', opcao.title);
                            selectOriginal.append(optionOculta);

                        } else {
                            // Se NÃO, adiciona na caixa de "Disponíveis" e no select original sem 'selected'
                            var optionVisivel = new Option(opcao.text, opcao.value);
                            $(optionVisivel).attr('title', opcao.title);
                            boxDisponiveis.append(optionVisivel);

                            var optionOculta = new Option(opcao.text, opcao.value);
                            $(optionOculta).attr('title', opcao.title);
                            selectOriginal.append(optionOculta);
                        }
                    });
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error("Erro na requisição AJAX:", textStatus, errorThrown);
                    alert("Ocorreu um erro ao buscar os campi.");
                }
            });
        }
    });
    // Chama a mesma função AJAX ao mudar o Núcleo Responsável
    $('select[name="nucleo_responsavel"]').on('change', function() {
        $('#id_tipo_calendario').trigger('change');
    });
});
