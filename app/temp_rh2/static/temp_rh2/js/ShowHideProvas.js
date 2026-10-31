$(document).ready(function () {
    function calcular_modalidades() {
        var valores_marcados = [];
        $('input:checkbox[name=modalidades]:checked').each(function () {
            valores_marcados.push($(this).val());
        });
        if (valores_marcados.includes('8')) {
            $('.form-row.provas_atletismo').show();
        } else {
            $('.form-row.provas_atletismo').hide();
            $('input:checkbox[name=provas_atletismo]:checked').each(function () {
                $(this).prop('checked', false);
            });
        }
        if (valores_marcados.includes('9')) {
            $('.form-row.provas_natacao').show();
        } else {
            $('.form-row.provas_natacao').hide();
            $('input:checkbox[name=provas_natacao]:checked').each(function () {
                $(this).prop('checked', false);
            });
        }
        if (valores_marcados.includes('25')) {
            $('.form-row.provas_jogos_eletronicos').show();
        } else {
            $('.form-row.provas_jogos_eletronicos').hide();
            $('input:checkbox[name=provas_jogos_eletronicos]:checked').each(function () {
                $(this).prop('checked', false);
            });
        }
    }

    calcular_modalidades();
    $("input[type='checkbox']").click(function () {
        calcular_modalidades();
    });
});
