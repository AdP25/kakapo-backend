from pathlib import Path


def test_expected_paths_exist():
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / "README.md",
        root / "pyproject.toml",
        root / ".env.example",
        root / "Dockerfile",
        root / "src" / "backend" / "proxy.py",
        root / "src" / "backend" / "requirements-docker.txt",
        root / "src" / "backend" / "seed_cache.py",
    ]
    for path in expected:
        assert path.exists(), f"Missing required path: {path}"
