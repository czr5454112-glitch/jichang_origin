import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_json_stream import iter_json_array_gz


def write(path, text):
    with gzip.open(path, "wt", encoding="utf8") as stream:
        stream.write(text)


@pytest.mark.parametrize("chunk", [1, 2, 3, 11, 1024])
def test_chunk_boundaries_preserve_numbers_unicode_strings_and_nested_objects(tmp_path, chunk):
    path = tmp_path/"values.json.gz"
    values = [12345, -3.456e-8, True, False, None, "汉字\\quoted\"", [], {},
        {"nested": [1, 2, {"key": "value"}]}, 1.2345e50]
    write(path, " \n"+json.dumps(values, ensure_ascii=False)+" \t\n")
    assert list(iter_json_array_gz(path, chunk_chars=chunk)) == values


def test_empty_array_and_many_items_do_not_accumulate_into_item_limit(tmp_path):
    path = tmp_path/"empty.json.gz"
    write(path, "  []  ")
    assert list(iter_json_array_gz(path, chunk_chars=1, max_item_chars=2)) == []
    write(path, json.dumps(list(range(10000))))
    assert sum(iter_json_array_gz(path, chunk_chars=4096, max_item_chars=8)) == sum(range(10000))


@pytest.mark.parametrize("text", ['{}', '[', '[1,', '[1,]', '[{"a":', '[1]x',
    '[1][2]', '[1 2]', '[NaN]', '[Infinity]', '[1e9999]', '[tru]'])
def test_malformed_truncated_or_nonfinite_data_is_rejected(tmp_path, text):
    path = tmp_path/"bad.json.gz"
    write(path, text)
    with pytest.raises(ValueError, match="airport_json_stream"):
        list(iter_json_array_gz(path, chunk_chars=2, max_item_chars=100))


def test_oversized_single_item_fails_even_when_total_file_is_valid(tmp_path):
    path = tmp_path/"large.json.gz"
    write(path, json.dumps(["x"*1000]))
    with pytest.raises(ValueError, match="item_character_limit_exceeded"):
        list(iter_json_array_gz(path, chunk_chars=16, max_item_chars=32))


def test_truncated_gzip_tail_cannot_be_reported_as_complete(tmp_path):
    path = tmp_path/"truncated.json.gz"
    path.write_bytes(gzip.compress(b"[1,2,3]")[:-6])
    with pytest.raises(ValueError, match="invalid_gzip_or_utf8"):
        list(iter_json_array_gz(path, chunk_chars=1))


def test_first_item_can_be_consumed_without_loading_remaining_large_items(tmp_path):
    path = tmp_path/"lazy.json.gz"
    write(path, json.dumps([{"first": True}, "x"*10000]))
    iterator = iter_json_array_gz(path, chunk_chars=16, max_item_chars=32)
    assert next(iterator) == {"first": True}
    with pytest.raises(ValueError, match="item_character_limit_exceeded"):
        next(iterator)
