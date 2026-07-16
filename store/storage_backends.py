"""Almacenamiento de medios en Supabase Storage (bucket Mixlaba)."""

from __future__ import annotations

import mimetypes
import os
import uuid
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


def _supabase_configured() -> bool:
    return bool(
        getattr(settings, 'SUPABASE_URL', '')
        and getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', '')
        and getattr(settings, 'SUPABASE_STORAGE_BUCKET', '')
    )


@deconstructible
class SupabaseMediaStorage(Storage):
    """Sube archivos al bucket de Supabase y devuelve la URL pública."""

    def __init__(self, bucket: str | None = None, base_url: str | None = None, service_key: str | None = None):
        self.bucket = bucket or settings.SUPABASE_STORAGE_BUCKET
        self.base_url = (base_url or settings.SUPABASE_URL).rstrip('/')
        self.service_key = service_key or settings.SUPABASE_SERVICE_ROLE_KEY
        self._fallback = FileSystemStorage(
            location=settings.MEDIA_ROOT,
            base_url=settings.MEDIA_URL,
        )

    def _use_fallback(self) -> bool:
        return not (self.base_url and self.service_key and self.bucket)

    def _normalize_name(self, name: str) -> str:
        return name.replace('\\', '/').lstrip('/')

    def _headers(self, content_type: str | None = None, upsert: bool = False) -> dict:
        headers = {
            'Authorization': f'Bearer {self.service_key}',
            'apikey': self.service_key,
        }
        if content_type:
            headers['Content-Type'] = content_type
        if upsert:
            headers['x-upsert'] = 'true'
        return headers

    def _upload_url(self, name: str) -> str:
        path = quote(self._normalize_name(name), safe='/')
        return f'{self.base_url}/storage/v1/object/{self.bucket}/{path}'

    def url(self, name: str) -> str:
        if self._use_fallback():
            return self._fallback.url(name)
        path = quote(self._normalize_name(name), safe='/')
        return f'{self.base_url}/storage/v1/object/public/{self.bucket}/{path}'

    def exists(self, name: str) -> bool:
        if self._use_fallback():
            return self._fallback.exists(name)
        response = requests.get(self.url(name), timeout=15)
        return response.status_code == 200

    def delete(self, name: str) -> None:
        if self._use_fallback():
            self._fallback.delete(name)
            return
        response = requests.delete(
            self._upload_url(name),
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()

    def size(self, name: str) -> int:
        if self._use_fallback():
            return self._fallback.size(name)
        response = requests.head(self.url(name), timeout=15)
        response.raise_for_status()
        return int(response.headers.get('Content-Length', 0))

    def _save(self, name: str, content) -> str:
        if self._use_fallback():
            return self._fallback._save(name, content)

        data = content.read()
        content_type = getattr(content, 'content_type', None) or mimetypes.guess_type(name)[0] or 'application/octet-stream'
        response = requests.post(
            self._upload_url(name),
            headers=self._headers(content_type=content_type, upsert=True),
            data=data,
            timeout=60,
        )
        if response.status_code not in (200, 201):
            response.raise_for_status()
        return name

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        directory, filename = os.path.split(self._normalize_name(name))
        base, ext = os.path.splitext(filename)
        unique_name = f'{base}-{uuid.uuid4().hex[:10]}{ext}'
        candidate = f'{directory}/{unique_name}' if directory else unique_name
        if max_length and len(candidate) > max_length:
            trim = max_length - len(unique_name) - 1
            directory = directory[:max(trim, 0)]
            candidate = f'{directory}/{unique_name}' if directory else unique_name
        return candidate

    def save(self, name, content, max_length=None):
        name = self.get_available_name(name, max_length=max_length)
        return self._save(name, content)

    def open(self, name, mode='rb'):
        if self._use_fallback():
            return self._fallback.open(name, mode)
        response = requests.get(self.url(name), timeout=30)
        response.raise_for_status()
        return ContentFile(response.content, name=name)
