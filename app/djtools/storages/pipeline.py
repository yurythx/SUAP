import hashlib
import os

from django.conf import settings
from pipeline.storage import PipelineStorage

CACHED_NAMES = {}


class CacheControlPipelineStorage(PipelineStorage):
    def url(self, name):
        absolute_path = os.path.join(settings.STATIC_ROOT, name)
        if name not in CACHED_NAMES:
            if os.path.exists(absolute_path) and os.path.isfile(absolute_path):
                with open(absolute_path, 'rb') as f:
                    hash = hashlib.md5(f.read()).hexdigest()
                    CACHED_NAMES[name] = f'{super().url(name)}?v={hash}'
            else:
                CACHED_NAMES[name] = super().url(name)
        return CACHED_NAMES[name]
