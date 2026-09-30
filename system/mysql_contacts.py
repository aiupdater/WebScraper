"""FebaMont contacts; credentials never belong to Config, logs or the repository."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import ssl
from system.paths import APP_ROOT, config_path


class MySQLError(RuntimeError):
    pass


def normalize_email(value):
    return (value or '').strip().lower()


def load_dotenv(base_path=None):
    base = Path(base_path) if base_path else APP_ROOT / 'config'
    for env_name in ('.env',):
        env_file = base / env_name
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass


@dataclass(frozen=True)
class MySQLSettings:
    host: str = 'nch06.vas-server.cz'
    database: str = 'dbemailapp_1'
    user: str = 'dbemailapp.1'
    port: int = 3306
    password: str = field(default='Dbemailapp.1', repr=False)
    tls: bool = False
    ca_file: str = ''

    def validate(self):
        if not self.host.strip() or not self.database.strip() or not self.user.strip():
            raise ValueError('Vyplňte server, databázi a uživatele MySQL.')
        if not 1 <= self.port <= 65535:
            raise ValueError('Port MySQL musí být 1–65535.')
        if not self.password:
            raise ValueError('Zadejte heslo v Nastavení MySQL nebo MYSQLPASSWORD.')

    def identity(self):
        value = [self.host.lower(), self.port, self.database, self.user]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    @classmethod
    def load(cls, path=None):
        if path is None:
            config_path('.env')
        target_path = Path(path) if path else config_path('mysql.local.json')
        load_dotenv(target_path.parent)
        values = json.loads(target_path.read_text(encoding='utf-8')) if target_path.exists() else {}
        if not isinstance(values, dict):
            raise ValueError('mysql.local.json musí obsahovat JSON objekt.')
        values = {k: v for k, v in values.items() if k in cls.__dataclass_fields__}
        for key in cls.__dataclass_fields__:
            raw = os.environ.get('MYSQL' + key.upper())
            if raw is not None:
                values[key] = raw
        if 'port' in values and values['port'] is not None and str(values['port']).strip():
            values['port'] = int(str(values['port']).strip())
        if isinstance(values.get('tls'), str):
            if values['tls'].lower() not in ('true', 'false', '1', '0'):
                raise ValueError('MYSQLTLS musí být true nebo false.')
            values['tls'] = values['tls'].lower() in ('true', '1')
        if values.get('ca_file') in ('false', 'null', 'None'):
            values['ca_file'] = ''
        return cls(**values)

    def save_public(self, path):
        data = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != 'password'}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def save_local(self, path):
        path = Path(path)
        data = {k: getattr(self, k) for k in self.__dataclass_fields__}
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)


def friendly_error(exc):
    code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    hints = {
        1045: 'Přihlášení odmítnuto. Ověřte heslo a povolenou IP adresu.',
        1044: 'Uživatel nemá přístup k databázi.',
        1142: 'Chybí oprávnění SELECT nebo INSERT pro tabulky kontaktů.',
        1146: 'Chybí tabulka emails nebo contact_groups.',
        1452: 'Vybraná skupina již neexistuje. Obnovte seznam skupin.',
        2003: 'Server není dostupný. Ověřte server, port a povolenou IP adresu.',
        2006: 'Spojení se serverem bylo přerušeno.',
        2013: 'Spojení se serverem bylo přerušeno.',
    }
    # Never include a driver message: it can contain credentials or connection strings.
    return 'MySQL: ' + hints.get(code, 'Operace selhala. Ověřte připojení, TLS a strukturu databáze.') + (f' (kód {code})' if code else '')


class MySQLContacts:
    """One connection per owner thread; GUI and pipeline use separate instances."""
    def __init__(self, settings):
        settings.validate()
        self.connection = None
        try:
            import pymysql
        except ImportError:
            raise MySQLError('Chybí PyMySQL. Spusťte INSTALOVAT.bat.') from None
        self.integrity_error = pymysql.err.IntegrityError
        try:
            context = ssl.create_default_context(cafile=settings.ca_file or None) if settings.tls else None
            self.connection = pymysql.connect(
                host=settings.host, port=settings.port, user=settings.user,
                password=settings.password, database=settings.database,
                charset='utf8mb4', autocommit=True, connect_timeout=8,
                read_timeout=12, write_timeout=12, local_infile=False,
                ssl=context, ssl_disabled=not settings.tls,
            )
            if settings.tls:
                with self.connection.cursor() as cursor:
                    cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
                    row = cursor.fetchone()
                    if not row or not row[1]:
                        raise MySQLError('MySQL: server neposkytl požadované TLS spojení.')
        except Exception as exc:
            self.close()
            raise MySQLError(str(exc) if isinstance(exc, MySQLError) else friendly_error(exc)) from None

    def groups(self):
        try:
            with self.connection.cursor() as cursor:
                try:
                    cursor.execute('SELECT id, name, color FROM contact_groups ORDER BY name, id')
                    rows = cursor.fetchall()
                    if rows and len(rows[0]) > 2:
                        return [(int(row[0]), row[1], (row[2] or '').strip()) for row in rows]
                    return [(int(row[0]), row[1]) for row in rows]
                except Exception:
                    cursor.execute('SELECT id, name FROM contact_groups ORDER BY name, id')
                    return [(int(row[0]), row[1]) for row in cursor.fetchall()]
        except Exception as exc:
            raise MySQLError(friendly_error(exc)) from None

    def existing_emails(self, check=lambda: None):
        import pymysql
        try:
            emails = set()
            with self.connection.cursor(pymysql.cursors.SSCursor) as cursor:
                # Include archived/unsubscribed contacts and every group.
                cursor.execute('SELECT email FROM emails WHERE email IS NOT NULL')
                while True:
                    check()
                    rows = cursor.fetchmany(2000)
                    if not rows:
                        return frozenset(emails)
                    emails.update(normalize_email(row[0]) for row in rows if row[0])
        except Exception as exc:
            if not isinstance(exc, (pymysql.MySQLError, OSError)):
                raise
            raise MySQLError(friendly_error(exc)) from None

    def add(self, email, group_id):
        email = normalize_email(email)
        try:
            with self.connection.cursor() as cursor:
                # The unique email index handles races with Emailapp and other scrapers.
                # Do not UPDATE existing rows (groups, unsubscribe flags or triggers).
                cursor.execute('INSERT INTO emails (email, email_domain, group_id) VALUES (%s, %s, %s)',
                               (email, email.rsplit('@', 1)[1], group_id))
            return 'INSERTED'
        except self.integrity_error as exc:
            if exc.args and exc.args[0] == 1062:
                return 'EXISTING'
            raise MySQLError(friendly_error(exc)) from None
        except Exception as exc:
            raise MySQLError(friendly_error(exc)) from None

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None
