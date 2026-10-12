import openai
from decouple import config
import requests
import json
import re
import textwrap
from pymilvus import connections, utility, FieldSchema, Collection, CollectionSchema, DataType
from tqdm import tqdm
from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, connections
from decouple import config
from openai import OpenAI
import os


from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path="C:\\Users\\shaan\\Documents\\.AIS_Startup\\prototypes\\prototype3\\prototype3\\backend\\backend\\ragapp\\rag-app\\.env")

# Retrieve the API key from the environment
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

# Initialize the OpenAI client with the API key
client = OpenAI(api_key=api_key)

# Load credentials from .env
ZILLIZ_URI = config("ZILLIZ_URI")
ZILLIZ_TOKEN = config("ZILLIZ_TOKEN")

print("pipeline_utils.py imports are working!") 

# * 
def connect_to_zilliz():
    """Connect to Zilliz DB using pymilvus."""
    connections.connect(uri=ZILLIZ_URI, token=ZILLIZ_TOKEN)
    print(f"Connected to Zilliz DB at {ZILLIZ_URI}")

_COLLECTION_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,254}")


# *
def get_or_create_collection(collection_name, dimension):
    """Open a tenant collection, creating it when this tenant has none yet.

    Callers must pass a server-derived collection name. The shared
    AIS_Information collection is not selected here.
    """
    if not isinstance(collection_name, str) or not _COLLECTION_NAME.fullmatch(collection_name):
        raise ValueError("Invalid collection name")

    if utility.has_collection(collection_name):
        collection = Collection(name=collection_name)
        collection.load()
        print(f"Using existing collection '{collection_name}'.")
        return collection

    fields = [
        FieldSchema(name="primary_key", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=8192),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
    ]
    schema = CollectionSchema(fields=fields, description="Tenant-isolated documents")
    collection = Collection(name=collection_name, schema=schema)
    collection.create_index(
        field_name="vector",
        index_params={"metric_type": "COSINE", "index_type": "AUTOINDEX", "params": {}},
    )
    collection.load()
    print(f"Collection '{collection_name}' created.")
    return collection


# * 
def format_docs(search_results):
    lines = []
    for hits in search_results:        # Each element in `search_results` is a list of Hit objects
        for h in hits:
            # Remove the second argument to avoid the TypeError
            title = h.entity.get("title") or ""
            description = h.entity.get("description") or ""
            lines.append(f"Title: {title}\nDescription: {description}")
    return "\n\n".join(lines)



# * 
def retrieve_documents(collection, query, embedding_model, limit=5):
    """
    Retrieve documents from Zilliz based on a query string.
    """  

    QUERY_PARAM = {
    "metric_type": "COSINE",
    "params": {"ef": 64},
    }

    query_embeddings = get_embedding(query)
    
    results = collection.search(
        [query_embeddings],
        anns_field="vector",
        param=QUERY_PARAM,
        limit=5,
        output_fields=["title", "description"]
    )
    for i, hits in enumerate(results):
        print("Description:", query[i])
        print("Results:")
        for ii, h in enumerate(hits):
            print("\tRank:", ii + 1, "Score:", h.score, "Title:", h.entity.get("title"))
            print(textwrap.fill(h.entity.get("description"), 88))
            print()
    return results


def get_embedding(text, model="text-embedding-ada-002"):
    # text = text.replace("\n", " ")
    return OpenAI().embeddings.create(input = [text], model=model).data[0].embedding


# * 
def generate_prompt(context, question):
    """
    Create a default informative prompt for the LLM.
    """
    prompt = (
        "You are an expert AI assistant specializing in analyzing and summarizing documents. "
        "Below is the context from the retrieved documents:\n\n"
        f"{context}\n\n"
        "Based on the above, answer the following question in a concise and informative manner:\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )
    return prompt

# * 
def call_openai(prompt, model):
    """
    Call the OpenAI API with the generated prompt.
    """

    # Load environment variables from .env file
    load_dotenv(dotenv_path="backend\\ragapp\\rag-app\\.env")

    # Retrieve the API key from the environment
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    # Initialize the OpenAI client with the API key
    client = OpenAI(api_key=api_key)

    client = OpenAI()
   
    response = client.chat.completions.create(
        model=model,
        store=True,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return (response.choices[0].message.content)

