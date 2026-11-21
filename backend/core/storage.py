"""
Django storage backend for Vercel Blob.

Used for uploaded media (profile pictures) when BLOB_READ_WRITE_TOKEN is set;
see STORAGES in settings.py. Talks to the same HTTP API as the official
@vercel/blob SDK, so it only needs `requests`.

Files are stored in a *public* Blob store with a random suffix appended to each
pathname, so URLs are unguessable. The value saved in the database is the blob
pathname (e.g. "profile_pictures/jane-Ab12Cd.jpg"); `url()` turns it into the
full https URL, which is what the web and mobile apps receive from the API.
"""

import mimetypes
import os
from urllib.parse import quote

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

API_URL = os.getenv('VERCEL_BLOB_API_URL', 'https://vercel.com/api/blob').rstrip('/')
API_VERSION = '13'
TIMEOUT = 60


def _store_id_from_token(token):
    # Token format: vercel_blob_rw_<storeId>_<secret>
    parts = token.split('_')
    if len(parts) < 5:
        raise ValueError('BLOB_READ_WRITE_TOKEN has an unexpected format.')
    return parts[3]


@deconstructible
class VercelBlobStorage(Storage):
    def __init__(self, token=None, base_url=None):
        self.token = token or os.getenv('BLOB_READ_WRITE_TOKEN', '')
        if not self.token:
            raise ValueError('BLOB_READ_WRITE_TOKEN is not set.')
        self.store_id = _store_id_from_token(self.token)
        self.base_url = (
            base_url
            or os.getenv('BLOB_BASE_URL')
            or f'https://{self.store_id.lower()}.public.blob.vercel-storage.com'
        ).rstrip('/')

    # -- helpers ---------------------------------------------------------

    def _headers(self, extra=None):
        headers = {
            'authorization': f'Bearer {self.token}',
            'x-api-version': API_VERSION,
            'x-vercel-blob-store-id': self.store_id,
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _raise_for_error(response, action):
        if response.ok:
            return
        try:
            error = response.json().get('error', {})
            detail = f"{error.get('code')}: {error.get('message')}"
        except ValueError:
            detail = response.text[:300]
        raise IOError(f'Vercel Blob {action} failed ({response.status_code}): {detail}')

    # -- Storage API -----------------------------------------------------

    def _save(self, name, content):
        name = name.replace('\\', '/').lstrip('/')
        content_type = (
            getattr(content, 'content_type', None)
            or mimetypes.guess_type(name)[0]
            or 'application/octet-stream'
        )
        if hasattr(content, 'seek'):
            content.seek(0)
        body = content.read()

        response = requests.put(
            f'{API_URL}/?pathname={quote(name)}',
            data=body,
            headers=self._headers({
                'x-vercel-blob-access': 'public',
                'x-content-type': content_type,
                'x-add-random-suffix': '1',
            }),
            timeout=TIMEOUT,
        )
        self._raise_for_error(response, 'upload')
        return response.json()['pathname']

    def _open(self, name, mode='rb'):
        response = requests.get(self.url(name), timeout=TIMEOUT)
        self._raise_for_error(response, 'download')
        return ContentFile(response.content, name=name)

    def delete(self, name):
        if not name:
            return
        response = requests.post(
            f'{API_URL}/delete',
            json={'urls': [self.url(name)]},
            headers=self._headers({'content-type': 'application/json'}),
            timeout=TIMEOUT,
        )
        self._raise_for_error(response, 'delete')

    def exists(self, name):
        # Every upload gets a random suffix, so a new name never collides.
        return False

    def url(self, name):
        if name.startswith('http://') or name.startswith('https://'):
            return name
        return f"{self.base_url}/{quote(name.lstrip('/'))}"

    def size(self, name):
        response = requests.head(self.url(name), timeout=TIMEOUT)
        self._raise_for_error(response, 'stat')
        return int(response.headers.get('content-length', 0))
