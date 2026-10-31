from django.forms.widgets import (
    HiddenInput,
)
from django.utils.safestring import mark_safe


class PhotoCaptureInput(HiddenInput):
    def render(self, name, value, attrs=None, renderer=None):
        s = f"""

        <div align="center">
            <video autoplay style="display:none;"></video>
            <canvas id="canvas" width="300" height="400"></canvas>
            <br>
            <input type="button" id="cancel" value="Cancelar" class="btn default">
            &nbsp;&nbsp;
            <input type="button" id="snapshot" value="Fotografar" class="btn primary">
        </div>

        <script language='javascript'>
        var video = document.querySelector("video");
        var canvas = document.querySelector("canvas");
        var canvas_visible = canvas.offsetParent != null;
        var ctx = canvas.getContext('2d');
        var t;
        var c = 0;

        if (canvas_visible){{
            navigator.getUserMedia = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia || navigator.msGetUserMedia || navigator.oGetUserMedia;

            if (navigator.getUserMedia) {{
            navigator.getUserMedia({{video: true}}, handleVideo, videoError);
            }}
        }}

        function handleVideo(stream) {{
            video.srcObject = stream;
        }}

        function videoError(e) {{
            ctx.font="20px Georgia";
            ctx.fillText("Nenhuma camera encontrada!",10,50);
        }}
        function crop(){{
            var sourceX = 200;
            var sourceY = 0;
            var sourceWidth = 300;
            var sourceHeight = 400;
            var destWidth = sourceWidth;
            var destHeight = sourceHeight;
            var destX = canvas.width / 2 - destWidth / 2;
            var destY = canvas.height / 2 - destHeight / 2;

            ctx.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight, destX, destY, destWidth, destHeight);
        }}
        function snapshot() {{
            if(c == 0){{
            crop();
            t = setTimeout("snapshot()", 100);
            }}
        }}

        if (canvas_visible){{
            document.querySelector('#snapshot').onclick = function() {{
            if(c == 0){{
                c = 1;
                crop();
                clearTimeout(t);
                var dataURL = canvas.toDataURL();
                hidden = document.querySelector("#id_{name}");
                hidden.value=dataURL;
            }}
            }}
            document.querySelector('#cancel').onclick = function() {{
            if(c == 1){{
                c = 0;
                snapshot();
            }}
            }}
            snapshot();
        }}
        </script>
        """
        return mark_safe(s) + super().render(name, value, attrs)


class PhotoCapturePortraitInput(HiddenInput):
    def render(self, name, value, attrs=None, renderer=None):
        s = f"""
            <div align="center">
                <video autoplay style="display:none;"></video>
                <canvas id="canvas" width="300" height="400"></canvas>
                <br>
                <input type="button" id="cancel" value="Cancelar" class="btn default">
                &nbsp;&nbsp;
                <input type="button" id="snapshot" value="Fotografar" class="btn primary">
            </div>
            <br>
            <script language='javascript'>
                var video = document.querySelector("video");
                var canvas = document.querySelector("canvas");
                var canvas_visible = canvas.offsetParent != null;
                var ctx = canvas.getContext('2d');
                var t;
                var c = 0;

                if (canvas_visible){{
                    navigator.getUserMedia = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia || navigator.msGetUserMedia || navigator.oGetUserMedia;

                    if (navigator.getUserMedia) {{
                        navigator.getUserMedia({{video: true}}, handleVideo, videoError);
                    }}
                }}

                function handleVideo(stream) {{
                    video.srcObject = stream;
                }}

                function videoError(e) {{
                    ctx.font="20px Georgia";
                    ctx.fillText("Nenhuma camera encontrada!",10,50);
                }}
                function crop(){{
                    var sourceX = 200;
                    var sourceY = 0;
                    var sourceWidth = 300;
                    var sourceHeight = 400;
                    var destWidth = sourceWidth;
                    var destHeight = sourceHeight;
                    var destX = canvas.width / 2 - destWidth / 2;
                    var destY = canvas.height / 2 - destHeight / 2;

                    ctx.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight, destX, destY, destWidth, destHeight);
                }}
                function snapshot() {{
                    if(c == 0){{
                        crop();
                        t = setTimeout("snapshot()", 100);
                    }}
                }}

                if (canvas_visible){{
                    document.querySelector('#snapshot').onclick = function() {{
                        if(c == 0){{
                            c = 1;
                            crop();
                            clearTimeout(t);
                            var dataURL = canvas.toDataURL();
                            hidden = document.querySelector("#id_{name}");
                            hidden.value=dataURL;
                        }}
                    }}
                    document.querySelector('#cancel').onclick = function() {{
                        if(c == 1){{
                            c = 0;
                            snapshot();
                        }}
                    }}
                    snapshot();
                }}
            </script>
        """
        return mark_safe(s) + super().render(name, value, attrs)


class Image(HiddenInput):
    def render(self, name, value, attrs=None, renderer=None):
        s = f"""
                <div class="form-row">
                    <div class="field-box-first">
                        <label>{self.label}:</label>
                        <img src="{self.url_image}"/>
                    </div>
                </div>
        """

        return mark_safe(s) + super().render(name, value, attrs)
