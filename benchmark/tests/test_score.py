from rasta_bench.score import cer, wer


def test_perfect_match():
    line = "bhaiya gate band hai order 18"
    assert wer(line, line) == 0.0
    assert cer(line, line) == 0.0


def test_one_word_wrong():
    assert wer("order 4 missing", "order 4 delay") == 1 / 3


def test_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "hello") == 1.0
    assert cer("", "") == 0.0


def test_cer_ignores_spaces():
    assert cer("ab cd", "abcd") == 0.0
