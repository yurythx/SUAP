   $(document).ready(function() {
            function toggleFields() {
                if ($('#id_categoria').val() === 'aluno') {
                    $(".form-row.aluno").show();
                    $(".form-row.servidor").hide();
                    $("select[name='servidor']").prop("value", "");
                    $("select[name='servidor']").val("");
                    $("select[name='servidor']").prop("val", "");
                    $("select[name='servidor']").trigger('change');
                } else {
                    $(".form-row.aluno").hide();
                    $("select[name='aluno']").prop("value", "");
                    $("select[name='aluno']").val("");
                    $("select[name='aluno']").prop("val", "");
                    $("select[name='aluno']").trigger('change');
                    $(".form-row.servidor").show();
                }
            }
            toggleFields();
            // Adiciona um listener para chamar a função quando o valor da categoria mudar
            $('#id_categoria').change(toggleFields);
        });
