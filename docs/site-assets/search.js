document.querySelector(".search-icon").addEventListener("click", function (e) {
    e.preventDefault();
    const searchBox = document.getElementById("search-overlay");
    searchBox.style.display = (searchBox.style.display === "none") ? "block" : "none";
    document.getElementById("search-input").focus();
});

document.querySelector(".close-search").addEventListener("click", function (e) {
    e.preventDefault();
    const searchBox = document.getElementById("search-overlay");
    searchBox.style.display = (searchBox.style.display === "none") ? "block" : "none";
    document.getElementById("search-input").focus();
});

// handle typing into the search input
document.getElementById("search-input").addEventListener("input", function () {
    const query = this.value.toLowerCase();
    const resultsDiv = document.getElementById("search-results");
    resultsDiv.innerHTML = "";

    if (query.length === 0) {
        return;
    }

    const matchingTerms = TERMS.filter(term => term.toLowerCase().includes(query)).slice(0,10);

    matchingTerms.forEach(term => {
        const link = document.createElement("a");
        link.href = term.replace(/ /g, "-").toLowerCase() + ".html";
        link.textContent = term;
        link.classList.add("search-result-link");
        resultsDiv.appendChild(link);
    });

    if (matchingTerms.length === 0) {
        resultsDiv.innerHTML = "<p>No matches found.</p>";
    }
});
