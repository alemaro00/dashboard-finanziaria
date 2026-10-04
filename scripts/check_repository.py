"""Offline integrity and boundary checks; not a substitute for full secret scanning."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
errors=[]
manifest=json.loads((ROOT/'vendor/SHA256.json').read_text())
for name,digest in manifest.items():
    if hashlib.sha256((ROOT/'vendor'/name).read_bytes()).hexdigest()!=digest:
        errors.append('Vendor integrity mismatch: '+name)
for path in (ROOT/'research').glob('*.py'):
    tree=ast.parse(path.read_text())
    for node in ast.walk(tree):
        modules=[]
        if isinstance(node,ast.Import):modules=[n.name.split('.')[0] for n in node.names]
        if isinstance(node,ast.ImportFrom):modules=[(node.module or '').split('.')[0]]
        if set(modules)&{'socket','ibapi','requests','urllib','http','subprocess','ctypes'}:
            errors.append('Forbidden transport/import in '+path.name)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'eval','exec','__import__'}:
            errors.append('Dynamic execution in '+path.name)
frontend=(ROOT/'salary-planner-react.html').read_text()
bridge=(ROOT/'ibkr_paper_bridge.py').read_text()
mac_build=(ROOT/'scripts'/'build-macos-app.sh').read_text()
for retired in ('Stima stipendio netto da RAL','Laboratorio strategie','/api/research/','/api/paper-lab/'):
    if retired in frontend:
        errors.append('Retired beta feature still present in frontend: '+retired)
for retired in ('/api/research/','/api/paper-lab/','ResearchEngine','PaperLab'):
    if retired in bridge:
        errors.append('Retired beta service still active in bridge: '+retired)
for excluded in ('paper_data.py','cp -R "$PROJECT_DIR/research"'):
    if excluded in mac_build:
        errors.append('Retired beta component still bundled: '+excluded)
for required in ('Gestione delle finanze','Wealth management','beta-badge'):
    if required not in frontend:
        errors.append('Required beta UI marker missing: '+required)
for required in ('/Applications/Beta Dashboard Finanziaria.app',
                 'it.alemaro.dashboard-finanziaria.beta',
                 'BetaDashboardFinanziaria'):
    if required not in mac_build:
        errors.append('Separate beta application identity missing: '+required)
native_wrapper=(ROOT/'macos'/'DashboardFinanziaria.m').read_text()
for required in ('127.0.0.1:8767', 'Dashboard Finanziaria Beta', 'DASHBOARD_DATA_DIR'):
    if required not in native_wrapper:
        errors.append('Separate beta runtime boundary missing: '+required)
banking_sync=(ROOT/'enable_banking_sync.py').read_text()
if '127.0.0.1:8767/api/enable-banking/callback' not in banking_sync:
    errors.append('Beta banking callback does not use the separate beta port')
if 'DASHBOARD_DATA_DIR' not in banking_sync or 'DEFAULT_KEY_PATH = (\n    DEFAULT_DATA_DIR' not in banking_sync:
    errors.append('Beta banking key does not follow the separate beta data directory')
for required in ('Configurazione iniziale · una sola volta', 'loadBankOptions', 'non devi copiare alcun indirizzo'):
    if required not in frontend:
        errors.append('Guided banking setup missing: '+required)
patterns=[re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
          re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(r'AKIA[A-Z0-9]{16}')]
skip={'.git','.venv','.build','dist','vendor','web-build','__pycache__','.ruff_cache'}
for path in ROOT.rglob('*'):
    if not path.is_file() or set(path.relative_to(ROOT).parts)&skip or path.stat().st_size>1_000_000:continue
    if path.suffix not in {'.py','.js','.cjs','.html','.md','.toml','.yml','.txt','.m','.sh','.command','.bat'}:continue
    for index,line in enumerate(path.read_text(errors='replace').splitlines(),1):
        if any(pattern.search(line) for pattern in patterns):
            errors.append(f'Potential secret: {path.relative_to(ROOT)}:{index}')
if errors:raise SystemExit('\n'.join(errors))
print('Vendor hashes, beta scope, offline research boundary, focused secret patterns: OK')
