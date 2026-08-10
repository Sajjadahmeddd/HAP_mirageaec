from hap_converter.ui.recents import MAX_ENTRIES, RecentEntry, RecentStore


def test_round_trip(tmp_path):
    store_path = tmp_path / "recent.json"
    store = RecentStore(store_path)
    store.add(RecentEntry(pdf_path="C:/a.pdf", output_path="C:/a.csv", status="completed"))
    reloaded = RecentStore(store_path)
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].pdf_path == "C:/a.pdf"
    assert reloaded.entries[0].timestamp  # stamped on add


def test_same_pdf_dedupes_and_moves_to_top(tmp_path):
    store = RecentStore(tmp_path / "recent.json")
    store.add(RecentEntry(pdf_path="C:/a.pdf", status="failed"))
    store.add(RecentEntry(pdf_path="C:/b.pdf", status="completed"))
    store.add(RecentEntry(pdf_path="C:/a.pdf", status="completed"))
    assert [e.pdf_path for e in store.entries] == ["C:/a.pdf", "C:/b.pdf"]
    assert store.entries[0].status == "completed"


def test_cap(tmp_path):
    store = RecentStore(tmp_path / "recent.json")
    for i in range(MAX_ENTRIES + 10):
        store.add(RecentEntry(pdf_path=f"C:/{i}.pdf"))
    assert len(store.entries) == MAX_ENTRIES
    assert store.entries[0].pdf_path == f"C:/{MAX_ENTRIES + 9}.pdf"


def test_corrupt_store_starts_fresh(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text("{not json!", encoding="utf-8")
    store = RecentStore(path)
    assert store.entries == []
    store.add(RecentEntry(pdf_path="C:/ok.pdf"))
    assert RecentStore(path).entries[0].pdf_path == "C:/ok.pdf"


def test_remove(tmp_path):
    store = RecentStore(tmp_path / "recent.json")
    store.add(RecentEntry(pdf_path="C:/a.pdf"))
    store.add(RecentEntry(pdf_path="C:/b.pdf"))
    store.remove("C:/a.pdf")
    assert [e.pdf_path for e in store.entries] == ["C:/b.pdf"]
