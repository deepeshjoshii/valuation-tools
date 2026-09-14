# Equity Analysis Tools

Live: **https://valuation-tools.streamlit.app**

A small, growing set of equity-research tools built for my own workflow — shared here in case they're useful to anyone else doing similar work.

## What's here

### 📊 Beta Calculator
Calculates a stock's beta against a benchmark via regression (with a covariance cross-check), checks how stable that beta has been over time (rolling beta), and builds a bottom-up beta from a peer set when the stock's own trading history is too short or noisy to trust directly. Feeds straight into a CAPM cost of equity.

**Answers:** how sensitive is this stock to the market, and what discount rate does that imply?

### 📉 Reverse DCF
Runs a DCF backwards across three methodologies — Net Income, FCFF, or FCFE — solving for the free-cash-flow (or earnings) growth rate that today's market price already implies, then compares that to the company's own historical growth.

**Answers:** what growth is the market already pricing in, and how does that compare with the company's track record?

## Tech stack

- **[Streamlit](https://streamlit.io)** — UI framework and hosting (Streamlit Community Cloud)
- **[yfinance](https://github.com/ranaroussi/yfinance)** — market data and financial statements
- **pandas / numpy / scipy** — data handling and regression
- **Plotly** — interactive charts

## Running it locally

```bash
git clone https://github.com/deepeshjoshii/valuation-tools.git
cd valuation-tools
pip install -r requirements.txt
streamlit run main.py
```

## Running the tests

```bash
pytest
```

Covers the core calculation engines (regression, CAGR-solving, WACC, sensitivity grids) in `beta_calculator.py` and `reverse_dcf.py`.

## Disclaimer

These tools are personal, educational projects built to support my own equity analysis workflow. They are **not investment advice or a recommendation to buy or sell securities** and should not be relied on as the sole basis for any investment decision.

Calculations depend on third-party data (Yahoo Finance via `yfinance`) that can be incomplete, delayed, mislabeled, or wrong for a given company or period — always cross-check key figures against a primary source before relying on them. All models involve simplifying assumptions; a different, reasonable set of assumptions can produce a materially different result.

## About

Built by **Deepesh Joshi** — a finance professional working in equity analysis, based in Indore, pursuing an MA in Economics alongside the CFA Program.

- 🔗 [GitHub](https://github.com/deepeshjoshii)
- 💼 [LinkedIn](https://linkedin.com/in/deepeshjoshii)
- ✉️ [Email](mailto:deepeshjosh2003@gmail.com)

## License

MIT — see [LICENSE](LICENSE).
