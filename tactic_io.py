"""Persist and export version 1 tactical-board documents.

The browser's Python filesystem is temporary. Saved tactics therefore use
localStorage there; explicit exports are downloaded from the virtual /tmp
filesystem. Desktop files are written to the current working directory.
"""

import base64
import importlib
import json
import sys
from pathlib import Path


STATE_VERSION = 1
MAX_JSON_BYTES = 1024 * 1024
STORAGE_KEY = "tactical-board.tactic.v1"
SAVE_FILENAME = "tactic.json"
EXPORT_JSON_FILENAME = "tactic-export.json"
EXPORT_PNG_FILENAME = "tactic.png"
WEB_EXPORT_DIR = Path("/tmp")

# Pygbag adds one upload listener per call to webbrowser.open_file(callback).
# Keep a single listener and route each upload to the latest pending request.
_upload_handler_registered = False
_pending_import_callback = None

_UPLOAD_SETUP_JS = r"""
(() => {
  const picker = window.document.getElementById('dlg_multifile');
  if (!picker) throw new Error('Pygbag file input is unavailable');
  picker.accept = '.json,application/json';
  picker.multiple = false;

  // The generated page includes the picker, but data-os omits 'fs'. Without
  // that feature Pygbag does not attach its change listener or send the Python
  // 'upload' event, even though webbrowser.open_file opens the chooser.
  const site = window.document.getElementById('site');
  const features = (site?.dataset.os || '').split(',').map(x => x.trim());
  if (!features.includes('fs') && !picker.__tacticalBoardUploadHook) {
    if (typeof window.transfer_uploads !== 'function')
      throw new Error('Pygbag upload transfer is unavailable');
    picker.addEventListener('change', () => {
      if (picker.files.length) window.transfer_uploads(picker.files, false);
      picker.value = '';
    });
    picker.__tacticalBoardUploadHook = true;
  }
  return true;
})()
"""


def _is_web():
    return sys.platform == "emscripten"


def _web_window():
    # platform.window exists in pygbag's Emscripten runtime only.
    from platform import window

    return window


def _validate_state(state):
    if not isinstance(state, dict):
        raise ValueError("A tática tem de ser um objeto JSON.")
    if type(state.get("version")) is not int or state["version"] != STATE_VERSION:
        raise ValueError("Versão de tática inválida; esperada versão 1.")
    return state


def _encode_state(state, ascii_only=False):
    _validate_state(state)
    try:
        text = json.dumps(state, ensure_ascii=ascii_only, indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError("A tática contém dados inválidos para JSON.") from exc
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("A tática excede o limite de 1 MB.")
    return text


def _reject_non_finite(value):
    raise ValueError(f"Valor JSON inválido: {value}.")


def _decode_state(text):
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("O ficheiro de tática excede o limite de 1 MB.")
    try:
        state = json.loads(text, parse_constant=_reject_non_finite)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("O ficheiro de tática não contém JSON válido.") from exc
    return _validate_state(state)


def _desktop_path(filename):
    return Path.cwd() / filename


def _web_export_path(filename):
    WEB_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return WEB_EXPORT_DIR / filename


def _download(path, mime_type):
    window = _web_window()
    try:
        window.MM.download(str(path))
        return
    except Exception as exc:
        # MM.download is documented by pygbag, but is absent or cannot read
        # /tmp files in some runtime versions. A data URL keeps the transfer
        # entirely in the browser and uses ASCII across the Python/JS bridge.
        mm_error = exc
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        anchor = window.document.createElement("a")
        anchor.href = f"data:{mime_type};base64,{encoded}"
        anchor.download = path.name
        window.document.body.appendChild(anchor)
        try:
            anchor.click()
        finally:
            anchor.remove()
    except Exception as exc:
        raise RuntimeError(
            f"Não foi possível descarregar {path.name}: "
            f"MM.download: {mm_error}; alternativa do navegador: {exc}"
        ) from exc


def save_state(state: dict) -> str:
    """Save a version 1 state locally and return its destination."""
    web = _is_web()
    # The pygbag JS bridge may corrupt non-ASCII characters sent directly to
    # localStorage. Escaped JSON stays ASCII in transit and restores Unicode
    # exactly when parsed. Exported and desktop JSON remain human-readable.
    text = _encode_state(state, ascii_only=web)
    if web:
        try:
            _web_window().localStorage.setItem(STORAGE_KEY, text)
        except Exception as exc:
            raise RuntimeError("Não foi possível guardar a tática no navegador.") from exc
        return "armazenamento local do navegador"

    path = _desktop_path(SAVE_FILENAME)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Não foi possível guardar a tática em {path}.") from exc
    return str(path)


def load_state() -> dict:
    """Load a version 1 state from localStorage or the desktop save file."""
    if _is_web():
        try:
            text = _web_window().localStorage.getItem(STORAGE_KEY)
        except Exception as exc:
            raise RuntimeError("Não foi possível abrir a tática no navegador.") from exc
        if text is None:
            raise FileNotFoundError("Ainda não existe uma tática guardada no navegador.")
        text = str(text)
    else:
        path = _desktop_path(SAVE_FILENAME)
        try:
            if path.stat().st_size > MAX_JSON_BYTES:
                raise ValueError("O ficheiro de tática excede o limite de 1 MB.")
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Ainda não existe uma tática guardada em {path}.") from exc
        except UnicodeError as exc:
            raise ValueError("O ficheiro de tática não está codificado em UTF-8.") from exc
        except OSError as exc:
            raise OSError(f"Não foi possível abrir a tática em {path}.") from exc
    return _decode_state(text)


def export_json(state: dict) -> str:
    """Write a portable JSON file, downloading it in the browser."""
    text = _encode_state(state)
    path = _web_export_path(EXPORT_JSON_FILENAME) if _is_web() else _desktop_path(EXPORT_JSON_FILENAME)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Não foi possível exportar o JSON para {path}.") from exc
    if _is_web():
        _download(path, "application/json;charset=utf-8")
        return EXPORT_JSON_FILENAME
    return str(path)


def export_png(surface) -> str:
    """Write a pygame surface as PNG, downloading it in the browser."""
    import pygame

    path = _web_export_path(EXPORT_PNG_FILENAME) if _is_web() else _desktop_path(EXPORT_PNG_FILENAME)
    try:
        pygame.image.save(surface, str(path))
    except (OSError, pygame.error) as exc:
        raise OSError(f"Não foi possível exportar a imagem para {path}.") from exc
    if _is_web():
        _download(path, "image/png")
        return EXPORT_PNG_FILENAME
    return str(path)


def _desktop_import_path():
    """Ask for a JSON file, falling back to the last export without Tk."""
    try:
        # Pygbag scans static imports even in desktop-only branches.
        filedialog = importlib.import_module("tkinter.filedialog")

        selected = filedialog.askopenfilename(
            title="Abrir tática JSON",
            filetypes=[("Tática JSON", "*.json"), ("Todos os ficheiros", "*.*")],
        )
    except Exception:
        # Tk may be absent or unusable in headless desktop environments.
        return _desktop_path(EXPORT_JSON_FILENAME)
    return Path(selected) if selected else None


def _on_browser_upload(event):
    global _pending_import_callback

    callback = _pending_import_callback
    _pending_import_callback = None
    if callback is None:
        return
    try:
        if int(event.size) > MAX_JSON_BYTES:
            raise ValueError("O ficheiro de tática excede o limite de 1 MB.")
        # Pygbag's upload event puts the file contents in its virtual /tmp
        # filesystem. event.text is the path, despite that field's name.
        path = Path(str(event.text))
        state = _decode_state(path.read_text(encoding="utf-8"))
    except UnicodeError:
        callback(None, ValueError("O ficheiro de tática não está codificado em UTF-8."))
    except Exception as exc:
        callback(None, exc)
    else:
        callback(state, None)


def import_json_file(callback) -> None:
    """Import a version 1 JSON document and call ``callback(state, error)``.

    On desktop this is synchronous and uses Tk's file dialog, or
    ``tactic-export.json`` when Tk is unavailable. In pygbag this uses its
    ``webbrowser.open_file`` extension and reads the virtual file named by
    ``event.text`` in the runtime's upload event. The browser operation
    finishes asynchronously.
    Browser upload support depends on this pygbag-specific API.
    """
    if not callable(callback):
        raise TypeError("A importação requer uma função de resposta.")

    if _is_web():
        import webbrowser

        global _pending_import_callback, _upload_handler_registered
        _pending_import_callback = callback
        try:
            _web_window().eval(_UPLOAD_SETUP_JS)
            if _upload_handler_registered:
                webbrowser.open_file()
            else:
                webbrowser.open_file(_on_browser_upload)
                _upload_handler_registered = True
        except Exception as exc:
            _pending_import_callback = None
            callback(None, RuntimeError(f"Não foi possível abrir o seletor de ficheiros do navegador: {exc}"))
        return

    try:
        path = _desktop_import_path()
        if path is None:
            raise FileNotFoundError("Nenhum ficheiro de tática foi selecionado.")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ValueError("O ficheiro de tática excede o limite de 1 MB.")
        state = _decode_state(path.read_text(encoding="utf-8"))
    except UnicodeError:
        callback(None, ValueError("O ficheiro de tática não está codificado em UTF-8."))
    except Exception as exc:
        callback(None, exc)
    else:
        callback(state, None)
