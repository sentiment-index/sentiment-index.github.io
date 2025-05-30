import os
from datetime import datetime, timedelta
from typing import List, Dict, Union
from zoneinfo import ZoneInfo

from tracker import get_term_list, load_avg_sentiment_scores, get_newsworthy_terms

HTML_BASE_DIR = "docs"

def term_to_url(term: str) -> str:
    return  term.replace(" ", "-").lower()+".html"

def generate_about():

    terms_list = get_term_list()
    terms_json = str(terms_list).replace("'", '"')

    html = f"""<link rel="stylesheet" href="style.css">
<html>
<head>
    <script>const TERMS = {terms_json};</script>
    <link rel="icon" type="image/x-icon" href="site-assets/favicon.svg">
</head>

<header class="site-header">
  <div class="header-content">
    <div class="logo">
      <img src="site-assets/logo.svg" alt="Logo">
    </div>
    <nav class="nav-links">
      <a href="index.html">Home</a>
      <a href="term-list.html">List</a>
      <a href="about.html">About</a>
      <button class="search-button"><img src="site-assets/search.svg" alt="Search" class="search-icon"></button>
    </nav>
  </div>
</header>

<body>
<div id="search-overlay" class="search-overlay" style="display: none;">
    <div class="search-box">
        <span><button class="close-search">X</button><input type="text" id="search-input" placeholder="Search for a term..." /></span>
        <div id="search-results"></div>
    </div>
</div>

<div class="topbox">
  <h1>How it works</h1>
</div>

<div class="wrapper">

<section class="about-section">
  <h2>The Idea</h2>
  <p>Every day, millions of conversations happen on the internet. We built this site to track how people feel about key topics over time. Why do we only search Reddit? Its API is the cheapest.</p>
</section>

<section class="about-section">
  <h2>The Methodology</h2>
  <p>We start with a curated list of 100 terms that we want to track. Every day at midnight MST, we search Reddit for new posts mentioning these terms. Each post is semantically analyzed and assigned a sentiment score from <strong>1 (very negative)</strong> to <strong>5 (very positive)</strong> based on how people are talking about it.</p>
  <p>For each term, we average the scores across all the posts from that day. We scale that to create our scores, which go from -1 for highly negative sentiment to 1 for positive sentiment.</p>
</section>

<section class="about-section">
  <h2>Notes</h2>
  <ul>
    <li>Sentiment scores are averaged across posts mentioning a term, not weighted by upvotes or engagement.</li>
    <li>We use a plaintext search, so we don't look at related terms, only the term itself.</li>
    <li>Posts are analyzed using semantic language models, but sentiment analysis is inherently subjective and imperfect.</li>
  </ul>
</section>

</div>

<div class="timenote">Last updated {datetime.now().strftime("%I:%M%p on %B %d, %Y")}</div>

<script src="site-assets/search.js"></script>
</body>
</html>
"""

    with open(os.path.join(HTML_BASE_DIR, "about.html"), "w", encoding="utf-8") as f:
        f.write(html)


def generate_index():
    term_scores = []

    term_list = get_term_list()

    for term in term_list:
        avg_data = load_avg_sentiment_scores(term)
        today = datetime.now(ZoneInfo("UTC")).date()
        yesterday = today - timedelta(days=1)
        n = 0

        while (str(today) not in avg_data or str(yesterday) not in avg_data) and n < 5:
            today = yesterday
            yesterday = today - timedelta(days=1)
            n += 1
        today_score = avg_data.get(str(today), 0.0)
        yesterday_score = avg_data.get(str(yesterday), 0.0)

        change = today_score - yesterday_score

        term_scores.append({
            "term": term,
            "today_score": today_score,
            "change": change,
        })

    newsworthy_terms = get_newsworthy_terms(term_list)

    top_movers = sorted([term_score for term_score in term_scores if term_score["today_score"]>-0.15], key=lambda x: -x["change"])[:3]
    bottom_movers = sorted([term_score for term_score in term_scores if term_score["today_score"]<0.15], key=lambda x: x["change"])[:3]
    top_terms = sorted(term_scores, key=lambda x: -x["today_score"])[:3]
    bottom_terms = sorted(term_scores, key=lambda x: x["today_score"])[:3]
    in_the_news = [term_score for term_score in term_scores if term_score["term"] in newsworthy_terms]

    html = """
<link rel="stylesheet" href="style.css">
<html>
<head>
    <link rel="icon" type="image/x-icon" href="site-assets/favicon.svg">
</head>

<header class="site-header">
  <div class="header-content">
    <div class="logo">
      <img src="site-assets/logo.svg" alt="Logo">
    </div>
    <nav class="nav-links">
      <a href="index.html">Home</a>
      <a href="term-list.html">List</a>
      <a href="about.html">About</a>
      <button class="search-button"><img src="site-assets/search.svg" alt="Search" class="search-icon"></button>
    </nav>
  </div>
</header>

<body>
<div id="search-overlay" class="search-overlay" style="display: none;">
      <div class="search-box">
          <span><button class="close-search">X</button><input type="text" id="search-input" placeholder="Search for a term..." /></span>
          <div id="search-results"></div>
      </div>
</div>
<div class="topbox">
<h1>But how does Reddit feel about it?</h1>
  <h2>We track sentiment across thousands of Reddit posts to show you how opinions change over time.</h2>
</div>
<div class="wrapper">

"""

    terms_list = get_term_list()
    terms_json = str(terms_list).replace("'", '"')

    html += f"""
    <script>
    const TERMS = {terms_json};
    </script>
    <script src="site-assets/search.js"></script>
    """

    def build_row(title, entries, key, icon_name, is_change=False):
        nonlocal html
        html += f"<div class='section'><div class='row-header'><img src='{icon_name}' class='row-icon'><h2>{title}</h2></div><div class='row'>"
        for entry in entries:
            score = entry[key]
            color_class = "positive" if score >= 0 else "negative"
            display_score = f"{score:+.2f}"

            arrow = ""
            if is_change:
                arrow = "↑" if score > 0 else "↓"

            label = "Change" if is_change else "Score"

            html += f"""
            <div class="card {color_class}">
                <a href="{term_to_url(entry['term'])}">
                    <div class="term-name">{entry['term']}</div>
                    <div class="score-section">
                        <div class="score-value">{display_score} {arrow}</div>
                        <div class="score-label">{label}</div>
                    </div>
                </a>
            </div>
            """
        html += "</div></div>"

    build_row("Popular Today", in_the_news, "change", "site-assets/rsi-hot.svg", is_change=True)
    build_row("Top Movers Today", top_movers, "change", "site-assets/rsi-moving-up.svg", is_change=True)
    build_row("Bottom Movers Today", bottom_movers, "change", "site-assets/rsi-moving-down.svg", is_change=True)
    build_row("Top Terms", top_terms, "today_score", "site-assets/rsi-top.svg", is_change=False)
    build_row("Bottom Terms", bottom_terms, "today_score", "site-assets/rsi-bottom.svg", is_change=False)

    html += f"""
</div>

<div class="timenote">Last updated {datetime.now().strftime("%I:%M%p on %B %d, %Y")}</div>
</body>
</html>
"""

    with open(os.path.join(HTML_BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return term_scores


def generate_term_page(term: str):
    avg_data = load_avg_sentiment_scores(term)

    sorted_dates = sorted(avg_data.keys())
    scores = [max(-1, min(1, avg_data[date])) for date in sorted_dates]

    today = datetime.now(ZoneInfo("UTC")).date()
    yesterday = today - timedelta(days=1)
    n = 0

    while (str(today) not in avg_data or str(yesterday) not in avg_data) and n < 5:
        today = yesterday
        yesterday = today - timedelta(days=1)
        n += 1
    today_score = avg_data.get(str(today), 0.0)
    yesterday_score = avg_data.get(str(yesterday), 0.0)

    terms_list = get_term_list()
    terms_json = str(terms_list).replace("'", '"')

    change = today_score - yesterday_score

    descriptor = ""
    descriptor_class = ""

    if today_score >= 0.3:
        descriptor = "strongly positive"
        descriptor_class = "positive"
    elif today_score >= 0.15:
        descriptor = "positive"
        descriptor_class = "positive"
    elif today_score >= -0.15:
        descriptor = "neutral"
        descriptor_class = "neutral"
    elif today_score >= -0.3:
        descriptor = "negative"
        descriptor_class = "negative"
    else:
        descriptor = "strongly negative"
        descriptor_class = "negative"

    # Formatting change arrow
    if change >= 0:
        change_arrow = "↑"
        change_class = "positive"
    else:
        change_arrow = "↓"
        change_class = "negative"

    # Make scores show nicely rounded
    score_display = f"{today_score:.3f}"
    change_display = f"{change_arrow} {abs(change):.3f}"

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sentiment for {term}</title>
    <link rel="stylesheet" href="style.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="icon" type="image/x-icon" href="site-assets/favicon.svg">
</head>
<body>

<div id="search-overlay" class="search-overlay" style="display: none;">
      <div class="search-box">
          <span><button class="close-search">X</button><input type="text" id="search-input" placeholder="Search for a term..." /></span>
          <div id="search-results"></div>
      </div>
</div>

<header class="site-header">
  <div class="header-content">
    <div class="logo">
      <img src="site-assets/logo.svg" alt="Logo">
    </div>
    <nav class="nav-links">
      <a href="index.html">Home</a>
      <a href="term-list.html">List</a>
      <a href="about.html">About</a>

      <button class="search-button"><img src="site-assets/search.svg" alt="Search" class="search-icon"></button>
    </nav>
  </div>
</header>


<div class="wrapper">
    <script>
    const TERMS = {terms_json};
    </script>
    <script src="site-assets/search.js"></script>

    <h1>Sentiment for “{term}” is <span class="{descriptor_class}">{descriptor}</span></h1>

    <div class="score-change">
        <div class="score-block">
            <div class="label">Score</div>
            <div class="score {descriptor_class}">{score_display}</div>
        </div>
        <div class="change-block">
            <div class="label">Change</div>
            <div class="change {change_class}">{change_display}</div>
        </div>
    </div>

    <canvas id="sentimentChart" width="800" height="400"></canvas>
</div>

<script>
    const ctx = document.getElementById('sentimentChart').getContext('2d');

    const allLabels = {sorted_dates};
    const allScores = {scores};

    const recentLabels = allLabels.slice(-30);
    const recentScores = allScores.slice(-30);

    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(144, 238, 144, 0.3)');
    gradient.addColorStop(0.5, 'rgba(255, 255, 255, 0)');
    gradient.addColorStop(1, 'rgba(255, 182, 193, 0.2)');

    const sentimentChart = new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: recentLabels,
            datasets: [{{
                label: 'Sentiment Score',
                data: recentScores,
                fill: true,
                borderColor: '#183660',
                backgroundColor: gradient,
                tension: 0.3,
                pointRadius: 2,
            }}]
        }},
        options: {{
            scales: {{
                y: {{
                    min: -1,
                    max: 1,
                    grid: {{
                        drawBorder: true,
                        color: function(context) {{
                            if (context.tick.value === 0) {{
                                return '#000';
                            }}
                            return '#e0e0e0';
                        }},
                        lineWidth: function(context) {{
                            return context.tick.value === 0 ? 2 : 1;
                        }}
                    }}
                }},
                x: {{
                    ticks: {{
                        autoSkip: true,
                        maxTicksLimit: 10
                    }}
                }}
            }},
            plugins: {{
                legend: {{
                    display: false
                }}
            }}
        }}
    }});
</script>

<div class="timenote">Last updated {datetime.now().strftime("%I:%M%p on %B %d, %Y")}</div>

</body>
</html>
"""

    output_path = os.path.join(HTML_BASE_DIR, term_to_url(term))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)



def generate_term_list(term_list: List[str], term_scores: List[Dict[str, Union[str, float]]]):
    terms_json = str(term_list).replace("'", '"')

    html = f"""
<link rel="stylesheet" href="style.css">
<html>
<head>
    <link rel="icon" type="image/x-icon" href="site-assets/favicon.svg">
    <script>const TERMS = {terms_json};</script>
    <script>
function sortTable(columnIndex, isNumeric = false) {{
  const table = document.getElementById("termsTable");
  const tbody = table.tBodies[0];
  const rowsArray = Array.from(tbody.rows);
  const header = table.rows[0].cells[columnIndex];
  const currentDir = header.getAttribute("data-dir") || "asc";
  const newDir = currentDir === "asc" ? "desc" : "asc";
  header.setAttribute("data-dir", newDir);

  const comparator = (rowA, rowB) => {{
    const cellA = rowA.cells[columnIndex].innerText.trim();
    const cellB = rowB.cells[columnIndex].innerText.trim();

    const aIsNegative = cellA.startsWith("-");
    const bIsNegative = cellB.startsWith("-");

    if (!aIsNegative && bIsNegative) return newDir === "asc" ? 1 : -1;
    if (aIsNegative && !bIsNegative) return newDir === "asc" ? -1 : 1;

    if (isNumeric) {{
      const aVal = parseFloat(cellA);
      const bVal = parseFloat(cellB);
      return newDir === "asc" ? aVal - bVal : bVal - aVal;
    }} else {{
      return newDir === "asc"
        ? cellA.localeCompare(cellB)
        : cellB.localeCompare(cellA);
    }}
  }};

  rowsArray.sort(comparator);

  rowsArray.forEach(row => tbody.appendChild(row));
}}
    </script>
</head>

<header class="site-header">
  <div class="header-content">
    <div class="logo">
      <img src="site-assets/logo.svg" alt="Logo">
    </div>
    <nav class="nav-links">
      <a href="index.html">Home</a>
      <a href="term-list.html">List</a>
      <a href="about.html">About</a>
      <button class="search-button"><img src="site-assets/search.svg" alt="Search" class="search-icon"></button>
    </nav>
  </div>
</header>

<body>
<div id="search-overlay" class="search-overlay" style="display: none;">
      <div class="search-box">
          <span><button class="close-search">X</button><input type="text" id="search-input" placeholder="Search for a term..." /></span>
          <div id="search-results"></div>
      </div>
</div>

<div class="topbox">
<h1>All Tracked Terms</h1>
<h2>Click a header to sort alphabetically, by score, or by daily change.</h2>
</div>

<div class="table-wrapper">
<table id="termsTable">
<thead>
<tr>
    <th onclick="sortTable(0, false)"><span>Term</span><span><img src="site-assets/tablearrows.svg" alt="table arrows"></span></th>
    <th onclick="sortTable(1, true)"><span>Today's Score</span><span><img src="site-assets/tablearrows.svg" alt="table arrows"></span></th>
    <th onclick="sortTable(2, true)"><span>Change From Yesterday</span><span><img src="site-assets/tablearrows.svg" alt="table arrows"></span></th>
</tr>
</thead>
<tbody>
"""

    for entry in term_scores:
        term = entry['term']
        today_score_val = entry['today_score']
        change_val = entry['change']

        today_score = f"{today_score_val:.3f}"
        arrow = "↑" if change_val >= 0 else "↓"
        change = f"{change_val:+.3f}{arrow}"

        score_class = "positive" if today_score_val >= 0 else "negative"
        change_class = "positive" if change_val >= 0 else "negative"

        html += f"""
    <tr>
        <td><a href="{term_to_url(term)}">{term}</a></td>
        <td class="{score_class}">{today_score}</td>
        <td class="{change_class}">{change}</td>
    </tr>
    """

    html += f"""
</tbody>
</table>
</div>

<div class="timenote">Last updated {datetime.now().strftime("%I:%M%p on %B %d, %Y")}</div>

<script src="site-assets/search.js"></script>

</body>
</html>
"""

    output_path = os.path.join(HTML_BASE_DIR, term_to_url("term-list"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    term_list = get_term_list()
    term_scores = generate_index()
    generate_about()
    generate_term_list(term_list, term_scores)
    for term in term_list:
        generate_term_page(term)

