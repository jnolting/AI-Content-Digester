from .fetchers import fetch_items
from .summarize import summarize_items
from .scoring import score_items
from .utils import write_report

def main():
    items = fetch_items()
    summaries = summarize_items(items)
    scored = score_items(summaries)
    write_report(scored, output_dir="reports")

if __name__ == "__main__":
    main()