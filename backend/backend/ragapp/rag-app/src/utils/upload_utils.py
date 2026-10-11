import hashlib
import fitz  # PyMuPDF
import os
from openai import OpenAI
from tqdm import tqdm
from pymilvus import connections, utility, FieldSchema, Collection, CollectionSchema, DataType
from utils.query_utils import connect_to_zilliz, call_openai
import re
from customprompts import summary_prompt_upload

print("file_upload.py imports are working!") 

def hash_file(file_path):
    """Create a hash of the file contents to track processed files."""
    with open(file_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    return file_hash


def load_pdf(file_path):
    """Load a PDF file and extract its text content."""
    documents = []
    try:
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            documents.append({
                "page_content": text,
                "metadata": {"source": file_path, "page": page_num},
            })
    except Exception as e:
        print(f"Error processing PDF {file_path}: {e}")
    return documents


def chunk_text(text, chunk_size):
    """
    A semantic chunking approach:
      1) Call OpenAI to get a summary of the entire text.
      2) Add that summary as the first chunk.
      3) Split the text by paragraphs, then by sentences if needed,
         ensuring no chunk exceeds chunk_size characters.
    Returns a list of text chunks.
    """

    # --- 1) Get a summary of the entire text from OpenAI ---

    summary_prompt = summary_prompt_upload(text)

    summary = call_openai(summary_prompt, model="gpt-3.5-turbo")
    summary = summary.strip()  # Clean up extra whitespace/newlines

    # First chunk = summary
    chunks = [summary]

    # --- 2) Paragraph splitting ---
    # Split on double newlines as a naive way to detect paragraphs
    paragraphs = text.split("\n\n")

    # We'll collect intermediate "paragraph-level" chunks into a list
    para_chunks = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            # Skip empty paragraphs
            continue

        # If paragraph is short enough, take it directly
        if len(paragraph) <= chunk_size:
            para_chunks.append(paragraph)
        else:
            # --- 3) Sentence-based splitting if paragraph is too large ---
            # Use a regex to split on sentence boundaries (roughly).
            # This splits on '.', '!', or '?' followed by a space.
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)

            current_chunk = []
            current_len = 0

            for sentence in sentences:
                sentence_len = len(sentence)

                # If adding this sentence would exceed the chunk_size, close off the current chunk
                if current_len + sentence_len > chunk_size:
                    if current_chunk:
                        para_chunks.append(" ".join(current_chunk).strip())
                    # Start a new chunk with the current sentence
                    current_chunk = [sentence]
                    current_len = sentence_len
                else:
                    # Add sentence to current chunk
                    current_chunk.append(sentence)
                    current_len += sentence_len + 1  # +1 for the space or separator

            # Append any leftover sentences in the final chunk
            if current_chunk:
                para_chunks.append(" ".join(current_chunk).strip())

    # One last pass: if any "chunk" is still longer than chunk_size
    # (e.g., a single extremely long sentence), we split by character limit.
    final_chunks = []
    for block in para_chunks:
        if len(block) > chunk_size:
            for i in range(0, len(block), chunk_size):
                final_chunks.append(block[i : i + chunk_size])
        else:
            final_chunks.append(block)

    # Add the semantic chunks after the summary
    chunks.extend(final_chunks)

    return chunks

# * 
def restructure_files(file_paths, uploaded_hashes, max_document_chars=50000, max_chunks_per_file=40):
    """
    Upload multiple files. Concatenate all text from a file, then chunk it, then
    name each chunk using the filename and the chunk number (e.g., "file.pdf - 1").
    Returns titles & descriptions in a 2D list.

    Text sent to the shared OpenAI key is capped so one file cannot unbounded
    the summarization and embedding calls.
    """
    if max_document_chars < 1:
        max_document_chars = 1
    if max_chunks_per_file < 1:
        max_chunks_per_file = 1

    data = [[], []]  # [titles, descriptions]
    for file_path in file_paths:
        file_hash = hash_file(file_path)
        if file_hash in uploaded_hashes:
            print(f"File already processed: {os.path.basename(file_path)}")
            continue

        filename = os.path.basename(file_path)
        lowered = file_path.lower()

        # PDF handling
        if lowered.endswith(".pdf"):
            docs = load_pdf(file_path)
            full_text = " ".join(doc["page_content"] for doc in docs)
            full_text = full_text[:max_document_chars]
            chunks = chunk_text(full_text, chunk_size=1200)[:max_chunks_per_file]
            for idx, chunk in enumerate(chunks, start=1):
                data[0].append(f"{filename} - {idx}")
                data[1].append(chunk)
            print(f"Uploaded {filename} in {len(chunks)} chunks.")

        # TXT handling
        elif lowered.endswith(".txt"):
            with open(file_path, "r") as f:
                full_text = f.read(max_document_chars)
            chunks = chunk_text(full_text, chunk_size=1200)[:max_chunks_per_file]
            for idx, chunk in enumerate(chunks, start=1):
                data[0].append(f"{filename} - {idx}")
                data[1].append(chunk)
            print(f"Uploaded {filename} in {len(chunks)} chunks.")

        else:
            print(f"Unsupported file type: {filename}")
            continue

        uploaded_hashes.add(file_hash)

    return data


def get_embedding(text, model):
    # text = text.replace("\n", " ")
    return OpenAI().embeddings.create(input = [text], model=model).data[0].embedding


# * 
def batch_insert(collection, dataset, embedding_model, BATCH_SIZE=100):
    """
    Inserts data in batches to Milvus/Zilliz.

    dataset[0] = list of chunk titles (strings)
    dataset[1] = list of chunk contents (strings)
    """

    # Reconnect if needed
    connect_to_zilliz()

    total_chunks = len(dataset[0])
    print(f"Inserting {total_chunks} chunks into Zilliz DB...")

    # Buffers to accumulate until we reach BATCH_SIZE
    buffer_titles = []
    buffer_texts = []

    # Helper function to embed all texts in buffer_texts
    def embed_and_insert():
        # Embedding each chunk individually
        embeddings = []
        for text in buffer_texts:
            emb = get_embedding(text, model=embedding_model)
            embeddings.append(emb)  # each emb is length 1536

        # Construct the final data in the order your collection expects
        insert_data = [
            buffer_titles,  # field 1 (titles)
            buffer_texts,   # field 2 (raw text)
            embeddings      # field 3 (vectors)
        ]

        # Insert into Milvus/Zilliz
        collection.insert(insert_data)

    # 1. Loop through each chunk. Lengths match the tenant collection schema.
    for i in tqdm(range(total_chunks)):
        buffer_titles.append(dataset[0][i][:500])
        buffer_texts.append(dataset[1][i][:8000])

        # 2. If we reached the BATCH_SIZE, insert
        if len(buffer_titles) >= BATCH_SIZE:
            embed_and_insert()
            # Reset the buffers for the next batch
            buffer_titles = []
            buffer_texts = []

    # 3. Handle leftover data (if less than BATCH_SIZE remain)
    if len(buffer_titles) > 0:
        embed_and_insert()
        buffer_titles = []
        buffer_texts = []
