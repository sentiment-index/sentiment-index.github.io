import time

from setup_pages import generate_index, generate_term_page, generate_about, generate_term_list
from tracker import add_term, get_term_list, RawData


if __name__ == "__main__":
    start = time.time()
    with open("terms.txt", "r") as file:
        for line in file:
            term = line.split("\n")[0]
            print(term, time.time()-start)
            add_term(term)
    term_list = get_term_list()
    term_scores = generate_index()
    generate_about()
    generate_term_list(term_list, term_scores)
    for term in term_list:
        generate_term_page(term)
