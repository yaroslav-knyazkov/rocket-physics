# -*- coding: utf-8 -*-
"""Tests for .claude/scripts/token_usage.py.

Run from repo root:
    PYTHONUTF8=1 python -m pytest .claude/scripts/tests/test_token_usage.py -v

Everything is synthetic fixtures under tmp_path: real ~/.claude/projects logs are
never opened (and the script never writes anything at all — checked separately).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import token_usage  # noqa: E402


# ---------------------------------------------------------------------------
# jsonl row builders
# ---------------------------------------------------------------------------

def usage(input_tokens=0, output_tokens=0, cache_creation=0, cache_read=0) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
    }


def row(msg_id, model, u, block_type="text", is_error=False) -> dict:
    r = {
        "type": "assistant",
        "message": {
            "id": msg_id,
            "model": model,
            "content": [{"type": block_type, "text": "x"}],
            "usage": u,
        },
    }
    if is_error:
        r["isApiErrorMessage"] = True
    return r


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


PRICES = {
    "opus": {"input": 15, "output": 75, "cache_write": 18.75, "cache_read": 1.50},
    "sonnet": {"input": 3, "output": 15, "cache_write": 3.75, "cache_read": 0.30},
    "haiku": {"input": 1, "output": 5, "cache_write": 1.25, "cache_read": 0.10},
}


@pytest.fixture()
def price_file(tmp_path: Path) -> Path:
    p = tmp_path / "prices.json"
    p.write_text(json.dumps({"_comment": "test fixture, not real prices", **PRICES}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_messages: the dedup fix itself
# ---------------------------------------------------------------------------

def test_multi_block_rows_sharing_one_id_counted_once(tmp_path):
    """thinking + tool_use + tool_use rows for the same message must collapse to one."""
    u = usage(input_tokens=2, output_tokens=402, cache_creation=25800, cache_read=17676)
    rows = [
        row("msg_1", "claude-opus-5", u, block_type="thinking"),
        row("msg_1", "claude-opus-5", u, block_type="tool_use"),
        row("msg_1", "claude-opus-5", u, block_type="tool_use"),
    ]
    path = tmp_path / "session.jsonl"
    write_jsonl(path, rows)

    messages = token_usage.load_messages(path)

    assert len(messages) == 1
    assert messages[0]["usage"] == u


def test_streaming_partial_takes_max_output_not_sum(tmp_path):
    """output_tokens grows across streaming-partial rows; cache/input stay identical."""
    rows = [
        row("msg_2", "claude-sonnet-5", usage(input_tokens=3, output_tokens=4, cache_creation=200, cache_read=100)),
        row("msg_2", "claude-sonnet-5", usage(input_tokens=3, output_tokens=159, cache_creation=200, cache_read=100)),
    ]
    path = tmp_path / "session.jsonl"
    write_jsonl(path, rows)

    messages = token_usage.load_messages(path)

    assert len(messages) == 1
    u = messages[0]["usage"]
    assert u["output_tokens"] == 159            # max, not sum (4+159=163 would be wrong)
    assert u["cache_creation_input_tokens"] == 200   # not doubled to 400
    assert u["cache_read_input_tokens"] == 100       # not doubled to 200
    assert u["input_tokens"] == 3


def test_rows_without_message_id_are_not_merged(tmp_path):
    """Two distinct anonymous rows must stay two messages, not collapse into one."""
    rows = [
        {"type": "assistant", "message": {"model": "claude-sonnet-5", "usage": usage(output_tokens=10)}},
        {"type": "assistant", "message": {"model": "claude-sonnet-5", "usage": usage(output_tokens=20)}},
    ]
    path = tmp_path / "session.jsonl"
    write_jsonl(path, rows)

    messages = token_usage.load_messages(path)

    assert len(messages) == 2
    assert {m["usage"]["output_tokens"] for m in messages} == {10, 20}


def test_missing_file_returns_empty_list(tmp_path):
    assert token_usage.load_messages(tmp_path / "does-not-exist.jsonl") == []


def test_rows_without_usage_are_skipped(tmp_path):
    rows = [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        row("msg_3", "claude-sonnet-5", usage(output_tokens=5)),
    ]
    path = tmp_path / "session.jsonl"
    write_jsonl(path, rows)

    messages = token_usage.load_messages(path)
    assert len(messages) == 1
    assert messages[0]["usage"]["output_tokens"] == 5


# ---------------------------------------------------------------------------
# pricing
# ---------------------------------------------------------------------------

def test_model_family_matches_by_substring():
    assert token_usage.model_family("claude-opus-5") == "opus"
    assert token_usage.model_family("claude-sonnet-5") == "sonnet"
    assert token_usage.model_family("claude-haiku-4") == "haiku"
    assert token_usage.model_family("<synthetic>") is None
    assert token_usage.model_family(None) is None


def test_cost_usd_hand_computed():
    u = usage(input_tokens=1000, output_tokens=1000, cache_creation=1000, cache_read=1000)
    price = PRICES["sonnet"]
    expected = (1000 * 3 + 1000 * 15 + 1000 * 3.75 + 1000 * 0.30) / 1_000_000
    assert token_usage.cost_usd(u, price) == pytest.approx(expected)


def test_cost_usd_none_price_is_zero():
    u = usage(input_tokens=1000, output_tokens=1000, cache_creation=1000, cache_read=1000)
    assert token_usage.cost_usd(u, None) == 0.0


def test_unknown_model_family_zero_cost_no_crash():
    label, price = token_usage.classify_model("some-future-model-x1", PRICES)
    assert label == "unknown"
    assert price is None
    u = usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_creation=1_000_000, cache_read=1_000_000)
    assert token_usage.cost_usd(u, price) == 0.0


def test_load_prices_strips_comment_key(price_file):
    prices = token_usage.load_prices(price_file)
    assert "_comment" not in prices
    assert set(prices) == {"opus", "sonnet", "haiku"}


def test_load_prices_missing_file_is_empty_dict(tmp_path):
    assert token_usage.load_prices(tmp_path / "nope.json") == {}


# ---------------------------------------------------------------------------
# session fixture for main()
# ---------------------------------------------------------------------------

SESSION_ID = "aaaaaaaa-1111-2222-3333-444444444444"


@pytest.fixture()
def session(tmp_path: Path):
    """A synthetic ~/.claude/projects/<slug>/ tree with a main thread and two subagents."""
    projects_root = tmp_path / "projects"
    proj = projects_root / "some-project-slug"
    proj.mkdir(parents=True)

    main_rows = [
        row("m1", "claude-opus-5", usage(input_tokens=10, output_tokens=100, cache_creation=1000, cache_read=5000)),
        row("m2", "claude-opus-5", usage(input_tokens=5, output_tokens=50, cache_creation=0, cache_read=1000)),
        # api-error / synthetic placeholder — must cost $0 and not pollute model mix
        row("m3", "<synthetic>", usage(), is_error=True),
    ]
    write_jsonl(proj / f"{SESSION_ID}.jsonl", main_rows)

    subagents_dir = proj / SESSION_ID / "subagents"
    subagents_dir.mkdir(parents=True)

    dev_rows = [
        row("s1", "claude-sonnet-5", usage(input_tokens=20, output_tokens=200, cache_creation=2000, cache_read=9000)),
        row("s1", "claude-sonnet-5", usage(input_tokens=20, output_tokens=200, cache_creation=2000, cache_read=9000)),
    ]
    write_jsonl(subagents_dir / "agent-dev1.jsonl", dev_rows)
    (subagents_dir / "agent-dev1.meta.json").write_text(
        json.dumps({"agentType": "developer", "description": "test task", "model": "sonnet"}), encoding="utf-8")

    # no meta.json here -> falls back to file stem
    nomega_rows = [row("s2", "claude-sonnet-5", usage(input_tokens=1, output_tokens=1))]
    write_jsonl(subagents_dir / "agent-nometa.jsonl", nomega_rows)

    return projects_root


def run_main(argv):
    return token_usage.main(argv)


def base_args(session, price_file, extra=()):
    return ["--session-id", SESSION_ID, "--projects-root", str(session), "--price-file", str(price_file), *extra]


# ---------------------------------------------------------------------------
# main(): behaviour
# ---------------------------------------------------------------------------

def test_main_reports_cost_and_dedup_across_agents(session, price_file, capsys):
    code = run_main(base_args(session, price_file))
    assert code == 0
    out = capsys.readouterr().out
    assert "Итог по сессии" in out
    assert "Оценочная стоимость" in out
    assert "developer" in out
    assert "agent-nometa" in out          # fallback to file stem


def test_main_json_is_valid_and_consistent(session, price_file, capsys):
    code = run_main(base_args(session, price_file, ["--json"]))
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["session_id"] == SESSION_ID
    # component costs must sum to the grand total (single source of truth invariant)
    assert sum(data["cost_by_component"].values()) == pytest.approx(data["cost_usd"], rel=1e-9)
    # per-agent costs must also sum to the grand total
    assert sum(a["cost_usd"] for a in data["agents"]) == pytest.approx(data["cost_usd"], rel=1e-6)
    assert data["api_errors"] == 1


def test_main_marks_synthetic_row_as_api_error_not_unknown_model(session, price_file, capsys):
    code = run_main(base_args(session, price_file, ["--json"]))
    data = json.loads(capsys.readouterr().out)
    assert data["api_errors"] == 1
    assert data["unknown_models"] == []       # <synthetic> must not trigger the unknown-model warning


def test_main_missing_session_file_exits_1(tmp_path, price_file, capsys):
    empty_root = tmp_path / "empty-projects"
    empty_root.mkdir()
    code = token_usage.main(["--session-id", "no-such-session", "--projects-root", str(empty_root),
                              "--price-file", str(price_file)])
    assert code == 1
    err = capsys.readouterr().err
    assert "no-such-session" in err
    assert "Traceback" not in err


def test_main_missing_session_id_exits_1(tmp_path, price_file, capsys, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    code = token_usage.main(["--projects-root", str(tmp_path), "--price-file", str(price_file)])
    assert code == 1
    assert "session_id" in capsys.readouterr().err


def test_main_reads_session_id_from_env(session, price_file, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_ID)
    code = token_usage.main(["--projects-root", str(session), "--price-file", str(price_file)])
    assert code == 0
    assert "Итог по сессии" in capsys.readouterr().out


def test_main_top_n_default_and_full(session, price_file, capsys):
    code = run_main(base_args(session, price_file, ["--json"]))
    data = json.loads(capsys.readouterr().out)
    # only 3 agents exist here (MAIN + 2 subagents), all fit under the default top-8
    assert len(data["agents"]) == 3

    code = run_main(base_args(session, price_file, ["--full", "--json"]))
    data_full = json.loads(capsys.readouterr().out)
    assert len(data_full["agents"]) == len(data["agents"])


def test_unknown_model_in_real_session_warns_but_does_not_crash(tmp_path, price_file, capsys):
    projects_root = tmp_path / "projects"
    proj = projects_root / "slug"
    proj.mkdir(parents=True)
    rows = [row("m1", "some-brand-new-model", usage(input_tokens=10, output_tokens=10, cache_creation=10, cache_read=10))]
    write_jsonl(proj / f"{SESSION_ID}.jsonl", rows)

    code = token_usage.main(["--session-id", SESSION_ID, "--projects-root", str(projects_root),
                              "--price-file", str(price_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "some-brand-new-model" in out
    assert "Внимание" in out


def test_long_context_warning_fires_over_10_percent(tmp_path, price_file, capsys):
    projects_root = tmp_path / "projects"
    proj = projects_root / "slug"
    proj.mkdir(parents=True)
    rows = [row(f"m{i}", "claude-sonnet-5", usage(cache_read=250_000)) for i in range(3)]
    rows += [row(f"n{i}", "claude-sonnet-5", usage(cache_read=1)) for i in range(10)]
    write_jsonl(proj / f"{SESSION_ID}.jsonl", rows)

    code = token_usage.main(["--session-id", SESSION_ID, "--projects-root", str(projects_root),
                              "--price-file", str(price_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "200 000" in out or "200000" in out


def test_no_long_context_warning_under_threshold(session, price_file, capsys):
    code = run_main(base_args(session, price_file))
    assert code == 0
    out = capsys.readouterr().out
    assert "надбавку за тир" not in out


# ---------------------------------------------------------------------------
# agent_display_name
# ---------------------------------------------------------------------------

def test_agent_display_name_uses_agent_type(tmp_path):
    jf = tmp_path / "agent-x.jsonl"
    jf.write_text("", encoding="utf-8")
    (tmp_path / "agent-x.meta.json").write_text(json.dumps({"agentType": "qa"}), encoding="utf-8")
    assert token_usage.agent_display_name(jf) == "qa"


def test_agent_display_name_falls_back_to_stem_when_meta_missing(tmp_path):
    jf = tmp_path / "agent-y.jsonl"
    jf.write_text("", encoding="utf-8")
    assert token_usage.agent_display_name(jf) == "agent-y"


def test_agent_display_name_falls_back_to_stem_when_field_missing(tmp_path):
    jf = tmp_path / "agent-z.jsonl"
    jf.write_text("", encoding="utf-8")
    (tmp_path / "agent-z.meta.json").write_text(json.dumps({"description": "no type here"}), encoding="utf-8")
    assert token_usage.agent_display_name(jf) == "agent-z"


# ---------------------------------------------------------------------------
# read-only guarantee
# ---------------------------------------------------------------------------

def test_nothing_is_written(session, price_file, tmp_path, capsys):
    listing_before = sorted(p.name for p in tmp_path.iterdir())
    session_files_before = {p: p.read_bytes() for p in session.rglob("*") if p.is_file()}

    for args in (
        base_args(session, price_file),
        base_args(session, price_file, ["--json"]),
        base_args(session, price_file, ["--full"]),
    ):
        run_main(args)
    capsys.readouterr()

    assert sorted(p.name for p in tmp_path.iterdir()) == listing_before
    assert {p: p.read_bytes() for p in session.rglob("*") if p.is_file()} == session_files_before


def test_source_has_no_write_calls():
    src = Path(token_usage.__file__).read_text(encoding="utf-8")
    for forbidden in ("write_text", "write_bytes", "os.replace", "mkdir", "subprocess", "shutil"):
        assert forbidden not in src, f"read-only script must not contain {forbidden}"


# ---------------------------------------------------------------------------
# context_stats: peak/median ctx per agent
# ---------------------------------------------------------------------------

def _msg(cache_read=0, cache_creation=0, is_error=False):
    return {
        "model": "claude-sonnet-5",
        "usage": usage(cache_creation=cache_creation, cache_read=cache_read),
        "is_error": is_error,
    }


def test_context_stats_normal_case():
    messages = [_msg(cache_read=100), _msg(cache_read=300), _msg(cache_read=200)]
    peak, median = token_usage.context_stats(messages)
    assert peak == 300
    assert median == 200   # sorted [100, 200, 300], index 1


def test_context_stats_single_message():
    peak, median = token_usage.context_stats([_msg(cache_read=50, cache_creation=10)])
    assert peak == 60
    assert median == 60


def test_context_stats_empty_list():
    assert token_usage.context_stats([]) == (0, 0)


def test_context_stats_error_rows_only_are_zero_not_crash():
    messages = [_msg(cache_read=999_999, is_error=True), _msg(cache_read=500_000, is_error=True)]
    assert token_usage.context_stats(messages) == (0, 0)


def test_context_stats_excludes_error_rows_from_median():
    messages = [_msg(cache_read=100), _msg(cache_read=200), _msg(cache_read=999_999, is_error=True)]
    peak, median = token_usage.context_stats(messages)
    assert peak == 200          # the huge error-row value must not count
    assert median == 200        # sorted [100, 200], index len//2=1 -> upper-middle element


def test_top_table_and_json_include_peak_and_median_ctx(session, price_file, capsys):
    code = run_main(base_args(session, price_file))
    assert code == 0
    out = capsys.readouterr().out
    assert "Пик ctx" in out
    assert "Медиана ctx" in out

    code = run_main(base_args(session, price_file, ["--json"]))
    data = json.loads(capsys.readouterr().out)
    for a in data["agents"]:
        assert "peak_ctx" in a
        assert "median_ctx" in a


# ---------------------------------------------------------------------------
# load_frontmatter_default_model
# ---------------------------------------------------------------------------

@pytest.fixture()
def agents_dir(tmp_path: Path) -> Path:
    d = tmp_path / "agents"
    d.mkdir()
    (d / "documentation.md").write_text(
        "---\nname: documentation\ntools: Read, Write\nmodel: haiku\ncolor: pink\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (d / "qa.md").write_text(
        "---\nname: qa\ntools: Read\nmodel: sonnet\n---\n\nBody.\n", encoding="utf-8",
    )
    (d / "no-model-field.md").write_text(
        "---\nname: no-model-field\ntools: Read\n---\n\nBody.\n", encoding="utf-8",
    )
    (d / "architect.md").write_text(
        "---\nname: architect\ntools: Read\nmodel: opus\n---\n\nBody.\n", encoding="utf-8",
    )
    return d


def test_frontmatter_default_present(agents_dir):
    assert token_usage.load_frontmatter_default_model("documentation", agents_dir) == "haiku"
    assert token_usage.load_frontmatter_default_model("qa", agents_dir) == "sonnet"


def test_frontmatter_default_file_missing(agents_dir):
    assert token_usage.load_frontmatter_default_model("no-such-agent", agents_dir) is None


def test_frontmatter_default_field_missing(agents_dir):
    assert token_usage.load_frontmatter_default_model("no-model-field", agents_dir) is None


def test_frontmatter_default_agents_dir_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert token_usage.load_frontmatter_default_model("documentation", missing) is None


# ---------------------------------------------------------------------------
# load_agent_meta / agent_display_name refactor (single read)
# ---------------------------------------------------------------------------

def test_load_agent_meta_returns_dict(tmp_path):
    jf = tmp_path / "agent-x.jsonl"
    jf.write_text("", encoding="utf-8")
    (tmp_path / "agent-x.meta.json").write_text(json.dumps({"agentType": "qa", "model": "opus"}), encoding="utf-8")
    meta = token_usage.load_agent_meta(jf)
    assert meta == {"agentType": "qa", "model": "opus"}


def test_load_agent_meta_missing_file_returns_empty_dict(tmp_path):
    jf = tmp_path / "agent-y.jsonl"
    jf.write_text("", encoding="utf-8")
    assert token_usage.load_agent_meta(jf) == {}


def test_agent_display_name_accepts_preloaded_meta(tmp_path):
    jf = tmp_path / "agent-z.jsonl"
    jf.write_text("", encoding="utf-8")
    # no meta.json on disk at all — display name must come from the passed-in dict
    assert token_usage.agent_display_name(jf, meta={"agentType": "developer"}) == "developer"


# ---------------------------------------------------------------------------
# model-vs-frontmatter audit
# ---------------------------------------------------------------------------

@pytest.fixture()
def override_session(tmp_path: Path, agents_dir):
    """A session with three subagents: no override, redundant override, real mismatch."""
    projects_root = tmp_path / "projects"
    proj = projects_root / "slug"
    proj.mkdir(parents=True)
    write_jsonl(proj / f"{SESSION_ID}.jsonl",
                [row("m1", "claude-opus-5", usage(input_tokens=1, output_tokens=1))])

    subagents_dir = proj / SESSION_ID / "subagents"
    subagents_dir.mkdir(parents=True)

    # documentation: default haiku, override sonnet -> real mismatch
    write_jsonl(subagents_dir / "agent-doc.jsonl", [
        row("d1", "claude-sonnet-5", usage(input_tokens=100, output_tokens=100, cache_creation=1000, cache_read=2000)),
    ])
    (subagents_dir / "agent-doc.meta.json").write_text(
        json.dumps({"agentType": "documentation", "model": "sonnet"}), encoding="utf-8")

    # qa: default sonnet, override sonnet -> redundant
    write_jsonl(subagents_dir / "agent-qa.jsonl", [
        row("q1", "claude-sonnet-5", usage(input_tokens=10, output_tokens=10)),
    ])
    (subagents_dir / "agent-qa.meta.json").write_text(
        json.dumps({"agentType": "qa", "model": "sonnet"}), encoding="utf-8")

    # developer: no explicit model in meta at all -> no line
    write_jsonl(subagents_dir / "agent-dev.jsonl", [row("v1", "claude-sonnet-5", usage(input_tokens=1))])
    (subagents_dir / "agent-dev.meta.json").write_text(
        json.dumps({"agentType": "developer"}), encoding="utf-8")

    # architect: default opus, override haiku -> downgrade (forbidden by project rule)
    write_jsonl(subagents_dir / "agent-arch.jsonl", [
        row("a1", "claude-haiku-4", usage(input_tokens=50, output_tokens=50, cache_creation=500, cache_read=1000)),
    ])
    (subagents_dir / "agent-arch.meta.json").write_text(
        json.dumps({"agentType": "architect", "model": "haiku"}), encoding="utf-8")

    return projects_root


def test_model_overrides_render_section(capsys, override_session, price_file, agents_dir, monkeypatch):
    monkeypatch.setattr(token_usage, "DEFAULT_AGENTS_DIR", agents_dir)
    code = token_usage.main(["--session-id", SESSION_ID, "--projects-root", str(override_session),
                              "--price-file", str(price_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Модель против дефолта" in out
    assert "documentation: sonnet вместо haiku" in out
    assert "Апгрейд, нужна причина в decisions" in out
    assert "architect: haiku вместо opus" in out
    assert "Понижение против фронтматтера — по правилу запрещено" in out
    assert "исключение: architect на инкрементальной стадии" in out
    assert "qa: model=sonnet передан явно" in out
    section = out.split("Модель против дефолта:")[1]
    assert "developer" not in section   # no explicit model= -> no line at all
    # sorted by |cost delta| descending: architect ($17.80 swing) must come before documentation
    assert section.index("architect:") < section.index("documentation:")


def test_model_overrides_downgrade_sign_is_a_saving(capsys, override_session, price_file, agents_dir, monkeypatch):
    """A downgrade (cheaper override than default) must render as a saving, not `+$-N`."""
    monkeypatch.setattr(token_usage, "DEFAULT_AGENTS_DIR", agents_dir)
    code = token_usage.main(["--session-id", SESSION_ID, "--projects-root", str(override_session),
                              "--price-file", str(price_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "+$-" not in out
    assert "−$" in out


def test_model_overrides_json_fields(price_file, override_session, agents_dir, monkeypatch, capsys):
    monkeypatch.setattr(token_usage, "DEFAULT_AGENTS_DIR", agents_dir)
    code = token_usage.main(["--session-id", SESSION_ID, "--projects-root", str(override_session),
                              "--price-file", str(price_file), "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    overrides_by_name = {o["name"]: o for o in data["model_overrides"]}
    assert overrides_by_name["documentation"]["kind"] == "upgrade"
    assert overrides_by_name["documentation"]["model_default"] == "haiku"
    assert "counterfactual_cost_usd" in overrides_by_name["documentation"]
    assert overrides_by_name["qa"]["kind"] == "redundant"
    assert overrides_by_name["architect"]["kind"] == "downgrade"
    assert overrides_by_name["architect"]["model_default"] == "opus"
    assert "developer" not in overrides_by_name

    # sorted by |cost delta| descending across the whole list
    order = [o["name"] for o in data["model_overrides"]]
    assert order.index("architect") < order.index("documentation")

    agents_by_name = {a["name"]: a for a in data["agents"]}
    assert agents_by_name["documentation"]["model_override"] == "sonnet"
    assert agents_by_name["documentation"]["model_default"] == "haiku"


def test_no_model_key_produces_no_line(session, price_file, capsys):
    # the `session` fixture's dev1 agent DOES pass model=sonnet in meta; agent-nometa has none.
    # Neither has a resolvable frontmatter file under the real .claude/agents in this repo path
    # unless it happens to exist — use the JSON path instead, which is unambiguous either way.
    code = run_main(base_args(session, price_file, ["--json"]))
    data = json.loads(capsys.readouterr().out)
    names_with_override = {o["name"] for o in data["model_overrides"]}
    assert "agent-nometa" not in names_with_override


# ---------------------------------------------------------------------------
# --live mode
# ---------------------------------------------------------------------------

def test_live_mode_exits_0_and_lists_agents(session, price_file, capsys):
    code = run_main(base_args(session, price_file, ["--live"]))
    assert code == 0
    out = capsys.readouterr().out
    assert "MAIN" in out
    assert "developer" in out


def test_live_mode_omits_full_report_markers(session, price_file, capsys):
    code = run_main(base_args(session, price_file, ["--live"]))
    assert code == 0
    out = capsys.readouterr().out
    assert "Оценочная стоимость" not in out
    assert "non-cache-read итого" not in out


def test_live_mode_json_valid_with_new_fields(session, price_file, capsys):
    code = run_main(base_args(session, price_file, ["--live", "--json"]))
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert "agents" in data
    for a in data["agents"]:
        assert "peak_ctx" in a
        assert "median_ctx" in a
        assert "last_activity" in a
        assert "cost_usd" in a
