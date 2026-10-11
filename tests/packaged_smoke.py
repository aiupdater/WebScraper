"""Launch the real executable in isolated user data, with offline diagnostics."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True)
    args = parser.parse_args()
    executable = Path(args.exe).resolve()
    with tempfile.TemporaryDirectory(prefix='WebScraper EXE česky ') as temporary:
        report = Path(temporary) / 'report.json'
        env = dict(os.environ, LOCALAPPDATA=temporary)
        # No Python/Playwright directory can assist the executable via PATH.
        env['PATH'] = os.pathsep.join([os.environ.get('SystemRoot','C:/Windows'),
                                     os.environ.get('SystemRoot','C:/Windows') + '/System32'])
        for name in list(env):
            if name.startswith('MYSQL') or name in ('PYTHONPATH','PYTHONHOME','PLAYWRIGHT_BROWSERS_PATH'):
                env.pop(name)
        result = subprocess.run([str(executable), '--diagnostic-report', str(report)],
            cwd=temporary, env=env, timeout=180, check=False)
        if not report.is_file():
            raise AssertionError('EXE nevytvořilo diagnostický výsledek. Exit: ' + str(result.returncode))
        data = json.loads(report.read_text(encoding='utf-8'))
        artifact = Path(__file__).resolve().parent / 'artifacts' / 'packaged-smoke.json'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        assert result.returncode == 0 and data['ok'], data
        print('PASS: actual EXE, isolated Czech paths, ' + ', '.join(data['checks']))


if __name__ == '__main__':
    main()
