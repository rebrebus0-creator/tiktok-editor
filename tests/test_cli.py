from stock_media.cli import main


def test_check_reports_missing_keys(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.setenv("STOCK_MEDIA_CACHE_DIR", str(tmp_path))

    assert main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "не задан PEXELS_API_KEY" in out
    assert "не задан PIXABAY_API_KEY" in out
    assert "openverse" in out


def test_check_marks_configured_provider(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("PEXELS_API_KEY", "abc")
    monkeypatch.setenv("STOCK_MEDIA_CACHE_DIR", str(tmp_path))

    main(["--check"])
    lines = capsys.readouterr().out.splitlines()
    pexels_line = next(line for line in lines if "pexels" in line)
    assert "[ок]" in pexels_line


def test_brief_is_required_without_check(capsys):
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
        assert "--check" in capsys.readouterr().err
    else:
        raise AssertionError("ожидали SystemExit")


def test_warns_when_no_provider_handles_video(monkeypatch, capsys, tmp_path):
    # Только Openverse — он умеет фото, но не видео.
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.setenv("STOCK_MEDIA_CACHE_DIR", str(tmp_path))

    code = main(["бег по набережной", "--kind", "video", "--dry-run"])
    captured = capsys.readouterr()
    assert code == 1
    assert "ни один включённый провайдер не умеет отдавать video" in captured.err
    assert "--check" in captured.err
