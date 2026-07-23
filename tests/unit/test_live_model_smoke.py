import asyncio

from pytest import CaptureFixture, MonkeyPatch

from jarvis.models import live_smoke


def test_live_smoke_is_explicitly_blocked_without_both_credentials(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = asyncio.run(live_smoke._main())

    captured = capsys.readouterr()
    assert result == 2
    assert "BLOCKED" in captured.err
    assert "OPENAI_API_KEY" in captured.err
    assert "DEEPSEEK_API_KEY" in captured.err
