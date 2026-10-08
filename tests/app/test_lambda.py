"""Guarda do deploy: o código precisa importar do jeito que a Lambda importa.

Na Lambda a raiz é src/ e o handler é app.main.handler. Um `from src.app...`
dentro de src/app/ passa nos outros testes (que rodam da raiz do repo) e
quebra em produção com ModuleNotFoundError. Este teste pega isso antes.
"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_app_importa_com_src_como_raiz():
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=SRC,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
