from bjorn.render import DONE_BOX, OPEN_BOX, head_of, is_tag_line, preprocess, snippet, strip_title_and_tags


def test_tasks_become_glyphs_outside_fences():
    src = "- [ ] open\n- [x] done\n  - [ ] nested\n```\n- [ ] in code\n```\n1. [ ] numbered\n"
    out = preprocess(src)
    assert f"- {OPEN_BOX} open" in out
    assert f"- {DONE_BOX} done" in out
    assert f"  - {OPEN_BOX} nested" in out
    assert "- [ ] in code" in out
    assert f"1. {OPEN_BOX} numbered" in out


def test_bear_only_marks_are_flattened():
    assert preprocess("a ==big== deal") == "a **big** deal"
    assert preprocess("an ~under~ line") == "an under line"
    assert preprocess("path ~/foo/bar") == "path ~/foo/bar"
    assert preprocess("~~strike~~ stays") == "~~strike~~ stays"


def test_tag_line_is_recognised_and_styled():
    assert is_tag_line("#kybernetes/Coding")
    assert is_tag_line("#a #b/c #multi word#")
    assert not is_tag_line("# Heading")
    assert not is_tag_line("text with #tag inside")
    assert preprocess("# T\n#kybernetes/Coding #techne\n\nbody") == "# T\n`#kybernetes/Coding` `#techne`\n\nbody"


def test_head_of_and_snippet():
    text = "\n".join(str(i) for i in range(100))
    head, cut = head_of(text, 10)
    assert cut and head.count("\n") == 9
    assert head_of("a\nb", 10) == ("a\nb", False)
    body = "# Title\n#tag\n\n## Section\nFirst real line\nmore"
    assert strip_title_and_tags(body).startswith("## Section")
    assert snippet(body) == "Section"
    assert snippet("# Only title\n#tag\n") == ""
