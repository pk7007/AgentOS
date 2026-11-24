from agentos.redact import redact, redact_obj


def test_redacts_known_secrets():
    t, n = redact("key sk-abcdefghijklmnop1234 and password: hunter2")
    assert "sk-abc" not in t and "hunter2" not in t and n == 2


def test_redacts_github_and_aws_and_private_key():
    pk = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"
    text = f"ghp_{'a' * 30} AKIA{'B' * 16} {pk} xoxb-1234567890-abc"
    t, n = redact(text)
    assert "ghp_" not in t and "AKIA" not in t and "MIIabc" not in t and "xoxb-" not in t
    assert n == 4


def test_keeps_label_redacts_value():
    t, _ = redact("api_key = XYZ987")
    assert t.startswith("api_key") and "XYZ987" not in t


def test_plain_text_untouched():
    assert redact("nothing secret here") == ("nothing secret here", 0)


def test_redact_obj_recurses():
    out = redact_obj({"a": ["password=x1", {"b": "token: t2"}], "n": 5})
    assert "x1" not in str(out) and "t2" not in str(out) and out["n"] == 5
