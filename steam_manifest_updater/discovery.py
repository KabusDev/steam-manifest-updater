"""Find installed Steam apps across every configured Steam library."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .vdf import VDFError, get_ci, parse

MANIFEST_NAME = re.compile(r'^appmanifest_(\d+)\.acf$', re.IGNORECASE)


@dataclass(frozen=True)
class InstalledApp:
    appid: str
    name: str
    library: Path
    install_dir: Path
    manifest: Path
    files_present: bool


def read_vdf(path: Path) -> dict:
    raw = path.read_bytes()
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return parse(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise VDFError(f'Cannot decode {path}')


def detect_steam_roots() -> list[Path]:
    """Windows registry / common locations, with Linux paths for contributors."""
    candidates = []
    if os.getenv('STEAM_PATH'):
        candidates.append(Path(os.environ['STEAM_PATH']))
    if sys.platform == 'win32':
        try:
            import winreg
            for hive, key in [
                (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam'),
            ]:
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        for entry in ('SteamPath', 'InstallPath'):
                            try:
                                candidates.append(Path(winreg.QueryValueEx(handle, entry)[0]))
                                break
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
            if os.getenv(variable):
                candidates.append(Path(os.environ[variable]) / 'Steam')
    else:
        candidates += [Path.home() / '.local/share/Steam', Path.home() / '.steam/steam']
    return _unique_existing(candidates)


def _unique_existing(paths) -> list[Path]:
    seen, output = set(), []
    for path in paths:
        path = Path(path).expanduser().resolve()
        key = os.path.normcase(str(path))
        if key not in seen and (path / 'steamapps').is_dir():
            seen.add(key)
            output.append(path)
    return output


def find_libraries(roots: list[Path], warn=lambda message: None) -> list[Path]:
    candidates = list(roots)
    for root in roots:
        for index in (root / 'steamapps/libraryfolders.vdf', root / 'config/libraryfolders.vdf'):
            if not index.is_file():
                continue
            try:
                folders = get_ci(read_vdf(index), 'libraryfolders', {})
                if not isinstance(folders, dict):
                    raise VDFError('libraryfolders must be an object')
                for key, item in folders.items():
                    if not key.isdigit():
                        continue
                    raw = get_ci(item, 'path') if isinstance(item, dict) else item
                    if isinstance(raw, str) and raw:
                        candidates.append(Path(raw))
            except (OSError, VDFError, ValueError) as exc:
                warn(f'Cannot read {index}: {exc}')
    return _unique_existing(candidates)


def discover(roots: list[Path], warn=lambda message: None) -> tuple[list[InstalledApp], list[Path]]:
    libraries = find_libraries(roots, warn=warn)
    found = []
    for library in libraries:
        for manifest in sorted((library / 'steamapps').glob('appmanifest_*.acf')):
            m = MANIFEST_NAME.match(manifest.name)
            if not m:
                continue
            try:
                state = get_ci(read_vdf(manifest), 'AppState')
                if not isinstance(state, dict):
                    raise VDFError('missing AppState block')
                appid = str(get_ci(state, 'appid', m.group(1)))
                install_name = get_ci(state, 'installdir')
                if not appid.isdigit() or appid != m.group(1):
                    raise VDFError('AppID differs from manifest filename')
                if not isinstance(install_name, str) or not install_name or '\x00' in install_name:
                    raise VDFError('missing installdir')
                base = (library / 'steamapps/common').resolve()
                install = (base / install_name).resolve()
                if install == base or base not in install.parents:
                    raise VDFError('installdir points outside steamapps/common')
                name = str(get_ci(state, 'name', f'App {appid}'))
                found.append(InstalledApp(appid, name, library, install, manifest, install.is_dir()))
            except (OSError, VDFError, ValueError) as exc:
                warn(f'Ignoring invalid manifest {manifest}: {exc}')
    return found, libraries
