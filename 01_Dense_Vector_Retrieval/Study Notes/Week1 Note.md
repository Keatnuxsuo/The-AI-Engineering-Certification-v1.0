## Dense vs sparse embeddings

Sparse embeddings are better for lexical precision.
Dense embeddings are better for semantic similarity.
Example:

- Query: "python abstract base class"
- Sparse retrieval favors docs containing those exact terms.
- Dense retrieval may also find docs about “interfaces” or “inheritance” even without exact wording.


##  RecursiveCharacterTextSplitter

Why do we need RecursiveCharacterTextSplitter?
- Because documents often have messy structure

How it works?
- "Can I cut at a paragraph? No? A sentence? No? A word? No? Fine, I'll cut at a character."

Underlying Computer Science Concept

This is actually a classic algorithmic idea:

Progressive Decomposition

Try:

Biggest meaningful unit
      ↓
Smaller unit
      ↓
Smaller unit
      ↓
Smallest unit

You see similar ideas in:

Parsing compilers
File system traversal
Divide-and-conquer algorithms
Tree searches

The algorithm is effectively saying:

Preserve as much semantic structure as possible before resorting to brute-force splitting.