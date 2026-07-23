import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import research_sources_index as rsi


def _write(dirpath, name, text):
    with open(os.path.join(dirpath, name), "w", encoding="utf-8") as f:
        f.write(text)


def test_collects_markdown_links_across_files():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "a.md", "See [Issue #502](https://github.com/x/y/issues/502) for detail.")
        _write(d, "b.md", "Also references [Issue #502](https://github.com/x/y/issues/502) again.")
        sources = rsi.collect_sources(d)
        assert "https://github.com/x/y/issues/502" in sources
        entry = sources["https://github.com/x/y/issues/502"]
        assert entry["files"] == {"a.md", "b.md"}
        assert "Issue #502" in entry["texts"]


def test_ignores_non_markdown_and_non_url_links():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "a.md", "A [local link](./other.md) and [bad](not-a-url) should not appear.")
        _write(d, "notes.txt", "[fake](https://example.com/should-not-be-scanned)")
        sources = rsi.collect_sources(d)
        assert sources == {}


def test_render_index_sorts_by_domain_and_lists_citing_files():
    sources = {
        "https://zeta.example.com/page": {"texts": {"Zeta"}, "files": {"z.md"}},
        "https://alpha.example.com/page": {"texts": {"Alpha"}, "files": {"a.md", "b.md"}},
    }
    text = rsi.render_index(sources)
    alpha_pos = text.index("alpha.example.com")
    zeta_pos = text.index("zeta.example.com")
    assert alpha_pos < zeta_pos
    assert "cited in: a.md, b.md" in text


def test_main_writes_out_file_and_reports_count(capsys):
    with tempfile.TemporaryDirectory() as d:
        _write(d, "a.md", "[Source](https://example.com/one)")
        out_path = os.path.join(d, "SOURCES_INDEX.md")
        rc = rsi.main([d, "--out", out_path])
        assert rc == 0
        assert os.path.isfile(out_path)
        content = open(out_path).read()
        assert "https://example.com/one" in content


def test_main_exits_2_on_missing_directory():
    rc = rsi.main(["/nonexistent/path/xyz"])
    assert rc == 2


def test_main_missing_out_value_exits_cleanly_not_indexerror():
    # --out given with no following value used to raise an unhandled
    # IndexError (argv[argv.index("--out") + 1] out of range); it must now
    # exit cleanly with a non-zero code instead of crashing.
    with tempfile.TemporaryDirectory() as d:
        rc = rsi.main([d, "--out"])
        assert rc == 2


def test_main_with_no_out_prints_to_stdout(capsys):
    with tempfile.TemporaryDirectory() as d:
        _write(d, "a.md", "[Source](https://example.com/two)")
        rc = rsi.main([d])
        assert rc == 0
        captured = capsys.readouterr()
        assert "https://example.com/two" in captured.out
