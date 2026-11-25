"""`template add` must report bad files as usage errors (exit 2), never a traceback."""


def test_template_add_bom_file(cli, home, tmp_path):
    cli(["init"])
    f = tmp_path / "t.toml"
    f.write_bytes(b"\xef\xbb\xbf" + b'id = "docs"\nname = "Docs"\nrole = "writer"\ndepartment = "eng"\n'
                  b'description = "d"\ncapabilities = ["docs"]\ninstructions = "write docs"\n')
    code, _, err = cli(["template", "add", str(f)])
    assert code == 0, err


def test_template_add_invalid_schema(cli, home, tmp_path):
    cli(["init"])
    f = tmp_path / "t.toml"
    f.write_text('id = "Bad Id"\n')
    code, _, err = cli(["template", "add", str(f)])
    assert code == 2 and "invalid template" in err


def test_template_add_missing_file(cli, home, tmp_path):
    cli(["init"])
    code, _, err = cli(["template", "add", str(tmp_path / "nope.toml")])
    assert code == 2 and "cannot read" in err
