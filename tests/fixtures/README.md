# Fixtures

Put real sample HAP PDFs and their hand-verified expected CSVs here
(e.g. `sample_report.pdf` + `hap_output_python.csv`), then extend
`tests/test_pipeline.py` to compare byte-exact against them.

The current test suite uses synthetic PDFs generated in `conftest.py`
because no real sample was available at kickoff.
