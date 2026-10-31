(function () {
    // register plugin
    CKEDITOR.plugins.add('blockimagepaste', {
        init: function (editor) {
            editor.on('paste', function (e) {
                var html = e.data.dataValue;
                if (!html) return;
                // Replace data: images in Firefox and upload them
                e.data.dataValue = html.replace(/<img( [^>]*)?>/gi, function (img) {
                    alert('Não é permitido colar imagens no editor.');
                    return '';
                });
            });
        }
    });
})();
