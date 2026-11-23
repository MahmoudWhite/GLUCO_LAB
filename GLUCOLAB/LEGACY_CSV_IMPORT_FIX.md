# GLUCOLAB — legacy LibreView and MiniMed CSV compatibility fix

This edition retains the latest device selector, logos, device-specific download guides,
and pastel YpsoPump theme. Only the structured data importer and regression tests
were updated.

## Fixed

- Metadata preambles that include Start Date / End Date no longer masquerade as the
  measurements table header. The reader selects a header with both a real timestamp
  and a glucose-value or basal-rate column.
- MiniMed CareLink CSV logs can contain many pump-event rows with blank basal-rate
  fields. Basal entries are validated from explicitly labelled U/h measurements;
  sparse rate-bearing rows are not rejected due to the ratio of other event rows.
- Data conversion does not invent glucose readings, basal readings, or medical
  pump settings. The existing medical warnings remain in place.

## Installation

1. Stop the old Python server (Ctrl+C in Anaconda Prompt).
2. Replace the old GLUCOLAB folder with this folder.
3. From the folder run: python -m pip install -r requirements.txt
4. Run: python app.py
5. Open http://127.0.0.1:8000 and press Ctrl+F5.

Validated with the existing test suite and anonymized/synthetic regression fixtures.
