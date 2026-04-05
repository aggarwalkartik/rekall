import re

STOPWORDS = {"a","an","the","is","are","was","were","what","how","why","when",
    "where","which","who","do","does","did","can","could","should","would",
    "about","for","with","from","into","on","at","to","in","of","and","or",
    "but","not","best","latest","recent","current","new","top","all","any",
    "be","been","being","have","has","had","it","its","this","that","these",
    "those","then","than","so","if","just","only","very","also","each","every"}

NEGATION = {"never","don't","dont","avoid","skip","without","stop","not",
    "no","disable","remove","exclude","ban"}
AFFIRMATION = {"always","use","prefer","ensure","must","require","enable",
    "include","force","mandate"}

def tokenize(text):
    return {w for w in re.findall(r'[a-z]+', text.lower()) if w not in STOPWORDS}

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def has_polarity_flip(text_a, text_b):
    norm_a = text_a.lower().replace("'", "")
    norm_b = text_b.lower().replace("'", "")
    words_a = set(re.findall(r'[a-z]+', norm_a))
    words_b = set(re.findall(r'[a-z]+', norm_b))
    a_neg = bool(words_a & NEGATION)
    b_neg = bool(words_b & NEGATION)
    a_aff = bool(words_a & AFFIRMATION)
    b_aff = bool(words_b & AFFIRMATION)
    return (a_neg and b_aff) or (b_neg and a_aff)

def find_contradictions(instincts):
    conflicts = []
    groups = {}
    for inst in instincts:
        key = (inst.get("domain",""), inst.get("section",""))
        groups.setdefault(key, []).append(inst)
    for key, items in groups.items():
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                tokens_i = tokenize(items[i]["pattern"])
                tokens_j = tokenize(items[j]["pattern"])
                if jaccard(tokens_i, tokens_j) > 0.1 and has_polarity_flip(items[i]["pattern"], items[j]["pattern"]):
                    conflicts.append((items[i], items[j]))
    return conflicts

# Test 1: Clear contradiction
instincts_1 = [
    {"id":"ins_001","pattern":"Always use TDD for new features","domain":"dev","section":"Working Standards"},
    {"id":"ins_002","pattern":"Skip TDD for prototype code","domain":"dev","section":"Working Standards"},
]
conflicts = find_contradictions(instincts_1)
assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}"

# Test 2: No contradiction — different sections
instincts_2 = [
    {"id":"ins_001","pattern":"Always use TDD for new features","domain":"dev","section":"Working Standards"},
    {"id":"ins_002","pattern":"Never use raw SQL in production","domain":"dev","section":"Security"},
]
conflicts = find_contradictions(instincts_2)
assert len(conflicts) == 0, f"Expected 0 conflicts, got {len(conflicts)}"

# Test 3: No contradiction — similar topic but no polarity flip
instincts_3 = [
    {"id":"ins_001","pattern":"Use humanizer on cover letters","domain":"job-search","section":"User Preferences"},
    {"id":"ins_002","pattern":"Use humanizer on CV bullets too","domain":"job-search","section":"User Preferences"},
]
conflicts = find_contradictions(instincts_3)
assert len(conflicts) == 0, f"Expected 0 conflicts, got {len(conflicts)}"

# Test 4: Contradiction with don't
instincts_4 = [
    {"id":"ins_001","pattern":"Always ask permission before vault operations","domain":"general","section":"Working Standards"},
    {"id":"ins_002","pattern":"Don't ask permission for vault operations","domain":"general","section":"Working Standards"},
]
conflicts = find_contradictions(instincts_4)
assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}"

print("All contradiction tests passed.")
