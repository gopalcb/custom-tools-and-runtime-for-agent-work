# Playwright UI Testing

Small browser inspection tool built around a persistent Chromium context.

## Commands

```bash
python main.py open --url http://localhost:3000 --headless
python main.py check --url http://localhost:3000
python main.py screenshot --url http://localhost:3000 --output /tmp/page.png
python main.py network --url http://localhost:3000 --reload
python main.py console-errors --url http://localhost:3000 --reload
python main.py hydration --url http://localhost:3000
python test.py
```

Playwright is imported lazily. Install browser dependencies with
`pip install playwright` and `playwright install chromium` before live browser
checks.
