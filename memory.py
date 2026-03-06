# memory.py
import uuid
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

class ChatMemory:

    def __init__(self, persist_dir="./chroma_db"):
        self.client = chromadb.Client(
            Settings(
                persist_directory=persist_dir,
                is_persistent=True
            )
        )

        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        self.collection = self.client.get_or_create_collection(
            name="chat_memory",
            embedding_function=self.embedding_function
        )

    def add_message(self, role, content, user_id="default", extra_metadata=None):
        message_id = str(uuid.uuid4())
        metadata = {"role": role, "user_id": user_id}
        if extra_metadata:
            metadata.update(extra_metadata)
        self.collection.add(
            ids=[message_id],
            documents=[content],
            metadatas=[metadata]
        )

    def query_history(self, query, user_id="default", n=5, composite_key=None):
        where_clause = {"user_id": user_id}
        if composite_key:
            where_clause = {"composite": composite_key}
        results = self.collection.query(
            query_texts=[query],
            n_results=n,
            where=where_clause
        )
        messages = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                messages.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i]
                })
        return messages

    def get_user_name(self, user_id="default"):
        composite_key = f"{user_id}|system_name"
        results = self.query_history("user_name", user_id=user_id, n=1, composite_key=composite_key)
        if results:
            return results[0]["content"]
        return None

    