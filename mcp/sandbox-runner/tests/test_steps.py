from conftest import JOB_ID, TMP_ROOT
from sandbox_runner.steps import find_block, parse


def test_parse_sample_readme():
    steps = parse((TMP_ROOT / "handsons" / JOB_ID / "README.md").read_text())
    ids = [s.id for s in steps]
    assert ids[:5] == ["prep-1", "prep-2", "prep-3", "prep-4", "prep-5"]
    assert "step-31" in ids and ids[-1].startswith("cleanup-")
    step, block = find_block(steps, "step-2#2")
    assert block.role == "check" and block.code == "echo ${QUEUE_URL}"
    assert step.checks and step.expected
    assert next(s for s in steps if s.id == "step-26").optional


def test_chapter_headings_are_not_steps():
    md = "## 手順\n\n### 1. 章\n\n#### 手順1: やる\n\n```bash\necho a\n```\n\n**確認ポイント**: a\n\n```text\na\n```\n"
    steps = parse(md)
    assert [s.id for s in steps] == ["step-1"]
    assert steps[0].blocks[0].role == "action" and steps[0].expected == ["a"]
