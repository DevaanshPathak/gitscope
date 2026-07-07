from gitscope import __version__
from gitscope.app import GitscopeApp
from gitscope.cli import main


def test_package_exposes_version() -> None:
    assert __version__ == "1.0.0"


def test_textual_app_can_be_constructed() -> None:
    app = GitscopeApp()

    assert app.TITLE == "gitscope"


def test_cli_version_can_be_invoked(capsys) -> None:
    exit_code = main(["--version"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "gitscope 1.0.0"
