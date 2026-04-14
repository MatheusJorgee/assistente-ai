#!/usr/bin/env python3
"""
Quinta-Feira Manager
Orquestrador unico para iniciar, monitorar e parar o sistema.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class ManagerConfig:
    project_root: Path
    backend_dir: Path
    frontend_dir: Path
    runtime_dir: Path
    logs_dir: Path
    state_file: Path
    backend_log: Path
    frontend_log: Path
    frontend_url: str = "http://localhost:3000"
    backend_port: int = 8000
    frontend_port: int = 3000


class QuintaManager:
    LEGACY_ROOT_FILES = ["iniciar.bat", "encerrar.bat", "reiniciar.bat", "INICIAR.bat"]
    LEGACY_SHORTCUTS = [
        "iniciar.lnk",
        "encerrar.lnk",
        "reiniciar.lnk",
        "QuintaFeira-Iniciar.lnk",
        "QuintaFeira-Parar.lnk",
        "INICIAR.lnk",
    ]

    def __init__(self, config: ManagerConfig):
        self.config = config
        self.config.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.config.logs_dir.mkdir(parents=True, exist_ok=True)

    def setup_cleanup(self) -> None:
        print("\n[SETUP] Limpando artefatos legados...")
        removed_root = self._remove_legacy_root_files()
        removed_shortcuts = self._remove_legacy_desktop_shortcuts()
        print(f"[SETUP] Arquivos removidos na raiz: {removed_root}")
        print(f"[SETUP] Atalhos removidos no Desktop: {removed_shortcuts}")

    def start_system(self) -> None:
        state = self._load_state()

        backend_pid = state.get("backend_pid")
        frontend_pid = state.get("frontend_pid")

        if backend_pid and self._is_pid_alive(backend_pid):
            print(f"[INFO] Backend ja em execucao (PID {backend_pid}).")
        else:
            backend_process = self._start_backend()
            state["backend_pid"] = backend_process.pid
            print(f"[OK] Backend iniciado (PID {backend_process.pid}).")

        if frontend_pid and self._is_pid_alive(frontend_pid):
            print(f"[INFO] Frontend ja em execucao (PID {frontend_pid}).")
        else:
            frontend_process = self._start_frontend()
            state["frontend_pid"] = frontend_process.pid
            print(f"[OK] Frontend iniciado (PID {frontend_process.pid}).")

        state["last_start_ts"] = int(time.time())
        self._save_state(state)

        # A opcao de inicio completo tambem abre a interface visual.
        self.open_visual_interface()

    def open_visual_interface(self) -> None:
        print(f"[INFO] Abrindo navegador em {self.config.frontend_url}")
        webbrowser.open(self.config.frontend_url)

    def tail_backend_logs(self) -> None:
        log_file = self.config.backend_log
        if not log_file.exists():
            print("[WARN] Log do backend ainda nao existe. Inicie o sistema antes.")
            return

        print("\n[LOGS] Exibindo logs do backend em tempo real.")
        print("[LOGS] Pressione Ctrl+C para sair dos logs.\n")

        with log_file.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            try:
                while True:
                    line = fh.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.2)
            except KeyboardInterrupt:
                print("\n[LOGS] Visualizacao encerrada.")

    def stop_all(self) -> None:
        print("\n[STOP] Encerrando todos os processos gerenciados...")
        state = self._load_state()

        pids = [
            ("backend", state.get("backend_pid")),
            ("frontend", state.get("frontend_pid")),
        ]

        for label, pid in pids:
            if pid:
                killed = self._kill_process_tree(pid)
                status = "OK" if killed else "NAO ENCONTRADO"
                print(f"[STOP] {label}: {status} (PID {pid})")

        # Fallback agressivo por porta para evitar processos orfaos.
        self._kill_by_port(self.config.backend_port)
        self._kill_by_port(self.config.frontend_port)

        self._save_state({})
        print("[STOP] Limpeza concluida.")

    def create_desktop_shortcut(self) -> None:
        desktop = self._desktop_path()
        if desktop is None:
            print("[WARN] Desktop do Windows nao encontrado.")
            return

        python_executable = self._resolve_python_executable()
        manager_script = self.config.project_root / "quinta_manager.py"
        shortcut_path = desktop / "Quinta-Feira.lnk"

        manager_arg = '"' + str(manager_script).replace('"', '""') + '"'

        ps_script = (
            "$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path.as_posix()}'); "
            f"$Shortcut.TargetPath = '{python_executable.as_posix()}'; "
            f"$Shortcut.Arguments = '{manager_arg}'; "
            f"$Shortcut.WorkingDirectory = '{self.config.project_root.as_posix()}'; "
            "$Shortcut.WindowStyle = 1; "
            "$Shortcut.Description = 'Orquestrador Quinta-Feira'; "
            "$Shortcut.Save();"
        )

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"[OK] Atalho criado/atualizado: {shortcut_path}")
        else:
            print("[ERRO] Falha ao criar atalho.")
            if result.stderr:
                print(result.stderr.strip())

    def run_menu(self) -> None:
        while True:
            print("\n" + "=" * 56)
            print("      QUINTA-FEIRA MANAGER - ORQUESTRADOR UNICO")
            print("=" * 56)
            print("[1] Iniciar Sistema Completo")
            print("[2] Abrir Interface Visual")
            print("[3] Ver Logs (backend)")
            print("[4] Parar Tudo")
            print("[0] Sair")
            print("=" * 56)

            choice = input("Escolha uma opcao: ").strip()

            if choice == "1":
                self.start_system()
            elif choice == "2":
                self.open_visual_interface()
            elif choice == "3":
                self.tail_backend_logs()
            elif choice == "4":
                self.stop_all()
            elif choice == "0":
                print("Saindo do manager.")
                return
            else:
                print("Opcao invalida. Tente novamente.")

    def _start_backend(self) -> subprocess.Popen:
        python_executable = self._resolve_python_executable()

        cmd = [
            str(python_executable),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.config.backend_port),
            "--reload",
        ]

        return self._spawn_process(
            cmd=cmd,
            cwd=self.config.backend_dir,
            log_file=self.config.backend_log,
        )

    def _start_frontend(self) -> subprocess.Popen:
        npm_executable = "npm.cmd" if os.name == "nt" else "npm"
        cmd = [npm_executable, "run", "dev"]

        return self._spawn_process(
            cmd=cmd,
            cwd=self.config.frontend_dir,
            log_file=self.config.frontend_log,
        )

    def _spawn_process(self, cmd: list[str], cwd: Path, log_file: Path) -> subprocess.Popen:
        with log_file.open("a", encoding="utf-8") as _:
            pass

        log_handle = log_file.open("a", encoding="utf-8")

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            text=True,
        )
        # O processo filho ja herdou o handle; fechamos no pai para evitar vazamento.
        log_handle.close()
        return process

    def _kill_process_tree(self, pid: int) -> bool:
        if not self._is_pid_alive(pid):
            return False

        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0

        # Compatibilidade basica para ambientes nao-Windows.
        try:
            os.killpg(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

    def _kill_by_port(self, port: int) -> None:
        if os.name != "nt":
            return

        cmd = (
            f"Get-NetTCPConnection -LocalPort {port} -State Listen "
            "-ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty OwningProcess -Unique"
        )

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return

        for token in result.stdout.splitlines():
            token = token.strip()
            if not token.isdigit():
                continue
            self._kill_process_tree(int(token))

    def _remove_legacy_root_files(self) -> int:
        removed = 0
        for name in self.LEGACY_ROOT_FILES:
            file_path = self.config.project_root / name
            if file_path.exists():
                try:
                    file_path.unlink()
                    removed += 1
                except OSError as exc:
                    print(f"[WARN] Nao foi possivel remover {file_path}: {exc}")
        return removed

    def _remove_legacy_desktop_shortcuts(self) -> int:
        desktop = self._desktop_path()
        if desktop is None:
            return 0

        removed = 0
        for name in self.LEGACY_SHORTCUTS:
            shortcut = desktop / name
            if shortcut.exists():
                try:
                    shortcut.unlink()
                    removed += 1
                except OSError as exc:
                    print(f"[WARN] Nao foi possivel remover {shortcut}: {exc}")

        return removed

    def _desktop_path(self) -> Optional[Path]:
        candidates = [
            Path.home() / "Desktop",
            Path(os.environ.get("USERPROFILE", "")) / "Desktop",
            Path(os.environ.get("OneDrive", "")) / "Desktop",
        ]

        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return None

    def _resolve_python_executable(self) -> Path:
        candidates = [
            self.config.project_root / ".venv" / "Scripts" / "python.exe",
            self.config.backend_dir / ".venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return Path("python")

    def _load_state(self) -> Dict[str, int]:
        if not self.config.state_file.exists():
            return {}

        try:
            with self.config.state_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, state: Dict[str, int]) -> None:
        with self.config.state_file.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)

    def _is_pid_alive(self, pid: int) -> bool:
        if not isinstance(pid, int) or pid <= 0:
            return False

        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                check=False,
                capture_output=True,
                text=True,
            )
            return str(pid) in result.stdout

        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def build_config() -> ManagerConfig:
    project_root = Path(__file__).resolve().parent
    runtime_dir = project_root / ".runtime"
    logs_dir = runtime_dir / "logs"

    return ManagerConfig(
        project_root=project_root,
        backend_dir=project_root / "backend",
        frontend_dir=project_root / "frontend",
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        state_file=runtime_dir / "quinta_manager_state.json",
        backend_log=logs_dir / "backend.log",
        frontend_log=logs_dir / "frontend.log",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quinta-Feira Manager")
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Executa apenas a limpeza de legado e sai.",
    )
    parser.add_argument(
        "--create-shortcut",
        action="store_true",
        help="Cria/atualiza o atalho Quinta-Feira na Area de Trabalho.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manager = QuintaManager(build_config())

    manager.setup_cleanup()

    if args.create_shortcut:
        manager.create_desktop_shortcut()

    if args.setup_only:
        return

    manager.run_menu()


if __name__ == "__main__":
    main()
