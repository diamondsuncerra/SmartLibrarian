import os
from dotenv import load_dotenv; load_dotenv()
from openai import OpenAI
from chromadb import PersistentClient
from chromadb.utils import embedding_functions

print("Python OK")

ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name=os.getenv("EMBED_MODEL", "text-embedding-3-small"),
)
client = PersistentClient(path=".chroma")  # creates a local folder
col = client.get_or_create_collection("books", embedding_function=ef)

if col.count() == 0:
    col.add(
        ids=["1","2"],
        documents=["friendship and magic in a fantasy world", "dystopian surveillance society"],
        metadatas=[{"title":"The Hobbit"},{"title":"1984"}],
    )

res = col.query(query_texts=["I want friendship and adventure"], n_results=2)
print("Results:", [(m["title"], r) for m, r in zip(res["metadatas"][0], res["documents"][0])])
print("Chroma OK")
