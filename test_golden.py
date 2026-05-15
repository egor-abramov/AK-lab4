import contextlib
import io
import logging
import os
import tempfile
import pytest

import machine
import translator


@pytest.mark.golden_test("golden/*.yml")
def test_translator_and_machine(golden, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.handler.setFormatter(logging.Formatter("%(message)s"))

    with tempfile.TemporaryDirectory() as tmpdirname:
        source = os.path.join(tmpdirname, "source.fth")
        inp = os.path.join(tmpdirname, "input.txt")
        target = os.path.join(tmpdirname, "target.bin")

        with open(source, "w", encoding="utf-8") as file:
            file.write(golden["in_source"])

        with open(inp, "w", encoding="utf-8") as file:
            file.write(golden.get("input", ""))

        with contextlib.redirect_stdout(io.StringIO()):
            translator.main(source, target)
            print("============================================================")

            machine.main(target, inp)

        with open(target + ".hex", encoding="utf-8") as file:
            code_log = file.read()

        assert code_log == golden.out["out_code_log"]
        assert caplog.text.strip() == golden.out["out_log"]
