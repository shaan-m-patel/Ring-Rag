# app.py
import hashlib
import logging
import os
import threading
from collections import defaultdict
from urllib.parse import urlparse

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.utils import secure_filename

from security import (
    authenticate_header,
    collection_name_for_tenant,
    is_safe_collection_name,
    quota,
    settings,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
settings.load()
app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes

if not settings.identities:
    logger.warning("RING_API_TOKENS is empty; every API request will be rejected.")

# Credentials are checked on the server. CORS only lets the configured
# frontend origin read responses; it is not the access-control mechanism.
CORS(
    app,
    resources={r"/*": {"origins": settings.origins}},
    allow_headers=["Content-Type", "Authorization"],
    methods=["POST", "OPTIONS"],
    supports_credentials=False,
)

_hash_lock = threading.Lock()
_uploaded_hashes = defaultdict(set)
_ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def _load_query_module():
    from utils import query_utils

    return query_utils


def _load_upload_module():
    from utils import upload_utils

    return upload_utils


def upload_root():
    root = os.path.realpath(os.environ.get("UPLOAD_FOLDER", "uploads"))
    os.makedirs(root, exist_ok=True)
    return root


def tenant_upload_dir(tenant_id):
    root = upload_root()
    digest = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:16]
    path = os.path.realpath(os.path.join(root, digest))
    if os.path.commonpath([root, path]) != root:
        raise RuntimeError("Refusing upload path outside the upload root")
    os.makedirs(path, exist_ok=True)
    return path


def _open_tenant_collection(query_utils):
    if not is_safe_collection_name(g.collection_name):
        raise RuntimeError("Unsafe collection name")
    return query_utils.get_or_create_collection(g.collection_name, 1536)


def _charge(action, cost=1):
    limit = settings.query_quota if action == "query" else settings.upload_quota
    retry_after = quota.consume(
        g.user_id,
        action,
        limit,
        settings.quota_window_seconds,
        cost,
    )
    if not retry_after:
        return None
    response = jsonify({"error": "Quota exceeded. Try again later."})
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


def _extension(filename):
    return os.path.splitext(filename)[1].lower()


def _save_upload(storage, directory):
    filename = secure_filename(storage.filename or "")
    if not filename or _extension(filename) not in _ALLOWED_EXTENSIONS:
        return None
    path = os.path.realpath(os.path.join(directory, filename))
    if os.path.commonpath([directory, path]) != directory:
        return None
    storage.save(path)
    return path


@app.before_request
def require_authentication():
    """Reject every request that does not present a configured bearer token.

    Browser preflight (OPTIONS) is answered by CORS and carries no API call.
    """
    if request.method == "OPTIONS":
        return None

    identity = authenticate_header(request.headers.get("Authorization"))
    if identity is None:
        return jsonify({"error": "Authentication required."}), 401

    g.user_id = identity["user_id"]
    g.tenant_id = identity["tenant_id"]
    g.collection_name = collection_name_for_tenant(identity["tenant_id"])
    return None


@app.route("/query", methods=["POST"])
def handle_query():
    data = request.get_json(silent=True) or {}
    query_text = data.get("query_text", "")
    if not isinstance(query_text, str) or not query_text.strip():
        return jsonify({"error": "query_text is required."}), 400
    query_text = query_text.strip()
    if len(query_text) > 4000:
        return jsonify({"error": "query_text is too long."}), 400

    denied = _charge("query", 1)
    if denied is not None:
        return denied

    try:
        query_utils = _load_query_module()
        query_utils.connect_to_zilliz()
        # Collection name comes from the token's tenant, never from the body.
        collection = _open_tenant_collection(query_utils)
        retrieved_docs = query_utils.retrieve_documents(
            collection, query_text, "text-embedding-ada-002", limit=5
        )
        if not retrieved_docs:
            return jsonify({"answer": "No relevant documents found."})

        formatted_context = query_utils.format_docs(retrieved_docs)
        prompt = query_utils.generate_prompt(formatted_context, query_text)
        result = query_utils.call_openai(prompt, model="gpt-4o-mini")
    except Exception:
        logger.exception("Query failed for user %s", g.user_id)
        return jsonify({"error": "Query failed."}), 500

    return jsonify({"answer": result})


@app.route("/upload_file", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request."}), 400

    upload = request.files["file"]
    if not upload or not upload.filename:
        return jsonify({"error": "No file selected."}), 400

    filename = secure_filename(upload.filename)
    if not filename or _extension(filename) not in _ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only .pdf and .txt files can be uploaded."}), 400

    denied = _charge("upload", 1)
    if denied is not None:
        return denied

    try:
        directory = tenant_upload_dir(g.tenant_id)
        file_path = _save_upload(upload, directory)
        if file_path is None:
            return jsonify({"error": "Could not store the uploaded file."}), 400

        upload_utils = _load_upload_module()
        with _hash_lock:
            docs = upload_utils.restructure_files(
                [file_path],
                _uploaded_hashes[g.tenant_id],
                max_document_chars=settings.max_document_chars,
                max_chunks_per_file=settings.max_chunks_per_file,
            )
        if not docs[0]:
            return jsonify({"message": "Nothing new to ingest."}), 200

        query_utils = _load_query_module()
        query_utils.connect_to_zilliz()
        collection = _open_tenant_collection(query_utils)
        upload_utils.batch_insert(collection, docs, "text-embedding-ada-002", BATCH_SIZE=100)
    except Exception:
        logger.exception("File upload failed for user %s", g.user_id)
        return jsonify({"error": "Upload failed."}), 500

    return jsonify({"message": f"File '{filename}' uploaded and ingested."}), 200


@app.route("/upload_folder", methods=["POST"])
def upload_folder():
    uploads = request.files.getlist("files") if request.files else []
    selected = []
    for upload in uploads:
        filename = secure_filename(upload.filename or "")
        if filename and _extension(filename) in _ALLOWED_EXTENSIONS:
            selected.append(upload)

    if not selected:
        return jsonify({"error": "No files in request."}), 400
    if len(selected) > settings.max_files_per_request:
        return jsonify({"error": "Too many files in one upload."}), 400

    denied = _charge("upload", len(selected))
    if denied is not None:
        return denied

    try:
        directory = tenant_upload_dir(g.tenant_id)
        file_paths = []
        stored_names = []
        for upload in selected:
            file_path = _save_upload(upload, directory)
            if file_path is None:
                continue
            file_paths.append(file_path)
            stored_names.append(os.path.basename(file_path))

        if not file_paths:
            return jsonify({"error": "No files were actually saved."}), 400

        upload_utils = _load_upload_module()
        with _hash_lock:
            docs = upload_utils.restructure_files(
                file_paths,
                _uploaded_hashes[g.tenant_id],
                max_document_chars=settings.max_document_chars,
                max_chunks_per_file=settings.max_chunks_per_file,
            )
        if docs[0]:
            query_utils = _load_query_module()
            query_utils.connect_to_zilliz()
            collection = _open_tenant_collection(query_utils)
            upload_utils.batch_insert(collection, docs, "text-embedding-ada-002", BATCH_SIZE=100)
    except Exception:
        logger.exception("Folder upload failed for user %s", g.user_id)
        return jsonify({"error": "Upload failed."}), 500

    return jsonify({
        "message": "Folder files uploaded and ingested.",
        "files": stored_names,
    }), 200


@app.route("/process_url", methods=["POST"])
def process_url():
    data = request.get_json(silent=True) or {}
    url = data.get("url", None)
    if not isinstance(url, str) or not url.strip():
        return jsonify({"error": "No URL provided."}), 400

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return jsonify({"error": "URL must be http or https."}), 400

    denied = _charge("upload", 1)
    if denied is not None:
        return denied

    # URL fetching is intentionally not implemented. When it is added it must
    # insert into g.collection_name for the authenticated tenant only.
    return jsonify({"message": "URL accepted."}), 200


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=debug)
