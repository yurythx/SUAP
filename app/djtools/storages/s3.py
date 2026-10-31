import os

from botocore.config import Config
from django.conf import settings
from pipeline.storage import PipelineMixin
from storages.backends.s3boto3 import S3Boto3Storage

__all__ = [
    'MediaS3Storage',
    'PrivateS3Storage',
    'S3PipelineStorage',
    'TemporaryS3Storage',
    'download_media_content_s3',
    'download_temporary_content_s3',
    'upload_media_s3',
    'upload_temporary_s3',
]


class CustomS3Boto3Storage(S3Boto3Storage):
    config = Config(
        connect_timeout=600,
        read_timeout=600,
    )


class S3PipelineStorage(PipelineMixin, CustomS3Boto3Storage):
    bucket_name = getattr(settings, 'AWS_STATIC_BUCKET_NAME', 'static')

    def post_process(self, paths, dry_run=False, **options):
        super_class = super()
        if hasattr(super_class, 'post_process'):
            yield from super_class.post_process(paths.copy(), dry_run, **options)
        for item in settings.PIPELINE['STYLESHEETS'].values():
            for relative_path in item['source_filenames']:
                absolute_path = os.path.join(settings.BASE_DIR, 'djtools/static', relative_path)
                if absolute_path.endswith('.scss'):
                    css_absolute_path = absolute_path.replace('.scss', '.css')
                    if os.path.exists(css_absolute_path):
                        os.unlink(css_absolute_path)


class MediaS3Storage(CustomS3Boto3Storage):
    bucket_name = getattr(settings, 'AWS_MEDIA_BUCKET_NAME', 'media')
    file_overwrite = False


class PrivateS3Storage(CustomS3Boto3Storage):
    location = 'private-media/'
    bucket_name = getattr(settings, 'AWS_PRIVATE_MEDIA_BUCKET_NAME', 'media')
    file_overwrite = False


class TemporaryS3Storage(CustomS3Boto3Storage):
    bucket_name = getattr(settings, 'AWS_TEMP_BUCKET_NAME', 'temp')
    file_overwrite = False


def upload_media_s3(full_local_path, relative_remote_path, file_overwrite=False):
    storage = MediaS3Storage(file_overwrite=file_overwrite)
    with open(full_local_path, 'rb') as f:
        file_path = storage.save(relative_remote_path, f)
    return file_path


def download_media_content_s3(relative_remote_path):
    storage = MediaS3Storage()
    with storage.open(relative_remote_path) as f:
        content = f.read()
    return content


def upload_temporary_s3(file_path):
    storage = TemporaryS3Storage()
    with open(file_path, 'rb') as f:
        file_path = storage.save(file_path.split('/')[-1], f)
    return file_path


def download_temporary_content_s3(file_path):
    storage = TemporaryS3Storage()
    with storage.open(file_path) as f:
        content = f.read()
    return content
