"""Local tests of the label reader: no PATSTAT access needed.

Run from the project folder:  python -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.labels import block_precision, listed_family_ids, load_labels  # noqa: E402

OLD_FORMAT = """label_id,docdb_family_id,appln_title,label,labeler,note
1,100,Car HUD,0,CL,
2,101,VR helmet,0,CL,v2: kapalı VR başlığı -> kapsam dışı
3,102,Smart glasses,1,CL,
4,103,HMD,,CL,"HMD tipi belirtilmemiş (AR/şeffaf mı, kapalı VR mi anlaşılmıyor)"
5,104,Old adjacent,2,GG,
6,105,Disputed,1,CL,
7,106,Default,1,CL,"HMD tipi belirtilmemiş, VR ipucu yok -> varsayılan 1"
"""
TEAM_FORMAT = """sample_id,sample_stratum,docdb_family_id,relevance_label,technology_segment,exclusion_reason,reviewer,review_notes
1,core_cpc,200,1,display_AR_optics,,AI,
2,random_union,201,0,out_of_scope,adjacent_hmd_vr,AI,
3,random_union,202,0,out_of_scope,vehicle_hud,AI,HUD not HMD
4,random_union,203,?,uncertain,,AI,Insufficient abstract evidence
5,random_union,105,0,out_of_scope,unrelated,AI,
6,random_union,204,0,out_of_scope,"Phone-based virtual-reality headset, outside the perimeter.",AI,
"""


class LabelReaderTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        Path(self.folder.name, "labels_round1.csv").write_text(OLD_FORMAT, encoding="utf-8")
        Path(self.folder.name, "validation_sample.csv").write_text(TEAM_FORMAT, encoding="utf-8")
        self.labels = load_labels(self.folder.name).set_index("docdb_family_id")

    def tearDown(self):
        self.folder.cleanup()

    def test_both_formats_give_the_same_categories(self):
        expected = {100: "0", 101: "2", 102: "1", 104: "2", 200: "1", 201: "2", 202: "0", 204: "2"}
        for family, category in expected.items():
            self.assertEqual(self.labels.loc[family, "category"], category, family)

    def test_unsure_and_conflict_have_no_label(self):
        self.assertTrue(pd.isna(self.labels.loc[203, "relevance"]))
        self.assertTrue(self.labels.loc[105, "conflict"])
        self.assertTrue(pd.isna(self.labels.loc[105, "relevance"]))

    def test_hmd_of_unstated_type_is_adjacent(self):
        for family in (103, 106):
            self.assertEqual(self.labels.loc[family, "category"], "2", family)

    def test_every_listed_family_is_skipped_by_the_sampler(self):
        self.assertEqual(len(listed_family_ids(self.folder.name)), 12)

    def test_block_precision(self):
        frame = pd.DataFrame({"relevance": [1, 1, 0, 0, None], "a": [1, 1, 1, 0, 1], "b": [0, 1, 0, 1, 1]})
        table = block_precision(frame, ["a", "b"]).set_index("scope")
        self.assertEqual(table.loc["all blocks", "labelled"], 4)
        self.assertEqual(table.loc["a", "precision_percent"], 66.7)
        self.assertEqual(table.loc["a", "exclusive_precision_percent"], 50.0)
        self.assertEqual(table.loc["b", "exclusive_precision_percent"], 0.0)


if __name__ == "__main__":
    unittest.main()
