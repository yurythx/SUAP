(function($) {
    $(document).on('formset:added', function(event, $row, formsetName) {
        sync_widgets();
    });
})(django.jQuery);
