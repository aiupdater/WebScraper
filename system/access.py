"""Rozpoznání blokace bez ukládání cookies, CAPTCHA tokenů nebo celého HTML."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AccessProblem:
    code: str
    message: str
    manual: bool = False


def detect_access_problem(status, headers, html):
    headers = {k.lower(): v for k, v in headers.items()}
    action = headers.get('x-amzn-waf-action', '').lower()
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    title = re.sub(r'\s+', ' ', title_match[1]).strip().lower() if title_match else ''
    content = html.lower()
    aws_captcha = 'captcha.awswaf.com/' in content and 'captchascript.rendercaptcha' in content
    if action == 'captcha' or aws_captcha or title in ('human verification', 'robot check'):
        return AccessProblem('CAPTCHA_REQUIRED', 'Server požaduje ruční ověření člověka v prohlížeči.', True)
    if action == 'challenge' or title.startswith(('just a moment', 'okamžik', 'einen moment')):
        return AccessProblem('BROWSER_CHALLENGE', 'Server zobrazuje ochranné ověření v prohlížeči.', True)
    if status in (401, 403) or title in ('access denied', 'request blocked', 'forbidden'):
        return AccessProblem('ACCESS_DENIED', f'Přístup zamítnut (HTTP {status}). Požadavky byly zastaveny.')
    if status == 429:
        after = headers.get('retry-after', '')
        suffix = f' Server žádá čekat: {after[:80]}.' if after else ''
        return AccessProblem('RATE_LIMITED', 'Server omezuje počet požadavků.' + suffix)
    if status >= 400:
        detail = '; Allow: ' + headers['allow'][:100] if headers.get('allow') else ''
        return AccessProblem('HTTP_ERROR', f'HTTP {status}{detail}')
    return None
