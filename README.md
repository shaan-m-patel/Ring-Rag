# RING RAG Application (Prototype 3.0)

## Demo
[https://youtu.be/-_mzu2c2y6w](https://youtu.be/-_mzu2c2y6w?t=270)

## Overview

The **RING RAG** (Retrieval-Augmented Generation) application is an advanced AI-powered system designed to facilitate the retrieval and processing of documents using state-of-the-art language models. It enables users to upload multiple documents, which are then preprocessed, vectorized, and indexed for efficient retrieval. The application is optimized for **query decomposition** and **intelligent chunking** to improve response accuracy and relevance.

### Key Features:

- **Multi-Document Processing:** Supports uploading and processing of multiple files simultaneously.
- **Query Decomposition:** Breaks down complex queries into sub-queries for more precise retrieval.
- **Attention-Based Chunking:** Segments documents using advanced chunking techniques to preserve context.
- **Summarization Techniques:** Generates concise document overviews for better query responses.
- **Customizable Vector Storage:** Flexible vectorization pipeline with metadata tagging.
- **Real-Time Transcription Support:** Enables AI-powered customer service applications.

## Project Structure

```
rag-app
├── src
│   ├── main.py          # Main logic for loading, processing, and querying documents
│   ├── file_upload.py   # Handles file uploads from the user's computer
│   ├── preprocessing.py # Implements intelligent chunking and metadata tagging
│   ├── query_engine.py  # Handles query decomposition and retrieval
│   ├── utils
│   │   └── __init__.py  # Utility functions for various tasks
│   ├── vector_store.py  # Manages vectorization and indexing of documents
│   └── types
│       └── index.py     # Custom types and interfaces for type safety
├── requirements.txt     # Project dependencies
└── README.md            # Documentation for the project
```

## Installation

To set up the RAG application, follow these steps:

1. **Clone the repository:**

   ```sh
   git clone <repository-url>
   cd rag-app
   ```

2. **Install the required dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

## How It Works

### 1. Preprocessing & Chunking

Before documents are stored in the vector database, they go through a **preprocessing pipeline**:

- **Text Cleaning:** Removes unnecessary characters, formatting, and stopwords.
- **Attention-Based Chunking:** Uses NLP techniques to segment documents into meaningful, context-aware chunks.
- **Summarization:** Generates brief summaries for each chunk to improve retrieval efficiency.

### 2. Query Decomposition

For complex user queries, the system:

- **Breaks queries into sub-queries** for granular retrieval.
- **Maps queries to relevant document chunks** using semantic search.
- **Synthesizes responses** from multiple retrieved chunks.

### 3. Vectorization & Storage

- **Embeddings:** Each document chunk is converted into a vector representation using transformer-based embeddings.
- **Metadata Tagging:** Each chunk is stored with metadata, such as document source, timestamp, and section identifiers.

### 4. Retrieval & Augmented Generation

- The system **retrieves the most relevant document chunks** based on vector similarity.
- The retrieved chunks are **re-ranked and passed to a large language model (LLM)** for response generation.
- The final response is **context-aware and user-specific**, leveraging both structured and unstructured data.

## Usage

1. **Start the application:**

   ```sh
   python src/main.py
   ```

2. **Upload documents** using the file upload interface.

3. **Submit queries** related to uploaded documents.

4. **Receive AI-generated responses** based on preprocessed, intelligently chunked, and vectorized data.

## Current Status

This application is currently a **public prototype**. While it offers robust document processing and query handling capabilities, it is under active development to expand its functionalities.

## Future Enhancements

### 1. Live Phone Transcription Integration

We plan to integrate **live phone transcription** capabilities to enhance real-time data processing. This will involve:

- **Real-Time Transcription:** Converting live phone conversations into text.
- **Immediate Analysis:** Processing transcribed text for instant insights and responses.
- **UI Development:** Creating a user-friendly interface to manage live transcriptions.

### 2. CRM Functionality

To improve customer relationship management, future updates will include:

- **CRM Integration:** Seamlessly connecting with existing CRM systems to synchronize data.
- **Enhanced Data Management:** Allowing for better tracking of customer interactions and histories.
- **Automated Summaries:** Generating concise summaries of interactions for quick reference.

## Contributing

Contributions are welcome! If you would like to contribute:

1. **Fork the repository.**
2. **Implement improvements or fixes.**
3. **Submit a pull request.**

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
