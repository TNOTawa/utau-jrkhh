"""项目 CRUD 与冻结语义单元测试。"""

from __future__ import annotations

import pytest

from jrh.core.errors import (
    DataError,
    FrozenError,
    InvalidInputError,
    NotFoundError,
)
from jrh.core.model import Timing
from jrh.core.project import JRHProject


def make_project(tmp_path, frozen=False):
    from fixtures.builder import build_demo_project

    return build_demo_project(tmp_path, with_audio=False, freeze=frozen)


class TestCreateOpen:
    def test_create_and_open(self, tmp_path):
        p = JRHProject.create(tmp_path / "x.jrh")
        assert p.manifest["format"] == "JRH"
        assert p.manifest["state"] == "draft"
        p2 = JRHProject.open(tmp_path / "x.jrh")
        assert p2.manifest["state"] == "draft"

    def test_open_missing(self, tmp_path):
        with pytest.raises(NotFoundError):
            JRHProject.open(tmp_path / "nope")

    def test_open_not_jrh(self, tmp_path):
        d = tmp_path / "x"
        d.mkdir()
        (d / "manifest.json").write_text('{"format": "OTHER"}', encoding="utf-8")
        with pytest.raises(DataError, match="format"):
            JRHProject.open(d)

    def test_open_bad_json(self, tmp_path):
        d = tmp_path / "x"
        d.mkdir()
        (d / "manifest.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(DataError, match="损坏"):
            JRHProject.open(d)

    def test_open_unsupported_schema(self, tmp_path):
        d = tmp_path / "x"
        d.mkdir()
        (d / "manifest.json").write_text(
            '{"format": "JRH", "schema_version": "9.9.9"}', encoding="utf-8"
        )
        with pytest.raises(DataError, match="schema"):
            JRHProject.open(d)


class TestSentenceOps:
    def test_create_requires_asset(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(NotFoundError):
            proj.create_sentence("asset-9", 0, 100)

    def test_bounds_checks(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        with pytest.raises(InvalidInputError, match="越界"):
            proj.create_sentence("a1", 0, 200000)
        with pytest.raises(InvalidInputError, match="start"):
            proj.create_sentence("a1", -1, 10)
        with pytest.raises(InvalidInputError, match="start"):
            proj.create_sentence("a1", 50, 50)
        with pytest.raises(InvalidInputError, match="采样率"):
            proj.create_sentence("a1", 0, 100, sample_rate=999)

    def test_delete_cascade_required(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 1000)
        proj.create_unit(1, "ni", _timing_ok())
        with pytest.raises(InvalidInputError, match="cascade"):
            proj.delete_sentence(1)
        proj.delete_sentence(1, cascade=True)
        assert 1 not in proj.sentences
        assert len(proj.units) == 0

    def test_split_draft(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "ni", Timing(0, 100, -3000, 0, 0))
        proj.create_unit(1, "hao", Timing(3000, 100, -3000, 0, 0))
        proj.create_unit(1, "a", Timing(7000, 0, -1000, 0, 0))
        new_sid, new_sent = proj.split_sentence(1, 6000)
        assert new_sent.start_sample == 6000 and new_sent.end_sample == 10000
        assert [u.label for u in proj.units_in_sentence(1)] == ["ni", "hao"]
        assert [u.label for u in proj.units_in_sentence(new_sid)] == ["a"]

    def test_split_straddling_unit_rejected(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "hao", Timing(0, 100, -7000, 0, 0))  # 跨 6000
        with pytest.raises(InvalidInputError, match="分割点"):
            proj.split_sentence(1, 6000)

    def test_split_point_outside(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        with pytest.raises(InvalidInputError):
            proj.split_sentence(1, 0)
        with pytest.raises(InvalidInputError):
            proj.split_sentence(1, 10000)

    def test_merge_basic(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 4000)
        proj.create_unit(1, "ni", Timing(0, 100, -2000, 0, 0))
        proj.create_sentence("a1", 4000, 10000)
        proj.create_unit(2, "hao", Timing(0, 100, -3000, 0, 0))
        keep = proj.merge_sentences(1, 2)
        assert keep == 1
        assert proj.sentences[1].end_sample == 10000
        # 第二句单元 offset 应减去两句起点差（4000）
        merged = proj.units_in_sentence(1)
        assert [u.label for u in merged] == ["ni", "hao"]
        assert merged[1].timing.offset == 0 - 4000

    def test_merge_different_asset_rejected(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.add_asset(_fake_asset("a2", 48000, 10000))
        proj.create_sentence("a1", 0, 1000)
        proj.create_sentence("a2", 0, 1000)
        with pytest.raises(InvalidInputError, match="同一 asset"):
            proj.merge_sentences(1, 2)

    def test_renumber_draft(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 1000)
        proj.create_sentence("a1", 2000, 3000)
        # 删除 1 号句后重排
        proj.delete_sentence(1, cascade=True)
        proj.renumber_sentences()
        assert list(proj.sentences.keys()) == [1]

    def test_renumber_unit_ids(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "ni", _timing_ok())
        proj.create_unit(1, "hao", _timing_ok())
        proj.create_unit(1, "a", _timing_ok())
        proj.delete_unit(1, 2)
        assert [u.unit_id for u in proj.units_in_sentence(1)] == [1, 3]
        proj.renumber_unit_ids(1)
        assert [u.unit_id for u in proj.units_in_sentence(1)] == [1, 2]


class TestUnitOps:
    def test_create_unit_ids_never_reuse(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "ni", _timing_ok())
        proj.create_unit(1, "hao", _timing_ok())
        proj.delete_unit(1, 2)
        u3 = proj.create_unit(1, "a", _timing_ok())
        assert u3.unit_id == 3  # 不复用 2

    def test_create_window_out_of_sentence(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 1000)
        with pytest.raises(InvalidInputError, match="超出句子范围"):
            proj.create_unit(1, "hao", Timing(0, 0, -2000, 0, 0))

    def test_update_timing_constraints(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "hao", _timing_ok())
        with pytest.raises(InvalidInputError, match="cutoff"):
            proj.update_unit(1, 1, timing=Timing(0, 0, 100, 0, 0))

    def test_update_label_enabled(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        u = proj.create_unit(1, "hao", _timing_ok())
        u = proj.update_unit(1, 1, label="gao", enabled=False)
        assert u.label == "gao" and not u.enabled

    def test_delete_unit_keeps_counter(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "hao", _timing_ok())
        proj.delete_unit(1, 1)
        assert proj.get_sentence(1).max_unit_id_ever == 1


class TestFrozen:
    def test_freeze_is_one_way(self, demo_project_frozen):
        with pytest.raises(FrozenError, match="已处于冻结状态"):
            JRHProject.open(demo_project_frozen).freeze()

    def test_freeze_then_new_ids_keep_growing(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        proj.delete_sentence(3, cascade=True)
        s = proj.create_sentence("asset-001", 0, 10000)
        assert s.sentence_id == 4  # 不复用 3
        u = proj.create_unit(s.sentence_id, "ni", _timing_ok())
        assert u.unit_id == 1  # 新句子从 1 开始
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        assert proj2.get_sentence(4).sentence_id == 4

    def test_frozen_renumber_forbidden(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        with pytest.raises(FrozenError):
            proj.renumber_sentences()
        with pytest.raises(FrozenError):
            proj.renumber_unit_ids(1)

    def test_frozen_edit_label_timing_allowed(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        u = proj.update_unit(1, 1, label="la")
        assert u.label == "la"
        u2 = proj.update_unit(1, 2, enabled=False)
        assert not u2.enabled

    def test_frozen_split(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        # 先调整单元边界，使分割点两侧无跨窗单元
        proj.update_unit(1, 2, timing=Timing(38000, 100, -30000, 0, 0))
        proj.update_unit(1, 3, timing=Timing(69000, 0, -10000, 0, 0))
        new_sid, new_sent = proj.split_sentence(1, 68500)
        assert new_sid == 4
        # 原句保留原编号；新句单元取句内新编号
        assert [u.coordinate() for u in proj.units_in_sentence(1)] == ["1:1", "1:2"]
        assert [u.coordinate() for u in proj.units_in_sentence(4)] == ["4:1"]

    def test_frozen_merge_keeps_min_id(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        keep = proj.merge_sentences(1, 2)
        assert keep == 1


class TestSaveLoad:
    def test_save_load_roundtrip(self, demo_project):
        proj = JRHProject.open(demo_project)
        before = {
            "sentences": [s.to_dict() for s in proj.sentences_sorted()],
            "units": [u.to_dict() for u in proj.units_sorted()],
            "groups": proj.candidate_groups.to_dict(),
        }
        proj.save()
        proj2 = JRHProject.open(demo_project)
        after = {
            "sentences": [s.to_dict() for s in proj2.sentences_sorted()],
            "units": [u.to_dict() for u in proj2.units_sorted()],
            "groups": proj2.candidate_groups.to_dict(),
        }
        assert before == after

    def test_duplicate_coordinate_rejected_on_open(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_fake_asset())
        proj.create_sentence("a1", 0, 10000)
        proj.create_unit(1, "hao", _timing_ok())
        # 手工写坏 units.json：同一坐标出现两次
        from jrh.core.util import write_json

        u = proj.units[(1, 1)].to_dict()
        units = [dict(u), dict(u)]
        write_json(tmp_path / "p" / "data" / "units.json", {"units": units})
        with pytest.raises(DataError, match="重复的单元坐标"):
            JRHProject.open(tmp_path / "p")


def _fake_asset(asset_id="a1", sample_rate=44100, num_samples=100000):
    from jrh.core.model import Asset

    return Asset(
        id=asset_id,
        file="assets/x.wav",
        kind="audio",
        sha256="0" * 64,
        sample_rate=sample_rate,
        num_samples=num_samples,
        duration_seconds=num_samples / sample_rate,
    )


def _timing_ok():
    return Timing(0, 100, -500, 0, 0)
