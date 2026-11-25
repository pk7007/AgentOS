import os
import subprocess
import sys

RUN = "import sys; from agentos.cli import main; sys.exit(main(sys.argv[1:]))"


def _agentos(home, *args):
    env = dict(os.environ, AGENTOS_HOME=str(home))
    return subprocess.run([sys.executable, "-c", RUN, *args], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120, check=False)


def test_cli_retire_without_tty_denied(home):
    assert _agentos(home, "init").returncode == 0
    assert _agentos(home, "template", "seed").returncode == 0
    r = _agentos(home, "template", "retire", "implementer", "--reason", "r")
    assert r.returncode == 3 and "terminal" in r.stderr


def test_cli_lift_stop_without_tty_denied(home):
    _agentos(home, "init")
    assert _agentos(home, "stop", "--reason", "drill").returncode == 0
    assert _agentos(home, "stop", "--lift").returncode == 3


def test_cli_raise_limit_without_tty_denied(home):
    _agentos(home, "init")
    assert _agentos(home, "limits", "set", "max_concurrent", "10").returncode == 3


def test_no_env_var_bypass(home):
    _agentos(home, "init")
    _agentos(home, "stop", "--reason", "drill")
    env_args = dict(os.environ, AGENTOS_HOME=str(home), AGENTOS_OWNER_CONFIRM="1")
    r = subprocess.run([sys.executable, "-c", RUN, "stop", "--lift"], env=env_args, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120, check=False)
    assert r.returncode == 3
