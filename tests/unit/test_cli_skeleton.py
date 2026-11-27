import agentos


def test_version_flag(cli):
    code, out, _ = cli(["--version"])
    assert code == 0 and agentos.__version__ in out


def test_unknown_command_exit_2(cli):
    code, _, _ = cli(["nope"])
    assert code == 2


def test_agentos_error_maps_exit_code():
    from agentos.errors import PolicyDenied

    e = PolicyDenied("no", reasons=["limit"])
    assert e.exit_code == 3 and e.reasons == ["limit"]
