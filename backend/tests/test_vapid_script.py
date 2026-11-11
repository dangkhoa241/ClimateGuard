"""scripts/make_vapid_keys.py: the private key goes to SSM as a SecureString and is never printed."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import make_vapid_keys as mk  # noqa: E402


class ParameterNotFound(Exception):
    pass


class FakeSsm:
    def __init__(self, existing=None):
        self.store, self.puts = ({mk.PARAM: existing} if existing else {}), []

    def get_parameter(self, Name, WithDecryption=False):
        if Name not in self.store:
            raise ParameterNotFound(Name)
        return {"Parameter": {"Value": self.store[Name]}}

    def put_parameter(self, **kw):
        self.puts.append(kw)
        self.store[kw["Name"]] = kw["Value"]


def test_pair_is_a_valid_p256_key_and_public_matches_private():
    private, public = mk.generate_pair()
    assert len(private) == 43
    assert mk.public_from_private(private) == public
    raw = base64.urlsafe_b64decode(public + "=" * (-len(public) % 4))
    assert len(raw) == 65 and raw[0] == 4  # what browsers need as applicationServerKey


def test_creates_a_securestring_and_prints_only_the_public_key(capsys):
    ssm = FakeSsm()
    assert mk.main([], client=ssm) == 0
    out = capsys.readouterr()
    put = ssm.puts[0]
    assert put["Type"] == "SecureString" and put["Name"] == "/climateguard/vapid-private-key"
    assert put["Overwrite"] is False
    assert put["Value"] not in out.out + out.err
    assert mk.public_from_private(put["Value"]) in out.out


def test_never_overwrites_without_force(capsys):
    private, _ = mk.generate_pair()
    ssm = FakeSsm(existing=private)
    assert mk.main([], client=ssm) == 1
    assert ssm.puts == [] and ssm.store[mk.PARAM] == private
    assert mk.main(["--force"], client=ssm) == 0 and ssm.puts[0]["Overwrite"] is True
    assert private not in capsys.readouterr().out


def test_show_public_prints_only_the_public_key(capsys):
    private, public = mk.generate_pair()
    assert mk.main(["--show-public"], client=FakeSsm(existing=private)) == 0
    out = capsys.readouterr().out
    assert public in out and private not in out
