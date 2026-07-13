"""Shared requests session with optional proxy support."""
import os
import requests


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
    })
    proxy = os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY')
    if proxy:
        session.proxies = {'http': proxy, 'https': proxy}
        no_proxy = os.getenv('NO_PROXY', '')
        if no_proxy:
            session.proxies['no'] = no_proxy
    return session
