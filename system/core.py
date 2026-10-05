"""WebScraper: testovatelné jádro bez závislosti na GUI. Python 3.11+."""
from __future__ import annotations

import csv
import hashlib
import ipaddress
import json
import logging
import re
import socket
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, quote, urljoin, urlsplit, urlunsplit

import httpx
from filelock import FileLock, Timeout
import tldextract
from bs4 import BeautifulSoup
from system.access import detect_access_problem
from system.mysql_contacts import MySQLContacts, MySQLError, normalize_email

VERSION = 1
AGENT = 'WebScraper/1.0'
PSL = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True)
BLOCKED = {'wlw.de', '11880.com', 'visable.com', 'visable.io', 'europages.com', 'schema.org',
           'facebook.com', 'instagram.com', 'linkedin.com', 'xing.com', 'youtube.com',
           'google.com', 'gstatic.com', 'googletagmanager.com', 'twitter.com', 'x.com'}
CONTACT = re.compile(r'impressum|imprint|kontakt|contact|legal|about|o-nas', re.I)
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


class Cancelled(Exception):
    pass


class FetchError(Exception):
    def __init__(self, message, code='FETCH_ERROR'):
        super().__init__(message)
        self.code = code


class BlockingAccessError(FetchError):
    """Zastaví další návštěvy WLW; u jiných webů zůstává chybou položky."""


def error_result(exc):
    return {'status': 'ERROR', 'code': exc.code, 'detail': f'{exc.code}: {exc}'}


def host(url):
    return (urlsplit(url).hostname or '').lower().rstrip('.')


def domain(value):
    result = PSL(value)
    return result.top_domain_under_public_suffix or value.lower().removeprefix('www.')


def blocked(value):
    return any(value == d or value.endswith('.' + d) for d in BLOCKED)


def clean_url(value, base=''):
    value = urljoin(base, value.strip())
    try:
        p = urlsplit(value)
        if p.scheme.lower() not in ('http', 'https') or not p.hostname or p.username or p.password:
            return None
        h = p.hostname.encode('idna').decode().lower().rstrip('.')
        if ':' in h or '.' not in h or h.endswith(('.local', '.localhost')):
            return None
        try:
            if not ipaddress.ip_address(h).is_global:
                return None
        except ValueError:
            pass
        port = p.port
        if port not in (None, 80, 443):
            return None
        netloc = h + (f':{port}' if port and port != (443 if p.scheme == 'https' else 80) else '')
        return urlunsplit((p.scheme.lower(), netloc, p.path or '/', p.query, ''))
    except (ValueError, UnicodeError):
        return None


def profile_url(value, base='https://www.wlw.de', portal='wlw'):
    value = clean_url(value, base)
    if portal == '11880':
        if not value or host(value) not in ('11880.com', 'www.11880.com'):
            return None
        path = urlsplit(value).path
        return 'https://www.11880.com' + path if re.fullmatch(r'/branchenbuch/[^/]+/[^/]+/[^/]+\.html', path) else None
    if not value or host(value) not in ('wlw.de', 'www.wlw.de'):
        return None
    m = re.match(r'^/de/firma/([^/?#]+)', urlsplit(value).path)
    return 'https://www.wlw.de/de/firma/' + m[1] if m else None


def root_url(value):
    value = clean_url(value)
    if not value or blocked(host(value)):
        return None
    p = urlsplit(value)
    # WWW je součást skutečné adresy; odstraňuje se jen z deduplikačního klíče.
    return urlunsplit((p.scheme, p.netloc, '/', '', ''))


def site_key(value):
    return host(value).removeprefix('www.')


def search_url(query, page, portal='wlw'):
    if portal == '11880':
        if query.startswith(('https://', 'http://')):
            base = clean_url(query)
            if not base or host(base) not in ('11880.com', 'www.11880.com') or not re.fullmatch(r'/suche/[^/]+/deutschland/?', urlsplit(base).path):
                raise ValueError('Zadejte kategorii nebo 11880 URL ve tvaru /suche/Tiefbau/deutschland.')
            path = urlsplit(base).path.rstrip('/')
        else:
            path = '/suche/' + quote(query.strip(), safe='') + '/deutschland'
        return urlunsplit(('https', 'www.11880.com', path, f'page={page}' if page > 1 else '', ''))
    if query.startswith(('https://', 'http://')):
        base = clean_url(query)
        if not base or host(base) not in ('www.wlw.de', 'wlw.de') or not urlsplit(base).path.startswith('/de/suche/'):
            raise ValueError('Zadejte odvětví nebo WLW URL ve tvaru /de/suche/tiefbau.')
        parts = urlsplit(base)
        path = re.sub(r'/page/\d+/?$', '', parts.path).rstrip('/')
        params = parts.query
    else:
        slug = quote(re.sub(r'\s+', '-', query.strip().lower()), safe='-')
        path, params = '/de/suche/' + slug, ''
    if page > 1:
        path += f'/page/{page}'
    return urlunsplit(('https', 'www.wlw.de', path, params, ''))


def search_profiles(html, base, portal='wlw'):
    soup = BeautifulSoup(html, 'html.parser')
    return sorted({u for a in soup.select('a[href]') if (u := profile_url(a['href'], base, portal))})


def directory_has_next(html):
    soup = BeautifulSoup(html, 'html.parser')
    if not soup.select_one('a.entry-detail-link'):
        return None  # Neznámé HTML není potvrzeným koncem výsledků.
    button = soup.select_one('button[aria-label="Zur nächsten Seite"]')
    return bool(button and not button.has_attr('disabled') and button.get('aria-disabled') != 'true')


def directory_contact(html, profile):
    """Kontakty z hlavní vizitky 11880, bez recenzí a doporučených firem."""
    soup = BeautifulSoup(html, 'html.parser')
    pieces = [str(node) for node in soup.select('.entry-detail-list')]
    for node in soup.select('.entry-detail-list [data-cfemail]'):
        try:
            encoded = bytes.fromhex(node['data-cfemail'])
            pieces.append(bytes(value ^ encoded[0] for value in encoded[1:]).decode('utf-8'))
        except (ValueError, UnicodeError, IndexError):
            pass
    for node in soup.select('[itemprop="email"]'):
        pieces.append(node.get('content', '') or node.get_text(' ', strip=True))
    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            if isinstance(obj.get('url'), str) and profile_url(obj['url'], profile, '11880') == profile and obj.get('email'):
                values = obj['email'] if isinstance(obj['email'], list) else [obj['email']]
                pieces.extend(value for value in values if isinstance(value, str))
            for key in ('@graph', 'mainEntity'):
                if key in obj:
                    walk(obj[key])
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(node.get_text()))
        except (ValueError, TypeError):
            pass
    emails = sorted(e for e in extract_emails(' '.join(pieces)) if not blocked(e.rsplit('@', 1)[1]))
    website = website_from_profile(html, profile).get('website', '')
    return {'status': 'OK', 'website': website, 'profile_emails': emails, 'source': profile,
            'detail': 'E-maily přímo z profilu 11880.com.' if emails else 'Profil neuvádí e-mail.'}


def decode_link(value, base):
    value = urljoin(base, value)
    for key in ('url', 'u', 'target', 'redirect'):
        values = parse_qs(urlsplit(value).query).get(key)
        if values and values[0].startswith(('https://', 'http://')):
            return values[0]
    return value


def website_from_profile(html, profile):
    """Pouze explicitní webové odkazy a Organization JSON-LD; žádné URL ze skriptů."""
    soup = BeautifulSoup(html, 'html.parser')
    candidates = {}

    def add(value, confidence):
        if not isinstance(value, str):
            return
        url = clean_url(decode_link(value, profile))
        if url and not blocked(host(url)) and not re.search(r'\.(png|jpg|svg|js|css|pdf)$', urlsplit(url).path, re.I):
            candidates[url] = min(candidates.get(url, 99), confidence)

    for a in soup.select('a[href]'):
        label = ' '.join([a.get_text(' ', strip=True), a.get('title', ''),
                          a.get('aria-label', ''), str(a.get('data-testid', ''))])
        if re.search(r'website|webseite|homepage|zur\s+web|internet', label, re.I):
            add(a['href'], 0)
        elif a.get('itemprop') == 'url':
            add(a['href'], 1)

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            kinds = obj.get('@type', [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if any(t in ('Organization', 'LocalBusiness', 'Corporation', 'ProfessionalService') for t in kinds):
                add(obj.get('url'), 1)
            for item in obj.values():
                if isinstance(item, (list, dict)):
                    walk(item)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
    # Aktuální veřejné SSR HTML WLW: Nuxt pole obsahuje indexované hodnoty.
    # Přijmeme pouze homepage objektu se slugem přesně shodným s profilem.
    payload = soup.select_one('script#__NUXT_DATA__[type="application/json"]')
    if payload:
        try:
            values = json.loads(payload.get_text())
            expected = urlsplit(profile).path.rstrip('/').split('/')[-1]
            def resolve(index):
                return values[index] if type(index) is int and 0 <= index < len(values) else None
            if isinstance(values, list):
                for obj in values:
                    if isinstance(obj, dict) and resolve(obj.get('slug')) == expected:
                        add(resolve(obj.get('homepage')), 0)
        except (ValueError, TypeError, IndexError):
            pass
    if not candidates:
        return {'website': '', 'status': 'NO_WEBSITE', 'detail': 'Chybí jednoznačný odkaz na firemní web.'}
    tier = min(candidates.values())
    best = sorted(u for u, score in candidates.items() if score == tier)
    if len({site_key(u) for u in best}) > 1:
        return {'website': '', 'status': 'REVIEW', 'detail': 'Více kandidátů: ' + ' | '.join(best)}
    return {'website': min(best, key=lambda u: (not u.startswith('https:'), len(u), u)),
            'status': 'OK', 'detail': 'Webový odkaz / homepage odpovídajícího profilu' if tier == 0 else 'Strukturovaná data'}


def extract_emails(html):
    soup = BeautifulSoup(html, 'html.parser')
    pieces = []
    for a in soup.select('a[href]'):
        if a['href'].lower().startswith('mailto:'):
            pieces.append(unquote(a['href'][7:].split('?', 1)[0]))
    for item in soup(['script', 'style', 'noscript']):
        item.decompose()
    pieces.append(soup.get_text(' ', strip=True))
    text = ' '.join(pieces)
    text = re.sub(r'\s*(?:\[at\]|\(at\))\s*', '@', text, flags=re.I)
    text = re.sub(r'\s*(?:\[dot\]|\(dot\))\s*', '.', text, flags=re.I)
    found = set()
    for email in EMAIL.findall(text):
        email = email.strip('.').lower()
        local, mail_host = email.rsplit('@', 1)
        if len(email) <= 254 and len(local) <= 64 and '..' not in local and not mail_host.endswith(('.png', '.jpg', '.svg', '.webp')):
            found.add(email)
    return found


def best_email(emails, site):
    preferred = ['info', 'kontakt', 'contact', 'office', 'mail', 'service', 'support']
    same = [e for e in emails if domain(e.rsplit('@', 1)[1]) == domain(host(site))]
    def score(e):
        local = e.split('@')[0]
        return (preferred.index(local) if local in preferred else 99, e)
    return min(same, key=score) if same else ''


@dataclass
class Config:
    query: str = ''
    start_page: int = 1
    max_pages: int = 20
    workers: int = 6
    delay: float = 1.0
    timeout: float = 20.0
    contact_pages: int = 4
    input_file: str = ''
    input_kind: str = 'profiles'
    respect_robots: bool = False  # Legacy field; ignored, retained for compatibility.
    wlw_mode: str = 'browser'
    browser_channel: str = 'chromium'
    manual_timeout: float = 600.0
    output_mode: str = 'files'
    skip_existing: bool = False
    save_best_email: bool = True
    group_id: int | None = None
    mysql_identity: str = ''  # Endpoint fingerprint only; never credentials.
    categories: tuple[str, ...] = ()
    portal: str = 'wlw'

    def validate(self):
        if self.portal not in ('wlw', '11880'):
            raise ValueError('Neznámý portál databáze firem.')
        if not isinstance(self.categories, (tuple, list)) or any(not isinstance(v, str) or not v.strip() for v in self.categories):
            raise ValueError('Neplatný seznam kategorií.')
        if self.output_mode not in ('files', 'mysql'):
            raise ValueError('Neznámý cíl ukládání.')
        if type(self.save_best_email) is not bool:
            raise ValueError('Neplatné nastavení způsobu ukládání kontaktů.')
        if self.group_id is not None and (type(self.group_id) is not int or self.group_id <= 0):
            raise ValueError('Neplatná skupina kontaktů.')
        if not self.query.strip() and not self.categories and not self.input_file:
            raise ValueError('Zadejte hledané odvětví nebo vstupní TXT soubor.')
        if not 1 <= self.start_page <= 10000 or not 1 <= self.max_pages <= 10000:
            raise ValueError('Stránka a počet stránek musí být mezi 1 a 10 000.')
        if not 1 <= self.workers <= 16 or not 0.2 <= self.delay <= 60:
            raise ValueError('Počet pracovníků: 1–16; prodleva: 0,2–60 sekund.')
        if not 1 <= self.timeout <= 120 or not 0 <= self.contact_pages <= 10:
            raise ValueError('Neplatný timeout nebo počet kontaktních stránek.')
        if self.input_kind not in ('profiles', 'websites'):
            raise ValueError('Neznámý typ vstupu.')
        if self.input_file and not Path(self.input_file).is_file():
            raise ValueError('Vstupní soubor neexistuje.')
        if self.wlw_mode not in ('browser', 'http'):
            raise ValueError('Neznámý režim načítání WLW.')
        if self.browser_channel not in ('chromium', 'msedge', 'chrome'):
            raise ValueError('Neznámý prohlížeč.')
        if not 10 <= self.manual_timeout <= 3600:
            raise ValueError('Čekání na ruční ověření musí být 10–3600 sekund.')


class Fetcher:
    def __init__(self, config, stop, emit, transport=None, check_dns=True):
        self.config, self.stop, self.emit = config, stop, emit
        self.check_dns = check_dns
        self.client = httpx.Client(timeout=config.timeout, follow_redirects=False,
                                   headers={'User-Agent': AGENT, 'Accept': 'text/html,application/xhtml+xml'},
                                   limits=httpx.Limits(max_connections=config.workers + 2), transport=transport)
        self.lock = threading.Lock()
        self.last = {}
        self.dns_ok = set()

    def close(self):
        self.client.close()

    def pause(self, seconds):
        if self.stop.wait(max(0, seconds)):
            raise Cancelled()

    def validate_target(self, url):
        if not clean_url(url):
            raise FetchError('Neplatná nebo neveřejná URL')
        h = host(url)
        if self.check_dns and h not in self.dns_ok:
            try:
                addresses = socket.getaddrinfo(h, None)
            except OSError as exc:
                raise FetchError(f'DNS: {exc}') from exc
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise FetchError('Cíl není veřejná internetová adresa')
            with self.lock:
                self.dns_ok.add(h)

    def pace(self, url):
        key = domain(host(url))
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.last.get(key, now))
            self.last[key] = slot + self.config.delay
        self.pause(slot - now)

    def raw(self, url):
        for redirect in range(6):
            self.validate_target(url)
            target = None
            for attempt in range(3):
                self.pace(url)
                self.emit('request', url=url)
                try:
                    with self.client.stream('GET', url) as response:
                        status = response.status_code
                        if status in (429, 500, 502, 503, 504) and attempt < 2:
                            delay = 2 ** (attempt + 1)
                            header = response.headers.get('retry-after', '')
                            if header:
                                try:
                                    delay = max(delay, float(header))
                                except ValueError:
                                    try:
                                        delay = max(delay, (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
                                    except (ValueError, TypeError, OverflowError):
                                        pass
                            if delay > 60:
                                raise BlockingAccessError(f'HTTP {status}: server žádá čekat {delay:.0f} s; zkuste později.', 'RATE_LIMITED')
                            self.emit('log', level='WARN', message=f'HTTP {status}; opakování za {delay:.0f} s — {url}')
                            self.pause(delay)
                            continue
                        if status in (301, 302, 303, 307, 308):
                            target = clean_url(response.headers.get('location', ''), url)
                            if not target or not response.headers.get('location'):
                                raise FetchError('Neplatné přesměrování')
                            break
                        kind = response.headers.get('content-type', '').lower()
                        if status < 400 and kind and not any(t in kind for t in ('text/html', 'application/xhtml+xml')):
                            raise FetchError('Odpověď není HTML')
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            if self.stop.is_set():
                                raise Cancelled()
                            data.extend(chunk)
                            if len(data) > 3_000_000:
                                raise FetchError('Stránka přesahuje limit 3 MB')
                        text = bytes(data).decode(response.encoding or 'utf-8', errors='replace')
                        problem = detect_access_problem(status, response.headers, text)
                        if problem:
                            error = BlockingAccessError if problem.code != 'HTTP_ERROR' else FetchError
                            raise error(problem.message, problem.code)
                        return text, str(response.url)
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                    if attempt == 2:
                        raise FetchError(f'{type(exc).__name__}: {exc}') from exc
                    self.emit('log', level='WARN', message=f'Síťová chyba, opakuji — {url}')
                    self.pause(2 ** (attempt + 1))
                except httpx.HTTPError as exc:
                    raise FetchError(f'{type(exc).__name__}: {exc}') from exc
                # InvalidURL záměrně není potomkem HTTPError. Může vzniknout až
                # uvnitř httpx při zpracování syntakticky vadné odpovědi serveru
                # (typicky Location s cestou bez úvodního lomítka).
                except httpx.InvalidURL as exc:
                    raise FetchError(f'Neplatná URL v odpovědi serveru: {exc}', 'INVALID_URL') from exc
            if target:
                url = target
                continue
            raise FetchError('Vyčerpány pokusy')
        raise FetchError('Příliš mnoho přesměrování')

    def get(self, url):
        return self.raw(url)


class Store:
    def __init__(self, folder, config):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.run_lock = FileLock(str(self.folder / 'beh.lock'))
        try:
            self.run_lock.acquire(timeout=0)
        except Timeout as exc:
            raise ValueError('V této složce již běží jiná instance aplikace.') from exc
        self.db = sqlite3.connect(self.folder / 'stav.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (stage INTEGER, url TEXT, data TEXT, PRIMARY KEY(stage,url))')
        self.output_mode = config.output_mode
        self.db.execute('CREATE TABLE IF NOT EXISTS deliveries (email TEXT PRIMARY KEY, state TEXT NOT NULL)')
        identity = asdict(config)
        if identity['categories']:
            identity['categories'] = list(identity['categories'])
        else:
            identity.pop('categories')
        for key in ('workers', 'delay', 'timeout', 'input_file', 'wlw_mode', 'browser_channel', 'manual_timeout', 'respect_robots'):
            identity.pop(key)
        identity['version'] = VERSION
        identity['input_hash'] = hashlib.sha256(Path(config.input_file).read_bytes()).hexdigest() if config.input_file else ''
        encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False)
        previous = self.db.execute("SELECT value FROM meta WHERE key='config'").fetchone()
        previous_identity = json.loads(previous[0]) if previous else None
        if previous_identity:
            previous_identity.setdefault('portal', 'wlw')
            for key, value in {'output_mode': 'files', 'skip_existing': False,
                               'group_id': None, 'mysql_identity': ''}.items():
                previous_identity.setdefault(key, value)
            # Migrace staré identity: přístupové nastavení nemění zadání úlohy.
            for key in ('wlw_mode', 'browser_channel', 'manual_timeout', 'respect_robots'):
                previous_identity.pop(key, None)
        if previous_identity and previous_identity != identity:
            self.db.close()
            self.run_lock.release()
            raise ValueError('Tato složka obsahuje jinou úlohu. Vyberte novou složku nebo původní nastavení.')
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('config',?)", (encoded,))
        self.db.commit()

    def get(self, stage, url):
        row = self.db.execute('SELECT data FROM jobs WHERE stage=? AND url=?', (stage, url)).fetchone()
        if row:
            data = json.loads(row[0])
            if data.get('status') not in ('ERROR', 'PARTIAL'):
                return data
        return None

    def put(self, stage, url, data):
        self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)', (stage, url, json.dumps(data, ensure_ascii=False)))
        self.db.commit()

    def rows(self, stage):
        return [(u, json.loads(d)) for u, d in self.db.execute('SELECT url,data FROM jobs WHERE stage=? ORDER BY url', (stage,))]

    def export(self):
        failures = []

        def replace(tmp, target):
            # Excel, antivir nebo synchronizace OneDrive mohou na Windows cílový
            # soubor krátce zamknout. Starý export zůstane platný a dočasný soubor
            # poslouží dalšímu pokusu, pokud zámek nepovolí ani po několika sekundách.
            for attempt in range(6):
                try:
                    tmp.replace(target)
                    return
                except PermissionError:
                    if attempt < 5:
                        time.sleep(0.5)
            failures.append(target.name)

        def atom(name, text):
            target = self.folder / name
            tmp = target.with_suffix(target.suffix + '.tmp')
            tmp.write_text(text, encoding='utf-8')
            replace(tmp, target)
        def table(name, columns, rows):
            target = self.folder / name
            tmp = target.with_suffix('.csv.tmp')
            with tmp.open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle, delimiter=';')
                writer.writerow(columns)
                for row in rows:
                    writer.writerow(["'" + str(v) if str(v).startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in row])
            replace(tmp, target)
        profile_rows = self.rows(2)
        email_rows = self.rows(4)
        table('profily.csv', ['profil', 'web', 'stav', 'detail'],
              [(u, d.get('website', ''), d['status'], d.get('detail', '')) for u, d in profile_rows])
        def get_all_emails_str(d):
            emails = d.get('emails') or ([d['email']] if d.get('email') else [])
            return ' | '.join(sorted(set(emails)))

        table('kontakty.csv', ['web', 'konecna_url', 'email', 'vsechny_emaily', 'zdroj', 'stav', 'detail', 'nalezeno_ke_kontrole', 'mysql_stav', 'preskocene_adresy'],
              [(u, d.get('final_url', ''), d.get('email', ''), get_all_emails_str(d), d.get('source', ''), d['status'], d.get('detail', ''), ' | '.join(d.get('candidates', [])), d.get('delivery', ''),
                ' | '.join(sorted(set(d.get('skipped_existing', []) + ([d['skipped_email']] if d.get('skipped_email') else []))))) for u, d in email_rows])
        by_site = {site_key(u): d for u, d in email_rows if not profile_url(u, portal='11880')}
        by_profile = dict(email_rows)
        joined = []
        for profile, data in profile_rows:
            site = data.get('website', '')
            contact = by_profile.get(profile) or (by_site.get(site_key(site), {}) if site else {})
            joined.append((profile, site, contact.get('email', ''), contact.get('source', ''),
                           data['status'], contact.get('status', 'NEZPRACOVANO'),
                           data.get('detail', ''), contact.get('detail', '')))
        table('firmy.csv', ['profil', 'web', 'email', 'zdroj_emailu', 'stav_profilu', 'stav_emailu',
                            'detail_profilu', 'detail_emailu'], joined)
        if self.output_mode == 'files':
            all_export_emails = sorted({e for _, d in email_rows for e in (d.get('emails') or ([d['email']] if d.get('email') else [])) if e})
            atom('emaily.txt', ''.join(e + '\n' for e in all_export_emails))
        profiles = {u for _, d in self.rows(1) for u in d.get('profiles', [])}
        atom('wlw_company_urls.txt', ''.join(u + '\n' for u in sorted(profiles)))
        atom('company_urls.txt', ''.join(u + '\n' for u in sorted(profiles)))
        atom('websites_clean.txt', ''.join(u + '\n' for u, _ in self.rows(3)))
        table('chyby.csv', ['krok', 'url', 'stav', 'detail'],
              [(s, u, d['status'], d.get('detail', '')) for s in (1, 2, 4) for u, d in self.rows(s) if d['status'] in ('ERROR', 'PARTIAL', 'REVIEW', 'NO_WEBSITE')])
        return failures

    def delivery(self, email):
        row = self.db.execute('SELECT state FROM deliveries WHERE email=?', (email,)).fetchone()
        return row[0] if row else None

    def delivered(self, email, state):
        self.db.execute('INSERT OR REPLACE INTO deliveries VALUES (?,?)', (email, state))
        self.db.commit()

    def delivery_counts(self):
        return dict(self.db.execute('SELECT state, COUNT(*) FROM deliveries GROUP BY state'))

    def close(self):
        self.db.close()
        self.run_lock.release()


class Pipeline:
    def __init__(self, config, folder, callback=lambda event: None, stop=None, fetch_factory=None, continue_event=None, mysql_settings=None, contacts_factory=None, finish_event=None, browser_control=None):
        self.config, self.folder = config, Path(folder)
        self.mysql_settings = mysql_settings
        self.contacts_factory = contacts_factory or MySQLContacts
        self.contacts = None
        self.existing = frozenset()
        self.callback, self.stop, self.fetch_factory = callback, stop or threading.Event(), fetch_factory
        self.logger = logging.getLogger(f'wlw.{id(self)}')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.errors = 0
        self.continue_event = continue_event or threading.Event()
        self.finish_event = finish_event or threading.Event()
        self.profile_origins = {}
        self.site_origins = {}
        self.browser_control = browser_control

    def emit(self, kind, **data):
        if kind == 'result' and data.get('stage') in (2, 4):
            origins = (self.profile_origins.get(data['url'], []) if data['stage'] == 2 or profile_url(data['url'], portal='11880')
                       else self.site_origins.get(site_key(data['url']), []))
            if origins:
                data['data']['origins'] = origins
                self.store.put(data['stage'], data['url'], data['data'])
        if kind == 'log':
            self.logger.info('%s %s', data.get('level', 'INFO'), data['message'])
        self.callback({'type': kind, **data})
        if kind == 'result' and data.get('stage') in (2, 4):
            result = data['data']
            origins = '; '.join(dict.fromkeys(
                origin['category'] + (f" · stránka {origin['page']}" if origin.get('page') else '')
                for origin in result.get('origins', []) if origin.get('category')))
            context = f'Kategorie: {origins or "Neuvedena"}'
            restored = ' · z uložených dat' if data.get('cached') and not data.get('updated') else ''
            self.emit('log', level='WARN' if result['status'] in ('ERROR', 'PARTIAL') else 'INFO',
                      message=f'{data["url"]} → {result["status"]} {result.get("detail", "")} [{context}{restored}]')

    def export(self):
        failures = self.store.export()
        if failures:
            self.emit('log', level='WARN', message=(
                'Windows nepovolil nahradit soubor(y) ' + ', '.join(failures) +
                '. Data zůstávají bezpečně ve stav.sqlite3; zavřete CSV/Excel nebo vyčkejte na OneDrive.'))
        return failures

    def check(self):
        if self.stop.is_set():
            raise Cancelled()
        if hasattr(getattr(self, 'fetch', None), 'pump'):
            self.fetch.pump()

    def deliver_contact(self, url, data):
        """Called by coordinator after the raw result is durably saved locally."""
        data = dict(data)
        emails = list(data.get('emails') or ([data['email']] if data.get('email') else []))
        if not emails:
            return data

        valid_delivered = []
        new_skipped = list(data.get('skipped_existing', []))

        if self.config.output_mode == 'mysql':
            for email in emails:
                norm_email = normalize_email(email)
                if not norm_email:
                    continue
                state = self.store.delivery(norm_email)
                if state is None:
                    # Mark pending BEFORE sending. Crash after remote commit is safe to retry.
                    self.store.delivered(norm_email, 'PENDING')
                if state in (None, 'PENDING'):
                    try:
                        state = self.contacts.add(norm_email, self.config.group_id)
                    except MySQLError:
                        self.stop.set()
                        raise
                    self.store.delivered(norm_email, state)
                if state == 'EXISTING':
                    if norm_email not in new_skipped:
                        new_skipped.append(norm_email)
                else:
                    valid_delivered.append(norm_email)
            data['delivery'] = 'INSERTED' if valid_delivered else 'EXISTING'
            data['detail'] = f'Uloženo {len(valid_delivered)} e-mailů do MySQL.' if valid_delivered else 'Všechny nalezené adresy již existují v MySQL.'
            if not valid_delivered:
                data['status'] = 'SKIPPED_EXISTING'
                data['email'] = ''
                data['emails'] = []
            else:
                data['emails'] = valid_delivered
                data['email'] = valid_delivered[0]
            data['skipped_existing'] = sorted(set(new_skipped))
            self.store.put(4, url, data)
            self.emit('database', counts=self.store.delivery_counts())
        elif self.config.skip_existing:
            for email in emails:
                norm_email = normalize_email(email)
                if norm_email in self.existing:
                    if norm_email not in new_skipped:
                        new_skipped.append(norm_email)
                else:
                    valid_delivered.append(norm_email)
            if not valid_delivered:
                data['status'] = 'SKIPPED_EXISTING'
                data['detail'] = 'Všechny nalezené adresy již existují v MySQL; přeskočeno.'
                data['email'] = ''
                data['emails'] = []
            else:
                data['emails'] = valid_delivered
                data['email'] = valid_delivered[0]
            data['skipped_existing'] = sorted(set(new_skipped))
            self.store.put(4, url, data)
        else:
            self.store.put(4, url, data)
        return data

    def deliver_saved_contacts(self):
        """Commit locally saved contacts only after crawling has completed."""
        for url, data in self.store.rows(4):
            if data.get('email') or data.get('emails'):
                delivered = self.deliver_contact(url, data)
                self.emit('result', stage=4, url=url, data=delivered, cached=True, updated=True)

    def batch(self, stage, urls, worker):
        if stage == 2 and getattr(self.fetch, 'serial_wlw', False):
            return self.serial_profiles(urls, worker)
        total, done = len(urls), 0
        results = {}
        pending = iter(urls)
        self.emit('stage', stage=stage, done=0, total=total, status='Běží')
        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            futures = {}
            exhausted = False
            while futures or not exhausted:
                while len(futures) < self.config.workers and not exhausted and not self.stop.is_set():
                    try:
                        url = next(pending)
                    except StopIteration:
                        exhausted = True
                        break
                    cached = self.store.get(stage, url)
                    if cached is not None:
                        if stage == 4 and self.config.output_mode != 'mysql':
                            cached = self.deliver_contact(url, cached)
                        results[url] = cached
                        self.emit('result', stage=stage, url=url, data=cached, cached=True)
                        done += 1
                        self.emit('stage', stage=stage, done=done, total=total, status='Běží')
                    else:
                        futures[pool.submit(worker, url)] = url
                if not futures:
                    self.check()
                    continue
                ready, _ = wait(futures, timeout=0.2, return_when=FIRST_COMPLETED)
                if hasattr(self.fetch, 'pump') and not self.stop.is_set():
                    self.fetch.pump()
                for future in ready:
                    url = futures.pop(future)
                    try:
                        data = future.result()
                    except Cancelled:
                        continue
                    except FetchError as exc:
                        data = error_result(exc)
                    self.store.put(stage, url, data)
                    if stage == 4 and self.config.output_mode != 'mysql':
                        data = self.deliver_contact(url, data)
                    results[url] = data
                    done += 1
                    if data['status'] in ('ERROR', 'PARTIAL'):
                        self.errors += 1
                    self.emit('result', stage=stage, url=url, data=data)
                    self.emit('stage', stage=stage, done=done, total=total, status='Běží')
                    if done % 20 == 0:
                        self.export()
                if self.stop.is_set() and not futures:
                    raise Cancelled()
        self.check()
        self.export()
        failed = sum(d['status'] in ('ERROR', 'PARTIAL') for d in results.values())
        self.emit('stage', stage=stage, done=total, total=total, status=f'Hotovo · chyb: {failed}' if failed else 'Hotovo')
        return results

    def serial_profiles(self, urls, worker):
        """Playwright zůstává ve vlákně koordinátoru, včetně hledání i close()."""
        results = {}
        description = 'Běží v prohlížeči' if self.config.wlw_mode == 'browser' else 'Běží přes HTTP'
        self.emit('stage', stage=2, done=0, total=len(urls), status=description)
        for index, url in enumerate(urls, 1):
            self.check()
            data = self.store.get(2, url)
            cached = data is not None
            if not cached:
                try:
                    data = worker(url)
                except FetchError as exc:
                    data = error_result(exc)
                    self.store.put(2, url, data)
                    self.errors += 1
                    self.emit('result', stage=2, url=url, data=data)
                    if isinstance(exc, BlockingAccessError):
                        raise
                else:
                    self.store.put(2, url, data)
                    self.emit('result', stage=2, url=url, data=data)
            else:
                self.emit('result', stage=2, url=url, data=data, cached=True)
            results[url] = data
            self.emit('stage', stage=2, done=index, total=len(urls), status=description)
            if index % 20 == 0:
                self.export()
        self.check()
        self.export()
        failed = sum(d['status'] == 'ERROR' for d in results.values())
        self.emit('stage', stage=2, done=len(urls), total=len(urls), status=f'Hotovo · chyb: {failed}' if failed else 'Hotovo')
        return results

    def scrape_site(self, url):
        html, final = self.fetch.get(url)
        sources = {e: final for e in extract_emails(html)}
        problems = []
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        for a in soup.select('a[href]'):
            link = clean_url(a['href'], final)
            if link and domain(host(link)) == domain(host(final)) and CONTACT.search(a.get_text(' ') + ' ' + a['href']):
                links.append(link)
        # Odkazy na kontakty a impressum
        links.extend(urljoin(final, '/' + p) for p in ('impressum', 'kontakt', 'contact'))
        links = list(dict.fromkeys(u for u in links if u != final))[:self.config.contact_pages]
        for link in links:
            self.check()
            try:
                sub_html, sub_final = self.fetch.get(link)
                if domain(host(sub_final)) != domain(host(final)):
                    continue
                for email in extract_emails(sub_html):
                    sources.setdefault(email, sub_final)
            except FetchError as exc:
                if 'HTTP 404' not in str(exc) and 'HTTP 410' not in str(exc):
                    problems.append(f'{link}: {exc}')

        return self.select_contact(sources, final, problems)

    def select_contact(self, sources, final, problems=()):
        same_domain = [e for e in sources if domain(e.rsplit('@', 1)[1]) == domain(host(final))]
        other_domain = [e for e in sources if e not in same_domain]

        preferred_prefixes = ['info', 'kontakt', 'contact', 'office', 'mail', 'service', 'support', 'sales', 'obchod']
        def email_sort_key(e):
            local = e.split('@')[0].lower()
            idx = preferred_prefixes.index(local) if local in preferred_prefixes else 99
            return (idx, e)

        valid_candidates = sorted(same_domain if same_domain else other_domain, key=email_sort_key)
        known = sorted(set(sources) & self.existing)
        new_candidates = [e for e in valid_candidates if e not in self.existing]

        # Výběr nejlepšího kontaktu pomocí funkce best_email:
        best = best_email(set(sources) - self.existing, final)
        if not best and new_candidates:
            best = new_candidates[0]

        if self.config.save_best_email:
            selected_emails = [best] if best else []
        else:
            selected_emails = new_candidates

        if selected_emails:
            status = 'OK'
        elif known and not (set(sources) - set(known)):
            status = 'SKIPPED_EXISTING'
        elif problems:
            status = 'PARTIAL'
        elif sources:
            status = 'REVIEW'
        else:
            status = 'NO_EMAIL'

        detail = (' | '.join(problems) if problems else
                  ('Adresy již existují v MySQL; přeskočeno.' if status == 'SKIPPED_EXISTING' else
                   'Jiná e-mailová doména; ověřte ručně.' if sources and not selected_emails else ''))

        return {
            'status': status,
            'email': best,
            'emails': selected_emails,
            'all_emails': sorted(sources),
            'skipped_existing': known,
            'source': sources.get(best, final),
            'final_url': final,
            'candidates': sorted(sources),
            'detail': detail
        }

    def run(self):
        self.config.validate()
        if self.config.output_mode == 'mysql' or self.config.skip_existing:
            if self.mysql_settings is None:
                raise ValueError('Nejprve nastavte připojení MySQL.')
            self.mysql_settings.validate()
            self.config.mysql_identity = self.mysql_settings.identity()
        self.store = Store(self.folder, self.config)
        handler = logging.FileHandler(self.folder / 'prubeh.log', encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        self.logger.addHandler(handler)
        self.fetch = None
        status = 'DONE'
        try:
            if self.config.output_mode == 'mysql' or self.config.skip_existing:
                self.emit('log', message='MySQL: připojuji databázi kontaktů…')
                self.contacts = self.contacts_factory(self.mysql_settings)
                groups = self.contacts.groups()
                if self.config.output_mode == 'mysql' and self.config.group_id is not None:
                    if self.config.group_id not in {gid for gid, *_ in groups}:
                        raise MySQLError('Vybraná skupina již neexistuje. Obnovte seznam skupin.')
                if self.config.skip_existing:
                    self.existing = self.contacts.existing_emails(self.check)
                    self.emit('log', message=f'MySQL: kontrola proti {len(self.existing)} adresám ze všech skupin.')
                # Retry a delivery only after a previous explicit finalization
                # reached MySQL but did not receive a conclusive response.
                if self.config.output_mode == 'mysql':
                    for url, data in self.store.rows(4):
                        emails = data.get('emails') or ([data['email']] if data.get('email') else [])
                        if any(self.store.delivery(normalize_email(email)) == 'PENDING' for email in emails):
                            self.deliver_contact(url, data)
            if self.fetch_factory:
                self.fetch = self.fetch_factory(self.config, self.stop, self.emit)
            else:
                from system.browser_fetcher import HybridFetcher
                self.fetch = HybridFetcher(self.config, self.stop, self.emit, self.folder, self.continue_event, self.browser_control)
            profiles, imported_sites = set(), []
            cfg = self.config
            if self.finish_event.is_set():
                profiles.update(profile for _, data in self.store.rows(1) for profile in data.get('profiles', []))
                if not profiles:
                    imported_sites = [url for url, _ in self.store.rows(3)]
                self.emit('log', message='Používám aktuálně uložená data; další stránky katalogu se nenačítají.')
                self.emit('stage', stage=1, done=len(self.store.rows(1)), total=len(self.store.rows(1)),
                          profiles=len(profiles), status='Hotovo z uložených dat')
            elif cfg.input_file:
                lines = Path(cfg.input_file).read_text(encoding='utf-8-sig').splitlines()
                parser = (lambda value: profile_url(value, portal=cfg.portal)) if cfg.input_kind == 'profiles' else clean_url
                values = sorted({u for line in lines if line.strip() and (u := parser(line.strip()))})
                rejected = sum(1 for line in lines if line.strip() and not parser(line.strip()))
                if not values:
                    raise ValueError('Vstup neobsahuje žádné platné URL.')
                self.emit('log', message=f'Import: {len(values)} unikátních URL; neplatných řádků: {rejected}.')
                if cfg.input_kind == 'profiles':
                    profiles.update(values)
                else:
                    imported_sites = values
                self.store.put(1, 'import', {'status': 'OK', 'profiles': sorted(profiles)})
                self.emit('stage', stage=1, done=1, total=1, profiles=len(profiles), status='Import hotov')
            else:
                categories = cfg.categories or (cfg.query,)
                total_pages = len(categories) * cfg.max_pages
                pages_done = 0
                for category_index, category in enumerate(categories):
                    self.check()
                    category_profiles = set()
                    self.emit('log', message=f'Kategorie {category_index + 1}/{len(categories)}: {category}')
                    for offset in range(cfg.max_pages):
                        self.check()
                        if self.finish_event.is_set():
                            break
                        page = cfg.start_page + offset
                        url = search_url(category.strip(), page, cfg.portal)
                        self.emit('stage', stage=1, done=category_index * cfg.max_pages + offset,
                                  total=total_pages, profiles=len(profiles),
                                  status=f'{category} · stránka {page}')
                        data = self.store.get(1, url)
                        if data is None:
                            try:
                                html, final = self.fetch.get(url)
                                found = search_profiles(html, final, cfg.portal)
                                if not found:
                                    raise FetchError('Nenalezeny profily: ověřte dotaz, HTML nebo ochranu webu. Konec není potvrzen.')
                                data = {'status': 'OK', 'profiles': found, 'category': category, 'page': page}
                                if cfg.portal == '11880':
                                    data['has_next'] = directory_has_next(html)
                                self.store.put(1, url, data)
                            except FetchError as exc:
                                self.store.put(1, url, error_result(exc))
                                self.errors += 1
                                self.emit('log', level='WARN', message=f'Vyhledávání zastaveno na stránce {page}: {exc}')
                                if isinstance(exc, BlockingAccessError):
                                    raise
                                break
                        new = set(data['profiles']) - category_profiles
                        if not new:
                            detail = 'Stránka opakuje již nalezené profily; další stránkování zastaveno. Konec není potvrzen.'
                            self.store.put(1, url, {**data, 'status': 'ERROR', 'detail': detail})
                            self.errors += 1
                            self.emit('log', level='WARN', message=detail)
                            break
                        category_profiles.update(new)
                        profiles.update(new)
                        pages_done = category_index * cfg.max_pages + offset + 1
                        self.emit('stage', stage=1, done=pages_done,
                                  total=total_pages, profiles=len(profiles),
                                  status=f'Profilů: {len(profiles)}')
                        if cfg.portal == '11880' and data.get('has_next') is False:
                            self.emit('log', message='Poslední stránka výsledků 11880.com; pokračuji zpracováním profilů.')
                            break
                        if self.finish_event.is_set():
                            self.emit('log', message='Dokončení zvoleného sběru: další vyhledávání je zastaveno.')
                            break
                    if self.finish_event.is_set():
                        break
                final_total = pages_done if pages_done > 0 else total_pages
                self.emit('stage', stage=1, done=pages_done, total=final_total,
                          profiles=len(profiles), status='S chybou' if self.errors else 'Hotovo')
            # Rebuild provenance from saved listings, including older runs whose
            # category and page can be recovered from the configured search URL.
            listing_origins = {}
            if not cfg.input_file:
                for category in cfg.categories or (cfg.query,):
                    for page in range(cfg.start_page, cfg.start_page + cfg.max_pages):
                        listing_origins[search_url(category.strip(), page, cfg.portal)] = {'category': category, 'page': page}
            for listing_url, listing in self.store.rows(1):
                origin = ({'category': listing['category'], 'page': listing['page']}
                          if listing.get('category') and listing.get('page') else listing_origins.get(listing_url))
                if origin:
                    for profile in listing.get('profiles', []):
                        entries = self.profile_origins.setdefault(profile, [])
                        if origin not in entries:
                            entries.append(origin)
            if profiles:
                def profile_worker(url):
                    html, final = self.fetch.get(url)
                    if cfg.portal == '11880':
                        if profile_url(final, portal=cfg.portal) != url:
                            raise FetchError('Profil byl přesměrován na jinou stránku.', 'UNEXPECTED_REDIRECT')
                        return directory_contact(html, url)
                    return website_from_profile(html, url)
                mapped = self.batch(2, sorted(profiles), profile_worker)
                for profile, data in mapped.items():
                    if data.get('website'):
                        entries = self.site_origins.setdefault(site_key(data['website']), [])
                        for origin in self.profile_origins.get(profile, []):
                            if origin not in entries:
                                entries.append(origin)
                sites = [d['website'] for d in mapped.values() if d.get('website')]
            else:
                sites = imported_sites
                self.emit('stage', stage=2, done=0, total=0, status='Přeskočeno')
            unique = {}
            for site in sorted(sites, key=lambda u: (not u.startswith('https:'), u)):
                root = root_url(site)
                if root:
                    unique.setdefault(site_key(root), root)
            for site in unique.values():
                self.store.put(3, site, {'status': 'OK'})
            self.emit('stage', stage=3, done=len(sites), total=len(sites), status=f'Hotovo · {len(unique)} unikátních webů')
            self.emit('log', message=f'Čištění: {len(sites)} odkazů → {len(unique)} webů.')
            if profiles and cfg.portal == '11880':
                direct = {url: data for url, data in mapped.items() if data['status'] == 'OK'}
                def profile_contact(url):
                    data = direct[url]
                    result = self.select_contact({e: url for e in data['profile_emails']}, data.get('website') or url)
                    result['source'] = url
                    return result
                self.batch(4, sorted(direct), profile_contact)
            elif unique:
                self.batch(4, sorted(unique.values()), self.scrape_site)
            else:
                self.emit('stage', stage=4, done=0, total=0, status='Bez vstupu')
            if self.config.output_mode == 'mysql':
                self.emit('log', message='MySQL: ukládám dokončený výsledek sběru…')
                self.deliver_saved_contacts()
            if self.errors:
                status = 'PARTIAL'
        except Cancelled:
            status = 'STOPPED'
            self.emit('log', message='Zastaveno. Uložené úlohy se příště přeskočí.')
        except BlockingAccessError as exc:
            status = 'BLOCKED'
            self.emit('log', level='ERROR', message=f'{exc.code}: {exc} Hotová práce zůstává uložená.')
        except MySQLError as exc:
            self.errors += 1
            status = 'FAILED'
            self.emit('log', level='ERROR', message=f'{exc} Výsledky jsou uloženy; spusťte pokračování ve stejné složce.')
        except Exception as exc:
            status = 'FAILED'
            self.logger.exception('Běh selhal')
            self.emit('log', level='ERROR', message=str(exc))
        finally:
            if self.contacts is not None:
                self.contacts.close()
            if self.fetch is not None:
                try:
                    self.fetch.close()
                except Exception as exc:
                    self.emit('log', level='WARN', message=f'Zavření síťové relace: {exc}')
            try:
                self.export()
                profile_count = len({profile for _, data in self.store.rows(1)
                                     for profile in data.get('profiles', [])})
                all_found_emails = {e for _, d in self.store.rows(4) for e in (d.get('emails') or ([d['email']] if d.get('email') else [])) if e}
                all_skipped_emails = {e for _, d in self.store.rows(4) for e in
                    d.get('skipped_existing', []) + ([d['skipped_email']] if d.get('skipped_email') else []) if e}
                summary = {'status': status, 'portal': self.config.portal, 'profiles': profile_count, 'websites': len(self.store.rows(3)),
                           'emails': len(all_found_emails),
                           'errors_this_run': self.errors,
                           'mysql': self.store.delivery_counts(),
                           'skipped_existing': len(all_skipped_emails),
                           'review': sum(d['status'] == 'REVIEW' for s in (2, 4) for _, d in self.store.rows(s))}
                (self.folder / 'souhrn.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
                self.emit('finish', **summary, folder=str(self.folder))
            finally:
                self.store.close()
                handler.close()
                self.logger.removeHandler(handler)
        return status
