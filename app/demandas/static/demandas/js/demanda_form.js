(function ($) {
    if (typeof $ === 'undefined') {
        return;
    }


    $(document).ready(function () {
        try {
            // Função para atualizar módulos (tags) baseado na área selecionada
            function atualizarModulos() {
                // Usar o atributo name ao invés de ID (pois o ID é dinâmico com Select2)
                var areaField = $('select[name="area"]');

                if (!areaField.length) {
                    return;
                }

                // Salvar seleção atual de tags
                var salvarSelecaoTags = function () {
                    var tags_selecionadas = [];
                    $('input[name="tags"]:checked').each(function () {
                        tags_selecionadas.push($(this).val());
                    });
                    return tags_selecionadas;
                };

                // Restaurar seleção de tags
                var restaurarSelecaoTags = function (tags_selecionadas) {
                    tags_selecionadas.forEach(function (tag_id) {
                        $('input[name="tags"][value="' + tag_id + '"]').prop('checked', true);
                    });
                };

                // Função para carregar módulos
                var carregarModulos = function () {
                    var areaId = areaField.val();

                    if (!areaId) {
                        $('#id_tags').empty();
                        return;
                    }

                    var tagsSelecionadas = salvarSelecaoTags();

                    // Fazer requisição AJAX
                    $.ajax({
                        url: '/demandas/ajax/get_tags_area/',
                        data: {
                            'area_id': areaId
                        },
                        dataType: 'json',
                        success: function (data) {
                            // Tentar encontrar o container de diferentes formas
                            var container = $('#id_tags');

                            // Se não encontrar, tentar outras alternativas
                            if (container.length === 0) {
                                // Tentar encontrar pelo campo input de tags
                                var tagsInput = $('input[name="tags"]').first();

                                if (tagsInput.length > 0) {
                                    // Procurar o container pai (pode ser ul, div, etc)
                                    container = tagsInput.closest('ul, div.checkbox-multiple-widget, div[class*="tags"], div[class*="modulos"]');

                                    // Se ainda não encontrou, pegar o parent direto
                                    if (container.length === 0) {
                                        container = tagsInput.parent().parent();
                                    }
                                }

                                // Última tentativa: procurar pela label "Módulos"
                                if (container.length === 0) {
                                    var modulosLabel = $('label:contains("Módulos")');

                                    if (modulosLabel.length > 0) {
                                        container = modulosLabel.next();
                                    }
                                }
                            }

                            if (container.length > 0) {
                                container.empty();

                                // Garantir que o container seja uma UL com a classe correta
                                if (!container.is('ul')) {
                                    var ul = $('<ul id="id_tags" class="checkboxes"></ul>');
                                    container.replaceWith(ul);
                                    container = ul;
                                } else if (!container.hasClass('checkboxes')) {
                                    container.addClass('checkboxes');
                                }

                                if (data.tags && data.tags.length > 0) {
                                    $.each(data.tags, function (index, tag) {
                                        var li = $('<li></li>');
                                        var label = $('<label></label>');
                                        label.attr('for', 'id_tags_' + index);


                                        var checkbox = $('<input type="checkbox" name="tags">');
                                        checkbox.attr('value', tag.id);
                                        checkbox.attr('id', 'id_tags_' + index);

                                        label.append(checkbox);
                                        label.append('\n ' + tag.nome);
                                        li.append(label);
                                        container.append(li);
                                    });

                                    // Restaurar seleção anterior se existir
                                    restaurarSelecaoTags(tagsSelecionadas);
                                } else {
                                    container.append('<li class="false">Nenhum módulo disponível para esta área.</li>');
                                }
                            }
                        },
                        error: function (xhr, status, error) {
                            console.error('Erro ao carregar módulos:', error);
                            console.error('Status:', status);
                            console.error('Response:', xhr.responseText);
                        }
                    });
                };

                // Evento de mudança - usar evento do Select2
                areaField.on('select2:select', function (e) {
                    carregarModulos();
                });

                // Também escutar o evento change padrão como fallback
                areaField.on('change', function (e) {
                    carregarModulos();
                });

                // Carregar módulos inicialmente (ou limpar se não houver área)
                carregarModulos();
            }

            // Aguardar um pouco para garantir que o Select2 já foi inicializado
            setTimeout(function () {
                atualizarModulos();
            }, 500);

        } catch (error) {
            console.error('[ERRO] demanda_form.js:', error);
        }
    });
})(django.jQuery);
