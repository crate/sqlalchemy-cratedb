from sqlalchemy_cratedb import DUMMY


def test_dummy():
    assert DUMMY == 42
