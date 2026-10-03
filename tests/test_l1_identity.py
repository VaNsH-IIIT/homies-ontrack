"""Layer 1 identity resolution: clustering and the date-of-birth conflict guard (owner: P1)."""
from datetime import date

from ontrack.l1_factory.identity import UnionFind, resolve

D1, D2 = date(1980, 5, 1), date(1991, 2, 3)


def test_union_find_is_transitive_and_uses_smallest_key_as_root():
    uf = UnionFind()
    uf.union("loan:B2", "crm:A")
    uf.union("card:C3", "loan:B2")
    assert uf.find("card:C3") == uf.find("crm:A") == "card:C3"  # smallest key of the cluster
    assert uf.find("cif:9") == "cif:9"


def test_links_from_three_systems_form_one_person():
    edges = [("crm:A", "card:X", 0.98, "case_account"), ("crm:A", "loan:Y", 0.97, "name_dob_postal"),
             ("card:X", "cif:Z", 0.95, "pad_link")]
    uf, best, refused = resolve(["crm:A", "card:X", "loan:Y", "cif:Z"], edges, {"crm:A": D1})
    assert len({uf.find(n) for n in ("crm:A", "card:X", "loan:Y", "cif:Z")}) == 1
    assert refused == []


def test_conflict_guard_refuses_merging_two_people_with_different_dobs():
    # A card key wrongly matches two different CRM people: the second link must be refused.
    edges = [("crm:A", "card:X", 0.98, "case_account"), ("crm:B", "card:X", 0.97, "name_dob_phone")]
    uf, _, refused = resolve(["crm:A", "crm:B", "card:X"], edges, {"crm:A": D1, "crm:B": D2})
    assert uf.find("crm:A") != uf.find("crm:B")
    assert uf.find("card:X") == uf.find("crm:A")  # the stronger link wins
    assert refused == [("crm:B", "card:X", 0.97, "name_dob_phone")]


def test_conflict_guard_sees_the_whole_cluster_not_just_the_edge():
    # loan:Y joins A's cluster through card:X; a later link from B (other DOB) to loan:Y is refused.
    edges = [("crm:A", "card:X", 0.99, "national_id"), ("card:X", "loan:Y", 0.98, "case_account"),
             ("crm:B", "loan:Y", 0.95, "splink")]
    uf, _, refused = resolve(["crm:A", "crm:B", "card:X", "loan:Y"], edges, {"crm:A": D1, "crm:B": D2})
    assert uf.find("crm:B") != uf.find("loan:Y")
    assert len(refused) == 1


def test_crm_duplicate_flag_is_exempt_from_the_guard():
    # The bank's own duplicate flag says these two CRM records are one person, even with a DOB typo.
    uf, _, refused = resolve(["crm:A", "crm:B"], [("crm:A", "crm:B", 0.99, "crm_duplicate")],
                             {"crm:A": D1, "crm:B": D2})
    assert uf.find("crm:A") == uf.find("crm:B")
    assert refused == []


def test_same_dob_or_unknown_dob_links_are_allowed():
    edges = [("crm:A", "crm:B", 0.97, "name_dob_postal"), ("crm:A", "card:X", 0.96, "splink")]
    uf, _, refused = resolve(["crm:A", "crm:B", "card:X"], edges, {"crm:A": D1, "crm:B": D1})
    assert uf.find("crm:B") == uf.find("card:X")
    assert refused == []


def test_each_key_records_its_strongest_evidence():
    edges = [("crm:A", "card:X", 0.96, "splink"), ("crm:A", "card:X", 0.98, "case_account")]
    _, best, _ = resolve(["crm:A", "card:X"], edges, {})
    assert best["card:X"] == (0.98, "case_account")
