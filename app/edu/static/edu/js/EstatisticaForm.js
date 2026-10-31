jQuery(function () {
    var html = $("<a class='btn' style='margin: 5px; margin-left: 70px' onclick='$(this).parent().find(\"input\").prop(\"checked\", !$(this).parent().find(\"input\").prop(\"checked\"));'>Marcar/Desmacar Todos</a>");
    $('.excluir_proitec').parent().append(html);
});