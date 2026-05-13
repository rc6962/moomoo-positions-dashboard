# Moomoo Positions Dashboard

A public Streamlit app for reviewing Moomoo position exports.

## Features

- Upload a Moomoo positions CSV
- Auto-classify positions as:
  - SELL NOW
  - TAKE PROFIT
  - SALVAGE
  - HOLD
  - WATCH
  - CLEAN UP
- Filter by action
- Search by ticker or name
- Click a position row to inspect details
- Export an action-list CSV

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
